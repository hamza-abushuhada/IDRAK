import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo_server as lab

class LabTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_source, self.old_receiver = lab.SOURCE_DB, lab.RECEIVER_DB
        self.old_flush=lab.flush_events
        lab.SOURCE_DB=Path(self.tmp.name)/'src.sqlite3'
        lab.RECEIVER_DB=Path(self.tmp.name)/'recv.sqlite3'
        lab.init_db()
        lab.flush_events=lambda channel=None,shop=None: None
    def tearDown(self):
        lab.flush_events=self.old_flush
        lab.SOURCE_DB,lab.RECEIVER_DB=self.old_source,self.old_receiver
        self.tmp.cleanup()
    def events(self,channel):
        return lab.source_get(lab.LEGACY_SHOP,'/api/'+channel+'/events',{'after':['0'],'limit':['200']})['events']
    def deliver(self,event):
        p=event['payload'];raw=json.dumps(p,ensure_ascii=False).encode()
        return lab.ingest_event(raw,lab.sign(raw,lab.LEGACY_SHOP))
    def test_pos_sale_and_inventory(self):
        x=lab.create_order(lab.LEGACY_SHOP,'pos',{'items':[{'sku':'BRG-001','quantity':2}], 'payment_method':'cash'})
        self.assertEqual(x['total'],'8.500')
        self.assertEqual(x['status'],'completed')
        product=[p for p in lab.source_get(lab.LEGACY_SHOP,'/api/products',{})['products'] if p['sku']=='BRG-001'][0]
        self.assertEqual(product['stock'],58)
        events=self.events('pos')
        self.assertEqual(events[0]['payload']['event_type'],'sale.created')
        self.assertEqual(events[1]['payload']['event_type'],'inventory.updated')
    def test_pending_payment_and_refund(self):
        o=lab.create_order(lab.LEGACY_SHOP,'web',{'items':[{'sku':'FRY-001','quantity':3}], 'payment_method':'cash_on_delivery'})
        self.assertEqual(o['status'],'pending')
        product=lambda:[p for p in lab.source_get(lab.LEGACY_SHOP,'/api/products',{})['products'] if p['sku']=='FRY-001'][0]
        self.assertEqual(product()['stock'],90)
        paid=lab.change_order(lab.LEGACY_SHOP,o['order_id'],'completed')
        self.assertEqual(paid['status'],'completed')
        self.assertEqual(product()['stock'],87)
        refund=lab.change_order(lab.LEGACY_SHOP,o['order_id'],'refunded')
        self.assertEqual(refund['status'],'refunded')
        self.assertEqual(product()['stock'],90)
        with self.assertRaises(ValueError): lab.change_order(lab.LEGACY_SHOP,o['order_id'],'completed')
    def test_signature_and_dedup(self):
        lab.create_order(lab.LEGACY_SHOP,'pos',{'items':[{'sku':'BRG-002','quantity':1}]})
        e=self.events('pos')[0]
        raw=json.dumps(e['payload']).encode()
        self.assertEqual(lab.ingest_event(raw,'sha256=bad')[0],401)
        self.assertEqual(self.deliver(e)[0],201)
        self.assertEqual(self.deliver(e)[1]['status'],'duplicate_skipped')
        self.assertEqual(lab.receiver_get(lab.LEGACY_SHOP,'/api/summary')['invoices'],1)
        self.assertEqual(lab.receiver_get(lab.LEGACY_SHOP,'/api/summary')['events'],1)
    def test_two_sources_unique_and_update_not_new_sale(self):
        pos=lab.create_order(lab.LEGACY_SHOP,'pos',{'items':[{'sku':'BRG-001','quantity':1}]})
        web=lab.create_order(lab.LEGACY_SHOP,'web',{'items':[{'sku':'BRG-001','quantity':1}], 'payment_method':'cash_on_delivery'})
        for e in self.events('pos')+self.events('web'):self.deliver(e)
        s=lab.receiver_get(lab.LEGACY_SHOP,'/api/summary')
        self.assertEqual(s['invoices'],2)
        self.assertEqual(s['revenue'],'4.250')
        lab.change_order(lab.LEGACY_SHOP,web['order_id'],'completed')
        for e in self.events('web'):self.deliver(e)
        s=lab.receiver_get(lab.LEGACY_SHOP,'/api/summary')
        self.assertEqual(s['invoices'],2)
        self.assertEqual(s['revenue'],'8.500')
        # re-delivering ALL events to simulate reconnect must not duplicate.
        for e in self.events('pos')+self.events('web'):self.deliver(e)
        self.assertEqual(lab.receiver_get(lab.LEGACY_SHOP,'/api/summary')['invoices'],2)
    def test_refund_reduces_reported_revenue(self):
        o=lab.create_order(lab.LEGACY_SHOP,'pos',{'items':[{'sku':'PZA-001','quantity':1}]})
        for e in self.events('pos'):self.deliver(e)
        self.assertEqual(lab.receiver_get(lab.LEGACY_SHOP,'/api/summary')['revenue'],'6.750')
        lab.change_order(lab.LEGACY_SHOP,o['order_id'],'refunded')
        for e in self.events('pos'):self.deliver(e)
        self.assertEqual(lab.receiver_get(lab.LEGACY_SHOP,'/api/summary')['revenue'],'0.000')
        self.assertEqual(lab.receiver_get(lab.LEGACY_SHOP,'/api/summary')['invoices'],1)
    def test_replay_out_of_order_does_not_revert_order(self):
        o=lab.create_order(lab.LEGACY_SHOP,'web',{'items':[{'sku':'SLD-001','quantity':1}], 'payment_method':'cash_on_delivery'})
        lab.change_order(lab.LEGACY_SHOP,o['order_id'],'completed')
        changes=self.events('web')
        later=[v for v in changes if v['payload']['event_type']=='sale.updated'][0]
        older=[v for v in changes if v['payload']['event_type']=='sale.created'][0]
        self.deliver(later);self.deliver(older)
        orders=lab.receiver_get(lab.LEGACY_SHOP,'/api/synced-orders')['orders']
        self.assertEqual(orders[0]['status'],'completed')
        self.assertEqual(orders[0]['revision'],2)
    def test_bad_inputs(self):
        with self.assertRaises(ValueError):lab.create_order(lab.LEGACY_SHOP,'pos',{'items':[{'sku':'x','quantity':1}]})
        with self.assertRaises(ValueError):lab.create_order(lab.LEGACY_SHOP,'pos',{'items':[{'sku':'FRY-001','quantity':0}]})
        with self.assertRaises(ValueError):lab.create_order(lab.LEGACY_SHOP,'web',{'items':[{'sku':'FRY-001','quantity':100}]})
    def test_incremental_cursor(self):
        lab.create_order(lab.LEGACY_SHOP,'pos',{'items':[{'sku':'DRK-001','quantity':1}]})
        first=lab.source_get(lab.LEGACY_SHOP,'/api/pos/events',{'after':['0'],'limit':['1']})
        second=lab.source_get(lab.LEGACY_SHOP,'/api/pos/events',{'after':[str(first['next_cursor'])]})
        self.assertEqual(len(first['events']),1)
        self.assertEqual(len(second['events']),1)
        self.assertGreater(second['next_cursor'],first['next_cursor'])

if __name__=='__main__':unittest.main()

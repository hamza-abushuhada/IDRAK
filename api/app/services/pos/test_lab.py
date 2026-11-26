"""اختبارات موصّلات المختبر (lab.py) — المكتبة القياسية فقط، بلا شبكة.

تغطّي: تحويل أحداث المختبر إلى النموذج الموحّد (الحالات المالية)، المخزون
المطلق، خريطة طرق الدفع، التحقّق من توقيع webhook، والترقيم (pagination) عبر
ناقل محقون.
"""

import hashlib
import hmac
import json
import os
import sys
import unittest
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import model  # noqa: E402
import lab  # noqa: E402
from model import EVENT_SALE, EVENT_REFUND, EVENT_INVENTORY  # noqa: E402


def _sale_payload(status="completed", rev=1, payment="cash", channel="pos", ext="POS-000001"):
    return {
        "schema_version": "1.0", "event_id": f"idrak-lab-pos:{ext}:r{rev}:sale.created",
        "event_type": "sale.created", "occurred_at": "2026-11-20T10:00:00Z",
        "source": {"system": "idrak-lab-pos", "account_id": "idrak-test-shop-001", "channel": channel},
        "source_sequence": 1,
        "order": {"external_id": ext, "status": status, "payment_method": payment,
                  "customer": "عميل", "currency": "JOD", "total": "8.500",
                  "items": [{"sku": "BRG-001", "name": "برغر", "quantity": 2, "unit_price": "4.250"}],
                  "created_at": "2026-11-20T10:00:00Z", "updated_at": "2026-11-20T10:05:00Z", "revision": rev},
    }


def _inv_payload(sku="BRG-001", on_hand=58, seq=9):
    return {
        "schema_version": "1.0", "event_id": f"idrak-lab-pos:POS-1:{sku}:r1:inventory.updated",
        "event_type": "inventory.updated", "occurred_at": "2026-11-20T10:05:00Z",
        "source": {"system": "idrak-lab-pos", "account_id": "idrak-test-shop-001", "channel": "pos"},
        "source_sequence": seq, "inventory": {"sku": sku, "on_hand": on_hand, "location_id": "main"},
    }


class TestMapPayload(unittest.TestCase):
    def test_completed_sale_maps_to_sale(self):
        ev = lab.map_payload(_sale_payload("completed"))
        self.assertEqual(ev.type, EVENT_SALE)
        self.assertEqual(ev.payload.status, "completed")
        self.assertEqual(ev.external_id, "POS-000001")
        self.assertEqual(ev.payload.lines[0].quantity, Decimal("2"))
        self.assertEqual(ev.payload.total(), Decimal("8.500"))
        ev.validate()  # يجب ألا يرفع

    def test_pending_maps_to_none(self):
        self.assertIsNone(lab.map_payload(_sale_payload("pending")))

    def test_cancelled_maps_to_none(self):
        self.assertIsNone(lab.map_payload(_sale_payload("cancelled")))

    def test_refunded_maps_to_refund(self):
        ev = lab.map_payload(_sale_payload("refunded", rev=2))
        self.assertEqual(ev.type, EVENT_REFUND)
        self.assertEqual(ev.payload.status, "returned")
        self.assertEqual(ev.version_key(), "2")

    def test_payment_method_mapping(self):
        self.assertEqual(lab.map_payload(_sale_payload(payment="demo_card")).payload.payment_method, "online")
        self.assertEqual(lab.map_payload(_sale_payload(payment="cash_on_delivery")).payload.payment_method, "cash")
        self.assertEqual(lab.map_payload(_sale_payload(payment="card")).payload.payment_method, "card")

    def test_inventory_is_absolute(self):
        ev = lab.map_payload(_inv_payload(on_hand=58, seq=9))
        self.assertEqual(ev.type, EVENT_INVENTORY)
        self.assertTrue(ev.payload.absolute)
        self.assertEqual(ev.payload.delta, Decimal("58"))
        self.assertEqual(ev.external_id, "inv:BRG-001")
        self.assertEqual(ev.version_key(), "9")
        ev.validate()

    def test_unknown_type_is_ignored(self):
        self.assertIsNone(lab.map_payload({"event_type": "customer.updated"}))


class TestWebhookSignature(unittest.TestCase):
    def setUp(self):
        self.adp = lab.LabPOSAdapter(secret="s3cret")

    def _sig(self, body):
        return "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()

    def test_valid_signature_accepted(self):
        body = json.dumps(_sale_payload(), separators=(",", ":")).encode("utf-8")
        self.assertTrue(self.adp.verify_webhook({"X-Idrak-Signature": self._sig(body)}, body))

    def test_header_case_insensitive(self):
        body = b'{"a":1}'
        self.assertTrue(self.adp.verify_webhook({"x-idrak-signature": self._sig(body)}, body))

    def test_wrong_signature_rejected(self):
        body = b'{"a":1}'
        self.assertFalse(self.adp.verify_webhook({"X-Idrak-Signature": "sha256=deadbeef"}, body))

    def test_missing_signature_rejected(self):
        self.assertFalse(self.adp.verify_webhook({}, b'{"a":1}'))

    def test_event_id_of(self):
        body = json.dumps(_sale_payload(), separators=(",", ":")).encode("utf-8")
        self.assertEqual(self.adp.event_id_of(body), "idrak-lab-pos:POS-000001:r1:sale.created")


class TestPaginationWithInjectedTransport(unittest.TestCase):
    def test_pull_paginates_and_maps(self):
        pages = {
            0: {"events": [{"cursor": 1, "payload": _sale_payload(ext="POS-000001")},
                           {"cursor": 2, "payload": _sale_payload("pending", ext="POS-000002")}],
                "next_cursor": 2, "has_more": True},
            2: {"events": [{"cursor": 3, "payload": _inv_payload()}],
                "next_cursor": 3, "has_more": False},
        }

        def transport(url):
            after = int(url.split("after=")[1].split("&")[0])
            return pages[after]

        adp = lab.LabPOSAdapter(transport=transport)
        events, cursor = adp._pull(0)
        # الطلب المعلّق يُحذف؛ يبقى بيع + مخزون.
        self.assertEqual(cursor, 3)
        self.assertEqual([e.type for e in events], [EVENT_SALE, EVENT_INVENTORY])


if __name__ == "__main__":
    unittest.main(verbosity=2)

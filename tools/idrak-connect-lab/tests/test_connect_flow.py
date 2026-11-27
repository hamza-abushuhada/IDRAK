"""Redirect authorization (no copy/paste): consent, approval, denial, expiry,
reuse, wrong shop, cashier refusal, cross-org binding and revocation.
Temporary SQLite only, through the serverless app (same code as Lab Staging)."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import test_user_login as base
from test_user_login import CASHIER_PW, OWNER_PW, lab

import pairing

IDRAK = 'https://idrak-web-staging.example.com'


class ConnectFlowTests(unittest.TestCase):
    setUp_base = base.UserLoginTests.setUp
    tearDown = base.UserLoginTests.tearDown
    client = base.UserLoginTests.client
    invite = base.UserLoginTests.invite
    activate = base.UserLoginTests.activate
    owner = base.UserLoginTests.owner
    login = base.UserLoginTests.login

    def setUp(self):
        self.setUp_base()
        env = patch.dict(os.environ, {'IDRAK_CONNECT_RETURN_ORIGIN': IDRAK})
        env.start()
        self.patches.append(env)
        self.org, self.user = str(uuid4()), str(uuid4())

    def request(self, org=None, exp=None, flow='redirect', state=None, lang='ar'):
        state = state or secrets.token_urlsafe(32)
        data = {'aud': 'idrak-lab-pairing-v1', 'org': org or self.org, 'user': self.user, 'nonce': str(uuid4()),
                'exp': exp or int(time.time()) + 600, 'name': 'مؤسسة الاختبار'}
        if flow:
            data.update(flow=flow, sh=hashlib.sha256(state.encode()).hexdigest(), lang=lang)
        value = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        return value + '.' + hmac.new(pairing.key(), b'intent:' + value.encode(), hashlib.sha256).hexdigest(), state

    def ctx(self, c, intent, state):
        return c.post('/api/connect/context', json={'intent': intent, 'state': state}, headers=self.O)

    def approve(self, c, intent, state, shop):
        return c.post('/api/connect/approve', json={'intent': intent, 'state': state, 'shop_id': shop['shop_id']}, headers=self.O)

    def exchange(self, code, intent):
        raw = json.dumps({'code': code, 'intent': intent, 'timestamp': int(time.time())}).encode()
        return pairing.exchange(raw, pairing.service_signature(raw))

    @staticmethod
    def fragment(url):
        return {k: v[0] for k, v in parse_qs(urlsplit(url).fragment).items()}

    # ---------------------------------------------------------------
    def test_full_journey_owner_approves_and_idrak_redeems_server_to_server(self):
        c = self.owner(self.a)
        intent, state = self.request()
        page = self.client().get('/connect')
        self.assertEqual(page.status_code, 200)
        self.assertIn('السماح بالربط', page.text)
        self.assertIn('no-referrer', page.text)
        info = self.ctx(c, intent, state)
        self.assertEqual(info.status_code, 200, info.text)
        body = info.json()
        self.assertEqual(body['business'], 'مؤسسة الاختبار')
        self.assertEqual([(s['shop_id'], s['role'], s['can_approve']) for s in body['shops']], [(self.a['shop_id'], 'owner', True)])
        self.assertEqual(self.fragment(body['cancel_url']), {'error': 'access_denied', 'state': state})
        self.assertTrue(body['cancel_url'].startswith(IDRAK + '/ar/app/integrations/callback#'))
        r = self.approve(c, intent, state, self.a)
        self.assertEqual(r.status_code, 200, r.text)
        url = r.json()['redirect']
        self.assertTrue(url.startswith(IDRAK + '/ar/app/integrations/callback#'), 'fixed callback, parameters only in the fragment')
        self.assertEqual(urlsplit(url).query, '')
        params = self.fragment(url)
        self.assertEqual(params['state'], state)
        with lab.connect(lab.SOURCE_DB) as db:
            stored = json.dumps([dict(x) for x in db.execute('SELECT * FROM lab_pairing_codes')])
        self.assertNotIn(params['code'], stored, 'only a hash of the code is stored')
        creds = self.exchange(params['code'], intent)
        self.assertEqual((creds['shop_id'], creds['org_id'], creds['shop_name']), (self.a['shop_id'], self.org, 'Shop A'))
        with self.assertRaises(lab.LabAuthError):
            self.exchange(params['code'], intent)  # code is single-use

    def test_request_is_single_use(self):
        c = self.owner(self.a)
        intent, state = self.request()
        self.assertEqual(self.approve(c, intent, state, self.a).status_code, 200)
        self.assertEqual(self.approve(c, intent, state, self.a).status_code, 409)
        self.assertEqual(self.ctx(c, intent, state).status_code, 409)

    def test_state_must_match_the_signed_request(self):
        c = self.owner(self.a)
        intent, state = self.request()
        for bad in (secrets.token_urlsafe(32), state[:-1], '', state + 'x'):
            self.assertEqual(self.ctx(c, intent, bad).status_code, 400)
            self.assertEqual(self.approve(c, intent, bad, self.a).status_code, 400)
        manual, _ = self.request(flow=None)  # manual pairing intents can't drive a redirect
        self.assertEqual(self.ctx(c, manual, state).status_code, 400)
        self.assertEqual(self.ctx(c, intent[:-2] + 'aa', state).status_code, 400)  # tampered signature
        bad_lang, s2 = self.request(lang='fr')
        self.assertEqual(self.ctx(c, bad_lang, s2).status_code, 400)

    def test_expired_or_overlong_requests_refused(self):
        c = self.owner(self.a)
        old, s1 = self.request(exp=int(time.time()) - 1)
        self.assertEqual(self.approve(c, old, s1, self.a).status_code, 400)
        far, s2 = self.request(exp=int(time.time()) + 3600)
        self.assertEqual(self.ctx(c, far, s2).status_code, 400)

    def test_cashier_cannot_approve(self):
        self.owner(self.a)
        cashier, r = self.activate(self.invite(self.a, 'cashier@example.org', 'cashier'), CASHIER_PW)
        self.assertEqual(r.status_code, 200)
        intent, state = self.request()
        shops = self.ctx(cashier, intent, state).json()['shops']
        self.assertEqual([(s['role'], s['can_approve']) for s in shops], [('cashier', False)])
        self.assertEqual(self.approve(cashier, intent, state, self.a).status_code, 403)
        with lab.connect(lab.SOURCE_DB) as db:
            self.assertIsNone(db.execute('SELECT 1 FROM lab_pairing_codes').fetchone())

    def test_wrong_shop_and_other_owners_shop_refused(self):
        c = self.owner(self.a)
        self.owner(self.b, 'owner-b@example.org')
        intent, state = self.request()
        self.assertEqual([s['shop_id'] for s in self.ctx(c, intent, state).json()['shops']], [self.a['shop_id']],
                         'never lists shops the user has no role in')
        self.assertEqual(self.approve(c, intent, state, self.b).status_code, 403)
        self.assertEqual(self.approve(c, intent, state, {'shop_id': 'shop-doesnotexist'}).status_code, 403)
        self.assertEqual(self.approve(c, intent, state, {'shop_id': '../x'}).status_code, 400)

    def test_shop_bound_to_another_organization_is_refused(self):
        c = self.owner(self.a)
        first, s1 = self.request()
        code = self.fragment(self.approve(c, first, s1, self.a).json()['redirect'])['code']
        self.exchange(code, first)  # shop A now belongs to self.org
        other, s2 = self.request(org=str(uuid4()))
        shop = self.ctx(c, other, s2).json()['shops'][0]
        self.assertEqual((shop['linked_elsewhere'], shop['can_approve']), (True, False))
        self.assertEqual(self.approve(c, other, s2, self.a).status_code, 409)
        again, s3 = self.request()  # the same organization may renew its own link
        self.assertTrue(self.ctx(c, again, s3).json()['shops'][0]['linked_here'])
        self.assertEqual(self.approve(c, again, s3, self.a).status_code, 200)

    def test_requires_a_signed_in_lab_user_not_tokens_or_operator(self):
        intent, state = self.request()
        self.assertEqual(self.ctx(self.client(), intent, state).status_code, 401)
        self.assertEqual(self.approve(self.client(), intent, state, self.a).status_code, 401)
        self.assertEqual(self.approve(self.client(), intent, state, self.a).headers.get('www-authenticate'), None)
        self.assertEqual(self.client().post('/api/connect/approve', json={'intent': intent, 'state': state, 'shop_id': self.a['shop_id']},
                                            headers=self.op).status_code, 401)
        tok = self.client()
        self.assertEqual(tok.post('/auth/login', json={'token': self.a['token']}, headers=self.O).status_code, 200)
        self.assertEqual(self.approve(tok, intent, state, self.a).status_code, 401)

    def test_revoked_access_and_logout_stop_approval(self):
        c = self.owner(self.a)
        token = self.invite(self.b, 'owner-a@example.org')
        r = c.post('/auth/activate', json={'token': token, 'password': OWNER_PW}, headers=self.O)
        self.assertEqual(r.status_code, 200, r.text)  # same user now owns A and B (session on B)
        intent, state = self.request()
        self.assertEqual(len(self.ctx(c, intent, state).json()['shops']), 2)
        with lab.connect(lab.SOURCE_DB) as db:
            db.execute('DELETE FROM lab_user_shops WHERE shop_id=?', (self.a['shop_id'],))
        self.assertEqual(self.approve(c, intent, state, self.a).status_code, 403, 'removed owner cannot approve')
        c.post('/auth/logout', json={}, headers=self.O)
        self.assertEqual(self.approve(c, intent, state, self.b).status_code, 401)

    def test_new_approval_supersedes_older_code_for_the_shop(self):
        c = self.owner(self.a)
        i1, s1 = self.request()
        i2, s2 = self.request()
        code1 = self.fragment(self.approve(c, i1, s1, self.a).json()['redirect'])['code']
        code2 = self.fragment(self.approve(c, i2, s2, self.a).json()['redirect'])['code']
        with self.assertRaises(lab.LabAuthError):
            self.exchange(code1, i1)
        self.assertEqual(self.exchange(code2, i2)['shop_id'], self.a['shop_id'])
        self.assertEqual(self.approve(c, i1, s1, self.a).status_code, 409, 'superseded request stays consumed')

    def test_cross_origin_and_unconfigured_return_refused(self):
        c = self.owner(self.a)
        intent, state = self.request()
        evil = c.post('/api/connect/approve', json={'intent': intent, 'state': state, 'shop_id': self.a['shop_id']},
                      headers={'Origin': 'https://evil.example'})
        self.assertEqual(evil.status_code, 403)
        for value in ('', 'http://idrak.example.com', 'https://idrak.example.com/path', 'https://user@idrak.example.com'):
            with patch.dict(os.environ, {'IDRAK_CONNECT_RETURN_ORIGIN': value}):
                self.assertEqual(self.approve(c, intent, state, self.a).status_code, 503, value)
        self.assertEqual(self.approve(c, intent, state, self.a).status_code, 200)

    def test_login_returns_only_to_the_fixed_connect_page(self):
        js = self.client().get('/login.js').text
        self.assertIn("get('next') === 'connect' ? '/connect' : '/pos'", js)


if __name__ == '__main__':
    unittest.main()

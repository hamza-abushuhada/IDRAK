"""Opt-in HTTP smoke check from Vercel's build network, never run by default.

Uses only the dedicated Lab credentials already present in its environment.
This exists because some local networks reset connections to *.vercel.app.
"""
import base64
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    mode = os.environ.get('IDRAK_LAB_CLOUD_VERIFY')
    if mode not in ('write', 'read'):
        return
    base = 'https://idrak-connect-lab.vercel.app'
    auth = 'Basic ' + base64.b64encode((os.environ.get('IDRAK_LAB_ACCESS_USER', 'lab') + ':' + os.environ['IDRAK_LAB_ACCESS_PASSWORD']).encode()).decode()

    def request(path, body=None, authenticated=True):
        headers = {'Authorization': auth} if authenticated else {}
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            headers['Content-Type'] = 'application/json'
        with urlopen(Request(base + path, data=data, headers=headers), timeout=30) as response:
            value = response.read()
            return json.loads(value) if 'json' in response.headers.get('Content-Type', '') else value

    for path in ('/health', '/pos', '/shop', '/simulator/'):
        request(path)
    try:
        request('/api/products', authenticated=False)
        raise AssertionError('Unauthenticated data access was accepted')
    except HTTPError as exc:
        assert exc.code == 401
    if mode == 'write':
        assert request('/simulator/api/summary')['invoices'] == 0, 'Use an empty independent Lab'
        request('/api/pos/sales', {'items': [{'sku': 'BRG-001', 'quantity': 2}], 'payment_method': 'cash'})
        web = request('/api/web/orders', {'items': [{'sku': 'FRY-001', 'quantity': 1}], 'payment_method': 'cash_on_delivery', 'customer': 'Synthetic Lab Test'})
        assert request('/simulator/api/summary')['revenue'] == '8.500'
        request('/api/orders/' + web['order_id'] + '/status', {'status': 'completed'})
        assert request('/simulator/api/summary')['revenue'] == '10.250'
        request('/api/orders/' + web['order_id'] + '/status', {'status': 'refunded'})
    summary = request('/simulator/api/summary')
    assert summary['invoices'] == 2 and summary['revenue'] == '8.500'
    products = request('/api/products')['products']
    assert next(p for p in products if p['sku'] == 'BRG-001')['stock'] == 58
    assert next(p for p in products if p['sku'] == 'FRY-001')['stock'] == 90
    print('CLOUD_HTTP_VERIFY_PASS: ' + mode + ' POS/store/refund/inventory/authentication/persistence', flush=True)


if __name__ == '__main__':
    main()

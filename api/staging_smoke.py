"""Opt-in cloud integration check. Refuses to run outside synthetic staging."""
import json
import os
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def main():
    if os.environ.get('IDRAK_STAGE_VERIFY') != '1':
        return
    assert os.environ.get('IDRAK_ENVIRONMENT') == 'staging'
    assert os.environ.get('IDRAK_LAB_BASE_URL') == 'https://idrak-connect-lab.vercel.app'
    import jwt
    base = 'https://idrak-connect-staging-api.vercel.app'
    token = jwt.encode({'sub': os.environ['IDRAK_STAGE_TEST_USER'], 'email': 'synthetic@example.test',
                        'aud': 'authenticated', 'exp': int(time.time()) + 600},
                       os.environ['SUPABASE_JWT_SECRET'], algorithm='HS256')

    def request(path, method='GET', body=None, org=None, expected=200):
        headers = {'Authorization': 'Bearer ' + token, 'X-Org-Id': org or os.environ['IDRAK_STAGE_TEST_ORG']}
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            headers['Content-Type'] = 'application/json'
        try:
            with urlopen(Request(base + path, data=data, headers=headers, method=method), timeout=60) as response:
                assert response.status == expected
                return json.load(response)
        except HTTPError as exc:
            if exc.code != expected:
                raise AssertionError('Staging request failed: ' + path + ' status=' + str(exc.code)) from None

    assert len(request('/integrations/providers')) == 6
    connections = request('/integrations/connections')
    for provider in ('lab_pos', 'lab_web'):
        existing = next((c for c in connections if c['provider_code'] == provider), None)
        if existing:
            cid = existing['id']
        else:
            result = request('/integrations/connections', 'POST', {'provider_code': provider})
            assert result['sync']['failed'] == 0
            cid = result['connection']['id']
        result = request('/integrations/connections/' + cid + '/sync', 'POST')
        assert result['sync']['failed'] == 0
        detail = request('/integrations/connections/' + cid)
        assert detail['sales_count'] == 1
        assert request('/integrations/connections/' + cid + '/test', 'POST')['ok']
        other = os.environ['IDRAK_STAGE_OTHER_ORG']
        assert request('/integrations/connections', org=other) == []
        request('/integrations/connections/' + cid, org=other, expected=404)
    print('CLOUD_STAGING_CONNECT_PASS: protected Lab feeds, POS/store sync, duplicate prevention, connection health and tenant isolation', flush=True)


if __name__ == '__main__':
    main()

"""Single-origin serverless simulator using only a dedicated PostgreSQL database."""
import base64
import hmac
import json
import logging
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
import psycopg

import demo_server as lab
from hosted_server import deliver_to_simulator, validate_settings
import postgres_backend

postgres_backend.install()
USER, PASSWORD = validate_settings()
lab.post_signed = deliver_to_simulator
app = FastAPI(title='IDRAK Connect Lab — isolated simulator', docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def authentication(request, call_next):
    if request.method == 'GET' and request.url.path == '/health':
        return await call_next(request)
    expected = 'Basic ' + base64.b64encode(f'{USER}:{PASSWORD}'.encode()).decode()
    if not hmac.compare_digest(request.headers.get('authorization', '').encode(), expected.encode()):
        return Response(status_code=401, headers={'WWW-Authenticate': 'Basic realm="IDRAK Connect Lab", charset="UTF-8"'})
    if request.method == 'POST':
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            return JSONResponse({'error': 'Cross-origin writes are not allowed'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def static_file(filename):
    assets = lab.ROOT / 'server_assets'
    if not assets.is_dir():
        assets = lab.ROOT / 'public'  # Local development before the Vercel build.
    text = (assets / filename).read_text(encoding='utf-8')
    if filename.endswith('.html'):
        text = text.replace('http://127.0.0.1:8766/', '/simulator/').replace('http://127.0.0.1:8765/', '/')
        text = text.replace('تجربة محلية', 'تجربة مستقلة').replace('وتعمل على جهازك فقط', 'ومعزولة عن مشروع إدراك الأصلي').replace('Local-only', 'Standalone demo')
        if filename == 'inbox.html':
            text = text.replace('href="/" class="active"', 'href="/simulator/" class="active"')
    mime = 'text/css' if filename.endswith('.css') else 'application/javascript' if filename.endswith('.js') else 'text/html'
    return Response(text, media_type=mime)


def dispatch_get(path, query):
    files = {'/': 'home.html', '/pos': 'pos.html', '/shop': 'shop.html', '/admin': 'admin.html',
             '/style.css': 'style.css', '/app.js': 'app.js', '/simulator': 'inbox.html', '/simulator/': 'inbox.html'}
    if path in files:
        return static_file(files[path])
    if path == '/health':
        with lab.connect(lab.SOURCE_DB) as db:
            db.execute('SELECT sku FROM products LIMIT 0')
        return JSONResponse({'ok': True, 'service': 'idrak-lab-postgres'})
    if path.startswith('/simulator/api/'):
        return JSONResponse(lab.receiver_get(path[len('/simulator'):]))
    if path.startswith('/api/'):
        return JSONResponse(lab.source_get(path, query))
    raise LookupError(path)


def dispatch_post(path, body):
    if path == '/api/pos/sales':
        return lab.create_order('pos', body)
    if path == '/api/web/orders':
        return lab.create_order('web', body)
    if path.startswith('/api/orders/') and path.endswith('/status'):
        return lab.change_order(path.split('/')[3], body.get('status'))
    if path == '/api/retry':
        lab.flush_events()
        return {'status': 'retried'}
    if path == '/api/redeliver':
        seq = body.get('seq')
        if type(seq) is not int:
            raise ValueError('seq must be integer')
        with lab.connect(lab.SOURCE_DB) as db:
            row = db.execute('SELECT payload FROM source_events WHERE seq=?', (seq,)).fetchone()
        if not row:
            raise ValueError('event not found')
        return {'receiver': deliver_to_simulator(f'http://127.0.0.1:{lab.RECEIVER_PORT}/ingest', json.loads(row['payload']))}
    raise LookupError(path)


@app.api_route('/{path:path}', methods=['GET', 'POST'])
async def dispatch(path: str, request: Request):
    try:
        if request.method == 'GET':
            return await run_in_threadpool(dispatch_get, '/' + path, parse_qs(request.url.query))
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 100_000:
                return JSONResponse({'error': 'Request too large'}, status_code=413)
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return JSONResponse(await run_in_threadpool(dispatch_post, '/' + path, value))
    except LookupError:
        return JSONResponse({'error': 'not found'}, status_code=404)
    except (ValueError, TypeError, KeyError) as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)
    except psycopg.Error as exc:
        logging.getLogger(__name__).error('Lab database request failed: sqlstate=%s', exc.sqlstate)
        return JSONResponse({'error': 'Simulator database unavailable'}, status_code=503)

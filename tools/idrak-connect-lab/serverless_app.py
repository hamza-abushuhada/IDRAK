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
import browser_auth

postgres_backend.install()
USER, PASSWORD = validate_settings()
lab.post_signed = deliver_to_simulator
app = FastAPI(title='IDRAK Connect Lab — isolated simulator', docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def authentication(request, call_next):
    path = request.url.path
    public = path in ('/login', '/login.js', '/activate', '/activate.js', '/style.css', '/service/pairing/exchange') + browser_auth.PUBLIC_AUTH_PATHS
    expected = 'Basic ' + base64.b64encode(f'{USER}:{PASSWORD}'.encode()).decode()
    principal = await run_in_threadpool(
        lab.authenticate, request.headers.get('authorization', ''), request.url.path, request.method, expected)
    cookie_principal = await run_in_threadpool(browser_auth.authenticate, request.cookies and request.headers.get('cookie'))
    # A browser shop session takes precedence over cached operator Basic auth.
    if browser_auth.COOKIE in request.cookies:
        principal = cookie_principal
    if principal is None and public:
        principal = lab.Principal('anonymous')
    if principal is None and not request.headers.get('authorization') and request.method == 'GET' and path in ('/', '/pos', '/shop', '/admin', '/simulator', '/simulator/'):
        return Response(status_code=303, headers={'Location': '/login', 'Cache-Control': 'no-store'})
    if principal is None:
        headers = {'Cache-Control': 'no-store'}
        if browser_auth.COOKIE not in request.cookies:
            headers['WWW-Authenticate'] = 'Basic realm="IDRAK Connect Lab", charset="UTF-8"'
        return Response(status_code=401, headers=headers)
    request.state.principal = principal
    if request.method == 'GET' and not lab.page_allowed(principal, path):
        return Response(status_code=303, headers={'Location': '/pos', 'Cache-Control': 'no-store'})
    if request.method == 'POST':
        if not browser_auth.same_origin(request.headers, str(request.base_url), cookie_auth=cookie_principal is not None or path in browser_auth.PUBLIC_AUTH_PATHS):
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


def dispatch_get(principal, x_shop, path, query):
    files = {'/login': 'login.html', '/login.js': 'login.js', '/activate': 'activate.html', '/activate.js': 'activate.js', '/operator': 'home.html', '/': 'home.html', '/pos': 'pos.html', '/shop': 'shop.html', '/admin': 'admin.html',
             '/style.css': 'style.css', '/app.js': 'app.js', '/simulator': 'inbox.html', '/simulator/': 'inbox.html'}
    if path in files:
        return static_file(files[path])
    if path == '/auth/session':
        return JSONResponse(browser_auth.session_info(principal, x_shop))
    if path == '/health':
        with lab.connect(lab.SOURCE_DB) as db:
            db.execute('SELECT sku FROM products LIMIT 0')
        return JSONResponse({'ok': True, 'service': 'idrak-lab-postgres'})
    if path.startswith('/simulator/api/'):
        return JSONResponse(lab.handle_receiver_get(principal, x_shop, path[len('/simulator'):]))
    if path.startswith('/api/'):
        return JSONResponse(lab.handle_source_get(principal, x_shop, path, query))
    raise LookupError(path)


@app.api_route('/{path:path}', methods=['GET', 'POST'])
async def dispatch(path: str, request: Request):
    try:
        if request.method == 'GET':
            return await run_in_threadpool(dispatch_get, request.state.principal, request.headers.get('x-lab-shop'),
                                           '/' + path, parse_qs(request.url.query))
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 100_000:
                return JSONResponse({'error': 'Request too large'}, status_code=413)
        if path == 'service/pairing/exchange':
            import pairing
            return JSONResponse(await run_in_threadpool(pairing.exchange, bytes(body), request.headers.get('authorization', '')))
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        if path.startswith('auth/'):
            client = request.headers.get('x-real-ip') or (request.headers.get('x-forwarded-for') or '').split(',')[0].strip()                 or (request.client.host if request.client else '')
            status, payload, cookie = await run_in_threadpool(
                browser_auth.handle_auth_post, '/' + path, value, request.state.principal if path in ('auth/logout', 'auth/switch-shop') else None, client)
            response = JSONResponse(payload, status_code=status)
            if cookie is not None:
                response.headers['Set-Cookie'] = browser_auth.cookie_header(cookie, request.url.scheme == 'https' or request.url.hostname not in ('localhost', '127.0.0.1', '::1'))
            return response
        return JSONResponse(await run_in_threadpool(
            lab.handle_source_post, request.state.principal, request.headers.get('x-lab-shop'), '/' + path, value))
    except lab.LabAuthError as exc:
        return JSONResponse({'error': str(exc)}, status_code=exc.status)
    except LookupError:
        return JSONResponse({'error': 'not found'}, status_code=404)
    except (ValueError, TypeError, KeyError) as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)
    except psycopg.Error as exc:
        logging.getLogger(__name__).error('Lab database request failed: sqlstate=%s', exc.sqlstate)
        return JSONResponse({'error': 'Simulator database unavailable'}, status_code=503)

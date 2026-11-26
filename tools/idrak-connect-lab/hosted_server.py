"""Single-port, password-protected standalone Lab. No IDRAK credentials required.

Run behind an HTTPS reverse proxy with a persistent data volume. The original
two-port localhost runner remains available in demo_server.py.
"""
from __future__ import annotations

import base64
import hmac
import json
import os
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

import demo_server as lab


def validate_settings():
    password = os.environ.get('IDRAK_LAB_ACCESS_PASSWORD', '')
    secret = os.environ.get('IDRAK_LAB_WEBHOOK_SECRET', '')
    if len(password) < 20:
        raise ValueError('Set IDRAK_LAB_ACCESS_PASSWORD to a separate random value of at least 20 characters')
    if len(secret) < 32:
        raise ValueError('Set IDRAK_LAB_WEBHOOK_SECRET to a separate random value of at least 32 characters')
    if secret == 'idrak-local-demo-only-secret' or secret == password:
        raise ValueError('Use distinct, non-default access and signing secrets')
    return os.environ.get('IDRAK_LAB_ACCESS_USER', 'lab'), password


def deliver_to_simulator(url, payload):
    # Hosted Lab is self-contained: never forward to the production IDRAK API.
    if url != f'http://127.0.0.1:{lab.RECEIVER_PORT}/ingest':
        raise ValueError('Only the standalone simulator is a valid destination')
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    status, _ = lab.ingest_event(raw, lab.sign(raw, payload['source']['account_id']))
    return status


class HostedHandler(lab.SourceHandler):
    def parse_request(self):
        if not super().parse_request():
            return False
        path = urlparse(self.path).path
        expected = 'Basic ' + base64.b64encode(f'{self.server.access_user}:{self.server.access_password}'.encode()).decode()
        self.principal = lab.authenticate(self.headers.get('Authorization', ''), path, self.command, expected)
        if self.principal is not None:
            return True
        # Drain only a bounded body before closing. Unread POST bytes can reset
        # the connection and hide the 401 response from clients on Windows.
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if 0 < size <= 100_000:
                self.connection.settimeout(2)
                self.rfile.read(size)
        except (ValueError, OSError):
            pass
        self.close_connection = True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="IDRAK Connect Lab", charset="UTF-8"')
        self.send_header('Content-Length', '0')
        self.send_header('Connection', 'close')
        self.end_headers()
        return False

    def serve_file(self, filename):
        # The localhost runner keeps its two origins. Hosted mode uses one origin.
        file = lab.ROOT / 'public' / filename
        if not file.is_file():
            return self.send_json(404, {'error': 'not found'})
        text = file.read_text(encoding='utf-8')
        if filename.endswith('.html'):
            text = text.replace('http://127.0.0.1:8766/', '/simulator/')
            text = text.replace('http://127.0.0.1:8765/', '/')
            text = text.replace('تجربة محلية', 'تجربة مستقلة')
            text = text.replace('وتعمل على جهازك فقط', 'ومعزولة عن مشروع إدراك الأصلي')
            text = text.replace('Local-only', 'Standalone demo')
            if filename == 'inbox.html':
                text = text.replace('href="/" class="active"', 'href="/simulator/" class="active"')
        raw = text.encode('utf-8')
        mime = 'text/css' if filename.endswith('.css') else ('application/javascript' if filename.endswith('.js') else 'text/html')
        self.send_response(200)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def _receiver(self, method):
        path = urlparse(self.path).path
        if path == '/simulator' or path.startswith('/simulator/'):
            self.path = self.path[len('/simulator'):] or '/'
            getattr(lab.ReceiverHandler, method)(self)
            return True
        return False

    def do_GET(self):
        if not self._receiver('do_GET'):
            super().do_GET()

    def do_POST(self):
        if not self._receiver('do_POST'):
            super().do_POST()


def start():
    user, password = validate_settings()
    lab.init_db()
    lab.post_signed = deliver_to_simulator
    lab.flush_events()
    server = ThreadingHTTPServer((os.environ.get('HOST', '0.0.0.0'), int(os.environ.get('PORT', '8765'))), HostedHandler)
    server.access_user, server.access_password = user, password
    print('Standalone IDRAK Connect Lab ready; simulator at /simulator/.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    start()

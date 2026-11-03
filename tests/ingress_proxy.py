"""Test-only proxy emulating Supervisor's stripped prefix and headers."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PREFIX = '/api/hassio_ingress/test_token'


class Proxy(BaseHTTPRequestHandler):
    def proxy(self):
        if not self.path.startswith(PREFIX + '/'):
            self.send_error(404, 'Request escaped Ingress prefix')
            return
        headers = dict(self.headers)
        headers['X-Ingress-Path'] = PREFIX
        headers['X-Forwarded-Proto'] = 'http'
        headers.pop('Accept-Encoding', None)
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        connection = http.client.HTTPConnection('172.30.32.3', 8086, timeout=30)
        try:
            connection.request(self.command, self.path[len(PREFIX):], body, headers)
            result = connection.getresponse()
            data = result.read()
            self.send_response(result.status)
            for key, value in result.getheaders():
                if key.lower() not in ('transfer-encoding', 'connection', 'content-length'):
                    self.send_header(key, value)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            connection.close()

    do_GET = proxy
    do_POST = proxy
    do_PATCH = proxy
    do_DELETE = proxy


ThreadingHTTPServer(('0.0.0.0', 8086), Proxy).serve_forever()

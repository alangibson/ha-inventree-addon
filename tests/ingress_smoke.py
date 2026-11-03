"""Isolated Ingress test; requires Docker and unused subnet 172.30.32.0/24."""
import base64
import http.cookiejar
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from smoke import docker


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else 'ha-inventree-addon'
    name = 'ha-ingress-test-' + uuid.uuid4().hex[:8]
    proxy = name + '-proxy'
    prefix = '/api/hassio_ingress/test_token'
    created_network = False
    try:
        docker('network', 'create', '--subnet', '172.30.32.0/24', name)
        created_network = True
        docker('run', '-d', '--init', '--name', name, '--network', name,
               '--ip', '172.30.32.3', '-p', '127.0.0.1::8086', image)
        source = Path(__file__).with_name('ingress_proxy.py').resolve()
        docker('run', '-d', '--name', proxy, '--network', name, '--ip', '172.30.32.2',
               '-p', '127.0.0.1::8086', '-v', f'{source}:/tmp/proxy.py:ro',
               '--entrypoint', 'python3', image, '/tmp/proxy.py')
        base = 'http://127.0.0.1:' + docker('port', proxy, '8086/tcp').rsplit(':', 1)[1]
        direct = 'http://127.0.0.1:' + docker('port', name, '8086/tcp').rsplit(':', 1)[1]
        jar = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

        def request(path, payload=None, origin=None, base_url=None, headers=None, method=None):
            headers = dict(headers or {})
            if payload is not None:
                headers.update({'Content-Type': 'application/json', 'Origin': origin or base})
                headers['X-CSRFToken'] = next(c.value for c in jar if c.name == 'csrftoken')
            req = urllib.request.Request((base_url or base + prefix) + path,
                headers=headers, method=method, data=json.dumps(payload).encode() if payload is not None else None)
            try:
                with client.open(req, timeout=30) as response:
                    return response.status, response.read(), response.headers
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read(), exc.headers

        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            try:
                if request('/api/')[0] == 200:
                    break
            except OSError:
                pass
            if docker('inspect', '-f', '{{.State.Running}}', name) != 'true':
                raise AssertionError('App exited before becoming ready')
            time.sleep(2)
        else:
            raise AssertionError('App did not become ready')
        status, html, headers = request('/web/')
        assert status == 200, (status, html[:300])
        assert headers['X-Frame-Options'] == 'SAMEORIGIN'
        text = html.decode()
        settings = json.loads(re.search(r'window.INVENTREE_SETTINGS=(\{.*?\})</script>', text)[1])
        assert settings['api_host'] == base + prefix + '/'
        assert settings['base_url'] == prefix.lstrip('/') + '/web'
        assets = re.findall(r'(?:src|href)="(' + prefix + r'/static/[^"]+)"', text)
        assert assets, 'No prefixed assets found'
        for asset in assets:
            if '/static/plugins/' in asset:
                continue  # Plugin assets are outside this core Ingress test.
            assert request(asset, base_url=base)[0] == 200, asset
        assert all(cookie.path.startswith(prefix) for cookie in jar)
        status, data, _ = request('/api/auth/v1/auth/login', {'username': 'admin', 'password': 'password'})
        assert status == 200, (status, data)
        assert request('/api/part/')[0] == 200, 'Session authentication failed'
        # Related-model selectors use api_url from OPTIONS metadata, rather
        # than hardcoded endpoints. Axios must not prepend api_host again.
        basic = 'Basic ' + base64.b64encode(b'admin:password').decode()
        status, data, _ = request('/api/user/me/token/', headers={'Authorization': basic})
        assert status == 200, (status, data)
        auth = {'Authorization': 'Token ' + json.loads(data)['token']}
        status, data, _ = request('/api/company/part/', method='OPTIONS', headers=auth)
        assert status == 200, (status, data)
        supplier_url = json.loads(data)['actions']['POST']['supplier']['api_url']
        assert supplier_url == base + prefix + '/api/company/', supplier_url
        query_url = supplier_url + '?is_supplier=true&search=&offset=0&limit=10'
        with client.open(urllib.request.Request(query_url, headers=auth), timeout=30) as response:
            assert response.status == 200, 'Supplier selector request failed'
        print('PASS: supplier metadata URL has one prefix and supplier lookup succeeds', flush=True)
        assert request('/api/auth/v1/auth/login', {'username': 'admin', 'password': 'password'}, origin='http://other.example')[0] == 403
        status, html, _ = request('/web/', base_url=direct, headers={
            'X-Ingress-Path': prefix, 'X-HA-Ingress-Path': prefix,
            'X-HA-Ingress-Proto': 'https'})
        assert status == 200 and prefix.encode() not in html, 'Direct client spoofed Ingress headers'
        print('PASS: prefixed frontend/assets, session login/API, cookies, CSRF, framing, direct access and spoofed-header rejection', flush=True)
        if '--keep' in sys.argv:
            print('Browser test URL: ' + base + prefix + '/web/', flush=True)
            input('Press Enter to clean up test containers: ')
    except Exception:
        subprocess.run(['docker', 'logs', '--tail', '50', name], check=False)
        raise
    finally:
        for container in (proxy, name):
            subprocess.run(['docker', 'rm', '-fv', container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if created_network:
            docker('network', 'rm', name)


if __name__ == '__main__':
    main()

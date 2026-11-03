"""End-to-end Docker test; only touches its own container and temporary volume."""
import base64
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

import yaml


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else 'ha-inventree:test'
    name = 'ha-inventree-smoke-' + uuid.uuid4().hex[:10]
    volume = name + '-config'
    root = Path(__file__).resolve().parents[1]
    options = yaml.safe_load((root / 'ha-inventree-addon/config.yaml').read_text())['options']
    standalone = '--standalone' in sys.argv[2:]
    password = 'password' if standalone else secrets.token_urlsafe(24)
    options.update(admin_email='test@example.org', admin_password=password)
    auth = 'Basic ' + base64.b64encode(f'admin:{password}'.encode()).decode()
    docker('volume', 'create', volume)
    try:
        with tempfile.TemporaryDirectory(prefix=name) as temporary:
            path = Path(temporary) / 'options.json'
            path.write_text(json.dumps(options))
            mounts = [] if standalone else ['-v', f'{path}:/data/options.json:ro']
            docker('run', '-d', '--init', '--name', name, '-p', '127.0.0.1::8086',
                   '-v', f'{volume}:/data/ha-inventree-addon', *mounts, image)
            port = docker('port', name, '8086/tcp').rsplit(':', 1)[1]
            base = f'http://localhost:{port}'

            def request(path, authenticated=False, payload=None):
                headers = {'Authorization': auth} if authenticated else {}
                data = None
                if payload is not None:
                    headers['Content-Type'] = 'application/json'
                    data = json.dumps(payload).encode()
                try:
                    with urllib.request.urlopen(urllib.request.Request(
                        base + path, headers=headers, data=data,
                        method='PATCH' if payload is not None else 'GET',
                    ), timeout=30) as response:
                        return response.status, response.read()
                except urllib.error.HTTPError as exc:
                    return exc.code, exc.read()

            def ready():
                nonlocal base
                # Docker may assign a different ephemeral host port on restart.
                port = docker('port', name, '8086/tcp').rsplit(':', 1)[1]
                base = f'http://localhost:{port}'
                deadline = time.monotonic() + 300
                while time.monotonic() < deadline:
                    if docker('inspect', '-f', '{{.State.Running}}', name) != 'true':
                        raise AssertionError('Container exited during initialization')
                    try:
                        if request('/api/')[0] == 200:
                            return
                    except (OSError, urllib.error.URLError):
                        pass
                    time.sleep(2)
                raise AssertionError('Server did not become ready')

            ready()
            assert request('/web/')[0] == 200, 'Frontend did not load'
            for host in ('homeassistant.local:8086', '192.168.50.12:8086', 'inventory.example:9090'):
                with urllib.request.urlopen(urllib.request.Request(
                    base + '/web/', headers={'Host': host}), timeout=30) as response:
                    assert response.status == 200, f'Frontend rejected {host}'
            # Exercise the actual Django CSRF middleware with the add-on settings.
            csrf_check = """
import os, sys
sys.path.insert(0, '/opt/ha-inventree')
import run
os.environ.update(run.environment())
os.chdir(os.environ['INVENTREE_BACKEND_DIR'] + '/InvenTree')
sys.path.insert(0, os.getcwd())
import django
django.setup()
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory
from django.middleware.csrf import CsrfViewMiddleware, get_token
assert 'django.middleware.csrf.CsrfViewMiddleware' in settings.MIDDLEWARE
assert 'InvenTree.middleware.InvenTreeHostSettingsMiddleware' not in settings.MIDDLEWARE
factory = RequestFactory()
for origin, accepted in [('http://inventory.example:9090', True), ('http://other.example', False)]:
    request = factory.post('/test/', HTTP_HOST='inventory.example:9090', HTTP_ORIGIN=origin)
    token = get_token(request)
    request.COOKIES[settings.CSRF_COOKIE_NAME] = request.META['CSRF_COOKIE']
    request.META['HTTP_X_CSRFTOKEN'] = token
    middleware = CsrfViewMiddleware(lambda request: HttpResponse())
    middleware.process_request(request)
    response = middleware.process_view(request, lambda request: HttpResponse(), (), {})
    assert (response is None) == accepted, (origin, response)
print('PASS: same-origin CSRF accepted; cross-origin CSRF rejected')
"""
            print(docker('exec', name, 'python3', '-c', csrf_check))
            assert request('/static/web/index.html')[0] == 200, 'Static assets missing'
            assert request('/api/part/', True)[0] == 200, 'Administrator login failed'
            token_status, token_data = request('/api/user/me/token/', True)
            assert token_status == 200, 'Token login failed'
            auth = 'Token ' + json.loads(token_data)['token']
            plugins = request('/api/plugins/', True)
            assert plugins[0] == 200 and b'supplierscout' in plugins[1].lower(), 'Plugin not discovered'
            assert request('/api/plugins/supplierscout/activate/', True, {'active': True})[0] == 200, 'Plugin activation failed'
            assert b'kicad-library-plugin' in plugins[1], 'KiCad plugin not discovered'
            assert b'smartparts' in plugins[1], 'Smart Parts plugin not discovered'
            for setting in ('ENABLE_PLUGINS_URL', 'ENABLE_PLUGINS_APP', 'ENABLE_PLUGINS_NAVIGATION', 'ENABLE_PLUGINS_INTERFACE', 'ENABLE_PLUGINS_EVENTS'):
                assert request(f'/api/settings/global/{setting}/', True, {'value': True})[0] == 200, f'{setting} failed'
            assert request('/api/plugins/kicad-library-plugin/activate/', True, {'active': True})[0] == 200, 'KiCad activation failed'
            assert request('/api/plugins/smartparts/activate/', True, {'active': True})[0] == 200, 'Smart Parts activation failed'
            docker('exec', name, 'sh', '-c', 'printf smoke-marker > /data/ha-inventree-addon/media/smoke.txt')
            assert request('/media/smoke.txt')[0] in (401, 403), 'Media is public'
            assert request('/media/smoke.txt', True) == (200, b'smoke-marker'), 'Authenticated media failed'
            key = docker('exec', name, 'cat', '/data/ha-inventree-addon/secret_key.txt')
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            docker('stop', '-t', '120', name)
            assert docker('inspect', '-f', '{{.State.ExitCode}}', name) == '0', 'Ungraceful shutdown'
            docker('start', name)
            ready()
            assert request('/api/part/', True)[0] == 200, 'User did not persist'
            plugin_status, plugin_data = request('/api/plugins/supplierscout/', True)
            assert plugin_status == 200 and json.loads(plugin_data)['active'], 'Plugin activation did not persist'
            assert request('/static/plugins/supplierscout/Panel.js')[0] == 200, 'Plugin frontend missing'
            kicad_status, kicad_data = request('/api/plugins/kicad-library-plugin/', True)
            assert kicad_status == 200 and json.loads(kicad_data)['active'], 'KiCad activation did not persist'
            category_status, category_data = request('/plugin/kicad-library-plugin/api/category/', True)
            assert category_status == 200 and json.loads(category_data) == [], 'KiCad API or database migrations failed'
            smart_status, smart_data = request('/api/plugins/smartparts/', True)
            assert smart_status == 200 and json.loads(smart_data)['active'], 'Smart Parts activation did not persist'
            assert request('/plugin/smartparts/', True)[0] == 200, 'Smart Parts dashboard failed'
            assert request('/static/plugins/smartparts/inventree_smart_parts/ui/purescan.js')[0] == 200, 'Smart Parts frontend missing'
            log_target = docker('exec', name, 'python3', '-c', "import importlib.util; from pathlib import Path; print((Path(importlib.util.find_spec('inventree_smart_parts').origin).parent / 'smart_parts_activity.jsonl').resolve())")
            assert log_target == '/data/ha-inventree-addon/smart_parts_activity.jsonl', 'Smart Parts log is not persistent'
            assert request('/media/smoke.txt', True) == (200, b'smoke-marker'), 'Media did not persist'
            assert hashlib.sha256(docker('exec', name, 'cat', '/data/ha-inventree-addon/secret_key.txt').encode()).hexdigest() == key_hash
            docker('stop', '-t', '120', name)
            assert docker('inspect', '-f', '{{.State.ExitCode}}', name) == '0'
            logs = subprocess.check_output(['docker', 'logs', name], stderr=subprocess.STDOUT, text=True)
            assert 'INVE-W10' not in logs, 'Unexpected configuration directory warning'
            print('PASS: startup, login, frontend, plugin discovery, media authorization, persistence and shutdown')
    except Exception:
        subprocess.run(['docker', 'logs', '--tail', '100', name], check=False)
        raise
    finally:
        subprocess.run(['docker', 'rm', '-f', name], check=False, stdout=subprocess.DEVNULL)
        docker('volume', 'rm', volume)


if __name__ == '__main__':
    main()

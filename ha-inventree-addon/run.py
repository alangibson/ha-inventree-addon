"""Configure the official image and supervise its web, worker and proxy processes."""

import json
import os
from pathlib import Path
import signal
import secrets
import subprocess
import sys
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def load_options(path=Path('/data/options.json')):
    """Home Assistant supplies this file; standalone installations need not."""
    try:
        with path.open() as stream:
            options = json.load(stream)
    except FileNotFoundError:
        return {}
    if not isinstance(options, dict):
        raise ValueError('Home Assistant options must be a JSON object')
    return options


def environment(options=None, data=Path('/data/ha-inventree-addon')):
    """Validate options before starting migrations; never log credentials."""
    supplied = options or {}
    env = os.environ.copy()
    # Non-empty HA options take precedence over native environment variables.
    # The standalone defaults provide a working SQLite installation without
    # any configuration file. Upstream only creates a user if it is absent.
    defaults = {
        'timezone': ('INVENTREE_TIMEZONE', 'UTC'),
        'admin_user': ('INVENTREE_ADMIN_USER', 'admin'),
        'admin_email': ('INVENTREE_ADMIN_EMAIL', 'admin@example.com'),
        'admin_password': ('INVENTREE_ADMIN_PASSWORD', 'password'),
        'database_engine': ('INVENTREE_DB_ENGINE', 'sqlite3'),
        'database_name': ('INVENTREE_DB_NAME', 'inventree'),
        'database_host': ('INVENTREE_DB_HOST', ''),
        'database_port': ('INVENTREE_DB_PORT', '5432'),
        'database_user': ('INVENTREE_DB_USER', ''),
        'database_password': ('INVENTREE_DB_PASSWORD', ''),
    }
    options = {key: supplied.get(key) or env.get(variable) or default
               for key, (variable, default) in defaults.items()}
    try:
        ZoneInfo(options['timezone'])
    except ZoneInfoNotFoundError:
        raise ValueError('timezone must be a valid IANA timezone') from None
    env.update({
        'INVENTREE_DATA_DIR': str(data),
        'INVENTREE_SITE_URL': '',
        'INVENTREE_ALLOWED_HOSTS': '*',
        'DJANGO_SETTINGS_MODULE': 'addon_settings',
        'PYTHONPATH': '/opt/ha-inventree' + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else ''),
        'INVENTREE_TIMEZONE': options['timezone'],
        'INVENTREE_ADMIN_USER': options['admin_user'],
        'INVENTREE_ADMIN_EMAIL': options['admin_email'],
        'INVENTREE_ADMIN_PASSWORD': options['admin_password'],
    })
    for key, value in {
        'INVENTREE_DEBUG': 'False', 'INVENTREE_AUTO_UPDATE': 'False',
        'INVENTREE_PLUGINS_ENABLED': 'True', 'INVENTREE_GUNICORN_WORKERS': '1',
        'INVENTREE_BACKGROUND_WORKERS': '1', 'INVENTREE_USE_X_FORWARDED_PROTO': 'False',
    }.items():
        env.setdefault(key, value)
    for key, path in {
        'STATIC_ROOT': 'static', 'MEDIA_ROOT': 'media', 'BACKUP_DIR': 'backup',
        'PLUGIN_DIR': 'plugins', 'CONFIG_FILE': 'config.yaml',
        'SECRET_KEY_FILE': 'secret_key.txt', 'OIDC_PRIVATE_KEY_FILE': 'oidc.pem',
        'PLUGIN_FILE': 'plugins.txt',
    }.items():
        env['INVENTREE_' + key] = str(data / path)
    engine = options['database_engine'].removeprefix('django.db.backends.')
    if engine == 'sqlite':
        engine = 'sqlite3'
    if engine not in ('sqlite3', 'postgresql'):
        raise ValueError('Unsupported database_engine')
    env['INVENTREE_DB_ENGINE'] = engine
    if engine == 'sqlite3':
        # HA's database_name option describes PostgreSQL, not a SQLite path.
        env['INVENTREE_DB_NAME'] = env.get('INVENTREE_DB_NAME') or str(data / 'inventree.sqlite3')
    else:
        for key in ('host', 'name', 'user', 'password'):
            if not options.get('database_' + key):
                raise ValueError('PostgreSQL requires database_' + key)
        for key in ('host', 'port', 'name', 'user', 'password'):
            env['INVENTREE_DB_' + key.upper()] = str(options['database_' + key])
    return env


class Services:
    def __init__(self, env):
        self.env = env
        self.children = []
        self.stopping = False

    def stop(self, *_):
        self.stopping = True
        for child in self.children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def start(self, command):
        if self.stopping:
            raise InterruptedError('Shutdown requested')
        child = subprocess.Popen(command, env=self.env, start_new_session=True)
        self.children.append(child)
        # Cover a stop signal arriving during Popen.
        if self.stopping:
            self.stop()
        return child

    def run(self, command):
        child = self.start(command)
        code = child.wait()
        self.children.remove(child)
        if code:
            raise RuntimeError('Initialization command failed; see preceding logs')

    def wait(self):
        while not self.stopping:
            for child in self.children:
                if child.poll() is not None:
                    raise RuntimeError('A required service exited; stopping the add-on')
            time.sleep(0.5)

    def close(self):
        self.stop()
        deadline = time.monotonic() + 90
        for child in self.children:
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


def main():
    env = environment(load_options())
    data = Path('/data/ha-inventree-addon')
    data.mkdir(parents=True, exist_ok=True)
    for folder in ('static', 'media', 'backup', 'plugins'):
        (data / folder).mkdir(exist_ok=True)
    # Use a minimal persistent config; add-on options override these defaults.
    config = data / 'config.yaml'
    if not config.exists():
        config.write_text('{}\n')
    secret = data / 'secret_key.txt'
    if not secret.exists():
        with open(secret, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
            stream.write(secrets.token_urlsafe(64))
    secret.chmod(0o600)
    services = Services(env)
    signal.signal(signal.SIGTERM, services.stop)
    signal.signal(signal.SIGINT, services.stop)
    try:
        # Use upstream tasks, but do not install packages or download frontend code
        # at startup. Both are already supplied by the pinned production image.
        print('[inventree] Preparing database and static files', flush=True)
        services.run(['/bin/bash', './init.sh', 'invoke', 'migrate', 'static', 'int.clean-settings'])
        for filename in ('oidc.pem', 'inventree.sqlite3'):
            if (data / filename).exists():
                (data / filename).chmod(0o600)
        services.run(['nginx', '-t'])
        services.start(['gunicorn', '-c', './gunicorn.conf.py', 'InvenTree.wsgi',
                        '-b', '127.0.0.1:8000', '--chdir',
                        env['INVENTREE_BACKEND_DIR'] + '/InvenTree'])
        services.start(['python3', env['INVENTREE_BACKEND_DIR'] + '/InvenTree/manage.py', 'qcluster'])
        services.start(['nginx', '-g', 'daemon off;'])
        print('[inventree] Web server, background worker and proxy started', flush=True)
        services.wait()
    except (RuntimeError, InterruptedError):
        if not services.stopping:
            raise
    finally:
        services.close()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, KeyError) as exc:
        print(f'[inventree] {exc}', file=sys.stderr, flush=True)
        sys.exit(1)

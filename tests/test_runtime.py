import importlib.util
import os
from pathlib import Path
import signal
import sys
import unittest
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('runtime', Path(__file__).parents[1] / 'ha-inventree-addon/run.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.options = dict(site_url='http://inventory.local:8086', timezone='UTC',
                            admin_user='admin', admin_email='admin@example.org',
                            admin_password='test-only', database_engine='sqlite3')

    def test_persistence_paths_override_image_defaults(self):
        env = runtime.environment(self.options)
        for key in ('DB_NAME', 'MEDIA_ROOT', 'STATIC_ROOT', 'SECRET_KEY_FILE',
                    'CONFIG_FILE', 'PLUGIN_DIR', 'OIDC_PRIVATE_KEY_FILE'):
            self.assertTrue(env['INVENTREE_' + key].startswith('/data/ha-inventree-addon/'), key)
        self.assertNotIn('*', env['INVENTREE_ALLOWED_HOSTS'])

    def test_bad_origin_and_timezone_rejected(self):
        for value in ('https://host/path', 'https://a:b@host', 'file:///etc/passwd',
                      'https://host?query=1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runtime.environment(dict(self.options, site_url=value))
        with self.assertRaises(ValueError):
            runtime.environment(dict(self.options, timezone='not/a-zone'))

    def test_missing_options_use_bootstrap_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            options = runtime.load_options(Path(folder) / 'missing.json')
        env = runtime.environment(options)
        self.assertEqual(env['INVENTREE_ADMIN_USER'], 'admin')
        self.assertEqual(env['INVENTREE_ADMIN_PASSWORD'], 'password')
        self.assertEqual(env['INVENTREE_DB_NAME'], '/data/ha-inventree-addon/inventree.sqlite3')

    def test_environment_overrides_defaults_and_ha_overrides_environment(self):
        with patch.dict(os.environ, {'INVENTREE_ADMIN_PASSWORD': 'custom',
                                   'INVENTREE_SITE_URL': 'https://parts.example.org',
                                   'INVENTREE_GUNICORN_WORKERS': '2'}):
            env = runtime.environment()
            self.assertEqual(env['INVENTREE_ADMIN_PASSWORD'], 'custom')
            self.assertEqual(env['INVENTREE_SITE_URL'], 'https://parts.example.org')
            self.assertEqual(env['INVENTREE_GUNICORN_WORKERS'], '2')
            self.assertEqual(runtime.environment(self.options)['INVENTREE_ADMIN_PASSWORD'], 'test-only')
            self.assertEqual(runtime.environment({'admin_password': ''})['INVENTREE_ADMIN_PASSWORD'], 'custom')

    def test_invalid_options_are_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'options.json'
            path.write_text('[]')
            with self.assertRaises(ValueError):
                runtime.load_options(path)

    def test_postgres_requires_complete_configuration(self):
        with self.assertRaises(ValueError):
            runtime.environment(dict(self.options, database_engine='postgresql'))
        env = runtime.environment(dict(self.options, database_engine='postgresql',
            database_host='db', database_port=5432, database_name='inventory',
            database_user='inventory', database_password='p$"\\word'))
        self.assertEqual(env['INVENTREE_DB_PASSWORD'], 'p$"\\word')
        self.assertEqual(env['INVENTREE_DB_PORT'], '5432')

    def test_service_failure_is_detected_and_other_children_stopped(self):
        services = runtime.Services(os.environ.copy())
        sleeper = services.start([sys.executable, '-c', 'import time; time.sleep(30)'])
        services.start([sys.executable, '-c', 'raise SystemExit(7)'])
        try:
            with self.assertRaises(RuntimeError):
                services.wait()
        finally:
            services.close()
        self.assertEqual(sleeper.returncode, -signal.SIGTERM)

    def test_shutdown_blocks_new_services(self):
        services = runtime.Services(os.environ.copy())
        services.stop()
        with self.assertRaises(InterruptedError):
            services.start([sys.executable, '-c', 'pass'])


if __name__ == '__main__':
    unittest.main()

"""Request-based hosting for installations without a canonical hostname."""

import os

# Upstream requires a nonempty list during import. Replace this bootstrap value
# below: Django itself supports an empty list with same-origin validation.
os.environ['INVENTREE_TRUSTED_ORIGINS'] = 'http://localhost'

from InvenTree.settings import *  # noqa: E402,F403

# Keep upstream authentication and Django's same-origin CSRF checks. Only the
# additional InvenTree check requiring a preconfigured public URL is removed.
SITE_URL = None
ALLOWED_HOSTS = ['*']
CSRF_TRUSTED_ORIGINS = []
USE_X_FORWARDED_HOST = False
MIDDLEWARE = ['ingress.IngressMiddleware'] + [  # noqa: F405
    middleware for middleware in MIDDLEWARE
    if middleware != 'InvenTree.middleware.InvenTreeHostSettingsMiddleware'
]

# Send PDF rendering diagnostics to the Home Assistant add-on log.
LOGGING['handlers']['weasyprint_console'] = {  # noqa: F405
    'class': 'logging.StreamHandler',
    'formatter': 'plain_console',
}
LOGGING['loggers']['weasyprint'] = {  # noqa: F405
    'handlers': ['weasyprint_console'],
    'level': 'DEBUG',
    'propagate': False,
}

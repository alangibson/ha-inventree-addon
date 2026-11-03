"""Adapt upstream responses to Home Assistant's per-installation Ingress path.

Only requests from the Supervisor can set X-HA-Ingress-Path through nginx.
Other clients' Ingress headers are discarded on the shared listener. No upstream or plugin files are edited.
"""

import json
import re

from django.http import HttpResponseBadRequest
from django.urls import get_script_prefix, set_script_prefix

PREFIX = re.compile(r'/api/hassio_ingress/[A-Za-z0-9_-]+')
ROOT_URL = re.compile(r'^/(?:api|auth|accounts|web|static|media|plugin|admin)(?:/|$)')
HTML_URL = re.compile(r'''(?P<attr>\b(?:href|src|action)\s*=\s*)(?P<quote>["'])(?P<url>/[^"']*)(?P=quote)''', re.IGNORECASE)
FRONTEND_SETTINGS = re.compile(r'(window\.INVENTREE_SETTINGS\s*=\s*)(\{.*?\})(\s*</script>)', re.DOTALL)


class IngressMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        prefix = request.META.get('HTTP_X_HA_INGRESS_PATH', '')
        if not prefix:
            return self.get_response(request)
        if not PREFIX.fullmatch(prefix):
            return HttpResponseBadRequest('Invalid Ingress path')

        previous_prefix = get_script_prefix()
        request.META['SCRIPT_NAME'] = prefix
        request.path = prefix + request.path_info
        # nginx accepts this scheme only from the Supervisor.
        scheme = request.META.get('HTTP_X_HA_INGRESS_PROTO', 'http')
        request.META['wsgi.url_scheme'] = 'https' if scheme == 'https' else 'http'
        set_script_prefix(prefix)
        try:
            response = self.get_response(request)
        finally:
            set_script_prefix(previous_prefix)

        origin = request.build_absolute_uri('/').rstrip('/')

        def routed_url(value):
            if value.startswith(origin + '/'):
                value = value[len(origin):]
            if value == prefix or value.startswith(prefix + '/'):
                return value
            if value.startswith('/') and not value.startswith('//'):
                return prefix + value
            return value

        if response.has_header('Location'):
            response['Location'] = routed_url(response['Location'])
        for cookie in response.cookies.values():
            cookie['path'] = routed_url(cookie['path'] or '/')
        # The HA iframe and Ingress share an origin. Direct access retains
        # upstream's framing policy.
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Cache-Control'] = 'no-store'

        if response.streaming or response.has_header('Content-Encoding'):
            return response
        content_type = response.get('Content-Type', '').split(';')[0]
        if content_type == 'text/html':
            html = response.content.decode(response.charset)
            html = HTML_URL.sub(lambda m: m['attr'] + m['quote'] + routed_url(m['url']) + m['quote'], html)

            def frontend(match):
                settings = json.loads(match[2])
                settings['base_url'] = prefix.lstrip('/') + '/web'
                settings['api_host'] = origin + prefix + '/'
                settings['server_list'] = {'server-current': {
                    'host': origin + prefix + '/', 'name': 'Home Assistant'}}
                settings['default_server'] = 'server-current'
                settings['show_server_selector'] = False
                # JSON is embedded in a script element.
                return match[1] + json.dumps(settings).replace('<', '\\u003c') + match[3]

            html = FRONTEND_SETTINGS.sub(frontend, html)
            response.content = html.encode(response.charset)
        elif content_type == 'application/json':
            def rewrite(value):
                if isinstance(value, dict):
                    return {key: rewrite(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [rewrite(item) for item in value]
                if isinstance(value, str):
                    path = value[len(origin):] if value.startswith(origin + '/') else value
                    if ROOT_URL.match(path):
                        return routed_url(value)
                return value
            response.content = json.dumps(rewrite(json.loads(response.content))).encode()
        else:
            return response
        response['Content-Length'] = str(len(response.content))
        for header in ('ETag', 'Content-MD5'):
            if response.has_header(header):
                del response[header]
        return response

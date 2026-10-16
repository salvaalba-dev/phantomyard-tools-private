"""Closed API dispatch for the opt-in scoped resource backend."""
import json
from urllib.parse import urlparse

AUTH_POST = {'/api/access-link', '/api/redeem', '/api/logout'}


def dispatch(handler, method):
    backend = getattr(handler.server, 'scoped_backend', None)
    parsed = urlparse(handler.path)
    if backend is None or not parsed.path.startswith('/api/'):
        return False
    # Preserve exact signed issuance, one-time redemption and cookie logout.
    if method == 'POST' and parsed.path in AUTH_POST:
        return False
    if not handler.allowed():
        handler.send(403, {'error': 'Reader origin rejected'})
        return True
    if parsed.query or parsed.fragment:
        handler.send(400, {'error': 'Query and fragment credentials are not accepted'})
        return True
    if method == 'GET' and parsed.path == '/api/access-info':
        handler.send(200, {'delegated': True, 'scoped': True})
        return True
    try:
        if method == 'GET' and parsed.path == '/api/state':
            handler.send(200, backend.state(handler.headers))
        elif method == 'GET' and parsed.path.startswith('/api/resource/'):
            resource = backend.detail(handler.headers, parsed.path.removeprefix('/api/resource/'))
            handler.send(200 if resource else 404, resource or {'error': 'Resource unavailable'})
        elif method == 'POST' and parsed.path in {'/api/search', '/api/sync'}:
            length = int(handler.headers.get('Content-Length', '0'))
            if (not 0 < length <= 8192
                    or handler.headers.get('Content-Type', '').split(';')[0] != 'application/json'):
                raise ValueError('Invalid scoped request')
            body = json.loads(handler.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Invalid scoped request')
            if parsed.path == '/api/search' and set(body) == {'query'}:
                handler.send(200, backend.search(handler.headers, body['query']))
            elif parsed.path == '/api/sync' and body == {}:
                handler.send(200, backend.state(handler.headers))
            else:
                raise ValueError('Invalid scoped request')
        else:
            # Do not fall through to unfiltered legacy metadata, KB, versions,
            # assistant jobs, setup/configuration or future API routes.
            handler.send(403, {'error': 'Operation unavailable in the scoped reader'})
    except KeyError:
        handler.send(404, {'error': 'Resource unavailable'})
    except (ValueError, TypeError, RecursionError):
        handler.send(401, {'error': 'Identified session or current scoped data required'})
    except OSError:
        handler.send(503, {'error': 'Scoped resources temporarily unavailable'})
    return True

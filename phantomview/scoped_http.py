"""Closed API dispatch for the opt-in scoped resource backend."""
import json
from urllib.parse import urlparse

AUTH_POST = {'/api/access-link', '/api/redeem', '/api/logout'}
ASSISTANT_JOBS = '/api/scoped-assistant/jobs'


def reject(handler, method, status, message):
    # Closing with an unread small POST can reset the connection on Windows
    # before the client receives its denial. Discard bounded bytes, never parse
    # them or wait indefinitely for a body on an unavailable operation.
    if method == 'POST':
        try:
            length = int(handler.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if 0 < length <= 8192:
            previous = handler.connection.gettimeout()
            try:
                handler.connection.settimeout(1)
                handler.rfile.read(length)
            except OSError:
                pass
            finally:
                handler.connection.settimeout(previous)
    handler.send(status, {'error': message})
    return True


def dispatch(handler, method):
    backend = getattr(handler.server, 'scoped_backend', None)
    parsed = urlparse(handler.path)
    if backend is None or not parsed.path.startswith('/api/'):
        return False
    # Preserve exact signed issuance, one-time redemption and cookie logout.
    if method == 'POST' and parsed.path in AUTH_POST:
        return False
    if not handler.allowed():
        return reject(handler, method, 403, 'Reader origin rejected')
    if parsed.query or parsed.fragment:
        return reject(handler, method, 400, 'Query and fragment credentials are not accepted')
    if method == 'GET' and parsed.path == '/api/access-info':
        handler.send(200, {'delegated': True, 'scoped': True})
        return True
    try:
        consultations = getattr(handler.server, 'scoped_consultations', None)
        if method == 'GET' and parsed.path == '/api/scoped-assistant/info' and consultations:
            recipient = backend.gate.identified_scope(handler.headers)[0]
            if backend.gate.audit is not consultations.assistant.audit:
                raise ValueError('The protected consultation audit changed')
            handler.send(200, {'available': recipient.persona in consultations.assistant.executors,
                               'persona': recipient.persona, 'scope_id': recipient.scope_id})
        elif method in {'GET', 'DELETE'} and parsed.path.startswith(ASSISTANT_JOBS + '/') and consultations:
            operation = consultations.get if method == 'GET' else consultations.cancel
            handler.send(*operation(handler.headers, parsed.path.removeprefix(ASSISTANT_JOBS + '/')))
        elif method == 'GET' and parsed.path == '/api/state':
            handler.send(200, backend.state(handler.headers))
        elif method == 'GET' and parsed.path == '/api/review' and getattr(handler.server, 'review_service', None):
            handler.send(200, handler.server.review_service.view(handler.headers))
        elif method == 'GET' and parsed.path.startswith('/api/resource/'):
            resource = backend.detail(handler.headers, parsed.path.removeprefix('/api/resource/'))
            handler.send(200 if resource else 404, resource or {'error': 'Resource unavailable'})
        elif method == 'POST' and parsed.path in {'/api/search', '/api/sync', '/api/review', ASSISTANT_JOBS}:
            if parsed.path == ASSISTANT_JOBS:
                if consultations is None:
                    return reject(handler, method, 403, 'Scoped consultations are not configured')
                backend.gate.identified_scope(handler.headers)
            if parsed.path == '/api/review' and not getattr(handler.server, 'review_service', None):
                return reject(handler, method, 403, 'Review is not configured')
            length = int(handler.headers.get('Content-Length', '0'))
            if (not 0 < length <= (65536 if parsed.path == '/api/review' else 8192)
                    or handler.headers.get('Content-Type', '').split(';')[0] != 'application/json'):
                raise ValueError('Invalid scoped request')
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('Duplicate request field')
                    result[key] = value
                return result
            body = json.loads(handler.rfile.read(length), object_pairs_hook=unique)
            if not isinstance(body, dict):
                raise ValueError('Invalid scoped request')
            if parsed.path == '/api/search' and set(body) == {'query'}:
                handler.send(200, backend.search(handler.headers, body['query']))
            elif parsed.path == '/api/sync' and body == {}:
                handler.send(200, backend.state(handler.headers))
            elif parsed.path == '/api/review':
                handler.send(202, handler.server.review_service.propose(handler.headers, body))
            elif parsed.path == ASSISTANT_JOBS:
                handler.send(*consultations.submit(handler.headers, body))
            else:
                raise ValueError('Invalid scoped request')
        else:
            # Do not fall through to unfiltered legacy metadata, KB, versions,
            # assistant jobs, setup/configuration or future API routes.
            reject(handler, method, 403, 'Operation unavailable in the scoped reader')
    except PermissionError:
        handler.send(403, {'error': 'Explicit review authority required'})
    except KeyError:
        handler.send(404, {'error': 'Resource unavailable'})
    except (ValueError, TypeError, RecursionError):
        handler.send(401, {'error': 'Identified session or current scoped data required'})
    except OSError:
        handler.send(503, {'error': 'Scoped resources temporarily unavailable'})
    return True

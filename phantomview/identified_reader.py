"""Compose the existing authority, reviewed projection, HTTP gate and daemon IPC."""
from http.server import ThreadingHTTPServer
import re
import threading

from authority_publication import PublishedAuthority
from identified_access import IdentifiedGate
from issuer_routes import validate_routes
from phantomview import Handler
from projection_review import PublishedProjection
from reader_handoff import ReaderHandoff
from scoped_backend import ScopedBackend
from scoped_http import reject
from session_audit import Ledger
from trusted_handoff import DaemonPeerPolicy


def signed_access():
    """Fail before binding if the existing signature verifier is unavailable."""
    try:
        from coincurve import PublicKeyXOnly
        from phantomblog import access
        if not callable(PublicKeyXOnly.verify):
            raise ImportError
        return access
    except ImportError:
        raise ValueError('Install the reviewed phantomblog[access] extra in the reader environment') from None


class RecipientGate(IdentifiedGate):
    """This assembled reader never creates an unidentified fallback session."""
    def redeem(self, code):
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', code):
            raise ValueError('An identified recipient link is required')
        with self.recipient_lock:
            if self.digest(code) not in self.recipient_links:
                raise ValueError('An identified recipient link is required')
            return super().redeem(code)


class RecipientHandler(Handler):
    def do_POST(self):
        # Only the protected native handoff may attach verified recipient context.
        # Browser issuance cannot supply it, even with a valid bot signature.
        from urllib.parse import urlparse
        if urlparse(self.path).path == '/api/access-link':
            reject(self, 'POST', 403, 'Request an identified link through the issuing persona')
            return
        super().do_POST()


class MultiIssuerGate(RecipientGate):
    """One session store, with disjoint unchanged protocol verifiers per issuer."""
    def __init__(self, *args, routes, **kwargs):
        if not isinstance(routes, list) or not 2 <= len(routes) <= 16:
            raise ValueError('Multiple protected issuer routes are required')
        routes = validate_routes(routes[0], routes[1:])
        super().__init__(*args, **kwargs)
        primary = routes[0]
        if primary['actor'] != self.policy['actor'] or primary['identities'] != self.policy['identities']:
            raise ValueError('Primary issuer route must match the reader policy')
        self.verifiers = {primary['actor']: self.links}
        for route in routes[1:]:
            self.verifiers[route['actor']] = self.access.AccessLinks(route['identities'])

    def issuer_links(self, persona):
        if not isinstance(persona, str) or persona not in self.verifiers:
            raise ValueError('No protected route for this issuer')
        return self.verifiers[persona]

    def redeem_link(self, code, create):
        bound = self.recipient_links.get(self.digest(code))
        if bound is None:
            raise ValueError('An identified recipient link is required')
        return self.issuer_links(bound[0].persona).redeem(code, create)


class PublishedReader:
    """Fixed trusted host composition; construction opens no network listener.

    The operator supplies protected publication paths, public issuer identities
    and an audit ledger. No source discovery, refresh worker or CLI is installed.
    """
    def __init__(self, *, authority, projection_root, actor, identities, origin, port,
                 issuer_uid, socket_path, socket_group, audit, session_seconds=1800, conversation_socket=None,
                 additional_issuers=None, reviewed_knowledge=None):
        if (not isinstance(authority, PublishedAuthority) or not isinstance(audit, Ledger)
                or not isinstance(actor, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', actor)
                or type(identities) not in (list, tuple) or not 1 <= len(identities) <= 64
                or any(not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key) for key in identities)
                or len(set(identities)) != len(identities)
                or type(port) is not int or not 0 <= port <= 65535):
            raise ValueError('Fixed authority, issuer allowlist, audit and reader binding required')
        primary = dict(actor=actor, identities=list(identities), issuer_uid=issuer_uid,
                       socket_path=str(socket_path), socket_group=socket_group,
                       conversation_socket=str(conversation_socket) if conversation_socket is not None else None)
        self.routes = ([primary] if additional_issuers is None else validate_routes(primary, additional_issuers))
        self.authority, self.port = authority, port
        gate_type = MultiIssuerGate if len(self.routes) > 1 else RecipientGate
        route_options = {'routes': self.routes} if len(self.routes) > 1 else {}
        self.gate = gate_type(signed_access(), {'actor': actor, 'identities': list(identities)},
                                  origin, port, directory_loader=authority, audit=audit,
                                  session_seconds=session_seconds, **route_options)
        if not self.gate.origin.startswith('https://'):
            raise ValueError('An explicit HTTPS reader origin is required')
        self.projection = PublishedProjection(projection_root, authority.read, authority.snapshot)
        self.knowledge_source = None
        knowledge = None
        if reviewed_knowledge is not None:
            from reader_knowledge import ReaderKnowledgeSource
            from reviewed_knowledge import ReviewedKnowledge
            self.knowledge_source = ReaderKnowledgeSource(reviewed_knowledge, authority.read, authority.snapshot)
            knowledge = ReviewedKnowledge(self.gate, self.knowledge_source.review, authority.read,
                                          authority.snapshot, self.knowledge_source.note,
                                          scan_source=self.knowledge_source._scan_review)
        self.backend = ScopedBackend(self.gate, self.projection.catalog, self.projection.record,
                                     reviewed_knowledge=knowledge)
        self.consultations = None
        if any(route['conversation_socket'] is not None for route in self.routes):
            from persona_conversation import NativePersonaClient, PersonaAssistant
            from scoped_consultations import ScopedConsultations
            self.consultations = ScopedConsultations(PersonaAssistant(self.backend,
                {route['actor']: NativePersonaClient(route['conversation_socket'], route['issuer_uid'], route['actor'])
                 for route in self.routes if route['conversation_socket'] is not None}))
        self.issuer_uid, self.socket_path, self.socket_group = issuer_uid, socket_path, socket_group
        self.server, self.handoff = None, None
        self._started = False
        self._start_lock = threading.Lock()
        self.preflight()

    def preflight(self):
        if self.knowledge_source is not None:
            self.knowledge_source.preflight()
        directory = self.authority()
        catalog = self.projection.catalog()
        if (any(route['actor'] not in directory.scope.policy['personas'] for route in self.routes)
                or catalog['organization'] != directory.scope.policy['organization']
                or catalog['authority_revision'] != directory.authority_revision):
            raise ValueError('Reviewed projection and issuing persona must match current authority')

    def _make_server(self):
        server = ThreadingHTTPServer(('127.0.0.1', self.port), RecipientHandler)
        server.gate, server.scoped_backend = self.gate, self.backend
        server.access_errors = (ValueError, self.gate.access.core.Invalid)
        server.scoped_consultations = self.consultations
        server.review_service = None
        return server

    def serve(self, *, stop_event=None):
        with self._start_lock:
            if self._started:
                raise ValueError('An identified reader instance cannot be restarted')
            self._started = True
        server = handoff = None
        handoffs = []
        try:
            # Verify explicit Linux daemon/reader accounts before binding HTTP or IPC.
            policies = [DaemonPeerPolicy(route['issuer_uid']) for route in self.routes]
            self.preflight()
            for route, policy in zip(self.routes, policies):
                options = {'actor': route['actor']} if len(self.routes) > 1 else {}
                handoffs.append(ReaderHandoff(route['socket_path'], route['socket_group'], policy, self.gate, **options))
            handoff = handoffs[0]
            server = self._make_server()
            self.server, self.handoff = server, handoff
            for listener in handoffs:
                listener.start(server)
            if stop_event is None:
                server.serve_forever()
            else:
                # Signal handlers only set an event; cleanup remains on this thread.
                server.timeout = 0.25
                while not stop_event.is_set():
                    server.handle_request()
        finally:
            try:
                failure = None
                for listener in reversed(handoffs):
                    try:
                        listener.close()
                    except Exception as error:
                        failure = failure or error
                if failure is not None:
                    raise failure
            finally:
                try:
                    if server is not None:
                        server.server_close()
                finally:
                    if self.consultations is not None:
                        self.consultations.close()
                    with self.gate.recipient_lock, self.gate.lock:
                        self.gate.sessions.clear()
                        self.gate.session_ids.clear()
                        self.gate.recipients.clear()
                        self.gate.recipient_links.clear()

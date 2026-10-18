"""Compose the existing authority, reviewed projection, HTTP gate and daemon IPC."""
from http.server import ThreadingHTTPServer
import re
import threading

from authority_publication import PublishedAuthority
from identified_access import IdentifiedGate
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


class PublishedReader:
    """Fixed trusted host composition; construction opens no network listener.

    The operator supplies protected publication paths, public issuer identities
    and an audit ledger. No source discovery, refresh worker or CLI is installed.
    """
    def __init__(self, *, authority, projection_root, actor, identities, origin, port,
                 issuer_uid, socket_path, socket_group, audit, session_seconds=1800, conversation_socket=None):
        if (not isinstance(authority, PublishedAuthority) or not isinstance(audit, Ledger)
                or not isinstance(actor, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', actor)
                or type(identities) not in (list, tuple) or not 1 <= len(identities) <= 64
                or any(not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{64}', key) for key in identities)
                or len(set(identities)) != len(identities)
                or type(port) is not int or not 0 <= port <= 65535):
            raise ValueError('Fixed authority, issuer allowlist, audit and reader binding required')
        self.authority, self.port = authority, port
        self.gate = RecipientGate(signed_access(), {'actor': actor, 'identities': list(identities)},
                                  origin, port, directory_loader=authority, audit=audit,
                                  session_seconds=session_seconds)
        if not self.gate.origin.startswith('https://'):
            raise ValueError('An explicit HTTPS reader origin is required')
        self.projection = PublishedProjection(projection_root, authority.read, authority.snapshot)
        self.backend = ScopedBackend(self.gate, self.projection.catalog, self.projection.record)
        self.consultations = None
        if conversation_socket is not None:
            from persona_conversation import NativePersonaClient, PersonaAssistant
            from scoped_consultations import ScopedConsultations
            self.consultations = ScopedConsultations(PersonaAssistant(self.backend,
                {actor: NativePersonaClient(conversation_socket, issuer_uid, actor)}))
        self.issuer_uid, self.socket_path, self.socket_group = issuer_uid, socket_path, socket_group
        self.server, self.handoff = None, None
        self._started = False
        self._start_lock = threading.Lock()
        self.preflight()

    def preflight(self):
        directory = self.authority()
        catalog = self.projection.catalog()
        if (self.gate.policy['actor'] not in directory.scope.policy['personas']
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
        try:
            # Verify explicit Linux daemon/reader accounts before binding HTTP or IPC.
            policy = DaemonPeerPolicy(self.issuer_uid)
            self.preflight()
            handoff = ReaderHandoff(self.socket_path, self.socket_group, policy, self.gate)
            server = self._make_server()
            self.server, self.handoff = server, handoff
            handoff.start(server)
            if stop_event is None:
                server.serve_forever()
            else:
                # Signal handlers only set an event; cleanup remains on this thread.
                server.timeout = 0.25
                while not stop_event.is_set():
                    server.handle_request()
        finally:
            try:
                if handoff is not None:
                    handoff.close()
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

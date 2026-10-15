"""Inactive, in-process recipient adapter over the unchanged signed-link gate.

No HTTP route, CLI switch or environment identity claim enables this adapter.
A trusted channel integration and a private policy loader must be supplied first.
"""
import re
import threading

from access_gate import Gate


class IdentifiedGate(Gate):
    def __init__(self, *args, directory_loader, **kwargs):
        if not callable(directory_loader):
            raise ValueError("A private organization policy loader is required")
        super().__init__(*args, **kwargs)
        self.directory_loader = directory_loader
        self.recipient_links, self.recipients = {}, {}
        self.recipient_lock = threading.RLock()

    def issue_identified(self, authorization, origin, **channel_context):
        """Trusted pre-model adapter only; never forward a browser JSON body.

        Shared Schnorr verification, exact tags/payload and replay protection stay
        in Gate.issue(). Recipient metadata never enters the URL or signed event.
        """
        if channel_context.get("persona") != self.policy.get("actor"):
            raise ValueError("Recipient issuer does not match this reader")
        recipient = self.directory_loader().resolve(**channel_context)
        with self.recipient_lock:
            self._prune_recipients()
            if len(self.recipient_links) >= 1000:
                raise ValueError("Too many pending recipient links")
            link = self.issue(authorization, origin)
            match = re.fullmatch(re.escape(self.origin) + r"/#c=([A-Za-z0-9_-]{43})", link)
            if not match:
                raise ValueError("Invalid signed access link response")
            self.recipient_links[self.digest(match[1])] = (recipient, self.clock() + 300)
            return link

    def _prune_recipients(self):
        self.recipient_links = {key: row for key, row in self.recipient_links.items() if row[1] > self.clock()}
        # Match base-session expiry/logout/revocation, without retaining identities.
        with self.lock:
            self._prune()
            self.recipients = {key: row for key, row in self.recipients.items() if key in self.sessions}

    def redeem(self, code):
        # Lock order is recipient -> signed-link -> session throughout this class.
        with self.recipient_lock:
            def create():
                bound = self.recipient_links.get(self.digest(code))
                if bound is None:
                    return self.create_session()  # Legacy analysis only, never promoted.
                if bound[1] <= self.clock():
                    raise ValueError("Recipient link expired")
                recipient = self.directory_loader().validate(bound[0])
                value = self.create_session()
                self.recipients[self.digest(value)] = recipient
                return value
            value = self.links.redeem(code, create)
            self.recipient_links.pop(self.digest(code), None)
            self._prune_recipients()
            return value

    def identified_scope(self, headers):
        """Check current private policy before EVERY extended request."""
        with self.recipient_lock:
            self._prune_recipients()
            owner, _ = self.session_scope(headers)
            recipient = self.recipients.get(owner)
            if recipient is None:
                raise ValueError("Request an identified link through your verified channel")
            directory = self.directory_loader()
            directory.validate(recipient)
            return recipient, directory

    def revoke(self, ident):
        with self.recipient_lock:
            result = super().revoke(ident)
            self._prune_recipients()
            return result

    def logout(self, headers):
        with self.recipient_lock:
            super().logout(headers)
            self._prune_recipients()

"""Inactive pre-model command handler for an isolated authenticated channel host.

The message object is transport-owned context, not an authentication mechanism.
Never register this module as a model tool or call it from an HTTP identity API.
"""
from dataclasses import dataclass
from enum import Enum
import os
import re
import threading
import time
from urllib.parse import urlsplit

from handoff_client import ReaderPolicy, request_access


class Outcome(Enum):
    NOT_COMMAND = 'not_command'
    REJECTED = 'rejected'
    DUPLICATE = 'duplicate'
    UNAVAILABLE = 'unavailable'
    DELIVERED = 'delivered'


@dataclass(frozen=True, repr=False)
class DirectMessage:
    sender: str
    message_id: str
    sent_at: int
    text: str
    direct: bool
    principal_authenticated: bool


class NativeAccessCommand:
    """Consume reserved commands; return status only, never the link or identity.

    The signer and direct-delivery callbacks belong to the isolated native host.
    They must enforce their own finite deadlines. The reader authenticates this
    process with SO_PEERCRED and resolves current human/persona/scope authority.
    """

    def __init__(self, *, channel, scope_id, socket_path, policy, origin,
                 sign_authorization, deliver_direct, wall_clock=time.time,
                 monotonic=time.monotonic):
        if not isinstance(policy, ReaderPolicy):
            raise ValueError('An isolated native reader policy is required')
        policy.__post_init__()  # Revalidate the current account, not a saved assertion.
        if (channel not in {'telegram', 'phantomchat'} or not isinstance(scope_id, str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', scope_id)
                or not callable(sign_authorization) or not callable(deliver_direct)):
            raise ValueError('Fixed native channel, scope and callbacks are required')
        if not isinstance(origin, str):
            raise ValueError('A fixed canonical HTTPS origin is required')
        parsed = urlsplit(origin)
        if (any(ord(char) < 33 for char in origin) or parsed.scheme != 'https'
                or not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment or origin != 'https://' + parsed.netloc):
            raise ValueError('A fixed canonical HTTPS origin is required')
        _ = parsed.port
        self.channel, self.scope_id, self.socket_path = channel, scope_id, socket_path
        self.policy, self.origin = policy, origin
        self._uid = os.getuid()
        self._sign, self._deliver = sign_authorization, deliver_direct
        self._wall, self._clock = wall_clock, monotonic
        self._seen, self._attempts, self._lock = {}, [], threading.Lock()

    def _valid(self, message):
        sender = (r'[1-9][0-9]{0,15}' if self.channel == 'telegram'
                  else r'npub1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{58}')
        identifier = r'[1-9][0-9]{0,15}' if self.channel == 'telegram' else r'[a-f0-9]{64}'
        return (message.direct is True and message.principal_authenticated is True
                and isinstance(message.sender, str) and re.fullmatch(sender, message.sender)
                and (self.channel != 'telegram' or int(message.sender) <= 2**53 - 1)
                and isinstance(message.message_id, str) and re.fullmatch(identifier, message.message_id)
                and type(message.sent_at) is int and abs(self._wall() - message.sent_at) <= 60)

    def handle(self, message):
        """Only NOT_COMMAND may continue to an ordinary model dispatcher.

        Reject arguments, scope/identity overrides, group/relay/open-bot contexts
        and stale events before signing, IPC or delivery. Claim before I/O; an
        ambiguous failure never resends the same event automatically.
        """
        if not isinstance(message, DirectMessage) or not isinstance(message.text, str):
            return Outcome.REJECTED
        if not re.match(r'^\s*/phantomview(?:\s|@|$)', message.text, re.IGNORECASE):
            return Outcome.NOT_COMMAND
        if message.text.strip() != '/phantomview' or not self._valid(message):
            return Outcome.REJECTED
        if os.getuid() != self._uid:
            return Outcome.REJECTED
        try:
            self.policy.__post_init__()
        except ValueError:
            return Outcome.REJECTED
        key = (message.sender, message.message_id)
        with self._lock:
            now = self._clock()
            self._seen = {key: expiry for key, expiry in self._seen.items() if expiry > now}
            self._attempts = [(stamp, sender) for stamp, sender in self._attempts if now - stamp < 60]
            if key in self._seen:
                return Outcome.DUPLICATE
            if (len(self._seen) >= 256 or len(self._attempts) >= 16
                    or sum(sender == message.sender for _, sender in self._attempts) >= 3):
                return Outcome.UNAVAILABLE
            self._seen[key] = now + 120
            self._attempts.append((now, message.sender))
        try:
            context = {'channel': self.channel, 'sender': message.sender, 'direct': True,
                       'principal_authenticated': True, 'scope_id': self.scope_id}
            authorization = self._sign()
            link = request_access(self.socket_path, self.policy, self.origin, authorization, context)
            # Defense in depth: callbacks never choose a delivery destination.
            if not re.fullmatch(re.escape(self.origin) + r'/#c=[A-Za-z0-9_-]{43}', link):
                return Outcome.UNAVAILABLE
            delivered = self._deliver(self.channel, message.sender, link)
            return Outcome.DELIVERED if delivered is True else Outcome.UNAVAILABLE
        except Exception:
            # Consume a reserved command on any callback failure. Exception text
            # may contain a grant or credential and must not reach model/logs.
            return Outcome.UNAVAILABLE

"""Recipient policy for a future pre-model channel adapter, not authentication.

Only the channel's authenticated direct-message handler may call resolve().
No HTTP body, tool argument, environment variable or model output is a verified
channel context. This module is not registered with the live reader.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import re

from assistant_scope import Scope


@dataclass(frozen=True)
class Recipient:
    organization: str
    human: str
    persona: str
    policy_revision: str
    directory_revision: str

    def metadata(self):
        """Exclude raw channel IDs, cookies and link credentials."""
        return asdict(self)


class HumanDirectory:
    def __init__(self, org, default_persona=None):
        self.scope = Scope.from_org(org, default_persona=default_persona)
        self.senders = {"telegram": {}, "phantomchat": {}}
        for human in org.get("humans", []):
            for channel, field in (("telegram", "telegram_user_id"), ("phantomchat", "npub")):
                value = human.get(field)
                if value is None:
                    continue
                if channel == "telegram":
                    if type(value) is not int or not 0 < value <= 2**53 - 1:
                        raise ValueError("Invalid Telegram human identity")
                    identity = str(value)
                else:
                    # The adapter uses nip19.npubEncode on the proven sender hex.
                    # No envelope `from`, handle or display name is accepted.
                    if not isinstance(value, str) or not re.fullmatch(r"npub1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{58}", value):
                        raise ValueError("Invalid PhantomChat human identity")
                    identity = value
                if identity in self.senders[channel]:
                    raise ValueError("Ambiguous channel identity")
                self.senders[channel][identity] = human["id"]
        encoded = json.dumps({"scope": self.scope.revision, "senders": self.senders}, sort_keys=True).encode()
        self.revision = hashlib.sha256(encoded).hexdigest()

    def resolve(self, *, channel, sender, persona, direct, principal_authenticated):
        """Resolve adapter-owned data AFTER its explicit allowlist check.

        Empty allowlists, relay tiers, group chats and email From do not qualify.
        PhantomChat must supply a canonical npub derived with its existing NIP-19
        library from the cryptographically proven sender, never message text.
        """
        if direct is not True or principal_authenticated is not True:
            raise ValueError("Verified direct channel principal required")
        if not isinstance(channel, str) or channel not in self.senders or not isinstance(sender, str):
            raise ValueError("Unsupported verified channel identity")
        human = self.senders[channel].get(sender)
        if human is None or not self.scope.can_issue(human, persona):
            raise ValueError("Human is not eligible for this persona")
        return Recipient(self.scope.policy["organization"], human, persona,
                         self.scope.revision, self.revision)

    def validate(self, recipient):
        if (not isinstance(recipient, Recipient)
                or recipient.organization != self.scope.policy["organization"]
                or recipient.policy_revision != self.scope.revision
                or recipient.directory_revision != self.revision
                or not self.scope.can_issue(recipient.human, recipient.persona)):
            raise ValueError("Recipient policy changed; request a new access link")
        return recipient

    def permits(self, recipient, resource):
        self.validate(recipient)
        return self.scope.permits(recipient.human, recipient.persona, resource)

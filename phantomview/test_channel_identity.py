"""Recipient binding tests; channel verification itself belongs to PhantomBot."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import unittest

from channel_identity import HumanDirectory
from identified_access import IdentifiedGate
from preview_human_access import preview
from test_access_gate import ACCESS


def organization():
    return {
        "organization": {"id": "example"},
        "roles": [{"id": "executive", "access_level": "board"}],
        "actors": [{"id": p, "role": "executive"} for p in ("coordinator", "administrator", "treasurer")],
        "humans": [
            {"id": "owner", "counterpart_persona": "coordinator", "telegram_user_id": 101},
            {"id": "secretary", "counterpart_persona": "administrator", "telegram_user_id": 102},
            {"id": "accountant", "counterpart_persona": "treasurer", "telegram_user_id": 103},
            {"id": "unbound", "telegram_user_id": 104},
        ],
        "policies": {
            "security_categories": {"category-0": {"owner": "owner"}, "category-1": {}, "category-4-project": {}},
            "access_levels": {"board": {"categories": [1]}},
        },
    }


def context(sender="101", persona="coordinator", **changes):
    return {"channel": "telegram", "sender": sender, "persona": persona,
            "direct": True, "principal_authenticated": True} | changes


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.org = organization()
        self.directory = HumanDirectory(self.org)

    def test_counterpart_matrix_and_independent_category_zero(self):
        for sender, persona, human in (("101", "coordinator", "owner"), ("102", "administrator", "secretary"), ("103", "treasurer", "accountant")):
            recipient = self.directory.resolve(**context(sender, persona))
            self.assertEqual(recipient.human, human)
            self.assertTrue(self.directory.permits(recipient, {"organization": "example", "category": "category-1", "secret": False}))
        with self.assertRaises(ValueError):
            self.directory.resolve(**context("102", "coordinator"))
        with self.assertRaises(ValueError):
            self.directory.resolve(**context("104"))
        self.org["policies"]["security_categories"]["category-0"]["owner"] = "unbound"
        directory = HumanDirectory(self.org)
        recipient = directory.resolve(**context("104", "treasurer"))
        self.assertTrue(directory.permits(recipient, {"organization": "example", "category": "category-4-project", "project": "project", "secret": False}))
        self.assertFalse(directory.permits(recipient, {"organization": "example", "category": "category-0", "secret": True}))

    def test_no_browser_identity_email_group_or_relay_authority(self):
        for changes in ({"sender": "owner"}, {"sender": "00101"}, {"sender": 101},
                        {"sender": "999"}, {"channel": "email"}, {"direct": False},
                        {"direct": 1}, {"principal_authenticated": False}, {"principal_authenticated": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.directory.resolve(**context(**changes))

    def test_ambiguous_or_invalid_channel_configuration_fails_closed(self):
        for value in (101, True, 0, -1, "105", 2**53):
            org = copy.deepcopy(self.org)
            org["humans"][1]["telegram_user_id"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                HumanDirectory(org)

    def test_phantomchat_uses_exact_adapter_npub_and_keeps_relay_untrusted(self):
        # Shape-only fixture: envelope verification/encoding belongs to the adapter.
        npub = "npub1" + "q" * 58
        self.org["humans"][0]["npub"] = npub
        directory = HumanDirectory(self.org)
        recipient = directory.resolve(**context(channel="phantomchat", sender=npub))
        self.assertEqual(recipient.human, "owner")
        for sender in ("owner", npub.upper(), "npub1" + "p" * 58):
            with self.assertRaises(ValueError):
                directory.resolve(**context(channel="phantomchat", sender=sender))
        with self.assertRaises(ValueError):
            directory.resolve(**context(channel="phantomchat", sender=npub, principal_authenticated=False))
        self.org["humans"][1]["npub"] = npub
        with self.assertRaises(ValueError):
            HumanDirectory(self.org)

    def test_channel_id_changes_invalidate_recipient_even_when_grants_unchanged(self):
        recipient = self.directory.resolve(**context())
        self.org["humans"][0]["telegram_user_id"] = 999
        changed = HumanDirectory(self.org)
        self.assertEqual(changed.scope.revision, recipient.policy_revision)
        with self.assertRaises(ValueError):
            changed.validate(recipient)
        self.assertNotIn("101", json.dumps(recipient.metadata()))

    def test_preview_does_not_write_or_assume_missing_channel_identity(self):
        del self.org["humans"][2]["telegram_user_id"]
        before = copy.deepcopy(self.org)
        rows = preview(self.org, ["owner=coordinator"])["humans"]
        self.assertEqual(self.org, before)
        accountant = next(row for row in rows if row["human"] == "accountant")
        self.assertEqual(accountant["counterpart"], "treasurer")
        self.assertFalse(accountant["eligible_after_trusted_channel_integration"])
        self.assertNotIn("101", json.dumps(rows))


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.org, self.ticks = organization(), [0]
        self.gate = IdentifiedGate(ACCESS, {"identities": ["a" * 64], "actor": "coordinator"},
                                  "https://view.example:8790", 8789,
                                  clock=lambda: self.ticks[0], directory_loader=lambda: HumanDirectory(self.org))

    def issue(self):
        link = self.gate.issue_identified("Nostr test-signed-event", self.gate.origin, **context())
        self.assertNotIn("owner", link)
        self.assertNotIn("101", link)
        return link.split("#c=")[1]

    def test_bound_single_use_session_and_legacy_never_promoted(self):
        code = self.issue()
        value = self.gate.redeem(code)
        headers = {"Cookie": "phantomview=" + value}
        recipient, directory = self.gate.identified_scope(headers)
        self.assertEqual(recipient.human, "owner")
        self.assertEqual(directory.scope.policy["organization"], "example")
        self.assertNotIn(code, self.gate.recipient_links)
        self.assertNotIn(value, self.gate.recipients)
        with self.assertRaises(ValueError):
            self.gate.redeem(code)
        legacy = self.gate.create_session()
        with self.assertRaises(ValueError):
            self.gate.identified_scope({"Cookie": "phantomview=" + legacy})

    def test_parallel_redeemers_only_one_gets_bound_session(self):
        code = self.issue()
        def redeem(_):
            try:
                return self.gate.redeem(code)
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            sessions = [value for value in pool.map(redeem, range(12)) if value]
        self.assertEqual(len(sessions), 1)
        self.assertEqual(len(self.gate.recipients), 1)

    def test_policy_changes_deny_redemption_and_every_subsequent_request(self):
        code = self.issue()
        self.org["humans"][0]["telegram_user_id"] = 999
        with self.assertRaises(ValueError):
            self.gate.redeem(code)
        self.assertEqual(self.gate.sessions, {})
        self.org["humans"][0]["telegram_user_id"] = 101
        value = self.gate.redeem(code)
        self.org["policies"]["security_categories"]["category-0"]["owner"] = "unbound"
        with self.assertRaises(ValueError):
            self.gate.identified_scope({"Cookie": "phantomview=" + value})

    def test_expiry_logout_and_revocation_clear_recipient_state(self):
        for action in ("logout", "expire", "revoke"):
            with self.subTest(action=action):
                self.setUp()
                value = self.gate.redeem(self.issue())
                headers = {"Cookie": "phantomview=" + value}
                if action == "logout":
                    self.gate.logout(headers)
                elif action == "expire":
                    self.ticks[0] = 1800
                else:
                    self.gate.revoke(next(iter(self.gate.session_ids.values())))
                with self.assertRaises(ValueError):
                    self.gate.identified_scope(headers)
                self.assertEqual(self.gate.recipients, {})

    def test_wrong_issuer_or_bad_signature_never_creates_recipient_binding(self):
        with self.assertRaises(ValueError):
            self.gate.issue_identified("Nostr test-signed-event", self.gate.origin, **context(persona="treasurer"))
        with self.assertRaises(ValueError):
            self.gate.issue_identified("invalid", self.gate.origin, **context())
        self.assertEqual(self.gate.recipient_links, {})

    def test_expired_recipient_link_cannot_create_session(self):
        code = self.issue()
        self.ticks[0] = 300
        with self.assertRaises(ValueError):
            self.gate.redeem(code)
        self.assertEqual(self.gate.sessions, {})


if __name__ == "__main__":
    unittest.main()

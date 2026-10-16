"""Optional integration suite against the real installed PhantomBlog verifier."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time
import unittest
import uuid

from channel_identity import HumanDirectory
from identified_access import IdentifiedGate
from scoped_knowledge import retrieve
from test_channel_identity import context, organization
from test_scoped_knowledge import note_fixture

try:
    from coincurve import PrivateKey
    from phantomblog import access
except ImportError:
    PrivateKey = None


@unittest.skipIf(PrivateKey is None, "Install the PhantomBlog access extra to run real-signature integration")
class SignedRecipientTests(unittest.TestCase):
    def setUp(self):
        self.org, self.ticks = organization(), [0]
        self.key = PrivateKey()
        self.identity = self.key.public_key_xonly.format().hex()
        self.gate = IdentifiedGate(access, {"identities": [self.identity], "actor": "coordinator"},
                                  "https://view.example:8790", 8789,
                                  clock=lambda: self.ticks[0], directory_loader=lambda: HumanDirectory(self.org))
        self.gate.links.clock = lambda: self.ticks[0]

    def signed(self, changes=None):
        event = {"pubkey": self.identity, "created_at": int(time.time()), "kind": 27235,
                 "tags": [["u", self.gate.origin + "/api/access-link"], ["method", "POST"],
                          ["payload", hashlib.sha256(b"{}").hexdigest()], ["nonce", uuid.uuid4().hex]],
                 "content": ""} | (changes or {})
        event["id"] = access.event_digest(event)
        event["sig"] = self.key.sign_schnorr(bytes.fromhex(event["id"])).hex()
        return event

    @staticmethod
    def authorization(event):
        return "Nostr " + base64.b64encode(json.dumps(event).encode()).decode()

    def issue(self, event=None, identified=True):
        authorization = self.authorization(event or self.signed())
        if identified:
            link = self.gate.issue_identified(authorization, self.gate.origin, **context())
        else:
            link = self.gate.issue(authorization, self.gate.origin)
        return link.split("#c=")[1]

    def test_real_signature_and_concurrent_single_use_redemption(self):
        code = self.issue()
        def redeem(_):
            try:
                return self.gate.redeem(code)
            except access.core.Invalid:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = [value for value in pool.map(redeem, range(16)) if value]
        self.assertEqual(len(results), 1)
        recipient, _ = self.gate.identified_scope({"Cookie": "phantomview=" + results[0]})
        self.assertEqual(recipient.human, "owner")

    def test_signature_replay_freshness_and_exact_payload_stay_enforced(self):
        event = self.signed()
        self.issue(event)
        with self.assertRaises(access.core.Invalid):
            self.issue(event)
        for changes in ({"created_at": int(time.time()) - 120}, {"content": "owner"},
                        {"tags": [["u", self.gate.origin + "/api/access-link"], ["method", "POST"],
                                  ["payload", hashlib.sha256(b'{"human":"owner"}').hexdigest()]]}):
            with self.subTest(changes=changes), self.assertRaises(access.core.Invalid):
                self.issue(self.signed(changes))
        event = self.signed()
        event["sig"] = "0" * 128
        with self.assertRaises(access.core.Invalid):
            self.issue(event)

    def test_pruning_recipient_metadata_never_extends_underlying_grant(self):
        code = self.issue()
        self.ticks[0] = 300
        self.gate._prune_recipients()
        with self.assertRaises(access.core.Invalid):
            self.gate.redeem(code)
        self.assertEqual(self.gate.sessions, {})

    def test_ordinary_signed_link_stays_unidentified(self):
        cookie = self.gate.redeem(self.issue(identified=False))
        with self.assertRaises(ValueError):
            self.gate.identified_scope({"Cookie": "phantomview=" + cookie})

    def test_real_signed_session_precedes_knowledge_reads_and_logout_denies(self):
        raw, catalog = note_fixture()
        loaded = []
        def load(ident):
            loaded.append(ident)
            return raw
        cookie = self.gate.redeem(self.issue())
        headers = {"Cookie": "phantomview=" + cookie}
        self.assertEqual(len(retrieve(self.gate, headers, lambda: catalog, load, 'organization')['notes']), 1)
        loaded.clear()
        self.gate.logout(headers)
        with self.assertRaises(ValueError):
            retrieve(self.gate, headers, lambda: catalog, load, 'organization')
        self.assertEqual(loaded, [])
        legacy = self.gate.redeem(self.issue(identified=False))
        with self.assertRaises(ValueError):
            retrieve(self.gate, {"Cookie": "phantomview=" + legacy}, lambda: catalog, load, 'organization')
        self.assertEqual(loaded, [])

    def test_real_signed_link_binds_scope_without_changing_signed_payload(self):
        from test_view_permissions import project_resource, scoped_organization
        self.org = scoped_organization()
        link = self.gate.issue_identified(self.authorization(self.signed()), self.gate.origin,
                                         **context(), scope_id='river-project')
        self.assertNotIn('river-project', link)
        cookie = self.gate.redeem(link.split('#c=')[1])
        headers = {'Cookie': 'phantomview=' + cookie}
        recipient, directory = self.gate.identified_scope(headers)
        self.assertEqual(recipient.scope_id, 'river-project')
        self.assertTrue(directory.permits(recipient, project_resource(category='category-3')))
        self.assertFalse(directory.permits(recipient, project_resource('other-project')))
        self.org['policies']['phantomview']['human_action_grants'] = {}
        with self.assertRaises(ValueError):
            self.gate.identified_scope(headers)

    def test_policy_change_denies_before_session_creation_without_consuming_grant(self):
        code = self.issue()
        self.org["humans"][0]["telegram_user_id"] = 999
        with self.assertRaises(ValueError):
            self.gate.redeem(code)
        self.assertEqual(self.gate.sessions, {})
        self.org["humans"][0]["telegram_user_id"] = 101
        value = self.gate.redeem(code)
        self.assertEqual(self.gate.identified_scope({"Cookie": "phantomview=" + value})[0].human, "owner")


if __name__ == "__main__":
    unittest.main()

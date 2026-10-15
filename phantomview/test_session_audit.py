import json
from pathlib import Path
import tempfile
import unittest
import uuid

from access_gate import Gate
from assistant_scope import Scope
from session_audit import Ledger
from test_access_gate import ACCESS


class AuditTests(unittest.TestCase):
    def test_session_lifecycle_correlates_without_credentials_and_deduplicates_polls(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp) / "audit.sqlite")
            ticks = [0]
            gate = Gate(ACCESS, {"identities": ["a" * 64]}, "https://example.test", 8789,
                        clock=lambda: ticks[0], audit=ledger)
            token = gate.create_session()
            headers = {"Cookie": "phantomview=" + token}
            job = str(uuid.uuid4())
            for _ in range(3):
                gate.audit_event(headers, "assistant_response_observed", job_id=job, status="held")
            gate.logout(headers)
            rows = ledger.export()
            self.assertEqual([r["event"] for r in rows],
                             ["session_created", "assistant_response_observed", "session_logout"])
            self.assertEqual(len({r["session"] for r in rows}), 1)
            self.assertNotIn(token, json.dumps(rows))
            self.assertNotIn(gate.digest(token), json.dumps(rows))
            self.assertFalse(gate.session(headers))
            token2 = gate.create_session()
            ticks[0] = 1801
            self.assertFalse(gate.session({"Cookie": "phantomview=" + token2}))
            self.assertEqual(ledger.export()[-1]["event"], "session_expired")

    def test_revocation_and_unavailable_ledger_never_create_unaudited_session(self):
        class Broken:
            def record(self, *args, **kwargs):
                raise OSError("private error")
        gate = Gate(ACCESS, {"identities": ["a" * 64]}, "https://example.test", 8789, audit=Broken())
        with self.assertRaises(ValueError):
            gate.create_session()
        self.assertEqual(gate.sessions, {})
        gate.audit = None
        token = gate.create_session()
        ident = next(iter(gate.session_ids.values()))
        gate.audit = Broken()
        self.assertTrue(gate.revoke(ident))
        self.assertFalse(gate.session({"Cookie": "phantomview=" + token}))

    def test_strict_metadata_retention_and_restart_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            ticks = [100000]
            path = Path(tmp) / "audit.sqlite"
            ledger = Ledger(path, 1, clock=lambda: ticks[0])
            ident = "a" * 32
            for metadata in ({"prompt": "secret"}, {"status": "token=value"}, {"job_id": "not-a-uuid"}):
                with self.assertRaises(ValueError):
                    ledger.record("assistant_requested", ident, **metadata)
            ledger.record("session_created", ident)
            self.assertEqual(len(Ledger(path).export()), 0)  # Old timestamp is outside real-time retention.
            ticks[0] += 86401
            ledger.record("session_logout", ident)
            self.assertEqual([r["event"] for r in ledger.export()], ["session_logout"])
            self.assertEqual(Ledger(path, 1, clock=lambda: ticks[0]).export(), ledger.export())


class ScopeTests(unittest.TestCase):
    def setUp(self):
        grants = {"categories": ["category-1", "category-2", "category-3"], "projects": []}
        self.policy = {"organization": "example", "humans": {"owner": grants}, "personas": {"lead": grants}}
        self.scope = Scope(self.policy)

    def resource(self, **changes):
        return dict(organization="example", category="category-2", secret=False, **changes)

    def test_exact_intersection_and_explicit_non_secret_classification(self):
        resource = self.resource()
        self.assertTrue(self.scope.permits("owner", "lead", resource))
        for human, persona in (("stranger", "lead"), ("owner", "other")):
            self.assertFalse(self.scope.permits(human, persona, resource))
        for change in ({"secret": True}, {"secret": None}, {"category": "category-0"},
                       {"category": "category-4-almaponia"}, {"organization": "elsewhere"},
                       {"category": None}, {"project": "almaponia"}):
            self.assertFalse(self.scope.permits("owner", "lead", {**resource, **change}))
        self.policy["humans"]["owner"]["categories"].append("category-4-almaponia")
        self.assertFalse(self.scope.permits("owner", "lead", {**resource, "category": "category-4-almaponia"}))

    def test_project_requires_exact_grant_on_both_principals(self):
        for row in (self.policy["humans"]["owner"], self.policy["personas"]["lead"]):
            row["categories"].append("category-4-almaponia")
            row["projects"].append("almaponia")
        scope = Scope(self.policy)
        resource = {**self.resource(), "category": "category-4-almaponia"}
        self.assertFalse(scope.permits("owner", "lead", resource))
        self.assertTrue(scope.permits("owner", "lead", {**resource, "project": "almaponia"}))
        self.assertFalse(scope.permits("owner", "lead", {**resource, "project": "other"}))
        self.assertNotEqual(scope.revision, self.scope.revision)


if __name__ == "__main__":
    unittest.main()

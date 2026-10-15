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
        self.policy = {"organization": "example", "humans": {"owner": {"counterpart_persona": "lead"}}, "personas": {"lead": grants}}
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
        self.policy["personas"]["lead"]["categories"].append("category-4-almaponia")
        self.assertFalse(self.scope.permits("owner", "lead", {**resource, "category": "category-4-almaponia"}))

    def test_project_requires_exact_grant_on_both_principals(self):
        row = self.policy["personas"]["lead"]
        row["categories"].append("category-4-almaponia")
        row["projects"].append("almaponia")
        scope = Scope(self.policy)
        resource = {**self.resource(), "category": "category-4-almaponia"}
        self.assertFalse(scope.permits("owner", "lead", resource))
        self.assertTrue(scope.permits("owner", "lead", {**resource, "project": "almaponia"}))
        self.assertFalse(scope.permits("owner", "lead", {**resource, "project": "other"}))
        self.assertNotEqual(scope.revision, self.scope.revision)

    def test_human_cannot_choose_another_persona_or_edit_inherited_grants(self):
        self.policy["personas"]["other"] = {"categories": ["category-3"], "projects": []}
        scope = Scope(self.policy)
        self.assertFalse(scope.can_issue("owner", "other"))
        self.assertFalse(scope.can_issue("unbound", "lead"))
        grants = scope.human_grants("owner")
        grants["categories"].clear()
        self.assertTrue(scope.permits("owner", "lead", self.resource()))
        self.policy["humans"]["owner"]["categories"] = ["category-3"]
        with self.assertRaises(ValueError):
            Scope(self.policy)

    def test_org_is_single_source_and_unbound_humans_have_no_eligibility(self):
        org = {"organization": {"id": "example"},
               "roles": [{"id": "ceo", "access_level": "level-3"}, {"id": "staff", "access_level": "level-2"}],
               "actors": [{"id": "paco", "role": "ceo"}, {"id": "pepa", "role": "staff"}, {"id": "roberto", "role": "staff"}],
               "humans": [{"id": "salvador", "counterpart_persona": "paco"},
                          {"id": "brigitte", "counterpart_persona": "pepa"},
                          {"id": "fran", "counterpart_persona": "roberto"}, {"id": "beatriz"}, {"id": "custodian"}],
               "policies": {"access_levels": {"level-3": {"categories": [1, 2, 3]}, "level-2": {"categories": [1, 2]}},
                            "security_categories": {"category-0": {"owner": "custodian"}, "category-1": {}, "category-2": {}, "category-3": {}}}}
        scope = Scope.from_org(org)
        self.assertEqual(scope.human_grants("salvador")["categories"], ["category-1", "category-2", "category-3"])
        self.assertEqual(scope.human_grants("fran"), scope.human_grants("brigitte"))
        self.assertIsNone(scope.human_grants("beatriz"))
        self.assertFalse(scope.can_issue("beatriz", "paco"))
        org["policies"]["access_levels"]["level-2"]["categories"] = [1]
        revised = Scope.from_org(org)
        self.assertEqual(revised.human_grants("fran")["categories"], ["category-1"])
        self.assertNotEqual(scope.revision, revised.revision)
        org["humans"][3]["counterpart_persona"] = "paco"
        with self.assertRaises(ValueError):
            Scope.from_org(org)
        org["humans"][3]["counterpart_persona"] = "missing"
        with self.assertRaises(ValueError):
            Scope.from_org(org)

    def test_category_zero_is_a_human_assignment_independent_of_persona_binding(self):
        org = {"organization": {"id": "example"},
               "roles": [{"id": "ceo", "access_level": "executive"},
                         {"id": "staff", "access_level": "operational", "security_exceptions": ["category-3", "category-4"]}],
               "actors": [{"id": "paco", "role": "ceo", "actor_exceptions": ["category-0"]},
                          {"id": "pepa", "role": "staff"}],
               "humans": [{"id": "salvador", "name": "Salvador", "counterpart_persona": "paco"},
                          {"id": "brigitte", "counterpart_persona": "pepa"}],
               "policies": {"access_levels": {"executive": {"categories": [1, 2, 3]}, "operational": {"categories": [1, 2]}},
                            "security_categories": {"category-0": {"scope": "actor", "owner": "Salvador"},
                                                    "category-1": {}, "category-2": {}, "category-3": {},
                                                    "category-4": {}, "category-4-project": {}}}}
        scope = Scope.from_org(org)
        resource = {"organization": "example", "category": "category-4-project", "project": "any-project", "secret": False}
        self.assertTrue(scope.permits("salvador", "paco", resource))
        self.assertTrue(scope.permits("salvador", "paco", {**resource, "category": "category-0"}))
        self.assertFalse(scope.permits("brigitte", "paco", resource))
        self.assertFalse(scope.permits("brigitte", "pepa", resource))
        self.assertFalse(scope.permits("salvador", "paco", {**resource, "organization": "other"}))
        self.assertFalse(scope.permits("salvador", "paco", {**resource, "secret": True}))
        self.assertFalse(scope.permits("salvador", "paco", {**resource, "category": "undeclared"}))
        self.assertIn("category-3", scope.human_grants("brigitte")["categories"])
        self.assertIn("category-4", scope.human_grants("brigitte")["categories"])
        del org["humans"][0]["counterpart_persona"]
        self.assertTrue(Scope.from_org(org).permits("salvador", "paco", resource))
        self.assertTrue(Scope.from_org(org).permits("salvador", "pepa", resource))
        self.assertFalse(Scope.from_org(org).can_issue("salvador", "unknown-persona"))
        org["humans"][0]["counterpart_persona"] = "paco"
        org["actors"][0]["actor_exceptions"] = []
        org["roles"][0]["security_exceptions"] = ["category-0"]
        self.assertTrue(Scope.from_org(org).permits("salvador", "paco", resource))
        self.assertFalse(Scope.from_org(org).permits("brigitte", "pepa", {**resource, "category": "category-0"}))
        org["policies"]["security_categories"]["category-0"]["owner"] = "brigitte"
        del org["humans"][1]["counterpart_persona"]
        reassigned = Scope.from_org(org, default_persona="paco")
        self.assertTrue(reassigned.permits("brigitte", "paco", resource))
        self.assertFalse(reassigned.permits("salvador", "paco", resource))
        self.assertNotEqual(scope.revision, reassigned.revision)
        org["actors"][0]["actor_exceptions"] = ["category-0"]
        org["policies"]["security_categories"]["category-0"]["owner"] = "unknown"
        with self.assertRaises(ValueError):
            Scope.from_org(org, default_persona="paco")
        del org["policies"]["security_categories"]["category-0"]["owner"]
        fallback = Scope.from_org(org, default_persona="paco")
        self.assertTrue(fallback.permits("salvador", "pepa", resource))
        with self.assertRaises(ValueError):
            Scope.from_org(org)
        del org["humans"][0]["counterpart_persona"]
        with self.assertRaises(ValueError):
            Scope.from_org(org, default_persona="paco")
        del org["policies"]["security_categories"]["category-0"]
        with self.assertRaises(ValueError):
            Scope.from_org(org, default_persona="paco")


if __name__ == "__main__":
    unittest.main()

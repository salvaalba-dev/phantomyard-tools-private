"""Private role briefing preview: authority reuse, deterministic output and inert metadata."""
import copy
import importlib.util
import unittest
from unittest.mock import patch

from role_briefing import MAX_INPUT_BYTES, prepare_briefing
from test_phantomorg_counterpart import organization

AVAILABLE = importlib.util.find_spec("phantomorg") is not None


def fixture():
    org = organization()
    org["humans"][0].pop("counterpart_persona")
    org["roles"][0]["security_exceptions"] = ["category-3"]
    org["actors"][0]["actor_exceptions"] = ["category-2"]
    return org


def metadata():
    return {"schema_version": 1, "organization_id": "example", "references": [
        {"document_id": "board-handbook", "applies_to": {"kind": "role", "id": "lead"},
         "version": "1.0", "category": "category-2", "owner": "owner"}]}


class PreviewBoundaryTests(unittest.TestCase):
    def test_invalid_or_unbounded_input_rejected_before_optional_dependency(self):
        for org, persona in (([], "coordinator"), ({}, ""), ({"large": "x" * MAX_INPUT_BYTES}, "coordinator")):
            with self.subTest(persona=persona), self.assertRaises(ValueError):
                prepare_briefing(org, persona)

    def test_missing_dependency_has_actionable_error(self):
        import builtins
        original = builtins.__import__

        def without_phantomorg(name, *args, **kwargs):
            if name.startswith("phantomorg"):
                raise ModuleNotFoundError("Optional dependency unavailable")
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=without_phantomorg):
            with self.assertRaisesRegex(ValueError, "compatible PhantomOrg package"):
                prepare_briefing({}, "coordinator")


@unittest.skipUnless(AVAILABLE, "Optional PhantomOrg package not installed")
class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.org = fixture()
        self.side = metadata()

    def test_unchanged_inputs_produce_identical_detached_output(self):
        original = copy.deepcopy([self.org, self.side])
        first = prepare_briefing(self.org, "coordinator", self.side)
        second = prepare_briefing(self.org, "coordinator", self.side)
        self.assertEqual(first, second)
        self.assertEqual(original, [self.org, self.side])
        self.assertEqual(first["status"], "private-preview")
        self.assertNotIn("resources", first)
        self.assertNotIn("generated_at", first)
        first["role"]["security_exceptions"].append("changed")
        first["document_references"][0]["version"] = "changed"
        self.assertEqual(second, prepare_briefing(self.org, "coordinator", self.side))

    def test_authoritative_access_keeps_base_and_both_exception_origins(self):
        result = prepare_briefing(self.org, "coordinator")
        self.assertEqual(result["access_description"]["categories"], [1, 2])
        self.assertEqual(result["access_description"]["role_exceptions"], ["category-3"])
        self.assertEqual(result["access_description"]["actor_exceptions"], ["category-2"])
        self.assertNotIn("absolute", result)
        self.assertEqual(result["reporting"]["counterpart_humans"], [])
        self.org["roles"][0]["reports_to_human"] = "member"
        self.assertEqual(prepare_briefing(self.org, "coordinator")["reporting"]["counterpart_humans"], [])

    def test_duplicate_or_missing_org_references_and_unknown_persona_fail(self):
        for change in ("duplicate", "role", "level"):
            org = copy.deepcopy(self.org)
            if change == "duplicate":
                org["actors"].append(copy.deepcopy(org["actors"][0]))
            elif change == "role":
                org["actors"][0]["role"] = "missing"
            else:
                org["roles"][0]["access_level"] = "missing"
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_briefing(org, "coordinator")
        with self.assertRaises(ValueError):
            prepare_briefing(self.org, "missing")

    def test_supplemental_metadata_cannot_override_grants_or_foreign_org(self):
        for field, value in (("organization_id", "foreign"), ("policies", {}), ("assistant", "other")):
            side = copy.deepcopy(self.side)
            side[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                prepare_briefing(self.org, "coordinator", side)

    def test_invalid_document_references_fail_closed(self):
        for field, value in (("document_id", "../outside"), ("category", "category-0"),
                             ("category", "unknown"), ("owner", "missing"),
                             ("applies_to", {"kind": "role", "id": "missing"}),
                             ("applies_to", {"kind": "persona", "id": "coordinator"}),
                             ("path", "/private/file")):
            side = copy.deepcopy(self.side)
            side["references"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                prepare_briefing(self.org, "coordinator", side)
        self.side["references"].append(copy.deepcopy(self.side["references"][0]))
        with self.assertRaises(ValueError):
            prepare_briefing(self.org, "coordinator", self.side)

    def test_only_matching_org_department_and_role_references_selected(self):
        self.org["roles"].append({"id": "observer", "name": "Observer", "department": "board",
                                  "reports_to": "lead", "access_level": "executive"})
        self.org["actors"].append({"id": "reviewer", "role": "observer", "tools": []})
        base = self.side["references"][0]
        self.side["references"] += [base | {"document_id": "org-policy", "applies_to": {"kind": "organization", "id": "example"}},
                                    base | {"document_id": "department-policy", "applies_to": {"kind": "department", "id": "board"}},
                                    base | {"document_id": "other-role-policy", "applies_to": {"kind": "role", "id": "observer"}}]
        result = prepare_briefing(self.org, "coordinator", self.side)
        self.assertEqual({row["document_id"] for row in result["document_references"]},
                         {"board-handbook", "org-policy", "department-policy"})
        self.assertEqual(result["reporting"]["subordinate_roles"], ["observer"])

    def test_unclassified_reference_is_retained_only_as_inert_private_metadata(self):
        self.side["references"][0]["category"] = None
        self.side["references"][0]["owner"] = None
        result = prepare_briefing(self.org, "coordinator", self.side)
        self.assertIsNone(result["document_references"][0]["category"])
        self.assertNotIn("authorized", result)
        self.assertNotIn("catalog", result)

    def test_source_or_supplemental_change_invalidates_revision(self):
        first = prepare_briefing(self.org, "coordinator", self.side)
        self.side["references"][0]["version"] = "2.0"
        second = prepare_briefing(self.org, "coordinator", self.side)
        self.assertNotEqual(first["revision"], second["revision"])
        self.assertEqual(first["provenance"]["organization_revision"], second["provenance"]["organization_revision"])
        self.org["roles"][0]["functions"] = ["coordination"]
        third = prepare_briefing(self.org, "coordinator", self.side)
        self.assertNotEqual(second["revision"], third["revision"])

    def test_explicit_counterpart_and_escalations_are_descriptive(self):
        from phantomorg.spec.model import Human
        if "counterpart_persona" not in Human.__dataclass_fields__:
            self.skipTest("Counterpart proposal not loaded")
        self.org["humans"][0]["counterpart_persona"] = "coordinator"
        self.org["roles"].append({"id": "support", "name": "Support", "department": "board",
                                  "reports_to": "lead", "access_level": "executive"})
        self.org["escalation_matrix"] = [{"from": "support", "to": "lead", "condition": "Blocked"},
                                          {"from": "*", "to": "lead", "condition": "Exception"}]
        result = prepare_briefing(self.org, "coordinator")
        self.assertEqual(result["reporting"]["counterpart_humans"], ["member"])
        self.assertEqual(len(result["escalation"]["incoming"]), 2)
        self.assertEqual(len(result["escalation"]["wildcard"]), 1)
        self.assertNotIn("session", result)


if __name__ == "__main__":
    unittest.main()

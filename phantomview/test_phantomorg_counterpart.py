"""Optional minimal PhantomOrg proposal: schema, compiler and viewer compatibility."""
import copy
import json
from pathlib import Path
import unittest

try:
    import phantomorg
    from phantomorg.compiler.humans import render_humans
    from phantomorg.spec.model import Human, OrgSpec
    from phantomorg.spec.shape_validator import ShapeError, validate_shape
    from phantomorg.validator.refs import check_references
    AVAILABLE = "counterpart_persona" in Human.__dataclass_fields__
except ImportError:
    AVAILABLE = False

from channel_identity import HumanDirectory


def organization():
    return {
        "version": 1,
        "organization": {"id": "example", "name": "Example Organization",
                         "sector": "ngo", "languages": ["en"]},
        "departments": [{"id": "board", "name": "Board", "parent": None,
                         "access_policy": "executive"}],
        "roles": [{"id": "lead", "name": "Lead", "department": "board",
                   "reports_to": None, "reports_to_human": "Board Member",
                   "access_level": "executive"}],
        "actors": [{"id": "coordinator", "role": "lead", "tools": []}],
        "humans": [{"id": "member", "name": "Board Member", "telegram_user_id": 101,
                    "counterpart_persona": "coordinator"},
                   {"id": "owner", "email": "owner@example.org"}],
        "policies": {"access_levels": {"executive": {"label": "Executive", "categories": [1, 2]}},
                     "security_categories": {"category-0": {"label": "Absolute access", "owner": "owner"},
                                             "category-1": {"label": "Internal"},
                                             "category-2": {"label": "Confidential"},
                                             "category-3": {"label": "Restricted"}}},
        "escalation_matrix": [],
        "communication": {"request_id_format": "{org_id}-{seq4}", "message_types": ["REQUEST"], "max_hops": 3},
    }


@unittest.skipUnless(AVAILABLE, "Minimal PhantomOrg counterpart proposal not available")
class CounterpartTests(unittest.TestCase):
    def setUp(self):
        self.org = organization()

    def validate(self, org):
        import jsonschema
        schema = json.loads((Path(phantomorg.__file__).parent / "spec/schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(org, schema)
        validate_shape(org)
        return OrgSpec.from_dict(org)

    def test_optional_mapping_survives_model_and_registry(self):
        model = self.validate(self.org)
        self.assertEqual(check_references(model), [])
        self.assertEqual(model.humans[0].counterpart_persona, "coordinator")
        self.assertIsNone(model.humans[1].counterpart_persona)
        registry = render_humans(model)
        self.assertIn("counterpart_persona |", registry)
        self.assertIn("`coordinator` |", registry)
        self.assertEqual(len(registry.splitlines()[-1].split("|")), 9)

    def test_legacy_registry_is_byte_identical_and_has_no_inferred_mapping(self):
        self.org["humans"][0].pop("counterpart_persona")
        model = self.validate(self.org)
        self.assertIsNone(model.humans[0].counterpart_persona)
        expected = (
            "# Human Registry — Example Organization\n\nOrganization: `example`\n\n"
            "Humans are external counterparts (not personas). Telegram user ids, "
            "Nostr npubs and emails are filled in as they get registered\n\n"
            "| id | name | role | telegram_user_id | npub | email |\n"
            "|---|---|---|---|---|---|\n"
            "| `member` | Board Member | — | 101 | `—` | — |\n"
            "| `owner` | — | — | — | `—` | owner@example.org |\n"
        )
        self.assertEqual(render_humans(model).encode(), expected.encode())
        self.org.pop("humans")
        self.assertEqual(render_humans(self.validate(self.org)), "")

    def test_schema_and_shape_reject_invalid_present_mapping(self):
        import jsonschema
        schema = json.loads((Path(phantomorg.__file__).parent / "spec/schema.json").read_text(encoding="utf-8"))
        for value in (None, "", "../actor", "Actor", 3, True, [], {}):
            with self.subTest(value=value):
                self.org["humans"][0]["counterpart_persona"] = value
                with self.assertRaises(ShapeError):
                    validate_shape(self.org)
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(self.org, schema)

    def test_missing_and_duplicate_actor_references_rejected(self):
        self.org["humans"][0]["counterpart_persona"] = "missing"
        self.assertTrue(any("does not exist" in error for error in check_references(self.validate(self.org))))
        self.org["humans"][0]["counterpart_persona"] = "coordinator"
        self.org["humans"][1]["counterpart_persona"] = "coordinator"
        self.assertTrue(any("counterpart_persona" in error and ("duplicated" in error or "already assigned" in error)
                            for error in check_references(self.validate(self.org))))

    def test_viewer_derives_existing_access_and_keeps_absolute_owner_independent(self):
        original = copy.deepcopy(self.org["policies"])
        self.validate(self.org)
        directory = HumanDirectory(self.org)
        recipient = directory.resolve(channel="telegram", sender="101", persona="coordinator",
                                      direct=True, principal_authenticated=True)
        self.assertEqual(recipient.human, "member")
        resource = {"organization": "example", "category": "category-2", "secret": False}
        self.assertTrue(directory.permits(recipient, resource))
        self.assertFalse(directory.permits(recipient, resource | {"category": "category-3"}))
        self.assertFalse(directory.scope.is_absolute("member"))
        self.assertTrue(directory.scope.is_absolute("owner"))
        self.assertEqual(self.org["policies"], original)
        with self.assertRaises(ValueError):
            directory.resolve(channel="email", sender="owner@example.org", persona="coordinator",
                              direct=True, principal_authenticated=True)
        self.org["humans"][0].pop("counterpart_persona")
        with self.assertRaises(ValueError):
            HumanDirectory(self.org).resolve(channel="telegram", sender="101", persona="coordinator",
                                            direct=True, principal_authenticated=True)


if __name__ == "__main__":
    unittest.main()

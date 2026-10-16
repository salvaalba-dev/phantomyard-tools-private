"""Optional integration against the private PhantomOrg counterpart patch."""
from pathlib import Path
import tempfile
import unittest

import yaml

from channel_identity import HumanDirectory
from test_channel_identity import context, organization

try:
    from phantomorg.spec.model import Human, PhantomViewPolicy
    from phantomorg.validator import validate_org
    COMPATIBLE = hasattr(Human, "counterpart_persona") and 'scope_definitions' in PhantomViewPolicy.__dataclass_fields__
except ImportError:
    COMPATIBLE = False


@unittest.skipUnless(COMPATIBLE, "Install the private PhantomOrg counterpart patch for integration tests")
class PhantomOrgAccessTests(unittest.TestCase):
    def source(self):
        org = organization()
        org["version"] = 1
        org["organization"].update(name="Example Organization", sector="ngo", languages=["en"], display_name="Example NGO")
        org["departments"] = [{"id": "board", "name": "Board", "parent": None, "access_policy": "board"}]
        org["roles"][0].update(name="Executive", department="board", reports_to=None)
        for actor in org["actors"]:
            actor["tools"] = []
        org["policies"]["access_levels"]["board"]["label"] = "Board"
        for ident, category in org["policies"]["security_categories"].items():
            category["label"] = ident
        org["policies"]["phantomview"] = {}
        org["escalation_matrix"] = []
        org["communication"] = {"request_id_format": "ORG-ACTOR-SEQUENCE", "message_types": ["REQUEST"], "max_hops": 3}
        org["humans"][2].pop("telegram_user_id")
        org["humans"][2]["email"] = "accountant@example.org"
        return org

    def test_validated_source_preserves_matrix_and_email_only_human_stays_unverified(self):
        org = self.source()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "org.yaml"
            path.write_text(yaml.safe_dump(org), encoding="utf-8")
            model, result = validate_org(path)
            self.assertTrue(result.ok, result.errors)
        self.assertEqual(model.humans[2].counterpart_persona, "treasurer")
        directory = HumanDirectory(org)
        for sender, persona in (("101", "coordinator"), ("102", "administrator")):
            recipient = directory.resolve(**context(sender=sender, persona=persona))
            self.assertTrue(directory.permits(recipient, {"organization": "example", "category": "category-1", "secret": False}))
        with self.assertRaises(ValueError):
            directory.resolve(**context(sender="accountant@example.org", persona="treasurer", channel="email"))
        self.assertIsNone(model.humans[2].telegram_user_id)

    def test_model_and_runtime_reject_same_duplicate_counterpart(self):
        org = self.source()
        org["humans"][1]["counterpart_persona"] = "coordinator"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "org.yaml"
            path.write_text(yaml.safe_dump(org), encoding="utf-8")
            _, result = validate_org(path)
            self.assertTrue(any("already assigned" in error for error in result.errors))
        with self.assertRaises(ValueError):
            HumanDirectory(org)

    def test_scopes_and_actions_survive_model_validation_and_runtime_checks(self):
        org = self.source()
        org['policies']['phantomview'] = {
            'scope_definitions': {'example': {'kind': 'organization'},
                                  'river-project': {'kind': 'project', 'label': 'River Project'}},
            'project_grants': {'administrator': ['river-project']},
            'persona_scope_grants': {'administrator': ['river-project']},
            'human_action_grants': {'secretary': {'view.personal.edit': ['river-project']}},
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'org.yaml'
            path.write_text(yaml.safe_dump(org), encoding='utf-8')
            model, result = validate_org(path)
            self.assertTrue(result.ok, result.errors)
        self.assertEqual(model.policies.phantomview.scope_definitions['river-project'].kind, 'project')
        directory = HumanDirectory(org)
        recipient = directory.resolve(**context('102', 'administrator'), scope_id='river-project')
        self.assertTrue(directory.allows_action(recipient, 'view.personal.edit', 'river-project', owner='secretary'))
        self.assertFalse(directory.allows_action(recipient, 'view.shared.edit', 'river-project'))
        with self.assertRaises(ValueError):
            directory.resolve(**context('102', 'administrator'), scope_id='example')


if __name__ == "__main__":
    unittest.main()

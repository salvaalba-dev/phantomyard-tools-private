"""Source tolerance must not be confused with identified viewer activation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from channel_identity import HumanDirectory
import phantomview as pv
import test_setup_proposal


def proposed_organization():
    fixture = test_setup_proposal.SetupProposalTests()
    fixture.setUp()
    result = fixture.draft()['proposed_org']
    result.update(version=1, departments=[])
    return result


class SourceCompatibilityTests(unittest.TestCase):
    def test_yaml_and_json_loaders_preserve_private_declarations(self):
        org = proposed_organization()
        with tempfile.TemporaryDirectory() as directory:
            for name, content in (('org.yaml', yaml.safe_dump(org)),
                                  ('org.json', json.dumps(org))):
                with self.subTest(name=name):
                    source = Path(directory) / name
                    source.write_text(content, encoding='utf-8')
                    before = source.read_bytes()
                    loaded = pv.validate_org(pv.read_source(source))
                    self.assertEqual(loaded, org)
                    directory_policy = HumanDirectory(loaded)
                    self.assertTrue(directory_policy.scope.is_absolute('owner'))
                    self.assertEqual(directory_policy.scope.policy['humans']['secretary'],
                                     {'counterpart_persona': 'administrator'})
                    self.assertEqual(source.read_bytes(), before)

    def test_presentation_projection_is_not_an_authority_document(self):
        org = proposed_organization()
        original = copy.deepcopy(org)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'org.json'
            source.write_text(json.dumps(org), encoding='utf-8')
            before = source.read_bytes()
            observer = pv.Observatory(root / 'unused-config.json')
            observer.config = {
                'mode': 'existing', 'org_files': [str(source)], 'personas_dir': '',
                'persona_paths': {}, 'remote_personas': {}, 'installation_labels': {},
                'docs_manifests': [], 'auto_procedures': False,
            }
            original_open = Path.open
            reads = []

            def selected_only(path, *args, **kwargs):
                self.assertEqual(path, source)
                self.assertNotIn('w', args[0] if args else kwargs.get('mode', 'r'))
                reads.append(path)
                return original_open(path, *args, **kwargs)

            with patch.object(Path, 'open', selected_only):
                snapshot = observer.collect()
            self.assertEqual(reads, [source])
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(org, original)
            self.assertEqual(len(snapshot['actors']), len(org['actors']))
            self.assertEqual(len(snapshot['humans']), len(org['humans']))
            self.assertNotIn('policies', snapshot)
            for human in snapshot['humans']:
                self.assertEqual(set(human), {'id', 'org', 'name', 'role'})
                self.assertNotIn('counterpart_persona', human)
                self.assertNotIn('telegram_user_id', human)
            with self.assertRaises(ValueError):
                HumanDirectory(snapshot)


if __name__ == '__main__':
    unittest.main()

"""Explicit tool references stay bounded, persona-local and inert."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tool_files import collect, validated


class ToolFileTests(unittest.TestCase):
    def actor(self, root):
        return {'key': 'example:actors:coordinator', 'tools': ['email', 'drive'], 'profile_path': str(root)}

    def binding(self, files):
        return {'actor': 'example:actors:coordinator', 'tool': 'email', 'files': files}

    def test_records_file_presence_without_reading_or_running_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'tools').mkdir()
            (root / 'tools' / 'mail.py').write_text('raise RuntimeError("NEVER_EXECUTE")')
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('No contents')), patch.object(Path, 'read_text', side_effect=AssertionError('No contents')):
                result = collect({'persona_tool_files': [self.binding(['tools/mail.py', 'tools/missing.py'])]}, [self.actor(root)])
            self.assertEqual(result['example:actors:coordinator'], [
                {'tool': 'email', 'file': 'tools/mail.py', 'state': 'file'},
                {'tool': 'email', 'file': 'tools/missing.py', 'state': 'missing'}])

    def test_unconfigured_installations_remain_unchanged(self):
        self.assertEqual(collect({}, []), {})

    def test_collector_attaches_explicit_references_to_the_selected_persona(self):
        import json
        import phantomview as pv
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); profile = root / 'persona'; (profile / 'tools').mkdir(parents=True)
            (profile / 'tools' / 'mail.py').write_text('NEVER_COPY_OR_EXECUTE')
            manifest = root / 'installation.json'
            manifest.write_text(json.dumps({'version': 1, 'components': [], 'relations': [],
                'persona_tool_files': [{'actor': 'demo:actors:atlas', 'tool': 'email', 'files': ['tools/mail.py']}]}))
            observer = pv.Observatory(root / 'config.json')
            result = observer.configure(pv.default_config() | {'mode': 'existing',
                'persona_paths': {'demo:atlas': str(profile)}, 'installation_file': str(manifest)})
            self.assertIsNone(result['error'])
            actor = next(row for row in result['snapshot']['actors'] if row['id'] == 'atlas')
            self.assertEqual(actor['tool_files'], [{'tool': 'email', 'file': 'tools/mail.py', 'state': 'file'}])
            self.assertNotIn('NEVER_COPY_OR_EXECUTE', json.dumps(result))

    def test_rejects_cross_persona_undeclared_or_excluded_bindings(self):
        actor = self.actor('/unused')
        for changes in ({'actor': 'different:actors:coordinator'}, {'tool': 'calendar'}, {'actor': []}):
            with self.assertRaises(ValueError):
                collect({'persona_tool_files': [self.binding(['tools/mail.py']) | changes]}, [actor])
        with self.assertRaises(ValueError):
            collect({'persona_tool_files': [self.binding(['tools/mail.py'])]}, [actor | {'excluded': ['email']}])

    def test_rejects_paths_arguments_urls_secrets_and_duplicate_references(self):
        for filename in ('/etc/shadow', '../mail.py', 'tools/../mail.py', 'tools/mail.py --token secret',
                         'https://example.org/mail.py', 'tools\\mail.py', 'tools/credentials.json'):
            with self.assertRaises(ValueError):
                collect({'persona_tool_files': [self.binding([filename])]}, [self.actor('/unused')])
        with self.assertRaises(ValueError):
            collect({'persona_tool_files': [self.binding(['tools/mail.py', 'tools/mail.py'])]}, [self.actor('/unused')])
        for row in ({'tool': 'email', 'file': 'tools/mail.py', 'state': []},
                    {'tool': 'email', 'file': 'tools/mail.py', 'state': 'file', 'token': 'NEVER_COPY'}):
            with self.assertRaises(ValueError):
                validated([row], ['email'])

    def test_symbolic_link_is_reported_without_following_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'tools').mkdir()
            try:
                (root / 'tools' / 'mail.py').symlink_to(root / 'missing-target.py')
            except OSError:
                self.skipTest('Symbolic links unavailable')
            result = collect({'persona_tool_files': [self.binding(['tools/mail.py'])]}, [self.actor(root)])
            self.assertEqual(result['example:actors:coordinator'][0]['state'], 'symlink')

    def test_export_requires_opt_in_and_preserves_persona_classification_boundary(self):
        from channel_identity import HumanDirectory
        from source_adapter import prepare
        from test_source_adapter import snapshot
        from test_view_permissions import scoped_organization
        source = snapshot(); actor = source['actors'][0]
        actor['tool_files'] = [{'tool': 'email', 'file': 'tools/mail.py', 'state': 'file'}]
        directory = HumanDirectory(scoped_organization())
        plain = prepare(source, directory)
        enriched = prepare(source, directory, profile_fields=True)
        plain_persona = next(row for row in plain['records'] if row['kind'] == 'persona')
        persona = next(row for row in enriched['records'] if row['kind'] == 'persona')
        self.assertNotIn('tool_files', plain_persona['data'])
        self.assertEqual(persona['data']['tool_files'], actor['tool_files'])
        self.assertEqual(plain_persona['id'], persona['id'])
        review = next(row for row in enriched['resources'] if row['id'] == persona['id'])
        self.assertIsNone(review['category']); self.assertIsNone(review['scope'])

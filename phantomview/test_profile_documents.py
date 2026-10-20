"""Profile collection is bounded, opt-in and separately reviewed before display."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from channel_identity import HumanDirectory
from profile_documents import MAX_BYTES, collect, validate_document
from projection_review import approve
from resource_review import revision
from source_adapter import prepare, prepare_like
from test_source_adapter import snapshot
from test_view_permissions import scoped_organization


def document(name='IDENTITY.md', content='A helpful coordinator.'):
    return {'name': name, 'content': content, 'sha256': hashlib.sha256(content.encode()).hexdigest()}


class ProfileDocumentTests(unittest.TestCase):
    def test_exact_files_only_and_source_exclusions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('IDENTITY.md', 'SOUL.md', 'MEMORY.md', 'tools.md', 'applied.md'):
                (root / name).write_text('Profile text', encoding='utf-8')
                (root / name).chmod(0o600)
            self.assertEqual({r['name'] for r in collect(root, lambda _: True)}, {'IDENTITY.md', 'SOUL.md'})
            self.assertEqual(collect(root, lambda _: False), [])
            (root / 'IDENTITY.md').write_text('password: PRIVATE_SENTINEL', encoding='utf-8')
            (root / 'SOUL.md').write_bytes(b'x' * (MAX_BYTES + 1))
            self.assertEqual(collect(root, lambda _: True), [])

    @unittest.skipUnless(os.name == 'posix', 'POSIX links and modes')
    def test_links_and_world_writable_sources_are_not_exported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            hidden = root / 'MEMORY.md'
            hidden.write_text('Private memory', encoding='utf-8')
            (root / 'IDENTITY.md').symlink_to(hidden)
            soul = root / 'SOUL.md'
            soul.write_text('Mutable profile', encoding='utf-8')
            soul.chmod(0o664)
            self.assertEqual([r['name'] for r in collect(root, lambda _: True)], ['SOUL.md'])
            soul.chmod(0o666)
            self.assertEqual(collect(root, lambda _: True), [])

    def test_collector_collection_is_explicit_and_memory_stays_unread(self):
        import phantomview as pv
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            persona = root / 'personas' / 'atlas'
            persona.mkdir(parents=True)
            for name in ('IDENTITY.md', 'SOUL.md', 'MEMORY.md'):
                (persona / name).write_text('PRIVATE_MEMORY' if name == 'MEMORY.md' else 'Profile text', encoding='utf-8')
                (persona / name).chmod(0o600)
            org = root / 'org.json'
            pv.atomic_json(org, pv.read_source(pv.HERE / 'example-org.yaml'))
            observer = pv.Observatory(root / 'config.json')
            config = pv.default_config() | {'mode': 'existing', 'org_files': [str(org)], 'personas_dir': str(persona.parent)}
            observer.configure(config)
            self.assertTrue(all('profile_documents' not in a for a in observer.snapshot['actors']))
            observer.configure(config | {'profile_documents': True})
            atlas = next(a for a in observer.snapshot['actors'] if a['id'] == 'atlas')
            self.assertEqual(len(atlas['profile_documents']), 2)
            self.assertNotIn('PRIVATE_MEMORY', json.dumps(observer.snapshot))
            with self.assertRaises(ValueError):
                observer.validate_config(config | {'profile_documents': 'yes'})

    def test_payload_name_digest_and_credential_checks(self):
        for value in (document('MEMORY.md'), document(content='-----BEGIN PRIVATE KEY-----'),
                      document() | {'sha256': '0' * 64}, document() | {'path': '/private/source'},
                      document(content='')):
            with self.assertRaises(ValueError):
                validate_document(value)

    def test_default_mode_unchanged_and_document_changes_are_bound(self):
        source, org = snapshot(), scoped_organization()
        directory = HumanDirectory(org)
        original = prepare(source, directory)
        source['actors'][0]['profile_documents'] = [document()]
        self.assertEqual(prepare(source, directory), original)
        draft = prepare(source, directory, profile_documents=True)
        documents = [r for r in draft['records'] if r['data'].get('source') == 'reviewed-profile']
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]['data']['content'], document()['content'])
        self.assertNotIn('/private/', json.dumps(documents))
        self.assertEqual(prepare_like(source, directory, draft), draft)
        changed = copy.deepcopy(source)
        changed['actors'][0]['profile_documents'] = [document(content='Changed profile')]
        self.assertNotEqual(prepare_like(changed, directory, draft), draft)
        with self.assertRaises(ValueError):
            prepare_like(source, directory, draft | {'profile_documents': False})

    def test_document_and_relationship_need_independent_acl_decisions(self):
        source, org = snapshot(), scoped_organization()
        source['actors'][0]['profile_documents'] = [document()]
        directory = HumanDirectory(org)
        draft = prepare(source, directory, profile_documents=True)
        decisions = {'schema_version': 1, 'draft_revision': revision(draft),
            'organization_revision': revision(org), 'resources': [
                {k: r[k] for k in ('id', 'payload_sha256')} | {'category': 'category-3',
                 'scope': {'kind': 'organization', 'id': 'example'}, 'project': None, 'secret': False}
                for r in draft['resources']]}
        bundle = approve(draft, decisions, org, lambda: source, reviewer=next(iter(directory.scope.policy['humans'])))
        self.assertTrue(bundle['profile_documents'])
        source['actors'][0]['profile_documents'] = [document(content='Changed after review')]
        with self.assertRaises(ValueError):
            approve(draft, decisions, org, lambda: source, reviewer=bundle['reviewer'])

    def test_profile_export_requires_explicit_searchable_actor(self):
        for value in (None, False, 1, 'true'):
            source = snapshot()
            actor = source['actors'][0]
            actor['profile_documents'] = [document()]
            if value is None:
                actor.pop('searchable', None)
            else:
                actor['searchable'] = value
            draft = prepare(source, HumanDirectory(scoped_organization()), profile_documents=True)
            self.assertFalse(any(row['data'].get('source') == 'reviewed-profile'
                                 for row in draft['records']))


if __name__ == '__main__':
    unittest.main()

"""Workspace plans contain only explicit model configuration and selected text."""
import tomllib
import unittest
from unittest.mock import patch

from worker_workspace import WorkerWorkspace


def workspace(root='/srv/example-worker', **changes):
    return WorkerWorkspace(**({'root': root, 'persona': 'guide', 'worker_uid': 29002,
        'worker_gid': 29002, 'provider': 'openrouter', 'model': 'example/model',
        'judge_provider': 'typesafe', 'judge_model': 'example/judge',
        'profile': {'BOOT.md': 'Explain the selected project.'}} | changes))


class WorkerWorkspaceTests(unittest.TestCase):
    def test_generated_config_has_no_channels_and_pins_model_screen_and_memory(self):
        plan = workspace()
        config = tomllib.loads(plan.files()['config/config.toml'].decode())
        self.assertEqual(config['harnesses']['chain'], ['native'])
        self.assertEqual(config['harnesses']['pi']['routing']['primary_model'], 'example/model')
        self.assertTrue(config['jev']['judge']['enabled'])
        self.assertFalse(config['jev']['router']['enabled'])
        self.assertEqual(config['memory_db'], '/srv/example-worker/data/memory.sqlite')
        self.assertEqual(config['personas_dir'], '/srv/example-worker/profiles')
        self.assertNotIn('channels', config)
        self.assertNotIn('api_key', config['jev'])
        self.assertEqual(config['autostart_personas'], [])

    def test_every_location_uses_the_dedicated_root_and_home(self):
        plan = workspace()
        self.assertTrue(all(value.startswith(plan.root + '/') for value in plan.launch_environment().values()))
        self.assertEqual(plan.directories()['data'], (29002, 29002, 0o700))
        self.assertEqual(plan.directories()['profiles/guide'], (0, 29002, 0o750))

    def test_secret_identity_vault_and_arbitrary_files_are_never_projected(self):
        for name in ('identity.json', 'vault.sqlite', 'phantomchat.json', 'config.toml',
                     '../BOOT.md', 'kb/private.md', '.env'):
            with self.assertRaises(ValueError):
                workspace(profile={'BOOT.md': 'Selected text', name: 'PRIVATE_SENTINEL'})

    def test_unknown_endpoints_injected_models_and_unsafe_bindings_fail(self):
        for changes in ({'root': '/'}, {'root': '//shared/worker'}, {'root': '/worker/../issuer'},
                        {'root': '/worker/'}, {'persona': '../issuer'}, {'worker_uid': 0},
                        {'worker_gid': True}, {'provider': 'custom-endpoint'},
                        {'model': 'model\n[channels]'}, {'judge_provider': 'other'},
                        {'profile': {}}, {'profile': {'BOOT.md': '\ud800'}}):
            with self.assertRaises(ValueError):
                workspace(**changes)

    def test_profile_snapshot_is_immutable_and_repr_does_not_disclose_it(self):
        profile = {'BOOT.md': 'PRIVATE_SENTINEL'}
        plan = workspace(profile=profile)
        profile.clear()
        self.assertEqual(plan.files()['profiles/guide/BOOT.md'], b'PRIVATE_SENTINEL')
        self.assertNotIn('PRIVATE_SENTINEL', repr(plan))
        with self.assertRaises(TypeError):
            plan.profile['BOOT.md'] = 'changed'

    def test_verification_is_linux_worker_only_and_does_not_provision(self):
        with patch('worker_workspace.sys.platform', 'win32'):
            with self.assertRaises(ValueError):
                workspace().verify()


if __name__ == '__main__':
    unittest.main()

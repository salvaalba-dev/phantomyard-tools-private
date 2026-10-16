"""Reject channel credentials and launch injection before native execution."""
import unittest

from worker_environment import UNAVAILABLE, environment, model_credentials


class WorkerEnvironmentTests(unittest.TestCase):
    def test_explicit_model_credentials_are_copied_without_ambient_reads(self):
        selection = {'PHANTOMBOT_PI_API_KEY': 'synthetic-model-key',
                     'PHANTOMBOT_JEV_API_KEY': 'synthetic-screen-key'}
        result = model_credentials(selection)
        selection.clear()
        self.assertEqual(result['PHANTOMBOT_PI_API_KEY'], 'synthetic-model-key')
        self.assertEqual(len(result), 2)

    def test_mixed_or_unknown_credential_maps_are_rejected_without_disclosure(self):
        for key in ('TELEGRAM_BOT_TOKEN', 'NOSTR_NSEC', 'PHANTOMBOT_PI_API_KEY_OTHER',
                    'PHANTOMVIEW_ISSUER_TOKEN', 'authorization', 'OPENROUTER_API_KEY'):
            with self.assertRaisesRegex(ValueError, '^' + UNAVAILABLE + '$'):
                model_credentials({'PHANTOMBOT_PI_API_KEY': 'synthetic-model-key',
                                   key: 'PRIVATE_SENTINEL'})

    def test_loader_and_transport_injection_variables_are_rejected(self):
        for key in ('NODE_OPTIONS', 'BUN_OPTIONS', 'LD_PRELOAD', 'PYTHONPATH',
                    'HTTPS_PROXY', 'TELEGRAM_BOT_TOKEN', 'PHANTOMBOT_JEV_BASE_URL',
                    'PHANTOMBOT_JEV_KEY_ENV', 'PHANTOMBOT_AUTOSTART_PERSONAS'):
            with self.assertRaisesRegex(ValueError, '^' + UNAVAILABLE + '$'):
                environment({key: 'PRIVATE_SENTINEL'})

    def test_locations_and_search_path_cannot_fall_back_to_current_directory(self):
        for key, value in (('HOME', ''), ('HOME', 'relative'), ('HOME', '//shared/home'),
                           ('XDG_DATA_HOME', '/worker/../issuer'), ('PATH', '/usr/bin:'),
                           ('PATH', '.:/usr/bin'), ('PATH', '/bin\n/tmp'),
                           ('PHANTOMBOT_CONFIG', '/worker\\issuer')):
            with self.assertRaises(ValueError):
                environment({key: value})

    def test_snapshot_is_immutable_and_does_not_follow_caller_mutation(self):
        values = {'HOME': '/worker/home', 'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}
        result = environment(values)
        values['HOME'] = '/issuer'
        self.assertEqual(result['HOME'], '/worker/home')
        with self.assertRaises(TypeError):
            result['HOME'] = '/issuer'

    def test_bounded_utf8_and_single_line_credentials(self):
        for value in ('', ' padded ', 'line\nbreak', 'line\rbreak', '\0', '\ud800', '\U0001f600' * 17000):
            with self.assertRaises(ValueError):
                environment({'PHANTOMBOT_PI_API_KEY': value})

    def test_unsupported_locales_and_non_string_values_fail_closed(self):
        for values in ({'LANG': 'other'}, {'LC_ALL': ''}, {'HOME': None}, [], {1: 'value'}):
            with self.assertRaises(ValueError):
                environment(values)


if __name__ == '__main__':
    unittest.main()

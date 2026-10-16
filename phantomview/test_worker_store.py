"""Synthetic private documents and fail-closed worker credential loading."""
import json
import unittest
from unittest.mock import patch

from worker_store import MAX_BYTES, UNAVAILABLE, decode_credentials, encode_credentials, load_credentials


class WorkerStoreTests(unittest.TestCase):
    def setUp(self):
        self.options = {'persona': 'guide', 'worker_uid': 29002}
        self.values = {'PHANTOMBOT_PI_API_KEY': 'MODEL_SENTINEL'}
        self.raw = encode_credentials(credentials=self.values, **self.options)

    def test_explicit_selection_round_trip_has_no_other_fields(self):
        self.assertEqual(decode_credentials(self.raw, **self.options), self.values)
        self.assertEqual(set(json.loads(self.raw)), {'schema_version', 'persona', 'worker_uid', 'credentials'})

    def test_wrong_binding_unknown_fields_and_type_coercion_fail(self):
        original = json.loads(self.raw)
        for changes in ({'persona': 'other'}, {'worker_uid': 1}, {'worker_uid': True},
                        {'schema_version': True}, {'schema_version': 2}, {'token': 'PRIVATE_SENTINEL'},
                        {'credentials': {}}, {'credentials': {'TELEGRAM_BOT_TOKEN': 'PRIVATE_SENTINEL'}}):
            raw = json.dumps(original | changes).encode()
            with self.assertRaisesRegex(ValueError, '^' + UNAVAILABLE + '$'):
                decode_credentials(raw, **self.options)

    def test_duplicate_fields_malformed_utf8_and_large_documents_fail(self):
        for raw in (self.raw.replace(b'"persona":"guide"', b'"persona":"guide","persona":"guide"'),
                    self.raw.replace(b'"MODEL_SENTINEL"', b'"MODEL_SENTINEL","PHANTOMBOT_PI_API_KEY":"other"'),
                    b'\xff', b'[]', b'null', b'{', b'x' * (MAX_BYTES + 1), b'[' * 2000):
            with self.assertRaisesRegex(ValueError, '^' + UNAVAILABLE + '$'):
                decode_credentials(raw, **self.options)

    def test_encoder_refuses_mixed_empty_or_unbound_selections(self):
        for values in ({}, {'NOSTR_NSEC': 'PRIVATE_SENTINEL'},
                       self.values | {'TELEGRAM_BOT_TOKEN': 'PRIVATE_SENTINEL'}):
            with self.assertRaisesRegex(ValueError, '^' + UNAVAILABLE + '$'):
                encode_credentials(credentials=values, **self.options)
        for options in ({'persona': '../issuer', 'worker_uid': 29002},
                        {'persona': 'guide', 'worker_uid': 0},
                        {'persona': 'guide', 'worker_uid': True}):
            with self.assertRaises(ValueError):
                encode_credentials(credentials=self.values, **options)

    def test_unbound_or_non_linux_loader_never_opens_a_path(self):
        with patch('worker_store.sys.platform', 'win32'), patch('worker_store.os.open') as opened:
            with self.assertRaisesRegex(ValueError, '^' + UNAVAILABLE + '$'):
                load_credentials('/protected/model.json', **self.options)
            opened.assert_not_called()

    def test_unsafe_paths_fail_before_open(self):
        with patch('worker_store.sys.platform', 'linux'), \
                patch('worker_store.os.getuid', return_value=29002, create=True), \
                patch('worker_store.os.geteuid', return_value=29002, create=True), \
                patch('worker_store.os.getegid', return_value=29002, create=True), \
                patch('worker_store.os.getgroups', return_value=[], create=True), \
                patch('worker_store.os.open') as opened:
            for path in ('relative', '//remote/file', '/store/../issuer', '/store//key',
                         '/store/./key', '/store/key\0', '/store/key\\other'):
                with self.assertRaises(ValueError):
                    load_credentials(path, **self.options)
            opened.assert_not_called()


if __name__ == '__main__':
    unittest.main()

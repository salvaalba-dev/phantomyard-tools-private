import io
import json
import os
import stat
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from bot_version import Monitor


class VersionTests(unittest.TestCase):
    def setUp(self):
        # The runner's Python can be user-owned. Model the production binary's
        # trusted metadata explicitly instead of assuming the test host is root.
        metadata = SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o755)
        stat_patch = patch('bot_version.Path.stat', return_value=metadata)
        stat_patch.start()
        self.addCleanup(stat_patch.stop)

    def test_refresh_after_external_update_and_bound_network_checks(self):
        with patch('bot_version.subprocess.run') as run, patch('bot_version.urlopen') as remote, patch('bot_version.time.monotonic') as clock:
            run.return_value = subprocess.CompletedProcess([], 0, '1.1.433\n', '')
            remote.side_effect = lambda *a, **k: io.BytesIO(json.dumps({'tag_name':'v1.1.434','draft':False,'prerelease':False}).encode())
            clock.return_value=0
            monitor=Monitor({'executable':sys.executable,'shared':True})
            first=monitor.status()
            self.assertTrue(first['update_available'])
            self.assertEqual(first['scope'],'shared')
            self.assertEqual(run.call_args.args[0],[sys.executable,'--version'])
            self.assertNotIn('--force',first['command'])
            run.return_value = subprocess.CompletedProcess([], 0, '1.1.434\n', '')
            clock.return_value=16
            self.assertEqual(monitor.status()['status'],'current')
            self.assertEqual(remote.call_count,1)
            monitor.status(force=True)
            self.assertEqual(remote.call_count,1)
            clock.return_value=61
            monitor.status(force=True)
            self.assertEqual(remote.call_count,2)

    def test_remote_failure_is_not_up_to_date(self):
        with patch('bot_version.subprocess.run',return_value=subprocess.CompletedProcess([],0,'1.1.433','')),patch('bot_version.urlopen',side_effect=OSError):
            result=Monitor({'executable':sys.executable}).status()
            self.assertEqual(result['status'],'unknown')
            self.assertFalse(result['update_available'])

    def test_untrusted_release_and_local_output_are_rejected(self):
        with patch('bot_version.subprocess.run',return_value=subprocess.CompletedProcess([],0,'1.1.433;bad','')),patch('bot_version.urlopen',return_value=io.BytesIO(b'{"tag_name":"v1.2.3;bad"}')):
            result=Monitor({'executable':sys.executable}).status()
            self.assertEqual(result['status'],'unknown')
            self.assertEqual(result['installed'],'')
            self.assertEqual(result['available'],'')


class ExecutableTrustTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX executable ownership policy')
    def test_user_owned_and_group_or_world_writable_binaries_are_rejected(self):
        for uid, mode in ((1000, 0o755), (0, 0o775), (0, 0o757)):
            metadata = SimpleNamespace(st_uid=uid, st_mode=stat.S_IFREG | mode)
            with self.subTest(uid=uid, mode=mode), patch('bot_version.Path.stat', return_value=metadata):
                with self.assertRaisesRegex(ValueError, 'root-owned'):
                    Monitor({'executable': sys.executable})


if __name__=='__main__':unittest.main()

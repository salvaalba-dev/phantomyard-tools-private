import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
from bot_version import Monitor


class VersionTests(unittest.TestCase):
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


if __name__=='__main__':unittest.main()

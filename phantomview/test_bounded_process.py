"""Real disposable Linux children; no provider, channel or production process."""
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

from bounded_process import run


@unittest.skipUnless(sys.platform == 'linux', 'Linux process-group lifecycle required')
class BoundedProcessTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def execute(self, source, payload=b'', *, cancelled=lambda: False, seconds=2, **kwargs):
        return run(['/usr/bin/python3', '-c', source], payload, cwd=self.root,
                   deadline=time.monotonic() + seconds, cancelled=cancelled, **kwargs)

    def test_complete_stdin_stdout_and_explicit_environment(self):
        source = 'import os,sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data); sys.stderr.write("discard")'
        self.assertEqual(self.execute(source, b'Question', environment={}), b'Question')
        self.assertEqual(self.execute('import os; print(os.environ.get("SYNTHETIC_PARENT", "absent"))',
                                     environment={}), b'absent\n')

    def test_pre_cancel_never_launches_process(self):
        popen = Mock()
        with self.assertRaises(RuntimeError):
            self.execute('raise AssertionError()', cancelled=lambda: True, popen=popen)
        popen.assert_not_called()

    def test_private_files_use_child_only_restrictive_umask(self):
        source = ('import os,stat; open("memory.sqlite","w").close(); '
                  'print(oct(stat.S_IMODE(os.stat("memory.sqlite").st_mode)))')
        self.assertEqual(self.execute(source, private_files=True), b'0o600\n')

    def test_cancel_kills_ignoring_child_even_when_stdin_is_not_consumed(self):
        ready = self.root / 'ready'
        created = []

        def launch(*args, **kwargs):
            process = subprocess.Popen(*args, **kwargs)
            created.append(process)
            return process

        with self.assertRaises(RuntimeError):
            self.execute('import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                         'open("ready","w").close(); time.sleep(20)',
                         b'x' * 65536, cancelled=ready.exists, popen=launch)
        self.assertIsNotNone(created[0].returncode)
        self.assertEqual(created[0].returncode, -signal.SIGKILL)
        self.assertTrue(all(pipe.closed for pipe in (created[0].stdin, created[0].stdout, created[0].stderr)))

    def test_output_overflow_terminates_without_waiting_for_turn_deadline(self):
        start = time.monotonic()
        with self.assertRaises(RuntimeError):
            self.execute('import signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                         'sys.stdout.write("x"*65000); sys.stdout.flush(); time.sleep(20)', output_limit=32)
        self.assertLess(time.monotonic() - start, 1.8)

    def test_closed_pipes_do_not_disable_deadline(self):
        with self.assertRaises(RuntimeError):
            self.execute('import os,time; os.close(0); os.close(1); os.close(2); time.sleep(20)', seconds=.2)

    def test_leader_exit_with_inherited_pipes_fails_and_stops_remaining_group(self):
        source = ('import os,time,signal; pid=os.fork(); '
                  '\nif pid:'
                  '\n while not os.path.exists("descendant.pid"): time.sleep(.005)'
                  '\n os._exit(0)'
                  '\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)'
                  '\nopen("descendant.pid","w").write(str(os.getpid()))'
                  '\ntime.sleep(20)')
        with self.assertRaises(RuntimeError):
            self.execute(source)
        pid = int((self.root / 'descendant.pid').read_text())
        stat = Path(f'/proc/{pid}/stat')
        # A reparented zombie may await CI's init reaper; it is no longer running.
        end = time.monotonic() + 1
        while stat.exists() and not stat.read_text().split(') ')[1].startswith('Z') and time.monotonic() < end:
            time.sleep(.01)
        self.assertTrue(not stat.exists() or stat.read_text().split(') ')[1].startswith('Z'))


if __name__ == '__main__':
    unittest.main()

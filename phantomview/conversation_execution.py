"""Inactive process lifecycle for the ordinary-turn worker contract.

A separate private native build supplies the first principal text entry point.
Trusted embedding must provision and review it before activating this boundary.
"""
import hashlib
import json
from pathlib import Path
import select
import subprocess
import threading
import time

from assistant_worker import HeldMarker
from bounded_process import run
from conversation_forwarding import AccountPolicy, MAX_TEXT, WorkerInbox
from worker_environment import MODEL_CREDENTIALS, environment as model_environment
from worker_store import load_credentials
from worker_workspace import WorkerWorkspace


class ConversationProcess:
    """One fixed-persona execution slot; never accepts command/config from a frame."""
    def __init__(self, *, inbox, executable, sha256, working_dir, environment, credential_file=None,
                 workspace=None):
        if not isinstance(inbox, WorkerInbox) or not isinstance(inbox.policy, AccountPolicy):
            raise ValueError('A fixed authenticated worker inbox is required')
        if (not isinstance(sha256, str) or len(sha256) != 64
                or any(char not in '0123456789abcdef' for char in sha256)
                or not isinstance(environment, dict) or len(environment) > 64
                or any(not isinstance(key, str) or not isinstance(value, str)
                       or not key or '=' in key or '\0' in key or '\0' in value
                       for key, value in environment.items())
                or sum(len(key) + len(value) for key, value in environment.items()) > 65536):
            raise ValueError('A fixed reviewed executable and explicit worker environment are required')
        self.inbox, self.executable, self.sha256 = inbox, str(executable), sha256
        self.working_dir = str(working_dir)
        # No ambient issuer/channel environment is inherited.
        fixed = {'PHANTOMVIEW_WORKER_PERSONA': inbox.persona,
                 'PHANTOMVIEW_WORKER_UID': str(inbox.policy.worker_uid)}
        self.workspace = workspace
        if workspace is not None:
            if (not isinstance(workspace, WorkerWorkspace) or workspace.persona != inbox.persona
                    or workspace.worker_uid != inbox.policy.worker_uid or str(working_dir) != workspace.home):
                raise ValueError('A matching fixed worker workspace is required')
            locations = workspace.launch_environment()
            if any(key in environment and environment[key] != value for key, value in locations.items()):
                raise ValueError('Worker workspace locations cannot be overridden')
            environment = environment | locations
        if any(key in environment and environment[key] != value for key, value in fixed.items()):
            raise ValueError('Worker environment cannot override the fixed persona/account')
        self.environment = model_environment(environment.copy() | fixed)
        if credential_file is not None and (
                not isinstance(credential_file, str) or not credential_file
                or MODEL_CREDENTIALS & self.environment.keys()):
            raise ValueError('Use one fixed model credential source')
        self.credential_file = credential_file
        self._slot = threading.Lock()
        self.verify()

    def launch_environment(self):
        """Read a fresh protected selection per turn, without caching secret values."""
        values = dict(self.environment)
        if self.credential_file is not None:
            values.update(load_credentials(self.credential_file, persona=self.inbox.persona,
                                           worker_uid=self.inbox.policy.worker_uid))
        return dict(model_environment(values))

    def verify(self):
        self.inbox.policy.check('worker')
        if self.workspace is not None:
            self.workspace.verify()
        binary, working = Path(self.executable), Path(self.working_dir)
        for path in (binary, working):
            if not path.is_absolute() or path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
                raise ValueError('Fixed protected worker paths are required')
        for parent in binary.parents:
            info = parent.stat()
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError('Worker artifacts must have protected root-owned parents')
        info = binary.stat()
        if (not binary.is_file() or info.st_uid != 0 or info.st_mode & 0o022
                or not info.st_mode & 0o111 or info.st_size > 128 * 1024 * 1024):
            raise ValueError('A protected reviewed worker artifact is required')
        digest = hashlib.sha256()
        with binary.open('rb') as stream:
            for chunk in iter(lambda: stream.read(65536), b''):
                digest.update(chunk)
        if digest.hexdigest() != self.sha256:
            raise ValueError('Worker artifact changed after review')
        for parent in (working, *working.parents):
            info = parent.stat()
            if info.st_uid not in {0, self.inbox.policy.worker_uid} or info.st_mode & 0o022:
                raise ValueError('Worker working paths must be protected')
        if not working.is_dir():
            raise ValueError('A fixed worker working directory is required')

    def serve_connection(self, connection, *, shutdown=None):
        """Own and close one accepted socket; return only a fixed outcome.

        A future native artifact must consume the full JSON job on stdin under
        __conversation-worker and preserve screening/audience/memory semantics.
        This class does not reinterpret the document as a plain `ask` prompt.
        """
        with connection:
            if not self._slot.acquire(blocking=False):
                return 'unavailable'
            try:
                self.verify()
                job = self.inbox.receive(connection)

                def cancelled():
                    return ((shutdown is not None and shutdown.is_set())
                            or time.monotonic() >= job.deadline
                            or bool(select.select([connection], [], [], 0)[0]))

                if cancelled():
                    return 'cancelled'
                document = {'schema_version': 1, 'kind': 'ordinary-turn', 'job_id': job.job_id,
                            'persona': job.persona, 'channel': job.route.channel,
                            'sender': job.route.sender, 'conversation': job.route.conversation,
                            'tier': job.route.tier, 'audience': job.route.audience, 'text': job.text}
                payload = json.dumps(document, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                marker = HeldMarker()
                raw = run([self.executable, '__conversation-worker'], payload,
                          cwd=self.working_dir, deadline=job.deadline, cancelled=cancelled,
                          stderr_sink=marker.feed, environment=self.launch_environment(), output_limit=MAX_TEXT,
                          private_files=self.workspace is not None)
                if cancelled():
                    return 'cancelled'
                if marker.seen:
                    return 'held'
                self.verify()  # Artifact/account changes cannot release the answer.
                self.inbox.reply(connection, job, raw.decode('utf-8'))
                return 'complete'
            except (OSError, ValueError, RuntimeError, TypeError, subprocess.SubprocessError):
                return 'unavailable'  # No stderr, prompt, response or exception text is exposed.
            finally:
                self._slot.release()

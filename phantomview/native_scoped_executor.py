"""Inactive Linux adapter for a reviewed, separately built scoped executable."""
import copy
import json
from pathlib import Path
import time
import uuid

from assistant_worker import Jobs
from native_scoped_patch import SOURCE_REVISION
from scoped_assistant import MAX_ENVELOPE_BYTES, encode

RESTRICTIONS = {'scoped-projection-only', 'ephemeral-persona', 'ephemeral-memory',
                'ephemeral-working-directory', 'native-screening', 'daily-recall-none'}


class ScopedNativeExecutor:
    def __init__(self, config):
        if (not isinstance(config, dict) or set(config) !=
                {'org', 'persona', 'executable', 'manifest', 'working_dir'}
                or any(not isinstance(value, str) or not value for value in config.values())):
            raise ValueError('An explicit protected native executor configuration is required')
        self.config = copy.deepcopy(config)
        self.jobs = Jobs(self.config)
        self.verify()

    def verify(self):
        # Linux artifact ownership is part of the boundary, not a browser claim.
        manifest_path = Path(self.config['manifest'])
        working = Path(self.config['working_dir'])
        binary = Path(self.config['executable'])
        if (not manifest_path.is_absolute() or manifest_path.is_symlink()
                or not binary.is_absolute() or binary.is_symlink()
                or not working.is_absolute() or not working.is_dir() or working.is_symlink()
                or any(parent.is_symlink() for parent in manifest_path.parents)
                or any(parent.is_symlink() for parent in working.parents)):
            raise ValueError('Fixed protected native paths are required')
        try:
            for parent in set(manifest_path.parents) | set(binary.parents):
                if parent.is_symlink() or parent.stat().st_uid != 0 or parent.stat().st_mode & 0o022:
                    raise ValueError('Native artifact parents must be protected root-owned directories')
            info = manifest_path.stat()
            if info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > 8192:
                raise ValueError('Native manifest must be root-owned, bounded and not writable by other accounts')
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if (manifest.get('source_revision') != SOURCE_REVISION
                    or not RESTRICTIONS <= set(manifest.get('restrictions', []))
                    or not self.jobs.verify_runtime()):
                raise ValueError('A reviewed scoped runtime is required; the legacy analysis worker is insufficient')
        except (OSError, KeyError, TypeError, AttributeError) as error:
            raise ValueError('Scoped native runtime verification failed') from error

    def __call__(self, envelope):
        self.verify()
        if (not isinstance(envelope, dict) or envelope.get('kind') != 'scoped-consultation'
                or envelope.get('trust') != 'untrusted'
                or envelope.get('organization') != self.config['org']
                or envelope.get('persona') != self.config['persona']):
            raise ValueError('Consultation does not match this fixed native executor')
        raw = encode(envelope)
        if not 0 < len(raw) <= MAX_ENVELOPE_BYTES:
            raise ValueError('Native consultation exceeds bounds')
        # Reuse the existing fixed argv/stdin, process deadline, bounded stdout
        # and native held-marker handling. No queue or shared conversation state.
        return self.jobs.execute({'id': str(uuid.uuid4()), 'prompt': raw.decode('utf-8'),
                                  'expires_at': time.time() + 120, 'status': 'running'})

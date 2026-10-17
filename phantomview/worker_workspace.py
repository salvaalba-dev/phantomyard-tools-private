"""Explicit ordinary-worker workspace plan and Linux permission verification."""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from types import MappingProxyType

from worker_environment import environment

UNAVAILABLE = 'Dedicated worker workspace unavailable'
PROFILE_FILES = frozenset({'BOOT.md', 'IDENTITY.md', 'SOUL.md'})


@dataclass(frozen=True, repr=False)
class WorkerWorkspace:
    root: str
    persona: str
    worker_uid: int
    worker_gid: int
    provider: str
    model: str
    judge_provider: str
    judge_model: str
    profile: dict = field(repr=False)

    def __post_init__(self):
        if (not isinstance(self.root, str) or not self.root.startswith('/') or self.root.startswith('//')
                or len(self.root) > 1024 or any(char in self.root for char in ('\\', '\0', '\n', '\r'))
                or any(part in {'', '.', '..'} for part in self.root[1:].split('/'))
                or not isinstance(self.persona, str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', self.persona)
                or any(type(value) is not int or value <= 0 for value in (self.worker_uid, self.worker_gid))
                or not isinstance(self.provider, str) or self.provider not in {'openrouter', 'openai', 'anthropic', 'google'}
                or not isinstance(self.judge_provider, str) or self.judge_provider not in {'typesafe', 'openrouter'}
                or any(not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}', value)
                       for value in (self.model, self.judge_model))
                or not isinstance(self.profile, dict) or 'BOOT.md' not in self.profile
                or set(self.profile) - PROFILE_FILES
                or any(not isinstance(value, str) or not value.strip() or '\0' in value
                       for value in self.profile.values())):
            raise ValueError(UNAVAILABLE)
        try:
            if sum(len(value.encode('utf-8')) for value in self.profile.values()) > 196608:
                raise ValueError(UNAVAILABLE)
        except UnicodeError:
            raise ValueError(UNAVAILABLE) from None
        object.__setattr__(self, 'profile', MappingProxyType(dict(self.profile)))

    @property
    def home(self):
        return self.root + '/home'

    def launch_environment(self):
        return dict(environment({'HOME': self.home, 'XDG_CONFIG_HOME': self.root + '/config',
            'XDG_DATA_HOME': self.root + '/data', 'XDG_STATE_HOME': self.root + '/state',
            'PHANTOMBOT_CONFIG': self.root + '/config/config.toml',
            'PHANTOMBOT_PERSONAS_DIR': self.root + '/profiles'}))

    def files(self):
        """Return private selected profile/config bytes; no source-store reads."""
        def quoted(value):
            return json.dumps(value, ensure_ascii=True)
        config = '\n'.join([
            'default_persona = ' + quoted(self.persona),
            'personas_dir = ' + quoted(self.root + '/profiles'),
            'memory_db = ' + quoted(self.root + '/data/memory.sqlite'),
            'autostart_personas = []', '[harnesses]', 'chain = ["native"]',
            '[harnesses.pi.routing]', 'provider = ' + quoted(self.provider),
            'primary_model = ' + quoted(self.model), '[embeddings]', 'provider = "none"',
            '[voice]', 'provider = "none"', '[jev]', 'provider = ' + quoted(self.judge_provider),
            'model = ' + quoted(self.judge_model), 'key_env = "PHANTOMBOT_JEV_API_KEY"',
            '[jev.judge]', 'enabled = true', '[jev.router]', 'enabled = false', '',
        ]).encode('utf-8')
        return {'config/config.toml': config} | {
            'profiles/' + self.persona + '/' + name: value.encode('utf-8')
            for name, value in self.profile.items()}

    def directories(self):
        """Relative directory metadata for an external trusted provisioner."""
        return {'.': (0, self.worker_gid, 0o710), 'config': (0, self.worker_gid, 0o750),
            'profiles': (0, self.worker_gid, 0o750),
            'profiles/' + self.persona: (0, self.worker_gid, 0o750),
            'home': (self.worker_uid, self.worker_gid, 0o700),
            'data': (self.worker_uid, self.worker_gid, 0o700),
            'state': (self.worker_uid, self.worker_gid, 0o700)}

    def verify(self):
        """Check a quiescent provisioned tree; never provision or repair it."""
        try:
            if (sys.platform != 'linux' or os.getuid() != self.worker_uid or os.geteuid() != self.worker_uid
                    or os.getegid() != self.worker_gid or 0 in os.getgroups()):
                raise ValueError(UNAVAILABLE)
            root = Path(self.root)
            for path in (root, *root.parents):
                info = path.lstat()
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                    raise ValueError(UNAVAILABLE)
            for name, (uid, gid, mode) in self.directories().items():
                info = (root / name).lstat()
                if (not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_gid != gid
                        or stat.S_IMODE(info.st_mode) != mode):
                    raise ValueError(UNAVAILABLE)
            expected = self.files()
            for folder, names in ((root / 'config', {'config.toml'}),
                                  (root / 'profiles', {self.persona}),
                                  (root / 'profiles' / self.persona, set(self.profile))):
                if {path.name for path in folder.iterdir()} != names:
                    raise ValueError(UNAVAILABLE)
            for name, content in expected.items():
                path = root / name
                info = path.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != self.worker_gid
                        or stat.S_IMODE(info.st_mode) != 0o640 or info.st_nlink != 1
                        or info.st_size != len(content)
                        or hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(content).digest()):
                    raise ValueError(UNAVAILABLE)
            # Mutable memory is worker-only; never follow a redirected SQLite file.
            for name in ('memory.sqlite', 'memory.sqlite-wal', 'memory.sqlite-shm'):
                path = root / 'data' / name
                if path.exists() or path.is_symlink():
                    info = path.lstat()
                    if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.worker_uid
                            or info.st_mode & 0o077 or info.st_nlink != 1):
                        raise ValueError(UNAVAILABLE)
            return True
        except (OSError, ValueError, TypeError, AttributeError):
            raise ValueError(UNAVAILABLE) from None

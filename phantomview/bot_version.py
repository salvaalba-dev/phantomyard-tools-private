"""Read-only PhantomBot release observation; never installs or restarts software."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

VERSION = re.compile(r"^v?(\d+\.\d+\.\d+)$")
RELEASES = "https://api.github.com/repos/phantomyard/phantombot/releases/latest"


class Monitor:
    def __init__(self, config):
        self.binary = Path(config["executable"])
        if not self.binary.is_absolute() or not self.binary.is_file():
            raise ValueError("An existing absolute PhantomBot executable is required")
        if os.name != "nt" and (self.binary.stat().st_uid != 0 or self.binary.stat().st_mode & 0o022):
            raise ValueError("The executable must be root-owned and not group/world writable")
        self.scope = "shared" if config.get("shared") is True else "setup"
        self.terminal_url = config.get("terminal_url", "")
        terminal = urlsplit(self.terminal_url)
        if self.terminal_url and (terminal.scheme != "https" or not terminal.netloc or terminal.username
                                  or terminal.password or terminal.query or terminal.fragment):
            raise ValueError("Expected a credential-free HTTPS administration URL")
        self.lock = threading.Lock()
        self.current, self.latest, self.checked_at = "", "", ""
        self.local_at = self.remote_at = float("-inf")
        self.error = "not-checked"

    def status(self, force=False):
        with self.lock:
            clock = time.monotonic()
            if clock - self.local_at >= 15:
                try:
                    result = subprocess.run([str(self.binary), "--version"], capture_output=True,
                                            text=True, timeout=5, check=True)
                    match = VERSION.fullmatch(result.stdout.strip())
                    self.current = match.group(1) if match else ""
                except (OSError, subprocess.SubprocessError):
                    self.current = ""
                self.local_at = clock
            if clock - self.remote_at >= (60 if force or self.error else 3600):
                self.remote_at = clock
                try:
                    request = Request(RELEASES, headers={"User-Agent": "PhantomView-version-observer",
                                                       "Accept": "application/vnd.github+json"})
                    with urlopen(request, timeout=6) as response:
                        raw = response.read(262145)
                    if len(raw) > 262144:
                        raise ValueError("Oversized release response")
                    release = json.loads(raw)
                    match = VERSION.fullmatch(release.get("tag_name", ""))
                    if not match or release.get("draft") or release.get("prerelease"):
                        raise ValueError("Expected a stable release")
                    self.latest = match.group(1)
                    self.checked_at = datetime.now(timezone.utc).isoformat()
                    self.error = ""
                except (OSError, ValueError, TypeError):
                    self.error = "release-check-unavailable"
            available = bool(not self.error and self.current and self.latest and self.current != self.latest)
            return {"installed": self.current, "available": self.latest, "channel": "stable",
                    "update_available": available, "status": "unknown" if self.error or not self.current
                    else "available" if available else "current", "checked_at": self.checked_at,
                    "scope": self.scope, "execution": "human-terminal", "terminal_url": self.terminal_url,
                    "command": "PHANTOMBOT_UPDATE_CHANNEL=stable " + shlex.quote(str(self.binary)) + " update",
                    "release_url": "https://github.com/phantomyard/phantombot/releases/tag/v" + self.latest
                    if self.latest else "https://github.com/phantomyard/phantombot/releases",
                    "error": self.error}

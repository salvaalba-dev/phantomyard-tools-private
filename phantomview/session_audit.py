"""Local metadata-only audit ledger. Not a transcript or tamper-proof archive."""
import json
from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid


class Ledger:
    EVENTS = {"session_created", "session_expired", "session_logout", "session_revoked",
              "assistant_requested", "assistant_response_observed"}
    FIELDS = {"request_id", "job_id", "status", "mode"}
    STATUSES = {"queued", "running", "complete", "held", "failed", "cancelled", "rejected"}

    def __init__(self, path, retention_days=30, clock=time.time):
        if type(retention_days) is not int or not 1 <= retention_days <= 90:
            raise ValueError("Invalid audit retention")
        path = Path(path)
        if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
            raise ValueError("Audit requires a fixed private local path")
        self.path, self.clock = path, clock
        self.retention = retention_days * 86400
        self.lock = threading.Lock()
        # The operator must provision the private parent outside any web export.
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at REAL NOT NULL, "
                       "session TEXT NOT NULL, event TEXT NOT NULL, metadata TEXT NOT NULL, "
                       "UNIQUE(session, event, metadata))")
            db.execute("CREATE INDEX IF NOT EXISTS events_at ON events(at)")
        path.chmod(0o600)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, event, session, **metadata):
        if event not in self.EVENTS or not isinstance(session, str) or not re.fullmatch(r"[a-f0-9]{32}", session):
            raise ValueError("Invalid audit event")
        if set(metadata) - self.FIELDS:
            raise ValueError("Audit metadata is not allowlisted")
        for key, value in metadata.items():
            if key in {"request_id", "job_id"}:
                if not isinstance(value, str) or str(uuid.UUID(value)) != value:
                    raise ValueError("Invalid correlation identifier")
            elif key == "status" and value not in self.STATUSES:
                raise ValueError("Invalid audit status")
            elif key == "mode" and value != "dashboard-analysis":
                raise ValueError("Unverified assistant mode")
        encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute("DELETE FROM events WHERE at < ?", (now - self.retention,))
            db.execute("INSERT OR IGNORE INTO events(at,session,event,metadata) VALUES (?,?,?,?)",
                       (now, session, event, encoded))

    def export(self):
        """Operator-only export; there is deliberately no dashboard HTTP endpoint."""
        with self.lock, self._connect() as db:
            rows = db.execute("SELECT id,at,session,event,metadata FROM events WHERE at >= ? ORDER BY id",
                              (self.clock() - self.retention,)).fetchall()
        return [dict(id=i, at=at, session=session, event=event, metadata=json.loads(meta))
                for i, at, session, event, meta in rows]

"""PhantomBlog access protocol adapter. Never reads persona credentials."""
import hashlib
from http.cookies import CookieError, SimpleCookie
import secrets
import threading
import time
from urllib.parse import urlsplit


class Gate:
    def __init__(self, access, policy, origin, port, session_seconds=1800, clock=time.monotonic):
        if type(session_seconds) is not int or not 60 <= session_seconds <= 3600:
            raise ValueError("La sesión debe durar entre 60 y 3600 segundos")
        if not isinstance(policy, dict) or not policy.get("identities"):
            raise ValueError("Es necesaria una lista explícita de emisores")
        self.origin = access.public_origin(origin, port)
        self.links = access.AccessLinks(policy["identities"])
        self.access = access
        self.policy = policy
        self.sessions = {}
        self.lock = threading.Lock()
        self.clock, self.seconds = clock, session_seconds

    def boundary(self, headers, port):
        for origin in (f"http://127.0.0.1:{port}", self.origin):
            if (headers.get("Host") == urlsplit(origin).netloc
                    and headers.get("Origin", origin) == origin
                    and headers.get("Sec-Fetch-Site", "same-origin") in ("same-origin", "none")):
                return origin
        return None

    def issue(self, authorization, origin):
        # Reuse the installed verifier, replay protection and five-minute grants.
        return self.links.issue(authorization, origin, self.origin)

    def create_session(self):
        with self.lock:
            self._prune()
            if len(self.sessions) >= 100:
                raise ValueError("Demasiadas sesiones")
            value = secrets.token_urlsafe(32)
            self.sessions[self.digest(value)] = self.clock() + self.seconds
            return value

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def _prune(self):
        current = self.clock()
        self.sessions = {key: expiry for key, expiry in self.sessions.items() if expiry > current}

    def session(self, headers):
        try:
            cookie = SimpleCookie(headers.get("Cookie", ""))
            value = cookie["phantomview"].value
            with self.lock:
                self._prune()
                return self.digest(value) in self.sessions
        except (CookieError, KeyError, ValueError, TypeError):
            return False

    def redeem(self, code):
        return self.links.redeem(code, self.create_session)

    def cookie(self, value=""):
        secure = "; Secure" if self.origin.startswith("https://") else ""
        return f"phantomview={value}; HttpOnly; SameSite=Strict; Path=/; Max-Age={self.seconds if value else 0}{secure}"

    def logout(self, headers):
        try:
            value = SimpleCookie(headers.get("Cookie", ""))["phantomview"].value
            with self.lock:
                self.sessions.pop(self.digest(value), None)
        except (CookieError, KeyError, ValueError, TypeError):
            pass


class SnapshotReader:
    """Fixed exported index only: the web process has no source/config access."""
    def __init__(self, path, policy):
        from pathlib import Path
        self.path = Path(path)
        self.policy = policy
        self.config = {"sync_interval": 0, "software_interval": 0}
        self.software_status = "Administración local"

    def data(self):
        import json
        if self.path.is_symlink() or self.path.stat().st_size > 8_000_000:
            raise ValueError("Índice no válido")
        result = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(result, dict) or not isinstance(result.get("snapshot"), dict):
            raise ValueError("Índice no válido")
        result["read_only"] = True
        result["access"] = {key: self.policy.get(key, "") for key in ("actor", "role", "request_instructions")}
        return result

    def refresh(self):
        return self.data()

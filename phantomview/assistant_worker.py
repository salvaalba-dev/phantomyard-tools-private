"""Private AU worker: bounded jobs using a compiled native-only, zero-tools runtime."""
import argparse
from collections import deque
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

from bounded_process import run as run_bounded_process


def redact(text):
    text = re.sub(r"(?i)(?:nsec1[a-z0-9]{20,}|(?:sk-|ghp_|github_pat_|AIza)[a-zA-Z0-9_-]{16,})", "[REDACTED]", text)
    return re.sub(r"(?im)((?:api[_ -]?key|password|secret|token|authorization)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", text)


class ConsultationHeld(Exception):
    """A real screenedHold completion, not a provider or transport error."""


class HeldMarker:
    def __init__(self):
        self.seen, self.tail = False, b""

    def feed(self, chunk):
        data = self.tail + chunk
        self.seen |= b"\nPHANTOMVIEW_HELD\n" in data
        self.tail = data[-32:]


class Jobs:
    def __init__(self, config, executor=None, clock=time.time):
        self.config, self.clock = config, clock
        self.executor = executor or self.execute
        self.rows, self.requests = {}, {}
        self.queue, self.active = deque(), None
        self.lock = threading.RLock()
        self.calls = deque()
        self.restricted = self.verify_runtime() if executor is None else True

    def verify_runtime(self):
        try:
            binary = Path(self.config["executable"])
            manifest = json.loads(Path(self.config["manifest"]).read_text())
            return (binary.is_absolute() and not binary.is_symlink() and binary.is_file()
                    and binary.stat().st_uid == 0 and not binary.stat().st_mode & 0o022
                    and hashlib.sha256(binary.read_bytes()).hexdigest() == manifest["sha256"]
                    and set(manifest["restrictions"]) >= {"native-only", "tools-none", "mcp-none", "extensions-none", "skills-none", "stateless", "screened-hold-marker"})
        except (OSError, ValueError, KeyError):
            return False

    def submit(self, body, owner):
        with self.lock:
            if not self.restricted:
                return 503, {"error": "Restricted assistant runtime unavailable"}
            if not re.fullmatch(r"[a-f0-9]{64}", owner) or not isinstance(body, dict) or set(body) != {"org", "persona", "prompt", "request_id", "basis", "expires_at"}:
                return 400, {"error": "Invalid assistant request"}
            if body["org"] != self.config["org"] or body["persona"] != self.config["persona"]:
                return 403, {"error": "Assistant setup is outside the authorized scope"}
            try:
                ident = str(uuid.UUID(body["request_id"]))
                assert ident == body["request_id"]
                expiry = float(body["expires_at"])
                assert self.clock() < expiry <= self.clock() + 1805
                assert isinstance(body["prompt"], str) and 0 < len(body["prompt"].encode()) <= 12000
                assert isinstance(body["basis"], dict) and len(json.dumps(body["basis"])) <= 1000
            except (ValueError, TypeError, AssertionError, AttributeError):
                return 400, {"error": "Invalid assistant request"}
            fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            # Session expiry is not a request identity: a retry can arrive one second later.
            fingerprint = hashlib.sha256(json.dumps({k:v for k,v in body.items() if k != "expires_at"}, sort_keys=True).encode()).hexdigest()
            key = (owner, ident)
            if key in self.requests:
                old = self.rows.get(self.requests[key])
                if old and old["fingerprint"] == fingerprint:
                    return 200, self.public(old)
                return 409, {"error": "Assistant request identifier already used"}
            self.prune()
            now = self.clock()
            recent = [pair for pair in self.calls if pair[0] > now - 3600]
            if len(recent) >= 40 or sum(o == owner for _,o in recent) >= 10:
                return 429, {"error": "Assistant consultation limit reached; try later"}
            if len(self.queue) >= 4 or len(self.rows) >= 40:
                return 429, {"error": "Assistant queue is full; try later"}
            job_id = str(uuid.uuid4())
            row = dict(body, id=job_id, owner=owner, fingerprint=fingerprint, status="queued", text="", created_at=now)
            self.rows[job_id] = row; self.requests[key] = job_id; self.queue.append(job_id); self.calls.append((now,owner))
            if self.active is None:
                self.active = True
                threading.Thread(target=self.drain, daemon=True).start()
            return 202, self.public(row)

    def public(self, row):
        return {key: row.get(key) for key in ("id", "status", "text", "persona", "basis", "created_at")}

    def get(self, ident, owner):
        with self.lock:
            row = self.rows.get(ident)
            if not row or row["owner"] != owner or row["expires_at"] <= self.clock():
                return 404, {"error": "Assistant reply unavailable in this session"}
            return 200, self.public(row)

    def cancel(self, ident, owner):
        with self.lock:
            row = self.rows.get(ident)
            if not row or row["owner"] != owner:
                return 404, {"error": "Assistant reply unavailable in this session"}
            row["status"] = "cancelled"; row["text"] = ""
            return 200, self.public(row)

    def prune(self):
        now = self.clock()
        for ident,row in list(self.rows.items()):
            if row["expires_at"] <= now and row["status"] != "running":
                self.rows.pop(ident)
                self.requests.pop((row["owner"],row["request_id"]),None)
        while self.calls and self.calls[0][0] <= now - 3600:
            self.calls.popleft()

    def drain(self):
        while True:
            with self.lock:
                if not self.queue:
                    self.active = None; return
                row = self.rows.get(self.queue.popleft())
                if not row or row["status"] == "cancelled" or row["expires_at"] <= self.clock():
                    continue
                row["status"] = "running"
            try:
                text = self.executor(row)
                with self.lock:
                    if row["status"] != "cancelled":
                        row["text"] = redact(text)[:20000]
                        row["status"] = "complete"
            except ConsultationHeld:
                with self.lock:
                    if row["status"] != "cancelled":
                        row["status"] = "held"; row["text"] = ""
            except Exception:
                with self.lock:
                    if row["status"] != "cancelled":
                        row["status"] = "failed"; row["text"] = "Assistant could not complete this consultation. No tools or corrections were executed."

    def execute(self, row):
        # Fixed argv, stdin input, no shell, no history and no user-selectable target.
        command = [self.config["executable"], "ask", "--persona", self.config["persona"], "--conversation", "phantomview:" + row["id"], "--", "-"]
        marker = HeldMarker()
        deadline = time.monotonic() + max(0, min(120, row["expires_at"] - self.clock()))
        try:
            raw = run_bounded_process(command, row["prompt"].encode(), cwd=self.config["working_dir"],
                                      deadline=deadline, cancelled=lambda: row["status"] == "cancelled",
                                      stderr_sink=marker.feed, popen=subprocess.Popen)
        except RuntimeError:
            if marker.seen:
                raise ConsultationHeld() from None
            raise
        if marker.seen:
            raise ConsultationHeld()
        return raw.decode("utf8", errors="replace")


class WorkerHandler(BaseHTTPRequestHandler):
    def log_message(self,*_): pass
    def send(self,status,body):
        raw=json.dumps(body,ensure_ascii=False).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def authorized(self):
        supplied=self.headers.get("Authorization","").removeprefix("Bearer ")
        return bool(supplied) and hmac.compare_digest(supplied.encode(),self.server.token.encode())
    def do_GET(self):
        if not self.authorized(): return self.send(401,{"error":"Assistant authentication required"})
        if self.path=="/status":return self.send(200,{"ready":self.server.jobs.restricted,"persona":self.server.jobs.config["persona"],"tools":"none","scope":"phantomview-analysis","session_limit":10,"global_limit":40})
        if re.fullmatch(r"/jobs/[a-f0-9-]{36}",self.path):return self.send(*self.server.jobs.get(self.path.rsplit("/",1)[1],self.headers.get("X-PhantomView-Session","")))
        self.send(404,{"error":"Unknown assistant operation"})
    def do_POST(self):
        if not self.authorized():return self.send(401,{"error":"Assistant authentication required"})
        if self.path!="/jobs":return self.send(404,{"error":"Unknown assistant operation"})
        try:
            size=int(self.headers.get("Content-Length","0"))
            if not 0<size<=16000:raise ValueError()
            body=json.loads(self.rfile.read(size))
            self.send(*self.server.jobs.submit(body,self.headers.get("X-PhantomView-Session","")))
        except (ValueError,TypeError):self.send(400,{"error":"Invalid assistant request"})
    def do_DELETE(self):
        if not self.authorized():return self.send(401,{"error":"Assistant authentication required"})
        if not re.fullmatch(r"/jobs/[a-f0-9-]{36}",self.path):return self.send(404,{"error":"Unknown assistant operation"})
        self.send(*self.server.jobs.cancel(self.path.rsplit("/",1)[1],self.headers.get("X-PhantomView-Session","")))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--config",required=True);args=parser.parse_args()
    config=json.loads(Path(args.config).read_text())
    token=Path(config["token_file"]).read_text().strip()
    if not re.fullmatch(r"[a-f0-9]{64}",token):raise ValueError("Invalid assistant token")
    server=ThreadingHTTPServer(("127.0.0.1",config["port"]),WorkerHandler);server.token=token;server.jobs=Jobs(config);server.serve_forever()


if __name__=="__main__":main()

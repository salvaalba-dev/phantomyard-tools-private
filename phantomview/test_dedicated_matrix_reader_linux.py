"""Rehearse the existing matrix route with a dedicated Linux reader."""

import contextlib
import http.client
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

READER = """
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from types import SimpleNamespace
import scoped_http

recipient = SimpleNamespace(persona="example-agent", human=None)
directory = SimpleNamespace(
    org={
        "organization": {"id": "example"},
        "documents": {"naming": {"domains": [
            {"id": "projects", "types": [{"id": "example", "category": "private"}]},
        ]}},
        "policies": {"security_categories": {"private": {}}},
    },
    permits=lambda current, resource: current is recipient and resource["project"] == "example",
)

def identified(headers):
    if headers.get("Authorization") != "Bearer synthetic-test-session":
        raise ValueError("session required")
    return recipient, directory

class Handler(BaseHTTPRequestHandler):
    def allowed(self):
        return True

    def send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        assert scoped_http.dispatch(self, "GET")

with HTTPServer(("127.0.0.1", 0), Handler) as server:
    server.timeout = 10
    server.scoped_backend = SimpleNamespace(gate=SimpleNamespace(identified_scope=identified))
    print(json.dumps([server.server_port, os.getuid(), os.getgid(), os.getgroups()]), flush=True)
    server.handle_request()
"""


@unittest.skipUnless(
    sys.platform == "linux"
    and os.geteuid() == 0
    and os.environ.get("PHANTOMVIEW_DEDICATED_READER_LINUX") == "1",
    "requires disposable Linux root ACL fixture",
)
class DedicatedMatrixReaderTests(unittest.TestCase):
    def test_legacy_route_uses_reader_uid_and_matrix_only_acl(self):
        from queue import Queue
        from unittest.mock import patch

        from phantomdocs import view_matrix_broker as broker
        from phantomdocs.view_matrix_http_patch import patch_http

        reader_uid, reader_gid, foreign_uid = 65534, 65532, 65533
        shared_ipc = 65531

        def acl(rule, target):
            subprocess.run(["setfacl", "-m", rule, target], check=True)

        with tempfile.TemporaryDirectory(
            prefix="pv-dedicated-reader-", dir="/var/lib"
        ) as tmp:
            root = Path(tmp)
            root.chmod(0o755)
            source = Path(__file__).with_name("scoped_http.py").read_bytes()
            (root / "scoped_http.py").write_bytes(patch_http(source))
            (root / "reader.py").write_text(READER)
            ipc = root / "ipc"
            ipc.mkdir()
            os.chown(ipc, 0, shared_ipc)
            ipc.chmod(0o750)
            alma, neighbor = ipc / "matrix.sock", ipc / "neighbor.sock"
            config = root / "routes.json"
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "routes": {
                            "example-agent": {
                                "socket": str(alma),
                                "server_uid": 0,
                                "domain": "projects",
                                "project_type": "example",
                                "scope_id": "example",
                            }
                        },
                    }
                )
            )
            config.chmod(0o600)
            acl(f"u:{reader_uid}:r--,u:{foreign_uid}:r--", config)
            acl(f"u:{reader_uid}:--x", ipc)

            def command(uid, groups, *args, **kwargs):
                return subprocess.Popen(
                    [sys.executable, "-E", "-s", "-B", *args],
                    user=uid,
                    group=reader_gid,
                    extra_groups=groups,
                    cwd=root,
                    env={
                        "PHANTOMVIEW_MATRIX_ROUTES": str(config),
                        "PATH": "/usr/bin:/bin",
                    },
                    **kwargs,
                )

            def http(uid, groups, authenticated=True):
                with command(
                    uid,
                    groups,
                    str(root / "reader.py"),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                ) as child:
                    ready = Queue()
                    thread = threading.Thread(
                        target=lambda: ready.put(child.stdout.readline()), daemon=True
                    )
                    thread.start()
                    try:
                        port, actual_uid, actual_gid, actual_groups = json.loads(
                            ready.get(timeout=5)
                        )
                        self.assertEqual(
                            (actual_uid, actual_gid, actual_groups),
                            (uid, reader_gid, groups),
                        )
                        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                        try:
                            headers = (
                                {"Authorization": "Bearer synthetic-test-session"}
                                if authenticated
                                else {}
                            )
                            conn.request("GET", "/api/matrix/v25", headers=headers)
                            response = conn.getresponse()
                            result = response.status, json.loads(response.read())
                        finally:
                            conn.close()
                        self.assertEqual(child.wait(timeout=5), 0)
                        return result
                    finally:
                        if child.poll() is None:
                            child.kill()

            def access(uid, groups):
                with command(
                    uid,
                    groups,
                    "-c",
                    "import os,sys; print([os.access(x, os.W_OK) for x in sys.argv[1:]])",
                    str(alma),
                    str(neighbor),
                    stdout=subprocess.PIPE,
                    text=True,
                ) as child:
                    out, _ = child.communicate(timeout=5)
                    self.assertEqual(child.returncode, 0)
                    return out.strip()

            with (
                socket.socket(socket.AF_UNIX) as listener,
                socket.socket(socket.AF_UNIX) as other,
            ):
                for stream, path in ((listener, alma), (other, neighbor)):
                    stream.bind(str(path))
                    os.chown(path, 0, shared_ipc)
                    path.chmod(0o660)
                    stream.listen()
                listener.settimeout(5)
                acl(f"u:{reader_uid}:-w-", alma)
                self.assertEqual(access(reader_uid, []), "[True, False]")
                self.assertEqual(access(foreign_uid, []), "[False, False]")
                self.assertEqual(access(foreign_uid, [shared_ipc]), "[True, True]")
                self.assertEqual(http(reader_uid, [], authenticated=False)[0], 404)
                self.assertEqual(http(foreign_uid, [])[0], 404)
                peers, authorized = [], []

                @contextlib.contextmanager
                def authority(actor):
                    authorized.append(actor)
                    yield {}, {}, object()

                def serve():
                    stream, _ = listener.accept()
                    _, uid, gid = struct.unpack(
                        "3i",
                        stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12),
                    )
                    peers.append((uid, gid))
                    broker.serve(
                        stream,
                        client_uid=reader_uid,
                        actor="example-agent",
                        binding={},
                        authority=authority,
                    )

                with patch.object(broker, "read_matrix", return_value="synthetic v25"):
                    for uid, groups, expected in (
                        (
                            reader_uid,
                            [],
                            (200, {"version": "v25", "content": "synthetic v25"}),
                        ),
                        (
                            foreign_uid,
                            [shared_ipc],
                            (404, {"error": "Matrix unavailable"}),
                        ),
                    ):
                        worker = threading.Thread(target=serve, daemon=True)
                        worker.start()
                        self.assertEqual(http(uid, groups), expected)
                        worker.join(6)
                        self.assertFalse(worker.is_alive())
                self.assertEqual(
                    peers, [(reader_uid, reader_gid), (foreign_uid, reader_gid)]
                )
                self.assertEqual(authorized, ["example-agent"])

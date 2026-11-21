"""Rehearse the existing matrix route with a dedicated Linux reader."""

import contextlib
import errno
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
    def test_tmpfiles_restores_handoff_bind_after_recreation(self):
        old_uid, reader_uid, reader_gid, handoff_group = 65533, 65534, 65532, 65531
        with tempfile.TemporaryDirectory(prefix="pv-handoff-", dir="/var/lib") as tmp:
            root = Path(tmp)
            root.chmod(0o755)
            handoff = root / "handoff"
            endpoint = handoff / "issue.sock"
            config = root / "handoff.conf"
            bind_socket = """\
import errno
import socket
import sys

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
    try:
        listener.bind(sys.argv[1])
    except PermissionError:
        sys.exit(errno.EACCES)
    listener.listen()
"""

            for phase, owner, expected in (
                ("old rule", old_uid, errno.EACCES),
                ("cutover", reader_uid, 0),
                ("fresh runtime", reader_uid, 0),
                ("rollback", old_uid, errno.EACCES),
            ):
                with self.subTest(phase=phase):
                    if phase == "fresh runtime":
                        handoff.rmdir()
                    config.write_text(
                        f"d {handoff} 0750 {owner} {handoff_group} -\n",
                        encoding="ascii",
                    )
                    subprocess.run(
                        ["/usr/bin/systemd-tmpfiles", "--create", str(config)],
                        check=True,
                        timeout=5,
                    )
                    metadata = handoff.stat()
                    self.assertEqual(
                        (metadata.st_uid, metadata.st_gid, metadata.st_mode & 0o7777),
                        (owner, handoff_group, 0o750),
                    )
                    result = subprocess.run(
                        [sys.executable, "-I", "-B", "-c", bind_socket, str(endpoint)],
                        user=reader_uid,
                        group=reader_gid,
                        extra_groups=[handoff_group],
                        check=False,
                        timeout=5,
                    )
                    self.assertEqual(result.returncode, expected)
                    if expected == 0:
                        self.assertEqual(endpoint.lstat().st_uid, reader_uid)
                        endpoint.unlink()

    def test_legacy_route_uses_reader_uid_and_matrix_only_acl(self):
        from queue import Queue
        from unittest.mock import patch

        from phantomdocs import view_matrix_broker as broker
        from phantomdocs.view_matrix_http_patch import patch_http

        reader_uid, reader_gid, foreign_uid = 65534, 65532, 65533
        shared_ipc, issuer_ipc, matrix_group, neighbor_group = (
            65531,
            65530,
            65529,
            65528,
        )
        handoff_groups = sorted([shared_ipc, issuer_ipc])

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
            handoff_dir = root / "handoff"
            matrix_dir = root / "matrix"
            neighbor_dir = root / "neighbor"
            for directory, group in (
                (handoff_dir, shared_ipc),
                (matrix_dir, matrix_group),
                (neighbor_dir, neighbor_group),
            ):
                directory.mkdir()
                os.chown(directory, 0, group)
                directory.chmod(0o750)
            handoff = handoff_dir / "issue.sock"
            alma = matrix_dir / "matrix.sock"
            neighbor = neighbor_dir / "matrix.sock"
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

            def request_matrix(uid, groups, authenticated=True):
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
                    str(handoff),
                    stdout=subprocess.PIPE,
                    text=True,
                ) as child:
                    out, _ = child.communicate(timeout=5)
                    self.assertEqual(child.returncode, 0)
                    return out.strip()

            with (
                socket.socket(socket.AF_UNIX) as listener,
                socket.socket(socket.AF_UNIX) as other,
                socket.socket(socket.AF_UNIX) as issuer,
            ):
                for stream, path, group in (
                    (listener, alma, matrix_group),
                    (other, neighbor, neighbor_group),
                    (issuer, handoff, shared_ipc),
                ):
                    stream.bind(str(path))
                    os.chown(path, 0, group)
                    path.chmod(0o660)
                    stream.listen()
                listener.settimeout(5)
                self.assertEqual(
                    access(reader_uid, handoff_groups), "[False, False, True]"
                )
                acl(f"u:{reader_uid}:--x", matrix_dir)
                self.assertEqual(
                    access(reader_uid, handoff_groups), "[False, False, True]"
                )
                acl(f"u:{reader_uid}:-w-", alma)
                self.assertEqual(
                    access(reader_uid, handoff_groups), "[True, False, True]"
                )
                self.assertEqual(
                    access(foreign_uid, handoff_groups), "[False, False, True]"
                )
                self.assertEqual(
                    request_matrix(reader_uid, handoff_groups, authenticated=False)[0],
                    404,
                )
                self.assertEqual(request_matrix(foreign_uid, handoff_groups)[0], 404)
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
                            handoff_groups,
                            (200, {"version": "v25", "content": "synthetic v25"}),
                        ),
                        (
                            foreign_uid,
                            sorted([*handoff_groups, matrix_group]),
                            (404, {"error": "Matrix unavailable"}),
                        ),
                    ):
                        worker = threading.Thread(target=serve, daemon=True)
                        worker.start()
                        self.assertEqual(request_matrix(uid, groups), expected)
                        worker.join(6)
                        self.assertFalse(worker.is_alive())
                self.assertEqual(
                    peers, [(reader_uid, reader_gid), (foreign_uid, reader_gid)]
                )
                self.assertEqual(authorized, ["example-agent"])

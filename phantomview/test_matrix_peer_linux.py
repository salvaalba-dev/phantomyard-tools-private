"""Exercise the scoped HTTP route with real Linux ACLs and broker peer checks."""

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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import scoped_http


@unittest.skipUnless(
    sys.platform == "linux"
    and os.geteuid() == 0
    and os.environ.get("PHANTOMVIEW_MATRIX_LINUX") == "1",
    "requires the disposable Linux root ACL fixture",
)
class MatrixPeerIntegration(unittest.TestCase):
    def test_http_read_and_unrelated_uid_denials(self):
        from phantomdocs import view_matrix_broker as broker

        authorized_uid, other_uid = 65534, 65533
        connector_gid = 65532
        recipient = SimpleNamespace(persona="example-agent", human=None)
        directory = SimpleNamespace(
            org={
                "organization": {"id": "example"},
                "documents": {
                    "naming": {
                        "domains": [
                            {
                                "id": "projects",
                                "types": [{"id": "example", "category": "private"}],
                            },
                        ]
                    }
                },
                "policies": {"security_categories": {"private": {}}},
            },
            permits=lambda current, resource: (
                current is recipient and resource["project"] == "example"
            ),
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
                if not scoped_http.dispatch(self, "GET"):
                    self.send(404, {})

        def acl(rule, path):
            subprocess.run(["setfacl", "-m", rule, str(path)], check=True)

        with tempfile.TemporaryDirectory(
            prefix="pv-matrix-peer-", dir="/var/lib"
        ) as temp:
            root = Path(temp)
            config = root / "routes.json"
            config.touch(mode=0o600)
            endpoint = root / "matrix.sock"
            route = {
                "socket": str(endpoint),
                "server_uid": 0,
                "client_gid": connector_gid,
                "domain": "projects",
                "project_type": "example",
                "scope_id": "example",
            }
            with (
                socket.socket(socket.AF_UNIX) as listener,
                ThreadingHTTPServer(
                    ("127.0.0.1", 0),
                    Handler,
                ) as web,
                patch.dict(os.environ, {"PHANTOMVIEW_MATRIX_PEER_ROUTES": str(config)}),
            ):
                listener.bind(str(endpoint))
                endpoint.chmod(0o600)
                acl(f"u:{authorized_uid}:--x", root)
                acl(f"u:{authorized_uid}:-w-", endpoint)
                listener.listen()
                listener.settimeout(2)
                web.scoped_backend = SimpleNamespace(
                    gate=SimpleNamespace(identified_scope=identified)
                )
                worker = threading.Thread(target=web.serve_forever, daemon=True)
                worker.start()
                requests = []
                peers = []

                @contextlib.contextmanager
                def authority(actor):
                    requests.append(actor)
                    yield {}, {}, object()

                def request(uid, authenticated=True):
                    config.write_text(
                        json.dumps(
                            {
                                "version": 2,
                                "routes": {
                                    "example-agent": {**route, "client_uid": uid}
                                },
                            }
                        )
                    )
                    headers = (
                        {"Authorization": "Bearer synthetic-test-session"}
                        if authenticated
                        else {}
                    )
                    conn = http.client.HTTPConnection(*web.server_address, timeout=10)
                    try:
                        conn.request("GET", "/api/matrix/v25", headers=headers)
                        response = conn.getresponse()
                        return response.status, json.loads(response.read())
                    finally:
                        conn.close()

                def serve_one(fn):
                    def serve():
                        connection, _ = listener.accept()
                        _, uid, gid = struct.unpack(
                            "3i",
                            connection.getsockopt(
                                socket.SOL_SOCKET, socket.SO_PEERCRED, 12
                            ),
                        )
                        peers.append((uid, gid))
                        broker.serve(
                            connection,
                            client_uid=authorized_uid,
                            actor="example-agent",
                            binding={},
                            authority=authority,
                        )

                    with patch.object(
                        broker, "read_matrix", return_value="synthetic v25"
                    ):
                        thread = threading.Thread(
                            target=serve,
                            daemon=True,
                        )
                        thread.start()
                        result = fn()
                        thread.join(5)
                        self.assertFalse(thread.is_alive())
                        return result

                try:
                    self.assertEqual(
                        request(authorized_uid, authenticated=False)[0], 404
                    )
                    self.assertEqual(request(other_uid)[0], 404)
                    self.assertEqual(requests, [])
                    self.assertEqual(
                        serve_one(lambda: request(authorized_uid)),
                        (
                            200,
                            {"version": "v25", "content": "synthetic v25"},
                        ),
                    )
                    self.assertEqual(requests, ["example-agent"])
                    self.assertEqual(peers, [(authorized_uid, connector_gid)])
                    with (
                        socket.socket(socket.AF_UNIX) as wrong,
                        socket.socket(socket.AF_UNIX) as client,
                    ):
                        wrong_address = str(root / "other.sock")
                        wrong.bind(wrong_address)
                        wrong.listen()
                        client.connect(wrong_address)
                        other_end, _ = wrong.accept()
                        with other_end:
                            other_end.settimeout(2)
                            with patch(
                                "matrix_http.connect",
                                return_value=contextlib.closing(client),
                            ):
                                self.assertEqual(request(authorized_uid)[0], 404)
                            self.assertEqual(other_end.recv(1), b"")
                    # A deliberately permissive second fixture proves the broker
                    # independently rejects the wrong UID after connect succeeds.
                    acl(f"u:{other_uid}:--x", root)
                    acl(f"u:{other_uid}:-w-", endpoint)
                    self.assertEqual(serve_one(lambda: request(other_uid))[0], 404)
                    self.assertEqual(requests, ["example-agent"])
                    self.assertEqual(peers[-1], (other_uid, connector_gid))
                finally:
                    web.shutdown()
                    worker.join(5)

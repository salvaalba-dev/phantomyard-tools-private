"""Opt-in rehearsal using the pinned supervisor and disposable systemd units."""

import errno
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_dedicated_matrix_reader_linux import READER

BROKER = """\
import hashlib
import socket
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from phantomdocs import view_matrix_broker

source = Path(view_matrix_broker.__file__).resolve()
assert source.is_relative_to(Path(sys.prefix).resolve()), source
assert hashlib.sha256(source.read_bytes()).hexdigest() == sys.argv[1], source

@contextmanager
def authority(actor):
    assert actor == "example-agent"
    yield {}, {}, object()

with patch.object(view_matrix_broker, "read_matrix", return_value="synthetic v25"):
    view_matrix_broker.serve(socket.socket(fileno=0), client_uid=970,
                             actor="example-agent", binding={}, authority=authority)
"""

PROBE = """\
import errno
import socket
import sys

with socket.socket(socket.AF_UNIX) as conn:
    conn.settimeout(5)
    try:
        conn.connect(sys.argv[1])
    except PermissionError:
        sys.exit(errno.EACCES)
    with conn.makefile("rb") as reply:
        print(reply.readline().decode(), end="")
"""


@unittest.skipUnless(
    sys.platform == "linux"
    and os.geteuid() == 0
    and os.environ.get("PHANTOMVIEW_DEDICATED_SYSTEMD") == "1",
    "requires a disposable Linux systemd runner with trial identities",
)
class DedicatedReaderSystemdTests(unittest.TestCase):
    def test_reconcile_and_recreate_matrix_socket(self):
        import pwd

        from phantomdocs.view_agent_guarded_launch import http_ready
        from phantomdocs.view_agent_host import read_json, validate_reader
        from phantomdocs.view_agent_recovery import RecoveryRequired
        from phantomdocs.view_agent_supervisor import reconcile_once
        from phantomdocs.view_agent_systemd import SystemdRouteHost

        account = pwd.getpwuid(970)
        self.assertEqual(account.pw_gid, 970)
        self.assertEqual(set(os.getgrouplist(account.pw_name, 970)), {970, 1001})

        with tempfile.TemporaryDirectory(prefix="pv-cutover-", dir="/run") as tmp:
            root = Path(tmp)
            root.chmod(0o755)
            state = root / "state"
            state.mkdir()
            os.chown(state, 0, 1001)
            state.chmod(0o750)
            matrix = root / "matrix"
            endpoint = matrix / "matrix-alma.sock"
            handoff = root / "handoff"
            units = Path("/run/systemd/system")
            viewer = units / f"{root.name}.service"
            listener = units / f"{root.name}-matrix.socket"
            broker = units / f"{root.name}-matrix@.service"
            config, baseline = state / "reader.json", state / "baseline.json"
            pending, committed = state / "pending.json", state / "committed.json"
            org = state / "org.json"
            policy, transaction = state / "policy.lock", state / "transaction.lock"
            routes, reader = root / "routes.json", root / "reader.py"
            broker_script, runtime = root / "broker.py", root / "runtime.conf"

            def systemctl(*args, check=True):
                return subprocess.run(
                    ["/usr/bin/systemctl", "--no-pager", *args], check=check, timeout=35
                )

            def acl(option, entry, path):
                subprocess.run(
                    ["/usr/bin/setfacl", option, entry, str(path)],
                    check=True,
                    timeout=5,
                )

            def probe(uid, gid, groups):
                return subprocess.run(
                    [sys.executable, "-I", "-c", PROBE, str(endpoint)],
                    user=uid,
                    group=gid,
                    extra_groups=groups,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )

            def get(path):
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                try:
                    conn.request(
                        "GET",
                        path,
                        headers={
                            "Authorization": "Bearer synthetic-test-session",
                        },
                    )
                    response = conn.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    conn.close()

            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            initial = {
                "schema_version": 1,
                "organization": "example",
                "actor": "example-agent",
                "agent_actors": [],
                "port": port,
                "reader_uid": 1001,
                "issuer_uid": 1059,
                "socket_group": 1059,
                "socket_path": str(handoff / "issuer.sock"),
            }
            for path, value in (
                (baseline, initial),
                (config, initial),
                (org, {"version": 1, "organization": {"id": "example"}, "actors": []}),
                (
                    routes,
                    {
                        "version": 1,
                        "routes": {
                            "example-agent": {
                                "socket": str(endpoint),
                                "server_uid": 0,
                                "domain": "projects",
                                "project_type": "example",
                                "scope_id": "example",
                            }
                        },
                    },
                ),
            ):
                path.write_text(json.dumps(value), encoding="utf-8")
            baseline.chmod(0o600)
            org.chmod(0o600)
            os.chown(config, 0, 1001)
            config.chmod(0o640)
            policy.touch(mode=0o600)
            transaction.touch(mode=0o600)
            source = Path(__file__).with_name("scoped_http.py").read_bytes()
            patched = subprocess.check_output(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    (
                        "import sys; from phantomdocs.view_matrix_http_patch import patch_http; "
                        "sys.stdout.buffer.write(patch_http(sys.stdin.buffer.read()))"
                    ),
                ],
                input=source,
                timeout=10,
            )
            (root / "scoped_http.py").write_bytes(patched)
            reader.write_text(READER, encoding="utf-8")
            broker_script.write_text(BROKER, encoding="utf-8")
            runtime.write_text(f"d {handoff} 0750 1001 1059 -\n", encoding="ascii")
            settings = {
                "config": str(config),
                "python": sys.executable,
                "reader": str(reader),
                "supplementary_groups": [1059, 1890],
            }
            launcher = [
                sys.executable,
                "-B",
                "-m",
                "phantomdocs.view_agent_guarded_launch",
                "--org",
                str(org),
                "--config",
                str(config),
                "--journal",
                str(pending),
                "--committed",
                str(committed),
                "--policy-lock",
                str(policy),
                "--python",
                sys.executable,
                "--reader",
                str(reader),
                "--supplementary-group",
                "1059",
                "--supplementary-group",
                "1890",
                "--runtime-directory",
                str(handoff),
            ]
            try:
                viewer.write_text(
                    "[Service]\nType=simple\nUser=root\nGroup=1001\n"
                    f"RuntimeDirectory={root.name}/handoff\nRuntimeDirectoryPreserve=no\n"
                    f"ExecStartPre=/usr/bin/systemd-tmpfiles --create {runtime}\n"
                    f"Environment=PYTHONPATH={os.environ['PYTHONPATH']}\n"
                    f"Environment=PHANTOMVIEW_MATRIX_ROUTES={routes}\n"
                    f"ExecStart={' '.join(launcher)}\nTimeoutStopSec=5\n",
                    encoding="ascii",
                )
                listener.write_text(
                    "[Socket]\nAccept=yes\nRemoveOnStop=yes\nSocketUser=root\n"
                    f"ListenStream={endpoint}\nSocketGroup=1891\nSocketMode=0660\n"
                    "DirectoryMode=0750\n"
                    f"ExecStartPost=/usr/bin/setfacl -m u:970:-w- {endpoint}\n",
                    encoding="ascii",
                )
                broker.write_text(
                    "[Service]\nType=oneshot\nStandardInput=socket\nStandardOutput=journal\n"
                    f"ExecStart={sys.executable} -I -B {broker_script} "
                    f"{os.environ['PHANTOMVIEW_MATRIX_BROKER_SHA256']}\nTimeoutStartSec=15\n",
                    encoding="ascii",
                )
                systemctl("daemon-reload")
                host = SystemdRouteHost(
                    org=str(org),
                    config=str(config),
                    journal=str(pending),
                    committed=str(committed),
                    policy_lock=str(policy),
                    transaction_lock=str(transaction),
                    unit=viewer.name,
                    validate=lambda data: validate_reader(data, settings),
                    health=lambda: http_ready(port),
                    readiness_seconds=4,
                )

                def build(_authority):
                    return json.dumps(read_json(str(baseline)), sort_keys=True).encode()

                host.write_committed(config.read_bytes(), host.authority()[1])
                baseline.write_text(
                    json.dumps(initial | {"reader_uid": 970}), encoding="utf-8"
                )
                with self.assertRaises(RecoveryRequired):
                    reconcile_once(host, build)
                self.assertEqual(host.pending(), (build(None), host.authority()[1]))
                self.assertFalse(http_ready(port))
                # The guard may take ownership of a root-owned runtime directory.
                runtime.write_text(f"d {handoff} 0750 0 1059 -\n", encoding="ascii")
                self.assertEqual(reconcile_once(host, build), "recovered")
                self.assertFalse(pending.exists())
                self.assertTrue(
                    host.configuration_is_committed(build(None), host.authority()[1])
                )
                self.assertEqual(
                    (config.stat().st_gid, config.stat().st_mode & 0o777), (1001, 0o640)
                )
                self.assertEqual(get("/"), (200, [970, 970, [970, 1001, 1059, 1890]]))
                self.assertEqual(
                    (handoff.stat().st_uid, handoff.stat().st_gid), (970, 1059)
                )
                runtime.write_text(f"d {handoff} 0750 970 1059 -\n", encoding="ascii")
                systemctl("restart", viewer.name)
                self.assertTrue(host.healthy())
                self.assertEqual(
                    (handoff.stat().st_uid, handoff.stat().st_gid), (970, 1059)
                )

                systemctl("start", listener.name)
                self.assertEqual(matrix.stat().st_mode & 0o777, 0o750)
                self.assertEqual(probe(1001, 1001, [1001]).returncode, errno.EACCES)
                self.assertEqual(
                    probe(970, 970, [970, 1001, 1059, 1890]).returncode, errno.EACCES
                )
                systemctl("stop", listener.name)
                self.assertFalse(endpoint.exists())
                matrix.rmdir()

                for cycle in ("initial", "recreated"):
                    with self.subTest(cycle=cycle):
                        matrix.mkdir()
                        os.chown(matrix, 0, 1891)
                        matrix.chmod(0o750)
                        acl("-m", "u:970:--x", matrix)
                        systemctl("start", listener.name)
                        metadata = endpoint.stat()
                        self.assertEqual(
                            (
                                metadata.st_uid,
                                metadata.st_gid,
                                metadata.st_mode & 0o777,
                            ),
                            (0, 1891, 0o660),
                        )
                        self.assertEqual(
                            get("/api/matrix/v25"),
                            (200, {"version": "v25", "content": "synthetic v25"}),
                        )
                        self.assertEqual(
                            probe(1001, 1001, [1001]).returncode, errno.EACCES
                        )
                        # Independently reach the broker as UID 1001, using only trial ACLs.
                        acl("-m", "u:1001:--x", matrix)
                        acl("-m", "u:1001:-w-", endpoint)
                        rejected = probe(1001, 1001, [1001])
                        self.assertEqual(rejected.returncode, 0, rejected.stderr)
                        self.assertEqual(
                            json.loads(rejected.stdout), {"error": "matrix unavailable"}
                        )
                        systemctl("stop", listener.name)
                        self.assertFalse(endpoint.exists())
                        matrix.rmdir()
                self.assertEqual(reconcile_once(host, build), "unchanged")
            except Exception:
                subprocess.run(
                    [
                        "/usr/bin/journalctl",
                        "--no-pager",
                        "--lines=75",
                        "-u",
                        viewer.name,
                        "-u",
                        listener.name,
                        "-u",
                        f"{root.name}-matrix@*.service",
                    ],
                    check=False,
                    timeout=10,
                )
                raise
            finally:
                systemctl(
                    "stop",
                    listener.name,
                    viewer.name,
                    f"{root.name}-matrix@*.service",
                    check=False,
                )
                for unit in (viewer, listener, broker):
                    unit.unlink(missing_ok=True)
                systemctl("daemon-reload")

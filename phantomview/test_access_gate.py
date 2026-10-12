import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import phantomview as pv
from access_gate import Gate, SnapshotReader


class Invalid(ValueError):
    pass


class ProtocolDouble:
    """Adapter contract double; real signature verification belongs to PhantomBlog."""
    def __init__(self, identities):
        self.used = False
    def issue(self, authorization, origin, delivery):
        if authorization != "Nostr test-signed-event":
            raise Invalid()
        return delivery + "/#c=" + "c" * 43
    def redeem(self, code, callback):
        if self.used or code != "c" * 43:
            raise Invalid()
        result = callback()
        self.used = True
        return result


ACCESS = types.SimpleNamespace(AccessLinks=ProtocolDouble, core=types.SimpleNamespace(Invalid=Invalid),
                              public_origin=lambda origin, port: origin)


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.clock = [10]
        self.policy = {"identities": ["a" * 64], "actor": "coordinator", "role": "chief_of_staff"}
        self.gate = Gate(ACCESS, self.policy, "https://view.example:8790", 8789,
                         clock=lambda: self.clock[0])

    def test_exact_host_origin_and_fetch_boundary(self):
        self.assertEqual(self.gate.boundary({"Host": "127.0.0.1:8789"}, 8789), "http://127.0.0.1:8789")
        self.assertEqual(self.gate.boundary({"Host": "view.example:8790"}, 8789), self.gate.origin)
        for headers in ({"Host": "evil.example"}, {"Host": "view.example:8790", "Origin": "https://evil.example"},
                        {"Host": "view.example:8790", "Sec-Fetch-Site": "cross-site"},
                        {"Host": "127.0.0.1:8789", "X-Forwarded-Host": "view.example:8790", "Origin": self.gate.origin}):
            self.assertIsNone(self.gate.boundary(headers, 8789))

    def test_session_expiry_and_no_plaintext_storage(self):
        value = self.gate.create_session()
        self.assertNotIn(value, self.gate.sessions)
        headers = {"Cookie": "phantomview=" + value}
        self.assertTrue(self.gate.session(headers))
        owner, expiry = self.gate.session_scope(headers)
        self.assertEqual(owner, self.gate.digest(value))
        self.assertNotEqual(owner, value)
        self.assertGreater(expiry, 0)
        self.clock[0] += 1800
        self.assertFalse(self.gate.session(headers))
        with self.assertRaises(ValueError):
            self.gate.session_scope(headers)

    def test_single_use_logout_and_cookie_flags(self):
        value = self.gate.redeem("c" * 43)
        with self.assertRaises(Invalid):
            self.gate.redeem("c" * 43)
        cookie = self.gate.cookie(value)
        for flag in ("HttpOnly", "Secure", "SameSite=Strict", "Max-Age=1800"):
            self.assertIn(flag, cookie)
        headers = {"Cookie": "phantomview=" + value}
        self.gate.logout(headers)
        self.assertFalse(self.gate.session(headers))

    def test_fixed_index_reads_without_writing_or_source_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "index.json"
            data = {"snapshot": {"actors": []}, "config": {}}
            file.write_text(json.dumps(data))
            before = file.read_bytes()
            reader = SnapshotReader(file, self.policy)
            self.assertTrue(reader.refresh()["read_only"])
            self.assertEqual(file.read_bytes(), before)
            self.assertEqual(list(Path(tmp).iterdir()), [file])

    def test_missing_policy_and_unbounded_sessions_refused(self):
        for policy, seconds in (({}, 1800), (self.policy, 0), (self.policy, 3601)):
            with self.assertRaises(ValueError):
                Gate(ACCESS, policy, self.gate.origin, 8789, seconds)


class HttpAccessTests(unittest.TestCase):
    def setUp(self):
        self.gate = Gate(ACCESS, {"identities": ["a" * 64], "actor": "coordinator"}, "https://view.example:8790", 0)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), pv.Handler)
        self.server.gate = self.gate
        self.server.access_errors = (ValueError, Invalid)
        self.server.observatory = types.SimpleNamespace(data=lambda: {"read_only": True})
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request("POST" if body is not None else "GET", path, body,
                           {"Content-Type": "application/json", **(headers or {})})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), json.loads(response.read())
        connection.close()
        return result

    def test_signed_issuance_requires_exact_payload_and_no_query_credentials(self):
        headers = {"Authorization": "Nostr test-signed-event"}
        self.assertEqual(self.request("/api/access-link", "{}", headers)[0], 200)
        self.assertEqual(self.request("/api/access-link", "{ }", headers)[0], 400)
        self.assertEqual(self.request("/api/access-link?token=x", "{}", headers)[0], 400)
        self.assertEqual(self.request("/api/access-link", "{}")[0], 401)

    def test_human_session_cannot_configure_sources_and_logout_revokes_it(self):
        self.assertEqual(self.request("/api/state")[0], 401)
        status, headers, _ = self.request("/api/redeem", json.dumps({"code": "c" * 43}))
        self.assertEqual(status, 200)
        cookie = {"Cookie": headers["Set-Cookie"].split(";")[0]}
        self.assertEqual(self.request("/api/state", headers=cookie)[0], 200)
        self.assertEqual(self.request("/api/config", '{"org_files":["/etc/passwd"]}', cookie)[0], 403)
        self.assertEqual(self.request("/api/redeem", json.dumps({"code": "c" * 43}))[0], 401)
        self.assertEqual(self.request("/api/logout", "{}", cookie)[0], 200)
        self.assertEqual(self.request("/api/state", headers=cookie)[0], 401)

    def test_public_info_does_not_disclose_issuer_keys(self):
        status, _, body = self.request("/api/access-info")
        self.assertEqual(status, 200)
        self.assertEqual(body["actor"], "coordinator")
        self.assertNotIn("identities", body)


if __name__ == "__main__":
    unittest.main()

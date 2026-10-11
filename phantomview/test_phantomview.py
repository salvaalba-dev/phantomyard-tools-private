import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

import phantomview as pv


class ObservatoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.obs = pv.Observatory(self.root / "config.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_demo_inventory_and_explicit_unknown_runtime(self):
        data = self.obs.refresh()
        self.assertIsNone(data["error"])
        self.assertEqual(len(data["snapshot"]["actors"]), 5)
        self.assertTrue(all(a["installed"] is None and a["runtime"] == "unknown" for a in data["snapshot"]["actors"]))

    def test_refresh_without_changes_does_not_duplicate_history(self):
        self.obs.refresh()
        self.obs.refresh()
        self.assertEqual(len(self.obs.history), 1)

    def test_added_actor_and_role_change_have_history(self):
        org = pv.read_source(pv.HERE / "example-org.yaml")
        file = self.root / "org.json"
        pv.atomic_json(file, org)
        cfg = pv.default_config()
        cfg.update(mode="existing", org_files=[str(file)])
        self.obs.configure(cfg)
        org["actors"][0]["tools"].append("sheets")
        pv.atomic_json(file, org)
        self.obs.refresh()
        self.assertEqual(len(self.obs.history), 2)
        self.assertTrue(any(x["action"] == "changed" and x["entity"].endswith("atlas") for x in self.obs.history[-1]["changes"]))

    def test_invalid_source_keeps_last_good_snapshot_without_secret_excerpt(self):
        self.obs.refresh()
        original = self.obs.snapshot["digest"]
        broken = self.root / "broken.yaml"
        broken.write_text("secret: PRIVATE_TOKEN\nactors: [", encoding="utf8")
        self.obs.config["org_files"] = [str(broken)]
        data = self.obs.refresh()
        self.assertEqual(data["snapshot"]["digest"], original)
        self.assertNotIn("PRIVATE_TOKEN", data["error"])

    def test_profile_discovery_never_reads_or_modifies_identity_or_vault(self):
        persona = self.root / "personas" / "atlas"
        persona.mkdir(parents=True)
        (persona / "identity.json").write_text('NOT_READ_SECRET', encoding="utf8")
        (persona / "vault.sqlite").write_bytes(b"NEVER_TOUCH")
        for file in ("IDENTITY.md", "SOUL.md", "tools.md"):
            (persona / file).write_text("profile", encoding="utf8")
        (persona / "mcp.json").write_text(json.dumps({"mcpServers": {"drive": {"transport": "http", "url": "PRIVATE", "auth": {"valueRef": "SECRET"}}}}))
        before = {p.name:p.read_bytes() for p in persona.iterdir()}
        self.obs.config.update(mode="existing", personas_dir=str(persona.parent))
        data = self.obs.refresh()
        serialized = json.dumps(data)
        self.assertNotIn("NOT_READ_SECRET", serialized)
        self.assertNotIn("PRIVATE", serialized)
        self.assertNotIn("SECRET", serialized)
        self.assertEqual(before, {p.name:p.read_bytes() for p in persona.iterdir()})
        atlas = next(a for a in data["snapshot"]["actors"] if a["id"] == "atlas")
        self.assertEqual(atlas["integrations"][0]["id"], "drive")

    def test_cycles_and_unknown_references_are_findings(self):
        org = pv.read_source(pv.HERE / "example-org.yaml")
        org["roles"][0]["reports_to"] = "coordinador"
        org["actors"][0]["role"] = "missing"
        file = self.root / "org.json"
        pv.atomic_json(file, org)
        self.obs.config.update(mode="existing", org_files=[str(file)])
        data = self.obs.refresh()
        titles = [x["title"] for x in data["snapshot"]["findings"]]
        self.assertIn("Rol inexistente", titles)
        self.assertIn("Ciclo en jerarquía", titles)

    def test_duplicate_ids_are_rejected(self):
        org = pv.read_source(pv.HERE / "example-org.yaml")
        org["actors"].append(copy.deepcopy(org["actors"][0]))
        with self.assertRaises(ValueError):
            pv.validate_org(org)

    def test_path_traversal_ids_are_rejected(self):
        org = pv.read_source(pv.HERE / "example-org.yaml")
        org["actors"][0]["id"] = "../../secrets"
        with self.assertRaises(ValueError):
            pv.validate_org(org)

    def test_current_document_head_excludes_old_versions(self):
        doc = {"manifest":{"org":"demo"},"currentVersions":{"u":"new"},"nodes":[
            {"urn":"u","mac":"old","slug":"old","kind":"doc"},
            {"urn":"u","mac":"new","slug":"current","kind":"doc"}]}
        file = self.root / "docs.json"
        pv.atomic_json(file, doc)
        self.obs.config["docs_manifests"] = [str(file)]
        data = self.obs.refresh()
        self.assertEqual([x["slug"] for x in data["snapshot"]["documents"]], ["current"])

    def test_empty_new_setup_does_not_invent_people(self):
        cfg = pv.default_config()
        cfg.update(mode="new", org_files=[], docs_manifests=[], procedures_file="")
        data = self.obs.configure(cfg)
        self.assertEqual(data["snapshot"]["actors"], [])

    def test_auto_update_requires_explicit_version(self):
        cfg = pv.default_config()
        cfg["software_interval"] = 3600
        with self.assertRaises(ValueError):
            self.obs.validate_config(cfg)

    def test_update_rejects_untrusted_remote(self):
        with patch.object(pv, "git", side_effect=[str(self.root), "https://evil.invalid/repo.git"]):
            with self.assertRaises(ValueError):
                pv.update_software("v0.1.0")

    def test_configuration_switch_clears_previous_organization_snapshot(self):
        self.obs.refresh()
        cfg = pv.default_config()
        cfg.update(mode="existing", org_files=[str(self.root / "missing.yaml")], docs_manifests=[], procedures_file="")
        data = self.obs.configure(cfg)
        self.assertIsNone(data["snapshot"])
        self.assertIsNotNone(data["error"])


    def test_explicit_profiles_are_scoped_to_declared_organization(self):
        profile = self.root / "separate-account" / "iris"
        profile.mkdir(parents=True)
        for name in ("IDENTITY.md", "SOUL.md"):
            (profile / name).write_text("private profile content", encoding="utf-8")
        (profile / "tools").mkdir()
        cfg = pv.default_config()
        cfg.update(mode="existing", persona_paths={"demo:iris": str(profile)})
        data = self.obs.configure(cfg)
        self.assertIsNone(data["error"])
        iris = next(a for a in data["snapshot"]["actors"] if a["id"] == "iris")
        self.assertTrue(iris["installed"])
        self.assertEqual(iris["profile_path"], str(profile.resolve()))
        self.assertNotIn("private profile content", json.dumps(data))
        self.assertFalse(any("tools.md" in f["title"] for f in data["snapshot"]["findings"]))
        self.assertTrue(any("sin ruta" in f["title"] for f in data["snapshot"]["findings"]))
        cfg["persona_paths"] = {"other:iris": str(profile)}
        self.assertIsNotNone(self.obs.configure(cfg)["error"])

    def test_same_profile_cannot_be_mapped_to_two_setups(self):
        cfg = pv.default_config()
        cfg["persona_paths"] = {"demo:iris": str(self.root), "other:iris": str(self.root)}
        with self.assertRaises(ValueError):
            self.obs.validate_config(cfg)

    def test_manifest_from_other_setup_is_rejected(self):
        manifest = pv.read_source(pv.HERE / "example-docs.yaml")
        manifest["manifest"]["org"] = "other"
        source = self.root / "foreign.json"
        pv.atomic_json(source, manifest)
        cfg = pv.default_config()
        cfg.update(mode="existing", docs_manifests=[str(source)])
        data = self.obs.configure(cfg)
        self.assertIsNotNone(data["error"])
        self.assertIsNone(data["snapshot"])


    def test_remote_persona_is_declared_without_local_probe(self):
        cfg = pv.default_config()
        cfg.update(mode="existing", remote_personas={"demo:iris": "PC local"}, persona_paths={"demo:atlas": str(self.root / "atlas")})
        data = self.obs.configure(cfg)
        self.assertIsNone(data["error"])
        iris = next(a for a in data["snapshot"]["actors"] if a["id"] == "iris")
        self.assertIsNone(iris["installed"])
        self.assertEqual(iris["runtime"], "unknown")
        self.assertTrue(iris["profile_remote"])
        self.assertEqual(iris["profile_location"], "PC local")
        self.assertFalse(any(f["entity"] == iris["key"] and "sin ruta" in f["title"] for f in data["snapshot"]["findings"]))
        cfg["persona_paths"]["demo:iris"] = str(self.root / "iris")
        with self.assertRaises(ValueError):
            self.obs.validate_config(cfg)

    def test_document_parent_mac_resolves_without_importing_raw_metadata(self):
        manifest = pv.read_source(pv.HERE / "example-docs.yaml")
        manifest["nodes"][0]["mac"] = "parent-hash"
        manifest["nodes"][1].pop("parent")
        manifest["nodes"][1]["parentMac"] = "parent-hash"
        manifest["nodes"][1]["meta"] = {"unexpected_secret": "do-not-collect"}
        file = self.root / "docs.json"
        pv.atomic_json(file, manifest)
        cfg = pv.default_config()
        cfg.update(mode="existing", docs_manifests=[str(file)])
        data = self.obs.configure(cfg)
        self.assertIsNone(data["error"])
        self.assertEqual(data["snapshot"]["documents"][1]["parent"], manifest["nodes"][0]["urn"])
        self.assertNotIn("do-not-collect", json.dumps(data))


    def test_reciprocal_conditional_escalation_is_review_not_runtime_failure(self):
        org = pv.read_source(pv.HERE / "example-org.yaml")
        a, b = org["roles"][0]["id"], org["roles"][1]["id"]
        org["escalation_matrix"] = [{"from": a, "to": b, "condition": "delegation"}, {"from": b, "to": a, "condition": "unresolved"}]
        file = self.root / "org.json"
        pv.atomic_json(file, org)
        cfg = pv.default_config()
        cfg.update(mode="existing", org_files=[str(file)])
        data = self.obs.configure(cfg)
        findings = [f for f in data["snapshot"]["findings"] if "escalado" in f["title"]]
        self.assertTrue(findings)
        self.assertTrue(all(f["severity"] == "warning" for f in findings))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), pv.Handler)
        self.server.token = "test-session-token"
        self.server.observatory = pv.Observatory(Path(self.tmp.name) / "config.json")
        self.server.observatory.refresh()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def test_anonymous_api_denied(self):
        with self.assertRaises(HTTPError) as ctx:
            urlopen(self.url + "/api/state")
        self.assertEqual(ctx.exception.code, 401)

    def test_authenticated_api_and_csp(self):
        req = Request(self.url + "/api/state", headers={"Authorization":"Bearer test-session-token"})
        with urlopen(req) as response:
            self.assertEqual(json.load(response)["version"], pv.VERSION)
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_cross_origin_and_dns_rebinding_denied(self):
        for headers in ({"Origin":"https://evil.invalid"},{"Host":"evil.invalid"}):
            headers["Authorization"] = "Bearer test-session-token"
            with self.assertRaises(HTTPError) as ctx:
                urlopen(Request(self.url + "/api/state", headers=headers))
            self.assertEqual(ctx.exception.code, 403)

    def test_static_path_traversal_denied(self):
        with self.assertRaises(HTTPError) as ctx:
            urlopen(self.url + "/../phantomview.py")
        self.assertEqual(ctx.exception.code, 404)

    def test_unauthenticated_config_write_denied(self):
        with self.assertRaises(HTTPError) as ctx:
            urlopen(Request(self.url + "/api/config", data=b"{}", headers={"Content-Type":"application/json"}))
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()

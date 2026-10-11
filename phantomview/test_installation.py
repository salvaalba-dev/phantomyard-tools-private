"""Inventory boundaries, observations and dependency validation."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import installation as inventory


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"version": 1, "components": [
            {"id": "viewer", "org": "au", "name": "Viewer", "kind": "phantomyard", "probe": {}},
            {"id": "python", "org": "au", "name": "Python", "kind": "runtime", "probe": {"type": "python"}}
        ], "relations": [{"from": "viewer", "to": "python", "type": "requires"}]}

    def test_distinguishes_declarations_from_actual_runtime_version(self):
        data = inventory.collect(self.manifest, [], {"au"}, "manifest.json")
        self.assertEqual(data["components"][0]["evidence"], "declared")
        self.assertEqual(data["components"][0]["status"], "unknown")
        self.assertEqual(data["components"][1]["evidence"], "checked")
        self.assertTrue(data["components"][1]["version"])
        self.assertEqual(data["relations"][0]["evidence"], "declared")

    def test_rejects_foreign_setup_and_dangling_edges(self):
        for field, value in (("org", "rakocy"), ("id", "viewer")):
            manifest = copy.deepcopy(self.manifest)
            manifest["components"][1][field] = value
            with self.assertRaises(ValueError):
                inventory.collect(manifest, [], {"au"}, "manifest.json")
        self.manifest["relations"][0]["to"] = "unselected"
        with self.assertRaises(ValueError):
            inventory.collect(self.manifest, [], {"au"}, "manifest.json")

    def test_no_arbitrary_commands_and_strict_systemd_unit(self):
        for probe in ({"type": "command", "command": "cat /etc/shadow"},
                      {"type": "systemd", "unit": "--help"},
                      {"type": "systemd", "unit": "a.service;reboot"},
                      {"type": "distribution", "name": "../../vault"}):
            with self.assertRaises(ValueError), patch("installation.subprocess.run") as execute:
                inventory.observe(probe)
            execute.assert_not_called()

    def test_systemd_observation_is_bounded_and_does_not_read_credentials(self):
        response = type("Result", (), {"stdout": "LoadState=loaded\nActiveState=active\nSubState=running\n"})()
        with patch("installation.subprocess.run", return_value=response) as execute:
            evidence, status, _, _ = inventory.observe({"type": "systemd", "unit": "viewer.service"})
        self.assertEqual((evidence, status), ("checked", "active"))
        self.assertEqual(execute.call_args.args[0], ["systemctl", "show", "viewer.service", "--property=LoadState,ActiveState,SubState"])
        self.assertEqual(execute.call_args.kwargs["timeout"], 4)
        self.assertNotIn("shell", execute.call_args.kwargs)

    def test_path_probe_reads_presence_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile"
            path.mkdir()
            (path / "identity.json").write_text("DO_NOT_READ")
            result = inventory.observe({"type": "path", "path": str(path)})
            self.assertEqual(result[:2], ("detected", "present"))
            self.assertNotIn("DO_NOT_READ", str(result))

    def test_persona_tool_bindings_must_stay_inside_selected_setup(self):
        actors = [{"id": "paco", "key": "au:actors:paco", "org": "au", "tools": ["email"], "source": "org.yaml"}]
        self.manifest["tool_bindings"] = [{"org": "au", "tool": "email", "component": "viewer"}]
        self.manifest["persona_bindings"] = [{"actor": "au:actors:paco", "component": "viewer"}]
        data = inventory.collect(self.manifest, actors, {"au"}, "manifest.json")
        self.assertTrue(any(e["from"] == "persona:au:actors:paco" and e["to"] == "viewer" for e in data["relations"]))
        self.manifest["persona_bindings"][0]["actor"] = "rakocy:actors:rakocy"
        with self.assertRaises(ValueError):
            inventory.collect(self.manifest, actors, {"au"}, "manifest.json")


if __name__ == "__main__":
    unittest.main()

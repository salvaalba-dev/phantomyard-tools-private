import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import diagnostics as d
import phantomview as pv


class DiagnosticTests(unittest.TestCase):
    def native(self):
        return {"persona": "atlas", "vault": {"token": "SECRET"},
                "telegram": {"personas": [{"persona": "atlas", "stated": True, "healthy": True, "detail": "SECRET"},
                                            {"persona": "foreign", "healthy": False}]},
                "phantomchat": {"personas": [{"persona": "atlas", "stated": False, "healthy": True, "npub": "PRIVATE"}]},
                "timers": {"heartbeat": {"stale": True, "age_minutes": 80, "threshold_minutes": 75},
                           "tick": {"stale": False, "age_minutes": 1, "threshold_minutes": 5}}}

    def target(self):
        return {"org": "example", "persona": "atlas", "user": "pb-atlas", "unit": "phantombot-pb-atlas.service"}

    def test_native_allowlist_and_exact_persona(self):
        checks = d.normalize_native(self.native(), "atlas")
        self.assertEqual([r["status"] for r in checks], ["ok", "not-configured", "attention", "ok"])
        self.assertNotIn("SECRET", json.dumps(checks))
        self.assertNotIn("PRIVATE", json.dumps(checks))
        with self.assertRaises(ValueError):
            d.normalize_native(self.native(), "foreign")

    def test_missing_and_non_boolean_health_stays_unknown(self):
        report = self.native()
        report["telegram"]["personas"][0]["healthy"] = "false"
        report["timers"]["heartbeat"]["stale"] = None
        checks = d.normalize_native(report, "atlas")
        self.assertEqual(checks[0]["status"], "unknown")
        self.assertEqual(checks[2]["status"], "unknown")

    def test_fixed_commands_disable_repairs_and_bound_runtime(self):
        calls = []
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            content = "LoadState=loaded\nActiveState=active\nSubState=running\n" if command[0] == "systemctl" else json.dumps(self.native())
            return subprocess.CompletedProcess(command, 0, content, "SECRET")
        result = d.collect_target(self.target(), "/installed/phantombot", runner)
        self.assertEqual(result["checks"][0]["status"], "ok")
        self.assertEqual(calls[1][0][-5:], ["doctor", "--persona", "atlas", "--no-repair", "--json"])
        self.assertEqual(calls[1][1]["timeout"], 8)
        self.assertNotIn("SECRET", json.dumps(result))

    def test_timeout_keeps_separate_service_evidence(self):
        def runner(command, **kwargs):
            if command[0] == "systemctl":
                return subprocess.CompletedProcess(command, 0, "LoadState=loaded\nActiveState=active", "")
            raise subprocess.TimeoutExpired(command, 8, output="SECRET")
        result = d.collect_target(self.target(), "/installed/phantombot", runner)
        self.assertEqual(result["doctor_error"], "timeout")
        self.assertEqual(result["checks"], [{"id": "service", "status": "ok"}])

    def test_target_cannot_select_another_user_or_command(self):
        self.assertEqual(len(d.validate_targets({"targets": [self.target()]})), 1)
        for field, value in (("user", "root"), ("unit", "other.service"), ("persona", "atlas; echo SECRET")):
            row = self.target()
            row[field] = value
            with self.assertRaises(ValueError):
                d.validate_targets({"targets": [row]})

    def test_import_rejects_future_dates_duplicates_and_unknown_checks(self):
        report = {"schema": 1, "personas": [{"key": "example:atlas", "checked_at": d.timestamp(), "checks": [{"id": "service", "status": "ok"}]}]}
        self.assertIn("example:atlas", d.safe_rows(report))
        bad = copy.deepcopy(report)
        bad["personas"][0]["checked_at"] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with self.assertRaises(ValueError): d.safe_rows(bad)
        bad = copy.deepcopy(report)
        bad["personas"].append(bad["personas"][0])
        with self.assertRaises(ValueError): d.safe_rows(bad)
        bad = copy.deepcopy(report)
        bad["personas"][0]["checks"][0]["id"] = "private-key"
        with self.assertRaises(ValueError): d.safe_rows(bad)

    def test_import_scopes_actors_and_ignores_volatile_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            obs = pv.Observatory(root / "config.json")
            profile = root / "atlas"
            profile.mkdir()
            report_file = root / "diagnostics.json"
            report = {"schema": 1, "personas": [{"key": "example:atlas", "checked_at": d.timestamp(), "checks": [{"id": "service", "status": "ok"}, {"id": "heartbeat", "status": "ok", "age_minutes": 1, "threshold_minutes": 75}]}]}
            org = pv.read_source(pv.HERE / "example-org.yaml")["organization"]["id"]
            report["personas"][0]["key"] = org + ":atlas"
            pv.atomic_json(report_file, report)
            obs.config.update(mode="existing", persona_paths={org + ":atlas": str(profile)}, diagnostics_file=str(report_file))
            data = obs.refresh()
            self.assertIsNone(data["error"])
            atlas = next(a for a in data["snapshot"]["actors"] if a["id"] == "atlas")
            self.assertEqual(atlas["runtime"], "observed")
            self.assertEqual(sum("diagnostics" in a for a in data["snapshot"]["actors"]), 1)
            count = len(obs.history)
            report["personas"][0]["checked_at"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
            report["personas"][0]["checks"][1]["age_minutes"] = 2
            pv.atomic_json(report_file, report)
            self.assertIsNone(obs.refresh()["error"])
            self.assertEqual(len(obs.history), count)
            obs.config["persona_paths"] = {}
            obs.config["remote_personas"] = {org + ":atlas": "Another PC"}
            atlas = next(a for a in obs.refresh()["snapshot"]["actors"] if a["id"] == "atlas")
            self.assertNotIn("diagnostics", atlas)


if __name__ == "__main__": unittest.main()

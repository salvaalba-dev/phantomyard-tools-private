"""Local PhantomBot observations. Fixed commands, no repairs, no raw report exports."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
ERRORS = {"timeout", "unavailable", "invalid-report"}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def boolean(value):
    return value if type(value) is bool else None


def normalize_native(report, persona):
    """Allowlist health flags only; discard keys, contacts, logs, paths and detail strings."""
    if not isinstance(report, dict) or report.get("persona") != persona:
        raise ValueError("Unexpected diagnostic persona")
    checks = []
    for channel in ("telegram", "phantomchat"):
        group = report.get(channel, {})
        rows = group.get("personas", []) if isinstance(group, dict) else []
        if not isinstance(rows, list):
            continue
        row = next((r for r in rows if isinstance(r, dict) and r.get("persona") == persona), None)
        if row is None:
            continue
        stated, healthy = boolean(row.get("stated")), boolean(row.get("healthy"))
        status = "not-configured" if stated is False else "ok" if healthy is True else "attention" if healthy is False else "unknown"
        checks.append({"id": channel, "status": status})
    timers = report.get("timers", {})
    if isinstance(timers, dict):
        for name in ("heartbeat", "tick"):
            row = timers.get(name)
            if not isinstance(row, dict):
                continue
            stale = boolean(row.get("stale"))
            checks.append({"id": name, "status": "attention" if stale is True else "ok" if stale is False else "unknown",
                           "age_minutes": number(row.get("age_minutes")),
                           "threshold_minutes": number(row.get("threshold_minutes"))})
    return checks


def validate_targets(data):
    rows = data.get("targets") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise ValueError("Expected 1–50 explicit local targets")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) and IDENTIFIER.fullmatch(row[k]) for k in ("org", "persona")):
            raise ValueError("Invalid diagnostic target")
        key = row["org"] + ":" + row["persona"]
        if key in seen or row.get("user") != "pb-" + row["persona"] or row.get("unit") != "phantombot-pb-" + row["persona"] + ".service":
            raise ValueError("Target must name its exact persona user and service")
        seen.add(key)
    return rows


def collect_target(row, executable, runner=subprocess.run):
    result = {"key": row["org"] + ":" + row["persona"], "checked_at": timestamp(), "checks": []}
    try:
        process = runner(["systemctl", "show", row["unit"], "--property=LoadState,ActiveState,SubState"], capture_output=True, text=True, timeout=4, check=False)
        values = dict(line.split("=", 1) for line in process.stdout.splitlines() if "=" in line)
        loaded, active = values.get("LoadState"), values.get("ActiveState")
        status = "ok" if loaded == "loaded" and active == "active" else "attention" if loaded == "not-found" or active in ("failed", "inactive") else "unknown"
        result["checks"].append({"id": "service", "status": status})
    except (OSError, subprocess.TimeoutExpired):
        result["checks"].append({"id": "service", "status": "unknown"})
    try:
        process = runner([shutil.which("runuser") or "/usr/sbin/runuser", "-u", row["user"], "--", str(executable),
                          "doctor", "--persona", row["persona"], "--no-repair", "--json"],
                         capture_output=True, text=True, timeout=8, check=False)
        if len(process.stdout) > 262144:
            raise ValueError("Diagnostic report exceeds bounds")
        result["checks"].extend(normalize_native(json.loads(process.stdout), row["persona"]))
    except subprocess.TimeoutExpired:
        result["doctor_error"] = "timeout"
    except OSError:
        result["doctor_error"] = "unavailable"
    except (ValueError, TypeError):
        result["doctor_error"] = "invalid-report"
    result["checked_at"] = timestamp()
    return result


def safe_rows(report):
    """Validate an imported export and reconstruct only the public diagnostic schema."""
    if not isinstance(report, dict) or report.get("schema") != 1 or not isinstance(report.get("personas"), list) or len(report["personas"]) > 50:
        raise ValueError("Invalid local diagnostic export")
    output = {}
    for row in report["personas"]:
        if not isinstance(row, dict):
            raise ValueError("Invalid diagnostic row")
        key = row.get("key", "")
        parts = key.split(":") if isinstance(key, str) else []
        if len(parts) != 2 or not all(IDENTIFIER.fullmatch(x) for x in parts) or key in output:
            raise ValueError("Invalid diagnostic key")
        date = row.get("checked_at")
        try:
            parsed = datetime.fromisoformat(date)
            if parsed.tzinfo is None or (parsed - datetime.now(timezone.utc)).total_seconds() > 60:
                raise ValueError("Invalid diagnostic date")
        except (TypeError, ValueError):
            raise ValueError("Invalid diagnostic date") from None
        checks = row.get("checks")
        if not isinstance(checks, list) or len(checks) > 5:
            raise ValueError("Invalid diagnostic checks")
        clean, seen = [], set()
        for check in checks:
            if not isinstance(check, dict) or check.get("id") not in {"service", "telegram", "phantomchat", "heartbeat", "tick"} or check.get("id") in seen or check.get("status") not in {"ok", "attention", "unknown", "not-configured"}:
                raise ValueError("Invalid diagnostic check")
            seen.add(check["id"])
            item = {"id": check["id"], "status": check["status"]}
            if check["id"] in {"heartbeat", "tick"}:
                item.update(age_minutes=number(check.get("age_minutes")), threshold_minutes=number(check.get("threshold_minutes")))
            clean.append(item)
        output[key] = {"checked_at": parsed.isoformat(), "checks": clean, "stale_after_seconds": 900,
                       "doctor_error": row.get("doctor_error") if row.get("doctor_error") in ERRORS else None}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    executable = Path(args.executable)
    if not executable.is_absolute() or not executable.is_file():
        parser.error("An installed PhantomBot executable is required")
    targets = validate_targets(json.loads(Path(args.targets).read_text(encoding="utf8")))
    report = {"schema": 1, "checked_at": timestamp(), "personas": [collect_target(row, executable) for row in targets]}
    safe_rows(report)
    output = Path(args.output)
    temporary = output.with_suffix(output.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf8") as stream:
        json.dump(report, stream, indent=2)
    os.chmod(temporary, 0o600)
    os.replace(temporary, output)
    print("Local diagnostic export updated:", len(targets), "personas")


if __name__ == "__main__":
    main()

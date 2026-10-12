"""Resolve the default persona in an explicitly selected PhantomBot runtime."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")


def safe_default(report):
    row = report.get("default_persona") if isinstance(report, dict) else None
    if not isinstance(row, dict) or not isinstance(row.get("resolved"), str) or not IDENTIFIER.fullmatch(row["resolved"]):
        raise ValueError("Default persona unavailable")
    if row.get("provenance") not in {"env", "state", "config", "builtin"}:
        raise ValueError("Default persona provenance unavailable")
    if row.get("exists") is not True or row.get("served") is not True:
        raise ValueError("Default persona is not available in this runtime")
    return {"persona": row["resolved"], "provenance": row["provenance"]}


def attach(report, actors):
    """Only resolve a selected local actor; never grant issuer permissions."""
    clean = safe_default({"default_persona": dict(report, resolved=report.get("persona"))})
    date = datetime.fromisoformat(report["checked_at"])
    if date.tzinfo is None or (date - datetime.now(timezone.utc)).total_seconds() > 60:
        raise ValueError("Invalid default persona observation time")
    actor = next((a for a in actors if a["org"] == report.get("org") and a["id"] == clean["persona"] and not a.get("profile_remote")), None)
    if not actor:
        raise ValueError("Default persona is outside the selected local setup")
    npub = actor.get("channels", {}).get("npub", "")
    return dict(clean, org=actor["org"], key=actor["key"], checked_at=date.isoformat(),
                npub=npub if isinstance(npub, str) and re.fullmatch(r"npub1[023456789acdefghjklmnpqrstuvwxyz]{58}", npub) else "")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True)
    parser.add_argument("--org", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"pb-[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", args.user) or not IDENTIFIER.fullmatch(args.org):
        parser.error("An explicit persona runtime and organization are required")
    executable = Path(args.executable)
    if not executable.is_absolute() or not executable.is_file():
        parser.error("An installed PhantomBot executable is required")
    # Do not pass --persona: that would override the default being observed.
    process = subprocess.run([shutil.which("runuser") or "/usr/sbin/runuser", "-u", args.user, "--", str(executable),
                              "doctor", "--no-repair", "--json"], capture_output=True, text=True, timeout=10, check=False)
    if len(process.stdout) > 262144:
        raise ValueError("Diagnostic report exceeds bounds")
    clean = safe_default(json.loads(process.stdout))
    clean.update(org=args.org, checked_at=datetime.now(timezone.utc).isoformat(), exists=True, served=True)
    output = Path(args.output)
    temporary = output.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf8") as stream:
        json.dump(clean, stream)
    os.chmod(temporary, 0o600)
    os.replace(temporary, output)
    print("Default persona observation updated:", clean["persona"], clean["provenance"])


if __name__ == "__main__":
    main()

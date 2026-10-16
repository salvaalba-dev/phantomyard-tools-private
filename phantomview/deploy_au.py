"""Explicit AU pilot installer. Run only after reviewing and approving deployment."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import zipfile

import yaml


def public_hex(value):
    # NIP-19 public key only. Reject nsec and all other identifiers.
    if not isinstance(value, str) or not value.startswith("npub1") or len(value) != 63 or value != value.lower():
        raise ValueError("Expected an npub public key")
    digits = ["qpzry9x8gf2tvdw0s3jn54khce6mua7l".index(c) for c in value[5:]]
    expanded = [ord(c) >> 5 for c in "npub"] + [0] + [ord(c) & 31 for c in "npub"]
    checksum = 1
    for digit in expanded + digits:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ digit
        for bit, generator in enumerate((0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)):
            if top >> bit & 1:
                checksum ^= generator
    if checksum != 1:
        raise ValueError("Invalid public key checksum")
    result, accumulator, bits = bytearray(), 0, 0
    for digit in digits[:-6]:
        accumulator = (accumulator << 5) | digit
        bits += 5
        if bits >= 8:
            bits -= 8
            result.append((accumulator >> bits) & 255)
    if len(result) != 32 or bits >= 5 or ((accumulator << (8 - bits)) & 255):
        raise ValueError("Invalid public key")
    return bytes(result).hex()


def main():
    import grp
    import pwd
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--apply", action="store_true", help="Install only after human approval")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError("Service installation requires an administrator")
    source = Path("/opt/phantomview-au")
    state = Path("/var/lib/phantomview-au")
    units = [Path("/etc/systemd/system") / name for name in
             ("phantomview-au-collect.service", "phantomview-au-collect.timer", "phantomview-au.service")]
    if any(path.exists() for path in [source, state, *units]):
        raise ValueError("A PhantomView AU destination already exists; refusing to overwrite it")
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    if len(config.get("org_files", [])) != 1 or config.get("software_interval"):
        raise ValueError("The pilot requires one organization and manual software updates")
    org = yaml.safe_load(Path(config["org_files"][0]).read_text())
    if org.get("organization", {}).get("id") != "aquaponics-united":
        raise ValueError("This installer is limited to AU")
    actor = next(a for a in org["actors"] if a["id"] == args.actor)
    if actor["role"] != args.role:
        raise ValueError("The persona role does not match the organization model")
    policy = {"identities": [public_hex(actor["npub"])], "actor": args.actor, "role": args.role,
              "request_instructions": "Request a temporary PhantomView URL from the responsible persona."}
    sys.path.insert(0, "/opt/phantomblog-tool")
    from phantomblog import access
    access.public_origin(args.origin, 8789)
    access.AccessLinks(policy["identities"])
    access._signer()
    for port in (8789, 8790):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise ValueError(f"Port {port} is occupied")
    pwd.getpwnam("aunited")
    gid = grp.getgrnam("aunited").gr_gid
    print("Plan: /opt/phantomview-au; /var/lib/phantomview-au; 3 dedicated units; reader aunited; loopback port 8789.")
    print("Configure the HTTPS proxy on port 8790 separately. Existing profiles and services remain unchanged.")
    if not args.apply:
        return
    # Validate the entire archive before writing any member.
    with zipfile.ZipFile(args.bundle) as archive:
        members = [member for member in archive.infolist() if member.filename.startswith("phantomview/") and not member.is_dir()]
        if not members or sum(member.file_size for member in members) > 16_000_000:
            raise ValueError("Invalid bundle")
        names = [Path(member.filename).name for member in members]
        if len(set(names)) != len(names) or not {"phantomview.py", "access_gate.py", "app.js", "index.html", "style.css", "logo.png"}.issubset(names):
            raise ValueError("Incomplete or duplicate bundle")
        for member in members:
            relative = Path(member.filename).relative_to("phantomview")
            if len(relative.parts) != 1 or relative.name.startswith("."):
                raise ValueError("Bundle path is not allowed")
        source.mkdir(mode=0o755)
        for member in members:
            target = source / Path(member.filename).name
            target.write_bytes(archive.read(member))
            target.chmod(0o644)
    state.mkdir(mode=0o750)
    os.chown(state, 0, gid)
    private, shared = state / "collector", state / "reader"
    private.mkdir(mode=0o700)
    shared.mkdir(mode=0o750)
    os.chown(shared, 0, gid)
    shared.chmod(0o2750)
    config["sync_interval"] = 300
    (private / "config.json").write_text(json.dumps(config, ensure_ascii=False))
    (private / "config.json").chmod(0o600)
    (shared / "access.json").write_text(json.dumps(policy, ensure_ascii=False))
    os.chown(shared / "access.json", 0, gid)
    (shared / "access.json").chmod(0o640)
    collector = f"""[Unit]
Description=PhantomView AU selected-source collector
[Service]
Type=oneshot
UMask=0027
ExecStart=/usr/bin/python3 {source}/phantomview.py --config {private}/config.json sync --export {shared}/index.json
ExecStartPost=/bin/chmod 0640 {shared}/index.json
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
RestrictAddressFamilies=AF_UNIX
ReadWritePaths={state}
"""
    timer = """[Unit]
Description=Refresh PhantomView AU every five minutes
[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Persistent=true
[Install]
WantedBy=timers.target
"""
    viewer = f"""[Unit]
Description=PhantomView AU read-only dashboard
After=network.target phantomview-au-collect.service
[Service]
User=aunited
Group=aunited
ExecStart=/usr/bin/python3 {source}/phantomview.py serve --port 8789 --reader-index {shared}/index.json --access-policy {shared}/access.json --access-module-dir /opt/phantomblog-tool --public-origin {args.origin} --session-seconds 1800
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
RestrictAddressFamilies=AF_INET AF_UNIX
[Install]
WantedBy=multi-user.target
"""
    for unit, content in zip(units, (collector, timer, viewer)):
        unit.write_text(content)
        unit.chmod(0o644)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "start", "phantomview-au-collect.service"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "phantomview-au-collect.timer", "phantomview-au.service"], check=True)
    print("Dedicated services installed. Verify the index, then configure the private proxy.")


if __name__ == "__main__":
    main()

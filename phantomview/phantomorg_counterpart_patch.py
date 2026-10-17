"""Prepare only the reviewed counterpart proposal in a disposable source tree."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def patch(root):
    root = Path(root).absolute()
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError("Source root must not contain symlinks")
    bundle = Path(__file__).resolve().parent
    manifest = json.loads((bundle / "phantomorg-counterpart-source.json").read_text(encoding="utf-8"))
    proposal = bundle / "phantomorg-counterpart.patch"
    if hashlib.sha256(proposal.read_bytes()).hexdigest() != manifest["patch_sha256"]:
        raise ValueError("Counterpart proposal checksum mismatch")
    for name, expected in manifest["inputs"].items():
        target = root / name
        if any(path.is_symlink() for path in (target, *target.parents)):
            raise ValueError("Source paths must not contain symlinks")
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError("Unsupported PhantomOrg source; use the pinned disposable tree")
    # Exact input checks and Git's full patch check happen before any writes.
    command = ["git", "apply", "--whitespace=error", str(proposal)]
    subprocess.run(command[:2] + ["--check"] + command[2:], cwd=root, check=True,
                   capture_output=True, text=True)
    subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 phantomorg_counterpart_patch.py /disposable/source/root")
    patch(sys.argv[1])
    print("Prepared explicit counterpart proposal; no live policy or access changed")

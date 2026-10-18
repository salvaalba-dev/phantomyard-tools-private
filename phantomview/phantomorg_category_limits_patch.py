"""Apply the restriction overlay only to the exact historical private proposal."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_text(encoding='utf-8').replace('\r\n', '\n').encode()).hexdigest()


def patch(root):
    root = Path(root).absolute()
    bundle = Path(__file__).resolve().parent
    manifest = json.loads((bundle / 'phantomorg-category-limits.manifest.json').read_text(encoding='utf-8'))
    base = json.loads((bundle / manifest['base_proposal']).read_text(encoding='utf-8'))
    proposal = bundle / 'phantomorg-category-limits.patch'
    if digest(proposal) != manifest['patch_sha256']:
        raise ValueError('Category limit proposal checksum mismatch')
    required = {name: row['result_sha256_lf'] for name, row in base['files'].items()}
    for name, row in manifest['files'].items():
        if name in required and required[name] != row['input_sha256_lf']:
            raise ValueError('Category limit proposal baseline mismatch')
        required[name] = row['input_sha256_lf']
    for name, expected in required.items():
        target = root / name
        if (Path(name).is_absolute() or '..' in Path(name).parts
                or any(path.is_symlink() for path in (target, *target.parents))):
            raise ValueError('Source paths must be relative and contain no symlinks')
        if expected is None:
            if target.exists():
                raise ValueError('Category limit proposal requires a new path')
        elif not target.is_file() or digest(target) != expected:
            raise ValueError('Unsupported PhantomOrg source; prepare the exact historical private proposal first')
    command = ['git', 'apply', '--whitespace=error', str(proposal)]
    subprocess.run(command[:2] + ['--check'] + command[2:], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
    for name, row in manifest['files'].items():
        if digest(root / name) != row['output_sha256_lf']:
            raise ValueError('Category limit proposal result mismatch; discard this disposable source tree')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 phantomorg_category_limits_patch.py /disposable/source/root')
    patch(sys.argv[1])
    print('Prepared restriction-only policy overlay; no live policy or access changed')

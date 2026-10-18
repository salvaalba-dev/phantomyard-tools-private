"""Read-only compatibility check for the private native host design.

Matching source is a review baseline, never evidence of runtime isolation.
No imports from the inspected checkout are executed.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

SOURCE_REVISION = '5af27060327ee8c53fe730dd8b98b6b305c62add'
ROOT_FILES = ('AGENTS.md', 'README.md', 'package.json', 'bun.lock',
              'bunfig.toml', 'tsconfig.json', 'tsconfig.engine.json')
MAX_FILES = 4096
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
BASELINE = Path(__file__).with_name('native-host-review.json')


def _walk_failure(_error):
    raise ValueError('Source tree cannot be fully inspected')


def snapshot(root):
    """Fingerprint every src file plus fixed dependency/build/contributor inputs.

    Normalize line endings only. Reject linked entries and bound traversal/read
    work. The caller must provide an offline, quiescent source copy: these checks
    are not a race-resistant filesystem sandbox or a source authenticity proof.
    """
    root = Path(os.path.abspath(root))
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ValueError('Source paths must not contain symlinks')
    source = root / 'src'
    if source.is_symlink() or not source.is_dir():
        raise ValueError('An offline native source tree is required')
    names = list(ROOT_FILES)
    entries = 0
    for directory, dirs, files in os.walk(source, followlinks=False, onerror=_walk_failure):
        for name in dirs + files:
            entries += 1
            if entries > MAX_FILES or (Path(directory) / name).is_symlink():
                raise ValueError('Source tree is linked or exceeds review bounds')
        names.extend((Path(directory) / name).relative_to(root).as_posix() for name in files)
    if len(names) > MAX_FILES:
        raise ValueError('Source tree exceeds review bounds')
    digest = hashlib.sha256()
    total = 0
    for name in sorted(names):
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Source review requires regular files')
        with path.open('rb') as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        total += len(raw)
        if len(raw) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError('Source tree exceeds review bounds')
        normalized = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').encode()
        digest.update(name.encode('utf-8') + b'\0' + hashlib.sha256(normalized).digest())
    return {'files': len(names), 'sha256': digest.hexdigest()}


def review(root, trust_boundary='isolated'):
    if trust_boundary not in ('isolated', 'daemon'):
        raise ValueError('An explicit supported trust boundary is required')
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    observed = snapshot(root)
    if (baseline['source_revision'] != SOURCE_REVISION or observed != baseline['snapshot']):
        raise ValueError('Native source differs from the reviewed baseline; review the installed release first')
    report = {'source_revision': SOURCE_REVISION, 'source_matches_review': True,
            'snapshot': observed, 'activation_ready': False,
            'required_work': ['isolated-native-host', 'protected-signing-and-delivery',
                              'ordinary-conversation-forwarding', 'installed-release-parity',
                              'authoritative-policy-and-classification', 'reversible-cutover'],
            'design': 'NATIVE_HOST_DESIGN.md'}
    if trust_boundary == 'daemon':
        report.update(trust_boundary='daemon', design='DAEMON_TRUST.md', required_work=[
            'native-startup-binding', 'identified-reader-assembly', 'assistant-transport',
            'installed-release-parity', 'authoritative-policy-and-classification',
            'reversible-cutover'])
    return report


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not (len(argv) == 1 or (len(argv) == 3 and argv[1] == '--trust-boundary'
                               and argv[2] in ('isolated', 'daemon'))):
        print('Usage: python3 native_host_review.py /offline/native/source '
              '[--trust-boundary isolated|daemon]', file=sys.stderr)
        return 2
    try:
        report = review(argv[0], argv[2] if len(argv) == 3 else 'isolated')
    except (OSError, ValueError, KeyError, TypeError):
        # Avoid echoing source paths, source content or exception text.
        print('Native source review failed; use an unchanged offline copy of the reviewed revision.',
              file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

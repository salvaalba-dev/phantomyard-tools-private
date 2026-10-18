"""Compare an offline binary with reviewed publisher metadata, without executing it.

This establishes byte parity with one published asset, not reproducible-build
attestation, current process identity, callback wiring or permission to deploy.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from native_host_review import SOURCE_REVISION

BASELINE = Path(__file__).with_name('native-release-review.json')
MAX_BINARY_BYTES = 256 * 1024 * 1024


def review(binary):
    """Inspect a quiescent regular file; never import or execute target code."""
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    if (baseline.get('schema_version') != 1
            or baseline.get('repository') != 'phantomyard/phantombot'
            or baseline.get('source_revision') != SOURCE_REVISION):
        raise ValueError('Release baseline does not match the reviewed source')
    size = baseline.get('asset_size')
    expected = baseline.get('asset_sha256')
    if (type(size) is not int or not 0 < size <= MAX_BINARY_BYTES
            or not isinstance(expected, str) or len(expected) != 64
            or any(char not in '0123456789abcdef' for char in expected)):
        raise ValueError('Invalid reviewed asset metadata')
    path = Path(os.path.abspath(binary))
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Binary review requires an unlinked path')
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != size:
        raise ValueError('Binary does not match the reviewed asset size')
    digest = hashlib.sha256()
    total = 0
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise ValueError('Binary changed during inspection')
        while chunk := stream.read(min(1024 * 1024, size - total + 1)):
            total += len(chunk)
            if total > size:
                raise ValueError('Binary exceeds the reviewed size')
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    current = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns')
    # Python exposes different ctime semantics through stat/fstat on Windows.
    if sys.platform != 'win32':
        fields += ('st_ctime_ns',)
    if (total != size or digest.hexdigest() != expected
            or any(getattr(before, field) != getattr(observed, field)
                   for observed in (after, current) for field in fields)):
        raise ValueError('Binary differs from the reviewed release')
    return {
        'schema_version': 1,
        'published_asset_matches': True,
        'source_revision': SOURCE_REVISION,
        'release_tag': baseline['tag'],
        'asset_sha256': expected,
        'asset_size': size,
        'activation_ready': False,
        'remaining_work': ['native-startup-binding', 'identified-reader-assembly',
                           'assistant-transport', 'reversible-cutover'],
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print('Usage: python3 native_release_review.py /offline/phantombot', file=sys.stderr)
        return 2
    try:
        result = review(argv[0])
    except (OSError, ValueError, KeyError, TypeError):
        print('Release review failed. Use a regular offline copy of the reviewed '
              'binary and inspect its release metadata before preparing a host.', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

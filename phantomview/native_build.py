"""Reviewed build inputs, provenance and read-only Linux artifact preflight."""
import argparse
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import zipfile
from importlib import metadata
from pathlib import Path

import native_host_entry as host
import relay_auth_patch

HERE = Path(__file__).resolve().parent
TEST_GROUPS = ('preparation', 'channels', 'persona')
SEMVER = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')
SHA = re.compile(r'[a-f0-9]{40}')


def write_private(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600) if os.name == 'posix' else None
        stream.write(raw)


def canonical_routes(raw, directory):
    if len(raw.encode('utf-8')) > 65536:
        raise ValueError('Build input exceeds its bound')
    document = json.loads(raw, object_pairs_hook=host._unique)
    normalized = {'schema_version': 1, 'routes': host.validate_routes(document)}
    canonical = json.dumps(normalized, sort_keys=True, separators=(',', ':')).encode()
    directory = Path(directory)
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    write_private(directory / 'routes.json', canonical)
    write_private(directory / 'routes.sha256', hashlib.sha256(canonical).hexdigest().encode())
    return normalized


def version_metadata(package, head, tag_head, tag, helper):
    if head != host.reviewed.SOURCE_REVISION or tag_head != head:
        raise ValueError('Reviewed release tag and native commit must agree')
    package_version = package.get('version')
    if (not isinstance(package_version, str) or not SEMVER.fullmatch(package_version)
            or not isinstance(tag, str) or not tag.startswith('v') or not SEMVER.fullmatch(tag[1:])
            or not isinstance(helper, str) or not SHA.fullmatch(helper)):
        raise ValueError('Explicit package, release and helper versions required')
    # Upstream package.json is a development version; release.yml numbers tags.
    return {'native_revision': head, 'package_version': package_version,
            'release_tag': tag, 'release_version': tag[1:], 'helper_revision': helper,
            'native_version': tag[1:] + '-phantomview.' + helper[:7]}


def source_metadata(source, tag, helper):
    source = Path(source)
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    tag_head = subprocess.check_output(
        ['git', '-C', str(source), 'rev-parse', 'refs/tags/phantomview-reviewed-native^{commit}'],
        text=True).strip()
    host.reviewed.review(source, trust_boundary='daemon')
    raw = (source / 'package.json').read_bytes()
    result = version_metadata(json.loads(raw), head, tag_head, tag, helper)
    result['package_sha256'] = hashlib.sha256(raw).hexdigest()
    return result


def stamp(source, document):
    source = Path(source)
    raw = (source / 'package.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != document['package_sha256']:
        raise ValueError('Reviewed package metadata changed before stamping')
    path = source / 'src/version.ts'
    text = path.read_text(encoding='utf-8')
    original = 'export const VERSION = "' + document['package_version'] + '-dev";'
    if text.count(original) != 1:
        raise ValueError('Reviewed native version placeholder changed')
    path.write_text(text.replace(original, 'export const VERSION = "' + document['native_version'] + '";'),
                    encoding='utf-8')


def embedded_version(source, document):
    text = (Path(source) / 'src/lib/vscodeExtensionAsset.generated.ts').read_text(encoding='utf-8')
    expected = 'VSCODE_EXTENSION_VERSION = "' + document['release_version'] + '"'
    if expected not in text:
        raise ValueError('Embedded editor version does not match the reviewed release')


def install_verifier(destination, site_directory):
    manifest = json.loads((HERE / 'build-sources/verifier-manifest.json').read_text())
    archive = HERE / 'build-sources' / manifest['archive']
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['archive_sha256']:
        raise ValueError('Archived verifier source digest mismatch')
    destination = Path(destination)
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) != len(manifest['files']) or {x.filename for x in entries} != set(manifest['files']):
            raise ValueError('Archived verifier member set mismatch')
        verified = {}
        for entry in entries:
            name = entry.filename
            if (name.startswith('/') or '..' in Path(name).parts or '\\' in name
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError('Unsafe archived verifier path')
            raw = bundle.read(entry)
            row = manifest['files'][name]
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if (len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']
                    or blob != row['git_blob']):
                raise ValueError('Archived verifier source differs from its reviewed Git blob')
            verified[name] = raw
    destination.mkdir(mode=0o700)
    for name, raw in verified.items():
        path = destination / name
        path.parent.mkdir(exist_ok=True, mode=0o700)
        write_private(path, raw)
    write_private(Path(site_directory) / 'phantomview-verifier.pth',
                  (str(destination.resolve()) + '\n').encode())
    return manifest['archive_sha256']


def required_glibc(text):
    versions = set(re.findall(r'\bGLIBC_([0-9]+(?:\.[0-9]+)+)\b', text))
    if not versions or 'GLIBC_PRIVATE' in text:
        raise ValueError('Explicit supported GLIBC symbol requirements required')
    return max(versions, key=lambda value: tuple(map(int, value.split('.'))))


def elf_metadata(binary):
    binary = Path(binary)
    with binary.open('rb') as stream:
        header = stream.read(20)
    if (header[:6] != b'\x7fELF\x02\x01' or len(header) != 20
            or int.from_bytes(header[18:20], 'little') != 62):
        raise ValueError('A Linux ELF64 x86-64 artifact is required')
    versions = subprocess.check_output(['readelf', '--version-info', '--wide', str(binary)], text=True)
    headers = subprocess.check_output(['readelf', '--program-headers', '--wide', str(binary)], text=True)
    interpreter = re.search(r'Requesting program interpreter: ([^\]\r\n]+)', headers)
    if not interpreter:
        raise ValueError('The reviewed build requires an explicit dynamic ELF interpreter')
    return {'minimum_glibc': required_glibc(versions), 'interpreter': interpreter[1]}


def check_glibc(required, actual):
    match = re.fullmatch(r'glibc ([0-9]+(?:\.[0-9]+)+)', actual)
    if not match or tuple(map(int, match[1].split('.'))) < tuple(map(int, required.split('.'))):
        raise ValueError('Host GLIBC is unsupported or older than the artifact requirement')
    return match[1]


def check_host(binary, expected):
    if not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise ValueError('An independently verified binary SHA-256 is required')
    with Path(binary).open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
            raise ValueError('Binary differs from the independently verified digest')
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('Select the reviewed Linux x86-64 host')
    abi = elf_metadata(binary)
    actual = check_glibc(abi['minimum_glibc'], os.confstr('CS_GNU_LIBC_VERSION') or '')
    if not Path(abi['interpreter']).is_file():
        raise ValueError('Required ELF interpreter is unavailable on this host')
    return abi | {'host_glibc': actual, 'binary_sha256': expected, 'status': 'host-compatible'}


def test_results(environment):
    results = {name: environment.get('TEST_' + name.upper()) for name in TEST_GROUPS}
    if any(value != 'success' for value in results.values()):
        raise ValueError('Every required test group must report success')
    return results



def verify_binary_version(result, expected):
    # Citty uses consola.log: CI emits '[log] VERSION', terminals may emit VERSION.
    # Dependency diagnostics on stderr are bounded independently.
    if result.stdout.strip() not in {expected, '[log] ' + expected} or len(result.stdout) > 1024 or len(result.stderr) > 4096:
        raise ValueError('Compiled native version does not match its provenance: '
                         + repr(result.stdout[:1024]))
    return True


def receipt(binary, source, root, environment):
    results = test_results(environment)
    dependency_patch = relay_auth_patch.verify_manifest(
        environment.get('PHANTOMVIEW_NATIVE_SOURCE', 'native-source'),
        json.loads((root / 'relay-auth-patch.json').read_text(encoding='utf-8')))
    image = {key: environment.get(key, '') for key in ('ImageOS', 'ImageVersion')}
    if not all(image.values()) or platform.python_version() != environment['BUILD_PYTHON_VERSION']:
        raise ValueError('Exact Python and hosted runner image provenance are required')
    bun = subprocess.check_output(['bun', '--version'], text=True).strip()
    if bun != environment['BUILD_BUN_VERSION']:
        raise ValueError('Bun version differs from the configured compiler')
    version = subprocess.run([str(Path(binary).resolve()), '--version'], check=True,
                             capture_output=True, text=True, timeout=10)
    verify_binary_version(version, source['native_version'])
    routes = (root / 'routes.json').read_bytes()
    digest = hashlib.sha256(routes).hexdigest()
    if digest != (root / 'routes.sha256').read_text():
        raise ValueError('Canonical routes changed after validation')
    manifest = json.loads((HERE / 'build-sources/verifier-manifest.json').read_text())
    with Path(binary).open('rb') as stream:
        binary_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return source | {
        'schema_version': 2, 'bun_version': bun, 'python_version': platform.python_version(),
        'python_packages': {name: metadata.version(name) for name in ('PyYAML', 'coincurve')},
        'runner_image': image, 'kernel': platform.release(), 'build_host_glibc': platform.libc_ver(),
        'target': 'bun-linux-x64-baseline', 'elf': elf_metadata(binary),
        'verifier_revision': manifest['revision'], 'verifier_archive_sha256': manifest['archive_sha256'],
        'python_lock_sha256': hashlib.sha256((HERE / 'native-build-requirements.lock').read_bytes()).hexdigest(),
        'routes_sha256': digest, 'binary_sha256': binary_sha, 'binary_bytes': Path(binary).stat().st_size,
        'workflow_run_id': environment['GITHUB_RUN_ID'],
        'workflow_run_attempt': environment['GITHUB_RUN_ATTEMPT'],
        'compiled_version_verified': verify_binary_version(version, source['native_version']),
        'version_diagnostics_sha256': hashlib.sha256(version.stderr.encode()).hexdigest(),
        'embedded_extension_version': source['release_version'],
        'dependency_patches': {'nostr-tools-auth': dependency_patch},
        'test_results': results, 'tests_passed': all(value == 'success' for value in results.values()),
        'installed': False, 'activation_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['routes', 'source', 'stamp', 'embedded', 'verifier', 'receipt', 'check-host'])
    parser.add_argument('--source', default='native-source')
    parser.add_argument('--root', default='operator-build')
    parser.add_argument('--site-directory')
    parser.add_argument('--binary')
    parser.add_argument('--expected-sha256')
    args = parser.parse_args()
    if args.operation == 'check-host' and (not args.binary or not args.expected_sha256):
        parser.error('check-host requires --binary and --expected-sha256')
    root = Path(args.root)
    if args.operation == 'routes':
        canonical_routes(os.environ.pop('NATIVE_HOST_JSON'), root)
    elif args.operation == 'source':
        document = source_metadata(args.source, os.environ['NATIVE_RELEASE_TAG'], os.environ['GITHUB_SHA'])
        write_private(root / 'source.json', (json.dumps(document, indent=2) + '\n').encode())
    elif args.operation in {'stamp', 'embedded'}:
        document = json.loads((root / 'source.json').read_text())
        (stamp if args.operation == 'stamp' else embedded_version)(args.source, document)
    elif args.operation == 'verifier':
        install_verifier(root / 'verifier', args.site_directory)
    elif args.operation == 'check-host':
        print(json.dumps(check_host(args.binary, args.expected_sha256), sort_keys=True))
    else:
        document = json.loads((root / 'source.json').read_text())
        output = root / 'artifact'
        result = receipt(output / 'phantombot', document, root, os.environ)
        write_private(output / 'build-receipt.json', (json.dumps(result, indent=2) + '\n').encode())
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

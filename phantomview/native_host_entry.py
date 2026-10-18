"""Prepare fixed CLI startup routes in an offline, reviewed native source copy."""
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import urlsplit

import authenticated_command_patch as command
import native_host_review as reviewed

ROUTES = 'src/channels/core/phantomViewHostRoutes.ts'
ENTRY = 'src/cli/run.ts'
ANCHOR = '    const code = await runRun({ ifNotRunning: Boolean(args["if-not-running"]) });'
REPLACEMENT = '''    const code = await runRun({ ifNotRunning: Boolean(args["if-not-running"]),
      authenticatedCommands: phantomViewStartupCommands(phantomViewHostRoutes) });'''
FIELDS = {'persona', 'channel', 'scopeId', 'origin', 'issuerUid', 'readerUid',
          'python', 'clientScript', 'socketPath'}
NOTE = '''

## Fixed private PhantomView host routes

This offline variant registers reviewed compile-time routes only in the existing
`run` command. The original CLI entry, credential bootstrap, embedded harness,
process lock and other subcommands remain in place. Routes contain deployment
coordinates, never keys, human identities or ACL grants. No runtime JSON, module
discovery, extra channel consumer or resident service is added. The existing
daemon account, including its tools, is trusted; the reader account is separate.
PhantomOrg remains authoritative for requesting humans and information access.

The build is tied to this reviewed source and fixed deployment routes. A stock
native update does not preserve the optional hook. Do not claim automatic upgrade
compatibility: review/rebuild this variant before an update or keep it inactive.
Preparing or compiling it does not install a reader or activate an assistant.
'''


def validate_routes(document):
    """Validate non-secret build input; it never becomes a runtime config loader."""
    if (type(document) is not dict or set(document) != {'schema_version', 'routes'}
            or type(document['schema_version']) is not int or document['schema_version'] != 1
            or type(document['routes']) is not list or not 1 <= len(document['routes']) <= 64):
        raise ValueError('A versioned, nonempty fixed route list is required')
    result, seen, issuers = [], set(), set()
    for route in document['routes']:
        if type(route) is not dict or set(route) != FIELDS:
            raise ValueError('Only fixed native deployment fields are supported')
        if (type(route['persona']) is not str
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', route['persona'])
                or route['channel'] not in ('telegram', 'phantomchat')
                or type(route['scopeId']) is not str
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', route['scopeId'])):
            raise ValueError('An explicit native persona, channel and scope are required')
        if any(type(route[key]) is not int or not 0 < route[key] < 2**32 - 1
               for key in ('issuerUid', 'readerUid')) or route['issuerUid'] == route['readerUid']:
            raise ValueError('Distinct nonroot daemon and reader accounts are required')
        origin = route['origin']
        if type(origin) is not str or not origin.isascii() or any(ord(c) <= 32 for c in origin):
            raise ValueError('A canonical HTTPS origin is required')
        parsed = urlsplit(origin)
        host = parsed.hostname or ''
        try:
            canonical_host = ipaddress.ip_address(host).compressed
            if ':' in canonical_host:
                canonical_host = '[' + canonical_host + ']'
        except ValueError:
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', host):
                raise ValueError('A canonical HTTPS host is required') from None
            canonical_host = host
        port = parsed.port
        if port is not None and (not 0 < port < 65536 or port == 443):
            raise ValueError('A canonical HTTPS port is required')
        expected = 'https://' + canonical_host + (f':{port}' if port is not None else '')
        if origin != expected:
            raise ValueError('An origin cannot contain credentials, paths, queries or fragments')
        for key in ('python', 'clientScript', 'socketPath'):
            path = route[key]
            if (type(path) is not str or not path.isascii() or not path.startswith('/')
                    or path.startswith('//') or PurePosixPath(path).as_posix() != path
                    or '..' in PurePosixPath(path).parts or path == '/'
                    or any(ord(c) <= 32 or ord(c) == 127 for c in path) or '\\' in path):
                raise ValueError('Fixed normalized Linux paths are required')
        key = route['channel'], route['persona']
        if key in seen:
            raise ValueError('Duplicate native listener routes are unsupported')
        seen.add(key)
        issuers.add(route['issuerUid'])
        result.append(dict(route))
    if len(issuers) != 1:
        raise ValueError('One native daemon account is required per host build')
    return result


def prepare(root, document):
    routes = validate_routes(document)
    root = Path(root).absolute()
    reviewed.review(root, 'daemon')
    target = root / ROUTES
    if target.exists() or target.is_symlink():
        raise ValueError('An existing host route artifact must not be overwritten')
    # Check the additional CLI anchor before the generic preparation writes files.
    original = (root / ENTRY).read_text(encoding='utf-8')
    command.provenance.replace_exact(original, ANCHOR, REPLACEMENT)
    source = '/** Fixed non-secret routes generated during offline host preparation. */\n'
    source += 'export const phantomViewHostRoutes = Object.freeze([\n'
    source += ',\n'.join('  Object.freeze(' + json.dumps(route, sort_keys=True) + ' as const)'
                         for route in routes)
    source += '\n]);\n'
    command.patch(root)
    entry = command.provenance.replace_exact((root / ENTRY).read_text(encoding='utf-8'),
                                             ANCHOR, REPLACEMENT)
    entry = ('import { phantomViewStartupCommands } from "../channels/core/phantomViewStartup.ts";\n'
             'import { phantomViewHostRoutes } from "../channels/core/phantomViewHostRoutes.ts";\n' + entry)
    target.write_text(source, encoding='utf-8', newline='\n')
    (root / ENTRY).write_text(entry, encoding='utf-8', newline='\n')
    for name in ('README.md', 'AGENTS.md'):
        path = root / name
        path.write_text(path.read_text(encoding='utf-8') + NOTE, encoding='utf-8', newline='\n')
    return {'source_revision': reviewed.SOURCE_REVISION, 'route_count': len(routes),
            'trust_boundary': 'daemon', 'activation_ready': False}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate build-input keys are unsupported')
        result[key] = value
    return result


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print('Usage: python3 native_host_entry.py /disposable/native/source /reviewed/routes.json',
              file=sys.stderr)
        return 2
    try:
        with Path(argv[1]).open('rb') as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError('Build input exceeds its bound')
        document = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique)
        report = prepare(argv[0], document)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print('Host preparation refused; use the reviewed offline source and fixed deployment routes.',
              file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Offline pairing of protected reader and native build descriptors; start nothing."""
import argparse
import json
from pathlib import Path
import sys

import native_host_entry as native
from organization_authority import _parse, _read
import reader_launch as reader


def compare(launch, hosts):
    """Check exact endpoint coverage without inferring identity, scope or ACL grants."""
    launch = reader.validate(launch)
    if type(hosts) is not list or not 1 <= len(hosts) <= 16:
        raise ValueError('Select one to sixteen native host build documents')
    expected = {route['actor']: route for route in reader.issuer_routes(launch)}
    covered, listeners, account_hosts = set(), set(), set()
    route_count = 0
    for document in hosts:
        routes = native.validate_routes(document)
        uid = routes[0]['issuerUid']
        if uid in account_hosts:
            raise ValueError('Combine routes sharing one daemon account in one host build')
        account_hosts.add(uid)
        for route in routes:
            actor = route['persona']
            if actor not in expected:
                raise ValueError('Native persona has no reader issuer route')
            target = expected[actor]
            for left, right in (('issuerUid', 'issuer_uid'), ('socketPath', 'socket_path'),
                                ('conversationSocketPath', 'conversation_socket')):
                if route.get(left) != target[right]:
                    raise ValueError('Native and reader issuer endpoints must agree')
            if route['readerUid'] != launch['reader_uid'] or route['origin'] != launch['origin']:
                raise ValueError('Native and reader account and HTTPS origin must agree')
            listener = actor, route['channel']
            if listener in listeners:
                raise ValueError('Native listener is configured more than once')
            listeners.add(listener)
            covered.add(actor)
            route_count += 1
    if covered != set(expected):
        raise ValueError('Every reader issuer requires an explicit native listener route')
    return {'status': 'route-descriptors-matched', 'issuer_count': len(covered),
            'native_host_count': len(hosts), 'native_listener_count': route_count,
            'source_revision': native.reviewed.SOURCE_REVISION, 'activation_ready': False,
            'pending': ['current-authority-and-approved-projection',
                        'loaded-public-signing-identities', 'native-source-and-build-review',
                        'host-permissions-and-reader-preflight',
                        'reviewed-cutover-and-verified-channel-tests']}


def load_host(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or path.suffix != '.json':
        raise ValueError('Select an absolute protected native host JSON file')
    raw = _read(path)
    if len(raw) > 65536:
        raise ValueError('Native build input exceeds its existing bound')
    return _parse(raw, '.json')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', required=True)
    parser.add_argument('--native-host', action='append', required=True)
    args = parser.parse_args(argv)
    try:
        report = compare(reader.load(args.reader), [load_host(path) for path in args.native_host])
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        # Deployment coordinates and raw exceptions never belong in shared logs.
        print('Route pairing refused. Check protected descriptor coverage, accounts, '
              'origin and sockets; see DEPLOYMENT_ROUTES.md.', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

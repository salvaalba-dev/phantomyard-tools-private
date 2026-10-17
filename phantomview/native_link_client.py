"""Private one-shot native IPC client, never a model tool or human identity API."""
import argparse
import json
import os
from pathlib import Path
import sys

# Isolated Python mode deliberately excludes CWD and PYTHONPATH. The operator
# protects this fixed module directory; never obtain it from input or environment.
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from handoff_client import ReaderPolicy, request_access
from trusted_handoff import MAX_FRAME, _unique, validate_request


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('Invalid fixed native client configuration')


def run(arguments, incoming, outgoing):
    """Read one bounded frame from native stdin, not sender fields from argv.

    The configured non-model issuer UID is still the authority. JSON flags do
    not authenticate anyone; request_access retains kernel reader verification.
    """
    try:
        parser = Parser(add_help=False)
        parser.add_argument('--socket', required=True)
        parser.add_argument('--issuer-uid', required=True, type=int)
        parser.add_argument('--reader-uid', required=True, type=int)
        parser.add_argument('--model-uid', required=True, type=int, action='append')
        parser.add_argument('--origin', required=True)
        parser.add_argument('--channel', required=True, choices=('telegram', 'phantomchat'))
        parser.add_argument('--scope-id', required=True)
        args = parser.parse_args(arguments)
        if not hasattr(os, 'getuid') or args.issuer_uid <= 0 or os.getuid() != args.issuer_uid:
            raise ValueError('Unexpected native process account')
        policy = ReaderPolicy(args.reader_uid, frozenset(args.model_uid))
        raw = incoming.read(MAX_FRAME + 1)
        if not raw or len(raw) > MAX_FRAME:
            raise ValueError('Invalid native frame size')
        document = validate_request(json.loads(raw, object_pairs_hook=_unique))
        if document['channel'] != args.channel or document['scope_id'] != args.scope_id:
            raise ValueError('Native route mismatch')
        context = {key: document[key] for key in
                   ('channel', 'sender', 'direct', 'principal_authenticated', 'scope_id')}
        link = request_access(args.socket, policy, args.origin, document['authorization'], context)
        result, status = {'schema_version': 1, 'link': link}, 0
    except (ValueError, TypeError, OSError, KeyError, RecursionError, argparse.ArgumentError):
        result, status = {'schema_version': 1, 'error': 'Verified access handoff denied'}, 1
    outgoing.write(json.dumps(result, separators=(',', ':')) + '\n')
    outgoing.flush()
    return status


if __name__ == '__main__':
    raise SystemExit(run(sys.argv[1:], sys.stdin.buffer, sys.stdout))

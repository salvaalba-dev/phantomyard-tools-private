"""Synthetic cross-runtime acceptance probe; never loads production identities."""
import base64
import json
from pathlib import Path
import sys

# The fixture is invoked with isolated Python imports on a disposable CI runner.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phantomblog import access
from channel_identity import HumanDirectory
from identified_access import IdentifiedGate
from test_channel_identity import context, organization


def run():
    raw = sys.stdin.buffer.read(16385)
    if len(raw) > 16384:
        raise ValueError('Oversized synthetic fixture')
    fixture = json.loads(raw)
    gate = IdentifiedGate(access, {'actor': 'coordinator', 'identities': [fixture['publicKey']]},
        fixture['origin'], 8790, directory_loader=lambda: HumanDirectory(organization()))
    link = gate.issue_identified(fixture['authorization'], gate.origin, **context())
    try:
        gate.issue_identified(fixture['authorization'], gate.origin, **context())
    except access.core.Invalid:
        pass
    else:
        raise AssertionError('Signed authorization replay accepted')
    code = link.split('#c=')[1]
    cookie = gate.redeem(code)
    recipient, _ = gate.identified_scope({'Cookie': 'phantomview=' + cookie})
    assert recipient.persona == 'coordinator'
    try:
        gate.redeem(code)
    except access.core.Invalid:
        pass
    else:
        raise AssertionError('Link redeemed twice')
    event = json.loads(base64.b64decode(fixture['authorization'][6:], validate=True))
    event['sig'] = ('1' if event['sig'][0] != '1' else '2') + event['sig'][1:]
    forged = 'Nostr ' + base64.b64encode(json.dumps(event).encode()).decode()
    try:
        gate.issue_identified(forged, gate.origin, **context())
    except access.core.Invalid:
        pass
    else:
        raise AssertionError('Forged signature accepted')
    # Do not print ephemeral grants, cookies, signatures or channel identities.
    print(json.dumps({'verified': True, 'replay_denied': True, 'single_use': True,
                      'forged_signature_denied': True, 'recipient_bound': True}))


if __name__ == '__main__':
    run()

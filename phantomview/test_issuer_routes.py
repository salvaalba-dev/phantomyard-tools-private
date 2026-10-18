"""Issuer accounts, signatures and human scopes cannot be interchanged."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid

from channel_identity import HumanDirectory
from identified_reader import MultiIssuerGate
from issuer_routes import validate_routes
from persona_conversation import PersonaAssistant
import reader_launch
from scoped_backend import ScopedBackend
from session_audit import Ledger
from test_channel_identity import context
from test_persona_conversation import NativeExecutor
from test_reader_launch import example
from test_view_permissions import project_resource, scoped_organization

try:
    from coincurve import PrivateKey
    from phantomblog import access
except ImportError:
    PrivateKey = None


def route(actor='administrator', key='a' * 64, uid=200):
    return {'actor': actor, 'identities': [key], 'issuer_uid': uid, 'socket_group': 400,
            'socket_path': '/run/example/' + actor + '.sock', 'conversation_socket': None}


class RouteContractTests(unittest.TestCase):
    def test_ambiguous_or_untrusted_routes_fail_closed(self):
        primary = route()
        secondary = route('treasurer', 'b' * 64, 201)
        for changes in ({'actor': 'administrator'}, {'identities': ['a' * 64]},
                        {'identities': []}, {'issuer_uid': True}, {'socket_group': 0},
                        {'socket_path': primary['socket_path']}, {'socket_path': '/run/../link.sock'},
                        {'socket_path': '/run//link.sock'}, {'socket_path': '/private/source.json'},
                        {'conversation_socket': primary['socket_path']}, {'endpoint': 'https://remote.example'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_routes(primary, [secondary | changes], occupied=['/private/source.json'])
        with self.assertRaises(ValueError):
            validate_routes(primary, [secondary], reader_uid=201)
        with self.assertRaises(ValueError):
            validate_routes(primary, [secondary] * 16)

    def test_launch_routes_are_detached_and_old_configuration_is_unchanged(self):
        config = example()
        self.assertEqual(reader_launch.validate(config), config)
        config['additional_issuers'] = [route('treasurer', 'b' * 64, 12004)]
        validated = reader_launch.validate(config)
        validated['additional_issuers'][0]['identities'].clear()
        self.assertEqual(len(config['additional_issuers'][0]['identities']), 1)
        for value in (None, {}, 'treasurer'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reader_launch.validate(example() | {'additional_issuers': value})


@unittest.skipIf(PrivateKey is None, 'Install the reviewed PhantomBlog access extra')
class MultiIssuerSignatureTests(unittest.TestCase):
    def setUp(self):
        self.keys = {actor: PrivateKey() for actor in ('administrator', 'treasurer')}
        self.routes = [route(actor, key.public_key_xonly.format().hex(), 200 + index)
                       for index, (actor, key) in enumerate(self.keys.items())]
        self.org = scoped_organization()
        self.org['policies']['security_categories']['category-4-river'] = {}
        self.org['actors'][2]['actor_exceptions'] = ['category-4-river']
        self.org['policies']['phantomview']['human_category_limits'] = {'accountant': ['category-4-river']}
        self.ticks = [0]
        self.gate = MultiIssuerGate(access, {key: self.routes[0][key] for key in ('actor', 'identities')},
            'https://view.example', 8790, routes=self.routes,
            directory_loader=lambda: HumanDirectory(self.org), clock=lambda: self.ticks[0])
        for verifier in self.gate.verifiers.values():
            verifier.clock = lambda: self.ticks[0]

    def authorization(self, actor, **changes):
        key = self.keys[actor]
        event = {'pubkey': key.public_key_xonly.format().hex(), 'created_at': int(time.time()),
                 'kind': 27235, 'tags': [['u', self.gate.origin + '/api/access-link'], ['method', 'POST'],
                 ['payload', hashlib.sha256(b'{}').hexdigest()], ['nonce', uuid.uuid4().hex]], 'content': ''} | changes
        event['id'] = access.event_digest(event)
        event['sig'] = key.sign_schnorr(bytes.fromhex(event['id'])).hex()
        return 'Nostr ' + base64.b64encode(json.dumps(event).encode()).decode()

    def issue(self, actor, authorization=None, **changes):
        sender, scope = ('102', 'example') if actor == 'administrator' else ('103', 'river-project')
        return self.gate.issue_identified(authorization or self.authorization(actor), self.gate.origin,
            **(context(sender, actor, scope_id=scope) | changes)).split('#c=')[1]

    def recipient(self, code):
        cookie = self.gate.redeem(code)
        return self.gate.identified_scope({'Cookie': 'phantomview=' + cookie})

    def test_signer_is_bound_to_route_and_recipient_scope_is_derived(self):
        with self.assertRaises(access.core.Invalid):
            self.issue('treasurer', self.authorization('administrator'))
        with self.assertRaises(ValueError):
            self.issue('treasurer', sender='102')
        self.assertEqual(self.gate.recipient_links, {})
        primary, _ = self.recipient(self.issue('administrator'))
        project, directory = self.recipient(self.issue('treasurer'))
        self.assertEqual((primary.human, primary.persona), ('secretary', 'administrator'))
        self.assertEqual((project.human, project.persona, project.scope_id), ('accountant', 'treasurer', 'river-project'))
        self.assertTrue(directory.permits(project, project_resource(category='category-4-river')))
        self.assertFalse(directory.permits(project, project_resource()))
        self.assertFalse(directory.permits(project, project_resource('other-project', category='category-4-river')))

    def test_real_protocol_replay_freshness_and_payload_checks_remain_enabled(self):
        authorization = self.authorization('treasurer')
        self.issue('treasurer', authorization)
        with self.assertRaises(access.core.Invalid):
            self.issue('treasurer', authorization)
        for changes in ({'created_at': int(time.time()) - 120}, {'content': 'forged human'},
                        {'tags': [['u', 'https://other.example/api/access-link'], ['method', 'POST'],
                                  ['payload', hashlib.sha256(b'{}').hexdigest()]]}):
            with self.subTest(changes=changes), self.assertRaises(access.core.Invalid):
                self.issue('treasurer', self.authorization('treasurer', **changes))

    def test_each_link_has_one_redeemer_across_shared_sessions(self):
        codes = [self.issue(actor) for actor in self.keys]
        def redeem(code):
            try:
                return self.gate.redeem(code)
            except (ValueError, access.core.Invalid):
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            values = [value for value in pool.map(redeem, codes * 8) if value]
        self.assertEqual(len(values), 2)
        self.assertEqual(len(self.gate.sessions), 2)

    def test_expiry_and_current_authority_apply_to_every_issuer(self):
        codes = [self.issue(actor) for actor in self.keys]
        self.ticks[0] = 300
        for code in codes:
            with self.assertRaises((ValueError, access.core.Invalid)):
                self.gate.redeem(code)
        cookie = self.gate.redeem(self.issue('treasurer'))
        self.org['policies']['phantomview']['human_category_limits']['accountant'] = ['category-1']
        with self.assertRaises(ValueError):
            self.gate.identified_scope({'Cookie': 'phantomview=' + cookie})

    def test_route_configuration_mutation_cannot_change_verifier_allowlists(self):
        before = copy.deepcopy(self.routes)
        self.routes[1]['identities'][:] = self.routes[0]['identities']
        self.assertEqual(self.gate.verifiers['treasurer'].identities, frozenset(before[1]['identities']))

    def test_restricted_secondary_session_never_falls_back_to_primary_native_assistant(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root).chmod(0o700)
            self.gate.audit = Ledger(Path(root) / 'audit.sqlite')
            directory = HumanDirectory(self.org)
            catalog = {'schema_version': 1, 'organization': 'example', 'status': 'approved',
                       'authority_revision': directory.authority_revision, 'resources': []}
            backend = ScopedBackend(self.gate, lambda: catalog, lambda _: None)
            executors = {actor: NativeExecutor(actor) for actor in self.keys}
            assistant = PersonaAssistant(backend, executors)
            headers = {}
            for actor in self.keys:
                cookie = self.gate.redeem(self.issue(actor))
                headers[actor] = {'Cookie': 'phantomview=' + cookie}
            assistant.consult(headers['administrator'], 'Explain the institution',
                              request_id=str(uuid.uuid4()), cancelled=threading.Event())
            self.assertFalse(assistant.available(headers['treasurer']))
            with self.assertRaises(PermissionError):
                assistant.consult(headers['treasurer'], 'Explain the project',
                                  request_id=str(uuid.uuid4()), cancelled=threading.Event())
            self.assertEqual(len(executors['administrator'].calls), 1)
            self.assertEqual(executors['treasurer'].calls, [])


if __name__ == '__main__':
    unittest.main()

"""Real signed component flow; native channel authentication is not simulated as proven.

The trusted contexts below are synthetic test inputs to the in-process adapter.
No installed channel hook, model invocation or live multi-issuer server is tested.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time
import unittest
import uuid

from channel_identity import HumanDirectory
from identified_access import IdentifiedGate
from scoped_backend import ScopedBackend
from test_channel_identity import context
from test_scoped_backend import ProjectionFixture

try:
    from coincurve import PrivateKey
    from phantomblog import access
except ImportError:
    PrivateKey = None


@unittest.skipIf(PrivateKey is None, "Install PhantomBlog with its access extra for real signatures")
class IdentifiedViewerFlowTests(ProjectionFixture):
    def setUp(self):
        super().setUp()
        self.keys = {persona: PrivateKey() for persona in
                     ('coordinator', 'administrator', 'treasurer')}
        self.ticks = [0]
        # An email-only member remains in PhantomOrg without becoming a
        # verified Telegram or PhantomChat principal.
        self.org['humans'][3].pop('telegram_user_id')
        self.org['humans'][3]['email'] = 'member@example.test'
        self.catalog['authority_revision'] = HumanDirectory(self.org).authority_revision

    def make_gate(self, persona='administrator'):
        identity = self.keys[persona].public_key_xonly.format().hex()
        gate = IdentifiedGate(access, {'actor': persona, 'identities': [identity]},
            'https://view.example:8790', 8790, clock=lambda: self.ticks[0],
            directory_loader=lambda: HumanDirectory(self.org))
        gate.links.clock = lambda: self.ticks[0]
        return gate

    def signed(self, gate, signer=None):
        key = self.keys[signer or gate.policy['actor']]
        event = {'pubkey': key.public_key_xonly.format().hex(), 'created_at': int(time.time()),
            'kind': 27235, 'tags': [['u', gate.origin + '/api/access-link'], ['method', 'POST'],
            ['payload', hashlib.sha256(b'{}').hexdigest()], ['nonce', uuid.uuid4().hex]], 'content': ''}
        event['id'] = access.event_digest(event)
        event['sig'] = key.sign_schnorr(bytes.fromhex(event['id'])).hex()
        return 'Nostr ' + base64.b64encode(json.dumps(event).encode()).decode()

    def link(self, gate, sender='102', persona='administrator', scope='example', **changes):
        return gate.issue_identified(self.signed(gate), gate.origin,
            **context(sender, persona, scope_id=scope, **changes))

    def redeem_headers(self, gate, link):
        return {'Cookie': 'phantomview=' + gate.redeem(link.split('#c=')[1])}

    def test_each_counterpart_reaches_its_own_assistant_and_authorized_projection(self):
        # Separate fixed-issuer gates exercise the existing supported contract.
        # This does not pretend one deployed gate already routes all issuers.
        for sender, persona, human, scope in (
                ('101', 'coordinator', 'owner', 'example'),
                ('102', 'administrator', 'secretary', 'example'),
                ('103', 'treasurer', 'accountant', 'river-project')):
            with self.subTest(persona=persona):
                gate = self.make_gate(persona)
                link = self.link(gate, sender, persona, scope)
                self.assertRegex(link, r'^https://view\.example:8790/#c=[A-Za-z0-9_-]{43}$')
                headers = self.redeem_headers(gate, link)
                recipient, _ = gate.identified_scope(headers)
                self.assertEqual((recipient.human, recipient.persona), (human, persona))
                backend = ScopedBackend(gate, lambda: self.catalog, self.load,
                    default_report_loader=lambda: {'default_persona': {
                        'resolved': 'coordinator', 'exists': True, 'served': True, 'provenance': 'config'}})
                view = backend.workspace(headers)
                self.assertEqual(view['navigation']['assistant'],
                    {'persona': persona, 'eligible': True, 'source': 'session-issuer'})
                self.assertIn(self.project, {row['id'] for row in view['resources']})
                if human != 'owner':
                    self.assertNotIn(self.hidden, json.dumps(view))
                    self.assertEqual(backend.search(headers, 'Private board')['results'], [])
                gate.logout(headers)
                with self.assertRaises(ValueError):
                    backend.workspace(headers)

    def test_identity_and_counterpart_checks_precede_grant_creation(self):
        gate = self.make_gate()
        authorization = self.signed(gate)
        for sender, changes in (('104', {}), ('unknown', {}), ('103', {}),
                                ('102', {'direct': False}),
                                ('102', {'principal_authenticated': False}),
                                ('member@example.test', {'channel': 'email'})):
            with self.subTest(sender=sender, changes=changes), self.assertRaises(ValueError):
                gate.issue_identified(authorization, gate.origin,
                    **context(sender, 'administrator', scope_id='example', **changes))
        self.assertEqual(gate.recipient_links, {})
        self.assertEqual(gate.sessions, {})
        # Failed recipient checks did not consume the valid signed authorization.
        link = gate.issue_identified(authorization, gate.origin,
            **context('102', 'administrator', scope_id='example'))
        self.assertEqual(gate.identified_scope(self.redeem_headers(gate, link))[0].human, 'secretary')

    def test_another_issuer_signature_or_claim_cannot_replace_the_fixed_issuer(self):
        gate = self.make_gate()
        with self.assertRaises(access.core.Invalid):
            gate.issue_identified(self.signed(gate, 'coordinator'), gate.origin,
                **context('102', 'administrator', scope_id='example'))
        with self.assertRaises(ValueError):
            self.link(gate, '101', 'coordinator')
        self.assertEqual(gate.recipient_links, {})
        self.assertEqual(gate.sessions, {})

    def test_signed_authorization_replay_cannot_rebind_a_link(self):
        gate = self.make_gate()
        authorization = self.signed(gate)
        link = gate.issue_identified(authorization, gate.origin,
            **context('102', 'administrator', scope_id='example'))
        with self.assertRaises(access.core.Invalid):
            gate.issue_identified(authorization, gate.origin,
                **context('101', 'administrator', scope_id='example'))
        headers = self.redeem_headers(gate, link)
        self.assertEqual(gate.identified_scope(headers)[0].human, 'secretary')
        self.assertEqual(len(gate.sessions), 1)

    def test_concurrent_redemption_binds_exactly_one_session_to_the_original_human(self):
        gate = self.make_gate()
        link = self.link(gate)

        def redeem(_):
            try:
                return self.redeem_headers(gate, link)
            except access.core.Invalid:
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = [row for row in pool.map(redeem, range(16)) if row is not None]
        self.assertEqual(len(results), 1)
        self.assertEqual(gate.identified_scope(results[0])[0].human, 'secretary')
        self.assertEqual(len(gate.sessions), 1)

    def test_channel_rebinding_before_redemption_denies_session_creation(self):
        gate = self.make_gate()
        link = self.link(gate)
        self.org['humans'][1]['telegram_user_id'] = 1002
        with self.assertRaises(ValueError):
            self.redeem_headers(gate, link)
        self.assertEqual(gate.sessions, {})

    def test_counterpart_removal_before_redemption_denies_session_creation(self):
        gate = self.make_gate()
        link = self.link(gate)
        self.org['humans'][1].pop('counterpart_persona')
        with self.assertRaises(ValueError):
            self.redeem_headers(gate, link)
        self.assertEqual(gate.sessions, {})

    def test_policy_change_after_login_blocks_workspace_and_search_before_record_reads(self):
        gate = self.make_gate()
        headers = self.redeem_headers(gate, self.link(gate))
        backend = ScopedBackend(gate, lambda: self.catalog, self.load)
        backend.workspace(headers)
        self.loaded.clear()
        self.org['roles'][0]['security_exceptions'] = ['category-3']
        for operation in (lambda: backend.workspace(headers), lambda: backend.search(headers, 'River')):
            with self.assertRaises(ValueError):
                operation()
        self.assertEqual(self.loaded, [])

    def test_legacy_link_cannot_be_promoted_to_identified_navigation(self):
        gate = self.make_gate()
        link = gate.issue(self.signed(gate), gate.origin)
        headers = self.redeem_headers(gate, link)
        self.assertTrue(gate.session(headers))
        backend = ScopedBackend(gate, lambda: self.catalog, self.load)
        with self.assertRaises(ValueError):
            backend.workspace(headers)
        self.assertEqual(self.loaded, [])

    def test_phantomchat_uses_the_registered_canonical_sender_without_a_second_login(self):
        # Public test identity from PhantomOrg's synthetic PhantomChat fixtures.
        # The native transport, not this component test, must prove ownership.
        npub = 'npub1nn8csdm4tpjvveutqjavgxqdsndqw6w0ua2u0rd4050lyzzstq7s5usgk5'
        self.org['humans'][1]['npub'] = npub
        self.catalog['authority_revision'] = HumanDirectory(self.org).authority_revision
        gate = self.make_gate()
        for changes in ({'principal_authenticated': False}, {'direct': False}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.link(gate, npub, channel='phantomchat', **changes)
        link = self.link(gate, npub, channel='phantomchat')
        self.assertNotIn(npub, link)
        headers = self.redeem_headers(gate, link)
        recipient, _ = gate.identified_scope(headers)
        self.assertEqual((recipient.human, recipient.persona), ('secretary', 'administrator'))
        view = ScopedBackend(gate, lambda: self.catalog, self.load).workspace(headers)
        self.assertEqual(view['navigation']['assistant']['persona'], 'administrator')
        self.assertNotIn(self.hidden, json.dumps(view))

    def test_independent_category_zero_owner_keeps_the_actual_issuing_persona(self):
        self.org['policies']['security_categories']['category-0']['owner'] = 'accountant'
        self.org['humans'][2].pop('counterpart_persona')
        self.catalog['authority_revision'] = HumanDirectory(self.org).authority_revision
        gate = self.make_gate()
        headers = self.redeem_headers(gate, self.link(gate, '103'))
        recipient, directory = gate.identified_scope(headers)
        self.assertEqual(recipient.human, 'accountant')
        self.assertTrue(directory.scope.is_absolute(recipient.human))
        view = ScopedBackend(gate, lambda: self.catalog, self.load).workspace(headers)
        self.assertIn(self.hidden, {row['id'] for row in view['resources']})
        self.assertEqual(view['navigation']['assistant']['persona'], 'administrator')
        self.assertFalse(directory.allows_action(recipient, 'resource.edit', 'example'))

    def test_operator_revocation_blocks_all_identified_reads(self):
        gate = self.make_gate()
        headers = self.redeem_headers(gate, self.link(gate))
        owner, _ = gate.session_scope(headers)
        self.assertTrue(gate.revoke(gate.session_ids[owner]))
        backend = ScopedBackend(gate, lambda: self.catalog, self.load)
        with self.assertRaises(ValueError):
            backend.workspace(headers)
        self.assertEqual(self.loaded, [])

    def test_expired_grant_never_creates_a_session(self):
        gate = self.make_gate()
        link = self.link(gate)
        self.ticks[0] = 300
        with self.assertRaises(access.core.Invalid):
            self.redeem_headers(gate, link)
        self.assertEqual(gate.sessions, {})

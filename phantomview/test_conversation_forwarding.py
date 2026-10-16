"""Synthetic ordinary forwarding tests; actual UID checks have a separate CI job."""
import json
import socket
import struct
import threading
import time
import unittest
from unittest.mock import patch

import conversation_forwarding as forwarding

POLICY = forwarding.AccountPolicy(29002, 29003, 29001, frozenset({29003, 29004}))
ROUTE = forwarding.Route('telegram', '101', '101', 'principal', 'private')


def frame(doc):
    raw = json.dumps(doc).encode()
    return struct.pack('!I', len(raw)) + raw


def request(**changes):
    return {'schema_version': 1, 'kind': 'ordinary-turn', 'job_id': 'a' * 32, 'persona': 'guide',
            'channel': 'telegram', 'sender': '101', 'conversation': '101', 'tier': 'principal',
            'audience': 'private', 'text': 'How is the project progressing?',
            'expires_at': int(time.time()) + 60} | changes


class Connection:
    family = getattr(socket, 'AF_UNIX', 1)

    def __init__(self, incoming=b'', response=None):
        self.incoming, self.response, self.sent = incoming, response, []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def connect(self, _):
        pass

    def settimeout(self, _):
        pass

    def sendall(self, raw):
        self.sent.append(raw)
        if self.response:
            self.incoming = frame(self.response(json.loads(raw[4:])))

    def recv(self, size):
        part, self.incoming = self.incoming[:size], self.incoming[size:]
        return part


def response(doc):
    return {'schema_version': 1, 'kind': 'ordinary-reply', 'job_id': doc['job_id'], 'text': 'Project summary'}


class ConversationForwardingTests(unittest.TestCase):
    def setUp(self):
        unix = patch.object(forwarding.socket, 'AF_UNIX', getattr(socket, 'AF_UNIX', 1), create=True)
        unix.start()
        self.addCleanup(unix.stop)
        for target in ('check', 'verify'):
            override = patch.object(forwarding.AccountPolicy, target)
            override.start()
            self.addCleanup(override.stop)
        destination = patch.object(forwarding, '_destination', return_value='/protected/worker.sock')
        destination.start()
        self.addCleanup(destination.stop)
        self.client = forwarding.Forwarder(persona='guide', socket_path='/protected/worker.sock', policy=POLICY)
        self.inbox = forwarding.WorkerInbox(persona='guide', policy=POLICY)

    def forward(self, connection, route=ROUTE, text='Question', **options):
        with patch.object(forwarding.socket, 'socket', return_value=connection):
            return self.client.forward(route, text, **options)

    def test_reply_retains_original_route_and_worker_cannot_select_delivery(self):
        connection = Connection(response=response)
        result = self.forward(connection)
        self.assertIs(result.route, ROUTE)
        self.assertEqual(result.text, 'Project summary')
        self.assertTrue(connection.closed)
        wire = json.loads(connection.sent[0][4:])
        self.assertEqual(wire['persona'], 'guide')
        self.assertEqual(wire['kind'], 'ordinary-turn')
        self.assertNotIn('authorization', wire)

    def test_access_control_or_recipient_fields_and_foreign_job_responses_are_rejected(self):
        for changes in ({'sender': '202'}, {'link': 'https://example.test/#c=hidden'},
                        {'operation': 'issue-access'}, {'kind': 'access-link'}, {'job_id': 'b' * 32},
                        {'schema_version': True}, {'text': ''}, {'text': 'x' * 32769}):
            connection = Connection(response=lambda doc, changes=changes: response(doc) | changes)
            with self.assertRaisesRegex(ValueError, '^' + forwarding.FAILURE + '$'):
                self.forward(connection)
            self.assertTrue(connection.closed)

    def test_reserved_commands_never_reach_worker(self):
        for text in ('/phantomview', ' /PHANTOMVIEW ', '/phantomview project', '/phantomview@bot'):
            connection = Connection(response=response)
            with self.assertRaises(ValueError):
                self.forward(connection, text=text)
            self.assertEqual(connection.sent, [])

    def test_audience_and_direct_route_cannot_be_promoted(self):
        for route in (forwarding.Route('telegram', '101', '202', 'principal', 'private'),
                      forwarding.Route('telegram', '101', '101', 'relay', 'private'),
                      forwarding.Route('telegram', '101', '101', 'open', 'private')):
            with self.assertRaises(ValueError):
                self.forward(Connection(response=response), route)
        route = forwarding.Route('phantomchat', 'a' * 64, 'a' * 64, 'relay', 'shared')
        self.assertIs(self.forward(Connection(response=response), route).route, route)

    def test_worker_rejects_replay_scope_overrides_expiry_and_cross_persona(self):
        first = self.inbox.receive(Connection(frame(request())))
        self.assertEqual(first.persona, 'guide')
        for changes in ({}, {'scope_id': 'other'}, {'kind': 'issue-access'}, {'persona': 'other'},
                        {'expires_at': int(time.time()) - 1}, {'expires_at': int(time.time()) + 300},
                        {'text': '/phantomview'}, {'audience': 'shared'}):
            with self.assertRaises(ValueError):
                self.inbox.receive(Connection(frame(request(**changes))))

    def test_frames_are_bounded_and_duplicate_fields_refused(self):
        for raw in (struct.pack('!I', forwarding.MAX_FRAME + 1), b'\0\0\0\0', frame([]),
                    struct.pack('!I', 7) + b'partial', frame({'schema_version': 1})):
            with self.assertRaises(ValueError):
                self.inbox.receive(Connection(raw))
        raw = b'{"schema_version":1,"schema_version":1}'
        with self.assertRaises(ValueError):
            self.inbox.receive(Connection(struct.pack('!I', len(raw)) + raw))

    def test_authentication_precedes_request_reads_and_prompt_writes(self):
        denied = Connection(frame(request()), response=response)
        with patch.object(POLICY.__class__, 'verify', side_effect=ValueError('sensitive detail')):
            with self.assertRaisesRegex(ValueError, '^' + forwarding.FAILURE + '$'):
                self.forward(denied)
            self.assertEqual(denied.sent, [])
            before = denied.incoming
            with self.assertRaises(ValueError):
                self.inbox.receive(denied)
            self.assertEqual(denied.incoming, before)

    def test_cancelled_or_expired_replies_never_return_for_delivery(self):
        cancelled = threading.Event()

        def late(doc):
            cancelled.set()
            return response(doc)

        with self.assertRaises(ValueError):
            self.forward(Connection(response=late), cancelled=cancelled)
        self.assertEqual(self.client._active, set())
        with self.assertRaises(ValueError):
            self.forward(Connection(response=response), seconds=0)
        expired = forwarding.WorkerJob('a' * 32, 'guide', ROUTE, 'Question', time.monotonic() - 1)
        with patch.object(forwarding.select, 'select', return_value=([], [], [])):
            with self.assertRaises(ValueError):
                self.inbox.reply(Connection(), expired, 'Late answer')

    def test_duplicate_active_conversation_does_not_release_first_claim(self):
        key = ('telegram', '101')
        self.client._active.add(key)
        with self.assertRaises(ValueError):
            self.forward(Connection(response=response))
        self.assertIn(key, self.client._active)
        self.client._active = {('telegram', str(index)) for index in range(8)}
        with self.assertRaises(ValueError):
            self.forward(Connection(response=response))

    def test_worker_reply_has_only_bound_id_and_plain_text(self):
        job = self.inbox.receive(Connection(frame(request())))
        connection = Connection()
        with patch.object(forwarding.select, 'select', return_value=([], [], [])):
            self.inbox.reply(connection, job, 'Answer')
        doc = json.loads(connection.sent[0][4:])
        self.assertEqual(set(doc), {'schema_version', 'kind', 'job_id', 'text'})
        self.assertEqual(doc['job_id'], job.job_id)
        with patch.object(forwarding.select, 'select', return_value=([connection], [], [])):
            with self.assertRaises(ValueError):
                self.inbox.reply(connection, job, 'Answer after disconnect')


class AccountPolicyTests(unittest.TestCase):
    def test_topology_and_actual_uid_are_enforced(self):
        with patch.object(forwarding.sys, 'platform', 'linux'), patch.object(forwarding.os, 'getuid', return_value=29002, create=True), patch.object(forwarding.socket, 'SO_PEERCRED', 17, create=True):
            POLICY.check('issuer')
            for policy in (forwarding.AccountPolicy(29002, 29002, 29001, frozenset({29002})),
                           forwarding.AccountPolicy(29002, 29003, 29001, frozenset({29002, 29003})),
                           forwarding.AccountPolicy(29002, 29003, 29001, frozenset()),
                           forwarding.AccountPolicy(0, 29003, 29001, frozenset({29003}))):
                with self.assertRaises(ValueError):
                    policy.check('issuer')
            with self.assertRaises(ValueError):
                POLICY.check('worker')
        with patch.object(forwarding.sys, 'platform', 'win32'):
            with self.assertRaises(ValueError):
                POLICY.check('issuer')


if __name__ == '__main__':
    unittest.main()

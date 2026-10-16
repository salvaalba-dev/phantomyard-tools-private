"""Pre-model command lifecycle with synthetic authenticated adapter context."""
from contextlib import ExitStack
from dataclasses import replace
import threading
import unittest
from unittest.mock import Mock, patch

import handoff_client
import native_access_command as command


class NativeAccessCommandTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(handoff_client.sys, 'platform', 'linux'))
        self.uid = self.stack.enter_context(patch.object(command.os, 'getuid', return_value=200, create=True))
        self.stack.enter_context(patch.object(handoff_client.socket, 'SO_PEERCRED', 17, create=True))
        self.policy = handoff_client.ReaderPolicy(100, frozenset({300}))
        self.origin = 'https://view.example:8790'
        self.link = self.origin + '/#c=' + 'a' * 43
        self.sign = Mock(return_value='Nostr synthetic-event')
        self.deliver = Mock(return_value=True)
        self.request = self.stack.enter_context(patch.object(command, 'request_access', return_value=self.link))
        self.now = 1000
        self.options = dict(channel='telegram', scope_id='river-project', socket_path='/private/native.sock',
                            policy=self.policy, origin=self.origin, sign_authorization=self.sign,
                            deliver_direct=self.deliver, wall_clock=lambda: self.now, monotonic=lambda: self.now)
        self.handler = command.NativeAccessCommand(**self.options)
        self.message = command.DirectMessage('101', '42', 1000, '/phantomview', True, True)

    def test_command_uses_fixed_scope_and_direct_sender_without_returning_credentials(self):
        outcome = self.handler.handle(self.message)
        self.assertIs(outcome, command.Outcome.DELIVERED)
        self.sign.assert_called_once_with()
        self.request.assert_called_once_with('/private/native.sock', self.policy, self.origin,
                                             'Nostr synthetic-event',
                                             {'channel': 'telegram', 'sender': '101', 'direct': True,
                                              'principal_authenticated': True, 'scope_id': 'river-project'})
        self.deliver.assert_called_once_with('telegram', '101', self.link)
        self.assertNotIn(self.link, repr(outcome))
        self.assertNotIn('101', repr(self.message))

    def test_other_messages_are_the_only_model_fallthrough(self):
        for text in ('Hello', 'Please send a link', '/status', '/phantomview-other'):
            self.assertIs(self.handler.handle(replace(self.message, text=text)), command.Outcome.NOT_COMMAND)
        self.sign.assert_not_called()
        self.request.assert_not_called()

    def test_reserved_overrides_and_malformed_context_are_consumed_before_signing(self):
        bad = [replace(self.message, text=text) for text in
               ('/phantomview owner', '/phantomview@otherbot', '/PhantomView', '/phantomview\n{}')]
        bad += [replace(self.message, **fields) for fields in
                ({'direct': False}, {'principal_authenticated': False}, {'direct': 1},
                 {'sender': '00101'}, {'sender': '-1'}, {'sender': str(2**53)},
                 {'message_id': '0'}, {'message_id': '../42'}, {'sent_at': True},
                 {'sent_at': 939}, {'sent_at': 1061})]
        for message in bad + [None, {'text': '/phantomview'}]:
            with self.subTest(message=type(message).__name__):
                self.assertIs(self.handler.handle(message), command.Outcome.REJECTED)
        self.sign.assert_not_called()
        self.request.assert_not_called()
        self.deliver.assert_not_called()

    def test_duplicate_delivery_is_not_reissued(self):
        self.assertIs(self.handler.handle(self.message), command.Outcome.DELIVERED)
        self.assertIs(self.handler.handle(self.message), command.Outcome.DUPLICATE)
        self.assertEqual(self.sign.call_count, 1)
        self.assertEqual(self.deliver.call_count, 1)

    def test_in_flight_duplicate_is_claimed_before_signer_runs(self):
        entered, release = threading.Event(), threading.Event()

        def sign():
            entered.set()
            if not release.wait(2):
                raise ValueError('Test signer deadline exceeded')
            return 'Nostr synthetic-event'

        self.sign.side_effect = sign
        results = []
        thread = threading.Thread(target=lambda: results.append(self.handler.handle(self.message)))
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertIs(self.handler.handle(self.message), command.Outcome.DUPLICATE)
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results, [command.Outcome.DELIVERED])
        self.assertEqual(self.request.call_count, 1)

    def test_callback_failures_do_not_retry_echo_or_fall_through(self):
        for callback in (self.sign, self.request, self.deliver):
            with self.subTest(callback=callback):
                self.handler = command.NativeAccessCommand(**self.options)
                callback.side_effect = RuntimeError(self.link + ' private signing failure')
                self.assertIs(self.handler.handle(self.message), command.Outcome.UNAVAILABLE)
                self.assertIs(self.handler.handle(self.message), command.Outcome.DUPLICATE)
                callback.side_effect = None

    def test_wrong_origin_or_nonfragment_response_never_reaches_delivery(self):
        for link in ('https://other.example/#c=' + 'a' * 43, self.origin + '/?c=' + 'a' * 43, None):
            self.handler = command.NativeAccessCommand(**self.options)
            self.request.return_value = link
            self.assertIs(self.handler.handle(self.message), command.Outcome.UNAVAILABLE)
        self.deliver.assert_not_called()

    def test_delivery_requires_explicit_acknowledgement(self):
        self.deliver.return_value = None
        self.assertIs(self.handler.handle(self.message), command.Outcome.UNAVAILABLE)

    def test_sender_budget_is_bounded_and_only_new_fresh_messages_can_resume(self):
        for index in range(3):
            self.assertIs(self.handler.handle(replace(self.message, message_id=str(index + 1))),
                          command.Outcome.DELIVERED)
        self.assertIs(self.handler.handle(self.message), command.Outcome.UNAVAILABLE)
        self.now += 61
        self.assertIs(self.handler.handle(self.message), command.Outcome.REJECTED)
        self.assertIs(self.handler.handle(replace(self.message, sent_at=self.now)), command.Outcome.DELIVERED)
        self.assertEqual(self.sign.call_count, 4)

    def test_global_budget_cannot_be_bypassed_with_more_senders(self):
        for index in range(16):
            self.assertIs(self.handler.handle(replace(self.message, sender=str(101 + index))),
                          command.Outcome.DELIVERED)
        self.assertIs(self.handler.handle(replace(self.message, sender='999')), command.Outcome.UNAVAILABLE)
        self.assertEqual(self.sign.call_count, 16)

    def test_current_and_shared_model_accounts_are_rejected(self):
        for uid in (0, 100, 300, 201):
            self.uid.return_value = uid
            self.assertIs(self.handler.handle(self.message), command.Outcome.REJECTED)
        self.sign.assert_not_called()
        self.uid.return_value = 300
        with self.assertRaises(ValueError):
            command.NativeAccessCommand(**self.options)

    def test_configuration_has_no_insecure_origin_or_email_fallback(self):
        for fields in ({'channel': 'email'}, {'scope_id': ''}, {'origin': 'http://view.example'},
                       {'origin': self.origin + '/path'}, {'origin': 'https://user@view.example'},
                       {'origin': 'https://view.example:bad'}, {'origin': self.origin + '\n'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                command.NativeAccessCommand(**(self.options | fields))

    def test_phantomchat_uses_proven_sender_npub_and_event_id(self):
        handler = command.NativeAccessCommand(**(self.options | {'channel': 'phantomchat'}))
        message = replace(self.message, sender='npub1' + 'q' * 58, message_id='a' * 64)
        self.assertIs(handler.handle(message), command.Outcome.DELIVERED)
        self.assertEqual(self.request.call_args.args[-1]['sender'], message.sender)
        self.assertEqual(self.deliver.call_args.args[:2], ('phantomchat', message.sender))


if __name__ == '__main__':
    unittest.main()

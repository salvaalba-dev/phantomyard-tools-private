"""Publication intent, last-moment authorization, outcome reporting and retries."""
import copy
import unittest
import uuid
from unittest.mock import patch

import projection_review
from review_publication import PublicationCoordinator, PublicationOutcomeUnknown
from test_review_consumer import ConsumerFixture


class PublicationTests(ConsumerFixture):
    def setUp(self):
        super().setUp()
        self.decisions = self.propose()
        self.coordinator = PublicationCoordinator(self.consumer)

    def publish(self, **overrides):
        args = {'headers': self.headers, 'request_id': self.request_id, 'decisions': self.decisions,
                'expected_revision': self.previous['revision']} | overrides
        return self.coordinator.publish(**args)

    def test_roundtrip_and_exact_retry_never_republishes(self):
        result = self.publish()
        self.assertTrue(result['published'])
        self.assertTrue(result['audit_confirmed'])
        self.assertFalse(result['replayed'])
        self.assertIsNone(result['publication_warning'])
        self.assertEqual(self.publisher.active()[1]['sequence'], 2)
        self.assertEqual(len(self.publisher.catalog()['resources']), len(self.previous['catalog']['resources']))
        with patch.object(self.publisher, 'publish', side_effect=AssertionError('Must not republish')):
            self.decisions['resources'].reverse()
            retry = self.publish()
        self.assertEqual(retry, result | {'replayed': True})
        events = self.gate.audit.export()
        self.assertEqual(sum(row['event'] == 'review_published' for row in events), 1)

    def test_failed_intent_audit_blocks_publication(self):
        record = self.gate.audit.record

        def fail(event, *args, **kwargs):
            if event == 'review_publish_requested':
                raise OSError('Audit unavailable')
            return record(event, *args, **kwargs)

        with patch.object(self.gate.audit, 'record', side_effect=fail):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(self.publisher.active()[1], self.previous)
        self.assertFalse((self.publisher.root / 'active.next.json').exists())

    def test_failed_final_audit_reports_commit_and_retry_repairs_receipt(self):
        record = self.gate.audit.record

        def fail(event, *args, **kwargs):
            if event == 'review_published':
                raise OSError('Audit unavailable')
            return record(event, *args, **kwargs)

        with patch.object(self.gate.audit, 'record', side_effect=fail):
            result = self.publish()
        self.assertTrue(result['published'])
        self.assertFalse(result['audit_confirmed'])
        retry = self.publish()
        self.assertTrue(retry['audit_confirmed'])
        self.assertEqual(retry['revision'], result['revision'])

    def test_logout_after_staging_prevents_atomic_activation(self):
        write = projection_review.write_new

        def logout(path, value):
            write(path, value)
            if path.name == 'active.next.json':
                self.gate.logout(self.headers)

        with patch.object(projection_review, 'write_new', side_effect=logout):
            with self.assertRaises(ValueError):
                self.publish()
        self.assertEqual(self.publisher.active()[1], self.previous)
        self.assertTrue((self.publisher.root / 'active.next.json').exists())

    def test_source_change_after_staging_prevents_activation(self):
        write = projection_review.write_new

        def change(path, value):
            write(path, value)
            if path.name == 'active.next.json':
                self.source['actors'][0]['tools'].append('drive')

        with patch.object(projection_review, 'write_new', side_effect=change):
            with self.assertRaises(ValueError):
                self.publish()
        self.assertEqual(projection_review.read_json(self.publisher.root / 'active.json'),
                         {'revision': self.previous['revision']})

    def test_policy_revocation_after_staging_prevents_activation(self):
        write = projection_review.write_new

        def revoke(path, value):
            write(path, value)
            if path.name == 'active.next.json':
                self.org['policies']['phantomview']['human_action_grants']['secretary'].pop('resource.classify')

        with patch.object(projection_review, 'write_new', side_effect=revoke):
            with self.assertRaises(ValueError):
                self.publish()
        self.assertEqual(projection_review.read_json(self.publisher.root / 'active.json'),
                         {'revision': self.previous['revision']})

    def test_caller_mutation_cannot_replace_detached_decisions_or_cookie(self):
        write = projection_review.write_new

        def mutate(path, value):
            write(path, value)
            if path.name == 'active.next.json':
                self.headers.clear()
                self.decisions['resources'].clear()

        with patch.object(projection_review, 'write_new', side_effect=mutate):
            self.assertTrue(self.publish()['published'])

    def test_error_after_atomic_switch_reports_committed_with_warning(self):
        publish = self.publisher.publish

        def fail(*args, **kwargs):
            publish(*args, **kwargs)
            raise OSError('Cleanup unavailable')

        with patch.object(self.publisher, 'publish', side_effect=fail):
            result = self.publish()
        self.assertTrue(result['published'])
        self.assertIn('inspect', result['publication_warning'])
        self.assertEqual(self.publisher.active()[1]['revision'], result['revision'])

    def test_unreadable_pointer_reports_unknown_outcome(self):
        with patch.object(self.publisher, 'publish', side_effect=OSError('Writer failed')):
            with patch('review_publication.read_json', side_effect=OSError('Pointer unavailable')):
                with self.assertRaises(PublicationOutcomeUnknown):
                    self.publish()

    def test_conflicting_retry_and_missing_receipts_fail_closed(self):
        self.publish()
        changed = copy.deepcopy(self.decisions)
        changed['resources'][0]['category'] = 'category-2'
        for args in ({'decisions': changed}, {'expected_revision': 'f' * 64},
                     {'expected_revision': '../history'}, {'request_id': str(uuid.uuid4())}):
            with self.subTest(args=args), self.assertRaises((ValueError, OSError)):
                self.publish(**args)
        events = [row for row in self.gate.audit.export() if row['event'] != 'review_publish_requested']
        with patch.object(self.gate.audit, 'export', return_value=events):
            with self.assertRaises(PermissionError):
                self.publish()

    def test_completed_retry_requires_current_session_and_explicit_write_grants(self):
        self.publish()
        self.gate.logout(self.headers)
        with self.assertRaises(ValueError):
            self.publish()
        self.authenticate('101')
        with self.assertRaises(PermissionError):
            PublicationCoordinator(self.consumer).publish(self.headers, self.request_id, self.decisions,
                                                         expected_revision=self.previous['revision'])

    def test_no_intent_receipt_cannot_claim_an_offline_publication(self):
        result = self.consumer.prepare(self.headers, self.request_id, self.decisions)
        self.publisher.publish(result['approval'], result['draft'], expected_revision=self.previous['revision'])
        with self.assertRaises(PermissionError):
            self.publish()


if __name__ == '__main__':
    unittest.main()

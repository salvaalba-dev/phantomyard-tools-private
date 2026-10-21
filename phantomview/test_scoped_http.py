"""Scoped HTTP mode cannot fall through to legacy unfiltered data routes."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import threading
from unittest.mock import Mock

import phantomview as pv
from test_scoped_backend import ProjectionFixture


class ScopedHTTPTests(ProjectionFixture):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), pv.Handler)
        self.server.gate = self.gate
        self.server.access_errors = (ValueError, self.gate.access.core.Invalid)
        self.server.scoped_backend = self.backend
        self.server.observatory = Mock()
        self.server.observatory.data.side_effect = AssertionError('Unfiltered snapshot must not be loaded')
        self.server.observatory.read_note.side_effect = AssertionError('Legacy KB reader must not be called')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, body=None, cookie=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            headers = {'Content-Type': 'application/json', 'Cookie': cookie or self.headers['Cookie']}
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_state_and_sync_return_only_scoped_projection(self):
        for method, path, body in (('GET', '/api/state', None), ('POST', '/api/sync', {})):
            status, view = self.request(method, path, body)
            self.assertEqual(status, 200)
            self.assertEqual(view['counts'], {'persona': 1, 'partner': 1, 'relationship': 1})
            self.assertNotIn(self.hidden, json.dumps(view))
            self.assertNotIn('config', view)
            self.assertEqual({row['kind'] for row in view['navigation']['core']}, {'persona', 'partner'})
            self.assertEqual(view['navigation']['view_revision'], view['view_revision'])
            self.assertTrue(view['navigation']['assistant']['eligible'])
        self.assertEqual(view['navigation']['assistant']['source'], 'session-issuer')

    def test_resource_reads_and_global_search_share_the_same_permissions(self):
        status, resource = self.request('GET', '/api/resource/' + self.project)
        self.assertEqual(status, 200)
        self.assertEqual(resource['id'], self.project)
        status, result = self.request('POST', '/api/search', {'query': 'river'})
        self.assertEqual(status, 200)
        self.assertEqual(result['scope_id'], 'example')
        self.assertEqual(result['organization'], 'example')
        self.assertEqual(len(result['view_revision']), 64)
        self.assertEqual([row['id'] for row in result['results']], [self.project])
        for ident in (self.hidden, self.other, 'f' * 64):
            status, result = self.request('GET', '/api/resource/' + ident)
            self.assertEqual((status, result), (404, {'error': 'Resource unavailable'}))
        self.assertNotIn(self.hidden, self.loaded)

    def test_legacy_and_future_api_routes_are_closed_without_loading_sources(self):
        for method, path in (('GET', '/api/knowledge/' + self.public),
                             ('GET', '/api/reviewed-knowledge/' + self.public),
                             ('GET', '/api/phantombot/status'), ('POST', '/api/phantombot/check'),
                             ('GET', '/api/assistant/status'), ('POST', '/api/assistant/jobs'),
                             ('POST', '/api/config'), ('GET', '/api/future-export')):
            status, _ = self.request(method, path, {} if method == 'POST' else None)
            self.assertEqual(status, 403)
        self.assertEqual(self.loaded, [])

    def test_explicit_reviewed_knowledge_reader_uses_the_same_identified_gate(self):
        from reviewed_knowledge import ReviewedKnowledge
        from test_reviewed_knowledge import knowledge_fixture
        source = knowledge_fixture(self.org)
        loaded = []
        def load(ident):
            loaded.append(ident)
            return source['raw']
        reader = ReviewedKnowledge(self.gate, lambda: source['bundle'], lambda: self.org,
                                   lambda: source['snapshot'], load)
        self.server.reviewed_knowledge = reader
        route = '/api/reviewed-knowledge/' + source['id']
        status, note = self.request('GET', route)
        self.assertEqual(status, 200)
        self.assertEqual(note['content'], 'Reviewed field procedures.')
        self.assertEqual(note['trust'], 'untrusted')
        self.assertNotIn('DO_NOT_DISCLOSE', json.dumps(note))
        source['snapshot']['actors'][0]['knowledge'][0]['searchable'] = False
        loaded.clear()
        self.assertEqual(self.request('GET', route), (404, {'error': 'Resource unavailable'}))
        self.assertEqual(loaded, [])
        reader.gate = object()
        self.assertEqual(self.request('GET', route)[0], 403)
        self.assertEqual(self.loaded, [])

    def test_reviewed_knowledge_does_not_accept_query_identity_or_unsigned_cookie(self):
        from reviewed_knowledge import ReviewedKnowledge
        from test_reviewed_knowledge import knowledge_fixture
        source = knowledge_fixture(self.org)
        forbidden = Mock(side_effect=AssertionError('No note read is allowed'))
        self.server.reviewed_knowledge = ReviewedKnowledge(
            self.gate, lambda: source['bundle'], lambda: self.org, lambda: source['snapshot'], forbidden)
        route = '/api/reviewed-knowledge/' + source['id']
        self.assertEqual(self.request('GET', route + '?human=owner')[0], 400)
        cookie = self.gate.create_session()
        self.assertEqual(self.request('GET', route, cookie='phantomview=' + cookie)[0], 401)
        forbidden.assert_not_called()

    def test_backend_bound_knowledge_is_listed_searched_and_opened_through_current_routes(self):
        from reviewed_knowledge import ReviewedKnowledge
        from scoped_backend import ScopedBackend
        from test_reviewed_knowledge import knowledge_fixture
        source = knowledge_fixture(self.org)
        reader = ReviewedKnowledge(self.gate, lambda: source['bundle'], lambda: self.org,
                                   lambda: source['snapshot'], lambda ident: source['raw'])
        self.server.scoped_backend = ScopedBackend(self.gate, lambda: self.catalog, self.load,
                                                   reviewed_knowledge=reader)
        status, view = self.request('GET', '/api/state')
        self.assertEqual(status, 200)
        self.assertEqual(view['counts']['knowledge'], 1)
        self.assertNotIn('Reviewed field procedures.', json.dumps(view))
        status, result = self.request('POST', '/api/search', {'query': 'field'})
        self.assertEqual(status, 200)
        self.assertEqual([row['id'] for row in result['results']], [source['id']])
        route = '/api/reviewed-knowledge/' + source['id']
        self.assertEqual(self.request('GET', route)[1]['content'], 'Reviewed field procedures.')
        self.server.reviewed_knowledge = object()
        self.assertEqual(self.request('GET', route)[0], 403)

    def test_rejected_small_post_bodies_return_denial_without_opening_sources(self):
        for _ in range(12):
            with self.subTest(attempt=_):
                status, result = self.request('POST', '/api/future-export', {'query': 'x' * 2000})
                self.assertEqual(status, 403)
                self.assertEqual(result, {'error': 'Operation unavailable in the scoped reader'})
        self.assertEqual(self.loaded, [])

    def test_unidentified_cookie_is_not_promoted_to_scoped_access(self):
        cookie = self.gate.create_session()
        status, _ = self.request('GET', '/api/state', cookie='phantomview=' + cookie)
        self.assertEqual(status, 401)
        self.assertEqual(self.loaded, [])

    def test_public_access_info_has_no_snapshot_or_private_identity_metadata(self):
        status, result = self.request('GET', '/api/access-info')
        self.assertEqual((status, result), (200, {'delegated': True, 'scoped': True}))
        self.assertEqual(self.loaded, [])

    def test_query_claims_and_request_scope_overrides_never_select_authority(self):
        self.assertEqual(self.request('GET', '/api/state?human=owner')[0], 400)
        self.assertEqual(self.request('POST', '/api/search', {'query': 'private', 'human': 'owner'})[0], 401)
        self.assertEqual(self.loaded, [])

    def test_existing_cookie_logout_revokes_scoped_projection(self):
        self.assertEqual(self.request('POST', '/api/logout', {})[0], 200)
        self.assertEqual(self.request('GET', '/api/state')[0], 401)
        self.assertEqual(self.loaded, [])

    def test_scoped_static_page_never_bootstraps_the_legacy_client(self):
        def get(path):
            connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
            try:
                connection.request('GET', path)
                response = connection.getresponse()
                return response.status, response.read().decode()
            finally:
                connection.close()
        status, page = get('/')
        self.assertEqual(status, 200)
        self.assertIn('/scoped-ui.js', page)
        self.assertNotIn('/app.js', page)
        for asset in ('/scoped-ui.js', '/scoped-ui.css', '/scoped-chat.js'):
            self.assertEqual(get(asset)[0], 200)
        self.assertEqual(self.loaded, [])
        self.server.scoped_backend = None
        self.assertIn('/app.js', get('/')[1])


    def test_original_delivery_uses_current_acl_and_rejects_query_credentials(self):
        from original_documents import descriptor
        raw = b'<h1>Guide</h1>'
        import hashlib
        value = descriptor(raw, {'contentHash': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}, 'html-text')
        ident = self.add('Original guide', 'document')
        self.replace(ident, {'source': 'reviewed-working-document', 'title': 'Guide', 'original': value})
        self.server.original_documents = Mock()
        self.server.original_documents.read.return_value = raw
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.request('GET', '/api/document-original/' + ident, headers=self.headers)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), raw)
            self.assertEqual(response.getheader('Cache-Control'), 'no-store, private')
            self.assertTrue(response.getheader('Content-Security-Policy').startswith('sandbox;'))
        finally:
            connection.close()
        self.server.original_documents.read.reset_mock()
        for path, cookie, expected in [('/api/document-original/' + self.hidden, None, 404),
                ('/api/document-original/' + ident + '?token=refused', None, 400),
                ('/api/document-original/' + ident, 'phantomview=expired', 401)]:
            status, _ = self.request('GET', path, cookie=cookie)
            self.assertEqual(status, expected)
        self.server.original_documents.read.assert_not_called()

"""Server-owned native turn authority over the existing PhantomOrg projection.

This object is a control-plane handle, never a prompt, browser payload, bearer
credential or claim that an ordinary native CLI enforces record permissions.
"""
import copy
import re
import uuid

from resource_review import revision
from scoped_backend import ScopedBackend
from scoped_knowledge import HEX


def selected_route(navigation, section_id):
    if section_id is None:
        return navigation['assistant']
    if not isinstance(section_id, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}:[a-z][a-z0-9-]{0,47}', section_id):
        raise ValueError('An installed visible section is required')
    if any(row['id'] == section_id for row in navigation['core']):
        return navigation['assistant']
    for module in navigation['modules']:
        if any(row['id'] == section_id for row in module['sections']):
            return module['assistant']
    raise ValueError('An installed visible section is required')


class NativeTurnContext:
    """Bind one native consultation to a current identified session and view.

    Native integration must use these authorized reads rather than an unfiltered
    native store. Providing this handle alone does not constrain native profile,
    memory, retrieval or tools; no native execution method is exposed here.
    """
    def __init__(self, backend, headers, *, section_id=None):
        if not isinstance(backend, ScopedBackend):
            raise ValueError('An existing scoped backend is required')
        self._backend = backend
        self._headers = {'Cookie': headers.get('Cookie', '')}
        self._recipient, directory = backend.gate.identified_scope(self._headers)
        self._session = backend.gate.session_scope(self._headers)[0]
        view = backend.workspace(self._headers)
        route = selected_route(view['navigation'], section_id)
        if route['eligible'] is not True or not route['persona']:
            raise PermissionError('No authorized assistant is selected')
        self._section = section_id
        self._navigation = revision(view['navigation'])
        self._binding = {'schema_version': 1, 'kind': 'native-turn-authority',
            'turn_id': str(uuid.uuid4()), 'organization': self._recipient.organization,
            'human': self._recipient.human, 'persona': route['persona'],
            'issuing_persona': self._recipient.persona, 'scope_id': self._recipient.scope_id,
            'policy_revision': self._recipient.policy_revision,
            'directory_revision': self._recipient.directory_revision,
            'authority_revision': directory.authority_revision, 'view_revision': view['view_revision'],
            'section_id': section_id, 'operation': 'read', 'complete_corpus': False}
        self._closed = False
        self._current()

    def _current(self):
        if self._closed:
            raise ValueError('Native turn authority is closed')
        gate = self._backend.gate
        recipient, directory = gate.identified_scope(self._headers)
        view = self._backend.workspace(self._headers)
        route = selected_route(view['navigation'], self._section)
        if (recipient != self._recipient or gate.session_scope(self._headers)[0] != self._session
                or gate.identified_scope(self._headers)[0] != self._recipient
                or directory.authority_revision != self._binding['authority_revision']
                or view['view_revision'] != self._binding['view_revision']
                or revision(view['navigation']) != self._navigation
                or route['eligible'] is not True or route['persona'] != self._binding['persona']):
            raise ValueError('Native turn authority changed; discard the consultation')
        return view

    def metadata(self):
        """Trusted native control metadata only; do not supply it as model text."""
        self._current()
        return copy.deepcopy(self._binding)

    def read(self, resource_id):
        if not isinstance(resource_id, str) or not HEX.fullmatch(resource_id):
            raise KeyError('Resource unavailable')
        view = self._current()
        record = next((row for row in view['resources'] + view['relations'] if row['id'] == resource_id), None)
        if record is None:
            raise KeyError('Resource unavailable')
        self._current()
        return copy.deepcopy(record)

    def search(self, query):
        self._current()
        result = self._backend.search(self._headers, query)
        if result['view_revision'] != self._binding['view_revision']:
            raise ValueError('Native search authority changed')
        self._current()
        return copy.deepcopy(result)

    def release(self, text):
        """Revalidate before delivery; this is not a model-output ACL classifier.

        A native adapter may call this only after enforcing authority across all
        inference inputs. Generated claims of safe or trusted output do not count.
        """
        if not isinstance(text, str) or len(text.encode('utf-8')) > 64000:
            raise ValueError('A bounded native response is required')
        self._current()
        return {'status': 'complete', 'text': text, **copy.deepcopy(self._binding)}

    def close(self):
        self._closed = True
        self._headers.clear()

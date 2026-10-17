"""Declarative viewer navigation over an existing authorized projection.

No module code, source URLs, filesystem readers or inference are executed here.
Call only with server-owned PhantomOrg/session and current projection objects.
"""
import copy
import re

from assistant import safe_default
from channel_identity import HumanDirectory

LABELS = {'organization': 'Organization', 'department': 'Departments', 'role': 'Roles',
          'persona': 'People', 'human': 'Humans', 'project': 'Projects', 'partner': 'Partners',
          'objective': 'Objectives', 'task': 'Tasks', 'document': 'Documents', 'knowledge': 'Knowledge',
          'procedure': 'Procedures', 'finding': 'Findings', 'component': 'Installation'}
VIEWS = frozenset({'table', 'cards', 'graph', 'document'})
SCOPE_KINDS = frozenset({'organization', 'department', 'project'})
HEX = re.compile(r'[a-f0-9]{64}')
ID = re.compile(r'[a-z][a-z0-9-]{0,47}')
FAILURE = 'A compatible declarative viewer module is required'


def _label(value):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= 80
            and not any(ord(char) < 32 or char in '<>' for char in value))


def validate_module(document):
    if (not isinstance(document, dict)
            or set(document) - {'schema_version', 'api_version', 'id', 'version', 'label',
                                'scope_kinds', 'sections', 'assistant'}
            or not {'schema_version', 'api_version', 'id', 'version', 'label', 'scope_kinds', 'sections'} <= set(document)
            or type(document['schema_version']) is not int or document['schema_version'] != 1
            or type(document['api_version']) is not int or document['api_version'] != 1
            or not isinstance(document['id'], str) or not ID.fullmatch(document['id']) or document['id'] == 'core'
            or not isinstance(document['version'], str) or not re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}', document['version'])
            or not _label(document['label']) or not isinstance(document['scope_kinds'], list)
            or not document['scope_kinds'] or len(document['scope_kinds']) > 3
            or any(not isinstance(kind, str) or kind not in SCOPE_KINDS for kind in document['scope_kinds'])
            or len(set(document['scope_kinds'])) != len(document['scope_kinds'])
            or not isinstance(document['sections'], list) or not 1 <= len(document['sections']) <= 12):
        raise ValueError(FAILURE)
    identifiers = set()
    for row in document['sections']:
        if (not isinstance(row, dict) or set(row) != {'id', 'label', 'kind', 'view'}
                or not isinstance(row['id'], str) or not ID.fullmatch(row['id']) or row['id'] in identifiers
                or not _label(row['label']) or not isinstance(row['kind'], str) or row['kind'] not in LABELS
                or not isinstance(row['view'], str) or row['view'] not in VIEWS):
            raise ValueError(FAILURE)
        identifiers.add(row['id'])
    if 'assistant' in document:
        row = document['assistant']
        if (not isinstance(row, dict) or set(row) != {'persona'}
                or not isinstance(row['persona'], str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', row['persona'])):
            raise ValueError(FAILURE)
    return copy.deepcopy(document)


class ModuleRegistry:
    """Operator-installed manifests only; never discover or import plugins."""
    def __init__(self, manifests=()):
        if not isinstance(manifests, (list, tuple)) or len(manifests) > 24:
            raise ValueError(FAILURE)
        checked = [validate_module(row) for row in manifests]
        if len({row['id'] for row in checked}) != len(checked):
            raise ValueError(FAILURE)
        self._modules = checked

    def navigation(self, *, directory, recipient, projection, default_report, assistant_authorized=None):
        """Describe visible menus; never use menu presence as authorization.

        Projection comes from the existing server-side backend, not request JSON.
        A server-owned optional adapter predicate may authorize a persona route;
        it cannot add data grants. No transport is called by this method.
        """
        if not isinstance(directory, HumanDirectory):
            raise ValueError('Current PhantomOrg authority is required')
        directory.validate(recipient)
        if (not isinstance(projection, dict) or type(projection.get('schema_version')) is not int
                or projection.get('schema_version') != 1
                or projection.get('organization') != recipient.organization
                or projection.get('scope_id') != recipient.scope_id
                or projection.get('policy_revision') != recipient.policy_revision
                or projection.get('complete_corpus') is not False
                or not isinstance(projection.get('view_revision'), str) or not HEX.fullmatch(projection['view_revision'])
                or not isinstance(projection.get('resources'), list) or len(projection['resources']) > 2000):
            raise ValueError('A current server-authorized resource projection is required')
        definitions = directory.scope.policy.get('view_access', {}).get('scope_definitions', {})
        scope = definitions.get(recipient.scope_id)
        if not isinstance(scope, dict) or scope.get('kind') not in SCOPE_KINDS:
            raise ValueError('A declared PhantomOrg scope is required')
        counts, seen = {}, set()
        for row in projection['resources']:
            if (not isinstance(row, dict) or not isinstance(row.get('id'), str) or not HEX.fullmatch(row['id'])
                    or row['id'] in seen or not isinstance(row.get('kind'), str) or row['kind'] not in LABELS
                    or row['kind'] == 'relationship'):
                raise ValueError('Invalid projected viewer resource')
            seen.add(row['id'])
            counts[row['kind']] = counts.get(row['kind'], 0) + 1
        actors = directory.scope.policy['personas']
        try:
            default = safe_default(default_report)['persona']
        except ValueError:
            default = None
        if default not in actors:
            default = None  # An offline assistant must not disable the viewer.
        if any('assistant' in module and module['assistant']['persona'] not in actors for module in self._modules):
            raise ValueError('Module assistant must exist in PhantomOrg')

        def assistant(persona, source):
            if persona is None:
                return {'persona': None, 'eligible': False, 'source': source}
            if persona not in actors:
                raise ValueError('Module assistant must exist in PhantomOrg')
            target_scope = recipient.scope_id in directory.scope.policy['view_access']['persona_scope_grants'].get(persona, [])
            eligible = target_scope and directory.scope.can_enter(recipient.human, persona, recipient.scope_id)
            if assistant_authorized is not None:
                if not callable(assistant_authorized):
                    raise ValueError('A server-owned assistant authorization adapter is required')
                eligible = target_scope and assistant_authorized(recipient, persona) is True
            return {'persona': persona if eligible else None, 'eligible': eligible, 'source': source}

        core = [{'id': 'core:' + kind, 'label': label, 'kind': kind, 'view': 'table', 'count': counts[kind]}
                for kind, label in LABELS.items() if counts.get(kind)]
        result = {'schema_version': 1, 'api_version': 1, 'organization': recipient.organization,
                  'scope_id': recipient.scope_id, 'policy_revision': recipient.policy_revision,
                  'view_revision': projection['view_revision'], 'core': core,
                  'assistant': assistant(default, 'runtime-default'), 'modules': []}
        for module in self._modules:
            if scope['kind'] not in module['scope_kinds']:
                continue
            sections = [dict(row, id=module['id'] + ':' + row['id'], count=counts[row['kind']])
                        for row in module['sections'] if counts.get(row['kind'])]
            if not sections:
                continue
            selected = module.get('assistant', {}).get('persona', default)
            result['modules'].append({'id': module['id'], 'version': module['version'],
                'label': module['label'], 'sections': sections,
                'assistant': assistant(selected, 'module' if 'assistant' in module else 'runtime-default')})
        directory.validate(recipient)
        return result

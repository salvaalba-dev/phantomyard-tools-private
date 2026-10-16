"""Private scope and action policy validation; never authenticates a principal."""
import copy
import re

ACTIONS = {'resource.edit', 'resource.classify', 'view.personal.edit', 'view.shared.edit'}
KINDS = {'organization', 'department', 'project'}
FIELDS = {'scope_definitions', 'persona_scope_grants', 'human_action_grants'}
RESERVED = {'con', 'prn', 'aux', 'nul'} | {f'{prefix}{number}' for prefix in ('com', 'lpt') for number in range(1, 10)}


def identifier(value):
    return (isinstance(value, str) and re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', value) is not None
            and value not in RESERVED)


def validate_view_access(raw, organization, actors, humans, departments=None, projects=None):
    """Validate exact grants, including references, without adding inferred rights.

    Department/project reference sets are supplied when loading organization source.
    Internal policy projections can omit departments because they contain only the
    already-resolved registry; they must still satisfy all registry/grant checks.
    """
    if not isinstance(raw, dict) or set(raw) - FIELDS or 'scope_definitions' not in raw:
        raise ValueError('Explicit scope definitions are required for view access grants')
    scopes = raw['scope_definitions']
    if not isinstance(scopes, dict) or not scopes:
        raise ValueError('Nonempty scope definitions required')
    for ident, row in scopes.items():
        if (not identifier(ident) or not isinstance(row, dict)
                or set(row) - {'kind', 'label'} or not isinstance(row.get('kind'), str) or row['kind'] not in KINDS
                or ('label' in row and (not isinstance(row['label'], str) or not row['label'].strip()))):
            raise ValueError('Invalid scope definition')
        if row['kind'] == 'organization' and ident != organization:
            raise ValueError('Organization scope must use its canonical organization ID')
        if row['kind'] == 'department' and departments is not None and ident not in departments:
            raise ValueError('Department scope references an unknown department')
    persona_grants = raw.get('persona_scope_grants', {})
    action_grants = raw.get('human_action_grants', {})
    if not isinstance(persona_grants, dict) or not isinstance(action_grants, dict):
        raise ValueError('Explicit scope/action grant mappings required')
    if projects is not None:
        if (not isinstance(projects, dict) or any(actor not in actors for actor in projects)
                or any(not isinstance(values, list) or any(not identifier(value) for value in values)
                       or len(set(values)) != len(values) for values in projects.values())):
            raise ValueError('Invalid explicit project grants')

    def scope_list(values):
        if (not isinstance(values, list) or any(not identifier(ident) or ident not in scopes for ident in values)
                or len(set(values)) != len(values)):
            raise ValueError('Unique declared scope IDs required')

    for actor, values in persona_grants.items():
        if not identifier(actor) or actor not in actors:
            raise ValueError('Unknown persona scope principal')
        scope_list(values)
        if projects is not None:
            for ident in values:
                if scopes[ident]['kind'] == 'project' and ident not in projects.get(actor, []):
                    raise ValueError('A project scope also requires an explicit matching project grant')
    if projects is not None:
        for values in projects.values():
            for ident in values:
                if scopes.get(ident, {}).get('kind') != 'project':
                    raise ValueError('Project grant must reference a declared project scope')
    for human, grants in action_grants.items():
        if not identifier(human) or human not in humans or not isinstance(grants, dict) or set(grants) - ACTIONS:
            raise ValueError('Unknown human action principal or capability')
        for values in grants.values():
            scope_list(values)
    return {'scope_definitions': copy.deepcopy(scopes), 'persona_scope_grants': copy.deepcopy(persona_grants),
            'human_action_grants': copy.deepcopy(action_grants)}

"""Deny-by-default policy primitive for a future verified-channel integration.

This module does not authenticate a sender and does not enable extended access.
Categories are exact labels, never a numeric ordering or inherited project right.
"""
import hashlib
import json

from view_permissions import ACTIONS, FIELDS, validate_view_access


class Scope:
    def __init__(self, policy):
        if (not isinstance(policy, dict) or not {"organization", "humans", "personas"} <= set(policy)
                or set(policy) - {"organization", "humans", "personas", "category_zero", "view_access", "human_category_limits"}):
            raise ValueError("Explicit assistant policy required")
        if not isinstance(policy["organization"], str) or not policy["organization"]:
            raise ValueError("Explicit organization required")
        for group in ("humans", "personas"):
            if not isinstance(policy[group], dict):
                raise ValueError("Explicit principals required")
            for principal, row in policy[group].items():
                if group == "humans":
                    if (not isinstance(principal, str) or not principal or not isinstance(row, dict)
                            or set(row) - {"counterpart_persona"}
                            or ("counterpart_persona" in row and
                                (not isinstance(row["counterpart_persona"], str)
                                 or row["counterpart_persona"] not in policy["personas"]))):
                        raise ValueError("Human requires an explicit existing persona counterpart")
                    continue
                if (not isinstance(principal, str) or not principal or not isinstance(row, dict)
                        or set(row) != {"categories", "projects"}):
                    raise ValueError("Explicit category and project grants required")
                for grants in (row["categories"], row["projects"]):
                    if not isinstance(grants, list) or any(not isinstance(x, str) or not x for x in grants):
                        raise ValueError("Grants must be exact nonempty string labels")
        zero = policy.get("category_zero")
        if zero is not None:
            if (not isinstance(zero, dict) or set(zero) != {"owner", "categories"}
                    or not isinstance(zero["owner"], str) or zero["owner"] not in policy["humans"]
                    or not isinstance(zero["categories"], list)
                    or any(not isinstance(c, str) or not c for c in zero["categories"])
                    or "category-0" not in zero["categories"]):
                raise ValueError("Category zero requires a declared human owner and categories")
        counterparts = [h["counterpart_persona"] for h in policy["humans"].values() if "counterpart_persona" in h]
        if len(set(counterparts)) != len(counterparts):
            raise ValueError("Ambiguous human counterpart")
        limits = policy.get('human_category_limits', {})
        if not isinstance(limits, dict):
            raise ValueError('Explicit human category limit mapping required')
        for human, categories in limits.items():
            binding = policy['humans'].get(human)
            persona = binding.get('counterpart_persona') if isinstance(binding, dict) else None
            if (persona is None or zero is not None and human == zero['owner']
                    or not isinstance(categories, list) or not categories
                    or any(not isinstance(c, str) or not c or c == 'category-0' for c in categories)
                    or len(set(categories)) != len(categories)
                    or not set(categories) <= set(policy['personas'][persona]['categories'])):
                raise ValueError('Human category limits may only narrow an ordinary counterpart grant')
        normalized_view = None
        if 'view_access' in policy:
            normalized_view = validate_view_access(
                policy['view_access'], policy['organization'], policy['personas'], policy['humans'],
                projects={key: value['projects'] for key, value in policy['personas'].items()})
        self.policy = json.loads(json.dumps(policy))
        if normalized_view is not None:
            self.policy['view_access'] = normalized_view
        self.revision = hashlib.sha256(json.dumps(self.policy, sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_org(cls, org, default_persona=None):
        """Read source org data, never browser claims or the public dashboard index.

        counterpart_persona and policies.phantomview.project_grants are private
        proposed extensions, not assertions of upstream PhantomOrg support.
        """
        def indexed(name):
            rows = org.get(name, [])
            if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get("id"), str) or not r["id"] for r in rows):
                raise ValueError("Invalid organization principals")
            result = {r["id"]: r for r in rows}
            if len(result) != len(rows):
                raise ValueError("Duplicate organization principal")
            return result
        roles, actors, humans = (indexed(name) for name in ("roles", "actors", "humans"))
        policies = org.get("policies", {})
        levels = policies.get("access_levels", {})
        declared = policies.get("security_categories", {})
        view = policies.get('phantomview', {})
        if not isinstance(view, dict) or set(view) - (FIELDS | {'project_grants', 'human_category_limits'}):
            raise ValueError('Invalid private PhantomView policy')
        projects = view.get("project_grants", {})
        if not all(isinstance(x, dict) for x in (levels, declared, projects)):
            raise ValueError("Invalid organization access policy")
        if "category-0" not in declared:
            raise ValueError("PhantomOrg must declare category-0")
        bindings = {ident: ({"counterpart_persona": human["counterpart_persona"]}
                            if "counterpart_persona" in human else {}) for ident, human in humans.items()}
        personas = {}
        for ident, actor in actors.items():
            role = roles.get(actor.get("role"), {})
            level = levels.get(role.get("access_level"), {})
            lists = [level.get("categories", []), role.get("security_exceptions", []), actor.get("actor_exceptions", [])]
            if any(not isinstance(items, list) for items in lists):
                raise ValueError("Invalid category list")
            categories = [c for items in lists for c in items]
            normalized = []
            for category in categories:
                label = "category-" + str(category) if type(category) is int else category
                if not isinstance(label, str) or label not in declared:
                    raise ValueError("Undeclared category")
                normalized.append(label)
            personas[ident] = {"categories": sorted(set(normalized)), "projects": projects.get(ident, [])}
        policy = {"organization": org["organization"]["id"], "humans": bindings, "personas": personas}
        if 'human_category_limits' in view:
            policy['human_category_limits'] = view['human_category_limits']
        if FIELDS & set(view):
            policy['view_access'] = validate_view_access(
                {key: value for key, value in view.items() if key in FIELDS},
                policy['organization'], actors, humans,
                departments={row['id'] for row in org.get('departments', [])}, projects=projects)
        if "category-0" in declared:
            definition = declared["category-0"]
            if not isinstance(definition, dict):
                raise ValueError("Invalid category zero definition")
            if "owner" in definition:
                if not isinstance(definition["owner"], str) or not definition["owner"].strip():
                    raise ValueError("Invalid explicit category zero owner")
                owner = definition["owner"].strip().casefold()
                matches = [hid for hid, h in humans.items()
                           if hid.casefold() == owner or str(h.get("name", "")).strip().casefold() == owner]
            else:
                # Trusted installation default, never a browser-selected persona.
                if not isinstance(default_persona, str) or default_persona not in actors:
                    raise ValueError("Category zero fallback requires a verified default persona")
                matches = [hid for hid, binding in bindings.items()
                           if binding.get("counterpart_persona") == default_persona]
            if len(matches) != 1:
                raise ValueError("Category zero owner is missing or ambiguous")
            policy["category_zero"] = {"owner": matches[0], "categories": sorted(declared)}
        return cls(policy)

    def is_absolute(self, human):
        return isinstance(human, str) and (self.policy.get("category_zero") or {}).get("owner") == human

    def human_grants(self, human):
        """Derived copy, not a second independently editable human ACL."""
        row = self.policy["humans"].get(human)
        if row is None:
            return None
        if self.is_absolute(human):
            return {"categories": list(self.policy["category_zero"]["categories"]), "projects": [], "all_projects": True}
        if "counterpart_persona" not in row:
            return None
        grants = json.loads(json.dumps(self.policy["personas"][row["counterpart_persona"]]))
        grants['categories'] = [category for category in grants['categories'] if category != 'category-0']
        limits = self.policy.get('human_category_limits', {}).get(human)
        if limits is not None:
            grants['categories'] = [category for category in grants['categories'] if category in limits]
        return grants

    def can_issue(self, human, persona):
        """Policy eligibility only; verified sender authentication is still required."""
        if not isinstance(human, str) or not isinstance(persona, str):
            return False
        row = self.policy["humans"].get(human)
        return (persona in self.policy["personas"] and
                (self.is_absolute(human) or (row is not None and row.get("counterpart_persona") == persona)))

    def permits(self, human, persona, resource):
        """Call only after a separate transport has authenticated the human."""
        if not self.can_issue(human, persona) or not isinstance(resource, dict) or resource.get("organization") != self.policy["organization"]:
            return False
        if resource.get("secret") is not False:
            return False
        if 'view_access' in self.policy:
            scope = resource.get('scope')
            if (not isinstance(scope, dict) or set(scope) != {'kind', 'id'}
                    or not isinstance(scope.get('id'), str)
                    or self.policy['view_access']['scope_definitions'].get(scope['id'], {}).get('kind') != scope['kind']
                    or not self.can_enter(human, persona, scope['id'])
                    or (scope['kind'] == 'project' and resource.get('project') != scope['id'])):
                return False
        category = resource.get("category")
        if not isinstance(category, str) or category == 'category-0':
            return False
        absolute = self.is_absolute(human)
        principals = [self.human_grants(human), self.policy["personas"].get(persona)]
        required = principals[:1] if absolute else principals
        if any(p is None or category not in p["categories"] for p in required):
            return False
        project = resource.get("project")
        if category.startswith("category-4") and (not isinstance(project, str) or not project):
            return False
        if project is not None and (not isinstance(project, str) or
                                    not project or (not absolute and any(project not in p["projects"] for p in principals))):
            return False
        return True

    def can_enter(self, human, persona, scope_id=None):
        """Read-scope eligibility only, after verified identity resolution."""
        if not self.can_issue(human, persona):
            return False
        view = self.policy.get('view_access')
        if view is None:
            return scope_id is None
        if not isinstance(scope_id, str) or scope_id not in view['scope_definitions']:
            return False
        return self.is_absolute(human) or scope_id in view['persona_scope_grants'].get(persona, [])

    def allows_action(self, human, persona, action, scope_id, *, resource=None, owner=None):
        """Explicit capabilities do not follow from category zero or read access."""
        view = self.policy.get('view_access')
        if not isinstance(action, str) or action not in ACTIONS or view is None or not self.can_enter(human, persona, scope_id):
            return False
        if scope_id not in view['human_action_grants'].get(human, {}).get(action, []):
            return False
        if action == 'view.personal.edit':
            return owner == human
        if action in {'resource.edit', 'resource.classify'}:
            return (isinstance(resource, dict) and isinstance(resource.get('scope'), dict)
                    and resource['scope'].get('id') == scope_id
                    and self.permits(human, persona, resource))
        return True

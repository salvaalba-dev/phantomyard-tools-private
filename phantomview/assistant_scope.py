"""Deny-by-default policy primitive for a future verified-channel integration.

This module does not authenticate a sender and does not enable extended access.
Categories are exact labels, never a numeric ordering or inherited project right.
"""
import hashlib
import json


class Scope:
    def __init__(self, policy):
        if not isinstance(policy, dict) or set(policy) != {"organization", "humans", "personas"}:
            raise ValueError("Explicit assistant policy required")
        if not isinstance(policy["organization"], str) or not policy["organization"]:
            raise ValueError("Explicit organization required")
        for group in ("humans", "personas"):
            if not isinstance(policy[group], dict):
                raise ValueError("Explicit principals required")
            for principal, row in policy[group].items():
                if group == "humans":
                    if (not isinstance(principal, str) or not principal or not isinstance(row, dict)
                            or set(row) != {"counterpart_persona"}
                            or not isinstance(row["counterpart_persona"], str)
                            or row["counterpart_persona"] not in policy["personas"]):
                        raise ValueError("Human requires an explicit existing persona counterpart")
                    continue
                if not isinstance(principal, str) or not principal or not isinstance(row, dict) or set(row) != {"categories", "projects"}:
                    raise ValueError("Explicit category and project grants required")
                for grants in row.values():
                    if not isinstance(grants, list) or any(not isinstance(x, str) or not x for x in grants):
                        raise ValueError("Grants must be exact nonempty string labels")
        counterparts = [h["counterpart_persona"] for h in policy["humans"].values()]
        if len(set(counterparts)) != len(counterparts):
            raise ValueError("Ambiguous human counterpart")
        self.policy = json.loads(json.dumps(policy))
        self.revision = hashlib.sha256(json.dumps(self.policy, sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_org(cls, org):
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
        projects = policies.get("phantomview", {}).get("project_grants", {})
        if not all(isinstance(x, dict) for x in (levels, declared, projects)):
            raise ValueError("Invalid organization access policy")
        personas = {}
        for ident, actor in actors.items():
            role = roles.get(actor.get("role"), {})
            level = levels.get(role.get("access_level"), {})
            categories = level.get("categories", [])
            if not isinstance(categories, list):
                raise ValueError("Invalid category list")
            normalized = []
            for category in categories:
                label = "category-" + str(category) if type(category) is int else category
                if not isinstance(label, str) or label not in declared:
                    raise ValueError("Undeclared category")
                normalized.append(label)
            personas[ident] = {"categories": normalized, "projects": projects.get(ident, [])}
        bindings = {ident: {"counterpart_persona": human["counterpart_persona"]}
                    for ident, human in humans.items() if "counterpart_persona" in human}
        return cls({"organization": org["organization"]["id"], "humans": bindings, "personas": personas})

    def human_grants(self, human):
        """Derived copy, not a second independently editable human ACL."""
        row = self.policy["humans"].get(human)
        if row is None:
            return None
        return json.loads(json.dumps(self.policy["personas"][row["counterpart_persona"]]))

    def can_issue(self, human, persona):
        """Policy eligibility only; verified sender authentication is still required."""
        if not isinstance(human, str) or not isinstance(persona, str):
            return False
        row = self.policy["humans"].get(human)
        return row is not None and row["counterpart_persona"] == persona

    def permits(self, human, persona, resource):
        """Call only after a separate transport has authenticated the human."""
        if not self.can_issue(human, persona) or not isinstance(resource, dict) or resource.get("organization") != self.policy["organization"]:
            return False
        if resource.get("secret") is not False:
            return False
        category = resource.get("category")
        # Actor exception category 0 is intentionally not supported by this pilot.
        if not isinstance(category, str) or category == "category-0":
            return False
        principals = [self.human_grants(human), self.policy["personas"].get(persona)]
        if any(p is None or category not in p["categories"] for p in principals):
            return False
        project = resource.get("project")
        if category.startswith("category-4") and (not isinstance(project, str) or not project):
            return False
        if project is not None and (not isinstance(project, str) or
                                    any(project not in p["projects"] for p in principals)):
            return False
        return True

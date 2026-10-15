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
                if not isinstance(principal, str) or not principal or not isinstance(row, dict) or set(row) != {"categories", "projects"}:
                    raise ValueError("Explicit category and project grants required")
                for grants in row.values():
                    if not isinstance(grants, list) or any(not isinstance(x, str) or not x for x in grants):
                        raise ValueError("Grants must be exact nonempty string labels")
        self.policy = json.loads(json.dumps(policy))
        self.revision = hashlib.sha256(json.dumps(self.policy, sort_keys=True).encode()).hexdigest()

    def permits(self, human, persona, resource):
        """Call only after a separate transport has authenticated the human."""
        if not isinstance(resource, dict) or resource.get("organization") != self.policy["organization"]:
            return False
        if resource.get("secret") is not False:
            return False
        category = resource.get("category")
        # Actor exception category 0 is intentionally not supported by this pilot.
        if not isinstance(category, str) or category == "category-0":
            return False
        principals = [self.policy["humans"].get(human), self.policy["personas"].get(persona)]
        if any(p is None or category not in p["categories"] for p in principals):
            return False
        project = resource.get("project")
        if category.startswith("category-4") and (not isinstance(project, str) or not project):
            return False
        if project is not None and (not isinstance(project, str) or
                                    any(project not in p["projects"] for p in principals)):
            return False
        return True

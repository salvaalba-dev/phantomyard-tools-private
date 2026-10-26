"""Generated PhantomOrg category reader; do not edit by hand.

Canonical source: salvaalba-dev/phantomyard-tools/phantomdocs/src/phantomdocs/access.py
Reviewed revision: 88236994bf42f88fe8355d13953cdcff0ba17b4c
Regenerate and verify with sync_category_acl.py. No local access grants.
"""
from __future__ import annotations

import re
import warnings
from typing import Any

_CATEGORY_ID_RE = re.compile(r"^category-\d+(?:-[A-Za-z0-9][A-Za-z0-9_-]*)*$")

def normalize_category(category: int | str) -> str:
    """Canonical ``category-...`` id for a category reference.

    Accepts an int (``2``), a numeric string (``"2"``) or an explicit id
    (``"category-2"``, ``"category-4-almaponia"``). Anything else is returned
    verbatim (it will simply never match a resolved id).
    """
    if isinstance(category, int):
        return f"category-{category}"
    text = str(category).strip()
    if text.startswith("category-"):
        return text
    if text.isdigit():
        return f"category-{text}"
    return text

def _exception_category_id(exc: Any) -> str | None:
    """The category id a role/actor exception grants, or None.

    A grant is a ``category-...`` id (``category-3``, ``category-4``,
    ``category-4-almaponia``). Bare integers are also accepted. Free-text /
    structured exceptions (e.g. prose) are NOT category grants.
    """
    if isinstance(exc, str):
        exc = exc.strip()
        if _CATEGORY_ID_RE.match(exc):
            return exc
    elif isinstance(exc, int):
        return f"category-{exc}"
    return None

def resolved_categories(org: dict[str, Any], actor_id: str) -> list[str]:
    """Category ids an actor may read, after RBAC base + role/actor exceptions."""
    actors = {a.get("id"): a for a in org.get("actors", [])}
    roles = {r.get("id"): r for r in org.get("roles", [])}
    levels = org.get("policies", {}).get("access_levels", {})

    actor = actors.get(actor_id)
    if not actor:
        return []
    role = roles.get(actor.get("role"), {})

    categories: set[str] = set()
    level = levels.get(role.get("access_level"), {})
    cats = level.get("categories")
    if not isinstance(cats, list):
        cats = []  # non-list categories (None/string/...) grant nothing — fail closed
    for cat in cats:
        categories.add(normalize_category(cat))

    for exc in list(role.get("security_exceptions") or []) + list(
        actor.get("actor_exceptions") or []
    ):
        cat_id = _exception_category_id(exc)
        if cat_id:
            categories.add(cat_id)
        elif exc:
            # Not a category grant; carried as prose, not an access grant.
            warnings.warn(
                f"actor {actor_id!r}: exception {exc!r} is not a 'category-...' "
                "grant and is ignored (fail-closed)",
                stacklevel=2,
            )
    return sorted(categories)

def _security_categories(org: dict[str, Any]) -> dict[str, Any]:
    """The declared ``policies.security_categories`` map (id -> spec)."""
    return org.get("policies", {}).get("security_categories", {}) or {}

def _category_parents(org: dict[str, Any]) -> dict[str, str | None]:
    """Map each declared category id to its declared parent id.

    Semantic mode (issue #100): when any category declares an explicit
    ``parent`` field, that field is the authority for the hierarchy — the
    ``-``-prefix in an id is then only canonical *naming*, not the
    authorization algorithm. A ``parent`` that does not reference a declared
    category is treated as a broken link (no parent) so ``can_read`` denies
    fail-closed rather than silently mis-resolving.

    Legacy mode (issue #45): when no category declares ``parent``, the parent
    is the longest declared proper ``-``-prefix, which links only *declared*
    categories — never a blind string match. An undeclared category has no
    parent.
    """
    cats = _security_categories(org)
    declared = set(cats)
    if any("parent" in spec for spec in cats.values()):
        tree: dict[str, str | None] = {}
        for cid, spec in cats.items():
            parent = spec.get("parent")
            tree[cid] = (
                parent if isinstance(parent, str) and parent in declared else None
            )
        return tree
    tree = {}
    for cid in declared:
        candidates = [d for d in declared if d != cid and cid.startswith(d + "-")]
        tree[cid] = max(candidates, key=len) if candidates else None
    return tree

def can_read(org: dict[str, Any], actor_id: str, category: int | str) -> bool:
    """True iff the actor's resolved access covers ``category``.

    A direct grant covers the category itself. Otherwise the category is
    granted when some resolved category is a *declared ancestor* of it — the
    hierarchy comes from ``policies.security_categories`` (issue #45), so an
    undeclared category is denied (fail-closed).
    """
    cat = normalize_category(category)
    if cat not in _security_categories(org):
        return False
    resolved = set(resolved_categories(org, actor_id))
    if cat in resolved:
        return True
    tree = _category_parents(org)
    if cat not in tree:
        return False
    current = tree.get(cat)
    seen: set[str] = set()
    while current is not None and current not in seen:
        seen.add(current)
        if current in resolved:
            return True
        current = tree.get(current)
    return False

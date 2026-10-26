# PhantomOrg category ACL compatibility

PhantomOrg is the only source of category declarations, role grants and persona
exceptions. PhantomView resolves those category grants with the existing
PhantomDocs reader contract rather than maintaining an exact-label-only ACL.
There are no organization, persona or project names embedded in the resolver.

The dependency-free `category_acl.py` subset is generated verbatim from the
reviewed PhantomDocs `access.py` identified in `category_acl_source.json`.
It retains normalization, role/persona grant resolution, declared category parents
and `can_read`. It does not import signing, storage, network or service code.
No new runtime dependency or PhantomBot change is required. CI checks both native
source fingerprints and byte-for-byte generated output against the pinned fork.

The native contract has two existing modes:

- If any category declares `parent`, those explicit references determine the
  hierarchy. Similar names do not imply a parent in this mode.
- For older declarations without any `parent` fields, the longest **declared**
  category prefix determines the parent. An undeclared label is never authorized.

An ancestor grant covers the category itself and its declared descendants. Child
grants never authorize parents or siblings. Category numbers have no ordering.
Broken parent references do not supply an ancestor grant; cyclic traversal stops.
Malformed category definitions are rejected while loading the viewer authority.

`Scope.from_org` resolves effective persona categories before deriving human
grants. Explicit human category limits remain exact allowlists over that resolved
set. Project grants, selected scopes, secret filtering and action permissions are
independent checks and remain unchanged. An inherited category alone does not
authorize another project. Category zero remains an independently declared human
privilege and does not confer write actions or flow upward from a child category.

For example, an authorized category-parent grant can cover `category-4-river`,
while a project-only human restricted to that label cannot read a sibling project,
the parent category or general organization records. All examples are synthetic.

Updating the reader changes the effective authority fingerprint where inherited
grants differ. Existing recipient bindings and reviewed publications must then be
renewed through the normal authority workflow. Deploy and review the candidate
publication together; do not change live categories or disable freshness checks
to work around an old publication. This change does not activate any live setup.

## Maintaining compatibility

Use the exact canonical source identified by the manifest:

```sh
python3 phantomview/sync_category_acl.py /reviewed/phantomdocs/src/phantomdocs/access.py --check
```

Without `--check`, the command regenerates only `category_acl.py`. It verifies
both source hashes before writing. A future canonical update requires reviewing
the manifest, regenerating the subset and rerunning the hierarchy, human-limit,
scope and publication tests. Do not hand-edit the generated resolver or silently
fall back to a different installed library version.

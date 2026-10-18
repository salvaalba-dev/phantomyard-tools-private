# Human category limits

Status: private consumer extension, not a native PhantomBot permission boundary.
PhantomOrg remains the authoritative source for counterparts and grants.

Ordinary humans inherit their counterpart's categories by default. An optional
`policies.phantomview.human_category_limits` mapping can narrow those categories:

```yaml
human_category_limits:
  project-coordinator:
    - category-4-river
```

Each key must identify a registered human with an existing counterpart. Each
nonempty list contains unique, exact category labels already granted to that
counterpart. Unknown humans, unbound humans, additional categories, category zero
and limits on the independent category-zero owner are rejected. Absence preserves
existing inheritance. A limit cannot add projects, scopes or actions, and does
not modify the persona's own categories. Category labels have no numeric ordering
or prefix wildcard: `category-4` does not grant `category-4-river`.

The server applies the intersection before constructing the visible projection,
including counts, menus, search, details and graph endpoints. Existing project,
scope, classification and secret checks still apply. Policy changes invalidate
previous recipient bindings and require fresh links.

Native conversation is unavailable for any human with an explicit limit, even
when the list currently equals the inherited categories. Native collaborative
memory and tools do not enforce this restriction. No alternate assistant is
automatically enabled. The viewer remains usable for authorized records.

## Deployment

Update and verify every consumer of the private policy before adding the field
to a live organization. Older strict consumers reject the new field; do not edit
the live source first. In particular, the historical `phantomorg-human-access.patch`
schema and model do not support this field. This increment adds the viewer consumer
only; it does not update that historical patch or assert standard compiler support.
Preserve exact-base checks for the separate counterpart
patch. This extension does not require changing the native persona or installing
an additional inference service.

Prepare a detached source candidate and access matrix, review the exact diff,
then publish through the existing organization authority workflow. A project-only
human also needs an explicit counterpart project grant and project scope. This
field alone neither creates that scope nor approves any unclassified documents.
Keep contact identifiers and private organization snapshots out of GitHub.

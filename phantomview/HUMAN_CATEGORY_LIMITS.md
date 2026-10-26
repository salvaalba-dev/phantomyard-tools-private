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
not modify the persona's own categories. Counterpart categories are first resolved
through the declared PhantomOrg hierarchy, as in PhantomDocs. A declared parent
grant covers its declared descendants; a child never grants its parent or siblings.
The human limit remains an exact allowlist over that resolved set: listing only
`category-4-river` does not also allow its parent or another project. Category
inheritance does not grant a project, scope, action or native conversation.

See [Category ACL compatibility](CATEGORY_ACL.md) for the pinned reader contract.

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
the live source first. The historical `phantomorg-human-access.patch` schema and
model do not support this field. The separate `phantomorg-category-limits.patch`
extends that exact private proposal with schema, shape, typed model and reference
validation. The preparation helper checks every historical result hash, the
overlay checksum and every resulting file hash. It rejects drift and reapplication
before applying changes to a disposable tree. Neither historical patch is rewritten.
This is a private proposal, not an upstream feature or an installed AU compiler.
This extension does not require changing the native persona or installing
an additional inference service.

After preparing the historical private proposal on its pinned disposable base:

```sh
python3 phantomview/phantomorg_category_limits_patch.py /disposable/source/root
```

The human-access workflow runs the full compiler suite both before and after the
overlay and checks viewer agreement. Model construction preserves existing
positional arguments; category lists are copied. When the absolute owner is
explicitly declared, the compiler rejects restrictions on that owner. If ownership
uses the installation-default fallback, the viewer must resolve it from its
verified installation configuration and reject an owner restriction at load time.

Prepare a detached source candidate and access matrix, review the exact diff,
then publish through the existing organization authority workflow. A project-only
human also needs an explicit counterpart project grant and project scope. This
field alone neither creates that scope nor approves any unclassified documents.
Keep contact identifiers and private organization snapshots out of GitHub.

Installations using a custom organization projector must retain its existing
extension fields and behavior. Do not replace it with the standard compiler or
strip unknown fields to make validation pass. The viewer validates its consumed
policy independently; compiler compatibility does not prove that every custom
organization document conforms to the standard schema.

# AU role projection and reusable adapter review

Status: completed static source review, 2026-10-17. No live execution, write,
service restart, configuration change or module activation. The complete selected
script was read through the authorized administrator file interface. The local
analysis copy matches the source fingerprint recorded in the earlier inspection:
`162b8cc1d889e4f97f96293f8157381068b44acfbbef191f6676f7656d6693e0`.
Live organization data, sidecar contents and persona notes are not committed.

## What the current script actually contributes

The selected `proyeccion-au.py` is a role-briefing generator, not a replacement
organization engine or viewer. It reads an organization YAML mapping and an
optional regulations sidecar and renders a Markdown block for one actor.

| Source logic | Observed contribution |
| --- | --- |
| `load`, lines 38-40; `by_id`, 43-48 | Raw YAML loading and identifier lookup; no full schema or reference validation. |
| `render_block`, 60-173 | Organization identity, department/parent, role/functions/description, reporting lines and access labels. |
| Escalation rendering within `render_block` | Outgoing, incoming and wildcard escalation routes with conditions and cross-department labels. |
| Communication and tools rendering | Envelope rules, request format, message types, hop limit, channels, tools, exclusions and selected actor contact fields. |
| Document rendering | Namespace and actor inbox reference. It does not read referenced documents. |
| Regulations sidecar rendering | Organization, department and role regulation references: path, version, category and owner; also a department-head label. It does not read regulation bodies or verify signatures. |
| `upsert`, 176-187 | Replaces the first matching actor-specific managed block and retains surrounding content, except normalization of blank lines after the block. |
| `main`, 190-234 | Explicit actor-directory mode, optional bulk home-directory discovery, dry-run, source fingerprint and generation timestamp. |

The default destination is a KB role note. The script does not ordinarily rebuild
IDENTITY.md, SOUL.md or runtime memory; the configurable destination is not itself
restricted to the default note. No assistant, listener or resident service is
implemented in this script. Its actual scheduling and invocation history were not
inspected, so this review does not claim that it currently refreshes automatically.

## What is specific to AU and what can be reused

The role-briefing pattern, managed block, input provenance, dry-run and optional
organization/department/role references are reusable. AU-specific choices include
the output name, fallback organization label, local store discovery assumptions,
sidecar conventions and presentation text. Keep installation-owned regulation
paths, versions and ownership declarations in configuration rather than core code.

PhantomOrg's reviewed compiler already renders identity, role, access, escalation,
tools and communication material and preserves managed/manual content. Its access
resolver keeps base categories, role exceptions and actor exceptions separately.
The AU note is a useful consolidated KB briefing and sidecar integration; this
review does not establish a reason to replace it or duplicate the core compiler.

## Limits to address before generalizing

- Access is descriptive only: the script neither loads `policies` to resolve
  categories nor authenticates humans, evaluates resource ACLs or binds counterparts.
  A printed category or owner is not authorization or a cryptographic signature.
- The exception expression uses actor exceptions **or** role exceptions. When both
  are populated, the note hides the role exceptions. A reusable renderer must use
  the authoritative resolver and retain both origins without inventing new grants.
- Source hashes are stable for unchanged input bytes, but timestamps change on each
  run and files are rewritten unconditionally. This is not byte-idempotent refresh.
- Duplicate IDs silently overwrite earlier entries. Missing role/department data
  can render empty labels. Validate the complete selected source before generation.
- Missing, duplicate or malformed managed markers are not rejected consistently;
  a broken marker pair can append another block. Preserve manual annotations and
  reject ambiguous updates rather than guessing.
- Bulk mode discovers all persona stores below the supplied home root. On a shared
  VPS it can include other installations, then abort on an unknown actor after
  earlier writes. Require an explicit installation/actor target list instead.
- The writer has no explicit output containment, symlink refusal, atomic replacement
  or all-target preflight. Add these before turning it into a reusable write adapter.
- Generated notes include channel and document-location metadata. A viewer cannot
  treat their entire contents as public or trust a sidecar label as an access grant.

These are static findings, not claims of observed exploitation or live data loss.
The script was not run to reproduce them against production files.

## Recommended integration boundary

Use an optional organization projection adapter with two bounded consumers:

```text
Authoritative PhantomOrg model + installation-owned supplemental metadata
                              |
                Optional role-briefing adapter
                  /                       \
 Explicit persona KB publication      Authorized viewer records
                                      + declarative viewer module
```

Keep authority in PhantomOrg. The adapter maps supplemental material to stable
organization/actor/role/document IDs and retains source revisions and applicable
restrictions. Supplemental metadata may describe regulations, partners, objectives
or tasks, but must not override the organization's grants or category-zero owner.
Unknown classifications remain unavailable to restricted viewer publication.

The KB publisher and visual consumer have different disclosure boundaries. Do not
reuse an unrestricted Markdown note as a filtered viewer response or imply that
viewer ACLs isolate PhantomBot's collaborative native knowledge. The visual path
must authorize records, dependencies, counts, search results and document bodies
before exposing them. Native conversation retains its existing stated boundary.

The current `viewer_modules.py` contract supplies additive, namespaced sections
and eligible existing-persona assistant selection over an already authorized
projection. It does not discover or execute plugin code, read arbitrary paths,
run generators or grant data access. Use supported document/procedure kinds for
regulation views initially. New record kinds or data providers need an explicit
versioned contract; a navigation manifest alone cannot ingest sidecar content.

This can belong to the broader multifunctional adaptation layer, but keep the
source adapter, optional KB publisher and UI manifest separate. Do not add a
second policy database, organization service, scheduler or resident agent. Reuse
explicit setup/refresh hooks when an implementation is authorized and compatible.

## Suggested execution sequence

1. Preserve the current AU script and its files. Define an additive adapter contract
   with generic input/output identifiers and one installation-owned configuration.
2. Build a pure briefing model from validated PhantomOrg data plus supplemental
   references, using synthetic examples. Keep authorization distinct from rendering.
3. Test exception composition, duplicate/missing references, unchanged-input no-op,
   malformed markers, manual content preservation, explicit target containment,
   denied derived records and failures before any multi-target write.
4. Preview generated briefs and viewer records on disposable fixtures. Compare
   sections against the current AU output and keep useful local behavior.
5. Only then stage a reversible, explicitly scoped AU integration. Add a visual
   module when authorized data exist; do not replace the existing projector merely
   because a standard package was absent from the inspected execution paths.

## Evidence and verification

The script was parsed as Python source and its complete functions reviewed; no
import or execution of the script was needed. Comparison used the pinned reviewed
PhantomOrg compiler (`build.py`, `blocks.py`, `access.py`) and the existing private
viewer module/source-adapter contracts. This documentation increment adds no code,
new services or runtime test claims. Adapter implementation remains proposed.

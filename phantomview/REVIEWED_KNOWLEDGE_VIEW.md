# Optional reviewed knowledge detail reader

Status: implemented and tested in private development. Not configured in AU.
This adds authorized knowledge cards, global text search and complete-note
retrieval to the opt-in identified reader, not a new
classifier, assistant, service, scheduler or native memory boundary.

## Existing authority and sources

`ReviewedKnowledge` reuses `resource_review.reviewed_catalog`, the current
`HumanDirectory.permits` decision and the existing collector provenance checks.
Protected application code supplies the same `IdentifiedGate` used by the scoped
backend and four current loaders:

```python
from reviewed_knowledge import ReviewedKnowledge

reader = ReviewedKnowledge(
    gate,
    review_loader=load_active_review,
    organization_loader=load_selected_phantomorg,
    snapshot_loader=load_current_selected_snapshot,
    note_loader=existing_private_kb_store,
)
backend = ScopedBackend(gate, load_projection_catalog, load_projection_record,
                        reviewed_knowledge=reader)
```

Import `ScopedBackend` from `scoped_backend`. These names illustrate
application-owned existing loaders, not new configuration
files or commands. An approved review is produced by the existing resource review
workflow; request fields, document frontmatter and model output cannot supply it.
An unclassified generated role note does not become approved just because its
publisher or filename is recognized. No classification is inferred from a folder,
persona, numeric category ordering or a document owner.

The production `PublishedReader` now supports this same binding through the
optional protected `reviewed_knowledge` launch object documented in
[READER_LAUNCH.md](READER_LAUNCH.md#optional-reviewed-knowledge). It supplies the
existing review bundle and captured payload store to these loaders, using the
exact same gate and authority as the published metadata reader. It creates no
review database, classifier, background service or native memory restriction.
The launch option remains absent by default and is not enabled in AU.

## Request and disclosure contract

When explicitly configured, `GET /api/reviewed-knowledge/<64-hex-note-id>` returns
one current, complete, approved note under the identified session's information
permissions. The configured reader must use the exact backend gate. The existing
legacy `/api/knowledge/` route remains closed in scoped mode.
The earlier `server.reviewed_knowledge` binding still supports detail-only use;
the backend binding adds discovery/search. Conflicting bindings are rejected.

- Authenticate before reading private review data; authorize before reading bytes.
- Check category, exact scope, project grants and existing secret exclusions with
  the current directory. This does not change category-zero semantics or actions.
- Require the approved payload fingerprint, exact actor/path provenance and an
  eligible, unique current collector entry. Truncated payloads are unavailable.
- Recheck provenance and bytes, review, organization and session before returning
  the complete result. Changed or removed notes need a current valid review.
- Return only ID, actor, title, content, classification, review/payload revisions
  and explicit `trust: untrusted`, `format: markdown`, `excerpt_only: false`.
  Filesystem paths and unrelated payload fields are omitted.
- Denied, unknown and excluded notes have the same generic 404 response. No denied
  note body is opened. Missing configuration or a different gate yields 403;
  expired/unidentified sessions or stale authority yield the existing generic 401.

Markdown remains untrusted content. The current UI uses plain text rendering;
never inject raw HTML. A model consumer must preserve
untrusted evidence provenance and existing JEV handling. Retrieval executes no
instructions and does not bypass the persona's native protections.

## Integration limits and next step

`ScopedBackend.state` merges only current permitted note metadata into its existing
resource collection. Existing menus, graphs and counts therefore use the same
visible records. No body, filesystem path, global review revision or hidden total
is included in a card. Adding a denied note does not change the visible revision.
Opaque ID collisions and aggregate projection bounds reject the complete response.

The existing `/api/search` searches permitted complete note text as well as the
metadata projection, independent of the selected menu. It normalizes case and
accents, returns metadata cards without excerpts, deduplicates matches and keeps
the existing 100-result bound. It checks that knowledge and the current workspace
remain consistent before returning results. Every scan is bounded to 16 MiB of
loaded bytes per pass: up to 16 MiB for selection and independently up to
16 MiB for final verification. Rechecks do not halve corpus capacity; exceeding
either bound returns no partial corpus. A final snapshot revision check rejects
metadata changes during either pass. Direct host-loader calls also require
current approval membership and the exact approved payload fingerprint.
The production binding reads and validates the approval once per scan, then uses
only its request-local approved rows for both body passes. The protected file's
identity, size, timestamps and permissions must still match at completion;
replacement, edits or permission changes discard the response. No approval or
payload cache survives the request. Direct `note()` calls retain their independent
approval and fingerprint checks. Large installations may need a later bounded index rather than larger caps.

The scoped client's Knowledge cards fetch the dedicated full-note endpoint and
check identity and payload revision against the selected card before rendering
with `textContent`. Markdown is displayed as plain text. Existing operation/detail
epochs clear old content and discard stale responses after close, refresh or logout.

No automatic review carry-forward or native-memory restriction is added. Existing
refresh remains responsible for current snapshots and captured payloads.
No extra maintenance process is installed. Upstream PhantomBot and live AU are
unchanged. The next setup step must bind the selected installation's actual approved
review and current loaders before activation; a private preview is not a substitute.

Validation covers allowed/denied reads, independent absolute owner behavior under
the existing policy, project session confinement, source exclusion/ambiguity,
changed content, logout, authority/review drift, detached output, HTTP gate binding,
query identity rejection and unconfigured/legacy route closure.
Additional workspace/UI checks cover body search, authorized menus/counts,
denied-note noninterference, project exclusions, source removal, bounded scans,
ID collisions, search drift and stale or malformed full-note responses. A temporary
loopback preview with synthetic fixtures verifies the menu, search, modal and close
button. It is not deployment or live AU evidence.

Host integration tests cover opt-in construction, protected review inputs,
read-only preflight, current-source exclusion and a complete HTTP flow from the
published reader to visible menus, global body search and plain-text note detail.
The profile UI accepts the reader's exact simple persona ID as well as the
existing organization-qualified form, while rejecting another organization's
identifier. Existing payload-revision and stale-dialog checks remain unchanged.

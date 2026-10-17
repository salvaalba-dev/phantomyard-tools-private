# Optional reviewed knowledge detail reader

Status: implemented and tested in private development. Not configured in AU.
This adds complete-note retrieval to the opt-in identified reader, not a new
classifier, assistant, service, scheduler or native memory boundary.

## Existing authority and sources

`ReviewedKnowledge` reuses `resource_review.reviewed_catalog`, the current
`HumanDirectory.permits` decision and the existing collector provenance checks.
Protected application code supplies the same `IdentifiedGate` used by the scoped
backend and four current loaders:

```python
from reviewed_knowledge import ReviewedKnowledge

server.reviewed_knowledge = ReviewedKnowledge(
    server.scoped_backend.gate,
    review_loader=load_active_review,
    organization_loader=load_selected_phantomorg,
    snapshot_loader=load_current_selected_snapshot,
    note_loader=existing_private_kb_store,
)
```

These names illustrate application-owned existing loaders, not new configuration
files or commands. An approved review is produced by the existing resource review
workflow; request fields, document frontmatter and model output cannot supply it.
An unclassified generated role note does not become approved just because its
publisher or filename is recognized. No classification is inferred from a folder,
persona, numeric category ordering or a document owner.

## Request and disclosure contract

When explicitly configured, `GET /api/reviewed-knowledge/<64-hex-note-id>` returns
one current, complete, approved note under the identified session's information
permissions. The configured reader must use the exact backend gate. The existing
legacy `/api/knowledge/` route remains closed in scoped mode.

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

Markdown remains untrusted content. A future UI must use text rendering or its
reviewed Markdown sanitizer; never inject raw HTML. A model consumer must preserve
untrusted evidence provenance and existing JEV handling. Retrieval executes no
instructions and does not bypass the persona's native protections.

## Integration limits and next step

The endpoint supplies detail retrieval only. It does not add a global KB listing,
counts, search corpus, navigation items, document-body links or automatic review
carry-forward. Those require authorized record discovery and consistent UI
bindings; no private preview or raw collector snapshot should substitute for them.
Existing refresh remains responsible for current snapshots and payloads. No extra
maintenance process is installed. Upstream PhantomBot and live AU are unchanged.

Validation covers allowed/denied reads, independent absolute owner behavior under
the existing policy, project session confinement, source exclusion/ambiguity,
changed content, logout, authority/review drift, detached output, HTTP gate binding,
query identity rejection and unconfigured/legacy route closure.

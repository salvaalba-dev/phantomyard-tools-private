# Versioned metadata approval and publication

`projection_review.py` is an inactive operator library for [selected metadata
drafts](SOURCE_ADAPTERS.md). It registers no HTTP route, model tool, setup hook or
service. The operator authenticates and authorizes the reviewer independently.
Being a declared human, including category zero, grants no write access here.
Hashes establish consistency, not reviewer authentication or external signatures.

## Decisions

A decision document has exactly `schema_version: 1`, `draft_revision`,
`organization_revision` and `resources`. Both revision fields are canonical SHA-256
fingerprints of the complete corresponding input. Each resource has exactly:

```json
{
  "id": "<opaque candidate ID>",
  "payload_sha256": "<candidate payload fingerprint>",
  "category": "category-3",
  "scope": {"kind": "project", "id": "river-project"},
  "project": "river-project",
  "secret": false
}
```

The example requires the category and scope to exist in the actual policy; it
grants nothing itself. No classifications carry over implicitly. Partial batches
require every source dependency and relationship endpoint to be selected too.
Duplicates, missing dependencies, category zero, unknown categories/scopes and
inconsistent project assignments fail closed. Decision ordering is immaterial.

`approve(draft, decisions, org, snapshot_loader, reviewer=..., previous=...)`
reconstructs the current draft twice and returns an approval containing sequence,
previous revision, source provenance and an approved catalog. It contains metadata
only; record bodies remain separate. The supplied reviewer must be declared in the
authoritative organization, but that check is not caller authentication.

## Publication

Construct `PublishedProjection(root, org_loader, snapshot_loader)` with trusted
loaders and a fixed absolute private directory without symlink parents. Model and
browser processes must not have write access. POSIX files use mode 0600 and new
generation directories use 0700; Windows deployments must provide restrictive
filesystem ACLs.

`publish(bundle, draft, expected_revision=...)` acquires an exclusive writer lock,
checks the active revision lease and history, revalidates decisions and sources,
then writes a new immutable generation. Use `None` only for the first publication.
Later calls supply the current approval fingerprint. Each generation contains
`approval.json` and separate opaque record JSON files. History is never overwritten.
After a final source and authority check, new files are fsynced and `active.json`
is atomically replaced with the new fingerprint.

The optional trusted `authorize` callback runs at publisher entry and after
staging the next pointer, immediately before replacement. The protected
[publication coordinator](REVIEW_PUBLICATION.md) uses it to revalidate the
identified reviewer and complete current approval evidence. Offline callers that
omit the callback retain the existing explicit operator trust boundary.

A crash may leave an inactive generation, `active.next.json` or `publish.lock`.
Recovery requires an operator to confirm no writer is running and inspect the
active pointer before removing incomplete staging artifacts. Do not automatically
clear locks or delete completed history. Atomic visibility requires a filesystem
supporting atomic replacement. Directory fsync and full power-loss durability are
not implemented; use a suitable local filesystem rather than an unverified mount.

## Reader integration and remaining work

Trusted embedding can supply `publisher.catalog` and `publisher.record` as scoped
backend loaders after the native-channel, frontend and deployment prerequisites
are met. Catalog loads read metadata only; authorized record bodies are opened
separately. Each loader checks the active pointer, approval fingerprint, full
organization revision and current selected-source draft. Any source addition,
change, removal or exclusion invalidates the entire publication until reviewed
again. Backend final revalidation rejects mixed-publication responses.

This strict initial approach favors consistent reviews over partial stale results.
The opt-in [review queue](REVIEW_QUEUE.md) now prepares drafts during setup and
collector refresh. Offline review, scoped frontend and protected operator
approval/publication libraries are available through their separate guides.
Automatic reuse of unchanged classifications, native channel isolation,
assistant/JEV integration and actual deployment remain pending. The AU reader
and default CLI are unchanged.
Organization-wide ingestion ACL enforcement remains deferred F01.

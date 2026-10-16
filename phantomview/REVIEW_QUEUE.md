# Automatic draft preparation during setup and refresh

The operator can opt into `ReviewQueue` during source collection. It creates
classification drafts automatically and never approves, publishes or grants access.
All draft classifications remain unset. Existing publication generations and their
active pointer are untouched.

The private queue directory must already exist, have appropriate ownership/ACLs
and have no symlink parents. Supply a trusted PhantomOrg source with explicit scope
definitions. The collector snapshot must contain that selected organization.

```sh
python phantomview.py --config /private/collector.json setup --mode existing --org /private/org.yaml --review-root /private/reviews --review-org /private/org.yaml
python phantomview.py --config /private/collector.json sync --review-root /private/reviews --review-org /private/org.yaml
```

Both review flags are required together. Keep them in the operator-owned scheduled
collector command for subsequent automatic refreshes. They are deliberately not
persisted in browser-editable configuration and are not accepted by `serve`.
No timer or service is installed by these commands. A trusted embedding can pass
`review_queue=ReviewQueue(...)` to `Observatory`; its configure, refresh and existing
periodic collector loop then use that same queue.

## Refresh behavior

Each successful collection reconstructs a source-bound draft. Identical drafts
reuse their immutable `<revision>.draft.json` file. Source changes, additions,
removals and exclusions produce a new draft without inheriting old classifications.
Actor diagnostic `checked_at` and per-check `age_minutes` are excluded from source
fingerprints because they are observation clocks. Substantive diagnostic changes
still invalidate evidence. Older approvals containing those volatile fields need
a fresh review after this normalization change.

An exclusive `queue.lock` protects writing. A complete private draft is fsynced
before the queue atomically replaces `review.json`. This metadata pointer contains
schema version, ready/blocked status, draft revision and organization revision;
it contains no source paths or parser errors. Failed collection or preparation
attempts mark the review blocked while retaining historical drafts. Setup and sync
return failure when collection or preparation fails.

`queue.current(snapshot)` is an operator API requiring a fresh matching snapshot
after a successful collection in the current process. It verifies organization,
draft fingerprint and reconstructed source evidence. New processes require a
successful refresh before retrieval. An in-memory invalidation also blocks reads
if storage failure prevents writing the blocked status. A persisted ready marker
alone is never evidence of a successful current collection.

The queue has the same filesystem and recovery assumptions as
[projection publication](PROJECTION_REVIEW.md): protected local storage, atomic
replacement support, explicit operator recovery of abandoned locks/staging files,
and no guarantee of full power-loss durability. No automatic history retention or
garbage collection is implemented; operators must monitor private storage growth.

## Remaining boundaries

There is no review route in the browser or assistant tool for this queue. Existing
HTTP authorization remains unchanged. A separate [offline review interface](REVIEW_INTERFACE.md)
now exports explicit decisions. In-dashboard review, source-aware approval
workflow wiring and the generic scoped frontend still need integration. The AU
collector has not been configured with these flags. Expanded assistant access,
native channel isolation and deployment remain separate steps. Organization-wide
ingestion ACL enforcement remains deferred F01.

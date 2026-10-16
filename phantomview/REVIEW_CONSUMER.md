# Protected proposal approval consumer

`ApprovalConsumer` connects authenticated proposals to versioned approval. It is an
operator-only in-process API, not a browser endpoint, background executor or
publication capability. The UI still creates pending proposals only.

Construct `ApprovalConsumer(review_service, publisher)` with the exact
`PublishedProjection.catalog` and `.record` bound loaders already used by the
service backend. Reader and publisher must share current PhantomOrg authority.
Protect the proposal spool, audit ledger, publication root and returned artifacts
from browser and model writers.

## Receipt and authority

New `review_proposed` events contain a `review_revision` fingerprint binding the
complete private proposal and authenticated recipient metadata. Approval requires
that exact acknowledged receipt in the protected ledger. A pending file alone is
insufficient. Altering the file and recomputing its hash cannot create a matching
audit receipt. Local hashes/ledger are not external approval signatures; their
ownership is part of the trusted operator boundary.

Older proposals without fingerprinted receipts are rejected. If all evidence is
still current, the original verified human can resubmit through the authenticated
review service to record a fresh receipt. Never backfill receipts from unauthenticated
files. Audit retention expiry likewise requires fresh authenticated submission.

## Complete explicit review

`consumer.prepare(headers, request_id, decisions)` requires a current identified
reviewer session. The reviewer comes from the gate, never a supplied human ID.
The trusted operator supplies a complete decision document in the
[projection review format](PROJECTION_REVIEW.md) after reviewing current sources.

The consumer validates:

- Exact proposal schema, UUID, fingerprint and protected acknowledged receipt.
- Current policy eligibility and classification rights of the original proposer
  for both source and destination assignments.
- The unchanged active catalog, current organization and source draft.
- Explicit decisions for every existing catalog ID exactly once. Unrelated
  classifications stay identical; no record is silently added or removed.
- Current reviewer read access and explicit `resource.classify` rights for old and
  new assignments of every catalog row, including unchanged records.
- Category/scope rules, content/provenance fingerprints, complete dependencies
  and history through the independent `projection_review.approve` implementation.
- Fresh reviewer session, publication and proposal evidence before recording the
  correlated `review_approved` audit event.

Category zero adds no write rights. Partial-scope reviewers cannot reaffirm a
wider catalog. Catalogs with secret rows excluded from identified sessions cannot
use this strict complete-catalog consumer; they require the separate protected
offline operator workflow. No permissions are installed to make approval pass.

## Result and publication

Preparation returns a private mapping containing `approval`, `draft` and `receipt`.
The receipt correlates request, proposal and approval fingerprints. The draft
contains private adapted source data. Audit failure prevents an approved result.
Unchanged repeated preparation is idempotent and does not activate a revision.

An authorized operator can pass `approval` and `draft` to `publisher.publish`, using
the approval's `previous_revision` as the expected active lease. Publication
independently rechecks source evidence, full organization and revision history
before the atomic switch. Intervening source/policy changes reject publication.
An intervening publication rejects further consumption of the old proposal.
Logout prevents new preparation but does not erase an already completed, audited
historical approval; publisher checks still apply.

There is no new HTTP approval/publish route, CLI command, service or automatic
polling. Actual operator orchestration, native channel isolation, assistant/JEV
integration and AU deployment remain pending. Organization-wide ingestion
enforcement remains deferred F01.

## Validation

Tests cover the complete synthetic proposal/approval/publication/backend path,
preservation of unrelated rows, duplicate preparation, replay after publication,
tampering with recomputed hashes, missing receipts, partial-scope and category-zero
write denial, source/policy changes, audit failure, logout and mismatched loaders.

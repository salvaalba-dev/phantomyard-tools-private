# Protected operator publication coordinator

`PublicationCoordinator(consumer)` completes the private in-process path from an
acknowledged proposal through explicit complete review to atomic publication.
It uses the same `ApprovalConsumer`, identified gate, audit ledger and protected
`PublishedProjection` loaders. It does not add an HTTP route, CLI command, worker
or automatic polling. The browser continues to submit pending proposals only.

## Invocation and authority

After reviewing the complete decision document, a trusted operator calls:

```python
coordinator.publish(
    reviewer_headers,
    request_id,
    decisions,
    expected_revision=current_approval_revision,
)
```

The expected revision must identify an existing approved generation; initial
publication remains the separate offline operator workflow. Headers supply only
the existing session cookie. The coordinator detaches the cookie and decisions
from caller-owned mutable objects. Never expose this API to model writers or
accept browser-selected filesystem paths.

The consumer checks current proposer and reviewer read/classification rights,
the exact acknowledged proposal, complete decisions and unchanged source evidence.
Category zero supplies no implicit write permission. A metadata-only
`review_publish_requested` receipt must be persisted before publication begins.
The publisher checks the active revision under its exclusive writer lock and
revalidates sources, provenance and history as before.

The coordinator supplies a trusted `authorize` callback to `publisher.publish`.
It checks the same reviewer and repeats complete consumer validation at entry and
again after staging `active.next.json`, immediately before atomic replacement.
Logout, expired sessions, changed policies, changed sources or changed proposal
evidence at that check prevent activation. This is a last synchronous check, not
a transaction spanning external policy writers or session revocation; trusted
loaders and process/storage isolation remain prerequisites.

## Outcomes and retry

Success returns `published`, `revision`, `request_id`, `replayed`,
`audit_confirmed` and `publication_warning`. The result contains no payloads,
channel identifiers or credentials. A final `review_published` receipt correlates
the request, proposal and approval fingerprints. Failure of that final audit write
reports `published: true, audit_confirmed: false`; an already committed pointer is
never rolled back or misreported as an uncommitted operation.

An exception from the publisher triggers protected pointer inspection. If the
new revision is active, the result reports success with a fixed warning requiring
operator inspection of staging/lock state. If the pointer cannot be read,
`PublicationOutcomeUnknown` includes the attempted revision: inspect storage
before retry or recovery. Other publication failures propagate. Failed staging,
inactive generations and writer locks are never automatically removed.

An exact completed retry never calls the publisher again. It requires the same
expected predecessor, an unchanged current source/authority, exact proposal,
approval and publication-intent receipts, complete matching decisions, the same
authenticated reviewer identity and current explicit write rights. The previous
immutable generation is used to reconstruct the approval independently. Decision
ordering is immaterial. Missing/expired evidence, another intervening publication
or conflicting decisions reject the retry. A successful retry can repair a missing
final outcome receipt; it cannot manufacture a missing publication intent.

Receipts are protected local evidence, not external signatures or a tamper-proof
archive. Audit retention is unchanged. Maintain protected local filesystem
ownership and explicit operator recovery, as described in
[projection publication](PROJECTION_REVIEW.md).

## Activation boundary

Synthetic tests cover publication and exact retry, audit failures before/after
activation, logout and source changes after staging, cleanup failures after the
atomic switch, unreadable outcomes, conflicting retries and missing receipts.
No real human grant, classification, AU service or other setup is changed.
Native channel isolation, scoped assistant/JEV integration and deployment remain
pending. Organization-wide ingestion ACL enforcement remains deferred F01.

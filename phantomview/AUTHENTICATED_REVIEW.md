# Authenticated category-change proposals

`ReviewService` is an opt-in proposal boundary for resources that already have
approved classifications. It does not approve drafts, update source metadata or
publish access changes. Unclassified queue items still require the protected
[offline review workflow](REVIEW_INTERFACE.md); this service never exposes them.

A trusted embedding must construct `ReviewService(scoped_backend, private_root)`
and pass it as `review_service=` to `phantomview.serve` with that exact backend.
The backend must use an identified gate with a protected `session_audit.Ledger`.
The private spool must already exist without symlink parents and must not be web
served or model writable. POSIX proposals use mode 0600; Windows requires private
filesystem ACLs. The default CLI and AU configuration remain unchanged.

## Explicit authority

Read access, counterpart association and category zero do not grant classification
rights. The existing PhantomOrg `human_action_grants` must explicitly include
`resource.classify` for the source scope. For example, this policy fragment is a
configuration illustration, not an installed grant:

```json
{
  "human_action_grants": {
    "secretary": {"resource.classify": ["example"]}
  }
}
```

The human and scope must already exist. Each candidate must be visible to the
identified session and pass the current action check. Target categories are exact
existing labels that also pass the human/persona read and action checks. Category
zero is never offered as an information label. Scope, project and secret status
remain fixed; changes to them are outside this increment. This service supports
reclassification proposals, not declassification beyond the requester's authority.

## HTTP and browser flow

When explicitly configured, `GET /api/review` returns only visible, classifiable
records with an available category change, including their current adapted data,
classification and payload fingerprint. No configured service or no applicable
write permission yields a closed response. The public access-info route does not
announce private review authority.

The scoped workspace shows **Review access** only after a successful authenticated
review read. Opening it fetches current review data again. The dialog shows a
record's contents and existing category, offers authorized alternatives and
requires explicit human confirmation before submission. Closing or hiding the
workspace clears review data and guards against stale asynchronous responses.

`POST /api/review` accepts exactly:

```json
{
  "request_id": "00000000-0000-4000-8000-000000000001",
  "base_revision": "<visible review fingerprint>",
  "view_revision": "<authorized view fingerprint>",
  "changes": [
    {
      "id": "<opaque resource ID>",
      "payload_sha256": "<current payload fingerprint>",
      "category": "category-3"
    }
  ]
}
```

There are at most 100 changes and a 64 KiB HTTP body. Duplicate JSON fields,
duplicate resource decisions, identity/scope/secret overrides, unknown categories,
no-op changes and stale evidence are rejected. Query and fragment parameters are
rejected; cookies and exact-origin checks remain the existing authentication
boundary. Issuance, signed payloads and single-use redemption are unchanged.

Public review fingerprints depend on visible review data and current authority,
not a global catalog hash. Adding a denied resource does not change the returned
review candidates or fingerprints. The private proposal records the full catalog
revision for later operator consistency checks; that value is never returned to
the browser.

## Audit, storage and approval boundary

The service records `review_requested` before staging and `review_proposed` after
fresh session, policy, catalog, data and action checks. Audit records contain the
existing random session audit ID, request UUID, queued status and proposal
fingerprint. They contain no
record bodies, categories, channel identities or credentials. The private proposal
contains the identified human/persona/scope metadata, old and proposed
classifications, payload fingerprints and catalog/view revisions, but no resource
bodies, source paths or bearer credentials.

Proposal files are exclusive immutable UUID-named JSON records. Exact retries are
idempotent; conflicting reuse fails. A successful response is HTTP 202 with
`status: pending` and `published: false`. No source, approved catalog or active
publication pointer is modified. The spool refuses new requests once its bounded
directory scan reaches 1,000 entries; concurrent requests can race near that
maintenance threshold. No automatic retention or deletion is implemented.

Storage alone is not acceptance. Audit or revalidation failure after writing can
leave an unacknowledged pending artifact. Such files are never automatically
executed. Filesystem permissions and hashes establish local integrity assumptions,
not a cryptographic approval signature or reviewer authentication for another
system. Operator approval must independently authenticate the reviewer, verify
current action grants, source/provenance and all source dependencies, and use the
versioned approval/publication checks. A pending proposal is not an approved
catalog and must never be fed directly to a publisher.

## Remaining integration

The authenticated proposal UI and HTTP boundary are implemented. The protected
[approval consumer](REVIEW_CONSUMER.md) now checks acknowledged proposals against
explicit complete decisions and current evidence, producing an approved revision
for separate operator publication. There is no `/api/review/approve`
or `/api/review/publish` route. Native channel isolation, JEV/assistant integration,
operator deployment configuration and actual AU activation remain separate work.
No real human grants or other setups are changed by this increment.

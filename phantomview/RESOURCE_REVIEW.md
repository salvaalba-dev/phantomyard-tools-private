# Versioned resource classification

Status: offline operator primitives implemented and tested; no live activation.
This increment covers selected KB exports, not all organization ingestion or all
dashboard records. Organization-wide ingestion remains deferred as requirement
F01 in the [execution plan](EXECUTION_PLAN.md).

## Authority and provenance

`resource_review.py` consumes trusted, JSON-compatible PhantomOrg source and the
fingerprinted draft produced by `scoped_knowledge.prepare_review`. It requires the
explicit scope registry described in [scope access](SCOPE_ACCESS.md). It cannot
infer a project, department or organization scope from a folder or persona name.

Every approved row has an existing actor, a declared nonzero category, a declared
scope with its exact kind, an explicit project value and a strict boolean secret
review. A project scope requires the same project ID. Nonproject scopes cannot
carry a project ID. Existing category-4 checks still require a project. Secret
resources remain excluded from retrieval, including for category-zero humans.

The stable `source_key` hashes the organization, actor and canonical relative KB
path. It survives body changes at the same source location. The collector's opaque
payload ID and complete JSON payload SHA-256 separately identify the reviewed
content revision. Moving or copying a note creates another source identity and
requires explicit review; content similarity never creates an access grant.
Different views consuming one approved catalog use the same classification.
Automatic copy-lineage propagation is not implemented by this increment.

## Review workflow

1. Prepare the existing folder suggestion draft and fingerprint current candidate
   payloads with `prepare_review`. Suggestions and `secret: null` are not approval.
2. An authorized operator reviews the selected contents, exclusions and intended
   category/scope. Decisions bind `review_revision`, `policy_revision` and
   `organization_revision` to the exact draft and authoritative source.
3. For a bulk review, call `decisions_from_folders(draft, org, review)` with exact
   actor/folder decisions. Each rule must explicitly contain `reviewed: true`,
   `category`, `scope`, `project` and `secret`. It applies only to fingerprinted
   members of that exact folder, never descendants or future notes. Unknown or
   duplicate folders fail. A changed draft requires a fresh folder-review binding.
4. Call `approve_review(draft, decisions, org, snapshot_loader, note_loader,
   reviewer=human_id, previous=previous_bundle)` to produce a versioned bundle.
   Omitted candidates receive no approval. An updated bundle replaces the selected
   catalog as a whole; previous rows are not implicitly carried forward.
5. `save_revision(private_directory, bundle)` exclusively creates an immutable
   revision file with owner-only POSIX mode. Existing files are never replaced.
   Load a chosen revision with `load_revision(private_directory, revision_id, org)`
   and materialize it using `reviewed_catalog(bundle, org)`.

For example, after reviewing every candidate in a synthetic folder:

```python
from assistant_scope import Scope
from resource_review import decisions_from_folders, revision

folder_review = {
    "schema_version": 1,
    "review_revision": revision(draft),
    "policy_revision": Scope.from_org(org).revision,
    "organization_revision": revision(org),
    "rules": [{
        "actor": "coordinator",
        "folder": "kb/policies",
        "reviewed": True,
        "category": "category-3",
        "scope": {"kind": "organization", "id": "harbor-foundation"},
        "project": None,
        "secret": False,
    }],
}
decisions = decisions_from_folders(draft, org, folder_review)
```

This example is not a classifier or a content-review substitute. The operator
must obtain the real category and scope from the selected organization and review
the current batch before recording a decision. No installation data is embedded.

## Revision checks and exclusions

Approval checks both current snapshot provenance and payload bytes twice. A note
must remain uniquely selected, searchable, available, untruncated and within size
bounds. Actor, organization, path and opaque ID must agree. Excluded notes and
orphan cached files cannot be approved just because their payload still exists.

Each bundle records its reviewer ID, source keys, content fingerprints, draft and
decision digests, PhantomOrg and policy digests, sequence and previous revision.
Any change to the JSON-compatible organization source invalidates materialization;
this deliberately conservative rule includes category meanings, not only grants.
Historical records remain readable as protected files but cannot be materialized
under changed authority without renewed review. Retrieval still rechecks content
hashes, source selection, current session and permissions independently.

The revision chain detects accidental changes. It is not a signature, verified
identity proof, trusted timestamp, tamper-proof audit log or rollback-prevention
mechanism. An attacker able to rewrite the protected store can recompute hashes.
The supplied reviewer ID records an operator assertion, not channel authentication.

## Activation boundary

All inputs and the revision directory must be protected from browser users and
model processes. The caller supplies fixed directories; storage rejects symlink
paths and traversal IDs and bounds file reads. The operator must establish actual
directory ownership and ACLs, particularly on Windows; Python file mode alone is
not a Windows access policy. Parent directories must not be writable by untrusted
processes. No active-revision pointer or rollback executor is supplied.

There is no HTTP endpoint, assistant tool or automatic deployment. These operator
functions must not be exposed directly as user-facing classification actions.
Future interactive changes need verified human identity, explicit
`resource.classify` authority over the current resource and the proposed new
classification, concurrency control, audit and worker/response rechecks. Category
zero alone does not grant classification or storage-write permissions.

The current AU review remains a draft. Scope migration, content/secret review,
trusted channel handoff and backend filtering must precede expanded assistance.
The live assistant remains the bounded analysis pilot.

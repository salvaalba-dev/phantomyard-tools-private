# Selected source adapters

`source_adapter.py` prepares a private, inert review draft from a trusted collector
JSON export and a trusted PhantomOrg JSON document. It does not approve resources,
publish a catalog, grant permissions, start services or update the live reader.

```sh
python source_adapter.py --snapshot selected-export.json --organization organization.json --output /private/reviews/source-draft.json
```

Use a protected operator-owned directory. The output must be a new absolute file;
existing files and symlink paths are rejected. POSIX creation uses mode 0600;
Windows installations must protect the directory with an appropriate filesystem
ACL. Drafts contain private metadata and must not be committed to a repository.

## Coverage

The adapter selects exactly one eligible organization matching PhantomOrg and
copies an explicit metadata field allowlist for organizations, departments, roles,
personas, humans and document references. Findings, procedures and graph edges
require resolvable selected source references. Foreign organization rows and
explicitly excluded sources are omitted. Missing collection ownership is never
inferred for base records or procedures.

Payloads omit credentials, channel addresses, nested knowledge, source paths,
document bodies, diagnostics, installation inventory and history. These omissions
are intentional coverage boundaries, not claims that the omitted data is public.
KB-derived procedures remain excluded pending a reviewed knowledge adapter.
Document-derived procedures now carry the collector's explicit `source_document`
URN; older exports need a collector refresh before those procedures can resolve.

Resource IDs bind organization, collection and source identity. Source changes
preserve IDs when an explicit identity is stable. Findings and edges without an
upstream ID use a content-derived fallback; changing that content creates a new
identity and requires a new review. Raw-source and adapted-payload fingerprints
are separate, so changes to omitted source fields still invalidate review evidence.
Fingerprints establish revision consistency, not source authenticity.

## Classification and dependencies

Every draft row leaves category, scope, project and secret classification unset.
Existing source labels are not silently converted into grants. Category numbers
are exact policy labels, never an ordered access hierarchy. Category 0 remains a
separate human authority and cannot classify a document.

Findings depend on their source entity. Procedures depend on their source and all
resolved actor/from/to references. Graph edges retain both endpoint dependencies.
The backend validates a bounded acyclic dependency graph and authorizes each row
before opening its payload. A derived row is omitted unless every dependency is
visible and current; classifying only the derived row cannot expose a hidden
source. Missing or stale dependencies also prevent derived counts and search hits.

The draft format is deliberately incompatible with `ProjectionCatalog`, including
when its status is changed manually. The separate versioned approval and publishing
library validates source revisions, authority, all classifications and dependency
restrictions before creating an approved catalog and a current availability
manifest. Do not bypass that step by treating this CLI as a production importer.

## Remaining integration

The inactive [projection review library](PROJECTION_REVIEW.md) now supplies explicit
versioned metadata approval and atomic publication. The opt-in
[operator review queue](REVIEW_QUEUE.md) now invokes draft preparation during setup
and collector refresh, without approval or publication. The classification review UI,
frontend projections, scoped assistant delivery and native channel isolation
remain separate integration steps. AU's live setup is unchanged. Organization-wide
ingestion ACL enforcement remains the deferred requirement F01.

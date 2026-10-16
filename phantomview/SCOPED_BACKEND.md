# Scoped resource projection and HTTP boundary

Status: opt-in generic backend and HTTP dispatch implemented; not enabled on AU.
The current interface still uses its legacy snapshot contract. Collector adapters,
review tooling for non-KB records, scope-specific UI definitions and scoped worker
assistance remain implementation work. Do not enable this mode for production
users as a substitute for those remaining pieces.

## Authoritative catalog

`ScopedBackend` receives an `IdentifiedGate`, a protected approved catalog loader
and a bounded current-record loader. Neither browser fields nor document metadata
can choose authoritative classifications or human identity. Catalogs require:

- `schema_version: 1`, the exact `organization`, `status: approved`, and
  `authority_revision` from the current trusted `HumanDirectory`.
- A `resources` list, with at most 2,000 unique opaque 64-hex IDs. Each row has
  `id`, `kind`, `category`, `scope`, `project`, `secret` and `payload_sha256`.
- Exact existing information categories and declared scope grants, enforced by
  the same directory policy as identified sessions. Category 0 never classifies
  resources; explicit secret exclusions still apply to its human holder.
- For a project scope, the exact same project ID. Nonproject scopes cannot carry
  a project ID. Every `relationship` row also declares two `endpoints` IDs that
  reference nonrelationship catalog records.

Supported resource kinds include organizations, departments, roles, personas,
humans, projects, partners, objectives, tasks, documents, knowledge, procedures,
findings, components and relationships. Adding a menu cannot confer permission
to read any of these kinds. A missing classification grants no access.

The authority digest binds the normalized access policy and source category
definitions. Directory revisions now include that digest, so a category meaning
change invalidates existing identified recipients as well as projection review.
Digests are change detectors, not administrator signatures. Protect catalogs and
their loaders from all model and browser writers. There is no automatic approval
or catalog persistence CLI in this increment.

## Record and source contract

The trusted loader receives only an already-authorized opaque ID and returns
bounded JSON bytes with exactly `id`, `kind` and `data`. `data` is one reviewed
classification unit. Its full record bytes must match the catalog SHA-256.
An example of a synthetic resource is:

```json
{
  "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "kind": "task",
  "data": {"title": "Review partner deliverables", "status": "pending"}
}
```

The sample ID is illustrative; deployments need stable opaque source identities
and independently reviewed provenance. A `data.category` or `data.human` field is
content, never an access grant. Do not bundle differently classified child tasks,
notes, identities, precomputed organization totals or unrelated private metadata
inside one low-scope record. Producers must split independently restricted facts
into separate reviewed records and represent cross-record graph links separately.
This backend cannot infer confidential subfields inside an incorrectly reviewed
record. No adapter currently promotes a legacy actor/KB export into this format.

Relationship `data` has exactly `source`, `target`, `type` and `label`. Source and
target must match its reviewed endpoint IDs. Both endpoints must be present and
authorized before the edge payload is opened. Stale or unavailable endpoints also
remove their incident edges; their existence is not announced to the caller.

`PrivateRecordStore` supplies a fixed private export directory and a fresh trusted
manifest loader. The manifest has `organization` and `resources` entries with
`id`, `available: true` and `searchable: true`. Removed, excluded or ambiguous
manifest entries cannot resurface through cached files. File reads reject
symlinks, traversal and nonregular files and are bounded to 64 KiB per record.
Protect parent directories from untrusted writers and provision actual filesystem
ACLs; Python modes alone do not configure Windows security.

## Projection, search and freshness

The backend authorizes each metadata row before loading its body, searching it or
counting it. A state response contains only permitted resources and relationships,
counts computed from them, the bound organization/scope and a visible-only
`view_revision`. Hidden catalog additions do not change that visible revision or
the returned counts. Raw source paths, configuration, history and global snapshot
metadata are not copied into the response.

Search runs across every permitted record kind, independently of menu selection.
It uses no shared cross-session index and returns at most 100 matching records.
Each request scans at most 8 MiB of authorized record bytes. A changed payload
does not inherit review silently. Selected bytes are rechecked for availability,
then the session and protected catalog are revalidated before releasing the
response. Policy changes, logout or source/catalog changes discard stale results.
Results explicitly do not claim complete organizational corpus coverage.

## Opt-in HTTP integration

An embedding application passes `scoped_backend=backend` to `phantomview.serve`.
The backend and HTTP redemption must share the exact `IdentifiedGate`. The default
CLI does not construct it. Its response schema is a new generic resource model,
not the legacy dashboard snapshot; configurable UI integration is still needed.

When configured, `scoped_http` owns the API surface:

| Route | Behavior |
| --- | --- |
| `GET /api/state` | Current authorized resource projection |
| `POST /api/sync` with `{}` | Fresh authorized projection |
| `POST /api/search` with `query` only | Search across the current permitted view |
| `GET /api/resource/<opaque-id>` | Permitted record, otherwise generic unavailable |
| `GET /api/access-info` | Public scoped/delegated mode flags only |
| Existing access-link, redeem and logout POST routes | Existing protocol retained |
| All other API routes | Denied; never forwarded to legacy handlers |

The legacy KB reader, snapshot/configuration data, version observers, assistant
jobs and future undeclared API routes cannot bypass this dispatch. Assistant
routes stay closed until worker and response-time authorization are integrated.
Ordinary signed analysis cookies do not become identified scoped sessions.
Static application assets remain public and contain no projected private data.

## Validation and remaining work

Tests exercise isolation across people and projects; denied-file read prevention;
relationship endpoint filtering; visible-only counts/revisions; source, policy and
category-definition changes; unknown/secret resources; manifest exclusions; global
search; and actual HTTP dispatch, logout and legacy-route denial.
The isolated Linux account job also connects real signed native issuance, HTTP
redemption and project-filtered HTTP state, asserting that no out-of-project
payload is opened through that complete test path.

An inert [metadata adapter](SOURCE_ADAPTERS.md) now prepares source-bound drafts.
Optional `requires` resource IDs enforce source visibility before derived payload
reads. Missing dependencies and cycles are rejected; denied or stale sources hide
dependent findings and procedures as well as graph relationships.

Remaining work includes reviewing and publishing actual selected-source drafts,
versioned approval tooling for non-KB records, frontend resource/view
definitions, scoped history/exports, native channel isolation, queued assistance,
JEV and audit integration. Organization-wide ingestion enforcement remains the
separate deferred requirement F01. AU's default reader and live data are unchanged.

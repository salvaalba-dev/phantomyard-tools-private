# PhantomView scope aware execution plan

PhantomView will provide one reusable application with identity-bound sessions,
server-enforced resource permissions and interfaces adapted to the user's scope.
Organization and project views share the same access, search, document, assistant
and audit services. Installation names, persona names and organizational structures
must come from configuration rather than application code.

Development takes place in `salvaalba-dev/phantomyard-tools-private`. New code,
comments, documentation, examples, commit messages and PR text use English.
Examples use synthetic data. Collected content, installation inventories,
credentials and private identity mappings are not committed.

## Current baseline

The live assistant remains the bounded analysis pilot. Private, tested components
exist for counterpart-derived permissions, independent category-zero ownership,
verified-recipient session bindings, classification review drafts and scoped KB
retrieval. They do not establish a deployed end-to-end identified assistant.

The native channel handoff, complete backend filtering, worker-time authorization,
scope-specific interface definitions and conversational configuration editing
remain implementation work. See [integration status](VERIFIED_CHANNEL_INTEGRATION.md)
for the current boundaries and [compatibility notes](PHANTOMORG_HUMAN_ACCESS.md)
for the private PhantomOrg extension patch.

## Architecture boundaries

- PhantomOrg is authoritative for human identity, counterpart relationships,
  information categories, scope grants and independently assigned category zero.
- Resource metadata identifies the organization, classification, applicable scope,
  source and reviewed revision. A storage folder or the persona holding a copy
  does not independently confer access.
- Authorization runs before serialization, payload reads and model inference.
  Menus and other presentation choices never grant data access.
- A session binds the verified human, issuing persona, organization, scope and
  policy revision. A browser cannot select an authoritative human or role.
- View definitions select supported components and their authorized data sources.
  Organization views may contain departments; project views may instead contain
  partners, objectives, milestones and tasks. Missing entities are not invented.
- Personal and shared configurations have distinct modification permissions.
  Category zero is absolute human information access within the organization,
  not a document classification or an automatic configuration-administration right.
- The assistant uses the session's persona and permitted evidence. Personalization
  writes validated configuration, not arbitrary generated application code.

## Delivery milestones

### 1 Architecture and baseline

Record the module boundaries, current status, future requirements and acceptance
criteria in this plan. Keep planned behavior distinct from deployed behavior.

Acceptance: the plan is committed and linked from the application documentation.

Commit: `docs: define scope-aware PhantomView architecture`

### 2 PhantomOrg access model

Implementation status: private source patch and runtime primitives prepared;
not deployed. See [scope and action permissions](SCOPE_ACCESS.md).

Complete coordinated schema, model, shape and reference validation for explicit
counterparts and scope grants. Define read, resource-edit, personal-view-edit and
shared-view-edit permissions independently. Preserve existing category meanings;
categories are exact labels, not an inferred numeric hierarchy.

Acceptance: synthetic organizations validate; ambiguous bindings and invalid
grants fail closed; category zero works independently of a persona counterpart.

Commit: `feat: validate scope-aware PhantomOrg permissions`

### 3 Classified organizational resources

Implementation status: versioned offline KB review primitives prepared and tested;
not deployed. See [resource review](RESOURCE_REVIEW.md). The installation's actual
classifications remain draft pending scope migration and content/secret review.
Other dashboard resource types and automatic copy-lineage propagation remain work.

Classify the current selected PhantomView sources using stable resource identities,
source provenance, exact scopes and reviewed content revisions. Prepare bulk review
from folder rules and verified source classifications. Retain collector exclusions
and project checks. Changed content must not inherit approval silently.

Acceptance: draft, changed, excluded and mismatched resources cannot become model
evidence; reviewed resources retain their category across copies and views.

This milestone covers selected PhantomView sources. Organization-wide enforcement
at every ingestion point is deferred under requirement F01 below.

Commit: `feat: add versioned organizational resource classification`

### 4 Verified temporary sessions

Implementation status: recipient-bound signed sessions, a Linux peer-credential
handoff boundary and a receiver-verifying native client are prepared, with a
dedicated disposable cross-account CI job. See [private handoff](TRUSTED_HANDOFF.md). Native
pre-model delivery and provisioned account isolation remain work. The opt-in
reader listener lifecycle is implemented; its default CLI and AU deployment are
unchanged. The native shared-daemon isolation design remains an activation issue;
no expanded session access is enabled.

Implement the native pre-model channel integration and a genuinely trusted
recipient handoff. Preserve the existing single-use signed access-link protocol.
Bind the session to the verified human and issuing persona; validate current
permissions on every extended request. Legacy unidentified sessions remain bounded.

Acceptance: group, relay, unknown identity, forged recipient, expired session and
stale-policy requests fail closed without adding a second routine human login.

Commit: `feat: bind verified channel recipients to scoped sessions`

### 5 Backend filtering

Implementation status: generic classified resource projection, graph/count/search
filtering and closed HTTP dispatch are prepared and tested. See
[scoped backend](SCOPED_BACKEND.md). Legacy-source adapters, non-KB review tooling,
frontend adaptation, scoped history/exports and assistant worker integration remain
work. No live reader activation is implied.

Apply the same resource authorization to detail views, graphs, search, documents,
procedures, history, counters, exports and assistant evidence. Calculate aggregates
from permitted records rather than hiding unauthorized records in the browser.

Acceptance: tests demonstrate isolation between humans and scopes, including
relationship edges, counts, cached data, policy changes and download paths.

Commit: `feat: enforce resource authorization across PhantomView`

### 6 Configurable scope interfaces

Introduce versioned definitions for navigation, pages and supported components.
Provide organization and project definitions over the shared services. Resolve the
appropriate definition from trusted session scope and approved configuration.

Acceptance: synthetic project users receive partner/objective/task views without
requiring departments; organization users retain their appropriate structure.
Unauthorized components cannot fetch protected data, including by direct request.

Commit: `feat: render configurable organization and project views`

### 7 Conversational personalization

Allow the assistant to propose and save narrowly defined, validated view changes.
Default to personal configuration. Shared changes require explicit shared-view
permissions. Preserve version history and rollback; separate configuration changes
from changes to organizational information or its classification.

Acceptance: a request such as "Add a Partners menu showing assigned tasks and
their current status" can produce a persistent supported view when the entities
exist. It cannot create permissions, execute generated code or fabricate records.

Commit: `feat: add assistant-managed view personalization`

### 8 Scoped assistance and traceability

Connect the session's persona to approved evidence and explicit action capabilities.
Revalidate at worker dispatch and before response delivery. Preserve JEV screening.
Record the principal, persona, scope, policy revision, action, outcome and relevant
resource/configuration revisions without recording credentials.

Acceptance: revoked or expired access prevents queued work or response delivery;
JEV holds remain holds; configuration history supports attributable rollback.

Commit: `feat: integrate scoped assistance and auditable changes`

### 9 Pilot and generic installation

Prepare backups and rollback, activate the selected AU pilot after the required
activation review, and verify organization, project, category-zero and personal-view
journeys. Package installation and upgrade steps for other PhantomBot setups.

Acceptance: the pilot passes end-to-end checks without changing unrelated setups;
documentation distinguishes generic installation from installation-specific data.

Commit: `test: validate scoped access and personalization workflows`

## Future requirement F01 Organization wide ingestion ACL

Status: recorded for future implementation; not activated by this plan.

Every information resource entering AU must carry ACL classification metadata
compatible with PhantomOrg. The same generic ingestion contract should be reusable
by other organizations. Coverage includes imported documents, incoming information,
attachments, forms, generated notes and derived content.

The intended contract records the organization, existing information category,
applicable scope or project, classification status, source provenance and revision.
For example, this is a proposed resource envelope, not an existing PhantomOrg field:

```json
{
  "resource_id": "project-partner-brief",
  "acl": {
    "organization": "harbor-foundation",
    "category": "category-3",
    "scope": {"kind": "project", "id": "river-project"},
    "classification_status": "pending"
  }
}
```

The category and scope must exist in the authoritative organization policy.
Pending or unclassified content is unavailable through ordinary retrieval until
reviewed. Classification must not default to a less restricted category merely
because a message arrived through an authenticated channel.

Copies and derived content retain source restrictions. A summary combining several
sources must enforce all applicable source restrictions; selecting a larger
category number is not a valid substitute. Changes to classification require
explicit authority independent of permission to customize a view.

Acceptance for the future implementation: each integrated ingestion adapter
validates the contract, quarantines incomplete classification, preserves provenance
and restrictions through transformations, and supplies metadata that downstream
storage, search, dashboards and assistants can enforce consistently. Adapter and
coverage inventories must identify any ingress routes not yet integrated.

## Commit and deployment discipline

Implemented inactive increment: selected metadata source adapters produce bounded
drafts with source/payload fingerprints and explicit derived-resource dependencies.
The scoped backend enforces those dependencies before reads, counts and search.
See [source adapter coverage](SOURCE_ADAPTERS.md).

Implemented inactive increment: [projection review](PROJECTION_REVIEW.md) supports
explicit metadata classification, immutable revision history and atomic publication
guarded by an expected active revision. Trusted readers reject changed sources or
authority. Setup/refresh hooks, the review UI and actual AU activation remain
pending. These increments do not activate expanded access or implement F01.

Commit each coherent milestone or tested increment to the private repository.
Record validation and remaining boundaries with the change. Keep history linear
and leave upstream repositories untouched. Commit and verify changes before any
deployment; deployment is a separate step with explicit target scope and rollback.

Use meaningful tests for identity, authorization and persistent configuration.
Documentation-only increments need content and link validation rather than new
application tests. Do not report planned features as active functionality.

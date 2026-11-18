# PhantomView: consolidated project status

Reviewed: 2026-11-18. Start here when resuming work. This is the source and
continuity overview; no live-host inspection or deployment was performed for
this documentation change.

## Direction and document precedence

PhantomView belongs to the Phantomyard ecosystem. It presents authorized
organization information and can route conversation to the existing persona
that issued the identified access link. It must preserve native identities,
memory, tools and channel authentication.

Read this overview first, then the one technical contract needed for the task.
The [collaborative viewer plan](../phantomview/COLLABORATIVE_VIEWER_PLAN.md)
remains authoritative for product ownership, trust and conversation behavior.
The [application README](../phantomview/README.md) indexes implementation details.
The earlier [execution plan](../phantomview/EXECUTION_PLAN.md) is historical;
the [viewer architecture](../phantomview/VIEWER_ARCHITECTURE.md) is supporting
detail and yields to the collaborative plan wherever they conflict.

Older statements about pending cutovers, enabled features or installed services
describe their original stage. Verify current installation state separately;
do not combine every historical pending item into a new implementation mandate.

## Ecosystem and ownership

| Component | Owning source | Relationship to PhantomView |
|---|---|---|
| PhantomView | [phantomyard-tools-private](https://github.com/salvaalba-dev/phantomyard-tools-private) | Visual application, collection, projections, identified reader and conversation adapters. This repository is public despite its name. |
| PhantomOrg | [phantomyard-tools/phantomorg](https://github.com/salvaalba-dev/phantomyard-tools/tree/main/phantomorg) | Generates organization policy, including `org.yaml`; defines organizational authority. |
| PhantomDocs | [phantomyard-tools/phantomdocs](https://github.com/salvaalba-dev/phantomyard-tools/tree/main/phantomdocs) | Document records/workflow, scoped matrix brokers and agent-route supervision used by viewer integrations. |
| PhantomBot | [phantombot](https://github.com/salvaalba-dev/phantombot) | Existing persona execution, native identity, memory, tools and channels. |
| PhantomChat / PhantomBridge | [phantomchat](https://github.com/salvaalba-dev/phantomchat), [phantomyard-tools/phantombridge](https://github.com/salvaalba-dev/phantomyard-tools/tree/main/phantombridge) | Existing messaging and transport contracts; integration and authentication require explicit verification. |

PhantomOrg policy governs relevant PhantomDocs and PhantomView reads. PhantomDocs
supplies document references and scoped matrix delivery; PhantomView presents
authorized evidence. Conversation adapters use an existing PhantomBot persona.
Repository boundaries determine change ownership, not architectural isolation.
Component presence alone does not establish a deployed connection.

## Sources of truth and evidence

| Question | Authoritative evidence |
|---|---|
| What code or design was reviewed? | Owning GitHub repository and exact commit or merged PR. |
| What organization policy applies? | Selected installation's authoritative generated organization policy and verified publication/consumer lifecycle. A stale copy is insufficient. |
| What document/version exists? | Native records and supported content readers. Registration, integrity, approval and recipient access remain separate facts. |
| What is installed and working? | Private, dated verification of installed revisions, configuration and behavior. A merge alone does not prove deployment. |
| What did a previous chat report? | Historical evidence to reconcile with current source; not an independent authority. |

Keep operational organization files, identities, private documents, credentials,
access links, host inventories and deployment receipts outside this public repo.

## Reviewed source baseline

| Repository | Reviewed default-branch revision |
|---|---|
| PhantomView | [`e619cda`](https://github.com/salvaalba-dev/phantomyard-tools-private/commit/e619cdafd5e70cbe6ceba6a4bb6e9f8e69e1604c) |
| PhantomOrg / PhantomDocs | [`16edf67`](https://github.com/salvaalba-dev/phantomyard-tools/commit/16edf6798a1b7debb77555919c7e41e61c7a3448) |

These are audit baselines, not permanent deployment pins. Recheck the owning
repository before implementation and distinguish these states:

- **Local candidate:** work exists locally; review and integration remain pending.
- **Merged source:** reviewed behavior exists in GitHub; deployment is separate.
- **Installation verified:** dated evidence establishes the selected host's behavior.

| Merged capability | Source evidence | Separate acceptance still required |
|---|---|---|
| Category inheritance | [Viewer #2](https://github.com/salvaalba-dev/phantomyard-tools-private/pull/2) | Current installation policy and grants. |
| Protected MP4 and download-only XLSX originals | [Viewer #6](https://github.com/salvaalba-dev/phantomyard-tools-private/pull/6), [#7](https://github.com/salvaalba-dev/phantomyard-tools-private/pull/7) | Real media publication/playback; XLSX support does not generate matrices. |
| Approved projection continuity during source drift | [Viewer #8](https://github.com/salvaalba-dev/phantomyard-tools-private/pull/8) | Installation cutover; unapproved additions remain excluded. |
| Scoped project-matrix access and presentation | [Tools #60](https://github.com/salvaalba-dev/phantomyard-tools/pull/60), [#61](https://github.com/salvaalba-dev/phantomyard-tools/pull/61) | Automatic generation/publication and organization-scope activation. |
| Guarded route supervision and onboarding readiness | [Tools #64](https://github.com/salvaalba-dev/phantomyard-tools/pull/64), [#65](https://github.com/salvaalba-dev/phantomyard-tools/pull/65) | Current host health and full-host power-loss recovery. |

Matrix publication, ingestion handover, organization-scope delivery, recipient
coverage and activation candidates were identified locally. The reviewed source
baseline does not establish them as fully integrated or production-ready.
Earlier synthetic tests do not demonstrate either complete operational matrix
automation. No fresh production status is asserted here.

## Ordered work queue

**Next task: organization-policy publication and consumption.** Owner:
`salvaalba-dev/phantomyard-tools`; change the viewer only if its consumer contract
changes. Define the authoritative generated policy, protected publication/access
boundary and freshness behavior. Account for every writer: a consumer lock cannot
serialize writers that do not acquire it. Acceptance covers concurrent writes,
interruption, stale/invalid/unreadable input, recovery and revocation through the
actual consumers, preserving permissions and existing runtime behavior.

**Then: completed processing to matrix publication.** Owner:
`salvaalba-dev/phantomyard-tools`. Bind authenticated completion to exact native
versions, scope, publisher, previous matrix and protected destination. Reconcile
operational tables and counts, preserve identifiers/history, reserve upload
identity durably and recover without duplicate registration or publication.
Acceptance requires a supported real processing path, idempotent retry,
interruption recovery and rejection of incomplete or cross-scope inputs.

**Then: recipient-safe matrix delivery and activation.** Owner:
`salvaalba-dev/phantomyard-tools` for broker/authorization; a separate viewer PR
only for an affected adapter or presentation. Verify every fact in the exact
matrix bytes against current recipient authority, including information absent
from the native manifest. Agent access or a category match alone proves neither
recipient access nor full coverage. Acceptance covers authorized delivery,
cross-scope denial, incomplete coverage, revocation during delivery and safe
retention of previous versions. Production activation is a separate reviewed step.

## Resume without reconstructing every chat

Use this overview, one queue item, the exact owning-repository revision and only
the evidence needed for that item. Reconcile the existing working tree with
current main before selecting changes: untracked files may already be merged,
and differing local files may be older than main. Preserve existing work.

Keep one problem per PR. At each handoff record the task, repository/revision,
candidate or merged changes, relevant validation, precise remaining blocker and
next action. Keep host verification receipts private and dated. If repeated
inspection leaves the same prerequisite unresolved, record that missing contract
instead of reopening unrelated document investigations. Refresh this overview
when a queue item changes; technical contracts remain in their owning sources.

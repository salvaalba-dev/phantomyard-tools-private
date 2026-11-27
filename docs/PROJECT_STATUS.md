# PhantomView: consolidated project status

Updated: 2026-11-28. Original broad source review: 2026-11-18. Start here when
resuming work. This overview separates GitHub source checks from the dated
production verification reported below; its author did not inspect or change
the live host during this documentation update.

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
automation. The reported reader migration below does not establish automatic
matrix generation or publication.

## Reported production verification, 2026-11-21

Source: Maki's VPS verification, relayed by the operator at 23:07 Europe/Madrid
(22:07 UTC) on 2026-11-21. The following are attributed operational observations,
not an independent host check by the documentation author. GitHub separately
confirms that [viewer PR #12](https://github.com/salvaalba-dev/phantomyard-tools-private/pull/12)
is merged.

- **Projection generation 26 is published.** The active pointer selects sequence
  26, reported live since 21:39 UTC. Approval/publication of this generation is
  complete; do not ask for it again based on the earlier pending report.
- **The PR #12 reader migration is applied in production.** Maki reports the
  dedicated reader identity, isolated matrix socket, working audit writes
  (310 events at inspection), no failed units, and verified denial of the former
  reader identity and an unrelated identity.
- **Authenticated matrix delivery works.** Requests with valid Alma, Paco and
  Pepa sessions returned HTTP 200. A standalone unauthenticated curl returning
  403/404 does not establish a delivery failure; the endpoint requires a session.

This supersedes the earlier generation-approval and reader-cutover blockers.
It establishes the reported deployed state, not continuous availability or
coverage of every operational contract. The report does not explicitly verify
the native handoff protocol, every policy refresh/reconciliation transition, or
recovery after a full host power loss; do not mark those independently verified
without their own dated evidence.

[Viewer PR #11](https://github.com/salvaalba-dev/phantomyard-tools-private/pull/11)
is superseded by #12 and is retained as closed historical design work. Do not
implement its dedicated-helper prototype as an additional production step.

## Ordered work queue

### 1. Protected matrix host overlay deployed for Alma

[PR #73](https://github.com/salvaalba-dev/phantomyard-tools/pull/73)
merged as b424ddf and was deployed to Alma's matrix service on 2026-11-28
(Europe/Madrid). An authenticated PhantomView request returned the same v25
matrix before and after the deployment. The read and the successful service
exit were within the 55-second and 65-second limits. The matrix socket was
active after the change and no rollback was needed.

See the [PR #73 production deployment handoff](PR73_PRODUCTION_HANDOFF.md)
for the scope of the verification and how to locate the restricted recovery record.

### 2. Automate both operational matrices

Owner: `salvaalba-dev/phantomyard-tools`, with a viewer change only for an affected
adapter or presentation. **Both automations remain incomplete:** Pepa's AU
organization matrix and Alma's ALMAPONIA project matrix. Publishing projection
generation 26 and deploying the reader do not generate or publish either matrix.

Before activation:

1. Establish the authoritative organization-policy publication/consumer lifecycle.
   The [committed-policy reader contract](../phantomview/COMMITTED_POLICY_READER.md)
   coordinates tools/viewer candidates, binds authority to a committed revision
   and holds a shared lock through delivery. Confirm its actual review,
   publication, privileged integration and installation status. A reader migration
   alone does not prove it deployed. Account for writers that do not share a lock.
2. Connect each supported real ingestion/completion path to authenticated native
   version evidence, the correct organization/project scope, publisher, previous
   matrix and protected destination. Keep Alma's ALMAPONIA identifier allocation
   and existing identifiers; do not duplicate registrations.
3. Generate faithful operational tables and counts, reconcile existing manual
   content, and preserve prior versions/history. An appended generated section
   or a successful document index alone is insufficient.
4. Publish with durable upload identity, idempotent retries and interruption
   recovery, then update the viewer binding atomically.
5. Verify every fact in the exact matrix bytes against current recipient
   authority, including facts absent from the native manifest. Agent access or
   a category match alone establishes neither recipient access nor full coverage.
   Test authorized delivery, cross-scope and incomplete-coverage denial,
   revocation during delivery and safe retention of prior versions.

Acceptance requires a verified end-to-end run for **each** scope, retry without
duplicates and recovery from interruption. Review production activation
separately; do not expand permissions or modify PhantomBot to infer completion.

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

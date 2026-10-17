# Collaborative PhantomView execution plan

Status: active plan, 2026-10-17. This document supersedes the earlier execution
plan, viewer architecture and native-ACL activation proposals where they conflict.
It records the agreed direction; it does not claim a deployed identified assistant.
Development remains in `salvaalba-dev/phantomyard-tools-private`, with linear
history, English source/documentation/examples and no upstream modifications.

## Product and ownership

PhantomView is a visual interface to an existing PhantomOrg organization and a
conversation surface for the existing persona that issued the human's access link.
It must preserve PhantomBot's collaborative knowledge model rather than create
new persona silos, replacement memories or another inference service.

| Component | Responsibility |
|---|---|
| PhantomBot | Existing persona execution, channel authentication, memory, configured knowledge sharing, credentials, harnesses and native trust/JEV behavior. |
| PhantomOrg | Organization structure, roles, actors, human registry, categories, exceptions, counterparts and applicable organizational scopes. Missing counterpart declarations need a compatible explicit mapping here. |
| PhantomView | Redeem the identified link, resolve current PhantomOrg authority, filter its own visual data, display linked evidence and route conversation to the issuing persona. |
| Optional modules | Add validated views and configured persona routes without granting access or replacing the standard viewer. |
| PhantomBridge / PhantomChat | Existing transports with their own documented contracts; neither is assumed to be a generic authenticated dashboard chat API. |

The standard assistant is the **issuing persona**, not whichever persona happens
to be the machine's default when the browser opens. The configured runtime default
is useful for initial discovery/setup before an identified session exists. An
explicit module override can select another existing persona only after current
PhantomOrg routing eligibility is checked and the UI makes the change visible.

An authenticated channel identifies a sender; PhantomOrg maps that identity to a
human and authority. A signed bot identity alone does not identify the human who
requested a link. Preserve both facts without adding another human login/signature.

## Reviewed source baseline

These are source snapshots, not a live AU installation inventory:

| Repository / revision | Inspected sources and consequence |
|---|---|
| [PhantomBot `5af2706`](https://github.com/phantomyard/phantombot/tree/5af27060327ee8c53fe730dd8b98b6b305c62add) | README, `src/cli/ask.ts`, Telegram core engine and PhantomChat server. Existing persona execution and verified channel principals are reusable. `ask` supports explicit persona, stdin, conversation and native history; it is not itself a sender-authentication interface. |
| [Phantomtools `5e007b4`](https://github.com/phantomyard/phantomtools/tree/5e007b4f2864e52ffef1360df86ed6b5267750cb) | Tool inventory, CONTRIBUTING, PhantomOrg model/spec/access/human compilers and PhantomBridge README. PhantomOrg compiles organizational policy into persona artifacts and an organization-wide human registry. Tools must remain additive. |
| [PhantomChat `2c8e840`](https://github.com/phantomyard/phantomchat/tree/2c8e8403565e5771695e8822f616a157f28258c6) | README. This is a client-side encrypted messaging application; embedding it does not automatically delegate the human's private-key identity to a dashboard session. |
| [Private viewer `d6cfd95`](https://github.com/salvaalba-dev/phantomyard-tools-private/tree/d6cfd95558043380ba3417e7b17b2361a18e39b1/phantomview) | Existing collector/viewer, identified gate, filtered backend, module navigation, observation adapter and experimental native components. Tests and source exist; live deployment and native connection remain separate facts. |

PhantomOrg's upstream `Human` model already records IDs, names, roles and channel
contacts. The inspected model does not contain the private `counterpart_persona`
extension used by the viewer experiment. Preserve that distinction; do not apply
the old exact-base private PhantomOrg patch blindly to the current release.

The contribution guide describes some older runtime behavior. Resolve differences
against the pinned runtime source rather than assuming every historical statement
describes the installed version. In particular, keep actual channel/JEV semantics.

## Reuse, adapt and retire from the standard path

| Existing work | New disposition |
|---|---|
| Graphs, cards, document/KB readers, procedures, global search, findings, installation inventory, status evidence and localization | Reuse. Filter before serialization, counts, search and linked document access. |
| `channel_identity.py`, `identified_access.py`, existing signed-link verifier and session/audit components | Reuse as foundations after checking schema and channel compatibility. Human identity must come from verified channel context. |
| `ScopedBackend`, resource classification and lineage/review components | Reuse for viewer data. This is enforcement of PhantomOrg authority at the viewer boundary, not an independently editable ACL system. |
| `viewer_modules.py`, scoped shell and `runtime_default.py` | Adapt assistant precedence to the session issuer; keep standard generated menus and additive modules. Runtime discovery must not override the issuer. |
| `NativeTurnContext` and view-revision-bound consultation helpers | Retain as inactive research or optional bounded-evidence helpers. Do not require a native conversation to stay within the currently displayed resource subset. |
| Isolated ordinary workers, ephemeral persona/memory builds, copied model credential stores and special native source patches | Not prerequisites of the standard viewer. Preserve history/tests; do not deploy or extend them as a replacement persona architecture. |
| Historical AU readiness report and earlier implementation plans | Keep as dated evidence, not a current requirement to install the retired worker design. |

Current implementation limits must remain explicit: `IdentifiedGate` is bound to
one configured issuer actor, the existing scoped consultation queue routes through
the session persona, and core module navigation now selects the validated session issuer. This route
metadata expresses policy eligibility, not proof of an available native transport.
Supporting several issuing personas in one viewer requires explicit trusted runtime
route registration and issuer-bound lookup, not overwriting a global actor/default
or accepting arbitrary persona/runtime values from the browser.

No runtime files or services are removed by this planning change. Any later cleanup
must distinguish unused source from installed dependencies and have a reversible
targeted migration. Never delete or regenerate a persona's identity or accumulated
memory, and never change the global active persona to route a request.

## Session and conversation contract

1. A human asks an existing persona for a link through an authenticated direct
   channel. The trusted channel path supplies the actual sender, channel and
   receiving persona; message text cannot declare these identities.
2. PhantomOrg resolves the sender and applicable human/persona relationship.
   Explicit category-zero ownership remains independent of an ordinary counterpart.
   Unknown, ambiguous or email-only unverified identity does not gain identified
   access automatically.
3. The normal signed single-use link carries the opaque grant in its fragment.
   Preserve canonical event ID verification, Schnorr verification, signer allowlist,
   freshness/replay protections, exact tag/payload binding, origin binding and locked
   single redemption. Recipient metadata stays server-side. Preserve existing
   configured grant/session lifetimes; verify the pilot's five-minute/30-minute
   settings before deployment rather than silently changing them.
4. Redemption binds the session to the verified human, issuing persona, organization,
   runtime route and current PhantomOrg authority. The browser cannot replace them.
   Never promote a legacy analysis-only link by guessing the human.
5. The viewer filters its data using current PhantomOrg policy and source metadata.
   Categories use the organization's existing meanings. Category zero is an explicit
   information privilege, not an implicit write permission or a new record category.
6. Chat routes to that same existing persona and its native stores. It does not
   create another persona or treat the selected menu as an inference sandbox.
   A separate web conversation ID may be needed for native threading; derive it
   server-side and do not claim it merges automatically with the phone transcript.
7. Revalidate session and routing eligibility before dispatch and before delivering
   web output. Logout/expiry/revocation suppress pending delivery. Native cancellation
   is reported according to actual transport support, without promising to undo
   work the persona already performed.

Authentication, organizational authority, visual filtering and native conversation
are distinct responsibilities. The absence of a human/organization ACL argument in
`ask` is **not by itself** a reason to rebuild native retrieval. The selected
persona remains the human's existing conversational counterpart under the agreed
PhantomOrg policy. Conversely, do not claim that this interface provides a new
hard record-level isolation guarantee across every native tool and memory read.
Such a stronger guarantee is a separate future requirement, not this plan's scope.

## Ordered delivery milestones

### P0. Reconcile the active design

Publish this plan and mark conflicting documents historical. Inventory reusable,
inactive and live components without deleting anything. No application behavior
or deployment changes belong in this milestone.

Acceptance: one canonical plan, explicit source revisions and no claim of an
already connected native assistant.

### P1. Verify the installed adapter and authenticated handoff

Progress, 2026-10-17: the selected installation's read-only inspection is complete.
See the [authenticated handoff review](P1_AUTHENTICATED_HANDOFF_REVIEW.md).
The installed reader still uses the legacy gate; verified requesting-human context
does not reach that reader through the inspected helper. CLI help compatibility
is confirmed, but identified-link acceptance and native conversation remain
pending. Next: authoritative counterpart mapping and the minimal trusted handoff.

Read the selected installation's actual versions, public command surface, existing
link issuer and channel integration. Document how proven sender context reaches
the reader. The existing shared slash dispatcher was not found to expose a general
PhantomView plugin hook in the reviewed source; do not invent one or infer identity
from model-controlled tool arguments/environment.

Prefer a supported channel integration. If one is absent, scope the smallest
optional generic handoff seam: deliver authenticated channel context, not an
organization/human model inside PhantomBot. Review that seam before implementation
and deployment. It must not require a replacement daemon, competing channel poller,
model-readable issuer credential or a universally trusted bridge identity.

Acceptance: Telegram and PhantomChat demonstrate a verified direct sender to
PhantomOrg mapping and one identified link, including denial/replay cases, without
a second human authentication step. A missing integration remains visibly pending.

### P2. Align PhantomOrg declarations and resource metadata

Use existing organization, role/access, human and compiled-scope declarations.
Resolve authoritative counterpart mappings explicitly where the installed schema
does not express them. Keep any necessary compatible extension in PhantomOrg;
validate it against the installed package, not an old patch base. Preserve existing
categories, exceptions and the independently assigned category-zero human.

Reuse approved source classifications and folder-rule drafts for viewer resources.
Unknown/private sources are not guessed public. Copies, summaries and linked
resources retain applicable restrictions. Approval remains separate from discovery.

Acceptance: synthetic organization/project fixtures and the selected installation
produce consistent human-to-persona access without a duplicate grant database.

### P3. Assemble the standard visual viewer

Generate organization identity, navigation, counts and links from current authorized
data. Keep overview, people, relationships, knowledge/documents, procedures,
findings and installation sections when relevant records exist. A project can
show partners, objectives and tasks instead of invented departments.

Global search covers all information authorized for the session regardless of the
selected menu. Use compact host labels with technical details on demand, one global
language selector, visible active findings and status evidence with timestamps.
Unverified, stale and unavailable are different states, not guessed healthy states.

Acceptance: allowed and denied records behave consistently in cards, graphs,
counts, search and document details; switching sections changes presentation only.

### P4. Connect the existing issuing persona

Implemented foundation: core and inheriting-module navigation select the validated
session issuer even when the host default changes or its observation is unavailable.
Explicit module overrides still require current authorization; denied routes never
fall back to the host default. This does not activate a native transport.
Bind each configured runtime and persona explicitly; no browser-provided command,
filesystem path, native conversation ID or global persona switch is authoritative.

Evaluate the existing public `ask` entry point and already installed transport.
Use stdin for question text and existing native credential resolution and memory.
No new inference service, engine root or copied secret store. Keep provenance and
JEV behavior of the chosen native surface; do not add a browser-accessible trusted
flag or assume a relay inherits the human's trust. `ask` screens untrusted input
and is not identical to a channel's authenticated-principal path; document this
difference rather than silently weakening either path.

Preserve asynchronous status, bounded requests, cancellation/expiry handling and
server-owned retry identifiers using existing reader components. Native holds and
errors must come from supported completion metadata, not phrases generated by a
model. If the selected public transport lacks structured completion/delegation,
record the precise small adapter requirement instead of inventing an API.

Supply only relevant authorized viewer context, such as a selected finding, on
demand. Do not paste an entire organization snapshot into every question. A prompt
helper generates copyable text on explicit request; it never executes remediation.
General native persona conversation and bounded finding analysis must be labelled
accurately; neither creates extra write authority merely by being inside the viewer.

Acceptance: the same eligible issuing persona answers in the web interface using
its existing configuration and memory; changing host defaults cannot redirect it.
Session ownership, revocation and native outcomes are tested end to end. No claim
of a separately sandboxed native knowledge subset is made.

### P5. Add explicit optional module lifecycle

Provide validated operator installation/removal/version checks for declarative
modules. Keep core menus intact and namespace module sections. Modules cannot
install arbitrary scripts, grant permissions or silently alter the core assistant.
An explicit eligible module persona is shown clearly; absence of its route does
not fall back to a more privileged one. UI customization is validated configuration,
not model-generated executable application code.

Acceptance: a synthetic project module adds partner/task views, survives restart,
and can be removed without damaging the core or changing organizational authority.

### P6. Reuse setup and refresh mechanisms

Setup reads the selected PhantomOrg source, verifies compatible formats and imports
available authorized structure, procedures, KB metadata and installation evidence.
Reuse existing collection/manual refresh and scheduled intervals; do not introduce
another scheduler, background model loop or inference-based synchronization service.
Report freshness, exclusions and source changes; never preserve a removed record
through a cached detail link. Refresh the default observation only through the
existing observation mechanism; it never rewrites an identified session's issuer.

Acceptance: new and existing installations produce repeatable setup and refresh
without duplicate records, changed grants or extra persona state.

### P7. Run a reversible single-installation pilot

After P1-P4 are concrete and validated, stage one selected organization. Record
versions, exact owned files, configuration changes, baseline service state and
rollback. Check verified links, each eligible human, category zero, issuer routing,
allowed/denied viewer records, native answer/status behavior and expiry/logout.
Keep other VPS setups and the public website widget outside the target. Remove
obsolete pilot services only after proving the new path replaces their function.

Acceptance: observed end-to-end results and rollback evidence are recorded. Then
package generic installation/module instructions and consider upstream contribution;
never publish live identities, collected private data, keys or transcripts.

## Future requirement F01: organization-wide ingestion ACL

Retain this requirement for later implementation: incoming organizational content,
attachments, imported documents, generated notes and derived material should carry
PhantomOrg-compatible organization/category/scope/provenance metadata. Do not make
PhantomView the owner of a second organization-wide ingestion system. Current
viewer exports still need valid classifications; this plan does not silently
reclassify the native collaborative memory or claim universal ingestion coverage.

## Validation and maintenance

Commit each coherent implementation increment to the private repository. Use
synthetic fixtures and meaningful tests for identity binding, issuer selection,
viewer ACL, module lifecycle, freshness and actual native handoff. Existing tests
for retired experiments preserve history but are not production readiness evidence.
Documentation-only changes require source/link/content review, not fabricated
runtime tests. Keep deployed, locally tested, CI-tested and planned states distinct.

No blanket immunity to upstream updates can be promised. Depend on public formats
and commands, keep a small adapter compatibility check and fail clearly when the
installed surface changes. Standard setup must remain additive: own named files or
marker-delimited sections, never replace a live persona directory or memory system.

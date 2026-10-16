# PhantomView

A read-only visual observatory for Phantomyard organizations. It combines declared
organization structure with bounded filesystem and service observations, preserving
source evidence and distinguishing declarations from operational checks.

See the [scope-aware execution plan](EXECUTION_PLAN.md) for identified access,
resource authorization, organization/project views and persistent personalization.
It also records future requirement F01 for organization-wide ingestion ACL metadata;
that requirement is deferred and does not change current ingestion behavior.
The private [scope and action model](SCOPE_ACCESS.md) defines explicit session
boundaries and separate modification capabilities; it is not enabled on the live reader.

## Install and run

Python 3.11 or later and PyYAML are required. Use `install.sh` / `run.sh` on Linux
or `install.ps1` / `run.cmd` on Windows. The bundled example is synthetic; it never
claims to represent an installed organization.

```sh
python phantomview.py serve --open
python phantomview.py setup --mode existing --org /absolute/org.yaml \
  --personas /absolute/personas --docs /absolute/manifest.yaml \
  --installation /absolute/installation.json --interval 300
python phantomview.py sync
```

The local launcher binds to loopback and uses a session token. Do not expose that
local mode directly to a public interface. The Sources & setup form configures only
the observatory. It does not change persona identities or organization documents.

For separate persona accounts, use `persona_paths` keyed by `organization:persona`.
Use `remote_personas` to declare actors on other machines. A remote declaration does
not inspect that machine. Profiles cannot be reused across selected organizations;
foreign document manifests and conflicting profile mappings are rejected.

## Organization and knowledge views

Views include organization graphs, departments, persona profiles, declared tool
capabilities, registered PhantomDocs documents, exported procedures and changes.
Graph hover and keyboard focus highlight directly connected nodes, arrows and flows.
Conditional escalation cycles are review findings, not confirmed runtime failures.

Profiles show public identifiers declared in the organization: `email`,
`telegram_bot` and `npub`. Email tools show the declared mailbox. Additional tool
accounts can be declared as `tool_accounts: {tool: username}` on an actor. Accounts
are never inferred from unrelated identifiers or extracted from credentials.

Markdown knowledge notes can be searched by title/path and opened in an authenticated
text reader. HTML and instructions in notes are not executed. Credential-named files
are excluded, and common private-key and secret patterns are redacted. This does not
guarantee detecting secrets embedded in arbitrary prose. Notes are bounded to 2 MB;
truncation and source modification time are shown explicitly. Removed notes cannot
be opened through an older identifier once they leave the selected index.

## Installation and dependencies

### Automatic procedure discovery

Setup and every collection automatically rebuild the procedure index from the
selected organization sources, current readable KB copies and registered document
metadata. No separate catalogue needs to be maintained. The existing scheduled
collector updates new, changed and removed sources; the dashboard's read-index
button reads the latest export. Standalone installations can use their configured
sync interval or `python phantomview.py sync`. `auto_procedures: false` explicitly
disables discovery. An optional `procedures_file` remains supported alongside it.

PhantomOrg escalation entries appear as independent conditional rules, preserving
their conditions and declared hop limit. An optional organization `procedures`
list is imported as structured source data. These are collector-supported input
fields, not a claim that a new upstream PhantomOrg schema has been installed.
Procedural document metadata is shown as a reference only; no external document
body or Drive content is fetched.

KB discovery recognizes protocol/procedure/workflow/checklist/pipeline/SOP/playbook/norm
titles and headings. Ordered lists, separate sections and
conditional bullet lists retain their source structure. Code fences and link-only
indexes are excluded. A detected document without structured steps keeps an open-
source link instead of inventing steps. Source ownership is distinct from step
responsibility; missing owners, inputs and outputs are explicitly unspecified.
Discovery does not verify that a procedure was reviewed or executed. It makes no
model calls, executes no instructions and never changes a source document.

Only notes present in the current authorized export and allowed for search are
eligible. Excluded/private, unavailable, truncated, stale-owner and remote-only
sources are not scanned. Discovery is bounded to 8 MB of KB text, 200,000 characters
per note, 150 entries and 40 items per entry; incomplete readings are labelled.
Oversized recognizable notes remain source references without extracting their
steps. Byte-identical complete notes can share cards while retaining up to 100
source-copy links and their owners. Cards are grouped by source to keep the view compact.
Rows have source-derived identifiers and source-note links, so updates appear in
change history and removed notes cannot remain accessible through stale rows.

Run `python -m unittest test_procedures test_phantomview` and
`node test_procedures.cjs` to verify discovery and rendering boundaries.

The single language selector in the top header controls the entire interface:
navigation, filters, dates, statuses, access screens, persona and KB reader controls,
findings/review panels, setup forms and the installation inventory. English is the
source language. The preference is remembered
locally and migrates the earlier installation-only preference. Organization-owned
names, descriptions, protocol conditions and document/KB content retain their source
language. Switching language preserves current filters and the open finding review.

Three views are available:

- **Software:** Phantomyard packages, services, runtimes, libraries, data and external
  services, with presence/version/service evidence.
- **People & tools:** declared persona capabilities and explicit links to software
  and external services.
- **Impact:** reverse traversal of declared `requires`, `reads`, `runs_on` and `uses`
  relations. Optional dependencies and publication outputs are excluded. This is a
  structural dependency view, not a measured outage prediction.

Use the organization filter, evidence filter and search field to narrow the map and
inventory. Selecting a component shows its description, location, version evidence,
maintainer if declared, outgoing/incoming relationships and affected components.
Shared host components carry a shared label inside the selected organization's
scope; other setups and their routes are not inspected.

An explicit version-1 JSON manifest contains `components`, `relations`, optional
`tool_bindings`, and optional `persona_bindings`. See `example-installation.json`.
Each component has an English identifier, organization ID, name, kind, localized
description, optional owner/shared/version declaration, and a bounded probe.

Supported probes are:

- `none`: a declaration only; external connectivity is not inferred.
- `path`: absolute-path presence only; contents and credentials are not read.
- `python`: the collector's current interpreter version.
- `distribution`: installed package metadata in that interpreter. Other virtual
  environments are not inspected, and presence is not a functional integration test.
- `systemd`: `LoadState`, `ActiveState` and `SubState` for an explicitly named unit.
  No service configuration, environment, arguments, logs or secrets are read.

Probes cannot execute arbitrary commands. The manifest accepts at most 150 software
components and 1,000 explicit relations; references and setup boundaries are
validated. All graph relationships remain **declared** even when their endpoints
are independently detected or checked.

The collector refreshes this inventory with the organization sources. Missing
packages/services are observations; malformed or inaccessible sources preserve the
last valid snapshot. Installation observations participate in change history.

## Delegated private access

The AU pilot reuses the installed PhantomBlog NIP-98 access verifier, signing
identity, replay protection and five-minute single-use grants. The existing issuer
is Paco. The added `acceso-phantomview.sh` tool and runbook preserve the original
PhantomBlog access tool. Requests and links belong in the existing private channel.
Installing the tool/runbook is separate from testing the persona chatbot response.

Human read sessions last 30 minutes. Cookies are HttpOnly, SameSite=Strict and Secure
under HTTPS. URL fragments are erased on redemption; logout revokes the session.
The same session protects state and KB endpoints. No browser configuration or
software administration is available in delegated reader mode.

The pilot uses a root collector restricted to explicitly selected AU sources and a
non-root web reader restricted to exported data. Collection is scheduled every five
minutes; private Tailscale HTTPS forwards to the loopback reader. Existing setups,
organization files and PhantomBlog services are preserved.

```sh
python phantomview.py --config /private/collector/config.json sync \
  --export /private/reader/index.json
python phantomview.py serve --port 8789 --reader-index /private/reader/index.json \
  --access-policy /private/reader/access.json \
  --access-module-dir /path/to/installed/phantomblog \
  --public-origin https://private-host.example:8790 --session-seconds 1800
```

The collector exports KB copies beside the index in `kb/`. The reader cannot collect
sources or modify their configuration. Its installation inventory is a fixed export,
not a privileged remote administration API.

## Updates, validation and limits

Data refresh can be manual or scheduled. Software updates are manual in the pilot.
The optional Git updater requires an operator-selected signed release tag, the
expected private repository, a clean checkout and successful tests before activation.
No signed release is currently published. A previous commit is saved for rollback.

```sh
python -m unittest discover -s . -p 'test_*.py'
node --check app.js
node --check installation.js
node --check review.js
node test_review.cjs
node test_i18n.cjs
```

Live Drive permissions, remote persona runtime, complete host inventory and external
service telemetry are not verified by this version. Source presence, package metadata,
service activity and declared relationships must be read as distinct evidence.

## Local PhantomBot diagnostics

`diagnostics.py` collects the exact services and native diagnostic reports for an
explicit list of local personas. It calls the installed PhantomBot executable as each
persona's Unix user with `doctor --persona NAME --no-repair --json`. Repairs are always
disabled. This requires a PhantomBot version that supports those options; an unavailable,
invalid or timed-out report remains partial evidence, never a successful check.

The targets file is operator-maintained and private. For example:

```json
{"targets": [{"org": "example", "persona": "atlas", "user": "pb-atlas", "unit": "phantombot-pb-atlas.service"}]}
```

```sh
python diagnostics.py --targets /private/local-targets.json --executable /absolute/installed/phantombot --output /private/local-diagnostics.json
```

Set `diagnostics_file` in the collector configuration to that output path. A collector
service can run the command as `ExecStartPre` before exporting its snapshot; the AU pilot
uses its existing five-minute collector timer. The web reader receives only the sanitized
snapshot and cannot run diagnostics or repairs. No extra network access is needed.

The export includes only service health, Telegram/PhantomChat health flags, heartbeat/tick
freshness and observation dates. It excludes raw reports, credential fields, identities,
contacts, paths and arbitrary diagnostic details. Native reports remain in memory during
collection. Each native call has an eight-second timeout; each service query has four.
The report file is written atomically with mode 0600.

Persona details show individual results and dates. Reports expire after 15 minutes;
service-only results are partial if the native diagnostic fails. Unconfigured optional
channels are distinguished from failures. Local evidence never verifies a remote persona.
Every persona card, overview operation cell and profile carries a visible status flag:
**Alive**, **Not running**, **Unverified**, or **Check expired**. Alive refers only to a
recently observed active local service. An active service with diagnostic warnings or
incomplete evidence shows **Alive · review** or **Alive · partial** in amber. Profiles
refresh their diagnostic flags with the snapshot, including expiry, while they remain open.
Successful checks confirm the observed service/listeners/timers, not a real message reply,
model inference or effective email/Drive/tool permissions. Changes in observation dates
and timer ages do not create organizational history entries; status changes do.

Run `node test_diagnostics.cjs` along with the Python suite and existing UI tests.


## In-context finding review

The Review control expands an inspection panel below the relationship map. It shows
up to three bounded return routes, source conditions on each edge, inherited wildcard
rules, the declared hop limit, review criteria and a link to the affected persona.
The main map switches to the relevant relationship layer. Closing or toggling the
panel restores the normal overview. The selected finding remains open across data
refreshes; findings no longer in the filtered snapshot are identified explicitly.

The route model expands `*` rules to selected roles while excluding the destination
itself, matching the collector's cycle analysis. Search is bounded to six edges and
2,000 visits. The visualization is an illustration, not a complete protocol validator
or evidence that an actual conversation loop occurred. It does not edit the source,
record a review approval, or resolve a finding. English source labels support
interface localization.

An open review is explicitly marked by an Active review banner above the map, a
highlighted finding row, an expanded Active review control, and an In review label
on the selected role node. These indicate the currently open inspection, not a
resolved finding or a recorded approval. Closing clears all active indicators.


### Compact installation labels

The optional collector configuration `installation_labels` maps selected
`organization:persona` keys to short human labels (maximum 48 characters), for
example `{"example:lead": "Example · VPS", "example:remote": "Example · PC Lead"}`.
The existing installation badge is replaced rather than supplemented. Detection
or declared remote-location evidence remains in its tooltip and persona details.
A label identifies the setup and machine; it does not prove installation or remote
connectivity. IP addresses are not added to overview cards. Foreign persona labels
are rejected. The organization specification and persona profiles are not changed.


### Default persona and PhantomChat

The compact sidebar embeds the official https://chat.phantomyard.ai client in an
isolated frame. Human sign-in belongs to PhantomChat; PhantomView does not read,
import or share chat keys, messages or its own access cookie. The client has its
own language controls. The expand button enlarges the existing frame without
reloading it. The external link provides a full-tab alternative.

Resolve the default in the selected setup's runtime, never an unrelated root
account: `python3 assistant.py --user pb-EXAMPLE --org EXAMPLE --executable
/absolute/path/to/phantombot --output /private/default-persona.json`. Run this
before each collector refresh and set `default_persona_file` to that export.
The resolver invokes `doctor --no-repair --json` without a persona override and
exports only the observed persona, provenance and time. Organization membership
and local location are checked before including its declared public npub.
Evidence expires after fifteen minutes. Multiple account installations must
explicitly choose their coordinating runtime; an organization chart does not
identify this runtime automatically.

The issuer must match the resolved default. Existing signed issuer permissions
are never automatically reassigned: a change displays a configuration warning
and requires an administrator to review the access policy and signing helper.
Use the public contact copy button to add/select the default persona in
PhantomChat. The upstream client currently has no supported npub URL route or
cross-origin embedding API to open that conversation automatically. No chat
messages are sent by PhantomView, and dashboard source data stays read-only.
# Analysis assistant pilot

## Global search and PhantomBot version trigger

The header shows `PhantomBot installed / available` for the configured binary and
the latest official stable release. Set `PHANTOMVIEW_BOT_VERSION_CONFIG` to a
root-owned JSON file containing an absolute `executable` and `shared: true` when
the binary is shared. The authenticated observer executes only `--version`,
checks GitHub's official stable release API hourly (manual checks are throttled
to one per minute), and re-observes the binary every 15 seconds. Unknown or failed
checks never claim the installation is current. This is the on-disk binary
version; running daemons may still need a separately planned restart. The pinned
analysis runtime is separate. The trigger opens release notes and a copyable
official update command for a human administrator to execute in the terminal;
the web process gains no install, restart, shell or sudo capability. Existing
host update schedules are unchanged.

Non-empty dashboard searches use a global results view independent of the
selected section, organization and department. Matching is deterministic,
case/accent/separator insensitive, with one-character approximate matching for
words of at least five characters. Results cover organization/department/role
descriptions, personas and responsibilities, declared public interfaces, tool
names, KB titles and readable KB text, document metadata, procedures, installation
components and findings in the authorized export only. KB search uses the existing
authenticated note reader, caches by note identity and search policy, returns only
bounded excerpts, and flags unavailable, truncated or over-budget results. It
never follows arbitrary source paths or connects to Drive. The KB text budget is
64 MB per authorized index; visible results are capped at 100. Source fields marked `searchable: false`, `confidential: true`, or
`visibility`/`classification` of private/confidential/restricted/secret are
excluded by the collector; KB front matter supports the same exclusions. Numeric document categories are not
assumed to be access levels. Search adds no raw source filesystem, Drive, credential, external document-body
or conversation-history access. It searches only the KB copies already available
through the note reader. This exclusion is not a new ACL:
the existing authenticated export remains the data boundary. JEV remains active
for actual model consultations; deterministic search sends no model requests.

PhantomView can host an analysis-only sidebar and a finding-specific **Prompt
helper**. The UI adapts the AU website widget's message/polling pattern, but uses
the dashboard's existing temporary session instead of a public visitor token or
a second PhantomChat sign-in. Responses are rendered as text, not HTML. Prompts
can be copied or downloaded as plain text.

The server reconstructs finding context from the exported snapshot, verifies the
observed default persona, and sends only bounded evidence and up to four short
follow-up messages. A change of view/finding starts fresh context. Logout clears
the visible transcript. The worker rejects foreign setups, expired requests,
cross-session result reads, and conflicting retries. Limits are ten consultations
per session per hour, forty globally per hour, one active job, four queued jobs,
and a 120-second execution timeout. Backend jobs do not extend dashboard access.

Application instructions stay in the fixed system suffix. The screened user
message is a JSON envelope of the actual question, evidence and bounded previous
turns; it does not mix those with application directives. Question and source
content remain untrusted. A real `screenedHold` completion emits a dedicated
stderr marker; the worker discards other stderr content and reports `held`
instead of a provider failure. It never lowers JEV's threshold or retries a held
message automatically. The runtime manifest must include `screened-hold-marker`.
The evidence includes a short glossary of dashboard labels, so the assistant can
distinguish installation presence, unverified operation, fresh service evidence
and an active review without guessing what the UI means.

`bridge_assistant.cjs` can be mounted as middleware or run as an independent
loopback adapter. This pilot uses the latter; it does not alter PhantomBlog or
claim a new upstream PhantomBridge API. Its service credential stays server-side
and authorizes only `/phantomview-assistant` operations, never arbitrary commands.

The pilot uses a separate root-owned, hash-verified compiled PhantomBot 1.1.425
runtime with `native_assistant_patch.py`. The patch removes unsafe harness
fallbacks, disables tools/MCP and extension/skill/template discovery, disables
history, and retains untrusted-input screening. The main daemon binary and its
normal channels remain unchanged. This is an explicitly pinned private pilot,
not a claim that an upstream integration already exists. The documented engine
API requires its own exclusive isolated root and must not be pointed at a live
daemon's data directory.

`deploy_consultation.py` is an AU-specific deployment example, not a universal
installer. It validates the existing issuer/default match and the pinned binary,
backs up changed source and policy, and creates only dedicated loopback services.
Review and authorize the persona access before activation. No persona credential
is included in the repository. Run `python -m unittest test_consultation
test_assistant test_access_gate` and `node test_review.cjs` before deployment,
then verify real replies and actual native restriction flags on the target host.
The worker keeps home directories read-only except the selected PhantomBot data,
state and that persona's native SDK agent-state directory. The SDK needs to write
its technical state under `~/.local/share/pi-native/personas/<persona>/agent`;
this filesystem permission does not enable model tools or alter JEV screening.

### Session audit and future scoped knowledge

The optional `PHANTOMVIEW_AUDIT_PATH` enables a local SQLite metadata ledger.
Provision its absolute path in a private reader-writable directory outside the
static files, exported index and KB folders. The directory and backups must be
accessible only to the operator and reader account; the model worker must not
have write access. No additional package is required. Invalid storage prevents
startup; failed writes prevent new sessions and assistant submissions. Logout
and revocation still invalidate the session even if their audit write fails.

Each session receives a separate random audit identifier, unrelated to its
cookie, cookie hash, phone number, email or npub. Events record creation, observed
expiry, logout, operator revocation, assistant request IDs and observed job
states. Repeated identical poll events are deduplicated. No prompts, responses,
credentials or link grants are stored. `Ledger.export()` is an operator API;
there is no public audit endpoint. Default retention is 30 days, bounded to
1–90 days when constructing the ledger. Expired rows are removed on writes and
excluded from exports. Retention does not erase operator backups or filesystem
copies; those need their own retention policy. Expiry is recorded on the next
session check, not by a scheduler. A reader restart invalidates in-memory
sessions; it does not reconstruct them from the persistent ledger.

Observed results are not guaranteed worker-completion events: a user who stops
polling may leave the last audit state at queued/running. This first stage is a
diagnostic trail, not a tamper-proof security archive or a full conversation
history. A compromised reader or root can alter it. A separately protected sink
and worker-side terminal events are needed before claiming stronger guarantees.

See [Verified human access: integration status](VERIFIED_CHANNEL_INTEGRATION.md)
for the inspected native channel boundaries, the inactive recipient/session
adapter, a read-only matrix preview, real-signature tests and the remaining
PhantomOrg schema/transport/retrieval work. No extended human access is enabled
by these modules or by the existing dashboard link.
The [private PhantomOrg compatibility patch](PHANTOMORG_HUMAN_ACCESS.md) now
provides the proposed counterpart/project fields with coordinated schema,
typed-model, reference and compiler tests. It is not applied to the live setup;
the unpatched upstream release still does not accept these extensions.

`assistant_scope.py` is a tested, inactive policy primitive for a future
verified-channel integration. Ordinary humans inherit category and project grants
from their explicitly linked persona; category 0 is an independent human grant
defined in PhantomOrg. No duplicate ordinary human ACL is maintained. It requires
explicit non-secret classification, and never infers access from numeric category
order or job titles. The human category-0 exception is described below. It does
not authenticate a sender, load persona memory, grant new knowledge access or
change JEV. The current signer supplies no verified human recipient; an existing
dashboard link therefore cannot establish the human identity required by this
policy. Expanded knowledge must stay disabled until the channel adapter supplies
trusted sender context, explicit operator-approved grants exist, and retrieval
filters resources before model inference. Browser-supplied identity, email From
alone and model-selected shell arguments are not authentication. No new human
login is required if the verified channel context is securely carried forward.

`Scope.from_org()` derives the private policy directly from an organization
source, resolving `actors[].role` through `roles[].access_level` and
`policies.access_levels`, plus `roles[].security_exceptions` and
`actors[].actor_exceptions`. Numeric categories become exact declared labels such
as `category-2`. A missing role or level never implies a level grant; explicitly
declared actor exceptions still apply.
Unknown category labels and duplicate principal IDs reject the policy. The
policy revision changes when effective grants or counterpart bindings change;
the future session adapter must reject stale policy revisions on each request.

The proposed **private extensions** below are not yet upstream PhantomOrg
features. They must be reviewed against its schema before deployment. No live
organization file is changed by this implementation:

```yaml
humans:
  - id: board_member
    counterpart_persona: coordinator
policies:
  phantomview:
    project_grants:
      coordinator: [example-project]
```

Human entries without `counterpart_persona` remain valid organization members
but ordinary humans cannot obtain an identified assistant session. Category 0
is the explicit exception to counterpart eligibility. A counterpart must refer to
an existing actor and must be unique among humans. `reports_to_human` is a
hierarchy relation and is never interpreted as a counterpart binding. Link
eligibility ordinarily requires the authenticated human's exact counterpart as issuer;
neither a caller-selected persona nor a matching job title is sufficient.
Project grants are exact labels, inherited from the counterpart, and do not
implicitly grant any category. A project resource requires both its category
and its project. The reader does not receive raw channel identifiers from this
policy resolver. Existing legacy link issuance remains unchanged until the
verified-channel adapter is implemented and explicitly activated.

Category 0 is PhantomOrg's human "god mode" information grant, independent of a
persona, counterpart relationship or executive job title. The source must declare
`policies.security_categories.category-0`. Its explicit human `owner` takes
precedence and may have no persona counterpart. Owner references resolve by exact
case-insensitive human ID or name, never fuzzy matching. Unknown, empty or
ambiguous explicit owners reject the policy and never trigger a fallback.

Only when `owner` is absent, `Scope.from_org(org, default_persona=...)` resolves
the unique human counterpart of the installation's verified default persona
(Paco in AU). The default must come from trusted installation configuration, not
the browser; no persona name is hardcoded. A missing category-0 declaration,
unverified default, absent counterpart or ambiguous binding rejects the policy.
Removing an explicit owner therefore invokes this documented fallback; it is
not a way to disable category 0. Change the assignment explicitly to transfer it.

The resolved human owner can access all declared organization categories and
projects through a known persona, without inheriting that persona's narrower
information scope. Other humans do not obtain god mode from a counterpart's
actor exception or from role/level entries. A persona's `category-0` entry alone
never grants god mode to a human. Another organization or an undeclared category
remains outside this policy. Verified channel authentication and issuer checks
are still necessary: policy eligibility is not proof of human identity and does
not make an unsigned browser claim valid. This enables
information scope only: it does not add tools, administration or credential
disclosure. Explicit secret-resource exclusions still apply. Ordinary category-4
role exceptions do not imply access to every project.

### Folder classification review drafts

`classification_proposal.py` prepares an offline JSON draft and optional HTML
review table from a metadata-only inventory. An inventory includes the trusted
organization ID, declared `categories`, and `folders` entries containing `actor`,
canonical relative `folder` (under `kb`) and positive `notes` counts. Do not
include note bodies, credentials or human channel identifiers.

```sh
python classification_proposal.py inventory.json --output draft.json --html review.html
```

To align a review with an inert access-matrix preview derived from trusted
PhantomOrg source, add `--access-preview access-preview.json`. The preview must
contain the same organization, `preview_only: true`, `live_access_changed: false`,
the `Scope` policy and its matching `policy_revision`. The report displays source
category meanings, exact persona grants and ordinary human category eligibility
inherited through counterparts. Category 0 owners appear separately as holders
of the independent absolute information privilege, never as a document category.
Category eligibility alone does not establish an authenticated channel, project
access, deployment or permission to obtain a link.

`--confidential-category category-3` can select that existing category for
confidential folder suggestions when the organization wants its narrower access
scope. The default remains `category-2`. These exact labels are references to
existing PhantomOrg categories, not a new hierarchy; their source meanings and
grants are never rewritten. If a selected category is undeclared, affected notes
remain unclassified. Neither category 0 nor project categories can be selected by
this option. All suggestions still require content review before activation.

Every rule is unapproved, nonrecursive and scoped to one actor and exact folder.
Suggestions use folder names only and require content review: they do not prove
classification. Mixed roots, imported documents and unidentified projects remain
unclassified. Category 0 is never suggested as a document category. Missing
organization categories are never invented. Potential secret folders are marked
for separate exclusion review; a numeric category never makes credentials safe.

The assistant does not consume these drafts, and this command cannot activate
permissions. Output files are created exclusively to preserve prior review work.
New notes and changed bodies need separate review: the metadata-only inventory
contains no content hashes and cannot attest to later content. Before activation,
the eventual policy implementation must bind accepted classifications to current
sources, enforce exact project grants and exclusions, invalidate changed content,
and apply authorization before retrieval or model inference. Keep installation
inventories and review artifacts outside the repository; commit only generic code
and synthetic fixtures.

### Scoped knowledge retrieval (inactive)

`scoped_knowledge.retrieve` prepares bounded evidence only for an identified
session and a private approved catalog. It authorizes each resource before any
payload read or search. Category, exact project grants and explicit secret
exclusions use the same `HumanDirectory`/`Scope` policy. Category 0 remains an
independent human privilege and cannot classify a document. Ordinary signed
analysis links cannot invoke this primitive as identified sessions.

`PrivateKBStore` receives a fixed private KB path and trusted current-snapshot
loader. Notes must remain searchable in that snapshot; orphan cached payloads
and collector-excluded notes cannot reappear through classification. The catalog
binds the complete exported JSON payload by SHA-256, including its title, actor,
relative path and body. Payload changes require renewed review. Returned excerpts
remain untrusted evidence for the native screen and do not constitute a complete
corpus search or grant tools to the assistant.

`prepare_review(proposal, snapshot, note_loader)` creates per-resource fingerprints
from current exact-folder suggestions without copying note bodies into the
review artifact. It leaves `status: draft` and `secret: null`; the approved catalog
validator rejects this output even if only its top-level status is changed. An
operator must review confidentiality/exclusions before producing an approved
catalog. A digest is a change detector, not a signature or proof of approval.

`resource_review.py` adds an offline, versioned review workflow over these drafts.
It requires explicit authoritative scopes, binds decisions to exact draft, content
and PhantomOrg revisions, and supports bulk review of current exact-folder members.
Protected revision files preserve provenance and history without selecting a live
catalog. See [versioned resource classification](RESOURCE_REVIEW.md) for the review
contract, storage requirements and activation boundaries.

There is no HTTP route or CLI activation for these primitives. Trusted loaders,
catalog integrity, native channel identity, policy validation at worker dispatch
and response delivery, audit integration and JEV remain activation prerequisites.
The live assistant is still the bounded analysis pilot. See
[integration status](VERIFIED_CHANNEL_INTEGRATION.md) for the remaining work.

The inactive [private verified-channel handoff](TRUSTED_HANDOFF.md) adds a bounded
Linux Unix-socket protocol with kernel peer-account checks before request reads.
It requires separately isolated native channel, reader and model accounts; it
does not authenticate model-supplied channel claims or start a listener on import.
Native channel integration and deployment checks remain prerequisites.


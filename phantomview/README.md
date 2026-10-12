# PhantomView

A read-only visual observatory for Phantomyard organizations. It combines declared
organization structure with bounded filesystem and service observations, preserving
source evidence and distinguishing declarations from operational checks.

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

The single language selector in the top header controls the entire interface:
navigation, filters, dates, statuses, access screens, persona and KB reader controls,
findings/review panels, setup forms and the installation inventory. English is the
source language; Spanish is an explicit UI translation. The preference is remembered
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
Each component has an English identifier, organization ID, name, kind, bilingual
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
record a review approval, or resolve a finding. English source labels have an explicit
Spanish interface translation.

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

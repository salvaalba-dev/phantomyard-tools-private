# Collector publication staging

Status, 2026-10-17: packaged and verified locally; **not deployed**. The AU source
declarations were applied in the earlier source-only change. Webmin subsequently
became unavailable during the next read-only inspection: its terminal remained
blank, and a fresh terminal navigation returned a connection timeout. That probe
did not yield evidence about publication permissions or assistant program paths.
No additional VPS modification is claimed.

## Bounded package

The staged collector package contains the following ten existing Python modules
from the reviewed `cac4a3b1015a3facd6aa42f815e126bb0c5d64fa` code baseline:

| Module | Collector purpose |
| --- | --- |
| `phantomview.py` | Existing `sync` command and export |
| `authority_publication.py` | Opt-in private organization publication |
| `organization_authority.py` | Bounded raw organization parsing and validation |
| `channel_identity.py` | Existing organization/human relationship reader |
| `assistant_scope.py` | Existing category and scope interpretation |
| `view_permissions.py` | Existing view declaration validation |
| `procedures.py` | Existing optional procedure discovery |
| `diagnostics.py` | Existing diagnostic-report sanitization |
| `assistant.py` | Existing default-persona observation attachment |
| `installation.py` | Existing installation observation |

The archive also includes a [per-file SHA-256 manifest](collector-stage-cac4a3b.json). It contains no live
configuration, organization, contacts, KB, credentials, web assets, service unit or
inference worker. The baseline label identifies the reviewed source revision;
per-file hashes identify the actual packaged bytes. This manifest is not a release
signature or a replacement for trusted source review.

The locally staged archive is `phantomview-collector-cac4a3b.zip`, 37,391 bytes,
SHA-256 `32f5d9f7933973f537706606dee15706935a3020a6baa5b311477bfc550b311f`.
It is an operational build artifact, not a new deployed service. The corresponding
source remains versioned in this repository; no second code implementation exists.

## Verification

The archive was extracted to a disposable directory outside the source tree.
A separate Python process ran the packaged `phantomview.py` with synthetic
organization/configuration files, procedure discovery, installation observations,
diagnostic observations and a default-persona observation. Only the packaged local
modules and the existing Python/PyYAML environment were required for this path.

Observed results:

- All ten archived source hashes matched the manifest.
- The packaged `sync --export ... --authority-dir ... --authority-org example`
  command exited zero and produced a matching index/private publication digest.
- A synthetic private human-registry marker was present in the private copy and
  absent from the index.
- Procedure, installation and default-persona observations were retained.
- Malformed source input on the next invocation caused a nonzero exit and replaced
  the private publication with the unavailable marker. The previous index was not
  promoted to authorization authority.

The verification script and machine-readable result are local build artifacts.
No live AU input was used, no service was installed and no native model/channel
request was made. No product-code change was needed. Earlier cross-platform CI
evidence remains separate from this Windows
package smoke test; this is not a Linux deployment or end-to-end assistant test.

## Intended deployment boundary

After the server is reachable, finish the selected publication/assistant inspection
and recheck the source and unit fingerprints. Review a versioned collector-only
directory under the existing AU application path and an update to only the existing
collector unit's executable path/options. Keep the five-minute timer and installed
web application unchanged. Do not install this package over the entire viewer tree:
it deliberately lacks the assets and modules needed to run the web server.

Before switching the collector, capture its current exact unit and source release
for rollback, inspect all configured collection features and verify that this
bounded package covers them. The successful synthetic test does not establish
compatibility with every future configuration option or live observation source.

The separate private authority directory, intended reader account/group and
ten-minute reader lease remain proposed. Exposing the complete organization copy
to the shared reader account requires explicit review of that account boundary.
Do not change permissions, add the authority options or enable a reader merely
because the package smoke test passes. The derived organization copy also needs
its existing ownership and propagation contract checked before it is refreshed.

Knowledge classification approval, verified requesting-human handoff and conversation
with the existing issuing persona remain pending. This package does not authenticate
a human, add channel hooks, start an assistant or change native collaborative memory.

See [source application](SETUP_DECLARATION_PROPOSAL.md#approved-source-only-application),
[publication prerequisites](AU_AUTHORITY_PUBLICATION_READINESS.md) and
[the collaborative plan](COLLABORATIVE_VIEWER_PLAN.md).

## Recovered AU preflight, 2026-10-18

The separate administrative terminal again displayed a root shell and completed
the selected read-only checks. The user-opened terminal belonged to another domain
account; it was observed only and was not used to run commands.

The authoritative source still has the applied SHA-256
`29052cfb4ae57dffb9dc0db6d882e8ce02d247b3ea1eb6702d5e54961566697a`,
three counterpart declarations and the viewer scope policy. The installed collector
still has SHA-256 `5c501b508f842b05afa02242d341af9db4d5a9a32de1f2feb55eacc8b60f5d2c`;
the staged package has not been installed. System Python is 3.12.3. Configured
software auto-update interval is zero and no software tag is selected.

The effective collector command is the existing Python `sync --export` invocation
recorded in the publication prerequisites. Its base unit uses `NoNewPrivileges=true`,
`ProtectSystem=strict` and `ReadWritePaths=/var/lib/phantomview-au`. One existing
drop-in, `assistant.conf`, adds only `ExecStartPre` and references the installed
`assistant.py`. Preserve this helper, the sandbox settings and all existing options.
The viewer and timer were active; the collector was observed during an invocation
with its previous result successful. Serialize any switch with that oneshot.

The reader directory remains root-owned, mode `02750`, group ID 1001. Both the
private authority directory and collector-release parent are absent. The original
projector fingerprint is unchanged. The derived organization file still has the
original source hash: its parent is `root:phantomdocs` mode `0750`, and the file is
`root:phantomdocs` mode `0640`. Do not copy it to the reader or change that group's
permissions as a substitute for the reviewed private publication.

The existing analysis worker runs as `pb-paco`, while its bridge runs as `aunited`.
This is evidence about current service accounts, not a native conversation test or
an isolated browser-session boundary. No raw environment or credentials were read.

The [proposed collector drop-in](au-collector-publication.conf.example)
now provides the exact command for review. It would be installed as a new dedicated
`private-authority.conf` drop-in, preserving `assistant.conf`. Only the collector
would use `/opt/phantomview-au/collector-releases/cac4a3b`; the installed viewer's
program and assets would remain unchanged. The existing timer would be paused only
for the serialized switch, then resumed at its existing cadence. No new unit,
listener, signer or credential is proposed.

The access decision remains explicit: the new authority directory would be
`root:aunited` mode `02750`, with generated files `0640`. The complete organization
document includes human identity and policy metadata. Every process with the same
reader account or applicable group access could read it; per-human browser ACL does
not isolate processes sharing that account. Creating this access requires approval
at the point of activation. This preflight made no permission or deployment change.

Approval of that collector-only publication would not activate the identified
reader or assistant, approve KB candidates, propagate the separate derived copy,
grant projects/actions or select an active reader lease. The proposed 600-second
lease remains for the later identified-reader configuration. After an approved
switch, verify private ownership/modes, exact source/index binding, excluded private
metadata, successful collection and preserved viewer/timer state before proceeding.

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

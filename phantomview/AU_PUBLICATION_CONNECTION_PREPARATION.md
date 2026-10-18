# AU publication and native connection preparation

Status on 2026-10-18: **prepared and verified; live cutover not performed**.
The existing reader, Paco daemon, collector and HTTPS forwarding remain active
with their prior configuration. Whole-daemon trust remains the agreed boundary.

## Detached publication rehearsal

The current selected organization and collector index reconstructed the exact
reviewed draft. The existing approval library reproduced the confirmed approval
revision before the publication rehearsal.

The existing publisher ran in
`/var/lib/phantomview-au/publication-preflight-20261018`, a separate root-only
directory. This is not the configured live projection path. It staged the 57
approved metadata records and its own detached generation pointer. The private
record loader returned bytes, which the rehearsal decoded and checked against
both the exact approved payload hashes and reconstructed records.

All 57 payloads matched. A second publication with the stale empty-pointer lease
was rejected without changing the staged pointer. Loading against a synthetic
changed source was rejected. Root ownership and absence of group/other access
were checked throughout the rehearsal tree. The selected source/index remained
stable, and the known service states/PIDs were unchanged.

The live path `/var/lib/phantomview-au/projection/active.json` remains absent.
No reader access, human grant, live projection or native listener was activated.
The detached rehearsal and its root-only receipt are retained for diagnosis.

## Manual private native artifact build

The [operator build workflow](../.github/workflows/phantomview-native-build.yml)
adds a manual build option without a deployment service. It accepts reviewed
non-secret native host JSON on private main only. Supply deployment coordinates
only: never credentials, human contacts, tokens, transcripts or organization data.
Workflow inputs can be visible to repository collaborators in Actions logs.

The JSON goes through an environment variable and strict existing validation,
never shell interpolation. All actions are pinned by full SHA. The build uses
the existing reviewed PhantomBot source `5af27060327ee8c53fe730dd8b98b6b305c62add`,
Bun `1.3.11`, the unchanged native lockfile and the existing real-signature
verifier baseline. Neither referenced repository is modified.

The workflow runs the existing preparation/refusal tests, authenticated-channel
and startup regressions, persona conversation tests, private controls and real
signer/reader tests before producing a Linux x64 baseline binary. It stamps a
traceable `1.1.433-phantomview.<helper-revision>` version, rebuilds the original
embedded editor extension at base version `1.1.433`, and executes the compiled
binary's version command on the disposable runner.

Only the binary and provenance receipt enter the one-day private Actions
artifact. The receipt binds helper/native revisions, compiler version, target,
canonical route hash and binary hash. It contains no raw routes or credentials.
The workflow has no VPS credential, SSH command, deployment step or write token
for either referenced repository.

## Verified AU artifact

[Build run 39165837083](https://github.com/salvaalba-dev/phantomyard-tools-private/actions/runs/39165837083)
passed using the two reviewed Paco routes: Telegram and PhantomChat.
The downloaded archive was retained in the private operator workspace and
independently checked:

- Helper revision: `b2a023b1fee07fedf2fdc336e523ecd73c9bf181`.
- Native version: `1.1.433-phantomview.b2a023b`.
- Archive SHA-256: `442f61d7a8ddc83c4749c28e9eae6e806bc0cd2dfa6fd120744acbc9ae3772d3`.
- Binary SHA-256: `c9897ed4209ed8b4d28a6e972028ec13909fca72610e44c73e4cf83bdd64b856`.
- Binary length: 117809596 bytes.
- Canonical route SHA-256: `702c62278a3a93f99a79e4f32ccf5f2ec26b416e470b8512bccf62bde570f7aa`.

The archive contained exactly the binary and receipt. Its binary digest, Linux
ELF x86-64 header, base/helper revisions, version evidence and exact local route
binding all matched. It has not been installed or run on AU. The earlier
development-labeled artifact from run 39165355942 is superseded and must not be
installed. No existing native executable was replaced.

## Concrete AU cutover inputs

The private prepared reader and native route documents still match, with two
native channels for one issuer. Inspection found and corrected a port mismatch
in the earlier proposal: HTTPS port 8790 currently proxies to
`http://127.0.0.1:8789`. The revised reader proposal uses loopback port 8789.
The HTTPS origin and existing Tailscale configuration require no change.

The prepared native override preserves the actual `phantombot run` argument
shape and all existing unrelated drop-ins, changing only the executable path
and adding the proposed service supplementary IPC group. The prepared reader
override selects the staged launcher/private runtime, adds the same group and
permits writes only to its socket and private audit directories in addition to
the existing unit allowances. Existing hardening remains in place.

The proposed group is `phantomview-au-ipc`, with observed available GID 1890.
Availability is not a reservation and must be checked immediately before use.
Use service `SupplementaryGroups`, not global account membership changes.
Separate reader-owned and daemon-owned socket parents use mode 0750; sockets
use 0660. A standard tmpfiles declaration can recreate the AU-only parents
after reboot without adding a resident service.

The final projection proposal contains only category-1/category-3 counts 14/43,
with root ownership, the existing reader group, directories 02750 and files
0640. The private audit directory is reader-owned 0700 with database 0600.
Sixty-five document metadata entries and all KB bodies remain excluded.
No organizational source, counterpart, project category, credential or memory
change is proposed. No additional issuer or setup is enabled by this package.

Before any live switch, revalidate current sources, unit hashes, artifact hashes,
publication lease and account/group coordinates; capture private rollback copies.
Apply only the reviewed AU files after explicit operator approval. Start the
compatible daemon, verify its persona/socket, run reader preflight as its real
service account and start the identified reader only if that passes. Real
verified-channel issuance and allowed/denied UI/assistant tests remain required.
These checks have not yet been performed on the proposed live connection.

Rollback must restore only the recorded AU executable/unit selections, preserve
the existing HTTPS target and collector, and return staged projection access to
root-only if abandoning the cutover. Keep existing workers, credentials and
persona memory intact until the new path is proven. A stock PhantomBot update
does not preserve the private hook; use the documented source review/rebuild
before a future update rather than an update blocker or compatibility claim.

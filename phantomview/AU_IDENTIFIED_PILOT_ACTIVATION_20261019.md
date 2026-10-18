# AU identified reader pilot activation

Status on 2026-10-19: **services active; real identified session and persona response verified**.

The operator explicitly authorized installation and activation of the AU-only
pilot, publication of the 57 previously approved metadata records, local
communication between the existing reader and Paco services, and rollback if
checks failed. No additional resident service was introduced.

## Installed and selected releases

- Reader source: `94dae2d`, previously staged and verified.
- Private Python runtime: `cp312-20261018`.
- Native helper revision: `b2a023b1fee07fedf2fdc336e523ecd73c9bf181`.
- Reviewed native source: `5af27060327ee8c53fe730dd8b98b6b305c62add`.
- Served native version: `1.1.433-phantomview.b2a023b`.
- Native binary SHA-256: `c9897ed4209ed8b4d28a6e972028ec13909fca72610e44c73e4cf83bdd64b856`.

The operator transferred a compressed copy of the previously verified Actions
artifact. Its two extracted payloads were independently compared to the original
archive before transfer. The transport archive SHA-256 was
`dc61d4a96638fba3a1a9b81e51e15e333fffe1ca265115e224c3ff189ef2d5b5`.
The VPS verified that digest, the exact member list, the build receipt, binary
digest, ELF architecture and binary length. The native version command passed
under the actual Paco account before selecting the executable.

## Publication and local permissions

The current raw source, published authority, reconstructed full draft and approved
revision were checked again immediately before publication. All 57 record payload
hashes matched: 14 category-1 and 43 category-3 records. The approval revision is
`fbcc36748f39b8df1dfd3f0dc0f92acb1592a25570fcd70deeae7ceb058613d1`.
Sixty-five document metadata entries and every KB body remain excluded. No
organizational source, counterpart, category grant or project grant was edited.

The projection uses root ownership and the existing reader group, directory mode
02750 and file mode 0640. The dedicated IPC group is applied only through the two
service configurations; account-wide group membership is unchanged. Separate
socket parents reject group writes. Both live sockets were checked for their
respective account owner, the reviewed group and mode 0660. The metadata audit
directory is reader-owned mode 0700 and its database mode 0600; it does not record
conversation transcripts.

The reader launch file is installed at
`/etc/phantomview-au-reader/reader.json`, inside its own root-owned, reader-group
0750 directory. Existing `/etc/phantomview-au` permissions remain unchanged.

## Executed recovery and corrected launch

The first reader preflight failed because the earlier proposed configuration
parent was root-only. The stored rollback procedure restored both prior service
selections and returned the projection to root-only access. This was an executed
recovery, not merely a proposed rollback. No unidentified viewer was started.

The corrected attempt used the dedicated configuration directory above. It
revalidated the same source and publication, verified all payloads again, and
passed `reader_launch.py --check` under the actual reader UID with the exact
service supplementary groups. The result reported `assistant_enabled: true`.
The existing reader was restarted only after that check passed.

A baseline fingerprint transcription error was also corrected by inspecting the
actual unchanged reader unit and its protected backup before provisioning. An
initial deployment-script syntax refusal occurred before execution and made no
live changes. These preparation issues did not weaken any runtime validation.

Private backup trees for both attempts retain original unit files, fingerprints,
introduced-file fingerprints and recovery scripts. The original native binary,
credentials and persona memory remain available. Operational backups and
installation-specific scripts are outside the repository.

## Verified live checks

- Both existing services report active/running and the native executable resolves
  to the reviewed versioned installation.
- Both local socket ownership/group/mode checks pass.
- The loopback root and access-info endpoint return HTTP 200; access-info reports
  an identified scoped reader.
- Without a session, state and assistant-info return HTTP 401.
- Legacy configuration and snapshot endpoints return HTTP 403.
- The audit database permissions pass.
- The unchanged HTTPS address serves the scoped workspace, with information and
  assistant unavailable until an identified session is established.

HTTPS port 8790 still forwards to loopback port 8789. Tailscale, the existing
collector cadence, public widget, other setups and additional issuers were not
changed. Whole-daemon trust remains the agreed boundary; this is not a claim of
model/tool isolation inside the daemon.

## Boot ordering and recovery configuration

The reader override orders startup after the existing Paco service and sets
`RestartSec=10s`, preserving its existing `Restart=on-failure`. The former
100-millisecond retry could exhaust the five-attempt startup limit before the
native socket was ready. The effective ordering and interval were checked with
`systemctl show` after a daemon reload; the reader PID remained unchanged.
This configuration was verified without rebooting the VPS.

The introduced-file recovery manifest was updated to bind this exact override,
while the preceding override and manifest were retained privately. The existing
root-only configuration directory remains mode 0700.

## Verified human acceptance

The human requested and opened a fresh link through their existing persona
conversation. The browser established an identified session showing AQUAPONICS
UNITED ngo and Paco as the assistant. The overview showed 33 visible records and
24 connections: eight personas, eight roles, four humans, seven departments, one
organization and five findings. This matches the 57 approved records including
relationship records. No operator impersonation shortcut was used.

A brief informational question completed through Paco's existing native
conversation. The browser displayed the native reply, and the metadata-only
audit recorded one created session and one completed assistant request. Prompt
and response text are not included in this report. A native reply remains persona
knowledge, not a guarantee that every claim matches the displayed projection.

A global search initiated from Departments returned matching role and human
records outside that section. The role detail opened successfully and its close
control worked. Reloading preserved the identified session.

## Supplemental branding asset

Visual verification found that the operator-assembled reader package omitted
`logo.png`. The protected existing AU asset was byte-identical to the repository
asset, Git blob `ae7c3ffe7aa21d2b607a861c25118f1928a0b276`, SHA-256
`9feedd5c984dddd53879fcb62068286e0431fa1c60445123d04ab56ff54dec01`.
The 190551-byte PNG was installed exclusively with root ownership and mode 0644,
alongside a supplemental branding manifest. Every original release-manifest file
was verified unchanged. The static endpoint returned HTTP 200 with the exact
digest, and the browser displayed the logo after reload without a service restart.
Future reader packages must include this tracked static asset.

## Remaining acceptance limits

This verifies one real human session through Paco; it does not establish both
channel variants independently or activate other issuers. Other counterparts,
strict project-only access and document/KB classification remain separate work.
The active human session was preserved rather than logging it out or waiting
for its full expiry during this check. Logout, expiry and denied-scope behavior
retain automated coverage, but were not all repeated through a real browser
session during this deployment. No reboot was performed.

A stock PhantomBot update still requires source review and rebuilding the optional
private hook. No update blocker or permanent compatibility guarantee was added.

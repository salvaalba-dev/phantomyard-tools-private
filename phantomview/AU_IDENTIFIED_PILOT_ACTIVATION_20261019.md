# AU identified reader pilot activation

Status on 2026-10-19: **services active; real verified-channel acceptance pending**.

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

## Remaining acceptance checks

The human must request `/phantomview` from Paco in their existing private Telegram
or PhantomChat conversation and open the resulting temporary link. Real channel
authentication, direct delivery, resolved human scope, visible records, search,
assistant response, logout and expiration still require verification. No human
identity was fabricated, and no live link was generated through an operator
impersonation shortcut. Service startup alone does not establish these outcomes.

A stock PhantomBot update still requires source review and rebuilding the optional
private hook. No update blocker or permanent compatibility guarantee was added.

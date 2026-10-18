# AU private authority publication readiness

## Status

Current status, 2026-10-18: **collector-side private publication is deployed and
verified**, following explicit approval of the shared reader account access.
The identified web reader and native assistant remain unactivated. See
[the deployment evidence](#approved-publication-deployment-2026-10-18).

Initial observation, 2026-10-17: read-only verification confirmed that the existing selected-source
collector can provide the publication cadence. No new scheduler or resident service
is needed. Publication is **not deployed** and identified access is **not ready for
activation**. The initial inspection changed no source declarations, permissions,
units or running code. The subsequent approved source-only update is recorded in
[the declaration application report](SETUP_DECLARATION_PROPOSAL.md#approved-source-only-application):
counterpart bindings, independent owner and organization-only scope declarations
are now present in the selected source. Private publication is still absent, and
knowledge classifications remain unapproved. The derived organization copy has
not been propagated by that change.

This report records operational paths and modes only. It contains no organization
document, human identifiers, credentials, note bodies or private setup artifact.

## Observed deployment

| Item | Observed value |
| --- | --- |
| Collector | `phantomview-au-collect.service`, `Type=oneshot` |
| Producer | Empty system-unit `User`/`Group`: system manager default root |
| Last result | `Result=success`, `ExecMainStatus=0` |
| Timer | `phantomview-au-collect.timer`, active/waiting |
| Cadence | `OnBootSec=1min`, `OnUnitActiveSec=5min` |
| Program | `/usr/bin/python3 /opt/phantomview-au/phantomview.py` |
| Configuration | `/var/lib/phantomview-au/collector/config.json` |
| Current operation | `sync --export /var/lib/phantomview-au/reader/index.json` |
| Selected organization source | `/root/proyeccion/org-live.yaml`, exactly one configured source |
| Authority configuration | No authority option in the inspected collector configuration |
| Proposed publication directory | `/var/lib/phantomview-au/authority`, currently absent |

Selected filesystem checks used `lstat`; none of these paths was a symbolic link.

| Path | Owner:group | Mode |
| --- | --- | --- |
| `/`, `/var`, `/var/lib` | `root:root` | `0755` |
| `/var/lib/phantomview-au` | `root:aunited` | `0750` |
| `/var/lib/phantomview-au/collector` | `root:root` | `0700` |
| `/var/lib/phantomview-au/reader` | `root:aunited` | `02750` |
| `/var/lib/phantomview-au/reader/index.json` | `root:aunited` | `0640` |

The existing reader account is `aunited`; the prior source-access probe confirmed
that it cannot read either original or published organization source. The selected
parent chain permits traversal without granting group/other write access.

The `aunited` account is not an isolated assistant boundary: other processes using
that account can read files granted to it. Reusing this group would expose the
complete private organization copy to those processes, not just to a browser
session. Viewer ACL filtering would still occur in the backend; these filesystem
permissions do not enforce per-human categories. No isolation claim follows from
the current directory modes.

## Proposed bounded change, not an activation instruction

1. Recheck the applied source declarations against their recorded fingerprints and
   finish approved content classifications. Counterpart bindings, organization-only
   viewer scopes and the independent category-zero owner reference have been applied
   in the source-only follow-up. Do not infer project grants or approve draft content
   as a side effect of publishing authority.
2. Review the complete release diff and capture the installed files and exact unit
   contents for rollback. Deploy the compatible collector modules as one reviewed
   release. The tested local implementation is not the installed VPS version.
3. After approving the intended account exposure, create only
   `/var/lib/phantomview-au/authority`, owned `root:aunited`, mode `02750`. Keep it
   separate from the reader index and its `kb` tree. Generated authority files use
   `0640` before atomic replacement. Do not widen `/root` access.
4. Extend only the existing collector invocation with
   `--authority-dir /var/lib/phantomview-au/authority --authority-org aquaponics-united`.
   Preserve the current executable, configuration, export target and five-minute
   timer. Serialize the initial collection with the existing systemd oneshot;
   avoid a simultaneous manual CLI export.
5. Configure the identified reader explicitly with that publication directory,
   existing index, organization ID and original source binding label. Propose
   `max_age=600` seconds for the observed 300-second cadence. This is a bounded
   freshness choice, not instant revocation: a stopped collector leaves the last
   valid publication usable until its ten-minute lease expires. A delayed collection
   can deny access after expiry. Do not lengthen the lease automatically on failure.
6. Before switching any live reader, verify producer ownership, reader-only access,
   metadata/index coherence, renewal, failure invalidation and expiry. Then complete
   verified channel issuance and the persona conversation integration separately.
   Publishing the copy alone neither switches the legacy viewer nor activates the
   identified assistant.

The complete copy includes identity and access metadata. It must never become an
HTTP resource, public export, repository fixture or browser payload. Approval of
its reader account is distinct from approval of category grants in PhantomOrg.

Rollback must restore the captured collector invocation and compatible installed
release, retain the original timer and source, and keep the identified reader
disabled. Do not silently fall back from identified access to the legacy viewer.
Handle any generated private publication as private operational data; do not
commit it or rely on deletion as the access-revocation mechanism.

## Evidence and remaining work

Read-only commands inspected the exact AU-prefixed units/timer, selected unit
files, `systemctl show` result/account fields, selected configuration keys and the
listed filesystem paths. No environment files, access-token file, unrelated setup,
KB body or native credential store was read. No runtime test of a deployed private
publication was performed because that publication does not yet exist.

The code's Linux/Windows and signed-gate checks are described in
[publication design](AUTHORITY_PUBLICATION.md). They establish component behavior,
not live deployment readiness. Required next inputs are approved content reviews,
the accepted account boundary and an identified-reader/native-handoff deployment
plan with end-to-end evidence. Keep those separate from the applied source declarations.

## Approved publication deployment, 2026-10-18

The approved archive was uploaded only to the AU application directory and its
SHA-256 matched `32f5d9f7933973f537706606dee15706935a3020a6baa5b311477bfc550b311f`.
All ten module hashes and Python syntax were verified before installation under
`/opt/phantomview-au/collector-releases/cac4a3b`. The installed web program and assets
were not overwritten.

A protected backup at
`/var/lib/phantomview-au/collector-publication-backup-20261018` contains the original
base unit, existing helper drop-in, collector configuration, index and collector
snapshot, with recorded original metadata/hashes. The directory is root-only
`0700`; saved files and deployment/verification receipts are `0600`. No private
backup, configuration, index or organization document is committed.

The existing timer was briefly paused for the serialized switch. A new dedicated
`/etc/systemd/system/phantomview-au-collect.service.d/private-authority.conf` replaces
only the collector's `ExecStart` with the reviewed versioned command and authority
options. The base unit and existing `assistant.conf` remain unchanged. Effective
argument verification passed; `NoNewPrivileges` and `ProtectSystem=strict` remain
enabled. The timer was resumed without changing its five-minute interval.

The new authority directory is `/var/lib/phantomview-au/authority`, owned
`root:aunited`, mode `02750`. Generated `organization.json` and the reader index are
root-owned, group-readable `0640` with the same intended reader group. This access
was explicitly approved for the shared account; it is not isolation between
processes that use that account.

| Live verification | Result |
| --- | --- |
| First collection through the existing service | Successful, exit status zero |
| Source revision | Matches the approved source declarations |
| Private publication and reader index | Matching snapshot digest |
| Raw human registry in the presentation index | Human rows remain limited to ID, organization, name and role |
| Private policy/publication fields in the index | Absent in recursive key checks |
| Load with `PublishedAuthority` as `aunited` | Passed against actual private files |
| Expired authority at a simulated 600-second boundary | Denied by the reader probe |
| Second collection through the same service | Successful; publication timestamp advanced, organization revision unchanged |
| Existing viewer | Active, same PID, installed entrypoint hash unchanged |
| Existing HTTPS viewer endpoint | Responded with its temporary-link sign-in screen; no authenticated or identified browsing session was exercised |
| Existing timer and default-persona helper | Active five-minute timer; helper hash unchanged |
| Observed exported inventory | 8 actors, 253 note metadata entries, 150 procedures |

The ten-minute lease was used **only by the verification probe**. No identified
HTTP reader has been configured with it; do not describe it as a newly active
browser-session policy. No malformed live source was injected. Failure invalidation
was tested using the earlier synthetic package smoke test, not by disrupting AU.
The note count includes existing exclusions and is not classification approval.

The separate `/opt/phantomdocs/org.yaml` copy was not propagated. The collector
reads the authoritative original directly; its private authority now follows that
same source. Verified requesting-human handoff, identified visual filtering,
knowledge approval and conversation with the existing issuing persona remain
pending. The existing analysis worker/bridge were not restarted or replaced.

### Recoverable rollback boundary

Pause the existing timer and wait for its oneshot to finish. Verify the current
dedicated drop-in against the saved switch receipt, then move only that drop-in to
a protected disabled backup path; do not remove `assistant.conf` or replace the base
unit. Reload systemd, verify the original effective command from the backup record
and resume the original timer. Keep the staged release and private files available
for diagnosis. Do not overwrite an index changed since the capture without a
separate consistency review. No rollback was executed or presented as tested.

If an identified reader is activated later, review its revocation and authority
availability before rolling back publication. Never silently replace identified
access with legacy unidentified access. The current source declarations and native
persona memories are outside this collector-only rollback.

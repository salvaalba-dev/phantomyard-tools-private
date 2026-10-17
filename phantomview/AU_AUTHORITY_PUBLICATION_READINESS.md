# AU private authority publication readiness

## Status

Read-only verification on 2026-10-17 confirms that the existing selected-source
collector can provide the publication cadence. No new scheduler or resident service
is needed. Publication is **not deployed** and identified access is **not ready for
activation**. No source declarations, permissions, units or running code were changed.

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

1. Finish and validate the detached PhantomOrg declarations, counterpart bindings,
   explicit viewer scopes, category-zero owner and approved content classifications.
   Do not publish an inferred grant matrix or the current incomplete source.
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
not live deployment readiness. Required next inputs are the reviewed source grants,
the accepted account boundary and an identified-reader/native-handoff deployment
plan with end-to-end evidence.

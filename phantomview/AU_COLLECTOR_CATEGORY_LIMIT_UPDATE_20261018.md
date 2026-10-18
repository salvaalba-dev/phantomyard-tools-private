# AU collector category-limit compatibility update, 2026-10-18

Status: **collector compatibility deployed and verified**. Human-specific access,
the identified reader and native conversation are not activated by this update.

## Exact change

The existing AU collector now runs the separate `collector-releases/a54f45c`
release. Only `assistant_scope.py` changes from the deployed `cac4a3b` package;
the other nine Python modules remain byte-identical. The policy module comes
from private main `a54f45cdd7318c01af4ae36c9c52a64cbe008ebf`.
Per-file hashes are recorded in [the release manifest](collector-stage-a54f45c.json).

Code-only archive SHA-256:
`9c1415beba7ed73651bfbe9d65b6e20b9dc251c1348c987769024e56967b65af`.
The upload, all ten module hashes and syntax were checked before staging.
No organization records, contacts, note bodies, credentials or private backups
are included in this archive or committed in this review.

The only active configuration change is the release-directory substitution in
the existing collector's `private-authority.conf` drop-in. The five-minute timer
was paused for serialization and resumed after collection. The source, current
grants, base service, helper, web application and native runtime were preserved.
No additional service, inference worker, account or dependency was introduced.
`NoNewPrivileges=yes` and `ProtectSystem=strict` were verified after the switch.

## Verification

| Check | Result |
|---|---|
| Isolated packaged CLI collection and failure invalidation | Passed with synthetic inputs |
| Synthetic human-category limit retained in private publication | Passed |
| Private category-limit metadata excluded from presentation index | Passed |
| Staged consumer against detached in-memory AU project proposal | Nine access checks passed; write access denied |
| Native persona categories in that proposal | Preserved |
| Collection through the existing AU service | Success; exit status zero |
| Fresh private publication versus source and index | Source equality and snapshot digest binding passed |
| Current authority revision and source fingerprint | Unchanged |
| Reader-account load of the private publication | Passed as the actual reader account |
| Existing web reader, assistant worker and selected native daemon | Active; same process IDs before and after switch |
| Existing installed web entry point | Same SHA-256 |
| Collector timer | Resumed and active |

The 600-second lease used by the reader-account probe was a verification argument,
not a newly configured live session policy. The project proposal was evaluated
in memory only; it was not saved as the authoritative source or published.

## Recovery

The root-only private backup directory
`/var/lib/phantomview-au/collector-category-limit-backup-20261018` retains the
original drop-in, proposed replacement and staging/verification/cutover receipts.
The previous release remains installed. Files in the backup use mode `0600` and
the directory uses `0700`.

Rollback must first compare the current drop-in with the recorded replacement
hash. Pause the selected timer, wait for any running collection, restore only the
saved drop-in, reload systemd, collect through the previous release and resume
the timer. Do not overwrite a subsequent operator edit or restore stale organization
data, indexes or native memory. The switch had guarded rollback if collection or
verification failed; no rollback was needed.

## Remaining activation boundary

The deployed web entry point still uses the legacy reader. Collector recognition
of a policy field does not authorize a human session. The new reader and native
handoff still require their reviewed deployment inputs and an approved projection.

The current identified-reader launcher supports one fixed issuing persona per
instance. Serving project links from another persona on the same viewer requires
an explicit multi-issuer routing extension; do not route that human through the
default issuer or introduce another service as an implicit workaround.

The custom organization projector remains in place. Its existing escalation
extension is preserved, rather than stripped to satisfy the standard compiler.
The independent compiler overlay remains a tested private compatibility proposal;
no second organization engine was installed on AU.

The detached project access candidate still requires controlled activation.
Unclassified notes remain unapproved, and native conversation remains unavailable
for a human with an explicit category limit because native memory/tools do not
enforce that human-specific restriction.

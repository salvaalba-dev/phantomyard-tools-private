# AU organization tree viewer update — 2026-10-19

## Active selection

The AU viewer is active at reader release
`/opt/phantomview-au/reader-releases/ui-677e8f1`, based on the preserved
`94dae2d` installation. Its 16 changed runtime files match the private Git
sources at `677e8f118e4f24d008de1f4883634707e40f6e12`. Unchanged runtime
files and the installed branding asset were preserved. The release manifest
records the baseline and complete resulting file hashes.

The package SHA-256 is
`202982aa1115cff3716a94b33f70405e9185de9d55d8b8cdccdc8f482b7ca072`.
Only `phantomview-au.service` was restarted. Its new
`95-organization-tree-ui.conf` selects the versioned reader with the same
Python runtime, protected launch configuration and existing HTTPS route.

The deployed interface includes persona terminology, linked overview counts,
and an organization tree whose levels follow declared reporting relationships.
Persona, role, counterpart and department links open current authorized records.
Workflow highlighting is separate from reporting placement. No tab-return
behavior change is included in this update.

## Projection change

The original 57 approved records retain their payloads and classifications.
The next reviewed publication adds only 19 declared relationships between
already-approved endpoints:

- Eight role-to-persona assignments.
- Eight role-to-department memberships.
- Three human-to-persona counterpart links.

All additions use category 3 and the existing organization scope. No human
grant, category assignment, source organization document or issuer configuration
was changed. No additional documents or knowledge bodies were published.

The resulting publication contains 76 records: 33 nodes and 43 relationships.
Its revision is
`6b4e2681ed94fb5d326847489b801106514accf2d11e56921558151882d1513b`,
extending
`fbcc36748f39b8df1dfd3f0dc0f92acb1592a25570fcd70deeae7ceb058613d1`.
The optional adapter mode is bound into approval and source-revalidation hashes.

## Deployment evidence

The staged archive, Git blobs and resulting installed file hashes were checked
before activation. Source-bound approval was recomputed before publication.
The initial staging preflight correctly refused the active reader's occupied
socket. A separate unused socket path was used for non-disruptive staging only.
After stopping the viewer, its real unchanged configuration passed the normal
preflight before restart; socket checks were not weakened.

Verified after startup:

- The root and access-info endpoint return HTTP 200.
- State and assistant-info return HTTP 401 without a session.
- The legacy configuration endpoint remains HTTP 403.
- Served JavaScript and CSS match the installed release hashes.
- The published catalog revalidates against current selected sources.
- The reader socket retains its configured UID/GID and mode 0660.
- Paco's PID is unchanged and its existing binary retains SHA-256
  `c9897ed4209ed8b4d28a6e972028ec13909fca72610e44c73e4cf83bdd64b856`.
- The host reports glibc 2.39. No native binary update was installed.

The protected backup and deployment receipt are at
`/var/lib/phantomview-au/ui-update-backup-20261019-677e8f1`.
The prior reader, projection generation and unit selection remain available for
rollback. Installation-specific scripts, credentials and source data stay on the
host and are not included in this report.

A real human session through the normal persona-issued link was verified after
the restart. All six overview banners opened their corresponding sections.
The live tree showed eight personas, eight roles, four humans, seven departments,
one organization and five findings. Reporting levels placed the CEO below the
organization, with the declared subordinate roles at their respective levels.
The three published counterpart links appeared; missing counterparts were not
inferred. Department, persona and human links opened the correct current records,
and the close button returned to the tree.

Keyboard focus on the training branch highlighted four cards and four edges,
including one workflow edge, while unrelated cards dimmed. Physical mouseover
was not exercised; mouseenter and focusin use the same highlighting function.
The authenticated overview displayed Paco as its native assistant. No assistant
message was submitted. No human identity was simulated. The protected host
receipt now records these checks as completed; no services were restarted during
this verification.

## Validation

- `python -m unittest discover -s phantomview -p 'test_*.py'`:
  706 local tests passed with 41 platform skips before the final clock-fingerprint
  regression was added. A prior local run encountered Windows error 10053 in an
  unchanged HTTP test; the complete rerun passed.
- Final focused tests: 16 source-adapter tests and 13 projection-review tests pass.
- All 12 JavaScript check files pass; tree coverage includes reporting levels,
  explicit visible joins, missing assignments, cycles, multiple managers and bounds.
- Python compileall, JavaScript syntax checks and targeted Python lint pass.
- CI for code commit `677e8f1` passes all four Linux/Windows Python 3.11/3.12 jobs.
  Linux Python 3.12 runs 707 tests successfully under both umask 022 and 002.
- Compatibility and isolated-handoff workflows also pass.
- Synthetic browser verification confirmed hierarchy rendering, connected path
  highlighting and department badge detail navigation.

[Main CI](https://github.com/salvaalba-dev/phantomyard-tools-private/actions/runs/39220031920),
[counterpart compatibility](https://github.com/salvaalba-dev/phantomyard-tools-private/actions/runs/39220031983),
[isolated handoff](https://github.com/salvaalba-dev/phantomyard-tools-private/actions/runs/39220031935).

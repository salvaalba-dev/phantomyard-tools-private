# AU detached reader configuration review

Observed and prepared on 2026-10-18 against private main `94dae2d`.
Status: **prepared for operator review; not ready for activation**.

## Selected host evidence

Read-only inspection of the selected executive daemon and reader confirmed their
existing separate nonroot accounts and the native executable path. The selected
native configuration/state declares the executive persona as default and an empty
autostart list. This is configuration evidence, not an attestation of live channel
listeners or loaded signing identities. No other setup was inspected or changed.

The existing system Python path is present; a proposed application-local virtual
environment path is absent. The exact proposed system interpreter finds
`coincurve` and YAML but does not find `phantomblog` under the administrator's
environment. A reviewed reader dependency environment is therefore still required;
actual account execution and signature capability remain unverified. A dedicated IPC group name and
numeric candidate were observed available; neither was created or reserved, and
availability must be checked again at cutover. Existing memberships were read
without change. The organization source still matches the prior collector
deployment fingerprint.

## Private preparation

A fresh selected collector index was downloaded into the private operator
workspace. Its exact bytes and the selected organization source were fingerprinted.
The existing metadata adapter produced a reproducible draft with these counts:

| Kind | Candidates |
| --- | ---: |
| Organization | 1 |
| Department | 7 |
| Role | 8 |
| Persona | 8 |
| Human | 4 |
| Document metadata | 65 |
| Finding | 5 |
| Relationship | 24 |
| **Total** | **122** |

The draft is metadata only. It does not include KB note bodies, private contact
values, detailed diagnostics, installation inventory or a new project adapter.
Knowledge-derived procedures remain outside this adapter. No candidate received
a category, scope, project or secret decision. Folder hints were not promoted to
classification. **Zero resources are approved or published.** A later source
change requires the existing current-draft checks and review again.

One protected reader proposal and one native host proposal were prepared for the
executive persona's Telegram and PhantomChat routes. Their persona, UIDs, origin,
handoff socket and optional conversation socket agree. The public signer was
decoded from the existing organization npub; agreement with the native loaded
signer remains a separate prerequisite. Proposed filesystem paths, IPC membership
and native build coordinates are not installed. No additional issuer, remote
persona, counterpart change or category restriction was activated.

Private outputs include the two proposed JSON configurations, projection draft,
unclassified decision template, receipt and an HTML review table. These retain
installation details and organizational metadata. Keep them outside GitHub; this
document records aggregate evidence only, not their contents or an access grant.

Follow-up: [detached release preparation](READER_RELEASE_PREPARATION.md) records
the verified source archive, disk-identity comparison and the actual reader
account's dependency versions. It does not activate this proposal.

## Verification

- The existing `deployment_routes.py` command returned
  `route-descriptors-matched`: one issuer, one native host and two listeners.
  Its result retains `activation_ready: false` and all deployment prerequisites.
- Reconstructing the draft from the captured inputs produced exact equality.
- Input fingerprints match the private receipt.
- Passing the unclassified template to the existing in-memory approval validator
  was rejected for missing classification. No approval or publication was created.

No runtime source changed in this increment, so no new full-suite result is
claimed. The preceding source increment's 693-test local result and green CI are
separate from these private preparation checks and from live deployment readiness.

## Remaining sequence

1. Review exact metadata decisions and dependencies in the private table; retain
   unresolved material outside the projection. KB classification can remain a
   separate later batch, with no implicit exposure in this first metadata view.
2. Verify native loaded public identity, actual enabled channels, interpreter
   dependencies and current authority. Prepare the source-matched native build
   and immutable reader release without replacing production executables.
3. Review exact account memberships, owned socket/audit parents, projection
   publication ownership, preserved service hardening and rollback artifacts.
4. Obtain the applicable per-action confirmation before access-affecting cutover.
   Run Linux reader preflight and then real verified-channel allowed/denied tests.

Other issuing personas require their actual hosts and existing native transports
to be reviewed. This local Unix-socket preparation does not create a remote-host
transport, copy persona credentials or assign another persona to the executive
daemon. It adds no service, account, listener or ACL authority by itself.

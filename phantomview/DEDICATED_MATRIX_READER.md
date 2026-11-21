# Dedicated identity and isolated matrix socket

Keep the existing guarded supervisor and legacy matrix route. Assign the HTTP
child a dedicated nonroot `reader_uid` and primary group, distinct from each
issuer. Review both account-derived and explicitly injected supplementary
groups. The new account needs no login shell or writable home. The existing
privileged supervisor still applies its runtime checks and issuer ACLs before
launching the child. Any boot-time provisioning rules must agree with that UID.
Move the selected matrix listener into a separate root-owned directory and
give it a group outside the reader's primary and supplementary groups.

| Boundary | Required access |
| --- | --- |
| Authority and selected index | Read the published organization and exact index, with search on each ancestor. Preserve producer ownership and write access. Authority replaces its file at mode `0640` with the parent group. Check the actual index writer and verify access after a refresh and atomic replacement. Keep protected route config root-owned and reader-readable. |
| Policy source and lock | Preserve the active authority schema and lease/commit checks. In lease mode the source path is a binding, so it requires no direct reader grant. For committed mode, test the existing source-parent and lock guards with the exact reader credentials. |
| Projection | Give the reader search and read access to the pointer, approval, and approved generation payloads. Inventory the deployed publisher's modes. Where the deployed tree already uses setgid directories and group-readable files, compare the full reach of retaining that group with using a separate publication-read group. If using a new group, arrange publisher-owned replacements, effective ACL masks and explicit output modes. Verify a new generation before cutover. Preserve writer ownership and deny reader writes. |
| Audit | With the reader quiesced, take a consistent SQLite backup and transfer only the audit state. Use a private reader-owned parent (`0700`) and database (`0600`). Verify that the reader can search every ancestor and write a real audit event. Account for SQLite journal/WAL/SHM files during backup and ownership migration. |
| Handoff and conversation | Keep readers and daemons as separate accounts. The launcher requires each handoff `socket_group` in the child's groups, and the supervisor manages the fixed handoff parents and issuer ACLs. Pair every native `readerUid` with the launch config, retain issuer IDs, origin and route paths, and validate optional conversation sockets and peer checks. |
| Matrix | Grant search (`--x`) on the protected socket directory and write (`-w-`) on the specific matrix socket to the dedicated UID. The socket creator must restore the effective ACL on each recreation. Set the broker's exact `client_uid` to the reader UID and keep the verified server UID. |

## Reconciled reader configuration

Trace the effective reader command to its active JSON and the reconciler's
settings to the protected baseline that supplies `reader_uid`. Record the
inventory, authority and agent inputs consumed by the builder, and identify
any retired JSON. Change the baseline and regenerate the active JSON through
the reconciler. The periodic reconciler can replace edits to generated
output and can stop the reader when validation fails.

Provision the dedicated system UID/GID before changing the baseline.
Validation resolves the UID through the host account database and tests the
candidate under the resolved account with the configured supplementary
groups. Check search on the publication tree's common parent as well as
each readable subtree. Both the validator and the guarded launcher set the
child's primary GID from the account record. The validator combines the
account's group list with the reconciler settings, and the launcher combines
it with its explicit supplementary-group arguments. Compare those two
inputs and verify the actual HTTP process credentials. The systemd
`Group=` and `SupplementaryGroups=` directives govern the supervisor
service context. The HTTP child and schema validation process each receive
their credentials explicitly.

Schema validation opens a temporary file owned by root and the new account's
primary group. The reconciler's replacement of the live reader JSON
preserves the existing file's group and mode and does not copy its inode ACL.
Require a separate successful open and load of the live JSON under the exact
reader credentials, including search on its parent, then repeat after
reconciliation. Verify read access to index and authority output after each
writer's atomic replacement too. Use ownership and group access preserved by
the writers, or prove that the writers restore any required ACL on new inodes.

## Persistent handoff ownership

Review all three directory provisioning layers together:

1. Effective boot-time rules under `tmpfiles.d` for the reader-owned paths.
2. The separate runtime rules file passed to `systemd-tmpfiles --create` in
   `ExecStartPre`. Prepare and review the installed file explicitly with the
   target `reader_uid`. The periodic reconciler only writes its reader
   configuration and transaction state; prepare runtime rules separately.
   A directory rule has the form `d path mode user group age`. Update only
   the user field for the managed handoff directories. Keep each route's
   existing group and mode, and preserve its separate ACL rules.
3. The service drop-in's `RuntimeDirectory=` paths, service group and guarded
   launcher arguments. Inspect both `Group=` and `SupplementaryGroups=`
   in the merged unit as well as the launcher's explicit supplementary-group
   arguments. Confirm path coverage and preserve issuer ACL handling.

Inspect all effective drop-ins in lexical order. A new override of a scalar
setting must sort after the existing assignment. An empty
`SupplementaryGroups=` clears prior assignments in the unit; an assignment
with values adds groups. Account-database memberships are independent.
Carry forward every required service group if a reset is needed. After
reloading the service manager during cutover, verify
the effective `Group`, `SupplementaryGroups`, `ExecStart`, `ExecStartPre`
and `RuntimeDirectory` values, then verify the actual child separately.

Keep the per-route group, mode `0750`, paths and applicable ACL rules for the
reader-owned parents. A group member without directory write access cannot
bind the socket. Check overlapping rules, and validate directory owner,
issuer ACLs and socket bind as the reader after restart and from freshly
provisioned runtime paths. Keep the isolated matrix directory outside the
reader-owned handoff paths.

## Socket separation

Keep the supplementary groups required by the handoff listeners. Provision a
root-owned per-route matrix directory, mode `0750`, with the matrix-only
group and a named search ACL for the dedicated UID. Ensure the directory and
its ACL are restored before the socket starts, including after reboot.
For other matrix routes use distinct protected directories and groups that
the reader does not inherit. Review any existing consumer's access before
moving its socket.

Stage a reviewed socket drop-in using the following example. Replace the
synthetic UID, group and path, and preserve other required socket hooks.

```ini
[Socket]
ListenStream=
ListenStream=/run/example-reader-matrix/matrix.sock
SocketUser=root
SocketGroup=example-matrix-ipc
SocketMode=0660
ExecStartPost=/usr/bin/setfacl -m u:12345:-w- /run/example-reader-matrix/matrix.sock
```

The ACL hook must succeed each time the socket is created. Pair the new
`ListenStream` literally in the protected HTTP route and update the broker
peer UID in the same cutover. Check the effective listener list and confirm
the previous matrix socket no longer accepts connections. Review the reader's
actual groups, ACL masks and access again after socket recreation.

## Rehearsal and cutover

The Linux rehearsal exercises the pinned HTTP dispatch and broker with a
synthetic session and matrix. It checks a successful authenticated response,
anonymous denial, and matrix isolation while the reader retains both handoff
groups. A foreign UID with those groups still cannot open the matrix socket.
Giving it the fixture's matrix-only group tests broker rejection separately.
The separate tmpfiles test proves that the old owner blocks Unix socket bind,
the migrated rules permit it on an existing and newly recreated directory, and
restoring the old rule restores the previous ownership. Authority refresh,
projection republication, audit writes, the native handoff protocol and the
matrix socket unit lifecycle are separate release checks.

1. Inventory the current unit, supervisor arguments, child credentials, native
   descriptors, publishers, and effective owner/mode/ACL on every target and
   ancestor. Save the exact previous configuration and permission state,
   including default ACLs. Identify the actual supervisor and reader releases
   from effective unit commands, the module search path and the HTTP child
   command line. Use those revisions for inspection and rehearsal. Verify the
   reader release manifest and configuration pairing before preparing the cutover.
2. Rehearse opening the actual live-format reader configuration under the
   planned identity before and after replacement, plus a fresh publication,
   audit write, issuer handoff, optional conversation,
   and socket recreation. Check that an unrelated UID fails at the appropriate
   filesystem or peer authorization boundary.
3. During an approved window, drain HTTP, pause affected handoff consumers and
   pause periodic reconciliation. Wait for any running reconciliation to
   finish before changing inputs. Stage the baseline, reviewed units and both
   tmpfiles rulesets, paired native settings and broker/socket changes.
   Validate the candidate and perform a controlled reconciliation. Test fresh
   authorized matrix and handoff requests before reopening ingress. Verify
   broker and reader results separately. Resume the timer and confirm the
   next reconciliation preserves the UID, groups, and ownership.
4. If a check fails, keep ingress drained and periodic reconciliation paused.
   Check the transaction journal before restoring inputs. A matching pending
   transaction requires the supervisor's forward recovery. If it is stale or
   cannot be recovered, keep the reader stopped for reviewed recovery.
   Once the journal is settled and current authority permits the previous
   configuration, restore authoritative inputs, unit and socket settings,
   native pairing, groups, both tmpfiles rulesets, and scoped metadata as a
   controlled change. Preserve new audit entries and validate the result before
   resuming the timer and reopening ingress.

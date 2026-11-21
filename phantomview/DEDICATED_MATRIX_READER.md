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
| Audit | With the reader quiesced, take a consistent SQLite backup and transfer only the audit state. Use a private reader-owned parent (`0700`) and database (`0600`). Verify a real audit write and account for SQLite journal/WAL/SHM files during backup and ownership migration. |
| Handoff and conversation | Keep readers and daemons as separate accounts. The launcher requires each handoff `socket_group` in the child's groups, and the supervisor manages the fixed handoff parents and issuer ACLs. Pair every native `readerUid` with the launch config, retain issuer IDs, origin and route paths, and validate optional conversation sockets and peer checks. |
| Matrix | Grant search (`--x`) on the protected socket directory and write (`-w-`) on the specific matrix socket to the dedicated UID. The socket creator must restore the effective ACL on each recreation. Set the broker's exact `client_uid` to the reader UID and keep the verified server UID. |

## Persistent handoff ownership

Follow the effective service command to the active reader JSON and record
the unit's supplementary-group arguments separately. Identify any retired
reader JSON so it stays outside the cutover. Choose an unused system UID/GID
under the host's account allocation policy.

Find every effective `tmpfiles.d` rule that provisions a reader-owned handoff
parent. Change the owner field to the dedicated account and keep the per-route
group, mode `0750`, paths, and applicable ACL rules. Preserve both handoff
groups where needed. A group member without directory write access cannot
bind the socket. Verify the full effective ruleset for overlapping entries
and apply the reviewed selected rules to the exact runtime paths during the
quiesced cutover. A live ownership change alone will be lost when the old
rules recreate the paths. Recreate the directories from their persistent
rules in rehearsal and verify ownership, issuer ACLs and bind as the reader.

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
   including default ACLs. Verify the reader release manifest and configuration
   pairing before preparing the cutover.
2. Rehearse read access and replacement under the planned identity, including
   a fresh publication, audit write, issuer handoff, optional conversation,
   and socket recreation. Check that an unrelated UID fails at the appropriate
   filesystem or peer authorization boundary.
3. During an approved window, drain HTTP and pause the affected handoff
   consumers. Change reader, handoff tmpfiles rules, socket, broker and paired
   native settings together.
   Restart with validated credentials, then test fresh authorized matrix and
   handoff requests before reopening ingress. An HTTP 404 can hide a peer or
   file permission mismatch, so verify broker and reader results separately.
4. If a check fails, quiesce again and restore the previous reader and broker
   configuration, socket listener, native pairing, groups, and persistent
   tmpfiles owner rules. Verify exact ownership, modes and ACLs after applying
   the restored rules to the scoped paths.
   Preserve audit entries added since the snapshot and verify the restored route
   before reopening ingress.

# Dedicated identity for the matrix reader

Keep the existing guarded supervisor and legacy matrix route. Assign the HTTP
child a dedicated nonroot `reader_uid` and primary group, distinct from each
issuer. Review both account-derived and explicitly injected supplementary
groups. The new account needs no login shell or writable home. The existing
privileged supervisor still prepares runtime paths before launching the child.

| Boundary | Required access |
| --- | --- |
| Authority and selected index | Read the published organization and exact index, with search on each ancestor. Preserve producer ownership and write access. Authority replaces its file at mode `0640` with the parent group. Check the actual index writer and verify access after a refresh and atomic replacement. Keep protected route config root-owned and reader-readable. |
| Policy source and lock | Preserve the active authority schema and lease/commit checks. In lease mode the source path is a binding, so it requires no direct reader grant. For committed mode, test the existing source-parent and lock guards with the exact reader credentials. |
| Projection | Give the reader search and read access to the pointer, approval, and approved generation payloads only. The stock writer creates generation directories at `0700` and files at `0600`. A file ACL on today's generation is insufficient. Confirm the actual publisher and how it will retain narrowly scoped read access after publication before cutover. Preserve writer ownership and deny reader writes. |
| Audit | With the reader quiesced, take a consistent SQLite backup and transfer only the audit state. Use a private reader-owned parent (`0700`) and database (`0600`). Verify a real audit write and account for SQLite journal/WAL/SHM files during backup and ownership migration. |
| Handoff and conversation | Keep readers and daemons as separate accounts. The launcher requires each handoff `socket_group` in the child's groups, and the supervisor manages the fixed handoff parents and issuer ACLs. Pair every native `readerUid` with the launch config, retain issuer IDs, origin and route paths, and validate optional conversation sockets and peer checks. |
| Matrix | Grant search (`--x`) on the protected socket directory and write (`-w-`) on the specific matrix socket to the dedicated UID. The socket creator must restore the effective ACL on each recreation. Set the broker's exact `client_uid` to the reader UID and keep the verified server UID. |

If the handoff group also controls a shared matrix socket directory and
group-writable sibling sockets, a named user ACL on one socket does not
restrict what group membership grants on its neighbors. Provision separate
handoff/transport groups or separate protected paths before claiming that the
reader can reach only its designated matrix socket. Review every retained
group using the real HTTP child's credentials.

## Rehearsal and cutover

The Linux rehearsal exercises the pinned HTTP dispatch and broker with a
synthetic session and matrix. It checks a successful authenticated response,
anonymous denial, filesystem ACL isolation, and broker rejection of a
different UID that can connect through the shared group. Live authority,
projection, audit and native handoff require separate release preflight.

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
   consumers. Change reader, broker, and paired native settings together.
   Restart with validated credentials, then test fresh authorized matrix and
   handoff requests before reopening ingress. An HTTP 404 can hide a peer or
   file permission mismatch, so verify broker and reader results separately.
4. If a check fails, quiesce again and restore the previous reader and broker
   configuration, native pairing, groups, and exact ownership/modes/ACLs.
   Preserve audit entries added since the snapshot and verify the restored route
   before reopening ingress.

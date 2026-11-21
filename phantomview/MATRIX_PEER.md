# Dedicated matrix broker identity

This connector draft is superseded by assigning a dedicated nonroot UID to the
existing HTTP reader through its `reader_uid` launch setting. The guarded
supervisor can run as root while the HTTP process runs as its unprivileged
child. Inspect the listening process and its supplementary groups to establish
its identity. The root-viewer connector below is retained for review history.

This is an opt-in route for a single identified persona and one broker socket.
The scoped HTTP handler checks the origin, identified session and current
project authorization. A short-lived helper opens the Unix socket under the
configured dedicated UID/GID with no supplementary groups. It returns only
the connected descriptor. The viewer checks that it is a Unix stream
connected to the exact configured path and verifies the broker's root peer
credentials and retains responsibility for rechecking the session, sending
the HTTP response, and acknowledging delivery. This prototype assumes a root
HTTP process and is unsuitable for the existing unprivileged reader.

For an Alma-only deployment, provision a dedicated system identity with no
login shell, unrelated processes, supplementary groups, writable home or writable executable
paths. A shared domain account cannot act as this identity. In the protected
broker configuration, set `client_uid` to the dedicated identity. Keep the
existing reader agent identity. This route requires a root broker
(`server_uid = 0`).

Use the protected root-owned `PHANTOMVIEW_MATRIX_PEER_ROUTES` configuration
shown below, substituting the locally approved actor, scope and numeric IDs.
Copy the socket path literally from the unit's `ListenStream` value. The
prototype compares pathname strings, so aliases such as `/var/run` for
`/run` do not match. Set it only in the scoped viewer. Build a new reader release from the reviewed
viewer commit. Compose the native route with the viewer UI and other required
patches. Omit the legacy `PHANTOMVIEW_MATRIX_ROUTES` setting and the call to
`phantomdocs.view_matrix_http_patch.patch_http()`. Its source pin is
`ecbe853eb1b14bc0da8a3dfdd879461daabbcad9c24fa9d951b8a534e3e69ef4`.
The new dispatcher intentionally fails this legacy pin with
`unsupported reader revision`. Regenerate the file manifest for the new
release, including `matrix_peer.py`, `matrix_http.py` and the changed
`scoped_http.py`. Independently verify the complete tree and its digest
before selecting it. Preserve the previous release and manifest for rollback.

```json
{
  "version": 2,
  "routes": {
    "example-agent": {
      "socket": "/run/example-view/matrix-example.sock",
      "server_uid": 0,
      "client_uid": 2050,
      "client_gid": 2050,
      "domain": "projects",
      "project_type": "example",
      "scope_id": "example"
    }
  }
}
```

Grant the named UID search-only access (`--x`) on the socket directory and
write-only access (`-w-`) on the single Alma socket. On Linux, Unix stream
connect requires write permission on a pathname socket. Directory search does
not grant listing. Preserve existing owners, group grants, named entries and
ACL mask effects. Apply the socket ACL on every creation through a reviewed
hook on that socket unit alone. Use `ExecStartPost=` without the `-` prefix so
an ACL failure fails socket startup. Do not add a default directory ACL or group
membership. Before activation, compare effective ACLs and verify that the
connector cannot open neighboring sockets and other UIDs cannot open Alma's
socket. The helper uses `/usr/bin/python3 -I -S -B` and checks all real,
effective and saved user and group IDs as well as an empty supplementary group
list before opening the socket. Verify the interpreter is executable by the
connector and supports `socket.send_fds` and `socket.recv_fds`.

For cutover, pause external Alma matrix traffic and drain in-flight requests.
Capture the effective viewer, broker and socket configuration and ACLs for
rollback. Install the reviewed release and protected route and broker JSON
while intake is paused. Check that the viewer route's `client_uid` exactly
matches the broker's effective protected configuration, that the route socket
matches the listener, and that `server_uid` is zero. Verify the socket ACL
after creation. Before restoring external intake, make an authenticated read
through the new viewer using controlled access, and verify the expected version,
content hash and independent denial checks. An identity mismatch can return a
404 while the broker exits successfully, so unit health and `OnFailure` alone
cannot validate this change. On failure restore both JSON bindings, the prior
release selection and ACLs before restoring intake.

The privileged Linux test uses a disposable ACL, the real scoped HTTP route, and
the PhantomDocs broker with a synthetic session and matrix payload. It checks
filesystem denial for another UID, then separately checks the broker denial
even if that UID can connect. Production acceptance still requires an
authenticated read through the installed viewer after separately authorized
changes to the identity, ACLs and broker configuration.

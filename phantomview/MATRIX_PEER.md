# Dedicated matrix broker identity

This is an opt-in route for a single identified persona and one broker socket.
The scoped HTTP handler checks the origin, identified session and current
project authorization. A short-lived helper opens the Unix socket under the
configured dedicated UID/GID with no supplementary groups. It returns only
the connected descriptor. The viewer verifies the broker's root peer
credentials and retains responsibility for rechecking the session, sending
the HTTP response, and acknowledging delivery.

For an Alma-only deployment, provision a dedicated system identity with no
login shell, unrelated processes, supplementary groups or writable executable
paths. A shared domain account cannot act as this identity. In the protected
broker configuration, set `client_uid` to the dedicated identity. Keep the
reader agent identity and broker server UID from the existing configuration.

Use the protected root-owned `PHANTOMVIEW_MATRIX_PEER_ROUTES` configuration
shown below, substituting the locally approved actor, scope and numeric IDs.
Set it only in the scoped viewer. Compose the native route with the viewer UI
and other required patches, omitting the legacy injected HTTP matrix route
and its `PHANTOMVIEW_MATRIX_ROUTES` setting. The older tools HTTP patch pins the
unmodified dispatcher and must not be applied to this revision.

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
hook on that socket unit alone. Do not add a default directory ACL or group
membership. Before activation, compare effective ACLs and verify that the
connector cannot open neighboring sockets and other UIDs cannot open Alma's
socket. Changing the broker UID and viewer route together avoids a mismatch.

The privileged Linux test uses a disposable ACL, the real scoped HTTP route, and
the PhantomDocs broker with a synthetic session and matrix payload. It checks
filesystem denial for another UID, then separately checks the broker denial
even if that UID can connect. Production acceptance still requires an
authenticated read through the installed viewer after separately authorized
changes to the identity, ACLs and broker configuration.

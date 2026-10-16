# Private verified-channel handoff

Status: inactive Linux IPC primitives, with synthetic and real-signature tests.
There is no installed listener, native PhantomBot hook or enabled expanded access.
See [integration status](VERIFIED_CHANNEL_INTEGRATION.md) for remaining work.

## Account boundary

`trusted_handoff.py` accepts a Unix-domain connection only after Linux
`SO_PEERCRED` identifies its process account as the configured native issuer UID.
It rejects network sockets and unknown accounts before reading request bytes or
returning a response. There is no bearer secret, HTTP identity endpoint, header
identity assertion or network fallback.

`PeerPolicy(issuer_uid, frozenset(model_uids))` requires:

- A nonroot native channel account distinct from the reader account.
- A nonempty, explicit inventory of all nonroot model/tool execution accounts.
- No model account matching the native issuer or reader account.
- Linux kernel peer credentials. Other platforms fail closed.

This validates configured separation; it cannot discover undeclared model
processes or prove that the operator's account inventory is complete. The issuer
account is authoritative: every process running as that account can assert channel
context. Do not run model tools, arbitrary shells, plugins or user jobs under it.
Do not grant model accounts root, UID-changing capabilities, sudo access to these
accounts, writable service code/configuration or access to their process memory.
The native handler must not pass a connected socket or signing credential to a
model process, including through inherited descriptors.

The current shared daemon/model account is not made safe merely by installing this
module. A separately isolated native channel component must first own the verified
channel context and be tested against the installed PhantomBot release. Existing
PhantomBot source is unchanged by this increment.

## Listener ownership

The operator provisions a fixed private runtime directory, owned by the reader or
root and not writable by group/others. Give the native channel account traversal
access and membership in a dedicated handoff group. All parent paths must be
operator-controlled and must not contain symlinks.

`bind_listener(absolute_path, group_id)` creates a Unix stream socket with mode
`0660` and the explicit group. It never removes or replaces an existing path;
inspect stale sockets before restarting. The caller owns the accept loop, service
lifecycle and cleanup. No daemon, service unit or live socket is created on import.
`serve_connection(connection, gate, peer_policy)` processes exactly one request and
closes the accepted connection on every outcome.

The reader must retain its `IdentifiedGate` instance in the same process as the
web session/redeem handler. Starting an independent broker with another gate would
not share the in-memory single-use grants or recipient bindings. No persistence or
cross-process session transfer is provided here.

`reader_handoff.ReaderHandoff` supplies the opt-in listener lifecycle. An embedding
application constructs it with the fixed socket path, group, `PeerPolicy` and
`IdentifiedGate`, then passes it as `handoff=` to `phantomview.serve`. Startup checks
that HTTP redemption and native issuance share that exact gate object. A mismatch
or listener startup failure closes the HTTP socket before serving requests.

The runtime processes one connection at a time, exposes a `healthy` observation,
interrupts pending socket I/O during shutdown and joins its listener thread.
Cleanup removes only a socket whose device, inode and owner still match the one
created by this runtime. It preserves an operator's replacement file. A stopped
runtime cannot be reused. Unexpected listener errors do not log request data and
make its health observation false; no legacy issuance fallback is selected.

There is no new CLI or environment activation setting. The default reader still
creates its existing analysis-only gate and no private listener. This embedding
seam does not implement per-resource HTTP filtering: do not enable identified
sessions for ordinary users until backend filtering and the remaining activation
checks are complete.

## Native client

`handoff_client.request_access` is an inactive library function for the isolated
native channel service, not a CLI, browser API or model tool. Its `ReaderPolicy`
requires a separate expected reader UID and an explicit nonroot model-account
inventory. The native issuer itself must also be a nonroot, separate account.

Before connecting, it checks the fixed socket path, socket ownership, protected
parent directory and absence of symlink parents. After connecting, it verifies
the reader's Linux kernel UID before sending the signed event or sender context.
It validates the response schema and exact configured HTTPS origin and accepts
only the existing `/#c=<43-character-grant>` delivery shape. It never derives a
destination from returned data, falls back to a network endpoint or retries a
signed request. A lost reply requires a fresh signed event.

The native caller must deliver the returned link directly to the verified sender
without logging it or passing it to a model. Receiver authentication does not
replace the channel's actual sender authentication or the server's signing checks.
This library does not register a PhantomBot command or alter its shared dispatcher.

## Native request contract

Only the native pre-model direct-message handler may construct a request, after
the transport has authenticated the actual sender and its explicit allowlist has
admitted that principal. Groups, relay tiers, open-bot strangers and email From
claims do not qualify. For PhantomChat, encode the cryptographically proven sender
hex using the native NIP-19 encoder; do not use an envelope's claimed sender.

Each frame contains a four-byte unsigned big-endian length followed by UTF-8 JSON.
The maximum frame is 16 KiB. Reads and reply share a three-second deadline; sending
small fragments cannot extend the read deadline. Duplicate JSON fields, incomplete
frames and unknown request fields fail. The exact request fields are:

```json
{
  "schema_version": 1,
  "authorization": "Nostr <base64-signed-event>",
  "channel": "telegram",
  "sender": "101",
  "direct": true,
  "principal_authenticated": true,
  "scope_id": "river-project"
}
```

The sample sender is synthetic. `scope_id` must be an explicitly permitted scope
in the current private PhantomOrg source. The reader's configured gate supplies
the issuing persona and public origin; neither can be overridden by this frame.
The authenticated native service vouches for the context booleans. They are not
authentication when submitted by an ordinary process or browser.

The native service supplies the normal signed NIP-98 event. Canonical NIP-01 ID
recomputation, Schnorr verification, issuer allowlist, freshness, replay cache,
exact tags and empty payload remain in the existing PhantomBlog verifier. No
recipient, category or scope is added to that signed protocol. The reader binds
recipient metadata privately to the resulting grant digest.

A successful reply contains only `schema_version: 1` and `link`. The link retains
the existing fragment credential and five-minute, locked, single-use redemption.
The native service must send it only to the verified direct sender through the
same channel. Never forward it into model inference, logs, analytics, group chats
or a different conversation. Failed delivery may leave an unused expiring grant;
it does not create a browser session or authorize an alternate recipient.

An authenticated peer receives a generic denial for invalid requests; exceptions,
credentials and sender details are never echoed. Unknown peers are disconnected
without a response. Replay rejection and current policy/channel-identity checks
remain active at issuance, redemption and every identified request. Legacy signed
links remain analysis-only and are never promoted automatically.

## Validation and activation

The tests cover account separation, rejection before reads, network rejection,
frame bounds/deadlines, duplicate fields, reader-owned origin/persona and generic
errors. The optional installed PhantomBlog access extra enables actual Schnorr
issuance, single-use redemption, scope binding, signature rejection, replay and
policy-revocation tests. Linux CI additionally checks actual kernel rejection and
socket ownership/mode behavior. The dedicated `PhantomView isolated handoff` job
uses the exact reviewed PhantomBlog fork revision and real access dependencies.
It runs the complete suite, then starts disposable reader, issuer and model
processes with separate numeric UIDs on its ephemeral runner. It checks positive
signed scoped issuance through the managed listener and redemption through the
actual HTTP reader handler, model rejection despite a valid
signed event, and reader-UID rejection before sender-context transmission.

The reader integration test also checks the resulting human/scope, rejects HTTP
redemption replay and verifies that listener shutdown removes its own socket.

The account test driver requires Linux, root and the explicit
`PHANTOMVIEW_ACCOUNT_TESTS=1` flag. Its child processes permanently drop their UIDs;
it creates no users, groups or services and writes only its temporary runtime
directory. Do not run this privileged test driver on the production VPS. Its CI
job has read-only repository permissions, no persisted checkout credentials and
no VPS credentials or access. CI isolation does not prove AU's native channel
handler or message delivery is correctly configured.

Before AU activation: provision and verify the isolated channel component; connect
the native pre-model handler and reader listener; test verified direct delivery;
migrate validated PhantomOrg scopes/counterparts; approve reviewed resources; and
enforce backend, worker and response-time access checks with JEV and audit. This
increment creates no new live access and requests no second human signature/login.

## Native PhantomBot source boundary

The inspected source keeps Telegram and PhantomChat listeners and model turns in
one `phantombot run` process. Its contributor guidance rejects a new per-persona
supervisor. Adding a shell command or an optional callback inside that existing
shared model account would not establish the dedicated issuer-account boundary.
No native patch is claimed or enabled by the reader integration. A compatible
native ingress/execution isolation design must be reviewed against the installed
release before its command handler can call the client. Do not start a competing
Telegram poller, disable existing personas or split services implicitly.

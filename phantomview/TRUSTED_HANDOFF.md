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
socket ownership/mode behavior. Positive cross-account kernel acceptance and
native message delivery still require a provisioned multi-account integration
environment; synthetic peer tests do not establish that deployment property.

Before AU activation: provision and verify the isolated channel component; connect
the native pre-model handler and reader listener; test verified direct delivery;
migrate validated PhantomOrg scopes/counterparts; approve reviewed resources; and
enforce backend, worker and response-time access checks with JEV and audit. This
increment creates no new live access and requests no second human signature/login.

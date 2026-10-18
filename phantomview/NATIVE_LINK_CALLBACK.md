# Native command to identified-link callback

Status: inactive source integration. No live AU configuration, channel, signer,
credential or service has changed. This binds the
[generic authenticated command seam](AUTHENTICATED_COMMAND_SEAM.md) to the existing
protected reader client without introducing a resident worker.

## Flow

1. The existing verified native loop invokes its fixed `AuthenticatedCommand`.
2. `nativeLinkCallback` checks the receiving persona, channel, source ID/time and
   current configured non-model issuer account. Configuration is fixed native
   code, never a browser or model-provided process command.
3. The existing native signer supplies the unchanged NIP-98 authorization. No
   signing key, vault contents or separate credential store are accepted here.
4. A short Python process runs `native_link_client.py` with isolated `-I` imports.
   Signed authorization and native sender are supplied through bounded stdin,
   not process arguments. Only fixed non-secret route/account configuration is
   passed as arguments. No shell or model-readable spool is used.
5. The one-shot client calls the existing `ReaderPolicy` and `request_access`.
   Kernel peer checks, fixed socket ownership, bounded framing, signed verification
   and current PhantomOrg recipient resolution remain in their existing components.
6. The callback validates the exact HTTPS fragment link again and sends it through
   the existing native direct-delivery function to the original verified sender.
   Its return value contains no link or identity. Failure consumes the command
   through the generic seam; it never falls back to a model.

PhantomChat retains native verified hex for message delivery and uses the existing
native NIP-19 encoder for PhantomOrg lookup. Telegram keeps its numeric user ID.
No human ID, category, project grant or browser-selected persona is authoritative.

## Fixed embedding contract

Construct `nativeLinkCallback` with a fixed persona/channel, scope ID, canonical
origin, issuer/reader/model UIDs, absolute Python/client/socket paths and the
existing signer, NIP-19 encoder and direct-delivery callbacks. Pass that callable
as the generic command handler. It has no CLI/config auto-registration and does
not change the global active persona. The process entry is private native plumbing,
never a persona tool or a public identity endpoint.

The reader must still use the same identified gate for issuance and redemption.
Its fixed issuer identity and PhantomOrg declarations must match the native route.
The existing gate remains single-issuer; this callback does not register several
runtime/persona routes automatically. Do not use an analysis-only legacy reader.

The operator must protect the executable, script/module directory and every parent
from model-account writes. The Python client imports only its fixed operator-owned
module directory in isolated mode. It does not attest filesystem ownership for
the native embedding or discover every process/account in the installation.

## Cancellation and failure boundaries

The client process has a 3.5-second bound and observes the native cancellation
signal. Cancellation sends SIGTERM, followed by SIGKILL after 200 ms if necessary.
The trusted client does not spawn further children. Stdout is limited to 2048
bytes and stderr is discarded. Native errors are reduced to a generic unavailable
result. No signed events, link grants or identity-bearing frames are logged.

Context is copied before awaiting the signer, so subsequent mutation cannot change
the native recipient. Recheck the signal after signing, after IPC and before direct
delivery. A started external delivery cannot be undone; its native implementation
must honor cancellation and return an explicit acknowledgement. An ambiguous
failure is not retried automatically. A grant issued just before cancellation may
remain unredeemed until its normal expiry; no extra revocation protocol is claimed.

## Validation and limits

Local Python tests verify exact framing, fixed routes, malformed/duplicate/oversized
input, account refusal, isolated entry imports and sanitized failures. The native
CI fixture executes real one-shot processes with synthetic reader replies and
checks canonical PhantomChat identity, direct delivery, context mutation,
cancellation and rejected response shapes. That fixture is not a kernel-peer test.

The existing isolated-handoff CI additionally uses permanently dropped disposable
Linux UIDs and the real signed verifier to exercise this client with the protected
socket and PhantomOrg resolution. A model account is denied before the valid issuer
connects. Existing replay, redemption, expiry and native dispatch tests remain intact.

This does not solve the live shared issuer/model account boundary or supply a new
native signer discovery API. Existing peer-policy requirements are preserved.
Installed-version compatibility, protected callback embedding, authoritative live
counterpart declarations, reader filtering and reversible deployment are still
required. Never activate this on AU by declaring the existing shared account safe.

## Private control transport preparation

The native source proposal now adds optional `sendPrivateControlMessage` methods
to the existing Telegram and PhantomChat transports. Use the fixed
`privateControlDelivery(channel, origin, transport)` adapter for `deliverDirect`;
it rejects transports that only implement ordinary `sendMessage`. It binds the
original native recipient and exact HTTPS fragment-link shape. No credential is
read, copied or provisioned by this delivery adapter.

Ordinary transport sends are unsuitable for this callback: Telegram can resolve
without an accepted API result, and both channels correlate sent text with later
reactions. A subsequent reaction must not reintroduce a live access grant as
conversation context. The optional methods bypass those outbound recorders.
They do not erase an already recorded message or remove browser/channel history.

Telegram performs one plain-text API request, disables link previews, requests
content protection and checks a successful private-chat acknowledgement for the
exact recipient. API failure, invalid/oversized acknowledgement and cancellation
return false without HTML fallback, retries or plaintext error logs. Content
protection is a platform hint, not a guarantee against copying.

PhantomChat uses the existing native encrypted `wrapV2` and configured relay publish
path. It returns true only on relay acceptance, without reaction correlation,
read-back subscriptions or rewrap retry jobs. This control path does not use the
optional P2P delivery shortcut. Ordinary chat keeps its existing behavior.

Acceptance means transport acknowledgement, not human receipt or reading. A
three-second deadline bounds waiting; it cannot retract a message already sent,
and an in-flight relay operation may complete after cancellation. Failure is not
retried automatically. Tests use mocked HTTP/relay IO and disposable Nostr keys;
no production human is contacted. Signing, protected reader handoff and AU
activation remain separate pending steps.

# Native access command seam

Status: inactive library with synthetic adapter-context tests and isolated Linux
account integration coverage. **No native PhantomBot hook, channel host, service,
account migration or AU activation is supplied by this increment.**

`NativeAccessCommand` consumes an exact `/phantomview` direct-message command
before model dispatch. The trusted embedding supplies a fixed channel, scope,
reader socket, reader UID/model-UID policy, HTTPS origin, signing callback and
direct-delivery callback. The reader's existing gate owns the issuing persona;
the signer must use that persona's protected identity. No command argument may
select a human, persona, scope, category, URL or credential.

## Native integration points

The inspected source is `5af27060327ee8c53fe730dd8b98b6b305c62add`; its compatibility
with the installed AU executable is not established by these tests.

- Telegram: `src/channels/core/engine.ts` computes
  `principalAuthenticated` from a nonempty explicit numeric allowlist before its
  inline slash-command path. The integration must use the transport's actual
  sender and message ID/date, require a private direct message, then intercept
  the reserved command before ordinary command or turn execution.
- PhantomChat: `src/channels/phantomchat/server.ts` resolves authorization tiers
  before its command path. Require the trusted direct tier and no group/relay
  context. The adapter must use native NIP-19 encoding of the cryptographically
  proven sender hex, plus the verified event ID/time, rather than any claimed
  display name, text or relay-envelope sender.
- Only `Outcome.NOT_COMMAND` may continue to ordinary model dispatch. Every other
  outcome consumes the reserved command. The native adapter may report a fixed
  failure notice directly to an already verified sender; it must never ask the
  model to interpret an issuance failure or retry it as a tool call.

`DirectMessage` is an in-process transport contract, **not proof of identity**.
It must never be deserialized from a browser, model output, tool argument or
unauthenticated HTTP request and treated as authenticated context. The reader
still resolves the current PhantomOrg human/counterpart/scope and enforces its
existing signing and session policy.

## Required process boundary

The host must be a separate nonroot channel/issuer account, distinct from the
reader and every model/tool execution account. Construction revalidates
`ReaderPolicy`; each reserved command rechecks it and the original process UID
before signing. `request_access` retains its kernel peer check before sending
authorization or sender bytes. There is no network or legacy issuance fallback.

These account checks validate configured identities, not a complete inventory of
process capabilities. They do not isolate a shared daemon, discover undeclared
models or protect credentials from another process with the same UID.

The current shared `phantombot run` must not install this handler and merely
declare its own account safe. The compatible architecture must keep verified
ingress/issuance outside every model/tool account, preserve one native channel
consumer, and preserve the contributor rule against per-persona supervisors.
It must address all model entry points and fallback harnesses, not only the
PhantomView worker. Starting a competing Telegram poller is not a migration.
The handler is a dispatch component for that future host, not the host itself.

## Delivery, bounds and failure behavior

- The exact lowercase command accepts surrounding whitespace but no arguments
  or bot-target suffix. Unsupported variants are consumed and rejected.
- Require explicit direct/principal booleans, a canonical supported sender,
  a transport-owned message ID and a timestamp within 60 seconds. The PhantomChat
  adapter remains responsible for signature/event validation; a matching npub
  string is not cryptographic proof.
- Claim `(sender, message ID)` under a lock before signing or IPC. The in-memory
  duplicate cache is bounded to 256 entries with 120-second retention. Concurrent
  duplicate delivery cannot trigger another signing or direct-delivery call.
- Allow at most three attempts per sender and sixteen per handler in a rolling
  minute. These limits are process-local. Keep one long-lived instance per fixed
  binding; creating an instance per message defeats its budgets and duplicate
  protection. Native channel checkpointing must still handle restarts; this is
  not durable exactly-once delivery or distributed rate accounting.
- The unchanged handoff client enforces its three-second IPC deadline. Signing
  and delivery callbacks must have finite native deadlines and must not log their
  arguments/results. This synchronous handler does not impose callback timeouts.
- Return only an `Outcome`. A valid fragment-only link is passed directly to the
  supplied delivery callback with the same fixed channel and proven sender.
  Require an explicit `True` acknowledgement for `DELIVERED`; transport acceptance
  does not prove that the human read the message.
- Any callback exception, denial or ambiguous delivery consumes the attempt.
  No exception text, link, signed event or raw identity is returned to a model.
  There is no automatic retry. An unused issued link expires normally; ask for a
  fresh native message rather than automatically reusing an ambiguous request.

No new login, human signature or change to canonical NIP-01/NIP-98 verification,
Schnorr validation, allowlists, freshness, replay, exact tags/payload or single-use
fragment redemption is introduced.

## Validation and activation

Unit tests cover fixed routing, no override/fallback, stale/unverified contexts,
concurrent duplicates, callback failures, fragment-only delivery, explicit
acknowledgement, budgets and shared/current account rejection. These tests mock
adapter authentication and IPC and do not prove native transport verification.

The ephemeral Linux account job additionally routes this handler through real
`ReaderPolicy`, Unix peer authentication, actual signed issuance, single-use HTTP
redemption and scoped resource reads. Its delivery callback is synthetic; it
sends no Telegram/PhantomChat message. The existing malicious-model test still
bypasses cooperative client checks to verify kernel-side rejection.

Before live activation, implement and review the native isolated host and its
installed-release adapter, protected signing/delivery lifecycle, complete account
inventory, persistent channel checkpoints and current PhantomOrg/resource policy.
See [AU readiness](AU_PILOT_READINESS.md). The public widget and other setups remain
outside this increment.

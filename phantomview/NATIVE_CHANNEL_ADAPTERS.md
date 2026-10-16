# Private Telegram and PhantomChat adapters

Status: inactive opt-in source hooks over pinned PhantomBot
`5af27060327ee8c53fe730dd8b98b6b305c62add`. No isolated host, signer, IPC/delivery
callback, CLI activation or live channel cutover is supplied by this increment.

`native_channel_patch.py` layers the [provenance patch](NATIVE_INGRESS_PROVENANCE.md)
and inserts `NativeAccessRouter` into both actual native server loops. It updates
the copied native README and AGENTS together. With no trusted `nativeAccess`
binding, ordinary dispatch remains unchanged. Upstream and AU remain unchanged.

## Channel authority

| Channel | Required native context |
| --- | --- |
| Telegram | Actual sender in a nonempty explicit allowlist; exactly private chat; conversation equals sender; no media/group/reaction; fresh API source ID/date |
| PhantomChat | Proven sender from verifying unwrap; configured startup allowlist snapshot admits it; relay membership denies even double-listed senders; direct conversation; no group/media/reaction; fresh canonical rumor ID/time |

PhantomChat uses native NIP-19 encoding of the proven sender. App-envelope sender,
ID/time and receipt IDs cannot replace this context. The hook never calls TOFU:
an empty startup allowlist cannot gain access-command authority from its first
sender. Ordinary nonreserved TOFU behavior remains unchanged.

When enabled, all reserved `/phantomview` variants are consumed before ordinary
slash commands, voice, reactions or model dispatch. Only the exact lowercase
command, allowing surrounding whitespace, reaches the callback. Arguments and
bot-target suffixes are rejected. Failure, rejection, cancellation and timeout
never become model input. Nonreserved messages retain their ordinary path.

## Protected host contract

The router fixes one persona/scope and freezes its copied account configuration.
Startup requires Linux, the actual nonroot issuer UID, a distinct positive reader
UID and a nonempty explicit model/tool UID inventory excluding issuer and reader.
Persona mismatch and plain callback objects fail before polling. Commands recheck
the current UID. This validates configured roles; it does not discover undeclared
models, isolate a shared daemon or prove the inventory complete.

The callback receives a frozen `NativeAccessContext` and an abort signal. It must
implement protected signing, existing peer-authenticated handoff and same-sender
direct delivery with fixed persona/reader settings. No context may enter inference
or an identity API; no credentials/grants may enter logs. The Python
[command handler](NATIVE_ACCESS_COMMAND.md) remains a lifecycle component, but the
adapters do not launch it or define a new bridge.

Duplicates are claimed synchronously before callback work, retained for 120
seconds in a bounded 256-entry map. Attempts are limited to three per
channel/sender and sixteen per router per minute. Keep one long-lived instance per
persona, optionally shared by both channels. Native checkpointing remains needed
across restarts; this is not durable/distributed exactly-once delivery.

Shutdown or a five-second deadline aborts the signal and bounds dispatcher waiting.
The callback must honor cancellation in actual signing, IPC and delivery: a promise
race does not prove an ignoring callback/process stopped. No ambiguous attempt is
automatically retried. Callback output and exception text are discarded. The
signed access-link protocol is unchanged.

## Validation and activation

Python tests check combined preparation, hook ordering and refusal before writes
for source drift/preexisting helpers. Native tests drive both actual server loops
with synthetic transports/scripted harnesses, proving zero model invocations for
consumed commands and ordinary behavior for disabled bindings/nonreserved text.
The positive PhantomChat test uses real gift-wrap signing/decryption, the actual
listener and server allowlist before checking canonical npub/rumor context.
Denial, duplicate, account, budget, failure and cancellation cases are also covered.

CI runs existing Telegram, PhantomChat channel and PhantomChat server regressions
and baseline compilation. No real channel, human messaging, external model or VPS
credentials are used. Actual kernel separation and signed redemption remain
covered by the separate isolated handoff job.

Activation still requires a protected callback and complete isolated host against
the installed release, ordinary conversation forwarding, every model/fallback
entry point review, a single channel consumer and reversible cutover. No
per-persona supervisors or competing pollers may be introduced. PhantomOrg
migration, reviewed classifications and audit provisioning remain required.
See [AU readiness](AU_PILOT_READINESS.md).

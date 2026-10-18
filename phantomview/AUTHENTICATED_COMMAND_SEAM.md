# Optional authenticated direct-command seam

Status: private source proposal, inactive. No signer, reader transport or AU
installation is connected. This is the small channel extension considered by P1
of the [collaborative plan](COLLABORATIVE_VIEWER_PLAN.md), not a replacement daemon.

## Ownership

PhantomBot already knows the receiving persona and native sender. This proposal
preserves that context before a reserved direct command can enter a model. It
introduces no human, organization, category, counterpart or ACL model in PhantomBot.
PhantomOrg remains authoritative for those declarations. PhantomView remains the
visual consumer and session holder. Native memory, tools and ordinary trust/JEV
paths are unchanged when the optional binding is absent.

`AuthenticatedCommand` is explicitly embedded in the existing channel loop. The
fixed command, persona and callback are operator/native code, not configuration
provided by a browser, message or model tool. The callback receives an immutable
channel, receiving persona, native sender, source message ID/time and command.
Telegram supplies its explicit principal decision. PhantomChat snapshots the
configured allowlist, excludes relays and does not elevate TOFU or an open bot.
Group, media, stale, malformed, duplicate and unauthenticated reserved requests
are consumed without model fallback. Ordinary text remains on its existing path.

Optional bindings cannot use native control names such as `/stop`, `/reset`,
`/update` or `/restart`. Construction rejects every command advertised by the
reviewed native dispatcher, leaving cancellation and lifecycle controls on their
existing path. Exact-source preparation now checks `src/channels/commands.ts`
before any writes; dispatcher drift requires a new review. The native fixture
compares this refusal against the actual exported command list.

PhantomChat sender IDs remain native verified hexadecimal public keys. The future
handoff adapter must use the existing native NIP-19 encoder to resolve PhantomOrg
npubs; it must not accept a message-envelope identity or browser replacement.

## Deliberate limits

The callback has a five-second cancellation signal and bounded attempt/duplicate
state. It must honor cancellation before side effects. Cancellation cannot undo
an issued grant or force an arbitrary callback to stop; callback completion and
private delivery remain integration responsibilities. Failure text and callback
return values never become model input or an ordinary conversational reply.

This seam is not an authentication endpoint. Calling its method with `true` is
not proof of a sender outside the actual verified native loop. It is not registered
as a tool, CLI, HTTP route, webhook or poller. It does not create account isolation
or make model/tool execution under a shared issuer account safe. Existing protected
handoff peer policies are neither relaxed nor bypassed. A compatible protected
handoff and explicit PhantomOrg counterpart mapping remain unresolved deployment
requirements. Do not deploy the historical isolated-worker architecture merely to
make this callback available, and do not treat this source proposal as AU readiness.

The existing signed-link design is untouched. No human login or second signature
is added by the seam. No credential is copied and no global persona is switched.

## Explicit daemon startup registration

The private source proposal now threads `RunInput.authenticatedCommands` through
the existing `runRun` startup. Trusted host code constructs an
`AuthenticatedCommandRegistry` with explicit channel/persona/command/callback
entries. The registry is validated before configuration loading. Each actual
listener resolves its own exact route; an unregistered persona or channel gets no
handler. There is no default-persona fallback. Registrations are copied, duplicate
routes and native control names are rejected, and state is separate per route.

An embedded startup can use the following shape after the reviewed native patch:

```typescript
const authenticatedCommands = new AuthenticatedCommandRegistry([
  { channel: "telegram", persona: "coordinator", command: "/phantomview",
    handle: verifiedTelegramLinkHandler },
  { channel: "phantomchat", persona: "coordinator", command: "/phantomview",
    handle: verifiedPhantomchatLinkHandler },
]);
await runRun({ authenticatedCommands });
```

The two handlers above must be supplied by the trusted integration; the example
does not create them. They are not model tools or JSON configuration. Use the
existing daemon startup and process lock, not a second polling process. No native
CLI flag, dynamic module loader, environment hook, service or signer discovery is
added. An unmodified CLI still starts without this registration. This closes
programmatic startup routing, not live link issuance or AU activation. The old
account-isolated callback keeps its checks and is not automatically compatible
with the shared collaborative daemon.

Standalone tests cover exact routing, immutable copies, duplicate/control-name
refusal and independent persona attempt state. The native startup fixture uses
temporary stores and stubbed Telegram listeners to check actual `runRun` wiring.
Native Telegram dispatch and verified PhantomChat gift-wrap fixtures now resolve
their handlers through the same registry. They do not contact live users or prove
production signing, delivery, reader integration or full startup networking.

## Reader callback integration

The private [native link callback](NATIVE_LINK_CALLBACK.md) now connects the seam
to the unchanged protected reader client through a bounded one-shot process and
original-sender direct delivery. It is an inactive embedding library, not signer
discovery or live AU activation. Shared-account and PhantomOrg deployment gaps
remain explicit; existing kernel peer policies are unchanged.

## Exact-source preparation

`authenticated_command_patch.py` targets the reviewed native source revision
`5af27060327ee8c53fe730dd8b98b6b305c62add`. It validates source hashes and hook anchors
before writing, refuses existing helpers and reapplication, and reuses the existing
source-provenance preparation. It updates the disposable native README and AGENTS
alongside the source changes. It does not apply the older account-specific router.
Never run it on a live installation or assume it matches installed version 1.1.433.

```bash
python3 authenticated_command_patch.py /disposable/pinned/checkout
node --test test_authenticated_command.cjs
```

Standalone Node tests require Node 24 for TypeScript stripping. Python discovery
checks this requirement and reports an explicit skip on older Node versions.
The dedicated `phantomview-authenticated-command.yml` workflow prepares a disposable
native checkout, runs actual Telegram/PhantomChat dispatch and NIP-17 gift-wrap
fixtures with Bun, includes existing channel regressions, and compiles the variant.
CI results must be observed separately from local checks; no inference provider or
production channel is contacted by these synthetic fixtures.

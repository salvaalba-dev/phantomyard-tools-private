# Private native conversation worker

Status: build-only variant over unchanged PhantomBot
`5af27060327ee8c53fe730dd8b98b6b305c62add`. Prepare only an offline disposable copy:

```bash
python3 native_conversation_patch.py /offline/pinned/phantombot
```

The patch verifies the complete reviewed source baseline before writes, adds the
dedicated `__conversation-worker` entry and updates the copied README and AGENTS
together. It does not modify upstream, patch an installed bot, publish a binary,
create a service or switch channel ownership. Reapplication/source drift fails.

## First supported slice

The protected [process wrapper](CONVERSATION_EXECUTION.md) supplies a fixed persona
and worker UID in its explicit environment. The native entry checks Linux and the
actual nonroot UID before reading bounded stdin or resolving persona configuration.
It runs before normal CLI credential migration/bootstrap. There is no public
trusted-input flag and no channel transport or signing operation in this entry.

The input is one compact UTF-8 JSON document matching the process wrapper's
ordinary-turn schema. An exact JSON round trip rejects duplicate fields and
alternate serialization; malformed/oversized input and unknown fields fail.
The persona must match the fixed binding, the direct conversation must equal its
canonical channel sender and reserved access commands are rejected.

This first native slice accepts **principal/private text only**. Relay, open,
shared, group, media and reaction contexts are not promoted to private retrieval;
unsupported contexts fail before inference. The transport library's broader
route schema does not imply native support for these contexts yet.

The UID/environment binding authenticates the execution role, not the human.
Verified human/channel authority still comes exclusively from the protected native
ingress and its peer-authenticated job handoff. A model account invoking this
entry directly cannot create issuer authority, issue a link or disable screening.
The model account must have no access to issuer credentials or reader sockets.

## Screening, memory and capabilities

The entry calls the real native `runAsk`/`runTurn` path with the configured persona
and persistent SQLite history under the existing `channel:conversation` key.
Persona files, native retrieval, index hooks and durable-fact enqueue behavior are
retained. Different job IDs do not create new conversations. History is not the
same as a complete channel experience: queue/control behavior, extraction drain,
notifications and all background inference still need separate integration.

Every request remains **untrusted for native screening**, even when its transport
tier is principal. The existing native JEV decision path and fallback judge remain
active. No JSON property or CLI option can set `trusted: true`. Consequently,
fact provenance retains the native untrusted-input floor rather than silently
claiming first-hand principal authority. This conservative behavior is deliberate
and requires validation with the final native ingress before cutover.

Only the configured native harness may answer or judge. Tools, MCP, managed
extensions, skills and prompt templates are disabled in this dedicated variant.
It does not reproduce a tool-capable normal daemon. The existing channel daemon
and its commands remain unchanged; do not replace their executable with this build.
The wrapper consumes the real native held marker and suppresses held stdout.
Other native diagnostics are discarded by the entry's stderr sink.

This worker intentionally sees its persona memory for ordinary private
conversation. **It must not replace the scoped PhantomView assistant executor.**
The dashboard assistant still requires the projection-only ephemeral-persona
variant and current-view ACL checks before inference and answer release. A human's
category or project scope is not widened by this ordinary conversation build.

## Credential and deployment prerequisites

Provision a worker-only persona/configuration/vault projection containing only
the reviewed model credentials and material it may read. The explicit process
environment and early CLI branch prevent ambient channel credential injection;
they do not sanitize a persona vault or config store that already contains those
credentials. Never point this variant at the current shared issuer store and
assume it is isolated. Review provider lookup, all process entry/fallback paths,
background scheduling, filesystem ownership and installed-release compatibility.

The full single-ingress host, actual channel delivery, native queue/control
integration, reviewed runtime manifest/publication and AU account/policy migration
remain pending. Native source compatibility is not installed-release parity.
The binary and digest produced by CI are validation outputs, not an approved
deployable artifact or evidence of real provider behavior.

## Validation

Private CI prepares the variant from the exact pinned source, checks source-drift
refusal and exercises real native screening, JEV wiring and persistent SQLite
history with synthetic harness/provider responses. It verifies denied contexts
never reach a model, private persona material remains available to supported
private turns, duplicate/oversized JSON is rejected, and a forged UID binding fails.
Existing memory and threat-judge regression suites run alongside these tests.
The baseline compiled executable is checked for refusal without its role binding.
No external provider, live persona store or real human/channel is contacted.

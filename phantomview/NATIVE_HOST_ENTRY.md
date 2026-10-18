# Offline native host entry preparation

Status: private build preparation, inactive. No AU service, channel, identity or
reader is changed. This completes the concrete CLI registration layer after the
[native startup binding](NATIVE_STARTUP_BINDING.md).

`native_host_entry.py` checks the full reviewed native source/dependency snapshot
at `5af27060327ee8c53fe730dd8b98b6b305c62add`, validates fixed deployment routes,
then prepares the existing command seam and registers those routes in the native
`run` command. Use a fresh, disposable source copy, never the installed binary or
a working tree containing other changes. Preparation refuses source drift,
existing generated helpers and reapplication. Filesystem write failures can leave
an incomplete disposable copy; discard that copy rather than trying to resume it.

```sh
python3 phantomview/native_host_entry.py /disposable/native/source /reviewed/routes.json
cd /disposable/native/source
bun install --frozen-lockfile
bun run build:x64
```

The committed `native-host-example.json` is a synthetic build/CI example, not AU
configuration. The operator supplies a reviewed non-secret deployment document
with exact persona/channel, scope, canonical HTTPS origin, distinct nonroot daemon
and reader UIDs and normalized Linux client/socket paths. It contains no keys,
human identities, categories or grants. A host build uses one daemon UID. Repeated
channel/persona routes are refused; several persona routes also require matching
reader endpoints/gates, because the existing identified gate is single-issuer.

Routes become a frozen TypeScript constant at build time. The daemon does not
load this JSON or an arbitrary plugin at runtime. Only the CLI `run` invocation
constructs its registry; programmatic `runRun()` retains explicit opt-in behavior.
The original `src/index.ts` is unchanged, preserving native credential bootstrap,
embedded harness startup and dispatch of the other CLI commands. The existing
process lock and `--if-not-running` behavior remain in the native run path.

Optional `conversationSocketPath`/`conversationGroup` fields additionally prepare
the [existing-persona transport](PERSONA_CONVERSATION.md). Channels for one persona
must agree on this descriptor. The listener starts inside the existing daemon
only after its run lock; native ask completion metadata is exposed without a
trusted-input bypass. Omission preserves the earlier link-only build behavior.
Signing uses the exact receiving listener's already loaded identity. Private
delivery uses that listener's existing transport. No service, poller, credential
store or replacement persona is created.

Whole-daemon trust is explicit: code with the daemon account's privileges belongs
to the accepted issuer boundary. The separate reader still checks kernel peers,
signed requests and current PhantomOrg authority. These routes cannot add a human
or grant ACL access. Native Nostr/JEV behavior remains on its existing paths.

## Upgrade and activation limits

A stock PhantomBot update replaces this optional private build and does not retain
the hook. Preserve the stock executable and recorded service configuration for
rollback; do not install an update blocker or claim a permanent integration API.
Review the new upstream source and rebuild before a future cutover. This is an
interim private integration pending a supported upstream registration surface.

CI prepares synthetic fixed routes and compiles the ordinary native CLI entry,
alongside actual channel/startup fixtures. Source tests prove unchanged bootstrap,
fixed registration and refusal without writes for invalid input or source drift.
Compilation and synthetic dispatch do not prove live issuance or human delivery.

Before AU activation, assemble the identified HTTP reader with the same gate used
by its handoff socket, bind its current private authority publication and reviewed
resource classifications, connect the issuing persona's existing conversation
transport, and capture exact artifacts and a reversible cutover. The prepared
report deliberately keeps `activation_ready: false`.

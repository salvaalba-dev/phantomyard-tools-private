# Native listener startup binding

The optional private source preparation now binds a fixed command route after
the existing native listener constructs its actual transport. It preserves the
standard daemon, normal model dispatch and native persona credential loading.
This is source integration, not a deployed AU callback or a CLI plugin loader.

`AuthenticatedCommandRegistry` retains its existing static registrations. A
second constructor argument adds fixed runtime registrations. Native startup
calls `bind` with the actual channel/persona and a lazy capability provider.
Unregistered listeners do not call that provider and keep ordinary dispatch.
Duplicate routes and native-control replacements are refused. Runtime routes
bind only once; a failed binding cannot retry with another identity or silently
fall back to a static/default route. Multiple listener accounts for the same
registered channel/persona are not supported by one runtime registration.

`nativeListenerRuntime` uses only the identity object already loaded by native
startup. Its frozen view exposes the public key, a signing operation and a bound
private-send operation. Neither secret key bytes nor the raw transport object
and its credential fields are passed to the runtime registration. Telegram
looks up the exact persona in the already loaded identity inventory; it does
not start that persona's PhantomChat listener to obtain a signing capability.
PhantomChat uses its own current listener identity. There is no default-persona
fallback, second credential store, second channel consumer or replacement
inference worker. A configured PhantomView route without an existing identity
or private-send capability is refused.

## Trusted host composition

`phantomViewStartupCommands` builds the registry from fixed host-owned route
descriptors containing persona, channel, scope, canonical origin, daemon/reader
UIDs and absolute one-shot client/socket paths. It composes the existing native
signer, exact signed-link callback and private control delivery with explicit
whole-daemon trust. It does not accept secret keys, sender identities, human ACL
claims, model UIDs or a browser-selected trust mode. PhantomOrg still resolves
the recipient and authority in the reader. Host configuration and capabilities
are trusted code within the accepted daemon boundary, not an account sandbox.

After exact-source preparation, a trusted programmatic host can pass the
registry to the existing native entry point:

```ts
import { runRun } from "./src/cli/run.ts";
import { phantomViewStartupCommands } from "./src/channels/core/phantomViewStartup.ts";

// reviewedRoutes contains fixed deployment descriptors, never message data.
await runRun({ authenticatedCommands: phantomViewStartupCommands(reviewedRoutes) });
```

This library does not register routes in the stock CLI or load an arbitrary
module/configuration file at runtime. The separate [offline host entry
preparation](NATIVE_HOST_ENTRY.md) now registers fixed reviewed build-time routes
in a disposable CLI variant while preserving its original bootstrap. The stock
binary remains unchanged. Identified reader/assistant assembly and a reversible
AU cutover remain required; source preparation does not activate AU.

## Validation

Standalone registry tests cover exact routing, copied registrations, bounded
construction, reserved controls, single binding and refusal after failure.
Native startup fixtures use temporary synthetic personas and check the exact
receiving persona's loaded signer without enabling its other channel. A native
composition fixture verifies both channels' signatures, recipient encoding,
explicit daemon argv and delivery through only the bound private operation.
Its one-shot reader response is synthetic; the existing separate signed-reader
and Linux peer-account suites cover actual verification and redemption. No
fixture contacts a production human, relay or inference provider.

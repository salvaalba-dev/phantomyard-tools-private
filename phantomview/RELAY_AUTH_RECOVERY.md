# Private relay AUTH crash repair

This change prepares a private build; it does not install or activate it. The
upstream revision, lockfile, daemon account and socket permission boundary stay
fixed. The existing socket guard continues to refuse every existing path.

## Failure and repair

The pinned nostr-tools 2.23.3 `auth()` drops the promise returned by `send()`.
A relay disconnecting while the signing callback runs therefore produces an
unhandled `SendingOnClosedConnection`, despite PhantomBot's outer auth guard.
The asynchronous promise executor also swallows signing errors without settling
the caller. The private overlay observes sign/send errors, rejects the outer
AUTH promise and removes its pending publish entry and timeout on send failure.
`send()` returns its connection continuation and rejects if the connection changed,
the websocket is missing/not OPEN, or the write throws. `publish()` and `count()`
reject their own promises and clear pending entries on send failure; a failed
subscription REQ closes the local subscription once and cancels its EOSE timer.
CLOSE is best effort and observes its send failure. Remote CLOSED frames still
perform local cleanup without echoing CLOSE. No global rejection handler is added.

A rejected AUTH clears its memoized promise so a transient signer failure can be
retried on the same connection. A late rejection from an older connection cannot
clear a newer AUTH promise or send the old challenge on the new connection.
Successful AUTH remains memoized. Success, negative OK and timeout behavior are
preserved.

The patch checks the version, exact SHA-256 of all 12 bundled relay copies and
exact method anchors before changing any file. It replaces directory entries
rather than truncating potentially shared package-cache hard links. The build
rechecks the patched hashes before compilation and embeds the overlay manifest
in its build receipt. Frozen dependency installation precedes this explicit
overlay; package.json and bun.lock are not changed.

## Verification

`test_relay_auth_patch.py` checks refusal on source drift/version changes,
duplicate anchors, reapplication, altered provenance and post-patch changes; it
also checks hard-link cache isolation. `relay_auth_regression.mjs` exercises the
actual installed abstract-relay and pool entry points with a synthetic websocket.
It reproduces the original crash before patching, then checks disconnect during
signing, transient retry, concurrent/reconnected AUTH, missing/closed websocket,
write failure, successful publish/count responses, negative OK, timeout and
subscription teardown. Its local observer is a unit-test double, not the daemon
guard.

`relay_auth_guard_integration.test.mjs` separately imports the real
`AuthGuardedSimplePool`, `guardRelayAuthRejection()` and signer from native commit
`5af27060327ee8c53fe730dd8b98b6b305c62add`. Under Bun it tests the actual automatic
AUTH path during a signing/disconnect race, idempotent guard installation,
successful signing/OK, and caller rejection followed by retry. Only the logger
and websocket are replaced. CI checks out those pinned source files and links
the patched disposable dependencies; the manual native build uses its actual
prepared source tree. The tests use synthetic keys and no external relay,
Telegram identity or persona store. They do not start the compiled daemon.

## Local build order and receipt requirement

After the usual reviewed source/routes preparation, install the unchanged frozen
dependencies, apply the overlay exactly once, run the checks, then verify before
compilation. From the repository root, the relevant commands are:

```sh
(cd native-source && bun install --frozen-lockfile)
python phantomview/relay_auth_patch.py native-source --manifest operator-build/relay-auth-patch.json
PHANTOMVIEW_NATIVE_SOURCE="$PWD/native-source" node --test --test-timeout=5000 phantomview/relay_auth_regression.mjs
PHANTOMVIEW_NATIVE_SOURCE="$PWD/native-source" bun test ./phantomview/relay_auth_regression.mjs --timeout 5000
PHANTOMVIEW_NATIVE_SOURCE="$PWD/native-source" bun test ./phantomview/relay_auth_guard_integration.test.mjs --timeout 5000
python phantomview/relay_auth_patch.py native-source --manifest operator-build/relay-auth-patch.json --verify
```

The native workflow runs the remaining daemon tests, stamps/compiles the build,
copies the artifact and invokes `native_build.py receipt`. Local receipt creation
now requires `operator-build/relay-auth-patch.json` and the matching patched
dependency tree in `PHANTOMVIEW_NATIVE_SOURCE` (default `native-source`), as well
as the existing toolchain/test/runner provenance. A missing manifest, a changed
overlay or changed dependency bytes must fail receipt generation; do not bypass
that gate or reuse a manifest from another build. `--root` changes the receipt's
build directory; set the source environment explicitly for a different checkout.
`installed:false` and `activation_ready:false` describe an uninstalled artifact;
they are not a systemd activation interlock or a record of live service state.

## Staging acceptance and rollback

Keep the existing Paco pilot drop-in disabled. Build only from the reviewed
private workflow after review/merge; its main-only dispatch guard is retained.
Use a disposable persona, independent Telegram identity, private state directory
and dedicated socket. Run the compiled Linux binary for at least 15 minutes and
several turns while injecting relay disconnects and running a nightly sweep.
Require no daemon exits/restarts or accumulating child processes. Separately test
clean shutdown and confirm that a live, foreign or unexplained socket is refused.

An abrupt kill can still leave a socket that requires inspection: this repair
deliberately does not weaken that fail-closed policy. Before any later activation,
stop the staging process, verify that no listener owns its dedicated socket and
inspect type, owner and identity before removing that staging socket. Never add
an unconditional production socket deletion hook.

Rollback stops only the staging instance and selects its previous artifact. No
Paco activation is authorized by passing these source-level tests. A separate
compiled-binary soak and reviewed cutover are still required. A future upstream
contribution can carry the transport fix independently of private host routing.

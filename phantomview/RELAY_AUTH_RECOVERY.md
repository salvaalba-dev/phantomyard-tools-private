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
`send()` returns its connection continuation so websocket write errors propagate
to the same caller. Success, negative OK and timeout behavior are preserved.

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
signing, signer failure, websocket write failure, successful OK, negative OK,
timeout and the existing fire-and-forget observation boundary. No real network,
keys, Telegram identity or persona store is used by those tests.

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

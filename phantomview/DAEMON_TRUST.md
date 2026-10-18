# Whole-daemon trusted issuance

Decision: the existing PhantomBot daemon is the trusted issuer, including persona
tools and code with that account's privileges. PhantomOrg owns human identities,
counterparts, scope and ACL; PhantomView applies that authority to the recipient
session. No separate model worker, channel daemon or credential store is required
by this mode. This source integration has not been activated on AU.

## Explicit configuration

The existing native callback accepts `trustBoundary: "daemon"` and an empty
`modelUids: []`. The fixed one-shot client receives `--trust-boundary daemon`
without a model UID inventory. The reader is constructed with
`DaemonPeerPolicy(issuer_uid)`, and the client uses
`DaemonReaderPolicy(receiver_uid)`. Both are explicit subclasses accepted by the
existing listener/client lifecycle; no listener starts on import.

Absent configuration keeps the isolated default. An empty inventory alone does
not activate daemon trust. Daemon mode rejects a model inventory rather than
claiming isolation it does not implement. A browser, message, signed payload or
human identity field cannot select the mode.

## Retained boundaries

- Linux kernel peer credentials authenticate the configured nonroot daemon
  account before the reader reads a frame. Other accounts are denied.
- The daemon verifies the configured reader account before sending an
  authorization or channel identity. The existing reader must use a different
  nonroot account; this adds no new model account or worker.
- Protected fixed socket paths, ownership/mode checks, bounded framing, deadlines,
  generic errors, direct-only context and no automatic retries remain unchanged.
- The actual native channel supplies the sender and receiving persona. PhantomOrg
  resolves the human; neither role names nor browser identity claims authorize.
- Canonical NIP-01 IDs, Schnorr signatures, issuer allowlist, freshness, replay
  cache, exact NIP-98 tag/payload binding and locked single-use fragment grants
  remain in the unchanged verifier. Existing recipient revision checks remain.
- Private control delivery avoids the ordinary reaction recorder and requires
  transport acceptance. Acceptance does not establish that the human read it.

The kernel check identifies an account, not a unique daemon PID or a particular
Telegram/PhantomChat message. All code with that account's privileges is within
the accepted trust boundary and could assert another sender if compromised.
Nostr/JEV retain their existing native functions; neither is presented as a new
process-isolation mechanism. This limitation is explicit, not an isolated-mode
claim retained after removing a guard.

## Verification and deployment status

Component tests check opt-in behavior, preserved isolated defaults, malformed
configuration, wrong-peer denial before frame reads and native flag propagation.
The disposable Linux account job additionally uses real kernel peer credentials
and signatures to deny an unrelated account, accept the trusted daemon account,
and redeem the resulting identified recipient session. Its temporary numeric UIDs
and synthetic organization never provision production accounts or contact humans.

Before AU activation, assemble the trusted native startup with its actual signer
and private delivery transport, bind the existing reader to its private current
PhantomOrg publication and filtered backend, and record exact artifacts and
rollback. This source change starts no service, grants no live socket access and
does not enable the native assistant. The legacy isolated mode remains available
for installations that independently require that stronger boundary.

## AU read-only follow-up, 2026-10-18

The selected administrative terminal was checked separately from the unrelated
domain terminal. No configuration, permissions, process or service was changed.
The installed PhantomBot reports `1.1.433`; its selected service is active under
`pb-paco`. The existing viewer is active under `aunited`. Those existing separate
accounts fit daemon/reader verification without adding model execution accounts.

The reader entrypoint still has SHA-256
`5c501b508f842b05afa02242d341af9db4d5a9a32de1f2feb55eacc8b60f5d2c`.
The authoritative source still has the approved declaration hash
`29052cfb4ae57dffb9dc0db6d882e8ce02d247b3ea1eb6702d5e54961566697a`;
the private publication reports matching organization revision
`4af4987bc07e01980efdf6b422c4339df96f86aeebd2c9df630c8b415085ae43`.
The collection timer is active; its oneshot collector was inactive between runs.
These observations alone do not establish publication freshness or callback wiring.

The tested native patch targets revision
`5af27060327ee8c53fe730dd8b98b6b305c62add`; a version string does not prove that
the installed binary matches that source. Assemble and review a compatible host
artifact before changing the running daemon. This follow-up is compatibility
evidence, not a deployment or identified-assistant acceptance test.

## Publisher provenance resolved, 2026-10-18

A subsequent publisher-metadata check resolves the source-parity question above.
The official `v1.1.433` release asset `phantombot-v1.1.433-linux-x64` has SHA-256
`66b287ab0aeeb7d800fe5d8eb142be5d95528d1bfa0fa2b3df3ada7eb4df9339`, matching
the installed AU binary observed in the read-only check. Its tag and successful
release build both resolve to the already reviewed source revision
`5af27060327ee8c53fe730dd8b98b6b305c62add`. The baseline is therefore the installed
release, not a different native revision. The unmodified official binary does
not contain the private command seam or its host registration.

A separate live read-only check confirmed the asset size (`109774816` bytes),
the on-disk digest and the current selected daemon process image digest against
that same published asset. It did not inspect process arguments, environments,
credentials or another installation. These are point-in-time observations,
not a persistent process-integrity monitor.

`native-release-review.json` records the public release asset and build evidence;
it contains no organization data. This is publisher metadata, not an independent
reproducible-build attestation. Recheck it if the installed artifact changes.
For a quiescent offline regular-file copy, run:

```sh
python3 native_release_review.py /offline/phantombot
python3 native_host_review.py /offline/phantombot-source --trust-boundary daemon
```

The first command checks bounded binary size and SHA-256 without executing it;
the second checks the source/dependency snapshot. Neither downloads code, changes
the installed daemon, verifies the currently running process image or activates
access. A matching binary report deliberately keeps `activation_ready: false`.
Native startup registration with the existing signer/private channel transport,
identified reader assembly, assistant transport and reversible cutover still
remain before end-to-end activation. This check does not reinstate the retired
issuer/model account split.

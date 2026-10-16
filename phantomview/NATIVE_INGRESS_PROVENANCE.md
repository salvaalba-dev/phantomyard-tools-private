# Native ingress provenance prerequisite

Status: private build-only patch over pinned PhantomBot source
`5af27060327ee8c53fe730dd8b98b6b305c62add`. This is a prerequisite for the isolated
native host, not an implementation or activation of that host.

Source inspection found that normalized Telegram messages discard API message
ID/date. PhantomChat retains an application delivery ID, which may come from an
inner text envelope, but does not carry canonical rumor time to its dispatcher.
Neither shape directly supplies the [access command](NATIVE_ACCESS_COMMAND.md)
with source-owned ID/time for freshness and duplicate checks.

`native_ingress_patch.py` adds optional immutable `sourceMessage: { id, sentAt }`
metadata without changing existing delivery/receipt IDs or ordinary dispatch:

- Telegram takes only API `message_id` and `date`, requiring positive safe
  integers. The update ID, quoted-message ID and text cannot replace them.
- PhantomChat takes the canonical inner rumor ID and `created_at` after the
  existing verifying unwrap, which checks signatures/sender binding and canonical
  rumor hash. Both NIP-17 and v2 unwrap paths retain that boundary. App-envelope
  IDs/timestamps and randomized outer-wrap timestamps are not freshness inputs.
- Missing, fractional, unsafe or malformed source values produce no metadata.
  Do not replace an absent source timestamp with receipt time. Normal messages
  still parse and keep their previous behavior.
- Metadata does not assert principal authentication, a direct conversation or
  an ACL grant. Group routing and the server-side explicit allowlist remain
  independent mandatory checks. The future native adapter must use source
  metadata, not the legacy application receipt ID, when constructing a command.

## Disposable patch preparation

The patch checks normalized UTF-8 SHA-256 values for all five changed existing
files before writing. It verifies exact replacement counts and refuses a preexisting
helper, unknown source drift or reapplication. It updates the copied native
`README.md` and contributor `AGENTS.md` together. It does not fetch source, install
a binary, alter upstream or write a live checkout. This is validation before
writes, not a transactional rollback guarantee if a later filesystem write fails.

```bash
python3 native_ingress_patch.py /disposable/pinned/phantombot
cp native_ingress_runtime.test.ts /disposable/pinned/phantombot/tests/phantomview-ingress.test.ts
cd /disposable/pinned/phantombot
bun install --frozen-lockfile
bun test tests/phantomview-ingress.test.ts tests/channels-telegram.test.ts tests/channels-phantomchat-channel.test.ts
bun run build:x64
```

Do not run those commands against AU's installed source/runtime. The pinned source
is distinct from the inspected AU worker revision; no installed-release parity is
implied by a successful build.

## Validation and remaining work

Python tests prepare temporary copies and check unknown-source and existing-file
refusal without writes. They require the pinned checkout, optionally located by
the test-only `PHANTOMVIEW_NATIVE_SOURCE` environment setting; otherwise they skip.
The dedicated Linux CI job always checks out the exact revision, supplies that
setting and runs these tests before modifying its disposable source copy.

Native tests exercise the actual Telegram parser and PhantomChat listener with
real in-memory gift-wrap signing/decryption. They test malicious app-envelope
ID/time/sender claims, plain NIP-17, tampered signatures, missing provenance,
groups/media and immutable metadata. Existing channel regression suites and
baseline compilation run in the same job. Fake relay transport prevents real
network channel activity. This increment does not claim new v2 runtime test
coverage beyond the unchanged verifying unwrap route.

The next implementation must connect an isolated native host to these adapters
and the protected command handler, preserve channel checkpoint/cancellation
lifecycle, forward ordinary conversations to an isolated execution path and
verify every model/fallback entry point. Replacing normal channel ownership needs
an explicit reversible cutover; never run a second poller beside Paco. Until then,
AU, its normal conversation, policies and services remain unchanged.

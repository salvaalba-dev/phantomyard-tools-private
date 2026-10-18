# Published identified reader assembly

Status: private local/source integration, not activated on AU. `PublishedReader`
connects the existing components without another inference worker, collector,
identity store or ACL database. Import and construction start no HTTP/IPC listener.

The trusted host supplies one `PublishedAuthority`, a protected reviewed projection
directory, the fixed issuing persona and its public signer allowlist, explicit
HTTPS origin/loopback port, native daemon UID, socket path/group and an existing
metadata-only `Ledger`. There is no environment discovery or browser configuration
endpoint. The [protected launcher](READER_LAUNCH.md) now supplies the optional
JSON host entry; production still needs an explicitly reviewed launch/cutover.

```python
from authority_publication import PublishedAuthority
from identified_reader import PublishedReader
from session_audit import Ledger

authority = PublishedAuthority(
    "/var/lib/example-view/authority", "/var/lib/example-view/reader/index.json",
    "example", "/opt/example/org.yaml", max_age=600,
)
reader = PublishedReader(
    authority=authority, projection_root="/var/lib/example-view/projection",
    actor="coordinator", identities=reviewed_public_keys,
    origin="https://view.example:8790", port=8790,
    issuer_uid=12001, socket_group=12001,
    socket_path="/run/example-view/reader.sock",
    audit=Ledger("/var/lib/example-view/audit/sessions.sqlite"),
)
reader.serve()
```

All coordinates above are synthetic. The operator must provision paths, ownership,
group traversal and protected publication permissions before launch. `serve()`
requires Linux and distinct nonroot reader/daemon accounts under explicit
whole-daemon trust. The existing protected listener performs kernel peer checks.
HTTP binds only loopback; an existing HTTPS proxy must preserve the established
origin/host boundary. No proxy, certificate, account or service is installed here.

## Shared authority and session path

`PublishedAuthority.snapshot()` returns the snapshot validated against that call's
fresh private publication and index. It uses the existing stable reads, source
binding and explicit lease; it never opens the original organization source.
`PublishedProjection` uses these current organization/snapshot loaders, preserving
approved classifications and refusing changed or missing approval generations.
Construction and serving both preflight current authority and projection.

Exactly one recipient gate is passed to the filtered backend, HTTP handler and
private handoff listener. Signed native issuance binds the verified requesting
human and issuing persona through PhantomOrg. HTTP cannot issue links or supply
identity claims. Redemption requires an existing identified recipient binding;
ordinary signed-but-unidentified legacy grants are refused. The underlying
signature, freshness/replay, locked single redemption, fragment and cookie designs
are unchanged. The generic legacy gate remains available to existing callers.

Each data request revalidates current policy and reviewed sources before returning
filtered menus, graph endpoints, counts, search or resource details. Legacy raw
index/KB, configuration, update and assistant endpoints remain closed. Publication
expiry, identity changes and stale source approvals deny access without fallback.
The collector's existing cadence and explicit lease still bound revocation delay.

One serve attempt is allowed per instance. Handoff startup precedes HTTP serving;
failures and shutdown close both sockets and discard in-memory sessions/bindings.
Normal host shutdown should call `reader.server.shutdown()` from a different
thread, then wait for `serve()` to return. A new instance requires fresh links.
Audit records are metadata only, not transcripts or a tamper-proof log.

## Evidence and remaining work

Real-signature component tests exercise private publication, approved projection,
HTTP redemption, filtered reads/search, replay, expiry, logout/revocation and
policy/source changes. Their sender contexts are synthetic trusted inputs.
The explicit disposable Linux account job additionally assembles this reader,
denies an unrelated process account, issues through the real daemon socket and
redeems through HTTP, verifying filtering and cleanup. No live channel is used.

The assistant transport, extra modules, content classification approval and AU
deployment remain separate. This increment exposes issuer routing metadata but
does not claim a connected conversation or enable the historical restricted
assistant worker. It does not modify the stock native CLI or any live setup.

Follow-up: the optional [existing-persona transport](PERSONA_CONVERSATION.md) now
connects through an explicit `conversation_socket` host argument. The default
reader still starts without an assistant. This source follow-up does not activate
AU or relax publication/classification prerequisites.

# Scoped consultation boundary

`ScopedAssistant` is an inactive, synchronous operator library between the scoped
resource backend and a future isolated native executor. It does not add a browser
route, queue, service, native hook, worker configuration or live deployment.

```python
assistant = ScopedAssistant(scoped_backend, protected_persona_executors)
result = assistant.consult(session_headers, question, resource_ids=visible_ids)
```

## Trusted routing and evidence

The executor registry is a protected operator mapping from exact persona IDs to
callables. Only the persona bound to the currently authenticated recipient can
select a callable. A missing binding fails closed; there is no default-persona or
legacy-worker fallback. A question or focus ID cannot set human identity, category,
scope, persona, worker address or credentials. Registry configuration must remain
outside browser/model writes.

The existing `ScopedBackend.state` authorizes before opening records, relationships
or dependencies. Project sessions cannot acquire organization or other-project
records. Unknown/denied focus IDs have the same unavailable response. No denied
payload is loaded or forwarded. Up to eight unique focus IDs can prioritize already
visible records. Remaining visible records are ranked by exact normalized question
words across all resource kinds, independently of the selected UI menu.

Questions are limited to 1,800 characters. The serialized UTF-8 JSON envelope is
limited to 12,000 bytes, with at most eight evidence excerpts of 1,000 characters.
Byte-budget exclusions and truncated excerpts set `evidence_limited`. Every
question and evidence item is explicitly untrusted; record strings are data, never
instructions. `complete_corpus` remains false even when no match is found. These
are selected classified projection records, not a claim that all organization KB,
files or native persona memory were searched. There is no previous-turn history.

The executor receives a detached envelope containing organization, scope, persona,
question and bounded evidence. It receives no cookie, raw channel identity, global
catalog hash, hidden count or classification-changing capability.

## Dispatch, screening and delivery

A protected `Ledger` is mandatory and cannot be replaced during a consultation.
New metadata-only events are `scoped_assistant_requested`,
`scoped_assistant_dispatched` and `scoped_assistant_finished`, correlated by a fresh
request UUID with `mode: scoped-consultation`. No question, answer, payload or raw
identity is stored. Audit failure blocks dispatch or response release.

Current recipient and authorized-view revision are checked after initial audit,
immediately before execution, after execution and after terminal audit. Logout,
expiry, authority changes and visible source changes discard the answer. This is
synchronous revalidation, not a transaction spanning external policy writers. If
revocation or failed storage prevents final auditing, the request can remain at
its last recorded stage; this library does not manufacture a terminal receipt or
claim a complete forensic transcript.

Native JEV screening remains mandatory in the trusted executor. The library reuses
`assistant_worker.ConsultationHeld`; only the trusted native adapter may raise it
from actual native screened-hold completion metadata. A model-produced JSON field
is never accepted as proof of screening. Held consultations release empty text.
Provider errors, invalid outputs and answers exceeding 64,000 UTF-8 bytes produce
failed results without partial text or exception details. Successful answers reuse
the existing credential-pattern redactor and are capped at 20,000 characters. The
redactor is not a replacement for ACL, JEV or secret review.

## Required native adapter work

The supplied callables in unit tests are synthetic executor doubles, not evidence
that a live model has passed JEV. The separate
[dedicated native executor](NATIVE_SCOPED_EXECUTOR.md) now supplies an inactive
adapter and pinned build variant; it has not been deployed.
Before supplying one, verify all of the following against the installed runtime:

- Exact persona and organization routing with independently protected credentials.
- Native untrusted-input/JEV screening and genuine hold propagation.
- Zero tools, MCP, extensions and skills; no file writes or mutations.
- No inherited unfiltered persona memory, history, prompt files or cross-session
  model state that could bypass the supplied resource ACL.
- Native-channel/model isolation, transport authentication, cancellation, timeouts,
  bounded concurrency and per-session/global inference budgets.

The existing AU worker is fixed to an analysis persona and is not silently reused.
The native channel isolation limitation in
[verified-channel integration](VERIFIED_CHANNEL_INTEGRATION.md) remains unresolved.
The library itself has no queue, persistent transcript, automatic retry, request
deduplication or rate limiter. Each explicit call is a new consultation; a future
transport must implement those lifecycle controls before exposing it to humans.

AU, its current assistant, grants and other setups remain unchanged.
Organization-wide ingestion ACL enforcement remains deferred F01.

## Validation

Synthetic tests cover organization/project isolation, denied/unknown focus IDs,
trusted persona routing, empty evidence, UTF-8 bounds, detached inputs, held and
failed execution, credential-pattern redaction, logout and source/policy/audit
changes during dispatch or delivery, and absence of a legacy fallback.

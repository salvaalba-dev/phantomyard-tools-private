# Scoped consultation transport

`ScopedConsultations` connects the scoped assistant to an opt-in bounded queue.
Pass it as `scoped_consultations=service` to `serve` with the exact same scoped
backend and identified gate. The protected executor registry must implement
`run(envelope, cancelled=event)`; plain uncancellable callables are rejected.
Scoped mode never constructs the legacy bridge client from environment settings.
There is no CLI activation, new credential or live AU change. The opt-in
[scoped widget](SCOPED_WIDGET.md) uses this transport when explicitly configured.

## Closed HTTP surface

- `POST /api/scoped-assistant/jobs` accepts exactly `request_id`, `question` and
  `resource_ids`: a canonical UUID, 1–1,800 characters and at most eight unique
  opaque IDs already visible to this session.
- `GET /api/scoped-assistant/jobs/<uuid>` returns only the owning session's job.
- `DELETE /api/scoped-assistant/jobs/<uuid>` cancels that job and clears its answer.

The existing origin/host boundary applies. Query/fragment fields, duplicate JSON
keys, JSON over 8,192 bytes, actor/scope overrides and unconfigured routes fail
closed. Signed issuance/redemption/logout is unchanged. Legacy assistant,
configuration and approval/publication routes remain closed. There is no job-list
endpoint, global queue metadata or browser-selected worker address.

Submission returns HTTP 202 with a random job ID, status and optional result.
An exact same-session repeat returns that job with HTTP 200 without another
inference. Conflicting reuse or a changed authorized view returns HTTP 409.
Another session cannot read/cancel a known job, even for the same human/persona.

## Bounds and lifecycle

The service allows one running consultation, four pending consultations, at most
40 retained jobs, 10 accepted consultations per session per hour and 40 globally
per hour. Cancelled work consumes quota; exact retries do not. Full queues/budgets
return HTTP 429. These in-memory limits and idempotency state reset on restart;
they are not distributed or durable accounting.

Admission binds the verified recipient and visible-view revision. Before execution
the basis is revalidated; the assistant checks again before inference and delivery.
Polling a completed answer rechecks current scope, sources and authority. Changed
views never release cached answers. Questions/cookies are cleared from jobs after
execution. Answers remain in process memory only until cancellation, expiry or
shutdown, for at most 30 minutes. No question/answer/cookie is written to audit.

A watcher checks session eligibility and a 120-second total deadline (including
queue time) every 100 ms during execution. Logout, policy invalidation, expiry,
deadline and shutdown signal cancellation without browser polling. Cancellation
is cooperative at the executor interface. The native adapter exposes the event
to the existing process poll loop, which terminates the process group and retains
its forced-termination fallback. Late output is discarded. Shutdown cancels all
work and clears retained answers; executors must honor the cancellation contract.
Stdin writing runs separately from the deadline loop, so a child that never reads
its prompt cannot block cancellation by filling the operating-system pipe.

Metadata events `scoped_assistant_queued`, `scoped_assistant_cancelled` and
`scoped_assistant_delivered` correlate request/job UUIDs. Returning a retained
result, including an exact retry, requires a healthy audit write and a fresh
authorization check. Admission audit failure starts nothing. Cancellation still stops
work when its audit write fails, while the caller receives an audit failure.
Revoked sessions can lack terminal receipts; no complete forensic transcript or
tamper-proof archive is claimed.

## Validation and activation

Tests cover real HTTP submit/poll/cancel, retries, ownership, origin/identity/query
rejection, queue/session/global limits, source invalidation, audit failures and
logout/deadline/shutdown cancellation. A Linux-only test runs a disposable process
and verifies termination through the native adapter. Model responses are simulated.

The [scoped browser widget](SCOPED_WIDGET.md) now supplies explicit consultation
controls and a private capability-information route. Provision the reviewed binary and
manifest, isolated accounts, approved classifications and verified native channel
integration before deployment. AU and other setups remain unchanged.
Organization-wide ingestion ACL enforcement remains deferred F01.

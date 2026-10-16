# Scoped assistant widget

The generic scoped workspace now includes a compact consultation panel beneath
the navigation. It uses the opt-in scoped consultation transport exclusively,
never the public chat widget, a legacy assistant bridge or browser credentials.
It does not enable a service, native hook or deployment by itself.

After loading current scoped state, the client requests
`GET /api/scoped-assistant/info`. This origin-bound identified endpoint returns
only availability for the bound persona, its ID and the current scope ID. Without
the explicitly configured consultation service, the endpoint stays closed and
the composer is disabled. No private channel identity or global queue state is
exposed. Capability availability is configuration metadata, not a live model probe.

## Consultation flow

The panel shows the persona, request status, optional visible-record focus,
question and plain-text answer. Navigation is compact and scrolls independently;
long answers scroll within the panel so the composer remains accessible. The
record dialog offers **Ask about this record** after a fresh authorized read.
Selecting it sets one visible opaque ID as focus without starting inference.
Changing focus clears the previous answer and requests cancellation of old work.

**Ask** submits one canonical request UUID and the question/focus to
`/api/scoped-assistant/jobs`. Only explicit human submission starts inference.
Queued/running requests are polled at one-second intervals, with a finite polling
limit. Holds, failures and cancellations show fixed status messages and no supplied
response text. Completed output must match the request UUID, persona, scope and
current authorized-view revision and declare `complete_corpus: false`.

Questions, focus labels and answers use `textContent`; generated Markdown/HTML is
never executed or inserted as markup. There is no conversation history, local
storage, cross-session cache or new identity form. Existing signed fragment
redemption and HttpOnly session cookies remain unchanged.

## Retry, cancellation and invalidation

A network error or rate limit offers **Retry same request**, preserving the exact
UUID and body so the server can avoid duplicate inference. It does not auto-resubmit
or silently issue a new request. **Cancel** clears local state and requests server
cancellation. **Clear** also removes a completed retained server answer.

Refresh/search, logout, document hiding and page exit clear the panel along with
the workspace. Known jobs receive a best-effort keepalive cancellation request.
Submission responses arriving after reset are discarded and their returned job IDs
are cancelled. Submission requests are not aborted before the client can discover
their job IDs. If the network/page lifetime prevents that cleanup, the server still
enforces its session/deadline limits; client clearing is not proof of process
termination. Poll generations prevent late output from returning to the DOM.

Authorization failures, missing jobs, changed views or malformed/mismatched replies
invalidate the workspace instead of displaying a cached fallback. Workspace
failure now invalidates pending read generations too. Reopening the page requires
current scoped data; navigating between categories never grants a different scope.

## Validation and remaining work

Node tests exercise submit/poll, cancellation before submission returns, stale
polls, exact retries, holds/failures, response binding, rate limits, plain text and
unconfigured capability denial. HTTP tests cover the capability envelope and static
asset. Browser verification uses synthetic records, a synthetic executor and
loopback-only temporary sessions. No real provider, persona or JEV decision is used
for the visual preview.

AU remains unchanged. Deployment still requires reviewed artifacts/classifications,
isolated accounts and verified native channel integration. Organization-wide
ingestion ACL enforcement remains deferred F01.

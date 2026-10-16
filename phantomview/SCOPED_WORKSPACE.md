# Generic scoped workspace

When a trusted embedding supplies `scoped_backend=` to `phantomview.serve`, the
root page now serves `scoped-index.html` and the separate `scoped-ui.js` and
`scoped-ui.css` assets. The default reader keeps its existing frontend. No CLI
activation flag or AU configuration is added by this increment.

The scoped page accepts only the generic resource projection schema. It never
adapts a legacy snapshot or falls back to legacy APIs. Server authorization occurs
before payload loading; client menus, filters and graph effects are presentation,
not access checks. Public static files contain no private resource data.

## Visible workspace

Navigation comes from resource kinds actually present in the authorized response.
An organization view can contain departments, roles and people; a project view can
contain partners, objectives and tasks without organization or department menus.
Counts are derived from returned records, never a global inventory. An available
organization record supplies its display title; otherwise only the organization
identifier already supplied as session context is shown.

Cards and freshly fetched record details support the backend's declared resource
kinds. Details show the authorized structured data as text. Custom project widgets
and per-human layout preferences remain future work. Existing metadata adapters
do not yet collect every kind supported by the backend; project examples use
synthetic manually classified records, not an assertion of collector coverage.

The directed relationship graph includes visible endpoints only and is capped at
60 records. Hovering or focusing a node highlights that origin, downstream nodes
and flow lines; unrelated elements dim. Cycles terminate through a visited set.
Nodes support keyboard activation and fetch current details from the backend.

## Search and session behavior

Search always posts the query alone to `/api/search`, independent of the menu
section. The response now includes the organization, scope and policy/view
fingerprints already present in scoped state, alongside its authorized matches.
The UI replaces the workspace with those results, rather than mixing old counts
or records into a new search. Relationship-only matches remain readable without
adding endpoint cards that did not match the query. The graph is hidden in search
mode. Search still returns at most 100 matches and reports truncation.

Temporary access codes are redeemed through the unchanged fragment-only flow.
Fragments are immediately removed from browser history; credentials never appear
in requests as query parameters or browser storage. Reads use the existing cookie,
same-origin requests and no-store behavior. Logout waits for pending redemption
before revoking the session and cannot be cancelled by a visibility-triggered
read abort. This does not change issuance, signature verification or redemption.

Starting a refresh/search, logging out, hiding the document or leaving the page
clears displayed resources, graphs, counts, navigation and detail contents.
Failed session/source checks leave an empty workspace with a generic message.
Request generations and abort controllers prevent old read responses from
repopulating a newer view. Record reads also use an independent generation guard.
A hidden page requires refresh when returning; back/forward cache restoration
requests fresh data. Idle visible pages are snapshots of the last successful
request, not a promise of immediate revocation without another request.

No assistant, setup, history/export or publication route is enabled.
An optional [authenticated review service](AUTHENTICATED_REVIEW.md) now supports
private pending category-change proposals under explicit action grants. Without
that service, its routes remain closed and its dialog stays hidden.
The [offline review interface](REVIEW_INTERFACE.md) remains an operator workflow.
Approval consumption still requires independent current authority, source review
and publication checks. Native channel
isolation, deployment configuration and actual AU activation remain prerequisites
for expanded access. Organization-wide ingestion enforcement remains deferred F01.

## Validation

HTTP tests verify scoped root selection, public static assets, absence of legacy
bootstrap, global search context and unchanged denial of legacy/future routes.
Node behavior tests cover project-only menus, visible counts, strict schema checks,
relationship-only search and cycle-safe directed graph highlighting. Browser tests
use synthetic scoped data and verify details, cross-section search, highlighted
flows, unavailable-source clearing and logout revocation.

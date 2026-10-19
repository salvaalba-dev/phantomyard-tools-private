# Generic scoped workspace

The organization diagram uses right-angle connectors. The organization label
stays inside the upper-left of the diagram at the first reporting level and
remains clickable and connected. Solid green arrows point from a role to its
manager; dashed amber arrows indicate workflow or escalation destinations;
dotted lines indicate organization context without inventing a reporting parent.
The visible legend includes line samples and direction meanings. Connector routes
choose clear horizontal/vertical paths using the cards as obstacles. Workflow
arrows can enter the destination from its nearest clear side, including the right;
an outer lane is a fallback, not the default. Separate ports and lanes avoid shared
segments when space permits, and route selection penalizes crossings and detours.
A connection that cannot be routed safely is counted in a visible diagram warning.
Hover and keyboard focus
continue to highlight related cards and connections. This changes presentation
only; reporting data, session authorization and record-detail routes are unchanged.

The overview groups available records into aligned Persona, Human and Role
columns. Each persona row uses only published counterpart and role assignment
relationships; every linked name opens its current authorized record. Missing
associations are labeled explicitly. Visible humans and roles without a published
persona association remain in separate rows. Other record kinds appear in groups
below the directory. Section navigation and global search retain their existing
record views, and narrow screens can scroll the three columns horizontally.

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
An organization view can contain departments, roles and personas; a project view can
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

### Organization overview tree

When the authorized view includes an organization and roles or personas, Overview
uses a top-down organization tree. Reporting levels come only from `reports`
relationships (child role to manager role). Workflow/escalation links are dashed
and do not change reporting levels. Dotted organization-context lines connect
visible roots; they do not assert that a missing reporting edge means no manager.
Project-only views and individual sections retain the relationship graph.

Role cards join visible personas through `assignment` links, departments through
`membership` links (role to department), and humans through `counterpart` links
(human to persona). Names, role identifiers inside arbitrary payloads and hidden
records never establish these joins. Cards open the persona/role, human or
department's current detail endpoint. Hover and keyboard focus highlight the
reporting path, descendants and directly connected workflow links.

Unassigned personas remain separately visible without invented manager links.
Missing counterparts/departments are described as not visible. Cycles and multiple
managers are marked for review instead of choosing a parent silently. The diagram
is bounded to 60 cards and reports truncation.

To prepare the missing declared links, run the existing source adapter with
`--organization-links`. This is opt-in and produces an inert, unclassified draft.
It reads counterpart identities from the trusted PhantomOrg directory, includes
only selected visible endpoints, deduplicates existing assignments and retains
source/authority fingerprints. Each new relationship still needs classification,
review and publication through the existing process. This flag grants no access,
changes no existing approval and publishes no live records.

The enabled adapter mode is bound into the draft and approval fingerprints.
Approval, publication, review pages and subsequent source revalidation recompute
that exact mode. Approvals without the optional mode retain their legacy source
fingerprints. An adapter option never substitutes for explicit resource decisions.

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

Setup, history/export and publication routes remain closed. The optional
[scoped assistant widget](SCOPED_WIDGET.md) uses its own explicitly configured
consultation routes; it never falls back to the legacy assistant.
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


### Fit-to-panel organization diagram

The organization tree measures its panel width and arranges compact cards in up to
four columns, wrapping larger reporting levels into additional rows. It preserves
the published reporting hierarchy and does not change records or authorization.
The organization remains a linked context card at the upper left. A resize rebuilds
coordinates rather than shrinking a fixed-width drawing or requiring horizontal
scrolling. Compact cards retain linked personas, roles and department badges;
full linked counterpart and department details appear below the diagram on hover
or keyboard focus. Narrow layouts move secondary card details into that row.

Solid reporting branches may share a bus only for the same actual manager. Dots
mark those real junctions. Workflow routes remain independent, use right-angle
turns, avoid card interiors and penalize crossings and shared segments. Crossings
without a dot do not imply a relationship. Dense cases that cannot be routed
safely retain the visible missing-route diagnostic and linked source records.
By default the selected persona's workflows are shown; the All workflows checkbox
reveals the complete visible workflow set. Selection and that preference survive
panel resizing. All data still comes from the server-authorized projection.

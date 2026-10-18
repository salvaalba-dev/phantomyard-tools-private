# Existing-persona conversation in PhantomView

Status: private source integration; no AU daemon, reader or conversation listener
is activated. This replaces neither native personas nor their collaborative memory.
The historical projection-only assistant remains a separate optional mode.

## Native execution

Optional fixed host routes can declare `conversationSocketPath` and
`conversationGroup`. All channels for a persona share that exact descriptor.
The existing daemon starts one bounded local socket per configured persona after
its run lock and closes it before native cleanup. An unconfigured build changes
neither `ask` nor daemon lifecycle. The original CLI bootstrap remains unchanged.
No additional resident inference process, credential store or channel poller exists.

The native listener calls the existing `runAsk` with an explicit served persona,
history enabled, a server-owned web conversation ID and the normal persona config,
memory, harness and tools. It adds no trusted flag and does not disable JEV.
This public ask path still screens input as untrusted; it is not identical to
an authenticated principal's phone-channel execution. Native holds may therefore
occur and remain visible as holds rather than being bypassed.

A small optional completion observer reads `done.meta.screenedHold` in native
code. Completion is released only after successful `runAsk` return. Generated
answer text, including quoted hold markers or JSON, cannot assert this status.
Existing calls without the observer preserve their documented behavior.

## Reader connection and trust

Pass the reviewed fixed socket path as `PublishedReader(conversation_socket=...)`.
The reader uses the session issuer, never the host default or a browser persona.
Before sending question bytes, its production Python client checks socket
ownership/modes and the daemon's Linux kernel peer UID. There is no network or
legacy assistant fallback and no automatic native retry after an ambiguous error.

The native listener authorizes callers through a protected parent and a `0660`
socket with an operator-selected group. It does **not** attest each caller UID:
every process able to connect through that group belongs to the trusted reader
boundary. Provision and review the group membership and parent ownership before
deployment; do not silently add users or widen an existing group. Requests are
refused until final socket ownership and permissions are installed. Existing
signed-link issuance still uses its separate kernel peer and signature checks.
The native networking runtime owns its socket pathname until shutdown. Stop it
before replacing that pathname; this is not the Python listener's guarded
replacement-file cleanup contract. Startup never overwrites an existing path.

Each request is bounded and explicitly correlated. The browser cannot select a
command, filesystem path, trust level, native thread or persona. The native
socket contains no human/channel impersonation API. A compromised authorized
reader could still submit native questions; this is part of the declared trust
boundary, not a new per-request Nostr authentication claim.

## Authority, context and lifecycle

The existing identified queue revalidates session ownership, current PhantomOrg
authority and the displayed evidence revision before dispatch and delivery. It
retains bounded rate/queue limits, cancellation, expiry, deduplication and metadata
audit. Its historical `/api/scoped-assistant/*` URLs serve the explicitly reported
`persona-conversation` mode; a browser cannot enable that mode itself.

Only explicitly selected, currently visible records are supplied as supplemental
untrusted evidence. A question without selection forwards no organization snapshot.
Native retrieval remains the persona's existing collaborative knowledge model;
this integration does not enforce record-level viewer ACL inside native memory
or tools, or claim the answer uses only the displayed data. The web UI labels this
mode accordingly. Native tool actions retain existing capabilities and safeguards;
the viewer does not add write grants or promise tool-less execution.

An explicit `policies.phantomview.human_category_limits` entry disables native
conversation for that human, including queue submission, dispatch and delivery.
The native persona cannot enforce a human-specific category restriction inside
its collaborative memory or tools. The reader reports the assistant unavailable
and does not select a fallback. Unrestricted counterpart sessions retain the
existing native behavior. See [Human category limits](HUMAN_CATEGORY_LIMITS.md).

Threads are derived server-side per session, organization, issuer and scope. They
persist in native conversation history but do not merge with the phone transcript.
Logout/revocation suppress pending web delivery and cancellation disconnects the
native request. Cancellation cannot undo an action or persisted history already
produced by the native persona. Audit is metadata only; it excludes question,
answer, cookies, link grants and raw channel identifiers.

## Verification and deployment boundary

Queue/HTTP/UI tests cover fixed routing, selected evidence, thread ownership,
deduplication, cancellation and typed holds. Native tests exercise the real local
socket, completion observer and existing ask regressions with synthetic harnesses.
The production Python client is exercised under a dropped disposable reader UID
against the native socket. No live relay, human or inference provider is contacted.

AU still requires reviewed group/socket coordinates, current resource approvals,
the compiled compatible native artifact, reader launch configuration and a
reversible cutover. Stock PhantomBot updates do not retain this private integration;
the same source review/rebuild requirement as the link hook applies.

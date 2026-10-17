# Verified human access: integration status

The [collaborative viewer plan](COLLABORATIVE_VIEWER_PLAN.md) now governs delivery.
This document preserves channel-authentication findings and earlier experiments;
it is not a mandate to deploy their isolated replacement-worker architecture.
Verified sender-to-session binding is still required. That transport question is
separate from adding human/organizational ACL logic inside PhantomBot.

Status: private, tested primitives; **not enabled on the AU reader or daemon**.
The current assistant remains the bounded, tool-less PhantomView analysis pilot.

The inactive [native command seam](NATIVE_ACCESS_COMMAND.md) now supplies reserved
command consumption, fixed binding, bounded duplicate/attempt handling and
direct-only delivery through the existing handoff client. It does not supply the
isolated native channel host or change the shared PhantomBot dispatcher.

## Source inspection

The inspected PhantomBot source is commit
`5af27060327ee8c53fe730dd8b98b6b305c62add`. AU currently runs version 1.1.433;
the inspection does not establish that this source is byte-identical to its binary.

- `src/channels/core/engine.ts` checks Telegram `msg.senderId` against an
  explicitly configured, nonempty allowlist before the slash-command path.
  An open bot may answer a stranger but does not authenticate a principal.
- `src/channels/phantomchat/server.ts` authorizes the proven sender as a tier.
  Only the trusted tier qualifies; relay authorization does not authenticate the
  relayed end user. Group messages must not issue personal dashboard links.
- `src/channels/core/types.ts` keeps `senderId` distinct from `conversationId`.
  A conversation ID is not a sender ID in a group.
- The existing shared slash dispatcher has no supported PhantomView plugin hook.
  A native, opt-in pre-model integration is still required. Merely installing a
  persona shell tool or reading `PHANTOMBOT_CONVERSATION` cannot supply this proof:
  a model-driven shell can choose its own arguments and environment.

Do not replace the shared PhantomBlog access protocol, add recipient tags to its
signed event, expose a recipient-setting HTTP endpoint or allow a model to choose
the human. The browser continues to receive only the single-use fragment grant.

## Prepared implementation

`channel_identity.py` resolves the verified adapter's Telegram ID or canonical
PhantomChat npub to exactly one human in the private organization source. For
PhantomChat the native adapter must use its existing NIP-19 encoder on the proven
sender hex; this module does not verify a Nostr envelope or signature itself.
It rejects groups, relay/open-bot contexts, email-only claims, unknown humans,
ambiguous channel identities and ordinary humans using another counterpart.
Category zero remains an independent human information grant.
When explicit scope mode is configured, the verified adapter must also bind a
permitted `scope_id`. Project/department recipients stay inside that scope;
organization sessions still require explicit grants for other scopes. The private
[scope/action model](SCOPE_ACCESS.md) separates information access from modification
capabilities. Its source definitions and grants participate in recipient revision
checks. No browser-selected human or capability becomes authoritative.

`identified_access.py` provides a separate, inactive `IdentifiedGate`:

1. A future trusted adapter calls `issue_identified` in process with its actual
   channel context and a normally signed issuer authorization.
2. The unchanged PhantomBlog verifier issues the five-minute grant. The adapter
   associates its digest with a recipient record in memory. No human identifier
   enters the URL, signed tags or signed payload.
3. The existing locked, single-use redemption creates a recipient-bound cookie
   session. Legacy signed links still create analysis-only sessions.
4. Every extended request must call `identified_scope`, then authorize each
   resource using the returned private directory before loading it. Both grants
   and registered channel identities contribute to the revision check.
5. Expiry, logout and revocation clear the recipient association. A restart
   discards grants and sessions as before. A failed session creation does not
   consume the underlying grant.

The context parameters are an **in-process trust contract**, not authentication
by themselves. Registering them as a public JSON endpoint would be unsafe. The
adapter is deliberately not imported by the reader and not selectable by CLI.
An authenticated IPC implementation must keep the channel's authority away from
model-controlled tool processes; a shared secret that those processes can read
would not establish that separation.

`trusted_handoff.py` now provides an inactive Linux Unix-socket boundary using
kernel peer credentials. It accepts only a separately provisioned native issuer
account, rejects model/unknown accounts before reading claims, and retains the
existing signed-link protocol. Persona and origin come from the reader's gate.
See [private handoff](TRUSTED_HANDOFF.md) for the account-isolation contract,
bounded frame protocol, tests and remaining native-hook requirements. It is not
imported by the live reader, and no listener or channel service has been enabled.

`handoff_client.py` supplies the inactive native-side client: fixed private socket,
reader kernel UID verification before sending context, bounded replies, exact
HTTPS fragment-link validation and no automatic retry. The dedicated isolated
handoff CI job tests real signing and separate kernel accounts on a disposable
runner. This does not install or authenticate the missing native message hook.

`reader_handoff.py` connects that boundary to the reader lifecycle through an
explicit embedding argument. It requires the same `IdentifiedGate` object as HTTP
redemption, closes the HTTP socket on startup failure and cleans up its own socket
on shutdown. The isolated test redeems the native-issued grant through the real
HTTP handler and checks its human/scope and single-use behavior. The default CLI
does not construct this runtime and the AU reader is unchanged.

The inspected daemon still hosts channel listeners and model turns together.
Its contributor guidance rejects a new per-persona supervisor; a shell tool in
that same account cannot supply isolated native authority. The native ingress or
model-execution isolation design remains unresolved and must be reviewed before
activation, without introducing a competing channel listener.

`scoped_backend.py` and `scoped_http.py` add an opt-in resource projection and
closed API boundary. They authorize before record reads, graph edges, counts and
search, then revalidate source, catalog and session state. Directory revisions now
include category-definition meaning changes. Legacy snapshot, KB and assistant
routes cannot be reached through scoped dispatch. This is a new resource schema;
it has no automatic legacy-export adapter or live activation. See
[scoped backend](SCOPED_BACKEND.md) for the remaining source/UI/worker boundaries.

`scoped_knowledge.py` adds the inactive retrieval boundary over an identified
session. It calls `identified_scope` before retrieval, checks each resource with
the private directory before opening or searching its payload, and rejects draft
catalogs. Approved entries bind the exact organization, actor, relative KB path,
category, optional project and full exported payload digest. Category 0 is never
a resource classification. Explicit secrets remain excluded for every human.

The fixed private store retains collector exclusions and requires each opaque
note ID to remain present and searchable in the current selected snapshot.
Changed, removed, truncated, mismatched or unavailable payloads cannot supply
evidence. The retriever rechecks the identified session, catalog revision and
selected payloads before returning bounded, explicitly untrusted excerpts. It
never forwards raw channel identifiers or describes denied documents. Empty
results do not claim that the whole organizational corpus was searched.

`prepare_review` automates fingerprint collection for existing exact-folder
suggestions. It produces only a draft, with every resource's secret review unset.
Changing the top-level status alone cannot make this an approved catalog.
Fingerprints detect changes, not confidentiality or administrator approval.
Review decisions and their catalog must come from a protected operator source,
never model output, note frontmatter or browser request fields.

No live reader/worker imports this module. Before enabling it, the integration
must enforce trusted loaders and a read-only private store, invalidate policy
changes again at worker dispatch and before releasing a response, and retain the
native untrusted-input screen (JEV). Retrieval tests are not evidence that those
transport, queue or worker boundaries have already been implemented.

`preview_human_access.py` produces a read-only matrix without printing raw channel
IDs. `--counterpart HUMAN=PERSONA` proposes a binding in memory only. It never
edits a source, adds an allowlist entry, issues a link or enables the assistant.

## PhantomOrg compatibility

The inspected PhantomOrg JSON schema and shape validator reject unknown human
fields. `humans[].counterpart_persona` and `policies.phantomview.project_grants`
are private extensions, not supported upstream fields. The
[private compatibility patch](PHANTOMORG_HUMAN_ACCESS.md) implements coordinated
schema, model, shape and reference support and is tested separately. It has not
been applied to AU. Adding the fields only
to YAML would break normal validation. The schema, shape validator, model and
reference validation must be extended together and tested before changing live
sources. `roles[].reports_to_human` describes reporting, not an explicit
counterpart relationship, and is not reused as an access grant.

AU's requested bindings are Salvador/Paco, Brigitte/Pepa and Fran/Roberto. The
read-only live inspection found registered Telegram identities for Salvador and
Brigitte, but **no registered Telegram identity or npub for Fran**. Fran's
verified channel identity must be registered before his identified session can
be enabled. Human category zero currently names Salvador explicitly.

## Remaining activation work

The inactive [scoped consultation library](SCOPED_ASSISTANT.md) now supplies
persona-bound evidence dispatch, current-view revalidation and metadata audit
checks around a synchronous trusted executor. Synthetic tests cover held/failed
results and revocation during inference. No production native executor is wired;
native memory isolation, genuine JEV integration, queue/budget controls and all
deployment prerequisites below still apply.

- Implement and test the opt-in native channel hook against the installed release;
  keep it before inference and deliver links only to that verified direct sender.
- Support the explicit counterpart/project extensions consistently in PhantomOrg,
  then validate the reviewed AU matrix and register missing channel identities.
- Integrate the prepared private handoff/client with the reader and an isolated
  native channel component; verify AU account separation and actual direct-message
  delivery. No publicly submitted identity field or model-readable signing secret.
- Review the fingerprinted classification catalog, then wire the prepared scoped
  retrieval before inference; dashboard KB exports alone do not establish
  per-resource category/project labels sufficient for expanded access.
- Connect recipient-aware metadata audit events and worker terminal events. The
  prepared generic audit remains optional and inactive; it is not a protected
  remote archive or full conversation history.
- Verify refusal paths, revision changes, isolation, expiry, JEV holds and one-time
  redemption end to end, then activate only AU. No second human signature/login.

## Validation

From this directory:

```bash
python3 -m unittest test_channel_identity -v
python3 -m unittest test_signed_recipient -v
```

The second suite requires the installed PhantomBlog access extra (`coincurve`).
It uses ephemeral keys and the real verifier, including signature rejection,
replay/freshness/exact-payload checks and concurrent single-use redemption. It
does not claim to test a not-yet-connected channel hook.

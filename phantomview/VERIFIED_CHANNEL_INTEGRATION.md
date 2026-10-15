# Verified human access: integration status

Status: private, tested primitives; **not enabled on the AU reader or daemon**.
The current assistant remains the bounded, tool-less PhantomView analysis pilot.

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

`preview_human_access.py` produces a read-only matrix without printing raw channel
IDs. `--counterpart HUMAN=PERSONA` proposes a binding in memory only. It never
edits a source, adds an allowlist entry, issues a link or enables the assistant.

## PhantomOrg compatibility

The inspected PhantomOrg JSON schema and shape validator reject unknown human
fields. `humans[].counterpart_persona` and `policies.phantomview.project_grants`
are proposed private extensions, not supported upstream fields. Adding them only
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

- Implement and test the opt-in native channel hook against the installed release;
  keep it before inference and deliver links only to that verified direct sender.
- Support the explicit counterpart/project extensions consistently in PhantomOrg,
  then validate the reviewed AU matrix and register missing channel identities.
- Transport the recipient association through a genuine trusted boundary to the
  reader. No publicly submitted identity field or model-readable signing secret.
- Wire scoped retrieval before inference; current dashboard KB exports do not
  establish per-resource category/project labels sufficient for expanded access.
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

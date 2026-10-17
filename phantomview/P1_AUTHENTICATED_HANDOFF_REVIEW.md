# Authenticated handoff inspection

Date: 2026-10-17. Status: read-only inspection completed; identified link
acceptance remains pending. This report follows the
[collaborative viewer plan](COLLABORATIVE_VIEWER_PLAN.md).

## Scope and evidence

The inspection covered only the selected installation's known viewer, analysis
worker, native persona service, link helper and organization declarations. It did
not enumerate other installations, issue a link, invoke inference, change policy,
restart services or deploy code. Live identities, private paths and raw operational
evidence are deliberately excluded from this report.

| Check | Observed result | Limit |
|---|---|---|
| Native version | PhantomBot `1.1.433`. | Version output is not an audit of the installed engine. |
| Public CLI | `ask --help` succeeds and documents persona selection, stdin, history and conversation options. | No inference, authenticated delegation or end-to-end conversation was tested. |
| Selected services | Viewer, existing analysis worker and native persona service were active/running. | A service-state snapshot does not establish complete health. |
| Process accounts | The analysis worker shares the native persona's account; the viewer uses a different account. | This is not an isolated issuer or inference boundary. |
| Installed reader | Imports and constructs the existing `access_gate.Gate`. No identified-scope reference was found in the inspected reader. | The identified source implementation is not the deployed reader path. |
| Identified components | `identified_access.py`, `channel_identity.py` and `reader_handoff.py` were absent at the checked installation locations. | This is a targeted file check, not a system-wide search. |
| Link helper | References the existing PhantomBlog `access-link` command with persona, persona-store, port and public-origin options. | The inspected helper does not convey a verified requesting human to the reader. |
| Issuer policy | One persona and one signing identity are configured. | A signer identifies the issuing bot, not the requesting human. |
| Organization | Four human records, three nonempty Telegram identity fields and no nonempty public-key identity fields; category zero is present. | Contact fields alone do not prove ownership or authorization. |
| Proposed private declarations | No `counterpart_persona` declaration or `policies.phantomview` section was present. | These private extensions must not be treated as mandatory upstream schema. Existing reporting relationships are not automatically counterpart mappings. |
| Organization copies | The two selected organization files matched byte for byte. | This does not prove that every consumer has reloaded them. |

## Consequence

The inspected active path verifies the issuing identity and redeems a browser
bearer link, but it does not bind that session to the verified human who requested
it. Native channel authentication must reach the reader through a trusted handoff;
the viewer must then resolve authority from PhantomOrg. Do not guess a human from
the configured issuer, message text, role name or browser-provided identity.

This is a missing identity handoff and authoritative relationship mapping. It is
not a reason to put organization categories or a human ACL engine into PhantomBot,
replace collaborative persona knowledge, or deploy the earlier isolated-worker
design. No second human login or signature is proposed.

## Next implementation increment

1. Resolve an explicit human-to-persona relationship from compatible PhantomOrg
   declarations. Validate ambiguity and category-zero ownership independently;
   do not blindly apply the historical exact-base schema patch.
2. Locate a supported authenticated direct-channel integration. If unavailable,
   review the smallest optional generic pre-model handoff seam carrying the proven
   sender, channel and receiving persona. Do not infer this context from a model
   tool invocation, ordinary environment values or a trusted relay identity.
3. Bind that receipt server-side to the specific signed grant, organization and
   configured issuer route. Keep the active single-issuer limitation explicit until
   trusted multi-issuer registration is implemented.
4. Reuse the existing signed-link security design unchanged: canonical NIP-01 ID
   recomputation, coincurve Schnorr verification, pubkey allowlist, freshness window,
   replay cache, locked single-use redemption, fragment-only delivery and exact
   tag/payload/origin binding. Do not add recipient identifiers to browser URLs.
5. Test unknown and ambiguous humans, wrong issuers, relayed/group requests, replay,
   expired grants, revocation and default-persona changes using synthetic fixtures.
   Then demonstrate Telegram and PhantomChat handoff against their actual supported
   surfaces before claiming P1 acceptance.

P1 remains incomplete until an identified link is demonstrated end to end. Native
assistant activation and deployment remain later milestones. No application tests
were run for this documentation-only inspection report; service status and CLI
help checks must not be reported as application test coverage.

## Subsequent component verification

The original inspection above remains read-only evidence of the installation.
A later source-only regression suite, `test_identified_viewer_flow.py`, now composes
the existing real PhantomBlog verifier, `IdentifiedGate`, `HumanDirectory`,
`ScopedBackend` and issuer-bound navigation. Thirteen tests cover:

- Three counterpart flows with a separate fixed-issuer gate per persona.
- Telegram and canonical registered PhantomChat sender contexts supplied by fixtures.
- Unknown, email-only, mismatched counterpart and unauthenticated/group contexts.
- Wrong signer or issuer claims, signed-event replay and concurrent single redemption.
- Channel rebinding and counterpart removal before redemption.
- Policy changes, logout and operator revocation before further record reads.
- An independently assigned category-zero owner without a counterpart, retaining
  the actual issuer and receiving no implicit write capability.
- Legacy unidentified links and expired grants denied identified viewer access.

Run from the `phantomview` directory with PhantomBlog and its access extra installed:

```bash
python -m unittest test_identified_viewer_flow -v
```

Without coincurve/PhantomBlog the tests are explicitly skipped; skips are not
signature verification evidence. The existing handoff CI job installs the pinned
PhantomBlog access dependency and discovers all Python tests. No new workflow or
runtime service is needed.

These fixtures supply trusted channel context directly. They do not authenticate
an actual sender or demonstrate production channel reception. Each fixed-issuer
gate has its own state; the tests do not claim a shared multi-issuer endpoint.
P1 native handoff acceptance, compatible live PhantomOrg declarations and native
assistant activation remain pending. No runtime or protocol implementation changes
are made by this verification increment.

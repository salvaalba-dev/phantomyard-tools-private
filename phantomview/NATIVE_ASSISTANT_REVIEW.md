# Existing-persona assistant integration review

## Decision

Reuse the existing persona and the public native command surface. Do not activate
ordinary conversation for a restricted PhantomView session yet: the inspected
`ask` route does not carry the current human's PhantomOrg category/project scope
into native retrieval. The standard viewer and default-persona observation adapter
can proceed independently. This is a specific integration gap, not a claim that
PhantomBot has no security controls or that its normal private channels are unsafe.

No replacement engine, memory copy, new ACL database, account, background service
or native source patch is introduced by this review. No live AU change was made.

## Verified upstream evidence

Reviewed on 2026-10-17 at PhantomBot commit
`5af27060327ee8c53fe730dd8b98b6b305c62add`. Source files were fetched again at that
exact commit and matched the initial review. This is an upstream source review,
not verification of the currently installed AU binary or its effective settings.

| Evidence | Observation | Integration consequence |
|---|---|---|
| [`ask.ts`, arguments](https://github.com/phantomyard/phantombot/blob/5af27060327ee8c53fe730dd8b98b6b305c62add/src/cli/ask.ts#L291-L336) | Public inputs include persona, prompt/stdin, conversation, history and streaming. There is no authenticated human or PhantomOrg resource-scope argument. | Do not invent an existing identity/ACL parameter. A private conversation key is not such a parameter. |
| [`ask.ts`, turn construction](https://github.com/phantomyard/phantombot/blob/5af27060327ee8c53fe730dd8b98b6b305c62add/src/cli/ask.ts#L153-L210) | Input remains untrusted and follows native screening. With history enabled, native retrieval, indexing and durable-fact handling are used. | Preserve JEV and native persona behavior. Do not use a trusted-input override. |
| [`RetrieveContextOptions`](https://github.com/phantomyard/phantombot/blob/5af27060327ee8c53fe730dd8b98b6b305c62add/src/orchestrator/retrieval.ts#L59-L80) | Retrieval receives persona paths, settings and conversation; memory and KB remain global within that persona. | Filtering the viewer's records does not filter all knowledge the native persona can use. |
| [Cross-conversation retrieval](https://github.com/phantomyard/phantombot/blob/5af27060327ee8c53fe730dd8b98b6b305c62add/src/orchestrator/retrieval.ts#L155-L240) | Other conversations can contribute context by default. Audience exclusions are applied in SQL before the candidate limit. | Existing audience protections are real and must be retained, but they do not establish the requested category/project ACL. |
| [`makeRetriever`](https://github.com/phantomyard/phantombot/blob/5af27060327ee8c53fe730dd8b98b6b305c62add/src/orchestrator/retrieval.ts#L586-L606) | The factory binds configuration, persona, directory and conversation. | The inspected path does not bind the viewer's current authenticated recipient or policy revision. |

Source blob IDs: `ask.ts` = `2553e4bfdc49899659437195355c46ac56160da2`;
`retrieval.ts` = `a709fd1080d04ffcbf2994d11ee82593689bca4e`.

## Why the existing link is still useful

The identified link and current PhantomOrg directory determine who entered, the
issuing persona and the permitted viewer scope. Preserve that authentication.
The missing step is applying the same authority to the additional knowledge that
native inference can load. Neither another human signature nor a second login
would supply that missing retrieval filter.

A persona's counterpart can inherit its declared information privileges. That
does not prove that a narrower project view equals every item in the persona's
native KB, profile, durable facts and conversation memory. In particular, opening
a project module must not quietly change a project-bound consultation into a
conversation over the persona's whole native knowledge surface.

## Smallest compatible next change

The viewer-side part now exists in `native_turn_context.py`. A trusted native
integration can construct `NativeTurnContext` from the existing scoped backend
and authenticated request headers. Its control metadata binds human, issuing and
selected personas, scope, directory/authority/policy/view revisions and a turn ID.
It does not expose the session cookie or accept a browser-authored grant object.
The selected section must be installed and visible; an unauthorized module
assistant cannot fall back silently to the core persona.

`read` and `search` delegate to the existing authorized backend projection, and
revalidate the original session and revisions before returning data. `release`
revalidates before returning a bounded response envelope; `close` invalidates the
handle. Category-zero information privileges come from PhantomOrg and do not
create write capabilities. No new policy store or configurable grant is added.

This is the viewer-side contract, not native enforcement. `release` cannot detect
hidden information that a native adapter already loaded elsewhere, and metadata
must never be pasted into a prompt as an ACL mechanism. The native input surfaces
below must consume the authority before ordinary native conversation can start.
No subprocess or HTTP execution route is registered by this module.

1. Use the existing verified recipient and current PhantomOrg policy as the only
   authority. Keep native channel identity and request text separate. The browser
   cannot choose a human, grant, project or policy revision as an authority claim.
2. Establish a supported native integration point that accepts a server-bound
   authorization context or a native handle to that context. Reuse the existing
   runtime's persona, credentials, memory and JEV; do not create another engine.
3. Apply the native authority before knowledge loading, including derived and
   linked context. Review profile text, curated memory, KB, durable facts,
   cross-conversation retrieval and tool access as separate input surfaces.
   Unknown classification cannot be assumed authorized for a restricted session.
4. Keep the existing audience filters and untrusted-input screen. Do not infer
   confidentiality from a JEV score or attempt to enforce it with a prompt.
5. Revalidate the current session, persona and policy before dispatch and before
   releasing an answer. Use the existing audit/session components and clear
   pending output on expiry, scope changes or revocation.

This is one authorization context derived from PhantomOrg, not a parallel policy
system. If the supported native surface cannot enforce it, keep the bounded
viewer assistant separate and explicitly unavailable for ordinary native chat.
The existing experimental native worker must not become a prerequisite merely
to bypass this missing public integration point.

## Activation acceptance criteria

These are required future end-to-end checks, not claims of implemented behavior:

| Case | Required result |
|---|---|
| Authorized counterpart in its full declared scope | The existing persona answers using its native runtime and JEV. |
| Project session and a matching restricted module | Only knowledge permitted in that project context can contribute. |
| Denied category or another project in memory/KB | Data does not reach inference or appear in the response. |
| Hidden cross-conversation fact or linked/derived content | Existing audience and PhantomOrg ACL both hold. |
| Missing classification or unsupported native authority context | No unrestricted fallback. |
| Expired/revoked session or changed policy during a turn | Pending output is withheld and the session must be refreshed. |
| Category-zero human | Explicit information privileges apply; independent write capabilities remain unchanged. |
| Module chooses another persona | Its own native scope is checked; the core default and human identity do not change. |

No real-user question, native inference call, channel message, credential read or
permission change was needed to establish these findings.

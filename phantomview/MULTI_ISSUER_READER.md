# Multiple issuers in one identified reader

Status: private source integration; no additional AU issuer is activated.

One HTTP reader, audit ledger, reviewed projection and session store can serve
up to sixteen explicitly configured issuing personas. Existing launch files
remain valid. The existing primary issuer fields retain their meaning; an
optional `additional_issuers` list adds protected host routes:

```json
{
  "additional_issuers": [
    {
      "actor": "project-guide",
      "identities": ["bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"],
      "issuer_uid": 12004,
      "socket_path": "/run/example-view/reader/project-link.sock",
      "socket_group": 12003,
      "conversation_socket": null
    }
  ]
}
```

This is a fragment of the protected launch document, not a replacement for its
required fields. Replace all synthetic coordinates with reviewed host values.
No route may be supplied by an HTTP request, channel message, model output or
handoff frame. Registry changes require a reviewed reader restart and fresh links.

## Binding and permissions

Every issuer has a distinct handoff socket, a fixed expected daemon UID and a
nonempty, disjoint public signing allowlist. Each listener checks Linux kernel
credentials before reading a frame. The selected persona comes from that
listener's protected host route. The version-one native frame remains unchanged;
adding a claimed persona or other fields is rejected.

Each route uses the unchanged PhantomBlog NIP-98 verifier, including canonical
event ID recomputation, Schnorr verification, exact tags and payload, freshness,
replay protection and single-use locked redemption. The verifiers remain
separate because their signer allowlists are disjoint. Pending recipient links
and human sessions share the reader's existing aggregate limits. Credentials
remain fragment-only. A link is redeemed through the verifier bound to its
server-held recipient; the browser cannot select a different verifier.

PhantomOrg resolves the verified channel human, counterpart, category limits,
projects and scopes before issuance and on every identified request. Adding a
host route grants no human, category, project, scope, document or action access.
Changing current authority invalidates old recipient bindings.

Whole-daemon account trust remains the chosen boundary. Distinct UIDs prevent
one account from using another account's listener. If multiple configured personas
share a daemon UID, code holding that account's privileges is trusted across those
routes; this does not provide persona isolation inside the account. Separate
signer allowlists still apply. The reader UID must differ from every issuer UID.

## Assistant and lifecycle

Optional native conversation sockets are fixed per issuer and cannot be shared
between personas. Only the session issuer's configured executor is used. A
missing route or disabled conversation socket never falls back to the primary
issuer or installation default. Explicit human category limits still disable
native conversation for that human; native collaborative memory/tools do not
implement the viewer's human-specific restriction.

Preflight checks every issuer, group, protected socket parent and optional
conversation endpoint against the same current authority and approved projection.
Every handoff listener shares the exact HTTP gate. Failure to start any listener
closes all prepared listeners and HTTP, cancels consultations and discards sessions.
No extra resident inference service, scheduler, account or credential store is added.

## Deployment boundary

Provision and review each native route, socket parent and membership before
launch. Existing pre-model native channel routing must point to the matching
handoff socket and verified scope. Enabling this source feature does not install
those routes or update the stock native binary. Follow the existing reversible
cutover procedure and verify real allowed/denied links for each configured issuer.
Unclassified records remain excluded. Production access changes require their
own reviewed activation; source CI is not evidence of live authentication.

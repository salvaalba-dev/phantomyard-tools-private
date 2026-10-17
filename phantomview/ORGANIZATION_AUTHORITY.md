# Raw organization authority binding

`OrganizationAuthority` is an optional callable for the existing identified gate's
`directory_loader`. It reads the explicitly selected authoritative PhantomOrg
document on every call. It is not another ACL database, organization engine,
background service, HTTP endpoint or automatic activation switch.

```python
from organization_authority import OrganizationAuthority

# Operator-owned configuration; never values supplied by the browser or model.
authority = OrganizationAuthority('/srv/example/org.yaml', 'example')
authority()  # Validate startup; do not serve identified access if this fails.

# Pass directory_loader=authority to the existing IdentifiedGate constructor.
# Reuse that exact gate for trusted issuance, redemption and the scoped backend.
# authority.read is the corresponding current raw-document loader for consumers
# that already require a protected organization_loader callback.
```

The example is synthetic. Signer allowlists, current origin/port, channel handoff,
reviewed catalogs and record loaders must be configured through their existing
contracts. This helper does not create them, register routes or change signed-link
verification. Canonical event IDs, Schnorr verification, freshness/replay checks,
single-use locked redemption, fragment-only delivery and exact payload/tag binding
remain in the unchanged signed-link implementation.

## Current source, not cached presentation

The file must contain the raw organization document, including authoritative human,
counterpart, category and viewer-scope declarations. A collector index or browser
snapshot cannot substitute for it. The loader binds exactly one absolute operator
path and expected organization ID, validates through the existing `HumanDirectory`,
and returns a fresh directory/document. There is no previous-good policy cache or
implicit legacy scope: explicit viewer-scope declarations are required. There is no
fallback to another source/default persona. Changed identities/policies invalidate
existing recipients through the gate's existing revision checks. A missing,
unreadable or invalid source fails the current request before extended data reads.

Documents are limited to 4 MiB. JSON duplicate keys/non-finite constants and YAML
duplicate keys, aliases, merge keys, excessive nesting or excessive parser events
are rejected. YAML anchors without references do not grant additional semantics.
Invalid input is reported without source snippets or private identity values.

Regular single-link files are required. Linked/reparse path components are
rejected; descriptor/path identity, size and modification metadata are checked
around the bounded read. POSIX additionally checks ctime and rejects group/world
writable source files. Windows creation-time snapshots are not treated as POSIX
ctime; identity, size and modification checks remain active.

These checks do **not** establish the security of every parent directory or native
account. The operator must keep the source, its parent chain and configuration
outside model/browser write authority and configure narrow read access for the
reader. Windows ACLs, kernel account isolation, concurrent privileged writers and
the actual deployment layout require separate checks. A trusted atomic replacement
is accepted on the next read; a replacement/change observed during a read fails.
This is current-source validation, not a filesystem transaction or signed policy.

## Verification

`test_handoff_authority.py` covers fresh reads, JSON/YAML equivalence, missing or
corrupt sources, organization mismatch, duplicate/aliased data, size limits,
nonregular files, hard links, concurrent changes and applicable POSIX protections.
The real-signature cases connect the file loader to `IdentifiedGate` and
`ScopedBackend`: signed issuance/redemption, bound recipient and issuing assistant,
allowed/denied workspace data, unknown sender, changed counterparts, current-policy
revocation, missing-file denial before record reads and logout. These tests reuse
the existing signing verifier rather than substituting a protocol double.

Channel contexts are **synthetic trusted test inputs**. They do not prove an
installed native Telegram/PhantomChat callback, allowlist check, protected transport,
live signer or multi-issuer server. The real-signature CI job discovers this test
and now includes authority-loader changes in its path filters. Generic matrix CI
may skip signature cases when optional signing dependencies are absent.

The detached AU proposal was accepted locally by this loader; neither it nor the
live organization source was edited. No live link, persona or assistant was invoked.
Private source data and review artifacts remain outside the repository.

## AU deployment boundary

The inspected live viewer remains on its legacy gate. A read-only check on
2026-10-17 confirmed that its service is active under the existing domain account.
Executing a harmless identity command as that account succeeded, while `test -r`
returned exit code 1 for both `/root/proyeccion/org-live.yaml` and
`/opt/phantomdocs/org.yaml`. These are file-read denials, not a failed account probe.
The selected source still matches the reviewed baseline and the published copy
remains byte-identical. No permissions, files, grants or services were changed.

Do not open the administrator directory to the reader or silently select a stale
copy. The next integration should prepare an explicit private authority export
through the existing collector/publication lifecycle, owned by the trusted producer
and readable only by the intended reader. It must preserve current source binding,
report publication failure/drift, support atomic refresh and never enter the public
index or static browser routes. This producer integration is **not implemented or
activated by this loader**; its exact target and access require deployment review.
No separate scheduler, resident organization service or independently editable
policy store is needed. Configure exactly one reviewed current raw-source path.

Before activation, review/apply the detached organization declarations, establish
source propagation and protected reader access, supply approved resource reviews,
and complete actual native verified-channel issuance with the same gate used for
redemption. Preserve the existing collaborative persona, memory and JEV behavior.
No second human login, replacement inference engine or model-readable issuer
credential is introduced by this source loader. It does not by itself connect
native assistant conversation or make the installation ready for activation.

See [the collaborative plan](COLLABORATIVE_VIEWER_PLAN.md),
[source compatibility](AU_PHANTOMORG_COMPATIBILITY.md) and
[native callback contract](NATIVE_LINK_CALLBACK.md).

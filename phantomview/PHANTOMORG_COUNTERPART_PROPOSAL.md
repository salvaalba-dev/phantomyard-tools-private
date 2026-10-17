# Minimal explicit PhantomOrg counterpart proposal

Status: private source proposal and disposable-source tests only. No live AU
configuration, human identity, permission, persona, service or upstream repository
is changed. This does not activate identified sessions or the native assistant.

## Scope and authority

`humans[].counterpart_persona` is an optional existing actor ID. An omitted field
means unbound. Present null, invalid identifiers, missing actors and two humans
assigned to the same persona are rejected. It survives model loading and appears
in HUMANS.md only when mappings exist; legacy output remains byte-identical.

The relationship belongs in PhantomOrg. The viewer derives access from the actor's
existing role, exceptions and organization policies; it keeps no second grant
registry. Category zero remains independently assigned. Names, `reports_to_human`,
role labels, email addresses and runtime defaults never infer a counterpart or
prove a verified channel principal. This proposal does not add channel trust,
resource classifications, write authority or native knowledge isolation.

The five-file implementation plus a small PhantomOrg README addition is deliberately
separate from the historical `phantomorg-human-access.patch`. That historical patch
has a different exact base and broader policy/schema changes; the two proposals
must not be stacked or applied blindly. Existing consumer code that requires those
broader private policies still requires its own reviewed declarations. The minimal
field alone is not a scoped-activation claim.

## Exact source and preparation

The manifest pins public read-only source `phantomyard/phantomtools` at
`5e007b4f2864e52ffef1360df86ed6b5267750cb` and SHA-256 hashes for all six touched
files and the patch. This is the inspected development base, not an assertion
about the installed AU version. No installation is performed by the preparer.

From this private repository, use a fresh disposable source checkout:

```sh
python3 phantomview/phantomorg_counterpart_patch.py /path/to/disposable/source
```

The source root contains `phantomorg/`. The preparer rejects symlinked paths,
changed source, a modified patch and reapplication before writing. Git checks the
complete patch before applying it. Keep the original checkout as the rollback;
never target live persona/configuration directories. Supported source changes
require a fresh review, manifest and compatibility run.

## Verification and remaining work

Dedicated Linux CI checks out the exact public revision with read-only permissions,
applies the proposal, proves reapplication refusal, runs the full PhantomOrg suite,
and tests schema/shape parity, reference integrity, legacy registry output and
compatibility with the viewer's existing HumanDirectory. Standard viewer tests
also run; the optional integration class skips when this proposal is not loaded.
Windows cannot run privileged symlink cases without the corresponding OS privilege;
Linux CI is the authoritative full-suite result.

Still pending: compare installed PhantomOrg source against this pinned base,
review and declare real counterpart mappings in PhantomOrg, validate the live
organization without leaking identities, and finish the existing issuer/channel
handoff. No production activation follows automatically from CI success.

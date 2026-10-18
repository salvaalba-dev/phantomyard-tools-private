# Offline deployment route pairing

Status: source preparation only; no AU route or access grant is activated.

Before preparing a native build, compare the protected reader launch document
with every native host build document targeting that reader:

```sh
python3 phantomview/deployment_routes.py --reader /protected/reader.json --native-host /protected/daemon-routes.json
```

Repeat `--native-host` for a separate daemon account. Combine routes sharing one
daemon account in one host document. Each document uses the existing
[native host schema](NATIVE_HOST_ENTRY.md); the reader uses the existing
[launch schema](READER_LAUNCH.md). No new production configuration is introduced.

The command validates both schemas, requires complete reader issuer coverage,
and compares exact persona, daemon UID, reader UID, canonical HTTPS origin,
handoff socket and optional conversation socket. Both channels may target the
same issuer. Every configured channel must agree with that issuer's conversation
enablement. The native validator still checks conversation group consistency
within a host; actual reader group membership remains a Linux preflight check.

The result contains counts and outstanding checks, never deployment coordinates,
signing keys, human identities or raw configuration errors. It reads selected
files only: no writes, sockets, subprocesses, services, inference or publication.
Use absolute protected JSON paths. Existing source read protections and native
input size bounds apply. This is an operator preparation tool, not an HTTP API.

`route-descriptors-matched` always retains `activation_ready: false`. Matching
descriptors do not prove installed source hashes, loaded signer identities,
Linux permissions, channel authentication or approved information access.
Native scope IDs are explicit build inputs and are not inferred, approved or
granted by this check. Current PhantomOrg authority and the approved projection
remain required; unresolved information stays excluded. Perform reader preflight
and the reviewed reversible cutover before testing real allowed/denied links.

For AU, the category-limit collector compatibility release is already separate
from this preparation. Additional issuers, the Beatriz restriction proposal,
native host builds and the identified reader still require their reviewed
deployment inputs; this command changes none of them.

## AU read-only observation, 2026-10-18

The selected executive daemon, existing reader and collector timer are active.
The organization source still matches the prior collector deployment fingerprint.
The proposed projection directory, reader socket parent and root-level identified
launcher are absent at the selected AU paths. No account, permission, policy,
service or executable was changed during this check. These observations establish
the unchanged baseline, not successful route pairing for a live deployment.

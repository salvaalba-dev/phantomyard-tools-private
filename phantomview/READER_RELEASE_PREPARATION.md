# Detached reader release and identity preparation

Prepared on 2026-10-18. Status: **verified archive; not installed or activated**.
This follows the [AU configuration review](AU_READER_CONFIGURATION_REVIEW.md).

## Exact source archive

The detached `phantomview-reader-94dae2d.zip` contains 102 tracked source/assets
and a release manifest. Its SHA-256 is:

```text
a5086f764eaafebb8f3c54f76403b6a6cfceb9567224a3f8071beee7977fc1bc
```

The reader files match private main revision
`370d4fd04309ce7a9b4811277736eb2a97cd0c3d`; runtime code is unchanged from the
`94dae2d` release label used in the detached native proposal. The bundled
`phantomblog` package and its MIT license match the already reviewed signing
revision `4147924afad85b1db6752b709c29b78d6f56774c`. No public repository was
modified. Every archived source byte matches its recorded Git blob and SHA-256;
the [manifest](reader-release-94dae2d.manifest.json) records these inputs.

Line-ending candidates were accepted only on exact Git blob equality. One local
UI asset differed from the selected revision; its exact tracked blob was obtained
into a detached packaging directory. The working source copy was not overwritten.
ZIP members use sorted names, a fixed timestamp and regular-file metadata.
The extracted archive's complete file set and hashes were checked.

Bundling the unmodified signing package beside the reader avoids a global Python
installation or a runtime source download. Python's protected script directory
resolves the package; isolated test execution explicitly selected that directory
and asserted the verifier came from it. This does not bundle Python, PyYAML,
coincurve, native binaries, live configuration, persona keys or human records.
The archive includes inert operator helpers from the tracked source tree; none
is automatically executed. An approved deployment must protect the release
directory against writes by the reader, daemon and their tools.

## Extracted-package checks

The extracted modules passed:

- Full manifest SHA-256 verification and Python compilation.
- An isolated-process import of the bundled real signature verifier.
- A synthetic Schnorr-signed NIP-98 request, fragment-only link delivery,
  successful one-use redemption, and rejection of both a redeemed link and a
  replayed signed request. No real recipient, channel or provider was contacted.
- The existing identified-reader, multi-issuer, trusted-handoff and launch
  regressions: **52 tests, OK, 5 platform skips**. Import assertions confirmed
  those runtime modules and the signing verifier came from the extraction.

These targeted archive checks supplement the prior source suite; they do not
claim a new full-suite run or Linux account test on the operator's Windows host.

## AU read-only checks

The existing reader process uses the proposed system Python without a configured
virtual environment or Python path override. A dependency probe under the actual
reader account found `coincurve 21.0.0`, its public verification API, and
`PyYAML 6.0.1`. The latter differs from the source requirement `PyYAML==6.0.3`.
Do not treat the current system environment as release-ready or update global
packages used by other setups. Prepare a compatible protected application
environment and verify it under the actual accounts before cutover.

A separate in-process check on the VPS compared the selected executive persona's
protected existing disk identity with its PhantomOrg public npub. They match.
The check returned booleans only: no key material was printed, exported, copied
or sent to a relay, and no message or signature was issued. The existing daemon
was not restarted. **This is a disk-identity comparison, not attestation of the
identity currently loaded in the daemon or live-channel authentication.**

## Deployment boundary

The archive remains in the private operator workspace. No VPS file was uploaded,
package installed, group created, membership changed, listener started or service
restarted in this increment. No classification, counterpart or ACL grant changed.

Remaining prerequisites include the matching Python environment, source-matched
native host build, protected IPC/filesystem provisioning, explicit metadata
decisions and publication, Linux preflight and approved reversible cutover.
Verify actual channel issuance and current authority after startup. The earlier
122 metadata candidates remain unclassified; KB content remains excluded.

## Runtime preparation follow-up

The [AU private runtime preparation](AU_PRIVATE_RUNTIME.md) records a separate
root-owned environment with the pinned dependencies and actual account probes.
The reader archive, native build and information access remain inactive.

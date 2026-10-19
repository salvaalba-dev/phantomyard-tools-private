# Native build provenance and host compatibility

The operator build is private, manual and restricted to main in this repository.
It prepares an artifact; it does not install, activate or restart an AU service.

## Version authority

Upstream package.json declares the development version 0.1.0. Its release
workflow numbers release tags independently. Therefore the private build reads
the package version for the source placeholder and records it separately from
the release version. It fetches v1.1.433 and requires that tag to resolve to the
exact reviewed native commit 5af27060327ee8c53fe730dd8b98b6b305c62add.
The stamped binary and embedded editor assets use that verified release version.
Changing either pin without reviewing their agreement fails the build. No
PhantomBot source pin or upstream release design is changed.

## Bounded, normalized preparation

The workflow writes the result of validate_routes(), never the original input.
Both routes.json and routes.sha256 are mode 0600 inside a mode 0700 directory.
The digest covers exactly the bytes consumed by source preparation. Both socket
paths are ASCII and bounded to 100 bytes, below Linux sun_path limits.
Unsupported branches, tags and repository names fail explicitly before checkout.

## Toolchain and verifier

The runner family is ubuntu-24.04, Python is 3.12.15 and Bun is 1.3.11.
The Linux x86-64 CPython 3.12 wheels for PyYAML 6.0.3 and coincurve 21.0.0
are pinned by SHA-256 in native-build-requirements.lock. pip requires hashes
and binary wheels. These distributions declare no runtime dependencies.
Native dependencies and the editor extension use their unchanged reviewed frozen
Bun locks. The upstream editor packager still invokes @vscode/vsce@latest via
npx, and VSIX archive timestamps vary. That upstream packaging input is not
hash-locked by this change; complete supply-chain and bit-for-bit reproducibility
remain separate work. No claim of complete reproducibility is made.

The verifier import closure is archived in build-sources with its original
license and unmodified sources from phantomblog at
4147924afad85b1db6752b709c29b78d6f56774c. The manifest records each original
Git blob, SHA-256 and byte length as well as the archive digest. Every member
is checked before extraction. This is not a complete PhantomBlog distribution.
No public-fork branch or tag is changed, and the build no longer depends on
that fork retaining its historical commit. The NIP-98 security design is unchanged.

Hosted runner images remain mutable. The receipt records ImageOS, ImageVersion,
kernel, Python, Bun, installed wheel versions, lock digest and ELF requirements.
This improves repeatability and provenance; it does not promise bit-identical
builds or an immutable operating-system image.

## Test evidence and retention

The receipt requires successful preparation, native-channel and persona test
step outcomes. Skipped, missing, cancelled or failed groups refuse receipt
creation. tests_passed is derived from those outcomes. The compiled version and
embedded extension version are verified separately.

Binary artifacts have seven-day retention. A separate non-secret receipt has
90-day retention. The original activated AU build receipt from run 39165837083
is preserved unchanged in build-receipts/39165837083.json. Its older schema does
not retroactively acquire the new provenance guarantees. Preserve receipts in
the private repository when accepting future releases for long-term audit.

## Read-only host preflight

The artifact is dynamically linked. Its receipt records the ELF interpreter
and the greatest required GLIBC symbol version using numeric version comparison.
Before installation, run on the destination Linux x86-64 host:

```sh
python3 phantomview/native_build.py check-host \
  --binary /path/to/verified/phantombot \
  --expected-sha256 <independently-verified-64-hex-digest>
```

This reads and verifies the binary before inspecting it with readelf. It checks
host glibc and interpreter availability without executing the artifact or
changing the host. Python 3.11 or later and readelf must already be available.
The trusted expected digest must come from the reviewed build receipt, not from
an untrusted replacement file on the same host.

The old AU artifact required GLIBC 2.25. A newly compiled artifact must be checked
again; do not assume its ABI requirement remains identical. At this review the
AU terminal connection had closed before a fresh host ABI result was obtained.
No host compatibility result is claimed here.

## Deployment facts remain host evidence

Rehearsal directories, active.json absence, group IDs and effective systemd
overrides are observations of a particular host at a particular time. Repository
tests cannot prove them. Revalidate them immediately before any later cutover
using the existing activation procedure and rollback checks. This build review
does not change the currently active AU release, permissions, routes or services.

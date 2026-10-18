# AU private Python runtime preparation

Prepared and checked on 2026-10-18. Status: **dependency environment prepared;
no production service uses it yet**.

## Pinned artifacts

The selected host is CPython 3.12.3 on Linux x86_64. Compatible binary wheels for
PyYAML 6.0.3 and coincurve 21.0.0 were obtained from the official PyPI
distribution service. Downloaded bytes were checked against the SHA-256 values
in the version-specific PyPI metadata. Wheel metadata declares no additional
runtime dependencies for these artifacts.

The [dependency artifact specification](runtime-dependencies-cp312-linux-x86_64.json)
records exact filenames, versions, HTTPS URLs and hashes. It is a platform-specific
artifact inventory, not a universal installer, auto-update policy or ACL grant.
No source build, package index override or unpinned dependency resolution was used.

## Detached environment on AU

A new root-owned environment was created at:

```text
/opt/phantomview-au/runtime-releases/cp312-20261018
```

The existing system interpreter's standard venv/ensurepip support created the
environment with `system_site_packages=False`. The two wheels were independently
downloaded and hash-checked on the VPS into a private staging directory, then
installed into this environment with `--no-index --no-deps --only-binary=:all:`.
No system package was installed, removed or upgraded.

Existing targets were refused. The selected application ancestors were checked
for root ownership, directory type, absence of symlinks and group/other write
access before staging. The completed runtime ownership/write-protection audit
checked 1,359 entries. All are root-owned; non-symlink entries are not writable
by group/others. The environment configuration excludes system site packages.
The private staging directory retains a receipt and the exact wheel files.

## Verification under actual accounts

Both the current reader account and the executive daemon account executed the
new interpreter in isolated Python mode (`-I`). Each check established:

- The expected private prefix differs from the base interpreter.
- User site packages are disabled.
- YAML 6.0.3 and coincurve 21.0.0 load from the private environment.
- A fresh synthetic Schnorr signature verifies using the installed native library.

The existing system Python still reports YAML 6.0.1 under the reader account.
The selected daemon, reader and collector timer states/PIDs and organization
source fingerprint were compared before and after preparation and are unchanged.
No real human identity, channel message, relay or inference request was used.

## Configuration and activation boundary

No service definition, interpreter selection, release pointer, group membership,
counterpart, classification or ACL was changed. The reviewed reader/signing
archive has not been uploaded, unpacked or selected by any AU service.

Future reviewed native descriptors must use this environment's `bin/python`
instead of the system interpreter, and the reader launch command must select
the same compatible environment. Repeat descriptor pairing after that edit.
The earlier detached proposal still names the system interpreter: its local
update could not be completed because the local file/command helper failed even
after specific filesystem access was granted. Do not claim that proposal was
updated or that its native build is ready.

This resolves the dependency-version preparation step only. Combined reader
imports and signed-link tests on AU still require the reviewed reader archive.
The earlier local extracted-archive tests remain separate evidence. Exact
metadata decisions/publication, native build, protected IPC provisioning,
Linux preflight and reviewed reversible cutover remain required.

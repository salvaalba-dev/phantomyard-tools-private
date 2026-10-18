# AU inactive reader source staging

Verified on 2026-10-18 after explicit operator authorization to install and test
the reviewed package without activating the identified viewer.

## Installed artifact

- Release directory: `/opt/phantomview-au/reader-releases/94dae2d`.
- Transfer archive: `/opt/phantomview-au/phantomview-reader-94dae2d.terminal.zip`.
- Archive SHA-256: `a5086f764eaafebb8f3c54f76403b6a6cfceb9567224a3f8071beee7977fc1bc`.
- Contents: 102 reviewed source/assets plus the release manifest.
- Runtime used for tests: `/opt/phantomview-au/runtime-releases/cp312-20261018/bin/python`.

The package is the unchanged artifact documented in
[reader release preparation](READER_RELEASE_PREPARATION.md). Its bundled
PhantomBlog verifier retains the reviewed signed-link design. No live
organization source, credentials, classification approval or human contact data
was included in the archive.

Webmin upload controls failed. A bounded terminal transfer created a separate
root-owned archive exclusively, appended only at exact expected offsets and
verified its final SHA-256 before extraction. Failed upload paths were not used.
Extraction rejected path traversal, symbolic links, unexpected members and
manifest mismatches before writing into the new version directory. It never
overwrote an existing release. Root owns the installed directories and files;
group/other write permission is absent.

The installation receipt is protected at
`/opt/phantomview-au/reader-stage-94dae2d.json`.
This is installation evidence, not an activation or classification approval.

## Actual-account verification

The same synthetic probe ran successfully under both existing accounts:
`aunited` (reader, UID 1001) and `pb-paco` (issuer, UID 1054).

Each used the private runtime with bytecode writes disabled:

```sh
runuser -u aunited -- /opt/phantomview-au/runtime-releases/cp312-20261018/bin/python -B - < synthetic-probe.py
runuser -u pb-paco -- /opt/phantomview-au/runtime-releases/cp312-20261018/bin/python -B - < synthetic-probe.py
```

The operator-supplied probe was passed on standard input, not installed as a
service. Each account verified all 102 manifest file hashes and root ownership
without group/other writes. Importing `reader_launch` succeeded. The signature
verifier loaded from the protected release, not a globally installed package.

An ephemeral synthetic key signed a canonical NIP-98 kind-27235 request. Both
accounts verified issuance in memory, fragment-only delivery, successful first
redemption, rejection of a second redemption, signed-request replay rejection,
tampered-event rejection and rejection with an empty signer allowlist.
No network request, real persona key, real session or delivered link was used.
These are primitive/runtime tests, not authenticated Telegram or PhantomChat
end-to-end tests.

## Live state and remaining work

The staging guard compared the known reader, Paco daemon and collector timer
states/PIDs before and after installation. They were unchanged. The organization
source fingerprint and legacy reader file hash remained unchanged. A final
process check confirmed the existing service still runs the legacy reader path.

No launch configuration was selected, no service restarted, no new listener
started, no projection published and no ACL grant changed. The newly installed
source is inactive. The confirmed captured metadata classifications remain
separate; see [classification review](AU_METADATA_CLASSIFICATION.md).

Current-draft reconstruction, protected publication and IPC provisioning, the
compatible native build, Linux reader preflight, reversible cutover and real
allowed/denied verified-channel tests remain prerequisites for activation.
This increment does not claim full reader deployment or activation readiness.
No runtime source was modified and no new full-suite result is claimed.

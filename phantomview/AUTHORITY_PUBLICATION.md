# Private authority publication through the existing collector

This opt-in extension publishes a private raw organization document through the
existing collector. It adds no service, scheduler, model call or independently
editable ACL store. Default collection/export and legacy reader behavior remain
unchanged. The collector retains exact parsed organization inputs in private
process memory, absent from `data()`, snapshots and the index. Explicit publication
re-reads the selected source through `OrganizationAuthority`, compares it with the
collected input and copies it without changing any declaration or grant.

## Explicit producer and reader configuration

All paths and identities below are synthetic. First prepare an existing private
authority and index directories with the trusted producer owner and the same intended reader group. The helper
does not create accounts, grant parent access or discover other setups.

```sh
python phantomview.py --config /private/collector/config.json sync \
  --export /private/reader/index.json \
  --authority-dir /private/reader-authority \
  --authority-org example
```

Add these options to the **existing** collector invocation after deployment review.
Publication requires exactly one selected organization and absolute source/index/
target paths without parent traversal. Organization and source must match the
current collection. The fixed output is `organization.json` inside a separate
existing private directory, outside the application, index directory and KB payload
tree. Source documents, unrelated existing files and other organizations' outputs
are never adopted as publication targets. Reviewed counterpart, independent
category-zero and viewer-scope declarations must already exist in the source.

```python
from authority_publication import PublishedAuthority

authority = PublishedAuthority(
    '/private/reader-authority', '/private/reader/index.json',
    'example', '/private/collector/org.yaml', max_age=180,
)
authority()  # Required startup validation; failure must prevent activation.
# Pass directory_loader=authority to the existing IdentifiedGate constructor.
# authority.read supplies the matching raw-document loader for existing consumers.
```

The source path in this reader configuration is a binding label; the reader never
opens it. It needs only the private publication and current index. There is no
fallback to an original source, another setup or an older publication. This helper
does not select a signer, issue links or install a native channel callback.

Choose the explicit lease after checking the actual collector cadence. The example
uses 180 seconds; supported values are 1–3600 seconds. A stopped collector does
**not** provide immediate revocation: the previous valid authority can remain usable
until its lease expires. Changed identities/policies invalidate recipients when
the next publication arrives through existing gate revision checks. A refresh with
unchanged grants renews availability without another human authentication step.

## Privacy, consistency and failure handling

The copy contains the complete organization, including human contact metadata.
It is **private server input**, never a browser payload, static asset, public index,
repository file or attachment. No HTTP route is added. On POSIX the directory must
be producer-owned with no group write or other access; its intended group may
read/traverse. Authority and opt-in index replacements use mode `0640` and their
configured common reader group, assigned before the atomic rename.
Linked/reparse components, hard links and unsafe existing files are rejected.
On Windows the parent ACL must be configured separately; POSIX modes do not prove
Windows isolation. Protected parent directories and account boundaries remain
operator responsibilities.

The private `_phantomview_publication` field binds the organization, source,
canonical document revision, collector snapshot digest and publication time.
It is stripped from raw-document results. This protected local metadata is not a
signature or another authorization database. Each reader input is bounded to 4 MiB.
Publication precedes index replacement. Every directory load checks both files
and rejects payload, source, organization or digest mismatches, future timestamps
and expiry. A failed index update cannot pair a new observation with a different
old index. The files are not one transaction: a temporary mismatch denies access.
The index digest is a presentation revision, not a signature or proof that every
note body is current; existing resource/content review checks remain required.

Collection failure or source drift replaces an owned copy with an unavailable
marker and reports failure. The legacy last-good index may remain, but identified
access cannot treat it as authority. If invalidation cannot write the target,
failure propagates and the previous copy still expires. Temporary files are private
and cleaned after failure. Serialize collector invocations per target; this is not
a multi-writer policy transaction. A privileged source edit after the publication
read can require the next refresh. Do not describe bounded replication as instant
enforcement across native stores. Signed-link verification and collaborative
PhantomBot memory/JEV behavior remain unchanged.

## Verification and AU status

Synthetic tests cover CLI opt-in/default behavior, private-data exclusion, source
binding, renewal/expiry, drift, collection/atomic-write failures, mismatched indexes,
payload tampering, source/manual-file preservation and applicable POSIX checks.
Real-signature component tests connect the publication to the identified gate and
filtered workspace, including expiry and changed-policy denial before record reads.
Channel context remains a synthetic trusted input, not a live verified handoff.

AU's current reader cannot read either original/published organization source.
This prepares the missing transport without opening administrator directories.
It is **not installed or activated in AU**. Collector cadence, target/account access,
approved declarations/classifications and native assistant integration still need
deployment review. No private AU inputs or artifacts are committed.

See [raw-source authority](ORGANIZATION_AUTHORITY.md),
[the collaborative plan](COLLABORATIVE_VIEWER_PLAN.md) and
[source-binding readiness](AU_SOURCE_BINDING_READINESS.md).

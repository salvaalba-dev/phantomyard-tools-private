# Committed organization policy through protected delivery

Status: coordinated review candidate with PhantomDocs; no deployment or access
change. This addresses the organization-policy queue item, not document processing
or matrix generation. A publication lease alone does not prove current authority.

## Contract

The PR #67/#68 publisher optionally bootstraps a minimal committed source receipt
inside the **existing** root-controlled common policy lock. It contains only a
protocol kind, canonical source path and exact source SHA-256. The lock is never
created or renamed by this API; its inode, owner, mode and xattrs remain unchanged.
No registry, grants, contacts, credentials or policy content enters the receipt.
The reader already needs read access to that lock; no source read grant is added.

Receipt advancement happens under the exclusive lock after source and all copies
are verified, and after a required bridge start succeeds. Pending remains until
the receipt is fsynced. An interrupted receipt write cannot authorize delivery:
pending rejects readers, and matching transaction recovery repairs the receipt.
Unknown nonempty lock contents are not adopted as a fresh bootstrap.

Once this protocol is active, the matching publisher detects it even if its new
CLI option is omitted. Ordinary exclusive writers are refused. Old binaries do
not know this protocol: exclude them and independent editors from live authority.
All source changes must use the common-lock source publication transaction.

The root collector adds `source_sha256` to the existing private authority
publication only while holding a shared lock and checking its source against the
committed receipt. It also retains the existing collection/input/index binding.
A collector cannot repackage an old observation as a newly committed policy.

The strict reader:

1. Acquires a shared lock with a two-second acquisition deadline and refuses
   pending, missing, malformed, foreign or unsupported receipt data.
2. Reads root-controlled private publication/index files through protected
   ancestors and requires the exact committed source hash and selected source.
   A reader-owned or replaceable publication cannot invent grants and copy the
   public receipt hash. No original source read is performed by the reader.
3. Retains one verified publication/index pair in thread-local delivery context.
   Returned values are independent copies; another request cannot reuse that
   context. A concurrent collector replacement cannot mix this response's inputs.
4. Holds the shared lock through HTTP authorization and output, including binary
   originals, and native identified-link handoff output. Future requests use the
   new committed revision; an old unexpired private publication is rejected even
   after pending disappears. Existing signature, peer and recipient checks remain.

The lease is an additional availability bound, not a fallback for a receipt
mismatch. Missing matching package support refuses the strict path.

## Explicit configuration and compatibility

Reader launch schema 2 requires `policy_lock`; schema 1 is the historical
lease-only mode and does **not** satisfy this contract. Paths must be normalized,
distinct Linux paths. Use the synthetic `reader-policy-launch.example.json`.
The guarded launcher/supervisor must bind the same common lock. After receipt
activation, the matching guarded startup refuses a legacy schema-1 reader.

Collector invocation adds `--policy-lock` to its existing explicit authority
publication options. The publisher and every recovery/prestart entry use
`--commit-witness` for initial bootstrap. These are future installation choices,
not commands executed by this preparation. Both source repositories must supply
matching reviewed revisions; package version strings alone are insufficient.

Legacy collector/reader constructors remain available for existing source tests
and explicit historical installations. Strict mode never silently downgrades to
them. A legacy collector publication lacks the required hash and is denied.

The matching PhantomDocs candidate extends only exact source-digest allowlists
for the agent-aware, mixed-signer and dynamic-projection composition chain.
Unrecognized sources remain refused. Rebuild the entire reviewed overlay: an old
`PYTHONPATH` package can shadow a newly installed helper in site-packages. Verify
actual module paths and resulting hashes for collector, reader and supervisor.
Preserve existing routes, UIDs/groups, signer allowlists and resource approvals.

## Delivery bounds

Only API requests enter this guard; public static application assets remain
available. HTTP header parsing occurs before lock acquisition. The protected
handler has a 15-second absolute socket I/O deadline, including slow POST bodies
and response writes. Expiration closes the transport; it cannot release old-policy
bytes later. This is not preemptive cancellation of arbitrary Python CPU work.
Keep callbacks bounded and review any future streaming handler separately.
Native handoff retains its existing bounded frame deadlines and closes refused
connections without issuing a link or poisoning the listener.

Individual bounded requests admitted before a writer acquires EX may finish.
This does not promise cancellation of bytes already delivered, fairness under
unbounded hostile load, or a production latency SLA. Reverse-proxy limits and
actual systemd/lock/readiness timing require installation rehearsal.

## Validation and installation gates

Portable tests cover stale-but-unexpired authority, pending refusal for HTTP
methods, real recipient revocation after refreshed authority, no original-source
read, independent pinned values, HTTP output lock lifetime, schema binding and
refused handoff cleanup. The local composition test executes exact mixed/dynamic
candidate handlers and checks refusal on pending and stale receipts.

The explicitly enabled root Linux suite uses disposable `/var/lib` paths and the
real matching publisher to exercise reviewed source changes, copy interruption,
recovery, collector races, actual flock ordering and an unprivileged reader with
no source access. It stubs service control and uses no installed policy or users'
documents. `PHANTOMVIEW_POLICY_LINUX=1` asserts Linux root rather than skipping
privileged cases silently. PR CI pins tools commit
`9b97815bd27fcefe4c0ed474a2c0601a9e48cdc4` from
[tools PR #69](https://github.com/salvaalba-dev/phantomyard-tools/pull/69).
Manual CI also accepts an immutable reviewed 40-character tools commit. Updating
this dependency requires reviewing the new revision and rerunning integration.

Required sequence before activation: publish/review the tools protocol candidate,
publish/review the matching viewer candidate, run both Linux suites and the pinned
cross-repository integration, rehearse systemd, agree all writers and alert routing,
then obtain explicit installation approval. No permission grant or PhantomBot
change is a workaround for a failing prerequisite.

During an approved maintenance window, keep readers/writers quiescent while
switching all matching runtimes/configuration, bootstrap the receipt, collect and
publish a fresh bound private authority/index, then start the schema-2 reader.
Do not expose a running lease-only reader as complete acceptance during bootstrap.
Verify existing positive/negative reader permissions before and after.

After activation, preserve lock inode and receipt bytes during recovery. Do not
truncate the lock to disable the protocol, restore an empty lock backup or switch
a pending transaction to legacy code. Complete matching forward recovery before
reviewing any rollback. Policy rollback remains another reviewed publication.

# PR #73 production deployment handoff

Updated 2026-11-28. PR #73 is deployed for Alma's PhantomDocs matrix
service. Start with [PROJECT_STATUS.md](PROJECT_STATUS.md) for ecosystem
context.

## Merged source and validation

Owner: `salvaalba-dev/phantomyard-tools`.
[PR #73](https://github.com/salvaalba-dev/phantomyard-tools/pull/73) merged on
2026-11-26 at 17:27:37 UTC as
[`b424ddf`](https://github.com/salvaalba-dev/phantomyard-tools/commit/b424ddf2f7b04b66b2f0dab18ccfb60777b7d72c).
Do not repeat its source review/merge as a pending operation or infer deployment
from that merge.

The source includes isolated Python startup, a separately approved runtime
manifest, bounded read-ahead with complete hashes and descriptor-bound ACL
checks, source/copy/payload-pin regression coverage, and ordinary unprivileged
inventory tests. Verification still precedes third-party imports.

The [timing correction](https://github.com/salvaalba-dev/phantomyard-tools/commit/3e62422ed336edb96953793f3d3b80735b886a49)
restores strict `55 <= elapsed < 65` acceptance. Seven job checks across four
workflows passed at that test revision. Its
[disposable systemd run](https://github.com/salvaalba-dev/phantomyard-tools/actions/runs/45857111846)
reported 65 passing tests and 55.561 seconds for forced rehash plus contention,
leaving 9.439 seconds to 65. The later merged commit adjusts documentation only;
these timings remain attributed to the exact test revision and CI fixture.

Private disposable qualification and a deliberately delayed observer also
validated success within the budget and refusal beyond it. Those receipts are
held outside this public repository. CI/private timings do not establish target
timing, physical cold-storage behavior, production rollback or real acceptance.

Use the merged [production gates](https://github.com/salvaalba-dev/phantomyard-tools/blob/b424ddf2f7b04b66b2f0dab18ccfb60777b7d72c/phantomdocs/contrib/matrix-overlay/PRODUCTION_GATES.md)
and [overlay README](https://github.com/salvaalba-dev/phantomyard-tools/blob/b424ddf2f7b04b66b2f0dab18ccfb60777b7d72c/phantomdocs/contrib/matrix-overlay/README.md)
for the owning technical contract. Their historical source/merge wording must
be read with the verified merge above; it is not a request to merge #73 again.

## Production verification

On 2026-11-28 (Europe/Madrid), production applied the merged bootstrap
and its reviewed runtime manifest. The pre-deployment inventory comparison
showed no unexpected differences. An authenticated PhantomView request
returned the same Alma v25 matrix before and after the change. The read and
the successful service exit were within the existing 55-second and
65-second limits, respectively. The matrix socket was active after the change.

## Recovery

The verified service backup was restored and tested in an isolated
environment before deployment. The live acceptance check passed and did not
trigger rollback. Operators can find the archive location, checksum and
selective restoration procedure in the restricted deployment record.

# PR #73: production preparation handoff

Updated 2026-11-26. Start with [PROJECT_STATUS.md](PROJECT_STATUS.md), then this
bounded handoff. Documentation only: no host access, staging, deployment or
activation is authorized here. The source task is complete; production
preparation remains incomplete.

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

## Remaining gates

| Gate | Remaining production evidence |
|---|---|
| Target inventory and provenance | Accepted final-path candidate manifest; complete dependency/native-extension, hash, owner, mode, ACL, ancestor and link review |
| Timing and resource admission | Target verification and full startup-to-cleanup measurements within unchanged limits; fresh shared-host resource evidence |
| Isolated target rehearsal | Authorized, confined synthetic trial; guard readiness, drift refusal, contention, cleanup and recovery; notification/dependency review before dispatch |
| Rollback | Existing rollback preserved; tested restoration of only candidate-owned changes in a disposable target-representative environment |
| Real acceptance | Separately authorized installation/activation, authenticated delivery and denial, lock cleanup, audit behavior and service/socket recreation evidence |

Historical host observations did not establish acceptance of the current
candidate. Previously stopped admission runs remain stopped; they did not
execute a target rehearsal. CPU diagnostics showed variable pressure on a VPS
shared by other domains and processes. They do not justify modifying workloads
or treating any earlier proposed observation window as currently viable.

## Resume sequence and stop criteria

1. Recheck the current owning GitHub source, repository instructions and local
   changes. Compare the merged runtime bytes with the private qualified package;
   a later source/dependency/metadata change invalidates affected evidence.
2. Ask the operator for the approved private receipt location if it is not
   available in the new environment. Reconcile evidence before proposing new
   host work. Do not publish inventories, credentials, identities, routes,
   manifests or deployment/rollback receipts in either public repository.
3. Prepare a concrete bounded proposal for the missing target gates. Host
   checks are currently stopped at the operator's request. A new chat does not
   restore access or execution authorization; obtain an explicit instruction
   for any later read-only inspection or isolated target stage.
4. After any such authorization, preserve the exact reviewed budgets, health
   thresholds, monotonic measurements and independent stop/cleanup controls.
   Keep the **55-second payload and 65-second service limits**. Observation or
   cleanup lag consumes margin; accepting 80 seconds is not an alternative.
5. Stop on source/provenance, permissions/ACL, effective configuration,
   alert/dependency, health, guard, namespace, timing, denial, cleanup or recovery
   failure. Retain failed receipts. Do not hide drift by recapturing a manifest,
   widen access, raise budgets, drop production caches or automatically retry
   a failed phase without a documented correction and new run identity.

No notification changes, workload rescheduling or VPS optimization is part of
this handoff. Any future deployment/activation needs a separate explicit
authorization after its prerequisite evidence is accepted.

## Preserve completed work and exclusions

Generation 26 publication and viewer PR #12 reader cutover are already complete
according to the attributed production record in PROJECT_STATUS.md. Do not
repeat them. Preserve local edits, production permissions and the existing VPS
rollback. Do not modify PhantomBot, process Pronisa or start either operational
matrix automation as part of #73.

**Precise blocker:** the current merged candidate has no accepted target
inventory/timing and isolated-target/rollback/acceptance evidence. The next
action is GitHub/private-evidence reconciliation and a scoped production-gate
proposal, without contacting the VPS under the present instruction.

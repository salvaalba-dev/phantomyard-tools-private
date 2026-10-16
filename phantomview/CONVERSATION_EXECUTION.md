# Ordinary worker process lifecycle

The [closed environment contract](WORKER_ENVIRONMENT.md) rejects unknown launch
variables and channel credentials before execution. Store/account isolation is
still a separate activation prerequisite.

Status: inactive transport-to-process lifecycle with synthetic executables and
real isolated-account CI tests. A separate [native worker build](NATIVE_CONVERSATION_WORKER.md)
now implements the first principal/private text entry point. No service or AU
configuration is enabled. Synthetic native tests do not establish live persona,
provider or complete channel integration.

## Fixed execution binding

`ConversationProcess` owns one accepted Unix connection, uses the fixed
`WorkerInbox` to authenticate and validate its job, and starts one reviewed fixed
executable with `__conversation-worker`. It passes the complete JSON job on stdin:
persona, native channel, original sender/conversation, principal/relay/open tier,
reply audience, job ID and text. It does not turn that JSON into a plain `ask`
question. A native implementation must explicitly consume the contract and
preserve its trust, audience, screening, memory and control semantics.

The executable and all artifact parents must be protected root-owned paths with
no symlinks or group/other write permission. A fixed SHA-256 is checked at
construction, before execution and before answer release. The working directory
and its ancestors must be protected root/worker-owned directories. The runtime
rechecks the configured worker's actual UID through the existing account policy.

Configuration is trusted operator input, never fields from a job, browser or model.
The process receives a copied explicit environment, not the daemon's ambient
environment; no issuer/channel credential discovery or loading is implemented.
The operator must provision only the worker's required model credentials and
review any loaders, configuration files and dependencies the executable can read.
File ownership and an artifact hash do not establish those properties or prove
JEV correctness. A compatible native build and protected deployment provenance
remain mandatory. No new manifest declaration can substitute for source review.

One instance permits one active execution and rejects another accepted connection
while busy. It is a lifecycle component, not a daemon, accept loop, queue or new
per-persona supervisor. Trusted embedding must preserve native queueing and
control responsiveness, and bound total connections and worker slots.

## Cancellation and cleanup

The shared `bounded_process.run` uses nonblocking pipes and selector-driven I/O
instead of background pipe threads. Input, output, cancellation and deadline
remain observable while a child refuses stdin or fills a pipe. No shell is used;
unrelated file descriptors are closed on launch.

- The total deadline is monotonic and cannot be extended by output or partial I/O.
  Worker jobs retain the forwarding protocol's original deadline.
- Disconnect, unexpected additional client input, shutdown or expiry stops answer
  release. The worker closes its accepted connection and releases its execution
  slot on every outcome. Late stdout is discarded.
- Cleanup sends TERM, allows up to 250 ms for the direct process to exit, sends
  KILL to the original process group even if its leader has already exited, and
  waits up to three seconds to reap the direct child. All pipe descriptors close.
  Pipe draining after leader exit is bounded, so descendants holding pipes cannot
  leave reader threads behind or produce a successful partial answer.
- Worker stdout is bounded to the ordinary protocol's 32 KiB. Stderr is discarded
  except for the existing trusted native held marker. Held results do not release
  stdout. Invalid UTF-8 and artifact/account changes also block release.
- Public outcomes are fixed status strings without prompt, reply, stderr or raw
  exception content. No failed or ambiguous request is automatically retried.

Process groups are cleanup, **not containment of arbitrary tools**. A descendant
that deliberately starts another session can escape a group signal. Before live
tool-capable conversation execution, provision and test external containment that
the model cannot escape, including its filesystem, credentials and job lifecycle.
An unkillable kernel task can also exceed the cleanup wait; that must surface as
failure rather than a successful answer. This module makes no cgroup guarantee.

The existing restricted `Jobs.execute` now reuses the same lifecycle runner while
retaining its fixed `ask` arguments, input limits, held-marker behavior and
cancellation contract. The legacy reader/worker remains undeployed and unchanged
on AU; this source change is validated before any deployment.

## Validation and next step

Linux tests start disposable local Python fixtures, with no provider access or
real channel messages. They cover a child that ignores TERM and refuses stdin,
output overflow, closed pipes before exit, a leader that leaves inherited pipes,
and actual socket-disconnect cancellation. Protocol tests retain full tier/audience
metadata, reject peer/artifact failures before execution and discard held, late or
invalid output before reply. The existing native scoped cancellation test continues
to exercise the shared runner.

The isolated handoff job additionally verifies the complete issuer-to-worker-to-
subprocess exchange under distinct real Linux UIDs, with a protected hashed
fixture executable. A second test closes the issuer connection after the child
starts, verifies failure without an answer, and confirms the direct child was
reaped. These fixtures prove lifecycle composition, not native model behavior.

The private native JSON entry now retains native screening/JEV and ordinary
persona memory for its principal/private text slice. Next: wire the single native
ingress owner and its queue/control behavior after credential-store isolation and
installed-release review. Every model,
recovery, extraction and fallback path still belongs outside the issuer account.
Media, groups, reactions and streaming remain outside this first text-job slice.
The scoped PhantomView assistant continues to require its separate projection-
only executor and current-view ACL checks.

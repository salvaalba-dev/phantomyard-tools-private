# Ordinary conversation forwarding protocol

Status: inactive Python transport library, synthetic tests and disposable Linux
account tests. It is **not** connected to native channel loops, a model runtime,
the scoped assistant or AU. It implements the first transport slice of the
[native host isolation design](NATIVE_HOST_DESIGN.md).

## Fixed account and reply boundary

`AccountPolicy` requires Linux kernel peer credentials, a nonroot issuer account,
a different nonroot reader account and a nonroot worker account in an explicit
model UID inventory. No model UID may equal the issuer or reader. Both ends check
their actual current UID and authenticate the other process before transmitting
identity/prompt bytes or reading a request. A socket with matching filesystem
ownership does not substitute for the connected process UID.

`Forwarder` fixes one persona and worker socket. Every socket ancestor must be
root/worker owned, not group/world writable and free of symlinks. The socket must
be worker owned with no other-account permission bits. Use a protected directory
under an operator-managed runtime path, not a world-writable temporary directory.
The embedding owns listener creation, permissions and lifecycle; there is no
listener, daemon, service, credential loader or automatic account creation here.

The protected native host constructs the immutable `Route` from authenticated
channel context. It supplies the original channel, sender, conversation, tier and
reply audience. This first slice accepts **text direct conversations only**:
Telegram numeric senders or canonical PhantomChat sender hex. Principal replies
are private; open/relay replies are shared. A route object is not proof of channel
authentication when supplied by a browser, model or arbitrary process.

The host creates a random job ID and sends exactly one bounded `ordinary-turn`
frame. `WorkerInbox` fixes its persona, checks the complete request schema and
refuses unknown fields, invalid route/audience combinations, cross-persona work,
expired work, oversized input and repeated job IDs. Its bounded duplicate cache
is process-local; native checkpointing is still required across restarts.

The only reply schema is `schema_version`, `kind: ordinary-reply`, the original
`job_id` and plain `text`. Any recipient, operation, access link, scope or other
extra field invalidates the entire reply. The issuer creates `BoundReply` using
its original local route, never response-supplied routing. There is no function
here to sign, issue, redeem or deliver an access link. Model text remains untrusted
ordinary text, including any URLs it invents; the protocol cannot prove factual
correctness or prevent a model from writing misleading prose.

Reserved `/phantomview` variants are rejected on both ends. Only the separately
protected native access path can consume them for issuance. This transport must
not be exposed as an assistant identity endpoint or used to bypass PhantomView's
scoped projection executor and current-view ACL checks.

## Bounds, cancellation and execution ownership

- Frames are at most 64 KiB and nonempty text at most 32 KiB of UTF-8. Duplicate
  JSON keys and unsupported schema fields fail closed.
- A long-lived forwarder permits eight active turns and one per channel and
  conversation. Busy work is rejected; native queueing and inline `/stop` handling
  still have to be connected above this boundary.
- Each request has a maximum 120-second total deadline. Connection and writes
  are bounded to three seconds; reads observe cancellation at most every 100 ms
  while waiting for bytes. The issuer closes the socket and returns no answer
  after cancellation, expiry or an invalid response. There is no automatic retry.
- Worker receipt has a three-second frame deadline. `WorkerJob` carries the
  original remaining deadline. `reply` rejects expired work and observes EOF or
  unexpected additional input before writing. The issuer rechecks its own deadline
  and cancellation before returning a bound answer.
- These checks bound protocol waiting and answer release. **They do not terminate
  an ignoring model process.** The embedding must observe disconnect/deadline,
  cancel execution and kill/join the actual child when necessary. No execution
  callback is started by this module.

One accepted connection carries one job. The embedding must own and close it on
every path, keep one long-lived inbox per fixed persona, limit accepted sockets
and execution concurrency, and prevent a stalled client from blocking other
conversations. No listener accept loop or streaming response protocol is provided.
Public exceptions are fixed messages without raw identities, prompts, replies,
credentials or underlying exception text. Do not add frame logging in callers.

## Validation and remaining integration

Synthetic tests exercise route binding, access/recipient-field injection, foreign
job IDs, direct/audience restrictions, reserved commands, replay/expiry, frame
bounds, duplicate JSON fields, authentication order, cancellation and capacity.
The isolated handoff CI job additionally uses real Linux sockets and permanently
dropped, distinct numeric UIDs on its disposable runner. It checks a successful
exchange, malicious worker output rejection, kernel rejection of a model that
bypasses client checks, and zero prompt bytes sent to a wrong-account worker even
after socket ownership metadata is changed to match the expected UID.

The tests send no real Telegram/PhantomChat messages and perform no model inference.
They do not establish native source integration or AU configuration. Run the root
account tests only on the explicitly enabled ephemeral runner, never on the VPS.

Next: implement the worker lifecycle with bounded cancellation/process termination,
then the native ingress binding and ordinary queue/control integration. Media,
groups, reactions, streaming, memory extraction, recovery and every fallback
must be preserved by the complete host split before live cutover. Native JEV
screening remains required; it is neither implemented nor bypassed by this wire
protocol. The scoped assistant retains its separate authorized projection path.

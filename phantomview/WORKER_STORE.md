# Dedicated model credential selection

Status: protected Linux file reader and ordinary-process integration, tested with
synthetic keys. No AU file, account, service or persona vault is modified.

`worker_store.encode_credentials()` accepts only an explicitly selected map from
the [model environment contract](WORKER_ENVIRONMENT.md). It returns private JSON
bytes containing schema version 1, one fixed persona, a positive worker UID and
the selected model credentials. It never opens, decrypts or copies a source
vault. Empty/mixed selections fail. The output is secret material, not a public
manifest: do not print it, commit it, pass it through argv or add it to an audit.
Provisioning its file and ownership remains an explicit operator step.

`load_credentials()` requires the actual Linux real/effective UID to equal the
declared nonroot worker UID. The worker must have a nonroot effective group and
no supplementary root group. The file must be root-owned, mode `0640`, assigned
to the worker's effective group and have exactly one hard link. That dedicated
group must exclude issuer, reader and other model accounts. Every ancestor must
be a root-owned directory without group/world write permission.

The reader walks directories using pinned descriptors, `openat`, `O_PATH`,
`O_NOFOLLOW` and `O_DIRECTORY`; it never resolves a symlink. Relative, dot, traversal, empty
and ambiguous path components fail. The final file is opened nonblocking, then
must be a bounded regular file. Pipes, links, mutable parents, changed metadata,
invalid UTF-8, duplicate fields, unknown properties and incorrect persona/UID
bindings fail with one generic error. No exception includes a path or secret.

The document is limited to 65,536 bytes and is read afresh for each authenticated
ordinary job. `ConversationProcess(..., credential_file=...)` merges that fixed
selection into its closed launch environment immediately before starting the
child. Supplying inline model credentials as well is refused. Values are not
cached on the process-wrapper object, placed in argv or returned as job results.
Atomic root-managed file replacement supports rotation on the next turn; it
does not revoke an already running provider request. Invalid/missing documents
prevent child launch and answer release. Reviewed inline environments remain
supported for existing embeddings; choosing a protected file is explicit.

## Remaining configuration and account work

The optional [workspace plan](WORKER_WORKSPACE.md) now supplies separate fixed
configuration, profile and memory locations with Linux permission verification.
It does not provision AU or migrate existing shared history.

This reader separates a model credential file; it does not sanitize a worker's
home, generate a complete native configuration or prevent the native runtime
from reading another reachable store. Provision separate worker home, XDG,
persona-memory and native-agent locations, and review config/vault/auth fallback
paths before activation. Never reuse issuer identity/channel records or its
complete vault. Enforce exclusion from issuer files and reader/signing sockets
with kernel permissions. An environment variable or this file alone does not
establish that complete boundary.

The scoped dashboard assistant retains its projection-only executor and ACL
checks. This ordinary persona-memory worker is not its replacement. Native
channel ownership, queue/control behavior, installed-release compatibility and
AU policy/resource classification remain separate cutover prerequisites.

Disposable root Linux CI checks real worker-only read access, denial for issuer,
reader and another model account, refused worker writes, links, pipes, mutable
parents and child-environment delivery. Tests use synthetic keys and return
boolean outcomes only. Portable tests cover schema rejection, redacted errors,
fresh per-turn loading, rotation and refusing dual credential sources.

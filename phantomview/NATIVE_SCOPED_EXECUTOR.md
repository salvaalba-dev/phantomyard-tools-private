# Dedicated scoped native executor

This inactive adapter and build-only patch address a verified limitation in the
inspected PhantomBot source at `5af27060327ee8c53fe730dd8b98b6b305c62add`.
`ask` without history still loads persona identity/MEMORY and daily recall.
The native screener also reads persona files and decision/people/norm drawers.
Those inputs are not filtered by PhantomView's classified projection. Therefore
the existing AU analysis executable must not serve expanded scoped sessions.

## Dedicated build

Apply `native_scoped_patch.py` only to a disposable checkout of the pinned source.
It verifies the exact normalized ask/harness source hashes before modifying files,
then layers the existing native-only/no-tools build patch. It updates the copied
README and contributor guide together. No upstream repository or live binary is
changed. The dedicated variant is intentionally not a replacement for normal
PhantomBot behavior.

Every invocation resolves the configured persona/model first, then constructs a
fresh neutral temporary persona root, an in-memory SQLite database and a private
working directory. No original BOOT, SOUL, MEMORY, tool-hint, drawer or daily file
is supplied as prompt material. History, retrieval, fact extraction, daily recall,
prompt cache and streaming are disabled. The temporary root is removed in a
`finally` block. The build retains native-only harness selection, no tools/MCP,
disabled extensions/skills/prompt templates and the trusted screened-hold marker.

The original `makeScreener` remains active, with the configured JEV judge and
native harness fallback. It sees the complete untrusted envelope and a neutral
isolated briefing rather than private persona drawers. This intentionally changes
the judge's prior context and may cause more holds; no threshold is lowered and
no principal/trusted bypass is added. Channel notification configuration is empty
for this dedicated invocation; holds are returned to PhantomView, not sent through
the persona's normal channels. Normal PhantomBot notifications are unchanged.

## Adapter and artifact provenance

`ScopedNativeExecutor(config)` is an explicit Linux-only callable for the
`ScopedAssistant` persona executor registry. Configuration has exactly `org`,
`persona`, `executable`, `manifest` and `working_dir`. These are trusted operator
paths/settings, never browser fields. Envelope organization/persona/kind/trust must
match the fixed binding. UTF-8 input is bounded to 12,000 bytes.

The adapter reuses `Jobs.execute` for fixed argv/stdin, a fresh conversation UUID,
the process deadline, bounded output and native hold handling. It does not call
the legacy HTTP worker, start a queue or issue credentials. The existing worker
verification still requires root-owned non-writable binary contents matching
the manifest SHA-256. The scoped adapter additionally requires bounded root-owned
manifest storage, protected artifact parent directories and the pinned
`source_revision` above. In addition to the legacy restrictions, the manifest must
declare:

```json
[
  "scoped-projection-only",
  "ephemeral-persona",
  "ephemeral-memory",
  "ephemeral-working-directory",
  "native-screening",
  "daily-recall-none"
]
```

Legacy restrictions remain `native-only`, `tools-none`, `mcp-none`,
`extensions-none`, `skills-none`, `stateless`, and `screened-hold-marker`.
The old AU manifest is insufficient and is deliberately rejected. The manifest is
an operator assertion protected by filesystem ownership, not a self-authenticating
certificate or proof that arbitrary binaries implement those claims. Generate it
only for a reviewed build whose source, patch, test results and compiled hash are
known. An operator must also protect the service configuration and working root.
The binary hash is rechecked before each invocation; directory ownership remains
part of the local trust boundary, not a sandbox against a compromised root user.

## Validation and activation boundary

`native_scoped_runtime.test.ts` runs against the actual patched pinned source.
Tests place forbidden sentinels in original persona files/drawers and capture
actual harness requests. They verify prompt isolation, ephemeral working roots,
zero tools, empty history, no original memory database, native hold propagation,
and configured JEV allow/hold paths. Native harness outputs and JEV HTTP responses
are simulated; no real provider credentials, inference or human messages are used.
The dedicated CI job also compiles the Linux x64 baseline executable. Python tests
cover adapter routing, artifact changes, unsupported source rejection and holds.

This is build/source validation, not evidence of deployment to AU or of installed
runtime parity. Before activation, review the compiled artifact and manifest,
separate native-channel/model/reader accounts, register authoritative human
identities, review classifications and add authenticated transport lifecycle,
inference budgets and cancellation. The native channel isolation issue remains
open. No expanded session, grants, classifications or live service is enabled.

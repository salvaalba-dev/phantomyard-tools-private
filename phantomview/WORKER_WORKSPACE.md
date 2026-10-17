# Dedicated ordinary-worker workspace

Status: explicit provisioning plan, Linux verifier and optional process-wrapper
binding. No installation, migration or live AU change is performed.

`WorkerWorkspace` accepts a fixed absolute root, persona, worker UID/group,
reviewed brain/judge provider and model IDs, and explicitly selected profile text.
It never discovers, opens or copies an existing installation. The first profile
slice accepts only `BOOT.md`, `IDENTITY.md` and `SOUL.md`; `identity.json`, vaults,
channel records, arbitrary files and nested KB paths are refused. Operators must
review the selected text itself: an allowed filename is not secret detection or
an ACL classification. Plan objects do not display profile contents in repr.

The generated TOML has one native harness, explicit brain routing, enabled JEV
judging, no JEV router, no channel configuration and no autostarted personas.
Voice and new embeddings are disabled in this first slice. No API key, custom
endpoint, shell command or caller-provided TOML fragment is accepted. Brain
providers are limited to openrouter, openai, anthropic and google; judge providers
are typesafe and openrouter. Additional providers/settings require review.

The layout is fixed beneath the dedicated root:

| Location | Owner/group | Mode | Purpose |
| --- | --- | --- | --- |
| root | root / worker group | 0710 | Protected workspace boundary |
| config, profiles, profiles/persona | root / worker group | 0750 | Read-only configuration and selected persona text |
| generated files | root / worker group | 0640 | Exact expected contents |
| home, data, state | worker / worker group | 0700 | Independent writable runtime and memory state |

`files()` returns private provisioning bytes and `directories()` returns required
metadata. An external trusted provisioner must stage a new tree and assign these
permissions. These APIs do not create directories, chown files, import history,
change services or repair existing trees. Never print, commit or publish selected
private profile text. Provision a fresh destination instead of overwriting a live
persona directory.

`ConversationProcess(..., workspace=plan)` binds HOME, all three XDG locations,
the explicit configuration path and persona root. Its working directory must be
the planned home; conflicting locations or persona/UID bindings fail. The
existing protected model credential file remains a separate optional selection.
The verifier runs before work and again before answer release. It requires the
actual nonroot Linux UID/group, protected root-owned ancestors, exact directory
metadata, exact configuration/profile contents and no extra profile/config files.
Symlinks, hard links and redirected SQLite files fail. The worker's memory files
must be regular, single-link, worker-owned and inaccessible to group/others.

Child execution sets umask 0077 through `Popen` without changing the parent's
umask. New SQLite/runtime files therefore start private. Existing embeddings
without a workspace retain their prior launch behavior. Writable subtrees are
not recursively scanned or sealed; root-managed publication must be quiescent.
This verifier is not a mount namespace, MAC policy or general filesystem sandbox.
Kernel permissions must still exclude issuer stores and protected sockets.

## Memory and native compatibility

The generated SQLite location is independent and persists across worker turns.
It starts empty: the full shared database is never copied. Importing existing
history/facts requires a separate persona-filtered migration, review and rollback.
Nested KB/vector imports and background drain/control parity remain pending.
Do not claim existing conversation history has been migrated by this increment.

Portable tests check generated TOML, immutable profile selection and binding
refusal. Disposable Linux account tests verify read-only config, private persistent
synthetic SQLite state, denied reads by other roles and rejection of identity
records, modified config and memory links. Native CI loads a generated synthetic
config through real PhantomBot configuration resolution and its vault environment
path, with a read-only profile and synthetic model keys. It verifies that no
persona identity/vault/channel file is created. No real provider is contacted.

The scoped dashboard assistant continues to use its projection-only executor and
ACL checks. This workspace belongs to ordinary private persona conversation;
it does not replace that assistant, widen scopes or authorize live activation.
Installed-release review, complete fallback/account isolation, single channel
ownership, current AU policies and resource classification remain cutover gates.

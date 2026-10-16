# Ordinary worker environment contract

Status: enforced by `ConversationProcess`; not a store migration or live account
isolation claim. AU services, credentials and persona stores are unchanged.

The process wrapper accepts a closed environment schema and inherits no ambient
environment. Unknown keys fail before artifact verification, job receipt or
native process creation. The fixed persona/account binding cannot be overridden;
the resulting environment snapshot is immutable.

Allowed values are:

- Fixed `PHANTOMVIEW_WORKER_PERSONA` and `PHANTOMVIEW_WORKER_UID` bindings.
- Absolute POSIX `HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`,
  `PHANTOMBOT_CONFIG` and `PHANTOMBOT_PERSONAS_DIR` locations.
- An absolute-only `PATH`, without empty or current-directory entries.
- `LANG` and `LC_ALL` set to `C`, `C.UTF-8` or `en_US.UTF-8`.
- Explicitly selected `PHANTOMBOT_PI_API_KEY`, `PHANTOMBOT_JEV_API_KEY`,
  `PHANTOMBOT_GEMINI_API_KEY` and `PHANTOMBOT_OPENAI_COMPATIBLE_API_KEY` secrets.

The secret names correspond to the reviewed default native brain, screening and
embedding lookup paths. Custom instance secrets, provider aliases and additional
settings require a reviewed extension; generic prefixes and caller-selected
credential names are not accepted. Provider/endpoint configuration belongs in
separately reviewed worker configuration, not arbitrary environment overrides.

`model_credentials()` validates an explicitly selected map. It never opens a
vault, decrypts a store, imports ambient values or silently filters a mixed store.
Unknown names reject the entire selection. Errors contain neither secret names
nor values. These maps contain secrets: never log them or serialize them into
audits, public manifests or browser responses. Secrets go only in the explicit
launch environment, never argv. Python cannot guarantee memory erasure.

Channel tokens, Nostr keys, issuer credentials, endpoint overrides, proxies,
runtime loader options and unknown variables are refused. Credentials must be
nonempty single-line UTF-8 without surrounding whitespace. Total environment
size is bounded to 65,536 UTF-8 bytes; existing wrapper bounds also remain active.

## Remaining filesystem boundary

An allowed absolute path does not prove a safe store. This check does not inspect
its ownership, sanitize its contents or deny access to another account. Pointing
at the issuer home remains incorrect. Provision a separate worker home/config,
persona-memory projection, model-only credentials and isolated native agent state.
Do not copy `identity.json`, channel configuration, the complete persona vault or
legacy provider auth directories from the issuer. Native vault/config/auth
fallback paths still require validation against this projection and the installed
release. Kernel accounts must deny issuer files and reader/signing sockets.

This contract is one required check, not the complete isolation boundary. The
scoped dashboard assistant keeps its separate projection-only executor; this
ordinary persona-memory worker does not broaden dashboard ACLs.

Tests cover mixed-secret rejection, launch injection, unknown names, path
fallback, invalid UTF-8, byte limits, immutable snapshots and constructor refusal
before artifact verification. No real credential or provider is used.

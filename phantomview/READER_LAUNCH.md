# Identified reader launch and reversible cutover

Status: tested source launcher and operator procedure; not installed on AU.
This runs the existing reader assembly in its existing process. It adds no
collector, scheduler, inference service, account, credential store or ACL system.

## Protected configuration

Copy `reader-launch.example.json` into a protected operator-owned configuration
directory and replace every synthetic coordinate, including the public signer
allowlist. Use a root-owned file readable by the reader, mode `0640` or `0600`,
with a parent that is not writable by group/others. Neither links nor duplicate
JSON fields are supported. Never put private keys, channel credentials, human
contacts, tokens or transcripts in this file or in repository examples.

All fields in the example are required. `conversation_socket: null` explicitly disables the
assistant for the primary issuer. An optional protected `additional_issuers` list
adds fixed routes in the same reader; see [multiple issuers](MULTI_ISSUER_READER.md).
An additional issuer may enable its own conversation socket independently.
The optional `reviewed_knowledge` object connects existing approved KB resources;
see the configuration and protection requirements below. Omitting it preserves
the existing metadata-only reader behavior.
`reader_uid` and every `issuer_uid` must be distinct nonroot
Linux accounts. `socket_group` is the already-provisioned group allowed to reach
the reader's handoff listener, not the conversation socket group.

The native build descriptor must agree with the reader's persona, HTTPS origin,
daemon/reader UIDs and handoff path. Its optional conversation descriptor must
name this reader's `conversation_socket`, with a group allowing this reader.
Use the offline [deployment route pairing](DEPLOYMENT_ROUTES.md) to compare all
native host documents with this launch file before preparing their builds.
Review group membership explicitly: every account able to reach the native
conversation socket is trusted to submit persona questions. No group membership
or filesystem permission is changed by this launcher.

Use separate protected parent directories for the two sockets. The reader owns
its handoff parent (or root provisions it with appropriate reader write access);
the daemon owns its conversation parent. Each parent rejects group/other writes.
Provision traversal without allowing either account to replace the other's
socket. Preserve the current producer/reader publication boundary. Audit parent
access must be private to the reader; existing audit files must be mode `0600`.
The launcher sets umask `077` before creating the audit database during serving.
Permissions of existing directories and all ancestor ownership remain an
operator deployment review, not a claim established by configuration parsing.

### Optional reviewed knowledge

Add this object only after independently reviewing and approving exact captured
resources with the existing `resource_review` workflow:

```json
"reviewed_knowledge": {
  "review_path": "/var/lib/example-view/knowledge-reviews/approved.json",
  "payload_directory": "/var/lib/example-view/private-kb"
}
```

`review_path` selects one full existing approval bundle, not a draft, catalog,
source note or browser request. `payload_directory` is the existing collector's
private captured KB store. The same published organization authority, selected
snapshot and identified session gate govern these notes and the visual metadata.
This configuration grants no categories, scopes or project membership and does
not carry approvals forward to changed or newly detected notes.

The selected review, its parent, the payload directory and served payload files
must be root/reader-owned and not writable by group or others on POSIX. Parent
directories are checked too; root-owned sticky system ancestors such as `/tmp`
are permitted. Regular files, bounded sizes and paths without links are required.
Protect Windows ACLs independently from browser and model writers. Do
not point this binding at persona-owned memory or an unreviewed live KB folder.

Preflight validates the current approval without opening note bodies, creating
files, approving content or starting another service. Missing or invalid optional
configuration fails closed; it is never silently disabled. Requests authorize
before reading note bodies, then recheck current source provenance, review,
organization, content fingerprints and session. Denied, incomplete, removed or
changed notes cannot contribute titles, counts, search matches or displayed text.
Notes remain untrusted plain text; cross-references do not grant access.

After independent review, the operator may atomically replace the selected full
approval file with another valid bundle. The existing request path reloads it;
no review watcher or additional database is introduced. Retain immutable review
revisions with `save_revision` before selecting a replacement. A new authority or
metadata snapshot still requires a matching valid visual publication. Changing
the launch coordinates themselves requires restarting the reader as before.
This binding is opt-in source integration, not evidence of activation in AU.

## Commands and check boundaries

Run as the configured reader account using the reviewed Python environment:

```sh
/opt/example-view/venv/bin/python /opt/example-view/release/phantomview/reader_launch.py --config /etc/example-view/reader.json --check
/opt/example-view/venv/bin/python /opt/example-view/release/phantomview/reader_launch.py --config /etc/example-view/reader.json
```

`--check` verifies Linux account separation, existing handoff group membership,
signature dependency availability, current published authority, issuer eligibility,
approved projection generation, protected target parents and absent handoff path.
When reviewed knowledge is configured, it also validates its existing approval
and protected fixed locations without scanning note bodies.
If an assistant is configured, its native socket must already exist with the
expected daemon owner, group membership and mode `0660`. The check does not
connect to it, authenticate a human, issue a link, bind HTTP/IPC, create audit
files, run inference or publish anything. `preflight-passed` is not a successful
end-to-end conversation or a promise that the port is free. A missing, stale or
changed approval/publication refuses launch without fallback.

Serving repeats preflight, starts only the existing identified assembly on
loopback, and creates the existing metadata audit as needed. SIGINT/SIGTERM set
a stop event; the HTTP accept loop checks it at most every 250 ms when idle and
then runs the existing handoff, consultation and session cleanup. Active native
work is cancelled through that existing lifecycle; completed tool actions and
native conversation history cannot be undone by shutdown. Fresh links are needed
after restart. There is no runtime configuration reload: replace a reviewed file
and restart the one reader process. Existing authority refresh remains separate.

## AU preparation and cutover order

The [AU source-binding review](AU_SOURCE_BINDING_READINESS.md) remains the source
of dated observations, not a declaration that its blockers are now resolved.
The agreed whole-daemon trust replaces the historical isolated-worker condition.
Do not use old readiness reports as instructions to deploy replacement personas.

1. Record the current AU service definitions, exact executable paths and hashes,
   active states, selected configuration, HTTPS forwarding target and release
   pointers in a private operator record. Do not export environment secrets or
   transcripts. Verify which known AU collector and assistant units are in use;
   do not enumerate or alter other setups or the public website widget.
2. Prepare current PhantomOrg counterpart, category-zero owner and explicit scope
   declarations through the existing compatible source adapter. Obtain the agreed
   category/folder approvals and publish matching authority/index/projection.
   A legacy temporary link or an available KB note is not a classification grant.
3. Review the actual daemon release against the pinned native source and preserve
   its executable, config, persona identities, tools and memory. Stage the compiled
   compatible artifact and fixed native routes separately, with recorded hashes.
   A stock binary cannot provide this optional transport without a compatible
   build. Retain the exact previous executable for rollback.
4. Prepare the protected launch file and socket/audit directories with real,
   reviewed UIDs/groups and current public signing identities. Record only public
   fingerprints and non-secret coordinates in the change proposal. Do not copy
   synthetic IDs from the example or assume a domain-owner account is adequate.
5. Stage and approve exact changes to the existing AU daemon and reader units,
   preserving their current hardening and existing collector cadence. Review
   native/reader ordering and HTTPS origin forwarding. Installing permissions or
   switching production executables is a distinct operator-approved cutover.
6. Start the reviewed daemon variant, verify its served persona and native socket,
   then run reader `--check` as its actual account. On failure, stop and inspect;
   never unlink an existing socket or weaken permissions automatically. Start the
   reader only after the check passes. No second assistant worker is required.
7. Through the real verified channel, request a new link from the intended persona.
   Verify the resolved human, allowed/denied visual records, search/counts, category
   zero handling, issuer routing, native answer/hold/error, logout and expiration.
   Test other eligible counterparts separately; email-only identities do not gain
   Telegram/PhantomChat authentication. Confirm legacy unidentified links fail.
8. Keep the previous worker configuration intact until the connected path is
   proven. Any later retirement of a known redundant AU worker needs its own
   targeted review; never remove accumulated persona memory or credentials.

## Rollback

Stop the new reader gracefully first so it closes its own handoff and cancels
pending delivery. Stop the reviewed daemon variant before touching its socket
pathname; restore only the recorded AU executable/unit overrides and prior
reader configuration/HTTPS target, then restart their prior units in their
recorded order. Restore the previous collector drop-in if it changed; do not
blindly copy an older organization file over newer legitimate policy edits.

Verify baseline service state and the prior access flow. New reader sessions and
links do not survive rollback; ask the persona for fresh baseline links. Retain
the metadata audit and staged artifacts privately for diagnosis. A fresh source
review is required before another attempt. This procedure is prepared evidence,
not an executed rollback or an authorization to change AU access.

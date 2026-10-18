# AU identified reader launch review, 2026-10-18

Status: read-only live inspection completed; **not ready for cutover**.
Source baseline: private main `d7071d5f735d53d3faa1d2e5dd60843df0e4ac61`.
No service, account, group, permission, source, classification or executable was
changed. No link was issued and no model inference or live channel test occurred.
This records current evidence without publishing human identities or private data.

## Observed state

| Requirement | Current observation | Consequence |
|---|---|---|
| Native daemon | The selected Paco daemon is active; version `1.1.433`. Binary SHA-256 matches `native-release-review.json`. | Reviewed stock release parity is established. This does not mean the optional private integration is installed. |
| Legacy reader | Active under its existing separate domain account; application SHA-256 still matches the publication deployment record. | Preserve the current application as the rollback baseline. |
| Existing analysis worker | Active under the daemon account. | Keep it intact until the replacement connection is proven. It is not the new native conversation listener. |
| Collector | Five-minute timer active; selected oneshot inactive with its last result successful and exit status zero. | An inactive completed oneshot is normal. No collection was triggered for this review. |
| Source declarations | Four humans, three counterpart bindings, viewer policy present and category-zero owner referencing a registered human. | The previously approved source edits are present; do not recreate them. |
| Source fingerprint | `29052cfb4ae57dffb9dc0db6d882e8ce02d247b3ea1eb6702d5e54961566697a` | Matches the approved source-only application record. |
| Private authority | Parsed publication equals the selected source; publication/index snapshot digests match and the index reports no error. Publication age was 45 seconds at the sampled check. | Collector publication is currently functioning. Freshness remains a lease check on every read, not a permanent result. |
| Publication permissions | Root-owned directory mode `02750`; publication and index mode `0640` with the intended existing reader group. Selected objects are not symlinks. | Existing approved publication access is preserved; this is not a complete ancestor or per-process isolation audit. |
| Viewer scope | One explicit scope definition, three persona scope-grant entries and no human action-grant entries. | Preserve existing grants; no additional scope or action authority is proposed. |
| Registered channel metadata | Two paired humans have registered Telegram user IDs; none has a registered npub. | Metadata is not a successful native authentication test. The email-only counterpart remains channel-ineligible. |
| Presentation inventory | Eight actors, 253 note metadata entries and 150 procedures. None of the indexed note rows contains the checked category fields. | Availability counts are not classification approval. This inspection did not read note bodies or infer their classifications. |
| Selected approved projection | `/var/lib/phantomview-au/projection` is absent. | The new reader cannot start against this proposed location until current resource decisions are reviewed and published. No claim is made about unsearched locations. |
| New application entry | `identified_reader.py` is absent from the existing `/opt/phantomview-au` application root. | The tested identified assembly is not installed at that location. Do not confuse private source CI with live activation. |
| Selected runtime directory | `/run/phantomview-au` is absent. | The proposed private socket parents are not provisioned. |
| Account groups | The existing reader and daemon have different primary accounts and no shared supplementary group in the checked membership sets. Existing daemon groups serve direction/document access. | Do not silently broaden either existing group to carry viewer traffic. Numeric IDs remain in the private operational review only. |

The channel and scope counts use the actual `telegram_user_id`,
`scope_definitions` and `persona_scope_grants` fields.

## Concrete deployment proposal

This is an unactivated proposal. Follow [the protected launcher procedure](READER_LAUNCH.md)
and retain whole-daemon trust without changing native collaborative knowledge.

1. Revalidate the existing private classification draft against the current source
   and collector snapshot. Review actual content and dependencies before approving
   a projection. Retain unresolved records outside publication; do not promote
   folder hints or raw availability to grants. Keep the authoritative source and
   its existing counterpart/category-zero declarations unchanged.
2. Stage a versioned private reader release and its reviewed Python environment
   separately from the legacy application. Use the existing reader account and
   existing HTTP service; introduce no additional resident worker or scheduler.
3. Propose one dedicated AU-only IPC group for the existing reader and daemon,
   with no unrelated accounts. Use it only for the new private socket directories
   and `0660` sockets. Review actual memberships and effective process groups
   before activation. Do not add the reader to the native document/direction
   groups or add the daemon to the broad domain group.
4. Under the proposed `/run/phantomview-au`, provision separate reader-owned and
   daemon-owned parent directories, protected from group/other writes. The fixed
   handoff route should use `reader/link.sock`; conversation should use
   `native/persona.sock`. Provision traversal explicitly without allowing one
   account to replace the other's endpoint. Parent lifecycle must survive/recreate
   correctly after reboot; ownership is setup responsibility, not launcher logic.
5. Prepare matching protected launch JSON and fixed native build routes with the
   actual organization, issuing persona, scope, HTTPS origin, public signer keys,
   UIDs/GID and paths. Keep these operational artifacts private. Do not copy the
   synthetic example IDs or change the active persona globally.
6. Build the compatible private native artifact from the reviewed source using
   those exact routes; record its hash and preserve the current stock executable.
   Review the exact existing AU unit changes, sandbox path allowances and HTTPS
   loopback forwarding target before any switch. No actual unit override or
   production artifact is prepared by this metadata-only inspection.
7. After the protected projection and deployment access are approved, perform the
   recorded AU-only cutover. Start the native listener, run the launcher preflight
   as the real reader account, then start the identified reader. Exercise real
   verified-channel links, allowed/denied views, issuer routing, holds, logout and
   expiry. Retire no old worker until this evidence is captured.

## Outstanding decisions and limits

Content classification and installation access are distinct approvals. This
inspection supplies neither. It does not expand project grants, give an email-only
human a channel identity, test a live assistant or certify the complete VPS.
Existing publication remains active while preparation continues. Other setups,
the public website widget and the derived organization-copy propagation are
outside this operation. Native credentials, environment files, token files,
conversations and note bodies were not displayed or exported.

The current release parity allows preparation against the reviewed source; a
later upstream update still needs compatibility review/rebuild for the private
hook. Before activation, recheck the source fingerprint, publication freshness,
actual process groups and current approved resource generation. Use the recorded
reader/native rollback procedure if the cutover fails, preserving intervening
policy edits and accumulated native memory.

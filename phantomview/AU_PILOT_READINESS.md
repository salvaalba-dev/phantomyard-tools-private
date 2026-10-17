# AU scoped assistant readiness

Historical inspection, not a fresh live check. The replacement-worker deployment
sequence below belongs to the earlier design and is superseded by the
[collaborative viewer plan](COLLABORATIVE_VIEWER_PLAN.md). Preserve the dated
observations; do not treat them as current standard installation prerequisites.

Read-only inspection: 2026-10-16. Result: **not ready for scoped activation**.
This report describes the inspected installation, not an authorization to change
accounts, publish access policy or replace the running persona daemon.

## Observed installation

| Check | Observation | Consequence |
| --- | --- | --- |
| Running PhantomBot | `1.1.433`, executable `/opt/phantomorg/bin/phantombot`, active `phantombot-pb-paco.service` | Version alone does not establish compatibility with the pinned scoped build. |
| Reader | Active `phantomview-au.service`, user/group `aunited` | The reader has a different account from Paco, but this does not establish channel/model isolation. |
| Existing assistant | Active `phantomview-au-assistant.service`, user `pb-paco`, working directory `/home/pb-paco` | The assistant worker and normal PhantomBot share an account. The trusted issuer boundary remains unresolved. |
| Scoped installation | None of `scoped_backend.py`, `scoped_consultations.py`, `scoped-chat.js`, `native_scoped_executor.py` exists under `/opt/phantomview-au` | The tested scoped widget/backend has not been deployed there. |
| Existing build provenance | Runtime checkout and manifest commit `fb2ebebf9737c555ae0db2a29152c45f51a7f18e` | Different from scoped adapter source revision `5af27060327ee8c53fe730dd8b98b6b305c62add`; do not patch the installed tree blindly. |
| Existing binary integrity | SHA-256 matches the existing manifest | This verifies the existing artifact only, not the new isolation guarantees. |
| Artifact ownership | Runtime directory UID 0 / mode `0711`; manifest UID 0 / `0640`; binary UID 0 / `0755` | These inspected objects are root-owned and not group/world writable. Ancestor permissions and the complete deployment boundary still require validation. |
| Organization source | `/root/proyeccion/org-live.yaml` equals `/opt/phantomdocs/org.yaml` byte for byte | Both inspected copies agree. Their hash differs from the earlier inspection, so old drafts must be revalidated against current sources. |
| Human counterparts | No inspected human record declares `counterpart_persona` | The proposed human/persona associations are not authoritative live declarations yet. |
| Scoped policy | No `policies.phantomview` block | Explicit scope, project and independent action grants have not been configured in this source. |

The existing runtime manifest declares `native-only`, `extensions-none`,
`skills-none`, `mcp-none`, `stateless`, `tools-none` and
`screened-hold-marker`. It has no `source_revision` field and does not declare
`scoped-projection-only`, `ephemeral-persona`, `ephemeral-memory`,
`ephemeral-working-directory`, `native-screening` or `daily-recall-none`.
It is insufficient for `ScopedNativeExecutor`, which must reject it.

The organization already declares access levels and security categories,
including category zero with an explicit owner and a project category. Those
existing declarations must be preserved and validated during migration. They do
not replace authenticated counterpart binding, explicit scope grants or resource
classification. This inspection did not approve any KB classification, infer
permissions from titles, issue links or exercise model inference.

## Required implementation order

1. Design the native verified-channel handoff against the installed release.
   Channel authentication and issuance must be separated from model execution by
   the account boundary in [trusted handoff](TRUSTED_HANDOFF.md). A helper invoked
   from the same model account does not create that boundary. Do not introduce a
   competing channel poller or implicitly replace the normal persona daemon.
2. Prepare a disposable, pinned [scoped native build](NATIVE_SCOPED_EXECUTOR.md).
   Review source compatibility, retain native JEV, generate the protected artifact
   manifest and verify the binary hash and complete filesystem/account boundary.
   Keep the ordinary persona executable unchanged.
3. Validate the [PhantomOrg compatibility migration](PHANTOMORG_HUMAN_ACCESS.md)
   against the actual installed package. Stage counterpart, category-zero,
   scope/project and independent action declarations for the agreed policy;
   do not derive an authenticated identity from an email From field.
4. Refresh source drafts from the current organization and payload fingerprints.
   Review classifications and dependency restrictions before protected publication.
   Unclassified records remain unavailable to ordinary scoped retrieval.
5. Assemble the reader, protected audit, issuer listener and persona executor
   registry with explicit isolated accounts. Verify direct delivery, issuance,
   redemption, revocation, current-view checks and cancellation using the actual
   installed components before switching AU to scoped mode.
6. Deploy a reversible AU-only pilot with recorded artifact hashes and rollback.
   Verify allowed and denied views for each eligible human. Keep other setups and
   the public website widget outside the change.

The existing CI validates isolated test accounts, real signatures, scoped browser
lifecycle and the pinned native source with simulated provider/JEV responses.
It does not establish live AU configuration or real provider behavior.

## Inspection boundaries

Only selected AU service properties, process names, known artifact metadata,
the local version command and selected organization policy metadata were read.
No environment secrets, private keys, channel credentials or question/answer
history were displayed. No service was restarted; no account, policy, binary,
classification, live configuration or other setup was changed. The privileged
disposable-account CI driver was not run on the VPS.

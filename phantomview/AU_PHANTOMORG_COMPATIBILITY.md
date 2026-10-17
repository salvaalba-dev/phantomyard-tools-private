# AU organization counterpart compatibility review

Observed on 2026-10-17 through the authorized VPS administrator session.
Mode: read-only, limited to the selected AU organization, projection script,
viewer entry point and known launchers. No deployment, link issuance, persona
execution, policy mutation or service restart was performed. Other setups were
not inspected. Live identities, organization records and credentials are omitted.

## Observed implementation

The known organization installation directory contains a runtime launcher,
persona material and regulations, rather than the standard PhantomOrg Python
source tree used by the minimal counterpart proposal. The standard `po` and
`phantomorg` launchers were absent from the inspected system PATH and the selected
administrator/persona local-bin locations. System Python could not locate the
`phantomorg` module. This is evidence about the inspected execution paths, not a
claim that no other account or environment on the VPS has a package installed.

AU currently has a custom organization projection script. Static inspection found
ordinary YAML loading, actor/role handling and no references to the human registry,
counterpart field, policies or security category definitions. The inspected loader
returns the raw YAML mapping; it is not the standard PhantomOrg schema validator.
The projection was not executed. Raw-loader tolerance alone does not establish
end-to-end counterpart validation, preservation or enforcement.

The deployed viewer entry point imports the legacy `Gate` and `SnapshotReader`.
This inspection does not establish an active identified-session integration.
The minimal package patch therefore has no confirmed matching installed target.
It must not be applied to the runtime directory or substituted for the projector.

## Organization structural checks

| Check | Observed result |
| --- | --- |
| Registered humans | 4 |
| Explicit counterpart declarations | 0 |
| Human registry IDs unique | Yes |
| Actor-to-role references valid | Yes |
| Role-to-access-level references valid | Yes |
| Source and published organization copies identical | Yes |
| Category-zero owner matches a registered human ID | No |
| Category-zero owner matches a registered human name or role | No |

The owner comparison is an exact declaration check, not an inference or a claim
about which human should hold absolute access. A legacy free-text owner must be
resolved to the operator-approved stable human ID before identified access can
rely on it. Counterpart membership must not implicitly assign category zero.

## Custom projection purpose and preservation

The subsequent [complete script review](AU_PROJECTION_ADAPTER_REVIEW.md) confirms
that the custom script adds a consolidated role KB briefing and supplemental
organization/department/role regulation references. It describes access labels
but does not enforce ACLs. Preserve this installation-specific function while
assessing an optional reusable adapter; absence of a standard package does not
justify replacing the script. The earlier inspection was intentionally narrower.

## Consequences and next implementation increment

Keep the reviewed minimal PhantomOrg proposal as a source compatibility proposal.
Do not install a second organization engine solely to make that patch applicable.
Keep the selected organization mapping as the authoritative input for the viewer;
its human relationships belong there, not in a separate viewer identity database.

Prepare a local, non-mutating declaration preview against the actual source:

1. Resolve operator-approved counterpart assignments to existing stable human and
   actor IDs. Reject missing IDs, duplicate bindings and inferred relationships.
2. Resolve the independently approved category-zero human to an explicit stable ID.
   Preserve existing role categories and exceptions; do not grant extra actions.
3. Confirm the existing projector leaves added declarations intact and that the
   published source reaches the current viewer collector without dropping them.
4. Exercise synthetic and disposable-source consumer tests before any live edit.
   The current legacy viewer is not made identified by adding YAML fields alone.
5. Record exact owned files, original content checksums, a non-destructive update
   path and rollback before a separate controlled AU activation.

The requested human/actor relationships are operator context, not committed live
fixtures. A human with email only still lacks a verified Telegram or PhantomChat
principal; this review does not invent email authentication. Native signer/channel
embedding and the previously recorded issuer-account boundary remain unresolved.

## Validation limits

This increment records static source inspection and in-memory reference checks.
No new runtime tests are claimed for this documentation-only change. The earlier
minimal proposal passed 564 PhantomOrg regression tests plus 96 subtests, seven
proposal checks and twelve viewer identity checks on its pinned disposable Linux
source. Those results do not certify the custom installed AU projection.

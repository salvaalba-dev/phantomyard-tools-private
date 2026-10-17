# AU organization counterpart compatibility review

The subsequent [source-binding readiness review](AU_SOURCE_BINDING_READINESS.md)
rechecks the live declarations, selected reader and current knowledge metadata.
It records the remaining source bindings without changing AU or exposing live IDs.

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

## Detached declaration compatibility follow-up

Observed on 2026-10-17 after the [setup draft](SETUP_DECLARATION_PROPOSAL.md).
The installed viewer source was downloaded through the existing authorized
administrator file interface and parsed statically, without import or execution.
Its SHA-256 still matches the source-binding review:
`5c501b508f842b05afa02242d341af9db4d5a9a32de1f2feb55eacc8b60f5d2c`.
The previously downloaded complete projector matches its reviewed fingerprint:
`162b8cc1d889e4f97f96293f8157381068b44acfbbef191f6676f7656d6693e0`.
The projector was neither downloaded again nor executed in this follow-up.

### What accepts the proposed fields

The installed `read_source` and `validate_org` functions match the current tested
development functions after normalizing only `ValueError` diagnostic payloads.
The actual conditions, parsing calls and return values were retained in that AST
comparison. Both return the original mapping rather than projecting it through a
closed human/policy schema. The installed human-presentation loop matches the
tested development loop exactly. This is a narrow comparison, not a claim that
the complete installed and development applications are identical.

Local disposable-source checks exercised the detached AU proposal through the
development reader, validator, `HumanDirectory` and collector. The collector used
an explicit temporary source with profile discovery, manifests, procedure
discovery, diagnostics, default-persona and installation exports disabled. A file
open guard permitted only that temporary organization file. It produced eight
actor and four human presentation records; the proposed source was unchanged.
No live path, profile, note body, credential or native persona was read or run by
this local check. No service or VPS file changed.

The generic regression tests in `test_setup_source_compatibility.py` verify both
YAML and JSON preservation, independent category-zero resolution, raw counterpart
availability, a single selected read and the projection boundary below. Fixtures
are synthetic; the private AU organization/proposal remains outside the repository.

### What does not propagate as authority

The current collector deliberately serializes each human with only `id`, `org`,
`name` and `role`. It omits counterpart declarations, channel identities and the
organization's policy block. That presentation index cannot substitute for the
authoritative organization document. Copying the private registry or complete
policies into the browser payload is not the integration fix.

The identified backend must load the selected **raw organization source** through
its protected authority loader and resolve current PhantomOrg policy there.
The collector remains the presentation/provenance input; it is filtered before
delivery by the identified path. Adding fields to YAML does not install that
path, change the legacy gate, authenticate a sender or enable the assistant.

The custom role projector reads the YAML mapping and renders role/persona data.
Static review confirms that its renderer does not read `humans` or `policies` and
its writer targets the selected persona note rather than rewriting the input
organization. No projector modification is required merely to accept these new
declarations. The existing projector is not an ACL evaluator and must not become
the source of human authentication. Its organization fingerprint includes input
bytes, so a later authorized regeneration can change generated markers even when
the role text is otherwise unaffected; no byte-identical generated-note claim is made.

The viewer's selected index points directly to the authoritative source. The
separate published organization copy was previously byte-identical, but its
refresh/synchronization mechanism has not been established. Do not assume an edit
automatically updates every consumer or update both files blindly.

### Decision and remaining gates

The detached declaration shape is compatible with the inspected raw loader and
presentation schema. **It has not been applied or activated.** Keep the projector
and native collaborative memory intact; no new organization engine, background
service or duplicate ACL database is required by this finding.

Before a live pilot, complete the protected raw-source binding and verified native
channel issuance, review content classifications, check current source drift and
the published-copy consumer path, and record the exact migration/rollback files.
The existing legacy viewer remains unchanged and is not evidence that identified
sessions or native assistant routing are already working.

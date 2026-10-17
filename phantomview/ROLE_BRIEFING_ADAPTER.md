# Optional role briefing adapter foundation

Status: private deterministic preview implementation. The separate optional
[local note publisher](BRIEFING_PUBLICATION.md) is now available for trusted
operator use. No AU deployment, live note write, model call, viewer route,
background service or module activation.

`role_briefing.prepare_briefing(organization, persona, supplemental=None)` prepares
one actor's structured briefing from an explicit PhantomOrg mapping. It reuses
PhantomOrg's shape validator, reference checks, model and `merge_access` resolver;
it does not introduce an alternative category or grant evaluator. A compatible
PhantomOrg Python package is an optional dependency for this adapter only. Missing
support produces a clear error rather than a permissive fallback. The earlier
selected-path inspection did not establish such a package in live AU.

```python
from role_briefing import prepare_briefing

supplemental = {
    "schema_version": 1,
    "organization_id": "example",
    "references": [{
        "document_id": "board-handbook",
        "applies_to": {"kind": "role", "id": "lead"},
        "version": "1.0",
        "category": "category-2",
        "owner": "owner",
    }],
}
briefing = prepare_briefing(organization, "coordinator", supplemental)
```

The caller supplies the already selected trusted organization mapping. Example
IDs must exist in it; the synthetic organization in `test_role_briefing.py` shows
the required relationships. No source discovery or path reading is performed.

## Implemented behavior

- Produces organization, department, actor and role data, reporting relationships,
  escalation routes and declared communication settings.
- Keeps base categories, role exceptions and actor exceptions separate using the
  existing resolver. Counterparts are explicit IDs; reporting text never infers
  them. It does not assign category zero, issue sessions or change any grant.
- Selects supplemental document references applying to the current organization,
  department or role. Rejects other organization IDs, missing targets, duplicate
  references, arbitrary paths and unknown configuration fields.
- Accepts only existing information categories or explicit null. Category zero
  cannot classify a document. Owners are existing organization/human/actor IDs,
  not proof of a document signature or of caller identity.
- Returns a detached `private-preview` with content fingerprints and no clock
  fields. Identical input produces identical output and revision; relevant source
  or supplemental changes invalidate the revision. This enables a later publisher
  to avoid unchanged writes; no publisher is implemented here.
- Bounds JSON-compatible input/output to 1 MiB and supplemental references to 256.

## Disclosure and compatibility boundaries

The result can include private declared organization/channel/contact metadata.
It is not an authorized viewer response, ProjectionCatalog, session or module
manifest. Never serve or publish the entire preview based only on its status,
selected persona, a supplemental owner or a category label. Null classifications
remain private unresolved references, not public documents. Fingerprints establish
consistency, not source authenticity, authorization or signature validity.

Only reference metadata is retained. Document existence, contents, integrity,
signatures, document namespace/inbox adaptation and safe linked-body retrieval are
not implemented. The adapter validates shapes and cross-references; it does not
replace PhantomOrg's complete CLI validation or resource authorization. Native
collaborative memory is not read, copied or isolated by this component.

The supplemental contract uses stable IDs and explicit target kinds. It does not
silently reinterpret the installation's legacy sidecar format. A future selected
migration adapter must map that format, report unresolved references and preserve
useful AU behavior before any replacement is considered.

## Next increments

1. Implemented separately: [optional local note publication](BRIEFING_PUBLICATION.md)
   with owned-marker handling, exact manual-content preservation, explicit targets,
   per-note atomic replacement and unchanged-input no-op. Live binding remains pending.
2. Authorized record adapter using existing PhantomOrg classifications, dependency
   checks and viewer publication boundaries. Unresolved references cannot be exposed.
   The [reviewed knowledge detail reader](REVIEWED_KNOWLEDGE_VIEW.md) now opens
   existing approved notes under the same identified session. Briefing publication
   alone does not classify or expose a note; record discovery remains pending.
3. Additive declarative viewer sections over those records. Existing module
   manifests cannot execute this adapter or grant access. Reuse setup/refresh rather
   than add another scheduler or resident agent.

## Validation

Eleven synthetic tests cover deterministic detached output, both exception origins,
invalid/duplicate references, absent dependency, input bounds, source revisions,
explicit counterpart display, private unclassified metadata and supplemental grant
rejection. Dedicated pinned PhantomOrg CI runs these tests without optional skips.
Standard viewer CI may skip the package-dependent tests when PhantomOrg is absent;
the boundary and missing-dependency tests still run. No raw AU script, sidecar,
organization mapping or generated private preview is committed.

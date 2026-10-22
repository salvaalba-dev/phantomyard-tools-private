# Document refresh batches

`document_refresh.prepare()` prepares all documents selected by an explicit
organization matrix in one pass. It resolves the native current revision and
generates the existing collector bindings with their current SHA-256 values.
Operators no longer need to copy fingerprints into individual bindings by hand.
It adds no service, dependency, HTTP endpoint or document management system.

The matrix identifies existing documents, personas, categories and formats:

```json
{
  "schema_version": 1,
  "organization": "example",
  "documents": [{
    "urn": "urn:example:doc:policies/conduct",
    "actor": "coordinator",
    "category": "category-2",
    "format": "html-text"
  }]
}
```

This is a mapping of existing classified sources, not another ACL. Its category
must exactly match the current native document; no numerical hierarchy, folder
name or owner grants a human access. The existing PhantomOrg projection review
and session authorization remain authoritative. Binary mappings also require
the existing reviewed `display` fields. Missing codes or versions are omitted.

Call the adapter from the existing operator or collection workflow:

```python
from document_refresh import prepare

plan = prepare(manifest, manifest_path, matrix, actors, search_policy,
               previous=config.get('working_documents', []))
```

An offline command uses the same bounded, stable, protected snapshot reader as
the existing publication inputs and prints a plan to standard output:

```sh
python3 phantomview/document_refresh.py --manifest /protected/store/manifest.yaml \
  --matrix /protected/document-matrix.json --snapshot /protected/snapshot.json \
  --config /protected/collector.json
```

Keep any captured output private. The snapshot must have a top-level `actors`
array. No configuration or source file is written by this command.

Inputs are already parsed, protected snapshots supplied by the existing loader.
The adapter does not open configuration paths, connect to Drive, verify native
cryptographic identities, consume inboxes or register documents. PhantomDocs
continues to own intake, verification, filing and append-only version history.
`source` locates its existing local blob store; all source reads reuse the
collector's path, size, content hash, format, ownership and content checks.

The deterministic plan contains:

- `prepared`: validated current bindings marked `add`, `refresh` or `unchanged`,
  plus native category assertions and payload fingerprints.
- `pending`: fixed reason codes for unmapped documents, changed classifications,
  missing sources or validation failures. Ineligible source identities and private
  paths, error messages and document bodies are not exported.
- `removed_bindings`: prior selections no longer present in the matrix.
- `excluded_bindings`: all prior selections absent from the prepared batch,
  including changed classifications, missing sources and newly hidden records.
- `input_revisions`: exact manifest, matrix, persona snapshot and prior-binding
  fingerprints for the downstream preparation lease.

The existing sixteen-document collector limit is retained. Invalid matrix schemas
or ambiguous native histories abort the whole batch. Individual bad sources remain
pending while valid sources are prepared; a downstream publisher must explicitly
handle removals and exclusions and must never retain an old version as a fallback.

## Activation boundary

This adapter only prepares a batch. It does **not** overwrite configuration, stage
original files, approve a projection, update the active pointer or restart a
service. A prepared binding is not a publication approval. New or changed bytes
still invalidate the previous source-bound projection approval.

The next integration step is to feed this plan into the existing protected
collector/publication workflow, stage exact originals and classify the resulting
document and persona-link records under the existing PhantomOrg matrix. Automatic
publication requires an explicit, reviewed policy for those transitions; merely
seeing a document in a native manifest is not that policy. Until that integration
is configured, production keeps its existing explicit bindings and fail-closed
behavior. Do not describe batch preparation as active automatic publication.

For automatic comparison on the existing collector schedule, see
[Periodic document observation](DOCUMENT_WATCH.md). That optional hook writes a
private change report even when stale bindings prevent normal collection. It
does not activate the publication transitions described above.

Organization and project inputs remain separate. No installation-specific matrix,
document, source path, human identifier or operational receipt belongs in this
repository. Review the initial mapping as a batch; handle later exceptions using
the existing document intake rather than creating a parallel queue in PhantomView.

# Selected working documents

The existing persona card can display a folder tree and read authorized working
documents beside its labels. IDENTITY and SOUL remain separate. No layout, web
route, service or dependency is added by this source adapter.

Collection is disabled by default. An operator may select up to 512 exact
PhantomDocs document URNs in the protected collector configuration. Each format
counts as one binding; refresh matrices use the same limit. Selection remains
explicit, and per-file size, content validation and ACL checks still apply:


```json
{"working_documents": [{
  "urn": "urn:example:doc:policies/conduct",
  "actor": "coordinator",
  "sha256": "<reviewed source SHA-256>",
  "format": "html-text"
}]}
```

The selected persona's declared role must be an owner of the exact document in
the selected organization's manifest. This association does not grant access.
Existing projection review must explicitly classify the document and its persona
relationship against PhantomOrg. The adapter never infers ACL from ownership,
folder names, prose or a numeric category hierarchy.

Only one local blob location under that manifest's `blobs/` tree is supported.
Symlinks, ambiguous versions, unresolved or circular folder ancestry, incomplete
or changed sources, non-UTF-8 or credential-like text and text sources larger
than 128 KiB are rejected, except for the explicitly enabled self-contained HTML
original allowance described below. The configured fingerprint binds the complete source.
The complete encoded text payload is additionally bounded to 32 KiB so it fits
inside the existing projection record limit.
Supported input modes are `markdown`, `text/plain` and `html-text`. HTML extraction
uses the standard library parser to produce plain text; styles, scripts, comments
and document-head content are omitted. It never renders HTML, executes document
instructions or retrieves external assets. Remote locations are excluded; reviewed
binary originals are described below.

The existing `profile_fields` export carries the selected text and folder labels
only through the reviewed projection. Host paths and raw HTML are not exported.
Source and extracted-text fingerprints remain bound into the review. Changed
documents require another source review before the binding is updated. Authorized
clients use the existing document reader, freshness checks and global search.


## Opening reviewed originals

Set `"original": true` on an existing explicit working-document binding to opt
that one document into original-file delivery. The current manifest entry must
have the exact reviewed `contentHash` and real byte `size`. Duplicate URNs,
changed fingerprints and conflicting explicit version metadata fail closed.
The reader never chooses a version by filename, timestamp or numeric ranking.
A newer current entry requires renewed review and publication; an old copy is
not silently substituted when the source changes.

The collector exports only bounded display metadata: the document name, optional
code and version, media type, real byte count and source fingerprint. Known HTML
metadata uses its unique H1 and unique `doc-code` block. Missing version metadata
is omitted. The UI displays `Name Â· Code Â· Version (size)` on one line, using
B, kB, MB or GB automatically with at most one decimal. Long labels retain the
complete accessible name and hover title. Profile documents keep their reader.

The operator stages an exact reviewed copy under
`<projection_root>/originals/<source SHA-256>`, in a protected directory readable
by the existing reader account. No original, local host path or private source
configuration belongs in GitHub. Original copies are independent of immutable
projection generations; a copy alone never grants access. The existing server
serves `/api/document-original/<opaque resource ID>` only after the current
identified session and projection authorize that exact document. It verifies
size, complete content hash and regular-file integrity, then rechecks session
and resource authorization before releasing bytes. No filesystem path or URL
is accepted from a browser. No extra service or dependency is introduced.

HTML and images open directly; PDF originals download with a readable filename
for consistent handling by browsers without an inline PDF viewer. No original
is converted or rewritten. Text originals that strictly decode as UTF-8 declare
`charset=utf-8` in their response media type so browsers display accented and
non-ASCII characters correctly. Other encodings retain the original media type;
the reader does not guess, transcode or repair stored bytes. Binary media types,
fingerprints, sizes and document versions remain unchanged. Responses
are private and non-cacheable, disable MIME sniffing and referrers, and apply a
sandbox policy without scripts, same-origin privileges, external assets, forms
or embedding. HTML therefore retains its original print headers; the viewer no
longer duplicates them in a separate transcription. External fonts are blocked.
The collector supports HTML, Markdown and plain-text inputs, plus explicitly
reviewed PDF, PNG and JPEG originals. Binary files are not decoded or transcribed;
only their reviewed display metadata enters the searchable projection.
Original delivery is bounded to 32 MiB; larger files and range streaming require
a separate adapter. Full originals load only on demand, never in `/api/state`.


## Reviewed binary originals

PDF, PNG and JPEG bindings require `original: true` and an explicit reviewed
`display` object. The display metadata is bound to the same complete source
fingerprint as the original. A friendly label may distinguish alternate formats;
no relationship or version ordering is inferred from similar names.

```json
{"working_documents": [{
  "urn": "urn:example:doc:policies/conduct-pdf",
  "actor": "coordinator",
  "sha256": "<reviewed source SHA-256>",
  "format": "application/pdf",
  "original": true,
  "display": {"title": "Code of conduct (PDF)", "code": "EX-20260101-001", "version": "v1.0"}
}]}
```

A title is required; code and version are optional and must never be invented.
If the current manifest also declares a code or version, conflicting reviewed
metadata is rejected. The collector checks the exact manifest hash, real size,
media signature and file ending, while retaining existing owner, scope, category
and filesystem checks. Binary reads are bounded to 32 MiB; large originals never
enter `/api/state`. Search and assistant projection evidence contain only the
reviewed title and reference, not the binary document's full contents.

Signature checks do not replace content review or a full format parser. Operators
must verify that each exact original opens correctly and that its contents match
the intended classification before publishing. Binary contents are not scanned
for credential-like text or automatically declared safe by the collector. No
OCR, PDF conversion, third-party retrieval or new dependency is installed. The
reader uses the same original-file route, current session authorization and
content fingerprint checks as the text-original pilot.


PDF downloads preserve the complete original bytes and all existing response
protections. A bounded ASCII download filename derives from the reviewed code,
version and title; it is display metadata, never a source path. This avoids blank
PDF tabs in browsers without a built-in PDF renderer. HTML sandbox behavior is
unchanged. The original-file endpoint and its ACL remain the same.


Self-contained HTML originals may include embedded logos. An explicit
`html-text` binding with `original: true` permits a complete source up to 1 MiB;
ordinary text sources remain limited to 128 KiB. Extracted text retains its
existing bounds, credential screening, complete fingerprint and ACL checks.
No remote asset is fetched by collection or delivery. A correction belongs in
the existing document intake and native PhantomDocs version chain: preserve the
previous original, record the reason and previous fingerprint, and review the
new current fingerprint before changing a viewer binding. A presentation-only
HTML revision does not change the official PDF edition. PhantomView does not
rewrite source documents or create an independent document history.


Native document revisions are resolved by a complete, bounded linear history,
not by array position. Multi-version records require unique identifiers, complete predecessor links
and consistent document identity. An explicit `currentVersions`
reference, when present, must point to the lineage tip. Duplicate, forked,
truncated or disconnected histories fail closed. Both document
metadata and selected original bindings use the same current-node resolver;
older versions remain in the native manifest and audit trail but do not create
extra viewer rows. A stale selected fingerprint still requires a fresh review.

This resolver checks structure and current-version selection, not native MACs or
signatures. Those remain the responsibility of PhantomDocs and its existing
verification tools. The collector continues to bind the exact reviewed current
source bytes by SHA-256; it does not reimplement a native cryptographic scheme.

For deterministic batch preparation from an existing document matrix, see
[Document refresh batches](DOCUMENT_REFRESH.md). The offline adapter resolves
current fingerprints and reports exceptions without publishing or changing ACL.


## Logical documents and formats

A document edition may have several independently registered original formats.
An optional `document_group` in each selected working-document binding declares
that relationship explicitly. It contains an organization-bound `id`, a `title`,
a `version`, and an optional `code`. For example:

```json
{"id":"urn:example:document:conduct","title":"Code of conduct","version":"v1.0","code":"EX-001"}
```

Members must match the declared version and code, belong to the same actor and
folder, and have distinct media types. Similar names or matching codes alone
never establish membership. This is an adapter mapping for sources without a
native format-family relationship; it does not rewrite native identities,
originals, fingerprints, revision history, or the registry.

The viewer presents one expandable edition with a link and size for each visible
format, preferring PDF first when available. Every link keeps its own current
session, resource ACL, and fingerprint checks. Group membership never reveals an
unauthorized format or grants access. Display counts count editions; server
resource counts and navigation validation retain the individual authorized files.
Existing bindings without this declaration retain their current presentation.

Batch preparation validates these declarations alongside current originals and
reports inconsistent groups instead of guessing. Publication still requires the
existing reviewed matrix and approval; this change does not automatically ingest
all documents or bypass either organizational or project intake.


## Shared persona associations

An explicit binding may retain its existing `actor` and add `related_actors`,
for example `"actor": "coordinator", "related_actors": ["project-lead"]`.
At most eight unique personas, including the primary actor, may be selected.
Every selected persona must belong to the same organization, be eligible for
collection, and hold a role listed in the native document's owners. Missing,
ambiguous, hidden or unrelated personas reject the binding rather than creating
partially verified associations. The same checks apply to batch preparation.

Collection reads and represents the document once and emits one explicit link
per selected persona. Grouped formats must share the same complete persona set.
These are document-use associations, never ACL grants: the document and every
relationship still need the existing projection review, classification and
per-session authorization. Reader cards render only the currently visible
associations and keep one resource and original-file endpoint. Existing single
persona bindings produce their previous payload and link unchanged.


## Verified Drive copies and original-only text

An optional collector `working_document_cache` names a protected, absolute local
directory of hash-named copies. It is used only for a selected native `gdrive`
location with a valid file reference. The collector never contacts Drive, changes
native locations, or ingests documents. An existing authorized download tool must
prepare copies separately. Missing or changed copies fail validation; there is no
network, path or stale-content fallback. The current native fingerprint, size,
owner, category, eligibility and downstream publication review still apply.
Cache directories and files reject symlinks, group/world writes and unexpected
owners on POSIX. Originals remain bounded to 32 MiB and are rehashed on collection.

A binding can explicitly set `original_only: true`, `original: true`, and reviewed
`display` metadata. Text then contributes only its reviewed title, optional code
and optional version to the projection. The complete original remains available
through the existing authorized original-file endpoint; it is not truncated or
indexed in full. UTF-8, NUL and credential-like text checks still apply to the
complete source. Existing inline-text bindings retain their behavior.

A format group may omit `version` only when all original descriptors also omit
it. This means the formal version is not declared, not that a version is inferred
from a filename or invented. An empty version is invalid. The explicit member
fingerprints and normal publication review still bind the selected edition;
registered version changes cannot be hidden by an unversioned group. A reviewed
label can retain a draft status without changing native records or implying
approval. Observation and batch planning accept the same optional cache and
original-only binding; automatic observation still does not publish documents.

### Restored local stores

A native local document may retain its previous absolute location after a store
has moved. When that location is absent and has the exact
`blobs/<hash-prefix>/<content-hash>` layout recorded by PhantomDocs, the reader
may use the same hash-addressed blob inside the explicitly selected store.
Present external paths, permission failures, symlinks, noncanonical locations
and external backend references are never redirected. Existing owner, category,
current-version, size, format and fingerprint checks still apply. The native
manifest, version history and original bytes are not modified by this lookup.

## Protected MP4 recordings

An explicitly selected `video/mp4` binding must set `original: true`,
`original_only: true` and reviewed `display` metadata. The current native size,
content hash, owner, category and normal projection review remain mandatory.
The collector publishes only the reviewed label and fingerprint, never media
bytes. Local sources and separately prepared verified Drive copies use the same
existing source protections. There is no public Drive redirect, automatic
download, new service or alternate identity policy.

MP4 originals have a separate 8 GiB ceiling; other originals retain their 32 MiB
ceiling. Collection checks the complete top-level container structure and hashes
the entire source in 256 KiB blocks. This is an integrity and container check,
not a codec decoder or malware scan. A valid file-type box and complete metadata
and media boxes are required. No version is inferred from a recording filename.

The existing authenticated original endpoint serves a whole recording or one
HTTP byte range, including open-ended and suffix ranges. Partial responses use
206, Content-Range and Accept-Ranges; malformed, duplicate, multiple and
unsatisfiable ranges return 416 without opening the file. Authorization precedes
file access and is checked again after hashing and before every bounded write.
Expiry, logout, policy or projection changes and file mutation stop the stream.
After headers have been sent, failure closes the connection instead of appending
a second HTTP response. Responses are private and not cached by the browser.

The reader caches at most 32 successful complete-file hash verdicts on POSIX,
keyed by the reviewed digest, store path and full file identity, size, times,
owner, group, mode and link count. Each request still opens and checks its exact
protected file, and every chunk checks the open file's identity. An altered file
must pass full verification again. Windows rehashes on each request because its
file timestamp semantics do not provide the same change identity. The cache
contains no media bytes, session grants or remote locations.

This feature alone does not select or publish any recording. Operators must
prepare exact verified private copies, review the existing native ACL and select
the intended persona links through the normal publication procedure. Existing
transcripts and summaries remain independently authorized document formats.

## Download-only Excel originals

Explicitly reviewed `.xlsx` originals use the media type
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and require
`original: true`, `original_only: true` and reviewed `display` metadata. The
existing 32 MiB original-file limit, native current-version fingerprint, owners,
PhantomOrg ACL and private-store checks apply. Only metadata is published or
searched. No cells are extracted, formulas evaluated, workbook formats changed
or previews generated. No additional dependency or service is required.

The package directory must identify an unencrypted XLSX workbook, with unique
member names and at most 4,096 entries. Both VBA payloads and Excel 4 macro-sheet
paths are rejected. The UTF-8 `[Content_Types].xml` declaration is bounded to
64 KiB, rejects DTD/entity declarations and macro/VBA media types, and must
declare the ordinary XLSX workbook type. No worksheet contents are read.
Macro-enabled packages, legacy `.xls`
files and `.xlsm` files are not supported by this initial XLSX change. This is a
bounded package identity check, not full workbook validation or a malware scan.

Clicking the existing filename link displays an English notice that Excel has
no preview and the original will be downloaded. After dismissal, the same
authenticated original endpoint delivers the exact reviewed bytes as an
attachment, with private no-store and nosniff headers. There is no additional
download button or download audit feature. Other formats keep their behavior.
This support alone does not ingest, select or publish any workbook.

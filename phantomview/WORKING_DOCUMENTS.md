# Selected working documents

The existing persona card can display a folder tree and read authorized working
documents beside its labels. IDENTITY and SOUL remain separate. No layout, web
route, service or dependency is added by this source adapter.

Collection is disabled by default. An operator may select up to sixteen exact
PhantomDocs document URNs in the protected collector configuration:

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
is omitted. The UI displays `Name · Code · Version (size)` on one line, using
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
is converted or rewritten. Responses
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

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
or changed sources, non-UTF-8 data, credential-like content and sources larger
than 128 KiB are rejected. The configured fingerprint binds the complete source.
The complete encoded text payload is additionally bounded to 32 KiB so it fits
inside the existing projection record limit.
Supported input modes are `markdown`, `text/plain` and `html-text`. HTML extraction
uses the standard library parser to produce plain text; styles, scripts, comments
and document-head content are omitted. It never renders HTML, executes document
instructions or retrieves external assets. PDFs and remote locations are excluded.

The existing `profile_fields` export carries the selected text and folder labels
only through the reviewed projection. Host paths and raw HTML are not exported.
Source and extracted-text fingerprints remain bound into the review. Changed
documents require another source review before the binding is updated. Authorized
clients use the existing document reader, freshness checks and global search.

# Human-readable record profiles

PhantomView presents the current authorized organization, department, role,
persona and human records as compact profiles. Contacts and related records sit
in two columns when space permits and stack on narrow screens. Responsibilities,
declared tools and linked documents follow without nested dialogs. Secondary
institutional metadata is expandable. Missing information is identified rather
than inferred from names, job titles, directories or another person's contacts.

## Existing authorization and sources

Opening a profile rereads the authorized state and record through the existing
endpoints. The state is checked again before display; changed scope, policy or
view invalidates the read. Closing, navigating, hiding the workspace or logging
out invalidates outstanding reads. No new raw-source endpoint is introduced.
Relations use only visible opaque endpoints from that projection. Persona
responsibilities come from explicitly assigned roles, not managers or peers.

Document associations use visible relationship endpoints. Reviewed KB notes may
also match the exact organization-qualified persona identity supplied by their
existing reader. Titles, filenames and partial identity matches are not joins.
Documents open inside the same profile and use their existing authorized detail
endpoint. Markdown is displayed as plain text; HTML and model instructions are
never executed. Document metadata alone does not imply that its body is available.
Root profile Markdown is not discovered, copied into KB or classified by this UI.

The assistant button keeps the existing behavior: set the selected record as
context for the already configured persona. It does not submit a message,
change tools, expand knowledge permissions or create another assistant service.

## Optional metadata review

The existing adapter remains byte-compatible by default. An explicit
`--profile-fields` flag adds selected profile metadata to a **new unclassified
draft**, alongside the optional `--organization-links` mode:

```sh
python source_adapter.py --snapshot /private/collector.json \
  --organization /private/org.json --output /private/profile-draft.json \
  --organization-links --profile-fields
```

This selects bounded descriptions, responsibilities and configured languages.
Contact fields are restricted to website, email, public npub and Telegram bot
username. Unsafe schemes, URL credentials and malformed values are omitted.
Human login identifiers and email are not added by this adapter. Institutional
legal metadata is limited to legal name, legal form, organization tax ID, country
and founding date; founder identifiers, personal addresses and fiscal documents
are not copied as part of a generic organization profile.

To collect those organization fields from an existing source, an operator may
explicitly enable `profile_metadata: true` in the collector configuration. It is
off by default. This changes source fingerprints and must be coordinated with a
new review and publication; it is not a live configuration migration.

The approval records `profile_fields: true` and rechecks that exact mode on every
publication/read. Existing approvals cannot silently authorize enriched payloads.
Review the changed contents, assign existing declared categories/scopes and secret
status, then use the existing approval/publication lease. A missing review never
falls back to an unfiltered collector export.

No PhantomOrg schema, live organization document, category definitions or
resource classifications are changed by these display and adapter changes.
Organization metadata must come from the installation's own supported source.
Custom fields tolerated by a raw AU source are not claimed to be upstream schema
fields. Adding them to standard PhantomOrg still requires a coordinated schema,
typed-model and compiler change. No AU-specific values are embedded in this code.

## Verification

Model tests cover exact joins, assignment-only responsibilities, missing values,
unsafe contact links and exact reviewed-note ownership. Dialog tests run the
actual render/read functions against inert DOM and HTTP fixtures, checking plain
text, in-place reading, current-view binding and cancelled/stale responses.
Adapter and publication tests verify opt-in selection, excluded sensitive fields,
unchanged default behavior and new approval fingerprints.

## Opt-in profile document sources

The collector option `profile_documents: true` selects only complete `IDENTITY.md`
and `SOUL.md` files from explicitly configured local persona roots. Memory, applied
prompts, tool configuration, KB notes and remote personas are excluded. Collection
is off by default and assigns no category. Files are bounded to 16 KiB, decoded
as UTF-8, checked for links, nonregular files, hard links, changing reads, POSIX
group/world write permissions, source exclusions and obvious credential patterns.
Pattern checks are a preliminary exclusion, not proof that a file contains no
sensitive information. Operators must review the exact contents. Windows source
ACLs must be protected by the operator; POSIX mode checks are not Windows ACL checks.

The source adapter option `--profile-documents` includes each selected text as an
independent unclassified document and an exact persona/document relationship.
Both require explicit category, scope, project and secret decisions before
publication. Their mode and content fingerprints survive approval and are checked
on every current projection read. Changed, removed or newly excluded source text
invalidates publication; old approvals never approve future file contents.

Profile bodies have separate source provenance. Merely collecting them does not
alter the existing metadata-only adapter output or grant access through the parent
persona. Existing ACL decisions still filter document records and their links.
The current card reader displays the authorized Markdown as plain text in place.
No native persona instructions are changed or executed, and no service is added.

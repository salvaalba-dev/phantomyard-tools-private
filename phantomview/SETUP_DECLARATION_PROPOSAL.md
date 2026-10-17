# Detached setup declaration review

`setup_proposal.py` prepares a **private offline draft**, not an installation,
migration or access grant. It reuses the existing PhantomOrg policy reader, human
directory, access preview and folder-classification proposal. It introduces no
service, scheduler, model call, native memory copy or second ACL authority.

## Inputs and ownership

Supply the selected authoritative organization YAML, its collector index, the
exact configured source path, explicit stable human/persona IDs and the independent
category-zero human owner. The tool does not infer identities from display names,
email, a role title or a default persona. The caller must establish those mappings.
Collector metadata is discovery evidence only; matching paths do not prove that
the collector and organization were captured atomically or that content is approved.

The first-setup draft changes only:

- The explicitly requested `humans[].counterpart_persona` fields.
- `policies.security_categories.category-0.owner`, using a registered human ID.
- A new `policies.phantomview` organization scope and explicitly selected persona
  scope grants, with **empty** project grants and human action grants.

Existing categories, labels, access levels, roles, actor exceptions, channel
identities and all unrelated source fields are preserved. Conflicting counterparts,
duplicate relationships, unknown references and an existing viewer policy stop the
proposal rather than being overwritten. The category-zero owner may be unbound to
any persona. Its independent information privilege does not grant actions; existing
secret exclusions are unchanged.

Organization-scope suggestions need explicit review. They do not classify every
resource as organizational or turn project categories into project membership.
This first-setup helper intentionally does not guess department/project boundaries;
those require a separate explicit proposal. The viewer fields remain private
extensions, not a claim of compatibility with every installed PhantomOrg release.

## Example

Run from the `phantomview` directory. All paths and identities below are synthetic.
The output directory must be new and outside the repository.

```sh
python setup_proposal.py \
  --org /private/input/org.yaml \
  --index /private/input/index.json \
  --source /srv/example/org.yaml \
  --counterpart owner=coordinator \
  --counterpart secretary=administrator \
  --counterpart accountant=treasurer \
  --absolute-owner owner \
  --organization-persona coordinator \
  --organization-persona administrator \
  --organization-persona treasurer \
  --output /private/reviews/first-setup
```

PyYAML is required by the existing organization-reading path. Input files are
bounded to 16 MiB each; principal inventories to 2,000 entries and knowledge
metadata to 20,000 notes. The selected index must identify exactly the supplied
organization/source and its complete actor set. These are format/reference checks,
not cryptographic collector authenticity or content authorization.

## Private outputs

| File | Purpose |
|---|---|
| `index.html` | Offline counterpart/category/channel-type summary and draft status. |
| `classification.html` | Exact-folder candidates and review requirements. |
| `proposal.json` | Full detached source, matrix, candidates and input fingerprints. |
| `proposed-org.json` | Proposed organization document for source review, never auto-loaded. |

The JSON files retain private source data, including registered contact metadata.
Keep the entire output directory private and **never commit or upload it**. The
summary HTML omits contact values but contains organizational identities and folder
structure. It is also private. Directory creation uses restrictive POSIX permissions;
on Windows, protection follows the parent directory's existing ACL. No authentication
credential store or note body is opened by this helper. Existing output directories
are refused. There is no apply operation, live service call or repository upload.

Fingerprints use canonical JSON encoding of the parsed inputs. They are not raw
file hashes, signatures or approvals. Re-read and compare authoritative sources
before a future migration; a refreshed collector produces another observation.

## Classification and authentication boundaries

Only searchable actors and searchable, available, non-truncated note metadata enter
the folder counts. Actor/source mismatches, duplicate eligible paths and noncanonical
KB paths fail. Excluded entries are counted; their paths and contents are not copied
into folder rules. Each rule applies to direct notes of exactly one actor/folder,
with `approved: false`, `recursive: false` and no guessed project assignment.

Confidential review hints explicitly use the organization's existing `category-3`;
unknown, mixed, imported, private and project folders remain unresolved. Folder
names are hints for human review, never classification evidence. No body, content
hash, reviewer signature or future/new note approval is supplied. Use the existing
reviewed-knowledge workflow after actual content review.

The matrix shows current category eligibility, including role/actor exceptions.
Registered Telegram or PhantomChat metadata is not proof of a verified sender,
allowlist acceptance or an installed trusted handoff. Email alone does not qualify.
An unbound ordinary human receives no counterpart authority. Existing live links
are not promoted by this draft. Native channel integration, issuer routing, source
propagation and live reader compatibility remain separate prerequisites.

See [source-binding readiness](AU_SOURCE_BINDING_READINESS.md),
[the collaborative plan](COLLABORATIVE_VIEWER_PLAN.md) and
[reviewed knowledge integration](REVIEWED_KNOWLEDGE_VIEW.md).

## Selected installation observation

On 2026-10-17 a detached run against the already selected AU source produced three
requested counterpart proposals and one independent absolute-owner declaration.
The source preservation check removed only the intended draft fields and recovered
the original document exactly. Existing role and actor exceptions were retained.

The current input contains **234 eligible notes in 61 exact folders**, with **19
excluded entries**. This differs from the earlier 62-folder count because that
inventory included excluded notes. The 61 draft rules contain 19 category-1 hints,
24 category-3 hints and 18 unresolved boundaries. **None is approved.** The
finance counterpart remains email-only and channel-ineligible. Private identities,
source documents and review artifacts are intentionally absent from this repository.

This result completes draft preparation only. It does not establish live
authentication, approved knowledge classifications, native assistant connectivity
or readiness for scoped activation.

## Source declaration review follow-up

A fresh read-only check on 2026-10-17 found the live selected source unchanged from
the detached proposal's parsed-input fingerprint. Its raw-file fingerprint also
matched the selected local source copy. The source still contains no counterpart
bindings or viewer policy; the proposal has not been applied.

The private review verified that removing only the three proposed counterpart
fields, restoring the existing category-zero owner field and removing the new
viewer policy recovers the original document exactly. The proposed document
passed the existing source validator, YAML serialization round trip and human
directory construction. Existing role categories, exceptions, channel identities
and all unrelated fields were preserved. These checks establish source-shape
compatibility, not installed channel or assistant behavior.

The private review receipt records the exact source/proposal fingerprints,
counterpart changes, independent owner and proposed organization-only scopes.
It remains outside the repository with the other private setup artifacts.
No project grants or human action grants are proposed. The email-only counterpart
remains channel-ineligible; no identity is invented to complete that binding.

Content review remains a separate decision: 53 eligible notes have category-1
hints, 111 have category-3 hints and 70 remain unresolved. These correspond to
19, 24 and 18 exact folders respectively. All 234 notes remain unapproved; metadata
and folder names are not evidence that their bodies satisfy a category. None of
these hints should become a grant as a side effect of accepting source declarations.

Validation: `python -m unittest discover -s phantomview -p 'test_setup*.py' -q`
passed 16 tests. The private source checks above were performed separately without
reading note bodies or changing the live organization. Any source write still
requires a fresh expected-source check, a protected recoverable backup, a minimal
reviewed diff and verification before downstream publication. Do not activate the
identified reader or assistant merely because declaration validation succeeds.

# Optional private role note publication

Status: local operator library, tested with synthetic inputs and temporary trees.
No AU activation, live notes, viewer routes, model tools or services are changed.

`briefing_publication.publish_briefings` prepares all explicit targets using the
existing role briefing adapter, then optionally writes one owned Markdown note
per persona. It defaults to preview mode and never discovers installations.

```python
from briefing_publication import publish_briefings

targets = [{"persona": "coordinator", "directory": "/private/example/personas/coordinator"}]
preview = publish_briefings(organization, targets, supplemental)
# A trusted local operator may explicitly request publication after reviewing it:
result = publish_briefings(organization, targets, supplemental, apply=True)
```

The directory and its `kb/` child must already exist. The directory name must match
the selected actor ID. One to sixteen distinct explicit actor targets are accepted;
no home-directory scan, arbitrary destination filename, target creation, ownership
change or process launch is performed. A compatible PhantomOrg dependency remains
required. This library is not exposed as an assistant capability or web endpoint.

## Owned file and content boundaries

The only destination is `kb/role-briefing-<organization-id>.md` inside each selected
persona directory. Organization and actor IDs are bounded safe components. The
renderer writes English headings and retains the source's declared values. It
shows organization/department/role, tools, reporting, separate access origins,
escalation, communication and supplemental document references.

Managed markers use the dedicated `PHANTOMVIEW:BRIEFING` namespace and bind both
organization and actor. A well-formed existing block is replaced; surrounding
UTF-8 manual content is preserved byte-for-byte. A note without managed markers
keeps all its content before an appended block. Duplicate, partial, foreign,
inline or out-of-order owned markers stop publication before any destination
change. Legacy `REG:` blocks are not adopted or rewritten implicitly. The existing
AU role note and custom projector are untouched; migration needs a separate preview.
Source values are escaped so they cannot forge managed blocks in the rendered note.

There are no generation timestamps. Identical sources and annotations produce no
write, lock or temporary file and preserve the note's modification time and identity.
All targets are prepared before the apply phase, so known invalid actors, sources,
paths or markers do not cause earlier target writes.

## Local write boundary and failure handling

Use existing protected operator-controlled directories and invoke apply as the
intended note owner, normally the persona's runtime account. POSIX existing notes
must be owned by the invoking user. New/replaced files use private temporary-file
permissions (0600 on POSIX); Windows relies on the selected directory's OS ACL.
No chown or broad permission changes are attempted.

Paths reject symlinks and Windows reparse points. Existing notes must be bounded
regular single-link UTF-8 files. Apply uses exclusive cooperative lock files,
private same-directory staging, flush/fsync, source-note drift checks and atomic
`os.replace` for each destination. Locks owned by another invocation are retained
and cause refusal; there is no automatic stale-lock override.

This is not an atomic transaction across several files and not isolation from a
hostile writer who can rename paths despite the directory protection assumption.
An observed concurrent edit is refused. An I/O failure can occur after an earlier
target was replaced. `PublicationError.completed` reports exactly those completed
actor IDs, allowing an operator to inspect state and retry deliberately. Automatic
rollback does not overwrite possible human edits. Cleanup failures also report
completed IDs; inspect any remaining owned staging/lock files before retrying.

## Authority and pending integration

Writing a persona KB briefing is a local maintenance action, not a human ACL grant.
It does not authenticate a counterpart, assign category zero, change tools or
restrict PhantomBot's native collaborative memory. The note can contain private
metadata; neither a preview nor a generated note is an authorized browser payload.
Preserve the existing viewer's resource filtering and publication requirements.

Still pending: legacy-sidecar mapping, reviewed AU target/version compatibility,
an authorized viewer-record adapter, visual module integration and explicit
setup/refresh binding. No new scheduler or background agent is introduced.

## Validation

Seventeen synthetic tests cover exact manual-content retention, malformed and legacy
markers, marker escaping, default no-write preview, unchanged-file identity,
all-target preflight, a frozen batch source, target validation, busy locks, observed edits during staging,
atomic replacement failure, partial-batch reporting and symlinked files/parents.
The two symlink tests may skip where Windows lacks link-creation privilege; pinned
Linux PhantomOrg CI executes the complete publication suite. Standard viewer CI
can omit package-dependent cases when the optional dependency is absent.

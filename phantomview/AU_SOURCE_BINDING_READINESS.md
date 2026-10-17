# AU source binding readiness: read-only review

Observed on 2026-10-17 through the authorized VPS administrator browser session.
Development baseline: `55d7ac4d47325aa23cb276bafd05889c9ced28e5`.

Decision: **not ready to bind or activate the identified knowledge workspace**.
The private implementation is tested, but the live installation does not yet
provide its authoritative identity, scope and reviewed-resource inputs. No empty
or permissive synthetic human view was presented as an authorized AU preview.

## Sources and compatibility

Only the known AU organization source/published copy, custom projector, viewer
entry point/service properties and reader index/directory were inspected. No
other setup, note body, channel credential, raw human registry or conversation
history was exported. No file was written on the VPS; no projector/persona was
executed and no service, policy, permission or session issuer was changed.

| Source check | Observed result |
| --- | --- |
| Organization source and published copy | Byte-identical; unchanged during this review |
| Custom role projector | Matches the previously reviewed complete script |
| Viewer organization selection | The index configuration points to the known AU organization source |
| Viewer service | Active/running under its existing domain account |
| Installed viewer entry point | Does not import the identified-session gate |
| Scoped backend / reviewed knowledge modules | Absent from the selected live viewer directory |
| Standard PhantomOrg package | Not found by system Python; other environments were not scanned |

Consistency fingerprints for the selected source objects:

- Organization source SHA-256:
  `bba3097d4e49764f8e2eda84703733103b4e32391c6245531a863db6270263dd`.
- Installed reader entry point SHA-256:
  `5c501b508f842b05afa02242d341af9db4d5a9a32de1f2feb55eacc8b60f5d2c`.
- Custom projector fingerprint remains the one in
  [the complete projector review](AU_PROJECTION_ADAPTER_REVIEW.md).

The collector index refreshes independently. It is not a frozen approval artifact;
source/payload fingerprints must be acquired again for any reviewed publication.

## Identity and scope declarations

The source contains four humans, eight actors and eight roles. None of the human
records declares a counterpart. There is no `policies.phantomview` block and no
explicit viewer scope definitions. The category-zero owner does not match a
registered human ID. These are current observations, not inferred permissions.

The operator's three requested relationships each resolve to one existing human
and one existing actor using the supplied names. This lookup prepares a proposal;
it does not authenticate a principal, write a counterpart or infer category zero.
The committed table uses functional labels and omits live IDs/contact values.

| Requested pairing | Unambiguous source candidates | Current counterpart declaration | Declared channel metadata | Existing role base categories |
| --- | --- | --- | --- | --- |
| Executive | Yes | Absent | Telegram and email; no npub | 1, 2, 3 |
| Administration | Yes | Absent | Telegram and email; no npub | 1, 2 |
| Finance | Yes | Absent | Email only | 1, 2 |

Declared Telegram metadata is not proof that the native verified-channel handoff
has been installed or exercised. Email alone does not qualify as a verified
Telegram/PhantomChat principal. Base role categories are descriptive here; this
table does not replace the resolver, actor/role exceptions or project grants.
The independently requested absolute human owner must be recorded as the approved
stable human ID in PhantomOrg, separately from counterpart membership.

## Knowledge evidence

| Collector metadata check | Observed result |
| --- | --- |
| Selected organization actors | 8; all marked searchable |
| Indexed notes | 253 |
| Notes eligible by actor/note collector availability flags | 234 |
| Notes outside those availability flags | 19 |
| Notes marked truncated | 0 |
| Notes carrying category metadata in this index | 0 |
| Notes carrying scope metadata in this index | 0 |
| Distinct exact actor/folder groups | 62 |
| Catalog/review/approval-named entries directly in the selected reader directory | 0 |

Collector eligibility is not authorization. The index contains titles, relative
paths, IDs, timestamps, sizes and availability flags, but no category/scope fields
on the inspected note metadata. This does not establish that source Markdown lacks
classification, or that no review exists elsewhere: note bodies and other trees
were not searched. No current protected approved review is bound to this reader.
The new workspace cannot use this legacy index as an approved knowledge catalog.

The 62 exact groups are candidates for the existing bounded folder-review process,
not automatic category assignments or recursive/future-content grants. Current
counts supersede earlier inventories for this observation only. No 253-note body
review, signatures, content hashes or per-human authorization test is claimed.

## Concrete integration sequence

1. Prepare a detached declaration proposal against the current source, resolving
   the approved counterpart pairs and independent absolute owner to existing stable
   IDs. Define organization/project scopes and explicit grants in PhantomOrg;
   preserve existing role categories/exceptions and native collaborative memory.
2. Validate the proposal against AU's actual custom loader/projector and source
   propagation. Do not apply the pinned package patch to an unmatched installation
   or install a second organization engine merely to make it fit.
3. Prepare current exact-folder classification candidates. Inspect the selected
   sources and batch decisions under the existing review workflow. Unresolved,
   excluded or changed notes remain unavailable; secret handling stays explicit.
4. Bind current approved reviews and existing collector payload loaders to the
   optional reviewed workspace in a disposable preview, using the same identified
   gate. Exercise allowed/denied menus, counts, body search, detail, drift and logout
   for each eligible principal. Finance remains channel-ineligible until supported
   verified-channel identity is available.
5. Complete the native verified-channel issuance/assistant compatibility work from
   the current collaborative viewer plan. Only then stage an AU-only reversible
   activation with exact artifacts, owned files and rollback.

Steps 1-5 remain pending. This review did not convert the active viewer or authorize
content merely because a human can currently receive a legacy temporary link.

## Validation and boundaries

This increment used bounded, read-only in-memory YAML/JSON checks, selected file
fingerprints, exact reference lookups and service-state observations. The source
copies and projector fingerprints were rechecked. No new runtime tests are claimed
for this documentation-only increment. The earlier 558-test development result,
including its optional skips and targeted Windows timeout rerun, remains separate
from live readiness. See [knowledge integration](REVIEWED_KNOWLEDGE_VIEW.md) and the
[collaborative plan](COLLABORATIVE_VIEWER_PLAN.md) for the current architecture;
older isolated-executor pilot documents are historical rather than the selected
native-persona integration design.

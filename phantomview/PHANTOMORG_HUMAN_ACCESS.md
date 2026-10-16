# Private PhantomOrg human-access compatibility patch

Status: source patch and tests; not applied to the AU source or shared services.
The public fork checkout and upstream remain unchanged.

`phantomorg-human-access.patch` extends the reviewed fork baseline
`e2c9ac19f71cbf8a97c023c171a201ce5e58e877`. The accompanying manifest records
SHA-256 hashes of the original and resulting UTF-8 files with LF line endings.
Do not apply it blindly to a different release or to a production checkout.

## Supported metadata

- Optional `humans[].counterpart_persona` names an existing actor; duplicate
  assignments and duplicate human channel identities are rejected.
- Optional `policies.phantomview.project_grants` records exact actor/project
  identifiers without granting implicit project access from a category number.
- Optional `scope_definitions`, `persona_scope_grants` and `human_action_grants`
  under the same block define explicit scopes and independent modification
  capabilities. See [scope/action semantics](SCOPE_ACCESS.md). Schema, shape,
  model and reference validation are extended together. Legacy documents without
  these fields retain their prior policy mode.
- The shape validator, JSON schema, typed model and cross-reference validator
  agree on the new fields. `HUMANS.md` displays counterparts when declared; its
  old format is preserved for organizations without the new field.
- With a `policies.phantomview` block, category zero must be declared. An explicit
  owner resolves to exactly one registered human by ID/name, independently of a
  counterpart. Unknown/ambiguous/blank/null owners are refused. An absent owner
  is resolved later from the verified runtime default and its unique counterpart.
- The optional `organization.display_name` used by the private dashboard is
  preserved as a label, without changing the canonical organization ID/name.

These fields describe information policy. They do not authenticate a sender,
enable tools or create a second human login. The original persona compiler's
actor access semantics are unchanged.

## AU matrix verification

Read-only evaluation of the current AU organization, with proposed bindings
injected **in memory only**, confirms:

| Human | Counterpart | Human category zero | Registered channel | Identified access after integration |
| --- | --- | --- | --- | --- |
| Salvador | Paco | Yes, explicit owner | Telegram | Eligible |
| Brigitte | Pepa | No | Telegram | Eligible |
| Fran | Roberto | No | Email only | Not eligible |
| Beatriz | None | No | Telegram | Not eligible |

No counterpart fields, policies, allowlists or services were changed by this
preview. Fran remains a valid email-only organization member; email From is not
treated as authenticated channel identity. Brigitte's ordinary categories derive
from Pepa's role/level/exceptions. Category zero is not inherited by other humans
merely because an actor or role carries that exception.

The initial KB inspection found cached note copies without structured category
metadata; the inspected frontmatter also lacked direct access/project fields.
The later AU folder proposal and fingerprinted resource draft use the selected
current snapshot rather than treating every cached payload as active knowledge.
The inspected PhantomDocs manifest had 65 registered nodes with declared categories. Those declarations
do not automatically classify arbitrary KB copies; an authoritative mapping or
verified content association is needed before reusing their grants.
The assistant must not infer authoritative classification from a note title.
Classification import/rules, the native verified-channel handoff and resource
filtering remain activation prerequisites. Private audit activation is separate.

## Reproduce in an isolated checkout of the fork

Starting from the pinned baseline, with LF checkout line endings:

```bash
git apply --check /path/to/phantomorg-human-access.patch
git apply /path/to/phantomorg-human-access.patch
python3 -m pip install -e './phantomorg[dev]'
python3 -m pytest phantomorg/tests -q
python3 -m compileall -q phantomorg/phantomorg
```

The dedicated private CI job applies the patch to that exact **fork** revision
and runs the complete suite on Linux, plus PhantomView's cross-package test.
Before applying it, CI checks that HEAD equals the manifest's base revision and
that every original file matches its recorded SHA-256. After applying it, CI
checks every resulting file against the manifest. A mismatch stops the job.
It has read-only repository permissions and never contacts the VPS or writes to
either the public fork or upstream.

Local validation: 149 targeted PhantomOrg tests passed, with four existing
symlink tests deselected because Windows refuses symlink creation (WinError 1314).
The same four failures were reproduced on the unmodified baseline. The broad
Windows suite also assumes POSIX `HOME` behavior in deployment tests and was
stopped; it is not reported as passing. PhantomView's 99 Python tests passed,
including the real-signature and patched-PhantomOrg integration suites. Changed
Python files pass Ruff E4/E7/E9/F checks and compile successfully. The generated
patch was checked, applied to a clean scratch copy and compared with the reviewed
result files. The scope/action increment additionally passes 158 targeted
PhantomOrg tests locally with two existing symlink tests deselected on Windows.
Its complete Linux suite is checked by the dedicated private CI workflow.

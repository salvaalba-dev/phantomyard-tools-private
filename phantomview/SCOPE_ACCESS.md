# Scope and action permissions

Status: private model and tested policy primitives, not active on the live reader.
The native channel handoff and full application filtering remain prerequisites.

PhantomOrg defines which information a verified human may read through a persona.
Declared scopes also determine which view definition a future session can select.
Category grants follow the [native PhantomOrg category hierarchy](CATEGORY_ACL.md).
That inheritance never supplies an undeclared project or scope grant.
Permission to read information is separate from permission to change resources or
configure personal/shared views. Category zero confers no automatic write right.

## Private source fields

The compatibility patch adds these optional fields under `policies.phantomview`:

- `scope_definitions`: a nonempty registry of scope IDs and their kinds. Kinds are
  `organization`, `department` and `project`. A label is optional. Organization
  scopes use the canonical organization ID; department scopes reference existing
  department IDs; project scope IDs are the exact project identifiers.
- `persona_scope_grants`: exact scope IDs granted to existing personas. Ordinary
  humans inherit the scope of their explicit counterpart; a reporting relationship
  or category number does not imply a scope grant.
- `human_action_grants`: explicit human capabilities, each naming exact scopes.
  Supported capabilities are `resource.edit`, `resource.classify`,
  `view.personal.edit` and `view.shared.edit`. This metadata does not execute actions.

The last two fields require `scope_definitions`, even when their mappings are empty.
Unknown fields, capabilities, principals and scopes are rejected. Scope lists must
contain unique valid IDs. Existing `project_grants` remain necessary: when scope
mode is declared, every project grant must reference a project scope, and a persona
granted that scope must also have the exact matching project grant.

This fragment extends a complete synthetic organization with the indicated actors,
humans and categories already defined. These are private extension fields, not
claims of support in an unpatched PhantomOrg release.

```yaml
humans:
  - id: alice
    counterpart_persona: coordinator
  - id: lorraine
    counterpart_persona: project-guide
policies:
  phantomview:
    scope_definitions:
      harbor-foundation:
        kind: organization
        label: Harbor Foundation
      river-project:
        kind: project
        label: River Project
    project_grants:
      coordinator: [river-project]
      project-guide: [river-project]
    persona_scope_grants:
      coordinator: [harbor-foundation, river-project]
      project-guide: [river-project]
    human_action_grants:
      lorraine:
        view.personal.edit: [river-project]
      alice:
        view.shared.edit: [river-project]
```

Lorraine could enter the project scope through Project Guide after verified
channel identification. The personal-view grant could later authorize a supported
configuration change for Lorraine's own view; it would not authorize a shared-view
change, a resource edit or a classification change. Existing category permissions
still determine which project records Lorraine can read.

## Session and resource boundaries

With scope mode configured, `HumanDirectory.resolve` requires an explicit permitted
`scope_id`. The trusted issuance adapter binds it to the immutable recipient record
before redemption. It never becomes an authoritative browser identity field or an
extra tag in the existing signed-link protocol.

A project or department session remains inside its selected scope, including when
its human has broader privileges. An organization session can include other scopes
only when the human/persona policy permits them. Entering the organization scope
does not implicitly grant every project. A category-zero human can enter any
declared organization scope through a known persona, independently of a counterpart,
but still receives the view boundary selected for that session.

Resources in scope mode require an exact descriptor, for example:

```json
{
  "organization": "harbor-foundation",
  "category": "category-3",
  "scope": {"kind": "project", "id": "river-project"},
  "project": "river-project",
  "secret": false
}
```

The category must be permitted independently. A project resource's project ID must
match its project scope. Missing descriptors, forged kinds and unknown scope IDs
fail closed. Category zero is a human privilege, never a resource classification.
Explicit secret exclusions continue to apply.

`HumanDirectory.allows_action` validates the current recipient, session scope,
explicit action grant and permitted target scope. A personal-view change must name
the requesting human as owner. Resource edits/classification additionally require
read access to the exact current target resource. A future mutation implementation
must still validate new values, destination classification and resource revisions;
this capability check alone is not a complete transaction or approval workflow.

Scope definitions and action grants contribute to the policy/directory revisions.
Changing them invalidates prior identified recipients. `preview_human_access.py`
reports available scopes without issuing links or enabling access.

## Compatibility and activation

Existing source documents without the new fields retain their legacy policy mode.
They do not gain implicit scope or modification grants. Declaring scope mode is an
explicit migration: classification catalogs need reviewed resource scope metadata
before retrieval can succeed. Draft catalogs cannot be promoted by adding a menu.

No live YAML, allowlist, service or interface configuration is changed by this
implementation. Validate source with the coordinated PhantomOrg patch before
deployment. Keep native channel proof, queue/response authorization checks, JEV,
audit integration and server-side filtering in the activation checklist. The
organization-wide ingestion ACL requirement remains deferred under F01 in the
[execution plan](EXECUTION_PLAN.md).

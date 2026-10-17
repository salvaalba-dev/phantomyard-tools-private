"""Private, deterministic role briefing preview over authoritative PhantomOrg data.

No filesystem access, publishing, authentication, ACL grants or viewer routes.
"""
import copy
from dataclasses import asdict
import hashlib
import json
import re

MAX_INPUT_BYTES = 1048576
MAX_REFERENCES = 256
DOCUMENT_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,159}")


def _encoded(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("Briefing inputs must be bounded JSON-compatible data") from error


def _fingerprint(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _text(value, limit=160):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= limit
            and not any(ord(char) < 32 for char in value))


def _references(document, spec):
    if (not isinstance(document, dict)
            or set(document) != {"schema_version", "organization_id", "references"}
            or type(document["schema_version"]) is not int or document["schema_version"] != 1
            or document["organization_id"] != spec.organization.id
            or not isinstance(document["references"], list)
            or len(document["references"]) > MAX_REFERENCES):
        raise ValueError("Supplemental metadata must select the current organization")
    targets = {"organization": {spec.organization.id},
               "department": {row.id for row in spec.departments},
               "role": {row.id for row in spec.roles}}
    owners = {spec.organization.id} | {row.id for row in spec.humans} | {row.id for row in spec.actors}
    seen = set()
    for row in document["references"]:
        if (not isinstance(row, dict)
                or set(row) != {"document_id", "applies_to", "version", "category", "owner"}
                or not isinstance(row["document_id"], str) or not DOCUMENT_ID.fullmatch(row["document_id"])
                or not _text(row["version"]) or not isinstance(row["applies_to"], dict)
                or set(row["applies_to"]) != {"kind", "id"}):
            raise ValueError("A supplemental reference needs a stable document ID and explicit target")
        target = row["applies_to"]
        if (not isinstance(target["kind"], str) or target["kind"] not in targets
                or not isinstance(target["id"], str) or target["id"] not in targets[target["kind"]]):
            raise ValueError("Supplemental target does not exist in PhantomOrg")
        if row["category"] is not None and (
                not isinstance(row["category"], str) or row["category"] == "category-0"
                or row["category"] not in spec.policies.security_categories):
            raise ValueError("Use a declared information category; category zero is not a document category")
        if row["owner"] is not None and (not isinstance(row["owner"], str) or row["owner"] not in owners):
            raise ValueError("Supplemental owner must be an existing organization, human or actor ID")
        identity = (target["kind"], target["id"], row["document_id"])
        if identity in seen:
            raise ValueError("Duplicate supplemental reference for the same target")
        seen.add(identity)
    return sorted(document["references"], key=lambda row: (
        row["applies_to"]["kind"], row["applies_to"]["id"], row["document_id"]))


def prepare_briefing(organization, persona, supplemental=None):
    """Return an inert private preview, never an authorized viewer projection.

    Supplemental categories/owners are declarations, not verified grants or
    signatures. Native collaborative memory is neither read nor restricted here.
    """
    if not isinstance(organization, dict) or not _text(persona, 80):
        raise ValueError("An organization mapping and explicit persona ID are required")
    if len(_encoded([organization, supplemental])) > MAX_INPUT_BYTES:
        raise ValueError("Briefing inputs exceed the preview size limit")
    # Copy before validation so caller mutations cannot alter a returned preview.
    raw = copy.deepcopy(organization)
    metadata = copy.deepcopy(supplemental)
    try:
        from phantomorg.compiler.access import merge_access
        from phantomorg.spec.model import OrgSpec
        from phantomorg.spec.shape_validator import validate_shape
        from phantomorg.validator.refs import check_references
    except ImportError as error:
        raise ValueError("A compatible PhantomOrg package is required for role briefing previews") from error
    validate_shape(raw)
    spec = OrgSpec.from_dict(raw)
    if check_references(spec):
        raise ValueError("Resolve PhantomOrg reference errors before preparing a briefing")
    try:
        actor = spec.actor_by_id(persona)
    except KeyError as error:
        raise ValueError("The selected persona must exist in PhantomOrg") from error
    role = spec.role_by_id(actor.role)
    department = spec.department_by_id(role.department)
    access = merge_access(spec, role, actor)
    if metadata is None:
        metadata = {"schema_version": 1, "organization_id": spec.organization.id, "references": []}
    references = _references(metadata, spec)
    selected = [row for row in references if (
        row["applies_to"]["kind"] == "organization"
        or row["applies_to"] == {"kind": "department", "id": department.id}
        or row["applies_to"] == {"kind": "role", "id": role.id})]
    routes = [asdict(row) for row in spec.escalation_matrix]
    result = {
        "schema_version": 1, "status": "private-preview", "persona": actor.id,
        "organization": asdict(spec.organization), "department": asdict(department),
        "role": asdict(role), "actor": asdict(actor),
        "reporting": {"manager_role": role.reports_to,
                      "subordinate_roles": sorted(row.id for row in spec.subordinates_of(role.id)),
                      "counterpart_humans": sorted(row.id for row in spec.humans
                                                   if getattr(row, "counterpart_persona", None) == actor.id)},
        "access_description": asdict(access),
        "escalation": {"outgoing": [row for row in routes if row["from_"] == role.id],
                       "incoming": [row for row in routes if row["to"] == role.id],
                       "wildcard": [row for row in routes if row["from_"] == "*"]},
        "communication": asdict(spec.communication),
        "document_references": selected,
        "provenance": {"organization_revision": _fingerprint(raw),
                       "supplemental_revision": _fingerprint(metadata)},
    }
    # All access fields remain descriptions. This format has no catalog/resources
    # envelope and must not be registered as a browser response or KB writer.
    result["revision"] = _fingerprint(result)
    if len(_encoded(result)) > MAX_INPUT_BYTES:
        raise ValueError("Briefing output exceeds the preview size limit")
    return result

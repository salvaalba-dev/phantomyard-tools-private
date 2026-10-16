"""Bounded, read-only software inventory for explicitly selected setups."""
import importlib.metadata
import platform
import re
import subprocess
import sys
from pathlib import Path

ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}$")
KINDS = {"phantomyard", "service", "runtime", "library", "external", "data"}
RELATIONS = {"requires", "optional", "reads", "publishes", "runs_on", "uses"}


def plain(value, limit=2000):
    return value[:limit] if isinstance(value, str) else ""


def translated(value):
    if isinstance(value, str):
        return {"en": value, "es": value}
    return {language: plain(value.get(language)) for language in ("en", "es")} if isinstance(value, dict) else {}


def observe(probe):
    """Never run commands supplied by a manifest or inspect process arguments."""
    if not isinstance(probe, dict):
        raise ValueError("Invalid component probe")
    kind = probe.get("type", "none")
    if kind == "none":
        return "declared", "unknown", "", "Manifest declaration"
    if kind == "path":
        path = Path(probe.get("path", ""))
        if not path.is_absolute():
            raise ValueError("A path probe requires an absolute path")
        return "detected", "present" if path.exists() else "missing", "", str(path)
    if kind == "python":
        return "checked", "present", platform.python_version(), sys.executable
    if kind == "distribution":
        name = probe.get("name", "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", name):
            raise ValueError("Invalid distribution name")
        try:
            return "detected", "present", importlib.metadata.version(name), "Python distribution metadata: " + sys.executable
        except importlib.metadata.PackageNotFoundError:
            return "detected", "missing", "", "Python distribution metadata: " + sys.executable
    if kind == "systemd":
        unit = probe.get("unit", "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,150}\.(service|timer)", unit):
            raise ValueError("Invalid systemd unit name")
        try:
            command = subprocess.run(["systemctl", "show", unit, "--property=LoadState,ActiveState,SubState"],
                                     capture_output=True, text=True, timeout=4, check=False)
            values = dict(line.split("=", 1) for line in command.stdout.splitlines() if "=" in line)
            if values.get("LoadState") == "not-found":
                return "checked", "missing", "", "systemd: " + unit
            if values.get("ActiveState"):
                return "checked", values["ActiveState"], "", "systemd: " + unit + " / " + values.get("SubState", "")
        except (OSError, subprocess.TimeoutExpired):
            pass
        return "declared", "unknown", "", "systemd observation unavailable: " + unit
    raise ValueError("Unsupported probe type")


def collect(manifest, actors, organization_ids, source):
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("Unsupported installation manifest")
    components, edges = manifest.get("components", []), manifest.get("relations", [])
    if not isinstance(components, list) or len(components) > 150 or not isinstance(edges, list) or len(edges) > 1000:
        raise ValueError("Installation inventory exceeds its bounds")
    result, ids = [], set()
    for component in components:
        if not isinstance(component, dict) or not ID.fullmatch(component.get("id", "")):
            raise ValueError("Invalid component identifier")
        ident, org = component["id"], component.get("org")
        if ident.startswith(("persona:", "tool:")) or ident in ids or org not in organization_ids or component.get("kind") not in KINDS:
            raise ValueError("Duplicate component, foreign setup or invalid component kind")
        ids.add(ident)
        evidence, status, version, location = observe(component.get("probe", {}))
        result.append({"id": ident, "org": org, "name": plain(component.get("name")),
                       "kind": component["kind"], "description": translated(component.get("description")),
                       "shared": component.get("shared") is True, "owner": plain(component.get("owner")),
                       "location": location, "version": version or plain(component.get("declared_version")),
                       "version_evidence": "detected" if version else "declared" if component.get("declared_version") else "unknown",
                       "status": status, "evidence": evidence, "source": source})
    relationships = []
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("from") not in ids or edge.get("to") not in ids or edge.get("type") not in RELATIONS:
            raise ValueError("Invalid dependency reference or relation type")
        if next(c["org"] for c in result if c["id"] == edge["from"]) != next(c["org"] for c in result if c["id"] == edge["to"]):
            raise ValueError("Cross-setup dependency requires a shared component declaration inside the setup")
        relationships.append({"from": edge["from"], "to": edge["to"], "type": edge["type"], "evidence": "declared"})
    for actor in actors:
        person_id = "persona:" + actor["key"]
        result.append({"id": person_id, "org": actor["org"], "name": actor["id"], "kind": "persona",
                       "actor": actor["key"], "description": translated(actor.get("description", "")),
                       "status": "remote" if actor.get("profile_remote") else "present" if actor.get("installed") else "unknown",
                       "evidence": "declared" if actor.get("profile_remote") else "detected" if actor.get("installed") else "declared",
                       "source": actor["source"], "location": actor.get("profile_path", actor.get("profile_location", "")),
                       "version": "", "shared": False, "owner": actor["id"]})
        for tool in actor["tools"]:
            tool_id = "tool:" + actor["org"] + ":" + tool
            if tool_id not in ids:
                ids.add(tool_id)
                result.append({"id": tool_id, "org": actor["org"], "name": tool, "kind": "tool", "description": translated("Declared persona capability"),
                               "status": "unknown", "evidence": "declared", "source": actor["source"], "location": "", "version": "", "shared": False, "owner": ""})
            relationships.append({"from": person_id, "to": tool_id, "type": "uses", "evidence": "declared"})
    bindings = manifest.get("tool_bindings", [])
    persona_bindings = manifest.get("persona_bindings", [])
    if not isinstance(bindings, list) or len(bindings) > 1000 or not isinstance(persona_bindings, list) or len(persona_bindings) > 1000:
        raise ValueError("Invalid installation bindings")
    for binding in bindings:
        if not isinstance(binding, dict) or binding.get("org") not in organization_ids:
            raise ValueError("Invalid tool binding")
        tool_id = "tool:" + binding["org"] + ":" + plain(binding.get("tool"))
        target = binding.get("component")
        if tool_id not in ids or target not in ids or next(c["org"] for c in result if c["id"] == target) != binding["org"]:
            raise ValueError("Unknown or foreign tool binding")
        relationships.append({"from": tool_id, "to": target, "type": "uses", "evidence": "declared"})
    for binding in persona_bindings:
        if not isinstance(binding, dict):
            raise ValueError("Invalid persona binding")
        actor = next((a for a in actors if a["key"] == binding.get("actor")), None)
        target = next((c for c in result if c["id"] == binding.get("component")), None)
        if not actor or not target or actor["org"] != target["org"]:
            raise ValueError("Unknown or foreign persona binding")
        relationships.append({"from": "persona:" + actor["key"], "to": target["id"], "type": "uses", "evidence": "declared"})
    return {"components": result, "relations": relationships, "source": source}

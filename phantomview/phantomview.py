"""PhantomView: local, authenticated, read-only organization observatory."""
from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import webbrowser

import yaml

VERSION = "0.1.0"
HERE = Path(__file__).resolve().parent
MAX_SOURCE_BYTES = 4 * 1024 * 1024
IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")
REMOTE = "https://github.com/salvaalba-dev/phantomyard-tools-private.git"


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, data, *, private_group=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".pv-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            if private_group is not None and os.name == 'posix':
                os.fchown(f.fileno(), -1, private_group)
                os.fchmod(f.fileno(), 0o640)
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_source(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Source is a symlink or exceeds the size limit")
    text = path.read_text(encoding="utf-8-sig")
    return json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)


def text(value):
    return value[:4000] if isinstance(value, str) else ""


def search_policy(item):
    """Honor explicit search exclusions; do not infer permissions from category IDs."""
    return (item.get("searchable") is not False and item.get("confidential") is not True
            and str(item.get("visibility", item.get("classification", ""))).lower()
            not in {"private", "confidential", "restricted", "secret"})


def note_search_policy(content):
    if not content.startswith('---\n') and not content.startswith('---\r\n'):
        return True
    front = re.split(r"(?m)^---\s*$", content[:16000], maxsplit=2)
    if len(front) < 3:
        return False
    try:
        metadata = yaml.safe_load(front[1]) or {}
        return isinstance(metadata, dict) and search_policy(metadata)
    except yaml.YAMLError:
        return False


def strings(value):
    return [text(x) for x in value[:100] if isinstance(x, str)] if isinstance(value, list) else []


def rows(value):
    if not isinstance(value, list) or len(value) > 10000 or any(not isinstance(x, dict) for x in value):
        raise ValueError("Expected a list of records")
    return value


def validate_org(org):
    if not isinstance(org, dict) or not isinstance(org.get("organization"), dict):
        raise ValueError("Invalid organization")
    if org.get("version") != 1:
        raise ValueError("Unsupported organization version")
    oid = org["organization"].get("id", "")
    if not isinstance(oid, str) or not IDENTIFIER.fullmatch(oid):
        raise ValueError("Invalid organization identifier")
    for kind in ("departments", "roles", "actors"):
        items = rows(org.get(kind))
        ids = [x.get("id") for x in items]
        if any(not isinstance(x, str) or not IDENTIFIER.fullmatch(x) for x in ids):
            raise ValueError(f"Invalid identifier in {kind}")
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate identifier in {kind}")
    return org


def cycle_nodes(edges):
    active, done, cycles = set(), set(), set()
    def visit(node, stack):
        if node in active:
            cycles.update(stack[stack.index(node):])
            return
        if node in done:
            return
        active.add(node)
        for target in edges.get(node, []):
            visit(target, stack + [node])
        active.remove(node)
        done.add(node)
    # Iterative depth is bounded by the accepted spec, preventing recursion abuse.
    if len(edges) > 200:
        return {"Graph exceeds display bounds"}
    for node in edges:
        visit(node, [])
    return cycles


def default_config():
    return {"mode": "demo", "org_files": [str(HERE / "example-org.yaml")],
            "personas_dir": "", "persona_paths": {}, "remote_personas": {}, "installation_labels": {}, "docs_manifests": [str(HERE / "example-docs.yaml")],
            "procedures_file": str(HERE / "example-procedures.json"),
            "doctor_file": "", "diagnostics_file": "", "default_persona_file": "", "installation_file": "", "sync_interval": 0, "software_tag": "", "software_interval": 0}


class Observatory:
    def __init__(self, config_path, *, review_queue=None):
        if review_queue is not None:
            from projection_queue import ReviewQueue
            if not isinstance(review_queue, ReviewQueue):
                raise ValueError("A trusted operator review queue is required")
        self.review_queue = review_queue
        self.path = Path(config_path).resolve()
        self.lock = threading.RLock()
        self.config = read_source(self.path) if self.path.exists() else default_config()
        self.validate_config(self.config)
        self.snapshot = None
        self.note_payloads = {}
        self.organization_inputs = {}
        self.last_attempt = None
        self.last_error = None
        self.history = []
        self.software_status = "Manual software updates"
        self.state_path = self.path.parent / "snapshot.json"
        if self.state_path.exists():
            try:
                state = read_source(self.state_path)
                self.snapshot = state.get("snapshot")
                self.history = state.get("history", [])[-50:]
            except (ValueError, OSError):
                pass

    @staticmethod
    def validate_config(config):
        if not isinstance(config, dict) or config.get("mode") not in ("demo", "new", "existing"):
            raise ValueError("Invalid mode")
        if type(config.get("auto_procedures", True)) is not bool:
            raise ValueError("Automatic procedure discovery must be a boolean")
        if type(config.get("profile_documents", False)) is not bool:
            raise ValueError("Profile document collection must be explicitly enabled")
        if type(config.get("profile_metadata", False)) is not bool:
            raise ValueError("Profile metadata collection must be a boolean")
        from working_documents import bindings
        bindings(config.get("working_documents", []))
        for key in ("org_files", "docs_manifests"):
            if not isinstance(config.get(key, []), list) or any(not isinstance(x, str) for x in config.get(key, [])):
                raise ValueError(f"Invalid configuration: {key}")
        for key in ("personas_dir", "procedures_file", "doctor_file", "diagnostics_file", "default_persona_file", "installation_file", "software_tag"):
            if not isinstance(config.get(key, ""), str):
                raise ValueError(f"Invalid configuration: {key}")
        paths = config.get("persona_paths", {})
        if not isinstance(paths, dict) or len(paths) > 1000:
            raise ValueError("Invalid persona mapping")
        for key, value in paths.items():
            parts = key.split(":") if isinstance(key, str) else []
            if len(parts) != 2 or not all(IDENTIFIER.fullmatch(x) for x in parts):
                raise ValueError("Use organization:persona for each explicit path")
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError("Each persona requires an absolute path")
        if len({str(Path(p).resolve()) for p in paths.values()}) != len(paths):
            raise ValueError("A folder cannot be assigned to two personas or setups")
        remote = config.get("remote_personas", {})
        if not isinstance(remote, dict) or len(remote) > 1000:
            raise ValueError("Invalid remote persona mapping")
        for key, value in remote.items():
            parts = key.split(":") if isinstance(key, str) else []
            if len(parts) != 2 or not all(IDENTIFIER.fullmatch(x) for x in parts) or not isinstance(value, str) or not value.strip():
                raise ValueError("Each remote persona requires organization:persona and a declared location")
        labels = config.get("installation_labels", {})
        if not isinstance(labels, dict) or len(labels) > 1000:
            raise ValueError("Invalid installation label mapping")
        for key, value in labels.items():
            parts = key.split(":") if isinstance(key, str) else []
            if len(parts) != 2 or not all(IDENTIFIER.fullmatch(x) for x in parts) or not isinstance(value, str) or not value.strip() or len(value) > 48:
                raise ValueError("Installation labels require organization:persona and at most 48 characters")
        if set(remote) & set(paths):
            raise ValueError("A persona cannot have both a local path and a remote location")
        for key in ("sync_interval", "software_interval"):
            value = config.get(key, 0)
            if type(value) is not int or not (value == 0 or 30 <= value <= 86400):
                raise ValueError("The interval must be 0 or between 30 and 86400 seconds")
        if config.get("software_interval") and not re.fullmatch(r"v\d+\.\d+\.\d+", config.get("software_tag", "")):
            raise ValueError("Automatic updates require an explicit signed release")

    def configure(self, config):
        self.validate_config(config)
        if config["mode"] == "demo":
            interval = config.get("sync_interval", 0)
            config = default_config()
            config["sync_interval"] = interval
        # Setup owns only its own configuration and index, never persona state.
        with self.lock:
            atomic_json(self.path, config)
            self.config = config
            self.snapshot = None
            self.history = []
            self.last_error = None
            if self.state_path.exists():
                atomic_json(self.state_path, {"snapshot": None, "history": []})
        return self.refresh()

    def collect(self):
        config = self.config
        self.organization_inputs = {}
        procedure_orgs = []
        result = {"organizations": [], "departments": [], "roles": [], "actors": [],
                  "humans": [], "edges": [], "documents": [], "procedures": [], "findings": [], "sources": []}
        def finding(severity, entity, title, source):
            result["findings"].append({"severity": severity, "entity": entity, "title": title, "source": source})
        pbase = Path(config["personas_dir"]).resolve() if config.get("personas_dir") else None
        explicit_paths = config.get("persona_paths", {})
        remote_personas = config.get("remote_personas", {})
        used_paths = set()
        for filename in config.get("org_files", []):
            org = validate_org(read_source(filename))
            oid = org["organization"]["id"]
            if any(x["id"] == oid for x in result["organizations"]):
                raise ValueError("Duplicate organization across sources")
            source = str(Path(filename).resolve())
            # Private producer memory only; never part of data(), snapshot or index.
            self.organization_inputs[source] = copy.deepcopy(org)
            procedure_orgs.append((org, source))
            result["sources"].append({"kind": "org", "path": source, "checked_at": now()})
            result["organizations"].append({"id": oid, "name": text(org["organization"].get("name")) or oid,
                                            "display_name": text(org["organization"].get("display_name")),
                                            "sector": text(org["organization"].get("sector")), "source": source,
                                            "communication": {"message_types": strings(org.get("communication", {}).get("message_types")),
                                                              "max_hops": org.get("communication", {}).get("max_hops", 3)}})
            if config.get("profile_metadata", False):
                from source_adapter import profile_data
                result["organizations"][-1].update(profile_data(org["organization"], 'organizations'))
            deps = {x["id"]: x for x in org["departments"]}
            roles = {x["id"]: x for x in org["roles"]}
            policies = org.get("policies") or {}
            if not isinstance(policies, dict) or not isinstance(policies.get("access_levels", {}), dict):
                raise ValueError("Invalid policies")
            hierarchy, escalation = {}, {}
            for kind, mapping, fields in (("departments", deps, ("id", "name", "parent", "access_policy")),
                                           ("roles", roles, ("id", "name", "department", "reports_to", "reports_to_human", "description", "access_level"))):
                for item in mapping.values():
                    clean = {key: text(item.get(key)) for key in fields}
                    clean.update(org=oid, key=f"{oid}:{kind}:{item['id']}", source=source,
                                 searchable=search_policy(item))
                    if kind == "roles":
                        clean["functions"] = strings(item.get("functions"))
                        clean["security_exceptions"] = strings(item.get("security_exceptions"))
                        if item.get("department") not in deps:
                            finding("error", clean["key"], "Department does not exist", source)
                        parent = text(item.get("reports_to"))
                        hierarchy[item["id"]] = [parent] if parent else []
                        if parent:
                            if parent not in roles:
                                finding("error", clean["key"], "Supervisor does not exist", source)
                            result["edges"].append({"from": clean["key"], "to": f"{oid}:roles:{parent}", "type": "reports", "label": "Reporta a"})
                    elif item.get("parent"):
                        if item["parent"] not in deps:
                            finding("error", clean["key"], "Parent department does not exist", source)
                        result["edges"].append({"from": clean["key"], "to": f"{oid}:departments:{text(item['parent'])}", "type": "department", "label": "Pertenece a"})
                    result[kind].append(clean)
            for entry in rows(org.get("escalation_matrix", [])):
                a, b = text(entry.get("from")), text(entry.get("to"))
                if b not in roles or (a != "*" and a not in roles):
                    finding("error", oid, "Escalation role does not exist", source)
                starts = [x for x in roles if x != b] if a == "*" else [a]
                for start in starts:
                    escalation.setdefault(start, []).append(b)
                result["edges"].append({"from": f"{oid}:roles:{a}", "to": f"{oid}:roles:{b}", "type": "escalation", "label": text(entry.get("condition"))})
            for name, graph in (("hierarchy", hierarchy), ("escalation", escalation)):
                for node in cycle_nodes(graph):
                    if name == "escalation":
                        # Conditional escalations may be reciprocal and bounded by TTL;
                        # the static graph cannot prove a runtime protocol violation.
                        finding("warning", f"{oid}:roles:{node}",
                                "Possible circular escalation route: review conditions and hop limit", source)
                    else:
                        finding("error", f"{oid}:roles:{node}", f"Circular {name}", source)
            for actor in org["actors"]:
                aid = actor["id"]
                role = roles.get(actor.get("role"), {})
                key = f"{oid}:actors:{aid}"
                clean = {"id": aid, "key": key, "org": oid, "role": text(actor.get("role")),
                         "department": text(role.get("department")), "description": text(role.get("description")),
                         "searchable": search_policy(actor) and search_policy(role),
                         "tools": strings(actor.get("tools")), "excluded": strings(actor.get("tools_excluded")),
                         "exceptions": strings(actor.get("actor_exceptions")), "source": source,
                         "installed": None, "runtime": "unknown", "integrations": [], "knowledge": [],
                         "channels": {x: text(actor.get(x)) for x in ("npub", "telegram_bot", "email")},
                         "tool_accounts": {k: text(v) for k, v in actor.get("tool_accounts", {}).items() if k in strings(actor.get("tools")) and isinstance(v, str)} if isinstance(actor.get("tool_accounts"), dict) else {},
                         "access_level": text(role.get("access_level")), "functions": strings(role.get("functions"))}
                level = policies.get("access_levels", {}).get(role.get("access_level"), {})
                clean["categories"] = [x for x in level.get("categories", []) if type(x) is int] if isinstance(level, dict) else []
                if not role:
                    finding("error", key, "Role does not exist", source)
                selected_path = explicit_paths.get(f"{oid}:{aid}")
                clean["installation_label"] = text(config.get("installation_labels", {}).get(f"{oid}:{aid}"))
                remote_location = remote_personas.get(f"{oid}:{aid}")
                if remote_location:
                    clean["profile_location"] = text(remote_location)
                    clean["profile_remote"] = True
                    result["sources"].append({"kind": "Declared remote persona", "org": oid, "actor": aid,
                                               "path": text(remote_location), "checked_at": None})
                elif pbase or selected_path:
                    persona = Path(selected_path) if selected_path else pbase / aid
                    if any(p.is_symlink() for p in (persona, *persona.parents)):
                        raise ValueError("Persona path is a symlink")
                    if not selected_path and not persona.resolve().is_relative_to(pbase):
                        raise ValueError("Persona path is outside its root")
                    resolved = str(persona.resolve())
                    if resolved in used_paths:
                        raise ValueError("Persona folder is shared across selected sources")
                    used_paths.add(resolved)
                    clean["profile_path"] = resolved
                    result["sources"].append({"kind": "persona", "org": oid, "actor": aid, "path": resolved, "checked_at": now()})
                    clean["installed"] = persona.is_dir()
                    if not clean["installed"]:
                        finding("warning", key, "Declared persona is not installed", source)
                    else:
                        if config.get("profile_documents", False) and clean["searchable"]:
                            from profile_documents import collect
                            clean["profile_documents"] = collect(persona, note_search_policy)
                        for file in ("IDENTITY.md", "SOUL.md", "tools.md"):
                            if file == "tools.md" and (persona / "tools").is_dir():
                                continue
                            if not (persona / file).is_file():
                                finding("warning", key, f"Incomplete profile: missing {file}", str(persona))
                        provenance = persona / ".phantomorg.yaml"
                        if provenance.exists():
                            prov = read_source(provenance)
                            installed_role = prov.get("role_id", prov.get("role")) if isinstance(prov, dict) else None
                            if installed_role and installed_role != clean["role"]:
                                finding("warning", key, "Installed role differs from specification", str(provenance))
                        mcp = persona / "mcp.json"
                        if mcp.exists():
                            reg = read_source(mcp)
                            servers = reg.get("mcpServers", {}) if isinstance(reg, dict) else {}
                            if not isinstance(servers, dict):
                                raise ValueError("Invalid MCP registry")
                            clean["integrations"] = [{"id": text(i), "transport": text(v.get("transport")), "status": "Sin comprobar"}
                                                     for i, v in servers.items() if isinstance(v, dict)]
                        kb = persona / "kb"
                        if kb.exists() and not kb.is_symlink():
                            for note in sorted(kb.rglob("*.md"))[:500]:
                                if any(p.is_symlink() for p in (note, *note.parents)) or not note.resolve().is_relative_to(kb.resolve()):
                                    continue
                                relative = note.relative_to(persona).as_posix()
                                entry = {"title": note.stem, "path": relative}
                                if re.search(r"(?:^|[/_.-])(secrets?|credentials?|vault|identity)(?:$|[/_.-])", relative, re.I):
                                    entry["unavailable"] = "Credentials file: reading excluded"
                                else:
                                    try:
                                        with note.open("rb") as handle:
                                            raw = handle.read(2_000_001)
                                        content = raw[:2_000_000].decode("utf-8-sig", errors="replace")
                                        content = re.sub(r"nsec1[023456789acdefghjklmnpqrstuvwxyz]{58}", "[CLAVE PRIVADA OCULTA]", content)
                                        content = re.sub(r"(?im)^(\s*(?:api[_ -]?key|access[_ -]?token|bot[_ -]?token|password|secret|private[_ -]?key)\s*[:=]).*$", r"\1 [OCULTO]", content)
                                        ident = hashlib.sha256((key + relative + content).encode()).hexdigest()
                                        payload = {"id": ident, "actor": key, "title": note.stem, "path": relative,
                                                   "content": content, "truncated": len(raw) > 2_000_000,
                                                   "modified_at": datetime.fromtimestamp(note.stat().st_mtime, timezone.utc).isoformat()}
                                        self.note_payloads[ident] = payload
                                        entry.update(id=ident, bytes=note.stat().st_size, modified_at=payload["modified_at"], truncated=payload["truncated"],
                                                     searchable=clean["searchable"] and note_search_policy(content))
                                    except OSError:
                                        entry["unavailable"] = "Note temporarily unavailable"
                                clean["knowledge"].append(entry)
                elif explicit_paths:
                    finding("warning", key, "Declared persona has no selected profile path", source)
                result["actors"].append(clean)
            for human in rows(org.get("humans", [])):
                result["humans"].append({"id": text(human.get("id")), "org": oid, "name": text(human.get("name")), "role": text(human.get("role"))})
        declared_keys = {f"{a['org']}:{a['id']}" for a in result["actors"]}
        if (set(explicit_paths) | set(remote_personas) | set(config.get("installation_labels", {}))) - declared_keys:
            raise ValueError("Explicit path references a persona outside the selected organizations")
        if pbase and pbase.exists():
            declared = {a["id"] for a in result["actors"]}
            for p in pbase.iterdir():
                if p.is_dir() and not p.name.startswith(".") and p.name not in declared:
                    finding("warning", p.name, "Installed persona has no assignment in the selected sources", str(pbase))
        for filename in config.get("docs_manifests", []):
            manifest = read_source(filename)
            if not isinstance(manifest, dict) or not isinstance(manifest.get("manifest"), dict):
                raise ValueError("Invalid document manifest")
            oid = text(manifest["manifest"].get("org"))
            if oid not in {o["id"] for o in result["organizations"]}:
                raise ValueError("The manifest belongs to an unselected organization")
            heads = manifest.get("currentVersions", {})
            nodes = rows(manifest.get("nodes", []))
            parent_urns = {text(n.get("mac")): text(n.get("urn")) for n in nodes if n.get("mac")}
            from working_documents import collect as collect_working_documents
            working = collect_working_documents(manifest, filename, config.get("working_documents", []), result["actors"], search_policy)
            for node in nodes:
                if heads and node.get("urn") in heads and node.get("mac") != heads[node["urn"]]:
                    continue
                result["documents"].append({"org": oid, "kind": text(node.get("kind")), "urn": text(node.get("urn")),
                    "slug": text(node.get("slug")), "parent": text(node.get("parent")) or parent_urns.get(text(node.get("parentMac")), ""), "owners": strings(node.get("owners")),
                    "category": node.get("category") if isinstance(node.get("category"), (int, str)) else None,
                    "location": text(node.get("location")), "source": str(Path(filename).resolve()), "integrity": "Sin comprobar",
                    "searchable": search_policy(node)})
                if node.get("urn") in working:
                    document = result["documents"][-1]
                    document["working_document"] = working[node["urn"]]
                    result["edges"].append({"from": f"{oid}:actors:{working[node['urn']]['actor']}", "to": node["urn"],
                        "type": "documentation", "label": "Working document", "org": oid})
            result["sources"].append({"kind": "documents", "path": str(Path(filename).resolve()), "checked_at": now()})
        if config.get("auto_procedures", True):
            from procedures import discover
            discovered, status = discover(procedure_orgs, result["actors"], self.note_payloads, result["documents"])
            result["procedures"].extend(discovered)
            result["procedure_discovery"] = status
        if config.get("procedures_file"):
            procedures = rows(read_source(config["procedures_file"]))
            for p in procedures:
                result["procedures"].append({"id": text(p.get("id")), "title": text(p.get("title")), "description": text(p.get("description")),
                    "steps": [{k: text(step.get(k)) for k in ("actor", "action", "input", "output")} for step in rows(p.get("steps", []))]})
        if config.get("doctor_file"):
            report = read_source(config["doctor_file"])
            if not isinstance(report, dict):
                raise ValueError("Invalid doctor report")
            for actor in result["actors"]:
                checks = []
                for channel in ("telegram", "phantomchat"):
                    group = report.get(channel, {})
                    if not isinstance(group, dict):
                        continue
                    for check in group.get("personas", []):
                        if isinstance(check, dict) and check.get("persona") == actor["id"]:
                            checks.append({"channel": channel, "healthy": check.get("healthy") is True})
                actor["channel_checks"] = checks
                actor["runtime"] = "reported" if checks else "unknown"
            result["sources"].append({"kind": "doctor-export", "path": config["doctor_file"],
                                      "checked_at": now(), "modified_at": datetime.fromtimestamp(Path(config["doctor_file"]).stat().st_mtime, timezone.utc).isoformat()})
        if config.get("diagnostics_file"):
            from diagnostics import safe_rows
            diagnostic_path = config["diagnostics_file"]
            diagnostics = safe_rows(read_source(diagnostic_path))
            for actor in result["actors"]:
                # A local report cannot verify a persona on another machine.
                if not actor.get("profile_remote") and actor["org"] + ":" + actor["id"] in diagnostics:
                    actor["diagnostics"] = diagnostics[actor["org"] + ":" + actor["id"]]
                    actor["runtime"] = "observed"
            result["sources"].append({"kind": "local-diagnostics", "path": diagnostic_path,
                                      "checked_at": now(), "modified_at": datetime.fromtimestamp(Path(diagnostic_path).stat().st_mtime, timezone.utc).isoformat()})
        if config.get("default_persona_file"):
            from assistant import attach
            source = config["default_persona_file"]
            result["assistant"] = attach(read_source(source), result["actors"])
            result["sources"].append({"kind": "default-persona", "path": source, "checked_at": now()})
        installation_file = config.get("installation_file") or (str(HERE / "example-installation.json") if config["mode"] == "demo" else "")
        if installation_file:
            from installation import collect as collect_installation
            source = str(Path(installation_file).resolve())
            manifest = read_source(source)
            result["installation"] = collect_installation(manifest, result["actors"],
                {org["id"] for org in result["organizations"]}, source)
            from tool_files import collect as collect_tool_files
            tool_files = collect_tool_files(manifest, result["actors"])
            for actor in result["actors"]:
                if actor["key"] in tool_files:
                    actor["tool_files"] = tool_files[actor["key"]]
            result["sources"].append({"kind": "installation", "path": source, "checked_at": now()})
        else:
            result["installation"] = {"components": [], "relations": [], "source": ""}
        return result

    def refresh(self):
        with self.lock:
            self.last_attempt = now()
            try:
                candidate = self.collect()
                if self.review_queue is not None:
                    self.review_queue.refresh(candidate)
                # Volatile observation times do not count as organizational changes.
                def stable_actor(actor):
                    actor = dict(actor)
                    if "diagnostics" in actor:
                        diagnostic = dict(actor["diagnostics"])
                        diagnostic.pop("checked_at", None)
                        diagnostic["checks"] = [{k: v for k, v in check.items() if k != "age_minutes"} for check in diagnostic["checks"]]
                        actor["diagnostics"] = diagnostic
                    return actor
                fingerprint = {k: v for k, v in candidate.items() if k != "sources"}
                fingerprint["actors"] = [stable_actor(actor) for actor in candidate["actors"]]
                digest = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                old = self.snapshot
                if not old or old.get("digest") != digest:
                    changes = []
                    for kind in ("actors", "roles", "departments", "documents", "procedures", "components"):
                        pk = "urn" if kind == "documents" else "key" if kind in ("actors", "roles", "departments") else "id"
                        before = {str(x.get(pk)): x for x in ((old or {}).get("installation", {}).get("components", []) if kind == "components" else (old or {}).get(kind, []))}
                        after = {str(x.get(pk)): x for x in (candidate.get("installation", {}).get("components", []) if kind == "components" else candidate[kind])}
                        for key in after.keys() - before.keys():
                            changes.append({"kind": kind, "entity": key, "action": "added"})
                        for key in before.keys() - after.keys():
                            changes.append({"kind": kind, "entity": key, "action": "removed"})
                        for key in before.keys() & after.keys():
                            changed = stable_actor(before[key]) != stable_actor(after[key]) if kind == "actors" else before[key] != after[key]
                            if changed:
                                changes.append({"kind": kind, "entity": key, "action": "changed"})
                    self.history.append({"at": now(), "initial": old is None, "changes": changes[:500], "total": len(changes)})
                    self.history = self.history[-50:]
                candidate.update(digest=digest, collected_at=now(), mode=self.config["mode"])
                self.snapshot = candidate
                self.last_error = None
                atomic_json(self.state_path, {"snapshot": candidate, "history": self.history})
            except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError, RecursionError):
                if self.review_queue is not None:
                    try:
                        self.review_queue.unavailable()
                    except (OSError, ValueError):
                        pass  # Preserve the collection error; never fall back to approval.
                # Never include parser excerpts: source files may contain private material.
                self.last_error = "Source could not be read or validated. The last valid reading is preserved; check paths and format."
            return self.data()

    def data(self):
        with self.lock:
            return {"version": VERSION, "snapshot": copy.deepcopy(self.snapshot), "history": copy.deepcopy(self.history),
                    "last_attempt": self.last_attempt, "error": self.last_error, "config": copy.deepcopy(self.config),
                    "software_status": self.software_status}

    def read_note(self, ident, snapshot=None):
        if not re.fullmatch(r"[a-f0-9]{64}", ident):
            raise ValueError("Invalid note")
        with self.lock:
            if not any(n.get("id") == ident for a in (self.snapshot or {}).get("actors", []) for n in a.get("knowledge", [])):
                raise ValueError("Note is outside the selected index")
            return copy.deepcopy(self.note_payloads[ident])

    def export(self, path, state, *, authority=None):
        path = Path(path)
        private_group = None
        if authority is not None:
            from authority_publication import AuthorityPublication, private_directory
            if not isinstance(authority, AuthorityPublication):
                raise ValueError('An explicit private authority publication is required')
            if not path.is_absolute() or '..' in path.parts:
                raise ValueError('Private publication requires an explicit absolute index path')
            if authority.directory == path.parent or authority.directory.is_relative_to(path.parent / 'kb'):
                raise ValueError('Use a separate private authority directory')
            parent = private_directory(path.parent)
            target = private_directory(authority.directory)
            if os.name == 'posix' and parent.st_gid != target.st_gid:
                raise ValueError('Index and authority directories must use the same intended reader group')
            private_group = parent.st_gid
            authority.publish(self, state)
        if state["error"]:
            return
        folder = path.parent / "kb"
        folder.mkdir(parents=True, exist_ok=True)
        os.chmod(folder, 0o2750 if os.name != "nt" else 0o700)
        for actor in state["snapshot"]["actors"]:
            for note in actor.get("knowledge", []):
                if note.get("id") in self.note_payloads:
                    target = folder / (note["id"] + ".json")
                    if not target.exists():
                        atomic_json(target, self.note_payloads[note["id"]])
                        os.chmod(target, 0o640)
        if authority is None:
            atomic_json(path, state)
        else:
            atomic_json(path, state, private_group=private_group)


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd or HERE.parent, capture_output=True, text=True, timeout=120, check=True).stdout.strip()


def update_software(tag, check=False):
    """Only operator-selected, cryptographically signed release tags may activate."""
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError("Select a release such as v0.1.0")
    root = Path(git("rev-parse", "--show-toplevel")).resolve()
    if git("remote", "get-url", "origin").rstrip("/") not in (REMOTE, REMOTE[:-4], "git@github.com:salvaalba-dev/phantomyard-tools-private.git"):
        raise ValueError("The origin does not match the authorized private repository")
    if git("status", "--porcelain"):
        raise ValueError("Local changes exist; preserving the installation")
    git("fetch", "origin", f"refs/tags/{tag}:refs/tags/{tag}")
    git("verify-tag", tag)
    candidate = git("rev-parse", f"{tag}^{{commit}}")
    current = git("rev-parse", "HEAD")
    if candidate == current:
        return "This version is already installed"
    if check:
        return f"Signed release available: {tag}"
    with tempfile.TemporaryDirectory(prefix="phantomview-release-") as temp:
        # Isolated checkout; never overwrite a running installation during validation.
        git("clone", "--no-hardlinks", str(root), temp)
        git("checkout", "--detach", candidate, cwd=temp)
        subprocess.run([os.sys.executable, "-m", "unittest", "discover", "-s", "phantomview", "-p", "test_*.py"],
                       cwd=temp, check=True, timeout=120, capture_output=True)
    previous = root / ".phantomview" / "previous-release.json"
    atomic_json(previous, {"commit": current, "at": now()})
    git("checkout", "--detach", candidate)
    return f"Activated {tag}; restart PhantomView. Configuration and index are preserved."


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, code, body, content_type="application/json; charset=utf-8", cookie=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; font-src 'self'; frame-src https://chat.phantomyard.ai; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        gate = getattr(self.server, "gate", None)
        if gate:
            self.request_origin = gate.boundary(self.headers, self.server.server_port)
            return bool(self.request_origin)
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"):
            return False
        return True

    def authenticated(self):
        if getattr(self.server, "gate", None):
            return self.server.gate.session(self.headers)
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        return bool(supplied) and hmac.compare_digest(supplied.encode(), self.server.token.encode())

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {"error": "Origin not allowed"})
        if getattr(self.server, 'scoped_backend', None) is not None:
            from scoped_http import dispatch
            if dispatch(self, 'GET'):
                return
        path = urlparse(self.path).path
        if path == "/api/phantombot/status":
            return self.bot_version_request()
        if path.startswith("/api/assistant/"):
            return self.assistant_request("GET")
        if path == "/api/access-info":
            gate = getattr(self.server, "gate", None)
            info = {"delegated": bool(gate), "actor": gate.policy.get("actor", "") if gate else "",
                    "role": gate.policy.get("role", "") if gate else ""}
            # The default issuer's public business contact lets humans request a link.
            # No organization, profile, source configuration or credentials are exposed.
            if gate:
                try:
                    assistant = self.server.observatory.data().get("snapshot", {}).get("assistant", {})
                    if assistant.get("persona") == info["actor"]:
                        info["assistant"] = {key: assistant.get(key, "") for key in ("persona", "org", "npub", "checked_at")}
                except (OSError, ValueError, AttributeError):
                    pass
            return self.send(200, info)
        if path.startswith("/api/knowledge/"):
            if not self.authenticated():
                return self.send(401, {"error": "Authentication necessary"})
            try:
                return self.send(200, self.server.observatory.read_note(path.removeprefix("/api/knowledge/")))
            except (ValueError, KeyError, OSError):
                return self.send(404, {"error": "Note is unavailable in the selected index"})
        if path == "/api/state":
            if not self.authenticated():
                return self.send(401, {"error": "Authentication necessary"})
            try:
                return self.send(200, self.server.observatory.data())
            except (ValueError, OSError):
                return self.send(503, {"error": "Index temporarily unavailable"})
        static = {"/search.js": ("search.js", "text/javascript; charset=utf-8"), "/version-ui.js": ("version-ui.js", "text/javascript; charset=utf-8"), "/consultation-ui.js": ("consultation-ui.js", "text/javascript; charset=utf-8"), "/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8"), "/logo.png": ("logo.png", "image/png"), "/installation.js": ("installation.js", "text/javascript; charset=utf-8"), "/review.js": ("review.js", "text/javascript; charset=utf-8"), "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"), "/assistant.js": ("assistant.js", "text/javascript; charset=utf-8")}
        if path not in static:
            if path in {'/scoped-ui.js', '/scoped-ui.css', '/scoped-chat.js'}:
                static[path] = (path.removeprefix('/'), 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
            else:
                return self.send(404, {"error": "Not found"})
        if path == '/' and getattr(self.server, 'scoped_backend', None) is not None:
            static[path] = ('scoped-index.html', 'text/html; charset=utf-8')
        file, mime = static[path]
        return self.send(200, (HERE / file).read_bytes(), mime)

    def do_DELETE(self):
        if getattr(self.server, 'scoped_backend', None) is not None:
            from scoped_http import dispatch
            if dispatch(self, 'DELETE'):
                return
        self.send(403, {'error': 'Operation unavailable'})

    def do_POST(self):
        if getattr(self.server, 'scoped_backend', None) is not None:
            from scoped_http import dispatch
            if dispatch(self, 'POST'):
                return
        if getattr(self.server, "gate", None):
            return self.gated_post()
        if not self.allowed() or not self.authenticated():
            return self.send(403, {"error": "Access not allowed"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 64000:
                return self.send(413, {"error": "Request is too large"})
            body = json.loads(self.rfile.read(length) or b"{}")
            if urlparse(self.path).path == "/api/search":
                return self.search_request(body)
            if urlparse(self.path).path == "/api/phantombot/check" and body == {}:
                return self.bot_version_request(force=True)
            if urlparse(self.path).path == "/api/sync":
                return self.send(200, self.server.observatory.refresh())
            if urlparse(self.path).path == "/api/config":
                return self.send(200, self.server.observatory.configure(body))
            return self.send(404, {"error": "Not found"})
        except (ValueError, TypeError, OSError):
            return self.send(400, {"error": "Configuration or request is invalid"})

    def gated_post(self):
        gate = self.server.gate
        if not self.allowed():
            return self.send(403, {"error": "Origin not allowed"})
        parsed = urlparse(self.path)
        if parsed.query or parsed.fragment:
            return self.send(400, {"error": "Credentials in the URL are not accepted"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json" or not 0 < length <= 8192:
                return self.send(400, {"error": "Invalid request"})
            raw = self.rfile.read(length)
            body = json.loads(raw)
            if not isinstance(body, dict):
                return self.send(400, {"error": "Invalid request"})
            if parsed.path == "/api/access-link":
                if raw != b"{}":
                    return self.send(400, {"error": "The signed request must be empty"})
                link = gate.issue(self.headers.get("Authorization", ""), self.request_origin)
                return self.send(200, {"link": link})
            if parsed.path == "/api/redeem":
                if set(body) != {"code"}:
                    return self.send(400, {"error": "Invalid request"})
                session = gate.redeem(body["code"])
                return self.send(200, {"ok": True}, cookie=gate.cookie(session))
            if not self.authenticated():
                return self.send(401, {"error": "Request a temporary link from the responsible persona"})
            if parsed.path == "/api/search":
                return self.search_request(body)
            if parsed.path == "/api/phantombot/check" and body == {}:
                return self.bot_version_request(force=True)
            if parsed.path.startswith("/api/assistant/"):
                return self.assistant_request("POST", body)
            if parsed.path == "/api/logout":
                gate.logout(self.headers)
                return self.send(200, {"ok": True}, cookie=gate.cookie())
            if parsed.path == "/api/sync":
                return self.send(200, self.server.observatory.data())
            return self.send(403, {"error": "Read-only access; local administration"})
        except self.server.access_errors:
            return self.send(401, {"error": "Link or request is invalid, expired or already used"})
        except (OSError, TypeError):
            return self.send(503, {"error": "Service temporarily unavailable"})

    def bot_version_request(self, force=False):
        if not self.authenticated():
            return self.send(401, {"error": "Session required"})
        parsed = urlparse(self.path)
        if parsed.query or parsed.fragment:
            return self.send(400, {"error": "Unexpected version request parameters"})
        monitor = getattr(self.server, "bot_version_monitor", None)
        if not monitor:
            return self.send(200, {"status": "unknown", "error": "not-configured"})
        return self.send(200, monitor.status(force))

    def search_request(self, body):
        if not self.authenticated():
            return self.send(401, {"error": "Session required"})
        parsed = urlparse(self.path)
        if parsed.query or parsed.fragment or set(body) != {"query"}:
            return self.send(400, {"error": "Invalid search request"})
        try:
            snapshot = self.server.observatory.data()["snapshot"]
            return self.send(200, self.server.knowledge_search.search(snapshot, body["query"], self.server.observatory.read_note))
        except (ValueError, TypeError, KeyError):
            return self.send(400, {"error": "Invalid search query"})
        except OSError:
            return self.send(503, {"error": "Search index temporarily unavailable"})

    def assistant_request(self, method, body=None):
        # The existing cookie and exact-origin boundary authorize consultations.
        gate = getattr(self.server, "gate", None)
        client = getattr(self.server, "assistant_client", None)
        parsed = urlparse(self.path)
        if not gate or not self.authenticated():
            return self.send(401, {"error": "Assistant session required"})
        if parsed.query or parsed.fragment or not self.allowed():
            return self.send(403, {"error": "Assistant origin rejected"})
        if not client:
            return self.send(503, {"error": "Assistant is not configured"})
        try:
            owner, expires = gate.session_scope(self.headers)
            path = parsed.path.removeprefix("/api/assistant")
            if method == "GET" and (path == "/status" or re.fullmatch(r"/jobs/[a-f0-9-]{36}", path)):
                response = client.call("GET", path, owner)
                if path != "/status" and response[0] == 200:
                    gate.audit_event(self.headers, "assistant_response_observed",
                                     job_id=response[1]["id"], status=response[1]["status"])
                return self.send(*response)
            if method == "POST" and path == "/jobs":
                from consultation import build_context
                snapshot = self.server.observatory.data()["snapshot"]
                payload = build_context(snapshot, body, gate.policy["actor"])
                payload["expires_at"] = expires
                gate.audit_event(self.headers, "assistant_requested", request_id=payload["request_id"],
                                 mode="dashboard-analysis")
                response = client.call("POST", path, owner, payload)
                if response[0] in (200, 202):
                    gate.audit_event(self.headers, "assistant_response_observed", request_id=payload["request_id"],
                                     job_id=response[1]["id"], status=response[1]["status"])
                return self.send(*response)
            if method == "POST" and re.fullmatch(r"/jobs/[a-f0-9-]{36}/cancel", path) and body == {}:
                response = client.call("DELETE", path.removesuffix("/cancel"), owner)
                if response[0] == 200:
                    gate.audit_event(self.headers, "assistant_response_observed",
                                     job_id=response[1]["id"], status=response[1]["status"])
                return self.send(*response)
            return self.send(404, {"error": "Unknown assistant operation"})
        except (ValueError, KeyError, TypeError):
            return self.send(400, {"error": "Invalid or stale assistant context; refresh PhantomView"})
        except (OSError, TimeoutError):
            return self.send(503, {"error": "Assistant unavailable"})


def serve(obs, port, open_browser, gate=None, handoff=None, scoped_backend=None, review_service=None,
          scoped_consultations=None):
    if scoped_consultations is not None:
        from scoped_consultations import ScopedConsultations
        if not isinstance(scoped_consultations, ScopedConsultations) or scoped_consultations.backend is not scoped_backend:
            raise ValueError('Consultations require the same explicitly configured scoped backend')
    if review_service is not None:
        from authenticated_review import ReviewService
        if not isinstance(review_service, ReviewService) or review_service.backend is not scoped_backend:
            raise ValueError('Review requires the same explicitly configured scoped backend')
    if scoped_backend is not None:
        from scoped_backend import ScopedBackend
        if not isinstance(scoped_backend, ScopedBackend) or scoped_backend.gate is not gate:
            raise ValueError('Scoped HTTP projection and redemption must share the same identified gate')
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.token = os.environ.get("PHANTOMVIEW_TOKEN") or secrets.token_urlsafe(32)
    os.environ["PHANTOMVIEW_TOKEN"] = server.token
    server.restart_requested = False
    server.observatory = obs
    server.gate = gate
    server.scoped_backend = scoped_backend
    server.review_service = review_service
    server.scoped_consultations = scoped_consultations
    from global_search import KnowledgeIndex
    server.knowledge_search = KnowledgeIndex()
    server.bot_version_monitor = None
    if os.environ.get("PHANTOMVIEW_BOT_VERSION_CONFIG"):
        from bot_version import Monitor
        try:
            server.bot_version_monitor = Monitor(read_source(Path(os.environ["PHANTOMVIEW_BOT_VERSION_CONFIG"])))
        except (OSError, ValueError, KeyError, TypeError):
            print("PhantomBot version observer not configured", flush=True)
    server.assistant_client = None
    if gate and scoped_backend is None and os.environ.get("PHANTOMVIEW_ASSISTANT_CONFIG"):
        from consultation import BridgeClient
        try:
            server.assistant_client = BridgeClient(read_source(Path(os.environ["PHANTOMVIEW_ASSISTANT_CONFIG"])))
        except (OSError, ValueError, KeyError, TypeError):
            print("PhantomView assistant configuration unavailable; analysis disabled", flush=True)
    if gate:
        server.access_errors = (ValueError, gate.access.core.Invalid)
    obs.refresh()
    if handoff is not None:
        try:
            handoff.start(server)
        except BaseException:
            server.server_close()
            raise
    stop = threading.Event()
    def loop():
        last_sync, last_update = time.monotonic(), time.monotonic()
        while not stop.wait(1):
            interval = obs.config.get("sync_interval", 0)
            if interval and time.monotonic() - last_sync >= interval:
                obs.refresh()
                last_sync = time.monotonic()
            interval = obs.config.get("software_interval", 0)
            if interval and time.monotonic() - last_update >= interval:
                try:
                    obs.software_status = update_software(obs.config["software_tag"])
                    if obs.software_status.startswith("Activada"):
                        server.restart_requested = True
                        server.shutdown()
                        return
                except (ValueError, subprocess.SubprocessError, OSError):
                    obs.software_status = "Update failed; preserving the installed version"
                last_update = time.monotonic()
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"PhantomView {VERSION}: {url} (acceso autenticado)", flush=True)
    if open_browser and not gate:
        webbrowser.open(url + "#token=" + server.token)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        try:
            if handoff is not None:
                handoff.close()
        finally:
            if scoped_consultations is not None:
                scoped_consultations.close()
            server.server_close()
    if server.restart_requested:
        os.execv(os.sys.executable, [os.sys.executable, *os.sys.argv])


def main():
    parser = argparse.ArgumentParser(description="PhantomView - organization, personas and documents")
    parser.add_argument("--config", default=str(HERE.parent / ".phantomview" / "config.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("serve")
    start.add_argument("--port", type=int, default=8765)
    start.add_argument("--open", action="store_true")
    start.add_argument("--reader-index", help="Exported index; web process has no source access")
    start.add_argument("--access-policy", help="JSON containing authorized issuer public identities")
    start.add_argument("--access-module-dir", help="Path to the installed PhantomBlog package")
    start.add_argument("--public-origin", help="Exact HTTPS origin of the proxy")
    start.add_argument("--session-seconds", type=int, default=1800)
    setup = sub.add_parser("setup")
    setup.add_argument("--mode", choices=["demo", "new", "existing"], default="existing")
    setup.add_argument("--org", action="append", default=[])
    setup.add_argument("--personas", default="")
    setup.add_argument("--docs", action="append", default=[])
    setup.add_argument("--procedures", default="")
    setup.add_argument("--interval", type=int, default=0)
    setup.add_argument("--installation", default="", help="Explicit installation inventory manifest")
    sync = sub.add_parser("sync")
    sync.add_argument("--export", help="Export the read-only index without granting source access")
    sync.add_argument("--authority-dir", help="Existing producer-owned private authority directory")
    sync.add_argument("--authority-org", help="Exact organization ID for the private publication")
    for command in (setup, sync):
        command.add_argument("--review-root", help="Existing private operator directory for automatic review drafts")
        command.add_argument("--review-org", help="Trusted PhantomOrg source with explicit scopes for draft review")
    update = sub.add_parser("update")
    update.add_argument("--tag", required=True)
    update.add_argument("--check", action="store_true")
    sub.add_parser("rollback")
    args = parser.parse_args()
    if args.command == "update":
        print(update_software(args.tag, args.check))
        return
    if args.command == "rollback":
        if git("status", "--porcelain"):
            raise ValueError("Local changes exist; refusing to switch versions")
        previous = read_source(Path(git("rev-parse", "--show-toplevel")) / ".phantomview" / "previous-release.json")
        commit = previous.get("commit", "")
        if not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise ValueError("Invalid restore point")
        git("checkout", "--detach", commit)
        print("Previous version restored; restart PhantomView")
        return
    gate = None
    if args.command == "serve" and args.access_policy:
        from access_gate import Gate, SnapshotReader
        if not args.reader_index or not args.public_origin or not args.access_module_dir:
            parser.error("Delegated access requires an exported index, origin and PhantomBlog module")
        import sys
        sys.path.insert(0, str(Path(args.access_module_dir).resolve()))
        from phantomblog import access
        policy = read_source(args.access_policy)
        audit = None
        if os.environ.get("PHANTOMVIEW_AUDIT_PATH"):
            from session_audit import Ledger
            audit = Ledger(os.environ["PHANTOMVIEW_AUDIT_PATH"])
        gate = Gate(access, policy, args.public_origin, args.port, args.session_seconds, audit=audit)
        obs = SnapshotReader(args.reader_index, policy)
    else:
        if args.command == "serve" and (args.public_origin or args.reader_index):
            parser.error("A remote origin requires delegated access")
        queue = None
        if args.command in ("setup", "sync"):
            if bool(args.review_root) != bool(args.review_org):
                parser.error("Draft review requires both --review-root and --review-org")
            if args.review_root:
                from projection_queue import ReviewQueue
                review_org = Path(args.review_org).resolve()
                queue = ReviewQueue(args.review_root, lambda: read_source(review_org))
        obs = Observatory(args.config, review_queue=queue)
    if args.command == "setup":
        cfg = default_config() if args.mode == "demo" else {"mode": args.mode, "org_files": args.org,
              "personas_dir": args.personas, "docs_manifests": args.docs, "procedures_file": args.procedures,
              "doctor_file": "", "installation_file": args.installation, "sync_interval": args.interval, "software_tag": "", "software_interval": 0}
        state = obs.configure(cfg)
        print("Configuration saved" if not state["error"] else state["error"])
        if state["error"]:
            raise SystemExit(1)
    elif args.command == "sync":
        if bool(args.authority_dir) != bool(args.authority_org) or args.authority_dir and not args.export:
            parser.error('Private authority requires --export, --authority-dir and --authority-org')
        authority = None
        if args.authority_dir:
            from authority_publication import AuthorityPublication
            authority = AuthorityPublication(args.authority_dir, args.authority_org)
        state = obs.refresh()
        if args.export:
            obs.export(args.export, state, authority=authority)
        print("Information updated" if not state["error"] else state["error"])
        if state["error"]:
            raise SystemExit(1)
    else:
        serve(obs, args.port, args.open, gate)


if __name__ == "__main__":
    main()

"""Session-scoped PhantomView context and a loopback-only PhantomBridge client."""
from datetime import datetime, timezone
from http.client import HTTPConnection
import hashlib
import json
from pathlib import Path
import re
import time

VIEWS = {"overview", "departments", "personas", "tools", "documents", "procedures", "history", "installation", "sources"}


def selected_default(snapshot, issuer):
    row = snapshot.get("assistant", {})
    try:
        date = datetime.fromisoformat(row["checked_at"])
        age = (datetime.now(timezone.utc) - date).total_seconds()
    except (KeyError, TypeError, ValueError):
        raise ValueError("Default persona not verified") from None
    if not -60 <= age <= 900 or row.get("persona") != issuer:
        raise ValueError("Default persona not verified")
    if not any(a["key"] == row.get("key") and not a.get("profile_remote") for a in snapshot.get("actors", [])):
        raise ValueError("Default persona is outside the selected local setup")
    return row


def build_context(snapshot, body, issuer):
    if not isinstance(body, dict) or set(body) - {"kind", "org", "finding", "view", "question", "locale", "request_id", "turns"}:
        raise ValueError("Invalid assistant request")
    kind, locale = body.get("kind"), body.get("locale")
    if kind not in {"question", "prompt-helper"} or locale not in {"en", "es"}:
        raise ValueError("Invalid assistant request")
    default = selected_default(snapshot, issuer)
    org = body.get("org") or default["org"]
    if org != default["org"] or body.get("view", "overview") not in VIEWS:
        raise ValueError("Assistant setup is outside the authorized scope")
    organization = next(o for o in snapshot["organizations"] if o["id"] == org)
    context = {"organization": organization["name"], "snapshot_at": snapshot["collected_at"],
               "view": body.get("view", "overview"), "evidence_type": "declared structure and bounded local observations"}
    context["dashboard_semantics"] = {
        "Detected": "Installation/profile presence was observed; this does not prove operational health.",
        "Unverified operation": "No usable local service observation: remote persona, missing diagnostics or unknown service check. It does not mean the service is stopped.",
        "Alive": "A fresh local service check is OK. Message replies, effective tool permissions and document access are not tested by this flag.",
        "Check expired": "The observation exceeded its configured freshness window, normally 15 minutes.",
        "Active review": "The finding is selected and highlighted for inspection; it is not resolved by selecting it.",
        "Possible circular escalation": "A route in the declared graph, not proof of an execution loop. Conditions, response/closure semantics and actual hop-limit enforcement are separate checks.",
    }
    finding = None
    if body.get("finding"):
        ident = body["finding"]
        if not isinstance(ident, list) or len(ident) != 3 or not all(isinstance(x, str) and len(x) <= 700 for x in ident):
            raise ValueError("Invalid finding reference")
        finding = next((f for f in snapshot["findings"] if [f["entity"], f["title"], f["source"]] == ident and (f["entity"] == org or f["entity"].startswith(org + ":"))), None)
        if not finding:
            raise ValueError("Finding is no longer present; refresh the review")
        context["finding"] = {k: finding.get(k) for k in ("entity", "title", "source", "severity")}
        entity = finding["entity"]
        context["relations"] = [{k: str(e.get(k, ""))[:400] for k in ("from", "to", "type", "label")}
                                for e in snapshot.get("edges", []) if e.get("from") == entity or e.get("to") == entity
                                or e.get("from") == org + ":roles:*"][:12]
        role = next((r for r in snapshot.get("roles", []) if r["key"] == entity), None)
        actor = next((a for a in snapshot.get("actors", []) if a["key"] == entity or role and a["org"] == org and a["role"] == role["id"]), None)
        if role:
            context["role"] = {k: role.get(k) for k in ("id", "name", "reports_to")}
        if actor:
            context["persona"] = {k: actor.get(k) for k in ("id", "role", "installed", "profile_remote", "runtime")}
            context["persona"]["diagnostics"] = actor.get("diagnostics", {})
        context["communication"] = {k: organization.get("communication", {}).get(k) for k in ("max_hops", "ttl_hours")}
        context["review_criteria"] = (["Differentiate a new escalation from an answer", "Check decision/closure semantics", "Check actual hop-limit enforcement; a graph cycle is not proof of a runtime loop"]
                                      if re.search(r"circular|cycle|ciclo", finding["title"], re.I)
                                      else ["Compare the declared profile and role with the source", "Distinguish installation presence from operational health", "Identify missing checks before proposing a correction"])
    else:
        if kind == "prompt-helper":
            raise ValueError("Select a finding before generating a prompt")
        context["counts"] = {k: sum(r.get("org") == org for r in snapshot.get(k, [])) for k in ("actors", "departments", "documents")}
        context["findings"] = [{k: f.get(k) for k in ("entity", "title", "severity")} for f in snapshot.get("findings", []) if f.get("entity", "").startswith(org + ":")][:5]
    question = body.get("question", "").strip() if isinstance(body.get("question", ""), str) else ""
    if len(question) > 1800 or kind == "question" and not question:
        raise ValueError("Write a question of at most 1800 characters")
    turns = body.get("turns", [])
    if not isinstance(turns, list) or len(turns) > 4 or any(not isinstance(t, dict) or set(t) != {"role", "text"} or t["role"] not in {"human", "assistant"} or not isinstance(t["text"], str) or len(t["text"]) > 800 for t in turns):
        raise ValueError("Invalid bounded conversation context")
    if turns:
        context["previous_turns_untrusted"] = turns
    request_id = body.get("request_id", "")
    if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9-]{36}", request_id):
        raise ValueError("Invalid assistant request identifier")
    # Application behavior belongs in the fixed system suffix, not in user text.
    # All question/evidence/follow-up strings still pass through the real screen.
    prompt = json.dumps({"application": "PhantomView", "kind": kind, "language": locale,
                         "trust": "untrusted", "question": question, "evidence": context}, ensure_ascii=False)
    if len(prompt.encode()) > 12000:
        raise ValueError("Finding context exceeds the consultation limit")
    basis = {"entity": finding["entity"] if finding else org, "snapshot_at": snapshot["collected_at"], "kind": kind}
    return {"org": org, "persona": default["persona"], "prompt": prompt, "request_id": request_id, "basis": basis}


class BridgeClient:
    def __init__(self, config):
        self.port = config["bridge_port"]
        if type(self.port) is not int or not 1024 <= self.port <= 65535:
            raise ValueError("Invalid local bridge port")
        path = Path(config["token_file"])
        if path.is_symlink():
            raise ValueError("Invalid assistant token file")
        self.token = path.read_text(encoding="utf8").strip()
        if not re.fullmatch(r"[a-f0-9]{64}", self.token):
            raise ValueError("Invalid assistant token")

    def call(self, method, path, owner="", payload=None):
        if not re.fullmatch(r"/(status|jobs(?:/[a-f0-9-]{36})?)", path):
            raise ValueError("Invalid assistant operation")
        raw = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, "/phantomview-assistant" + path, body=raw,
                               headers={"Authorization": "Bearer " + self.token, "X-PhantomView-Session": owner, "Content-Type": "application/json"})
            response = connection.getresponse()
            value = response.read(65537)
            if len(value) > 65536:
                raise ValueError("Assistant response exceeds bounds")
            data = json.loads(value)
            if not isinstance(data, dict):
                raise ValueError("Invalid assistant response")
            return response.status, data
        finally:
            connection.close()

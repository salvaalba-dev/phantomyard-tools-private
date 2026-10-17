"""Explicit local publication of private role briefings; dry-run by default.

Trusted operator invocation only. No route, model tool, discovery or scheduler.
"""
import copy
import html
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from role_briefing import MAX_INPUT_BYTES, prepare_briefing

MARKER = "<!-- PHANTOMVIEW:BRIEFING"
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}")
MAX_TARGETS = 16


class PublicationError(RuntimeError):
    """A batch stopped; completed persona IDs identify already published notes."""
    def __init__(self, completed):
        super().__init__("Briefing publication stopped; inspect completed targets before retrying")
        self.completed = tuple(completed)


def _display(value):
    if value is None or value == [] or value == {} or value == "":
        return "Not declared"
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False)
    text = html.escape(text, quote=False).replace("\r", " ").replace("\n", " ")
    return re.sub(r"([\\`*_{}\[\]#!|])", r"\\\1", text)


def _markers(org, persona):
    return (f"{MARKER} BEGIN org={org} persona={persona} -->",
            f"{MARKER} END org={org} persona={persona} -->")


def render_briefing(briefing):
    """Render a private prepared object; the public entry prepares it internally."""
    org, persona = briefing["organization"]["id"], briefing["persona"]
    if not ID.fullmatch(org) or not ID.fullmatch(persona):
        raise ValueError("Publication requires bounded organization and persona IDs")
    begin, end = _markers(org, persona)
    lines = [begin, "# Role briefing", "", "Generated from PhantomOrg; edit annotations outside this block.",
             "Access labels below describe policy; they do not grant access.", "",
             f"Source revision: {briefing['revision']}", ""]
    for title, field in (("Organization", "organization"), ("Department", "department"),
                         ("Role", "role"), ("Persona and tools", "actor"),
                         ("Reporting", "reporting"), ("Declared access", "access_description"),
                         ("Escalation", "escalation"), ("Communication", "communication")):
        lines += [f"## {title}"]
        lines += [f"- {key.replace('_', ' ').capitalize()}: {_display(value)}"
                  for key, value in briefing[field].items()]
        lines += [""]
    lines += ["## Supplemental document references"]
    lines += [f"- {_display(row)}" for row in briefing["document_references"]] or ["- Not declared"]
    lines += ["", end, ""]
    return "\n".join(lines).encode("utf-8")


def _merge(existing, block, org, persona):
    begin, end = (value.encode() for value in _markers(org, persona))
    if b"<!-- REG:" in existing:
        raise ValueError("Legacy role markers need an explicit migration; no implicit adoption")
    if MARKER.encode() not in existing:
        separator = b"" if not existing or existing.endswith(b"\n\n") else (b"\n" if existing.endswith(b"\n") else b"\n\n")
        return existing + separator + block
    if existing.count(MARKER.encode()) != 2 or existing.count(begin) != 1 or existing.count(end) != 1:
        raise ValueError("Ambiguous or foreign briefing markers; preserve and review the note")
    start, finish = existing.find(begin), existing.find(end)
    if (finish <= start or (start and existing[start - 1:start] != b"\n")
            or (finish and existing[finish - 1:finish] != b"\n")):
        raise ValueError("Briefing markers must be ordered standalone lines")
    if not existing[start + len(begin):].startswith((b"\n", b"\r\n")):
        raise ValueError("Briefing begin marker must occupy its own line")
    finish += len(end)
    if existing[finish:finish + 2] == b"\r\n":
        finish += 2
    elif existing[finish:finish + 1] == b"\n":
        finish += 1
    elif finish != len(existing):
        raise ValueError("Briefing end marker must occupy its own line")
    return existing[:start] + block + existing[finish:]


def _paths(path):
    for item in (path, *path.parents):
        if not item.exists() and not item.is_symlink():
            continue
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise ValueError("Publication paths must not contain links or reparse points")


def _read(path):
    _paths(path)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return None, None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Publication notes must be regular single-link files")
        if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise ValueError("Run publication as the owner of the selected note")
        content = stream.read(MAX_INPUT_BYTES + 1)
    if len(content) > MAX_INPUT_BYTES:
        raise ValueError("Publication note exceeds size limit")
    content.decode("utf-8")
    return content, (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size, info.st_mode)


def publish_briefings(organization, targets, supplemental=None, *, apply=False):
    """Prepare every explicit target first; optionally replace each note atomically.

    Parent directories must be existing, operator-controlled persona/KB trees.
    Cooperative locks and drift checks do not provide hostile-writer isolation or
    a cross-file transaction. An apply failure reports completed persona IDs.
    """
    if type(apply) is not bool or not isinstance(targets, list) or not 1 <= len(targets) <= MAX_TARGETS:
        raise ValueError("Provide one to sixteen explicit publication targets")
    # One frozen source/target snapshot for the complete selected batch.
    organization = copy.deepcopy(organization)
    supplemental = copy.deepcopy(supplemental)
    targets = copy.deepcopy(targets)
    plans, seen_personas, seen_paths = [], set(), set()
    for row in targets:
        if (not isinstance(row, dict) or set(row) != {"persona", "directory"}
                or not isinstance(row["persona"], str) or not ID.fullmatch(row["persona"])
                or not isinstance(row["directory"], str)):
            raise ValueError("Each target needs an explicit persona and absolute directory")
        root = Path(row["directory"])
        if not root.is_absolute() or not root.is_dir() or not (root / "kb").is_dir():
            raise ValueError("Target persona and KB directories must already exist")
        _paths(root / "kb")
        if root.name != row["persona"]:
            raise ValueError("Target directory must name the selected persona")
        briefing = prepare_briefing(organization, row["persona"], supplemental)
        org = briefing["organization"]["id"]
        block = render_briefing(briefing)
        path = root / "kb" / f"role-briefing-{org}.md"
        normalized = os.path.normcase(str(path.resolve()))
        if row["persona"] in seen_personas or normalized in seen_paths:
            raise ValueError("Duplicate publication target")
        seen_personas.add(row["persona"])
        seen_paths.add(normalized)
        old, identity = _read(path)
        new = _merge(old or b"", block, org, row["persona"])
        if len(new) > MAX_INPUT_BYTES:
            raise ValueError("Merged briefing note exceeds size limit")
        plans.append({"persona": row["persona"], "path": path, "old": old,
                      "identity": identity, "new": new, "revision": briefing["revision"]})
    changed = [row for row in plans if row["old"] != row["new"]]
    if not apply:
        return [{"persona": row["persona"], "path": str(row["path"]), "revision": row["revision"],
                 "action": "unchanged" if row["old"] == row["new"] else "would-write",
                 "content": row["new"].decode("utf-8")} for row in plans]
    locks, staged, completed = [], [], []
    try:
        for row in sorted(changed, key=lambda row: str(row["path"])):
            lock = row["path"].with_name("." + row["path"].name + ".lock")
            _paths(lock)
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.close(fd)
            locks.append(lock)
        for row in changed:
            _paths(row["path"])
            if _read(row["path"]) != (row["old"], row["identity"]):
                raise ValueError("Note changed after preview preparation")
            fd, filename = tempfile.mkstemp(prefix=".briefing-", dir=row["path"].parent)
            staged.append((row, Path(filename)))
            with os.fdopen(fd, "wb") as stream:
                stream.write(row["new"])
                stream.flush()
                os.fsync(stream.fileno())
        # No destination is changed until all targets have passed preparation.
        for row, _ in staged:
            if _read(row["path"]) != (row["old"], row["identity"]):
                raise ValueError("Note changed during publication preparation")
        for row, temporary in staged:
            _paths(row["path"])
            if _read(row["path"]) != (row["old"], row["identity"]):
                raise ValueError("Note changed before replacement")
            os.replace(temporary, row["path"])
            completed.append(row["persona"])
    except (OSError, ValueError) as error:
        raise PublicationError(completed) from error
    finally:
        cleanup_errors = []
        for item in [temporary for _, temporary in staged] + list(reversed(locks)):
            try:
                item.unlink(missing_ok=True)
            except OSError as error:
                cleanup_errors.append(error)
        if cleanup_errors:
            raise PublicationError(completed) from cleanup_errors[0]
    return [{"persona": row["persona"], "path": str(row["path"]), "revision": row["revision"],
             "action": "written" if row["persona"] in completed else "unchanged"} for row in plans]

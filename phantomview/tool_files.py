"""Explicit capability-to-file references; never read or execute tool contents."""
from pathlib import Path, PurePosixPath
import re
import stat

STATES = {'file', 'symlink', 'missing', 'unavailable'}
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z')
FILE = re.compile(r'tools/(?:[A-Za-z0-9_][A-Za-z0-9_.-]*/)*[A-Za-z0-9_][A-Za-z0-9_.-]*\.(?:py|sh|js|mjs|ts|md)\Z')


def valid_file(value):
    return (isinstance(value, str) and len(value) <= 240 and FILE.fullmatch(value)
            and all(part not in {'.', '..'} for part in PurePosixPath(value).parts))


def validated(rows, tools):
    """Copy only bounded references belonging to declared capabilities."""
    if not isinstance(rows, list) or len(rows) > 128:
        raise ValueError('Invalid tool file references')
    result, seen = [], set()
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'tool', 'file', 'state'}
                or not isinstance(row['tool'], str) or row['tool'] not in tools or not valid_file(row['file'])
                or not isinstance(row['state'], str) or row['state'] not in STATES):
            raise ValueError('Invalid tool file reference')
        key = (row['tool'], row['file'])
        if key in seen:
            raise ValueError('Duplicate tool file reference')
        seen.add(key)
        result.append(dict(row))
    return result


def collect(manifest, actors):
    """Observe explicit persona-local filenames without following symbolic links."""
    bindings = manifest.get('persona_tool_files', [])
    if not isinstance(bindings, list) or len(bindings) > 1000:
        raise ValueError('Invalid persona tool file bindings')
    selected = {actor['key']: actor for actor in actors}
    result = {}
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != {'actor', 'tool', 'files'}:
            raise ValueError('Invalid persona tool file binding')
        actor = selected.get(binding['actor']) if isinstance(binding['actor'], str) else None
        tool, files = binding['tool'], binding['files']
        if (actor is None or not isinstance(tool, str) or not NAME.fullmatch(tool)
                or tool not in actor['tools'] or tool in actor.get('excluded', [])
                or not isinstance(files, list) or not 1 <= len(files) <= 16):
            raise ValueError('Tool binding must belong to a declared selected persona capability')
        root = Path(actor['profile_path']) if actor.get('profile_path') else None
        for filename in files:
            if not valid_file(filename):
                raise ValueError('A bounded relative tool filename is required')
            state = 'unavailable'
            if root is not None:
                candidate = root / filename
                try:
                    if any(parent.is_symlink() for parent in (candidate.parent, *candidate.parent.parents)):
                        state = 'unavailable'
                    else:
                        info = candidate.lstat()
                        state = 'symlink' if stat.S_ISLNK(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'unavailable'
                except FileNotFoundError:
                    state = 'missing'
                except OSError:
                    state = 'unavailable'
            result.setdefault(actor['key'], []).append({'tool': tool, 'file': filename, 'state': state})
    return {key: validated(rows, selected[key]['tools']) for key, rows in result.items()}

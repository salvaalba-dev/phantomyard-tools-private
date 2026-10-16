"""Read-only access-matrix preview; never edits PhantomOrg or issues links."""
import argparse
import copy
import json
from pathlib import Path

from channel_identity import HumanDirectory


def preview(org, counterparts=(), default_persona=None):
    proposed = copy.deepcopy(org)
    humans = {h["id"]: h for h in proposed.get("humans", [])}
    if len(humans) != len(proposed.get("humans", [])):
        raise ValueError("Duplicate human identifiers")
    assignments = {}
    for assignment in counterparts:
        human, separator, persona = assignment.partition("=")
        if not separator or not persona or human not in humans or human in assignments:
            raise ValueError("Expected unique HUMAN=PERSONA preview assignments")
        assignments[human] = persona
        humans[human]["counterpart_persona"] = persona
    directory = HumanDirectory(proposed, default_persona)
    rows = []
    for human, row in directory.scope.policy["humans"].items():
        channels = [channel for channel, senders in directory.senders.items() if human in senders.values()]
        grants = directory.scope.human_grants(human)
        view = directory.scope.policy.get('view_access')
        scopes = ([scope_id for scope_id in sorted(view['scope_definitions'])
                   if any(directory.scope.can_enter(human, persona, scope_id)
                          for persona in directory.scope.policy['personas'])] if view is not None else None)
        rows.append({"human": human, "counterpart": row.get("counterpart_persona"),
                     "category_zero": directory.scope.is_absolute(human),
                     "registered_channels": channels,
                     "categories": grants["categories"] if grants else [],
                     "projects": grants["projects"] if grants else [],
                     "all_projects": bool(grants and grants.get("all_projects")),
                     "available_scopes": scopes,
                     "eligible_after_trusted_channel_integration": bool(grants and channels and (scopes is None or scopes))})
    return {"organization": directory.scope.policy["organization"], "preview_only": True,
            "proposed_bindings": bool(assignments), "live_access_changed": False,
            "humans": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, type=Path)
    parser.add_argument("--counterpart", action="append", default=[], metavar="HUMAN=PERSONA",
                        help="Propose a binding in memory for this preview only")
    parser.add_argument("--default-persona")
    args = parser.parse_args()
    import yaml
    result = preview(yaml.safe_load(args.org.read_text(encoding="utf-8")), args.counterpart, args.default_persona)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

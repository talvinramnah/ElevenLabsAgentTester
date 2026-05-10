"""Apply the OSCE patient evaluation rubric to a target agent.

Usage:
    python apply_criteria.py <agent_id>            # apply rubric (replaces all existing criteria)
    python apply_criteria.py <agent_id> --dry-run  # show diff without writing

The rubric is defined in criteria.py and is the source of truth.
"""

from __future__ import annotations

import argparse
import json
import sys

from criteria import CRITERIA, all_criteria_payload
from elevenlabs_client import get_agent, update_agent_criteria


def _summarise_existing(agent: dict) -> list[str]:
    ps = agent.get("platform_settings") or {}
    ev = ps.get("evaluation") or {}
    return [c.get("id", "?") for c in (ev.get("criteria") or [])]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent_id")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent without making the PATCH call.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt when overwriting existing criteria.",
    )
    args = parser.parse_args(argv)

    print(f"Fetching agent {args.agent_id}...")
    current = get_agent(args.agent_id)
    name = current.get("name", "(unnamed)")
    existing_ids = _summarise_existing(current)
    print(f"  name: {name}")
    print(f"  existing criteria: {len(existing_ids)}")
    for cid in existing_ids:
        print(f"    - {cid}")

    new_payload = all_criteria_payload()
    new_ids = [c["id"] for c in new_payload]
    print(f"\nNew rubric: {len(new_payload)} criteria")
    for c in CRITERIA:
        print(f"    - [{c.category}] {c.id}")

    overlap = set(existing_ids) & set(new_ids)
    only_existing = set(existing_ids) - set(new_ids)
    only_new = set(new_ids) - set(existing_ids)
    print("\nDiff:")
    print(f"  to add:    {len(only_new)}")
    print(f"  to keep:   {len(overlap)}")
    print(f"  to remove: {len(only_existing)}")
    if only_existing:
        print("  WARNING: the following existing criteria are NOT in the new rubric and will be removed:")
        for cid in sorted(only_existing):
            print(f"    - {cid}")

    if args.dry_run:
        print("\n--dry-run: not writing. Body that would be sent to PATCH:")
        print(json.dumps({"platform_settings": {"evaluation": {"criteria": new_payload}}}, indent=2)[:2000])
        return 0

    if existing_ids and not args.yes:
        ans = input(
            f"\nAgent has {len(existing_ids)} existing criteria. Replace with the new "
            f"{len(new_payload)} criteria? [y/N] "
        ).strip().lower()
        if ans != "y":
            print("Aborted.")
            return 1

    print("\nPATCHing agent with new criteria...")
    updated = update_agent_criteria(args.agent_id, new_payload)
    after_ids = _summarise_existing(updated)
    print(f"Done. Agent now has {len(after_ids)} criteria.")
    if set(after_ids) != set(new_ids):
        print("WARNING: post-PATCH criteria do not match what we sent.")
        print(f"  sent:  {sorted(new_ids)}")
        print(f"  found: {sorted(after_ids)}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

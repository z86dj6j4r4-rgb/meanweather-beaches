#!/usr/bin/env python3
"""merge_beaches.py — safely append new beaches to beaches.json

Usage:
    python3 scripts/merge_beaches.py new_beaches.json               # dry-run
    python3 scripts/merge_beaches.py new_beaches.json --apply        # write
    python3 scripts/merge_beaches.py new_beaches.json --target FILE  # test against a copy

Input is a plain JSON array of beach objects (not a {meta, beaches} wrapper).

Behaviour:
  - Every new entry is validated against the same schema as validate_beaches.py.
    Unlike that script, an entry with an unrecognized key is a HARD failure here
    (not a warning) — a key outside the known schema means the entry was written
    against the wrong convention and needs re-authoring, not silent acceptance.
  - An id colliding with an existing entry, or with another entry in the new
    file, is rejected.
  - An entry within 300m of any existing beach is rejected (same beach, entered
    under a different name, is a known failure mode in this file).
  - Surviving entries are appended to the target file's `beaches` array. The
    `meta` block is never touched — update_beaches.py owns it.
  - Dry-run by default; nothing is written without --apply.
  - Running with an empty input array must leave the target file byte-identical
    (see scripts/test_merge_roundtrip.py or the manual check in the handover plan).
"""

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_beaches import check_entry  # noqa: E402

PROXIMITY_REJECT_METERS = 300
EARTH_RADIUS_METERS = 6_371_000


def haversine_meters(lat1, lng1, lat2, lng2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a))


def nearest_existing(entry, existing_beaches):
    """Return (nearest_beach, distance_m) or (None, None) if existing_beaches is empty."""
    best = None
    best_dist = None
    lat, lng = entry.get("lat"), entry.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return None, None
    for b in existing_beaches:
        blat, blng = b.get("lat"), b.get("lng")
        if not isinstance(blat, (int, float)) or not isinstance(blng, (int, float)):
            continue
        dist = haversine_meters(lat, lng, blat, blng)
        if best_dist is None or dist < best_dist:
            best, best_dist = b, dist
    return best, best_dist


def evaluate(new_beaches, existing_beaches):
    """Return a list of verdict dicts, one per new entry, in input order.

    Each verdict: {"entry": ..., "status": "add"|"reject", "reasons": [...]}
    """
    seen_ids = {b["id"]: "existing beaches.json" for b in existing_beaches if isinstance(b.get("id"), str)}
    verdicts = []

    for i, entry in enumerate(new_beaches):
        reasons = []

        if not isinstance(entry, dict):
            verdicts.append({"entry": entry, "status": "reject", "reasons": ["entry is not an object"]})
            continue

        entry_id = entry.get("id", f"<no id, index {i}>")

        # Structural validation — reuse validate_beaches.py's checks. Any
        # "warning" there (unrecognized keys) is a hard failure here.
        errors, warnings = check_entry(entry, i, seen_ids)
        reasons.extend(errors)
        reasons.extend(w.replace("unrecognized key(s)", "unrecognized key(s) — reject, wrong schema") for w in warnings)

        # Proximity check only makes sense once lat/lng are confirmed numeric,
        # which check_entry has already validated above.
        nearest, dist = nearest_existing(entry, existing_beaches)
        if nearest is not None and dist < PROXIMITY_REJECT_METERS:
            reasons.append(
                f"within {dist:.0f}m of existing beach '{nearest.get('id')}' "
                f"({nearest.get('name')}) — possible duplicate under a different name"
            )

        status = "reject" if reasons else "add"
        verdicts.append({"entry": entry, "id": entry_id, "status": status, "reasons": reasons})

    return verdicts


def print_report(verdicts):
    added = [v for v in verdicts if v["status"] == "add"]
    rejected = [v for v in verdicts if v["status"] == "reject"]

    print(f"{len(verdicts)} new beach(es) evaluated: {len(added)} to add, {len(rejected)} rejected\n")

    for v in verdicts:
        mark = "✓ ADD   " if v["status"] == "add" else "✗ REJECT"
        name = v["entry"].get("name", "<no name>") if isinstance(v["entry"], dict) else "<invalid>"
        print(f"{mark}  {v['id']}  ({name})")
        for r in v["reasons"]:
            print(f"           {r}")
    print()

    return added, rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("new_beaches_path", help="Path to a JSON array of new beach objects")
    parser.add_argument("--target", default="beaches.json", help="File to merge into (default: beaches.json)")
    parser.add_argument("--apply", action="store_true", help="Write the result. Default is dry-run.")
    args = parser.parse_args()

    try:
        with open(args.new_beaches_path, encoding="utf-8") as f:
            new_beaches = json.load(f)
    except FileNotFoundError:
        print(f"❌ {args.new_beaches_path}: file not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ {args.new_beaches_path}: not valid JSON — {e}")
        sys.exit(1)

    if not isinstance(new_beaches, list):
        print(f"❌ {args.new_beaches_path}: expected a JSON array of beach objects, got {type(new_beaches).__name__}")
        sys.exit(1)

    try:
        with open(args.target, encoding="utf-8") as f:
            target_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ {args.target}: file not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ {args.target}: not valid JSON — {e}")
        sys.exit(1)

    existing_beaches = target_data.get("beaches", [])

    verdicts = evaluate(new_beaches, existing_beaches)
    added, rejected = print_report(verdicts)

    if not added:
        print("Nothing to add.")
        sys.exit(0 if not rejected else 1)

    if not args.apply:
        print(f"Dry-run only — {len(added)} entr(y/ies) would be appended to {args.target}. Re-run with --apply to write.")
        sys.exit(0 if not rejected else 1)

    target_data["beaches"].extend(v["entry"] for v in added)
    with open(args.target, "w", encoding="utf-8") as f:
        json.dump(target_data, f, indent=2)

    print(f"✓ Appended {len(added)} entr(y/ies) to {args.target}. meta block left untouched — run update_beaches.py next.")
    sys.exit(0 if not rejected else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""find_duplicates.py — read-only duplicate/health report for beaches.json

Usage: python3 scripts/find_duplicates.py [path]   (default: beaches.json)

Three checks, all diagnostic only:
  1. Duplicate id values
  2. Duplicate name values
  3. Entries within 300m of each other by haversine distance — the important
     one, since the same beach often appears under two different names
     (e.g. "Sandhaven Beach" vs "South Shields").

This script never writes to beaches.json or anything else. It prints a report
and stops — the human decides which entry to keep, since one may have better
restriction data and the other the EA water-quality id.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_beaches import haversine_meters  # noqa: E402

PROXIMITY_METERS = 300


def wq_flag(entry):
    return "yes" if entry.get("water_quality_site_id") not in (None, "") and "water_quality_site_id" in entry else "no"


def print_pair(index_a, entry_a, index_b, entry_b, distance_m=None):
    """Print two entries as a labeled two-column comparison."""
    rows = [
        ("id", entry_a.get("id"), entry_b.get("id")),
        ("name", entry_a.get("name"), entry_b.get("name")),
        ("county", entry_a.get("county"), entry_b.get("county")),
        ("coords", f"{entry_a.get('lat')}, {entry_a.get('lng')}", f"{entry_b.get('lat')}, {entry_b.get('lng')}"),
        ("restriction_type", entry_a.get("restriction_type"), entry_b.get("restriction_type")),
        ("last_verified", entry_a.get("last_verified"), entry_b.get("last_verified")),
        ("water_quality_site_id", wq_flag(entry_a), wq_flag(entry_b)),
    ]
    label_w = max(len(r[0]) for r in rows)
    col_w = max(max(len(str(r[1])), len(str(r[2]))) for r in rows) + 2

    print(f"  {'':<{label_w}}   [A] index {index_a:<6} {'[B] index ' + str(index_b)}")
    for label, a, b in rows:
        print(f"  {label:<{label_w}}   {str(a):<{col_w}} {b}")
    if distance_m is not None:
        print(f"  {'distance':<{label_w}}   {distance_m:.0f}m apart")
    print()


def check_duplicate_ids(beaches):
    by_id = {}
    for i, b in enumerate(beaches):
        by_id.setdefault(b.get("id"), []).append(i)
    return {k: v for k, v in by_id.items() if len(v) > 1}


def check_duplicate_names(beaches):
    by_name = {}
    for i, b in enumerate(beaches):
        by_name.setdefault(b.get("name"), []).append(i)
    return {k: v for k, v in by_name.items() if len(v) > 1}


def check_proximity(beaches, threshold=PROXIMITY_METERS):
    """All unordered pairs (i, j) with i < j whose entries are within threshold metres."""
    matches = []
    n = len(beaches)
    for i in range(n):
        lat_i, lng_i = beaches[i].get("lat"), beaches[i].get("lng")
        if not isinstance(lat_i, (int, float)) or not isinstance(lng_i, (int, float)):
            continue
        for j in range(i + 1, n):
            lat_j, lng_j = beaches[j].get("lat"), beaches[j].get("lng")
            if not isinstance(lat_j, (int, float)) or not isinstance(lng_j, (int, float)):
                continue
            dist = haversine_meters(lat_i, lng_i, lat_j, lng_j)
            if dist < threshold:
                matches.append((i, j, dist))
    return matches


def report_duplicate_ids(beaches, dupes):
    print("=" * 70)
    print(f"1. DUPLICATE IDS — {len(dupes)} found")
    print("=" * 70)
    if not dupes:
        print("  none\n")
        return
    for id_, indices in dupes.items():
        print(f"  id '{id_}' used by {len(indices)} entries: indices {indices}")
        for k in range(len(indices) - 1):
            print_pair(indices[k], beaches[indices[k]], indices[k + 1], beaches[indices[k + 1]])


def report_duplicate_names(beaches, dupes):
    print("=" * 70)
    print(f"2. DUPLICATE NAMES — {len(dupes)} found")
    print("=" * 70)
    if not dupes:
        print("  none\n")
        return

    same_county_groups = {}
    diff_county_groups = {}
    for name, indices in dupes.items():
        counties = {beaches[i].get("county") for i in indices}
        if len(counties) == 1:
            same_county_groups[name] = indices
        else:
            diff_county_groups[name] = indices

    print(f"\n-- Same name, SAME county ({len(same_county_groups)}) — likely genuine duplicates, review these --\n")
    if not same_county_groups:
        print("  none\n")
    for name, indices in same_county_groups.items():
        print(f"  '{name}' — {len(indices)} entries, same county")
        for k in range(len(indices) - 1):
            print_pair(indices[k], beaches[indices[k]], indices[k + 1], beaches[indices[k + 1]])

    print(f"\n-- Same name, DIFFERENT county ({len(diff_county_groups)}) — probably distinct beaches that share a name --\n")
    if not diff_county_groups:
        print("  none\n")
    for name, indices in diff_county_groups.items():
        print(f"  '{name}' — {len(indices)} entries, different counties")
        for k in range(len(indices) - 1):
            print_pair(indices[k], beaches[indices[k]], indices[k + 1], beaches[indices[k + 1]])


def report_proximity(beaches, matches):
    print("=" * 70)
    print(f"3. ENTRIES WITHIN {PROXIMITY_METERS}m OF EACH OTHER — {len(matches)} found")
    print("=" * 70)
    if not matches:
        print("  none\n")
        return
    for i, j, dist in sorted(matches, key=lambda m: m[2]):
        same_name = beaches[i].get("name") == beaches[j].get("name")
        tag = " [also a name match, see section 2]" if same_name else " [different names — likely the same beach under two names]"
        print(f"  pair{tag}")
        print_pair(i, beaches[i], j, beaches[j], distance_m=dist)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "beaches.json"

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ {path}: file not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ {path}: not valid JSON — {e}")
        sys.exit(1)

    beaches = data.get("beaches", [])
    print(f"find_duplicates.py — {path}, {len(beaches)} entries. Read-only, no changes made.\n")

    id_dupes = check_duplicate_ids(beaches)
    name_dupes = check_duplicate_names(beaches)
    proximity_matches = check_proximity(beaches)

    report_duplicate_ids(beaches, id_dupes)
    report_duplicate_names(beaches, name_dupes)
    report_proximity(beaches, proximity_matches)

    print("=" * 70)
    print(
        f"Summary: {len(id_dupes)} duplicate id group(s), {len(name_dupes)} duplicate "
        f"name group(s), {len(proximity_matches)} pair(s) within {PROXIMITY_METERS}m. "
        f"Nothing was changed — this is a report only."
    )


if __name__ == "__main__":
    main()

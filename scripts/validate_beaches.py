#!/usr/bin/env python3
"""validate_beaches.py — structural gate for beaches.json

Usage: python3 scripts/validate_beaches.py [path]   (default: beaches.json)

Exits 1 if any entry fails a hard check, 0 otherwise. Schema is derived from
the fields actually present in the live file (see CLAUDE.md), not from prose —
BeachService.swift isn't in this repo. storm_overflow_active/dog_status_detail
are deliberately NOT part of this schema: they don't appear anywhere in the
live 312 entries and are presumed worker-injected, not stored.

Unrecognized keys on an entry are a WARNING here, never a hard failure — this
only guards structure needed for correct decoding, not schema purity of
already-live data. (merge_beaches.py, which gates *new* entries before they're
ever added, treats the same condition as a hard failure — see KNOWN_KEYS.)

If this fails against a copy of the current live file, the validator's rule is
wrong, not the data. Report it, don't "fix" beaches.json to satisfy the script.
"""

import json
import re
import sys

REQUIRED_KEYS = frozenset({
    "id", "name", "county", "lat", "lng", "restriction_type",
    "restricted_date_start", "restricted_date_end",
    "restricted_time_start", "restricted_time_end",
    "on_lead_required", "notes", "source_url", "last_verified",
})

# Optional but recognized — present on some entries, absent on others.
OPTIONAL_KEYS = frozenset({
    "pspo_expires", "water_quality_authority", "water_quality_site_id",
})

KNOWN_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS

RESTRICTION_TYPES = frozenset({
    "prohibited_seasonal", "on_lead_seasonal",
    "prohibited_year_round", "no_restriction",
})

WATER_QUALITY_AUTHORITIES = frozenset({"ea", "nrw"})

# Wide enough for Shetland/Scilly, tight enough to catch a swapped lat/lng
# or a stray digit.
UK_LAT_RANGE = (49.8, 60.9)
UK_LNG_RANGE = (-8.7, 2.0)

ID_RE = re.compile(r"^gb_[a-z0-9_]+$")
LAST_VERIFIED_RE = re.compile(r"^\d{4}-\d{2}$")
PSPO_EXPIRES_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def entry_label(entry, index):
    return f"[{index}] {entry.get('id', '<no id>')}"


def check_entry(entry, index, seen_ids):
    """Return (errors, warnings) for a single beach entry."""
    errors = []
    warnings = []
    label = entry_label(entry, index)

    if not isinstance(entry, dict):
        return ([f"{label}: entry is not an object"], [])

    missing = REQUIRED_KEYS - entry.keys()
    if missing:
        errors.append(f"{label}: missing required field(s): {', '.join(sorted(missing))}")

    extra = entry.keys() - KNOWN_KEYS
    if extra:
        warnings.append(f"{label}: unrecognized key(s): {', '.join(sorted(extra))}")

    entry_id = entry.get("id")
    if isinstance(entry_id, str):
        if entry_id in seen_ids:
            errors.append(f"{label}: duplicate id (also seen at index {seen_ids[entry_id]})")
        else:
            seen_ids[entry_id] = index
        if not ID_RE.match(entry_id):
            errors.append(f"{label}: id '{entry_id}' does not match gb_<county>_<slug>")
    elif "id" in entry:
        errors.append(f"{label}: id is not a string")

    rtype = entry.get("restriction_type")
    if "restriction_type" in entry and rtype not in RESTRICTION_TYPES:
        errors.append(
            f"{label}: restriction_type '{rtype}' not in "
            f"{sorted(RESTRICTION_TYPES)}"
        )

    lv = entry.get("last_verified")
    if "last_verified" in entry and (not isinstance(lv, str) or not LAST_VERIFIED_RE.match(lv)):
        errors.append(f"{label}: last_verified '{lv}' is not YYYY-MM")

    if "pspo_expires" in entry:
        pe = entry["pspo_expires"]
        if pe is not None and (not isinstance(pe, str) or not PSPO_EXPIRES_RE.match(pe)):
            errors.append(f"{label}: pspo_expires '{pe}' is not YYYY-MM-DD or null")

    lat, lng = entry.get("lat"), entry.get("lng")
    if "lat" in entry or "lng" in entry:
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            errors.append(f"{label}: lat/lng must be numbers")
        else:
            if not (UK_LAT_RANGE[0] <= lat <= UK_LAT_RANGE[1]):
                errors.append(f"{label}: lat {lat} outside UK bounding box")
            if not (UK_LNG_RANGE[0] <= lng <= UK_LNG_RANGE[1]):
                errors.append(f"{label}: lng {lng} outside UK bounding box")

    has_wqa = "water_quality_authority" in entry
    has_wqid = "water_quality_site_id" in entry
    if has_wqa != has_wqid:
        errors.append(
            f"{label}: water_quality_authority and water_quality_site_id "
            f"must both be present or both omitted"
        )
    # A handful of live entries carry both keys as an explicit `null` pair
    # rather than omitting them — "not yet matched" (e.g. Scotland, pending
    # SEPA matching per meta.water_quality_note) as distinct from "definitely
    # not a designated bathing water" (omitted). Treat null as a valid state
    # for either field, not just a real value.
    wqa = entry.get("water_quality_authority")
    if has_wqa and wqa is not None and wqa not in WATER_QUALITY_AUTHORITIES:
        errors.append(
            f"{label}: water_quality_authority '{wqa}' "
            f"not in {sorted(WATER_QUALITY_AUTHORITIES)} (or null)"
        )
    wqid = entry.get("water_quality_site_id")
    if has_wqid and wqid is not None and (not isinstance(wqid, str) or len(wqid) != 5):
        errors.append(f"{label}: water_quality_site_id '{wqid}' is not a 5-character string (or null)")

    return errors, warnings


def validate(data):
    """Return (errors, warnings) for the whole document."""
    errors = []
    warnings = []

    if not isinstance(data, dict) or "meta" not in data or "beaches" not in data:
        return (["top level must be an object with 'meta' and 'beaches' keys"], [])

    meta = data["meta"]
    beaches = data["beaches"]

    if not isinstance(beaches, list):
        return (["'beaches' must be an array"], [])

    seen_ids = {}
    for i, entry in enumerate(beaches):
        e, w = check_entry(entry, i, seen_ids)
        errors.extend(e)
        warnings.extend(w)

    stored_total = meta.get("total_beaches") if isinstance(meta, dict) else None
    if stored_total != len(beaches):
        errors.append(
            f"meta.total_beaches ({stored_total!r}) != actual beach count ({len(beaches)})"
        )

    return errors, warnings


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

    errors, warnings = validate(data)

    if warnings:
        print(f"⚠️  {len(warnings)} warning(s):")
        for w in warnings:
            print(f"  {w}")
        print()

    if errors:
        print(f"❌ {len(errors)} error(s) in {path}:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    beach_count = len(data.get("beaches", []))
    print(f"✓ {path}: valid — {beach_count} beaches, {len(warnings)} warning(s)")
    sys.exit(0)


if __name__ == "__main__":
    main()

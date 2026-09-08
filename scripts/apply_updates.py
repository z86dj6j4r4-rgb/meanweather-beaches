#!/usr/bin/env python3
"""apply_updates.py — apply a patch file to existing beaches.json entries

Usage:
    python3 scripts/apply_updates.py [updates.json]               # dry-run
    python3 scripts/apply_updates.py [updates.json] --apply        # write
    python3 scripts/apply_updates.py [updates.json] --target FILE  # test against a copy

See PSPO_RENEWAL_WORKFLOW.md. `updates.json` is an array of partial objects, each
carrying `id` plus only the fields that change:

    [
      {
        "id": "gb_east_sussex_brighton_central",
        "pspo_expires": "2029-10-19",
        "last_verified": "2026-09",
        "_reason": "Brighton & Hove renewed 20 Oct 2026 for 3 years, restrictions unchanged"
      }
    ]

Rules:
  - `id` must match an existing entry exactly. An unknown id is a hard error that
    aborts the whole run — nothing is written. A partial application is worse
    than none.
  - Any field present in a patch overwrites that field. A field set to explicit
    `null` clears it (distinct from a field simply absent from the patch, which
    is left untouched).
  - `_reason` is documentation for the human and the changelog — stripped before
    the entry is written to beaches.json.
  - Patched entries are re-validated with validate_beaches.py's check_entry, so
    a patch that breaks the schema (bad restriction_type, malformed date, etc.)
    is caught before anything is written.
  - Dry-run by default; nothing is written without --apply. --apply additionally
    refuses to run if the target file already has uncommitted changes (nothing
    to safely roll back to with `git checkout`).
  - On --apply: writes beaches.json (meta block untouched), emits/updates
    CHANGELOG_pending.md, and archives the patch file (with `_reason` intact)
    to updates/applied/YYYY-MM-DD.json.
  - An empty updates.json array leaves the target file untouched entirely.
"""

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_beaches import check_entry  # noqa: E402

IGNORE_KEYS = {"id", "_reason"}
USER_FACING_FIELDS = {
    "restriction_type", "restricted_date_start", "restricted_date_end",
    "restricted_time_start", "restricted_time_end", "on_lead_required",
}
LONG_VALUE_THRESHOLD = 60


def fmt_value(v):
    if v is None:
        return "null"
    return str(v)


def diff_fields(before, patch):
    """Yield (field, old, new) for every field the patch changes."""
    for field, new in patch.items():
        if field in IGNORE_KEYS:
            continue
        old = before.get(field)
        yield field, old, new


def print_diff_report(applications):
    for app in applications:
        entry = app["before"]
        print(f"{app['id']}  {entry.get('name', '<no name>')}")
        for field, old, new in app["diffs"]:
            old_s, new_s = fmt_value(old), fmt_value(new)
            if isinstance(old, str) and isinstance(new, str) and old != new and (
                len(old) > LONG_VALUE_THRESHOLD or len(new) > LONG_VALUE_THRESHOLD
            ):
                print(f"    {field:<22} [changed, {len(old)} chars -> {len(new)} chars]")
            else:
                print(f"    {field:<22} {old_s}  ->  {new_s}")
        print()


def is_real_change(patch):
    return bool((patch.keys() - IGNORE_KEYS) & USER_FACING_FIELDS)


def build_changelog_section(applications):
    today = date.today().isoformat()
    real_by_county = {}
    verified_by_county = {}

    for app in applications:
        county = app["after"].get("county", "Unknown")
        name = app["after"].get("name", app["id"])
        if is_real_change(app["patch"]):
            reason = app["patch"].get("_reason")
            desc = reason if reason else f"{name} — restriction details updated"
            real_by_county.setdefault(county, []).append(desc)
        else:
            verified_by_county.setdefault(county, 0)
            verified_by_county[county] += 1

    lines = [f"## Beach data update — {today}", ""]

    if real_by_county:
        lines.append("**Updated restrictions**")
        for county in sorted(real_by_county):
            for desc in real_by_county[county]:
                lines.append(f"- {county}: {desc}")
        lines.append("")

    if verified_by_county:
        lines.append("**Verified, no change**")
        for county in sorted(verified_by_county):
            n = verified_by_county[county]
            lines.append(f"- {county}: {n} beach{'es' if n != 1 else ''} re-verified")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_changelog(applications, path):
    section = build_changelog_section(applications)
    existing = ""
    p = Path(path)
    if p.exists():
        existing = p.read_text(encoding="utf-8")
    # Newest section on top.
    p.write_text(section + ("\n" + existing if existing else ""), encoding="utf-8")
    return str(p)


def archive_patch(raw_patches, updates_dir):
    Path(updates_dir).mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    candidate = Path(updates_dir) / f"{today}.json"
    suffix = 2
    while candidate.exists():
        candidate = Path(updates_dir) / f"{today}_{suffix}.json"
        suffix += 1
    with open(candidate, "w", encoding="utf-8") as f:
        json.dump(raw_patches, f, indent=2)
    return str(candidate)


def target_is_dirty(target_path):
    """Return True if git reports uncommitted changes for target_path.
    Returns False (assume clean) if git can't answer — e.g. target is a
    scratch copy outside the repo, used for testing."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", target_path],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("updates_path", nargs="?", default="updates.json", help="Path to the patch file (default: updates.json)")
    parser.add_argument("--target", default="beaches.json", help="File to patch (default: beaches.json)")
    parser.add_argument("--apply", action="store_true", help="Write the result. Default is dry-run.")
    args = parser.parse_args()

    try:
        with open(args.updates_path, encoding="utf-8") as f:
            patches = json.load(f)
    except FileNotFoundError:
        print(f"❌ {args.updates_path}: file not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ {args.updates_path}: not valid JSON — {e}")
        sys.exit(1)

    if not isinstance(patches, list):
        print(f"❌ {args.updates_path}: expected a JSON array of patch objects, got {type(patches).__name__}")
        sys.exit(1)

    if not patches:
        print(f"{args.updates_path} is empty — nothing to apply. {args.target} left untouched.")
        sys.exit(0)

    try:
        with open(args.target, encoding="utf-8") as f:
            target_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ {args.target}: file not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ {args.target}: not valid JSON — {e}")
        sys.exit(1)

    beaches = target_data.get("beaches", [])
    by_id = {b["id"]: i for i, b in enumerate(beaches) if isinstance(b.get("id"), str)}

    # Pass 1: every patch must be well-formed and reference a known, unique id.
    # Fail loudly and abort completely — a partial application is worse than none.
    errors = []
    seen_patch_ids = set()
    for i, patch in enumerate(patches):
        if not isinstance(patch, dict):
            errors.append(f"[{i}] patch is not an object")
            continue
        pid = patch.get("id")
        if not isinstance(pid, str):
            errors.append(f"[{i}] patch has no string 'id'")
            continue
        if pid in seen_patch_ids:
            errors.append(f"[{i}] duplicate patch for id '{pid}' within {args.updates_path}")
            continue
        seen_patch_ids.add(pid)
        if pid not in by_id:
            errors.append(f"[{i}] unknown id '{pid}' — no matching entry in {args.target}")

    if errors:
        print(f"❌ {len(errors)} error(s) in {args.updates_path} — aborting, nothing written:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    # Pass 2: apply each patch to an in-memory copy of its entry, re-validate
    # with the same checks validate_beaches.py uses, and record the diff.
    applications = []
    validation_errors = []
    for patch in patches:
        pid = patch["id"]
        idx = by_id[pid]
        before = beaches[idx]
        after = dict(before)
        for field, value in patch.items():
            if field in IGNORE_KEYS:
                continue
            after[field] = value

        entry_errors, entry_warnings = check_entry(after, idx, {})
        if entry_errors:
            for e in entry_errors:
                validation_errors.append(f"patch for '{pid}': {e}")
        for w in entry_warnings:
            print(f"⚠️  patch for '{pid}': {w}")

        applications.append({
            "id": pid,
            "index": idx,
            "before": before,
            "after": after,
            "patch": patch,
            "diffs": list(diff_fields(before, patch)),
        })

    if validation_errors:
        print(f"❌ {len(validation_errors)} entr(y/ies) failed re-validation after patching — aborting, nothing written:")
        for e in validation_errors:
            print(f"  {e}")
        sys.exit(1)

    print(f"{len(applications)} beach(es) patched from {args.updates_path}:\n")
    print_diff_report(applications)

    if not args.apply:
        print(f"Dry-run only — {args.target} not written. Re-run with --apply to write.")
        sys.exit(0)

    if target_is_dirty(args.target):
        print(
            f"❌ {args.target} already has uncommitted changes — refusing to apply. "
            f"Commit or stash first, so a bad patch stays recoverable with "
            f"`git checkout -- {args.target}`."
        )
        sys.exit(1)

    for app in applications:
        beaches[app["index"]] = app["after"]

    with open(args.target, "w", encoding="utf-8") as f:
        json.dump(target_data, f, indent=2)

    target_dir = Path(args.target).resolve().parent
    changelog_path = write_changelog(applications, target_dir / "CHANGELOG_pending.md")
    archive_path = archive_patch(patches, target_dir / "updates" / "applied")

    print(f"✓ Applied {len(applications)} update(s) to {args.target}. meta block left untouched — run update_beaches.py next.")
    print(f"✓ Changelog: {changelog_path}")
    print(f"✓ Patch archived: {archive_path}")


if __name__ == "__main__":
    main()

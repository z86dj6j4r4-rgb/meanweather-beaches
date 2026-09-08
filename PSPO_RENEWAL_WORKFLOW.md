# PSPO renewal workflow

For Claude Code. Companion to `CLAUDE.md` (conventions) and
`CLAUDE_CODE_HANDOVER.md` (tooling build).

This covers **updating existing beach entries**, which is a different and riskier
operation from adding new ones. Adding appends whole entries. Renewal edits fields
inside entries that are already live and serving 300+ users.

## Why this exists

PSPOs are made for three-year terms. `update_beaches.py` already warns when
`pspo_expires` is approaching or past. When that fires, the council has usually
either renewed the order (new expiry date, restrictions often unchanged), changed
the restrictions, or let it lapse entirely.

That means a steady trickle of small edits to existing entries, forever. Currently
the file has orders expiring across 2026 (15 beaches), 2027 (174) and 2028 (60),
so this is not an occasional task — 2027 alone is over half the file.

Hand-editing 174 entries is not viable. It needs to be a patch operation.

## The split

**Research happens in chat, not here.** Verifying what a council has actually done
requires reading the order, judging whether a source is authoritative, and noticing
when restrictions have changed rather than just dates. That produces a patch file.

**Claude Code applies the patch.** Mechanical, validated, reversible.

Do not attempt to research council orders as part of applying a patch.

## Patch file format

`updates.json` — an array of partial objects. Each carries `id` plus **only the
fields that change**. Nothing else.

```json
[
  {
    "id": "gb_east_sussex_brighton_central",
    "pspo_expires": "2029-10-19",
    "last_verified": "2026-09",
    "_reason": "Brighton & Hove renewed 20 Oct 2026 for 3 years, restrictions unchanged"
  },
  {
    "id": "gb_kent_whitstable",
    "restricted_date_start": "05-01",
    "notes": "Thanet extended the exclusion to the northern sea wall from 2027.",
    "pspo_expires": "2030-03-31",
    "last_verified": "2026-09",
    "_reason": "New order adds a year-round section — restriction_type may need review"
  }
]
```

Rules:

- `id` is required and must match an existing entry exactly. **Fail loudly on an
  unknown id** — do not create a new entry from a patch.
- Any field present is overwritten. Any field absent is left untouched.
- `_reason` is documentation for the human and the changelog. Strip it before
  writing to `beaches.json`.
- A field set to `null` means "clear this value", which is different from omitting
  it. Handle both.

## `scripts/apply_updates.py`

Dry-run by default; `--apply` to write.

1. Load `beaches.json` and `updates.json`.
2. For each patch, find the entry by `id`. Unknown id → error, abort, change
   nothing. A partial application is worse than none.
3. Print a **field-level diff** before writing:

```
gb_east_sussex_brighton_central  Brighton Central Beach
    pspo_expires   2026-10-19  ->  2029-10-19
    last_verified  2025-11     ->  2026-09

gb_kent_whitstable  Whitstable Beach
    restricted_date_start  null  ->  "05-01"
    notes          [changed, 84 chars -> 91 chars]
    pspo_expires   2027-03-31  ->  2030-03-31
```

4. Require confirmation, or `--apply` given explicitly.
5. Write with `json.dump(data, f, indent=2)` to match `update_beaches.py`.
6. Emit `CHANGELOG_pending.md` (see below).
7. Do **not** touch the metadata block — `update_beaches.py` owns that.

## Changelog output

The script knows exactly what changed, so release notes come free. Write
`CHANGELOG_pending.md` grouped by county, in plain language suitable for App Store
"What's New" text — not field names and ids.

```markdown
## Beach data update — 2026-09-08

**Updated restrictions**
- Kent: Whitstable Beach now has a year-round restricted section

**Verified, no change**
- East Sussex: 5 Brighton & Hove beaches re-verified (order renewed to 2029)
```

Rules for the text:

- A `pspo_expires` change alone is "re-verified" — users do not care about order
  expiry dates, only about whether the rules changed.
- A change to `restriction_type`, dates, times, or `on_lead_required` is a real
  user-facing change and gets its own line.
- Group by county, and collapse repeats ("5 Brighton & Hove beaches") rather than
  listing every beach.
- Never mention ids, field names, or JSON.

## Full sequence

```bash
# 1. See what needs checking
python3 update_beaches.py

# 2. [Research happens in chat — produces updates.json]

# 3. Preview the changes
python3 scripts/apply_updates.py            # dry-run

# 4. Apply
python3 scripts/apply_updates.py --apply

# 5. Structural check
python3 scripts/validate_beaches.py

# 6. Metadata, totals, coverage, next reminders
python3 update_beaches.py

# 7. Commit
git add beaches.json CHANGELOG_pending.md
git commit -m "beaches: PSPO renewals (county, county)"
git push

# 8. Confirm the worker is serving it (6h cache — may lag)
./scripts/verify_deploy.sh
```

Steps 5 and 6 are not optional and not interchangeable. The validator catches
structural damage; `update_beaches.py` fixes metadata drift and re-scans expiry
dates so the next reminder cycle is correct.

## Safety requirements

- **Never edit `beaches.json` by hand.** The whole point of the patch file is that
  a small file is safe to hand-write and a 6000-line one is not.
- The script must refuse to run on a dirty working tree, or warn clearly. A failed
  patch should be recoverable with `git checkout -- beaches.json`.
- Empty `updates.json` must produce a byte-identical `beaches.json`. Test this.
- Archive applied patches to `updates/applied/YYYY-MM-DD.json` rather than
  deleting, so there is a record of what was changed and why (`_reason` is the
  audit trail).

## Things that need judgement, not automation

Flag these for the human rather than handling silently:

- A renewal that **changes** `restriction_type` — the vocabulary is fixed and a new
  value needs a decision, plus possibly a change in `BeachService.swift`.
- A mid-month start date. `dogStatusNow` currently parses only the month and
  discards the day, so `05-15` would display as banned from 1 May. Reject these
  until that is fixed.
- An order that has **lapsed with no replacement**. That is not a date change, it
  is a restriction change — the beach may now be unrestricted, and the entry needs
  `restriction_type` updating too, not just `pspo_expires`.
- Scotland. Scottish councils do not use PSPOs (England and Wales legislation).
  Fife, East Lothian and Edinburgh entries use byelaws with no fixed expiry, so
  `pspo_expires: null` is correct there and should never be "fixed".
- Private beaches. Landowner controls are not council orders and have no expiry.
  North Devon publishes a list of these; Tunnels Beach and Hartland Quay are
  examples already in the file.

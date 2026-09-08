# Handover: beaches.json tooling

Brief for Claude Code. Read this and `CLAUDE.md` before doing anything.

## Context

`beaches.json` holds UK beach dog-restriction data for MeanWeather (iOS, live on the App
Store). It has **300+ entries** and is served to users via GitHub Pages → a Cloudflare
worker → the app. It is consumed by `BeachResult` in `BeachService.swift`.

The file has been hand-edited to date. That no longer scales:

1. **Hand-pasting entries breaks the file.** A recent paste of new beaches replaced
   the file's closing braces and had to be rolled back with `git checkout`. Nothing
   was pushed and no users were affected, but this is the third or fourth time.
2. **Structural breakage is easy and silent.** `JSONDecoder` fails the *entire array*
   if one element fails to decode, so a single entry missing a non-optional field
   blanks every beach in the app. There is no error surfaced to the user — just an
   empty list.
3. **Matching beaches to EA bathing water ids is manual and error-prone.** The EA's
   official names differ routinely from council and colloquial names, so name-based
   lookup fails often.

The working tree is currently clean and matches what is serving users. Build the
tooling against this known-good state.

## Ground rules

- **Do not edit `beaches.json` until explicitly told to.** Work on a copy.
- Build and prove the tooling first, run it against the real file second, as a
  separate commit.
- Derive the schema from `BeachResult` in `BeachService.swift`, not from prose.
  If this document and the Swift model disagree, the Swift model wins — say so.
- Ask before inventing a convention. Several field conventions in this repo were
  guessed at earlier and may be wrong.

## Before writing any code

Take a snapshot so regressions are detectable:

```bash
cp beaches.json reference/beaches.snapshot.json
git add reference/beaches.snapshot.json && git commit -m "snapshot before tooling"
```

Then read and report back on:

- `head -40 beaches.json` — the metadata block, including `coverage` and any
  hand-maintained total
- 2–3 representative entries, including one South West beach with storm overflow
  populated and one with no water-quality fields
- `BeachResult` and `dogStatusNow` in `BeachService.swift`
- The worker source if it is in this repo — specifically, how
  `water_quality_site_id` is used to call the EA API, and whether a region prefix
  is reconstructed

State what you found before proceeding. Do not assume.

## Task 0 — Duplicate health check

The file has been hand-maintained for a long time and has never been checked for
duplicates. There may well be beaches entered twice under different names.

Write `scripts/find_duplicates.py` that reports, for the whole file:

- Exact duplicate `id` values
- Exact duplicate `name` values
- **Entries within 300m of each other** — this is the important one. The same beach
  appears under different names (e.g. "Sandhaven Beach" vs "South Shields"), so
  coordinate proximity is the only reliable detector.

Output a review list showing both entries side by side with their ids, names,
coordinates, distance apart, and `last_verified`. **Do not auto-delete anything** —
the human decides which to keep, since one entry may have better restriction data
and the other may have the EA id.

This is diagnostic only at this stage. Report findings and stop.

## Task 1 — Validator

`scripts/validate_beaches.py`, exit 1 on any failure. Checks:

- File is valid JSON and matches the expected top-level shape
- No duplicate ids
- Every entry has all non-optional `BeachResult` fields (confirm which from the
  Swift model — at minimum `id`, `name`, `lat`, `lng`, `last_verified`,
  `storm_overflow_active`)
- `restriction_type` is in the allowed set (derive the set from what is already
  in the file; report it, don't assume)
- Coordinates inside a UK bounding box
- `water_quality_site_id` is a 5-character **string** with leading zeros intact
- `water_quality_authority` is `"ea"` or `"nrw"` only
- Welsh counties never carry `"ea"`
- Stored total in metadata equals actual array length
- `coverage` array equals the sorted set of counties present
- No two entries within 300m (warning, not failure)

**Calibrate it:** run against the current file *before* the 15 are cleaned up.
Report what it finds. If it fails on data that is live and working, the validator
is wrong, not the data — fix the validator.

## Task 2 — EA reference cache

`scripts/refresh_ea_cache.py` → writes `reference/ea_bathing_waters.json`.

Source: `https://environment.data.gov.uk/doc/bathing-water.json?_pageSize=500`
(paginate; there are ~400 designated bathing waters in England).

Store per record: `eubwid`, numeric site id, official name, lat, long, district.

Notes:
- Leading zeros are significant. Codes are 5 chars; North East ones are `0xxxx`.
  Never parse as int.
- Region prefixes: `ukc` North East, `ukd` North West, `ukh` East, `ukk` South West.
- **Wales is not in this API.** Bathing water reporting for Wales moved to Natural
  Resources Wales in 2015. Welsh entries use `"nrw"` and a separate id scheme —
  match the format already used by the ~38 existing `nrw` entries in the file.
- Commit the cache. Refresh a couple of times a year; designations change rarely.

## Task 3 — Merge script

`scripts/merge_beaches.py new_beaches.json [--apply]`. Dry-run by default.

Behaviour:

1. Load the new beaches file and the EA cache.
2. For each new beach, find the nearest EA sampling point by coordinate distance.
   - Within 400m → attach `water_quality_authority: "ea"` and the site id
   - 400m–1km → attach but flag for review
   - Over 1km, or no match → omit both water-quality keys entirely (do not write
     `null` — Swift optionals decode a missing key as nil cleanly). Many beaches
     genuinely are not designated bathing waters; this is normal.
3. **Match on coordinates, never on names.** The EA's official names differ
   routinely from council and colloquial names — Sandhaven is "South Shields",
   Longsands is "Tynemouth Long Sands South", Seaburn is "Seaburn - Sunderland".
   Name matching has already failed repeatedly.
4. Check each new beach against existing entries for proximity duplicates before
   appending. Refuse to add anything within 300m of an existing beach; report it.
5. Rewrite the metadata block at the top of the file. It contains `version`,
   `last_updated` and `coverage`, all currently maintained by hand and therefore
   prone to drift. On every run:
   - `coverage` = sorted set of counties present in the beaches array
   - `last_updated` = today's date
   - `version` = auto-increment the patch number (this is informational for the
     maintainer only; the app does not read it — its purpose is confirming that
     what the worker is serving matches what was last committed)
   - any stored total = actual array length
6. Print a review table: beach → matched EA name → site id → distance → verdict.

**Regression test:** running the merge with an empty new-beaches file must produce
output byte-identical to `reference/beaches.snapshot.json` except for
`last_updated` and `version`. If a formatting pass silently rewrites 300 existing
entries, this catches it. Write this test before the merge script itself.

**First live input:** three South Tyneside beaches are pending and will be
supplied as `new_beaches.json` — Sandhaven Beach (EA `05300`), Littlehaven Beach
(not an EA-designated bathing water, so no water-quality keys) and Marsden Bay
(EA `05400`). These are the merge script's first real test. The coordinates in
that file are approximations and must be geocoded properly before the merge is
applied — flag them rather than trusting them.

## Task 4 — Staleness report

PSPOs are made for **three-year terms** and must be renewed. Several entries in the
file are past their original term already. Left unmanaged, the app will show
restrictions that no longer legally exist.

`scripts/stale_check.py`:

- Lists entries with `last_verified` older than 12 months, oldest first
- Flags any entry whose `notes` mention an expiry or commencement year now past
- Prioritises entries with an active restriction over those with
  `restriction_type: "none"` — a stale "no restrictions" entry matters far less
  than a stale ban
- Output should be a work list of councils to re-check, grouped by council where
  possible

Schedule as a GitHub Action each **February**, ahead of the May season start.

## Task 5 — Gates

- Pre-commit hook running `validate_beaches.py`
- GitHub Action running the same validator on push (Pages serves whatever is on
  main regardless of whether it decodes, so the local hook alone is insufficient)
- `scripts/verify_deploy.sh` — hits the worker with coordinates near a
  newly-added beach and confirms that beach's id appears in the payload. The
  worker caches for **6 hours**, so if the beach is absent the script should say
  so plainly with the expected cache expiry, rather than implying failure.

Checking the endpoint merely responds is not enough — a decode failure returns a
valid 200 with an undecodable body, and the app shows an empty list.

## Known trap: mid-month start dates

`dogStatusNow` in `BeachService.swift` parses **only the month** from
`restricted_date_start` via `monthInt(from:)`; the day is discarded.

Fine for `05-01` → `09-30`. Wrong for anything starting mid-month. Cornwall's Blue
Flag beaches run 15 May – 30 Sept and would display as banned from 1 May.

The validator should reject any entry with a non-`01` start day until
`monthInt` and the `inSeason` comparison are made day-aware. Flag this; do not fix
it as part of this work unless asked.

## Order of work

0. Snapshot, then report findings from the "before writing any code" section
1. `find_duplicates.py` — run as a health check, report, do not delete
2. `validate_beaches.py`, calibrated against the live file
3. EA cache
4. Merge script + regression test, then the three South Tyneside beaches as its
   first live run
5. Staleness report
6. Hooks and Action

Stop and check in after each numbered step.

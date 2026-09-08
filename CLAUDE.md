# Adding beaches to beaches.json

Reference for Claude Code. Read this fully before editing `beaches.json`.

## What this file is

`beaches.json` is the source of UK beach dog-restriction data for MeanWeather. It lives in
this repo, is published via GitHub Pages, and is served to the app through a Cloudflare
worker at `https://beaches.rnv4mj76rr.workers.dev/beaches/nearby?lat=&lon=&radius=`
with a 6-hour cache TTL. The app consumes it via `BeachResult` in `BeachService.swift`,
which lives in the separate iOS app repo, not here.

Two things every new beach needs:

1. **The dog restriction rules** — from the council's own PSPO (Public Spaces Protection
   Order) page, not from a dog-friendly-beaches blog.
2. **The EA bathing water code** — a 5-digit sampling point ID, if the beach is a
   designated bathing water. Many are not, and that is fine.

## Never open beaches.json in an editor

Scripts own this file. Editing it by hand, or leaving it open in a tab while a script
runs, causes save conflicts that can silently revert work. Use `new_beaches.json` (with
`scripts/merge_beaches.py`) for additions, and terminal commands (`grep`, `jq`,
`python3 -m json.tool`, the scripts in `scripts/`) to inspect it — never an editor tab.

## File shape

Top-level **object**, not a bare array. There is a metadata block first (including a
`coverage` array of county names), then the beaches array. The file ends:

```
  }
 ]
}
```

A missing final `}` is the single most common breakage. It produces a
"Expecting ',' delimiter" error pointing at the *last line of the file*, which is
misleading — the parser only reports where it gave up, not where the fault is.

## Entry schema

Field names are snake_case in JSON. `BeachService.swift` is not in this repo (it lives in
the iOS app repo) — this schema is derived from the **312 entries actually in the live
file**, confirmed field-by-field, not from the Swift model. If you get access to
`BeachResult` and it disagrees with this, the Swift model wins — update this doc and say so.

```json
{
  "id": "gb_county-slug_beach-slug",
  "name": "Beach Name",
  "county": "County",
  "lat": 00.0000,
  "lng": -0.0000,
  "restriction_type": "prohibited_seasonal | on_lead_seasonal | prohibited_year_round | no_restriction",
  "restricted_date_start": "MM-DD",
  "restricted_date_end": "MM-DD",
  "restricted_time_start": "HH:mm",
  "restricted_time_end": "HH:mm",
  "on_lead_required": false,
  "notes": "Human-readable rule detail, FPN amount, enforcement, caveats.",
  "source_url": "https://council.gov.uk/...",
  "last_verified": "YYYY-MM",
  "pspo_expires": "YYYY-MM-DD",
  "water_quality_authority": "ea | nrw",
  "water_quality_site_id": "05300"
}
```

There is no separate `dog_status_detail` field — the human-readable rule description lives
in `notes`, alongside enforcement/FPN detail.

`storm_overflow_active` and `dog_status_detail` do **not** belong in `beaches.json` — they
appear nowhere in the live file. If something injects storm-overflow status, it happens at
the Cloudflare worker, at request time, not in this stored file. Do not add either key to
an entry.

### Required vs optional

`id`, `name`, `county`, `lat`, `lng`, `restriction_type`, `restricted_date_start`,
`restricted_date_end`, `restricted_time_start`, `restricted_time_end`, `on_lead_required`,
`notes`, `source_url` and `last_verified` are present on every entry — always include them.

`pspo_expires` is present on most entries but is `null` for beaches with no fixed-term
order — Scottish byelaw beaches (Fife, East Lothian, Edinburgh) and private/landowner-
controlled beaches (e.g. Tunnels Beach, Hartland Quay) genuinely have no PSPO to expire.

`water_quality_authority` and `water_quality_site_id` are optional and always appear
together. **Omit both keys entirely** rather than writing `null` when a beach has no EA/NRW
designation — the app's decoder treats a missing key as cleanly absent. A small number of
existing entries (mostly Scotland, where SEPA matching is pending per `meta.water_quality_note`)
carry both keys as an explicit `null` pair instead — that's a distinct "not yet matched"
state from older data, not a convention to follow for new entries.

The date/time fields are written as explicit `null` when a beach has no restriction,
because `dogStatusNow` checks them for nil to decide "always allowed".

### Why one bad entry breaks everything

`JSONDecoder` fails the **entire array** if a single element fails to decode. One entry
missing `last_verified` wipes out every beach in the response, silently. This exact bug
already bit us once via `GeocodingResult.country`. Validate before pushing.

## Finding the EA bathing water code

The EA publishes ~400 designated bathing waters in England. The code stored in
`water_quality_site_id` is the **numeric half** of the `eubwid` — e.g. `ukc2204-05300`
is stored as `"05300"`.

**Leading zeros matter.** North East codes are in the `0xxxx` range. Never let the value
pass through `parseInt` or a spreadsheet.

Look one up by name:

```bash
curl -s "https://environment.data.gov.uk/doc/bathing-water.json?name=Marsden" \
  | jq -r '.result.items[]?.eubwidNotation'
```

The name filter is an **exact match** on the EA's official name, which often differs from
the colloquial or council name:

| You'd call it | EA calls it |
|---|---|
| Sandhaven | South Shields |
| Longsands | Tynemouth Long Sands South |
| Seaburn | Seaburn - Sunderland |
| Roker | Roker - Sunderland |

If a name misses, sweep a whole region and grep locally:

```bash
curl -s "https://environment.data.gov.uk/doc/bathing-water.json?_pageSize=500" \
  | jq -r '.result.items[]? | select(.eubwidNotation | startswith("ukc")) |
           "\(.name._value // .label[0]._value) -> \(.eubwidNotation)"'
```

Region prefixes seen so far: `ukc` North East, `ukd` North West, `ukh` East,
`ukk` South West. Wales is **not** in this API — bathing water reporting for Wales moved
to Natural Resources Wales in 2015. Welsh beaches use `"nrw"` and NRW's own ID scheme;
match the format used by existing `nrw` entries in the file.

If a beach returns nothing, it is probably not designated (needs roughly 100+ bathers a
day in season). Omit both water-quality keys. This is normal for small beaches.

## Finding the PSPO rules

Use the council's own page or the sealed PSPO PDF. Local news is acceptable only when it
quotes the council directly, and the council URL still goes in `source_url`.

Record in `notes`:

- FPN amount and any early-payment reduction
- The PSPO's commencement date and term (they run **3 years** and must be renewed)
- Whether the restriction is a partial zone, and what the boundary is

**Flag expired orders.** Several PSPOs in the file are past their original 3-year term
and need re-checking — Sea Palling (from May 2021) and Isles of Scilly (July 2020).
Do not silently assume renewal.

## Known trap: mid-month start dates

`dogStatusNow` in `BeachService.swift` parses **only the month** from
`restricted_date_start` via `monthInt(from:)`. The day is discarded.

This is fine for 05-01 → 09-30 entries. It is **wrong** for anything starting mid-month.
Cornwall's Blue Flag beaches (Porthmeor, Porthminster, Carbis Bay) run 15 May – 30 Sept
and would show as banned from 1 May.

Fix `monthInt` and the `inSeason` comparison to be day-aware **before** adding any entry
with a non-01 start day.

Variable dates (Fylde's St Annes starts Good Friday) cannot be represented at all —
approximate conservatively and say so in `notes`.

## Validation before commit

Run all of these. Each catches something the others miss.

```bash
# 1. Is it valid JSON at all?
python3 -m json.tool beaches.json > /dev/null && echo "valid JSON"

# 2. Beach count — compare before and after your edit
grep -c '"id":' beaches.json

# 3. Duplicate IDs — valid JSON, but breaks Identifiable in SwiftUI
grep -o '"id": "[^"]*"' beaches.json | sort | uniq -d

# 4. Every entry has the non-optional fields (counts must all match count from #2)
grep -c '"last_verified"' beaches.json
grep -c '"restriction_type"' beaches.json

# 5. Confirm today's additions landed (adjust the month to this one, format is YYYY-MM)
grep -c '"last_verified": "2026-09"' beaches.json
```

`scripts/validate_beaches.py` runs a stricter version of all five checks plus the
UK-bounding-box, `water_quality_site_id`-length, `restriction_type`-enum and
`meta.total_beaches`-vs-actual-count checks — run it too. `update_beaches.py` rebuilds the
`coverage` array and `meta.total_beaches`/`last_updated` automatically; run it after any
edit rather than updating those fields by hand.

## Commit and deploy

```bash
git add beaches.json
git commit -m "beaches: add N beaches (region)"
git push
```

GitHub Pages redeploys automatically. The Cloudflare worker caches for 6 hours, so the
app will not see changes immediately — this is expected, not a bug. To verify sooner,
hit the worker directly with coordinates near a new beach and check it appears.

## Checklist for a new batch

- [ ] Every beach sourced from a council PSPO page, URL in `source_url`
- [ ] `last_verified` set to this month (`YYYY-MM`) on every new entry
- [ ] `pspo_expires` set (or left `null` only for byelaw/private beaches) on every new entry
- [ ] Coordinates geocoded, not recalled from memory — verify each one
- [ ] EA code looked up via the API, leading zeros intact
- [ ] Beaches with no EA designation have both water-quality keys omitted
- [ ] Welsh beaches use `"nrw"`, not `"ea"`
- [ ] No `storm_overflow_active` or `dog_status_detail` keys added — not part of this schema
- [ ] No mid-month start dates unless `monthInt` has been made day-aware
- [ ] All validation commands and `scripts/validate_beaches.py` pass
- [ ] `update_beaches.py` run so `coverage`/`total_beaches`/`last_updated` are current
- [ ] File ends `}` then `]` then `}`

# Adding beaches to beaches.json

Reference for Claude Code. Read this fully before editing `beaches.json`.

## What this file is

`beaches.json` is the source of UK beach dog-restriction data for MeanWeather. It lives in
this repo, is published via GitHub Pages, and is served to the app through a Cloudflare
worker at `https://beaches.rnv4mj76rr.workers.dev/beaches/nearby?lat=&lon=&radius=`
with a 6-hour cache TTL. The app consumes it via `BeachService.swift`.

Two things every new beach needs:

1. **The dog restriction rules** — from the council's own PSPO (Public Spaces Protection
   Order) page, not from a dog-friendly-beaches blog.
2. **The EA bathing water code** — a 5-digit sampling point ID, if the beach is a
   designated bathing water. Many are not, and that is fine.

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

Field names are snake_case in JSON and map to camelCase in `BeachResult` in
`BeachService.swift`. Check that file if the model has changed.

```json
{
  "id": "kebab-case-unique",
  "name": "Beach Name",
  "county": "County",
  "lat": 00.0000,
  "lng": -0.0000,
  "restriction_type": "seasonal | seasonal_time | seasonal_partial | none",
  "dog_status_detail": "Human-readable sentence describing the rule.",
  "restricted_date_start": "MM-DD",
  "restricted_date_end": "MM-DD",
  "restricted_time_start": "HH:mm",
  "restricted_time_end": "HH:mm",
  "on_lead_required": false,
  "notes": "Enforcement detail, PSPO expiry, caveats.",
  "source_url": "https://council.gov.uk/...",
  "last_verified": "YYYY-MM-DD",
  "water_quality_authority": "ea | nrw",
  "water_quality_site_id": "05300",
  "storm_overflow_active": false
}
```

### Required vs optional

`storm_overflow_active` is a non-optional `Bool` in Swift — **always include it**, set to
`false` unless there is a live SWW feed for that beach. `last_verified` is likewise
non-optional.

`water_quality_authority`, `water_quality_site_id` and `storm_overflow_water_course` are
`String?`. **Omit the key entirely** rather than writing `null` — Swift's decoder uses
`decodeIfPresent` for optionals, so a missing key becomes `nil` cleanly.

The date/time fields are `String?` and *should* be written as explicit `null` when a beach
has no restriction, because `dogStatusNow` checks them for nil to decide "always allowed".

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
grep -c '"storm_overflow_active"' beaches.json

# 5. Confirm today's additions landed
grep -c '"last_verified": "YYYY-MM-DD"' beaches.json
```

Then update the `coverage` array in the metadata block if any new county was introduced,
and bump any total/`generated_at` field that is maintained by hand.

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
- [ ] `last_verified` set to today on every new entry
- [ ] Coordinates geocoded, not recalled from memory — verify each one
- [ ] EA code looked up via the API, leading zeros intact
- [ ] Beaches with no EA designation have both water-quality keys omitted
- [ ] Welsh beaches use `"nrw"`, not `"ea"`
- [ ] `storm_overflow_active` present on every entry
- [ ] No mid-month start dates unless `monthInt` has been made day-aware
- [ ] All five validation commands pass
- [ ] `coverage` array updated for new counties
- [ ] File ends `}` then `]` then `}`

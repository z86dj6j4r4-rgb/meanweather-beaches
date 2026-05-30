[README.md](https://github.com/user-attachments/files/28427806/README.md)
# MeanWeather Beach Database

Public API for UK dog beach restrictions. Used by the MeanWeather iOS app.

## Endpoint

```
GET https://z86dj6j4r4-rgb.github.io/meanweather-beaches/beaches.json
```

## Coverage

| County | Beaches | Source | PSPO valid until |
|--------|---------|--------|-----------------|
| Cornwall | 29 | cornwall.gov.uk | 2028 |
| Devon | 13 | northdevon.gov.uk, eastdevon.gov.uk, torbay.gov.uk | 2026 |
| Dorset | 10 | dorsetcouncil.gov.uk | Dec 2026 |
| Somerset | 6 | somerset.gov.uk | 2026 |
| Pembrokeshire | 12 | pembrokeshire.gov.uk | 2026 |
| Yorkshire | 13 | northyorks.gov.uk, eastriding.gov.uk | 2026 |
| Northumberland | 8 | northumberland.gov.uk | 2026 |
| Suffolk | 8 | eastsuffolk.gov.uk, waveney.gov.uk | 2026 |
| Norfolk | 7 | north-norfolk.gov.uk, west-norfolk.gov.uk | 2026 |
| **Total** | **106** | | |

## Coming soon
- Sussex (Brighton, Eastbourne, Worthing)
- Kent (Whitstable, Margate, Folkestone)
- Hampshire & Isle of Wight
- Lincolnshire
- Wales — Gower Peninsula, Anglesey

## Restriction types

| Type | Meaning |
|------|---------|
| `prohibited_seasonal` | Dogs banned during dates/times shown |
| `on_lead_seasonal` | Dogs allowed but must be on lead during dates/times |
| `prohibited_year_round` | Dogs never permitted |
| `no_restriction` | Dogs welcome at all times |

## Response format

```json
{
  "meta": {
    "version": "1.0.0",
    "last_updated": "2026-05-30",
    "total_beaches": 106
  },
  "beaches": [
    {
      "id": "gb_cornwall_carbis_bay",
      "name": "Carbis Bay Beach",
      "county": "Cornwall",
      "lat": 50.1911,
      "lng": -5.474,
      "restriction_type": "prohibited_seasonal",
      "restricted_date_start": "05-15",
      "restricted_date_end": "09-30",
      "restricted_time_start": "10:00",
      "restricted_time_end": "18:00",
      "on_lead_required": false,
      "notes": "Blue Flag beach - longer restriction period",
      "source_url": "https://www.cornwall.gov.uk/...",
      "last_verified": "2026-05"
    }
  ]
}
```

## Data accuracy

All restrictions sourced from official council PSPO pages. PSPOs are reviewed every 3 years.
`last_verified` shows when each entry was last checked.

Found an error? Open an issue on this repo.

## Usage

Free to use. Attribution appreciated: "Beach data: MeanWeather"

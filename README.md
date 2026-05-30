# MeanWeather Beach Database

Public API for UK dog beach restrictions. Used by the MeanWeather iOS app.

## Endpoints

### All beaches
```
GET https://timleavy.github.io/meanweather-beaches/beaches.json
```

### Response format
```json
{
  "meta": {
    "version": "1.0.0",
    "last_updated": "2026-05-30",
    "coverage": ["Cornwall", "Devon", "Dorset"],
    "total_beaches": 52
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
      "source_url": "https://www.cornwall.gov.uk/environment/animal-welfare-and-enforcement/dogs-on-beaches/",
      "last_verified": "2026-05"
    }
  ]
}
```

## Restriction types

| Type | Meaning |
|------|---------|
| `prohibited_seasonal` | Dogs banned during dates/times shown |
| `on_lead_seasonal` | Dogs allowed but must be on lead during dates/times |
| `prohibited_year_round` | Dogs never permitted |
| `no_restriction` | Dogs welcome at all times |

## Coverage

| County | Beaches | Source | PSPO valid until |
|--------|---------|--------|-----------------|
| Cornwall | 29 | cornwall.gov.uk | 2028 |
| Devon | 13 | northdevon.gov.uk, eastdevon.gov.uk, torbay.gov.uk | 2026 |
| Dorset | 10 | dorsetcouncil.gov.uk | Dec 2026 |

## Coming soon
- Somerset
- Pembrokeshire
- Suffolk / Norfolk
- Yorkshire coast
- Northumberland

## Data accuracy
All restrictions are sourced from official council PSPO pages.
PSPOs are reviewed every 3 years — `last_verified` shows when each entry was last checked.

Found an error? Open an issue or email meanweather@frapply.com

## Usage
Free to use. Attribution appreciated: "Beach data: MeanWeather"

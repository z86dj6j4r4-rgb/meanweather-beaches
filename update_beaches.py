#!/usr/bin/env python3
# update_beaches.py — MeanWeather Beach Data Maintenance Tool
# Run before every git push: python3 update_beaches.py
#
# What it does:
#   1. Counts actual beach entries and updates meta.total_beaches
#   2. Updates meta.last_updated to today
#   3. Warns about PSPOs expiring within 90 days
#   4. Flags any already-expired PSPOs

import json
from datetime import date, datetime

WARN_DAYS = 90  # warn this many days before expiry

with open('beaches.json') as f:
    data = json.load(f)

count = len(data['beaches'])
today = date.today()

# Update meta
data['meta']['total_beaches'] = count
data['meta']['last_updated'] = str(today)

# Check PSPOs
expired = []
expiring_soon = []

for beach in data['beaches']:
    expiry_str = beach.get('pspo_expires')
    if not expiry_str:
        continue
    try:
        expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()
        days_left = (expiry_date - today).days
        if days_left < 0:
            expired.append((beach['name'], beach['county'], expiry_str, abs(days_left)))
        elif days_left <= WARN_DAYS:
            expiring_soon.append((beach['name'], beach['county'], expiry_str, days_left))
    except ValueError:
        pass

# Save
with open('beaches.json', 'w') as f:
    json.dump(data, f, indent=2)

# Report
print(f"✓ beaches.json updated: {count} beaches | {today}")
print()

if expired:
    print(f"{'='*55}")
    print(f"🚨  {len(expired)} EXPIRED PSPO(s) — verify and update NOW:")
    print(f"{'='*55}")
    for name, county, expiry, days_ago in sorted(expired, key=lambda x: x[2]):
        print(f"  • {name} ({county})")
        print(f"    Expired: {expiry} ({days_ago} days ago)")
    print()

if expiring_soon:
    print(f"{'='*55}")
    print(f"⏰  {len(expiring_soon)} PSPO(s) expiring within {WARN_DAYS} days:")
    print(f"{'='*55}")
    for name, county, expiry, days_left in sorted(expiring_soon, key=lambda x: x[3]):
        print(f"  • {name} ({county})")
        print(f"    Expires: {expiry} ({days_left} days)")
    print()

if not expired and not expiring_soon:
    print(f"✓ All PSPOs current — nothing expiring within {WARN_DAYS} days")

# Summary of upcoming expirations by year
print()
from collections import Counter
years = Counter()
for beach in data['beaches']:
    exp = beach.get('pspo_expires')
    if exp:
        years[exp[:4]] += 1
print("PSPO expiry summary:")
for year, n in sorted(years.items()):
    marker = " ← CHECK NOW" if year <= str(today.year) else ""
    print(f"  {year}: {n} beaches{marker}")

#!/usr/bin/env python3
# update_beaches.py — MeanWeather Beach Data Maintenance Tool
# Run before every git push: python3 update_beaches.py
#
# What it does:
#   1. Counts actual beach entries and updates meta.total_beaches
#   2. Updates meta.last_updated to today
#   3. Warns about PSPOs expiring within 90 days
#   4. Generates a .ics calendar file for any expiring/expired PSPOs

import json
from datetime import date, datetime, timedelta
from collections import Counter
import uuid

WARN_DAYS = 90

with open('beaches.json') as f:
    data = json.load(f)

count = len(data['beaches'])
today = date.today()

# Update meta
data['meta']['total_beaches'] = count
data['meta']['last_updated'] = str(today)

# Rebuild coverage automatically
counties = list(set(b.get('county', '') for b in data['beaches'] if b.get('county')))
data['meta']['coverage'] = sorted(counties)

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
            expired.append((beach['name'], beach['county'], expiry_str, abs(days_left), expiry_date))
        elif days_left <= WARN_DAYS:
            expiring_soon.append((beach['name'], beach['county'], expiry_str, days_left, expiry_date))
    except ValueError:
        pass

# Save updated beaches.json
with open('beaches.json', 'w') as f:
    json.dump(data, f, indent=2)

# ── Console output ────────────────────────────────────────────────────────────

print(f"✓ beaches.json updated: {count} beaches | {today}")
print()

if expired:
    print(f"{'='*55}")
    print(f"🚨  {len(expired)} EXPIRED PSPO(s) — verify and update NOW:")
    print(f"{'='*55}")
    for name, county, expiry, days_ago, _ in sorted(expired, key=lambda x: x[2]):
        print(f"  • {name} ({county})")
        print(f"    Expired: {expiry} ({days_ago} days ago)")
    print()

if expiring_soon:
    print(f"{'='*55}")
    print(f"⏰  {len(expiring_soon)} PSPO(s) expiring within {WARN_DAYS} days:")
    print(f"{'='*55}")
    for name, county, expiry, days_left, _ in sorted(expiring_soon, key=lambda x: x[3]):
        print(f"  • {name} ({county})")
        print(f"    Expires: {expiry} ({days_left} days)")
    print()

if not expired and not expiring_soon:
    print(f"✓ All PSPOs current — nothing expiring within {WARN_DAYS} days")

# PSPO expiry summary
print()
years = Counter()
for beach in data['beaches']:
    exp = beach.get('pspo_expires')
    if exp:
        years[exp[:4]] += 1
print("PSPO expiry summary:")
for year, n in sorted(years.items()):
    marker = " ← CHECK NOW" if year <= str(today.year) else ""
    print(f"  {year}: {n} beaches{marker}")

# ── ICS generation ────────────────────────────────────────────────────────────

alerts = expired + expiring_soon

if alerts:
    # Group by expiry date to avoid duplicate calendar events
    by_date = {}
    for name, county, expiry_str, _, expiry_date in alerts:
        if expiry_date not in by_date:
            by_date[expiry_date] = []
        by_date[expiry_date].append(f"{name} ({county})")

    ics_lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//MeanWeather Beach Data//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
    ]

    for expiry_date, beaches in sorted(by_date.items()):
        # Remind 2 weeks before expiry (or today if already expired)
        remind_date = max(today, expiry_date - timedelta(days=14))
        date_str = remind_date.strftime('%Y%m%d')
        expiry_str = expiry_date.strftime('%Y%m%d')
        now_str = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')

        beach_list = '\\n'.join(f"• {b}" for b in beaches)
        summary = f"⚠️ MeanWeather PSPO Check — {len(beaches)} beach(es) due {expiry_date}"
        description = (
            f"The following beach PSPO(s) expire on {expiry_date}:\\n\\n"
            f"{beach_list}\\n\\n"
            f"Action: Visit each council website to verify current restrictions "
            f"and update beaches.json + pspo_expires dates.\\n\\n"
            f"Run: python3 update_beaches.py"
        )

        ics_lines += [
            'BEGIN:VEVENT',
            f'UID:{uuid.uuid4()}@meanweather-beaches',
            f'DTSTAMP:{now_str}',
            f'DTSTART;VALUE=DATE:{date_str}',
            f'DTEND;VALUE=DATE:{date_str}',
            f'SUMMARY:{summary}',
            f'DESCRIPTION:{description}',
            'BEGIN:VALARM',
            'TRIGGER:-PT0S',
            'ACTION:DISPLAY',
            f'DESCRIPTION:{summary}',
            'END:VALARM',
            'END:VEVENT',
        ]

    ics_lines.append('END:VCALENDAR')

    ics_filename = f'pspo_reminders_{today}.ics'
    with open(ics_filename, 'w') as f:
        f.write('\r\n'.join(ics_lines))

    print()
    print(f"📅 Calendar file created: {ics_filename}")
    print(f"   Double-click to import into Apple Calendar")
else:
    print()
    print("📅 No calendar reminders needed — all PSPOs current")

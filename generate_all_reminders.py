#!/usr/bin/env python3
# generate_all_reminders.py
# Run once to generate Apple Calendar reminders for ALL future PSPO expiry dates.
# Double-click the output .ics file to import into Apple Calendar.
# You never need to remember to check — Calendar will remind you.

import json
from datetime import date, datetime, timedelta
from collections import Counter
import uuid

with open('beaches.json') as f:
    data = json.load(f)

today = date.today()

# Group all future expiry dates
by_date = {}
expired = []

for beach in data['beaches']:
    expiry_str = beach.get('pspo_expires')
    if not expiry_str:
        continue
    try:
        expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()
        if expiry_date < today:
            expired.append((beach['name'], beach['county'], expiry_str))
        else:
            if expiry_date not in by_date:
                by_date[expiry_date] = []
            by_date[expiry_date].append(f"{beach['name']} ({beach['county']})")
    except ValueError:
        pass

# Report
print(f"Found {len(by_date)} future PSPO expiry dates")
print(f"Generating calendar reminders for all of them...\n")

if expired:
    print(f"⚠️  {len(expired)} already expired — fix these in beaches.json:")
    for name, county, expiry in expired:
        print(f"   • {name} ({county}) — expired {expiry}")
    print()

# Build ICS
ics_lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//MeanWeather Beach Data//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
]

for expiry_date, beaches in sorted(by_date.items()):
    # Two events per expiry:
    # 1. 3 months before — early warning
    # 2. 2 weeks before — final reminder

    beach_list = '\\n'.join(f"• {b}" for b in beaches)
    now_str = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    expiry_fmt = expiry_date.strftime('%-d %B %Y')

    for weeks_before, label in [(12, '3-month warning'), (2, 'Final reminder')]:
        remind_date = expiry_date - timedelta(weeks=weeks_before)
        if remind_date < today:
            remind_date = today  # don't create past events
        date_str = remind_date.strftime('%Y%m%d')

        summary = f"🏖 PSPO {label}: {len(beaches)} beach(es) expire {expiry_fmt}"
        description = (
            f"PSPO expiry {label} — expires {expiry_fmt}\\n\\n"
            f"Beaches to verify:\\n{beach_list}\\n\\n"
            f"Action:\\n"
            f"1. Visit each council website\\n"
            f"2. Confirm restrictions unchanged or update beaches.json\\n"
            f"3. Update pspo_expires date\\n"
            f"4. Run: python3 update_beaches.py && git push"
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

    print(f"  ✓ {expiry_fmt} — {len(beaches)} beaches — 2 reminders created")

ics_lines.append('END:VCALENDAR')

filename = f'pspo_all_reminders_{today}.ics'
with open(filename, 'w') as f:
    f.write('\r\n'.join(ics_lines))

total_events = len(by_date) * 2
print(f"\n📅 Created: {filename}")
print(f"   {total_events} calendar events across {len(by_date)} expiry dates")
print(f"   Double-click to import all into Apple Calendar")

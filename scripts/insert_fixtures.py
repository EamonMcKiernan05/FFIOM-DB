
#!/usr/bin/env python3
import sqlite3
import json
from datetime import datetime
from collections import defaultdict

FFIOM_DB = "data/fantasy_iom.db"
SEASON = "2025-26"

# All Premier League fixtures scraped from the 2 FullTime pages
FIXTURES = [
"2025-08-30|13:45|St Marys|DHSOB|5|1",
"2025-08-30|14:30|Ayre United|Foxdale|7|1",
"2025-08-30|14:30|Corinthians|Union Mills|6|1",
"2025-08-30|14:30|Ramsey|Peel|4|7",
"2025-08-30|14:30|Rushen United|Braddan|2|1",
"2025-08-30|14:30|St Johns United|Laxey|1|2",
"2025-09-02|18:15|Braddan|Corinthians|3|8",
"2025-09-02|18:15|DHSOB|Ramsey|0|2",
"2025-09-02|18:15|Foxdale|Rushen United|1|4",
"2025-09-02|18:15|Laxey|St Marys|3|2",
"2025-09-02|18:15|Onchan|St Johns United|2|2",
"2025-09-02|18:15|Peel|Ayre United|3|3",
"2025-09-06|13:45|St Marys|Onchan|2|3",
"2025-09-06|14:30|Ayre United|DHSOB|4|2",
"2025-09-06|14:30|Corinthians|Foxdale|10|1",
"2025-09-06|14:30|Ramsey|Laxey|1|3",
"2025-09-06|14:30|Rushen United|Peel|3|2",
"2025-09-06|14:30|Union Mills|Braddan|3|3",
"2025-09-13|14:30|DHSOB|Rushen United|0|2",
"2025-09-13|14:30|Foxdale|Union Mills|1|5",
"2025-09-13|14:30|Laxey|Ayre United|2|1",
"2025-09-13|14:30|Onchan|Ramsey|3|1",
"2025-09-13|14:30|Peel|Corinthians|1|1",
"2025-09-13|14:30|St Johns United|St Marys|3|2",
"2025-09-20|14:30|Ayre United|Onchan|2|4",
"2025-09-20|14:30|Braddan|Foxdale|6|1",
"2025-09-20|14:30|Corinthians|DHSOB|5|3",
"2025-09-20|14:30|Ramsey|St Johns United|4|2",
"2025-09-20|14:30|Rushen United|Laxey|0|0",
"2025-09-27|13:45|St Marys|Ramsey|1|2",
"2025-09-27|14:30|DHSOB|Union Mills|2|7",
"2025-09-27|14:30|Laxey|Corinthians|0|0",
"2025-09-27|14:30|Onchan|Rushen United|3|1",
"2025-09-27|14:30|Peel|Braddan|10|2",
"2025-09-27|14:30|St Johns United|Ayre United|2|2",
"2025-10-04|14:30|Ayre United|St Marys|0|4",
"2025-10-04|14:30|Braddan|DHSOB|3|3",
"2025-10-04|14:30|Corinthians|Onchan|3|1",
"2025-10-11|13:45|St Marys|Rushen United|2|1",
"2025-10-11|14:30|DHSOB|Foxdale|3|1",
"2025-10-11|14:30|Laxey|Braddan|7|1",
"2025-10-11|14:30|Onchan|Union Mills|5|1",
"2025-10-11|14:30|Ramsey|Ayre United|2|4",
"2025-10-11|14:30|St Johns United|Corinthians|0|0",
"2025-10-18|14:30|Braddan|Onchan|3|4",
"2025-10-18|14:30|Corinthians|St Marys|1|0",
"2025-10-18|14:30|Foxdale|Laxey|2|9",
"2025-10-18|14:30|Peel|DHSOB|7|1",
"2025-10-18|14:30|Rushen United|Ramsey|2|0",
"2025-10-18|14:30|Union Mills|St Johns United|2|4",
"2025-10-25|13:45|St Marys|Union Mills|6|2",
"2025-10-25|14:30|Ayre United|Rushen United|2|3",
"2025-10-25|14:30|Laxey|Peel|4|5",
"2025-10-25|14:30|Onchan|Foxdale|2|2",
"2025-10-25|14:30|St Johns United|Braddan|6|1",
"2025-11-01|14:00|Braddan|St Marys|2|5",
"2025-11-01|14:00|Corinthians|Ayre United|5|1",
"2025-11-01|14:00|Peel|Onchan|2|0",
"2025-11-01|14:00|Union Mills|Ramsey|4|4",
"2025-11-08|13:45|St Marys|Foxdale|8|0",
"2025-11-08|14:00|Ayre United|Union Mills|2|1",
"2025-11-08|14:00|Onchan|DHSOB|3|3",
"2025-11-08|14:00|Ramsey|Braddan|3|3",
"2025-11-08|14:00|Rushen United|Corinthians|0|7",
"2025-11-08|14:00|St Johns United|Peel|0|3",
"2025-11-15|14:00|Braddan|Ayre United|4|4",
"2025-11-15|14:00|Peel|St Marys|2|1",
"2025-11-15|14:00|Union Mills|Rushen United|1|1",
"2025-11-22|14:00|DHSOB|St Marys|1|2",
"2025-11-22|14:00|Laxey|Onchan|4|4",
"2025-11-22|14:00|Rushen United|St Johns United|1|2",
"2025-11-22|14:00|Union Mills|Corinthians|0|8",
"2025-11-29|14:00|Ayre United|Peel|2|4",
"2025-11-29|14:00|Corinthians|Braddan|4|1",
"2025-11-29|14:00|Union Mills|Laxey|0|1",
"2025-12-13|13:45|St Marys|St Johns United|2|1",
"2025-12-13|14:00|Ayre United|Laxey|2|2",
"2025-12-13|14:00|Corinthians|Peel|0|5",
"2025-12-13|14:00|Ramsey|Onchan|2|0",
"2025-12-13|14:00|Rushen United|DHSOB|1|0",
"2025-12-13|14:00|Union Mills|Foxdale|5|4",
"2026-01-03|13:45|St Marys|Laxey|2|1",
"2026-01-10|14:00|DHSOB|Corinthians|1|3",
"2026-01-10|14:00|Foxdale|Braddan|0|2",
"2026-01-10|14:00|Onchan|Ayre United|6|1",
"2026-01-10|14:00|Peel|Union Mills|2|1",
"2026-01-10|14:00|St Johns United|Ramsey|5|0",
"2026-01-17|14:00|Ayre United|St Johns United|0|3",
"2026-01-17|14:00|Braddan|Peel|1|4",
"2026-01-17|14:00|Corinthians|Laxey|3|2",
"2026-01-17|14:00|Rushen United|Onchan|0|4",
"2026-01-17|14:00|Union Mills|DHSOB|3|2",
"2026-01-24|13:45|St Marys|Ayre United|5|2",
"2026-01-24|14:00|DHSOB|Braddan|1|2",
"2026-01-24|14:00|Laxey|Union Mills|0|3",
"2026-01-24|14:00|Onchan|Corinthians|3|6",
"2026-01-24|14:00|Peel|Foxdale|2|0",
"2026-01-31|14:00|Braddan|Rushen United|0|3",
"2026-02-21|13:45|St Marys|Braddan|7|2",
"2026-02-28|14:30|Corinthians|Ramsey|4|0",
"2026-02-28|14:30|Rushen United|Ayre United|1|3",
"2026-03-07|14:30|Ayre United|Ramsey|2|3",
"2026-03-07|14:30|Laxey|St Johns United|3|2",
"2026-03-07|14:30|Rushen United|Foxdale|5|4",
"2026-03-14|14:30|Ayre United|Corinthians|1|1",
"2026-03-14|14:30|Laxey|DHSOB|4|1",
"2026-03-14|14:30|Onchan|Peel|1|12",
"2026-03-14|14:30|Ramsey|Union Mills|4|1",
"2026-03-14|14:30|St Johns United|Foxdale|3|3",
"2026-03-17|19:00|St Johns United|Rushen United|3|1",
"2026-03-21|14:30|Braddan|Union Mills|3|7",
"2026-03-21|14:30|DHSOB|St Johns United|0|3",
"2026-03-21|14:30|Foxdale|Ayre United|1|1",
"2026-03-21|14:30|Laxey|Ramsey|1|2",
"2026-03-28|14:30|Braddan|Ramsey|2|2",
"2026-03-28|14:30|DHSOB|Onchan|2|6",
"2026-03-28|14:30|Foxdale|Corinthians|1|14",
"2026-03-28|14:30|Peel|St Johns United|6|1",
"2026-03-28|14:30|Union Mills|Ayre United|4|0",
"2026-03-31|19:00|St Johns United|Union Mills|4|0",
"2026-04-07|18:00|Corinthians|St Johns United|5|0",
"2026-04-07|18:00|DHSOB|Laxey|1|2",
"2026-04-07|18:00|Foxdale|Peel|1|8",
"2026-04-07|18:00|Onchan|St Marys|2|1",
"2026-04-11|13:45|St Marys|Peel|3|5",
"2026-04-11|14:30|Ayre United|Braddan|1|4",
"2026-04-11|14:30|Onchan|Laxey|0|1",
"2026-04-11|14:30|Ramsey|Foxdale|4|2",
"2026-04-11|14:30|Rushen United|Union Mills|0|2",
"2026-04-11|14:30|St Johns United|DHSOB|7|3",
"2026-04-14|18:15|Laxey|Rushen United|2|2",
"2026-04-14|18:15|Peel|Ramsey|6|1",
"2026-04-14|18:15|St Marys|Corinthians|3|3",
"2026-04-14|18:15|Union Mills|Onchan|4|4",
"2026-04-18|14:30|DHSOB|Ayre United|4|5",
"2026-04-21|18:30|Laxey|Foxdale|4|2",
"2026-04-21|18:30|Onchan|Braddan|2|2",
"2026-04-21|18:30|Peel|Rushen United|7|0",
"2026-04-21|18:30|Ramsey|DHSOB|2|0",
"2026-04-21|18:30|Union Mills|St Marys|2|5",
"2026-04-25|14:30|Foxdale|Ramsey|5|3",
"2026-04-28|18:30|Braddan|Laxey|1|10",
"2026-04-28|18:30|Corinthians|Rushen United|5|0",
"2026-04-28|18:30|Foxdale|DHSOB|7|4",
"2026-04-28|18:30|Ramsey|St Marys|2|1",
"2026-04-28|18:30|Union Mills|Peel|2|5",
"2026-04-28|19:00|St Johns United|Onchan|4|1",
"2026-05-02|14:30|Foxdale|St Johns United|3|4",
"2026-05-05|18:30|Braddan|St Johns United|6|4",
"2026-05-05|18:30|Foxdale|Onchan|4|5",
"2026-05-05|18:30|Ramsey|Corinthians|2|3",
]

print(f"Loaded {len(FIXTURES)} fixtures")

# Parse fixtures
fixtures = []
for line in FIXTURES:
    parts = line.split("|")
    fixtures.append({
        "date": parts[0],
        "time": parts[1],
        "home": parts[2],
        "away": parts[3],
        "hs": int(parts[4]),
        "as": int(parts[5]),
    })

# Sort by date
fixtures.sort(key=lambda x: (x["date"], x["time"]))

# Group by date for gameweek consolidation
weekly = defaultdict(list)
for fx in fixtures:
    weekly[fx["date"]].append(fx)

sorted_dates = sorted(weekly.keys())
print(f"Unique dates: {len(sorted_dates)}")

# Build consolidated gameweeks
# Rules: if a GW has 3 or fewer games, merge with previous (unless 9+ games, then merge with next)
raw_gws = [{"date": d, "fixtures": weekly[d]} for d in sorted_dates]

consolidated = []
for gw in raw_gws:
    consolidated.append(gw)

# Merge small GWs into previous
i = 0
while i < len(consolidated):
    if len(consolidated[i]["fixtures"]) <= 3 and len(consolidated[i]["fixtures"]) > 0 and i > 0:
        # Check if previous GW would exceed 9
        if len(consolidated[i-1]["fixtures"]) + len(consolidated[i]["fixtures"]) <= 9:
            consolidated[i-1]["fixtures"].extend(consolidated[i]["fixtures"])
            consolidated.pop(i)
        else:
            # Try merging with next
            if i + 1 < len(consolidated):
                consolidated[i+1]["fixtures"] = consolidated[i]["fixtures"] + consolidated[i+1]["fixtures"]
                consolidated.pop(i)
            else:
                i += 1
    else:
        i += 1

print(f"Consolidated gameweeks: {len(consolidated)}")
for i, gw in enumerate(consolidated):
    dates = sorted(set(f["date"] for f in gw["fixtures"]))
    print(f"  GW{i+1}: {len(gw['fixtures'])} fixtures, dates: {dates}")

# Insert into DB
conn = sqlite3.connect(FFIOM_DB)
cursor = conn.cursor()

# Clear existing
cursor.execute("DELETE FROM fixtures")
cursor.execute("DELETE FROM gameweeks")
cursor.execute("DELETE FROM historical_stats")

# Insert gameweeks
for i, gw in enumerate(consolidated, 1):
    dates = sorted(set(f["date"] for f in gw["fixtures"]))
    cursor.execute(
        "INSERT INTO gameweeks (number, season, start_date, end_date, closed, scored) VALUES (?, ?, ?, ?, 1, 1)",
        (i, SEASON, dates[0], dates[-1]),
    )

# Insert fixtures
for i, gw in enumerate(consolidated, 1):
    for fx in gw["fixtures"]:
        cursor.execute(
            "INSERT INTO fixtures (gameweek_id, fixture_date, home_team_name, away_team_name, home_score, away_score, played) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (i, fx["date"], fx["home"], fx["away"], fx["hs"], fx["as"]),
        )

conn.commit()
print(f"Inserted {len(consolidated)} gameweeks and {len(fixtures)} fixtures")

# Verify
cursor.execute("SELECT COUNT(*) FROM gameweeks")
print(f"Gameweeks in DB: {cursor.fetchone()[0]}")
cursor.execute("SELECT COUNT(*) FROM fixtures")
print(f"Fixtures in DB: {cursor.fetchone()[0]}")
cursor.execute("SELECT number, start_date, end_date FROM gameweeks")
for r in cursor.fetchall():
    print(f"  GW{r[0]}: {r[1]} to {r[2]}")

conn.close()
print("Done!")

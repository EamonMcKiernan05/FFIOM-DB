#!/usr/bin/env python3
"""Recalculate gameweek deadlines based on earliest fixture in each GW.

Deadline is set to 2 hours before the first kick-off in that gameweek.
"""
import os, sys

GAME_ROOT = "/home/eamon/Fantasy-Football-Isle-of-Man"
sys.path.insert(0, GAME_ROOT)
os.environ["DATABASE_URL"] = "sqlite:///./data/fantasy_iom.db"
os.chdir(GAME_ROOT)

from app.database import SessionLocal
from app.models import Gameweek, Fixture
from datetime import datetime, timedelta

db = SessionLocal()

print("=== Recalculating Gameweek Deadlines ===")
print("Deadline: 2 hours before first kick-off in each gameweek\n")

gws = db.query(Gameweek).filter(Gameweek.season == "2025-26").order_by(Gameweek.number).all()

for gw in gws:
    fixtures = db.query(Fixture).filter(
        Fixture.gameweek_id == gw.id,
        Fixture.date != None
    ).order_by(Fixture.date.asc()).all()

    if fixtures:
        first_kickoff = min(f.date for f in fixtures if f.date)
        new_deadline = first_kickoff - timedelta(hours=2)
    else:
        # No fixtures with dates, use start_date at 11:00
        new_deadline = datetime.combine(gw.start_date, datetime.min.time()).replace(hour=11)

    old_deadline = gw.deadline
    gw.deadline = new_deadline

    # Format for display
    old_str = old_deadline.strftime("%Y-%m-%d %H:%M") if old_deadline else "None"
    new_str = new_deadline.strftime("%Y-%m-%d %H:%M")
    first_str = fixtures[0].date.strftime("%Y-%m-%d %H:%M") if fixtures and fixtures[0].date else "None"

    print(f"GW {gw.number:2d}: {old_str} -> {new_str} (first fixture: {first_str}, {len(fixtures)} fixtures)")

db.commit()
print(f"\nUpdated {len(gws)} gameweek deadlines")

# Show all GWs with deadlines
print("\n=== All Deadlines ===")
for gw in gws:
    fixtures = db.query(Fixture).filter(Fixture.gameweek_id == gw.id, Fixture.date != None).order_by(Fixture.date.asc()).all()
    first_str = fixtures[0].date.strftime("%Y-%m-%d %H:%M") if fixtures and fixtures[0].date else "None"
    deadline_str = gw.deadline.strftime("%Y-%m-%d %H:%M") if gw.deadline else "None"
    print(f"  GW {gw.number:2d}: deadline {deadline_str} | first fixture {first_str} | closed={gw.closed} | scored={gw.scored}")

db.close()

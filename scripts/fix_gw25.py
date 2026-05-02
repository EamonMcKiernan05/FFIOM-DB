#!/usr/bin/env python3
"""Fix GW 25 closed status and auto-close any GWs past their deadline."""
import os, sys
from datetime import datetime

sys.path.insert(0, '/home/eamon/Fantasy-Football-Isle-of-Man')
os.environ['DATABASE_URL'] = 'sqlite:///./data/fantasy_iom.db'
os.chdir('/home/eamon/Fantasy-Football-Isle-of-Man')

from app.database import SessionLocal
from app.models import Gameweek

db = SessionLocal()

now = datetime.utcnow()
print(f"Current time: {now}\n")

# Auto-close/open all GWs based on deadline
for gw in db.query(Gameweek).filter(Gameweek.season == "2025-26").order_by(Gameweek.number).all():
    old_closed = gw.closed
    if gw.deadline:
        gw.closed = now >= gw.deadline
        if gw.closed and not gw.scored:
            gw.scored = False
    if old_closed != gw.closed:
        print(f"  GW {gw.number:2d}: closed {old_closed} -> {gw.closed} (deadline: {gw.deadline})")

db.commit()

# Show final state
print("\nFinal state:")
for gw in db.query(Gameweek).filter(Gameweek.season == "2025-26").order_by(Gameweek.number).all():
    status = "CURRENT" if not gw.closed else ("CLOSED" if not gw.scored else "SCORED")
    print(f"  GW {gw.number:2d}: {status:8s} | deadline: {gw.deadline.strftime('%Y-%m-%d %H:%M') if gw.deadline else 'None'}")

db.close()

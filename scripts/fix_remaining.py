#!/usr/bin/env python3
"""Fix remaining players without positions and verify dream teams."""
import os, sys
sys.path.insert(0, '/home/eamon/Fantasy-Football-Isle-of-Man')
os.environ['DATABASE_URL'] = 'sqlite:///./data/fantasy_iom.db'
os.chdir('/home/eamon/Fantasy-Football-Isle-of-Man')

from app.database import SessionLocal
from app.models import Player, DreamTeam, DreamTeamPlayer, Gameweek

db = SessionLocal()

# Assign default MID to players without positions
no_pos = db.query(Player).filter(
    Player.is_active == True,
    Player.position == None
).all()
print(f"Players without position: {len(no_pos)}")
for p in no_pos:
    p.position = "MID"
db.commit()
print("Assigned MID to remaining players")

# Verify final counts
print("\n=== Position counts ===")
for pos in ["GK", "DEF", "MID", "FWD"]:
    count = db.query(Player).filter(
        Player.is_active == True,
        Player.position == pos
    ).count()
    print(f"  {pos}: {count}")

# Verify dream teams
print("\n=== Dream Teams ===")
dt_count = db.query(DreamTeam).count()
dtp_count = db.query(DreamTeamPlayer).count()
print(f"  DreamTeams: {dt_count}")
print(f"  Members: {dtp_count}")

# Show first dream team
dt = db.query(DreamTeam).first()
if dt:
    gw = db.query(Gameweek).get(dt.gameweek_id)
    print(f"\n  First dream team: GW {gw.number if gw else '?'} ({dt.season})")
    print(f"  Total points: {dt.total_points}")
    members = db.query(DreamTeamPlayer).filter(
        DreamTeamPlayer.dream_team_id == dt.id
    ).order_by(DreamTeamPlayer.formation_position).all()
    for m in members[:5]:
        player = m.player
        if player:
            print(f"    {m.formation_position}. {player.name:25s} {player.team.name:20s} {player.position:3s} pts:{m.points}")
    if len(members) > 5:
        print(f"    ... and {len(members) - 5} more")

# Check in_dreamteam flag
dt_flagged = db.query(Player).filter(Player.in_dreamteam == True).count()
print(f"\n  Players with in_dreamteam=True: {dt_flagged}")

db.close()
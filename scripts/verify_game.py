#!/usr/bin/env python3
"""Final verification of game state after FFIOM-DB sync."""
import os, sys
sys.path.insert(0, '/home/eamon/Fantasy-Football-Isle-of-Man')
os.environ['DATABASE_URL'] = 'sqlite:///./data/fantasy_iom.db'
os.chdir('/home/eamon/Fantasy-Football-Isle-of-Man')

from app.database import SessionLocal
from app.models import Player, Team, Gameweek, Fixture, FantasyTeam, SquadPlayer, DreamTeam, DreamTeamPlayer, PlayerGameweekPoints

db = SessionLocal()

print("=== Final Game State ===")
print(f"  Players:     {db.query(Player).filter(Player.is_active == True).count()}")
print(f"  Teams:       {db.query(Team).count()}")
print(f"  Gameweeks:   {db.query(Gameweek).count()}")
print(f"  Fixtures:    {db.query(Fixture).count()}")

# Position breakdown
print("\n=== Positions ===")
for pos in ["GK", "DEF", "MID", "FWD"]:
    count = db.query(Player).filter(Player.is_active == True, Player.position == pos).count()
    print(f"  {pos}: {count}")

# Players per team
print("\n=== Players per Team ===")
for team in db.query(Team).all():
    count = db.query(Player).filter(Player.team_id == team.id, Player.is_active == True).count()
    print(f"  {team.name:25s} {count:3d}")

# Fantasy teams
print("\n=== Fantasy Teams ===")
for ft in db.query(FantasyTeam).all():
    squad = db.query(SquadPlayer).filter(SquadPlayer.fantasy_team_id == ft.id).all()
    print(f"  {ft.name}: {len(squad)} squad players")
    for sp in squad[:3]:
        player = sp.player
        if player:
            print(f"    {sp.position_slot}. {player.name:25s} {player.position:3s} {player.team.name}")
    if len(squad) > 3:
        print(f"    ... and {len(squad) - 3} more")

# Dream teams
print("\n=== Dream Teams ===")
dt_count = db.query(DreamTeam).count()
dtp_count = db.query(DreamTeamPlayer).count()
print(f"  DreamTeams: {dt_count}")
print(f"  Members:    {dtp_count}")

# Gameweek points
pgw_count = db.query(PlayerGameweekPoints).count()
print(f"  GW Points:  {pgw_count}")

# Top scorers
print("\n=== Top Scorers ===")
top = db.query(Player).filter(Player.is_active == True).order_by(Player.goals.desc()).limit(5).all()
for p in top:
    print(f"  {p.name:25s} {p.team.name:20s} {p.position:3s} G:{p.goals:2d} Apps:{p.apps:2d}")

db.close()

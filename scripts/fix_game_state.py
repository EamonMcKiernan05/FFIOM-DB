#!/usr/bin/env python3
"""Fix game database state after FFIOM-DB sync.

Problems:
1. Players have position=NULL (FFIOM-DB player_seasons had no position data)
2. PlayerGameweekPoints is empty (no gameweek-level stats)
3. DreamTeams is empty (needs gameweek data)

This script:
1. Assigns positions to players based on stats (same logic as seed script)
2. Generates PlayerGameweekPoints from season stats + fixtures
3. Regenerates DreamTeams for all closed gameweeks
"""

import argparse
import os
import random
import sqlite3
import sys

# Paths
FFIOM_DB_PATH = "/home/eamon/FFIOM-DB/data/fantasy_iom.db"
GAME_ROOT = "/home/eamon/Fantasy-Football-Isle-of-Man"
sys.path.insert(0, GAME_ROOT)
os.environ["DATABASE_URL"] = "sqlite:///./data/fantasy_iom.db"
os.chdir(GAME_ROOT)

from app.database import SessionLocal
from app.models import (
    Player, Team, Gameweek, Fixture,
    PlayerGameweekPoints, DreamTeam, DreamTeamPlayer,
)


def assign_positions(players_for_team):
    """Assign positions to players based on goals and appearances data.

    Same logic as seed-real-data.py assign_positions_to_players.
    """
    # Sort by goals desc, then by appearances desc
    sorted_players = sorted(
        players_for_team,
        key=lambda p: (p.goals, p.apps),
        reverse=True,
    )

    # Goalkeepers: 2 players with 0 goals and highest appearances
    gk_candidates = sorted(
        [p for p in sorted_players if p.goals == 0],
        key=lambda p: p.apps,
        reverse=True,
    )[:2]
    for p in gk_candidates:
        p.position = "GK"

    remaining = [p for p in sorted_players if p not in gk_candidates]

    # Forwards: top 3 scorers
    forwards = remaining[:3]
    for p in forwards:
        p.position = "FWD"

    remaining = [p for p in remaining if p not in forwards]

    # Midfielders: next 5 with most goals/assists
    midfielders = remaining[:5]
    for p in midfielders:
        p.position = "MID"

    remaining = [p for p in remaining if p not in midfielders]

    # Defenders: everyone else
    defenders = remaining[:5]
    for p in defenders:
        p.position = "DEF"

    return gk_candidates + forwards + midfielders + defenders


def fix_positions(game_db):
    """Assign positions to all players without positions."""
    print("=== Assigning positions ===")

    players_no_pos = game_db.query(Player).filter(
        Player.is_active == True,
        Player.position == None,
    ).all()

    print(f"  Players without position: {len(players_no_pos)}")

    # Group by team
    teams = game_db.query(Team).all()
    for team in teams:
        team_players = [
            p for p in players_no_pos if p.team_id == team.id
        ]
        if team_players:
            assign_positions(team_players)
            print(f"  {team.name}: assigned {len(team_players)} players")

    game_db.commit()

    # Summary
    for pos in ["GK", "DEF", "MID", "FWD"]:
        count = game_db.query(Player).filter(
            Player.position == pos, Player.is_active == True
        ).count()
        print(f"    {pos}: {count}")


def distribute_season_stats(game_db):
    """Distribute season stats across gameweeks to create PlayerGameweekPoints.

    We have season totals (goals, assists, etc.) and fixtures.
    We distribute stats across the player's matches proportionally.
    """
    print("\n=== Generating PlayerGameweekPoints ===")

    # Get all closed gameweeks with fixtures
    closed_gws = game_db.query(Gameweek).filter(
        Gameweek.closed == True,
        Gameweek.season == "2025-26",
    ).order_by(Gameweek.number).all()

    print(f"  Closed gameweeks: {len(closed_gws)}")

    # Get all fixtures
    fixtures = game_db.query(Fixture).filter(
        Fixture.gameweek_id.in_([gw.id for gw in closed_gws])
    ).all()
    print(f"  Fixtures: {len(fixtures)}")

    # Get all active players
    active_players = game_db.query(Player).filter(
        Player.is_active == True
    ).all()
    print(f"  Active players: {len(active_players)}")

    random.seed(42)  # Reproducible

    # Group players by team
    players_by_team = {}
    for p in active_players:
        players_by_team.setdefault(p.team_id, []).append(p)

    entries_created = 0
    for gw in closed_gws:
        gw_fixtures = [f for f in fixtures if f.gameweek_id == gw.id]

        for fixture in gw_fixtures:
            # Get players from both teams
            home_players = players_by_team.get(fixture.home_team_id, [])
            away_players = players_by_team.get(fixture.away_team_id, [])

            # Each player has some chance of playing this GW
            for player in home_players + away_players:
                # Calculate probability of playing based on total apps
                if player.apps <= 0:
                    continue

                # Probability of playing this GW = apps / total possible matches
                # Roughly: if player has 20 apps and there are 24 GWs, they played ~83%
                play_prob = min(player.apps / 24.0, 0.9)

                if random.random() > play_prob:
                    continue

                was_home = fixture.home_team_id == player.team_id

                # Distribute stats
                goals_this_gw = 0
                assists_this_gw = 0
                minutes = 0
                bonus = 0

                # Goals: roughly uniform distribution across apps
                goals_per_game = player.goals / max(player.apps, 1)
                if random.random() < goals_per_game:
                    goals_this_gw = 1

                # Assists: roughly uniform
                assists_per_game = player.assists / max(player.apps, 1)
                if random.random() < assists_per_game:
                    assists_this_gw = 1

                # Minutes: ~60-90 for starters, ~0-45 for subs
                if player.position in ["GK", "DEF"]:
                    minutes = random.randint(75, 90)
                elif player.position == "MID":
                    minutes = random.randint(60, 90)
                elif player.position == "FWD":
                    minutes = random.randint(50, 80)
                else:
                    minutes = random.randint(60, 90)

                # Clean sheet for defenders/GKs if team didn't concede
                clean_sheet = False
                if player.position in ["GK", "DEF"]:
                    if was_home and fixture.away_score == 0:
                        clean_sheet = True
                    elif not was_home and fixture.home_score == 0:
                        clean_sheet = True

                # Saves for GKs
                saves = 0
                if player.position == "GK":
                    saves = random.randint(0, 5)

                # Calculate points
                base_points = 0
                if minutes >= 60:
                    base_points += 2
                elif minutes >= 1:
                    base_points += 1

                base_points += goals_this_gw * 4
                base_points += assists_this_gw * 3
                if clean_sheet:
                    if player.position == "GK":
                        base_points += 4
                    else:
                        base_points += 4
                if player.position == "GK":
                    if saves >= 3:
                        base_points += 1
                    if saves >= 4:
                        base_points += 2
                    if saves >= 7:
                        base_points += 3

                # Only create entry if player has any involvement
                if minutes > 0 or goals_this_gw > 0 or assists_this_gw > 0 or clean_sheet:
                    pgp = PlayerGameweekPoints(
                        player_id=player.id,
                        gameweek_id=gw.id,
                        opponent_team=fixture.away_team_name if was_home else fixture.home_team_name,
                        was_home=was_home,
                        minutes_played=minutes,
                        did_play=minutes > 0,
                        goals_scored=goals_this_gw,
                        assists=assists_this_gw,
                        clean_sheet=clean_sheet,
                        goals_conceded=(fixture.home_score if was_home else fixture.away_score),
                        saves=saves,
                        base_points=base_points,
                        total_points=max(base_points, 0),
                    )
                    game_db.add(pgp)
                    entries_created += 1

    game_db.commit()
    print(f"  Created {entries_created} PlayerGameweekPoints entries")


def regenerate_dream_teams(game_db):
    """Regenerate DreamTeams for all closed gameweeks."""
    print("\n=== Regenerating DreamTeams ===")

    closed_gws = game_db.query(Gameweek).filter(
        Gameweek.closed == True,
        Gameweek.season == "2025-26",
    ).order_by(Gameweek.number).all()

    for gw in closed_gws:
        # Check if dream team already exists
        existing = game_db.query(DreamTeam).filter(
            DreamTeam.gameweek_id == gw.id
        ).first()
        if existing:
            print(f"  GW {gw.number}: dream team already exists, skipping")
            continue

        # Get all gameweek points for this GW
        pgw = game_db.query(PlayerGameweekPoints).filter(
            PlayerGameweekPoints.gameweek_id == gw.id
        ).all()

        if not pgw:
            print(f"  GW {gw.number}: no gameweek points, skipping")
            continue

        # Sort by total points desc, take top 11
        sorted_pgw = sorted(pgw, key=lambda p: p.total_points, reverse=True)[:11]

        dream_team = DreamTeam(
            gameweek_id=gw.id,
            season="2025-26",
            total_points=sum(p.total_points for p in sorted_pgw),
        )
        game_db.add(dream_team)
        game_db.flush()

        for i, entry in enumerate(sorted_pgw, 1):
            player = game_db.query(Player).get(entry.player_id)
            if not player:
                continue

            dtp = DreamTeamPlayer(
                dream_team_id=dream_team.id,
                player_id=entry.player_id,
                position=player.position,
                points=entry.total_points,
                formation_position=i,
            )
            game_db.add(dtp)

            # Mark player as in dream team
            player.in_dreamteam = True

    game_db.commit()
    print(f"  Processed {len(closed_gws)} gameweeks")


def main():
    parser = argparse.ArgumentParser(description="Fix game state after FFIOM-DB sync")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--step", default="all",
        help="Which step to run: all, positions, gw_points, dream_teams")
    args = parser.parse_args()

    game_db = SessionLocal()

    try:
        if args.step in ["all", "positions"]:
            fix_positions(game_db)

        if args.step in ["all", "gw_points"]:
            distribute_season_stats(game_db)

        if args.step in ["all", "dream_teams"]:
            regenerate_dream_teams(game_db)

        # Summary
        print("\n=== Final State ===")
        print(f"  Players:     {game_db.query(Player).filter(Player.is_active == True).count()}")
        print(f"  With pos:    {game_db.query(Player).filter(Player.is_active == True, Player.position != None).count()}")
        print(f"  GW Points:   {game_db.query(PlayerGameweekPoints).count()}")
        print(f"  DreamTeams:  {game_db.query(DreamTeam).count()}")
        print(f"  DT Members:  {game_db.query(DreamTeamPlayer).count()}")

    finally:
        game_db.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Recalculate PlayerGameweekPoints and DreamTeams after GW consolidation.

Handles multi-fixture teams: if a team plays twice in a GW, player points
from BOTH fixtures are summed. Captain/triple captain multipliers apply
to the combined total.
"""
import os, random, sys

GAME_ROOT = "/home/eamon/Fantasy-Football-Isle-of-Man"
sys.path.insert(0, GAME_ROOT)
os.environ["DATABASE_URL"] = "sqlite:///./data/fantasy_iom.db"
os.chdir(GAME_ROOT)

from app.database import SessionLocal
from app.models import (
    Gameweek, Fixture, Player,
    PlayerGameweekPoints, DreamTeam, DreamTeamPlayer,
)


def recalculate_gw_points():
    """Recalculate PlayerGameweekPoints for all gameweeks."""
    print("=== Recalculating PlayerGameweekPoints ===")

    game_db = SessionLocal()
    try:
        old_count = game_db.query(PlayerGameweekPoints).count()
        game_db.query(PlayerGameweekPoints).delete()
        game_db.commit()
        print(f"  Cleared {old_count} existing entries")

        closed_gws = game_db.query(Gameweek).filter(
            Gameweek.closed == True, Gameweek.season == "2025-26"
        ).order_by(Gameweek.number).all()

        players_by_team = {}
        for p in game_db.query(Player).filter(Player.is_active == True).all():
            players_by_team.setdefault(p.team_id, []).append(p)

        random.seed(42)
        entries_created = 0

        for gw in closed_gws:
            gw_fixtures = game_db.query(Fixture).filter(Fixture.gameweek_id == gw.id).all()

            team_fixture_counts = {}
            for f in gw_fixtures:
                for tid in [f.home_team_id, f.away_team_id]:
                    if tid:
                        team_fixture_counts[tid] = team_fixture_counts.get(tid, 0) + 1
            multi_teams = {t: c for t, c in team_fixture_counts.items() if c > 1}

            # Accumulate per-player stats for this GW
            gw_player_stats = {}

            for fixture in gw_fixtures:
                for player in (players_by_team.get(fixture.home_team_id, []) +
                               players_by_team.get(fixture.away_team_id, [])):
                    if player.apps <= 0:
                        continue
                    if random.random() > min(player.apps / 24.0, 0.9):
                        continue

                    was_home = fixture.home_team_id == player.team_id
                    goals_fx = 1 if random.random() < (player.goals / max(player.apps, 1)) else 0
                    assists_fx = 1 if random.random() < (player.assists / max(player.apps, 1)) else 0

                    minutes = random.randint(
                        75 if player.position in ["GK", "DEF"] else
                        60 if player.position == "MID" else
                        50,
                        90 if player.position in ["GK", "DEF"] else
                        90 if player.position == "MID" else 80
                    )

                    clean_sheet = False
                    if player.position in ["GK", "DEF"]:
                        if was_home and (fixture.away_score or 0) == 0:
                            clean_sheet = True
                        elif not was_home and (fixture.home_score or 0) == 0:
                            clean_sheet = True

                    saves = random.randint(0, 5) if player.position == "GK" else 0
                    yellow_card = random.random() < 0.03 if player.position != "GK" else False
                    red_card = random.random() < 0.005
                    goals_conceded = (fixture.home_score or 0) if was_home else (fixture.away_score or 0)

                    pts = 0
                    if minutes >= 60: pts += 2
                    elif minutes >= 1: pts += 1
                    pts += goals_fx * 4 + assists_fx * 3
                    if clean_sheet: pts += 4
                    if player.position == "GK":
                        if saves >= 7: pts += 3
                        elif saves >= 4: pts += 2
                        elif saves >= 3: pts += 1
                    if yellow_card: pts -= 1
                    if red_card: pts -= 3

                    pid = player.id
                    if pid not in gw_player_stats:
                        gw_player_stats[pid] = {
                            'opponent_team': fixture.away_team_name if was_home else fixture.home_team_name,
                            'was_home': was_home,
                            'minutes_played': 0, 'goals_scored': 0, 'assists': 0,
                            'clean_sheet': True, 'goals_conceded': 0, 'saves': 0,
                            'yellow_card': False, 'red_card': False,
                            'base_points': 0, 'total_points': 0,
                        }
                    s = gw_player_stats[pid]
                    s['minutes_played'] += minutes
                    s['goals_scored'] += goals_fx
                    s['assists'] += assists_fx
                    s['clean_sheet'] = s['clean_sheet'] and clean_sheet
                    s['goals_conceded'] += goals_conceded
                    s['saves'] += saves
                    s['yellow_card'] = s['yellow_card'] or yellow_card
                    s['red_card'] = s['red_card'] or red_card
                    s['base_points'] += pts
                    s['total_points'] += max(pts, 0)
                    if s['opponent_team'] and (fixture.away_team_name if was_home else fixture.home_team_name) not in s['opponent_team']:
                        s['opponent_team'] += " / " + (fixture.away_team_name if was_home else fixture.home_team_name)

            for pid, s in gw_player_stats.items():
                if s['minutes_played'] > 0 or s['goals_scored'] > 0 or s['assists'] > 0:
                    game_db.add(PlayerGameweekPoints(
                        player_id=pid, gameweek_id=gw.id,
                        opponent_team=s['opponent_team'], was_home=s['was_home'],
                        minutes_played=s['minutes_played'], did_play=True,
                        goals_scored=s['goals_scored'], assists=s['assists'],
                        clean_sheet=s['clean_sheet'], goals_conceded=s['goals_conceded'],
                        saves=s['saves'], yellow_card=s['yellow_card'], red_card=s['red_card'],
                        base_points=s['base_points'], total_points=s['total_points'],
                    ))
                    entries_created += 1

            if multi_teams:
                print(f"  GW {gw.number}: {len(gw_fixtures)} fx, {len(multi_teams)} multi-fx teams, {len(gw_player_stats)} players")
            else:
                print(f"  GW {gw.number}: {len(gw_fixtures)} fx, {len(gw_player_stats)} players")

        game_db.commit()
        print(f"  Created {entries_created} PlayerGameweekPoints entries")
    finally:
        game_db.close()


def regenerate_dream_teams():
    """Regenerate DreamTeams for all closed gameweeks."""
    print("\n=== Regenerating DreamTeams ===")

    game_db = SessionLocal()
    try:
        game_db.query(DreamTeamPlayer).delete()
        game_db.query(DreamTeam).delete()
        game_db.commit()
        game_db.query(Player).update({Player.in_dreamteam: False}, synchronize_session=False)
        game_db.commit()

        closed_gws = game_db.query(Gameweek).filter(
            Gameweek.closed == True, Gameweek.season == "2025-26"
        ).order_by(Gameweek.number).all()

        for gw in closed_gws:
            pgw = game_db.query(PlayerGameweekPoints).filter(
                PlayerGameweekPoints.gameweek_id == gw.id
            ).all()
            if not pgw:
                continue

            sorted_pgw = sorted(pgw, key=lambda p: p.total_points, reverse=True)[:11]
            dream_team = DreamTeam(
                gameweek_id=gw.id, season="2025-26",
                total_points=sum(p.total_points for p in sorted_pgw),
            )
            game_db.add(dream_team)
            game_db.flush()

            for i, entry in enumerate(sorted_pgw, 1):
                player = game_db.query(Player).get(entry.player_id)
                if not player:
                    continue
                game_db.add(DreamTeamPlayer(
                    dream_team_id=dream_team.id, player_id=entry.player_id,
                    position=player.position, points=entry.total_points,
                    formation_position=i,
                ))
                player.in_dreamteam = True

        game_db.commit()
        print(f"  Created {game_db.query(DreamTeam).count()} DreamTeams with {game_db.query(DreamTeamPlayer).count()} members")
    finally:
        game_db.close()


if __name__ == "__main__":
    recalculate_gw_points()
    regenerate_dream_teams()

    # Final summary
    import sqlite3
    db_path = "data/fantasy_iom.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    print("\n=== Final State ===")
    for table in ["gameweeks", "fixtures", "player_gameweek_points", "dream_teams", "dream_team_players"]:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table}: {cur.fetchone()[0]}")
    conn.close()

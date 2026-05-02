#!/usr/bin/env python3
"""Consolidate gameweeks with 3 or fewer fixtures.

Strategy:
1. Identify GWs with <= 3 fixtures
2. Merge them into the previous GW (cascade into the same target is OK)
3. Use raw SQL for moves to avoid SQLAlchemy session issues
4. Renumber sequentially
5. Recalculate PlayerGameweekPoints (multi-fixture teams supported)
6. Regenerate DreamTeams
"""

import argparse
import os
import random
import sys

GAME_ROOT = "/home/eamon/Fantasy-Football-Isle-of-Man"
sys.path.insert(0, GAME_ROOT)
os.environ["DATABASE_URL"] = "sqlite:///./data/fantasy_iom.db"
os.chdir(GAME_ROOT)

import sqlite3
from app.database import SessionLocal, engine
from app.models import (
    Gameweek, Fixture, Player,
    PlayerGameweekPoints, DreamTeam, DreamTeamPlayer,
)

THRESHOLD = 3  # GWs with <= this many fixtures get merged


def get_db_path():
    """Extract the SQLite file path from the DATABASE_URL."""
    url = os.environ.get("DATABASE_URL", "sqlite:///./data/fantasy_iom.db")
    # Remove sqlite:/// or sqlite:// prefix
    for prefix in ["sqlite:///", "sqlite://"]:
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    return url


def consolidate_gameweeks():
    """Merge GWs with <= THRESHOLD fixtures into adjacent GWs using raw SQL."""

    db_path = get_db_path()
    print(f"Database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=OFF")  # Disable FK for now, we handle it manually
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get all GWs for 2025-26
    cur.execute("""
        SELECT id, number, start_date, end_date, closed, scored
        FROM gameweeks WHERE season = '2025-26'
        ORDER BY number
    """)
    all_gws = [dict(row) for row in cur.fetchall()]

    print(f"\nBefore: {len(all_gws)} gameweeks")
    for gw in all_gws:
        cur.execute("SELECT COUNT(*) as c FROM fixtures WHERE gameweek_id = ?", (gw['id'],))
        count = cur.fetchone()['c']
        print(f"  GW {gw['number']:2d} (id={gw['id']}, {gw['start_date']}): {count:2d} fx")

    # Identify GWs to merge
    gw_ids = [gw['id'] for gw in all_gws]

    # Find GWs with <= THRESHOLD fixtures
    merge_candidates = []
    for gw in all_gws:
        cur.execute("SELECT COUNT(*) as c FROM fixtures WHERE gameweek_id = ?", (gw['id'],))
        count = cur.fetchone()['c']
        if count <= THRESHOLD:
            merge_candidates.append(gw)

    print(f"\nCandidates to merge ({len(merge_candidates)}):")
    for gw in merge_candidates:
        cur.execute("SELECT COUNT(*) as c FROM fixtures WHERE gameweek_id = ?", (gw['id'],))
        print(f"  GW {gw['number']} (id={gw['id']}): {cur.fetchone()['c']} fixtures")

    # Build merge map: source_gw_id -> target_gw_id
    # Merge into the PREVIOUS GW that is NOT itself being merged
    merge_map = {}
    for gw in all_gws:
        idx = gw_ids.index(gw['id'])
        if gw in merge_candidates:
            if idx == 0:
                # First GW - merge into next non-candidate GW
                for next_gw in all_gws[idx + 1:]:
                    if next_gw not in merge_candidates:
                        merge_map[gw['id']] = next_gw['id']
                        break
            else:
                # Merge into previous non-candidate GW
                for prev_gw in reversed(all_gws[:idx]):
                    if prev_gw not in merge_candidates:
                        merge_map[gw['id']] = prev_gw['id']
                        break

    print(f"\nMerge plan:")
    for source_id, target_id in merge_map.items():
        source = next(g for g in all_gws if g['id'] == source_id)
        target = next(g for g in all_gws if g['id'] == target_id)
        print(f"  GW {source['number']} -> GW {target['number']} (id: {source['id']} -> {target['id']})")

    # Execute merges
    for source_id, target_id in merge_map.items():
        source = next(g for g in all_gws if g['id'] == source_id)
        target = next(g for g in all_gws if g['id'] == target_id)

        # Move fixtures
        cur.execute("UPDATE fixtures SET gameweek_id = ? WHERE gameweek_id = ?",
                    (target_id, source_id))
        moved = cur.rowcount
        print(f"  Moved {moved} fixtures from GW {source['number']} to GW {target['number']}")

         # Move PlayerGameweekPoints (handle overlaps: combine stats if player in both GWs)
        # Get players in source GW
        cur.execute("SELECT player_id FROM player_gameweek_points WHERE gameweek_id = ?",
                    (source_id,))
        source_players = [r['player_id'] for r in cur.fetchall()]

        # Get players in target GW
        cur.execute("SELECT player_id, id FROM player_gameweek_points WHERE gameweek_id = ?",
                    (target_id,))
        target_map = {r['player_id']: r['id'] for r in cur.fetchall()}

        # For overlapping players, combine stats
        for pid in source_players:
            if pid in target_map:
                # Player exists in both GWs - combine stats into target, delete source
                target_entry_id = target_map[pid]

                cur.execute("""
                    SELECT minutes_played, goals_scored, assists, goals_conceded, saves,
                           bonus_points, base_points, total_points, yellow_card, red_card,
                           own_goal, penalties_saved, penalties_missed, influence_gw,
                           creativity_gw, threat_gw, bps_score
                    FROM player_gameweek_points WHERE player_id = ? AND gameweek_id = ?
                """, (pid, source_id))
                source_entry = dict(cur.fetchone())

                cur.execute("""
                    UPDATE player_gameweek_points SET
                        minutes_played = minutes_played + ?,
                        goals_scored = goals_scored + ?,
                        assists = assists + ?,
                        goals_conceded = goals_conceded + ?,
                        saves = saves + ?,
                        bonus_points = bonus_points + ?,
                        base_points = base_points + ?,
                        total_points = total_points + ?,
                        yellow_card = MAX(yellow_card, ?),
                        red_card = MAX(red_card, ?),
                        own_goal = MAX(own_goal, ?),
                        penalties_saved = penalties_saved + ?,
                        penalties_missed = penalties_missed + ?,
                        influence_gw = influence_gw + ?,
                        creativity_gw = creativity_gw + ?,
                        threat_gw = threat_gw + ?,
                        bps_score = bps_score + ?
                    WHERE id = ?
                """, (
                    source_entry['minutes_played'] or 0,
                    source_entry['goals_scored'] or 0,
                    source_entry['assists'] or 0,
                    source_entry['goals_conceded'] or 0,
                    source_entry['saves'] or 0,
                    source_entry['bonus_points'] or 0,
                    source_entry['base_points'] or 0,
                    source_entry['total_points'] or 0,
                    source_entry['yellow_card'] or 0,
                    source_entry['red_card'] or 0,
                    source_entry['own_goal'] or 0,
                    source_entry['penalties_saved'] or 0,
                    source_entry['penalties_missed'] or 0,
                    source_entry['influence_gw'] or 0,
                    source_entry['creativity_gw'] or 0,
                    source_entry['threat_gw'] or 0,
                    source_entry['bps_score'] or 0,
                    target_entry_id,
                ))

                # Delete source entry
                cur.execute("DELETE FROM player_gameweek_points WHERE player_id = ? AND gameweek_id = ?",
                            (pid, source_id))

        # Now move remaining source entries (no overlaps)
        cur.execute("UPDATE player_gameweek_points SET gameweek_id = ? WHERE gameweek_id = ?",
                    (target_id, source_id))
        moved_pgw = cur.rowcount
        if moved_pgw:
            print(f"  Moved {moved_pgw} GW point entries")

        # Move GameweekStats
        cur.execute("UPDATE gameweek_stats SET gameweek_id = ? WHERE gameweek_id = ?",
                    (target_id, source_id))

        # Delete DreamTeam for source GW
        cur.execute("SELECT id FROM dream_teams WHERE gameweek_id = ?", (source_id,))
        dt_row = cur.fetchone()
        if dt_row:
            cur.execute("DELETE FROM dream_team_players WHERE dream_team_id = ?", (dt_row['id'],))
            cur.execute("DELETE FROM dream_teams WHERE id = ?", (dt_row['id'],))
            print(f"  Deleted DreamTeam for GW {source['number']}")

        # Move FantasyTeamHistory
        cur.execute("UPDATE fantasy_team_history SET gameweek_id = ? WHERE gameweek_id = ?",
                    (target_id, source_id))

        # Move Transfers
        cur.execute("UPDATE transfers SET gameweek_id = ? WHERE gameweek_id = ?",
                    (target_id, source_id))

        # Move Chips
        cur.execute("UPDATE chips SET gameweek_id = ? WHERE gameweek_id = ?",
                    (target_id, source_id))

        # Move PlayerPriceHistory
        cur.execute("UPDATE player_price_history SET gameweek_id = ? WHERE gameweek_id = ?",
                    (target_id, source_id))

        # Update target to absorb source properties
        if source['closed']:
            cur.execute("UPDATE gameweeks SET closed = 1 WHERE id = ?", (target_id,))
        if source['scored']:
            cur.execute("UPDATE gameweeks SET scored = 1 WHERE id = ?", (target_id,))

        # Delete source GW
        cur.execute("DELETE FROM gameweeks WHERE id = ?", (source_id,))
        print(f"  Deleted GW {source['number']} (id={source_id})")

    conn.commit()

    # Renumber gameweeks sequentially
    cur.execute("""
        SELECT id, number FROM gameweeks WHERE season = '2025-26' ORDER BY start_date, id
    """)
    remaining = cur.fetchall()
    for i, row in enumerate(remaining, 1):
        new_num = i
        if row['number'] != new_num:
            cur.execute("UPDATE gameweeks SET number = ? WHERE id = ?", (new_num, row['id']))
    conn.commit()
    print("\nRenumbered gameweeks.")

    # Verify
    print("\nAfter consolidation:")
    cur.execute("""
        SELECT id, number, start_date, closed, scored
        FROM gameweeks WHERE season = '2025-26' ORDER BY number
    """)
    for row in cur.fetchall():
        cur.execute("SELECT COUNT(*) as c FROM fixtures WHERE gameweek_id = ?", (row['id'],))
        count = cur.fetchone()['c']
        print(f"  GW {row['number']:2d} (id={row['id']}, {row['start_date']}): {count:2d} fx closed={row['closed']} scored={row['scored']}")

    conn.close()


def recalculate_gw_points():
    """Recalculate PlayerGameweekPoints for all gameweeks."""

    print("\n=== Recalculating PlayerGameweekPoints ===")

    game_db = SessionLocal()

    try:
        # Clear existing points
        old_count = game_db.query(PlayerGameweekPoints).count()
        game_db.query(PlayerGameweekPoints).delete()
        game_db.commit()
        print(f"  Cleared {old_count} existing entries")

        closed_gws = game_db.query(Gameweek).filter(
            Gameweek.closed == True,
            Gameweek.season == "2025-26",
        ).order_by(Gameweek.number).all()

        players_by_team = {}
        for p in game_db.query(Player).filter(Player.is_active == True).all():
            players_by_team.setdefault(p.team_id, []).append(p)

        random.seed(42)
        entries_created = 0

        for gw in closed_gws:
            gw_fixtures = game_db.query(Fixture).filter(
                Fixture.gameweek_id == gw.id
            ).all()

            # Check for multi-fixture teams
            team_fixture_counts = {}
            for f in gw_fixtures:
                for tid in [f.home_team_id, f.away_team_id]:
                    if tid:
                        team_fixture_counts[tid] = team_fixture_counts.get(tid, 0) + 1

            multi_teams = {tid: c for tid, c in team_fixture_counts.items() if c > 1}
            if multi_teams:
                print(f"  GW {gw.number}: {len(gw_fixtures)} fixtures, {len(multi_teams)} teams play multiple times")

            # Accumulate stats per player in this GW (handles multi-fixture teams)
            gw_player_stats = {}  # player_id -> accumulated stats dict

            for fixture in gw_fixtures:
                home_players = players_by_team.get(fixture.home_team_id, [])
                away_players = players_by_team.get(fixture.away_team_id, [])

                for player in home_players + away_players:
                    if player.apps <= 0:
                        continue

                    play_prob = min(player.apps / 24.0, 0.9)
                    if random.random() > play_prob:
                        continue

                    was_home = fixture.home_team_id == player.team_id

                    goals_this_fx = 0
                    assists_this_fx = 0
                    minutes = 0
                    saves = 0
                    clean_sheet = False
                    yellow_card = False
                    red_card = False

                    goals_per_game = player.goals / max(player.apps, 1)
                    if random.random() < goals_per_game:
                        goals_this_fx = 1

                    assists_per_game = player.assists / max(player.apps, 1)
                    if random.random() < assists_per_game:
                        assists_this_fx = 1

                    if player.position in ["GK", "DEF"]:
                        minutes = random.randint(75, 90)
                    elif player.position == "MID":
                        minutes = random.randint(60, 90)
                    elif player.position == "FWD":
                        minutes = random.randint(50, 80)
                    else:
                        minutes = random.randint(60, 90)

                    if player.position in ["GK", "DEF"]:
                        if was_home and fixture.away_score == 0:
                            clean_sheet = True
                        elif not was_home and fixture.home_score == 0:
                            clean_sheet = True

                    if player.position == "GK":
                        saves = random.randint(0, 5)

                    if player.position != "GK" and random.random() < 0.03:
                        yellow_card = True
                    if random.random() < 0.005:
                        red_card = True

                    goals_conceded = fixture.home_score if was_home else fixture.away_score

                    base_points = 0
                    if minutes >= 60:
                        base_points += 2
                    elif minutes >= 1:
                        base_points += 1
                    base_points += goals_this_fx * 4
                    base_points += assists_this_fx * 3
                    if clean_sheet:
                        base_points += 4
                    if player.position == "GK":
                        if saves >= 3:
                            base_points += 1
                        if saves >= 4:
                            base_points += 2
                        if saves >= 7:
                            base_points += 3
                    if yellow_card:
                        base_points -= 1
                    if red_card:
                        base_points -= 3

                    # Accumulate into per-player GW stats
                    pid = player.id
                    if pid not in gw_player_stats:
                        gw_player_stats[pid] = {
                            'player': player,
                            'opponent_team': fixture.away_team_name if was_home else fixture.home_team_name,
                            'was_home': was_home,
                            'minutes_played': 0,
                            'goals_scored': 0,
                            'assists': 0,
                            'clean_sheet': True,  # Only true if clean in ALL fixtures
                            'goals_conceded': 0,
                            'saves': 0,
                            'yellow_card': False,
                            'red_card': False,
                            'base_points': 0,
                            'total_points': 0,
                        }

                    s = gw_player_stats[pid]
                    s['minutes_played'] += minutes
                    s['goals_scored'] += goals_this_fx
                    s['assists'] += assists_this_fx
                    s['clean_sheet'] = s['clean_sheet'] and clean_sheet
                    s['goals_conceded'] += goals_conceded
                    s['saves'] += saves
                    s['yellow_card'] = s['yellow_card'] or yellow_card
                    s['red_card'] = s['red_card'] or red_card
                    s['base_points'] += base_points
                    s['total_points'] += max(base_points, 0)

                    # Append opponent if second fixture
                    if s['opponent_team'] and fixture.away_team_name != s['opponent_team'] and fixture.home_team_name != s['opponent_team']:
                        opp = fixture.away_team_name if was_home else fixture.home_team_name
                        s['opponent_team'] = s['opponent_team'] + " / " + opp

            # Now insert one entry per player
            for pid, s in gw_player_stats.items():
                if s['minutes_played'] > 0 or s['goals_scored'] > 0 or s['assists'] > 0:
                    pgp = PlayerGameweekPoints(
                        player_id=pid,
                        gameweek_id=gw.id,
                        opponent_team=s['opponent_team'],
                        was_home=s['was_home'],
                        minutes_played=s['minutes_played'],
                        did_play=s['minutes_played'] > 0,
                        goals_scored=s['goals_scored'],
                        assists=s['assists'],
                        clean_sheet=s['clean_sheet'],
                        goals_conceded=s['goals_conceded'],
                        saves=s['saves'],
                        yellow_card=s['yellow_card'],
                        red_card=s['red_card'],
                        base_points=s['base_points'],
                        total_points=s['total_points'],
                    )
                    game_db.add(pgp)
                    entries_created += 1

            print(f"    GW {gw.number}: {len(gw_player_stats)} players")

        game_db.commit()
        print(f"  Created {entries_created} PlayerGameweekPoints entries")

        # Combine entries for players with multiple fixtures in same GW
        multi_entries = game_db.query(PlayerGameweekPoints).with_entities(
            PlayerGameweekPoints.player_id,
            PlayerGameweekPoints.gameweek_id,
        ).group_by(
            PlayerGameweekPoints.player_id,
            PlayerGameweekPoints.gameweek_id,
        ).having("COUNT(*) > 1").all()

        combined_count = 0
        for player_id, gw_id in multi_entries:
            entries = game_db.query(PlayerGameweekPoints).filter(
                PlayerGameweekPoints.player_id == player_id,
                PlayerGameweekPoints.gameweek_id == gw_id,
            ).all()

            if len(entries) > 1:
                combined = entries[0]
                for entry in entries[1:]:
                    combined.minutes_played += entry.minutes_played
                    combined.goals_scored += entry.goals_scored
                    combined.assists += entry.assists
                    combined.goals_conceded += entry.goals_conceded
                    combined.saves += entry.saves
                    combined.bonus_points += entry.bonus_points
                    combined.base_points += entry.base_points
                    combined.total_points += entry.total_points
                    if combined.opponent_team and entry.opponent_team:
                        combined.opponent_team = combined.opponent_team + " / " + entry.opponent_team
                    combined.yellow_card = combined.yellow_card or entry.yellow_card
                    combined.red_card = combined.red_card or entry.red_card
                    combined.clean_sheet = combined.clean_sheet and entry.clean_sheet
                    game_db.delete(entry)

                game_db.commit()
                player = game_db.query(Player).get(player_id)
                gw = game_db.query(Gameweek).get(gw_id)
                print(f"    Combined: {player.name} GW {gw.number}: {combined.total_points} pts ({combined.goals_scored}G, {combined.assists}A)")
                combined_count += 1

        print(f"  Combined {combined_count} multi-fixture entries")

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
            Gameweek.closed == True,
            Gameweek.season == "2025-26",
        ).order_by(Gameweek.number).all()

        for gw in closed_gws:
            pgw = game_db.query(PlayerGameweekPoints).filter(
                PlayerGameweekPoints.gameweek_id == gw.id
            ).all()

            if not pgw:
                continue

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
                player.in_dreamteam = True

        game_db.commit()
        print(f"  Created {game_db.query(DreamTeam).count()} DreamTeams with {game_db.query(DreamTeamPlayer).count()} members")

    finally:
        game_db.close()


def main():
    parser = argparse.ArgumentParser(description="Consolidate small gameweeks")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("STEP 1: Consolidate gameweeks")
    print("=" * 60)
    consolidate_gameweeks()

    print("\n" + "=" * 60)
    print("STEP 2: Recalculate GW points (multi-fixture support)")
    print("=" * 60)
    recalculate_gw_points()

    print("\n" + "=" * 60)
    print("STEP 3: Regenerate DreamTeams")
    print("=" * 60)
    regenerate_dream_teams()

    # Final summary
    print("\n" + "=" * 60)
    print("FINAL STATE")
    print("=" * 60)

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM gameweeks WHERE season = '2025-26'")
    print(f"  Gameweeks: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM fixtures")
    print(f"  Fixtures: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM player_gameweek_points")
    print(f"  PlayerGameweekPoints: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM dream_teams")
    print(f"  DreamTeams: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM dream_team_players")
    print(f"  DreamTeam members: {cur.fetchone()[0]}")

    # Show multi-fixture GWs
    cur.execute("""
        SELECT g.id, g.number, COUNT(f.id) as fx_count
        FROM gameweeks g
        JOIN fixtures f ON f.gameweek_id = g.id
        WHERE g.season = '2025-26'
        GROUP BY g.id
        HAVING fx_count >= 8
        ORDER BY g.number
    """)
    rows = cur.fetchall()
    if rows:
        print(f"\n  Large GWs (8+ fixtures): {len(rows)}")
        for row in rows:
            print(f"    GW {row['number']}: {row['fx_count']} fixtures")

    conn.close()


if __name__ == "__main__":
    main()

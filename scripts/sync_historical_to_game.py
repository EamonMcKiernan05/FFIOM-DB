#!/usr/bin/env python3
"""Sync historical_stats from FFIOM-DB into Fantasy Football IOM game DB.

This takes the retrospectively-calculated player points from FFIOM-DB
historical_stats and syncs them as PlayerGameweekPoints records in the
game database.

Usage:
    python scripts/sync_historical_to_game.py [--season 2025-26] [--clear] [--dry-run]

This is the connection between FFIOM-DB (source of truth) and the game
backend (SQLAlchemy ORM).
"""

import argparse
import os
import sys
import sqlite3
from datetime import datetime

# Paths
FFIOM_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "fantasy_iom.db",
)
GAME_ROOT = os.environ.get(
    "FFIOM_GAME_ROOT", "/home/eamon/Fantasy-Football-Isle-of-Man"
)
GAME_DB_PATH = os.path.join(GAME_ROOT, "data", "fantasy_iom.db")


def main():
    parser = argparse.ArgumentParser(
        description="Sync FFIOM-DB historical_stats into game PlayerGameweekPoints"
    )
    parser.add_argument(
        "--season", default="2025-26", help="Season to sync (default: 2025-26)"
    )
    parser.add_argument(
        "--gw", type=int, default=None, help="Sync only this gameweek"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing PlayerGameweekPoints before syncing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes",
    )
    args = parser.parse_args()

    if not os.path.exists(FFIOM_DB_PATH):
        print(f"ERROR: FFIOM-DB not found at {FFIOM_DB_PATH}")
        sys.exit(1)

    if not os.path.exists(GAME_DB_PATH):
        print(f"ERROR: Game DB not found at {GAME_DB_PATH}")
        sys.exit(1)

    # Load game models
    sys.path.insert(0, GAME_ROOT)
    os.chdir(GAME_ROOT)
    os.environ["DATABASE_URL"] = "sqlite:///./data/fantasy_iom.db"

    from app.database import SessionLocal
    from app.models import Player, Gameweek, PlayerGameweekPoints

    # Open connections
    ffiom = sqlite3.connect(FFIOM_DB_PATH)
    ffiom.row_factory = sqlite3.Row
    game_db = SessionLocal()

    # Build player lookup: name -> player_id
    players = game_db.query(Player).all()
    player_by_name = {p.name: p for p in players}
    # Also build by lowercase for fuzzy matching
    player_by_name_lower = {p.name.lower(): p for p in players}

    # Build gameweek lookup: number -> gameweek_id
    gameweeks = game_db.query(Gameweek).filter(
        Gameweek.season == args.season
    ).order_by(Gameweek.number).all()
    gw_num_to_id = {gw.number: gw.id for gw in gameweeks}

    # Build FFIOM player lookup: name -> fa_id
    ffiom_player_rows = ffiom.execute(
        "SELECT fa_id, name FROM players"
    ).fetchall()
    ffiom_name_to_fa = {row["name"]: row["fa_id"] for row in ffiom_player_rows}

    # Load historical stats from FFIOM-DB
    query = f"""
        SELECT hs.*, p.name as player_name
        FROM historical_stats hs
        JOIN players p ON hs.fa_id = p.fa_id
        WHERE hs.season = ?
    """
    params = [args.season]

    if args.gw:
        query += " AND hs.gameweek = ?"
        params.append(args.gw)

    query += " ORDER BY hs.gameweek, p.name"

    print(f"Season: {args.season}")
    print(f"Gameweeks: {len(gw_num_to_id)} in game DB")
    print(f"Players: {len(player_by_name)} in game DB, {len(ffiom_name_to_fa)} in FFIOM-DB")
    print()

    raw_stats = ffiom.execute(query, params).fetchall()
    print(f"Raw historical stats: {len(raw_stats)}")

    # Deduplicate: some players appear in both First and Combination teams
    # Keep the entry with highest total_points for each (player_name, gameweek)
    deduped = {}
    for stat in raw_stats:
        key = (stat["player_name"], stat["gameweek"])
        if key not in deduped or stat["total_points"] > deduped[key]["total_points"]:
            deduped[key] = stat

    stats = list(deduped.values())
    print(f"After dedup: {len(stats)} entries ({len(raw_stats) - len(stats)} duplicates removed)")

    if args.clear:
        count = game_db.query(PlayerGameweekPoints).filter(
            PlayerGameweekPoints.gameweek_id.in_(gw_num_to_id.values())
        ).count()
        print(f"Clearing {count} existing PlayerGameweekPoints...")
        game_db.query(PlayerGameweekPoints).filter(
            PlayerGameweekPoints.gameweek_id.in_(gw_num_to_id.values())
        ).delete(synchronize_session=False)
        game_db.commit()

    synced = 0
    skipped = 0
    errors = []

    for stat in stats:
        gw_num = stat["gameweek"]
        player_name = stat["player_name"]

        gw_id = gw_num_to_id.get(gw_num)
        if not gw_id:
            continue

        # Find player by name
        game_player = player_by_name.get(player_name)
        if not game_player:
            game_player = player_by_name_lower.get(player_name.lower())
        if not game_player:
            # Try partial match
            for gn, gp in player_by_name.items():
                if gn.lower() == player_name.lower():
                    game_player = gp
                    break

        if not game_player:
            skipped += 1
            continue

        if not args.dry_run:
            # Use merge-style upsert: check for existing, update or insert
            existing = game_db.query(PlayerGameweekPoints).filter(
                PlayerGameweekPoints.player_id == game_player.id,
                PlayerGameweekPoints.gameweek_id == gw_id,
            ).first()

            if existing:
                existing.opponent_team = stat["opponent"]
                existing.was_home = bool(stat["was_home"])
                existing.minutes_played = stat["minutes_played"] or 90
                existing.did_play = True
                existing.goals_scored = stat["goals_scored"] or 0
                existing.assists = stat["assists"] or 0
                existing.clean_sheet = bool(stat["clean_sheet"])
                existing.goals_conceded = stat["goals_conceded"] or 0
                existing.saves = stat["saves"] or 0
                existing.yellow_card = bool(stat["yellow_card"])
                existing.red_card = bool(stat["red_card"])
                existing.own_goal = bool(stat["own_goal"])
                existing.bonus_points = stat["bonus_points"] or 0
                existing.base_points = stat["base_points"] or 0
                existing.total_points = stat["total_points"] or 0
            else:
                pgp = PlayerGameweekPoints(
                    player_id=game_player.id,
                    gameweek_id=gw_id,
                    opponent_team=stat["opponent"],
                    was_home=bool(stat["was_home"]),
                    minutes_played=stat["minutes_played"] or 90,
                    did_play=True,
                    goals_scored=stat["goals_scored"] or 0,
                    assists=stat["assists"] or 0,
                    clean_sheet=bool(stat["clean_sheet"]),
                    goals_conceded=stat["goals_conceded"] or 0,
                    saves=stat["saves"] or 0,
                    yellow_card=bool(stat["yellow_card"]),
                    red_card=bool(stat["red_card"]),
                    own_goal=bool(stat["own_goal"]),
                    bonus_points=stat["bonus_points"] or 0,
                    base_points=stat["base_points"] or 0,
                    total_points=stat["total_points"] or 0,
                )
                game_db.add(pgp)

            synced += 1

            # Flush periodically to avoid memory issues
            if synced % 500 == 0:
                game_db.flush()

    if not args.dry_run:
        game_db.commit()
        print(f"\nSync complete: {synced} records synced, {skipped} skipped (player not found)")
    else:
        print(f"\n[Dry run] Would sync {synced} records, skip {skipped}")

    # Update player season totals from synced data
    if not args.dry_run:
        for gw_id in gw_num_to_id.values():
            # Aggregate points per player for this GW
            results = game_db.query(
                PlayerGameweekPoints.player_id,
                PlayerGameweekPoints.total_points
            ).filter(
                PlayerGameweekPoints.gameweek_id == gw_id
            ).all()

            for player_id, pts in results:
                player = game_db.query(Player).get(player_id)
                if player:
                    # Add to season totals
                    player.total_points_season = (player.total_points_season or 0) + pts

        game_db.commit()
        print("Player season totals updated")

    # Stats summary
    for gw_num in sorted(gw_num_to_id.keys()):
        count = game_db.query(PlayerGameweekPoints).filter(
            PlayerGameweekPoints.gameweek_id == gw_num_to_id[gw_num]
        ).count()
        if count > 0:
            result = game_db.query(
                PlayerGameweekPoints.total_points
            ).filter(
                PlayerGameweekPoints.gameweek_id == gw_num_to_id[gw_num]
            ).all()
            total = sum(r.total_points for r in result)
            print(f"  GW {gw_num}: {count} players, {total} total points")

    game_db.close()
    ffiom.close()
    print("\nDone!")


if __name__ == "__main__":
    main()

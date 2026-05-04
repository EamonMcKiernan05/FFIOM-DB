#!/usr/bin/env python3
"""Sync historical_stats from FFIOM-DB into Fantasy Football IOM game DB.

Usage:
    python scripts/sync_historical_to_game.py [--season 2025-26] [--clear] [--dry-run]
"""

import argparse
import os
import sys
import sqlite3

# Paths
FFIOM_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "fantasy_iom.db",
)
GAME_ROOT = os.environ.get(
    "FFIOM_GAME_ROOT", "/home/eamon/Fantasy-Football-Isle-of-Man"
)

# Team name mapping
TEAM_NAME_MAP = {
    "Peel First": "Peel",
    "Corinthians First": "Corinthians",
    "Laxey First": "Laxey",
    "St Marys First": "St Marys",
    "St Johns United First": "St Johns",
    "Onchan First": "Onchan",
    "Ramsey First": "Ramsey",
    "Rushen United First": "Rushen United",
    "Union Mills First": "Union Mills",
    "Ayre United First": "Ayre United",
    "Braddan First": "Braddan",
    "Foxdale First": "Foxdale",
    "DHSOB First": "DHSOB",
    "Peel": "Peel",
    "Corinthians": "Corinthians",
    "Laxey": "Laxey",
    "St Marys": "St Marys",
    "St Johns": "St Johns",
    "Onchan": "Onchan",
    "Ramsey": "Ramsey",
    "Rushen United": "Rushen United",
    "Union Mills": "Union Mills",
    "Ayre United": "Ayre United",
    "Braddan": "Braddan",
    "Foxdale": "Foxdale",
    "DHSOB": "DHSOB",
}


def main():
    parser = argparse.ArgumentParser(
        description="Sync FFIOM-DB historical_stats into game PlayerGameweekPoints"
    )
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--gw", type=int, default=None)
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(FFIOM_DB_PATH):
        print(f"ERROR: FFIOM-DB not found at {FFIOM_DB_PATH}")
        sys.exit(1)

    # Load game models
    sys.path.insert(0, GAME_ROOT)
    os.chdir(GAME_ROOT)
    os.environ["DATABASE_URL"] = "sqlite:///./data/fantasy_iom.db"

    from app.database import SessionLocal
    from app.models import Player, Gameweek, PlayerGameweekPoints, Team

    # Open connections
    ffiom = sqlite3.connect(FFIOM_DB_PATH)
    ffiom.row_factory = sqlite3.Row
    game_db = SessionLocal()

    # Build player lookup: name -> player_id
    players = game_db.query(Player).all()
    player_by_name = {p.name: p for p in players}
    player_by_name_lower = {p.name.lower(): p for p in players}

    # Build gameweek lookup: number -> gameweek_id
    gameweeks = game_db.query(Gameweek).filter(
        Gameweek.season == args.season
    ).order_by(Gameweek.number).all()
    gw_num_to_id = {gw.number: gw.id for gw in gameweeks}

    # Load all teams for lookup
    game_teams = {t.name: t for t in game_db.query(Team).all()}

    # Load historical stats from FFIOM-DB
    query = """
        SELECT hs.*, p.name as player_name, p.fa_id
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
    print(f"Players: {len(player_by_name)} in game DB")

    raw_stats = ffiom.execute(query, params).fetchall()
    print(f"Raw historical stats: {len(raw_stats)}")

    # Deduplicate
    deduped = {}
    for stat in raw_stats:
        key = (stat["player_name"], stat["gameweek"])
        if key not in deduped or stat["total_points"] > deduped[key]["total_points"]:
            deduped[key] = stat

    stats = list(deduped.values())
    print(f"After dedup: {len(stats)} entries")

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
    added_players = 0

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

        # If not found, add the player
        if not game_player:
            raw_team = None
            for s in stats:
                if s["player_name"] == player_name:
                    # Get team from player_seasons
                    row = ffiom.execute(
                        "SELECT team FROM player_seasons WHERE fa_id = ? AND season = ?",
                        (s["fa_id"], args.season),
                    ).fetchone()
                    if row:
                        raw_team = row["team"]
                    break

            if not raw_team:
                skipped += 1
                continue

            normalized_team = TEAM_NAME_MAP.get(raw_team, raw_team.replace(" First", "").strip())
            game_team = game_teams.get(normalized_team)

            if not game_team:
                skipped += 1
                continue

            web_name = player_name.lower().replace(" ", "_").replace("'", "")
            game_player = Player(
                name=player_name,
                web_name=web_name,
                team_id=game_team.id,
                position=None,
                price=5.0,
                price_start=5.0,
                is_active=True,
            )
            game_db.add(game_player)
            game_db.flush()

            player_by_name[player_name] = game_player
            player_by_name_lower[player_name.lower()] = game_player
            added_players += 1

        if not args.dry_run:
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

            if synced % 500 == 0:
                game_db.flush()

    if not args.dry_run:
        game_db.commit()
        print(f"\nSync complete: {synced} records, {added_players} new players, {skipped} skipped")
    else:
        print(f"\n[Dry run] Would sync {synced} records, add {added_players} players")

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

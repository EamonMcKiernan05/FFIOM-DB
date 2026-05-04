#!/usr/bin/env python3
"""Import teams, gameweeks, and fixtures from the Fantasy Football IOM game DB.

Syncs fixture data from the game database into FFIOM-DB so that retrospective
scoring can be computed from fixture results rather than player season stats.

Usage:
    python scripts/import_from_game.py [--season 2025-26] [--clear] [--dry-run]
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
GAME_DB_PATH = os.environ.get(
    "FFIOM_GAME_DB",
    "/home/eamon/Fantasy-Football-Isle-of-Man/data/fantasy_iom.db",
)

# Normalize fixture team names to our canonical names
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


def normalize_team_name(name):
    """Map fixture team names to canonical names."""
    if not name:
        return name
    return TEAM_NAME_MAP.get(name, name.strip())


def main():
    parser = argparse.ArgumentParser(
        description="Import teams, gameweeks, fixtures from game DB into FFIOM-DB"
    )
    parser.add_argument(
        "--season", default="2025-26", help="Season to import (default: 2025-26)"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing teams/gameweeks/fixtures before importing",
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

    print(f"FFIOM-DB: {FFIOM_DB_PATH}")
    print(f"Game DB:  {GAME_DB_PATH}")
    print(f"Season:   {args.season}")
    print()

    # Ensure src/ is on the path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    ffiom = sqlite3.connect(FFIOM_DB_PATH)
    ffiom.execute("PRAGMA foreign_keys=OFF")
    game = sqlite3.connect(GAME_DB_PATH)
    game.row_factory = sqlite3.Row

    # Ensure tables exist
    import src.schema as schema_module
    schema_module.create_tables(ffiom)

    added = {"teams": 0, "gameweeks": 0, "fixtures": 0}
    updated = {"teams": 0, "gameweeks": 0, "fixtures": 0}

    # --- TEAMS ---
    if args.clear:
        ffiom.execute("DELETE FROM fixtures")
        ffiom.execute("DELETE FROM gameweeks")
        ffiom.execute("DELETE FROM teams")
        ffiom.commit()
        print("Cleared existing teams, gameweeks, fixtures")

    cur = game.execute("SELECT * FROM teams ORDER BY id")
    game_teams = cur.fetchall()
    print(f"\n=== TEAMS ({len(game_teams)} in game DB) ===")

    # Build lookup: game team id -> FFIOM team id
    game_team_id_map = {}
    ffiom_cur = ffiom.cursor()

    for gt in game_teams:
        canonical = normalize_team_name(gt["name"])
        row = ffiom_cur.execute(
            "SELECT id FROM teams WHERE name = ?", (canonical,)
        ).fetchone()

        if row:
            game_team_id_map[gt["id"]] = row[0]
            updated["teams"] += 1
        else:
            ffiom_cur.execute(
                "INSERT INTO teams (name, short_name, division) VALUES (?, ?, ?)",
                (canonical, gt["short_name"], "Premier"),
            )
            new_id = ffiom_cur.lastrowid
            game_team_id_map[gt["id"]] = new_id
            added["teams"] += 1
            print(f"  Added team: {canonical} (game_id={gt['id']} -> ffiom_id={new_id})")

    print(f"  Teams: +{added['teams']} / ~{updated['teams']}")

    # --- GAMEWEEKS ---
    cur = game.execute(
        "SELECT * FROM gameweeks WHERE season = ? ORDER BY number",
        (args.season,),
    )
    game_gws = cur.fetchall()
    print(f"\n=== GAMEWEEKS ({len(game_gws)} for {args.season}) ===")

    # Build lookup: game gw id -> FFIOM gw id
    game_gw_id_map = {}

    for gg in game_gws:
        row = ffiom_cur.execute(
            "SELECT id FROM gameweeks WHERE number = ? AND season = ?",
            (gg["number"], args.season),
        ).fetchone()

        if row:
            game_gw_id_map[gg["id"]] = row[0]
            updated["gameweeks"] += 1
        else:
            ffiom_cur.execute(
                "INSERT INTO gameweeks (number, season, start_date, end_date, deadline, closed, scored) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    gg["number"],
                    args.season,
                    gg["start_date"],
                    gg["end_date"],
                    gg["deadline"],
                    bool(gg["closed"]),
                    bool(gg["scored"]),
                ),
            )
            new_id = ffiom_cur.lastrowid
            game_gw_id_map[gg["id"]] = new_id
            added["gameweeks"] += 1

    print(f"  Gameweeks: +{added['gameweeks']} / ~{updated['gameweeks']}")

    # --- FIXTURES ---
    cur = game.execute(
        "SELECT * FROM fixtures WHERE gameweek_id IN ({}) ORDER BY id".format(
            ",".join(str(gid) for gid in game_gw_id_map.keys())
        )
    )
    game_fixtures = cur.fetchall()
    print(f"\n=== FIXTURES ({len(game_fixtures)}) ===")

    for gf in game_fixtures:
        ffiom_gw_id = game_gw_id_map.get(gf["gameweek_id"])
        if not ffiom_gw_id:
            continue

        ffiom_home_id = game_team_id_map.get(gf["home_team_id"])
        ffiom_away_id = game_team_id_map.get(gf["away_team_id"])

        home_name = normalize_team_name(gf["home_team_name"])
        away_name = normalize_team_name(gf["away_team_name"])

        # Check if fixture already exists (by gw + teams + date)
        existing = ffiom_cur.execute(
            "SELECT id FROM fixtures WHERE gameweek_id = ? AND home_team_id = ? "
            "AND away_team_id = ? AND fixture_date = ?",
            (ffiom_gw_id, ffiom_home_id, ffiom_away_id, gf["date"]),
        ).fetchone()

        if existing:
            updated["fixtures"] += 1
        else:
            ffiom_cur.execute(
                "INSERT INTO fixtures (gameweek_id, fixture_date, home_team_id, away_team_id, "
                "home_team_name, away_team_name, home_score, away_score, "
                "half_time_home, half_time_away, home_scorers, away_scorers, "
                "played, competition, division_name, home_difficulty, away_difficulty) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ffiom_gw_id,
                    gf["date"],
                    ffiom_home_id,
                    ffiom_away_id,
                    home_name,
                    away_name,
                    gf["home_score"],
                    gf["away_score"],
                    gf["half_time_home"],
                    gf["half_time_away"],
                    gf["home_scorers"],
                    gf["away_scorers"],
                    bool(gf["played"]),
                    gf["competition"],
                    gf["division_name"],
                    gf["home_difficulty"] or 3,
                    gf["away_difficulty"] or 3,
                ),
            )
            added["fixtures"] += 1

    print(f"  Fixtures: +{added['fixtures']} / ~{updated['fixtures']}")

    if args.dry_run:
        print("\n[Dry run] No changes written")
    else:
        ffiom.commit()

    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"  Teams:     {ffiom.execute('SELECT COUNT(*) FROM teams').fetchone()[0]} total")
    print(f"  Gameweeks: {ffiom.execute('SELECT COUNT(*) FROM gameweeks').fetchone()[0]} total")
    print(
        f"  Fixtures:  {ffiom.execute('SELECT COUNT(*) FROM fixtures').fetchone()[0]} total"
    )
    print(
        f"  Played:    {ffiom.execute('SELECT COUNT(*) FROM fixtures WHERE played=1').fetchone()[0]}"
    )

    # Log sync
    ffiom.execute(
        "INSERT INTO sync_log (source, sync_type, records_processed, records_added, records_updated, completed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "game_db",
            "import_fixtures",
            len(game_fixtures),
            sum(added.values()),
            sum(updated.values()),
            datetime.now().isoformat(),
        ),
    )
    ffiom.commit()

    ffiom.close()
    game.close()
    print("\nImport complete.")


if __name__ == "__main__":
    main()

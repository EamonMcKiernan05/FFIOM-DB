#!/usr/bin/env python3
"""Rebuild FFIOM-DB with correct Premier League player data from FullTime website.

Usage:
    python scripts/rebuild_premier_players.py [--season 2025-26]
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

FFIOM_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "fantasy_iom.db",
)

# Valid Premier League teams
VALID_TEAMS = {
    "Peel First", "Corinthians First", "Laxey First", "St Marys First",
    "St Johns United First", "Onchan First", "Ramsey First",
    "Rushen United First", "Union Mills First", "Ayre United First",
    "Braddan First", "Foxdale First", "DHSOB First",
}


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild FFIOM-DB with correct Premier League player data"
    )
    parser.add_argument(
        "--season", default="2025-26", help="Season to rebuild (default: 2025-26)"
    )
    parser.add_argument(
        "--input", default="data/fulltime_premier_players.json",
        help="Path to scraped player data JSON"
    )
    args = parser.parse_args()

    if not os.path.exists(FFIOM_DB_PATH):
        print(f"ERROR: FFIOM-DB not found at {FFIOM_DB_PATH}")
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    # Load scraped player data
    with open(args.input) as f:
        scraped_players = json.load(f)

    print(f"Loaded {len(scraped_players)} players from {args.input}")

    # Filter to valid Premier League teams
    premier_players = [p for p in scraped_players if p.get("team") in VALID_TEAMS]
    print(f"Premier League players: {len(premier_players)}")

    # Open database
    conn = sqlite3.connect(FFIOM_DB_PATH)
    conn.execute("PRAGMA foreign_keys=OFF")
    cur = conn.cursor()

    season = args.season

    # Clear existing season data
    cur.execute("DELETE FROM historical_stats WHERE season = ?", (season,))
    cur.execute("DELETE FROM player_seasons WHERE season = ?", (season,))
    cur.execute("DELETE FROM player_movements WHERE season = ?", (season,))
    conn.commit()
    print("Cleared existing season data")

    # Insert players and season stats
    inserted = 0
    for p in premier_players:
        fa_id = p["fa_id"]
        name = p["name"]
        team = p["team"]
        goals = p.get("goals", 0)
        assists = p.get("assists", 0)
        appearances = p.get("appearances", 0)
        yellows = p.get("yellows", 0)
        reds = p.get("reds", 0)

        # Insert or update player
        cur.execute("SELECT id FROM players WHERE fa_id = ?", (fa_id,))
        row = cur.fetchone()

        if row:
            player_id = row[0]
            # Update player info
            cur.execute(
                "UPDATE players SET name = ?, team = ?, updated_at = ? WHERE fa_id = ?",
                (name, team, datetime.now().isoformat(), fa_id),
            )
        else:
            # Insert new player
            cur.execute(
                "INSERT INTO players (fa_id, name, team, position, is_active) VALUES (?, ?, ?, ?, 1)",
                (fa_id, name, team, None),
            )
            player_id = cur.lastrowid

        # Insert season stats
        cur.execute(
            "INSERT OR REPLACE INTO player_seasons "
            "(fa_id, season, team, goals, assists, appearances, yellows, reds, minutes_played) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fa_id, season, team, goals, assists, appearances, yellows, reds, appearances * 90),
        )
        inserted += 1

    conn.commit()
    print(f"Inserted/updated {inserted} players and season stats")

    # Verify
    player_count = cur.execute(
        "SELECT COUNT(*) FROM player_seasons WHERE season = ?", (season,)
    ).fetchone()[0]
    print(f"Total player_seasons entries: {player_count}")

    # Show top scorers
    top = cur.execute(
        "SELECT p.name, ps.team, ps.goals, ps.appearances "
        "FROM player_seasons ps JOIN players p ON ps.fa_id = p.fa_id "
        "WHERE ps.season = ? ORDER BY ps.goals DESC LIMIT 10",
        (season,),
    ).fetchall()
    print("\nTop 10 scorers:")
    for name, team, goals, apps in top:
        print(f"  {name:<30} {team:<25} goals={goals} apps={apps}")

    # Log sync
    cur.execute(
        "INSERT INTO sync_log (source, sync_type, records_processed, records_added, completed_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "fulltime_website",
            "rebuild_premier_players",
            len(scraped_players),
            inserted,
            datetime.now().isoformat(),
            "success",
        ),
    )
    conn.commit()
    conn.close()
    print("\nRebuild complete!")


if __name__ == "__main__":
    main()

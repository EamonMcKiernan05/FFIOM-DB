#!/usr/bin/env python3
"""
Restructure FFIOM-DB to be the source of truth for player/fixture data.

This script:
1. Backs up current FFIOM-DB
2. Drops game-specific tables from FFIOM-DB (users, fantasy_teams, squad_players, etc.)
3. Keeps only reference tables: players, teams, gameweeks, fixtures, leagues, divisions, seasons

The game DB (Fantasy-Football-Isle-of-Man) is NOT modified.
"""
import shutil
import sqlite3
from pathlib import Path
import os
import sys

FFIOM_DB = Path("/home/eamon/FFIOM-DB/data/fantasy_iom.db")
BACKUP = Path("/home/eamon/FFIOM-DB/data/fantasy_iom.db.pre_separation")

# Tables to KEEP in FFIOM-DB (source of truth)
KEEP_TABLES = {
    'players',       # Player registry
    'teams',         # Football teams
    'gameweeks',     # Gameweek definitions
    'fixtures',      # Match fixtures
    'leagues',       # League structure
    'divisions',     # Division within league
    'seasons',       # Season tracking
}

# Tables to DROP from FFIOM-DB (game-specific)
DROP_TABLES = {
    'users',
    'fantasy_teams',
    'squad_players',
    'player_gameweek_points',
    'fantasy_team_history',
    'transfers',
    'chips',
    'dream_teams',
    'dream_team_players',
    'mini_leagues',
    'mini_league_members',
    'h2h_leagues',
    'h2h_participants',
    'h2h_matches',
    'player_price_history',
    'gameweek_stats',
    'player_fixtures',
}


def main():
    if not FFIOM_DB.exists():
        print(f"ERROR: FFIOM-DB not found at {FFIOM_DB}")
        sys.exit(1)

    # Step 1: Backup
    print(f"Backing up FFIOM-DB to {BACKUP}")
    shutil.copy2(str(FFIOM_DB), str(BACKUP))
    print("Backup complete.")

    # Step 2: Connect and inspect
    conn = sqlite3.connect(str(FFIOM_DB))
    cur = conn.cursor()

    # Get all current tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    all_tables = [r[0] for r in cur.fetchall()]
    print(f"\nCurrent tables ({len(all_tables)}): {', '.join(all_tables)}")

    # Step 3: Count data before dropping
    print("\nData counts before restructuring:")
    for t in sorted(all_tables):
        try:
            cur.execute(f'SELECT COUNT(*) FROM [{t}]')
            cnt = cur.fetchone()[0]
            print(f"  {t}: {cnt} rows")
        except Exception as e:
            print(f"  {t}: ERROR - {e}")

    # Step 4: Drop game tables
    print(f"\nDropping {len(DROP_TABLES)} game-specific tables from FFIOM-DB...")
    for table in DROP_TABLES:
        if table in all_tables:
            cur.execute(f'DROP TABLE IF EXISTS [{table}]')
            print(f"  Dropped: {table}")
        else:
            print(f"  Already absent: {table}")

    conn.commit()

    # Step 5: Verify remaining tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    remaining = [r[0] for r in cur.fetchall()]
    print(f"\nRemaining tables in FFIOM-DB ({len(remaining)}):")
    for t in remaining:
        cur.execute(f'SELECT COUNT(*) FROM [{t}]')
        cnt = cur.fetchone()[0]
        print(f"  {t}: {cnt} rows")

    conn.close()
    print(f"\nDone! FFIOM-DB now contains only reference data.")
    print(f"Backup available at: {BACKUP}")


if __name__ == "__main__":
    main()

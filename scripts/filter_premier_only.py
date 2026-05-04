#!/usr/bin/env python3
"""Filter FFIOM-DB to only include Canada Life Premier League data.

Removes all Combination teams, Marown, St Georges, and any other non-Premier
League data from player_seasons, historical_stats, and player_movements.

The Premier League teams are the 13 First XI teams.

Usage:
    python scripts/filter_premier_only.py [--season 2025-26] [--dry-run]
"""

import argparse
import os
import sys
from datetime import datetime

FFIOM_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "fantasy_iom.db",
)

# The 13 Canada Life Premier League teams (with "First" suffix as stored)
PREMIER_TEAMS = {
    "Peel First",
    "Corinthians First",
    "Laxey First",
    "St Marys First",
    "St Johns United First",
    "Onchan First",
    "Ramsey First",
    "Rushen United First",
    "Union Mills First",
    "Ayre United First",
    "Braddan First",
    "Foxdale First",
    "DHSOB First",
}


def main():
    parser = argparse.ArgumentParser(
        description="Filter FFIOM-DB to Premier League data only"
    )
    parser.add_argument(
        "--season", default="2025-26", help="Season to filter (default: 2025-26)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing"
    )
    args = parser.parse_args()

    if not os.path.exists(FFIOM_DB_PATH):
        print(f"ERROR: FFIOM-DB not found at {FFIOM_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(FFIOM_DB_PATH)
    conn.execute("PRAGMA foreign_keys=OFF")  # Allow deletes regardless of FK
    cur = conn.cursor()

    season = args.season

    # Count current data
    total_seasons = cur.execute(
        "SELECT COUNT(*) FROM player_seasons WHERE season = ?", (season,)
    ).fetchone()[0]
    total_historical = cur.execute(
        "SELECT COUNT(*) FROM historical_stats WHERE season = ?", (season,)
    ).fetchone()[0]

    # Count Premier League data
    premier_seasons = cur.execute(
        "SELECT COUNT(*) FROM player_seasons WHERE season = ? AND team IN ("
        + ",".join(["?"] * len(PREMIER_TEAMS))
        + ")",
        [season] + list(PREMIER_TEAMS),
    ).fetchone()[0]

    premier_fa_ids = cur.execute(
        "SELECT DISTINCT fa_id FROM player_seasons WHERE season = ? AND team IN ("
        + ",".join(["?"] * len(PREMIER_TEAMS))
        + ")",
        [season] + list(PREMIER_TEAMS),
    ).fetchall()
    premier_fa_set = {r[0] for r in premier_fa_ids}

    premier_historical = cur.execute(
        "SELECT COUNT(*) FROM historical_stats WHERE season = ? AND fa_id IN ("
        + ",".join(["?"] * len(premier_fa_set))
        + ")",
        [season] + list(premier_fa_set),
    ).fetchone()[0]

    print(f"Season: {season}")
    print(f"Current data:")
    print(f"  player_seasons: {total_seasons} total, {premier_seasons} Premier League")
    print(f"  historical_stats: {total_historical} total, {premier_historical} Premier League")
    print(f"  Players to keep: {len(premier_fa_set)}")

    to_remove_seasons = total_seasons - premier_seasons
    to_remove_historical = total_historical - premier_historical

    if to_remove_seasons == 0 and to_remove_historical == 0:
        print("\nAlready filtered - no changes needed.")
        conn.close()
        return

    if args.dry_run:
        print(f"\n[Dry run] Would remove:")
        print(f"  {to_remove_seasons} player_seasons entries")
        print(f"  {to_remove_historical} historical_stats entries")
        conn.close()
        return

    # Remove non-Premier player_seasons
    cur.execute(
        "DELETE FROM player_seasons WHERE season = ? AND team NOT IN ("
        + ",".join(["?"] * len(PREMIER_TEAMS))
        + ")",
        [season] + list(PREMIER_TEAMS),
    )
    removed_seasons = cur.rowcount

    # Remove non-Premier historical_stats
    placeholders = ",".join(["?"] * len(premier_fa_set))
    cur.execute(
        "DELETE FROM historical_stats WHERE season = ? AND fa_id NOT IN (" + placeholders + ")",
        [season] + list(premier_fa_set),
    )
    removed_historical = cur.rowcount

    # Remove non-Premier player_movements (from non-Premier teams or to non-Premier teams)
    premier_list = list(PREMIER_TEAMS)
    premier_placeholders = ",".join(["?"] * len(PREMIER_TEAMS))
    cur.execute(
        f"DELETE FROM player_movements WHERE season = ? AND ("
        f"(from_team NOT IN ({premier_placeholders}) AND from_team != 'Unknown') "
        f"OR (to_team NOT IN ({premier_placeholders}) AND to_team != 'Unknown'))",
        [season] + premier_list + premier_list,
    )
    removed_movements = cur.rowcount

    conn.commit()

    # Verify
    remaining_seasons = cur.execute(
        "SELECT COUNT(*) FROM player_seasons WHERE season = ?", (season,)
    ).fetchone()[0]
    remaining_historical = cur.execute(
        "SELECT COUNT(*) FROM historical_stats WHERE season = ?", (season,)
    ).fetchone()[0]

    # Check remaining teams
    remaining_teams = cur.execute(
        "SELECT DISTINCT team, COUNT(*) as cnt FROM player_seasons WHERE season = ? GROUP BY team ORDER BY cnt DESC",
        (season,),
    ).fetchall()

    print(f"\nFiltered:")
    print(f"  Removed {removed_seasons} player_seasons entries")
    print(f"  Removed {removed_historical} historical_stats entries")
    print(f"  Removed {removed_movements} player_movements entries")
    print(f"\nRemaining:")
    print(f"  player_seasons: {remaining_seasons}")
    print(f"  historical_stats: {remaining_historical}")
    print(f"\nRemaining teams:")
    for team, cnt in remaining_teams:
        status = "PREMIER" if team in PREMIER_TEAMS else "OTHER"
        print(f"  [{status}] {cnt} players - '{team}'")

    # Log
    cur.execute(
        "INSERT INTO sync_log (source, sync_type, records_processed, records_deleted, completed_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "filter_premier_only",
            "remove_non_premier",
            to_remove_seasons + to_remove_historical,
            removed_seasons + removed_historical,
            datetime.now().isoformat(),
            "success",
        ),
    )
    conn.commit()
    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    import sqlite3
    main()

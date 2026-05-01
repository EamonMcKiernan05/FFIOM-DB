#!/usr/bin/env python3
"""Import existing player data from JSON files into FFIOM-DB.

Usage:
    python scripts/import_real_data.py [--season 2025-26] [--players-file path] [--stats-file path]

Imports players from real_players.json and enriches with stats from player_stats_cache.json.
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.schema import create_tables
from src.sync import SyncEngine


def load_config():
    """Load configuration from config.yaml."""
    try:
        import yaml

        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"
        )
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except ImportError:
        print("WARNING: pyyaml not installed, using defaults")
        return {}
    except FileNotFoundError:
        return {}


def main():
    parser = argparse.ArgumentParser(description="Import player data from JSON files")
    parser.add_argument("--season", default="2025-26", help="Season identifier (default: 2025-26)")
    parser.add_argument(
        "--players-file",
        default=None,
        help="Path to real_players.json (default: from config.yaml)",
    )
    parser.add_argument(
        "--stats-file",
        default=None,
        help="Path to player_stats_cache.json (default: from config.yaml)",
    )
    args = parser.parse_args()

    config = load_config()

    # Get paths from args or config
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "data", "fantasy_iom.db")

    if args.players_file is None:
        players_file = config.get("data_sources", {}).get(
            "players_file", "/home/eamon/Fantasy-Football-Isle-of-Man/data/real_players.json"
        )
    else:
        players_file = args.players_file

    if args.stats_file is None:
        stats_file = config.get("data_sources", {}).get(
            "stats_file", "/home/eamon/Fantasy-Football-Isle-of-Man/data/player_stats_cache.json"
        )
    else:
        stats_file = args.stats_file

    season = args.season

    # Verify files exist
    if not os.path.exists(players_file):
        print(f"ERROR: Players file not found: {players_file}")
        sys.exit(1)

    if not os.path.exists(stats_file):
        print(f"WARNING: Stats file not found: {stats_file} (will import without stats)")
        stats_file = None

    # Initialize database if needed
    if not os.path.exists(db_path):
        print(f"Database not found. Initializing: {db_path}")
        conn = sqlite3.connect(db_path)
        create_tables(conn)
        conn.close()

    # Import data
    print(f"Importing players from: {players_file}")
    if stats_file:
        print(f"Enriching with stats from: {stats_file}")
    print(f"Season: {season}")

    conn = sqlite3.connect(db_path)
    engine = SyncEngine(conn)

    result = engine.sync_from_json(players_file, stats_file or "", season)

    # Print summary
    print(f"\nImport complete:")
    print(f"  Source: {result['source']}")
    print(f"  Records processed: {result['records_processed']}")
    print(f"  Records added: {result['records_added']}")
    print(f"  Records updated: {result['records_updated']}")

    # Show sync log
    from src.queries import get_sync_log

    logs = get_sync_log(conn, limit=3)
    if logs:
        print(f"\nRecent sync entries:")
        for log in logs:
            print(f"  [{log['started_at']}] {log['source']} - {log['sync_type']} ({log['status']})")

    conn.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Initialize the FFIOM-DB database.

Usage:
    python scripts/init_db.py [--force-reset]

Creates the database file and all tables with proper constraints.
If the database already exists, it will print a warning unless --force-reset is used.
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.schema import create_tables


def main():
    parser = argparse.ArgumentParser(description="Initialize FFIOM-DB database")
    parser.add_argument(
        "--force-reset",
        action="store_true",
        help="Delete existing database and re-create from scratch",
    )
    args = parser.parse_args()

    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fantasy_iom.db"
    )
    data_dir = os.path.dirname(db_path)

    # Ensure data directory exists
    os.makedirs(data_dir, exist_ok=True)

    if os.path.exists(db_path) and not args.force_reset:
        print(f"Database already exists: {db_path}")
        print("Use --force-reset to delete and re-create.")
        return

    if args.force_reset and os.path.exists(db_path):
        print(f"Deleting existing database: {db_path}")
        os.remove(db_path)

    print(f"Creating database: {db_path}")
    conn = sqlite3.connect(db_path)
    create_tables(conn)
    conn.close()
    print("Database initialized successfully.")
    print("Tables created: players, player_seasons, player_movements, historical_stats, sync_log")


if __name__ == "__main__":
    main()

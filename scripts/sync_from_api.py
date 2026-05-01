#!/usr/bin/env python3
"""Sync player data from the FullTime API into FFIOM-DB.

Usage:
    python scripts/sync_from_api.py [--api-url http://localhost:5000] [--division-id 175685803] [--season 2025-26]

Fetches the latest player data from the FullTime API and merges it into the local database.
Uses INSERT OR IGNORE for new players and UPDATE for existing players.
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
    parser = argparse.ArgumentParser(description="Sync player data from FullTime API")
    parser.add_argument(
        "--api-url", default=None, help="FullTime API base URL (default: from config.yaml)"
    )
    parser.add_argument(
        "--division-id", default=None, help="Division ID (default: from config.yaml)"
    )
    parser.add_argument("--season", default="2025-26", help="Season identifier (default: 2025-26)")
    args = parser.parse_args()

    config = load_config()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "data", "fantasy_iom.db")

    # Get API settings from args or config
    api_url = args.api_url or config.get("api", {}).get("url", "http://localhost:5000")
    division_id = args.division_id or config.get("api", {}).get("division_id", 175685803)
    season = args.season

    # Remove trailing slash from API URL
    api_url = api_url.rstrip("/")

    # Initialize database if needed
    if not os.path.exists(db_path):
        print(f"Database not found. Initializing: {db_path}")
        conn = sqlite3.connect(db_path)
        create_tables(conn)
        conn.close()

    print(f"Syncing from FullTime API:")
    print(f"  API URL: {api_url}")
    print(f"  Division ID: {division_id}")
    print(f"  Season: {season}")

    conn = sqlite3.connect(db_path)
    engine = SyncEngine(conn)

    try:
        result = engine.sync_from_api(api_url, division_id, season)

        print(f"\nSync complete:")
        print(f"  Source: {result['source']}")
        print(f"  Records processed: {result['records_processed']}")
        print(f"  Records added: {result['records_added']}")
        print(f"  Records updated: {result['records_updated']}")

        if result.get("errors"):
            print(f"  Errors: {', '.join(result['errors'])}")

        # Show sync log
        from src.queries import get_sync_log

        logs = get_sync_log(conn, limit=3)
        if logs:
            print(f"\nRecent sync entries:")
            for log in logs:
                print(f"  [{log['started_at']}] {log['source']} - {log['sync_type']} ({log['status']})")

    except Exception as e:
        print(f"\nSync failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

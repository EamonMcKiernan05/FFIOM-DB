#!/usr/bin/env python3
"""Scrape FullTime website and update FFIOM-DB.

Usage:
    python scripts/scrape_and_update.py [--action results|players|all] [--season 2025-26]

This script uses the browser to scrape:
- Results from https://fulltime.thefa.com/results.html
- Player stats from stat leaders page
- Individual player pages if needed
"""

import argparse
import json
import os
import sqlite3
import sys
import subprocess
from datetime import datetime

FFIOM_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "fantasy_iom.db",
)


def scrape_results_to_json(output_path):
    """Scrape results from FullTime website using browser tools.
    
    This requires browser tools to be available. Uses the browser_navigate
    and browser_console tools to extract data.
    """
    print("Scraping results from FullTime website...")
    
    # Navigate to results page
    import subprocess
    
    # This is a placeholder - actual scraping happens via browser tools
    # The browser tools (browser_navigate, browser_console) are used in the CLI
    # to extract the data, then saved to JSON
    
    print("Note: Results scraping requires browser tools.")
    print("Use browser_navigate to results page, then browser_console to extract data.")
    print("Save the extracted data to a JSON file for processing.")
    
    return []


def scrape_players_to_json(output_path):
    """Scrape player stats from FullTime stat leaders page using browser tools.
    
    This requires browser tools to be available.
    """
    print("Scraping player stats from FullTime stat leaders page...")
    
    print("Note: Player scraping requires browser tools.")
    print("Use browser_navigate to stat leaders page, then browser_console to extract data.")
    print("Save the extracted data to a JSON file for processing.")
    
    return []


def update_ffiom_db(players_json_path, season="2025-26"):
    """Update FFIOM-DB with scraped player data."""
    
    if not os.path.exists(players_json_path):
        print(f"ERROR: Players JSON not found: {players_json_path}")
        return False
    
    with open(players_json_path) as f:
        players = json.load(f)
    
    print(f"Loaded {len(players)} players from {players_json_path}")
    
    # Filter to Premier League teams
    premier_players = [p for p in players if p.get("team") in VALID_TEAMS]
    print(f"Premier League players: {len(premier_players)}")
    
    # Update FFIOM-DB
    conn = sqlite3.connect(FFIOM_DB_PATH)
    conn.execute("PRAGMA foreign_keys=OFF")
    cur = conn.cursor()
    
    # Clear existing season data
    cur.execute("DELETE FROM historical_stats WHERE season = ?", (season,))
    cur.execute("DELETE FROM player_seasons WHERE season = ?", (season,))
    conn.commit()
    
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
            cur.execute(
                "UPDATE players SET name = ?, team = ?, updated_at = ? WHERE fa_id = ?",
                (name, team, datetime.now().isoformat(), fa_id),
            )
        else:
            cur.execute(
                "INSERT INTO players (fa_id, name, team, position, is_active) VALUES (?, ?, ?, ?, 1)",
                (fa_id, name, team, None),
            )
        
        # Insert season stats
        cur.execute(
            "INSERT OR REPLACE INTO player_seasons "
            "(fa_id, season, team, goals, assists, appearances, yellows, reds, minutes_played) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fa_id, season, team, goals, assists, appearances, yellows, reds, appearances * 90),
        )
        inserted += 1
    
    conn.commit()
    print(f"Inserted/updated {inserted} players")
    conn.close()
    return True


def main():
    parser = argparse.ArgumentParser(description="Scrape FullTime website and update FFIOM-DB")
    parser.add_argument(
        "--action", 
        choices=["results", "players", "update", "all"],
        default="all",
        help="Action to perform (default: all)"
    )
    parser.add_argument(
        "--season", default="2025-26", help="Season to update"
    )
    parser.add_argument(
        "--players-json", 
        default="data/fulltime_premier_players.json",
        help="Path to scraped players JSON"
    )
    parser.add_argument(
        "--results-json",
        default="data/scraper_results.json",
        help="Path to scraped results JSON"
    )
    args = parser.parse_args()
    
    if args.action in ["players", "all"]:
        print("=== Player Scraping ===")
        print("Note: Player scraping requires browser tools.")
        print("Use browser_navigate to stat leaders page, then browser_console to extract data.")
        print(f"Save extracted data to {args.players_json}")
        print()
    
    if args.action in ["results", "all"]:
        print("=== Results Scraping ===")
        print("Note: Results scraping requires browser tools.")
        print("Use browser_navigate to results page, then browser_console to extract data.")
        print(f"Save extracted data to {args.results_json}")
        print()
    
    if args.action in ["update", "all"]:
        if os.path.exists(args.players_json):
            print("=== Updating FFIOM-DB ===")
            update_ffiom_db(args.players_json, args.season)
        else:
            print(f"Skipping update: {args.players_json} not found")


if __name__ == "__main__":
    main()

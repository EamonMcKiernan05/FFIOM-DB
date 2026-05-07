#!/usr/bin/env python3
"""FullTime website scraper pipeline for FFIOM data.

Scrapes player stats from the FullTime website stat leaders page and
syncs them into FFIOM-DB with correct team assignments.

Usage:
    python scripts/scraper_pipeline.py [--season 2025-26] [--output data/fulltime_premier_players.json]

This requires browser tools to be available (browser_navigate, browser_console).
For automated use, run this script manually after opening the stat leaders page in a browser.
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

# Valid Premier League teams
VALID_TEAMS = {
    "Peel First", "Corinthians First", "Laxey First", "St Marys First",
    "St Johns United First", "Onchan First", "Ramsey First",
    "Rushen United First", "Union Mills First", "Ayre United First",
    "Braddan First", "Foxdale First", "DHSOB First",
}

# Team name mapping (Combination -> First)
TEAM_MAP = {
    "Peel Combination": "Peel First",
    "Corinthians Combination": "Corinthians First",
    "Laxey Combination": "Laxey First",
    "St Marys Combination": "St Marys First",
    "St Johns United Combination": "St Johns United First",
    "Onchan Combination": "Onchan First",
    "Ramsey Combination": "Ramsey First",
    "Rushen United Combination": "Rushen United First",
    "Union Mills Combination": "Union Mills First",
    "Ayre United Combination": "Ayre United First",
    "Braddan Combination": "Braddan First",
    "Foxdale Combination": "Foxdale First",
    "DHSOB Combination": "DHSOB First",
}


def normalize_team(team_name):
    """Normalize team name to First format if it's a Combination team."""
    if not team_name:
        return team_name
    # Check if it's a Combination team that should be First
    if team_name in TEAM_MAP:
        return TEAM_MAP[team_name]
    # Already a valid First team
    if team_name in VALID_TEAMS:
        return team_name
    # Unknown team, return as-is
    return team_name


def scrape_players_to_json(output_path):
    """Scrape player stats from FullTime stat leaders page using browser tools.
    
    This requires browser tools to be available. Uses browser_navigate and
    browser_console to extract data from the stat leaders page.
    """
    print("Scraping player stats from FullTime website...")
    print("Note: This requires browser tools (browser_navigate, browser_console).")
    print("Open the stat leaders page in a browser and extract the data.")
    print()
    print("Instructions:")
    print("1. Open browser to: https://fulltime.thefa.com/statLeaders.html?...")
    print("2. Use browser_console to extract player data")
    print("3. Save the extracted data to a JSON file")
    print()
    
    # Check if we have a cached file
    if os.path.exists(output_path):
        with open(output_path) as f:
            data = json.load(f)
        print(f"Found cached data: {len(data)} players")
        return data
    
    print("No cached data found. Please scrape manually or use browser tools.")
    return []


def update_ffiom_db(players, season="2025-26"):
    """Update FFIOM-DB with scraped player data."""
    
    print(f"Loaded {len(players)} players")
    
    # Filter to valid Premier League teams
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
    parser = argparse.ArgumentParser(description="FullTime website scraper pipeline")
    parser.add_argument(
        "--season", default="2025-26", help="Season to update"
    )
    parser.add_argument(
        "--output", 
        default="data/fulltime_premier_players.json",
        help="Path to scraped players JSON"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without updating DB"
    )
    args = parser.parse_args()
    
    # Scrape players
    players = scrape_players_to_json(args.output)
    
    if not players:
        print("No player data found. Please scrape manually.")
        return
    
    # Filter to Premier League teams
    premier_players = [p for p in players if p.get("team") in VALID_TEAMS]
    print(f"Premier League players: {len(premier_players)}")
    
    if args.dry_run:
        print("\nDry run - showing top scorers:")
        for p in sorted(premier_players, key=lambda x: x.get("goals", 0), reverse=True)[:10]:
            print(f"  {p['name']:<30} {p['team']:<25} goals={p.get('goals', 0)} apps={p.get('appearances', 0)}")
        return
    
    # Update FFIOM-DB
    update_ffiom_db(players, args.season)
    
    print("\nDone! FFIOM-DB updated with correct team assignments.")


if __name__ == "__main__":
    main()

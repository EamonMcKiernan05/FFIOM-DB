#!/usr/bin/env python3
"""Scrape player stats from FullTime website.

Usage:
    python scripts/scrape_fulltime_stats.py [--season 2025-26] [--output data/fulltime_premier_players.json]
"""

import argparse
import json
import os
import subprocess
import sys
import time

# FullTime website URL for Premier League player stats
STATS_URL = "https://fulltime.thefa.com/statLeaders.html?itemsPerPage=100&selectedDivision=175685803&selectedOrgStatRecordingTypeID_ForSort=8359803&teamID=&selectedStatisticDisplayMode=3&selectedSeason=804198730&selectedFixtureGroupAgeGroup=0"

# Premier League team name mapping (Combination -> First)
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

# Valid Premier League teams
VALID_TEAMS = {
    "Peel First", "Corinthians First", "Laxey First", "St Marys First",
    "St Johns United First", "Onchan First", "Ramsey First",
    "Rushen United First", "Union Mills First", "Ayre United First",
    "Braddan First", "Foxdale First", "DHSOB First",
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


def scrape_players():
    """Use browser to scrape player stats from FullTime website."""
    print(f"Scraping player stats from FullTime website...")
    print(f"URL: {STATS_URL}")

    # Use browser tools to navigate and extract data
    # This script will be run from the FFIOM-DB directory
    os.chdir('/home/eamon/FFIOM-DB')

    # Use the browser to navigate and extract table data
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Setup headless Chrome
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')

    try:
        driver = webdriver.Chrome(options=options)
        driver.get(STATS_URL)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
        time.sleep(2)  # Wait for table to load

        # Extract table data
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        print(f"Found {len(rows)} rows in table")

        players = []
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 10:
                continue

            # Extract data from cells
            # Column mapping based on FullTime stat leaders table
            try:
                player = {
                    "name": cells[1].text.strip(),
                    "team": cells[2].text.strip(),
                    "appearances": int(cells[3].text.strip() or "0"),
                    "goals": int(cells[5].text.strip() or "0"),
                    "assists": int(cells[7].text.strip() or "0"),
                    "yellows": int(cells[8].text.strip() or "0"),
                    "reds": int(cells[9].text.strip() or "0"),
                }
                players.append(player)
            except (ValueError, IndexError) as e:
                print(f"Skipping row: {e}")
                continue

        # Filter to Premier League teams only and 3+ appearances
        premier_players = []
        for p in players:
            team = normalize_team(p["team"])
            if team in VALID_TEAMS and p["appearances"] >= 3:
                p["team"] = team
                premier_players.append(p)

        print(f"Total players scraped: {len(players)}")
        print(f"Premier League players (3+ apps): {len(premier_players)}")

        # Sort by goals
        premier_players.sort(key=lambda x: x["goals"], reverse=True)

        # Print top scorers
        print("\nTop 20 Premier League scorers:")
        for p in premier_players[:20]:
            print(f"  {p['name']:<30} {p['team']:<25} goals={p['goals']} apps={p['appearances']}")

        driver.quit()
        return premier_players

    except ImportError:
        print("Selenium not installed. Trying alternative approach...")
        # Fallback: use the cached data with team corrections
        return fallback_scrape()


def fallback_scrape():
    """Fallback: use cached data with team corrections."""
    cache_path = '/home/eamon/Fantasy-Football-Isle-of-Man/data/player_stats_cache.json'
    if not os.path.exists(cache_path):
        print(f"Cache file not found: {cache_path}")
        return []

    with open(cache_path) as f:
        stats = json.load(f)

    premier_players = []
    for fa_id, s in stats.items():
        team = normalize_team(s.get("team", ""))
        if team in VALID_TEAMS and s.get("appearances", 0) >= 3:
            premier_players.append({
                "fa_id": fa_id,
                "name": s.get("name", ""),
                "team": team,
                "appearances": s.get("appearances", 0),
                "goals": s.get("goals", 0),
                "assists": s.get("assists", 0),
                "yellows": s.get("yellows", 0),
                "reds": s.get("reds", 0),
            })

    premier_players.sort(key=lambda x: x["goals"], reverse=True)
    print(f"Fallback: {len(premier_players)} Premier League players")
    return premier_players


def main():
    parser = argparse.ArgumentParser(description="Scrape FullTime player stats")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--output", default="data/fulltime_premier_players.json")
    args = parser.parse_args()

    players = scrape_players()

    if players:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, 'w') as f:
            json.dump(players, f, indent=2)
        print(f"\nSaved {len(players)} players to {args.output}")
    else:
        print("No players scraped!")
        sys.exit(1)


if __name__ == "__main__":
    main()

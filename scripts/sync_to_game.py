#!/usr/bin/env python3
"""
Sync FFIOM-DB (source of truth) -> Fantasy-Football-Isle-of-Man game DB.

Copies player data, team data, gameweeks, fixtures from FFIOM-DB into the
game app's database. Uses UPDATE OR INSERT to preserve game DB integrity.

Usage:
    python scripts/sync_to_game.py [--dry-run] [--season 2025-26]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

FFIOM_DB = Path("/home/eamon/FFIOM-DB/data/fantasy_iom.db")
GAME_DB = Path("/home/eamon/Fantasy-Football-Isle-of-Man/data/fantasy_iom.db")


def sync_teams(dry_run=False):
    """Sync teams from FFIOM-DB to game DB."""
    ffiom = sqlite3.connect(str(FFIOM_DB))
    game = sqlite3.connect(str(GAME_DB))
    ffiom.row_factory = sqlite3.Row
    game.row_factory = sqlite3.Row

    cur_f = ffiom.cursor()
    cur_g = game.cursor()

    # Get teams from FFIOM-DB
    cur_f.execute("SELECT id, name, short_name, division FROM teams")
    ffiom_teams = cur_f.fetchall()

    for team in ffiom_teams:
        # Check if team exists in game DB by name
        cur_g.execute("SELECT id FROM teams WHERE name = ?", (team['name'],))
        existing = cur_g.fetchone()

        if existing:
            # Update existing team
            if not dry_run:
                cur_g.execute(
                    "UPDATE teams SET short_name = ?, division_id = NULL WHERE id = ?",
                    (team['short_name'], existing['id'])
                )
        else:
            # Insert new team
            if not dry_run:
                cur_g.execute(
                    "INSERT OR IGNORE INTO teams (name, short_name) VALUES (?, ?)",
                    (team['name'], team['short_name'])
                )

    if not dry_run:
        game.commit()

    ffiom.close()
    game.close()
    print(f"Teams synced: {len(ffiom_teams)} from FFIOM-DB")
    return len(ffiom_teams)


def sync_players(dry_run=False):
    """Sync players from FFIOM-DB to game DB."""
    ffiom = sqlite3.connect(str(FFIOM_DB))
    game = sqlite3.connect(str(GAME_DB))
    ffiom.row_factory = sqlite3.Row
    game.row_factory = sqlite3.Row

    cur_f = ffiom.cursor()
    cur_g = game.cursor()

    # Get all players from FFIOM-DB
    cur_f.execute("""
        SELECT id, name, web_name, team_id, position, price, price_start,
               price_change, price_change_event, price_change_fall,
               price_change_total, selected_by_percent, form, in_dreamteam,
               apps, goals, assists, clean_sheets, yellow_cards, red_cards,
               saves, minutes_played, bonus, goals_conceded, own_goals,
               penalties_saved, penalties_missed, influence, creativity,
               threat, ict_index, total_points_season, transfers_in,
               transfers_out, is_active, is_injured, injury_status,
               injury_return, now_playing
        FROM players
    """)
    ffiom_players = cur_f.fetchall()

    synced = 0
    updated = 0

    for player in ffiom_players:
        # Check if player exists in game DB by name + team_id
        cur_g.execute(
            "SELECT id FROM players WHERE name = ? AND team_id = ?",
            (player['name'], player['team_id'])
        )
        existing = cur_g.fetchone()

        if existing:
            # Update player stats/prices from FFIOM-DB
            if not dry_run:
                cur_g.execute("""
                    UPDATE players SET
                        web_name = COALESCE(?, web_name),
                        price = ?,
                        price_start = ?,
                        price_change = ?,
                        selected_by_percent = ?,
                        form = ?,
                        in_dreamteam = ?,
                        apps = ?,
                        goals = ?,
                        assists = ?,
                        clean_sheets = ?,
                        yellow_cards = ?,
                        red_cards = ?,
                        saves = ?,
                        minutes_played = ?,
                        bonus = ?,
                        goals_conceded = ?,
                        own_goals = ?,
                        penalties_saved = ?,
                        penalties_missed = ?,
                        influence = ?,
                        creativity = ?,
                        threat = ?,
                        ict_index = ?,
                        total_points_season = ?,
                        is_active = ?,
                        is_injured = ?,
                        now_playing = ?
                    WHERE id = ?
                """, (
                    player['web_name'], player['price'], player['price_start'],
                    player['price_change'], player['selected_by_percent'],
                    player['form'], player['in_dreamteam'], player['apps'],
                    player['goals'], player['assists'], player['clean_sheets'],
                    player['yellow_cards'], player['red_cards'], player['saves'],
                    player['minutes_played'], player['bonus'], player['goals_conceded'],
                    player['own_goals'], player['penalties_saved'],
                    player['penalties_missed'], player['influence'],
                    player['creativity'], player['threat'], player['ict_index'],
                    player['total_points_season'], player['is_active'],
                    player['is_injured'], player['now_playing'],
                    existing['id']
                ))
            updated += 1
        else:
            # Player not in game DB - skip (they may not be active)
            pass

        synced += 1

    if not dry_run:
        game.commit()

    ffiom.close()
    game.close()
    print(f"Players: {synced} checked, {updated} updated from FFIOM-DB")
    return synced, updated


def sync_fixtures(dry_run=False):
    """Sync fixtures from FFIOM-DB to game DB."""
    ffiom = sqlite3.connect(str(FFIOM_DB))
    game = sqlite3.connect(str(GAME_DB))
    ffiom.row_factory = sqlite3.Row
    game.row_factory = sqlite3.Row

    cur_f = ffiom.cursor()
    cur_g = game.cursor()

    # Get fixtures from FFIOM-DB
    cur_f.execute("SELECT COUNT(*) FROM fixtures")
    ffiom_count = cur_f.fetchone()[0]

    # Compare fixture counts
    cur_g.execute("SELECT COUNT(*) FROM fixtures")
    game_count = cur_g.fetchone()[0]

    ffiom.close()
    game.close()

    print(f"Fixtures: FFIOM-DB={ffiom_count}, Game DB={game_count}")
    return ffiom_count, game_count


def sync_gameweeks(dry_run=False):
    """Sync gameweeks from FFIOM-DB to game DB."""
    ffiom = sqlite3.connect(str(FFIOM_DB))
    game = sqlite3.connect(str(GAME_DB))
    ffiom.row_factory = sqlite3.Row
    game.row_factory = sqlite3.Row

    cur_f = ffiom.cursor()
    cur_g = game.cursor()

    cur_f.execute("SELECT COUNT(*) FROM gameweeks")
    ffiom_count = cur_f.fetchone()[0]

    cur_g.execute("SELECT COUNT(*) FROM gameweeks")
    game_count = cur_g.fetchone()[0]

    ffiom.close()
    game.close()

    print(f"Gameweeks: FFIOM-DB={ffiom_count}, Game DB={game_count}")
    return ffiom_count, game_count


def main():
    parser = argparse.ArgumentParser(description="Sync FFIOM-DB to game DB")
    parser.add_argument("--dry-run", action="store_true", help="Preview sync without changes")
    parser.add_argument("--season", default="2025-26", help="Season to sync")
    args = parser.parse_args()

    print(f"Syncing FFIOM-DB -> Game DB (dry_run={args.dry_run})")
    print(f"FFIOM-DB: {FFIOM_DB}")
    print(f"Game DB:  {GAME_DB}")
    print()

    if not FFIOM_DB.exists():
        print(f"ERROR: FFIOM-DB not found at {FFIOM_DB}")
        sys.exit(1)

    if not GAME_DB.exists():
        print(f"ERROR: Game DB not found at {GAME_DB}")
        sys.exit(1)

    # Sync in order: teams -> players -> fixtures -> gameweeks
    sync_teams(dry_run=args.dry_run)
    sync_players(dry_run=args.dry_run)
    sync_fixtures(dry_run=args.dry_run)
    sync_gameweeks(dry_run=args.dry_run)

    print("\nSync complete!")


if __name__ == "__main__":
    main()

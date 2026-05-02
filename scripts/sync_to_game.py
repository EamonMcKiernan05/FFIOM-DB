#!/usr/bin/env python3
"""Sync FFIOM-DB player registry into the Fantasy Football IOM game database.

Usage:
    python scripts/sync_to_game.py [--season 2025-26] [--dry-run] [--clear-players]

This reads from FFIOM-DB (the source of truth) and syncs players into the
game's SQLAlchemy Player model using INSERT OR UPDATE logic keyed on name.
"""

import argparse
import os
import sys

# Paths
FFIOM_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fantasy_iom.db"
)
GAME_ROOT = os.environ.get(
    "FFIOM_GAME_ROOT", "/home/eamon/Fantasy-Football-Isle-of-Man"
)
GAME_DATABASE_URL = "sqlite:///./data/fantasy_iom.db"

import sqlite3


def load_game_models():
    """Import game models from the Fantasy Football IOM project."""
    sys.path.insert(0, GAME_ROOT)
    os.chdir(GAME_ROOT)
    os.environ["DATABASE_URL"] = GAME_DATABASE_URL

    from app.database import SessionLocal
    from app.models import Player, Team

    return SessionLocal, Player, Team


def get_team_by_name(db, Team, team_name):
    """Find a game Team by name."""
    return db.query(Team).filter(Team.name == team_name).first()


def normalize_team_name(name):
    """Map FFIOM-DB team names to game team names."""
    if not name:
        return None
    mapping = {
        "Peel First": "Peel",
        "Corinthians First": "Corinthians",
        "Laxey First": "Laxey",
        "St Marys First": "St Marys",
        "St Johns United First": "St Johns",
        "Onchan First": "Onchan",
        "Ramsey First": "Ramsey",
        "Rushen United First": "Rushen United",
        "Union Mills First": "Union Mills",
        "Ayre United First": "Ayre United",
        "Braddan First": "Braddan",
        "Foxdale First": "Foxdale",
        "DHSOB First": "DHSOB",
        "Peel Combination": "Peel Combination",
        "Douglas Rangers": "Douglas Rangers",
    }
    if name in mapping:
        return mapping[name]
    cleaned = name.replace(" First", "").strip()
    if cleaned in mapping:
        return mapping[cleaned]
    return name


def estimate_price(goals, apps, assists, position):
    """Estimate FPL-style player price based on stats."""
    base = 4.5
    base += goals * 0.4
    base += assists * 0.3
    base += (apps / 20.0) * 0.5
    if position == "GK":
        base += 0.2
    elif position == "FWD":
        base += 0.3
    elif position == "MID":
        base += 0.2
    return max(4.0, min(10.0, round(base, 1)))


def sync_players(ffiom_conn, game_db, Player, Team, season="2025-26",
                 dry_run=False, clear_players=False):
    """Sync players from FFIOM-DB into the game database."""

    cursor = ffiom_conn.execute(
        """
        SELECT p.fa_id, p.name, ps.team, p.position, ps.goals, ps.assists,
               ps.appearances, ps.yellows, ps.reds, ps.clean_sheets, ps.saves,
               ps.minutes_played, ps.bonus, ps.goals_conceded, ps.own_goals,
               ps.penalties_saved, ps.penalties_missed, ps.influence,
               ps.creativity, ps.threat, ps.ict_index, ps.total_points, ps.form
        FROM players p
        JOIN player_seasons ps ON p.fa_id = ps.fa_id
        WHERE ps.season = ? AND ps.appearances >= 3
        ORDER BY p.name
        """,
        (season,),
    )
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    game_teams = {t.name: t for t in game_db.query(Team).all()}

    existing_players = {}
    for p in game_db.query(Player).all():
        existing_players[p.name] = p

    added = 0
    updated = 0
    skipped = 0

    if clear_players:
        count = game_db.query(Player).count()
        print(f"Clearing {count} existing players...")
        game_db.query(Player).delete()
        game_db.commit()
        existing_players = {}

    for row in rows:
        data = dict(zip(columns, row))
        fa_id = data["fa_id"]
        name = data["name"]
        raw_team = data["team"]
        position = data["position"]
        goals = data["goals"]
        assists = data["assists"]
        apps = data["appearances"]
        yellows = data["yellows"] or 0
        reds = data["reds"] or 0

        if apps < 3:
            skipped += 1
            continue

        team_name = normalize_team_name(raw_team)
        team = game_teams.get(team_name) if team_name else None

        if not team:
            skipped += 1
            continue

        existing = existing_players.get(name)

        if existing:
            existing.team_id = team.id
            existing.position = position
            existing.goals = goals
            existing.assists = assists
            existing.apps = apps
            existing.yellow_cards = yellows
            existing.red_cards = reds
            existing.clean_sheets = data["clean_sheets"] or 0
            existing.saves = data["saves"] or 0
            existing.minutes_played = data["minutes_played"] or 0
            existing.bonus = data["bonus"] or 0
            existing.goals_conceded = data["goals_conceded"] or 0
            existing.own_goals = data["own_goals"] or 0
            existing.penalties_saved = data["penalties_saved"] or 0
            existing.penalties_missed = data["penalties_missed"] or 0
            existing.influence = data["influence"] or 0.0
            existing.creativity = data["creativity"] or 0.0
            existing.threat = data["threat"] or 0.0
            existing.ict_index = data["ict_index"] or 0.0
            existing.total_points_season = data["total_points"] or 0
            existing.form = data["form"] or 0.0
            existing.price = estimate_price(goals, apps, assists, position)
            updated += 1
        else:
            price = estimate_price(goals, apps, assists, position)
            web_name = name.lower().replace(" ", "_").replace("'", "")

            player = Player(
                name=name,
                web_name=web_name,
                team_id=team.id,
                position=position,
                price=price,
                price_start=price,
                goals=goals,
                assists=assists,
                apps=apps,
                yellow_cards=yellows,
                red_cards=reds,
                clean_sheets=data["clean_sheets"] or 0,
                saves=data["saves"] or 0,
                minutes_played=data["minutes_played"] or 0,
                bonus=data["bonus"] or 0,
                goals_conceded=data["goals_conceded"] or 0,
                own_goals=data["own_goals"] or 0,
                penalties_saved=data["penalties_saved"] or 0,
                penalties_missed=data["penalties_missed"] or 0,
                influence=data["influence"] or 0.0,
                creativity=data["creativity"] or 0.0,
                threat=data["threat"] or 0.0,
                ict_index=data["ict_index"] or 0.0,
                total_points_season=data["total_points"] or 0,
                form=data["form"] or 0.0,
                is_active=True,
            )
            game_db.add(player)
            added += 1

    if dry_run:
        print(f"\n[Dry run] Would add {added}, update {updated}, skip {skipped}")
    else:
        game_db.commit()
        print(f"\nSync complete:")
        print(f"  Added:   {added}")
        print(f"  Updated: {updated}")
        print(f"  Skipped: {skipped}")

    return added, updated, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Sync FFIOM-DB into Fantasy Football IOM game"
    )
    parser.add_argument(
        "--season", default="2025-26", help="Season to sync (default: 2025-26)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without making changes"
    )
    parser.add_argument(
        "--clear-players", action="store_true",
        help="Clear existing players before syncing (use with caution)"
    )
    args = parser.parse_args()

    if not os.path.exists(FFIOM_DB_PATH):
        print(f"ERROR: FFIOM-DB not found at {FFIOM_DB_PATH}")
        print("Run: python scripts/init_db.py && python scripts/import_real_data.py")
        sys.exit(1)

    print(f"Opening FFIOM-DB: {FFIOM_DB_PATH}")
    ffiom_conn = sqlite3.connect(FFIOM_DB_PATH)

    SessionLocal, Player, Team = load_game_models()
    game_db = SessionLocal()

    try:
        sync_players(
            ffiom_conn, game_db, Player, Team,
            season=args.season, dry_run=args.dry_run,
            clear_players=args.clear_players,
        )

        print(f"\nGame database state:")
        print(f"  Teams:   {game_db.query(Team).count()}")
        print(f"  Players: {game_db.query(Player).count()}")
    finally:
        game_db.close()
        ffiom_conn.close()


if __name__ == "__main__":
    main()

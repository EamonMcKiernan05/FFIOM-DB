#!/usr/bin/env python3
"""Calculate player point totals retrospectively from fixture results.

This script goes through ALL played fixtures and calculates FFIOM fantasy points
for every player based on fixture data (NOT pre-computed player stats).

Approach:
- For each gameweek, process all played fixtures
- For each fixture, get players on both teams (from player_seasons)
- Distribute team goals among players using season goal ratios
- Estimate clean sheets, cards, minutes from fixture results
- Calculate FFIOM fantasy points per the scoring rules
- Store in historical_stats table

Scoring rules:
- Goal: +4
- Penalty goal: +2
- Clean sheet: +3
- 60+ min: +2, 1-59 min: +1
- Saves: +1 per 3 saves
- Penalty save: +5
- Yellow card: -1
- Red card: -3
- Own goal: -2
- Penalties missed: -2 each
- Defensive contributions (10+): +2
- Goals conceded: -1 per 2 conceded
- Bonus points (BPS): top players per GW

Usage:
    python scripts/calculate_retrospective_points.py [--season 2025-26] [--clear] [--dry-run]
"""

import argparse
import os
import sys
import sqlite3
import math
import random
from datetime import datetime

# Paths
FFIOM_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "fantasy_iom.db",
)

# Scoring constants
GOAL_POINTS = 4
PENALTY_GOAL_BONUS = 2
CLEAN_SHEET_POINTS = 3
MINUTES_60_PLUS = 2
MINUTES_UNDER_60 = 1
YELLOW_CARD_POINTS = -1
RED_CARD_POINTS = -3
OWN_GOAL_POINTS = -2
PENALTY_MISSED_POINTS = -2
PENALTY_SAVE_POINTS = 5
SAVES_PER_POINT = 3
DEFENSIVE_CONTRIBUTION_THRESHOLD = 10
DEFENSIVE_CONTRIBUTION_POINTS = 2
GOALS_CONCEDED_PER_PENALTY = 2


def calculate_player_points(
    goals_scored=0,
    assists=0,
    clean_sheet=False,
    yellow_card=False,
    red_card=False,
    own_goal=False,
    minutes_played=0,
    saves=0,
    penalties_saved=0,
    penalties_missed=0,
    was_penalty_goal=False,
    defensive_contributions=0,
    goals_conceded=0,
    bonus_points=0,
):
    """Calculate FFIOM fantasy points for a player in one gameweek."""
    points = 0

    # Minutes played
    if minutes_played >= 60:
        points += MINUTES_60_PLUS
    elif minutes_played >= 1:
        points += MINUTES_UNDER_60

    # Goals
    points += goals_scored * GOAL_POINTS

    # Penalty goal bonus
    if was_penalty_goal:
        points += PENALTY_GOAL_BONUS

    # Clean sheet
    if clean_sheet:
        points += CLEAN_SHEET_POINTS

    # Saves (GK)
    points += saves // SAVES_PER_POINT

    # Penalty saves
    points += penalties_saved * PENALTY_SAVE_POINTS

    # Cards
    if yellow_card:
        points += YELLOW_CARD_POINTS
    if red_card:
        points += RED_CARD_POINTS

    # Own goal
    if own_goal:
        points += OWN_GOAL_POINTS

    # Penalties missed
    if penalties_missed:
        points += penalties_missed * PENALTY_MISSED_POINTS

    # Defensive contributions
    if defensive_contributions >= DEFENSIVE_CONTRIBUTION_THRESHOLD:
        points += DEFENSIVE_CONTRIBUTION_POINTS

    # Goals conceded
    points -= goals_conceded // GOALS_CONCEDED_PER_PENALTY

    # Bonus points
    points += bonus_points

    return points


def calculate_bps(
    goals_scored=0,
    assists=0,
    clean_sheet=False,
    saves=0,
    penalties_saved=0,
    yellow_card=False,
    red_card=False,
    goals_conceded=0,
    minutes_played=0,
    tackles=0,
    blocks=0,
    interceptions=0,
    was_penalty_goal=False,
    own_goal=False,
    penalties_missed=0,
    position=None,
):
    """Calculate BPS score for bonus point allocation."""
    bps = 0

    # Minutes played
    if minutes_played > 15:
        bps += (minutes_played - 15) // 15

    # Goals (position-dependent)
    if goals_scored:
        goal_bps = {"FWD": 8, "MID": 10, "DEF": 12, "GK": 16}
        bps += goals_scored * goal_bps.get(position, 8)

    # Penalty goal
    if was_penalty_goal:
        bps += 2

    # Assists
    bps += assists * 8

    # Saves
    bps += saves * 2

    # Penalty saves
    bps += penalties_saved * 15

    # Clean sheet (position-dependent)
    if clean_sheet:
        cs_bps = {"GK": 10, "DEF": 5, "MID": 3}
        bps += cs_bps.get(position, 0)

    # Defensive actions
    bps += tackles + blocks + interceptions

    # Negatives
    bps -= yellow_card * 3
    bps -= red_card * 8
    bps -= own_goal * 4
    bps -= penalties_missed * 10
    bps -= goals_conceded * 2

    return max(0, bps)


def distribute_goals_to_players(team_players, team_goals, season_goals_map, seed):
    """Distribute team goals among the team's players based on season ratios.

    Args:
        team_players: List of dicts with fa_id, season_goals, season_apps
        team_goals: Total goals scored by the team in this fixture
        season_goals_map: {fa_id: season_goals}
        seed: Random seed for reproducibility
    """
    if not team_goals or not team_players:
        return {p["fa_id"]: 0 for p in team_players}

    rng = random.Random(seed)

    # Calculate goal ratios for each player
    total_season_goals = sum(p.get("season_goals", 0) for p in team_players)
    if total_season_goals == 0:
        # If no season goals, distribute evenly
        base = team_goals // len(team_players)
        remainder = team_goals - base * len(team_players)
        goals = {p["fa_id"]: base for p in team_players}
        for i, p in enumerate(team_players[:remainder]):
            goals[p["fa_id"]] += 1
        return goals

    # Distribute proportionally based on season goal ratio
    player_goals = {}
    distributed = 0
    sorted_players = sorted(team_players, key=lambda p: p.get("season_goals", 0), reverse=True)

    for p in sorted_players:
        fa_id = p["fa_id"]
        s_goals = p.get("season_goals", 0)
        ratio = s_goals / total_season_goals
        allocated = round(team_goals * ratio)
        player_goals[fa_id] = min(allocated, team_goals - distributed)
        distributed += player_goals[fa_id]

    # Adjust remainder
    remainder = team_goals - distributed
    if remainder > 0:
        # Give to top scorers
        for p in sorted_players:
            if remainder <= 0:
                break
            player_goals[p["fa_id"]] = player_goals.get(p["fa_id"], 0) + 1
            remainder -= 1
    elif remainder < 0:
        # Take from bottom scorers
        for p in reversed(sorted_players):
            if remainder >= 0:
                break
            player_goals[p["fa_id"]] = max(0, player_goals.get(p["fa_id"], 0) - 1)
            remainder += 1

    return player_goals


def estimate_cards_for_fixture(season_yellows, season_reds, season_apps, fixtures_played):
    """Estimate probability of a card in this fixture based on season rates."""
    if season_apps == 0:
        return False, False

    # Card rate per appearance
    yellow_rate = season_yellows / season_apps if season_apps > 0 else 0
    red_rate = season_reds / season_apps if season_apps > 0 else 0

    # Small probability for each fixture
    return (
        random.random() < min(yellow_rate * 1.5, 0.3),  # Cap at 30%
        random.random() < min(red_rate * 2, 0.05),  # Cap at 5%
    )


def main():
    parser = argparse.ArgumentParser(
        description="Calculate retrospective player points from fixture results"
    )
    parser.add_argument(
        "--season", default="2025-26", help="Season to calculate (default: 2025-26)"
    )
    parser.add_argument(
        "--gw", type=int, default=None, help="Calculate only this gameweek"
    )
    parser.add_argument(
        "--clear", action="store_true", help="Clear existing historical_stats first"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)"
    )
    args = parser.parse_args()

    if not os.path.exists(FFIOM_DB_PATH):
        print(f"ERROR: FFIOM-DB not found at {FFIOM_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(FFIOM_DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ensure tables exist
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import src.schema as schema_module
    schema_module.create_tables(conn)

    # Seed random for reproducibility
    random.seed(args.seed)

    # Load season player data
    players = cur.execute(
        "SELECT p.fa_id, p.name, p.position, ps.team, ps.goals, ps.appearances, "
        "ps.assists, ps.yellows, ps.reds, ps.clean_sheets, ps.saves, "
        "ps.goals_conceded, ps.own_goals, ps.penalties_saved, ps.penalties_missed "
        "FROM players p JOIN player_seasons ps ON p.fa_id = ps.fa_id "
        "WHERE ps.season = ? AND ps.appearances >= 1",
        (args.season,),
    ).fetchall()

    print(f"Season: {args.season}")
    print(f"Players loaded: {len(players)}")

    if not players:
        print("No players found for this season. Run sync_from_api.py first.")
        sys.exit(1)

    # Normalize fixture team names to our canonical names
    # Only Canada Life Premier League teams - discard Combination/other data
    PREMIER_TEAMS = {
        "Peel", "Corinthians", "Laxey", "St Marys", "St Johns", "Onchan",
        "Ramsey", "Rushen United", "Union Mills", "Ayre United", "Braddan",
        "Foxdale", "DHSOB",
    }

    TEAM_NAME_MAP = {
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
    }

    def normalize_team_name(name):
        """Normalize player_seasons team name to match teams table.
        Returns None for non-Premier teams."""
        if not name:
            return None
        if name in TEAM_NAME_MAP:
            return TEAM_NAME_MAP[name]
        cleaned = name.replace(" First", "").replace(" Combination", "").strip()
        if cleaned in PREMIER_TEAMS:
            return cleaned
        return None  # Not a Premier League team

    # Build team -> players lookup (with normalized team names, Premier League only)
    team_players = {}
    for p in players:
        team = normalize_team_name(p["team"])
        if not team:  # Skip non-Premier teams
            continue
        if team not in team_players:
            team_players[team] = []
        team_players[team].append({
            "fa_id": p["fa_id"],
            "name": p["name"],
            "position": p["position"],
            "season_goals": p["goals"] or 0,
            "season_apps": p["appearances"] or 0,
            "season_assists": p["assists"] or 0,
            "season_yellows": p["yellows"] or 0,
            "season_reds": p["reds"] or 0,
            "season_saves": p["saves"] or 0,
            "season_goals_conceded": p["goals_conceded"] or 0,
            "season_own_goals": p["own_goals"] or 0,
            "season_penalties_saved": p["penalties_saved"] or 0,
            "season_penalties_missed": p["penalties_missed"] or 0,
        })

    # Load teams
    teams = cur.execute("SELECT id, name FROM teams").fetchall()
    team_id_to_name = {t["id"]: t["name"] for t in teams}

    # Clear existing stats if requested
    if args.clear:
        cur.execute("DELETE FROM historical_stats")
        conn.commit()
        print("Cleared existing historical_stats")

    # Load gameweeks and fixtures
    gw_query = "SELECT * FROM gameweeks WHERE season = ? AND closed = 1"
    gw_params = (args.season,)

    if args.gw:
        gw_query += " AND number = ?"
        gw_params = gw_params + (args.gw,)

    gameweeks = cur.execute(gw_query, gw_params).fetchall()
    print(f"Gameweeks to process: {len(gameweeks)}")

    total_points = 0
    gw_stats = []

    for gw in gameweeks:
        gw_id = gw["number"]
        gw_db_id = gw["id"]

        # Get fixtures for this gameweek
        fixtures = cur.execute(
            "SELECT * FROM fixtures WHERE gameweek_id = ? AND played = 1",
            (gw_db_id,),
        ).fetchall()

        if not fixtures:
            print(f"  GW {gw_id}: No played fixtures, skipping")
            continue

        print(f"\n  GW {gw_id}: {len(fixtures)} fixtures")

        # Collect all player stats for this GW (for BPS calculation)
        gw_player_entries = []

        for fixture in fixtures:
            fx_seed = hash(f"{gw_id}-{fixture['id']}")

            home_team_id = fixture["home_team_id"]
            away_team_id = fixture["away_team_id"]
            home_score = fixture["home_score"] or 0
            away_score = fixture["away_score"] or 0

            home_team_name = team_id_to_name.get(home_team_id, fixture["home_team_name"])
            away_team_name = team_id_to_name.get(away_team_id, fixture["away_team_name"])

            if not home_team_name or not away_team_name:
                continue

            home_players_list = team_players.get(home_team_name, [])
            away_players_list = team_players.get(away_team_name, [])

            # Determine which players actually play this fixture
            # Use season appearances as a guide - players with high app counts play most GWs
            seed_val = fx_seed + 1000
            home_played = [p for p in home_players_list
                          if random.Random(seed_val + hash(p["fa_id"])).random() <
                             min(p["season_apps"] / 20.0, 0.9)]
            away_played = [p for p in away_players_list
                          if random.Random(seed_val + hash(p["fa_id"]) + 1).random() <
                             min(p["season_apps"] / 20.0, 0.9)]

            if not home_played:
                home_played = home_players_list[:10] if home_players_list else []
            if not away_played:
                away_played = away_players_list[:10] if away_players_list else []

            # Distribute goals
            home_goals = distribute_goals_to_players(
                home_played, home_score, {}, fx_seed + 2000
            )
            away_goals = distribute_goals_to_players(
                away_played, away_score, {}, fx_seed + 3000
            )

            # Clean sheet determination
            home_clean_sheet = (away_score == 0)
            away_clean_sheet = (home_score == 0)

            # Process home team players
            for p in home_played:
                fa_id = p["fa_id"]
                pos = p["position"] or "MID"

                # Minutes played (GK and defenders tend to play full games)
                min_seed = fx_seed + hash(fa_id) + 4000
                if pos in ("GK", "DEF"):
                    minutes = 90
                elif random.Random(min_seed).random() < 0.7:
                    minutes = 90
                else:
                    minutes = random.Random(min_seed).randint(30, 75)

                player_goals = home_goals.get(fa_id, 0)

                # Cards
                card_seed = fx_seed + hash(fa_id) + 5000
                yellow_prob = p["season_yellows"] / max(p["season_apps"], 1)
                red_prob = p["season_reds"] / max(p["season_apps"], 1)
                yellow = random.Random(card_seed).random() < min(yellow_prob, 0.25)
                red = random.Random(card_seed + 1).random() < min(red_prob, 0.03)

                # GK saves
                saves = 0
                if pos == "GK":
                    # Estimate saves based on goals conceded
                    saves = max(2, away_score + random.randint(1, 4))

                # Penalty detection (top scorers more likely)
                was_penalty = False
                if player_goals > 0 and p["season_goals"] > 5:
                    was_penalty = random.Random(fx_seed + hash(fa_id) + 6000).random() < 0.2

                # Defensive contributions estimate
                def_contributions = 0
                if pos in ("DEF", "GK"):
                    def_contributions = random.randint(5, 15)
                elif pos == "MID":
                    def_contributions = random.randint(2, 10)

                # Own goal
                own_goal = False
                if random.Random(fx_seed + hash(fa_id) + 7000).random() < 0.01:
                    own_goal = True

                # Calculate points
                base_pts = calculate_player_points(
                    goals_scored=player_goals,
                    clean_sheet=home_clean_sheet,
                    yellow_card=yellow,
                    red_card=red,
                    own_goal=own_goal,
                    minutes_played=minutes,
                    saves=saves,
                    was_penalty_goal=was_penalty,
                    defensive_contributions=def_contributions,
                    goals_conceded=away_score,
                )

                # BPS
                bps = calculate_bps(
                    goals_scored=player_goals,
                    clean_sheet=home_clean_sheet,
                    saves=saves,
                    yellow_card=yellow,
                    red_card=red,
                    goals_conceded=away_score,
                    minutes_played=minutes,
                    was_penalty_goal=was_penalty,
                    own_goal=own_goal,
                    position=pos,
                )

                gw_player_entries.append({
                    "fa_id": fa_id,
                    "name": p["name"],
                    "position": pos,
                    "base_points": base_pts,
                    "bps": bps,
                    "minutes": minutes,
                    "goals": player_goals,
                    "clean_sheet": home_clean_sheet,
                    "goals_conceded": away_score,
                    "saves": saves,
                    "yellow": yellow,
                    "red": red,
                    "was_home": True,
                    "opponent": away_team_name,
                })

            # Process away team players
            for p in away_played:
                fa_id = p["fa_id"]
                pos = p["position"] or "MID"

                min_seed = fx_seed + hash(fa_id) + 8000
                if pos in ("GK", "DEF"):
                    minutes = 90
                elif random.Random(min_seed).random() < 0.7:
                    minutes = 90
                else:
                    minutes = random.Random(min_seed).randint(30, 75)

                player_goals = away_goals.get(fa_id, 0)

                card_seed = fx_seed + hash(fa_id) + 9000
                yellow_prob = p["season_yellows"] / max(p["season_apps"], 1)
                red_prob = p["season_reds"] / max(p["season_apps"], 1)
                yellow = random.Random(card_seed).random() < min(yellow_prob, 0.25)
                red = random.Random(card_seed + 1).random() < min(red_prob, 0.03)

                saves = 0
                if pos == "GK":
                    saves = max(2, home_score + random.randint(1, 4))

                was_penalty = False
                if player_goals > 0 and p["season_goals"] > 5:
                    was_penalty = random.Random(fx_seed + hash(fa_id) + 10000).random() < 0.2

                def_contributions = 0
                if pos in ("DEF", "GK"):
                    def_contributions = random.randint(5, 15)
                elif pos == "MID":
                    def_contributions = random.randint(2, 10)

                own_goal = False
                if random.Random(fx_seed + hash(fa_id) + 11000).random() < 0.01:
                    own_goal = True

                base_pts = calculate_player_points(
                    goals_scored=player_goals,
                    clean_sheet=away_clean_sheet,
                    yellow_card=yellow,
                    red_card=red,
                    own_goal=own_goal,
                    minutes_played=minutes,
                    saves=saves,
                    was_penalty_goal=was_penalty,
                    defensive_contributions=def_contributions,
                    goals_conceded=home_score,
                )

                bps = calculate_bps(
                    goals_scored=player_goals,
                    clean_sheet=away_clean_sheet,
                    saves=saves,
                    yellow_card=yellow,
                    red_card=red,
                    goals_conceded=home_score,
                    minutes_played=minutes,
                    was_penalty_goal=was_penalty,
                    own_goal=own_goal,
                    position=pos,
                )

                gw_player_entries.append({
                    "fa_id": fa_id,
                    "name": p["name"],
                    "position": pos,
                    "base_points": base_pts,
                    "bps": bps,
                    "minutes": minutes,
                    "goals": player_goals,
                    "clean_sheet": away_clean_sheet,
                    "goals_conceded": home_score,
                    "saves": saves,
                    "yellow": yellow,
                    "red": red,
                    "was_home": False,
                    "opponent": home_team_name,
                })

        # Award bonus points: top 3 by BPS get 3, 2, 1
        gw_player_entries.sort(key=lambda x: x["bps"], reverse=True)
        for i, entry in enumerate(gw_player_entries[:3]):
            entry["bonus_points"] = 3 - i
            entry["total_points"] = entry["base_points"] + entry["bonus_points"]
        for entry in gw_player_entries[3:]:
            entry["bonus_points"] = 0
            entry["total_points"] = entry["base_points"]

        # Write to historical_stats
        if not args.dry_run:
            for entry in gw_player_entries:
                cur.execute(
                    "INSERT OR REPLACE INTO historical_stats "
                    "(fa_id, season, gameweek, opponent, was_home, minutes_played, "
                    "goals_scored, assists, clean_sheet, goals_conceded, saves, "
                    "yellow_card, red_card, own_goal, bonus_points, base_points, total_points) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        entry["fa_id"],
                        args.season,
                        gw_id,
                        entry["opponent"],
                        entry["was_home"],
                        entry["minutes"],
                        entry["goals"],
                        0,  # assists (estimated 0 from fixture data)
                        entry["clean_sheet"],
                        entry["goals_conceded"],
                        entry["saves"],
                        entry["yellow"],
                        entry["red"],
                        entry.get("own_goal", False),
                        entry["bonus_points"],
                        entry["base_points"],
                        entry["total_points"],
                    ),
                )
            conn.commit()

        # Stats
        gw_total = sum(e["total_points"] for e in gw_player_entries)
        gw_points = len(gw_player_entries)
        top_scorer = max(gw_player_entries, key=lambda x: x["total_points"])
        print(f"    {gw_points} players scored, total GW points: {gw_total}")
        print(f"    Top scorer: {top_scorer['name']} ({top_scorer['total_points']} pts)")

        total_points += gw_total
        gw_stats.append({
            "gw": gw_id,
            "players": gw_points,
            "total": gw_total,
            "top_scorer": top_scorer["name"],
            "top_pts": top_scorer["total_points"],
        })

    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"Season: {args.season}")
    print(f"Gameweeks processed: {len(gw_stats)}")
    print(f"Total player-GW entries: {sum(s['players'] for s in gw_stats)}")
    print(f"Total points awarded: {total_points}")

    for s in gw_stats:
        print(f"  GW {s['gw']}: {s['players']} players, {s['total']} pts "
              f"(top: {s['top_scorer']} {s['top_pts']}pts)")

    if not args.dry_run:
        # Update season totals in player_seasons
        for p in players:
            fa_id = p["fa_id"]
            result = cur.execute(
                "SELECT SUM(total_points) as total, "
                "SUM(goals_scored) as goals, "
                "COUNT(*) as gw_count, "
                "AVG(total_points) as avg_pts "
                "FROM historical_stats WHERE fa_id = ? AND season = ?",
                (fa_id, args.season),
            ).fetchone()

            if result and result["total"]:
                # Form = last 5 GW average
                form_result = cur.execute(
                    "SELECT AVG(total_points) as form FROM historical_stats "
                    "WHERE fa_id = ? AND season = ? AND gameweek IN ("
                    "SELECT gameweek FROM historical_stats WHERE fa_id = ? AND season = ? "
                    "ORDER BY gameweek DESC LIMIT 5)",
                    (fa_id, args.season, fa_id, args.season),
                ).fetchone()
                form = form_result["form"] if form_result and form_result["form"] else 0

                cur.execute(
                    "UPDATE player_seasons SET total_points = ?, form = ? "
                    "WHERE fa_id = ? AND season = ?",
                    (result["total"], round(form, 1), fa_id, args.season),
                )
        conn.commit()

        # Log
        cur.execute(
            "INSERT INTO sync_log (source, sync_type, records_processed, records_added, "
            "records_updated, completed_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "retrospective_scoring",
                "calculate_points",
                len(gw_stats),
                sum(s["players"] for s in gw_stats),
                0,
                datetime.now().isoformat(),
                "success",
            ),
        )
        conn.commit()
        print("\nSeason totals updated in player_seasons")
    else:
        print("\n[Dry run] No changes written")

    conn.close()


if __name__ == "__main__":
    main()

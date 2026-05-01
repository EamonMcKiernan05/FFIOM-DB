"""Sync engine for FFIOM-DB - FullTime API + JSON import + merge logic."""

import json
import sqlite3
import time
from datetime import datetime, timezone

import requests


class SyncEngine:
    """Database sync engine for importing and merging player data.

    Uses an append-only model - players are never deleted automatically.
    Team changes are tracked as movements in the player_movements table.
    """

    def __init__(self, conn):
        """Initialize SyncEngine.

        Args:
            conn: sqlite3 connection object (should have schema created)
        """
        self.conn = conn
        self.cursor = conn.cursor()

    def sync_from_api(self, api_url, division_id, season="2025-26"):
        """Fetch player data from FullTime API and merge into database.

        Args:
            api_url: Base URL of the FullTime API
            division_id: Division ID for the league
            season: Season identifier string

        Returns:
            dict: Sync result with counts of processed, added, and updated records
        """
        log_id = self._start_sync_log("FullTime API", "api_sync")
        added = 0
        updated = 0
        errors = []

        try:
            # Fetch division data from API
            endpoint = f"{api_url}/api/division/{division_id}"
            response = requests.get(endpoint, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Process players from API response
            players = data.get("players", [])
            for player_data in players:
                fa_id = str(player_data.get("id", "") or player_data.get("personID", ""))
                if not fa_id:
                    continue

                name = player_data.get("name", "")
                team = player_data.get("team", "")
                position = player_data.get("position", None)
                price = player_data.get("price", 5.0)

                result = self.merge_player(fa_id, name, team, position, season)
                if result == "added":
                    added += 1
                elif result == "updated":
                    updated += 1

            self.conn.commit()
            self._complete_sync_log(
                log_id, "api_sync", len(players), added, updated, 0, "success", None
            )

        except requests.RequestException as e:
            error_msg = f"API request failed: {e}"
            errors.append(error_msg)
            self._complete_sync_log(
                log_id,
                "api_sync",
                len(players) if 'players' in locals() else 0,
                added,
                updated,
                0,
                "error",
                error_msg,
            )
            self.conn.commit()
        except Exception as e:
            error_msg = f"Sync failed: {e}"
            errors.append(error_msg)
            self._complete_sync_log(
                log_id,
                "api_sync",
                0,
                added,
                updated,
                0,
                "error",
                error_msg,
            )
            self.conn.commit()

        return {
            "source": "FullTime API",
            "sync_type": "api_sync",
            "records_processed": added + updated,
            "records_added": added,
            "records_updated": updated,
            "errors": errors,
        }

    def sync_from_json(self, players_file, stats_file, season="2025-26"):
        """Import player data from JSON files.

        Args:
            players_file: Path to real_players.json file
            stats_file: Path to player_stats_cache.json file
            season: Season identifier string

        Returns:
            dict: Sync result with counts of processed, added, and updated records
        """
        log_id = self._start_sync_log("JSON Import", "incremental")
        added = 0
        updated = 0

        try:
            # Load players list
            with open(players_file, "r") as f:
                players_data = json.load(f)

            players_list = players_data.get("players", [])

            # Load stats cache
            stats_cache = {}
            if stats_file:
                try:
                    with open(stats_file, "r") as f:
                        stats_cache = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError):
                    pass

            # Process each player
            for player in players_list:
                fa_id = str(player.get("personID", ""))
                if not fa_id:
                    continue

                name = player.get("name", "")
                team = ""
                position = None

                # Enrich with stats data if available
                stat = stats_cache.get(fa_id)
                if stat:
                    team = stat.get("team", "")

                # Merge player FIRST (FK constraint: player_seasons -> players)
                result = self.merge_player(fa_id, name, team, position, season)

                # THEN upsert season stats (player now exists)
                if stat:
                    self._upsert_season_stats(fa_id, season, stat)
                if result == "added":
                    added += 1
                elif result == "updated":
                    updated += 1

            self.conn.commit()
            self._complete_sync_log(
                log_id, "incremental", len(players_list), added, updated, 0, "success", None
            )

        except Exception as e:
            self._complete_sync_log(
                log_id,
                "incremental",
                0,
                added,
                updated,
                0,
                "error",
                str(e),
            )
            self.conn.commit()
            raise

        return {
            "source": "JSON Import",
            "sync_type": "incremental",
            "records_processed": added + updated,
            "records_added": added,
            "records_updated": updated,
        }

    def merge_player(self, fa_id, name, team, position, season="2025-26"):
        """Upsert a player into the registry and track movements.

        Uses INSERT OR IGNORE for the player registry (keyed on fa_id).
        Detects team changes and logs them in player_movements.
        Creates/updates player_season entry for the given season.

        Args:
            fa_id: Fantasy Football personID
            name: Player name
            team: Team name
            position: Player position (nullable)
            season: Season identifier string

        Returns:
            str: "added" if new player, "updated" if existing player changed
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Check if player exists
        self.cursor.execute("SELECT id, team FROM players WHERE fa_id = ?", (fa_id,))
        existing = self.cursor.fetchone()

        if existing is None:
            # New player - INSERT OR IGNORE
            self.cursor.execute(
                """INSERT OR IGNORE INTO players (fa_id, name, team, position, price, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 5.0, 1, ?, ?)""",
                (fa_id, name, team, position, now, now),
            )

            # Create initial season entry
            self.cursor.execute(
                """INSERT OR IGNORE INTO player_seasons (fa_id, season, team, position, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (fa_id, season, team, position, now, now),
            )

            return "added"
        else:
            # Existing player - check for changes
            old_team = existing[1]

            self.cursor.execute(
                """UPDATE players SET name = ?, team = ?, position = ?, updated_at = ?
                   WHERE fa_id = ?""",
                (name, team, position, now, fa_id),
            )

            # Track movement if team changed
            if old_team and team and old_team != team:
                self.cursor.execute(
                    """INSERT INTO player_movements (fa_id, from_team, to_team, movement_date, season, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (fa_id, old_team, team, now, season, now),
                )

            # Update season entry
            self.cursor.execute(
                """INSERT OR REPLACE INTO player_seasons (fa_id, season, team, position, created_at, updated_at)
                   VALUES (?, ?, ?, ?, COALESCE(
                       (SELECT created_at FROM player_seasons WHERE fa_id = ? AND season = ?),
                       ?
                   ), ?)""",
                (fa_id, season, team, position, fa_id, season, now, now),
            )

            return "updated"

    def _upsert_season_stats(self, fa_id, season, stats_data):
        """Upsert season statistics for a player.

        Uses INSERT OR REPLACE for seasonal stats (keyed on fa_id + season).

        Args:
            fa_id: Fantasy Football personID
            season: Season identifier string
            stats_data: Dict of statistics from stats cache
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        self.cursor.execute(
            """INSERT OR REPLACE INTO player_seasons (
                fa_id, season, team, position, goals, assists, appearances,
                yellows, reds, clean_sheets, saves, minutes_played, bonus,
                goals_conceded, own_goals, penalties_saved, penalties_missed,
                influence, creativity, threat, ict_index, total_points, form,
                selected_by_percent, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fa_id,
                season,
                stats_data.get("team", ""),
                stats_data.get("position", None),
                stats_data.get("goals", 0),
                stats_data.get("assists", 0),
                stats_data.get("appearances", 0),
                stats_data.get("yellows", 0),
                stats_data.get("reds", 0),
                stats_data.get("clean_sheets", 0),
                stats_data.get("saves", 0),
                stats_data.get("minutes_played", 0),
                stats_data.get("bonus", 0),
                stats_data.get("goals_conceded", 0),
                stats_data.get("own_goals", 0),
                stats_data.get("penalties_saved", 0),
                stats_data.get("penalties_missed", 0),
                stats_data.get("influence", 0.0),
                stats_data.get("creativity", 0.0),
                stats_data.get("threat", 0.0),
                stats_data.get("ict_index", 0.0),
                stats_data.get("total_points", 0),
                stats_data.get("form", 0.0),
                stats_data.get("selected_by_percent", 0.0),
                now,
                now,
            ),
        )

    def log_sync(self, source, sync_type, records=0, status="success", error=None):
        """Write a sync entry to the sync_log table.

        Args:
            source: Data source identifier
            sync_type: Type of sync operation
            records: Number of records processed
            status: Sync status ("success" or "error")
            error: Error message if failed
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute(
            """INSERT INTO sync_log (source, sync_type, records_processed, records_added,
               records_updated, records_deleted, started_at, completed_at, status, error_message)
               VALUES (?, ?, ?, 0, 0, 0, ?, ?, ?, ?)""",
            (source, sync_type, records, now, now, status, error),
        )
        self.conn.commit()

    def _start_sync_log(self, source, sync_type):
        """Start a new sync log entry.

        Args:
            source: Data source identifier
            sync_type: Type of sync operation

        Returns:
            int: sync_log row id
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute(
            """INSERT INTO sync_log (source, sync_type, started_at, status)
               VALUES (?, ?, ?, 'in_progress')""",
            (source, sync_type, now),
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def _complete_sync_log(self, log_id, sync_type, processed, added, updated, deleted, status, error):
        """Complete a sync log entry with final counts.

        Args:
            log_id: sync_log row id
            sync_type: Type of sync operation
            processed: Records processed
            added: Records added
            updated: Records updated
            deleted: Records deleted
            status: Sync status
            error: Error message if any
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute(
            """UPDATE sync_log SET sync_type = ?, records_processed = ?, records_added = ?,
               records_updated = ?, records_deleted = ?, completed_at = ?, status = ?,
               error_message = ?
               WHERE id = ?""",
            (sync_type, processed, added, updated, deleted, now, status, error, log_id),
        )
        self.conn.commit()

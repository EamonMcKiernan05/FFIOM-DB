#!/usr/bin/env python3
"""Tests for FFIOM-DB database operations."""

import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.schema import create_tables, get_table_count, list_tables
from src.sync import SyncEngine
from src.queries import (
    get_player,
    get_season_players,
    get_player_history,
    get_player_movements,
    get_top_scorers,
    get_sync_log,
    get_player_season_stats,
    get_all_players,
    get_team_roster,
)


def test_create_tables():
    """Test that all 5 tables are created with correct structure."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)

    tables = list_tables(conn)
    assert "players" in tables, f"players table missing. Tables: {tables}"
    assert "player_seasons" in tables, f"player_seasons table missing"
    assert "player_movements" in tables, f"player_movements table missing"
    assert "historical_stats" in tables, f"historical_stats table missing"
    assert "sync_log" in tables, f"sync_log table missing"

    # Verify WAL mode (skip for in-memory DB)
    cursor = conn.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    if mode != "memory":  # In-memory DBs always use "memory" mode
        assert mode == "wal", f"WAL mode not enabled, got: {mode}"

    conn.close()
    print("PASS: test_create_tables")


def test_sync_from_json():
    """Test importing players from JSON files."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    engine = SyncEngine(conn)

    # Create test data
    test_data = {
        "players": [
            {"name": "Test Player 1", "personID": "111111111"},
            {"name": "Test Player 2", "personID": "222222222"},
            {"name": "Test Player 3", "personID": "333333333"},
        ]
    }
    test_stats = {
        "111111111": {
            "name": "Test Player 1",
            "faId": "111111111",
            "team": "Test Team",
            "goals": 5,
            "assists": 2,
            "appearances": 10,
            "yellows": 1,
            "reds": 0,
        }
    }

    # Write to temp files
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(test_data, f)
        players_file = f.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(test_stats, f)
        stats_file = f.name

    try:
        result = engine.sync_from_json(players_file, stats_file, "2025-26")
        assert result["records_processed"] == 3, f"Expected 3, got {result['records_processed']}"
        assert result["records_added"] == 3, f"Expected 3 added, got {result['records_added']}"

        # Verify players were created
        player = get_player(conn, "111111111")
        assert player is not None, "Player not found"
        assert player["name"] == "Test Player 1", f"Wrong name: {player['name']}"
        assert player["team"] == "Test Team", f"Wrong team: {player['team']}"

        # Verify season stats
        season_stats = get_player_season_stats(conn, "111111111", "2025-26")
        assert season_stats is not None, "Season stats not found"
        assert season_stats["goals"] == 5, f"Wrong goals: {season_stats['goals']}"

        # Verify sync log
        logs = get_sync_log(conn)
        assert len(logs) > 0, "Sync log empty"
        assert logs[0]["status"] == "success", f"Sync failed: {logs[0]}"

    finally:
        os.unlink(players_file)
        os.unlink(stats_file)

    conn.close()
    print("PASS: test_sync_from_json")


def test_player_movements():
    """Test that team changes are tracked as movements."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    engine = SyncEngine(conn)

    # Add player with initial team
    engine.merge_player("111111111", "Test Player", "Team A", None, "2025-26")
    conn.commit()

    # Update player with new team
    engine.merge_player("111111111", "Test Player", "Team B", None, "2025-26")
    conn.commit()

    # Check movement was recorded
    movements = get_player_movements(conn, "111111111")
    assert len(movements) == 1, f"Expected 1 movement, got {len(movements)}"
    assert movements[0]["from_team"] == "Team A", f"Wrong from_team: {movements[0]}"
    assert movements[0]["to_team"] == "Team B", f"Wrong to_team: {movements[0]}"

    conn.close()
    print("PASS: test_player_movements")


def test_append_only_model():
    """Test that players are never deleted automatically."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    engine = SyncEngine(conn)

    # Add player
    engine.merge_player("111111111", "Test Player", "Team A", None, "2025-26")
    conn.commit()

    # Sync with different data that doesn't include this player
    test_data = {"players": [{"name": "Other Player", "personID": "222222222"}]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(test_data, f)
        players_file = f.name

    try:
        engine.sync_from_json(players_file, "", "2025-26")
    finally:
        os.unlink(players_file)

    # Original player should still exist
    player = get_player(conn, "111111111")
    assert player is not None, "Player was deleted (should be append-only)"

    conn.close()
    print("PASS: test_append_only_model")


def test_top_scorers():
    """Test top scorers query."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    engine = SyncEngine(conn)

    # Add players with different goal counts
    for i, (name, goals) in enumerate([
        ("Player A", 10), ("Player B", 5), ("Player C", 8), ("Player D", 3)
    ], 1):
        fa_id = str(i).zfill(9)
        engine.merge_player(fa_id, name, f"Team {chr(64+i)}", None, "2025-26")
        # Update season stats
        engine.cursor.execute(
            "UPDATE player_seasons SET goals = ?, appearances = 10 WHERE fa_id = ?",
            (goals, fa_id)
        )
    conn.commit()

    top = get_top_scorers(conn, "2025-26", n=3)
    assert len(top) == 3, f"Expected 3, got {len(top)}"
    assert top[0]["name"] == "Player A", f"Expected Player A first, got {top[0]['name']}"
    assert top[0]["goals"] == 10, f"Expected 10 goals, got {top[0]['goals']}"

    conn.close()
    print("PASS: test_top_scorers")


def test_season_players():
    """Test fetching all players for a season."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    engine = SyncEngine(conn)

    for i in range(5):
        fa_id = str(i).zfill(9)
        engine.merge_player(fa_id, f"Player {i}", f"Team {chr(65+i)}", None, "2025-26")
    conn.commit()

    players = get_season_players(conn, "2025-26")
    assert len(players) == 5, f"Expected 5, got {len(players)}"

    # Test with non-existent season
    players_empty = get_season_players(conn, "2024-25")
    assert len(players_empty) == 0, f"Expected 0 for empty season, got {len(players_empty)}"

    conn.close()
    print("PASS: test_season_players")


def test_team_roster():
    """Test fetching roster for a specific team."""
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    engine = SyncEngine(conn)

    for i in range(3):
        fa_id = str(i).zfill(9)
        engine.merge_player(fa_id, f"Player {i}", "Team A", None, "2025-26")
    for i in range(3, 5):
        fa_id = str(i).zfill(9)
        engine.merge_player(fa_id, f"Player {i}", "Team B", None, "2025-26")
    conn.commit()

    roster = get_team_roster(conn, "Team A", "2025-26")
    assert len(roster) == 3, f"Expected 3, got {len(roster)}"

    roster_b = get_team_roster(conn, "Team B", "2025-26")
    assert len(roster_b) == 2, f"Expected 2, got {len(roster_b)}"

    conn.close()
    print("PASS: test_team_roster")


def run_tests():
    """Run all tests."""
    print("Running FFIOM-DB tests...")
    print()

    tests = [
        test_create_tables,
        test_sync_from_json,
        test_player_movements,
        test_append_only_model,
        test_top_scorers,
        test_season_players,
        test_team_roster,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__} - {e}")
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()

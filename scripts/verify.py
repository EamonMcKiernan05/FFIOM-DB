#!/usr/bin/env python3
"""Verify FFIOM-DB database contents."""

import sqlite3

conn = sqlite3.connect("data/fantasy_iom.db")

# Count records
for table in ["players", "player_seasons", "player_movements", "historical_stats", "sync_log"]:
    cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
    print(f"{table}: {cur.fetchone()[0]} records")

# Show some sample data
print("\nTop scorers:")
cur = conn.execute("""
    SELECT p.name, ps.team, ps.goals, ps.assists, ps.appearances 
    FROM player_seasons ps
    JOIN players p ON ps.fa_id = p.fa_id
    WHERE ps.season = ? AND ps.appearances > 0
    ORDER BY ps.goals DESC
    LIMIT 10
""", ("2025-26",))
for row in cur.fetchall():
    print(f"  {row[0]:30s} {row[1]:25s} G:{row[2]} A:{row[3]} Apps:{row[4]}")

# Show sync log
print("\nSync log:")
cur = conn.execute("SELECT * FROM sync_log ORDER BY started_at DESC LIMIT 3")
for row in cur.fetchall():
    print(f"  {row}")

conn.close()

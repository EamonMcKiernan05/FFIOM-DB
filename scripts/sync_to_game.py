#!/usr/bin/env python3
"""Sync FFIOM-DB database to Fantasy-Football-Isle-of-Man game."""
import shutil
import sqlite3
from pathlib import Path

FFIOM_DB = Path("/home/eamon/FFIOM-DB/data/fantasy_iom.db")
GAME_DB = Path("/home/eamon/Fantasy-Football-Isle-of-Man/data/fantasy_iom.db")

def sync():
    """Copy FFIOM-DB to game directory."""
    if not FFIOM_DB.exists():
        raise FileNotFoundError(f"FFIOM-DB not found: {FFIOM_DB}")
    
    # Backup game DB
    if GAME_DB.exists():
        backup = GAME_DB.with_suffix('.db.backup')
        shutil.copy2(GAME_DB, backup)
        print(f"Backed up: {backup}")
    
    # Copy database
    shutil.copy2(FFIOM_DB, GAME_DB)
    print(f"Synced: {FFIOM_DB} -> {GAME_DB}")
    
    # Verify
    conn = sqlite3.connect(GAME_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"Tables: {len(tables)}")
    conn.close()
    print("Sync complete!")

if __name__ == "__main__":
    sync()

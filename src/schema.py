"""SQLite schema definitions for FFIOM-DB."""

import sqlite3


def create_tables(conn):
    """Create all database tables with proper constraints.

    Enables WAL mode and foreign key enforcement on the connection.

    Args:
        conn: sqlite3 connection object
    """
    # Enable WAL mode for better concurrent read performance
    conn.execute("PRAGMA journal_mode=WAL")

    # Enable foreign key enforcement
    conn.execute("PRAGMA foreign_keys=ON")

    cursor = conn.cursor()

    # Players table - permanent registry
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fa_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            team TEXT NOT NULL DEFAULT '',
            position TEXT,
            price REAL DEFAULT 5.0,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Player seasons table - season-specific assignments and stats
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fa_id TEXT NOT NULL,
            season TEXT NOT NULL,
            team TEXT NOT NULL DEFAULT '',
            position TEXT,
            goals INTEGER DEFAULT 0,
            assists INTEGER DEFAULT 0,
            appearances INTEGER DEFAULT 0,
            yellows INTEGER DEFAULT 0,
            reds INTEGER DEFAULT 0,
            clean_sheets INTEGER DEFAULT 0,
            saves INTEGER DEFAULT 0,
            minutes_played INTEGER DEFAULT 0,
            bonus INTEGER DEFAULT 0,
            goals_conceded INTEGER DEFAULT 0,
            own_goals INTEGER DEFAULT 0,
            penalties_saved INTEGER DEFAULT 0,
            penalties_missed INTEGER DEFAULT 0,
            influence REAL DEFAULT 0.0,
            creativity REAL DEFAULT 0.0,
            threat REAL DEFAULT 0.0,
            ict_index REAL DEFAULT 0.0,
            total_points INTEGER DEFAULT 0,
            form REAL DEFAULT 0.0,
            selected_by_percent REAL DEFAULT 0.0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fa_id, season),
            FOREIGN KEY (fa_id) REFERENCES players(fa_id)
        )
    """)

    # Player movements table - transfer tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fa_id TEXT NOT NULL,
            from_team TEXT NOT NULL,
            to_team TEXT NOT NULL,
            movement_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            season TEXT NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (fa_id) REFERENCES players(fa_id)
        )
    """)

    # Historical stats table - gameweek-level archive
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historical_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fa_id TEXT NOT NULL,
            season TEXT NOT NULL,
            gameweek INTEGER NOT NULL,
            opponent TEXT,
            was_home BOOLEAN DEFAULT 0,
            minutes_played INTEGER DEFAULT 0,
            goals_scored INTEGER DEFAULT 0,
            assists INTEGER DEFAULT 0,
            clean_sheet BOOLEAN DEFAULT 0,
            goals_conceded INTEGER DEFAULT 0,
            saves INTEGER DEFAULT 0,
            yellow_card BOOLEAN DEFAULT 0,
            red_card BOOLEAN DEFAULT 0,
            own_goal BOOLEAN DEFAULT 0,
            penalties_saved INTEGER DEFAULT 0,
            penalties_missed INTEGER DEFAULT 0,
            bonus_points INTEGER DEFAULT 0,
            base_points INTEGER DEFAULT 0,
            total_points INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fa_id, season, gameweek),
            FOREIGN KEY (fa_id) REFERENCES players(fa_id)
        )
    """)

    # Teams table - IOM football teams
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            short_name TEXT,
            division TEXT DEFAULT 'Premier',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Gameweeks table - rounds of fixtures
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gameweeks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER NOT NULL,
            season TEXT NOT NULL DEFAULT '',
            start_date DATE,
            end_date DATE,
            deadline DATETIME,
            closed BOOLEAN DEFAULT 0,
            scored BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(number, season)
        )
    """)

    # Fixtures table - individual matches
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fixtures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gameweek_id INTEGER NOT NULL,
            fixture_date DATETIME,
            home_team_id INTEGER,
            away_team_id INTEGER,
            home_team_name TEXT NOT NULL DEFAULT '',
            away_team_name TEXT NOT NULL DEFAULT '',
            home_score INTEGER,
            away_score INTEGER,
            half_time_home INTEGER,
            half_time_away INTEGER,
            home_scorers TEXT,
            away_scorers TEXT,
            played BOOLEAN DEFAULT 0,
            competition TEXT,
            division_name TEXT,
            home_difficulty INTEGER DEFAULT 3,
            away_difficulty INTEGER DEFAULT 3,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (gameweek_id) REFERENCES gameweeks(id),
            FOREIGN KEY (home_team_id) REFERENCES teams(id),
            FOREIGN KEY (away_team_id) REFERENCES teams(id)
        )
    """)

    # Sync log table - audit trail
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            sync_type TEXT NOT NULL,
            records_processed INTEGER DEFAULT 0,
            records_added INTEGER DEFAULT 0,
            records_updated INTEGER DEFAULT 0,
            records_deleted INTEGER DEFAULT 0,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            status TEXT DEFAULT 'success',
            error_message TEXT
        )
    """)

    conn.commit()


def get_table_count(conn, table_name):
    """Get the row count for a table.

    Args:
        conn: sqlite3 connection object
        table_name: Name of the table

    Returns:
        int: Number of rows in the table
    """
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]


def list_tables(conn):
    """List all tables in the database.

    Args:
        conn: sqlite3 connection object

    Returns:
        list: List of table names
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]

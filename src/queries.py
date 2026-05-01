"""Query helpers for FFIOM-DB."""

import sqlite3


def get_player(conn, fa_id):
    """Fetch a player by FA personID.

    Args:
        conn: sqlite3 connection
        fa_id: Fantasy Football personID

    Returns:
        dict or None
    """
    cursor = conn.execute("SELECT * FROM players WHERE fa_id = ?", (fa_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def get_season_players(conn, season="2025-26"):
    """Fetch all players active in a season.

    Args:
        conn: sqlite3 connection
        season: Season identifier

    Returns:
        list of dicts
    """
    cursor = conn.execute(
        """SELECT p.*, ps.*
           FROM players p
           JOIN player_seasons ps ON p.fa_id = ps.fa_id
           WHERE ps.season = ?
           ORDER BY p.name""",
        (season,),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_player_history(conn, fa_id, season="2025-26"):
    """Fetch gameweek-level stats for a player in a season.

    Args:
        conn: sqlite3 connection
        fa_id: Fantasy Football personID
        season: Season identifier

    Returns:
        list of dicts
    """
    cursor = conn.execute(
        """SELECT * FROM historical_stats
           WHERE fa_id = ? AND season = ?
           ORDER BY gameweek""",
        (fa_id, season),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_player_movements(conn, fa_id):
    """Fetch transfer history for a player.

    Args:
        conn: sqlite3 connection
        fa_id: Fantasy Football personID

    Returns:
        list of dicts
    """
    cursor = conn.execute(
        """SELECT * FROM player_movements
           WHERE fa_id = ?
           ORDER BY movement_date DESC""",
        (fa_id,),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_top_scorers(conn, season="2025-26", n=10):
    """Get the top goal scorers for a season.

    Args:
        conn: sqlite3 connection
        season: Season identifier
        n: Number of players to return

    Returns:
        list of dicts
    """
    cursor = conn.execute(
        """SELECT p.fa_id, p.name, ps.team, ps.goals, ps.assists, ps.appearances, ps.total_points
           FROM player_seasons ps
           JOIN players p ON ps.fa_id = p.fa_id
           WHERE ps.season = ? AND ps.appearances > 0
           ORDER BY ps.goals DESC, ps.assists DESC
           LIMIT ?""",
        (season, n),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_sync_log(conn, limit=20):
    """Get recent sync log entries.

    Args:
        conn: sqlite3 connection
        limit: Maximum entries to return

    Returns:
        list of dicts
    """
    cursor = conn.execute(
        """SELECT * FROM sync_log
           ORDER BY started_at DESC
           LIMIT ?""",
        (limit,),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_player_season_stats(conn, fa_id, season="2025-26"):
    """Get season stats for a specific player.

    Args:
        conn: sqlite3 connection
        fa_id: Fantasy Football personID
        season: Season identifier

    Returns:
        dict or None
    """
    cursor = conn.execute(
        "SELECT * FROM player_seasons WHERE fa_id = ? AND season = ?",
        (fa_id, season),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def get_all_players(conn):
    """Fetch all players from the registry.

    Args:
        conn: sqlite3 connection

    Returns:
        list of dicts
    """
    cursor = conn.execute("SELECT * FROM players ORDER BY name")
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_team_roster(conn, team_name, season="2025-26"):
    """Get all players for a specific team in a season.

    Args:
        conn: sqlite3 connection
        team_name: Team name
        season: Season identifier

    Returns:
        list of dicts
    """
    cursor = conn.execute(
        """SELECT p.*, ps.*
           FROM players p
           JOIN player_seasons ps ON p.fa_id = ps.fa_id
           WHERE ps.team = ? AND ps.season = ?
           ORDER BY p.name""",
        (team_name, season),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

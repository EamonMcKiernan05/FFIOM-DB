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


# --- Fixture and Gameweek queries ---


def get_gameweeks(conn, season="2025-26"):
    """Get all gameweeks for a season.

    Args:
        conn: sqlite3 connection
        season: Season identifier

    Returns:
        list of dicts
    """
    cursor = conn.execute(
        "SELECT * FROM gameweeks WHERE season = ? ORDER BY number",
        (season,),
    )
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_fixtures(conn, gameweek_id=None, season="2025-26", played=None):
    """Get fixtures with optional filters.

    Args:
        conn: sqlite3 connection
        gameweek_id: Filter by gameweek ID
        season: Season identifier
        played: Filter by played status (True/False)

    Returns:
        list of dicts
    """
    query = "SELECT f.*, g.number as gw_num FROM fixtures f JOIN gameweeks g ON f.gameweek_id = g.id WHERE g.season = ?"
    params = [season]

    if gameweek_id is not None:
        query += " AND f.gameweek_id = ?"
        params.append(gameweek_id)
    if played is not None:
        query += " AND f.played = ?"
        params.append(1 if played else 0)

    query += " ORDER BY f.fixture_date"
    cursor = conn.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_team_fixtures(conn, team_name, season="2025-26"):
    """Get all fixtures for a specific team.

    Args:
        conn: sqlite3 connection
        team_name: Team name (e.g., 'Peel', 'Onchan')
        season: Season identifier

    Returns:
        list of dicts
    """
    # Also check First-suffix versions
    team_first = f"{team_name} First"
    query = """
        SELECT f.*, g.number as gw_num
        FROM fixtures f
        JOIN gameweeks g ON f.gameweek_id = g.id
        WHERE g.season = ?
          AND (f.home_team_name = ? OR f.home_team_name = ?
               OR f.away_team_name = ? OR f.away_team_name = ?)
        ORDER BY f.fixture_date
    """
    cursor = conn.execute(query, (season, team_name, team_first, team_name, team_first))
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_gameweek_summary(conn, gw_number, season="2025-26"):
    """Get summary for a gameweek: top scorers, fixture results.

    Args:
        conn: sqlite3 connection
        gw_number: Gameweek number
        season: Season identifier

    Returns:
        dict with 'gameweek', 'top_scorers', 'fixtures'
    """
    gw = conn.execute(
        "SELECT * FROM gameweeks WHERE number = ? AND season = ?",
        (gw_number, season),
    ).fetchone()
    if not gw:
        return None

    gw_dict = dict(gw)

    # Top scorers
    cursor = conn.execute(
        "SELECT p.name, hs.total_points, hs.goals_scored, hs.clean_sheet, hs.minutes_played "
        "FROM historical_stats hs JOIN players p ON hs.fa_id = p.fa_id "
        "WHERE hs.gameweek = ? AND hs.season = ? "
        "ORDER BY hs.total_points DESC LIMIT 5",
        (gw_number, season),
    )
    cols = [desc[0] for desc in cursor.description]
    top_scorers = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Fixtures
    cursor = conn.execute(
        "SELECT f.* FROM fixtures f WHERE f.gameweek_id = ? ORDER BY f.fixture_date",
        (gw["id"],),
    )
    cols = [desc[0] for desc in cursor.description]
    fixtures = [dict(zip(cols, row)) for row in cursor.fetchall()]

    return {
        "gameweek": gw_dict,
        "top_scorers": top_scorers,
        "fixtures": fixtures,
    }


def get_season_summary(conn, season="2025-26"):
    """Get season summary stats.

    Args:
        conn: sqlite3 connection
        season: Season identifier

    Returns:
        dict with season summary
    """
    player_count = conn.execute(
        "SELECT COUNT(*) FROM player_seasons WHERE season = ?", (season,)
    ).fetchone()[0]

    gw_count = conn.execute(
        "SELECT COUNT(*) FROM gameweeks WHERE season = ?", (season,)
    ).fetchone()[0]

    fixture_count = conn.execute(
        "SELECT COUNT(*) FROM fixtures f JOIN gameweeks g ON f.gameweek_id = g.id "
        "WHERE g.season = ?", (season,)
    ).fetchone()[0]

    played_count = conn.execute(
        "SELECT COUNT(*) FROM fixtures f JOIN gameweeks g ON f.gameweek_id = g.id "
        "WHERE g.season = ? AND f.played = 1", (season,)
    ).fetchone()[0]

    total_stats = conn.execute(
        "SELECT COUNT(*) as entries, SUM(total_points) as total_pts, "
        "AVG(total_points) as avg_pts FROM historical_stats WHERE season = ?",
        (season,),
    ).fetchone()

    return {
        "season": season,
        "players": player_count,
        "gameweeks": gw_count,
        "fixtures_total": fixture_count,
        "fixtures_played": played_count,
        "historical_entries": total_stats["entries"],
        "total_points": total_stats["total_pts"],
        "avg_points": total_stats["avg_pts"],
    }

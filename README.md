# FFIOM-DB

Fantasy Football Isle of Man — persistent player database with append-only merge logic and FullTime API sync.

## Overview

FFIOM-DB is the source-of-truth player registry for Fantasy Football Isle of Man. It replaces the wipe-and-seed workflow with an append-only model that preserves historical stats and tracks player movements across seasons.

### Design Principles

- **Append-only registry** — players are never automatically deleted
- **Season-scoped stats** — each season gets its own row per player
- **Movement tracking** — club transfers logged automatically
- **Full audit trail** — every sync operation recorded in `sync_log`
- **FullTime API as incremental feed** — local DB is always the source of truth

## Quick Start

```bash
# Initialize the database
python scripts/init_db.py

# Import existing player data
python scripts/import_real_data.py

# Sync from FullTime API
python scripts/sync_from_api.py
```

## Schema

| Table | Purpose |
|-------|---------|
| `players` | Permanent player registry (FA personID as unique key) |
| `player_seasons` | Season-specific team assignments and cumulative stats |
| `player_movements` | Transfer history between clubs |
| `historical_stats` | Gameweek-level stat archive |
| `sync_log` | Audit trail for all sync operations |

### players
- `id` — autoincrement PK
- `fa_id` — FA personID (unique, indexed)
- `name` — full name
- `team` — current club
- `position` — GK / DEF / MID / FWD (nullable)
- `price` — FPL-style price in millions (default 5.0)
- `is_active` — boolean flag
- `created_at` / `updated_at` — timestamps

### player_seasons
- `id` — autoincrement PK
- `fa_id` — FK to players
- `season` — e.g. "2025-26"
- `team` — club for that season
- All cumulative season stats (goals, assists, appearances, etc.)
- Unique constraint on `(fa_id, season)`

### player_movements
- `id` — autoincrement PK
- `fa_id` — FK to players
- `from_team` / `to_team` — club change
- `movement_date` — when the transfer occurred
- `season` — which season it happened in

### historical_stats
- `id` — autoincrement PK
- `fa_id` — FK to players
- `season` — season identifier
- `gameweek` — gameweek number
- Match context + raw stats + points breakdown
- Unique constraint on `(fa_id, season, gameweek)`

### sync_log
- `id` — autoincrement PK
- `source` — data source (e.g. "FullTime API", "JSON import")
- `sync_type` — full_seed / incremental / api_sync
- `records_processed` / `records_added` / `records_updated` / `records_deleted`
- `started_at` / `completed_at` / `status` / `error_message`

## Data Sources

- **FullTime API**: `http://localhost:5000/api` (Division ID: 175685803)
- **JSON files**: `real_players.json` + `player_stats_cache.json`

## Configuration

Edit `config.yaml` to customize:
- Database path
- Default season
- FullTime API URL and division ID
- Sync settings

## API

```python
from src.schema import create_tables
from src.sync import SyncEngine
from src.queries import get_player, get_season_players, get_top_scorers

# Initialize
import sqlite3
conn = sqlite3.connect("data/fantasy_iom.db")
create_tables(conn)

# Sync
engine = SyncEngine(conn)
engine.sync_from_json("data/real_players.json", "data/player_stats_cache.json", "2025-26")

# Query
player = get_player(conn, "614634143")
top_scorers = get_top_scorers(conn, "2025-26", n=10)
```

## Force Reset

To completely wipe and re-seed the database:
```bash
python scripts/init_db.py --force-reset
```

## License

Private project for Fantasy Football Isle of Man.

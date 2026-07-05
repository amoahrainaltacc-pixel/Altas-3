"""
Lightweight async SQLite persistence layer for Atlas.
All tables are created lazily on startup. No ORM — plain SQL kept small and explicit.
"""

import time
import aiosqlite
import os
from config import DB_PATH

_conn: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    prefix TEXT DEFAULT ',',
    mod_log_channel INTEGER,
    join_log_channel INTEGER,
    message_log_channel INTEGER,
    voice_log_channel INTEGER,
    role_log_channel INTEGER,
    nick_log_channel INTEGER,
    server_log_channel INTEGER,
    delete_log_channel INTEGER,
    edit_log_channel INTEGER,
    autorole_id INTEGER,
    welcome_channel INTEGER,
    welcome_message TEXT,
    goodbye_channel INTEGER,
    goodbye_message TEXT,
    suggestion_channel INTEGER,
    verify_channel INTEGER,
    verify_role INTEGER,
    server_locked INTEGER DEFAULT 0,
    antiraid INTEGER DEFAULT 0,
    automod_enabled INTEGER DEFAULT 0,
    antispam INTEGER DEFAULT 0,
    antilink INTEGER DEFAULT 0,
    antiinvite INTEGER DEFAULT 0,
    antiemoji INTEGER DEFAULT 0,
    anticaps INTEGER DEFAULT 0,
    antihoist INTEGER DEFAULT 0,
    antibot INTEGER DEFAULT 0,
    antinuke INTEGER DEFAULT 0,
    antiwebhook INTEGER DEFAULT 0,
    level_up_message INTEGER DEFAULT 1,
    maintenance INTEGER DEFAULT 0,
    language TEXT DEFAULT 'en'
);

CREATE TABLE IF NOT EXISTS whitelist (
    guild_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS blacklist (
    user_id INTEGER PRIMARY KEY,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    moderator_id INTEGER,
    reason TEXT,
    created_at INTEGER
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    channel_id INTEGER,
    message TEXT,
    remind_at INTEGER
);

CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task TEXT,
    created_at INTEGER
);

CREATE TABLE IF NOT EXISTS afk (
    user_id INTEGER PRIMARY KEY,
    reason TEXT,
    since INTEGER
);

CREATE TABLE IF NOT EXISTS reaction_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    message_id INTEGER,
    emoji TEXT,
    role_id INTEGER
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    channel_id INTEGER,
    owner_id INTEGER,
    claimed_by INTEGER,
    status TEXT DEFAULT 'open',
    reason TEXT,
    created_at INTEGER,
    closed_at INTEGER
);

CREATE TABLE IF NOT EXISTS ticket_config (
    guild_id INTEGER PRIMARY KEY,
    category_id INTEGER,
    support_role_id INTEGER,
    panel_channel_id INTEGER,
    log_channel_id INTEGER,
    counter INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS giveaways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    channel_id INTEGER,
    message_id INTEGER,
    prize TEXT,
    winners INTEGER,
    host_id INTEGER,
    end_time INTEGER,
    ended INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS giveaway_entries (
    giveaway_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (giveaway_id, user_id)
);

CREATE TABLE IF NOT EXISTS economy (
    guild_id INTEGER,
    user_id INTEGER,
    balance INTEGER DEFAULT 500,
    bank INTEGER DEFAULT 0,
    last_daily INTEGER DEFAULT 0,
    last_work INTEGER DEFAULT 0,
    last_rob INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS levels (
    guild_id INTEGER,
    user_id INTEGER,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 0,
    last_xp_at INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS level_roles (
    guild_id INTEGER,
    level INTEGER,
    role_id INTEGER,
    PRIMARY KEY (guild_id, level)
);

CREATE TABLE IF NOT EXISTS starboard (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    threshold INTEGER DEFAULT 3
);

CREATE TABLE IF NOT EXISTS starboard_posts (
    original_message_id INTEGER PRIMARY KEY,
    starboard_message_id INTEGER
);
"""


async def init_db() -> None:
    global _conn
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    _conn = await aiosqlite.connect(DB_PATH)
    _conn.row_factory = aiosqlite.Row
    await _conn.executescript(SCHEMA)
    await _conn.commit()
    # Lightweight migration for columns added after initial release —
    # CREATE TABLE IF NOT EXISTS won't add new columns to an existing table.
    migrations = [
        "ALTER TABLE guild_config ADD COLUMN language TEXT DEFAULT 'en'",
        "ALTER TABLE tickets ADD COLUMN reason TEXT",
        "ALTER TABLE tickets ADD COLUMN closed_at INTEGER",
        "ALTER TABLE ticket_config ADD COLUMN log_channel_id INTEGER",
    ]
    for stmt in migrations:
        try:
            await _conn.execute(stmt)
            await _conn.commit()
        except Exception:
            pass


def get_conn() -> aiosqlite.Connection:
    if _conn is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _conn


async def ensure_guild(guild_id: int) -> None:
    conn = get_conn()
    await conn.execute(
        "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,)
    )
    await conn.commit()


async def get_guild_config(guild_id: int) -> aiosqlite.Row:
    await ensure_guild(guild_id)
    conn = get_conn()
    cur = await conn.execute(
        "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
    )
    row = await cur.fetchone()
    return row


async def set_guild_config(guild_id: int, **fields) -> None:
    await ensure_guild(guild_id)
    conn = get_conn()
    keys = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [guild_id]
    await conn.execute(
        f"UPDATE guild_config SET {keys} WHERE guild_id = ?", values
    )
    await conn.commit()


async def get_prefix_value(guild_id: int) -> str:
    row = await get_guild_config(guild_id)
    return row["prefix"] if row and row["prefix"] else ","


def now() -> int:
    return int(time.time())

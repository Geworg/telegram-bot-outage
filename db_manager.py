import asyncpg
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

# --- Logger Setup ---
log = logging.getLogger(__name__)

# --- Database Connection Pool ---
pool = None

async def init_db_pool():
    """Initializes the database connection pool."""
    global pool
    if pool:
        return
    try:
        pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))
        log.info("Database connection pool created successfully.")
        await setup_schema()
    except Exception as e:
        log.critical(f"Failed to create database connection pool: {e}", exc_info=True)
        pool = None
        exit(1)

async def close_db_pool():
    """Closes the database connection pool."""
    global pool
    if pool:
        await pool.close()
        log.info("Database connection pool closed.")

async def setup_schema():
    """Creates or alters tables in the database to match the required schema."""
    if not pool:
        log.error("Cannot setup schema, pool is not initialized.")
        return

    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                nick VARCHAR(64) DEFAULT 'none',
                name VARCHAR(255) DEFAULT '',
                language_code VARCHAR(10) DEFAULT 'en',
                tier VARCHAR(50) DEFAULT 'Free',
                frequency_seconds INTEGER DEFAULT 21600,
                notification_sound_enabled BOOLEAN DEFAULT TRUE,
                silent_mode_enabled BOOLEAN DEFAULT FALSE,
                silent_mode_start_time TIME DEFAULT '23:00:00',
                silent_mode_end_time TIME DEFAULT '07:00:00',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_active_at TIMESTAMPTZ DEFAULT NOW(),
                last_ad_sent_at TIMESTAMPTZ
            );
        ''')
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nick VARCHAR(64) DEFAULT 'none';")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(255) DEFAULT ''; ")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_sound_enabled BOOLEAN DEFAULT TRUE;")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS silent_mode_enabled BOOLEAN DEFAULT FALSE;")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS silent_mode_start_time TIME DEFAULT '23:00:00';")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS silent_mode_end_time TIME DEFAULT '07:00:00';")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_ad_sent_at TIMESTAMPTZ;")
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_addresses (
                address_id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                region VARCHAR(255),
                street VARCHAR(255),
                full_address_text TEXT,
                latitude DECIMAL(9, 6),
                longitude DECIMAL(9, 6),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_id, full_address_text)
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS outages (
                outage_id SERIAL PRIMARY KEY,
                raw_text_hash VARCHAR(64) UNIQUE NOT NULL,
                source_type VARCHAR(50) NOT NULL,
                source_url TEXT,
                publication_date TIMESTAMPTZ,
                start_datetime TIMESTAMPTZ,
                end_datetime TIMESTAMPTZ,
                status VARCHAR(100),
                regions TEXT[],
                streets TEXT[],
                details JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS sent_notifications (
                user_id BIGINT NOT NULL,
                outage_hash VARCHAR(64) NOT NULL,
                sent_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (user_id, outage_hash)
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_status (
                status_key VARCHAR(255) PRIMARY KEY,
                status_value TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        ''')
        log.info("Database schema verified/updated.")

# --- User Management ---
async def get_user(user_id: int) -> Optional[asyncpg.Record]:
    if not pool: return None
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def create_or_update_user(user_id: int, language_code: str, nick: str = 'none', name: str = ''):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, language_code, nick, name, last_active_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                language_code = EXCLUDED.language_code,
                nick = EXCLUDED.nick,
                name = EXCLUDED.name,
                last_active_at = NOW();
        ''', user_id, language_code, nick, name)
    log.info(f"User {user_id} created/updated: lang={language_code}, nick={nick}, name={name}.")

async def update_user_language(user_id: int, language_code: str):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET language_code = $1 WHERE user_id = $2", language_code, user_id)

async def update_user_frequency(user_id: int, frequency_seconds: int):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET frequency_seconds = $1 WHERE user_id = $2", frequency_seconds, user_id)

async def update_user_sound_settings(user_id: int, settings: Dict[str, Any]):
    """Updates various sound-related settings for a user."""
    if not pool: return
    set_clauses = []
    values = []
    i = 1
    for key, value in settings.items():
        set_clauses.append(f"{key} = ${i}")
        values.append(value)
        i += 1
    if not set_clauses:
        return
    values.append(user_id)
    query = f"UPDATE users SET {', '.join(set_clauses)} WHERE user_id = ${i}"
    async with pool.acquire() as conn:
        await conn.execute(query, *values)

# --- Address Management ---
async def add_user_address(user_id: int, region: str, street: str, full_address: str, lat: float, lon: float) -> bool:
    if not pool: return False
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO user_addresses (user_id, region, street, full_address_text, latitude, longitude)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', user_id, region, street, full_address, lat, lon)
        return True
    except asyncpg.UniqueViolationError:
        log.warning(f"Attempted to add duplicate address for user {user_id}: {full_address}")
        return False

async def get_user_addresses(user_id: int) -> List[asyncpg.Record]:
    if not pool: return []
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM user_addresses WHERE user_id = $1 ORDER BY created_at", user_id)

async def remove_user_address(address_id: int, user_id: int) -> bool:
    if not pool: return False
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM user_addresses WHERE address_id = $1 AND user_id = $2", address_id, user_id)
        return 'DELETE 1' in result

async def clear_all_user_addresses(user_id: int) -> int:
    """Removes all addresses for a user and returns the count of deleted rows."""
    if not pool: return 0
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM user_addresses WHERE user_id = $1", user_id)
        return int(result.split(' ')[1]) if 'DELETE' in result else 0

# --- Outage & Notification Management ---
async def add_outage(outage_data: Dict[str, Any]):
    if not pool: return
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO outages (raw_text_hash, source_type, source_url, publication_date, start_datetime, end_datetime, status, regions, streets, details)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (raw_text_hash) DO NOTHING
            ''',
            outage_data['raw_text_hash'], outage_data.get('source_type'),
            outage_data.get('source_url'), outage_data.get('publication_date'),
            outage_data.get('start_datetime'), outage_data.get('end_datetime'),
            outage_data.get('status'), outage_data.get('regions'),
            outage_data.get('streets'), outage_data.get('details')
            )
    except Exception as e:
        log.error(f"Error adding outage to DB: {e}", exc_info=True)

async def find_outages_for_address(lat: float, lon: float, radius_meters: int = 500) -> List[asyncpg.Record]:
    """Finds current and future outages near a specific coordinate point."""
    if not pool: return []
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM outages WHERE end_datetime IS NULL OR end_datetime > NOW() - INTERVAL '1 day' ORDER BY start_datetime DESC")

async def get_last_outage_for_address(full_address_text: str) -> Optional[asyncpg.Record]:
    """Finds the most recent past outage for a specific address text for historical lookups."""
    if not pool: return None
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM outages WHERE details->>'armenian_text' ILIKE $1 AND end_datetime < NOW() ORDER BY end_datetime DESC LIMIT 1",
            f'%{full_address_text}%'
        )

# --- Bot Status & Analytics ---
async def set_bot_status(key: str, value: str):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO bot_status (status_key, status_value, updated_at) VALUES ($1, $2, NOW())
            ON CONFLICT (status_key) DO UPDATE SET status_value = $2, updated_at = NOW();
        ''', key, value)

async def get_bot_status(key: str) -> Optional[str]:
    if not pool: return None
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT status_value FROM bot_status WHERE status_key = $1", key)

async def get_system_stats() -> Dict[str, int]:
    if not pool: return {'total_users': 0, 'total_addresses': 0}
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        total_addresses = await conn.fetchval("SELECT COUNT(*) FROM user_addresses")
        return {
            'total_users': total_users,
            'total_addresses': total_addresses
        }

async def get_user_notification_count(user_id: int) -> int:
     if not pool: return 0
     async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM sent_notifications WHERE user_id = $1", user_id)

# --- Заглушка для find_outages_for_address_text ---
async def find_outages_for_address_text(address_text: str):
    """
    Находит все аварии (outages), где адрес (или его часть) встречается в деталях outage (armenian_text, streets, regions).
    Возвращает список outages, отсортированных по дате начала (start_datetime DESC).
    """
    if not pool:
        return []
    async with pool.acquire() as conn:
        # Поиск по armenian_text, streets и regions (строгое и частичное совпадение)
        return await conn.fetch('''
            SELECT * FROM outages
            WHERE 
                (details->>'armenian_text' ILIKE $1
                 OR $1 = ANY(streets)
                 OR $1 = ANY(regions)
                 OR EXISTS (
                    SELECT 1 FROM unnest(streets) AS s WHERE s ILIKE $2
                 )
                 OR EXISTS (
                    SELECT 1 FROM unnest(regions) AS r WHERE r ILIKE $2
                 )
                )
            ORDER BY start_datetime DESC
        ''', f'%{address_text}%', f'%{address_text}%')

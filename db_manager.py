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
    """
    Initializes the database connection pool.
    This should be called once when the bot starts.
    """
    global pool
    if pool:
        return
    try:
        pool = await asyncpg.create_pool(
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        log.info("Database connection pool created successfully.")
        await setup_schema()
    except Exception as e:
        log.critical(f"Failed to create database connection pool: {e}", exc_info=True)
        pool = None

async def close_db_pool():
    """
    Closes the database connection pool.
    This should be called once when the bot stops.
    """
    global pool
    if pool:
        await pool.close()
        log.info("Database connection pool closed.")

async def setup_schema():
    """
    Creates the necessary tables in the database if they don't already exist.
    """
    if not pool:
        log.error("Cannot setup schema, pool is not initialized.")
        return

    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
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
                UNIQUE(user_id, region, street)
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
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS analytics_events (
                event_id SERIAL PRIMARY KEY,
                user_id BIGINT,
                event_type VARCHAR(100) NOT NULL,
                event_details JSONB,
                timestamp TIMESTAMPTZ DEFAULT NOW()
            );
        ''')
        log.info("Database schema verified/created.")

# --- User Management ---

async def get_user(user_id: int) -> Optional[asyncpg.Record]:
    """Fetches a user's data from the database."""
    if not pool: return None
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

async def create_or_update_user(user_id: int, language_code: str):
    """Creates a new user or updates their last_active_at timestamp."""
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, language_code, last_active_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                last_active_at = NOW();
        ''', user_id, language_code)
    log.info(f"User {user_id} created or updated.")

async def update_user_language(user_id: int, language_code: str):
    """Updates a user's language preference."""
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET language_code = $1, last_active_at = NOW() WHERE user_id = $2",
            language_code, user_id
        )

async def update_user_frequency(user_id: int, frequency_seconds: int):
    """Updates a user's notification frequency."""
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET frequency_seconds = $1, last_active_at = NOW() WHERE user_id = $2",
            frequency_seconds, user_id
        )
# --- Address Management ---

async def add_user_address(user_id: int, region: str, street: str, full_address: str = None, lat: float = None, lon: float = None) -> bool:
    """Adds a new address for a user, returns True if successful, False if duplicate."""
    if not pool: return False
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO user_addresses (user_id, region, street, full_address_text, latitude, longitude)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', user_id, region, street, full_address, lat, lon)
        return True
    except asyncpg.UniqueViolationError:
        log.warning(f"Attempted to add duplicate address for user {user_id}: {region}, {street}")
        return False

async def get_user_addresses(user_id: int) -> List[asyncpg.Record]:
    """Retrieves all addresses for a given user."""
    if not pool: return []
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM user_addresses WHERE user_id = $1 ORDER BY created_at", user_id)

async def remove_user_address(address_id: int, user_id: int) -> bool:
    """Removes a specific address by its ID, ensuring it belongs to the user."""
    if not pool: return False
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM user_addresses WHERE address_id = $1 AND user_id = $2",
            address_id, user_id
        )
        # result is a string like 'DELETE 1'
        return 'DELETE 1' in result

async def clear_user_addresses(user_id: int):
    """Removes all addresses for a user."""
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_addresses WHERE user_id = $1", user_id)

# --- Outage & Notification Management ---

async def add_outage(outage_data: Dict[str, Any]):
    """Adds a new outage announcement to the database."""
    if not pool: return
    try:
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO outages (raw_text_hash, source_type, source_url, publication_date, start_datetime, end_datetime, status, regions, streets, details)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ''',
            outage_data['raw_text_hash'],
            outage_data.get('source_type'),
            outage_data.get('source_url'),
            outage_data.get('publication_date'),
            outage_data.get('start_datetime'),
            outage_data.get('end_datetime'),
            outage_data.get('status'),
            outage_data.get('regions'),
            outage_data.get('streets'),
            outage_data.get('details')
            )
    except asyncpg.UniqueViolationError:
        # This is expected if we re-parse the same announcement, so we can ignore it.
        pass
    except Exception as e:
        log.error(f"Error adding outage to DB: {e}", exc_info=True)


async def check_if_notification_sent(user_id: int, outage_hash: str) -> bool:
    """Checks if a notification for a specific outage has already been sent to a user."""
    if not pool: return True # Assume sent to prevent spam if DB is down
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT 1 FROM sent_notifications WHERE user_id = $1 AND outage_hash = $2",
            user_id, outage_hash
        )
        return result is not None

async def add_sent_notification(user_id: int, outage_hash: str):
    """Records that a notification has been sent."""
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO sent_notifications (user_id, outage_hash)
            VALUES ($1, $2)
            ON CONFLICT (user_id, outage_hash) DO NOTHING;
        ''', user_id, outage_hash)

# --- Bot Status & Analytics ---

async def set_bot_status(key: str, value: str):
    """Sets a key-value status for the bot (e.g., maintenance mode)."""
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO bot_status (status_key, status_value, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (status_key) DO UPDATE SET
                status_value = $2,
                updated_at = NOW();
        ''', key, value)

async def get_bot_status(key: str) -> Optional[str]:
    """Gets a status value for the bot."""
    if not pool: return None
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT status_value FROM bot_status WHERE status_key = $1", key)

async def log_analytics_event(user_id: int, event_type: str, details: Dict = None):
    """Logs a user interaction or system event for analytics."""
    if not pool: return
    import json
    details_json = json.dumps(details) if details else None
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO analytics_events (user_id, event_type, event_details)
            VALUES ($1, $2, $3)
        ''', user_id, event_type, details_json)

# <3
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
        # Exit if DB connection fails, as the bot cannot function.
        # In a real production environment, you might want a retry mechanism.
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
        # User table with sound settings
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                language_code VARCHAR(10) DEFAULT 'en',
                frequency_seconds INTEGER DEFAULT 21600, -- Default 6 hours
                tier VARCHAR(20) DEFAULT 'Free',
                notification_sound_enabled BOOLEAN DEFAULT TRUE,
                silent_mode_enabled BOOLEAN DEFAULT FALSE,
                silent_mode_start_time TIME DEFAULT '23:00:00',
                silent_mode_end_time TIME DEFAULT '07:00:00',
                last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        ''')
        log.info("Users table schema verified/updated.")

        # User Addresses table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_addresses (
                address_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                region TEXT NOT NULL,
                street TEXT NOT NULL,
                full_address_text TEXT NOT NULL,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE (user_id, full_address_text)
            );
        ''')
        log.info("User_addresses table schema verified/updated.")

        # Outage Announcements table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS outages (
                raw_text_hash VARCHAR(64) PRIMARY KEY, -- SHA256 hash of raw text
                source_type VARCHAR(50) NOT NULL, -- e.g., 'water', 'gas', 'electric'
                source_url TEXT,
                publication_date TIMESTAMP WITH TIME ZONE,
                start_datetime TIMESTAMP WITH TIME ZONE,
                end_datetime TIMESTAMP WITH TIME ZONE,
                status VARCHAR(50), -- e.g., 'planned', 'emergency', 'resolved'
                regions TEXT[], -- Array of affected regions
                streets TEXT[], -- Array of affected streets
                details JSONB, -- Store original Armenian text and any other extracted data
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        ''')
        log.info("Outages table schema verified/updated.")

        # Notification Log table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS notification_log (
                log_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                outage_hash VARCHAR(64) NOT NULL REFERENCES outages(raw_text_hash) ON DELETE CASCADE,
                notified_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE (user_id, outage_hash)
            );
        ''')
        log.info("Notification_log table schema verified/updated.")

        # Bot Status table (for maintenance mode, last check time, etc.)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_status (
                status_key VARCHAR(100) PRIMARY KEY,
                status_value TEXT,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        ''')
        log.info("Bot_status table schema verified/updated.")
        log.info("Database schema verified/updated.")

# --- User Management ---
async def create_or_update_user(user_id: int, language_code: str = 'en') -> dict:
    if not pool: return {}
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            '''
            INSERT INTO users (user_id, language_code) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET language_code = $2, last_active = NOW()
            RETURNING *;
            ''',
            user_id, language_code
        )
        return dict(user) if user else {}

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    if not pool: return None
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(user) if user else None

async def get_all_users() -> List[Dict[str, Any]]:
    """Fetches all users from the database."""
    if not pool: return []
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT * FROM users")
        return [dict(user) for user in users]

async def update_user_language(user_id: int, language_code: str):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET language_code = $1, last_active = NOW() WHERE user_id = $2", language_code, user_id)

async def update_user_frequency(user_id: int, frequency_seconds: int):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET frequency_seconds = $1, last_active = NOW() WHERE user_id = $2", frequency_seconds, user_id)

async def update_user_last_active(user_id: int):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_active = NOW() WHERE user_id = $1", user_id)

async def set_user_notification_sound(user_id: int, enabled: bool):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET notification_sound_enabled = $1, last_active = NOW() WHERE user_id = $2", enabled, user_id)

async def set_user_silent_mode_enabled(user_id: int, enabled: bool):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET silent_mode_enabled = $1, last_active = NOW() WHERE user_id = $2", enabled, user_id)

async def set_user_silent_mode_times(user_id: int, start_time: datetime.time, end_time: datetime.time):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET silent_mode_start_time = $1, silent_mode_end_time = $2, last_active = NOW() WHERE user_id = $3",
            start_time,
            end_time,
            user_id
        )
# --- User Address Management ---
async def add_user_address(user_id: int, region: str, street: str, full_address_text: str, latitude: float, longitude: float) -> Optional[int]:
    if not pool: return None
    async with pool.acquire() as conn:
        try:
            address_id = await conn.fetchval(
                '''
                INSERT INTO user_addresses (user_id, region, street, full_address_text, latitude, longitude)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, full_address_text) DO NOTHING
                RETURNING address_id;
                ''',
                user_id, region, street, full_address_text, latitude, longitude
            )
            return address_id
        except Exception as e:
            log.error(f"Error adding user address {full_address_text} for user {user_id}: {e}", exc_info=True)
            return None

async def get_user_addresses(user_id: int) -> List[Dict[str, Any]]:
    if not pool: return []
    async with pool.acquire() as conn:
        addresses = await conn.fetch("SELECT * FROM user_addresses WHERE user_id = $1 ORDER BY created_at", user_id)
        return [dict(addr) for addr in addresses]

async def remove_user_address(address_id: int, user_id: int) -> bool:
    if not pool: return False
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM user_addresses WHERE address_id = $1 AND user_id = $2", address_id, user_id)
        return result == 'DELETE 1'

async def clear_all_user_addresses(user_id: int) -> bool:
    if not pool: return False
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM user_addresses WHERE user_id = $1", user_id)
        # asyncpg returns 'DELETE N' where N is number of rows
        return result.startswith('DELETE')


# --- Outage Management ---
async def add_outage(outage_data: Dict[str, Any]):
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute(
            '''
            INSERT INTO outages (raw_text_hash, source_type, source_url, publication_date, start_datetime, end_datetime, status, regions, streets, details)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (raw_text_hash) DO UPDATE SET
                source_type = EXCLUDED.source_type,
                source_url = EXCLUDED.source_url,
                publication_date = EXCLUDED.publication_date,
                start_datetime = EXCLUDED.start_datetime,
                end_datetime = EXCLUDED.end_datetime,
                status = EXCLUDED.status,
                regions = EXCLUDED.regions,
                streets = EXCLUDED.streets,
                details = EXCLUDED.details,
                created_at = NOW(); -- Update timestamp on conflict as well
            ''',
            outage_data['raw_text_hash'],
            outage_data['source_type'],
            outage_data['source_url'],
            outage_data['publication_date'],
            outage_data['start_datetime'],
            outage_data['end_datetime'],
            outage_data['status'],
            outage_data['regions'],
            outage_data['streets'],
            outage_data['details']
        )

async def get_active_outages_for_address(full_address_text: str) -> List[Dict[str, Any]]:
    """
    Fetches active outages (where end_datetime is in the future or not specified)
    for a given full address text.
    Uses ILIKE for fuzzy matching on the Armenian text within details.
    """
    if not pool: return []
    async with pool.acquire() as conn:
        # We look for outages that are either ongoing or upcoming
        # An outage is considered active if:
        # 1. its end_datetime is NULL (ongoing indefinitely)
        # 2. OR its end_datetime is in the future
        # AND its Armenian text details match the address (case-insensitive)
        outages = await conn.fetch(
            """
            SELECT * FROM outages
            WHERE (end_datetime IS NULL OR end_datetime > NOW())
            AND details->>'armenian_text' ILIKE $1
            ORDER BY start_datetime NULLS LAST; -- Order by start time, nulls at end
            """,
            f'%{full_address_text}%'
        )
        return [dict(o) for o in outages]


async def get_past_outages_for_address(full_address_text: str) -> Optional[Dict[str, Any]]:
    """
    Fetches the most recent past outage for a given full address text.
    """
    if not pool: return None
    async with pool.acquire() as conn:
        past_outage = await conn.fetchrow(
            "SELECT * FROM outages WHERE details->>'armenian_text' ILIKE $1 AND end_datetime < NOW() ORDER BY end_datetime DESC LIMIT 1",
            f'%{full_address_text}%'
        )
        return dict(past_outage) if past_outage else None

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
    """Gets the total number of notifications sent to a specific user."""
    if not pool: return 0
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM notification_log WHERE user_id = $1", user_id)

async def record_notification_sent(user_id: int, outage_hash: str):
    """Records that a notification for a specific outage has been sent to a user."""
    if not pool: return
    async with pool.acquire() as conn:
        await conn.execute(
            '''
            INSERT INTO notification_log (user_id, outage_hash) VALUES ($1, $2)
            ON CONFLICT (user_id, outage_hash) DO NOTHING;
            ''',
            user_id, outage_hash
        )

async def has_notification_been_sent(user_id: int, outage_hash: str) -> bool:
    """Checks if a notification for a specific outage has already been sent to a user."""
    if not pool: return False
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM notification_log WHERE user_id = $1 AND outage_hash = $2",
            user_id, outage_hash
        )
        return count > 0

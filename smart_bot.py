import os
import json
import re
import asyncio
import shutil
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from time import time as timestamp
from typing import Dict, List, Optional, Set, Any, Tuple, Callable
from collections import defaultdict
from difflib import SequenceMatcher, get_close_matches
from enum import Enum, auto
import urllib.parse
import hashlib
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, ContextTypes, CommandHandler, MessageHandler, filters, BasePersistence, JobQueue, PicklePersistence
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter, TimedOut, NetworkError
from logger import log_info, log_error, log_warning
from translations import translations, CONTACT_PHONE_NUMBER, CONTACT_ADDRESS_TEXT, MAP_URL, CLICKABLE_PHONE_MD, CLICKABLE_ADDRESS_MD
from parse_water import parse_all_water_announcements_async
from parse_gas import parse_all_gas_announcements_async
from parse_electric import parse_all_electric_announcements_async
from handlers import set_frequency_command, handle_frequency_choice, FREQUENCY_OPTIONS
from ai_engine import clarify_address_ai, is_ai_available, MODEL_PATH as AI_MODEL_PATH, MODELS_DIR as AI_MODELS_DIR
import aiofiles
import aiofiles.os as aios
from pathlib import Path
import requests
from tqdm import tqdm

# --- Configuration ---
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    log_error("TELEGRAM_BOT_TOKEN not found in .env file. Bot cannot start.")
    exit()

ADMIN_USER_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_USER_IDS", "").split(',') if admin_id.strip()]
log_info(f"Admin User IDs: {ADMIN_USER_IDS}")
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
PERSISTENCE_FILE = DATA_DIR / "bot_persistence.json"
USER_SETTINGS_FILE = DATA_DIR / "user_settings.json"
ADDRESSES_FILE = DATA_DIR / "addresses.json"
NOTIFIED_FILE = DATA_DIR / "notified_announcements.json"
BOT_STATUS_FILE = DATA_DIR / "bot_general_status.json"
REGION_STREET_MAP_FILE = DATA_DIR / "region_street_map.json"
# Model download configuration (specific to smart_bot.py's download logic)
# NOTE: This is somewhat redundant with ai_engine.py's model path. Ideally, one source of truth.
# For this example, we assume smart_bot.py ensures the model exists at the path ai_engine.py expects.
MODEL_URL = os.getenv("LLAMA_MODEL_URL", "https://huggingface.co/Geworg/phi2-gguf/resolve/main/phi-2.Q4_K_M.gguf")
# Use AI_MODEL_PATH from ai_engine.py as the target for download
LOCAL_MODEL_PATH = Path(AI_MODEL_PATH)

# --- Constants ---
DEFAULT_LANG = "hy"
USER_DATA_STEP_KEY = "current_step"
USER_DATA_SELECTED_REGION_KEY = "selected_region"
USER_DATA_ADDRESS_ATTEMPT_KEY = "address_attempt"
USER_DATA_TEMP_ADDRESS_KEY = "temp_address_info"
# Callback prefixes
CALLBACK_PREFIX_SUBSCRIBE = "subscribe_"
CALLBACK_PREFIX_ADDRESS_CONFIRM = "address_confirm_"
CALLBACK_PREFIX_HELP = "help_action_"
CALLBACK_PREFIX_FAQ_ITEM = "faq_item_"
CALLBACK_PREFIX_SOUND = "sound_settings_"
CALLBACK_PREFIX_REMOVE_ADDRESS = "remove_addr_"
CALLBACK_PREFIX_LANGUAGE = "lang_"
# Free tier ad display frequency
AD_INTERVAL_SECONDS = 24 * 60 * 60
LAST_AD_TIMESTAMP_KEY = "last_ad_timestamp"

# --- Enums ---
class UserStepsEnum(Enum):
    NONE = auto()
    AWAITING_REGION_CHOICE = auto()
    AWAITING_STREET_INPUT = auto()
    AWAITING_ADDRESS_CONFIRMATION = auto()
    AWAITING_FREQUENCY_CHOICE = auto()
    AWAITING_ADDRESS_TO_REMOVE = auto()
    AWAITING_ADDRESS_TO_CHECK = auto()
    AWAITING_LANGUAGE_CHOICE = auto()
# --- Data Structures & Locks (using asyncio.Lock for critical sections with files) ---
# NOTE: These global dictionaries will be managed by Telegram's persistence if configured.
# If not using persistence for these, manual loading/saving with locks is crucial.
# For this version, we assume persistence handles user_settings and addresses.
# notified_announcements will be handled manually with locks.
user_settings: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"lang": DEFAULT_LANG, "frequency": 21600, "current_tier": "Free", "sound_enabled": True})
addresses: Dict[str, List[Dict[str, str]]] = defaultdict(list)
notified_announcements: Dict[str, float] = {} # Store announcement hash -> timestamp notified
region_street_map: Dict[str, List[str]] = {} # Marz/Region -> List of streets
# Locks for file operations not handled by persistence
notified_lock = asyncio.Lock()
status_lock = asyncio.Lock()
region_map_lock = asyncio.Lock()
# user_settings_lock = asyncio.Lock() # Not needed if using PTB persistence for user_settings
# addresses_lock = asyncio.Lock()   # Not needed if using PTB persistence for addresses
# --- Utility Functions ---
def get_translation(key: str, lang: str, default_text: Optional[str] = None, **kwargs) -> str:
    """Retrieves a translation string, falling back to default or key itself."""
    if default_text is None:
        default_text = key.replace("_", " ").capitalize()
    return translations.get(key, {}).get(lang, default_text).format(**kwargs)

def get_user_lang(user_id_str: str) -> str:
    # Assumes user_settings is populated (e.g., by persistence or load function)
    return user_settings.get(user_id_str, {}).get("lang", DEFAULT_LANG)

def get_reply_markup_for_lang(lang: str, context: Optional[ContextTypes.DEFAULT_TYPE] = None, user_id_str: Optional[str] = None) -> ReplyKeyboardMarkup:
    """Generates the main keyboard for the user's language."""
    # Ensure lang is valid, fallback to DEFAULT_LANG
    if lang not in ["hy", "ru", "en"]:
        lang = DEFAULT_LANG

    keyboard = [
        [KeyboardButton(get_translation("add_address_btn", lang)), KeyboardButton(get_translation("remove_address_btn", lang))],
        [KeyboardButton(get_translation("show_addresses_btn", lang)), KeyboardButton(get_translation("clear_all_btn", lang))],
        [KeyboardButton(get_translation("check_address_btn", lang)), KeyboardButton(get_translation("set_frequency_btn", lang))],
        [KeyboardButton(get_translation("change_language_btn", lang)), KeyboardButton(get_translation("help_btn", lang))],
    ]
    # Example of adding a button based on user tier (if such logic exists)
    # if user_id_str and context and user_settings.get(user_id_str, {}).get("current_tier", "Free") != "Free":
    #     keyboard.append([KeyboardButton(get_translation("premium_features_btn", lang))])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def save_data_async(filepath: Path, data: Any, lock: Optional[asyncio.Lock] = None) -> None:
    """Asynchronously saves data to a JSON file with an optional lock."""
    # IMPROVEMENT: Use a temporary file for atomic-like write to prevent data corruption on crash
    temp_filepath = filepath.with_suffix(filepath.suffix + ".tmp")
    try:
        if lock:
            async with lock:
                async with aiofiles.open(temp_filepath, mode="w", encoding="utf-8") as f:
                    await f.write(json.dumps(data, indent=2, ensure_ascii=False))
                await aios.rename(temp_filepath, filepath)
        else:
            async with aiofiles.open(temp_filepath, mode="w", encoding="utf-8") as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))
            await aios.rename(temp_filepath, filepath)
        log_info(f"Data saved to {filepath}")
    except Exception as e:
        log_error(f"Error saving data to {filepath}: {e}", exc=e)
        if await aios.path.exists(temp_filepath):
            try:
                await aios.remove(temp_filepath)
            except Exception as e_rem:
                log_error(f"Error removing temporary file {temp_filepath}: {e_rem}")

async def load_data_async(filepath: Path, default_factory: Callable = dict, lock: Optional[asyncio.Lock] = None) -> Any:
    """Asynchronously loads data from a JSON file with an optional lock."""
    try:
        if await aios.path.exists(filepath):
            if lock:
                async with lock:
                    async with aiofiles.open(filepath, mode="r", encoding="utf-8") as f:
                        content = await f.read()
                        if not content: return default_factory() # Handle empty file
                        return json.loads(content)
            else:
                async with aiofiles.open(filepath, mode="r", encoding="utf-8") as f:
                    content = await f.read()
                    if not content: return default_factory()
                    return json.loads(content)
        return default_factory()
    except json.JSONDecodeError as e:
        log_error(f"JSONDecodeError loading data from {filepath}: {e}. Returning default.", exc=e)
        # IMPROVEMENT: Backup corrupted file and return default
        corrupted_backup_path = filepath.with_suffix(filepath.suffix + f".corrupted_{datetime.now().strftime('%Y%m%d%H%M%S')}")
        try:
            await aios.rename(filepath, corrupted_backup_path)
            log_info(f"Backed up corrupted file to {corrupted_backup_path}")
        except Exception as backup_e:
            log_error(f"Could not backup corrupted file {filepath}: {backup_e}")
        return default_factory()
    except Exception as e:
        log_error(f"Error loading data from {filepath}: {e}. Returning default.", exc=e)
        return default_factory()

# --- Load initial data ---
async def load_all_data():
    """Loads all necessary data files at startup."""
    global user_settings, addresses, notified_announcements, region_street_map
    # For data managed by PTB persistence, this manual loading might be redundant
    # if persistence is configured correctly and loads data into context.bot_data / user_data.
    # However, if direct access to these dicts is needed outside PTB handlers,
    # loading them here ensures they are populated.
    # We will use the PTB built-in persistence for user_settings and addresses.
    # `notified_announcements` and `region_street_map` are managed manually.
    notified_announcements.update(await load_data_async(NOTIFIED_FILE, dict, notified_lock))
    log_info(f"Loaded {len(notified_announcements)} notified announcement records.")

    region_street_map.update(await load_data_async(REGION_STREET_MAP_FILE, dict, region_map_lock))
    log_info(f"Loaded {len(region_street_map)} regions into region_street_map.")
    if not region_street_map:
        log_warning(f"{REGION_STREET_MAP_FILE} is empty or not found. Address validation features might be limited.")

# --- Model Download ---
def download_model_if_needed(model_url: str, model_path: Path, model_dir: Path):
    """Downloads the LLM model if it doesn't exist."""
    if model_path.exists():
        log_info(f"Model {model_path.name} already exists at {model_path}.")
        return True

    log_info(f"Model {model_path.name} not found. Attempting to download from {model_url}...")
    model_dir.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(model_url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        
        with open(model_path, 'wb') as f, tqdm(
            desc=model_path.name,
            total=total_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for chunk in response.iter_content(chunk_size=8192):
                size = f.write(chunk)
                bar.update(size)
        log_info(f"Model {model_path.name} downloaded successfully to {model_path}.")
        return True
    except requests.exceptions.RequestException as e:
        log_error(f"Failed to download model {model_path.name}: {e}", exc=e)
        if model_path.exists(): # Remove partially downloaded file
            try:
                os.remove(model_path)
            except OSError as oe:
                log_error(f"Could not remove partially downloaded model {model_path}: {oe}")
        return False
    except Exception as e:
        log_error(f"An unexpected error occurred during model download: {e}", exc=e)
        return False

# --- Announcement Processing ---
def create_announcement_hash(announcement: Dict[str, Any]) -> str:
    """Creates a unique hash for an announcement to avoid duplicates."""
    # Use key fields that define uniqueness. Source URL + a snippet of text or key date/location parts.
    # A simpler way is to hash a concatenated string of essential fields.
    # Ensure consistent order of keys if hashing the whole dict (not recommended due to potential new fields).
    key_fields = [
        str(announcement.get("source_url", "")),
        str(announcement.get("start_datetime", "")),
        str(announcement.get("end_datetime", "")),
        # Use a sorted representation of regions and streets for consistency
        ",".join(sorted(announcement.get("regions", []))),
        # Taking a snippet of streets/buildings as full text might be too volatile
        # Use the first street/building entry if available, or a hash of the list
        str(announcement.get("streets_buildings", [""])[0][:50]) # First 50 chars of first street entry
    ]
    # If "original_text_snippet" is reliable and concise, it can be part of the hash
    # key_fields.append(announcement.get("original_text_snippet", ""))
    # Normalize by converting all to string and joining
    unique_string = "|".join(key_fields).encode('utf-8')
    return hashlib.md5(unique_string).hexdigest()

async def format_notification_message(announcement: Dict[str, Any], lang: str) -> str:
    """Formats an announcement into a user-friendly notification message."""
    # Basic formatting, can be enhanced with more details from announcement
    # IMPROVEMENT: Use translations for field names and values where appropriate
    service_emoji_map = {
        "water": "💧",
        "gas": "🔥",
        "electric": "⚡️"
    }
    service_type = "unknown"
    if "vjur" in announcement.get("source_url", ""): service_type = "water"
    elif "gazprom" in announcement.get("source_url", ""): service_type = "gas"
    elif "ena" in announcement.get("source_url", ""): service_type = "electric"
    emoji = service_emoji_map.get(service_type, "⚠️")
    title_key = "notification_title_water" if service_type == "water" \
                else "notification_title_gas" if service_type == "gas" \
                else "notification_title_electric" if service_type == "electric" \
                else "notification_title_generic"
    title = get_translation(title_key, lang, emoji + " Внимание! Отключение") + f" {emoji}"
    lines = [f"*{title}*"] # Markdown
    if "shutdown_type" in announcement and announcement["shutdown_type"]:
        lines.append(f"{get_translation('shutdown_type', lang, 'Тип')}: _{announcement['shutdown_type']}_")
    if "start_datetime" in announcement and announcement["start_datetime"]:
        lines.append(f"{get_translation('start_time', lang, 'Начало')}: *{announcement['start_datetime']}*")
    if "end_datetime" in announcement and announcement["end_datetime"]:
        lines.append(f"{get_translation('end_time', lang, 'Окончание')}: *{announcement['end_datetime']}*")
    if "duration_hours" in announcement and announcement["duration_hours"]:
        lines.append(f"{get_translation('duration', lang, 'Продолжительность')}: {announcement['duration_hours']} {get_translation('hours_short', lang, 'ч')}.")
    if "regions" in announcement and announcement["regions"]:
        lines.append(f"{get_translation('regions', lang, 'Районы')}: {', '.join(announcement['regions'])}")
    if "streets_buildings" in announcement and announcement["streets_buildings"]:
        # lines.append(f"{get_translation('addresses', lang, 'Адреса')}:") # Too generic for a list
        for entry in announcement["streets_buildings"]:
             lines.append(f"📍 _{entry}_") # Using markdown for italics
    if "additional_details" in announcement and announcement["additional_details"]:
        lines.append(f"{get_translation('details', lang, 'Детали')}: {announcement['additional_details']}")
    # Source might be too technical for users, but good for admins/debugging
    # lines.append(f"\nИсточник: {announcement.get('source_url', 'N/A')}")
    return "\n".join(lines)

def is_address_match(user_addr_info: Dict[str, str], announcement: Dict[str, Any]) -> bool:
    """
    Checks if the user's address (region/street) matches the announcement.
    This needs to be quite sophisticated due to address variations.
    `user_addr_info` is like `{"region": "Ереван", "street": "Баграмяна"}`.
    `announcement` contains `regions` (list) and `streets_buildings` (list of strings).
    """
    # Placeholder for actual matching logic.
    # Current logic is very basic. For a real system, this needs fuzzy matching,
    # knowledge of district synonyms, street name variations (e.g. "ул. Х" vs "Х улица").
    # The AI address clarification output could be used here if it normalizes names.
    ann_regions = [r.lower().strip() for r in announcement.get("regions", [])]
    user_region = user_addr_info.get("region", "").lower().strip()
    user_street = user_addr_info.get("street", "").lower().strip()
    if not user_region or not user_street: # Should not happen with validated addresses
        return False
    # 1. Check region match
    region_match = False
    if user_region in ann_regions:
        region_match = True
    else: # Check for partial match or common administrative divisions if Yerevan
        if "ереван" in user_region or "yerevan" in user_region:
            for ar in ann_regions:
                if "ереван" in ar or "yerevan" in ar: # e.g., user subscribed to "Ереван", announcement for "Кентрон, Ереван"
                    region_match = True
                    break
        # Add more complex region mapping if needed (e.g. "Арабкир" is part of "Ереван")
    if not region_match:
        return False
    # 2. Check street match (if region matches)
    # This is the hardest part. `announcement["streets_buildings"]` is a list of strings like "ул. Абовяна 1-10, ул. Туманяна все дома"
    for detailed_address_str in announcement.get("streets_buildings", []):
        # Simple check: does the user's street name appear in the announcement string for this region?
        # This can lead to false positives (e.g., "Ленина" in "Ленинаканская") or false negatives.
        # Using SequenceMatcher for a slightly better match.
        # Consider tokenizing and comparing sets of words.
        if SequenceMatcher(None, user_street, detailed_address_str.lower()).quick_ratio() > 0.7: # Arbitrary threshold
             # Further check if a more specific part of detailed_address_str matches user_street better
            best_match_ratio = 0
            # Split by common delimiters to check parts of the string
            parts = re.split(r'[;,.]', detailed_address_str.lower())
            for part in parts:
                part = part.strip()
                # Remove common prefixes like "ул.", "пр." before matching
                part_cleaned = re.sub(r'^(ул\.?|пр\.?|улица|проспект)\s+', '', part).strip()
                # A simple direct check
                if user_street in part_cleaned: # e.g. "абовян" in "улица абовяна"
                    log_debug(f"Address match: User '{user_street}' in announcement part '{part_cleaned}' (Region: {user_region})")
                    return True
                # SequenceMatcher on cleaned parts
                ratio = SequenceMatcher(None, user_street, part_cleaned).quick_ratio()
                if ratio > best_match_ratio:
                    best_match_ratio = ratio

            if best_match_ratio > 0.85: # Higher threshold for part-based matching
                log_debug(f"Address match (via parts, ratio {best_match_ratio:.2f}): User '{user_street}' similar to announcement part in '{detailed_address_str}' (Region: {user_region})")
                return True
    
    log_debug(f"No street match for user '{user_street}' (Region: {user_region}) in announcement {announcement.get('original_text_snippet', 'N/A')}")
    return False

async def periodic_site_check_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodically fetches announcements, processes them, and notifies users."""
    job_start_time = timestamp()
    log_info("Periodic site check job started.")
    # Load bot status (maintenance mode)
    bot_status = await load_data_async(BOT_STATUS_FILE, lambda: {"is_maintenance": False, "maintenance_message": ""}, status_lock)
    if bot_status.get("is_maintenance"):
        log_info(f"Bot is in maintenance mode. Skipping periodic check. Message: {bot_status.get('maintenance_message')}")
        return
    if not is_ai_available():
        log_warning("AI model not available. Periodic site check job will be limited or skipped.")
        # Decide if you want to proceed without AI or just stop
        # For now, we proceed, but parsing will likely fail or return errors.
        # Parsers should handle "AI not available" gracefully.
    all_new_announcements: List[Dict] = []
    parsers = {
        "water": parse_all_water_announcements_async,
        "gas": parse_all_gas_announcements_async,
        "electric": parse_all_electric_announcements_async,
    }
    for service_name, parser_func in parsers.items():
        log_info(f"Checking for {service_name} announcements...")
        try:
            # Add a timeout for each parser to prevent job from hanging indefinitely
            service_announcements = await asyncio.wait_for(parser_func(), timeout=300.0) # 5 minutes timeout per service
            log_info(f"Found {len(service_announcements)} {service_name} announcements.")
            all_new_announcements.extend(service_announcements)
        except asyncio.TimeoutError:
            log_error(f"Timeout while parsing {service_name} announcements.")
        except Exception as e:
            log_error(f"Error parsing {service_name} announcements: {e}", exc=e)
    if not all_new_announcements:
        log_info("No new announcements found across all services.")
        # return # Keep running to check users due for ad or other tasks
    # Filter out already notified announcements and malformed ones
    valid_unseen_announcements = []
    async with notified_lock: # Ensure exclusive access to notified_announcements
        current_time = timestamp()
        # Cleanup old notified announcements (e.g., older than 7 days) to prevent indefinite growth
        # IMPROVEMENT: Pruning notified_announcements
        MAX_NOTIFIED_AGE_SECONDS = 7 * 24 * 60 * 60 
        pruned_count = 0
        global notified_announcements # Ensure we are modifying the global dict
        keys_to_delete = [
            h for h, ts in notified_announcements.items() 
            if current_time - ts > MAX_NOTIFIED_AGE_SECONDS
        ]
        for h_key in keys_to_delete:
            del notified_announcements[h_key]
            pruned_count +=1
        if pruned_count > 0:
            log_info(f"Pruned {pruned_count} old entries from notified_announcements.")
        for ann in all_new_announcements:
            if not isinstance(ann, dict) or "error" in ann or not ann.get("start_datetime"): # Basic validation
                log_warning(f"Skipping malformed or error announcement: {str(ann)[:200]}")
                continue
            ann_hash = create_announcement_hash(ann)
            if ann_hash not in notified_announcements:
                valid_unseen_announcements.append(ann)
                # Mark as notified immediately (or after successful user notifications)
                # For now, mark here to avoid reprocessing if notification fails for some users
                notified_announcements[ann_hash] = current_time 
            else:
                log_info(f"Announcement with hash {ann_hash} (Snippet: {ann.get('original_text_snippet', '')[:50]}) already processed.")
        if valid_unseen_announcements or pruned_count > 0: # Save if new ones added or old ones pruned
             await save_data_async(NOTIFIED_FILE, notified_announcements) # No lock needed, already under notified_lock
    if not valid_unseen_announcements:
        log_info("No new, valid, unseen announcements to notify users about.")
    else:
        log_info(f"Processing {len(valid_unseen_announcements)} new valid announcements for notification.")
    # --- Notify Users ---
    # Iterate through all users and their addresses.
    # This part needs access to `user_settings` and `addresses`.
    # If using PTB persistence, context.application.user_data should be the source.
    # For simplicity here, assuming `user_settings` and `addresses` are up-to-date global dicts.
    # In a PTB setup, you'd iterate `context.application.user_data.items()`.
    # We need user_data which is typically accessed via context in handlers.
    # For a job, we can access application.user_data
    # user_data_dict = context.application.user_data # This holds data for all users if persistence is set up
    # PTB's job queue passes the application object in context.application
    ptb_user_data: Dict[int, Dict[str, Any]] = context.application.user_data
    ptb_bot_data: Dict[str, Any] = context.application.bot_data
    # Create a local copy for iteration to avoid issues if modified during loop
    # user_settings_snapshot = dict(user_settings) # or from ptb_bot_data.get('user_settings_global', {})
    # addresses_snapshot = dict(addresses) # or from ptb_bot_data.get('addresses_global', {})
    users_to_notify_tasks = []
    for user_id_int, u_data in ptb_user_data.items():
        user_id_str = str(user_id_int)
        user_lang = u_data.get("lang", DEFAULT_LANG) # Get lang from persisted user_data
        user_frequency_setting = u_data.get("frequency", 21600) # Default to 6h
        user_current_tier = u_data.get("current_tier", "Free")
        user_sound_enabled = u_data.get("sound_enabled", True)
        # Check if user is due for a check based on their frequency
        # This job runs every `job_queue_interval_seconds` (e.g. 60s)
        # A user's specific frequency (e.g., 1h, 6h) means they should only get notifications
        # if enough time has passed since their *last notification* for a *similar type of event*,
        # or simply, this job processes *all new events* and filters by address.
        # The `user_frequency_setting` is more about how often the *bot checks for them*,
        # but this job checks for *everyone*.
        # So, the main filtering is by address match.
        user_tracked_addresses = u_data.get("addresses", []) # Get addresses from persisted user_data
        if not user_tracked_addresses:
            continue
        for ann in valid_unseen_announcements:
            for user_addr_info in user_tracked_addresses: # e.g. {"region": "...", "street": "..."}
                if is_address_match(user_addr_info, ann):
                    log_info(f"Address match for user {user_id_str} (Lang: {user_lang}, Addr: {user_addr_info['region']}/{user_addr_info['street']}) for announcement: {ann.get('original_text_snippet', '')[:50]}")
                    # Avoid sending the same matched announcement multiple times if user has multiple matching addresses (e.g. broad region + specific street)
                    # This check is tricky. For now, assume one notification per announcement per user.
                    # A simple way: add (user_id, ann_hash) to a temporary set for this job run.
                    message_text = await format_notification_message(ann, user_lang)
                    # Schedule the send_message task
                    users_to_notify_tasks.append(
                        send_message_robustly(context.bot, user_id_int, message_text, user_sound_enabled)
                    )
                    break # Found a match for this announcement for this user, move to next announcement for this user
    
    if users_to_notify_tasks:
        log_info(f"Gathered {len(users_to_notify_tasks)} notification tasks to send.")
        await asyncio.gather(*users_to_notify_tasks, return_exceptions=True) # Send all notifications concurrently
        log_info("Finished sending notifications for this batch.")

    # --- Send AD to free users if due ---
    current_job_time = timestamp()
    ad_message_template_ru = "CheckSiteUpdateBot: Отслеживайте отключения воды, газа, света в Армении! Узнайте о платных функциях для более частых проверок: /subscription" # TODO: Add to translations
    ad_tasks = []
    for user_id_int, u_data in ptb_user_data.items():
        user_id_str = str(user_id_int)
        if u_data.get("current_tier", "Free") == "Free":
            last_ad_ts = u_data.get(LAST_AD_TIMESTAMP_KEY, 0)
            if current_job_time - last_ad_ts > AD_INTERVAL_SECONDS:
                user_lang = u_data.get("lang", DEFAULT_LANG)
                # TODO: Get ad_message from translations
                ad_message = get_translation("ad_message_free_tier", user_lang, default_text=ad_message_template_ru)

                log_info(f"User {user_id_str} is due for an ad. Last ad: {datetime.fromtimestamp(last_ad_ts) if last_ad_ts else 'Never'}")
                ad_tasks.append(send_message_robustly(context.bot, user_id_int, ad_message, disable_notification=True)) # Ads should be silent
                u_data[LAST_AD_TIMESTAMP_KEY] = current_job_time # Update last ad timestamp
    if ad_tasks:
        log_info(f"Sending ads to {len(ad_tasks)} free users.")
        await asyncio.gather(*ad_tasks, return_exceptions=True)
        # Note: If using PicklePersistence or JSONPersistence, user_data changes are automatically saved.
        # If managing user_data manually, ensure it's saved after updating LAST_AD_TIMESTAMP_KEY.
    job_duration = timestamp() - job_start_time
    log_info(f"Periodic site check job finished in {job_duration:.2f} seconds.")

async def send_message_robustly(bot, chat_id: int, text: str, sound_enabled: Optional[bool] = True, **kwargs) -> bool:
    """Sends a message with error handling for common Telegram API errors."""
    disable_notification_for_send = not sound_enabled # If sound is False, disable notification
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN, # Or HTML, ensure `text` is formatted accordingly
            disable_notification=disable_notification_for_send,
            **kwargs
        )
        log_info(f"Message sent to {chat_id}. Sound: {sound_enabled}. Text snippet: {text[:70]}...")
        return True
    except Forbidden:
        log_warning(f"Bot was blocked by user {chat_id} or kicked from group. Cannot send message.")
        # Here you might want to mark user as inactive in your database/settings
        # e.g., context.application.user_data[chat_id]['active'] = False
    except RetryAfter as e:
        log_warning(f"Flood control exceeded for chat {chat_id}. Retry after {e.retry_after}s. Message: {text[:50]}")
        await asyncio.sleep(e.retry_after + 1)
        # Optionally retry: return await send_message_robustly(bot, chat_id, text, sound_enabled, **kwargs)
    except (TimedOut, NetworkError) as e:
        log_error(f"Telegram network error for chat {chat_id}: {e}. Message: {text[:50]}", exc=e)
        # Optionally retry after a delay
    except Exception as e:
        log_error(f"Failed to send message to {chat_id}: {e}. Message: {text[:50]}", exc=e)
    return False

# --- Command Handlers (Examples, many are stubs or need refinement) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    user = update.effective_user
    if not user: return # Should not happen
    user_id_str = str(user.id)
    # Initialize user data if new, or retrieve existing
    # PTB persistence handles this: context.user_data is specific to this user.
    # Default language setting
    if "lang" not in context.user_data:
        context.user_data["lang"] = DEFAULT_LANG
        # You might want to ask for language on first start
    if "current_tier" not in context.user_data: # Default tier
        context.user_data["current_tier"] = "Free"
    if "sound_enabled" not in context.user_data:
        context.user_data["sound_enabled"] = True # Sound on by default
    if "addresses" not in context.user_data:
        context.user_data["addresses"] = []
    lang = context.user_data["lang"]
    context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE # Reset step
    welcome_message = get_translation("welcome", lang, name=user.first_name)
    await update.message.reply_text(
        welcome_message,
        reply_markup=get_reply_markup_for_lang(lang, context, user_id_str)
    )
    # Ask for language choice on first start more explicitly
    if "lang_chosen_once" not in context.user_data:
        await choose_language_command(update, context, initial_setup=True)
        context.user_data["lang_chosen_once"] = True

async def choose_language_command(update: Update, context: ContextTypes.DEFAULT_TYPE, initial_setup: bool = False) -> None:
    """Allows the user to choose the interface language."""
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG) # Current lang for the prompt itself
    buttons = [
        [InlineKeyboardButton("Հայերեն  Armenian 🇦🇲", callback_data=f"{CALLBACK_PREFIX_LANGUAGE}hy")],
        [InlineKeyboardButton("Русский Russian 🇷🇺", callback_data=f"{CALLBACK_PREFIX_LANGUAGE}ru")],
        [InlineKeyboardButton("English 🇬🇧", callback_data=f"{CALLBACK_PREFIX_LANGUAGE}en")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    prompt_text = get_translation("choose_language_prompt", lang)
    if initial_setup:
        prompt_text = get_translation("choose_language_initial_prompt", lang, default_text="Please select your preferred language to continue:")
    if update.callback_query: # If called from a callback (e.g. back button)
        await update.callback_query.edit_message_text(prompt_text, reply_markup=markup)
    else: # If called from a command
        await update.message.reply_text(prompt_text, reply_markup=markup)
    context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.AWAITING_LANGUAGE_CHOICE

async def handle_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles language selection from InlineKeyboard."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not user: return
    chosen_lang = query.data.split(CALLBACK_PREFIX_LANGUAGE)[1]
    context.user_data["lang"] = chosen_lang
    context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
    confirmation_text = get_translation("language_changed_confirmation", chosen_lang, lang_name=chosen_lang.upper())
    await query.edit_message_text(text=confirmation_text)
    # Also send a message with the new main keyboard in the chosen language
    await context.bot.send_message(
        chat_id=user.id,
        text=get_translation("main_menu_now_active", chosen_lang), # "Main menu is now active in [Language]."
        reply_markup=get_reply_markup_for_lang(chosen_lang, context, str(user.id))
    )
    log_info(f"User {user.id} changed language to {chosen_lang}")
# ... (Other command handlers like add_address, remove_address_command, etc. need similar review and updates)
# ... (handle_text_message needs to route based on context.user_data[USER_DATA_STEP_KEY])
# IMPROVEMENT: Example of a more robust `add_address_command` flow
async def add_address_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    # In a real scenario, you'd fetch regions from region_street_map or a predefined list.
    # For now, using a placeholder list. These should be translated.
    available_regions = list(region_street_map.keys()) if region_street_map else ["Ереван", "Котайк", "Арарат", "Ширак", "Лори", "Сюник", "Тавуш", "Армавир", "Гегаркуник", "Арагацотн", "Вайоц Дзор"]
    if not available_regions:
        await update.message.reply_text(get_translation("no_regions_configured", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
        return
    buttons = [[KeyboardButton(get_translation(f"region_{reg.lower()}", lang, default_text=reg))] for reg in available_regions]
    # Add a cancel button
    buttons.append([KeyboardButton(get_translation("cancel_btn", lang))])
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(get_translation("choose_region_prompt", lang), reply_markup=markup)
    context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.AWAITING_REGION_CHOICE

async def handle_region_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    chosen_region_text = update.message.text
    # Reverse translate if needed, or map from display name to canonical name
    # For now, assume chosen_region_text is the canonical name
    # available_regions = list(region_street_map.keys()) if region_street_map else [...] # Get regions again
    # Find the canonical region name if translated buttons were used. This is complex.
    # Simpler: store canonical name in button callback_data if using InlineKeyboard for regions.
    # With ReplyKeyboard, the text itself is sent.
    # Basic cancel
    if chosen_region_text == get_translation("cancel_btn", lang):
        await update.message.reply_text(get_translation("action_cancelled", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
        context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
        return
    context.user_data[USER_DATA_SELECTED_REGION_KEY] = chosen_region_text # Store the chosen region
    await update.message.reply_text(
        get_translation("enter_street_prompt", lang, region=chosen_region_text),
        reply_markup=ReplyKeyboardMarkup([[get_translation("cancel_btn", lang)]], resize_keyboard=True, one_time_keyboard=True) # Just a cancel button
    )
    context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.AWAITING_STREET_INPUT

async def handle_street_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    raw_street_text = update.message.text.strip()
    if raw_street_text == get_translation("cancel_btn", lang):
        await update.message.reply_text(get_translation("action_cancelled", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
        context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
        return
    if not raw_street_text or len(raw_street_text) < 2: # Basic validation
        await update.message.reply_text(get_translation("street_too_short_error", lang))
        # Keep USER_DATA_STEP_KEY as AWAITING_STREET_INPUT to allow retry
        return
    selected_region = context.user_data.get(USER_DATA_SELECTED_REGION_KEY)
    if not selected_region: # Should not happen if flow is correct
        await update.message.reply_text(get_translation("error_region_not_selected", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
        context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
        return
    full_address_input_for_ai = f"{selected_region}, {raw_street_text}"
    # Use AI to clarify/validate street against region
    # await update.message.reply_text(get_translation("address_being_verified_ai", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id))) # Inform user
    # Show typing action
    await context.bot.send_chat_action(chat_id=user.id, action="typing")
    # Pass region_street_map for potential cross-validation by AI or its caller
    ai_address_result = await clarify_address_ai(full_address_input_for_ai, region_street_map)
    if "error" in ai_address_result or not ai_address_result.get("street_identified"):
        error_comment = ai_address_result.get("comment", "Could not understand the street name.")
        await update.message.reply_text(
            get_translation("ai_street_clarification_failed", lang, error=error_comment, region=selected_region) + "\n" + \
            get_translation("please_try_again_street", lang)
        )
        # context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.AWAITING_STREET_INPUT # Allow retry
        return # Keep step as AWAITING_STREET_INPUT
    # For simplicity, we trust AI's region if it differs, or use user's selected_region
    # A more robust system would handle mismatches or low certainty.
    final_region = ai_address_result.get("region_identified", selected_region)
    final_street = ai_address_result["street_identified"]
    context.user_data[USER_DATA_TEMP_ADDRESS_KEY] = {"region": final_region, "street": final_street}
    confirmation_text = get_translation(
        "confirm_address_prompt", lang,
        region=final_region,
        street=final_street
    )
    buttons = [
        [InlineKeyboardButton(get_translation("confirm_yes", lang), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}yes")],
        [InlineKeyboardButton(get_translation("confirm_no_retry", lang), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}no")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(confirmation_text, reply_markup=markup)
    context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.AWAITING_ADDRESS_CONFIRMATION

async def handle_address_confirmation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    choice = query.data.split(CALLBACK_PREFIX_ADDRESS_CONFIRM)[1]
    if choice == "yes":
        temp_address = context.user_data.get(USER_DATA_TEMP_ADDRESS_KEY)
        if not temp_address:
            await query.edit_message_text(get_translation("error_generic_try_again", lang))
            context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
            return
        # Add to user's persisted addresses
        if "addresses" not in context.user_data: context.user_data["addresses"] = []
        # Check if address already exists
        addr_exists = any(a["region"] == temp_address["region"] and a["street"] == temp_address["street"] for a in context.user_data["addresses"])
        if addr_exists:
            await query.edit_message_text(get_translation("address_already_exists", lang, region=temp_address["region"], street=temp_address["street"]))
        else:
            context.user_data["addresses"].append(temp_address)
            await query.edit_message_text(get_translation("address_added_successfully", lang, region=temp_address["region"], street=temp_address["street"]))
            log_info(f"User {user.id} added address: {temp_address}")
        # Send main menu keyboard again
        await context.bot.send_message(chat_id=user.id, text=get_translation("main_menu_prompt", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
    elif choice == "no":
        await query.edit_message_text(get_translation("add_address_retry_prompt", lang))
        # Restart the add address flow by prompting for region again
        # To do this cleanly, might need to call add_address_command logic or set step to AWAITING_REGION_CHOICE
        # For simplicity, just take them to main menu and they can try "Add Address" again
        await context.bot.send_message(chat_id=user.id, text=get_translation("main_menu_prompt", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
    context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
    context.user_data.pop(USER_DATA_TEMP_ADDRESS_KEY, None)
    context.user_data.pop(USER_DATA_SELECTED_REGION_KEY, None)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles general text messages based on the user's current step."""
    user = update.effective_user
    if not user or not update.message or not update.message.text: return
    user_id_str = str(user.id)
    lang = context.user_data.get("lang", DEFAULT_LANG)
    text = update.message.text
    current_step = context.user_data.get(USER_DATA_STEP_KEY, UserStepsEnum.NONE)
    # Global commands accessible regardless of step (like cancel)
    if text == get_translation("cancel_btn", lang): # Assuming "Cancel" is a general keyword
        context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
        await update.message.reply_text(get_translation("action_cancelled", lang), reply_markup=get_reply_markup_for_lang(lang, context, user_id_str))
        return
    # Step-based routing
    if current_step == UserStepsEnum.AWAITING_REGION_CHOICE:
        await handle_region_choice(update, context)
    elif current_step == UserStepsEnum.AWAITING_STREET_INPUT:
        await handle_street_input(update, context)
    elif current_step == UserStepsEnum.AWAITING_FREQUENCY_CHOICE:
        # This specific handler is in handlers.py, but text input needs routing here
        await handle_frequency_choice(update, context, user_settings, translations, save_user_settings_async_wrapper_ptb(context))
    # ... other steps for removing address, checking address etc.
    # Button-like text commands (main menu)
    elif text == get_translation("add_address_btn", lang):
        await add_address_command(update, context)
    elif text == get_translation("remove_address_btn", lang):
        await remove_address_command(update, context) # Implement this
    elif text == get_translation("show_addresses_btn", lang):
        await address_list_command(update, context) # Implement this
    elif text == get_translation("clear_all_btn", lang):
        await clear_all_addresses_command(update, context) # Implement this
    elif text == get_translation("check_address_btn", lang):
        await check_specific_address_command(update, context) # Implement this
    elif text == get_translation("set_frequency_btn", lang):
        # This handler is in handlers.py, call it
        await set_frequency_command(update, context, user_settings, translations)
    elif text == get_translation("change_language_btn", lang):
        await choose_language_command(update, context)
    elif text == get_translation("help_btn", lang):
        await show_help_command(update, context) # Implement this
    else:
        # Fallback for unrecognized text if not in a specific step
        # Check if AI is available and the text is long enough to be a query
        if is_ai_available() and len(text) > 10: # Arbitrary length
             # Could try to interpret as a general query or address check
             # For now, just a generic reply
            await update.message.reply_text(get_translation("unknown_command", lang), reply_markup=get_reply_markup_for_lang(lang, context, user_id_str))
        else:
            await update.message.reply_text(get_translation("unknown_command_short", lang), reply_markup=get_reply_markup_for_lang(lang, context, user_id_str))
# --- Wrappers for saving data when using PTB persistence ---
# PTB persistence saves user_data and bot_data automatically.
# If you have global dicts that are NOT part of user_data/bot_data and need saving,
# these wrappers would be for them.
# For `notified_announcements` and `region_street_map`, they are saved in their respective load/save calls.
# `user_settings` and `addresses` are now part of `context.user_data`.
def save_user_settings_async_wrapper_ptb(context: ContextTypes.DEFAULT_TYPE) -> Callable:
    """
    Wrapper for saving user_settings (which are now in context.user_data).
    PTB's persistence handles saving automatically. This function might only be needed
    if you were saving to a separate user_settings.json AND wanted to trigger it from handlers.py.
    Since user settings are in context.user_data, this wrapper is mostly a placeholder
    to show how handlers.py could trigger a save if it were needed.
    """
    async def save_needed_data():
        # context.application.persistence.flush() # Explicitly flush if needed, usually automatic
        log_info("User data (including settings) will be saved by PTB persistence.")
        pass # PTB persistence handles this.
    return save_needed_data

# Placeholder for other commands to be implemented or fleshed out
async def remove_address_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    user_addresses = context.user_data.get("addresses", [])
    if not user_addresses:
        await update.message.reply_text(get_translation("no_addresses_to_remove", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
        return
    buttons = []
    for i, addr in enumerate(user_addresses):
        # Format address for display, ensure it's not too long for a button
        addr_text = f"{addr['region']}, {addr['street']}"
        max_len = 30 # Max button text length (approx)
        display_text = (addr_text[:max_len-3] + "...") if len(addr_text) > max_len else addr_text
        buttons.append([InlineKeyboardButton(display_text, callback_data=f"{CALLBACK_PREFIX_REMOVE_ADDRESS}{i}")])
    buttons.append([InlineKeyboardButton(get_translation("cancel_btn", lang), callback_data=f"{CALLBACK_PREFIX_REMOVE_ADDRESS}cancel")])
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(get_translation("select_address_to_remove_prompt", lang), reply_markup=markup)
    context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.AWAITING_ADDRESS_TO_REMOVE # Or handle directly in callback

async def handle_remove_address_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    data_part = query.data.split(CALLBACK_PREFIX_REMOVE_ADDRESS)[1]
    if data_part == "cancel":
        await query.edit_message_text(get_translation("action_cancelled", lang))
        await context.bot.send_message(chat_id=user.id, text=get_translation("main_menu_prompt", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
        context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
        return
    try:
        address_idx_to_remove = int(data_part)
        user_addresses = context.user_data.get("addresses", [])
        if 0 <= address_idx_to_remove < len(user_addresses):
            removed_addr = user_addresses.pop(address_idx_to_remove)
            await query.edit_message_text(get_translation("address_removed_successfully", lang, region=removed_addr["region"], street=removed_addr["street"]))
            log_info(f"User {user.id} removed address: {removed_addr}")
        else:
            await query.edit_message_text(get_translation("error_invalid_selection", lang))
    except ValueError:
        await query.edit_message_text(get_translation("error_generic_try_again", lang))
    await context.bot.send_message(chat_id=user.id, text=get_translation("main_menu_prompt", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
    context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE


async def address_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    user_addresses = context.user_data.get("addresses", [])
    if not user_addresses:
        await update.message.reply_text(get_translation("no_addresses_added", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
        return
    message_lines = [get_translation("your_tracked_addresses_list", lang) + ":"]
    for i, addr in enumerate(user_addresses):
        message_lines.append(f"{i+1}. {addr['region']} - {addr['street']}")
    await update.message.reply_text("\n".join(message_lines), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))

async def clear_all_addresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # IMPROVEMENT: Add confirmation step
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    context.user_data["addresses"] = []
    await update.message.reply_text(get_translation("all_addresses_cleared", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
    log_info(f"User {user.id} cleared all addresses.")

async def check_specific_address_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This would be similar to add_address but instead of saving, it performs an immediate check.
    # It would involve asking for region, then street, then querying current announcements.
    # For brevity, not fully implemented here.
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    await update.message.reply_text(get_translation("feature_not_fully_implemented", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))

async def show_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    # The help text from translations.py already includes Markdown formatting for contacts
    help_text_key = "help_text_detailed" # Ensure this key exists in translations.py
    help_text_content = get_translation(help_text_key, lang, default_text="Default help text if key not found.")
    # Ensure contact details are appended if not part of the main help text key
    # This is now handled in translations.py directly in the "help_text_detailed"
    # contact_info = f"\n\n{get_translation('contact_us_info', lang)}\n{CLICKABLE_PHONE_MD}\n{CLICKABLE_ADDRESS_MD}"
    # full_help_text = help_text_content + contact_info
    await update.message.reply_text(
        help_text_content, # Use the direct content which should include contacts
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True, # Good practice for help messages
        reply_markup=get_reply_markup_for_lang(lang, context, str(user.id))
    )

async def show_statistics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Placeholder for statistics
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    await update.message.reply_text(get_translation("stats_not_implemented_yet", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))

async def show_subscription_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Placeholder for subscription info
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    await update.message.reply_text(get_translation("subscription_info_placeholder", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))

async def show_sound_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    current_sound_status = context.user_data.get("sound_enabled", True)
    status_text = get_translation("sound_on", lang) if current_sound_status else get_translation("sound_off", lang)
    button_text = get_translation("turn_sound_off", lang) if current_sound_status else get_translation("turn_sound_on", lang)
    message_text = get_translation("current_sound_status_prompt", lang, status=status_text)
    buttons = [[InlineKeyboardButton(button_text, callback_data=f"{CALLBACK_PREFIX_SOUND}{'off' if current_sound_status else 'on'}")],
               [InlineKeyboardButton(get_translation("back_to_main_menu_btn", lang), callback_data=f"{CALLBACK_PREFIX_SOUND}cancel")]]
    markup = InlineKeyboardMarkup(buttons)
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=markup)
    else:
        await update.message.reply_text(message_text, reply_markup=markup)

async def handle_sound_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not user: return
    lang = context.user_data.get("lang", DEFAULT_LANG)
    action = query.data.split(CALLBACK_PREFIX_SOUND)[1]
    if action == "on":
        context.user_data["sound_enabled"] = True
        await query.edit_message_text(get_translation("sound_turned_on_confirmation", lang))
    elif action == "off":
        context.user_data["sound_enabled"] = False
        await query.edit_message_text(get_translation("sound_turned_off_confirmation", lang))
    elif action == "cancel":
        await query.edit_message_text(get_translation("action_cancelled", lang))
        # No need to resend main menu keyboard if just editing a message.
        # Could send a new message if preferred.
        # For now, let user use the reply keyboard or /start
    # If not cancelling, show updated status and offer main menu
    if action != "cancel":
         await context.bot.send_message(chat_id=user.id, text=get_translation("main_menu_prompt", lang), reply_markup=get_reply_markup_for_lang(lang, context, str(user.id)))
    log_info(f"User {user.id} set sound_enabled to {context.user_data['sound_enabled']}")

async def post_init(application: Application) -> None:
    """Tasks to run after the bot application has been initialized."""
    # Load data that isn't handled by PTB's persistence directly at startup
    await load_all_data()
    # Set bot commands for different languages (optional, but good for UX)
    # This is just an example for one language set.
    # You might want to set this per user if your bot heavily relies on command list.
    commands_hy = [
        BotCommand("start", "Սկսել / Հիմնական մենյու"),
        BotCommand("language", "Փոխել լեզուն"),
        BotCommand("myaddresses", "Իմ հասցեները"),
        BotCommand("addaddress", "Ավելացնել հասցե"),
        BotCommand("help", "Օգնություն"),
    ]
    # You can set commands for specific languages or a general set
    # await application.bot.set_my_commands(commands_hy, language_code="hy")
    # For a general set:
    await application.bot.set_my_commands(commands_hy) # Will use these for users with "hy" if no specific language match, or as default
    log_info("Bot commands set.")
    # Download LLM model if not present
    # Ensure AI_MODELS_DIR and LOCAL_MODEL_PATH are correctly defined Path objects
    model_dir_path = Path(AI_MODELS_DIR)
    if not download_model_if_needed(MODEL_URL, LOCAL_MODEL_PATH, model_dir_path):
        log_error(f"LLM Model could not be downloaded. AI features might be impacted.")
    else:
        # Try to initialize ai_engine again if it failed due to missing model
        if not is_ai_available() and LOCAL_MODEL_PATH.exists():
            log_info("Attempting to re-initialize AI engine after model download...")
            # This is tricky as llm_instance is module-level in ai_engine.
            # A better approach is for ai_engine to have a load_model() function
            # that smart_bot can call after ensuring the model file exists.
            # For now, assume ai_engine will pick it up on next import/call if it checks os.path.exists.
            # Or, if ai_engine is structured as a class, instantiate it here.
            pass # The check `is_ai_available()` will be more accurate now.

# --- Main Bot Setup ---
def main() -> None:
    """Starts the bot."""
    if not BOT_TOKEN: # Already checked, but good to be defensive
        return
    # IMPROVEMENT: Use JSONPersistence
    persistence = JSONPersistence(filepath=PERSISTENCE_FILE)
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .persistence(persistence)
        .post_init(post_init) # Run after setup
        .build()
    )
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("language", choose_language_command))
    # The handlers.py `set_frequency_command` and `handle_frequency_choice` need to be adapted
    # to use context.user_data instead of global user_settings dicts if they are to be used directly.
    # For now, integrating frequency choice into main text handler or specific commands.
    # application.add_handler(CommandHandler("setfrequency", set_frequency_command)) # From handlers.py
    # Command aliases or direct commands for main menu items
    application.add_handler(CommandHandler("addaddress", add_address_command))
    application.add_handler(CommandHandler("removeaddress", remove_address_command))
    application.add_handler(CommandHandler("myaddresses", address_list_command))
    application.add_handler(CommandHandler("clearall", clear_all_addresses_command))
    application.add_handler(CommandHandler("checkaddress", check_specific_address_command))
    application.add_handler(CommandHandler("help", show_help_command))
    application.add_handler(CommandHandler("stats", show_statistics_command))
    application.add_handler(CommandHandler("subscription", show_subscription_options))
    application.add_handler(CommandHandler("sound", show_sound_settings_command))
    # Callback query handlers
    application.add_handler(CallbackQueryHandler(handle_language_callback, pattern=f"^{CALLBACK_PREFIX_LANGUAGE}"))
    application.add_handler(CallbackQueryHandler(handle_address_confirmation_callback, pattern=f"^{CALLBACK_PREFIX_ADDRESS_CONFIRM}"))
    application.add_handler(CallbackQueryHandler(handle_remove_address_callback, pattern=f"^{CALLBACK_PREFIX_REMOVE_ADDRESS}"))
    application.add_handler(CallbackQueryHandler(handle_sound_settings_callback, pattern=f"^{CALLBACK_PREFIX_SOUND}"))
    # application.add_handler(CallbackQueryHandler(handle_subscription_callback, pattern=f"^{CALLBACK_PREFIX_SUBSCRIBE}")) # From original, ensure handler exists
    # application.add_handler(CallbackQueryHandler(handle_help_action_callback, pattern=f"^{CALLBACK_PREFIX_HELP}")) # From original
    # application.add_handler(CallbackQueryHandler(handle_faq_item_callback, pattern=f"^{CALLBACK_PREFIX_FAQ_ITEM}")) # From original
    # Message handler for text messages (must be one of the last handlers)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    # Job Queue
    job_queue: Optional[JobQueue] = application.job_queue
    if job_queue:
        # Check interval carefully. 60s is frequent.
        # If parsers are slow or rate-limited, this could be an issue.
        job_queue_interval_seconds = int(os.getenv("JOB_QUEUE_INTERVAL_SECONDS", 300)) # Default 5 mins
        # Run first job after a short delay to allow bot to fully start
        first_run_delay = int(os.getenv("JOB_QUEUE_FIRST_DELAY_SECONDS", 15)) 
        job_queue.run_repeating(
            periodic_site_check_job,
            interval=job_queue_interval_seconds,
            first=first_run_delay,
            name="periodic_site_check" # Naming the job is good practice
        )
        log_info(f"JobQueue 'periodic_site_check_job' scheduled every {job_queue_interval_seconds}s, first run in {first_run_delay}s.")
    else:
        log_error("JobQueue is not available. Periodic checks will not run.")
    log_info("Bot is starting polling...")
    application.run_polling()

if __name__ == "__main__":
    main()

# <3
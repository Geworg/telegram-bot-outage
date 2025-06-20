# --- Standard Library ---
import asyncio
import logging
import os
import re
import sys
from enum import Enum, auto
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Callable, Any

# --- Third-party Libraries ---
from dotenv import load_dotenv
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    User
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    JobQueue
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import Forbidden, BadRequest, TimedOut, NetworkError

# --- Local Modules ---
import db_manager
import ai_engine
import api_clients
from translations import translations, TIER_LABELS

# Import parsing functions
from parse_water import parse_all_water_announcements_async
from parse_gas import parse_all_gas_announcements_async
from parse_electric import parse_all_electric_announcements_async


# --- Initial Setup ---
load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# --- Constants ---
class UserSteps(Enum):
    NONE = auto()
    AWAITING_INITIAL_LANG = auto()
    AWAITING_REGION = auto()
    AWAITING_ADDRESS = auto()
    AWAITING_SILENT_MODE_TIMES = auto()
    CONFIRM_SILENT_MODE_TIMES = auto() # New step for confirmation

# --- Global Dictionaries ---
user_data_temp: Dict[int, Dict[str, Any]] = {} # To store temporary data for multi-step conversations

# --- Helper Functions ---
def get_translation(key: str, lang_code: str) -> str:
    """Retrieves the translated string for a given key and language code."""
    return translations.get(key, {}).get(lang_code, key) # Fallback to key if translation not found

def get_tier_label(tier_key: str, lang_code: str) -> str:
    """Retrieves the translated tier label."""
    return TIER_LABELS.get(tier_key, {}).get(lang_code, tier_key)

async def set_user_silent_mode_times(user_id: int, start_time_str: str, end_time_str: str):
    """
    Sets silent mode start and end times for a user in the database.
    """
    try:
        # Parse time strings into datetime.time objects
        start_time = dt_time.fromisoformat(start_time_str)
        end_time = dt_time.fromisoformat(end_time_str)

        settings = {
            "silent_mode_enabled": True, # Automatically enable silent mode if times are set
            "silent_mode_start_time": start_time,
            "silent_mode_end_time": end_time
        }
        await db_manager.update_user_sound_settings(user_id, settings)
        return True
    except ValueError as e:
        log.error(f"Error parsing silent mode times for user {user_id}: {e}")
        return False
    except Exception as e:
        log.error(f"Error updating silent mode times in DB for user {user_id}: {e}")
        return False

# --- Telegram Bot Commands & Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    user = update.effective_user
    if not user:
        log.error("Start command received without effective user.")
        return

    user_db = await db_manager.get_user(user.id)
    lang_code = user_db.get('language_code', 'en') if user_db else 'en' # Default to 'en'

    if not user_db:
        # New user, ask for language
        keyboard = [
            [KeyboardButton("English 🇺🇸"), KeyboardButton("Русский 🇷🇺"), KeyboardButton("Հայերեն 🇦🇲")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "Welcome! Please choose your language:\nԲարի գալուստ! Խնդրում ենք ընտրել ձեր լեզուն:\nДобро пожаловать! Пожалуйста, выберите ваш язык:",
            reply_markup=reply_markup
        )
        user_data_temp[user.id] = {"step": UserSteps.AWAITING_INITIAL_LANG}
        log.info(f"New user {user.id} started, awaiting language selection.")
    else:
        # Existing user, send main menu
        await db_manager.create_or_update_user(user.id, lang_code) # Update last_active_at
        await send_main_menu(user.id, context, lang_code)
        log.info(f"Existing user {user.id} re-started, main menu sent.")

async def send_main_menu(user_id: int, context: ContextTypes.DEFAULT_TYPE, lang_code: str, message_id: Optional[int] = None) -> None:
    """Sends the main menu to the user, optionally editing an existing message."""
    user_data_temp.pop(user_id, None) # Clear any pending steps
    user_data_temp[user_id] = {"step": UserSteps.NONE} # Reset user step to NONE

    keyboard = [
        [
            KeyboardButton(get_translation("add_address_btn", lang_code)),
            KeyboardButton(get_translation("my_addresses_btn", lang_code))
        ],
        [
            KeyboardButton(get_translation("check_outage_btn", lang_code)),
            KeyboardButton(get_translation("frequency_btn", lang_code))
        ],
        [
            KeyboardButton(get_translation("sound_settings_btn", lang_code)),
            KeyboardButton(get_translation("stats_btn", lang_code)) # Changed to "stats_btn"
        ],
        [
            KeyboardButton(get_translation("contact_support_btn", lang_code)),
            KeyboardButton(get_translation("about_bot_btn", lang_code))
        ]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    text = get_translation("main_menu_greeting", lang_code)

    if message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        except BadRequest as e:
            log.warning(f"Could not edit message {message_id} for user {user_id}: {e}. Sending new message instead.")
            await context.bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await context.bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


async def my_addresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /myaddresses command, showing user's saved addresses."""
    user = update.effective_user
    if not user: return
    
    user_db = await db_manager.get_user(user.id)
    lang_code = user_db.get('language_code', 'en') if user_db else 'en'
    
    addresses = await db_manager.get_user_addresses(user.id)
    if not addresses:
        await context.bot.send_message(user.id, get_translation("no_addresses_yet", lang_code))
        return

    text = get_translation("your_addresses", lang_code) + "\n"
    keyboard = []
    for addr in addresses:
        text += f"• {addr['full_address_text']} (/del_{addr['address_id']})\n"
        keyboard.append([InlineKeyboardButton(f"❌ {addr['full_address_text']}", callback_data=f"del_addr_{addr['address_id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(user.id, text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


async def frequency_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /frequency command, allowing users to set notification frequency."""
    user = update.effective_user
    if not user: return

    user_db = await db_manager.get_user(user.id)
    lang_code = user_db.get('language_code', 'en') if user_db else 'en'
    current_freq_seconds = user_db.get('frequency_seconds', 21600) # Default 6 hours

    current_freq_hours = current_freq_seconds // 3600
    
    keyboard = [
        [
            InlineKeyboardButton(get_translation("freq_3_hours", lang_code), callback_data="set_freq_10800"),
            InlineKeyboardButton(get_translation("freq_6_hours", lang_code), callback_data="set_freq_21600")
        ],
        [
            InlineKeyboardButton(get_translation("freq_12_hours", lang_code), callback_data="set_freq_43200"),
            InlineKeyboardButton(get_translation("freq_24_hours", lang_code), callback_data="set_freq_86400")
        ],
        [InlineKeyboardButton(get_translation("back_to_main_menu", lang_code), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        user.id,
        get_translation("frequency_message", lang_code).format(current_freq_hours=current_freq_hours),
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /stats command, showing bot statistics.
    Only accessible by ADMIN_USER_IDS.
    """
    user = update.effective_user
    if not user: return

    admin_ids_str = os.getenv("ADMIN_USER_IDS")
    admin_ids = [int(aid.strip()) for aid in admin_ids_str.split(',') if aid.strip().isdigit()] if admin_ids_str else []

    user_db = await db_manager.get_user(user.id)
    lang_code = user_db.get('language_code', 'en') if user_db else 'en'

    if user.id not in admin_ids:
        await context.bot.send_message(user.id, get_translation("admin_unauthorized", lang_code))
        log.warning(f"Unauthorized access attempt to /stats by user {user.id}")
        return

    log.info(f"Admin user {user.id} requested stats.")
    stats = await db_manager.get_system_stats()
    
    total_users = stats.get('total_users', 0)
    total_addresses = stats.get('total_addresses', 0)

    stats_message = get_translation("stats_message", lang_code).format(
        total_users=total_users,
        total_addresses=total_addresses
    )
    await context.bot.send_message(user.id, stats_message, parse_mode=ParseMode.MARKDOWN)

async def clear_addresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /clearaddresses command."""
    user = update.effective_user
    if not user: return

    user_db = await db_manager.get_user(user.id)
    lang_code = user_db.get('language_code', 'en') if user_db else 'en'
    
    deleted_count = await db_manager.clear_all_user_addresses(user.id)
    if deleted_count > 0:
        await context.bot.send_message(user.id, get_translation("all_addresses_cleared", lang_code).format(count=deleted_count))
        log.info(f"User {user.id} cleared {deleted_count} addresses.")
    else:
        await context.bot.send_message(user.id, get_translation("no_addresses_to_clear", lang_code))

async def qa_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /qa command for asking questions about outages."""
    user = update.effective_user
    if not user: return

    user_db = await db_manager.get_user(user.id)
    lang_code = user_db.get('language_code', 'en') if user_db else 'en'
    
    await context.bot.send_message(user.id, get_translation("qa_prompt", lang_code))
    user_data_temp[user.id] = {"step": UserSteps.AWAITING_ADDRESS, "context": "qa_check"} # Reuse AWAITING_ADDRESS for QA

async def sound_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /sound command, leading to sound notification settings.
    """
    user = update.effective_user
    if not user: return

    user_db = await db_manager.get_user(user.id)
    lang_code = user_db.get('language_code', 'en') if user_db else 'en'
    
    sound_enabled = user_db.get('notification_sound_enabled', True)
    silent_mode_enabled = user_db.get('silent_mode_enabled', False)
    silent_start_time = user_db.get('silent_mode_start_time', dt_time(23, 0))
    silent_end_time = user_db.get('silent_mode_end_time', dt_time(7, 0))

    keyboard = [
        [InlineKeyboardButton(get_translation("toggle_sound_on" if not sound_enabled else "toggle_sound_off", lang_code), callback_data="toggle_sound")],
        [InlineKeyboardButton(get_translation("toggle_silent_mode_on" if not silent_mode_enabled else "toggle_silent_mode_off", lang_code), callback_data="toggle_silent_mode")],
        [InlineKeyboardButton(get_translation("set_silent_mode_times", lang_code), callback_data="set_silent_mode_times")],
        [InlineKeyboardButton(get_translation("back_to_main_menu", lang_code), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    status_text = get_translation("current_sound_settings", lang_code).format(
        sound_status=get_translation("enabled" if sound_enabled else "disabled", lang_code),
        silent_mode_status=get_translation("enabled" if silent_mode_enabled else "disabled", lang_code),
        silent_start=silent_start_time.strftime("%H:%M"),
        silent_end=silent_end_time.strftime("%H:%M")
    )

    await context.bot.send_message(
        user.id,
        status_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    user_data_temp.pop(user.id, None) # Clear any pending steps

async def maintenance_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to turn on maintenance mode."""
    user = update.effective_user
    if not user: return
    
    admin_ids_str = os.getenv("ADMIN_USER_IDS")
    admin_ids = [int(aid.strip()) for aid in admin_ids_str.split(',') if aid.strip().isdigit()] if admin_ids_str else []

    user_db = await db_manager.get_user(user.id)
    lang_code = user_db.get('language_code', 'en') if user_db else 'en'

    if user.id not in admin_ids:
        await context.bot.send_message(user.id, get_translation("admin_unauthorized", lang_code))
        return

    await db_manager.set_bot_status("maintenance_mode", "on")
    await context.bot.send_message(user.id, get_translation("maintenance_on_feedback", lang_code))
    log.info(f"Admin {user.id} turned ON maintenance mode.")

async def maintenance_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to turn off maintenance mode."""
    user = update.effective_user
    if not user: return

    admin_ids_str = os.getenv("ADMIN_USER_IDS")
    admin_ids = [int(aid.strip()) for aid in admin_ids_str.split(',') if aid.strip().isdigit()] if admin_ids_str else []

    user_db = await db_manager.get_user(user.id)
    lang_code = user_db.get('language_code', 'en') if user_db else 'en'

    if user.id not in admin_ids:
        await context.bot.send_message(user.id, get_translation("admin_unauthorized", lang_code))
        return

    await db_manager.set_bot_status("maintenance_mode", "off")
    await context.bot.send_message(user.id, get_translation("maintenance_off_feedback", lang_code))
    log.info(f"Admin {user.id} turned OFF maintenance mode.")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming text messages based on user's current step."""
    user = update.effective_user
    if not user or not update.message or not update.message.text:
        log.warning("Message handler received update without user or text.")
        return

    # Check maintenance mode
    maintenance_status = await db_manager.get_bot_status("maintenance_mode")
    if maintenance_status == "on":
        user_db = await db_manager.get_user(user.id)
        lang_code = user_db.get('language_code', 'en') if user_db else 'en'
        admin_ids_str = os.getenv("ADMIN_USER_IDS")
        admin_ids = [int(aid.strip()) for aid in admin_ids_str.split(',') if aid.strip().isdigit()] if admin_ids_str else []

        if user.id not in admin_ids:
            await context.bot.send_message(user.id, get_translation("maintenance_user_notification", lang_code))
            return
    
    user_db = await db_manager.get_user(user.id)
    lang_code = user_db.get('language_code', 'en') if user_db else 'en'

    current_step = user_data_temp.get(user.id, {}).get("step", UserSteps.NONE)
    message_text = update.message.text.strip()

    if current_step == UserSteps.AWAITING_INITIAL_LANG:
        chosen_lang = "en"
        if "русский" in message_text.lower():
            chosen_lang = "ru"
        elif "հայերեն" in message_text.lower():
            chosen_lang = "hy"
        
        await db_manager.create_or_update_user(user.id, chosen_lang)
        await send_main_menu(user.id, context, chosen_lang)
        log.info(f"User {user.id} set language to {chosen_lang}.")
        user_data_temp.pop(user.id, None) # Clear step
    
    elif current_step == UserSteps.AWAITING_ADDRESS:
        if user_data_temp[user.id].get("context") == "qa_check":
            await handle_qa_address_input(user.id, message_text, context, lang_code)
        else: # Regular address addition
            await handle_address_input(user.id, message_text, context, lang_code)
        user_data_temp.pop(user.id, None) # Clear step after handling

    elif current_step == UserSteps.AWAITING_SILENT_MODE_TIMES:
        await handle_silent_mode_times_input(user.id, message_text, context, lang_code)

    elif current_step == UserSteps.CONFIRM_SILENT_MODE_TIMES:
        # This state should primarily be handled by callback queries from the inline keyboard.
        # If a text message comes in here, it's unexpected.
        await context.bot.send_message(user.id, get_translation("please_use_buttons", lang_code), reply_markup=ReplyKeyboardRemove())
        # Re-send the confirmation message if they send text
        start_time_str = user_data_temp[user.id].get("start_time")
        end_time_str = user_data_temp[user.id].get("end_time")
        if start_time_str and end_time_str:
            await send_silent_mode_confirmation(user.id, context, lang_code, start_time_str, end_time_str)
        else:
            await send_main_menu(user.id, context, lang_code) # Fallback to main menu


    else:
        # Handle general text messages (e.g., if a user types something unexpected)
        log.info(f"User {user.id} sent unhandled message: '{message_text}' in state {current_step}.")
        if message_text == get_translation("add_address_btn", lang_code):
            await context.bot.send_message(user.id, get_translation("enter_address_prompt", lang_code), reply_markup=ReplyKeyboardRemove())
            user_data_temp[user.id] = {"step": UserSteps.AWAITING_ADDRESS, "context": "add_new_address"}
        elif message_text == get_translation("my_addresses_btn", lang_code):
            await my_addresses_command(update, context)
        elif message_text == get_translation("check_outage_btn", lang_code):
            await qa_command(update, context) # Reuse QA for immediate check
        elif message_text == get_translation("frequency_btn", lang_code):
            await frequency_command(update, context)
        elif message_text == get_translation("sound_settings_btn", lang_code):
            await sound_command(update, context)
        elif message_text == get_translation("stats_btn", lang_code): # Changed to "stats_btn"
            await stats_command(update, context)
        elif message_text == get_translation("contact_support_btn", lang_code):
            await context.bot.send_message(user.id, get_translation("support_message", lang_code), parse_mode=ParseMode.MARKDOWN)
        elif message_text == get_translation("about_bot_btn", lang_code):
            await context.bot.send_message(user.id, get_translation("about_bot_message", lang_code), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        else:
            # If nothing matches, respond with a general prompt or main menu
            await context.bot.send_message(user.id, get_translation("unrecognized_command", lang_code))
            await send_main_menu(user.id, context, lang_code)


# --- Address Input Handlers ---
async def handle_address_input(user_id: int, address_text: str, context: ContextTypes.DEFAULT_TYPE, lang_code: str):
    """Handles the user's address input for adding a new address."""
    await context.bot.send_chat_action(user_id, ChatAction.TYPING)
    await context.bot.send_message(user_id, get_translation("verifying_address", lang_code))

    verified_addr = await api_clients.get_verified_address_from_yandex(address_text, lang_code)

    if verified_addr:
        success = await db_manager.add_user_address(
            user_id,
            verified_addr['region'],
            verified_addr['street'],
            verified_addr['full_address'],
            verified_addr['latitude'],
            verified_addr['longitude']
        )
        if success:
            await context.bot.send_message(user_id, get_translation("address_added_success", lang_code).format(address=verified_addr['full_address']), parse_mode=ParseMode.MARKDOWN)
            log.info(f"User {user_id} added address: {verified_addr['full_address']}")
        else:
            await context.bot.send_message(user_id, get_translation("address_already_exists", lang_code).format(address=verified_addr['full_address']))
    else:
        await context.bot.send_message(user_id, get_translation("address_not_found", lang_code).format(address=address_text))
        log.info(f"User {user_id} failed to add address: '{address_text}' - not found/verified.")
    
    await send_main_menu(user_id, context, lang_code)


async def handle_qa_address_input(user_id: int, address_text: str, context: ContextTypes.DEFAULT_TYPE, lang_code: str):
    """Handles address input when checking for outages (QA context)."""
    await context.bot.send_chat_action(user_id, ChatAction.TYPING)
    await context.bot.send_message(user_id, get_translation("checking_outages", lang_code))

    verified_addr = await api_clients.get_verified_address_from_yandex(address_text, lang_code)

    if verified_addr:
        # For QA, we don't save the address to user_addresses, just check outages for it.
        # Use dummy lat/lon for now as db_manager.find_outages_for_address is a placeholder for geo-search
        # For now, it will return ALL recent outages and we filter in Python.
        outages = await db_manager.find_outages_for_address(
            verified_addr['latitude'],
            verified_addr['longitude']
        )
        
        relevant_outages = []
        for outage in outages:
            # Simple text-based matching for relevance until proper geo-indexing is in place
            armenian_text = outage['details'].get('armenian_text', '').lower()
            # Check if the full verified address or street/region parts are in the outage text
            if verified_addr['full_address'].lower() in armenian_text or \
               (verified_addr['street'] and verified_addr['street'].lower() in armenian_text) or \
               (verified_addr['region'] and verified_addr['region'].lower() in armenian_text):
                relevant_outages.append(outage)
        
        if relevant_outages:
            response_text = get_translation("found_outages_for_address", lang_code).format(address=verified_addr['full_address']) + "\n\n"
            for outage in relevant_outages:
                source_type = outage.get('source_type', get_translation('unknown_type', lang_code))
                status = outage.get('status', get_translation('unknown_status', lang_code))
                start_dt = outage.get('start_datetime')
                end_dt = outage.get('end_datetime')
                details_armenian = outage['details'].get('armenian_text', get_translation('no_details', lang_code))

                response_text += f"*{get_translation('source_type', lang_code)}:* {source_type.capitalize()}\n"
                response_text += f"*{get_translation('status', lang_code)}:* {status.capitalize()}\n"
                if start_dt:
                    response_text += f"*{get_translation('start_time', lang_code)}:* {start_dt.strftime('%Y-%m-%d %H:%M')}\n"
                if end_dt:
                    response_text += f"*{get_translation('end_time', lang_code)}:* {end_dt.strftime('%Y-%m-%d %H:%M')}\n"
                response_text += f"*{get_translation('details', lang_code)}:* {details_armenian}\n\n"
            await context.bot.send_message(user_id, response_text, parse_mode=ParseMode.MARKDOWN)
        else:
            # Check for past outages if no current/future ones are found
            last_outage = await db_manager.get_last_outage_for_address(verified_addr['full_address'])
            if last_outage:
                response_text = get_translation("no_current_outages", lang_code).format(address=verified_addr['full_address']) + "\n\n"
                response_text += get_translation("last_outage_recorded", lang_code) + "\n\n"
                
                source_type = last_outage.get('source_type', get_translation('unknown_type', lang_code))
                status = last_outage.get('status', get_translation('unknown_status', lang_code))
                start_dt = last_outage.get('start_datetime')
                end_dt = last_outage.get('end_datetime')
                details_armenian = last_outage['details'].get('armenian_text', get_translation('no_details', lang_code))

                response_text += f"*{get_translation('source_type', lang_code)}:* {source_type.capitalize()}\n"
                response_text += f"*{get_translation('status', lang_code)}:* {status.capitalize()}\n"
                if start_dt:
                    response_text += f"*{get_translation('start_time', lang_code)}:* {start_dt.strftime('%Y-%m-%d %H:%M')}\n"
                if end_dt:
                    response_text += f"*{get_translation('end_time', lang_code)}:* {end_dt.strftime('%Y-%m-%d %H:%M')}\n"
                response_text += f"*{get_translation('details', lang_code)}:* {details_armenian}\n\n"
                await context.bot.send_message(user_id, response_text, parse_mode=ParseMode.MARKDOWN)

            else:
                await context.bot.send_message(user_id, get_translation("no_outages_found", lang_code).format(address=verified_addr['full_address']))
                await context.bot.send_message(user_id, get_translation("no_past_outages", lang_code))
            
    else:
        await context.bot.send_message(user_id, get_translation("address_not_found", lang_code).format(address=address_text))
    
    await send_main_menu(user_id, context, lang_code)


# --- Silent Mode Time Input Handlers ---
async def handle_silent_mode_times_input(user_id: int, message_text: str, context: ContextTypes.DEFAULT_TYPE, lang_code: str):
    """
    Parses user input for silent mode start and end times, supporting fuzzy matching.
    """
    # Normalize input: replace common delimiters with a colon for easier parsing
    normalized_text = re.sub(r'[\s.,-]', ':', message_text)
    
    # Try to find two time patterns (HH:MM or H:M)
    time_patterns = re.findall(r'(\d{1,2}(?::\d{2})?)', normalized_text)
    
    # Ensure times are in HH:MM format (e.g., "7" becomes "07:00", "22:3" becomes "22:30")
    formatted_times = []
    for t in time_patterns:
        if ':' in t:
            parts = t.split(':')
            h = parts[0].zfill(2)
            m = parts[1].zfill(2)
            formatted_times.append(f"{h}:{m}")
        else:
            # Assume it's just an hour, set minutes to 00
            h = t.zfill(2)
            formatted_times.append(f"{h}:00")

    if len(formatted_times) == 2:
        start_time_str = formatted_times[0]
        end_time_str = formatted_times[1]

        # Validate if they are valid times
        try:
            dt_time.fromisoformat(start_time_str)
            dt_time.fromisoformat(end_time_str)
        except ValueError:
            await context.bot.send_message(user_id, get_translation("invalid_time_format", lang_code))
            user_data_temp[user_id]["step"] = UserSteps.AWAITING_SILENT_MODE_TIMES # Keep current step
            return

        user_data_temp[user_id] = {
            "step": UserSteps.CONFIRM_SILENT_MODE_TIMES,
            "start_time": start_time_str,
            "end_time": end_time_str
        }
        await send_silent_mode_confirmation(user_id, context, lang_code, start_time_str, end_time_str)
    else:
        await context.bot.send_message(user_id, get_translation("invalid_time_range_format", lang_code))
        user_data_temp[user_id]["step"] = UserSteps.AWAITING_SILENT_MODE_TIMES # Keep current step

async def send_silent_mode_confirmation(user_id: int, context: ContextTypes.DEFAULT_TYPE, lang_code: str, start_time_str: str, end_time_str: str):
    """
    Sends the confirmation message for silent mode times with inline buttons.
    """
    keyboard = [
        [InlineKeyboardButton(get_translation("yes_button", lang_code), callback_data=f"confirm_silent_times_{start_time_str}_{end_time_str}")],
        [InlineKeyboardButton(get_translation("no_edit_button", lang_code), callback_data="edit_silent_times")],
        [InlineKeyboardButton(get_translation("cancel_button", lang_code), callback_data="cancel_silent_times")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        user_id,
        get_translation("confirm_silent_mode_times", lang_code).format(start_time=start_time_str, end_time=end_time_str),
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming callback queries from inline keyboards."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback query

    user_id = query.from_user.id
    user_db = await db_manager.get_user(user_id)
    lang_code = user_db.get('language_code', 'en') if user_db else 'en'

    data = query.data

    if data == "main_menu":
        await send_main_menu(user_id, context, lang_code, query.message.message_id)
        return

    elif data.startswith("set_freq_"):
        try:
            frequency_seconds = int(data.split("_")[2])
            await db_manager.update_user_frequency(user_id, frequency_seconds)
            hours = frequency_seconds // 3600
            await query.edit_message_text(
                text=get_translation("frequency_set_success", lang_code).format(hours=hours),
                parse_mode=ParseMode.MARKDOWN
            )
            log.info(f"User {user_id} set frequency to {hours} hours.")
            # After setting frequency, send main menu again
            await send_main_menu(user_id, context, lang_code)

        except (IndexError, ValueError) as e:
            log.error(f"Error parsing frequency callback data: {data} - {e}")
            await query.edit_message_text(text=get_translation("error_generic", lang_code))
            await send_main_menu(user_id, context, lang_code)

    elif data.startswith("del_addr_"):
        try:
            address_id = int(data.split("_")[2])
            success = await db_manager.remove_user_address(address_id, user_id)
            if success:
                await query.edit_message_text(text=get_translation("address_removed_success", lang_code))
                log.info(f"User {user_id} removed address ID: {address_id}.")
            else:
                await query.edit_message_text(text=get_translation("address_remove_failed", lang_code))
        except (IndexError, ValueError) as e:
            log.error(f"Error parsing address deletion callback data: {data} - {e}")
            await query.edit_message_text(text=get_translation("error_generic", lang_code))
        # After deletion, refresh the my addresses list or go to main menu
        await my_addresses_command(update, context) # Re-send addresses
    
    elif data == "toggle_sound":
        user_db = await db_manager.get_user(user_id)
        current_setting = user_db.get('notification_sound_enabled', True)
        new_setting = not current_setting
        await db_manager.update_user_sound_settings(user_id, {"notification_sound_enabled": new_setting})
        
        await query.edit_message_text(
            text=get_translation("sound_toggled", lang_code).format(status=get_translation("enabled" if new_setting else "disabled", lang_code)),
            parse_mode=ParseMode.MARKDOWN
        )
        await sound_command(update, context) # Re-send sound settings menu

    elif data == "toggle_silent_mode":
        user_db = await db_manager.get_user(user_id)
        current_setting = user_db.get('silent_mode_enabled', False)
        new_setting = not current_setting
        await db_manager.update_user_sound_settings(user_id, {"silent_mode_enabled": new_setting})
        
        await query.edit_message_text(
            text=get_translation("silent_mode_toggled", lang_code).format(status=get_translation("enabled" if new_setting else "disabled", lang_code)),
            parse_mode=ParseMode.MARKDOWN
        )
        await sound_command(update, context) # Re-send sound settings menu

    elif data == "set_silent_mode_times":
        await query.edit_message_text(
            text=get_translation("prompt_silent_mode_times", lang_code),
            parse_mode=ParseMode.MARKDOWN
        )
        user_data_temp[user_id] = {"step": UserSteps.AWAITING_SILENT_MODE_TIMES}

    elif data.startswith("confirm_silent_times_"):
        try:
            # Extract times from callback data: confirm_silent_times_HH:MM_HH:MM
            parts = data.split('_')
            if len(parts) == 4:
                start_time_str = parts[2]
                end_time_str = parts[3]

                success = await set_user_silent_mode_times(user_id, start_time_str, end_time_str)
                if success:
                    await query.edit_message_text(get_translation("silent_mode_times_set_success", lang_code).format(start_time=start_time_str, end_time=end_time_str))
                    log.info(f"User {user_id} set silent times: {start_time_str}-{end_time_str}")
                else:
                    await query.edit_message_text(get_translation("error_setting_silent_times", lang_code))
                
                await sound_command(update, context) # Return to sound settings or main menu
            else:
                raise ValueError("Malformed silent times confirmation data.")
        except (IndexError, ValueError) as e:
            log.error(f"Error processing confirm_silent_times callback: {data} - {e}")
            await query.edit_message_text(get_translation("error_generic", lang_code))
            await sound_command(update, context) # Fallback

    elif data == "edit_silent_times":
        await query.edit_message_text(
            text=get_translation("prompt_silent_mode_times", lang_code), # Re-prompt for input
            parse_mode=ParseMode.MARKDOWN
        )
        user_data_temp[user_id] = {"step": UserSteps.AWAITING_SILENT_MODE_TIMES} # Go back to input state

    elif data == "cancel_silent_times":
        await query.edit_message_text(get_translation("silent_mode_times_canceled", lang_code))
        user_data_temp.pop(user_id, None) # Clear pending step
        await sound_command(update, context) # Return to sound settings or main menu

    else:
        # Fallback for unhandled callback queries
        log.warning(f"Unhandled callback query data: {data} from user {user_id}")
        await query.edit_message_text(text=get_translation("error_generic", lang_code))
        await send_main_menu(user_id, context, lang_code)


async def periodic_site_check_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Job to periodically check utility websites for new announcements and notify users.
    """
    log.info("Starting periodic site check job...")
    
    # Check if maintenance mode is ON
    maintenance_status = await db_manager.get_bot_status("maintenance_mode")
    if maintenance_status == "on":
        log.info("Bot is in maintenance mode, skipping site check.")
        return

    # Load AI models if not already loaded (important for parsing)
    if not ai_engine.is_ai_available():
        log.warning("AI models not loaded, attempting to load for site check.")
        await ai_engine.load_models() # Make sure to await this call
        if not ai_engine.is_ai_available():
            log.error("AI models failed to load. Cannot perform site checks requiring AI.")
            return

    # Fetch and process announcements concurrently
    await asyncio.gather(
        parse_all_water_announcements_async(),
        parse_all_gas_announcements_async(),
        parse_all_electric_announcements_async()
    )
    log.info("Finished fetching and processing all announcements.")

    # TODO: Implement notification logic here.
    # 1. Fetch all users and their addresses.
    # 2. For each user's address, find relevant new outages.
    # 3. Check user's notification settings (frequency, silent mode).
    # 4. Send notification if conditions met and outage hasn't been sent before.
    # 5. Record sent notification.

    log.info("Periodic site check job completed.")


async def post_init(application: Application):
    """Initializes database and loads AI models after the bot starts."""
    log.info("Bot application starting, initializing DB and AI models...")
    await db_manager.init_db_pool()
    # It's better to load AI models here once, rather than every job run.
    # The ai_engine.load_models() function handles checking if already loaded.
    await ai_engine.load_models() # Make sure to await this call
    log.info("Bot post-initialization complete.")

async def post_shutdown(application: Application):
    """Closes database connection pool when the bot shuts down."""
    await db_manager.close_db_pool()
    log.info("Bot shut down gracefully.")

def main():
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        log.critical("TELEGRAM_BOT_TOKEN not set. Exiting.")
        sys.exit(1)

    application = (
        ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN"))
        .post_init(post_init).post_shutdown(post_shutdown).build()
    )
    
    command_handlers = {
        "start": start_command, "myaddresses": my_addresses_command,
        "frequency": frequency_command, "stats": stats_command,
        "clearaddresses": clear_addresses_command, "qa": qa_command,
        "sound": sound_command, "maintenance_on": maintenance_on_command,
        "maintenance_off": maintenance_off_command
    }
    for command, handler in command_handlers.items():
        application.add_handler(CommandHandler(command, handler))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    job_queue = application.job_queue
    job_interval = int(os.getenv("JOB_INTERVAL_SECONDS", "1800"))
    job_queue.run_repeating(periodic_site_check_job, interval=job_interval, first=10, name="site_check")
    log.info(f"Scheduled 'site_check' job to run every {job_interval} seconds.")

    # Set bot commands for Telegram UI
    bot_commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("myaddresses", "Manage my saved addresses"),
        BotCommand("frequency", "Set notification frequency"),
        BotCommand("sound", "Sound notification settings"),
        BotCommand("qa", "Ask about outages for an address"),
        BotCommand("stats", "Show bot statistics (admin only)"),
        BotCommand("clearaddresses", "Clear all my saved addresses"),
        # Admin commands (not listed to general users)
        # BotCommand("maintenance_on", "Turn on maintenance mode (admin)"),
        # BotCommand("maintenance_off", "Turn off maintenance mode (admin)"),
    ]
    application.bot.set_my_commands(bot_commands)

    log.info("Bot started polling...")
    application.run_polling()


if __name__ == "__main__":
    main()

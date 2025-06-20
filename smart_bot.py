# --- Standard Library ---
import asyncio
import logging
import os
import re
import sys
from enum import Enum, auto
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional, Callable

# --- Third-party Libraries ---
from dotenv import load_dotenv # Moved to top
load_dotenv() # Load environment variables as early as possible

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
from parse_water import parse_all_water_announcements_async
from parse_gas import parse_all_gas_announcements_async
from parse_electric import parse_all_electric_announcements_async

# --- Initial Setup ---
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
    AWAITING_STREET = auto()
    AWAITING_FREQUENCY = auto()
    AWAITING_SUPPORT_MESSAGE = auto()
    AWAITING_SILENT_INTERVAL = auto()
    AWAITING_SILENT_INTERVAL_CONFIRMATION = auto()
    AWAITING_CLEAR_ADDRESSES_CONFIRMATION = auto() # New: for confirming address clear

ADMIN_IDS = [int(i) for i in os.getenv("ADMIN_USER_IDS", "").split(',') if i]
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID")
TIER_ORDER = ["Free", "Basic", "Premium", "Ultra"]
REGIONS_LIST = ["Երևան", "Արագածոտն", "Արարատ", "Արմավիր", "Գեղարքունիք", "Լոռի", "Կոտայք", "Շիրակ", "Սյունիք", "Վայոց Ձոր", "Տավուշ"]
FREQUENCY_OPTIONS = {
    "Free_6h": {"interval": 21600, "hy": "⏱ 6 ժամ", "ru": "⏱ 6 часов", "en": "⏱ 6 hours", "tier": "Free"},
    "Free_12h": {"interval": 43200, "hy": "⏱ 12 ժամ", "ru": "⏱ 12 часов", "en": "⏱ 12 hours", "tier": "Free"},
    "Basic_1h": {"interval": 3600, "hy": "⏱ 1 ժամ", "ru": "⏱ 1 час", "en": "⏱ 1 hour", "tier": "Basic"},
    "Premium_30m": {"interval": 1800, "hy": "⏱ 30 րոպե", "ru": "⏱ 30 минут", "en": "⏱ 30 min", "tier": "Premium"},
    "Ultra_15m": {"interval": 900, "hy": "⏱ 15 րոպե", "ru": "⏱ 15 минут", "en": "⏱ 15 min", "tier": "Ultra"},
}

# --- Utility Functions ---
def get_text(key: str, lang: str, **kwargs) -> str:
    """Retrieves translated text for a given key and language."""
    # Fallback to English if the requested language or key is not found
    text = translations.get(key, {}).get(lang, translations.get(key, {}).get("en", f"Translation missing for {key}"))
    return text.format(**kwargs)

def get_user_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Retrieves the user's language code from context or defaults to 'en'."""
    return context.user_data.get("lang", "en")

def requires_admin(func: Callable) -> Callable:
    """Decorator to restrict access to admin users."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in ADMIN_IDS:
            lang = get_user_lang(context)
            # Use update.message.reply_text if it's a command/message, query.edit_message_text if it's a callback
            if update.message:
                await update.message.reply_text(get_text("admin_unauthorized", lang))
            elif update.callback_query:
                await update.callback_query.answer(get_text("admin_unauthorized", lang), show_alert=True)
                await update.callback_query.message.edit_text(get_text("admin_unauthorized", lang)) # Or simply remove the buttons
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def get_main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Generates the main menu keyboard."""
    keyboard = [
        [KeyboardButton(get_text("add_address_btn", lang)), KeyboardButton(get_text("remove_address_btn", lang))],
        [KeyboardButton(get_text("my_addresses_btn", lang)), KeyboardButton(get_text("frequency_btn", lang))],
        [KeyboardButton(get_text("sound_settings_btn", lang)), KeyboardButton(get_text("qa_btn", lang))],
        [KeyboardButton(get_text("contact_support_btn", lang))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def get_user_sound_settings_keyboard(user_id: int, lang: str) -> InlineKeyboardMarkup:
    """Generates the inline keyboard for sound settings."""
    user = await db_manager.get_user(user_id)
    if not user:
        return InlineKeyboardMarkup([]) # Should not happen if user exists

    sound_enabled = user['notification_sound_enabled']
    silent_mode_enabled = user['silent_mode_enabled']
    silent_start_time = user['silent_mode_start_time'].strftime('%H:%M') if user['silent_mode_start_time'] else '23:00'
    silent_end_time = user['silent_mode_end_time'].strftime('%H:%M') if user['silent_mode_end_time'] else '07:00'

    sound_status_text = get_text("sound_on" if sound_enabled else "sound_off", lang)
    silent_status_text = get_text("silent_mode_on" if silent_mode_enabled else "silent_mode_off", lang)

    keyboard = [
        [InlineKeyboardButton(sound_status_text, callback_data=f"toggle_sound:{'off' if sound_enabled else 'on'}")],
        [InlineKeyboardButton(silent_status_text, callback_data=f"toggle_silent_mode:{'off' if silent_mode_enabled else 'on'}")],
        [InlineKeyboardButton(get_text("set_silent_times_btn", lang).format(start_time=silent_start_time, end_time=silent_end_time), callback_data="set_silent_times_callback")],
        [InlineKeyboardButton(get_text("back_to_main_menu_btn", lang), callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Helper for parsing fuzzy time input ---
def parse_time_fuzzy(time_str: str) -> Optional[dt_time]:
    """
    Parses a time string with fuzzy matching for formats like HH:MM, HH.MM, HH,MM, HHMM.
    Returns datetime.time object or None if parsing fails.
    """
    time_str = time_str.strip()
    # Try HH:MM, HH.MM, HH,MM
    match = re.match(r"^(\d{1,2})[.:,]?(\d{2})$", time_str)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return dt_time(h, m)
    
    # Try HHMM (e.g., 2230)
    match = re.match(r"^(\d{1,2})(\d{2})$", time_str)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return dt_time(h, m)

    return None

# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(context) # Default or from existing user data

    user = await db_manager.get_user(user_id)
    if not user:
        # New user, ask for language
        keyboard = [[KeyboardButton("Հայերեն"), KeyboardButton("Русский"), KeyboardButton("English")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("👋 Ողջույն! Խնդրում ենք ընտրել Ձեր լեզուն:\n👋 Привет! Пожалуйста, выберите ваш язык.\n👋 Hello! Please choose your language.", reply_markup=reply_markup)
        context.user_data["step"] = UserSteps.AWAITING_INITIAL_LANG.name
    else:
        # Existing user, send main menu
        context.user_data["lang"] = user["language_code"]
        lang = user["language_code"]
        await update.message.reply_text(get_text("welcome_back", lang), reply_markup=get_main_menu_keyboard(lang))
        context.user_data["step"] = UserSteps.NONE.name
    log.info(f"User {user_id} started bot. New user: {not bool(user)}")

async def my_addresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(context)
    addresses = await db_manager.get_user_addresses(user_id)
    if not addresses:
        await (update.message or update.callback_query.message).reply_text(get_text("no_addresses_yet", lang))
        return

    address_list_text = get_text("your_addresses", lang) + "\n"
    keyboard_buttons = []
    for addr in addresses:
        address_list_text += f"- {addr['full_address_text']} (ID: {addr['address_id']})\n"
        keyboard_buttons.append([InlineKeyboardButton(f"❌ {addr['full_address_text']}", callback_data=f"remove_address:{addr['address_id']}")])

    reply_markup = InlineKeyboardMarkup(keyboard_buttons) if keyboard_buttons else None
    await (update.message or update.callback_query.message).reply_text(address_list_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def frequency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(context)
    user = await db_manager.get_user(user_id)
    if not user:
        await (update.message or update.callback_query.message).reply_text(get_text("user_not_found", lang))
        return

    current_frequency_seconds = user['frequency_seconds']
    current_tier = user['tier']

    keyboard_buttons = []
    for key, opts in FREQUENCY_OPTIONS.items():
        button_text = get_text(key, lang)
        if opts['interval'] == current_frequency_seconds:
            button_text += " ✅" # Indicate current selection
        
        # Check if user's current tier allows this option or higher
        user_tier_index = TIER_ORDER.index(current_tier)
        option_tier_index = TIER_ORDER.index(opts['tier'])
        
        if option_tier_index <= user_tier_index:
            keyboard_buttons.append([InlineKeyboardButton(button_text, callback_data=f"set_frequency:{opts['interval']}")])
        else:
            # If the option's tier is higher than the user's, show it as unavailable
            keyboard_buttons.append([InlineKeyboardButton(f"🔒 {button_text} ({get_text(opts['tier'], lang)})", callback_data="unauthorized")])

    keyboard_buttons.append([InlineKeyboardButton(get_text("back_to_main_menu_btn", lang), callback_data="main_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    await (update.message or update.callback_query.message).reply_text(get_text("choose_frequency", lang).format(current_frequency=get_text(f"Free_{current_frequency_seconds/3600:.0f}h", lang) if current_frequency_seconds >= 3600 else get_text(f"Premium_{current_frequency_seconds/60:.0f}m", lang)), reply_markup=reply_markup)

async def sound_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(context)
    user = await db_manager.get_user(user_id)
    if not user:
        return # Should not happen if user exists

    sound_enabled = user['notification_sound_enabled']
    silent_mode_enabled = user['silent_mode_enabled']
    silent_start_time = user['silent_mode_start_time'].strftime('%H:%M') if user['silent_mode_start_time'] else '23:00'
    silent_end_time = user['silent_mode_end_time'].strftime('%H:%M') if user['silent_mode_end_time'] else '07:00'

    sound_status_text = get_text("sound_on" if sound_enabled else "sound_off", lang)
    silent_status_text = get_text("silent_mode_on" if silent_mode_enabled else "silent_mode_off", lang)

    keyboard = [
        [InlineKeyboardButton(sound_status_text, callback_data=f"toggle_sound:{'off' if sound_enabled else 'on'}")],
        [InlineKeyboardButton(silent_status_text, callback_data=f"toggle_silent_mode:{'off' if silent_mode_enabled else 'on'}")],
        [InlineKeyboardButton(get_text("set_silent_times_btn", lang).format(start_time=silent_start_time, end_time=silent_end_time), callback_data="set_silent_times_callback")],
        [InlineKeyboardButton(get_text("back_to_main_menu_btn", lang), callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        # Check if the update is from a callback query (meaning a message already exists)
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.edit_text(get_text("sound_settings_prompt", lang), reply_markup=reply_markup)
        elif update.message:
            # Otherwise, send a new message
            await update.message.reply_text(get_text("sound_settings_prompt", lang), reply_markup=reply_markup)
    except BadRequest as e:
        # This can happen if the message was too old to edit, or concurrently modified
        log.warning(f"Failed to edit message in sound_command, sending new one. Error: {e}")
        if update.callback_query and update.callback_query.message:
            # If it was a callback, send a new message to the chat
            await update.callback_query.message.reply_text(get_text("sound_settings_prompt", lang), reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(get_text("sound_settings_prompt", lang), reply_markup=reply_markup)



@requires_admin
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(context)
    
    system_stats = await db_manager.get_system_stats()
    user_notif_count = await db_manager.get_user_notification_count(user_id)
    
    # Fetch bot status information for display
    last_check_start = await db_manager.get_bot_status("last_check_start")
    last_check_end = await db_manager.get_bot_status("last_check_end")
    last_check_status = await db_manager.get_bot_status("last_check_status")

    # Format datetime objects for display if they exist
    last_check_start_formatted = datetime.fromisoformat(last_check_start).strftime('%Y-%m-%d %H:%M:%S') if last_check_start else 'N/A'
    last_check_end_formatted = datetime.fromisoformat(last_check_end).strftime('%Y-%m-%d %H:%M:%S') if last_check_end else 'N/A'


    await (update.message or update.callback_query.message).reply_text(
        get_text(
            "stats_message",
            lang,
            total_users=system_stats.get('total_users', 0),
            total_addresses=system_stats.get('total_addresses', 0),
            last_check_start=last_check_start_formatted,
            last_check_end=last_check_end_formatted,
            last_check_status=last_check_status if last_check_status else 'unknown',
            user_notifications=user_notif_count
        ),
        parse_mode=ParseMode.MARKDOWN
    )


async def clear_addresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(context)

    addresses = await db_manager.get_user_addresses(user_id)
    if not addresses:
        await (update.message or update.callback_query.message).reply_text(get_text("no_addresses_to_clear", lang))
        return

    keyboard = [
        [InlineKeyboardButton(get_text("yes_delete_all_btn", lang), callback_data="clear_addresses_confirm:yes")],
        [InlineKeyboardButton(get_text("no_cancel_btn", lang), callback_data="clear_addresses_confirm:no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await (update.message or update.callback_query.message).reply_text(get_text("clear_addresses_confirmation", lang), reply_markup=reply_markup)
    context.user_data["step"] = UserSteps.AWAITING_CLEAR_ADDRESSES_CONFIRMATION.name
    log.info(f"User {user_id} initiated clear addresses command, awaiting confirmation.")


async def qa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    keyboard = [[InlineKeyboardButton(get_text("contact_support_btn", lang), callback_data="contact_support")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await (update.message or update.callback_query.message).reply_text(get_text("qa_title", lang), reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

@requires_admin
async def maintenance_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    await db_manager.set_bot_status("maintenance_mode", "on")
    await (update.message or update.callback_query.message).reply_text(get_text("maintenance_on_feedback", lang))

@requires_admin
async def maintenance_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    await db_manager.set_bot_status("maintenance_mode", "off")
    await (update.message or update.callback_query.message).reply_text(get_text("maintenance_off_feedback", lang))

# --- Message Handler ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    lang = get_user_lang(context) # Get language from context.user_data or default

    # Check maintenance mode
    maintenance_mode = await db_manager.get_bot_status("maintenance_mode")
    if maintenance_mode == "on" and user_id not in ADMIN_IDS:
        await update.message.reply_text(get_text("maintenance_user_notification", lang))
        return

    current_step = context.user_data.get("step", UserSteps.NONE.name)
    log.debug(f"User {user_id} in step: {current_step}, received text: {user_text}")

    if current_step == UserSteps.AWAITING_INITIAL_LANG.name:
        if 'Հայերեն' in user_text:
            lang_code = 'hy'
        elif 'Русский' in user_text:
            lang_code = 'ru'
        elif 'English' in user_text:
            lang_code = 'en'
        else:
            await update.message.reply_text("Please choose a language from the options.")
            return

        context.user_data["lang"] = lang_code
        await db_manager.create_or_update_user(user_id, lang_code)
        await update.message.reply_text(get_text("language_set_success", lang_code), reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text(get_text("welcome_message", lang_code), reply_markup=get_main_menu_keyboard(lang_code))
        context.user_data["step"] = UserSteps.NONE.name
        log.info(f"User {user_id} set language to {lang_code}.")

    elif current_step == UserSteps.NONE.name:
        # Handle main menu button presses (which come as text messages)
        if user_text == get_text("add_address_btn", lang):
            context.user_data["step"] = UserSteps.AWAITING_REGION.name
            region_keyboard = [[KeyboardButton(region)] for region in REGIONS_LIST]
            await update.message.reply_text(get_text("choose_region", lang), reply_markup=ReplyKeyboardMarkup(region_keyboard, resize_keyboard=True))
            log.info(f"User {user_id} chose to add address.")
        elif user_text == get_text("remove_address_btn", lang):
            # This should ideally be handled by my_addresses_command which offers removal
            # For now, let's just re-trigger my_addresses_command
            await my_addresses_command(update, context)
            log.info(f"User {user_id} chose to remove address.")
        elif user_text == get_text("my_addresses_btn", lang):
            await my_addresses_command(update, context)
            log.info(f"User {user_id} chose to view my addresses.")
        elif user_text == get_text("frequency_btn", lang):
            await frequency_command(update, context)
            log.info(f"User {user_id} chose to change frequency.")
        elif user_text == get_text("sound_settings_btn", lang):
            await sound_command(update, context)
            log.info(f"User {user_id} chose sound settings.")
        elif user_text == get_text("qa_btn", lang):
            await qa_command(update, context)
            log.info(f"User {user_id} chose Q&A.")
        elif user_text == get_text("contact_support_btn", lang):
            # This should trigger the contact support flow
            await qa_command(update, context) # Re-using qa_command to show support options
            log.info(f"User {user_id} chose to contact support via main menu button.")
        else:
            # Fallback for unrecognized text input when not in a specific step
            await update.message.reply_text(get_text("unrecognized_command", lang), reply_markup=get_main_menu_keyboard(lang))
            log.warning(f"User {user_id} in NONE step sent unrecognized text: {user_text}")

    elif current_step == UserSteps.AWAITING_REGION.name:
        selected_region = user_text.strip()
        if selected_region in REGIONS_LIST:
            context.user_data["address_region"] = selected_region
            context.user_data["step"] = UserSteps.AWAITING_STREET.name
            await update.message.reply_text(get_text("enter_street", lang), reply_markup=ReplyKeyboardRemove())
            log.info(f"User {user_id} selected region: {selected_region}.")
        else:
            await update.message.reply_text(get_text("invalid_region", lang))

    elif current_step == UserSteps.AWAITING_STREET.name:
        street_text = user_text.strip()
        region = context.user_data.get("address_region")
        
        full_address_text = f"{region}, {street_text}" if region else street_text

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        # Geocode the address using Yandex API
        verified_address_data = await api_clients.get_verified_address_from_yandex(full_address_text, lang="hy_AM" if lang == "hy" else "ru_RU")

        if verified_address_data:
            await db_manager.add_user_address(
                user_id=user_id,
                region=verified_address_data.get('region', region), # Use verified region if available
                street=verified_address_data.get('street', street_text), # Use verified street if available
                full_address_text=verified_address_data['full_address'], # Use the full verified address
                latitude=verified_address_data['latitude'],
                longitude=verified_address_data['longitude']
            )
            await update.message.reply_text(get_text("address_add_success", lang).format(address=verified_address_data['full_address']))
            
            # Check for current outages at the new address
            relevant_outages = await db_manager.get_active_outages_for_address(verified_address_data['full_address'])
            if relevant_outages:
                outage_messages = [f"- {o['details'].get('armenian_text', 'No details')}" for o in relevant_outages]
                await update.message.reply_text(get_text("active_outages_for_address", lang) + "\n" + "\n".join(outage_messages), parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(get_text("no_active_outages_for_address", lang))

            context.user_data["step"] = UserSteps.NONE.name
            del context.user_data["address_region"] # Clean up context
            log.info(f"User {user_id} added address: {verified_address_data['full_address']}.")
        else:
            await update.message.reply_text(get_text("address_not_found", lang))
            log.warning(f"User {user_id} entered unresolvable address: {full_address_text}.")

    elif current_step == UserSteps.AWAITING_SUPPORT_MESSAGE.name:
        support_message_text = user_text.strip()
        if SUPPORT_CHAT_ID:
            try:
                # Forward the user's message to the support chat
                await context.bot.forward_message(
                    chat_id=SUPPORT_CHAT_ID,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
                await update.message.reply_text(get_text("support_message_sent", lang))
                log.info(f"User {user_id} sent support message: '{support_message_text}'")
            except (Forbidden, BadRequest) as e:
                log.error(f"Failed to forward message to support chat {SUPPORT_CHAT_ID}: {e}")
                await update.message.reply_text(get_text("support_send_failed", lang))
        else:
            await update.message.reply_text(get_text("support_not_configured", lang))
            log.warning("SUPPORT_CHAT_ID is not configured in .env")
        context.user_data["step"] = UserSteps.NONE.name

    elif current_step == UserSteps.AWAITING_SILENT_INTERVAL.name:
        # Expected format: "HH:MM HH:MM" or similar
        # Regex to capture two time strings, separated by space or other common separators
        match = re.match(r"^\s*(\d{1,2}[.:,]?\d{2})\s+to\s+(\d{1,2}[.:,]?\d{2})\s*$", user_text, re.IGNORECASE) or \
                re.match(r"^\s*(\d{1,2}[.:,]?\d{2})\s*-\s*(\d{1,2}[.:,]?\d{2})\s*$", user_text) or \
                re.match(r"^\s*(\d{1,2}[.:,]?\d{2})\s+(\d{1,2}[.:,]?\d{2})\s*$", user_text)

        if match:
            start_time_str_raw = match.group(1)
            end_time_str_raw = match.group(2)

            start_time_obj = parse_time_fuzzy(start_time_str_raw)
            end_time_obj = parse_time_fuzzy(end_time_str_raw)

            if start_time_obj and end_time_obj:
                # Store the parsed times temporarily
                context.user_data["proposed_silent_start"] = start_time_obj.strftime('%H:%M')
                context.user_data["proposed_silent_end"] = end_time_obj.strftime('%H:%M')

                keyboard = [
                    [InlineKeyboardButton(get_text("yes", lang), callback_data="confirm_silent_interval_yes_callback")],
                    [InlineKeyboardButton(get_text("no_edit_btn", lang), callback_data="confirm_silent_interval_edit_callback")],
                    [InlineKeyboardButton(get_text("cancel_btn", lang), callback_data="cancel_action_callback")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    get_text("confirm_silent_interval", lang).format(
                        start_time=context.user_data["proposed_silent_start"],
                        end_time=context.user_data["proposed_silent_end"]
                    ),
                    reply_markup=reply_markup
                )
                context.user_data["step"] = UserSteps.AWAITING_SILENT_INTERVAL_CONFIRMATION.name
                log.info(f"User {user_id} proposed silent interval: {start_time_obj}-{end_time_obj}")
            else:
                await update.message.reply_text(get_text("silent_interval_invalid_format", lang))
                log.warning(f"User {user_id} entered invalid fuzzy time format within recognized pattern: {user_text}")
        else:
            await update.message.reply_text(get_text("silent_interval_invalid_format", lang))
            log.warning(f"User {user_id} entered unrecognized time format: {user_text}")

    else:
        # Default fallback for unrecognized text input when not in a specific step (commands are handled by CommandHandler)
        await update.message.reply_text(get_text("unrecognized_command", lang), reply_markup=get_main_menu_keyboard(lang))
        log.warning(f"User {user_id} sent unrecognized text and not in a specific step: {user_text}")


# --- Callback Query Handler ---
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    lang = get_user_lang(context) # Get language from context.user_data or default
    
    await query.answer() # Acknowledge the callback query
    log.debug(f"User {user_id} sent callback_data: {query.data}")

    # Check maintenance mode for non-admin users
    maintenance_mode = await db_manager.get_bot_status("maintenance_mode")
    if maintenance_mode == "on" and user_id not in ADMIN_IDS:
        await query.edit_message_text(get_text("maintenance_user_notification", lang))
        return

    if query.data == "main_menu":
        # Edit the message that contained the inline keyboard to the main menu prompt
        try:
            await query.message.edit_text(get_text("main_menu_prompt", lang), reply_markup=get_main_menu_keyboard(lang))
        except BadRequest as e:
            log.warning(f"Failed to edit message to main menu, sending new one. Error: {e}")
            await context.bot.send_message(query.message.chat_id, get_text("main_menu_prompt", lang), reply_markup=get_main_menu_keyboard(lang))
        context.user_data["step"] = UserSteps.NONE.name
        log.info(f"User {user_id} returned to main menu.")

    elif query.data.startswith("set_lang:"):
        new_lang = query.data.split(":")[1]
        context.user_data["lang"] = new_lang
        await db_manager.update_user_language(user_id, new_lang)
        await query.edit_message_text(get_text("language_changed", new_lang), reply_markup=get_main_menu_keyboard(new_lang))
        log.info(f"User {user_id} changed language to {new_lang}.")

    elif query.data.startswith("remove_address:"):
        address_id_to_remove = int(query.data.split(":")[1])
        removed = await db_manager.remove_user_address(address_id_to_remove, user_id)
        if removed:
            await query.edit_message_text(get_text("address_removed_success", lang))
            log.info(f"User {user_id} removed address ID: {address_id_to_remove}.")
            # Refresh addresses list or main menu
            # Send a new message as editing a previous one with changed list might be awkward
            await my_addresses_command(update, context) # Show updated list
        else:
            await query.edit_message_text(get_text("address_remove_failed", lang))
            log.warning(f"User {user_id} failed to remove address ID: {address_id_to_remove}.")
    
    elif query.data.startswith("set_frequency:"):
        new_frequency = int(query.data.split(":")[1])
        current_user = await db_manager.get_user(user_id)
        if not current_user:
            await query.edit_message_text(get_text("user_not_found", lang))
            return
        
        selected_option = next((opts for key, opts in FREQUENCY_OPTIONS.items() if opts['interval'] == new_frequency), None)
        if selected_option:
            user_tier_index = TIER_ORDER.index(current_user['tier'])
            option_tier_index = TIER_ORDER.index(selected_option['tier'])

            if option_tier_index <= user_tier_index:
                await db_manager.update_user_frequency(user_id, new_frequency)
                await query.edit_message_text(get_text("frequency_set_success", lang).format(frequency=get_text(f"Free_{new_frequency/3600:.0f}h", lang) if new_frequency >= 3600 else get_text(f"Premium_{new_frequency/60:.0f}m", lang)))
                log.info(f"User {user_id} set frequency to {new_frequency} seconds.")
                # Update the job if it exists
                job_name = f"notify_{user_id}"
                current_jobs = context.job_queue.get_jobs_by_name(job_name)
                for job in current_jobs:
                    job.schedule_removal()
                context.job_queue.run_repeating(
                    callback=periodic_notification_job,
                    interval=new_frequency,
                    first=5, # Run soon after setting
                    user_id=user_id,
                    name=job_name
                )
                log.info(f"Updated notification job for user {user_id} to {new_frequency} seconds.")
            else:
                await query.edit_message_text(get_text("feature_not_available_for_tier", lang).format(tier=get_text(selected_option['tier'], lang)))
                log.warning(f"User {user_id} tried to set frequency {new_frequency} requiring tier {selected_option['tier']} but has {current_user['tier']}.")
        else:
            await query.edit_message_text(get_text("invalid_frequency_option", lang))
            log.warning(f"User {user_id} selected invalid frequency option: {new_frequency}")
        
        # Edit the reply markup of the message that triggered the callback
        try:
            await query.message.edit_reply_markup(reply_markup=None) # Remove old buttons
        except BadRequest as e:
            log.warning(f"Failed to clear old frequency buttons: {e}")
        await frequency_command(update, context) # Show updated frequency menu

    elif query.data.startswith("toggle_sound:"):
        action = query.data.split(":")[1]
        new_status = True if action == "on" else False
        await db_manager.set_user_notification_sound(user_id, new_status)
        lang = get_user_lang(context)
        await query.edit_message_text(get_text("sound_enabled_feedback" if new_status else "sound_disabled_feedback", lang))
        log.info(f"User {user_id} toggled sound to {new_status}.")
        # Use sound_command to refresh the keyboard, which also sends the main text
        await sound_command(update, context) 

    elif query.data.startswith("toggle_silent_mode:"):
        action = query.data.split(":")[1]
        new_status = True if action == "on" else False
        await db_manager.set_user_silent_mode_enabled(user_id, new_status)
        lang = get_user_lang(context)
        await query.edit_message_text(get_text("silent_mode_enabled_feedback" if new_status else "silent_mode_disabled_feedback", lang))
        # Use sound_command to refresh the keyboard, which also sends the main text
        await sound_command(update, context) 
        log.info(f"User {user_id} toggled silent mode to {new_status}.")
        

    elif query.data == "set_silent_times_callback":
        lang = get_user_lang(context)
        await query.edit_message_text(get_text("set_silent_interval_prompt", lang))
        context.user_data["step"] = UserSteps.AWAITING_SILENT_INTERVAL.name
        log.info(f"User {user_id} initiated silent interval setting.")

    elif query.data == "confirm_silent_interval_yes_callback":
        lang = get_user_lang(context)
        start_time_str = context.user_data.pop("proposed_silent_start", None)
        end_time_str = context.user_data.pop("proposed_silent_end", None)

        if start_time_str and end_time_str:
            start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
            end_time_obj = datetime.strptime(end_time_str, '%H:%M').time()
            
            await db_manager.set_user_silent_mode_times(user_id, start_time_obj, end_time_obj)
            await db_manager.set_user_silent_mode_enabled(user_id, True) # Also enable silent mode
            await query.edit_message_text(
                get_text("silent_interval_set_success", lang).format(
                    start_time=start_time_str,
                    end_time=end_time_str
                )
            )
            log.info(f"User {user_id} confirmed and set silent interval to {start_time_str}-{end_time_str}.")
        else:
            await query.edit_message_text(get_text("silent_interval_error", lang)) # Should not happen if data is pop'd correctly
            log.error(f"User {user_id} confirmed silent interval but data missing from context.")
        
        context.user_data["step"] = UserSteps.NONE.name
        # Refresh sound settings keyboard and message by re-calling sound_command
        await sound_command(update, context)


    elif query.data == "confirm_silent_interval_edit_callback":
        lang = get_user_lang(context)
        await query.edit_message_text(get_text("silent_interval_edit", lang))
        context.user_data["step"] = UserSteps.AWAITING_SILENT_INTERVAL.name
        log.info(f"User {user_id} chose to edit silent interval.")

    elif query.data == "cancel_action_callback":
        lang = get_user_lang(context)
        # Clear any temporary state
        context.user_data.pop("proposed_silent_start", None)
        context.user_data.pop("proposed_silent_end", None)
        await query.edit_message_text(get_text("silent_interval_cancelled", lang))
        context.user_data["step"] = UserSteps.NONE.name
        # Refresh sound settings keyboard and message by re-calling sound_command
        await sound_command(update, context)


    elif query.data == "contact_support":
        lang = get_user_lang(context)
        await query.edit_message_text(
            get_text("contact_support_message", lang).format(
                phone=translations["CLICKABLE_PHONE_MD"],
                map_address=translations["CLICKABLE_ADDRESS_MD"]
            ),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        context.user_data["step"] = UserSteps.AWAITING_SUPPORT_MESSAGE.name
        log.info(f"User {user_id} chose to contact support.")

    elif query.data == "unauthorized":
        await query.answer(get_text("feature_not_available_for_tier", lang), show_alert=True)
        log.info(f"User {user_id} tried to access unauthorized feature via callback.")
    
    # --- New: Clear Addresses Confirmation Callbacks ---
    elif query.data == "clear_addresses_confirm:yes":
        lang = get_user_lang(context)
        removed = await db_manager.clear_all_user_addresses(user_id)
        if removed:
            await query.edit_message_text(get_text("all_addresses_cleared", lang))
            log.info(f"User {user_id} confirmed and cleared all addresses.")
        else:
            await query.edit_message_text(get_text("clear_addresses_failed", lang))
            log.warning(f"User {user_id} confirmed clear but no addresses were cleared (or error occurred).")
        context.user_data["step"] = UserSteps.NONE.name
        await query.message.reply_markup(reply_markup=get_main_menu_keyboard(lang)) # Show main menu keyboard

    elif query.data == "clear_addresses_confirm:no":
        lang = get_user_lang(context)
        await query.edit_message_text(get_text("clear_addresses_cancelled", lang))
        context.user_data["step"] = UserSteps.NONE.name
        await query.message.reply_markup(reply_markup=get_main_menu_keyboard(lang)) # Show main menu keyboard

    else:
        # Default fallback for unhandled callbacks
        await query.edit_message_text(get_text("unrecognized_command", lang))
        context.user_data["step"] = UserSteps.NONE.name


# --- Scheduled Jobs ---
async def periodic_site_check_job(context: ContextTypes.DEFAULT_TYPE):
    log.info("Starting periodic site check for all utilities...")
    await db_manager.set_bot_status("last_check_start", datetime.now().isoformat())
    
    # AI models are now API-based, so no local loading needed.
    # We rely on ai_engine.is_ai_available() to check for API key presence.
    if not ai_engine.is_ai_available():
        log.error("AI API keys are not available. Skipping parsing tasks.")
        await db_manager.set_bot_status("last_check_status", "failed_api_keys")
        return
    
    # Run parsing tasks concurrently
    try:
        await asyncio.gather(
            parse_all_water_announcements_async(),
            parse_all_gas_announcements_async(),
            parse_all_electric_announcements_async()
        )
        await db_manager.set_bot_status("last_check_status", "success")
        log.info("Periodic site check completed successfully.")
    except Exception as e:
        log.error(f"Error during periodic site check: {e}", exc_info=True)
        await db_manager.set_bot_status("last_check_status", "failed_parsing")
    
    await db_manager.set_bot_status("last_check_end", datetime.now().isoformat())


async def periodic_notification_job(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.user_id
    # log.info(f"Running periodic notification job for user {user_id}")

    user = await db_manager.get_user(user_id)
    if not user:
        log.warning(f"Notification job for non-existent user {user_id} detected. Removing job.")
        context.job.schedule_removal()
        return

    # Check maintenance mode for non-admin users
    maintenance_mode = await db_manager.get_bot_status("maintenance_mode")
    if maintenance_mode == "on" and user_id not in ADMIN_IDS:
        # Do not send notifications during maintenance
        return

    # Check silent mode
    if user['silent_mode_enabled']:
        now = datetime.now().time()
        start_time = user['silent_mode_start_time']
        end_time = user['silent_mode_end_time']
        
        # Handle overnight silent periods (e.g., 22:00 to 07:00)
        if start_time < end_time: # Silent period within the same day
            if start_time <= now < end_time:
                log.info(f"User {user_id} is in silent mode ({start_time}-{end_time}). Skipping notification.")
                return
        else: # Silent period spans across midnight
            if now >= start_time or now < end_time:
                log.info(f"User {user_id} is in silent mode overnight ({start_time}-{end_time}). Skipping notification.")
                return

    user_lang = user['language_code']
    user_addresses = await db_manager.get_user_addresses(user_id)

    if not user_addresses:
        log.info(f"User {user_id} has no addresses, skipping notification.")
        return

    notification_count = 0
    for address in user_addresses:
        active_outages = await db_manager.get_active_outages_for_address(address['full_address_text'])
        
        for outage in active_outages:
            # Check if this specific outage has already been sent to this user
            already_notified = await db_manager.has_notification_been_sent(user_id, outage['raw_text_hash'])
            if not already_notified:
                try:
                    notification_text = get_text("outage_notification", user_lang).format(
                        type=outage['source_type'],
                        address=address['full_address_text'],
                        details=outage['details'].get('armenian_text', get_text("no_details_provided", user_lang)),
                        start_time=outage['start_datetime'].strftime('%H:%M') if outage['start_datetime'] else get_text("not_specified", user_lang),
                        end_time=outage['end_datetime'].strftime('%H:%M') if outage['end_datetime'] else get_text("not_specified", user_lang)
                    )
                    
                    if user['notification_sound_enabled']:
                        await context.bot.send_message(chat_id=user_id, text=notification_text, parse_mode=ParseMode.MARKDOWN)
                    else:
                        await context.bot.send_message(chat_id=user_id, text=notification_text, parse_mode=ParseMode.MARKDOWN, disable_notification=True)
                    
                    await db_manager.record_notification_sent(user_id, outage['raw_text_hash'])
                    notification_count += 1
                    log.info(f"Sent notification for outage {outage['raw_text_hash']} to user {user_id}.")
                except Forbidden:
                    log.warning(f"Bot blocked by user {user_id}. Removing user and addresses.")
                    await db_manager.delete_user(user_id)
                    context.job.schedule_removal()
                    return # Exit after removing blocked user
                except (BadRequest, TimedOut, NetworkError) as e:
                    log.error(f"Error sending notification to user {user_id}: {e}")
                    # Consider retries or specific error handling

    if notification_count == 0:
        log.info(f"No new notifications for user {user_id}.")
    
    # Update last active time for user
    await db_manager.update_user_last_active(user_id)

async def post_init(application: Application):
    await db_manager.init_db_pool()
    ai_engine.initialize_api_status() # Initialize API key check after .env is loaded
    
    # Set up bot commands
    await application.bot.set_my_commands([
        BotCommand("start", get_text("start_command_desc", "en")),
        BotCommand("myaddresses", get_text("myaddresses_command_desc", "en")),
        BotCommand("frequency", get_text("frequency_command_desc", "en")),
        BotCommand("sound", get_text("sound_command_desc", "en")),
        BotCommand("qa", get_text("qa_command_desc", "en")),
        BotCommand("stats", get_text("stats_command_desc", "en")),
        BotCommand("clearaddresses", get_text("clearaddresses_command_desc", "en")),
        BotCommand("maintenance_on", "Turn on maintenance mode (Admin)"), # Admin command, no translation needed in bot cmd list
        BotCommand("maintenance_off", "Turn off maintenance mode (Admin)"), # Admin command
    ])

    # Schedule individual notification jobs for existing users
    all_users = await db_manager.get_all_users()
    for user in all_users:
        if user['frequency_seconds'] > 0: # Only schedule if frequency is set
            job_name = f"notify_{user['user_id']}"
            # Ensure job is not already scheduled to prevent duplicates on restart
            if not application.job_queue.get_jobs_by_name(job_name):
                application.job_queue.run_repeating(
                    callback=periodic_notification_job,
                    interval=user['frequency_seconds'],
                    first=10, # Run soon after bot starts
                    user_id=user['user_id'],
                    name=job_name
                )
                log.info(f"Scheduled notification job for user {user['user_id']} with interval {user['frequency_seconds']}s.")

async def post_shutdown(application: Application):
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

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

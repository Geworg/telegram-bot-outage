# --- Standard Library ---
import asyncio
import logging
import os
import re
import sys
import inspect
from enum import Enum, auto
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional, Callable

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
    AWAITING_STREET = auto()
    AWAITING_FREQUENCY = auto()
    AWAITING_SUPPORT_MESSAGE = auto()
    AWAITING_SILENT_INTERVAL = auto()

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

# --- Helper & Utility Functions ---
def get_user_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Gets user language from context, falling back to 'en'."""
    user_data = getattr(context, 'user_data', None)
    if user_data is None or not hasattr(user_data, 'get'):
        return 'en'
    return user_data.get("lang", "en")

def get_text(key: str, lang: str, **kwargs) -> str:
    """Gets translated text, falling back to the key itself."""
    return translations.get(key, {}).get(lang, f"<{key}>").format(**kwargs)

async def send_typing_periodically(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    try:
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pass

# --- Вспомогательные безопасные функции ---
def safe_set_user_data(user_data, key, value):
    if user_data is not None and hasattr(user_data, '__setitem__'):
        user_data[key] = value

def safe_get_user_data(user_data, key, default=None):
    if user_data is not None and hasattr(user_data, 'get'):
        return user_data.get(key, default)
    return default

def safe_get(obj, attr, default=None):
    return getattr(obj, attr, default) if obj is not None else default

def safe_call(obj, method, *args, **kwargs):
    if obj is not None and hasattr(obj, method):
        fn = getattr(obj, method)
        if callable(fn):
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                return result
            return None
    return None

def admin_only(func: Callable):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = getattr(update, 'effective_user', None)
        if user is None or getattr(user, 'id', None) not in ADMIN_IDS:
            lang = get_user_lang(context)
            message = getattr(update, 'message', None)
            if message is not None and hasattr(message, 'reply_text'):
                await message.reply_text(get_text("admin_unauthorized", lang))
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- Keyboard Generation ---
def get_main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(get_text("add_address_btn", lang)), KeyboardButton(get_text("remove_address_btn", lang))],
        [KeyboardButton(get_text("my_addresses_btn", lang)), KeyboardButton(get_text("clear_addresses_btn", lang))],
        [KeyboardButton(get_text("frequency_btn", lang)), KeyboardButton(get_text("sound_btn", lang))],
        [KeyboardButton(get_text("qa_btn", lang))],  # Удалена кнопка статистики
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- Command & Button Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = safe_get(update, 'effective_user')
    message = safe_get(update, 'message')
    user_id = safe_get(user, 'id')
    if user is None or message is None or user_id is None:
        return
    user_in_db = await db_manager.get_user(user_id)
    user_data = safe_get(context, 'user_data')
    if not user_in_db:
        safe_set_user_data(user_data, "step", UserSteps.AWAITING_INITIAL_LANG.name)
        user_lang_code = safe_get(user, 'language_code')
        user_lang_code = user_lang_code if user_lang_code in ['ru', 'hy'] else 'en'
        prompt = get_text("initial_language_prompt", user_lang_code)
        buttons = [
            [KeyboardButton("\U0001F1E6\U0001F1F2 Հայերեն" + (" (continue)" if user_lang_code == 'hy' else ""))],
            [KeyboardButton("\U0001F1F7\U0001F1FA Русский" + (" (продолжить)" if user_lang_code == 'ru' else ""))],
            [KeyboardButton("\U0001F1EC\U0001F1E7 English" + (" (continue)" if user_lang_code == 'en' else ""))]
        ]
        keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
        result = safe_call(message, 'reply_text', prompt, reply_markup=keyboard)
        if inspect.isawaitable(result):
            await result
        await db_manager.create_or_update_user(user_id, user_lang_code)
        safe_set_user_data(user_data, "lang", user_lang_code)
    else:
        lang = user_in_db['language_code'] if user_in_db and 'language_code' in user_in_db else 'en'
        safe_set_user_data(user_data, "lang", lang)
        safe_set_user_data(user_data, "step", UserSteps.NONE.name)
        result = safe_call(message, 'reply_text', get_text("menu_message", lang), reply_markup=get_main_menu_keyboard(lang))
        if inspect.isawaitable(result):
            await result

async def add_address_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.AWAITING_REGION.name)
    buttons = [[KeyboardButton(r)] for r in REGIONS_LIST]
    buttons.append([KeyboardButton(get_text("cancel", lang))])
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    message = getattr(update, 'message', None)
    if message is not None and hasattr(message, 'reply_text'):
        await message.reply_text(get_text("choose_region", lang), reply_markup=keyboard)

async def remove_address_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getattr(update, 'effective_user', None)
    message = getattr(update, 'message', None)
    lang = get_user_lang(context)
    user_id = getattr(user, 'id', None)
    if user_id is None:
        return
    addresses = await db_manager.get_user_addresses(user_id)
    if not addresses:
        if message is not None:
            await message.reply_text(get_text("no_addresses_yet", lang))
        return
    buttons = [[InlineKeyboardButton(addr['full_address_text'], callback_data=f"remove_addr_{addr['address_id']}")] for addr in addresses]
    buttons.append([InlineKeyboardButton(get_text("cancel", lang), callback_data="cancel_action")])
    keyboard = InlineKeyboardMarkup(buttons)
    if message is not None:
        await message.reply_text(get_text("select_address_to_remove", lang), reply_markup=keyboard)

async def my_addresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getattr(update, 'effective_user', None)
    message = getattr(update, 'message', None)
    lang = get_user_lang(context)
    user_id = getattr(user, 'id', None)
    if user_id is None:
        return
    addresses = await db_manager.get_user_addresses(user_id)

    if not addresses:
        if message is not None:
            await message.reply_text(get_text("no_addresses_yet", lang))
        return

    response_text = get_text("your_addresses_list_title", lang) + "\n\n"
    for addr in addresses:
        response_text += f"\U0001F4CD `{addr['full_address_text']}`\n"
    if message is not None:
        await message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN_V2)

async def frequency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getattr(update, 'effective_user', None)
    message = getattr(update, 'message', None)
    lang = get_user_lang(context)
    user_id = getattr(user, 'id', None)
    if user_id is None or message is None:
        return
    user_db = await db_manager.get_user(user_id)
    if not user_db:
        return
    user_tier = "Ultra" if user_id in ADMIN_IDS else user_db.get('tier', 'Free')
    user_tier_index = TIER_ORDER.index(user_tier)
    buttons = []
    for key, option in FREQUENCY_OPTIONS.items():
        if user_tier_index >= TIER_ORDER.index(option['tier']):
            buttons.append([KeyboardButton(option[lang])])
    current_freq_text = get_text("frequency_current", lang)
    for option in FREQUENCY_OPTIONS.values():
        if option['interval'] == user_db.get('frequency_seconds'):
            current_freq_text += f" {option[lang]}"
            break
    keyboard = ReplyKeyboardMarkup(buttons + [[KeyboardButton(get_text("cancel", lang))]], resize_keyboard=True, one_time_keyboard=True)
    if hasattr(message, 'reply_text'):
        await message.reply_text(f"{current_freq_text}\n\n{get_text('frequency_prompt', lang)}", reply_markup=keyboard)
    safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.AWAITING_FREQUENCY.name)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getattr(update, 'effective_user', None)
    message = getattr(update, 'message', None)
    user_id = getattr(user, 'id', None)
    lang = get_user_lang(context)
    if user_id is None or user_id not in ADMIN_IDS or message is None:
        if message is not None:
            await message.reply_text(get_text("admin_unauthorized", lang))
        return
    system_stats = await db_manager.get_system_stats()
    user_notif_count = await db_manager.get_user_notification_count(user_id)
    await message.reply_text(get_text("stats_message", lang, **system_stats, user_notifications=user_notif_count), parse_mode=ParseMode.MARKDOWN_V2)

async def clear_addresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    buttons = [[
        InlineKeyboardButton(get_text("yes", lang), callback_data="confirm_clear_yes"),
        InlineKeyboardButton(get_text("no", lang), callback_data="cancel_action")
    ]]
    keyboard = InlineKeyboardMarkup(buttons)
    message = getattr(update, 'message', None)
    if message is not None:
        await message.reply_text(get_text("clear_addresses_prompt", lang), reply_markup=keyboard)

async def qa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    buttons = [
        [InlineKeyboardButton(get_text("qa_placeholder_q1", lang), callback_data="qa_1")],
        [InlineKeyboardButton(get_text("qa_placeholder_q2", lang), callback_data="qa_2")],
        [InlineKeyboardButton(get_text("support_btn", lang), callback_data="qa_support")],
        [InlineKeyboardButton(get_text("back_btn", lang), callback_data="qa_back")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    message = getattr(update, 'message', None)
    if message is not None:
        await message.reply_text(get_text("qa_title", lang), reply_markup=keyboard)

# Исправление: await только для async, user_data проверки, безопасные вызовы
async def sound_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getattr(update, 'effective_user', None)
    message = getattr(update, 'message', None)
    callback_query = getattr(update, 'callback_query', None)
    user_id = getattr(user, 'id', None)
    lang = get_user_lang(context)
    if user_id is None:
        return
    user_db = await db_manager.get_user(user_id)
    if not user_db:
        return
    sound_status = get_text("sound_on_status", lang) if user_db.get('notification_sound_enabled') else get_text("sound_off_status", lang)
    silent_status = get_text("silent_mode_on_status", lang, start=user_db['silent_mode_start_time'].strftime('%H:%M'), end=user_db['silent_mode_end_time'].strftime('%H:%M')) if user_db.get('silent_mode_enabled') and user_db.get('silent_mode_start_time') and user_db.get('silent_mode_end_time') else get_text("silent_mode_off_status", lang)
    text = f"{get_text('sound_settings_title', lang)}\n\n{sound_status}\n{silent_status}"
    buttons = [
        [InlineKeyboardButton(get_text("sound_toggle_off" if user_db.get('notification_sound_enabled') else "sound_toggle_on", lang), callback_data="sound_toggle_main")],
        [InlineKeyboardButton(get_text("silent_mode_toggle_off" if user_db.get('silent_mode_enabled') else "silent_mode_toggle_on", lang), callback_data="sound_toggle_silent")],
        [InlineKeyboardButton(get_text("back_btn", lang), callback_data="sound_back")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    target_message = None
    if callback_query and hasattr(callback_query, 'message') and callback_query.message is not None:
        target_message = callback_query.message
    elif message is not None:
        target_message = message
    if target_message is not None:
        try:
            if callback_query and hasattr(target_message, 'edit_text') and callable(target_message.edit_text):
                result = target_message.edit_text(text, reply_markup=keyboard)
                if inspect.isawaitable(result):
                    await result
            elif hasattr(target_message, 'reply_text') and callable(target_message.reply_text):
                result = target_message.reply_text(text, reply_markup=keyboard)
                if inspect.isawaitable(result):
                    await result
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                log.warning(f"Failed to edit sound menu: {e}")

@admin_only
async def maintenance_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db_manager.set_bot_status("maintenance_mode", "true")
    lang = get_user_lang(context)
    message = getattr(update, 'message', None)
    user = getattr(update, 'effective_user', None)
    user_id = getattr(user, 'id', None)
    if message is not None:
        await message.reply_text(get_text("maintenance_on_feedback", lang))
    if user_id is not None:
        log.info(f"Admin {user_id} enabled maintenance mode.")

@admin_only
async def maintenance_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db_manager.set_bot_status("maintenance_mode", "false")
    lang = get_user_lang(context)
    message = getattr(update, 'message', None)
    user = getattr(update, 'effective_user', None)
    user_id = getattr(user, 'id', None)
    if message is not None:
        await message.reply_text(get_text("maintenance_off_feedback", lang))
    if user_id is not None:
        log.info(f"Admin {user_id} disabled maintenance mode.")

# --- Заглушка для отсутствующей функции в db_manager ---
if not hasattr(db_manager, 'find_outages_for_address_text'):
    async def find_outages_for_address_text(address_text):
        return []
    setattr(db_manager, 'find_outages_for_address_text', find_outages_for_address_text)

# --- Callback: clear_addresses_callback ---
async def clear_addresses_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = getattr(update, 'callback_query', None)
    if query is None or not hasattr(query, 'from_user') or query.from_user is None:
        return
    user_id = getattr(query.from_user, 'id', None)
    lang = get_user_lang(context)
    if user_id is None:
        return
    await db_manager.clear_all_user_addresses(user_id)
    if hasattr(query, 'edit_message_text') and callable(query.edit_message_text):
        result = safe_call(query, 'edit_message_text', get_text("all_addresses_cleared", lang))
        if inspect.isawaitable(result):
            await result
    chat = getattr(update, 'effective_chat', None)
    chat_id = getattr(chat, 'id', None)
    if chat_id is not None:
        await context.bot.send_message(chat_id=chat_id, text=get_text("menu_message", lang), reply_markup=get_main_menu_keyboard(lang))

# --- Main Message Router ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_maintenance = await db_manager.get_bot_status("maintenance_mode")
    user = getattr(update, 'effective_user', None)
    message = getattr(update, 'message', None)
    if is_maintenance == "true" and (user is None or getattr(user, 'id', None) not in ADMIN_IDS):
        lang = get_user_lang(context)
        if message is not None and hasattr(message, 'reply_text'):
            await message.reply_text(get_text("maintenance_user_notification", lang))
        return
    user_data = getattr(context, 'user_data', None)
    step = safe_get_user_data(user_data, "step")
    lang = get_user_lang(context)
    if message and hasattr(message, 'text') and message.text == get_text("cancel", lang):
        safe_set_user_data(user_data, "step", UserSteps.NONE.name)
        if hasattr(message, 'reply_text'):
            await message.reply_text(get_text("action_cancelled", lang), reply_markup=get_main_menu_keyboard(lang))
        return
    step_handlers = {
        UserSteps.AWAITING_INITIAL_LANG.name: handle_language_selection,
        UserSteps.AWAITING_REGION.name: handle_region_selection,
        UserSteps.AWAITING_STREET.name: handle_street_input,
        UserSteps.AWAITING_FREQUENCY.name: handle_frequency_selection,
        UserSteps.AWAITING_SUPPORT_MESSAGE.name: handle_support_message,
        UserSteps.AWAITING_SILENT_INTERVAL.name: handle_silent_interval_input,
        UserSteps.NONE.name: handle_main_menu_text,
    }
    handler = step_handlers.get(step) if step is not None else handle_main_menu_text
    if handler is not None and callable(handler):
        await handler(update, context)

async def handle_main_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = getattr(update, 'message', None)
    if message is None:
        return
    text = message.text
    lang = get_user_lang(context)
    menu_map = {
        get_text("add_address_btn", lang): add_address_command,
        get_text("remove_address_btn", lang): remove_address_command,
        get_text("my_addresses_btn", lang): my_addresses_command,
        get_text("frequency_btn", lang): frequency_command,
        get_text("sound_btn", lang): sound_command,
        get_text("qa_btn", lang): qa_command,
        get_text("stats_btn", lang): stats_command,
        get_text("clear_addresses_btn", lang): clear_addresses_command,
    }
    command_to_run = menu_map.get(text)
    if command_to_run:
        await command_to_run(update, context)
    else:
        await message.reply_text(get_text("unknown_command", lang), reply_markup=get_main_menu_keyboard(lang))

# --- State Logic Handlers ---
async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = getattr(update, 'message', None)
    if message is None:
        return
    text = message.text
    lang_code = 'en'
    if text and 'Հայերեն' in text:
        lang_code = 'hy'
    elif text and 'Русский' in text:
        lang_code = 'ru'
    user_data = getattr(context, 'user_data', None)
    if user_data is not None:
        user_data["lang"] = lang_code
    user = getattr(update, 'effective_user', None)
    user_id = getattr(user, 'id', None)
    if user_id is not None:
        await db_manager.update_user_language(user_id, lang_code)
    await message.reply_text(
        get_text("language_set_success", lang_code),
        reply_markup=get_main_menu_keyboard(lang_code)
    )
    if user_data is not None:
        user_data["step"] = UserSteps.NONE.name

async def handle_region_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = getattr(update, 'message', None)
    if message is None:
        return
    region = getattr(message, 'text', None)
    if region not in REGIONS_LIST:
        lang = get_user_lang(context)
        if hasattr(message, 'reply_text'):
            await message.reply_text(get_text("unknown_command", lang))
        return
    safe_set_user_data(getattr(context, 'user_data', None), "selected_region", region)
    lang = get_user_lang(context)
    if hasattr(message, 'reply_text'):
        await message.reply_text(get_text("enter_street", lang, region=region), reply_markup=ReplyKeyboardRemove())
    safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.AWAITING_STREET.name)

# Безопасная работа с context.user_data и .get/.pop
async def handle_street_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = getattr(update, 'message', None)
    chat = getattr(update, 'effective_chat', None)
    if message is None or chat is None:
        return
    chat_id = getattr(chat, 'id', None)
    if chat_id is None:
        return
    lang = get_user_lang(context)
    typing_task = asyncio.create_task(send_typing_periodically(context, chat_id))
    try:
        street_text = getattr(message, 'text', None)
        region = None
        user_data = getattr(context, 'user_data', None)
        if user_data is not None and hasattr(user_data, 'get'):
            region = user_data.get("selected_region", "Armenia")
        full_query = f"{region}, {street_text}"
        await message.reply_text(get_text("address_verifying", lang))
        verified_address = await api_clients.get_verified_address_from_yandex(full_query)
        if verified_address and verified_address.get('full_address'):
            if user_data is not None:
                user_data["verified_address_cache"] = verified_address
            buttons = [[
                InlineKeyboardButton(get_text("yes", lang), callback_data="confirm_address_yes"),
                InlineKeyboardButton(get_text("no", lang), callback_data="cancel_action")
            ]]
            keyboard = InlineKeyboardMarkup(buttons)
            escaped_address = verified_address['full_address'].replace('-', '\\-').replace('.', '\\.')
            await message.reply_text(
                get_text("address_confirm_prompt", lang, address=escaped_address),
                reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await message.reply_text(get_text("address_not_found_yandex", lang))
            if user_data is not None:
                user_data["step"] = UserSteps.AWAITING_STREET.name
    finally:
        typing_task.cancel()

async def handle_frequency_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = getattr(update, 'message', None)
    user = getattr(update, 'effective_user', None)
    if message is None or user is None:
        return
    text = message.text
    lang = get_user_lang(context)
    user_id = getattr(user, 'id', None)
    selected_interval = None
    for option in FREQUENCY_OPTIONS.values():
        if option[lang] == text:
            selected_interval = option['interval']
            break
    if selected_interval and user_id is not None:
        await db_manager.update_user_frequency(user_id, selected_interval)
        result = safe_call(message, 'reply_text', get_text("frequency_set_success", lang), reply_markup=get_main_menu_keyboard(lang))
        if inspect.isawaitable(result):
            await result
        safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.NONE.name)
    else:
        result = safe_call(message, 'reply_text', get_text("unknown_command", lang))
        if inspect.isawaitable(result):
            await result

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getattr(update, 'effective_user', None)
    message = getattr(update, 'message', None)
    lang = get_user_lang(context)
    if not SUPPORT_CHAT_ID or user is None or message is None:
        return
    user_mention = getattr(user, 'mention_markdown_v2', lambda: str(getattr(user, 'id', 'user')))()
    support_message = get_text("support_message_from_user", "en", user_mention=user_mention, user_id=getattr(user, 'id', None), message=message.text)
    await context.bot.send_message(chat_id=SUPPORT_CHAT_ID, text=support_message, parse_mode=ParseMode.MARKDOWN_V2)
    result = safe_call(message, 'reply_text', get_text("support_message_sent", lang), reply_markup=get_main_menu_keyboard(lang))
    if inspect.isawaitable(result):
        await result
    safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.NONE.name)

def fuzzy_parse_time(text: str) -> Optional[str]:
    """
    Пытается распознать время в различных форматах (22,30, 07,00, 22-30, 2230 и т.д.) и вернуть строку HH:MM.
    Возвращает None, если не удалось распознать.
    """
    text = text.strip().replace(',', ':').replace('.', ':').replace('-', ':').replace(' ', ':')
    # Пример: 2230 -> 22:30
    if re.fullmatch(r'\d{4}', text):
        return f"{text[:2]}:{text[2:]}"
    # Пример: 22:30 или 22:3
    m = re.match(r'^(\d{1,2}):(\d{1,2})$', text)
    if m:
        h, m_ = m.groups()
        return f"{int(h):02d}:{int(m_):02d}"
    # Пример: 22
    if re.fullmatch(r'\d{1,2}', text):
        return f"{int(text):02d}:00"
    return None

async def handle_silent_interval_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = getattr(update, 'message', None)
    if message is None:
        return
    text = message.text
    lang = get_user_lang(context)
    # Попробуем найти два времени в строке любым способом
    # Например: 22,30 07,00 или 22-30 7-00 или 2230 700
    # Разделим по пробелу или тире
    parts = re.split(r'[\s–—-]+', text.strip())
    if len(parts) == 1:
        # Может быть через дефис
        parts = re.split(r'\s*-\s*', text.strip())
    if len(parts) == 1:
        # Может быть через запятую
        parts = re.split(r'\s*,\s*', text.strip())
    if len(parts) == 2:
        start = fuzzy_parse_time(parts[0])
        end = fuzzy_parse_time(parts[1])
    else:
        # Попробуем найти все группы из 2-4 цифр
        found = re.findall(r'\d{1,2}[:.,-]?\d{0,2}', text)
        if len(found) >= 2:
            start = fuzzy_parse_time(found[0])
            end = fuzzy_parse_time(found[1])
        else:
            start = end = None
    if start and end:
        # Спросим подтверждение
        confirm_text = f"{get_text('confirm_silent_mode_period', lang, start=start, end=end)}"
        buttons = [
            [InlineKeyboardButton(get_text('yes', lang), callback_data=f'silent_confirm_yes:{start}:{end}')],
            [InlineKeyboardButton(get_text('no_edit', lang), callback_data='silent_confirm_edit')],
            [InlineKeyboardButton(get_text('cancel', lang), callback_data='cancel_action')]
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        await message.reply_text(confirm_text, reply_markup=keyboard)
        user_data = getattr(context, 'user_data', None)
        if user_data is not None:
            user_data['pending_silent_times'] = {'start': start, 'end': end}
        return
    else:
        await message.reply_text(get_text("invalid_time_interval", lang))
        return

# --- Callback Query Handlers ---
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = getattr(update, 'callback_query', None)
    if query is None or not hasattr(query, 'data') or query.data is None:
        return
    if not hasattr(query, 'answer') or not callable(query.answer):
        return
    result = safe_call(query, 'answer')
    if inspect.isawaitable(result):
        await result
    data = query.data
    if data.startswith("remove_addr_"):
        await remove_address_callback(update, context)
    elif data == "confirm_address_yes":
        await confirm_address_callback(update, context)
    elif data == "confirm_clear_yes":
        await clear_addresses_callback(update, context)
    elif data.startswith("qa_"):
        await qa_callback_handler(update, context)
    elif data.startswith("sound_"):
        await sound_callback_handler(update, context)
    elif data == "cancel_action":
        await cancel_callback(update, context)
    elif data.startswith('silent_confirm_yes:'):
        # Подтверждение тихого режима
        parts = data.split(':')
        if len(parts) == 3:
            _, start, end = parts
            user = getattr(query, 'from_user', None)
            user_id = getattr(user, 'id', None)
            if user_id is not None:
                settings = {"silent_mode_start_time": start, "silent_mode_end_time": end, "silent_mode_enabled": True}
                await db_manager.update_user_sound_settings(user_id, settings)
                lang = get_user_lang(context)
                if hasattr(query, 'edit_message_text') and callable(query.edit_message_text):
                    result = safe_call(query, 'edit_message_text', get_text("silent_interval_set", lang), reply_markup=ReplyKeyboardRemove())
                    if inspect.isawaitable(result):
                        await result
                user_data = getattr(context, 'user_data', None)
                if user_data is not None:
                    user_data["step"] = UserSteps.NONE.name
                await sound_command(update, context)
        return
    elif data == 'silent_confirm_edit':
        lang = get_user_lang(context)
        if hasattr(query, 'edit_message_text') and callable(query.edit_message_text):
            result = safe_call(query, 'edit_message_text', get_text("enter_silent_interval_prompt", lang))
            if inspect.isawaitable(result):
                await result
        user_data = getattr(context, 'user_data', None)
        if user_data is not None:
            user_data["step"] = UserSteps.AWAITING_SILENT_INTERVAL.name
        return
        
async def remove_address_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = getattr(update, 'callback_query', None)
    if query is None or not hasattr(query, 'data') or query.data is None:
        return
    lang = get_user_lang(context)
    data_parts = query.data.split('_')
    if len(data_parts) < 3:
        return
    try:
        address_id_to_remove = int(data_parts[2])
    except ValueError:
        return
    user = getattr(query, 'from_user', None)
    user_id = getattr(user, 'id', None)
    if user_id is None:
        return
    await db_manager.remove_user_address(address_id_to_remove, user_id)
    await query.edit_message_text(get_text("address_removed_success", lang))
    if hasattr(query, 'message') and query.message is not None and hasattr(query.message, 'chat_id'):
        await context.bot.send_message(chat_id=query.message.chat_id, text=get_text("menu_message", lang), reply_markup=get_main_menu_keyboard(lang))

async def confirm_address_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = getattr(update, 'callback_query', None)
    if query is None or not hasattr(query, 'from_user') or query.from_user is None:
        return
    user_id = getattr(query.from_user, 'id', None)
    lang = get_user_lang(context)
    user_data = getattr(context, 'user_data', None)
    address_data = user_data.pop("verified_address_cache", None) if user_data is not None and hasattr(user_data, 'pop') else None
    if not address_data or user_id is None:
        await query.edit_message_text("Error: Cached address data expired.")
        return
    success = await db_manager.add_user_address(
        user_id=user_id, region=address_data.get('region', 'N/A'),
        street=address_data.get('street', 'N/A'), full_address=address_data.get('full_address'),
        lat=address_data.get('latitude'), lon=address_data.get('longitude')
    )
    if success:
        await query.edit_message_text(get_text("address_added_success", lang))
        await check_outages_for_new_address(update, context, address_data)
    else:
        await query.edit_message_text(get_text("address_already_exists", lang))
    if user_data is not None:
        user_data["step"] = UserSteps.NONE.name
    if hasattr(query, 'message') and query.message is not None and hasattr(query.message, 'chat_id'):
        await context.bot.send_message(
            chat_id=query.message.chat_id, text=get_text("menu_message", lang),
            reply_markup=get_main_menu_keyboard(lang)
        )

async def check_outages_for_new_address(update: Update, context: ContextTypes.DEFAULT_TYPE, address_data: dict):
    lang = get_user_lang(context)
    chat_id = safe_get(safe_get(update, 'effective_chat'), 'id')
    if chat_id is None:
        return
    await context.bot.send_message(chat_id, get_text("outage_check_on_add_title", lang), parse_mode=ParseMode.MARKDOWN_V2)
    await asyncio.gather(
        parse_all_water_announcements_async(), parse_all_gas_announcements_async(), parse_all_electric_announcements_async()
    )
    all_recent_outages = await db_manager.find_outages_for_address_text(address_data['full_address'])
    if not all_recent_outages:
        await context.bot.send_message(chat_id, get_text("outage_check_on_add_none_found", lang))
    else:
        response_text = get_text("outage_check_on_add_found", lang)
        for outage in all_recent_outages:
            response_text += f"\n\n- {outage['source_type']}: {outage.get('start_datetime', 'N/A')}"

        await context.bot.send_message(chat_id, response_text)

    last_outage = await db_manager.get_last_outage_for_address(address_data['full_address'])
    if last_outage:
        await context.bot.send_message(chat_id, f"{get_text('last_outage_recorded', lang)} {last_outage['end_datetime'].strftime('%Y-%m-%d')}")
    else:
        await context.bot.send_message(chat_id, get_text("no_past_outages", lang))

async def qa_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = safe_get(update, 'callback_query')
    lang = get_user_lang(context)
    data = safe_get(query, 'data')
    if query is None or not data:
        return
    action = data.split('_')[-1] if data else None
    user_data = getattr(context, 'user_data', None)
    if action == "support":
        safe_set_user_data(user_data, "step", UserSteps.AWAITING_SUPPORT_MESSAGE.name)
        result = safe_call(query, 'edit_message_text', get_text("support_prompt", lang))
        if inspect.isawaitable(result):
            await result
    elif action == "back":
        result = safe_call(query, 'delete')
        if inspect.isawaitable(result):
            await result
    else:
        answer_key = f"qa_placeholder_a{action}"
        result = safe_call(query, 'answer', text=get_text(answer_key, lang), show_alert=True)
        if inspect.isawaitable(result):
            await result

async def sound_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = safe_get(update, 'callback_query')
    user_id = safe_get(safe_get(query, 'from_user'), 'id')
    action = safe_get(query, 'data')
    if user_id is None:
        return
    if action == "sound_toggle_main":
        user = await db_manager.get_user(user_id)
        notif_enabled = user['notification_sound_enabled'] if user and 'notification_sound_enabled' in user else False
        await db_manager.update_user_sound_settings(user_id, {"notification_sound_enabled": not notif_enabled})
    elif action == "sound_toggle_silent":
        user = await db_manager.get_user(user_id)
        silent_enabled = user['silent_mode_enabled'] if user and 'silent_mode_enabled' in user else False
        if silent_enabled:
            await db_manager.update_user_sound_settings(user_id, {"silent_mode_enabled": False})
        else:
            lang = get_user_lang(context)
            safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.AWAITING_SILENT_INTERVAL.name)
            result = safe_call(safe_get(query, 'message'), 'reply_text', get_text("enter_silent_interval_prompt", lang))
            if inspect.isawaitable(result):
                await result
            return
    elif action == "sound_back":
        result = safe_call(query, 'delete')
        if inspect.isawaitable(result):
            await result
        return
    await sound_command(update, context)

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    query = safe_get(update, 'callback_query')
    result = safe_call(query, 'edit_message_text', text=get_text("action_cancelled", lang))
    if inspect.isawaitable(result):
        await result
    chat_id = safe_get(safe_get(update, 'effective_chat'), 'id')
    if chat_id is not None:
        await context.bot.send_message(chat_id=chat_id, text=get_text("menu_message", lang), reply_markup=get_main_menu_keyboard(lang))

# --- Periodic Jobs ---
async def periodic_site_check_job(context: ContextTypes.DEFAULT_TYPE):
    log.info("Starting periodic site check job...")
    await asyncio.gather(
        parse_all_water_announcements_async(),
        parse_all_gas_announcements_async(),
        parse_all_electric_announcements_async()
    )
    log.info("Periodic site check job finished.")

# --- Application Setup ---
async def post_init(application: Application):
    await db_manager.init_db_pool()
    ai_engine.load_models()
    
    commands = {
        "en": [BotCommand("start", "Start/Menu"), BotCommand("myaddresses", "My addresses"), BotCommand("clearaddresses", "Clear all addresses"), BotCommand("sound", "Sound settings"), BotCommand("frequency", "Check frequency"), BotCommand("qa", "Q&A and Support"), BotCommand("stats", "Statistics")],
        "ru": [BotCommand("start", "Старт/Меню"), BotCommand("myaddresses", "Мои адреса"), BotCommand("clearaddresses", "Очистить все адреса"), BotCommand("sound", "Настройки звука"), BotCommand("frequency", "Частота проверок"), BotCommand("qa", "Вопрос-ответ"), BotCommand("stats", "Статистика")],
        "hy": [BotCommand("start", "Սկիզբ/Մենյու"), BotCommand("myaddresses", "Իմ հասցեները"), BotCommand("clearaddresses", "Մաքրել բոլոր հասցեները"), BotCommand("sound", "Ձայնի կարգավորումներ"), BotCommand("frequency", "Ստուգման հաճախականություն"), BotCommand("qa", "Հարց ու պատասխան"), BotCommand("stats", "Վիճակագրություն")]
    }
    for lang_code, cmd_list in commands.items():
        await application.bot.set_my_commands(cmd_list, language_code=lang_code)
    log.info("Bot commands set. Bot is initialized.")

async def post_shutdown(application: Application):
    await db_manager.close_db_pool()
    log.info("Bot shut down gracefully.")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not isinstance(token, str):
        log.critical("TELEGRAM_BOT_TOKEN not set or invalid. Exiting.")
        sys.exit(1)

    application = (
        ApplicationBuilder().token(token)
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

    job_queue = getattr(application, 'job_queue', None)
    job_interval = int(os.getenv("JOB_INTERVAL_SECONDS", "1800"))
    if job_queue is not None and hasattr(job_queue, 'run_repeating') and callable(job_queue.run_repeating):
        job_queue.run_repeating(periodic_site_check_job, interval=job_interval, first=10, name="site_check")
        log.info(f"Scheduled 'site_check' job to run every {job_interval} seconds.")
    else:
        log.warning("Job queue is not available. Periodic jobs will not run.")

    log.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

# --- Standard Library ---
import asyncio
import logging
import os
import re
import sys
import inspect
import time
from enum import Enum, auto
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional, Callable
from contextlib import asynccontextmanager

# --- Third-party Libraries ---
from dotenv import load_dotenv
from telegram import (
    Update,
    BotCommandScopeChat,
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

if os.getenv("BOT_ENABLED", "false").lower() != "true":
    print("Бот отключён переменной среды. Завершение работы.")
    sys.exit(0)

# --- Constants ---
class UserSteps(Enum):
    NONE = auto()
    AWAITING_INITIAL_LANG = auto()
    AWAITING_REGION = auto()
    AWAITING_STREET = auto()
    AWAITING_FREQUENCY = auto()
    AWAITING_SUPPORT_MESSAGE = auto()
    AWAITING_CHECK_REGION = auto()
    AWAITING_CHECK_ADDRESS_INPUT = auto()

ADMIN_IDS = [int(i) for i in os.getenv("ADMIN_USER_IDS", "").split(',') if i]
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID")
TIER_ORDER = ["Free", "Basic", "Premium", "Ultra"]
REGIONS_LISTS = {"hy": ["Երևան", "Արագածոտն", "Արարատ", "Արմավիր", "Գեղարքունիք", "Լոռի", "Կոտայք", "Շիրակ", "Սյունիք", "Վայոց Ձոր", "Տավուշ"],
                 "ru": ["Ереван", "Арагацотн", "Арарат", "Армавир", "Гегаркуник", "Лори", "Котайк", "Ширак", "Сюник", "Вайоц Дзор", "Тавуш"],
                 "en": ["Yerevan", "Aragatsotn", "Ararat", "Armavir", "Gegharkunik", "Lori", "Kotayk", "Shirak", "Syunik", "Vayots Dzor", "Tavush"]}

def get_regions_list(lang: str) -> list:
    return REGIONS_LISTS.get(lang, REGIONS_LISTS["en"])

FREQUENCY_OPTIONS = {
    "Free_6h": {"interval": 21600, "hy": "⏱ 6 ժամ", "ru": "⏱ 6 часов", "en": "⏱ 6 hours", "tier": "Free"},
    "Free_12h": {"interval": 43200, "hy": "⏱ 12 ժամ", "ru": "⏱ 12 часов", "en": "⏱ 12 hours", "tier": "Free"},
    "Basic_1h": {"interval": 3600, "hy": "⏱ 1 ժամ", "ru": "⏱ 1 час", "en": "⏱ 1 hour", "tier": "Basic"},
    "Premium_30m": {"interval": 1800, "hy": "⏱ 30 րոպե", "ru": "⏱ 30 минут", "en": "⏱ 30 min", "tier": "Premium"},
    "Ultra_15m": {"interval": 900, "hy": "⏱ 15 րոպե", "ru": "⏱ 15 минут", "en": "⏱ 15 min", "tier": "Ultra"},
}

# --- New array of keys for FAQ ---
FAQ_QUESTION_KEYS = [f"qa_q{i+1}" for i in range(20)]
FAQ_ANSWER_KEYS = [f"qa_a{i+1}" for i in range(20)]
FAQ_PAGE_SIZE = 5

# --- Helper & Utility Functions ---
def get_user_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Gets user language from context, falling back to 'en'."""
    user_data = getattr(context, 'user_data', None)
    if user_data is None or not hasattr(user_data, 'get'):
        return 'en'
    lang = user_data.get("lang", "en")
    if lang not in ['ru', 'en', 'hy']:
        return 'en'
    return lang

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

@asynccontextmanager
async def send_typing_if_slow(context, chat_id):
    task = None
    is_sent = False
    async def typing():
        nonlocal is_sent
        await asyncio.sleep(1)
        is_sent = True
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass
    try:
        task = asyncio.create_task(typing())
        yield
    finally:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

# --- Auxiliary security functions ---
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
        [KeyboardButton(get_text("frequency_btn", lang)), KeyboardButton(get_text("qa_btn", lang))],
        [KeyboardButton(get_text("check_address_btn", lang))],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- Command & Button Handlers ---
def typing_indicator_for_all(func):
    async def wrapper(update, context, *args, **kwargs):
        chat_id = None
        if hasattr(update, 'effective_chat') and getattr(update, 'effective_chat', None):
            chat_id = update.effective_chat.id
        elif hasattr(update, 'message') and getattr(update, 'message', None):
            chat_id = update.message.chat_id
        elif hasattr(update, 'callback_query') and getattr(update, 'callback_query', None):
            chat_id = update.callback_query.message.chat_id if update.callback_query.message else None
        if chat_id is not None:
            async with send_typing_if_slow(context, chat_id):
                return await func(update, context, *args, **kwargs)
        else:
            return await func(update, context, *args, **kwargs)
    return wrapper

@typing_indicator_for_all
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = safe_get(update, 'effective_user')
    message = safe_get(update, 'message')
    user_id = safe_get(user, 'id')
    if user is None or message is None or user_id is None:
        return
    user_in_db = await db_manager.get_user(user_id)
    user_data = safe_get(context, 'user_data')
    application = getattr(context, 'application', None)
    user_nick = getattr(user, 'username', 'none') or 'none'
    user_name = (getattr(user, 'first_name', '') or '') + (' ' + getattr(user, 'last_name', '') if getattr(user, 'last_name', '') else '')
    user_name = user_name.strip()
    if not user_in_db:
        safe_set_user_data(user_data, "step", UserSteps.AWAITING_INITIAL_LANG.name)
        user_lang_code = safe_get(user_data, "lang") or safe_get(user, 'language_code')
        if user_lang_code not in ['ru', 'en', 'hy']:
            user_lang_code = 'en'
        prompt = get_text("initial_language_prompt", user_lang_code)
        buttons = [
            [KeyboardButton("\U0001F1E6\U0001F1F2 Հայերեն" + (" (continue)" if user_lang_code == 'hy' else ""))],
            [KeyboardButton("\U0001F1F7\U0001F1FA Русский" + (" (продолжить)" if user_lang_code == 'ru' else ""))],
            [KeyboardButton("\U0001F1EC\U0001F1E7 English" + (" (continue)" if user_lang_code == 'en' else ""))]
        ]
        keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
        async with send_typing_if_slow(context, message.chat_id):
            result = safe_call(message, 'reply_text', prompt, reply_markup=keyboard)
            if inspect.isawaitable(result):
                await result
        await db_manager.create_or_update_user(user_id, user_lang_code, user_nick, user_name)
        safe_set_user_data(user_data, "lang", user_lang_code)
        if application:
            await update_user_commands_menu(application, user_lang_code, user_id)
    else:
        lang = user_in_db['language_code'] if user_in_db and 'language_code' in user_in_db else 'en'
        if lang not in ['ru', 'en', 'hy']:
            lang = 'en'
        safe_set_user_data(user_data, "lang", lang)
        safe_set_user_data(user_data, "step", UserSteps.NONE.name)
        if application:
            await update_user_commands_menu(application, lang, user_id)
        async with send_typing_if_slow(context, message.chat_id):
            result = safe_call(message, 'reply_text', get_text("menu_message", lang), reply_markup=get_main_menu_keyboard(lang))
            if inspect.isawaitable(result):
                await result
    await db_manager.create_or_update_user(user_id, safe_get(user, 'language_code', 'en'), user_nick, user_name)

@typing_indicator_for_all
async def add_address_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.AWAITING_REGION.name)
    regions = get_regions_list(lang)
    buttons = [[KeyboardButton(r)] for r in regions]
    buttons.append([KeyboardButton(get_text("cancel", lang))])
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    message = getattr(update, 'message', None)
    if message is not None and hasattr(message, 'reply_text'):
        await message.reply_text(get_text("choose_region", lang), reply_markup=keyboard)

@typing_indicator_for_all
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

@typing_indicator_for_all
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

@typing_indicator_for_all
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

def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_ * [ ] ( ) ~ ` > # + - = | { } . !'.split()
    for ch in escape_chars:
        text = text.replace(ch, f'\\{ch}')
    return text

@typing_indicator_for_all
@admin_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getattr(update, 'effective_user', None)
    message = getattr(update, 'message', None)
    user_id = getattr(user, 'id', None)
    lang = get_user_lang(context)
    if message is None or user_id is None:
        return
    system_stats = await db_manager.get_system_stats()
    user_notif_count = await db_manager.get_user_notification_count(int(user_id))
    lines = [
        f"{escape_markdown_v2(str(get_text('stats_title', lang)))}",
        f"{escape_markdown_v2(str(get_text('stats_total_users', lang)))}: {str(system_stats.get('total_users', 0))}",
        f"{escape_markdown_v2(str(get_text('stats_total_addresses', lang)))}: {str(system_stats.get('total_addresses', 0))}",
        f"{escape_markdown_v2(str(get_text('stats_your_info', lang)))}: {escape_markdown_v2(str(user_id))}",
        f"{escape_markdown_v2(str(get_text('stats_notif_received', lang)))}: {str(user_notif_count)}",
    ]
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)

@typing_indicator_for_all
async def clear_addresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    user = getattr(update, 'effective_user', None)
    message = getattr(update, 'message', None)
    user_id = getattr(user, 'id', None)
    if user_id is None or message is None:
        return
    addresses = await db_manager.get_user_addresses(user_id)
    if not addresses:
        await message.reply_text(get_text("no_addresses_yet", lang), reply_markup=get_main_menu_keyboard(lang))
        return
    buttons = [[
        InlineKeyboardButton(get_text("yes", lang), callback_data="confirm_clear_yes"),
        InlineKeyboardButton(get_text("no_cancel_action_btn", lang), callback_data="cancel_action")
    ]]
    keyboard = InlineKeyboardMarkup(buttons)
    await message.reply_text(get_text("clear_addresses_prompt", lang), reply_markup=keyboard)

@typing_indicator_for_all
async def qa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    page = 0
    user_data = getattr(context, 'user_data', None)
    if user_data is not None:
        user_data['faq_page'] = page
    await send_faq_page(update, context, page, lang)

@typing_indicator_for_all
async def send_faq_page(update_or_query, context, page, lang):
    start = page * FAQ_PAGE_SIZE
    end = start + FAQ_PAGE_SIZE
    question_keys = FAQ_QUESTION_KEYS[start:end]
    buttons = [[InlineKeyboardButton(get_text(qk, lang), callback_data=f"faq_q_{i}_{page}")
                ] for i, qk in enumerate(question_keys, start=0)]
    nav_buttons = []
    prev_text = get_text("faq_prev_btn", lang) if "faq_prev_btn" in translations else {"ru": "⏮ Назад", "en": "⏮ Back", "hy": "⏮ Հետ"}[lang]
    next_text = get_text("faq_next_btn", lang) if "faq_next_btn" in translations else {"ru": "⏭ Вперёд", "en": "⏭ Next", "hy": "⏭ Առաջ"}[lang]
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(prev_text, callback_data=f"faq_prev_{page}"))
    if end < len(FAQ_QUESTION_KEYS):
        nav_buttons.append(InlineKeyboardButton(next_text, callback_data=f"faq_next_{page}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(get_text("support_btn", lang), callback_data="qa_support")])
    keyboard = InlineKeyboardMarkup(buttons)
    text = get_text("qa_title", lang)
    if hasattr(update_or_query, 'message') and update_or_query.message is not None:
        await update_or_query.message.reply_text(text, reply_markup=keyboard)
    elif hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(text, reply_markup=keyboard)

@typing_indicator_for_all
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

@typing_indicator_for_all
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
        await query.edit_message_text(get_text("address_added_success", lang), reply_markup=None)
        if message := getattr(query, 'message', None):
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=get_text("menu_message", lang),
                reply_markup=get_main_menu_keyboard(lang)
            )
        if user_data is not None:
            user_data["step"] = UserSteps.NONE.name
        await check_outages_for_new_address(update, context, address_data)
    else:
        await query.edit_message_text(get_text("address_already_exists", lang))
    if user_data is not None:
        user_data["step"] = UserSteps.NONE.name

@typing_indicator_for_all
async def check_outages_for_new_address(update: Update, context: ContextTypes.DEFAULT_TYPE, address_data: dict):
    lang = get_user_lang(context)
    chat_id = safe_get(safe_get(update, 'effective_chat'), 'id')
    if chat_id is None:
        return
    await context.bot.send_message(chat_id, escape_markdown_v2(get_text("outage_check_on_add_title", lang)), parse_mode=ParseMode.MARKDOWN_V2)
    all_recent_outages = await db_manager.find_outages_for_address_text(address_data['full_address'])
    if not all_recent_outages:
        await context.bot.send_message(chat_id, escape_markdown_v2(get_text("outage_check_on_add_none_found", lang)), parse_mode=ParseMode.MARKDOWN_V2)
    else:
        response_text = escape_markdown_v2(get_text("outage_check_on_add_found", lang))
        for outage in all_recent_outages:
            response_text += f"\n\n- {escape_markdown_v2(str(outage['source_type']))}: {escape_markdown_v2(str(outage.get('start_datetime', 'N/A')))}"
        await context.bot.send_message(chat_id, response_text, parse_mode=ParseMode.MARKDOWN_V2)

    last_outage = await db_manager.get_last_outage_for_address(address_data['full_address'])
    if last_outage:
        await context.bot.send_message(chat_id, f"{get_text('last_outage_recorded', lang)} {last_outage['end_datetime'].strftime('%Y-%m-%d')}")
    else:
        await context.bot.send_message(chat_id, get_text("no_past_outages", lang))

@typing_indicator_for_all
async def qa_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = safe_get(update, 'callback_query')
    lang = get_user_lang(context)
    data = safe_get(query, 'data')
    user_data = getattr(context, 'user_data', None)
    if query is None or not data:
        return
    if data.startswith("faq_q_"):
        parts = data.split('_')
        q_idx = int(parts[2])
        page = int(parts[3])
        q_key = FAQ_QUESTION_KEYS[page * FAQ_PAGE_SIZE + q_idx]
        a_key = FAQ_ANSWER_KEYS[page * FAQ_PAGE_SIZE + q_idx]
        answer_text = get_text(a_key, lang)
        if not answer_text or answer_text.strip() == a_key:
            answer_text = get_text("faq_answer_not_found", lang) if "faq_answer_not_found" in translations else "Ответ не найден."
        buttons = [[InlineKeyboardButton(get_text("back_btn", lang), callback_data=f"faq_page_{page}")]]
        keyboard = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(answer_text, reply_markup=keyboard)
    elif data.startswith("faq_page_"):
        page = int(data.split('_')[2])
        await send_faq_page(query, context, page, lang)
    elif data.startswith("faq_prev_"):
        page = int(data.split('_')[2]) - 1
        if user_data is not None:
            user_data['faq_page'] = page
        await send_faq_page(query, context, page, lang)
    elif data.startswith("faq_next_"):
        page = int(data.split('_')[2]) + 1
        if user_data is not None:
            user_data['faq_page'] = page
        await send_faq_page(query, context, page, lang)
    elif data == "qa_support":
        safe_set_user_data(user_data, "step", UserSteps.AWAITING_SUPPORT_MESSAGE.name)
        await query.edit_message_text(get_text("support_prompt", lang))
    elif data == "qa_back":
        page = user_data.get('faq_page', 0) if user_data else 0
        await send_faq_page(query, context, page, lang)
    else:
        await query.answer(get_text("unknown_command", lang), show_alert=True)

# --- Helper for /language command ---
@typing_indicator_for_all
async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда для смены языка. Показывает пользователю выбор языков и обновляет меню команд.
    """
    message = getattr(update, 'message', None)
    user = getattr(update, 'effective_user', None)
    user_id = getattr(user, 'id', None)
    application = getattr(context, 'application', None)
    lang = get_user_lang(context)
    if application and user_id is not None:
        await update_user_commands_menu(application, lang, user_id)
    if message is None:
        return
    user_data = getattr(context, 'user_data', None)
    safe_set_user_data(user_data, "step", UserSteps.AWAITING_INITIAL_LANG.name)
    prompt = get_text("change_language_prompt", lang)
    buttons = [
        [KeyboardButton("\U0001F1E6\U0001F1F2 Հայերեն")],
        [KeyboardButton("\U0001F1F7\U0001F1FA Русский")],
        [KeyboardButton("\U0001F1EC\U0001F1E7 English")]
    ]
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.reply_text(prompt, reply_markup=keyboard)

# --- Command & Callback Handlers ---
command_handlers = {
    "start": start_command, "myaddresses": my_addresses_command,
    "frequency": frequency_command, "stats": stats_command,
    "clearaddresses": clear_addresses_command, "qa": qa_command,
    "language": language_command
}

# --- Check address without adding ---
@typing_indicator_for_all
async def check_address_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    user_data = getattr(context, 'user_data', None)
    safe_set_user_data(user_data, "step", UserSteps.AWAITING_CHECK_REGION.name)
    regions = get_regions_list(lang)
    buttons = [[KeyboardButton(r)] for r in regions]
    buttons.append([KeyboardButton(get_text("cancel", lang))])
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    message = getattr(update, 'message', None)
    if message is not None:
        await message.reply_text(get_text("choose_region", lang), reply_markup=keyboard)

@typing_indicator_for_all
async def handle_check_region_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    user_data = getattr(context, 'user_data', None)
    message = getattr(update, 'message', None)
    text = getattr(message, 'text', None) if message else None
    regions = get_regions_list(lang)
    if text in regions:
        safe_set_user_data(user_data, "check_region", text)
        safe_set_user_data(user_data, "step", UserSteps.AWAITING_CHECK_ADDRESS_INPUT.name)
        if message:
            await message.reply_text(get_text("enter_street", lang, region=text), reply_markup=ReplyKeyboardRemove())
    elif text == get_text("cancel", lang):
        safe_set_user_data(user_data, "step", UserSteps.NONE.name)
        if message:
            await message.reply_text(get_text("action_cancelled", lang), reply_markup=get_main_menu_keyboard(lang))
    else:
        if message:
            await message.reply_text(get_text("choose_region", lang), reply_markup=ReplyKeyboardMarkup([[KeyboardButton(r)] for r in regions]+[[KeyboardButton(get_text("cancel", lang))]], resize_keyboard=True, one_time_keyboard=True))

@typing_indicator_for_all
async def handle_check_address_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    user_data = getattr(context, 'user_data', None)
    message = getattr(update, 'message', None)
    text = getattr(message, 'text', None) if message else None
    region = safe_get_user_data(user_data, "check_region", "")
    if not text:
        if message:
            await message.reply_text(get_text("error_generic", lang))
        return
    if message:
        await message.reply_text(get_text("address_verifying", lang))
    from api_clients import get_verified_address_from_yandex
    address_query = f"{region}, {text}" if region else text
    result = await get_verified_address_from_yandex(address_query, lang="ru_RU" if lang == "ru" else ("en_US" if lang == "en" else "hy_AM"))
    if result:
        from db_manager import find_outages_for_address_text
        outages = await find_outages_for_address_text(result['full_address'])
        if outages:
            outages_text = get_text('outage_check_on_add_found', lang)
            for outage in outages:
                outages_text += f"\n\n- {outage['source_type']}: {outage.get('start_datetime', 'N/A')}"

            if message:
                await message.reply_text(
                    f"{get_text('address_confirm_prompt', lang, address=result['full_address'])}\n\n{outages_text}",
                    reply_markup=get_main_menu_keyboard(lang)
                )
        else:
            if message:
                await message.reply_text(
                    f"{get_text('address_confirm_prompt', lang, address=result['full_address'])}\n\n{get_text('outage_check_on_add_none_found', lang)}",
                    reply_markup=get_main_menu_keyboard(lang)
                )
    else:
        if message:
            await message.reply_text(get_text("address_not_found_yandex", lang), reply_markup=get_main_menu_keyboard(lang))
    safe_set_user_data(user_data, "step", UserSteps.NONE.name)
    safe_set_user_data(user_data, "check_region", None)

# --- State Logic Handlers ---
@typing_indicator_for_all
async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    text = getattr(message, 'text', None)
    if not text:
        return

    if "Հայերեն" in text:
        lang = "hy"
    elif "Русский" in text:
        lang = "ru"
    elif "English" in text:
        lang = "en"
    else:
        lang = "en"

    user = update.effective_user
    if user is None:
        return
    user_id = user.id
    if context.user_data is not None:
        context.user_data["lang"] = lang
    await db_manager.update_user_language(user_id, lang)

    await update_user_commands_menu(context.application, lang, user_id)

    await message.reply_text(
        get_text("language_set_success", lang),
        reply_markup=get_main_menu_keyboard(lang)
    )
    if context.user_data is not None:
        context.user_data["step"] = UserSteps.NONE.name

@typing_indicator_for_all
async def handle_region_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = getattr(update, 'message', None)
    if message is None:
        return
    region = getattr(message, 'text', None)
    lang = get_user_lang(context)
    regions = get_regions_list(lang)
    if region == get_text("cancel", lang):
        safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.NONE.name)
        if hasattr(message, 'reply_text'):
            await message.reply_text(get_text("action_cancelled", lang), reply_markup=get_main_menu_keyboard(lang))
        return
    if region not in regions:
        if hasattr(message, 'reply_text'):
            await message.reply_text(get_text("unknown_command", lang))
        return
    safe_set_user_data(getattr(context, 'user_data', None), "selected_region", region)
    if hasattr(message, 'reply_text'):
        await message.reply_text(get_text("enter_street", lang, region=region), reply_markup=ReplyKeyboardRemove())
    safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.AWAITING_STREET.name)

@typing_indicator_for_all
async def handle_street_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = getattr(update, 'message', None)
    user_data = getattr(context, 'user_data', None)
    lang = get_user_lang(context)
    if message is None:
        return
    text = getattr(message, 'text', None)
    if not text or text == get_text("cancel", lang):
        safe_set_user_data(user_data, "step", UserSteps.NONE.name)
        if hasattr(message, 'reply_text'):
            await message.reply_text(get_text("action_cancelled", lang), reply_markup=get_main_menu_keyboard(lang))
        return
    cancel_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(get_text("cancel", lang))]],
        resize_keyboard=True, one_time_keyboard=True
    )
    typing_task = asyncio.create_task(send_typing_periodically(context, message.chat_id))
    try:
        region = None
        if user_data is not None and hasattr(user_data, 'get'):
            region = user_data.get("selected_region", "Armenia")
        full_query = f"{region}, {text}"
        await message.reply_text(get_text("address_verifying", lang), reply_markup=cancel_keyboard)
        verified_address = await api_clients.get_verified_address_from_yandex(full_query)
        if verified_address and verified_address.get('full_address'):
            if user_data is not None:
                user_data["verified_address_cache"] = verified_address
            buttons = [[
                InlineKeyboardButton(get_text("yes", lang), callback_data="confirm_address_yes"),
                InlineKeyboardButton(get_text("no_cancel_action_btn", lang), callback_data="cancel_action")
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

@typing_indicator_for_all
async def handle_frequency_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = getattr(update, 'message', None)
    user = getattr(update, 'effective_user', None)
    if message is None or user is None:
        return
    text = message.text
    lang = get_user_lang(context)
    user_id = getattr(user, 'id', None)
    selected_interval = None
    if text == get_text("cancel", lang):
        safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.NONE.name)
        await message.reply_text(get_text("action_cancelled", lang), reply_markup=get_main_menu_keyboard(lang))
        return
    for option in FREQUENCY_OPTIONS.values():
        if option[lang] == text:
            selected_interval = option['interval']
            break
    if selected_interval and user_id is not None:
        await db_manager.update_user_frequency(user_id, selected_interval)
        result = safe_call(message, 'reply_text', get_text("frequency_set_success", lang), reply_markup=get_main_menu_keyboard(lang))
        if result is not None and inspect.isawaitable(result):
            await result
        safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.NONE.name)
    else:
        result = safe_call(message, 'reply_text', get_text("unknown_command", lang))
        if inspect.isawaitable(result):
            await result

@typing_indicator_for_all
async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getattr(update, 'effective_user', None)
    message = getattr(update, 'message', None)
    support_lang = None
    support_user = None
    if SUPPORT_CHAT_ID:
        try:
            support_user_id = int(SUPPORT_CHAT_ID)
            support_user = await db_manager.get_user(support_user_id)
        except Exception:
            support_user = None
    if support_user and 'language_code' in support_user and support_user['language_code']:
        support_lang = support_user['language_code']
    elif SUPPORT_CHAT_ID and hasattr(context.bot, 'get_chat'):
        try:
            chat = await context.bot.get_chat(SUPPORT_CHAT_ID)
            support_lang = getattr(chat, 'language_code', None)
        except Exception:
            support_lang = None
    if support_lang not in ['hy', 'ru', 'en']:
        support_lang = 'en'
    if not support_lang:
        support_lang = 'en'
    # ...
    if not SUPPORT_CHAT_ID or user is None or message is None:
        return
    user_mention = getattr(user, 'mention_markdown_v2', lambda: str(getattr(user, 'id', 'user')))()
    user_username = getattr(user, 'username', None)
    if user_username:
        user_username = f"@{user_username}"
    else:
        user_username = "None"
    support_message = get_text(
        "support_message_from_user", support_lang,
        user_mention=user_mention,
        user_username=user_username,
        user_id=getattr(user, 'id', None),
        message=message.text
    )
    delivered = False
    try:
        await context.bot.send_message(chat_id=SUPPORT_CHAT_ID, text=escape_markdown_v2(support_message), parse_mode=ParseMode.MARKDOWN_V2)
        delivered = True
    except Exception as e:
        log.error(f"Не удалось доставить сообщение админу: {e}")
        delivered = False
    lang = get_user_lang(context)
    if message is not None:
        if delivered:
            await message.reply_text(get_text("support_message_sent", lang), reply_markup=get_main_menu_keyboard(lang))
        else:
            await message.reply_text(get_text("support_message_failed", lang) if "support_message_failed" in translations else "❌ Не удалось доставить сообщение админу.", reply_markup=get_main_menu_keyboard(lang))
    safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.NONE.name)

# --- Callback Query Handlers ---
@typing_indicator_for_all
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
    elif data == "cancel_action":
        await cancel_callback(update, context)
    return

@typing_indicator_for_all
async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    query = getattr(update, 'callback_query', None)
    if query is not None and hasattr(query, 'edit_message_text'):
        await query.edit_message_text(get_text("action_cancelled", lang), reply_markup=get_main_menu_keyboard(lang))
    else:
        message = getattr(update, 'message', None)
        if message is not None and hasattr(message, 'reply_text'):
            await message.reply_text(get_text("action_cancelled", lang), reply_markup=get_main_menu_keyboard(lang))

# --- Periodic Jobs ---
async def periodic_site_check_job(context: ContextTypes.DEFAULT_TYPE):
    log.info("Starting periodic site check job...")
    coros = [
        parse_all_water_announcements_async(),
        parse_all_gas_announcements_async(),
        parse_all_electric_announcements_async()
    ]
    await asyncio.gather(*(c for c in coros if c is not None))
    log.info("Periodic site check job finished.")

# --- Application Setup ---
async def set_bot_commands(application: Application, lang: str, user_id: Optional[int] = None):
    """Устанавливает команды бота с описаниями на нужном языке для конкретного пользователя (если user_id указан)."""
    commands = [
        BotCommand("start", get_text("cmd_start", lang)),
        BotCommand("myaddresses", get_text("cmd_myaddresses", lang)),
        BotCommand("clearaddresses", get_text("cmd_clearaddresses", lang)),
        BotCommand("frequency", get_text("cmd_frequency", lang)),
        BotCommand("qa", get_text("cmd_qa", lang)),
        BotCommand("language", get_text("cmd_language", lang)),
    ]
    if user_id is not None:
        await application.bot.set_my_commands(commands, language_code=lang, scope={"type": "chat", "chat_id": int(user_id)})
    else:
        await application.bot.set_my_commands(commands, language_code=lang)

async def update_user_commands_menu(application: Application, lang: str, user_id: int):
    """
    Обновляет меню команд Telegram только для одного пользователя на выбранном языке.
    """
    commands = [
        BotCommand("start", get_text("cmd_start", lang)),
        BotCommand("myaddresses", get_text("cmd_myaddresses", lang)),
        BotCommand("language", get_text("cmd_language", lang)),
        BotCommand("clearaddresses", get_text("cmd_clearaddresses", lang)),
        BotCommand("frequency", get_text("cmd_frequency", lang)),
        BotCommand("qa", get_text("cmd_qa", lang)),
    ]
    await application.bot.set_my_commands(
        commands=commands,
        language_code=lang,
        scope=BotCommandScopeChat(chat_id=user_id)
    )

async def post_init(application: Application):
    await db_manager.init_db_pool()
    ai_engine.load_models()
    for lang_code in ["en", "ru", "hy"]:
        await set_bot_commands(application, lang_code)
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
        "language": language_command
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

@typing_indicator_for_all
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    message = getattr(update, 'message', None)
    user_data = getattr(context, 'user_data', None)
    text = getattr(message, 'text', None) if message else None

    step = safe_get_user_data(user_data, "step", UserSteps.NONE.name)
    if step == UserSteps.AWAITING_INITIAL_LANG.name:
        await handle_language_selection(update, context)
        return
    elif step == UserSteps.AWAITING_REGION.name:
        await handle_region_selection(update, context)
        return
    elif step == UserSteps.AWAITING_STREET.name:
        await handle_street_input(update, context)
        return
    elif step == UserSteps.AWAITING_FREQUENCY.name:
        await handle_frequency_selection(update, context)
        return
    elif step == UserSteps.AWAITING_SUPPORT_MESSAGE.name:
        await handle_support_message(update, context)
        return
    elif step == UserSteps.AWAITING_CHECK_REGION.name:
        await handle_check_region_selection(update, context)
        return
    elif step == UserSteps.AWAITING_CHECK_ADDRESS_INPUT.name:
        await handle_check_address_input(update, context)
        return

    if text == get_text("add_address_btn", lang):
        await add_address_command(update, context)
    elif text == get_text("remove_address_btn", lang):
        await remove_address_command(update, context)
    elif text == get_text("my_addresses_btn", lang):
        await my_addresses_command(update, context)
    elif text == get_text("frequency_btn", lang):
        await frequency_command(update, context)
    elif text == get_text("qa_btn", lang):
        await qa_command(update, context)
    elif text == get_text("clear_addresses_btn", lang):
        await clear_addresses_command(update, context)
    elif text == get_text("check_address_btn", lang):
        await check_address_command(update, context)
    elif text == get_text("cancel", lang):
        safe_set_user_data(user_data, "step", UserSteps.NONE.name)
        if message is not None:
            await message.reply_text(get_text("action_cancelled", lang), reply_markup=get_main_menu_keyboard(lang))
    else:
        if message is not None:
            await message.reply_text(get_text("unknown_command", lang))

# TODO: /clearaddres (1), /addaddress (1) and /checkaddress commands

@typing_indicator_for_all
async def clear_addresses_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    query = getattr(update, 'callback_query', None)
    user_data = getattr(context, 'user_data', None)
    user = getattr(query, 'from_user', None) if query else None
    user_id = getattr(user, 'id', None) if user else None
    if query is not None and hasattr(query, 'data'):
        if query.data == "confirm_clear_yes" and user_id is not None:
            count = await db_manager.clear_all_user_addresses(user_id)
            if user_data is not None:
                user_data["step"] = UserSteps.NONE.name
            await query.edit_message_text(get_text("all_addresses_cleared", lang), reply_markup=get_main_menu_keyboard(lang))
        elif query.data == "cancel_action":
            if user_data is not None:
                user_data["step"] = UserSteps.NONE.name
            await query.edit_message_text(get_text("action_cancelled", lang), reply_markup=get_main_menu_keyboard(lang))

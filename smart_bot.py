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

ADMIN_IDS = [int(i) for i in os.getenv("ADMIN_USER_IDS", "").split(',') if i]
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID")
TIER_ORDER = ["Free", "Basic", "Premium", "Ultra"]
REGIONS_LISTS = {
    "hy": [
        "Երևան", "Արագածոտն", "Արարատ", "Արմավիր", "Գեղարքունիք", "Լոռի", "Կոտայք", "Շիրակ", "Սյունիք", "Վայոց Ձոր", "Տավուշ"
    ],
    "ru": [
        "Ереван", "Арагацотн", "Арарат", "Армавир", "Гегаркуник", "Лори", "Котайк", "Ширак", "Сюник", "Вайоц Дзор", "Тавуш"
    ],
    "en": [
        "Yerevan", "Aragatsotn", "Ararat", "Armavir", "Gegharkunik", "Lori", "Kotayk", "Shirak", "Syunik", "Vayots Dzor", "Tavush"
    ]
}

def get_regions_list(lang: str) -> list:
    return REGIONS_LISTS.get(lang, REGIONS_LISTS["en"])

FREQUENCY_OPTIONS = {
    "Free_6h": {"interval": 21600, "hy": "⏱ 6 ժամ", "ru": "⏱ 6 часов", "en": "⏱ 6 hours", "tier": "Free"},
    "Free_12h": {"interval": 43200, "hy": "⏱ 12 ժամ", "ru": "⏱ 12 часов", "en": "⏱ 12 hours", "tier": "Free"},
    "Basic_1h": {"interval": 3600, "hy": "⏱ 1 ժամ", "ru": "⏱ 1 час", "en": "⏱ 1 hour", "tier": "Basic"},
    "Premium_30m": {"interval": 1800, "hy": "⏱ 30 րոպե", "ru": "⏱ 30 минут", "en": "⏱ 30 min", "tier": "Premium"},
    "Ultra_15m": {"interval": 900, "hy": "⏱ 15 րոպե", "ru": "⏱ 15 минут", "en": "⏱ 15 min", "tier": "Ultra"},
}

# --- Новый массив ключей для FAQ ---
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
        [KeyboardButton(get_text("frequency_btn", lang)), KeyboardButton(get_text("qa_btn", lang))],  # Удалена кнопка статистики
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
    application = getattr(context, 'application', None)
    # Получаем nick и name
    user_nick = getattr(user, 'username', 'none') or 'none'
    user_name = (getattr(user, 'first_name', '') or '') + (' ' + getattr(user, 'last_name', '') if getattr(user, 'last_name', '') else '')
    user_name = user_name.strip()
    if not user_in_db:
        safe_set_user_data(user_data, "step", UserSteps.AWAITING_INITIAL_LANG.name)
        user_lang_code = safe_get(user, 'language_code')
        if user_lang_code not in ['ru', 'en', 'hy']:
            user_lang_code = 'en'
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
        await db_manager.create_or_update_user(user_id, user_lang_code, user_nick, user_name)
        safe_set_user_data(user_data, "lang", user_lang_code)
    else:
        lang = user_in_db['language_code'] if user_in_db and 'language_code' in user_in_db else 'en'
        if lang not in ['ru', 'en', 'hy']:
            lang = 'en'
        safe_set_user_data(user_data, "lang", lang)
        safe_set_user_data(user_data, "step", UserSteps.NONE.name)
        if application:
            await set_bot_commands(application, lang, user_id=user_id)
        result = safe_call(message, 'reply_text', get_text("menu_message", lang), reply_markup=get_main_menu_keyboard(lang))
        if inspect.isawaitable(result):
            await result
    # Всегда обновляем nick и name при старте
    await db_manager.create_or_update_user(user_id, safe_get(user, 'language_code', 'en'), user_nick, user_name)

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

async def qa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    page = 0
    user_data = getattr(context, 'user_data', None)
    if user_data is not None:
        user_data['faq_page'] = page
    await send_faq_page(update, context, page, lang)

async def send_faq_page(update_or_query, context, page, lang):
    start = page * FAQ_PAGE_SIZE
    end = start + FAQ_PAGE_SIZE
    question_keys = FAQ_QUESTION_KEYS[start:end]
    buttons = [[InlineKeyboardButton(get_text(qk, lang), callback_data=f"faq_q_{i+1}_{page}")]
               for i, qk in enumerate(question_keys, start=start)]
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⏮ Назад", callback_data=f"faq_prev_{page}"))
    if end < len(FAQ_QUESTION_KEYS):
        nav_buttons.append(InlineKeyboardButton("⏭ Вперёд", callback_data=f"faq_next_{page}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(get_text("support_btn", lang), callback_data="qa_support")])
    keyboard = InlineKeyboardMarkup(buttons)
    text = get_text("qa_title", lang)
    if hasattr(update_or_query, 'message') and update_or_query.message is not None:
        await update_or_query.message.reply_text(text, reply_markup=keyboard)
    elif hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(text, reply_markup=keyboard)

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
    coros = [
        parse_all_water_announcements_async(),
        parse_all_gas_announcements_async(),
        parse_all_electric_announcements_async()
    ]
    await asyncio.gather(*(c for c in coros if c is not None))
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
    user_data = getattr(context, 'user_data', None)
    if query is None or not data:
        return
    if data.startswith("faq_q_"):
        # faq_q_{num}_{page}
        parts = data.split('_')
        q_num = int(parts[2])
        page = int(parts[3])
        answer_key = f"qa_a{q_num}"
        answer_text = get_text(answer_key, lang)
        buttons = [[InlineKeyboardButton(get_text("back_btn", lang), callback_data=f"faq_page_{page}")]]
        keyboard = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(answer_text, reply_markup=keyboard)
    elif data.startswith("faq_page_"):
        # faq_page_{page}
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
async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда для смены языка. Показывает пользователю выбор языков.
    """
    message = getattr(update, 'message', None)
    if message is None:
        return
    user_data = getattr(context, 'user_data', None)
    safe_set_user_data(user_data, "step", UserSteps.AWAITING_INITIAL_LANG.name)
    prompt = get_text("change_language_prompt", get_user_lang(context))
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
    "language": language_command  # Новая команда для смены языка
}

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
    elif text and 'English' in text:
        lang_code = 'en'
    user_data = getattr(context, 'user_data', None)
    if user_data is not None:
        user_data["lang"] = lang_code
    user = getattr(update, 'effective_user', None)
    user_id = getattr(user, 'id', None)
    if user_id is not None:
        await db_manager.update_user_language(user_id, lang_code)
    application = getattr(context, 'application', None)
    if application and user_id:
        await set_bot_commands(application, lang_code, user_id=user_id)
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
    lang = get_user_lang(context)
    regions = get_regions_list(lang)
    if region not in regions:
        if hasattr(message, 'reply_text'):
            await message.reply_text(get_text("unknown_command", lang))
        return
    safe_set_user_data(getattr(context, 'user_data', None), "selected_region", region)
    if hasattr(message, 'reply_text'):
        await message.reply_text(get_text("enter_street", lang, region=region), reply_markup=ReplyKeyboardRemove())
    safe_set_user_data(getattr(context, 'user_data', None), "step", UserSteps.AWAITING_STREET.name)

# Безопасная работа с context.user_data и .get/.pop
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
    # Показываем клавиатуру с кнопкой "Отмена" при вводе адреса
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
    # Определяем язык поддержки
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
    await context.bot.send_message(chat_id=SUPPORT_CHAT_ID, text=support_message, parse_mode=ParseMode.MARKDOWN_V2)
    lang = get_user_lang(context)
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
    if re.fullmatch(r'\d{4}', text):
        return f"{text[:2]}:{text[2:]}"
    m = re.match(r'^(\d{1,2}):(\d{1,2})$', text)
    if m:
        h, m_ = m.groups()
        return f"{int(h):02d}:{int(m_):02d}"
    if re.fullmatch(r'\d{1,2}', text):
        return f"{int(text):02d}:00"
    return None

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
    elif data == "cancel_action":
        await cancel_callback(update, context)
    return

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
        BotCommand("stats", get_text("cmd_stats", lang)),
        BotCommand("language", get_text("cmd_language", lang)),
    ]
    if user_id is not None:
        await application.bot.set_my_commands(commands, language_code=lang, scope={"type": "chat", "chat_id": int(user_id)})
    else:
        await application.bot.set_my_commands(commands, language_code=lang)

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


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    message = getattr(update, 'message', None)
    user = getattr(update, 'effective_user', None)
    if user is not None:
        user_id = getattr(user, 'id', None)
        user_nick = getattr(user, 'username', 'none') or 'none'
        user_name = (getattr(user, 'first_name', '') or '') + (' ' + getattr(user, 'last_name', '') if getattr(user, 'last_name', '') else '')
        user_name = user_name.strip()
        user_lang_code = getattr(user, 'language_code', 'en')
        if user_id is not None:
            await db_manager.create_or_update_user(user_id, user_lang_code, user_nick, user_name)
    if message is not None:
        await message.reply_text(get_text("unknown_command", lang))

# Вставляем заглушку clear_addresses_callback, если она отсутствует
async def clear_addresses_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    query = getattr(update, 'callback_query', None)
    if query is not None and hasattr(query, 'edit_message_text'):
        await query.edit_message_text(get_text("action_cancelled", lang), reply_markup=get_main_menu_keyboard(lang))

if __name__ == "__main__":
    main()
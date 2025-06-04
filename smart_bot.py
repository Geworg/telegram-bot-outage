import os
import json
import re
import asyncio
import shutil
import sys
from datetime import datetime, time as dt_time, timedelta
from dataclasses import dataclass, field
from time import time as timestamp
from typing import Dict, List, Optional, Set, Any, Tuple, Callable
from collections import defaultdict, namedtuple
from difflib import SequenceMatcher, get_close_matches
from enum import Enum, auto
import urllib.parse
import hashlib

from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, ContextTypes, CommandHandler, MessageHandler, filters, BasePersistence, PicklePersistence, JobQueue
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter, TimedOut, NetworkError

from logger import log_info, log_error, log_warning
from translations import translations
from parse_water import parse_all_water_announcements_async
from parse_gas import parse_all_gas_announcements_async
from parse_electric import parse_all_electric_announcements_async
from ai_engine import clarify_address_ai, is_ai_available, MODEL_PATH as AI_MODEL_PATH

import aiofiles
import aiofiles.os as aios
from pathlib import Path

# if os.getenv("MAINTENANCE_MODE", "false").lower() == "true":
#     print("🚧 Приложение в режиме обслуживания. Остановка.")
#     sys.exit(1)


# --- КОНСТАНТЫ ---
class UserSteps(Enum):
    NONE = auto()
    AWAITING_LANGUAGE_CHOICE = auto()
    AWAITING_REGION = auto()
    AWAITING_STREET = auto()
    AWAITING_STREET_CONFIRMATION = auto()
    AWAITING_ADDRESS_TO_REMOVE = auto()
    AWAITING_CLEAR_ALL_CONFIRMATION = auto()
    AWAITING_REGION_FOR_CHECK = auto()
    AWAITING_STREET_FOR_CHECK = auto()
    AWAITING_FREQUENCY_CHOICE = auto()
    AWAITING_SUBSCRIPTION_CHOICE = auto()
    AWAITING_SUPPORT_MESSAGE = auto()
    AWAITING_FAQ_CHOICE = auto()
    AWAITING_SILENT_START_TIME = auto()
    AWAITING_SILENT_END_TIME = auto()

USER_DATA_LANG = "current_language"
USER_DATA_STEP = "current_step"
USER_DATA_SELECTED_REGION = "selected_region_for_add"
USER_DATA_SELECTED_REGION_FOR_CHECK = "selected_region_for_check"
USER_DATA_RAW_STREET_INPUT = "raw_street_input"
USER_DATA_CLARIFIED_ADDRESS_CACHE = "clarified_address_cache"
USER_DATA_TEMP_SOUND_SETTINGS = "temp_sound_settings"

CALLBACK_PREFIX_LANG = "lang_select:"
CALLBACK_PREFIX_SUBSCRIBE = "subscribe:"
CALLBACK_PREFIX_ADDRESS_CONFIRM = "addr_confirm:"
CALLBACK_PREFIX_HELP = "help_action:"
CALLBACK_PREFIX_FAQ_ITEM = "faq_item:"
CALLBACK_PREFIX_SOUND = "sound_set:"

FREQUENCY_OPTIONS = {
    "Free_6h":    {"interval": 21600, "hy": "⏱ 6 ժամ",  "ru": "⏱ 6 часов",  "en": "⏱ 6 hours",  "tier": "Free"},
    "Free_12h":   {"interval": 43200, "hy": "⏱ 12 ժամ", "ru": "⏱ 12 часов","en": "⏱ 12 hours", "tier": "Free"},
    "Free_24h":   {"interval": 86400, "hy": "⏱ 24 ժամ", "ru": "⏱ 24 часа", "en": "⏱ 24 hours", "tier": "Free"},
    "Basic_1h":   {"interval": 3600,  "hy": "⏱ 1 ժամ",  "ru": "⏱ 1 час",   "en": "⏱ 1 hour",   "tier": "Basic"},
    "Premium_30m":{"interval": 1800,  "hy": "⏱ 30 րոպե","ru": "⏱ 30 минут","en": "⏱ 30 min", "tier": "Premium"},
    "Ultra_15m":  {"interval": 900,   "hy": "⏱ 15 րոպե","ru": "⏱ 15 минут","en": "⏱ 15 min", "tier": "Ultra"},
}
TIER_ORDER = ["Free", "Basic", "Premium", "Ultra"]
paid_levels = {"Basic", "Premium", "Ultra"}
premium_tiers = {
    option_name: {
        "interval": option_data["interval"],
        "label": {  # Можно сразу собрать метки на трех языках
            "hy": option_data["hy"],
            "ru": option_data["ru"],
            "en": option_data["en"],
        },
        "tier": option_data["tier"],
        # Если позже понадобится цена — можно добавить сюда поле "price_cents" или "price_dram"
    }
    for option_name, option_data in FREQUENCY_OPTIONS.items()
    if option_data["tier"] in paid_levels
}

# --- КОНФИГУРАЦИЯ ---
@dataclass
class BotConfig:
    telegram_token: str
    admin_user_ids_str: str
    settings_file: Path = Path("user_settings.json")
    address_file: Path = Path("addresses.json")
    notified_file: Path = Path("notified.json")
    bot_status_file: Path = Path("bot_general_status.json")
    backup_dir: Path = Path("backups")
    log_level: str = "INFO"
    default_user_timezone: str = "Asia/Yerevan"
    support_chat_id_str: Optional[str] = None
    max_requests_per_minute: int = 30 # Added from previous context
    max_backups_to_keep: int = 5 # Added from previous context

    admin_user_ids: List[int] = field(init=False, default_factory=list)
    support_chat_id: Optional[int] = field(init=False, default=None)

    def __post_init__(self):
        if self.admin_user_ids_str:
            try:
                self.admin_user_ids = [int(uid.strip()) for uid in self.admin_user_ids_str.split(',') if uid.strip().isdigit()]
            except ValueError: log_error(f"Ошибка ADMIN_USER_IDS: '{self.admin_user_ids_str}'.")
        if not self.admin_user_ids: log_warning("ADMIN_USER_IDS не установлен.")
        else: log_info(f"Администраторы: {self.admin_user_ids}")

        if self.support_chat_id_str and self.support_chat_id_str.strip().lstrip('-').isdigit():
            self.support_chat_id = int(self.support_chat_id_str.strip())
            log_info(f"ID чата поддержки: {self.support_chat_id}")
        elif self.support_chat_id_str: log_warning(f"SUPPORT_CHAT_ID ('{self.support_chat_id_str}') неверный.")

    @classmethod
    def from_env(cls) -> 'BotConfig':
        load_dotenv()
        backup_path = Path(os.getenv("BACKUP_DIR", "backups"))
        backup_path.mkdir(parents=True, exist_ok=True)
        return cls(
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            admin_user_ids_str=os.getenv("ADMIN_USER_IDS", ""),
            settings_file=Path(os.getenv("SETTINGS_FILE", "user_settings.json")),
            address_file=Path(os.getenv("ADDRESS_FILE", "addresses.json")),
            notified_file=Path(os.getenv("NOTIFIED_FILE", "notified.json")),
            bot_status_file=Path(os.getenv("BOT_STATUS_FILE", "bot_general_status.json")),
            backup_dir=backup_path,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            default_user_timezone=os.getenv("DEFAULT_USER_TIMEZONE", "Asia/Yerevan"),
            support_chat_id_str=os.getenv("SUPPORT_CHAT_ID"),
            max_requests_per_minute=int(os.getenv("MAX_REQUESTS_PER_MINUTE", "30")),
            max_backups_to_keep=int(os.getenv("MAX_BACKUPS_TO_KEEP", "5"))
        )

    def validate(self) -> bool:
        if not self.telegram_token: raise ValueError("Необходим TELEGRAM_BOT_TOKEN")
        return True

config = BotConfig.from_env() # config is now global
config.validate()

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ И ССЫЛКИ НА BOT_DATA ---
# These will be initialized/populated in post_init_hook by linking to bot_data
# This helps in making them accessible globally while being managed by PTB's bot_data persistence (for some aspects)
# For direct manipulation and custom saving, we'll access them via context.application.bot_data['..._ref']

# To avoid confusion, these are primarily for type hinting or conceptual understanding.
# Actual data lives in context.application.bot_data after initialization.
_user_settings_type = Dict[str, Dict[str, Any]]
_user_addresses_type = Dict[int, List[Dict[str, str]]]
_user_notified_headers_type = Dict[int, Set[str]]
_bot_general_status_type = Dict[str, Any]

# Runtime data not persisted by PicklePersistence directly through these global vars
last_check_time: Dict[int, float] = {}
user_request_counts: Dict[int, List[float]] = defaultdict(list)
bot_start_time = timestamp()

# Locks
settings_file_lock = asyncio.Lock()
address_file_lock = asyncio.Lock()
notified_file_lock = asyncio.Lock()
bot_status_file_lock = asyncio.Lock()

# Named tuple for easier access to bot_data components in handlers
BotDataAccessor = namedtuple("BotDataAccessor", [
    "translations", "user_settings", "user_addresses", "user_notified",
    "config", "bot_status", "premium_tiers", "frequency_options", "all_known_regions"
])

def get_bot_data(context: ContextTypes.DEFAULT_TYPE) -> BotDataAccessor:
    bd = context.application.bot_data
    return BotDataAccessor(
        translations=bd.get("translations_ref", {}),
        user_settings=bd.get("user_settings_ref", {}),
        user_addresses=bd.get("user_addresses_ref", {}),
        user_notified=bd.get("user_notified_headers_ref", {}),
        config=bd.get("config_ref", config), # Fallback to global config if not in bot_data yet
        bot_status=bd.get("bot_general_status_ref", {}),
        premium_tiers=bd.get("premium_tiers_ref", {}),
        frequency_options=bd.get("frequency_options_ref", {}),
        all_known_regions=bd.get("all_known_regions_flat_ref", set())
    )

# --- ЯЗЫКИ И КЛАВИАТУРЫ ---
languages = {"Հայերեն": "hy", "Русский": "ru", "English": "en"}
regions_hy = ["Երևան", "Արագածոտն", "Արարատ", "Արմավիր", "Գեղարքունիք", "Լոռի", "Կոտայք", "Շիրակ", "Սյունիք", "Վայոց ձոր", "Տավուշ"]
regions_ru = ["Ереван", "Арагацотн", "Арарат", "Армавир", "Вайоц Дзор", "Гехаркуник", "Котайк", "Лори", "Сюник", "Тавуш", "Ширак"]
regions_en = ["Yerevan", "Aragatsotn", "Ararat", "Armavir", "Gegharkunik", "Kotayk", "Lori", "Shirak", "Syunik", "Tavush", "Vayots Dzor"]
# all_known_regions_flat is initialized in post_init_hook and put into bot_data

def get_language_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(lang_name, callback_data=f"{CALLBACK_PREFIX_LANG}{code}")]
         for lang_name, code in languages.items()]
    )

def get_region_keyboard(lang: str, context: ContextTypes.DEFAULT_TYPE) -> ReplyKeyboardMarkup:
    handler_data = get_bot_data(context)
    regions_map = {"hy": regions_hy, "ru": regions_ru, "en": regions_en}
    current_regions = regions_map.get(lang, regions_ru)
    keyboard = [[KeyboardButton(region)] for region in current_regions]
    keyboard.append([KeyboardButton(handler_data.translations.get("cancel", {}).get(lang, "Cancel"))])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_main_menu_buttons(lang: str, context: ContextTypes.DEFAULT_TYPE) -> List[List[KeyboardButton]]:
    handler_data = get_bot_data(context)
    translations = handler_data.translations

    log_info(f"[MainMenuButtons] Generating for lang: '{lang}'")

    # Примеры текстов кнопок с логированием
    add_addr_text = translations.get("add_address_btn", {}).get(lang, "➕ Add Address")
    log_info(f"[MainMenuButtons] 'add_address_btn' for lang '{lang}': '{add_addr_text}'")

    remove_addr_text = translations.get("remove_address_btn", {}).get(lang, "➖ Remove Address")
    log_info(f"[MainMenuButtons] 'remove_address_btn' for lang '{lang}': '{remove_addr_text}'")

    show_addresses_text = translations.get("show_addresses_btn", {}).get(lang, "📋 Show Addresses")
    log_info(f"[MainMenuButtons] 'show_addresses_btn' for lang '{lang}': '{show_addresses_text}'")

    clear_all_text = translations.get("clear_all_btn", {}).get(lang, "🧹 Clear All")
    log_info(f"[MainMenuButtons] 'clear_all_btn' for lang '{lang}': '{clear_all_text}'")

    check_address_text = translations.get("check_address_btn", {}).get(lang, "🔍 Check Address")
    log_info(f"[MainMenuButtons] 'check_address_btn' for lang '{lang}': '{check_address_text}'")

    sound_settings_text = translations.get("sound_settings_btn", {}).get(lang, "🎵 Sound Settings")
    log_info(f"[MainMenuButtons] 'sound_settings_btn' for lang '{lang}': '{sound_settings_text}'")

    subscription_text = translations.get("subscription_btn", {}).get(lang, "⭐ Subscription")
    log_info(f"[MainMenuButtons] 'subscription_btn' for lang '{lang}': '{subscription_text}'")

    statistics_text = translations.get("statistics_btn", {}).get(lang, "📊 Statistics")
    log_info(f"[MainMenuButtons] 'statistics_btn' for lang '{lang}': '{statistics_text}'")

    set_frequency_text = translations.get("set_frequency_btn", {}).get(lang, "⏱️ Set Frequency")
    log_info(f"[MainMenuButtons] 'set_frequency_btn' for lang '{lang}': '{set_frequency_text}'")

    help_text = translations.get("help_btn", {}).get(lang, "❓ Help")
    log_info(f"[MainMenuButtons] 'help_btn' for lang '{lang}': '{help_text}'")

    return [
        [KeyboardButton(add_addr_text), KeyboardButton(remove_addr_text)],
        [KeyboardButton(show_addresses_text), KeyboardButton(clear_all_text)],
        [KeyboardButton(check_address_text), KeyboardButton(sound_settings_text)],
        [KeyboardButton(subscription_text), KeyboardButton(statistics_text)],
        [KeyboardButton(set_frequency_text), KeyboardButton(help_text)]
    ]

def reply_markup_for_lang(lang: str, context: ContextTypes.DEFAULT_TYPE) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(get_main_menu_buttons(lang, context), resize_keyboard=True)

# premium_tiers is now accessed via get_bot_data(context).premium_tiers

def get_subscription_keyboard(lang: str, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    handler_data = get_bot_data(context)
    buttons = []
    for tier_key, tier_info in handler_data.premium_tiers.items(): # Use from bot_data
        price_str = (f"({tier_info['price_amd']} {handler_data.translations.get('amd_short', {}).get(lang, 'AMD')}/"
                     f"{handler_data.translations.get('month_short', {}).get(lang, 'mo')})"
                     if tier_info['price_amd'] > 0 else f"({handler_data.translations.get('free', {}).get(lang, 'Free')})")
        label = f"{handler_data.translations.get(f'tier_{tier_key.lower()}', {}).get(lang, tier_key)} {price_str}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"{CALLBACK_PREFIX_SUBSCRIBE}{tier_key}")])
    return InlineKeyboardMarkup(buttons)


# --- ДЕКОРАТОРЫ И ХЕЛПЕРЫ ---
def handler_prechecks(func: Callable):
    """Декоратор для проверки режима обслуживания, лимита запросов и установки языка в context.user_data."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user: return

        handler_data = get_bot_data(context)
        user_id_str = str(user.id)

        # 1. Проверка режима обслуживания
        if handler_data.bot_status.get("is_maintenance") and user.id not in handler_data.config.admin_user_ids:
            lang_for_maintenance = context.user_data.get(USER_DATA_LANG) or handler_data.user_settings.get(user_id_str, {}).get("lang", "ru")
            maintenance_msg = handler_data.bot_status.get("maintenance_message") or \
                              handler_data.translations.get("bot_under_maintenance_user_notification", {}).get(lang_for_maintenance, "Bot is under maintenance.")
            if update.message: await update.message.reply_text(maintenance_msg)
            elif update.callback_query: await update.callback_query.message.reply_text(maintenance_msg) # Or answer callback
            return

        # 2. Проверка лимита запросов
        if is_user_rate_limited(user.id, context): # is_user_rate_limited сама использует context для config
            # Можно добавить сообщение пользователю о превышении лимита
            return

        # ... (maintenance and rate limit checks) ...
        current_context_lang = context.user_data.get(USER_DATA_LANG)
        lang_from_settings = handler_data.user_settings.get(user_id_str, {}).get("lang")
        log_info(f"[Prechecks] User: {user_id_str}. Context lang: {current_context_lang}. Settings lang: {lang_from_settings}.")

        if USER_DATA_LANG not in context.user_data: # Only set from settings if not already in context (e.g., from a previous handler in same update)
            if lang_from_settings:
                context.user_data[USER_DATA_LANG] = lang_from_settings
                log_info(f"[Prechecks] User: {user_id_str}. Set context lang from settings to: {lang_from_settings}.")
            # else:
                # log_info(f"[Prechecks] User: {user_id_str}. No lang in settings or context. start_command will prompt or default will be used.")
        # ...
        return await func(update, context, *args, **kwargs)
    return wrapper

def get_lang_for_handler(context: ContextTypes.DEFAULT_TYPE, user_id: Optional[int] = None) -> str:
    """Получает язык пользователя, приоритет: context.user_data, затем user_settings, затем 'ru'."""
    if USER_DATA_LANG in context.user_data:
        return context.user_data[USER_DATA_LANG]
    
    if user_id: # Если user_id передан (например, для сообщений от имени бота)
        user_settings_data = get_bot_data(context).user_settings
        lang = user_settings_data.get(str(user_id), {}).get("lang", "ru")
        context.user_data[USER_DATA_LANG] = lang # Кешируем для текущей обработки, если user_id совпадает с effective_user
        return lang
    return "ru" # Общий fallback

async def reply_with_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text_key: str, default_text: str = "Menu."):
    lang = get_lang_for_handler(context, update.effective_user.id if update.effective_user else None)
    handler_data = get_bot_data(context)
    message_text = handler_data.translations.get(text_key, {}).get(lang, default_text)
    
    target_chat_id = update.effective_chat.id if update.effective_chat else None
    if not target_chat_id:
        log_error("reply_with_main_menu: Could not determine target_chat_id.")
        return

    # Send as a new message
    await context.bot.send_message(chat_id=target_chat_id, text=message_text, reply_markup=reply_markup_for_lang(lang, context))

    context.user_data[USER_DATA_STEP] = UserSteps.NONE.name
    
    # Comprehensive cleanup of temporary user_data keys
    keys_to_clear = [
        USER_DATA_SELECTED_REGION, 
        USER_DATA_SELECTED_REGION_FOR_CHECK,
        USER_DATA_RAW_STREET_INPUT, 
        USER_DATA_CLARIFIED_ADDRESS_CACHE,
        USER_DATA_TEMP_SOUND_SETTINGS # If this is used and needs reset here
        # Add any other temporary keys used in various flows
    ]
    cleared_keys_log = []
    for key_to_pop in keys_to_clear:
        if context.user_data.pop(key_to_pop, None) is not None:
            cleared_keys_log.append(key_to_pop)
    if cleared_keys_log:
        log_info(f"Cleared temp user_data keys: {cleared_keys_log} for user {update.effective_user.id if update.effective_user else 'N/A'}")

async def handle_cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает действие отмены."""
    await reply_with_main_menu(update, context, "cancelled", "Operation cancelled.")


# --- УТИЛИТЫ (validate_user_input, is_user_rate_limited, normalize_address, etc.) ---
# Эти функции были в предыдущем ответе, здесь они используются.
# Убедитесь, что is_user_rate_limited использует config из context.
def validate_user_input(text: str) -> bool:
    if not text or len(text) > 1000: return False
    dangerous_patterns = ['<script', 'javascript:', 'onclick', 'onerror', 'onload', 'eval(', 'file://']
    return not any(pattern in text.lower() for pattern in dangerous_patterns)

def is_user_rate_limited(user_id: int, context: ContextTypes.DEFAULT_TYPE, max_requests_override: Optional[int] = None, window: int = 60) -> bool:
    bot_config_data: BotConfig = context.application.bot_data.get("config_ref")
    if not bot_config_data: return False 

    max_requests = max_requests_override if max_requests_override is not None else bot_config_data.max_requests_per_minute
    now = timestamp()
    user_reqs = user_request_counts.setdefault(user_id, []) # user_request_counts - глобальный
    user_reqs[:] = [req_time for req_time in user_reqs if now - req_time < window]
    
    if len(user_reqs) >= max_requests: return True
    user_reqs.append(now)
    return False

def normalize_address_component(text: str) -> str:
    if not text: return ""
    text = text.lower().strip()
    text = re.sub(r'[.,()\[\]"\']', '', text) 
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def fuzzy_match(s1: str, s2: str, threshold=0.85) -> bool:
    if not s1 or not s2: return False
    return SequenceMatcher(None, s1, s2).ratio() >= threshold

def match_address(user_address_region: str, user_address_street: str,
                  entry_regions: List[str], entry_streets: List[str],
                  context: ContextTypes.DEFAULT_TYPE) -> bool: # context добавлен для потенциального доступа к доп. картам
    norm_user_region = normalize_address_component(user_address_region)
    norm_user_street = normalize_address_component(user_address_street)

    norm_entry_regions = [normalize_address_component(r) for r in entry_regions if r]
    norm_entry_streets = [normalize_address_component(s) for s in entry_streets if s]

    region_match_found = False
    if not norm_entry_regions: # Если в объявлении регионы не указаны
        # Считаем совпадением, если у пользователя тоже не указан регион или это общий регион типа "все"
        # Это сложная логика, для простоты пока: если в объявлении нет регионов, не матчим конкретный регион пользователя.
        # Исключение: если пользовательский регион совпадает с одним из "общих" регионов в системе.
        # Это требует доработки и карты "общих" регионов.
        # log_warning(f"match_address: No regions specified in entry. User region: {norm_user_region}")
        region_match_found = True # Осторожно! Если в объявлении нет регионов, оно может быть для всех.
                                  # Но если у юзера задан конкретный регион, а в объявлении пусто - не должно матчиться.
                                  # Для текущей логики, если в объявлении нет регионов, оно не матчится с адресом юзера, у которого регион есть.
                                  # Если у юзера тоже нет региона (что странно), то формально совпадение.
        if norm_user_region: region_match_found = False # Если у юзера регион есть, а в новости нет - не матчим

    else:
        for er_norm in norm_entry_regions:
            if fuzzy_match(norm_user_region, er_norm, threshold=0.9):
                region_match_found = True; break
    
    if not region_match_found: return False

    if not norm_entry_streets: # Отключение на весь регион (улицы в объявлении не указаны)
        return True

    for es_norm in norm_entry_streets:
        if fuzzy_match(norm_user_street, es_norm, threshold=0.8): return True
        if norm_user_street in es_norm: return True # Частичное совпадение
    return False

def escape_markdown_v2(text: str) -> str:
    if not isinstance(text, str): text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(['\\' + char if char in escape_chars else char for char in text])

# --- АСИНХРОННОЕ СОХРАНЕНИЕ И ЗАГРУЗКА ДАННЫХ (модифицированы для передачи application в hook-ах) ---
async def _save_json_async(filepath: Path, data: Any, lock: asyncio.Lock):
    async with lock:
        try:
            async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            log_info(f"[FileSave] Данные сохранены: {filepath}")
        except Exception as e: log_error(f"[FileSave] Ошибка {filepath}: {e}", exc_info=True); raise

async def _load_json_async(filepath: Path, lock: asyncio.Lock, default_factory=dict) -> Any:
    # ... (без изменений) ...
    async with lock:
        if not await aios.path.exists(filepath):
            log_info(f"[FileLoad] Файл не найден {filepath}, возврат по умолчанию.")
            return default_factory() if callable(default_factory) else default_factory
        try:
            async with aiofiles.open(filepath, "r", encoding="utf-8") as f: content = await f.read()
            if not content:
                log_warning(f"[FileLoad] Файл пуст {filepath}. Возврат по умолчанию.")
                return default_factory() if callable(default_factory) else default_factory
            return json.loads(content)
        except json.JSONDecodeError as e_json:
            log_error(f"[FileLoad] Ошибка JSON {filepath}: {e_json}. Контент: '{content[:200] if 'content' in locals() else 'N/A'}'")
            return default_factory() if callable(default_factory) else default_factory
        except Exception as e:
            log_error(f"[FileLoad] Ошибка загрузки {filepath}: {e}", exc_info=True)
            return default_factory() if callable(default_factory) else default_factory


async def _perform_backup_async(filepath: Path, app_or_context: Application | ContextTypes.DEFAULT_TYPE):
    bot_config_data: BotConfig = app_or_context.bot_data.get("config_ref") if isinstance(app_or_context, Application) \
        else app_or_context.application.bot_data.get("config_ref")
    if not await aios.path.exists(filepath) or not bot_config_data: return
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = bot_config_data.backup_dir / f"{filepath.stem}.backup_{timestamp_str}{filepath.suffix}"
    try:
        await asyncio.get_event_loop().run_in_executor(None, shutil.copy2, filepath, backup_file)
        log_info(f"[Backup] Резервная копия {filepath} -> {backup_file}")
    except Exception as e: log_error(f"[Backup] Ошибка {filepath}: {e}", exc_info=True)

async def _cleanup_old_backups_async(filename_prefix_stem: str, app_or_context: Application | ContextTypes.DEFAULT_TYPE):
    # ... (аналогично _perform_backup_async для получения bot_config_data) ...
    bot_config_data: BotConfig = app_or_context.bot_data.get("config_ref") if isinstance(app_or_context, Application) \
        else app_or_context.application.bot_data.get("config_ref")
    if not bot_config_data: return
    try:
        backup_files = await asyncio.get_event_loop().run_in_executor( None, lambda: sorted(
                [f for f in bot_config_data.backup_dir.iterdir() if f.name.startswith(filename_prefix_stem) and ".backup_" in f.name],
                key=os.path.getmtime, reverse=True ))
        for old_backup in backup_files[bot_config_data.max_backups_to_keep:]: # Используем max_backups_to_keep
            try: await aios.remove(old_backup); log_info(f"[BackupCleanup] Удалена: {old_backup}")
            except Exception as e_rm: log_error(f"[BackupCleanup] Ошибка {old_backup}: {e_rm}", exc_info=True)
    except Exception as e_list: log_error(f"[BackupCleanup] Ошибка бэкапов для '{filename_prefix_stem}': {e_list}", exc_info=True)


async def save_user_settings_async(app_or_context: Application | ContextTypes.DEFAULT_TYPE):
    bd = app_or_context.bot_data if isinstance(app_or_context, Application) else app_or_context.application.bot_data
    bot_settings: Optional[_user_settings_type] = bd.get("user_settings_ref")
    bot_config_data: Optional[BotConfig] = bd.get("config_ref")
    if bot_settings is None or bot_config_data is None: log_error("[SaveSettings] Нет данных"); return
    
    filepath = bot_config_data.settings_file
    await _perform_backup_async(filepath, app_or_context)
    await _save_json_async(filepath, bot_settings, settings_file_lock)
    await _cleanup_old_backups_async(filepath.stem, app_or_context)

async def load_user_settings_async(application: Application): # Принимает Application для хуков
    bot_config_data: BotConfig = application.bot_data.get("config_ref")
    if not bot_config_data: log_error("[LoadSettings] Нет config_ref"); return
    raw_settings = await _load_json_async(bot_config_data.settings_file, settings_file_lock, default_factory=dict)
    application.bot_data.get("user_settings_ref", {}).clear()
    application.bot_data.get("user_settings_ref", {}).update(raw_settings)
    log_info(f"[LoadSettings] Настройки для {len(raw_settings)} пользователей.")

async def save_tracked_data_async(app_or_context: Application | ContextTypes.DEFAULT_TYPE):
    bd = app_or_context.bot_data if isinstance(app_or_context, Application) else app_or_context.application.bot_data
    bot_addresses: Optional[_user_addresses_type] = bd.get("user_addresses_ref")
    bot_notified: Optional[_user_notified_headers_type] = bd.get("user_notified_headers_ref")
    bot_config_data: Optional[BotConfig] = bd.get("config_ref")
    if not all([bot_addresses is not None, bot_notified is not None, bot_config_data]): log_error("[SaveTracked] Нет данных"); return

    addr_filepath = bot_config_data.address_file
    await _perform_backup_async(addr_filepath, app_or_context)
    await _save_json_async(addr_filepath, {str(k): v for k, v in bot_addresses.items()}, address_file_lock)
    await _cleanup_old_backups_async(addr_filepath.stem, app_or_context)

    notif_filepath = bot_config_data.notified_file
    await _perform_backup_async(notif_filepath, app_or_context)
    await _save_json_async(notif_filepath, {str(k): list(v) for k, v in bot_notified.items()}, notified_file_lock)
    await _cleanup_old_backups_async(notif_filepath.stem, app_or_context)

async def load_tracked_data_async(application: Application):
    bot_config_data: BotConfig = application.bot_data.get("config_ref")
    if not bot_config_data: log_error("[LoadTracked] Нет config_ref"); return
    
    raw_addresses = await _load_json_async(bot_config_data.address_file, address_file_lock, default_factory=dict)
    temp_user_addresses = {int(k): v for k, v in raw_addresses.items() if k.isdigit() and isinstance(v, list)} # Ключи int
    application.bot_data.get("user_addresses_ref", {}).clear()
    application.bot_data.get("user_addresses_ref", {}).update(temp_user_addresses)
    log_info(f"[LoadTracked] Адреса для {len(temp_user_addresses)} пользователей.")

    raw_notified = await _load_json_async(bot_config_data.notified_file, notified_file_lock, default_factory=dict)
    temp_notified = {int(k): set(v) for k, v in raw_notified.items() if k.isdigit() and isinstance(v, list)}
    application.bot_data.get("user_notified_headers_ref", {}).clear()
    application.bot_data.get("user_notified_headers_ref", {}).update(temp_notified)
    log_info(f"[LoadTracked] История уведомлений для {len(temp_notified)}.")

async def save_bot_general_status_async(app_or_context: Application | ContextTypes.DEFAULT_TYPE):
    bd = app_or_context.bot_data if isinstance(app_or_context, Application) else app_or_context.application.bot_data
    bot_status: Optional[_bot_general_status_type] = bd.get("bot_general_status_ref")
    bot_config_data: Optional[BotConfig] = bd.get("config_ref")
    if not bot_status or not bot_config_data: return
    await _save_json_async(bot_config_data.bot_status_file, bot_status, bot_status_file_lock)

async def load_bot_general_status_async(application: Application):
    bot_config_data: BotConfig = application.bot_data.get("config_ref")
    if not bot_config_data: return
    loaded_status = await _load_json_async(bot_config_data.bot_status_file, bot_status_file_lock, 
                                           default_factory=lambda: {"is_maintenance": False, "maintenance_message": ""})
    status_ref = application.bot_data.get("bot_general_status_ref", {})
    status_ref["is_maintenance"] = loaded_status.get("is_maintenance", False)
    status_ref["maintenance_message"] = loaded_status.get("maintenance_message", "")
    log_info(f"[LoadStatus] Статус бота: {status_ref}")

# --- ОСНОВНАЯ ЛОГИКА БОТА (Уведомления) ---
async def process_utility_data(user_id: int, context: ContextTypes.DEFAULT_TYPE, data: List[Dict], utility_type: str, emoji: str):
    handler_data = get_bot_data(context)
    if not data: return

    user_id_str = str(user_id)
    user_s = handler_data.user_settings.get(user_id_str, {})
    lang = user_s.get("lang", "ru")

    # Логика звука
    sound_enabled = user_s.get("notification_sound_enabled", True)
    silent_mode_active_flag = False
    if sound_enabled and user_s.get("silent_mode_enabled", False):
        try:
            user_tz_str = user_s.get("timezone", handler_data.config.default_user_timezone)
            user_timezone = pytz.timezone(user_tz_str)
            now_user_tz = datetime.now(user_timezone)
            start_s, end_s = user_s.get("silent_mode_start_time","23:00"), user_s.get("silent_mode_end_time","07:00")
            if not (re.match(r'^\d{2}:\d{2}$', start_s) and re.match(r'^\d{2}:\d{2}$', end_s)):
                start_s, end_s = "23:00", "07:00" # Fallback
            start_t, end_t = dt_time.fromisoformat(start_s), dt_time.fromisoformat(end_s)
            now_t = now_user_tz.time()
            if start_t <= end_t: silent_mode_active_flag = start_t <= now_t <= end_t
            else: silent_mode_active_flag = now_t >= start_t or now_t <= end_t
        except Exception as e_sound: log_error(f"Ошибка звука для {user_id_str}: {e_sound}")
    
    disable_notification_final_flag = not sound_enabled or silent_mode_active_flag
    # Конец логики звука

    user_addrs_list = handler_data.user_addresses.get(user_id, [])
    if not user_addrs_list: return

    sent_for_this_user_in_batch = False
    for entry in data:
        if not entry or not isinstance(entry, dict): continue
        header_parts = [str(entry.get(k, 'N/A')) for k in ['published', 'start_datetime', 'end_datetime']] + \
                       [utility_type, ",".join(sorted(entry.get("streets", []) or [])), ",".join(sorted(entry.get("regions", []) or []))]
        header_hash = hashlib.md5((" | ".join(header_parts)).encode('utf-8')).hexdigest()

        if header_hash in handler_data.user_notified.get(user_id, set()): continue
        
        for address_obj in user_addrs_list:
            if match_address(address_obj["region"], address_obj["street"], entry.get("regions", []), entry.get("streets", []), context):
                try:
                    # ... (Формирование сообщения msg как раньше, используя handler_data.translations)
                    type_off_key = f"{utility_type}_off"; type_off_text = handler_data.translations.get(type_off_key, {}).get(lang, utility_type.capitalize())
                    display_region = escape_markdown_v2(address_obj['region']); display_street = escape_markdown_v2(address_obj['street'])
                    start_dt_str = entry.get('start_datetime', 'N/A'); end_dt_str = entry.get('end_datetime', 'N/A')
                    msg_parts = [
                        f"{emoji} *{escape_markdown_v2(type_off_text)}* {display_region} \\- {display_street}",
                        f"📅 *{escape_markdown_v2(handler_data.translations.get('date_time_label', {}).get(lang, 'Period'))}:* {escape_markdown_v2(start_dt_str)} → {escape_markdown_v2(end_dt_str)}",
                    ] # ... (остальные части сообщения)
                    entry_regions = entry.get('regions'); entry_streets = entry.get('streets')
                    if entry_regions: msg_parts.append(f"📍 *{escape_markdown_v2(handler_data.translations.get('locations_label', {}).get(lang, 'Locations'))}:* {escape_markdown_v2(', '.join(entry_regions))}")
                    if entry_streets: msg_parts.append(f"  └ *{escape_markdown_v2(handler_data.translations.get('streets_label', {}).get(lang, 'Streets'))}:* {escape_markdown_v2(', '.join(entry_streets))}")
                    elif not entry_streets and entry_regions : msg_parts.append(f"  └ *{escape_markdown_v2(handler_data.translations.get('streets_label', {}).get(lang, 'Streets'))}:* {escape_markdown_v2(handler_data.translations.get('all_streets_in_region', {}).get(lang, 'All streets'))}")
                    msg_parts.extend([
                        f"⚙️ *{escape_markdown_v2(handler_data.translations.get('status_label', {}).get(lang, 'Status'))}:* {escape_markdown_v2(entry.get('shutdown_type', entry.get('status', 'N/A')))}",
                        f"🗓 *{escape_markdown_v2(handler_data.translations.get('published_label', {}).get(lang, 'Published'))}:* {escape_markdown_v2(entry.get('publication_date_on_site', entry.get('published', 'N/A')))}"
                    ])
                    msg = "\n\n".join(msg_parts)

                    await context.bot.send_message(chat_id=user_id, text=msg, parse_mode=ParseMode.MARKDOWN_V2, disable_notification=disable_notification_final_flag)
                    handler_data.user_notified.setdefault(user_id, set()).add(header_hash)
                    sent_for_this_user_in_batch = True
                    log_info(f"Уведомление ({utility_type}) -> {user_id} по {address_obj['street']}")
                    break 
                except Exception as e: log_error(f"Ошибка уведомления ({utility_type}) для {user_id}: {e}", exc_info=True)
    
    if sent_for_this_user_in_batch: # Сохраняем только если что-то было отправлено
        await save_tracked_data_async(context)


async def check_site_for_user(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    handler_data = get_bot_data(context)
    if not handler_data.user_addresses.get(user_id): return

    log_info(f"Проверка сайтов для {user_id}")
    try:
        # Парсеры должны принимать context для доступа к AI_MODEL_PATH и другим настройкам, если они не глобальные
        water_data, gas_data, electric_data = await asyncio.gather(
            parse_all_water_announcements_async(context), 
            parse_all_gas_announcements_async(context),
            parse_all_electric_announcements_async(context),
            return_exceptions=True
        )
        # Логирование ошибок парсинга
        if isinstance(water_data, Exception): log_error(f"Ошибка парсинга воды: {water_data}"); water_data = []
        if isinstance(gas_data, Exception): log_error(f"Ошибка парсинга газа: {gas_data}"); gas_data = []
        if isinstance(electric_data, Exception): log_error(f"Ошибка парсинга эл-ва: {electric_data}"); electric_data = []
    except Exception as e: log_error(f"Крит. ошибка сбора данных для {user_id}: {e}", exc_info=True); return

    await process_utility_data(user_id, context, water_data, "water", "🚰")
    await process_utility_data(user_id, context, gas_data, "gas", "🔥")
    await process_utility_data(user_id, context, electric_data, "electric", "💡")

async def is_shutdown_for_address_now_v2(address_street: str, address_region: str, context: ContextTypes.DEFAULT_TYPE) -> Tuple[List[Dict], str]:
    handler_data = get_bot_data(context)
    lang = get_lang_for_handler(context, None) # Общий язык для проверки
    active_shutdowns_details: List[Dict] = []

    def _check_match(entry_data: List[Dict], utility_type: str):
        if not entry_data: return
        for entry in entry_data:
            if not entry or not isinstance(entry, dict): continue
            if match_address(address_region, address_street, entry.get("regions", []), entry.get("streets", []), context):
                active_shutdowns_details.append({ # Сбор деталей как в предыдущей версии
                    "utility_type": utility_type,
                    "display_name": handler_data.translations.get(f"{utility_type}_off_short", {}).get(lang, utility_type.capitalize()),
                    "start_datetime": entry.get("start_datetime", "N/A"), "end_datetime": entry.get("end_datetime", "N/A"),
                    "status": entry.get("shutdown_type", entry.get("status", "N/A")),
                    "entry_regions": entry.get("regions", []), "entry_streets": entry.get("streets", []),
                })
    try:
        # ... (сбор water_data, gas_data, electric_data как в check_site_for_user) ...
        water_data, gas_data, electric_data = await asyncio.gather(
            parse_all_water_announcements_async(context), 
            parse_all_gas_announcements_async(context),
            parse_all_electric_announcements_async(context),
            return_exceptions=True
        )
        if not isinstance(water_data, Exception): _check_match(water_data, "water")
        else: log_error(f"Ошибка воды для is_shutdown_v2: {water_data}")
        # ... (аналогично для gas и electric)
        if not isinstance(gas_data, Exception): _check_match(gas_data, "gas")
        else: log_error(f"Ошибка газа для is_shutdown_v2: {gas_data}")
        if not isinstance(electric_data, Exception): _check_match(electric_data, "electric")
        else: log_error(f"Ошибка эл-ва для is_shutdown_v2: {electric_data}")

    except Exception as e: log_error(f"Ошибка is_shutdown_v2 для {address_region}, {address_street}: {e}", exc_info=True)
    
    if not active_shutdowns_details:
        return [], handler_data.translations.get("shutdown_check_not_found_v2", {}).get(lang, "✅ No active outages for '{address_display}'.") # Плейсхолдер будет заменен вызывающей функцией
    
    active_shutdowns_details.sort(key=lambda x: x.get("start_datetime", "0"))
    messages = []
    # ... (Формирование messages как в предыдущей версии, используя handler_data.translations) ...
    for detail in active_shutdowns_details:
        emoji = "🚰" if detail["utility_type"] == "water" else "🔥" if detail["utility_type"] == "gas" else "💡"
        type_off_text = handler_data.translations.get(f"{detail['utility_type']}_off", {}).get(lang, detail['utility_type'].capitalize())
        msg = (f"{emoji} *{escape_markdown_v2(type_off_text)}*\n" # ... (и т.д. как в предыдущей версии)
               f"📅 *{escape_markdown_v2(handler_data.translations.get('date_time_label', {}).get(lang, 'Period'))}:* {escape_markdown_v2(detail['start_datetime'])} → {escape_markdown_v2(detail['end_datetime'])}\n"
               f"📍 *{escape_markdown_v2(handler_data.translations.get('locations_label', {}).get(lang, 'Locations'))}:* {escape_markdown_v2(', '.join(detail['entry_regions']))}\n"
        )
        if detail['entry_streets']: msg += f"  └ *{escape_markdown_v2(handler_data.translations.get('streets_label', {}).get(lang, 'Streets'))}:* {escape_markdown_v2(', '.join(detail['entry_streets']))}\n"
        else: msg += f"  └ *{escape_markdown_v2(handler_data.translations.get('streets_label', {}).get(lang, 'Streets'))}:* {escape_markdown_v2(handler_data.translations.get('all_streets_in_region', {}).get(lang, 'All streets'))}\n"
        msg += f"⚙️ *{escape_markdown_v2(handler_data.translations.get('status_label', {}).get(lang, 'Status'))}:* {escape_markdown_v2(detail['status'])}"
        messages.append(msg)

    full_response_text = handler_data.translations.get("shutdown_check_found_v2_intro", {}).get(lang, "⚠️ Active outages for '{address_display}':")
    full_response_text += "\n\n" + "\n\n---\n\n".join(messages)
    return active_shutdowns_details, full_response_text


# --- ОБРАБОТЧИКИ КОМАНД ТЕЛЕГРАМ ---
# Админские команды (maintenance_on/off_command, broadcast_message_to_users) - как в предыдущем ответе
def admin_only(func: Callable): # Декоратор для админских команд
    # ... (реализация как в предыдущем ответе, используя get_bot_data) ...
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        handler_data = get_bot_data(context)
        lang = get_lang_for_handler(context, user.id if user else None)

        if not handler_data.config or not user or user.id not in handler_data.config.admin_user_ids:
            log_warning(f"Неавторизованный доступ к админ-команде: user_id={user.id if user else 'Unknown'}")
            if update.message:
                await update.message.reply_text(handler_data.translations.get("admin_command_not_authorized", {}).get(lang, "Not authorized."))
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def broadcast_message_to_users(context: ContextTypes.DEFAULT_TYPE, message_text: str, source_admin_id: int):
    # ... (реализация как в предыдущем ответе, используя get_bot_data) ...
    handler_data = get_bot_data(context)
    user_ids_to_notify = [int(uid_str) for uid_str in handler_data.user_settings.keys()]
    sent_count = 0; failed_count = 0
    log_info(f"Admin {source_admin_id} запускает рассылку: '{message_text}' для {len(user_ids_to_notify)}.")
    for user_id in user_ids_to_notify:
        if user_id == source_admin_id: continue
        try:
            # Используем escape_markdown_v2, если сообщение не отформатировано заранее
            await context.bot.send_message(chat_id=user_id, text=escape_markdown_v2(message_text), parse_mode=ParseMode.MARKDOWN_V2)
            sent_count += 1; await asyncio.sleep(0.05)
        except Forbidden: log_warning(f"Рассылка: Пользователь {user_id} заблокировал."); failed_count += 1
        except Exception as e: log_error(f"Рассылка: Ошибка для {user_id}: {e}"); failed_count += 1
    summary = f"Рассылка: Отправлено: {sent_count}. Ошибок: {failed_count}."
    log_info(summary); await context.bot.send_message(chat_id=source_admin_id, text=summary)


@admin_only
async def maintenance_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (реализация как в предыдущем ответе, используя get_bot_data и get_lang_for_handler) ...
    handler_data = get_bot_data(context)
    user = update.effective_user
    lang = get_lang_for_handler(context, user.id) # Язык для ответа админу
    custom_message = " ".join(context.args) if context.args else None
    user_notification_message_text = custom_message or handler_data.translations.get("maintenance_on_default_user_message", {}).get("ru", "Bot is under maintenance.")
    
    handler_data.bot_status["is_maintenance"] = True
    handler_data.bot_status["maintenance_message"] = user_notification_message_text
    await save_bot_general_status_async(context)
    
    admin_feedback = handler_data.translations.get("maintenance_on_admin_feedback", {}).get(lang, "Maintenance ON. Users will be notified with: '{message}'")
    await update.message.reply_text(admin_feedback.format(message=user_notification_message_text))
    log_info(f"Admin {user.id} включил обслуживание. Сообщение: {user_notification_message_text}")
    await broadcast_message_to_users(context, user_notification_message_text, user.id)


@admin_only
async def maintenance_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (реализация как в предыдущем ответе) ...
    handler_data = get_bot_data(context)
    user = update.effective_user
    lang = get_lang_for_handler(context, user.id)
    handler_data.bot_status["is_maintenance"] = False
    await save_bot_general_status_async(context)
    await update.message.reply_text(handler_data.translations.get("maintenance_off_admin_feedback", {}).get(lang, "Maintenance mode OFF."))
    log_info(f"Admin {user.id} выключил обслуживание.")
    back_online_message = handler_data.translations.get("bot_active_again_user_notification", {}).get("ru", "The bot is back online!") # Используем язык по умолчанию для массовой рассылки
    await broadcast_message_to_users(context, back_online_message, user.id)


@handler_prechecks
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user # user гарантированно есть после @handler_prechecks
    user_id_str = str(user.id)
    handler_data = get_bot_data(context) # Получаем доступ к данным
    
    log_info(f"[CmdStart] User: {user_id_str}, Name: {user.full_name}")

    # Язык уже должен быть в context.user_data[USER_DATA_LANG] благодаря декоратору,
    # или будет предложен выбор, если это абсолютно новый пользователь.
    current_lang_in_context = context.user_data.get(USER_DATA_LANG)
    lang_in_settings = handler_data.user_settings.get(user_id_str, {}).get("lang")

    if not current_lang_in_context and not lang_in_settings: # Абсолютно новый пользователь
        context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_LANGUAGE_CHOICE.name
        await update.message.reply_text(
            handler_data.translations.get("choose_language_inline", {}).get("ru", "Please choose your language:"),
            reply_markup=get_language_inline_keyboard()
        )
    else:
        lang = current_lang_in_context or lang_in_settings or "ru" # Определяем язык для меню
        if not current_lang_in_context: context.user_data[USER_DATA_LANG] = lang # Устанавливаем в user_data, если не было

        await reply_with_main_menu(update, context, "start_text", "Hello! Choose an action.")


@handler_prechecks
async def handle_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        log_warning("[LangCallback] Query or query.data is missing.")
        if query: await query.answer("Error processing request.")
        return
    await query.answer()

    user = query.from_user
    user_id_str = str(user.id)
    handler_data = get_bot_data(context)
    
    try:
        prefix_len = len(CALLBACK_PREFIX_LANG)
        if not query.data.startswith(CALLBACK_PREFIX_LANG):
            log_error(f"Invalid callback data format for language selection: {query.data}")
            await query.edit_message_text(text="Error: Invalid language callback format.")
            return
        
        selected_lang_code = query.data[prefix_len:]

        if selected_lang_code not in languages.values():
            log_warning(f"Invalid language code '{selected_lang_code}' selected by user {user_id_str}.")
            # Assuming you have a translation for this error
            lang_for_error = context.user_data.get(USER_DATA_LANG, "en") # Use current or default for error msg
            error_text = handler_data.translations.get("error_invalid_lang_code", {}).get(lang_for_error, "Error: Invalid language code.")
            await query.edit_message_text(text=error_text)
            return

        log_info(f"User {user_id_str} initiated language change to: {selected_lang_code}. Current context lang: {context.user_data.get(USER_DATA_LANG)}. Current settings lang: {handler_data.user_settings.get(user_id_str, {}).get('lang')}")

        context.user_data[USER_DATA_LANG] = selected_lang_code # Update current context
        
        current_s = handler_data.user_settings.get(user_id_str, {}).copy()
        current_s["lang"] = selected_lang_code
        # ... (initialize other settings if needed) ...
        handler_data.user_settings[user_id_str] = current_s
        
        # Log before and after save attempt
        log_info(f"Attempting to save language '{selected_lang_code}' for user {user_id_str} to settings file.")
        await save_user_settings_async(context) # Persist changes
        log_info(f"Save complete. Verifying settings for {user_id_str}: {handler_data.user_settings.get(user_id_str, {}).get('lang')}")
        
        try:
            await query.delete_message()
        except Exception as e_del:
            log_warning(f"Could not delete language selection message for user {user_id_str}: {e_del}")

        # The lang for "language_set" and its keyboard should now be selected_lang_code
        # because reply_with_main_menu calls get_lang_for_handler which reads from context.user_data
        await reply_with_main_menu(update, context, "language_set", "Language set!")
        log_info(f"Language change to '{selected_lang_code}' for user {user_id_str} processed. Main menu sent.")

    except Exception as e:
        log_error(f"Error in handle_language_callback for {user_id_str}, data '{query.data}': {e}", exc_info=True)
        try:
            # Try to edit message if delete failed or if error happened before delete
            await query.edit_message_text(text="An error occurred while setting the language. Please try /start.")
        except Exception as e_edit:
            log_error(f"Failed to send error message in handle_language_callback: {e_edit}")
            # If editing also fails, maybe send a new message if possible (but query.message might be gone)
            if query.message: # Check if original message context still exists
                 await context.bot.send_message(chat_id=user_id_str, text="An error occurred. Please try /start.")

@handler_prechecks
async def change_language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang_for_handler(context, update.effective_user.id)
    handler_data = get_bot_data(context)
    await update.message.reply_text(
        handler_data.translations.get("choose_language_inline", {}).get(lang, "Choose language:"),
        reply_markup=get_language_inline_keyboard()
    )
    context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_LANGUAGE_CHOICE.name


@handler_prechecks
async def address_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang_for_handler(context, user_id)
    handler_data = get_bot_data(context)
    user_addrs = handler_data.user_addresses.get(user_id, [])
    
    if user_addrs:
        address_lines = [f"📍 {a['region']} — {a['street']}" for a in user_addrs]
        text_to_send = handler_data.translations.get("address_list", {}).get(lang, "Your addresses:") + "\n" + "\n".join(address_lines)
    else:
        text_to_send = handler_data.translations.get("no_addresses", {}).get(lang, "No addresses added yet.")
    
    await update.message.reply_text(text_to_send, reply_markup=reply_markup_for_lang(lang, context))
    context.user_data[USER_DATA_STEP] = UserSteps.NONE.name


@handler_prechecks
async def show_statistics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (реализация как в предыдущем ответе, используя get_bot_data и get_lang_for_handler) ...
    user_id = update.effective_user.id
    lang = get_lang_for_handler(context, user_id)
    handler_data = get_bot_data(context)
    
    active_users_count = len(handler_data.user_settings)
    total_tracked_addresses = sum(len(addr_list) for addr_list in handler_data.user_addresses.values())
    uptime_seconds = timestamp() - bot_start_time
    uptime_str = str(timedelta(seconds=int(uptime_seconds))) # Простое форматирование
    user_addr_count = len(handler_data.user_addresses.get(user_id, []))
    user_notif_count = len(handler_data.user_notified.get(user_id, set()))

    stats_text = (
        f"📊 {handler_data.translations.get('statistics_title', {}).get(lang, 'Bot Statistics')}\n\n"
        f"🕒 {handler_data.translations.get('stats_uptime', {}).get(lang, 'Uptime')}: {uptime_str}\n"
        f"👥 {handler_data.translations.get('stats_users_with_settings', {}).get(lang, 'Total users (with settings)')}: {active_users_count}\n"
        f"📍 {handler_data.translations.get('stats_total_addresses', {}).get(lang, 'Total addresses tracked')}: {total_tracked_addresses}\n\n"
        f"👤 {handler_data.translations.get('stats_your_info_title', {}).get(lang, 'Your Information')}:\n"
        f"🏠 {handler_data.translations.get('stats_your_addresses', {}).get(lang, 'Your addresses')}: {user_addr_count}\n"
        f"📨 {handler_data.translations.get('stats_your_notifications_sent', {}).get(lang, 'Notifications you received')}: {user_notif_count}"
    )
    await update.message.reply_text(stats_text, reply_markup=reply_markup_for_lang(lang, context))
    context.user_data[USER_DATA_STEP] = UserSteps.NONE.name


@handler_prechecks
async def show_subscription_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang_for_handler(context, update.effective_user.id)
    handler_data = get_bot_data(context)
    await update.message.reply_text(
        handler_data.translations.get("subscription_options_title", {}).get(lang, "Choose plan:"),
        reply_markup=get_subscription_keyboard(lang, context)
    )
    context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_SUBSCRIPTION_CHOICE.name


@handler_prechecks # Callback не требует prechecks, но язык нужен
async def handle_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_id_str = str(user_id)
    lang = get_lang_for_handler(context, user_id) # Убедимся, что язык есть
    handler_data = get_bot_data(context)

    try:
        selected_tier_key = query.data.split(CALLBACK_PREFIX_SUBSCRIBE)[1]
        if selected_tier_key not in handler_data.premium_tiers:
            await query.edit_message_text(handler_data.translations.get("error_invalid_tier", {}).get(lang, "Invalid tier."))
            return

        plan = handler_data.premium_tiers[selected_tier_key]
        current_s = handler_data.user_settings.get(user_id_str, {})
        current_s.update({
            "frequency": plan["interval"], 
            "current_tier": selected_tier_key,
            "ads_enabled": plan.get("ad_enabled", plan["price_amd"] == 0) # ads_enabled, если бесплатно
        })
        handler_data.user_settings[user_id_str] = current_s
        await save_user_settings_async(context)

        tier_name_tr = handler_data.translations.get(f'tier_{selected_tier_key.lower()}', {}).get(lang, selected_tier_key)
        # ... (форматирование сообщения об успехе)
        success_msg = handler_data.translations.get("subscription_success_details",{}).get(lang, "Subscribed to {plan}.").format(plan=tier_name_tr)
        await query.edit_message_text(success_msg)
        await reply_with_main_menu(update, context, "menu_returned") # Отправляем новое сообщение с меню
    except Exception as e:
        log_error(f"Error in handle_subscription_callback for {user_id_str}: {e}", exc_info=True)
        await query.edit_message_text(handler_data.translations.get("error_generic", {}).get(lang, "Error."))
    finally: # Сброс шага в reply_with_main_menu
        pass


@handler_prechecks
async def check_address_command_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang_for_handler(context, update.effective_user.id)
    handler_data = get_bot_data(context)
    await update.message.reply_text(
        handler_data.translations.get("choose_region_for_check", {}).get(lang, "Choose region to check:"),
        reply_markup=get_region_keyboard(lang, context)
    )
    context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_REGION_FOR_CHECK.name


@handler_prechecks # Команда /sound
async def sound_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_sound_settings_menu(update, context)
    # Шаг не меняем, управление через коллбэки меню настроек

async def show_sound_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id_to_edit: Optional[int] = None):
    # ... (реализация как в предыдущем ответе, используя get_bot_data и get_lang_for_handler) ...
    # ... Важно: при вызове из текстовой команды message_id_to_edit будет None ...
    user = update.effective_user if update.effective_user else update.callback_query.from_user
    lang = get_lang_for_handler(context, user.id)
    handler_data = get_bot_data(context)
    user_id_str = str(user.id)
    current_s = handler_data.user_settings.get(user_id_str, {})

    sound_on = current_s.get("notification_sound_enabled", True)
    silent_mode_on = current_s.get("silent_mode_enabled", False)
    silent_start = current_s.get("silent_mode_start_time", "23:00")
    silent_end = current_s.get("silent_mode_end_time", "07:00")

    sound_status_text = handler_data.translations.get("notification_sound_on" if sound_on else "notification_sound_off", {}).get(lang, "Sound ON" if sound_on else "Sound OFF")
    silent_status_text = handler_data.translations.get("silent_mode_on" if silent_mode_on else "silent_mode_off", {}).get(lang, "Silent ON ({start}-{end})" if silent_mode_on else "Silent OFF").format(start=silent_start, end=silent_end)

    keyboard_markup = await get_sound_settings_inline_keyboard(user_id_str, context) # Используем хелпер
    title_text = handler_data.translations.get("sound_settings_title", {}).get(lang, "Sound Settings")

    if message_id_to_edit and update.callback_query:
        try: await update.callback_query.edit_message_text(text=title_text, reply_markup=keyboard_markup)
        except Exception as e: log_error(f"Error editing sound menu: {e}") # Могло быть отправлено новое сообщение
    elif update.message: # Вызов из команды /sound или текстовой кнопки
        await update.message.reply_text(text=title_text, reply_markup=keyboard_markup)


@handler_prechecks # Callback не требует prechecks, но язык нужен
async def handle_sound_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (реализация как в предыдущем ответе, используя get_bot_data и get_lang_for_handler) ...
    query = update.callback_query; await query.answer()
    user = query.from_user; user_id_str = str(user.id)
    lang = get_lang_for_handler(context, user.id)
    handler_data = get_bot_data(context)
    current_s = handler_data.user_settings.get(user_id_str, {})
    action = query.data.split(CALLBACK_PREFIX_SOUND)[1]
    changed = False

    if action == "toggle_main_sound":
        current_s["notification_sound_enabled"] = not current_s.get("notification_sound_enabled", True); changed = True
    elif action == "toggle_silent_status":
        current_s["silent_mode_enabled"] = not current_s.get("silent_mode_enabled", False); changed = True
        if "timezone" not in current_s: current_s["timezone"] = handler_data.config.default_user_timezone
    elif action == "set_silent_start":
        context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_SILENT_START_TIME.name
        await query.message.reply_text(handler_data.translations.get("enter_silent_start_time_prompt", {}).get(lang, "Enter start HH:MM:"))
        return 
    elif action == "set_silent_end":
        context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_SILENT_END_TIME.name
        await query.message.reply_text(handler_data.translations.get("enter_silent_end_time_prompt", {}).get(lang, "Enter end HH:MM:"))
        return
    elif action == "back_to_main":
        await query.delete_message()
        await reply_with_main_menu(update, context, "menu_returned")
        return

    if changed:
        handler_data.user_settings[user_id_str] = current_s
        await save_user_settings_async(context)
    
    await show_sound_settings_menu(update, context, message_id_to_edit=query.message.message_id if query.message else None)


@handler_prechecks
async def handle_silent_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (реализация как в предыдущем ответе, используя get_bot_data и get_lang_for_handler) ...
    # ... Важно: после установки времени, вызвать show_sound_settings_menu для обновления меню ...
    user = update.effective_user; user_id_str = str(user.id)
    lang = get_lang_for_handler(context, user.id)
    handler_data = get_bot_data(context)
    current_step_name = context.user_data.get(USER_DATA_STEP)
    current_s = handler_data.user_settings.get(user_id_str, {})
    entered_time = update.message.text.strip()

    if not re.match(r'^(?:[01]\d|2[0-3]):[0-5]\d$', entered_time):
        await update.message.reply_text(handler_data.translations.get("invalid_time_format", {}).get(lang, "Invalid HH:MM"))
        return # Оставляем на том же шаге

    if current_step_name == UserSteps.AWAITING_SILENT_START_TIME.name:
        current_s["silent_mode_start_time"] = entered_time
    elif current_step_name == UserSteps.AWAITING_SILENT_END_TIME.name:
        current_s["silent_mode_end_time"] = entered_time
    
    handler_data.user_settings[user_id_str] = current_s
    await save_user_settings_async(context)
    await update.message.reply_text(handler_data.translations.get("sound_settings_saved", {}).get(lang, "Time set!"))
    
    context.user_data[USER_DATA_STEP] = UserSteps.NONE.name # Сброс шага
    # Показываем обновленное меню настроек звука новым сообщением
    await show_sound_settings_menu(update, context)


async def get_sound_settings_inline_keyboard(user_id_str: str, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    # ... (реализация как в предыдущем ответе, используя get_bot_data) ...
    handler_data = get_bot_data(context)
    current_s = handler_data.user_settings.get(user_id_str, {})
    lang = current_s.get("lang", "ru")
    sound_on = current_s.get("notification_sound_enabled", True)
    silent_mode_on = current_s.get("silent_mode_enabled", False)
    silent_start = current_s.get("silent_mode_start_time", "23:00"); silent_end = current_s.get("silent_mode_end_time", "07:00")
    sound_text = handler_data.translations.get("notification_sound_on" if sound_on else "notification_sound_off", {}).get(lang)
    silent_text = handler_data.translations.get("silent_mode_on" if silent_mode_on else "silent_mode_off", {}).get(lang).format(start=silent_start, end=silent_end)
    
    keyboard = [
        [InlineKeyboardButton(f"{handler_data.translations.get('toggle_sound', {}).get(lang)}: {sound_text}", callback_data=f"{CALLBACK_PREFIX_SOUND}toggle_main_sound")],
        [InlineKeyboardButton(f"{handler_data.translations.get('toggle_silent_mode', {}).get(lang)}: {silent_text}", callback_data=f"{CALLBACK_PREFIX_SOUND}toggle_silent_status")],
    ]
    if silent_mode_on:
        keyboard.append([
            InlineKeyboardButton(f"{handler_data.translations.get('set_silent_start_time', {}).get(lang)}: {silent_start}", callback_data=f"{CALLBACK_PREFIX_SOUND}set_silent_start"),
            InlineKeyboardButton(f"{handler_data.translations.get('set_silent_end_time', {}).get(lang)}: {silent_end}", callback_data=f"{CALLBACK_PREFIX_SOUND}set_silent_end")
        ])
    keyboard.append([InlineKeyboardButton(handler_data.translations.get("back_to_main_menu_btn", {}).get(lang), callback_data=f"{CALLBACK_PREFIX_SOUND}back_to_main")])
    return InlineKeyboardMarkup(keyboard)


async def show_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /help — выводит подробную справку из translations.help_text_detailed
    """
    handler_data = get_bot_data(context)
    user = update.effective_user
    lang = get_lang_for_handler(context, user.id)
    help_text = handler_data.translations.get("help_text_detailed", {}).get(
        lang,
        "🇦🇲\n"
        "Հասանելի հրամաններ՝\n"
        "/start — Գործարկեք բոտը և ընտրեք լեզու։\n"
        "/language — Փոխեք ինտերֆեյսի լեզուն։\n"
        "/myaddresses — Ցուցադրեք պահպանված հասցեները։\n"
        "/stats — Ցուցադրեք վիճակագրությունը։\n"
        "/help — Ցուցադրեք այս հուշումը։\n"
        "/sound — Ձայնի կարգավորումներ։\n"
        "/set_frequency — Փոխեք ստուգումների հաճախականությունը։\n\n"
        "Admin հրամաններ՝\n"
        "/maintenance_on — Միացրեք սպասարկման ռեժիմը։\n"
        "/maintenance_off — Անջատեք սպասարկման ռեժիմը։\n\n\n\n"
        "🇷🇺\n"
        "Доступные команды:\n"
        "/start — Запустить бота и выбрать язык.\n"
        "/language — Изменить язык интерфейса.\n"
        "/myaddresses — Показать сохранённые адреса.\n"
        "/stats — Показать статистику.\n"
        "/help — Показать эту подсказку.\n"
        "/sound — Настройки звука.\n"
        "/set_frequency — Изменить частоту проверок.\n\n"
        "Админские команды:\n"
        "/maintenance_on — Включить режим обслуживания.\n"
        "/maintenance_off — Выключить режим обслуживания.\n\n\n\n"
        "🇬🇧\n"
        "Available commands:\n"
        "/start — Start the bot and select a language.\n"
        "/language — Change the interface language.\n"
        "/myaddresses — Show saved addresses.\n"
        "/stats — Show statistics.\n"
        "/help — Show this hint.\n"
        "/sound — Sound settings.\n"
        "/set_frequency — Change the frequency of checks.\n\n"
        "Admin commands:\n"
        "/maintenance_on — Enable maintenance mode.\n"
        "/maintenance_off — Disable maintenance mode."
    )

    await update.message.reply_text(help_text)

# In smart_bot.py

# ... (other imports and setup) ...

@handler_prechecks
async def handle_text_message_new_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        log_warning("[TextMsg] Received update without message text.")
        return

    text_received = update.message.text.strip()
    user = update.effective_user
    message = update.message # Ensure message is defined for replies
    user_id = user.id
    user_id_str = str(user.id)
    lang = get_lang_for_handler(context, user_id)
    handler_data = get_bot_data(context)
    current_step_name = context.user_data.get(USER_DATA_STEP, UserSteps.NONE.name)

    log_info(f"[TextMsg Router] User: {user_id_str}, Received Text: '{text_received}', Lang: '{lang}', Step: '{current_step_name}'")

    # --- Centralized Cancel Check ---
    cancel_text_localized = handler_data.translations.get("cancel", {}).get(lang, "❌ Cancel") # Default to a common one
    log_info(f"[TextMsg Router] Comparing for Cancel: Received='{text_received}', ExpectedCancelLocalized='{cancel_text_localized}', Match={text_received == cancel_text_localized}")
    if text_received == cancel_text_localized:
        log_info(f"[TextMsg Router] Cancel action triggered by text: '{text_received}' for step {current_step_name}")
        await handle_cancel_action(update, context) # This resets step to NONE and replies with main menu
        return

    # Helper to get translated button text for cleaner lookups
    def get_btn_text(key: str, default: str) -> str:
        return handler_data.translations.get(key, {}).get(lang, default)

    if current_step_name == UserSteps.NONE.name:
        button_actions: Dict[str, Callable] = {
            get_btn_text("add_address_btn", "➕ Add Address"): lambda: (
                message.reply_text(get_btn_text("choose_region", "Region:"), reply_markup=get_region_keyboard(lang, context)), # Message reply here
                UserSteps.AWAITING_REGION.name
            ),
            get_btn_text("remove_address_btn", "➖ Remove Address"): lambda: (
                message.reply_text(get_btn_text("enter_address_to_remove_prompt", "Street to remove?"),
                                 reply_markup=ReplyKeyboardMarkup([[get_btn_text("cancel", "❌ Cancel")]], resize_keyboard=True, one_time_keyboard=True)),
                UserSteps.AWAITING_ADDRESS_TO_REMOVE.name
            ) if handler_data.user_addresses.get(user_id) else (
                message.reply_text(get_btn_text("no_addresses", "No addresses.")), # Message reply here
                UserSteps.NONE.name 
            ),
            get_btn_text("show_addresses_btn", "📋 Show Addresses"): lambda: (address_list_command(update, context), UserSteps.NONE.name), # Command handles reply and step
            get_btn_text("clear_all_btn", "🧹 Clear All"): lambda: (
                 message.reply_text(get_btn_text("confirm_clear", "Confirm clear all?"), 
                                  reply_markup=ReplyKeyboardMarkup([[KeyboardButton(get_btn_text("yes", "Yes")),
                                                                     KeyboardButton(get_btn_text("no", "No"))]],
                                                                    resize_keyboard=True, one_time_keyboard=True)), # Message reply here
                UserSteps.AWAITING_CLEAR_ALL_CONFIRMATION.name
            ) if handler_data.user_addresses.get(user_id) else (
                message.reply_text(get_btn_text("no_addresses", "No addresses.")), # Message reply here
                UserSteps.NONE.name
            ),
            get_btn_text("check_address_btn", "🔍 Check Address"): lambda: (check_address_command_entry(update, context), UserSteps.AWAITING_REGION_FOR_CHECK.name), # Command handles reply and step
            get_btn_text("sound_settings_btn", "🎵 Sound Settings"): lambda: (sound_settings_command(update, context), UserSteps.NONE.name), # Command handles reply, step managed by callbacks
            get_btn_text("subscription_btn", "⭐ Subscription"): lambda: (show_subscription_options(update, context), UserSteps.AWAITING_SUBSCRIPTION_CHOICE.name), # Command handles reply, step managed by callbacks
            get_btn_text("statistics_btn", "📊 Statistics"): lambda: (show_statistics_command(update, context), UserSteps.NONE.name), # Command handles reply and step
            get_btn_text("set_frequency_btn", "⏱️ Set Frequency"): lambda: (set_frequency_command_entry(update, context), UserSteps.AWAITING_FREQUENCY_CHOICE.name), # Command handles reply and step
            get_btn_text("help_btn", "❓ Help"): lambda: (show_help_command(update, context), UserSteps.NONE.name), # Command handles reply and step
        }
        
        action_to_execute = None
        next_step_for_action = UserSteps.NONE.name # Default to no change or handled by command

        for btn_text_key, action_config in button_actions.items():
            log_info(f"[TextMsg Router] Main Menu Check: Received='{text_received}', ComparingWith='{btn_text_key}', Match={text_received == btn_text_key}")
            if text_received == btn_text_key:
                if isinstance(action_config, tuple): # (action_lambda, next_step_name)
                    action_to_execute = action_config[0]
                    next_step_for_action = action_config[1]
                else: # Just an action_lambda (e.g. a command that handles its own step)
                    action_to_execute = action_config
                break
        
        if action_to_execute:
            log_info(f"[TextMsg Router] Action found for '{text_received}'. Next step will be: {next_step_for_action}")
            result = action_to_execute() # Execute the lambda
            if asyncio.iscoroutine(result): # If the lambda itself returned an awaitable (e.g. a direct command call)
                await result
            
            # If the lambda returned a tuple like (message_reply_awaitable, step_name)
            # this structure needs adjustment, or the lambda directly sets the step.
            # The current button_actions lambdas mostly either call commands (which handle their own replies/steps)
            # or return a (reply_awaitable, step_name) for direct execution.
            # The above call `action_to_execute()` already executes the first part if it's a reply.
            
            # Set the step if it was part of the config
            if next_step_for_action != UserSteps.NONE.name or action_to_execute is not None and not isinstance(action_config, tuple):
                 # If action_config was not a tuple, it means the step is managed by the command or should remain NONE
                 # If action_config was a tuple, next_step_for_action is already set.
                 if next_step_for_action != UserSteps.NONE.name : # check if it needs to be assigned
                    context.user_data[USER_DATA_STEP] = next_step_for_action.name

            # If a command was called that reset the step to NONE (e.g. address_list_command), this is fine.
            # If a new step was set (e.g. AWAITING_REGION), this is also fine.
            log_info(f"[TextMsg Router] After action for '{text_received}', new step in context: {context.user_data.get(USER_DATA_STEP)}")

        else: # No button matched in NONE state
            log_warning(f"[TextMsg Router] Text '{text_received}' did not match any known main menu button for lang '{lang}'.")
            await message.reply_text(get_btn_text("unknown_command", "Unknown cmd."), reply_markup=reply_markup_for_lang(lang, context))
        return # Crucial: Return after handling NONE state

    elif current_step_name == UserSteps.AWAITING_REGION.name:
        log_info(f"[TextMsg AWAITING_REGION] Received region: '{text_received}'. All known regions: {handler_data.all_known_regions}")
        if text_received not in handler_data.all_known_regions:
            log_warning(f"Invalid region '{text_received}' selected by user {user_id_str}.")
            await message.reply_text(get_btn_text("error_invalid_region_selection", "Invalid region."), reply_markup=get_region_keyboard(lang, context))
            return # Stay in this step
        context.user_data[USER_DATA_SELECTED_REGION] = text_received
        # Use get_btn_text for the prompt as well
        prompt_text = get_btn_text("enter_street_for_add", "Street to add:")
        log_info(f"[TextMsg AWAITING_REGION] Prompting for street in lang '{lang}': '{prompt_text}'") # Log the prompt
        await message.reply_text(prompt_text,
                                 reply_markup=ReplyKeyboardMarkup([[get_btn_text("cancel", "❌ Cancel")]], resize_keyboard=True, one_time_keyboard=True))
        context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_STREET.name
        log_info(f"[TextMsg AWAITING_REGION] Step changed to AWAITING_STREET for user {user_id_str}.")
        return 

    elif current_step_name == UserSteps.AWAITING_STREET.name:
        street_input = text_received # Already stripped
        context.user_data[USER_DATA_RAW_STREET_INPUT] = street_input
        selected_region = context.user_data.get(USER_DATA_SELECTED_REGION)

        if not selected_region:
            log_error(f"User {user_id_str} in AWAITING_STREET but no region selected. Resetting.")
            await handle_cancel_action(update, context) # Should reset to main menu
            return

        ai_is_ready = await is_ai_available() # Removed context argument if not needed by your is_ai_available
        
        if ai_is_ready:
            await message.reply_text(get_btn_text("address_clarifying_ai", "Checking... 🤖"), reply_markup=ReplyKeyboardMarkup([[]], remove_keyboard=True)) # remove_keyboard
            # Pass context if your clarify_address_ai needs it, otherwise remove
            clarified_data = await clarify_address_ai(street_input, region_street_map={"region_name": selected_region}) # Adjusted call based on ai_engine

            buttons_confirm = []
            # Check if 'street_identified' exists and is not None or empty
            if clarified_data and not clarified_data.get("error") and clarified_data.get("street_identified"):
                # Suggested street from AI
                suggested_street_full = clarified_data.get("street_identified", "").strip()
                # Cache the AI result, ensuring we have what we need
                context.user_data[USER_DATA_CLARIFIED_ADDRESS_CACHE] = {
                    "region_identified": clarified_data.get("region_identified", selected_region), # Use AI region or original
                    "street_identified": suggested_street_full,
                    "original_input": street_input # Keep original street input
                }

                prompt_msg = get_btn_text("ai_clarify_prompt", "AI: '{sug_addr}'. Correct?").format(
                    sug_addr=f"{context.user_data[USER_DATA_CLARIFIED_ADDRESS_CACHE]['region_identified']}, {suggested_street_full}"
                )
                buttons_confirm = [
                    [InlineKeyboardButton(get_btn_text("yes", "Yes"), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}yes_ai")],
                    [InlineKeyboardButton(get_btn_text("no_save_original", "No, save mine"), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}original_input")],
                    [InlineKeyboardButton(get_btn_text("cancel", "❌ Cancel"), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}cancel_add")]
                ]
            else: # AI failed or no street identified
                error_comment = clarified_data.get("error_comment", "AI could not process.") if clarified_data else "AI error."
                # Ensure street_input (original) is part of the cache for "original_input" callback
                context.user_data[USER_DATA_CLARIFIED_ADDRESS_CACHE] = {
                     "original_input": street_input,
                     "region_identified": selected_region # Keep original region
                }
                prompt_msg = get_btn_text("ai_clarify_failed_save_original_prompt", "AI: {comment}. Save '{addr}' as is?").format(
                    comment=error_comment, addr=f"{selected_region}, {street_input}"
                )
                buttons_confirm = [
                    [InlineKeyboardButton(get_btn_text("confirm_ai_save_original", "Save as is"), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}original_input")],
                    [InlineKeyboardButton(get_btn_text("cancel", "❌ Cancel"), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}cancel_add")]
                ]
            await message.reply_text(prompt_msg, reply_markup=InlineKeyboardMarkup(buttons_confirm))
            context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_STREET_CONFIRMATION.name
        else: # AI not available
            user_addrs = handler_data.user_addresses.setdefault(user_id, [])
            norm_street = normalize_address_component(street_input)
            norm_region = normalize_address_component(selected_region)
            is_duplicate = any(normalize_address_component(addr["street"]) == norm_street and 
                               normalize_address_component(addr["region"]) == norm_region for addr in user_addrs)
            if is_duplicate:
                await message.reply_text(get_btn_text("address_exists", "Address exists.").format(address=f"{selected_region}, {street_input}"))
            else:
                user_addrs.append({"region": selected_region, "street": street_input})
                await save_tracked_data_async(context)
                await message.reply_text(get_btn_text("address_added", "Address added.").format(address=f"{selected_region}, {street_input}"))
            await reply_with_main_menu(update, context, "menu_returned") # Resets step to NONE
        return

    elif current_step_name == UserSteps.AWAITING_ADDRESS_TO_REMOVE.name:
        # This needs more robust UI, e.g., listing addresses with inline buttons to select.
        # For now, simple text match:
        address_to_remove_text = text_received
        user_addrs = handler_data.user_addresses.get(user_id, [])
        found_and_removed = False
        if user_addrs:
            # Attempt to find by exact street match (simple for now)
            # This is weak, as region isn't considered.
            # A better way is to list them and let user choose by index or callback.
            original_len = len(user_addrs)
            user_addrs[:] = [addr for addr in user_addrs if addr["street"].strip().lower() != address_to_remove_text.lower()]
            if len(user_addrs) < original_len:
                found_and_removed = True
                await save_tracked_data_async(context)
                await message.reply_text(get_btn_text("address_removed", "Address '{address}' removed.").format(address=address_to_remove_text))
            else:
                await message.reply_text(get_btn_text("address_not_found_to_remove", "Address '{address}' not found.").format(address=address_to_remove_text))
        else:
            await message.reply_text(get_btn_text("no_addresses", "No addresses to remove."))
        
        await reply_with_main_menu(update, context, "menu_returned") # Go back to main menu
        return

    elif current_step_name == UserSteps.AWAITING_CLEAR_ALL_CONFIRMATION.name:
        yes_text = get_btn_text("yes", "Yes")
        no_text = get_btn_text("no", "No") # "No" should act like cancel here

        if text_received == yes_text:
            handler_data.user_addresses.pop(user_id, None)
            handler_data.user_notified.pop(user_id, None) # Clear notified history for this user too
            await save_tracked_data_async(context)
            await reply_with_main_menu(update, context, "all_addresses_cleared", "All addresses cleared.")
        elif text_received == no_text:
            await handle_cancel_action(update, context) # Treat "No" as cancel
        else: # Any other text while awaiting confirmation
            await message.reply_text(
                get_btn_text("please_confirm_yes_no", "Please confirm (Yes/No)."),
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton(yes_text), KeyboardButton(no_text)]],
                                                 resize_keyboard=True, one_time_keyboard=True)
            )
            # Stay in this step, so no return here unless you want to exit the handler
        return


    elif current_step_name == UserSteps.AWAITING_REGION_FOR_CHECK.name:
        log_info(f"[TextMsg AWAITING_REGION_FOR_CHECK] Received region: '{text_received}'.")
        if text_received not in handler_data.all_known_regions:
            log_warning(f"Invalid region '{text_received}' selected for check by user {user_id_str}.")
            await message.reply_text(get_btn_text("error_invalid_region_selection", "Invalid region."), reply_markup=get_region_keyboard(lang, context))
            return # Stay in this step
        context.user_data[USER_DATA_SELECTED_REGION_FOR_CHECK] = text_received
        prompt_text = get_btn_text("enter_street_for_check", "Street to check:")
        log_info(f"[TextMsg AWAITING_REGION_FOR_CHECK] Prompting for street in lang '{lang}': '{prompt_text}'")
        await message.reply_text(prompt_text,
                                 reply_markup=ReplyKeyboardMarkup([[get_btn_text("cancel", "❌ Cancel")]], resize_keyboard=True, one_time_keyboard=True))
        context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_STREET_FOR_CHECK.name
        log_info(f"[TextMsg AWAITING_REGION_FOR_CHECK] Step changed to AWAITING_STREET_FOR_CHECK for user {user_id_str}.")
        return

    elif current_step_name == UserSteps.AWAITING_STREET_FOR_CHECK.name:
        street_to_check = text_received # Already stripped
        region_to_check = context.user_data.get(USER_DATA_SELECTED_REGION_FOR_CHECK)
        if not region_to_check:
            log_error(f"User {user_id_str} in AWAITING_STREET_FOR_CHECK but no region selected. Resetting.")
            await handle_cancel_action(update, context)
            return

        await message.reply_text(get_btn_text("checking_now", "Checking..."), reply_markup=ReplyKeyboardMarkup([[]], remove_keyboard=True))
        active_shutdowns_details, shutdown_message_template = await is_shutdown_for_address_now_v2(street_to_check, region_to_check, context)
        
        # Ensure address_display placeholder is correctly substituted
        address_display_text = f"{escape_markdown_v2(region_to_check)}, {escape_markdown_v2(street_to_check)}"
        final_message = shutdown_message_template.replace("{address_display}", address_display_text)
        
        await message.reply_text(final_message, reply_markup=reply_markup_for_lang(lang, context), parse_mode=ParseMode.MARKDOWN_V2)
        
        context.user_data.pop(USER_DATA_SELECTED_REGION_FOR_CHECK, None)
        context.user_data[USER_DATA_STEP] = UserSteps.NONE.name # Reset step
        log_info(f"Check address completed for {user_id_str}. Step reset to NONE.")
        return

    elif current_step_name == UserSteps.AWAITING_FREQUENCY_CHOICE.name:
        # Cancel should be handled by the top-level cancel check.
        # If it's not "Cancel", then it's a frequency choice.
        await handle_frequency_choice_text(update, context)
        return 

    elif current_step_name == UserSteps.AWAITING_SILENT_START_TIME.name or \
         current_step_name == UserSteps.AWAITING_SILENT_END_TIME.name:
        # Cancel should be handled by the top-level cancel check.
        await handle_silent_time_input(update, context)
        return

    # Fallback for unhandled steps or text in callback-only steps
    else:
        is_callback_only_step = current_step_name in [
            UserSteps.AWAITING_LANGUAGE_CHOICE.name,        # Expects CallbackQuery
            UserSteps.AWAITING_STREET_CONFIRMATION.name,  # Expects CallbackQuery
            UserSteps.AWAITING_SUBSCRIPTION_CHOICE.name,  # Expects CallbackQuery
            # UserSteps.AWAITING_FAQ_CHOICE.name, # If you add this
            # UserSteps.AWAITING_SUPPORT_MESSAGE.name # If you add this
        ]

        if is_callback_only_step:
            log_info(f"Received text '{text_received}' during a callback-only step {current_step_name} for user {user_id_str}. Informing user.")
            # You might want to inform the user to use buttons or simply ignore.
            # For now, let's send to main menu if text is received in such a state.
            await message.reply_text(get_btn_text("use_buttons_prompt", "Please use the provided buttons or commands."), reply_markup=reply_markup_for_lang(lang,context))
            context.user_data[USER_DATA_STEP] = UserSteps.NONE.name # Reset to main menu
        else:
            log_warning(f"Unhandled text input '{text_received}' for step {current_step_name} (user: {user_id_str}). Resetting to main menu.")
            await reply_with_main_menu(update, context, "unknown_command", "Unknown state. Menu.")
        # No return needed, as it's the end of the function.

# --- Функции для установки частоты (интегрированы) ---
@handler_prechecks
async def set_frequency_command_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_lang_for_handler(context, user.id)
    handler_data = get_bot_data(context)
    user_id_str = str(user.id)
    
    user_s = handler_data.user_settings.get(user_id_str, {})
    user_current_tier_name = user_s.get("current_tier", "Free")

    if user.id in handler_data.config.admin_user_ids:  # Admin override
        user_current_tier_name = TIER_ORDER[-1]  # Max tier, e.g., "Ultra"

    await update.message.reply_text(
        handler_data.translations.get("set_frequency_prompt", {}).get(lang, "Choose frequency:"),
        reply_markup=get_frequency_reply_keyboard(lang, user_current_tier_name, context)
    )
    
    context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_FREQUENCY_CHOICE.name

def get_frequency_reply_keyboard(
    lang: str,
    user_tier_name: str,
    context: ContextTypes.DEFAULT_TYPE,
    user_is_admin: bool = False
) -> ReplyKeyboardMarkup:
    handler_data = get_bot_data(context)
    keyboard_buttons = []

    if user_is_admin:
        user_tier_index = len(TIER_ORDER) - 1  # Максимальный доступ
    else:
        user_tier_index = TIER_ORDER.index(user_tier_name) if user_tier_name in TIER_ORDER else 0

    for _, option_details in handler_data.frequency_options.items():
        required_tier_for_option = option_details.get("tier", "Free")
        try:
            required_tier_index = TIER_ORDER.index(required_tier_for_option)
            if user_tier_index >= required_tier_index:
                keyboard_buttons.append(KeyboardButton(option_details.get(lang, "N/A Option")))
        except ValueError:
            continue  # Пропускаем, если tier не найден

    # Группируем кнопки по 2 в ряд
    grouped_keyboard = [keyboard_buttons[i:i + 2] for i in range(0, len(keyboard_buttons), 2)]
    grouped_keyboard.append([
        KeyboardButton(handler_data.translations.get("cancel", {}).get(lang, "Cancel"))
    ])
    
    return ReplyKeyboardMarkup(grouped_keyboard, resize_keyboard=True, one_time_keyboard=True)

@handler_prechecks  # Ensure lang is set
async def handle_frequency_choice_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id_str = str(user.id)
    lang = get_lang_for_handler(context, user.id)
    handler_data = get_bot_data(context)

    if not update.message or not update.message.text:
        await reply_with_main_menu(update, context, "error_generic", "An error occurred.")
        return

    text_received = update.message.text.strip()
    log_info(f"[FreqChoice] User: {user_id_str}, Lang: {lang}, Received Text: '{text_received}' for frequency choice.")

    selected_option_details = None
    selected_option_key_found = None

    for key, option_details_from_map in handler_data.frequency_options.items():
        expected_text_for_option = option_details_from_map.get(lang)
        log_info(f"[FreqChoice] Comparing: Received='{text_received}', Expected='{expected_text_for_option}' for option key '{key}'")
        if text_received == expected_text_for_option:
            selected_option_details = option_details_from_map
            selected_option_key_found = key
            break

    log_info(f"[FreqChoice] Matched option key after loop: {selected_option_key_found}, Details: {selected_option_details}")

    if selected_option_details:
        current_s = handler_data.user_settings.get(user_id_str, {}).copy()
        user_current_tier_name = current_s.get("current_tier", "Free")

        user_is_admin = user.id in handler_data.config.admin_user_ids
        if user_is_admin:
            user_current_tier_name = TIER_ORDER[-1]  # Admins get max tier

        can_select = True  # Default to True for admins

        if not user_is_admin:
            user_tier_index = TIER_ORDER.index(user_current_tier_name) if user_current_tier_name in TIER_ORDER else 0
            required_tier_for_freq = selected_option_details.get("tier", "Free")
            required_tier_index = TIER_ORDER.index(required_tier_for_freq) if required_tier_for_freq in TIER_ORDER else 0
            can_select = user_tier_index >= required_tier_index

        if not can_select:
            log_warning(f"[FreqChoice] User {user_id_str} (Tier: {user_current_tier_name}) tried to select freq for tier {required_tier_for_freq} but is not allowed.")
            await update.message.reply_text(handler_data.translations.get("premium_required_for_frequency", {}).get(lang, "Higher tier required."))
            await update.message.reply_text(
                handler_data.translations.get("set_frequency_prompt", {}).get(lang, "Choose frequency:"),
                reply_markup=get_frequency_reply_keyboard(lang, user_current_tier_name, context, user_is_admin)
            )
        else:
            current_s["frequency"] = selected_option_details["interval"]
            handler_data.user_settings[user_id_str] = current_s
            await save_user_settings_async(context)
            log_info(f"[FreqChoice] User {user_id_str} set frequency to {selected_option_details['interval']}s (Option key: {selected_option_key_found}).")
            await reply_with_main_menu(update, context, "frequency_set", "Frequency set!")
    else:
        log_warning(f"[FreqChoice] Invalid frequency choice '{text_received}' by user {user_id_str} with lang '{lang}'.")
        user_s = handler_data.user_settings.get(user_id_str, {})
        user_current_tier_name = user_s.get("current_tier", "Free")
        user_is_admin = user.id in handler_data.config.admin_user_ids
        if user_is_admin:
            user_current_tier_name = TIER_ORDER[-1]
        await update.message.reply_text(
            handler_data.translations.get("invalid_frequency_option", {}).get(lang, "Invalid choice. Please select from the list or press 'Cancel'."),
            reply_markup=get_frequency_reply_keyboard(lang, user_current_tier_name, context, user_is_admin)
        )


# --- ПЕРИОДИЧЕСКИЕ ЗАДАЧИ ---
async def periodic_site_check_job(context: ContextTypes.DEFAULT_TYPE):
    handler_data = get_bot_data(context)
    if handler_data.bot_status.get("is_maintenance"):
        log_info("Режим обслуживания, периодическая проверка пропускается."); return

    now = timestamp()
    user_ids_to_check = list(handler_data.user_addresses.keys()) # Ключи user_addresses - int
    log_info(f"Periodic check for {len(user_ids_to_check)} users with addresses.")
    active_checks = 0

    for user_id_int in user_ids_to_check:
        user_id_str = str(user_id_int)
        current_user_s = handler_data.user_settings.get(user_id_str, {})
        
        frequency_seconds: int
        if user_id_int in handler_data.config.admin_user_ids: # Админская частота
            frequency_seconds = 60
        else:
            current_tier = current_user_s.get("current_tier", "Free")
            default_freq_for_tier = handler_data.premium_tiers.get(current_tier, {}).get("interval", 21600)
            frequency_seconds = current_user_s.get("frequency", default_freq_for_tier)

        if last_check_time.get(user_id_int, 0) + frequency_seconds <= now:
            log_info(f"Запуск проверки для {user_id_str} (частота: {frequency_seconds}s)")
            try:
                await check_site_for_user(user_id_int, context)
                last_check_time[user_id_int] = now; active_checks +=1
            except Exception as e: log_error(f"Ошибка проверки для {user_id_str}: {e}", exc_info=True)
    
    log_info(f"Periodic check done. Active: {active_checks} / {len(user_ids_to_check)} eligible.")


# In smart_bot.py
async def handle_address_confirmation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 

    user_id = query.from_user.id
    lang = get_lang_for_handler(context, user_id)
    handler_data = get_bot_data(context)
    
    # Ensure USER_DATA_CLARIFIED_ADDRESS_CACHE and USER_DATA_SELECTED_REGION exist
    clarified_cache = context.user_data.get(USER_DATA_CLARIFIED_ADDRESS_CACHE)
    selected_region_for_add = context.user_data.get(USER_DATA_SELECTED_REGION) # This was from AWAITING_REGION step

    if not clarified_cache or not selected_region_for_add:
        log_error(f"Missing address confirmation data for user {user_id}. Cache: {clarified_cache}, Region: {selected_region_for_add}")
        await query.edit_message_text(
            handler_data.translations.get("error_missing_data", {}).get(lang, "Error: critical data missing for address confirmation."),
        ) # No main menu reply here, user might need to restart flow.
        context.user_data[USER_DATA_STEP] = UserSteps.NONE.name # Reset step
        return # Early exit

    # Extract action from callback data
    action = query.data[len(CALLBACK_PREFIX_ADDRESS_CONFIRM):]
    log_info(f"Address confirmation callback: User {user_id}, Action: {action}, Cache: {clarified_cache}, Region: {selected_region_for_add}")

    street_to_save = None
    region_to_save = selected_region_for_add # Default to user selected region

    if action == "yes_ai":
        # User confirmed AI's suggestion
        if clarified_cache.get("street_identified"):
            street_to_save = clarified_cache["street_identified"]
            # Optionally use AI's region if it's different and considered more accurate
            if clarified_cache.get("region_identified"):
                region_to_save = clarified_cache["region_identified"]
            log_info(f"User {user_id} confirmed AI address: Region='{region_to_save}', Street='{street_to_save}'")
        else:
            log_warning(f"User {user_id} pressed 'yes_ai' but no street_identified in cache.")
            # Fallback to original input or error
            street_to_save = clarified_cache.get("original_input")
            region_to_save = selected_region_for_add # Revert to originally selected region for safety
            if not street_to_save:
                 await query.edit_message_text(handler_data.translations.get("error_ai_cache_missing", {}).get(lang, "Error: AI data incomplete."))
                 context.user_data[USER_DATA_STEP] = UserSteps.NONE.name
                 return


    elif action == "original_input":
        # User wants to save their original input
        street_to_save = clarified_cache.get("original_input")
        region_to_save = selected_region_for_add # Or use clarified_cache.get("region_identified", selected_region_for_add)
        log_info(f"User {user_id} chose original address: Region='{region_to_save}', Street='{street_to_save}'")
        if not street_to_save: # Should always exist if flow is correct
            log_error(f"User {user_id} pressed 'original_input' but no original_input in cache.")
            await query.edit_message_text(handler_data.translations.get("error_missing_data", {}).get(lang, "Error: Original input missing."))
            context.user_data[USER_DATA_STEP] = UserSteps.NONE.name
            return

    elif action == "cancel_add":
        log_info(f"User {user_id} cancelled address addition via AI confirmation.")
        # Edit message first, then send main menu with reply_with_main_menu
        await query.edit_message_text(
            handler_data.translations.get("action_cancelled", {}).get(lang, "Action cancelled.")
        )
        # Send a new message with the main menu
        await reply_with_main_menu(update, context, "menu_returned", default_text="Main menu.") # reply_with_main_menu handles step reset
        return # Important to return as reply_with_main_menu sends a new message

    else:
        log_warning(f"Unknown address confirmation action: {action} for user {user_id}")
        await query.edit_message_text(
            handler_data.translations.get("error_generic", {}).get(lang, "Error: Unknown action.")
        )
        context.user_data[USER_DATA_STEP] = UserSteps.NONE.name # Reset step
        return

    # Proceed to save if street_to_save is determined
    if street_to_save and region_to_save:
        user_addrs = handler_data.user_addresses.setdefault(user_id, [])
        norm_street = normalize_address_component(street_to_save)
        norm_region = normalize_address_component(region_to_save)
        
        is_duplicate = any(
            normalize_address_component(addr["street"]) == norm_street and
            normalize_address_component(addr["region"]) == norm_region
            for addr in user_addrs
        )

        if is_duplicate:
            msg_text = handler_data.translations.get("address_exists", {}).get(lang, "Address already exists.").format(address=f"{region_to_save}, {street_to_save}")
        else:
            user_addrs.append({"region": region_to_save, "street": street_to_save})
            await save_tracked_data_async(context)
            msg_text = handler_data.translations.get("address_added", {}).get(lang, "Address added.").format(address=f"{region_to_save}, {street_to_save}")
        
        await query.edit_message_text(msg_text)
        # Send a new message with the main menu AFTER editing the current one
        await reply_with_main_menu(update, context, "menu_returned", default_text="Main menu.")
    else:
        # This case should ideally be caught earlier if street_to_save wasn't set.
        log_error(f"Address confirmation for user {user_id} resulted in no street_to_save. Action: {action}")
        await query.edit_message_text(handler_data.translations.get("error_final_street_empty", {}).get(lang, "Failed to determine street to save."))
        await reply_with_main_menu(update, context, "menu_returned", default_text="Main menu.")


    # Clean up temporary data from context.user_data
    context.user_data.pop(USER_DATA_CLARIFIED_ADDRESS_CACHE, None)
    # USER_DATA_SELECTED_REGION is cleared by reply_with_main_menu or when the flow naturally ends.
    # No, reply_with_main_menu was modified to clear specific keys. Let's ensure USER_DATA_SELECTED_REGION is cleared too.
    # It's better if reply_with_main_menu clears all temporary operational keys.

    # The step is reset by reply_with_main_menu or set specifically here if needed.
    # Since reply_with_main_menu is called, step will be NONE.


# --- ХУКИ ИНИЦИАЛИЗАЦИИ И ЗАВЕРШЕНИЯ ---
async def post_init_hook(application: Application):
    log_info("Bot post_init_hook: Загрузка данных...")
    # Инициализация ссылок в bot_data на глобальные словари (если они еще не там)
    # Это более явный способ убедиться, что bot_data содержит нужные ссылки
    # Лучше инициализировать их в main() при создании initial_bot_shared_data
    
    # Загрузка данных
    await load_user_settings_async(application)
    await load_tracked_data_async(application)
    await load_bot_general_status_async(application)

    # Инициализация all_known_regions_flat в bot_data
    application.bot_data.setdefault("all_known_regions_flat_ref", set(regions_hy + regions_ru + regions_en))

    await set_bot_commands_async(application)
    log_info("Данные загружены, команды установлены.")

async def post_shutdown_hook(application: Application):
    log_info("Bot post_shutdown_hook: Сохранение данных...")
    await save_user_settings_async(application)
    await save_tracked_data_async(application)
    await save_bot_general_status_async(application)
    log_info("Данные сохранены перед выключением.")


async def set_bot_commands_async(application: Application):
    # ... (реализация как в предыдущем ответе, используя get_bot_data(application) для translations)
    # Важно: get_bot_data ожидает ContextTypes.DEFAULT_TYPE. Для application нужно напрямую application.bot_data
    translations_data = application.bot_data.get("translations_ref", translations)
    lang_for_cmd_desc = "ru" # Язык по умолчанию для описания команд
    commands = [
        BotCommand("start", translations_data.get("command_start_description", {}).get(lang_for_cmd_desc, "Старт")),
        BotCommand("language", translations_data.get("command_language_description", {}).get(lang_for_cmd_desc, "Сменить язык")),
        BotCommand("myaddresses", translations_data.get("command_myaddresses_description", {}).get(lang_for_cmd_desc, "Мои адреса")),
        BotCommand("sound", translations_data.get("command_sound_description", {}).get(lang_for_cmd_desc, "Настройки звука")),
        BotCommand("stats", translations_data.get("command_stats_description", {}).get(lang_for_cmd_desc, "Статистика")),
        BotCommand("help", translations_data.get("command_help_description", {}).get(lang_for_cmd_desc, "Помощь")),
        # Команды, управляемые кнопками, можно не добавлять в меню команд
    ]
    admin_commands = [
        BotCommand("maintenance_on", "Вкл. обслуживание (админ)"),
        BotCommand("maintenance_off", "Выкл. обслуживание (админ)"),
    ]
    try:
        await application.bot.set_my_commands(commands) # Общие команды
        bot_cfg: Optional[BotConfig] = application.bot_data.get("config_ref")
        if bot_cfg: # Установка админских команд для админов
            for admin_id in bot_cfg.admin_user_ids:
                try: await application.bot.set_my_commands(commands + admin_commands, scope={"type": "chat", "chat_id": admin_id})
                except Exception as e_admin_cmd: log_error(f"Ошибка установки админ-команд для {admin_id}: {e_admin_cmd}")

        log_info("Команды бота установлены.")

    except Exception as e: log_error(f"Ошибка установки команд бота: {e}", exc_info=True)

# --- ТОЧКА ВХОДА ---
def main():
    log_info(f"ЗАПУСК БОТА CheckSiteUpdateBot v... (версия {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    log_info(f"Log Level: {config.log_level}, Admins: {config.admin_user_ids}")
    log_info(f"AI Model (if local): {AI_MODEL_PATH if not os.getenv('USE_HUGGINGFACE_API') else 'HuggingFace API'}")

    persistence_filepath = config.backup_dir / "bot_session_data.pickle"
    ptb_persistence = PicklePersistence(filepath=persistence_filepath)

    initial_bot_shared_data = {
        "user_settings_ref": {}, # Будет заполнено в post_init_hook
        "user_addresses_ref": {},
        "user_notified_headers_ref": {},
        "bot_general_status_ref": {"is_maintenance": False, "maintenance_message": ""}, # Начальное значение
        "translations_ref": translations, 
        "config_ref": config,
        "premium_tiers_ref": premium_tiers,
        "frequency_options_ref": FREQUENCY_OPTIONS,
        "all_known_regions_flat_ref": set(regions_hy + regions_ru + regions_en) # Инициализация здесь
    }

    application_builder = ApplicationBuilder().token(config.telegram_token)
    application_builder.persistence(ptb_persistence)
    application_builder.post_init(post_init_hook)
    application_builder.post_shutdown(post_shutdown_hook)
    application = application_builder.build()
    log_info("Application built.")
    application.bot_data.update(initial_bot_shared_data)

    # Регистрация обработчиков
    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("language", change_language_command))
    application.add_handler(CommandHandler("myaddresses", address_list_command))
    application.add_handler(CommandHandler("stats", show_statistics_command))
    application.add_handler(CommandHandler("help", show_help_command)) # TODO: Реализовать show_help_command
    application.add_handler(CommandHandler("sound", sound_settings_command)) 
    application.add_handler(CommandHandler("set_frequency", set_frequency_command_entry))
    application.add_handler(CommandHandler("maintenance_on", maintenance_on_command))
    application.add_handler(CommandHandler("maintenance_off", maintenance_off_command))

    application.add_handler(CallbackQueryHandler(handle_language_callback, pattern=f"^{CALLBACK_PREFIX_LANG}"))
    application.add_handler(CallbackQueryHandler(handle_subscription_callback, pattern=f"^{CALLBACK_PREFIX_SUBSCRIBE}"))
    application.add_handler(CallbackQueryHandler(handle_address_confirmation_callback, pattern=f"^{CALLBACK_PREFIX_ADDRESS_CONFIRM}")) #TODO: handle_address_confirmation_callback
    application.add_handler(CallbackQueryHandler(handle_sound_settings_callback, pattern=f"^{CALLBACK_PREFIX_SOUND}")) # TODO: application.add_handler(CallbackQueryHandler(handle_help_action_callback, pattern=f"^{CALLBACK_PREFIX_HELP}"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message_new_logic))
    
    job_q: Optional[JobQueue] = application.job_queue
    if job_q:
        job_interval = int(os.getenv("JOB_QUEUE_INTERVAL_SECONDS", "300"))
        first_delay = int(os.getenv("JOB_QUEUE_FIRST_DELAY_SECONDS", "15"))
        job_q.run_repeating(periodic_site_check_job, interval=job_interval, first=first_delay, name="site_check")
        log_info(f"Job 'site_check' scheduled every {job_interval}s, first in {first_delay}s.")
    else: log_error("JobQueue is not available.")

    log_info("Бот начал опрос...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    log_info("Бот остановлен.")

if __name__ == "__main__":
    main()

# <3
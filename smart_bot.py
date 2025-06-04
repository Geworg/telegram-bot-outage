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
from translations import translations # Assuming this is your primary translations source
# Parsers are assumed to be correctly imported and functional
from parse_water import parse_all_water_announcements_async
from parse_gas import parse_all_gas_announcements_async
from parse_electric import parse_all_electric_announcements_async
from ai_engine import clarify_address_ai, is_ai_available, MODEL_PATH as AI_MODEL_PATH # Ensure these are correctly used

import aiofiles
import aiofiles.os as aios
from pathlib import Path

if os.getenv("MAINTENANCE_MODE", "false").lower() == "true":
    print("🚧 Приложение в режиме обслуживания. Остановка.")
    sys.exit(1)

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
    # Кнопка "Изменить язык" удалена, "Настройки звука" добавлена
    return [
        [KeyboardButton(handler_data.translations.get("add_address_btn", {}).get(lang, "➕ Add Address")),
         KeyboardButton(handler_data.translations.get("remove_address_btn", {}).get(lang, "➖ Remove Address"))],
        [KeyboardButton(handler_data.translations.get("show_addresses_btn", {}).get(lang, "📋 Show Addresses")),
         KeyboardButton(handler_data.translations.get("clear_all_btn", {}).get(lang, "🧹 Clear All"))],
        [KeyboardButton(handler_data.translations.get("check_address_btn", {}).get(lang, "🔍 Check Address")),
         KeyboardButton(handler_data.translations.get("sound_settings_btn", {}).get(lang, "🎵 Sound Settings"))],
        [KeyboardButton(handler_data.translations.get("subscription_btn", {}).get(lang, "⭐ Subscription")),
         KeyboardButton(handler_data.translations.get("statistics_btn", {}).get(lang, "📊 Statistics"))],
        [KeyboardButton(handler_data.translations.get("set_frequency_btn", {}).get(lang, "⏱️ Set Frequency")),
         KeyboardButton(handler_data.translations.get("help_btn", {}).get(lang, "❓ Help"))]
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

        # 3. Установка языка в context.user_data для текущей сессии, если его там нет
        if USER_DATA_LANG not in context.user_data:
            lang_from_settings = handler_data.user_settings.get(user_id_str, {}).get("lang")
            if lang_from_settings:
                context.user_data[USER_DATA_LANG] = lang_from_settings
            # Если языка нет ни в user_data, ни в settings, start_command должен предложить выбор.
            # Для других команд, если язык не установлен, будет использован 'ru' по умолчанию при получении из handler_data.
        
        # 4. Убедимся, что текущий язык есть в context.user_data для последующих вызовов handler_data.translations
        # Это делается внутри get_lang_for_handler(context)

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
    """Отправляет переведенное сообщение и клавиатуру главного меню, сбрасывает шаг."""
    lang = get_lang_for_handler(context, update.effective_user.id if update.effective_user else None)
    handler_data = get_bot_data(context)
    message_text = handler_data.translations.get(text_key, {}).get(lang, default_text)
    
    if update.message:
        await update.message.reply_text(message_text, reply_markup=reply_markup_for_lang(lang, context))
    elif update.callback_query and update.callback_query.message: # Если это коллбэк, отправляем новое сообщение
        await update.callback_query.message.reply_text(message_text, reply_markup=reply_markup_for_lang(lang, context))

    context.user_data[USER_DATA_STEP] = UserSteps.NONE.name
    # Очистка временных данных
    for key_to_pop in [USER_DATA_SELECTED_REGION, USER_DATA_SELECTED_REGION_FOR_CHECK,
                       USER_DATA_RAW_STREET_INPUT, USER_DATA_CLARIFIED_ADDRESS_CACHE,
                       USER_DATA_TEMP_SOUND_SETTINGS]:
        context.user_data.pop(key_to_pop, None)

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
    data = query.data if query and query.data else "<no data>"
    log_info(f"[DBG] handle_language_callback: callback_data = «{data}»")
    # await query.answer()
    # query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id_str = str(user.id)
    handler_data = get_bot_data(context)
    
    try:
        selected_lang_code = query.data.split(CALLBACK_PREFIX_LANG)[1]
        if selected_lang_code not in languages.values():
            await query.edit_message_text(text="Error: Invalid language code.")
            return

        context.user_data[USER_DATA_LANG] = selected_lang_code # Обновляем язык в текущей сессии
        current_s = handler_data.user_settings.get(user_id_str, {})
        current_s["lang"] = selected_lang_code
        if "notification_sound_enabled" not in current_s: # Инициализация настроек при первом выборе языка
            current_s.update({
                "notification_sound_enabled": True, "silent_mode_enabled": False,
                "silent_mode_start_time": "23:00", "silent_mode_end_time": "07:00",
                "timezone": handler_data.config.default_user_timezone
            })
        handler_data.user_settings[user_id_str] = current_s
        await save_user_settings_async(context)
        
        await query.delete_message()
        await reply_with_main_menu(update, context, "language_set", "Language set!")
        log_info(f"User {user_id_str} selected language: {selected_lang_code}.")

    except Exception as e:
        log_error(f"Error in handle_language_callback for {user_id_str}, data '{query.data}': {e}", exc_info=True)
        await query.edit_message_text(text="Error setting language. Try /start.")


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


@handler_prechecks
async def handle_text_message_new_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip() if update.message else "<no text>"
    log_info(f"[DBG] Входящий текст: «{text}», текущий шаг: {context.user_data.get(USER_DATA_STEP)}")
    user = update.effective_user # Гарантированно есть
    message = update.message
    user_id = user.id; user_id_str = str(user.id)
    lang = get_lang_for_handler(context, user_id) # Язык уже должен быть в context.user_data
    handler_data = get_bot_data(context)
    
    text = message.text.strip()
    if not validate_user_input(text):
        await message.reply_text(handler_data.translations.get("error_invalid_input", {}).get(lang, "Invalid input."))
        return

    current_step_name = context.user_data.get(USER_DATA_STEP, UserSteps.NONE.name)
    log_info(f"[TextMsg] User: {user_id_str}, Text: '{text}', Lang: '{lang}', Step: '{current_step_name}'")

    if text == handler_data.translations.get("cancel", {}).get(lang, "#!#CANCEL#!#"): # Используем уникальный маркер, если "Cancel" может быть обычным словом
        await handle_cancel_action(update, context)
        return

    # ---- Шаг NONE: Обработка кнопок главного меню ----
    if current_step_name == UserSteps.NONE.name:
        # Сопоставление текста кнопки с действием
        button_actions: Dict[str, Callable] = {
            handler_data.translations.get("add_address_btn", {}).get(lang, "➕ Add Address"): lambda: (
                message.reply_text(handler_data.translations.get("choose_region", {}).get(lang, "Region:"), reply_markup=get_region_keyboard(lang, context)),
                UserSteps.AWAITING_REGION.name
            ),
            handler_data.translations.get("remove_address_btn", {}).get(lang, "➖ Remove Address"): lambda: (
                message.reply_text(handler_data.translations.get("enter_address_to_remove_prompt", {}).get(lang, "Street to remove?"), # TODO: Улучшить удаление
                                 reply_markup=ReplyKeyboardMarkup([[handler_data.translations.get("cancel", {}).get(lang, "Cancel")]], resize_keyboard=True, one_time_keyboard=True)),
                UserSteps.AWAITING_ADDRESS_TO_REMOVE.name
            ) if handler_data.user_addresses.get(user_id) else (
                message.reply_text(handler_data.translations.get("no_addresses", {}).get(lang, "No addresses.")),
                UserSteps.NONE.name # Остаемся в NONE
            ),
            handler_data.translations.get("show_addresses_btn", {}).get(lang, "📋 Show Addresses"): lambda: (address_list_command(update, context), UserSteps.NONE.name), # address_list_command сам сбросит шаг
            handler_data.translations.get("clear_all_btn", {}).get(lang, "🧹 Clear All"): lambda: (
                 message.reply_text(handler_data.translations.get("confirm_clear", {}).get(lang, "Confirm clear all?"), 
                                  reply_markup=ReplyKeyboardMarkup([[KeyboardButton(handler_data.translations.get("yes", {}).get(lang, "Yes")),
                                                                     KeyboardButton(handler_data.translations.get("no", {}).get(lang, "No"))]],
                                                                    resize_keyboard=True, one_time_keyboard=True)),
                UserSteps.AWAITING_CLEAR_ALL_CONFIRMATION.name
            ) if handler_data.user_addresses.get(user_id) else (
                message.reply_text(handler_data.translations.get("no_addresses", {}).get(lang, "No addresses.")), UserSteps.NONE.name
            ),
            handler_data.translations.get("check_address_btn", {}).get(lang, "🔍 Check Address"): lambda: (check_address_command_entry(update, context), UserSteps.AWAITING_REGION_FOR_CHECK.name), # check_address_command_entry установит шаг
            handler_data.translations.get("sound_settings_btn", {}).get(lang, "🎵 Sound Settings"): lambda: (sound_settings_command(update, context), UserSteps.NONE.name), # Управляется коллбэками
            handler_data.translations.get("subscription_btn", {}).get(lang, "⭐ Subscription"): lambda: (show_subscription_options(update, context), UserSteps.AWAITING_SUBSCRIPTION_CHOICE.name),
            handler_data.translations.get("statistics_btn", {}).get(lang, "📊 Statistics"): lambda: (show_statistics_command(update, context), UserSteps.NONE.name),
            handler_data.translations.get("set_frequency_btn", {}).get(lang, "⏱️ Set Frequency"): lambda: (set_frequency_command_entry(update, context), UserSteps.AWAITING_FREQUENCY_CHOICE.name), # set_frequency_command_entry установит шаг
            handler_data.translations.get("help_btn", {}).get(lang, "❓ Help"): lambda: (show_help_command(update, context), UserSteps.NONE.name), # show_help_command - для меню помощи
        }
        
        action_result = button_actions.get(text)
        if action_result:
            # Некоторые действия - это кортежи (awaitable, next_step_name)
            # Некоторые - просто awaitable (команды, которые сами управляют меню и шагом)
            if isinstance(action_result, tuple) and len(action_result) == 2:
                awaitable_action, next_step_name = action_result
                if asyncio.iscoroutine(awaitable_action): await awaitable_action
                elif callable(awaitable_action): await awaitable_action() # Для лямбд, которые возвращают awaitable
                context.user_data[USER_DATA_STEP] = next_step_name
            elif asyncio.iscoroutine(action_result): # Если это просто awaitable (например, вызов команды)
                await action_result
            elif callable(action_result): # Если это лямбда, возвращающая awaitable или None
                res = await action_result()
                if isinstance(res, tuple) and len(res) == 2: # Если лямбда вернула (awaitable, step)
                     if asyncio.iscoroutine(res[0]): await res[0]
                     context.user_data[USER_DATA_STEP] = res[1]

            # Если шаг не был установлен или сброшен внутри действия, и это не коллбэк-ориентированное меню
            # Это условие может быть излишним, если все действия корректно управляют шагом или вызывают reply_with_main_menu
            # if context.user_data.get(USER_DATA_STEP) != UserSteps.NONE.name and \
            #    current_step_name == UserSteps.NONE.name and \
            #    text not in [handler_data.translations.get("sound_settings_btn", {}).get(lang), # Эти управляются коллбэками
            #                   handler_data.translations.get("help_btn", {}).get(lang)]:
            #     pass # Шаг должен быть установлен действием

        else: # Текст не совпал ни с одной кнопкой
            await message.reply_text(handler_data.translations.get("unknown_command", {}).get(lang, "Unknown cmd."), reply_markup=reply_markup_for_lang(lang, context))
        return

    # ---- Обработка других шагов ----
    elif current_step_name == UserSteps.AWAITING_REGION.name:
        if text not in handler_data.all_known_regions: # Используем из bot_data
            await message.reply_text(handler_data.translations.get("error_invalid_region_selection", {}).get(lang, "Invalid region."), reply_markup=get_region_keyboard(lang, context))
            return
        context.user_data[USER_DATA_SELECTED_REGION] = text
        await message.reply_text(handler_data.translations.get("enter_street_for_add", {}).get(lang, "Street to add:"),
                                 reply_markup=ReplyKeyboardMarkup([[handler_data.translations.get("cancel", {}).get(lang, "Cancel")]], resize_keyboard=True, one_time_keyboard=True))
        context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_STREET.name

    elif current_step_name == UserSteps.AWAITING_STREET.name:
        street_input = text
        context.user_data[USER_DATA_RAW_STREET_INPUT] = street_input
        selected_region = context.user_data.get(USER_DATA_SELECTED_REGION)
        if not selected_region: await handle_cancel_action(update, context); return # Ошибка, отмена
        
        ai_is_ready = await is_ai_available(context) # Передаем context
        if ai_is_ready:
            await message.reply_text(handler_data.translations.get("address_clarifying_ai", {}).get(lang, "Checking... 🤖"), reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True)) # Убираем кнопки ReplyKeyboard
            clarified_data = await clarify_address_ai(street_input, selected_region, context) # Передаем context
            
            # ... (логика кнопок подтверждения для ИИ, как в предыдущей версии) ...
            # ... она должна устанавливать UserSteps.AWAITING_STREET_CONFIRMATION.name
            # Пример кнопок для подтверждения:
            buttons_confirm = []
            if clarified_data and not clarified_data.get("error") and clarified_data.get("street_name"):
                suggested_street_parts = [clarified_data.get('street_type', ''), clarified_data.get('street_name', ''), clarified_data.get('house_number', '')]
                suggested_street_full = " ".join(filter(None, suggested_street_parts)).strip(); suggested_street_full = re.sub(r'\s+', ' ', suggested_street_full)
                context.user_data[USER_DATA_CLARIFIED_ADDRESS_CACHE] = clarified_data # Кешируем результат ИИ
                prompt_msg = handler_data.translations.get("ai_clarify_prompt", {}).get(lang, "AI: '{sug_addr}'. Correct?").format(sug_addr=f"{selected_region}, {suggested_street_full}")
                buttons_confirm = [
                    [InlineKeyboardButton(handler_data.translations.get("yes", {}).get(lang, "Yes"), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}yes")],
                    [InlineKeyboardButton(handler_data.translations.get("no_save_original", {}).get(lang, "No, save mine"), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}original")],
                    [InlineKeyboardButton(handler_data.translations.get("cancel", {}).get(lang, "Cancel"), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}cancel_add")]
                ]
            else: # ИИ не смог или ошибка
                error_comment = clarified_data.get("comment", "AI could not process.") if clarified_data else "AI error."
                prompt_msg = handler_data.translations.get("ai_clarify_failed_save_original_prompt", {}).get(lang, "AI: {comment}. Save '{addr}' as is?").format(comment=error_comment, addr=street_input)
                buttons_confirm = [
                    [InlineKeyboardButton(handler_data.translations.get("confirm_ai_save_original", {}).get(lang, "Save as is"), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}original")],
                    [InlineKeyboardButton(handler_data.translations.get("cancel", {}).get(lang, "Cancel"), callback_data=f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}cancel_add")]
                ]
            await message.reply_text(prompt_msg, reply_markup=InlineKeyboardMarkup(buttons_confirm))
            context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_STREET_CONFIRMATION.name
            return

        else: # ИИ недоступен
            # ... (логика добавления адреса как есть, проверка дубликата, сохранение) ...
            # ... затем reply_with_main_menu ...
            user_addrs = handler_data.user_addresses.setdefault(user_id, [])
            norm_street = normalize_address_component(street_input); norm_region = normalize_address_component(selected_region)
            is_duplicate = any(normalize_address_component(addr["street"]) == norm_street and 
                               normalize_address_component(addr["region"]) == norm_region for addr in user_addrs)
            if is_duplicate:
                await message.reply_text(handler_data.translations.get("address_exists", {}).get(lang, "Address exists."))
            else:
                user_addrs.append({"region": selected_region, "street": street_input})
                await save_tracked_data_async(context)
                await message.reply_text(handler_data.translations.get("address_added", {}).get(lang, "Address added."))
                # TODO: Запуск проверки для нового адреса
            await reply_with_main_menu(update, context, "menu_returned") # Сбрасываем шаг и показываем меню

    elif current_step_name == UserSteps.AWAITING_ADDRESS_TO_REMOVE.name:
        # ... (логика удаления, затем reply_with_main_menu) ...
        address_to_remove_text = text
        user_addrs = handler_data.user_addresses.get(user_id, [])
        
        # ... (логика поиска и удаления, как в предыдущих версиях)
        # ... если удалено:
        # await save_tracked_data_async(context)
        # await reply_with_main_menu(update, context, "address_removed_key", "Address removed.")
        # ... если не найдено:
        # await message.reply_text(...)
        # await reply_with_main_menu(update, context, "menu_returned")
        # Пока заглушка, т.к. логика удаления может быть сложной (выбор из списка и т.д.)
        await reply_with_main_menu(update, context, "feature_not_fully_implemented", "Removal needs UI improvement.")


    elif current_step_name == UserSteps.AWAITING_CLEAR_ALL_CONFIRMATION.name:
        if text == handler_data.translations.get("yes", {}).get(lang, "Yes"):
            handler_data.user_addresses.pop(user_id, None)
            handler_data.user_notified.pop(user_id, None)
            await save_tracked_data_async(context)
            await reply_with_main_menu(update, context, "all_addresses_cleared", "All cleared.")
        else: # "No" or other text
            await handle_cancel_action(update, context) # Отмена

    elif current_step_name == UserSteps.AWAITING_REGION_FOR_CHECK.name:
        if text not in handler_data.all_known_regions:
            await message.reply_text(handler_data.translations.get("error_invalid_region_selection", {}).get(lang, "Invalid region."), reply_markup=get_region_keyboard(lang, context))
            return
        context.user_data[USER_DATA_SELECTED_REGION_FOR_CHECK] = text
        await message.reply_text(handler_data.translations.get("enter_street_for_check", {}).get(lang, "Street to check:"),
                                 reply_markup=ReplyKeyboardMarkup([[handler_data.translations.get("cancel", {}).get(lang, "Cancel")]], resize_keyboard=True, one_time_keyboard=True))
        context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_STREET_FOR_CHECK.name
    
    elif current_step_name == UserSteps.AWAITING_STREET_FOR_CHECK.name:
        street_to_check = text
        region_to_check = context.user_data.get(USER_DATA_SELECTED_REGION_FOR_CHECK)
        if not region_to_check: await handle_cancel_action(update, context); return

        await message.reply_text(handler_data.translations.get("checking_now", {}).get(lang, "Checking..."), reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
        _, shutdown_message_template = await is_shutdown_for_address_now_v2(street_to_check, region_to_check, context)
        
        final_message = shutdown_message_template.format(address_display=f"{escape_markdown_v2(region_to_check)}, {escape_markdown_v2(street_to_check)}")
        await message.reply_text(final_message, reply_markup=reply_markup_for_lang(lang, context), parse_mode=ParseMode.MARKDOWN_V2)
        
        context.user_data.pop(USER_DATA_SELECTED_REGION_FOR_CHECK, None)
        context.user_data[USER_DATA_STEP] = UserSteps.NONE.name # Сброс шага

    elif current_step_name == UserSteps.AWAITING_FREQUENCY_CHOICE.name:
        await handle_frequency_choice_text(update, context) # Эта функция сама управляет шагом и меню

    elif current_step_name == UserSteps.AWAITING_SILENT_START_TIME.name or \
         current_step_name == UserSteps.AWAITING_SILENT_END_TIME.name:
        await handle_silent_time_input(update, context) # Эта функция сама управляет шагом и меню

    else: # Неизвестный шаг или шаг, обрабатываемый только CallbackQueryHandler
        if current_step_name not in [
            UserSteps.AWAITING_LANGUAGE_CHOICE.name, 
            UserSteps.AWAITING_STREET_CONFIRMATION.name,
            UserSteps.AWAITING_SUBSCRIPTION_CHOICE.name
            # Добавьте другие шаги, которые обрабатываются только коллбэками
        ]:
            log_warning(f"Необработанный текстовый ввод для шага {current_step_name}. Сброс.")
            await reply_with_main_menu(update, context, "unknown_command", "Unknown state. Menu.")

# --- Функции для установки частоты (интегрированы) ---
@handler_prechecks
async def set_frequency_command_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_lang_for_handler(context, user.id)
    handler_data = get_bot_data(context)
    user_id_str = str(user.id)
    user_s = handler_data.user_settings.get(user_id_str, {})
    user_current_tier_name = user_s.get("current_tier", "Free")

    await update.message.reply_text(
        handler_data.translations.get("set_frequency_prompt", {}).get(lang, "Choose frequency:"),
        reply_markup=get_frequency_reply_keyboard(lang, user_current_tier_name, context)
    )
    context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_FREQUENCY_CHOICE.name

def get_frequency_reply_keyboard(lang: str, user_tier_name: str, context: ContextTypes.DEFAULT_TYPE) -> ReplyKeyboardMarkup:
    handler_data = get_bot_data(context)
    keyboard_buttons = []
    user_tier_index = TIER_ORDER.index(user_tier_name) if user_tier_name in TIER_ORDER else 0

    for _, option_details in handler_data.frequency_options.items():
        required_tier_for_option = option_details.get("tier", "Free")
        try:
            required_tier_index = TIER_ORDER.index(required_tier_for_option)
            if user_tier_index >= required_tier_index: # Пользователь имеет доступ
                keyboard_buttons.append(KeyboardButton(option_details.get(lang, "N/A Option")))
        except ValueError: continue # Пропускаем, если tier не найден
    
    # Группируем кнопки по 2 в ряду
    grouped_keyboard = [keyboard_buttons[i:i + 2] for i in range(0, len(keyboard_buttons), 2)]
    grouped_keyboard.append([KeyboardButton(handler_data.translations.get("cancel", {}).get(lang, "Cancel"))])
    return ReplyKeyboardMarkup(grouped_keyboard, resize_keyboard=True, one_time_keyboard=True)

@handler_prechecks # Текстовый ввод частоты
async def handle_frequency_choice_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id_str = str(user.id)
    lang = get_lang_for_handler(context, user.id)
    handler_data = get_bot_data(context)
    text = update.message.text.strip()

    selected_option = None
    for key, option_details in handler_data.frequency_options.items():
        if text == option_details.get(lang):
            selected_option = option_details; break
    
    if selected_option:
        current_s = handler_data.user_settings.get(user_id_str, {})
        # Проверка доступности этой частоты для текущего тарифа пользователя (уже сделана в get_frequency_reply_keyboard)
        # но на всякий случай можно повторить
        user_current_tier_name = current_s.get("current_tier", "Free")
        user_tier_index = TIER_ORDER.index(user_current_tier_name) if user_current_tier_name in TIER_ORDER else 0
        required_tier_for_freq = selected_option.get("tier", "Free")
        can_select = True
        try:
            if user_tier_index < TIER_ORDER.index(required_tier_for_freq): can_select = False
        except ValueError: can_select = False
        
        if not can_select:
            await update.message.reply_text(handler_data.translations.get("premium_required_for_frequency", {}).get(lang, "Higher tier required."))
            await reply_with_main_menu(update, context, "menu_returned") # Возврат в меню
        else:
            current_s["frequency"] = selected_option["interval"]
            handler_data.user_settings[user_id_str] = current_s
            await save_user_settings_async(context)
            await reply_with_main_menu(update, context, "frequency_set", "Frequency set!")
    else: # Неверный выбор
        user_s = handler_data.user_settings.get(user_id_str, {})
        user_current_tier_name = user_s.get("current_tier", "Free")
        await update.message.reply_text(
            handler_data.translations.get("invalid_frequency_option", {}).get(lang, "Invalid choice."),
            reply_markup=get_frequency_reply_keyboard(lang, user_current_tier_name, context) # Показать клавиатуру снова
        ) # Шаг не сбрасываем, пользователь должен выбрать или отменить


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


async def handle_address_confirmation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик нажатий на кнопки подтверждения адреса (Да / Нет / Отмена) после
    AI-кларификации. 
    CALLBACK_PREFIX_ADDRESS_CONFIRM — префикс, который вы используете при создании callback_data,
    например: f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}yes", f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}original", f"{CALLBACK_PREFIX_ADDRESS_CONFIRM}cancel_add".
    """
    query = update.callback_query
    if not query:
        return  # на всякий случай

    await query.answer()  # закрываем «висящую» иконку ожидания

    # Получаем код после префикса, например: "yes", "original" или "cancel_add"
    data = query.data[len(CALLBACK_PREFIX_ADDRESS_CONFIRM):]

    handler_data = get_bot_data(context)  # доступ к translations, user_addresses и т. д.
    user_id = query.from_user.id
    lang = get_lang_for_handler(context, user_id)

    if data == "yes":
        # Пользователь согласился с вариантом ИИ.
        clarified = context.user_data.get(USER_DATA_CLARIFIED_ADDRESS_CACHE)
        if clarified:
            # Пример: сохраняем в handler_data.user_addresses
            region = context.user_data.get(USER_DATA_SELECTED_REGION)
            street_full = " ".join(filter(None, [
                clarified.get("street_type", ""),
                clarified.get("street_name", ""),
                clarified.get("house_number", "")
            ])).strip()

            # Проверяем дубликаты:
            user_addrs = handler_data.user_addresses.setdefault(user_id, [])
            is_duplicate = any(
                normalize_address_component(addr["street"]) == normalize_address_component(street_full) and
                normalize_address_component(addr["region"]) == normalize_address_component(region)
                for addr in user_addrs
            )
            if is_duplicate:
                await query.edit_message_text(
                    handler_data.translations.get("address_exists", {}).get(lang, "Address already exists."),
                    reply_markup=reply_markup_for_lang(lang, context)
                )
            else:
                user_addrs.append({"region": region, "street": street_full})
                await save_tracked_data_async(context)
                await query.edit_message_text(
                    handler_data.translations.get("address_added", {}).get(lang, "Address added."),
                    reply_markup=reply_markup_for_lang(lang, context)
                )
        else:
            # На всякий случай, если кэша нет
            await query.edit_message_text(
                handler_data.translations.get("error_ai_cache_missing", {}).get(lang, "Error: no AI data."),
                reply_markup=reply_markup_for_lang(lang, context)
            )

    elif data == "original":
        # Пользователь выбрал «Сохранить то, что ввёл самостоятельно» (игнорируем подсказку ИИ).
        raw_street = context.user_data.get(USER_DATA_RAW_STREET_INPUT)
        region = context.user_data.get(USER_DATA_SELECTED_REGION)
        if raw_street and region:
            user_addrs = handler_data.user_addresses.setdefault(user_id, [])
            is_duplicate = any(
                normalize_address_component(addr["street"]) == normalize_address_component(raw_street) and
                normalize_address_component(addr["region"]) == normalize_address_component(region)
                for addr in user_addrs
            )
            if is_duplicate:
                await query.edit_message_text(
                    handler_data.translations.get("address_exists", {}).get(lang, "Address already exists."),
                    reply_markup=reply_markup_for_lang(lang, context)
                )
            else:
                user_addrs.append({"region": region, "street": raw_street})
                await save_tracked_data_async(context)
                await query.edit_message_text(
                    handler_data.translations.get("address_added", {}).get(lang, "Address added."),
                    reply_markup=reply_markup_for_lang(lang, context)
                )
        else:
            await query.edit_message_text(
                handler_data.translations.get("error_missing_data", {}).get(lang, "Error: missing data."),
                reply_markup=reply_markup_for_lang(lang, context)
            )

    else:  # data == "cancel_add" или любой другой непредусмотренный
        # Возвращаемся в главное меню без сохранения
        await query.edit_message_text(
            handler_data.translations.get("action_cancelled", {}).get(lang, "Action cancelled."),
            reply_markup=reply_markup_for_lang(lang, context)
        )

    # После любой ветки сбрасываем шаг пользователя:
    context.user_data[USER_DATA_STEP] = UserSteps.NONE.name


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
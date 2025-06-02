import os
import json
import re
import asyncio
import shutil
from datetime import datetime
from time import time
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict
from difflib import SequenceMatcher
from dataclasses import dataclass
from enum import Enum, auto

from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes, PicklePersistence
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown # Для экранирования Markdown

from logger import log_info, log_error
from translations import translations
# Теперь импортируем реальные парсеры вместо заглушек
from parse_water import parse_all_water_announcements_async
from parse_gas import parse_all_gas_announcements_async
from parse_electric import parse_all_electric_announcements_async
from handlers import set_frequency_command, handle_frequency_choice

import aiofiles
import aiofiles.os as aios
from pathlib import Path

# --- КОНСТАНТЫ ---
class UserSteps(Enum):
    NONE = auto()
    AWAITING_LANGUAGE_CHOICE = auto()
    AWAITING_REGION = auto()
    AWAITING_STREET = auto()
    AWAITING_ADDRESS_TO_REMOVE = auto()
    AWAITING_CLEAR_ALL_CONFIRMATION = auto()
    AWAITING_ADDRESS_TO_CHECK = auto()
    AWAITING_FREQUENCY_CHOICE = auto()
    AWAITING_SUBSCRIPTION_CHOICE = auto()

USER_DATA_LANG = "current_language"
USER_DATA_STEP = "current_step"
USER_DATA_SELECTED_REGION = "selected_region_for_add"
CALLBACK_PREFIX_SUBSCRIBE = "subscribe:"
CALLBACK_PREFIX_PAY = "pay:" # Потенциальный префикс для будущей оплаты

# --- КОНФИГУРАЦИЯ ---
@dataclass
class BotConfig:
    telegram_token: str
    settings_file: Path = Path("user_settings.json")
    address_file: Path = Path("addresses.json")
    notified_file: Path = Path("notified.json")
    backup_dir: Path = Path("backups")
    log_level: str = "INFO"
    backup_interval_seconds: int = 86400
    max_requests_per_minute: int = 30
    max_backups_to_keep: int = 5
    ad_interval_seconds: int = 86400 # Интервал для показа рекламы (пример)

    @classmethod
    def from_env(cls) -> 'BotConfig':
        load_dotenv()
        backup_path = Path(os.getenv("BACKUP_DIR", "backups"))
        backup_path.mkdir(parents=True, exist_ok=True)
        return cls(
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            settings_file=Path(os.getenv("SETTINGS_FILE", "user_settings.json")),
            address_file=Path(os.getenv("ADDRESS_FILE", "addresses.json")),
            notified_file=Path(os.getenv("NOTIFIED_FILE", "notified.json")),
            backup_dir=backup_path,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            backup_interval_seconds=int(os.getenv("BACKUP_INTERVAL_SECONDS", "86400")),
            max_requests_per_minute=int(os.getenv("MAX_REQUESTS_PER_MINUTE", "30")),
            max_backups_to_keep=int(os.getenv("MAX_BACKUPS_TO_KEEP", "5")),
            ad_interval_seconds=int(os.getenv("AD_INTERVAL_SECONDS", "86400"))
        )

    def validate(self) -> bool:
        if not self.telegram_token:
            log_error("TELEGRAM_BOT_TOKEN не найден в переменных окружения или .env файле.")
            raise ValueError("Необходим TELEGRAM_BOT_TOKEN")
        return True

config = BotConfig.from_env()
config.validate()

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
user_settings: Dict[int, Dict[str, Any]] = {}
user_languages: Dict[int, str] = {} # Этот словарь можно объединить с user_settings
user_addresses: Dict[int, List[Dict[str, str]]] = {}
user_notified_headers: Dict[int, Set[str]] = {}
last_check_time: Dict[int, float] = {}
last_ad_time: Dict[int, float] = {} # Для отслеживания времени последнего показа рекламы
user_request_counts: Dict[int, List[float]] = defaultdict(list)
start_time = time()
settings_file_lock = asyncio.Lock()
address_file_lock = asyncio.Lock()
notified_file_lock = asyncio.Lock()

# --- ЯЗЫКИ И КЛАВИАТУРЫ ---
languages = {"🇦🇲 Հայերեն": "hy", "🇷🇺 Русский": "ru", "🇺🇸 English": "en"}
language_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton(text) for text in languages.keys()]],
    resize_keyboard=True, one_time_keyboard=True
)

regions_hy = ["Երևան", "Արագածոտն", "Արարատ", "Արմավիր", "Գեղարքունիք", "Լոռի", "Կոտայք", "Շիրակ", "Սյունիք", "Վայոց ձոր", "Տավուշ"]
regions_ru = ["Ереван", "Арагацотн", "Арарат", "Армавир", "Вайоц дзор", "Гехаркуник", "Котайк", "Лори", "Сюник", "Тавуш", "Ширак"]
regions_en = ["Yerevan", "Aragatsotn", "Ararat", "Armavir", "Gegharkunik", "Kotayk", "Lori", "Shirak", "Syunik", "Tavush", "Vayots Dzor"]

def get_region_keyboard(lang: str) -> ReplyKeyboardMarkup:
    regions_map = {"hy": regions_hy, "ru": regions_ru, "en": regions_en}
    current_regions = regions_map.get(lang, regions_hy)
    keyboard = [[KeyboardButton(region)] for region in current_regions]
    keyboard.append([KeyboardButton(translations.get("cancel", {}).get(lang, "Cancel"))])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_main_menu_buttons(lang: str) -> List[List[KeyboardButton]]:
    # Используем .get для безопасного доступа к переводам
    return [
        [KeyboardButton(translations.get("add_address_btn", {}).get(lang, "Add Address")),
         KeyboardButton(translations.get("remove_address_btn", {}).get(lang, "Remove Address"))],
        [KeyboardButton(translations.get("show_addresses_btn", {}).get(lang, "Show Addresses")),
         KeyboardButton(translations.get("clear_all_btn", {}).get(lang, "Clear All"))],
        [KeyboardButton(translations.get("check_address_btn", {}).get(lang, "Check Address")),
         KeyboardButton(translations.get("change_language_btn", {}).get(lang, "Change Language"))],
        [KeyboardButton(translations.get("statistics_btn", {}).get(lang, "Statistics")),
         KeyboardButton(translations.get("help_btn", {}).get(lang, "Help"))],
        [KeyboardButton(translations.get("set_frequency_btn", {}).get(lang, "Set Frequency")),
         KeyboardButton(translations.get("subscription_btn", {}).get(lang, "Subscription"))]
    ]

def reply_markup_for_lang(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(get_main_menu_buttons(lang), resize_keyboard=True)

# --- УТИЛИТЫ ---
def validate_user_input(text: str) -> bool:
    if not text or len(text) > 1000: return False
    dangerous_patterns = ['<script', 'javascript:', 'onclick', 'onerror', 'onload', 'eval(']
    return not any(pattern in text.lower() for pattern in dangerous_patterns)

def is_user_rate_limited(user_id: int, max_requests: Optional[int] = None, window: int = 60) -> bool:
    if max_requests is None: max_requests = config.max_requests_per_minute
    now = time()
    user_reqs = user_request_counts[user_id]
    user_reqs[:] = [req_time for req_time in user_reqs if now - req_time < window]
    if len(user_reqs) >= max_requests: return True
    user_reqs.append(now)
    return False

# Определение тарифов (можно вынести в отдельный конфигурационный файл или раздел)
premium_tiers = {
    "Free": {"interval": 21600, "price_amd": 0, "ad_enabled": True, "checks_per_day_limit": 4}, # 6 часов
    "Basic": {"interval": 3600, "price_amd": 490, "ad_enabled": False, "checks_per_day_limit": 24}, # 1 час
    "Premium": {"interval": 900, "price_amd": 990, "ad_enabled": False, "checks_per_day_limit": 96}, # 15 минут
    "Ultra": {"interval": 300, "price_amd": 1990, "ad_enabled": False, "checks_per_day_limit": 288} # 5 минут
}
# Добавим сюда опции для более частых проверок из handlers.py для консистентности
# Это будет использоваться для формирования клавиатуры подписки.
# В handlers.py FREQUENCY_OPTIONS останется для выбора частоты вручную.

def get_subscription_keyboard(lang: str) -> InlineKeyboardMarkup:
    buttons = []
    for tier_key, tier_info in premium_tiers.items():
        # Безопасное получение переводов
        price_str = (f"({tier_info['price_amd']} {translations.get('amd_short', {}).get(lang, 'AMD')}/"
                     f"{translations.get('month_short', {}).get(lang, 'mo')})"
                     if tier_info['price_amd'] > 0 else f"({translations.get('free', {}).get(lang, 'Free')})")
        label = f"{translations.get(f'tier_{tier_key.lower()}', {}).get(lang, tier_key)} {price_str}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"{CALLBACK_PREFIX_SUBSCRIBE}{tier_key}")])
    # Можно добавить кнопку "Оплатить" если выбран платный тариф, ведущую к платежной системе
    # buttons.append([InlineKeyboardButton(text=translations.get("pay_button", {}).get(lang, "Proceed to Payment"), callback_data=f"{CALLBACK_PREFIX_PAY}selected_tier")])
    return InlineKeyboardMarkup(buttons)

async def show_subscription_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_info(f"[smart_bot] show_subscription_options called for user {update.effective_user.id}")
    if not update.message: return
    lang = context.user_data.get(USER_DATA_LANG, "hy")
    
    # BUG FIX 1: Использовать lang для текста "Опции подписки"
    subscription_options_text = translations.get("subscription_options_title", {}).get(lang, "Subscription Options:")
    
    await update.message.reply_text(
        subscription_options_text, # Исправлено
        reply_markup=get_subscription_keyboard(lang)
    )
    context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_SUBSCRIPTION_CHOICE
    log_info(f"[smart_bot] User {update.effective_user.id} step set to AWAITING_SUBSCRIPTION_CHOICE")

async def handle_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        log_error("[smart_bot] handle_subscription_callback: query or query.data is None")
        return

    await query.answer()
    user_id = query.from_user.id
    lang = context.user_data.get(USER_DATA_LANG, "hy")
    log_info(f"[smart_bot] handle_subscription_callback for user {user_id}, data: '{query.data}'")

    try:
        selected_tier_key = query.data.split(CALLBACK_PREFIX_SUBSCRIBE)[1]
        if selected_tier_key not in premium_tiers:
            log_error(f"Unknown tier key '{selected_tier_key}' selected by user {user_id}.")
            await query.edit_message_text(translations.get("error_invalid_tier", {}).get(lang, "Invalid subscription tier selected."))
            context.user_data[USER_DATA_STEP] = UserSteps.NONE
            return

        plan = premium_tiers[selected_tier_key]
        log_info(f"[smart_bot] User {user_id} selected tier: {selected_tier_key}, plan details: {plan}")

        current_s = user_settings.get(user_id, {})
        current_s.update({
            "frequency": plan["interval"],
            "is_premium": plan["price_amd"] > 0,
            "ads_enabled": plan["ad_enabled"],
            "current_tier": selected_tier_key
        })
        user_settings[user_id] = current_s
        await save_user_settings_async()
        log_info(f"[smart_bot] Settings saved for user {user_id} after subscription choice.")

        # BUG FIX 4: Улучшенное сообщение о смене подписки
        tier_name_translated = translations.get(f'tier_{selected_tier_key.lower()}', {}).get(lang, selected_tier_key)
        interval_hours = plan['interval'] / 3600
        interval_minutes = plan['interval'] / 60

        if plan['interval'] >= 3600:
            interval_desc = f"{int(interval_hours)} {translations.get('hours_short', {}).get(lang, 'h')}"
        else:
            interval_desc = f"{int(interval_minutes)} {translations.get('minutes_short', {}).get(lang, 'min')}"

        success_message_key = "subscription_success_details" if plan["price_amd"] > 0 else "subscription_free_success_details"
        
        success_message_template = translations.get(success_message_key, {}).get(lang, "Subscription {plan} activated. Check interval: {interval}.")
        
        success_message = success_message_template.format(plan=tier_name_translated, interval=interval_desc)

        await query.edit_message_text(success_message)
        # Здесь можно добавить логику для перехода к оплате, если это платный тариф
        # if plan["price_amd"] > 0:
        #     await query.message.reply_text(translations.get("proceed_to_payment_prompt", {}).get(lang, "Please proceed to payment...")) # Добавить кнопку оплаты
        # else:
        #     await query.message.reply_text(text=translations.get("menu_returned", {}).get(lang, "Returned to menu."), reply_markup=reply_markup_for_lang(lang))
        
        await query.message.reply_text(text=translations.get("menu_returned", {}).get(lang, "Returned to main menu."), reply_markup=reply_markup_for_lang(lang))
        context.user_data[USER_DATA_STEP] = UserSteps.NONE

    except (IndexError, KeyError) as e:
        log_error(f"Ошибка обработки callback-данных подписки '{query.data}' для пользователя {user_id}: {e}")
        await query.edit_message_text(translations.get("error_generic", {}).get(lang, "Error processing selection."))
        context.user_data[USER_DATA_STEP] = UserSteps.NONE
    except Exception as e:
        log_error(f"Непредвиденная ошибка в handle_subscription_callback для пользователя {user_id}, data '{query.data}': {e}", exc=e)
        await query.edit_message_text(translations.get("error_generic", {}).get(lang, "A serious error occurred."))
        context.user_data[USER_DATA_STEP] = UserSteps.NONE


def normalize_address(addr: str) -> str:
    if not addr: return ""
    addr_low = addr.lower()
    addr_strip = addr_low.strip()
    addr_space = re.sub(r'\s+', ' ', addr_strip)
    replacements = {'ул.': 'улица', 'пр.': 'проспект', 'փ.': 'փողոց', 'st.': 'street', 'ave.': 'avenue', 'բլվ.': 'բուլվար', 'пер.': 'переулок'}
    for old, new in replacements.items():
        addr_space = addr_space.replace(old, new)
    return addr_space

def fuzzy_match_address(user_address_normalized: str, entry_locations_normalized: List[str], threshold: float = 0.8) -> bool:
    for loc_norm in entry_locations_normalized:
        if user_address_normalized in loc_norm: return True # Прямое вхождение
        if SequenceMatcher(None, user_address_normalized, loc_norm).ratio() >= threshold: return True
    return False

def match_address(user_id: int, entry: Dict[str, Any]) -> Optional[Dict[str, str]]:
    user_addrs = user_addresses.get(user_id, [])
    if not user_addrs: return None

    entry_streets_norm = [normalize_address(s) for s in entry.get("streets", [])]
    entry_regions_norm = [normalize_address(r) for r in entry.get("regions", [])]

    for address_obj in user_addrs:
        user_street_norm = normalize_address(address_obj["street"])
        user_region_norm = normalize_address(address_obj["region"])

        region_match_confirmed = False
        if entry_regions_norm: # Если в объявлении указаны регионы
            if fuzzy_match_address(user_region_norm, entry_regions_norm, threshold=0.9):
                region_match_confirmed = True
        else: # Если в объявлении регионы не указаны, считаем, что по региону совпадение есть (проверяем только улицу)
            region_match_confirmed = True

        if region_match_confirmed:
            if entry_streets_norm: # Если в объявлении указаны улицы
                if fuzzy_match_address(user_street_norm, entry_streets_norm):
                    return address_obj
            else: # Если в объявлении улицы не указаны, но регион совпал (или не был указан в объявлении)
                  # Это рискованно, может привести к ложным срабатываниям, если отключают весь регион.
                  # Пока оставим так, но это место для возможного улучшения логики.
                  # Возможно, стоит возвращать совпадение, только если есть хотя бы одно совпадение по улице, если улицы указаны.
                  # Если в объявлении нет улиц, то это широкомасштабное отключение, и совпадение по региону достаточно.
                log_info(f"Address match for user {user_id} on region '{user_region_norm}' due to unspecified streets in entry.")
                return address_obj # Считаем совпадением, если улицы в объявлении не указаны, а регион подошел.
    return None

# --- АСИНХРОННОЕ СОХРАНЕНИЕ И ЗАГРУЗКА ДАННЫХ ---
async def _save_json_async(filepath: Path, data: Any, lock: asyncio.Lock):
    async with lock:
        try:
            async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            log_info(f"Данные успешно сохранены в {filepath}")
        except Exception as e:
            log_error(f"Не удалось сохранить данные в {filepath}: {e}")
            raise

async def _load_json_async(filepath: Path, lock: asyncio.Lock, default_factory=dict) -> Any:
    async with lock:
        if not await aios.path.exists(filepath):
            log_info(f"Файл {filepath} не найден, возвращается значение по умолчанию.")
            return default_factory() if callable(default_factory) else default_factory
        try:
            async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            log_error(f"Не удалось загрузить данные из {filepath}: {e}. Возвращается значение по умолчанию.")
            return default_factory() if callable(default_factory) else default_factory

async def _perform_backup_async(filepath: Path):
    if not await aios.path.exists(filepath): return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = config.backup_dir / f"{filepath.stem}.backup_{timestamp}{filepath.suffix}"
    try:
        # shutil.copy2 синхронный, выполняем в executor'е
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, shutil.copy2, filepath, backup_file)
        log_info(f"Резервная копия создана для {filepath} в {backup_file}")
    except Exception as e:
        log_error(f"Не удалось создать резервную копию для {filepath}: {e}")

async def _cleanup_old_backups_async(filename_prefix_stem: str):
    loop = asyncio.get_event_loop()
    # Получаем все файлы, затем фильтруем по имени, которое начинается с filename_prefix_stem и содержит .backup_
    backup_files = await loop.run_in_executor(
        None,
        lambda: sorted(
            [f for f in config.backup_dir.iterdir() if f.name.startswith(filename_prefix_stem) and f.name.count(".backup_")],
            key=os.path.getmtime,
            reverse=True
        )
    )
    for old_backup in backup_files[config.max_backups_to_keep:]:
        try:
            await aios.remove(old_backup)
            log_info(f"Удалена старая резервная копия: {old_backup}")
        except Exception as e:
            log_error(f"Не удалось удалить старую резервную копию {old_backup}: {e}")

async def save_user_settings_async():
    global user_settings
    filepath = config.settings_file
    await _perform_backup_async(filepath)
    try:
        data_to_save = {str(k): v for k, v in user_settings.items()} # Ключи ID пользователей должны быть строками в JSON
        await _save_json_async(filepath, data_to_save, settings_file_lock)
        await _cleanup_old_backups_async(filepath.stem)
    except Exception as e: # Добавил аргумент 'e'
        log_error(f"Ошибка сохранения {filepath}, данные могут быть неконсистентны: {e}")

async def load_user_settings_async():
    global user_settings, user_languages # user_languages теперь часть user_settings
    raw_settings = await _load_json_async(config.settings_file, settings_file_lock, default_factory=dict)
    # Конвертируем ключи обратно в int и обновляем user_languages
    temp_user_settings = {}
    for k_str, v_dict in raw_settings.items():
        if k_str.isdigit():
            uid = int(k_str)
            temp_user_settings[uid] = v_dict
            if "lang" in v_dict: # Обновляем user_languages для обратной совместимости, если где-то используется
                 user_languages[uid] = v_dict["lang"]
        else:
            log_error(f"Неверный формат ID пользователя в файле настроек: {k_str}")
    user_settings = temp_user_settings
    log_info(f"Загружены настройки для {len(user_settings)} пользователей.")


async def save_tracked_data_async():
    global user_addresses, user_notified_headers
    addr_filepath = config.address_file
    await _perform_backup_async(addr_filepath)
    try:
        addr_data_to_save = {str(k): v for k, v in user_addresses.items()}
        await _save_json_async(addr_filepath, addr_data_to_save, address_file_lock)
        await _cleanup_old_backups_async(addr_filepath.stem)
    except Exception as e:
        log_error(f"Ошибка сохранения {addr_filepath}: {e}")

    notif_filepath = config.notified_file
    await _perform_backup_async(notif_filepath)
    try:
        # Конвертируем set в list для JSON-сериализации
        notif_data_to_save = {str(k): list(v) for k, v in user_notified_headers.items()}
        await _save_json_async(notif_filepath, notif_data_to_save, notified_file_lock)
        await _cleanup_old_backups_async(notif_filepath.stem)
    except Exception as e:
        log_error(f"Ошибка сохранения {notif_filepath}: {e}")

async def load_tracked_data_async():
    global user_addresses, user_notified_headers
    # Загрузка адресов
    raw_addresses = await _load_json_async(config.address_file, address_file_lock, default_factory=dict)
    temp_user_addresses = {}
    for uid_str, items_list in raw_addresses.items():
        if not uid_str.isdigit():
            log_error(f"Неверный формат ID пользователя в файле адресов: {uid_str}")
            continue
        uid_int = int(uid_str)
        valid_items = []
        if isinstance(items_list, list):
            for item in items_list:
                if isinstance(item, dict) and "street" in item and "region" in item:
                    valid_items.append(item)
                # Поддержка старого формата, где адрес был просто строкой
                elif isinstance(item, str):
                    valid_items.append({"region": "Չսահմանված", "street": item}) # Регион по умолчанию
                    log_info(f"Конвертирован старый формат адреса для пользователя {uid_int}: {item}")
                else:
                    log_info(f"Пропуск неверного элемента адреса для пользователя {uid_int}: {item}")
            temp_user_addresses[uid_int] = valid_items
        else:
            log_error(f"Элементы адреса для пользователя {uid_int} не являются списком: {items_list}")
            temp_user_addresses[uid_int] = [] # Пустой список, если формат неверный
    user_addresses = temp_user_addresses
    log_info(f"Загружены адреса для {len(user_addresses)} пользователей.")

    # Загрузка истории уведомлений
    raw_notified = await _load_json_async(config.notified_file, notified_file_lock, default_factory=dict)
    temp_user_notified_headers = {}
    for k_str, v_list in raw_notified.items():
        if not k_str.isdigit():
            log_error(f"Неверный формат ID пользователя в файле истории уведомлений: {k_str}")
            continue
        if isinstance(v_list, list): # Убеждаемся, что v_list - это список
            temp_user_notified_headers[int(k_str)] = set(v_list)
        else:
            log_error(f"История уведомлений для пользователя {k_str} не является списком: {v_list}")
            temp_user_notified_headers[int(k_str)] = set() # Пустое множество, если формат неверный
    user_notified_headers = temp_user_notified_headers
    log_info(f"Загружена история уведомлений для {len(user_notified_headers)} пользователей.")

# --- ОСНОВНАЯ ЛОГИКА БОТА ---
async def process_utility_data(user_id: int, context: ContextTypes.DEFAULT_TYPE, data: List[Dict], utility_type: str, emoji: str, lang: str):
    if not data: return

    for entry in data:
        if not entry or not isinstance(entry, dict):
            log_info(f"Пропуск неверной записи в данных {utility_type}: {entry}")
            continue

        header_parts = [
            entry.get('published', 'N/A'), # Дата публикации для уникальности
            entry.get('start_date', 'N/A'),
            entry.get('start_time', 'N/A'),
            utility_type
        ]
        # Собираем улицы и регионы в строку для заголовка, чтобы сделать его более уникальным
        # Это важно, если объявления могут иметь одинаковое время начала, но разные улицы/регионы
        streets_str = ",".join(sorted(entry.get("streets", [])))
        regions_str = ",".join(sorted(entry.get("regions", [])))
        header_parts.append(streets_str)
        header_parts.append(regions_str)
        
        header = " | ".join(header_parts)


        if user_id in user_notified_headers and header in user_notified_headers[user_id]:
            log_info(f"Уведомление с заголовком '{header}' уже было отправлено пользователю {user_id}")
            continue # Уже уведомлен об этом конкретном событии

        matched_address_obj = match_address(user_id, entry)
        if matched_address_obj:
            try:
                # Безопасное получение переводов с фолбэками
                type_off_key = f"{utility_type}_off"
                type_off_text = translations.get(type_off_key, {}).get(lang, utility_type.capitalize())

                msg_parts = [
                    f"{emoji} *{type_off_text}* {escape_markdown(matched_address_obj['region'], 2)} - {escape_markdown(matched_address_obj['street'], 2)}",
                    f"📅 *{translations.get('date_time_label', {}).get(lang, 'Period')}:* {escape_markdown(entry.get('start_date', 'N/A'),2)} {escape_markdown(entry.get('start_time', 'N/A'),2)} → {escape_markdown(entry.get('end_date', 'N/A'),2)} {escape_markdown(entry.get('end_time', 'N/A'),2)}",
                ]
                if entry.get('regions'):
                     msg_parts.append(f"📍 *{translations.get('locations_label', {}).get(lang, 'Locations')}:* {escape_markdown(', '.join(entry.get('regions', [])),2)}")
                if entry.get('streets'):
                     msg_parts.append(f"  *└ {translations.get('streets_label', {}).get(lang, 'Streets')}:* {escape_markdown(', '.join(entry.get('streets')),2)}")
                
                msg_parts.extend([
                    f"⚙️ *{translations.get('status_label', {}).get(lang, 'Status')}:* {escape_markdown(entry.get('status', 'N/A'),2)}",
                    f"🗓 *{translations.get('published_label', {}).get(lang, 'Published')}:* {escape_markdown(entry.get('published', 'N/A'),2)}"
                ])
                msg = "\n\n".join(msg_parts)

                await context.bot.send_message(chat_id=user_id, text=msg, parse_mode=ParseMode.MARKDOWN_V2)
                user_notified_headers.setdefault(user_id, set()).add(header)
                await save_tracked_data_async() # Сохраняем сразу после добавления в set
                log_info(f"Отправлено уведомление ({utility_type}) пользователю {user_id} по адресу {matched_address_obj['street']}")
            except KeyError as ke: # Обработка случая, если ключ перевода отсутствует
                log_error(f"Ошибка ключа перевода для уведомления ({utility_type}) пользователю {user_id}: {ke}. Проверьте translations.py.")
            except Exception as e:
                log_error(f"Не удалось отправить уведомление ({utility_type}) пользователю {user_id}: {e}", exc=e)


async def check_site_for_user(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    # Язык пользователя для уведомлений
    lang = context.user_data.get(USER_DATA_LANG) or user_settings.get(user_id, {}).get("lang", "hy")

    if not user_addresses.get(user_id):
        log_info(f"Нет адресов для проверки для пользователя {user_id}")
        return

    log_info(f"Проверка сайтов для пользователя {user_id}")
    try:
        # Запускаем все парсеры параллельно
        water_data, gas_data, electric_data = await asyncio.gather(
            parse_all_water_announcements_async(),
            parse_all_gas_announcements_async(),
            parse_all_electric_announcements_async(),
            return_exceptions=True # Чтобы одна ошибка не остановила все
        )

        # Обработка результатов и ошибок
        if isinstance(water_data, Exception):
            log_error(f"Ошибка парсинга воды для пользователя {user_id}: {water_data}")
            water_data = []
        if isinstance(gas_data, Exception):
            log_error(f"Ошибка парсинга газа для пользователя {user_id}: {gas_data}")
            gas_data = []
        if isinstance(electric_data, Exception):
            log_error(f"Ошибка парсинга электричества для пользователя {user_id}: {electric_data}")
            electric_data = []

    except Exception as e: # Общая ошибка, если gather сам по себе падает
        log_error(f"Критическая ошибка при сборе данных для пользователя {user_id}: {e}")
        return

    # Обработка данных по каждому типу коммунальных услуг
    await process_utility_data(user_id, context, water_data, "water", "🚰", lang)
    await process_utility_data(user_id, context, gas_data, "gas", "🔥", lang)
    await process_utility_data(user_id, context, electric_data, "💡", "electric", lang)


async def is_shutdown_for_address_now(address_street: str, address_region: str) -> List[str]:
    normalized_street = normalize_address(address_street)
    normalized_region = normalize_address(address_region)
    active_shutdown_types: List[str] = [] # Явная типизация

    # Внутренняя функция для проверки совпадения
    def _check_match(entry_data: List[Dict], utility_type: str):
        for entry in entry_data:
            if not entry or not isinstance(entry, dict): continue # Пропускаем некорректные записи

            entry_streets_norm = [normalize_address(s) for s in entry.get("streets", [])]
            entry_regions_norm = [normalize_address(r) for r in entry.get("regions", [])]

            region_match_confirmed = False
            if entry_regions_norm:
                if fuzzy_match_address(normalized_region, entry_regions_norm, threshold=0.9):
                    region_match_confirmed = True
            else: # Если регионы в объявлении не указаны, считаем, что совпадение по региону есть
                region_match_confirmed = True
            
            if region_match_confirmed:
                if entry_streets_norm: # Если улицы в объявлении указаны
                     if fuzzy_match_address(normalized_street, entry_streets_norm):
                        if utility_type not in active_shutdown_types:
                            active_shutdown_types.append(utility_type)
                        return # Достаточно одного совпадения для данного типа
                # else: # Если улицы в объявлении не указаны, но регион совпал
                #     # Это может быть отключение всего региона. Добавляем тип.
                #     if utility_type not in active_shutdown_types:
                #         active_shutdown_types.append(utility_type)
                #     return # Оставил закомментированным, чтобы избежать ложных срабатываний если улицы не указаны в объявлении.
                #              # Требует более точного определения бизнес-логики.

    try:
        water_data, gas_data, electric_data = await asyncio.gather(
            parse_all_water_announcements_async(),
            parse_all_gas_announcements_async(),
            parse_all_electric_announcements_async(),
            return_exceptions=True
        )

        if not isinstance(water_data, Exception) and water_data: _check_match(water_data, "water")
        if not isinstance(gas_data, Exception) and gas_data: _check_match(gas_data, "gas")
        if not isinstance(electric_data, Exception) and electric_data: _check_match(electric_data, "electric")

    except Exception as e:
        log_error(f"Ошибка в is_shutdown_for_address_now для {address_region}, {address_street}: {e}")

    return active_shutdown_types

# --- ОБРАБОТЧИКИ КОМАНД ТЕЛЕГРАМ ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_info(f"[smart_bot] /start command from user {user.id if user else 'Unknown'}")
    if not user or not update.message: return

    if is_user_rate_limited(user.id):
        log_info(f"Превышен лимит запросов для пользователя {user.id} в /start")
        # Можно отправить сообщение о превышении лимита, если это нужно
        # await update.message.reply_text("Rate limit exceeded. Please try again later.")
        return

    # Если язык еще не установлен (новый пользователь или сброс данных)
    if USER_DATA_LANG not in context.user_data and user.id not in user_settings:
        await update.message.reply_text(
            translations.get("choose_language", {}).get("hy", "Ընտրեք լեզուն:") + "\n" + # На армянском по умолчанию
            translations.get("choose_language", {}).get("ru", "Выберите язык:") + "\n" +
            translations.get("choose_language", {}).get("en", "Choose language:"),
            reply_markup=language_keyboard
        )
        context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_LANGUAGE_CHOICE
    else:
        # Если язык есть в user_data или user_settings, используем его
        lang = context.user_data.get(USER_DATA_LANG) or user_settings.get(user.id, {}).get("lang", "hy")
        context.user_data[USER_DATA_LANG] = lang # Убедимся, что язык в user_data для текущей сессии

        await update.message.reply_text(
            translations.get("start_text", {}).get(lang, "Hello! Choose an action."),
            reply_markup=reply_markup_for_lang(lang)
        )
        context.user_data[USER_DATA_STEP] = UserSteps.NONE

async def address_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_info(f"[smart_bot] address_list_command from user {user.id if user else 'Unknown'}")
    if not user or not update.message: return
    user_id = user.id

    lang = context.user_data.get(USER_DATA_LANG) or user_settings.get(user_id, {}).get("lang", "hy")
    if is_user_rate_limited(user_id): return

    addresses = user_addresses.get(user_id, [])
    if addresses:
        address_lines = [f"📍 {a['region']} — {a['street']}" for a in addresses] # Добавлен эмодзи
        text_to_send = translations.get("address_list", {}).get(lang, "Your addresses:") + "\n" + "\n".join(address_lines)
    else:
        text_to_send = translations.get("no_addresses", {}).get(lang, "No addresses added yet.")

    await update.message.reply_text(text_to_send, reply_markup=reply_markup_for_lang(lang))
    context.user_data[USER_DATA_STEP] = UserSteps.NONE

async def show_statistics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_info(f"[smart_bot] show_statistics_command from user {user.id if user else 'Unknown'}")
    if not user or not update.message: return
    user_id = user.id

    lang = context.user_data.get(USER_DATA_LANG) or user_settings.get(user_id, {}).get("lang", "hy")
    if is_user_rate_limited(user_id):
        log_info(f"[smart_bot] Rate limit for stats user {user_id}")
        return

    # Статистика (пример)
    active_users_with_addresses = len(user_addresses) # Пользователи с хотя бы одним адресом
    total_addresses_tracked = sum(len(addrs) for addrs in user_addresses.values())
    uptime_seconds = time() - start_time
    uptime_days = int(uptime_seconds // 86400)
    uptime_hours = int((uptime_seconds % 86400) // 3600)
    uptime_minutes = int((uptime_seconds % 3600) // 60)
    
    uptime_str_parts = []
    if uptime_days > 0: uptime_str_parts.append(f"{uptime_days} {translations.get('stats_days_unit', {}).get(lang, 'd')}")
    if uptime_hours > 0: uptime_str_parts.append(f"{uptime_hours} {translations.get('stats_hours_unit', {}).get(lang, 'h')}")
    if uptime_minutes > 0 or not uptime_str_parts : uptime_str_parts.append(f"{uptime_minutes} {translations.get('stats_minutes_unit', {}).get(lang, 'm')}")
    uptime_formatted = " ".join(uptime_str_parts)


    user_specific_addresses = len(user_addresses.get(user_id, []))
    user_specific_notifications_sent = len(user_notified_headers.get(user_id, set())) # Сколько уникальных уведомлений было отправлено этому пользователю

    stats_text = (
        f"📊 {translations.get('statistics_title', {}).get(lang, 'Bot Statistics')}\n\n"
        f"🕒 {translations.get('stats_uptime', {}).get(lang, 'Uptime')}: {uptime_formatted}\n"
        f"👥 {translations.get('stats_users_with_addresses', {}).get(lang, 'Users with addresses')}: {active_users_with_addresses}\n"
        f"📍 {translations.get('stats_total_addresses', {}).get(lang, 'Total addresses tracked')}: {total_addresses_tracked}\n\n"
        f"👤 {translations.get('stats_your_info_title', {}).get(lang, 'Your Information')}:\n"
        f"🏠 {translations.get('stats_your_addresses', {}).get(lang, 'Your addresses')}: {user_specific_addresses}\n"
        f"📨 {translations.get('stats_your_notifications_sent', {}).get(lang, 'Notifications you received')}: {user_specific_notifications_sent}"
    )
    await update.message.reply_text(stats_text, reply_markup=reply_markup_for_lang(lang))
    context.user_data[USER_DATA_STEP] = UserSteps.NONE

async def show_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_info(f"[smart_bot] show_help_command from user {user.id if user else 'Unknown'}")
    if not user or not update.message: return
    user_id = user.id

    lang = context.user_data.get(USER_DATA_LANG) or user_settings.get(user_id, {}).get("lang", "hy")
    if is_user_rate_limited(user_id):
        log_info(f"[smart_bot] Rate limit for help user {user_id}")
        return

    help_text_key = "help_text_main"
    # BUG FIX 3: Использовать локализованный фолбэк, если основной текст помощи отсутствует
    default_help_unavailable = translations.get("help_unavailable", {}).get(lang, "Help section is not yet available in your language.")
    raw_help_message = translations.get(help_text_key, {}).get(lang, default_help_unavailable)
    
    # Экранирование Markdown символов
    escaped_help_message = escape_markdown(raw_help_message, version=2)

    try:
        await update.message.reply_text(
            escaped_help_message,
            reply_markup=reply_markup_for_lang(lang),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e: # Если даже с экранированием не отправляется (маловероятно, но возможно)
        log_error(f"Ошибка отправки сообщения помощи пользователю {user_id} (даже после экранирования): {e}", exc=e)
        # Пробуем отправить без Markdown форматирования
        await update.message.reply_text(raw_help_message, reply_markup=reply_markup_for_lang(lang))

    context.user_data[USER_DATA_STEP] = UserSteps.NONE

async def change_language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log_info(f"[smart_bot] change_language_command from user {user.id if user else 'Unknown'}")
    if not user or not update.message : return
    user_id = user.id # Определяем user_id

    if is_user_rate_limited(user_id): return

    # BUG FIX 2: Запрос на смену языка должен быть на текущем языке пользователя
    current_lang = context.user_data.get(USER_DATA_LANG) or user_settings.get(user_id, {}).get("lang", "hy")
    prompt_text = translations.get("choose_language_prompt_button", {}).get(current_lang, "Please select your new language using the buttons below:")

    await update.message.reply_text(prompt_text, reply_markup=language_keyboard)
    context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_LANGUAGE_CHOICE


# --- ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ И ДИАЛОГОВ ---
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    if not user or not message or not message.text: return

    # Определяем язык пользователя для ответа
    # Приоритет: user_data (текущая сессия) -> user_settings (сохраненные) -> дефолтный 'hy'
    lang = context.user_data.get(USER_DATA_LANG) or user_settings.get(user.id, {}).get("lang", "hy")
    # Если язык был определен из user_settings, сохраним его в user_data для этой сессии
    if USER_DATA_LANG not in context.user_data and user.id in user_settings:
        context.user_data[USER_DATA_LANG] = lang
        
    current_step = context.user_data.get(USER_DATA_STEP, UserSteps.NONE)
    text = message.text.strip()
    log_info(f"[smart_bot] handle_text_message: user={user.id}, text='{text}', lang='{lang}', current_step='{current_step}'")

    if is_user_rate_limited(user.id):
        log_info(f"Превышен лимит запросов для пользователя {user.id} (текстовое сообщение)")
        # await message.reply_text(translations.get("error_rate_limit", {}).get(lang, "Too many requests. Please wait."))
        return

    if not validate_user_input(text):
        await message.reply_text(translations.get("error_invalid_input", {}).get(lang, "Invalid input. Please try again."))
        return

    # Обработка выбора языка (самый первый шаг или смена языка)
    if current_step == UserSteps.AWAITING_LANGUAGE_CHOICE:
        log_info(f"[smart_bot] handle_text_message: Processing AWAITING_LANGUAGE_CHOICE for text '{text}'")
        if text in languages: # 'Русский', 'English', 'Հայերեն'
            selected_lang_code = languages[text] # 'ru', 'en', 'hy'
            context.user_data[USER_DATA_LANG] = selected_lang_code
            
            current_user_s = user_settings.get(user.id, {})
            current_user_s["lang"] = selected_lang_code
            user_settings[user.id] = current_user_s
            await save_user_settings_async() # Сохраняем настройки

            await message.reply_text(
                translations.get("language_set", {}).get(selected_lang_code, "Language set!"),
                reply_markup=reply_markup_for_lang(selected_lang_code)
            )
            context.user_data[USER_DATA_STEP] = UserSteps.NONE
            log_info(f"[smart_bot] Language set to '{selected_lang_code}' for user {user.id}. Step reset to NONE.")
        else: # Если пользователь ввел текст вместо нажатия кнопки выбора языка
            # Запрос должен быть на языке, который был *до* попытки смены, или на всех, если это первый вход
            prompt_lang_for_choice = lang # Используем текущий язык для этого сообщения
            if USER_DATA_LANG not in context.user_data and user.id not in user_settings : # Самый первый вход
                 await message.reply_text(
                    translations.get("choose_language", {}).get("hy", "Ընտրեք լեզուն:") + "\n" +
                    translations.get("choose_language", {}).get("ru", "Выберите язык:") + "\n" +
                    translations.get("choose_language", {}).get("en", "Choose language:"),
                    reply_markup=language_keyboard)
            else: # Попытка сменить язык, но ввел текст
                 await message.reply_text(
                    translations.get("choose_language_prompt_button", {}).get(prompt_lang_for_choice, "Please use buttons to select language."),
                    reply_markup=language_keyboard)
        return # Завершаем обработку здесь

    # Обработка кнопки "Отмена"
    if text == translations.get("cancel", {}).get(lang, "FallbackCancel"): # Добавлен фолбэк для 'cancel'
        log_info(f"[smart_bot] handle_text_message: Cancel button pressed by user {user.id}")
        await message.reply_text(
            translations.get("cancelled", {}).get(lang, "Action cancelled."),
            reply_markup=reply_markup_for_lang(lang)
        )
        context.user_data[USER_DATA_STEP] = UserSteps.NONE
        context.user_data.pop(USER_DATA_SELECTED_REGION, None) # Очищаем выбранный регион, если был
        return

    # Обработка команд главного меню и других шагов
    # (Сокращено для краткости, основная логика без изменений, но с добавлением .get для переводов)
    if current_step == UserSteps.NONE:
        log_info(f"[smart_bot] handle_text_message: current_step is NONE, processing main menu button '{text}'")
        # Используем .get() для всех ключей переводов, чтобы избежать KeyError
        if text == translations.get("add_address_btn", {}).get(lang):
            await message.reply_text(translations.get("choose_region", {}).get(lang, "Choose region:"), reply_markup=get_region_keyboard(lang))
            context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_REGION
        elif text == translations.get("remove_address_btn", {}).get(lang):
            if user_addresses.get(user.id):
                await message.reply_text(translations.get("enter_address_to_remove_prompt", {}).get(lang, "Which address to remove? (Enter street name)"), reply_markup=ReplyKeyboardMarkup([[translations.get("cancel", {}).get(lang, "Cancel")]], resize_keyboard=True, one_time_keyboard=True))
                context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_ADDRESS_TO_REMOVE
            else:
                await message.reply_text(translations.get("no_addresses", {}).get(lang, "No addresses yet."), reply_markup=reply_markup_for_lang(lang))
        elif text == translations.get("show_addresses_btn", {}).get(lang):
            await address_list_command(update, context)
        elif text == translations.get("clear_all_btn", {}).get(lang):
            if user_addresses.get(user.id):
                confirm_keyboard = ReplyKeyboardMarkup([
                    [KeyboardButton(translations.get("yes", {}).get(lang, "Yes")), KeyboardButton(translations.get("no", {}).get(lang, "No"))]
                ], resize_keyboard=True, one_time_keyboard=True)
                await message.reply_text(translations.get("confirm_clear", {}).get(lang, "Confirm clear all addresses?"), reply_markup=confirm_keyboard)
                context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_CLEAR_ALL_CONFIRMATION
            else:
                await message.reply_text(translations.get("no_addresses", {}).get(lang, "No addresses yet."), reply_markup=reply_markup_for_lang(lang))
        elif text == translations.get("check_address_btn", {}).get(lang):
            await message.reply_text(translations.get("enter_address_to_check_street", {}).get(lang, "Enter street to check:"), reply_markup=ReplyKeyboardMarkup([[translations.get("cancel", {}).get(lang, "Cancel")]], resize_keyboard=True, one_time_keyboard=True))
            context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_ADDRESS_TO_CHECK
        elif text == translations.get("change_language_btn", {}).get(lang):
            await change_language_command(update, context)
        elif text == translations.get("statistics_btn", {}).get(lang):
            await show_statistics_command(update, context)
        elif text == translations.get("help_btn", {}).get(lang):
            await show_help_command(update, context)
        elif text == translations.get("subscription_btn", {}).get(lang):
            await show_subscription_options(update, context) # Это покажет InlineKeyboard
        elif text == translations.get("set_frequency_btn", {}).get(lang):
            log_info(f"[smart_bot] 'Set Frequency' button pressed by user {user.id}. Calling set_frequency_command.")
            await set_frequency_command(update, context) # Эта команда из handlers.py
        else:
            log_info(f"[smart_bot] Unknown command/button '{text}' from user {user.id} in step NONE.")
            await message.reply_text(translations.get("unknown_command", {}).get(lang, "Unknown command."), reply_markup=reply_markup_for_lang(lang))
        return

    # --- Обработка шагов диалога ---
    if current_step == UserSteps.AWAITING_REGION:
        # Пользователь выбрал регион (текст кнопки региона)
        # Проверяем, есть ли такой регион в текущем языке
        current_regions_map = {"hy": regions_hy, "ru": regions_ru, "en": regions_en}
        if text not in current_regions_map.get(lang, []):
            await message.reply_text(translations.get("error_invalid_region_selection", {}).get(lang, "Invalid region. Please choose from buttons."), reply_markup=get_region_keyboard(lang))
            return # Остаемся на том же шаге

        context.user_data[USER_DATA_SELECTED_REGION] = text # Сохраняем выбранный регион
        await message.reply_text(
            translations.get("enter_street", {}).get(lang, "Please enter street name:"),
            reply_markup=ReplyKeyboardMarkup([[translations.get("cancel", {}).get(lang, "Cancel")]], resize_keyboard=True, one_time_keyboard=True)
        )
        context.user_data[USER_DATA_STEP] = UserSteps.AWAITING_STREET

    elif current_step == UserSteps.AWAITING_STREET:
        region = context.user_data.get(USER_DATA_SELECTED_REGION)
        if not region:
            await message.reply_text(translations.get("error_region_not_selected", {}).get(lang, "Region not selected. Please start over."), reply_markup=reply_markup_for_lang(lang))
            context.user_data[USER_DATA_STEP] = UserSteps.NONE
            return

        street = text # Пользователь ввел название улицы
        user_addresses.setdefault(user.id, [])
        normalized_new_street = normalize_address(street)
        normalized_new_region = normalize_address(region)

        is_duplicate = any(
            normalize_address(addr["street"]) == normalized_new_street and \
            normalize_address(addr["region"]) == normalized_new_region
            for addr in user_addresses[user.id]
        )

        if is_duplicate:
            await message.reply_text(
                translations.get("address_exists", {}).get(lang, "Address '{address}' already exists.").format(address=f"{region}, {street}"),
                reply_markup=reply_markup_for_lang(lang)
            )
        else:
            user_addresses[user.id].append({"region": region, "street": street})
            await save_tracked_data_async()
            await message.reply_text(
                translations.get("address_added", {}).get(lang, "Address '{address}' added.").format(address=f"{region}, {street}"),
                reply_markup=reply_markup_for_lang(lang)
            )
            # Проверка на текущие отключения для нового адреса
            shutdown_types = await is_shutdown_for_address_now(street, region)
            if shutdown_types:
                 types_str = ", ".join([translations.get(f"{stype}_off_short", {}).get(lang, stype.capitalize()) for stype in shutdown_types])
                 await message.reply_text(translations.get("shutdown_found_for_new_address", {}).get(lang, "ℹ️ Active outages for new address: {types}.").format(types=types_str))
            else:
                 await message.reply_text(translations.get("no_shutdowns_for_new_address", {}).get(lang, "✅ No active outages found for the new address."))

        context.user_data.pop(USER_DATA_SELECTED_REGION, None) # Очищаем выбранный регион
        context.user_data[USER_DATA_STEP] = UserSteps.NONE

    elif current_step == UserSteps.AWAITING_ADDRESS_TO_REMOVE:
        address_to_remove_text = text # Пользователь ввел улицу для удаления
        current_user_addresses = user_addresses.get(user.id, [])
        normalized_address_to_remove = normalize_address(address_to_remove_text)
        address_found_to_remove = None
        
        # Ищем адрес по совпадению улицы (предполагаем, что улицы уникальны в рамках одного пользователя, или пользователь знает, что удаляет)
        # Для более точного удаления можно попросить выбрать из списка, если есть дубликаты по названию улицы в разных регионах.
        best_match_addr = None
        highest_ratio = 0.0
        
        for addr_obj in current_user_addresses:
            norm_street = normalize_address(addr_obj["street"])
            # Сначала ищем точное совпадение нормализованной улицы
            if norm_street == normalized_address_to_remove:
                address_found_to_remove = addr_obj
                break
            # Если точного нет, ищем нечеткое
            ratio = SequenceMatcher(None, normalized_address_to_remove, norm_street).ratio()
            if ratio > highest_ratio:
                highest_ratio = ratio
                best_match_addr = addr_obj
        
        if not address_found_to_remove and best_match_addr and highest_ratio > 0.7: # Порог для нечеткого совпадения
            address_found_to_remove = best_match_addr
            log_info(f"Fuzzy matched address for removal: '{address_to_remove_text}' with '{best_match_addr['street']}' (ratio: {highest_ratio})")


        if address_found_to_remove:
            current_user_addresses.remove(address_found_to_remove)
            if not current_user_addresses: # Если список адресов пуст после удаления
                user_addresses.pop(user.id, None)
            else:
                user_addresses[user.id] = current_user_addresses
            await save_tracked_data_async()
            await message.reply_text(
                translations.get("address_removed", {}).get(lang, "Address '{address}' removed.").format(address=f"{address_found_to_remove['region']}, {address_found_to_remove['street']}"),
                reply_markup=reply_markup_for_lang(lang)
            )
        else:
            await message.reply_text(
                translations.get("address_not_found_to_remove",{}).get(lang,"Address to remove not found: {address}").format(address=address_to_remove_text),
                reply_markup=reply_markup_for_lang(lang)
            )
        context.user_data[USER_DATA_STEP] = UserSteps.NONE

    elif current_step == UserSteps.AWAITING_CLEAR_ALL_CONFIRMATION:
        if text == translations.get("yes", {}).get(lang, "Yes"):
            user_addresses.pop(user.id, None) # Удаляем все адреса для этого пользователя
            user_notified_headers.pop(user.id, None) # И историю уведомлений
            await save_tracked_data_async()
            await message.reply_text(translations.get("all_addresses_cleared",{}).get(lang, "All addresses cleared."), reply_markup=reply_markup_for_lang(lang))
        elif text == translations.get("no", {}).get(lang, "No"):
            await message.reply_text(translations.get("cancelled", {}).get(lang, "Cancelled."), reply_markup=reply_markup_for_lang(lang))
        else: # Если пользователь ввел что-то кроме "Да" или "Нет"
            await message.reply_text(translations.get("please_confirm_yes_no", {}).get(lang, "Please confirm (Yes/No)."), reply_markup=reply_markup_for_lang(lang))
            return # Остаемся на этом шаге
        context.user_data[USER_DATA_STEP] = UserSteps.NONE

    elif current_step == UserSteps.AWAITING_ADDRESS_TO_CHECK:
        street_to_check = text
        # Для проверки берем первый регион из сохраненных адресов пользователя, или Ереван по умолчанию
        default_region_to_check = "Երևան" # Армянское название для внутреннего использования, если нет других
        if lang == "ru": default_region_to_check = "Ереван"
        elif lang == "en": default_region_to_check = "Yerevan"

        if user_addresses.get(user.id) and user_addresses[user.id]:
            default_region_to_check = user_addresses[user.id][0]["region"] # Используем регион первого добавленного адреса

        log_info(f"Checking immediate shutdown for: Street='{street_to_check}', Region='{default_region_to_check}'")
        shutdown_types = await is_shutdown_for_address_now(street_to_check, default_region_to_check)

        if shutdown_types:
            types_str = ", ".join([translations.get(f"{stype}_off_short", {}).get(lang, stype.capitalize()) for stype in shutdown_types])
            await message.reply_text(
                translations.get("shutdown_check_found", {}).get(lang, "⚠️ Outages found for '{address}': {types}.").format(address=f"{default_region_to_check}, {street_to_check}", types=types_str),
                reply_markup=reply_markup_for_lang(lang)
            )
        else:
            await message.reply_text(
                translations.get("shutdown_check_not_found", {}).get(lang, "✅ No outages found for '{address}'.").format(address=f"{default_region_to_check}, {street_to_check}"),
                reply_markup=reply_markup_for_lang(lang)
            )
        context.user_data[USER_DATA_STEP] = UserSteps.NONE

    elif current_step == UserSteps.AWAITING_FREQUENCY_CHOICE:
        log_info(f"[smart_bot] Calling handle_frequency_choice from handlers.py for user {user.id}, text '{text}'")
        # Эта функция из handlers.py должна сама сбросить шаг
        await handle_frequency_choice(update, context)

    elif current_step == UserSteps.AWAITING_SUBSCRIPTION_CHOICE:
        log_info(f"[smart_bot] User {user.id} is in AWAITING_SUBSCRIPTION_CHOICE but sent text '{text}'. This step expects a CallbackQuery.")
        await message.reply_text(
            translations.get("use_inline_buttons_for_subscription", {}).get(lang, "Please use the buttons under the message to choose a subscription."),
            reply_markup=reply_markup_for_lang(lang) # Возвращаем в главное меню
        )
        context.user_data[USER_DATA_STEP] = UserSteps.NONE # Сбрасываем шаг

    else: # Неизвестный шаг или текст, который не должен был прийти на этом шаге
        log_info(f"[smart_bot] Unhandled step {current_step} for user {user.id} with text '{text}'. Resetting step to NONE.")
        await message.reply_text(translations.get("unknown_command", {}).get(lang, "Unknown state. Returning to menu."), reply_markup=reply_markup_for_lang(lang))
        context.user_data[USER_DATA_STEP] = UserSteps.NONE
    return

# --- ПЕРИОДИЧЕСКИЕ ЗАДАЧИ ---
async def periodic_site_check_job(context: ContextTypes.DEFAULT_TYPE):
    now = time()
    user_ids_with_settings = list(user_settings.keys()) # Копируем ключи, чтобы избежать проблем при изменении словаря во время итерации
    log_info(f"[smart_bot] periodic_site_check_job running for {len(user_ids_with_settings)} users with settings.")

    active_checks = 0
    for user_id in user_ids_with_settings:
        if not user_addresses.get(user_id): # Пропускаем пользователей без адресов
            continue

        current_user_s = user_settings.get(user_id, {}) # Получаем настройки пользователя
        # Частота по умолчанию - из бесплатного тарифа, если не указана
        default_frequency = premium_tiers.get("Free", {}).get("interval", 21600) # 6 часов
        frequency_seconds = current_user_s.get("frequency", default_frequency)

        if last_check_time.get(user_id, 0) + frequency_seconds <= now:
            log_info(f"Запуск периодической проверки для пользователя {user_id} (частота: {frequency_seconds}s)")
            try:
                await check_site_for_user(user_id, context)
                last_check_time[user_id] = now # Обновляем время последней проверки
                active_checks += 1
            except Exception as e:
                log_error(f"Ошибка во время периодической проверки для пользователя {user_id}: {e}", exc=e)
        
        # Логика показа рекламы (пример)
        # if current_user_s.get("ads_enabled", premium_tiers.get("Free", {}).get("ad_enabled", True)):
        #     if last_ad_time.get(user_id, 0) + config.ad_interval_seconds <= now:
        #         lang = current_user_s.get("lang", "hy")
        #         ad_message = translations.get("ad_message_example", {}).get(lang, "This is an ad! Consider upgrading for an ad-free experience.")
        #         try:
        #             await context.bot.send_message(chat_id=user_id, text=ad_message)
        #             last_ad_time[user_id] = now
        #             log_info(f"Показана реклама пользователю {user_id}")
        #         except Exception as e:
        #             log_error(f"Ошибка отправки рекламы пользователю {user_id}: {e}")
    log_info(f"[smart_bot] periodic_site_check_job completed. Active checks performed: {active_checks}")

# --- ИНИЦИАЛИЗАЦИЯ И ЗАПУСК БОТА ---
async def post_init_hook(application: Application):
    log_info("[smart_bot] Bot post_init_hook: Загрузка данных...")
    await load_user_settings_async()
    await load_tracked_data_async()
    # Восстановление last_check_time из user_settings, если необходимо
    # for user_id, settings in user_settings.items():
    #     if "last_successful_check" in settings: # Пример, если бы мы сохраняли это
    #         last_check_time[user_id] = settings["last_successful_check"]
    log_info("Данные бота успешно загружены.")

async def post_shutdown_hook(application: Application):
    log_info("[smart_bot] Bot post_shutdown_hook: Сохранение данных...")
    # Можно добавить сохранение last_check_time в user_settings, если это критично
    # for user_id, lct in last_check_time.items():
    #    if user_id in user_settings:
    #        user_settings[user_id]["last_successful_check"] = lct
    await save_user_settings_async()
    await save_tracked_data_async()
    log_info("Данные успешно сохранены перед выключением.")

def main():
    log_info(f"ЗАПУСК НОВОЙ ВЕРСИИ БОТА (с исправлениями от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    log_info(f"Запуск CheckSiteUpdateBot с уровнем логирования: {config.log_level}")

    # Указываем путь для файла PicklePersistence внутри папки backups
    persistence_filepath = config.backup_dir / "bot_session_data.pickle"
    ptb_persistence = PicklePersistence(filepath=persistence_filepath)

    # Данные, передаваемые в обработчики через application.bot_data
    # Эти данные должны быть доступны синхронно, если это необходимо в синхронных частях PTB
    # Асинхронные функции и изменяемые глобальные словари передаются "как есть"
    bot_shared_data = {
        "user_settings_ref": user_settings, # Ссылка на глобальный словарь
        "save_user_settings_async_func": save_user_settings_async,
        "reply_markup_for_lang_func": reply_markup_for_lang,
        "UserStepsEnum": UserSteps,
        "USER_DATA_STEP_KEY": USER_DATA_STEP, # Ключ для user_data
        "USER_DATA_LANG_KEY": USER_DATA_LANG, # Ключ для user_data
        "premium_tiers_ref": premium_tiers, # Ссылка на словарь тарифов
        "user_addresses_ref": user_addresses, # Ссылка на глобальный словарь
        "save_tracked_data_async_func": save_tracked_data_async,
        "translations_ref": translations, # Ссылка на словарь переводов
        "config_ref": config, # Ссылка на объект конфигурации
        # Дополнительные данные, если нужны в handlers.py или других модулях
    }
    log_info(f"[smart_bot] main: bot_shared_data prepared. Keys: {list(bot_shared_data.keys())}")
    for key, value in bot_shared_data.items():
        if callable(value):
            log_info(f"[smart_bot] main: bot_shared_data function '{key}' is callable.")
        elif value is None: # Проверяем, если какое-то значение None, это может быть проблемой
            log_error(f"[smart_bot] main: bot_shared_data CRITICAL: '{key}' is None. Это может привести к ошибкам в обработчиках.")

    application_builder = ApplicationBuilder().token(config.telegram_token)
    application_builder.persistence(ptb_persistence)
    application_builder.post_init(post_init_hook) # Вызывается после инициализации Application и JobQueue
    application_builder.post_shutdown(post_shutdown_hook) # Вызывается перед остановкой
    application = application_builder.build()
    application.bot_data.update(bot_shared_data)
    log_info("[smart_bot] main: Application built successfully with bot_data.")

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("language", change_language_command))
    application.add_handler(CommandHandler("set_frequency", set_frequency_command)) # из handlers.py
    application.add_handler(CommandHandler("list_addresses", address_list_command)) # синоним для "Показать адреса"
    application.add_handler(CommandHandler("stats", show_statistics_command))
    application.add_handler(CommandHandler("help", show_help_command))
    # Дополнительные команды, если нужны (например, /subscribe, /addaddress <регион> <улица>)
    log_info("[smart_bot] main: CommandHandlers registered.")

    # Обработчик текстовых сообщений (должен идти после CommandHandlers)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Обработчик CallbackQuery (для Inline кнопок)
    application.add_handler(CallbackQueryHandler(handle_subscription_callback, pattern=f"^{CALLBACK_PREFIX_SUBSCRIBE}"))
    # application.add_handler(CallbackQueryHandler(handle_payment_callback, pattern=f"^{CALLBACK_PREFIX_PAY}")) # Для будущей оплаты
    log_info("[smart_bot] main: Message and CallbackQuery Handlers registered.")

    # Настройка и запуск периодической задачи
    # Интервал можно сделать настраиваемым или зависящим от общей нагрузки
    job_queue_interval_seconds = 60 # Как часто сам JobQueue проверяет, не пора ли запустить задачу
    application.job_queue.run_repeating(
        periodic_site_check_job,
        interval=job_queue_interval_seconds,
        first=10 # Запустить через 10 секунд после старта бота
    )
    log_info(f"[smart_bot] main: JobQueue task 'periodic_site_check_job' scheduled to run every {job_queue_interval_seconds}s.")

    log_info("Бот начал опрос...")
    application.run_polling()
    log_info("Бот остановлен.")

if __name__ == "__main__":
    main()

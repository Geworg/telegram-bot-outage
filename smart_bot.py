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
    return context.user_data.get("lang", "en")

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

def admin_only(func: Callable):
    """Decorator to restrict command access to admins."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in ADMIN_IDS:
            lang = get_user_lang(context)
            await update.message.reply_text(get_text("admin_unauthorized", lang))
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
    user = update.effective_user
    user_in_db = await db_manager.get_user(user.id)

    if not user_in_db:
        context.user_data["step"] = UserSteps.AWAITING_INITIAL_LANG.name
        user_lang_code = user.language_code if user.language_code in ['ru', 'hy'] else 'en'
        prompt = get_text("initial_language_prompt", user_lang_code)
        buttons = [
            [KeyboardButton("🇦🇲 Հայերեն" + (" (continue)" if user_lang_code == 'hy' else ""))],
            [KeyboardButton("🇷🇺 Русский" + (" (продолжить)" if user_lang_code == 'ru' else ""))],
            [KeyboardButton("🇬🇧 English" + (" (continue)" if user_lang_code == 'en' else ""))]
        ]
        keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(prompt, reply_markup=keyboard)
        await db_manager.create_or_update_user(user.id, user_lang_code)
        context.user_data["lang"] = user_lang_code
    else:
        context.user_data["lang"] = user_in_db['language_code']
        context.user_data["step"] = UserSteps.NONE.name
        lang = user_in_db['language_code']
        await update.message.reply_text(
            get_text("menu_message", lang),
            reply_markup=get_main_menu_keyboard(lang)
        )

async def add_address_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    context.user_data["step"] = UserSteps.AWAITING_REGION.name
    buttons = [[KeyboardButton(r)] for r in REGIONS_LIST]
    buttons.append([KeyboardButton(get_text("cancel", lang))])
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(get_text("choose_region", lang), reply_markup=keyboard)

async def remove_address_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(context)
    addresses = await db_manager.get_user_addresses(user_id)
    if not addresses:
        await update.message.reply_text(get_text("no_addresses_yet", lang))
        return

    buttons = [[InlineKeyboardButton(addr['full_address_text'], callback_data=f"remove_addr_{addr['address_id']}")] for addr in addresses]
    buttons.append([InlineKeyboardButton(get_text("cancel", lang), callback_data="cancel_action")])
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(get_text("select_address_to_remove", lang), reply_markup=keyboard)

async def my_addresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(context)
    addresses = await db_manager.get_user_addresses(user_id)

    if not addresses:
        await update.message.reply_text(get_text("no_addresses_yet", lang))
        return

    response_text = get_text("your_addresses_list_title", lang) + "\n\n"
    for addr in addresses:
        response_text += f"📍 `{addr['full_address_text']}`\n"
    
    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN_V2)

async def frequency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(context)
    user = await db_manager.get_user(user_id)
    if not user: return
    
    user_tier = "Ultra" if user_id in ADMIN_IDS else user['tier']
    user_tier_index = TIER_ORDER.index(user_tier)
    
    buttons = []
    for key, option in FREQUENCY_OPTIONS.items():
        if user_tier_index >= TIER_ORDER.index(option['tier']):
            buttons.append([KeyboardButton(option[lang])])
            
    current_freq_text = get_text("frequency_current", lang)
    for option in FREQUENCY_OPTIONS.values():
        if option['interval'] == user['frequency_seconds']:
            current_freq_text += f" {option[lang]}"
            break
            
    keyboard = ReplyKeyboardMarkup(buttons + [[KeyboardButton(get_text("cancel", lang))]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(f"{current_freq_text}\n\n{get_text('frequency_prompt', lang)}", reply_markup=keyboard)
    context.user_data["step"] = UserSteps.AWAITING_FREQUENCY.name

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(context)
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(get_text("admin_unauthorized", lang))
        return
    system_stats = await db_manager.get_system_stats()
    user_notif_count = await db_manager.get_user_notification_count(user_id)
    await update.message.reply_text(get_text("stats_message", lang, **system_stats, user_notifications=user_notif_count), parse_mode=ParseMode.MARKDOWN_V2)

async def clear_addresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    buttons = [[
        InlineKeyboardButton(get_text("yes", lang), callback_data="confirm_clear_yes"),
        InlineKeyboardButton(get_text("no", lang), callback_data="cancel_action")
    ]]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(get_text("clear_addresses_prompt", lang), reply_markup=keyboard)

async def qa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    buttons = [
        [InlineKeyboardButton(get_text("qa_placeholder_q1", lang), callback_data="qa_1")],
        [InlineKeyboardButton(get_text("qa_placeholder_q2", lang), callback_data="qa_2")],
        [InlineKeyboardButton(get_text("support_btn", lang), callback_data="qa_support")],
        [InlineKeyboardButton(get_text("back_btn", lang), callback_data="qa_back")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(get_text("qa_title", lang), reply_markup=keyboard)

async def sound_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(context)
    user = await db_manager.get_user(user_id)
    if not user: return
    
    sound_status = get_text("sound_on_status", lang) if user['notification_sound_enabled'] else get_text("sound_off_status", lang)
    silent_status = get_text("silent_mode_on_status", lang, start=user['silent_mode_start_time'].strftime('%H:%M'), end=user['silent_mode_end_time'].strftime('%H:%M')) if user['silent_mode_enabled'] else get_text("silent_mode_off_status", lang)
    
    text = f"{get_text('sound_settings_title', lang)}\n\n{sound_status}\n{silent_status}"
    
    buttons = [
        [InlineKeyboardButton(get_text("sound_toggle_off" if user['notification_sound_enabled'] else "sound_toggle_on", lang), callback_data="sound_toggle_main")],
        [InlineKeyboardButton(get_text("silent_mode_toggle_off" if user['silent_mode_enabled'] else "silent_mode_toggle_on", lang), callback_data="sound_toggle_silent")],
        [InlineKeyboardButton(get_text("back_btn", lang), callback_data="sound_back")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    
    target_message = update.callback_query.message if update.callback_query else update.message
    try:
        if update.callback_query:
            await target_message.edit_text(text, reply_markup=keyboard)
        else:
            await target_message.reply_text(text, reply_markup=keyboard)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            log.warning(f"Failed to edit sound menu: {e}")

@admin_only
async def maintenance_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db_manager.set_bot_status("maintenance_mode", "true")
    lang = get_user_lang(context)
    await update.message.reply_text(get_text("maintenance_on_feedback", lang))
    log.info(f"Admin {update.effective_user.id} enabled maintenance mode.")

@admin_only
async def maintenance_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db_manager.set_bot_status("maintenance_mode", "false")
    lang = get_user_lang(context)
    await update.message.reply_text(get_text("maintenance_off_feedback", lang))
    log.info(f"Admin {update.effective_user.id} disabled maintenance mode.")

# --- Main Message Router ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_maintenance = await db_manager.get_bot_status("maintenance_mode")
    if is_maintenance == "true" and update.effective_user.id not in ADMIN_IDS:
        lang = get_user_lang(context)
        await update.message.reply_text(get_text("maintenance_user_notification", lang))
        return

    step = context.user_data.get("step")
    lang = get_user_lang(context)

    if update.message and update.message.text == get_text("cancel", lang):
        context.user_data["step"] = UserSteps.NONE.name
        await update.message.reply_text(get_text("action_cancelled", lang), reply_markup=get_main_menu_keyboard(lang))
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

    handler = step_handlers.get(step, handle_main_menu_text)
    await handler(update, context)

async def handle_main_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
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
        await update.message.reply_text(get_text("unknown_command", lang), reply_markup=get_main_menu_keyboard(lang))

# --- State Logic Handlers ---
async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    lang_code = 'en'
    if 'Հայերեն' in text: lang_code = 'hy'
    elif 'Русский' in text: lang_code = 'ru'
    
    context.user_data["lang"] = lang_code
    await db_manager.update_user_language(update.effective_user.id, lang_code)
    
    await update.message.reply_text(
        get_text("language_set_success", lang_code),
        reply_markup=get_main_menu_keyboard(lang_code)
    )
    context.user_data["step"] = UserSteps.NONE.name
    
async def handle_region_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    region = update.message.text
    if region not in REGIONS_LIST:
        lang = get_user_lang(context)
        await update.message.reply_text(get_text("unknown_command", lang))
        return
        
    context.user_data["selected_region"] = region
    lang = get_user_lang(context)
    
    await update.message.reply_text(get_text("enter_street", lang, region=region), reply_markup=ReplyKeyboardRemove())
    context.user_data["step"] = UserSteps.AWAITING_STREET.name
    
async def handle_street_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    lang = get_user_lang(context)
    
    typing_task = asyncio.create_task(send_typing_periodically(context, chat_id))
    try:
        street_text = update.message.text
        region = context.user_data.get("selected_region", "Armenia")
        full_query = f"{region}, {street_text}"

        await update.message.reply_text(get_text("address_verifying", lang))
        
        verified_address = await api_clients.get_verified_address_from_yandex(full_query)

        if verified_address and verified_address.get('full_address'):
            context.user_data["verified_address_cache"] = verified_address
            buttons = [[
                InlineKeyboardButton(get_text("yes", lang), callback_data="confirm_address_yes"),
                InlineKeyboardButton(get_text("no", lang), callback_data="cancel_action")
            ]]
            keyboard = InlineKeyboardMarkup(buttons)
            escaped_address = verified_address['full_address'].replace('-', '\\-').replace('.', '\\.')
            await update.message.reply_text(
                get_text("address_confirm_prompt", lang, address=escaped_address),
                reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await update.message.reply_text(get_text("address_not_found_yandex", lang))
            context.user_data["step"] = UserSteps.AWAITING_STREET.name
    finally:
        typing_task.cancel()

async def handle_frequency_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    lang = get_user_lang(context)
    user_id = update.effective_user.id
    
    selected_interval = None
    for option in FREQUENCY_OPTIONS.values():
        if option[lang] == text:
            selected_interval = option['interval']
            break
            
    if selected_interval:
        await db_manager.update_user_frequency(user_id, selected_interval)
        await update.message.reply_text(get_text("frequency_set_success", lang), reply_markup=get_main_menu_keyboard(lang))
        context.user_data["step"] = UserSteps.NONE.name
    else:
        await update.message.reply_text(get_text("unknown_command", lang))

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_lang(context)
    
    if not SUPPORT_CHAT_ID:
        log.error("SUPPORT_CHAT_ID is not set, cannot forward message.")
        await update.message.reply_text(get_text("error_generic", lang), reply_markup=get_main_menu_keyboard(lang))
        context.user_data["step"] = UserSteps.NONE.name
        return
        
    support_message = get_text("support_message_from_user", "en", user_mention=user.mention_markdown_v2(), user_id=user.id, message=update.message.text)
    await context.bot.send_message(chat_id=SUPPORT_CHAT_ID, text=support_message, parse_mode=ParseMode.MARKDOWN_V2)
    await update.message.reply_text(get_text("support_message_sent", lang), reply_markup=get_main_menu_keyboard(lang))
    context.user_data["step"] = UserSteps.NONE.name

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
    text = update.message.text
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
        await update.message.reply_text(confirm_text, reply_markup=keyboard)
        context.user_data['pending_silent_times'] = {'start': start, 'end': end}
        return
    else:
        await update.message.reply_text(get_text("invalid_time_interval", lang))
        return

# --- Callback Query Handlers ---
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("remove_addr_"): await remove_address_callback(update, context)
    elif data == "confirm_address_yes": await confirm_address_callback(update, context)
    elif data == "confirm_clear_yes": await clear_addresses_callback(update, context)
    elif data.startswith("qa_"): await qa_callback_handler(update, context)
    elif data.startswith("sound_"): await sound_callback_handler(update, context)
    elif data == "cancel_action": await cancel_callback(update, context)
    elif data.startswith('silent_confirm_yes:'):
        # Подтверждение тихого режима
        _, start, end = data.split(':')
        settings = {"silent_mode_start_time": start, "silent_mode_end_time": end, "silent_mode_enabled": True}
        await db_manager.update_user_sound_settings(query.from_user.id, settings)
        lang = get_user_lang(context)
        await query.edit_message_text(get_text("silent_interval_set", lang), reply_markup=ReplyKeyboardRemove())
        context.user_data["step"] = UserSteps.NONE.name
        await sound_command(update, context)
        return
    elif data == 'silent_confirm_edit':
        lang = get_user_lang(context)
        await query.edit_message_text(get_text("enter_silent_interval_prompt", lang))
        context.user_data["step"] = UserSteps.AWAITING_SILENT_INTERVAL.name
        return
        
async def remove_address_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = get_user_lang(context)
    address_id_to_remove = int(query.data.split('_')[2])
    await db_manager.remove_user_address(address_id_to_remove, query.from_user.id)
    await query.edit_message_text(get_text("address_removed_success", lang))
    await context.bot.send_message(chat_id=query.message.chat_id, text=get_text("menu_message", lang), reply_markup=get_main_menu_keyboard(lang))

async def confirm_address_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    lang = get_user_lang(context)
    address_data = context.user_data.pop("verified_address_cache", None)

    if not address_data:
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

    context.user_data["step"] = UserSteps.NONE.name
    await context.bot.send_message(
        chat_id=query.message.chat_id, text=get_text("menu_message", lang),
        reply_markup=get_main_menu_keyboard(lang)
    )

async def check_outages_for_new_address(update: Update, context: ContextTypes.DEFAULT_TYPE, address_data: dict):
    lang = get_user_lang(context)
    chat_id = update.effective_chat.id
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

async def clear_addresses_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db_manager.clear_all_user_addresses(update.callback_query.from_user.id)
    lang = get_user_lang(context)
    await update.callback_query.edit_message_text(get_text("all_addresses_cleared", lang))
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text("menu_message", lang), reply_markup=get_main_menu_keyboard(lang))

async def qa_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = get_user_lang(context)
    action = query.data.split('_')[-1]
    
    if action == "support":
        context.user_data["step"] = UserSteps.AWAITING_SUPPORT_MESSAGE.name
        await query.edit_message_text(get_text("support_prompt", lang))
    elif action == "back":
        await query.delete()
    else:
        answer_key = f"qa_placeholder_a{action}"
        await query.answer(text=get_text(answer_key, lang), show_alert=True)
        
async def sound_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    action = query.data
    
    if action == "sound_toggle_main":
        user = await db_manager.get_user(user_id)
        await db_manager.update_user_sound_settings(user_id, {"notification_sound_enabled": not user['notification_sound_enabled']})
    elif action == "sound_toggle_silent":
        user = await db_manager.get_user(user_id)
        if user['silent_mode_enabled']:
            await db_manager.update_user_sound_settings(user_id, {"silent_mode_enabled": False})
        else:
            lang = get_user_lang(context)
            context.user_data["step"] = UserSteps.AWAITING_SILENT_INTERVAL.name
            await query.message.reply_text(get_text("enter_silent_interval_prompt", lang))
            return

    elif action == "sound_back":
        await query.delete()
        return
        
    await sound_command(update, context)

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    try:
        await update.callback_query.edit_message_text(text=get_text("action_cancelled", lang))
    except BadRequest:
        pass
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text("menu_message", lang), reply_markup=get_main_menu_keyboard(lang))

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

    log.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

# --- Standard Library ---
import asyncio
import logging
import os
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
    BotCommand
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
from telegram.error import Forbidden

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
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# --- Constants ---
class UserSteps(Enum):
    NONE = auto()
    AWAITING_INITIAL_LANG = auto()
    AWAITING_REGION = auto()
    AWAITING_STREET = auto()
    AWAITING_ADDRESS_CONFIRM = auto()
    AWAITING_ADDRESS_REMOVE = auto()
    AWAITING_FREQUENCY = auto()

ADMIN_IDS = [int(i) for i in os.getenv("ADMIN_USER_IDS", "").split(',') if i]
TIER_ORDER = ["Free", "Basic", "Premium", "Ultra"]
FREQUENCY_OPTIONS = {
    "Free_6h": {"interval": 21600, "hy": "⏱ 6 ժամ", "ru": "⏱ 6 часов", "en": "⏱ 6 hours", "tier": "Free"},
    "Free_12h": {"interval": 43200, "hy": "⏱ 12 ժամ", "ru": "⏱ 12 часов","en": "⏱ 12 hours", "tier": "Free"},
    "Basic_1h": {"interval": 3600, "hy": "⏱ 1 ժամ", "ru": "⏱ 1 час", "en": "⏱ 1 hour", "tier": "Basic"},
    "Premium_30m": {"interval": 1800, "hy": "⏱ 30 րոպե", "ru": "⏱ 30 минут","en": "⏱ 30 min", "tier": "Premium"},
    "Ultra_15m": {"interval": 900, "hy": "⏱ 15 րոպե", "ru": "⏱ 15 минут","en": "⏱ 15 min", "tier": "Ultra"},
}

# --- Helper Functions ---
def get_user_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang", "en")

def get_text(key: str, lang: str, **kwargs) -> str:
    return translations.get(key, {}).get(lang, f"<{key}>").format(**kwargs)

# --- Typing Indicator ---
async def send_typing_periodically(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Sends 'typing' action every 4.5 seconds until cancelled."""
    try:
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4.5)
    except asyncio.CancelledError:
        pass # This is expected when the task is cancelled

# --- Keyboard Generation ---
def get_main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(get_text("add_address_btn", lang)), KeyboardButton(get_text("remove_address_btn", lang))],
        [KeyboardButton(get_text("show_addresses_btn", lang)), KeyboardButton(get_text("set_frequency_btn", lang))],
        [KeyboardButton(get_text("language_btn", lang)), KeyboardButton(get_text("help_btn", lang))],
        [KeyboardButton(get_text("stats_btn", lang))]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- Decorators ---
def admin_only(func: Callable):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in ADMIN_IDS:
            lang = get_user_lang(context)
            await update.message.reply_text(get_text("admin_unauthorized", lang))
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_in_db = await db_manager.get_user(user.id)

    if not user_in_db:
        # New user
        context.user_data["step"] = UserSteps.AWAITING_INITIAL_LANG.name
        user_lang_code = user.language_code if user.language_code in ['ru', 'hy'] else 'en'
        
        prompt = get_text("initial_language_prompt", user_lang_code)
        
        # Language buttons with flags and context
        buttons = [
            [KeyboardButton("🇦🇲 Հայերեն" + (" (continue)" if user_lang_code == 'hy' else ""))],
            [KeyboardButton("🇷🇺 Русский" + (" (продолжить)" if user_lang_code == 'ru' else ""))],
            [KeyboardButton("🇬🇧 English" + (" (continue)" if user_lang_code == 'en' else ""))]
        ]
        keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(prompt, reply_markup=keyboard)
        await db_manager.create_or_update_user(user.id, user_lang_code)
    else:
        # Existing user
        context.user_data["lang"] = user_in_db['language_code']
        context.user_data["step"] = UserSteps.NONE.name
        lang = get_user_lang(context)
        await update.message.reply_text(
            get_text("menu_message", lang),
            reply_markup=get_main_menu_keyboard(lang)
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    await update.message.reply_text(get_text("help_text", lang), parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
    
async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    buttons = [
        [KeyboardButton("🇦🇲 Հայերեն")],
        [KeyboardButton("🇷🇺 Русский")],
        [KeyboardButton("🇬🇧 English")]
    ]
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(get_text("change_language_prompt", lang), reply_markup=keyboard)
    context.user_data["step"] = UserSteps.AWAITING_INITIAL_LANG.name

# --- Admin Handlers ---
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

@admin_only
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = " ".join(context.args)
    if not message_text:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    lang = get_user_lang(context)
    await update.message.reply_text(get_text("broadcast_started", lang))
    
    # This is a simplified broadcast. For very large user bases, this would need to be a background job.
    all_users = [] # You'd get this from db_manager.get_all_users()
    sent_count = 0
    for user in all_users:
        try:
            await context.bot.send_message(chat_id=user['user_id'], text=message_text)
            sent_count += 1
            await asyncio.sleep(0.1) # Avoid rate limits
        except Forbidden:
            log.warning(f"Broadcast failed for user {user['user_id']}: Bot was blocked.")
        except Exception as e:
            log.error(f"Broadcast failed for user {user['user_id']}: {e}")

    await update.message.reply_text(get_text("broadcast_finished", lang, count=sent_count))

# --- Message Handler / Router ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check maintenance mode
    is_maintenance = await db_manager.get_bot_status("maintenance_mode")
    if is_maintenance == "true" and update.effective_user.id not in ADMIN_IDS:
        lang = get_user_lang(context)
        await update.message.reply_text(get_text("maintenance_user_notification", lang))
        return

    # Route based on user step
    step = context.user_data.get("step", UserSteps.NONE.name)
    
    if step == UserSteps.AWAITING_INITIAL_LANG.name:
        await handle_language_selection(update, context)
    elif step == UserSteps.AWAITING_REGION.name:
        await handle_region_selection(update, context)
    elif step == UserSteps.AWAITING_STREET.name:
        await handle_street_input(update, context)
    # Add other steps here
    else: # Default to main menu actions
        await handle_main_menu_text(update, context)

# --- State-based Logic Handlers ---
async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    lang_code = 'en'
    if 'Հայերեն' in text:
        lang_code = 'hy'
    elif 'Русский' in text:
        lang_code = 'ru'
    
    context.user_data["lang"] = lang_code
    await db_manager.update_user_language(update.effective_user.id, lang_code)
    
    lang = get_user_lang(context) # Get the newly set language
    await update.message.reply_text(
        get_text("language_set_success", lang),
        reply_markup=get_main_menu_keyboard(lang)
    )
    context.user_data["step"] = UserSteps.NONE.name

async def handle_main_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    lang = get_user_lang(context)
    
    if text == get_text("add_address_btn", lang):
        # Present region keyboard
        context.user_data["step"] = UserSteps.AWAITING_REGION.name
        # You need a list of regions for the keyboard
        # For now, a placeholder
        regions = ["Երևան", "Շիրակ", "Լոռի"] # This should be comprehensive
        buttons = [[KeyboardButton(r)] for r in regions]
        keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(get_text("choose_region", lang), reply_markup=keyboard)

    elif text == get_text("help_btn", lang):
        await help_command(update, context)
    
    elif text == get_text("language_btn", lang):
        await language_command(update, context)
        
    else:
        await update.message.reply_text(
            get_text("unknown_command", lang),
            reply_markup=get_main_menu_keyboard(lang)
        )

async def handle_region_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    region = update.message.text
    # You should validate this against your known list of regions
    context.user_data["selected_region"] = region
    lang = get_user_lang(context)
    
    await update.message.reply_text(
        get_text("enter_street", lang, region=region),
        reply_markup=ReplyKeyboardRemove()
    )
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
            # Ask for confirmation
            buttons = [[
                InlineKeyboardButton(get_text("yes", lang), callback_data="confirm_address_yes"),
                InlineKeyboardButton(get_text("no", lang), callback_data="confirm_address_no")
            ]]
            keyboard = InlineKeyboardMarkup(buttons)
            await update.message.reply_text(
                get_text("address_confirm_prompt", lang, address=verified_address['full_address']),
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            context.user_data["step"] = UserSteps.AWAITING_ADDRESS_CONFIRM.name
        else:
            await update.message.reply_text(get_text("address_not_found_yandex", lang))
            # Go back to main menu or re-prompt for street
            context.user_data["step"] = UserSteps.NONE.name
            await update.message.reply_text(get_text("menu_message", lang), reply_markup=get_main_menu_keyboard(lang))

    finally:
        typing_task.cancel()

# --- Callback Query Handlers ---
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_user_lang(context)

    if query.data == "confirm_address_yes":
        address_data = context.user_data.get("verified_address_cache")
        if not address_data:
            await query.edit_message_text("Error: Cached address data not found.")
            return

        success = await db_manager.add_user_address(
            user_id=update.effective_user.id,
            region=address_data.get('province') or address_data.get('area'),
            street=f"{address_data.get('street', '')}, {address_data.get('house', '')}".strip(', '),
            full_address=address_data.get('full_address'),
            lat=address_data.get('latitude'),
            lon=address_data.get('longitude')
        )
        
        if success:
            await query.edit_message_text(get_text("address_added_success", lang))
        else:
            await query.edit_message_text(get_text("address_already_exists", lang))

        context.user_data["step"] = UserSteps.NONE.name
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=get_text("menu_message", lang),
            reply_markup=get_main_menu_keyboard(lang)
        )

    elif query.data == "confirm_address_no":
        await query.edit_message_text(get_text("action_cancelled", lang))
        context.user_data["step"] = UserSteps.NONE.name
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=get_text("menu_message", lang),
            reply_markup=get_main_menu_keyboard(lang)
        )


# --- Periodic Jobs ---
async def periodic_site_check_job(context: ContextTypes.DEFAULT_TYPE):
    # This job should now run the new parsing functions
    log.info("Starting periodic site check job...")
    await asyncio.gather(
        parse_all_water_announcements_async(),
        parse_all_gas_announcements_async(),
        parse_all_electric_announcements_async()
    )
    # The notification logic will be a separate job
    log.info("Periodic site check job finished.")


# --- Application Setup ---
async def post_init(application: Application):
    """Runs after the bot is initialized."""
    await db_manager.init_db_pool()
    ai_engine.load_models()
    
    # Set bot commands for different languages
    await application.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Get help information"),
        BotCommand("language", "Change language")
    ])
    log.info("Bot is initialized, DB pool and AI models are ready.")

async def post_shutdown(application: Application):
    """Runs before the bot shuts down."""
    await db_manager.close_db_pool()
    log.info("Bot is shutting down, DB pool closed.")

def main():
    """Start the bot."""
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        log.critical("TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
        sys.exit(1)

    application = (
        ApplicationBuilder()
        .token(os.getenv("TELEGRAM_BOT_TOKEN"))
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("language", language_command))
    application.add_handler(CommandHandler("maintenance_on", maintenance_on_command))
    application.add_handler(CommandHandler("maintenance_off", maintenance_off_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    # Schedule jobs
    job_queue = application.job_queue
    job_interval = int(os.getenv("JOB_INTERVAL_SECONDS", "1800")) # Default 30 mins
    job_queue.run_repeating(periodic_site_check_job, interval=job_interval, first=10, name="site_check")
    log.info(f"Scheduled 'site_check' job to run every {job_interval} seconds.")

    # Start the Bot
    log.info("Starting bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

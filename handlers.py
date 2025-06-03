# handlers.py
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton # KeyboardButton may not be needed here if using main menu from smart_bot
from telegram.ext import ContextTypes
from logger import log_error, log_info, log_warning

# NOTE: Большая часть логики работы с частотой и ее выбором была интегрирована 
# в `smart_bot.py` (в `handle_text_message` и соответствующие команды/коллбэки).
# Этот файл может быть сокращен или его функции адаптированы для вызова из `smart_bot.py`.
# Глобальные user_settings и translations теперь лучше получать из context или передавать как параметры.
# Опции частоты для выбора пользователем.
FREQUENCY_OPTIONS = {
    "Free_6h": {"interval": 21600, "hy": "⏱ 6 ժամ", "ru": "⏱ 6 часов", "en": "⏱ 6 hours", "tier": "Free"},
    "Free_12h": {"interval": 43200, "hy": "⏱ 12 ժամ", "ru": "⏱ 12 часов", "en": "⏱ 12 hours", "tier": "Free"},
    "Free_24h": {"interval": 86400, "hy": "⏱ 24 ժամ", "ru": "⏱ 24 часа", "en": "⏱ 24 hours", "tier": "Free"},
    "Basic_1h": {"interval": 3600, "hy": "⏱ 1 ժամ", "ru": "⏱ 1 час", "en": "⏱ 1 hour", "tier": "Basic"},
    "Premium_30m": {"interval": 1800, "hy": "⏱ 30 րոպե", "ru": "⏱ 30 минут", "en": "⏱ 30 min", "tier": "Premium"},
    "Premium_15m": {"interval": 900, "hy": "⏱ 15 րոպե", "ru": "⏱ 15 минут", "en": "⏱ 15 min", "tier": "Premium"},
    "Ultra_5m": {"interval": 300, "hy": "⏱ 5 րոպե", "ru": "⏱ 5 минут", "en": "⏱ 5 min", "tier": "Ultra"},
    "Ultra_1m": {"interval": 60, "hy": "⏱ 1 րոպե", "ru": "⏱ 1 минута", "en": "⏱ 1 min", "tier": "Ultra"},
}

# Tiers definition (example, actual tiers might be more complex)
TIER_HIERARCHY = {"Free": 0, "Basic": 1, "Premium": 2, "Ultra": 3}
# USER_DATA_STEP_KEY = "current_step" # Defined in smart_bot.py
# class UserStepsEnum(Enum): # Defined in smart_bot.py
#     NONE = auto()
#     AWAITING_FREQUENCY_CHOICE = auto()

async def set_frequency_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user_settings_ref: dict, translations_ref: dict) -> None:
    """Initiates the process of setting notification frequency."""
    # NOTE: user_settings_ref and translations_ref are passed if this is called from smart_bot.
    # In PTB, these would ideally come from context.user_data and a shared translations module.
    user = update.effective_user
    if not user: return
    # lang = user_settings_ref.get(str(user.id), {}).get("lang", "hy") # Old way
    lang = context.user_data.get("lang", "hy") # PTB way
    # user_current_tier_name = user_settings_ref.get(str(user.id), {}).get("current_tier", "Free") # Old way
    user_current_tier_name = context.user_data.get("current_tier", "Free") # PTB way
    user_current_tier_level = TIER_HIERARCHY.get(user_current_tier_name, 0)
    buttons = []
    for key, option in FREQUENCY_OPTIONS.items():
        option_tier_level = TIER_HIERARCHY.get(option["tier"], 0)
        if option_tier_level <= user_current_tier_level: # Only show options available for user's tier or lower
            buttons.append([KeyboardButton(option[lang])])
    # Add cancel button using translations
    # cancel_btn_text = translations_ref.get("cancel_btn", {}).get(lang, "Cancel")
    # buttons.append([KeyboardButton(cancel_btn_text)])
    if not buttons: # Should not happen if Free tier options exist
        await update.message.reply_text(translations_ref.get("no_frequency_options_available", {}).get(lang, "No frequency options available for your tier."))
        return
    # This function now primarily used to display options.
    # The actual choice handling is better done via a text handler in smart_bot.py
    # that routes to handle_frequency_choice, or via inline keyboard callbacks.
    # Using ReplyKeyboard for now as per original structure.
    # from smart_bot import get_translation # Avoid circular import if possible
    # For now, assume translations_ref is the main translations dict.
    cancel_btn_text = translations_ref.get("cancel_btn", {}).get(lang, "Cancel")
    buttons.append([KeyboardButton(cancel_btn_text)])
    reply_markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    prompt_text = translations_ref.get("frequency_options_prompt", {}).get(lang, "Select update frequency:")
    await update.message.reply_text(prompt_text, reply_markup=reply_markup)
    # context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.AWAITING_FREQUENCY_CHOICE # Using enum from smart_bot
    # This step is now set in smart_bot.py before calling this or similar logic.
    # Or, if this is a direct command, it sets the step.
    # from smart_bot import USER_DATA_STEP_KEY, UserStepsEnum # For clarity
    context.user_data["current_step"] = "AWAITING_FREQUENCY_CHOICE" # Simpler string if enum not shared easily
    log_info(f"User {user.id} prompted for frequency choice. Current step: AWAITING_FREQUENCY_CHOICE")

async def handle_frequency_choice(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  user_settings_ref: dict, # Passed from smart_bot
                                  translations_ref: dict,  # Passed from smart_bot
                                  save_user_settings_async_func: callable # Passed from smart_bot
                                 ) -> None:
    """Handles the user's text input for frequency choice."""
    # NOTE: This function is designed to be called by the main text handler in smart_bot.py
    # when current_step is AWAITING_FREQUENCY_CHOICE.
    user = update.effective_user
    if not user or not update.message or not update.message.text:
        return
    user_id_str = str(user.id)
    text = update.message.text
    # lang = user_settings_ref.get(user_id_str, {}).get("lang", "hy") # Old way
    lang = context.user_data.get("lang", "hy") # PTB way
    # from smart_bot import get_reply_markup_for_lang, USER_DATA_STEP_KEY, UserStepsEnum # For main keyboard and step enum
    # Simplification: assume main reply markup generation is in smart_bot
    # reply_markup_for_lang_func = context.application.bot_data.get('get_main_keyboard_func') # If passed via bot_data
    # --- Simpler way to get main keyboard (if smart_bot provides it) ---
    # For now, construct a minimal one or assume it's handled after this.
    from smart_bot import get_reply_markup_for_lang # Direct import (can cause issues if not careful with structure)
    # Handle "Cancel" first
    # cancel_btn_text = translations_ref.get("cancel_btn", {}).get(lang, "Cancel")
    # if text == cancel_btn_text:
    #     await update.message.reply_text(
    #         translations_ref.get("action_cancelled", {}).get(lang, "Action cancelled."),
    #         reply_markup=get_reply_markup_for_lang(lang, context, user_id_str) # Back to main menu
    #     )
    #     context.user_data["current_step"] = "NONE" # UserStepsEnum.NONE
    #     return
    # --- Cancel is handled by main text handler in smart_bot.py ---
    selected_option_key = None
    selected_interval = None
    for key, option_details in FREQUENCY_OPTIONS.items():
        if option_details.get(lang) == text:
            selected_option_key = key
            selected_interval = option_details["interval"]
            break
    if selected_option_key and selected_interval is not None:
        # current_s = user_settings_ref.get(user_id_str, {}) # Old way
        # user_current_tier_name = current_s.get("current_tier", "Free") # Old way
        user_current_tier_name = context.user_data.get("current_tier", "Free") # PTB way
        user_tier_level = TIER_HIERARCHY.get(user_current_tier_name, 0)
        chosen_option_details = FREQUENCY_OPTIONS[selected_option_key]
        required_tier_for_choice = chosen_option_details["tier"]
        required_tier_level = TIER_HIERARCHY.get(required_tier_for_choice, 0)
        can_select_frequency = True
        if required_tier_level > user_tier_level:
            log_warning(f"User {user_id_str} (Tier: {user_current_tier_name}) tried to select frequency '{text}' requiring Tier {required_tier_for_choice}. DENIED.")
            can_select_frequency = False
        if not can_select_frequency:
            await update.message.reply_text(
                translations_ref.get("premium_required_for_frequency", {}).get(lang, "This frequency requires a higher tier."),
                reply_markup=get_reply_markup_for_lang(lang, context, user_id_str) # Main menu
            )
            # context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
            context.user_data["current_step"] = "NONE"
            return
        # Update frequency in context.user_data (PTB will persist this)
        context.user_data["frequency"] = selected_interval
        # user_settings_ref[user_id_str] = current_s # Old way: modifying global dict
        # await save_user_settings_async_func() # Old way: calling passed save function
        log_info(f"[handlers] User {user_id_str} frequency set to {selected_interval} ({text}). Settings will be persisted by PTB.")
        await update.message.reply_text(
            translations_ref.get("frequency_set", {}).get(lang, "Frequency set!"),
            reply_markup=get_reply_markup_for_lang(lang, context, user_id_str) # Main menu
        )
        # context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
        context.user_data["current_step"] = "NONE"
    else:
        log_warning(f"[handlers] User {user_id_str} text '{text}' didn't match frequency option for lang '{lang}'.")
        # user_s = user_settings_ref.get(user_id_str, {}) # Old way
        # user_current_tier_name = user_s.get("current_tier", "Free") # Old way
        user_current_tier_name = context.user_data.get("current_tier", "Free") # PTB way
        await update.message.reply_text(
            translations_ref.get("invalid_frequency_option", {}).get(lang, "Invalid choice. Please select from the list or Cancel."),
            # No change in reply_markup, keep frequency options keyboard if an error, or back to main menu
             reply_markup=get_reply_markup_for_lang(lang, context, user_id_str) # Main menu on error
        )
        # Keep step as AWAITING_FREQUENCY_CHOICE to allow retry, or clear it.
        # Clearing it and showing main menu might be less confusing.
        context.user_data["current_step"] = "NONE"
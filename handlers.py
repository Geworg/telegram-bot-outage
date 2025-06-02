# handlers.py
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
# translations импортируется глобально в smart_bot, здесь он будет доступен через context.application.bot_data
from logger import log_error, log_info, log_warning # Добавлен log_warning

# Опции частоты для выбора пользователем. Премиум-опции должны соответствовать тарифам.
# Эти опции могут быть динамически отфильтрованы на основе подписки пользователя.
FREQUENCY_OPTIONS = {
    # Бесплатные
    "6h": {"interval": 21600, "hy": "⏱ 6 ժամ", "ru": "⏱ 6 часов", "en": "⏱ 6 hours"},
    "12h": {"interval": 43200, "hy": "⏱ 12 ժամ", "ru": "⏱ 12 часов", "en": "⏱ 12 hours"},
    "24h": {"interval": 86400, "hy": "⏱ 24 ժամ", "ru": "⏱ 24 часа", "en": "⏱ 24 hours"},
    # Платные (соответствуют Basic, Premium, Ultra из premium_tiers в smart_bot.py)
    "1h": {"interval": 3600, "hy": "⏱ 1 ժամ", "ru": "⏱ 1 час", "en": "⏱ 1 hour", "premium_min_tier": "Basic"},
    "15m": {"interval": 900, "hy": "⏱ 15 րոպե", "ru": "⏱ 15 минут", "en": "⏱ 15 min", "premium_min_tier": "Premium"},
    "5m": {"interval": 300, "hy": "⏱ 5 րոպե", "ru": "⏱ 5 минут", "en": "⏱ 5 min", "premium_min_tier": "Ultra"},
    # Экстремальные (могут быть для самых дорогих тарифов или админов)
    # "1m": {"interval": 60, "hy": "⏱ 1 րոպե", "ru": "⏱ 1 минута", "en": "⏱ 1 min", "premium_min_tier": "Ultra"},
}
# Порядок тарифов для определения "минимально необходимого"
TIER_ORDER = ["Free", "Basic", "Premium", "Ultra"]


def get_frequency_keyboard(lang: str, user_tier: str, translations_dict: dict) -> ReplyKeyboardMarkup:
    log_info(f"[handlers] get_frequency_keyboard called for lang: {lang}, user_tier: {user_tier}")
    keyboard = []
    row = []
    
    user_tier_index = TIER_ORDER.index(user_tier) if user_tier in TIER_ORDER else 0

    for key, option_details in FREQUENCY_OPTIONS.items():
        required_tier_key = option_details.get("premium_min_tier")
        if required_tier_key:
            required_tier_index = TIER_ORDER.index(required_tier_key) if required_tier_key in TIER_ORDER else float('inf')
            if user_tier_index < required_tier_index: # Если уровень пользователя ниже требуемого
                continue # Пропускаем эту опцию

        row.append(KeyboardButton(option_details[lang]))
        if len(row) == 2: # По две кнопки в ряду
            keyboard.append(row)
            row = []
    if row: # Добавляем оставшиеся кнопки, если их нечетное количество
        keyboard.append(row)
    
    cancel_text = translations_dict.get("cancel", {}).get(lang, "Cancel")
    keyboard.append([KeyboardButton(cancel_text)])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


async def set_frequency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_info("[handlers] set_frequency_command called")
    if not update.message:
        log_error("[handlers] set_frequency_command: update.message is None")
        return

    # Получаем необходимые данные и Enum из bot_data (передано из smart_bot.py)
    bot_data = context.application.bot_data
    USER_DATA_LANG_KEY = bot_data.get("USER_DATA_LANG_KEY", "current_language")
    UserStepsEnum = bot_data.get("UserStepsEnum")
    USER_DATA_STEP_KEY = bot_data.get("USER_DATA_STEP_KEY", "current_step")
    user_settings_ref = bot_data.get("user_settings_ref")
    translations_ref = bot_data.get("translations_ref") # Получаем переводы

    if not all([UserStepsEnum, USER_DATA_STEP_KEY, user_settings_ref is not None, translations_ref is not None]):
        log_error("[handlers] set_frequency_command: Critical data (UserStepsEnum, keys, user_settings_ref, translations_ref) not found in bot_data.")
        # Отправляем сообщение на языке по умолчанию или на английском, если переводы недоступны
        error_message = "A system error occurred while trying to set frequency. Please report this to the admin."
        if translations_ref:
            lang_for_error = context.user_data.get(USER_DATA_LANG_KEY, "en") # Пытаемся использовать язык пользователя или 'en'
            error_message = translations_ref.get("error_generic_admin", {}).get(lang_for_error, error_message)
        await update.message.reply_text(error_message)
        return

    lang = context.user_data.get(USER_DATA_LANG_KEY, "hy") # Язык пользователя
    user_id = update.effective_user.id
    log_info(f"[handlers] set_frequency_command for user {user_id}, lang: {lang}")

    user_s = user_settings_ref.get(user_id, {})
    user_current_tier = user_s.get("current_tier", "Free") # Получаем текущий тариф пользователя
    log_info(f"[handlers] User {user_id} current tier: {user_current_tier}")

    prompt_text = translations_ref.get("set_frequency_prompt", {}).get(lang, "Please choose a check frequency:")
    await update.message.reply_text(
        prompt_text,
        reply_markup=get_frequency_keyboard(lang, user_current_tier, translations_ref)
    )
    context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.AWAITING_FREQUENCY_CHOICE
    log_info(f"[handlers] User {user_id} step set to AWAITING_FREQUENCY_CHOICE")


async def handle_frequency_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_info("[handlers] handle_frequency_choice called")
    if not update.message or not update.message.text:
        log_error("[handlers] handle_frequency_choice: update.message or text is None")
        return

    # Загрузка необходимых данных и функций из bot_data
    bot_data = context.application.bot_data
    user_settings_ref = bot_data.get("user_settings_ref")
    save_user_settings_async_func = bot_data.get("save_user_settings_async_func")
    reply_markup_for_lang_func = bot_data.get("reply_markup_for_lang_func")
    UserStepsEnum = bot_data.get("UserStepsEnum")
    USER_DATA_STEP_KEY = bot_data.get("USER_DATA_STEP_KEY")
    USER_DATA_LANG_KEY = bot_data.get("USER_DATA_LANG_KEY")
    translations_ref = bot_data.get("translations_ref")
    premium_tiers_ref = bot_data.get("premium_tiers_ref")


    if not all([user_settings_ref is not None, save_user_settings_async_func,
                reply_markup_for_lang_func, UserStepsEnum, USER_DATA_STEP_KEY,
                USER_DATA_LANG_KEY, translations_ref is not None, premium_tiers_ref is not None]):
        log_error("[handlers] handle_frequency_choice: Critical shared data not found in context.application.bot_data. Check main() in smart_bot.py!")
        error_message = "A system error occurred while choosing frequency. Please report to admin."
        # Попытка отправить сообщение об ошибке на языке пользователя или на английском
        lang_for_error = context.user_data.get(USER_DATA_LANG_KEY, "en")
        if translations_ref: # Если переводы вообще доступны
             error_message = translations_ref.get("error_generic_admin", {}).get(lang_for_error, error_message)
        await update.message.reply_text(error_message)
        if UserStepsEnum and USER_DATA_STEP_KEY: # Попытка сбросить шаг, если Enum и ключ шага доступны
            context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
        return

    user_id = update.effective_user.id
    lang = context.user_data.get(USER_DATA_LANG_KEY, "hy")
    text = update.message.text.strip() # Текст с кнопки частоты
    log_info(f"[handlers] handle_frequency_choice for user {user_id}, lang: {lang}, received text: '{text}'")

    # Обработка отмены
    if text == translations_ref.get("cancel", {}).get(lang, "FallbackCancel"):
        log_info(f"[handlers] User {user_id} cancelled frequency choice.")
        await update.message.reply_text(
            translations_ref.get("cancelled_frequency", {}).get(lang, "Frequency selection cancelled."),
            reply_markup=reply_markup_for_lang_func(lang) # Функция для главной клавиатуры
        )
        context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
        return

    selected_interval = None
    selected_option_key = None
    for key, option_details in FREQUENCY_OPTIONS.items():
        if text == option_details.get(lang): # Сравниваем с локализованным текстом кнопки
            selected_interval = option_details["interval"]
            selected_option_key = key
            log_info(f"[handlers] User {user_id} selected frequency option key: {key}, interval: {selected_interval}")
            break

    if selected_interval is not None and selected_option_key is not None:
        current_s = user_settings_ref.get(user_id, {})
        user_current_tier = current_s.get("current_tier", "Free")
        user_current_tier_index = TIER_ORDER.index(user_current_tier) if user_current_tier in TIER_ORDER else 0

        # Проверка, доступна ли выбранная частота для текущего тарифа пользователя
        chosen_freq_details = FREQUENCY_OPTIONS[selected_option_key]
        required_tier_for_freq_key = chosen_freq_details.get("premium_min_tier")
        
        can_select_frequency = True
        if required_tier_for_freq_key:
            required_tier_index = TIER_ORDER.index(required_tier_for_freq_key) if required_tier_for_freq_key in TIER_ORDER else float('inf')
            if user_current_tier_index < required_tier_index:
                can_select_frequency = False
        
        if not can_select_frequency:
            log_info(f"[handlers] User {user_id} (tier: {user_current_tier}) tried to select frequency '{selected_option_key}' which requires tier '{required_tier_for_freq_key}'.")
            await update.message.reply_text(
                translations_ref.get("premium_required_for_frequency", {}).get(lang, "This frequency requires a higher subscription tier."),
                reply_markup=reply_markup_for_lang_func(lang) # Главное меню
            )
            context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
            return

        # Если частота доступна, обновляем настройки
        current_s["frequency"] = selected_interval
        # ads_enabled зависит от ТЕКУЩЕГО тарифа пользователя, а не от выбранной частоты
        # current_s["ads_enabled"] = premium_tiers_ref.get(user_current_tier, {}).get("ad_enabled", True)

        user_settings_ref[user_id] = current_s # Обновляем настройки в общем словаре
        await save_user_settings_async_func() # Вызываем функцию сохранения из smart_bot.py
        log_info(f"[handlers] User {user_id} frequency set to {selected_interval}. Settings saved.")

        await update.message.reply_text(
            translations_ref.get("frequency_set", {}).get(lang, "Frequency set successfully!"),
            reply_markup=reply_markup_for_lang_func(lang) # Главное меню
        )
        context.user_data[USER_DATA_STEP_KEY] = UserStepsEnum.NONE
    else:
        log_warning(f"[handlers] User {user_id} entered text '{text}' which didn't match any frequency option for lang '{lang}'.")
        user_s = user_settings_ref.get(user_id, {})
        user_current_tier = user_s.get("current_tier", "Free")
        await update.message.reply_text(
            translations_ref.get("please_use_buttons_for_frequency", {}).get(lang, "Please use the buttons to select frequency."),
            reply_markup=get_frequency_keyboard(lang, user_current_tier, translations_ref) # Показываем клавиатуру снова
        )
        # Шаг не меняем, ждем корректного нажатия кнопки
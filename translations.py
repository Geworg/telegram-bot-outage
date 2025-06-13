import urllib.parse

# --- Constants for Contact Information ---
CONTACT_PHONE_NUMBER = "+37412345678"  # Replace with your actual phone number
CONTACT_ADDRESS_TEXT = "Gyumri, Shirak Province, Armenia" # Replace with your address
ENCODED_ADDRESS_FOR_MAP = urllib.parse.quote(CONTACT_ADDRESS_TEXT)
MAP_URL = f"https://www.google.com/maps/search/?api=1&query={ENCODED_ADDRESS_FOR_MAP}"

CLICKABLE_PHONE_MD = f"📞 [{CONTACT_PHONE_NUMBER}](tel:{CONTACT_PHONE_NUMBER.replace('+', '')})"
CLICKABLE_ADDRESS_MD = f"📍 [{CONTACT_ADDRESS_TEXT}]({MAP_URL})"

# --- Tier Labels ---
TIER_LABELS = {
    "Free": {"hy": "Անվճար", "ru": "Бесплатный", "en": "Free"},
    "Basic": {"hy": "Հիմնական", "ru": "Базовый", "en": "Basic"},
    "Premium": {"hy": "Պրեմիում", "ru": "Премиум", "en": "Premium"},
    "Ultra": {"hy": "Ուլտրա", "ru": "Ультра", "en": "Ultra"},
}

# --- Translations Dictionary ---
translations = {
    # --- Main Menu Buttons ---
    "add_address_btn": {"hy": "➕ Ավելացնել հասցե", "ru": "➕ Добавить адрес", "en": "➕ Add Address"},
    "remove_address_btn": {"hy": "➖ Հեռացնել հասցե", "ru": "➖ Удалить адрес", "en": "➖ Remove Address"},
    "show_addresses_btn": {"hy": "📋 Իմ հասցեները", "ru": "📋 Мои адреса", "en": "📋 My Addresses"},
    "set_frequency_btn": {"hy": "⏱️ Սահմանել հաճախականությունը", "ru": "⏱️ Задать частоту", "en": "⏱️ Set Frequency"},
    "sound_settings_btn": {"hy": "🎵 Ձայնի կարգավորումներ", "ru": "🎵 Настройки звука", "en": "🎵 Sound Settings"},
    "help_btn": {"hy": "❓ Օգնություն", "ru": "❓ Помощь", "en": "❓ Help"},
    "language_btn": {"hy": "🌐 Փոխել լեզուն", "ru": "🌐 Сменить язык", "en": "🌐 Change Language"},
    "stats_btn": {"hy": "📊 Վիճակագրություն", "ru": "📊 Статистика", "en": "📊 Statistics"},
    
    # --- General UI ---
    "cancel": {"hy": "❌ Չեղարկել", "ru": "❌ Отменить", "en": "❌ Cancel"},
    "yes": {"hy": "✅ Այո", "ru": "✅ Да", "en": "✅ Yes"},
    "no": {"hy": "Ոչ", "ru": "Нет", "en": "No"},
    "back_btn": {"hy": "⬅️ Հետ", "ru": "⬅️ Назад", "en": "⬅️ Back"},
    "menu_message": {"hy": "Գլխավոր մենյու:", "ru": "Главное меню:", "en": "Main menu:"},
    "action_cancelled": {"hy": "Գործողությունը չեղարկվեց։", "ru": "Действие отменено.", "en": "Action cancelled."},
    "error_generic": {"hy": "Տեղի է ունեցել սխալ։ Խնդրում եմ փորձել մի փոքր ուշ։", "ru": "Произошла ошибка. Пожалуйста, попробуйте немного позже.", "en": "An error occurred. Please try again later."},
    "use_buttons_prompt": {"hy": "Խնդրում եմ օգտվել ներքևի կոճակներից:", "ru": "Пожалуйста, воспользуйтесь кнопками ниже.", "en": "Please use the buttons below."},
    "unknown_command": {"hy": "Անհայտ հրաման։", "ru": "Неизвестная команда.", "en": "Unknown command."},

    # --- Language Selection ---
    "initial_language_prompt": {
        "ru": "Пожалуйста, выберите язык бота, используя кнопки ниже.",
        "hy": "Խնդրում ենք ընտրել բոտի լեզուն՝ օգտագործելով ստորև տրված կոճակները։",
        "en": "Please select the bot's language using the buttons below."
    },
    "change_language_prompt": {"hy": "Ընտրեք նոր լեզուն:", "ru": "Выберите новый язык:", "en": "Choose the new language:"},
    "language_set_success": {"hy": "Լեզուն փոխված է հայերենի։", "ru": "Язык изменён на русский.", "en": "Language changed to English."},
    
    # --- Address Management ---
    "choose_region": {"hy": "Ընտրեք ձեր մարզը կամ Երևանի շրջանը:", "ru": "Выберите вашу область или район Еревана:", "en": "Choose your region or Yerevan district:"},
    "enter_street": {"hy": "Ընտրված է՝ {region}։\nԱյժմ մուտքագրեք ձեր փողոցի և շենքի համարը (օրինակ՝ Աբովյան 5):", "ru": "Выбрано: {region}.\nТеперь введите вашу улицу и номер дома (например, Абовяна 5):", "en": "Selected: {region}.\nNow, enter your street and house number (e.g., Abovyan 5):"},
    "address_verifying": {"hy": "⏳ Ստուգում եմ հասցեն...", "ru": "⏳ Проверяю адрес...", "en": "⏳ Verifying address..."},
    "address_not_found_yandex": {"hy": "Ցավոք, չհաջողվեց գտնել այդպիսի հասցե։ Խնդրում եմ, փորձեք նորից՝ ավելի ճշգրիտ մուտքագրելով։", "ru": "К сожалению, не удалось найти такой адрес. Пожалуйста, попробуйте снова, введя его точнее.", "en": "Sorry, that address could not be found. Please try again with a more precise entry."},
    "address_confirm_prompt": {"hy": "Հայտնաբերվել է հետևյալ հասցեն՝\n\n`{address}`\n\nՊահպանե՞լ այն:", "ru": "Найден следующий адрес:\n\n`{address}`\n\nСохранить его?", "en": "The following address was found:\n\n`{address}`\n\nSave it?"},
    "address_added_success": {"hy": "✅ Հասցեն հաջողությամբ ավելացվեց։", "ru": "✅ Адрес успешно добавлен.", "en": "✅ Address added successfully."},
    "address_already_exists": {"hy": "ℹ️ Այս հասցեն արդեն գոյություն ունի ձեր ցուցակում։", "ru": "ℹ️ Этот адрес уже существует в вашем списке.", "en": "ℹ️ This address already exists in your list."},
    "no_addresses_yet": {"hy": "Դուք դեռ հասցեներ չեք ավելացրել։", "ru": "У вас пока нет добавленных адресов.", "en": "You haven't added any addresses yet."},
    "your_addresses_list_title": {"hy": "Ձեր պահպանված հասցեները:", "ru": "Ваши сохранённые адреса:", "en": "Your saved addresses:"},
    "select_address_to_remove": {"hy": "Ընտրեք հասցեն, որը ցանկանում եք հեռացնել։", "ru": "Выберите адрес для удаления.", "en": "Select an address to remove."},
    "address_removed_success": {"hy": "✅ Հասցեն հեռացված է։", "ru": "✅ Адрес удалён.", "en": "✅ Address removed."},

    # --- Frequency & Subscription ---
    "set_frequency_prompt": {"hy": "Ընտրեք ստուգման հաճախականությունը։ Որքան հաճախակի է ստուգումը, այնքան ավելի բարձր է պահանջվող բաժանորդագրության մակարդակը։", "ru": "Выберите частоту проверки. Чем чаще проверка, тем выше требуемый уровень подписки.", "en": "Choose the check frequency. The more frequent the check, the higher the required subscription tier."},
    "frequency_set_success": {"hy": "⏱️ Ստուգման հաճախականությունը սահմանված է։", "ru": "⏱️ Частота проверки установлена.", "en": "⏱️ Check frequency has been set."},
    "frequency_tier_required": {"hy": "Այս հաճախականության համար պահանջվում է «{tier}» կամ ավելի բարձր մակարդակի բաժանորդագրություն։", "ru": "Для этой частоты требуется подписка уровня «{tier}» или выше.", "en": "This frequency requires a '{tier}' subscription or higher."},
    "ad_message": {"hy": "⭐ Ավելի արագ ծանուցումների համար անցեք վճարովի բաժանորդագրության։ /help", "ru": "⭐ Для более быстрых уведомлений перейдите на платную подписку. /help", "en": "⭐ For faster notifications, upgrade your subscription. /help"},

    # --- Help & Stats ---
    "help_text": {
        "hy": (
            "**CheckSiteUpdateBot**-ը օգնում է ձեզ տեղեկացված մնալ Հայաստանում կոմունալ ծառայությունների անջատումների մասին։\n\n"
            "• `➕ Ավելացնել հասցե` - Հետևել նոր հասցեի։\n"
            "• `➖ Հեռացնել հասցե` - Դադարեցնել հասցեին հետևելը։\n"
            "• `📋 Իմ հասցեները` - Դիտել ձեր հասցեների ցանկը։\n"
            "• `⏱️ Սահմանել հաճախականությունը` - Ընտրել, թե որքան հաճախ ստուգվեն կայքերը։\n"
            "• `🎵 Ձայնի կարգավորումներ` - Կառավարել ծանուցումների ձայնը։\n\n"
            "Հարցերի դեպքում կարող եք կապնվել մեզ հետ:\n"
            f"{CLICKABLE_PHONE_MD}\n"
            f"{CLICKABLE_ADDRESS_MD}"
        ),
        "ru": (
            "**CheckSiteUpdateBot** помогает вам оставаться в курсе отключений коммунальных услуг в Армении.\n\n"
            "• `➕ Добавить адрес` - Отслеживать новый адрес.\n"
            "• `➖ Удалить адрес` - Прекратить отслеживание адреса.\n"
            "• `📋 Мои адреса` - Посмотреть список ваших адресов.\n"
            "• `⏱️ Задать частоту` - Выбрать, как часто проверять сайты.\n"
            "• `🎵 Настройки звука` - Управлять звуком уведомлений.\n\n"
            "Если у вас есть вопросы, вы можете связаться с нами:\n"
            f"{CLICKABLE_PHONE_MD}\n"
            f"{CLICKABLE_ADDRESS_MD}"
        ),
        "en": (
            "**CheckSiteUpdateBot** helps you stay informed about utility outages in Armenia.\n\n"
            "• `➕ Add Address` - Track a new address.\n"
            "• `➖ Remove Address` - Stop tracking an address.\n"
            "• `📋 My Addresses` - View your list of addresses.\n"
            "• `⏱️ Set Frequency` - Choose how often to check the sites.\n"
            "• `🎵 Sound Settings` - Manage notification sounds.\n\n"
            "If you have any questions, you can contact us:\n"
            f"{CLICKABLE_PHONE_MD}\n"
            f"{CLICKABLE_ADDRESS_MD}"
        )
    },
    "stats_message": {"hy": "📊 *Վիճակագրություն*\n\n👥 *Ընդհանուր օգտատերեր:* {total_users}\n📍 *Ընդհանուր հասցեներ:* {total_addresses}\n\n👤 *Ձեր տվյալները*\n✉️ *Ստացված ծանուցումներ:* {user_notifications}", "ru": "📊 *Статистика*\n\n👥 *Всего пользователей:* {total_users}\n📍 *Всего адресов:* {total_addresses}\n\n👤 *Ваши данные*\n✉️ *Получено уведомлений:* {user_notifications}", "en": "📊 *Statistics*\n\n👥 *Total Users:* {total_users}\n📍 *Total Addresses:* {total_addresses}\n\n👤 *Your Stats*\n✉️ *Notifications Received:* {user_notifications}"},

    # --- Notifications ---
    "outage_notification_header": {"hy": "⚠️ *Ուշադրություն, անջատում*", "ru": "⚠️ *Внимание, отключение*", "en": "⚠️ *Attention, Outage*"},
    "outage_water": {"hy": "💧 *Ջուր*", "ru": "💧 *Вода*", "en": "💧 *Water*"},
    "outage_gas": {"hy": "🔥 *Գազ*", "ru": "🔥 *Газ*", "en": "🔥 *Gas*"},
    "outage_electric": {"hy": "💡 *Էլեկտրաէներգիա*", "ru": "💡 *Электричество*", "en": "💡 *Electricity*"},
    "outage_period": {"hy": "Ժամանակահատված", "ru": "Период", "en": "Period"},
    "outage_status": {"hy": "Կարգավիճակ", "ru": "Статус", "en": "Status"},
    "outage_locations": {"hy": "Տեղանքներ", "ru": "Местоположения", "en": "Locations"},

    # --- Admin ---
    "admin_unauthorized": {"hy": "Դուք իրավասու չեք այս հրամանը կատարելու։", "ru": "Вы не авторизованы для выполнения этой команды.", "en": "You are not authorized to execute this command."},
    "maintenance_on_feedback": {"hy": "⚙️ Սպասարկման ռեժիմը միացված է։", "ru": "⚙️ Режим обслуживания включен.", "en": "⚙️ Maintenance mode is ON."},
    "maintenance_off_feedback": {"hy": "✅ Սպասարկման ռեժիմը անջատված է։", "ru": "✅ Режим обслуживания выключен.", "en": "✅ Maintenance mode is OFF."},
    "maintenance_user_notification": {"hy": "⚙️ Բոտը ժամանակավորապես սպասարկման մեջ է։ Խնդրում ենք փորձել մի փոքր ուշ։", "ru": "⚙️ Бот временно находится на техобслуживании. Пожалуйста, попробуйте позже.", "en": "⚙️ The bot is temporarily under maintenance. Please try again later."},
    "broadcast_started": {"hy": "📢 Սկսում եմ հաղորդագրության ուղարկումը։", "ru": "📢 Начинаю рассылку сообщения.", "en": "📢 Starting broadcast."},
    "broadcast_finished": {"hy": "✅ Հաղորդագրությունն ուղարկված է {count} օգտատիրոջ։", "ru": "✅ Сообщение отправлено {count} пользователям.", "en": "✅ Message sent to {count} users."},
}

import os
import urllib.parse

# --- Constants for Contact Information ---
# It's better to get the support chat ID from environment variables
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID")
CONTACT_PHONE_NUMBER = "+37412345678"  # Replace with your actual phone number
CONTACT_ADDRESS_TEXT = "Gyumri, Shirak Province, Armenia" # Replace with your address
ENCODED_ADDRESS_FOR_MAP = urllib.parse.quote(CONTACT_ADDRESS_TEXT)
MAP_URL = f"https://www.google.com/maps/search/?api=1&query={ENCODED_ADDRESS_FOR_MAP}"

# Using markdown_v2 escape for phone number
CLICKABLE_PHONE_MD = f"📞 [{CONTACT_PHONE_NUMBER.replace('+', '\\+')}]({CONTACT_PHONE_NUMBER})"
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
    # --- Main Menu & Commands ---
    "add_address_btn": {"hy": "➕ Ավելացնել հասցե", "ru": "➕ Добавить адрес", "en": "➕ Add Address"},
    "remove_address_btn": {"hy": "➖ Հեռացնել հասցե", "ru": "➖ Удалить адрес", "en": "➖ Remove Address"},
    "my_addresses_btn": {"hy": "📋 Իմ հասցեները", "ru": "📋 Мои адреса", "en": "📋 My Addresses"},
    "frequency_btn": {"hy": "⏱️ Ստուգման հաճախականություն", "ru": "⏱️ Частота проверок", "en": "⏱️ Check Frequency"},
    "sound_btn": {"hy": "🎵 Ձայնի կարգավորումներ", "ru": "🎵 Настройки звука", "en": "🎵 Sound Settings"},
    "qa_btn": {"hy": "💬 Հարց ու պատասխան", "ru": "💬 Вопрос-ответ", "en": "💬 Q&A"},
    "stats_btn": {"hy": "📊 Վիճակագրություն", "ru": "📊 Статистика", "en": "📊 Statistics"},
    "clear_addresses_btn": {"hy": "🗑️ Մաքրել բոլոր հասցեները", "ru": "🗑️ Очистить все адреса", "en": "🗑️ Clear All Addresses"},

    # --- General UI ---
    "cancel": {"hy": "❌ Չեղարկել", "ru": "❌ Отменить", "en": "❌ Cancel"},
    "yes": {"hy": "✅ Այո", "ru": "✅ Да", "en": "✅ Yes"},
    "no": {"hy": "Ոչ", "ru": "Нет", "en": "No"},
    "back_btn": {"hy": "⬅️ Հետ", "ru": "⬅️ Назад", "en": "⬅️ Back"},
    "menu_message": {"hy": "Գլխավոր մենյու:", "ru": "Главное меню:", "en": "Main menu:"},
    "action_cancelled": {"hy": "Գործողությունը չեղարկվեց։", "ru": "Действие отменено.", "en": "Action cancelled."},
    "error_generic": {"hy": "Տեղի է ունեցել սխալ։ Խնդրում եմ փորձել մի փոքր ուշ։", "ru": "Произошла ошибка. Пожалуйста, попробуйте немного позже.", "en": "An error occurred. Please try again later."},
    "unknown_command": {"hy": "Անհայտ հրաման։ Օգտվեք կոճակներից։", "ru": "Неизвестная команда. Воспользуйтесь кнопками.", "en": "Unknown command. Please use the buttons."},

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
    "clear_addresses_prompt": {"hy": "⚠️ Վստա՞հ եք, որ ցանկանում եք հեռացնել ձեր բոլոր հասցեները։ Այս գործողությունը հետ շրջել հնարավոր չէ։", "ru": "⚠️ Вы уверены, что хотите удалить все свои адреса? Это действие необратимо.", "en": "⚠️ Are you sure you want to remove all your addresses? This action cannot be undone."},
    "all_addresses_cleared": {"hy": "🗑️ Ձեր բոլոր հասցեները հեռացված են։", "ru": "🗑️ Все ваши адреса были удалены.", "en": "🗑️ All your addresses have been removed."},
    "outage_check_on_add_title": {"hy": "🔍 *Արագ ստուգում նոր հասցեի համար...*", "ru": "🔍 *Быстрая проверка для нового адреса...*", "en": "🔍 *Quick check for new address...*"},
    "outage_check_on_add_none_found": {"hy": "✅ Այս պահին ձեր նոր հասցեի համար ակտիվ կամ սպասվող անջատումներ չեն հայտնաբերվել։", "ru": "✅ На данный момент для вашего нового адреса не найдено активных или предстоящих отключений.", "en": "✅ No active or upcoming outages found for your new address at this time."},
    "outage_check_on_add_found": {"hy": "⚠️ *Ուշադրություն։* Հայտնաբերվել են անջատումներ ձեր նոր հասցեի համար։", "ru": "⚠️ *Внимание!* Обнаружены отключения для вашего нового адреса:", "en": "⚠️ *Attention!* Outages found for your new address:"},

    # --- Frequency ---
    "frequency_prompt": {"hy": "Ընտրեք ստուգման հաճախականությունը։", "ru": "Выберите частоту проверки:", "en": "Choose the check frequency:"},
    "frequency_current": {"hy": "Ընթացիկ՝", "ru": "Текущая:", "en": "Current:"},
    "frequency_set_success": {"hy": "⏱️ Ստուգման հաճախականությունը փոխված է։", "ru": "⏱️ Частота проверки изменена.", "en": "⏱️ Check frequency has been changed."},
    "frequency_tier_required": {"hy": "Այս հաճախականության համար պահանջվում է «{tier}» կամ ավելի բարձր մակարդակի բաժանորդագրություն։", "ru": "Для этой частоты требуется подписка уровня «{tier}» или выше.", "en": "This frequency requires a '{tier}' subscription or higher."},

    # --- Sound Settings ---
    "sound_settings_title": {"hy": "🎵 Ձայնի կարգավորումներ", "ru": "🎵 Настройки звука", "en": "🎵 Sound Settings"},
    "sound_toggle_on": {"hy": "🔊 Միացնել բոլոր ձայները", "ru": "🔊 Включить все звуки", "en": "🔊 Enable All Sounds"},
    "sound_toggle_off": {"hy": "🔇 Անջատել բոլոր ձայները", "ru": "🔇 Выключить все звуки", "en": "🔇 Disable All Sounds"},
    "sound_on_status": {"hy": "Հիմնական ձայնը՝ ✅ Միացված", "ru": "Основной звук: ✅ Включен", "en": "Main Sound: ✅ Enabled"},
    "sound_off_status": {"hy": "Հիմնական ձայնը՝ ❌ Անջատված", "ru": "Основной звук: ❌ Выключен", "en": "Main Sound: ❌ Disabled"},
    "silent_mode_toggle_on": {"hy": "🌙 Միացնել լուռ ռեժիմը", "ru": "� Включить тихий режим", "en": "🌙 Enable Silent Mode"},
    "silent_mode_toggle_off": {"hy": "☀️ Անջատել լուռ ռեժիմը", "ru": "☀️ Выключить тихий режим", "en": "☀️ Disable Silent Mode"},
    "silent_mode_on_status": {"hy": "Լուռ ռեժիմ՝ ✅ {start} - {end}", "ru": "Тихий режим: ✅ {start} - {end}", "en": "Silent Mode: ✅ {start} - {end}"},
    "silent_mode_off_status": {"hy": "Լուռ ռեժիմ՝ ❌ Անջատված", "ru": "Тихий режим: ❌ Выключен", "en": "Silent Mode: ❌ Disabled"},
    "enter_silent_interval_prompt": {"hy": "Մուտքագրեք լուռ ռեժիմի ժամանակահատվածը (օրինակ՝ 23:00-07:00)։", "ru": "Введите интервал тихого режима (например, 23:00-07:00):", "en": "Enter the silent mode interval (e.g., 23:00-07:00):"},
    "invalid_time_interval": {"hy": "❌ Սխալ ձևաչափ։ Խնդրում եմ մուտքագրել «ժժ:րր-ժժ:րր» տեսքով։", "ru": "❌ Неверный формат. Пожалуйста, введите в виде «ЧЧ:ММ-ЧЧ:ММ».", "en": "❌ Invalid format. Please enter as 'HH:MM-HH:MM'."},
    "silent_interval_set": {"hy": "✅ Լուռ ռեժիմի ժամանակահատվածը սահմանված է։", "ru": "✅ Интервал тихого режима установлен.", "en": "✅ Silent mode interval has been set."},

    # --- Q&A and Support ---
    "qa_title": {"hy": "💬 Հաճախ տրվող հարցեր", "ru": "💬 Часто задаваемые вопросы", "en": "💬 Frequently Asked Questions"},
    "qa_placeholder_q1": {"hy": "Հարց 1։ Ինչպե՞ս ավելացնել հասցե։", "ru": "Вопрос 1: Как добавить адрес?", "en": "Question 1: How do I add an address?"},
    "qa_placeholder_a1": {"hy": "Պատասխան 1։ Սեղմեք «Ավելացնել հասցե» կոճակը։", "ru": "Ответ 1: Нажмите кнопку «Добавить адрес».", "en": "Answer 1: Press the 'Add Address' button."},
    "qa_placeholder_q2": {"hy": "Հարց 2։ Որքա՞ն հաճախ են ստուգվում կայքերը։", "ru": "Вопрос 2: Как часто проверяются сайты?", "en": "Question 2: How often are the sites checked?"},
    "qa_placeholder_a2": {"hy": "Պատասխան 2։ Դա կախված է ձեր ընտրած հաճախականությունից։", "ru": "Ответ 2: Это зависит от выбранной вами частоты.", "en": "Answer 2: It depends on your chosen frequency."},
    "support_btn": {"hy": "✉️ Գրել սպասարկման կենտրոն", "ru": "✉️ Написать в поддержку", "en": "✉️ Write to Support"},
    "support_prompt": {"hy": "Խնդրում եմ մուտքագրեք ձեր հաղորդագրությունը սպասարկման կենտրոնի համար։ Ադմինիստրատորը կստանա այն և կպատասխանի ձեզ հնարավորինս շուտ։", "ru": "Пожалуйста, введите ваше сообщение для службы поддержки. Администратор получит его и свяжется с вами в ближайшее время.", "en": "Please enter your message for the support team. The administrator will receive it and get back to you as soon as possible."},
    "support_message_sent": {"hy": "✅ Ձեր հաղորդագրությունն ուղարկված է։", "ru": "✅ Ваше сообщение отправлено.", "en": "✅ Your message has been sent."},

    # --- Statistics ---
    "stats_title": {"hy": "📊 Վիճակագրություն", "ru": "📊 Статистика", "en": "📊 Statistics"},
    "stats_total_users": {"hy": "Ընդհանուր օգտատերեր", "ru": "Всего пользователей", "en": "Total Users"},
    "stats_total_addresses": {"hy": "Ընդհանուր հասցեներ", "ru": "Всего адресов", "en": "Total Addresses"},
    "stats_your_info": {"hy": "Ձեր տվյալները", "ru": "Ваши данные", "en": "Your Stats"},
    "stats_notif_received": {"hy": "Ստացված ծանուցումներ", "ru": "Получено уведомлений", "en": "Notifications Received"},

    # --- Notifications ---
    "outage_notification_header": {"hy": "⚠️ *Ուշադրություն, անջատում*", "ru": "⚠️ *Внимание, отключение*", "en": "⚠️ *Attention, Outage*"},
    "outage_water": {"hy": "💧 *Ջուր*", "ru": "💧 *Вода*", "en": "💧 *Water*"},
    "outage_gas": {"hy": "🔥 *Գազ*", "ru": "🔥 *Газ*", "en": "🔥 *Gas*"},
    "outage_electric": {"hy": "💡 *Էլեկտրաէներգիա*", "ru": "💡 *Электричество*", "en": "💡 *Electricity*"},
    "outage_period": {"hy": "Ժամանակահատված", "ru": "Период", "en": "Period"},
    "outage_status": {"hy": "Կարգավիճակ", "ru": "Статус", "en": "Status"},
    "outage_locations": {"hy": "Տեղանքներ", "ru": "Местоположения", "en": "Locations"},
    "last_outage_recorded": {"hy": "Վերջին անգամ այս հասցեում անջատում գրանցվել է՝", "ru": "Последнее отключение по этому адресу было зафиксировано:", "en": "The last outage recorded at this address was:"},
    "no_past_outages": {"hy": "Նախկինում այս հասցեում անջատումներ չեն գրանցվել։", "ru": "Ранее отключений по этому адресу не было зафиксировано.", "en": "No past outages have been recorded for this address."},

    # --- Admin ---
    "admin_unauthorized": {"hy": "Դուք իրավասու չեք այս հրամանը կատարելու։", "ru": "Вы не авторизованы для выполнения этой команды.", "en": "You are not authorized to execute this command."},
    "maintenance_on_feedback": {"hy": "⚙️ Սպասարկման ռեժիմը միացված է։", "ru": "⚙️ Режим обслуживания включен.", "en": "⚙️ Maintenance mode is ON."},
    "maintenance_off_feedback": {"hy": "✅ Սպասարկման ռեժիմը անջատված է։", "ru": "✅ Режим обслуживания выключен.", "en": "✅ Maintenance mode is OFF."},
    "maintenance_user_notification": {"hy": "⚙️ Բոտը ժամանակավորապես սպասարկման մեջ է։ Խնդրում ենք փորձել մի փոքր ուշ։", "ru": "⚙️ Бот временно находится на техобслуживании. Пожалуйста, попробуйте позже.", "en": "⚙️ The bot is temporarily under maintenance. Please try again later."},
    "support_message_from_user": {"hy": "✉️ *Նոր հաղորդագրություն սպասարկման կենտրոնին*\n\n*Օգտատեր:* {user_mention}\n*User ID:* `{user_id}`\n\n*Հաղորդագրություն։*\n\n{message}", "ru": "✉️ *Новое сообщение в поддержку*\n\n*От:* {user_mention}\n*User ID:* `{user_id}`\n\n*Сообщение:*\n\n{message}", "en": "✉️ *New Support Message*\n\n*From:* {user_mention}\n*User ID:* `{user_id}`\n\n*Message:*\n\n{message}"},
}

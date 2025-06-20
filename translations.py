import os
import urllib.parse

# --- Constants for Contact Information ---
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID")
CONTACT_PHONE_NUMBER = "+37412345678"
PLACE_ID = "ChIJx_fIM5i9akARt38HYgW6IOk"
MAP_URL = f"https://www.google.com/maps/search/?api=1&query=place_id:{PLACE_ID}"
ENCODED_ADDRESS_FOR_MAP = urllib.parse.quote(PLACE_ID)
escaped_number = CONTACT_PHONE_NUMBER.replace('+', '\\+')
CLICKABLE_PHONE_MD = f"📞 [{escaped_number}]({CONTACT_PHONE_NUMBER})"
CLICKABLE_ADDRESS_MD = f"📍 [{PLACE_ID}]({MAP_URL})"

# --- Tier Labels ---
TIER_LABELS = {"Free": {"hy": "Անվճար", "ru": "Бесплатный", "en": "Free"}, "Basic": {"hy": "Հիմնական", "ru": "Базовый", "en": "Basic"}, "Premium": {"hy": "Պրեմիում", "ru": "Премиум", "en": "Premium"}, "Ultra": {"hy": "Ուլտրա", "ru": "Ուլտրա", "en": "Ultra"}}

# --- Translations Dictionary ---
translations = {
    # --- Main Menu & Commands ---
    "add_address_btn": {"hy": "➕ Ավելացնել հասցե", "ru": "➕ Добавить адрес", "en": "➕ Add Address"},
    "remove_address_btn": {"hy": "➖ Հեռացնել հասցե", "ru": "➖ Удалить адрес", "en": "➖ Remove Address"},
    "my_addresses_btn": {"hy": "📋 Իմ հասցեները", "ru": "📋 Мои адреса", "en": "📋 My Addresses"},
    "frequency_btn": {"hy": "⚙️ Ծանուցման հաճախականություն", "ru": "⚙️ Частота уведомлений", "en": "⚙️ Notification Frequency"},
    "sound_settings_btn": {"hy": "🔊 Ձայնի կարգավորումներ", "ru": "🔊 Настройки звука", "en": "🔊 Sound Settings"},
    "qa_btn": {"hy": "❓ Հարցեր և Պատասխաններ", "ru": "❓ Вопросы и Ответы", "en": "❓ Q&A"},
    "contact_support_btn": {"hy": "💬 Կապ հաճախորդների սպասարկման հետ", "ru": "💬 Связаться со службой поддержки", "en": "💬 Contact Support"},
    "back_to_main_menu_btn": {"hy": "↩️ Գլխավոր ընտրացանկ", "ru": "↩️ Главное меню", "en": "↩️ Main Menu"},

    "start_command_desc": {"hy": "Սկսել բոտը և ստանալ ողջույնի հաղորդագրություն", "ru": "Запустить бота и получить приветственное сообщение", "en": "Start the bot and get a welcome message"},
    "myaddresses_command_desc": {"hy": "Դիտել կամ հեռացնել Ձեր պահպանված հասցեները", "ru": "Посмотреть или удалить ваши сохраненные адреса", "en": "View or remove your saved addresses"},
    "frequency_command_desc": {"hy": "Կարգավորել ծանուցումների ստացման հաճախականությունը", "ru": "Настроить частоту получения уведомлений", "en": "Adjust notification frequency"},
    "sound_command_desc": {"hy": "Կարգավորել ծանուցումների ձայնային կարգավորումները", "ru": "Настроить звуковые настройки уведомлений", "en": "Adjust notification sound settings"},
    "qa_command_desc": {"hy": "Գտնել պատասխաններ հաճախ տրվող հարցերին", "ru": "Найти ответы на часто задаваемые вопросы", "en": "Find answers to frequently asked questions"},
    "stats_command_desc": {"hy": "Դիտել բոտի վիճակագրությունը (միայն ադմինների համար)", "ru": "Посмотреть статистику бота (только для админов)", "en": "View bot statistics (Admin only)"},
    "clearaddresses_command_desc": {"hy": "Ջնջել բոլոր պահպանված հասցեները", "ru": "Удалить все сохраненные адреса", "en": "Delete all saved addresses"},


    # --- General ---
    "welcome_message": {"hy": "Բարի գալուստ OutageInfoBot։ Ես կօգնեմ ձեզ հետևել կոմունալ ծառայությունների պլանային անջատումներին։", "ru": "Добро пожаловать в OutageInfoBot. Я помогу вам отслеживать плановые отключения коммунальных услуг.", "en": "Welcome to OutageInfoBot. I will help you track planned utility outages."},
    "welcome_back": {"hy": "Ուրախ ենք, որ վերադարձել եք։", "ru": "С возвращением!", "en": "Welcome back!"},
    "main_menu_prompt": {"hy": "Ընտրեք գործողություն գլխավոր մենյուից։", "ru": "Выберите действие из главного меню.", "en": "Choose an action from the main menu."},
    "language_changed": {"hy": "Լեզուն փոխված է հայերենի։", "ru": "Язык изменен на русский.", "en": "Language changed to English."},
    "language_set_success": {"hy": "Լեզուն հաջողությամբ սահմանվել է։", "ru": "Язык успешно установлен.", "en": "Language set successfully."},
    "unrecognized_command": {"hy": "Չճանաչված հրաման։ Խնդրում ենք օգտագործել ստեղնաշարի կոճակները կամ /start հրամանը։", "ru": "Неизвестная команда. Пожалуйста, используйте кнопки на клавиатуре или команду /start.", "en": "Unrecognized command. Please use keyboard buttons or /start command."},
    "user_not_found": {"hy": "Օգտատերը չի գտնվել։ Խնդրում ենք օգտագործել /start հրամանը։", "ru": "Пользователь не найден. Пожалуйста, используйте команду /start.", "en": "User not found. Please use /start command."},
    
    # --- Address Management ---
    "choose_region": {"hy": "Ընտրեք ձեր մարզը կամ Երևանի շրջանը:", "ru": "Выберите ваш регион или район Еревана:", "en": "Choose your region or district of Yerevan:"},
    "enter_street": {"hy": "Մուտքագրեք փողոցի անունը և տան համարը (օրինակ՝ Աբովյան 12):", "ru": "Введите название улицы и номер дома (например: Абовяна 12):", "en": "Enter street name and house number (e.g., Abovyan 12):"},
    "invalid_region": {"hy": "Սխալ մարզ։ Խնդրում ենք ընտրել ցուցակից։", "ru": "Неվերный регион. Пожалуйста, выберите из списка.", "en": "Invalid region. Please choose from the list."},
    "address_add_success": {"hy": "✅ Հասցեն ({address}) ավելացվել է։", "ru": "✅ Адрес ({address}) добавлен.", "en": "✅ Address ({address}) added."},
    "address_not_found": {"hy": "Հասցեն չի գտնվել կամ ճանաչվել։ Խնդրում ենք փորձել նորից։", "ru": "Адрес не найден или не распознан. Пожалуйста, попробуйте еще раз.", "en": "Address not found or recognized. Please try again."},
    "no_addresses_yet": {"hy": "Դուք դեռ հասցեներ չունեք։ Օգտագործեք «➕ Ավելացնել հասցե» կոճակը՝ սկսելու համար։", "ru": "У вас пока нет добавленных адресов. Используйте кнопку «➕ Добавить адрес», чтобы начать.", "en": "You don't have any addresses added yet. Use the '➕ Add Address' button to start."},
    "your_addresses": {"hy": "Ձեր պահպանված հասցեները:", "ru": "Ваши сохраненные адреса:", "en": "Your saved addresses:"},
    "address_removed_success": {"hy": "Հասցեն հաջողությամբ հեռացված է։", "ru": "Адрес успешно удален.", "en": "Address successfully removed."},
    "address_remove_failed": {"hy": "Հասցեն հեռացնել չհաջողվեց։", "ru": "Не удалось удалить адрес.", "en": "Failed to remove address."},
    "all_addresses_cleared": {"hy": "Բոլոր հասցեները մաքրվել են։", "ru": "Все адреса удалены.", "en": "All addresses cleared."},
    "active_outages_for_address": {"hy": "Ընթացիկ անջատումներ ձեր նոր հասցեի համար:", "ru": "Текущие отключения для вашего нового адреса:", "en": "Current outages for your new address:"},
    "no_active_outages_for_address": {"hy": "✅ Ներկա պահին ձեր նոր հասցեի համար ակտիվ կամ սպասվող անջատումներ չեն հայտնաբերվել։", "ru": "✅ На данный момент для вашего нового адреса не найдено активных или предстоящих отключений.", "en": "✅ Currently no active or upcoming outages found for your new address."},

    # --- Frequency Settings ---
    "choose_frequency": {"hy": "Ընտրեք ծանուցումների հաճախականությունը։ Ձեր ներկայիս հաճախականությունը՝ {current_frequency}։", "ru": "Выберите частоту уведомлений. Ваша текущая частота: {current_frequency}.", "en": "Choose notification frequency. Your current frequency: {current_frequency}."},
    "frequency_set_success": {"hy": "Ծանուցումների հաճախականությունը հաջողությամբ սահմանվել է {frequency}։", "ru": "Частота уведомлений успешно установлена на {frequency}.", "en": "Notification frequency successfully set to {frequency}."},
    "invalid_frequency_option": {"hy": "Սխալ հաճախականության ընտրանք։", "ru": "Неվերный вариант частоты.", "en": "Invalid frequency option."},
    "feature_not_available_for_tier": {"hy": "Այս հնարավորությունը հասանելի չէ ձեր {tier} փաթեթի համար։", "ru": "Эта функция недоступна для вашего тарифа {tier}.", "en": "This feature is not available for your {tier} tier."},

    # --- Sound Settings ---
    "sound_settings_prompt": {"hy": "Կարգավորեք ծանուցումների ձայնային կարգավորումները։", "ru": "Настройте звуковые параметры уведомлений.", "en": "Adjust notification sound settings."},
    "sound_on": {"hy": "🎶 Ձայնը միացված է", "ru": "🎶 Звук включен", "en": "🎶 Sound is ON"},
    "sound_off": {"hy": "🔇 Ձայնն անջատված է", "ru": "🔇 Звук выключен", "en": "🔇 Sound is OFF"},
    "silent_mode_on": {"hy": "🌙 Լուռ ռեժիմը միացված է", "ru": "🌙 Тихий режим включен", "en": "🌙 Silent mode is ON"},
    "silent_mode_off": {"hy": "☀️ Լուռ ռեժիմն անջատված է", "ru": "☀️ Тихий режим выключен", "en": "☀️ Silent mode is OFF"},
    "toggle_sound:on": {"hy": "Միացնել ձայնը", "ru": "Включить звук", "en": "Turn ON Sound"}, # Callback data key is part of text
    "toggle_sound:off": {"hy": "Անջատել ձայնը", "ru": "Выключить звук", "en": "Turn OFF Sound"}, # Callback data key is part of text
    "toggle_silent_mode:on": {"hy": "Միացնել լուռ ռեժիմը", "ru": "Включить тихий режим", "en": "Turn ON Silent Mode"}, # Callback data key is part of text
    "toggle_silent_mode:off": {"hy": "Անջատել լուռ ռեժիմը", "ru": "Выключить тихий режим", "en": "Turn OFF Silent Mode"}, # Callback data key is part of text
    "set_silent_times_btn": {"hy": "Կարգավորել լուռ ռեժիմի ժամերը ({start_time}-{end_time})", "ru": "Настроить время тихого режима ({start_time}-{end_time})", "en": "Set Silent Mode Times ({start_time}-{end_time})"},
    "sound_enabled_feedback": {"hy": "Ձայնային ծանուցումները միացված են։", "ru": "Звуковые уведомления включены.", "en": "Sound notifications are enabled."},
    "sound_disabled_feedback": {"hy": "Ձայնային ծանուցումներն անջատված են։", "ru": "Звуковые уведомления выключены.", "en": "Sound notifications are disabled."},
    "silent_mode_enabled_feedback": {"hy": "Լուռ ռեժիմը միացված է։", "ru": "Тихий режим включен.", "en": "Silent mode is enabled."},
    "silent_mode_disabled_feedback": {"hy": "Լուռ ռեժիմն անջատված է։", "ru": "Тихий режим выключен.", "en": "Silent mode is disabled."},
    "set_silent_interval_prompt": {"hy": "Խնդրում ենք մուտքագրել լուռ ծանուցումների ժամանակահատվածը (օրինակ՝ 22:30 07:00):", "ru": "Пожалуйста, введите период бесшумных уведомлений (например, 22:30 07:00):", "en": "Please enter the silent notification period (e.g., 22:30 07:00):"},
    "confirm_silent_interval": {"hy": "Դուք նկատի ունեիք լուռ ծանուցումներ ստանալ {start_time}-ից մինչև {end_time}՞", "ru": "Вы имели в виду получать бесшумные уведомления с {start_time} до {end_time}?", "en": "Did you mean to receive silent notifications from {start_time} to {end_time}?"},
    "silent_interval_invalid_format": {"hy": "Սխալ ժամաձև։ Խնդրում ենք մուտքագրել ժամերը այսպես՝ '22:30 07:00'։", "ru": "Неверный формат времени. Пожалуйста, введите время в формате '22:30 07:00'.", "en": "Invalid time format. Please enter times like '22:30 07:00'."},
    "silent_interval_set_success": {"hy": "Լուռ ծանուցումների ժամանակահատվածը սահմանվել է {start_time}-ից մինչև {end_time}։", "ru": "Период бесшумных уведомлений установлен с {start_time} до {end_time}.", "en": "Silent notification period set from {start_time} to {end_time}."},
    "silent_interval_edit": {"hy": "Խնդրում ենք նորից մուտքագրել լուռ ծանուցումների ժամանակահատվածը։", "ru": "Пожалуйста, введите период бесшумных уведомлений заново.", "en": "Please re-enter the silent notification period."},
    "silent_interval_cancelled": {"hy": "Լուռ ծանուցումների ժամանակահատվածի կարգավորումը չեղարկվել է։", "ru": "Настройка периода бесшумных уведомлений отменена.", "en": "Setting silent notification period cancelled."},
    "silent_interval_error": {"hy": "Սխալ տվյալներ լուռ ռեժիմի ժամերը պահպանելիս։", "ru": "Ошибка при сохранении времени тихого режима.", "en": "Error saving silent mode times."},
    "yes": {"hy": "✅ Այո", "ru": "✅ Да", "en": "✅ Yes"},
    "no_edit_btn": {"hy": "📝 Ոչ, խմբագրել", "ru": "📝 Нет, изменить", "en": "📝 No, edit"},
    "cancel_btn": {"hy": "❌ Չեղարկել", "ru": "❌ Отменить", "en": "❌ Cancel"},

    # --- Outage Notifications ---
    "outage_notification": {"hy": "⚡️ *Նոր {type} անջատում* ⚡️\n\nՀասցե: `{address}`\nՄանրամասներ: {details}\nՍկիզբ: {start_time}\nԱվարտ: {end_time}", "ru": "⚡️ *Новое {type} отключение* ⚡️\n\nАдрес: `{address}`\nПодробности: {details}\nНачало: {start_time}\nОкончание: {end_time}", "en": "⚡️ *New {type} outage* ⚡️\n\nAddress: `{address}`\nDetails: {details}\nStart: {start_time}\nEnd: {end_time}"},
    "no_details_provided": {"hy": "Մանրամասներ չեն տրամադրվել։", "ru": "Подробности не предоставлены.", "en": "No details provided."},
    "not_specified": {"hy": "Նշված չէ", "ru": "Не указано", "en": "Not specified"},

    # --- Q&A and Support ---
    "qa_title": {"hy": "💬 Հաճախ տրվող հարցեր:\n\n*Ինչպե՞ս ավելացնել հասցե*։\nՍեղմեք «➕ Ավելացնել հասցե» կոճակը և հետևեք հրահանգներին։\n\n*Ինչպե՞ս ստուգել իմ հասցեները*։\nՍեղմեք «📋 Իմ հասցեները» կոճակը։\n\n*Որքա՞ն հաճախ եմ ծանուցումներ ստանալու*։\nԴուք կարող եք կարգավորել ծանուցումների հաճախականությունը «⚙️ Ծանուցման հաճախականություն» բաժնում։\n\n*Ի՞նչ անել, եթե հասցեն չի գտնվում*։\nՓորձեք մուտքագրել հասցեն տարբեր ձևերով կամ կապվեք աջակցության հետ։\n\n*Ինչպե՞ս անջատել ձայնային ծանուցումները*։\n«🔊 Ձայնի կարգավորումներ» բաժնում կարող եք միացնել կամ անջատել ձայնային ծանուցումները։\n\n*Կարո՞ղ եմ ստանալ անջատումների մասին տեղեկատվություն այլ քաղաքների կամ մարզերի համար*։\nԱյո, կարող եք ավելացնել ցանկացած հասցե Հայաստանի Հանրապետության տարածքից։\n\n*Ինչպե՞ս ջնջել բոլոր հասցեները*։\nՕգտագործեք /clearaddresses հրամանը։\n\n*Ո՞վ է այս բոտի ստեղծողը և ինչպե՞ս կարող եմ կապ հաստատել նրա հետ*։\nԱյս բոտը ստեղծվել է անհատ մշակողի կողմից։ Կարող եք կապ հաստատել աջակցության հետ՝ սեղմելով «💬 Կապ հաճախորդների սպասարկման հետ» կոճակը։\n\n*Ինչպե՞ս կարող եմ աջակցել նախագծին*։\nԾրագիրը դեռևս ֆինանսական աջակցություն չի ընդունում։ Սակայն դուք կարող եք կիսվել բոտի մասին տեղեկատվությամբ ձեր ընկերների հետ։\n", "ru": "💬 Часто задаваемые вопросы:\n\n*Как добавить адрес*?\nНажмите кнопку «➕ Добавить адрес» и следуйте инструкциям.\n\n*Как проверить мои адреса*?\nНажмите кнопку «📋 Мои адреса».\n\n*Как часто я буду получать уведомления*?\nВы можете настроить частоту уведомлений в разделе «⚙️ Частота уведомлений».\n\n*Что делать, если адрес не найден*?\nПопробуйте ввести адрес в различных форматах или свяжитесь со службой поддержки.\n\n*Как отключить звуковые уведомления*?\nВ разделе «🔊 Настройки звука» вы можете включить или выключить звуковые уведомления.\n\n*Могу ли я получать информацию об отключениях для других городов или регионов*?\nДа, вы можете добавить любой адрес на территории Республики Армения.\n\n*Как удалить все адреса*?\nИспользуйте команду /clearaddresses.\n\n*Кто создатель этого бота и как я могу с ним связаться*?\nЭтот бот создан независимым разработчиком. Вы можете связаться со службой поддержки, нажав кнопку «💬 Связаться со службой поддержки».\n\n*Как я могу поддержать проект*?\nПроект пока не принимает финансовую поддержку. Однако вы можете поделиться информацией о боте со своими друзьями.\n", "en": "💬 Frequently Asked Questions:\n\n*How to add an address*?\nClick the '➕ Add Address' button and follow the instructions.\n\n*How to check my addresses*?\nClick the '📋 My Addresses' button.\n\n*How often will I receive notifications*?\nYou can adjust the notification frequency in the '⚙️ Notification Frequency' section.\n\n*What if the address is not found*?\nTry entering the address in different formats or contact support.\n\n*How to turn off sound notifications*?\nIn the '🔊 Sound Settings' section, you can enable or disable sound notifications.\n\n*Can I get outage information for other cities or regions*?\nYes, you can add any address within the Republic of Armenia.\n\n*How to delete all addresses*?\nUse the /clearaddresses command.\n\n*Who is the creator of this bot and how can I contact them*?\nThis bot was created by an independent developer. You can contact support by clicking the '💬 Contact Support' button.\n\n*How can I support the project*?\nThe project does not yet accept financial support. However, you can share information about the bot with your friends.\n"},
    "contact_support_message": {"hy": "Եթե ունեք հարցեր կամ խնդիրներ, խնդրում ենք կապվել մեզ հետ։\nՀեռախոսահամար՝ {phone}\nՀասցե՝ {map_address}", "ru": "Если у вас есть вопросы или проблемы, пожалуйста, свяжитесь с нами.\nНомер телефона: {phone}\nАдрес: {map_address}", "en": "If you have questions or issues, please contact us.\nPhone number: {phone}\nAddress: {map_address}"},
    "support_message_sent": {"hy": "Ձեր հաղորդագրությունը հաջողությամբ ուղարկվել է աջակցությանը։ Մենք կպատասխանենք որքան հնարավոր է շուտ։", "ru": "Ваше сообщение успешно отправлено в поддержку. Мы ответим как можно скорее.", "en": "Your message has been successfully sent to support. We will reply as soon as possible."},
    "support_send_failed": {"hy": "Չհաջողվեց ուղարկել ձեր հաղորդագրությունը։ Խնդրում ենք փորձել նորից կամ օգտագործել այլ մեթոդ։", "ru": "Не удалось отправить ваше сообщение. Пожалуйста, попробуйте еще раз или используйте другой метод.", "en": "Failed to send your message. Please try again or use another method."},
    "support_not_configured": {"hy": "Աջակցության չատը կազմաձևված չէ։", "ru": "Чատ поддержки не настроен.", "en": "Support chat is not configured."},

    # --- Statistics (Admin only) ---
    "stats_message": {"hy": "📊 *Բոտի վիճակագրություն:*\nԸնդհանուր օգտատերեր: {total_users}\nԸնդհանուր հասցեներ: {total_addresses}\nՎերջին ստուգման սկիզբ: {last_check_start}\nՎերջին ստուգման ավարտ: {last_check_end}\nՎերջին ստուգման կարգավիճակ: {last_check_status}\nՁեր ուղարկված ծանուցումներ: {user_notifications}", "ru": "📊 *Статистика бота:*\nВсего пользователей: {total_users}\nВсего адресов: {total_addresses}\nНачало последней проверки: {last_check_start}\nОкончание последней проверки: {last_check_end}\nСтатус последней проверки: {last_check_status}\nОтправлено вам уведомлений: {user_notifications}", "en": "📊 *Bot Statistics:*\nTotal Users: {total_users}\nTotal Addresses: {total_addresses}\nLast Check Start: {last_check_start}\nLast Check End: {last_check_end}\nLast Check Status: {last_check_status}\nNotifications sent to you: {user_notifications}"},

    # --- Admin ---
    "admin_unauthorized": {"hy": "Դուք իրավասու չեք այս հրամանը կատարելու։", "ru": "Вы не авторизованы для выполнения этой команды.", "en": "You are not authorized to execute this command."},
    "maintenance_on_feedback": {"hy": "⚙️ Սպասարկման ռեժիմը միացված է։", "ru": "⚙️ Режим обслуживания включен.", "en": "⚙️ Maintenance mode is ON."},
    "maintenance_off_feedback": {"hy": "✅ Սպասարկման ռեժիմը անջատված է։", "ru": "✅ Режим обслуживания выключен։", "en": "✅ Maintenance mode is OFF."},
    "maintenance_user_notification": {"hy": "⚙️ Բոտը ժամանակավորապես սպասարկման մեջ է։ Խնդրում ենք փորձել մի փոքր ուշ։", "ru": "⚙️ Бот временно находится на техобслуживании. Пожалуйста, попробуйте позже.", "en": "⚙️ The bot is temporarily under maintenance. Please try again later."},
    "support_message": {"hy": "Խնդիր կամ հարց ունե՞ք։ Գրեք մեզ։", "ru": "Есть проблема или вопрос? Напишите нам.", "en": "Have an issue or a question? Write to us."}
}

import os
import urllib.parse

# --- Constants for Contact Information ---
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID")
CONTACT_PHONE_NUMBER = "+37412345678" # Placeholder
PLACE_ID = "ChIJx_fIM5i9akARt38HYgW6IOk" # Example Google Maps Place ID for a location in Yerevan
MAP_URL = f"https://www.google.com/maps/search/?api=1&query=place_id:{PLACE_ID}"
ENCODED_ADDRESS_FOR_MAP = urllib.parse.quote(PLACE_ID) # Not currently used with this MAP_URL format
escaped_number = CONTACT_PHONE_NUMBER.replace('+', '\\+')
CLICKABLE_PHONE_MD = f"📞 [{escaped_number}]({CONTACT_PHONE_NUMBER})"
CLICKABLE_ADDRESS_MD = f"📍 [Office]({MAP_URL})" # Placeholder, replace with actual address text if needed

# --- Tier Labels ---
TIER_LABELS = {"Free": {"hy": "Անվճար", "ru": "Бесплатный", "en": "Free"}, "Basic": {"hy": "Հիմնական", "ru": "Базовый", "en": "Basic"}, "Premium": {"hy": "Պրեմիում", "ru": "Премиум", "en": "Premium"}, "Ultra": {"hy": "Ուլտրա", "ru": "Ультра", "en": "Ultra"}}

# --- Translations Dictionary ---
translations = {
    # --- Main Menu & Commands ---
    "add_address_btn": {"hy": "➕ Ավելացնել հասցե", "ru": "➕ Добавить адрес", "en": "➕ Add Address"},
    "my_addresses_btn": {"hy": "Իմ հասցեները", "ru": "Мои адреса", "en": "My Addresses"},
    "check_outage_btn": {"hy": "Ստուգել անջատումը", "ru": "Проверить отключение", "en": "Check Outage"},
    "frequency_btn": {"hy": "Ծանուցումների հաճախականություն", "ru": "Частота уведомлений", "en": "Notification Frequency"},
    "sound_settings_btn": {"hy": "Ձայնի կարգավորումներ", "ru": "Настройки звука", "en": "Sound Settings"},
    "stats_btn": {"hy": "Վիճակագրություն", "ru": "Статистика", "en": "Statistics"}, # Updated key for stats button
    "contact_support_btn": {"hy": "Կապ հաճախորդների աջակցման հետ", "ru": "Связаться с поддержкой", "en": "Contact Support"},
    "about_bot_btn": {"hy": "Բոտի մասին", "ru": "О боте", "en": "About Bot"},
    "main_menu_greeting": {"hy": "Ողջույն! Ընտրեք գործողություն ստորև:", "ru": "Привет! Выберите действие ниже:", "en": "Hello! Choose an action below:"},
    "back_to_main_menu": {"hy": "↩️ Գլխավոր մենյու", "ru": "↩️ Главное меню", "en": "↩️ Main Menu"},

    # --- Address Management ---
    "enter_address_prompt": {"hy": "Խնդրում ենք մուտքագրել ձեր հասցեն (օրինակ՝ *Երևան, Կոմիտասի 5*).", "ru": "Пожалуйста, введите ваш адрес (например: *Ереван, Комитаса 5*).", "en": "Please enter your address (e.g., *Yerevan, Komitas 5*)."},
    "verifying_address": {"hy": "Ստուգում եմ հասցեն, սպասեք...", "ru": "Проверяю адрес, пожалуйста, подождите...", "en": "Verifying address, please wait..."},
    "address_added_success": {"hy": "Հասցեն *{address}* հաջողությամբ ավելացվեց:", "ru": "Адрес *{address}* успешно добавлен.", "en": "Address *{address}* added successfully."},
    "address_already_exists": {"hy": "Այս հասցեն՝ *{address}*, արդեն ավելացված է ձեր ցանկում։", "ru": "Этот адрес *{address}* уже есть в вашем списке.", "en": "This address *{address}* is already in your list."},
    "address_not_found": {"hy": "Ներողություն, հասցեն՝ *{address}*, չգտնվեց։ Խնդրում ենք փորձել կրկին կամ ավելի ճշգրիտ մուտքագրել։", "ru": "Извините, адрес *{address}* не найден. Пожалуйста, попробуйте еще раз или введите более точно.", "en": "Sorry, address *{address}* not found. Please try again or enter a more precise location."},
    "no_addresses_yet": {"hy": "Դուք դեռ հասցեներ չեք ավելացրել։", "ru": "Вы еще не добавили ни одного адреса.", "en": "You haven't added any addresses yet."},
    "your_addresses": {"hy": "Ձեր ավելացված հասցեները:", "ru": "Ваши добавленные адреса:", "en": "Your added addresses:"},
    "address_removed_success": {"hy": "Հասցեն հաջողությամբ հեռացվեց։", "ru": "Адрес успешно удален.", "en": "Address removed successfully."},
    "address_remove_failed": {"hy": "Հասցեն հեռացնել չհաջողվեց։", "ru": "Не удалось удалить адрес.", "en": "Failed to remove address."},
    "all_addresses_cleared": {"hy": "Բոլոր {count} հասցեները մաքրված են։", "ru": "Все {count} адресов удалены.", "en": "All {count} addresses cleared."},
    "no_addresses_to_clear": {"hy": "Դուք հասցեներ չունեք մաքրելու։", "ru": "У вас нет адресов для очистки.", "en": "You have no addresses to clear."},

    # --- Frequency Settings ---
    "frequency_message": {"hy": "Ընտրեք ծանուցումների հաճախականությունը։ Ձեր ներկայիս հաճախականությունը՝ {current_freq_hours} ժամը մեկ։", "ru": "Выберите частоту уведомлений. Ваша текущая частота: раз в {current_freq_hours} часов.", "en": "Choose notification frequency. Your current frequency: once every {current_freq_hours} hours."},
    "freq_3_hours": {"hy": "Ամեն 3 ժամը մեկ", "ru": "Каждые 3 часа", "en": "Every 3 hours"},
    "freq_6_hours": {"hy": "Ամեն 6 ժամը մեկ", "ru": "Каждые 6 часов", "en": "Every 6 hours"},
    "freq_12_hours": {"hy": "Ամեն 12 ժամը մեկ", "ru": "Каждые 12 часов", "en": "Every 12 hours"},
    "freq_24_hours": {"hy": "Ամեն 24 ժամը մեկ", "ru": "Каждые 24 часа", "en": "Every 24 hours"},
    "frequency_set_success": {"hy": "Ծանուցումների հաճախականությունը սահմանվել է՝ ամեն {hours} ժամը մեկ։", "ru": "Частота уведомлений установлена: раз в {hours} часов.", "en": "Notification frequency set to every {hours} hours."},

    # --- Sound Settings ---
    "current_sound_settings": {"hy": "Ձայնի կարգավորումներ:\nՁայնային ծանուցումներ: *{sound_status}*\nԱնձայն ռեժիմ: *{silent_mode_status}*\nԱնձայն ռեժիմի ժամեր: *{silent_start}* - *{silent_end}*", "ru": "Настройки звука:\nЗвуковые уведомления: *{sound_status}*\nТихий режим: *{silent_mode_status}*\nЧасы тихого режима: *{silent_start}* - *{silent_end}*", "en": "Sound Settings:\nSound notifications: *{sound_status}*\nSilent mode: *{silent_mode_status}*\nSilent mode hours: *{silent_start}* - *{silent_end}*"},
    "enabled": {"hy": "Միացված է", "ru": "Включено", "en": "Enabled"},
    "disabled": {"hy": "Անջատված է", "ru": "Отключено", "en": "Disabled"},
    "toggle_sound_on": {"hy": "Միացնել ձայնը", "ru": "Включить звук", "en": "Turn Sound ON"},
    "toggle_sound_off": {"hy": "Անջատել ձայնը", "ru": "Выключить звук", "en": "Turn Sound OFF"},
    "sound_toggled": {"hy": "Ձայնային ծանուցումները հիմա՝ *{status}*։", "ru": "Звуковые уведомления теперь: *{status}*.", "en": "Sound notifications are now: *{status}*."},
    "toggle_silent_mode_on": {"hy": "Միացնել անձայն ռեժիմը", "ru": "Включить тихий режим", "en": "Turn Silent Mode ON"},
    "toggle_silent_mode_off": {"hy": "Անջատել անձայն ռեժիմը", "ru": "Выключить тихий режим", "en": "Turn Silent Mode OFF"},
    "silent_mode_toggled": {"hy": "Անձայն ռեժիմը հիմա՝ *{status}*։", "ru": "Тихий режим теперь: *{status}*.", "en": "Silent mode is now: *{status}*."},
    "set_silent_mode_times": {"hy": "Սահմանել անձայն ռեժիմի ժամերը", "ru": "Установить часы тихого режима", "en": "Set Silent Mode Hours"},
    "prompt_silent_mode_times": {"hy": "Մուտքագրեք անձայն ռեժիմի սկզբի և ավարտի ժամերը (օրինակ՝ *23:00 07:00* կամ *22,30 07,00*):", "ru": "Введите часы начала и окончания тихого режима (например: *23:00 07:00* или *22,30 07,00*).", "en": "Enter silent mode start and end times (e.g., *23:00 07:00* or *22,30 07,00*)."},
    "confirm_silent_mode_times": {"hy": "Դուք ցանկանում եք ծանուցումներ ստանալ անձայն ռեժիմով՝ *{start_time}*-ից *{end_time}*՞", "ru": "Вы хотите получать уведомления в тихом режиме с *{start_time}* до *{end_time}*?", "en": "You'd like to receive notifications in silent mode from *{start_time}* to *{end_time}*?"},
    "yes_button": {"hy": "✅ Այո", "ru": "✅ Да", "en": "✅ Yes"},
    "no_edit_button": {"hy": "📝 Ոչ, խմբագրել", "ru": "📝 Нет, изменить", "en": "📝 No, edit"},
    "cancel_button": {"hy": "❌ Չեղարկել", "ru": "❌ Cancel", "en": "❌ Cancel"},
    "invalid_time_format": {"hy": "Սխալ ժամի ձևաչափ։ Օրինակ՝ *23:00*։", "ru": "Неверный формат времени. Пример: *23:00*.", "en": "Invalid time format. Example: *23:00*."},
    "invalid_time_range_format": {"hy": "Սխալ ժամանակահատվածի ձևաչափ։ Խնդրում ենք մուտքագրել սկզբի և ավարտի ժամերը (օրինակ՝ *23:00 07:00*).", "ru": "Неверный формат диапазона времени. Пожалуйста, введите время начала и окончания (например: *23:00 07:00*).", "en": "Invalid time range format. Please enter start and end times (e.g., *23:00 07:00*)."},
    "silent_mode_times_set_success": {"hy": "Անձայն ռեժիմի ժամերը սահմանվել են՝ *{start_time}*-ից *{end_time}*։", "ru": "Часы тихого режима установлены: с *{start_time}* до *{end_time}*.", "en": "Silent mode hours set: from *{start_time}* to *{end_time}*."},
    "error_setting_silent_times": {"hy": "Սխալ տեղի ունեցավ անձայն ռեժիմի ժամերը սահմանելիս։", "ru": "Произошла ошибка при установке часов тихого режима.", "en": "An error occurred while setting silent mode hours."},
    "silent_mode_times_canceled": {"hy": "Անձայն ռեժիմի ժամերի սահմանումը չեղարկվեց։", "ru": "Установка часов тихого режима отменена.", "en": "Setting silent mode hours canceled."},
    "please_use_buttons": {"hy": "Խնդրում ենք օգտագործել ստորև նշված կոճակները։", "ru": "Пожалуйста, используйте кнопки ниже.", "en": "Please use the buttons below."},


    # --- Outage Information ---
    "checking_outages": {"hy": "Ստուգում եմ անջատումները, սպասեք...", "ru": "Проверяю отключения, пожалуйста, подождите...", "en": "Checking for outages, please wait..."},
    "found_outages_for_address": {"hy": "Հայտնաբերված անջատումներ *{address}* հասցեի համար:", "ru": "Найденные отключения для адреса *{address}*:", "en": "Found outages for address *{address}*:"},
    "no_outages_found": {"hy": "Ներկա պահին անջատումներ չեն գտնվել *{address}* հասցեի համար։", "ru": "На текущий момент отключений по адресу *{address}* не найдено.", "en": "No outages found for *{address}* at the moment."},
    "no_current_outages": {"hy": "Ներկա պահին անջատումներ չեն գտնվել *{address}* հասցեի համար։", "ru": "На текущий момент отключений по адресу *{address}* не найдено.", "en": "No current outages found for *{address}*."},
    "unknown_type": {"hy": "Անհայտ տեսակ", "ru": "Неизвестный тип", "en": "Unknown type"},
    "unknown_status": {"hy": "Անհայտ կարգավիճակ", "ru": "Неизвестный статус", "en": "Unknown status"},
    "source_type": {"hy": "Աղբյուրի տեսակ", "ru": "Тип источника", "en": "Source Type"},
    "status": {"hy": "Կարգավիճակ", "ru": "Статус", "en": "Status"},
    "start_time": {"hy": "Սկիզբ", "ru": "Начало", "en": "Start Time"},
    "end_time": {"hy": "Ավարտ", "ru": "Окончание", "en": "End Time"},
    "details": {"hy": "Մանրամասներ", "ru": "Подробности", "en": "Details"},
    "no_details": {"hy": "Մանրամասներ չկան։", "ru": "Деталей нет.", "en": "No details."},
    "qa_prompt": {"hy": "Մուտքագրեք հասցե, որի համար ցանկանում եք ստուգել անջատումները (օրինակ՝ *Երևան, Կոմիտասի 5*).", "ru": "Введите адрес, для которого хотите проверить отключения (например: *Ереван, Комитаса 5*).", "en": "Enter the address you want to check for outages (e.g., *Yerevan, Komitas 5*)."},
    "last_outage_recorded": {"hy": "Այս հասցեում վերջին անգամ գրանցված անջատումը եղել է:", "ru": "Последнее отключение, зафиксированное по этому адресу, было:", "en": "The last outage recorded at this address was:"},
    "no_past_outages": {"hy": "Նախկինում այս հասցեում անջատումներ չեն գրանցվել։", "ru": "Ранее отключений по этому адресу не было зафиксировано.", "en": "No past outages have been recorded for this address."},

    # --- Admin ---
    "admin_unauthorized": {"hy": "Դուք իրավասու չեք այս հրամանը կատարելու։", "ru": "Вы не авторизованы для выполнения этой команды.", "en": "You are not authorized to execute this command."},
    "maintenance_on_feedback": {"hy": "⚙️ Սպասարկման ռեժիմը միացված է։", "ru": "⚙️ Режим обслуживания включен.", "en": "⚙️ Maintenance mode is ON."},
    "maintenance_off_feedback": {"hy": "✅ Սպասարկման ռեժիմը անջատված է։", "ru": "✅ Режим обслуживания выключен.", "en": "✅ Maintenance mode is OFF."},
    "maintenance_user_notification": {"hy": "⚙️ Բոտը ժամանակավորապես սպասարկման մեջ է։ Խնդրում ենք փորձել մի փոքր ուշ։", "ru": "⚙️ Ботը ժամանակավորապես սպասարկման մեջ է։ Խնդրում ենք փորձել մի փոքր ուշ։", "en": "⚙️ The bot is temporarily under maintenance. Please try again later."},
    "support_message": {"hy": f"Խնդրում ենք կապվել մեր աջակցության հետ՝ {CLICKABLE_PHONE_MD} կամ գրել մեզ Telegram-ում։\n", "ru": f"Пожалуйста, свяжитесь с нашей службой поддержки по телефону {CLICKABLE_PHONE_MD} или напишите нам в Telegram.\n", "en": f"Please contact our support at {CLICKABLE_PHONE_MD} or write us on Telegram.\n"},
    "about_bot_message": {"hy": "ℹ️ *@OutageInfoBot* - ը ձեր անձնական օգնականն է՝ կոմունալ անջատումներին հետևելու համար։ Մենք ավտոմատ կերպով ստուգում ենք կոմունալ ծառայությունների պաշտոնական կայքերը և ժամանակին ծանուցումներ ենք ուղարկում ձեր գրանցված հասցեների համար։\n\n🎯 *Նպատակներ:*\n- Տրամադրել հարմար, կենտրոնացված և ժամանակին տեղեկատվություն կոմունալ անջատումների մասին։\n- Խնայել օգտատերերի ժամանակը՝ այլևս կարիք չկա ձեռքով ստուգել կայքերը։\n- Բարձրացնել իրազեկվածությունը և կանխել անակնկալ անջատումները։\n\n💡 *Օգուտներ:*\n- Ծանուցումներ նախապես, ինչը թույլ է տալիս ավելի լավ պլանավորել օրը։\n- Խնայում է անձնական և աշխատանքային ժամանակը։\n- Հատկապես օգտակար է բիզնեսների համար, որտեղ անջատումները կարող են հանգեցնել ֆինանսական կորուստների։\n\n*Շնորհակալություն @OutageInfoBot-ն օգտագործելու համար։*",
                         "ru": "ℹ️ *@OutageInfoBot* — это ваш личный помощник по отслеживанию отключений коммунальных услуг. Мы автоматически проверяем официальные сайты коммунальных служб и своевременно отправляем уведомления для ваших зарегистрированных адресов.\n\n🎯 *Цели бота:*\n- Предоставлять удобный, централизованный и своевременный доступ к информации об отключениях.\n- Экономить время пользователей: больше не нужно вручную проверять сайты.\n- Повышать осведомленность и предотвращать неприятные сюрпризы, возникающие при неожиданном отключении ресурсов.\n\n💡 *Преимущества:*\n- Пользователи получают уведомления заранее, что позволяет лучше планировать свой день.\n- Экономит личное и рабочее время — не нужно вручную проверять сайты.\n- Особенно полезно для бизнеса, где перебои в коммунальных ресурсах могут привести к финансовым потерям.\n\n*Спасибо, что используете @OutageInfoBot!*",
                         "en": "ℹ️ *@OutageInfoBot* is your personal assistant for tracking utility outages. We automatically check official utility websites and send timely notifications for your registered addresses.\n\n🎯 *Bot Goals:*\n- Provide convenient, centralized, and timely access to information about utility outages.\n- Save users' time: no need to manually check websites anymore.\n- Raise awareness and prevent unpleasant surprises that arise when resources are unexpectedly disconnected.\n\n💡 *Benefits:*\n- Users receive notifications in advance, allowing them to better plan their day.\n- Saves personal and work time – no need to manually check websites.\n- Especially useful for businesses, where interruptions in utility resources can lead to financial losses.\n\n*Thank you for using @OutageInfoBot!*"},
    "unrecognized_command": {"hy": "Ներողություն, ես չհասկացա ձեր հրամանը։ Խնդրում եմ օգտագործեք ստորև նշված կոճակները կամ /start հրամանը։", "ru": "Извините, я не понял вашу команду. Пожалуйста, используйте кнопки ниже или команду /start.", "en": "Sorry, I didn't understand your command. Please use the buttons below or the /start command."}
}

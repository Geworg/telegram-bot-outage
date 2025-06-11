import urllib.parse

CONTACT_PHONE_NUMBER = "+37477123456"
CONTACT_ADDRESS_TEXT = "Երևան, Բադիկյան 99/1"
ENCODED_ADDRESS_FOR_MAP = urllib.parse.quote(CONTACT_ADDRESS_TEXT)
MAP_URL = f"https://www.google.com/maps/search/?api=1&query={ENCODED_ADDRESS_FOR_MAP}"
CLICKABLE_PHONE_MD = f"📞 [{CONTACT_PHONE_NUMBER}](tel:{CONTACT_PHONE_NUMBER})"
CLICKABLE_ADDRESS_MD = f"📍 [{CONTACT_ADDRESS_TEXT}]({MAP_URL})"

translations = {
    "add_address_btn": {"hy": "➕ Ավելացնել հասցե", "ru": "➕ Добавить адрес", "en": "➕ Add address"},
    "remove_address_btn": {"hy": "➖ Հեռացնել հասցե", "ru": "➖ Удалить адрес", "en": "➖ Remove address"},
    "show_addresses_btn": {"hy": "📋 Ցուցադրել հասցեներ", "ru": "📋 Показать адреса", "en": "📋 Show addresses"},
    "clear_all_btn": {"hy": "🧹 Մաքրել բոլորը", "ru": "🧹 Очистить всё", "en": "🧹 Clear all"},
    "check_address_btn": {"hy": "🔍 Ստուգել հասցեն", "ru": "🔍 Проверить адрес", "en": "🔍 Check address"},
    "statistics_btn": {"hy": "📊 Վիճակագրություն", "ru": "📊 Статистика", "en": "📊 Statistics"},
    "help_btn": {"hy": "❓ Օգնություն", "ru": "❓ Помощь", "en": "❓ Help"},
    "subscription_btn": {"hy": "⭐ Բաժանորդագրություն", "ru": "⭐ Подписка", "en": "⭐ Subscription"},
    "address_added": {"hy": "Հասցեն «{address}» ավելացված է։", "ru": "Адрес «{address}» добавлен.", "en": "Address “{address}” added."},
    "address_exists": {"hy": "Հասցեն «{address}» արդեն գոյություն ունի։", "ru": "Адрес «{address}» уже существует.", "en": "Address “{address}” already exists."},
    "address_list": {"hy": "Ձեր ավելացված հասցեներն են․", "ru": "Ваши добавленные адреса:", "en": "Your added addresses:"},
    "address_removed": {"hy": "Հասցեն «{address}» հեռացված է։", "ru": "Адрес «{address}» удалён.", "en": "Address “{address}” removed."},
    "address_not_found_to_remove": {"hy": "Հեռացման համար հասցե «{address}» չի գտնվել:", "ru": "Адрес для удаления «{address}» не найден.", "en": "Address to remove '{address}' not found."},
    "cancel": {"hy": "❌ Չեղարկել", "ru": "❌ Отменить", "en": "❌ Cancel"},
    "cancelled": {"hy": "Գործողությունը չեղարկվեց։", "ru": "Действие отменено.", "en": "Action cancelled."},
    "set_frequency_prompt": {"hy": "Խնդրում եմ ընտրել ստուգման հաճախականությունը։", "ru": "Пожалуйста, выберите частоту проверки:", "en": "Please choose a check frequency:"},
    "cancelled_frequency": {"hy": "Հաճախականության ընտրությունը չեղարկվել է։", "ru": "Выбор частоты отменён.", "en": "Frequency selection cancelled."},
    "frequency_set": {"hy": "Ստուգման հաճախականությունը հաջողությամբ սահմանված է։", "ru": "Частота проверки успешно установлена.", "en": "Check frequency set successfully."},
    "choose_language": {"hy": "Ընտրեք լեզուն:", "ru": "Выберите язык:", "en": "Choose language:"},
    "main_menu_now_active": {"hy": "Հիմնական մենյուն այժմ ակտիվ է {lang_name} լեզվով:", "ru": "Главное меню теперь активно на {lang_name} языке.", "en": "Main menu is now active in {lang_name}."},
    "cancel_btn": {"hy": "❌ Չեղարկել", "ru": "❌ Отмена", "en": "❌ Cancel"},
    "action_cancelled": {"hy": "Գործողությունը չեղարկվեց։", "ru": "Действие отменено.", "en": "Action cancelled."},
    "choose_region_prompt": {"hy": "Ընտրեք մարզը:", "ru": "Выберите область:", "en": "Select the region:"},
    "no_regions_configured": {"hy": "Ցավում եմ, մարզեր դեռ կազմաձևված չեն։", "ru": "К сожалению, области пока не настроены.", "en": "Sorry, regions are not configured yet."},
    "enter_street_prompt": {"hy": "{region} մարզ։\nԽնդրում եմ մուտքագրել փողոցի անունը:", "ru": "Область: {region}.\nПожалуйста, введите название улицы:", "en": "Region: {region}.\nPlease enter the street name:"},
    "street_too_short_error": {"hy": "Փողոցի անունը չափազանց կարճ է։", "ru": "Название улицы слишком короткое.", "en": "The street name is too short."},
    "error_region_not_selected": {"hy": "Սխալ։ Մարզը ընտրված չէ։ Խնդրում եմ նորից փորձել։", "ru": "Ошибка: Область не выбрана. Пожалуйста, попробуйте снова.", "en": "Error: Region not selected. Please try again."},
    "address_being_verified_ai": {"hy": "Հասցեն ստուգվում է AI-ի միջոցով...⏳", "ru": "Адрес проверяется с помощью AI...⏳", "en": "Verifying address with AI...⏳"},
    "ai_street_clarification_failed": {"hy": "Չհաջողվեց ճշգրտել փողոցը «{region}» մարզում։\nAI-ի մեկնաբանություն․ «{error}»", "ru": "Не удалось уточнить улицу для региона «{region}».\nКомментарий AI: «{error}»", "en": "Could not clarify the street for region '{region}'.\nAI comment: '{error}'"},
    "please_try_again_street": {"hy": "Խնդրում եմ փորձել մուտքագրել փողոցը նորից, գուցե ավելի մանրամասն։", "ru": "Пожалуйста, попробуйте ввести улицу еще раз, возможно, более подробно.", "en": "Please try entering the street again, perhaps with more detail."},
    "confirm_address_prompt": {"hy": "Հաստատում եք այս հասցեն՝\nՄարզ/շրջան՝ *{region}*\nՓողոց՝ *{street}*", "ru": "Подтверждаете этот адрес:\nОбласть/район: *{region}*\nУлица: *{street}*", "en": "Do you confirm this address:\nRegion/District: *{region}*\nStreet: *{street}*"},
    "confirm_yes": {"hy": "✅ Այո", "ru": "✅ Да", "en": "✅ Yes"},
    "confirm_no_retry": {"hy": "❌ Ոչ (նորից)", "ru": "❌ Нет (повторить)", "en": "❌ No (retry)"},
    "address_added_successfully": {"hy": "Հասցեն հաջողությամբ ավելացվեց:\n*{region}*, *{street}*", "ru": "Адрес успешно добавлен:\n*{region}*, *{street}*", "en": "Address added successfully:\n*{region}*, *{street}*"},
    "address_already_exists": {"hy": "Այս հասցեն ({region}, {street}) արդեն գոյություն ունի ձեր ցուցակում։", "ru": "Этот адрес ({region}, {street}) уже существует в вашем списке.", "en": "This address ({region}, {street}) already exists in your list."},
    "error_generic_try_again": {"hy": "Տեղի է ունեցել սխալ։ Խնդրում եմ փորձել մի փոքր ուշ։", "ru": "Произошла ошибка. Пожалуйста, попробуйте немного позже.", "en": "An error occurred. Please try again later."},
    "add_address_retry_prompt": {"hy": "Հասցեի ավելացումը չեղարկված է։ Կարող եք նորից փորձել «Ավելացնել հասցե» կոճակով։", "ru": "Добавление адреса отменено. Можете попробовать снова кнопкой «Добавить адрес».", "en": "Address addition cancelled. You can try again using the 'Add Address' button."},
    "main_menu_prompt": {"hy": "Ի՞նչ կուզենայիք անել հիմա:", "ru": "Что бы вы хотели сделать сейчас?", "en": "What would you like to do now?"},
    "no_addresses_to_remove": {"hy": "Դուք դեռ հասցեներ չեք ավելացրել։", "ru": "У вас пока нет добавленных адресов.", "en": "You haven't added any addresses yet."},
    "select_address_to_remove_prompt": {"hy": "Ընտրեք հասցեն, որը ցանկանում եք հեռացնել:", "ru": "Выберите адрес, который хотите удалить:", "en": "Select the address you want to remove:"},
    "address_removed_successfully": {"hy": "Հասցեն ({region}, {street}) հաջողությամբ հեռացվել է։", "ru": "Адрес ({region}, {street}) успешно удален.", "en": "Address ({region}, {street}) removed successfully."},
    "no_addresses_added": {"hy": "Դուք դեռ հասցեներ չեք ավելացրել։", "ru": "Вы еще не добавили ни одного адреса.", "en": "You haven't added any addresses yet."},
    "your_tracked_addresses_list": {"hy": "Ձեր հետևվող հասցեները", "ru": "Ваши отслеживаемые адреса", "en": "Your tracked addresses"},
    "all_addresses_cleared": {"hy": "Բոլոր հասցեները հաջողությամբ մաքրվել են։", "ru": "Все адреса успешно удалены.", "en": "All addresses have been cleared."},
    "feature_not_fully_implemented": {"hy": "Այս գործառույթը դեռ լիովին իրականացված չէ։", "ru": "Эта функция еще не полностью реализована.", "en": "This feature is not fully implemented yet."},
    "contact_us_info": {"hy": "Հարցերի դեպքում կարող եք կապնվել մեզ հետ:", "ru": "Если у вас есть вопросы, вы можете связаться с нами:", "en": "If you have questions, you can contact us:"},
    "help_text_detailed": {
        "hy": (
            "Օգնություն\n\n"
            "**CheckSiteUpdateBot**-ը օգնում է ձեզ տեղեկացված մնալ Հայաստանում ջրի, գազի և էլեկտրաէներգիայի անջատումների մասին։\n\n"
            "**Հիմնական հրամաններ և կոճակներ:**\n"
            "• `/start` - Սկսել\n"
            "• `➕ Ավելացնել հասցե` - Ավելացնել նոր հասցե անջատումները հետևելու համար\n"
            "• `➖ Հեռացնել հասցե` - Հեռացնել նախկինում ավելացված հասցեն\n"
            "• `📋 Ցուցադրել հասցեներ` - Ցուցադրել ձեր բոլոր հասցեները\n"
            "• `🧹 Մաքրել բոլորը` - Հեռացնել ձեր բոլոր հասցեները\n"
            "• `🔍 Ստուգել հասցեն` - Անմիջապես ստուգել անջատումները որոշակի հասցեում\n"
            "• `⚙️ Փոխել լեզուն` - Ընտրել բոտի լեզուն (Հայերեն, Русский, English)\n"
            "• `⏱️ Սահմանել հաճախականությունը` - Սահմանել, թե որքան հաճախ բոտը պետք է ստուգի թարմացումները\n"
            "• `🎵 Ձայնային ծանուցումներ` - Միացնել/անջատել ձայնը նոր անջատումների մասին ծանուցումների համար\n"
            "• `⭐ Բաժանորդագրություն` - Կառավարել ձեր բաժանորդագրության պլանը\n"
            "• `📊 Վիճակագրություն` - Ցուցադրել բոտի և ձեր անձնական վիճակագրությունը\n\n"
            "Հարցերի դեպքում կարող եք կապնվել մեզ հետ:\n"
            f"{CLICKABLE_PHONE_MD}\n"
            f"{CLICKABLE_ADDRESS_MD}"
        ),
        "ru": (
            "Помощь\n\n"
            "**CheckSiteUpdateBot** помогает вам оставаться в курсе отключений воды, газа и электричества в Армении.\n\n"
            "**Основные команды и кнопки:**\n"
            "• `/start` - Начать / Главное меню\n"
            "• `➕ Добавить адрес` - Добавить новый адрес для отслеживания отключений\n"
            "• `➖ Удалить адрес` - Удалить ранее добавленный адрес\n"
            "• `📋 Показать адреса` - Показать все ваши адреса\n"
            "• `🧹 Очистить всё` - Удалить все ваши адреса\n"
            "• `🔍 Проверить адрес` - Мгновенно проверить отключения по конкретному адресу (скоро)\n"
            "• `⚙️ Сменить язык` - Выбрать язык интерфейса бота (Հայերեն, Русский, English)\n"
            "• `⏱️ Задать частоту` - Установить, как часто бот должен проверять обновления\n"
            "• `🎵 Звуковые уведомления` - Включить/выключить звук для уведомлений о новых отключениях\n"
            "• `⭐ Подписка` - Управлять вашим планом подписки (скоро)\n"
            "• `📊 Статистика` - Показать статистику бота и вашу личную (скоро)\n\n"
            "Если у вас есть вопросы, вы можете связаться с нами:\n"
            f"{CLICKABLE_PHONE_MD}\n"
            f"{CLICKABLE_ADDRESS_MD}"
        ),
        "en": (
            "Help\n\n"
            "**CheckSiteUpdateBot** helps you stay informed about water, gas, and electricity outages in Armenia.\n\n"
            "**Main Commands and Buttons:**\n"
            "• `/start` - Start / Main menu\n"
            "• `➕ Add address` - Add a new address to track outages for\n"
            "• `➖ Remove address` - Remove a previously added address\n"
            "• `📋 Show addresses` - Display all your added addresses\n"
            "• `🧹 Clear all` - Remove all your addresses\n"
            "• `🔍 Check address` - Instantly check for outages on a specific address\n"
            "• `⚙️ Change language` - Choose the bot's interface language (Հայերեն, Русский, English)\n"
            "• `⏱️ Set Frequency` - Set how often the bot should check for updates\n"
            "• `🎵 Sound Notifications` - Enable/disable sound for new outage notifications\n"
            "• `⭐ Subscription` - Manage your subscription plan\n"
            "• `📊 Statistics` - Show bot statistics and your personal stats\n\n"
            "If you have questions, you can contact us:\n"
            f"{CLICKABLE_PHONE_MD}\n"
            f"{CLICKABLE_ADDRESS_MD}"
        )
    },
    "unknown_command_short": {"hy": "Սխալ", "ru": "Ошибка", "en": "Error"},
    "stats_not_implemented_yet": {"hy": "Վիճակագրության բաժինը դեռ մշակման փուլում է։ 📊", "ru": "Раздел статистики пока в разработке. 📊", "en": "Statistics section is still under development. 📊"},
    "subscription_info_placeholder": {"hy": "Բաժանորդագրության մասին տեղեկատվությունը շուտով հասանելի կլինի։ ⭐", "ru": "Информация о подписке скоро будет доступна. ⭐", "en": "Subscription information will be available soon. ⭐"},
    "set_frequency_btn": {"hy": "⏱️ Սահմանել հաճախականությունը", "ru": "⏱️ Задать частоту", "en": "⏱️ Set Frequency"},
    "frequency_options_prompt": {"hy": "Ընտրեք, թե որքան հաճախ պետք է ստուգվեն թարմացումները:", "ru": "Выберите, как часто проверять обновления:","en": "Choose how often to check for updates:"},
    "notification_title_water": {"hy": "💧 Ջրամատակարարման Անջատում", "ru": "💧 Отключение Воды", "en": "💧 Water Outage"},
    "notification_title_gas": {"hy": "🔥 Գազամատակարարման Անջատում", "ru": "🔥 Отключение Газа", "en": "🔥 Gas Outage"},
    "notification_title_electric": {"hy": "⚡️ Էլեկտրաէներգիայի Անջատում", "ru": "⚡️ Отключение Электричества", "en": "⚡️ Electricity Outage"},
    "notification_title_generic": {"hy": "⚠️ Ուշադրություն՝ Անջատում", "ru": "⚠️ Внимание: Отключение", "en": "⚠️ Attention: Outage"},
    "shutdown_type": {"hy": "Տեսակ", "ru": "Тип", "en": "Type"},
    "start_time": {"hy": "Սկիզբ", "ru": "Начало", "en": "Start"},
    "end_time": {"hy": "Ավարտ", "ru": "Окончание", "en": "End"},
    "duration": {"hy": "Տևողություն", "ru": "Продолжительность", "en": "Duration"},
    "hours_short": {"hy": "ժ", "ru": "ч", "en": "h"},
    "regions": {"hy": "Մարզեր/շրջաններ", "ru": "Районы", "en": "Regions/Districts"},
    "addresses": {"hy": "Հասցեներ", "ru": "Адреса", "en": "Addresses"},
    "details": {"hy": "Մանրամասներ", "ru": "Детали", "en": "Details"},
    "ad_message_free_tier": {"hy": "CheckSiteUpdateBot․ Հետևեք ջրի, գազի, հոսանքի անջատումներին Հայաստանում։ Իմացեք ավելին վճարովի հնարավորությունների մասին՝ /subscription", "ru": "CheckSiteUpdateBot: Отслеживайте отключения воды, газа, света в Армении! Узнайте о платных функциях для более частых проверок: /subscription", "en": "CheckSiteUpdateBot: Track water, gas, & electricity outages in Armenia! Learn about premium features for more frequent checks: /subscription"},
    "sound_settings_btn": {"hy": "🎵 Ձայնային կարգավորումներ", "ru": "🎵 Звуковые уведомления", "en": "🎵 Sound Settings"},
    "sound_settings_title": {"hy": "Ձայնային ծանուցումների կարգավորումներ", "ru": "Настройки звуковых уведомлений", "en": "Sound Notification Settings"},
    "notification_sound_on": {"hy": "🔊 Ձայնը ՄԻԱՑՎԱԾ Է", "ru": "🔊 Звук ВКЛЮЧЕН", "en": "🔊 Sound ON"},
    "notification_sound_off": {"hy": "🔇 Ձայնը ԱՆՋԱՏՎԱԾ Է", "ru": "🔇 Звук ВЫКЛЮЧЕН", "en": "🔇 Sound OFF"},
    "toggle_sound": {"hy": "Փոխել ձայնը (Միաց/Անջատ)", "ru": "Переключить звук (Вкл/Выкл)", "en": "Toggle Sound (On/Off)"},
    "set_silent_start_time": {"hy": "Սահմանել սկիզբը (օր. 23:00)", "ru": "Установить начало (напр. 23:00)", "en": "Set Start Time (e.g. 23:00)"},
    "set_silent_end_time": {"hy": "Սահմանել ավարտը (օր. 07:00)", "ru": "Установить конец (напр. 07:00)", "en": "Set End Time (e.g. 07:00)"},
    "enter_silent_start_time_prompt": {"hy": "Մուտքագրեք գիշերային ռեժիմի սկզբի ժամը (ֆորմատ՝ ժժ:րր, օրինակ՝ 22:30):", "ru": "Введите время начала ночного режима (формат ЧЧ:ММ, например, 22:30):", "en": "Enter silent mode start time (HH:MM format, e.g., 22:30):"},
    "enter_silent_end_time_prompt": {"hy": "Մուտքագրեք գիշերային ռեժիմի ավարտի ժամը (ֆորմատ՝ ժժ:րր, օրինակ՝ 07:00):", "ru": "Введите время окончания ночного режима (формат ЧЧ:ММ, например, 07:00):", "en": "Enter silent mode end time (HH:MM format, e.g., 07:00):"},
    "invalid_time_format": {"hy": "Ժամանակի սխալ ձևաչափ: Խնդրում եմ մուտքագրել ժժ:րր տեսքով:", "ru": "Неверный формат времени. Пожалуйста, введите в формате ЧЧ:ММ.", "en": "Invalid time format. Please enter in HH:MM format."},
    "sound_settings_saved": {"hy": "Ձայնային կարգավորումները պահպանված են:", "ru": "Настройки звука сохранены.", "en": "Sound settings saved."},
    "command_sound_description": {"hy": "Ձայնային կարգավորումներ", "ru": "Настройки звука", "en": "Sound settings"},
    "current_sound_status_prompt": {"hy": "Ընթացիկ ձայնային կարգավիճակը՝ *{status}*։\nՑանկանու՞մ եք փոխել այն։", "ru": "Текущий статус звуковых уведомлений: *{status}*.\nХотите изменить?", "en": "Current sound notification status: *{status}*.\nDo you want to change it?"},
    "sound_on": {"hy": "Միացված", "ru": "Включены", "en": "Enabled"},
    "sound_off": {"hy": "Անջատված", "ru": "Выключены", "en": "Disabled"},
    "turn_sound_on": {"hy": "🔊 Միացնել ձայնը", "ru": "🔊 Включить звук", "en": "🔊 Enable Sound"},
    "turn_sound_off": {"hy": "🔇 Անջատել ձայնը", "ru": "🔇 Выключить звук", "en": "🔇 Disable Sound"},
    "sound_turned_on_confirmation": {"hy": "Ձայնային ծանուցումները միացված են։", "ru": "Звуковые уведомления включены.", "en": "Sound notifications enabled."},
    "sound_turned_off_confirmation": {"hy": "Ձայնային ծանուցումները անջատված են։", "ru": "Звуковые уведомления выключены.", "en": "Sound notifications disabled."},
    "choose_language_prompt": {"hy": "Ընտրեք լեզուն:", "ru": "Выберите язык:", "en": "Select language:"},
    "choose_language_prompt_button": {"hy": "Խնդրում եմ ընտրել նոր լեզուն՝ օգտագործելով ներքևի կոճակները:", "ru": "Пожалуйста, выберите новый язык, используя кнопки ниже:", "en": "Please select your new language using the buttons below:"},
    "choose_language_initial_prompt": {"hy": "Խնդրում եմ ընտրել ձեր նախընտրած լեզուն շարունակելու համար:", "ru": "Пожалуйста, выберите предпочитаемый язык для продолжения:", "en": "Please select your preferred language to continue:"},
    "language_changed_confirmation": {"hy": "Լեզուն փոխված է {lang_name}", "ru": "Язык изменен на {lang_name}", "en": "Language changed to {lang_name}"},
    "choose_region": {"hy": "Խնդրում եմ ընտրել տարածաշրջան։", "ru": "Пожалуйста, выберите регион:", "en": "Please choose a region:"},
    "error_invalid_region_selection": {"hy": "Սխալ մարզի ընտրություն: Խնդրում եմ ընտրել կոճակներից:", "ru": "Неверный выбор региона. Пожалуйста, выберите из кнопок.", "en": "Invalid region selection. Please choose from the buttons."},
    "confirm_clear": {"hy": "Վստա՞հ եք, որ ցանկանում եք մաքրել բոլոր հասցեներն ու տվյալները։", "ru": "Вы уверены, что хотите удалить все адреса и данные?", "en": "Are you sure you want to clear all addresses and data?"},
    "please_confirm_yes_no": {"hy": "Խնդրում եմ հաստատել (Այո/Ոչ)։", "ru": "Пожалуйста, подтвердите (Да/Нет).", "en": "Please confirm (Yes/No)."},
    "enter_street_for_add": {"hy": "➕ Ավելացնելու համար մուտքագրեք փողոցի անունը։", "ru": "➕ Для добавления введите название улицы:", "en": "➕ To add, enter the street name:"},
    "error_invalid_input": {"hy": "Սխալ մուտքագրում: Խնդրում եմ նորից փորձել:", "ru": "Некорректный ввод. Пожалуйста, попробуйте снова.", "en": "Invalid input. Please try again."},
    "error_rate_limit": {"hy": "Չափազանց շատ հարցումներ: Խնդրում եմ սպասել:", "ru": "Слишком много запросов. Пожалуйста, подождите.", "en": "Too many requests. Please wait."},
    "change_language_btn": {"hy": "🌐 Փոխել լեզուն", "ru": "🌐 Сменить язык", "en": "🌐 Change Language"},
    "error_invalid_selection": {"hy": "Սխալ ընտրություն։ Խնդրում ենք ընտրել կոճակներից մեկը։", "ru": "Неверный выбор. Пожалуйста, выберите одну из кнопок.", "en": "Invalid selection. Please choose one of the buttons."},
    "language_set": {"hy": "Լեզուն հաջողությամբ ընտրված է։", "ru": "Язык успешно выбран.", "en": "Language selected successfully."},
    "no_addresses": {"hy": "Դուք դեռ չունեք ավելացված հասցեներ։", "ru": "У вас пока нет добавленных адресов.", "en": "You don’t have any added addresses yet."},
    "shutdown_check_found": {"hy": "⚠️ «{address}» հասցեի համար հայտնաբերվել են հետևյալ անջատում(ներ)ը՝ {types}։", "ru": "⚠️ Для адреса «{address}» найдены следующие отключения: {types}.", "en": "⚠️ The following outage(s) were found for address “{address}”: {types}."},
    "shutdown_check_not_found": {"hy": "✅ «{address}» հասցեի համար պլանային կամ վթարային անջատումներ չեն հայտնաբերվել։", "ru": "✅ Для адреса «{address}» плановых или аварийных отключений не найдено.", "en": "✅ No planned or emergency outages found for address “{address}”."},
    "welcome": {"hy": "Ողջույն, {name} 👋 Ես CheckSiteUpdateBot-ն եմ, պատրաստ եմ օգնել ձեզ տեղեկացված մնալ կոմունալ անջատումների մասին:", "ru": "Привет, {name} 👋 Я CheckSiteUpdateBot, готов помочь вам оставаться в курсе отключений коммунальных услуг!", "en": "Hello, {name} 👋 I'm CheckSiteUpdateBot, ready to help you stay informed about utility outages!"},
    "start_text": {"hy": "Բարև ձեզ։ Ես CheckSiteUpdateBot-ն եմ, ձեր օգնականը Հայաստանում կոմունալ ծառայությունների անջատումներին հետևելու համար։", "ru": "Здравствуйте! Я CheckSiteUpdateBot, ваш помощник для отслеживания отключений коммунальных услуг в Армении.", "en": "Hello! I'm CheckSiteUpdateBot, your assistant for tracking utility outages in Armenia."},
    "water_off": {"hy": "ՋՐԻ անջատում", "ru": "ОТКЛЮЧЕНИЕ ВОДЫ", "en": "WATER outage"},
    "gas_off": {"hy": "ԳԱԶԻ անջատում", "ru": "ОТКЛЮЧЕНИЕ ГАЗА", "en": "GAS outage"},
    "electric_off": {"hy": "ԷԼԵԿՏՐԱԷՆԵՐԳԻԱՅԻ անջատում", "ru": "ОТКЛЮЧЕНИЕ ЭЛЕКТРИЧЕСТВА", "en": "ELECTRICITY outage"},
    "yes": {"hy": "Այո", "ru": "Да", "en": "Yes"},
    "no": {"hy": "Ոչ", "ru": "Нет", "en": "No"},
    "no_save_original": {"hy": "Ոչ, պահպանել իմ տարբերակը", "ru": "Нет, сохранить мою версию", "en": "No, save my version"},
    "please_use_buttons_for_frequency": {"hy": "Խնդրում եմ օգտվել կոճակներից՝ հաճախականությունն ընտրելու համար։", "ru": "Пожалуйста, используйте кнопки для выбора частоты.", "en": "Please use the buttons to select the frequency."},
    "amd_short": {"hy": "դր", "ru": "драм", "en": "AMD"},
    "month_short": {"hy": "ամս.", "ru": "мес.", "en": "mo."},
    "minutes_short": {"hy": "ր", "ru": "мин", "en": "min"},
    "free": {"hy": "Անվճար", "ru": "Бесплатно", "en": "Free"},
    "tier_free": {"hy": "Անվճար", "ru": "Бесплатный", "en": "Free"},
    "tier_basic": {"hy": "Հիմնական", "ru": "Базовый", "en": "Basic"},
    "tier_premium": {"hy": "Պրեմիում", "ru": "Премиум", "en": "Premium"},
    "tier_ultra": {"hy": "Ուլտրա", "ru": "Ультра", "en": "Ultra"},
    "menu_returned": {"hy": "Վերադարձ գլխավոր մենյու։", "ru": "Возврат в главное меню.", "en": "Returned to main menu."},
    "error_generic": {"hy": "Տեղի է ունեցել սխալ։ Խնդրում եմ փորձել մի փոքր ուշ։", "ru": "Произошла ошибка. Пожалуйста, попробуйте позже.", "en": "An error occurred. Please try again later."},
    "error_generic_admin": {"hy": "Տեղի է ունեցել համակարգային սխալ: Խնդրում եմ տեղեկացնել ադմինիստրատորին:", "ru": "Произошла системная ошибка. Пожалуйста, сообщите администратору.", "en": "A system error occurred. Please inform the administrator."}, # Пункт 5
    "error_invalid_tier": {"hy": "Ընտրված է սխալ բաժանորդագրության տարբերակ:", "ru": "Выбран неверный вариант подписки.", "en": "Invalid subscription tier selected."},
    "error_region_not_selected_for_check": {"hy": "Ստուգման համար տարածաշրջանն ընտրված չէ։ Խնդրում եմ նորից փորձել։", "ru": "Регион для проверки не выбран. Пожалуйста, попробуйте снова.", "en": "Region for check not selected. Please try again."}, # Пункт 2
    "error_confirmation_timeout": {"hy": "Հաստատման սխալ (հնարավոր է ժամանակի սպառում): Խնդրում եմ նորից փորձել հասցեի ավելացումը:", "ru": "Ошибка подтверждения (возможно, истекло время). Пожалуйста, попробуйте добавить адрес снова.", "en": "Confirmation error (possibly timed out). Please try adding the address again."}, # Пункт 6а
    "error_final_street_empty": {"hy": "Չհաջողվեց որոշել փողոցը: Խնդրում եմ նորից փորձել:", "ru": "Не удалось определить улицу. Пожалуйста, попробуйте снова.", "en": "Failed to determine street. Please try again."}, # Пункт 6а
    "shutdown_found_for_new_address": {"hy": "ℹ️ Ուշադրություն։ Նոր հասցեի համար հայտնաբերվել են հետևյալ ակտիվ անջատում(ներ)ը՝ {types}։", "ru": "ℹ️ Внимание! Для нового адреса обнаружены следующие активные отключения: {types}.", "en": "ℹ️ Attention! The following active outage(s) were found for the new address: {types}."},
    "no_shutdowns_for_new_address": {"hy": "✅ Նոր հասցեի համար ակտիվ անջատումներ այս պահին չեն հայտնաբերվել։", "ru": "✅ Для нового адреса активные отключения на данный момент не найдены.", "en": "✅ No active outages found for the new address at this time."},
    "subscription_options_title": {"hy": "Ընտրեք բաժանորդագրության պլանը:", "ru": "Выберите план подписки:", "en": "Choose your subscription plan:"},
    "subscription_success_details": {"hy": "Դուք հաջողությամբ բաժանորդագրվեցիք «{plan}» պլանին։ Ստուգման հաճախականությունը՝ {interval}։", "ru": "Вы успешно подписались на план «{plan}». Частота проверки: {interval}.", "en": "You have successfully subscribed to the “{plan}” plan. Check interval: {interval}."},
    "subscription_free_success_details": {"hy": "Դուք ընտրել եք «{plan}» պլանը։ Ստուգման հաճախականությունը՝ {interval}։", "ru": "Вы выбрали план «{plan}». Частота проверки: {interval}.", "en": "You have selected the “{plan}” plan. Check interval: {interval}."},
    "use_inline_buttons_for_subscription": {"hy": "Խնդրում եմ օգտագործել հաղորդագրության տակի կոճակները՝ բաժանորդագրությունն ընտրելու համար։", "ru": "Пожалуйста, используйте кнопки под сообщением для выбора подписки.", "en": "Please use the buttons under the message to choose a subscription."},
    "unknown_command": {"hy": "Անհայտ հրաման։ Խնդրում եմ օգտվել մենյուի կոճակներից։", "ru": "Неизвестная команда. Пожалуйста, используйте кнопки меню.", "en": "Unknown command. Please use the menu buttons."},
    "date_time_label": {"hy": "Ժամանակահատված", "ru": "Период", "en": "Period"},
    "locations_label": {"hy": "Տեղանքներ", "ru": "Местоположения", "en": "Locations"},
    "streets_label": {"hy": "Փողոցներ", "ru": "Улицы", "en": "Streets"},
    "all_streets_in_region": {"hy": "Բոլոր փողոցները նշված վայր(եր)ում", "ru": "Все улицы в указанном месте(ах)", "en": "All streets in specified location(s)"}, # Пункт 1
    "status_label": {"hy": "Կարգավիճակ", "ru": "Статус", "en": "Status"},
    "published_label": {"hy": "Հրապարակված է", "ru": "Опубликовано", "en": "Published"},
    "water_off_short": {"hy": "Ջուր", "ru": "Вода", "en": "Water"},
    "gas_off_short": {"hy": "Գազ", "ru": "Газ", "en": "Gas"},
    "electric_off_short": {"hy": "Էլեկտր.", "ru": "Электр.", "en": "Electr."},
    "help_unavailable": {"hy": "Օգնության բաժինը ձեր լեզվով դեռ հասանելի չէ։", "ru": "Раздел помощи пока не доступен на вашем языке.", "en": "Help section is not yet available in your language."},
    "stats_uptime": {"hy": "Աշխատանքի տևող.", "ru": "Время работы", "en": "Uptime"},
    "stats_days_unit": {"hy": "օր", "ru": "д", "en": "d"},
    "stats_hours_unit": {"hy": "ժ", "ru": "ч", "en": "h"},
    "stats_minutes_unit": {"hy": "ր", "ru": "м", "en": "m"},
    "stats_users_with_addresses": {"hy": "Օգտատեր հասցեներով", "ru": "Польз. с адресами", "en": "Users with addresses"},
    "stats_total_addresses": {"hy": "Ընդհանուր հասցեներ", "ru": "Всего адресов", "en": "Total addresses"},
    "stats_your_info_title": {"hy": "Ձեր տվյալները", "ru": "Ваша информация", "en": "Your Information"},
    "stats_your_addresses": {"hy": "Ձեր հասցեները", "ru": "Ваши адреса", "en": "Your addresses"},
    "stats_your_notifications_sent": {"hy": "Ձեզ ուղարկված ծանուց.", "ru": "Уведомлений вам", "en": "Notifications to you"},
    "statistics_title": {"hy": "Բոտի վիճակագրություն", "ru": "Статистика Бота", "en": "Bot Statistics"},
    "command_start_description": {"hy": "Սկսել", "ru": "Старт", "en": "Start"},
    "command_language_description": {"hy": "Փոխել լեզուն", "ru": "Изменить язык", "en": "Change language"},
    "command_addaddress_description": {"hy": "Ավելացնել հասցե", "ru": "Добавить адрес", "en": "Add address"},
    "command_myaddresses_description": {"hy": "Իմ հասցեները", "ru": "Мои адреса", "en": "My addresses"},
    "command_checkaddress_description": {"hy": "Ստուգել հասցեն հիմա", "ru": "Проверить адрес сейчас", "en": "Check address now"},
    "command_frequency_description": {"hy": "Սահմանել ստուգման հաճախականությունը", "ru": "Установить частоту проверок", "en": "Set check frequency"},
    "command_subscription_description": {"hy": "Կառավարել բաժանորդագրությունը", "ru": "Управлять подпиской", "en": "Manage subscription"},
    "command_stats_description": {"hy": "Դիտել վիճակագրությունը", "ru": "Посмотреть статистику", "en": "View statistics"},
    "command_help_description": {"hy": "Ստանալ օգնություն", "ru": "Получить помощь", "en": "Get help"},
    "address_clarifying_ai": {"hy": "Ստուգում եմ հասցեն բանականության միջոցով... 🤖", "ru": "Проверяю адрес с помощью ИИ... 🤖", "en": "Checking address with AI... 🤖"},
    "ai_clarify_prompt": {"hy": "ԻԻ-ն առաջարկում է՝ «{suggested_address}»։ Արդյո՞ք սա ճիշտ է:", "ru": "ИИ предлагает: «{suggested_address}». Это верно?", "en": "AI suggests: '{suggested_address}'. Is this correct?"},
    "ai_clarify_failed_save_original_prompt": {"hy": "ԻԻ-ն չկարողացավ ճշգրտել։ Պահպանե՞լ «{address}» հասցեն, ինչպես մուտքագրել եք:", "ru": "ИИ не смог уточнить. Сохранить «{address}» как есть?", "en": "AI couldn't clarify. Save '{address}' as is?"},
    "confirm_ai_save_original": {"hy": "Այո, պահպանել ինչպես կա", "ru": "Да, сохранить как есть", "en": "Yes, save as is"},
    "address_clarification_cancelled": {"hy": "Հասցեի ավելացումը չեղարկված է։ Խնդրում եմ, փորձեք նորից կամ մուտքագրեք ավելի ճշգրիտ։", "ru": "Добавление адреса отменено. Пожалуйста, попробуйте снова или введите более точно.", "en": "Address addition cancelled. Please try again or enter more precisely."},
    "admin_command_not_authorized": {"hy": "Դուք իրավասու չեք այս հրամանն օգտագործելու համար։", "ru": "Вы не авторизованы для использования этой команды.", "en": "You are not authorized to use this command."},
    "maintenance_on_admin_feedback": {"hy": "Սպասարկման ռեժիմը ՄԻԱՑՎԱԾ Է։ Օգտատերերը կտեղեկացվեն հետևյալ հաղորդագրությամբ՝ «{message}»", "ru": "Режим обслуживания ВКЛЮЧЕН. Пользователи будут уведомлены сообщением: «{message}»", "en": "Maintenance mode ON. Users will be notified with: '{message}'"},
    "maintenance_on_default_user_message": {"hy": "⚙️ Բոտը ժամանակավորապես սպասարկման մեջ է և շուտով կվերականգնի իր աշխատանքը։", "ru": "⚙️ Бот временно находится на техническом обслуживании и скоро возобновит работу.", "en": "⚙️ The bot is temporarily undergoing maintenance and will be back shortly."},
    "maintenance_off_admin_feedback": {"hy": "Սպասարկման ռեժիմը ԱՆՋԱՏՎԱԾ Է։", "ru": "Режим обслуживания ВЫКЛЮЧЕН.", "en": "Maintenance mode OFF."},
    "bot_active_again_user_notification": {"hy": "✅ Բոտը վերսկսել է իր աշխատանքը։ Կարող եք օգտվել բոլոր գործառույթներից։", "ru": "✅ Бот возобновил работу! Вы можете использовать все функции.", "en": "✅ The bot is back online! You can use all features now."},
    "bot_under_maintenance_user_notification": {"hy": "⚙️ Բոտը ժամանակավորապես անհասանելի է տեխնիկական սպասարկման պատճառով։ Խնդրում ենք փորձել ավելի ուշ։", "ru": "⚙️ Бот временно недоступен из-за технического обслуживания. Пожалуйста, попробуйте позже.", "en": "⚙️ The bot is temporarily unavailable due to maintenance. Please try again later."},
    "choose_language_inline": {"hy": "Ընտրեք ձեր նախընտրած լեզուն:", "ru": "Выберите предпочитаемый язык:", "en": "Choose your preferred language:"},
    "choose_region_for_check": {"hy": "🔍 Ստուգման համար ընտրեք տարածաշրջանը:", "ru": "🔍 Для проверки выберите регион:", "en": "🔍 Choose region to check:"},
    "enter_street_for_check": {"hy": "🔍 Ստուգման համար մուտքագրեք փողոցի անունը:", "ru": "🔍 Для проверки введите название улицы:", "en": "🔍 To check, enter the street name:"},
    "checking_now": {"hy": "⏳ Ստուգում եմ, խնդրում եմ սպասել...", "ru": "⏳ Проверяю, пожалуйста, подождите...", "en": "⏳ Checking, please wait..."},
    "shutdown_check_found_v2_intro": {"hy": "⚠️ «{address_display}» հասցեի համար հայտնաբերվել են հետևյալ ակտիվ անջատումները.", "ru": "⚠️ Для адреса «{address_display}» найдены следующие активные отключения:", "en": "⚠️ Active outages found for '{address_display}':"},
    "shutdown_check_not_found_v2": {"hy": "✅ «{address_display}» հասցեի համար այս պահին ակտիվ անջատումներ չեն հայտնաբերվել։", "ru": "✅ Для адреса «{address_display}» на данный момент активные отключения не найдены.", "en": "✅ No active outages found for '{address_display}' at this time."},
    "silent_mode_on": {"hy": "🌙 Գիշերային ռեժիմ ({start}-{end})", "ru": "🌙 Ночной режим ({start}-{end})", "en": "🌙 Silent Mode ({start}-{end})"},
    "silent_mode_off": {"hy": "☀️ Սովորական ռեժիմ", "ru": "☀️ Обычный режим", "en": "☀️ Normal Mode"},
    "toggle_silent_mode": {"hy": "Գիշերային ռեժիմ", "ru": "Ночной режим", "en": "Silent Mode"},
    "back_to_main_menu_btn": {"hy": "⬅️ Հետ դեպի գլխավոր մենյու", "ru": "⬅️ Назад в главное меню", "en": "⬅️ Back to Main Menu"},
    "set_frequency_prompt": {"hy": "Ընտրեք ստուգման հաճախականությունը:", "ru": "Выберите частоту проверки:", "en": "Choose check frequency:"},
    "frequency_set": {"hy": "Հաճախականությունը սահմանված է:", "ru": "Частота установлена.", "en": "Frequency set."},
    "invalid_frequency_option": {"hy": "Սխալ ընտրություն: Խնդրում եմ ընտրել ցուցակից կամ սեղմել «Չեղարկել»:", "ru": "Неверный выбор. Пожалуйста, выберите из списка или нажмите «Отмена».", "en": "Invalid choice. Please select from the list or press 'Cancel'."},
    "premium_required_for_frequency": {"hy": "Այս հաճախականության համար պահանջվում է ավելի բարձր մակարդակի բաժանորդագրություն:", "ru": "Для этой частоты требуется подписка более высокого уровня.", "en": "This frequency requires a higher subscription tier."},
}

# <3
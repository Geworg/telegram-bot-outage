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
TIER_LABELS = {"Free": {"hy": "Անվճար", "ru": "Бесплатный", "en": "Free"}, "Basic": {"hy": "Հիմնական", "ru": "Базовый", "en": "Basic"}, "Premium": {"hy": "Պրեմիում", "ru": "Премиум", "en": "Premium"}, "Ultra": {"hy": "Ուլտրա", "ru": "Ультра", "en": "Ultra"}}

# --- Translations Dictionary ---
translations = {}

# --- Main Menu & Commands ---
translations["add_address_btn"] = {"hy": "➕ Ավելացնել հասցե", "ru": "➕ Добавить адрес", "en": "➕ Add Address"}
translations["remove_address_btn"] = {"hy": "➖ Հեռացնել հասցե", "ru": "➖ Удалить адрес", "en": "➖ Remove Address"}
translations["my_addresses_btn"] = {"hy": "📌 Իմ հասցեները", "ru": "📌 Мои адреса", "en": "📌 My Addresses"}
translations["frequency_btn"] = {"hy": "⏱️ Ստուգման հաճախականություն", "ru": "⏱️ Частота проверок", "en": "⏱️ Check Frequency"}
translations["qa_btn"] = {"hy": "💬 Հարցեր և պատասխաններ", "ru": "💬 Вопрос–ответ", "en": "💬 Q&A"}
translations["clear_addresses_btn"] = {"hy": "🗑️ Մաքրել բոլոր հասցեները", "ru": "🗑️ Очистить все адреса", "en": "🗑️ Clear All Addresses"}
translations["check_address_btn"] = {"hy": "🔎 Ստուգել հասցեն", "ru": "🔎 Проверить адрес", "en": "🔎 Check Address"}

# --- Command Descriptions ---
translations["cmd_start"] = {"hy": "Սկսել/Մենյու", "ru": "Старт/Меню", "en": "Start/Menu"}
translations["cmd_myaddresses"] = {"hy": "Իմ հասցեները", "ru": "Мои адреса", "en": "My addresses"}
translations["cmd_clearaddresses"] = {"hy": "Մաքրել բոլոր հասցեները", "ru": "Очистить все адреса", "en": "Clear all addresses"}
translations["cmd_frequency"] = {"hy": "Ստուգման հաճախականություն", "ru": "Частота проверок", "en": "Check frequency"}
translations["cmd_qa"] = {"hy": "Հարցեր ու պատասխաններ և աջակցություն", "ru": "Вопрос–ответ и поддержка", "en": "Q&A and Support"}
translations["cmd_language"] = {"hy": "Փոխել լեզուն", "ru": "Сменить язык", "en": "Change language"}

# --- General UI ---
translations["cancel"] = {"hy": "⛔ Չեղարկել", "ru": "⛔ Отменить", "en": "⛔ Cancel"}
translations["yes"] = {"hy": "✅ Այո", "ru": "✅ Да", "en": "✅ Yes"}
translations["no"] = {"hy": "❌ Ոչ", "ru": "❌ Нет", "en": "❌ No"}
translations["back_btn"] = {"hy": "↩️ Հետ", "ru": "↩️ Назад", "en": "↩️ Back"}
translations["no_cancel_action_btn"] = {"hy": "❌ Ոչ, չեղարկել գործողությունը", "ru": "❌ Нет, отменить действие", "en": "❌ No, cancel the action"}
translations["menu_message"] = {"hy": "📋 Դուք գտնվում եք գլխավոր ցանկում։ Խնդրում ենք ընտրել գործողություն՝ օգտագործելով կոճակներ կամ հրամաններ։ Եթե ունեք ​​դժվարություններ կամ չեք հասկանում միջերեսը, սեղմեք «💬 Հարցեր և պատասխաններ» կոճակը կամ ուղարկեք /qa հրամանը չատում։",
                                "ru": "📋 Вы находитесь в главном меню. Пожалуйста, выберите действие с помощью кнопок или команд. Если возникли трудности или непонимание интерфейса, нажмите кнопку „💬 Вопрос–ответ“ или отправьте команду /qa в чат.",
                                "en": "📋 You are in the main menu. Please select an action using buttons or commands. If you have any difficulties or do not understand the interface, click the '💬 Q&A' button or send the /qa command in the chat."}
translations["action_cancelled"] = {"hy": "Գործողությունը չեղարկվեց։", "ru": "Действие отменено.", "en": "Action cancelled."}
translations["error_generic"] = {"hy": "Տեղի է ունեցել սխալ։ Խնդրում եմ փորձել մի փոքր ուշ։", "ru": "Произошла ошибка. Пожалуйста, попробуйте немного позже.", "en": "An error occurred. Please try again later."}
translations["unknown_command"] = {"hy": "Անհայտ հրաման։ Օգտագործեք կոճակներ կամ հրամաններ։", "ru": "Неизвестная команда. Используйте кнопки или команды.", "en": "Unknown command. Use buttons or commands."}

# --- Language Selection ---
translations["initial_language_prompt"] = {"hy": "Խնդրում ենք ընտրել բոտի լեզուն՝ օգտագործելով ստորև տրված կոճակները։", "ru": "Пожалуйста, выберите язык бота, используя кнопки ниже.", "en": "Please select the bot's language using the buttons below."}
translations["change_language_prompt"] = {"hy": "Ընտրեք լեզուն:", "ru": "Выберите язык:", "en": "Choose the language:"}
translations["language_set_success"] = {"hy": "Լեզուն փոխված է հայերենի։", "ru": "Язык изменён на русский.", "en": "Language changed to English."}

# --- Address Management ---
translations["choose_region"] = {"hy": "Ընտրեք մարզը կամ Երևան քաղաքը:", "ru": "Выберите область или город Ереван:", "en": "Choose region or city Yerevan:"}
translations["enter_street"] = {"hy": "Ընտրված է {region}։\nԱյժմ մուտքագրեք փողոցի և շենքի համարը (օրինակ՝ Աբովյանի փողոց, 5)․", "ru": "Выбрано: {region}.\nТеперь введите улицу и номер дома (например: улица Абовяна, 5):", "en": "Selected: {region}.\nNow, enter street and house number (e.g., Abovyan Street, 5):"}
translations["address_verifying"] = {"hy": "⏳ Ստուգում եմ հասցեն...", "ru": "⏳ Проверяю адрес...", "en": "⏳ Verifying address..."}
translations["address_not_found_yandex"] = {"hy": "Ցավոք, չհաջողվեց գտնել այդպիսի հասցե։ Խնդրում եմ, փորձեք նորից՝ մուտքագրելով ինչպես Յանդեքս Քարտեզում, օրինակ՝ улица Ханджяна, 9Б։", "ru": "К сожалению, нам не удалось найти такой адрес. Попробуйте еще раз, введя его как в Яндекс.Картах, например: улица Ханджяна, 9Б.", "en": "Unfortunately, we were unable to find such an address. Please try again by entering it as in Yandex Maps, for example: улица Ханджяна, 9Б."}
translations["address_confirm_prompt"] = {"hy": "Հայտնաբերվել է հետևյալ հասցեն՝\n\n`{address}`\n\nՊահպանե՞լ այն:", "ru": "Найден следующий адрес:\n\n`{address}`\n\nСохранить его?", "en": "The following address was found:\n\n`{address}`\n\nSave it?"}
translations["address_added_success"] = {"hy": "✅ Հասցեն հաջողությամբ ավելացվել է։", "ru": "✅ Адрес успешно добавлен.", "en": "✅ The address has been successfully added."}
translations["address_already_exists"] = {"hy": "ℹ️ Այս հասցեն արդեն գոյություն ունի ձեր ցուցակում։", "ru": "ℹ️ Этот адрес уже существует в вашем списке.", "en": "ℹ️ This address already exists in your list."}
translations["no_addresses_yet"] = {"hy": "Դուք դեռ հասցեներ չեք ավելացրել։", "ru": "У вас пока нет добавленных адресов.", "en": "You haven't added any addresses yet."}
translations["your_addresses_list_title"] = {"hy": "Ձեր պահպանված հասցեները:", "ru": "Ваши сохранённые адреса:", "en": "Your saved addresses:"}
translations["select_address_to_remove"] = {"hy": "Ընտրեք հասցեն, որը ցանկանում եք հեռացնել։", "ru": "Выберите адрес для удаления.", "en": "Select an address to remove."}
translations["address_removed_success"] = {"hy": "✅ Հասցեն հեռացված է։", "ru": "✅ Адрес удалён.", "en": "✅ Address removed."}
translations["clear_addresses_prompt"] = {"hy": "⚠️ Վստա՞հ եք, որ ցանկանում եք հեռացնել ձեր բոլոր հասցեները։ Այս գործողությունը հետ շրջել հնարավոր չէ։", "ru": "⚠️ Вы уверены, что хотите удалить все свои адреса? Это действие необратимо.", "en": "⚠️ Are you sure you want to remove all your addresses? This action cannot be undone."}
translations["all_addresses_cleared"] = {"hy": "🗑️ Ձեր բոլոր հասցեները հեռացված են։", "ru": "🗑️ Все ваши адреса были удалены.", "en": "🗑️ All your addresses have been removed."}
translations["outage_check_on_add_title"] = {"hy": "🔍 Ստուգում նոր հասցեի համար...", "ru": "🔍 Проверка для нового адреса...", "en": "🔍 Check for new address..."}
translations["outage_check_on_add_none_found"] = {"hy": "✅ Այս պահին ձեր նոր հասցեի համար ակտիվ կամ սպասվող անջատումներ չեն հայտնաբերվել։", "ru": "✅ На данный момент для вашего нового адреса не найдено активных или предстоящих отключений.", "en": "✅ No active or upcoming outages found for your new address at this time."}
translations["outage_check_on_add_found"] = {"hy": "⚠️ *Ուշադրություն։* Հայտնաբերվել են անջատումներ ձեր նոր հասցեի համար։", "ru": "⚠️ *Внимание!* Обнаружены отключения для вашего нового адреса:", "en": "⚠️ *Attention!* Outages found for your new address:"}

# --- Frequency ---
translations["frequency_prompt"] = {"hy": "Ընտրեք ստուգման հաճախականությունը.", "ru": "Выберите частоту проверки:", "en": "Choose the check frequency:"}
translations["frequency_current"] = {"hy": "Ստուգումների ներկայիս հաճախականությունը՝", "ru": "Текущая частота проверок:", "en": "Current frequency of checks:"}
translations["frequency_set_success"] = {"hy": "⏱️ Ստուգման հաճախականությունը փոխված է։", "ru": "⏱️ Частота проверки изменена.", "en": "⏱️ Check frequency has been changed."}
translations["frequency_tier_required"] = {"hy": "Այս հաճախականության համար պահանջվում է «{tier}» կամ ավելի բարձր մակարդակի բաժանորդագրություն։", "ru": "Для этой частоты требуется подписка уровня «{tier}» или выше.", "en": "This frequency requires a '{tier}' subscription or higher."}

# --- Q&A and Support ---
translations["qa_title"] = {"hy": "💬 Հաճախ տրվող հարցեր", "ru": "💬 Часто задаваемые вопросы", "en": "💬 Frequently Asked Questions"}
translations["support_btn"] = {"hy": "✉️ Գրել սպասարկման կենտրոն", "ru": "✉️ Написать в поддержку", "en": "✉️ Write to Support"}
translations["support_prompt"] = {"hy": "Խնդրում եմ մուտքագրել ձեր հաղորդագրությունը ադմինիստրատորի համար։ Նա կստանա այն և կկապվի ձեզ հետ հնարավորինս շուտ։", "ru": "Пожалуйста, введите ваше сообщение для администратора. Он получит его и свяжется с вами при первой возможности.", "en": "Please enter your message for the administrator. He will receive it and contact you as soon as possible."}
translations["support_message_sent"] = {"hy": "✅ Ձեր հաղորդագրությունն ուղարկված է։", "ru": "✅ Ваше сообщение отправлено.", "en": "✅ Your message has been sent."}

# --- Statistics ---
translations["stats_title"] = {"hy": "📊 Վիճակագրություն", "ru": "📊 Статистика", "en": "📊 Statistics"}
translations["stats_total_users"] = {"hy": "Ընդհանուր օգտատերեր", "ru": "Всего пользователей", "en": "Total Users"}
translations["stats_total_addresses"] = {"hy": "Ընդհանուր հասցեներ", "ru": "Всего адресов", "en": "Total Addresses"}
translations["stats_your_info"] = {"hy": "Ձեր տվյալները", "ru": "Ваши данные", "en": "Your Stats"}
translations["stats_notif_received"] = {"hy": "Ստացված ծանուցումներ", "ru": "Получено уведомлений", "en": "Notifications Received"}

# --- Notifications ---
translations["outage_notification_header"] = {"hy": "⚠️ *Ուշադրություն, անջատում*", "ru": "⚠️ *Внимание, отключение*", "en": "⚠️ *Attention, Outage*"}
translations["outage_water"] = {"hy": "💧 *Ջուր*", "ru": "💧 *Вода*", "en": "💧 *Water*"}
translations["outage_gas"] = {"hy": "🔥 *Գազ*", "ru": "🔥 *Газ*", "en": "🔥 *Gas*"}
translations["outage_electric"] = {"hy": "⚡ *Էլեկտրաէներգիա*", "ru": "⚡ *Электричество*", "en": "⚡ *Electricity*"}
translations["outage_period"] = {"hy": "Ժամանակահատված", "ru": "Период", "en": "Period"}
translations["outage_status"] = {"hy": "Կարգավիճակ", "ru": "Статус", "en": "Status"}
translations["outage_locations"] = {"hy": "Տեղանքներ", "ru": "Местоположения", "en": "Locations"}
translations["last_outage_recorded"] = {"hy": "Վերջին անգամ այս հասցեում անջատում գրանցվել է՝", "ru": "Последнее отключение по этому адресу было зафиксировано:", "en": "The last outage recorded at this address was:"}
translations["no_past_outages"] = {"hy": "Նախկինում այս հասցեում անջատումներ չեն գրանցվել։", "ru": "Ранее отключений по этому адресу не было зафиксировано.", "en": "No past outages have been recorded for this address."}

# --- Admin ---
translations["admin_unauthorized"] = {"hy": "Դուք իրավասու չեք այս հրամանը կատարելու։", "ru": "Вы не авторизованы для выполнения этой команды.", "en": "You are not authorized to execute this command."}
translations["maintenance_on_feedback"] = {"hy": "⚙️ Սպասարկման ռեժիմը միացված է։", "ru": "⚙️ Режим обслуживания включен.", "en": "⚙️ Maintenance mode is ON."}
translations["maintenance_off_feedback"] = {"hy": "✅ Սպասարկման ռեժիմը անջատված է։", "ru": "✅ Режим обслуживания выключен.", "en": "✅ Maintenance mode is OFF."}
translations["maintenance_user_notification"] = {"hy": "⚙️ Բոտը ժամանակավորապես սպասարկման մեջ է։ Խնդրում ենք փորձել մի փոքր ուշ։", "ru": "⚙️ Бот временно находится на техобслуживании. Пожалуйста, попробуйте позже.", "en": "⚙️ The bot is temporarily under maintenance. Please try again later."}
translations["support_message_from_user"] = {"hy": "✉️ *Նոր հաղորդագրություն սպասարկման կենտրոնին*\n\n*Ում կողմից*․ {user_mention}\n*Telegram-անուն*․ {user_username}\n*Օգտատիրոջ ID*․ `{user_id}`\n*Հաղորդագրություն*․ {message}", "ru": "✉️ *Новое сообщение в поддержку*\n\n*От кого*: {user_mention}\n*Telegram-ник*: {user_username}\n*ID пользователя*: `{user_id}`\n*Сообщение*:\n\n{message}", "en": "✉️ *New Support Message*\n\n*From whom*: {user_mention}\n*Telegram username*: {user_username}\n*User ID*: `{user_id}`\n*Message*:\n\n{message}"}
for i, (q_en, a_en, q_ru, a_ru, q_hy, a_hy) in enumerate([
    ("How do I add an address?", "Press the 'Add Address' button in the main menu and follow the instructions.", "Как добавить адрес?", "Нажмите кнопку 'Добавить адрес' в главном меню и следуйте инструкциям.", "Ինչպե՞ս ավելացնել հասցե։", "Սեղմեք «Ավելացնել հասցե» կոճակը գլխավոր մենյուում և հետևեք հրահանգներին։"),
    ("How do I remove an address?", "Go to 'My Addresses', select the address and press 'Remove'.", "Как удалить адрес?", "Откройте 'Мои адреса', выберите нужный адрес и нажмите 'Удалить'.", "Ինչպե՞ս հեռացնել հասցե։", "Բացեք «Իմ հասցեները», ընտրեք հասցեն և սեղմեք «Հեռացնել»։"),
    ("How can I change the notification frequency?", "Press 'Check Frequency' in the menu and choose the desired interval.", "Как изменить частоту уведомлений?", "Нажмите 'Частота проверок' в меню и выберите нужный интервал.", "Ինչպե՞ս փոխել ծանուցումների հաճախականությունը։", "Մենյուում սեղմեք «Ստուգման հաճախականություն» և ընտրեք ցանկալի միջակայքը։"),
    ("How do I view my saved addresses?", "Press 'My Addresses' in the menu.", "Как посмотреть мои адреса?", "Нажмите 'Мои адреса' в меню.", "Ինչպե՞ս տեսնել իմ հասցեները։", "Մենյուում սեղմեք «Իմ հասցեները»։"),
    ("How do I clear all addresses?", "Press 'Clear All Addresses' and confirm the action.", "Как удалить все адреса?", "Нажмите 'Очистить все адреса' և հաստատեք գործողությունը.", "Ինչպե՞ս մաքրել բոլոր հասցեները։", "Սեղմեք «Մաքրել բոլոր հասցեները» և հաստատեք գործողությունը։"),
    ("How do I change the bot language?", "Use the /language command or the menu option.", "Как сменить язык бота?", "Используйте команду /language или соответствующую кнопку в меню.", "Ինչպե՞ս փոխել բոտի լեզուն։", "Օգտագործեք /language հրամանը կամ ընտրեք համապատասխան կոճակը մենյուում։"),
    ("How do I contact support?", "Press 'Write to Support' in the Q&A section.", "Как связаться с поддержкой?", "Нажмите 'Написать в поддержку' в разделе Q&A.", "Ինչպե՞ս կապ հաստատել աջակցման հետ։", "Հարց ու պատասխան բաժնում սեղմեք «Գրել սպասարկման կենտրոն»։"),
    ("What do the different subscription tiers mean?", "Each tier offers different notification intervals and features.", "Что означают уровни подписки?", "Каждый уровень даёт разные интервалы уведомлений и функции.", "Ի՞նչ են նշանակում բաժանորդագրության մակարդակները։", "Յուրաքանչյուր մակարդակ առաջարկում է տարբեր հաճախականություններ և հնարավորություններ։"),
    ("How do I upgrade my subscription?", "Contact support for upgrade options.", "Как повысить уровень подписки?", "Свяжитесь с поддержкой для получения информации о повышении уровня.", "Ինչպե՞ս բարձրացնել բաժանորդագրության մակարդակը։", "Բարձրացման համար կապ հաստատեք աջակցման հետ։"),
    ("How do I know if there is an outage in my area?", "Add your address and the bot will notify you about outages.", "Как узнать об отключении в моём районе?", "Добавьте свой адрес, и бот будет уведомлять вас об отключениях.", "Ինչպե՞ս իմանալ իմ տարածքում անջատումների մասին։", "Ավելացրեք ձեր հասցեն, և բոտը կտեղեկացնի անջատումների մասին։"),
    ("Why am I not receiving notifications?", "Check your notification settings and make sure your address is correct.", "Почему я не получаю уведомления?", "Проверьте настройки уведомлений և հասցեի ճշգրտությունը։", "Ինչու՞ չեմ ստանում ծանուցումներ։", "Ստուգեք ծանուցումների կարգավորումները և հասցեի ճշգրտությունը։"),
    ("Can I use the bot for free?", "Yes, there is a free tier with basic features.", "Можно ли пользоваться ботом бесплатно?", "Да, есть бесплатный уровень с базовыми функциями.", "Կարո՞ղ եմ անվճար օգտվել բոտից։", "Այո, կա անվճար մակարդակ հիմնական հնարավորություններով։"),
    ("How do I enable silent mode?", "Use the silent mode option in the menu.", "Как включить тихий режим?", "Используйте опцию тихого режима в меню.", "Ինչպե՞ս միացնել լուռ ռեժիմը։", "Օգտագործեք լուռ ռեժիմի տարբերակը մենյուում։"),
    ("How do I disable silent mode?", "Go to silent mode settings and turn it off.", "Как отключить тихий режим?", "Откройте настройки тихого режима և отключите նրան։", "Ինչպե՞ս անջատել լուռ ռեժիմը։", "Բացեք լուռ ռեժիմի կարգավորումները և անջատեք այն։"),
    ("How do I update my address?", "Remove the old address and add a new one.", "Как обновить адрес?", "Удалите старый адрес и добавьте новый.", "Ինչպե՞ս թարմացնել հասցեն։", "Հեռացրեք հին հասցեն և ավելացրեք նոր հասցե։"),
    ("How do I set a default address?", "Currently, the first address is used as default.", "Как установить адрес по умолчанию?", "Сейчас առաջին добавленным адресом считается адрес по умолчанию.", "Ինչպե՞ս սահմանել հիմնական հասցե։", "Ներկայումս առաջին ավելացված հասցեն համարվում է հիմնական։"),
    ("Can I add multiple addresses?", "Yes, you can add several addresses.", "Можно ли добавить несколько адресов?", "Да, вы можете добавить несколько адресов.", "Կարո՞ղ եմ ավելացնել մի քանի հասցե։", "Այո, կարող եք ավելացնել մի քանի հասցե։"),
    ("How do I delete my account?", "Contact support to request account deletion.", "Как удалить свой аккаунт?", "Свяжитесь с поддержкой для удаления аккаунта.", "Ինչպե՞ս ջնջել իմ հաշիվը։", "Հաշիվը ջնջելու համար կապ հաստատեք աջակցման հետ։"),
    ("Is my data safe?", "We take data privacy seriously and do not share your information.", "Безопасны ли мои данные?", "Мы серьёзно относимся к безопасности данных и не передаём их третьим лицам.", "Իմ տվյալները անվտանգ ե՞ն։", "Մենք լրջորեն ենք վերաբերվում տվյալների գաղտնիությանը և չենք փոխանցում դրանք երրորդ անձանց։")
]):
    translations[f"qa_q{i+1}"] = {"en": q_en, "ru": q_ru, "hy": q_hy}
    translations[f"qa_a{i+1}"] = {"en": a_en, "ru": a_ru, "hy": a_hy}

translations["faq_prev_btn"] = {"hy": "⏮ Հետ", "ru": "⏮ Назад", "en": "⏮ Back"}
translations["faq_next_btn"] = {"hy": "⏭ Առաջ", "ru": "⏭ Вперёд", "en": "⏭ Next"}
translations["address_check_summary"] = {"hy": "✅ Ձեր հասցեն պահպանված է։ Եթե այս պահին անջատումներ չկան, դուք получите уведомления при их появлении։\n\nՀասցե՝ {address}",
                                         "ru": "✅ Ваш адрес сохранён. Если сейчас нет отключений, вы получите уведомление при их появлении.\n\nАдрес: {address}",
                                         "en": "✅ Your address has been saved. If there are no outages now, you will be notified when they appear.\n\nAddress: {address}"}

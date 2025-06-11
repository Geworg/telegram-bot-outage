-- Расширение для "нечеткого" (fuzzy) поиска по схожести строк (триграммы).
-- Помогает находить адреса, даже если пользователь ввел их с опечатками.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-----------------------------------------
-- 1. ТАБЛИЦЫ ДЛЯ ГЕОГРАФИЧЕСКИХ ДАННЫХ --
-----------------------------------------

-- Общая таблица для всех географических объектов (область, город, район, улица).
-- Использует иерархическую структуру "adjacency list" (parent_id).
CREATE TABLE place (
  id SERIAL PRIMARY KEY,
  parent_id INTEGER REFERENCES place(id) ON DELETE CASCADE, -- Ссылка на родительский объект (e.g., для улицы parent_id будет id города). NULL для верхнего уровня (области).
  type VARCHAR(25) NOT NULL, -- Тип объекта: 'region', 'locality' (город/село), 'district' (район в городе), 'street', 'area' (участок/квартал).
  name_hy TEXT NOT NULL,
  name_ru TEXT NOT NULL,
  name_en TEXT NOT NULL
);

-- Индексы для очень быстрого текстового поиска по названиям на любом языке.
CREATE INDEX idx_place_name_hy_trgm ON place USING GIN (name_hy gin_trgm_ops);
CREATE INDEX idx_place_name_ru_trgm ON place USING GIN (name_ru gin_trgm_ops);
CREATE INDEX idx_place_name_en_trgm ON place USING GIN (name_en gin_trgm_ops);
CREATE INDEX idx_place_parent_id ON place (parent_id); -- Индекс для быстрого поиска "детей" объекта.

-- Таблица для конкретных зданий/домов.
CREATE TABLE address (
  id SERIAL PRIMARY KEY,
  place_id INTEGER NOT NULL REFERENCES place(id) ON DELETE CASCADE, -- Ссылка на улицу, район или др. объект из таблицы place.
  house_number TEXT, -- Номер дома, может быть сложным (e.g., "15/1", "28 строение 3"). Может быть NULL, если адрес - это просто улица.
  postal_code VARCHAR(10), -- Почтовый индекс (необязательно).
  raw_address TEXT, -- Исходный текст адреса от пользователя, если его не удалось полностью нормализовать.
  -- Уникальность адреса обеспечивается комбинацией улицы/места и номера дома.
  UNIQUE (place_id, house_number)
);

CREATE INDEX idx_address_place_id ON address (place_id);

--------------------------------
-- 2. ТАБЛИЦЫ ДЛЯ ЛОГИКИ БОТА --
--------------------------------

-- Таблица пользователей бота. Замена для user_settings.json.
CREATE TABLE bot_user (
  user_id BIGINT PRIMARY KEY, -- Telegram User ID
  username VARCHAR(255),
  first_name TEXT,
  last_name TEXT,
  language_code VARCHAR(5) DEFAULT 'hy', -- Язык интерфейса бота
  subscription_tier VARCHAR(20) DEFAULT 'Free',
  frequency_sec INTEGER DEFAULT 21600, -- Частота проверки в секундах (6 часов по умолчанию)
  sound_enabled BOOLEAN DEFAULT TRUE,
  silent_mode_enabled BOOLEAN DEFAULT FALSE,
  silent_start_time TIME DEFAULT '23:00',
  silent_end_time TIME DEFAULT '07:00',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица для отслеживаемых пользователями адресов. Замена для addresses.json.
CREATE TABLE user_tracked_address (
  id SERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES bot_user(user_id) ON DELETE CASCADE,
  -- Вместо хранения place_id и house_number, ссылаемся напрямую на полную запись в 'address'
  address_id INTEGER NOT NULL REFERENCES address(id) ON DELETE CASCADE,
  -- Уникальная связь, чтобы пользователь не мог добавить один и тот же адрес дважды.
  UNIQUE (user_id, address_id)
);

------------------------------------
-- 3. ТАБЛИЦЫ ДЛЯ ДАННЫХ ОТКЛЮЧЕНИЙ --
------------------------------------

-- Таблица для хранения каждого спарсенного объявления об отключении.
CREATE TABLE announcement (
  id SERIAL PRIMARY KEY,
  source_type VARCHAR(20) NOT NULL, -- 'water', 'gas', 'electric'
  shutdown_type VARCHAR(20) NOT NULL, -- 'planned', 'emergency'
  publication_date TIMESTAMPTZ, -- Дата публикации на сайте
  start_datetime TIMESTAMPTZ NOT NULL,
  end_datetime TIMESTAMPTZ NOT NULL,
  reason TEXT,
  source_url VARCHAR(1024),
  original_text TEXT, -- Полный исходный текст объявления для анализа
  created_at TIMESTAMPTZ DEFAULT NOW(),
  -- Хэш для быстрой проверки на уникальность объявления
  content_hash VARCHAR(64) UNIQUE
);

-- Связующая таблица: какие места (place) затрагивает какое объявление (announcement).
-- Позволяет гибко указывать отключения (на всю область, на город, на несколько улиц).
CREATE TABLE announcement_place_link (
  announcement_id INTEGER NOT NULL REFERENCES announcement(id) ON DELETE CASCADE,
  place_id INTEGER NOT NULL REFERENCES place(id) ON DELETE CASCADE,
  PRIMARY KEY (announcement_id, place_id)
);

-- Таблица для отслеживания, какие пользователи уже были уведомлены о каких объявлениях.
-- Замена для notified.json.
CREATE TABLE user_notification_log (
  user_id BIGINT NOT NULL REFERENCES bot_user(user_id) ON DELETE CASCADE,
  announcement_id INTEGER NOT NULL REFERENCES announcement(id) ON DELETE CASCADE,
  sent_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_id, announcement_id)
);


/***********************************************************************************/
/****************************** НАПОЛНЕНИЕ ДАННЫМИ (ПРИМЕРЫ) ******************************/
/***********************************************************************************/

-- Уровень 1: Области (parent_id IS NULL)
INSERT INTO place (id, parent_id, type, name_hy, name_ru, name_en) VALUES
  (1, NULL, 'region', 'Երևան', 'Ереван', 'Yerevan'),
  (2, NULL, 'region', 'Արագածոտն', 'Арагацотн', 'Aragatsotn'),
  (3, NULL, 'region', 'Արարատ', 'Арарат', 'Ararat'),
  (4, NULL, 'region', 'Արմավիր', 'Армавир', 'Armavir'),
  (5, NULL, 'region', 'Գեղարքունիք', 'Гехаркуник', 'Gegharkunik'),
  (6, NULL, 'region', 'Լոռի', 'Лори', 'Lori'),
  (7, NULL, 'region', 'Կոտայք', 'Котайк', 'Kotayk'),
  (8, NULL, 'region', 'Շիրակ', 'Ширак', 'Shirak'),
  (9, NULL, 'region', 'Սյունիք', 'Сюник', 'Syunik'),
  (10, NULL, 'region', 'Վայոց Ձոր', 'Вайоц Дзор', 'Vayots Dzor'),
  (11, NULL, 'region', 'Տավուշ', 'Тавуш', 'Tavush');

-- Уровень 2: Города в других областях
INSERT INTO place (id, parent_id, type, name_hy, name_ru, name_en) VALUES
  (200, 8, 'locality', 'Գյումրի', 'Гюмри', 'Gyumri'), -- Гюмри в Шираке (id=8)
  (201, 6, 'locality', 'Վանաձոր', 'Ванадзор', 'Vanadzor'), -- Ванадзор в Лори (id=6)
  (202, 7, 'locality', 'Աբովյան', 'Абовян', 'Abovyan'); -- Абовян в Котайке (id=7)

-- Уровень 3: Улицы. Привязываем к родительским объектам (районам или городам)
-- Улицы в Ереване, район Кентрон (id=) 
INSERT INTO place (id, parent_id, type, name_hy, name_ru, name_en) VALUES 
  (1001, 'street', 'Աբովյան փողոց', 'улица Абовяна', 'Abovyan Street'), 
  (1002, 'street', 'Մաշտոցի պողոտա', 'проспект Маштоца', 'Mashtots Avenue'), 
  (1003, 'street', 'Սայաթ-Նովայի պողոտա', 'проспект Саят-Новы', 'Sayat-Nova Avenue'), 
  (1004, 'street', 'Հերացու փողոց', 'улица Ерецу', 'Heratsi Street'), 
  (1005, 'street', 'Սունդուկյանի փողոց', 'улица Сундукяна', 'Sundukyan Street'),
  (1006, 'street', 'Հանրապետության փողոց', 'улица Республики', 'Republic Square'),
  (1007, 'street', 'Նալբանդյան փողոց', 'улица Налбандяна', 'Nalbandyan Street'),
  (1008, 'street', 'Արամի փողոց', 'улица Арама', 'Aram Street'),
  (1009, 'street', 'Տպագրիչների փողոց', 'улица Тпагричнери', 'Tpagrichner Street'),
  (1010, 'street', 'Եզնիկ Կողբացու փողոց', 'улица Езника Кохбаци', 'Yeznik Koghbatsi Street'),
  (1011, 'street', 'Կոմիտասի պողոտա', 'проспект Комитаса', 'Komitas Avenue'),
  (1012, 'street', 'Վարդանանց փողոց', 'улица Вардананц', 'Vardanants Street'),
  (1013, 'street', 'Խորեն Աբրահամյանի փողոց', 'улица Хорена Абрамяна', 'Khoren Abrahamyan Street'),
  (1014, 'street', 'Անրի Վեռնոյի փողոց', 'улица Анри Вернёя', 'Anri Verno Street'),
  (1015, 'street', 'Իսահակյան փողոց', 'улица Исаакяна', 'Isahakyan Street'),
  (1016, 'street', 'Ամիրյան փողոց', 'улица Амиряна', 'Amiryan Street'),
  (1017, 'street', 'Պուշկինի փողոց', 'улица Пушкина', 'Pushkin Street'),
  (1018, 'street', 'Կարեն Դեմիրճյանի փողոց', 'улица Карена Демирчяна', 'Karen Demirchyan Street'),
  (1019, 'street', 'Արշակունյաց պողոտա', 'проспект Аршакуняц', 'Arshakunyats Avenue'),
  (1020, 'street', 'Տիգրան Մեծի փողոց', 'улица Тиграна Великого', 'Tigran Mets Street'),
  (1021, 'street', 'Վաղարշակի փողոց', 'улица Вагаршака', 'Vagharshak Street'),
  (1022, 'street', 'Սուրբ Գրիգոր Լուսավորչի փողոց', 'улица Сурб Григора Просветителя', 'Surb Grigor Lusavorich Street'),
  (1023, 'street', 'Մովսեսի Խորենացու փողոց', 'улица Мовсеса Хоренаци', 'Movses Khorenatsi Street'),
  (1024, 'street', 'Մելիք-Ադամյանի փողոց', 'улица Мелик-Адамяна', 'Melik-Adamyan Street'),
  (1025, 'street', 'Ծիծեռնակապերդի փողոց', 'улица Цицицирнакаберда', 'Tsitsernakaberd Street'),
  (1026, 'street', 'Կյուրեղյան փողոց', 'улица Кюрегяна', 'Kyureghyan Street'),
  (1027, 'street', 'Ֆրիկի փողոց', 'улица Фрика', 'Frik Street'),
  (1028, 'street', 'Վերազիվարի փողոց', 'улица Веразивара', 'Verazivari Street'),
  (1029, 'street', 'Կապանցու փողոց', 'улица Капанцу', 'Kapantsu Street'),
  (1030, 'street', 'Արամ Խաչատրյանի փողոց', 'улица Арама Хачатряна', 'Aram Khachaturyan Street'),
  (1031, 'street', 'Եկմալյանի փողոց', 'улица Екмаляна', 'Ekmaylyan Street'),
  (1032, 'street', 'Հրանտ Մատևյանի փողոց', 'улица Гранта Матевяна', 'Hrant Matevyan Street'),
  (1033, 'street', 'Պետրոս Ադամյանի փողոց', 'улица Петроса Адамяна', 'Petros Adamyan Street'),
  (1034, 'street', 'Արցախի պողոտա', 'проспект Арцаха', 'Artsakh Avenue'),
  (1035, 'street', 'Ծովակալ Իսակովի պողոտա', 'проспект адмирала Исакова', 'Admiral Isakov Avenue'),
  (1036, 'street', 'Ալեքսանդր Մյասնիկյանի պողոտա', 'проспект Александра Мясникяна', 'Alexander Myasnikyan Avenue'),
  (1037, 'street', 'Ալեքսանդր Թամանյանի փողոց', 'улица Александра Таманяна', 'Alexander Tamanian Street'),
  (1038, 'street', 'Հաղթանակի պողոտա', 'проспект Победы', 'Victory Avenue'),
  (1039, 'street', 'Ավետիք Իսահակյանի փողոց', 'улица Аветика Исахакяна', 'Avetik Isahakyan Street'),
  (1040, 'street', 'Րաֆֆու փողոց', 'улица Раффи', 'Raffi Street'),
  (1041, 'street', 'Սասունցի Դավթի փողոց', 'улица Сасунского Давида', 'Sasuntsi Davit Street'),
  (1042, 'street', 'Գարեգին Նժդեհի փողոց', 'улица Гарегина Нжде', 'Garegin Nzhdeh Street'),
  (1043, 'street', 'Արամ Մանուկյանի փողոց', 'улица Арама Манукяна', 'Aram Manukyan Street'),
  (1044, 'street', 'Ալեքսանդր Սպենդիարյանի փողոց', 'улица Александра Спендиаряна', 'Alexander Spendiarian Street'),
  (1045, 'street', 'Հովհաննես Թումանյանի փողոց', 'улица Ованеса Туманяна', 'Hovhannes Tumanyan Street'),
  (1046, 'street', 'Սերգեյ Փարաջանովի փողոց', 'улица Сергея Параджанова', 'Sergei Parajanov Street'),
  (1047, 'street', 'Գուսան Շերամ փողոց', 'улица Гусана Шерама', 'Gusan Sheram Street'),
  (1048, 'street', 'Մարտիրոս Սարյանի փողոց', 'улица Мартироса Сарьяна', 'Martiros Saryan Street'),
  (1036, 'street', 'Սարյան փողոց', 'улица Сарьяна', 'Saryan Street'),
  (1037, 'street', 'Փափազյան փողոց', 'улица Пападзяна', 'Papazyan Street'),
  (1038, 'street', 'Կորյունի փողոց', 'улица Корюна', 'Koryun Street'),
  (1039, 'street', 'Էրեբունու փողոց', 'улица Эребуни', 'Erebuni Street'),
  (1040, 'street', 'Մոսկովյան փողոց', 'улица Московян', 'Moskovyan Street'),
  (1041, 'street', 'Ստեփան Զորյանի փողոց', 'улица Степана Зоряна', 'Stepan Zoryan Street'),
  (1042, 'street', 'Մարշալ Բաղրամյանի պողոտա', 'проспект Маршала Баграмяна', 'Marshal Baghramyan Avenue'),
  (1043, 'street', 'Վազգեն Սարգսյանի փողոց', 'улица Вазгена Саргсяна', 'Vazgen Sargsyan Street'),
  (1044, 'street', 'Ղազար Փարպեցու փողոց', 'улица Казара Парпеци', 'Ghazar Parpetsi Street'),
  (1045, 'street', 'Հին երևանցու փողոց', 'улица Ин Ереванцу', 'Hin Yerevantsu Street'),
  (1046, 'street', 'Պուշկինի փողոց', 'улица Пушкина', 'Pushkin Street'),
  (1047, 'street', 'Հակոբ Պարոնյանի փողոց', 'улица Акопа Пароняна', 'Hakob Paronian Street'),
  (1048, 'street', 'Ալեք Մանուկյանի փողոց', 'улица Алека Манукяна', 'Alek Manukyan Street'),
  (1049, 'street', 'Արշակ Ալպոյաճյանի փողոց', 'улица Аршака Алпоячяна', 'Arshak Alpoyachyan Street'),
  (1050, 'street', 'Միհրան Տոումանյանի փողոց', 'улица Михрана Туманяна', 'Mihran Tumanyan Street'),
  (1051, 'street', 'Գևորգ Էմինի փողոց', 'улица Геворга Эмина', 'Gevorg Emin Street'),
  (1052, 'street', 'Եղիշե Չարենցի փողոց', 'улица Егише Чаренца', 'Yeghishe Charents Street'),
  (1053, 'street', 'Մալաթիայի փողոց', 'улица Малатия', 'Malatia Street'),
  (1054, 'street', 'Պերճի փողոց', 'улица Перча', 'Perch Street'),
  (1055, 'street', 'Արմեն Տիգրանյանի փողոց', 'улица Армена Тиграняна', 'Armen Tigranian Street'),
  (1056, 'street', 'Վահան Թերյանի փողոց', 'улица Вагана Терьяна', 'Vahan Terian Street'),
  (1057, 'street', 'Նիկող Աղբալյանի փողոց', 'улица Никола Агбаляна', 'Nikol Aghbalyan Street'),
  (1058, 'street', 'Հովհաննես Շիրազի փողոց', 'улица Ованеса Шираза', 'Hovhannes Shiraz Street'),
  (1059, 'street', 'Փավստոս Բուզանդի փողոց', 'улица Фавстоса Бюзанда', 'Pavstos Buzand Street'),
  (1060, 'street', 'Մելքումովի փողոց', 'улица Мелкумова', 'Melkumov Street'),
  (1061, 'street', 'Անդրանիկ Զորավարի փողոց', 'улица Андраника Зоравара', 'Andranik Zoravar Street'),
  (1062, 'street', 'Միքայել Մազմանյանի փողոց', 'улица  Микаэл Мазманяна', 'Mikayel Mazmanyan Street'),
  (1063, 'street', 'Հյուսիս—Հարավ ավտոմայրուղի', 'Шоссе Север-Юг', 'North-South Highway'),
  (1064, 'street', 'Մովսես Սիլիկյան նոր խճուղի', 'Новое шоссе Мовсеса Силикяна', 'Movses Silikyan New Highway'),
  (1065, 'street', 'Տոլստոյի փողոց', 'улица Толстого', 'Tolstoy Street'),
  (1066, 'street', 'Չեխովի փողոց', 'улица Чехова', 'Chekhov Street');

-- Улицы в Гюмри (id=200)
INSERT INTO place (id, parent_id, type, name_hy, name_ru, name_en) VALUES
  (2001, 200, 'street', 'Ռուսթավելի փողոց', 'улица Руставели', 'Rustaveli Street'),
  (2002, 200, 'street', 'Սայաթ-Նովայի փողոց', 'улица Саят-Новы', 'Sayat-Nova Street');

-- Уровень 4: Конкретные дома (таблица address). Привязываем к улицам.
-- Дома на ул. Абовяна в Ереване (id=1001)
INSERT INTO address (place_id, house_number, postal_code) VALUES
  (1001, '1/1', '0001'),
  (1001, '2', '0001'),
  (1001, '3', '0001');

-- Дома на ул. Руставели в Гюмри (id=2001)
INSERT INTO address (place_id, house_number, postal_code) VALUES
  (2001, '10', '3104'),
  (2001, '12', '3104');

-- Пример добавления улицы в городе Ванадзор (id=201)
INSERT INTO place (id, parent_id, type, name_hy, name_ru, name_en) VALUES (2011, 201, 'street', 'Տիգրան Մեծի պողոտա', 'проспект Тиграна Меца', 'Tigran Mets Avenue');
INSERT INTO address (place_id, house_number) VALUES (2011, '25');

-- ПЕРЕЗАПУСК СЧЕТЧИКОВ ID, чтобы следующие INSERT'ы не конфликтовали с заданными вручную
-- Запускать после ручного наполнения, чтобы автоматическая нумерация продолжилась с максимального ID + 1
SELECT setval('place_id_seq', (SELECT MAX(id) FROM place));
SELECT setval('address_id_seq', (SELECT MAX(id) FROM address));
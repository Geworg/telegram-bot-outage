import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import json
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
# URL-адреса сайтов для скрейпинга
SOURCES = {
    'Veolia Jur': 'https://interactive.vjur.am/',
    'Gazprom vtarayin': 'https://armenia-am.gazprom.com/notice/announcement/vtar/',
    'Gazprom planayin': 'https://armenia-am.gazprom.com/notice/announcement/plan/',
    'HEC': 'https://www.ena.am/Info.aspx?id=5&lang=1'
}

# Имя файла локальной базы данных для хранения и обработки данных
DB_FILE = 'outages.db'
# Имя конечного SQL-файла для вашего проекта
OUTPUT_SQL_FILE = 'outages_dump.sql'

# --- СЛОВАРИ И ВСПОМОГАТЕЛЬНЫЕ ДАННЫЕ ---

# Словарь для транслитерации с армянского
TRANSLIT_MAP = {
    'ա': 'a', 'բ': 'b', 'գ': 'g', 'դ': 'd', 'ե': 'e', 'զ': 'z', 'է': 'e', 'ը': 'y',
    'թ': 't', 'ժ': 'zh', 'ի': 'i', 'լ': 'l', 'խ': 'x', 'ծ': 'ts', 'կ': 'k', 'հ': 'h',
    'ձ': 'dz', 'ղ': 'gh', 'ճ': 'ch', 'մ': 'm', 'յ': 'y', 'ն': 'n', 'շ': 'sh', 'ո': 'o',
    'չ': 'ch', 'պ': 'p', 'ջ': 'j', 'ռ': 'r', 'ս': 's', 'վ': 'v', 'տ': 't', 'ր': 'r',
    'ց': 'c', 'ու': 'u', 'փ': 'ph', 'ք': 'q', 'օ': 'o', 'ֆ': 'f', 'և': 'ev',
    'Ա': 'A', 'Բ': 'B', 'Գ': 'G', 'Դ': 'D', 'Ե': 'E', 'Զ': 'Z', 'Է': 'E', 'Ը': 'Y',
    'Թ': 'T', 'Ժ': 'Zh', 'Ի': 'I', 'Լ': 'L', 'Խ': 'X', 'Ծ': 'Ts', 'Կ': 'K', 'Հ': 'H',
    'Ձ': 'Dz', 'Ղ': 'Gh', 'Ճ': 'Ch', 'Մ': 'M', 'Յ': 'Y', 'Ն': 'N', 'Շ': 'Sh', 'Ո': 'O',
    'Չ': 'Ch', 'Պ': 'P', 'Ջ': 'J', 'Ռ': 'R', 'Ս': 'S', 'Վ': 'V', 'Տ': 'T', 'Ր': 'R',
    'Ց': 'C', 'ՈՒ': 'U', 'Ու': 'U', 'Փ': 'Ph', 'Ք': 'Q', 'Օ': 'O', 'Ֆ': 'F',  'ԵՎ': 'Ev', 'Եվ': 'Ev',
    ' ': ' ', ',': ',', '-': '-', '.': ':', '–': '-', '—': '-', '(': '(', ')': ')', '/': '/',
    ':': '․', ';': ';', '՞': '?', '«': '"', '»': '"', '՛': '', '՝': '', '…': '...',
}

REGIONS_AM = ["Երևան", "Արագածոտն", "Արարատ", "Արմավիր", "Գեղարքունիք", "Լոռի", "Կոտայք", "Շիրակ", "Սյունիք", "Վայոց ձոր", "Տավուշ"]
YEREVAN_DISTRICTS_AM = ["Աջափնյակ", "Արաբկիր", "Ավան", "Դավթաշեն", "Էրեբունի", "Կենտրոն", "Մալաթիա-Սեբաստիա", "Նոր Նորք", "Նորք-Մարաշ", "Նուբարաշեն", "Շենգավիթ"]

# --- ОСНОВНЫЕ ФУНКЦИИ ---
def transliterate(text):
    return "".join(TRANSLIT_MAP.get(char, char) for char in text)

def setup_database():
    """Создает таблицы в базе данных SQLite, если они еще не существуют."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Создаем основную таблицу для хранения информации об отключениях
    # Используем JSON для хранения диапазонов домов для гибкости
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS outages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        region_am TEXT NOT NULL,
        community_am TEXT NOT NULL,
        street_am TEXT NOT NULL,
        region_translit TEXT NOT NULL,
        community_translit TEXT NOT NULL,
        street_translit TEXT NOT NULL,
        building_ranges_json TEXT, -- JSON-массив диапазонов, e.g., "[[1, 20], [45, 70]]" or '["all"]'
        source_url TEXT,
        last_updated TEXT NOT NULL,
        UNIQUE(region_translit, community_translit, street_translit)
    )
    ''')
    conn.commit()
    conn.close()
    print("База данных готова.")

def get_html(url):
    """Получает HTML-код страницы с обработкой ошибок."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Ошибка при загрузке {url}: {e}")
        return None

def parse_announcement(text, url):
    text = text.replace('–', '-').replace('—', '-')
    region_found = "N/A"
    community_found = "N/A"

    for region in REGIONS_AM:
        if region in text:
            region_found = region
            break

    if region_found == "Երևան":
        community_found = "Yerevan"
        for district in YEREVAN_DISTRICTS_AM:
            if re.search(f"{district}(\\w*)", text):
                community_found = district
                break

    streets_match = re.search(r'([\w\s\-,]+)\s+(փողոց|պողոտա|շենք)', text)
    if not streets_match:
        return []

    streets_block = streets_match.group(1)
    streets_raw = [s.strip() for s in streets_block.split(',')]

    results = []
    for street_raw in streets_raw:
        if not street_raw:
            continue
        street_name = street_raw
        ranges = ["all"]
        numbers_match = re.findall(r'(\d+-\d+|\d+)', street_raw)
        if numbers_match:
            street_name = re.sub(r'[\d\s,-]+$', '', street_name).strip()
            processed_ranges = []
            for num in numbers_match:
                if '-' in num:
                    start, end = map(int, num.split('-'))
                    processed_ranges.append(sorted([start, end]))
                else:
                    processed_ranges.append([int(num), int(num)])
            ranges = processed_ranges
        street_name = street_name.replace("փող.", "").replace("փողոց", "").strip()
        if street_name:
            results.append({
                "region_am": region_found,
                "community_am": community_found,
                "street_am": street_name,
                "ranges": ranges,
                "source_url": url
            })
    return results

def update_database(parsed_data):
    """Обновляет базу данных на основе новых данных, объединяя диапазоны домов."""
    if not parsed_data:
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    for item in parsed_data:
        # Транслитерация для уникального ключа и хранения
        region_translit = transliterate(item['region_am'])
        community_translit = transliterate(item['community_am'])
        street_translit = transliterate(item['street_am'])
        
        # Проверяем, существует ли уже такая улица
        cursor.execute('''
        SELECT building_ranges_json FROM outages 
        WHERE region_translit = ? AND community_translit = ? AND street_translit = ?
        ''', (region_translit, community_translit, street_translit))
        
        result = cursor.fetchone()
        
        now = datetime.now().isoformat()

        if result:
            # --- Логика объединения данных ---
            existing_ranges_json = result[0]
            existing_ranges = json.loads(existing_ranges_json)
            
            new_ranges = item['ranges']

            # Если где-то указано "все дома", то итоговый результат - "все дома"
            if "all" in existing_ranges or "all" in new_ranges:
                final_ranges = ["all"]
            else:
                # Объединяем списки диапазонов и убираем дубликаты
                combined = existing_ranges + new_ranges
                # Сортировка и слияние пересекающихся диапазонов (сложная логика, здесь упрощено)
                unique_ranges = [list(x) for x in set(tuple(x) for x in combined)]
                final_ranges = sorted(unique_ranges)

            final_ranges_json = json.dumps(final_ranges)
            
            cursor.execute('''
            UPDATE outages 
            SET building_ranges_json = ?, source_url = ?, last_updated = ?
            WHERE region_translit = ? AND community_translit = ? AND street_translit = ?
            ''', (final_ranges_json, item['source_url'], now, region_translit, community_translit, street_translit))
            print(f"Обновлено: {item['street_am']}, новые диапазоны: {final_ranges_json}")

        else:
            # --- Логика вставки новой записи ---
            new_ranges_json = json.dumps(item['ranges'])
            cursor.execute('''
            INSERT INTO outages (
                region_am, community_am, street_am, 
                region_translit, community_translit, street_translit, 
                building_ranges_json, source_url, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['region_am'], item['community_am'], item['street_am'],
                region_translit, community_translit, street_translit,
                new_ranges_json, item['source_url'], now
            ))
            print(f"Добавлено: {item['street_am']}")
            
    conn.commit()
    conn.close()

#list-post > div.items

def scrape_site(name, url):
    print(f"\n--- Анализ сайта: {name} ---")
    html = get_html(url)
    if not html:
        return

    soup = BeautifulSoup(html, 'html.parser')
    announcements = []

    if name == 'Veolia Jur':
        news_items = soup.select('#list-post > div.items > div.panel-group > div.panel')
        for item in news_items:
            title_elem = item.select_one('.panel-heading a')
            title = title_elem.get_text(strip=True) if title_elem else ''
            body_elem = item.select_one('.panel-body')
            text = body_elem.get_text(separator="\n", strip=True) if body_elem else ''
            full_text = f"{title}\n{text}"
            announcements.append({'text': full_text, 'url': url})

    elif name.startswith('Gazprom'):
        # Для Gazprom используем общий селектор для обоих типов объявлений
        items = soup.select('.announcements-list .item')
        for item in items:
            announcements.append({'text': item.get_text(), 'url': url})

    elif name == 'HEC':
        planned_block = soup.select_one('#ctl00_ContentPlaceHolder1_attenbody')
        if planned_block:
            text = planned_block.get_text(separator="\n", strip=True)
            announcements.append({'text': text, 'url': url})

        rows = soup.select('#ctl00_ContentPlaceHolder1_vtarayin tbody tr')
        for row in rows:
            date_cell = row.select_one('td.termination-date span')
            addr_cell = row.select('td')[1].get_text(strip=True) if len(row.select('td')) > 1 else ''
            if date_cell:
                date_text = date_cell.get_text(strip=True)
                full_text = f"{date_text}\n{addr_cell}"
                announcements.append({'text': full_text, 'url': url})

    print(f"Найдено {len(announcements)} объявлений.")
    for announcement in announcements:
        parsed_data = parse_announcement(announcement['text'], announcement['url'])
        update_database(parsed_data)

def generate_sql_dump():
    """Создает финальный .sql файл из данных в локальной базе SQLite."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # Позволяет обращаться к колонкам по имени
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM outages")
    rows = cursor.fetchall()
    
    with open(OUTPUT_SQL_FILE, 'w', encoding='utf-8') as f:
        # Записываем команду для создания таблицы
        f.write('''
-- Дамп данных об отключениях, сгенерировано {now}
DROP TABLE IF EXISTS `outages`;
CREATE TABLE `outages` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT,
    `region_am` TEXT NOT NULL,
    `community_am` TEXT NOT NULL,
    `street_am` TEXT NOT NULL,
    `region_translit` TEXT NOT NULL,
    `community_translit` TEXT NOT NULL,
    `street_translit` TEXT NOT NULL,
    `building_ranges_json` TEXT,
    `source_url` TEXT,
    `last_updated` TEXT NOT NULL
);
'''.format(now=datetime.now()))
        
        if rows:
            f.write("\n-- Данные\n")
            f.write("INSERT INTO `outages` VALUES\n")
            
            values = []
            for row in rows:
                # Экранируем одинарные кавычки в текстовых полях
                values.append("({id}, '{region_am}', '{community_am}', '{street_am}', '{region_translit}', '{community_translit}', '{street_translit}', '{building_ranges_json}', '{source_url}', '{last_updated}')".format(
                    id=row['id'],
                    region_am=row['region_am'].replace("'", "''"),
                    community_am=row['community_am'].replace("'", "''"),
                    street_am=row['street_am'].replace("'", "''"),
                    region_translit=row['region_translit'].replace("'", "''"),
                    community_translit=row['community_translit'].replace("'", "''"),
                    street_translit=row['street_translit'].replace("'", "''"),
                    building_ranges_json=row['building_ranges_json'].replace("'", "''"),
                    source_url=row['source_url'],
                    last_updated=row['last_updated']
                ))

            f.write(",\n".join(values) + ";\n")

    conn.close()
    print(f"\nФайл {OUTPUT_SQL_FILE} успешно создан.")

# --- ТОЧКА ВХОДА В СКРИПТ ---
if __name__ == '__main__':
    setup_database()
    for name, url in SOURCES.items():
        scrape_site(name, url)
    generate_sql_dump()
    print("\nРабота завершена.")
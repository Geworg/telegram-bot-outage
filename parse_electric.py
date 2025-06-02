# parse_electric.py
import asyncio
import httpx
from bs4 import BeautifulSoup
import json
import re # Добавлен импорт re
from ai_engine import ask_model
from logger import log_error, log_info, log_warning

# URL для Электросетей Армении
ELECTRIC_URL = "https://www.ena.am/Info.aspx?id=5&lang=1" # lang=1 это армянский, lang=2 русский, lang=3 английский

async def fetch_electric_announcements_async() -> list[str]:
    log_info(f"Fetching electric announcements from {ELECTRIC_URL} (async)...")
    raw_texts = []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # lang=1 (армянский) обычно содержит самую оперативную информацию
            response = await client.get(ELECTRIC_URL) 
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            # Селектор для ENA, может потребовать адаптации.
            # Пример: <div id="divNotices"> <div class="cat_article"> <p> - текст объявления
            # Или может быть структура с panel-group / panel-body как у других.
            # Исходя из предыдущей заглушки: soup.find('div', class_='items')
            # и panel.find('div', class_='panel-body')
            
            # Предположим, что структура похожа на другие сайты с "items" и "panel-group"
            # items_container = soup.find('div', class_='items') # Это может быть специфично для Газпрома/Воды
            # Если на ENA другая структура, этот селектор нужно изменить.
            # Например, если объявления в <div class="news_item_container">
            announcement_items = soup.select('div.items div.panel-group div.panel-body') # Заглушечный селектор
            if not announcement_items:
                # Попробуем найти более общие контейнеры текста, если специфичный не найден
                # announcement_items = soup.select('div.news-list-item p') # или другой подходящий селектор для ENA
                log_info(f"No electric announcements found with 'div.items div.panel-group div.panel-body' on {ELECTRIC_URL}. Found {len(announcement_items)} items.")
            
            for item in announcement_items:
                text_content = item.get_text(separator="\n", strip=True)
                if text_content:
                    raw_texts.append(text_content)
            
        log_info(f"Fetched {len(raw_texts)} raw electric announcements from {ELECTRIC_URL}.")
        return raw_texts
    except httpx.HTTPStatusError as e:
        log_error(f"HTTP error {e.response.status_code} while fetching electric data from {ELECTRIC_URL}: {e.request.url}")
    except httpx.RequestError as e:
        log_error(f"Network error fetching electric data from {ELECTRIC_URL}: {e}")
    except Exception as e:
        log_error(f"Generic error parsing electric HTML from {ELECTRIC_URL}: {e}", exc=e)
    return []


async def extract_electric_info_async(text: str) -> dict:
    log_info_text_preview = text[:70].replace('\n', ' ')
    log_info(f"Extracting electric info for text (first 70 chars): {log_info_text_preview}...")
    # Промпт для электричества
    prompt = f"""
Проанализируй следующий текст объявления об отключении ЭЛЕКТРИЧЕСТВА и извлеки структурированную информацию.
Текст объявления:
---
{text}
---

Извлеки данные строго в формате JSON со следующими полями:
- "published": дата публикации объявления (string, "дд.мм.гггг" или null, если нет).
- "status": тип отключения (string, "Плановое" или "Аварийное"; если неясно, определи по контексту или ставь "Плановое").
- "start_date": дата начала отключения (string, "дд.мм.гггг").
- "start_time": время начала отключения (string, "чч:мм").
- "end_date": дата окончания отключения (string, "дд.мм.гггг").
- "end_time": время окончания отключения (string, "чч:мм").
- "regions": список регионов/административных районов/городов (list of strings, например, ["Ереван, Кентрон", "г. Гюмри"] или null).
- "streets": список затронутых улиц с номерами домов, если указаны (list of strings, например, ["ул. Амиряна 1-5, здания", "с. Паракар полностью"] или null).
- "description": краткое описание причины или дополнительная информация (string или null).

Правила:
1. Если поле отсутствует в тексте, значение должно быть null.
2. Даты должны быть в формате "дд.мм.гггг". Если год не указан, предположи текущий год ({datetime.now().year}).
3. Время должно быть в формате "чч:мм" (24-часовой). ENA часто использует формат "10:00-18:00". В этом случае start_time="10:00", end_time="18:00".
4. Если указан диапазон дат (например, "с 21 по 23 мая"), "start_date" - первая дата, "end_date" - вторая.
5. Если указано только "с [дата] [время] до [время]" (без даты окончания), значит "end_date" совпадает с "start_date".

Ответь ТОЛЬКО JSON объектом.
Пример ответа:
{{
  "published": "20.05.2024",
  "status": "Плановое",
  "start_date": "22.05.2024",
  "start_time": "11:00",
  "end_date": "22.05.2024",
  "end_time": "17:00",
  "regions": ["Ереван, Ачапняк"],
  "streets": ["кв. Силикян 1-я ул. 1-40; 3-я ул. 1-35", "ул. Бабаджаняна 21, 23, 25"],
  "description": "Для обеспечения безопасности и надежности электроснабжения."
}}
"""
    loop = asyncio.get_event_loop()
    raw_json_output = ""
    try:
        raw_json_output = await loop.run_in_executor(None, ask_model, prompt)
        match = re.search(r'{\s*.*?\s*}', raw_json_output, re.DOTALL)
        if match:
            cleaned_json_string = match.group(0)
            try:
                parsed_data = json.loads(cleaned_json_string)
                log_info(f"Successfully extracted electric info: Status - {parsed_data.get('status')}, StartDate - {parsed_data.get('start_date')}")
                return parsed_data
            except json.JSONDecodeError as e_json:
                log_error(f"JSON Decode Error for electric after cleaning: {e_json}. Cleaned: '{cleaned_json_string}'. Raw: '{raw_json_output}'")
                return {}
        else:
            log_error(f"No JSON object found in LLM output for electric. Raw: {raw_json_output}")
            return {}
    except Exception as e:
        log_error(f"Generic error in extract_electric_info_async: {e}. LLM Output: '{raw_json_output}'", exc=e)
        return {}

async def parse_all_electric_announcements_async() -> list[dict]:
    log_info("Starting parse_all_electric_announcements_async...")
    texts = await fetch_electric_announcements_async()
    if not texts:
        log_info("No electric announcement texts fetched.")
        return []

    log_info(f"Fetched {len(texts)} electric texts. Starting extraction...")
    tasks = [extract_electric_info_async(t) for t in texts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    final_results = []
    for i, res in enumerate(results):
        if isinstance(res, dict) and res:
            final_results.append(res)
        elif isinstance(res, Exception):
            log_error(f"Exception during electric info extraction task for text {i+1}: {res}", exc=res)
        else:
            text_snippet = texts[i][:70].replace('\n', ' ')
            log_warning(f"Empty result from electric info extraction for text {i+1}. Original text (first 70 chars): {text_snippet}")
            
    log_info(f"Total electric announcements successfully processed into JSON: {len(final_results)} (out of {len(texts)} fetched raw texts)")
    return final_results
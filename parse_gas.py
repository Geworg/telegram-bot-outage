import asyncio
import httpx
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timedelta
from ai_engine import structure_text_with_ai_async, is_ai_available
from logger import log_error, log_info, log_warning

GAS_URL_VTAR = "https://armenia-am.gazprom.com/notice/announcement/vtar/"
GAS_URL_PLAN = "https://armenia-am.gazprom.com/notice/announcement/plan/"

async def fetch_gas_announcements_async() -> list[str]:
    log_info("Fetching gas announcements (async)...")
    raw_texts = []
    urls_to_fetch = [GAS_URL_VTAR, GAS_URL_PLAN]

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            for url in urls_to_fetch:
                log_info(f"Fetching from {url}...")
                response = await client.get(url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                # Селектор для Газпрома, может потребовать адаптации
                # <div class="items"> <div class="panel-group"> <div class="panel-body"> - текст объявления
                announcement_items = soup.select('div.items div.panel-group div.panel-body')
                if not announcement_items:
                     log_info(f"No gas announcements found with selector on {url}")

                for item in announcement_items:
                    text_content = item.get_text(separator="\n", strip=True)
                    if text_content:
                        # Добавляем URL источника для возможного различения статуса (план/авария)
                        # если LLM не справится или для логов
                        raw_texts.append(f"Источник: {url}\n{text_content}")
                log_info(f"Fetched {len(announcement_items)} items from {url}")
        
        log_info(f"Total fetched {len(raw_texts)} raw gas announcements from all sources.")
        return raw_texts
    except httpx.HTTPStatusError as e:
        log_error(f"HTTP error {e.response.status_code} while fetching gas data from {e.request.url}")
    except httpx.RequestError as e: # Ошибка сети/DNS и т.д.
        log_error(f"Network error fetching gas data from {getattr(e, 'request', 'N/A') and getattr(e.request, 'url', 'N/A')}: {e}")
    except Exception as e: # Другие ошибки (например, при парсинге HTML)
        log_error(f"Generic error parsing gas HTML: {e}", exc=e)
    return []


async def extract_gas_info_async(text_with_source: str) -> dict:
    # Извлекаем URL источника, если он был добавлен
    source_url_line, text = text_with_source.split("\n", 1) if text_with_source.startswith("Источник:") else (None, text_with_source)
    status_from_url = None
    if source_url_line and GAS_URL_VTAR in source_url_line: status_from_url = "Аварийное"
    elif source_url_line and GAS_URL_PLAN in source_url_line: status_from_url = "Плановое"

    log_info_text_preview = text[:70].replace('\n', ' ')
    log_info(f"Extracting gas info (source: {source_url_line or 'N/A'}, first 70 chars): {log_info_text_preview}...")
    # Промпт для газа, аналогичен водному, но специфичен для газа
    prompt = f"""
Проанализируй следующий текст объявления об отключении ГАЗА и извлеки структурированную информацию.
Текст объявления:
---
{text}
---

Извлеки данные строго в формате JSON со следующими полями:
- "published": дата публикации объявления (string, "дд.мм.гггг" или null, если нет).
- "status": тип отключения (string, "Плановое" или "Аварийное"). Если в тексте неясно, но URL источника был "{GAS_URL_VTAR}", ставь "Аварийное". Если "{GAS_URL_PLAN}", ставь "Плановое". Если неясно и нет URL, используй "Плановое".
- "start_date": дата начала отключения (string, "дд.мм.гггг").
- "start_time": время начала отключения (string, "чч:мм").
- "end_date": дата окончания отключения (string, "дд.мм.гггг").
- "end_time": время окончания отключения (string, "чч:мм").
- "regions": список регионов/административных районов (list of strings, например, ["г. Ереван, Ачапняк", "Котайкская область, г. Абовян"] или null).
- "streets": список затронутых улиц с номерами домов, если указаны (list of strings, например, ["ул. Шираки 20-30", "кв. Норагюх все дома"] или null).
- "description": краткое описание причины или дополнительная информация (string или null).

Правила:
1. Если поле отсутствует в тексте, значение должно быть null.
2. Даты должны быть в формате "дд.мм.гггг". Если год не указан, предположи текущий год ({datetime.now().year}).
3. Время должно быть в формате "чч:мм" (24-часовой).
4. Если указан диапазон дат (например, "с 21 по 23 мая"), "start_date" - первая дата, "end_date" - вторая.
5. Если указано только "с [дата] [время] до [время]" (без даты окончания), значит "end_date" совпадает с "start_date".

Ответь ТОЛЬКО JSON объектом.
Пример ответа:
{{
  "published": null,
  "status": "{status_from_url if status_from_url else "Плановое"}",
  "start_date": "23.05.2024",
  "start_time": "09:00",
  "end_date": "23.05.2024",
  "end_time": "17:00",
  "regions": ["г. Ереван, Ачапняк"],
  "streets": ["ул. Шираки 22, 22/1, 24"],
  "description": "Плановые ремонтные работы."
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
                # Если LLM не установил статус, а мы его определили по URL, устанавливаем его
                if 'status' not in parsed_data and status_from_url:
                    parsed_data['status'] = status_from_url
                elif parsed_data.get('status') is None and status_from_url: # Если LLM вернул null, но мы знаем
                    parsed_data['status'] = status_from_url

                log_info(f"Successfully extracted gas info: Status - {parsed_data.get('status')}, StartDate - {parsed_data.get('start_date')}")
                return parsed_data
            except json.JSONDecodeError as e_json:
                log_error(f"JSON Decode Error for gas after cleaning: {e_json}. Cleaned: '{cleaned_json_string}'. Raw: '{raw_json_output}'")
                return {}
        else:
            log_error(f"No JSON object found in LLM output for gas. Raw: {raw_json_output}")
            return {}
    except Exception as e:
        log_error(f"Generic error in extract_gas_info_async: {e}. LLM Output: '{raw_json_output}'", exc=e)
        return {}

async def parse_all_gas_announcements_async() -> list[dict]:
    log_info("Starting parse_all_gas_announcements_async...")
    texts_with_sources = await fetch_gas_announcements_async()
    if not texts_with_sources:
        log_info("No gas announcement texts fetched.")
        return []

    log_info(f"Fetched {len(texts_with_sources)} gas texts. Starting extraction...")
    tasks = [extract_gas_info_async(tws) for tws in texts_with_sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    final_results = []
    for i, res in enumerate(results):
        if isinstance(res, dict) and res:
            final_results.append(res)
        elif isinstance(res, Exception):
            log_error(f"Exception during gas info extraction task for text {i+1}: {res}", exc=res)
        else:
            text_snippet = texts_with_sources[i][:100].replace('\n', ' ')
            log_warning(f"Empty result from gas info extraction for text {i+1}. Original text (first 70 chars from source): {text_snippet}")
                
    log_info(f"Total gas announcements successfully processed into JSON: {len(final_results)} (out of {len(texts_with_sources)} fetched raw texts)")
    return final_results
    
# parse_water.py
import asyncio
import httpx
from bs4 import BeautifulSoup
import json
import re # Добавлен импорт re
# Предполагается, что ai_engine.py существует и ask_model в нем - синхронная функция
# Если ask_model асинхронная, то вызов await loop.run_in_executor не нужен, можно делать await ask_model(...)
from ai_engine import ask_model # Импортируем как есть
from logger import log_error, log_info

# URL для отключений воды
WATER_URL = "https://interactive.vjur.am/"

async def fetch_water_announcements_async() -> list[str]:
    log_info(f"Fetching water announcements from {WATER_URL} (async)...")
    raw_texts = []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client: # Увеличен таймаут
            # Могут быть разные секции для плановых и аварийных, или все вместе
            # Здесь пример для одной страницы, но можно расширить для нескольких URL, если нужно
            response = await client.get(WATER_URL)
            response.raise_for_status() # Проверка на HTTP ошибки

            # Парсинг HTML (BeautifulSoup синхронный, для очень больших страниц можно вынести в executor)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем контейнеры с объявлениями. Классы могут отличаться.
            # Этот селектор основан на предыдущем предположении. Адаптируйте под реальную структуру сайта.
            # Например, если каждое объявление в <div class="announcement-item">
            announcement_items = soup.select('div.items div.panel-group div.panel-body') # Пример селектора
            if not announcement_items:
                # Попробуем другой общий селектор, если первый не сработал
                # announcement_items = soup.find_all('article') # или другой тег
                log_info(f"No items found with 'div.items div.panel-group div.panel-body' at {WATER_URL}. Found {len(announcement_items)} items.")


            for item in announcement_items:
                text_content = item.get_text(separator="\n", strip=True) # Получаем текст, сохраняя переносы строк
                if text_content: # Добавляем только если есть текст
                    raw_texts.append(text_content)
            
        log_info(f"Fetched {len(raw_texts)} raw water announcements from {WATER_URL}.")
        return raw_texts
    except httpx.HTTPStatusError as e:
        log_error(f"HTTP error {e.response.status_code} while fetching water data from {WATER_URL}: {e.request.url}")
    except httpx.RequestError as e:
        log_error(f"Network error fetching water data from {WATER_URL}: {e}")
    except Exception as e:
        log_error(f"Generic error parsing water HTML from {WATER_URL}: {e}", exc=e)
    return [] # Возвращаем пустой список в случае любой ошибки

async def extract_water_info_async(text: str) -> dict:
    log_info_text = text[:70].replace('\n', ' ') # Сначала подготовить текст
    log_info(f"Extracting water info for text (first 70 chars): {log_info_text}...")
    # Промпт должен быть максимально точным и включать примеры разных форматов дат/времени, если они встречаются
    prompt = f"""
Проанализируй следующий текст объявления об отключении ВОДЫ и извлеки структурированную информацию.
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
- "regions": список регионов/административных районов (list of strings, например, ["Кентрон", "Арабкир"] или ["Армавирская область"] или null).
- "streets": список затронутых улиц с номерами домов, если указаны (list of strings, например, ["ул. Абовяна 1-10", "пр. Маштоца все дома"] или null).
- "description": краткое описание причины или дополнительная информация (string или null).

Правила:
1. Если поле отсутствует в тексте, значение должно быть null (JSON null, не строка "null").
2. Даты должны быть в формате "дд.мм.гггг". Если год не указан, предположи текущий год ({datetime.now().year}).
3. Время должно быть в формате "чч:мм" (24-часовой).
4. Если указан диапазон дат (например, "с 21 по 23 мая"), "start_date" - первая дата, "end_date" - вторая.
5. Если указано только "с [дата] [время] до [время]" (без даты окончания), значит "end_date" совпадает с "start_date".
6. В "streets" включай также номера домов, корпуса, если они есть.
7. В "regions" могут быть как районы Еревана, так и области Армении.

Ответь ТОЛЬКО JSON объектом. Не добавляй никаких пояснений до или после JSON.
Пример ответа:
{{
  "published": "20.05.2024",
  "status": "Плановое",
  "start_date": "21.05.2024",
  "start_time": "10:00",
  "end_date": "21.05.2024",
  "end_time": "18:00",
  "regions": ["Кентрон"],
  "streets": ["ул. Туманяна 5, 7", "пр. Саят-Новы 10-15"],
  "description": "Ремонтные работы на линии."
}}
"""
    loop = asyncio.get_event_loop()
    raw_json_output = "" # Инициализируем на случай ошибки до вызова LLM
    try:
        # Предполагаем, что ask_model - это блокирующая функция (CPU-bound или IO-bound)
        raw_json_output = await loop.run_in_executor(None, ask_model, prompt)
        
        # Попытка очистить JSON от возможных текстовых "артефактов" (например, ```json ... ```)
        match = re.search(r'{\s*.*?\s*}', raw_json_output, re.DOTALL)
        if match:
            cleaned_json_string = match.group(0)
            try:
                parsed_data = json.loads(cleaned_json_string)
                log_info(f"Successfully extracted water info: Status - {parsed_data.get('status')}, StartDate - {parsed_data.get('start_date')}")
                # Дополнительная валидация полей может быть здесь
                return parsed_data
            except json.JSONDecodeError as e_json:
                log_error(f"JSON Decode Error for water after cleaning: {e_json}. Cleaned JSON String: '{cleaned_json_string}'. Raw LLM Output: '{raw_json_output}'")
                return {} # Возвращаем пустой словарь при ошибке декодирования
        else:
            log_error(f"No JSON object found in LLM output for water. Raw LLM Output: {raw_json_output}")
            return {}
            
    except Exception as e: # Ловим другие возможные ошибки (например, если ask_model падает)
        log_error(f"Generic error in extract_water_info_async: {e}. LLM Output (if available): '{raw_json_output}'", exc=e)
        return {}

async def parse_all_water_announcements_async() -> list[dict]:
    log_info("Starting parse_all_water_announcements_async...")
    texts = await fetch_water_announcements_async()
    if not texts:
        log_info("No water announcement texts fetched.")
        return []
    
    log_info(f"Fetched {len(texts)} water texts. Starting extraction...")
    # Запускаем извлечение информации параллельно для всех текстов
    # Используем asyncio.create_task для более явного управления задачами, если потребуется
    tasks = [extract_water_info_async(t) for t in texts]
    results = await asyncio.gather(*tasks, return_exceptions=True) # Собираем результаты или исключения
    
    final_results = []
    for i, res in enumerate(results):
        if isinstance(res, dict) and res:  # Убедимся, что это не ошибка и не пустой dict
            final_results.append(res)
        elif isinstance(res, Exception):
            log_error(f"Exception during water info extraction task for text {i+1}: {res}", exc=res)
        else:  # Если вернулся пустой dict из extract_info
            text_snippet = texts[i][:70].replace('\n', ' ')
            log_warning(f"Empty result from water info extraction for text {i+1}. Original text (first 70 chars): {text_snippet}")

    log_info(f"Total water announcements successfully processed into JSON: {len(final_results)} (out of {len(texts)} fetched raw texts)")
    return final_results
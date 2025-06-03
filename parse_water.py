import asyncio
import httpx
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timedelta
from ai_engine import structure_text_with_ai_async, is_ai_available
from logger import log_error, log_info, log_warning

WATER_URL = "https://interactive.vjur.am/"

PROMPT_TEMPLATE_WATER = f"""
You are an AI assistant specialized in extracting information about water outages in Armenia from text.
The text is from the Veolia Jur website.
Extract the following fields from the provided text. If a field is not present, use null or an empty string.
Format dates and times as "YYYY-MM-DD HH:MM". Calculate duration if possible.

Fields to extract:
- "publication_date_on_site": Date and time the announcement was found/published (use "{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}" if not in text).
- "shutdown_type": Type of shutdown (e.g., "planned", "emergency", "профилактическое", "аварийное", "պլանային", "վթարային"). If not specified, try to infer or use "unknown".
- "start_datetime": Start date and time of the outage (e.g., "2024-07-15 10:00").
- "end_datetime": End date and time of the outage (e.g., "2024-07-15 18:00").
- "duration_hours": Calculated duration of the outage in hours (float or int).
- "regions": List of affected regions/districts (e.g., ["Арабкир", "Центр"]).
- "streets_buildings": List of strings, each describing affected streets and building numbers for a region.
  Try to capture detailed street names and building numbers/ranges.
  Example: ["ул. Наири Заряна 10-50", "пр. Комитаса все здания"].
- "source_url": The URL from which this information was sourced (use "{WATER_URL}").
- "original_text_snippet": First 100 characters of the original text for reference.
- "additional_details": Any other relevant information not covered above.

Respond ONLY with a single JSON object. Ensure all specified fields are present in your JSON response.
Address information should be as precise as possible.

Input text:
{{text_content}}
"""

async def fetch_water_announcements_async() -> list[str]:
    log_info(f"Fetching water announcements from {WATER_URL} (async)...")
    raw_texts = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(WATER_URL)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            # !!! ВАЖНО: ЭТОТ СЕЛЕКТОР НУЖНО АДАПТИРОВАТЬ ПОД РЕАЛЬНУЮ СТРУКТУРУ САЙТА VEOLIA JUR !!!
            # Current selector 'div.items div.panel-group div.panel-body' is a placeholder.
            # Inspect the website with browser developer tools (F12) to find correct selectors.
            # Example selectors (these are guesses, replace with actual ones):
            # announcement_items = soup.select('article.news-item')
            # announcement_items = soup.select('div.shutdown-notice')
            # If structure is like Gazprom:
            announcement_container = soup.find('div', class_='items') # Or similar top-level container
            if announcement_container:
                # Common pattern: panel-group contains multiple panel, each with panel-heading and panel-body
                announcement_elements = announcement_container.select('div.panel-group div.panel.panel-default')
                log_info(f"Found {len(announcement_elements)} potential water announcement elements using 'div.panel-group div.panel.panel-default'.")
                if not announcement_elements: # Fallback to direct panel-body if the above is too specific
                    announcement_elements = announcement_container.select('div.panel-body')
                    log_info(f"Fallback: Found {len(announcement_elements)} potential water announcement elements using 'div.panel-body'.")
                for item in announcement_elements:
                    # Try to get a title or date if available, helps with context
                    title_element = item.find(['h3', 'h4', 'div'], class_=['panel-title', 'title', 'date-display-single'])
                    title_text = title_element.get_text(separator=" ", strip=True) if title_element else ""
                    body_element = item.find('div', class_='panel-body') # Content is often in panel-body
                    if not body_element: # If no panel-body, use the item itself (if it's a direct content block)
                        body_element = item
                    text_content = body_element.get_text(separator="\\n", strip=True) # Use \\n as separator for LLM
                    if text_content:
                        full_text = f"{title_text}\\n{text_content}".strip()
                        raw_texts.append(full_text)
                        log_info(f"Extracted water text block (length {len(full_text)} chars). Start: {full_text[:100]}...")
                    else:
                        log_warning(f"Empty text content for a water announcement item: {item.prettify()[:200]}")
            else:
                log_warning(f"Could not find the main announcement container ('div.items') on {WATER_URL}. Page structure might have changed.")
                # As a last resort, try to grab all text from a main content area
                main_content = soup.find('main') or soup.find('div', id='content') or soup.body
                if main_content:
                    all_text = main_content.get_text(separator="\\n", strip=True)
                    if len(all_text) > 200: # Arbitrary threshold to avoid adding tiny bits of text
                        log_warning(f"Using fallback: extracting all text from main content area of {WATER_URL} due to missing specific selectors.")
                        # This is risky as it might grab unrelated text. Split into chunks if too long?
                        # For now, add as one large block; LLM might be able to find multiple announcements.
                        # raw_texts.append(all_text) # Disabled for now, too unreliable
                        pass
            if not raw_texts:
                log_warning(f"No water announcements found on {WATER_URL} using current selectors. Website structure may have changed or no active announcements.")
    except httpx.RequestError as e:
        log_error(f"HTTPX RequestError fetching water announcements: {e}", exc=e)
    except httpx.HTTPStatusError as e:
        log_error(f"HTTPX HTTPStatusError fetching water announcements: {e.response.status_code} for {e.request.url}", exc=e)
    except Exception as e:
        log_error(f"Generic error fetching water announcements: {e}", exc=e)
    log_info(f"Fetched {len(raw_texts)} raw text blocks for water announcements.")
    return raw_texts

async def extract_water_info_async(text_content: str) -> dict:
    """
    Extracts structured information from a single water announcement text using AI.
    """
    if not text_content.strip():
        log_warning("Skipping empty text content for water info extraction.")
        return {}
    # log_info(f"Attempting to extract water info from text: {text_content[:150]}...") # Can be verbose
    # IMPROVEMENT: Using the centralized structure_text_with_ai_async
    structured_data = await structure_text_with_ai_async(text_content, PROMPT_TEMPLATE_WATER)
    if "error" in structured_data:
        log_warning(f"Failed to structure water text with AI. Error: {structured_data.get('comment')}. Original text snippet: {text_content[:100]}")
        return structured_data # Return the error structure for further handling
    # IMPROVEMENT: Add source_url and original_text_snippet if not already added by LLM
    if "source_url" not in structured_data:
        structured_data["source_url"] = WATER_URL
    if "original_text_snippet" not in structured_data and "original_text" in structured_data: # Use full original_text if snippet not made by LLM
         structured_data["original_text_snippet"] = structured_data.get("original_text", "")[:100].replace('\n', ' ')
    elif "original_text_snippet" not in structured_data:
         structured_data["original_text_snippet"] = text_content[:100].replace('\n', ' ')
    # IMPROVEMENT: Post-process dates and calculate duration if LLM didn't.
    # This is an example; actual date parsing might need more robust logic based on LLM output format.
    try:
        if "start_datetime" in structured_data and "end_datetime" in structured_data and \
           isinstance(structured_data["start_datetime"], str) and \
           isinstance(structured_data["end_datetime"], str) and \
           "duration_hours" not in structured_data: # Only if LLM didn't provide it
            start_dt_str = structured_data["start_datetime"]
            end_dt_str = structured_data["end_datetime"]
            # Attempt to parse common date formats (adapt as needed based on LLM's typical output)
            # This is a very basic example. Consider using dateutil.parser for more robust parsing.
            dt_formats = ["%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S"]
            start_dt, end_dt = None, None
            for fmt in dt_formats:
                try:
                    start_dt = datetime.strptime(start_dt_str, fmt)
                    break
                except ValueError:
                    continue
            for fmt in dt_formats:
                try:
                    end_dt = datetime.strptime(end_dt_str, fmt)
                    break
                except ValueError:
                    continue
            if start_dt and end_dt and end_dt > start_dt:
                duration = end_dt - start_dt
                structured_data["duration_hours"] = round(duration.total_seconds() / 3600, 1)
                log_info(f"Calculated duration: {structured_data['duration_hours']}h for water announcement.")
            elif start_dt and end_dt and end_dt <= start_dt:
                log_warning(f"End datetime is not after start datetime for water: Start: {start_dt_str}, End: {end_dt_str}")
    except Exception as e:
        log_warning(f"Could not calculate duration for water announcement: {e}. Data: {structured_data}")
        # Do not fail the whole extraction if duration calculation fails
    # log_info(f"Successfully extracted water info: { {k:v for k,v in structured_data.items() if k != 'original_text'} }") # Avoid logging full text
    return structured_data

async def parse_all_water_announcements_async() -> list[dict]:
    log_info("Starting parse_all_water_announcements_async...")
    if not is_ai_available():
        log_warning("AI model not available. Skipping water announcements parsing.")
        return []
    texts = await fetch_water_announcements_async()
    if not texts:
        log_info("No water announcement texts fetched.")
        return []
    log_info(f"Fetched {len(texts)} water texts. Starting extraction with AI...")
    tasks = [extract_water_info_async(t) for t in texts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    final_results = []
    for i, res in enumerate(results):
        if isinstance(res, dict) and res and "error" not in res:
            final_results.append(res)
        elif isinstance(res, Exception):
            log_error(f"Exception during water info extraction task {i+1}: {res}", exc=res)
        elif isinstance(res, dict) and "error" in res:
             log_warning(f"AI error for water text {i+1}. Error: {res.get('comment', 'Unknown AI error')}. Original: {res.get('original_text_snippet', res.get('original_text', 'N/A')[:100])}")
        else:
            log_warning(f"Empty or unexpected result from water info extraction for text {i+1}. Result: {res}")     
    log_info(f"WATER announcements processed. Extracted valid data for {len(final_results)} out of {len(texts)} texts.")
    return final_results

# NOTE: 1. Централизовать URL-адреса или получить из конфигурации.
# 2. Обновить PROMPT_TEMPLATE_* для более подробного и надежного извлечения.
# 3. Улучшить селекторы HTML в fetch_*_announcements_async с большим количеством журналов и резервных вариантов.
# 4. Обеспечить, чтобы extract_*_info_async использовал structure_text_with_ai_async.
# 5. При необходимости добавить постобработку для длительности.
# 6. Улучшить журналирование в parse_all_*_announcements_async для успехов и неудач.
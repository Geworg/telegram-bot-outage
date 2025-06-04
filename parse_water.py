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
- "publication_date_on_site": Date and time the announcement was found/published (use "{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}" if not in text and no other date available).
- "shutdown_type": Type of shutdown (e.g., "planned", "emergency", "профилактическое", "аварийное", "պլանային", "վթարային"). If not specified, try to infer or use "unknown".
- "start_datetime": Start date and time of the outage (e.g., "2024-07-15 10:00").
- "end_datetime": End date and time of the outage (e.g., "2024-07-15 18:00").
- "duration_hours": Calculated duration of the outage in hours. If start and end are present, calculate it.
- "reason": Reason for the outage if specified (e.g., "maintenance", "repair", "профилактические работы", "аварийно-восстановительные работы").
- "locations": A list of affected locations. Each location object should have:
    - "region": (e.g., "Շենգավիթ", "Кентрон", "Shengavit")
    - "city_district": (e.g., "Նոր Նորք", "Арабкир")
    - "street_address": Full street address including building numbers, house numbers if available (e.g., "ք. Երևան, Նոր Նորքի 2-րդ զանգ.՝ Գայի պող. 10/1, 10/2, 12/1, 12/2, 14/1 շենքեր")
- "source_url": The URL from which this information was extracted (use "{WATER_URL}").
- "additional_info": Any other relevant information not fitting other fields.
- "contact_info": Any contact numbers or information provided.

Output the result as a single JSON object.
"""

async def fetch_water_announcements_async() -> list[str]:
    log_info(f"Fetching water announcements from {WATER_URL} (async)...")
    raw_texts = []
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client: # Increased timeout
            response = await client.get(WATER_URL)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            # User: "уведомления находятся и начинаются с <div class="items"> до </div>"
            # Based on Water.html, the actual text is within panel-body inside items.
            # Example: <div class="items"> ... <div class="panel panel-danger/info..."> <div class="panel-body"> TEXT </div> </div> ... </div>
            # Corrected selector to find all panel-body divs within the div.items container
            announcement_container = soup.find('div', class_='items')
            if announcement_container:
                announcement_panels = announcement_container.select('div.panel div.panel-body')
                if announcement_panels:
                    for panel_body in announcement_panels:
                        text_content = panel_body.get_text(separator='\n', strip=True)
                        if text_content: # Ensure there's actual text
                            raw_texts.append(text_content)
                    log_info(f"Extracted {len(raw_texts)} water announcement texts using 'div.items div.panel div.panel-body'.")
                else:
                    log_warning(f"Container 'div.items' found, but no 'div.panel div.panel-body' found within it at {WATER_URL}.")
            else:
                # Fallback or alternative selector if 'div.items' is not found or for different structures.
                # The previous script used 'div.panel.panel-info', this is now incorporated above more generally.
                # If 'div.items' is crucial and not found, it's a significant page change.
                log_warning(f"Main announcement container 'div.items' not found at {WATER_URL}. Page structure might have changed.")
            if not raw_texts:
                log_warning(f"No water announcement texts extracted from {WATER_URL}. Check selectors and page structure.")
    except httpx.HTTPStatusError as e:
        log_error(f"HTTP error fetching water announcements: {e.response.status_code} for {e.request.url}", exc=e)
        return []
    except httpx.RequestError as e:
        log_error(f"Request error fetching water announcements: {e}", exc=e)
        return []
    except Exception as e:
        log_error(f"General error fetching water announcements: {e}", exc=e)
        return []
    log_info(f"Finished fetching water announcements. Total texts extracted: {len(raw_texts)}")
    return raw_texts

async def extract_water_info_async(text_content: str) -> dict:
    if not await is_ai_available():
        log_warning("AI service is not available. Skipping water info extraction.")
        return {"error": "AI service unavailable", "original_text": text_content}
    try:
        # Using the PROMPT_TEMPLATE_WATER defined at the top of this file
        structured_data = await structure_text_with_ai_async(text_content, PROMPT_TEMPLATE_WATER, "water")
        if not structured_data:
            log_warning(f"AI returned no data for water text. Text: {text_content[:100]}...")
            return {"error": "AI returned no data", "original_text_snippet": text_content[:100]}
        # Add source URL and type if not already there from AI (though prompt asks for it)
        structured_data["source_url"] = WATER_URL
        structured_data["source_type"] = "water"
        structured_data["original_text_snippet"] = text_content[:150]
        # Example of post-processing AI output if necessary:
        # if "start_datetime" in structured_data and isinstance(structured_data["start_datetime"], str):
        #     # Attempt to parse and reformat, or validate
        #     pass 
        return structured_data
    except json.JSONDecodeError as je: # If AI output is not valid JSON (though structure_text_with_ai_async should handle this)
        log_error(f"Failed to decode JSON from AI for water: {je}. Raw output: AI_OUTPUT_WAS_HERE", exc=je) # Be careful logging raw output if sensitive
        return {"error": f"AI output JSON decode error: {je}", "original_text_snippet": text_content[:100]}
    except Exception as e:
        log_error(f"Error structuring water text with AI: {e}. Text: {text_content[:100]}...", exc=e)
        return {"error": f"AI processing failed: {e}", "original_text_snippet": text_content[:100]}

async def parse_all_water_announcements_async(context) -> list[dict]:
    log_info("Starting parse_all_water_announcements_async...")
    texts = await fetch_water_announcements_async()
    if not texts:
        log_info("No water announcement texts fetched.")
        return []
    log_info(f"Fetched {len(texts)} water texts. Starting AI extraction with AI...")
    tasks = [extract_water_info_async(t) for t in texts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    final_results = []
    for i, res in enumerate(results):
        if isinstance(res, dict) and "error" not in res and res: # Ensure it's a dict, no error, and not empty
            final_results.append(res)
        elif isinstance(res, Exception):
            log_error(f"Exception during water info extraction task {i+1}: {res}", exc=res)
        elif isinstance(res, dict) and "error" in res:
             log_warning(f"AI or processing error for water text {i+1}. Error: {res.get('error', 'Unknown AI error')}. Original snippet: {res.get('original_text_snippet', texts[i][:100] if i < len(texts) else 'N/A')}")
        else:
            log_warning(f"Empty or unexpected result from water info extraction for text {i+1}. Result: {res}. Original snippet: {texts[i][:100] if i < len(texts) else 'N/A'}")   
    log_info(f"WATER announcements processed. Extracted valid data for {len(final_results)} out of {len(texts)} texts.")
    return final_results

# Example usage (optional, for testing)
# if __name__ == '__main__':
#     async def main():
#         results = await parse_all_water_announcements_async()
#         if results:
#             print(f"Successfully parsed {len(results)} water announcements:")
#             for item in results:
#                 print(json.dumps(item, ensure_ascii=False, indent=2))
#         else:
#             print("No water announcements parsed.")
#     asyncio.run(main())

# <3
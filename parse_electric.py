import asyncio
import httpx
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timedelta
from ai_engine import structure_text_with_ai_async, is_ai_available
from logger import log_error, log_info, log_warning

ELECTRIC_URL = "https://www.ena.am/Info.aspx?id=5&lang=1" # lang=1 Armenian

async def fetch_electric_announcements_async() -> list[str]:
    log_info(f"Fetching electric announcements from {ELECTRIC_URL} (async)...")
    raw_texts = []
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client: # Increased timeout, added follow_redirects
            response = await client.get(ELECTRIC_URL)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. Planned Outages
            # User: "текст плановых отключений начинается с <span id="ctl00_ContentPlaceHolder1_attenbody"> до </span>"
            planned_outages_span = soup.find('span', id='ctl00_ContentPlaceHolder1_attenbody')
            if planned_outages_span:
                planned_text = planned_outages_span.get_text(separator='\n', strip=True)
                if planned_text:
                    raw_texts.append(planned_text)
                    log_info("Extracted planned electricity outage text.")
                else:
                    log_warning("Planned outage span ctl00_ContentPlaceHolder1_attenbody found but was empty.")
            else:
                log_warning("Planned electricity outage span (ctl00_ContentPlaceHolder1_attenbody) not found.")

            # 2. Emergency Outages
            # User: "блок аварийных отключений это список в конце страницы. Начинается с старых адресов, до новых."
            # "Последняя кнопка ... это список последних отключений. Нужно перейти, чтобы отобразилось."
            # NB: httpx cannot click buttons or execute JS for pagination. This will only get the initially loaded table data.
            emergency_table = soup.find('table', id='ctl00_ContentPlaceHolder1_vtarayin')
            if emergency_table:
                log_info("Found emergency electricity outage table (ctl00_ContentPlaceHolder1_vtarayin). Parsing rows...")
                log_warning("Emergency electricity outages: Only parsing the currently visible page due to static fetching limitations. Full data might require JS execution for pagination.")
                
                rows = emergency_table.select('tbody tr')
                if not rows: # Fallback if tbody is not explicitly there or rows are direct children of table
                    rows = emergency_table.select('tr')

                announcements_in_table = 0
                for row in rows:
                    cells = row.find_all(['td', 'th']) # Include th just in case headers are mixed or for robustness
                    row_texts = [cell.get_text(strip=True) for cell in cells]
                    if any(text for text in row_texts): # Ensure row is not empty
                        # Concatenate cell texts to form a single "document" for the AI
                        # The AI will need to be trained/prompted to understand this structure
                        # Example: "Date | Time | Region | Street | Status"
                        raw_texts.append(" | ".join(filter(None, row_texts)))
                        announcements_in_table +=1
                if announcements_in_table > 0:
                    log_info(f"Extracted {announcements_in_table} emergency outage rows from the table.")
                else:
                    log_warning("Emergency outage table found, but no data rows were extracted. Structure might have changed or table is empty.")
            else:
                log_warning("Emergency electricity outage table (ctl00_ContentPlaceHolder1_vtarayin) not found.")
            
            if not raw_texts:
                log_warning(f"No electric announcement texts extracted from {ELECTRIC_URL}. Check selectors and page structure.")

    except httpx.HTTPStatusError as e:
        log_error(f"HTTP error fetching electric announcements: {e.response.status_code} for {e.request.url}", exc=e)
        return []
    except httpx.RequestError as e:
        log_error(f"Request error fetching electric announcements: {e}", exc=e)
        return []
    except Exception as e:
        log_error(f"General error fetching electric announcements: {e}", exc=e)
        return []
    
    log_info(f"Finished fetching electric announcements. Total texts extracted: {len(raw_texts)}")
    return raw_texts

async def extract_electric_info_async(text_content: str) -> dict:
    if not await is_ai_available():
        log_warning("AI service is not available. Skipping electric info extraction.")
        return {"error": "AI service unavailable", "original_text": text_content}

    # The prompt should be designed to handle both planned text blocks and structured " | " separated table rows.
    # This might require two different prompts or a very robust single prompt.
    # For simplicity, assuming a robust PROMPT_TEMPLATE_ELECTRIC exists or is configured in ai_engine.
    prompt_template = "Extract structured outage information from the following Armenian electricity announcement. The text might be a general announcement or a table row with fields separated by '|'. Fields to extract: publication_date_on_site, shutdown_type (planned/emergency), start_datetime, end_datetime, duration_hours, region, city_district, street_address, additional_info. Format dates as YYYY-MM-DD HH:MM. If it's a general announcement, capture the overall message. If it's a table row, interpret the columns appropriately. Current date for reference if publication date is missing: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        structured_data = await structure_text_with_ai_async(text_content, prompt_template, "electric")
        if not structured_data:
            log_warning(f"AI returned no data for electric text. Text: {text_content[:100]}...")
            return {"error": "AI returned no data", "original_text_snippet": text_content[:100]}
        
        # Basic validation or transformation can be added here if needed
        structured_data["source_type"] = "electric"
        structured_data["original_text_snippet"] = text_content[:150] # Add snippet for logging/debugging
        return structured_data
        
    except Exception as e:
        log_error(f"Error structuring electric text with AI: {e}. Text: {text_content[:100]}...", exc=e)
        return {"error": f"AI processing failed: {e}", "original_text_snippet": text_content[:100]}

async def parse_all_electric_announcements_async() -> list[dict]:
    log_info("Starting parse_all_electric_announcements_async...")
    texts = await fetch_electric_announcements_async()
    if not texts:
        log_info("No electric announcement texts fetched.")
        return []

    log_info(f"Fetched {len(texts)} electric texts. Starting AI extraction...")
    
    # Consider rate limiting if AI service has limits
    tasks = [extract_electric_info_async(t) for t in texts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    final_results = []
    for i, res in enumerate(results):
        if isinstance(res, dict) and "error" not in res and res:
            final_results.append(res)
        elif isinstance(res, Exception):
            log_error(f"Exception during electric info extraction task for text index {i}: {res}", exc=res)
        elif isinstance(res, dict) and "error" in res:
            log_warning(f"AI or processing error for electric text index {i}: {res.get('error')}. Original snippet: {res.get('original_text_snippet', texts[i][:70])}")
        else:
            text_snippet = texts[i][:70].replace('\n', ' ') if i < len(texts) else "N/A"
            log_warning(f"Empty or unexpected result from electric info extraction for text index {i}. Original text snippet: {text_snippet}")
            
    log_info(f"ELECTRIC announcements processed. Extracted valid data for {len(final_results)} out of {len(texts)} texts.")
    return final_results

# Example usage (optional, for testing)
# if __name__ == '__main__':
#     async def main():
#         # Mock ai_engine for local testing if needed
#         # global is_ai_available, structure_text_with_ai_async
#         # async def mock_is_ai_available(): return True
#         # async def mock_structure_text_with_ai_async(text, prompt, type): 
#         #     print(f"Mock AI processing {type} text: {text[:50]}...")
#         #     return {"mock_data": text[:50]}
#         # is_ai_available = mock_is_ai_available
#         # structure_text_with_ai_async = mock_structure_text_with_ai_async
          
#         results = await parse_all_electric_announcements_async()
#         if results:
#             print(f"Successfully parsed {len(results)} electric announcements:")
#             for item in results:
#                 print(json.dumps(item, ensure_ascii=False, indent=2))
#         else:
#             print("No electric announcements parsed.")
#     asyncio.run(main())
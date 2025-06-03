import asyncio
import httpx
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timedelta
from ai_engine import structure_text_with_ai_async, is_ai_available
from logger import log_error, log_info, log_warning

GAS_URL_VTAR = "https://armenia-am.gazprom.com/notice/announcement/vtar/" # Emergency
GAS_URL_PLAN = "https://armenia-am.gazprom.com/notice/announcement/plan/" # Planned

# It's good practice to have a specific prompt for gas if its text structure or required fields differ.
# For now, assuming a generic or adaptable prompt is used in structure_text_with_ai_async or a PROMPT_TEMPLATE_GAS exists.
PROMPT_TEMPLATE_GAS = f"""
You are an AI assistant specialized in extracting information about gas outages in Armenia from text.
The text is from the Gazprom Armenia website.
Extract the following fields from the provided text. If a field is not present, use null or an empty string.
Format dates and times as "YYYY-MM-DD HH:MM". Calculate duration if possible.

Fields to extract:
- "publication_date_on_site": Date and time the announcement was found/published (use "{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}" if not in text and no other date available).
- "shutdown_type": Type of shutdown (e.g., "planned", "emergency", "պլանային", "վթարային"). Try to infer from context or source URL if not specified.
- "start_datetime": Start date and time of the outage.
- "end_datetime": End date and time of the outage.
- "duration_hours": Calculated duration in hours.
- "reason": Reason for the outage.
- "locations": A list of affected location objects, each with:
    - "region": Administrative region.
    - "city_district": City or district.
    - "street_address": Detailed street address, buildings, areas.
- "source_url": The URL from which this information was extracted.
- "additional_info": Other relevant details.
- "contact_info": Any contact numbers provided.

Output the result as a single JSON object. If the text indicates no current outages of a certain type, reflect that, perhaps with an "all_clear" field set to true or empty locations.
"""

async def fetch_gas_announcements_async() -> list[tuple[str, str]]: # Return list of (text, url)
    log_info("Fetching gas announcements (async)...")
    texts_with_sources = [] # Store tuples of (text_content, source_url)
    # Map URL to its type (planned/emergency) and specific selectors if needed
    urls_to_fetch_map = {
        GAS_URL_PLAN: "planned",
        GAS_URL_VTAR: "emergency"
    }
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client: # Increased timeout
            for url, outage_type in urls_to_fetch_map.items():
                log_info(f"Fetching from {url} (type: {outage_type})...")
                response = await client.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                content_extracted = False
                # User for GAS_URL_PLAN: "текст начинается с <div class="page_text_cont"> до </div>"
                # User for GAS_URL_VTAR: "только вот это: "<div id="content_wrapper">...<h1>..." (implies general text)
                # Try 'div.page_text_cont' for both first, as it's a common content container.
                page_content_div = soup.select_one('div.page_text_cont')
                if page_content_div:
                    text_content = page_content_div.get_text(separator='\n', strip=True)
                    if text_content:
                        texts_with_sources.append((text_content, url))
                        log_info(f"Extracted text from 'div.page_text_cont' for {outage_type} at {url}")
                        content_extracted = True
                    else:
                        log_warning(f"'div.page_text_cont' found but was empty for {outage_type} at {url}.")
                if not content_extracted and outage_type == "emergency":
                    # Fallback for emergency if 'div.page_text_cont' is not found or empty,
                    # and try to get text from the broader 'div#content_wrapper'.
                    content_wrapper = soup.select_one('div#content_wrapper')
                    if content_wrapper:
                        # Attempt to get a more specific text block, excluding nav, h1, etc.
                        # This part is heuristic and might need adjustment based on actual VTAR page structure.
                        # We want to avoid grabbing just the title or navigation links.
                        main_text_elements = content_wrapper.find_all(['p', 'div'], recursive=True)
                        candidate_texts = []
                        for elem in main_text_elements:
                            # Avoid known non-content containers if they exist within content_wrapper
                            if elem.name == 'div' and ('class' in elem.attrs and any(c in elem.attrs['class'] for c in ['breadcrumbs', 'child_navigation_wrapper', 'hidden'])):
                                continue
                            if elem.find_parent(['nav', 'header', 'footer', 'script', 'style']): # Basic exclusion
                                continue
                            text = elem.get_text(separator='\n', strip=True)
                            if text and len(text) > 50 : # Arbitrary length to prefer substantial text blocks
                                # Avoid re-adding if page_text_cont was already (even if empty) within this.
                                if not page_content_div or (page_content_div and elem not in page_content_div.find_all()):
                                     candidate_texts.append(text)
                        if candidate_texts:
                            # Join candidate texts; AI will need to parse this combined block.
                            combined_text = "\n\n---\n\n".join(candidate_texts)
                            texts_with_sources.append((combined_text, url))
                            log_info(f"Extracted general text from 'div#content_wrapper' for emergency at {url}.")
                            content_extracted = True
                        else:
                            log_warning(f"Could not extract substantial general text from 'div#content_wrapper' for emergency at {url}. Page might be minimal.")
                    else:
                        log_warning(f"'div#content_wrapper' not found for emergency at {url}.")
                if not content_extracted:
                    log_warning(f"No specific content container ('div.page_text_cont' or fallback for emergency) yielded text for {outage_type} at {url}. Page structure may have changed or no relevant announcements present.")
            if not texts_with_sources:
                log_warning("No gas announcement texts extracted from any URL.")
            else:
                log_info(f"Successfully extracted {len(texts_with_sources)} text blocks for gas announcements.")
    except httpx.HTTPStatusError as e:
        log_error(f"HTTP error fetching gas announcements: {e.response.status_code} for {e.request.url}", exc=e)
        return []
    except httpx.RequestError as e:
        log_error(f"Request error fetching gas announcements: {e}", exc=e)
        return []
    except Exception as e:
        log_error(f"General error fetching gas announcements: {e}", exc=e)
        return []
    return texts_with_sources

async def extract_gas_info_async(text_content_with_source: tuple[str, str]) -> dict:
    text_content, source_url = text_content_with_source
    if not await is_ai_available():
        log_warning("AI service is not available. Skipping gas info extraction.")
        return {"error": "AI service unavailable", "original_text": text_content, "source_url": source_url}
    try:
        # Use PROMPT_TEMPLATE_GAS defined above
        structured_data = await structure_text_with_ai_async(text_content, PROMPT_TEMPLATE_GAS, "gas")
        if not structured_data:
            log_warning(f"AI returned no data for gas text from {source_url}. Text: {text_content[:100]}...")
            return {"error": "AI returned no data", "original_text_snippet": text_content[:100], "source_url": source_url}
        structured_data["source_url"] = source_url # Ensure source_url is in the final dict
        structured_data["source_type"] = "gas"
        structured_data["original_text_snippet"] = text_content[:150]
        # Infer shutdown_type from URL if AI doesn't fill it
        if "shutdown_type" not in structured_data or not structured_data.get("shutdown_type") or structured_data.get("shutdown_type") == "unknown":
            if source_url == GAS_URL_PLAN:
                structured_data["shutdown_type"] = "planned"
            elif source_url == GAS_URL_VTAR:
                structured_data["shutdown_type"] = "emergency"
        return structured_data
    except Exception as e:
        log_error(f"Error structuring gas text with AI from {source_url}: {e}. Text: {text_content[:100]}...", exc=e)
        return {"error": f"AI processing failed: {e}", "original_text_snippet": text_content[:100], "source_url": source_url}

async def parse_all_gas_announcements_async() -> list[dict]:
    log_info("Starting parse_all_gas_announcements_async...")
    texts_with_sources = await fetch_gas_announcements_async()
    if not texts_with_sources:
        log_info("No gas announcement texts fetched.")
        return []
    log_info(f"Fetched {len(texts_with_sources)} gas texts with sources. Starting AI extraction...")
    tasks = [extract_gas_info_async(tws) for tws in texts_with_sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    final_results = []
    for i, res in enumerate(results):
        original_text_snippet = "N/A"
        source_url_for_log = "N/A"
        if i < len(texts_with_sources):
            original_text_snippet = texts_with_sources[i][0][:100] if texts_with_sources[i][0] else "N/A"
            source_url_for_log = texts_with_sources[i][1]
        if isinstance(res, dict) and "error" not in res and res:
            final_results.append(res)
        elif isinstance(res, Exception):
            log_error(f"Exception during gas info extraction task for text from {source_url_for_log}: {res}", exc=res)
        elif isinstance(res, dict) and "error" in res:
            log_warning(f"AI or processing error for gas text from {res.get('source_url', source_url_for_log)}. Error: {res.get('error', 'Unknown AI error')}. Original snippet: {res.get('original_text_snippet', original_text_snippet)}")
        else:
            log_warning(f"Empty or unexpected result from gas info extraction for text from {source_url_for_log}. Result: {res}. Original snippet: {original_text_snippet}")
    log_info(f"GAS announcements processed. Extracted valid data for {len(final_results)} out of {len(texts_with_sources)} texts.")
    return final_results

# Example usage (optional, for testing)
# if __name__ == '__main__':
#     async def main():
#         results = await parse_all_gas_announcements_async()
#         if results:
#             print(f"Successfully parsed {len(results)} gas announcements:")
#             for item in results:
#                 print(json.dumps(item, ensure_ascii=False, indent=2))
#         else:
#             print("No gas announcements parsed.")
#     asyncio.run(main())

# <3
import asyncio
import httpx
from bs4 import BeautifulSoup
import logging
from typing import List, Dict

# New local imports. ai_engine functions are now async, so we need to await them
from ai_engine import is_ai_available, translate_armenian_to_english, extract_entities_from_text
from parsing_utils import get_text_hash, structure_ner_entities
import db_manager

log = logging.getLogger(__name__)

GAS_URL_VTAR = "https://armenia-am.gazprom.com/notice/announcement/vtar/"  # Emergency
GAS_URL_PLAN = "https://armenia-am.gazprom.com/notice/announcement/plan/"  # Planned

async def fetch_gas_announcements() -> List[Dict]:
    """
    Fetches raw outage announcements from the Gazprom Armenia website for both
    planned and emergency outages.
    """
    log.info("Fetching gas announcements...")
    announcements = []
    urls_to_fetch = {
        GAS_URL_PLAN: "planned",
        GAS_URL_VTAR: "emergency"
    }
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for url, outage_type in urls_to_fetch.items():
                log.info(f"Fetching from {url} (type: {outage_type})...")
                response = await client.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # The main content is usually in 'div.page_text_cont'
                content_div = soup.select_one('div.page_text_cont')
                if content_div:
                    text_content = content_div.get_text(separator='\n', strip=True)
                    if text_content and "отключений нет" not in text_content.lower():
                        announcements.append({
                            "text": text_content,
                            "url": url,
                            "type": outage_type
                        })
                        log.info(f"Extracted content from {url}.")
                    else:
                        log.info(f"No active gas outages reported at {url}.")
                else:
                    log.warning(f"Content container 'div.page_text_cont' not found at {url}.")

    except httpx.RequestError as e:
        log.error(f"HTTP request error fetching gas announcements: {e}", exc_info=True)
    except Exception as e:
        log.error(f"General error fetching gas announcements: {e}", exc_info=True)
        
    return announcements

async def process_and_store_gas_announcement(announcement: dict):
    """
    Processes a single raw gas announcement using AI and stores it in the database.
    """
    raw_armenian_text = announcement['text']
    source_url = announcement['url']
    inferred_type = announcement['type']

    # Await the async AI functions
    english_text = await translate_armenian_to_english(raw_armenian_text)
    if not english_text:
        log.warning("Translation failed for a gas announcement.")
        return

    entities = await extract_entities_from_text(english_text)
    if not entities:
        log.info("No entities found in translated gas announcement.")
        return

    structured_data = structure_ner_entities(entities, english_text)

    # If AI couldn't determine status, use the one inferred from the URL
    if structured_data.get('status', 'unknown') == 'unknown':
        structured_data['status'] = inferred_type

    final_outage_data = {
        "raw_text_hash": get_text_hash(raw_armenian_text),
        "source_type": "gas",
        "source_url": source_url,
        "publication_date": None,
        "start_datetime": structured_data.get('start_datetime'),
        "end_datetime": structured_data.get('end_datetime'),
        "status": structured_data.get('status'),
        "regions": structured_data.get('regions', []),
        "streets": structured_data.get('streets', []),
        "details": structured_data.get('details', {})
    }
    final_outage_data['details']['armenian_text'] = raw_armenian_text
    
    await db_manager.add_outage(final_outage_data)
    log.info(f"Stored processed gas outage with hash: {final_outage_data['raw_text_hash']}")

async def parse_all_gas_announcements_async():
    """
    Main orchestrator function for gas parsing.
    """
    if not is_ai_available():
        log.error("Cannot parse gas announcements: AI models are not available (API keys missing).")
        return

    log.info("Starting full gas announcement parsing cycle...")
    raw_announcements = await fetch_gas_announcements()
    
    if not raw_announcements:
        log.info("No new gas announcements to process.")
        return
        
    tasks = [process_and_store_gas_announcement(ann) for ann in raw_announcements]
    await asyncio.gather(*tasks)
    
    log.info("Finished gas announcement parsing cycle.")
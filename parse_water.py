import asyncio
import httpx
from bs4 import BeautifulSoup
import logging
from typing import List
from ai_engine import is_ai_available, translate_armenian_to_english, extract_entities_from_text
from parsing_utils import get_text_hash, structure_ner_entities
import db_manager

log = logging.getLogger(__name__)

WATER_URL = "https://interactive.vjur.am/"

async def fetch_water_announcements() -> List[dict]:
    """
    Fetches raw outage announcements from the Veolia Jur website. Returns a list of dictionaries, each with the raw text and source URL.
    """
    log.info(f"Fetching water announcements from {WATER_URL}...")
    announcements = []
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(WATER_URL)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            panels = soup.select('div.items div.panel div.panel-body')
            if not panels:
                log.warning(f"No announcement panels found at {WATER_URL}. Page structure may have changed.")
                return []
            
            for panel_body in panels:
                text_content = panel_body.get_text(separator='\n', strip=True)
                if text_content:
                    announcements.append({"text": text_content, "url": WATER_URL})
            
            log.info(f"Extracted {len(announcements)} raw water announcements.")

    except httpx.RequestError as e:
        log.error(f"HTTP request error fetching water announcements: {e}", exc_info=True)
    except Exception as e:
        log.error(f"General error fetching water announcements: {e}", exc_info=True)
        
    return announcements


async def process_and_store_announcement(announcement: dict):
    """
    Processes a single raw announcement using AI and stores it in the database.
    """
    raw_armenian_text = announcement['text']
    source_url = announcement['url']
    
    english_text = translate_armenian_to_english(raw_armenian_text)
    if not english_text:
        log.warning("Translation failed for a water announcement.")
        return

    entities = extract_entities_from_text(english_text)
    if not entities:
        log.info("No entities found in translated water announcement.")
        return

    structured_data = structure_ner_entities(entities, english_text)

    final_outage_data = {
        "raw_text_hash": get_text_hash(raw_armenian_text),
        "source_type": "water",
        "source_url": source_url,
        "publication_date": None,
        "start_datetime": structured_data.get('start_datetime'),
        "end_datetime": structured_data.get('end_datetime'),
        "status": structured_data.get('status', 'unknown'),
        "regions": structured_data.get('regions', []),
        "streets": structured_data.get('streets', []),
        "details": structured_data.get('details', {})
    }
    
    final_outage_data['details']['armenian_text'] = raw_armenian_text

    await db_manager.add_outage(final_outage_data)
    log.info(f"Stored processed water outage with hash: {final_outage_data['raw_text_hash']}")

async def parse_all_water_announcements_async():
    """
    Main orchestrator function for water parsing. Fetches, processes, and stores all water announcements.
    """
    if not is_ai_available():
        log.error("Cannot parse water announcements: AI models are not available.")
        return

    log.info("Starting full water announcement parsing cycle...")
    raw_announcements = await fetch_water_announcements()
    if not raw_announcements:
        log.info("No new water announcements to process.")
        return
    
    tasks = [process_and_store_announcement(ann) for ann in raw_announcements]
    await asyncio.gather(*tasks)
    
    log.info("Finished water announcement parsing cycle.")

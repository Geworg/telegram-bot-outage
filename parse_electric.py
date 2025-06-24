import logging
import asyncio
import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag
from typing import List, Dict
from ai_engine import is_ai_available, translate_armenian_to_english, extract_entities_from_text
from parsing_utils import get_text_hash, structure_ner_entities
import db_manager

log = logging.getLogger(__name__)

ELECTRIC_URL = "https://www.ena.am/Info.aspx?id=5&lang=1"  # lang=1 is Armenian

async def fetch_electric_announcements() -> List[Dict]:
    """
    Fetches raw outage announcements from the Electric Networks of Armenia website.
    It scrapes both the planned outages text block and the emergency outages table.
    """
    log.info(f"Fetching electric announcements from {ELECTRIC_URL}...")
    announcements = []
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(ELECTRIC_URL)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            planned_span = soup.find('span', id='ctl00_ContentPlaceHolder1_attenbody')
            if planned_span:
                planned_text = planned_span.get_text(separator='\n', strip=True)
                if planned_text:
                    announcements.append({
                        "text": planned_text,
                        "url": ELECTRIC_URL,
                        "type": "planned"
                    })
                    log.info("Extracted planned electricity outage text.")
            else:
                log.warning("Planned electricity outage span not found.")

            emergency_table = soup.find('table', id='ctl00_ContentPlaceHolder1_vtarayin')
            if emergency_table and isinstance(emergency_table, Tag):
                tbody = emergency_table.find('tbody') if isinstance(emergency_table, Tag) else None
                rows = tbody.find_all('tr') if isinstance(tbody, Tag) else []
                log.info(f"Found {len(rows)} rows in the emergency electricity outage table.")
                for row in rows:
                    cells = [cell.get_text(strip=True) for cell in row.find_all('td')] if isinstance(row, Tag) else []
                    row_text = " | ".join(filter(None, cells))
                    if row_text:
                        announcements.append({
                            "text": row_text,
                            "url": ELECTRIC_URL,
                            "type": "emergency"
                        })
                log.info("Finished extracting emergency table rows.")
            else:
                log.warning("Emergency electricity outage table not found.")

    except httpx.RequestError as e:
        log.error(f"HTTP request error fetching electric announcements: {e}", exc_info=True)
    except Exception as e:
        log.error(f"General error fetching electric announcements: {e}", exc_info=True)

    return announcements

async def process_and_store_electric_announcement(announcement: dict):
    """
    Processes a single raw electric announcement using AI and stores it.
    """
    raw_text = announcement['text']
    source_url = announcement['url']
    inferred_type = announcement['type']

    english_text = translate_armenian_to_english(raw_text)
    if not english_text:
        log.warning("Translation failed for an electric announcement.")
        return

    entities = extract_entities_from_text(english_text)
    if not entities:
        log.info("No entities found in translated electric announcement.")
        return

    structured_data = structure_ner_entities(entities, english_text)

    if structured_data.get('status', 'unknown') == 'unknown':
        structured_data['status'] = inferred_type

    final_outage_data = {
        "raw_text_hash": get_text_hash(raw_text),
        "source_type": "electric",
        "source_url": source_url,
        "publication_date": None,
        "start_datetime": structured_data.get('start_datetime'),
        "end_datetime": structured_data.get('end_datetime'),
        "status": structured_data.get('status'),
        "regions": structured_data.get('regions', []),
        "streets": structured_data.get('streets', []),
        "details": structured_data.get('details', {})
    }
    
    final_outage_data['details']['armenian_text'] = raw_text

    await db_manager.add_outage(final_outage_data)
    log.info(f"Stored processed electric outage with hash: {final_outage_data['raw_text_hash']}")

async def parse_all_electric_announcements_async():
    """
    Main orchestrator function for electricity parsing.
    """
    if not is_ai_available():
        log.error("Cannot parse electric announcements: AI models are not available.")
        return

    log.info("Starting full electric announcement parsing cycle...")
    raw_announcements = await fetch_electric_announcements()
    
    if not raw_announcements:
        log.info("No new electric announcements to process.")
        return
        
    tasks = [process_and_store_electric_announcement(ann) for ann in raw_announcements]
    await asyncio.gather(*tasks)
    
    log.info("Finished electric announcement parsing cycle.")

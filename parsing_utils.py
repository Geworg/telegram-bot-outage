import logging
import pytz
import hashlib
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

log = logging.getLogger(__name__)

YEREVAN_TZ = pytz.timezone("Asia/Yerevan")

def get_text_hash(text: str) -> str:
    """Creates a SHA256 hash for a given string to act as a unique ID."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def parse_dates_and_times_from_entities(entities: List[Dict[str, Any]], original_text: str) -> Dict[str, Optional[datetime]]:
    """
    A sophisticated function to find start and end datetimes from NER entities and raw text.
    Handles various formats like "June 15, from 10:00 to 18:00" and "24.06.2025 23:50".

    Args:
        entities: A list of entity dicts from the NER model.
        original_text: The original English text for context.

    Returns:
        A dictionary containing 'start_datetime' and 'end_datetime'.
    """
    dates = [e['word'] for e in entities if e['entity_group'] in ['DATE', 'TIME'] or (e['entity_group'] == 'CARDINAL' and re.match(r'\d{1,2}:\d{2}', e['word']))]
    times = sorted(re.findall(r'(\d{1,2}:\d{2})', original_text))
    start_dt, end_dt = None, None
    try:
        dt_matches = re.findall(r'(\d{2}\.\d{2}\.\d{4})[\s|,]*(\d{1,2}:\d{2})?', original_text)
        if dt_matches:
            if len(dt_matches) >= 2:
                start_str, start_time = dt_matches[0]
                end_str, end_time = dt_matches[1]
                if start_time:
                    start_dt = datetime.strptime(f"{start_str} {start_time}", "%d.%m.%Y %H:%M")
                else:
                    start_dt = datetime.strptime(start_str, "%d.%m.%Y")
                if end_time:
                    end_dt = datetime.strptime(f"{end_str} {end_time}", "%d.%m.%Y %H:%M")
                else:
                    end_dt = datetime.strptime(end_str, "%d.%m.%Y")
            elif len(dt_matches) == 1:
                date_str, first_time = dt_matches[0]
                found_times = re.findall(r'(\d{1,2}:\d{2})', original_text)
                if len(found_times) >= 2:
                    start_dt = datetime.strptime(f"{date_str} {found_times[0]}", "%d.%m.%Y %H:%M")
                    end_dt = datetime.strptime(f"{date_str} {found_times[1]}", "%d.%m.%Y %H:%M")
                elif first_time:
                    start_dt = datetime.strptime(f"{date_str} {first_time}", "%d.%m.%Y %H:%M")
        if not start_dt and len(times) >= 2:
            date_match = re.search(r'(\w+\s\d{1,2})', original_text, re.IGNORECASE)
            if date_match:
                date_str = date_match.group(1)
                now = datetime.now(YEREVAN_TZ)
                start_datetime_str = f"{date_str} {now.year} {times[0]}"
                end_datetime_str = f"{date_str} {now.year} {times[1]}"
                start_dt = datetime.strptime(start_datetime_str, "%B %d %Y %H:%M")
                end_dt = datetime.strptime(end_datetime_str, "%B %d %Y %H:%M")
                start_dt = YEREVAN_TZ.localize(start_dt)
                end_dt = YEREVAN_TZ.localize(end_dt)
    except Exception as e:
        log.warning(f"Could not parse datetime from text: '{original_text}'. Error: {e}")
    return {
        'start_datetime': start_dt,
        'end_datetime': end_dt
    }

def structure_ner_entities(entities: List[Dict[str, Any]], original_english_text: str) -> Dict[str, Any]:
    """
    Processes a list of NER entities to build a structured outage dictionary.
    
    Args:
        entities: The list of entities from the NER pipeline.
        original_english_text: The English text the entities were extracted from.

    Returns:
        A dictionary with structured data like regions, streets, and other details.
    """
    structured_data = {
        "regions": [],
        "streets": [],
        "organizations": [],
        "persons": [],
        "misc": [],
        "locations": [],
        "details": {"english_text": original_english_text},
        "start_datetime": None,
        "end_datetime": None,
        "status": "unknown"
    }

    for entity in entities:
        entity_group = entity.get('entity_group')
        word = entity.get('word')
        
        if not entity_group or not word:
            continue

        if entity_group == 'LOC':
            structured_data['locations'].append(word)
        elif entity_group == 'ORG':
            structured_data['organizations'].append(word)
        elif entity_group == 'PER':
            structured_data['persons'].append(word)
        elif entity_group == 'MISC':
            structured_data['misc'].append(word)
    
    structured_data['regions'] = structured_data['locations']
    structured_data['streets'] = structured_data['locations']

    date_info = parse_dates_and_times_from_entities(entities, original_english_text)
    structured_data.update(date_info)
    
    if "planned" in original_english_text.lower():
        structured_data['status'] = 'planned'
    elif "emergency" in original_english_text.lower() or "accident" in original_english_text.lower():
        structured_data['status'] = 'emergency'
    else:
        structured_data['status'] = 'unknown'

    return structured_data

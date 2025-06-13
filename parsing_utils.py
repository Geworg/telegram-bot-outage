import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pytz

# Configure logger for this module
log = logging.getLogger(__name__)

# Assume the bot operates in Yerevan time when interpreting ambiguous dates/times
YEREVAN_TZ = pytz.timezone("Asia/Yerevan")

def get_text_hash(text: str) -> str:
    """Creates a SHA256 hash for a given string to act as a unique ID."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def parse_dates_and_times_from_entities(entities: List[Dict[str, Any]], original_text: str) -> Dict[str, Optional[datetime]]:
    """
    A sophisticated function to find start and end datetimes from NER entities and raw text.
    Handles various formats like "June 15, from 10:00 to 18:00".

    Args:
        entities: A list of entity dicts from the NER model.
        original_text: The original English text for context.

    Returns:
        A dictionary containing 'start_datetime' and 'end_datetime'.
    """
    # This is a complex task. The NER model might give us "June 15", "10:00", and "18:00" separately.
    # We need to combine them intelligently.

    # Simplified example logic:
    # A real-world implementation would need to be much more robust, handling ranges,
    # different months, years, etc. This is a good starting point.
    
    dates = [e['word'] for e in entities if e['entity_group'] in ['DATE', 'TIME'] or (e['entity_group'] == 'CARDINAL' and re.match(r'\d{1,2}:\d{2}', e['word']))]
    
    # Placeholder logic: Find times and a date
    times = sorted(re.findall(r'(\d{1,2}:\d{2})', original_text))
    
    # This is highly heuristic.
    # A production system would use a more advanced date parsing library
    # or more complex regex to handle all cases found in the source websites.
    start_dt, end_dt = None, None
    
    try:
        # Very basic assumption: first time is start, second is end.
        if len(times) >= 2:
            # We need a date. 
            # Let's find one in the text.
            # This logic is extremely simplified.
            date_match = re.search(r'(\w+\s\d{1,2})', original_text, re.IGNORECASE) # e.g., "June 15"
            if date_match:
                date_str = date_match.group(1)
                now = datetime.now(YEREVAN_TZ)
                
                start_datetime_str = f"{date_str} {now.year} {times[0]}"
                end_datetime_str = f"{date_str} {now.year} {times[1]}"
                
                # Try to parse the constructed string
                start_dt = datetime.strptime(start_datetime_str, "%B %d %Y %H:%M")
                end_dt = datetime.strptime(end_datetime_str, "%B %d %Y %H:%M")
                
                # Localize to Yerevan timezone
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
        "details": {} # For extra unstructured info
    }

    for entity in entities:
        entity_group = entity.get('entity_group')
        word = entity.get('word')
        
        if not entity_group or not word:
            continue

        # Simple mapping based on entity type
        if entity_group == 'LOC':
            structured_data['locations'].append(word)
        elif entity_group == 'ORG':
            structured_data['organizations'].append(word)
        elif entity_group == 'PER':
            structured_data['persons'].append(word)
        elif entity_group == 'MISC':
            structured_data['misc'].append(word)
    
    # Heuristic to separate regions and streets from 'locations'
    # In a real scenario, this would need a known list of Armenian regions/cities for better accuracy.
    # For now, we'll assume locations might contain both.
    # This is a place for significant improvement.
    structured_data['regions'] = structured_data['locations'] # Simplified for now
    structured_data['streets'] = structured_data['locations']  # Simplified for now

    # Extract dates and times
    date_info = parse_dates_and_times_from_entities(entities, original_english_text)
    structured_data.update(date_info)
    
    # Simple logic for status
    if "planned" in original_english_text.lower():
        structured_data['status'] = 'planned'
    elif "emergency" in original_english_text.lower() or "accident" in original_english_text.lower():
        structured_data['status'] = 'emergency'
    else:
        structured_data['status'] = 'unknown'

    # Add the full text as a detail
    structured_data['details']['english_text'] = original_english_text

    return structured_data

# <3
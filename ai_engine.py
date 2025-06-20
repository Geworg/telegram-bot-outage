import os
import logging
import httpx # Import httpx for making HTTP requests
from typing import List, Dict, Any, Optional

# Commented out local transformer imports
# try:
#     from transformers import pipeline, MarianMTModel, MarianTokenizer, AutoTokenizer, AutoModelForTokenClassification
#     import torch
#     TRANSFORMERS_AVAILABLE = True
# except ImportError:
#     TRANSFORMERS_AVAILABLE = False

# Assume TRANSFORMERS_AVAILABLE is always False since we are moving to API calls
TRANSFORMERS_AVAILABLE = False

# os.environ["TRANSFORMERS_CACHE"] = "/tmp/huggingface" # No longer needed for API
trans_model_name = os.getenv("TRANSLATION_MODEL", "Helsinki-NLP/opus-mt-hy-en")
ner_model_name = os.getenv("NER_MODEL", "dslim/bert-base-NER")

log = logging.getLogger(__name__)

# --- Global Model Storage / API Client Configuration ---
# These are initialized as None and configured by the `load_models` function.
# Instead of pipelines, we'll configure HTTP clients and API keys.
hf_translation_api_key = None
hf_ner_api_key = None
models_loaded = False # Now indicates if API keys are configured

# Hugging Face Inference API endpoints
HF_TRANSLATION_API_URL = f"https://api-inference.huggingface.co/models/{trans_model_name}"
HF_NER_API_URL = f"https://api-inference.huggingface.co/models/{ner_model_name}"

async def load_models():
    """
    Loads Hugging Face API keys from environment variables.
    This function should be called once when the bot application starts.
    """
    global hf_translation_api_key, hf_ner_api_key, models_loaded

    if models_loaded:
        log.info("Hugging Face API keys are already loaded.")
        return

    log.info("Loading Hugging Face API keys...")
    
    hf_translation_api_key = os.getenv("TRANSLATION_API_KEY")
    hf_ner_api_key = os.getenv("NER_API_KEY")

    if not hf_translation_api_key:
        log.critical("TRANSLATION_API_KEY is not set. Translation feature is disabled.")
    if not hf_ner_api_key:
        log.critical("NER_API_KEY is not set. NER feature is disabled.")

    if hf_translation_api_key and hf_ner_api_key:
        models_loaded = True
        log.info("All Hugging Face API keys have been loaded and are ready.")
    else:
        models_loaded = False
        log.error("Missing one or more Hugging Face API keys. AI features will be disabled.")


def is_ai_available() -> bool:
    """Checks if the necessary Hugging Face API keys have been loaded successfully."""
    return models_loaded


async def translate_armenian_to_english(text: str) -> Optional[str]:
    """Translates a string of Armenian text to English using the Hugging Face Inference API."""
    if not is_ai_available() or not hf_translation_api_key:
        log.error("Translation API key is not available, cannot process text.")
        return None
    
    headers = {"Authorization": f"Bearer {hf_translation_api_key}"}
    payload = {"inputs": text}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(HF_TRANSLATION_API_URL, headers=headers, json=payload)
            response.raise_for_status() # Raise an exception for bad status codes
            
            result = response.json()
            # The translation API usually returns a list of dicts, e.g., [{'translation_text': '...'}]
            return result[0]['translation_text'] if result and isinstance(result, list) and result[0].get('translation_text') else None
    except httpx.RequestError as e:
        log.error(f"HTTP request error during translation: {e}", exc_info=True)
        return None
    except Exception as e:
        log.error(f"An error occurred during translation: {e}", exc_info=True)
        return None

async def extract_entities_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extracts named entities (like Dates, Locations, Organizations) from English text
    using the Hugging Face Inference API.

    Args:
        text (str): The English text to be processed.

    Returns:
        A list of dictionaries, where each dictionary represents an entity.
        Example (API output might vary slightly, will need adaptation):
        [
            {'entity_group': 'LOC', 'score': 0.99, 'word': 'Yerevan'},
            {'entity_group': 'MISC', 'score': 0.95, 'word': 'Veolia Jur'},
            {'entity_group': 'DATE', 'score': 0.89, 'word': 'June 15'}
        ]
    """
    if not is_ai_available() or not hf_ner_api_key:
        log.error("NER API key is not available, cannot extract entities.")
        return []
    
    headers = {"Authorization": f"Bearer {hf_ner_api_key}"}
    payload = {"inputs": text}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(HF_NER_API_URL, headers=headers, json=payload)
            response.raise_for_status() # Raise an exception for bad status codes
            
            entities = response.json()
            # The NER model "dslim/bert-base-NER" returns a list of entities like:
            # [{'entity_group': 'LOC', 'score': 0.99, 'word': 'Yerevan', 'start': 0, 'end': 7}]
            return entities
    except httpx.RequestError as e:
        log.error(f"HTTP request error during entity extraction: {e}", exc_info=True)
        return []
    except Exception as e:
        log.error(f"An error occurred during entity extraction: {e}", exc_info=True)
        return []

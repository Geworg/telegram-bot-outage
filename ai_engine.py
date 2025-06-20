import os
import logging
from typing import List, Dict, Any, Optional
import httpx # New import for API calls

log = logging.getLogger(__name__)

# --- API Endpoints and Keys ---
# Using Hugging Face Inference API as a default assumption.
# These can be customized in the .env file.
TRANSLATION_API_URL = os.getenv("TRANSLATION_API_URL", "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-hy-en")
NER_API_URL = os.getenv("NER_API_URL", "https://api-inference.huggingface.co/models/dslim/bert-base-NER")

TRANSLATION_API_KEY = os.getenv("TRANSLATION_API_KEY")
NER_API_KEY = os.getenv("NER_API_KEY")

# Flag to indicate if API keys are available. Replaces models_loaded.
api_available = False

def initialize_api_status():
    """Checks if API keys are set and updates the api_available status."""
    global api_available
    if not TRANSLATION_API_KEY:
        log.warning("TRANSLATION_API_KEY is not set. Translation functionality may be limited or unavailable.")
    if not NER_API_KEY:
        log.warning("NER_API_KEY is not set. NER functionality may be limited or unavailable.")
    
    api_available = bool(TRANSLATION_API_KEY and NER_API_KEY) # Both must be present for full AI functionality
    if api_available:
        log.info("AI API keys are available.")
    else:
        log.warning("AI API keys are missing or incomplete. AI features will be disabled.")


# --- Commented out old local model loading code ---
# try:
#     from transformers import pipeline, MarianMTModel, MarianTokenizer, AutoTokenizer, AutoModelForTokenClassification
#     import torch
#     TRANSFORMERS_AVAILABLE = True
# except ImportError:
#     TRANSFORMERS_AVAILABLE = False

# os.environ["TRANSFORMERS_CACHE"] = "/tmp/huggingface"
# trans_model_name = os.getenv("TRANSLATION_MODEL", "Helsinki-NLP/opus-mt-hy-en")
# ner_model_name = os.getenv("NER_MODEL", "dslim/bert-base-NER")

# translator_pipeline = None
# ner_pipeline = None
# models_loaded = False

# def load_models():
#     """
#     Loads the Hugging Face models for translation and NER into memory.
#     This function should be called once when the bot application starts.
#     It checks for GPU availability for better performance.
#     """
#     global translator_pipeline, ner_pipeline, models_loaded

#     if not TRANSFORMERS_AVAILABLE:
#         log.critical("The 'transformers' or 'torch' library is not installed. AI features are disabled.")
#         return

#     if models_loaded:
#         log.info("AI models are already loaded.")
#         return

#     log.info("Loading AI models. This may take a moment...")
#     try:
#         # Check if a CUDA-enabled GPU is available, otherwise use CPU (-1)
#         device = 0 if torch.cuda.is_available() else -1
#         device_name = torch.cuda.get_device_name(0) if device == 0 else "CPU"
#         log.info(f"AI models will be loaded on device: {device_name}")

#         # 1. Load Translation Model (Armenian to English)
#         trans_model_name = "Helsinki-NLP/opus-mt-hy-en"
#         log.info(f"Loading translation model: {trans_model_name}...")
#         translator_pipeline = pipeline(
#             "translation",
#             model=trans_model_name,
#             device=device
#         )
#         log.info("Translation model loaded successfully.")

#         # 2. Load Named Entity Recognition (NER) Model
#         ner_model_name = "dslim/bert-base-NER"
#         log.info(f"Loading NER model: {ner_model_name}...")
#         ner_pipeline = pipeline(
#             "ner",
#             model=ner_model_name,
#             aggregation_strategy="simple", # Groups sub-words (e.g., "New", "York" -> "New York")
#             device=device
#         )
#         log.info("NER model loaded successfully.")

#         models_loaded = True
#         log.info("All AI models have been loaded and are ready.")

#     except Exception as e:
#         log.critical(f"A critical error occurred while loading AI models: {e}", exc_info=True)
#         # Ensure we don't partially load models
#         translator_pipeline = None
#         ner_pipeline = None
#         models_loaded = False
# --- End of commented out local model loading code ---


def is_ai_available() -> bool:
    """Checks if the necessary AI API keys are configured."""
    return api_available

async def translate_armenian_to_english(text: str) -> Optional[str]:
    """Translates a string of Armenian text to English using an external API."""
    if not is_ai_available() or not TRANSLATION_API_KEY:
        log.error("Translation API key is not available, cannot process text.")
        return None
    
    headers = {"Authorization": f"Bearer {TRANSLATION_API_KEY}"}
    payload = {"inputs": text}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(TRANSLATION_API_URL, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status() # Raise an exception for 4xx or 5xx responses
            result = response.json()
            
            # Hugging Face Inference API for translation typically returns a list of dicts:
            # [{'translation_text': '...'}]
            return result[0]['translation_text'] if result and isinstance(result, list) and result[0].get('translation_text') else None
        except httpx.HTTPStatusError as e:
            log.error(f"Translation API HTTP error {e.response.status_code}: {e.response.text}")
            return None
        except httpx.RequestError as e:
            log.error(f"Network error or request timeout calling Translation API: {e}", exc_info=True)
            return None
        except Exception as e:
            log.error(f"Unexpected error during translation API call: {e}", exc_info=True)
            return None

async def extract_entities_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extracts named entities from English text using an external API.

    Args:
        text (str): The English text to be processed.

    Returns:
        A list of dictionaries, where each dictionary represents an entity.
        Example (might vary slightly based on specific API output):
        [
            {'entity_group': 'LOC', 'score': 0.99, 'word': 'Yerevan'},
            {'entity_group': 'MISC', 'score': 0.95, 'word': 'Veolia Jur'},
            {'entity_group': 'DATE', 'score': 0.89, 'word': 'June 15'}
        ]
    """
    if not is_ai_available() or not NER_API_KEY:
        log.error("NER API key is not available, cannot extract entities.")
        return []

    headers = {"Authorization": f"Bearer {NER_API_KEY}"}
    payload = {"inputs": text}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(NER_API_URL, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status() # Raise an exception for 4xx or 5xx responses
            result = response.json()
            
            # Hugging Face Inference API for NER typically returns a list of entity dicts:
            # [{'entity_group': 'LOC', 'score': 0.99, 'word': 'Yerevan', ...}, ...]
            return result if result and isinstance(result, list) else []
        except httpx.HTTPStatusError as e:
            log.error(f"NER API HTTP error {e.response.status_code}: {e.response.text}")
            return []
        except httpx.RequestError as e:
            log.error(f"Network error or request timeout calling NER API: {e}", exc_info=True)
            return []
        except Exception as e:
            log.error(f"Unexpected error during NER API call: {e}", exc_info=True)
            return []

# Removed: initialize_api_status() from module level. This will now be called explicitly in smart_bot.py's post_init.
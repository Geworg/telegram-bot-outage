import os
import logging
from typing import List, Dict, Any, Optional
try:
    from transformers import pipeline, MarianMTModel, MarianTokenizer, AutoTokenizer, AutoModelForTokenClassification
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

os.environ["TRANSFORMERS_CACHE"] = "/tmp/huggingface"
trans_model_name = os.getenv("TRANSLATION_MODEL", "Helsinki-NLP/opus-mt-hy-en")
ner_model_name = os.getenv("NER_MODEL", "dslim/bert-base-NER")

log = logging.getLogger(__name__)

# --- Global Model Storage ---
# These are initialized as None and loaded by the `load_models` function.
translator_pipeline = None
ner_pipeline = None
models_loaded = False

def load_models():
    """
    Loads the Hugging Face models for translation and NER into memory.
    This function should be called once when the bot application starts.
    It checks for GPU availability for better performance.
    """
    global translator_pipeline, ner_pipeline, models_loaded

    if not TRANSFORMERS_AVAILABLE:
        log.critical("The 'transformers' or 'torch' library is not installed. AI features are disabled.")
        return

    if models_loaded:
        log.info("AI models are already loaded.")
        return

    log.info("Loading AI models. This may take a moment...")
    try:
        # Check if a CUDA-enabled GPU is available, otherwise use CPU (-1)
        device = 0 if torch.cuda.is_available() else -1
        device_name = torch.cuda.get_device_name(0) if device == 0 else "CPU"
        log.info(f"AI models will be loaded on device: {device_name}")

        # 1. Load Translation Model (Armenian to English)
        trans_model_name = "Helsinki-NLP/opus-mt-hy-en"
        log.info(f"Loading translation model: {trans_model_name}...")
        translator_pipeline = pipeline(
            "translation",
            model=trans_model_name,
            device=device
        )
        log.info("Translation model loaded successfully.")

        # 2. Load Named Entity Recognition (NER) Model
        ner_model_name = "dslim/bert-base-NER"
        log.info(f"Loading NER model: {ner_model_name}...")
        ner_pipeline = pipeline(
            "ner",
            model=ner_model_name,
            aggregation_strategy="simple", # Groups sub-words (e.g., "New", "York" -> "New York")
            device=device
        )
        log.info("NER model loaded successfully.")

        models_loaded = True
        log.info("All AI models have been loaded and are ready.")

    except Exception as e:
        log.critical(f"A critical error occurred while loading AI models: {e}", exc_info=True)
        # Ensure we don't partially load models
        translator_pipeline = None
        ner_pipeline = None
        models_loaded = False

def is_ai_available() -> bool:
    """Checks if the necessary AI models have been loaded successfully."""
    return models_loaded

def translate_armenian_to_english(text: str) -> Optional[str]:
    """Translates a string of Armenian text to English using the loaded pipeline."""
    if not is_ai_available() or not translator_pipeline:
        log.error("Translation model is not available, cannot process text.")
        return None
    try:
        # The pipeline returns a list of dictionaries, e.g., [{'translation_text': '...'}]
        result = translator_pipeline(text)
        return result[0]['translation_text'] if result else None
    except Exception as e:
        log.error(f"An error occurred during translation: {e}", exc_info=True)
        return None

def extract_entities_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extracts named entities (like Dates, Locations, Organizations) from English text.

    Args:
        text (str): The English text to be processed.

    Returns:
        A list of dictionaries, where each dictionary represents an entity.
        Example:
        [
            {'entity_group': 'LOC', 'score': 0.99, 'word': 'Yerevan'},
            {'entity_group': 'MISC', 'score': 0.95, 'word': 'Veolia Jur'},
            {'entity_group': 'DATE', 'score': 0.89, 'word': 'June 15'}
        ]
    """
    if not is_ai_available() or not ner_pipeline:
        log.error("NER model is not available, cannot extract entities.")
        return []
    try:
        entities = ner_pipeline(text)
        return entities
    except Exception as e:
        log.error(f"An error occurred during entity extraction: {e}", exc_info=True)
        return []
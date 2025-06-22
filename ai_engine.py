import os
import logging
import requests
from typing import List, Dict, Any, Optional

log = logging.getLogger(__name__)

TRANSLATION_API_KEY = os.getenv("TRANSLATION_API_KEY")
TRANSLATION_MODEL = os.getenv("TRANSLATION_MODEL", "Helsinki-NLP/opus-mt-hy-en")
NER_API_KEY = os.getenv("NER_API_KEY")
NER_MODEL = os.getenv("NER_MODEL", "dslim/bert-base-NER")

# --- Global Model Storage ---
# Локальные пайплайны и torch больше не используются, теперь только API
# translator_pipeline = None
# ner_pipeline = None
# models_loaded = False

def load_models():
    """
    (Больше не требуется.)
    Оставлено для совместимости. Теперь модели загружаются через API Hugging Face.
    """
    log.info("AI models are now accessed via Hugging Face API. No local loading required.")
    return

def is_ai_available() -> bool:
    """
    Проверяет, заданы ли API-ключи для Hugging Face.
    """
    return bool(TRANSLATION_API_KEY and NER_API_KEY)

def translate_armenian_to_english(text: str) -> Optional[str]:
    """
    Переводит армянский текст на английский через Hugging Face API (NLLB-200).
    """
    if not TRANSLATION_API_KEY:
        log.error("TRANSLATION_API_KEY is not set.")
        return None
    try:
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{TRANSLATION_MODEL}",
            headers={"Authorization": f"Bearer {TRANSLATION_API_KEY}"},
            json={
                "inputs": text,
                "parameters": {
                    "src_lang": "armn",  # армянский
                    "tgt_lang": "eng_Latn"  # английский (латиница)
                }
            }
        )
        response.raise_for_status()
        data = response.json()
        # NLLB-200 возвращает {'translation_text': '...'} или [{'translation_text': '...'}]
        if isinstance(data, dict) and 'translation_text' in data:
            return data['translation_text']
        elif isinstance(data, list) and data and 'translation_text' in data[0]:
            return data[0]['translation_text']
        elif isinstance(data, dict) and 'error' in data:
            log.error(f"Translation API error: {data['error']}")
            return None
        else:
            log.error(f"Unexpected translation API response: {data}")
            return None
    except Exception as e:
        log.error(f"Translation API call failed: {e}", exc_info=True)
        return None

def extract_entities_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Извлекает именованные сущности из английского текста через Hugging Face API.
    """
    if not NER_API_KEY:
        log.error("NER_API_KEY is not set.")
        return []
    try:
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{NER_MODEL}",
            headers={"Authorization": f"Bearer {NER_API_KEY}"},
            json={"inputs": text}
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and 'error' in data:
            log.error(f"NER API error: {data['error']}")
            return []
        else:
            log.error(f"Unexpected NER API response: {data}")
            return []
    except Exception as e:
        log.error(f"NER API call failed: {e}", exc_info=True)
        return []
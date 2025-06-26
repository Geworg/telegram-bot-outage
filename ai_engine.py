import os
import logging
import requests
from typing import List, Dict, Any, Optional
from deep_translator import GoogleTranslator

log = logging.getLogger(__name__)

NER_API_KEY = os.getenv("NER_API_KEY")
NER_MODEL = os.getenv("NER_MODEL", "dslim/bert-base-NER")

def load_models():
    """
    Оставлено для совместимости. Теперь модели загружаются через API Hugging Face.
    """
    log.info("AI models are now accessed via Hugging Face API. No local loading required.")
    return

def is_ai_available() -> bool:
    """
    Проверяет, задан ли API-ключ для Hugging Face NER (переводчик теперь не требует ключа).
    """
    return bool(NER_API_KEY)

def translate_armenian_to_english(text: str) -> Optional[str]:
    """
    Переводит армянский текст на английский через Google Translate (deep-translator).
    Возвращает None при ошибке.
    """
    try:
        translated = GoogleTranslator(source='hy', target='en').translate(text)
        if not translated or not isinstance(translated, str):
            log.error(f"GoogleTranslator returned empty or invalid result for: {text}")
            return None
        return translated
    except Exception as e:
        log.error(f"GoogleTranslator translation failed: {e}", exc_info=True)
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
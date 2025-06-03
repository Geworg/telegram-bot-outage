from llama_cpp import Llama
import logging
import os
import json
import re
import asyncio

# --- Конфигурация модели ---
MODEL_FILENAME = os.getenv("LLAMA_MODEL_FILENAME", "phi-2.q4_k_m.gguf") # IMPROVEMENT: Get from .env
MODELS_DIR = os.getenv("MODELS_PATH", ".") # Default to current directory if not set
MODEL_PATH = os.path.join(MODELS_DIR, MODEL_FILENAME)
N_CTX = int(os.getenv("LLAMA_N_CTX", 2048))
N_THREADS = int(os.getenv("LLAMA_N_THREADS", os.cpu_count() or 2)) # IMPROVEMENT: Default to available CPUs or 2
VERBOSE_LLAMA = os.getenv("LLAMA_VERBOSE", "False").lower() == "true"
LLM_MAX_TOKENS_PARSE = int(os.getenv("LLM_MAX_TOKENS_PARSE", 500)) # IMPROVEMENT: Configurable max_tokens for parsing
LLM_TEMPERATURE_PARSE = float(os.getenv("LLM_TEMPERATURE_PARSE", 0.2)) # IMPROVEMENT: Configurable temperature for parsing
LLM_MAX_TOKENS_ADDRESS = int(os.getenv("LLM_MAX_TOKENS_ADDRESS", 300)) # IMPROVEMENT: Configurable max_tokens for address
LLM_TEMPERATURE_ADDRESS = float(os.getenv("LLM_TEMPERATURE_ADDRESS", 0.3)) # IMPROVEMENT: Configurable temperature for address

# --- Инициализация LLM ---
llm_instance = None
try:
    if os.path.exists(MODEL_PATH):
        llm_instance = Llama(
            model_path=MODEL_PATH,
            n_ctx=N_CTX,
            n_threads=N_THREADS,
            verbose=VERBOSE_LLAMA
        )
        logging.info(f"LLaMA model loaded successfully from {MODEL_PATH} with n_ctx={N_CTX}, n_threads={N_THREADS}")
    else:
        logging.error(f"LLaMA model file not found at {MODEL_PATH}. AI features will be disabled.")
except Exception as e:
    logging.error(f"Failed to load LLaMA model: {e}", exc_info=True)
    llm_instance = None

def is_ai_available() -> bool:
    """Проверяет, доступна ли модель LLM."""
    return llm_instance is not None

def ask_model_sync(prompt: str, max_tokens: int, temperature: float) -> str:
    """
    Синхронная функция для запроса к модели.
    Вызывается из асинхронного кода через run_in_executor.
    """
    if not llm_instance:
        logging.error("LLM model is not loaded. Cannot process AI request.")
        return json.dumps({"error": "LLM model not loaded", "comment": "AI features are disabled."})
    try:
        logging.debug(f"Sending prompt to LLM (sync): Max tokens: {max_tokens}, Temp: {temperature}\nPrompt: {prompt[:500]}...") # Log a snippet
        response = llm_instance(prompt, max_tokens=max_tokens, temperature=temperature, stop=["\n\n"]) # type: ignore
        output_text = response['choices'][0]['text'].strip() if response and response['choices'] else ""
        logging.debug(f"LLM raw response (sync): {output_text[:500]}...") # Log a snippet
        return output_text
    except Exception as e:
        logging.error(f"Error during LLM call (sync): {e}", exc_info=True)
        return json.dumps({"error": "LLM call failed", "comment": str(e)})

async def ask_model(prompt: str, max_tokens: int, temperature: float) -> str:
    """
    Асинхронная обертка для запроса к модели LLM.
    LlamaCPP работает синхронно, поэтому используем run_in_executor.
    """
    if not is_ai_available():
        logging.error("LLM model is not loaded. Cannot process AI request.")
        return json.dumps({"error": "LLM model not loaded", "comment": "AI features are disabled."})

    loop = asyncio.get_event_loop()
    try:
        raw_json_output = await loop.run_in_executor(
            None,
            ask_model_sync,
            prompt,
            max_tokens,
            temperature
        )
        return raw_json_output
    except Exception as e:
        logging.error(f"Error running LLM call in executor: {e}", exc_info=True)
        return json.dumps({"error": "LLM executor failed", "comment": str(e)})

async def structure_text_with_ai_async(text_content: str, prompt_template: str) -> dict:
    """
    Асинхронно структурирует текст с помощью AI, используя предоставленный шаблон промпта.
    """
    if not is_ai_available():
        return {"error": "AI not available", "original_text": text_content}
    prompt = prompt_template.format(text_content=text_content)
    raw_json_output = await ask_model(prompt, LLM_MAX_TOKENS_PARSE, LLM_TEMPERATURE_PARSE)
    logging.info(f"LLM RAW JSON output for structuring: '{raw_json_output[:200]}...'") # Log snippet
    try:
        match = re.search(r'```json\s*(\{.*?\})\s*```', raw_json_output, re.DOTALL)
        if not match:
            match = re.search(r'(\{.*?\})', raw_json_output, re.DOTALL)
        if match:
            cleaned_json_string = match.group(1)
            parsed_data = json.loads(cleaned_json_string)
            if "original_text" not in parsed_data:
                parsed_data["original_text"] = text_content
            if "error" in parsed_data:
                 logging.error(f"LLM returned an error structure: {parsed_data}")
            return parsed_data
        else:
            logging.warning(f"No JSON object found in LLM output for structuring. Output: {raw_json_output}")
            return {"error": "AI response format error", "comment": "AI did not return valid JSON.", "original_text": text_content, "raw_output": raw_json_output}
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON from LLM for structuring. Error: {e}. Output: {raw_json_output}")
        return {"error": "AI response JSON decode error", "comment": f"AI response was not valid JSON: {raw_json_output}", "original_text": text_content}
    except Exception as e:
        logging.error(f"Unexpected error processing LLM output for structuring: {e}", exc_info=True)
        return {"error": "Unexpected AI processing error", "comment": str(e), "original_text": text_content, "raw_output": raw_json_output}

async def clarify_address_ai(raw_address_text: str, region_street_map: Optional[dict] = None) -> dict:
    """
    Уточняет адрес с помощью AI.
    region_street_map (необязательно): предзагруженная карта регионов/улиц для возможной валидации.
    """
    if not is_ai_available():
        return {"original_input": raw_address_text, "error": "AI not available"}
    # IMPROVEMENT: Более сложный промпт, включающий примеры и указание на языки
    prompt = f"""
You are an address recognition assistant for Armenia.
Your task is to parse the user's input, which might be in Armenian, Russian, or English (including transliterated versions), and may contain typos or be incomplete.
The user wants to specify an address in Armenia. Identify the region (marz or Yerevan district) and the street.
If the input is very vague or clearly not an address, indicate that.

User input: "{raw_address_text}"

Desired JSON output format:
{{
  "original_input": "{raw_address_text}",
  "region_identified": "Name of the region or Yerevan district (e.g., 'Ереван', 'Арабкир', 'Котайк', 'Лорийская область')",
  "street_identified": "Name of the street (e.g., 'ул. Абовяна', 'Баграмяна', 'Саят-Нова')",
  "certainty": "high/medium/low (your assessment of how certain you are about the identified parts)",
  "error_comment": "null (or a brief explanation if parsing failed or input is ambiguous, e.g., 'Too vague', 'Street not found in typical Armenian context')"
}}

If the input provides specific building numbers, you can ignore them for this task, focus on region and street.
If multiple interpretations are possible, choose the most likely one for Armenia.
Prioritize Armenian regions and cities. For Yerevan, specify the administrative district if possible (e.g., Kentron, Arabkir, Shengavit), otherwise just 'Yerevan' or 'Ереван'.

Respond ONLY with a single JSON object.
"""
    # logging.info(f"Clarifying address with AI. Prompt: {prompt}") # Can be verbose
    raw_json_output = await ask_model(prompt, LLM_MAX_TOKENS_ADDRESS, LLM_TEMPERATURE_ADDRESS)
    logging.info(f"LLM RAW JSON output for address clarification: '{raw_json_output}'")
    try:
        match = re.search(r'```json\s*(\{.*?\})\s*```', raw_json_output, re.DOTALL)
        if not match:
            match = re.search(r'(\{.*?\})', raw_json_output, re.DOTALL)
        if match:
            cleaned_json_string = match.group(1)
            parsed_data = json.loads(cleaned_json_string)
            if "original_input" not in parsed_data: # Ensure original input is always there
                parsed_data["original_input"] = raw_address_text
            # IMPROVEMENT: Basic validation against region_street_map if provided
            if region_street_map and "region_identified" in parsed_data and parsed_data["region_identified"]:
                # This is a placeholder for more complex validation logic
                # For example, check if parsed_data["region_identified"] is a key in region_street_map
                # Or if parsed_data["street_identified"] is in the list of streets for that region.
                # This could adjust the "certainty" or add a comment.
                logging.debug(f"Address Clarification: AI output {parsed_data}, region_street_map available for potential cross-check.")

            return parsed_data
        else:
            logging.warning(f"No JSON object found in LLM output for address clarification. Output: {raw_json_output}")
            return {"original_input": raw_address_text, "error": "AI response format error", "comment": "AI did not return valid JSON.", "raw_output": raw_json_output}
    except json.JSONDecodeError:
        logging.error(f"Failed to decode JSON from LLM for address clarification. Output: {raw_json_output}")
        return {"original_input": raw_address_text, "error": "AI response JSON decode error", "comment": f"AI response was not valid JSON: {raw_json_output}"}
    except Exception as e:
        logging.error(f"Unexpected error processing LLM output for address clarification: {e}", exc_info=True)
        return {"original_input": raw_address_text, "error": "Unexpected AI processing error", "comment": str(e), "raw_output": raw_json_output}

# <3
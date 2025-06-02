# ai_engine.py
from llama_cpp import Llama
import logging # Рекомендуется добавить логирование

# Инициализация модели один раз
# Рассмотрите возможность вынести model_path и n_ctx в конфигурацию (например, .env файл)
MODEL_PATH = "phi-2.q4_k_m.gguf" # Или из os.getenv()
N_CTX = 2048

try:
    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=N_CTX,
        verbose=False  # False - хорошо для продакшена
    )
except Exception as e: # Например, если файл модели не найден
    logging.error(f"Failed to load LLaMA model from {MODEL_PATH}: {e}")
    llm = None # Установить в None, чтобы последующие вызовы могли это проверить

def ask_model(prompt: str, max_tokens: int = 512) -> str:
    if llm is None:
        logging.error("LLaMA model is not loaded. Cannot process prompt.")
        return "" # Или выбросить исключение

    try:
        output = llm(prompt=prompt, max_tokens=max_tokens, temperature=0.1) # Добавил temperature для более детерминированного вывода

        if output and "choices" in output and output["choices"] and \
           isinstance(output["choices"], list) and len(output["choices"]) > 0 and \
           "text" in output["choices"][0]:
            return output["choices"][0]["text"].strip()
        else:
            logging.error(f"Unexpected LLaMA output structure: {output}")
            return "" # Возвращаем пустую строку при неожиданной структуре
    except Exception as e:
        logging.error(f"Error during LLaMA call: {e}. Prompt: {prompt[:100]}...") # Логируем начало промпта
        return "" # Возвращаем пустую строку в случае ошибки
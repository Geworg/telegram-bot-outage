from typing import Optional
import logging

logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def log_info(msg: str):
    logging.info(msg)

def log_error(msg: str, exc: Optional[Exception] = None):
    if exc:
        logging.error(f"{msg} - {str(exc)}", exc_info=True)
    else:
        logging.error(msg)

def log_warning(msg: str):
    logging.warning(msg)

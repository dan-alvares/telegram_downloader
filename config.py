import os
import sys
from typing import Any
from dotenv import load_dotenv

# Pasta onde o .exe está sendo executado
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

CONFIG_FILE = os.path.join(BASE_DIR, "config.toml")

def load_config() -> dict[str, Any]:
    # config = toml.load(CONFIG_FILE)

    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")

    if not api_id or not api_hash:
        raise RuntimeError("TG_API_ID e TG_API_HASH devem estar no .env")

    return {
        "api_id": api_id,
        "api_hash": api_hash,
        "session_name": 'telegram_session',
        "download_dir": 'downloads',
    }
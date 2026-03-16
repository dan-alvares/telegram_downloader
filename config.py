import os
import sys
from typing import Any
from dotenv import load_dotenv

# Compatível com Nuitka --onefile
if "__compiled__" in dir():
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

def load_config() -> dict[str, Any]:
    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")
    downloads_sim = os.getenv("DOWNLOAD_SIM", 4)

    if not api_id or not api_hash:
        raise RuntimeError("TG_API_ID e TG_API_HASH devem estar no .env")

    return {
        "api_id": api_id,
        "api_hash": api_hash,
        "session_name": "telegram_session",
        "download_dir": "downloads",
        "concurrent_downloads": int(downloads_sim)
    }
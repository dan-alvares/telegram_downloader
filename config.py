import os
import toml
from typing import Any
from dotenv import load_dotenv

load_dotenv()

CONFIG_FILE = "config.toml"
# 
def load_config() -> dict[str, Any]:
    config = toml.load(CONFIG_FILE)

    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")

    if not api_id or not api_hash:
        raise RuntimeError("TG_API_ID e TG_API_HASH devem estar no .env")

    return {
        "api_id": api_id,
        "api_hash": api_hash,
        "session_name": config["telegram"]["session_name"],
        "download_dir": config["telegram"]["download_dir"],
    }
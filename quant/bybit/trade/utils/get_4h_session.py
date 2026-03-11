import os
import logging
import threading
from pybit.unified_trading import HTTP
from common.env_loader import load_project_env

logger = logging.getLogger(__name__)
ENV_PATH = load_project_env()
logger.info(f"ENV loaded from: {ENV_PATH}")

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

if not BYBIT_API_KEY or not BYBIT_API_SECRET:
    raise RuntimeError("Missing BYBIT_API_KEY / BYBIT_API_SECRET")

_thread_local = threading.local()

def _create_session():
    return HTTP(
        testnet=False,
        api_key=BYBIT_API_KEY,
        api_secret=BYBIT_API_SECRET,
    )

def get_4h_session():
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = _create_session()
        _thread_local.session = session
    return session
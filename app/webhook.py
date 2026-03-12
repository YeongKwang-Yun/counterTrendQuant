from flask import Flask, request, jsonify
from quant.make_trade_data import make_trade_data

# utils
from common.util import send_tradingview_embed_from_data
from common.env_loader import load_project_env

import logging
import os
import queue
import threading
import json
import time
import hashlib
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ENV_PATH = load_project_env()
logger.info(f"ENV loaded from: {ENV_PATH}")

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROUP_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CHANNEL_CHAT_ID = os.getenv("TELEGRAM_CHANNEL_ID")

ENABLE_BYBIT = os.getenv("ENABLE_BYBIT", "0") == "1"
ENABLE_TELEGRAM_NOTIFY = os.getenv("ENABLE_TELEGRAM_NOTIFY", "0") == "1"
ENABLE_DISCORD_NOTIFY = os.getenv("ENABLE_DISCORD_NOTIFY", "0") == "1"

app = Flask(__name__)

stream_queues = {}
stream_workers = {}
stream_guard = threading.Lock()

event_store = {}
event_store_guard = threading.Lock()
DEDUP_TTL_SECONDS = 600

logger.info("--------------------------")
logger.info("Webhook server started")
logger.info("--------------------------")

def validate_env():
    missing_vars = []

    if ENABLE_TELEGRAM_NOTIFY:
        if not TELEGRAM_BOT_TOKEN:
            missing_vars.append("TELEGRAM_BOT_TOKEN")
        if not GROUP_CHAT_ID:
            missing_vars.append("TELEGRAM_CHAT_ID")
        if not CHANNEL_CHAT_ID:
            missing_vars.append("TELEGRAM_CHANNEL_ID")
    
    if ENABLE_BYBIT:
        if not BYBIT_API_KEY or not BYBIT_API_SECRET:
            missing_vars.append("BYBIT API KEYS")

    if missing_vars:
        logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
        sys.exit(1)

validate_env()

@app.route("/", methods=["GET"])
def index():
    return "✅ Chartedu Webhook Server is running.", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True) or {}
    
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "Invalid JSON body"}), 400
    
    required_fields = [
        "sort", "exchange", "time_frame", "message_type", "update_gubun",
        "ticker", "side", "entry_price", "target_price_1", "stop_loss", "qty", "trade_id"
    ]
    
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        return jsonify({"error": f"Missing fields: {', '.join(missing_fields)}"}), 400
        
    sort = data.get('sort')
    exchange = data.get("exchange") or "unknown"
    time_frame = data.get("time_frame") or "unknown"
    ticker = data.get("ticker") or "unknown"

    stream_key = f"{exchange}:{time_frame}:{ticker}"
    event_id = build_event_id(data)

    accepted, state = reserve_event(event_id)
    if not accepted:
        # logger.info(f"[DEDUP] ignored event_id={event_id}, state={state}, stream_key={stream_key}")
        return jsonify({
            "status": "duplicate_ignored",
            "event_id": event_id,
            "state": state
        }), 200
    if sort == "trade":
        q = get_stream_queue(stream_key)
        q.put((event_id, data))

        logger.info(f"[ENQUEUED] stream_key={stream_key}, event_id={event_id}, data={data}")

        return jsonify({
            "status": "accepted",
            "event_id": event_id,
            "stream_key": stream_key
        }), 200
    elif sort != "trade":
        return jsonify({"error": f"Unsupported sort: {sort}"}), 400
    
def build_event_id(data: dict) -> str:
    payload = {
        "sort": data.get("sort"),
        "exchange": data.get("exchange"),
        "time_frame": data.get("time_frame"),
        "message_type": data.get("message_type"),
        "update_gubun": data.get("update_gubun"),
        "tbc_gubun": data.get("tbc_gubun"),
        "ticker": data.get("ticker"),
        "side": data.get("side"),
        "entry_price": data.get("entry_price"),
        "target_price_1": data.get("target_price_1"),
        "stop_loss": data.get("stop_loss"),
        "qty": data.get("qty"),
        "order_time": data.get("order_time"),
        "trade_id": data.get("trade_id"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def cleanup_expired_events(now: float):
    expired_keys = [
        event_id for event_id, meta in event_store.items()
        if now - meta["ts"] > DEDUP_TTL_SECONDS
    ]
    for event_id in expired_keys:
        del event_store[event_id]

def reserve_event(event_id: str):
    now = time.time()
    with event_store_guard:
        cleanup_expired_events(now)

        meta = event_store.get(event_id)
        if meta and meta["state"] in ("queued", "processing", "done"):
            return False, meta["state"]

        event_store[event_id] = {"state": "queued", "ts": now}
        return True, "queued"

def update_event_state(event_id: str, state: str):
    with event_store_guard:
        if event_id in event_store:
            event_store[event_id]["state"] = state
            event_store[event_id]["ts"] = time.time()
            
def process_trade_event(data: dict):
    if ENABLE_DISCORD_NOTIFY:
        try:
            send_tradingview_embed_from_data(data)
        except Exception:
            logger.exception("Discord notify failed")

    response = make_trade_data(data) or {}
    bybit_status = (response.get("bybit") or {}).get("bybit_status", "error")
    
    if bybit_status == "success":
        logger.info(
            f"[TRADE] success ticker={data.get('ticker')} side={data.get('side')} "
            f"message_type={data.get('message_type')} update_gubun={data.get('update_gubun')}"
        )
    elif bybit_status != "success":
        raise RuntimeError(f"Bybit order failed: {response}")

def stream_worker(stream_key: str, q: queue.Queue):
    logger.info(f"[WORKER] started for stream_key={stream_key}")
    while True:
        event_id, data = q.get()
        try:
            update_event_state(event_id, "processing")
            sort = data.get("sort")

            if sort == "trade":
                process_trade_event(data)
            else:
                raise ValueError(f"Unsupported sort: {sort}")

            update_event_state(event_id, "done")
            logger.info(f"[WORKER] done event_id={event_id}, stream_key={stream_key}")
        except Exception:
            update_event_state(event_id, "failed")
            logger.exception(f"[WORKER] failed event_id={event_id}, stream_key={stream_key}")
        finally:
            q.task_done()

def get_stream_queue(stream_key: str) -> queue.Queue:
    with stream_guard:
        q = stream_queues.get(stream_key)
        if q is None:
            q = queue.Queue()
            worker = threading.Thread(
                target=stream_worker,
                args=(stream_key, q),
                daemon=True,
                name=f"worker-{stream_key}"
            )
            stream_queues[stream_key] = q
            stream_workers[stream_key] = worker
            worker.start()
        return q
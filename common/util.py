# from telebot import TeleBot
import requests
import logging
import os
import json  
import time
import hashlib
import threading

from common.env_loader import load_project_env

ENV_PATH = load_project_env()
logger = logging.getLogger(__name__)
logger.info(f"ENV loaded from: {ENV_PATH}")

DISCORD_BYBIT_WEBHOOK_URL = os.getenv('DISCORD_BYBIT_WEBHOOK_URL')
DISCORD_TRADINGVIEW_LOG_URL = os.getenv('DISCORD_TRADINGVIEW_LOG_URL')

last_alert_time = {}
_last_alert_lock = threading.Lock()

# 디스코드 채팅방에 메시지 보내기
def send_discord_message(title, description, color, sort=None, exchange=None, time_frame=None, trade_id=None):
    discord_webhook_url = None
    
    if exchange == "bybit":
        if time_frame == "4h":
            discord_webhook_url = DISCORD_BYBIT_WEBHOOK_URL

    if not discord_webhook_url:
        logger.error(f"Discord webhook URL not configured for exchange={exchange}, time_frame={time_frame}, trade_id={trade_id}")
        return {"status": "error", "reason": "webhook_url_not_configured"}

    additional_info = f"\n📌 **Sort:** `{sort}`\n📌 **Exchange:** `{exchange}`\n📌 **Quant:** `{time_frame}`\n📌 **trade_id:** `{trade_id}`"
    description += additional_info

    alert_key = _make_alert_key(title, sort, exchange, time_frame, description)

    now = time.time()
    with _last_alert_lock:
        _cleanup_last_alert_cache(now)
        if alert_key in last_alert_time and now - last_alert_time[alert_key] < 30:
            logger.warning(f"Duplicate Discord message detected: {title}")
            return {"status": "skipped", "reason": "duplicate"}
        last_alert_time[alert_key] = now

    payload = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
        }]
    }

    # logger.info(
    #     f"[DISCORD] sort={sort} exchange={exchange} time_frame={time_frame} "
    #     f"url_selected={'yes' if discord_webhook_url else 'no'} "
    #     f"title={title!r} desc_len={len(description)}"
    # )

    try:
        response = requests.post(discord_webhook_url, json=payload, timeout=5)
        if response.status_code == 204:
            logger.info("Discord message sent successfully.")
            return {"status": "success"}
        else:
            logger.error(f"Failed to send Discord message: {response.status_code} - {response.text}")
            return {"status": "error", "reason": f"http_{response.status_code}", "body": response.text}
    except Exception as e:
        logger.exception("An error occurred while sending the Discord message.")
        return {"status": "error", "reason": "exception", "message": str(e)}
        
        
def send_tradingview_alert_log(message: str):
    if not DISCORD_TRADINGVIEW_LOG_URL:
        logger.warning("DISCORD_TRADINGVIEW_LOG_URL is not set.")
        return {"status": "error", "reason": "url_not_set"}

    # logger.info(f"[TV-RAW] attempting send, tv_url_set={bool(DISCORD_TRADINGVIEW_LOG_URL)}")
    content = _truncate_text(message, 1900)
    payload = {"content": content}

    try:
        r = requests.post(DISCORD_TRADINGVIEW_LOG_URL, json=payload, timeout=5)
        if r.status_code in (200, 204):
            return {"status": "success"}
        logger.error(f"[TV-RAW] failed: {r.status_code} - {r.text}")
        return {"status": "error", "reason": f"http_{r.status_code}"}
    except Exception as e:
        logger.exception("DISCORD_TRADINGVIEW_LOG failed")
        return {"status": "error", "reason": "exception", "message": str(e)}


def format_tradingview_embed(data: dict):
    qt = data.get("time_frame")
    sort = data.get("sort")
    exch = data.get("exchange")

    header = (
        f"📌 **Sort:** {_fmt(sort)}\n"
        f"🏦 **Exchange:** {_fmt(exch)}\n"
        f"⏱️ **Quant:** {_fmt(qt)}\n"
    )

    # if qt == "1m":
    #     title = "📥 TradingView Webhook (1m)"
    #     body = (
    #         f"📍 **Ticker:** {_fmt(data.get('ticker'))}\n"
    #         f"🛒 **Side:** {_fmt(data.get('side'))}\n"
    #         f"🎯 **TP1:** {_fmt(data.get('target_price_1'))}\n"
    #         f"🛑 **SL:** {_fmt(data.get('stop_loss'))}\n"
    #         f"📦 **Qty:** {_fmt(data.get('qty'))}\n"
    #         f"⚙️ **EP Type:** {_fmt(data.get('ep_type'))}\n"
    #     )
    #     color = 0x2F88FF

    if qt == "4h":
        title = "📥 TradingView Webhook (4h)"
        body = (
            f"🧾 **Message Type:** {_fmt(data.get('message_type'))}\n"
            f"🔁 **Update Gubun:** {_fmt(data.get('update_gubun'))}\n"
            f"🕊 **TBC Gubun:** {_fmt(data.get('tbc_gubun'))}\n"
            f"📍 **Ticker:** {_fmt(data.get('ticker'))}\n"
            f"🛒 **Side:** {_fmt(data.get('side'))}\n"
            f"💰 **Entry Price:** {_fmt(data.get('entry_price'))}\n"
            f"🎯 **TP1:** {_fmt(data.get('target_price_1'))}\n"
            f"🛑 **SL:** {_fmt(data.get('stop_loss'))}\n"
            f"📦 **Qty:** {_fmt(data.get('qty'))}\n"
        )
        color = 0x7C4DFF
    else:
        title = "📥 TradingView Webhook (unknown quant)"
        body = "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```"
        color = 0xAAAAAA

    description = _truncate_text(header + "\n" + body, 3800)  # ✅ 문자열에서 자르기
    return title, description, color

def send_tradingview_embed_from_data(data: dict):
    if not DISCORD_TRADINGVIEW_LOG_URL:
        logger.warning("DISCORD_TRADINGVIEW_LOG_URL is not set.")
        return {"status": "error", "reason": "url_not_set"}

    # logger.info(f"[TV-EMBED] attempting send, tv_url_set={bool(DISCORD_TRADINGVIEW_LOG_URL)}")

    title, description, color = format_tradingview_embed(data)
    payload = {"embeds": [{"title": title, "description": description, "color": color}]}

    try:
        r = requests.post(DISCORD_TRADINGVIEW_LOG_URL, json=payload, timeout=5)
        if r.status_code in (200, 204):
            logger.info("TradingView log sent to Discord.")
            return {"status": "success"}
        else:
            logger.error(f"Discord log failed: {r.status_code} - {r.text}")
            return {"status": "error", "reason": f"http_{r.status_code}", "body": r.text}
    except Exception as e:
        logger.exception("send_tradingview_embed_from_data failed.")
        return {"status": "error", "reason": "exception", "message": str(e)}
        
def _fmt(v):
    return "`—`" if v is None or v == "" else f"`{v}`"

def _truncate_text(s: str, limit: int = 3800) -> str:
    s = s or ""
    return s if len(s) <= limit else (s[:limit] + "\n…(truncated)")

def _make_alert_key(title, sort, exchange, time_frame, description):
    digest = hashlib.sha1(description.encode("utf-8")).hexdigest()[:10]
    return f"{title}_{sort}_{exchange}_{time_frame}_{digest}"

def _cleanup_last_alert_cache(now: float, ttl: int = 300):
    expired = [k for k, ts in last_alert_time.items() if now - ts > ttl]
    for k in expired:
        del last_alert_time[k]
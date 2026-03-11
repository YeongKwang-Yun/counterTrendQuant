import requests
import logging
import os

from common.env_loader import load_project_env

ENV_PATH = load_project_env()
logger = logging.getLogger(__name__)
logger.info(f"ENV loaded from: {ENV_PATH}")

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')


# 텔레그램 API 를 이용해 특정 채팅방에 메시지 전송하기.
def send_to_telegram(chat_id, message, parse_mode="MarkdownV2"):
    try:
        logger.info(f"Sending message to {chat_id}: {message}")

        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': parse_mode,
            "disable_web_page_preview": True,
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.warning(f"Failed to send message: {response.text}")

        return response

    except Exception as e:
        logger.exception("Error sending Telegram message.")
        return None
    
# 강조를 위해 메시지 고정하기
def pin_telegram_message(chat_id, message_id):
    pin_url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/pinChatMessage'
    payload = {
        'chat_id': chat_id,
        'message_id': message_id
    }
    response = requests.post(pin_url, json=payload)
    if response.status_code == 200:
        logger.info(f"메시지 고정 완료")
    else:
        logger.info(f"메시지 고정 실패 : {response.status_code} - {response.text}")

    return response
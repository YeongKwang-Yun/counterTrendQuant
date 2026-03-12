from telegram.common.utils import send_to_telegram, pin_telegram_message
import logging
import os

from common.env_loader import load_project_env

ENV_PATH = load_project_env()
logger = logging.getLogger(__name__)
# logger.info(f"ENV loaded from: {ENV_PATH}")

GROUP_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
CHANNEL_CHAT_ID = os.getenv("TELEGRAM_CHANNEL_ID")
TEST_CHANNEL_ID = os.getenv("TELEGRAM_TEST_CHANNEL_ID")

SEND_TEST_ONLY = os.getenv("TELEGRAM_SEND_TEST_ONLY", "0") == "1"

def _resolve_channel_id() -> str:
    """
    테스트 모드면 TEST_CHANNEL_ID로 강제.
    아니면 기존 CHANNEL_CHAT_ID 사용.
    """
    if SEND_TEST_ONLY:
        if not TEST_CHANNEL_ID:
            raise RuntimeError("TELEGRAM_SEND_TEST_ONLY=1 인데 TELEGRAM_TEST_CHANNEL_ID가 비어있습니다.")
        return TEST_CHANNEL_ID
    return CHANNEL_CHAT_ID

# # 크립토 트레이딩 튜터 공쌤 그룹 채팅방에 메시지 전송하기
# def send_to_group(message):
#     if SEND_TEST_ONLY:
#         logger.info("[TELEGRAM] TEST_ONLY enabled -> skip send_to_group()")
#         return "SKIPPED_TEST_ONLY"
    
#     group_status = None
#     try:
#         group_response = send_to_telegram(GROUP_CHAT_ID, message)
#         if not group_response:
#             logger.warning("Telegram send_to_telegram returned None")
#             return "Error"
#         group_status = group_response.status_code

#         if group_status == 200:
#             logger.info(f"그룹 채팅방에 메시지 전송 성공")
#             group_message_id = group_response.json()['result']['message_id']

#             if group_message_id:
#                 pin_telegram_message(GROUP_CHAT_ID, group_message_id)
#             else:
#                 logger.info(f"그룹 채팅방에 메시지 고정 실패 : {group_response.status_code} - {group_response.text}")
#         else:
#             logger.info(f"그룹 채팅방에 메시지 전송 실패")

#     except Exception as e:
#         logger.exception("send_to_group 에서 에러 발생")
#         group_status = "Error"

#     return group_status

# 채널에 메시지 전송하기
def send_to_channel(message):
    channel_status = None

    try:
        target_id = _resolve_channel_id()
        
        channel_response = send_to_telegram(target_id, message)
        if not channel_response:
            logger.warning("Telegram send_to_telegram returned None")
            return "Error"
        channel_status = channel_response.status_code

        if channel_status == 200:
            # logger.info(f"채널에 메시지 전송 성공")
            channel_message_id = channel_response.json()['result']['message_id']

            if channel_message_id:
                pin_telegram_message(target_id, channel_message_id)
            else:
                logger.info(f"채널에 메시지 고정 실패 : {channel_response.status_code} - {channel_response.text}")
        else:
            logger.info(f"채널에 메시지 전송 실패")

    except Exception as e:
        logger.exception(f"send_to_channel 에서 에러 발생 : {e}")
        channel_status = "Error"

    return channel_status






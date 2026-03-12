import logging

# Bybit
from quant.bybit.trade.place_order_4h import place_order_4h as bybit_place_order_4h         # 4h Quant 주문

# Telegram 
from telegram.make_signal_data import make_trade_notify_message_4h
from telegram.send_signal_data import send_to_channel

# Common
from common.util import send_discord_message
from quant.bybit.utils.build_4h_title import build_4h_title

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 전달받은 data 가공해서 주문 함수 호출하기
def make_trade_data(data):
    try:
        exchange = data.get('exchange')                                                 # 거래소 종류
        ticker = clean_ticker(data.get("ticker"))       # 티커 : BTCUSDT
        data['ticker'] = ticker

        bybit_response = None
        
        if exchange == "bybit":
            bybit_response = process_bybit_order(data=data, **data)
            
        return {
            "bybit": bybit_response
        }

    except Exception as e:
        logger.exception("An error occurred while placing the order.")
        error_msg = str(e)

#       디스코드 Webhook URL 바꿔야함.
        send_discord_message(
            title="🚨 **Unhandled Exception - Bybit Order**",
            description=f"📌 **Ticker:** {data.get('ticker', 'Unknown')}\n🛑 **Exception:** `{error_msg}`",
            color=15158332,
            sort=data.get('sort', 'unknown'),
            exchange=data.get('exchange', 'unknown'),
            time_frame=data.get('time_frame', 'unknown')
        )

        return {
            "bybit": {
                "bybit_status": "error",
                "message": error_msg,
                "order_id": None,
                "order_link_id": None,
                "data": None,
            }
        }

"""
    Bybit 에서 주문을 실행하고 결과 처리.
    주문이 성공하면 주문 조회 API 를 통해 최종 주문 상태를 확인.
"""
def process_bybit_order(data, sort, exchange, time_frame, ticker, side, entry_price, target_price_1, stop_loss, qty, trade_id=None, order_time=None, message_type=None, update_gubun=None, tbc_gubun=None):
    result = {
        "bybit_status": "error",
        "message": "Unknown error",
        "order_id": None,
        "order_link_id": None,
        "data": None,
        "open_order": None,
        "tp_order": None,
        "sl_order": None,
        "errors": [],
        "is_switching": False,
        "prev_side": None,
        "telegram_channel": None,
    }
    if time_frame == "4h":
        # 포지션 오픈하기
        order_response = bybit_place_order_4h(sort=sort, exchange=exchange, time_frame=time_frame, message_type=message_type, update_gubun=update_gubun, tbc_gubun=tbc_gubun, ticker=ticker, side=side, entry_price=entry_price, target_price_1=target_price_1, stop_loss=stop_loss, qty=qty, trade_id=trade_id)
        
        result.update({
            "bybit_status": order_response.get("bybit_status", "error"),
            "message": order_response.get("message", "Unknown"),
            "order_id": order_response.get("order_id"),
            "order_link_id": order_response.get("order_link_id"),
            "data": order_response.get("data"),
            "open_order": order_response.get("open_order"),
            "tp_order": order_response.get("tp_order"),
            "sl_order": order_response.get("sl_order"),
            "errors": order_response.get("errors", []),
            "is_switching": order_response.get("is_switching", False),
            "prev_side": order_response.get("prev_side", None),
        })
        
        if result["bybit_status"] != "success":
            logger.error(f"[4h] handler failed: {result}")
            return result
               
        # ✅ 요구사항대로 타이틀 생성
        send_title = build_4h_title(message_type, update_gubun, tbc_gubun)
            
        # ✅ 4h 성공 알림 보내기
        desc = (
            f"📍 **Ticker:** `{ticker}`\n"
            f"🛒 **Side:** `{side}`\n"
            f"💰 **Entry Price:** `{entry_price}`\n"
            f"🎯 **TP1:** `{target_price_1}`\n"
            f"🛑 **SL:** `{stop_loss}`\n"
            f"🔗 **OrderId:** `{result.get('order_id')}`\n"
            f"🔗 **OrderLinkId:** `{result.get('order_link_id')}`\n"
        )
            
        # ✅ 하단 메타 블록(값이 있을 때만 노출)
        meta_lines = []
        if message_type:
            meta_lines.append(f"📌 **Message_type:** `{message_type}`")
        if update_gubun:
            meta_lines.append(f"📌 **Update_gubun:** `{update_gubun}`")
        if (tbc_gubun or "").lower() == "tbc":
            meta_lines.append("📌 **흑삼병**")
        if meta_lines:
            desc += "\n" + "\n".join(meta_lines)
                
        send_discord_message(
            title=send_title,
            description=desc,
            color=0x2ecc71,   # green
            sort=sort,
            exchange=exchange,
            time_frame=time_frame,
            trade_id=trade_id
        )

        if update_gubun == "open":
            try:
                notify_data = dict(data)
                notify_data["is_switching"] = order_response.get("is_switching", False)
                notify_data["prev_side"] = order_response.get("prev_side")
        
                msg = make_trade_notify_message_4h(notify_data)
                send_channel_response = send_to_channel(msg)
                result["telegram_channel"] = send_channel_response

                # logger.info("--------------------------")
                # logger.info("-------send_channel_response----------")
                # logger.info(send_channel_response)
                # logger.info("--------------------------")

            except Exception as e:
                logger.exception("[TELEGRAM] notify failed")
                result["telegram_channel"] = {"status": "error", "message": str(e)}
    else:
        msg = f"Unknown time_frame: {time_frame}"
        logger.error(msg)
        result["message"] = msg
    
    return result


def clean_ticker(ticker: str | None) -> str:
    if not ticker:
        return ""

    result = str(ticker).strip()

    if " " in result:
        result = result.split()[0]

    if result.endswith(".P"):
        result = result[:-2]

    return result
import logging
import time 

from quant.bybit.utils.position_utils import _find_position
logger = logging.getLogger(__name__)

# 
# 포지션 스위칭 용 함수
# 새로운 신호가 Buy 인 경우
#   has_short == True → Switching !
#   has_long == True → Positions Add
# 
# 새로운 신호가 Sell 인 경우
#   has_long == True → Switching !
#   has_short == True → Positions Add
# 
#   둘 다 False 인 경우는 아예 신규오픈이기 때문에 그냥 Open 처리.

def get_position_state(session, symbol: str) -> dict:
    resp = session.get_positions(category="linear", symbol=symbol) 
    
    # logger.info(f"✅ get_position_stat : {resp}")
    
    if resp.get("retCode") != 0:
        raise RuntimeError(f"get_positions failed: {resp}")

    long_size = 0.0
    short_size = 0.0

    for pos in resp.get("result", {}).get("list", []):
        try:
            idx = int(pos.get("positionIdx", 0))
            size = float(pos.get("size", 0) or 0)

            if idx == 1:
                long_size = size
            elif idx == 2:
                short_size = size
        except Exception:
            continue

    return {
        "long_size": long_size,
        "short_size": short_size,
        "has_long": long_size > 0,
        "has_short": short_size > 0,
    }
    
    
# 판단용 Helper
def classify_position_action(position_state: dict, signal_side: str) -> dict:
    has_long = position_state.get("has_long", False)
    has_short = position_state.get("has_short", False)

    # logger.info(f"✅ has_long : {has_long}")
    # logger.info(f"✅ has_short : {has_short}")

    # 비정상 상태: hedge mode에서 양방향 동시 보유
    if has_long and has_short:
        return {
            "action": "ambiguous",
            "prev_side": None,
            "close_position_idx": None,
            "close_qty": 0.0,
        }

    if signal_side == "Buy":
        if has_short:
            return {
                "action": "switch",
                "prev_side": "Sell",
                "close_position_idx": 2,
                "close_qty": position_state.get("short_size", 0.0),
            }
        elif has_long:
            return {
                "action": "add",
                "prev_side": "Buy",
                "close_position_idx": None,
                "close_qty": 0.0,
            }
        else:
            return {
                "action": "open",
                "prev_side": None,
                "close_position_idx": None,
                "close_qty": 0.0,
            }

    elif signal_side == "Sell":
        if has_long:
            return {
                "action": "switch",
                "prev_side": "Buy",
                "close_position_idx": 1,
                "close_qty": position_state.get("long_size", 0.0),
            }
        elif has_short:
            return {
                "action": "add",
                "prev_side": "Sell",
                "close_position_idx": None,
                "close_qty": 0.0,
            }
        else:
            return {
                "action": "open",
                "prev_side": None,
                "close_position_idx": None,
                "close_qty": 0.0,
            }

    return {
        "action": "invalid",
        "prev_side": None,
        "close_position_idx": None,
        "close_qty": 0.0,
    }
    
def cancel_exit_orders_for_position(session, ticker, position_idx):
    resp = session.get_open_orders(category="linear", symbol=ticker)
    if resp.get("retCode") != 0:
        raise RuntimeError(f"get_open_orders failed: {resp}")

    cancelled = []
    failed = []

    for o in resp.get("result", {}).get("list", []):
        try:
            if int(o.get("positionIdx", 0)) != int(position_idx):
                continue

            order_link_id = o.get("orderLinkId", "")
            if not (order_link_id.startswith("TP") or order_link_id.startswith("SL")):
                continue

            cancel_resp = session.cancel_order(
                category="linear",
                symbol=ticker,
                orderId=o["orderId"]
            )

            if cancel_resp.get("retCode") == 0:
                cancelled.append(o.get("orderId"))
            else:
                failed.append({
                    "orderId": o.get("orderId"),
                    "response": cancel_resp
                })
        except Exception as e:
            failed.append({
                "orderId": o.get("orderId"),
                "error": str(e)
            })

    return {"cancelled": cancelled, "failed": failed}

def wait_until_position_flat(session, symbol, position_idx, retries=10, sleep_sec=0.5):
    for _ in range(retries):
        size, _ = _find_position(session, symbol, position_idx)
        if abs(size) < 1e-12:
            return True
        time.sleep(sleep_sec)
    return False
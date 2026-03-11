import logging
import time

# Bybit Utils
from quant.bybit.trade.utils.get_4h_session import get_4h_session                                 # Sub  Account (4시간 퀀트)
from quant.bybit.trade.utils.place_sl_order import place_sl_order                                   # StopLoss 주문하기
from quant.bybit.trade.utils.place_sl_order import find_specific_sl_order                           # EntryPrice 로 특정 StopLoss 주문 조회해서 order_link_id 추출하기
from quant.bybit.trade.utils.place_tp_order import place_tp_order                                   # TakeProfit 주문하기
from quant.bybit.trade.utils.order_management import classify_position_action, get_position_state, cancel_exit_orders_for_position, wait_until_position_flat

# utils
from common.util import send_discord_message
from quant.bybit.utils.set_qty import normalize_qty_str, qty_to_lots, lots_to_qty_str
from quant.bybit.utils.position_utils import kill_dust

logger = logging.getLogger(__name__)

# Bybit Place_Order API Required Parameters:
#     category    (string)        : linear, inverse, spot, option 중 linear
#     symbol      (string)        : 티커 (e.x BTCUSDT)
#     side        (string)        : Buy, Sell
#     orderType   (string)        : Market, Limit
#     qty         (string)        : qty
#     positionIdx (int)           : 0 = one-way mode
#                                 : 1 = hedage mode (Buy)
#                                 : 2 = headge mode (Sell)

# NOTE:
# This handler currently assumes BTCUSDT linear perpetual only.
# qty step = 0.001
# entry price formatting = 2 decimals
def place_order_4h(
    sort, exchange, time_frame, message_type, update_gubun, tbc_gubun,
    ticker, side, entry_price,
    target_price_1=None, stop_loss=None, qty=None, order_type="Market", order_time=None, trade_id=None):
    
    result = {
        "bybit_status": "error",
        "message": "",
        "order_id": None,
        "order_link_id": None,
        "data": None,
        "open_order": None,
        "tp_order": None,
        "sl_order": None,
        "trade_id": trade_id,
        "is_switching": False,
        "prev_side": None,
        "errors": []
    }
    
    session = get_4h_session()
    
    if side == "Buy":
        positionIdx = 1
    elif side == "Sell":
        positionIdx = 2
    else:
        logger.error(f"Invalid side: {side}")
        return {"bybit_status": "error", "message": "Invalid side"}
    
    if qty is None:
        logger.error("Missing qty")
        return {"bybit_status": "error", "message": "Missing qty"}
    if entry_price is None:
        logger.error("Missing entry_price")
        return {"bybit_status": "error", "message": "Missing entry_price"}
    if not trade_id:
        logger.error("Missing trade_id")
        return {"bybit_status": "error", "message": "Missing trade_id"}

    # qty 정규화 (BTCUSDT.P 기준 최소 qty = 0.001)
    qty_norm = normalize_qty_str(str(qty))  # 예: '0.0085' -> '0.008' (0.001 스텝)
    total_lots = qty_to_lots(qty_norm)
    
    if total_lots == 0:
        msg = f"Qty below min step: qty={qty}, step=0.001"
        logger.error(msg)
        return {"bybit_status": "error", "message": msg}
    
    # === CASE 1: Open ===
    if message_type == "open_order":
        # Step 0: Switching Check
        position_state = get_position_state(session, ticker)
        decision = classify_position_action(position_state, side)

        logger.info(f"✅ place_order_4h.py >> position_state : {position_state}")
        logger.info(f"✅ place_order_4h.py >> decision: {decision}")

        result["is_switching"] = (decision["action"] == "switch")
        result["prev_side"] = decision.get("prev_side")

        # === 이미 양방향 포지션 오픈 중인 CASE 의 경우 스위칭 하면 안됨.
        if decision["action"] == "ambiguous":
            msg = f"Ambiguous position state: both long and short exist on {ticker}"
            logger.error(msg)
            result["bybit_status"] = "error"
            result["message"] = msg
            send_discord_message(
                title="🚨 Ambiguous Position State",
                description=msg,
                color=15158332,
                sort=sort,
                exchange=exchange,
                time_frame=time_frame
            )
            return result

        if decision["action"] == "switch":
            cancel_result = cancel_exit_orders_for_position(
                session=session,
                ticker=ticker,
                position_idx=decision["close_position_idx"]
            )   

            if cancel_result["failed"]:
                msg = f"Failed to cancel opposite exit orders: {cancel_result['failed']}"
                logger.error(msg)
                result["bybit_status"] = "error"
                result["message"] = msg
                return result

            close_qty_norm = normalize_qty_str(str(decision["close_qty"]))
            close_side = "Sell" if decision["prev_side"] == "Buy" else "Buy"

            # close_qty 가 "0.000"이 될 수 있기 때문에 방어 로직 필요함.
            if close_qty_norm == "0.000":
                kill_dust(
                    session=session,
                    symbol=ticker,
                    positionIdx=decision["close_position_idx"],
                    step_qty="0.001",
                    sort=sort,
                    exchange=exchange,
                    time_frame=time_frame,
                    send_discord_message=send_discord_message,
                    notify="skipped"
                )

                flat_ok = wait_until_position_flat(
                    session=session,
                    symbol=ticker,
                    position_idx=decision["close_position_idx"],
                    retries=5,
                    sleep_sec=0.5
                )

                if not flat_ok:
                    msg = f"Switch close incomplete: dust position still remains on {ticker}"
                    logger.error(msg)
                    result["bybit_status"] = "error"
                    result["message"] = msg
                    return result
            else:
                close_resp = session.place_order(
                    category="linear",
                    symbol=ticker,
                    side=close_side,
                    orderType="Market",
                    qty=close_qty_norm,
                    reduceOnly=True,
                    positionIdx=decision["close_position_idx"],
                    orderLinkId=f"SC_{trade_id}"
                )

                if close_resp.get("retCode") != 0:
                    msg = f"Switch close failed: {close_resp}"
                    logger.error(msg)
                    result["bybit_status"] = "error"
                    result["message"] = msg
                    return result
                
                flat_ok = wait_until_position_flat(
                    session=session,
                    symbol=ticker,
                    position_idx=decision["close_position_idx"],
                    retries=10,
                    sleep_sec=0.5
                )

                if not flat_ok:
                    kill_dust(
                        session=session,
                        symbol=ticker,
                        positionIdx=decision["close_position_idx"],
                        step_qty="0.001",
                        sort=sort,
                        exchange=exchange,
                        time_frame=time_frame,
                        send_discord_message=send_discord_message,
                        notify="skipped"
                    )

                    flat_ok = wait_until_position_flat(
                        session=session,
                        symbol=ticker,
                        position_idx=decision["close_position_idx"],
                        retries=5,
                        sleep_sec=0.5
                    )

                if not flat_ok:
                    msg = f"Switch close incomplete: position still remains on {ticker}"
                    logger.error(msg)
                    result["bybit_status"] = "error"
                    result["message"] = msg
                    return result
                send_discord_message(
                    title="🔄 Position Switching Detected",
                    description=(
                        f"**Ticker:** {ticker}\n"
                        f"**Prev Side:** {decision['prev_side']}\n"
                        f"**New Side:** {side}\n"
                        f"**Close Qty:** {close_qty_norm}"
                    ),
                    color=0xF1C40F,
                    sort=sort,
                    exchange=exchange,
                    time_frame=time_frame,
                    trade_id=trade_id
                )
                
        # Step 1: parameter settings
        order_params = {
            "category": "linear",                                               # Product type: spot, linear, inverse
            "symbol": ticker,                                                   # BTCUSDT
            "side": side,                                                       # Buy or Sell
            "orderType": order_type,                                            # Market or Limit
            "qty": qty_norm,                                                    # always order by qty
            "positionIdx": positionIdx,                                         # 1 = Buy , 2 = Sell (Headge mode)
            "orderLinkId": f"OPEN_{trade_id}",
        }
        
        try:
            # Step 2: 주문하기 (Place Order API)
            response = session.place_order(**order_params)
            
            # Place Order Succeed
            if response.get("retCode") == 0:
                logger.info(f"✅ 주문 성공: {response}")
                record_open_result(result, response, "✅ 주문 성공 open_order: " + response.get("retMsg", "None"))
                                
                # Step 3: TP 설정
                if tbc_gubun == "tbc":
                    # Three Black Corw Positions TP Open (흑삼병)
                    tp1_qty = lots_to_qty_str(total_lots)
                    tp1 = None

                    try:
                        if tp1_qty != "0.000":
                            tp1 = place_tp_order(
                                side,
                                tp1_qty,
                                target_price_1,
                                positionIdx,
                                ticker,
                                session,
                                order_link_id=f"TP1_{trade_id}"
                            )
                        else:
                            tp1 = {"skipped": True, "retMsg": "TP skipped because qty is 0.000"}

                        if is_ok_response(tp1) or is_skipped_response(tp1):
                            record_tp_result(result, tp1)
                        else:
                            record_tp_result(result, tp1, "❌ TakeProfit 주문 실패 (흑삼병 TP1)")
                            send_discord_message(
                                title="❌ TakeProfit placement failed [4h][TBC]",
                                description=(
                                    f" **Ticker :** {ticker}\n"
                                    f" **Side :** {side}\n"
                                    f" **TP1 :** {target_price_1}\n"
                                    f" **TP1 Response :** ```{tp1}```\n"
                                ),
                                color=15158332,
                                sort=sort,
                                exchange="bybit",
                                time_frame="4h",
                                trade_id=trade_id
                            )

                    except Exception as e:
                        logger.exception("❌ TBC TP1 주문 중 오류 발생")
                        tp1 = {"exception": str(e)}
                        record_tp_result(result, tp1, "❌ TBC TP1 주문 중 오류 발생")
                            
                    # Step 4: Three Black Corw Positions sl Open (흑삼병)
                    sl = None

                    try:
                        sl_order_link_id = f"SL_{trade_id}"

                        if stop_loss is None:
                            sl = {"skipped": True, "retMsg": "StopLoss is None — skipped SL placement"}
                            logger.warning("StopLoss is None — skipping SL placement")
                            send_discord_message(
                                title="⚠️ StopLoss skipped [4h][TBC]",
                                description=f" **Ticker :** {ticker}\n SL was not provided; skipped placing SL.",
                                color=15105570,
                                sort=sort,
                                exchange="bybit",
                                time_frame="4h",
                                trade_id=trade_id
                            )
                        else:
                            sl = place_sl_order(side, qty_norm, stop_loss, positionIdx, ticker, session, sl_order_link_id)

                        if is_ok_response(sl) or is_skipped_response(sl):
                            record_sl_result(result, sl)
                        else:
                            record_sl_result(result, sl, "❌ StopLoss 주문 실패 (흑삼병)")
                            logger.error(f"❌ StopLoss 주문 실패 : {sl}")

                    except Exception as e:
                        logger.exception("❌ StopLoss 주문 중 오류 발생")
                        sl = {"exception": str(e)}
                        record_sl_result(result, sl, "❌ StopLoss 주문 중 오류 발생 (흑삼병)")
                        
                # Normal Long & Short Positions Open
                elif tbc_gubun == "n":
                    # Step 3: Place TP Order
                    tp1_order_link_id = f"TP1_{trade_id}"
                    tp1_qty = lots_to_qty_str(total_lots)
                    tp1 = None
                    try:
                        if tp1_qty != "0.000":
                            tp1 = place_tp_order(
                                side,
                                tp1_qty,
                                target_price_1,
                                positionIdx,
                                ticker,
                                session,
                                tp1_order_link_id
                            )
                        else:
                            tp1 = {"skipped": True, "retMsg": "TP skipped because qty is 0.000"}

                        if is_ok_response(tp1) or is_skipped_response(tp1):
                            record_tp_result(result, tp1)
                        else:
                            record_tp_result(result, tp1, "❌ TakeProfit 주문 실패")
                            send_discord_message(
                                title="❌ TakeProfit Placement Failed [4h]",
                                description=(
                                    f" **Ticker :** {ticker}\n"
                                    f" **Side :** {side}\n"
                                    f" **TP :** {target_price_1}\n"
                                    f" **TP1 :** ```{tp1}```"
                                ),
                                color=15158332,
                                sort=sort,
                                exchange="bybit",
                                time_frame="4h",
                                trade_id=trade_id
                            )

                    except Exception as e:
                        logger.exception("❌ TakeProfit 주문 중 오류 발생")
                        tp1 = {"exception": str(e)}
                        record_tp_result(result, tp1, "❌ TakeProfit 주문 중 오류 발생")
                        send_discord_message(
                            title="🚨 **Unhandled Exception - place_order_4h.py (tp_place)**",
                            description=(
                                f" **Ticker:** {ticker}\n"
                                f" **TP :** {target_price_1}\n"
                                f" **Exception:** {str(e)}"
                            ),
                            color=15158332,
                            sort=sort,
                            exchange="bybit",
                            time_frame="4h",
                            trade_id=trade_id
                        )
                    # Step 4: Place SL Order
                    sl = None
                    try:
                        sl_order_link_id = f"SL_{trade_id}"

                        if stop_loss is None:
                            sl = {"skipped": True, "retMsg": "StopLoss is None — skipped SL placement"}
                            send_discord_message(
                                title="⚠️ StopLoss skipped",
                                description=f"📌 **Ticker:** {ticker}\nℹ️ SL was not provided; skipped placing SL.",
                                color=15105570,
                                sort=sort,
                                exchange="bybit",
                                time_frame="4h",
                                trade_id=trade_id
                            )
                        else:
                            sl = place_sl_order(side, qty_norm, stop_loss, positionIdx, ticker, session, sl_order_link_id)

                        if is_ok_response(sl) or is_skipped_response(sl):
                            record_sl_result(result, sl)
                        else:
                            record_sl_result(result, sl, "❌ StopLoss 주문 실패")
                            logger.error(f"❌ StopLoss 주문 실패 : {sl}")

                    except Exception as e:
                        logger.exception("❌ StopLoss 주문 중 오류 발생")
                        sl = {"exception": str(e)}
                        record_sl_result(result, sl, "❌ StopLoss 주문 중 오류 발생")
                        send_discord_message(
                            title="🚨 **Unhandled Exception - place_order_4h.py (sl_place)**",
                            description=(
                                f" **Ticker:** {ticker}\n"
                                f" **Side:** {side}\n"
                                f" **qty:** {qty_norm}\n"
                                f" **Exception:** {str(e)}"
                            ),
                            color=15158332,
                            sort=sort,
                            exchange="bybit",
                            time_frame="4h",
                            trade_id=trade_id
                        )
            else:
                logger.error(f"❌ 주문 실패: {response}")

                err_msg = "❌ 주문 실패 open_order: " + response.get("retMsg", "Unknown error")
                record_open_result(result, response, err_msg)
                result["errors"].append(err_msg)

                send_discord_message(
                    title="❌ Open Order Failed (4h)",
                    description=(
                        f" **Ticker :** {ticker}\n"
                        f" **Side :** {side}\n"
                        f" **qty :** {qty_norm}\n"
                        f" **Response :** ```{response}```"
                    ),
                    color=15158332,
                    sort=sort,
                    exchange="bybit",
                    time_frame="4h",
                    trade_id=trade_id
                )
        except Exception as e:
            logger.exception("❌ Open Order 에서 예외 발생")
            err_msg = "❌ Open Order 에서 예외 발생: " + str(e)
            result["message"] = err_msg
            result["errors"].append(err_msg)
            send_discord_message(
                title="🚨 **Unhandled Exception - place_order_4h.py (open_order)**",
                description=(
                    f" **Ticker:** {ticker}\n"
                    f" **Side:** {side}\n"
                    f" **Qty:** {qty_norm}\n"
                    f" **Exception:** {str(e)}"
                ),
                color=15158332,
                sort=sort,
                exchange="bybit",
                time_frame="4h",
                trade_id=trade_id
            )
        return finalize_open_result(result)
    # CASE 2: Update StopLoss
    elif message_type == "update_sl":
        
        # Three Black Corw Positions Open (흑삼병) TP1 Hit 시 StopLoss Order Cancel
        if tbc_gubun == "tbc":
            try:
                if update_gubun == "tp1_hit":
                    # entry_price 를 이용하여 특정 SL 주문의 order_link_id 값 조회                    
                    sl_order = find_specific_sl_order(session, ticker, trade_id)
                    
                    logger.info(f"✅ sl_order : {sl_order}")

                    if sl_order:
                        sl_order_link_id = sl_order["orderLinkId"]
                        
                        logger.info(f"✅ 흑삼병 StopLoss 주문의 orderLinkId : {sl_order_link_id}")
                        
                        # SL 주문 취소 
                        cancel_result = session.cancel_order(
                            category="linear",
                            symbol=ticker,
                            orderLinkId=sl_order_link_id
                        )
                        if cancel_result.get("retCode") == 0:
                            # logger.info(f"✅ 흑삼병 TP Hit : StopLoss 주문 취소 완료 : {sl_order_link_id}")
                            update_result(result, "success", "✅ 흑삼병 TP Hit : 기존 StopLoss 주문 취소 완료" + cancel_result.get("retMsg", "None"), cancel_result)
                        else:
                            logger.error("❌ StopLoss 주문 취소 실패")
                            update_result(result, "failed", "❌ 흑삼병 TP Hit : But StopLoss 주문 취소 실패" + cancel_result.get("retMsg", "None"), cancel_result)
                            return result
                        # 혹시 잔여물량 남았는지 체크해서 만약 잔여물량이 남았다면 더스트 킬러 작동.
                        time.sleep(0.5)
                        kill_dust(session, ticker, positionIdx, step_qty="0.001",
                                sort=sort, exchange="bybit", time_frame="4h",
                                send_discord_message=send_discord_message,
                                notify="skipped")
                        synthetic = {"retCode": 0, "retMsg": "SL already cleaned up"}
                        update_result(result, "success", "✅ 흑삼병 TP1 Hit - 기존 StopLoss 주문 취소 및 잔여 정리 완료", synthetic)
                        return result
                    else:
                            msg = f"SL order not found for ticker={ticker}, side={side}, entry_price={entry_price}, trade_id={trade_id}"
                            logger.error(msg)
                            update_result(result, "failed", msg, {})
                            return result
                elif update_gubun == "sl_hit":
                    # 혹시 잔여물량 남았는지 체크해서 만약 잔여물량이 남았다면 더스트 킬러 작동.
                    time.sleep(0.5)
                    kill_dust(session, ticker, positionIdx, step_qty="0.001",
                            sort=sort, exchange="bybit", time_frame="4h",
                            send_discord_message=send_discord_message,
                            notify="skipped")
                    synthetic = {"retCode": 0, "retMsg": "SL already cleaned up"}
                    update_result(result, "success", "✅ 흑삼병 SL Hit - 잔여 정리 완료", synthetic)
                    return result
                else:
                    msg = f"❌ invalid update_gubun: {update_gubun}"
                    logger.error(msg)
                    update_result(result, "failed", msg, {})
                    return result
            except Exception as e:
                logger.exception("❌ Three Black Crow (흑삼병) sl_order_link_id 조회 중 오류 발생")
                update_result(result, "failed", "❌ Three Black Crow (흑삼병) sl_order_link_id 조회 중 오류 발생" + str(e), {})
                return result
            
        # Normal Long & Short Positions Open
        elif tbc_gubun == "n":
            try:
                if update_gubun == "tp1_hit":
                    # entry_price 를 이용하여 특정 SL 주문의 order_link_id 값 조회
                    sl_order = find_specific_sl_order(session, ticker, trade_id)

                    if sl_order:
                        sl_order_link_id = sl_order["orderLinkId"]
                        
                        logger.info(f"✅ StopLoss 주문의 orderLinkId : {sl_order_link_id}")
                        
                        # SL 주문 취소 
                        cancel_result = session.cancel_order(
                            category="linear",
                            symbol=ticker,
                            orderLinkId=sl_order_link_id
                        )
                        if cancel_result.get("retCode") == 0:
                            # logger.info(f"✅ TP 1 Hit : 기존 StopLoss 주문 취소 완료 : {sl_order_link_id}")
                            update_result(result, "success", "✅ TP 1 Hit 기존 StopLoss 주문 취소 완료" + cancel_result.get("retMsg", "None"), cancel_result)
                            
                        else:
                            logger.error("❌ TP 1 Hit StopLoss 주문 취소 실패")
                            update_result(result, "failed", "❌ TP 1 Hit : But StopLoss 주문 취소 실패" + cancel_result.get("retMsg", "None"), cancel_result)
                            return result
                        
                        time.sleep(2)

                        # TP 가 체결된 경우에는 더 이상 SL 등록 없음
                        logger.info("✅ TP 1 Hit - 잔여 StopLoss 주문 제거 완료")
                            
                        # 혹시 잔여물량 남았는지 체크해서 만약 잔여물량이 남았다면 더스트 킬러 작동.
                        time.sleep(0.5)
                        kill_dust(session, ticker, positionIdx, step_qty="0.001",
                                sort=sort, exchange="bybit", time_frame="4h",
                                send_discord_message=send_discord_message,
                                notify="skipped")  # 정상잔량이면 스킵 로그를 보내도록
                        synthetic = {"retCode": 0, "retMsg": "SL already cleaned up"}
                        update_result(result, "success", "✅ TP 1 Hit - 기존 StopLoss 주문 취소 및 잔여 정리 완료", synthetic)
                        return result
                    else:
                        msg = f"SL order not found for ticker={ticker}, side={side}, entry_price={entry_price}, trade_id={trade_id}"
                        logger.error(msg)
                        update_result(result, "failed", msg, {})
                        return result    
                elif update_gubun == "sl_hit":
                    logger.info("✅ SL Hit - 잔여 정리 완료")
                            
                    # 혹시 잔여물량 남았는지 체크해서 만약 잔여물량이 남았다면 더스트 킬러 작동.
                    time.sleep(0.5)
                    kill_dust(session, ticker, positionIdx, step_qty="0.001",
                            sort=sort, exchange="bybit", time_frame="4h",
                            send_discord_message=send_discord_message,
                            notify="skipped")
                    synthetic = {"retCode": 0, "retMsg": "SL already cleaned up"}
                    update_result(result, "success", "✅ SL Hit - 잔여 정리 완료", synthetic)
                    return result

                else:
                    msg = f"❌ invalid update_gubun: {update_gubun}"
                    logger.error(msg)
                    update_result(result, "failed", msg, {})
                    return result
            except Exception as e:
                logger.exception("❌ sl_order_link_id 조회 중 오류 발생")
                update_result(result, "failed", "❌ sl_order_link_id 조회 중 오류 발생" + str(e), {})
                return result
    else:
        logger.error(f"Unknown message_type: {message_type}")
        return {"bybit_status": "error", "message": f"Unknown message_type: {message_type}"}
    return result

def update_result(result, status, msg, data):
    result.update({
        "bybit_status": status,
        "message": msg,
        "data": data
    })
    if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
        result["order_id"] = data["result"].get("orderId")
        result["order_link_id"] = data["result"].get("orderLinkId")

def is_ok_response(resp):
    return isinstance(resp, dict) and resp.get("retCode") == 0

def is_skipped_response(resp):
    return isinstance(resp, dict) and resp.get("skipped") is True

def record_open_result(result, resp, msg=""):
    result["open_order"] = resp
    if isinstance(resp, dict) and "result" in resp and isinstance(resp["result"], dict):
        result["order_id"] = resp["result"].get("orderId")
        result["order_link_id"] = resp["result"].get("orderLinkId")
    if msg:
        result["message"] = msg

def record_tp_result(result, resp, err_msg=None):
    result["tp_order"] = resp
    if err_msg:
        result["errors"].append(err_msg)

def record_sl_result(result, resp, err_msg=None):
    result["sl_order"] = resp
    if err_msg:
        result["errors"].append(err_msg)

def finalize_open_result(result):
    open_ok = is_ok_response(result["open_order"])
    tp_ok = is_ok_response(result["tp_order"]) or is_skipped_response(result["tp_order"])
    sl_ok = is_ok_response(result["sl_order"]) or is_skipped_response(result["sl_order"])

    if open_ok and tp_ok and sl_ok:
        result["bybit_status"] = "success"
        if not result["message"]:
            result["message"] = "Open / TP / SL all succeeded"
    else:
        result["bybit_status"] = "failed"
        if result["errors"]:
            result["message"] = " | ".join(result["errors"])
        elif not result["message"]:
            result["message"] = "One or more order steps failed"

    return result
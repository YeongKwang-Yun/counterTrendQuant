import uuid
import logging

logger = logging.getLogger(__name__)

def _find_position(session, symbol, positionIdx):
    resp = session.get_positions(category="linear", symbol=symbol)
    if resp.get("retCode") != 0:
        raise RuntimeError(f"get_positions failed: {resp}")

    positions = resp.get("result", {}).get("list", [])
    for pos in positions:
        try:
            if int(pos.get("positionIdx", 0)) == int(positionIdx):
                size = float(pos.get("size", 0) or 0)
                return size, pos
        except Exception:
            continue

    return 0.0, None

def kill_dust(
    session, symbol, positionIdx, step_qty="0.001",
    sort=None, exchange="bybit", time_frame=None,
    send_discord_message=None,
    notify="acted"  # "acted" | "skipped" | "all"
): 
    """
    더스트 킬러:
    - abs(size) == 0      => no_position
    - 0 < abs(size) < step => reduceOnly Market 청산 (acted)
    - abs(size) >= step    => 정상 잔량. 기본은 조용히 스킵하지만,
                              notify="skipped" 또는 "all"이면 스킵 로그 전송.
    """
    try:
        step = float(step_qty)
    except Exception:
        step = 0.001
        step_qty = "0.001"

    size, meta = _find_position(session, symbol, positionIdx)
    abs_size = abs(size)

    # 완전 0 이면 종료
    if abs_size <= 0.0:
        if send_discord_message and notify in ("skipped", "all"):
            send_discord_message(
                title=f"ℹ️ Dust Killer skipped (no position) [{time_frame}]",
                description=(
                    f" **Symbol:** {symbol}\n"
                    f" **PosIdx:** {positionIdx}\n"
                    f" **Reason:** no_position"
                ),
                color=9807270,
                sort=sort, exchange=exchange, time_frame=time_frame or ""
            )
        return {"acted": False, "reason": "no_position", "size": abs_size}

    # 스텝 미만(=더스트)일 때만 실행
    if abs_size < step:
        side_to_close = "Sell" if size > 0 else "Buy"
        try:
            resp = session.place_order(
                category="linear",
                symbol=symbol,
                side=side_to_close,
                orderType="Market",
                qty=step_qty,               # step 만큼 보내도 reduceOnly라 실제 잔량만 체결
                reduceOnly=True,
                positionIdx=positionIdx,
                orderLinkId=f"DUSTKILLER_{symbol}_{positionIdx}_{uuid.uuid4().hex[:8]}"
            )
            ok = (resp.get("retCode") == 0 and resp.get("retMsg") == "OK")
            if ok:
                logger.info(f"✅ Dust killer executed: {symbol} posIdx={positionIdx}, size={abs_size}")
                if send_discord_message and notify in ("acted", "all"):
                    send_discord_message(
                        title=f"✅ Dust Killer executed [{time_frame}]",
                        description=(
                            f" **Symbol:** {symbol}\n"
                            f" **PosIdx:** {positionIdx}\n"
                            f" **Dust Size:** {abs_size}\n"
                            f" **API:** Market reduceOnly\n"
                            f" **Resp:** ```{resp}```"
                        ),
                        color=3066993,
                        sort=sort, exchange=exchange, time_frame=time_frame or ""
                    )
            else:
                logger.error(f"❌ Dust killer failed: {resp}")
                if send_discord_message:
                    send_discord_message(
                        title=f"❌ Dust Killer failed [{time_frame}]",
                        description=(
                            f" **Symbol:** {symbol}\n"
                            f" **PosIdx:** {positionIdx}\n"
                            f" **Dust Size:** {abs_size}\n"
                            f" **Response:** ```{resp}```"
                        ),
                        color=15158332,
                        sort=sort, exchange=exchange, time_frame=time_frame or ""
                    )
            return {"acted": ok, "response": resp, "size": abs_size}
        except Exception as e:
            logger.exception("Dust killer exception")
            if send_discord_message:
                send_discord_message(
                    title=f"🚨 Dust Killer exception [{time_frame}]",
                    description=(
                        f" **Symbol:** {symbol}\n"
                        f" **PosIdx:** {positionIdx}\n"
                        f" **Exception:** {str(e)}"
                    ),
                    color=15158332,
                    sort=sort, exchange=exchange, time_frame=time_frame or ""
                )
            return {"acted": False, "error": str(e), "size": abs_size}
    else:
        # 스텝 이상이면 더스트 아님 → 기본은 조용히 스킵
        if send_discord_message and notify in ("skipped", "all"):
            send_discord_message(
                title=f"ℹ️ Dust Killer skipped (normal position) [{time_frame}]",
                description=(
                    f" **Symbol:** {symbol}\n"
                    f" **PosIdx:** {positionIdx}\n"
                    f" **Current Size:** {abs_size}\n"
                    f" **Reason:** not_dust (>= {step_qty})"
                ),
                color=9807270,
                sort=sort, exchange=exchange, time_frame=time_frame or ""
            )
        return {"acted": False, "reason": "not_dust", "size": abs_size}
    
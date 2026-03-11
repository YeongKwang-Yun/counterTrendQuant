HIT_MAP_4H = {
    "tp1_hit": "TP1 Hit",
    "sl_hit": "SL Hit",
}

def build_4h_title(message_type: str | None, update_gubun: str | None, tbc_gubun: str | None) -> str:
    mt = (message_type or "").lower()
    ug = (update_gubun or "").lower()
    tbc = (tbc_gubun or "").lower()

    if mt == "open_order":
        base = "✅ 4h 주문 포지션 오픈 및 TP/SL 세팅 완료"
    elif mt == "update_sl":
        if ug == "tp1_hit":
            base = "✅ 4h 주문 TP1 Hit 및 SL 취소 완료"
        elif ug == "sl_hit":
            base = "✅ 4h 주문 SL Hit 후 잔여 정리 완료"
        else:
            base = "✅ 4h 주문 후속 처리 완료"
    else:
        base = "✅ 4h 주문 처리 완료"

    if tbc == "tbc":
        base += " [흑삼병]"

    return base
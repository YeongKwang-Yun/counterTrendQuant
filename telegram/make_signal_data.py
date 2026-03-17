import re
import logging
from common.env_loader import load_project_env

ENV_PATH = load_project_env()
logger = logging.getLogger(__name__)
# logger.info(f"ENV loaded from: {ENV_PATH}")

def _is_empty(v) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s == "" or s.lower() in ("na", "nan", "none")

def _fmt_price(v, digits=2) -> str | None:
    if _is_empty(v):
        return None
    s = str(v).strip()
    try:
        num = float(s.replace(",", ""))
        return f"{num:,.{digits}f}"
    except Exception:
        return s

def _to_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in ("1", "true", "y", "yes")

def escape_md2(text: str) -> str:
    if text is None:
        return ""
    return re.sub(r'([_*\[\]\(\)~`>#+\-=|{}.!])', r'\\\1', str(text))

def make_trade_notify_message_4h(data: dict) -> str:
    ticker = (data.get("ticker") or "N/A").replace("BINANCE:", "").replace("BYBIT:", "")
    side = (data.get("side") or "").lower()
    time_frame = data.get("time_frame")
    is_long = side in ("buy", "long")
    emoji = "🟢" if is_long else "🔴"
    direction = "Long" if is_long else "Short"

    tp_raw = data.get("notify_target_price_1")

    if _is_empty(tp_raw):
        tp_raw = data.get("target_price_1")

    # 2) 가격 포맷
    ep = _fmt_price(data.get("entry_price"), 2) or "N/A"
    tp = _fmt_price(tp_raw, 2) or "N/A"
    sl = _fmt_price(data.get("stop_loss"), 2) or "N/A"
    
    is_switching = _to_bool(data.get("is_switching"))
    prev_side = (data.get("prev_side") or "").strip()
    if prev_side.lower() in ("buy", "long"):
        prev_direction = "Long"
    elif prev_side.lower() in ("sell", "short"):
        prev_direction = "Short"
    else:
        prev_direction = ""

    # 3) 헤더
    title_line = f"{emoji} {ticker} {direction} Signal"
    if is_switching:
        title_line += " (Switching)"
        
    # 4) 본문
    body_lines = [
        title_line,
        f"EP : {ep} $",
        f"TP : {tp} $",
        f"SL : {sl} $",
        "",
        f"{time_frame} 타임프레임 기준으로 발생한 시그널입니다.\n",
    ]
    if is_switching:
        if prev_side:
            body_lines.append(f"{prev_direction} 포지션 보유 중 {direction} 시그널 발생")
        else:
            body_lines.append(f"반대 방향 포지션 보유 중에 {direction} 시그널이 발생했습니다.")
        body_lines.append(f"봇은 스위칭하여 {direction} 포지션을 오픈했습니다.\n")

    body_lines.append("시스템 트레이딩 관점에 대한 공유일 뿐,")
    body_lines.append("고토봇은 투자를 유도하지 않습니다.")
    title = escape_md2(f"GotoBot Quant Signal - {ticker} ({time_frame})")
    body = "\n".join(body_lines)

    return f"*{title}*\n```text\n{body}\n```"

def make_signal_message(data: dict) -> str:
    side = (data.get("side") or "").lower()
    is_long = side in ("buy", "long")

    emoji = "🟢" if is_long else "🔴"
    direction = "Long" if is_long else "Short"

    ep = _fmt_price(data.get("entry_price"), 1) or "N/A"
    sl = _fmt_price(data.get("stop_loss"), 1) or "N/A"

    time_frame = (data.get("time_frame") or "").lower()
    if time_frame == "1d":
        tf = "1D"
    else:
        tf = data.get("time_frame") or "N/A"

    title = escape_md2(f"{emoji} GotoBot Nasdaq Signal ({tf})")

    body_lines = [
        f"Nasdaq {direction} Signal",
        f"EP : {ep} $",
        f"SL : {sl} $",
        "",
        f"{tf} 타임프레임 기준으로 발생한 시그널입니다.",
        "나스닥 장기 추세에 대한 공유일 뿐,",
        "고토봇은 투자를 유도하지 않습니다."
    ]

    body = "\n".join(body_lines)
    return f"*{title}*\n```text\n{body}\n```"


# 
# 여기는 TP 가 여러 개 인 CASE 에서 사용.
# 
# 
# def make_trade_notify_message_4h(data: dict) -> str:
#     # 1) 이벤트 라벨 + 체크 상태 결정
#     ticker = (data.get("ticker") or "N/A").replace("BINANCE:", "").replace("BYBIT:", "")
#     side = (data.get("side") or "").lower()
#     is_long = side in ("buy", "long")
#     emoji = "🟢" if is_long else "🔴"

#     message_type = (data.get("message_type") or "").lower()
#     update_gubun  = (data.get("update_gubun") or "").lower()

#     # open / tp hit / sl hit
#     if message_type == "open_order":
#         event_label = "Long Open" if is_long else "Short Open"
#         hit_tp1 = hit_tp2 = hit_tp3 = hit_sl = False
#     elif message_type == "update_sl":
#         if update_gubun == "first":
#             event_label = "TP 1 Hit"
#             hit_tp1, hit_tp2, hit_tp3, hit_sl = True, False, False, False
#         elif update_gubun == "second":
#             event_label = "TP 2 Hit"
#             hit_tp1, hit_tp2, hit_tp3, hit_sl = True, True, False, False
#         elif update_gubun == "third":
#             event_label = "TP 3 Hit"
#             hit_tp1, hit_tp2, hit_tp3, hit_sl = True, True, True, False
#         elif update_gubun == "sl_hit":
#             event_label = "SL Hit"
#             hit_tp1 = hit_tp2 = hit_tp3 = False
#             hit_sl = True
#         else:
#             event_label = "Update"
#             hit_tp1 = hit_tp2 = hit_tp3 = hit_sl = False
#     else:
#         event_label = "Trade"
#         hit_tp1 = hit_tp2 = hit_tp3 = hit_sl = False

#     # 2) 가격 포맷
#     ep = _fmt_price(data.get("entry_price"), 2) or "N/A"
#     sl = _fmt_price(data.get("stop_loss"), 2)

#     tp1 = _fmt_price(data.get("target_price_1"), 2)
#     tp2 = _fmt_price(data.get("target_price_2"), 2)
#     tp3 = _fmt_price(data.get("target_price_3"), 2)

#     # 3) TP 존재하는 것만 출력 + 체크표시
#     tp_rows = []
#     if tp1 is not None: tp_rows.append(("TP 1", tp1, hit_tp1))
#     if tp2 is not None: tp_rows.append(("TP 2", tp2, hit_tp2))
#     if tp3 is not None: tp_rows.append(("TP 3", tp3, hit_tp3))

#     # 4) 본문(정렬은 코드블록에서 해결)
#     sep = "_" * 27
#     body_lines = [
#         sep,
#         f"{emoji} {ticker} {event_label}",
#         f"EP   :  {ep} $",
#     ]

#     for label, price, checked in tp_rows:
#         ck = "   ✅" if checked else ""
#         body_lines.append(f"{label} :  {price} $"+ck)

#     if sl is not None:
#         ck = "   ✅" if hit_sl else ""
#         # 'SL' 라벨 폭 맞춤
#         body_lines.append(f"SL   :  {sl} $"+ck)

#     body_lines.append(sep)

#     # 5) 최종: 제목은 굵게(escape) + 본문은 코드블록
#     title = escape_md2("4h Quant Bot Signal Test 테스트 진행 중")
#     body = "\n".join(body_lines)

#     # MarkdownV2 코드블록
#     return f"*{title}*\n```text\n{body}\n```"


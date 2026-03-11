import logging

logger = logging.getLogger(__name__)

def place_tp_order(side, qty, price, positionIdx, ticker, session, order_link_id):
    # 일반 리밋 TP (reduceOnly)
    return session.place_order(
        category="linear",
        symbol=ticker,
        side="Sell" if side == "Buy" else "Buy",
        orderType="Limit",
        qty=str(qty),
        price=str(price),
        reduceOnly=True,
        positionIdx=positionIdx,
        orderLinkId=order_link_id
    )

def place_tp_order_conditional(side, qty, limit_price, trigger_price, trigger_direction, positionIdx, ticker, session, order_link_id):
    # 조건부(트리거) TP: 트리거 발생 시 Limit로 제출
    # trigger_direction: 1(Long TP), 2(Short TP)
    return session.place_order(
        category="linear",
        symbol=ticker,
        side="Sell" if side == "Buy" else "Buy",
        orderType="Limit",
        qty=str(qty),
        price=str(limit_price),
        triggerPrice=str(trigger_price),
        triggerDirection=int(trigger_direction),
        reduceOnly=True,
        positionIdx=positionIdx,
        timeInForce="PostOnly",
        orderLinkId=order_link_id
    )
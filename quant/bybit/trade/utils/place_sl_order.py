def place_sl_order(side, qty, price, positionIdx, ticker, session, order_link_id):
    return session.place_order(
        category="linear",
        symbol=ticker,
        side="Sell" if side == "Buy" else "Buy",  # ➜ SL도 진입 반대방향
        orderType="Market",
        triggerDirection=2 if side == "Buy" else 1,
        triggerPrice=price,
        qty=qty,
        positionIdx=positionIdx,
        reduceOnly=True,
        orderLinkId=order_link_id
    )
    
def find_specific_sl_order(session, ticker, trade_id):
    response = session.get_open_orders(category="linear", symbol=ticker)

    if response.get("retCode") != 0:
        raise RuntimeError(f"get_open_orders failed: {response}")

    orders = response.get("result", {}).get("list", [])
    expected_order_link_id = f"SL_{trade_id}"

    for o in orders:
        if o.get("orderLinkId", "") == expected_order_link_id:
            return o

    return None
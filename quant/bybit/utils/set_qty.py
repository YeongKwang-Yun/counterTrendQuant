from decimal import Decimal, ROUND_DOWN, ROUND_UP

STEP = Decimal("0.001")

def normalize_qty_str(qty_str: str, step: Decimal = STEP, mode: str = "floor") -> str:
    q = Decimal(str(qty_str))
    n = q / step

    if mode == "ceil":
        n = n.to_integral_value(rounding=ROUND_UP)
    else:
        n = n.to_integral_value(rounding=ROUND_DOWN)

    return f"{(n * step):.3f}"

def qty_to_lots(qty_str: str, step: Decimal = STEP) -> int:
    q = Decimal(str(qty_str))
    return int((q / step).to_integral_value(rounding=ROUND_DOWN))

def lots_to_qty_str(lots: int, step: Decimal = STEP) -> str:
    return f"{(Decimal(lots) * step):.3f}"

def split_lots(total_lots: int, p1: float = 0.5, p2: float = 0.3):
    n1 = int(Decimal(total_lots) * Decimal(str(p1)))
    n2 = int(Decimal(total_lots) * Decimal(str(p2)))
    n3 = total_lots - n1 - n2
    return n1, n2, n3
from typing import Optional

def calculate_total(subtotal: float, tax_rate: Optional[float] = None) -> float:
    global TAX_RATE
    # BUG: relies on global TAX_RATE that doesn't exist if tax_rate is None
    if tax_rate is None:
        return subtotal * (1 + TAX_RATE)  # NameError here
    return round(subtotal * (1 + tax_rate), 2)
    return round(subtotal * (1 + tax_rate), 2)
# Bug #5: uses undefined TAX_RATE when not provided via env/config.

def calculate_total(subtotal: float, tax_rate: float | None = None) -> float:
    # BUG: relies on global TAX_RATE that doesn't exist if tax_rate is None
    if tax_rate is None:
        return subtotal * (1 + TAX_RATE)  # NameError here
    return round(subtotal * (1 + tax_rate), 2)

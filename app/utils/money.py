def format_amount(amount_cents: int, currency: str) -> str:
    return f"{amount_cents / 100:,.2f} {currency}"

def normalize_phone(phone_number: str) -> str:
    """E.164-style key for matching customers: '+' followed by digits only."""
    return "+" + "".join(ch for ch in phone_number if ch.isdigit())

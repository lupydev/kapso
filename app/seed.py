"""Seed demo invoices for a customer: `uv run python -m app.seed --phone +573001112233`."""

import argparse

from sqlmodel import Session, select

from app.core.db import get_engine
from app.models import Invoice
from app.services import billing
from app.utils.phone import normalize_phone

DEMO_INVOICES = [
    (8990000, "Internet - October"),
    (15430000, "Electricity - October"),
    (4210000, "Water - October"),
    (120000000, "Rent - November"),
]


def seed_demo_invoices(session: Session, phone_number: str, currency: str = "COP") -> list[Invoice]:
    """Create the demo invoices once per customer; returns the ones created."""
    already_seeded = session.exec(
        select(Invoice).where(Invoice.phone_number == normalize_phone(phone_number))
    ).first()
    if already_seeded:
        return []
    invoices = [
        billing.create_invoice(session, phone_number, amount_cents, currency, description)
        for amount_cents, description in DEMO_INVOICES
    ]
    session.commit()
    return invoices


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phone", required=True, help="Customer WhatsApp number, e.g. +573001112233")
    parser.add_argument("--currency", default="COP")
    args = parser.parse_args()
    with Session(get_engine()) as session:
        created = seed_demo_invoices(session, args.phone, args.currency)
    print(f"Created {len(created)} invoices" if created else "Customer already has invoices; nothing created")


if __name__ == "__main__":
    main()

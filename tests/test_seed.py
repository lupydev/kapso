from sqlmodel import Session, select

from app.models import Invoice
from app.seed import DEMO_INVOICES, seed_demo_invoices


def test_seed_creates_demo_invoices_once(engine):
    with Session(engine) as session:
        first = seed_demo_invoices(session, "+57 300 111 2233")
        second = seed_demo_invoices(session, "573001112233")
        invoices = session.exec(select(Invoice)).all()

    assert len(first) == len(DEMO_INVOICES)
    assert second == []
    assert len(invoices) == len(DEMO_INVOICES)
    assert {invoice.phone_number for invoice in invoices} == {"+573001112233"}
    assert all(invoice.status == "pending" for invoice in invoices)

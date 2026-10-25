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


def test_seed_command_uses_seed_phone_from_the_environment(engine, monkeypatch, capsys):
    from app import seed

    monkeypatch.setattr(seed, "get_engine", lambda: engine)
    monkeypatch.setenv("SEED_PHONE", "+57 300 111 2233")
    monkeypatch.setattr("sys.argv", ["seed"])

    seed.main()

    assert "Created 4 invoices" in capsys.readouterr().out


def test_seed_command_is_a_no_op_without_a_phone(engine, monkeypatch, capsys):
    # Runs as Railway's pre-deploy command: a missing SEED_PHONE must not fail the deploy.
    from app import seed

    monkeypatch.setattr(seed, "get_engine", lambda: engine)
    monkeypatch.delenv("SEED_PHONE", raising=False)
    monkeypatch.setattr("sys.argv", ["seed"])

    seed.main()

    assert "SEED_PHONE not set" in capsys.readouterr().out
    with Session(engine) as session:
        assert session.exec(select(Invoice)).all() == []

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Invoice, PaymentLink, get_session
from app.kapso import KapsoError, get_kapso
from app.main import app

SECRET = "test-secret"
CUSTOMER = "+573001112233"


class FakeKapso:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.fail_next = False

    def send_text(self, to: str, body: str) -> None:
        self._record({"to": to, "kind": "text", "body": body})

    def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]]) -> None:
        self._record({"to": to, "kind": "buttons", "body": body, "buttons": buttons})

    def _record(self, message: dict) -> None:
        if self.fail_next:
            self.fail_next = False
            raise KapsoError("boom")
        self.sent.append(message)


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def kapso():
    return FakeKapso()


@pytest.fixture
def client(engine, kapso):
    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_kapso] = lambda: kapso
    app.dependency_overrides[get_settings] = lambda: Settings(
        kapso_api_key="k",
        kapso_phone_number_id="123",
        kapso_webhook_secret=SECRET,
        public_base_url="https://example.test",
        invoice_amount_cents=5000000,
        invoice_currency="COP",
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def inbound(message_id: str, *, text: str | None = None, button: str | None = None) -> dict:
    if button:
        message = {
            "id": message_id,
            "type": "interactive",
            "interactive": {"type": "button_reply", "button_reply": {"id": button, "title": button}},
        }
    else:
        message = {"id": message_id, "type": "text", "text": {"body": text or "hi"}}
    return {
        "message": message,
        "conversation": {"id": "conv_1", "phone_number": CUSTOMER, "phone_number_id": "123"},
        "phone_number_id": "123",
    }


def post_event(client, payload: dict, *, secret: str = SECRET, event: str = "whatsapp.message.received"):
    raw = json.dumps(payload).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/kapso",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Event": event,
            "X-Webhook-Signature": signature,
        },
    )


def test_rejects_invalid_signature(client, kapso):
    response = post_event(client, inbound("wamid.1"), secret="wrong")

    assert response.status_code == 401
    assert kapso.sent == []


def test_ignores_other_events(client, kapso):
    response = post_event(client, inbound("wamid.1"), event="whatsapp.message.delivered")

    assert response.status_code == 200
    assert kapso.sent == []


def test_text_message_replies_with_invoice_buttons(client, kapso, engine):
    response = post_event(client, inbound("wamid.1", text="hola"))

    assert response.status_code == 200
    assert len(kapso.sent) == 1
    reply = kapso.sent[0]
    assert reply["to"] == CUSTOMER
    assert reply["kind"] == "buttons"
    assert "50,000.00 COP" in reply["body"]
    assert [button_id for button_id, _ in reply["buttons"]] == ["pay", "paid"]
    with Session(engine) as session:
        invoices = session.exec(select(Invoice)).all()
    assert len(invoices) == 1
    assert invoices[0].status == "pending"


def test_duplicate_delivery_is_processed_once(client, kapso, engine):
    first = post_event(client, inbound("wamid.1", text="hola"))
    second = post_event(client, inbound("wamid.1", text="hola"))

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(kapso.sent) == 1
    with Session(engine) as session:
        assert len(session.exec(select(Invoice)).all()) == 1


def test_pay_button_returns_the_same_link_every_time(client, kapso, engine):
    post_event(client, inbound("wamid.1", text="hola"))
    post_event(client, inbound("wamid.2", button="pay"))
    post_event(client, inbound("wamid.3", button="pay"))

    links = [m["body"] for m in kapso.sent[1:]]
    assert len(links) == 2
    assert links[0] == links[1]
    assert "https://example.test/pay/" in links[0]
    with Session(engine) as session:
        assert len(session.exec(select(PaymentLink)).all()) == 1


def test_paid_button_before_paying_reports_pending(client, kapso):
    post_event(client, inbound("wamid.1", text="hola"))
    post_event(client, inbound("wamid.2", button="paid"))

    assert "not received" in kapso.sent[-1]["body"]


def test_checkout_confirmation_marks_invoice_paid_once(client, kapso, engine):
    post_event(client, inbound("wamid.1", text="hola"))
    post_event(client, inbound("wamid.2", button="pay"))
    with Session(engine) as session:
        token = session.exec(select(PaymentLink)).one().token

    page = client.get(f"/pay/{token}")
    first = client.post(f"/pay/{token}/confirm")
    second = client.post(f"/pay/{token}/confirm")

    assert page.status_code == 200
    assert "50,000.00 COP" in page.text
    assert first.status_code == 200
    assert second.status_code == 200
    receipts = [m for m in kapso.sent if "Payment received" in m["body"]]
    assert len(receipts) == 1
    with Session(engine) as session:
        assert session.exec(select(Invoice)).one().status == "paid"

    post_event(client, inbound("wamid.3", button="paid"))
    assert "already paid" in kapso.sent[-1]["body"]


def test_unknown_payment_link_returns_404(client):
    assert client.get("/pay/nope").status_code == 404
    assert client.post("/pay/nope/confirm").status_code == 404


def test_failed_send_returns_500_so_kapso_retries(client, kapso):
    kapso.fail_next = True
    failed = post_event(client, inbound("wamid.1", text="hola"))
    retried = post_event(client, inbound("wamid.1", text="hola"))

    assert failed.status_code == 500
    assert retried.status_code == 200
    assert len(kapso.sent) == 1

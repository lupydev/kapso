import pytest
from sqlmodel import Session, select

from app.models import WebhookEvent
from app.services import events
from tests.support import CUSTOMER, inbound, post_event, post_raw


def _events(engine) -> list[WebhookEvent]:
    with Session(engine) as session:
        return list(session.exec(select(WebhookEvent).order_by(WebhookEvent.id)).all())


def test_every_verified_delivery_is_logged_with_its_outcome(client, kapso, engine, seed):
    seed((100, "Internet - October"))

    post_event(client, inbound("wamid.1", text="hola"))
    post_event(client, inbound("wamid.1", text="hola"))
    post_event(client, inbound("wamid.2"), event="whatsapp.message.delivered")
    post_raw(client, b"not json")
    kapso.fail_next = True
    post_event(client, inbound("wamid.3", text="hola"))

    logged = [(e.event_type, e.message_id, e.outcome, e.status_code) for e in _events(engine)]
    assert logged == [
        ("whatsapp.message.received", "wamid.1", "processed", 200),
        ("whatsapp.message.received", "wamid.1", "duplicate", 200),
        ("whatsapp.message.delivered", None, "ignored", 200),
        ("whatsapp.message.received", None, "malformed", 400),
        ("whatsapp.message.received", "wamid.3", "retry", 500),
    ]
    first = _events(engine)[0]
    assert first.phone_number == CUSTOMER
    assert '"wamid.1"' in first.payload


def test_unsigned_requests_are_not_logged(client, engine):
    post_event(client, inbound("wamid.1", text="hola"), secret="wrong")

    assert _events(engine) == []


def test_logging_failure_does_not_change_the_response(client, kapso, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(events, "record_webhook", broken)

    response = post_event(client, inbound("wamid.1", text="hola"))

    assert response.status_code == 200
    assert response.json() == {"status": "processed"}
    assert len(kapso.sent) == 1


def test_large_payloads_are_truncated(client, engine):
    payload = inbound("wamid.1", text="x" * 50_000)

    post_event(client, payload)

    assert len(_events(engine)[0].payload) == events.MAX_PAYLOAD_CHARS

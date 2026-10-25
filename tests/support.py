"""Shared test doubles and request builders."""

import hashlib
import hmac
import json

from app.services.messaging import KapsoError

SECRET = "test-secret"
CUSTOMER = "+573001112233"


class FakeKapso:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.fail_next = False
        self.fail_retryable = True

    def send_text(self, to: str, body: str) -> None:
        self._record({"to": to, "kind": "text", "body": body})

    def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]]) -> None:
        self._record({"to": to, "kind": "buttons", "body": body, "buttons": buttons})

    def _record(self, message: dict) -> None:
        if self.fail_next:
            self.fail_next = False
            raise KapsoError("boom", retryable=self.fail_retryable)
        self.sent.append(message)


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


def post_raw(client, raw: bytes, *, secret: str = SECRET, event: str = "whatsapp.message.received"):
    """POST raw bytes to the webhook, signed the way Kapso signs them."""
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


def post_event(client, payload: dict, *, secret: str = SECRET, event: str = "whatsapp.message.received"):
    return post_raw(client, json.dumps(payload).encode(), secret=secret, event=event)

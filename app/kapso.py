from typing import Annotated, Protocol

import httpx
from fastapi import Depends

from app.config import Settings, get_settings

GRAPH_VERSION = "v24.0"


class KapsoError(Exception):
    pass


class Messenger(Protocol):
    def send_text(self, to: str, body: str) -> None: ...

    def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]]) -> None: ...


class KapsoClient:
    """Sends WhatsApp messages through Kapso's Meta-compatible proxy."""

    def __init__(self, settings: Settings) -> None:
        self._url = (
            f"{settings.kapso_api_base_url}/meta/whatsapp/{GRAPH_VERSION}"
            f"/{settings.kapso_phone_number_id}/messages"
        )
        self._headers = {"X-API-Key": settings.kapso_api_key}

    def send_text(self, to: str, body: str) -> None:
        self._send({"to": to, "type": "text", "text": {"body": body}})

    def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]]) -> None:
        self._send(
            {
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": button_id, "title": title}}
                            for button_id, title in buttons
                        ]
                    },
                },
            }
        )

    def _send(self, message: dict) -> None:
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual", **message}
        try:
            response = httpx.post(self._url, json=payload, headers=self._headers, timeout=8)
        except httpx.HTTPError as exc:
            raise KapsoError(f"Kapso request failed: {exc}") from exc
        if response.is_error:
            raise KapsoError(f"Kapso returned {response.status_code}: {response.text}")


def get_kapso(settings: Annotated[Settings, Depends(get_settings)]) -> Messenger:
    return KapsoClient(settings)

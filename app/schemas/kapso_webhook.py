from pydantic import BaseModel, ConfigDict

MESSAGE_RECEIVED = "whatsapp.message.received"


class _Lenient(BaseModel):
    # As permissive as the payload allows: a rejected webhook (400) is never retried by
    # Kapso, so the message would be lost. Numbers are accepted where strings are expected.
    model_config = ConfigDict(coerce_numbers_to_str=True)


class Reply(_Lenient):
    id: str | None = None


class Interactive(_Lenient):
    button_reply: Reply | None = None
    list_reply: Reply | None = None


class InboundMessage(_Lenient):
    id: str
    interactive: Interactive | None = None

    @property
    def selection_id(self) -> str | None:
        """ID of the tapped reply button or chosen list row, if any."""
        if not self.interactive:
            return None
        reply = self.interactive.list_reply or self.interactive.button_reply
        return reply.id if reply else None


class Conversation(_Lenient):
    phone_number: str


class MessageReceived(_Lenient):
    """The parts of Kapso's `whatsapp.message.received` payload (v2) this app reads."""

    message: InboundMessage
    conversation: Conversation

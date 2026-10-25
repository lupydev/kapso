from pydantic import BaseModel, ConfigDict

MESSAGE_RECEIVED = "whatsapp.message.received"


class _Lenient(BaseModel):
    # As permissive as the payload allows: a rejected webhook (400) is never retried by
    # Kapso, so the message would be lost. Numbers are accepted where strings are expected.
    model_config = ConfigDict(coerce_numbers_to_str=True)


class ButtonReply(_Lenient):
    id: str | None = None


class Interactive(_Lenient):
    button_reply: ButtonReply | None = None


class InboundMessage(_Lenient):
    id: str
    interactive: Interactive | None = None

    @property
    def button_id(self) -> str | None:
        if self.interactive and self.interactive.button_reply:
            return self.interactive.button_reply.id
        return None


class Conversation(_Lenient):
    phone_number: str


class MessageReceived(_Lenient):
    """The parts of Kapso's `whatsapp.message.received` payload (v2) this app reads."""

    message: InboundMessage
    conversation: Conversation

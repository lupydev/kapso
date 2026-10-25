from pydantic import BaseModel, Field

MESSAGE_RECEIVED = "whatsapp.message.received"


class ButtonReply(BaseModel):
    id: str


class Interactive(BaseModel):
    button_reply: ButtonReply | None = None


class InboundMessage(BaseModel):
    id: str = Field(min_length=1)
    interactive: Interactive | None = None

    @property
    def button_id(self) -> str | None:
        if self.interactive and self.interactive.button_reply:
            return self.interactive.button_reply.id
        return None


class Conversation(BaseModel):
    phone_number: str = Field(min_length=1)


class MessageReceived(BaseModel):
    """The parts of Kapso's `whatsapp.message.received` payload (v2) this app reads."""

    message: InboundMessage
    conversation: Conversation

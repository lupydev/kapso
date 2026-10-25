# Kapso payment collection

A WhatsApp payment-collection bot built on [Kapso](https://kapso.ai) by a coding agent. The agent used only Kapso's agent surfaces: the Project MCP, `@kapso/cli`, the `gokapso/agent-skills` skills and the docs MCP.

The experiment and what it found about building on Kapso with an agent are in [`AGENT_DX_REPORT.md`](AGENT_DX_REPORT.md). The raw evidence is in [`FRICTION_LOG.md`](FRICTION_LOG.md).

## What it does

1. A customer sends any message to the WhatsApp number.
2. The bot replies with their pending invoice and two buttons: **Pay** and **I already paid**.
3. **Pay** returns a link to a simulated checkout. Repeated taps return the same link.
4. Confirming the checkout marks the invoice paid and sends a receipt on WhatsApp, once.
5. **I already paid** reports whether the payment was received.

No real money moves. The checkout page stands in for a payment provider.

## Reliability

Kapso retries a webhook when it doesn't get a 200. The handler is built around that:

| Concern | How it's handled |
| --- | --- |
| Forged requests | `X-Webhook-Signature` is checked as hex HMAC-SHA256 of the raw body before parsing. Bad or malformed signatures get `401`. |
| Duplicate deliveries | The inbound `message.id` is the primary key of `ProcessedMessage`, claimed in the same transaction as the work. A redelivery returns `200 {"status": "duplicate"}` and sends nothing. |
| Transient send failures | A Kapso 5xx, 429 or timeout rolls back the claim and returns `500`, so Kapso retries. |
| Permanent send failures | Any other Kapso 4xx (e.g. no sandbox session) keeps the claim and returns `200 {"status": "undeliverable"}`, because a retry would fail the same way. |
| Unusable payloads | A signed body that isn't valid JSON, or has no `message` or `conversation.phone_number`, gets `400`. |
| Double-submitted checkout | The invoice is marked paid with a conditional `UPDATE ... WHERE status != 'paid'`. Only the request that changed the row sends a receipt. |
| Receipt can't be sent | The payment is committed first and the receipt is best-effort. A receipt that fails (e.g. outside the 24-hour window) is logged; the payment still counts. |

These were checked against live Kapso: three replays of a real signed webhook were acknowledged as duplicates with no extra outbound messages, and a Kapso test delivery that used to fail after 3 attempts now succeeds on the first.

## Project layout

```text
app/
  config.py   Settings from .env and .env.local
  db.py       SQLModel tables: ProcessedMessage, Invoice, PaymentLink
  kapso.py    Kapso client (Meta-compatible proxy) and error classification
  billing.py  Invoice, payment link and receipt logic
  main.py     FastAPI routes: webhook, checkout page, confirm
tests/
  test_webhook.py
```

| Route | Purpose |
| --- | --- |
| `POST /webhooks/kapso` | Kapso `whatsapp.message.received` webhook (payload v2) |
| `GET /pay/{token}` | Simulated checkout page |
| `POST /pay/{token}/confirm` | Mark the invoice paid and send the receipt |

## Run it locally

Requirements: [uv](https://docs.astral.sh/uv/), [`@kapso/cli`](https://docs.kapso.ai/docs/whatsapp/cli) logged in to your project, a WhatsApp number in Kapso (the sandbox works), and [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) or another tunnel.

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Create a `.env` file (gitignored) with your project API key, then find your `phone_number_id`:

   ```bash
   echo 'KAPSO_API_KEY=<your-api-key>' > .env
   kapso whatsapp numbers list --output json
   ```

3. Expose port 8000 and note the `https://…trycloudflare.com` URL it prints:

   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```

4. Generate a webhook secret and create the webhook. The secret goes into `.env.local` (gitignored) and is never printed:

   ```bash
   SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
   URL=https://<your-tunnel>.trycloudflare.com
   cat > .env.local <<EOF
   KAPSO_PHONE_NUMBER_ID=<phone_number_id>
   KAPSO_WEBHOOK_SECRET=$SECRET
   PUBLIC_BASE_URL=$URL
   EOF
   kapso whatsapp webhooks new --phone-number-id <phone_number_id> \
     --url "$URL/webhooks/kapso" --event whatsapp.message.received \
     --payload-version v2 --no-buffer-enabled --active --secret-key "$SECRET"
   ```

5. Start the app:

   ```bash
   uv run fastapi dev
   ```

6. Message the number from WhatsApp. With the sandbox, send any message to the sandbox chat first: activating the session doesn't open the 24-hour window, so the bot's first reply would fail without it.

A quick tunnel gets a new URL every time it restarts. Update `PUBLIC_BASE_URL` and the webhook URL (`kapso whatsapp webhooks update`) when that happens.

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `KAPSO_API_KEY` | yes | | Kapso project API key |
| `KAPSO_PHONE_NUMBER_ID` | yes | | Number that sends replies |
| `KAPSO_WEBHOOK_SECRET` | yes | | Secret used to verify webhook signatures |
| `PUBLIC_BASE_URL` | yes | | Public URL used in payment links |
| `KAPSO_API_BASE_URL` | no | `https://api.kapso.ai` | Kapso API host |
| `DATABASE_URL` | no | `sqlite:///db.sqlite3` | SQLModel database URL |
| `INVOICE_AMOUNT_CENTS` | no | `5000000` | Demo invoice amount (50,000.00) |
| `INVOICE_CURRENCY` | no | `COP` | Demo invoice currency |

## Tests

```bash
uv run pytest
```

The tests run the FastAPI app against an in-memory SQLite database with a fake Kapso client. They cover signature checks, duplicate and retried deliveries, permanent and transient send failures, idempotent payment links, and a double-confirm race on a file-backed database.

## Known limitations

- Demo scope: one invoice per customer, simulated payments, no CSRF protection on the checkout form (the 128-bit token is the only credential).
- SQLite holds its write lock during the Kapso HTTP call. That's fine at demo traffic; a real deployment should use Postgres or send replies after commit.
- If a send times out but actually reached WhatsApp, the retry sends it again.
- Batched webhooks (`X-Webhook-Batch`) aren't supported; keep buffering off.
- A `message` without an `id` returns `500` instead of `400`. Kapso always sends one, so this is untested hardening work.

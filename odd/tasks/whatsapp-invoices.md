# WhatsApp invoices: pick and pay, webhook event log, admin panel

Objective: replace the auto-created demo invoice with seeded invoices the customer lists and picks from WhatsApp, log every verified webhook, and show both in an admin page.
Branch: `feat/payment-collection` · Delivery: commits on the existing stacked branch · Tests: `uv run pytest`

## Specs

- **S1 — Seeded invoices.** User: "para que la app se accesible se debe de crear un database". Invoices come from a seed command, several per customer, each with a description. Inbound messages no longer create invoices.
- **S2 — Pick an invoice from the chat.** User: "desde el chat de kapso se deberia poder preguntar por los invoices y escoger uno en aprticular para pagar". Any message replies with a WhatsApp list of the customer's pending invoices (max 10 rows; title ≤ 24, description ≤ 72, button ≤ 20). Choosing a row sends the payment link for that invoice. No pending invoices → a text saying so. A row for an invoice that isn't the sender's or isn't pending must not produce a link.
- **S3 — Webhook event log.** User: "valdria la pena guardar en la db los eventos de los webhooks y se puedan consultar". Every signature-verified webhook request is stored with event type, message id, phone, outcome and status code, including ignored, malformed, duplicate and retried ones. Unsigned requests are not stored.
- **S4 — Admin page.** Server-rendered HTML at `/admin` listing invoices and recent webhook events. Not public: protected by a configured password; disabled when none is set. (Assumption: HTTP Basic auth with `ADMIN_PASSWORD`.)
- Out of scope (agreed): SPA frontend with `app.frontend()`.

## Tasks

| ID | Specs | Route | Status | Commit |
| --- | --- | --- | --- | --- |
| T1 | S1, S2 | inline | done (RED→GREEN, 43 tests) | 38401f4 |
| T2 | S3 | inline | done (RED→GREEN, 47 tests) | cc11da3 |
| T3 | S4 | inline | done (RED→GREEN, 54 tests) | 4f00622, docs afd7a3a |
| T4 | all | verifier (item 2: admin auth) | done: S1–S4 pass, no blockers; advisory fixed | 87b1c5c |

## Log

- **L1** (2026-10-25, user, verbatim): "para que la app se accesible se debe de crear un database y desde el chat de kapso se deberia poder preguntar por los invoices y escoger uno en aprticular para pagar o algo asi, porque cuando le envio un mensaje al whatsapp es que se crea el invoice y si se unde pay hasta ahi queda toda la ejecucion, ademas de que valdria la pena guardar en la db los eventos de los webhooks y se puedan consultar no? fastapi ya permite frontend no?"
- **L2** (2026-10-25, user): "dale, vamos con ese alcance" — seeded invoices, list picker, webhook event table, server-rendered `/admin`; no SPA.
- **L3**: Adding `Invoice.description` and new tables needs a fresh `db.sqlite3` (no migrations; demo data only).
- **L4**: Moved the live `db.sqlite3` to `db.sqlite3.bak` (reversible, gitignored), seeded 4 demo invoices for the user's number from `.env` without printing it, and touched `app/main.py` to reload the dev server.
- **L5**: Kapso docs show the inbound `button_reply` payload but not `list_reply`; used Meta's standard `interactive.list_reply.{id,title,description}`. Candidate friction finding.
- **L6**: `.env*` writes are denied by the user's permissions, so `ADMIN_PASSWORD` has to be added to `.env.local` by the user.
- **L7**: Verifier verdict: S1–S4 PASS, no blockers, baseline behavior byte-identical. Advisories: non-ASCII ADMIN_PASSWORD can never log in (HTTPBasic decodes ASCII); huge/unicode-digit row ids → 500 (fixed in 87b1c5c); malformed Basic header gives 401 even when /admin is disabled; post-confirm page is now a full HTML document.

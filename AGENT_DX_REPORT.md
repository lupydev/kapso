# Agent DX Report: building on Kapso with a coding agent

**Date**: 2026-10-25 · **Agent**: Claude Code with the Kapso Project MCP, `@kapso/cli` 0.19.2 and `gokapso/agent-skills` · **Number**: shared sandbox · **Raw evidence**: [`FRICTION_LOG.md`](FRICTION_LOG.md) (F1–F13)

## The experiment

A coding agent built a small WhatsApp payment-collection app on Kapso. A customer messages the number and gets an invoice with **Pay** / **I already paid** buttons. **Pay** returns a single simulated checkout link per invoice, and confirming it sends a receipt. The rule was that the agent only uses Kapso's agent surfaces (Project MCP, CLI, agent skills, docs MCP); the human does what only a human can do, like signing up and tapping buttons on a phone.

The app works end to end. It verifies HMAC webhook signatures, deduplicates by message ID, records the payment before the best-effort receipt, and returns 200 for permanent send errors so Kapso doesn't retry them. In a live reliability test, three replays of a real signed webhook with an already-processed `wamid` were all acknowledged as duplicates, and Kapso logged no extra outbound messages.

## Headline

**Kapso's agent surfaces are good for building and weak for getting started.** Once the agent had a working number, the MCP, CLI and skills carried it through building, debugging and testing with almost no friction. Most of the friction sits in the first hour, and it has one root cause: **the sandbox, the default path for any new developer or agent, is invisible or wrong on almost every agent-facing surface.**

| Milestone (local time, UTC-5) | Time |
| --- | --- |
| Sandbox session activated from my phone | 08:58 |
| First agent-sent message delivered | 09:56 (the first try failed, see F9) |
| Full payment flow working on a real phone | 10:34 |
| Reliability fix verified against live Kapso retries | 10:40 |

**Human touches**: 6. Four were inherent to the experiment (sign-up, OAuth sign-in, pasting the Quick setup prompt, testing on the phone). **Two were caused by friction**: re-running the skills install because the documented command is interactive (F5), and sending "hola" by hand to open the 24-hour window (F9).

## Root causes

### 1. The sandbox is a second-class citizen (F1, F2, F7, F9, F11)

Every finding here is the same bug seen from a different surface:

- **Counted as zero.** MCP `status` reports `whatsapp_numbers.count: 0` and sends the agent to `kapso_setup_open`, while `list_whatsapp_numbers` and the CLI's `kapso status` both find the sandbox (F7). The dashboard counters disagree with their own table (F1). An agent that follows the server instructions ("start with status") routes a ready user back into setup.
- **No phone number.** The sandbox has `display_phone_number: null` in the CLI and the MCP (F2), so the agent can't tell the human which number to message. The number does reach the agent later, in `context.from` on an inbound button reply, but only after the human has already found the chat.
- **The window doesn't open.** Sending the activation code doesn't open the 24-hour window. The agent's first send failed with `422` an hour after activation (F9). The fix is a human action ("message the sandbox"), which needs the number from F2.
- **Tests can't reach it.** `test_whatsapp_webhook` sends from `15551234567`. Any handler that replies gets `403 Active sandbox session required`, returns 500, and burns all retries (F11). The test checks the failure path, not the handler.

### 2. Onboarding hands the agent false context (F3, F4, F5, F6, F8)

Quick setup is written for one fixed order (API key → CLI → `kapso setup` → production number), but the dashboard steers people elsewhere. The step-4 prompt then makes three claims that were false for me: "production" message, "I exported KAPSO_API_KEY", "I ran kapso setup" (F8). A careful agent has to verify each one. A trusting agent looks for a production number that doesn't exist or calls the API with an empty key. Around that prompt: two auth paths with no stated precedence (F3), an interactive skills installer that blocks agents and fails silently for humans (F5), and no mention of the Project MCP (F6).

### 3. Small contract drift in observability (F10, F12, F13)

- The skill says webhook retries come at 10s, 40s and 90s. In practice there were 3 attempts in about 54s, which matches another docs page and not the skill (F12).
- Inbound messages stay at `processing_status: "pending"` after my webhook handled them, and the field isn't documented (F10).
- `kapso logs search` can't find a webhook delivery by its own ID, the ID an agent is most likely to hold (F13).

## What worked well (keep it)

- **Errors are written for agents.** The 422 returned `next_steps` and `retry.action: "fix_and_retry"`, enough for an agent to choose the next move without reading docs.
- **Secrets stay out of the transcript.** `kapso whatsapp webhooks new --secret-key` let the agent generate the secret locally so it never got printed, and the skill scripts redact secrets by default.
- **Cross-source log search.** One `kapso logs search` call showed the whole failure chain: webhook delivery → my 500 → my outbound POST → Kapso's 403. Root cause in one query.
- **The MCP covers the build.** Sending, listing messages, webhook deliveries with attempt counts, and test deliveries were all available without leaving the agent.

## Two concrete fixes

### Fix 1 (MCP schema): make `status` sandbox-aware

This removes F7, closes F2 for agents, and turns F9 into something the agent can act on. Proposed `status` response:

```json
{
  "whatsapp_numbers": {
    "count": 1,
    "items": [
      {
        "phone_number_id": "597907523413541",
        "kind": "sandbox",
        "display_phone_number": "+56 9 2040 3095",
        "sandbox_sessions": [
          {
            "phone_number": "+57300•••1639",
            "status": "active",
            "service_window_open_until": null
          }
        ]
      }
    ]
  },
  "next": [
    {
      "action": "ask_user_to_message",
      "to": "+56 9 2040 3095",
      "reason": "service_window_closed",
      "text": "Send any message to the Kapso Sandbox chat so I can reply."
    }
  ]
}
```

- `count` includes sandbox numbers, so `next` no longer points a ready user at setup.
- `display_phone_number` is filled in for the sandbox. It's already public: the activation link and inbound `context.from` both expose it.
- `service_window_open_until` tells the agent before it sends whether free-form text will fail. Today it finds out from a 422.

### Fix 2 (skill and docs): document the failure contract agents actually hit

Patch `integrate-whatsapp/references/webhooks-overview.md`. This ships without any product change:

```diff
 Retry schedule (Kapso webhooks):
-- 10 seconds
-- 40 seconds
-- 90 seconds
+- 3 attempts in total, about 10s and 40s apart (observed: +0s, +13s, +54s), then `failed`
+
+Which status to return:
+- Return 200 for permanent failures (a Kapso 4xx other than 429 when you reply,
+  malformed payloads). A retry fails the same way and burns attempts.
+- Return 5xx only for transient failures (Kapso 5xx or 429, timeouts) you want retried.
+- Deduplicate on `message.id`. Retries resend the same message, and a slow 200 can
+  cause a duplicate delivery.
+
+Test deliveries (`test_whatsapp_webhook`) come from `15551234567` with a
+`wamid.TEST_` ID. Replies to that number fail with 403 on the sandbox; check for
+the `wamid.TEST_` prefix before sending.
```

The last paragraph is a workaround. The real fix is a test-delivery flag (an `X-Webhook-Test: true` header) or the option to target your own active sandbox session (F11).

## Backlog, ranked by agent impact

| # | Fix | Findings | Effort guess |
| --- | --- | --- | --- |
| 1 | Sandbox-aware `status` (Fix 1) | F1, F2, F7, F9 | M |
| 2 | Activation message opens the 24-hour window | F9 | S–M |
| 3 | Generate the step-4 prompt from project state (number kind, auth method, MCP) | F3, F4, F8 | S |
| 4 | Non-interactive skills install in Quick setup; `kapso status` reports missing skills | F5 | S |
| 5 | Test deliveries flagged or targetable | F11 | S |
| 6 | Skill/docs failure contract (Fix 2) | F12 | XS |
| 7 | Index delivery IDs in log search; document `processing_status` | F10, F13 | S |
| 8 | Mention the Project MCP in Quick setup | F6 | XS |

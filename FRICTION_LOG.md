# Friction Log

Timestamped log of every friction point hit while building with Kapso. Times are local, taken from screenshots, date 2026-10-25.

Severity: **H** blocks an agent, **M** costs a human or agent time, **L** cosmetic.

## Human journey (dashboard, before the agent took over)

| Time | Step | Observation |
| --- | --- | --- |
| before 09:21 | Sign up | Short onboarding asks what you want to build, then a modal asks for a project name (`soka`). |
| 09:21 | Project Home | First screen is a chat ("How can I help?", model picker "GPT-6 Luna"). Suggested cards start with "Connect a production WhatsApp number", not the sandbox. |
| 09:22 | Phone numbers | Green "Set up" badge in the sidebar pulled attention here before Quick setup. |
| 09:24 | Sandbox session | Added my phone (`57300…`) as a sandbox session; status Active. |
| 09:25 | Quick setup | Step 1 created the API key (stored in project `.env`), step 2 installed the CLI (skills prompt cancelled, see F5), step 3 (connect number) was already done via the dashboard. |

## Findings

### F1 — Phone number counters disagree with the table (L)
- **What**: Phone numbers page header shows `0 / 1 phone numbers` and the tab shows `Phone numbers 0`, while the table lists one row (Sandbox WhatsApp).
- **Evidence**: Screenshot 09:22.
- **Impact**: Users wonder whether setup worked.

### F2 — Sandbox number is not discoverable by an agent (H)
- **What**: `kapso whatsapp numbers list --output json` returns `display_phone_number: null` for the sandbox (`phone_number_id 597907523413541`). The dashboard side panel also shows "Shared test number" without the number itself.
- **Evidence**: CLI 0.19.2 output; screenshot 09:24.
- **Impact**: An agent can't tell the user which WhatsApp number to message, so the zero-dashboard loop breaks.
- **Workaround found later**: once the user taps an interactive button, the inbound message's `context.from` (from MCP `list_whatsapp_messages`) holds the sandbox's display number. So the number leaks through message context but isn't exposed on the number resource, and it only shows up after the human has already found the chat.

### F3 — Quick setup mixes two auth paths (M)
- **What**: Step 1 says `export KAPSO_API_KEY=...`; step 2 also says `kapso login` (browser). The CLI docs say that when `KAPSO_API_KEY` is set, project commands use it directly, so one of the two is redundant. It is unclear which identity wins when both exist.
- **Evidence**: Quick setup screenshot 09:25; docs.kapso.ai/docs/whatsapp/cli#authentication.
- **Impact**: An agent can act on a different project than the human expects.

### F4 — Quick setup assumes a linear order the UI doesn't steer toward (M)
- **What**: The sidebar's green "Set up" badge on Phone numbers leads users to connect a number in the dashboard first; Quick setup step 3 (`kapso setup`) then repeats it. The step-4 prompt says "Send the first **production** WhatsApp message" and "I ran kapso setup", which isn't true for a sandbox-first user.
- **Evidence**: Screenshots 09:22, 09:25.
- **Impact**: The copy-paste prompt hands the agent false context.

### F5 — Skills install command in Quick setup is interactive (L)
- **What**: `npx skills add gokapso/agent-skills` prompts for agents and skills (the CLI offers `-a`, `-s` and `-y` to skip them). I cancelled the prompt during setup, so no Kapso skills were installed, and nothing in Quick setup or `kapso status` flagged that they were missing.
- **Evidence**: `npx skills list` and `npx skills list -g` showed no Kapso skills. `npx skills add gokapso/agent-skills -a claude-code -s '*' -y` then installed all 4 (`automate-whatsapp`, `integrate-whatsapp`, `integrate-whatsapp-calling`, `observe-whatsapp`) into `.claude/skills/` without prompts.
- **Impact**: A coding agent that runs the command as shown blocks on a prompt. A human who skips it silently ends up with an agent that has no Kapso skills.
- **Proposal**: show the non-interactive form in Quick setup, and have `kapso status` report whether the agent skills are installed.
- **Note**: the installer's security summary flags `automate-whatsapp` with 1 Socket alert and a Snyk "Med Risk" rating. A quick scan found only `api.kapso.ai` endpoints and no `curl | sh` or `rm -rf` patterns.

### F6 — Quick setup doesn't mention Project MCP (L)
- **What**: Quick setup covers CLI + skills only. Project MCP setup lives in a separate docs page.
- **Impact**: MCP-only agents (no shell) get no on-ramp from the dashboard.

### F7 — MCP `status` ignores the sandbox number and pushes setup (M)
- **What**: With the Project MCP connected over OAuth (project `soka`), `status` returns `whatsapp_numbers.count: 0` and `next: kapso_setup_open`. `list_whatsapp_numbers` on the same session returns the sandbox number (`597907523413541`, `kind: sandbox`, `total_count: 1`). The MCP also returns `display_phone_number: null` for it, same as F2.
- **Evidence**: MCP `status` and `list_whatsapp_numbers` calls, 2026-10-25 after `/mcp` sign-in.
- **Also**: CLI `kapso status` (0.19.2) on the same project reports `WhatsApp Numbers: 1`, so the CLI and the MCP disagree.
- **Impact**: An agent that follows the server instructions ("start with status") routes a sandbox user back into number setup instead of building. Same root as F1: sandbox numbers are excluded from counts.

### F8 — Step 4 prompt hands the agent three false premises (M)
- **What**: The Quick setup step 4 prompt says "Send the first **production** WhatsApp message", "I exported KAPSO_API_KEY in my environment" and "I ran kapso setup to connect a WhatsApp number". In this project: the only number is the sandbox, `KAPSO_API_KEY` is in `.env` but not exported (the CLI is authenticated via `kapso login`), and the number was connected in the dashboard. The prompt doesn't mention the Project MCP at all.
- **Evidence**: Prompt text copied from Quick setup; `echo $KAPSO_API_KEY` empty; `kapso status` shows the `kapso login` user.
- **Impact**: The agent must verify every claim before acting. One that trusts the prompt either looks for a production number that doesn't exist or calls the API with an empty key. Extends F3 and F4.
- **Proposal**: generate the prompt from the project's actual state (number kind, auth method, MCP connected or not).

### F9 — Sandbox activation doesn't leave a 24-hour window open (M)
- **What**: The sandbox session was activated by sending the code from my phone, and the very first outbound text from the agent was rejected with `422 Cannot send non-template messages outside the 24-hour window.` The error's `next_steps` says "Send a WhatsApp template message to reopen the session", without saying whether the shared sandbox number has templates the project can use.
- **Evidence**: `kapso whatsapp messages send --phone-number-id 597907523413541 --to <me> --text ...` (CLI 0.19.2), same day as activation.
- **Impact**: The "first message" step of the onboarding fails for a sandbox user. To recover, the human has to message the sandbox from their phone, but per F2 the agent can't tell them which number to message.
- **Resolved**: activation was sent at 08:58 and the send failed about an hour later, well inside 24 h, so the activation code does **not** open the window. After I sent "hola" at 09:55, the same command succeeded (`wamid` returned).
- **Proposal**: count the activation message as an inbound message that opens the window, or say in the activation confirmation that the user must send one more message.

### F10 — Inbound `processing_status` stays `pending` after the webhook succeeded (L)
- **What**: Both inbound messages of the end-to-end test (text, then the "Pay" button reply) show `kapso.processing_status: "pending"` in MCP `list_whatsapp_messages`. My webhook returned 200 and processed both, as the outbound replies and the local DB confirm. Outbound messages show `processed`.
- **Evidence**: MCP `list_whatsapp_messages` since 15:30Z on 2026-10-25; local `processedmessage` table has 2 rows.
- **Impact**: An agent debugging delivery reads "pending" as "my webhook didn't handle it". It's unclear what the field tracks (Kapso workflows? agents?) and the docs don't say.
- **Open question**: which consumer is expected to move inbound messages out of `pending` when you use your own webhook.

### F11 — Test webhook delivery targets a recipient the sandbox rejects (M)
- **What**: MCP `test_whatsapp_webhook` sends a `whatsapp.message.received` sample from `15551234567` (message id `wamid.TEST_…`). A handler that replies gets `403 {"error":"Active sandbox session required to send messages"}` from Kapso, so the "test" exercises the failure path and burns all retries.
- **Evidence**: delivery `6a622df6-…` (3 attempts, 500, `failed`); my server log showing the 403; `kapso logs search` shows the POST to `/messages` returning 403 for `15551234567`.
- **Impact**: An agent using the test delivery to check its webhook sees 500s and may "fix" a working handler. There's no way to send a test event to the user's own sandbox session.
- **Proposal**: let the test delivery target an active sandbox session, or flag the payload as a test (header or `is_test` field) so handlers can skip side effects.

### F12 — Retry schedule differs between the skill and the docs (L)
- **What**: The `integrate-whatsapp` skill (`references/webhooks-overview.md`) says retries happen at 10s, 40s and 90s (4 attempts). The migration docs say "3 attempts in about 50 seconds". Observed: 3 attempts at +0s, +13s and +54s, then `failed`.
- **Evidence**: delivery `6a622df6-…` timestamps 12:38:36, 12:38:49, 12:39:30.
- **Impact**: An agent sizing idempotency windows or timeouts from the skill plans for a 90s retry that never comes.

### F13 — Log search can't find a webhook delivery by its ID (L)
- **What**: `kapso logs search --query "<delivery id>" --period 24h --source all` returns no events, but searching by the phone number ID returns two `whatsapp_webhook_delivery` events whose `resource_id` is that same delivery ID.
- **Evidence**: delivery `6a622df6-9992-47a7-93ca-ad8c98dc39d2`.
- **Impact**: The skill's troubleshooting advice ("search Logs before drilling into per-resource endpoints") fails for the ID an agent is most likely to hold. Minor: `--period` accepts `24h` but rejects `1d`.

### Reliability test result (positive)
- Replaying the real signed `whatsapp.message.received` for an already-processed `wamid` three times through the tunnel returned `200 {"status":"duplicate"}` each time, and Kapso shows no new outbound messages. Kapso's retries + message-id dedup worked as documented once the handler separated permanent from transient failures.

### F14 — Docs show the inbound `button_reply` payload but not `list_reply` (L)
- **What**: The webhook event docs (`docs/platform/webhooks/message-events#interactive-messages`) and the `integrate-whatsapp` skill reference only show `interactive.button_reply`. Sending list messages is documented, but what comes back when a customer picks a row isn't. I built against Meta's standard `interactive.list_reply.{id,title,description}`, and it worked end to end.
- **Evidence**: docs MCP search for "list_reply inbound interactive" returned only `button_reply` examples; the live customer pick was processed by the `list_reply` handler.
- **Impact**: An agent that only trusts Kapso's docs either guesses or drops list replies.

### F15 — Sandbox test sessions can only be created in the dashboard (M)
- **What**: Adding a tester's phone to the sandbox is "WhatsApp → Sandbox → Add Test Number" in the dashboard, followed by a 6-character code the tester sends within 15 minutes. Neither the Project MCP tool list nor `kapso` CLI 0.19.2 has a way to create, list or check sandbox sessions.
- **Evidence**: docs page `docs/how-to/whatsapp/use-sandbox-for-testing`; MCP tools/list has no sandbox-session tool.
- **Impact**: An agent can build and deploy the whole app but can't onboard a second tester, which is exactly what you need to share a sandbox demo with a team. Combined with F2, an agent can't even tell a tester which number to message.
- **Proposal**: an MCP/CLI `create_sandbox_session(phone)` that returns the activation code, the sandbox number and a `wa.me` link.

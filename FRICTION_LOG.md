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

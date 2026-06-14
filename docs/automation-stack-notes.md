# Automation Hub — Tools & Techniques Notes

Personal reference notes on the automation stack built for this project's
**Automation Hub** tab. First time using n8n, ngrok, and Docker together for
something like this — written so future-me can pick this back up without
re-learning it from scratch.

---

## What was built

The Streamlit app computes RFM segments and flags customers who need action
(Cannot Lose Them, At Risk, Need Attention, New Customers, Promising). The
Automation Hub tab turns that into a JSON "alert payload" and sends it
somewhere useful — in this case, an n8n workflow that routes alerts to Slack
and logs them to a Google Sheet.

On top of the manual "click a button in the app" flow, two things automate it
further:

- `scripts/dispatch_alerts.py` — a standalone script that recomputes the same
  RFM segments and posts the same payload, with no Streamlit needed
- `.github/workflows/dispatch-alerts.yml` — runs that script on a daily
  schedule via GitHub Actions

A second workflow, `.github/workflows/streamlit-keepalive.yml`, just pings the
deployed app every 6 hours so Streamlit Community Cloud doesn't put it to
sleep from inactivity.

---

## How it all fits together

```
[Streamlit app]  --or--  [GitHub Actions: dispatch_alerts.py]
        |
        | POST JSON payload (alerts array)
        v
[n8n webhook: /webhook/rfm-alerts]
        |
        |-- Split Out Alerts (one item per alert)
        |-- Assign Channel (map segment -> Slack channel)
        |-- Switch by Priority (Critical / High -> notify, others -> drop)
        |       |
        |       |-- Loop Over Items + Wait 1s (avoids Slack rate limit)
        |       |-- Notify Slack
        |
        |-- Log Alert to Sheet (every alert, regardless of priority)
```

The **payload shape** is the contract between the app and n8n:

```json
{
  "source": "rfm-customer-intelligence",
  "dataset": "...",
  "generated_at": "...",
  "alert_count": 12,
  "alerts": [
    {
      "customer_id": "...",
      "segment": "At Risk",
      "priority": "High",
      "action": "...",
      "recency_days": 45,
      "frequency": 3,
      "monetary": 1234.56,
      "rfm_score": "243"
    }
  ]
}
```

Both `app.py` (Automation Hub tab) and `scripts/dispatch_alerts.py` build this
same shape — that's deliberate, so the n8n workflow doesn't care which one
sent it.

---

## Tool-by-tool notes

### n8n

n8n is a self-hostable workflow automation tool (like Zapier/Make, but you run
it yourself). The workflow lives in `n8n/rfm_segment_alert_router.json` and
can be imported via **Workflows → Import from File**.

Nodes used, in order:

1. **Webhook** — the entry point. Listens on `/webhook/rfm-alerts` for a POST
   request. This is the URL you paste into the app's "Webhook URL" field.
2. **Split Out** — n8n workflows operate on "items" (think: rows). This node
   takes the single incoming payload and splits `body.alerts` into one item
   per alert, so downstream nodes run once per alert.
3. **Set ("Assign Channel")** — adds a `channel` field to each item by mapping
   `segment` to a Slack channel name using an inline JS object lookup
   (`{"Cannot Lose Them": "#customer-success-urgent", ...}`).
4. **Switch** — routes items into separate branches based on `priority`.
   Critical and High go to Slack; everything else is dropped from that branch
   (but still gets logged — see step 6).
5. **Set ("Format Slack Message")** — builds the actual Slack message text
   using a template string with `{{ }}` expressions pulling from the item's
   fields.
6. **Loop Over Items (Split In Batches) + Wait** — see "Slack rate limit" note
   below.
7. **Slack node** — posts the message to the channel from step 3.
8. **Google Sheets node** — runs in parallel to steps 4-7, appending every
   alert (any priority) to a sheet for a weekly review log.

**Credentials**: the JSON ships with placeholder credential IDs
(`REPLACE_WITH_CREDENTIAL_ID`, `REPLACE_WITH_GOOGLE_SHEET_ID`). After
importing, you have to set up your own Slack and Google Sheets credentials in
n8n's credential manager and point the nodes at them — the workflow won't run
without this.

**Slack rate limit (HTTP 429)**: Slack's `chat.postMessage` API throttles
rapid-fire messages. If a batch has many Critical/High alerts, sending them
all at once trips this. Fix: a **Split In Batches** node (batch size 1) feeds
into a **Wait** node (1 second) before each Slack post, so messages go out one
at a time with a gap. Looks slower, but it's what stops the workflow from
silently failing on larger batches.

### Docker

Used to run n8n locally rather than installing it natively or paying for n8n
cloud. Typical command (adjust as needed):

```bash
docker run -it --rm \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n
```

`-v ~/.n8n:/home/node/.n8n` persists workflows/credentials across container
restarts — without it, everything resets when the container stops. n8n's UI
is then at `http://localhost:5678`.

### ngrok

ngrok creates a temporary public URL that tunnels to a port on your local
machine. Needed here because the **Streamlit app is deployed** (Streamlit
Community Cloud), so when it sends a webhook POST, it's going out over the
public internet — it can't reach `localhost:5678` on your laptop. ngrok
bridges that gap.

```bash
ngrok http 5678
```

This gives a URL like `https://abcd1234.ngrok-free.app`, which becomes:
`https://abcd1234.ngrok-free.app/webhook/rfm-alerts` — paste that into the
app's Webhook URL field.

**Gotcha**: free ngrok URLs change every time you restart ngrok. If the
deployed app's webhook URL is hardcoded anywhere, it'll break on restart —
either re-paste the new URL each session, or look into ngrok's paid static
domains if this becomes a recurring workflow.

### GitHub Actions

Two scheduled workflows, both using cron syntax (`* * * * *` =
minute/hour/day-of-month/month/day-of-week, always UTC):

- `dispatch-alerts.yml` — `cron: "0 8 * * *"` = 08:00 UTC daily. Checks out
  the repo, installs `requirements.txt`, runs
  `scripts/dispatch_alerts.py --priorities Critical,High`. The webhook URL is
  read from a **repository secret** (`RFM_WEBHOOK_URL`), set under
  **Settings → Secrets and variables → Actions**. Also supports manual runs
  (`workflow_dispatch`) with a `dry_run` option that prints the payload
  instead of sending it — useful for testing without spamming Slack.
- `streamlit-keepalive.yml` — `cron: "0 */6 * * *"` = every 6 hours. Just
  curls the app's URL so Streamlit Cloud sees activity and doesn't spin the
  app down.

**Important caveat learned from this session**: GitHub Actions workflow files
live under `.github/workflows/`, and a Personal Access Token needs the
**`workflow`** scope to push changes to that folder — a normal `repo`-scoped
token gets rejected with "refusing to allow a Personal Access Token to create
or update workflow ... without `workflow` scope". Fix is in GitHub → Settings
→ Developer settings → Tokens → tick `workflow` → Update token (no need to
regenerate for classic tokens — editing scopes in place works and the same
cached credential picks it up).

Because these workflows have only `schedule`/`workflow_dispatch` triggers,
they won't show any *runs* until triggered, but should still be **listed**
under the Actions tab as soon as the files land on the default branch (assuming
Actions are enabled for the repo under Settings → Actions → General).

### Slack

Standard incoming integration via n8n's Slack node + OAuth credential (not a
plain webhook URL — n8n's Slack node uses the Slack API directly, which is why
a credential has to be configured in n8n rather than just pasting a Slack
webhook URL).

### Google Sheets

Same pattern as Slack — n8n's Google Sheets node needs an OAuth2 credential
and a target spreadsheet ID. Used purely as a log/audit trail of every alert
generated, independent of priority.

---

## Setup checklist (for next time / a fresh machine)

1. `docker run` n8n (see command above), open `http://localhost:5678`
2. Import `n8n/rfm_segment_alert_router.json` via Workflows → Import from File
3. Set up Slack and Google Sheets credentials in n8n, attach to the two nodes
4. Activate the workflow so the webhook is live
5. Run `ngrok http 5678`, copy the forwarding URL
6. Paste `<ngrok-url>/webhook/rfm-alerts` into the Automation Hub tab's Webhook
   URL field (for live testing), and/or set it as the `RFM_WEBHOOK_URL`
   repository secret on GitHub (for the scheduled dispatch)
7. Test with `python scripts/dispatch_alerts.py --dry-run` first to check the
   payload shape without sending anything

---

## Key concepts to remember

- **Webhook** = just a URL that accepts an HTTP POST with a JSON body — the
  "trigger" half of almost every automation integration
- **n8n items** = the unit workflows operate on; "Split Out" turns one
  payload into many items so each alert gets processed individually
- **ngrok** = temporary public tunnel to localhost; URL changes on restart
  unless paid for a static domain
- **GitHub Actions secrets** = how to give a scheduled workflow access to a
  URL/token without committing it to the repo
- **PAT scopes** = `repo` covers most pushes, but `.github/workflows/` changes
  specifically need the `workflow` scope too

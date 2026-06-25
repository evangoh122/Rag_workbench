# PostHog → Google Slides (daily, self-hosted n8n)

Pushes PostHog metrics into a Google Sheet, then refreshes the **linked charts**
in a Google Slides deck once a day. Charts are native Google charts (built once in
the Sheet); n8n only refills the data and tells Slides to re-pull them.

```
Daily 07:00 → PostHog Query API → Google Sheet (data tab) → refreshSheetsChart() on the deck
```

---

## 1. One-time manual setup (the part that can't be automated)

### a. Google Sheet (the data source)
1. Create a Google Sheet. Add a tab named **`data`**.
2. Note its **spreadsheetId** — the long ID in the URL:
   `https://docs.google.com/spreadsheets/d/`**`<spreadsheetId>`**`/edit`

### b. Build the chart(s) in the Sheet
Run the workflow **once manually** first (Step 4) so the `data` tab has real
columns/rows. Then in the Sheet: **Insert → Chart**, pick your chart type, set its
data range (e.g. `data!A:C`). Style it how you want — this styling is what shows on
the slide.

### c. Link the chart into Slides
1. Open (or create) your Google Slides deck. Note its **presentationId**:
   `https://docs.google.com/presentation/d/`**`<presentationId>`**`/edit`
2. **Insert → Chart → From Sheets**, choose your Sheet + chart.
3. ✅ **Keep "Link to spreadsheet" checked** — this is what makes `refreshSheetsChart`
   work. Repeat for each chart you want on the deck.

> Only *linked* charts refresh. Pasted images / unlinked charts will not update.

### d. PostHog project + key (Cloud US)
1. Project ID: PostHog → **Settings → Project** (a number).
2. Personal API key: **Settings → Personal API keys → Create**. Give it
   *Query Read* scope (and read on Insights). Copy the key (starts with `phx_`).

---

## 2. Create the 3 credentials in n8n

In your self-hosted n8n: **Credentials → New**.

| Credential type            | Used for            | How to fill                                                                 |
|----------------------------|---------------------|------------------------------------------------------------------------------|
| **Header Auth**            | PostHog             | Name: `Authorization`  ·  Value: `Bearer phx_your_key_here`                  |
| **Google Sheets OAuth2 API** | reading/writing Sheet | OAuth — connect your Google account                                       |
| **Google Slides OAuth2 API** | get deck + refresh charts | OAuth — connect the **same** Google account                          |

**Google Cloud prerequisite (once):** in a Google Cloud project, enable the
**Google Sheets API** and **Google Slides API**, create an **OAuth client ID**
(type *Web application*), and add your n8n callback URL
(`https://<your-n8n-host>/rest/oauth2-credential/callback`) as an authorized
redirect URI. Paste the client ID/secret into both Google credentials above.

> The Slides OAuth2 credential's default scopes include Drive access, which is what
> lets `refreshSheetsChart` read the linked spreadsheet. Connect both Google
> credentials with the same account so they can see the same files.

---

## 3. Import & configure the workflow

1. n8n → **Workflows → Import from File** → select `workflow.json`.
2. Open the **Config** node and fill in:
   - `posthogProjectId`
   - `spreadsheetId`
   - `sheetTab` (default `data`)
   - `presentationId`
   - `posthogHost` is already `https://us.posthog.com` (Cloud US).
3. Open each node showing a credential warning and pick the credential you made:
   - **PostHog Query** → Header Auth
   - **Clear Sheet**, **Write Rows** → Google Sheets OAuth2
   - **Get Presentation**, **Refresh Charts** → Google Slides OAuth2

---

## 4. Test, then turn on the schedule

- Click **Execute Workflow** to run it once. Confirm:
  - the Sheet's `data` tab fills with rows,
  - the linked chart(s) in Slides update.
- The trigger is a daily cron at **07:00** (`0 7 * * *`). Edit the **Every day 07:00**
  node to change the time. **Activate** the workflow (toggle, top-right) so it runs
  on schedule.

---

## 5. Customizing the metrics

The query lives in the **PostHog Query** node (`jsonBody`). It's HogQL. Default:

```sql
SELECT toDate(timestamp) AS day,
       count() AS events,
       count(DISTINCT person_id) AS users
FROM events
WHERE timestamp >= now() - INTERVAL 30 DAY
GROUP BY day
ORDER BY day
```

Swap in any HogQL you like (filter by `event = 'signed_up'`, breakdown by property,
etc.). The first row of the Sheet becomes your column headers automatically, so
adjust the chart's data range in the Sheet if you add/remove columns.

## Notes & gotchas
- **Adding a new chart later?** Just link it into the deck (Step 1c). The workflow
  auto-discovers every linked chart on every slide — no workflow change needed.
- **Empty deck:** if no linked charts are found, the `Has charts?` IF node short-
  circuits so `batchUpdate` is never called with an empty request.
- **Multiple decks:** duplicate the workflow and change `presentationId`.

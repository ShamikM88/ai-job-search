# Live Job Dashboard

A local, filterable, write-back-capable dashboard over `seen_jobs.json` and
`job_search_tracker.csv` - the read side for everything `/scrape`, `/rank`, and `/apply`
produce during a session.

## Running it

```bash
bun run job_scraper/serve_dashboard.js
```

Bookmark the URL it prints (`http://127.0.0.1:4321/` by default; override with
`PORT=<port>`). There is no static-export mode - a bookmarked `file://` page can't write
back to the tracker CSV, which is what makes the Apply / status-update controls actually
work. The `/dashboard` skill wraps this: it checks whether the server is already running
before starting a new one, and opens the URL in a browser tab.

Binds to `127.0.0.1` only, deliberately never `0.0.0.0` - `/api/status` writes to disk on
an unauthenticated request, fine for a single-user localhost tool, not fine on a LAN.

## What it shows

One row per `seen_jobs.json` entry: job code, company, title, market (UK/DE/IE, inferred
from `location_text`), fit score and verdict, application status, location and language
gate badges, first-seen date, and a quick action (an **Apply** button for anything not yet
applied to, or a link-out icon for postings already tracked). Click a row to expand it for
the full strengths/gaps breakdown and any other detail fields.

Filterable by search text, market, verdict, application status, and portal; sortable on
every column; a set of stat cards above the table double as quick filters (click one to
toggle it).

**Copy buttons** - a small ⧉ icon sits next to the job code and next to the listing title.
Clicking either copies the value to your clipboard (briefly turning into a ✓) without
triggering the row's own expand/collapse click handler. The job-code button copies just
the code (the short hash shown in the ID column - handy for referencing a specific row in
conversation without retyping the full company/title). The title button copies
`Company — Title` together, not the bare title alone, since the same title can recur
across different companies and a bare title copy would be ambiguous.

## Writing back

The **Apply** button and any other status control POST to `/api/status`, which mirrors
`/outcome`'s Step 4 rules exactly: updates the tracker row's status, overwrites `date`
with today's date only when the row is leaving `drafted` (the column means "applied on,"
not "drafted on"), and appends a dated note rather than overwriting existing notes - never
restructuring the CSV. Anything updated here stays fully compatible with a later
`/outcome` pass for richer outcome recording (interview stages, feedback, document
archiving).

`GET /api/data` rebuilds fresh from disk on every call, so there's no "regenerate after
`/scrape` or `/rank`" step to remember - just reload the tab to see new data.

## Files

- `serve_dashboard.js` - the HTTP server (routes, static PDF serving from `cv/` and
  `cover_letters/`, no auth by design since it's localhost-only).
- `dashboard_lib.js` - data building (`buildDashboardData`), the tracker-write logic
  (`updateTrackerStatus`), and the entire client-side HTML/CSS/JS shell as one exported
  string (`SHELL_HTML`) - there's no separate build step or bundler involved.

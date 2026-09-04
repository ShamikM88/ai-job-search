# /gmail-sync - Sync Application Status from Gmail

You are scanning the user's Gmail for status signals on tracked job applications (interview invites, assessment links, offers, rejections) and, once approved, writing the detected changes into `job_search_tracker.csv` and `documents/applications/<company>_<role>/outcome.md` - the same two places `/outcome` writes to, in the same schema. The same run also surfaces job-recommendation digest emails from portals like StepStone, LinkedIn, Indeed, Xing, and Glassdoor, dedup-checks them, and registers genuinely new leads into `job_scraper/seen_jobs.json` (the same cache `/scrape` writes) so `/rank` can score them on its next run - see Step 5b. This part is read-only against Gmail itself but not against local state, unlike the tracker/`outcome.md` side of this command.

Unlike `/outcome` (which asks the user what happened), `/gmail-sync` classifies real emails on its own - but it never writes on its own. Every classified change is presented as a batch **before** anything touches the tracker or `outcome.md`, and only proceeds once the user approves it (approving the whole batch at once is fine; writing first and flagging it after is not). Because a wrong write silently corrupts application history that `/setup` later calibrates from, every proposed change must cite its source email and every uncertain case must be surfaced instead of guessed. Never treat this command's job as "notice something in an inbox" - it is "propose a correct, sourced line for a permanent record, and write it only once the user says yes."

Follow these steps **in order**.

---

## Step 0: Prerequisites

Confirm the Gmail MCP tools (`mcp__claude_ai_Gmail__*`) are available. If not, tell the user to connect the Gmail integration (claude.ai Settings → Connectors → Gmail) and stop - do not attempt this via Bash, IMAP, or any other channel.

---

## Step 1: Parse Input

`$ARGUMENTS` may contain:

- Nothing → default lookback (see Step 3)
- A company name, e.g. `/gmail-sync acme` → scope the search to that one tracked application
- `since <YYYY-MM-DD>` → override the lookback start date for this run only (does not change the persisted state file)

---

## Step 2: Load State

1. Read `job_search_tracker.csv`. If it does not exist, tell the user there is nothing to sync against yet (suggest `/outcome` or `/apply` first) and stop. Do not create it here - `/gmail-sync` never originates new applications, only updates existing ones.
2. Read `gmail_sync/state.json` (create if missing: `{"last_sync": null, "processed_message_ids": []}`).
3. Build the set of **open applications**: tracker rows whose `status` is not **Final** (per the **Tracker status vocabulary** in `/outcome`). For each, derive its archive folder `documents/applications/<company>_<role>/` (lowercase, underscores - same convention as `/outcome`) and check whether `outcome.md` exists there.

   **`drafted` rows stay in this set, and are the reason it is worth searching.** `/apply` writes them but never submits; the user submits by hand and may not think to run `/outcome`. A reply arriving against a row still marked `drafted` is exactly that case, and the row holds the company name the search needs.
4. If `$ARGUMENTS` named a company, filter this set to the matching row(s) (case-insensitive). No match → tell the user and stop, do not guess.

---

## Step 3: Build the Search Query

Lookback window: `since <date>` argument if given, else `state.last_sync` if set, else `newer_than:30d`.

1. Call `list_labels` and look for a user label whose name suggests job-search email (e.g. contains "job", "application", "career" case-insensitively). Note its `id` if found.
2. Normalize each open application's company name for matching later (lowercase; strip `inc`, `inc.`, `llc`, `ltd`, `a/s`, `corp`, `corporation`, `group`; strip punctuation; collapse whitespace).
3. Build a Gmail query combining (with `OR` groups via `{}`):
   - `label:<id>` if a job-search label was found
   - A quoted-name OR-group of the open applications' company names, e.g. `{"Acme Corp" "BigCo"}`
   - A sender-domain OR-group of common ATS platforms: `{from:greenhouse.io from:lever.co from:myworkday.com from:ashbyhq.com from:smartrecruiters.com from:icims.com from:bamboohr.com}`
   - A sender-domain OR-group of job-portal recommendation senders, independent of the open-applications list above (these emails are about *new* jobs, not existing tracked ones): `{from:stepstone.de from:stepstone.com from:jobs-noreply@linkedin.com from:indeed.com from:xing.com from:glassdoor.com}`
   - The lookback bound, e.g. `newer_than:30d` or `after:2026/06/15`
   - `in:inbox` (skip sent/drafts - status signals come from what employers send you, not what you sent them)

Example: `newer_than:30d in:inbox ({"Acme Corp" "BigCo"} OR {from:greenhouse.io from:lever.co from:myworkday.com from:ashbyhq.com} OR {from:stepstone.de from:jobs-noreply@linkedin.com from:indeed.com})`

4. Call `search_threads` with `view: THREAD_VIEW_MINIMAL`, `pageSize: 50`, paginating via `pageToken` until exhausted or results are clearly outside the relevant window.

---

## Step 4: Filter to New Messages

For each returned thread, inspect its messages' IDs against `state.processed_message_ids`. Skip a thread entirely if every message in it is already processed. For threads with unprocessed messages, call `get_thread` with `messageFormat: FULL_CONTENT` to get full bodies - **classification in Step 5 must never be based on the snippet/subject alone**, since snippets truncate the exact phrase that distinguishes "we'd like to schedule a call" from "thanks for applying."

---

## Step 5: Classify Each Unprocessed Message

For each new message, first try to match it to one open application: compare the normalized sender domain / display name / subject / body against the normalized company names from Step 3. No confident match (company genuinely absent, or ambiguous between two tracked companies) → do not propose a write; record it in the Step 6 summary as "unmatched" and move to the next message.

For a matched message, classify by content (require the signal phrase in the subject or the first few lines - a company name appearing only deep in a forwarded thread or newsletter footer is not a signal):

| Signal | Example phrasing | Tracker `status` | `outcome.md` action |
|---|---|---|---|
| Application ack | "we've received your application" | `drafted` -> `applied`, otherwise *(no change)* | On a `drafted` row this is the one email that proves the user submitted by hand, and it arrives within a day of them doing so - propose the move with `date` set to the email's date. On any other status it is noise. |
| OA / assessment | "online assessment", "coding challenge", "complete your assessment", HackerRank/Codility links | `interview` | Tick nearest matching stage checkbox (or add a Notes line if no checkbox fits - assessments aren't always a listed stage) |
| Interview invite/scheduled | "schedule a call", "phone screen", "technical interview", "next round", "onsite", "final round" | `interview` | Tick the matching stage checkbox with the email's date |
| Offer extended | "pleased to offer", "extend an offer", "offer letter" | `offer` | Tick "Offer received" checkbox. **Never propose `hired` or `offer_declined` from an email** - accepting or declining is the user's decision, not something to infer. Flag prominently in the Step 6 summary as needing the user's decision, separate from the plain approve/skip table. |
| Rejection | "moving forward with other candidates", "not selected", "unable to proceed", "decided not to continue" | `rejected` | Set `Status: rejected`, `Date resolved:` to the email's date |

**Conflict rule:** if the classified signal contradicts the application's current final-ness (e.g. a "moving forward" email arrives for a company whose tracker row briefly shows a `rejected`-adjacent recent write already, or a rejection arrives after an offer was already proposed this run) - do not propose overwriting it. Record it as a conflict in Step 6 for manual `/outcome` resolution instead.

---

## Step 5b: Classify Job-Recommendation Emails

This is a **separate track** from Step 5 above - it never proposes a tracker or `outcome.md` write, because a recommendation digest is about jobs the candidate hasn't applied to, not a status change on one they have. It does, however, write to `job_scraper/seen_jobs.json`, per the dedup-and-register step below - without that, there is nowhere for a surfaced lead to actually go: `/rank` only scores entries that already exist there with `status: "new"`, it does not accept a pasted URL, so a lead that stopped at "presented in chat" was a dead end dressed up as a suggestion to "run /rank on it."

For each unprocessed message from a job-portal recommendation sender (the domain group added in Step 3) that Step 5 did **not** already match to an open application as a status signal: check whether it is actually a recommendation/digest email, not something else the same portal sends (an application confirmation, an interview-scheduling email, an account/security notice). Require a digest-style signal phrase in the subject or opening lines - e.g. "jobs recommended for you", "new jobs matching your search", "jobs für Sie ausgewählt", "empfohlene Jobs", "X new jobs posted for [search/title]". A portal email that doesn't match this pattern is not a recommendation email - leave it alone (it may still be relevant to Step 5's matching, or simply irrelevant).

For a confirmed recommendation email, extract every distinct job listing mentioned in the body: title, company, and URL (if the email links directly to a posting rather than a generic search-results page). A digest with only a generic "see all matches" link and no individual listings has nothing to extract - note it was received, but there is nothing to list.

**Dedup and register each extracted lead, reusing `/scrape`'s own Step 2/Step 4 logic exactly** (same file, same schema, same checks - this is not a parallel dedup mechanism, it's the existing one):
1. Read `job_scraper/seen_jobs.json` and `job_search_tracker.csv` once, if not already loaded this run.
2. Skip a lead if its URL or company+title combo already exists in `seen_jobs.json` (normalize company names the same mojibake-aware, diacritic-stripping way established for tracker dedup - a raw string mismatch on an umlaut or an encoding artifact is a confirmed real failure mode, not a hypothetical one). Skip if the company+role already appears in `job_search_tracker.csv`. Record skipped leads as "already seen" in Step 6, not silently dropped.
3. For a lead that clears both checks, add it to `seen_jobs.json` under a new key (its URL, matching `/scrape`'s convention) with `status: "new"`, `portal: "gmail-recommendation"`, `first_seen`: today's date, and `title`/`company`/`url`/`location_text` from what the email provided (`location_text` may be absent if the email didn't state one - do not guess it). Do **not** run a fit assessment here - that's `/rank`'s job on its next invocation, exactly as it is for anything else with `status: "new"`.
4. This step does not run `/scrape`'s Step 1 (search), Step 2's WebFetch/detail-fetch, Step 2.5 (mass-posting detection), or Step 4.5 (referral links) - it only borrows the dedup check and the write schema for leads that already arrived by email, fully formed. It is not a substitute for `/scrape` and doesn't invoke it.

---

## Step 6: Present Proposed Updates

**Nothing has been written yet.** Present every classified change from Step 5 as a single batch, so the user can review the full picture before anything touches the tracker or `outcome.md`:

```
## Gmail Sync - Proposed Updates - YYYY-MM-DD

Scanned N threads (M new messages) since <lookback date>.

### Proposed Changes (reply "approve all", or list which to skip, e.g. "skip 2")
| # | Company | Role | Signal | Current -> Proposed Status | Source Email (date) |
|---|---|---|---|---|---|
| 1 | ... | ... | Interview invite | applied -> interview | "Subject line" (2026-07-10) |
| 2 | ... | ... | Offer extended | interview -> offer | "Subject line" (2026-07-12) |
| 3 | ... | ... | Application ack | drafted -> applied, date -> 2026-07-02 | "Subject line" (2026-07-02) |

A row leaving `drafted` shows its date change in the status cell, as row 3 does: that row was never recorded as submitted, so Step 7a is about to replace the drafting date. Say that the date is taken from the email and ask whether the user knows the real submission date - approving the status move should not silently approve a date they can correct.

### Needs Manual Review (conflicting signal - not proposed, use /outcome)
- **<Company>** - <what conflicted and why it wasn't proposed>

### Unmatched Emails (no change proposed)
- "<subject>" from <sender> - looked job-related but couldn't be confidently linked to a tracked application.

### Job Recommendations Found (registered as `new` in seen_jobs.json - no approval needed, nothing scored yet)
| Portal | Title | Company | Received | URL |
|---|---|---|---|---|
| StepStone | ... | ... | 2026-07-10 | [Link](...) |

### Recommendations Already Seen (skipped, not re-registered)
- <Title> at <Company> - already in seen_jobs.json / tracker - [Link](...)

Say explicitly that the registered leads are unscored (`status: "new"`) and ready for `/rank` - suggest running it now if there are enough to be worth a batch, or naming a specific one for `/apply` directly.

### Stale Applications (30+ days, no activity)
- **<Company>** - last activity YYYY-MM-DD, still `<status>`.
```

If the Proposed Changes table would be empty, say so briefly and skip straight to Step 8 (Update State) - there is nothing to approve. Offers still land in the Proposed Changes table (the tracker moves to `offer`); it's only `hired`/`offer_declined` that are never proposed. The Job Recommendations tables are independent of this - they can have rows even when Proposed Changes is empty, and need no approval (the `seen_jobs.json` write in Step 5b already happened by the time this is presented, same as Step 5's classification already happened - Step 7's approval gate is specifically for tracker/`outcome.md` writes); omit either table entirely when it would be empty.

---

## Step 7: Wait for Approval

Stop here and wait for the user's reply. Do not write anything from this run's classification before an explicit response arrives.

- "approve all" / "yes" / equivalent → every row in the Proposed Changes table proceeds to Step 7a.
- A partial response, e.g. "approve 1, skip 2" or "just the interview one" → only the specified rows proceed.
- "no" / decline / no changes wanted → no rows proceed; go straight to Step 8 (Update State).

Approving the whole batch in one reply is expected UX - the requirement is that the reply happens first, not that the user approves row by row.

### Step 7a: Write Approved Updates

For every row the user approved:

1. **Tracker (`job_search_tracker.csv`):** update the matched row's `status` column per the Step 5 table, and append to `notes`: `<date> gmail-sync: <signal> ("<email subject>")`. Never restructure the CSV, reorder rows, or touch unrelated rows - same rule `/outcome` follows.

   **If the matched row was still `drafted`,** also set `date` to the email's date. The employer replying proves the user submitted by hand without running `/outcome`, so the drafting date now in that column is wrong. The email's date is an upper bound on the real submission date, tight for an ack and loose for a rejection weeks later, which is why Step 6 shows it and lets the user supply the actual date instead.
2. **`outcome.md`:** tick the relevant stage checkbox (adding the date in parentheses) or update `Status`/`Date resolved` per the table. Append a dated entry to `## Notes`, never overwrite existing Notes history:
   ```
   YYYY-MM-DD (via /gmail-sync): <one-line summary of what the email said>. Source: "<subject>" from <sender>, <email date>.
   ```
3. If no archive folder/`outcome.md` exists yet for a matched application, create the folder and a minimal `outcome.md` following the exact format in `documents/README.md`, same as `/outcome` would. This is the normal case for a row that was still `drafted`: `/apply` Step 6b writes the tracker row and only `/outcome` Step 3 ever creates the archive, so the folder legitimately does not exist yet. It is also the case for a row added by hand.

Rows the user skipped are left untouched - no tracker write, no `outcome.md` write - but their message IDs are still marked processed in Step 8, so the same email isn't re-proposed every run.

---

## Step 8: Update State

Add every message ID processed this run - approved, skipped, unmatched, filtered as noise, or surfaced as a Step 5b recommendation - to `gmail_sync/state.json`'s `processed_message_ids`, and set `last_sync` to today's date. This makes re-running idempotent - the same email never produces a duplicate proposal, Notes entry, or recommendation-list row.

---

## Step 9: Staleness Check

For open applications with **no** matching activity found this run, check the tracker's `date` column and the most recent dated Notes entry in their `outcome.md`. If the most recent of those is 30+ days old, flag the application as "needs follow-up" in the closing summary below. This is surfaced only - never write anything for staleness.

**Skip `drafted` rows here** - nothing was sent, so no one is late replying.

---

## Step 10: Present Closing Summary

Confirm what actually happened, distinct from the Step 6 proposal:

```
## Gmail Sync - Done - YYYY-MM-DD

### Written
| Company | Role | Signal | Tracker Status | Source Email |
|---|---|---|---|---|
| ... | ... | Interview invite | applied -> interview | "Subject line", 2026-07-10 |

### Skipped (not written)
- **<Company>** - <signal> declined by user.

### Offers Requiring Your Decision
- **<Company>** - offer written 2026-07-12 ("<subject>"). Tracker set to `offer`; run `/outcome <company>` to record accept/decline once you decide.

### Stale Applications (30+ days, no activity)
- **<Company>** - last activity YYYY-MM-DD, still `<status>`.
```

If nothing was proposed this run, a brief note is enough instead of an empty summary.

If this run pushed the count of applications with a **final** `outcome.md` status to 3+ (or resolved a second application sharing a pattern), suggest the same `/setup` Path A calibration handoff `/outcome` suggests - do not duplicate that logic, just point the user there.

---

## Important Rules

1. **Classify from full email bodies, never snippets.** A status-changing proposal requires having actually fetched and read the message via `get_thread`/`get_message`.
2. **Nothing is written to the tracker or `outcome.md` before the user approves the Step 6 batch.** Approving everything in one reply is fine UX; writing first and flagging it after is not. This gate is specifically for application history (Step 5/7a) - it does not extend to Step 5b's `seen_jobs.json` registration, which follows `/scrape`'s own precedent of writing to that cache unconditionally, since it is a low-stakes, freely-re-derivable index rather than a permanent record.
3. **Never propose `hired` or `offer_declined`.** Those require the user's real-world decision; `/gmail-sync` stops at proposing `offer` and flags it.
4. **A conflicting signal against an already-final or already-written status is a manual-review flag, not a proposed overwrite.** When in doubt, don't propose it - surface it.
5. **Append-only to `outcome.md` Notes**, same as `/outcome`. Never rewrite or delete existing history.
6. **Idempotent by message ID.** Re-running must never re-propose, or duplicate a tracker note or Notes entry for, the same email.
7. **Never fabricate a match.** If the company can't be confidently identified from the email, it goes in "Unmatched," not a guess.
8. **Read-only against Gmail itself.** This command reads and classifies; it does not label, archive, or delete anything in the user's mailbox.
9. **All state is personal data.** `gmail_sync/state.json`, `job_search_tracker.csv`, and `documents/applications/**` are gitignored - never suggest committing them.
10. **Recommendation leads (Step 5b) are dedup-checked and registered into `seen_jobs.json` as `status: "new"`, never scored.** This reuses `/scrape`'s own dedup check and write schema rather than a parallel mechanism - it never runs a fit assessment, never fetches the posting for detail, and never touches the tracker. A registered lead is picked up by the next `/rank` run exactly like anything else with `status: "new"`; it is not evaluated here.

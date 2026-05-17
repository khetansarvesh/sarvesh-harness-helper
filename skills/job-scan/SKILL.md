---
name: job-scan
description: Discover new job postings from ATS platforms — scans Greenhouse, Ashby, Lever APIs, filters by title, deduplicates, and feeds the evaluation pipeline.
---

# Job Portal Scanner

Discover new job postings by scanning ATS platforms (Greenhouse, Ashby, Lever) directly via their public APIs. Filters by title keywords, deduplicates against Notion, and adds new offers to Notion with status "Scanned" for evaluation.

## When to Activate

- User asks to scan for new jobs or openings
- User wants to discover roles at specific companies
- User says "scan", "find jobs", "check portals", or "what's new"
- On a recurring schedule (e.g., every few days)

## Prerequisites

- **Python 3.10+** installed
- **NOTION_TOKEN** environment variable set (or in `.env` at repo root)
- (Optional) **Playwright** for Level 1 (direct navigation) and Level 3 (liveness verification)

## Non-Negotiables

1. **Always deduplicate** before adding — check Notion DB (URL match + company+role match)
2. **Never add expired postings** — Level 3 (WebSearch) results MUST be verified via Playwright before adding
3. **Never parallelize Playwright** — liveness checks must run sequentially (one page at a time)
4. **Respect title filters** — at least 1 positive keyword must match AND 0 negative keywords can match
5. **Notion is the single source of truth** — all dedup and storage goes through Notion

## 3-Tier Discovery Strategy

### Level 1 — Playwright Direct (Most Reliable)

Navigate directly to each company's `careers_url` with a browser:

- Sees the page in real-time (not cached by Google)
- Works with SPAs (Ashby, Lever, Workday)
- Detects new offers instantly
- Handles pagination

**When to use:** For companies with `careers_url` configured. Best for companies you check regularly.

### Level 2 — ATS APIs (Fast, Structured) — PRIMARY for script

The `scout_specials.py` script uses this level. Hits public JSON APIs directly:

| ATS            | API Endpoint                                                | Parser                                |
| -------------- | ----------------------------------------------------------- | ------------------------------------- |
| **Greenhouse** | `https://boards-api.greenhouse.io/v1/boards/{company}/jobs` | `jobs[]` → `title`, `absolute_url`    |
| **Ashby**      | `https://api.ashbyhq.com/posting-api/job-board/{company}`   | `jobs[]` → `title`, `jobUrl`          |
| **Lever**      | `https://api.lever.co/v0/postings/{company}`                | Root array `[]` → `text`, `hostedUrl` |

**Auto-detection:** The script detects the ATS provider from the `careers_url` pattern:

- `jobs.ashbyhq.com/{slug}` → Ashby API
- `jobs.lever.co/{slug}` → Lever API
- `api` field containing "greenhouse" → Greenhouse API

**Concurrency:** 10 parallel workers (HTTP fetch pool, not Playwright).

### Level 3 — WebSearch (Broad Discovery)

Use WebSearch with `site:` filters to discover companies NOT yet in `tracked_companies`:

- `site:jobs.ashbyhq.com "AI Engineer" OR "ML Engineer"`
- `site:job-boards.greenhouse.io "Research Scientist" OR "Applied AI"`

**CRITICAL:** WebSearch results may be stale (Google caches for weeks). Before adding to Notion, verify liveness with Playwright or `check-liveness.mjs`.

### Priority Order

1. **Level 2 (APIs)** via `scout_specials.py` — fast, reliable, zero-token (run this most often)
2. **Level 1 (Playwright)** — when you need real-time verification or the company has no API
3. **Level 3 (WebSearch)** — for discovering new companies, always verify before adding

## Title Filtering

Loaded from the **Notion Preferences page**. Applied centrally in `dedup_liveness_upload.py` (not during collection). View current keywords:

```bash
python3 scripts/notion/page_preferences.py --title-filter --pretty
```

**Rule:** At least 1 positive keyword must match AND 0 negative keywords can match (case-insensitive).

**Matching logic:**
- Short keywords (≤3 chars: AI, ML, NLP, RAG) use **word boundary** matching — `\bAI\b` matches "AI Engineer" but NOT "Chair" or "MAID"
- Longer keywords ("Machine Learning", "Research Engineer") use **substring** matching
- Negative keywords always use substring matching

Edit keywords directly in the Notion Preferences page under "Positive Job Title Filters" and "Negative Job Title Filters" headers.

## Deduplication

Before adding any offer, check against the **Notion applications DB**:

1. **URL match** — exact URL already exists in any row
2. **Company+role match** — same company + role combination (catches URL changes)

This prevents re-scanning the same offer even if it appears across multiple levels.

## Liveness Verification

Runs on ALL candidates in the pipeline (API + WebSearch + user input). The `dedup_liveness_upload.py` script checks every URL after dedup, regardless of source.

**Using the script:**

```bash
node skills/job-scan/scripts/liveness_helpers/check-liveness.mjs URL1 URL2 URL3
# or from a file:
node skills/job-scan/scripts/liveness_helpers/check-liveness.mjs --file urls.txt
```

**Classification logic (liveness_helpers/liveness-core.mjs):**

| Signal                                                                                  | Result        |
| --------------------------------------------------------------------------------------- | ------------- |
| HTTP 404 or 410                                                                         | **Expired**   |
| URL contains `?error=true` (Greenhouse redirect)                                        | **Expired**   |
| Page text matches expired patterns ("job no longer available", "position filled", etc.) | **Expired**   |
| Visible Apply/Submit button in main content (not nav/footer)                            | **Active**    |
| Page has content but no Apply button                                                    | **Uncertain** |
| Content < 300 chars (nav/footer only)                                                   | **Expired**   |

**Expired patterns detected (multilingual):**

- English: "job no longer available", "position has been filled", "this job has expired"

**Visibility check:** Only counts Apply buttons that are:

- NOT inside `<nav>`, `<header>`, or `<footer>`
- NOT `aria-hidden="true"`
- NOT `display: none` or `visibility: hidden`
- Have physical size (width > 0, height > 0)

## Running the Scanner

### Default scan (API + WebSearch + liveness):

This is the standard pipeline that runs every time `/job-scan` is invoked. ALL steps are mandatory — do NOT skip WebSearch or liveness.

**Important:** Title filtering is centralized in `dedup_liveness_upload.py`, NOT in the collection steps. All sources just dump raw candidates into `candidate_store.json`. Filtering happens once at the end.

**Step 1:** Run API scan, writing to candidate store (defaults to last 24 hours, use `--hours 0` for all):

```bash
python3 skills/job-scan/scripts/scout_specials.py
```

**Step 1.5 (MANDATORY):** WebSearch fallback for companies without ATS APIs:

`scout_specials.py` prints companies it skipped (no detectable API) with their careers URLs. **ALWAYS run WebSearch for these skipped companies** — they often include top employers (OpenAI, Meta, Apple, etc.) that don't have public JSON APIs.

**How to build the query:** Use `site:{careers_page_url}` followed by positive keywords from the Notion Preferences page (the same keywords used by the title filter). Pick the most relevant 3-5 keywords for each query.

Example for Google DeepMind (`https://deepmind.google/about/careers/`):

```
site:deepmind.google "Research Engineer" OR "ML Engineer" OR "Research Scientist" OR "AI Engineer"
```

Example for OpenAI (`https://openai.com/careers`):

```
site:openai.com/careers "Research Engineer" OR "Applied AI" OR "Machine Learning" OR "LLM"
```

For each skipped company:

1. Build a WebSearch query using `site:{careers_url}` + positive keywords from Notion Preferences
2. Run WebSearch with the query
3. Parse each result — extract title, company, and URL
4. Append ALL results to `skills/job-scan/candidate_store.json` (title filtering happens later in Step 3)

**Use a background agent** to run all skipped company searches in parallel for speed.

**Step 2 (MANDATORY):** WebSearch discovery for broad queries:

Load search queries from Notion by running:

```bash
python3 scripts/notion/page_preferences.py --search-queries --pretty
```

For each query:

1. Run WebSearch with the query string
2. Parse each result — extract title, company, and URL:
   - Title: text before " @ " or " | " or " — " in the result title
   - Company: text after " @ " or " | " or " — "
   - URL: the result link
3. Append ALL results to `skills/job-scan/candidate_store.json` (title filtering happens later in Step 3)

Each candidate should be: `{"company": "...", "role": "...", "url": "...", "source": "web_search"}`

**Use a background agent** to run all broad discovery queries in parallel for speed.

**Step 2.5 (MANDATORY):** Add user-input jobs from Notion Preferences:

Load manually added job URLs:
```bash
python3 scripts/notion/page_preferences.py --user-input-jobs --pretty
```

For each URL listed, append to `skills/job-scan/candidate_store.json` with:
```json
{"company": "(extract from URL or page title)", "role": "(extract from page title)", "url": "...", "source": "user_input"}
```

This allows you to paste job URLs directly into the Notion Preferences page under "User Input Jobs" and have them flow through the same pipeline.

**Step 3 (MANDATORY):** Title filter, dedup, liveness check, and upload:

```bash
python3 skills/job-scan/scripts/dedup_liveness_upload.py skills/job-scan/candidate_store.json
```

This script runs four steps in sequence:
1. **Title filter** — loads positive/negative keywords from Notion Preferences, filters candidates by role title. Short keywords (AI, ML, NLP) use word-boundary matching to avoid false positives.
2. **Dedup** — queries Notion once, filters duplicates (URL + company::role, both vs Notion and intra-batch)
3. **Liveness check** — runs Playwright on each deduped URL to verify it's still active. Expired links are filtered out before upload.
4. **Upload** — writes surviving jobs to Notion with status "Scanned"

**NEVER use `--skip-liveness`** — dead URLs will get uploaded to Notion.

### Scan a single company:

```bash
python3 skills/job-scan/scripts/scout_specials.py --company anthropic
```

### Preview without writing:

```bash
python3 skills/job-scan/scripts/scout_specials.py --dry-run
```

### Check if specific URLs are still active:

```bash
node skills/job-scan/scripts/liveness_helpers/check-liveness.mjs https://job-boards.greenhouse.io/company/jobs/123
```

## Output

### New offers → Notion DB (status: "Scanned")

Each new offer is added as a row in the Notion applications database with:

- `Company_Name`, `Role`, `URL`, `Date` populated
- `Status` = "Scanned"
- No score (added later by job-eval/job-eval)

### Console summary:

```
Portal Scan — 2026-04-15                    ← scout_specials.py output
━━━━━━━━━━━━━━━━━━━━━━━━━━
Companies scanned:     14
Total jobs found:      2103
Filtered:              2089 removed          ← hours filter only (default: 24h)
Intra-scan dupes:      0 skipped
New offers added:      14

Loaded 122 candidates from candidate_store.json   ← dedup_liveness_upload.py output
  Title filter: 27 positive, 31 negative keywords
  After title filter: 107 pass, 15 filtered out
  After dedup: 97 new, 10 duplicates
  Liveness: 48 expired, 49 active/uncertain pass through
  Uploaded 49 jobs to Notion (status: Scanned)

→ Run job-eval on new offers to score them.
```

## File Structure

```
skills/job-scan/
├── SKILL.md                        # This file
├── candidate_store.json            # Staging file for collect → filter → dedup → liveness → upload
└── scripts/
    ├── scout_specials.py           # Portal scanner orchestrator
    ├── dedup_liveness_upload.py         # Title filter → dedup → liveness → upload to Notion
    ├── api_helpers/
    │   ├── api_job_fetcher.py      # Parallel fetch from ATS APIs
    │   ├── api_parsers.py          # Board-specific parsers (Greenhouse/Ashby/Lever/Workday)
    │   └── api_resolver.py         # URL → API endpoint resolver
    └── liveness_helpers/
        ├── check-liveness.mjs      # Playwright URL liveness checker
        └── liveness-core.mjs       # Shared liveness classification logic

scripts/notion/                     # Shared Notion scripts (at repo root)
├── config.py                       # Loads all IDs from .env
├── notion_client.py                # HTTP primitives
├── db_applications.py              # Applications DB (add, query, update, dedup)
├── db_companies.py                 # Companies DB (load by category)
├── page_reader.py                  # Page block fetcher
└── page_preferences.py             # Preferences parser (title filter, search queries)
```

## Dependencies

- **playwright** — `npm install playwright && npx playwright install chromium` (for liveness checks only)

## Related Skills

- **job-eval** — Evaluate offers discovered by scanning
- **job-cv-tailor** — Generate tailored CV for high-scoring offers
- **job-apply** — Fill application forms

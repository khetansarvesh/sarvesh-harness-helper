---
name: job-scan
description: Discover new job postings from ATS platforms — scans Greenhouse, Ashby, Lever APIs, filters by title, deduplicates, and feeds the evaluation pipeline.
---

# Job Portal Scanner

Discover new job postings by scanning ATS platforms (Greenhouse, Ashby, Lever) directly via their public APIs. Filters by title keywords, deduplicates against Notion, and adds new offers to Notion with status "Scanned" for evaluation.

## Setup

**Requirements**
- Python 3.10+; Node.js for the `.mjs` liveness/extraction helpers
- Install the Notion integration package:
  ```bash
  python -m pip install sarvesh-ai-notion-interface
  ```
- Notion access via environment variables or a `.env` file in your working directory:
  - `NOTION_TOKEN` — Notion integration token (required)
  - Database IDs as needed: `NOTION_DB_APPLICATIONS`, `NOTION_DB_COMPANIES`, `NOTION_DB_CONNECTIONS`
  - Page IDs as needed: `NOTION_PAGE_PARENT`, `NOTION_PAGE_RESUME`, `NOTION_PAGE_PROJECTS`

The Notion integration package (`sarvesh-ai-notion-interface`) is published on PyPI and contains all database helpers for job tracking.

## Codex Compatibility

- "WebSearch" in older notes means Codex's web search capability.
- "Background agent" means a Codex subagent. If subagents are unavailable on your current surface, run the same collection steps sequentially in the main thread.
- Browser steps are written as actions, not tool IDs. Use the browser surface available in your Codex environment: browser MCP, in-app browser, Chrome extension, or computer use.

## When to Activate

- User asks to scan for new jobs or openings
- User wants to discover roles at specific companies
- User says "scan", "find jobs", "check portals", or "what's new"
- On a recurring schedule (e.g., every few days)

## Prerequisites

- **Python 3.10+** installed
- **NOTION_TOKEN** environment variable set (or in `.env` at repo root)
- **Playwright** installed (`npx playwright install chromium`) — required for liveness verification
- **Jobright.ai tab** open in Chrome with filters applied and user logged in — required for Jobright scan

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

**CRITICAL:** web search results may be stale (search indexes can lag for weeks). Before adding to Notion, verify liveness with Playwright or `check-liveness.mjs`.

### Priority Order

1. **Level 2 (APIs)** via `scout_specials.py` — fast, reliable, zero-token (run this most often)
2. **Level 1 (Playwright)** — when you need real-time verification or the company has no API
3. **Level 3 (WebSearch)** — for discovering new companies, always verify before adding

## Title Filtering

Loaded from the **Notion Preferences page**. Applied centrally in `dedup_liveness_upload.py` (not during collection). View current keywords:

```bash
python3 -m sarvesh_ai_notion_interface.page_preferences --title-filter --pretty
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
node scripts/liveness_helpers/check-liveness.mjs URL1 URL2 URL3
# or from a file:
node scripts/liveness_helpers/check-liveness.mjs --file urls.txt
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

This is the standard pipeline that runs every time `/job-scan` is invoked. ALL steps are mandatory — do NOT skip web search or liveness.

**Important:** Title filtering is centralized in `dedup_liveness_upload.py`, NOT in the collection steps. All sources just dump raw candidates into `candidate_store.json`. Filtering happens once at the end.

**Step 1:** Run API scan, writing to candidate store. **NEVER use `--hours 0`** — it disables the time filter entirely and floods the pipeline with stale jobs (some months old). The default 24h filter is correct for daily scans. For weekly scans, use `--hours 168`. For broader catch-up scans, use `--hours 720` (30 days) at most:

```bash
python3 scripts/scout_specials.py
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
2. Run the query with WebSearch **with the same `startPublishedDate` time filter as Step 2** (based on the scan interval — 4h/24h/168h)
3. For each result, check if the URL is a **specific job posting** or a **landing/category page**:
   - **Specific job URL** (has UUID, numeric job ID like `/jobs/12345`, or known ATS pattern) → add directly to candidate store
   - **Landing/category page** (URL ends in `/careers`, `/search?`, `/job-category/`, or has no job-specific identifier) → **run the Adaptive Career Page Crawl protocol below**
4. **Return all results as JSON** — do NOT write to `candidate_store.json` directly from a subagent. Instead, return the array of candidates in the subagent result, and the main thread will append them to `candidate_store.json` after the subagent completes.

**Process skipped companies sequentially** (one browser tab or browser session at a time). Do not parallelize browser crawling.

#### Adaptive Career Page Crawl Protocol

When a URL is a landing/category page, follow this protocol to extract individual job URLs using the site's own filters.

**Step A — Open & Orient:**

1. Open the landing page URL in the available browser tool
2. Wait 3 seconds for JS/SPA rendering
3. Capture a page snapshot or equivalent structured DOM/accessibility view
4. Classify the page into one of three types:
   - **Type A (Filter-capable):** Page has visible search/filter controls — look for `searchbox`, `combobox`, `textbox` with labels like "search", "keyword", "location", "country", "team", "category"
   - **Type B (Plain listing):** Page shows job listings directly with no filter UI — just links to individual jobs
   - **Type C (Unusable):** Page requires login, shows CAPTCHA, is empty, or failed to load
5. Branch based on type: Type A → Step B, Type B → Step C, Type C → Step E

**Step B — Apply Filters (Type A only):**

1. **Location filter (priority 1):**
   - If location dropdown/combobox exists: `click` to open it, `take_snapshot` to see options, click "United States" / "US" / "USA" / "North America" (whichever available)
   - If location text input exists: `fill` with "United States", press Enter or select from autocomplete
   - If no location filter: skip (do not fail)

2. **Keyword filter (priority 2):**
   - If search/keyword text input exists: `fill` with the top 2-3 positive keywords from Notion Preferences joined by space (e.g., "ML Engineer Research Scientist"). Do NOT use OR syntax — type natural terms.
   - If role/team/category dropdown exists: open it, select the option closest to positive keywords (e.g., "Machine Learning", "AI", "Research")
   - If no keyword filter: skip (do not fail)

3. **Trigger search:** Press Enter or click a "Search" / "Apply" / "Filter" button if visible. Wait 2-3 seconds for results.

4. **Verify results:** Call `take_snapshot` again.
   - If results loaded (links visible): proceed to Step C
   - If "0 results" or page unchanged: **broaden** — remove keyword filter, keep only location, retry. If still 0: fall through to Step C with unfiltered page.

**Step C — Extract Job Links (Type A filtered + Type B):**

Run this JavaScript through the browser tool's page-evaluation capability:

```javascript
(() => {
  const links = Array.from(document.querySelectorAll('a[href]'));
  const seen = new Set();
  return links.filter(a => {
    const href = a.href;
    const path = new URL(href, location.origin).pathname;
    return /\/(jobs?|details|position|opening|apply|posting|role)\b/i.test(path)
      || /\/\d{5,}/.test(path)
      || /[0-9a-f]{8}-[0-9a-f]{4}-/.test(path);
  }).map(a => ({
    url: a.href,
    title: a.textContent.trim().replace(/\\s+/g, ' ').substring(0, 200)
  })).filter(j => j.title.length > 3 && !seen.has(j.url) && seen.add(j.url));
})()
```

- If `evaluate_script` fails or returns empty: fall back to reading the snapshot for links with job-like patterns
- For each extracted job: `{"company": "<company_name>", "role": "<title>", "url": "<url>", "source": "career_crawl"}`
- **Discard the original landing page URL** — never add it to the candidate store

**Step D — Handle Pagination (max 3 pages):**

1. After extracting from the current page, check the snapshot for pagination controls: "Next", "Show more", page number buttons, or "Load more"
2. If a next-page control exists AND fewer than 50 jobs extracted so far: click it, wait 2 seconds, run extraction again
3. **Cap at 3 pages maximum** — stop after page 3 regardless
4. If the site uses infinite scroll / "Load more": click the load-more button up to 2 times, then extract all links at once
5. Deduplicate extracted URLs across pages before adding to candidate store

**Step E — Handle Failures (Type C + errors):**

- **Page won't load / timeout:** Log `crawl failed: page did not load for {company}`. Move to next company.
- **Login / CAPTCHA required:** Log `crawl failed: login/CAPTCHA required for {company}`. Move to next company.
- **No job links found:** Log `crawl failed: no job links detected on {url}`. Move to next company.
- **Script errors:** Try snapshot-based fallback. If that also finds nothing, log and move on.
- **NEVER block the pipeline** — a failed crawl must not prevent processing other companies.

After processing all skipped companies, print a summary:
```
Career page crawl: X companies attempted, Y succeeded (Z total jobs), W failed
```

#### Worked Example

```
Company: TechCorp (skipped, careers_url: https://careers.techcorp.com/engineering)
1. WebSearch: `site:careers.techcorp.com "ML Engineer" OR "Research Scientist"`
   → Returns https://careers.techcorp.com/engineering?team=ml (landing page)
2. Open page → take_snapshot
   → Finds: searchbox (uid: s42), location dropdown (uid: s78), 150 job listings
   → Classified as Type A (filter-capable)
3. Apply filters:
   → Click location dropdown (s78) → select "United States"
   → Fill search box (s42) with "ML Engineer"
   → Press Enter → wait 3s → take_snapshot
   → Now shows 12 results (down from 150)
4. Extract links:
   → evaluate_script returns 12 job objects with specific URLs
   → e.g., {url: "careers.techcorp.com/jobs/12345/senior-ml-engineer", title: "Senior ML Engineer"}
5. No page 2 → done
6. Append 12 candidates to candidate_store.json with source: "career_crawl"
```

**Step 1.75 (MANDATORY):** Jobright.ai scrape

Jobright.ai is a job aggregator with AI-powered matching. If the user has a Jobright tab open with filters applied, scrape it for additional job discoveries.

1. Inspect open browser pages and look for a page URL containing `jobright.ai`
   - If **not found** → print `"Jobright: No tab found, skipping"` and move to Step 2
   - If **found** → switch to that page in the active browser tool

2. **Auto-refresh** the page to get the latest listings. Reload the current Jobright URL (for example `https://jobright.ai/jobs/recommend`), then wait for text such as `Recommended` or `APPLY` to ensure the page has fully loaded.

   All extraction functions are in `scripts/jobright_helpers/extract-jobright.mjs` (relative to this skill's directory). Read the file and inject functions through the browser tool's script-evaluation feature.

3. **Scroll to load all jobs.** Call `evaluate_script` with the `scrollAndCount()` function from `extract-jobright.mjs`. Returns the total number of job cards loaded.

4. **Extract all job cards.** Call `evaluate_script` with the `extractJobs()` function. Returns array of `{title, company, jobrightUrl, location}`.

5. **Resolve real ATS URLs.** Call `evaluate_script` with `resolveUrls(jobrightUrls)` passing the array of Jobright URLs. This fetches each info page in-browser (where auth cookies exist) and regex-matches real ATS URLs (Greenhouse, Ashby, Lever, Workday, Personio, etc.).

   For any `greenhouse-embed:{token}` results, call `resolveGhEmbed(slug, token)` to resolve via the Greenhouse boards API. Derive slug from company name: lowercase, remove spaces/special chars (e.g., "Anduril Industries" → "andurilindustries").

6. **Merge and save.** Combine extracted jobs with resolved URLs. Each job should have: `title`, `company`, `url` (real ATS URL or Jobright fallback), `location`. Save as `jobright_raw.json` in this skill's directory.

7. **Run the processing script** to normalize and append to candidate store:
   ```bash
   python3 scripts/resolve_jobright.py
   ```

8. Print the summary from the script output.

**Step 2 (MANDATORY):** WebSearch discovery for broad queries:

Load search queries from Notion by running:

```bash
python3 -m sarvesh_ai_notion_interface.page_preferences --search-queries --pretty
```

For each query:

1. Run WebSearch with the query string **AND a `startPublishedDate` time filter** = 24 hours ago (ISO 8601) : 
   - **NEVER run web searches without `startPublishedDate`** — without it, Exa returns stale results that waste liveness checks and flood the pipeline with expired jobs.
2. Parse each result — extract title, company, and URL:
   - Title: text before " @ " or " | " or " — " in the result title
   - Company: text after " @ " or " | " or " — "
   - URL: the result link
3. **Return all results as JSON** — do NOT write to `candidate_store.json` directly from a subagent. Instead, return the array of candidates in the subagent result, and the main thread will append them to `candidate_store.json` after the subagent completes.

Each candidate should be: `{"company": "...", "role": "...", "url": "...", "source": "web_search"}`

**Note:** Web search candidates will not have a `location` field — that's expected. The `dedup_liveness_upload.py` pipeline automatically enriches missing locations from ATS APIs (Greenhouse/Ashby/Lever) during Step 3. No need to add location manually.

**Use a subagent** to run broad discovery queries in parallel when the current surface supports subagents. After the subagent completes, parse its returned JSON and append to `candidate_store.json` yourself. If subagents are unavailable, run the queries sequentially in the main thread.

**IMPORTANT — Subagent File Write Pattern:**
Subagents should not write `candidate_store.json` directly. Always instruct subagents to:
1. Collect results in memory
2. Return the full JSON array in their completion message
3. The main orchestrator then reads the agent's result and writes to `candidate_store.json`

Never instruct a subagent to write/edit/append to `candidate_store.json` directly.

**Step 2.5 (MANDATORY):** Add user-input jobs from Notion Preferences:

Load manually added job URLs:
```bash
python3 -m sarvesh_ai_notion_interface.page_preferences --user-input-jobs --pretty
```

For each URL listed, append to `candidate_store.json` (in this skill's directory) with:
```json
{"company": "(extract from URL or page title)", "role": "(extract from page title)", "url": "...", "source": "user_input"}
```

This allows you to paste job URLs directly into the Notion Preferences page under "User Input Jobs" and have them flow through the same pipeline.

**Step 3 (MANDATORY):** Title filter, location enrichment, dedup, liveness check, and upload:

```bash
python3 scripts/dedup_liveness_upload.py candidate_store.json
```

This script runs six steps in sequence:
1. **Title filter** — loads positive/negative keywords from Notion Preferences, filters candidates by role title. Short keywords (AI, ML, NLP) use word-boundary matching to avoid false positives.
2. **Location enrichment** — for candidates with no location (e.g., from web search), batch-fetches Greenhouse/Ashby/Lever APIs by company slug to resolve the job's location. This allows non-US jobs to be filtered out even when they come from web search.
3. **Location filter** — removes non-US jobs using `is_us_location()`. Jobs with known US/Remote locations pass; known non-US (India, Germany, London, etc.) are filtered out; unknown locations pass through.
4. **URL filter** — removes landing/category pages that aren't specific job postings.
5. **Dedup** — queries Notion once, filters duplicates (URL + company::role, both vs Notion and intra-batch)
6. **Liveness check** — runs Playwright on each deduped URL to verify it's still active. Expired links are filtered out before upload.
7. **Upload** — writes surviving jobs to Notion with status "Scanned", including the `Location` field.

**NEVER use `--skip-liveness`** — dead URLs will get uploaded to Notion.

### Scan a single company:

```bash
python3 scripts/scout_specials.py --company anthropic
```

### Preview without writing:

```bash
python3 scripts/scout_specials.py --dry-run
```

### Check if specific URLs are still active:

```bash
node scripts/liveness_helpers/check-liveness.mjs https://job-boards.greenhouse.io/company/jobs/123
```

## Output

### New offers → Notion DB (status: "Scanned")

Each new offer is added as a row in the Notion applications database with:

- `Company_Name`, `Role`, `URL`, `Date`, `Location` populated
- `Status` = "Scanned"
- `Source` = API / Web Search / Broad Web Search / Fallback Web Search / User / Jobright (normalized from candidate source field)
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

Jobright: 8 jobs processed, 7 resolved to ATS URLs, 1 fallback  ← resolve_jobright.py output

Loaded 122 candidates from candidate_store.json   ← dedup_liveness_upload.py output
  Title filter: 27 positive, 31 negative keywords
  After title filter: 107 pass, 15 filtered out
  Location enrichment: 20 candidates need location lookup
    Greenhouse: 8 enriched, Ashby: 10 enriched, Lever: 2 enriched
  After location filter: 97 pass, 10 non-US filtered out
  After URL filter: 93 pass, 4 landing pages filtered out
  After dedup: 82 new, 11 duplicates
  Liveness: 41 expired, 41 active/uncertain pass through
  Uploaded 41 jobs to Notion (status: Scanned)

→ Run job-eval on new offers to score them.
```

## File Structure

```
skills/job-scan/
├── SKILL.md                        # This file
├── candidate_store.json            # Staging file for collect → filter → dedup → liveness → upload
├── jobright_raw.json               # Temporary: raw Jobright extraction (deleted after resolve)
└── scripts/
    ├── scout_specials.py           # Portal scanner orchestrator
    ├── resolve_jobright.py         # Jobright data normalizer + candidate store writer
    ├── enrich_location.py             # Enrich missing locations from ATS APIs (called by dedup_liveness_upload)
    ├── dedup_liveness_upload.py         # Title filter → location enrichment → dedup → liveness → upload to Notion
    ├── backfill_location.py             # One-time backfill of Location column for existing Scanned jobs
    ├── jobright_helpers/
    │   └── extract-jobright.mjs    # Browser-side JS functions for Jobright extraction
    ├── api_helpers/
    │   ├── api_job_fetcher.py      # Parallel fetch from ATS APIs
    │   ├── api_parsers.py          # Board-specific parsers (Greenhouse/Ashby/Lever/Workday)
    │   └── api_resolver.py         # URL → API endpoint resolver
    └── liveness_helpers/
        ├── check-liveness.mjs      # Playwright URL liveness checker
        └── liveness-core.mjs       # Shared liveness classification logic

sarvesh_ai_notion_interface        # Notion integration (pip install sarvesh-ai-notion-interface)
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

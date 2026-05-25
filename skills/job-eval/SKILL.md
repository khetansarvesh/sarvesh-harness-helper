---
name: job-eval
description: Parallel batch processing — evaluate 10-100+ job offers simultaneously via claude -p workers with state tracking, retry logic, and resumability.
---

# Batch Job Evaluation

Process multiple job offers in parallel. Each worker runs a full A-G evaluation independently. The orchestrator tracks state, handles retries, and merges results into the application tracker.

Each worker produces a report + tracker entry. The orchestrator manages the coordination.

## When to Activate

- User has 3+ job offers to evaluate
- User wants to process their entire pipeline at once
- User says "batch evaluate", "process all pending", or "evaluate everything"
- After job-scan discovers many new offers

## Prerequisites

- **`claude` CLI** installed and authenticated
- **NOTION_TOKEN** environment variable set
- `Notion (fetch via `python3 scripts/notion/page_reader.py resume`)` and `Notion (fetch via `python3 scripts/notion/page_reader.py projects`)` populated
- URLs to evaluate (in `batch-data/batch-input.tsv` or use `--from-notion` to pull "Scanned" jobs)

## Non-Negotiables

1. **Lock file prevents double execution** — never run two batch-runners simultaneously
2. **Every worker is independent** — one failure doesn't affect others
3. **State is always persisted** — interrupted runs resume from where they left off
4. **Workers write to Notion directly** — no local merge needed
5. **Workers don't generate PDFs** — only reports + tracker entries. Run job-cv-tailor separately for high-scoring roles.
6. **Disqualification filters run before A-G evaluation** — non-US jobs and clearance-required jobs are rejected early with score 0

## Disqualification Filters

Workers apply two automatic disqualification filters **before** the expensive A-G evaluation. If either triggers, the job is immediately scored 0, marked "Discarded" in Notion, and the worker stops early.

### What triggers automatic disqualification

| Filter | Disqualify (score 0) | Pass |
|--------|---------------------|------|
| **Non-US Location** | Explicitly non-US locations (London UK, Berlin Germany, Toronto Canada, etc.), "Remote (EU only)", "Remote (EMEA)", "Remote (APAC)" | US cities/states, "Remote", "Remote (US)", "Hybrid" with US city, ambiguous/missing location |
| **Security Clearance / US Citizenship** | Active clearance required (TS, TS/SCI, Secret, Top Secret, DoD), ability to obtain clearance, "US citizenship required", "Must be a US citizen", "US Person" per ITAR/EAR | "Authorized to work in US" (F-1 OPT satisfies), "Sponsorship available", "US Person preferred" (soft) |

### How disqualification appears

- **State file:** status = `completed`, score = `0`
- **Notion:** status = `Discarded`, score = `0`
- **Worker JSON output:** includes `"disqualified": true` and `"disqualification_reason": "{reason}"`
- **Batch summary:** counted separately in the "Disqualified" counter
- **Report:** short mini-report (no A-G sections) explaining the disqualification reason

## Running the Batch

### From the repo root:

```bash
# Pull "Scanned" jobs from Notion and evaluate in parallel
bash skills/job-eval/batch-runner.sh --from-notion --parallel 4

# Preview what would be processed (no execution)
bash skills/job-eval/batch-runner.sh --from-notion --dry-run

# Evaluate all offers in batch-input.tsv (manual input)
bash skills/job-eval/batch-runner.sh

# Evaluate 4 offers in parallel
bash skills/job-eval/batch-runner.sh --parallel 4

# Retry only failed offers
bash skills/job-eval/batch-runner.sh --retry-failed --parallel 2

# Start from offer #10, max 3 retries each
bash skills/job-eval/batch-runner.sh --start-from 10 --max-retries 3

# Skip tracker entries for low-scoring offers
bash skills/job-eval/batch-runner.sh --min-score 3.5 --parallel 4
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--parallel N` | 1 | Number of concurrent workers |
| `--dry-run` | false | Preview without executing |
| `--from-notion` | false | Query Notion for "Scanned" jobs and generate batch-input.tsv |
| `--retry-failed` | false | Only retry previously failed offers |
| `--start-from N` | 0 | Skip offers with ID < N |
| `--max-retries N` | 2 | Max retry attempts per offer |
| `--min-score N` | 0 (off) | Skip tracker/report for scores below N |

## Input Format

### batch-input.tsv

Location: `skills/job-eval/batch-data/batch-input.tsv`

```tsv
id	url	source	notes	page_id
1	https://job-boards.greenhouse.io/anthropic/jobs/123	Greenhouse
2	https://jobs.ashbyhq.com/openai/abc	Ashby	high priority
3	https://jobs.lever.co/scaleai/xyz	Notion	Scale AI — ML Engineer	34598a5a-ae72-xxxx-xxxx-xxxxxxxxxxxx
```

**Columns:**
1. `id` — sequential integer (1, 2, 3...)
2. `url` — full job posting URL
3. `source` — where it came from (Greenhouse, Ashby, Lever, Notion, etc.)
4. `notes` — optional metadata
5. `page_id` — Notion page ID (optional; auto-populated by `--from-notion`)

**How to populate:**
- **From Notion (recommended):** use `--from-notion` flag — auto-generates from "Scanned" jobs
- Manually: add URLs you want to evaluate (leave `page_id` empty)

## How It Works

### 1. Lock Acquisition
- Creates `batch-data/batch-runner.pid` with process ID
- If another batch-runner is running → error exit
- Stale locks (dead PID) are auto-recovered

### 2. State Initialization
- Creates `batch-data/batch-state.tsv` if missing
- Reads existing state to determine what's pending/completed/failed

### 3. Worker Spawning (per offer)

For each pending offer:

```
Reserve report number (sequential, 3-digit zero-padded)
    ↓
Resolve placeholders in batch-prompt.md ({{URL}}, {{REPORT_NUM}}, {{DATE}}, {{ID}})
    ↓
Launch: claude -p --dangerously-skip-permissions --append-system-prompt-file resolved-prompt.md "Process offer..."
    ↓
Worker produces: report to Notion (via db_applications.py) + JSON stdout
    ↓
Orchestrator extracts score from JSON, updates state
```

### 4. Parallel Processing

With `--parallel N`:
- Maintains pool of N background workers
- When one finishes, next offer starts immediately
- State lock prevents race conditions on state file updates

### 5. Post-Processing

After all workers finish:
- Each worker already pushed its evaluation to Notion directly
- No local merge needed — Notion is the source of truth

### 6. Summary
```
job-eval — 2026-04-15
━━━━━━━━━━━━━━━━━━━━━━━━━━
Total:     50
Completed: 47
Failed:    2
Skipped:   1 (below min-score)
Average:   3.9/5

→ Run job-cv-tailor on high-scoring offers
```

## State Tracking

### batch-state.tsv

Location: `skills/job-eval/batch-data/batch-state.tsv`

```tsv
id	url	status	started_at	completed_at	report_num	score	error	retries
1	https://...	completed	2026-04-15T10:30:00Z	2026-04-15T10:45:00Z	001	4.3	-	0
2	https://...	failed	2026-04-15T10:46:00Z	2026-04-15T10:50:00Z	002	-	Timeout	1
3	https://...	pending	-	-	-	-	-	0
```

### State Transitions

```
pending → processing → completed (score > 0, full A-G evaluation)
                    → completed (score 0, disqualified — skipped A-G evaluation)
                    → failed (retry with --retry-failed)
                    → skipped (score below --min-score)
```

- `completed` → skipped on re-run (already done)
- `failed` + retries >= max-retries → skipped permanently
- `failed` + retries < max-retries → retried with `--retry-failed`
- `processing` (stale — PID dead) → auto-recovered as pending

## Resumability

If the batch is interrupted (Ctrl+C, crash, laptop dies):

1. Re-run the same command
2. Orchestrator reads `batch-state.tsv`
3. Skips all `completed` offers
4. Retries `failed` offers (if retries < max)
5. Continues with `pending` offers

**Nothing is lost.** Reports and tracker entries from completed workers are already on disk.

## Output

### Per worker:
- **Notion row:** Created with Company, Role, URL, Score, Status, Date
- **Notion report:** Full evaluation content pushed into the page body
- **Log:** `skills/job-eval/batch-data/logs/{report_num}-{id}.log`

### After all workers:
- All evaluations already in Notion — no local merge needed

## Error Handling

| Scenario | What happens |
|----------|-------------|
| URL inaccessible | Worker fails → marked `failed`, continue with others |
| JD behind login wall | Worker can't extract JD → fails → flag for manual paste |
| Worker crashes | Marked `failed` → retry with `--retry-failed` |
| Orchestrator dies | Re-run → skips completed, continues pending |
| Score below min | Marked `skipped` → no report/tracker entry |
| All workers fail | Summary shows 0 completed → investigate logs |

## File Structure

```
skills/job-eval/
├── SKILL.md                        # This file
├── batch-runner.sh                 # Orchestrator script
├── batch-prompt.md                 # Self-contained worker prompt
└── batch-data/                     # Runtime data
    ├── batch-input.tsv             # URLs to process (user populates)
    ├── batch-state.tsv             # State tracking (auto-created)
    └── logs/                       # Worker execution logs

skills/job-scan/
└── portals.yml                     # Scan config (companies + title filters)
```

## Related Skills

- **job-scan** — Discover new offers (writes to Notion as "Scanned")
- **job-eval** — A-G evaluation logic lives in `batch-prompt.md`
- **job-cv-tailor** — Generate tailored CV for high-scoring offers (run after batch)
- **job-apply** — Fill application forms for offers you decide to apply to

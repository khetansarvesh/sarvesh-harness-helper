---
name: job-reachout
description: Research the team behind a job posting, identify the hiring manager and best contact, and draft a personalized cold email / LinkedIn DM that maps the user's work to the company's public thesis. Use when the user has already applied (or is about to) and wants a warm signal-boost to a decision-maker.
---

# Job Reachout — Team Research + Personalized Cold Message

After a job application is submitted, a well-researched cold message to the right person raises response rates dramatically. This skill researches the team behind a specific job posting, identifies the single best contact (hiring manager, founder, or peer), and drafts a personalized email or LinkedIn DM that maps the user's actual work to the company's publicly stated thesis.

## When to Activate

- User says "find out who posted this job" or "who should I email about this role"
- User asks to "draft a message for the hiring manager at [company]"
- User says "reach out to [company] people" after applying
- User wants a warm intro / signal-boost on top of a submitted application
- User shares a job URL and asks "who do I contact?"
- User says "run reachout for all my evaluated jobs" or "draft reachouts for everything in Almost Applied" → **batch mode** (Phase 0 queries Notion, loops Phase 1–6 per job, writes each to Notion)

## Prerequisites

- **The job posting URL or company + role name** — required to identify the team (single-job mode). In batch mode, URLs come from Notion.
- **User's profile data** loaded fresh:
  - `Notion (fetch via `python3 scripts/notion/page_reader.py resume`)` — experience, education, skills, projects
  - `Notion (fetch via `python3 scripts/notion/page_reader.py projects`)` — detailed project descriptions for matching
- Optional but high-value: the user has already applied (so the message is a signal-boost, not a substitute)
- `NOTION_TOKEN` environment variable set — for fetching profile data AND for the Notion read/write in batch mode

## Non-Negotiables

1. **NEVER draft a generic message** — every message must reference a specific, verifiable piece of the company's public work (a blog post, paper, product launch, LinkedIn post, or research area)
2. **NEVER invent contact info** — only use emails/LinkedIn URLs found via search or confidently inferred from public patterns. Flag guessed emails as "try this, may bounce"
3. **Always identify the hiring manager FIRST** — the goal is the decision-maker, not a random employee. Founders/CTOs at small startups are usually the hiring manager
4. **Always read the user's profile fresh** — never rely on cached/remembered project descriptions
5. **Always map user's work → company's thesis with named projects on both sides** — "my EvoSkill maps to your Generative Simulators" beats "I have relevant experience"
6. **Be honest about qualification gaps** — if the user doesn't meet a hard requirement (PhD, years of experience, citizenship), get ahead of it in the message rather than hiding it
7. **One concrete ask** — always end with a specific, low-friction request (usually "20-min chat to compare what I built vs. what you're building")
8. **ALWAYS write findings back to Notion** in batch mode — the full reachout section (team, mapping, contacts, draft, why-it-works) goes under a `## Reachout` header on the job's Notion page. The chat shows the draft for copy-paste; Notion is the persistent record.
9. **NEVER overwrite an existing Reachout section** — if a page already has one, skip it (re-runs produce a new dated section, preserving history). Always check before writing.

## The Process

The skill runs in two modes:
- **Single-job mode** — user gives a URL or company name. Run Phases 1–5, then Phase 6 if a Notion `page_id` is known.
- **Batch mode** — user says "run for all evaluated jobs" / "draft reachouts for everything in Almost Applied". Phase 0 queries Notion for candidates, then Phases 1–6 run sequentially per job. Findings are written to each job's Notion page under a `## Reachout` header.

### Phase 0: Query Notion for Candidate Jobs (batch mode only)

**Goal:** Get the list of jobs that need a reachout, skipping any that already have one.

**Step 0.1 — Query candidates:**

```bash
python3 skills/job-reachout/scripts/reachout_writer.py query
```

Returns JSON with all jobs in `Evaluated` or `Almost Applied` status, each flagged with `has_reachout: true/false`. The `has_reachout` flag is populated by fetching each page's blocks and checking for an existing `## Reachout` heading — this prevents duplicate writes on re-runs.

**Step 0.2 — Filter and present to the user:**

Parse the JSON. Split into:
- **Pending** (`has_reachout: false`) — these need a reachout drafted
- **Already done** (`has_reachout: true`) — skip these

Show the user the pending list and ask for confirmation:

```
Found N jobs needing a reachout (M already have one, skipping):
1. [Company] — [Role] ([status]) — [url]
2. ...
Proceed with all N? Or pick specific numbers?
```

**Step 0.3 — Handle missing URLs:**

If a job has `url: null`, flag it and skip — the research phase needs a URL or company+role to work. Note it in the final summary.

**Step 0.4 — Load the user's profile ONCE:**

```bash
python3 scripts/notion/page_reader.py resume
python3 scripts/notion/page_reader.py projects
```

The profile is the same for every job in the batch — load it once before the loop, not per-job.

---

### Phase 1: Identify the Team Behind the Role

**Goal:** Find out which team posted the listing, who the hiring manager is, and who the research/engineering leads are.

**Step 1.1 — Pull the job description and extract team signals:**

If the user gives a URL, fetch it. Read the JD for:
- Team name (e.g., "Research team", "AI agents team")
- Who the role reports to (e.g., "meets weekly with the CTO" = CTO is hiring manager)
- Research areas / tech keywords (e.g., "scalable oversight", "RL environments", "continual learning")
- Company stage and size (early-stage startup = founder is hiring manager; big company = need team lead)

**Step 1.2 — Search the company's careers page and about page:**

```bash
# Use web_search_exa to find the company's team/research pages
web_search_exa query: "[company] team research about" numResults: 10
web_search_exa query: "[company] founders CTO research lead" numResults: 10
```

Fetch these URLs with `web_fetch_exa`:
- Company `/about` or `/company` page — lists founders and their titles
- Company `/research` or `/blog` page — lists recent work and often the authors
- Company `/careers` or `/join` page — confirms the role is open

**Step 1.3 — Find who specifically posted this role:**

```bash
web_search_exa query: "[company] [role title] hiring manager LinkedIn" numResults: 10
web_search_exa query: "[company] [role title] site:linkedin.com/jobs" numResults: 5
```

Look for LinkedIn posts where a founder/lead says "we're hiring [role]" — that person is the hiring manager and has implicitly invited DMs. Fetch their LinkedIn post to confirm.

**Step 1.4 — Find the research/engineering team members (peers):**

```bash
web_search_exa query: "[company] [role title] LinkedIn" numResults: 10
```

Look for people whose LinkedIn title matches the role (e.g., "Research Scientist at [company]"). These are peers who could refer you inward. Note their join dates — recent hires are more approachable.

### Phase 2: Find the Company's Public Thesis

**Goal:** Identify a specific, named piece of the company's public work that the user's work maps to. This is the hook that makes the message land.

**Step 2.1 — Find the company's flagship blog post / paper / launch announcement:**

```bash
web_search_exa query: "[company] [research area from JD] blog introducing" numResults: 8
web_search_exa query: "[company] announcing launch product" numResults: 5
```

Fetch the top 1-2 posts. Extract:
- The name of the work (e.g., "Generative Simulators", "Verifiable Continual Learning")
- The core thesis in 1-2 sentences (e.g., "turn failures into replayable learning environments with in-loop regression control")
- The specific problems they name (e.g., "an update that fixes today's failure can silently break what worked yesterday")
- The author (often a founder — confirms who to message)

**Step 2.2 — Check the founder/CTO's personal research page:**

Many founders have a personal site (e.g., `rebecca-qian.github.io`, `cs.umd.edu/~sfeizi/`). Fetch it for:
- Their stated research interests (these are the keywords to match)
- Their previous work (Meta AI, Google, etc. — useful for personalization)
- Their email (often listed on faculty pages)

**Step 2.3 — Note the funding/stage context:**

```bash
web_search_exa query: "[company] funding raised series" numResults: 5
```

Recent funding = company is actively hiring, founder is reachable, message timing is good. Mention it only if it's recent (last ~3 months) and relevant.

### Phase 3: Map the User's Work to the Company's Thesis

**Goal:** Build a concrete, named mapping between what the user has built and what the company is doing. This is the core of the message.

**Step 3.1 — Load the user's projects:**

```bash
python3 scripts/notion/page_reader.py projects
# And for specific projects:
python3 scripts/notion/page_reader.py {project_name}
```

**Step 3.2 — Build the mapping table:**

For each of the user's projects, check if it maps to a concept from the company's thesis. Write it as a table:

| Company concept | User's project | How it maps |
|---|---|---|
| (from their blog/paper) | (user's project name) | (1 sentence on the technical mapping) |

Rules:
- Only include mappings that are **technically precise** — "my RAG agent is like your agent" is useless; "my TraceDB stores past traces for cross-iteration recall, which is your 'replayable learning environments'" is good
- Aim for 3-4 strong mappings, not 10 weak ones
- Name projects on **both sides** — "my EvoSkill → your Generative Simulators"
- Quantify the user's work (metrics, SOTA results, % improvements)

**Step 3.3 — Identify qualification gaps:**

Compare the user's profile to the JD's hard requirements. Common gaps:
- PhD required, user has MS
- X+ years experience, user has fewer
- US citizenship required, user is on visa
- Specific domain (optical, healthcare, etc.), user has different domain

**Get ahead of these in the message** — don't hide them. Frame as "honest caveat: the listing asks for X, I have Y — but the building experience maps directly."

### Phase 4: Identify the Best Contact and Channel

**Goal:** Pick the single person to message and the best way to reach them.

**Step 4.1 — Rank contacts:**

| Priority | Who | When to pick them |
|---|---|---|
| 1 | Founder/CTO who posted the role | Early-stage startup (<50 people), they said "DM me", role reports to them |
| 2 | Founder/CTO (even if didn't post) | Small company where they're the hiring manager |
| 3 | Team lead / Head of Research | Mid-size company, founder is too senior |
| 4 | Recent peer hire (same role) | Large company, need a referral inward |
| 5 | CEO (operations) | Only if founder/CTO unreachable and CEO posted the role |

**Step 4.2 — Find their contact channel:**

Preferred order:
1. **Faculty email** (if they're a professor) — `cs.umd.edu/~sfeizi/` lists `sfeizi@cs.umd.edu`. Professors always read their faculty email.
2. **LinkedIn DM** — if they explicitly said "DM me" in a post, this is the channel they invited
3. **Guessed email** — `firstname@company.com` is the most common founder pattern. Flag as "try this, may bounce"
4. **LinkedIn connection request** — for peers and when no email is found

**Step 4.3 — Check for warm-intro angles:**

Look for any shared connection that makes the cold message warmer:
- Same university (professor at user's school = "Hi Professor [Name], I'm a [school] ML MS student")
- Same previous employer
- Same research community (published in same venues)
- Same hometown/region (use sparingly, only if genuinely useful)

These go in the **first line** of the message — they're the opener that gets it read.

### Phase 5: Draft the Message

**Goal:** Write a concise, personalized message that opens with the warm angle, maps the user's work to the company's thesis, and ends with one specific ask.

**Step 5.1 — Subject line (for email):**

Format: `[Status]: [Role title] — [Hook]`

Examples:
- `Applied: MTS Research Scientist — EvoSkill/EvoData → Generative Simulators overlap`
- `Applied: AI Research / Engineering — Sarvesh Khetan (UMD ML MS); my EvoSkill work maps to RELAI's regression-in-loop thesis`

Rules:
- Start with "Applied:" if the user already applied — signals this is a follow-up, not cold spam
- Name the exact role so they can route it
- Include the hook (the named mapping) — that's what gets an open
- Avoid generic subjects like "Following up on my application" or "Excited about [company]"

**Step 5.2 — Message body structure:**

**Paragraph 1 — Warm opener + status (2-3 lines):**
- Lead with the warm angle (shared university, "I saw your post about X")
- State that you applied (so this is a signal-boost, not a substitute)
- Name the specific role

**Paragraph 2 — The mapping (the core, 4-6 lines):**
- "The overlap with your [named work] is unusually direct:"
- 3-4 bullet points, each mapping a user project → a company concept
- Named projects on both sides
- Quantified results on user's side

**Paragraph 3 — Honest caveat (1-2 lines, only if there's a gap):**
- "The honest caveat: the listing asks for X, I have Y — but the building experience maps almost line-for-line to what you're doing."
- Only include if there's a real gap. Don't apologize, reframe.

**Paragraph 4 — One specific ask + low friction (2 lines):**
- "Would 20 min to walk through what I built vs. what you're building be useful?"
- Offer to remove friction (come to their office, jump on a call, send a demo)
- Don't ask for a job. Ask for a conversation.

**Sign-off:**
- Name
- Degree + school (if relevant)
- GitHub + LinkedIn

**Step 5.3 — LinkedIn DM version (shorter):**

If the channel is LinkedIn, compress to ~120 words (LinkedIn connection note limit):
- Drop the subject line
- Keep the warm opener (1 line)
- Keep 2-3 strongest mappings (not all 4)
- Keep the honest caveat if critical (1 line)
- Keep the 20-min ask
- Drop the sign-off links (LinkedIn profile has them)

**Step 5.4 — Why-this-works commentary:**

After drafting, include a short "Why this works" section explaining the choices — this helps the user understand the strategy and adjust if needed. Cover:
- Why the opener works (warm angle)
- Why the mapping works (named projects, quantified)
- Why the caveat works (gets ahead of gaps)
- Why the ask works (low friction, specific)

---

### Phase 6: Write Findings to Notion (batch mode, or single-job with a page_id)

**Goal:** Persist the full reachout section under a `## Reachout` header on the job's Notion page so it's a permanent record alongside the evaluation report.

**Step 6.1 — Check for an existing Reachout section:**

```bash
python3 skills/job-reachout/scripts/reachout_writer.py has-reachout --page-id {page_id}
```

Returns `{"has_reachout": true/false}`. If `true`, **skip** — do not overwrite. Re-runs produce a new dated section (the script always appends, never deletes), but within a single batch run you should skip to avoid duplicates.

**Step 6.2 — Build the markdown body:**

Write the reachout findings to a temp file in this exact format (this is the body — the script prepends the `## Reachout` header and date automatically):

```markdown
### Team
- **Hiring manager:** [Name] ([Title]) — [how they're connected: posted the role / CTO / etc.]
- **Company stage:** [funding stage, team size]
- **Key peers:** [Name] ([role]), [Name] ([role])

### Fit mapping
- **[Company thesis item 1]** → [User project 1]: [1-sentence how it maps, with metric]
- **[Company thesis item 2]** → [User project 2]: [1-sentence how it maps, with metric]
- **[Company thesis item 3]** → [User project 3]: [1-sentence how it maps, with metric]

### Qualification gaps
- [Honest caveat, or "None — profile matches JD requirements"]

### Recommended contacts
1. **[Name]** — [Role] — [channel: email address or LinkedIn URL]
2. **[Name]** — [Role] — [channel]
3. **[Name]** — [Role] — [channel]

### Draft message
**Subject:** [subject line]

[full message body — the same draft shown in chat, so the user can copy-paste from Notion too]

### Why this works
- [reason 1]
- [reason 2]
- [reason 3]
```

Save to `/tmp/reachout_{page_id}.md`.

**Step 6.3 — Write to Notion:**

```bash
python3 skills/job-reachout/scripts/reachout_writer.py write --page-id {page_id} --report-file /tmp/reachout_{page_id}.md
```

This converts the markdown to Notion blocks (heading_3, bulleted lists, paragraphs) and appends them to the page. The script prepends a `## Reachout` heading_2 and a `*Drafted: YYYY-MM-DD*` date line.

**Step 6.4 — Confirm and move to next job:**

Verify the write returned `{"success": true}`. Show the user a one-line confirmation:

```
✓ [Company] — reachout written to Notion (contact: [Name], channel: [email/LinkedIn])
```

Then immediately proceed to the next job in the batch. Do NOT wait for the user to send the message — sending is manual and happens after the batch completes.

## Output Format

### Single-job mode

Present in chat AND write to Notion (if page_id known):

1. **Team analysis** — who posted the role, hiring manager, team size/stage, peers
2. **Why this is a good fit** — mapping table (company thesis → user's work), honest gaps
3. **Recommended contacts** — ranked table with channel
4. **Draft message** — subject + body + send instructions
5. **Why this works** — 3-4 strategic bullets

### Batch mode

For each job, show in chat a **compact summary** (not the full draft — that goes to Notion):

```
[1/17] Patronus AI — MTS Research Scientist
  Hiring manager: Rebecca Qian (CTO, posted the role)
  Top contact: rebecca@patronus.ai / linkedin.com/in/rebeccaqian
  Fit: EvoData→Generative Simulators, TraceDB→replayable learning envs, LLM-as-Judge→Glider
  ✓ Reachout written to Notion
```

Then at the end of the batch, print a **batch summary**:

```
Reachout batch complete — 17 jobs processed
━━━━━━━━━━━━━━━━━━━━━━━━━━
Reachout drafted + written:  14
Skipped (already had one):   2
Skipped (no URL):            1
Failed:                      0

Next steps — send the messages manually:
1. Patronus AI → Rebecca Qian (rebecca@patronus.ai) — subject: "Applied: MTS RS — EvoSkill/EvoData → Generative Simulators"
2. Relai → Soheil Feizi (sfeizi@cs.umd.edu) — subject: "Applied: AI Research — my EvoSkill work maps to RELAI's regression-in-loop thesis"
...
```

The full draft for each job is in its Notion page under the `## Reachout` header — open the page to copy-paste the message.

## Follow-Up Protocol

If no reply after the first message:
- **Wait 4-5 business days** (professors and founders are busy)
- **Send one gentle nudge** on a different channel (e.g., if emailed, nudge on LinkedIn)
- **Nudge message**: 2 lines — "wanted to make sure this didn't get buried" + restate the one-line hook + same 20-min ask
- **Never send a third message** — if two go unanswered, move on

## Tailoring by Contact Type

### Founder / CTO (early-stage startup)
- They posted the role and said "DM me" → LinkedIn DM is the channel
- Reference their personal research page or recent blog post
- Lead with the technical mapping, not credentials
- Be direct — founders value brevity and signal

### Professor / Faculty founder
- Use their faculty email (most reliable)
- Open with "Hi Professor [Last Name], I'm a [school] [program] student"
- Reference their lab's recent work
- Offer to come to their office (if same university)

### Hiring Manager (mid-size company)
- Find them on LinkedIn, send a connection request with a note
- Reference the team's specific product/feature, not the company broadly
- Focus on how you'd hit the ground running on their current problems

### Peer (recent hire, same role)
- LinkedIn connection request, casual tone
- Lead with genuine interest in their work, NOT a job ask
- Ask about their experience at the company — the referral happens naturally
- Frame: "saw you joined [company] as [role] recently — I'm applying and would love to hear what the team is like"

## Common Mistakes to Avoid

1. **Generic flattery** — "I love your company's mission" is useless. Name a specific piece of their work.
2. **Listing your resume** — the message is a mapping, not a recap. Pick 3-4 projects that map, skip the rest.
3. **Asking for a job** — ask for a 20-min conversation. The job ask is implicit and comes across as higher-agency.
4. **Long messages** — email body should be ~200 words, LinkedIn DM ~120 words. Every sentence must earn its place.
5. **Hiding qualification gaps** — if they asked for a PhD and you have an MS, say so. They'll find out from your application anyway; getting ahead builds trust.
6. **Skipping the research** — a message that could be sent to any company will be ignored. The 30 minutes of research is what makes it land.
7. **Wrong contact** — don't email the CEO if the CTO posted the role. Don't message a peer if the founder is reachable. Rank contacts and pick #1.
8. **No specific ask** — "let me know if you'd like to chat" is weak. "Would 20 min to compare what I built vs. what you're building be useful?" is strong.

## File Structure

```
skills/job-reachout/
├── SKILL.md                        # This file
└── scripts/
    └── reachout_writer.py          # Notion I/O: query candidates, check existing, append section
```

The skill also uses the shared Notion scripts at `scripts/notion/`:
- `notion_client.py` — HTTP primitives (used by reachout_writer.py)
- `db_applications.py` — `markdown_to_notion_blocks()` and `append_blocks_to_page()` (imported by reachout_writer.py)
- `page_reader.py` — fetches resume/projects profile data
- `config.py` — loads `NOTION_DB_APPLICATIONS` from `.env`

## Configuration

The statuses that trigger a reachout in batch mode are defined in `reachout_writer.py`:

```python
REACHOUT_STATUSES = ["Evaluated", "Almost Applied"]
```

To also run reachouts for jobs you've already submitted (often the best time — right after applying), add `"Applied"` to this list. To restrict to only one stage, remove the other. The script reads this constant at import time; no other config is needed.

## Related Skills

- **job-apply** — Fill the application form (run this BEFORE reachout, so the message is a signal-boost)
- **job-eval** — Evaluate the offer (run this to decide if reachout is worth the effort)
- **job-cv-tailor** — Generate a tailored CV (the reachout message references the same projects)
- **linkedin-outreach** — Lighter-weight LinkedIn message drafter (use this skill instead for the full research-to-draft pipeline)
- **job-interview-prep** — If the reachout lands a conversation, switch to interview prep

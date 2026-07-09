---
name: job-reachout
description: Research the team behind a job posting or LinkedIn hiring post, classify the contact type (recruiter / hiring manager / peer / founder), and draft a personalized cold email or LinkedIn DM that maps the user's work to the company's public thesis. Use when the user has already applied (or is about to), shares LinkedIn post URLs to reach out on, or wants a warm signal-boost to a decision-maker.
---

# Job Reachout — Team Research + Personalized Cold Message

After a job application is submitted (or when the user shares a hiring LinkedIn post), a well-researched cold message to the right person raises response rates dramatically. This skill researches the team behind a specific job posting or LinkedIn post, classifies who you're messaging, identifies the best contact, and drafts a personalized email or LinkedIn DM that maps the user's actual work to the company's publicly stated thesis.

## When to Activate

- User says "find out who posted this job" or "who should I email about this role"
- User asks to "draft a message for the hiring manager at [company]"
- User says "reach out to [company] people" after applying
- User wants a warm intro / signal-boost on top of a submitted application
- User shares a job URL and asks "who do I contact?"
- User shares one or more **LinkedIn post URLs** and wants outreach drafts (hiring posts, recruiter posts, founder "we're hiring" posts)
- User says "run reachout for all my evaluated jobs" or "draft reachouts for everything in Almost Applied" → **batch mode** (Phase 0 queries Notion, loops Phase 1–6 per job, writes each to Notion)

## Prerequisites

- **One of:** job posting URL, company + role name, or LinkedIn post URL(s) — required to identify the team (single-job / LinkedIn-post mode). In batch mode, URLs come from Notion.
- **User's profile data** loaded fresh:
  - `Notion (fetch via `python3 scripts/notion/page_reader.py resume`)` — experience, education, skills, projects
  - `Notion (fetch via `python3 scripts/notion/page_reader.py projects`)` — detailed project descriptions for matching
- Optional but high-value: the user has already applied (so the message is a signal-boost, not a substitute)
- `NOTION_TOKEN` environment variable set — for fetching profile data; also required for Notion write in batch mode
- **Notion write is optional** — if the user says "don't upload to Notion" / "just create a file", skip Phase 6 and write a local markdown file instead (see Phase 6.5)

## Non-Negotiables

1. **NEVER draft a generic message** — every message must reference a specific, verifiable piece of the company's public work (a blog post, paper, product launch, LinkedIn post, or research area)
2. **NEVER invent contact info** — only use emails/LinkedIn URLs found via search, published in the post, or **inferred via `infer_email.py` from Companies→Connections referral patterns**. Always flag inferred emails as "try this, may bounce". Never hand-wave `firstname@company.com` when referral emails exist to learn from.
3. **Always classify the contact type BEFORE drafting** — Recruiter vs Hiring Manager vs Peer vs Founder/CTO vs Interviewer changes the message framework (see Phase 4.0). Wrong framework = ignored message.
4. **Always identify the hiring manager / decision-maker** — even when the poster is a recruiter, find the CTO/team lead as a backup contact. Founders/CTOs at small startups are usually the hiring manager.
5. **Always infer email for the primary reachout target** — after picking who to message (Phase 4.1), run `infer_email.py` (Phase 4.4) unless a verified email is already known (faculty page, published in post, or already in Connections). Put the top candidate + confidence in Recommended contacts.
6. **Always read the user's profile fresh** — never rely on cached/remembered project descriptions
7. **Always map user's work → company's thesis with named projects on both sides** — "my EvoSkill maps to your Generative Simulators" beats "I have relevant experience"
8. **Be honest about qualification gaps** — if the user doesn't meet a hard requirement (PhD, years of experience, citizenship, location), get ahead of it in the message rather than hiding it
9. **One concrete ask** — always end with a specific, low-friction request. Ask type depends on contact: recruiter → "happy to share CV"; HM/founder → "20-min chat to compare what I built vs. what you're building"; peer → soft topic ask, NOT a job ask
10. **Write findings back to Notion in batch mode** — unless the user explicitly opts out. Full reachout section goes under a `## Reachout` header. Chat shows the draft for copy-paste; Notion is the persistent record. If opted out, write a local markdown file (Phase 6.5).
11. **NEVER overwrite an existing Reachout section** — if a page already has one, skip it (re-runs produce a new dated section, preserving history). Always check before writing.
12. **SHORT MESSAGES ONLY — this is the #1 reason cold messages get ignored.** Hard limits: email body ≤120 words, LinkedIn DM ≤80 words, connection request note ≤300 characters. For HM/founder messages: pick exactly **2 projects** — each gets **one bullet line**: bold hyperlinked project name + the company concept it maps to + one headline metric. For recruiter messages: skip the 2-bullet mapping; use fit → proof → CTA instead (see Phase 5.2b). No sub-bullets, no expansion, no "happy to come to your office / jump on a call / send a demo" menu.
13. **ALWAYS hyperlink the project name** — if the project has a public link (arXiv paper, GitHub repo, Medium write-up), the project name in the message MUST be a clickable hyperlink. Find the link in Step 3.2.5. Format in markdown: `**[ROMA](https://arxiv.org/...)**`. If no public link exists, leave the name bold-only (`**ROMA**`).
14. **Writing hygiene (from high-response LinkedIn outreach)** — plain simple English; no flattery ("I love your company"); no desperation ("I would be honored"); no emojis; never share a phone number; conversational tone, not a cover letter; one ask only.

## The Process

The skill runs in three modes:
- **Single-job mode** — user gives a job URL or company name. Run Phases 1–5, then Phase 6 if a Notion `page_id` is known (or Phase 6.5 if Notion opted out).
- **LinkedIn-post mode** — user gives one or more LinkedIn post URLs (often in a file like `linkedin.md`). For each post: research the poster + company (Phase 1.0), then Phases 2–5. Default output is a local markdown file (Phase 6.5) unless the user asks to write to Notion.
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

### Phase 1.0: Research LinkedIn Posts (LinkedIn-post mode)

**Goal:** When the input is LinkedIn post URL(s), extract poster + role + company before the normal team research.

**Step 1.0.1 — Fetch each post:**

LinkedIn often blocks plain `WebFetch`. Prefer (in order):
1. Chrome DevTools MCP (`navigate_page` → `take_snapshot`) when available
2. `WebSearch` on the poster name + role keywords from the URL slug
3. `WebFetch` as a fallback

Extract from each post:
- **Who posted**: name, title, company (or agency, e.g. SuperSourcing)
- **Post type**: job posting / company hiring blast / thought leadership / product launch / milestone
- **Role details**: title, location, YOE, compensation signals, must-have skills
- **CTA they invited**: "DM me", "apply here", email address in the post

**Step 1.0.2 — Classify the poster immediately** (feeds Phase 4.0):

| Signal in title/post | Likely type |
|---|---|
| Talent / TA / Recruiter / Leadership Hiring / Sourcer | **Recruiter** |
| CTO / Founder / Head of X / Eng Manager posting "we're hiring" | **Hiring Manager / Founder** |
| Same role title as the opening, recent join | **Peer** |
| Agency domain email (e.g. `@supersourcing.com`) | **Recruiter** (client company may be unnamed — flag it) |

**Step 1.0.3 — Resolve the real company:**

If the poster is an agency recruiter and the company is unnamed, note that in Flags and keep the message recruiter-framed (fit → proof → CV CTA). Do not invent a company thesis.

If the poster is talent at a named company (e.g. Nikki at ExaCare), continue with Phase 1–2 on that company and still find the CTO/HM as backup.

**Step 1.0.4 — Adapt research to post type:**

| Post Type | Research focus |
|---|---|
| **Job posting / hiring blast** | Role requirements + company thesis + HM/CTO backup |
| **Company news/milestone** | Growth area they named → map user's work there |
| **Thought leadership** | Their specific claim → related experience (peer/HM tone) |
| **Product launch** | Problem the product solves → user's closest project |

Then continue into Phase 1 (team) / Phase 2 (thesis) as usual.

---

### Phase 1: Identify the Team Behind the Role

**Goal:** Find out which team posted the listing, who the hiring manager is, and who the research/engineering leads are.

**Step 1.1 — Pull the job description and extract team signals:**

If the user gives a URL, fetch it. Read the JD for:
- Team name (e.g., "Research team", "AI agents team")
- Who the role reports to (e.g., "meets weekly with the CTO" = CTO is hiring manager)
- Research areas / tech keywords (e.g., "scalable oversight", "RL environments", "continual learning")
- Company stage and size (early-stage startup = founder is hiring manager; big company = need team lead)
- Location / remote / hybrid constraints (flag mismatches with user's location early)

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

| Company concept | User's project | How it maps | Link |
|---|---|---|---|
| (from their blog/paper) | (user's project name) | (1 sentence on the technical mapping) | (arXiv/GitHub/Medium URL, or —) |

Rules:
- Only include mappings that are **technically precise** — "my RAG agent is like your agent" is useless; "my TraceDB stores past traces for cross-iteration recall, which is your 'replayable learning environments'" is good
- Pick exactly **2 mappings** for the message (the strongest). Build 3-4 in the table for analysis, but only the top 2 go into the draft — see Phase 5
- Name projects on **both sides** — "my EvoSkill → your Generative Simulators"
- Quantify the user's work (metrics, SOTA results, % improvements)
- Populate the **Link** column via Step 3.2.5

**Step 3.2.5 — Find each project's public link (REQUIRED):**

For every project that might appear in the message, find its public URL. This is non-negotiable — hyperlinked project names make the message verifiable and credible in one click.

Search in this order and pick the FIRST hit:

1. **The user's GitHub repos** — check `https://api.github.com/users/{github_username}/repos?per_page=100` for a repo matching the project name (case-insensitive). Use `{repo.html_url}`.
2. **arXiv** — run `web_search_exa query: "{project_name}" arxiv {user_name}` — if the user co-authored a paper, use `https://arxiv.org/abs/{id}`.
3. **The official/org GitHub** — run `web_search_exa query: "{project_name}" github {org_name}` (e.g. "ROMA github sentient-agi") — if the project lives in an org repo the user contributed to, use that.
4. **Medium / personal blog** — run `web_search_exa query: "site:{user_medium} {project_name}"` — if there's a project-specific write-up, use that URL.
5. **Google Scholar** — run `web_search_exa query: "{user_name}" google scholar` — save the Scholar profile URL; use it as the fallback link for any published project that has no per-project URL.

If none of the above yields a project-specific URL, leave the Link column as `—` and the name will be bold-only (not hyperlinked) in the message.

**Known link inventory for the current profile (verify before reuse, links may change):**

| Project | Link | Type |
|---|---|---|
| ROMA | https://arxiv.org/abs/2602.01848 | arXiv paper |
| EvoSkill | https://arxiv.org/abs/2603.02766 | arXiv paper |
| SERA | https://github.com/khetansarvesh/SERA | GitHub repo |
| Deep Research (Strategy) | https://khetansarvesh.medium.com/search-deep-research-agents-a7b6f3ae6d32 | Medium article |
| Google Scholar (all pubs) | https://scholar.google.com/citations?user=MSW5-VMAAAAJ | fallback |

Re-run Step 3.2.5 only if the profile changes or a new project appears; otherwise this inventory can be reused across jobs in a batch.

**Step 3.3 — Identify qualification gaps:**

Compare the user's profile to the JD's hard requirements. Common gaps:
- PhD required, user has MS
- X+ years experience, user has fewer
- US citizenship required, user is on visa
- Location mismatch (role is NY/Toronto/onsite; user is elsewhere / remote-only)
- Specific domain (optical, healthcare, etc.), user has different domain
- Agency post with unnamed company / comp currency mismatch

**Get ahead of these in the message** — don't hide them. Frame as "honest caveat: the listing asks for X, I have Y — but the building experience maps directly." Put material gaps in the summary **Flags** column when writing local markdown (Phase 6.5).

### Phase 4: Classify Contact Type, Then Pick Channel

**Goal:** Classify who you're messaging (this changes the draft framework), then pick the single best person and channel.

**Step 4.0 — Classify contact type (REQUIRED before drafting):**

| Type | Who | Message focus | Ask |
|---|---|---|---|
| **Recruiter** | Talent acquisition, sourcing, agency | Fit criteria → screening answers → CTA | Share CV / confirm alignment |
| **Hiring Manager** | Team lead who's hiring | Specific challenge → quantified achievement → ask | 20-min chat on the challenge |
| **Founder / CTO** | Early-stage decision-maker | Named thesis mapping (2 project bullets) → caveat → ask | 20-min compare-builds chat |
| **Peer** | Someone in a similar role on the team | Genuine interest → shared problem → soft ask | Take on a topic — **NOT a job ask** |
| **Interviewer** | Someone who will interview you (date known) | Research signal → connection → looking forward | Looking forward to [date] |

**Key rules:**
- **Peer:** Do NOT ask for a job. The referral happens naturally if the conversation flows. Lead with genuine interest in their work.
- **Interviewer:** Keep it light. Goal is they know you prepared, not that you're desperate.
- **Recruiter:** Answer screening questions before they ask (YOE, location/availability, degree, stack). Skip the 2-bullet thesis mapping unless they also own the technical hire.
- **Always suggest 1–2 backup contacts** with justification (e.g. recruiter primary → CTO backup if no reply).

**Step 4.1 — Rank contacts:**

| Priority | Who | When to pick them |
|---|---|---|
| 1 | Founder/CTO who posted the role | Early-stage startup (<50 people), they said "DM me", role reports to them |
| 2 | Founder/CTO (even if didn't post) | Small company where they're the hiring manager |
| 3 | Team lead / Head of Research | Mid-size company, founder is too senior |
| 4 | Recruiter who posted / owns the req | They invited DMs or listed an email — use as primary *channel*, still find HM/CTO as backup |
| 5 | Recent peer hire (same role) | Large company, need a referral inward |
| 6 | CEO (operations) | Only if founder/CTO unreachable and CEO posted the role |

**Step 4.2 — Find their contact channel:**

Preferred order:
1. **Faculty email** (if they're a professor) — `cs.umd.edu/~sfeizi/` lists `sfeizi@cs.umd.edu`. Professors always read their faculty email.
2. **Email they published in the post** (recruiters often do this) — use it; they invited that channel
3. **Email already in Connections** for that person — if they're linked on the company's Referral relation and have an Email field, use it (verified)
4. **Inferred email via `infer_email.py`** (Phase 4.4) — required for the primary target when 1–3 are missing
5. **LinkedIn DM** — if they explicitly said "DM me" in a post, this is a strong channel even when email is also inferred (send both if useful)
6. **LinkedIn connection request** — for peers and when no email can be inferred (note ≤300 chars)

**Step 4.3 — Check for warm-intro angles:**

Look for any shared connection that makes the cold message warmer:
- Same university (professor at user's school = "Hi Professor [Name], I'm a [school] ML MS student")
- Same previous employer
- Same research community (published in same venues)
- Same hometown/region (use sparingly, only if genuinely useful)

These go in the **first line** of the message — they're the opener that gets it read.

**Step 4.4 — Infer email for the primary reachout target (REQUIRED):**

Once Phase 4.1 has named the person to message, resolve their email before drafting.

**Skip inference only if** you already have a verified address from Step 4.2 items 1–3.

**Otherwise run:**

```bash
python3 skills/job-reachout/scripts/infer_email.py \
  --company "{Company Name}" \
  --name "{First Last}" \
  --json
```

Optional: `--domain company.com` when the company has no work emails on Referral (only gmail / empty) but you know the corporate domain from their website.

**How to use the output:**
1. Read `learned.domain` + `learned.pattern` + `learned.pattern_confidence`
2. Take `inferred[0]` as the **primary email** if confidence is `high` or `medium`
3. If top confidence is `low` only, still list it but prefer LinkedIn DM as the send channel and mark email as backup
4. List `inferred[1]` (and optionally `[2]`) as fallbacks in Recommended contacts
5. Always label inferred addresses: **"try this, may bounce"**
6. If `inferred` is empty (no domain), say so explicitly and fall back to LinkedIn — do **not** invent `@company.com` by hand unless you pass `--domain` from a real careers/about page

**Also check warm referrals at the same time:** if the company has Referral connections, note the top 1–2 people (name + relation) under Recommended contacts as alternate warm paths — even when you're emailing the HM/CTO cold.

Example Recommended contacts block after inference:

```markdown
### Recommended contacts
1. **Ben Willox** — Co-Founder & CTO — email: `ben@exacare.com` (inferred, medium, pattern=`first` from referrals) — try this, may bounce
   - Fallbacks: `ben.willox@exacare.com`, `bwillox@exacare.com`
   - LinkedIn: https://www.linkedin.com/in/benjamin-willox
2. **Nikki Padda** — Talent — LinkedIn DM (posted the role)
3. **Warm referrals on file:** [Name] (BITS) — phone/email from Connections
```

### Phase 5: Draft the Message

**Goal:** Write a concise, personalized message using the framework that matches the contact type from Phase 4.0.

**Step 5.1 — Subject line (for email only):**

Format: `[Status]: [Role title] — [Hook]`

Examples:
- `Applied: MTS Research Scientist — EvoSkill/EvoData → Generative Simulators overlap`
- `Applied: AI Research / Engineering — Sarvesh Khetan (UMD ML MS); my EvoSkill work maps to RELAI's regression-in-loop thesis`

Rules:
- Start with "Applied:" if the user already applied — signals this is a follow-up, not cold spam
- Name the exact role so they can route it
- Include the hook (the named mapping) — that's what gets an open
- Avoid generic subjects like "Following up on my application" or "Excited about [company]"
- Skip subject entirely for LinkedIn DMs / connection notes

**Step 5.2 — Message body by contact type (STAY SHORT — see Non-Negotiable #12):**

Hard limits always apply: email ≤120 words, LinkedIn DM ≤80 words, connection note ≤300 chars.

#### 5.2a — Founder / CTO / Hiring Manager (default thesis-mapping framework)

**Paragraph 1 — Warm opener + status (1-2 lines, ≤30 words):**
- Lead with the warm angle (shared university, "I saw your post about X")
- State that you applied + name the role in the same line (skip "applied" if you haven't yet)

**Paragraph 2 — The mapping (THE CORE, 2 bullets):**
- Exactly **2 bullets**, one per project. Not inline text — actual bullet points (`- `).
- Each bullet is **one line**: `**[Project](link)** → [company concept]: [headline metric with a number]`
- The project name MUST be bold AND a hyperlink when a link exists (per Step 3.2.5). Format: `**[ROMA](https://arxiv.org/abs/2602.01848)**`.
- If no public link exists for the project, use bold-only: `**ProjectName**`.
- The arrow (`→`) separates the project from the company concept it maps to. The colon separates concept from metric.
- Example bullet: `**[ROMA](https://arxiv.org/abs/2602.01848)** → your hierarchical reasoning work: 10% SOTA on SEAL-0.`
- If you can't fit the impact in one bullet line, the project isn't the right pick. Choose a different one.

**Paragraph 3 — Honest caveat (1 line, only if there's a real gap):**
- "Honest caveat: the role asks for X, I have Y — but the building experience transfers directly."
- Skip entirely if there's no material gap. Don't pad.

**Paragraph 4 — One specific ask (1 line, ≤20 words):**
- HM: "Would love to hear how your team is approaching [specific challenge]."
- Founder/CTO: "Would 20 min to compare what I built vs. what you're building be useful?"
- One sentence. No friction-removal menu.

**Sign-off (email only, 2 lines):**
- Name + degree/school on one line
- GitHub OR LinkedIn on one line (not both — pick the stronger for this contact)

#### 5.2b — Recruiter (fit → proof → CTA — NO 2-bullet thesis dump)

Recruiters screen; they don't debate research theses. Answer their filters up front.

1. **Fit (1 line):** Role + most relevant experience + availability/location
2. **Proof (1–2 lines):** Pre-answer screening — YOE, degree, stack, one headline metric. Optionally one hyperlinked project if it proves the filter.
3. **CTA (1 line):** "Happy to share my CV if this aligns with what you're looking for."
4. **Caveat (optional, 1 line):** Only for hard gaps (YOE, location, visa) — same honest-caveat framing

Example shape:
> Hi Nikki — saw your post on Senior MLE roles at ExaCare. I'm an AI researcher at Sentient (UMD ML MS, June 2026) with 3+ YOE building production LLM agents.
>
> Recent work: **[ROMA](https://arxiv.org/abs/2602.01848)** (10% SOTA hierarchical agents) and **[SERA](https://github.com/khetansarvesh/SERA)** (50% latency drop across 40+ tools).
>
> Honest caveat: SF-based — roles list NY/Toronto/Vancouver. Happy to share my CV if you're still open on location.

#### 5.2c — Peer (interest → shared problem → soft ask — NO job ask)

1. **Interest:** Genuine reference to their work — blog, talk, OSS, paper, or a specific thing they shipped
2. **Connection:** Something you're doing in the same space (not a pitch)
3. **CTA:** "I've been working on similar problems at [company] — would love your take on [topic]."

#### 5.2d — Interviewer (pre-interview, date known)

1. **Research:** One specific thing about their work/background
2. **Context:** Light connection to your experience
3. **CTA:** "Looking forward to our conversation on [date]."

**Step 5.3 — LinkedIn DM / connection-note compression:**

- Drop the subject line
- Keep the contact-type framework, but compress to ≤80 words (DM) or ≤300 chars (connection note)
- Connection notes: often only opener + one proof line + soft ask — drop second project if needed
- Name only at the end (no sign-off links — LinkedIn profile has them)

**Step 5.4 — Why-this-works commentary:**

After drafting, include a short "Why this works" section explaining the choices — this helps the user understand the strategy and adjust if needed. Cover:
- Why this contact type / framework was chosen
- Why the opener works (warm angle / post reference)
- Why the mapping or proof works (named projects, quantified, or screening answers)
- Why the caveat works (gets ahead of gaps) — if present
- Why the ask works (low friction, type-appropriate)
- Why this email / channel (inferred pattern + confidence, or verified source; LinkedIn backup)
- Backup contacts if primary goes quiet

**Step 5.5 — What NOT to write (anti-patterns):**

BAD: "Hi! I came across your post and was really impressed by SmarterDx's work in healthcare AI. I'm a passionate ML engineer with 3+ years of experience in NLP, RAG, LLMs, and deep learning..."

GOOD: "Hi [Name] — saw your post about the Staff ML Engineer role at SmarterDx. I've been building production AI agents at Sentient, most recently a search agent that beat SOTA by 10% on hierarchical tasks."

Never: flattery, desperation, emoji, phone number, resume dump, multiple asks, buzzword soup.

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
1. **[Name]** — [Role] — [channel]
   - Email: `[inferred or verified]` ([confidence], pattern=`…` from referrals) — try this, may bounce
   - Fallbacks: `…`, `…`
   - LinkedIn: [url]
2. **[Name]** — [Role] — [channel]
3. **Warm referrals on file:** [Name] ([relation]) — from Companies→Connections

### Inferred email
- **Target:** [Name]
- **Primary:** `email@company.com` ([high|medium|low], pattern=`first` / `first.last` / …)
- **Fallbacks:** `…`
- **Evidence:** learned from N referral work emails on domain `company.com`
- **Note:** try this, may bounce — skip this block only if email was verified (faculty / post / Connections)

### Draft message
**To:** `[primary email]` (or LinkedIn DM if inference empty / low-only)
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

### Phase 6.5: Write to Local Markdown (LinkedIn-post mode, or Notion opted out)

**Goal:** Persist drafts to a local file when the user says "don't upload to Notion" / "just create a file", or when running LinkedIn-post mode without a Notion `page_id`.

**When to use:**
- User explicitly opts out of Notion
- Input was LinkedIn post URL(s) / a file like `linkedin.md` and no job Notion pages exist
- Notion write failed and the user still needs the drafts

**Default filename:** `linkedin_outreach_messages.md` (or a name the user specifies). Do **not** overwrite `linkedin.md` if that file only holds source URLs.

**Required structure:**

```markdown
# LinkedIn Outreach Messages

Generated: [date]

## Summary

The summary table must be comprehensive — ALL context (post link, location, who to message, why I'm a fit, flags) so the user can act from the table alone.

| # | Company | Role | Location | Person to Message | Post | Why I'm a Fit | Flags |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | [[Company]](#1-company--role) | [Role] | [City/Remote] | [Name, Title] (+ backup if any) | [post](url) | [specific match — projects/metrics] | [concerns or —] |

The Company column links to the section below (anchor: `#1-company--role`, lowercase, hyphens).

---

## 1. [Company] — [Role]

### Team
- ...

### Fit mapping
- ...

### Qualification gaps
- ...

### Recommended contacts
1. ...

### Inferred email
- **Target:** [Name]
- **Primary:** `email@company.com` ([confidence], pattern=`…`) — try this, may bounce
- **Fallbacks:** …

### Draft — Email to [Name] / LinkedIn DM

> [full message]

**Send via:** email to `…` (inferred) and/or LinkedIn DM

### Why this works
- ...
```

Rules:
- If a post should be skipped (wrong location, unrelated role, hard gap the user won't accept), still include it in the summary table with the reason in **Flags**, and write `**Skipped** — [reason]` in the message section (or draft with a loud caveat if the user may still want it).
- Include a short **Send order** section at the bottom when there are multiple posts.
- Still show drafts in chat for copy-paste; the file is the persistent record when Notion is skipped.

---

## Output Format

### Single-job mode

Present in chat AND write to Notion (if page_id known and not opted out) OR local markdown (Phase 6.5):

1. **Contact type** — Recruiter / HM / Founder / Peer / Interviewer (drives framework)
2. **Team analysis** — who posted the role, hiring manager, team size/stage, peers
3. **Why this is a good fit** — mapping table (company thesis → user's work), honest gaps
4. **Recommended contacts** — ranked table with channel + backups + warm referrals on file
5. **Inferred email** — primary + fallbacks from `infer_email.py` (or verified source)
6. **Draft message** — subject (if email) + body + **send via** (email and/or LinkedIn)
7. **Why this works** — 3-4 strategic bullets

### LinkedIn-post mode

Same content as single-job, but batched into one local markdown file with a summary table (Phase 6.5). Chat shows a compact per-post summary plus the draft.

### Batch mode

For each job, show in chat a **compact summary** (not the full draft — that goes to Notion):

```
[1/17] Patronus AI — MTS Research Scientist
  Contact type: Founder/CTO
  Hiring manager: Rebecca Qian (CTO, posted the role)
  Top contact: rebecca@patronus.ai (inferred, high, pattern=first) / linkedin.com/in/rebeccaqian
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
- Lead with the technical mapping (Phase 5.2a), not credentials
- Be direct — founders value brevity and signal

### Professor / Faculty founder
- Use their faculty email (most reliable)
- Open with "Hi Professor [Last Name], I'm a [school] [program] student"
- Reference their lab's recent work
- Offer to come to their office (if same university)

### Hiring Manager (mid-size company)
- Find them on LinkedIn; connection note ≤300 chars or InMail ≤80 words
- Reference the team's specific product/feature, not the company broadly
- Hook = specific challenge; proof = one quantified achievement; ask = how they're approaching it

### Recruiter / Talent / Agency
- Use Phase 5.2b (fit → proof → CV CTA) — do not dump a 2-bullet research thesis
- Pre-answer YOE, location, start date, degree, stack
- If they listed an email in the post, use that channel
- Always find HM/CTO as backup; if agency and company is unnamed, flag it and keep the ask at CV-share / "right level"

### Peer (recent hire, same role)
- LinkedIn connection request, casual tone — Phase 5.2c
- Lead with genuine interest in their work, NOT a job ask
- Ask about their experience at the company — the referral happens naturally
- Frame: "saw you joined [company] as [role] recently — I've been working on [related problem] and would love your take on [topic]"

### Interviewer (date known)
- Phase 5.2d only — light research signal, no pitch, no ask for a job

## Common Mistakes to Avoid

1. **Wrong contact-type framework** — messaging a recruiter with a founder thesis dump (or a peer with a job ask) gets ignored. Classify first (Phase 4.0).
2. **Generic flattery** — "I love your company's mission" is useless. Name a specific piece of their work or their actual post.
3. **Listing your resume** — the message is a mapping (or screening answers), not a recap. For HM/founder: pick **2 projects**. For recruiter: one proof line. Listing 3-4 projects signals you can't prioritize.
4. **Asking for a job (to HM/founder/peer)** — ask for a 20-min conversation (or a peer's take). The job ask is implicit. Exception: recruiters — CV CTA is correct.
5. **Long messages** — email ≤120 words, LinkedIn DM ≤80 words, connection note ≤300 chars. Hard limits. A cold message that takes >30 seconds to read gets ignored.
6. **Multi-line project descriptions** — each of your 2 projects gets ONE bullet line: bold hyperlinked name + company concept + headline metric. If you need a second line, rewrite or pick a different project.
7. **Unlinked project names** — if a project has a public arXiv/GitHub/Medium link, the name MUST be a hyperlink (`**[ROMA](url)**`). Run Step 3.2.5 before drafting.
8. **Hiding qualification gaps** — if they asked for a PhD / 10+ YOE / a city you're not in, say so in one line. They'll find out anyway; getting ahead builds trust.
9. **Skipping the research** — a message that could be sent to any company will be ignored. The research is what makes it land. For LinkedIn posts, reference the actual post content.
10. **Wrong contact** — don't email the CEO if the CTO posted the role. Don't stop at the recruiter if the founder is reachable as backup. Rank contacts and pick #1 + backups.
11. **Skipping email inference** — once you know who to message, run `infer_email.py` (Phase 4.4). Don't guess `@company.com` by hand when referrals can teach the pattern, and don't omit the Inferred email section.
12. **No specific ask** — "let me know if you'd like to chat" is weak. Type-appropriate asks only (Phase 4.0 / 5.2).
13. **Flattery, desperation, emojis, phone numbers** — kill response rate. Keep plain, specific, human.

## File Structure

```
skills/job-reachout/
├── SKILL.md                        # This file
└── scripts/
    ├── reachout_writer.py          # Notion I/O: query candidates, check existing, append section
    └── infer_email.py              # Infer target emails from Companies→Connections referral patterns
```

### `infer_email.py` — guess emails from referral patterns

**Required in Phase 4.4** for every primary reachout target without a verified email.

When you know who to message (e.g. a CTO found via LinkedIn) but not their email, learn the company's format from Connections already linked on that company's **Referral** relation:

```bash
# Show learned domain + pattern from referrals
python3 skills/job-reachout/scripts/infer_email.py --company "Google"

# Infer candidates for the reachout target (always use --json in agent runs)
python3 skills/job-reachout/scripts/infer_email.py --company "Prior Labs" --name "Jane Doe" --json
python3 skills/job-reachout/scripts/infer_email.py --company "Kipo AI" --name "Alex Kim" --domain kipo.ai --json
```

Behavior:
- Loads Companies DB → `Referral` relation → Connections with emails
- Ignores personal domains (gmail, etc.) and off-domain work emails that don't match the company name
- Votes on local-part pattern (`first`, `first.last`, `flast`, `firstlast`, …)
- Emits ranked candidates flagged **"try this, may bounce"**
- Use `--domain` when referrals only have personal emails or the company row is missing work domains

**Agent rules:**
1. Run this after Phase 4.1 names the person — before Phase 5 draft
2. Prefer `inferred[0]` when confidence is high/medium; if only low, lead with LinkedIn DM and list email as backup
3. Put primary + fallbacks + evidence in the **Inferred email** output section
4. Never skip silently when the company exists in Companies DB — if inference returns empty, say "no referral work emails / no domain" and use LinkedIn
5. Also surface warm Referral connections as alternate contacts when present

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
- **linkedin-outreach** — Absorbed into this skill (contact-type frameworks, LinkedIn-post mode, local markdown output, writing hygiene). Prefer **job-reachout** for all hiring outreach; keep `linkedin-outreach` only as a thin pointer if referenced elsewhere.
- **job-interview-prep** — If the reachout lands a conversation, switch to interview prep

---
name: job-interview-prep
description: Company-specific interview preparation — process intel, STAR+R story mapping, technical checklists, and company signals.
---

# Interview Preparation

Generate a comprehensive, company-specific interview preparation guide. Researches the interview process, maps your experience to likely questions, and identifies gaps.

## Setup

**Requirements**
- Python 3.10+
- Install the Notion integration package:
  ```bash
  python -m pip install sarvesh-ai-notion-interface
  ```
- Notion access via environment variables or a `.env` file in your working directory:
  - `NOTION_TOKEN` — Notion integration token (required)
  - Page IDs as needed: `NOTION_PAGE_RESUME`, `NOTION_PAGE_PROJECTS`, `NOTION_PAGE_PARENT`

The Notion integration package (`sarvesh-ai-notion-interface`) is published on PyPI and contains all database helpers for job tracking.

## When to Activate

- User says "prepare me for an interview at [company]"
- User has an upcoming interview and wants to prep
- User asks for STAR stories for a specific role
- User wants to know what to expect in interviews at a company

## Prerequisites

- `Notion (fetch via `python3 -m sarvesh_ai_notion_interface.page_reader resume`)` — work experience and skills
- `Notion (fetch via `python3 -m sarvesh_ai_notion_interface.page_reader projects`)` — project summaries and answer snippets

## Non-Negotiables

1. **Never fabricate stories** — every STAR response must trace to real experience in the user's profile
2. **Always cite sources** for interview process data (Glassdoor, Blind, LeetCode Discuss, etc.)
3. **Flag gaps honestly** — if the user has no matching story for a likely question, say so and suggest how to bridge
4. **Tailor to the specific role** — generic prep is useless. Every question and story must connect to the JD
5. **Label inferred questions** — every question NOT sourced from a real candidate report must be labeled `[inferred from JD]`. Never attribute inferred questions to Glassdoor or Blind.
6. **Never fabricate statistics** — never invent Glassdoor ratings, experience percentages, or interview statistics. If data is unavailable, write "unknown — not enough data"

## Workflow

### Step 1: Gather Context

1. Read `Notion (fetch via `python3 -m sarvesh_ai_notion_interface.page_reader resume`)` and `Notion (fetch via `python3 -m sarvesh_ai_notion_interface.page_reader projects`)`
2. If an evaluation report exists for this company/role, read it for archetype and gap analysis
3. Ask the user for any additional context:
   - Which round is it? (phone screen, technical, behavioral, onsite, final)
   - Do they know who's interviewing them?
   - Any specific topics they're worried about?

### Step 2: Research Interview Process

Use WebSearch to find interview intel. Run these queries:

| Query                                                         | What to extract                                                                                                      |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `"{company}" "{role}" interview questions site:glassdoor.com` | Actual questions asked, difficulty rating, experience rating, process timeline, number of rounds, offer/reject ratio |
| `"{company}" interview process site:teamblind.com`            | Candid process descriptions, recent data points, comp negotiation details, hiring bar                                |
| `"{company}" "{role}" interview site:leetcode.com/discuss`    | Specific coding/technical problems, system design topics, round structure                                            |
| `"{company}" engineering blog`                                | Tech stack, values, what they publish about, technical priorities                                                    |
| `"{company}" interview process {role}`                        | General fallback — fills gaps from above: blog posts, YouTube, prep guides, candidate write-ups                      |

**If the company is small or obscure** and yields few results, broaden: search for the role archetype at similar-stage companies, and note that intel is sparse.

Extract and organize:

**Process Overview:**

| Field                    | Details                                                               |
| ------------------------ | --------------------------------------------------------------------- |
| Rounds                   | (number and types: phone, technical, system design, behavioral, etc.) |
| Timeline                 | (typical days/weeks from first contact to offer)                      |
| Difficulty               | (1-5 based on reported experiences)                                   |
| Positive Experience Rate | (% from Glassdoor if available, or "unknown")                         |
| Known Quirks             | (anything unusual about their process)                                |
| Sources                  | (links to Glassdoor, Blind, etc.)                                     |

If data is insufficient for any field, write "unknown — not enough data" rather than guessing.

### Step 3: Round-by-Round Breakdown

For each interview round:

```markdown
### Round {N}: {Type}

- **Duration:** {X} min
- **Conducted by:** (peer / manager / skip-level / recruiter — if known)
- **What's evaluated:** (coding, system design, behavioral, culture fit)
- **Reported questions:**
  - {question} — [source: Glassdoor 2026-Q1]
  - {question} — [source: Blind]
  - {question} — [inferred from JD]
- **How to prepare:** (1-2 concrete actions)
```

If round structure is unknown, state that and provide the best available intel on what types of rounds to expect based on company size, stage, and role level.

### Step 4: Question Categories

Organize all discovered and inferred questions into 4 categories. For sourced questions, cite: `[source: Glassdoor 2026-Q1]`. For questions inferred from JD analysis, label: `[inferred from JD]`.

**Technical Questions:**

- System design (relevant to role: ML pipelines, agent architectures, RAG systems, etc.)
- Coding (algorithms, data structures, ML implementation)
- Domain-specific (NLP, CV, distributed training, inference optimization — whatever the role requires)
- For each: the question, source, and what a strong answer looks like for THIS candidate (reference specific CV proof points)

**Behavioral Questions:**

- Leadership and teamwork
- Conflict resolution
- Failure and learning
- Decision-making under ambiguity
- For each: the question, source, and which story from your projects maps best

**Role-Specific Questions:**

- Tied directly to JD requirements
- "Tell me about a time you [specific JD requirement]"
- For each: the question, why they're likely asking it (what JD requirement it maps to), and the candidate's best angle

**Red-Flag Questions:**

- Questions about gaps in your profile
- "Why are you leaving your current role?"
- "Why should we hire you over someone with more experience?"
- Read the user's profile to identify what might raise questions. For each: the likely question, why it comes up, and a recommended framing (honest, specific, forward-looking — never defensive)

### Step 5: STAR+R Story Mapping

For each likely question, map a story from the user's experience:

| #   | Question | Best Story    | Fit                 | S   | T   | A   | R   | Reflection |
| --- | -------- | ------------- | ------------------- | --- | --- | --- | --- | ---------- |
| 1   | ...      | [Story Title] | strong/partial/none | ... | ... | ... | ... | ...        |

**Fit ratings:**

- `strong` — story directly answers the question
- `partial` — story is adjacent, needs reframing
- `none` — no existing story (flag as gap)

Fetch detailed project context from Notion for rich STAR stories:

```bash
python3 -m sarvesh_ai_notion_interface.page_reader roma          # Agent architecture, SOTA results
python3 -m sarvesh_ai_notion_interface.page_reader sera          # Scaling agents, systematic experiments
python3 -m sarvesh_ai_notion_interface.page_reader deep-research # Multi-agent systems, evaluation
python3 -m sarvesh_ai_notion_interface.page_reader txt2sql       # Knowledge graphs, team leadership, patent
python3 -m sarvesh_ai_notion_interface.page_reader mroma         # Cost optimization, multimodal design
```

**Reflection is critical.** It separates senior from junior candidates:

- What did you learn?
- What would you do differently?
- How did this change your approach to similar problems?

### Step 6: Gap Analysis

For questions where the user has NO matching story (fit = `none`):

1. Flag the gap explicitly
2. Suggest the closest adjacent experience
3. Propose a bridging narrative ("I haven't done X specifically, but in project Y I faced a similar challenge where...")
4. If the gap is a hard blocker, flag it as a risk area

For each gap, suggest: "You need a story about {topic}. Consider: {specific experience from profile that could become a STAR+R story}."

### Step 7: Technical Prep Checklist

Based on what the company actually tests, not generic advice. Create a prioritized checklist. Max 10 items:

| #   | Topic   | Priority        | Why (evidence)                            | Resources |
| --- | ------- | --------------- | ----------------------------------------- | --------- |
| 1   | (topic) | High/Medium/Low | (reported in interviews / required in JD) | (links)   |

Prioritize by: frequency in reported interviews > JD requirements > general best practices.

### Step 8: Company Signals

**Values they screen for** (with sources):

- What does their careers page emphasize?
- What do interviewers mention in Glassdoor reviews?
- Example: "Stripe screens for 'increase the GDP of the internet'"

**Vocabulary to use:**

- Terms from their engineering blog, product docs, JD
- Company-specific jargon (product names, internal frameworks)
- Example: "Anthropic says 'safety' not 'alignment'"

**Things to avoid:**

- Anti-patterns mentioned in negative reviews
- Topics that are sensitive for the company (recent incidents, controversies)

**Smart questions to ask them:**

- 3-5 questions that demonstrate research and genuine interest
- At least 1 about team/org structure
- At least 1 about technical challenges
- Never ask things easily found on the website
- Tie to recent news or blog posts discovered in Step 2

### Step 9: Output

Write the complete prep guide with this header and structure:

```markdown
# Interview Intel: {Company} — {Role}

**Evaluation Report:** {link to Notion evaluation report if exists, or "N/A"}
**Researched:** {YYYY-MM-DD}
**Sources:** {N} Glassdoor reviews, {N} Blind posts, {N} other

## Process Overview

(table from Step 2)

## Round-by-Round Breakdown

(per round from Step 3)

## Likely Questions

(4 categories from Step 4)

## Story Bank (STAR+R)

(mapped stories table from Step 5)

## Technical Prep Checklist

(prioritized list from Step 7)

## Company Signals

(values, vocabulary, questions to ask from Step 8)

## Gaps & Risk Areas

(flagged gaps with bridging strategies from Step 6)
```

### Step 10: Post-Research Actions

After delivering the report:

1. **Draft gap stories:** Ask the user if they want to draft STAR+R stories for any gaps found in Step 6
2. **Interview timeline:** If the user has a scheduled interview date, note days remaining and suggest a review schedule
3. **Deepen research:** If company research in Step 2 was thin, suggest running the **market-research** skill for deeper company intel (strategy, culture, competitive landscape)

## Related Skills

- **job-eval** — Evaluate the offer before prepping (provides archetype + gap analysis)
- **market-research** — Deep company research if interview intel is sparse
- **job-cv-tailor** — Generate a tailored CV for this specific role
- **job-apply** — Fill the application form

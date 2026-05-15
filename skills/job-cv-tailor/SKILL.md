---
name: job-cv-tailor
description: Generate ATS-optimized, JD-tailored CVs — edits LaTeX resume template with keyword injection, summary rewriting, project selection, and compiles to PDF via pdflatex.
---

# ATS-Optimized CV Tailor (LaTeX)

Generate a tailored CV for a specific job description. Reads your LaTeX resume template, edits it to match the JD (rewrite summary, reorder bullets, select projects, inject keywords), saves a tailored copy, and compiles to PDF locally.

## When to Activate

- User asks to generate a CV or resume for a specific role
- User wants to tailor their resume to a JD
- User says "make a PDF", "generate CV", or "tailor my resume"
- After running **job-eval**, user wants a customized CV for a high-scoring role

## Prerequisites

- `profile/resume.tex` — LaTeX resume template (source of truth — never overwrite this)
- `Notion (fetch via `python3 scripts/notion/page_reader.py resume`)` — structured experience, education, skills data
- `Notion (fetch via `python3 scripts/notion/page_reader.py projects`)` — project summaries
- **pdflatex** installed locally (TeX Live or MacTeX)
  - macOS: `brew install --cask mactex` or `brew install --cask basictex`
  - Lato font: `tlmgr install lato`
- A job description (text, URL, or from a previous evaluation)

## Non-Negotiables

1. **Never invent skills or experience** — only reformulate what actually exists in the profile
2. **Every bullet must trace to real experience** — keyword injection means rephrasing, not fabricating
3. **Single page** — if the tailored version exceeds 1 page, trim content (fewer projects, shorter bullets)
4. **Preserve LaTeX structure** — don't break macros, formatting commands, or section ordering
5. **Never auto-submit** the CV — user reviews the final PDF

## Workflow

### Step 1: Read JD and Profile

1. Get the job description (user pastes text, or use WebFetch on a URL)
2. Read `profile/resume.tex` — the LaTeX template you'll modify
3. Read `Notion (fetch via `python3 scripts/notion/page_reader.py resume`)` and `Notion (fetch via `python3 scripts/notion/page_reader.py projects`)` for full context
4. If an evaluation report exists (from **job-eval**), read it for archetype and keyword analysis

### Step 2: Extract Keywords (15-20)

From the JD, extract:

- **Hard skills:** specific technologies, frameworks, tools, languages
- **Soft skills:** leadership patterns, collaboration styles
- **Domain terms:** industry-specific vocabulary
- **Action verbs:** what the role does (build, deploy, research, optimize, lead)

Rank by frequency and prominence in the JD. The top 5 go in the summary.

### Step 3: Detect Archetype

Classify the role to frame the summary appropriately:

| Archetype         | JD Signals                                           | Summary Emphasis                                               |
| ----------------- | ---------------------------------------------------- | -------------------------------------------------------------- |
| AI/ML Research    | "research", "SOTA", "publications", "benchmarks"     | SOTA results, publications, experiment methodology             |
| LLM/NLP           | "RAG", "agents", "LLM", "prompting", "orchestration" | RAG pipelines, agent orchestration, LLM optimization           |
| ML Platform/MLOps | "pipelines", "serving", "monitoring", "CI/CD"        | Production systems, observability, evals, deployment           |
| Computer Vision   | "vision", "detection", "diffusion", "VLM", "video"   | Detection, generation, VLMs, diffusion models                  |
| Data Science      | "analytics", "experimentation", "modeling", "A/B"    | Business impact, experimentation, stakeholder communication    |
| Applied AI        | "end-to-end", "prototype", "production", "deploy"    | End-to-end delivery, cross-functional, prototype-to-production |

### Step 4: Plan Tailored Content

Before editing any LaTeX, decide what changes to make:

**Professional Summary** (2-4 sentences):

- Inject top 5 JD keywords naturally
- Lead with strongest match point for the detected archetype
- Include one quantified achievement
- Bridge from your background to this specific role

**Technical Skills reorder:**

- Within each category (Languages, Frameworks, Cloud, Dev Tools, IT Constructs), move JD-matching items to the front

**Work Experience bullet reorder:**

- For each job entry, score bullets by JD relevance (0-3)
- Put most relevant bullets first
- Optionally rephrase 1-2 top bullets to incorporate JD vocabulary

**Projects selection:**

- From the 7 project bullets, select top 4-5 most relevant
- Reorder by relevance
- Optionally rephrase to emphasize JD-matching aspects

**Achievements filter** (if needed for space):

- Keep the most relevant 3-4 of 5

### Step 5: Keyword Injection Rules (Ethical)

**ALLOWED:**

- Reformulate existing experience using JD vocabulary
  - "LLM workflows with retrieval" → "RAG pipeline design and LLM orchestration"
- Reframe true skills with JD terminology
  - "observability, evals, error handling" → "MLOps: observability, evals, cost monitoring"
- Elevate stakeholder context
  - "collaborated with team" → "stakeholder management across engineering and business"

**FORBIDDEN:**

- Adding skills the user doesn't have
- Inventing metrics or experience
- Claiming expertise in unused technologies

**Validation:** Every keyword must trace back to `Notion (fetch via `python3 scripts/notion/page_reader.py resume`)` or `Notion (fetch via `python3 scripts/notion/page_reader.py projects`)`.

### Step 6: Edit resume.tex

Read `profile/resume.tex` and make modifications using the Edit tool:

**6a. Add Professional Summary**

Insert a new section after the header and before Education:

```latex
%-----------PROFESSIONAL SUMMARY-----------
\section{Professional Summary}
\begin{itemize}[leftmargin=0.2in, label={}, nosep]
  \item \small{
    [2-4 sentences with top 5 JD keywords, archetype framing, one quantified achievement]
  }
\end{itemize}
```

If a Professional Summary section already exists (from a previous tailoring), replace its content.

**6b. Reorder Technical Skills**

Find the Technical Skills section. Within each `\textbf{Category:}` line, reorder the comma-separated items to frontload JD-matching keywords. Example:

Before: `\textbf{Frameworks:} PyTorch, Hugging Face, Langchain, LangGraph, LlamaIndex, PySpark...`
After (if JD emphasizes RAG/agents): `\textbf{Frameworks:} Langchain, LangGraph, LlamaIndex, PyTorch, Hugging Face, PySpark...`

**6c. Reorder Work Experience Bullets**

For each job entry, reorder the `\resumeItem{...}` lines. The most JD-relevant bullet goes first. Optionally rephrase 1-2 bullets to weave in JD vocabulary naturally.

Example — if JD emphasizes "multi-agent systems":
Move the SERA bullet (multi-agent, 40+ tools) above the Harbor ATIF bullet.

**6d. Select & Reorder Projects**

From the 7 `\resumeItem{...}` lines in the Projects section, keep only the 4-5 most relevant. Remove the rest. Reorder by JD relevance.

**6e. Preserve Everything Else**

Do NOT modify:

- Header/contact info
- Education section
- LaTeX preamble/macros
- Section ordering (Education → Skills → Work Exp → Publications → Projects → Achievements)
- Hyperlinks
- Formatting commands

### Step 7: Save Modified .tex

Save the tailored version as a **new file** (never overwrite the original):

```
profile/resume_tailored_{company-slug}.tex
```

Where `{company-slug}` is the company name in lowercase with hyphens (e.g., `scale-ai`, `anthropic`, `cohere`).

### Step 8: Compile to PDF

Run via Bash:

```bash
cd /path/to/ai_skills_repo/profile && pdflatex -interaction=nonstopmode resume_tailored_{company-slug}.tex
```

Run **twice** (LaTeX sometimes needs two passes for proper rendering):

```bash
cd /path/to/ai_skills_repo/profile && pdflatex -interaction=nonstopmode resume_tailored_{company-slug}.tex && pdflatex -interaction=nonstopmode resume_tailored_{company-slug}.tex
```

Then move the PDF to the output directory:

```bash
mv profile/resume_tailored_{company-slug}.pdf applications_database/resumes/cv-{company-slug}-{YYYY-MM-DD}.pdf
```

Clean up LaTeX auxiliary files:

```bash
rm -f profile/resume_tailored_{company-slug}.{aux,log,out}
```

### Step 9: Verify & Present

1. **Check compilation succeeded** — exit code 0 and PDF file exists
2. **Check page count** — warn if PDF is >1 page (content may need trimming)
3. **Present summary to user:**

```
CV tailored for: {Company} — {Role}
Archetype: {detected}
Keywords injected: {list of top keywords}
Changes made:
  - Summary: added/updated with {keywords}
  - Skills: reordered {categories}
  - Experience: reordered bullets in {job entries}
  - Projects: selected {N} of 7, removed {removed ones}
Output: applications_database/resumes/cv-{company-slug}-{date}.pdf
```

## Cover Letter Generation

When a cover letter is required (form marks it mandatory, or user asks):

1. **Structure (1 page max, 4 paragraphs):**
   - Paragraph 1: Why this company specifically (concrete fact, not flattery)
   - Paragraph 2: Your strongest match point with a quantified result
   - Paragraph 3: Bridge — how your background connects to what they need (archetype-aware)
   - Paragraph 4: Forward-looking close
2. **JD keywords** woven naturally throughout
3. Save as plain text or compile a separate LaTeX cover letter

## Error Handling

| Issue                   | Solution                                                                           |
| ----------------------- | ---------------------------------------------------------------------------------- |
| pdflatex not installed  | Tell user: "Install TeX Live: `brew install --cask mactex`"                        |
| Compilation error       | Read the `.log` file for errors, fix LaTeX syntax issues                           |
| PDF > 1 page            | Trim: reduce projects from 5→3, shorten bullets, remove least relevant achievement |
| Font not found (Lato)   | Tell user: "Run `sudo tlmgr install lato`"                                         |
| Original .tex corrupted | Never happens — we never overwrite `profile/resume.tex`                            |

## File Structure

```
profile/
├── resume.tex                              # Original template (NEVER overwrite)
├── resume_tailored_scale-ai.tex            # Tailored copy for Scale AI
├── resume_tailored_anthropic.tex           # Tailored copy for Anthropic
└── ...

applications_database/
└── resumes/
    ├── cv-scale-ai-2026-04-16.pdf          # Compiled tailored PDFs
    ├── cv-anthropic-2026-04-16.pdf
    └── ...
```

## Related Skills

- **job-eval** — Evaluate the offer first (provides archetype + keywords for smarter tailoring)
- **job-apply** — Fill the application form after generating the CV
- **job-interview-prep** — Prepare for interviews at this company
- **job-tracker** — Track the application status

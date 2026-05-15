---
name: job-apply
description: Fill job applications using Chrome DevTools MCP — triggers Simplify extension first, then intelligently fills remaining fields from resume and project data.
---

# Job Application Filler

Automate job application filling using Chrome DevTools MCP tools. Uses the Simplify browser extension for initial auto-fill, then intelligently fills remaining fields from the user's resume and project descriptions.

## When to Activate

- User asks to fill/apply to job applications
- User says "apply to all evaluated jobs" or "apply to everything"

## Prerequisites

- Chrome browser open with Chrome DevTools MCP connected
- Simplify browser extension installed in Chrome
- Profile data filled in:
  - `Notion (fetch via `python3 scripts/notion/page_reader.py resume`)` — personal info, education, experience, skills (shared, at repo root)
  - `Notion (fetch via `python3 scripts/notion/page_reader.py projects`)` — project descriptions and reusable answer snippets (shared, at repo root)
- (Optional) Prior evaluation from **job-eval** — if the role was evaluated, the skill uses the evaluation report for smarter, archetype-aware answer generation
- `NOTION_TOKEN` environment variable set — for querying evaluated jobs and updating status

## Non-Negotiables

1. **NEVER click Submit/Apply buttons** — always stop before submission and ask the user to review
2. **NEVER auto-fill sensitive fields** (SSN, bank details, salary if user hasn't specified) — flag these for the user
3. **Always take a final screenshot** for user review before declaring done
4. **Read profile data fresh** every time — never rely on cached/remembered values
5. **ALWAYS trigger Simplify FIRST** — finding and clicking the Simplify autofill button is the #1 priority before any manual filling. Try multiple methods (screenshot, snapshot, evaluate_script) to locate it. Only skip if Simplify is genuinely not installed.
6. **Cover letter handling:**
   - If the form marks cover letter as **optional** → leave empty (don't upload unless user asks)
   - If the form marks cover letter as **required** → generate one:
     - 1 page max, 3-4 paragraphs
     - Paragraph 1: Why this company specifically (concrete fact, not flattery)
     - Paragraph 2: Your strongest match point with a quantified result
     - Paragraph 3: Bridge — how your background connects to what they need
     - Paragraph 4: Forward-looking close
     - Use JD keywords naturally throughout
     - Save as text in the textarea, or generate PDF if file upload required

## Workflow

### Step 1: Get Evaluated Jobs from Notion

Run the query script to get all "Evaluated" jobs from Notion:
```bash
python3 scripts/notion/db_applications.py query --status "Evaluated"
```

Parse the JSON output — get list of `{page_id, company, role, url, score}`.

Filter: only process jobs that have a URL (skip rows with `url: null`).

Show the user the list and ask for confirmation:
```
Found N evaluated jobs to apply to:
1. Cohere — Applied AI Engineer (4.4) — https://...
2. Together AI — Research Engineer (3.8) — https://...
...
Proceed with all N?
```

### Step 2: Load Profile Data & Evaluation Context

Read profile files to have all user data available:

- Read `Notion (fetch via `python3 scripts/notion/page_reader.py resume`)` for structured data (name, email, education, experience, skills)
- Read `Notion (fetch via `python3 scripts/notion/page_reader.py projects`)` for project summaries and reusable answer snippets
- For open-ended questions requiring detailed answers, fetch project context from Notion:
  ```bash
  python3 scripts/notion/page_reader.py roma          # ROMA recursive deep search agent
  python3 scripts/notion/page_reader.py sera          # SERA semantic embedding agent
  python3 scripts/notion/page_reader.py mroma         # m-ROMA multimodal extension
  python3 scripts/notion/page_reader.py deep-research # Multi-agent deep research at Strategy
  python3 scripts/notion/page_reader.py txt2sql       # Text2SQL agent at Piramal
  ```
  Requires `NOTION_TOKEN` env var set.

If profile files are empty/incomplete, warn the user and ask them to fill in the data first.

**Load evaluation context (if available):**

Each row in the Notion database is a page. The evaluation report is stored as the page body content. Fetch it using the existing script with the page_id directly:
```bash
# The page_id comes from db_applications.py query output
python3 scripts/notion/page_reader.py {page_id}
```
If the page body has content, extract:
- **Archetype** — determines answer framing (Research Engineer answers differ from Applied AI answers)
- **Block B gaps** — know what gaps to proactively address in open-ended answers
- **Block F STAR stories** — pre-mapped stories ready to use for behavioral questions
- **Keywords** — extracted JD keywords to weave into answers

When evaluation context is available, use these enhanced framing rules for open-ended answers:

- **Tone: "I'm choosing you"** — frame answers as selective ("What drew me to [Company] is..."), never desperate
- **Archetype-aware:** Research/ML roles → lead with SOTA results, publications. Applied/Platform roles → lead with production systems, scale metrics
- **Use evaluation proof points:** For "Why this role?" → reference matching proof point. For "Relevant achievement?" → use a pre-mapped STAR story

If no evaluation exists, proceed with profile data only — the skill works fine without it.

### Step 3: Process Each Job

For each job, sequentially:

#### 3a. Open in New Tab

**ALWAYS open each job in a NEW TAB** — use `mcp__chrome-devtools__new_page` (NEVER navigate in existing tab).

#### 3b. Trigger Simplify Extension

Simplify adds a floating button overlay to job application pages. Find and click it:

1. **Take a screenshot** to locate the Simplify button
   - Look for a blue/green floating button, often in the bottom-right corner
   - It may say "Autofill" or show the Simplify logo
   - Common selectors: `[class*="simplify"]`, `[id*="simplify"]`, `button` with Simplify text

2. **Click the Simplify button**:
   ```
   Use mcp__chrome-devtools__click with the Simplify button's location
   ```

3. **Wait for Simplify to populate fields**:
   ```
   Use mcp__chrome-devtools__wait_for with timeout of 5000ms for form fields to be filled
   ```

4. If Simplify button is not found, skip to Step 3c (manual fill all fields)

5. If Simplify opens a modal/popup, interact with it to confirm auto-fill

#### 3c. Screenshot & Analyze Gaps

After Simplify runs (or if skipped):

1. **Take a screenshot** of the full form

2. **Scroll down and take additional screenshots** if the form is long
   ```
   Use mcp__chrome-devtools__press_key with "PageDown" then screenshot again
   Repeat until you've seen the entire form
   ```

3. **Identify unfilled fields** by analyzing the screenshots:
   - Empty text inputs (no value visible)
   - Unselected dropdowns (showing "Select..." or placeholder)
   - Unchecked required checkboxes
   - Empty textareas (especially for open-ended questions)
   - File upload fields without files attached

#### 3d. Fill Remaining Fields

For each unfilled field, match it to profile data and fill:

**Text Inputs (name, email, phone, LinkedIn, etc.)**
```
Use mcp__chrome-devtools__click on the field first
Use mcp__chrome-devtools__fill with the value from resume.md
```

**Dropdowns (work authorization, degree type, etc.)**
```
Use mcp__chrome-devtools__click to open the dropdown
Use mcp__chrome-devtools__take_screenshot to see options
Use mcp__chrome-devtools__click on the correct option
```

**Textareas (cover letter, "why this role", project descriptions)**
```
Use mcp__chrome-devtools__click on the textarea
Use mcp__chrome-devtools__fill with content adapted from projects.md
```

For open-ended questions, follow these strict rules:

- **Plain simple English** — no jargon-heavy sentences, no filler words, no fluff
- **Under 150 words** — be short, crisp, and impactful. Every sentence must earn its place
- **Lead with the result** — start with what you achieved, then briefly explain how
- **One project per answer** — pick the single most relevant project from projects.md, don't cram multiple
- **Use real numbers** — percentages, dollar amounts, team sizes, time saved
- **No generic statements** — every answer must reference a specific project, tool, or metric from the profile
- **Read the question carefully** — answer exactly what's asked, nothing more
- Fetch detailed project context from Notion (`python3 scripts/notion/page_reader.py {project}`) when composing answers

**File Uploads (resume PDF, cover letter)**
```
Use mcp__chrome-devtools__upload_file with the path from resume.md "Resume PDF Path" field
```

**Checkboxes / Radio Buttons**
```
Use mcp__chrome-devtools__click on the appropriate option
```

**Field Matching Guide**

| Form Label Pattern                                         | Profile Source                                                                                                         |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| First Name, Last Name, Full Name                           | resume.md > Personal Information > Full Name                                                                           |
| Email, E-mail                                              | resume.md > Personal Information > Email                                                                               |
| Phone, Mobile, Telephone                                   | resume.md > Personal Information > Phone                                                                               |
| LinkedIn, LinkedIn URL                                     | resume.md > Personal Information > LinkedIn                                                                            |
| GitHub, Portfolio, Website                                 | resume.md > Personal Information > GitHub/Portfolio                                                                    |
| City, Location, Address                                    | resume.md > Personal Information > Location                                                                            |
| University, School, College                                | resume.md > Education > University                                                                                     |
| Degree, Education Level                                    | resume.md > Education > Degree                                                                                         |
| Major, Field of Study                                      | resume.md > Education > Major                                                                                          |
| GPA                                                        | resume.md > Education > GPA                                                                                            |
| Graduation Date, Grad Year                                 | resume.md > Education > Graduation Date                                                                                |
| Current Company, Employer                                  | resume.md > Work Experience > Experience 1 > Company                                                                   |
| Current Title, Job Title                                   | resume.md > Work Experience > Experience 1 > Title                                                                     |
| Years of Experience                                        | resume.md > Additional Information > Years of Experience                                                               |
| Work Authorization, Legally authorized                     | resume.md > Work Authorization                                                                                         |
| Visa Sponsorship, Require sponsorship                      | resume.md > Work Authorization > Visa sponsorship required                                                             |
| Salary, Compensation, Pay                                  | Flag for user -- do not auto-fill unless specified in resume.md                                                        |
| Start Date, Available from                                 | resume.md > Additional Information > Earliest Start Date                                                               |
| How did you hear about us, Referral                        | resume.md > Additional Information > How did you hear about us                                                         |
| Gender, Race, Ethnicity, Veteran, Disability               | resume.md > Additional Information (EEO fields -- use values if provided, otherwise select "Decline to self-identify") |
| Resume, CV (file upload)                                   | resume.md > Resume PDF Path                                                                                            |
| Cover Letter (file upload)                                 | resume.md > Cover Letter PDF Path                                                                                      |
| Tell us about yourself, Why interested, Describe a project | projects.md > select most relevant snippet and adapt                                                                   |

#### 3e. Handle Platform-Specific Quirks

**Greenhouse**
- Multi-page forms: after filling visible fields, look for "Next" or "Continue" button
- Click it and repeat Steps 3c-3d for the next page
- Custom questions often appear on page 2+

**Lever**
- Single-page forms with sections
- Resume upload is usually at the top
- Custom questions at the bottom

**Workday**
- Complex multi-step wizard
- Requires account creation sometimes -- flag for user
- Many dropdown-heavy fields

**Ashby**
- Clean single-page layout
- File upload then form fields

**Generic ATS / Custom Forms**
- Use screenshot analysis to identify form structure
- Match labels to profile data using the field matching guide above

#### 3f. Take Final Screenshot

Take a screenshot of the completed form for reference.

#### 3g. Update Notion Status

Update the row to "Almost Applied":
```bash
python3 scripts/notion/db_applications.py update-status --page-id "{page_id}" --status "Almost Applied"
```

#### 3h. Move to Next Job

**Do NOT wait for user to submit** — move on immediately to the next job.

### Step 4: Summary

After all jobs processed, summarize:

```
Applied to N jobs. All forms filled and open in separate tabs.
Review each tab and click Submit when ready.

Tabs open:
1. Cohere — Applied AI Engineer → Status: Almost Applied
2. Together AI — Research Engineer → Status: Almost Applied
...
```

## Critical Rules

- **ALWAYS open each job in a NEW TAB** — never navigate away from a tab with a filled form
- **NEVER wait** for user to submit before moving to the next job
- **NEVER click Submit** — user reviews and submits each tab manually
- **Update Notion status after filling each form** — not at the end

## Handling Edge Cases

### CAPTCHA

- Flag for user: "There's a CAPTCHA on this form. Please solve it manually, then tell me to continue."

### Login Required

- Flag for user: "This application requires login. Please log in first, then tell me to continue."

### Multi-page Forms

- Fill each page completely before advancing
- Take screenshots of each page for the review summary

### Dynamic Fields (fields that appear based on previous answers)

- After filling a field that might trigger new fields, take a screenshot
- If new fields appeared, fill those too

### Pre-filled but Incorrect Fields

- If Simplify filled a field incorrectly, clear it first:
  ```
  Use mcp__chrome-devtools__click on the field (triple-click to select all)
  Use mcp__chrome-devtools__fill with the correct value
  ```

## Troubleshooting

| Issue                         | Solution                                                                    |
| ----------------------------- | --------------------------------------------------------------------------- |
| Simplify button not found     | Skip Simplify, fill all fields manually from profile data                   |
| Chrome DevTools not connected | Ask user to ensure Chrome is open and MCP server is running                 |
| Field won't accept input      | Try clicking the field first, then use `type_text` instead of `fill`        |
| Dropdown options not visible  | Take screenshot after clicking, use `press_key` with arrow keys to navigate |
| Form has iframes              | Use `evaluate_script` to check for iframes, switch context if needed        |
| File upload fails             | Verify the PDF path in resume.md is correct and file exists                 |

## Related Skills

- **job-eval** — Evaluate a job offer before applying (A-G scoring framework)
- **job-interview-prep** — Prepare for interviews at a specific company
- **job-cv-tailor** — Generate an ATS-optimized CV tailored to the JD
- **job-ops** — Command center that routes to all career skills
- **linkedin-outreach** — Draft personalized LinkedIn outreach messages

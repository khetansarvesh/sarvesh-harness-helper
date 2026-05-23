#!/usr/bin/env python3
"""
Filter, deduplicate, liveness check, and upload candidates to Notion.

Pipeline: candidate_store.json → title filter → dedup vs Notion → liveness check → upload as "Scanned"

Usage:
  python3 dedup_liveness_upload.py skills/job-scan/candidate_store.json
  python3 dedup_liveness_upload.py skills/job-scan/candidate_store.json --skip-liveness
"""

import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from scripts.notion.db_applications import load_dedup_sets, add_scanned_jobs_batch
from scripts.notion.page_preferences import build_title_filter

# Import US location filter (add parent of job-scan scripts to path)
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from api_helpers.api_job_fetcher import is_us_location

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIVENESS_SCRIPT = os.path.join(SCRIPT_DIR, "liveness_helpers", "check-liveness.mjs")


def normalize_source(raw: str) -> str | None:
    """Map raw source strings to Notion select values: API, Web Search, User."""
    if not raw:
        return None
    raw = raw.strip().lower()
    if raw.endswith("-api"):
        return "API"
    if raw in ("web_search", "career_crawl"):
        return "Web Search"
    if raw == "user_input":
        return "User"
    return None


def apply_title_filter(candidates):
    """Filter candidates by title using positive/negative keywords from Notion Preferences."""
    title_filter = build_title_filter()

    passed = []
    filtered = 0

    for c in candidates:
        role = c.get("role", "")
        if title_filter(role):
            passed.append(c)
        else:
            filtered += 1

    print(f"  After title filter: {len(passed)} pass, {filtered} filtered out")
    return passed


def is_specific_job_url(url: str) -> bool:
    """Return True if URL points to a specific job posting, not a category/landing page."""
    if not url:
        return False

    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    query = parsed.query
    segments = [s for s in path.split("/") if s]

    # Known ATS patterns — ALWAYS specific job URLs
    if "ashbyhq.com" in parsed.netloc and len(segments) >= 2:
        return True
    if "greenhouse.io" in parsed.netloc and "/jobs/" in path:
        return True
    if "lever.co" in parsed.netloc and len(segments) >= 2:
        return True
    if "workable.com" in parsed.netloc and "/j/" in path:
        return True
    if "myworkdayjobs.com" in parsed.netloc and "/job/" in path:
        return True

    # REJECT patterns — landing/category pages
    reject_patterns = [
        r"/careers/?$",
        r"/careers[#?]",
        r"/careers-at-",
        r"/job-category/",
        r"/job-categories/",
        r"/search\b",
        r"[?&]team=",
        r"[?&]filter=",
        r"/explore-careers",
        r"/content/en/",
        r"/opportunities/?$",
    ]
    full_url_str = path + ("?" + query if query else "")
    for pattern in reject_patterns:
        if re.search(pattern, full_url_str, re.IGNORECASE):
            return False

    # Category page: /en/jobs/{category-slug} with NO numeric ID
    if re.search(r"/jobs?/[a-z][a-z0-9-]+$", path) and not re.search(r"/\d{5,}", path):
        return False

    # Generic /ai-ml-engineering style endpoints
    if re.search(r"/[a-z]+-[a-z]+-[a-z]+/?$", path) and not re.search(r"\d{5,}", path):
        if len(segments) <= 4 and not re.search(r"[a-f0-9]{8}-", url):
            return False

    # Check for job-specific identifiers
    if re.search(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", url):
        return True
    if re.search(r"/\d{5,}", path):
        return True
    if re.search(r"/[jJ][rR]\d{4,}", path) or re.search(r"/[R]\d{5,}", path):
        return True
    if re.search(r"--\d{5,}", path):
        return True

    # Short path with no identifiers = probably landing page
    if len(segments) <= 2:
        return False

    return True


def apply_url_filter(candidates):
    """Filter out URLs that point to landing/category pages instead of specific job postings."""
    passed = []
    filtered = 0
    for c in candidates:
        url = c.get("url", "")
        if is_specific_job_url(url):
            passed.append(c)
        else:
            filtered += 1
    print(f"  After URL filter: {len(passed)} pass, {filtered} landing/category pages filtered out")
    return passed


def apply_location_filter(candidates):
    """Filter candidates to US-based, remote, or unknown locations only."""
    passed = []
    filtered = 0
    for c in candidates:
        location = c.get("location", "")
        if is_us_location(location):
            passed.append(c)
        else:
            filtered += 1
    print(f"  After location filter: {len(passed)} pass, {filtered} non-US filtered out")
    return passed


def dedup(candidates):
    """Deduplicate candidates against Notion and intra-batch."""
    print("Querying Notion for dedup...")
    seen_urls, seen_company_roles = load_dedup_sets()

    new_jobs = []
    dupes = 0
    intra_urls = set()
    intra_company_roles = set()

    for c in candidates:
        url = c.get("url", "")
        company = c.get("company", "").strip()
        role = c.get("role", "").strip()

        if not url:
            continue

        if url in seen_urls or url in intra_urls:
            dupes += 1
            continue

        key = f"{company.lower()}::{role.lower()}"
        if key in seen_company_roles or key in intra_company_roles:
            dupes += 1
            continue

        intra_urls.add(url)
        intra_company_roles.add(key)
        new_jobs.append({"company": company, "role": role, "url": url, "location": c.get("location", ""), "source": c.get("source", "")})

    print(f"  After dedup: {len(new_jobs)} new, {dupes} duplicates")
    return new_jobs


def liveness_check(jobs):
    """Run Playwright liveness check on job URLs. Returns only active/uncertain jobs."""
    if not jobs:
        return jobs

    urls = [j["url"] for j in jobs]
    print(f"Running liveness check on {len(urls)} URLs...")

    # Write URLs to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(urls))
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["node", LIVENESS_SCRIPT, "--file", tmp_path],
            capture_output=True, text=True, timeout=600,
        )
        output = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired:
        os.unlink(tmp_path)
        print("  ERROR: Liveness check timed out. Aborting — no jobs will be uploaded.", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        os.unlink(tmp_path)
        print("  ERROR: Node.js or check-liveness.mjs not found. Aborting — no jobs will be uploaded.", file=sys.stderr)
        sys.exit(1)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # CRITICAL: If the liveness script crashed, abort rather than passing all jobs through
    if result.returncode != 0 and result.returncode != 1:
        print(f"  ERROR: Liveness script crashed (exit code {result.returncode}).", file=sys.stderr)
        if stderr:
            print(f"  stderr: {stderr[:500]}", file=sys.stderr)
        print("  Aborting — no jobs will be uploaded.", file=sys.stderr)
        sys.exit(1)

    # Parse output: each line is "✅ active     URL" or "❌ expired    URL" or "⚠️ uncertain  URL"
    classified_count = 0
    expired_urls = set()
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(r"[✅❌⚠️]+\s+(active|expired|uncertain)\s+(https?://\S+)", line)
        if match:
            classified_count += 1
            status = match.group(1)
            url = match.group(2)
            if status == "expired":
                expired_urls.add(url)

    # If liveness checked zero URLs but we expected results, something went wrong
    if classified_count == 0:
        print(f"  ERROR: Liveness script produced no results for {len(urls)} URLs.", file=sys.stderr)
        if stderr:
            print(f"  stderr: {stderr[:500]}", file=sys.stderr)
        print("  Aborting — no jobs will be uploaded.", file=sys.stderr)
        sys.exit(1)

    surviving = [j for j in jobs if j["url"] not in expired_urls]
    print(f"  Liveness: {len(expired_urls)} expired, {len(surviving)} active/uncertain pass through")
    return surviving


def upload(jobs, candidate_file):
    """Upload jobs to Notion and clear the candidate store."""
    if not jobs:
        print("No jobs to upload.")
        return

    result = add_scanned_jobs_batch(jobs)
    if result.get("success"):
        print(f"  Uploaded {result.get('count', 0)} jobs to Notion (status: Scanned)")
    else:
        print(f"  Upload error: {result}", file=sys.stderr)
        sys.exit(1)

    with open(candidate_file, "w") as f:
        json.dump([], f)
    print(f"  Cleared {candidate_file}")

    print(f"\nDone. {len(jobs)} new jobs added to Notion.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 dedup_liveness_upload.py <candidate_store.json> [--skip-liveness]", file=sys.stderr)
        sys.exit(1)

    candidate_file = sys.argv[1]
    skip_liveness = "--skip-liveness" in sys.argv

    if not os.path.exists(candidate_file):
        print(f"Error: {candidate_file} not found.", file=sys.stderr)
        sys.exit(1)

    with open(candidate_file, "r") as f:
        candidates = json.load(f)

    if not candidates:
        print("No candidates to process.")
        return

    print(f"Loaded {len(candidates)} candidates from {candidate_file}")

    # Step 1: Title filter
    filtered = apply_title_filter(candidates)

    if not filtered:
        print("No candidates passed title filter.")
        return

    # Step 1.5: Location filter (US only)
    filtered = apply_location_filter(filtered)

    if not filtered:
        print("No candidates passed location filter.")
        return

    # Step 1.6: URL specificity filter (block landing/category pages)
    filtered = apply_url_filter(filtered)

    if not filtered:
        print("No candidates passed URL filter.")
        return

    # Step 2: Dedup
    new_jobs = dedup(filtered)

    if not new_jobs:
        print("No new jobs after dedup.")
        return

    # Step 3: Liveness check
    if skip_liveness:
        print("Skipping liveness check (--skip-liveness)")
        surviving = new_jobs
    else:
        surviving = liveness_check(new_jobs)

    # Step 3.5: Normalize source field
    for job in surviving:
        job["source"] = normalize_source(job.get("source", ""))

    # Step 4: Upload
    upload(surviving, candidate_file)


if __name__ == "__main__":
    main()

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
        new_jobs.append({"company": company, "role": role, "url": url, "location": c.get("location", "")})

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
    except subprocess.TimeoutExpired:
        print("  Warning: Liveness check timed out — skipping, all jobs pass through")
        return jobs
    except FileNotFoundError:
        print("  Warning: Node.js or check-liveness.mjs not found — skipping liveness check")
        return jobs
    finally:
        os.unlink(tmp_path)

    # Parse output: each line is "✅ active     URL" or "❌ expired    URL" or "⚠️ uncertain  URL"
    expired_urls = set()
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(r"[✅❌⚠️]+\s+(active|expired|uncertain)\s+(https?://\S+)", line)
        if match:
            status = match.group(1)
            url = match.group(2)
            if status == "expired":
                expired_urls.add(url)

    if expired_urls:
        surviving = [j for j in jobs if j["url"] not in expired_urls]
        print(f"  Liveness: {len(expired_urls)} expired, {len(surviving)} active/uncertain pass through")
        return surviving
    else:
        print(f"  Liveness: all {len(jobs)} URLs active")
        return jobs


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

    # Step 4: Upload
    upload(surviving, candidate_file)


if __name__ == "__main__":
    main()

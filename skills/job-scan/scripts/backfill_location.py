#!/usr/bin/env python3
"""
Backfill Location column in Notion for existing Scanned jobs.

Loads jobs with empty Location from a JSON file, enriches location
via ATS APIs (Greenhouse, Ashby, Lever), and updates Notion pages.

Usage:
  python3 skills/job-scan/scripts/backfill_location.py /tmp/no_loc_scanned_jobs.json
  python3 skills/job-scan/scripts/backfill_location.py /tmp/no_loc_scanned_jobs.json --dry-run
"""

import json
import os
import re
import sys
import urllib.request

from sarvesh_ai_notion_interface.config import NOTION_TOKEN, NOTION_DB_APPLICATIONS
from sarvesh_ai_notion_interface.notion_client import notion_request

# Import enrichment logic
sys.path.insert(0, os.path.dirname(__file__))
from api_helpers.api_resolver import identify_board, extract_slug, build_api
from api_helpers.api_job_fetcher import is_us_location

FETCH_TIMEOUT_S = 10


def fetch_json(url):
    """Fetch JSON from a URL with timeout."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return None


def update_notion_location(page_id, location):
    """Update the Location property of a Notion page."""
    return notion_request(f"pages/{page_id}", method="PATCH", data={
        "properties": {
            "Location": {"rich_text": [{"text": {"content": location}}]}
        }
    })


def enrich_greenhouse_batch(jobs):
    """Enrich location for Greenhouse jobs by batch-fetching company APIs."""
    from collections import defaultdict

    enriched = 0
    by_slug = defaultdict(list)

    for j in jobs:
        url = j.get("url", "")
        slug = extract_slug(url, "greenhouse")
        match = re.search(r"/jobs/(\d+)", url)
        job_id = int(match.group(1)) if match else None
        if slug and job_id:
            by_slug[slug].append((j, job_id))

    for slug, items in by_slug.items():
        api_info = build_api("greenhouse", slug)
        if not api_info:
            print(f"    Greenhouse: no API for slug '{slug}'")
            continue

        print(f"    Greenhouse: fetching {slug} ({len(items)} jobs)...", end=" ", flush=True)
        data = fetch_json(api_info["api"])
        if not data:
            print("API error")
            continue

        # Build lookup
        job_locations = {}
        for j in data.get("jobs", []):
            jid = j.get("id")
            loc = (j.get("location") or {}).get("name", "")
            if jid and loc:
                job_locations[jid] = loc

        matched = 0
        for job, job_id in items:
            if job_id in job_locations:
                job["location"] = job_locations[job_id]
                matched += 1
        enriched += matched
        print(f"{matched}/{len(items)} matched")

    return enriched


def enrich_ashby_batch(jobs):
    """Enrich location for Ashby jobs by batch-fetching company APIs."""
    from collections import defaultdict

    enriched = 0
    by_slug = defaultdict(list)

    for j in jobs:
        url = j.get("url", "")
        slug = extract_slug(url, "ashby")
        if slug:
            by_slug[slug].append(j)

    for slug, items in by_slug.items():
        api_info = build_api("ashby", slug)
        if not api_info:
            print(f"    Ashby: no API for slug '{slug}'")
            continue

        print(f"    Ashby: fetching {slug} ({len(items)} jobs)...", end=" ", flush=True)
        data = fetch_json(api_info["api"])
        if not data:
            print("API error")
            continue

        url_locations = {}
        for j in data.get("jobs", []):
            job_url = j.get("jobUrl", "")
            loc = j.get("location", "")
            if job_url and loc:
                url_locations[job_url] = loc

        matched = 0
        for job in items:
            if job.get("url", "") in url_locations:
                job["location"] = url_locations[job["url"]]
                matched += 1
        enriched += matched
        print(f"{matched}/{len(items)} matched")

    return enriched


def enrich_lever_batch(jobs):
    """Enrich location for Lever jobs by batch-fetching company APIs."""
    from collections import defaultdict

    enriched = 0
    by_slug = defaultdict(list)

    for j in jobs:
        url = j.get("url", "")
        slug = extract_slug(url, "lever")
        if slug:
            by_slug[slug].append(j)

    for slug, items in by_slug.items():
        api_info = build_api("lever", slug)
        if not api_info:
            print(f"    Lever: no API for slug '{slug}'")
            continue

        print(f"    Lever: fetching {slug} ({len(items)} jobs)...", end=" ", flush=True)
        data = fetch_json(api_info["api"])
        if not data or not isinstance(data, list):
            print("API error")
            continue

        url_locations = {}
        for j in data:
            hosted_url = j.get("hostedUrl", "")
            loc = (j.get("categories") or {}).get("location", "")
            if hosted_url and loc:
                url_locations[hosted_url] = loc

        matched = 0
        for job in items:
            if job.get("url", "") in url_locations:
                job["location"] = url_locations[job["url"]]
                matched += 1
        enriched += matched
        print(f"{matched}/{len(items)} matched")

    return enriched


def main():
    dry_run = "--dry-run" in sys.argv

    if len(sys.argv) < 2:
        print("Usage: python3 backfill_location.py <jobs.json> [--dry-run]", file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]
    with open(input_file) as f:
        jobs = json.load(f)

    print(f"Loaded {len(jobs)} jobs with missing location")

    # Group by ATS
    ats_groups = {"greenhouse": [], "ashby": [], "lever": [], "unknown": [], "other": []}
    for j in jobs:
        ats = j.get("ats", "unknown")
        if ats in ats_groups:
            ats_groups[ats].append(j)
        else:
            ats_groups["other"].append(j)

    print(f"  Greenhouse: {len(ats_groups['greenhouse'])}")
    print(f"  Ashby:      {len(ats_groups['ashby'])}")
    print(f"  Lever:      {len(ats_groups['lever'])}")
    print(f"  Other:      {len(ats_groups['other'])}")
    print(f"  Unknown:    {len(ats_groups['unknown'])}")
    print()

    # Enrich each ATS type
    total_enriched = 0

    if ats_groups["greenhouse"]:
        print("Enriching Greenhouse jobs...")
        total_enriched += enrich_greenhouse_batch(ats_groups["greenhouse"])
        print()

    if ats_groups["ashby"]:
        print("Enriching Ashby jobs...")
        total_enriched += enrich_ashby_batch(ats_groups["ashby"])
        print()

    if ats_groups["lever"]:
        print("Enriching Lever jobs...")
        total_enriched += enrich_lever_batch(ats_groups["lever"])
        print()

    # Summary
    still_missing = [j for j in jobs if not j.get("location", "").strip()]
    us_jobs = [j for j in jobs if j.get("location", "").strip() and is_us_location(j["location"])]
    non_us_jobs = [j for j in jobs if j.get("location", "").strip() and not is_us_location(j["location"])]

    print("=" * 60)
    print(f"Enrichment results:")
    print(f"  Total:           {len(jobs)}")
    print(f"  Enriched:        {total_enriched}")
    print(f"  Still missing:   {len(still_missing)}")
    print(f"  US/Remote:       {len(us_jobs)}")
    print(f"  Non-US:          {len(non_us_jobs)}")
    print()

    # Show non-US jobs that should be discarded
    if non_us_jobs:
        print("Non-US jobs (should be discarded):")
        for j in non_us_jobs:
            print(f"  {j['company']:20s} | {j['role'][:50]:50s} | {j['location']}")
        print()

    # Show still-missing jobs
    if still_missing:
        print(f"Jobs still without location ({len(still_missing)}):")
        for j in still_missing[:10]:
            print(f"  {j['company']:20s} | {j['role'][:50]:50s} | src={j.get('source','')} | ats={j.get('ats','')}")
        if len(still_missing) > 10:
            print(f"  ... and {len(still_missing) - 10} more")
        print()

    if dry_run:
        print("DRY RUN — no Notion updates made.")
        return

    # Update Notion for enriched US jobs
    updated = 0
    update_errors = 0

    for j in us_jobs:
        if not j.get("location", "").strip():
            continue
        try:
            result = update_notion_location(j["page_id"], j["location"])
            if result.get("id"):
                updated += 1
            else:
                update_errors += 1
                print(f"  Error updating {j['company']} — {j['role'][:30]}: {result}")
        except Exception as e:
            update_errors += 1
            print(f"  Error updating {j['company']} — {j['role'][:30]}: {e}")

    print(f"Notion updates: {updated} succeeded, {update_errors} errors")

    # Archive non-US jobs
    archived = 0
    for j in non_us_jobs:
        try:
            notion_request(f"pages/{j['page_id']}", method="PATCH", data={"archived": True})
            archived += 1
        except Exception as e:
            print(f"  Error archiving {j['company']} — {j['role'][:30]}: {e}")

    if archived:
        print(f"Archived {archived} non-US jobs from Notion")

    print("\nDone!")


if __name__ == "__main__":
    main()

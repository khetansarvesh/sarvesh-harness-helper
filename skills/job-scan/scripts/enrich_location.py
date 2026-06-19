#!/usr/bin/env python3
"""
Location enrichment for job candidates.

For candidates with no location data, attempts to resolve location from:
1. ATS APIs (Greenhouse, Ashby, Lever) — batch lookup by company slug
2. Fallback: parse location from the job URL page title/path

Used by dedup_liveness_upload.py before the location filter step,
so that web-search-sourced jobs can be properly filtered by US location.
"""

import re
import urllib.request
import json
from collections import defaultdict

# Reuse existing resolver
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api_helpers"))
from api_resolver import identify_board as detect_board, extract_slug, build_api


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
    except Exception:
        return None


def _extract_greenhouse_job_id(url):
    """Extract numeric job ID from a Greenhouse URL."""
    match = re.search(r"/jobs/(\d+)", url)
    return int(match.group(1)) if match else None


def _extract_ashby_job_id(url):
    """Extract Ashby job ID from URL path."""
    # Ashby URLs: https://jobs.ashbyhq.com/{slug}/{jobId}
    match = re.search(r"jobs\.ashbyhq\.com/[^/]+/([a-f0-9-]{36})", url)
    return match.group(1) if match else None


def _extract_lever_job_id(url):
    """Extract Lever posting ID from URL."""
    # Lever URLs: https://jobs.lever.co/{slug}/{postingId}
    match = re.search(r"jobs\.lever\.co/[^/]+/([a-f0-9-]{36})", url)
    return match.group(1) if match else None


def enrich_greenhouse(candidates):
    """Enrich location for Greenhouse candidates by batch-fetching company APIs.

    Groups candidates by company slug, fetches the full job list for each,
    and matches by job ID to get location.
    """
    enriched = 0
    errors = 0

    # Group by slug
    by_slug = defaultdict(list)
    for c in candidates:
        url = c.get("url", "")
        board = detect_board(url)
        if board != "greenhouse":
            continue
        slug = extract_slug(url, board)
        job_id = _extract_greenhouse_job_id(url)
        if slug and job_id:
            by_slug[slug].append((c, job_id))

    for slug, items in by_slug.items():
        api_info = build_api("greenhouse", slug)
        if not api_info:
            continue
        data = fetch_json(api_info["api"])
        if not data:
            errors += 1
            continue

        # Build lookup: job_id → location
        job_locations = {}
        for j in data.get("jobs", []):
            jid = j.get("id")
            loc = (j.get("location") or {}).get("name", "")
            if jid and loc:
                job_locations[jid] = loc

        # Apply to candidates
        for c, job_id in items:
            if job_id in job_locations:
                c["location"] = job_locations[job_id]
                enriched += 1

    return enriched, errors


def enrich_ashby(candidates):
    """Enrich location for Ashby candidates by batch-fetching company APIs."""
    enriched = 0
    errors = 0

    by_slug = defaultdict(list)
    for c in candidates:
        url = c.get("url", "")
        board = detect_board(url)
        if board != "ashby":
            continue
        slug = extract_slug(url, board)
        if slug:
            by_slug[slug].append(c)

    for slug, items in by_slug.items():
        api_info = build_api("ashby", slug)
        if not api_info:
            continue
        data = fetch_json(api_info["api"])
        if not data:
            errors += 1
            continue

        # Build lookup: jobUrl → location
        url_locations = {}
        for j in data.get("jobs", []):
            job_url = j.get("jobUrl", "")
            loc = j.get("location", "")
            if job_url and loc:
                url_locations[job_url] = loc

        for c in items:
            url = c.get("url", "")
            if url in url_locations:
                c["location"] = url_locations[url]
                enriched += 1

    return enriched, errors


def enrich_lever(candidates):
    """Enrich location for Lever candidates by batch-fetching company APIs."""
    enriched = 0
    errors = 0

    by_slug = defaultdict(list)
    for c in candidates:
        url = c.get("url", "")
        board = detect_board(url)
        if board != "lever":
            continue
        slug = extract_slug(url, board)
        if slug:
            by_slug[slug].append(c)

    for slug, items in by_slug.items():
        api_info = build_api("lever", slug)
        if not api_info:
            continue
        data = fetch_json(api_info["api"])
        if not data or not isinstance(data, list):
            errors += 1
            continue

        # Build lookup: hostedUrl → location
        url_locations = {}
        for j in data:
            hosted_url = j.get("hostedUrl", "")
            loc = (j.get("categories") or {}).get("location", "")
            if hosted_url and loc:
                url_locations[hosted_url] = loc

        for c in items:
            url = c.get("url", "")
            if url in url_locations:
                c["location"] = url_locations[url]
                enriched += 1

    return enriched, errors


def enrich_locations(candidates):
    """Enrich location data for all candidates missing it.

    Tries ATS APIs first (Greenhouse, Ashby, Lever), then URL-based heuristics.

    Returns:
        (enriched_count, error_count)
    """
    # Only process candidates with empty/missing location
    needs_enrichment = [c for c in candidates if not c.get("location", "").strip()]

    if not needs_enrichment:
        print(f"  Location enrichment: all {len(candidates)} candidates already have location data")
        return 0, 0

    print(f"  Location enrichment: {len(needs_enrichment)} candidates need location lookup")

    total_enriched = 0
    total_errors = 0

    # Try each ATS
    for enrich_fn, name in [
        (enrich_greenhouse, "Greenhouse"),
        (enrich_ashby, "Ashby"),
        (enrich_lever, "Lever"),
    ]:
        enriched, errors = enrich_fn(needs_enrichment)
        total_enriched += enriched
        total_errors += errors
        if enriched > 0 or errors > 0:
            print(f"    {name}: {enriched} enriched, {errors} API errors")

    # Update needs_enrichment to reflect remaining un-enriched
    still_missing = sum(1 for c in needs_enrichment if not c.get("location", "").strip())
    if still_missing > 0:
        print(f"    {still_missing} candidates still without location (non-ATS or API miss)")

    print(f"  Location enrichment: {total_enriched} enriched, {total_errors} errors")
    return total_enriched, total_errors

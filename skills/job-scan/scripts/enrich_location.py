#!/usr/bin/env python3
"""
Location enrichment for job candidates.

For candidates with no location data, resolve the underlying ATS posting and
copy its location onto the candidate before the location filter runs.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api_helpers"))
from api_resolver import identify_board as detect_board, extract_slug, build_api
from api_job_fetcher import fetch_company_jobs
from candidate_matching import match_job, slug_group_key


def enrich_locations(candidates):
    """Enrich location data for all candidates missing it.

    Returns:
        (enriched_count, error_count)
    """
    needs_enrichment = [c for c in candidates if not c.get("location", "").strip()]

    if not needs_enrichment:
        print(f"  Location enrichment: all {len(candidates)} candidates already have location data")
        return 0, 0

    print(f"  Location enrichment: {len(needs_enrichment)} candidates need location lookup")

    grouped = defaultdict(list)
    unsupported = 0
    for candidate in needs_enrichment:
        url = candidate.get("url", "")
        board = detect_board(url)
        slug = extract_slug(url, board)
        api_info = build_api(board, slug) if board != "unknown" else None
        if not api_info or not api_info.get("api"):
            unsupported += 1
            continue
        grouped[(board, slug_group_key(slug))].append((candidate, slug, api_info))

    enriched = 0
    errors = 0
    board_stats = defaultdict(lambda: {"enriched": 0, "errors": 0})

    for (board, _slug_key), items in grouped.items():
        candidate, _, api_info = items[0]
        wrapped_api = dict(api_info)
        wrapped_api["url"] = api_info["api"]
        company_payload = {
            "name": candidate.get("company", "") or board,
            "careers_url": candidate.get("url", ""),
            "_api": {"type": board, **wrapped_api},
        }
        jobs, error = fetch_company_jobs(company_payload)
        if error:
            errors += len(items)
            board_stats[board]["errors"] += len(items)
            continue

        for candidate, _, _ in items:
            matched = match_job(candidate.get("url", ""), board, jobs)
            if not matched:
                continue
            location = (matched.get("location") or "").strip()
            if not location:
                continue
            candidate["location"] = location
            enriched += 1
            board_stats[board]["enriched"] += 1

    for board in sorted(board_stats):
        stats = board_stats[board]
        if stats["enriched"] > 0 or stats["errors"] > 0:
            print(f"    {board}: {stats['enriched']} enriched, {stats['errors']} API errors")

    still_missing = sum(1 for c in needs_enrichment if not c.get("location", "").strip())
    if still_missing > 0:
        print(f"    {still_missing} candidates still without location (unsupported ATS or unresolved match)")
    if unsupported > 0:
        print(f"    {unsupported} candidates on unsupported/unknown boards")

    print(f"  Location enrichment: {enriched} enriched, {errors} errors")
    return enriched, errors

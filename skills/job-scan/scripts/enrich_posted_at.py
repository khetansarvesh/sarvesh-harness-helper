#!/usr/bin/env python3
"""
Enrich ATS posted_at for web-search candidates and enforce a time window.

This is used by dedup_liveness_upload.py so broad web-search results are
validated against the underlying ATS posting timestamp instead of relying only
on search-engine freshness.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api_helpers"))
from api_resolver import identify_board as detect_board, extract_slug, build_api
from api_job_fetcher import fetch_company_jobs


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def _extract_job_key(url: str, board: str):
    if not url:
        return None
    path = urlsplit(url).path.rstrip("/")
    if board == "ashby":
        match = re.search(
            r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:/application)?$",
            path,
            re.IGNORECASE,
        )
        return match.group(1).lower() if match else None
    if board == "lever":
        match = re.search(
            r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:/apply)?$",
            path,
            re.IGNORECASE,
        )
        return match.group(1).lower() if match else None
    if board == "greenhouse":
        match = re.search(r"/jobs/(\d+)$", path)
        return match.group(1) if match else None
    if board == "workable":
        match = re.search(r"/j/([A-Z0-9]+)(?:/apply)?$", path, re.IGNORECASE)
        return match.group(1).upper() if match else None
    if board == "workday":
        return path
    return None


def _slug_group_key(slug):
    return json.dumps(slug, sort_keys=True, default=str)


def _match_job(candidate_url: str, board: str, jobs: list[dict]) -> dict | None:
    target_norm = _normalize_url(candidate_url)
    target_key = _extract_job_key(candidate_url, board)

    for job in jobs:
        if _normalize_url(job.get("url", "")) == target_norm:
            return job

    if target_key:
        for job in jobs:
            if _extract_job_key(job.get("url", ""), board) == target_key:
                return job

    target_path = urlsplit(target_norm).path
    for job in jobs:
        if urlsplit(_normalize_url(job.get("url", ""))).path == target_path:
            return job
    return None


def enforce_web_search_posted_at_window(candidates: list[dict], hours: int):
    """
    Resolve ATS posted_at for web_search candidates and filter out stale rows.

    Returns (surviving_candidates, stats).
    """
    if hours <= 0:
        return candidates, {
            "considered": 0,
            "supported": 0,
            "resolved": 0,
            "filtered_old": 0,
            "unresolved": 0,
            "api_errors": 0,
            "hours": hours,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    targets = []
    for candidate in candidates:
        if candidate.get("source") != "web_search":
            continue
        url = candidate.get("url", "")
        board = detect_board(url)
        slug = extract_slug(url, board)
        api_info = build_api(board, slug) if board != "unknown" else None
        if not api_info or not api_info.get("api"):
            continue
        targets.append((candidate, board, slug, api_info))

    if not targets:
        return candidates, {
            "considered": 0,
            "supported": 0,
            "resolved": 0,
            "filtered_old": 0,
            "unresolved": 0,
            "api_errors": 0,
            "hours": hours,
        }

    grouped = defaultdict(list)
    for candidate, board, slug, api_info in targets:
        grouped[(board, _slug_group_key(slug))].append((candidate, slug, api_info))

    stale_urls = set()
    resolved = 0
    unresolved = 0
    api_errors = 0

    for (board, _slug_key), items in grouped.items():
        candidate, slug, api_info = items[0]
        wrapped_api = dict(api_info)
        wrapped_api["url"] = api_info["api"]
        company_payload = {
            "name": candidate.get("company", "") or board,
            "careers_url": candidate.get("url", ""),
            "_api": {"type": board, **wrapped_api},
        }
        jobs, error = fetch_company_jobs(company_payload)
        if error:
            api_errors += len(items)
            continue

        for candidate, _, _ in items:
            matched = _match_job(candidate.get("url", ""), board, jobs)
            if not matched:
                unresolved += 1
                continue

            posted_at = matched.get("posted_at")
            if posted_at is None:
                unresolved += 1
                continue

            resolved += 1
            candidate["posted_at"] = posted_at.isoformat()
            if posted_at < cutoff:
                stale_urls.add(candidate.get("url", ""))

    surviving = [c for c in candidates if c.get("url", "") not in stale_urls]
    return surviving, {
        "considered": len(targets),
        "supported": len(targets),
        "resolved": resolved,
        "filtered_old": len(stale_urls),
        "unresolved": unresolved,
        "api_errors": api_errors,
        "hours": hours,
    }

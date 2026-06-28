#!/usr/bin/env python3
"""
Resolve posted_at for fallback web-search candidates and filter stale jobs.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api_helpers"))
from api_parsers import parse_date
from api_resolver import build_api, extract_slug, identify_board as detect_board
from api_job_fetcher import fetch_company_jobs
from candidate_matching import extract_job_key, match_job

FALLBACK_SOURCES = {"career_crawl", "fallback_web_search", "fallback web search"}
FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json",
}
DEFAULT_REPORT_PATH = "/tmp/jobscan_fallback_posted_at_report.json"

DATE_PATTERNS = [
    (r'"datePosted"\s*:\s*"([^"]+)"', "jsonld_datePosted"),
    (r'"datePublished"\s*:\s*"([^"]+)"', "jsonld_datePublished"),
    (r'"postedDate"\s*:\s*"([^"]+)"', "postedDate"),
    (r'"publicationDate"\s*:\s*"([^"]+)"', "publicationDate"),
    (r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)', "meta_article_published_time"),
]


def _is_fallback_source(raw: str) -> bool:
    return (raw or "").strip().lower() in FALLBACK_SOURCES


def _fetch_page(url: str):
    req = urllib.request.Request(url, headers=FETCH_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.geturl(), resp.read().decode("utf-8", errors="replace")


def _coerce_datetime(value: str):
    dt = parse_date(value)
    if dt is not None:
        return dt

    match = re.search(
        r"(?P<year>20\d{2})-(?P<month>\d{1,2})-(?P<day>\d{1,2})(?P<rest>T[^\"\s<]+)?",
        value or "",
    )
    if not match:
        return None

    rest = match.group("rest") or ""
    normalized = (
        f"{match.group('year')}-"
        f"{int(match.group('month')):02d}-"
        f"{int(match.group('day')):02d}"
        f"{rest}"
    )
    dt = parse_date(normalized)
    if dt is not None:
        return dt
    try:
        dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _extract_page_posted_at(page: str):
    for pattern, label in DATE_PATTERNS:
        match = re.search(pattern, page, re.IGNORECASE)
        if not match:
            continue
        value = html.unescape(match.group(1)).strip()
        dt = _coerce_datetime(value)
        if dt is None:
            continue
        return dt, label
    return None, None


def _extract_wrapper_urls(page: str, base_url: str):
    candidates = []
    patterns = [
        r'<a[^>]+href=["\']([^"\']+)["\']',
        r'<iframe[^>]+src=["\']([^"\']+)["\']',
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        r'"(https?://[^"]+\.icims\.com/jobs/[^"]+)"',
    ]
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, page, re.IGNORECASE):
            raw_url = html.unescape(match.group(1)).strip()
            if not raw_url or raw_url.startswith(("mailto:", "javascript:", "#")):
                continue
            url = urljoin(base_url, raw_url)
            board = detect_board(url)
            if board == "unknown":
                continue
            if board not in {"oracle", "icims", "workday", "applytojob"}:
                # Only keep ATS-like URLs that look job-specific.
                if extract_job_key(url, board) is None:
                    continue
            if url in seen:
                continue
            seen.add(url)
            candidates.append((url, board))
    return candidates


def _resolve_via_ats(target_url: str, company: str):
    board = detect_board(target_url)
    slug = extract_slug(target_url, board)
    api_info = build_api(board, slug) if board != "unknown" else None
    if not api_info or not api_info.get("api"):
        return None, "unsupported_board"

    wrapped_api = dict(api_info)
    wrapped_api["url"] = api_info["api"]
    payload = {
        "name": company or board,
        "careers_url": target_url,
        "_api": {"type": board, **wrapped_api},
    }
    jobs, error = fetch_company_jobs(payload)
    if error:
        return None, f"ats_api_error:{error}"

    matched = match_job(target_url, board, jobs)
    if not matched:
        return None, "ats_match_not_found"

    return {
        "board": board,
        "url": target_url,
        "posted_at": matched.get("posted_at"),
        "location": (matched.get("location") or "").strip(),
    }, None


def enforce_fallback_posted_at_window(candidates: list[dict], hours: int, report_path: str = DEFAULT_REPORT_PATH):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours) if hours > 0 else None
    considered = []
    resolved_and_kept = []
    resolved_and_filtered_old = []
    unresolved = []
    errors = []
    stale_urls = set()

    for candidate in candidates:
        if not _is_fallback_source(candidate.get("source", "")):
            continue

        original_url = candidate.get("url", "")
        record = {
            "company": candidate.get("company", ""),
            "role": candidate.get("role", ""),
            "url": original_url,
            "source": candidate.get("source", ""),
        }
        considered.append(record)

        resolution = None
        failure_reason = None

        direct_resolution, direct_error = _resolve_via_ats(original_url, candidate.get("company", ""))
        if direct_resolution and direct_resolution.get("posted_at") is not None:
            resolution = {
                "posted_at": direct_resolution["posted_at"],
                "posted_at_source": f"ats:{direct_resolution['board']}",
                "matched_url": direct_resolution["url"],
                "location": direct_resolution.get("location", ""),
            }
        else:
            failure_reason = direct_error

        final_url = None
        page = None
        if resolution is None:
            try:
                final_url, page = _fetch_page(original_url)
            except Exception as exc:
                errors.append({**record, "error": f"page_fetch_error:{exc}"})
                candidate["fallback_posted_at_status"] = "error"
                candidate["fallback_posted_at_reason"] = f"page_fetch_error:{exc}"
                continue

            for unwrapped_url, board in _extract_wrapper_urls(page, final_url):
                ats_resolution, ats_error = _resolve_via_ats(unwrapped_url, candidate.get("company", ""))
                if not ats_resolution:
                    failure_reason = ats_error
                    continue
                if ats_resolution.get("posted_at") is None:
                    failure_reason = "ats_posted_at_missing"
                    continue
                resolution = {
                    "posted_at": ats_resolution["posted_at"],
                    "posted_at_source": f"ats:{board}",
                    "matched_url": ats_resolution["url"],
                    "unwrapped_url": unwrapped_url,
                    "location": ats_resolution.get("location", ""),
                }
                break

        if resolution is None and page is not None:
            page_posted_at, signal = _extract_page_posted_at(page)
            if page_posted_at is not None:
                resolution = {
                    "posted_at": page_posted_at,
                    "posted_at_source": f"page:{signal}",
                    "matched_url": final_url or original_url,
                }
            elif failure_reason is None:
                failure_reason = "no_page_signal"

        if resolution is None:
            unresolved.append(
                {
                    **record,
                    "final_url": final_url,
                    "unresolved_reason": failure_reason or "unresolved",
                }
            )
            candidate["fallback_posted_at_status"] = "unresolved"
            candidate["fallback_posted_at_reason"] = failure_reason or "unresolved"
            continue

        posted_at = resolution["posted_at"]
        candidate["posted_at"] = posted_at.isoformat()
        candidate["posted_at_source"] = resolution["posted_at_source"]
        candidate["fallback_posted_at_status"] = "resolved"
        if resolution.get("unwrapped_url"):
            candidate["unwrapped_url"] = resolution["unwrapped_url"]
        location = (resolution.get("location") or "").strip()
        if location and not candidate.get("location", "").strip():
            candidate["location"] = location

        report_row = {
            **record,
            "final_url": final_url,
            "matched_url": resolution.get("matched_url"),
            "unwrapped_url": resolution.get("unwrapped_url"),
            "posted_at": posted_at.isoformat(),
            "posted_at_source": resolution["posted_at_source"],
            "location": location or candidate.get("location", ""),
        }
        if cutoff and posted_at < cutoff:
            stale_urls.add(original_url)
            resolved_and_filtered_old.append(report_row)
        else:
            resolved_and_kept.append(report_row)

    surviving = [candidate for candidate in candidates if candidate.get("url", "") not in stale_urls]

    report = {
        "summary": {
            "considered": len(considered),
            "resolved": len(resolved_and_kept) + len(resolved_and_filtered_old),
            "filtered_old": len(resolved_and_filtered_old),
            "unresolved": len(unresolved),
            "errors": len(errors),
            "hours": hours,
        },
        "resolved_and_kept": resolved_and_kept,
        "resolved_and_filtered_old": resolved_and_filtered_old,
        "unresolved": unresolved,
        "errors": errors,
    }
    if report_path:
        with open(report_path, "w") as fh:
            json.dump(report, fh, indent=2)

    return surviving, {
        **report["summary"],
        "report_path": report_path,
    }

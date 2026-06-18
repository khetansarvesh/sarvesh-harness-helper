"""
HTTP job fetcher for ATS APIs.

Fetches job listings from Greenhouse, Ashby, Lever, Workday, and
SmartRecruiters APIs. Handles paginated providers inline and provides
parallel fetch with filtering and deduplication.
"""

import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from api_helpers.api_parsers import PARSERS, parse_workday


# ── US location filter ────────────────────────────────────────────────
# Allow jobs located in the US, remote, or with no location specified.

_US_STATE_ABBREVS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

_US_KEYWORDS = re.compile(
    r"\bUnited States\b|\bUSA\b|\bU\.S\.A\b|\bU\.S\.\b|\bRemote\b",
    re.IGNORECASE,
)

_NON_US_KEYWORDS = re.compile(
    r"\bIndia\b|\bGermany\b|\bFrance\b|\bJapan\b|\bChina\b|\bKorea\b"
    r"|\bSingapore\b|\bTaiwan\b|\bIreland\b|\bCanada\b|\bBrazil\b"
    r"|\bMexico\b|\bAustralia\b|\bIsrael\b|\bSpain\b|\bItaly\b"
    r"|\bNetherlands\b|\bSweden\b|\bSwitzerland\b|\bPoland\b|\bPune\b"
    r"|\bBangalore\b|\bHyderabad\b|\bMumbai\b|\bDelhi\b|\bGurgaon\b"
    r"|\bNoida\b|\bChennai\b|\bTokyo\b|\bLondon\b|\bBerlin\b|\bParis\b"
    r"|\bMunich\b|\bToronto\b|\bVancouver\b|\bMontreal\b|\bDublin\b"
    r"|\bAmsterdam\b|\bShanghai\b|\bBeijing\b|\bSeoul\b|\bTel Aviv\b"
    r"|\bSão Paulo\b|\bMexico City\b|\bSydney\b|\bMelbourne\b"
    r"|\bTaoyuan\b|\bAthlone\b",
    re.IGNORECASE,
)


def is_us_location(location: str) -> bool:
    """Return True if location is US-based, remote, or unknown."""
    if not location or not location.strip():
        return True  # Unknown location — don't filter out

    # Explicit US signals
    if _US_KEYWORDS.search(location):
        return True

    # Check for US state abbreviations (e.g. "CA", "NY", "San Francisco, CA")
    tokens = re.split(r"[,\s\-/|]+", location)
    for token in tokens:
        if token.upper() in _US_STATE_ABBREVS:
            return True

    # Explicit non-US signals
    if _NON_US_KEYWORDS.search(location):
        return False

    # Ambiguous — let it through to avoid false negatives
    return True

FETCH_TIMEOUT_S = 10


def fetch_json(url, method="GET", body=None):
    """Fetch JSON from a URL with timeout and browser User-Agent."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    data = json.dumps(body).encode() if body else None

    req = urllib.request.Request(url, method=method, headers=headers, data=data)

    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}") from e
    except Exception as e:
        raise RuntimeError(str(e)) from e


def fetch_company_jobs(company):
    """Fetch and parse all jobs for a single company.

    Args:
        company: Dict with "name" and "_api" ({"type", "url", "method"}).

    Returns:
        Tuple of (jobs_list, error_string_or_None).
    """
    api = company["_api"]
    board_type = api["type"]
    api_url = api["url"]
    name = company.get("name", "Unknown")

    try:
        if board_type == "workday":
            all_jobs = []
            page_size = 20
            offset = 0
            total = float("inf")
            while offset < total and offset < 500:
                data = fetch_json(api_url, method="POST", body={"limit": page_size, "offset": offset, "searchText": ""})
                total = data.get("total", 0)
                all_jobs.extend(parse_workday(data, name, api_url))
                offset += page_size
            return all_jobs, None
        elif board_type == "smartrecruiters":
            all_jobs = []
            page_size = 100
            offset = 0
            total = float("inf")
            parser = PARSERS.get(board_type)
            while offset < total and offset < 1000:
                data = fetch_json(f"{api_url}?limit={page_size}&offset={offset}")
                total = data.get("totalFound", 0)
                all_jobs.extend(parser(data, name))
                offset += page_size
            return all_jobs, None
        else:
            data = fetch_json(api_url)
            parser = PARSERS.get(board_type)
            if not parser:
                return [], f"Unknown board type: {board_type}"
            return parser(data, name), None
    except Exception as e:
        return [], str(e)


def fetch_and_filter(targets, title_filter, cutoff, concurrency=10):
    """Fetch jobs from all targets in parallel, apply title/hours filter + intra-scan dedup.

    Notion dedup is NOT done here — that happens later in dedup_liveness_upload.py.

    Args:
        targets: List of company dicts with "_api" field.
        title_filter: Function that takes a title string, returns True if it passes.
        cutoff: datetime cutoff for --hours filter, or None.
        concurrency: Max parallel workers (default 10).

    Returns:
        (new_offers, stats, errors) where:
        - new_offers: list of candidate dicts
        - stats: dict with total_found, total_filtered, total_dupes
        - errors: list of {"company", "error"} dicts
    """
    total_found = 0
    total_filtered = 0
    total_dupes = 0
    new_offers = []
    errors = []

    # Intra-scan dedup (same URL found across multiple companies in one scan)
    seen_urls = set()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(fetch_company_jobs, c): c for c in targets}

        for future in as_completed(futures):
            company = futures[future]
            jobs, error = future.result()

            if error:
                errors.append({"company": company.get("name", "?"), "error": error})
                continue

            total_found += len(jobs)

            for job in jobs:
                # Hours filter
                if cutoff and job["posted_at"] and job["posted_at"] < cutoff:
                    total_filtered += 1
                    continue
                # Title filter
                if not title_filter(job["title"]):
                    total_filtered += 1
                    continue
                # Location filter — US only
                if not is_us_location(job.get("location", "")):
                    total_filtered += 1
                    continue
                # Intra-scan URL dedup
                if job["url"] in seen_urls:
                    total_dupes += 1
                    continue

                seen_urls.add(job["url"])
                new_offers.append({
                    "company": job["company"],
                    "role": job["title"],
                    "url": job["url"],
                    "location": job.get("location", ""),
                    "source": f"{company['_api']['type']}-api",
                })

    stats = {
        "total_found": total_found,
        "total_filtered": total_filtered,
        "total_dupes": total_dupes,
    }
    return new_offers, stats, errors

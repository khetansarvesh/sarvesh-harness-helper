"""
HTTP job fetcher for ATS APIs.

Fetches job listings from 
- Greenhouse
- Ashby 
- Lever
- Workday
- SmartRecruiters
- Workable
- Gem
- Eightfold 
- Rippling
- Work at a Startup
- ApplyToJob
 - iCIMS
Handles paginated providers inline and provides parallel fetch with
filtering and deduplication.
"""

import html
import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.error
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, wait as futures_wait, FIRST_COMPLETED
from urllib.parse import quote, urlencode

from api_helpers.api_parsers import PARSERS, parse_applytojob_date, parse_icims_date, parse_relative_age_text, parse_workday


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
    r"|\bSingapore\b|\bTaiwan\b|\bIreland\b|\bCanada\b|\bBrazil\b|\bIndonesia\b"
    r"|\bMexico\b|\bAustralia\b|\bIsrael\b|\bSpain\b|\bItaly\b"
    r"|\bNetherlands\b|\bSweden\b|\bSwitzerland\b|\bPoland\b|\bNorway\b"
    r"|\bSerbia\b|\bEstonia\b|\bPune\b"
    r"|\bBangalore\b|\bHyderabad\b|\bMumbai\b|\bDelhi\b|\bGurgaon\b"
    r"|\bNoida\b|\bChennai\b|\bTokyo\b|\bLondon\b|\bBerlin\b|\bParis\b"
    r"|\bMunich\b|\bWarsaw\b|\bTallinn\b|\bOslo\b|\bBelgrade\b"
    r"|\bToronto\b|\bVancouver\b|\bMontreal\b|\bDublin\b"
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
MAX_RETRIES = 4
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
BOARD_CONCURRENCY_LIMITS = {
    "workable": 1,
    "eightfold": 1,
    "workatastartup": 2,
    "applytojob": 2,
    "icims": 2,
}
WORKABLE_PLACEHOLDER_SLUG = "j"
EIGHTFOLD_PAGE_DELAY_S = 0.35
EIGHTFOLD_BROWSER_TIMEOUT_S = 300
EIGHTFOLD_BROWSER_HELPER = os.path.join(os.path.dirname(__file__), "fetch_eightfold_browser.mjs")


def build_headers(extra_headers=None):
    """Build common request headers for ATS calls."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _compute_retry_delay(attempt, headers):
    """Return retry delay in seconds, honoring Retry-After when present."""
    retry_after = (headers or {}).get("Retry-After")
    if retry_after:
        try:
            return min(30.0, max(1.0, float(retry_after)))
        except ValueError:
            pass
    return min(30.0, 2.0 * (2 ** attempt))


def _request_bytes(url, method="GET", body=None, headers=None):
    """Fetch raw response bytes with retry/backoff for transient upstream failures."""
    req_headers = build_headers(headers)
    data = json.dumps(body).encode() if body is not None else None
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, method=method, headers=req_headers, data=data)
        try:
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code in RETRYABLE_HTTP_CODES and attempt < MAX_RETRIES:
                time.sleep(_compute_retry_delay(attempt, e.headers))
                continue
            raise RuntimeError(f"HTTP {e.code}") from e
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(_compute_retry_delay(attempt, {}))
                continue
            raise RuntimeError(str(e)) from e

    raise RuntimeError(str(last_error))


def fetch_text(url, method="GET", body=None, headers=None):
    """Fetch raw text from a URL with timeout and browser User-Agent."""
    try:
        return _request_bytes(url, method=method, body=body, headers=headers).decode("utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(str(e)) from e


def fetch_json(url, method="GET", body=None, headers=None):
    """Fetch JSON from a URL with timeout and browser User-Agent."""
    try:
        return json.loads(_request_bytes(url, method=method, body=body, headers=headers))
    except Exception as e:
        raise RuntimeError(str(e)) from e


def infer_eightfold_domain(careers_url):
    """Extract Eightfold's required domain parameter from the board page."""
    if not careers_url:
        return None
    text = fetch_text(careers_url, headers={"Accept": "text/html"})
    patterns = [
        r'domain=([A-Za-z0-9._-]+\.[A-Za-z]{2,})',
        r'"domain"\s*:\s*"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def infer_workday_redirect_api(careers_url):
    """Resolve Workday tenant redirects to the current cxs jobs endpoint."""
    if not careers_url:
        return None

    page_html = fetch_text(careers_url, headers={"Accept": "text/html,application/xhtml+xml"})
    redirect_match = re.search(r"window\.location\.href\s*=\s*'([^']+)'", page_html, re.IGNORECASE)
    if not redirect_match:
        redirect_match = re.search(r'<meta[^>]+http-equiv="refresh"[^>]+url=([^"\'>]+)', page_html, re.IGNORECASE)
    if not redirect_match:
        return None

    redirect_url = html.unescape(redirect_match.group(1))
    req = urllib.request.Request(redirect_url, headers=build_headers({"Accept": "text/html,application/xhtml+xml"}))
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
        final_url = resp.geturl()

    match = re.search(r"https://([^/.]+)\.(wd\d+)\.myworkdayjobs\.com/(?:en-US/)?([^/?#]+)", final_url)
    if not match:
        return None

    company, wd, site = match.groups()
    return f"https://{company}.{wd}.myworkdayjobs.com/wday/cxs/{company}/{site}/jobs"


def build_oracle_jobs_url(api_url, api, limit, offset):
    finder = (
        "findReqs;"
        f"siteNumber={api['site_number']},"
        f"facetsList={api.get('facets')},"
        f"limit={limit},"
        f"offset={offset},"
        "sortBy=POSTING_DATES_DESC"
    )
    params = {
        "onlyData": "true",
        "expand": api.get("expand"),
        "finder": finder,
    }
    return f"{api_url}?{urlencode(params)}"


def fetch_eightfold_data_browser(careers_url, api):
    """Fallback to a real browser session for Eightfold boards that block raw HTTP pagination."""
    if not careers_url:
        raise RuntimeError("Eightfold browser fallback requires careers_url")

    cmd = [
        "node",
        EIGHTFOLD_BROWSER_HELPER,
        "--url",
        careers_url,
        "--maxStart",
        "5000",
        "--pageDelayMs",
        str(int(EIGHTFOLD_PAGE_DELAY_S * 1000)),
    ]
    if api.get("domain"):
        cmd.extend(["--domain", api["domain"]])

    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=EIGHTFOLD_BROWSER_TIMEOUT_S,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Eightfold browser fallback failed: {detail[:300]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Eightfold browser fallback returned invalid JSON") from exc


def _dedupe_jobs_by_url(jobs):
    deduped = []
    seen = set()
    for job in jobs:
        url = job.get("url", "")
        key = url or (job.get("title", ""), job.get("location", ""), job.get("posted_at"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped


def _normalize_company_key(value):
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def fetch_workatastartup_search(query):
    if not query:
        return []
    return (fetch_json(f"https://www.workatastartup.com/jobs/search?q={quote(query)}") or {}).get("jobs") or []


def enrich_workatastartup_posted_at(jobs, api, company_name):
    """Approximate posted_at via Work at a Startup's public search endpoint."""
    slug_meta = api.get("slug") or {}
    company_slug = slug_meta.get("slug") if isinstance(slug_meta, dict) else None
    company_key = _normalize_company_key(company_name)
    posted_at_by_job_id = {}

    def ingest(rows):
        for row in rows:
            if company_slug and row.get("companySlug") != company_slug:
                continue
            if not company_slug and _normalize_company_key(row.get("companyName")) != company_key:
                continue
            job_id = row.get("id")
            if not job_id or job_id in posted_at_by_job_id:
                continue
            posted_at = parse_relative_age_text(row.get("companyLastActiveAt"))
            if posted_at is not None:
                posted_at_by_job_id[job_id] = posted_at

    search_queries = []
    for candidate in (company_name, company_slug, company_slug.replace("-", " ") if company_slug else None):
        if candidate and candidate not in search_queries:
            search_queries.append(candidate)

    for query in search_queries:
        ingest(fetch_workatastartup_search(query))

    missing = [job for job in jobs if job.get("job_id") and job.get("job_id") not in posted_at_by_job_id]
    for job in missing:
        title = job.get("title", "").strip()
        if not title:
            continue
        rows = fetch_workatastartup_search(title)
        for row in rows:
            if row.get("id") != job.get("job_id"):
                continue
            if company_slug and row.get("companySlug") != company_slug:
                continue
            if not company_slug and _normalize_company_key(row.get("companyName")) != company_key:
                continue
            posted_at = parse_relative_age_text(row.get("companyLastActiveAt"))
            if posted_at is not None:
                posted_at_by_job_id[job["job_id"]] = posted_at
                break

    for job in jobs:
        job_id = job.get("job_id")
        if job_id in posted_at_by_job_id:
            job["posted_at"] = posted_at_by_job_id[job_id]


def _fetch_applytojob_job_detail(job):
    """Fetch exact posted date from an ApplyToJob job page."""
    try:
        page = fetch_text(job["url"], headers={"Accept": "text/html,application/xhtml+xml"})
        match = re.search(r'"datePosted"\s*:\s*"(\d{4}-\d{2}-\d{2})"', page, re.IGNORECASE)
        if match:
            job["posted_at"] = parse_applytojob_date(match.group(1))
    except Exception:
        job["posted_at"] = None
    return job


def enrich_applytojob_posted_at(jobs, concurrency=6):
    """Enrich ApplyToJob listing results with datePosted from each job page."""
    if not jobs:
        return jobs

    max_workers = min(concurrency, max(1, len(jobs)))
    enriched = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_applytojob_job_detail, dict(job)): job for job in jobs}
        for future in as_completed(futures):
            enriched.append(future.result())
    return enriched


def fetch_icims_listing_pages(listing_url, max_pages=25):
    """Fetch iCIMS iframe listing pages following pr= pagination."""
    pages = []
    seen = set()
    next_url = listing_url
    while next_url and next_url not in seen and len(pages) < max_pages:
        seen.add(next_url)
        html = fetch_text(next_url, headers={"Accept": "text/html,application/xhtml+xml"})
        pages.append(html)
        match = re.search(r'<link rel="next" href="([^"]+)"', html, re.IGNORECASE)
        if not match:
            break
        next_url = html_unescape_url(match.group(1))
    return pages


def html_unescape_url(value):
    return html.unescape(value).replace("&amp;", "&")


def _fetch_icims_job_detail(job):
    """Fetch exact posted date and location from an iCIMS job page."""
    try:
        page = fetch_text(job["url"] + "?in_iframe=1", headers={"Accept": "text/html,application/xhtml+xml"})
        ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.IGNORECASE | re.DOTALL)
        if ld_match:
            payload = json.loads(ld_match.group(1))
            job["posted_at"] = parse_icims_date(payload.get("datePosted"))
            job_location = payload.get("jobLocation") or []
            if job_location and not job.get("location"):
                address = ((job_location[0] or {}).get("address") or {})
                locality = address.get("addressLocality", "")
                region = address.get("addressRegion", "")
                country = address.get("addressCountry", "")
                location_bits = [part for part in (locality, region, country) if part and part != "UNAVAILABLE"]
                if location_bits:
                    job["location"] = ", ".join(location_bits)
    except Exception:
        job["posted_at"] = None
    return job


def enrich_icims_jobs(jobs, concurrency=6):
    """Enrich iCIMS listing results with datePosted and location from each job page."""
    if not jobs:
        return jobs

    max_workers = min(concurrency, max(1, len(jobs)))
    enriched = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_icims_job_detail, dict(job)): job for job in jobs}
        for future in as_completed(futures):
            enriched.append(future.result())
    return enriched


def _workable_public_filter_queries(filters):
    departments = filters.get("departments") or []
    top_level_departments = [d.get("name") for d in departments if d.get("parent_id") is None and d.get("name")]
    if top_level_departments:
        return [[("department", department)] for department in top_level_departments]

    workplaces = [value for value in (filters.get("workplaces") or []) if value]
    if workplaces:
        return [[("workplace", workplace)] for workplace in workplaces]

    worktypes = [value for value in (filters.get("worktypes") or []) if value]
    if worktypes:
        return [[("worktype", worktype)] for worktype in worktypes]

    countries = []
    seen_countries = set()
    for item in filters.get("locations") or []:
        country = item.get("country")
        if not country or country in seen_countries:
            continue
        seen_countries.add(country)
        countries.append(country)
    if countries:
        return [[("location[0][country]", country)] for country in countries]

    return []


def fetch_workable_jobs_public(api, name):
    """Fetch Workable jobs from public markdown endpoints before touching the throttled JSON API."""
    if api.get("slug") == WORKABLE_PLACEHOLDER_SLUG:
        raise RuntimeError("HTTP 404")

    parser = PARSERS.get("workable")
    markdown = fetch_text(api["url"], method=api.get("method", "GET"), headers=api.get("headers"))
    jobs = parser(markdown, name, api)
    if jobs is not None:
        return jobs

    filters_api = api.get("filters_api")
    if not filters_api:
        return None

    filters = fetch_json(filters_api, headers=api.get("headers"))
    queries = _workable_public_filter_queries(filters)
    if not queries:
        return None

    aggregated = []
    for query_items in queries:
        query = urlencode(query_items)
        filtered_markdown = fetch_text(f"{api['url']}?{query}", method="GET", headers=api.get("headers"))
        filtered_jobs = parser(filtered_markdown, name, api)
        if filtered_jobs is None:
            continue
        aggregated.extend(filtered_jobs)

    aggregated = _dedupe_jobs_by_url(aggregated)
    return aggregated if aggregated else None


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
                try:
                    data = fetch_json(api_url, method="POST", body={"limit": page_size, "offset": offset, "searchText": ""})
                except Exception as e:
                    if "HTTP 400" not in str(e) and "HTTP 410" not in str(e):
                        raise e
                    redirected_api_url = infer_workday_redirect_api(company.get("careers_url", ""))
                    if not redirected_api_url or redirected_api_url == api_url:
                        raise e
                    api_url = redirected_api_url
                    data = fetch_json(api_url, method="POST", body={"limit": page_size, "offset": offset, "searchText": ""})
                total = data.get("total", 0)
                all_jobs.extend(parse_workday(data, name, api_url))
                offset += page_size
            return all_jobs, None
        elif board_type == "oracle":
            all_jobs = []
            page_size = 100
            offset = 0
            total = float("inf")
            parser = PARSERS.get(board_type)
            while offset < total and offset < 5000:
                data = fetch_json(build_oracle_jobs_url(api_url, api, page_size, offset))
                items = data.get("items") or []
                requisitions = (items[0].get("requisitionList") or []) if items else []
                total = (items[0].get("TotalJobsCount") or len(requisitions)) if items else 0
                if not requisitions:
                    break
                all_jobs.extend(parser(data, name, api))
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
                all_jobs.extend(parser(data, name, api))
                offset += page_size
            return all_jobs, None
        elif board_type == "eightfold":
            all_jobs = []
            page_size = 10
            offset = 0
            total = float("inf")
            parser = PARSERS.get(board_type)
            domain = api.get("domain")
            if not domain:
                domain = infer_eightfold_domain(company.get("careers_url", ""))
                if domain:
                    api["domain"] = domain
            try:
                while offset < total and offset < 5000:
                    params = {"query": "", "location": "", "start": offset}
                    if api.get("domain"):
                        params["domain"] = api["domain"]
                    data = fetch_json(f"{api_url}?{urlencode(params)}")
                    total = ((data.get("data") or {}).get("count") or 0)
                    jobs = parser(data, name, api)
                    if not jobs:
                        break
                    all_jobs.extend(jobs)
                    offset += page_size
                    if offset < total:
                        # Eightfold blocks bursty pagination on large boards.
                        time.sleep(EIGHTFOLD_PAGE_DELAY_S)
                return all_jobs, None
            except Exception as e:
                if "HTTP 403" not in str(e):
                    raise e
                data = fetch_eightfold_data_browser(company.get("careers_url", ""), api)
                return parser(data, name, api), None
        elif board_type == "ashby":
            parser = PARSERS.get(board_type)
            html = fetch_text(api_url, method=api.get("method", "GET"), headers=api.get("headers"))
            jobs = parser(html, name, api)
            if jobs is not None:
                return jobs, None

            # Fallback for boards that still expose the older public jobs API.
            fallback_api = api.get("fallback_api")
            if fallback_api:
                data = fetch_json(
                    fallback_api,
                    method=api.get("fallback_method", "GET"),
                    headers=api.get("headers"),
                )
                return parser(data, name, api), None
            return [], "Ashby HTML bootstrap data missing and no fallback API configured"
        elif board_type == "workable":
            try:
                jobs = fetch_workable_jobs_public(api, name)
            except Exception as e:
                if "HTTP 404" in str(e):
                    raise e
                fallback_api = api.get("fallback_api")
                if not fallback_api:
                    raise e
                data = fetch_json(
                    fallback_api,
                    method=api.get("fallback_method", "POST"),
                    body=api.get("fallback_body"),
                    headers=api.get("headers"),
                )
                parser = PARSERS.get(board_type)
                return parser(data, name, api), None

            if jobs is not None:
                return jobs, None

            fallback_api = api.get("fallback_api")
            if fallback_api:
                data = fetch_json(
                    fallback_api,
                    method=api.get("fallback_method", "POST"),
                    body=api.get("fallback_body"),
                    headers=api.get("headers"),
                )
                parser = PARSERS.get(board_type)
                return parser(data, name, api), None
            return [], "Workable markdown feed missing and no fallback API configured"
        elif board_type == "rippling":
            parser = PARSERS.get(board_type)
            html = fetch_text(api_url)
            return parser(html, name, api), None
        elif board_type == "workatastartup":
            parser = PARSERS.get(board_type)
            html = fetch_text(api_url, headers={"Accept": "text/html,application/xhtml+xml"})
            jobs = parser(html, name, api)
            if jobs is None:
                return [], "Work at a Startup bootstrap data missing"
            enrich_workatastartup_posted_at(jobs, api, name)
            return jobs, None
        elif board_type == "applytojob":
            parser = PARSERS.get(board_type)
            html = fetch_text(api_url, headers={"Accept": "text/html,application/xhtml+xml"})
            jobs = parser(html, name, api)
            if jobs is None:
                return [], "ApplyToJob listing bootstrap missing"
            return enrich_applytojob_posted_at(jobs), None
        elif board_type == "icims":
            parser = PARSERS.get(board_type)
            parsed_jobs = []
            for page_html in fetch_icims_listing_pages(api_url):
                parsed_jobs.extend(parser(page_html, name, api))
            parsed_jobs = _dedupe_jobs_by_url(parsed_jobs)
            return enrich_icims_jobs(parsed_jobs), None
        else:
            data = fetch_json(
                api_url,
                method=api.get("method", "GET"),
                body=api.get("body"),
                headers=api.get("headers"),
            )
            parser = PARSERS.get(board_type)
            if not parser:
                return [], f"Unknown board type: {board_type}"
            return parser(data, name, api), None
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

    # Hard wall-clock timeout per company. urlopen's per-socket timeout does not
    # protect against slow-drip servers (a host that trickles bytes slower than the
    # socket timeout keeps the connection alive indefinitely). This caps the total
    # time any single company fetch can block the batch.
    PER_COMPANY_TIMEOUT_S = 90
    POLL_INTERVAL_S = 5

    def _process_jobs(company, jobs, error):
        nonlocal total_found, total_filtered, total_dupes
        if error:
            errors.append({"company": company.get("name", "?"), "error": error})
            return
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

    # Process in chunks so a few hung fetches can't hold all worker slots and
    # starve the rest of the queue. Each chunk gets a fresh pool; abandoned/hung
    # worker threads from a chunk keep running in the background but don't block
    # subsequent chunks.
    CHUNK_SIZE = 50

    def process_batch(batch, max_workers):
        if not batch:
            return
        for i in range(0, len(batch), CHUNK_SIZE):
            _process_chunk(batch[i:i + CHUNK_SIZE], max_workers)

    def _process_chunk(chunk, max_workers):
        pool = ThreadPoolExecutor(max_workers=min(max_workers, len(chunk)))
        try:
            futures = {pool.submit(fetch_company_jobs, c): c for c in chunk}
            start_times = {f: time.monotonic() for f in futures}
            pending = set(futures)
            while pending:
                # Abandon any futures that exceeded the wall-clock cap.
                now = time.monotonic()
                for future in [f for f in pending if now - start_times[f] > PER_COMPANY_TIMEOUT_S]:
                    company = futures[future]
                    errors.append({
                        "company": company.get("name", "?"),
                        "error": f"wall-clock timeout after {PER_COMPANY_TIMEOUT_S}s",
                    })
                    future.cancel()
                    pending.discard(future)
                if not pending:
                    break
                done, pending = futures_wait(
                    pending, timeout=POLL_INTERVAL_S, return_when=FIRST_COMPLETED
                )
                for future in done:
                    company = futures[future]
                    try:
                        jobs, error = future.result(timeout=0.1)
                    except Exception as e:
                        _process_jobs(company, [], f"fetch exception: {e}")
                        continue
                    _process_jobs(company, jobs, error)
        finally:
            # Non-blocking shutdown: don't wait for abandoned/hung worker threads.
            pool.shutdown(wait=False, cancel_futures=True)

    grouped = defaultdict(list)
    for target in targets:
        grouped[target["_api"]["type"]].append(target)

    unrestricted = []
    for board, batch in grouped.items():
        limit = BOARD_CONCURRENCY_LIMITS.get(board)
        if limit is None:
            unrestricted.extend(batch)
        else:
            process_batch(batch, max_workers=min(concurrency, limit))

    process_batch(unrestricted, max_workers=concurrency)

    stats = {
        "total_found": total_found,
        "total_filtered": total_filtered,
        "total_dupes": total_dupes,
    }
    return new_offers, stats, errors

"""
API response parsers for job board platforms.

Supports: Greenhouse, Ashby, Lever, Workday, SmartRecruiters, Workable,
Gem, Eightfold, Rippling.
Each parser takes the raw API JSON response and returns a list of job dicts:
  {"title": str, "url": str, "company": str, "location": str, "posted_at": datetime|None}
"""

import html
import re
from datetime import datetime, timedelta, timezone


def parse_date(value):
    """Parse an ISO date string to a datetime object."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def parse_workday_date(text):
    """Parse Workday's 'Posted Today' / 'Posted Yesterday' / 'Posted 3 Days Ago' / 'Posted 30+ Days Ago' text."""
    if not text:
        return None
    if re.search(r"today", text, re.IGNORECASE):
        return datetime.now(timezone.utc)
    if re.search(r"yesterday", text, re.IGNORECASE):
        # "Yesterday" could be 24-48h ago; use 36h to ensure it's filtered
        # out by a 24h cutoff but passes a 48h (2-day) cutoff
        return datetime.now(timezone.utc) - timedelta(hours=36)
    if re.search(r"30\+\s*days?\s*ago", text, re.IGNORECASE):
        return datetime.now(timezone.utc) - timedelta(days=31)  # Treat as 31 days ago
    match = re.search(r"(\d+)\s*days?\s*ago", text, re.IGNORECASE)
    if match:
        return datetime.now(timezone.utc) - timedelta(days=int(match.group(1)))
    return None


def parse_greenhouse(data, company_name, api=None):
    """Parse Greenhouse API response."""
    jobs = data.get("jobs", [])
    return [
        {
            "title": j.get("title", ""),
            "url": j.get("absolute_url", ""),
            "company": company_name,
            "location": (j.get("location") or {}).get("name", ""),
            "posted_at": parse_date(j.get("first_published")),
        }
        for j in jobs
    ]


def parse_ashby(data, company_name, api=None):
    """Parse Ashby API response."""
    jobs = data.get("jobs", [])
    return [
        {
            "title": j.get("title", ""),
            "url": j.get("jobUrl", ""),
            "company": company_name,
            "location": j.get("location", ""),
            "posted_at": parse_date(j.get("publishedAt")),
        }
        for j in jobs
    ]


def parse_lever(data, company_name, api=None):
    """Parse Lever API response."""
    if not isinstance(data, list):
        return []
    return [
        {
            "title": j.get("text", ""),
            "url": j.get("hostedUrl", ""),
            "company": company_name,
            "location": (j.get("categories") or {}).get("location", ""),
            "posted_at": (
                datetime.fromtimestamp(int(j["createdAt"]) / 1000, tz=timezone.utc)
                if j.get("createdAt")
                else None
            ),
        }
        for j in data
    ]


def parse_workday(data, company_name, base_url):
    """Parse Workday API response."""
    jobs = data.get("jobPostings", [])
    site_url = base_url.replace("/wday/cxs/", "/en-US/").replace("/jobs", "")
    return [
        {
            "title": j.get("title", ""),
            "url": site_url + j.get("externalPath", ""),
            "company": company_name,
            "location": j.get("locationsText", ""),
            "posted_at": parse_workday_date(j.get("postedOn")),
        }
        for j in jobs
    ]


def parse_smartrecruiters(data, company_name, api=None):
    """Parse SmartRecruiters postings response."""
    jobs = data.get("content", [])
    return [
        {
            "title": j.get("name", ""),
            "url": j.get("applyUrl", "") or f"https://jobs.smartrecruiters.com/{(j.get('company') or {}).get('identifier', company_name)}/{j.get('id', '')}",
            "company": company_name,
            "location": ((j.get("location") or {}).get("fullLocation") or ""),
            "posted_at": parse_date(j.get("releasedDate")),
        }
        for j in jobs
    ]


def parse_workable(data, company_name, api=None):
    """Parse Workable jobs response."""
    jobs = data.get("results", [])
    slug = (api or {}).get("slug", "")
    board_url = f"https://apply.workable.com/{slug}" if slug else ""
    parsed = []
    for j in jobs:
        loc = j.get("location") or {}
        locations = j.get("locations") or []
        primary = locations[0] if locations else loc
        location_bits = [
            primary.get("city", ""),
            primary.get("region", ""),
            primary.get("country", ""),
        ]
        location = ", ".join(part for part in location_bits if part)
        if not location and j.get("remote"):
            location = "Remote"
        elif j.get("remote") and "remote" not in location.lower():
            location = f"{location} • Remote" if location else "Remote"

        shortcode = j.get("shortcode", "")
        parsed.append({
            "title": j.get("title", ""),
            "url": f"{board_url}/j/{shortcode}" if board_url and shortcode else "",
            "company": company_name,
            "location": location,
            "posted_at": parse_date(j.get("published")),
        })
    return parsed


def parse_gem(data, company_name, api=None):
    """Parse Gem public GraphQL batch response."""
    if not isinstance(data, list):
        return []

    payload = {}
    for item in data:
        payload.update(item.get("data") or {})

    postings = ((payload.get("oatsExternalJobPostings") or {}).get("jobPostings") or [])
    board_url = (api or {}).get("board_url", "").rstrip("/")
    parsed = []
    for j in postings:
        ext_id = j.get("extId", "")
        job_meta = j.get("job") or {}
        locations = j.get("locations") or []
        loc = locations[0] if locations else {}
        location = loc.get("name", "")
        if job_meta.get("locationType") == "REMOTE" and "remote" not in location.lower():
            location = f"{location} • Remote" if location else "Remote"

        parsed.append({
            "title": j.get("title", ""),
            "url": f"{board_url}/{ext_id}" if board_url and ext_id else "",
            "company": company_name,
            "location": location,
            "posted_at": None,
        })
    return parsed


def parse_eightfold(data, company_name, api=None):
    """Parse Eightfold public search response."""
    payload = (data.get("data") or {})
    positions = payload.get("positions") or []
    base_url = (api or {}).get("base_url", "").rstrip("/")
    domain = (api or {}).get("domain")
    parsed = []
    for j in positions:
        position_url = j.get("positionUrl") or f"/careers/job/{j.get('id', '')}"
        if base_url:
            url = f"{base_url}{position_url}"
            if domain:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}domain={domain}"
        else:
            url = position_url

        posted_at = None
        if j.get("postedTs"):
            posted_at = datetime.fromtimestamp(int(j["postedTs"]), tz=timezone.utc)

        parsed.append({
            "title": j.get("name", ""),
            "url": url,
            "company": company_name,
            "location": " | ".join(j.get("locations") or []),
            "posted_at": posted_at,
        })
    return parsed


def parse_rippling(data, company_name, api=None):
    """Parse Rippling public job board HTML."""
    if not isinstance(data, str):
        return []

    base_url = (api or {}).get("base_url", "https://ats.rippling.com").rstrip("/")
    jobs = {}
    for href, inner in re.findall(
        r'<a[^>]+href="(/[^"]+/jobs/[0-9a-f-]{36})"[^>]*>(.*?)</a>',
        data,
        re.IGNORECASE | re.DOTALL,
    ):
        title = re.sub(r"<[^>]+>", " ", inner)
        title = html.unescape(title)
        title = re.sub(r"\s+", " ", title).strip()
        if not title or title.lower() == "view job":
            continue
        jobs.setdefault(href, title)

    return [
        {
            "title": title,
            "url": f"{base_url}{href}",
            "company": company_name,
            "location": "",
            "posted_at": None,
        }
        for href, title in jobs.items()
    ]


PARSERS = {
    "greenhouse": parse_greenhouse,
    "ashby": parse_ashby,
    "lever": parse_lever,
    "smartrecruiters": parse_smartrecruiters,
    "workable": parse_workable,
    "gem": parse_gem,
    "eightfold": parse_eightfold,
    "rippling": parse_rippling,
}

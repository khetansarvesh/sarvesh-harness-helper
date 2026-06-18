"""
API response parsers for job board platforms.

Supports: Greenhouse, Ashby, Lever, Workday, SmartRecruiters.
Each parser takes the raw API JSON response and returns a list of job dicts:
  {"title": str, "url": str, "company": str, "location": str, "posted_at": datetime|None}
"""

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
    """Parse Workday's 'Posted Today' / 'Posted 3 Days Ago' text."""
    if not text:
        return None
    if re.search(r"today", text, re.IGNORECASE):
        return datetime.now(timezone.utc)
    match = re.search(r"(\d+)\s*days?\s*ago", text, re.IGNORECASE)
    if match:
        return datetime.now(timezone.utc) - timedelta(days=int(match.group(1)))
    return None


def parse_greenhouse(data, company_name):
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


def parse_ashby(data, company_name):
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


def parse_lever(data, company_name):
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


def parse_smartrecruiters(data, company_name):
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


PARSERS = {
    "greenhouse": parse_greenhouse,
    "ashby": parse_ashby,
    "lever": parse_lever,
    "smartrecruiters": parse_smartrecruiters,
}

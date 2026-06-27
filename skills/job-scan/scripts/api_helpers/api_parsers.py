"""
API response parsers for job board platforms.

Supports: Greenhouse, Ashby, Lever, Workday, SmartRecruiters, Workable,
Gem, Eightfold, Rippling, Work at a Startup, ApplyToJob, iCIMS.
Each parser takes the raw API JSON response and returns a list of job dicts:
  {"title": str, "url": str, "company": str, "location": str, "posted_at": datetime|None}
"""

import html
import json
import re
from datetime import datetime, timedelta, timezone


def parse_date(value):
    """Parse an ISO date string to a datetime object."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
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


def parse_relative_age_text(text):
    """Parse relative age strings like '5 minutes ago' or 'about 2 months ago'."""
    if not text:
        return None

    now = datetime.now(timezone.utc)
    lowered = text.strip().lower()
    if lowered in {"today", "just now"}:
        return now
    if lowered == "yesterday":
        return now - timedelta(hours=36)

    match = re.search(
        r"(?:about\s+)?(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago",
        lowered,
        re.IGNORECASE,
    )
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "minute":
        return now - timedelta(minutes=value)
    if unit == "hour":
        return now - timedelta(hours=value)
    if unit == "day":
        return now - timedelta(days=value)
    if unit == "week":
        return now - timedelta(weeks=value)
    if unit == "month":
        return now - timedelta(days=value * 30)
    if unit == "year":
        return now - timedelta(days=value * 365)
    return None


def parse_applytojob_date(text):
    """Parse ApplyToJob ISO date strings."""
    return parse_date(text)


def parse_icims_date(text):
    """Parse iCIMS ISO date strings."""
    return parse_date(text)


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
    # Current Ashby hosted board HTML embeds the full job list in window.__appData.
    if isinstance(data, str):
        slug = (api or {}).get("slug", "").strip()
        marker = "window.__appData = "
        start = data.find(marker)
        if start == -1:
            return None

        payload_start = start + len(marker)
        in_string = False
        escape = False
        depth = 0
        payload_end = None
        for idx, ch in enumerate(data[payload_start:], start=payload_start):
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    payload_end = idx + 1
                    break

        if payload_end is None:
            return None

        try:
            app_data = json.loads(data[payload_start:payload_end])
        except json.JSONDecodeError:
            return None

        postings = ((app_data.get("jobBoard") or {}).get("jobPostings") or [])
        out = []
        for j in postings:
            job_id = j.get("id", "")
            secondary = [loc.get("locationName", "") for loc in j.get("secondaryLocations") or [] if loc.get("locationName")]
            location_parts = [j.get("locationName", "")] + secondary
            location = " | ".join(part for part in location_parts if part)
            out.append({
                "title": j.get("title", ""),
                "url": f"https://jobs.ashbyhq.com/{slug}/{job_id}" if slug and job_id else "",
                "company": company_name,
                "location": location,
                "posted_at": parse_date(j.get("publishedDate")),
            })
        return out

    # Legacy Ashby endpoint shape:
    #   {"jobs":[{"title","jobUrl","location","publishedAt"}]}
    if "jobs" in data:
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

    # Current hosted-board GraphQL shape:
    #   {"data":{"jobBoard":{"jobPostings":[...]}}}
    slug = (api or {}).get("slug", "").strip()
    postings = ((data.get("data") or {}).get("jobBoard") or {}).get("jobPostings") or []
    out = []
    for j in postings:
        job_id = j.get("id", "")
        secondary = [loc.get("locationName", "") for loc in j.get("secondaryLocations") or [] if loc.get("locationName")]
        location_parts = [j.get("locationName", "")] + secondary
        location = " | ".join(part for part in location_parts if part)
        out.append({
            "title": j.get("title", ""),
            "url": f"https://jobs.ashbyhq.com/{slug}/{job_id}" if slug and job_id else "",
            "company": company_name,
            "location": location,
            "posted_at": None,
        })
    return out


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
    parsed = []
    for j in jobs:
        title = j.get("title", "")
        external_path = j.get("externalPath", "")
        # Some Workday payloads include board-root artifacts that are not jobs.
        if not title or "/job/" not in external_path:
            continue
        parsed.append({
            "title": title,
            "url": site_url + external_path,
            "company": company_name,
            "location": j.get("locationsText", ""),
            "posted_at": parse_workday_date(j.get("postedOn")),
        })
    return parsed


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


def parse_oracle(data, company_name, api=None):
    """Parse Oracle Recruiting candidate-experience jobs response."""
    items = data.get("items") or []
    if not items:
        return []
    requisitions = (items[0].get("requisitionList") or [])
    board_url = (api or {}).get("board_url", "").rstrip("/")
    parsed = []
    for j in requisitions:
        req_id = j.get("Id", "")
        location = j.get("PrimaryLocation", "") or ""
        workplace_type = j.get("WorkplaceType", "") or ""
        if workplace_type and workplace_type.lower() not in location.lower():
            location = f"{location} ({workplace_type})" if location else workplace_type
        parsed.append({
            "title": j.get("Title", ""),
            "url": f"{board_url}/job/{req_id}" if board_url and req_id else "",
            "company": company_name,
            "location": location,
            "posted_at": parse_date(j.get("PostedDate")),
        })
    return parsed


def parse_workable(data, company_name, api=None):
    """Parse Workable jobs response."""
    if isinstance(data, str):
        board_url = (api or {}).get("board_url", "").rstrip("/")
        lines = data.splitlines()
        rows = []
        table_header = "| Title | Department | Location | Type | Salary | Posted | Details |"
        table_started = False

        for line in lines:
            if line.strip() == table_header:
                table_started = True
                continue
            if table_started and line.startswith("|---"):
                continue
            if table_started and line.startswith("|"):
                rows.append(line)

        # Public markdown feeds with no rows are valid and mean no openings.
        if table_started and not rows:
            return []
        if not table_started:
            return None

        parsed = []
        for row in rows:
            cols = [part.strip() for part in row.strip().strip("|").split("|")]
            if len(cols) < 7:
                continue
            if len(cols) > 7:
                title = " | ".join(cols[: len(cols) - 6]).strip()
                _department, location, _job_type, _salary, posted, details = cols[len(cols) - 6 :]
            else:
                title, _department, location, _job_type, _salary, posted, details = cols
            match = re.search(r"/jobs/view/([A-Z0-9]+)\.md", details)
            shortcode = match.group(1) if match else ""
            parsed.append({
                "title": title,
                "url": f"{board_url}/j/{shortcode}" if board_url and shortcode else "",
                "company": company_name,
                "location": location,
                "posted_at": parse_date(posted),
            })
        return parsed

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


def parse_workatastartup(data, company_name, api=None):
    """Parse Work at a Startup public company/job page HTML."""
    if not isinstance(data, str):
        return []

    match = re.search(r'data-page="([^"]+)"', data, re.IGNORECASE | re.DOTALL)
    if not match:
        return None

    try:
        payload = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError:
        return None

    props = payload.get("props") or {}
    company = props.get("company") or {}
    jobs = company.get("jobs") or []
    base_url = (api or {}).get("base_url", "https://www.workatastartup.com").rstrip("/")

    return [
        {
            "job_id": job.get("id"),
            "title": job.get("title", ""),
            "url": f"{base_url}/jobs/{job.get('id', '')}" if job.get("id") else "",
            "company": company_name,
            "location": job.get("location", ""),
            "posted_at": None,
        }
        for job in jobs
    ]


def parse_applytojob(data, company_name, api=None):
    """Parse ApplyToJob listing page HTML."""
    if not isinstance(data, str):
        return []

    jobs = []
    seen = set()
    list_items = re.findall(
        r"<li[^>]*class=\"list-group-item\"[^>]*>(.*?)</li>",
        data,
        re.IGNORECASE | re.DOTALL,
    )
    anchor_re = re.compile(
        r"<a[^>]+href=\"(https://[^\"']+?/apply/[A-Za-z0-9]+/[^\"']+)\"[^>]*>\s*(.*?)\s*</a>",
        re.IGNORECASE | re.DOTALL,
    )
    location_re = re.compile(
        r"fa-map-marker[^>]*></i>\s*([^<]+)",
        re.IGNORECASE | re.DOTALL,
    )

    for block in list_items:
        match = anchor_re.search(block)
        if not match:
            continue
        url = html.unescape(match.group(1)).strip()
        if url in seen:
            continue
        seen.add(url)
        title = re.sub(r"<[^>]+>", " ", match.group(2))
        title = html.unescape(title)
        title = re.sub(r"\s+", " ", title).strip()
        location_match = location_re.search(block)
        location = ""
        if location_match:
            location = html.unescape(location_match.group(1))
            location = re.sub(r"\s+", " ", location).strip()
        jobs.append({
            "title": title,
            "url": url,
            "company": company_name,
            "location": location,
            "posted_at": None,
        })

    if jobs:
        return jobs

    fallback_urls = re.findall(
        r"https://[^\"']+?/apply/[A-Za-z0-9]+/[^\"'\s<>]+",
        data,
        re.IGNORECASE,
    )
    for url in fallback_urls:
        clean_url = html.unescape(url).strip()
        if clean_url in seen:
            continue
        seen.add(clean_url)
        jobs.append({
            "title": "",
            "url": clean_url,
            "company": company_name,
            "location": "",
            "posted_at": None,
        })
    return jobs


def parse_icims(data, company_name, api=None):
    """Parse iCIMS iframe listing HTML."""
    if not isinstance(data, str):
        return []

    jobs = []
    seen = set()
    anchor_re = re.compile(
        r'<a[^>]+href="(https://[^"]+/jobs/\d+/[^"]+/job(?:\?in_iframe=1)?)"[^>]*title="(\d+\s*-\s*[^"]+)"',
        re.IGNORECASE,
    )

    for url, title_attr in anchor_re.findall(data):
        clean_url = html.unescape(url).replace("?in_iframe=1", "").strip()
        if clean_url in seen:
            continue
        seen.add(clean_url)
        title = re.sub(r"^\d+\s*-\s*", "", html.unescape(title_attr)).strip()
        jobs.append({
            "title": title,
            "url": clean_url,
            "company": company_name,
            "location": "",
            "posted_at": None,
        })
    return jobs


PARSERS = {
    "greenhouse": parse_greenhouse,
    "ashby": parse_ashby,
    "lever": parse_lever,
    "oracle": parse_oracle,
    "smartrecruiters": parse_smartrecruiters,
    "workable": parse_workable,
    "gem": parse_gem,
    "eightfold": parse_eightfold,
    "rippling": parse_rippling,
    "workatastartup": parse_workatastartup,
    "applytojob": parse_applytojob,
    "icims": parse_icims,
}

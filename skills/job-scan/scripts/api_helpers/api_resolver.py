#!/usr/bin/env python3
"""
Resolve a careers page URL to its public API endpoint.

Supports public APIs for Greenhouse, Ashby, Lever, Workday, SmartRecruiters,
Workable, Gem, Eightfold, Rippling, Work at a Startup, ApplyToJob, and iCIMS.

Usage:
  python3 api_resolver.py https://jobs.ashbyhq.com/cohere
  python3 api_resolver.py https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
  python3 api_resolver.py --batch urls.txt
"""

import json
import re
import sys
import urllib.request
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse


ORACLE_FACETS = "LOCATIONS;WORK_LOCATIONS;WORKPLACE_TYPES;TITLES;CATEGORIES;ORGANIZATIONS;POSTING_DATES;FLEX_FIELDS"
ORACLE_EXPAND = "requisitionList.workLocation,requisitionList.otherWorkLocations,requisitionList.secondaryLocations,flexFieldsFacet.values,requisitionList.requisitionFlexFields"


def fetch_text(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def infer_oracle_site_meta(url):
    """Extract Oracle Recruiting site metadata from the hosted jobs page."""
    html = fetch_text(url)
    base_tag = re.search(r"<base[^>]+>", html, re.IGNORECASE)
    if not base_tag:
        return None

    tag = base_tag.group(0)
    href_match = re.search(r'href="([^"]+)"', tag, re.IGNORECASE)
    api_base_match = re.search(r'data-apibaseurl="([^"]+)"', tag, re.IGNORECASE)
    site_number_match = re.search(r'data-sitenumber="([^"]+)"', tag, re.IGNORECASE)
    if not href_match or not api_base_match or not site_number_match:
        return None

    parsed = urlparse(url)
    board_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", href_match.group(1)).rstrip("/")
    return {
        "api_base": api_base_match.group(1).rstrip("/"),
        "site_number": site_number_match.group(1),
        "board_url": board_url,
    }


def infer_redirected_jobs_url(url):
    """Detect careers pages that now delegate to a different hosted jobs board."""
    try:
        html = fetch_text(url)
    except Exception:
        return None
    oracle_match = re.search(r'data-search_href_location="(https://[^"]+/sites/[^"]+/jobs)"', html, re.IGNORECASE)
    if oracle_match:
        return oracle_match.group(1)
    oracle_match = re.search(r"https://[^\"']+/sites/[^\"']+/jobs", html, re.IGNORECASE)
    if oracle_match:
        return oracle_match.group(0)
    return None


# ── Function 1: Identify the job board ──────────────────────────────

def identify_board(url):
    """Identify which job board a careers URL belongs to."""
    if re.search(r"jobs\.ashbyhq\.com", url):
        return "ashby"
    if re.search(r"jobs\.lever\.co", url):
        return "lever"
    if re.search(r"(?:job-boards(?:\.eu)?|boards)\.greenhouse\.io", url):
        return "greenhouse"
    if re.search(r"careers\.smartrecruiters\.com", url, re.IGNORECASE):
        return "smartrecruiters"
    if re.search(r"apply\.workable\.com", url, re.IGNORECASE):
        return "workable"
    if re.search(r"jobs\.gem\.com", url, re.IGNORECASE):
        return "gem"
    if re.search(r"ats\.rippling\.com", url, re.IGNORECASE):
        return "rippling"
    if re.search(r"workatastartup\.com/(?:companies/[^/?#]+|jobs/\d+)", url, re.IGNORECASE):
        return "workatastartup"
    if re.search(r"applytojob\.com/apply(?:[/?#]|$)", url, re.IGNORECASE):
        return "applytojob"
    if re.search(r"\.icims\.com(?:[/?#]|$)", url, re.IGNORECASE):
        return "icims"
    if re.search(r"/sites/[^/?#]+/(?:jobs|job(?:/|$))", url, re.IGNORECASE):
        return "oracle"
    if re.search(r"(?:^https?://)?[^/]*eightfold\.ai", url, re.IGNORECASE) or (
        re.search(r"/careers(?:[/?#]|$)", url, re.IGNORECASE)
        and re.search(r"[?&]domain=[^&#]+", url, re.IGNORECASE)
    ):
        return "eightfold"
    if re.search(r"\.wd\d+\.myworkdayjobs\.com", url):
        return "workday"
    return "unknown"


# ── Function 2: Extract slug(s) from the URL ────────────────────────

def extract_slug(url, board):
    """Extract the slug or identifiers from a careers URL."""
    if board == "ashby":
        match = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)", url)
        return unquote(match.group(1)) if match else None

    if board == "lever":
        match = re.search(r"jobs\.lever\.co/([^/?#]+)", url)
        return match.group(1) if match else None

    if board == "greenhouse":
        match = re.search(r"[?&]for=([^&#]+)", url)
        if match:
            return match.group(1)
        match = re.search(r"(?:job-boards(?:\.eu)?|boards)\.greenhouse\.io/([^/?#]+)", url)
        return match.group(1) if match else None

    if board == "smartrecruiters":
        match = re.search(r"careers\.smartrecruiters\.com/([^/?#]+)", url, re.IGNORECASE)
        return match.group(1) if match else None

    if board == "workable":
        match = re.search(r"apply\.workable\.com/([^/?#]+)", url, re.IGNORECASE)
        return match.group(1) if match else None

    if board == "gem":
        match = re.search(r"jobs\.gem\.com/([^/?#]+)", url, re.IGNORECASE)
        return match.group(1) if match else None

    if board == "rippling":
        match = re.search(r"ats\.rippling\.com/([^/?#]+)/jobs", url, re.IGNORECASE)
        return match.group(1) if match else None

    if board == "workatastartup":
        company_match = re.search(r"workatastartup\.com/companies/([^/?#]+)", url, re.IGNORECASE)
        if company_match:
            return {
                "kind": "company",
                "slug": company_match.group(1),
                "url": f"https://www.workatastartup.com/companies/{company_match.group(1)}",
            }
        job_match = re.search(r"workatastartup\.com/jobs/(\d+)", url, re.IGNORECASE)
        if job_match:
            return {
                "kind": "job",
                "job_id": job_match.group(1),
                "url": f"https://www.workatastartup.com/jobs/{job_match.group(1)}",
            }
        return None

    if board == "applytojob":
        listing_match = re.search(r"(https?://[^/?#]+\.applytojob\.com/apply)(?:[/?#].*)?$", url, re.IGNORECASE)
        if listing_match:
            return {
                "base_url": f"https://{urlparse(listing_match.group(1)).netloc}",
                "listing_url": listing_match.group(1).rstrip("/"),
            }
        return None

    if board == "icims":
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        return {
            "base_url": base_url,
            "listing_url": f"{base_url}/jobs/search?ss=1&in_iframe=1",
        }

    if board == "oracle":
        return infer_oracle_site_meta(url)

    if board == "eightfold":
        parsed = urlparse(url)
        domain = parse_qs(parsed.query).get("domain", [None])[0]
        return {
            "base_url": f"{parsed.scheme}://{parsed.netloc}",
            "domain": domain,
        }

    if board == "workday":
        match = re.search(
            r"([^/.]+)\.(wd\d+)\.myworkdayjobs\.com/(?:en-US/)?([^/?#]+)", url
        )
        if match:
            return {
                "company": match.group(1),
                "wd": match.group(2),
                "site": match.group(3),
            }
        return None

    return None


# ── Function 3: Build the API endpoint ──────────────────────────────

def build_api(board, slug):
    """Build the public API endpoint from board type and slug."""
    if board == "ashby" and slug:
        return {
            "api": f"https://jobs.ashbyhq.com/{quote(slug, safe='')}",
            "method": "GET",
            "slug": slug,
            "fallback_api": f"https://api.ashbyhq.com/posting-api/job-board/{quote(slug, safe='')}",
            "fallback_method": "GET",
        }

    if board == "lever" and slug:
        return {
            "api": f"https://api.lever.co/v0/postings/{slug}",
            "method": "GET",
        }

    if board == "greenhouse" and slug:
        return {
            "api": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            "method": "GET",
        }

    if board == "workday" and slug:
        company = slug["company"]
        wd = slug["wd"]
        site = slug["site"]
        return {
            "api": f"https://{company}.{wd}.myworkdayjobs.com/wday/cxs/{company}/{site}/jobs",
            "method": "POST",
        }

    if board == "smartrecruiters" and slug:
        return {
            "api": f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
            "method": "GET",
        }

    if board == "workable" and slug:
        return {
            "api": f"https://apply.workable.com/{slug}/jobs.md",
            "method": "GET",
            "slug": slug,
            "board_url": f"https://apply.workable.com/{slug}",
            "filters_api": f"https://apply.workable.com/api/v3/accounts/{slug}/jobs/filters",
            "fallback_api": f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
            "fallback_method": "POST",
            "fallback_body": {
                "query": "",
                "department": [],
                "location": [],
                "workplace": [],
                "worktype": [],
            },
        }

    if board == "oracle" and slug:
        return {
            "api": f"{slug['api_base']}/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
            "method": "GET",
            "site_number": slug["site_number"],
            "board_url": slug["board_url"],
            "expand": ORACLE_EXPAND,
            "facets": ORACLE_FACETS,
        }

    if board == "gem" and slug:
        return {
            "api": "https://jobs.gem.com/api/public/graphql/batch",
            "method": "POST",
            "slug": slug,
            "board_url": f"https://jobs.gem.com/{slug}",
            "body": [
                {
                    "operationName": "JobBoardTheme",
                    "variables": {"boardId": slug},
                    "query": (
                        "query JobBoardTheme($boardId: String!) {"
                        " publicBrandingTheme(externalId: $boardId) {"
                        " id theme __typename } }"
                    ),
                },
                {
                    "operationName": "JobBoardList",
                    "variables": {"boardId": slug},
                    "query": (
                        "query JobBoardList($boardId: String!) {"
                        " oatsExternalJobPostings(boardId: $boardId) {"
                        " jobPostings {"
                        " id extId title"
                        " locations { id name city isoCountry isRemote extId __typename }"
                        " job {"
                        " id department { id name extId __typename }"
                        " locationType employmentType __typename }"
                        " __typename } __typename }"
                        " oatsExternalJobPostingsFilters(boardId: $boardId) {"
                        " type displayName rawValue value count __typename }"
                        " jobBoardExternal(vanityUrlPath: $boardId) {"
                        " id teamDisplayName descriptionHtml pageTitle __typename }"
                        " }"
                    ),
                },
            ],
        }

    if board == "eightfold" and slug:
        return {
            "api": f"{slug['base_url']}/api/pcsx/search",
            "method": "GET",
            "base_url": slug["base_url"],
            "domain": slug["domain"],
        }

    if board == "rippling" and slug:
        return {
            "api": f"https://ats.rippling.com/{slug}/jobs",
            "method": "GET",
            "slug": slug,
            "base_url": "https://ats.rippling.com",
        }

    if board == "workatastartup" and slug:
        return {
            "api": slug["url"],
            "method": "GET",
            "slug": slug,
            "base_url": "https://www.workatastartup.com",
        }

    if board == "applytojob" and slug:
        return {
            "api": slug["listing_url"],
            "method": "GET",
            "slug": slug,
            "base_url": slug["base_url"],
        }

    if board == "icims" and slug:
        return {
            "api": slug["listing_url"],
            "method": "GET",
            "slug": slug,
            "base_url": slug["base_url"],
        }

    return {"api": None, "method": None}


# ── Main: resolve a URL end-to-end ──────────────────────────────────

def resolve(url):
    """Resolve a careers URL to its API endpoint."""
    url = url.strip()
    board = identify_board(url)
    if board == "eightfold":
        slug = extract_slug(url, board)
        if not slug or not slug.get("domain"):
            redirected_jobs_url = infer_redirected_jobs_url(url)
            if redirected_jobs_url:
                url = redirected_jobs_url
                board = identify_board(url)
    slug = extract_slug(url, board)
    api_info = build_api(board, slug)

    return {
        "url": url,
        "board": board,
        "slug": slug,
        **api_info,
    }


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage: python3 api_resolver.py <url>", file=sys.stderr)
        print("       python3 api_resolver.py --batch urls.txt", file=sys.stderr)
        sys.exit(1)

    if args[0] == "--batch":
        with open(args[1], "r") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        results = [resolve(url) for url in urls]
        print(json.dumps(results, indent=2))
    else:
        result = resolve(args[0])
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

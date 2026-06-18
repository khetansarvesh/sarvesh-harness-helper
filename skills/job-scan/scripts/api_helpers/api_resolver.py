#!/usr/bin/env python3
"""
Resolve a careers page URL to its public API endpoint.

Supports public APIs for Greenhouse, Ashby, Lever, Workday, SmartRecruiters,
Workable, Gem, Eightfold, and Rippling.

Usage:
  python3 api_resolver.py https://jobs.ashbyhq.com/cohere
  python3 api_resolver.py https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
  python3 api_resolver.py --batch urls.txt
"""

import json
import re
import sys
from urllib.parse import parse_qs, urlparse


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
        return match.group(1) if match else None

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
            "api": f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            "method": "GET",
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
            "api": f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
            "method": "POST",
            "slug": slug,
            "body": {
                "query": "",
                "department": [],
                "location": [],
                "workplace": [],
                "worktype": [],
            },
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

    return {"api": None, "method": None}


# ── Main: resolve a URL end-to-end ──────────────────────────────────

def resolve(url):
    """Resolve a careers URL to its API endpoint."""
    url = url.strip()
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

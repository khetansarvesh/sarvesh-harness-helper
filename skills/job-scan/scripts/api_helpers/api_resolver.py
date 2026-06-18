#!/usr/bin/env python3
"""
Resolve a careers page URL to its public API endpoint.

Supports public APIs for Greenhouse, Ashby, Lever, Workday, and SmartRecruiters.

Usage:
  python3 api_resolver.py https://jobs.ashbyhq.com/cohere
  python3 api_resolver.py https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
  python3 api_resolver.py --batch urls.txt
"""

import json
import re
import sys


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

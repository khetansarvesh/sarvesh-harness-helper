#!/usr/bin/env python3
"""
Shared helpers for matching candidate URLs to ATS jobs.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def extract_job_key(url: str, board: str):
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
    if board == "oracle":
        match = re.search(r"/(?:preview|job)/(\d+)$", path, re.IGNORECASE)
        return match.group(1) if match else None
    if board == "icims":
        match = re.search(r"/jobs/(\d+)", path, re.IGNORECASE)
        return match.group(1) if match else None
    if board == "workday":
        return path
    return None


def slug_group_key(slug):
    return json.dumps(slug, sort_keys=True, default=str)


def match_job(candidate_url: str, board: str, jobs: list[dict]) -> dict | None:
    target_norm = normalize_url(candidate_url)
    target_key = extract_job_key(candidate_url, board)

    for job in jobs:
        if normalize_url(job.get("url", "")) == target_norm:
            return job

    if target_key:
        for job in jobs:
            if extract_job_key(job.get("url", ""), board) == target_key:
                return job

    target_path = urlsplit(target_norm).path
    for job in jobs:
        if urlsplit(normalize_url(job.get("url", ""))).path == target_path:
            return job
    return None

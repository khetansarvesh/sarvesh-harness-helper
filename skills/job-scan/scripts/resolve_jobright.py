#!/usr/bin/env python3
"""
Process Jobright.ai job data and append to candidate_store.

Reads extracted Jobright job data (with pre-resolved ATS URLs from the agent's
browser-based resolution) and appends candidates to candidate_store.json.

The agent extracts jobs from the Jobright tab via Chrome DevTools MCP and resolves
real ATS URLs in-browser (where session cookies are available). This script just
normalizes the data and appends to the candidate store.

Usage:
  python3 resolve_jobright.py                          # uses default paths
  python3 resolve_jobright.py --raw /path/to/raw.json  # custom raw input
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.join(SCRIPT_DIR, "..")
DEFAULT_RAW = os.path.join(SKILL_DIR, "jobright_raw.json")
CANDIDATE_STORE = os.path.join(SKILL_DIR, "candidate_store.json")


def normalize_candidates(raw_jobs: list[dict]) -> list[dict]:
    """Convert raw Jobright jobs to candidate_store format.

    Each raw job should have: title, company, url (real ATS URL or Jobright fallback),
    location, and optionally jobrightUrl.
    """
    candidates: list[dict] = []
    for job in raw_jobs:
        url = job.get("url") or job.get("jobrightUrl", "")
        candidates.append({
            "company": job.get("company", ""),
            "role": job.get("title", ""),
            "url": url,
            "location": job.get("location", ""),
            "source": "jobright",
        })
    return candidates


def append_to_candidate_store(candidates: list[dict], store_path: str = CANDIDATE_STORE) -> None:
    """Append resolved candidates to candidate_store.json."""
    existing: list[dict] = []
    if os.path.exists(store_path):
        with open(store_path) as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = []

    existing.extend(candidates)
    with open(store_path, "w") as f:
        json.dump(existing, f, indent=2)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Process Jobright jobs into candidate store")
    parser.add_argument("--raw", default=DEFAULT_RAW, help="Path to jobright_raw.json")
    parser.add_argument("--store", default=CANDIDATE_STORE, help="Path to candidate_store.json")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing")
    args = parser.parse_args()

    if not os.path.exists(args.raw):
        print(f"Error: {args.raw} not found. Run Jobright extraction first.", file=sys.stderr)
        sys.exit(1)

    with open(args.raw) as f:
        raw_jobs = json.load(f)

    if not raw_jobs:
        print("Jobright: 0 jobs in raw file, nothing to process.")
        return

    candidates = normalize_candidates(raw_jobs)

    # Count stats
    ats_resolved = sum(1 for c in candidates if "jobright.ai" not in c["url"])
    fallback = len(candidates) - ats_resolved

    for c in candidates:
        tag = "✓" if "jobright.ai" not in c["url"] else "⚠"
        print(f"  {tag} {c['company']} | {c['role']} → {c['url']}")

    print(f"\nJobright: {len(candidates)} jobs processed, {ats_resolved} resolved to ATS URLs, {fallback} fallback")

    if not args.dry_run:
        append_to_candidate_store(candidates, args.store)
        print(f"  Appended to {args.store}")

        # Clean up raw file
        os.remove(args.raw)
        print(f"  Cleaned up {args.raw}")


if __name__ == "__main__":
    main()

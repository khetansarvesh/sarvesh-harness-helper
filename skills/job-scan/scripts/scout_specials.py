#!/usr/bin/env python3
"""
scout_specials.py — Portal scanner orchestrator.

Loads companies from Notion, resolves their ATS APIs, fetches job listings,
applies hours filter (default: 24h), and writes candidates to candidate_store.json.
Title filtering, dedup, liveness, and upload happen later in dedup_liveness_upload.py.

Usage:
  python3 scout_specials.py                              # scan Dream + Big-Tech companies
  python3 scout_specials.py --category Startup           # scan Startups only
  python3 scout_specials.py --company cohere --dry-run   # preview single company
  python3 scout_specials.py --hours 24                   # only jobs posted in last 24 hours
"""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", "..", ".."))
from scripts.notion.db_companies import load_companies
from api_helpers.api_job_fetcher import fetch_and_filter
from api_helpers.api_resolver import resolve

# ── Config ──────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.join(SCRIPT_DIR, "..")

CANDIDATE_STORE = os.path.join(SKILL_DIR, "candidate_store.json")

# ── API resolution (via api_resolver.resolve) ───────────────────────

def resolve_apis(companies):
    """Resolve careers URLs to API endpoints."""
    out = []
    for company in companies:
        r = resolve(company.get("careers_url", ""))
        if r["board"] == "unknown":
            out.append({**company, "_api": None})
        else:
            api_meta = {"type": r["board"], "url": r["api"], "method": r["method"]}
            for key in ("slug", "body", "headers", "base_url", "domain", "board_url", "site_number", "expand", "facets", "filters_api", "fallback_api", "fallback_method", "fallback_body"):
                if r.get(key) is not None:
                    api_meta[key] = r[key]
            out.append({**company, "_api": api_meta})
    return out


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scan ATS portals for job listings.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--company", default=None, help="Scan only this company (substring match)")
    parser.add_argument("--hours", type=int, default=24, help="Only jobs posted in the last N hours (default: 24)")
    # Default: scan ALL companies in the Notion Companies DB (no category filter).
    # To restrict to specific categories, pass --category Dream Big-Tech etc.
    # parser.add_argument("--category", nargs="+", default=["Dream", "Big-Tech"],
    #                     help="Notion company categories to scan (default: Dream Big-Tech)")
    parser.add_argument("--category", nargs="+", default=None,
                        help="Notion company categories to scan (default: ALL companies)")
    args = parser.parse_args()

    # 1. Load companies from Notion
    companies = load_companies(args.category)
    print(f"  Found {len(companies)} companies with careers pages")

    # 2. Get APIs
    enabled = companies
    if args.company:
        enabled = [c for c in enabled if args.company.lower() in c.get("name", "").lower()]
    resolved = resolve_apis(enabled)
    targets = [c for c in resolved if c["_api"] is not None]
    skipped_companies = [c for c in resolved if c["_api"] is None]
    print(f"Scanning {len(targets)} companies via API ({len(skipped_companies)} skipped — no API detected)")

    if skipped_companies:
        print(f"\nCompanies needing WebSearch fallback:")
        for c in skipped_companies:
            print(f"  → {c['name']} | {c.get('careers_url', 'no URL')}")
        print()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours) if args.hours > 0 else None

    # 3. Fetch all jobs (no title filter here only time filter)
    new_offers, stats, errors = fetch_and_filter(targets, lambda title: True, cutoff)

    # 5. Write candidates to store
    if not args.dry_run and new_offers:
        with open(CANDIDATE_STORE, "w") as f:
            json.dump(new_offers, f, indent=2)
        print(f"  Written {len(new_offers)} candidates to {CANDIDATE_STORE}")

    # 6. Print summary
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'━' * 45}")
    print(f"Portal Scan — {today}")
    print(f"{'━' * 45}")
    print(f"Companies scanned:     {len(targets)}")
    print(f"Total jobs found:      {stats['total_found']}")
    print(f"Filtered:              {stats['total_filtered']} removed")
    print(f"Intra-scan dupes:      {stats['total_dupes']} skipped")
    print(f"New offers added:      {len(new_offers)}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e['company']}: {e['error']}")

    if new_offers:
        print("\nNew offers:")
        for o in new_offers:
            print(f"  + {o['company']} | {o['role']}")
        if args.dry_run:
            print("\n(dry run — run without --dry-run to save results)")
        else:
            print(f"\nCandidates saved to {CANDIDATE_STORE}")
            print(f"Run: python3 skills/job-scan/scripts/dedup_liveness_upload.py {CANDIDATE_STORE}")

    print(f"\n→ Next: dedup_liveness_upload.py to push to Notion, then job-eval to evaluate.")


if __name__ == "__main__":
    main()

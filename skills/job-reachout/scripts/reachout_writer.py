#!/usr/bin/env python3
"""
Reachout Writer — Notion I/O for the job-reachout skill.

Queries the Applications DB for jobs in 'Evaluated' or 'Almost Applied' status,
checks whether a page already has a Reachout section, and appends a new
Reachout section (header + date + markdown body) to a page's body.

Usage:
  python3 reachout_writer.py query
  python3 reachout_writer.py has-reachout --page-id PAGE_ID
  python3 reachout_writer.py write --page-id PAGE_ID --report-file /tmp/reachout.md

The 'write' command appends blocks; it does NOT delete existing Reachout
sections (re-runs produce a new dated section, preserving history).
"""

import argparse
import json
import os
import sys
from datetime import date

from sarvesh_ai_notion_interface.notion_client import notion_request, load_all_rows
from sarvesh_ai_notion_interface.config import NOTION_TOKEN, NOTION_DB_APPLICATIONS
from sarvesh_ai_notion_interface.db_applications import markdown_to_notion_blocks, append_blocks_to_page


REACHOUT_STATUSES = ["Evaluated", "Almost Applied"]
REACHOUT_HEADER = "Reachout"


# ── Query candidates ────────────────────────────────────────────────

def query_reachout_candidates():
    """Query Notion for jobs in Evaluated or Almost Applied status.

    Returns list of {page_id, company, role, url, status, date, has_reachout}.
    The has_reachout flag is populated per-job so the caller can skip without
    a second round-trip.
    """
    candidates = []
    for status in REACHOUT_STATUSES:
        rows = load_all_rows(NOTION_DB_APPLICATIONS, {
            "property": "Status",
            "select": {"equals": status},
        })
        for row in rows:
            p = row["properties"]
            company = "".join(t.get("plain_text", "") for t in p.get("Company_Name", {}).get("rich_text", []))
            role = "".join(t.get("plain_text", "") for t in p.get("Role", {}).get("rich_text", []))
            url = p.get("URL", {}).get("url")
            date_val = (p.get("Date", {}).get("date") or {}).get("start")
            source = (p.get("Source", {}).get("select") or {}).get("name")
            page_id = row["id"]
            candidates.append({
                "page_id": page_id,
                "company": company,
                "role": role,
                "url": url,
                "status": status,
                "date": date_val,
                "source": source,
                "has_reachout": page_has_reachout_header(page_id),
            })
    return candidates


# ── Check for existing Reachout section ─────────────────────────────

def fetch_page_blocks(page_id):
    """Fetch all top-level blocks from a Notion page, handling pagination."""
    blocks = []
    cursor = None
    while True:
        endpoint = f"blocks/{page_id}/children?page_size=100"
        if cursor:
            endpoint += f"&start_cursor={cursor}"
        data = notion_request(endpoint, method="GET")
        blocks.extend(data.get("results", []))
        if data.get("has_more"):
            cursor = data.get("next_cursor")
        else:
            break
    return blocks


def page_has_reachout_header(page_id):
    """Return True if the page has a heading_2 block whose text contains 'Reachout'."""
    try:
        blocks = fetch_page_blocks(page_id)
    except Exception:
        return False
    for block in blocks:
        if block.get("type") == "heading_2":
            rich_text = block.get("heading_2", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            if REACHOUT_HEADER.lower() in text.lower():
                return True
    return False


# ── Append Reachout section ─────────────────────────────────────────

def append_reachout_section(page_id, markdown_body):
    """Append a Reachout section to a Notion page.

    Prepends a '## Reachout' heading_2 + a 'Drafted: YYYY-MM-DD' line, then
    converts the supplied markdown_body to Notion blocks and appends them.

    Does NOT delete existing Reachout sections — re-runs produce a new dated
    section so the caller can see the evolution of the outreach draft.
    """
    header_md = f"## Reachout\n*Drafted: {date.today().isoformat()}*\n\n"
    full_md = header_md + markdown_body
    blocks = markdown_to_notion_blocks(full_md)
    if not blocks:
        return {"success": False, "error": "No blocks generated from markdown"}
    append_blocks_to_page(page_id, blocks)
    return {"success": True, "page_id": page_id, "blocks_added": len(blocks)}


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Reachout Notion I/O for the job-reachout skill.")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("query", help="Query jobs in Evaluated/Almost Applied status (with has_reachout flag)")

    p_check = sub.add_parser("has-reachout", help="Check if a page already has a Reachout section")
    p_check.add_argument("--page-id", required=True)

    p_write = sub.add_parser("write", help="Append a Reachout section to a page from a markdown file")
    p_write.add_argument("--page-id", required=True)
    p_write.add_argument("--report-file", required=True)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "query":
        candidates = query_reachout_candidates()
        already = sum(1 for c in candidates if c["has_reachout"])
        print(json.dumps({
            "success": True,
            "count": len(candidates),
            "already_have_reachout": already,
            "pending": len(candidates) - already,
            "jobs": candidates,
        }, indent=2))

    elif args.command == "has-reachout":
        has = page_has_reachout_header(args.page_id)
        print(json.dumps({"success": True, "page_id": args.page_id, "has_reachout": has}, indent=2))

    elif args.command == "write":
        with open(args.report_file, "r") as f:
            md = f.read()
        result = append_reachout_section(args.page_id, md)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

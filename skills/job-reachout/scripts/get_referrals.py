#!/usr/bin/env python3
"""
Get top referrals for a company from the Notion Companies → Connections databases.

Usage:
  python3 skills/job-eval/get_referrals.py --company "Google"
  python3 skills/job-eval/get_referrals.py --company "AMD" --top 5
  python3 skills/job-eval/get_referrals.py --company "Spotify" --json

Priority rules (highest first):
  1. Name contains "friend" — personal connection
  2. Has phone number — direct reachability
  3. Relation contains "BITS" or "TERP" — alumni network
  4. Has email AND Email_Thread = "yes" — existing conversation
  5. Has email (Email_Thread empty or other) — reachable by email

Output: top N referrals (default 3) with name, role, relation, phone, email, linkedin.
"""

import argparse
import json
import os
import sys

from sarvesh_ai_notion_interface.notion_client import load_all_rows, notion_request
from sarvesh_ai_notion_interface.config import NOTION_DB_COMPANIES, NOTION_DB_CONNECTIONS


def find_company_referral_ids(company_name: str) -> tuple[list[str], str | None]:
    """Look up a company in the Companies DB and return its referral page IDs.

    Returns:
        Tuple of (list of referral page IDs, referral_link URL or None).
    """
    rows = load_all_rows(NOTION_DB_COMPANIES, None)
    target = company_name.lower().strip()

    for row in rows:
        props = row.get("properties", {})
        name = "".join(
            t.get("plain_text", "") for t in props.get("Company", {}).get("title", [])
        ).strip()
        if name.lower() == target:
            refs = props.get("Referral", {}).get("relation", [])
            ref_link = props.get("Referral_Link", {}).get("url")
            return [r["id"] for r in refs], ref_link

    return [], None


def fetch_contact(page_id: str) -> dict | None:
    """Fetch a single contact page from Notion by ID."""
    try:
        page = notion_request(f"pages/{page_id}", method="GET")
    except SystemExit:
        return None

    props = page.get("properties", {})
    name = "".join(
        t.get("plain_text", "") for t in props.get("Name", {}).get("title", [])
    ).strip()
    phone = props.get("Phone", {}).get("phone_number") or ""
    email = props.get("Email", {}).get("email") or ""
    linkedin = props.get("Linkedin", {}).get("url") or ""
    relations = [x["name"] for x in props.get("Relation", {}).get("multi_select", [])]
    roles = [x["name"] for x in props.get("Role", {}).get("multi_select", [])]
    email_thread_sel = props.get("Email_Thread", {}).get("select")
    email_thread = email_thread_sel.get("name", "") if email_thread_sel else ""
    notes = "".join(
        t.get("plain_text", "") for t in props.get("Notes", {}).get("rich_text", [])
    ).strip()

    return {
        "name": name,
        "phone": phone,
        "email": email,
        "email_thread": email_thread,
        "linkedin": linkedin,
        "relation": relations,
        "role": roles,
        "notes": notes,
    }


def priority_score(contact: dict) -> tuple[int, int, int, int, int]:
    """Compute a priority score tuple (higher = better, sorted descending).

    Returns:
        (is_friend, has_phone, is_alumni, email_with_thread, has_email) — each 0 or 1.
    """
    is_friend = 1 if "friend" in contact["name"].lower() else 0
    has_phone = 1 if contact["phone"] else 0
    is_alumni = 1 if any(r in ("BITS", "TERP") for r in contact["relation"]) else 0
    has_email = 1 if contact["email"] else 0
    email_with_thread = 1 if has_email and contact.get("email_thread", "").lower() == "yes" else 0
    return (is_friend, has_phone, is_alumni, email_with_thread, has_email)


def get_top_referrals(company_name: str, top_n: int = 3) -> dict:
    """Get top N referrals for a company, ranked by priority rules.

    Returns:
        Dict with company, referral_link, referrals list, and count.
    """
    ref_ids, ref_link = find_company_referral_ids(company_name)

    if not ref_ids:
        return {
            "company": company_name,
            "referral_link": ref_link,
            "count": 0,
            "referrals": [],
        }

    contacts = []
    for pid in ref_ids:
        contact = fetch_contact(pid)
        if contact:
            contacts.append(contact)

    contacts.sort(key=priority_score, reverse=True)
    top = contacts[:top_n]

    for c in top:
        score = priority_score(c)
        tags = []
        if score[0]:
            tags.append("friend")
        if score[1]:
            tags.append("has_phone")
        if score[2]:
            tags.append("alumni")
        if score[3]:
            tags.append("email_thread")
        if score[4] and not score[3]:
            tags.append("has_email")
        c["priority_tags"] = tags

    return {
        "company": company_name,
        "referral_link": ref_link,
        "count": len(contacts),
        "referrals": top,
    }


def format_text(result: dict) -> str:
    """Format the result as human-readable text."""
    lines = [f"Referrals for {result['company']}: {result['count']} total"]
    if result["referral_link"]:
        lines.append(f"  Referral link: {result['referral_link']}")
    if not result["referrals"]:
        lines.append("  No referrals found.")
        return "\n".join(lines)

    lines.append("")
    for i, c in enumerate(result["referrals"], 1):
        tags = ", ".join(c.get("priority_tags", []))
        role_str = ", ".join(c["role"]) if c["role"] else "—"
        rel_str = ", ".join(c["relation"]) if c["relation"] else "—"
        lines.append(f"  {i}. {c['name']}")
        lines.append(f"     Role: {role_str}  |  Relation: {rel_str}")
        if c["phone"]:
            lines.append(f"     Phone: {c['phone']}")
        if c["email"]:
            lines.append(f"     Email: {c['email']}")
        if c["linkedin"]:
            lines.append(f"     LinkedIn: {c['linkedin']}")
        if tags:
            lines.append(f"     Priority: [{tags}]")
        lines.append("")

    return "\n".join(lines)


def resolve_status(score: float, company_name: str) -> str:
    """Determine the Notion status based on score and referral availability.

    Returns:
        "Discarded" if score < 2, "Referral" if score >= 2 and company has
        referrals, "Evaluated" otherwise.
    """
    if score < 2:
        return "Discarded"
    ref_ids, _ = find_company_referral_ids(company_name)
    if ref_ids:
        return "Referral"
    return "Evaluated"


def main():
    parser = argparse.ArgumentParser(description="Get top referrals for a company")
    sub = parser.add_subparsers(dest="command")

    # Default: get referrals (also works without subcommand for backwards compat)
    parser.add_argument("--company", help="Company name (case-insensitive)")
    parser.add_argument("--top", type=int, default=3, help="Number of referrals to return (default: 3)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Subcommand: resolve-status
    p_status = sub.add_parser("resolve-status", help="Resolve Notion status from score + company")
    p_status.add_argument("--score", type=float, required=True, help="Evaluation score (e.g., 3.8)")
    p_status.add_argument("--company", required=True, help="Company name (case-insensitive)")

    args = parser.parse_args()

    if args.command == "resolve-status":
        status = resolve_status(args.score, args.company)
        print(status)
    else:
        if not args.company:
            parser.error("--company is required")
        result = get_top_referrals(args.company, args.top)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(format_text(result))


if __name__ == "__main__":
    main()

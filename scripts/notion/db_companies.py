#!/usr/bin/env python3
"""
Companies Database — load, check, and add companies in Notion.

Usage:
  python3 scripts/notion/db_companies.py list --categories Dream Big-Tech --pretty
  python3 scripts/notion/db_companies.py check --name "Mistral AI"
  python3 scripts/notion/db_companies.py add --name "Mistral AI" --url "https://jobs.lever.co/mistral" --category Dream
"""

import argparse
import json
import sys
import os

try:
    from .notion_client import load_all_rows, notion_request
    from .config import NOTION_DB_COMPANIES
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from notion_client import load_all_rows, notion_request
    from config import NOTION_DB_COMPANIES


def load_companies(categories):
    """Load companies from Notion, filtered by category.

    Args:
        categories: List of category names (e.g., ["Dream", "Big-Tech"])

    Returns:
        List of dicts: [{"name": str, "careers_url": str, "categories": [str]}]
    """
    category_filters = [
        {"property": "Category", "multi_select": {"contains": cat}}
        for cat in categories
    ]
    filter_body = {"or": category_filters} if len(category_filters) > 1 else category_filters[0]

    rows = load_all_rows(NOTION_DB_COMPANIES, filter_body)

    companies = []
    for row in rows:
        props = row.get("properties", {})
        name = "".join(t.get("plain_text", "") for t in props.get("Company", {}).get("title", [])).strip()
        careers_url = (props.get("Careers_Page", {}).get("url") or "").strip()
        cats = [c["name"] for c in props.get("Category", {}).get("multi_select", [])]

        if name and careers_url:
            companies.append({"name": name, "careers_url": careers_url, "categories": cats})

    return companies


def company_exists(name):
    """Check if a company already exists in the DB (case-insensitive).

    Args:
        name: Company name to check.

    Returns:
        True if a company with that name exists, False otherwise.
    """
    rows = load_all_rows(NOTION_DB_COMPANIES)
    name_lower = name.lower().strip()
    for row in rows:
        props = row.get("properties", {})
        existing = "".join(t.get("plain_text", "") for t in props.get("Company", {}).get("title", [])).strip()
        if existing.lower() == name_lower:
            return True
    return False


def add_company(name, careers_url, categories=None):
    """Add a new company to the Notion Companies DB.

    Args:
        name: Company name.
        careers_url: Careers page URL.
        categories: List of category strings (e.g., ["Dream"]). Defaults to ["Discovery"].

    Returns:
        Dict with "success" and "page_id" keys.
    """
    if categories is None:
        categories = ["Discovery"]

    properties = {
        "Company": {"title": [{"text": {"content": name}}]},
        "Category": {"multi_select": [{"name": cat} for cat in categories]},
    }
    if careers_url:
        properties["Careers_Page"] = {"url": careers_url}

    result = notion_request("pages", method="POST", data={
        "parent": {"database_id": NOTION_DB_COMPANIES},
        "properties": properties,
    })

    return {"success": True, "page_id": result.get("id", "")}


def add_company_if_new(name, careers_url, categories=None):
    """Add a company only if it doesn't already exist.

    Args:
        name: Company name.
        careers_url: Careers page URL.
        categories: List of category strings.

    Returns:
        Dict with "added" (bool) and optionally "page_id".
    """
    if company_exists(name):
        return {"added": False, "reason": f"'{name}' already exists"}
    result = add_company(name, careers_url, categories)
    return {"added": True, "page_id": result["page_id"]}


def main():
    parser = argparse.ArgumentParser(description="Manage companies in Notion.")
    sub = parser.add_subparsers(dest="command")

    # list (default)
    list_p = sub.add_parser("list", help="List companies by category")
    list_p.add_argument("--categories", nargs="+", default=["Dream", "Big-Tech"])
    list_p.add_argument("--pretty", action="store_true")

    # check
    check_p = sub.add_parser("check", help="Check if a company exists")
    check_p.add_argument("--name", required=True)

    # add
    add_p = sub.add_parser("add", help="Add a new company (skips if exists)")
    add_p.add_argument("--name", required=True)
    add_p.add_argument("--url", required=True, help="Careers page URL")
    add_p.add_argument("--category", nargs="+", default=["Discovery"])

    args = parser.parse_args()

    if args.command == "check":
        exists = company_exists(args.name)
        print(json.dumps({"name": args.name, "exists": exists}))

    elif args.command == "add":
        result = add_company_if_new(args.name, args.url, args.category)
        print(json.dumps(result, indent=2))

    else:  # list or no subcommand
        cats = getattr(args, "categories", ["Dream", "Big-Tech"])
        pretty = getattr(args, "pretty", False)
        companies = load_companies(cats)

        if pretty:
            print(f"Found {len(companies)} companies (categories: {', '.join(cats)}):\n")
            for c in companies:
                print(f"  {c['name']:30s} | {str(c['categories']):30s} | {c['careers_url']}")
        else:
            print(json.dumps(companies, indent=2))


if __name__ == "__main__":
    main()

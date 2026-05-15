#!/usr/bin/env python3
"""
Connections Database — add and query connections in Notion.

Usage:
  python3 scripts/notion/db_connections.py add --name "John Doe"
  python3 scripts/notion/db_connections.py add --name "John Doe" --role Engineer --email john@co.com --linkedin "https://linkedin.com/in/john" --relation BITS DMV
  python3 scripts/notion/db_connections.py check --name "John Doe"
  python3 scripts/notion/db_connections.py list --pretty
"""

import argparse
import json
import os
import sys
from typing import Optional

try:
    from .notion_client import load_all_rows, notion_request
    from .config import NOTION_DB_CONNECTIONS
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from notion_client import load_all_rows, notion_request
    from config import NOTION_DB_CONNECTIONS


def connection_exists(name: str) -> bool:
    """Check if a connection already exists in the DB (case-insensitive).

    Args:
        name: Person's name to check.

    Returns:
        True if a connection with that name exists, False otherwise.
    """
    rows = load_all_rows(NOTION_DB_CONNECTIONS)
    name_lower = name.lower().strip()
    for row in rows:
        props = row.get("properties", {})
        existing = "".join(
            t.get("plain_text", "") for t in props.get("Name", {}).get("title", [])
        ).strip()
        if existing.lower() == name_lower:
            return True
    return False


def add_connection(
    name: str,
    role: Optional[list[str]] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    linkedin: Optional[str] = None,
    notes: Optional[str] = None,
    emailed: Optional[str] = None,
    relation: Optional[list[str]] = None,
) -> dict:
    """Add a new connection to the Notion Connections DB.

    Args:
        name: Person's name (required).
        role: List of role tags (e.g., ["Engineer", "CTO"]).
        email: Email address.
        phone: Phone number.
        linkedin: LinkedIn profile URL.
        notes: Free-text notes.
        emailed: Emailed status ("yes" or "no").
        relation: List of relation tags (e.g., ["BITS", "DMV", "TERP"]).

    Returns:
        Dict with "success" and "page_id" keys.
    """
    properties: dict = {
        "Name": {"title": [{"text": {"content": name}}]},
    }

    if role:
        properties["Role"] = {"multi_select": [{"name": r} for r in role]}
    if email:
        properties["Email"] = {"email": email}
    if phone:
        properties["Phone"] = {"phone_number": phone}
    if linkedin:
        properties["Linkedin"] = {"url": linkedin}
    if notes:
        properties["Notes"] = {"rich_text": [{"text": {"content": notes}}]}
    if emailed:
        properties["Email_Sent"] = {"select": {"name": emailed}}
    if relation:
        properties["Relation"] = {"multi_select": [{"name": r} for r in relation]}

    result = notion_request("pages", method="POST", data={
        "parent": {"database_id": NOTION_DB_CONNECTIONS},
        "properties": properties,
    })

    return {"success": True, "page_id": result.get("id", "")}


def add_connection_if_new(
    name: str,
    role: Optional[list[str]] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    linkedin: Optional[str] = None,
    notes: Optional[str] = None,
    emailed: Optional[str] = None,
    relation: Optional[list[str]] = None,
) -> dict:
    """Add a connection only if it doesn't already exist.

    Args:
        name: Person's name (required).
        role: List of role tags.
        email: Email address.
        phone: Phone number.
        linkedin: LinkedIn profile URL.
        notes: Free-text notes.
        emailed: Emailed status.
        relation: List of relation tags.

    Returns:
        Dict with "added" (bool) and optionally "page_id".
    """
    if connection_exists(name):
        return {"added": False, "reason": f"'{name}' already exists"}
    result = add_connection(name, role, email, phone, linkedin, notes, emailed, relation)
    return {"added": True, "page_id": result["page_id"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage connections in Notion.")
    sub = parser.add_subparsers(dest="command")

    # list
    list_p = sub.add_parser("list", help="List all connections")
    list_p.add_argument("--pretty", action="store_true")

    # check
    check_p = sub.add_parser("check", help="Check if a connection exists")
    check_p.add_argument("--name", required=True)

    # add
    add_p = sub.add_parser("add", help="Add a new connection (skips if exists)")
    add_p.add_argument("--name", required=True)
    add_p.add_argument("--role", nargs="+", default=None)
    add_p.add_argument("--email", default=None)
    add_p.add_argument("--phone", default=None)
    add_p.add_argument("--linkedin", default=None)
    add_p.add_argument("--notes", default=None)
    add_p.add_argument("--emailed", default=None, choices=["yes", "no"])
    add_p.add_argument("--relation", nargs="+", default=None)

    args = parser.parse_args()

    if args.command == "check":
        exists = connection_exists(args.name)
        print(json.dumps({"name": args.name, "exists": exists}))

    elif args.command == "add":
        result = add_connection_if_new(
            args.name, args.role, args.email, args.phone,
            args.linkedin, args.notes, args.emailed, args.relation,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "list":
        rows = load_all_rows(NOTION_DB_CONNECTIONS)
        connections = []
        for row in rows:
            props = row.get("properties", {})
            name = "".join(
                t.get("plain_text", "") for t in props.get("Name", {}).get("title", [])
            ).strip()
            roles = [c["name"] for c in props.get("Role", {}).get("multi_select", [])]
            email = props.get("Email", {}).get("email") or ""
            linkedin = props.get("Linkedin", {}).get("url") or ""
            relations = [c["name"] for c in props.get("Relation", {}).get("multi_select", [])]
            if name:
                connections.append({
                    "name": name, "role": roles, "email": email,
                    "linkedin": linkedin, "relation": relations,
                })

        if getattr(args, "pretty", False):
            print(f"Found {len(connections)} connections:\n")
            for c in connections:
                print(f"  {c['name']:30s} | {str(c['role']):25s} | {c['linkedin']}")
        else:
            print(json.dumps(connections, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Applications Database — Notion CRUD operations.

All functions for the Applications DB: add scanned jobs, query by status,
update status, update evaluations, dedup, markdown→blocks, file uploads.

Usage:
  python3 scripts/notion/db_applications.py add --company X --role Y --url Z
  python3 scripts/notion/db_applications.py add-batch              # JSON from stdin
  python3 scripts/notion/db_applications.py query --status "Evaluated"
  python3 scripts/notion/db_applications.py update-status --page-id X --status Y
  python3 scripts/notion/db_applications.py update-eval --page-id X --score 4.3 --status Evaluated --report-file /tmp/r.md
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date

# Handle both package import and direct execution
try:
    from .notion_client import notion_request, load_all_rows
    from .config import NOTION_TOKEN, NOTION_API, NOTION_DB_APPLICATIONS
    from .company_matcher import match_company_name
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from notion_client import notion_request, load_all_rows
    from config import NOTION_TOKEN, NOTION_API, NOTION_DB_APPLICATIONS
    from company_matcher import match_company_name

VALID_STATUSES = [
    "Scanned", "Evaluated", "Almost Applied", "Applied", "Responded",
    "Interview", "Offer", "Rejected", "Discarded", "SKIP"
]


# ── Add scanned jobs ────────────────────────────────────────────────

def resolve_about_company_relation(company):
    """Return a single-page relation payload for About_Company, if confidently matched."""
    result = match_company_name(company)
    if result.get("status") != "matched":
        return None
    match = result.get("match") or {}
    if not match.get("page_id"):
        return None
    return [{"id": match["page_id"]}]


def update_about_company(page_id, company_page_id):
    """Set the About_Company relation for an application page."""
    notion_request(
        f"pages/{page_id}",
        method="PATCH",
        data={"properties": {"About_Company": {"relation": [{"id": company_page_id}]}}},
    )
    return {"success": True, "page_id": page_id, "company_page_id": company_page_id}


def add_scanned_job(company, role, url, source=None, location=None):
    """Add a single scanned job row to Notion."""
    properties = {
        "Report": {"title": [{"text": {"content": "Report"}}]},
        "Company_Name": {"rich_text": [{"text": {"content": company}}]},
        "Role": {"rich_text": [{"text": {"content": role}}]},
        "Date": {"date": {"start": date.today().isoformat()}},
        "Status": {"select": {"name": "Scanned"}},
    }
    if url:
        properties["URL"] = {"url": url}
    if source:
        properties["Source"] = {"select": {"name": source}}
    if location:
        properties["Location"] = {"rich_text": [{"text": {"content": location}}]}
    about_company_relation = resolve_about_company_relation(company)
    if about_company_relation:
        properties["About_Company"] = {"relation": about_company_relation}

    result = notion_request("pages", method="POST", data={
        "parent": {"database_id": NOTION_DB_APPLICATIONS},
        "properties": properties,
    })

    if "error" in result:
        return {"success": False, "company": company, "role": role, "error": result["error"]}

    return {
        "success": True,
        "page_id": result["id"],
        "company": company,
        "role": role,
        "url": url,
        "status": "Scanned",
        "about_company_linked": bool(about_company_relation),
    }


def add_scanned_jobs_batch(jobs):
    """Add multiple scanned jobs to Notion.

    Args:
        jobs: List of dicts with "company", "role", "url" keys,
              optional "location" and "source" keys.

    Returns:
        Dict with "success", "count", "results".
    """
    results = []
    for job in jobs:
        result = add_scanned_job(
            job["company"],
            job["role"],
            job.get("url"),
            source=job.get("source"),
            location=job.get("location"),
        )
        results.append(result)
    return {"success": True, "count": len(results), "results": results}


# ── Query by status ─────────────────────────────────────────────────

def query_by_status(status):
    """Query Notion database for rows matching a specific status.

    Returns:
        Dict with "success", "status_filter", "count", "jobs".
    """
    rows = load_all_rows(NOTION_DB_APPLICATIONS, {
        "property": "Status",
        "select": {"equals": status},
    })

    # Sort by score descending (None scores last)
    rows.sort(key=lambda r: r["properties"].get("Score", {}).get("number") or -999, reverse=True)

    jobs = []
    for row in rows:
        p = row["properties"]
        company = "".join(t.get("plain_text", "") for t in p.get("Company_Name", {}).get("rich_text", []))
        role = "".join(t.get("plain_text", "") for t in p.get("Role", {}).get("rich_text", []))
        url = p.get("URL", {}).get("url")
        score = p.get("Score", {}).get("number")
        row_status = p.get("Status", {}).get("select", {}).get("name", "?") if p.get("Status", {}).get("select") else "?"

        jobs.append({
            "page_id": row["id"],
            "company": company,
            "role": role,
            "url": url,
            "score": score,
            "status": row_status,
        })

    return {"success": True, "status_filter": status, "count": len(jobs), "jobs": jobs}


# ── Update status ───────────────────────────────────────────────────

def update_status(page_id, new_status):
    """Update the status of a Notion page."""
    if new_status not in VALID_STATUSES:
        return {"success": False, "error": f"Invalid status '{new_status}'"}

    notion_request(f"pages/{page_id}", method="PATCH", data={
        "properties": {"Status": {"select": {"name": new_status}}}
    })

    return {"success": True, "page_id": page_id, "new_status": new_status}


# ── Dedup sets ──────────────────────────────────────────────────────

def load_dedup_sets():
    """Load seen URLs and company::role pairs from the applications DB."""
    seen_urls = set()
    seen_company_roles = set()

    if not NOTION_TOKEN:
        print("  Warning: NOTION_TOKEN not set — skipping Notion dedup")
        return seen_urls, seen_company_roles

    rows = load_all_rows(NOTION_DB_APPLICATIONS)

    for row in rows:
        props = row.get("properties", {})

        url = props.get("URL", {}).get("url")
        if url:
            seen_urls.add(url)

        company_texts = props.get("Company_Name", {}).get("rich_text", [])
        company = "".join(t.get("plain_text", "") for t in company_texts).strip().lower()

        role_texts = props.get("Role", {}).get("rich_text", [])
        role = "".join(t.get("plain_text", "") for t in role_texts).strip().lower()

        if company and role:
            seen_company_roles.add(f"{company}::{role}")

    print(f"  Notion dedup: {len(rows)} rows loaded, {len(seen_urls)} URLs tracked")
    return seen_urls, seen_company_roles


# ── Markdown → Notion blocks ────────────────────────────────────────

def parse_inline(text):
    """Parse inline markdown (bold, italic, code, links) into Notion rich_text array."""
    rich_text = []
    pattern = re.compile(
        r"(\*\*(.+?)\*\*)"
        r"|(\*(.+?)\*)"
        r"|(`(.+?)`)"
        r"|(\[(.+?)\]\((.+?)\))"
    )

    last_end = 0
    for match in pattern.finditer(text):
        if match.start() > last_end:
            plain = text[last_end:match.start()]
            if plain:
                rich_text.append({"type": "text", "text": {"content": plain}})

        if match.group(2):
            bold_content = match.group(2)
            # Check if bold content contains a link: **[text](url)**
            link_in_bold = re.match(r"^\[(.+?)\]\((.+?)\)$", bold_content)
            if link_in_bold:
                rich_text.append({"type": "text", "text": {"content": link_in_bold.group(1), "link": {"url": link_in_bold.group(2)}}, "annotations": {"bold": True}})
            else:
                rich_text.append({"type": "text", "text": {"content": bold_content}, "annotations": {"bold": True}})
        elif match.group(4):
            rich_text.append({"type": "text", "text": {"content": match.group(4)}, "annotations": {"italic": True}})
        elif match.group(6):
            rich_text.append({"type": "text", "text": {"content": match.group(6)}, "annotations": {"code": True}})
        elif match.group(8):
            rich_text.append({"type": "text", "text": {"content": match.group(8), "link": {"url": match.group(9)}}})

        last_end = match.end()

    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            rich_text.append({"type": "text", "text": {"content": remaining}})

    if not rich_text:
        rich_text.append({"type": "text", "text": {"content": text}})

    return rich_text


def markdown_to_notion_blocks(markdown_text):
    """Convert markdown text to Notion block objects."""
    blocks = []
    lines = markdown_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            blocks.append({"object": "block", "type": "code", "code": {
                "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}],
                "language": lang if lang else "plain text",
            }})
            continue

        if line.strip() in ("---", "***", "___"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        if line.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": parse_inline(line[4:].strip())}})
            i += 1
            continue
        if line.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": parse_inline(line[3:].strip())}})
            i += 1
            continue
        if line.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1", "heading_1": {"rich_text": parse_inline(line[2:].strip())}})
            i += 1
            continue

        if line.strip().startswith("- ") or line.strip().startswith("* "):
            blocks.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": parse_inline(line.strip()[2:])}})
            i += 1
            continue

        num_match = re.match(r"^\s*\d+\.\s+(.*)", line)
        if num_match:
            blocks.append({"object": "block", "type": "numbered_list_item", "numbered_list_item": {"rich_text": parse_inline(num_match.group(1))}})
            i += 1
            continue

        if line.strip().startswith("|"):
            if re.match(r"^\|[\s\-|]+\|$", line.strip()):
                i += 1
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            text = " | ".join(cells)
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": parse_inline(text)}})
            i += 1
            continue

        blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": parse_inline(line.strip())}})
        i += 1

    return blocks


def append_blocks_to_page(page_id, blocks):
    """Append blocks to a Notion page. Max 100 blocks per request."""
    for i in range(0, len(blocks), 100):
        chunk = blocks[i:i + 100]
        notion_request(f"blocks/{page_id}/children", method="PATCH", data={"children": chunk})


# ── File upload ─────────────────────────────────────────────────────

def upload_file_to_notion(file_path):
    """Upload a file to Notion and return the file_upload id."""
    filename = os.path.basename(file_path)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_types = {
        "pdf": "application/pdf", "png": "image/png",
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    result = notion_request("file_uploads", method="POST", data={
        "filename": filename, "content_type": content_type,
    })

    upload_id = result["id"]
    upload_url = result.get("upload_url", f"{NOTION_API}/file_uploads/{upload_id}/send")

    boundary = "----NotionFileUploadBoundary"
    with open(file_path, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(upload_url, method="POST", headers={
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2026-03-11",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }, data=body)

    try:
        with urllib.request.urlopen(req) as resp:
            json.loads(resp.read())
            return upload_id, filename
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"Warning: File upload failed: HTTP {e.code}: {err_body}", file=sys.stderr)
        return None, filename


# ── Update evaluation ───────────────────────────────────────────────

def update_evaluation(page_id, score, status, report_file=None, resume_file=None):
    """Update an existing Notion row with evaluation results and report content."""
    if status not in VALID_STATUSES:
        return {"success": False, "error": f"Invalid status '{status}'"}

    resume_upload_id = None
    resume_filename = None
    if resume_file and os.path.exists(resume_file):
        resume_upload_id, resume_filename = upload_file_to_notion(resume_file)
    elif resume_file:
        print(f"Warning: Resume file not found: {resume_file}", file=sys.stderr)

    properties = {
        "Score": {"number": score},
        "Status": {"select": {"name": status}},
    }
    if resume_upload_id:
        properties["Resume"] = {"files": [{"type": "file_upload", "file_upload": {"id": resume_upload_id}, "name": resume_filename}]}

    result = notion_request(f"pages/{page_id}", method="PATCH", data={"properties": properties})
    page_url = result.get("url", "")

    blocks_added = 0
    if report_file and os.path.exists(report_file):
        markdown = open(report_file, "r").read()
        blocks = markdown_to_notion_blocks(markdown)
        if blocks:
            append_blocks_to_page(page_id, blocks)
            blocks_added = len(blocks)
    elif report_file:
        print(f"Warning: Report file not found: {report_file}", file=sys.stderr)

    return {
        "success": True,
        "page_id": page_id,
        "url": page_url,
        "score": score,
        "status": status,
        "report_blocks": blocks_added,
        "resume_uploaded": resume_upload_id is not None,
    }


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Applications DB operations.")
    sub = parser.add_subparsers(dest="command")

    # add
    p_add = sub.add_parser("add", help="Add a scanned job")
    p_add.add_argument("--company", required=True)
    p_add.add_argument("--role", required=True)
    p_add.add_argument("--url", default=None)
    p_add.add_argument("--source", default=None, choices=["API", "Web Search", "Broad Web Search", "Fallback Web Search", "User", "Jobright"])

    # add-batch
    sub.add_parser("add-batch", help="Add scanned jobs from JSON stdin")

    # query
    p_query = sub.add_parser("query", help="Query jobs by status")
    p_query.add_argument("--status", default="Evaluated")

    # update-status
    p_status = sub.add_parser("update-status", help="Update job status")
    p_status.add_argument("--page-id", required=True)
    p_status.add_argument("--status", required=True)

    # update-eval
    p_eval = sub.add_parser("update-eval", help="Update with evaluation results")
    p_eval.add_argument("--page-id", required=True)
    p_eval.add_argument("--score", required=True, type=float)
    p_eval.add_argument("--status", default="Evaluated")
    p_eval.add_argument("--report-file", default=None)
    p_eval.add_argument("--resume-file", default=None)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "add":
        result = add_scanned_job(args.company, args.role, args.url, source=args.source)
        print(json.dumps(result, indent=2))

    elif args.command == "add-batch":
        jobs = json.loads(sys.stdin.read())
        result = add_scanned_jobs_batch(jobs)
        print(json.dumps(result, indent=2))

    elif args.command == "query":
        result = query_by_status(args.status)
        print(json.dumps(result, indent=2))

    elif args.command == "update-status":
        result = update_status(args.page_id, args.status)
        print(json.dumps(result, indent=2))

    elif args.command == "update-eval":
        result = update_evaluation(args.page_id, args.score, args.status, args.report_file, args.resume_file)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

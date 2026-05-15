"""
Notion configuration — loads all IDs from .env file.

All Notion database IDs, page IDs, and the API token are loaded from
the repo root .env file. Falls back to environment variables.
"""

import os

# Find .env file relative to this script
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(_SCRIPT_DIR, "..", "..", ".env")


def _load_env():
    """Load variables from .env file into os.environ (if not already set)."""
    if not os.path.exists(_ENV_FILE):
        return
    with open(_ENV_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            # Don't override existing env vars
            if key not in os.environ:
                os.environ[key] = value


# Load .env on import
_load_env()

# ── API ─────────────────────────────────────────────────────────────

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_API = "https://api.notion.com/v1"

# ── Database IDs ────────────────────────────────────────────────────

NOTION_DB_APPLICATIONS = os.environ.get("NOTION_DB_APPLICATIONS", "")
NOTION_DB_COMPANIES = os.environ.get("NOTION_DB_COMPANIES", "")
NOTION_DB_CONNECTIONS = os.environ.get("NOTION_DB_CONNECTIONS", "")

# ── Page IDs ────────────────────────────────────────────────────────

PROJECTS = {
    "roma": os.environ.get("NOTION_PAGE_ROMA", ""),
    "mroma": os.environ.get("NOTION_PAGE_MROMA", ""),
    "sera": os.environ.get("NOTION_PAGE_SERA", ""),
    "deep-research": os.environ.get("NOTION_PAGE_DEEP_RESEARCH", ""),
    "txt2sql": os.environ.get("NOTION_PAGE_TXT2SQL", ""),
    "harness": os.environ.get("NOTION_PAGE_HARNESS", ""),
    "profile": os.environ.get("NOTION_PAGE_PROFILE", ""),
    "projects": os.environ.get("NOTION_PAGE_PROJECTS", ""),
    "resume": os.environ.get("NOTION_PAGE_RESUME", ""),
}

PARENT_PAGE = os.environ.get("NOTION_PAGE_PARENT", "")

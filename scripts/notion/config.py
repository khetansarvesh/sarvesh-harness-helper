"""
Notion configuration — loads all IDs from .env file.

All Notion database IDs, page IDs, and the API token are loaded from
the repo root .env file. Falls back to environment variables.

Project pages (roma, sera, etc.) are auto-discovered from the parent
page's children via the Notion API on first access.
"""

import collections.abc
import json
import logging
import os
import re
import urllib.request

logger = logging.getLogger(__name__)

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

PARENT_PAGE = os.environ.get("NOTION_PAGE_PARENT", "")


# ── Auto-discovery helpers ──────────────────────────────────────────

# Short aliases for Notion page titles that differ from their normalized form.
# Maps normalized title -> short alias used in batch-prompt.md and CLI.
_TITLE_ALIASES = {
    "multimodal-roma-mroma": "mroma",
    "deep-research-agent": "deep-research",
    "text2sql": "txt2sql",
    "automated-harness-tracing": "harness",
}


def _normalize_title(title: str) -> str:
    """Convert a Notion child page title to a project key.

    Applies aliases so that long Notion titles map to the short keys
    used by batch-prompt.md and the CLI.

    Examples: "ROMA" -> "roma", "Multimodal ROMA mROMA" -> "mroma",
              "Deep Research Agent" -> "deep-research",
              "text2sql" -> "txt2sql", "Automated Harness Tracing" -> "harness"
    """
    key = title.strip().lower()
    key = re.sub(r"\s+", "-", key)
    key = re.sub(r"[^a-z0-9\-]", "", key)
    # Collapse repeated hyphens
    key = re.sub(r"-{2,}", "-", key)
    key = key.strip("-")
    return _TITLE_ALIASES.get(key, key)


def _fetch_child_pages(parent_id: str) -> dict[str, str]:
    """Fetch child pages from a Notion parent page.

    Uses urllib.request directly to avoid circular imports with
    page_reader.py or notion_client.py.

    Returns:
        Dict mapping normalized title -> page ID.
    """
    if not parent_id or not NOTION_TOKEN:
        return {}

    url = f"{NOTION_API}/blocks/{parent_id}/children?page_size=100"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    })

    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    children = {}
    for block in data.get("results", []):
        if block.get("type") == "child_page":
            title = block["child_page"].get("title", "")
            block_id = block.get("id", "")
            if title and block_id:
                children[_normalize_title(title)] = block_id

    return children


class LazyProjectsDict(collections.abc.MutableMapping):
    """A dict-like object that lazily discovers project pages from Notion.

    On first access, fetches child pages from the parent page and merges
    them with explicit env var entries. Explicit env vars always win.
    """

    def __init__(self, explicit: dict[str, str], parent_id: str):
        self._explicit = dict(explicit)
        self._parent_id = parent_id
        self._discovered: dict[str, str] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            self._discovered = _fetch_child_pages(self._parent_id)
        except Exception as e:
            logger.warning("Failed to auto-discover project pages from parent: %s", e)
            self._discovered = {}

    def _merged(self) -> dict[str, str]:
        self._ensure_loaded()
        merged = dict(self._discovered)
        merged.update(self._explicit)  # explicit wins
        return merged

    def __getitem__(self, key):
        return self._merged()[key]

    def __setitem__(self, key, value):
        self._explicit[key] = value

    def __delitem__(self, key):
        del self._explicit[key]

    def __iter__(self):
        return iter(self._merged())

    def __len__(self):
        return len(self._merged())

    def __contains__(self, key):
        return key in self._merged()

    def __repr__(self):
        return f"LazyProjectsDict({self._merged()!r})"


# ── Build PROJECTS dict ─────────────────────────────────────────────

# Explicit pages that are NOT children of the parent page
_explicit_pages = {
    "profile": os.environ.get("NOTION_PAGE_PROFILE", ""),
    "projects": os.environ.get("NOTION_PAGE_PROJECTS", ""),
    "resume": os.environ.get("NOTION_PAGE_RESUME", ""),
}

# Backward compat: scan for any NOTION_PAGE_* env vars and include them
_SKIP_KEYS = {"NOTION_PAGE_PARENT", "NOTION_PAGE_PROFILE", "NOTION_PAGE_PROJECTS", "NOTION_PAGE_RESUME"}
for _key, _val in os.environ.items():
    if _key.startswith("NOTION_PAGE_") and _key not in _SKIP_KEYS and _val:
        _name = _key.replace("NOTION_PAGE_", "").lower().replace("_", "-")
        _explicit_pages[_name] = _val

PROJECTS = LazyProjectsDict(explicit=_explicit_pages, parent_id=PARENT_PAGE)

#!/usr/bin/env python3
"""
Reusable fuzzy matcher for linking application rows to company DB pages.

Designed to be conservative:
- exact alias matches auto-link
- high-confidence fuzzy matches auto-link
- ambiguous/low-confidence matches are surfaced for review
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

from scripts.notion.notion_client import load_all_rows
from scripts.notion.config import NOTION_DB_COMPANIES


CORP_SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "llc",
    "ltd",
    "limited",
    "plc",
    "gmbh",
    "ag",
    "sa",
    "sas",
    "bv",
    "nv",
    "pte",
    "pty",
    "group",
    "holdings",
    "technologies",
    "technology",
}

SPLIT_PATTERN = re.compile(r"\s*(?:/|\||;|\u2022)\s*")

_COMPANY_INDEX: list["CompanyRecord"] | None = None


@dataclass(frozen=True)
class CompanyRecord:
    page_id: str
    name: str
    careers_url: str
    aliases: tuple[str, ...]
    compact_aliases: tuple[str, ...]
    token_aliases: tuple[frozenset[str], ...]


def _ascii_fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _normalize_text(text: str) -> str:
    text = _ascii_fold(text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[\(\)\[\]\{\}]", " ", text)
    text = re.sub(r"[^a-z0-9/+\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _strip_suffix_tokens(tokens: list[str]) -> list[str]:
    trimmed = list(tokens)
    while trimmed and trimmed[-1] in CORP_SUFFIXES:
        trimmed.pop()
    return trimmed


def _normalize_alias(text: str) -> str:
    norm = _normalize_text(text)
    tokens = _strip_suffix_tokens(norm.split())
    return " ".join(tokens).strip()


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text or "")


def _token_set(text: str) -> frozenset[str]:
    return frozenset(token for token in text.split() if token and token not in CORP_SUFFIXES)


def _alias_variants(name: str) -> set[str]:
    source = (name or "").strip()
    if not source:
        return set()

    variants = {source}
    variants.add(re.sub(r"\([^)]*\)", " ", source).strip())

    for piece in SPLIT_PATTERN.split(source):
        piece = piece.strip()
        if piece:
            variants.add(piece)

    # Also keep comma/ dash leading part variants for names like "X, Inc." or "Foo - Bar"
    for sep in (",", " - ", " — "):
        if sep in source:
            head = source.split(sep, 1)[0].strip()
            if head:
                variants.add(head)

    normalized = set()
    for variant in variants:
        norm = _normalize_alias(variant)
        if norm:
            normalized.add(norm)
    return normalized


def load_company_index(force_refresh: bool = False) -> list[CompanyRecord]:
    global _COMPANY_INDEX
    if _COMPANY_INDEX is not None and not force_refresh:
        return _COMPANY_INDEX

    rows = load_all_rows(NOTION_DB_COMPANIES)
    records: list[CompanyRecord] = []
    for row in rows:
        props = row.get("properties", {})
        name = "".join(t.get("plain_text", "") for t in props.get("Company", {}).get("title", [])).strip()
        careers_url = (props.get("Careers_Page", {}).get("url") or "").strip()
        if not name:
            continue
        aliases = sorted(_alias_variants(name))
        compact_aliases = sorted({_compact(alias) for alias in aliases if _compact(alias)})
        token_aliases = tuple(sorted({_token_set(alias) for alias in aliases if _token_set(alias)}, key=lambda s: (len(s), sorted(s))))
        records.append(
            CompanyRecord(
                page_id=row["id"],
                name=name,
                careers_url=careers_url,
                aliases=tuple(aliases),
                compact_aliases=tuple(compact_aliases),
                token_aliases=token_aliases,
            )
        )

    _COMPANY_INDEX = records
    return records


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _score_match(query_aliases: set[str], record: CompanyRecord) -> tuple[float, str]:
    query_compacts = {_compact(alias) for alias in query_aliases if _compact(alias)}
    query_tokens = {_token_set(alias) for alias in query_aliases if _token_set(alias)}

    if set(record.aliases) & query_aliases:
        return 1.0, "exact_alias"
    if set(record.compact_aliases) & query_compacts:
        return 0.995, "exact_compact_alias"

    best_seq = 0.0
    best_jaccard = 0.0
    subset_bonus = 0.0
    for query_alias in query_aliases:
        for company_alias in record.aliases:
            best_seq = max(best_seq, difflib.SequenceMatcher(None, query_alias, company_alias).ratio())
    for query_token_set in query_tokens:
        for company_token_set in record.token_aliases:
            if not query_token_set or not company_token_set:
                continue
            jac = _jaccard(query_token_set, company_token_set)
            best_jaccard = max(best_jaccard, jac)
            if len(query_token_set) >= 2 and (
                query_token_set <= company_token_set or company_token_set <= query_token_set
            ):
                subset_bonus = max(subset_bonus, 0.03)

    score = max(best_seq, 0.65 * best_seq + 0.35 * best_jaccard + subset_bonus)
    reason = f"fuzzy(seq={best_seq:.3f},tok={best_jaccard:.3f})"
    return min(score, 0.99), reason


def match_company_name(
    company_name: str,
    *,
    records: list[CompanyRecord] | None = None,
    min_score: float = 0.93,
    min_gap: float = 0.05,
) -> dict:
    records = records or load_company_index()
    query_aliases = _alias_variants(company_name)
    if not query_aliases:
        return {"status": "unmatched", "query": company_name, "reason": "empty_company_name", "candidates": []}

    scored = []
    for record in records:
        score, reason = _score_match(query_aliases, record)
        if score <= 0:
            continue
        scored.append(
            {
                "page_id": record.page_id,
                "company_name": record.name,
                "careers_url": record.careers_url,
                "score": round(score, 4),
                "reason": reason,
            }
        )

    scored.sort(key=lambda item: (-item["score"], item["company_name"].lower()))
    if not scored:
        return {"status": "unmatched", "query": company_name, "reason": "no_candidates", "candidates": []}

    best = scored[0]
    second_score = scored[1]["score"] if len(scored) > 1 else 0.0
    gap = round(best["score"] - second_score, 4)

    if best["score"] >= min_score and gap >= min_gap:
        return {
            "status": "matched",
            "query": company_name,
            "match": best,
            "gap": gap,
            "candidates": scored[:5],
        }

    return {
        "status": "ambiguous" if best["score"] >= min_score else "unmatched",
        "query": company_name,
        "match": best,
        "gap": gap,
        "candidates": scored[:5],
    }

#!/usr/bin/env python3
"""
Infer a person's work email from referral email patterns at a company.

Looks up the company in the Notion Companies DB, loads Connections linked via
the Referral relation, learns the email domain + local-part pattern from
employees who already have emails, then applies that pattern to a target name.

Usage:
  # Show learned pattern + all referral emails
  python3 skills/job-reachout/scripts/infer_email.py --company "Google"

  # Infer email(s) for a person you want to reach out to
  python3 skills/job-reachout/scripts/infer_email.py --company "Google" --name "Ben Willox"
  python3 skills/job-reachout/scripts/infer_email.py --company "Prior Labs" --name "Jane Doe" --json

  # Override / add a domain when referrals only have personal emails
  python3 skills/job-reachout/scripts/infer_email.py --company "Kipo AI" --name "Alex Kim" --domain kipo.ai

Flags guessed emails as try-this-may-bounce. Never invents a domain with no evidence
unless --domain is provided.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts", "notion"))
sys.path.insert(0, os.path.join(_REPO_ROOT, "skills", "job-eval"))

from config import NOTION_DB_COMPANIES  # noqa: E402
from get_referrals import fetch_contact  # noqa: E402
from notion_client import load_all_rows  # noqa: E402


PERSONAL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.in",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "icloud.com",
    "me.com",
    "protonmail.com",
    "proton.me",
    "aol.com",
    "mail.com",
    "qq.com",
    "163.com",
}

# Patterns we can detect and apply. Order is display preference only;
# voting decides the winner.
PATTERN_IDS = (
    "first",
    "first.last",
    "first_last",
    "first-last",
    "flast",
    "f.last",
    "firstl",
    "firstlast",
    "last",
    "last.first",
    "lastf",
)


@dataclass
class ReferralEmail:
    name: str
    email: str
    domain: str
    local: str
    matched_pattern: str | None
    is_personal: bool
    role: list[str]
    linkedin: str


@dataclass
class InferredEmail:
    email: str
    pattern: str
    domain: str
    confidence: str  # high | medium | low
    evidence_count: int
    note: str


def _ascii_fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _normalize_name_parts(full_name: str) -> list[str]:
    """Split a person name into lowercase alphabetic parts.

    Drops parenthetical nicknames, suffixes (Jr/Sr/III), and punctuation.
    """
    name = _ascii_fold(full_name)
    name = re.sub(r"\(.*?\)", " ", name)
    name = re.sub(r"[\"'`]", "", name)
    # Drop common relationship / noise phrases that appear in Connections
    lower = name.lower()
    for noise in (
        "brother in law",
        "sister in law",
        "friend",
        "roommate",
        "cousin",
        "uncle",
        "aunt",
    ):
        if noise in lower:
            # Keep only the part before the noise phrase when present
            name = re.split(re.escape(noise), name, flags=re.IGNORECASE)[0]
            break
    name = re.sub(r"[^A-Za-z\s\-]", " ", name)
    parts = [p for p in re.split(r"[\s\-]+", name.strip()) if p]
    skip = {"jr", "sr", "ii", "iii", "iv", "phd", "md", "mba"}
    parts = [p.lower() for p in parts if p.lower() not in skip]
    return parts


def _pattern_local(parts: list[str], pattern: str) -> str | None:
    """Build a local-part from name parts for a known pattern."""
    if not parts:
        return None
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    fi = first[0] if first else ""
    li = last[0] if last else ""

    if pattern == "first":
        return first
    if pattern == "last":
        return last or None
    if not last:
        # Multi-token patterns need a last name
        if pattern in {"first.last", "first_last", "first-last", "flast", "f.last", "firstl", "firstlast", "last.first", "lastf"}:
            return None
    if pattern == "first.last":
        return f"{first}.{last}"
    if pattern == "first_last":
        return f"{first}_{last}"
    if pattern == "first-last":
        return f"{first}-{last}"
    if pattern == "flast":
        return f"{fi}{last}"
    if pattern == "f.last":
        return f"{fi}.{last}"
    if pattern == "firstl":
        return f"{first}{li}"
    if pattern == "firstlast":
        return f"{first}{last}"
    if pattern == "last.first":
        return f"{last}.{first}"
    if pattern == "lastf":
        return f"{last}{fi}"
    return None


def detect_pattern(full_name: str, local: str) -> str | None:
    """Return the pattern id that explains local given full_name, or None."""
    parts = _normalize_name_parts(full_name)
    if not parts:
        return None
    local_norm = local.lower().strip()
    # Strip digits sometimes appended (jsmith2)
    local_base = re.sub(r"\d+$", "", local_norm)
    for pattern in PATTERN_IDS:
        candidate = _pattern_local(parts, pattern)
        if candidate and candidate == local_base:
            return pattern
        if candidate and candidate == local_norm:
            return pattern
    return None


def _split_email(email: str) -> tuple[str, str] | None:
    email = (email or "").strip().lower()
    if "@" not in email:
        return None
    local, domain = email.rsplit("@", 1)
    if not local or not domain:
        return None
    return local, domain


def find_company_row(company_name: str) -> dict | None:
    """Find a Companies DB row by exact or fuzzy name match.

    Returns dict with name, referral_ids, referral_link, or None.
    """
    rows = load_all_rows(NOTION_DB_COMPANIES, None)
    target = company_name.lower().strip()
    target_compact = re.sub(r"[^a-z0-9]", "", target)

    exact = None
    fuzzy: list[tuple[int, dict]] = []

    for row in rows:
        props = row.get("properties", {})
        name = "".join(
            t.get("plain_text", "") for t in props.get("Company", {}).get("title", [])
        ).strip()
        if not name:
            continue
        name_l = name.lower()
        name_compact = re.sub(r"[^a-z0-9]", "", name_l)
        refs = props.get("Referral", {}).get("relation", [])
        ref_link = props.get("Referral_Link", {}).get("url")
        record = {
            "name": name,
            "referral_ids": [r["id"] for r in refs],
            "referral_link": ref_link,
        }
        if name_l == target or name_compact == target_compact:
            exact = record
            break
        # Containment / prefix fuzzy
        if target in name_l or name_l in target or (
            target_compact and (target_compact in name_compact or name_compact in target_compact)
        ):
            score = difflib_ratio(target, name_l)
            fuzzy.append((score, record))

    if exact:
        return exact
    if fuzzy:
        fuzzy.sort(key=lambda x: x[0], reverse=True)
        if fuzzy[0][0] >= 0.6:
            return fuzzy[0][1]
    return None


def difflib_ratio(a: str, b: str) -> float:
    import difflib

    return difflib.SequenceMatcher(None, a, b).ratio()


def load_referral_emails(company_name: str) -> tuple[dict | None, list[ReferralEmail]]:
    """Load company row + referral contacts that have emails."""
    company = find_company_row(company_name)
    if not company:
        return None, []

    results: list[ReferralEmail] = []
    for pid in company["referral_ids"]:
        contact = fetch_contact(pid)
        if not contact:
            continue
        email = (contact.get("email") or "").strip()
        if not email:
            continue
        split = _split_email(email)
        if not split:
            continue
        local, domain = split
        is_personal = domain in PERSONAL_DOMAINS
        pattern = None if is_personal else detect_pattern(contact["name"], local)
        results.append(
            ReferralEmail(
                name=contact["name"],
                email=email.lower(),
                domain=domain,
                local=local,
                matched_pattern=pattern,
                is_personal=is_personal,
                role=contact.get("role") or [],
                linkedin=contact.get("linkedin") or "",
            )
        )
    return company, results


def _domain_matches_company(domain: str, company_name: str) -> float:
    """Score how well an email domain looks like the company name (0–1)."""
    company_compact = re.sub(r"[^a-z0-9]", "", company_name.lower())
    # Strip TLD(s): priorlabs.ai → priorlabs, getcandidly.com → getcandidly
    label = domain.lower().split(":")[-1]
    label = label.split("@")[-1]
    parts = label.split(".")
    # Drop common TLDs / dual TLDs (co.uk)
    while parts and parts[-1] in {
        "com", "ai", "io", "co", "org", "net", "dev", "app", "tech", "so",
        "xyz", "us", "uk", "in", "ca", "de", "fr",
    }:
        parts.pop()
    domain_compact = re.sub(r"[^a-z0-9]", "", "".join(parts))
    if not company_compact or not domain_compact:
        return 0.0
    if company_compact == domain_compact:
        return 1.0
    if company_compact in domain_compact or domain_compact in company_compact:
        return 0.85
    return difflib_ratio(company_compact, domain_compact)


def learn_pattern(
    referrals: list[ReferralEmail],
    domain_override: str | None = None,
    company_name: str | None = None,
) -> dict:
    """Vote on company domain + local-part pattern from referral emails."""
    work = [r for r in referrals if not r.is_personal]
    personal = [r for r in referrals if r.is_personal]

    domain_counts: Counter[str] = Counter()
    for r in work:
        domain_counts[r.domain] += 1

    domain = (domain_override or "").lower().strip() or None
    domain_source = "override" if domain else None
    if not domain and domain_counts:
        # Prefer domains that look like the company name, then by vote count.
        # Avoid letting a mis-tagged referral (e.g. oleg@sentient.xyz on Google)
        # win a tie against google.com.
        ranked = sorted(
            domain_counts.items(),
            key=lambda kv: (
                _domain_matches_company(kv[0], company_name or "") if company_name else 0.0,
                kv[1],
            ),
            reverse=True,
        )
        best_domain, best_count = ranked[0]
        best_score = _domain_matches_company(best_domain, company_name or "") if company_name else 0.0
        # If the top name-match is weak and another domain has more votes, use votes
        if company_name and best_score < 0.5:
            domain, _ = max(domain_counts.items(), key=lambda kv: kv[1])
            domain_source = "referrals_majority"
        else:
            domain = best_domain
            domain_source = "referrals_name_match" if best_score >= 0.5 else "referrals"

    # Learn local-part pattern only from emails on the chosen company domain
    pattern_counts: Counter[str] = Counter()
    evidence: list[dict] = []
    domain_matched = [r for r in work if domain and r.domain == domain]
    pattern_pool = domain_matched if domain_matched else work

    for r in pattern_pool:
        if r.matched_pattern:
            pattern_counts[r.matched_pattern] += 1
            evidence.append(
                {
                    "name": r.name,
                    "email": r.email,
                    "pattern": r.matched_pattern,
                }
            )

    pattern = None
    pattern_support = 0
    if pattern_counts:
        pattern, pattern_support = pattern_counts.most_common(1)[0]

    # Confidence for the learned pattern itself
    if pattern_support >= 2:
        pattern_confidence = "high"
    elif pattern_support == 1:
        pattern_confidence = "medium"
    else:
        pattern_confidence = "low"

    return {
        "domain": domain,
        "domain_source": domain_source,
        "domain_votes": dict(domain_counts),
        "pattern": pattern,
        "pattern_support": pattern_support,
        "pattern_votes": dict(pattern_counts),
        "pattern_confidence": pattern_confidence,
        "evidence": evidence,
        "work_email_count": len(work),
        "personal_email_count": len(personal),
        "off_domain_work_emails": [
            {"name": r.name, "email": r.email}
            for r in work
            if domain and r.domain != domain
        ],
        "unmatched_work_emails": [
            {"name": r.name, "email": r.email}
            for r in pattern_pool
            if not r.matched_pattern
        ],
    }


def infer_emails_for_name(
    full_name: str,
    learned: dict,
    max_candidates: int = 5,
) -> list[InferredEmail]:
    """Generate ranked email candidates for a target name."""
    parts = _normalize_name_parts(full_name)
    if not parts:
        return []

    domain = learned.get("domain")
    if not domain:
        return []

    primary = learned.get("pattern")
    votes: dict[str, int] = learned.get("pattern_votes") or {}
    support = learned.get("pattern_support") or 0

    # Candidate patterns: primary first, then other observed patterns, then common fallbacks
    ordered: list[str] = []
    if primary:
        ordered.append(primary)
    for p, _ in sorted(votes.items(), key=lambda x: (-x[1], x[0])):
        if p not in ordered:
            ordered.append(p)
    for p in ("first.last", "first", "flast", "firstlast", "f.last"):
        if p not in ordered:
            ordered.append(p)

    seen_locals: set[str] = set()
    out: list[InferredEmail] = []
    for i, pattern in enumerate(ordered):
        local = _pattern_local(parts, pattern)
        if not local or local in seen_locals:
            continue
        seen_locals.add(local)
        email = f"{local}@{domain}"

        if pattern == primary and support >= 2:
            confidence = "high"
            note = f"matches dominant pattern seen {support}x — try this, may bounce"
        elif pattern == primary and support == 1:
            confidence = "medium"
            note = "matches single observed pattern — try this, may bounce"
        elif pattern in votes:
            confidence = "medium"
            note = f"secondary pattern seen {votes[pattern]}x — try this, may bounce"
        else:
            confidence = "low"
            note = "common fallback (no referral evidence for this pattern) — try this, may bounce"

        # First fallback after observed patterns stays low
        if i > 0 and pattern not in votes and primary:
            confidence = "low"

        out.append(
            InferredEmail(
                email=email,
                pattern=pattern,
                domain=domain,
                confidence=confidence,
                evidence_count=votes.get(pattern, 0) if pattern in votes else (support if pattern == primary else 0),
                note=note,
            )
        )
        if len(out) >= max_candidates:
            break

    return out


def format_text(
    company_query: str,
    company: dict | None,
    referrals: list[ReferralEmail],
    learned: dict,
    target_name: str | None,
    inferred: list[InferredEmail],
) -> str:
    lines: list[str] = []
    if not company:
        lines.append(f"Company not found in Companies DB: {company_query!r}")
        lines.append("Check the exact name in Notion, or pass a closer spelling.")
        return "\n".join(lines)

    matched = company["name"]
    if matched.lower() != company_query.lower().strip():
        lines.append(f"Company: {matched}  (matched from {company_query!r})")
    else:
        lines.append(f"Company: {matched}")
    if company.get("referral_link"):
        lines.append(f"Referral link: {company['referral_link']}")
    lines.append(f"Referrals with email: {len(referrals)} "
                 f"({learned['work_email_count']} work, {learned['personal_email_count']} personal)")
    lines.append("")

    if referrals:
        lines.append("Referral emails:")
        for r in referrals:
            tag = "personal" if r.is_personal else (r.matched_pattern or "unmatched")
            lines.append(f"  - {r.name}: {r.email}  [{tag}]")
        lines.append("")

    lines.append("Learned pattern:")
    if learned["domain"]:
        lines.append(f"  Domain:  {learned['domain']}  (source: {learned['domain_source']})")
    else:
        lines.append("  Domain:  —  (no work-domain emails; pass --domain)")
    if learned["pattern"]:
        lines.append(
            f"  Pattern: {learned['pattern']}  "
            f"(support={learned['pattern_support']}, confidence={learned['pattern_confidence']})"
        )
    else:
        lines.append("  Pattern: —  (could not map any referral name → local-part)")
    if learned["domain_votes"]:
        lines.append(f"  Domain votes:  {learned['domain_votes']}")
    if learned["pattern_votes"]:
        lines.append(f"  Pattern votes: {learned['pattern_votes']}")
    if learned["unmatched_work_emails"]:
        lines.append("  Unmatched work emails (name didn't fit a known pattern):")
        for u in learned["unmatched_work_emails"]:
            lines.append(f"    - {u['name']}: {u['email']}")
    if learned.get("off_domain_work_emails"):
        lines.append("  Off-domain work emails (ignored for pattern learning):")
        for u in learned["off_domain_work_emails"]:
            lines.append(f"    - {u['name']}: {u['email']}")

    if target_name:
        lines.append("")
        lines.append(f"Inferred for {target_name!r}:")
        if not inferred:
            lines.append("  — none (need a domain; pass --domain or add work emails to referrals)")
        else:
            for i, cand in enumerate(inferred, 1):
                lines.append(
                    f"  {i}. {cand.email}  [{cand.confidence}]  pattern={cand.pattern}"
                )
                lines.append(f"     {cand.note}")

    return "\n".join(lines)


def build_result(
    company_query: str,
    company: dict | None,
    referrals: list[ReferralEmail],
    learned: dict,
    target_name: str | None,
    inferred: list[InferredEmail],
) -> dict:
    return {
        "query_company": company_query,
        "matched_company": company["name"] if company else None,
        "referral_link": company.get("referral_link") if company else None,
        "referrals": [asdict(r) for r in referrals],
        "learned": learned,
        "target_name": target_name,
        "inferred": [asdict(c) for c in inferred],
        "disclaimer": "Inferred emails are guesses from referral patterns — try this, may bounce.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Infer work emails from company referral email patterns"
    )
    parser.add_argument("--company", required=True, help="Company name (Companies DB)")
    parser.add_argument(
        "--name",
        help="Target person to infer an email for (e.g. 'Ben Willox')",
    )
    parser.add_argument(
        "--domain",
        help="Force company email domain (e.g. exacare.com) when referrals lack work emails",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Max inferred candidates to return (default: 5)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    company, referrals = load_referral_emails(args.company)
    empty_learned = {
        "domain": (args.domain or "").lower().strip() or None,
        "domain_source": "override" if args.domain else None,
        "domain_votes": {},
        "pattern": None,
        "pattern_support": 0,
        "pattern_votes": {},
        "pattern_confidence": "low",
        "evidence": [],
        "work_email_count": 0,
        "personal_email_count": 0,
        "off_domain_work_emails": [],
        "unmatched_work_emails": [],
    }
    if company:
        learned = learn_pattern(
            referrals,
            domain_override=args.domain,
            company_name=company["name"],
        )
    else:
        learned = empty_learned

    # If company missing but --domain + --name given, still allow fallback inference
    inferred: list[InferredEmail] = []
    if args.name:
        if not learned.get("pattern") and learned.get("domain"):
            # No observed pattern — still generate common fallbacks
            learned = {
                **learned,
                "pattern": "first.last",
                "pattern_support": 0,
                "pattern_confidence": "low",
            }
        inferred = infer_emails_for_name(args.name, learned, max_candidates=args.top)

    if args.json:
        print(json.dumps(
            build_result(args.company, company, referrals, learned, args.name, inferred),
            indent=2,
        ))
    else:
        print(format_text(args.company, company, referrals, learned, args.name, inferred))


if __name__ == "__main__":
    main()

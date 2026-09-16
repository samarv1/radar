"""Shared company-name normalization and fuzzy matching."""

import re
from collections.abc import Sequence

from rapidfuzz import fuzz, process


_LEGAL_SUFFIXES = re.compile(
    r"\b(inc|llc|corp|ltd|co|incorporated|limited|company|technologies|technology|"
    r"solutions|software|labs|lab|studio|studios|ai|io|app|apps|group|ventures|"
    r"holdings|capital|partners|fund|management|pbc)\b",
    re.IGNORECASE,
)
_TICKER = re.compile(r"\s*\([A-Z][A-Z0-9\s,]*\)")
_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")
_TRAILING_LEGAL_SUFFIXES = re.compile(
    r"(?:\s+\b(?:inc|incorporated|llc|ltd|limited|corp|corporation|company|co|pbc)\b\.?)+$",
    re.IGNORECASE,
)


def normalize_company_name(name: str) -> str:
    name = _TICKER.sub("", name)
    name = _PUNCTUATION.sub(" ", name.lower())
    name = _LEGAL_SUFFIXES.sub(" ", name)
    return _WHITESPACE.sub(" ", name).strip()


def normalize_company_identity(name: str) -> str:
    """Normalize legal suffixes while preserving words that distinguish companies."""
    name = _TICKER.sub("", name)
    name = _PUNCTUATION.sub(" ", name.lower())
    name = _WHITESPACE.sub(" ", name).strip()
    return _TRAILING_LEGAL_SUFFIXES.sub("", name).strip()


def find_exact_company_match(
    company_name: str,
    normalized_candidates: Sequence[str],
) -> int | None:
    normalized = normalize_company_identity(company_name)
    if not normalized:
        return None
    try:
        return normalized_candidates.index(normalized)
    except ValueError:
        return None


def find_company_match(
    company_name: str,
    normalized_candidates: Sequence[str],
    *,
    threshold: float,
) -> tuple[int, float] | None:
    normalized = normalize_company_name(company_name)
    if not normalized:
        return None
    result = process.extractOne(
        normalized,
        normalized_candidates,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold,
    )
    if result is None:
        return None
    _, score, index = result
    return index, score

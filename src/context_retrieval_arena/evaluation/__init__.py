"""Deterministic lexical and page-overlap metrics, not semantic judgments."""

import re
import unicodedata
from collections import Counter

VERSION = "lexical-pages-v1"
CITATION = re.compile(r"\[page\s+(\d+)\]", re.IGNORECASE)


def tokens(text: str) -> list[str]:
    text = CITATION.sub(" ", text)
    return re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold())


def score(answer: str, reference: str | None, evidence: list[int] | None,
          supplied: list[int], page_count: int, *, complete: bool = True) -> dict:
    cited = sorted({int(p) for p in CITATION.findall(answer)})
    valid_cited = {p for p in cited if 1 <= p <= page_count}
    exact = f1 = None
    if reference is not None:
        expected, actual = tokens(reference), tokens(answer)
        exact = float(complete and actual == expected)
        overlap = sum((Counter(expected) & Counter(actual)).values())
        f1 = (2 * overlap / (len(expected) + len(actual))) if expected or actual else 1.0
        if not complete:
            f1 = 0.0
    relevant = set(evidence or [])
    return {
        "exact_match": exact,
        "token_f1": f1,
        "cited_pages": cited,
        "invalid_cited_pages": sorted(set(cited) - valid_cited),
        "supplied_page_recall": len(relevant & set(supplied)) / len(relevant) if relevant else None,
        "cited_page_recall": (len(relevant & valid_cited) / len(relevant) if complete else 0.0) if relevant else None,
        "cited_page_precision": (len(relevant & valid_cited) / len(cited) if complete else 0.0) if relevant and cited else (0.0 if relevant else None),
    }

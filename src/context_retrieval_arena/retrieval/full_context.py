from dataclasses import dataclass

from ..models import Document


@dataclass(frozen=True)
class Context:
    text: str
    page_numbers: list[int]


def retrieve(document: Document, question: str) -> Context:
    """Include every page in order, without chunking or truncation."""
    return Context(
        "\n\n".join(f"[PDF PAGE {p.number}]\n{p.text}" for p in document.pages),
        [p.number for p in document.pages],
    )

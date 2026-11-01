"""Local preflight checks; no credentials, API calls, or token estimates."""

from .models import Document, Question


def check_inputs(document: Document, questions: list[Question], min_pages: int = 150,
                 require_references: bool = False) -> dict:
    if min_pages < 1:
        raise ValueError("min_pages must be positive")
    empty = [p.number for p in document.pages if not p.text.strip()]
    missing_answers = [q.id for q in questions if q.reference_answer is None]
    missing_evidence = [q.id for q in questions if q.answerable and not q.evidence_pages]
    errors, warnings = [], []
    if len(document.pages) < min_pages:
        errors.append(f"Expected at least {min_pages} pages; found {len(document.pages)}")
    if not questions:
        errors.append("Dataset contains no questions")
    if require_references and (missing_answers or missing_evidence):
        errors.append("Every question requires a reference answer; answerable questions require evidence_pages")
    if empty:
        warnings.append("Some pages have no text; inspect for scans, figures, or extraction loss")
    if len(questions) < 100:
        warnings.append("Dataset has fewer than 100 questions; suitable for a pilot only")
    if missing_answers or missing_evidence:
        warnings.append("Some questions cannot be fully evaluated")
    return {"passed": not errors, "errors": errors, "warnings": warnings,
            "page_count": len(document.pages), "question_count": len(questions),
            "unanswerable_count": sum(not q.answerable for q in questions),
            "empty_text_pages": empty, "missing_reference_ids": missing_answers,
            "missing_evidence_ids": missing_evidence,
            "extracted_characters": sum(len(p.text) for p in document.pages),
            "manual_checks_required": ["extraction fidelity", "reference correctness", "evidence support"],
            "unverified": ["model context capacity", "live provider access", "provider caching"]}

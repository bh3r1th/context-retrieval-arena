"""Sequential baseline runner; every question receives the same complete document."""

import hashlib
import json
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from time import perf_counter

from .generation import PROMPT_VERSION, Provider, build_prompt
from .evaluation import VERSION as EVALUATION_VERSION, score
from .models import Document, GenerationConfig, Question, Usage
from .pricing import Pricing
from .retrieval.full_context import retrieve


def load_questions(text: str, page_count: int) -> list[Question]:
    data = json.loads(text)
    if not isinstance(data, list) or not data:
        raise ValueError("Dataset must be a nonempty JSON array")
    questions = []
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each question must be an object")
        try:
            q = Question(**item)
        except TypeError as exc:
            raise ValueError("Question has missing or unknown fields") from exc
        if not isinstance(q.id, str) or not q.id.strip() or q.id in seen:
            raise ValueError("Question IDs must be nonempty, unique strings")
        if not isinstance(q.question, str) or not q.question.strip():
            raise ValueError("Question text must be nonempty")
        if q.reference_answer is not None and (
            not isinstance(q.reference_answer, str) or not q.reference_answer.strip()
        ):
            raise ValueError("reference_answer must be a nonempty string")
        if q.evidence_pages is not None and (
            not isinstance(q.evidence_pages, list)
            or any(type(p) is not int or not 1 <= p <= page_count for p in q.evidence_pages)
        ):
            raise ValueError("evidence_pages must contain valid one-based PDF page numbers")
        if q.evidence_pages and len(set(q.evidence_pages)) != len(q.evidence_pages):
            raise ValueError("evidence_pages must not contain duplicates")
        seen.add(q.id)
        questions.append(q)
    return questions


def run_baseline(document: Document, questions: list[Question], provider: Provider,
                 config: GenerationConfig, pricing: Pricing | None = None) -> tuple[dict, list[dict]]:
    if not questions:
        raise ValueError("At least one question is required")
    if pricing and pricing.model != config.model:
        raise ValueError("Pricing model must exactly match the requested generation model")
    started = perf_counter()
    rows = []
    for question in questions:
        query_started = perf_counter()
        context = retrieve(document, question.question)
        prompt = build_prompt(context.text, question.question)
        retrieval_seconds = perf_counter() - query_started
        generation_started = perf_counter()
        error_type = None
        answer = None
        try:
            answer = provider.generate(prompt, config)
        except Exception as exc:
            # Do not serialize provider messages: they may contain credentials.
            error_type = type(exc).__name__
        generation_seconds = perf_counter() - generation_started
        query_seconds = perf_counter() - query_started
        usage = answer.usage if answer else Usage()
        text = answer.text if answer else ""
        finish = answer.finish_reason if answer else None
        complete = bool(text.strip()) and str(finish).rsplit(".", 1)[-1] == "STOP"
        status = "error" if error_type else ("ok" if complete else "incomplete")
        rows.append({
            "question_id": question.id,
            "question": question.question,
            "reference_answer": question.reference_answer,
            "reference_evidence_pages": question.evidence_pages,
            "answer": text,
            "status": status,
            "error_type": error_type,
            "supplied_pages": context.page_numbers,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "usage": asdict(usage),
            "retrieval_seconds": retrieval_seconds,
            "generation_seconds": generation_seconds,
            "query_seconds": query_seconds,
            "model_version": answer.model_version if answer else None,
            "finish_reason": finish,
            "cost_usd": pricing.estimate(usage) if pricing else None,
            "evaluation": score(text, question.reference_answer, question.evidence_pages,
                                context.page_numbers, len(document.pages), complete=complete),
        })
    return {
        "schema_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "full_context",
        "provider": provider.name,
        "generation": asdict(config),
        "prompt_version": PROMPT_VERSION,
        "python_version": platform.python_version(),
        "document_sha256": document.source_sha256,
        "document_content_sha256": hashlib.sha256(json.dumps(
            [asdict(p) for p in document.pages], sort_keys=True, ensure_ascii=False
        ).encode()).hexdigest(),
        "question_count": len(questions),
        "page_count": len(document.pages),
        "evaluation_version": EVALUATION_VERSION,
        "extractor_version": document.extractor_version,
        "extraction_seconds": document.extraction_seconds,
        "dataset_sha256": hashlib.sha256(json.dumps(
            [asdict(q) for q in questions], sort_keys=True, ensure_ascii=False
        ).encode()).hexdigest(),
        "run_seconds": perf_counter() - started,
        "cache_policy": "provider_default; uncontrolled",
        "measurement_scope": "query includes retrieval, prompt assembly, and generation; excludes ingestion and artifact I/O",
        "cost_policy": "flat token estimate; excludes cache storage, retries not reflected in usage, and other fees" if pricing else "unpriced",
        "pricing": asdict(pricing) if pricing else None,
    }, rows

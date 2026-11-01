"""Sequential baseline runner; every question receives the same complete document."""

import hashlib
import json
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from time import perf_counter

from .generation import PROMPT_VERSION, Provider, build_prompt
from .models import Document, GenerationConfig, Question
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
        q = Question(**item)
        if not isinstance(q.id, str) or not q.id.strip() or q.id in seen:
            raise ValueError("Question IDs must be nonempty, unique strings")
        if not isinstance(q.question, str) or not q.question.strip():
            raise ValueError("Question text must be nonempty")
        if q.reference_answer is not None and not isinstance(q.reference_answer, str):
            raise ValueError("reference_answer must be a string")
        if q.evidence_pages is not None and (
            not isinstance(q.evidence_pages, list)
            or any(type(p) is not int or not 1 <= p <= page_count for p in q.evidence_pages)
        ):
            raise ValueError("evidence_pages must contain valid one-based PDF page numbers")
        seen.add(q.id)
        questions.append(q)
    return questions


def run_baseline(document: Document, questions: list[Question], provider: Provider,
                 config: GenerationConfig) -> tuple[dict, list[dict]]:
    if not questions:
        raise ValueError("At least one question is required")
    started = perf_counter()
    rows = []
    for question in questions:
        query_started = perf_counter()
        context = retrieve(document, question.question)
        prompt = build_prompt(context.text, question.question)
        generation_started = perf_counter()
        answer = provider.generate(prompt, config)
        generation_seconds = perf_counter() - generation_started
        rows.append({
            "question_id": question.id,
            "question": question.question,
            "reference_answer": question.reference_answer,
            "reference_evidence_pages": question.evidence_pages,
            "answer": answer.text,
            "supplied_pages": context.page_numbers,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "usage": asdict(answer.usage),
            "generation_seconds": generation_seconds,
            "query_seconds": perf_counter() - query_started,
            "model_version": answer.model_version,
            "finish_reason": answer.finish_reason,
            "cost_usd": None,
        })
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "full_context",
        "provider": provider.name,
        "generation": asdict(config),
        "prompt_version": PROMPT_VERSION,
        "python_version": platform.python_version(),
        "document_sha256": document.source_sha256,
        "extractor_version": document.extractor_version,
        "extraction_seconds": document.extraction_seconds,
        "dataset_sha256": hashlib.sha256(json.dumps(
            [asdict(q) for q in questions], sort_keys=True, ensure_ascii=False
        ).encode()).hexdigest(),
        "run_seconds": perf_counter() - started,
        "cache_policy": "provider_default; uncontrolled",
        "measurement_scope": "query includes retrieval, prompt assembly, and generation; excludes ingestion and artifact I/O",
        "cost_policy": "unpriced; token usage retained for later model-specific pricing",
    }, rows

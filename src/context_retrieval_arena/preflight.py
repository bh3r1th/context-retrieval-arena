"""Remote token counting only: never calls answer generation."""

import hashlib
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Protocol

from .benchmark import fingerprints
from .generation import PROMPT_VERSION, build_prompt
from .models import Document, GenerationConfig, Question
from .retrieval.full_context import retrieve


class TokenCounter(Protocol):
    name: str

    def count_tokens(self, prompt: str, model: str) -> int: ...
    def model_limits(self, model: str) -> tuple[int, int]: ...


def count_prompts(document: Document, questions: list[Question], provider: TokenCounter,
                  config: GenerationConfig, *, limits: tuple[int, int] | None = None,
                  limits_source: str | None = None) -> dict:
    if not questions:
        raise ValueError("At least one question is required")
    if limits is not None:
        if not limits_source or not limits_source.strip():
            raise ValueError("Explicit model limits require a source URL or reference")
        input_limit, output_limit = limits
    else:
        if limits_source is not None:
            raise ValueError("limits_source requires explicit limits")
        input_limit, output_limit = provider.model_limits(config.model)
    if any(type(n) is not int or n < 1 for n in (input_limit, output_limit)):
        raise ValueError("Provider model limits are missing or invalid")
    rows = []
    for question in questions:
        context = retrieve(document, question.question)
        prompt = build_prompt(context.text, question.question)
        count = provider.count_tokens(prompt, config.model)
        if type(count) is not int or count < 1:
            raise ValueError("Provider prompt token count is missing or invalid")
        rows.append({"question_id": question.id, "input_tokens": count,
                     "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                     "fits_input_limit": count <= input_limit,
                     "fits_with_output_reserve": count + config.max_output_tokens <= input_limit})
    output_fits = config.max_output_tokens <= output_limit
    return {"schema_version": 1, "counted_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider.name, "generation": asdict(config),
            "provider_connection": getattr(provider, "connection", None),
            "limits_source": limits_source if limits is not None else "provider model metadata",
            "limits_verified_by_provider": limits is None,
            "prompt_version": PROMPT_VERSION, **fingerprints(document, questions),
            "input_token_limit": input_limit, "output_token_limit": output_limit,
            "output_limit_passed": output_fits,
            "passed": output_fits and all(row["fits_with_output_reserve"] for row in rows),
            "policy": "conservative: input plus reserved output must fit input limit; output must fit output limit",
            "limitations": "Counts do not verify generation access, billing, cache behavior, or model-specific thinking allocation. Recount if inputs, prompts, model, or settings change.",
            "questions": rows}

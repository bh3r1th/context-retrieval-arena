"""Small, serializable contracts shared between pipeline stages."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    number: int  # One-based PDF page number, not the printed page label.
    text: str


@dataclass(frozen=True)
class Document:
    schema_version: int
    source_name: str
    source_sha256: str
    extractor_version: str
    extraction_seconds: float
    pages: list[Page]


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    reference_answer: str | None = None
    evidence_pages: list[int] | None = None


@dataclass(frozen=True)
class GenerationConfig:
    model: str
    temperature: float = 0.0
    max_output_tokens: int = 2048
    seed: int | None = None

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model must be specified explicitly")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class Generation:
    text: str
    usage: Usage
    model_version: str | None = None
    finish_reason: str | None = None

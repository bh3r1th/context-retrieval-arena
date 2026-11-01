"""Explicit flat USD token rates; no inferred prices or missing-token assumptions."""

import math
from dataclasses import asdict, dataclass
from datetime import date

from .models import Usage


@dataclass(frozen=True)
class Pricing:
    model: str
    effective_date: str
    source: str
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float
    reasoning_per_million: float
    currency: str = "USD"

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.source.strip() or self.currency != "USD":
            raise ValueError("Pricing requires a model, source, and USD currency")
        date.fromisoformat(self.effective_date)
        for field, value in asdict(self).items():
            if field.endswith("per_million") and (
                type(value) not in (int, float) or not math.isfinite(value) or value < 0
            ):
                raise ValueError("Token rates must be finite nonnegative numbers")

    def estimate(self, usage: Usage) -> float | None:
        counts = [usage.input_tokens, usage.cached_input_tokens, usage.output_tokens, usage.reasoning_tokens]
        if any(type(n) is not int or n < 0 for n in counts):
            return None
        inputs, cached, outputs, reasoning = counts
        if cached > inputs:
            return None
        estimate = ((inputs - cached) * self.input_per_million
                + cached * self.cached_input_per_million
                + outputs * self.output_per_million
                + reasoning * self.reasoning_per_million) / 1_000_000
        return estimate if math.isfinite(estimate) else None

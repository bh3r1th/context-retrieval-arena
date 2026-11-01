"""Thin adapter around Google's optional official SDK."""

from ..models import Generation, GenerationConfig, Usage


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str) -> None:
        from google import genai

        self.client = genai.Client(api_key=api_key, http_options={"timeout": 120_000})

    def close(self) -> None:
        self.client.close()

    def count_tokens(self, prompt: str, model: str) -> int:
        response = self.client.models.count_tokens(model=model, contents=prompt)
        if type(response.total_tokens) is not int or response.total_tokens < 1:
            raise ValueError("Provider returned no valid prompt token count")
        return response.total_tokens

    def model_limits(self, model: str) -> tuple[int, int]:
        info = self.client.models.get(model=model)
        values = info.input_token_limit, info.output_token_limit
        if any(type(value) is not int or value < 1 for value in values):
            raise ValueError("Provider did not return valid input/output limits")
        return values

    def generate(self, prompt: str, config: GenerationConfig) -> Generation:
        from google.genai import types

        response = self.client.models.generate_content(
            model=config.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=config.temperature,
                max_output_tokens=config.max_output_tokens,
                seed=config.seed,
                candidate_count=1,
            ),
        )
        text = response.text
        metadata = response.usage_metadata
        usage = Usage() if metadata is None else Usage(
            input_tokens=metadata.prompt_token_count,
            output_tokens=metadata.candidates_token_count,
            cached_input_tokens=metadata.cached_content_token_count,
            reasoning_tokens=metadata.thoughts_token_count,
            total_tokens=metadata.total_token_count,
        )
        finish = response.candidates[0].finish_reason if response.candidates else None
        return Generation(text or "", usage, response.model_version, str(finish) if finish else None)

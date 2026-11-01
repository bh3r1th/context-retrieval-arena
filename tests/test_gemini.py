"""Exercise the real SDK response types without network calls or API keys."""

import importlib.util
import unittest
from unittest.mock import patch

from context_retrieval_arena.generation.gemini import GeminiProvider
from context_retrieval_arena.models import GenerationConfig

try:
    SDK_INSTALLED = importlib.util.find_spec("google.genai") is not None
except ModuleNotFoundError:
    SDK_INSTALLED = False


@unittest.skipUnless(SDK_INSTALLED, "optional Gemini extra not installed")
class GeminiTests(unittest.TestCase):
    def test_token_count_and_model_limits_use_sdk_without_generation(self):
        from google.genai import types

        provider = GeminiProvider("offline-test-key")
        try:
            with patch.object(provider.client.models, "count_tokens", return_value=types.CountTokensResponse(total_tokens=123)) as count, patch.object(provider.client.models, "get", return_value=types.Model(input_token_limit=1000, output_token_limit=200)), patch.object(provider.client.models, "generate_content") as generate:
                self.assertEqual(provider.model_limits("test"), (1000, 200))
                self.assertEqual(provider.count_tokens("exact prompt", "test"), 123)
                count.assert_called_once_with(model="test", contents="exact prompt")
                generate.assert_not_called()
            with patch.object(provider.client.models, "count_tokens", return_value=types.CountTokensResponse()), self.assertRaises(ValueError):
                provider.count_tokens("test", "test")
            with patch.object(provider.client.models, "get", return_value=types.Model()), self.assertRaises(ValueError):
                provider.model_limits("test")
        finally:
            provider.close()

    def test_sdk_config_and_usage_mapping(self):
        from google.genai import types

        response = types.GenerateContentResponse(
            candidates=[types.Candidate(
                content=types.Content(parts=[types.Part(text="Answer [page 1]")]),
                finish_reason="STOP",
            )],
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=100, candidates_token_count=20,
                cached_content_token_count=50, thoughts_token_count=7, total_token_count=127,
            ),
            model_version="test-version",
        )
        provider = GeminiProvider("offline-test-key")
        try:
            with patch.object(provider.client.models, "generate_content", return_value=response) as generate:
                result = provider.generate("test prompt", GenerationConfig("test-model", seed=42))
            self.assertEqual(result.text, "Answer [page 1]")
            self.assertEqual(result.usage.input_tokens, 100)
            self.assertEqual(result.usage.cached_input_tokens, 50)
            self.assertEqual(result.usage.reasoning_tokens, 7)
            self.assertEqual(result.usage.total_tokens, 127)
            self.assertEqual(result.model_version, "test-version")
            self.assertIn("STOP", result.finish_reason)
            sent = generate.call_args.kwargs
            self.assertEqual(sent["model"], "test-model")
            self.assertEqual(sent["contents"], "test prompt")
            self.assertEqual(sent["config"].seed, 42)
            self.assertEqual(sent["config"].temperature, 0)
            self.assertEqual(sent["config"].max_output_tokens, 2048)
        finally:
            provider.close()

    def test_empty_response_retains_usage_and_finish_reason(self):
        from google.genai import types

        provider = GeminiProvider("offline-test-key")
        try:
            response = types.GenerateContentResponse(
                usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=100),
                candidates=[types.Candidate(finish_reason="SAFETY")],
            )
            with patch.object(provider.client.models, "generate_content", return_value=response):
                result = provider.generate("test", GenerationConfig("test"))
            self.assertEqual(result.text, "")
            self.assertEqual(result.usage.input_tokens, 100)
            self.assertIn("SAFETY", result.finish_reason)
        finally:
            provider.close()

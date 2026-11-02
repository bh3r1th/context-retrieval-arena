import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from context_retrieval_arena.benchmark import run_baseline
from context_retrieval_arena.cli import main
from context_retrieval_arena.generation.gemini import GeminiProvider
from context_retrieval_arena.models import Generation, GenerationConfig, Question, Usage
from context_retrieval_arena.preflight import count_prompts
from context_retrieval_arena.reporting import compare_runs, write_results
from test_preflight import document
from test_gemini import SDK_INSTALLED


class VertexFixture:
    name = "vertex_ai"

    def __init__(self, *, vertexai, project, location):
        assert vertexai is True
        self.connection = {"backend": "vertex", "project": project, "location": location}

    def close(self):
        pass

    def model_limits(self, model):
        raise AssertionError("Explicit limits should avoid the unsupported metadata path")

    def count_tokens(self, prompt, model):
        return 100

    def generate(self, prompt, config):
        return Generation("answer [page 1]", Usage(100, 10, 0, 0, 110), "test-v1", "STOP")


class VertexPreflightTests(unittest.TestCase):
    def test_explicit_limits_record_provenance_and_skip_metadata(self):
        provider = VertexFixture(vertexai=True, project="project-test", location="global")
        result = count_prompts(document(), [Question("q", "Q")], provider,
                               GenerationConfig("test", max_output_tokens=150),
                               limits=(1000, 200), limits_source="https://example.com/model-spec")
        self.assertTrue(result["passed"])
        self.assertFalse(result["limits_verified_by_provider"])
        self.assertEqual(result["limits_source"], "https://example.com/model-spec")
        self.assertEqual(result["provider_connection"]["location"], "global")
        with self.assertRaises(ValueError):
            count_prompts(document(), [Question("q", "Q")], provider,
                          GenerationConfig("test"), limits=(1000, 200))

    def test_reports_reject_mixed_vertex_locations(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = []
            for location in ["global", "us-central1"]:
                provider = VertexFixture(vertexai=True, project="project-test", location=location)
                manifest, rows = run_baseline(document(), [Question("q", "Q")], provider, GenerationConfig("test"))
                path = Path(temp) / location
                write_results(path, manifest, rows)
                paths.append(path / "results.json")
            with self.assertRaises(ValueError):
                compare_runs(paths)


@unittest.skipUnless(SDK_INSTALLED, "optional Gemini extra not installed")
class VertexSDKTests(unittest.TestCase):
    def test_adc_client_uses_project_and_global_without_api_key(self):
        with patch("google.genai.Client") as client:
            provider = GeminiProvider(vertexai=True, project="project-test")
            client.assert_called_once_with(vertexai=True, project="project-test", location="global", http_options={"timeout": 120_000})
            self.assertEqual(provider.name, "vertex_ai")
            provider.close()
            client.return_value.close.assert_called_once()

    def test_developer_client_explicitly_disables_vertex_mode(self):
        with patch("google.genai.Client") as client:
            GeminiProvider("offline-test-key")
            client.assert_called_once_with(vertexai=False, api_key="offline-test-key", http_options={"timeout": 120_000})

    def test_invalid_backend_combinations_fail_before_client_creation(self):
        for args in [dict(vertexai=True), dict(vertexai=True, project=" "),
                     dict(vertexai=True, project="project-test", api_key="offline"),
                     dict(api_key="offline", project="project-test")]:
            with self.subTest(args=args), patch("google.genai.Client") as client:
                with self.assertRaises(ValueError):
                    GeminiProvider(**args)
                client.assert_not_called()


class VertexCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.doc, self.questions = self.root / "doc.json", self.root / "questions.json"
        self.doc.write_text(json.dumps(asdict(document())))
        self.questions.write_text('[{"id":"q", "question":"Question?"}]')

    def args(self, command, output):
        return ["cra", command, "--document", str(self.doc), "--questions", str(self.questions),
                "--backend", "vertex", "--model", "test", "--max-output-tokens", "150", "--output", str(output)]

    def test_vertex_cli_tokens_without_api_key_and_generation_records_project(self):
        environment = {"GOOGLE_CLOUD_PROJECT": "project-test", "GOOGLE_CLOUD_LOCATION": "",
                       "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}
        token_path = self.root / "tokens.json"
        args = self.args("tokens", token_path) + ["--input-token-limit", "1000", "--output-token-limit", "200", "--limits-source", "verified documentation"]
        with patch.dict("os.environ", environment), patch("context_retrieval_arena.generation.gemini.GeminiProvider", VertexFixture), patch("sys.argv", args), redirect_stdout(io.StringIO()):
            main()
        result = json.loads(token_path.read_text())
        self.assertTrue(result["passed"])
        self.assertEqual(result["provider_connection"], {"backend": "vertex", "project": "project-test", "location": "global"})
        run_path = self.root / "run"
        with patch.dict("os.environ", environment), patch("context_retrieval_arena.generation.gemini.GeminiProvider", VertexFixture), patch("sys.argv", self.args("run", run_path)), redirect_stdout(io.StringIO()):
            main()
        result = json.loads((run_path / "results.json").read_text())
        self.assertEqual(result["manifest"]["provider"], "vertex_ai")
        self.assertEqual(result["manifest"]["provider_connection"]["project"], "project-test")

    def test_invalid_cli_options_fail_before_client_creation(self):
        base = self.args("tokens", self.root / "tokens.json")
        flags = ["--input-token-limit", "1000", "--output-token-limit", "200", "--limits-source", "docs"]
        for args in [base, base + ["--input-token-limit", "1000"], base + flags,
                     self.args("run", self.root / "run") + ["--backend", "developer", "--project", "project-test"]]:
            with self.subTest(args=args), patch.dict("os.environ", {"GOOGLE_CLOUD_PROJECT": ""}), patch("sys.argv", args), patch("context_retrieval_arena.generation.gemini.GeminiProvider") as client, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as status:
                main()
            self.assertEqual(status.exception.code, 2)
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()

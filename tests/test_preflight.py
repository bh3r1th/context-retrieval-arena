import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

from context_retrieval_arena.benchmark import load_questions, run_baseline
from context_retrieval_arena.checks import check_inputs
from context_retrieval_arena.cli import main
from context_retrieval_arena.models import Document, Generation, GenerationConfig, Page, Question, Usage
from context_retrieval_arena.preflight import count_prompts
from context_retrieval_arena.reporting import compare_runs, write_results

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/datasets/sec-regulation-best-interest-2018"


class Counter:
    name = "offline-test"

    def __init__(self, *args):
        self.prompts = []

    def model_limits(self, model):
        return 1000, 200

    def count_tokens(self, prompt, model):
        self.prompts.append(prompt)
        return 100

    def close(self):
        pass

    def generate(self, *args):
        raise AssertionError("Token preflight must never generate answers")


def document():
    return Document(1, "a.pdf", "a" * 64, "test", 0, [Page(1, "First page"), Page(2, "Last page")])


class TokenPreflightTests(unittest.TestCase):
    def test_counts_exact_generation_prompts_without_reference_leak(self):
        counter = Counter()
        questions = [Question("q", "Question?", "SECRET REFERENCE", [2])]
        config = GenerationConfig("test", max_output_tokens=150)
        result = count_prompts(document(), questions, counter, config)
        self.assertTrue(result["passed"])
        self.assertIn("First page", counter.prompts[0])
        self.assertIn("Last page", counter.prompts[0])
        self.assertNotIn("SECRET REFERENCE", counter.prompts[0])
        class Generator:
            name = "offline-test"
            def generate(self, prompt, config):
                self.prompt = prompt
                return Generation("answer", Usage(), None, "STOP")
        generator = Generator()
        _, rows = run_baseline(document(), questions, generator, config)
        self.assertEqual(generator.prompt, counter.prompts[0])
        self.assertEqual(rows[0]["prompt_sha256"], result["questions"][0]["prompt_sha256"])

    def test_overflow_output_reserve_and_missing_metadata(self):
        questions = [Question("q", "Question?")]
        for limits, count, output, passed in [((1000, 200), 100, 201, False),
                                              ((1000, 200), 900, 150, False),
                                              ((1000, 200), 1050, 150, False),
                                              ((1000, 200), 850, 150, True)]:
            counter = Counter()
            with patch.object(counter, "model_limits", return_value=limits), patch.object(counter, "count_tokens", return_value=count):
                result = count_prompts(document(), questions, counter, GenerationConfig("test", max_output_tokens=output))
            self.assertEqual(result["passed"], passed)
        for value in [None, -1, True, 0]:
            counter = Counter()
            with patch.object(counter, "count_tokens", return_value=value), self.assertRaises(ValueError):
                count_prompts(document(), questions, counter, GenerationConfig("test"))
        with patch.object(counter, "model_limits", return_value=(None, 100)), self.assertRaises(ValueError):
            count_prompts(document(), questions, counter, GenerationConfig("test"))

    def test_cli_writes_token_artifact_and_never_generates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            doc, questions = root / "doc.json", root / "questions.json"
            doc.write_text(json.dumps(asdict(document())))
            questions.write_text('[{"id":"q", "question":"Question?"}]')
            args = ["cra", "tokens", "--document", str(doc), "--questions", str(questions),
                    "--model", "test", "--max-output-tokens", "150", "--output", str(root / "tokens.json")]
            with patch("sys.argv", args), patch.dict("os.environ", {"GEMINI_API_KEY": "offline"}), patch("context_retrieval_arena.generation.gemini.GeminiProvider", Counter), redirect_stdout(io.StringIO()):
                main()
                result = json.loads((root / "tokens.json").read_text())
                self.assertTrue(result["passed"])
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as status:
                    main()
                self.assertEqual(status.exception.code, 2)

    def test_cli_requires_credentials_and_redacts_counting_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            doc, questions = root / "doc.json", root / "questions.json"
            doc.write_text(json.dumps(asdict(document())))
            questions.write_text('[{"id":"q", "question":"Question?"}]')
            args = ["cra", "tokens", "--document", str(doc), "--questions", str(questions),
                    "--model", "test", "--output", str(root / "tokens.json")]
            with patch("sys.argv", args), patch.dict("os.environ", {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}), patch("context_retrieval_arena.generation.gemini.GeminiProvider") as provider, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as status:
                main()
            self.assertEqual(status.exception.code, 2)
            provider.assert_not_called()
            stderr = io.StringIO()
            with patch("sys.argv", args), patch.dict("os.environ", {"GEMINI_API_KEY": "offline"}), patch("context_retrieval_arena.generation.gemini.GeminiProvider", Counter), patch.object(Counter, "count_tokens", side_effect=RuntimeError("sensitive-token-value")), redirect_stderr(stderr), self.assertRaises(SystemExit) as status:
                main()
            self.assertEqual(status.exception.code, 1)
            self.assertNotIn("sensitive-token-value", stderr.getvalue())
            self.assertFalse((root / "tokens.json").exists())


class PilotDatasetTests(unittest.TestCase):
    def test_evidence_quotes_and_fingerprints_match_the_stored_pdf(self):
        pdf = ROOT / "data/documents/sec-regulation-best-interest-2018/regulation-best-interest-proposed-rule.pdf"
        audit = json.loads((DATASET / "pilot.review.json").read_text())
        self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(), audit["document_sha256"])
        dataset = DATASET / "pilot.json"
        self.assertEqual(hashlib.sha256(dataset.read_bytes()).hexdigest(), audit["dataset_file_sha256"])
        questions = load_questions(dataset.read_text(), 408)
        self.assertEqual(len(questions), 20)
        self.assertEqual(sum(not q.answerable for q in questions), 3)
        reader = PdfReader(pdf)
        texts = {}
        self.assertEqual([q.id for q in questions], [item["id"] for item in audit["items"]])
        for question, item in zip(questions, audit["items"]):
            self.assertEqual(question.evidence_pages, [e["page"] for e in item["evidence"]])
            for evidence in item["evidence"]:
                number = evidence["page"]
                if number not in texts:
                    texts[number] = " ".join(reader.pages[number - 1].extract_text().split())
                self.assertIn(evidence["quote"], texts[number])
            if not question.answerable:
                self.assertTrue(item["reasoning_or_absence_rationale"])
        self.assertEqual(1755 - 1549, 206)
        self.assertEqual(round(2857 / 3841 * 100, 1), 74.4)

    def test_unanswerable_validation_and_artifact_roundtrip(self):
        text = '[{"id":"q", "question":"Unknown?", "reference_answer":"Cannot determine from this document.", "answerable":false, "evidence_pages":[]}]'
        questions = load_questions(text, 2)
        check = check_inputs(document(), questions, min_pages=1, require_references=True)
        self.assertTrue(check["passed"])
        self.assertEqual(check["unanswerable_count"], 1)
        class Abstainer:
            name = "offline-test"
            def generate(self, prompt, config):
                return Generation("Cannot determine from this document.", Usage(), None, "STOP")
        manifest, rows = run_baseline(document(), questions, Abstainer(), GenerationConfig("test"))
        self.assertEqual(rows[0]["evaluation"]["exact_match"], 1)
        self.assertIsNone(rows[0]["evaluation"]["cited_page_recall"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "run"
            write_results(root, manifest, rows)
            self.assertEqual(compare_runs([root / "results.json"])[0]["unanswerable_questions"], 1)
        for answerable, pages in [("false", "[1]"), ("false", "null"), ('"no"', "[]")]:
            data = f'[{{"id":"q", "question":"Q", "answerable":{answerable}, "evidence_pages":{pages}}}]'
            with self.assertRaises(ValueError):
                load_questions(data, 2)


if __name__ == "__main__":
    unittest.main()

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from context_retrieval_arena.benchmark import load_questions, run_baseline
from context_retrieval_arena.checks import check_inputs
from context_retrieval_arena.cli import main
from context_retrieval_arena.evaluation import score
from context_retrieval_arena.models import Document, Generation, GenerationConfig, Page, Question, Usage
from context_retrieval_arena.pricing import Pricing
from context_retrieval_arena.reporting import compare_runs, summarize, write_results
from test_baseline import make_pdf


class FixtureProvider:
    name = "offline-test"

    def __init__(self, *args):
        self.calls = 0

    def close(self):
        pass

    def generate(self, prompt, config):
        self.calls += 1
        if self.calls == 2:
            raise TimeoutError("private diagnostic")
        return Generation("42 [page 151]", Usage(100, 10, 20, 5, 115), "test-v1", "STOP")


def fixtures():
    doc = Document(1, "test.pdf", "a" * 64, "test", 0.1,
                   [Page(i, "Page text") for i in range(1, 152)])
    questions = [Question("q1", "Result?", "42", [151]), Question("q2", "Other result?", "42", [151])]
    prices = Pricing("test", "2026-11-01", "synthetic test prices", 2, 1, 4, 4)
    return doc, questions, prices


class MetricTests(unittest.TestCase):
    def test_normalization_and_repeated_tokens(self):
        result = score("ＦＯＯ, foo! [page 2]", "foo foo", [2], [1, 2], 2)
        self.assertEqual(result["exact_match"], 1)
        self.assertEqual(result["token_f1"], 1)
        self.assertAlmostEqual(score("foo", "foo foo", None, [], 2)["token_f1"], 2 / 3)

    def test_citation_overlap_is_distinct_from_supplied_coverage(self):
        result = score("answer [page 1] [page 1] [page 999]", None, [1, 2], [1, 2], 2)
        self.assertIsNone(result["exact_match"])
        self.assertEqual(result["supplied_page_recall"], 1)
        self.assertEqual(result["cited_page_recall"], 0.5)
        self.assertEqual(result["cited_page_precision"], 0.5)
        self.assertEqual(result["invalid_cited_pages"], [999])
        self.assertIsNone(score("answer", None, [], [], 2)["cited_page_recall"])

    def test_incomplete_answer_scores_zero(self):
        result = score("42 [page 1]", "42", [1], [1], 1, complete=False)
        self.assertEqual(result["exact_match"], 0)
        self.assertEqual(result["token_f1"], 0)
        self.assertEqual(result["cited_page_recall"], 0)
        self.assertEqual(result["supplied_page_recall"], 1)


class PricingTests(unittest.TestCase):
    def test_cached_and_reasoning_rates_without_double_counting(self):
        _, _, pricing = fixtures()
        self.assertAlmostEqual(pricing.estimate(Usage(100, 10, 20, 5)), 0.00024)

    def test_unknown_and_invalid_counts_stay_unknown(self):
        _, _, pricing = fixtures()
        for usage in [Usage(), Usage(100, 10, None, 0), Usage(100, 10, 0, None),
                      Usage(10, 1, 11, 0), Usage(10, -1, 0, 0), Usage(True, 0, 0, 0)]:
            with self.subTest(usage=usage):
                self.assertIsNone(pricing.estimate(usage))

    def test_invalid_rates_and_model_mismatch_fail_before_calls(self):
        doc, questions, pricing = fixtures()
        for rate in [-1, float("nan"), float("inf"), True]:
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                Pricing("test", "2026-11-01", "test", rate, 0, 0, 0)
        provider = FixtureProvider()
        with self.assertRaisesRegex(ValueError, "model"):
            run_baseline(doc, questions, provider, GenerationConfig("other"), pricing)
        self.assertEqual(provider.calls, 0)


class ExperimentTests(unittest.TestCase):
    def test_failed_queries_remain_in_score_and_cost_denominators(self):
        doc, questions, pricing = fixtures()
        manifest, rows = run_baseline(doc, questions, FixtureProvider(), GenerationConfig("test"), pricing)
        summary = summarize(manifest, rows)
        self.assertEqual(summary["questions"], 2)
        self.assertEqual(summary["error"], 1)
        self.assertEqual(summary["exact_match"], 0.5)
        self.assertEqual(summary["exact_match_count"], 2)
        self.assertEqual(summary["priced_queries"], 1)
        self.assertIsNone(summary["total_query_cost_usd"])
        self.assertAlmostEqual(summary["known_query_cost_usd"], 0.00024)
        self.assertEqual(summary["input_tokens_known_sum"], 100)
        self.assertEqual(summary["input_tokens_reported_queries"], 1)
        self.assertIsNone(summary["input_tokens_total"])
        self.assertNotIn("private diagnostic", json.dumps(rows))
        self.assertEqual(manifest["question_count"], 2)

    def test_missing_references_are_unscored_not_correct(self):
        doc, _, _ = fixtures()
        manifest, rows = run_baseline(doc, [Question("q", "Q")], FixtureProvider(), GenerationConfig("test"))
        summary = summarize(manifest, rows)
        self.assertIsNone(summary["exact_match"])
        self.assertEqual(summary["exact_match_count"], 0)

    def test_truncated_and_empty_answers_are_incomplete(self):
        doc, questions, _ = fixtures()
        for text, finish in [("42 [page 151]", "MAX_TOKENS"), ("", "STOP"), ("42", None)]:
            provider = FixtureProvider()
            with patch.object(provider, "generate", return_value=Generation(text, Usage(), "test", finish)):
                _, rows = run_baseline(doc, questions[:1], provider, GenerationConfig("test"))
            self.assertEqual(rows[0]["status"], "incomplete")
            self.assertEqual(rows[0]["evaluation"]["exact_match"], 0)

    def test_preflight_thresholds_references_and_blank_pages(self):
        doc, questions, _ = fixtures()
        self.assertTrue(check_inputs(doc, questions, require_references=True)["passed"])
        self.assertFalse(check_inputs(doc, questions, min_pages=300)["passed"])
        self.assertFalse(check_inputs(doc, [Question("q", "Q")], require_references=True)["passed"])
        blank = Document(1, "a.pdf", "a" * 64, "test", 0, [Page(1, ""), Page(2, "text")])
        self.assertEqual(check_inputs(blank, questions, min_pages=1)["empty_text_pages"], [1])

    def test_dataset_rejects_incomplete_or_ambiguous_entries(self):
        for item in [{"id": "q"}, {"id": "q", "question": "Q", "extra": 1},
                     {"id": "q", "question": "Q", "reference_answer": " "},
                     {"id": "q", "question": "Q", "evidence_pages": [1, 1]}]:
            with self.subTest(item=item), self.assertRaises(ValueError):
                load_questions(json.dumps([item]), 151)

    def test_report_rejects_incompatible_incomplete_and_old_runs(self):
        doc, questions, _ = fixtures()
        manifest, rows = run_baseline(doc, questions, FixtureProvider(), GenerationConfig("test"))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "run"
            write_results(path, manifest, rows)
            original = path / "results.json"
            self.assertEqual(len(compare_runs([original, original])), 2)
            self.assertTrue((path / "report.md").is_file())
            for field, value in [("document_sha256", "b" * 64), ("schema_version", 1),
                                 ("generation", {"model": "different"})]:
                altered = {"manifest": {**manifest, field: value}, "results": rows}
                other = Path(temp) / "altered.json"
                other.write_text(json.dumps(altered))
                with self.subTest(field=field), self.assertRaises(ValueError):
                    compare_runs([original, other])
            for changed in [rows[:1], [rows[0], rows[0]]]:
                other.write_text(json.dumps({"manifest": manifest, "results": changed}))
                with self.assertRaises(ValueError):
                    compare_runs([other])
            changed = copy.deepcopy(rows)
            changed[0]["model_version"] = "different"
            other.write_text(json.dumps({"manifest": manifest, "results": changed}))
            with self.assertRaises(ValueError):
                compare_runs([original, other])
            changed = copy.deepcopy(rows)
            changed[0]["reference_answer"] = "tampered reference"
            other.write_text(json.dumps({"manifest": manifest, "results": changed}))
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                compare_runs([other])

    def test_report_rejects_nonfinite_metrics_and_negative_timings(self):
        doc, questions, _ = fixtures()
        manifest, rows = run_baseline(doc, questions, FixtureProvider(), GenerationConfig("test"))
        for target, field, value in [("evaluation", "token_f1", float("nan")),
                                     (None, "query_seconds", -1),
                                     ("usage", "input_tokens", -1)]:
            changed = copy.deepcopy(rows)
            (changed[0][target] if target else changed[0])[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                summarize(manifest, changed)

    def test_151_page_cli_ingest_check_run_and_report_offline(self):
        def invoke(args):
            with patch("sys.argv", ["cra", *map(str, args)]), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                main()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf, document, dataset = root / "large.pdf", root / "doc.json", root / "questions.json"
            make_pdf(pdf, [f"Page {i}: result is 42." for i in range(1, 152)])
            invoke(["ingest", pdf, "--output", document])
            _, questions, _ = fixtures()
            dataset.write_text(json.dumps([asdict(q) for q in questions]))
            invoke(["check", "--document", document, "--questions", dataset, "--source-pdf", pdf, "--require-references"])
            with patch.dict("os.environ", {"GEMINI_API_KEY": "offline-test-key"}), patch("context_retrieval_arena.generation.gemini.GeminiProvider", FixtureProvider):
                with self.assertRaises(SystemExit) as exit_status:
                    invoke(["run", "--document", document, "--questions", dataset, "--model", "test", "--output", root / "run"])
                self.assertEqual(exit_status.exception.code, 1)
            results = root / "run/results.json"
            data = json.loads(results.read_text())
            self.assertEqual(data["results"][0]["supplied_pages"], list(range(1, 152)))
            self.assertEqual(data["results"][1]["status"], "error")
            self.assertIn("lock_sha256", data["manifest"]["code"])
            invoke(["report", results, "--output", root / "comparison"])
            self.assertTrue((root / "comparison/summary.csv").is_file())
            with self.assertRaises(SystemExit):
                invoke(["check", "--document", document, "--questions", dataset, "--min-pages", 300])
            pdf.write_bytes(b"different source")
            with self.assertRaises(SystemExit):
                invoke(["check", "--document", document, "--questions", dataset, "--source-pdf", pdf])


if __name__ == "__main__":
    unittest.main()

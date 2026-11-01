import csv
import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from context_retrieval_arena.benchmark import load_questions, run_baseline
from context_retrieval_arena.cli import load_document
from context_retrieval_arena.ingestion import ingest_pdf
from context_retrieval_arena.models import Generation, GenerationConfig, Question, Usage
from context_retrieval_arena.reporting import write_results


def make_pdf(path: Path, texts: list[str]) -> None:
    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as output:
        writer.write(output)


class RecordingProvider:
    name = "offline-test"

    def __init__(self):
        self.prompts = []

    def generate(self, prompt, config):
        self.prompts.append(prompt)
        return Generation("The result is 42 [page 3].", Usage(100, 10, 0), "test-model", "STOP")


class PipelineTests(unittest.TestCase):
    def test_pdf_to_baseline_to_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "sample.pdf"
            make_pdf(pdf, ["Introduction", "", "The result is 42."])
            document = ingest_pdf(pdf)
            self.assertEqual(document.source_sha256, hashlib.sha256(pdf.read_bytes()).hexdigest())
            self.assertEqual([p.number for p in document.pages], [1, 2, 3])
            self.assertEqual(document.pages[1].text, "")
            saved = root / "document.json"
            saved.write_text(json.dumps(asdict(document)), encoding="utf-8")
            self.assertEqual(load_document(saved), document)
            questions = load_questions(json.dumps([
                {"id": "q1", "question": "What result?", "reference_answer": "42", "evidence_pages": [3]},
                {"id": "q2", "question": "What introduction?"},
            ]), 3)
            provider = RecordingProvider()
            manifest, rows = run_baseline(document, questions, provider, GenerationConfig("test"))
            self.assertEqual(len(provider.prompts), 2)
            for prompt in provider.prompts:
                self.assertLess(prompt.index("[PDF PAGE 1]"), prompt.index("[PDF PAGE 3]"))
                self.assertIn("The result is 42.", prompt)
                self.assertIn("[PDF PAGE 2]", prompt)
            self.assertEqual(rows[0]["supplied_pages"], [1, 2, 3])
            self.assertEqual(rows[0]["usage"]["input_tokens"], 100)
            self.assertIsNone(rows[0]["cost_usd"])
            self.assertGreaterEqual(rows[0]["query_seconds"], rows[0]["generation_seconds"])
            write_results(root / "run", manifest, rows)
            result = json.loads((root / "run/results.json").read_text())
            self.assertEqual(result["results"][0]["reference_evidence_pages"], [3])
            with (root / "run/results.csv").open() as stream:
                csv_rows = list(csv.DictReader(stream))
            self.assertEqual(len(csv_rows), 2)
            self.assertEqual(csv_rows[0]["output_tokens"], "10")
            with self.assertRaises(FileExistsError):
                write_results(root / "run", manifest, rows)

    def test_no_text_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "blank.pdf"
            make_pdf(pdf, [""])
            with self.assertRaisesRegex(ValueError, "no extractable text"):
                ingest_pdf(pdf)

    def test_encrypted_pdf_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "encrypted.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.encrypt("test-password")
            with pdf.open("wb") as stream:
                writer.write(stream)
            with self.assertRaisesRegex(ValueError, "Encrypted"):
                ingest_pdf(pdf)

    def test_bad_datasets_are_rejected(self):
        for data in [[], [{"id": "a", "question": ""}],
                     [{"id": "a", "question": "Q", "evidence_pages": [4]}],
                     [{"id": "a", "question": "Q", "evidence_pages": [True]}],
                     [{"id": "a", "question": "Q"}] * 2]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                load_questions(json.dumps(data), 3)

    def test_config_rejects_invalid_limits(self):
        with self.assertRaises(ValueError):
            GenerationConfig("test", max_output_tokens=0)

    def test_provider_errors_propagate(self):
        class BrokenProvider(RecordingProvider):
            def generate(self, prompt, config):
                raise RuntimeError("context limit exceeded")
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "sample.pdf"
            make_pdf(pdf, ["text"])
            with self.assertRaisesRegex(RuntimeError, "context limit"):
                run_baseline(ingest_pdf(pdf), [Question("q", "Q")], BrokenProvider(), GenerationConfig("test"))


if __name__ == "__main__":
    unittest.main()

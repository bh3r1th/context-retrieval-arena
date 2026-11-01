import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from .benchmark import load_questions, run_baseline
from .checks import check_inputs
from .ingestion import ingest_pdf
from .models import Document, GenerationConfig, Page
from .pricing import Pricing
from .reporting import compare_runs, write_results, write_summary


def load_document(path: Path) -> Document:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unsupported document schema")
    data["pages"] = [Page(**p) for p in data["pages"]]
    document = Document(**data)
    if not document.pages or any(type(p.number) is not int for p in document.pages) or [p.number for p in document.pages] != list(range(1, len(document.pages) + 1)):
        raise ValueError("Document must preserve contiguous one-based PDF pages")
    if any(not isinstance(p.text, str) for p in document.pages) or not any(p.text.strip() for p in document.pages):
        raise ValueError("Document must contain extracted text")
    if not isinstance(document.source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", document.source_sha256):
        raise ValueError("Document requires a valid source SHA-256")
    if type(document.extraction_seconds) not in (int, float) or not math.isfinite(document.extraction_seconds) or document.extraction_seconds < 0:
        raise ValueError("Invalid extraction time")
    return document


def code_provenance() -> dict:
    root = Path(__file__).resolve().parents[2]
    def git(*args):
        try:
            return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL, text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    lock = root / "uv.lock"
    return {"git_commit": head, "git_dirty": bool(status) if status is not None else None,
            "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None}


def main() -> None:
    try:
        _main()
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"Invalid input or artifact: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


def _main() -> None:
    parser = argparse.ArgumentParser(description="Long-document QA experiments")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="Extract PDF text into a page-preserving JSON artifact")
    ingest.add_argument("pdf", type=Path)
    ingest.add_argument("--output", required=True, type=Path)
    run = commands.add_parser("run", help="Run the Gemini full-context baseline")
    run.add_argument("--document", required=True, type=Path)
    run.add_argument("--questions", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path, help="New output directory; existing paths are rejected")
    run.add_argument("--model", required=True, help="Explicit Gemini model ID; prefer a pinned model version")
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--max-output-tokens", type=int, default=2048)
    run.add_argument("--seed", type=int)
    run.add_argument("--pricing", type=Path, help="Explicit flat USD rates as JSON; no default prices")
    run.add_argument("--require-references", action="store_true")
    check = commands.add_parser("check", help="Validate local document/dataset without API calls")
    check.add_argument("--document", required=True, type=Path)
    check.add_argument("--questions", required=True, type=Path)
    check.add_argument("--min-pages", type=int, default=150)
    check.add_argument("--require-references", action="store_true")
    check.add_argument("--source-pdf", type=Path, help="Verify the source PDF hash if available")
    report = commands.add_parser("report", help="Compare compatible schema-v2 results locally")
    report.add_argument("results", nargs="+", type=Path, help="Paths to results.json files")
    report.add_argument("--output", required=True, type=Path, help="New directory")
    args = parser.parse_args()
    if args.command == "report":
        summaries = compare_runs(args.results)
        args.output.mkdir(parents=True, exist_ok=False)
        write_summary(args.output, summaries)
        print(f"Wrote comparison of {len(summaries)} runs to {args.output}")
        return
    if args.command == "ingest":
        if args.output.exists():
            parser.error("Output already exists; choose a new path")
        document = ingest_pdf(args.pdf)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(document), indent=2, ensure_ascii=False) + "\n")
        empty = [p.number for p in document.pages if not p.text.strip()]
        print(f"Extracted {len(document.pages)} pages to {args.output}")
        if empty:
            print(f"Warning: pages without extracted text (no OCR): {empty}", file=sys.stderr)
        return
    if args.command == "check":
        document = load_document(args.document)
        questions = load_questions(args.questions.read_text(encoding="utf-8"), len(document.pages))
        result = check_inputs(document, questions, args.min_pages, args.require_references)
        if args.source_pdf:
            with args.source_pdf.open("rb") as stream:
                matches = hashlib.file_digest(stream, "sha256").hexdigest() == document.source_sha256
            result["source_pdf_matches"] = matches
            if not matches:
                result["errors"].append("Source PDF does not match the ingestion artifact")
                result["passed"] = False
        print(json.dumps(result, indent=2))
        if not result["passed"]:
            raise SystemExit(1)
        return
    if args.output.exists():
        parser.error("Output already exists; choose a new run directory")
    config = GenerationConfig(args.model, args.temperature, args.max_output_tokens, args.seed)
    document = load_document(args.document)
    questions = load_questions(args.questions.read_text(encoding="utf-8"), len(document.pages))
    if args.require_references and not check_inputs(document, questions, 1, True)["passed"]:
        parser.error("Every question requires a reference answer and nonempty evidence_pages")
    pricing = Pricing(**json.loads(args.pricing.read_text(encoding="utf-8"))) if args.pricing else None
    if pricing and pricing.model != config.model:
        parser.error("Pricing model must exactly match --model")
    provenance = code_provenance()
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        parser.error("Set GEMINI_API_KEY or GOOGLE_API_KEY securely; never put keys in command arguments")
    try:
        from .generation.gemini import GeminiProvider

        provider = GeminiProvider(key)
    except ImportError:
        parser.error("Install the optional provider: uv sync --extra gemini --locked")
    try:
        manifest, rows = run_baseline(document, questions, provider, config, pricing)
    finally:
        provider.close()
    manifest["package_version"] = version("context-retrieval-arena")
    manifest["provider_sdk_version"] = version("google-genai")
    manifest["code"] = provenance
    write_results(args.output, manifest, rows)
    print(f"Wrote {len(rows)} answers to {args.output}")
    if any(row["status"] != "ok" for row in rows):
        print("Run contains failed or incomplete answers; inspect results.json", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

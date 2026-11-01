import argparse
import json
import os
import sys
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from .benchmark import load_questions, run_baseline
from .ingestion import ingest_pdf
from .models import Document, GenerationConfig, Page
from .reporting import write_results


def load_document(path: Path) -> Document:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported document schema")
    data["pages"] = [Page(**p) for p in data["pages"]]
    document = Document(**data)
    if not document.pages or [p.number for p in document.pages] != list(range(1, len(document.pages) + 1)):
        raise ValueError("Document must preserve contiguous one-based PDF pages")
    if any(not isinstance(p.text, str) for p in document.pages) or not any(p.text.strip() for p in document.pages):
        raise ValueError("Document must contain extracted text")
    return document


def main() -> None:
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
    args = parser.parse_args()
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
    if args.output.exists():
        parser.error("Output already exists; choose a new run directory")
    config = GenerationConfig(args.model, args.temperature, args.max_output_tokens, args.seed)
    document = load_document(args.document)
    questions = load_questions(args.questions.read_text(encoding="utf-8"), len(document.pages))
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        parser.error("Set GEMINI_API_KEY or GOOGLE_API_KEY securely; never put keys in command arguments")
    try:
        from .generation.gemini import GeminiProvider

        provider = GeminiProvider(key)
    except ImportError:
        parser.error("Install the optional provider: uv sync --extra gemini --locked")
    try:
        manifest, rows = run_baseline(document, questions, provider, config)
    finally:
        provider.close()
    manifest["package_version"] = version("context-retrieval-arena")
    manifest["provider_sdk_version"] = version("google-genai")
    write_results(args.output, manifest, rows)
    print(f"Wrote {len(rows)} answers to {args.output}")


if __name__ == "__main__":
    main()

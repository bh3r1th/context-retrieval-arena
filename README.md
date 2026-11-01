# context-retrieval-arena

A small Python framework for comparing full-context, embedding RAG, and
structure-aware RAG on large PDFs. **Phase 1:** PDF text ingestion and a Gemini
full-context baseline. Embeddings, PageIndex, evaluation scores, pricing, and
comparative reports are planned, not implemented.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked --extra gemini
uv run --no-sync python -m unittest discover -s tests -v
uv run --no-sync cra --help
```

For ingestion without Gemini dependencies: `uv sync --locked`.
If the default uv cache is unwritable, set `UV_CACHE_DIR` to a writable location.
Do not commit credentials, private PDFs, or generated artifacts.

## Extract a PDF

```sh
uv run --no-sync cra ingest /path/to/document.pdf --output artifacts/document.json
```

The JSON preserves every PDF page, its one-based physical page number, source
SHA-256, extraction time, and pypdf version. Blank pages stay in position and are
reported on stderr. Fully textless and encrypted PDFs are rejected. pypdf extracts
text; it does not OCR scans, interpret figures, or guarantee table reading order.
Inspect extracted text before designing questions, especially for mixed scans.
The baseline sends **extracted text**, not native PDF bytes or page images.

## Run full context

Set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) securely in your environment. Keys are
read at runtime and never saved in artifacts. The SDK uses
`generativelanguage.googleapis.com`; network policy must allow it.

Create a JSON array of questions (see `examples/questions.json`):

```json
[
  {
    "id": "q001",
    "question": "What result is reported?",
    "reference_answer": "A manually verified reference answer",
    "evidence_pages": [12, 13]
  }
]
```

IDs must be unique. Evidence uses physical PDF pages, starting at 1, regardless of
printed page labels. Reference answers and evidence are optional in phase 1;
they are retained for later evaluation and never included in generation prompts.

```sh
uv run --no-sync cra run \
  --document artifacts/document.json \
  --questions examples/questions.json \
  --model YOUR_GEMINI_MODEL_ID \
  --temperature 0 --max-output-tokens 2048 \
  --output artifacts/run-001
```

Choose a model ID explicitly, preferably a pinned version with enough context for
the PDF plus question and output allowance. Each question sends all pages in
order with page markers and a shared QA prompt. Nothing is silently truncated.
Oversized inputs and provider errors abort the run; phase 1 does not checkpoint
partial runs. Nonempty truncated responses retain the provider finish reason;
inspect it before scoring. The SDK timeout is 120 seconds per HTTP request;
SDK retries can increase observed call latency.

Each new output directory contains `results.json` and `results.csv`:

- Answers, references, supplied pages, prompt hashes, and finish reasons.
- Provider-reported input, output, cached-input, reasoning, and total tokens when
  available. Missing counts stay null; output and reasoning counts are separate.
- Generation latency and query latency (retrieval + prompt assembly + generation).
  Query timing excludes prior PDF extraction and artifact I/O. Extraction and run
  times are recorded separately in the manifest.
- Document and normalized dataset hashes, model/settings, model version when
  returned, prompt version, Python, package, extractor, and SDK versions.

`cost_usd` is null until explicit model-specific pricing is implemented; it is not
zero. Accuracy and evidence recall are not computed yet. Supplied pages measure
context coverage, not evidence actually used or cited by an answer.

Provider implicit caching is uncontrolled and recorded as such. Repeated runs
are **not** yet controlled cold/warm experiments. Temperature zero and an optional
`--seed` improve repeatability but do not guarantee identical provider outputs.
Use a new output directory for each run; existing artifacts are never overwritten.
Results include extracted answers and references and may contain sensitive data.

## Architecture and implementation phases

See [docs/architecture.md](docs/architecture.md) for component boundaries, the
comparison protocol, and the staged implementation plan.

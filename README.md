# context-retrieval-arena

A small Python framework for comparing full-context, embedding RAG, and
structure-aware RAG on large PDFs. Includes PDF text ingestion, a Gemini
full-context baseline, deterministic evaluation, explicit token-price estimates,
and local reports. Embeddings, PageIndex, semantic judging, and controlled cache
experiments remain deferred.

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

The repository includes a [408-page SEC benchmark PDF and selection notes](docs/benchmark-document.md)
under `data/documents/sec-regulation-best-interest-2018/`.

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

The [20-question SEC pilot](data/datasets/sec-regulation-best-interest-2018/README.md)
and [pilot runbook](docs/pilot-runbook.md) are included. The pilot is source-checked
by the assistant; independent human review and live generation remain pending.

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
printed page labels. References are optional and never enter prompts. Missing
references remain unscored; duplicate evidence pages and empty answers are rejected.

Optional `answerable` defaults to true. Unanswerable controls must explicitly use
`answerable: false` and `evidence_pages: []`. `--require-references` still requires
their reference answers, but supporting pages are required only for answerable items.

Validate inputs before spending API credits:

```sh
uv run --no-sync cra check \
  --document artifacts/document.json --questions examples/questions.json \
  --source-pdf /path/to/document.pdf --min-pages 150 --require-references
```

This local command returns JSON and exits 1 on failed checks (2 on invalid input).
It checks page count, dataset structure, reference coverage, and optionally the
source PDF hash. Blank-text pages and pilot datasets produce warnings. Lower
`--min-pages` for fixtures. It does not verify extraction fidelity, references,
model capacity, or live access. See [docs/checks.md](docs/checks.md).

```sh
uv run --no-sync cra run \
  --document artifacts/document.json \
  --questions examples/questions.json \
  --model YOUR_GEMINI_MODEL_ID \
  --temperature 0 --max-output-tokens 2048 --require-references \
  --output artifacts/run-001
```

Choose a model ID explicitly, preferably a pinned version with enough context for
the PDF plus question and output allowance. Each question sends all pages in
order with page markers and a shared QA prompt. Nothing is silently truncated.
Provider exceptions are recorded by type and later questions still execute.
Messages are omitted because SDK errors may contain credentials. `ok` requires
nonempty text and a `STOP` finish reason. Truncated, blocked, empty, and unknown-finish
answers are `incomplete`; usage is retained even for empty responses. Runs with
failed/incomplete answers write artifacts and exit 1. Input errors exit 2.
Process interruption does not checkpoint/resume yet. SDK timeout is 120 seconds
per HTTP request; SDK retries can increase observed latency.

Each new output directory contains `results.json`, `results.csv`, `summary.json`,
`summary.csv`, and `report.md`:

- Answers, references, supplied pages, prompt hashes, and finish reasons.
- Provider-reported input, output, cached-input, reasoning, and total tokens when
  available. Missing counts stay null; output and reasoning counts are separate.
- Generation latency and query latency (retrieval + prompt assembly + generation).
  Query timing excludes prior PDF extraction and artifact I/O. Extraction and run
  times are recorded separately in the manifest.
- Document source/content and normalized dataset hashes, model/settings, resolved
  model version when returned, prompt/evaluation versions, Python, package,
  extractor, SDK, Git commit/dirty flag, and lockfile hash.

Evaluation uses Unicode-normalized, casefolded word tokens with punctuation and
`[page N]` citations removed: exact match and multiset token F1. These are lexical
proxies, **not semantic accuracy**; use manual/rubric scoring for open answers.
Citation parsing recognizes `[page N]` only. Recall and precision compare unique
page citations to references; invalid page IDs penalize precision. Page overlap
does not verify citation support. Supplied-page recall is separate and trivially
1 for full context. Missing evidence (including `[]`) leaves evidence scores null.

Failed/incomplete answers score zero where references exist; missing references
stay null. Summaries retain denominators, success/failure counts, token-count
coverage, and latency mean/median/nearest-rank P95.

## Explicit pricing

Before any later live generation, `cra tokens` can count each exact full-context
prompt through Gemini and check reported model limits with an output reserve.
It uploads document text and requires credentials/network access; it never generates
answers. See [the pilot runbook](docs/pilot-runbook.md). It has not been run live.

Cost defaults to null, not zero. Add `--pricing /path/to/rates.json` with this schema:

```json
{
  "model": "YOUR_GEMINI_MODEL_ID",
  "effective_date": "2026-11-01",
  "source": "Synthetic example only; replace with verified provider pricing",
  "currency": "USD",
  "input_per_million": 1.0,
  "cached_input_per_million": 0.1,
  "output_per_million": 2.0,
  "reasoning_per_million": 2.0
}
```

**These numbers are not actual Gemini prices.** Supply verified rates for the
exact model, context-length tier, and billing mode. The calculator supports one
flat rate set, not automatic tiers or storage/non-token fees. The rate record is
saved in the manifest. Cached inputs are subtracted from total inputs before
applying the uncached rate; SDK candidate-output and reasoning counts are priced
separately. Missing/invalid counts leave cost unknown, even when an omitted counter
might mean zero. Total cost is null unless every query has a price; known subtotals
and coverage are retained. Retries with unreported usage and other fees are excluded,
so these are estimates rather than invoice totals.

## Compare runs locally

```sh
uv run --no-sync cra report \
  artifacts/run-001/results.json artifacts/run-002/results.json \
  --output artifacts/comparison-001
```

This writes summary JSON/CSV and Markdown without API calls. Reports require
schema-v2 runs with matching document/content, dataset, generation, prompt,
evaluation, and pricing settings. Missing/duplicate results and different known
resolved model versions are rejected. Unknown model versions do not prove backend
equivalence. Old schema-v1 results require a new run.

Provider implicit caching is uncontrolled and recorded as such. Repeated runs
are **not** yet controlled cold/warm experiments. Temperature zero and an optional
`--seed` improve repeatability but do not guarantee identical provider outputs.
Use a new output directory for each run; existing artifacts are never overwritten.
Results include extracted answers and references and may contain sensitive data.

## Architecture and implementation phases

See [docs/architecture.md](docs/architecture.md) for component boundaries, the
comparison protocol, and the staged implementation plan.

# Full-context pilot runbook

## Current state

- Stored source: 408-page SEC Regulation Best Interest proposed rule (2018).
- Dataset: 20 source-checked pilot questions, including 3 unanswerable controls.
- Evidence quotations verified against their physical pages; arithmetic checked;
  numerical table pages 229/230 visually inspected.
- Local input checks pass; only the expected pilot-size warning remains.
- **Budget is US$0: no paid calls are authorized.** No live generation or remote
  token counting has been performed. Neither `GEMINI_API_KEY` nor `GOOGLE_API_KEY`
  is configured in the current environment. Provider-domain access is not verified.
- Independent human review, model choice, measured context fit, verified pricing,
  and a live answer-quality review remain pending.

The commands below are instructions for later use, not evidence of live validation.

## 1. Reproduce local validation

From the repository root, install with `uv sync --locked --extra gemini` if needed.
Reuse the existing extraction or generate it once (output paths must be new):

```sh
uv run --no-sync cra ingest \
  data/documents/sec-regulation-best-interest-2018/regulation-best-interest-proposed-rule.pdf \
  --output artifacts/documents/sec-regulation-best-interest-2018/document.json
uv run --no-sync cra check \
  --document artifacts/documents/sec-regulation-best-interest-2018/document.json \
  --source-pdf data/documents/sec-regulation-best-interest-2018/regulation-best-interest-proposed-rule.pdf \
  --questions data/datasets/sec-regulation-best-interest-2018/pilot.json \
  --min-pages 300 --require-references
uv run --no-sync python -m unittest discover -s tests -v
```

Review `pilot.json` alongside `pilot.review.json`, then inspect original PDF pages
for the supporting quotations. Acceptable paraphrases and calculation tolerances
should be agreed before scoring model answers. If editing questions or references,
update the review record's dataset file hash and recheck evidence; tests detect drift.

## 2. Later: select a model and count the exact prompts

Select an explicitly named Gemini model supported by the account. Prefer a stable
version with sufficient context. Do not infer tokens from the 910,070 characters.
Configure a key securely and allow `generativelanguage.googleapis.com` through the
environment's supported settings. Never store credentials in Git or command arguments.

`cra tokens` makes remote model-metadata and token-count calls and **uploads the
complete extracted document once per question**. It does not generate answers.
Confirm current provider terms/access before executing; it is not a local tokenizer.

```sh
uv run --no-sync cra tokens \
  --document artifacts/documents/sec-regulation-best-interest-2018/document.json \
  --questions data/datasets/sec-regulation-best-interest-2018/pilot.json \
  --model YOUR_VERIFIED_MODEL_ID --max-output-tokens 2048 \
  --temperature 0 --seed 42 \
  --output artifacts/pilot-token-preflight.json
```

The artifact records exact full-context prompt hashes/counts, source/content/dataset
hashes, model/settings, counting timestamp, SDK/code provenance and reported model
limits. It fails if counts or limits are missing/invalid, output exceeds the output
limit, or any prompt plus the reserved output exceeds the reported input limit.
The last rule is deliberately conservative; providers may expose separate limits.
Failure artifacts with valid counts are retained and exit 1. API errors exit 1
without claiming a successful preflight. Existing output paths are rejected.

Passing does not prove generation access, model-specific thinking configuration,
cache behavior or billing. Repeat after changing model, document, dataset, prompt,
or output settings. SDK responses are mocked in tests; current live capacity is unknown.

## 3. Later: pricing and paid pilot

Do not execute generation under the current US$0 budget. First obtain a spending
limit and verify official pricing for the chosen model/context tier and billing mode.
Use the explicit JSON schema documented in README.md; do not reuse the synthetic
example rates. Record the effective date and pricing URL. Account for reasoning,
cache storage, retries and other charges; the built-in flat token estimator is not
a hard spending cap. Do a small initial trial before a 20-query run.

After authorization and successful token preflight, a full pilot command is:

```sh
uv run --no-sync cra run \
  --document artifacts/documents/sec-regulation-best-interest-2018/document.json \
  --questions data/datasets/sec-regulation-best-interest-2018/pilot.json \
  --model YOUR_VERIFIED_MODEL_ID --max-output-tokens 2048 \
  --temperature 0 --seed 42 --require-references \
  --pricing /path/to/verified-rates.json --output artifacts/pilot-001
```

## 4. Review answers before expanding

Read `results.json`, `results.csv`, `summary.json` and `report.md` together. Exit
status 1 means at least one error or incomplete answer; do not omit those questions.

For every question, record reviewer/date, correctness (1 = correct, 0.5 = materially
partial, 0 = wrong/unsupported), whether cited evidence actually supports the
answer, and notes on missing facts or invented claims. Numeric items must use the
right table/panel/date/unit; the percentage item is rounded to one decimal place.
For unanswerables, require an explicit abstention without invented details. Missing
citations on an answerable answer need review even when its text is correct.

Keep human judgments separate from deterministic lexical and page-overlap metrics.
These manual rubric scores are not implemented as an automated judge. Lexical exact
match may fail good paraphrases; a correct page number does not prove support.

Compare token usage, finish reasons, reported model versions, latency, estimated
cost coverage and the actual provider bill. Repeated runs remain cache-uncontrolled;
do not label them controlled cold/warm trials. Expand to 100–200 verified questions
and add embedding RAG/PageIndex only after the baseline is understood.

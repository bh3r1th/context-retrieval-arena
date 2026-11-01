# Validation checklist

## Automated locally

Run `uv run --no-sync python -m unittest discover -s tests -v`.

- PDF extraction: physical page order, blank pages, source hashes, encryption and
  fully textless inputs; JSON round-trip.
- Dataset structure: IDs, required text, nonempty answers, evidence bounds and duplicates.
- Context: every page supplied without truncation; provider errors retain result rows.
- Evaluation: lexical normalization, repeated tokens, citation page overlap,
  invalid citations, missing references, failed/incomplete scoring.
- Pricing: uncached/cached split, separate reasoning, invalid rates, unknown usage,
  model mismatch before API calls, incomplete totals and denominator coverage.
- Provider adapter: official SDK request/response types with mocked calls,
  generation settings and retained usage on empty/blocked responses.
- Reporting: JSON/CSV/Markdown, failed-query denominators, nonfinite values,
  incompatible runs, duplicates/missing results, model drift, no overwrite.
- CLI integration: a generated 151-page PDF through ingest, check, fake-provider
  run, and report. This is a synthetic fixture, not a realistic benchmark.
- Real PDF pilot: stored document/dataset hashes, every evidence quotation against
  its cited physical page, arithmetic answers, and unanswerable validation.
- Remote token-count preflight: exact generation-prompt matching, no answer calls,
  model input/output limits, output reserve, missing metadata and artifact safety;
  SDK calls are mocked. No live context-fit claim is made.

Run `cra check` on the selected PDF artifact and dataset before live generation.
Its JSON separates errors, warnings, required manual checks and unverified live
capabilities. A passing local check does not establish live readiness.

## Manual checks before live experiments

- Select a public, representative 150–300+ page PDF and record source, license,
  version/date and SHA-256. Do not treat the synthetic fixture as that document.
- Compare extracted text against original front/middle/end pages, tables,
  headings, multicolumn pages, scans and appendices. Review empty-page warnings.
- Prepare 10–20 pilot questions, then 100–200 verified questions: factual,
  cross-section, numerical/table and unanswerable examples. Check reference
  answers and physical page evidence manually; keep questions out of prompts.
- Agree on a scoring rubric and human review protocol for open answers. Lexical
  match is insufficient for semantic correctness; page overlap is insufficient
  to establish that a citation supports a claim.

## Live checks (require credentials and an agreed budget)

- Verify provider/model access with a small pilot before a full paid dataset.
- Use provider token counting to verify prompt plus output/thinking allowance
  against the model context window. Never infer tokens from character count.
- Inspect completion reasons, safety blocks, timeouts, and token metadata,
  including omitted cached/reasoning counters. Watch the result exit status.
- Verify current pricing by model/tier/date, reasoning rules, cache/storage fees
  and retry accounting. Do not substitute the README's synthetic rates.
- Compare observed latency and billing to artifacts on a small run.

## Later comparisons (not implemented)

- Match questions, generation settings, scoring, input representation and pricing.
- Record embedding/tree preparation and retrieval calls, tokens, latency and cost.
- Define cold/warm local-index and provider-cache states separately; confirm cache
  hits from metadata instead of naming repeated runs "warm".
- Counterbalance strategy order, repeat trials and report uncertainty, errors,
  preparation-inclusive totals and query-only totals without hiding failures.

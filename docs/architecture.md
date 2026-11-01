# Architecture and implementation plan

## Minimal component boundaries

```text
PDF -> ingestion -> page-preserving Document
                                  |
Question -> retrieval strategy -> context + supplied page IDs
                                  |
                      shared prompt + generation provider
                                  |
                         answer + usage + timings
                                  |
                    evaluation -> reporting (JSON/CSV/report)
```

`models.py` contains small dataclasses shared across stages. `ingestion.py` uses
pypdf without introducing a parsing service. `retrieval/full_context.py` supplies
every page. `generation/` exposes a provider protocol and the optional official
Gemini SDK adapter. `benchmark.py` orchestrates sequential queries. `evaluation/`
computes lexical/page metrics; `pricing.py` estimates explicit flat token rates;
`reporting.py` writes records, summaries, and Markdown comparisons.
The CLI has independent `ingest`, `check`, `run`, and `report` commands so local
validation and analysis run separately from paid generation.

Future retrieval implementations should return context and physical page IDs
using the existing context contract. Add a shared strategy protocol when the
second strategy exists. Index builders should persist versioned artifacts keyed
by document hash and indexing settings. Do not add a registry, service layer,
vector database, orchestration framework, or multiple configuration systems yet.

## Phase 1 — ingestion and full context (implemented; live validation pending)

- Versioned page-text artifact, PDF hash, extraction timing, empty-page warnings.
- All-page retrieval, shared prompt, configurable model/temperature/output/seed.
- Provider-reported usage, query timings, JSON/CSV and reproducibility metadata.
- Offline integration tests with real generated PDFs and a recording provider;
  SDK adapter tests use mocked SDK responses, without billable requests.
- Live validation requires a representative PDF, model access, secure API key,
  and permission for the resulting API spend. No live run is claimed by offline tests.

## Phase 2 — evaluation and experiment protocol

Implemented: lexical exact match/token F1, supplied/cited page recall and citation
precision, explicit flat USD pricing, failure-aware summaries, compatibility checks,
and a local preflight command. A synthetic 151-page fixture exercises the CLI
without paid calls. No real benchmark PDF or verified reference dataset is bundled.

Remaining work:

- Validate a 100–200-question reference dataset with supporting page/section evidence.
- Decide answer metrics before comparing systems: normalized exact match for
  suitable questions, and rubric scoring for open answers. Persist rubric, judge
  model/version, raw judgments, and any human adjudication separately.
- Verify live model-specific token/billing semantics and preparation amortization;
  flat token estimates exclude storage fees and retries not reflected in usage.
- Add a run configuration file only when repeated experiment settings justify it.

## Phase 3 — embedding RAG (dependency decision first)

- Agree on embedding model/provider, chunking and overlap, top-k, and similarity.
- Reuse an established embedding client and local similarity library; assess whether
  simple local storage suffices before introducing a vector database.
- Persist chunk-to-page mappings, embedding settings and index fingerprints.
- Measure indexing time/tokens/cost separately; reuse the same generation provider,
  questions, prompt policy and evaluation across strategies.

## Phase 4 — structure-aware RAG and controlled comparisons

- Inspect the current upstream PageIndex API, license, provider support and artifact
  format before selecting a release/commit. Wrap its tree building and reasoning
  retrieval; do not reimplement PageIndex or assume Gemini compatibility.
- Require explicit approval for new major dependencies or extra provider credentials.
- Preserve mappings from tree nodes to original PDF pages and record tree-building
  and reasoning-retrieval calls, including their tokens, latency and cost.
- Define cold/warm precisely: fresh/reused local artifacts and separately controlled
  provider caches. Verify actual cache usage using provider metadata. Include
  full-context caching/storage overhead where applicable.
- Randomize or counterbalance strategy order, repeat trials, pin models/settings,
  and record cache state and failures. Report both query-only and preparation-inclusive
  totals, plus amortization assumptions and uncertainty.

## Scope limits

No OCR, native multimodal PDF comparison, distributed execution, async concurrency,
automatic judge, built-in prices, chunking, embeddings, or tree index yet.
The text ingestion artifact is the common source for the current baseline; future
strategies must document any input-representation differences as experiment variables.
Keep the package independently runnable without managed-cloud-specific tooling.

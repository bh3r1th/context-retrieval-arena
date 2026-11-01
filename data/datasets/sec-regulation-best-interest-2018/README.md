# SEC Regulation Best Interest pilot

`pilot.json` contains **20 questions** about the stored 2018 proposed rule:

- 9 factual questions.
- 4 cross-section questions.
- 2 table lookup questions.
- 2 numerical reasoning questions.
- 3 unanswerable controls.

Each item has a reference answer and physical PDF page IDs. `answerable` defaults
to true for older datasets. An explicit `answerable: false` requires
`evidence_pages: []`; an empty evidence list does not establish that a question is
unanswerable by itself. `--require-references` requires answers for every item and
nonempty evidence for answerable items.

`pilot.review.json` is a separate audit record, never sent to the generation model.
It contains whitespace-normalized source quotations, page IDs, question categories,
arithmetic/absence rationales and document/dataset file hashes. The generation
manifest additionally records a normalized dataset hash; it is not the raw file hash.
Source quotations were checked against extracted PDF text by the assistant. Table
pages 229 and 230 were rendered and inspected. Independent human adjudication is
still pending; this is a research pilot, not a gold-standard dataset.

Unanswerable controls ask for a later final-rule vote, realized 2025 costs, or a
fictional customer's personal account data. None can be established from this
2018 proposal. They have no supporting page evidence; evidence-overlap scores are
therefore null. Their canonical reference is `Cannot determine from this document.`
Lexical scoring can penalize synonymous abstentions; manually review these answers.

The questions intentionally refer to the historical proposal. Do not substitute
the 2019 final rule or current law. All proposed obligations are hypothetical
requirements of this document, not claims about current legal obligations.

The pilot is curated for debugging and covers only selected sections. It is not
an unbiased sample of all 408 pages. Expand to 100–200 balanced questions only
after source review and the full-context pilot. Do not treat pilot scores as final
strategy-comparison results.

See [the pilot runbook](../../../docs/pilot-runbook.md) for local validation, token
counting, live-run prerequisites and manual answer review.

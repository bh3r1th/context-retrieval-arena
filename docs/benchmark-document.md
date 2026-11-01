# Selected benchmark PDF

**SEC — Proposed Rule: Regulation Best Interest**, Release 34-83062, File S7-07-18,
dated April 18, 2018 (conformed to Federal Register version).

- **408 physical pages**, 1,803,860 bytes (about 1.8 MB).
- Extracted text: **910,070 characters**, about **127,270 whitespace-delimited words**.
- No pages with empty extracted text. No OCR was needed for extraction.
- SHA-256: `d8611d968d8ba9542ec775f43b80953b365758599701fd9c438383a6b82cd58f`.

This is a substantial text workload despite the compact PDF size. It has a detailed
hierarchical table of contents, definitions and obligations, economic analysis,
numerical tables, extensive footnotes and cross-references, alternatives, and proposed
regulatory text. These support factual, numerical, cross-section and unanswerable
questions. PageIndex also distributes it as an example, making it convenient for
later integration. Do not reuse its prebuilt tree for a cold indexing measurement.

This is a **historical proposed rule**, not the final rule or current legal guidance.
Questions must explicitly refer to this document rather than today's regulations.
It is publicly available and may appear in model training data; evidence-grounded
questions and unanswerable controls should address this limitation.

## Source and retained files

[Pinned PDF download from the PageIndex example collection](https://raw.githubusercontent.com/VectifyAI/PageIndex/2e0f4dd35aa6a24c2dedfcf54678b0b0ad323ce8/examples/documents/Regulation%20Best%20Interest_proposed%20rule.pdf).
The download is a mirror copy; identity was checked from the PDF title, metadata,
release number and contents. It was not independently compared with SEC-hosted bytes.
SEC-authored government content is distinct from PageIndex's software license.

The source PDF and provenance are committed under
`data/documents/sec-regulation-best-interest-2018/`:

- [regulation-best-interest-proposed-rule.pdf](../data/documents/sec-regulation-best-interest-2018/regulation-best-interest-proposed-rule.pdf): the downloaded source.
- [source.json](../data/documents/sec-regulation-best-interest-2018/source.json): source URL, pinned repository revision, hash and measured statistics from initial validation.

Generated `document.json` and `preflight.json` remain under the ignored
`artifacts/documents/sec-regulation-best-interest-2018/` directory. A fresh checkout
already includes the PDF. Verify its SHA-256 and regenerate extracted text locally:

```sh
sha256sum data/documents/sec-regulation-best-interest-2018/regulation-best-interest-proposed-rule.pdf
uv run --no-sync cra ingest \
  data/documents/sec-regulation-best-interest-2018/regulation-best-interest-proposed-rule.pdf \
  --output artifacts/documents/sec-regulation-best-interest-2018/document.json
uv run --no-sync cra check \
  --document artifacts/documents/sec-regulation-best-interest-2018/document.json \
  --source-pdf data/documents/sec-regulation-best-interest-2018/regulation-best-interest-proposed-rule.pdf \
  --questions examples/questions.json --min-pages 300
```

The ingestion CLI rejects existing output files; use a new output path when rerunning.

The existing example dataset is a placeholder, so preflight warns about absent
references and pilot size. It does not establish dataset readiness.

## Validation and next step

All 408 pages were extracted. Text was spot-checked across the document, including
table-containing pages; the table of contents at physical page 4 was also rendered
and inspected. Extraction completed in about 12.8 seconds on the current machine.
These checks do not constitute a full visual/table-accuracy audit.

A [20-question pilot](../data/datasets/sec-regulation-best-interest-2018/README.md)
now includes physical page evidence and a separate quotation audit. The assistant
checked supporting source text and rendered numerical table pages 229/230;
independent human adjudication remains pending. The real PDF and pilot pass
`cra check --require-references`, with only the expected pilot-size warning.

Next: follow [the pilot runbook](pilot-runbook.md) for human review and later Gemini
token counting. Context fit must be measured for the selected model before a paid
run. The current authorized API budget is zero. No live token count, generation,
or answer-quality evaluation score is claimed.

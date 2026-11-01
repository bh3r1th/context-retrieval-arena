"""Machine-readable results and local, denominator-aware comparative reports."""

import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median

METRICS = ("exact_match", "token_f1", "supplied_page_recall", "cited_page_recall", "cited_page_precision")


def summarize(manifest: dict, rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("Cannot summarize an empty run")
    for row in rows:
        for name in ("query_seconds", "generation_seconds", "retrieval_seconds", "cost_usd"):
            value = row[name]
            if name == "cost_usd" and value is None:
                continue
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid result value for {name}")
        for name in METRICS:
            value = row["evaluation"][name]
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError(f"Invalid metric value for {name}")
    latencies = sorted(row["query_seconds"] for row in rows)
    costs = [row["cost_usd"] for row in rows if row["cost_usd"] is not None]
    summary = {
        "strategy": manifest["strategy"], "questions": len(rows),
        "ok": sum(row["status"] == "ok" for row in rows),
        "error": sum(row["status"] == "error" for row in rows),
        "incomplete": sum(row["status"] == "incomplete" for row in rows),
        "unanswerable_questions": sum(not row.get("answerable", True) for row in rows),
        "query_seconds_mean": mean(latencies), "query_seconds_median": median(latencies),
        "query_seconds_p95": latencies[math.ceil(0.95 * len(latencies)) - 1],
        "extraction_seconds": manifest["extraction_seconds"],
        "run_seconds": manifest["run_seconds"],
        "priced_queries": len(costs), "known_query_cost_usd": sum(costs),
        "total_query_cost_usd": sum(costs) if len(costs) == len(rows) else None,
    }
    for metric in METRICS:
        values = [row["evaluation"][metric] for row in rows if row["evaluation"][metric] is not None]
        summary[metric] = mean(values) if values else None
        summary[f"{metric}_count"] = len(values)
    for name in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens"):
        values = [row["usage"][name] for row in rows if row["usage"][name] is not None]
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError(f"Invalid usage value for {name}")
        summary[f"{name}_reported_queries"] = len(values)
        summary[f"{name}_known_sum"] = sum(values)
        summary[f"{name}_total"] = sum(values) if len(values) == len(rows) else None
    return summary


def render_report(summaries: list[dict]) -> str:
    def display(value):
        return "—" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)

    columns = ["run", "strategy", "questions", "ok", "error", "incomplete", "exact_match",
               "token_f1", "cited_page_recall", "query_seconds_p95", "total_query_cost_usd"]
    lines = ["# Experiment report", "", "| " + " | ".join(columns) + " |",
             "| " + " | ".join("---" for _ in columns) + " |"]
    for i, summary in enumerate(summaries, 1):
        lines.append("| " + " | ".join(display(i if c == "run" else summary[c]) for c in columns) + " |")
    lines.extend(["", "Run numbers follow input order; full paths and denominators are in summary.json/CSV.",
                  "Lexical exact match/F1 are not semantic accuracy. Page overlap does not verify citation support.",
                  "Failed/incomplete answers score zero where references exist; missing references are unscored.",
                  "Missing prices or token counts leave total cost unknown (—), not zero.",
                  "Costs cover reported tokens only; exclude storage, hidden retries, and other fees.",
                  "P95 uses nearest rank. Query time excludes PDF ingestion and artifact I/O.",
                  "Provider caching is uncontrolled; this is not a controlled cold/warm comparison.", ""])
    return "\n".join(lines)


def write_summary(directory: Path, summaries: list[dict]) -> None:
    (directory / "summary.json").write_text(json.dumps(summaries, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (directory / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    (directory / "report.md").write_text(render_report(summaries), encoding="utf-8")


def compare_runs(paths: list[Path]) -> list[dict]:
    if not paths:
        raise ValueError("At least one results.json is required")
    summaries, expected, expected_questions = [], None, None
    model_versions = set()
    required = ("provider", "generation", "document_sha256", "document_content_sha256", "dataset_sha256",
                "prompt_version", "evaluation_version", "pricing", "page_count", "question_count")
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest, rows = data["manifest"], data["results"]
        if manifest.get("schema_version") != 2:
            raise ValueError("Reports require schema version 2; rerun older experiments")
        if any(key not in manifest for key in required):
            raise ValueError("Run manifest is missing comparison metadata")
        current = {key: manifest[key] for key in required}
        if expected is not None and current != expected:
            raise ValueError("Runs differ in document, dataset, generation, prompt, evaluation, or pricing settings")
        expected = current
        ids = [row["question_id"] for row in rows]
        if len(ids) != manifest["question_count"] or len(ids) != len(set(ids)):
            raise ValueError("Run has missing or duplicate question results")
        normalized = [{"id": row["question_id"], "question": row["question"],
                       "reference_answer": row["reference_answer"],
                       "evidence_pages": row["reference_evidence_pages"]} for row in rows]
        for record, row in zip(normalized, rows):
            if type(row.get("answerable", True)) is not bool:
                raise ValueError("Result answerable labels must be boolean")
            if not row.get("answerable", True):
                record["answerable"] = False
        digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if digest != manifest["dataset_sha256"]:
            raise ValueError("Result questions/references do not match the dataset fingerprint")
        questions = sorted((row["question_id"], row["question"], row["reference_answer"],
                            row["reference_evidence_pages"]) for row in rows)
        if expected_questions is not None and questions != expected_questions:
            raise ValueError("Run question results do not match")
        expected_questions = questions
        model_versions.update(row["model_version"] for row in rows if row["model_version"])
        if len(model_versions) > 1:
            raise ValueError("Runs contain different resolved model versions")
        if any(row.get("status") not in {"ok", "error", "incomplete"} for row in rows):
            raise ValueError("Run contains an unknown result status")
        summary = summarize(manifest, rows)
        summary["source"] = str(path)
        summaries.append(summary)
    return summaries


def write_results(directory: Path, manifest: dict, rows: list[dict]) -> None:
    summary = summarize(manifest, rows)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "results.json").write_text(
        json.dumps({"manifest": manifest, "results": rows}, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with (directory / "results.csv").open("w", encoding="utf-8", newline="") as stream:
        flattened = []
        for row in rows:
            flat = {k: v for k, v in row.items() if k not in {"usage", "evaluation"}}
            flat.update(row["usage"])
            flat.update(row["evaluation"])
            flattened.append({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in flat.items()})
        writer = csv.DictWriter(stream, fieldnames=list(flattened[0]))
        writer.writeheader()
        writer.writerows(flattened)
    write_summary(directory, [summary])

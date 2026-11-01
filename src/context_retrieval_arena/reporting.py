"""Machine-readable artifacts; comparative reports follow in phase 2."""

import csv
import json
from pathlib import Path


def write_results(directory: Path, manifest: dict, rows: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "results.json").write_text(
        json.dumps({"manifest": manifest, "results": rows}, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with (directory / "results.csv").open("w", encoding="utf-8", newline="") as stream:
        flattened = []
        for row in rows:
            flat = {k: v for k, v in row.items() if k != "usage"}
            flat.update(row["usage"])
            flattened.append({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in flat.items()})
        writer = csv.DictWriter(stream, fieldnames=list(flattened[0]))
        writer.writeheader()
        writer.writerows(flattened)

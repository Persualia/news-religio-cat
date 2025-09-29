#!/usr/bin/env python3
"""CLI helper to execute all intent plans against Qdrant."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

THIS_FILE = Path(__file__).resolve()
SAMPLES_DIR = THIS_FILE.parent
ROOT = SAMPLES_DIR.parents[1]

import sys

for candidate in (ROOT, ROOT / "src"):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from scripts.samples.search_executor import execute_plan, ensure_clients

PLANS_PATH = SAMPLES_DIR / "query_intents.json"
OUTPUT_DIR = SAMPLES_DIR / "executed_plans"


def load_plans(path: Path) -> Dict[str, Dict[str, Any]]:
    data = json.loads(path.read_text())
    plans = data.get("plans")
    if not isinstance(plans, dict):
        raise SystemExit("query_intents.json no contiene 'plans' válidos")
    return plans


def slugify(text: str) -> str:
    import re

    normalized = (
        re.sub(r"\s+", " ", text.strip().lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "query"


def main() -> None:
    load_dotenv()
    plans = load_plans(PLANS_PATH)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    qdrant_client, openai_client = ensure_clients()

    summary = []
    for idx, (query_text, plan) in enumerate(plans.items(), start=1):
        print(f"[{idx}/{len(plans)}] Ejecutando: {query_text}")
        try:
            result = execute_plan(
                query_text,
                plan,
                qdrant_client=qdrant_client,
                openai_client=openai_client,
            )
            status = "ok"
            error = None
        except Exception as exc:  # noqa: BLE001
            result = None
            status = "error"
            error = str(exc)
            print(f"  ✖ Error: {error}")

        file_slug = f"{idx:02d}_{slugify(query_text)[:80]}"
        output_path = OUTPUT_DIR / f"{file_slug}.json"
        payload = {
            "query": query_text,
            "plan": plan,
            "status": status,
            "results": result,
        }
        if error:
            payload["error"] = error
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        summary.append(
            {
                "query": query_text,
                "intent": plan.get("intent"),
                "status": status,
                "result_file": str(output_path.relative_to(ROOT)),
                "error": error,
            }
        )
        if status == "ok":
            print(f"  ✓ Guardado en {output_path}")

    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Resumen guardado en {summary_path}")


if __name__ == "__main__":
    main()

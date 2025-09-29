#!/usr/bin/env python3
"""Generate final answers using an agent with access to search_qdrant tool."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

THIS_FILE = Path(__file__).resolve()
SAMPLES_DIR = THIS_FILE.parent
ROOT = SAMPLES_DIR.parents[1]

import sys

for candidate in (ROOT, ROOT / "src"):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from openai import OpenAI

from scripts.samples.search_executor import execute_plan, ensure_clients

PLANS_PATH = SAMPLES_DIR / "query_intents.json"
EXECUTED_DIR = SAMPLES_DIR / "executed_plans"
SUMMARY_PATH = EXECUTED_DIR / "summary.json"

MODEL = "gpt-4.1-mini"
TOOL_NAME = "search_qdrant"

AGENT_PROMPT = (
    "Eres un asistente periodístico. Recibes la consulta original del usuario y el plan "
    "generado por un planner. Decide si necesitas buscar en la base de datos Qdrant usando la herramienta "
    "`search_qdrant`. Usa el plan como guía (puedes ajustar `topK` o `per_site` si necesitas más cobertura). "
    "Cuando llames a la herramienta, envía un JSON con `query` (la consulta original) y `plan` (el plan que quieras ejecutar).\n\n"
    "Si la herramienta devuelve resultados, utilízalos para responder. Incluye fragmentos, citas o datos concretos cuando sea relevante, "
    "y cita las fuentes usando formato [texto](URL).\n\n"
    "Si no necesitas buscar, responde directamente. Si el contexto obtenido es insuficiente para una respuesta fiable, explícalo "
    "y sugiere qué información faltaría.\n\n"
    "Responde siempre en el mismo idioma de la consulta original."
)

TOOL_SPEC = {
    "type": "function",
    "name": TOOL_NAME,
    "description": "Ejecuta un plan de búsqueda contra Qdrant y devuelve artículos, fragmentos y contexto.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Consulta original del usuario."
            },
            "plan": {
                "type": "object",
                "description": "Plan de búsqueda generado por el planner (puede ajustarse)."
            }
        },
        "required": ["query", "plan"],
        "additionalProperties": False,
    },
}


def load_plans(path: Path) -> Dict[str, Dict[str, Any]]:
    data = json.loads(path.read_text())
    plans = data.get("plans")
    if not isinstance(plans, dict):
        raise SystemExit("query_intents.json no contiene 'plans' válidos")
    return plans


def build_user_message(query: str, plan: Dict[str, Any]) -> str:
    plan_json = json.dumps(plan, indent=2, ensure_ascii=False)
    return (
        f"Consulta original:\n{query}\n\n"
        f"Plan sugerido (no modificar la estructura, sólo ajustar topK/per_site si lo consideras necesario):\n"
        f"{plan_json}\n\n"
        "Indica si precisas datos de Qdrant. Si los necesitas, llama a la herramienta `search_qdrant` con el JSON adecuado."
    )


def collect_tool_calls(response) -> List[Any]:
    calls = []
    outputs = getattr(response, "output", None) or []
    for output in outputs:
        output_type = getattr(output, "type", None)
        if output_type == "function_call":
            calls.append(output)
            continue
        contents = getattr(output, "content", None) or []
        for item in contents:
            if getattr(item, "type", None) == "tool_call":
                tool_call = getattr(item, "tool_call", None)
                calls.append(tool_call or item)
    return calls


def get_output_text(response) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    outputs = getattr(response, "output", None) or []
    for output in outputs:
        contents = getattr(output, "content", None) or []
        for item in contents:
            if getattr(item, "type", None) == "output_text":
                return item.text
    return ""


def call_agent(query: str, plan: Dict[str, Any], *, qdrant_client=None, openai_client=None) -> str:
    qdrant_client, openai_client = ensure_clients(qdrant_client, openai_client)
    client = openai_client

    conversation = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": AGENT_PROMPT}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": build_user_message(query, plan)}],
        },
    ]

    response = client.responses.create(
        model=MODEL,
        input=conversation,
        tools=[TOOL_SPEC],
    )

    while True:
        tool_calls = collect_tool_calls(response)
        if not tool_calls:
            break

        for call in tool_calls:
            arguments = getattr(call, "arguments", None)
            if arguments is None and hasattr(call, "function"):
                arguments = getattr(call.function, "arguments", None)
            if not arguments:
                continue
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                continue
            tool_query = args.get("query") or query
            tool_plan = args.get("plan") or plan
            try:
                result = execute_plan(tool_query, tool_plan, qdrant_client=qdrant_client, openai_client=openai_client)
            except Exception as exc:  # noqa: BLE001
                result_payload = {"error": str(exc)}
            else:
                result_payload = result
            conversation.append(
                {
                    "role": "developer",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Resultado de {TOOL_NAME}:\n" + json.dumps(result_payload, ensure_ascii=False),
                        }
                    ],
                }
            )
        response = client.responses.create(
            model=MODEL,
            input=conversation,
            tools=[TOOL_SPEC],
        )

    return get_output_text(response).strip()


def main() -> None:
    load_dotenv()
    plans = load_plans(PLANS_PATH)
    EXECUTED_DIR.mkdir(parents=True, exist_ok=True)

    qdrant_client, openai_client = ensure_clients()

    for idx, (query_text, plan) in enumerate(plans.items(), start=1):
        file_slug = f"{idx:02d}_{slugify(query_text)[:80]}"
        result_file = EXECUTED_DIR / f"{file_slug}.json"
        if not result_file.exists():
            continue
        print(f"[{idx}/{len(plans)}] Generando respuesta del agente: {query_text}")
        answer = call_agent(query_text, plan, qdrant_client=qdrant_client, openai_client=openai_client)
        data = json.loads(result_file.read_text())
        data["agent_answer"] = answer
        result_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"  ✓ Respuesta guardada en {result_file}")


def slugify(text: str) -> str:
    import re

    normalized = (
        re.sub(r"\s+", " ", text.strip().lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "query"


if __name__ == "__main__":
    main()

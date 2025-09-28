#!/usr/bin/env python3
"""Extract intents for query samples using OpenAI structured outputs."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover - env guard for local runs
    raise SystemExit("The 'openai' package is required. Install with pip install -r requirements.txt") from exc


@dataclass
class ExtractionResult:
    """Holds the outcome for a single query."""

    query: str
    plan: Optional[Dict[str, Any]]
    error: Optional[str] = None


THIS_FILE = Path(__file__).resolve()
SAMPLES_DIR = THIS_FILE.parent
ROOT = SAMPLES_DIR.parents[2]

QUERY_SAMPLES_PATH = SAMPLES_DIR / "query_samples.yml"
SCHEMA_PATH = SAMPLES_DIR / "intent_schema.yml"
PROMPT_PATH = SAMPLES_DIR / "intent_extractor_prompt.yml"
OUTPUT_PATH = SAMPLES_DIR / "query_intents.json"

DEFAULT_MODEL = "gpt-4.1-mini"

DATE_TOOL_NAME = "get_current_date"
DATE_TOOL = {
    "type": "function",
    "name": DATE_TOOL_NAME,
    "description": "Obtén la fecha actual en la zona horaria Europe/Madrid en formato YYYY-MM-DD.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text())
    except FileNotFoundError as exc:  # pragma: no cover - surfacing config issues
        raise SystemExit(f"Required file not found: {path}") from exc


def load_query_samples(path: Path) -> List[str]:
    raw = load_yaml(path)
    if isinstance(raw, Mapping):
        candidates = raw.get("QUERY_SAMPLES")
    else:
        candidates = raw

    if not isinstance(candidates, list):
        raise SystemExit(f"Expected a list of queries in {path}, found: {type(candidates)!r}")

    queries: List[str] = []
    for item in candidates:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized:
            queries.append(normalized)

    if not queries:
        raise SystemExit(f"No usable queries found in {path}")
    return queries


def load_prompt(path: Path) -> str:
    raw = load_yaml(path)
    if isinstance(raw, Mapping):
        prompt = raw.get("INTENT_PROMPT")
    else:
        prompt = raw
    if not isinstance(prompt, str):
        raise SystemExit(f"Prompt string not found in {path}")
    prompt = prompt.strip()
    if not prompt:
        raise SystemExit(f"Prompt in {path} is empty")
    return prompt


def load_schema(path: Path) -> Dict[str, Any]:
    raw = load_yaml(path)
    if not isinstance(raw, MutableMapping):
        raise SystemExit(f"Schema in {path} must be a JSON object")
    return build_compatible_schema(dict(raw))


def build_compatible_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Strip unsupported keywords so Responses API can enforce the schema file."""

    strip_keys = {"$schema", "$id", "description", "title"}

    def sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: Dict[str, Any] = {}
            for key, nested in value.items():
                if key in strip_keys:
                    continue
                cleaned[key] = sanitize(nested)
            return cleaned
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    return sanitize(schema)


def extract_json_from_response(response: Any) -> Dict[str, Any]:
    """Attempt to recover the structured JSON payload from a Responses API reply."""

    # Preferred property on recent SDK releases
    parse_error: Optional[str] = None
    output_text = getattr(response, "output_text", None)
    if output_text:
        parsed: Optional[Any] = None
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as err:  # pragma: no cover - unexpected format
            parse_error = f"Model output is not valid JSON: {err}"
        if isinstance(parsed, dict):
            return parsed
        if parsed is not None:
            parse_error = "Structured output is not a JSON object"

    # Fall back to digging into the response structure
    if hasattr(response, "model_dump"):
        raw = response.model_dump()
    elif hasattr(response, "to_dict"):
        raw = response.to_dict()
    elif hasattr(response, "dict"):
        raw = response.dict()  # type: ignore[call-arg]
    elif hasattr(response, "json"):
        raw = json.loads(response.json())
    elif isinstance(response, dict):
        raw = response
    else:  # pragma: no cover - safety net
        raise ValueError("Cannot introspect response payload")

    outputs = raw.get("output") if isinstance(raw, dict) else None
    if not outputs:
        if parse_error:
            raise ValueError(parse_error)
        raise ValueError("Response did not include any output content")

    for output in outputs:
        if isinstance(output, dict):
            contents = output.get("content")
        else:
            contents = getattr(output, "content", None)
        if not contents:
            continue
        for content in contents:
            if isinstance(content, dict):
                if "json" in content:
                    payload = content["json"]
                    if isinstance(payload, dict):
                        return payload
                text = content.get("text")
            else:
                payload = getattr(content, "json", None)
                if isinstance(payload, dict):
                    return payload
                text = getattr(content, "text", None)
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    if parse_error:
        raise ValueError(parse_error)
    raise ValueError("Unable to extract JSON payload from response")


def run_extraction(
    client: OpenAI,
    *,
    model: str,
    prompt: str,
    schema: Dict[str, Any],
    query: str,
) -> Dict[str, Any]:
    base_input = [
        {
            "role": "system",
            "content": [
                {"type": "input_text", "text": prompt},
                {
                    "type": "input_text",
                    "text": "You MUST comply with the JSON schema via structured outputs.",
                },
            ],
        },
        {"role": "user", "content": [{"type": "input_text", "text": query}]},
    ]

    response = client.responses.create(
        model=model,
        input=base_input,
        text={
            "format": {
                "type": "json_schema",
                "name": "intent_schema_v3_1",
                "schema": schema,
                "strict": True,
            }
        },
        tools=[DATE_TOOL],
    )
    resolved = resolve_tool_calls(
        client,
        response,
        model=model,
        schema=schema,
        base_input=base_input,
    )
    return extract_json_from_response(resolved)


def resolve_tool_calls(
    client: OpenAI,
    response: Any,
    *,
    model: str,
    schema: Dict[str, Any],
    base_input: List[Dict[str, Any]],
) -> Any:
    """Handle tool call outputs; currently supports get_current_date."""

    current = response
    conversation = list(base_input)
    while True:
        tool_calls = list(iter_tool_calls(current))
        if not tool_calls:
            return current

        outputs = []
        for call in tool_calls:
            name = getattr(call, "name", None)
            if not name and hasattr(call, "function"):
                name = getattr(call.function, "name", None)
            if name != DATE_TOOL_NAME:
                raise ValueError(f"Unsupported tool requested: {name}")

            payload = {
                "today": current_date_madrid(),
                "timezone": "Europe/Madrid",
            }

            conversation.append(
                {
                    "role": "developer",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Tool {DATE_TOOL_NAME} result: {json.dumps(payload)}",
                        }
                    ],
                }
            )

        current = client.responses.create(
            model=model,
            input=conversation,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "intent_schema",
                    "schema": schema,
                    "strict": True,
                }
            },
        )


def iter_tool_calls(response: Any) -> Any:
    outputs = getattr(response, "output", None) or []
    for output in outputs:
        output_type = getattr(output, "type", None)
        if output_type == "function_call":
            yield output
            continue

        contents = getattr(output, "content", None) or []
        for item in contents:
            if getattr(item, "type", None) == "tool_call":
                tool_call = getattr(item, "tool_call", None)
                yield tool_call or item


def current_date_madrid() -> str:
    now = datetime.now(ZoneInfo("Europe/Madrid"))
    return now.strftime("%Y-%m-%d")


def main() -> None:
    load_dotenv()

    queries = load_query_samples(QUERY_SAMPLES_PATH)
    schema = load_schema(SCHEMA_PATH)
    prompt = load_prompt(PROMPT_PATH)

    client = OpenAI()

    results: List[ExtractionResult] = []
    for idx, query in enumerate(queries, start=1):
        print(f"[{idx}/{len(queries)}] Processing query: {query}")
        try:
            plan = run_extraction(
                client,
                model=DEFAULT_MODEL,
                prompt=prompt,
                schema=schema,
                query=query,
            )
            results.append(ExtractionResult(query=query, plan=plan))
            print("  ✓ Intent extracted")
        except Exception as error:  # noqa: BLE001 - we want to persist the failure
            message = str(error)
            results.append(ExtractionResult(query=query, plan=None, error=message))
            print(f"  ✖ Extraction failed: {message}")

    output_payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": DEFAULT_MODEL,
        "total_queries": len(results),
        "successful": sum(1 for item in results if item.plan is not None),
        "failed": sum(1 for item in results if item.error is not None),
        "plans": {item.query: item.plan for item in results if item.plan is not None},
    }
    failures = {item.query: item.error for item in results if item.error is not None}
    if failures:
        output_payload["errors"] = failures

    OUTPUT_PATH.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False))
    print(f"Saved aggregated intents to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

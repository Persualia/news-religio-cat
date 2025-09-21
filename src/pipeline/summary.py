"""Utilities to summarize daily news and notify n8n."""
from __future__ import annotations

from typing import Sequence

import httpx
from openai import OpenAI

from config import get_settings
from models import Article

_MODEL = "gpt-4.1-mini"
_CLIENT: OpenAI | None = None


def _get_client() -> OpenAI:
    global _CLIENT
    if _CLIENT is None:
        settings = get_settings()
        _CLIENT = OpenAI(api_key=settings.openai.api_key)
    return _CLIENT


def summarize_articles(articles: Sequence[Article]) -> str:
    if not articles:
        return "No articles scraped today."

    client = _get_client()
    items = [f"- {article.title} ({article.site})" for article in articles[:10]]
    prompt = (
        "Redacta un resum concís en català de les notícies següents, "
        "destacant el context religiós quan sigui rellevant:\n"
        + "\n".join(items)
    )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Ets un periodista que resumeix notícies religioses catalanes.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=400,
    )
    return response.choices[0].message.content.strip()


def post_summary(summary: str) -> httpx.Response:
    settings = get_settings()
    headers = {"Content-Type": "application/json"}
    if settings.summary.auth_token:
        headers["Authorization"] = f"Bearer {settings.summary.auth_token}"

    payload = {"summary": summary}

    with httpx.Client() as client:
        response = client.post(settings.summary.endpoint, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        return response


__all__ = ["summarize_articles", "post_summary"]

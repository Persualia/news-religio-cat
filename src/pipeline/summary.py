"""Utilities to summarize daily news and notify n8n."""
from __future__ import annotations

from collections import defaultdict
import logging
from textwrap import shorten
from typing import Sequence, Tuple

import httpx
from openai import OpenAI

from config import get_settings
from models import Article

_MODEL = "gpt-4.1-mini"
_CLIENT: OpenAI | None = None
_MAX_HIGHLIGHTS = 6

_KEYWORD_WEIGHTS = {
    "papa": 3.0,
    "francisc": 3.0,
    "benet": 2.5,
    "vatican": 2.5,
    "vaticà": 2.5,
    "sant": 1.5,
    "canon": 1.5,
    "vocations": 1.5,
    "vocació": 1.5,
    "educació": 1.0,
    "joves": 1.5,
    "solidar": 1.0,
    "conflicte": 1.0,
    "pau": 1.0,
    "refugiat": 1.0,
    "confess": 1.0,
    "celebració": 1.0,
}


def _get_client() -> OpenAI:
    global _CLIENT
    if _CLIENT is None:
        settings = get_settings()
        _CLIENT = OpenAI(api_key=settings.openai.api_key)
    return _CLIENT


def summarize_articles(articles: Sequence[Article]) -> str:
    if not articles:
        return "No articles scraped today."

    scored = [(article, _relevance_score(article)) for article in articles]
    scored.sort(key=lambda item: item[1], reverse=True)

    highlight_text, highlighted_urls = _generate_highlights(scored[:_MAX_HIGHLIGHTS]) if scored else ("", set())
    markdown_listing = _build_markdown_listing(scored, highlighted_urls)

    if highlight_text:
        return f"{highlight_text}\n\n{markdown_listing}".strip()
    return markdown_listing


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


def _relevance_score(article: Article) -> float:
    score = 1.0
    text = " ".join(
        filter(
            None,
            [article.title, article.description, article.content[:600]],
        )
    ).lower()

    for keyword, weight in _KEYWORD_WEIGHTS.items():
        if keyword in text:
            score += weight

    score += min(len(article.content) / 600, 3)
    if article.description:
        score += 0.5
    return score


def _generate_highlights(scored_articles: Sequence[tuple[Article, float]]) -> Tuple[str, set[str]]:
    if not scored_articles:
        return "", set()

    client = _get_client()
    lines: list[str] = []
    for idx, (article, score) in enumerate(scored_articles, start=1):
        snippet_source = article.description or article.content
        snippet = shorten(snippet_source.replace("\n", " "), width=220, placeholder="…")
        lines.append(
            f"{idx}. Site: {article.site} | Autor: {article.author or 'Sense autor'} | Score: {score:.2f} | "
            f"TitleMarkdown: [{article.title}]({article.url}) | Summary: {snippet}"
        )

    prompt = (
        "Genera un apartat '## Destacats' amb un màxim de 6 punts. "
        "Format de cada punt: '- [Títol](URL) — Site (Autor opcional): resum breu amb impacte pastoral'. "
        "Respecta l'ordre d'importància (score descendent) i evita repetir els mateixos detalls. "
        "Redacta en català amb to informatiu.\n\n"
        "Notícies ordenades per score:\n"
        + "\n".join(lines)
    )

    logger.info("Calling OpenAI summary with %d highlight entries", len(scored_articles))
    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Ets un periodista especialitzat en actualitat religiosa. "
                    "Redactes resums breus i clars centrats en l'impacte pastoral."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=32768,
    )
    highlighted_urls = {article.url for article, _ in scored_articles}
    return response.choices[0].message.content.strip(), highlighted_urls


def _build_markdown_listing(
    scored_articles: Sequence[tuple[Article, float]],
    highlighted_urls: set[str],
) -> str:
    grouped: dict[str, list[tuple[float, Article]]] = defaultdict(list)
    for article, score in scored_articles:
        grouped[article.site].append((score, article))

    lines: list[str] = ["## Notícies per lloc"]
    for site in sorted(grouped.keys()):
        lines.append(f"### {site}")
        for score, article in sorted(grouped[site], key=lambda item: item[0], reverse=True):
            if article.url in highlighted_urls:
                continue
            author_suffix = f" — {article.author}" if article.author else ""
            lines.append(f"- [{article.title}]({article.url}){author_suffix}")
    return "\n".join(lines)


__all__ = ["summarize_articles", "post_summary"]
logger = logging.getLogger(__name__)

# news-religio-cat


## Goal

* Daily scraping of selected sites.
* Idempotent storage of articles.
* Hybrid retrieval (filters + vector search) for a future RAG chat.
* Auto-summary of the most relevant news via OpenAI and POST to an n8n endpoint.

---



## websites to scrape (initial)

- https://www.salesians.cat/noticies/
- https://jesuites.net/ca/totes-les-noticies
- https://www.maristes.cat/noticies
... more to come


---

## Technology choices (confirmed)

* **Qdrant Cloud** (HNSW) for ANN vector search with payload filtering.
* **Python 3.10** (usar entorno virtual `.venv`).
* **openai** API:

  * Embeddings: `text-embedding-3-small` (1536 dims)
  * Chat: `gpt-4.1-mini` (summaries)
* **GitHub Actions** (scheduled, once per day) to run the ingestion pipeline.

> Rationale: Qdrant Cloud offers low-latency ANN with managed scaling. GitHub Actions provides a simple scheduler. OpenAI models remain cost-effective and easy to integrate.

---

## Data model

Two Qdrant collections keep storage lean:

### 1) `articles`

* Point ID: deterministic SHA1 of the canonical URL.
* Vector: mean of that article's chunk embeddings (1536 dims).
* Payload: `site`, `base_url`, `url`, `lang`, `author`, `title`, `description`, full `content`, `published_at` / `indexed_at` (ISO) and `published_at_ts` / `indexed_at_ts` (epoch), plus `doc_id`.

### 2) `chunks`

* Point ID: `<article_id>:<chunk_ix>`.
* Vector: embedding of the chunk (1536 dims).
* Payload: inherits article metadata (`article_id`, `site`, `lang`, `author`, etc.) plus `chunk_ix`, chunk `content`, and timestamps.

> Chunk-level retrieval powers semantic search while article points provide dedupe + "latest" views.

---

## Repository structure (proposed)

```
news-religio-cat/
├─ src/
│  ├─ config.py              # env, constants
│  ├─ vector_client.py       # Qdrant client factory
│  ├─ embeddings.py          # OpenAI embeddings
│  ├─ summarizer.py          # OpenAI chat summary (system+user)
│  ├─ chunking.py            # chunk_text(text, max_tokens, overlap)
│  ├─ storage.py             # upsert_articles(), bulk_chunks()
│  ├─ pipeline_daily.py      # orchestrates the daily run
│  ├─ scraping/
│  │  ├─ base.py             # BaseScraper (fetch, parse list, parse article)
│  │  ├─ salesians.py        # Site-specific scraper (list + article)
│  │  ├─ jesuites.py
│  │  ├─ maristes.py
│  │  └─ ...
│  └─ tests/
│     ├─ test_salesians.py   # golden tests for parsing functions
│     ├─ test_jesuites.py
│     └─ ...
├─ scripts/
│  ├─ init_indices.py        # create templates + monthly indices + aliases
│  └─ run_daily.py           # CLI entry to run pipeline (used by GH Actions)
├─ .github/workflows/daily.yml
├─ .env.example
├─ requirements.txt
└─ README.md
```

---

## Environment (.env)

```
OPENAI_API_KEY=sk-...
N8N_SUMMARY_ENDPOINT=https://example.com/webhook/news-summary
SUMMARY_TO=periodista@example.com    # optional metadata to send
LANG_DEFAULT=es
CHUNK_MAX_TOKENS=800
CHUNK_OVERLAP=120
QDRANT_URL=https://YOUR-ID.eu-central-1-0.aws.cloud.qdrant.io
QDRANT_API_KEY=xxxxxxxxxxxxxxxx
QDRANT_COLLECTION_PREFIX=news_
```

> `QDRANT_URL` and `QDRANT_API_KEY` configure the managed vector store. Never commit real secrets.

---

## Local setup (.venv)

1. Ejecuta `./scripts/setup_venv.sh` (usa `python3.10` por defecto; sobreescribe con `PYTHON_BIN=...` si es necesario).
2. Activa el entorno: `source .venv/bin/activate`.
3. Lanza los tests con `python -m pytest` y ejecuta los scripts (`python scripts/init_indices.py`, etc.).

> El entorno virtual se ignora por git (`.venv/`).

---

## Logging & dry-run

* Los logs se imprimen por consola con cabecera y resumen final; puedes ajustar la verbosidad con `--log-level` (`DEBUG`, `INFO`, etc.).
* Ejecuta `PYTHONPATH=src python scripts/run_daily.py --dry-run --log-level DEBUG` para inspeccionar los documentos generados (se muestran como JSON multilínea) sin tocar Qdrant ni OpenAI.
* Usa `--no-index` para ejecutar scraping + resumen (+ embeddings opcionales) sin escribir en Qdrant; útil para probar integraciones como n8n.
* En modo normal (sin `--dry-run`/`--no-index`) el pipeline indexa datos y genera resumen final.

---

## Scraping strategy

* **Input**: list of `site` definitions with

  * `name` (site id),
  * `list_url` (news list),
  * parsing config or custom parser class.
* **Two-phase**:

  1. **List phase** — fetch list page(s) and extract items: `title`, `url`, possible `published_at`. Normalize to absolute URLs. Store **candidates** in memory for the run.
  2. **Article phase** — for **new** URLs only (check existence in `articles-live` by URL), fetch article page and extract: `title`, `author`, `published_at` (fallback to None), `content` (clean HTML → text), `lang`.
* **Per-site classes**: `BaseScraper` + subclasses implement `parse_list(html)` and `parse_article(html)`.
* **Idempotency**: `_id = sha1(url)`. If exists, skip or update fields without re-indexing chunks unless content changed.
* **Language**: heuristics (`lang` meta, URL path) or optional lightweight detector. Use `LANG_DEFAULT` otherwise.

**Tests** (golden samples):

* Save a fixture HTML for each site (list and article). Write deterministic tests for `parse_list()` → list of items, and `parse_article()` → structured dict with expected fields.

---

## Chunking

* Token-approx by words initially (`CHUNK_MAX_TOKENS` \~ 800, `CHUNK_OVERLAP` \~ 120).
* Only chunk **full content**; store chunk docs into `chunks-*` with shared metadata.
* Use exact same `_id` scheme: `sha1(url):{chunk_ix}` for idempotent updates.

---

## Embeddings (OpenAI)

* Model: `text-embedding-3-small` (1536-D).
* Vectorize: **content chunks** (mandatory). Optionally title/description later if we see gains.
* Normalization: not required for cosine in Qdrant; keep raw vector from API.

---

## Summaries & n8n integration

* After successful ingestion, collect **top N** headlines for the day (e.g., by `published_at` or by site priority).
* Build a **system prompt** enforcing brief, factual summaries (CA/ES).
* Build a **user prompt** with the list of items and any constraints.
* Use `gpt-4.1-mini` to generate a **bullet digest** (max tokens bounded).
* `POST` JSON to `N8N_SUMMARY_ENDPOINT` with payload: `{date, site_counts, highlights_markdown}`.
* Handle non-200 responses with retry/backoff.

---

## Ingestion pipeline (daily)

1. Resolve monthly index names (`articles-YYYY.MM`, `chunks-YYYY.MM`) and ensure they exist.
2. For each site scraper:

   * Fetch list → new URLs → fetch articles → yield normalized items.
3. Insert/Upsert into **articles** index.
4. Chunk + embed → bulk insert into **chunks** index.
5. Generate summary → POST to n8n endpoint.
6. Metrics/logs: successes, failures, total docs, OpenAI usage, storage growth.

**Bulk settings**:

* Batch size 5–15 MB.
* `refresh_interval` can be relaxed during ingestion; restore afterwards.
* If plan allows, set `replicas=0` for initial loads and back to `1`.

---

## Queries (examples)

* **Última noticia por topic/site**: filter (`site`, `published_at` range), `should` = text BM25 + `knn` on `content_vec`, sort by `published_at:desc`.
* **Entre fechas / por autor**: exact filters + optional vector `knn` for semantic topic.

---

## GitHub Actions (scheduler)

`.github/workflows/daily.yml`

```yaml
name: daily-ingest
on:
  schedule:
    - cron: "0 5 * * *"   # 05:00 UTC daily
  workflow_dispatch: {}
permissions:
  contents: read
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Run pipeline
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          N8N_SUMMARY_ENDPOINT: ${{ secrets.N8N_SUMMARY_ENDPOINT }}
          QDRANT_URL: ${{ secrets.QDRANT_URL }}
          QDRANT_API_KEY: ${{ secrets.QDRANT_API_KEY }}
        run: |
          python scripts/run_daily.py
```

---

## Requirements (minimal)

```
qdrant-client==1.11.*
httpx==0.27.*
beautifulsoup4==4.12.*
python-dotenv==1.0.*
openai==1.*
rapidfuzz==3.*        # optional: dedupe/heuristics
lxml==5.*             # faster HTML parsing
pytest==8.*           # tests
```

---

## Implementation notes & pitfalls

* **`site` vs domain**: `site` is the configured source id (from our list). Do *not* overwrite it with `url`'s host.
* **Dates**: prefer `published_at`; if missing, store `null` and always set `indexed_at`.
* **Encoding**: ensure UTF-8 end-to-end; strip zero-width spaces.
* **Robots/ethics**: respect robots.txt where applicable and throttle requests (sleep, concurrency=2–3).
* **OpenAI limits**: rate-limit and retry; batch embeddings where possible.
* **Storage control**: monthly indices + retention (e.g., keep 6 months hot; snapshot/delete older).
* **Testing**: HTML fixtures for each site; assertions for fields and counts.

---

## What’s out of scope (for now)

* Multi-tenant auth, admin UI.
* Title/description embeddings (can be added if proven beneficial).
* Cross-encoder re-ranking (future quality boost for RAG).

---

## Next steps

1. Scaffold repo with the structure above.
2. Implement `BaseScraper` and one site scraper (Salesians) + tests.
3. Create index templates + monthly indices + aliases.
4. Wire embeddings + chunking + bulk insertion.
5. Implement summary POST to n8n.
6. Add two more scrapers; validate throughput and storage.
7. Enable scheduler in GitHub Actions.

---

## Appendix: minimal Python stubs

**`src/embeddings.py`**

```python
from openai import OpenAI
import os

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def embed(text: str) -> list[float]:
    r = _client.embeddings.create(model="text-embedding-3-small", input=text)
    return r.data[0].embedding
```

**`src/chunking.py`**

```python
def chunk_text(text: str, max_tokens=800, overlap=120):
    words = text.split()
    step = max_tokens - overlap
    return [" ".join(words[i:i+max_tokens]) for i in range(0, len(words), step) if words[i:i+max_tokens]]
```

**`src/vector_client.py`**

```python
from functools import lru_cache

from qdrant_client import QdrantClient

from config import get_settings


@lru_cache(maxsize=1)
def get_client() -> QdrantClient:
    settings = get_settings()
    q = settings.qdrant
    return QdrantClient(url=q.url, api_key=q.api_key, timeout=q.timeout)
```

**`scripts/run_daily.py`**

```python
# Orchestrate: init indices (if needed) -> scrape -> insert articles -> chunk+embed -> insert chunks -> summarize -> POST
```

---

## Evaluation of the plan

* **Meets requirements**: fields minimal; site-specific scrapers; daily scheduler; vector search ready; summaries to n8n.
* **You might add later**: simple `news_domain` for diagnostics (not required), cross-encoder re-rank for RAG quality, and per-language analyzers if retrieval quality needs tuning.
* **Cost control**: monthly indices + retention; embeddings only on chunks; 1 shard; ANN HNSW with modest parameters.

> If you approve this plan, the next deliverable is the initial repo scaffold plus one fully working scraper (Salesians) with tests and the `init_indices.py` script.

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

* **OpenSearch 2.6.0 (Bonsai.io)** with **k-NN (HNSW)** for ANN vector search.
* **Python 3.10** (usar entorno virtual `.venv`).
* **openai** API:

  * Embeddings: `text-embedding-3-small` (1536 dims)
  * Chat: `gpt-4.1-mini` (summaries)
* **GitHub Actions** (scheduled, once per day) to run the ingestion pipeline.

> Rationale: OpenSearch 2.x provides true ANN for low-latency similarity; Bonsai manages the cluster. GitHub Actions offers a free/cheap scheduler. OpenAI models are cost-effective and simple to integrate.

---

## Data model

We keep it **minimal and purposeful**. Two indices:

### 1) `articles-YYYY.MM` (one doc per article)

Fields (all lowercase keys):

* `site` *(keyword)* — **Source identifier** from our websites list (not the article’s domain).
* `url` *(keyword, unique)* — Canonical article URL.
* `base_url` *(keyword)* — URL base del scraper (punto de entrada).
* `lang` *(keyword)* — e.g., `ca`, `es`, `en` (detected or provided).
* `author` *(keyword, nullable)*.
* `published_at` *(date, nullable)* — As parsed; may be missing.
* `indexed_at` *(date)* — Ingestion time (UTC ISO8601).
* `title` *(text, analyzer by language)* — Also vectorized if available.
* `description` *(text, analyzer by language, nullable)* — Also vectorized if available.
* `content` *(text, analyzer by language)* — Full plain-text content (HTML stripped).
* `search_text_short` *(text)* — `title + description` vía `copy_to`, pensado para BM25 de alta precisión.
* `search_text` *(text)* — `title + description + content` vía `copy_to`, usado para recall general.

> **IDs & idempotency**: `_id = sha1(url)` so re-runs update the same doc. No extra synthetic IDs needed.

### 2) `chunks-YYYY.MM` (one doc per content chunk — supports RAG)

* Inherits a subset of article fields for filtering: `site`, `url`, `lang`, `author`, `published_at`, `indexed_at`.
* `chunk_ix` *(integer)* — Order within the article.
* `content` *(text)* — The chunk text.
* `content_vec` *(knn\_vector\[1536])* — Embedding of the chunk.
* (Optional) `title_vec`, `description_vec` only if we later prove value. **Do not create now.**

> Why a separate `chunks` index? Vector search performs best on granular units; we can still show article-level metadata via `url` join in the app. Keeping `articles` clean avoids duplication and simplifies non-vector queries.

---

## OpenSearch settings & mappings

### Common index template

* 1 shard (start simple), 1 replica (after ingestion; can be 0 during bulk load if plan allows).
* Monthly indices with alias `articles-live` / `chunks-live`.
* Language analyzers: start with a simple Spanish analyzer; content in Catalan also benefits from standard/Spanish. We can add `ca` analyzer later if needed.

```jsonc
// Template for articles-*
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1,
    "refresh_interval": "1s",
    "analysis": {
      "analyzer": {
        "es_std": { "type": "standard", "stopwords": "_spanish_" }
      }
    }
  },
  "mappings": {
    "properties": {
      "site":         { "type": "keyword" },
      "url":          { "type": "keyword" },
      "lang":         { "type": "keyword" },
      "author":       { "type": "keyword" },
      "published_at": { "type": "date" },
      "indexed_at":   { "type": "date" },
      "title":        { "type": "text", "analyzer": "es_std" },
      "description":  { "type": "text", "analyzer": "es_std" },
      "content":      { "type": "text", "analyzer": "es_std" }
    }
  }
}
```

```jsonc
// Template for chunks-*
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1,
    "refresh_interval": "1s",
    "knn": true,
    "analysis": {
      "analyzer": {
        "es_std": { "type": "standard", "stopwords": "_spanish_" }
      }
    }
  },
  "mappings": {
    "properties": {
      "site":         { "type": "keyword" },
      "url":          { "type": "keyword" },
      "lang":         { "type": "keyword" },
      "author":       { "type": "keyword" },
      "published_at": { "type": "date" },
      "indexed_at":   { "type": "date" },
      "chunk_ix":     { "type": "integer" },
      "content":      { "type": "text", "analyzer": "es_std" },
      "content_vec": {
        "type": "knn_vector",
        "dimension": 1536,
        "method": {
          "name": "hnsw",
          "space_type": "cosinesimil",
          "engine": "nmslib",
          "parameters": { "m": 16, "ef_construction": 128 }
        }
      }
    }
  }
}
```

> Sorting by recency: include `published_at` and `indexed_at`; queries can `sort: [{"published_at":"desc"}]` or fall back to `indexed_at` when missing.

---

## Repository structure (proposed)

```
news-religio-cat/
├─ src/
│  ├─ config.py              # env, constants
│  ├─ opensearch_client.py   # client factory, template/alias helpers
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
BONSAI_URL=https://USER:PASSWORD@XXXXX.bonsaisearch.net
OPENAI_API_KEY=sk-...
N8N_SUMMARY_ENDPOINT=https://example.com/webhook/news-summary
SUMMARY_TO=periodista@example.com    # optional metadata to send
LANG_DEFAULT=es
CHUNK_MAX_TOKENS=800
CHUNK_OVERLAP=120
```

> `BONSAI_URL` contains credentials. In code, split into host/user/pass. Never commit real `.env`.

---

## Local setup (.venv)

1. Ejecuta `./scripts/setup_venv.sh` (usa `python3.10` por defecto; sobreescribe con `PYTHON_BIN=...` si es necesario).
2. Activa el entorno: `source .venv/bin/activate`.
3. Lanza los tests con `python -m pytest` y ejecuta los scripts (`python scripts/init_indices.py`, etc.).

> El entorno virtual se ignora por git (`.venv/`).

---

## Logging & dry-run

* Los logs se imprimen por consola con cabecera y resumen final; puedes ajustar la verbosidad con `--log-level` (`DEBUG`, `INFO`, etc.).
* Ejecuta `PYTHONPATH=src python scripts/run_daily.py --dry-run --log-level DEBUG` para inspeccionar los documentos generados (se muestran como JSON multilínea) sin tocar OpenSearch ni OpenAI.
* Usa `--no-index` para ejecutar scraping + resumen (+ embeddings opcionales) sin escribir en OpenSearch; útil para probar integraciones como n8n.
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
* Normalization: not required for cosine in OpenSearch; keep raw vector from API.

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
          BONSAI_URL: ${{ secrets.BONSAI_URL }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          N8N_SUMMARY_ENDPOINT: ${{ secrets.N8N_SUMMARY_ENDPOINT }}
        run: |
          python scripts/run_daily.py
```

---

## Requirements (minimal)

```
opensearch-py==2.6.*
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

**`src/opensearch_client.py`**

```python
import os
from urllib.parse import urlparse
from opensearchpy import OpenSearch

BONSAI_URL = os.getenv("BONSAI_URL")
_u = urlparse(BONSAI_URL)

client = OpenSearch(
    hosts=[{"host": _u.hostname, "port": 443}],
    http_auth=(_u.username, _u.password),
    use_ssl=True, verify_certs=True, scheme="https",
)
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

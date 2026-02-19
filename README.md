# news-religio-cat

Ingestion service that gathers the latest headlines from selected Catholic news sources and posts them to Trello. Each successful run keeps a ledger in Google Sheets to avoid duplicates and raises Slack alerts whenever a scraper stops returning results.

---

## Objectives

- Scrape a curated list of sources to obtain title, URL and light metadata (author, published date, language).
- Avoid storing or processing full article content.
- Create a Trello card per unseen article and keep an auditable record in Google Sheets (`Date`, `ID`, `Source`, `Title`).
- Ensure idempotency across runs via deterministic URL hashing and the Google Sheets registry.
- Alert maintainers via Slack if a source stops yielding URLs or if Trello creation fails.

---

## websites to scrape (initial)

1. jesuites (actualitzen sovint) https://jesuites.net/ca/totes-les-noticies
2. maristes https://www.maristes.cat/noticies
3. lasalle https://lasalle.cat/actualitat/
4. escolapia https://escolapia.cat/actualitat/
5. salesians https://www.salesians.cat/noticies/
6. claretians https://claretpaulus.org/ca/actualitat/
7. bisbatsolsona: https://bisbatsolsona.cat/comunicacio/noticies/
8. bisbaturgell: https://bisbaturgell.org/ca/category/actualitat-cat
9. bisbatlleida: https://www.bisbatlleida.org/ca/news
10. bisbattarragona: https://www.arquebisbattarragona.cat/
11. bisbatgirona: https://www.bisbatgirona.cat/ca/noticies.html
12. bisbatbarcelona: https://esglesia.barcelona/noticies/
13. bisbatsantfeliu: https://bisbatsantfeliu.cat/wp-json/wp/v2/posts?per_page=9&_fields=link,title.rendered,date
14. bisbatterrassa: https://www.bisbatdeterrassa.org/wp-json/wp/v2/posts?per_page=9&_fields=link,title.rendered,date
15. bisbatvic: https://www.bisbatvic.org/ca/noticies?field_tax_blog_tid=All
16. bisbattortosa: https://www.bisbattortosa.org/wp-json/wp/v2/posts?per_page=9&_fields=link,title.rendered,date
17. sagradafamilia https://sagradafamilia.org/actualitat
18. santjoandedeu https://sjd.es/wp-json/wp/v2/posts?per_page=9&_fields=link,title.rendered,date
19. abadiamontserrat https://www.millenarimontserrat.cat/noticies
20. peretarres https://www.peretarres.org/actualitat/noticies
21. serveijesuitarefugiats https://jrs.net/es/noticias-e-historias/
22. migrastudium https://www.migrastudium.org/actualitat
23. fundaciocomtal https://comtal.org/es/noticias/
24. caminsfundacio https://www.caminsfundacio.org/posat-al-dia/
25. franciscans https://caputxins.cat/actualitat-caputxina/
26. vedruna https://vedruna.cat/noticies/
27. fedac https://escoles.fedac.cat/noticies/
28. sjddobrasocial https://solidaritat.santjoandedeu.org/actual/
29. blanquerna https://www.blanquerna.edu/ca/noticies
30. iqs https://iqs.edu/ca/iqs/noticies/
31. euss https://neussletter.4veuss.com/
32. justiciaipau https://www.justiciaipau.org/diem
33. gter http://www.grupdereligions.org/
34. islamat https://www.islamcat.org/category/actualitats/
35. urc https://urc.cat/actualitat/
36. moenstirdelpoblet https://www.poblet.cat/ca/actualitat/
37. oar https://ajuntament.barcelona.cat/oficina-afers-religiosos/ca/noticies
38. audir https://audir.org/noticies/
39. dgar https://afersreligiosos.gencat.cat/ca/actualitat/noticies/
40. caritassantfeliu https://www.caritassantfeliu.cat/
41. caritasterrassa https://diocesanaterrassa.caritas.es/es/
42. caritasbarcelona https://blog.caritas.barcelona/es/
43. caritastarragona https://www.caritasdtarragona.cat/que-diem/actualitat/
44. caritasgirona https://www.caritasgirona.cat/
45. cpl https://www.cpl.es/
46. carmelitesdescalcosdecatalunya http://www.carmelcat.cat/
47. iscreb https://www.iscreb.org/ca/comunicacio/noticies
48. opusdei http://opusdei.cat/ca-es/
49. adoratrius http://www.adoratrius.cat/
50. cataloniasacra https://www.cataloniasacra.cat/category/noticies/
51. acat https://acat.pangea.org/
52. fundaciolacaixa https://mediahub.fundacionlacaixa.org/ca/social


## Next websites to scrape (future)

53. Fundació PROIDE http://www.fundacioproide.org/ !no veig pagina de notícies
54. Caputxins http://www.caputxins.cat/ ! ja hi son
55. santaluisademarillac: http://osmarillac.org/ ! no existeix domini
56. Servei Arxiu Monges Benedictines http://www.federaciobenedictines.cat/wordpress/ ! no existeix


---

## Architecture

| Component | Responsibility |
| --- | --- |
| `src/scraping/*` | Site-specific scrapers inheriting from `BaseScraper`. They fetch listing pages and return `NewsItem` instances with metadata only. |
| `src/pipeline/ingestion.py` | `TrelloPipeline` orchestrates scraping, deduplication against Google Sheets, Trello card creation and Slack notifications. |
| `src/integrations/google_sheets.py` | Wraps gspread to read the processed IDs column and append new rows in batch. |
| `src/integrations/trello.py` | Minimal Trello REST client that creates cards with metadata-rich descriptions. |
| `src/integrations/slack.py` | Webhook notifier for anomaly alerts. |
| `scripts/run_daily.py` | CLI entry point (used locally and in GitHub Actions). |

The pipeline is intentionally modular so each integration behaves like a small service that the orchestrator composes.

---

## Repository layout

```
news-religio-cat/
├─ src/
│  ├─ config.py                     # environment settings loader
│  ├─ models.py                     # NewsItem + SheetRecord domain objects
│  ├─ integrations/
│  │  ├─ google_sheets.py           # Google Sheets repository
│  │  ├─ slack.py                   # Slack webhook notifier
│  │  └─ trello.py                  # Trello REST client
│  ├─ pipeline/
│  │  ├─ __init__.py
│  │  └─ ingestion.py               # TrelloPipeline orchestrator
│  └─ scraping/
│     ├─ __init__.py
│     ├─ base.py                    # BaseScraper + HTTP helpers
│     ├─ jesuites.py
│     ├─ maristes.py
│     └─ salesians.py
├─ scripts/
│  └─ run_daily.py                  # CLI for local/GitHub Actions runs
├─ tests/                           # Fixtures and regression tests
├─ requirements.txt
└─ README.md
```

---

## Environment variables

Configure the following variables in `.env` (loaded via `python-dotenv`):

| Variable | Description |
| --- | --- |
| `TRELLO_KEY` / `TRELLO_TOKEN` | Trello API key and token for the service account. |
| `TRELLO_BOARD_ID` | Trello board that owns the target list. |
| `TRELLO_LIST_ID` | Trello list where new cards will be created. |
| `SLACK_BOT_TOKEN` | Bot Token for alerts (optional; skips notifications when omitted). |
| `GOOGLE_PROJECT_ID` | Google Cloud project for the service account. |
| `GOOGLE_CLIENT_EMAIL` | Service account email. |
| `GOOGLE_PRIVATE_KEY` | Private key; keep the literal `\n` sequences (handled by `config.py`). |
| `GOOGLE_SHEET_ID` | Spreadsheet ID containing the processed ledger. |
| `GOOGLE_SHEET_WORKSHEET` | (Optional) Worksheet/tab name; defaults to the first sheet. |
| `GOOGLE_PRIVATE_KEY_ID`, `GOOGLE_CLIENT_ID`, `GOOGLE_TOKEN_URI`, etc. | Optional overrides when not using the default Google endpoints. |
| `SCRAPER_USER_AGENT`, `SCRAPER_REQUEST_TIMEOUT`, `SCRAPER_MAX_RETRIES`, `SCRAPER_THROTTLE_SECONDS` | Scraper tuning knobs with safe defaults. |

The spreadsheet must expose the columns `Date`, `ID`, `Source`, `Title`. The pipeline appends new rows at the bottom so you can pivot or audit historic runs.

---

## Running the pipeline

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=src python scripts/run_daily.py --log-level INFO
```

Useful flags:

- `--dry-run`: scrape sources and report which cards would be created without touching Trello or Google Sheets.
- `--limit-per-site N`: cap the number of items processed per scraper.
- `--sites salesians jesuites`: restrict execution to specific scrapers (comma- or space-separated).

The script prints a JSON summary with totals at the end of the run.
The payload now includes a `live` flag that is `true` when the execution runs from GitHub Actions (production) and `false` otherwise.

---

## GitHub Actions

`.github/workflows/daily-run.yml` reuses `scripts/run_daily.py` on a nightly cron (`0 23 * * *`). Provide the required secrets in the repository or organisation settings to mirror your `.env` configuration.

---

## Slack alerting

- If a scraper returns zero URLs, a Slack alert is raised suggesting a review (site layout likely changed).
- Errors while creating Trello cards also trigger an alert.
- When the run finishes, a Slack block message is posted with the Madrid timestamp plus the aggregate counters (`sources_processed`, `total_items`, `new_items`, `skipped_existing`, `alerts_sent`, `live`) directly to `#catalunya-religio`. `live=true` indicates the message was produced by the GitHub Action.
- When no webhook is configured, the pipeline keeps running and logs the messages locally.

---

## Trello metadata

Every Trello card contains:

- `name`: article title.
- `urlSource`: original article URL.
- `desc`: summary, published date, author and extra metadata captured during scraping.

The deterministic document ID (`sha1(normalised_url)`) is only stored in Google Sheets and used for deduplication, so feel free to archive cards manually without affecting future runs.

---

## Development tips

- Fixtures in `tests/fixtures/` keep representative HTML samples to prevent regressions when updating scrapers.
- The codebase sticks to standard library + `httpx`, `beautifulsoup4`, `gspread` and `google-auth`; avoid pulling large frameworks.
- When adding a new source, focus on delivering metadata directly from listing pages whenever possible.
- Keep Slack alerts actionable: one message per failing source and reuse the deterministic site IDs.

---

## Roadmap ideas

- Add health metrics (Prometheus or simple JSON logs) for ingestion duration and per-source counts.
- Enrich Trello cards with labels or custom fields once taxonomy is defined.
- Introduce a lightweight FastAPI service to expose the last run status if a control plane becomes necessary.

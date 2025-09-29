// Construye la(s) request(s) HTTP a Qdrant según el intent.
// Entrada esperada (del paso 4):
//   { intent, queryText, filters, topK, per_site, embedding?, qFilter? }

// Constantes alineadas con src/search/qdrant_search.py y context_builder.py
const FETCH_MULTIPLIER = 4;              // _search_collection fetch multiplier
const DEFAULT_ARTICLE_TOPK = 10;
const DEFAULT_CHUNK_TOPK = 10;
const DEFAULT_LATEST_PER_SITE = 5;
const DEFAULT_BACKGROUND_TOPK = 20;
const CONTEXT_CANDIDATE_MULTIPLIER = 6;  // DEFAULT_CHUNK_CANDIDATE_MULTIPLIER

// Colecciones por defecto; permiten override vía variables de entorno
const COLLECTION_ARTICLES = 'articles';
const COLLECTION_CHUNKS   = 'chunks';

// Base URL y Auth opcional desde entorno (n8n expone process.env en Function/Code)
const QDRANT_URL = '';
const QDRANT_API_KEY = '';

function headers() {
  const h = { 'Content-Type': 'application/json' };
  if (QDRANT_API_KEY) h['api-key'] = QDRANT_API_KEY;
  return h;
}

function searchParams() {
  // Valores seguros por defecto (coinciden con logging de samples)
  return { hnsw_ef: 256, exact: false, indexed_only: false };
}

function buildSearchRequest(collection, vector, filter, limit) {
  const body = {
    // Qdrant API espera `vector` y `filter`
    vector,
    limit,
    with_payload: true,
    with_vectors: false,
    search_params: searchParams(),
  };
  if (filter) body.filter = filter;
  return {
    method: 'POST',
    url: (QDRANT_URL ? `${QDRANT_URL}` : '') + `/collections/${collection}/points/search`,
    headers: headers(),
    body,
  };
}

function buildScrollRequest(collection, filter, limit) {
  const body = {
    filter: filter || undefined,
    with_payload: true,
    limit,
    offset: null,
  };
  return {
    method: 'POST',
    url: (QDRANT_URL ? `${QDRANT_URL}` : '') + `/collections/${collection}/points/scroll`,
    headers: headers(),
    body,
  };
}

function clampInt(n, min, max, def) {
  const v = Number.isInteger(n) ? n : def;
  return Math.max(min, Math.min(max, v));
}

// Lee datos normalizados de pasos previos
const intent   = String($json.intent || '');
const topK     = Number($json.topK || 0) || 0;
const perSite  = Number($json.per_site || 0) || 0;
const qFilter  = $json.qFilter || undefined;
const embedding = $json.embedding; // puede venir del paso 3 (OpenAI embeddings)
const queryText = String($json.queryText || '').trim();

// Para exact_phrase (solo relevante en search_chunks), lo traemos del paso 1
let exactPhrase = false;
try {
  const plan = $('step_1_normalize_plan').first().json.plan;
  exactPhrase = Boolean(plan && plan.exact_phrase);
} catch (e) {
  exactPhrase = false;
}

const requests = [];

// Helpers de límites (replicando multiplicadores del backend)
function articleFetchLimit(k) {
  const base = k || DEFAULT_ARTICLE_TOPK;
  return Math.max(base, 1) * FETCH_MULTIPLIER;
}
function chunkFetchLimit(k, forContext = false) {
  if (forContext) {
    // build_chat_context: chunk_limit = max((k or DEFAULT_ARTICLE_TOPK) * 4, 20)
    // candidate_limit = chunk_limit * CONTEXT_CANDIDATE_MULTIPLIER
    // luego _search_collection aplica FETCH_MULTIPLIER
    const baseK = k || DEFAULT_ARTICLE_TOPK;
    const chunkLimit = Math.max(baseK * 4, 20);
    return chunkLimit * CONTEXT_CANDIDATE_MULTIPLIER * FETCH_MULTIPLIER;
  }
  const base = k || DEFAULT_CHUNK_TOPK;
  // Si es búsqueda exacta, acostumbra a pedir más y filtrar a posteriori
  const factor = exactPhrase ? 2 : 1;
  return Math.max(base * factor, 1) * FETCH_MULTIPLIER;
}

// Lógica por intent
switch (intent) {
  case 'latest_by_site': {
    const per = perSite || DEFAULT_LATEST_PER_SITE;
    // Si vienen sitios explícitos, emitimos una request por site (scroll)
    const sites = Array.isArray($json.filters?.site) ? $json.filters.site.filter(Boolean) : [];
    if (sites.length) {
      for (const site of sites) {
        const siteFilter = qFilter ? { ...qFilter } : undefined;
        if (siteFilter) {
          // Inyecta condición de site si no estaba
          const must = Array.isArray(siteFilter.must) ? siteFilter.must.slice() : [];
          must.push({ key: 'site', match: { any: [site] } });
          siteFilter.must = must;
        }
        requests.push(buildScrollRequest(COLLECTION_ARTICLES, siteFilter || qFilter, per * 3));
      }
    } else {
      // Scroll único si no se especifican sites
      requests.push(buildScrollRequest(COLLECTION_ARTICLES, qFilter, per * 3));
    }
    break;
  }

  case 'filter_only_articles': {
    const limit = Math.max(topK || DEFAULT_ARTICLE_TOPK, 1) * 2; // pedimos un poco más para ordenar después
    requests.push(buildScrollRequest(COLLECTION_ARTICLES, qFilter, limit));
    break;
  }

  case 'filter_only_chunks': {
    const limit = Math.max(topK || DEFAULT_CHUNK_TOPK, 1) * 2;
    requests.push(buildScrollRequest(COLLECTION_CHUNKS, qFilter, limit));
    break;
  }

  case 'search_articles': {
    if (Array.isArray(embedding) && embedding.length && queryText) {
      requests.push(
        buildSearchRequest(COLLECTION_ARTICLES, embedding, qFilter, articleFetchLimit(topK))
      );
    } else {
      // Fallback sin embedding: scroll
      const limit = Math.max(topK || DEFAULT_ARTICLE_TOPK, 1) * 2;
      requests.push(buildScrollRequest(COLLECTION_ARTICLES, qFilter, limit));
    }
    break;
  }

  case 'search_chunks': {
    if (Array.isArray(embedding) && embedding.length && queryText) {
      requests.push(
        buildSearchRequest(COLLECTION_CHUNKS, embedding, qFilter, chunkFetchLimit(topK, false))
      );
    } else {
      const limit = Math.max(topK || DEFAULT_CHUNK_TOPK, 1) * 2;
      requests.push(buildScrollRequest(COLLECTION_CHUNKS, qFilter, limit));
    }
    break;
  }

  case 'summarize':
  case 'backgrounder': {
    const baseK = topK || DEFAULT_BACKGROUND_TOPK;
    if (Array.isArray(embedding) && embedding.length && queryText) {
      // 1) Artículos principales
      requests.push(
        buildSearchRequest(COLLECTION_ARTICLES, embedding, qFilter, articleFetchLimit(baseK))
      );
      // 2) Contexto (chunks) amplio
      requests.push(
        buildSearchRequest(COLLECTION_CHUNKS, embedding, qFilter, chunkFetchLimit(baseK, true))
      );
    } else {
      // Fallback sin embedding: scroll artículos
      const limit = Math.max(baseK, DEFAULT_ARTICLE_TOPK) * 2;
      requests.push(buildScrollRequest(COLLECTION_ARTICLES, qFilter, limit));
    }
    break;
  }

  case 'compare_viewpoints': {
    const sites = Array.isArray($json.filters?.site) ? $json.filters.site.filter(Boolean) : [];
    const baseK = topK || DEFAULT_ARTICLE_TOPK;
    if (Array.isArray(embedding) && embedding.length && queryText) {
      if (sites.length) {
        for (const site of sites) {
          const siteFilter = qFilter ? { ...qFilter } : undefined;
          if (siteFilter) {
            const must = Array.isArray(siteFilter.must) ? siteFilter.must.slice() : [];
            must.push({ key: 'site', match: { any: [site] } });
            siteFilter.must = must;
          }
          requests.push(
            buildSearchRequest(COLLECTION_ARTICLES, embedding, siteFilter || qFilter, articleFetchLimit(baseK))
          );
        }
      } else {
        requests.push(
          buildSearchRequest(COLLECTION_ARTICLES, embedding, qFilter, articleFetchLimit(baseK))
        );
      }
      // Contexto general para contraste
      requests.push(
        buildSearchRequest(COLLECTION_CHUNKS, embedding, qFilter, chunkFetchLimit(baseK, true))
      );
    } else {
      const limit = Math.max(baseK, DEFAULT_ARTICLE_TOPK) * 2;
      requests.push(buildScrollRequest(COLLECTION_ARTICLES, qFilter, limit));
    }
    break;
  }

  default: {
    // Intent desconocido → no requests; devolvemos tal cual para que el flujo decida
    break;
  }
}

return requests;


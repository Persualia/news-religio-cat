// Consolida y normaliza las respuestas de Qdrant tras ejecutar los requests.
// - Entrada: múltiples items (uno por request ejecutado en el nodo HTTP previo)
// - Salida: un único item con { intent, data, context? }

// Defaults alineados con el backend
const DEFAULT_ARTICLE_TOPK = 10;
const DEFAULT_CHUNK_TOPK = 10;
const DEFAULT_BACKGROUND_TOPK = 20;
const RECENCY_WEIGHT = 0.35;   // src/search/qdrant_search.py
const HALF_LIFE_HOURS = 36.0;  // src/search/qdrant_search.py

// Lee parámetros del plan (pasos previos)
const s2 = $('step_2_sanitize_plan').first().json || {};
const intent = String(s2.intent || '');
const topK = Number(s2.topK || 0) || 0;
const perSite = Number(s2.per_site || 0) || 0;
const queryText = String(s2.queryText || '').trim();
const filters = s2.filters || {};
const exactPhrase = Boolean(($('step_1_normalize_plan').first().json || {}).plan?.exact_phrase);

const nowTs = Math.floor(Date.now() / 1000);

function toInt(value) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.floor(n) : 0;
}

function recencyWeightFromTs(ts, nowTs, halfLifeHours = HALF_LIFE_HOURS) {
  const base = toInt(ts);
  if (!base) return 0.0;
  const delta = Math.max(nowTs - base, 0);
  if (delta <= 0) return 1.0;
  const ageHours = delta / 3600;
  if (halfLifeHours <= 0) return 1.0;
  const decay = Math.exp(-Math.log(2) * (ageHours / halfLifeHours));
  return decay;
}

function combinedScore(vectorScore, recencyW, bias = RECENCY_WEIGHT) {
  const vs = Math.max(Number(vectorScore) || 0, 0);
  const rw = Math.max(Math.min(Number(recencyW) || 0, 1.2), 0);
  const b = Math.max(Math.min(Number(bias) || 0, 0.9), 0);
  return (1 - b) * vs + b * rw;
}

function parseDate(d, end = false) {
  if (!d) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(d)) {
    const dt = new Date(d + (end ? 'T23:59:59.999Z' : 'T00:00:00.000Z'));
    return Math.floor(dt.getTime() / 1000);
  }
  const t = Date.parse(d);
  if (Number.isNaN(t)) return null;
  return Math.floor(t / 1000);
}

function inDateRange(ts, f) {
  if (!ts) return true;
  const gte = parseDate(f.date_from, false);
  const lte = parseDate(f.date_to, true);
  if (gte && ts < gte) return false;
  if (lte && ts > lte) return false;
  return true;
}

function timestampFromPayload(payload) {
  return toInt(payload?.published_at_ts || payload?.indexed_at_ts || 0);
}

function pickFields(payload, desired) {
  const out = {};
  for (const k of desired) {
    if (payload && Object.prototype.hasOwnProperty.call(payload, k)) {
      out[k] = payload[k];
    }
  }
  // Asegura disponibilidad de info de fecha si existe
  for (const k of ['published_at', 'indexed_at', 'published_at_ts', 'indexed_at_ts']) {
    if (payload && payload[k] !== undefined && out[k] === undefined) out[k] = payload[k];
  }
  return out;
}

function makeSnippet(text, limit = 320) {
  if (!text) return '';
  const one = String(text).split(/\s+/).join(' ');
  if (one.length <= limit) return one;
  return one.slice(0, limit).replace(/\s+$/, '') + '…';
}

function normalizePointsFromResponse(resp) {
  // Soporta ambos: search (lista) y scroll (obj con points)
  const result = resp?.result;
  if (!result) return [];
  let points = [];
  if (Array.isArray(result)) {
    points = result;
  } else if (Array.isArray(result?.scored_points)) {
    points = result.scored_points;
  } else if (Array.isArray(result?.points)) {
    points = result.points;
  }
  return points.map((pt) => {
    const payload = pt?.payload || {};
    const ts = timestampFromPayload(payload);
    const score = Number(pt?.score || 0);
    const vectorScore = Number.isFinite(score) ? score : 0;
    const recency = recencyWeightFromTs(ts, nowTs);
    const combined = combinedScore(vectorScore, recency);
    // Clasificación correcta: un CHUNK siempre lleva 'chunk_ix'.
    // Algunos artículos también incluyen 'content'; no usar 'content' para distinguir.
    const isChunk = Object.prototype.hasOwnProperty.call(payload, 'chunk_ix');
    return {
      id: String(pt?.id ?? ''),
      payload,
      vector_score: vectorScore,
      recency_weight: recency,
      combined_score: combined,
      timestamp: ts,
      kind: isChunk ? 'chunk' : 'article',
    };
  });
}

function byCombinedThenTsDesc(a, b) {
  if (b.combined_score !== a.combined_score) return b.combined_score - a.combined_score;
  return (b.timestamp || 0) - (a.timestamp || 0);
}

function byTsDesc(a, b) {
  return (b.timestamp || 0) - (a.timestamp || 0);
}

function serializeResult(hit, fields) {
  const payload = pickFields(hit.payload || {}, fields || []);
  const out = {
    id: hit.id,
    scores: {
      vector: Number.isFinite(hit.vector_score) ? Number(hit.vector_score) : undefined,
      recency: Number.isFinite(hit.recency_weight) ? Number(hit.recency_weight) : undefined,
      combined: Number.isFinite(hit.combined_score) ? Number(hit.combined_score) : undefined,
    },
    timestamp: hit.timestamp || undefined,
    payload,
  };
  // Limpia undefineds/scores vacíos
  if (!out.scores.vector && !out.scores.recency && !out.scores.combined) delete out.scores;
  if (!out.timestamp) delete out.timestamp;
  return out;
}

function filterByDate(hits, f) {
  return hits.filter((h) => inDateRange(h.timestamp, f));
}

// Recolecta todos los puntos de todas las respuestas
const allItems = $input.all();
let allPoints = [];
for (const item of allItems) {
  const resp = item.json || {};
  allPoints = allPoints.concat(normalizePointsFromResponse(resp));
}

// Separa artículos vs chunks
const articlePoints = allPoints.filter((p) => p.kind === 'article');
const chunkPoints = allPoints.filter((p) => p.kind === 'chunk');

// Lógicas por intent
function latestBySite() {
  const per = perSite || 5;
  const groups = {};
  for (const p of articlePoints) {
    const site = String(p.payload?.site || '').trim();
    if (!site) continue;
    if (!inDateRange(p.timestamp, filters)) continue;
    if (!groups[site]) groups[site] = [];
    groups[site].push(p);
  }
  const out = {};
  for (const [site, arr] of Object.entries(groups)) {
    arr.sort(byTsDesc);
    const fields = ['title', 'url', 'site', 'author', 'published_at'];
    out[site] = arr.slice(0, per).map((h) => serializeResult(h, fields));
  }
  return { intent: 'latest_by_site', groups: out };
}

function hitsArticles(limit) {
  const fields = ['title', 'url', 'site', 'author', 'published_at'];
  const selected = articlePoints
    .filter((h) => inDateRange(h.timestamp, filters))
    .sort(byCombinedThenTsDesc)
    .slice(0, limit || DEFAULT_ARTICLE_TOPK)
    .map((h) => serializeResult(h, fields));
  return { intent: 'search_articles', hits: selected };
}

function hitsChunks(limit) {
  const fields = ['url', 'content', 'site', 'author', 'published_at'];
  let selected = chunkPoints.filter((h) => inDateRange(h.timestamp, filters));
  if (exactPhrase && queryText) {
    const needle = queryText.toLowerCase();
    selected = selected.filter((h) => String(h.payload?.content || '').toLowerCase().includes(needle));
  }
  selected = selected.sort(byCombinedThenTsDesc).slice(0, limit || DEFAULT_CHUNK_TOPK).map((h) => serializeResult(h, fields));
  return { intent: 'search_chunks', hits: selected };
}

function filterOnlyArticles(limit) {
  const fields = ['title', 'url', 'site', 'author', 'published_at'];
  const selected = articlePoints
    .filter((h) => inDateRange(h.timestamp, filters))
    .sort(byTsDesc)
    .slice(0, limit || DEFAULT_ARTICLE_TOPK)
    .map((h) => serializeResult(h, fields));
  return { intent: 'filter_only_articles', hits: selected };
}

function filterOnlyChunks(limit) {
  const fields = ['url', 'content', 'site', 'author', 'published_at'];
  const selected = chunkPoints
    .filter((h) => inDateRange(h.timestamp, filters))
    .sort(byTsDesc)
    .slice(0, limit || DEFAULT_CHUNK_TOPK)
    .map((h) => serializeResult(h, fields));
  return { intent: 'filter_only_chunks', hits: selected };
}

function buildContextFromChunks(limitArticles) {
  // Agrupa chunks por artículo y selecciona hasta 3 por artículo
  const perArticle = 3;
  const maxArticles = Math.max(limitArticles || DEFAULT_ARTICLE_TOPK, 5);
  const groups = new Map();
  for (const h of chunkPoints) {
    if (!inDateRange(h.timestamp, filters)) continue;
    const articleId = String(h.payload?.article_id || h.payload?.doc_id || h.payload?.url || '').trim();
    if (!articleId) continue;
    if (!groups.has(articleId)) groups.set(articleId, []);
    groups.get(articleId).push(h);
  }
  // Ranking por combined score, luego ts
  const articlesRanked = [];
  for (const [articleId, arr] of groups.entries()) {
    arr.sort(byCombinedThenTsDesc);
    const topChunks = arr.slice(0, perArticle);
    const meta = topChunks[0]?.payload || {};
    const article = {
      id: articleId,
      site: meta.site,
      url: meta.url,
      title: meta.article_title || meta.title,
      description: meta.article_description || meta.description,
      author: meta.author,
      published_at: meta.published_at,
      chunks: topChunks.map((c) => ({
        chunk_ix: c.payload?.chunk_ix,
        score: Number.isFinite(c.vector_score) ? Number(c.vector_score) : undefined,
        recency: Number.isFinite(c.recency_weight) ? Number(c.recency_weight) : undefined,
        snippet: makeSnippet(c.payload?.content || ''),
      })),
    };
    articlesRanked.push({
      key: articleId,
      score: topChunks[0]?.combined_score || 0,
      ts: topChunks[0]?.timestamp || 0,
      entry: article,
    });
  }
  articlesRanked.sort((a, b) => (b.ts - a.ts) || (b.score - a.score));
  const articles = articlesRanked.slice(0, maxArticles).map((x) => x.entry);
  // Stats aproximadas
  let totalChunks = 0;
  let totalTokens = 0;
  for (const a of articles) {
    totalChunks += (a.chunks || []).length;
    for (const ch of a.chunks || []) {
      const len = (ch.snippet || '').length;
      const approxTokens = Math.max(Math.floor(len / 4), 1);
      totalTokens += approxTokens;
    }
  }
  if (!articles.length) return null;
  return {
    total_chunks: totalChunks,
    total_tokens: totalTokens,
    unique_sites: Array.from(new Set(articles.map((a) => a.site).filter(Boolean))).sort(),
    articles,
  };
}

function compareViewpoints(limit) {
  // Agrupa artículos por site (sea search o scroll)
  const fields = ['title', 'url', 'site', 'author', 'published_at'];
  const grouped = {};
  const selected = articlePoints.filter((h) => inDateRange(h.timestamp, filters));
  selected.sort(byCombinedThenTsDesc);
  const perGroup = limit || DEFAULT_ARTICLE_TOPK;
  for (const h of selected) {
    const site = String(h.payload?.site || '').trim();
    if (!site) continue;
    if (!grouped[site]) grouped[site] = [];
    if (grouped[site].length < perGroup) grouped[site].push(serializeResult(h, fields));
  }
  const context = buildContextFromChunks(perGroup);
  return { intent: 'compare_viewpoints', data: grouped, context: context || undefined };
}

function backgrounderLike(limit) {
  // Devuelve artículos + contexto de chunks si los hay
  const articles = hitsArticles(limit).hits;
  const context = buildContextFromChunks(limit);
  return { intent, data: articles, context: context || undefined };
}

let output;
switch (intent) {
  case 'latest_by_site':
    output = latestBySite();
    break;
  case 'filter_only_articles':
    output = filterOnlyArticles(topK || DEFAULT_ARTICLE_TOPK);
    break;
  case 'filter_only_chunks':
    output = filterOnlyChunks(topK || DEFAULT_CHUNK_TOPK);
    break;
  case 'search_articles':
    output = hitsArticles(topK || DEFAULT_ARTICLE_TOPK);
    break;
  case 'search_chunks':
    output = hitsChunks(topK || DEFAULT_CHUNK_TOPK);
    break;
  case 'summarize':
    output = backgrounderLike(topK || DEFAULT_ARTICLE_TOPK);
    break;
  case 'backgrounder':
    output = backgrounderLike(topK || DEFAULT_BACKGROUND_TOPK);
    break;
  case 'compare_viewpoints':
    output = compareViewpoints(topK || DEFAULT_ARTICLE_TOPK);
    break;
  default:
    output = { intent, hits: [] };
}

return [output];

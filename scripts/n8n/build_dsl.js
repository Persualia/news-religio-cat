const EXACT_FIELDS = {
  site: "site.keyword",
  author: "author.keyword",
  lang: "lang.keyword"
};

function resolveField(field) {
  return EXACT_FIELDS[field] || field;
}

function termFilter(field, values) {
  if (Array.isArray(values) && values.length) {
    return { terms: { [resolveField(field)]: values } };
  }
  return null;
}

function rangeFilter(field, gte, lte) {
  const range = {};
  if (gte) range.gte = gte;
  if (lte) range.lte = lte;
  return Object.keys(range).length ? { range: { [field]: range } } : null;
}

function makeFilters(filters) {
  const must = [];
  if (!filters) return must;
  for (const clause of [
    termFilter("site", filters.site),
    termFilter("lang", filters.lang),
    termFilter("author", filters.author),
    rangeFilter("published_at", filters.date_from, filters.date_to)
  ]) {
    if (clause) must.push(clause);
  }
  return must;
}

function lexicalQueryArticles(plan, queryText, mustFilters) {
  const should = [];
  if (plan.phrase) {
    should.push({ match_phrase: { title: queryText } });
    should.push({ match_phrase: { description: queryText } });
  }
  if (plan.keywords || (!plan.phrase && queryText)) {
    should.push({
      multi_match: {
        query: queryText,
        fields: ["search_text_short^3", "title^4", "description^2", "content"],
        type: "best_fields",
        operator: "and"
      }
    });
  }
  return {
    bool: {
      must: mustFilters,
      should,
      minimum_should_match: should.length ? 1 : 0
    }
  };
}

function lexicalQueryChunks(plan, queryText, mustFilters) {
  const should = [];
  if (plan.phrase) {
    should.push({ match_phrase: { content: queryText } });
  }
  if (plan.keywords || (!plan.phrase && queryText)) {
    should.push({
      multi_match: {
        query: queryText,
        fields: ["content"],
        type: "best_fields",
        operator: "and"
      }
    });
  }
  return {
    bool: {
      must: mustFilters,
      should,
      minimum_should_match: should.length ? 1 : 0
    }
  };
}

function joinUrl(base, path) {
  const trimmedBase = base ? base.replace(/\/+$/, "") : "";
  const trimmedPath = path.replace(/^\/+/, "");
  return trimmedBase ? `${trimmedBase}/${trimmedPath}` : `/${trimmedPath}`;
}

const input = items[0].json;
const plan = input.plan;
const fields = Array.isArray(input.fields) && input.fields.length ? input.fields : undefined;
const topK = input.topK || plan.topK || 5;
const filtersBool = makeFilters(plan.filters);
const sortBy = plan.sort?.by || "published_at";
const sortOrder = plan.sort?.order || "desc";
const bonsai = (input.bonsai && typeof input.bonsai === "object") ? input.bonsai : {};
const baseUrlCandidate = typeof input.baseUrl === "string" ? input.baseUrl : bonsai.baseUrl;
const baseUrl = typeof baseUrlCandidate === "string" ? baseUrlCandidate : "";
const indexArticles = input.indexArticles || "articles-live";
const indexChunks = input.indexChunks || "chunks-live";
const queryText = input.query_text || "";

let url = "";
let body = {};
let target = plan.return?.index === "chunks" ? "chunks" : "articles";

if (plan.intent === "latest_by_site") {
  const topHits = {
    size: plan.topK || 5,
    sort: [{ [sortBy]: { order: sortOrder, unmapped_type: "date" } }]
  };
  if (fields) topHits._source = fields;
  body = {
    size: 0,
    query: { bool: { must: filtersBool } },
    aggs: {
      by_site: {
        terms: { field: resolveField("site"), size: 50 },
        aggs: { latest: { top_hits: topHits } }
      }
    }
  };
  url = joinUrl(baseUrl, `${indexArticles}/_search`);
  target = "aggs";
} else if (plan.intent === "search_articles") {
  if (plan.mode === "lexical") {
    body = {
      size: topK,
      query: lexicalQueryArticles(plan, queryText, filtersBool),
      sort: [{ [sortBy]: { order: sortOrder, unmapped_type: "date" } }]
    };
    if (fields) body._source = fields;
    url = joinUrl(baseUrl, `${indexArticles}/_search`);
    target = "articles_lexical";
  } else {
    if (!Array.isArray(input.embedding) || !input.embedding.length) {
      throw new Error("Falta 'embedding' para búsqueda semántica (search_articles hybrid).");
    }
    const k = Math.max(5 * topK, 200);
    const numCandidates = Math.max(10 * topK, 500);
    body = {
      size: k,
      _source: ["url", "site", "author", "published_at", "chunk_ix"],
      query: {
        knn: {
          field: "content_vec",
          query_vector: input.embedding,
          k,
          num_candidates: numCandidates,
          filter: { bool: { must: filtersBool } }
        }
      },
      sort: [{ [sortBy]: { order: sortOrder, unmapped_type: "date" } }]
    };
    url = joinUrl(baseUrl, `${indexChunks}/_search`);
    target = "articles_from_chunks";
  }
} else if (plan.intent === "search_chunks") {
  if (plan.mode === "lexical") {
    body = {
      size: topK,
      query: lexicalQueryChunks(plan, queryText, filtersBool),
      sort: [{ [sortBy]: { order: sortOrder, unmapped_type: "date" } }]
    };
    if (fields) body._source = fields;
    url = joinUrl(baseUrl, `${indexChunks}/_search`);
    target = "chunks_lexical";
  } else {
    if (!Array.isArray(input.embedding) || !input.embedding.length) {
      throw new Error("Falta 'embedding' para búsqueda semántica (search_chunks hybrid).");
    }
    const k = Math.max(5 * topK, 200);
    const numCandidates = Math.max(10 * topK, 500);
    body = {
      size: topK,
      _source: fields || ["url", "content", "chunk_ix", "published_at", "site", "lang", "author"],
      query: {
        knn: {
          field: "content_vec",
          query_vector: input.embedding,
          k,
          num_candidates: numCandidates,
          filter: { bool: { must: filtersBool } }
        }
      },
      sort: [{ [sortBy]: { order: sortOrder, unmapped_type: "date" } }]
    };
    url = joinUrl(baseUrl, `${indexChunks}/_search`);
    target = "chunks_knn";
  }
} else if (plan.intent === "summarize") {
  body = { size: 0, query: { match_none: {} } };
  url = joinUrl(baseUrl, `${indexArticles}/_search`);
  target = "noop";
} else {
  throw new Error(`Intent no soportado: ${plan.intent}`);
}

return [{ json: { url, body, intent: plan.intent, target } }];

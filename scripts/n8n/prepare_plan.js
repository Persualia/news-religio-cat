function clampInt(n, min, max, def) {
  n = Number.isInteger(n) ? n : def;
  return Math.max(min, Math.min(max, n));
}

function toStringSafe(value) {
  return (value ?? "").toString().trim();
}

function stripQuotes(input) {
  return toStringSafe(input).replace(/[“”«»"']/g, "").trim();
}

const src = items[0]?.json?.output || {};
const plan = JSON.parse(JSON.stringify(src));

plan.topK = clampInt(plan.topK, 1, 50, 5);
plan.mode = plan.mode || (plan.semantic ? "hybrid" : "lexical");
plan.semantic = plan.mode === "hybrid";

let queryText = "";
if (toStringSafe(plan.phrase)) {
  queryText = stripQuotes(plan.phrase);
} else if (toStringSafe(plan.keywords)) {
  queryText = toStringSafe(plan.keywords);
} else {
  queryText = "notícies rellevants";
}

if (!plan.return) plan.return = {};
if (!plan.return.index) {
  plan.return.index = plan.intent === "search_chunks" ? "chunks" : "articles";
}
if (!Array.isArray(plan.return.fields) || !plan.return.fields.length) {
  plan.return.fields = plan.return.index === "chunks"
    ? ["url", "content", "chunk_ix", "published_at", "site", "lang", "author"]
    : ["title", "url", "published_at", "site", "author", "description"];
}

plan.filters = plan.filters || {};
for (const key of ["site", "lang", "author"]) {
  if (Array.isArray(plan.filters[key]) && !plan.filters[key].length) {
    delete plan.filters[key];
  }
}

plan.sort = plan.sort || { by: "published_at", order: "desc" };

const semantic = !!plan.semantic;

return [{
  json: {
    plan,
    query_text: queryText,
    fields: plan.return.fields,
    topK: plan.topK,
    semantic,
    mode: plan.mode
  }
}];

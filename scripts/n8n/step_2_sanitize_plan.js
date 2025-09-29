// Replica sanitize_filters, clean_filter_list y drop_empty_filters
function cleanList(values) {
  if (!values) return [];
  const out = [];
  for (const v of values) {
    if (v === null || v === undefined) continue;
    const s = String(v).trim();
    if (s) out.push(s);
  }
  return out;
}
function sanitizeFilters(raw) {
  raw = raw || {};
  return {
    site: cleanList(raw.site),
    base_url: cleanList(raw.base_url),
    url: cleanList(raw.url),
    lang: cleanList(raw.lang),
    author: cleanList(raw.author),
    article_id: cleanList(raw.article_id),
    date_from: (raw.date_from || '').trim(),
    date_to: (raw.date_to || '').trim(),
  };
}
function dropEmpty(f) {
  const o = {};
  for (const [k,v] of Object.entries(f)) {
    if (Array.isArray(v) && v.length===0) continue;
    if (typeof v==='string' && v==='') continue;
    o[k]=v;
  }
  return o;
}
const plan = $input.first().json.plan || {}; // viene del paso anterior
const filters = dropEmpty(sanitizeFilters(plan.filters||{}));
const topK = Number(plan.topK||0);
const per_site = Number(plan.per_site||0);
const intent = String(plan.intent||'');
const queryText = String(plan.query||'').trim();

return [{ intent, queryText, filters, topK, per_site }];

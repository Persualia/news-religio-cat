// Equivalente a _build_filter y _parse_datetime/_date_bounds
function fieldMatchAny(key, values) {
  return { key, match: { any: values } };
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

const f = $json.filters || {};
const must = [];
if (Array.isArray(f.site) && f.site.length) must.push(fieldMatchAny('site', f.site));
if (Array.isArray(f.base_url) && f.base_url.length) must.push(fieldMatchAny('base_url', f.base_url));
if (Array.isArray(f.lang) && f.lang.length) must.push(fieldMatchAny('lang', f.lang));
if (Array.isArray(f.author) && f.author.length) must.push(fieldMatchAny('author', f.author));
if (Array.isArray(f.url) && f.url.length) must.push(fieldMatchAny('url', f.url));
if (Array.isArray(f.article_id) && f.article_id.length) must.push(fieldMatchAny('article_id', f.article_id));

const df = parseDate(f.date_from, false);
const dt = parseDate(f.date_to, true);
if (df || dt) {
  const range = {};
  if (df) range.gte = df;
  if (dt) range.lte = dt;
  must.push({ should: [
    { key: 'published_at_ts', range },
    { key: 'indexed_at_ts', range },
  ] });
}

const qFilter = must.length ? { must } : undefined;
return [{ ...$json, qFilter }];

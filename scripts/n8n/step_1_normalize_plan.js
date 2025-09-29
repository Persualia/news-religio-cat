// NODO CODE: parsea la Responses API y construye "plan"
const out = {};
const plan = $input.first().json.query; // lo que viene en el paso anterior

function fallback(v, def) {
  return (v === undefined || v === null || (typeof v === 'string' && !v.trim())) ? def : v;
}

// Normaliza mínimos como en tu script
plan.intent       = String(plan.intent || '');
plan.query        = fallback(plan.query, '');
plan.exact_phrase = Boolean(plan.exact_phrase);
plan.topK         = Number.isInteger(plan.topK) ? plan.topK : 0;
plan.per_site     = Number.isInteger(plan.per_site) ? plan.per_site : 0;
plan.filters      = plan.filters && typeof plan.filters==='object' ? plan.filters : {
  site:[], base_url:[], url:[], lang:[], author:[], article_id:[], date_from:'', date_to:''
};
return [{ plan }];

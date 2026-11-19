// Readable copy of the code inside the "Detect tools and score" node of
// tech-footprint-weekly.json. Same logic as footprint/detect.py + signals.py
// (homepage, headers, DNS TXT/SPF/MX, gaps). Edit here, then paste into n8n.

const pack = $('Load stack pack').first().json;
const accounts = $('Accounts').all();
const pages = $('Fetch homepage').all();
const txts = $('DNS TXT').all();
const mxs = $('DNS MX').all();
const observedAt = new Date().toISOString();

const HOSTLIKE = /^[a-z0-9.-]+\.[a-z]{2,}(\/.*)?$/;
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const toRegex = (p) =>
  p.startsWith('re:') ? new RegExp(p.slice(3), 'i')
  : HOSTLIKE.test(p) ? new RegExp('(?<![a-z0-9-])' + esc(p))
  : new RegExp(esc(p));
const cache = {};
const match = (p, text) => (cache[p] ||= toRegex(p)).test(text);
const isOwn = (p, own) => HOSTLIKE.test(p) && (p.split('/')[0] === own || p.split('/')[0].endsWith('.' + own));

const roleOf = (id) =>
  (pack.seller.competitors || []).includes(id) ? 'competitor'
  : (pack.seller.complements || []).includes(id) ? 'complement' : 'neutral';

const dnsData = (item) => ((item && item.json && item.json.Answer) || [])
  .map((a) => String(a.data || '').replace(/" "/g, '').replace(/^"|"$/g, '').toLowerCase());

const out = [];
accounts.forEach((acc, i) => {
  const domain = acc.json.domain.toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0];
  const page = pages[i] ? pages[i].json : {};
  const fetched = !page.error && typeof page.body === 'string' && (page.statusCode || 200) < 400;
  const html = fetched ? page.body.toLowerCase() : '';
  const headers = {};
  Object.entries(page.headers || {}).forEach(([k, v]) => { headers[k.toLowerCase()] = String(v).toLowerCase(); });
  const txt = dnsData(txts[i]);
  const spf = txt.filter((t) => t.startsWith('v=spf1'));
  const otherTxt = txt.filter((t) => !t.startsWith('v=spf1'));
  const mx = dnsData(mxs[i]).map((m) => m.split(' ').pop().replace(/\.$/, ''));

  const row = (extra) => ({
    account_domain: domain, signal_type: '', signal_value: '', tool_name: '', category: '', role: '',
    weight: 0, play: '', source: '', evidence: '', evidence_url: fetched ? `https://${domain}` : '',
    pack: pack.pack, observed_at: observedAt, ...extra,
  });

  const found = {};
  for (const tool of Object.values(pack.tools)) {
    const p = tool.patterns || {};
    let ev = null;
    for (const s of p.html || []) if (!ev && !isOwn(s, domain) && match(s, html)) ev = ['homepage', s];
    for (const [h, needle] of Object.entries(p.headers || {}))
      if (!ev && h in headers && (needle === '' || headers[h].includes(needle))) ev = ['headers', `${h}: ${needle || '(present)'}`];
    for (const s of p.dns_txt || []) if (!ev && otherTxt.some((r) => match(s, r))) ev = ['dns_txt', s];
    for (const s of p.spf || []) if (!ev && spf.some((r) => match(s, r))) ev = ['spf', s];
    for (const s of p.mx || []) if (!ev && mx.some((r) => match(s, r))) ev = ['dns_mx', s];
    if (!ev) continue;
    found[tool.id] = tool;
    const role = roleOf(tool.id);
    const key = role === 'competitor' ? 'competitor_found' : role === 'complement' ? 'complement_found' : null;
    out.push(row({
      signal_type: 'tech_detected', signal_value: tool.id, tool_name: tool.name, category: tool.category,
      role, weight: key ? pack.weights[key] || 0 : 0, play: key ? pack.plays[key] || '' : '',
      source: ev[0], evidence: ev[1],
    }));
  }

  if (fetched) {
    const cats = new Set(Object.values(found).map((t) => t.category));
    for (const cat of pack.seller.must_have_categories || []) {
      if (!cats.has(cat)) out.push(row({
        signal_type: 'gap', signal_value: cat, category: cat, role: 'gap',
        weight: pack.weights.gap_found || 0, play: pack.plays.gap_found || '',
        source: 'homepage', evidence: `no ${cat} tool detected`,
      }));
    }
  } else {
    out.push(row({ signal_type: 'fetch_error', evidence: String(page.error?.message || page.error || 'no response').slice(0, 300) }));
  }
});

return out.map((json) => ({ json }));

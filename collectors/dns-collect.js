// DNS collector for abm-tech-footprint (companion to browser-collect.js).
//
//   1. Open https://dns.google in Chrome, then DevTools > Console.
//   2. Edit the `domains` list, paste this file, press Enter.
//   3. Merge the printed JSON (keyed by domain) into raw.json, or save it as
//      dns.json and pass both:  --from-raw raw.json --dns-raw dns.json
//
// Looks up TXT (SPF + verification tokens), MX, DMARC, MTA-STS and BIMI
// records through Google Public DNS. Runs on dns.google so there is no CORS issue.
(async () => {
  const domains = ['example.com'];   // <- your domains, no www
  const q = async (name, type) => {
    const j = await fetch(`/resolve?name=${encodeURIComponent(name)}&type=${type}`).then((r) => r.json());
    const code = { TXT: 16, MX: 15 }[type];
    return (j.Answer || []).filter((a) => a.type === code).map((a) =>
      type === 'MX' ? a.data.split(' ').pop().replace(/\.$/, '') : a.data.replace(/" "/g, '').replace(/^"|"$/g, ''));
  };
  const out = {};
  for (const d of domains) {
    const [txt, mx, dmarc, mta_sts, bimi] = await Promise.all([
      q(d, 'TXT'), q(d, 'MX'), q(`_dmarc.${d}`, 'TXT'), q(`_mta-sts.${d}`, 'TXT'), q(`default._bimi.${d}`, 'TXT'),
    ]);
    out[d] = { txt, mx, dmarc, mta_sts, bimi };
  }
  console.log(JSON.stringify(out));
  return JSON.stringify(out);
})();

// Browser collector for abm-tech-footprint.
//
// Use when a site blocks scripts (bot protection) or your network can't reach it:
//   1. Open the company's homepage in Chrome and accept/close nothing special.
//   2. Open DevTools > Console, paste this whole file, press Enter.
//   3. Copy the printed JSON object into a file such as raw.json (a JSON array of
//      these objects, one per company).
//   4. Add DNS with collectors/dns-collect.js (run on https://dns.google), then:
//        python -m footprint scan --pack security-compliance --from-raw raw.json
//
// It reads only what the browser already loaded: same-origin response headers,
// the URLs of loaded resources, a few HTML markers and compliance keywords.
// It sends nothing anywhere.
(async () => {
  const own = location.hostname.replace(/^www\./, '');
  const res = await fetch(location.href, { cache: 'no-store', credentials: 'omit' });
  const headers = Object.fromEntries([...res.headers]);
  const html = await res.text();
  const dom = document.documentElement.outerHTML;

  // every third-party URL the page loaded or links to (host + path, no query)
  const urls = new Set();
  const add = (u) => {
    try {
      const x = new URL(u, location.href);
      if (!x.protocol.startsWith('http')) return;
      const host = x.hostname.replace(/^www\./, '');
      const isOwn = host === own || host.endsWith('.' + own);
      const path = x.pathname.slice(0, 80);
      if (!isOwn) urls.add(host + path);
      else if (/^(trust|security|status|app|docs)\./.test(x.hostname)) urls.add(x.hostname + path);
      else if (/\/(wp-content|wp-includes|sites\/default\/files)\//.test(path)) urls.add(host + path);
      else if (/\/(trust|trust-center|security)\/?$/.test(path)) urls.add(host + path);
    } catch (e) { /* ignore */ }
  };
  performance.getEntriesByType('resource').forEach((e) => add(e.name));
  document.querySelectorAll('[src],[href],[action]').forEach((el) =>
    add(el.getAttribute('src') || el.getAttribute('href') || el.getAttribute('action')));

  // HTML markers that are not URLs
  const markers = ['data-wf-site', 'drupal-settings-json', 'optanon', 'mktoforms2', 'fbq(\'init\'', '__next_data__', 'framerusercontent.com']
    .filter((m) => (html + dom).toLowerCase().includes(m.toLowerCase()));

  // compliance language on the page
  const text = document.body ? document.body.innerText.toLowerCase() : '';
  const phrases = ['soc 2', 'soc2', 'iso 27001', 'iso/iec 27001', 'iso 42001', 'hipaa', 'gdpr', 'fedramp', 'pci dss', 'trust center', 'penetration test', 'bug bounty']
    .filter((p) => text.includes(p));

  // security.txt (RFC 9116)
  let securityTxt = false;
  try {
    const r = await fetch('/.well-known/security.txt', { cache: 'no-store', credentials: 'omit' });
    const body = r.ok ? (await r.text()).slice(0, 500).toLowerCase() : '';
    securityTxt = r.ok && body.includes('contact:') && !body.includes('<html');
  } catch (e) { /* ignore */ }

  const out = {
    domain: own,
    url: location.href,
    title: document.title,
    status: res.status,
    headers,
    html: [...urls].sort().join('\n') + '\n' + markers.join('\n') + '\n' + phrases.join('\n'),
    security_txt: securityTxt,
  };
  console.log(JSON.stringify(out));
  return JSON.stringify(out);
})();

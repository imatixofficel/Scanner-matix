/**
 * Matix Worker — companion backend for the Matix IP Scanner.
 *
 * Deploy this on Cloudflare Workers (free tier is enough) and it gives the
 * Matix frontend two things a static GitHub Pages site cannot do on its own:
 *
 *   GET  /ranges   -> the official Cloudflare IPv4 ranges, fetched server-side
 *                     (no browser CORS restriction applies here) and returned
 *                     with permissive CORS headers.
 *
 *   POST /scan     -> body: { "ips": ["1.2.3.4", ...] }
 *                     Measures a REAL round-trip time to each IP by making an
 *                     HTTPS request to Cloudflare's own trace endpoint while
 *                     forcing the connection to that specific IP address
 *                     (via the `cf.resolveOverride` option). This is a real,
 *                     measured value — never a random or fabricated number.
 *                     Note: because the Worker itself runs on Cloudflare's
 *                     network, these numbers reflect edge-to-edge routing,
 *                     not a home user's last-mile latency. That's still real
 *                     data — just say so if you present it to end users.
 *
 * No secrets or API keys are needed for either endpoint.
 *
 * DEPLOY (no coding, just copy/paste):
 *   1. Go to https://dash.cloudflare.com -> Workers & Pages -> Create ->
 *      "Create Worker".
 *   2. Give it a name (e.g. "matix-worker") and click "Deploy" to scaffold it.
 *   3. Click "Edit code", delete the placeholder code, paste this whole file
 *      in, then click "Deploy" again.
 *   4. Copy the Worker's URL (looks like https://matix-worker.YOURNAME.workers.dev).
 *   5. In app.js, set:
 *        var RANGES_API_URL = 'https://matix-worker.YOURNAME.workers.dev/ranges';
 *        var SCAN_API_URL    = 'https://matix-worker.YOURNAME.workers.dev/scan';
 *      Re-upload app.js to your GitHub repo.
 */

const CLOUDFLARE_IPV4_SOURCE = 'https://www.cloudflare.com/ips-v4';
const TRACE_URL = 'https://cloudflare.com/cdn-cgi/trace';

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

function jsonResponse(data, status) {
  return new Response(JSON.stringify(data), {
    status: status || 200,
    headers: Object.assign({ 'Content-Type': 'application/json' }, CORS_HEADERS),
  });
}

async function handleRanges() {
  try {
    const res = await fetch(CLOUDFLARE_IPV4_SOURCE, { cf: { cacheTtl: 300 } });
    if (!res.ok) throw new Error('Cloudflare responded with ' + res.status);
    const text = await res.text();
    const ranges = text
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\/\d{1,2}$/.test(l));
    if (!ranges.length) throw new Error('Empty range list from Cloudflare');
    return jsonResponse({ ranges: ranges });
  } catch (err) {
    return jsonResponse({ error: 'Could not fetch official Cloudflare ranges: ' + err.message }, 502);
  }
}

async function measureOne(ip) {
  const started = Date.now();
  try {
    const res = await fetch(TRACE_URL, {
      cf: { resolveOverride: ip },
      signal: AbortSignal.timeout(5000),
    });
    const ms = Date.now() - started;
    if (!res.ok) return { ip: ip, ms: null, status: 'offline' };
    return { ip: ip, ms: ms, status: 'online' };
  } catch (err) {
    return { ip: ip, ms: null, status: 'offline' };
  }
}

async function handleScan(request) {
  let body;
  try {
    body = await request.json();
  } catch (err) {
    return jsonResponse({ error: 'Invalid JSON body' }, 400);
  }
  const ips = Array.isArray(body && body.ips) ? body.ips.slice(0, 200) : [];
  if (!ips.length) return jsonResponse({ error: 'No IPs provided' }, 400);

  // Measure with limited concurrency so we don't open hundreds of sockets at once.
  const concurrency = 15;
  const results = [];
  let index = 0;

  async function worker() {
    while (index < ips.length) {
      const current = ips[index++];
      results.push(await measureOne(current));
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, ips.length) }, worker));

  return jsonResponse({ results: results });
}

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS });
    }
    if (url.pathname === '/ranges' && request.method === 'GET') {
      return handleRanges();
    }
    if (url.pathname === '/scan' && request.method === 'POST') {
      return handleScan(request);
    }
    return jsonResponse({ error: 'Not found. Use GET /ranges or POST /scan.' }, 404);
  },
};

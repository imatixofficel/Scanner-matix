/* =========================================================================
   Matix — app.js
   Vanilla JS, no build step, no framework, no dependencies.
   ========================================================================= */
(function () {
  'use strict';

  /* -----------------------------------------------------------------------
     CONFIG
     Set SCAN_API_URL to a real backend / Cloudflare Worker endpoint that
     performs actual latency measurement against a list of IPs and returns
     JSON: { "results": [ { "ip": "1.2.3.4", "ms": 42, "status": "online" } ] }
     GitHub Pages alone cannot perform real TCP/ICMP pings — this project
     never fabricates that data. See README.md for the expected contract.
     ------------------------------------------------------------------- */
  var SCAN_API_URL = 'https://scanner.imatixofficel.workers.dev/scan';

  /* Optional: URL of the /ranges endpoint from the companion worker.js
     (see that file for one-click deploy instructions). If set, this is used
     instead of fetching www.cloudflare.com/ips-v4 directly from the browser,
     which avoids CORS issues entirely. Example:
       'https://matix-worker.YOURNAME.workers.dev/ranges' */
  var RANGES_API_URL = 'https://scanner.imatixofficel.workers.dev/renges';

  var CLOUDFLARE_IPV4_SOURCE = 'https://www.cloudflare.com/ips-v4';

  /* -----------------------------------------------------------------------
     Small helpers
     ------------------------------------------------------------------- */
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $all(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

  var toastEl = $('#toast');
  var toastTimer = null;
  function showToast(message, kind) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.className = 'toast is-visible' + (kind ? ' is-' + kind : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastEl.className = 'toast';
    }, 2600);
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* noop */ }
    document.body.removeChild(ta);
    return Promise.resolve();
  }

  /* -----------------------------------------------------------------------
     Loading screen
     ------------------------------------------------------------------- */
  window.addEventListener('load', function () {
    setTimeout(function () {
      var screen = $('#loading-screen');
      if (!screen) return;
      screen.classList.add('is-hidden');
      setTimeout(function () { screen.remove(); }, 650);
    }, 1300);
  });

  /* -----------------------------------------------------------------------
     Hamburger drawer
     ------------------------------------------------------------------- */
  var hamburgerBtn = $('#hamburger-btn');
  var drawer = $('#drawer');
  var drawerOverlay = $('#drawer-overlay');

  function openDrawer() {
    drawer.classList.add('is-open');
    drawer.setAttribute('aria-hidden', 'false');
    drawerOverlay.classList.add('is-visible');
    hamburgerBtn.setAttribute('aria-expanded', 'true');
  }
  function closeDrawer() {
    drawer.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
    drawerOverlay.classList.remove('is-visible');
    hamburgerBtn.setAttribute('aria-expanded', 'false');
  }
  hamburgerBtn.addEventListener('click', function () {
    if (drawer.classList.contains('is-open')) closeDrawer(); else openDrawer();
  });
  drawerOverlay.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeDrawer();
  });

  /* Page navigation */
  var drawerLinks = $all('.drawer-link');
  var pages = $all('.page');
  drawerLinks.forEach(function (link) {
    link.addEventListener('click', function () {
      var target = link.getAttribute('data-target');
      pages.forEach(function (p) { p.classList.toggle('is-active', p.id === target); });
      drawerLinks.forEach(function (l) { l.classList.toggle('is-active', l === link); });
      closeDrawer();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });

  /* =========================================================================
     IP SCANNER
     ========================================================================= */
  var startScanBtn = $('#start-scan-btn');
  var ipCountSelect = $('#ip-count');
  var progressWrap = $('#scan-progress-wrap');
  var progressFill = $('#scan-progress-fill');
  var progressLabel = $('#scan-progress-label');
  var progressCount = $('#scan-progress-count');
  var statusMsg = $('#scan-status-msg');
  var resultsWrap = $('#results-wrap');
  var resultsBody = $('#results-body');
  var resultsSummary = $('#results-summary');
  var copyBestBtn = $('#copy-best-btn');
  var copyAllBtn = $('#copy-all-btn');

  var cachedRanges = null; // real Cloudflare IPv4 CIDR ranges, fetched once
  var lastResults = [];    // last rendered scan results, sorted by ping

  function setStatus(message, kind) {
    if (!message) {
      statusMsg.hidden = true;
      statusMsg.textContent = '';
      return;
    }
    statusMsg.hidden = false;
    statusMsg.className = 'status-msg' + (kind ? ' is-' + kind : '');
    statusMsg.textContent = message;
  }

  function setProgress(percent, label, doneCount, totalCount) {
    progressWrap.hidden = false;
    progressFill.style.width = Math.max(0, Math.min(100, percent)) + '%';
    if (label) progressLabel.textContent = label;
    progressCount.textContent = doneCount + ' / ' + totalCount;
  }

  /* --- IPv4 / CIDR helpers --- */
  function ipToInt(ip) {
    var parts = ip.split('.').map(Number);
    return ((parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]) >>> 0;
  }
  function intToIp(int) {
    return [(int >>> 24) & 255, (int >>> 16) & 255, (int >>> 8) & 255, int & 255].join('.');
  }
  function randomIpFromCidr(cidr) {
    var parts = cidr.split('/');
    var base = ipToInt(parts[0]);
    var prefix = parseInt(parts[1], 10);
    var hostBits = 32 - prefix;
    var size = Math.pow(2, hostBits);
    var network = (base & (~(size - 1) >>> 0)) >>> 0;
    if (size <= 2) return intToIp(network);
    var offset = 1 + Math.floor(Math.random() * (size - 2));
    return intToIp((network + offset) >>> 0);
  }

  /* Fetch the official Cloudflare IPv4 ranges. No fabricated ranges — if the
     network request fails (offline, or blocked by CORS from a raw static
     host), we surface that honestly instead of inventing a fallback list. */
  function fetchCloudflareRanges() {
    if (cachedRanges) return Promise.resolve(cachedRanges);

    if (RANGES_API_URL) {
      // Preferred path: a small backend (see worker.js) fetches the ranges
      // server-side and returns them with permissive CORS headers.
      return fetch(RANGES_API_URL, { cache: 'no-store' })
        .then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.json();
        })
        .then(function (data) {
          var ranges = (data && data.ranges) || [];
          if (!ranges.length) throw new Error('empty range list from RANGES_API_URL');
          cachedRanges = ranges;
          return ranges;
        });
    }

    // Fallback: try fetching Cloudflare's published list directly from the
    // browser. This works in some environments and fails with a CORS error
    // in others — either way, no fake ranges are ever substituted.
    return fetch(CLOUDFLARE_IPV4_SOURCE, { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.text();
      })
      .then(function (text) {
        var ranges = text.split('\n').map(function (l) { return l.trim(); }).filter(function (l) {
          return /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\/\d{1,2}$/.test(l);
        });
        if (!ranges.length) throw new Error('empty range list');
        cachedRanges = ranges;
        return ranges;
      });
  }

  function pickRandomIps(ranges, count) {
    var picked = new Set();
    var attempts = 0;
    var maxAttempts = count * 20;
    while (picked.size < count && attempts < maxAttempts) {
      var cidr = ranges[Math.floor(Math.random() * ranges.length)];
      picked.add(randomIpFromCidr(cidr));
      attempts++;
    }
    return Array.from(picked);
  }

  /* Call the real measurement API. Never invent ping/status values locally. */
  function measureViaApi(ips) {
    return fetch(SCAN_API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ips: ips })
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (data) {
      var list = Array.isArray(data) ? data : (data && data.results) || [];
      return list.map(function (item) {
        return {
          ip: item.ip,
          ms: typeof item.ms === 'number' ? item.ms : (typeof item.latency === 'number' ? item.latency : null),
          status: item.status || (typeof item.ms === 'number' || typeof item.latency === 'number' ? 'online' : 'offline')
        };
      });
    });
  }

  function renderResults(results) {
    lastResults = results.slice().sort(function (a, b) {
      var am = a.status === 'online' ? a.ms : Infinity;
      var bm = b.status === 'online' ? b.ms : Infinity;
      return am - bm;
    });

    resultsBody.innerHTML = '';
    var bestCount = Math.min(20, lastResults.filter(function (r) { return r.status === 'online'; }).length);

    lastResults.forEach(function (r, i) {
      var tr = document.createElement('tr');
      tr.style.animationDelay = (i * 18) + 'ms';
      if (i < bestCount && r.status === 'online') tr.classList.add('is-best');

      var pingText = r.status === 'online' && typeof r.ms === 'number' ? r.ms + ' ms' : '—';
      var statusClass = r.status === 'online' ? 'online' : 'offline';
      var statusText = r.status === 'online' ? 'Online' : 'Offline';

      tr.innerHTML =
        '<td>' + (i + 1) + '</td>' +
        '<td class="ip-cell">' + r.ip + '</td>' +
        '<td class="ping-cell">' + pingText + '</td>' +
        '<td><span class="status-pill ' + statusClass + '">' + statusText + '</span></td>' +
        '<td><button class="copy-row-btn" type="button">Copy</button></td>';

      tr.querySelector('.copy-row-btn').addEventListener('click', function () {
        copyText(r.ip).then(function () { showToast('Copied ✓', 'success'); });
      });

      resultsBody.appendChild(tr);
    });

    var onlineCount = lastResults.filter(function (r) { return r.status === 'online'; }).length;
    resultsSummary.textContent = lastResults.length + ' نتیجه — ' + onlineCount + ' Online — Best ' + bestCount + ' مشخص شده';
    resultsWrap.hidden = false;
  }

  startScanBtn.addEventListener('click', function () {
    var count = parseInt(ipCountSelect.value, 10);
    startScanBtn.disabled = true;
    resultsWrap.hidden = true;
    setStatus(null);
    setProgress(8, 'در حال دریافت محدوده IP رسمی Cloudflare...', 0, count);

    fetchCloudflareRanges()
      .then(function (ranges) {
        setProgress(35, 'در حال انتخاب IPهای واقعی از محدوده رسمی...', 0, count);
        var ips = pickRandomIps(ranges, count);

        if (!SCAN_API_URL) {
          // Honest, explicit refusal to fabricate ping/status data.
          setProgress(100, 'تکمیل شد', count, count);
          setTimeout(function () {
            progressWrap.hidden = true;
            setStatus('اسکنر واقعی هنوز به API متصل نشده است.', 'info');
            startScanBtn.disabled = false;
          }, 300);
          return null;
        }

        setProgress(60, 'در حال اندازه‌گیری Latency واقعی از API...', 0, count);
        return measureViaApi(ips).then(function (results) {
          setProgress(100, 'تکمیل شد', results.length, count);
          setTimeout(function () {
            progressWrap.hidden = true;
            renderResults(results);
            startScanBtn.disabled = false;
          }, 250);
        });
      })
      .catch(function (err) {
        progressWrap.hidden = true;
        setStatus('امکان دریافت لیست IP رسمی Cloudflare وجود نداشت (خطای شبکه یا CORS). داده جعلی نمایش داده نمی‌شود. برای رفع این مشکل، worker.js را طبق README دیپلوی کنید و RANGES_API_URL را در app.js تنظیم کنید. جزئیات فنی: ' + err.message, 'error');
        startScanBtn.disabled = false;
      });
  });

  copyBestBtn.addEventListener('click', function () {
    var best = lastResults.filter(function (r) { return r.status === 'online'; }).slice(0, 20);
    if (!best.length) { showToast('نتیجه‌ای برای کپی وجود ندارد', 'error'); return; }
    copyText(best.map(function (r) { return r.ip; }).join('\n')).then(function () {
      showToast('Copied ✓', 'success');
    });
  });

  copyAllBtn.addEventListener('click', function () {
    if (!lastResults.length) { showToast('نتیجه‌ای برای کپی وجود ندارد', 'error'); return; }
    copyText(lastResults.map(function (r) { return r.ip; }).join('\n')).then(function () {
      showToast('Copied ✓', 'success');
    });
  });

  /* =========================================================================
     CONFIG BUILDER
     ========================================================================= */
  var configsInput = $('#configs-input');
  var ipsInput = $('#ips-input');
  var configsCount = $('#configs-count');
  var ipsCount = $('#ips-count');
  var combineBtn = $('#combine-btn');
  var combinedWrap = $('#combined-wrap');
  var combinedOutput = $('#combined-output');
  var combinedSummary = $('#combined-summary');
  var copyCombinedBtn = $('#copy-combined-btn');

  var VLESS_RE = /^vless:\/\/([^@]+)@([^:/?#\s]+):(\d+)(\/[^?#]*)?(\?[^#]*)?(#.*)?$/i;
  var IPV4_RE = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;

  function linesOf(textarea) {
    return textarea.value.split('\n').map(function (l) { return l.trim(); }).filter(Boolean);
  }

  function updateCounts() {
    configsCount.textContent = linesOf(configsInput).length;
    ipsCount.textContent = linesOf(ipsInput).length;
  }
  configsInput.addEventListener('input', updateCounts);
  ipsInput.addEventListener('input', updateCounts);
  updateCounts();

  function swapAddress(configLine, newIp) {
    var m = configLine.match(VLESS_RE);
    if (!m) return null;
    var uuid = m[1], port = m[3], path = m[4] || '', query = m[5] || '', fragment = m[6] || '';
    return 'vless://' + uuid + '@' + newIp + ':' + port + path + query + fragment;
  }

  combineBtn.addEventListener('click', function () {
    var configs = linesOf(configsInput);
    var ips = linesOf(ipsInput);

    if (!configs.length) { showToast('لطفاً حداقل یک کانفیگ VLESS وارد کنید.', 'error'); return; }
    if (!ips.length) { showToast('لطفاً حداقل یک IP وارد کنید.', 'error'); return; }

    var invalidIp = ips.find(function (ip) { return !IPV4_RE.test(ip); });
    if (invalidIp) { showToast('IP نامعتبر: ' + invalidIp, 'error'); return; }

    var invalidConfigIndex = configs.findIndex(function (c) { return !VLESS_RE.test(c); });
    if (invalidConfigIndex !== -1) {
      showToast('کانفیگ نامعتبر در خط ' + (invalidConfigIndex + 1) + ' (باید با vless:// شروع شود).', 'error');
      return;
    }

    var combined = [];
    configs.forEach(function (config) {
      ips.forEach(function (ip) {
        var out = swapAddress(config, ip);
        if (out) combined.push(out);
      });
    });

    combinedOutput.value = combined.join('\n');
    combinedSummary.textContent = configs.length + ' کانفیگ × ' + ips.length + ' IP = ' + combined.length + ' کانفیگ ترکیبی';
    combinedWrap.hidden = false;
  });

  copyCombinedBtn.addEventListener('click', function () {
    if (!combinedOutput.value) { showToast('چیزی برای کپی وجود ندارد', 'error'); return; }
    copyText(combinedOutput.value).then(function () {
      showToast('Copied ✓', 'success');
    });
  });

})();

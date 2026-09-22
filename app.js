(function () {
  'use strict';

  var RESULTS_JSON_URL = 'data/clean_ips.json';

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $all(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

  /* ==========================================================
     ۱. بستن لودینگ — تضمینی
     ========================================================== */
  (function initLoadingClose() {
    function closeSplash() {
      var screen = document.getElementById('loading-screen');
      if (!screen) return;
      screen.classList.add('is-hidden');
      screen.style.opacity = '0';
      screen.style.pointerEvents = 'none';
      setTimeout(function () {
        if (screen && screen.parentNode) screen.parentNode.removeChild(screen);
      }, 650);
    }
    if (document.readyState === 'complete') {
      setTimeout(closeSplash, 1200);
    } else {
      window.addEventListener('load', function () {
        setTimeout(closeSplash, 1200);
      });
    }
    setTimeout(closeSplash, 2500);
    setTimeout(closeSplash, 6000);
  })();

  /* ==========================================================
     ۲. Toast
     ========================================================== */
  var toastEl = $('#toast');
  var toastTimer = null;
  function showToast(message, kind) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.className = 'toast is-visible' + (kind ? ' is-' + kind : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.className = 'toast'; }, 2600);
  }

  /* ==========================================================
     ۳. Copy
     ========================================================== */
  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
  }
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () {
        fallbackCopy(text);
      });
    }
    fallbackCopy(text);
    return Promise.resolve();
  }

  /* ==========================================================
     ۴. Drawer / Menu
     ========================================================== */
  var hamburgerBtn = $('#hamburger-btn');
  var drawer = $('#drawer');
  var drawerOverlay = $('#drawer-overlay');

  function openDrawer() {
    if (!drawer) return;
    drawer.classList.add('is-open');
    drawer.setAttribute('aria-hidden', 'false');
    if (drawerOverlay) drawerOverlay.classList.add('is-visible');
    if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'true');
  }
  function closeDrawer() {
    if (!drawer) return;
    drawer.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
    if (drawerOverlay) drawerOverlay.classList.remove('is-visible');
    if (hamburgerBtn) hamburgerBtn.setAttribute('aria-expanded', 'false');
  }
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener('click', function () {
      if (drawer.classList.contains('is-open')) closeDrawer();
      else openDrawer();
    });
  }
  if (drawerOverlay) drawerOverlay.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeDrawer();
  });

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

  /* ==========================================================
     ۵. Scanner + Earth Loader + Last Update
     ========================================================== */
  var startScanBtn    = $('#start-scan-btn');
  var ipCountSelect   = $('#ip-count');
  var earthLoader     = $('#earth-loader');
  var earthTitle      = $('#earth-status-title');
  var earthSub        = $('#earth-status-sub');
  var progressWrap    = $('#scan-progress-wrap');
  var progressFill    = $('#scan-progress-fill');
  var progressLabel   = $('#scan-progress-label');
  var progressCount   = $('#scan-progress-count');
  var statusMsg       = $('#scan-status-msg');
  var resultsWrap     = $('#results-wrap');
  var resultsBody     = $('#results-body');
  var resultsSummary  = $('#results-summary');
  var lastUpdateBadge = $('#last-update-badge');
  var copyBestBtn     = $('#copy-best-btn');
  var copyAllBtn      = $('#copy-all-btn');

  var lastResults = [];

  function setStatus(message, kind) {
    if (!statusMsg) return;
    if (!message) {
      statusMsg.hidden = true;
      statusMsg.textContent = '';
      return;
    }
    statusMsg.hidden = false;
    statusMsg.className = 'status-msg' + (kind ? ' is-' + kind : '');
    statusMsg.textContent = message;
  }

  function showEarth(title, sub) {
    if (!earthLoader) return;
    if (earthTitle) earthTitle.textContent = title || 'در حال دریافت داده‌ها';
    if (earthSub)   earthSub.textContent   = sub   || 'اتصال به سرور Matix';
    earthLoader.hidden = false;
    if (progressWrap) progressWrap.hidden = true;
  }

  function hideEarth() {
    if (earthLoader) earthLoader.hidden = true;
  }

  function setProgress(percent, label, doneCount, totalCount) {
    if (!progressWrap) return;
    progressWrap.hidden = false;
    if (progressFill) progressFill.style.width = Math.max(0, Math.min(100, percent)) + '%';
    if (label && progressLabel) progressLabel.textContent = label;
    if (progressCount) progressCount.textContent = doneCount + ' / ' + totalCount;
  }

  /* ---- زمان نسبی (هوشمند) ---- */
  function timeAgo(ts) {
    if (!ts) return 'نامشخص';

    // اگه میلی‌ثانیه بود → ثانیه
    if (ts > 1e12) ts = Math.floor(ts / 1000);

    var now = Math.floor(Date.now() / 1000);
    var diff = now - ts;

    // اگه زمان آینده بود → ساعت سرور خراب
    if (diff < -60) return '⚠️ زمان نامعتبر';

    // اگه تو ۶۰ ثانیه آینده بود → بپذیر به عنوان الان
    if (diff < 0) diff = 0;

    if (diff < 30)         return 'همین الان';
    if (diff < 60)         return diff + ' ثانیه پیش';
    if (diff < 3600)       return Math.floor(diff / 60) + ' دقیقه پیش';
    if (diff < 86400)      return Math.floor(diff / 3600) + ' ساعت پیش';
    if (diff < 86400 * 30) return Math.floor(diff / 86400) + ' روز پیش';
    return Math.floor(diff / 86400) + ' روز پیش';
  }

  function renderLastUpdate(data) {
    if (!lastUpdateBadge) return;
    var ts = data.updated || data.last_updated || 0;
    if (!ts) { lastUpdateBadge.hidden = true; return; }

    if (ts > 1e12) ts = Math.floor(ts / 1000);

    var now = Math.floor(Date.now() / 1000);
    var diff = now - ts;
    var ago = timeAgo(ts);

    var cls = 'last-update-badge';

    // اگه timestamp آینده بود (> ۶۰ ثانیه جلوتر)
    if (diff < -60) {
      cls += ' is-stale';
      lastUpdateBadge.className = cls;
      lastUpdateBadge.innerHTML =
        '<span class="dot"></span>' +
        '<span>⚠️ ساعت سرور نامعتبر — لطفاً بعداً تلاش کن</span>';
      lastUpdateBadge.hidden = false;
      return;
    }

    var diffMin = Math.max(0, diff) / 60;
    if (diffMin > 60 * 24)      cls += ' is-stale';
    else if (diffMin > 30)      cls += ' is-old';

    // زمان دقیق به شمسی
    var exact = '';
    try {
      exact = new Date(ts * 1000).toLocaleString('fa-IR', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit'
      });
    } catch (e) { exact = ''; }

    lastUpdateBadge.className = cls;
    lastUpdateBadge.innerHTML =
      '<span class="dot"></span>' +
      '<span>آخرین بروزرسانی IPها: <strong>' + ago + '</strong>' +
      (exact ? ' <span style="opacity:.6">(' + exact + ')</span>' : '') +
      '</span>';
    lastUpdateBadge.hidden = false;
  }

  /* ---- رندر جدول ---- */
  function renderResults(results) {
    lastResults = results.slice().sort(function (a, b) {
      if (a.long_term && !b.long_term) return -1;
      if (!a.long_term && b.long_term) return 1;
      if (a.persistent && !b.persistent) return -1;
      if (!a.persistent && b.persistent) return 1;
      return (a.ms == null ? 99999 : a.ms) - (b.ms == null ? 99999 : b.ms);
    });

    if (!lastResults.length) {
      setStatus('هیچ IP سالمی پیدا نشد. دوباره امتحان کن.', 'error');
      if (resultsWrap) resultsWrap.hidden = true;
      return;
    }

    if (resultsBody) {
      resultsBody.innerHTML = '';
      lastResults.forEach(function (item, index) {
        var tr = document.createElement('tr');
        var cls = [];
        if (item.long_term) cls.push('is-long-term');
        else if (item.persistent) cls.push('is-persistent');
        if (index < 20) cls.push('is-best');
        if (cls.length) tr.className = cls.join(' ');

        var statusPill = item.status === 'online'
          ? '<span class="status-pill online">online</span>'
          : '<span class="status-pill offline">' + (item.status || 'unknown') + '</span>';

        var pingText = item.ms != null ? item.ms + ' ms' : '—';

        tr.innerHTML =
          '<td>' + (index + 1) + '</td>' +
          '<td class="ip-cell">' + item.ip + '</td>' +
          '<td class="ping-cell">' + pingText + '</td>' +
          '<td>' + statusPill + '</td>' +
          '<td><button class="copy-row-btn" data-ip="' + item.ip + '">Copy</button></td>';

        resultsBody.appendChild(tr);
      });
    }

    var persistentCount = lastResults.filter(function (x) { return x.persistent; }).length;
    var longTermCount   = lastResults.filter(function (x) { return x.long_term; }).length;
    if (resultsSummary) {
      resultsSummary.textContent =
        lastResults.length + ' IP | 💎 ' + persistentCount +
        ' persistent | 👑 ' + longTermCount + ' long-term';
    }

    if (resultsWrap) resultsWrap.hidden = false;
  }

  /* ---- Start Scan ---- */
  function startScan() {
    if (!startScanBtn) return;
    startScanBtn.disabled = true;
    if (resultsWrap) resultsWrap.hidden = true;
    setStatus('', null);

    showEarth('در حال دریافت داده‌های Cloudflare', 'اتصال به سرور Matix...');

    var subMessages = [
      'در حال اسکن IPهای کلادفلر...',
      'بررسی پاسخ‌دهی سرورها...',
      'محاسبه سرعت و پینگ...',
      'در حال آماده‌سازی نتایج...'
    ];
    var subIdx = 0;
    var subTimer = setInterval(function () {
      subIdx = (subIdx + 1) % subMessages.length;
      if (earthSub) earthSub.textContent = subMessages[subIdx];
    }, 1400);

    var t = Date.now();
    fetch(RESULTS_JSON_URL + '?t=' + t, { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        clearInterval(subTimer);

        var minDelay = 1800;
        var elapsed = Date.now() - t;
        var wait = Math.max(0, minDelay - elapsed);

        setTimeout(function () {
          if (earthTitle) earthTitle.textContent = 'نتایج آماده شد';
          if (earthSub)   earthSub.textContent   = 'در حال نمایش...';

          setTimeout(function () {
            hideEarth();

            var limit = parseInt(ipCountSelect.value, 10) || 20;
            var results = (data.results || data.ips || []).slice(0, limit);

            if (!results.length) {
              setStatus('لیست IP خالی است. لطفاً بعداً تلاش کن.', 'error');
              startScanBtn.disabled = false;
              return;
            }

            renderLastUpdate(data);
            renderResults(results);
            startScanBtn.disabled = false;
            showToast(results.length + ' IP بارگذاری شد ✅', 'success');
          }, 600);
        }, wait);
      })
      .catch(function (err) {
        clearInterval(subTimer);
        hideEarth();
        console.error('[Matix] Scan error:', err);
        setStatus('خطا در دریافت داده‌ها: ' + err.message +
          ' — فایل data/clean_ips.json را بررسی کن.', 'error');
        startScanBtn.disabled = false;
      });
  }

  if (startScanBtn) startScanBtn.addEventListener('click', startScan);

  /* دکمه Copy هر ردیف */
  if (resultsBody) {
    resultsBody.addEventListener('click', function (e) {
      var btn = e.target.closest('.copy-row-btn');
      if (!btn) return;
      var ip = btn.getAttribute('data-ip');
      copyText(ip).then(function () {
        showToast('IP کپی شد: ' + ip, 'success');
      });
    });
  }

  /* Copy 20 Best */
  if (copyBestBtn) {
    copyBestBtn.addEventListener('click', function () {
      if (!lastResults.length) { showToast('اول اسکن کن', 'error'); return; }
      var best = lastResults.slice(0, 20).map(function (r) { return r.ip; }).join('\n');
      copyText(best).then(function () {
        showToast('۲۰ IP برتر کپی شد ⚡', 'success');
      });
    });
  }

  /* Copy All */
  if (copyAllBtn) {
    copyAllBtn.addEventListener('click', function () {
      if (!lastResults.length) { showToast('اول اسکن کن', 'error'); return; }
      var all = lastResults.map(function (r) { return r.ip; }).join('\n');
      copyText(all).then(function () {
        showToast('همه IPها کپی شدند', 'success');
      });
    });
  }

  /* ---- Auto-load badge در شروع ---- */
  (function loadInitialBadge() {
    fetch(RESULTS_JSON_URL + '?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data) renderLastUpdate(data);
      })
      .catch(function () { /* silent */ });
  })();

  /* ==========================================================
     ۶. Config Builder
     ========================================================== */
  var configsInput    = $('#configs-input');
  var ipsInput        = $('#ips-input');
  var configsCount    = $('#configs-count');
  var ipsCount        = $('#ips-count');
  var combineBtn      = $('#combine-btn');
  var combinedWrap    = $('#combined-wrap');
  var combinedOutput  = $('#combined-output');
  var combinedSummary = $('#combined-summary');
  var copyCombinedBtn = $('#copy-combined-btn');

  function updateCounts() {
    if (configsCount && configsInput) {
      configsCount.textContent = configsInput.value
        .split('\n').map(function (s) { return s.trim(); })
        .filter(Boolean).length;
    }
    if (ipsCount && ipsInput) {
      ipsCount.textContent = ipsInput.value
        .split('\n').map(function (s) { return s.trim(); })
        .filter(Boolean).length;
    }
  }
  if (configsInput) configsInput.addEventListener('input', updateCounts);
  if (ipsInput)     ipsInput.addEventListener('input', updateCounts);

  /* جایگزینی host در VLESS */
  function replaceHost(configLine, newIp) {
    try {
      var m = configLine.match(/^(vless:\/\/[^@]+@)([^:\/?#]+)(:\d+)([^\s]*)$/i);
      if (!m) return null;
      return m[1] + newIp + m[3] + m[4];
    } catch (e) {
      return null;
    }
  }

  function combineConfigs() {
    if (!configsInput || !ipsInput) return;

    var configs = configsInput.value
      .split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
    var ips = ipsInput.value
      .split('\n').map(function (s) { return s.trim(); }).filter(Boolean);

    if (!configs.length) { showToast('هیچ کانفیگی وارد نشده', 'error'); return; }
    if (!ips.length)     { showToast('هیچ IP وارد نشده', 'error'); return; }

    var output = [];
    var failed = 0;

    configs.forEach(function (cfg) {
      ips.forEach(function (ip) {
        var replaced = replaceHost(cfg, ip);
        if (replaced) output.push(replaced);
        else failed++;
      });
    });

    if (!output.length) {
      showToast('هیچ کانفیگ معتبری ساخته نشد. فرمت VLESS را بررسی کن.', 'error');
      return;
    }

    if (combinedOutput) combinedOutput.value = output.join('\n');
    if (combinedSummary) {
      combinedSummary.textContent = output.length + ' کانفیگ ساخته شد' +
        (failed ? ' (' + failed + ' نامعتبر نادیده گرفته شد)' : '');
    }
    if (combinedWrap) combinedWrap.hidden = false;
    showToast(output.length + ' کانفیگ ساخته شد ✅', 'success');
  }

  if (combineBtn) combineBtn.addEventListener('click', combineConfigs);

  if (copyCombinedBtn) {
    copyCombinedBtn.addEventListener('click', function () {
      if (!combinedOutput || !combinedOutput.value) return;
      copyText(combinedOutput.value).then(function () {
        showToast('همه کانفیگ‌ها کپی شدند', 'success');
      });
    });
  }

  /* ==========================================================
     ۷. راه‌اندازی اولیه
     ========================================================== */
  updateCounts();

})();

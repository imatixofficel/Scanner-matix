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
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () {
        return fallbackCopy(text);
      });
    }
    return Promise.resolve(fallbackCopy(text));
  }
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
    drawerOverlay.classList.add('is-visible');
    hamburgerBtn.setAttribute('aria-expanded', 'true');
  }
  function closeDrawer() {
    if (!drawer) return;
    drawer.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
    drawerOverlay.classList.remove('is-visible');
    hamburgerBtn.setAttribute('aria-expanded', 'false');
  }
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener('click', function () {
      if (drawer.classList.contains('is-open')) closeDrawer(); else openDrawer();
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
     ۵. Scanner
     ========================================================== */
  var startScanBtn    = $('#start-scan-btn');
  var ipCountSelect   = $('#ip-count');
  var progressWrap    = $('#scan-progress-wrap');
  var progressFill    = $('#scan-progress-fill');
  var progressLabel   = $('#scan-progress-label');
  var progressCount   = $('#scan-progress-count');
  var statusMsg       = $('#scan-status-msg');
  var resultsWrap     = $('#results-wrap');
  var resultsBody     = $('#results-body');
  var resultsSummary  = $('#results-summary');
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

  function setProgress(percent, label, doneCount, totalCount) {
    if (!progressWrap) return;
    progressWrap.hidden = false;
    if (progressFill) progressFill.style.width = Math.max(0, Math.min(100, percent)) + '%';
    if (label && progressLabel) progressLabel.textContent = label;
    if (progressCount) progressCount.textContent = doneCount + ' / ' + totalCount;
  }

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
      resultsWrap.hidden = true;
      return;
    }

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

    var persistentCount = lastResults.filter(function (x) { return x.persistent; }).length;
    var longTermCount   = lastResults.filter(function (x) { return x.long_term; }).length;
    resultsSummary.textContent =
      lastResults.length + ' IP | 💎 ' + persistentCount +
      ' persistent | 👑 ' + longTermCount + ' long-term';

    resultsWrap.hidden = false;
  }

  function startScan() {
    if (!startScanBtn) return;
    startScanBtn.disabled = true;
    resultsWrap.hidden = true;
    setStatus('', null);
    setProgress(5, 'در حال دریافت داده‌ها از سرور...', 0, 0);

    var t = Date.now();
    fetch(RESULTS_JSON_URL + '?t=' + t, { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        setProgress(50, 'در حال پردازش نتایج...', 0, 0);
        var limit = parseInt(ipCountSelect.value, 10) || 20;
        var results = (data.results || data.ips || []).slice(0, limit);

        if (!results.length) {
          setStatus('لیست IP خالی است. لطفاً بعداً تلاش کن.', 'error');
          progressWrap.hidden = true;
          startScanBtn.disabled = false;
          return;
        }

        setTimeout(function () {
          setProgress(100, 'انجام شد ✅', results.length, results.length);
          renderResults(results);
          setTimeout(function () { progressWrap.hidden = true; }, 900);
          startScanBtn.disabled = false;
          showToast(results.length + ' IP بارگذاری شد', 'success');
        }, 300);
      })
      .catch(function (err) {
        console.error('[Matix] Scan error:', err);
        setStatus('خطا در دریافت داده‌ها: ' + err.message + ' — فایل data/clean_ips.json را بررسی کن.', 'error');
        if (progressWrap) progressWrap.hidden = true;
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

  /* ==========================================================
     ۶. Config Builder
     ========================================================== */
  var configsInput  = $('#configs-input');
  var ipsInput      = $('#ips-input');
  var configsCount  = $('#configs-count');
  var ipsCount      = $('#ips-count');
  var combineBtn    = $('#combine-btn');
  var combinedWrap  = $('#combined-wrap');
  var combinedOutput= $('#combined-output');
  var combinedSummary = $('#combined-summary');
  var copyCombinedBtn = $('#copy-combined-btn');

  function updateCounts() {
    if (configsCount) {
      configsCount.textContent = configsInput.value
        .split('\n').map(function (s) { return s.trim(); })
        .filter(Boolean).length;
    }
    if (ipsCount) {
      ipsCount.textContent = ipsInput.value
        .split('\n').map(function (s) { return s.trim(); })
        .filter(Boolean).length;
    }
  }
  if (configsInput) configsInput.addEventListener('input', updateCounts);
  if (ipsInput)     ipsInput.addEventListener('input', updateCounts);

  /**
   * جایگزینی IP/Host داخل کانفیگ VLESS.
   * ساختار: vless://uuid@host:port?query#remark
   * فقط بخش host را عوض می‌کنیم، پورت و بقیه ثابت می‌مانند.
   */
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
    var configs = configsInput.value
      .split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
    var ips = ipsInput.value
      .split('\n').map(function (s) { return s.trim(); }).filter(Boolean);

    if (!configs.length) { showToast('هیچ کانفیگی وارد نشده', 'error'); return; }
    if (!ips.length)     { showToast('هیچ IP وارد نشده', 'error'); return; }

    var output = [];
    var failed = 0;

    configs.forEach(function (cfg, idx) {
      ips.forEach(function (ip) {
        var replaced = replaceHost(cfg, ip);
        if (replaced) {
          output.push(replaced);
        } else {
          failed++;
        }
      });
    });

    if (!output.length) {
      showToast('هیچ کانفیگ معتبری ساخته نشد. فرمت VLESS را بررسی کن.', 'error');
      return;
    }

    combinedOutput.value = output.join('\n');
    combinedSummary.textContent = output.length + ' کانفیگ ساخته شد' +
      (failed ? ' (' + failed + ' نامعتبر نادیده گرفته شد)' : '');
    combinedWrap.hidden = false;
    showToast(output.length + ' کانفیگ ساخته شد ✅', 'success');
  }

  if (combineBtn) combineBtn.addEventListener('click', combineConfigs);

  if (copyCombinedBtn) {
    copyCombinedBtn.addEventListener('click', function () {
      if (!combinedOutput.value) return;
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

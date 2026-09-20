(function () {
  'use strict';

  var RESULTS_JSON_URL = 'data/clean_ips.json';

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $all(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }

  var toastEl = $('#toast');
  var toastTimer = null;
  function showToast(message, kind) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.className = 'toast is-visible' + (kind ? ' is-' + kind : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.className = 'toast'; }, 2600);
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
    ta.focus(); ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
    return Promise.resolve();
  }

  window.addEventListener('load', function () {
    setTimeout(function () {
      var screen = $('#loading-screen');
      if (!screen) return;
      screen.classList.add('is-hidden');
      setTimeout(function () { screen.remove(); }, 650);
    }, 1300);
  });

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

  var lastResults = [];

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

  function renderResults(results) {
    lastResults = results.slice().sort(function (a, b) {
      if (a.persistent && !b.persistent) return -1;
      if (!a.persistent && b.persistent) return 1;
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
      if (r.persistent) tr.classList.add('is-persistent');

      var pingText = r.status === 'online' && typeof r.ms === 'number' ? r.ms + ' ms' : '—';
      var speedText = r.speed_mbps ? ' | ' + r.speed_mbps + ' Mbps' : '';
      var persistentBadge = r.persistent ? ' 💎' : '';
      var statusClass = r.status === 'online' ? 'online' : 'offline';
      var statusText = r.status === 'online' ? 'Online' : 'Offline';
      var coloText = r.colo ? ' <span style="opacity:.6;font-size:11px">' + r.colo + '</span>' : '';

      tr.innerHTML =
        '<td>' + (i + 1) + '</td>' +
        '<td class="ip-cell">' + r.ip + persistentBadge + '</td>' +
        '<td class="ping-cell">' + pingText + speedText + '</td>' +
        '<td><span class="status-pill ' + statusClass + '">' + statusText + '</span>' + coloText + '</td>' +
        '<td><button class="copy-row-btn" type="button">Copy</button></td>';

      tr.querySelector('.copy-row-btn').addEventListener('click', function () {
        copyText(r.ip).then(function () { showToast('Copied ✓', 'success'); });
      });

      resultsBody.appendChild(tr);
    });

    var onlineCount = lastResults.filter(function (r) { return r.status === 'online'; }).length;
    var persistentCount = lastResults.filter(function (r) { return r.persistent; }).length;
    resultsSummary.textContent = lastResults.length + ' نتیجه — ' + onlineCount + ' Online — ' + persistentCount + ' ماندگار 💎';
    resultsWrap.hidden = false;
  }

  startScanBtn.addEventListener('click', function () {
    var count = parseInt(ipCountSelect.value, 10);
    startScanBtn.disabled = true;
    resultsWrap.hidden = true;
    setStatus(null);

    var loadingMessages = [
      '⏳ دریافت لیست اولیه IPها...',
      '🔍 بررسی زنده بودن IPها...',
      '⚡ تست سرعت IPهای برتر...',
      '📊 مرتب‌سازی نتایج...',
      '✅ آماده‌سازی نمایش...'
    ];
    var loadingIdx = 0;
    setProgress(5, loadingMessages[0], 0, count);
    var loadingInterval = setInterval(function() {
      loadingIdx = (loadingIdx + 1) % loadingMessages.length;
      setProgress((loadingIdx + 1) * 18, loadingMessages[loadingIdx], 0, count);
    }, 500);

    fetch(RESULTS_JSON_URL + '?t=' + Date.now())
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        clearInterval(loadingInterval);
        if (!data.results || !data.results.length) {
          throw new Error('هنوز اسکنی انجام نشده. چند دقیقه دیگه امتحان کن.');
        }
        setProgress(100, 'تکمیل شد', data.results.length, data.results.length);

        var ageMin = Math.round((Date.now() / 1000 - data.updated) / 60);
        var persistentCount = data.persistent_count || 0;
        setStatus(
          '🔄 آخرین به‌روزرسانی: ' + ageMin + ' دقیقه پیش — ' +
          '✅ ' + data.online_count + ' IP آنلاین از ' + data.total_tested + ' تست‌شده — ' +
          '💎 ' + persistentCount + ' IP ماندگار',
          'info'
        );

        var results = data.results.slice(0, count);
        setTimeout(function () {
          progressWrap.hidden = true;
          renderResults(results);
          startScanBtn.disabled = false;
        }, 500);
      })
      .catch(function (err) {
        clearInterval(loadingInterval);
        progressWrap.hidden = true;
        setStatus('دریافت نتایج با خطا مواجه شد: ' + err.message, 'error');
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
      showToast('کانفیگ نامعتبر در خط ' + (invalidConfigIndex + 1), 'error');
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

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

  /* --- New Success Notification (bottom toast) --- */
  function showNotif(message, options) {
    options = options || {};
    var container = document.getElementById('toastContainer');
    if (!container) return;

    var notif = document.createElement('div');
    notif.className = 'toast-notif';
    notif.innerHTML =
      '<div class="toast-notif-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg></div>' +
      '<div class="toast-notif-msg">' + message + '</div>' +
      '<button class="toast-notif-close" type="button" aria-label="close"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>';

    notif.querySelector('.toast-notif-close').addEventListener('click', function () {
      notif.style.opacity = '0';
      setTimeout(function () { if (notif.parentNode) notif.parentNode.removeChild(notif); }, 300);
    });

    container.appendChild(notif);

    setTimeout(function () {
      notif.style.opacity = '0';
      notif.style.transform = 'translateY(-10px)';
      setTimeout(function () { if (notif.parentNode) notif.parentNode.removeChild(notif); }, 300);
    }, options.duration || 5000);
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

  /* =========================================================================
     Country Filter
     ========================================================================= */

  var COUNTRY_FLAGS = {
    'FRA': { flag: '🇩🇪', name: 'آلمان (فرانکفورت)' },
    'DUS': { flag: '🇩🇪', name: 'آلمان (دوسلدورف)' },
    'AMS': { flag: '🇳🇱', name: 'هلند (آمستردام)' },
    'LHR': { flag: '🇬🇧', name: 'انگلیس (لندن)' },
    'CDG': { flag: '🇫🇷', name: 'فرانسه (پاریس)' },
    'MXP': { flag: '🇮🇹', name: 'ایتالیا (میلان)' },
    'FCO': { flag: '🇮🇹', name: 'ایتالیا (روم)' },
    'VIE': { flag: '🇦🇹', name: 'اتریش (وین)' },
    'WAW': { flag: '🇵🇱', name: 'لهستان (ورشو)' },
    'BRU': { flag: '🇧🇪', name: 'بلژیک (بروکسل)' },
    'MAD': { flag: '🇪🇸', name: 'اسپانیا (مادرید)' },
    'BCN': { flag: '🇪🇸', name: 'اسپانیا (بارسلونا)' },
    'ZRH': { flag: '🇨🇭', name: 'سوئیس (زوریخ)' },
    'IST': { flag: '🇹🇷', name: 'ترکیه (استانبول)' },
    'OTP': { flag: '🇷🇴', name: 'رومانی (بخارست)' },
    'SOF': { flag: '🇧🇬', name: 'بلغارستان (صوفیه)' },
    'ARN': { flag: '🇸🇪', name: 'سوئد (استکهلم)' },
    'HEL': { flag: '🇫🇮', name: 'فنلاند (هلسینکی)' },
    'OSL': { flag: '🇳🇴', name: 'نروژ (اسلو)' },
    'CPH': { flag: '🇩🇰', name: 'دانمارک (کپنهاگ)' },
    'LAX': { flag: '🇺🇸', name: 'آمریکا (لس‌آنجلس)' },
    'SEA': { flag: '🇺🇸', name: 'آمریکا (سیاتل)' },
    'SJC': { flag: '🇺🇸', name: 'آمریکا (سن‌خوزه)' },
    'IAD': { flag: '🇺🇸', name: 'آمریکا (واشنگتن)' },
    'EWR': { flag: '🇺🇸', name: 'آمریکا (نیویورک)' },
    'ORD': { flag: '🇺🇸', name: 'آمریکا (شیکاگو)' },
    'YYZ': { flag: '🇨🇦', name: 'کانادا (تورنتو)' },
    'NRT': { flag: '🇯🇵', name: 'ژاپن (توکیو)' },
    'KIX': { flag: '🇯🇵', name: 'ژاپن (اوساکا)' },
    'SIN': { flag: '🇸🇬', name: 'سنگاپور' },
    'HKG': { flag: '🇭🇰', name: 'هنگ‌کنگ' },
    'ICN': { flag: '🇰🇷', name: 'کره جنوبی (سئول)' },
    'BOM': { flag: '🇮🇳', name: 'هند (بمبئی)' },
    'DEL': { flag: '🇮🇳', name: 'هند (دهلی)' },
    'DXB': { flag: '🇦🇪', name: 'امارات (دوبی)' },
    'TLV': { flag: '🇮🇱', name: 'اسرائیل (تل‌آویو)' },
    'SYD': { flag: '🇦🇺', name: 'استرالیا (سیدنی)' },
    'GRU': { flag: '🇧🇷', name: 'برزیل (سائوپائولو)' },
    'EZE': { flag: '🇦🇷', name: 'آرژانتین (بوئنوس‌آیرس)' },
    'JNB': { flag: '🇿🇦', name: 'آفریقای جنوبی (ژوهانسبورگ)' }
  };

  var selectedCountry = null;
  var cachedScannerIPs = [];

  var countryPicker = document.getElementById('countryPicker');
  var countryTrigger = document.getElementById('countryTrigger');
  var countryTriggerFlag = document.getElementById('countryTriggerFlag');
  var countryTriggerName = document.getElementById('countryTriggerName');
  var countrySearch = document.getElementById('countrySearch');
  var countryList = document.getElementById('countryList');
  var countryStatus = document.getElementById('countryStatus');

  if (countryTrigger) {
    countryTrigger.addEventListener('click', function (e) {
      e.stopPropagation();
      countryPicker.classList.toggle('is-open');
      if (countryPicker.classList.contains('is-open')) {
        countrySearch.focus();
        renderCountryList();
      }
    });

    document.addEventListener('click', function (e) {
      if (countryPicker && !countryPicker.contains(e.target)) {
        countryPicker.classList.remove('is-open');
      }
    });

    countrySearch.addEventListener('input', renderCountryList);
  }

  function renderCountryList() {
    if (!countryList) return;
    var query = (countrySearch.value || '').trim().toLowerCase();
    var countByColo = {};

    cachedScannerIPs.forEach(function (item) {
      var c = item.colo || 'UNK';
      countByColo[c] = (countByColo[c] || 0) + 1;
    });

    var html = '';

    var showAuto = !query || 'خودکار'.indexOf(query) !== -1 || 'auto'.indexOf(query) !== -1 || 'بهترین'.indexOf(query) !== -1;
    if (showAuto) {
      html += '<button class="country-item is-auto' + (selectedCountry === null ? ' is-selected' : '') + '" data-colo="">' +
        '<span class="flag">⚡</span>' +
        '<span class="name">خودکار (بهترین)</span>' +
        '<span class="code">AUTO</span>' +
        '<span class="count-badge">' + cachedScannerIPs.length + '</span>' +
        '</button>';
    }

    var sorted = Object.keys(countByColo).sort(function (a, b) { return countByColo[b] - countByColo[a]; });

    sorted.forEach(function (colo) {
      var info = COUNTRY_FLAGS[colo] || { flag: '🌍', name: colo };
      if (query && info.name.toLowerCase().indexOf(query) === -1 && colo.toLowerCase().indexOf(query) === -1) return;

      html += '<button class="country-item' + (selectedCountry === colo ? ' is-selected' : '') + '" data-colo="' + colo + '">' +
        '<span class="flag">' + info.flag + '</span>' +
        '<span class="name">' + info.name + '</span>' +
        '<span class="code">' + colo + '</span>' +
        '<span class="count-badge">' + countByColo[colo] + '</span>' +
        '</button>';
    });

    if (!html) html = '<div style="padding:16px; text-align:center; color:var(--text-tertiary);">کشوری یافت نشد</div>';

    countryList.innerHTML = html;

    countryList.querySelectorAll('.country-item').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var colo = btn.dataset.colo;
        selectedCountry = colo || null;

        if (colo) {
          var info = COUNTRY_FLAGS[colo] || { flag: '🌍', name: colo };
          countryTriggerFlag.textContent = info.flag;
          countryTriggerName.textContent = info.name + ' (' + colo + ')';
        } else {
          countryTriggerFlag.textContent = '⚡';
          countryTriggerName.textContent = 'خودکار (بهترین)';
        }

        countryPicker.classList.remove('is-open');
        updateCountryStatus();
      });
    });
  }

  function updateCountryStatus() {
    if (!countryStatus) return;
    if (!cachedScannerIPs.length) {
      countryStatus.textContent = 'هنوز IP از اسکنر دریافت نشده';
      return;
    }
    if (selectedCountry) {
      var info = COUNTRY_FLAGS[selectedCountry] || { flag: '🌍', name: selectedCountry };
      var count = cachedScannerIPs.filter(function (r) { return r.colo === selectedCountry; }).length;
      countryStatus.innerHTML = '✅ فیلتر فعال: ' + info.flag + ' ' + info.name + ' — ' + count + ' IP';
    } else {
      countryStatus.innerHTML = '⚡ حالت خودکار فعال — ' + cachedScannerIPs.length + ' IP (مرتب بر اساس بهترین پینگ)';
    }
  }

  /* =========================================================================
     Drawer
     ========================================================================= */

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

  /* =========================================================================
     IP Scanner
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
      if (a.long_term && !b.long_term) return -1;
      if (!a.long_term && b.long_term) return 1;
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
      if (r.long_term) tr.classList.add('is-long-term');

      var pingText = r.status === 'online' && typeof r.ms === 'number' ? r.ms + ' ms' : '—';
      var speedText = r.speed_mbps ? ' | ' + r.speed_mbps + ' Mbps' : '';

      var badge = '';
      if (r.long_term) badge = ' 💎💎';
      else if (r.persistent) badge = ' 💎';

      var sourceText = '';
      if (r.source === 'fresh') sourceText = ' <span style="opacity:.5;font-size:10px">[NEW]</span>';
      else if (r.source === 'old') sourceText = ' <span style="opacity:.5;font-size:10px">[OLD]</span>';

      var statusClass = r.status === 'online' ? 'online' : 'offline';
      var statusText = r.status === 'online' ? 'Online' : 'Offline';
      var coloText = r.colo ? ' <span style="opacity:.6;font-size:11px">' + r.colo + '</span>' : '';

      tr.innerHTML =
        '<td>' + (i + 1) + '</td>' +
        '<td class="ip-cell">' + r.ip + badge + sourceText + '</td>' +
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
    var longTermCount = lastResults.filter(function (r) { return r.long_term; }).length;

    resultsSummary.textContent =
      lastResults.length + ' نتیجه — ' +
      onlineCount + ' Online — ' +
      longTermCount + ' 💎💎 بلندمدت — ' +
      persistentCount + ' 💎 ماندگار';

    resultsWrap.hidden = false;
  }

  startScanBtn.addEventListener('click', function () {
    var count = parseInt(ipCountSelect.value, 10);
    startScanBtn.disabled = true;
    resultsWrap.hidden = true;
    setStatus(null);

    var loadingMessages = [
      '⏳ دریافت لیست IPها...',
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

        // ذخیره IPها برای فیلتر کشور
        if (!cachedScannerIPs.length) {
          cachedScannerIPs = data.results.slice();
          updateCountryStatus();
        }

        var ageMin = Math.round((Date.now() / 1000 - data.updated) / 60);
        var persistentCount = data.persistent_count || 0;
        var longTermCount = data.long_term_count || 0;
        var freshCount = data.fresh_count || 0;
        var oldCount = data.old_count || 0;

        setStatus(
          '🔄 آخرین به‌روزرسانی: ' + ageMin + ' دقیقه پیش — ' +
          '✅ ' + data.online_count + ' IP آنلاین — ' +
          '🆕 ' + freshCount + ' تازه — ' +
          '📦 ' + oldCount + ' قبلی — ' +
          '💎 ' + persistentCount + ' ماندگار — ' +
          '💎💎 ' + longTermCount + ' بلندمدت',
          'info'
        );

        // فیلتر بر اساس کشور انتخاب‌شده
        var filtered = data.results;
        if (selectedCountry) {
          filtered = data.results.filter(function (r) { return r.colo === selectedCountry; });
          if (!filtered.length) {
            throw new Error('هیچ IPی از این کشور پیدا نشد. کشور دیگه‌ای انتخاب کن.');
          }
        }

        var results = filtered.slice(0, count);
        setTimeout(function () {
          progressWrap.hidden = true;
          renderResults(results);
          startScanBtn.disabled = false;
          // پیام موفقیت
          showNotif(
            filtered.length + ' IP پیدا شد' + (selectedCountry ? ' از ' + selectedCountry : '') +
            ' (نمایش ' + results.length + ')'
          );
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

  /* =========================================================================
     Config Builder
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

    if (!configs.length) { showToast('لطفاً حداقل یک 

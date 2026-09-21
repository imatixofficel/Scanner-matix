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
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.focus(); ta.select();
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
      statusMsg.hidden = true; statusMsg.textContent = ''; return;
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
      if (a.p

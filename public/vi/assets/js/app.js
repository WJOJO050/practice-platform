/* ============================================================
   人工智能学院 视觉形象识别系统 · 交互
   ============================================================ */
(function () {
  'use strict';

  var DATA = window.VI_DATA || { chapters: [], items: [] };
  var chapters = DATA.chapters;
  var items = DATA.items;
  var chMap = {};
  chapters.forEach(function (c) { chMap[c.code] = c; });

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var state = { filter: 'all', q: '', list: items.slice(), index: -1 };

  /* ---------------- 顶栏 & 进度 ---------------- */
  var topbar = $('#topbar');
  var progress = $('#progress');

  function onScroll() {
    var y = window.scrollY || document.documentElement.scrollTop;
    topbar.classList.toggle('is-stuck', y > 60);
    var h = document.documentElement.scrollHeight - window.innerHeight;
    progress.style.width = (h > 0 ? (y / h) * 100 : 0) + '%';
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* ---------------- 篇章卡片 ---------------- */
  function countOf(code) {
    return items.filter(function (i) { return i.ch === code; }).length;
  }

  var CH_GRAD = {
    'A-01': 'linear-gradient(135deg,#9B3A3A 0%,#6E3348 46%,#3A2E5E 100%)',
    'A-02': 'linear-gradient(135deg,#454478 0%,#2A3270 55%,#1C2B62 100%)',
    'A-03': 'linear-gradient(135deg,#1C2B62 0%,#243A72 60%,#33507F 100%)',
    'A-04': 'linear-gradient(135deg,#6E3A55 0%,#4B3468 55%,#2A2E63 100%)',
    'A-05': 'linear-gradient(135deg,#8E3A44 0%,#63354F 52%,#3B2E5C 100%)',
    'B-01': 'linear-gradient(135deg,#993333 0%,#6E2F42 55%,#4A2740 100%)',
    'B-02': 'linear-gradient(135deg,#2E3A6B 0%,#222F62 60%,#1C2B62 100%)'
  };

  function renderChapters() {
    var wrap = $('#chapterGrid');
    wrap.innerHTML = chapters.map(function (c, i) {
      return '' +
        '<button class="chapter" data-ch="' + c.code + '" style="--i:' + i + '">' +
          '<span class="chapter__bg" style="background:' + (CH_GRAD[c.code] || '') + '"></span>' +
          '<img class="chapter__mark" src="assets/img/brand/emblem.webp" alt="" aria-hidden="true">' +
          '<span class="chapter__veil"></span>' +
          '<span class="chapter__count">' + String(countOf(c.code)).padStart(2, '0') + ' 项</span>' +
          '<span class="chapter__no">' + c.code + '</span>' +
          '<span class="chapter__cn">' + c.cn + '</span>' +
          '<span class="chapter__en">' + c.en + '</span>' +
          '<span class="chapter__intro">' + c.intro + '</span>' +
        '</button>';
    }).join('');

    $$('.chapter', wrap).forEach(function (el) {
      el.addEventListener('click', function () {
        var code = el.getAttribute('data-ch');
        setFilter(code);
        document.getElementById('catalog').scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  }

  /* ---------------- 筛选 chips ---------------- */
  function renderChips() {
    var wrap = $('#chips');
    var html = '<button class="chip" role="tab" data-ch="all" aria-selected="true">' +
      '<span>ALL</span>全部 <b>' + items.length + '</b></button>';
    html += chapters.map(function (c) {
      return '<button class="chip" role="tab" data-ch="' + c.code + '" aria-selected="false">' +
        '<span>' + c.code + '</span>' + c.cn + '</button>';
    }).join('');
    wrap.innerHTML = html;

    $$('.chip', wrap).forEach(function (el) {
      el.addEventListener('click', function () {
        setFilter(el.getAttribute('data-ch'));
      });
    });
  }

  function setFilter(code) {
    state.filter = code;
    $$('#chips .chip').forEach(function (el) {
      el.setAttribute('aria-selected', String(el.getAttribute('data-ch') === code));
    });
    apply();
  }

  /* ---------------- 列表 ---------------- */
  var io = null;
  if ('IntersectionObserver' in window) {
    io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add('in');
          io.unobserve(e.target);
        }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });
  }

  function match(it, q) {
    if (!q) return true;
    var hay = (it.code + ' ' + it.cn + ' ' + it.en + ' ' + it.desc + ' ' +
      it.att.map(function (a) { return a[0] + a[1]; }).join(' ')).toLowerCase();
    return q.split(/\s+/).every(function (w) { return hay.indexOf(w) > -1; });
  }

  function apply() {
    var q = state.q.trim().toLowerCase();
    state.list = items.filter(function (it) {
      return (state.filter === 'all' || it.ch === state.filter) && match(it, q);
    });
    renderGrid();
    var res = $('#result');
    var chName = state.filter === 'all' ? '全部篇章' : (chMap[state.filter] ? chMap[state.filter].cn : '');
    res.innerHTML = '<b>' + state.list.length + '</b> 项规范 · ' + chName +
      (q ? ' · 检索「' + escapeHtml(state.q.trim()) + '」' : '');
    $('#empty').hidden = state.list.length > 0;
  }

  function renderGrid() {
    var grid = $('#grid');
    grid.innerHTML = state.list.map(function (it, i) {
      var thumb = it.imgs[0] || '';
      var multi = '<span class="card__ch">' + it.ch + '</span>';
      var codeExtra = it.imgs.length > 1 ? '<i>+' + (it.imgs.length - 1) + '</i>' : '';
      return '' +
        '<button class="card" data-i="' + items.indexOf(it) + '" style="transition-delay:' +
          Math.min(i * 18, 260) + 'ms">' +
          '<span class="card__thumb"><img src="' + thumb + '" alt="' + escapeHtml(it.cn) +
            '" loading="lazy" decoding="async"></span>' +
          '<span class="card__body">' +
            '<span class="card__top"><span class="card__code">' + it.code + codeExtra + '</span>' + multi + '</span>' +
            '<span class="card__cn">' + it.cn + '</span>' +
            '<span class="card__en">' + it.en + '</span>' +
            '<span class="card__more">查看图版' +
              '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"></path></svg>' +
            '</span>' +
          '</span>' +
        '</button>';
    }).join('');

    $$('.card', grid).forEach(function (el) {
      if (io) io.observe(el); else el.classList.add('in');
      el.addEventListener('click', function () {
        openDrawer(parseInt(el.getAttribute('data-i'), 10));
      });
    });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ---------------- 检索 ---------------- */
  var search = $('#search');
  var clearBtn = $('#searchClear');

  search.addEventListener('input', function () {
    state.q = search.value;
    clearBtn.hidden = !state.q;
    apply();
  });
  clearBtn.addEventListener('click', function () {
    search.value = ''; state.q = ''; clearBtn.hidden = true; apply(); search.focus();
  });
  $('#searchJump').addEventListener('click', function () {
    document.getElementById('catalog').scrollIntoView({ behavior: 'smooth' });
    setTimeout(function () { search.focus(); }, 420);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement !== search) {
      e.preventDefault();
      document.getElementById('catalog').scrollIntoView({ behavior: 'smooth' });
      setTimeout(function () { search.focus(); }, 380);
    }
  });

  /* ---------------- 抽屉 ---------------- */
  var drawer = $('#drawer');
  var backdrop = $('#backdrop');
  var body = $('#drawerBody');
  var lastFocus = null;

  function openDrawer(i) {
    var it = items[i];
    if (!it) return;
    state.index = i;
    lastFocus = document.activeElement;

    var ch = chMap[it.ch] || { cn: it.ch, code: it.ch };
    var figs = it.imgs.map(function (src, k) {
      return '<figure><img src="' + src + '" alt="' + escapeHtml(it.cn) + ' 图 ' + (k + 1) +
        '" loading="lazy" decoding="async">' +
        (it.imgs.length > 1 ? '<figcaption>图 ' + (k + 1) + ' / ' + it.imgs.length + '</figcaption>' : '') +
        '</figure>';
    }).join('');

    var atts = it.att.map(function (a) {
      return '<div class="detail__att"><dt>' + escapeHtml(a[0]) + '</dt><dd>' +
        escapeHtml(a[1]) + '</dd></div>';
    }).join('');

    body.innerHTML = '' +
      '<div class="detail__head">' +
        '<p class="detail__ch">' + ch.code + ' · ' + ch.cn + '</p>' +
        '<h2 class="detail__title" id="drawerTitle">' + it.cn + '</h2>' +
        '<p class="detail__en">' + it.en + '</p>' +
      '</div>' +
      '<div class="detail__figs">' + figs + '</div>' +
      (it.desc ? '<div class="detail__block"><p class="detail__label"><b>信息释义</b> Information</p>' +
        '<p class="detail__desc">' + escapeHtml(it.desc) + '</p></div>' : '') +
      (atts ? '<div class="detail__block"><p class="detail__label"><b>注意事项</b> Attention</p>' +
        '<dl class="detail__atts">' + atts + '</dl></div>' : '') +
      '<div class="detail__pager">' +
        '<button type="button" data-go="-1"><span>上一个</span>' + prevName(-1) + '</button>' +
        '<button type="button" data-go="1"><span>下一个</span>' + prevName(1) + '</button>' +
      '</div>';

    $('#drawerNo').textContent = it.code + '  ·  ' + pad(i + 1) + '/' + pad(items.length);

    $$('.detail__pager button', body).forEach(function (b) {
      b.addEventListener('click', function () { step(parseInt(b.getAttribute('data-go'), 10)); });
    });

    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    backdrop.hidden = false;
    requestAnimationFrame(function () { backdrop.classList.add('show'); });
    document.body.style.overflow = 'hidden';
    body.scrollTop = 0;
    $('#close').focus();
  }

  function prevName(dir) {
    var n = state.index + dir;
    return items[n] ? escapeHtml(items[n].cn) : '—';
  }

  function pad(n) { return String(n).padStart(2, '0'); }

  function step(dir) {
    var n = state.index + dir;
    if (n < 0 || n >= items.length) return;
    openDrawer(n);
  }

  function closeDrawer() {
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    backdrop.classList.remove('show');
    document.body.style.overflow = '';
    setTimeout(function () { backdrop.hidden = true; }, 380);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  $('#close').addEventListener('click', closeDrawer);
  backdrop.addEventListener('click', closeDrawer);

  document.addEventListener('keydown', function (e) {
    if (!drawer.classList.contains('open')) return;
    if (e.key === 'Escape') closeDrawer();
    if (e.key === 'ArrowLeft') step(-1);
    if (e.key === 'ArrowRight') step(1);
  });


  /* ---------------- 下载 ---------------- */
  var DL_ICON = {
    pdf: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"></path><path d="M14 3v5h5"></path><path d="M9 13h6M9 17h4"></path></svg>',
    zip: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"></path><path d="M2 3h20v4H2z"></path><path d="M10 11h4v4h-4z"></path></svg>',
    cloud: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 18a4 4 0 0 1-.6-8 5.5 5.5 0 0 1 10.6-1.3A3.8 3.8 0 0 1 17.5 18"></path><path d="M12 12v7M9 16l3 3 3-3"></path></svg>'
  };

  function renderDownloads() {
    var list = DATA.downloads || [];
    var wrap = $('#dlGrid');
    if (!wrap) return;
    wrap.innerHTML = list.map(function (d) {
      var has = !!d.href;
      var attrs = has
        ? ' href="' + d.href + '"' + (d.kind === 'cloud'
            ? ' target="_blank" rel="noopener"'
            : ' download="' + d.file + '"')
        : ' aria-disabled="true"';
      var tag = has ? 'a' : 'div';
      return '<' + tag + ' class="dl dl--' + d.kind + (has ? '' : ' is-disabled') + '"' + attrs + '>' +
          '<span class="dl__icon">' + (DL_ICON[d.kind] || DL_ICON.pdf) + '</span>' +
          '<span class="dl__title">' + d.title + '</span>' +
          '<span class="dl__meta">' + d.meta + '</span>' +
          '<span class="dl__desc">' + d.desc + '</span>' +
          '<span class="dl__action">' + d.action +
            (has ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 11l5 5 5-5M5 20h14"></path></svg>' : '') +
          '</span>' +
        '</' + tag + '>';
    }).join('');
  }

  /* ---------------- 启动 ---------------- */
  renderChapters();
  renderChips();
  apply();
  renderDownloads();
})();

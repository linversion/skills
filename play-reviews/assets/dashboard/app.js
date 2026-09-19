/* Play 评论情报查看器 — 零依赖, 读取 window.REVIEWS_DATA 或接受拖入的 CSV */
(function () {
  "use strict";

  var COUNTRY_NAMES = {
    us: "美国", gb: "英国", ca: "加拿大", au: "澳大利亚", de: "德国", fr: "法国",
    jp: "日本", kr: "韩国", nl: "荷兰", se: "瑞典", it: "意大利", es: "西班牙",
    br: "巴西", in: "印度", mx: "墨西哥", ru: "俄罗斯", tr: "土耳其", id: "印尼",
    vn: "越南", th: "泰国", ph: "菲律宾", my: "马来西亚", sg: "新加坡", hk: "香港",
    tw: "台湾", ch: "瑞士", at: "奥地利", be: "比利时", dk: "丹麦", fi: "芬兰",
    no: "挪威", pl: "波兰", pt: "葡萄牙", ie: "爱尔兰", nz: "新西兰", za: "南非",
    ae: "阿联酋", sa: "沙特", ar: "阿根廷", cl: "智利", co: "哥伦比亚",
    eg: "埃及", ng: "尼日利亚"
  };
  var SCORE_COLORS = { 5: "#2f7d50", 4: "#7fa04b", 3: "#c6962e", 2: "#cd6a2c", 1: "#b83a2b" };
  var STARS = { 1: "★", 2: "★★", 3: "★★★", 4: "★★★★", 5: "★★★★★" };

  var state = {
    data: null,
    apps: [],
    scores: new Set(),
    regions: new Set(),
    needReply: false,
    q: "",
    sort: "newest",
    days: 0,
    from: "",
    to: "",
    offline: false,
    inlineApps: []
  };

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function regionCodes(r) { return (r.countries || "").split("|").filter(Boolean); }
  function regionLabel(code) { return (COUNTRY_NAMES[code] ? COUNTRY_NAMES[code] + " " : "") + code.toUpperCase(); }

  /* ---------- 数据装载 ---------- */
  function setData(payload) {
    state.data = payload;
    state.scores = new Set();
    state.regions = new Set();
    state.needReply = false;
    state.q = "";
    state.sort = "newest";
    state.days = 0;
    state.from = "";
    state.to = "";
    $("search").value = "";
    $("sort").value = "newest";
    $("date-from").value = "";
    $("date-to").value = "";
    $("reply-btn").setAttribute("aria-pressed", "false");
    renderAll();
    refreshTimeUI();
    try {
      localStorage.setItem("playReviewsLastApp", payload.app_id || "");
      var tier = localStorage.getItem("playReviewsTier:" + (payload.app_id || ""));
      if (tier) $("tier-sel").value = tier;
    } catch (e) {}
    syncAppSel();
  }

  /* ---------- 多应用切换 ---------- */
  function safeId(appId) { return String(appId).replace(/[^A-Za-z0-9._-]/g, "_"); }

  function renderAppSel() {
    var sel = $("app-sel");
    sel.innerHTML = "";
    var apps = state.apps || [];
    sel.style.display = apps.length ? "" : "none";
    apps.forEach(function (a) {
      var opt = new Option((a.title || a.app_id) + " · " + a.total + " 条", a.app_id);
      sel.add(opt);
    });
    if (state.data) sel.value = state.data.app_id;
  }

  function syncAppSel() {
    var sel = $("app-sel");
    if (sel && state.data) sel.value = state.data.app_id;
  }

  function refreshApps() {
    return fetch("apps/index.json", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) {
        state.apps = data.apps || [];
        renderAppSel();
      })
      .catch(function () {});
  }

  function inlineData(appId) {
    var e = (state.inlineApps || []).filter(function (a) { return a.app_id === appId; })[0];
    return e ? e.data : null;
  }

  function loadApp(appId) {
    if (state.offline) {
      var p = inlineData(appId);
      if (p) {
        setData(p);
        setFetchStatus("✓ 已切换 " + (p.title || appId) + " · " + p.reviews.length + " 条");
      } else {
        setFetchStatus("内联数据中无 " + appId, true);
      }
      return;
    }
    setFetchStatus("加载 " + appId + " …");
    return fetch("apps/" + safeId(appId) + ".json", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (payload) {
        setData(payload);
        setFetchStatus("✓ 已切换 " + (payload.title || payload.app_id) + " · " + payload.reviews.length + " 条");
      })
      .catch(function (err) {
        setFetchStatus("加载失败: " + (err && err.message ? err.message : err), true);
      });
  }

  /* ---------- 统计 ---------- */
  function computeStats(reviews) {
    var total = reviews.length, sum = 0, latest = "";
    var byScore = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
    var byRegion = new Map(); // code -> count
    var replies = 0;
    for (var i = 0; i < total; i++) {
      var r = reviews[i];
      sum += r.score;
      if (byScore[r.score] != null) byScore[r.score]++;
      var codes = regionCodes(r);
      for (var j = 0; j < codes.length; j++) {
        byRegion.set(codes[j], (byRegion.get(codes[j]) || 0) + 1);
      }
      if (r.replyContent) replies++;
      if (r.at && r.at > latest) latest = r.at;
    }
    return {
      total: total, avg: total ? (sum / total) : 0, byScore: byScore,
      regions: byRegion, replies: replies, latest: latest ? latest.slice(0, 10) : "—"
    };
  }

  function poolAnnotation(reviews) {
    // 找出返回完全相同评论集的地区 (同语言池), 返回 Map code -> poolKey
    var byCode = new Map();
    for (var i = 0; i < reviews.length; i++) {
      var codes = regionCodes(reviews[i]);
      for (var j = 0; j < codes.length; j++) {
        if (!byCode.has(codes[j])) byCode.set(codes[j], new Set());
        byCode.get(codes[j]).add(reviews[i].reviewId);
      }
    }
    var sig = new Map();
    byCode.forEach(function (ids, code) {
      var key = ids.size + ":" + Array.from(ids).slice(0, 50).sort().join(",");
      if (!sig.has(key)) sig.set(key, []);
      sig.get(key).push(code);
    });
    var codePool = new Map(), pools = [];
    sig.forEach(function (codes) {
      if (codes.length > 1) {
        pools.push(codes);
        for (var i = 0; i < codes.length; i++) codePool.set(codes[i], pools.length - 1);
      }
    });
    return { codePool: codePool, pools: pools };
  }

  /* ---------- 渲染 ---------- */
  function renderAll() {
    if (!state.data || !state.data.reviews) { renderSetup(); return; }
    renderHead();
    renderScoreBar();
    renderScorePanel();
    renderRegions();
    renderList();
  }

  function renderSetup() {
    $("app-id").textContent = "尚未加载数据";
    $("app-src").textContent = "";
    $("ledger").innerHTML = "";
    $("score-bar").innerHTML = "";
    $("score-legend").innerHTML = "";
    $("region-list").innerHTML = "";
    $("pool-note").textContent = "";
    $("review-list").innerHTML =
      '<div class="empty-state"><div class="big">把评论 CSV 拖进本页面</div>' +
      "或先运行 scripts/scrape_play_reviews.py 抓取,<br>" +
      "再用 scripts/csv_to_reviews_js.py 生成 data.js 后刷新。</div>";
  }

  function renderHead() {
    var d = state.data;
    var stats = computeStats(d.reviews);
    $("app-id").textContent = d.title || d.app_id || "未知应用";
    $("app-src").textContent = (d.app_id ? d.app_id + " · " : "") + (d.generated_at ? "DATA " + d.generated_at : "");
    $("head-meta").textContent = "REVIEW LEDGER · " + stats.total + " ENTRIES";
    var pool = poolAnnotation(d.reviews);
    var pooledCodes = 0;
    pool.pools.forEach(function (cs) { pooledCodes += cs.length; });
    var poolCount = pool.pools.length + (stats.regions.size - pooledCodes);
    var items = [
      { num: stats.total, label: "去重评论" },
      { num: stats.avg.toFixed(2), label: "平均评分", small: " / 5" },
      { num: poolCount, label: "语言池", small: " · " + stats.regions.size + " 国" },
      { num: stats.replies, label: "开发者回复" },
      { num: stats.latest, label: "最新评论", mono: true }
    ];
    $("ledger").innerHTML = items.map(function (it) {
      return '<div class="ledger-item"><div class="ledger-num">' +
        (it.mono ? '<span style="font-family:var(--font-mono);font-size:22px;font-weight:500">' + esc(it.num) + "</span>" : esc(String(it.num)) + (it.small ? "<small>" + it.small + "</small>" : "")) +
        '</div><div class="ledger-label">' + esc(it.label) + "</div></div>";
    }).join("");
    $("pool-note").__pools = pool.pools;
  }

  function renderScoreBar() {
    var stats = computeStats(contextReviews({ score: true }));
    var bar = $("score-bar"), legend = $("score-legend");
    bar.innerHTML = "";
    legend.innerHTML = "";
    for (var s = 5; s >= 1; s--) {
      (function (score) {
        var n = stats.byScore[score];
        var seg = document.createElement("button");
        seg.className = "score-seg" + (state.scores.size && !state.scores.has(score) ? " off" : "");
        seg.style.flexGrow = String(Math.max(n, 0.35));
        seg.style.background = SCORE_COLORS[score];
        seg.textContent = n ? String(n) : "";
        seg.title = score + " 星 · " + n + " 条";
        seg.setAttribute("aria-pressed", state.scores.has(score) ? "true" : "false");
        seg.addEventListener("click", function () { toggleScore(score); });
        bar.appendChild(seg);

        var chip = document.createElement("button");
        chip.className = "legend-chip" + (state.scores.size && !state.scores.has(score) ? " off" : "");
        chip.innerHTML = '<span class="dot" style="background:' + SCORE_COLORS[score] + '"></span>' +
          score + " 星 <b>" + n + "</b>";
        chip.addEventListener("click", function () { toggleScore(score); });
        legend.appendChild(chip);
      })(s);
    }
  }

  function renderScorePanel() {
    var stats = computeStats(contextReviews({ score: true }));
    var box = $("score-panel");
    box.innerHTML = "";
    for (var s = 5; s >= 1; s--) {
      (function (score) {
        var btn = document.createElement("button");
        btn.className = "score-row";
        btn.setAttribute("aria-pressed", state.scores.has(score) ? "true" : "false");
        btn.title = "只看 " + score + " 星评论 (再点一次取消)";
        btn.innerHTML = '<span class="stars s' + score + '">' + (STARS[score] || "") + "</span>" +
          "<span>" + score + " 星</span>" +
          '<span class="n">' + stats.byScore[score] + "</span>";
        btn.addEventListener("click", function () { toggleScore(score); });
        box.appendChild(btn);
      })(s);
    }
    if (state.scores.size) {
      var hint = document.createElement("p");
      hint.className = "pool-note";
      hint.textContent = "已选 " + state.scores.size + " 个星级 (多选=并集)";
      box.appendChild(hint);
    }
  }

  function renderRegions() {
    var stats = computeStats(contextReviews({ region: true }));
    var pool = poolAnnotation(state.data.reviews);
    var list = $("region-list");
    list.innerHTML = "";
    var codes = Array.from(stats.regions.keys()).sort(function (a, b) {
      return stats.regions.get(b) - stats.regions.get(a);
    });
    codes.forEach(function (code) {
      var btn = document.createElement("button");
      btn.className = "region-chip";
      btn.setAttribute("aria-pressed", state.regions.has(code) ? "true" : "false");
      var poolTag = pool.codePool.has(code) ? " ≈" : "";
      btn.innerHTML = '<span class="code">' + esc(code.toUpperCase()) + "</span>" +
        '<span>' + esc(COUNTRY_NAMES[code] || "") + poolTag + "</span>" +
        '<span class="n">' + stats.regions.get(code) + "</span>";
      btn.title = regionLabel(code);
      btn.addEventListener("click", function () { toggleRegion(code); });
      list.appendChild(btn);
    });
    var note = $("pool-note");
    if (pool.pools.length) {
      note.innerHTML = "≈ 同一评论池(评论集完全相同):<br>" + pool.pools.map(function (codes) {
        return "<b>" + codes.map(function (c) { return c.toUpperCase(); }).join(" ≈ ") + "</b>";
      }).join("<br>");
    } else {
      note.textContent = "";
    }
  }

  function highlight(text) {
    var safe = esc(text);
    if (!state.q) return safe;
    var q = esc(state.q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return safe.replace(new RegExp(q, "gi"), function (m) { return "<mark>" + m + "</mark>"; });
  }

  function inDateRange(r) {
    var d = String(r.at || "").slice(0, 10);
    if (state.from && (!d || d < state.from)) return false;
    if (state.to && (!d || d > state.to)) return false;
    return true;
  }

  // skip 传 {score:true} / {region:true} 时跳过该维度, 用于"其余筛选下的分布"上下文统计
  function matchesFilters(r, skip) {
    skip = skip || {};
    var q = state.q.trim().toLowerCase();
    if (!skip.score && state.scores.size && !state.scores.has(r.score)) return false;
    if (state.needReply && !r.replyContent) return false;
    if (!skip.region && state.regions.size) {
      var codes = regionCodes(r), hit = false;
      for (var i = 0; i < codes.length; i++) if (state.regions.has(codes[i])) { hit = true; break; }
      if (!hit) return false;
    }
    if (!inDateRange(r)) return false;
    if (q && !((r.content || "").toLowerCase().includes(q) || (r.userName || "").toLowerCase().includes(q))) return false;
    return true;
  }

  function contextReviews(skip) {
    return state.data && state.data.reviews
      ? state.data.reviews.filter(function (r) { return matchesFilters(r, skip); })
      : [];
  }

  function filteredReviews() {
    var out = state.data.reviews.filter(function (r) { return matchesFilters(r); });
    out.sort(function (a, b) {
      switch (state.sort) {
        case "highest": return b.score - a.score || (b.thumbsUpCount - a.thumbsUpCount);
        case "lowest": return a.score - b.score || (b.thumbsUpCount - a.thumbsUpCount);
        case "thumbs": return (b.thumbsUpCount - a.thumbsUpCount) || String(b.at).localeCompare(String(a.at));
        default: return String(b.at).localeCompare(String(a.at));
      }
    });
    return out;
  }

  function renderList() {
    var rows = filteredReviews();
    $("count-line").textContent = "已显示 " + rows.length + " / " + state.data.reviews.length;
    var box = $("review-list");
    if (!rows.length) {
      box.innerHTML = '<div class="empty-state"><div class="big">没有匹配的评论</div>试试放宽筛选条件</div>';
      return;
    }
    var html = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var codes = regionCodes(r);
      var tags = codes.map(function (c) {
        return '<span class="region-tag' + (c === r.primary_country ? " primary" : "") + '">' + esc(c.toUpperCase()) + "</span>";
      }).join("");
      html.push(
        '<article class="review">' +
          '<div class="r-top">' +
            '<span class="score-chip s' + r.score + '"><span aria-hidden="true">' + (STARS[r.score] || "") + "</span><span class=\"n\">" + r.score + "</span></span>" +
            '<span class="region-tags">' + tags + "</span>" +
            '<span class="r-meta">' +
              (r.reviewCreatedVersion ? '<span class="ver">v' + esc(r.reviewCreatedVersion) + "</span>" : "") +
              (r.thumbsUpCount ? "<span>▲ " + r.thumbsUpCount + "</span>" : "") +
              "<time>" + esc(String(r.at || "").slice(0, 10)) + "</time>" +
            "</span>" +
          "</div>" +
          '<p class="r-body" lang="">' + highlight(r.content || "") + "</p>" +
          (r.userName ? '<div class="r-user">— ' + highlight(r.userName) + "</div>" : "") +
          (r.replyContent
            ? '<div class="r-reply"><div class="reply-label">开发者回复 · ' + esc(String(r.repliedAt || "").slice(0, 10)) + "</div>" +
              '<div class="reply-body">' + esc(r.replyContent) + "</div></div>"
            : "") +
        "</article>"
      );
    }
    box.innerHTML = html.join("");
  }

  /* ---------- 交互 ---------- */
  function toggleScore(score) {
    if (state.scores.has(score)) state.scores.delete(score); else state.scores.add(score);
    reRenderPanels();
  }
  function toggleRegion(code) {
    if (state.regions.has(code)) state.regions.delete(code); else state.regions.add(code);
    reRenderPanels();
  }

  $("search").addEventListener("input", function (e) { state.q = e.target.value; reRenderPanels(); });
  $("sort").addEventListener("change", function (e) { state.sort = e.target.value; renderList(); });
  $("reply-btn").addEventListener("click", function () {
    state.needReply = !state.needReply;
    this.setAttribute("aria-pressed", state.needReply ? "true" : "false");
    reRenderPanels();
  });
  /* ---------- 时间范围筛选 ---------- */
  function refreshTimeUI() {
    var mode = state.days === "custom" ? "custom" : String(state.days);
    document.querySelectorAll("#time-chips .chip").forEach(function (c) {
      c.classList.toggle("on", c.getAttribute("data-days") === mode);
    });
    var dr = $("date-range");
    if (state.days === "custom") {
      dr.hidden = false;
      if (!$("date-from").value && state.from) $("date-from").value = state.from;
      if (!$("date-to").value && state.to) $("date-to").value = state.to;
    } else {
      dr.hidden = true;
    }
  }

  function reRenderPanels() {
    renderScoreBar(); renderScorePanel(); renderRegions(); renderList();
  }

  $("time-chips").addEventListener("click", function (e) {
    var btn = e.target.closest(".chip");
    if (!btn) return;
    var v = btn.getAttribute("data-days");
    if (v === "custom") {
      state.days = "custom";
      if (!state.from) {
        var t = new Date();
        t.setDate(t.getDate() - 30);
        state.from = t.toISOString().slice(0, 10);
      }
    } else {
      var days = parseInt(v, 10);
      state.days = days;
      state.from = "";
      state.to = "";
      if (days > 0) {
        var t2 = new Date();
        t2.setDate(t2.getDate() - days);
        state.from = t2.toISOString().slice(0, 10);
      }
      $("date-from").value = state.from;
      $("date-to").value = state.to;
    }
    refreshTimeUI();
    reRenderPanels();
  });

  $("date-from").addEventListener("change", function () {
    state.from = this.value || "";
    reRenderPanels();
  });
  $("date-to").addEventListener("change", function () {
    state.to = this.value || "";
    reRenderPanels();
  });

  /* ---------- 导出 (当前筛选所见) ---------- */
  var EXPORT_COLS = ["reviewId", "countries", "primary_country", "score", "content",
    "reviewCreatedVersion", "at", "thumbsUpCount", "userName", "replyContent", "repliedAt"];

  function csvCell(v) {
    var s = String(v == null ? "" : v);
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  function filterDescriptor() {
    var parts = [];
    if (state.scores.size) parts.push(Array.from(state.scores).sort().join("+") + "星");
    if (state.regions.size) parts.push(Array.from(state.regions).map(function (c) { return c.toUpperCase(); }).join("+"));
    if (state.days === "custom") parts.push((state.from || "…") + "~" + (state.to || "…"));
    else if (state.days > 0) parts.push("近" + state.days + "天");
    if (state.needReply) parts.push("有回复");
    if (state.q.trim()) parts.push('搜"' + state.q.trim() + '"');
    return parts.length ? parts.join("·") : "全部";
  }

  $("export-csv-btn").addEventListener("click", function () {
    var rows = filteredReviews();
    var lines = [EXPORT_COLS.join(",")];
    rows.forEach(function (r) {
      lines.push(EXPORT_COLS.map(function (c) { return csvCell(r[c]); }).join(","));
    });
    var name = String((state.data && (state.data.title || state.data.app_id)) || "reviews")
      .replace(/[\\/:*?"<>|\s]+/g, "_");
    var blob = new Blob(["\uFEFF" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name + "_" + filterDescriptor() + "_" + new Date().toISOString().slice(0, 10) + ".csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 3000);
    setFetchStatus("✓ 已导出 " + rows.length + " 条 CSV（" + filterDescriptor() + "）");
  });

  function legacyCopy(text, done) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      done();
    } catch (e) {
      setFetchStatus("复制失败, 请手动选择", true);
    }
    ta.remove();
  }

  $("copy-btn").addEventListener("click", function () {
    var rows = filteredReviews();
    var d = state.data || {};
    var lines = [(d.title || d.app_id || "") + " · " + rows.length + " 条 · 筛选: " + filterDescriptor() + " · 数据 " + (d.generated_at || "")];
    lines.push("────────────────");
    rows.forEach(function (r) {
      var codes = regionCodes(r).map(function (c) { return c.toUpperCase(); }).join(",");
      lines.push(r.score + "★ " + String(r.at || "").slice(0, 10) + (codes ? " [" + codes + "]" : "") + " " + (r.content || ""));
      if (r.replyContent) lines.push("  ↳ 回复: " + r.replyContent);
    });
    var text = lines.join("\n");
    function done() { setFetchStatus("✓ 已复制 " + rows.length + " 条文本, 可直接粘贴"); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { legacyCopy(text, done); });
    } else {
      legacyCopy(text, done);
    }
  });

  $("reset-btn").addEventListener("click", function () {
    state.scores.clear(); state.regions.clear(); state.needReply = false; state.q = "";
    state.days = 0; state.from = ""; state.to = "";
    $("search").value = "";
    $("date-from").value = "";
    $("date-to").value = "";
    $("reply-btn").setAttribute("aria-pressed", "false");
    refreshTimeUI();
    renderScoreBar(); renderScorePanel(); renderRegions(); renderList();
  });

  /* ---------- 拉取最新 (需要 serve_reviews.py 提供的 /api/scrape) ---------- */
  var fetchBtn = $("fetch-btn");
  var fetchStatus = $("fetch-status");

  function setFetchStatus(msg, isErr) {
    fetchStatus.textContent = msg;
    fetchStatus.classList.toggle("err", !!isErr);
  }

  fetchBtn.addEventListener("click", function () {
    if (state.offline) { setFetchStatus("离线模式不可拉取 — 请经服务器启动页面", true); return; }
    if (!state.data || !state.data.app_id) { setFetchStatus("请先加载数据", true); return; }
    var appId = state.data.app_id;
    fetchBtn.disabled = true;
    fetchBtn.classList.add("busy");
    fetchBtn.querySelector(".label").textContent = "抓取中…";
    setFetchStatus("连接服务器…");

    var ctrl = new AbortController();
    var tier = ($("tier-sel") && $("tier-sel").value) || "t1";
    fetch("/api/scrape?app=" + encodeURIComponent(appId) + "&tier=" + tier, { signal: ctrl.signal })
      .then(function (res) {
        if (!res.ok || !res.body) throw new Error("HTTP " + res.status + " — 请用 scripts/serve_reviews.py 启动页面");
        var reader = res.body.getReader();
        var dec = new TextDecoder();
        var buf = "";
        function pump() {
          return reader.read().then(function (chunk) {
            if (chunk.done) return;
            buf += dec.decode(chunk.value, { stream: true });
            var idx;
            while ((idx = buf.indexOf("\n")) >= 0) {
              var line = buf.slice(0, idx).trim();
              buf = buf.slice(idx + 1);
              if (!line) continue;
              var msg;
              try { msg = JSON.parse(line); } catch (e) { continue; }
              if (msg.type === "start") {
                setFetchStatus(msg.tier.toUpperCase() + " · " + msg.markets + " 国抓取中…");
              } else if (msg.type === "progress") {
                setFetchStatus(msg.error
                  ? msg.country + " 失败: " + msg.error.slice(0, 40)
                  : msg.country.toUpperCase() + " +" + msg.new + " · 累计 " + msg.total);
              } else if (msg.type === "fatal") {
                throw new Error(msg.message);
              } else if (msg.type === "done") {
                setData(msg.payload);
                setFetchStatus("✓ 已更新 " + msg.payload.reviews.length + " 条");
                refreshApps();
              }
            }
            return pump();
          });
        }
        return pump();
      })
      .catch(function (err) {
        if (err && err.name === "AbortError") { setFetchStatus("已取消"); return; }
        setFetchStatus("抓取失败: " + (err && err.message ? err.message : err), true);
      })
      .then(function () {
        fetchBtn.disabled = false;
        fetchBtn.classList.remove("busy");
        fetchBtn.querySelector(".label").textContent = "⟳ 拉取最新";
      });
  });

  /* ---------- CSV 拖放 ---------- */
  function parseCSV(text) {
    text = text.replace(/^\uFEFF/, "");
    var rows = [], row = [], field = "", inQ = false;
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (inQ) {
        if (ch === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; } else inQ = false;
        } else field += ch;
      } else if (ch === '"') inQ = true;
      else if (ch === ",") { row.push(field); field = ""; }
      else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && text[i + 1] === "\n") i++;
        row.push(field); field = "";
        if (row.length > 1 || row[0] !== "") rows.push(row);
        row = [];
      } else field += ch;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    return rows.filter(function (r) { return r.length > 1 || (r[0] && r[0] !== ""); });
  }

  function csvToPayload(text, name) {
    var rows = parseCSV(text);
    if (rows.length < 2) return null;
    var head = rows[0].map(function (h) { return h.trim(); });
    var idx = {};
    head.forEach(function (h, i) { idx[h] = i; });
    if (idx.reviewId == null && idx.content == null) return null;
    function col(r, k) { return idx[k] != null ? (r[idx[k]] || "") : ""; }
    var reviews = [];
    for (var i = 1; i < rows.length; i++) {
      var r = rows[i];
      if (!col(r, "reviewId") && !col(r, "content")) continue;
      reviews.push({
        reviewId: col(r, "reviewId"),
        countries: col(r, "countries"),
        primary_country: col(r, "primary_country"),
        score: parseInt(col(r, "score"), 10) || 0,
        content: col(r, "content"),
        reviewCreatedVersion: col(r, "reviewCreatedVersion"),
        at: col(r, "at"),
        thumbsUpCount: parseInt(col(r, "thumbsUpCount"), 10) || 0,
        userName: col(r, "userName"),
        replyContent: col(r, "replyContent"),
        repliedAt: col(r, "repliedAt")
      });
    }
    return { app_id: name.replace(/\.csv$/i, "").replace(/_/g, "."), source_csv: name, generated_at: "", reviews: reviews };
  }

  var overlay = $("drop-overlay");
  var dragDepth = 0;
  document.addEventListener("dragenter", function (e) { e.preventDefault(); dragDepth++; overlay.classList.add("on"); });
  document.addEventListener("dragover", function (e) { e.preventDefault(); });
  document.addEventListener("dragleave", function (e) { e.preventDefault(); if (--dragDepth <= 0) { dragDepth = 0; overlay.classList.remove("on"); } });
  document.addEventListener("drop", function (e) {
    e.preventDefault(); dragDepth = 0; overlay.classList.remove("on");
    var file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () {
      var payload = csvToPayload(String(reader.result), file.name);
      if (payload && payload.reviews.length) setData(payload);
      else alert("无法解析该文件 — 请拖入 scrape_play_reviews.py 导出的 CSV");
    };
    reader.readAsText(file, "utf-8");
  });

  /* ---------- 启动: 服务器索引 → data.js 内联多包 (file://) → 单包回退 ---------- */
  function bootFromInline() {
    var ra = window.REVIEWS_APPS;
    if (ra && ra.apps && ra.apps.length) {
      state.offline = true;
      state.inlineApps = ra.apps;
      state.apps = ra.apps.map(function (a) {
        return { app_id: a.app_id, title: a.title, total: a.total, generated_at: a.generated_at };
      });
      renderAppSel();
      $("offline-banner").hidden = false;
      var fb = $("fetch-btn");
      fb.disabled = true;
      fb.title = "离线模式不可用 — 请经服务器启动页面";
      var last = null;
      try { last = localStorage.getItem("playReviewsLastApp"); } catch (e) {}
      var pick = state.apps.filter(function (a) { return a.app_id === last; })[0] || state.apps[0];
      var p = inlineData(pick.app_id);
      if (p) setData(p);
      setFetchStatus("离线模式 · 数据截至 " + ((pick && pick.generated_at) || "最近一次抓取"));
      return;
    }
    if (window.REVIEWS_DATA && window.REVIEWS_DATA.reviews && window.REVIEWS_DATA.reviews.length) {
      setData(window.REVIEWS_DATA);
    } else {
      renderSetup();
    }
  }

  $("app-sel").addEventListener("change", function (e) {
    if (e.target.value) loadApp(e.target.value);
  });
  $("tier-sel").addEventListener("change", function () {
    try {
      if (state.data) localStorage.setItem("playReviewsTier:" + state.data.app_id, this.value);
    } catch (e) {}
  });

  fetch("apps/index.json", { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      state.apps = data.apps || [];
      renderAppSel();
      if (!state.apps.length) return legacyBoot();
      var last = null;
      try { last = localStorage.getItem("playReviewsLastApp"); } catch (e) {}
      var pick = state.apps.filter(function (a) { return a.app_id === last; })[0] || state.apps[0];
      return loadApp(pick.app_id);
    })
    .catch(bootFromInline);
})();

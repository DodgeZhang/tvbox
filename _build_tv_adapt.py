# -*- coding: utf-8 -*-
"""一次性构建脚本：在 AppleMusic.html 基础上注入 TV/手机双端适配，生成 AppleMusicTV.html（不覆盖原文件）"""
import os

base = r"d:\交投资料\相关文档\07-Git文件\Github\tvbox\webhome\html"
src = os.path.join(base, "AppleMusic.html")
dst = os.path.join(base, "AppleMusicTV.html")

with open(src, "r", encoding="utf-8", newline="") as f:
    raw = f.read()

# 主应用 <script>（行 2753 的裸 <script>）到行 8686 的 </script>，其后内容为浏览器扩展注入垃圾，全部丢弃
start = raw.index("<script>")
end = raw.index("</script>", start) + len("</script>")
base_html = raw[:end]

CSS = r'''
<style id="aq-dual-adapt">
/* ============================================================
   Apple Music 双端适配注入样式（TV 遥控 / 手机触屏）
   原则：只增强、不改变原有视觉风格；TV 规则全部限定 html.tv-mode，
   触屏规则限定 html.touch-device 或小屏媒体查询。
   ============================================================ */

/* ---------- 手机/触屏：命中区域、即时反馈（视觉尺寸不变） ---------- */
html.touch-device button,
html.touch-device .tab,
html.touch-device .chip,
html.touch-device .album,
html.touch-device .ch-item,
html.touch-device .pl-card,
html.touch-device .duo-card,
html.touch-device .song,
html.touch-device .lib-item,
html.touch-device a {
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
html.touch-device .album,
html.touch-device .ch-item,
html.touch-device .pl-card,
html.touch-device .duo-card { transition: transform .12s ease; }
html.touch-device .album:active,
html.touch-device .ch-item:active,
html.touch-device .pl-card:active,
html.touch-device .duo-card:active { transform: scale(.97); }
/* 整行类元素按下给底色反馈，不做缩放避免满宽溢出 */
html.touch-device .song:active,
html.touch-device .lib-item:active { background: rgba(250, 45, 72, .08); }

/* iOS 输入框字号 >=16px 防止聚焦自动放大（搜索框原本即 17px） */
html.touch-device .field,
html.touch-device .src-editor input { font-size: 16px; }

/* 小图标按钮扩大隐形命中区到 >=44px（不改视觉大小） */
html.touch-device .circle-btn,
html.touch-device .ch-refresh,
html.touch-device .plat-btn,
html.touch-device .song-more { position: relative; }
html.touch-device .circle-btn::before,
html.touch-device .ch-refresh::before,
html.touch-device .plat-btn::before,
html.touch-device .song-more::before {
  content: ""; position: absolute; inset: -6px; border-radius: inherit;
}
html.touch-device .ch-refresh::before,
html.touch-device .plat-btn::before { inset: -7px; }

/* 超窄屏（<=360px）紧凑留白，避免横向溢出 */
@media (max-width: 360px) {
  .page { padding-left: 14px; padding-right: 14px; }
  .header { padding-left: 14px; padding-right: 14px; }
  .album { flex-basis: 134px; width: 134px; max-width: 134px; }
  .album-art { width: 134px; height: 134px; }
  .album-name, .album-artist { max-width: 134px; }
  .ch-grid, .pl-grid { gap: 12px 8px; }
  .top-duo { gap: 8px; }
}
/* 横屏矮屏手机：播放页封面收敛，避免遮挡控制区 */
@media (pointer: coarse) and (max-height: 520px) {
  #npArt { width: 168px; height: 168px; }
}

/* ---------- TV 遥控模式：焦点环 ---------- */
html.tv-mode *:focus { outline: none !important; }
html.tv-mode .tv-focus {
  outline: 3px solid var(--pink);
  outline-offset: 3px;
  box-shadow: 0 0 0 7px rgba(250, 45, 72, .22), 0 10px 30px rgba(236, 34, 65, .28) !important;
  transform: scale(1.07);
  transition: transform .12s ease, box-shadow .12s ease, outline-color .12s ease;
  position: relative;
  z-index: 30;
}
/* 整行类元素轻微放大，避免满宽行溢出 */
html.tv-mode .tv-focus.song,
html.tv-mode .tv-focus.lib-item { transform: scale(1.015); }
html.tv-mode .tv-focus.album { transform: scale(1.08); }
html.tv-mode .tv-focus.ch-tab,
html.tv-mode .tv-focus.search-tab,
html.tv-mode .tv-focus.chip { transform: scale(1.05); }
/* 输入类与全屏歌词不使用缩放 */
html.tv-mode input.tv-focus,
html.tv-mode textarea.tv-focus,
html.tv-mode select.tv-focus,
html.tv-mode .tv-focus[type="range"] { transform: none; }
html.tv-mode .np-lyrics.tv-focus {
  outline: none;
  box-shadow: none !important;
  transform: none;
}
@media (prefers-reduced-motion: reduce) {
  html.tv-mode .tv-focus { transition: none; }
}

/* ---------- TV 10-foot UI：大屏布局放大（>=820px） ---------- */
@media (min-width: 820px) {
  html.tv-mode #app { max-width: 920px; }
  html.tv-mode .header { padding-left: 30px; padding-right: 30px; }
  html.tv-mode .header h1 { font-size: 30px; }
  html.tv-mode .plat-btn { height: 40px; padding: 0 16px; font-size: 15px; }
  html.tv-mode .page { padding-left: 30px; padding-right: 30px; }
  html.tv-mode .sec-title { font-size: 24px; }
  html.tv-mode .top-duo { height: 220px; margin-bottom: 26px; }
  html.tv-mode .ch-grid,
  html.tv-mode .pl-grid { grid-template-columns: repeat(5, 1fr); gap: 20px 16px; }
  html.tv-mode .ch-item { padding: 18px 12px; }
  html.tv-mode .ch-ico { width: 54px; height: 54px; font-size: 26px; }
  html.tv-mode .album { flex-basis: 172px; width: 172px; max-width: 172px; }
  html.tv-mode .album-art { width: 172px; height: 172px; }
  html.tv-mode .album-name,
  html.tv-mode .album-artist { max-width: 172px; }
  html.tv-mode .circle-btn { width: 40px; height: 40px; }
  html.tv-mode .dock { bottom: 22px; }
  html.tv-mode .tab { font-size: 12px; }
  /* 播放页内容收束到中部安全宽度 */
  html.tv-mode .np {
    padding-left: calc((100vw - 860px) / 2);
    padding-right: calc((100vw - 860px) / 2);
  }
  html.tv-mode #npPlay { width: 84px !important; height: 84px !important; }
  html.tv-mode .np-controls button { width: 64px; height: 64px; }
  html.tv-mode .np-tools button { font-size: 13px; }
  html.tv-mode .np-tools svg { width: 30px; height: 30px; }
  html.tv-mode .np-seek input[type="range"] { height: 26px; }
  /* 弹层加宽 */
  html.tv-mode .sheet { max-width: 720px; }
  html.tv-mode .src-editor { max-width: 560px; }
  html.tv-mode .q-pop { width: 240px; }
}
@media (min-width: 1280px) {
  html.tv-mode #app { max-width: 1240px; }
  html.tv-mode .ch-grid,
  html.tv-mode .pl-grid { grid-template-columns: repeat(7, 1fr); }
  html.tv-mode .album { flex-basis: 196px; width: 196px; max-width: 196px; }
  html.tv-mode .album-art { width: 196px; height: 196px; }
  html.tv-mode .album-name,
  html.tv-mode .album-artist { max-width: 196px; }
  html.tv-mode .top-duo { height: 250px; }
}

/* ---------- TV：dock-side（主页/搜索圆钮）始终恢复可见可聚焦 ---------- */
/* 原应用仅在 dock collapsed 时让它们可见，展开状态 width:0 opacity:0
   导致 TV 方向键完全找不到底部导航，这里强制恢复 */
html.tv-mode .dock-side {
  position: relative !important;
  display: grid !important;
  place-items: center !important;
  opacity: 1 !important;
  width: 44px !important;
  min-width: 44px !important;
  max-width: 44px !important;
  height: 44px !important;
  flex: 0 0 44px !important;
  pointer-events: auto !important;
  transform: scale(1) !important;
  border-width: 0.5px !important;
  border-radius: 50% !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: visible !important;
}

/* ---------- TV 横屏：dock 移到左侧竖排 ---------- */
/* TV 遥控器几乎总是横屏；用 aspect ratio + tv-mode 限定，
   同时 HTML 会挂 .landscape 类（由 JS 监听 orientation + 宽高比） */
@media (orientation: landscape), (min-aspect-ratio: 16/9) {
  html.tv-mode .dock {
    position: fixed !important;
    left: 10px !important;
    top: 50% !important;
    right: auto !important;
    bottom: auto !important;
    transform: translateY(-50%) !important;
    flex-direction: column !important;
    width: 68px !important;
    min-width: 68px !important;
    max-width: 68px !important;
    height: auto !important;
    padding: 10px 6px !important;
    gap: 10px !important;
    background:
      linear-gradient(180deg, rgba(255,255,255,0.78) 0%, rgba(255,255,255,0.62) 100%);
    backdrop-filter: saturate(220%) blur(48px);
    -webkit-backdrop-filter: saturate(220%) blur(48px);
    border: 0.5px solid rgba(255,255,255,0.55);
    border-radius: 36px;
    box-shadow: 0 10px 28px rgba(0,0,0,0.09), inset 0 1px 0 rgba(255,255,255,0.95);
    pointer-events: auto;
  }
  /* 竖排 dock 隐藏 mini（播放信息在播放页/迷你播放更有意义） */
  html.tv-mode .dock .mini { display: none !important; }
  /* tabbar 竖排 */
  html.tv-mode .dock .tabbar {
    flex-direction: column !important;
    width: 56px !important;
    height: auto !important;
    max-height: none !important;
    border-radius: 28px;
    overflow: hidden;
    padding: 4px 0;
    gap: 2px;
  }
  html.tv-mode .dock .tab {
    flex: 0 0 auto !important;
    width: 100%;
    height: 52px;
    font-size: 9px;
    gap: 1px;
  }
  /* 圆钮侧键 */
  html.tv-mode .dock .dock-side {
    width: 40px !important;
    height: 40px !important;
    flex: 0 0 40px !important;
    margin: 0 auto !important;
  }
  /* 主内容让出 dock 宽度 */
  html.tv-mode #app { padding-left: 92px !important; box-sizing: border-box; }
  html.tv-mode .header { padding-left: 28px !important; }
  html.tv-mode .page { padding-left: 28px !important; }
  /* 播放页不受左侧 dock 挤压 */
  html.tv-mode .np { padding-left: 0 !important; }
  /* dock 不再需要强制展开——它被固定在侧栏一直可见 */
  html.tv-mode .dock,
  html.tv-mode .dock.collapsed {
    transform: translateY(-50%) !important;
  }
}

/* ---------- 模式切换轻提示 ---------- */
.aq-tip {
  position: fixed; left: 50%; bottom: 130px;
  transform: translate(-50%, 18px);
  background: rgba(20, 20, 25, .88); color: #fff;
  padding: 10px 22px; border-radius: 999px;
  font-size: 14px; line-height: 1.4; z-index: 9999;
  opacity: 0; pointer-events: none;
  transition: opacity .25s ease, transform .25s ease;
  -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px);
  max-width: 80vw; text-align: center;
}
.aq-tip.show { opacity: 1; transform: translate(-50%, 0); }
</style>
'''

JS = r'''
<script>
/* ============================================================
   AQ 双端适配引擎（注入式，不改动原应用任何逻辑）
   - TV：遥控器方向键空间焦点导航 / OK 确认 / 返回分层退出 / 媒体键
   - 手机：由系统原生触屏处理（CSS 已补命中区与反馈），本引擎只做模式识别
   - 开关：F2 手动切换；URL ?tv=1 / ?tv=0；非触屏设备首次按方向键自动进入
   ============================================================ */
(function () {
  "use strict";
  var docEl = document.documentElement;
  function $(id) { return document.getElementById(id); }
  var LS_KEY = "aq_tv_mode";

  /* ---------- 设备识别 ---------- */
  var ua = navigator.userAgent || "";
  var tvUA = /android[\s_-]?tv|smart[ -]?tv|google[ ]?tv|googletv|aft(t|m|n|b|s|r|d|i|ks|ka|mm|ss)|bravia|vidaa|web0s|netcast|hbbtv|tizen|netrange|opera tv|roku|crkey|ce-html/i.test(ua);
  var coarse = !!(window.matchMedia && matchMedia("(pointer: coarse)").matches) ||
    "ontouchstart" in window || navigator.maxTouchPoints > 0;
  var saved = null;
  try { saved = localStorage.getItem(LS_KEY); } catch (e) {}
  var tvMode = saved === "1" ? true : saved === "0" ? false : tvUA;

  /* URL 参数临时/强制指定（并记忆到 localStorage） */
  try {
    var qs = new URLSearchParams(location.search);
    if (qs.get("tv") === "1") { tvMode = true; try { localStorage.setItem(LS_KEY, "1"); } catch (e) {} }
    else if (qs.get("tv") === "0") { tvMode = false; try { localStorage.setItem(LS_KEY, "0"); } catch (e) {} }
  } catch (e) {}

  function paint() {
    docEl.classList.toggle("tv-mode", !!tvMode);
    docEl.classList.toggle("touch-device", !!coarse);
  }
  paint();

  /* ---------- 轻提示 ---------- */
  var tipEl = null, tipTimer = 0;
  function showTip(t) {
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "aq-tip"; document.body.appendChild(tipEl); }
    tipEl.textContent = t;
    tipEl.classList.add("show");
    clearTimeout(tipTimer);
    tipTimer = setTimeout(function () { tipEl.classList.remove("show"); }, 1600);
  }

  function toggleTV() {
    tvMode = !tvMode;
    try { localStorage.setItem(LS_KEY, tvMode ? "1" : "0"); } catch (e) {}
    paint();
    if (tvMode) {
      showTip("TV 遥控模式：已开启（方向键导航 / OK 确认 / 返回退出）");
      setTimeout(function () { focusDefault(); }, 60);
    } else {
      var rings = document.querySelectorAll(".tv-focus");
      for (var i = 0; i < rings.length; i++) rings[i].classList.remove("tv-focus");
      ringHolder = null;
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
      showTip("TV 遥控模式：已关闭");
    }
  }

  /* ---------- 焦点候选与可视判定 ---------- */
  var CUSTOM = ".duo-card,.album,.ch-item,.pl-card,.song,.chip,.ch-tab,.search-tab,.lib-item,.np-lyrics,.np-art-wrap,#mini.show";
  var SELECTOR = "a[href],button,input,select,textarea,[role=button],.q-opt," + CUSTOM;

  function isVisible(el) {
    if (!el || el.disabled) return false;
    var r = el.getBoundingClientRect();
    if (r.width < 3 || r.height < 3) return false;
    var cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || cs.visibility === "collapse") return false;
    if (parseFloat(cs.opacity) < 0.08 || cs.pointerEvents === "none") return false;
    if (el.closest && el.closest(".page:not(.on)")) return false;
    return true;
  }

  /* 当前最上层交互作用域：弹层 > 播放页 > 普通页面（含顶栏、dock） */
  function layer() {
    var ed = document.querySelector(".src-editor-mask.open");
    if (ed) return { kind: "editor", roots: [ed] };
    var qp = $("qPop");
    if (qp && qp.classList.contains("open")) return { kind: "qpop", roots: [qp] };
    var sm = $("sheetMask");
    if (sm && sm.classList.contains("open")) return { kind: "sheet", roots: [$("sheetBody")] };
    var pw = $("platWrap");
    if (pw && pw.classList.contains("open")) return { kind: "plat", roots: [pw] };
    var np = $("np");
    if (np && np.classList.contains("open")) {
      return { kind: "np", roots: [np], lyrics: np.classList.contains("lyrics-full") };
    }
    var roots = [];
    var page = document.querySelector(".page.on");
    if (page) roots.push(page);
    var hdr = document.querySelector(".header");
    if (hdr) roots.push(hdr);
    var dock = $("dock");
    if (dock) roots.push(dock);
    return { kind: "page", roots: roots, page: page };
  }

  /* 播放队列弹层的行是无类名、inline cursor:pointer 的 div，单独纳入 */
  var SHEET_ROW = "#sheetBody div[style*=\"cursor: pointer\"]";
  function gather(L) {
    var out = [], seen = new Set();
    var sel = SELECTOR + (L.kind === "sheet" ? "," + SHEET_ROW : "");
    L.roots.forEach(function (root) {
      if (!root || !root.querySelectorAll) return;
      var nodes = root.querySelectorAll(sel);
      for (var i = 0; i < nodes.length; i++) {
        var el = nodes[i];
        if (seen.has(el)) continue;
        if (!isVisible(el)) continue;
        /* 非原生可聚焦的卡片/行在 TV 模式下纳入焦点序列 */
        if (tvMode && !el.hasAttribute("tabindex") &&
            (el.matches(CUSTOM) || el.matches(SHEET_ROW))) el.setAttribute("tabindex", "-1");
        seen.add(el);
        out.push(el);
      }
    });
    return out;
  }

  /* ---------- 焦点环与焦点记忆 ----------
     主路径由引擎在每次移动焦点时显式挂环（兼容不派发 focusin 的
     WebView/自动化环境）；同时保留 focusin/focusout 监听作为兜底。 */
  var pageAnchor = {};
  var ringHolder = null;
  function applyRing(el) {
    if (ringHolder && ringHolder !== el) ringHolder.classList.remove("tv-focus");
    if (el && el.classList) el.classList.add("tv-focus");
    ringHolder = el || null;
  }
  document.addEventListener("focusin", function (e) {
    if (!tvMode) return;
    var t = e.target;
    if (t && t.classList && t.matches && t.matches(SELECTOR)) applyRing(t);
    var p = t && t.closest ? t.closest(".page") : null;
    if (p && p.id) pageAnchor[p.id] = t;
  }, true);
  document.addEventListener("focusout", function (e) {
    if (ringHolder === e.target && document.activeElement !== e.target) return;
    if (e.target && e.target.classList && ringHolder !== e.target) e.target.classList.remove("tv-focus");
  }, true);

  function focusEl(el) {
    if (!el) return;
    try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); }
    if (tvMode) applyRing(el);
    var p = el.closest ? el.closest(".page") : null;
    if (p && p.id) pageAnchor[p.id] = el;
    requestAnimationFrame(function () {
      try { el.scrollIntoView({ block: "nearest", inline: "nearest" }); } catch (e) {}
    });
  }

  function pickDefault(L, list) {
    var el;
    if (L.kind === "np") {
      if (L.lyrics) return $("npLyrics");
      return $("npPlay");
    }
    if (L.kind === "qpop") return L.roots[0].querySelector(".q-opt.on") || list[0];
    if (L.kind === "plat") return L.roots[0].querySelector(".plat-menu button.on") || list[0];
    if (L.kind === "editor") return L.roots[0].querySelector("input[type=text],input:not([type]),textarea") || list[0];
    if (L.kind === "sheet") {
      el = L.roots[0].querySelector(SHEET_ROW);
      return el || list[0];
    }
    if (L.page) {
      el = pageAnchor[L.page.id];
      if (el && list.indexOf(el) >= 0) return el;
      if (L.page.id === "p-search") { el = $("qInput"); if (el && isVisible(el)) return el; }
      return list[0];
    }
    return list[0];
  }

  function focusDefault(soft) {
    if (!tvMode) return;
    var L = layer();
    var list = gather(L);
    if (!list.length) return;
    if (soft && document.activeElement && document.activeElement !== document.body &&
      list.indexOf(document.activeElement) >= 0) return;
    focusEl(pickDefault(L, list));
  }

  /* ---------- 空间方向导航 ---------- */
  function move(dir, origin) {
    var L = layer();
    /* 全屏歌词：上下键滚动歌词 */
    if (L.lyrics && (dir === "up" || dir === "down")) {
      var box = $("npLyrics");
      if (box) box.scrollBy({ top: dir === "up" ? -64 : 64, behavior: "smooth" });
      return;
    }
    var list = gather(L);
    if (!list.length) return;
    var act = origin || document.activeElement;
    if (!act || list.indexOf(act) < 0) { focusEl(pickDefault(L, list)); return; }

    /* mini 播放条：未进入该区域时只选 mini 本体（OK 打开播放页），
       进入后左右键才选到内部的播放/下一首按钮 */
    var miniEl = $("mini");
    if (miniEl && act !== miniEl && !miniEl.contains(act)) {
      list = list.filter(function (el) { return el === miniEl || !miniEl.contains(el); });
    }

    /* 播放页：控制行上键直达进度条（避免被整幅歌词区截获） */
    if (L.kind === "np" && dir === "up" && act.id &&
        ["npPrev", "npPlay", "npNext", "npFav", "npSpeed", "npQuality", "npQueue", "npClose"].indexOf(act.id) >= 0) {
      var seek = $("npSeek");
      if (seek && isVisible(seek)) { focusEl(seek); return; }
    }

    var ar = act.getBoundingClientRect();
    var ax = (ar.left + ar.right) / 2, ay = (ar.top + ar.bottom) / 2;
    var best = null, bestScore = Infinity, innerBest = null, innerScore = Infinity, relaxBest = null, relaxScore = Infinity;

    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (el === act) continue;
      var r = el.getBoundingClientRect();
      var cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2;
      var along = 0, cross = 0, edge = 0, half = false, contained = act.contains(el);
      if (dir === "right") { along = cx - ax; cross = Math.abs(cy - ay); edge = r.left - ar.right; half = cx > ax - 6; }
      else if (dir === "left") { along = ax - cx; cross = Math.abs(cy - ay); edge = ar.left - r.right; half = cx < ax + 6; }
      else if (dir === "down") { along = cy - ay; cross = Math.abs(cx - ax); edge = r.top - ar.bottom; half = cy > ay - 6; }
      else { along = ay - cy; cross = Math.abs(cx - ax); edge = ar.top - r.bottom; half = cy < ay + 6; }
      if (!half) continue;
      var score = edge + cross * 1.7;
      if (edge > -4) {
        if (score < bestScore) { bestScore = score; best = el; }
      } else if (contained) {
        /* 当前元素内部的小按钮（如歌曲行右侧的“更多”） */
        var s = Math.max(edge, -ar.width * 0.8) + cross;
        if (s < innerScore) { innerScore = s; innerBest = el; }
      } else {
        var rs = Math.max(edge, -ar.width * 0.55) + cross * 1.7;
        if (rs < relaxScore) { relaxScore = rs; relaxBest = el; }
      }
    }
    focusEl(best || innerBest || relaxBest);
  }

  /* ---------- 弹层开关感知：自动落焦 / 关闭回焦 ---------- */
  function sig() {
    return {
      editor: !!document.querySelector(".src-editor-mask.open"),
      qpop: !!($("qPop") && $("qPop").classList.contains("open")),
      sheet: !!($("sheetMask") && $("sheetMask").classList.contains("open")),
      plat: !!($("platWrap") && $("platWrap").classList.contains("open")),
      np: !!($("np") && $("np").classList.contains("open")),
      lyrics: !!($("np") && $("np").classList.contains("lyrics-full")),
      page: (document.querySelector(".page.on") || {}).id || ""
    };
  }
  var cur = sig(), rafId = 0;
  function currentOrNull() { var a = document.activeElement; return a && a !== document.body ? a : null; }
  function schedule() {
    if (rafId) return;
    rafId = requestAnimationFrame(function () { rafId = 0; react(); });
  }
  new MutationObserver(schedule).observe(document.body, {
    subtree: true, childList: true, attributes: true, attributeFilter: ["class"]
  });

  /* TV 模式下底栏始终展开：原应用会在播放时随下滑自动收起底栏，
     收起后方向键无法到达标签栏，这里同步阻止 collapsed 生效 */
  (function () {
    var dock = $("dock");
    if (!dock) return;
    new MutationObserver(function () {
      if (tvMode && dock.classList.contains("collapsed")) dock.classList.remove("collapsed");
    }).observe(dock, { attributes: true, attributeFilter: ["class"] });
  })();

  /* 焦点堆栈：每个弹层打开时压栈记录来源焦点，关闭时逐层回焦
     （播放页内的音质/操作表子弹层关闭时，播放页本身仍开着） */
  var KINDS = ["editor", "qpop", "sheet", "plat", "np"];
  var OPEN_DELAY = { editor: 180, qpop: 200, sheet: 240, plat: 180, np: 280 };
  var focusStack = [];
  function react() {
    var s = sig();
    var opened = [], closed = [];
    for (var ii = 0; ii < KINDS.length; ii++) {
      var k = KINDS[ii];
      if (s[k] && !cur[k]) opened.push(k);
      else if (!s[k] && cur[k]) closed.push(k);
    }
    if (s.lyrics !== cur.lyrics) {
      cur = s;
      setTimeout(function () { if (tvMode) focusEl(s.lyrics ? $("npLyrics") : $("npPlay")); }, 60);
      return;
    }
    if (opened.length) {
      cur = s;
      opened.forEach(function (kd) { focusStack.push({ k: kd, f: currentOrNull() }); });
      setTimeout(focusDefault, OPEN_DELAY[opened[0]] || 200);
      return;
    }
    if (closed.length) {
      cur = s;
      var restore = null;
      /* 从栈顶弹出本次关闭的层（可能一次关多层，如 sheet 里点歌直接进 np） */
      while (focusStack.length && closed.indexOf(focusStack[focusStack.length - 1].k) >= 0) {
        restore = focusStack.pop().f;
      }
      /* 若关闭的不是栈顶层（异常顺序），也移除对应记录 */
      focusStack = focusStack.filter(function (it) { return closed.indexOf(it.k) < 0; });
      setTimeout(function () {
        var L = layer(), list = gather(L);
        if (restore && isVisible(restore) && list.indexOf(restore) >= 0) focusEl(restore);
        else focusDefault();
      }, 80);
      return;
    }
    var nowOverlay = s.editor || s.qpop || s.sheet || s.plat || s.np;
    if (!nowOverlay && s.page && s.page !== cur.page) { cur = s; setTimeout(focusDefault, 140); return; }
    cur = s;
  }
  setTimeout(function () { if (tvMode) focusDefault(); }, 700);

  /* ---------- 按键映射 ---------- */
  var TEXT_TYPES = { text: 1, search: 1, url: 1, tel: 1, password: 1, email: 1, number: 1, "": 1 };
  function typing(el) {
    if (!el) return false;
    if (el.tagName === "TEXTAREA" || el.isContentEditable) return true;
    if (el.tagName === "INPUT") return !!TEXT_TYPES[(el.type || "text").toLowerCase()];
    return false;
  }
  function click(el) { if (el) el.click(); }

  function doBack(L) {
    if (L.lyrics) {
      /* 全屏歌词压了历史层：history.back() 走原应用 popstate 退出，播放页保留 */
      try { history.back(); } catch (eHb) { var _np = $("np"); if (_np) _np.classList.remove("lyrics-full"); }
      return;
    }
    if (L.kind === "editor") { click(document.querySelector(".src-editor-mask.open")); return; }
    if (L.kind === "qpop") { click($("qPopMask")); return; }
    if (L.kind === "sheet") { click($("sheetMask")); return; }
    if (L.kind === "plat") { click($("btnPlat")); return; }
    if (L.kind === "np") { click($("npClose")); return; }
    /* 普通页面：非首页先回首页（首页按下无动作，避免误退出网站） */
    if (L.page && L.page.id !== "p-home") {
      click(document.querySelector('.tab[data-p="home"]') || $("dockHome"));
    }
  }

  function seekStep(dir) {
    var s = $("npSeek");
    if (!s) return;
    var max = Number(s.max) || 1000, min = Number(s.min) || 0;
    var step = Math.max(8, Math.round((max - min) * 0.03));
    var v = Number(s.value) || 0;
    v = dir === "right" ? Math.min(max, v + step) : Math.max(min, v - step);
    s.value = v;
    s.dispatchEvent(new Event("input", { bubbles: true }));
    s.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function npOpen() { var n = $("np"); return n && n.classList.contains("open"); }
  function miniShown() { var m = $("mini"); return m && m.classList.contains("show"); }
  function mediaPlay() {
    if (npOpen()) click($("npPlay"));
    else if (miniShown()) click($("miniPlay"));
  }
  function mediaNext() {
    if (npOpen()) click($("npNext"));
    else if (miniShown()) click($("miniNext"));
  }
  function mediaPrev() { if (npOpen()) click($("npPrev")); }

  window.addEventListener("keydown", function (e) {
    var k = e.key, kc = e.keyCode;
    if (k === "F2") { e.preventDefault(); toggleTV(); return; }

    /* 非 TV 模式：非触屏设备首次使用方向键/确认键时自动进入（兼顾 UA 不标准的电视盒与桌面测试） */
    if (!tvMode) {
      if (!coarse && !typing(e.target) && ((kc >= 37 && kc <= 40) || kc === 13 || kc === 23)) {
        tvMode = true; paint();
      } else return;
    }

    /* 媒体键 */
    if (k === "MediaPlayPause" || k === "MediaPlay" || k === "MediaPause" || kc === 179) {
      e.preventDefault(); mediaPlay(); return;
    }
    if (k === "MediaTrackNext" || kc === 176) { e.preventDefault(); mediaNext(); return; }
    if (k === "MediaTrackPrevious" || kc === 177) { e.preventDefault(); mediaPrev(); return; }

    var dir = (k === "ArrowLeft" || kc === 37) ? "left"
      : (k === "ArrowRight" || kc === 39) ? "right"
      : (k === "ArrowUp" || kc === 38) ? "up"
      : (k === "ArrowDown" || kc === 40) ? "down" : null;

    /* 文本输入中：左右键/回车交给光标、系统输入法与原应用（如回车搜索）；
       单行输入框的上下键用于离开输入框、恢复遥控器导航（TV 惯例） */
    if (typing(e.target)) {
      if (k === "Escape") { e.preventDefault(); try { e.target.blur(); } catch (err) {} return; }
      if (e.target.tagName === "INPUT" && (k === "ArrowUp" || k === "ArrowDown" || kc === 38 || kc === 40)) {
        e.preventDefault();
        var from = e.target;
        from.blur();
        move(k === "ArrowUp" || kc === 38 ? "up" : "down", from);
      }
      return;
    }

    var L = layer();

    /* 返回键：Esc / Backspace / Tizen 10009 / Android Back 4 / 各家遥控器命名 */
    if (k === "Escape" || k === "Backspace" || k === "Back" || k === "GoBack" ||
      k === "XF86Back" || k === "XF86Exit" || kc === 10009 || kc === 4) {
      e.preventDefault();
      e.stopPropagation();
      doBack(L);
      return;
    }

    if (dir) {
      e.preventDefault();
      if (e.target && e.target.id === "npSeek" && (dir === "left" || dir === "right")) {
        seekStep(dir);
        return;
      }
      move(dir);
      return;
    }

    /* OK / 确认 / 空格：激活当前焦点元素 */
    if (k === "Enter" || k === " " || kc === 23) {
      var el = document.activeElement;
      if (el && el !== document.body && !typing(el)) {
        e.preventDefault();
        click(el);
      }
    }
  }, true);

  /* TV 设备首次进入时给出一次操作提示 */
  if (tvMode && tvUA && saved !== "1" && saved !== "0") {
    setTimeout(function () { showTip("已进入 TV 遥控模式：方向键移动焦点，OK 确认，返回键退出"); }, 900);
  }

  /* 调试/自检接口（只读为主） */
  window.__aqDbg = {
    layer: layer, gather: gather, move: move, focusDefault: focusDefault,
    isVisible: isVisible, isTV: function () { return tvMode; },
    info: function () {
      var L = layer(), list = gather(L);
      return {
        kind: L.kind, n: list.length,
        active: document.activeElement ? {
          tag: document.activeElement.tagName, id: document.activeElement.id,
          cls: String(document.activeElement.className).slice(0, 40)
        } : null,
        items: list.map(function (el) {
          return (el.getAttribute("data-p") || el.id || String(el.className).split(" ")[0]);
        })
      };
    }
  };
})();
</script>
'''

anchor = "</style></head>"
pos = base_html.index(anchor) + len("</style>")
out = base_html[:pos] + CSS + base_html[pos:] + JS + "\n</body>\n</html>\n"

with open(dst, "w", encoding="utf-8", newline="") as f:
    f.write(out)

print("OK", len(raw), "->", len(out))
print("dst:", dst)

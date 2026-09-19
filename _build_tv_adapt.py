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

/* ---------- TV：统一隐藏 dock-side（主页/搜索圆钮） ---------- */
/* dock-side 是原应用底部 dock collapsed 时才显示的冗余入口；
   TV 模式下 dock 始终展开，tabbar（主页/搜索/资料库/设置）已覆盖全部导航，
   两个 .dock-side 与 tab 完全重复，直接隐藏 */
html.tv-mode .dock .dock-side { display: none !important; }

/* ---------- TV 横屏：dock 变成左侧满高侧栏 ---------- */
/* 覆盖原 10-foot 媒体查询的 max-width（920/1240/1920px）让页面铺满；
   dock 用 position:fixed 贴左但不做悬浮胶囊（纯色 + 0 圆角 + 无阴影），
   主内容靠 #app padding-left 让位，header + .page 保持正常垂直堆叠。 */
@media (orientation: landscape), (min-aspect-ratio: 16/9) {
  /* 清除原 820/1280/1800 段给 #app 设置的 max-width 限制 */
  html.tv-mode #app {
    max-width: none !important;
    width: 100% !important;
    padding-left: 96px !important;
    padding-right: 0 !important;
    margin-left: 0 !important;
    box-sizing: border-box;
  }
  /* header / .page 不再受 10-foot 段的 max-width 限制 */
  html.tv-mode .header,
  html.tv-mode .page {
    width: 100% !important;
    max-width: none !important;
    padding-left: 4px !important;
    padding-right: 16px !important;
    box-sizing: border-box;
  }
  html.tv-mode .header {
    display: flex !important;
    justify-content: space-between !important;
    align-items: center !important;
  }
  html.tv-mode .header h1 {
    font-size: 26px !important;
    margin: 0 !important;
  }
  html.tv-mode .header-btns {
    display: flex !important;
    justify-content: flex-end !important;
    align-items: center !important;
    margin-left: auto;
    gap: 8px;
  }
  html.tv-mode .header-btns .plat-btn {
    margin-left: 0 !important;
  }

  /* ===== 老 TV 内核兼容（Chromium 60-80 常见于电视盒子/智能电视） ===== */
  /* 1) .album 填满 grid 列（避免固定 172px 在宽屏 minmax(150px,1fr) 多列时溢出重叠）；
        .album-art 靠图片自然比例保方形（不依赖 aspect-ratio，该属性需 Chromium≥88） */
  html.tv-mode .h-row .album {
    width: 100% !important;
    max-width: none !important;
    flex-basis: auto !important;
  }
  html.tv-mode .album-art {
    width: 100% !important;
    height: auto !important;
    aspect-ratio: 1 / 1;            /* 现代浏览器：方形；老浏览器忽略，<img> 靠自然比例仍方形 */
  }
  /* 2) .duo-cover / .duo-mask 用 inset:0 定位（需 Chromium≥87），老内核补全四边 */
  html.tv-mode .duo-cover,
  html.tv-mode .duo-mask {
    top: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    left: 0 !important;
  }
  /* 2b) 全量 inset:0 兜底：所有原文件用 inset:0 的弹层/页面容器，
        老内核不认 inset 会导致 #np 播放页等无尺寸不可见。这里统一补全四边。 */
  html.tv-mode .page,
  html.tv-mode .np,
  html.tv-mode .np-bg,
  html.tv-mode .sheet-mask,
  html.tv-mode .feature-slide,
  html.tv-mode .feature-slide .feat-right,
  html.tv-mode .q-pop-mask,
  html.tv-mode .src-editor-mask {
    top: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    left: 0 !important;
  }
  /* 伪元素 inset 兜底（装饰层，不补会导致渐变背景不铺满） */
  html.tv-mode .np-bg::after,
  html.tv-mode .np::before {
    top: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    left: 0 !important;
  }
  /* 3) .np-art / 其他使用 CSS min() 的宽度，先给固定兜底值再用 min()；
        老浏览器丢弃 min() 行、保留兜底值 */
  html.tv-mode .np-art {
    width: 320px !important;          /* 兜底：min(72vw,320px) 老内核不认 */
    width: min(72vw, 320px) !important;
    height: 320px !important;
    height: auto !important;
  }
  html.tv-mode .np.open .np-art {
    height: auto !important;
  }
  /* 4) flex gap 兜底（Chromium<84 不认 flex gap，用 margin 补偿关键间距） */
  html.tv-mode .dock .tabbar {
    margin: 0 !important;
  }

  /* 5) 播放页控制按钮：原样式依赖 backdrop-filter 毛玻璃（老内核不支持），
        改成实色背景 + 高对比图标，否则按钮在白底上几乎看不见 */
  html.tv-mode .np-controls {
    gap: 56px !important;             /* 加大上一曲/播放/下一曲按钮间距 */
    padding: 12px 20px 18px !important;
  }
  html.tv-mode .np-controls button {
    background: #f2f2f7 !important;          /* 实色浅灰底，替代毛玻璃 */
    -webkit-backdrop-filter: none !important;
    backdrop-filter: none !important;
    border: 2px solid rgba(0,0,0,0.08) !important;
    color: #1c1c1e !important;                /* 深色图标，确保可见 */
    box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
    /* 老内核 place-items (grid) 居中可能导致图标偏移，改用 flexbox 居中 */
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    transition: background .15s ease, box-shadow .15s ease, border-color .15s ease !important;
  }
  html.tv-mode .np-controls button svg {
    fill: #1c1c1e !important;                 /* SVG 图标强制深色 */
    width: 28px !important;
    height: 28px !important;
    display: block !important;
    /* 老 Chromium SVG 渲染可能歪斜，强制几何精度渲染 + 保持宽高比 */
    shape-rendering: geometricPrecision !important;
  }
  html.tv-mode .np-controls .np-play {
    background: #1c1c1e !important;           /* 播放按钮深色底 */
    color: #fff !important;
    border: 2px solid rgba(0,0,0,0.15) !important;
    box-sizing: border-box !important;        /* 确保圆形不变形 */
  }
  html.tv-mode .np-controls .np-play svg {
    fill: #fff !important;                    /* 播放按钮内白色图标 */
  }
  /* 控制按钮焦点高亮：用边框变色 + 外发光，不用 scale（避免圆形/图标变形） */
  html.tv-mode .np-controls .tv-focus {
    transform: none !important;
    outline: none !important;
    border-color: #fa2d48 !important;
    box-shadow: 0 0 0 5px rgba(250,45,72,0.28), 0 6px 18px rgba(250,45,72,0.25) !important;
  }
  html.tv-mode .np-controls .np-play.tv-focus {
    background: #fa2d48 !important;           /* 播放按钮聚焦时变粉红，最醒目 */
    border-color: #fa2d48 !important;
  }
  html.tv-mode .np-controls .np-play.tv-focus svg {
    fill: #fff !important;
  }
  /* 底部工具栏同样去毛玻璃 */
  html.tv-mode .np-tools {
    background: #f2f2f7 !important;
    -webkit-backdrop-filter: none !important;
    backdrop-filter: none !important;
  }
  html.tv-mode .np-tools button {
    color: #1c1c1e !important;
    border-radius: 12px !important;
    transition: background .15s ease !important;
  }
  html.tv-mode .np-tools button svg {
    fill: #1c1c1e !important;
  }
  html.tv-mode .np-tools .tv-focus {
    transform: none !important;
    outline: none !important;
    background: rgba(250,45,72,0.12) !important;
    color: #fa2d48 !important;
  }
  html.tv-mode .np-tools .tv-focus svg {
    fill: #fa2d48 !important;
  }

  /* dock：贴左满高侧栏，position:fixed 但视觉上与 body 同色，不像浮层 */
  html.tv-mode .dock {
    position: fixed !important;
    order: unset !important;
    left: 0 !important;
    right: auto !important;
    top: 0 !important;
    bottom: 0 !important;
    transform: none !important;
    width: 80px !important;
    min-width: 80px !important;
    max-width: 80px !important;
    height: 100vh !important;
    flex: none !important;
    flex-direction: column !important;
    gap: 0 !important;
    padding: 16px 0 16px 0 !important;
    margin: 0 !important;
    background: var(--surface) !important;
    border-right: 0.5px solid rgba(0,0,0,0.08) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    z-index: 20;
    pointer-events: auto;
  }
  html.tv-mode .dock.collapsed {
    flex-direction: column !important;
    gap: 0 !important;
    background: var(--surface) !important;
  }
  /* mini 隐藏（播放信息在播放页更合适） */
  html.tv-mode .dock .mini { display: none !important; }
  /* tabbar 作为侧栏主体，撑满全高，四个 tab 均匀分布 */
  html.tv-mode .dock .tabbar {
    flex: 1 1 auto !important;
    width: 80px !important;
    min-width: 80px !important;
    max-width: 80px !important;
    height: 100% !important;
    flex-direction: column !important;
    justify-content: space-evenly !important;
    align-items: center !important;
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    padding: 0 !important;
    gap: 0 !important;
    max-height: none !important;
    overflow: visible !important;
  }
  html.tv-mode .dock .tab {
    flex: 0 0 auto !important;
    width: 60px !important;
    height: 60px !important;
    border-radius: 50%;
    flex-direction: column;
    justify-content: center;
    gap: 2px;
    font-size: 10px;
    color: var(--label-2);
    transition: color .2s ease, background .2s ease;
  }
  html.tv-mode .dock .tab svg { width: 26px; height: 26px; }
  html.tv-mode .dock .tab.on {
    color: var(--pink);
    background: rgba(250, 45, 72, 0.08);
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
  /* 宽屏横屏判定：宽度达到 10 英尺布局断点(820px)且宽>高。
     电视盒子几乎总是横屏大屏；触屏笔记本/台式机外接显示器横屏访问时
     也应直接呈现 TV 适配（侧栏 dock / 焦点导航 / 放大布局）。
     竖屏手机（宽<820）不会被误判。 */
  function isWideLandscape() {
    return window.innerWidth >= 820 && window.innerWidth > window.innerHeight;
  }
  var saved = null;
  try { saved = localStorage.getItem(LS_KEY); } catch (e) {}
  var tvMode = saved === "1" ? true : saved === "0" ? false : (tvUA || isWideLandscape());
  /* 用户是否已显式选择过模式（localStorage 记忆 或 URL ?tv=x）；
     显式选择后，resize/旋转不再自动改写，以用户选择为准 */
  var userChosen = saved === "1" || saved === "0";

  /* URL 参数临时/强制指定（并记忆到 localStorage） */
  try {
    var qs = new URLSearchParams(location.search);
    if (qs.get("tv") === "1") { tvMode = true; userChosen = true; try { localStorage.setItem(LS_KEY, "1"); } catch (e) {} }
    else if (qs.get("tv") === "0") { tvMode = false; userChosen = true; try { localStorage.setItem(LS_KEY, "0"); } catch (e) {} }
  } catch (e) {}

  function paint() {
    docEl.classList.toggle("tv-mode", !!tvMode);
    docEl.classList.toggle("touch-device", !!coarse);
  }
  paint();

  /* ---------- 浏览器能力诊断（方便在 TV 上确认内核版本/特性支持） ---------- */
  (function diag() {
    function supports(cssProp) {
      try { return (window.CSS && CSS.supports) ? CSS.supports(cssProp) : null; }
      catch (e) { return null; }
    }
    var info = {
      ua: ua,
      tvMode: tvMode,
      coarse: coarse,
      vw: window.innerWidth, vh: window.innerHeight,
      dpr: window.devicePixelRatio || 1,
      aspectRatio: supports("aspect-ratio: 1"),
      inset: supports("inset: 0"),
      cssMin: supports("width: min(1px, 2px)"),
      backdropFilter: supports("backdrop-filter: blur(1px)"),
      flexGap: supports("gap: 1px") && supports("display: flex"),
      grid: supports("display: grid"),
      customProperties: supports("--x: 0")
    };
    try { console.info("[AQ TV] browser capability:", JSON.stringify(info)); } catch (e) {}
    window.__aqDiag = info;
  })();

  /* 屏幕旋转 / 窗口尺寸变化：用户未显式选择时，进入宽屏横屏自动开 TV 模式 */
  var resizeTimer = 0;
  window.addEventListener("resize", function () {
    if (userChosen || tvMode) return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (!tvMode && isWideLandscape()) {
        tvMode = true;
        paint();
        showTip("已进入 TV 遥控模式：方向键移动焦点，OK 确认，F2 可切换");
        setTimeout(function () { focusDefault(); }, 60);
      }
    }, 200);
  }, { passive: true });
  window.addEventListener("orientationchange", function () {
    setTimeout(function () {
      if (!userChosen && !tvMode && isWideLandscape()) {
        tvMode = true;
        paint();
        setTimeout(function () { focusDefault(); }, 60);
      }
    }, 250);
  }, { passive: true });

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
    userChosen = true;
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
    /* 音质弹框：#qPopMask 同步加 .open，#qPop 下一帧才加，两个都要检查避免漏判 */
    var qp = $("qPop"), qpm = $("qPopMask");
    var qpOpen = (qp && qp.classList.contains("open")) || (qpm && qpm.classList.contains("open"));
    if (qpOpen) return { kind: "qpop", roots: [qp && qp.classList.contains("open") ? qp : (qpm || qp)] };
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
    /* 评分改用"沿轴中心距离"而不是边缘间距 edge：
       焦点环给卡片加了 scale(1.07)，放大后当前卡会与紧邻卡边缘重叠，
       若用 edge 分档，相邻卡会因 edge≤0 被降级、隔一张的卡反而胜出 → 跳卡。
       中心距离不受 scale 影响，相邻卡 along 最小，永远不会被跳过。 */
    var strictBest = null, strictScore = Infinity;
    var relaxBest = null, relaxScore = Infinity;
    var isHorz = dir === "left" || dir === "right";
    var rowCandidates = [];   // 全部候选坐标，供"行序换行"使用（不能只收半平面内的）

    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (el === act) continue;
      var r = el.getBoundingClientRect();
      var cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2;
      rowCandidates.push({ el: el, cx: cx, cy: cy });
      var along = 0, cross = 0, half = false;
      if (dir === "right") { along = cx - ax; cross = Math.abs(cy - ay); half = cx > ax - 6; }
      else if (dir === "left") { along = ax - cx; cross = Math.abs(cy - ay); half = cx < ax + 6; }
      else if (dir === "down") { along = cy - ay; cross = Math.abs(cx - ax); half = cy > ay - 6; }
      else { along = ay - cy; cross = Math.abs(cx - ax); half = cy < ay + 6; }
      if (!half || along < -6) continue;

      /* 同排/同列 cross 容差：以两元素中较小尺寸为基准。
         左右键比对高度（同一水平行），上下键比对宽度（同一列）。
         严格档 0.45，放宽档 1.1（用于错位布局的兜底，绝不跨整行抢焦）。 */
      var baseSize = isHorz ? Math.min(ar.height, r.height) : Math.min(ar.width, r.width);
      var strictTol = Math.max(22, baseSize * 0.45);
      var relaxTol = Math.max(60, baseSize * 1.1);

      var score = along + cross * 1.7;
      if (cross <= strictTol) {
        if (score < strictScore) { strictScore = score; strictBest = el; }
      } else if (cross <= relaxTol) {
        if (score < relaxScore) { relaxScore = score; relaxBest = el; }
      }
    }

    var target = strictBest;

    /* grid/flex 换行布局的"阅读顺序换行"：
       右向走到行尾时，跳到下一行最左侧元素（而不是斜跳到下一行同列，
       那样视觉上像跳过了一整行卡片）；左向同理回上一行最右侧。
       已在最后一行/第一行时停在边界，不做斜向回跳（避免首尾振荡）。 */
    if (!target && isHorz) {
      /* 换行只在"同一布局容器"内寻找（如 #recRow 网格），
         避免选中固定侧栏 dock、隔壁区块按钮等几何上更近但不相关的元素；
         找不到网格容器时退回到当前 .page 作用域 */
      var scope = null;
      var pp = act.parentElement, hops = 0;
      while (pp && pp !== document.body && hops < 4) {
        var pd = getComputedStyle(pp).display;
        if ((pd.indexOf("grid") === 0 || pd.indexOf("flex") === 0) && pp.children.length >= 3) { scope = pp; break; }
        pp = pp.parentElement; hops++;
      }
      if (!scope && act.closest) scope = act.closest(".page");

      var scoped = [];
      for (var k1 = 0; k1 < rowCandidates.length; k1++) {
        var cc = rowCandidates[k1];
        if (scope && scope.contains(cc.el)) scoped.push(cc);
      }
      if (!scoped.length) scoped = rowCandidates;

      var rowGap = ar.height * 0.5;
      /* 先找最近的下/上一行的 cy，再在该行内取最左/最右 */
      var nearestCy = null;
      for (var k2 = 0; k2 < scoped.length; k2++) {
        var d = scoped[k2];
        if (dir === "right") {
          if (d.cy <= ay + rowGap) continue;
          if (nearestCy === null || d.cy < nearestCy) nearestCy = d.cy;
        } else {
          if (d.cy >= ay - rowGap) continue;
          if (nearestCy === null || d.cy > nearestCy) nearestCy = d.cy;
        }
      }
      if (nearestCy !== null) {
        var sameRowTol = ar.height * 0.5;
        var wrapBest2 = null, wrapKey2 = null;
        for (var k3 = 0; k3 < scoped.length; k3++) {
          var e = scoped[k3];
          if (Math.abs(e.cy - nearestCy) > sameRowTol) continue;
          if (dir === "right") {
            if (wrapKey2 === null || e.cx < wrapKey2) { wrapKey2 = e.cx; wrapBest2 = e.el; }
          } else {
            if (wrapKey2 === null || e.cx > wrapKey2) { wrapKey2 = e.cx; wrapBest2 = e.el; }
          }
        }
        target = wrapBest2;   /* 没有上/下一行时为 null → 停在边界 */
      }
    }

    /* 上下方向仍允许放宽档兜底（不同区块间可能有列偏移）；
       水平方向不再用斜向 relax，防止跨行跳卡 */
    if (!target && !isHorz) target = relaxBest;

    focusEl(target);
  }

  /* ---------- 弹层开关感知：自动落焦 / 关闭回焦 ---------- */
  function sig() {
    return {
      editor: !!document.querySelector(".src-editor-mask.open"),
      qpop: !!((($("qPop") && $("qPop").classList.contains("open")) || ($("qPopMask") && $("qPopMask").classList.contains("open")))),
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

  /* TV 模式点播后自动进入播放页：
     原应用的手机交互是"点卡片只出声，再上滑/点迷你条才打开播放页"，
     TV 无触摸手势且横屏下迷你条被隐藏，导致只闻其声不见播放页。
     这里监听音频真正开始播放（URL 异步解析完成）的时机，
     若播放页未打开，则复用原应用入口（点击 #mini 非按钮区 → openNowPlaying）。 */
  (function () {
    var audioEl = $("audio");
    if (!audioEl) return;
    audioEl.addEventListener("play", function () {
      if (!tvMode) return;
      var np = $("np");
      if (np && np.classList.contains("open")) return;
      /* 音频已开始播放但播放页未开：走共享兜底（mini.click → 直接加 open class） */
      ensureNowPlaying("audio-play");
    });
  })();

  /* ---------- 播放页打开共享兜底 ----------
     三个入口都会调用：
       1) audio.play 事件（键盘/鼠标点击卡片都最终走到这里）
       2) keydown OK（键盘确认键）
       3) document click（TCL 等电视遥控器 OK 键发送鼠标 click 而非 keydown）
     原应用 openNowPlaying 在 IIFE 内不可全局调用，这里 replicate 其核心动作。 */
  var ensureTimer = 0;
  function ensureNowPlaying(trigger) {
    if (!tvMode) return;
    clearTimeout(ensureTimer);
    var np = $("np");
    if (np && np.classList.contains("open")) return;
    showDiag(["ensureNP trig=" + trigger + " np.open=" + (np && np.classList.contains("open"))]);
    ensureTimer = setTimeout(function () {
      var n = $("np");
      if (n && n.classList.contains("open")) { showDiag(["ensureNP already open"]); return; }
      /* 尝试 #mini（原应用自己的入口：其 click handler 调 openNowPlaying） */
      var mini = $("mini");
      var miniShow = mini && mini.classList.contains("show");
      showDiag(["ensureNP mini.show=" + miniShow + " display=" + (mini ? getComputedStyle(mini).display : "none")]);
      if (mini) { try { mini.click(); } catch (e1) {} }
      setTimeout(function () {
        var n2 = $("np");
        if (n2 && n2.classList.contains("open")) { showDiag(["ensureNP opened via mini.click"]); return; }
        /* mini.click 在 display:none 下老 WebView 可能不响应，直接 replicate openNowPlaying 核心 */
        if (n2) {
          n2.classList.remove("closing", "lyrics-full");
          n2.style.transform = "";
          n2.style.opacity = "";
          n2.style.transition = "";
          n2.classList.add("open");
          try { history.pushState({ aqNp: 1 }, "", "#player"); } catch (eh) {}
        }
        showDiag(["ensureNP opened via direct addClass, now=" + (n2 && n2.classList.contains("open"))]);
      }, 160);
    }, 120);
  }

  /* 捕获遥控器 OK 键模拟的鼠标 click（TCL/部分 Android TV 的 DPAD 中心键发 click 而非 keydown） */
  document.addEventListener("click", function (e) {
    if (!tvMode) return;
    var t = e.target;
    if (!t || !t.closest) return;
    var playable = t.closest(".album") || t.closest(".song") ||
                   t.closest(".ch-item") || t.closest(".pl-card") ||
                   t.closest(".duo-card") || t.id === "guessCard" || t.id === "radarCard";
    if (playable) ensureNowPlaying("click");
  }, true);

  /* ---------- SVG 图标渲染修复（老 Chromium 下播放/暂停等 SVG 图标可能歪斜） ----------
     preserveAspectRatio 是 SVG 属性不是 CSS 属性，需在元素上显式设置；
     同时给 play SVG 补 width/height 属性（原文件只设了 CSS 尺寸，老内核可能不认）。 */
  function fixSvgIcons() {
    if (!tvMode) return;
    var svgs = document.querySelectorAll(".np-controls svg, .np-tools svg, #npPlayIcon, #miniPlayIcon");
    for (var i = 0; i < svgs.length; i++) {
      var s = svgs[i];
      if (!s.getAttribute("preserveAspectRatio")) s.setAttribute("preserveAspectRatio", "xMidYMid meet");
      if (!s.getAttribute("width")) s.setAttribute("width", "28");
      if (!s.getAttribute("height")) s.setAttribute("height", "28");
      s.setAttribute("shape-rendering", "geometricPrecision");
    }
  }
  setTimeout(fixSvgIcons, 600);
  /* 播放页打开后再次修复（play/pause 切换时 innerHTML 会重建 path） */
  var _npObs = new MutationObserver(function () {
    var np = $("np");
    if (np && np.classList.contains("open")) fixSvgIcons();
  });
  setTimeout(function () {
    var np = $("np");
    if (np) _npObs.observe(np, { attributes: true, attributeFilter: ["class"] });
  }, 1000);

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
  function click(el) {
    if (!el) return;
    /* 老 TV 内核对非表单元素的 .click() 偶发不触发监听，
       回退到派发真实 MouseEvent（带 bubbles，让原应用的事件委托/onclick 都能收到） */
    try {
      el.click();
    } catch (e1) {
      try {
        var ev = new MouseEvent("click", { bubbles: true, cancelable: true, view: window });
        el.dispatchEvent(ev);
      } catch (e2) {}
    }
  }

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
        /* 老 TV 内核下 activeElement 可能是卡片内部子节点（如 img），
           取最近的可点击容器再触发，否则 click 落在子节点上原应用不响应 */
        var target = el.closest(".album,.song,.ch-item,.pl-card,.duo-card,.q-opt,.tab,.chip,.ch-tab,.search-tab,.lib-item,.np-lyrics,.np-art-wrap,.song-more,.q-opt,.plat-btn,.plat-menu button,.ch-refresh,.sec-link,.src-check,.field,.range,input,select,textarea,button,a,[role=button],#mini,#guessCard,#radarCard");
        if (!target) target = el;
        var okLines = [];
        okLines.push("OK target=" + (target.className || target.id || target.tagName));
        click(target);
        var playable = target.closest(".album") || target.closest(".song") ||
                       target.closest(".ch-item") || target.closest(".pl-card") ||
                       target.closest(".duo-card") || target.id === "guessCard" || target.id === "radarCard";
        okLines.push("playable=" + !!playable);
        showDiag(okLines);
        if (playable) {
          ensureNowPlaying("keydown-OK");
        }
      }
    }
  }, true);

  /* ---------- 屏幕调试浮层（TV 无 DevTools，常驻显示能力信息 + 最近交互） ---------- */
  var diagEl = null;
  var diagLines = ["[AQ TV diag] ready"];
  function showDiag(extra) {
    if (extra && extra.length) diagLines = diagLines.concat(extra);
    if (diagLines.length > 20) diagLines = diagLines.slice(-20);
    if (!diagEl) {
      diagEl = document.createElement("div");
      diagEl.id = "aq-diag";
      diagEl.style.cssText = "position:fixed;right:12px;top:12px;z-index:999999;background:rgba(0,0,0,.72);color:#7CFC00;font:11px/1.45 monospace;padding:7px 10px;border-radius:6px;max-width:380px;max-height:60vh;overflow:auto;white-space:pre-wrap;pointer-events:none;";
      document.body.appendChild(diagEl);
    }
    diagEl.textContent = diagLines.join("\n");
    if (tvMode) diagEl.style.display = "block";
  }
  /* TV 模式下常驻显示（含浏览器能力信息），便于在 TV 上直接看问题 */
  if (tvMode) {
    setTimeout(function () {
      var d = window.__aqDiag || {};
      showDiag([
        "UA=" + (ua || "").slice(0, 60),
        "vw=" + window.innerWidth + " vh=" + window.innerHeight + " dpr=" + (window.devicePixelRatio || 1),
        "aspectRatio=" + d.aspectRatio + " inset=" + d.inset + " cssMin=" + d.cssMin,
        "backdrop=" + d.backdropFilter + " flexGap=" + d.flexGap + " grid=" + d.grid,
        "press any key to see keyCode"
      ]);
    }, 1200);
  }
  window.addEventListener("keydown", function (e) {
    /* 记录所有按键，方便确认遥控器 OK 键到底发什么码 */
    showDiag(["key=" + (e.key || "?") + " code=" + (e.code || "?") + " kc=" + (e.keyCode || 0)]);
    if (e.key === "F3") {
      e.preventDefault();
      if (diagEl) diagEl.style.display = diagEl.style.display === "none" ? "block" : "none";
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

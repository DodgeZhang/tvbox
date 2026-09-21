# -*- coding: utf-8 -*-
"""
剧圈圈在线 (jqqzx.me) TVBox/hipy T4 Python Spider
- 仅手机端可访问（桌面 UA 返回 404），全程使用 Android 移动 UA
- MacCMS v10 变体，自定义 .module-poster-item 模板
- 分类: /vodshow/id/{slug}/page/{n}.html
- 详情: /vod/{id}.html
- 播放: /play/{vodid}-{sid}-{nid}.html → player_aaaa JSON → /jx/player.php?vid=
- 搜索: /index.php/ajax/suggest?mid=1&wd={key}&limit=50 (绕过搜索验证码)
- 解析: jx 页面 jsjiami v7 混淆需 JS 执行，且开头有 self==top 反嵌检查（顶层加载会
  把标题改成 404），故经 localProxy 返回全屏 iframe 包装页加载 jx 页（iframe 中
  self != top 检查通过）→ 站内 JS 解密 vid → DPlayer 拉 m3u8 → 客户端嗅探直链
- 依赖: requests (hipy 自带)，lxml 可选（无则用 re 兜底）
"""
import sys
import re
import json
import base64
import requests
from urllib.parse import urljoin, quote

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        """本地开发时兜底，hipy 运行时会用 base.spider.Spider"""
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            kw.pop('verify', None)
            r = requests.get(url, headers=headers, timeout=15, verify=False, **kw)
            r.encoding = r.apparent_encoding or 'utf-8'
            return r

# lxml 可选
try:
    from lxml import etree
    _HAS_LXML = True
except ImportError:
    _HAS_LXML = False


HOST = "https://www.jqqzx.me"
UA = ("Mozilla/5.0 (Linux; Android 12; Pixel 6) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Mobile Safari/537.36")

CATEGORIES = [
    {"type_id": "dianying", "type_name": "电影"},
    {"type_id": "juji",     "type_name": "剧集"},
    {"type_id": "dongman",  "type_name": "动漫"},
    {"type_id": "zongyi",   "type_name": "综艺"},
    {"type_id": "duanju",   "type_name": "短剧"},
]


class Spider(Spider):
    def getName(self):
        return "剧圈圈在线"

    def init(self, extend=""):
        self.host = HOST.rstrip("/")
        self.ua = UA
        self.headers = {
            "User-Agent": self.ua,
            "Referer": self.host + "/",
        }
        self.categories = list(CATEGORIES)

    # ---------- 基础工具 ----------
    def _fetch(self, url, headers=None, t=15000):
        hd = headers or self.headers
        try:
            return self.fetch(url, headers=hd, timeout=t, verify=False)
        except TypeError:
            return self.fetch(url, headers=hd, timeout=t)
        except Exception:
            return None

    def _get(self, url, t=15000):
        """GET 请求返回文本，失败返回空串"""
        r = self._fetch(url, t=t)
        if r is None:
            return ""
        try:
            return r.text if hasattr(r, 'text') else str(r.content or b"", "utf-8", "ignore")
        except Exception:
            return ""

    def _post(self, url, data=None, headers=None, t=15000):
        hd = headers or self.headers
        try:
            r = requests.post(url, data=data or {}, headers=hd, timeout=t / 1000.0,
                              verify=False)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception:
            return ""

    def _fix(self, url):
        """相对 URL 补全为绝对 URL"""
        if not url:
            return ""
        return urljoin(self.host + "/", url)

    def _e64(self, s):
        return base64.b64encode(str(s).encode("utf-8")).decode("utf-8")

    def _d64(self, s):
        s = str(s)
        return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "ignore")

    def _wrap_proxy(self, target):
        """构造 localProxy 包装页地址（hipy 9978 端口 do=py 路由）"""
        return "http://127.0.0.1:9978/proxy?do=py&url=" + quote(self._e64(target), safe='')

    # ---------- 列表解析（re 正则，不依赖 lxml） ----------
    def _list(self, html):
        """从 HTML 中提取视频列表
        选择器: a.module-poster-item → href=/vod/{id}.html, img[data-original], .module-item-note
        """
        out = []
        seen = set()
        # jqqzx 列表项: <a href="/vod/{id}.html" title="{name}" class="module-poster-item module-item">
        # 内部结构复杂，分两段正则匹配
        # 先用大正则找每个 a.module-poster-item 块
        block_re = re.compile(
            r'<a\s[^>]*class="[^"]*module-poster-item[^"]*"[^>]*>(.*?)</a>',
            re.S | re.I
        )
        # 也匹配 title 在 class 前面的顺序
        block_re2 = re.compile(
            r'<a\s[^>]*?href="([^"]*/vod/(\d+)\.html)"[^>]*>(.*?)</a>',
            re.S | re.I
        )
        # 实际用 block_re2 + 过滤 class
        for m in block_re2.finditer(html or ""):
            href = m.group(1)
            vid = m.group(2)
            body = m.group(3)
            # 检查 class 是否含 module-poster-item
            block_start = m.start()
            prefix = html[max(0, block_start - 200):block_start]
            # 从 a 标签自身找 class
            a_start = html.rfind('<a', 0, block_start + 50)
            if a_start < 0:
                continue
            a_tag = html[a_start:block_start + 500]
            if 'module-poster-item' not in a_tag:
                continue
            if not vid or vid in seen:
                continue
            seen.add(vid)
            # 标题: a 的 title 属性
            title_m = re.search(r'title="([^"]*)"', a_tag)
            name = (title_m.group(1).strip() if title_m else "")
            if not name:
                # img alt
                alt_m = re.search(r'alt="([^"]*)"', body)
                name = (alt_m.group(1).strip() if alt_m else "")
            if not name:
                # .module-poster-item-title 文本
                pt_m = re.search(r'class="module-poster-item-title"[^>]*>(.*?)<', body, re.S)
                name = (re.sub(r'<[^>]+>', '', pt_m.group(1)).strip() if pt_m else vid)
            # 图片: data-original > data-src > src
            pic = ""
            orig_m = re.search(r'data-original="([^"]*)"', body)
            if orig_m:
                pic = orig_m.group(1)
            else:
                src_m = re.search(r'data-src="([^"]*)"', body)
                if src_m:
                    pic = src_m.group(1)
                else:
                    src_m2 = re.search(r'\bsrc="(https?://[^"]+)"', body)
                    if src_m2:
                        pic = src_m2.group(1)
            pic = self._fix(pic)
            # 备注: .module-item-note
            note = ""
            note_m = re.search(r'class="module-item-note"[^>]*>(.*?)<', body, re.S)
            if note_m:
                note = re.sub(r'<[^>]+>', '', note_m.group(1)).strip()
            out.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": note,
            })
        return out

    def _pagecount(self, html, pg):
        """从分类页提取总页数
        jqqzx 分页: <a class="page-link page-next" title="尾页" href="/vodshow/id/{slug}/page/{N}.html">尾页</a>
        """
        try:
            # 优先: 找尾页链接里的最大页码
            last_m = re.search(
                r'href="([^"]*/page/(\d+)\.html)"[^>]*title="尾页"',
                html or "", re.I
            )
            if last_m:
                return int(last_m.group(2))
            # 兜底: 收集所有 page 链接里的最大数字
            nums = [int(m.group(1)) for m in re.finditer(r'/page/(\d+)\.html', html or "")
                    if m.group(1).isdigit()]
            if nums:
                return max(nums)
            # 再兜底: 看是否有下一页
            has_next = bool(re.search(
                r'class="[^"]*page-next[^"]*"[^>]*(?:title="[^"]*下一页[^"]*"[^>]*)?>下一页',
                html or "", re.S | re.I
            ))
            return max(nums + [pg + (1 if has_next else 0)])
        except Exception:
            return pg

    # ---------- 六接口 ----------
    def homeContent(self, filter):
        html = self._get(self.host)
        return {
            "class": self.categories,
            "list": self._list(html),
            "filters": {},
        }

    def homeVideoContent(self):
        html = self._get(self.host)
        return {"list": self._list(html)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = max(int(str(pg)), 1)
        except Exception:
            pg = 1
        cat = str(tid)
        # 真实分类 URL: /vodshow/id/{slug}/page/{n}.html
        if pg > 1:
            url = f"{self.host}/vodshow/id/{cat}/page/{pg}.html"
        else:
            url = f"{self.host}/vodshow/id/{cat}.html"
        html = self._get(url)
        items = self._list(html)
        limit = len(items) or 20
        pagecount = self._pagecount(html, pg)
        return {
            "page": pg,
            "pagecount": pagecount,
            "limit": limit,
            "total": pagecount * limit,
            "list": items,
        }

    def detailContent(self, ids):
        out = []
        for vid in ids:
            try:
                html = self._get(f"{self.host}/vod/{vid}.html")
                if not html:
                    continue
                # 标题: h1.module-info-heading 或 第一个 h1
                name = ""
                h1_m = re.search(
                    r'<h1[^>]*class="[^"]*module-info-heading[^"]*"[^>]*>(.*?)</h1>',
                    html, re.S | re.I
                )
                if h1_m:
                    name = re.sub(r'<[^>]+>', '', h1_m.group(1)).strip()
                if not name:
                    h1_m2 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S | re.I)
                    if h1_m2:
                        name = re.sub(r'<[^>]+>', '', h1_m2.group(1)).strip()
                if not name:
                    name = str(vid)

                # 封面: .module-item-pic img data-original / .module-info-poster img / lazy img
                pic = ""
                for pat in [
                    r'class="[^"]*module-item-pic[^"]*"[^>]*>.*?data-original="([^"]+)"',
                    r'class="[^"]*module-info-poster[^"]*"[^>]*>.*?data-original="([^"]+)"',
                    r'class="[^"]*lazy[^"]*"[^>]*>.*?data-original="([^"]+)"',
                ]:
                    m = re.search(pat, html, re.S | re.I)
                    if m:
                        pic = m.group(1)
                        break
                pic = self._fix(pic)

                # 简介
                desc = ""
                for pat in [
                    r'class="[^"]*module-info-introduction[^"]*"[^>]*>(.*?)</div>',
                    r'class="[^"]*content_info[^"]*"[^>]*>(.*?)</div>',
                ]:
                    m = re.search(pat, html, re.S | re.I)
                    if m:
                        desc = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                        break

                # 类型/年代/演员/导演/地区
                type_name = ""
                year = ""
                actor = ""
                director = ""
                area = ""
                # .module-info-item 结构: title / content 成对出现
                item_re = re.compile(
                    r'class="module-info-item-title"[^>]*>(.*?)</div>.*?'
                    r'class="module-info-item-content"[^>]*>(.*?)</div>',
                    re.S | re.I
                )
                for m in item_re.finditer(html):
                    label = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                    value = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                    low = label.lower()
                    if "演员" in label or "主演" in label:
                        actor = value
                    elif "导演" in label:
                        director = value
                    elif "地区" in label:
                        area = value
                    elif "年份" in label or "年代" in label:
                        year = value
                    elif "类型" in label or "分类" in label:
                        type_name = value

                # 线路名: tab-item 的 data-dropdown-value 或文本（去末尾集数数字）
                tab_names = []
                tab_re = re.compile(
                    r'class="[^"]*module-tab-item[^"]*"[^>]*data-dropdown-value="([^"]+)"',
                    re.I
                )
                for m in tab_re.finditer(html):
                    txt = m.group(1).strip()
                    if txt:
                        tab_names.append(txt)
                if not tab_names:
                    # 兜底: 从 span 文本提
                    tab_re2 = re.compile(
                        r'class="[^"]*module-tab-item[^"]*"[^>]*>.*?<span>(.*?)</span>',
                        re.S | re.I
                    )
                    for m in tab_re2.finditer(html):
                        txt = m.group(1).strip()
                        if txt:
                            txt = re.sub(r'\s*\d+\s*$', '', txt).strip()
                            if txt:
                                tab_names.append(txt)

                # 播放列表块: .module-play-list-content (按出现顺序)
                panel_re = re.compile(
                    r'<div[^>]*class="[^"]*module-play-list-content[^"]*"[^>]*>(.*?)</div>\s*</div>',
                    re.S | re.I
                )
                panels = panel_re.findall(html)
                if not panels:
                    # 更宽松匹配
                    panel_re2 = re.compile(
                        r'class="[^"]*module-play-list-content[^"]*"[^>]*>(.*?)(?=<div[^>]*class=|\Z)',
                        re.S | re.I
                    )
                    panels = panel_re2.findall(html)

                fs = []
                us = []
                for i, panel in enumerate(panels):
                    source = tab_names[i] if i < len(tab_names) else f"线路{i + 1}"
                    # 每集: <a class="module-play-list-link" href="/play/xxx-{sid}-{nid}.html" title="播放xxx第N集"><span>第N集</span></a>
                    ep_re = re.compile(
                        r'<a\s[^>]*class="[^"]*module-play-list-link[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                        re.S | re.I
                    )
                    links = []
                    for em in ep_re.finditer(panel):
                        href = em.group(1)
                        if not href:
                            continue
                        ep_text = re.sub(r'<[^>]+>', '', em.group(2)).strip()
                        if not ep_text:
                            title_m = re.search(r'title="([^"]*)"', em.group(0))
                            if title_m:
                                ep_text = title_m.group(1).strip()
                        links.append(ep_text + "$" + href)
                    if links:
                        fs.append(source)
                        us.append("#".join(links))

                out.append({
                    "vod_id": str(vid),
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_content": desc,
                    "vod_year": year,
                    "vod_area": area,
                    "vod_actor": actor,
                    "vod_director": director,
                    "vod_play_from": "$$$".join(fs),
                    "vod_play_url": "$$$".join(us),
                })
            except Exception:
                continue
        return {"list": out}

    def searchContent(self, key, quick, pg="1"):
        """搜索走 MacCMS suggest 接口绕过验证码"""
        try:
            url = f"{self.host}/index.php/ajax/suggest"
            params = {"mid": 1, "wd": key, "limit": 50}
            hd = {**self.headers, "Accept": "application/json, text/plain, */*"}
            r = self._fetch(url, headers=hd, t=15000)
            if r is None:
                return {"list": [], "page": int(pg) if str(pg).isdigit() else 1}
            try:
                data = r.json()
            except Exception:
                txt = r.text if hasattr(r, 'text') else ""
                data = json.loads(txt) if txt else {}
            items = []
            for it in data.get("list", []) or []:
                items.append({
                    "vod_id": str(it.get("id", "")),
                    "vod_name": it.get("name", ""),
                    "vod_pic": it.get("pic", ""),
                    "vod_remarks": "",
                })
            return {"list": items, "page": int(pg) if str(pg).isdigit() else 1}
        except Exception:
            return {"list": [], "page": int(pg) if str(pg).isdigit() else 1}

    def playerContent(self, flag, id, vipFlags=None):
        """播放解析
        id 形如 /play/93678-10-1.html
        注意1: 播放页页脚有触屏劫持广告脚本（touchend 跳转 ezze0ct.com → 纯爱导航站），
        不能让 WebView 加载播放页，否则嗅探器被广告劫持。
        注意2: jx/player.php 混淆代码开头有反嵌检查 self==top → $('title').text('404')，
        WebView 顶层直连 jx URL 会把标题改成 404 并破坏播放器（APP 实测 title=404）。
        正确做法: Python 端提取 player_aaaa.url（encrypt=0 时为 jx vid 密文，不解密），
        经 localProxy 返回全屏 iframe 包装页加载 jx 播放器页（iframe 中 self != top），
        站内 JS 解密出 m3u8 → DPlayer 播放 → 客户端嗅探到直链。
        """
        try:
            play_url = self._fix(id) if id and id.startswith("/") else (id or "")
            html = self._get(play_url, t=8000)
            hd = {"User-Agent": self.ua}
            vid = ""
            if html:
                m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.S)
                if not m:
                    m = re.search(r'player_aaaa\s*=\s*(\{.*?\})', html, re.S)
                if m:
                    try:
                        pd = json.loads(m.group(1))
                    except Exception:
                        pd = {}
                    vid = pd.get("url", "") or ""
                    encrypt = str(pd.get("encrypt", "0"))
                    if encrypt == "1" and vid:
                        try:
                            from urllib.parse import unescape as _u
                            vid = _u(vid)
                        except Exception:
                            pass
                    elif encrypt == "2" and vid:
                        try:
                            from urllib.parse import unescape as _u
                            vid = _u(base64.b64decode(vid).decode("utf-8", "ignore"))
                        except Exception:
                            pass
            if vid:
                # vid 与站内真实 iframe 拼接方式保持一致（不做 percent-encode，
                # 与 MacPlayer.Parse + PlayUrl 行为对齐；base64 密文含 +/= 时
                # getQueryString 按原文读取才能正确解密）
                jx_url = f"{self.host}/jx/player.php?vid={vid}"
                return {
                    "parse": 1,
                    "playUrl": "",
                    "url": self._wrap_proxy(jx_url),
                    "header": hd,
                }
            # 兜底: 拿不到 vid 时嗅探播放页（可能被广告劫持，成功率低）
            return {
                "parse": 1,
                "playUrl": "",
                "url": play_url,
                "header": hd,
            }
        except Exception:
            play_url = self._fix(id) if id and id.startswith("/") else (id or "")
            return {
                "parse": 1,
                "playUrl": "",
                "url": play_url,
                "header": {"User-Agent": self.ua},
            }

    def localProxy(self, param):
        """本地代理：返回全屏 iframe 包装页。
        jx/player.php 只允许在 iframe 中运行（self==top 反嵌），包装页提供 iframe
        上下文；jx 页内 DPlayer/hls.js 从 www.jqqzx.me 原域加载并请求 m3u8，
        客户端嗅探器（shouldInterceptRequest 覆盖所有子框架请求）捕获直链。
        """
        try:
            raw = ""
            if isinstance(param, dict):
                raw = param.get("url", "") or ""
            elif param:
                raw = str(param)
            target = ""
            if raw:
                try:
                    target = self._d64(raw)
                except Exception:
                    try:
                        from urllib.parse import unquote as _uq
                        target = self._d64(_uq(raw))
                    except Exception:
                        target = ""
            if not target.startswith("http"):
                return [404, "text/plain", "", ""]
            page = (
                '<!DOCTYPE html><html><head><meta charset="utf-8">'
                '<meta name="referrer" content="no-referrer">'
                '<title>剧圈圈在线</title>'
                '<style>html,body{margin:0;padding:0;width:100%;height:100%;'
                'background:#000;overflow:hidden}'
                'iframe{position:absolute;left:0;top:0;width:100%;height:100%;'
                'border:0}</style></head><body>'
                f'<iframe src="{target}" allowfullscreen="true" frameborder="0" '
                'scrolling="no"></iframe></body></html>'
            )
            return [200, "text/html; charset=utf-8", page, ""]
        except Exception:
            return [404, "text/plain", "", ""]

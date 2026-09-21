#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
剧圈圈在线 (jqqzx.me) TVBox/hipy T4 Python Spider
- 仅手机端可访问（桌面 UA 返回 404），全程使用 Android 移动 UA
- MacCMS v10 变体，自定义 .module-poster-item 模板
- 分类: /vodshow/id/{slug}/page/{n}.html
- 详情: /vod/{id}.html
- 播放: /play/{vodid}-{sid}-{nid}.html → player_aaaa JSON → /jx/player.php?vid=
- 搜索: /index.php/ajax/suggest?mid=1&wd={key}&limit=50 (绕过搜索验证码)
- 解析: 所有线路 ps=1，jx 页面 jsjiami v7 混淆需 JS 执行 → parse:1 由客户端嗅探
"""
import json
import re
from urllib.parse import urljoin, urlparse, quote
import requests
from lxml import etree
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "剧圈圈在线"

    def init(self, extend=""):
        self.name = "剧圈圈在线"
        self.host = "https://www.jqqzx.me"
        # 移动 UA 必需，桌面 UA 会被 JS 重定向到 404
        self.ua = ("Mozilla/5.0 (Linux; Android 12; Pixel 6) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Mobile Safari/537.36")
        self.headers = {
            "User-Agent": self.ua,
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        # MacCMS v10 分类 slug（从首页导航提取）
        self.categories = [
            {"type_id": "dianying", "type_name": "电影"},
            {"type_id": "juji",     "type_name": "剧集"},
            {"type_id": "dongman",  "type_name": "动漫"},
            {"type_id": "zongyi",   "type_name": "综艺"},
            {"type_id": "duanju",   "type_name": "短剧"},
        ]
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        # 禁用 HTTPS 校验（部分 CDN 证书问题）
        self.session.verify = False

    # ---------- 基础工具 ----------
    def _get(self, url, timeout=20):
        """GET 请求，统一返回文本；失败返回空串"""
        try:
            r = self.session.get(url, headers=self.headers, timeout=timeout,
                                  proxies=self.session.proxies or None)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception:
            return ""

    def _post(self, url, data=None, timeout=20):
        try:
            r = self.session.post(url, data=data or {}, headers=self.headers,
                                  timeout=timeout, proxies=self.session.proxies or None)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception:
            return ""

    def _fix(self, url):
        """相对 URL 补全为绝对 URL"""
        return urljoin(self.host + "/", url or "")

    def _text(self, node):
        """提取节点内全部文本并合并空白"""
        if node is None:
            return ""
        return " ".join("".join(node.xpath(".//text()")).split())

    # ---------- 列表解析 ----------
    def _list(self, html):
        """从分类/搜索/首页 HTML 中提取视频列表
        选择器: a.module-poster-item → href=/vod/{id}.html, img[data-original], .module-item-note
        """
        tree = etree.HTML(html or "")
        out = []
        seen = set()
        # jqqzx 用 module-poster-item 作为列表项锚点
        items = tree.xpath('//a[contains(@class,"module-poster-item")]')
        for a in items:
            try:
                href = a.get("href", "")
                m = re.search(r"/vod/(\d+)\.html", href)
                if not m:
                    continue
                vid = m.group(1)
                if vid in seen:
                    continue
                seen.add(vid)
                # 图片懒加载在 data-original
                img = a.xpath('.//img')
                pic = ""
                if img:
                    pic = (img[0].get("data-original")
                           or img[0].get("data-src")
                           or img[0].get("src") or "")
                pic = self._fix(pic)
                # 标题优先 title 属性，再 img alt，再 .module-poster-item-title
                name = (a.get("title") or "").strip()
                if not name and img:
                    name = (img[0].get("alt") or "").strip()
                if not name:
                    name = self._text(a.xpath('.//*[contains(@class,"module-poster-item-title")]')[0]) \
                        if a.xpath('.//*[contains(@class,"module-poster-item-title")]') else vid
                # 备注: HD/1080P/正片 等
                note = ""
                note_nodes = a.xpath('.//*[contains(@class,"module-item-note")]')
                if note_nodes:
                    note = self._text(note_nodes[0])
                out.append({
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": note,
                })
            except Exception:
                continue
        return out

    def _pagecount(self, html, pg):
        """从分类页 HTML 提取总页数
        jqqzx 分页: <a class="page-link page-next" title="尾页" href="/vodshow/id/{slug}/page/{N}.html">尾页</a>
        """
        try:
            tree = etree.HTML(html or "")
            # 找 "尾页" 链接里的最大页码
            last = tree.xpath('//a[contains(text(),"尾页") or contains(@title,"尾页")]')
            if last:
                href = last[0].get("href", "")
                m = re.search(r"/page/(\d+)", href)
                if m:
                    return int(m.group(1))
            # 兜底: 收集所有 page 链接里的最大数字
            nums = []
            for a in tree.xpath('//a[contains(@class,"page-link")]'):
                href = a.get("href", "")
                m = re.search(r"/page/(\d+)", href)
                if m:
                    nums.append(int(m.group(1)))
            if nums:
                return max(nums)
            # 再兜底: 看是否有"下一页"链接
            nxt = tree.xpath('//a[contains(@class,"page-next") and (contains(text(),"下一页") or contains(@title,"下一页"))]')
            return max(nums + [pg + (1 if nxt else 0)])
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
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        # 真实分类 URL: /vodshow/id/{slug}/page/{n}.html
        # 注: /type/{slug}.html 是"分类首页"，不分页；真正分页在 /vodshow/id/{slug}/page/{n}.html
        if pg > 1:
            url = f"{self.host}/vodshow/id/{tid}/page/{pg}.html"
        else:
            url = f"{self.host}/vodshow/id/{tid}.html"
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
                tree = etree.HTML(html)
                # 标题
                name = (self._text(tree.xpath('//h1[contains(@class,"module-info-heading")]')[0])
                        if tree.xpath('//h1[contains(@class,"module-info-heading")]')
                        else (self._text(tree.xpath('//h1')[0]) if tree.xpath('//h1') else str(vid)))
                # 封面
                pic = ""
                pic_nodes = tree.xpath('//div[contains(@class,"module-item-pic")]//img/@data-original')
                if not pic_nodes:
                    pic_nodes = tree.xpath('//div[contains(@class,"module-info-poster")]//img/@data-original')
                if not pic_nodes:
                    pic_nodes = tree.xpath('//img[contains(@class,"lazy")]/@data-original')
                if pic_nodes:
                    pic = self._fix(pic_nodes[0])
                # 简介
                desc = ""
                desc_nodes = tree.xpath('//div[contains(@class,"module-info-introduction") or contains(@class,"content_info")]')
                if desc_nodes:
                    desc = self._text(desc_nodes[0])
                # 类型/年代/演员/导演
                type_name = ""
                year = ""
                actor = ""
                director = ""
                area = ""
                # 通用: 在 .module-info-tag 里找
                for tag in tree.xpath('//div[contains(@class,"module-info-tag")]//a'):
                    txt = self._text(tag)
                    if not type_name and txt:
                        type_name = txt
                    # 不做更精细区分
                # 信息项 (module-info-item)
                for li in tree.xpath('//div[contains(@class,"module-info-items")]//div[contains(@class,"module-info-item")]'):
                    label = self._text(li.xpath('.//*[contains(@class,"module-info-item-title")]')[0]) \
                        if li.xpath('.//*[contains(@class,"module-info-item-title")]') else ""
                    value = self._text(li.xpath('.//*[contains(@class,"module-info-item-content")]')[0]) \
                        if li.xpath('.//*[contains(@class,"module-info-item-content")]') else ""
                    low = label.lower()
                    if "演员" in label or "主演" in label or "actor" in low:
                        actor = value
                    elif "导演" in label or "director" in low:
                        director = value
                    elif "地区" in label or "area" in low:
                        area = value
                    elif "年份" in label or "year" in low or "年代" in label:
                        year = value
                    elif "类型" in label or "class" in low or "分类" in label:
                        if not type_name:
                            type_name = value
                # 线路名: 从 tab 提取 (按出现顺序)
                tab_names = []
                for tab in tree.xpath('//div[contains(@class,"module-tab-items-box")]//div[contains(@class,"module-tab-item")]'):
                    txt = self._text(tab)
                    if txt:
                        # 去掉末尾的集数小数字 <small>22</small>
                        txt = re.sub(r"\s*\d+\s*$", "", txt).strip()
                        if txt:
                            tab_names.append(txt)
                # 播放列表块: .module-play-list-content (按出现顺序对应 tab)
                panels = tree.xpath('//div[contains(@class,"module-play-list-content")]')
                fs = []
                us = []
                for i, panel in enumerate(panels):
                    # 线路名兜底
                    if i < len(tab_names):
                        source = tab_names[i]
                    else:
                        source = f"线路{i + 1}"
                    eps = panel.xpath('.//a[contains(@class,"module-play-list-link")]')
                    links = []
                    for a in eps:
                        href = a.get("href", "")
                        if not href:
                            continue
                        # 集名: a 内 span 文本，或 title 属性去掉前缀
                        ep_text = self._text(a) or ""
                        if not ep_text:
                            title = a.get("title", "")
                            m_t = re.search(r"第?\d+[集話]", title)
                            ep_text = m_t.group(0) if m_t else ""
                        # play_id 用原始相对路径 (/play/xxx-yyy-zzz.html)，client 端用此路径再次请求
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
        """搜索走 MacCMS suggest 接口绕过验证码
        /index.php/ajax/suggest?mid=1&wd={key}&limit=50
        返回 JSON: {"list":[{"id","name","en","pic"}]}
        """
        try:
            url = f"{self.host}/index.php/ajax/suggest"
            params = {"mid": 1, "wd": key, "limit": 50}
            r = self.session.get(url, params=params, headers=self.headers,
                                 timeout=15, proxies=self.session.proxies or None)
            data = r.json()
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

    def playerContent(self, flag, id, vipFlags):
        """播放解析
        id 形如 /play/93678-10-1.html
        访问播放页 → 提取 player_aaaa JSON → decrypt (encrypt 0/1/2) → 取 url
        因 jx 解析页 (/jx/player.php?vid={url}) 是 jsjiami v7 混淆需 JS 执行，
        无法在 Python 端解出真实 m3u8，故 parse:1 让客户端 webview 嗅探。
        这里把 url 传给客户端，并附 Referer 让 webview 加载 jx 解析页。
        """
        try:
            play_url = self._fix(id) if id.startswith("/") else id
            html = self._get(play_url)
            # 提取 player_aaaa = {...}
            m = re.search(r"player_aaaa\s*=\s*(\{.*?\})\s*</script>", html, re.S)
            if not m:
                m = re.search(r"player_aaaa\s*=\s*(\{.*?\})", html, re.S)
            player_data = {}
            if m:
                try:
                    player_data = json.loads(m.group(1))
                except Exception:
                    # MacCMS 有时是 JS 对象字面量，用单引号或没引号的 key
                    try:
                        raw = m.group(1)
                        # 把 key 加双引号
                        raw2 = re.sub(r"([{,]\s*)([a-zA-Z_]\w*)\s*:", r'\1"\2":', raw)
                        player_data = json.loads(raw2)
                    except Exception:
                        player_data = {}
            url = player_data.get("url", "")
            encrypt = str(player_data.get("encrypt", "0"))
            # MacCMS decrypt 规则
            if encrypt == "1":
                # unescape
                try:
                    from urllib.parse import unescape
                    url = unescape(url)
                except Exception:
                    pass
            elif encrypt == "2":
                # unescape(base64decode(url))
                try:
                    import base64
                    from urllib.parse import unescape
                    url = unescape(base64.b64decode(url).decode("utf-8", "ignore"))
                except Exception:
                    pass
            # 构造 jx 解析 URL: 站点根 + /jx/player.php?vid={url}
            # 因为 pcfg.js 中所有 player 都 ps=1，parse=/jx/player.php?vid=
            jx_url = f"{self.host}/jx/player.php?vid={quote(url, safe='')}"
            # parse=1 客户端嗅探；referer 给站点根，让 webview 能加载解析页
            header = {
                "User-Agent": self.ua,
                "Referer": play_url,
            }
            return {
                "parse": 1,
                "url": jx_url,
                "header": json.dumps(header),
            }
        except Exception:
            return {"parse": 1, "url": self._fix(id) if id.startswith("/") else id, "header": json.dumps({"User-Agent": self.ua})}

    def localProxy(self, params):
        # 本源不需要本地代理（图片走 https 直链，视频走客户端 webview 嗅探）
        return None

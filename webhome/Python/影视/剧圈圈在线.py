# -*- coding: utf-8 -*-
"""
剧圈圈在线 (jqqzx.me) TVBox/hipy T4 Python Spider
- 仅手机端可访问（桌面 UA 返回 404），全程使用 Android 移动 UA
- MacCMS v10 变体，自定义 .module-poster-item 模板
- 分类: /vodshow/id/{slug}/page/{n}.html
- 详情: /vod/{id}.html
- 播放: /play/{vodid}-{sid}-{nid}.html → player_aaaa JSON → vid
- 搜索: /index.php/ajax/suggest?mid=1&wd={key}&limit=50 (绕过搜索验证码)
- 解析: Python 直接 POST /jx/api.php (body: vid=xxx) 换取加密播放地址，
  再本地解密出真实直链（移动云 S3 预签名 mp4/m3u8，24h 有效），parse:0 直播。
  解密算法（逆向自 jx 页 jsjiami v7 混淆代码，已浏览器端到端验证一致）:
    1) base64 标准解码密文
    2) 逐字节 XOR md5('test') 的 hex 串 (098f6bcd...) 循环
    3) 宽容 base64 解码（跳过非法字符，4字符一组，余3出2字节/余2出1字节/余1丢弃）
       → 得到 "表A_b64/表B_b64/数据_b64" 三段文本（'/' 分隔）
    4) 表A/表B 各自宽容 b64 解码为 26 字母替换表的 JSON 文本，再 JSON.stringify 加引号
    5) 数据段宽容 b64 解码后逐字符替换: 字母且在表A文本中 → out += A文本[B文本.indexOf(ch)]
       （大小写敏感，非字母原样保留；与站内 out += k2[k1.indexOf(ch)] 一致）
- 依赖: requests (hipy 自带)，lxml 可选（无则用 re 兜底）
"""
import sys
import re
import json
import base64
import hashlib
import requests
from urllib.parse import urljoin

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

    # ---------- 播放地址解密（逆向自 jx/player.php 混淆 JS） ----------
    _B64_LEGAL = set(
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    )
    _XOR_KEY = hashlib.md5(b"test").hexdigest()  # 098f6bcd4621d373cade4e832627b4f6

    @classmethod
    def _lenient_b64(cls, data):
        """宽容 base64 解码（复刻站内 Base64.decode）:
        跳过字母表外字符，按 4 字符一组解码；余 3 出 2 字节、余 2 出 1 字节、余 1 丢弃
        """
        if isinstance(data, str):
            data = data.encode("latin-1", "ignore")
        valid = bytes(c for c in data if c in cls._B64_LEGAL)
        n = len(valid) // 4 * 4
        out = bytearray()
        try:
            out += base64.b64decode(valid[:n])
        except Exception:
            pass
        rem = valid[n:]
        try:
            if len(rem) == 3:
                out += base64.b64decode(rem + b"=")
            elif len(rem) == 2:
                out += base64.b64decode(rem + b"==")
        except Exception:
            pass
        return bytes(out)

    @classmethod
    def _sign_url(cls, cipher):
        """把 /jx/api.php 返回的加密 url 解密为真实直链"""
        try:
            raw = base64.b64decode(cipher)
        except Exception:
            return ""
        key = cls._XOR_KEY
        xored = bytes(c ^ ord(key[i % len(key)]) for i, c in enumerate(raw))
        text = cls._lenient_b64(xored).decode("latin-1", "ignore")
        parts = text.split("/")
        if len(parts) < 3:
            return ""
        # 与站内 sign() 对齐: k1 = stringify(解码 parts[1])，k2 = stringify(解码 parts[0])
        k1 = json.dumps(cls._lenient_b64(parts[1]).decode("latin-1", "ignore"))
        k2 = json.dumps(cls._lenient_b64(parts[0]).decode("latin-1", "ignore"))
        data = cls._lenient_b64("/".join(parts[2:])).decode("latin-1", "ignore")
        out = []
        for ch in data:
            if ("a" <= ch <= "z" or "A" <= ch <= "Z") and ch in k2:
                try:
                    out.append(k2[k1.index(ch)])
                except ValueError:
                    out.append(ch)
            else:
                out.append(ch)
        return "".join(out)

    def _resolve_play(self, vid):
        """POST /jx/api.php 用 vid 换取并解密真实播放直链，失败返回空串"""
        try:
            # requests 传 dict 会正确 percent-encode（vid 中的 + → %2B）
            r = requests.post(
                f"{self.host}/jx/api.php",
                data={"vid": vid},
                headers={"User-Agent": self.ua},
                timeout=15,
                verify=False,
            )
            r.encoding = "utf-8"
            j = r.json()
            cipher = (j.get("data") or {}).get("url", "") or ""
            if not cipher:
                return ""
            if cipher.startswith("http"):  # 服务端偶尔直接返回明文
                return cipher
            url = self._sign_url(cipher)
            return url if url.startswith("http") else ""
        except Exception:
            return ""

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
        """播放解析（直链方案，无需 WebView）
        id 形如 /play/93678-10-1.html
        流程: 播放页提 player_aaaa.url(vid 密文) → POST /jx/api.php 换加密地址
        → 本地解密出移动云 S3 预签名直链（24h 有效，无 Referer/UA 校验）→ parse:0
        注意: 播放页页脚有触屏劫持广告脚本，绝不能让 WebView 加载播放页嗅探。
        """
        hd = {"User-Agent": self.ua}
        try:
            play_url = self._fix(id) if id and id.startswith("/") else (id or "")
            html = self._get(play_url, t=8000)
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
            if not vid:
                return {"parse": 1, "playUrl": "", "url": play_url, "header": hd}
            # 个别线路 player_aaaa.url 本身就是直链
            if vid.startswith("http"):
                return {"parse": 0, "playUrl": "", "url": vid, "header": hd}
            # 常规: vid 密文 → api.php 换真实直链
            url = self._resolve_play(vid)
            if url:
                return {"parse": 0, "playUrl": "", "url": url, "header": hd}
            # 兜底: api 失败时交 jx 页给客户端嗅探
            return {
                "parse": 1,
                "playUrl": "",
                "url": f"{self.host}/jx/player.php?vid={vid}",
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
        """本地代理占位（当前播放链路已直链化，不再使用包装页）"""
        return [404, "text/plain", "", ""]

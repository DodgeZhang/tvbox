# -*- coding: utf-8 -*-
"""qlys影视 (https://www.qlys.cc) - TVBox/OK影视"""

import re, json, time, threading
from urllib.parse import quote, urlencode

import requests
from requests.adapters import HTTPAdapter

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except ImportError:
    ThreadPoolExecutor = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import urllib3; urllib3.disable_warnings()
except Exception:
    pass

try:
    import sys; sys.path.append('..')
    from base.spider import Spider as _Base
except ImportError:
    _Base = object

HOST = "https://www.qlys.cc"
MIRRORS = ["https://qlys.cc"]
UA = ("Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

AREAS = "大陆 香港 台湾 美国 法国 英国 日本 韩国 德国 泰国 印度 新加坡 其他".split()
YEARS = [str(y) for y in range(2026, 2005, -1)]

CATS = [
    ("1", "电影",   [("10","动作片"),("11","恐怖片"),("12","科幻片"),("13","战争片"),
                     ("14","爱情片"),("15","喜剧片"),("16","剧情片"),("17","记录片")]),
    ("2", "电视剧", [("6","国产剧"),("7","港台剧"),("8","日韩剧"),("9","欧美剧"),("22","泰国剧")]),
    ("3", "短剧",   [("30","女频恋爱"),("31","反转爽剧"),("32","脑洞悬疑"),
                     ("33","古装仙侠"),("34","年代穿越"),("35","现代都市")]),
    ("4", "动漫",   [("40","国产动漫"),("41","日本动漫"),("42","欧美动漫"),("43","海外动漫")]),
    ("5", "综艺",   [("50","大陆综艺"),("51","日韩综艺"),("52","港台综艺"),("53","欧美综艺")]),
]

PLAY_BTN = re.compile(r'^(播放|立即播放|点击播放|在线播放|正片|选集|播放全集|开始播放)$')
ALL_OPT = lambda items: [{"n": "全部", "v": ""}] + items

ALL_CLASSES = [{"type_id": c[0], "type_name": c[1], "filter": "1"} for c in CATS]
ALL_FILTERS = {c[0]: [
    {"key": "class", "name": "类型", "value": ALL_OPT([{"n": n, "v": s} for s, n in c[2]])},
    {"key": "area",  "name": "地区", "value": ALL_OPT([{"n": a, "v": a} for a in AREAS])},
    {"key": "year",  "name": "年份", "value": ALL_OPT([{"n": y, "v": y} for y in YEARS])},
    {"key": "by",    "name": "排序", "value": [{"n":"最新","v":"time"},{"n":"最热","v":"hits"},{"n":"评分","v":"score"}]},
] for c in CATS}

SUB2MAIN = {s: c[0] for c in CATS for s, _ in c[2]}
CATIDS = {c[0] for c in CATS}

PIC_ATTRS = ('data-original', 'data-src', 'src')
CARD_SEL = 'a.myui-vodlist__thumb, a.stui-vodlist__thumb, a[href*="/vod/detail/"]'
REMARK_SEL = '.remarks, span.remarks, .pic-text, .pic-tag, .module-item-note'
DESC_SEL = ('.detail-desc p, .detail-desc, .vod-detail-desc p, '
            '.myui-content__detail .data:last-child, '
            '.stui-content__detail .data:last-child')
META_SEL = '.detail-meta span, .detail-meta, .vod-detail-meta span, .module-info-item'
REMARK_RE = re.compile(r'(更新至[^\s]{0,12}|连载至[^\s]{0,12}|全\d+集|全集|已完结|正片|HD中字|HD国语|TC中字)')
META_RE = re.compile(r'^(导演|主演|地区|语言|类型|年份|又名|编剧)[：:]\s*(.+)$')


class Spider(_Base):
    siteUrl = HOST

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({'User-Agent': UA, 'Referer': HOST + '/',
                               'Accept-Language': 'zh-CN,zh;q=0.9'})
        self.s.verify = False
        ad = HTTPAdapter(pool_connections=20, pool_maxsize=40, max_retries=0)
        self.s.mount('http://', ad)
        self.s.mount('https://', ad)
        self.host = HOST
        self.cache = {}
        self.lock = threading.Lock()

    def init(self, extend=""):
        self.extend = extend or ""

    # ---------- 网络 ----------
    def _req(self, url, **kw):
        for host in [self.host] + [m for m in MIRRORS if m != self.host]:
            target = url.replace(self.host, host, 1) if url.startswith(self.host) else url
            for i in range(2):
                try:
                    r = self.s.get(target, timeout=kw.get('timeout', 8),
                                   headers={'Referer': kw.get('referer', self.host + '/')},
                                   data=kw.get('data'))
                    if r.status_code == 429:
                        time.sleep(2); continue
                    r.raise_for_status()
                    r.encoding = r.apparent_encoding or 'utf-8'
                    self.host = host
                    return r
                except Exception:
                    if i == 0: time.sleep(0.2)
        return None

    def _text(self, url, **kw):
        r = self._req(url, **kw)
        return r.text if r else ""

    # ---------- 缓存 ----------
    def _cache(self, key, ttl, value=None):
        item = self.cache.get(key)
        if value is None:
            return item[1] if item and time.time() - item[0] < ttl else None
        if len(self.cache) > 512: self.cache.clear()
        self.cache[key] = (time.time(), value, ttl)
        return value

    # ---------- HTML ----------
    @staticmethod
    def _soup(html):
        if not html or BeautifulSoup is None: return None
        try: return BeautifulSoup(html, 'lxml')
        except Exception: return BeautifulSoup(html, 'html.parser')

    def _abs(self, u):
        u = (u or '').strip()
        if not u: return ''
        if u.startswith('//'): return 'https:' + u
        if u.startswith('/'): return self.host + u
        return u if u.startswith('http') else self.host + '/' + u

    @staticmethod
    def _vid(href):
        m = re.search(r'/(\d{4,10})\.(?:html|shtml)$', href or '')
        return m.group(1) if m else None

    def _pic(self, el):
        if el is None: return ''
        for n in [el] + el.find_all('img'):
            for a in PIC_ATTRS:
                v = str(n.get(a) or '').strip()
                if v and not v.startswith('data:'): return self._abs(v)
            m = re.search(r'url\(([^)]+)\)', str(n.get('style') or ''))
            if m: return self._abs(m.group(1).strip(' "\''))
        return ''

    def _cards(self, html, limit=36):
        soup = self._soup(html)
        if not soup: return []
        out = {}
        for a in soup.select(CARD_SEL):
            vid = self._vid(str(a.get('href') or ''))
            name = str(a.get('title') or '').strip()
            img = a.find('img')
            if not name and img: name = str(img.get('alt') or '').strip()
            if not (vid and name) or vid in out: continue

            # 副标题：多级容器查找
            rmk = ''
            for scope in (a, a.find_parent('li'), a.find_parent('div')):
                if scope is None: continue
                st = scope.select_one(REMARK_SEL)
                if st:
                    rmk = st.get_text(strip=True)
                    if rmk: break
            if not rmk:
                m = REMARK_RE.search(name)
                if m: rmk = m.group(1)

            name = re.sub(r'\s*[（(]\s*\d{4}\s*[）)]\s*$', '', name.strip())
            out[vid] = {'vod_id': vid, 'vod_name': name, 'vod_pic': self._pic(a), 'vod_remarks': rmk}
        return list(out.values())[:limit]

    # ---------- 首页 ----------
    def homeContent(self, filter=False):
        cached = self._cache('home', 600)
        if not cached:
            cached = self._cards(self._text(self.host + '/'), 60)
            if cached: self._cache('home', 600, cached)
        return {"class": ALL_CLASSES, "filters": ALL_FILTERS, "list": cached or []}

    def homeVideoContent(self):
        return {"list": self.homeContent()["list"]}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter, extend):
        page = max(1, int(pg or 1))
        ext = extend if isinstance(extend, dict) else (json.loads(extend) if isinstance(extend, str) and extend else {})
        slug = str(ext.get('class') or tid or '').strip()
        if not slug: return self._empty(page)

        ck = "c:%s|%d|%s" % (slug, page, json.dumps(ext, sort_keys=True))
        cached = self._cache(ck, 300)
        if cached: return cached

        params = {k: v.strip() for k in ('area','year','by') if isinstance(v := ext.get(k), str) and v.strip()}
        qs = ('?' + urlencode(params)) if params else ''
        html = self._text("%s/index.php/vod/type/id/%s/page/%d.html%s" % (self.host, slug, page, qs))

        if not html or '404' in html[:2000]:
            main = SUB2MAIN.get(slug) or (slug if slug in CATIDS else None)
            if main and main != slug:
                html = self._text("%s/index.php/vod/type/id/%s/page/%d.html%s" % (self.host, main, page, qs))

        if not html: return self._empty(page)
        m = re.search(r'尾页[^>]*page/(\d+)\.html', html)
        pages = [int(x) for x in re.findall(r'/page/(\d+)\.html', html)]
        pc = int(m.group(1)) if m else (max(pages) if pages else 1)
        result = {"list": self._cards(html), "page": page, "pagecount": pc,
                  "limit": 36, "total": pc * 36}
        return self._cache(ck, 300, result)

    @staticmethod
    def _empty(page):
        return {"list": [], "page": page, "pagecount": 1, "limit": 36, "total": 0}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = str((ids if isinstance(ids, str) else ids[0])).split(',')[0].strip()
        if not vid: return {"list": []}
        cached = self._cache("d:" + vid, 300)
        if cached is not None: return cached
        return self._cache("d:" + vid, 300, self._detail(vid))

    def _detail(self, vid):
        soup = self._soup(self._text("%s/index.php/vod/detail/id/%s.html" % (self.host, vid)))
        if not soup: return {"list": []}

        name = ''
        for sel in ('h1', '.myui-content__detail h1', '.stui-content__detail h1'):
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                name = re.sub(r'\s*[（(]\s*\d{4}\s*[）)]\s*$', '', el.get_text(strip=True)); break

        img = soup.select_one('.myui-content__thumb img, .stui-content__thumb img, .myui-player__info img')

        # 元信息：兼容 .detail-meta 新模板 + 经典 .data 模板
        meta = {}
        for sp in soup.select(META_SEL):
            m = META_RE.match(sp.get_text(' ', strip=True))
            if m:
                key, val = m.group(1), m.group(2).strip()
                if val: meta.setdefault(key, val)
        if not meta:
            for p in soup.select('.myui-content__detail p.data, .stui-content__detail p.data'):
                lab = p.find('span', class_='text-muted')
                if not lab: continue
                label = lab.get_text(strip=True).rstrip(':：')
                if label not in ('导演','主演','地区','语言'): continue
                val = p.get_text(' ', strip=True)[len(lab.get_text(strip=True)):].lstrip(':： ').strip()
                if val: meta.setdefault(label, val)

        text = soup.get_text(' ', strip=True)
        ym = re.search(r'[（(]\s*(\d{4})\s*[）)]', text) or re.search(r'\b(19\d{2}|20\d{2})\b', text)
        rm = REMARK_RE.search(text)

        # 简介：多级容器查找
        content = ''
        desc = soup.select_one(DESC_SEL)
        if desc:
            content = desc.get_text(' ', strip=True)
        if not content:
            mt = soup.find('meta', attrs={'name': 'description'})
            if mt:
                c = str(mt.get('content') or '')
                m = re.search(r'剧情为[:：](.{10,})', c)
                content = m.group(1).strip() if m else c[:200]
        content = re.sub(r'\s+', ' ', content).strip()

        # 线路
        groups, seen = [], set()
        for tab in soup.select('span.source-tab-item[data-target]'):
            tgt = str(tab.get('data-target') or '').strip()
            if not tgt or tgt in seen: continue
            seen.add(tgt)
            eps = self._eps(soup.find(id=tgt))
            if eps: groups.append((tab.get_text(strip=True) or '线路', eps))
        if not groups:
            for tab in soup.select('a[href^="#"], a[data-toggle="tab"]'):
                href = str(tab.get('href') or '')
                if not href.startswith('#') or href in seen: continue
                seen.add(href)
                eps = self._eps(soup.find(id=href[1:]))
                if eps: groups.append((tab.get_text(strip=True) or '线路', eps))
        if not groups:
            eps = self._eps(soup)
            if eps: groups.append(('默认线路', eps))

        froms = '$$$'.join(g[0] for g in groups) or '默认'
        urls = '$$$'.join('#'.join("%s$%s" % e for e in g[1]) for g in groups)

        return {"list": [{
            "vod_id": vid, "vod_name": name or ("视频%s" % vid),
            "vod_pic": self._pic(img) if img else '',
            "vod_remarks": rm.group(1) if rm else '',
            "vod_year": ym.group(1) if ym else '',
            "vod_area": meta.get('地区', ''), "vod_lang": meta.get('语言', ''),
            "vod_director": meta.get('导演', ''), "vod_actor": meta.get('主演', ''),
            "vod_content": content,
            "vod_play_from": froms, "vod_play_url": urls,
        }]}

    @staticmethod
    def _eps(pane):
        if not pane: return []
        out, seen = [], set()
        for a in pane.select('a[href*="/vod/play/"]'):
            nm = a.get_text(strip=True) or '播放'
            href = a.get('href', '')
            if PLAY_BTN.match(nm) or href in seen: continue
            seen.add(href)
            out.append((nm, href))
        return out

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        if not id: return {"parse": 0, "playUrl": "", "url": ""}
        url = self._abs(str(id))
        real = self._cache("p:" + url, 900) or self._resolve(url)
        if real: return self._payload(real)

        vid = re.search(r'/play/id/(\d+)/', url)
        cached_d = self._cache("d:" + vid.group(1), 300) if vid else None
        if cached_d and cached_d["list"]:
            for seg in (cached_d["list"][0].get("vod_play_url") or "").split("$$$"):
                for item in seg.split("#")[:6]:
                    parts = item.split("$", 1)
                    if len(parts) == 2 and parts[1] != url:
                        real = self._resolve(parts[1])
                        if real:
                            self._cache("p:" + url, 900, real)
                            return self._payload(real)
        return {"parse": 1, "playUrl": "", "url": url,
                "header": {"User-Agent": UA, "Referer": self.host + "/"}}

    def _resolve(self, play_url):
        cached = self._cache("p:" + play_url, 900)
        if cached: return cached
        text = self._text(play_url, referer=self.host + '/', timeout=4)
        if not text: return ''
        m = re.search(r'var\s+player_\w+\s*=\s*(\{.*?\})\s*[;<]', text, re.S)
        real = ''
        if m:
            try:
                u = (json.loads(m.group(1)).get('url') or '').replace('\\/', '/').strip()
                if u: real = self._abs(u)
            except Exception: pass
        if not real:
            m = re.search(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', text)
            if m: real = self._abs(m.group(1).replace('\\/', '/'))
        if real: self._cache("p:" + play_url, 900, real)
        return real

    @staticmethod
    def _payload(url):
        m = '.m3u8' in url.lower()
        return {"parse": 0, "playUrl": "", "url": url,
                "header": {"User-Agent": UA, "Referer": HOST + "/", "Origin": HOST},
                "format": "application/x-mpegURL" if m else "",
                "contentType": "application/x-mpegURL" if m else ""}

    # ---------- 搜索 ----------
    def searchContent(self, keyword, quick=False, pg=1):
        kw = (keyword or '').strip()
        if not kw: return {"list": [], "msg": "请输入关键词"}
        page = int(pg or 1)
        ck = "s:%s|%s" % (page, kw.lower())
        cached = self._cache(ck, 180)
        if cached is not None: return cached

        result = (self._suggest(quote(kw), page) or self._site(quote(kw), kw, page)
                  or self._scrape(kw, page) or {"list": [], "msg": "未找到相关内容"})
        return self._cache(ck, 180, result)

    def _suggest(self, kw, page):
        for t in ("%s/index.php/ajax/suggest?wd=%s&page=%d", "%s/ajax/suggest?wd=%s&page=%d"):
            text = self._text(t % (self.host, kw, page), referer=self.host + '/', timeout=5).strip()
            if not text.startswith('{'): continue
            try: data = json.loads(text)
            except Exception: continue
            out = [{'vod_id': str(i.get('id')), 'vod_name': str(i.get('name') or ''),
                    'vod_pic': self._abs(i.get('pic') or ''), 'vod_remarks': str(i.get('remark') or '')}
                   for i in (data.get('list') or data.get('data') or [])
                   if isinstance(i, dict) and i.get('id') and i.get('name')]
            if out: return {"list": out}
        return None

    def _site(self, kw_q, kw, page):
        suffix = "&page=%d" % page if page > 1 else ""
        for url in ("%s/index.php/vod/search.html?wd=%s%s" % (self.host, kw_q, suffix),
                    "%s/vod/search.html?wd=%s%s" % (self.host, kw_q, suffix)):
            html = self._text(url, referer=self.host + '/', timeout=5)
            if not html or '搜索功能关闭' in html or '搜索功能暂停' in html: continue
            cards = self._cards(html)
            if cards:
                m = self._rank(cards, kw)
                if m: return {"list": m}
        return None

    def _scrape(self, kw, page):
        if page > 1: return {"list": []}
        pages = (1,2,3,4,5) if len(kw) >= 3 else (1,2,3,4)

        def fetch(cid, p):
            return self._cards(self._text("%s/index.php/vod/type/id/%s/page/%d.html" % (self.host, cid, p), timeout=5))

        all_cards = []
        tasks = [(c[0], p) for c in CATS for p in pages]
        if ThreadPoolExecutor:
            with ThreadPoolExecutor(max_workers=5) as ex:
                for f in as_completed([ex.submit(fetch, *t) for t in tasks], timeout=25):
                    try: all_cards.extend(f.result())
                    except Exception: pass
        else:
            for t in tasks:
                try: all_cards.extend(fetch(*t))
                except Exception: pass
        m = self._rank(all_cards, kw, 24)
        return {"list": m} if m else None

    @staticmethod
    def _rank(cards, kw, limit=24):
        raw = kw.lower().replace(' ', '')
        if not raw: return cards[:limit]
        toks = [raw] if len(raw) <= 2 else [raw[i:i+2] for i in range(len(raw)-1)] + list(raw)

        def sc(n):
            n = (n or '').lower().replace(' ', '')
            if not n: return 0
            if raw in n: return 100
            return sum(1 for t in toks if t in n)

        return [c for s, c in sorted(((sc(c.get('vod_name')), c) for c in cards),
                                     key=lambda x: x[0], reverse=True) if s > 0][:limit]

    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    def destroy(self):
        try: self.s.close()
        except Exception: pass

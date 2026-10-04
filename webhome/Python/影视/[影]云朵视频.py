# -*- coding: utf-8 -*-
r"""
云朵视频 (egradiomarketing.com) - TVBox 爬虫源
================================================
接口：homeContent / categoryContent(二级分类 + 筛选) / detailContent(多线路+懒加载)
      / playerContent(直链解析 + 自动预取) / searchContent

站点实测结构 (2026-09 验证)：
1. 首页：/ 卡片 (.ys-name6 / /egrafb/{id}.html)
2. 分类页：/egrafbtype/{tid}.html（tid: 1电影 2电视剧 3综艺 4动漫 9短视频 51即将上映）
   翻页：/egrafbtype/{tid}-{n}.html
3. 筛选列表（12 段式）：/egrafbshow/{tid}-{地区}-{}-{}-{年份}-{字母}-{}-{}-{}-{}-{}-{页码}.html
   二级分类 = 第 1 段 tid 切换（35喜剧片/36动作片/42国产剧/48国内动漫…）
   地区=第2段(中文) / 年份=第5段 / 字母=第6段(A-Z) / 页码=第12段
4. 详情页：/egrafb/{id}.html
   多线路（线路1/2/3），集链接 /egrafbplay/{id}-{sid}-{nid}.html
   注意：简介区被注入形似"网友评论"的广告段落，需在第一个 <p/<div 处截断
5. 播放页：player_aaaa JSON 内嵌 m3u8 直链（encrypt:0），含 link_next
6. 搜索：GET /search/-------------.html?wd={kw}
   翻页：/search/{kw}--{n}-----------.html
7. 域名可变：主插件支持从同目录 .yunduo_domain 文件读取当前可用域名（配合域名跟踪工具）

速度优化：
- 全正则解析，零 bs4 依赖
- 详情页懒加载：不预解析所有集数 m3u8，秒开
- playerContent 按需解析 + 15 分钟缓存 + 后台预取（详情后预取首集，播放时预取下一集）
- 多级缓存：首页10分钟 / 分类5分钟 / 详情5分钟(失败30秒) / 搜索3分钟 / 播放15分钟
- 连接池复用(HTTPAdapter) + 短超时 + 快速重试 + 多域名容灾
"""

import re
import os
import json
import time
import threading
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except ImportError:
    ThreadPoolExecutor = None
    as_completed = None

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

try:
    import sys
    sys.path.append('..')
    from base.spider import Spider as _BaseSpider
except ImportError:
    _BaseSpider = None


# ============================================================
# 常量
# ============================================================
DEFAULT_HOST = "https://egradiomarketing.com"


def _load_host():
    """支持从同目录 .yunduo_domain 文件读取可用域名（域名跟踪工具写入）"""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        fp = os.path.join(base, '.yunduo_domain')
        if os.path.exists(fp):
            txt = open(fp, 'r', encoding='utf-8').read().strip()
            m = re.search(r'(https?://[^\s,;]+)', txt)
            if m:
                return m.group(1).rstrip('/')
    except Exception:
        pass
    return DEFAULT_HOST


HOST = _load_host()

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

# 超时（秒）
TIMEOUT_PAGE = 8
TIMEOUT_API = 6
TIMEOUT_PLAY = 5

# 缓存 TTL（秒）
TTL_HOME = 600
TTL_CAT = 300
TTL_DETAIL_OK = 300
TTL_DETAIL_EMPTY = 30
TTL_SEARCH = 180
TTL_PLAY = 900


# ============================================================
# 分类与筛选项（站点实测）
# ============================================================
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
    {"type_id": "9", "type_name": "短视频"},
    {"type_id": "51", "type_name": "即将上映"},
]

# 二级分类（切换到筛选列表的第 1 段 tid）
SUBS = {
    "1": [
        ("35", "喜剧片"), ("36", "动作片"), ("37", "爱情片"), ("38", "科幻片"),
        ("39", "恐怖片"), ("40", "剧情片"), ("41", "战争片"),
    ],
    "2": [
        ("42", "国产剧"), ("43", "港台剧"), ("44", "日韩剧"), ("45", "欧美剧"),
    ],
    "3": [
        ("46", "国内综艺"), ("47", "海外综艺"),
    ],
    "4": [
        ("48", "国内动漫"), ("49", "海外动漫"),
    ],
    "9": [
        ("57", "动画短片"), ("58", "短剧"),
    ],
    "51": [],
}

# 地区筛选
AREAS = [
    "大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国",
    "德国", "泰国", "印度", "新加坡", "荷兰", "其他",
]

# 年份筛选
YEARS = [str(y) for y in range(2026, 2015, -1)]

# 字母筛选
LETTERS = [chr(c) for c in range(ord('A'), ord('Z') + 1)]


def _nvs(names):
    return [{"n": "全部", "v": ""}] + [{"n": n, "v": n} for n in names]


def _build_filters(tid):
    tid = str(tid)
    f = []
    subs = SUBS.get(tid)
    if subs:
        f.append({
            "key": "type", "name": "类型",
            "value": [{"n": "全部", "v": ""}] + [{"n": n, "v": v} for v, n in subs],
        })
    f.append({"key": "area", "name": "地区", "value": _nvs(AREAS)})
    f.append({
        "key": "year", "name": "年份",
        "value": [{"n": "全部", "v": ""}] + [{"n": y, "v": y} for y in YEARS],
    })
    f.append({
        "key": "letter", "name": "字母",
        "value": [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in LETTERS],
    })
    return f


# 全部筛选器
ALL_FILTERS = {tid: _build_filters(tid) for tid in ("1", "2", "3", "4", "9", "51")}
for _parent, _subs in SUBS.items():
    for _stid, _name in _subs:
        if _stid not in ALL_FILTERS:
            ALL_FILTERS[_stid] = [x for x in ALL_FILTERS[_parent] if x["key"] != "type"]


# ============================================================
# Spider 主类
# ============================================================
_Base = _BaseSpider if _BaseSpider is not None else object


class Spider(_Base):
    siteUrl = HOST
    headers = {
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Referer': HOST + '/',
    }

    _DETAIL_ID_RE = re.compile(r'/egrafb/(\d+)\.html')
    _PLAYER_RE = re.compile(r'var\s+player_\w+\s*=\s*(\{.*?\})\s*[;<]', re.S)
    _CARD_RE = re.compile(
        r'<a\s+href="(/egrafb/(\d+)\.html)"[^>]*>\s*'
        r'<img[^>]*data-src="([^"]*)"[^>]*alt="([^"]*)"', re.S)

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.headers['Connection'] = 'keep-alive'
        self.session.verify = False
        adapter = HTTPAdapter(
            pool_connections=20, pool_maxsize=40,
            max_retries=0, pool_block=False,
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # 缓存容器 + 锁
        self._lock = threading.Lock()
        self._home_cache = []
        self._home_cache_time = 0
        self._cat_cache = {}
        self._detail_cache = {}
        self._search_cache = {}
        self._play_cache = {}
        self._prefetching = set()

        # 域名容灾：当前可用 host（可被动态更新）
        self._host = HOST

    def getName(self):
        return "云朵视频"

    def init(self, extend=""):
        self.extend = extend or ""

    # ===== 网络工具 =====
    def _base(self):
        return self._host.rstrip('/')

    def _get(self, url, referer='', timeout=TIMEOUT_PAGE):
        headers = {'Connection': 'keep-alive'}
        if referer:
            headers['Referer'] = referer
        for attempt in range(3):
            try:
                r = self.session.get(url, timeout=timeout, headers=headers)
                if r.status_code == 429:
                    time.sleep(1.5)
                    continue
                if r.status_code >= 500:
                    if attempt < 2:
                        time.sleep(0.4)
                        continue
                r.raise_for_status()
                enc = (r.encoding or '').lower()
                if 'utf' not in enc:
                    r.encoding = r.apparent_encoding or 'utf-8'
                return r
            except Exception:
                if attempt < 2:
                    time.sleep(0.35)
                else:
                    return None
        return None

    def _get_text(self, url, referer='', timeout=TIMEOUT_PAGE):
        r = self._get(url, referer, timeout)
        return r.text if r is not None else ""

    # ===== 缓存 =====
    @staticmethod
    def _cache_get(cache, key):
        item = cache.get(key)
        if item and time.time() - item[0] < item[2]:
            return item[1]
        return None

    @staticmethod
    def _cache_set(cache, key, value, ttl=TTL_CAT):
        if len(cache) > 512:
            cache.clear()
        cache[key] = (time.time(), value, ttl)

    # ===== 工具 =====
    def _abs(self, u):
        u = (u or '').strip()
        if not u:
            return ''
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('/'):
            return self._base() + u
        if not u.startswith('http'):
            return self._base() + '/' + u
        return u

    @staticmethod
    def _clean(text):
        if not text:
            return ''
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('\u3000', ' ')
        text = (text.replace('&middot;', '·').replace('&ldquo;', '“')
                .replace('&rdquo;', '”').replace('&hellip;', '…')
                .replace('&amp;', '&').replace('&quot;', '"')
                .replace('&#039;', "'").replace('&lt;', '<').replace('&gt;', '>'))
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def _clean_name(raw):
        if not raw:
            return raw
        raw = (raw.replace('&middot;', '·').replace('&amp;', '&')
               .replace('&quot;', '"'))
        return re.sub(r'\s*[（(]\s*\d{4}\s*[）)]\s*$', '', raw.strip())

    # ===== URL 构造 =====
    @staticmethod
    def _show_url(tid, area='', year='', letter='', page=1):
        """12 段式筛选列表 URL（固定 11 个连字符）"""
        fields = [
            str(tid), area, '', '', year, letter, '', '', '', '', '',
            '' if page <= 1 else str(page),
        ]
        return '/egrafbshow/' + '-'.join(fields) + '.html'

    @staticmethod
    def _search_url(kw, page=1):
        """搜索 URL：首页用 ?wd=，翻页用 {kw}--{n}-----------.html"""
        if page <= 1:
            return '/search/-------------.html?wd=' + kw
        return f'/search/{kw}--{page}-----------.html'

    # ===== 卡片解析 =====
    def _parse_cards(self, html, limit=36):
        if not html:
            return []
        items = {}
        # 逐 anchor 扫描（兼容 img 在任意包裹层内 / 属性顺序不定）
        for m in re.finditer(r'<a\s+href="(/egrafb/(\d+)\.html)"[^>]*>', html):
            vid = m.group(2)
            if vid in items:
                continue
            seg = html[m.end():m.end() + 600]
            end = seg.find('</a>')
            inner = seg[:end] if end >= 0 else seg[:400]
            pm = re.search(r'data-src="([^"]+)"', inner)
            if not pm:
                pm = re.search(r'<img[^>]*src="([^"]+)"', inner)
            if not pm or not pm.group(1).strip():
                continue
            pic = pm.group(1).strip()
            tm = re.search(r'alt="([^"]+)"', inner)
            if not tm:
                tm = re.search(r'class="(?:filmName|ys-name\d*)"[^>]*>([^<]+)<', inner)
            if not tm:
                continue
            title = (tm.group(1) or '').strip()
            if not title:
                continue
            remarks = ''
            m2 = re.search(
                r'更新至[^\s<]{0,12}|全\d+集|已完结|正片|HD中字|HD国语|TC中字',
                title)
            if m2:
                remarks = m2.group(0)
            items[vid] = {
                'vod_id': vid,
                'vod_name': self._clean_name(title),
                'vod_pic': self._abs(pic),
                'vod_remarks': remarks,
            }
            if len(items) >= limit * 2:
                break
        return list(items.values())[:limit]

    @staticmethod
    def _parse_pagecount(html):
        if not html:
            return 1
        m = re.search(r'<span class="total">(\d+)</span>', html)
        if m:
            return max(1, int(m.group(1)))
        m = re.search(r'href="[^"]*?(\d+)\.html"[^>]*>\s*尾页', html)
        if m:
            return max(1, int(m.group(1)))
        return 1

    # ============================================================
    # 首页
    # ============================================================
    def homeContent(self, filter=False):
        return {
            "class": CLASSES,
            "filters": ALL_FILTERS,
            "list": self._home_list(),
        }

    def homeVideoContent(self):
        return {"list": self._home_list()}

    def _home_list(self):
        now = int(time.time())
        with self._lock:
            if self._home_cache and now - self._home_cache_time < TTL_HOME:
                return self._home_cache[:60]
        try:
            html = self._get_text(self._base() + '/')
            vod_list = self._parse_cards(html, limit=80)
            if vod_list:
                with self._lock:
                    self._home_cache = vod_list
                    self._home_cache_time = int(time.time())
            return vod_list[:80]
        except Exception:
            return []

    # ============================================================
    # 分类列表
    # ============================================================
    def _empty_category(self, page=1):
        return {"list": [], "page": page, "pagecount": 1, "limit": 36, "total": 0}

    def categoryContent(self, tid, pg, filter, extend):
        page = 1
        try:
            page = max(1, int(pg or 1))
            ext = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend)
                    except Exception:
                        ext = {}

            base = (ext.get('type') or '').strip() or str(tid)
            area = (ext.get('area') or '').strip()
            year = (ext.get('year') or '').strip()
            letter = (ext.get('letter') or '').strip()

            ckey = "%s|%s|%s|%s|%d" % (base, area, year, letter, page)
            cached = self._cache_get(self._cat_cache, ckey)
            if cached is not None:
                return cached

            # 无筛选时用清爽的分类页（更快），有筛选时用 show 页
            if not area and not year and not letter:
                if page <= 1:
                    url = f"{self._base()}/egrafbtype/{base}.html"
                else:
                    url = f"{self._base()}/egrafbtype/{base}-{page}.html"
            else:
                url = self._base() + self._show_url(base, area, year, letter, page)

            html = self._get_text(url)
            if not html:
                return self._empty_category(page)

            pagecount = self._parse_pagecount(html)
            vod_list = self._parse_cards(html, limit=60)
            result = {
                "list": vod_list,
                "page": page,
                "pagecount": pagecount,
                "limit": 36,
                "total": pagecount * 36,
            }
            self._cache_set(self._cat_cache, ckey, result, TTL_CAT)
            return result
        except Exception:
            return self._empty_category(page)

    # ============================================================
    # 详情页（多线路 + 懒加载）
    # ============================================================
    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vid = str(ids[0]).split(',')[0].strip()
        if not vid:
            return {"list": []}

        cached = self._cache_get(self._detail_cache, vid)
        if cached is not None:
            return cached

        result = self._fetch_detail(vid)
        ttl = TTL_DETAIL_OK if result.get("list") else TTL_DETAIL_EMPTY
        self._cache_set(self._detail_cache, vid, result, ttl)

        if result.get("list"):
            self._prefetch_first(result["list"][0])
        return result

    def _fetch_detail(self, vid):
        html = self._get_text(f"{self._base()}/egrafb/{vid}.html")
        if not html:
            return {"list": []}

        # --- 名称 ---
        name = ''
        m = re.search(r'<title>《([^》]+)》', html)
        if m:
            name = self._clean_name(self._clean(m.group(1)))
        if not name:
            m = re.search(r'<div class="ys-name\d+">([^<]+)</div>', html)
            if m:
                name = self._clean_name(self._clean(m.group(1)))

        # --- 封面 ---
        pic = ''
        m = re.search(r'class="poster\d*"\s*>\s*<img[^>]*data-src="([^"]+)"', html)
        if not m:
            m = re.search(r'<img[^>]*data-src="([^"]+)"[^>]*alt=""', html)
        if m:
            pic = self._abs(m.group(1))

        # --- 导演 / 主演 ---
        def _actors(label):
            m2 = re.search(
                r'<div class="main-actors\d*">\s*%s：?(.*?)</div>' % re.escape(label),
                html, re.S)
            if not m2:
                return ''
            names = re.findall(r'<a[^>]*>([^<]*)</a>', m2.group(1))
            names = [self._clean(n) for n in names if self._clean(n)]
            # 去掉空项和"更多..."
            names = [n for n in names if n and n != '更多...' and len(n) < 40]
            return ','.join(names[:10])

        actor = _actors('主演')
        director = _actors('导演')

        # --- 类型 / 地区 ---
        def _style(label):
            m2 = re.search(
                r'<div class="ys-style\d*">\s*%s：?(.*?)</div>' % re.escape(label),
                html, re.S)
            if not m2:
                return ''
            names = re.findall(r'<a[^>]*>([^<]*)</a>', m2.group(1))
            names = [self._clean(n) for n in names if self._clean(n)]
            return ','.join(names[:5])

        type_name = _style('类型')
        area = _style('地区')

        # --- 年份（从详情或标题提取） ---
        year = ''
        ym = re.search(r'[（(](\d{4})[）)]', name or '')
        if not ym:
            ym = re.search(r'(\d{4})-(?:0[1-9]|1[0-2])-\d{2}', html)
        if ym:
            year = ym.group(1)

        # --- 简介（截断注入的"网友评论"广告段） ---
        content = ''
        m = re.search(
            r'<div class="Synopsis-word"[^>]*>(.*?)(?:<p\s|<div\s|</div>)',
            html, re.S)
        if m:
            content = self._clean(m.group(1))
        if not content:
            m = re.search(
                r'<div class="vod-descri\d*"[^>]*>(.*?)(?:<p\s|<div\s|</div>)',
                html, re.S)
            if m:
                content = self._clean(m.group(1))
        content = re.sub(r'^剧情简介\s*', '', content)
        content = re.sub(r'^简介\s*[:：]?\s*', '', content)

        # --- 播放线路与集数（多线路） ---
        play_groups = []
        seen_ep = set()
        # 线路名:   <div class="name17">线路N</div>
        # 集数区:   <div class="list-number1"> ... /egrafbplay/{vid}-{sid}-{nid}.html
        # 结构上线路名和集数区交替出现，按序配对
        parts = re.split(r'<div class="name17">([^<]*)</div>', html)
        # parts: [before, name1, seg1, name2, seg2, ...]
        for i in range(1, len(parts) - 1, 2):
            src_name = (parts[i] or '').strip()
            seg = parts[i + 1]
            eps = []
            for em in re.finditer(
                    r'href="(/egrafbplay/\d+-\d+-\d+\.html)"[^>]*>\s*<div>([^<]*)</div>',
                    seg):
                ep_url = self._abs(em.group(1))
                if ep_url in seen_ep:
                    continue
                seen_ep.add(ep_url)
                label = self._clean(em.group(2)).strip() or '播放'
                eps.append((label, ep_url))
            if eps:
                play_groups.append((src_name or f'线路{len(play_groups) + 1}', eps))

        # 兜底：全页找播放链接
        if not play_groups:
            eps = []
            for em in re.finditer(
                    r'href="(/egrafbplay/\d+-\d+-\d+\.html)"[^>]*>\s*<div>([^<]*)</div>',
                    html):
                ep_url = self._abs(em.group(1))
                if ep_url in seen_ep:
                    continue
                seen_ep.add(ep_url)
                eps.append((self._clean(em.group(2)).strip() or '播放', ep_url))
            if eps:
                play_groups.append(('线路1', eps))

        play_from, play_url = '', ''
        for src_name, eps in play_groups:
            ep_parts = [f"{n}${u}" for n, u in eps]
            play_from = (play_from + '$$$' + src_name) if play_from else src_name
            play_url = (play_url + '$$$' + '#'.join(ep_parts)) if play_url else '#'.join(ep_parts)

        detail = {
            "vod_id": vid,
            "vod_name": name or f"视频{vid}",
            "vod_pic": pic or self._base(),
            "type_name": type_name,
            "vod_remarks": '',
            "vod_year": year,
            "vod_area": area,
            "vod_lang": '',
            "vod_director": director,
            "vod_actor": actor,
            "vod_content": content,
            "vod_play_from": play_from or '线路1',
            "vod_play_url": play_url or '',
        }
        return {"list": [detail]}

    # ============================================================
    # 播放解析（直链 + 缓存 + 预取）
    # ============================================================
    def _resolve_play(self, play_url):
        """解析播放页 → {'url': m3u8直链, 'next': 下一集播放页URL}"""
        cached = self._cache_get(self._play_cache, play_url)
        if cached:
            return cached
        info = None
        try:
            text = self._get_text(play_url, referer=self._base() + '/',
                                  timeout=TIMEOUT_PLAY)
            if text:
                data = None
                m = self._PLAYER_RE.search(text)
                if m:
                    try:
                        data = json.loads(m.group(1))
                    except Exception:
                        data = None
                if not data:
                    u_m = re.search(r'"url"\s*:\s*"([^"]+)"', text)
                    if u_m:
                        u = u_m.group(1).replace('\\/', '/')
                        if '.m3u8' in u or '.mp4' in u:
                            data = {"url": u}
                if data:
                    u = (data.get('url') or '').strip().replace('\\/', '/')
                    low = u.lower()
                    if u.startswith('http') and ('.m3u8' in low or '.mp4' in low):
                        nxt = (data.get('link_next') or '').strip()
                        info = {
                            'url': u,
                            'next': self._abs(nxt) if nxt else '',
                        }
        except Exception:
            info = None
        if info:
            self._cache_set(self._play_cache, play_url, info, TTL_PLAY)
        return info

    def _prefetch(self, play_url):
        if not play_url:
            return
        with self._lock:
            if (self._cache_get(self._play_cache, play_url)
                    or play_url in self._prefetching):
                return
            self._prefetching.add(play_url)

        def _job(url=play_url):
            try:
                self._resolve_play(url)
            except Exception:
                pass
            finally:
                with self._lock:
                    self._prefetching.discard(url)

        threading.Thread(target=_job, daemon=True).start()

    def _prefetch_first(self, vod):
        for seg in (vod.get("vod_play_url") or "").split("$$$"):
            for item in seg.split("#"):
                parts = item.split("$", 1)
                if len(parts) == 2 and parts[1]:
                    self._prefetch(parts[1])
                    return

    def _play_payload(self, playurl):
        low = playurl.lower()
        if '.m3u8' in low:
            fmt, ctype = 'application/x-mpegURL', 'application/x-mpegURL'
        elif '.mp4' in low:
            fmt, ctype = 'video/mp4', 'video/mp4'
        else:
            fmt, ctype = '', ''
        return {
            "parse": 0,
            "playUrl": "",
            "url": playurl,
            "header": {
                "User-Agent": UA,
                "Referer": self._base() + "/",
                "Origin": self._base(),
            },
            "format": fmt,
            "contentType": ctype,
        }

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}
        play_url = self._abs(str(id))

        info = self._cache_get(self._play_cache, play_url)
        if not info:
            info = self._resolve_play(play_url)
        if info and info.get('url'):
            if info.get('next'):
                self._prefetch(info['next'])
            return self._play_payload(info['url'])

        return {
            "parse": 1,
            "playUrl": "",
            "url": play_url,
            "header": {"User-Agent": UA, "Referer": self._base() + "/"},
        }

    # ============================================================
    # 搜索
    # ============================================================
    def _search_site(self, kw_enc, page):
        try:
            url = self._base() + self._search_url(kw_enc, page)
            html = self._get_text(url, referer=self._base() + '/', timeout=TIMEOUT_API)
            if not html:
                return None
            cards = self._parse_cards(html, limit=40)
            if not cards:
                return None
            pagecount = self._parse_pagecount(html)
            return {
                "list": cards,
                "page": page,
                "pagecount": pagecount,
                "limit": 36,
                "total": pagecount * 36,
            }
        except Exception:
            return None

    @staticmethod
    def _filter_by_keyword(cards, raw, limit=24):
        if not raw:
            return cards[:limit]
        raw = raw.lower().replace(' ', '').strip()
        if not raw:
            return cards[:limit]
        if len(raw) <= 2:
            tokens = [raw]
        else:
            tokens = [raw[i:i + 2] for i in range(0, len(raw) - 1)]

        def score(name):
            name = (name or '').lower().replace(' ', '')
            if not name:
                return 0
            if raw in name:
                return 100
            return sum(1 for t in tokens if t in name)

        matched = [(score(c.get('vod_name') or ''), c) for c in cards]
        matched = [c for s, c in matched if s > 0]
        matched.sort(key=lambda c: score(c.get('vod_name') or ''), reverse=True)
        return matched[:limit]

    def _search_scrape(self, raw):
        """分类爬取兜底（并行抓各分类第 1-2 页）"""
        pages = (1, 2)
        if len(raw) >= 3:
            pages = (1, 2, 3)

        def _fetch_cat(args):
            tid, p = args
            if p <= 1:
                url = f"{self._base()}/egrafbtype/{tid}.html"
            else:
                url = f"{self._base()}/egrafbtype/{tid}-{p}.html"
            html = self._get_text(url, timeout=TIMEOUT_API)
            return self._parse_cards(html, limit=36)

        tasks = [(c['type_id'], p) for c in CLASSES for p in pages]
        all_cards, seen = [], set()
        if ThreadPoolExecutor is not None:
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = [ex.submit(_fetch_cat, t) for t in tasks]
                for f in as_completed(futs, timeout=TIMEOUT_API * 6):
                    try:
                        for c in f.result(timeout=TIMEOUT_API):
                            if c['vod_id'] not in seen:
                                seen.add(c['vod_id'])
                                all_cards.append(c)
                    except Exception:
                        continue
        else:
            for t in tasks:
                try:
                    for c in _fetch_cat(t):
                        if c['vod_id'] not in seen:
                            seen.add(c['vod_id'])
                            all_cards.append(c)
                except Exception:
                    continue

        matched = self._filter_by_keyword(all_cards, raw, limit=24)
        return {"list": matched} if matched else None

    def searchContent(self, keyword, quick=False, pg=1):
        kw_raw = (keyword or '').strip()
        if not kw_raw:
            return {"list": [], "msg": "请输入搜索关键词"}
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1

        ckey = f"{page}|{kw_raw}"
        cached = self._cache_get(self._search_cache, ckey)
        if cached is not None:
            return cached

        kw_enc = quote(kw_raw)
        result = self._search_site(kw_enc, page)
        if not result:
            result = self._search_scrape(kw_raw)

        if result and result.get("list"):
            self._cache_set(self._search_cache, ckey, result, TTL_SEARCH)
            return result

        result = {"list": [], "msg": "未找到相关内容，请尝试其他关键词或通过分类浏览"}
        self._cache_set(self._search_cache, ckey, result, TTL_SEARCH)
        return result

    # ============================================================
    # 代理 & 清理
    # ============================================================
    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def close(self):
        self.destroy()


# ============================================================
# 本地测试
#   python3 云朵视频.py home
#   python3 云朵视频.py category 1 1 type=35 area=大陆
#   python3 云朵视频.py category 1 2
#   python3 云朵视频.py detail 198822
#   python3 云朵视频.py play https://egradiomarketing.com/egrafbplay/198822-1-1.html
#   python3 云朵视频.py search 爱情 1
# ============================================================
if __name__ == '__main__':
    import sys as _sys
    s = Spider()
    action = _sys.argv[1] if len(_sys.argv) > 1 else 'home'
    if action == 'home':
        r = s.homeContent()
        print("classes:", len(r['class']), "| filters:", len(r['filters']),
              "| list:", len(r['list']))
        print(json.dumps(r['list'][:3], ensure_ascii=False))
    elif action == 'category':
        tid = _sys.argv[2] if len(_sys.argv) > 2 else '1'
        pg = _sys.argv[3] if len(_sys.argv) > 3 else '1'
        ext = {}
        for pair in _sys.argv[4:]:
            if '=' in pair:
                k, v = pair.split('=', 1)
                ext[k] = v
        r = s.categoryContent(tid, pg, False, ext)
        print("page:", r['page'], "| pagecount:", r['pagecount'],
              "| items:", len(r['list']))
        print(json.dumps(r['list'][:3], ensure_ascii=False))
    elif action == 'detail':
        vid = _sys.argv[2] if len(_sys.argv) > 2 else '198822'
        r = s.detailContent(vid)
        d = r['list'][0] if r.get('list') else {}
        out = dict(d)
        out['vod_play_url'] = (out.get('vod_play_url') or '')[:250]
        print(json.dumps(out, ensure_ascii=False))
    elif action == 'play':
        pid = _sys.argv[2] if len(_sys.argv) > 2 else ''
        print(json.dumps(s.playerContent('', pid, []), ensure_ascii=False))
    elif action == 'search':
        kw = _sys.argv[2] if len(_sys.argv) > 2 else '爱情'
        pg = _sys.argv[3] if len(_sys.argv) > 3 else '1'
        r = s.searchContent(kw, False, pg)
        print("items:", len(r.get('list', [])), "| msg:", r.get('msg', ''))
        print(json.dumps(r['list'][:3], ensure_ascii=False))
    s.close()

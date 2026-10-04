# -*- coding: utf-8 -*-
"""
第九短剧网 (www.gzsns.com) Python Spider — 兼容 FongMi/TV (T3) 与 WebHomeTV/PeekPro (T4)
【定制版 v10】苹果CMS10 + vfed 模板，基于真实 HTML 结构逐页实测

本次修订(基于线上抓包实测):
  1) 分类筛选面板重做:  类型 / 地区 / 年份 / 排序  四组下拉全部内置
     - 真实筛选路由:  /show/{id}/area/{值}.html    地区
                      /show/{id}/year/{值}.html     年份(年代)
                      /show/{id}/by/{time|hits|score}.html  排序
     - 二级分类(总裁短剧等)本身就是独立分类路由 /show/{subid}.html,
       在 filter 中作为“类型”维度, 选定后 id 切到子分类, 可与地区/年份/排序叠加。
     - 各筛选段可任意组合, 服务端会自行规范化顺序。
  2) 分页路由修正(实测): 统一为  {当前筛选URL去掉.html}/page/{n}.html
       例: 无筛选   /show/3/page/2.html
           带筛选   /show/3/area/大陆/page/2.html
  3) 搜索修复(实测): 本网站 /search.html?wd= 后端已失效——任意关键词都 302 跳到某部
     无关详情页, 其页面正文是“猜你喜欢”推荐(与关键词无关)。
     v9 曾把这份无关推荐当搜索结果返回, 造成“搜索内容不对”。
     现改为: 跟随 302 → 解析详情主片 → 仅当主片标题确实包含关键词才作为单条结果返回,
     否则判定站点无该词结果并返回空, 不再把无关推荐塞给用户。
  4) 加载/图片速度:
     - 首页首屏由多个分类并发抓取聚合, 显著缩短首屏等待。
     - 图片直给 CDN 原址(https://img.shyleps.com/...), 不二次加工。
     - 网络超时全面收紧, 失败快速降级, 避免整页卡顿。
"""

import sys
import json
import re
import time
import threading

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as _rq
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass

    class Spider:
        def fetch(self, url, headers=None, **kw):
            timeout = kw.pop('timeout', 15)
            r = _rq.get(url, headers=headers, timeout=timeout, verify=False, **kw)
            return r

from urllib.parse import quote


# ============================================================
# 常量（全部来自首页/分类页实测）
# ============================================================

HOST = "https://www.gzsns.com"

UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36")

CLASSES = [
    {"type_name": "电影",   "type_id": "1"},
    {"type_name": "电视剧", "type_id": "2"},
    {"type_name": "短剧",   "type_id": "3"},
    {"type_name": "动漫",   "type_id": "4"},
    {"type_name": "综艺",   "type_id": "5"},
    {"type_name": "奈飞新剧", "type_id": "48"},
]

# 二级分类（短剧/影视细分）。它们本身是独立分类路由 /show/{id}.html，
# 选定时即把当前分类 id 切到该二级 id，可再叠加 地区/年份/排序。
SUBCATS = {
    "1":  [("剧情片", "6"), ("动作片", "7"), ("冒险片", "8"), ("喜剧片", "9"),
           ("奇幻片", "10"), ("恐怖片", "11"), ("悬疑片", "16"), ("惊悚片", "17")],
    "2":  [("国产剧", "12"), ("港剧", "13"), ("韩剧", "14"), ("日剧", "15"),
           ("泰剧", "23"), ("台剧", "24"), ("欧美剧", "25"), ("新马剧", "26")],
    "3":  [("总裁短剧", "41"), ("神豪短剧", "42"), ("穿越重生短剧", "43"),
           ("都市短剧", "44"), ("年代短剧", "45"), ("长篇剧场", "46")],
    "4":  [("国产动漫", "36"), ("日本动漫", "37"), ("韩国动漫", "38"),
           ("欧美动漫", "39"), ("港台动漫", "40"), ("漫剧", "47")],
    "5":  [("国产综艺", "30"), ("港台综艺", "31"), ("韩国综艺", "32"),
           ("日本综艺", "33"), ("欧美综艺", "35")],
    "48": [("奈飞电影", "49"), ("奈飞自制剧", "50")],
}

# 站点全分类统一筛选值（实测 电影1/电视剧2/短剧3/动漫4/综艺5/奈飞48 的
# 地区 / 年代下拉完全一致，因此全局复用一份即可）
AREAS = ["大陆", "欧美", "香港", "美国", "台湾", "日本", "韩国", "英国",
         "法国", "德国", "俄罗斯", "泰国", "印度", "加拿大", "西班牙",
         "意大利", "新加坡"]
YEARS = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019",
         "2018", "2017", "2016", "2015", "2014", "2013", "2012", "2011"]
SORTS = [("按时间", "time"), ("按人气", "hits"), ("按评分", "score")]


def _options(pairs):
    return [{"n": "全部", "v": ""}] + [{"n": n, "v": v} for n, v in pairs]


FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    flt = []
    # 类型：二级分类（选定后 id 切到二级子分类路由）
    if tid in SUBCATS:
        flt.append({"key": "sub", "name": "类型", "value": _options(SUBCATS[tid])})
    # 地区
    flt.append({"key": "area", "name": "地区",
                "value": _options([(a, a) for a in AREAS])})
    # 年份
    flt.append({"key": "year", "name": "年份",
                "value": _options([(y, y) for y in YEARS])})
    # 排序
    flt.append({"key": "by", "name": "排序",
                "value": _options(SORTS)})
    FILTERS[tid] = flt


# 搜索路由候选（实测该站 /search.html?wd= 已失效，这里按序尝试并做关键词命中校验）
SEARCH_TPLS = [
    "/search.html?wd=%s",
    "/vod/search/wd/%s.html",
]


# ============================================================
# Spider 主类
# ============================================================

class Spider(Spider):

    def getName(self):
        return "第九短剧网"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ""
        else:
            self.extend = extend or ""
        self.header = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        }
        self._home_cache = []
        self._home_cache_time = 0
        self._home_lock = threading.Lock()
        self._pg_cache = {}
        self._search_tpl = None

    # ===== 网络层 =====
    def _rsp_text(self, rsp):
        try:
            raw = rsp.content
            if raw:
                for enc in ("utf-8", "gb18030"):
                    try:
                        return raw.decode(enc)
                    except Exception:
                        continue
                return raw.decode("utf-8", "ignore")
        except Exception:
            pass
        try:
            return rsp.text or ""
        except Exception:
            return ""

    def _fetch_text(self, url, timeout=(2.5, 4.5), retries=1):
        for i in range(retries + 1):
            try:
                rsp = self.fetch(url, headers=self.header, timeout=timeout)
                text = self._rsp_text(rsp)
                if text and len(text) > 100:
                    return text
            except Exception:
                pass
            if i < retries:
                time.sleep(0.2)
        return ""

    def _match(self, pattern, text, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1) if m else ""

    def _strip_tags(self, s):
        return re.sub(r'<[^>]+>', '', s or '').strip()

    # ===== 卡片解析（vfed 模板，实测结构） =====
    def _parse_cards(self, html):
        cards = []
        seen = set()
        for m in re.finditer(
                r'<li class="fed-list-item[^"]*"[^>]*>(.*?)</li>\s*(?=<li|</ul>)',
                html, re.S):
            block = m.group(1)
            vid = self._match(r'/detail/(\d+)\.html', block)
            if not vid or vid in seen:
                continue
            pic = self._match(r'data-original="([^"]+)"', block)
            if pic and pic.startswith('//'):
                pic = "https:" + pic
            title = self._strip_tags(self._match(
                r'<a class="fed-list-title[^"]*"[^>]*>(.*?)</a>', block, re.S))
            if not title:
                continue
            status = self._strip_tags(self._match(
                r'<span class="fed-list-remarks[^"]*"[^>]*>(.*?)</span>', block, re.S))
            seen.add(vid)
            cards.append({
                "vod_id": vid,
                "vod_name": title[:60],
                "vod_pic": pic or "",
                "vod_remarks": status or "HD",
            })
        return cards

    # ===== 详情/播放 =====
    def _is_direct_media(self, url):
        url = (url or "").lower()
        return any(x in url for x in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".mpd"))

    def _line_names(self, html):
        names = {}
        for m in re.finditer(r'data-target="#playsx(\d+)"[^>]*>(.*?)</a>', html, re.S):
            names[int(m.group(1))] = self._strip_tags(m.group(2))[:10]
        if names:
            return names
        idx = 0
        for m in re.finditer(r'data-target="#[^"]*?(\d+)"[^>]*>(.*?)</a>', html, re.S):
            t = self._strip_tags(m.group(2))
            if t and len(t) <= 12 and not t.startswith(("上一", "下一")):
                names[int(m.group(1))] = t[:10]
        if names:
            return names
        idx = 0
        tab = self._match(r'class="[^"]*play[^"]*tab[^"]*"[^>]*>(.*?)</ul>', html, re.S)
        if tab:
            for m in re.finditer(r'<a[^>]*>(.*?)</a>', tab, re.S):
                t = self._strip_tags(m.group(1))
                if t and t not in ("收起", "展开") and len(t) <= 12:
                    idx += 1
                    names[idx] = t[:10]
        return names

    def _parse_detail_main(self, html, vid):
        """解析一个详情页的“主影片”字段；解析不到主标题返回 None。"""
        title = self._strip_tags(self._match(r'<h1[^>]*>(.*?)</h1>', html, re.S))[:60]
        if not title:
            title = self._match(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
            title = (title or "").strip()[:60]
        if not title:
            return None
        pic = self._match(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
        if not pic:
            pic = self._match(r'data-original="(https?://[^"]+)"', html)
        if pic and pic.startswith('//'):
            pic = "https:" + pic
        content = self._match(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html)
        remarks = self._strip_tags(self._match(
            r'<span class="fed-list-remarks[^"]*"[^>]*>(.*?)</span>', html, re.S))[:20]
        return {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic or "",
            "vod_remarks": remarks or "",
            "vod_content": (content or "")[:800],
        }

    # ============================================================
    # 首页
    # ============================================================

    def homeContent(self, filter):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        now = int(time.time())
        with self._home_lock:
            if self._home_cache and now - self._home_cache_time < 600:
                return {"list": list(self._home_cache)}

        result = {}
        def _worker(url):
            try:
                text = self._fetch_text(url, timeout=(2.5, 4.5), retries=0)
                if text:
                    result[url] = self._parse_cards(text)
            except Exception:
                pass

        targets = [HOST + "/"] + [HOST + "/show/%s.html" % c["type_id"]
                                  for c in CLASSES[:5]]
        threads = []
        for u in targets:
            t = threading.Thread(target=_worker, args=(u,))
            t.daemon = True
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=6)

        videos = []
        have = set()
        # 聚合顺序：首页 > 各分类，去重
        for u in targets:
            for card in result.get(u, []):
                if card["vod_id"] not in have:
                    videos.append(card)
                    have.add(card["vod_id"])

        if not videos:
            videos = [{"vod_id": "__diag__", "vod_name": "连接失败 点我看原因",
                       "vod_pic": "", "vod_remarks": "点进此卡片"}]

        with self._home_lock:
            self._home_cache = videos[:60]
            self._home_cache_time = int(time.time())
        return {"list": videos[:60]}

    # ============================================================
    # 分类列表（类型/地区/年份/排序 四维 + 翻页）
    # ============================================================

    def _base_list_url(self, tid, extend):
        """根据筛选条件构造不含分页的列表 URL（第1页）。"""
        ext = extend if isinstance(extend, dict) else {}
        if isinstance(extend, str):
            try:
                ext = json.loads(extend)
            except Exception:
                ext = {}
        # 类型(二级子分类)决定基础分类 id
        base = tid
        sub = str(ext.get("sub", "") or "")
        if sub.isdigit():
            base = sub

        path = "/show/%s" % base
        segs = []
        for key, label in (("area", "area"), ("year", "year")):
            v = str(ext.get(key, "") or "").strip()
            if v:
                segs.append("%s/%s" % (label, quote(v)))
        by = str(ext.get("by", "") or "").strip().lower()
        if by in ("time", "hits", "score", "addtime"):
            if by == "addtime":
                by = "time"
            segs.append("by/%s" % by)
        if segs:
            path += "/" + "/".join(segs)
        path += ".html"
        return HOST + path

    def _total_pages(self, html):
        """从 vfed 页码区抽最大页数。"""
        best = 0
        seg = html
        i = html.find('fed-page')
        if i >= 0:
            seg = html[i:i + 4000]
        for m in re.finditer(r'href="[^"]*/(\d+)\.html"[^>]*>\s*(\d+)\s*</a>', seg):
            best = max(best, int(m.group(2)))
        # 兜底：识别 “1/2173” 形式
        mm = re.search(r'1/(\d+)', seg)
        if mm:
            best = max(best, int(mm.group(1)))
        return best

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1
            key = "%s|%s|%d" % (tid, extend, 1)
            base_url = self._base_list_url(str(tid), extend)

            # 构造带分页的 URL：统一把 .html 替换成 /page/{n}.html
            if page <= 1:
                url = base_url
            else:
                url = base_url[: -len(".html")] + "/page/%d.html" % page

            html = self._fetch_text(url, timeout=(2.5, 4.5), retries=1)
            if not html or "/detail/" not in html:
                return {"page": page, "pagecount": page, "limit": 20,
                        "total": 0, "list": []}

            cards = self._parse_cards(html)
            total = self._total_pages(html)
            pagecount = max(total, page, 1)
            return {"list": cards, "page": page, "pagecount": pagecount,
                    "limit": 20, "total": pagecount * max(len(cards), 1)}
        except Exception:
            return {"page": 1, "pagecount": 1, "limit": 20, "total": 0, "list": []}

    # ============================================================
    # 详情页
    # ============================================================

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vid = str(ids[0])

        if vid == "__diag__":
            return {"list": [{
                "vod_id": vid, "vod_name": "诊断信息", "vod_pic": "",
                "vod_content": "无法连接站点。请检查网络能否打开 https://www.gzsns.com/",
                "vod_play_from": "提示",
                "vod_play_url": "打开站点$https://www.gzsns.com/",
            }]}

        try:
            return self._detail(vid)
        except Exception:
            return {"list": []}

    def _detail(self, vid):
        url = HOST + "/detail/%s.html" % vid
        html = self._fetch_text(url, timeout=(2.5, 4.5), retries=1)
        if not html or len(html) < 500:
            return {"list": []}

        main = self._parse_detail_main(html, vid)
        if not main:
            return {"list": []}

        line_names = self._line_names(html)

        # ===== 播放选集：模式无关提取 =====
        EXCLUDE_PREFIX = ("/detail/", "/show/", "/t/", "/tags", "/ranking",
                          "/map", "/art/", "/label/", "javascript", "#")
        EP_TEXT = re.compile(
            r'^(第?\d{1,4}[集期话回部]?|HD.*|BD.*|TC.*|TS.*|DVD.*|正片.*|预告.*|全集.*|完结.*|上|下|'
            r'\d{1,4}[-—]\d{1,4}|更新至?.*|第.*?[集期])$')

        raw_eps = []
        for m in re.finditer(
                r'<a[^>]+href="((?:https?://[^/"]+)?/[^"<>]+)"[^>]*>(.*?)</a>', html, re.S):
            href, text = m.group(1), self._strip_tags(m.group(2))
            text = re.sub(r'\s+', ' ', text)
            if not text or len(text) > 25:
                continue
            path = href.replace(HOST, '') if href.startswith('http') else href
            if any(path.startswith(p) for p in EXCLUDE_PREFIX):
                continue
            if not (EP_TEXT.match(text) or re.search(r'第\d+', text)):
                continue
            if 'play' not in path and 'vod' not in path and '.html' not in path:
                continue
            raw_eps.append((path, text))

        groups = {}
        order = []
        for path, text in raw_eps:
            base = path.split('?')[0]
            base = re.sub(r'/[^/]+\.[a-zA-Z0-9]+$', '', base) or '/play'
            nums = re.findall(r'(\d+)', path)
            if len(nums) >= 3:
                key = base + '#' + nums[-2]
            else:
                key = base
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append((path, text))

        def _ep_key(item):
            text, path = item[1], item[0]
            nums = re.findall(r'(\d{1,8})', text)
            if nums:
                n = int(nums[0])
                if n > 100000:
                    return int(str(n)[-4:])
                return n
            nums2 = re.findall(r'(\d+)', path)
            return int(nums2[-1]) if nums2 else 0

        name_list = [line_names[k] for k in sorted(line_names.keys())]
        play_from, play_url = [], []
        for gi, key in enumerate(order):
            eps = sorted(groups[key], key=_ep_key)
            if gi < len(name_list):
                name = name_list[gi]
            else:
                clean = key.split('#')[0].strip('/').split('/')[-1] or 'play'
                name = clean[:10]
            play_from.append(name)
            play_url.append("#".join(
                "%s$%s" % (t, HOST + p if p.startswith('/') else p) for p, t in eps))

        if not play_url:
            m = re.search(r'(https?://[^"\'<>\s\\]+?\.m3u8[^"\'<>\s\\]*)', html)
            if m:
                play_from, play_url = ["直链"], ["播放$" + m.group(1).replace("\\/", "/")]

        main["vod_play_from"] = "$$$".join(play_from) if play_from else "暂无"
        main["vod_play_url"] = "$$$".join(play_url) if play_url else "暂无$" + url
        return {"list": [main]}

    # ============================================================
    # 搜索（修复：不再把站点详情页的无关推荐当结果）
    # ============================================================

    def searchContent(self, key, quick, pg="1"):
        try:
            kw = quote(key)
            # 1) 若已有可用路由，先试一次
            if self._search_tpl:
                return self._search_via(HOST + (self._search_tpl % kw), key)
            # 2) 按序尝试各候选
            for tpl in SEARCH_TPLS:
                res = self._search_via(HOST + (tpl % kw), key)
                if res["list"]:
                    self._search_tpl = tpl
                    return res
            # 3) 最终尝试首页真实搜索入口
            res = self._search_via(HOST + "/search.html?wd=" + kw, key)
            return res
        except Exception:
            return {"list": []}

    def _search_via(self, url, key):
        """请求一个搜索 URL 并做“关键词命中校验”。

        本网站 /search.html?wd= 会 302 到某部无关详情页（后端搜索已失效），
        其正文是“猜你喜欢”推荐。为避免把无关推荐当结果：
          - 若返回的是详情页且主片标题包含关键词 -> 返回该单条（真正命中的）；
          - 否则视为无有效结果，返回空。
        """
        try:
            html = self._fetch_text(url, timeout=(2.5, 4.5), retries=0)
            if not html:
                return {"list": []}
            # 情况 A：站点把搜索词解析后仍落在列表/标签结果页（含多张卡片）
            if html.count('<li class="fed-list-item') >= 2:
                cards = self._parse_cards(html)
                if cards:
                    # 若这是“结果列表”，卡片标题应普遍含关键词才有意义；
                    # 但 vfed 详情页底部“猜你喜欢”也有卡片，故按主标题是否含词过滤
                    hit = [c for c in cards if self._title_hit(c["vod_name"], key)]
                    if hit:
                        return {"list": hit}
                    return {"list": []}
            # 情况 B：被 302 落到了某个详情页 -> 校验该详情主片是否含关键词
            if html.count('<li class="fed-list-item') < 2 or '/detail/' in html:
                vid = self._match(r'/detail/(\d+)\.html', html)
                main = self._parse_detail_main(html, vid or "0")
                if main and self._title_hit(main["vod_name"], key):
                    return {"list": [main]}
            return {"list": []}
        except Exception:
            return {"list": []}

    @staticmethod
    def _title_hit(title, key):
        """标题与关键词命中判断（宽松：标题含关键词任一字词即算）。"""
        if not title or not key:
            return False
        t = title.lower()
        k = key.lower()
        if k in t:
            return True
        # 多关键词（空格分隔）时要求至少一个命中
        for part in re.split(r'[\s,，]+', k):
            if part and len(part) >= 1 and part in t:
                return True
        return False

    # ============================================================
    # 播放（v10：player_data 优先 + 多级嗅探 + 直链）
    # ============================================================

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}
        url = str(id).replace("\\/", "/")
        if not url.startswith("http"):
            url = HOST + (url if url.startswith("/") else "/" + url)
        hdr = {"User-Agent": UA, "Referer": HOST + "/"}

        # 直链直接播
        if self._is_direct_media(url):
            is_m3u8 = ".m3u8" in url.lower()
            fmt = "application/x-mpegURL" if is_m3u8 else ""
            return {"parse": 0, "playUrl": "", "url": url,
                    "header": hdr, "format": fmt, "contentType": fmt}

        # 官源交给壳子
        low = url.lower()
        if any(k in low for k in ("mgtv.com", "youku.com", "iqiyi.com", "qiyi.com",
                                  "v.qq.com", "bilibili.com")):
            return {"parse": 1, "playUrl": "", "url": url, "header": hdr}

        # 播放页深度嗅探
        html = self._fetch_text(url, timeout=(2, 3), retries=0)
        if html:
            pm = re.search(r'player_data\s*=\s*(\{.*?\})\s*;', html, re.S)
            if pm:
                try:
                    pdata = json.loads(pm.group(1))
                    pu = (pdata.get("url") or "").replace("\\/", "/")
                    if pu.startswith("http") and self._is_direct_media(pu):
                        return {"parse": 0, "playUrl": "", "url": pu, "header": hdr,
                                "format": "application/x-mpegURL",
                                "contentType": "application/x-mpegURL"}
                except Exception:
                    pass
            m = re.search(r'"url"\s*:\s*"((?:https?:)?\\\\?/\\\\?/[^"]+?\.m3u8[^"]*)"', html)
            if m:
                direct = m.group(1).replace("\\/", "/")
                if direct.startswith("//"):
                    direct = "https:" + direct
                if direct.startswith("http") and self._is_direct_media(direct):
                    return {"parse": 0, "playUrl": "", "url": direct, "header": hdr,
                            "format": "application/x-mpegURL",
                            "contentType": "application/x-mpegURL"}
            fm = re.search(r'<iframe[^>]+src="([^"]+)"', html)
            if fm:
                fsrc = fm.group(1).replace("&amp;", "&")
                if fsrc.startswith("//"):
                    fsrc = "https:" + fsrc
                elif fsrc.startswith("/"):
                    fsrc = HOST + fsrc
                elif not fsrc.startswith("http"):
                    fsrc = self._extract_origin(url) + fsrc
                fhtml = self._fetch_text(fsrc, timeout=(2, 3), retries=0)
                if fhtml:
                    m = re.search(r'(https?://[^"\'<>\s\\]+?\.m3u8[^"\'<>\s\\]*)', fhtml)
                    if not m:
                        m = re.search(r'"url"\s*:\s*"((?:https?:)?\\?/\\?/[^"]+?\.m3u8[^"]*)"', fhtml)
                    if m:
                        direct = m.group(1).replace("\\/", "/")
                        if direct.startswith("//"):
                            direct = "https:" + direct
                        if direct.startswith("http") and self._is_direct_media(direct):
                            return {"parse": 0, "playUrl": "", "url": direct, "header": hdr,
                                    "format": "application/x-mpegURL",
                                    "contentType": "application/x-mpegURL"}
                    pm2 = re.search(r'player_data\s*=\s*(\{.*?\})\s*;', fhtml, re.S)
                    if pm2:
                        try:
                            pdata = json.loads(pm2.group(1))
                            pu = (pdata.get("url") or "").replace("\\/", "/")
                            if pu.startswith("http") and self._is_direct_media(pu):
                                return {"parse": 0, "playUrl": "", "url": pu, "header": hdr,
                                        "format": "application/x-mpegURL",
                                        "contentType": "application/x-mpegURL"}
                        except Exception:
                            pass
            m = re.search(r'(https?://[^"\'<>\s\\]+?\.m3u8[^"\'<>\s\\]*)', html)
            if m:
                direct = m.group(1).replace("\\/", "/")
                return {"parse": 0, "playUrl": "", "url": direct, "header": hdr,
                        "format": "application/x-mpegURL",
                        "contentType": "application/x-mpegURL"}

        # WebView 兜底
        return {"parse": 1, "playUrl": "", "url": url, "header": hdr}

    def _extract_origin(self, url):
        try:
            m = re.match(r'(https?://[^/]+)', url)
            return m.group(1) if m else HOST
        except Exception:
            return HOST

    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    def destroy(self):
        pass

    def close(self):
        pass

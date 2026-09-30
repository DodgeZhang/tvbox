# -*- coding: utf-8 -*-
"""
量子资源 Python Spider — 兼容 FongMi/TV (T3) 与 WebHomeTV / PeekPro (T4)
主源: https://cj.lziapi.com
副源: 速播/就要/极速 — 详情页并发聚合线路（最多9条）
分类结构: 精选/电视剧/电影/综艺/动漫/短剧/体育 + 四维筛选（类型/地区/年份/语言）
"""

import sys
import json
import re
import time
import threading
from urllib.parse import quote

sys.path.append('..')

# ===== 兼容导入 =====
try:
    from base.spider import Spider
except ImportError:
    try:
        import requests as _rq
        try:
            import urllib3; urllib3.disable_warnings()
        except Exception:
            pass
        _session = _rq.Session()
        _session.verify = False
        _session.headers.update({"Connection": "keep-alive"})

        class Spider:
            def fetch(self, url, headers=None, **kw):
                timeout = kw.pop('timeout', 15)
                r = _session.get(url, headers=headers, timeout=timeout, **kw)
                r.encoding = 'utf-8'
                return r
    except ImportError:
        import urllib.request as _ur, ssl as _ssl

        class _FakeResp:
            def __init__(self, data):
                self.text = data.decode('utf-8', 'ignore')
                self.content = data

        class Spider:
            def fetch(self, url, headers=None, **kw):
                timeout = kw.pop('timeout', 15)
                ctx = _ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = _ssl.CERT_NONE
                req = _ur.Request(url, headers=headers or {})
                return _FakeResp(_ur.urlopen(req, timeout=timeout, context=ctx).read())

# ============================================================
# 常量
# ============================================================

HOST    = "https://cj.lziapi.com"
PRI_API = HOST + "/api.php/provide/vod/"
UA      = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) "
           "AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/120.0.0.0 Mobile Safari/537.36")

# 副源（仅用于详情页并发聚合线路）
SEC_APIS = [
    ("速播", "https://subocj.com/api.php/provide/vod/"),
    ("就要", "https://jyzyapi.com/api.php/provide/vod/"),
    ("极速", "https://jszyapi.com/api.php/provide/vod/"),
]

ROUTE_ALIAS = {
    "liangzi":     "量子线路",
    "lzm3u8":      "M3U8-量子",
    "subyun":      "速播线路",
    "subm3u8":     "M3U8-速播",
    "jinyingyun":  "就要线路",
    "jinyingm3u8": "M3U8-就要",
    "jsyun":       "极速线路",
    "jsm3u8":      "M3U8-极速",
    "http":        "下载线路",
}

# ── 顶级分类（与图片一致：精选/电视剧/电影/综艺/动漫/短剧/体育）───────────
# type_id "featured" 特殊处理：不过滤类型，展示最新内容
CLASSES = [
    {"type_id": "featured", "type_name": "精选"},
    {"type_id": "13",       "type_name": "电视剧"},
    {"type_id": "8",        "type_name": "电影"},
    {"type_id": "25",       "type_name": "综艺"},
    {"type_id": "29",       "type_name": "动漫"},
    {"type_id": "46",       "type_name": "短剧"},
    {"type_id": "37",       "type_name": "体育"},
]

# ── 各维度筛选 ────────────────────────────────────────────────────────────

_YEAR = {
    "key": "year", "name": "年份",
    "value": [
        {"n": "全部", "v": ""},
        {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
        {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"},
        {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"},
        {"n": "2020", "v": "2020"}, {"n": "更早",  "v": "2019"},
    ]
}
_BY = {
    "key": "by", "name": "排序",
    "value": [
        {"n": "最新", "v": "time"},
        {"n": "人气", "v": "hits"},
        {"n": "评分", "v": "score"},
    ]
}

# 地区（各大类共用，配合 API area= 参数）
_AREA_TV = {
    "key": "area", "name": "地区",
    "value": [
        {"n": "全部", "v": ""},
        {"n": "大陆", "v": "大陆"},  {"n": "香港", "v": "香港"},
        {"n": "台湾", "v": "台湾"},  {"n": "韩国", "v": "韩国"},
        {"n": "美国", "v": "美国"},  {"n": "日本", "v": "日本"},
        {"n": "泰国", "v": "泰国"},
    ]
}
_AREA_MOVIE = {
    "key": "area", "name": "地区",
    "value": [
        {"n": "全部", "v": ""},
        {"n": "大陆", "v": "大陆"},  {"n": "香港", "v": "香港"},
        {"n": "台湾", "v": "台湾"},  {"n": "美国", "v": "美国"},
        {"n": "韩国", "v": "韩国"},  {"n": "日本", "v": "日本"},
        {"n": "英国", "v": "英国"},  {"n": "法国", "v": "法国"},
    ]
}

# 语言
_LANG = {
    "key": "lang", "name": "语言",
    "value": [
        {"n": "全部", "v": ""},
        {"n": "国语", "v": "国语"},  {"n": "英语", "v": "英语"},
        {"n": "粤语", "v": "粤语"},  {"n": "日语", "v": "日语"},
        {"n": "韩语", "v": "韩语"},  {"n": "泰语", "v": "泰语"},
    ]
}

# 类型（电视剧）—— key="t" 会覆盖 categoryContent 里的 eff_tid
_TYPE_TV = {
    "key": "t", "name": "类型",
    "value": [
        {"n": "全部",   "v": ""},
        {"n": "国产剧", "v": "13"}, {"n": "港台剧", "v": "14"},
        {"n": "韩剧",   "v": "15"}, {"n": "欧美剧", "v": "16"},
        {"n": "日剧",   "v": "22"}, {"n": "台剧",   "v": "21"},
        {"n": "泰剧",   "v": "24"},
    ]
}
_TYPE_MOVIE = {
    "key": "t", "name": "类型",
    "value": [
        {"n": "全部",   "v": ""},
        {"n": "爱情片", "v": "8"},  {"n": "恐怖片", "v": "10"},
        {"n": "记录片", "v": "20"},
    ]
}
_TYPE_SHOW = {
    "key": "t", "name": "类型",
    "value": [
        {"n": "全部",   "v": ""},
        {"n": "大陆综艺", "v": "25"}, {"n": "港台综艺", "v": "26"},
        {"n": "日韩综艺", "v": "27"}, {"n": "欧美综艺", "v": "28"},
    ]
}
_TYPE_ANIME = {
    "key": "t", "name": "类型",
    "value": [
        {"n": "全部",   "v": ""},
        {"n": "国产动漫", "v": "29"}, {"n": "日韩动漫", "v": "30"},
    ]
}
_TYPE_SPORT = {
    "key": "t", "name": "类型",
    "value": [
        {"n": "全部",   "v": ""},
        {"n": "足球", "v": "37"}, {"n": "篮球", "v": "38"},
        {"n": "网球", "v": "39"},
    ]
}

FILTERS = {
    "featured": [_BY],
    "13":  [_TYPE_TV,    _AREA_TV,    _YEAR, _LANG],  # 电视剧：四维筛选
    "8":   [_TYPE_MOVIE, _AREA_MOVIE, _YEAR, _LANG],  # 电影：四维筛选
    "25":  [_TYPE_SHOW,  _AREA_TV,    _YEAR],          # 综艺：三维
    "29":  [_TYPE_ANIME, _YEAR],                        # 动漫：二维
    "46":  [_YEAR, _BY],                                # 短剧
    "37":  [_TYPE_SPORT, _YEAR],                        # 体育
}

# ============================================================
# TTL 缓存
# ============================================================

class _TtlCache:
    def __init__(self):
        self._store = {}

    def get(self, key):
        item = self._store.get(key)
        if item and time.time() - item[1] < item[2]:
            return item[0]
        return None

    def set(self, key, value, ttl):
        self._store[key] = (value, time.time(), ttl)

_cache = _TtlCache()

# ============================================================
# Spider 主类
# ============================================================

class Spider(Spider):

    def __init__(self):
        self._home_cache      = []
        self._home_cache_time = 0
        self.header = {"User-Agent": UA, "Referer": HOST + "/"}

    def getName(self):
        return "量子资源"

    def init(self, extend=""):
        self.extend = "" if isinstance(extend, list) else (extend or "")

    # ─── 网络工具 ────────────────────────────────────────────────────

    def _rsp_text(self, rsp):
        if rsp is None: return ""
        if isinstance(rsp, str):  return rsp
        if isinstance(rsp, bytes): return rsp.decode('utf-8', 'ignore')
        try:   return rsp.text
        except Exception:
            try: return rsp.content.decode('utf-8', 'ignore')
            except Exception: return ""

    def _get_json(self, url, timeout=8):
        try:
            text = self._rsp_text(self.fetch(url, headers=self.header, timeout=timeout))
            return json.loads(text) if text else None
        except Exception:
            return None

    @staticmethod
    def _get_json_raw(url, timeout=7):
        """独立请求（副源并发用）"""
        try:
            import urllib.request as ur, ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = ur.Request(url, headers={"User-Agent": UA})
            data = ur.urlopen(req, timeout=timeout, context=ctx).read()
            return json.loads(data.decode('utf-8', 'ignore'))
        except Exception:
            return None

    # ─── 辅助 ────────────────────────────────────────────────────────

    @staticmethod
    def _norm_pic(pic):
        pic = (pic or "").strip()
        if not pic: return ""
        return ("https:" + pic) if pic.startswith("//") else pic

    @staticmethod
    def _alias_routes(from_str):
        parts = from_str.split("$$$") if from_str else []
        return "$$$".join(ROUTE_ALIAS.get(p.strip(), p.strip()) for p in parts)

    def _item_to_card(self, item):
        return {
            "vod_id":      str(item.get("vod_id", "")),
            "vod_name":    item.get("vod_name", "未知"),
            "vod_pic":     self._norm_pic(item.get("vod_pic", "")),
            "vod_remarks": item.get("vod_remarks", ""),
        }

    # ─── 多源线路并发聚合 ─────────────────────────────────────────────

    def _fetch_sec_routes(self, title, results):
        def fetch_one(name, api):
            try:
                enc = quote(title, safe='')
                r   = self._get_json_raw(api + "?ac=videolist&wd=" + enc + "&pg=1", timeout=6)
                if not r or not r.get("list"):
                    return
                for item in r["list"]:
                    if title in item.get("vod_name", ""):
                        d = self._get_json_raw(
                            api + "?ac=videolist&ids=" + str(item["vod_id"]), timeout=6)
                        if d and d.get("list"):
                            sec = d["list"][0]
                            f, u = sec.get("vod_play_from",""), sec.get("vod_play_url","")
                            if f and u:
                                results.append((f, u))
                        break
            except Exception:
                pass

        threads = [threading.Thread(target=fetch_one, args=(n, a), daemon=True)
                   for n, a in SEC_APIS]
        for t in threads: t.start()
        for t in threads: t.join(timeout=7)

    def _build_detail(self, item):
        content = re.sub(r'<[^>]+>', '',
                         item.get("vod_content") or item.get("vod_blurb") or "").strip()
        pri_from  = item.get("vod_play_from", "")
        pri_url   = item.get("vod_play_url",  "")
        down_from = item.get("vod_down_from", "")
        down_url  = item.get("vod_down_url",  "")

        sec_results = []
        title = item.get("vod_name", "")
        if title:
            self._fetch_sec_routes(title, sec_results)

        all_froms = pri_from.split("$$$") if pri_from else []
        all_urls  = pri_url.split("$$$")  if pri_url  else []
        if down_url and down_url.strip():
            all_froms.append(down_from or "http")
            all_urls.append(down_url)
        for sec_f, sec_u in sec_results:
            for f, u in zip(sec_f.split("$$$"), sec_u.split("$$$")):
                if f.strip() and u.strip():
                    all_froms.append(f.strip())
                    all_urls.append(u.strip())

        return {
            "vod_id":       str(item.get("vod_id", "")),
            "vod_name":     item.get("vod_name",    "未知"),
            "vod_pic":      self._norm_pic(item.get("vod_pic", "")),
            "type_name":    item.get("type_name",   ""),
            "vod_year":     str(item.get("vod_year", "")),
            "vod_area":     item.get("vod_area",    ""),
            "vod_remarks":  item.get("vod_remarks", ""),
            "vod_actor":    item.get("vod_actor",   ""),
            "vod_director": item.get("vod_director",""),
            "vod_content":  content,
            "vod_play_from": self._alias_routes("$$$".join(all_froms)),
            "vod_play_url":  "$$$".join(all_urls),
        }

    # ============================================================
    # 首页
    # ============================================================

    def homeContent(self, filter):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        now = int(time.time())
        if self._home_cache and now - self._home_cache_time < 300:
            return {"list": self._home_cache}
        data = self._get_json(PRI_API + "?ac=videolist&pg=1&by=time", timeout=8)
        if not data or not data.get("list"):
            return {"list": []}
        cards = [self._item_to_card(i) for i in data["list"]]
        self._home_cache      = cards
        self._home_cache_time = now
        return {"list": cards}

    # ============================================================
    # 分类列表（四维筛选：类型/地区/年份/语言）
    # ============================================================

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg or 1))
            ext  = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:    ext = json.loads(extend)
                    except: ext = {}

            year = ext.get("year", "")
            by   = ext.get("by",   "time")
            area = ext.get("area", "")
            lang = ext.get("lang", "")
            # 类型筛选：key="t" 覆盖顶级 tid
            sub_t = ext.get("t", "")

            # 精选：不过滤类型
            if tid == "featured":
                url = PRI_API + "?ac=videolist&pg=%d&by=%s" % (page, by or "time")
            else:
                eff_tid = sub_t if sub_t else tid
                url = PRI_API + "?ac=videolist&t=%s&pg=%d" % (eff_tid, page)
                if by:   url += "&by="   + by
                if year: url += "&year=" + year
                if area: url += "&area=" + quote(area, safe='')
                if lang: url += "&lang=" + quote(lang, safe='')

            cached = _cache.get("cat_" + url)
            if cached: return cached

            data = self._get_json(url, timeout=8)
            if not data:
                return {"page": page, "pagecount": 1, "limit": 20, "total": 0, "list": []}

            result = {
                "list":      [self._item_to_card(i) for i in data.get("list", [])],
                "page":      page,
                "pagecount": int(data.get("pagecount", 1)),
                "limit":     20,
                "total":     int(data.get("total", 0)),
            }
            _cache.set("cat_" + url, result, ttl=180)
            return result
        except Exception:
            return {"page": 1, "pagecount": 1, "limit": 20, "total": 0, "list": []}

    # ============================================================
    # 详情（多源线路聚合）
    # ============================================================

    def detailContent(self, ids):
        if isinstance(ids, str): ids = [ids]
        vod_id = str(ids[0])
        cached = _cache.get("det_" + vod_id)
        if cached: return cached

        data = self._get_json(PRI_API + "?ac=videolist&ids=" + vod_id, timeout=8)
        if not data or not data.get("list"):
            return {"list": []}

        vod = self._build_detail(data["list"][0])
        if not vod.get("vod_play_url"):
            return {"list": []}

        result = {"list": [vod]}
        _cache.set("det_" + vod_id, result, ttl=300)
        return result

    # ============================================================
    # 搜索
    # ============================================================

    def searchContent(self, key, quick, pg="1"):
        try:
            key = (key or "").strip()
            if not key: return {"list": []}
            page    = max(1, int(pg or 1))
            encoded = quote(key, safe='')
            data    = self._get_json(
                PRI_API + "?ac=videolist&wd=%s&pg=%d" % (encoded, page),
                timeout=10)
            if not data or not data.get("list"):
                return {"list": []}
            return {"list": [self._item_to_card(i) for i in data["list"]]}
        except Exception:
            return {"list": []}

    # ============================================================
    # 播放解析
    # ============================================================

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}
        play_url  = str(id).replace("\\/", "/")
        url_lower = play_url.lower()
        is_m3u8   = ".m3u8" in url_lower
        is_media  = is_m3u8 or ".mp4" in url_lower or ".flv" in url_lower
        if is_media:
            return {
                "parse":       0,
                "playUrl":     "",
                "url":         play_url,
                "header":      {"User-Agent": UA, "Referer": HOST + "/"},
                "format":      "application/x-mpegURL" if is_m3u8 else "",
                "contentType": "application/x-mpegURL" if is_m3u8 else "",
            }
        return {
            "parse":  1,
            "playUrl": "",
            "url":    play_url,
            "header": {"User-Agent": UA, "Referer": HOST + "/"},
        }

    def localProxy(self, param):
        return [200, "text/plain", b"ok", {}]

    def destroy(self): pass
    def close(self):   self.destroy()

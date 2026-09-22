# -*- coding: utf-8 -*-
# ============================================================
#  kanju.ai (看剧AI) · TVBox 爬虫  v1.1 搜索修复版
#  修复:
#   1. 移除 requests/secrets 硬依赖 → 纯标准库可用, 有 requests 则优先
#   2. _req 不再静默吞异常 → 失败原因写 stderr (TVBox logcat 可见)
#   3. init 改用带签名的 API 心跳选域名 (TVBox fetch 返回 str 无 status_code,
#      原逻辑备用域名永远选不上)
#   4. searchContent: 支持翻页 + 长标题召回兜底 (逐段截短重试)
#   5. _vod 字段类型加固 (actors/directors 可能是字符串)
# ============================================================
import sys
import json
import time
import hmac
import hashlib
import random
import urllib.parse
import urllib.request
import gzip as _gzip
import math

sys.path.append('..')
try:
    from base.spider import Spider as _Base
except ImportError:
    class _Base(object):
        def fetch(self, url, headers=None, **kw):
            import requests as rq
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

try:
    import requests as _rq
except Exception:
    _rq = None

HOSTS = ["https://kanju.ai", "https://kanju20.com"]
KEY = "557d0e4ae929f438da6bd84412374e6086b8af09b3fed54bf22601d5bf8c54a0"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
YJ = "https://zy.baipiaozhe.com/v1/playback/yjm3u8/%s.m3u8"
CLIENT = {
    "x-ai-movie-client-name": "dianyingtiantang-frontend",
    "x-ai-movie-client-version": "1.0.0",
    "x-ai-movie-build-version": "dianyingtiantang-v2026.08.11.1-8cbb0b0d407e-672e67d62528",
    "x-ai-movie-protocol-version": "2026-07-05.library-v2.playback-v1",
}

CATEGORIES = {
    "movie": "电影", "series": "电视剧", "short_drama": "短剧",
    "anime": "动漫", "variety": "综艺", "documentary": "纪录片",
}
GENRES = {
    "movie": ["动作", "冒险", "剧情", "喜剧", "奇幻", "古装", "家庭", "科幻"],
    "series": ["动作", "冒险", "剧情", "刑侦", "古装", "历史", "台剧", "悬疑"],
    "short_drama": ["剧情", "动作", "反转爽剧", "古装仙侠", "喜剧", "女频恋爱", "家庭", "年代"],
    "anime": ["热血", "冒险", "奇幻", "日本动漫", "国产动漫", "爆笑", "武侠", "儿童"],
    "variety": ["大陆综艺", "真人秀", "情感", "爱情", "社交观察"],
    "documentary": ["历史", "纪录片"],
}


def _log(*a):
    sys.stderr.write("[kanju] " + " ".join(str(x) for x in a) + "\n")


def _token_hex(n):
    return "".join(random.choice("0123456789abcdef") for _ in range(n * 2))


def _join_names(v, n):
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "/".join(str(x) for x in v[:n])
    return ""


class Spider(_Base):
    def init(self, extend=""):
        self._hi = 0
        # 用带签名的轻量 API 探测域名, 不用 fetch+status_code (TVBox fetch 返回 str)
        for i, h in enumerate(HOSTS):
            try:
                ts, nonce, sig = self._sign("GET", "/v1/feed/home")
                hdrs = self._headers(h, ts, nonce, sig)
                code, _ = self._http("GET", h + "/v1/feed/home", hdrs, None, 8)
                if code == 200:
                    self._hi = i
                    _log("选用域名:", h)
                    break
            except Exception as e:
                _log("域名探测失败", h, repr(e))
        return ""

    # ---------- 底层 HTTP ----------
    def _headers(self, host, ts, nonce, sig):
        hdrs = {"User-Agent": UA, "Accept": "application/json",
                "Referer": host + "/", "x-ai-movie-timestamp": ts,
                "x-ai-movie-nonce": nonce, "x-ai-movie-signature": sig}
        hdrs.update(CLIENT)
        return hdrs

    def _http(self, method, url, headers, data, timeout):
        """返回 (status, text)。优先 requests, 缺失时用 urllib。"""
        if _rq is not None:
            r = _rq.request(method, url, data=data, headers=headers, timeout=timeout)
            return r.status_code, r.text
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = _gzip.decompress(raw)
                return resp.status, raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                if e.headers.get("Content-Encoding") == "gzip":
                    raw = _gzip.decompress(raw)
            except Exception:
                pass
            return e.code, raw.decode("utf-8", "replace")

    def _sign(self, method, path):
        ts = str(int(time.time() * 1000))
        nonce = _token_hex(16)
        msg = "%s\n%s\n%s\n%s" % (method, path, ts, nonce)
        sig = hmac.new(KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
        return ts, nonce, sig

    def _host(self):
        return HOSTS[getattr(self, '_hi', 0)]

    def _req(self, method, path, body=None):
        for attempt in range(len(HOSTS)):
            host = self._host()
            try:
                ts, nonce, sig = self._sign(method, path)
                hdrs = self._headers(host, ts, nonce, sig)
                data = None
                if body is not None:
                    hdrs["Content-Type"] = "application/json"
                    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                code, text = self._http(method, host + path, hdrs, data, 12)
                if code in (200, 201):
                    return json.loads(text)
                _log(method, path, "-> HTTP", code, text[:120])
            except Exception as e:
                _log(method, path, "异常:", repr(e))
            self._hi = (self._hi + 1) % len(HOSTS)
            time.sleep(1)
        return {}

    # ---------- 映射 ----------
    def _vod(self, c):
        if not isinstance(c, dict):
            return None
        return {
            "vod_id": c.get("id", ""),
            "vod_name": c.get("title", ""),
            "vod_pic": c.get("poster_url", ""),
            "vod_remarks": c.get("remarks") or str(c.get("year") or ""),
            "vod_year": c.get("year") or "",
            "vod_area": c.get("area") or "",
            "vod_actor": _join_names(c.get("actors"), 3),
            "vod_director": _join_names(c.get("directors"), 2),
        }

    # ---------- TVBox 接口 ----------
    def homeContent(self, filter=False):
        cls = []
        for k, v in CATEGORIES.items():
            cls.append({
                "type_id": k, "type_name": v,
                "subs": [{"type_id": "%s:%s" % (k, g), "type_name": g} for g in GENRES[k]],
            })
        return {"class": cls, "list": []}

    def homeVideoContent(self):
        now = time.time()
        if getattr(self, "_hv_t", 0) > now - 300 and getattr(self, "_hv", None):
            return self._hv
        seen, lst = set(), []
        paths = ["/v1/feed/home",
                 "/v1/browse/catalog?kind=movie&sort=trending&window=day&page=1&limit=40",
                 "/v1/browse/catalog?kind=series&sort=trending&window=day&page=1&limit=40"]
        for p in paths:
            j = self._req("GET", p)
            for s in (j.get("sections") or []):
                for c in (s.get("cards") or []):
                    v = self._vod(c)
                    if v and v["vod_id"] and v["vod_id"] not in seen:
                        seen.add(v["vod_id"])
                        lst.append(v)
            for c in (j.get("cards") or []):
                v = self._vod(c)
                if v and v["vod_id"] and v["vod_id"] not in seen:
                    seen.add(v["vod_id"])
                    lst.append(v)
        self._hv, self._hv_t = {"list": lst}, now
        return self._hv

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        cat, gen = str(tid), ""
        if ":" in cat:
            cat, gen = cat.split(":", 1)
        if cat not in CATEGORIES:
            cat = "movie"
        if gen:
            path = "/v1/browse/catalog?kind=%s&genre=%s&page=%d&limit=40" % (cat, urllib.parse.quote(gen), pn)
        else:
            path = "/v1/browse/catalog?kind=%s&page=%d&limit=40" % (cat, pn)
        j = self._req("GET", path)
        cards = j.get("cards") or []
        total = (j.get("pagination") or {}).get("total", 0) or 0
        return {"page": pn, "pagecount": max(math.ceil(total / 40), 1), "limit": 40,
                "total": total, "list": [v for v in (self._vod(c) for c in cards) if v]}

    def detailContent(self, ids):
        if isinstance(ids, list):
            vid = ids[0] if ids else ""
        else:
            vid = str(ids) if ids else ""
        vid = vid.split("/")[0]
        if not vid:
            return {"list": []}
        d = self._req("GET", "/v1/catalog/%s" % vid)
        # 详情失败时尝试 work_id (搜索卡片的 id 偶尔不是 canonical id)
        if not d.get("episodes") and vid.startswith("av_"):
            _log("详情空, vod_id=", vid[:40])
        eps = d.get("episodes") or []
        urls = []
        for e in eps:
            t = e.get("token")
            if t:
                urls.append("%s$%s" % (e.get("title") or "第%s集" % (e.get("number") or len(urls) + 1), t))
        play_from, play_url = "kanju", "#".join(urls)
        if eps and urls:
            tok0 = eps[0].get("token")
            if tok0:
                try:
                    rj = self._req("GET", "/v1/playback/resolve/%s" % tok0)
                    # 不截断：网站返回多少条线路就展示多少条
                    names = [l.get("provider_name") or "" for l in (rj.get("line_options") or [])]
                    names = [n for n in names if n]
                    if names:
                        play_from = "$$$".join(names)
                        play_url = "$$$".join([play_url] * len(names))
                except Exception as e:
                    _log("resolve 线路异常:", repr(e))
        return {"list": [{
            "vod_id": vid, "vod_name": d.get("title", ""), "vod_pic": d.get("poster_url", ""),
            "vod_year": d.get("year", ""), "vod_area": d.get("area", ""),
            "vod_class": _join_names(d.get("genres"), 3),
            "vod_director": _join_names(d.get("directors"), 2),
            "vod_actor": _join_names(d.get("actors"), 3),
            "vod_content": d.get("description") or "",
            "vod_remarks": d.get("status") or d.get("remarks") or "",
            "vod_play_from": play_from, "vod_play_url": play_url,
        }]}

    def searchContent(self, key, quick=False, pg="1"):
        k = str(key or "").strip()
        if not k:
            return {"list": [], "page": 1, "pagecount": 1}
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1

        def do_query(q, page):
            path = "/v1/browse/catalog?q=%s&page=%d&limit=20" % (urllib.parse.quote(q), page)
            return self._req("GET", path)

        # 1) 完整关键词
        j = do_query(k, pn)
        cards = j.get("cards") or []
        used = k
        # 2) 长标题召回兜底: 完整词 0 结果时, 逐步截短重试 (服务端搜索对长串召回差)
        trims = [k[:-2], k[:-4], k[:6], k[:4]] if len(k) > 4 else []
        for t in trims:
            if cards:
                break
            if t and len(t) >= 2:
                _log("搜索[%s]无结果, 兜底重试[%s]" % (k, t))
                j = do_query(t, pn)
                cards = j.get("cards") or []
                used = t
        total = (j.get("pagination") or {}).get("total", 0) or 0
        lst = [v for v in (self._vod(c) for c in cards) if v]
        return {"list": lst, "page": pn,
                "pagecount": max(math.ceil(total / 20), 1) if total else (1 if lst else 1)}

    def playerContent(self, flag, id, vipFlags=None, vipIds=None):
        tok = str(id or "").strip()
        if not tok:
            return {"url": ""}
        # 1) 用签名解析接口拿到播放线路
        j = self._req("GET", "/v1/playback/resolve/%s" % tok)
        lines = j.get("line_options") or []
        wanted = str(flag or "")
        if wanted and wanted != "kanju":
            picked = [l for l in lines if (l.get("provider_name") or "") == wanted]
            lines = picked or lines
        for lo in lines:
            t = (lo.get("url") or "").strip()
            if not t:
                continue
            if t.startswith("resolve://"):
                rj = self._req("POST", "/v1/playback/resolve-line", {"ticket": t[10:]})
                url = (rj.get("line") or {}).get("url") or ""
            else:
                url = t
            if url:
                return {"parse": 0, "url": url}
        # 2) 兜底：白嫖者 YJ 直链
        try:
            if _rq is not None:
                r = _rq.get(YJ % tok, headers={"User-Agent": UA}, timeout=6, allow_redirects=False)
                if r.status_code == 200 and "#EXTM3U" in r.text:
                    return {"parse": 0, "url": YJ % tok}
            else:
                code, text = self._http("GET", YJ % tok, {"User-Agent": UA}, None, 6)
                if code == 200 and "#EXTM3U" in text:
                    return {"parse": 0, "url": YJ % tok}
        except Exception as e:
            _log("YJ 兜底异常:", repr(e))
        return {"url": ""}

    def localProxy(self, param):
        return None
# -*- coding: utf-8 -*-
# 看剧AI kanju19.com (hipy t4 py源)
# 协议: HMAC-SHA256 请求签名; 剧集token经 /v1/playback/resolve 解析多线路
# 追剧日历: /v1/watch-calendar (对应 https://kanju19.com/updates)
import sys
import time
import math
import hmac
import hashlib
import secrets
import datetime
import urllib.parse

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def fetch(self, url, headers=None, **kw):
            import requests as rq
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

import requests

HOSTS = [
    "https://kanju19.com",
    "https://main.kanju13.com",
    "https://kanju20.com",
    "https://kanju.ai",
]
KEY = "557d0e4ae929f438da6bd84412374e6086b8af09b3fed54bf22601d5bf8c54a0"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
YJ_M3U8 = "https://zy.baipiaozhe.com/v1/playback/yjm3u8/%s.m3u8"
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

# 实测各 genre 取值服务端均真实过滤(假类型返回0条)
GENRES = {
    "movie": ["动作", "冒险", "剧情", "喜剧", "奇幻", "古装", "家庭", "科幻"],
    "series": ["动作", "冒险", "剧情", "刑侦", "古装", "历史", "台剧", "悬疑"],
    "short_drama": ["剧情", "动作", "反转爽剧", "古装仙侠", "喜剧", "女频恋爱", "家庭", "年代"],
    "anime": ["热血", "冒险", "奇幻", "日本动漫", "国产动漫", "爆笑", "武侠", "儿童"],
    "variety": ["大陆综艺", "真人秀", "情感", "爱情", "社交观察"],
    "documentary": ["历史", "纪录片"],
}

# 追剧日历筛选项, 与 /updates 页面四个 tab 一致
CAL_KINDS = [("series", "电视剧"), ("anime", "动漫"), ("variety", "综艺"), ("movie", "电影")]
CAL_KIND_SET = {"series", "anime", "variety", "movie"}
WEEKDAYS = [("0", "今天"), ("1", "周一"), ("2", "周二"), ("3", "周三"),
            ("4", "周四"), ("5", "周五"), ("6", "周六"), ("7", "周日")]
CAL_SORTS = [("heat", "热度优先"), ("year", "年份最新")]
CAL_LIMIT = 20


class Spider(Spider):
    def init(self, extend=""):
        self._hi = 0
        self._cal_more = {}
        for i, h in enumerate(HOSTS):
            try:
                r = requests.get(h + "/v1/runtime/bootstrap", headers={"User-Agent": UA}, timeout=(5, 10))
                if r.status_code == 200:
                    self._hi = i
                    break
            except Exception:
                continue
        return ""

    def getName(self):
        return "看剧AI19"

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def _host(self):
        return HOSTS[getattr(self, '_hi', 0)]

    def _sign(self, method, path):
        ts = str(int(time.time() * 1000))
        nonce = secrets.token_hex(16)
        msg = "%s\n%s\n%s\n%s" % (method, path, ts, nonce)
        sig = hmac.new(KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
        return ts, nonce, sig

    def _req(self, method, path, body=None):
        for _ in range(len(HOSTS)):
            host = self._host()
            try:
                ts, nonce, sig = self._sign(method, path)
                hdrs = {
                    "User-Agent": UA, "Accept": "application/json",
                    "Referer": host + "/",
                    "x-ai-movie-timestamp": ts, "x-ai-movie-nonce": nonce,
                    "x-ai-movie-signature": sig,
                }
                hdrs.update(CLIENT)
                if body is not None:
                    hdrs["Content-Type"] = "application/json"
                    r = requests.post(host + path, json=body, headers=hdrs, timeout=10)
                else:
                    r = requests.get(host + path, headers=hdrs, timeout=10)
                if r.status_code in (200, 201):
                    return r.json()
            except Exception:
                pass
            self._hi = (self._hi + 1) % len(HOSTS)
        return {}

    @staticmethod
    def _parse_ext(extend):
        """兼容 dict / query串 / 空值"""
        if isinstance(extend, dict):
            return extend
        d = {}
        if extend:
            for pair in str(extend).split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    d[urllib.parse.unquote(k)] = urllib.parse.unquote(v)
        return d

    @staticmethod
    def _today_weekday():
        """Asia/Shanghai 的 ISO 星期: 周一=1 ... 周日=7 (与接口 weekday 一致)"""
        tz = datetime.timezone(datetime.timedelta(hours=8))
        return datetime.datetime.now(tz).isoweekday()

    def _vod(self, c):
        return {
            "vod_id": c.get("id", ""),
            "vod_name": c.get("title", ""),
            "vod_pic": c.get("poster_url", ""),
            "vod_remarks": c.get("remarks") or str(c.get("year") or ""),
            "vod_year": str(c.get("year") or ""),
            "vod_area": c.get("area") or "",
            "vod_class": "/".join((c.get("genres") or [])[:3]),
        }

    def _cal_vod(self, c):
        remark = c.get("latest_episode_label") or c.get("season_label") or ""
        return {
            "vod_id": c.get("id", ""),
            "vod_name": c.get("title", ""),
            "vod_pic": c.get("poster_url", ""),
            "vod_remarks": remark or str(c.get("year") or ""),
            "vod_year": str(c.get("year") or ""),
        }

    def homeContent(self, filter=False):
        cls = [{"type_id": "calendar", "type_name": "📅追剧日历"}]
        for k, v in CATEGORIES.items():
            cls.append({"type_id": k, "type_name": v})
        filters = {}
        # 各内容分类: 类型(genre)筛选 —— 走标准 filters/extend, 不再用 subs
        for k in CATEGORIES:
            filters[k] = [{
                "key": "genre", "name": "类型",
                "value": [{"n": "全部", "v": ""}] + [{"n": g, "v": g} for g in GENRES[k]],
            }]
        # 追剧日历: 类型(电影/电视剧/动漫/综艺) + 日期 + 排序
        filters["calendar"] = [
            {"key": "kind", "name": "类型",
             "value": [{"n": n, "v": v} for v, n in CAL_KINDS]},
            {"key": "weekday", "name": "日期",
             "value": [{"n": n, "v": v} for v, n in WEEKDAYS]},
            {"key": "sort", "name": "排序",
             "value": [{"n": n, "v": v} for v, n in CAL_SORTS]},
        ]
        return {"class": cls, "filters": filters, "list": []}

    def homeVideoContent(self):
        seen, lst = set(), []
        j = self._req("GET", "/v1/feed/home")
        for s in (j.get("sections") or []):
            for c in (s.get("cards") or []):
                v = self._vod(c)
                if v["vod_id"] and v["vod_id"] not in seen:
                    seen.add(v["vod_id"])
                    lst.append(v)
        for c in (j.get("cards") or []):
            v = self._vod(c)
            if v["vod_id"] and v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                lst.append(v)
        return {"list": lst}

    def _cal_group(self, j, kind, wd):
        """从 watch-calendar 响应中取出指定星期/类型的分组, 返回 (more_url, items, total)"""
        days = j.get("days") or []
        day = None
        for d in days:
            if int(d.get("weekday") or 0) == wd:
                day = d
                break
        if day is None and days:
            day = days[0]
        if not day:
            return None, [], 0
        grp = (day.get("groups") or {}).get(kind) or {}
        return grp.get("more_url"), (grp.get("preview") or []), int(grp.get("total") or 0)

    def _calendar_content(self, pn, ext):
        kind = ext.get("kind") or "series"
        if kind not in CAL_KIND_SET:
            kind = "series"
        sort = ext.get("sort") or "heat"
        if sort not in ("heat", "year"):
            sort = "heat"
        try:
            wd = int(ext.get("weekday") or "0")
        except Exception:
            wd = 0
        if wd <= 0:
            wd = self._today_weekday()
        wd = min(max(wd, 1), 7)
        key = "%s:%d:%s" % (kind, wd, sort)
        if pn <= 1:
            path = ("/v1/watch-calendar?week=current&sort=%s&kind=%s&weekday=%d&limit=%d"
                    % (sort, kind, wd, CAL_LIMIT))
            j = self._req("GET", path)
            more, cards, total = self._cal_group(j, kind, wd)
            self._cal_more[key] = more
        else:
            more = self._cal_more.get(key)
            if not more:
                return {"page": pn, "pagecount": 1, "limit": CAL_LIMIT, "total": 0, "list": []}
            # more_url 已含 view/cursor 等全部 query, 直接按完整 path 重新签名
            j = self._req("GET", more)
            more, cards, total = self._cal_group(j, kind, wd)
            self._cal_more[key] = more
        return {
            "page": pn,
            "pagecount": max(int(math.ceil(total / float(CAL_LIMIT))), 1),
            "limit": CAL_LIMIT,
            "total": total,
            "list": [self._cal_vod(c) for c in cards],
        }

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        ext = self._parse_ext(extend)
        if str(tid) == "calendar":
            return self._calendar_content(pn, ext)
        cat = str(tid)
        if cat not in CATEGORIES:
            cat = "movie"
        gen = ext.get("genre", "")
        limit = 40
        path = "/v1/browse/catalog?kind=%s&page=%d&limit=%d" % (cat, pn, limit)
        if gen:
            path += "&genre=%s" % urllib.parse.quote(gen)
        j = self._req("GET", path)
        cards = j.get("cards") or []
        total = int((j.get("pagination") or {}).get("total") or 0)
        return {
            "page": pn,
            "pagecount": max(int(math.ceil(total / float(limit))), 1),
            "limit": limit,
            "total": total,
            "list": [self._vod(c) for c in cards],
        }

    def detailContent(self, ids):
        if isinstance(ids, list):
            vid = ids[0] if ids else ""
        else:
            vid = str(ids) if ids else ""
        vid = vid.split("/")[0]
        if not vid:
            return {"list": []}
        d = self._req("GET", "/v1/catalog/%s" % vid)
        if not d or d.get("error"):
            return {"list": []}
        eps = d.get("episodes") or []
        urls = []
        for e in eps:
            tok = e.get("token")
            if not tok:
                continue
            name = e.get("title") or e.get("display_name") or "第%d集" % (len(urls) + 1)
            urls.append("%s$%s" % (name, tok))
        play_from, play_url = "kanju", "#".join(urls)
        if eps and urls:
            tok0 = eps[0].get("token")
            if tok0:
                rj = self._req("GET", "/v1/playback/resolve/%s" % tok0)
                names, seen = [], set()
                for lo in (rj.get("line_options") or []):
                    n = lo.get("provider_name") or lo.get("label") or ""
                    if n and n not in seen:
                        seen.add(n)
                        names.append(n)
                    if len(names) >= 12:
                        break
                if names:
                    play_from = "$$$".join(names)
                    play_url = "$$$".join(["#".join(urls)] * len(names))
        kind = d.get("content_kind") or ""
        remark = d.get("remarks") or ""
        if kind and kind != "movie" and d.get("episode_count"):
            remark = remark or "全%s集" % d.get("episode_count")
        return {"list": [{
            "vod_id": vid, "vod_name": d.get("title", ""), "vod_pic": d.get("poster_url", ""),
            "vod_year": str(d.get("year") or ""), "vod_area": d.get("area") or "",
            "vod_class": "/".join((d.get("genres") or [])[:3]),
            "vod_director": "/".join((d.get("directors") or [])[:2]),
            "vod_actor": "/".join((d.get("actors") or [])[:3]),
            "vod_content": d.get("description") or "",
            "vod_remarks": remark,
            "vod_play_from": play_from, "vod_play_url": play_url,
        }]}

    def searchContent(self, key, quick=False, pg="1"):
        k = str(key or "").strip()
        if not k:
            return {"list": []}
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        j = self._req("GET", "/v1/browse/catalog?q=%s&page=%d&limit=20" % (urllib.parse.quote(k), pn))
        return {"list": [self._vod(c) for c in (j.get("cards") or [])]}

    def playerContent(self, flag, id, vipFlags=None):
        tok = str(id or "").strip()
        if not tok:
            return {"parse": 1, "playUrl": "", "url": "", "header": {"User-Agent": UA}}
        rj = self._req("GET", "/v1/playback/resolve/%s" % tok)
        lines = rj.get("line_options") or []

        def resolve_line(ticket):
            rj2 = self._req("POST", "/v1/playback/resolve-line", {"ticket": ticket})
            return ((rj2.get("line") or {}).get("url") or "").strip()

        def pick(cands):
            for lo in cands:
                u = (lo.get("url") or "").strip()
                if u.startswith("resolve://"):
                    u = resolve_line(u[10:])
                if u.startswith("http"):
                    return u
            return ""

        ordered = []
        if flag:
            ordered += [lo for lo in lines if (lo.get("provider_name") or "") == str(flag)]
        ordered += [lo for lo in lines if lo.get("url_kind") == "m3u8" and lo.get("resolved")]
        ordered += lines
        url = pick(ordered)
        if not url:
            murl = YJ_M3U8 % tok
            try:
                r = requests.get(murl, headers={"User-Agent": UA}, timeout=8)
                if r.status_code == 200 and "#EXTM3U" in r.text:
                    url = murl
            except Exception:
                pass
        if not url:
            return {"parse": 1, "playUrl": "", "url": "", "header": {"User-Agent": UA}}
        direct = (".m3u8" in url) or (".mp4" in url) or (".mkv" in url) or (".flv" in url)
        return {
            "parse": 0 if direct else 1,
            "playUrl": "",
            "url": url,
            "header": {"User-Agent": UA, "Referer": self._host() + "/"},
        }

    def localProxy(self, param):
        return None

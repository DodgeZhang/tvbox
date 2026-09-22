# -*- coding: utf-8 -*-
import re
import sys
import json
import time
import random
import hashlib
import urllib.request
from urllib.parse import quote

sys.path.append('..')
from base.spider import Spider

_UA = "okhttp/4.12.0"
_FINGER = "SF-F5F11CB15897115AE6BCFE063C288F730CA865588F572C780A3E8477D0DD3776"
_SK = "SK-sk_13oXDZ7u9j2Tk1c0cawWVFfO"
_DEVICE_UUID = "uuid-a43a3421-2704-4deb-afe4-136aed229307"
_USER_TOKEN = "ZThkNjRlYzhlNmZmNzZkMDI1ZDhhMTVhNzA2YjFlN2YxYjQwMTA5NzBkZThiN2NlZTk0ZGYzOWU2MmQ5NzQ3Y3wxMzI5NnxmemNyeW18MTc4ODM1ODE1Ng=="

# 分类：type_id(1/2/3/4) -> filter/vod 的 type_name
_CATS = [("1", "电影"), ("2", "剧集"), ("3", "动漫"), ("4", "综艺")]

# 播放源顺序：易被防盗链拦截的分片源排到末尾(用户仍可手切)
_REORDER = ("IMDB", "CO4K", "qsvip")


class Spider(Spider):

    def getName(self):
        return "云朵影视"

    def init(self, extend=""):
        self.host = "http://154.21.198.181:8002"
        try:
            text = str(extend or "").strip()
            if text.startswith("{"):
                ext = json.loads(text)
                if isinstance(ext, dict) and ext.get("host"):
                    self.host = str(ext.get("host")).rstrip("/")
        except Exception:
            pass
        self.ua = _UA
        # 集 ID -> 影片 id，player 跨线路回落用(集 ID 不携带影片 id)
        self._ep2vid = {}
        # 影片 id -> [(flag, 首集ID)] 供跨线路回落
        self._lines = {}

    def getDependence(self):
        return []

    # ---- 数据层(app 接口 + RN/Hermes 签名) ----

    def _sign_headers(self):
        t = str(int(time.time() * 1000))
        nonce = (hashlib.sha256(_DEVICE_UUID.encode()).hexdigest().upper()[:8]
                 + "".join(str(random.randint(0, 9)) for _ in range(8)))
        sign = hashlib.sha256((
            "finger=" + _FINGER + "&id=com.tvcloud.io&nonce=" + nonce
            + "&sk=" + _SK + "&time=" + t + "&v=4").encode()).hexdigest().upper()
        return {
            "User-Agent": self.ua, "accept": "application/json",
            "x-aid": "com.tvcloud.io", "x-ave": "4",
            "x-time": t, "x-nonc": nonce, "x-sign": sign,
            "x-device-id": _DEVICE_UUID, "x-device-brand": "realtek",
            "x-device-model": "ZIDOO_X9S", "x-client-type": "tv",
            "x-update-id": "embedded", "x-user-token": _USER_TOKEN,
        }

    def _fetch(self, path):
        """发送带认证的HTTP GET请求，返回原始文本"""
        try:
            req = urllib.request.Request(self.host + path, headers=self._sign_headers())
            resp = urllib.request.urlopen(req, timeout=20)
            return resp.read().decode('utf-8', errors='replace')
        except Exception as e:
            print(f'fetch error: {e}')
            return ""

    def _api(self, path):
        raw = self._fetch(path)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _decode(self, ep, flag):
        """单次 decode，返回 (is_ok, url_or_reason)。"""
        path = "/api.php/app/decode/url/?url={}&vodFrom={}&_t={}".format(
            quote(ep), quote(flag), int(time.time() * 1000))
        raw = self._fetch(path)
        try:
            d = json.loads(raw)
            u = (d.get("data") or "").strip()
            if d.get("code") == 1 and u.startswith("http"):
                return True, u
            return False, u or raw[:80]
        except Exception:
            return False, raw[:80]

    def _clean(self, s):
        return (s or "").replace("$", "＄").replace("#", "＃").strip()

    def _card(self, v):
        return {
            "vod_id": str(v.get("vod_id") or ""),
            "vod_name": str(v.get("vod_name") or ""),
            "vod_pic": v.get("vod_pic") or "",
            "vod_remarks": str(v.get("vod_remarks") or ""),
        }

    def _dedup(self, items):
        seen, out = set(), []
        for it in items:
            vid = str(it.get("vod_id") or "")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            out.append(self._card(it))
        return out

    # ---- 契约方法 ----

    def homeContent(self, filter):
        classes = [{"type_id": tid, "type_name": name} for tid, name in _CATS]
        result = {"class": classes, "filters": self._build_filters(), "list": []}
        cards = []
        j = self._api("/api.php/app/index/home")
        d = j.get("data") or {}
        for v in (d.get("recommend") or []):
            if v.get("vod_id"):
                cards.append(v)
        jr = self._api("/api.php/app/ranking/list")
        try:
            for rk in (jr.get("data") or {}).get("rankings") or []:
                for v in (rk.get("videos") or []):
                    if v.get("vod_id"):
                        cards.append(v)
        except Exception:
            pass
        if len(cards) < 20:
            tf = self._api("/api.php/app/filter/vod?type_name=%E7%94%B5%E5%BD%B1&page=1&limit=24&sort=hits")
            for v in (tf.get("data") or []):
                if v.get("vod_id"):
                    cards.append(v)
        result["list"] = self._dedup(cards)
        return result

    def homeVideoContent(self):
        result = {"list": []}
        items = []
        j = self._api("/api.php/app/index/home")
        d = j.get("data") or {}
        for v in (d.get("recommend") or []):
            if v.get("vod_id"):
                items.append(v)
        if len(items) < 20:
            for rk in ((self._api("/api.php/app/ranking/list").get("data") or {}).get("rankings") or []):
                for v in (rk.get("videos") or []):
                    if v.get("vod_id"):
                        items.append(v)
        result["list"] = self._dedup(items)
        return result

    def _build_filters(self):
        years = [{"n": "全部", "v": ""}]
        for y in range(2026, 2005, -1):
            years.append({"n": str(y), "v": str(y)})

        areas = ([{"n": "全部", "v": ""}] +
                 [{"n": x, "v": x} for x in
                  ("中国大陆", "中国香港", "中国台湾", "美国", "日本", "韩国", "泰国", "英国", "法国", "印度", "其他")])

        sorts = [{"n": "时间", "v": "time"}, {"n": "人气", "v": "hits"}, {"n": "评分", "v": "score"}]

        movie_class = ([{"n": "全部", "v": ""}] +
                       [{"n": x, "v": x} for x in
                        ("动作", "喜剧", "爱情", "科幻", "恐怖", "剧情", "战争", "犯罪", "奇幻", "冒险", "悬疑", "动画", "古装", "武侠", "历史", "家庭", "惊悚")])
        tv_class = ([{"n": "全部", "v": ""}] +
                    [{"n": x, "v": x} for x in
                     ("剧情", "喜剧", "爱情", "科幻", "悬疑", "恐怖", "古装", "动作", "家庭", "战争", "犯罪", "历史", "冒险", "奇幻", "国产剧")])
        anime_class = ([{"n": "全部", "v": ""}] +
                       [{"n": x, "v": x} for x in ("国产动漫", "日本动漫", "欧美动漫", "海外动漫", "其他")])

        variety_filters = [
            {"key": "area", "name": "地区", "value": areas},
            {"key": "sort", "name": "排序", "value": sorts},
            {"key": "year", "name": "年份", "value": years},
        ]

        return {
            "电影": [{"key": "class", "name": "类型", "value": movie_class},
                    {"key": "area", "name": "地区", "value": areas},
                    {"key": "sort", "name": "排序", "value": sorts},
                    {"key": "year", "name": "年份", "value": years}],
            "剧集": [{"key": "class", "name": "类型", "value": tv_class},
                    {"key": "area", "name": "地区", "value": areas},
                    {"key": "sort", "name": "排序", "value": sorts},
                    {"key": "year", "name": "年份", "value": years}],
            "综艺": variety_filters,
            "动漫": [{"key": "class", "name": "类型", "value": anime_class},
                    {"key": "sort", "name": "排序", "value": sorts},
                    {"key": "year", "name": "年份", "value": years}],
        }

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        result = {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}
        # type_id 或中文名都能定位 type_name
        name = dict(_CATS).get(str(tid), "")
        if not name:
            for _tid, nm in _CATS:
                if nm == str(tid):
                    name = nm
                    break
        if not name:
            name = "电影"
        url = "/api.php/app/filter/vod?type_name={}&page={}&limit=24&sort=hits".format(quote(name), page)
        if extend:
            area = extend.get("area", "")
            if area and area != "全部":
                url += f"&area={quote(area)}"
            cls = extend.get("class", "")
            if cls and cls != "全部":
                url += f"&class={quote(cls)}"
            year = extend.get("year", "")
            if year and year != "全部":
                url += f"&year={year}"
            sort = extend.get("sort", "")
            if sort:
                url += f"&sort={sort}"
        j = self._api(url)
        lst = j.get("data")
        if not isinstance(lst, list):
            lst = []
        result["list"] = [self._card(v) for v in lst if v.get("vod_id")]
        total = int(j.get("total") or len(result["list"]) or 0)
        pagecount = int(j.get("pageCount") or 0)
        if total > 0:
            result["total"] = total
        result["pagecount"] = pagecount or max(1, -(-total // 24)) if total else 1
        return result

    def detailContent(self, ids):
        result = {"list": []}
        vid = str(ids[0]).split(",")[0].split("?")[0].strip()
        j = self._api("/api.php/app/vod/get_detail?vod_id=" + quote(vid))
        data = j.get("data")
        if not isinstance(data, list) or not data:
            return result
        v = data[0]
        pf = (v.get("vod_play_from") or "").split("$$$")
        pu = (v.get("vod_play_url") or "").split("$$$")
        epmap = {}
        for i, f in enumerate(pf):
            if f and i < len(pu):
                epmap[f] = pu[i]
        flags = [f for f in pf if f and epmap.get(f)]
        if not flags and v.get("vod_play_url"):
            flags = ["线路1"]
            epmap = {"线路1": v["vod_play_url"]}

        # 线路排序：易被防盗链拦截的分片源排到末尾，TVBox 默认走稳定线路
        flags = [f for f in flags if f not in _REORDER] + [f for f in flags if f in _REORDER]
        urls = [epmap[f] for f in flags]

        # 缓存 集ID→影片 与 影片→(线路,首集ID) 回落表
        lines = []
        for f, uu in zip(flags, urls):
            eps = [x.split("$")[-1] for x in (uu.split("#") if uu else []) if x]
            first = eps[0] if eps else ""
            for e in eps:
                self._ep2vid[e] = vid
            if first:
                lines.append((f, first))
        self._lines[vid] = lines
        if len(self._ep2vid) > 30000:
            self._ep2vid.clear()
        if len(self._lines) > 4000:
            self._lines = {}

        content = re.sub(r"<[^>]+>", "", v.get("vod_content") or "").strip()
        result["list"] = [{
            "vod_id": vid,
            "vod_name": str(v.get("vod_name") or vid),
            "vod_pic": v.get("vod_pic") or "",
            "vod_year": str(v.get("vod_year") or ""),
            "vod_area": str(v.get("vod_area") or ""),
            "vod_director": str(v.get("vod_director") or ""),
            "vod_actor": str(v.get("vod_actor") or ""),
            "vod_content": content,
            "vod_remarks": str(v.get("vod_remarks") or ""),
            # 只有线路名做全角转义；vod_play_url 的 '#'/$ 原样保留
            "vod_play_from": "$$$".join(self._clean(x) for x in flags),
            "vod_play_url": "$$$".join(str(x) for x in urls),
        }]
        return result

    def searchContent(self, key, quick, pg="1"):
        result = {"list": []}
        kw = str(key or "").strip()
        if not kw:
            return result
        j = self._api("/api.php/app/search/index?wd={}&page={}".format(quote(kw), pg))
        d = j.get("data")
        lst = d if isinstance(d, list) else (d.get("videos", []) if isinstance(d, dict) else [])
        result["list"] = [self._card(v) for v in lst if v.get("vod_id")]
        return result

    def playerContent(self, flag, pid, vipFlags):
        result = {"parse": 0, "url": "", "header": {"Referer": self.host + "/", "User-Agent": self.ua}}
        ep = (pid or "").strip()
        if not ep or not flag:
            return result

        # ① 原线路递增重试，救间歇性失效
        for i in range(5):
            ok, u = self._decode(ep, flag)
            if ok:
                result["url"] = u
                return result
            time.sleep(0.5 + 0.6 * i)

        # ② 持久失效 → 跨线路自动回落：同片其它线路的首集
        vid = self._ep2vid.get(ep, "")
        if vid:
            for o_flag, o_first in self._lines.get(vid, []):
                if o_flag == flag:
                    continue
                ok, u = self._decode(o_first, o_flag)
                if ok:
                    result["url"] = u
                    return result
                time.sleep(0.3)
        return result

    def isVideoFormat(self, url):
        text = str(url or "").lower()
        return any(x in text for x in (".m3u8", ".mp4", ".flv", ".ts", ".mkv", ".webm", ".m4s"))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return None

    def destroy(self):
        return None

    def localProxy(self, params):
        return None

    def proxy(self, params):
        return self.localProxy(params)
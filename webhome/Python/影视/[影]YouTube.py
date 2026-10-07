# -*- coding: utf-8 -*-
# YouTube「探索」源 —— TVBox / hipy / 影视仓 T4 py 源
#
# 分类：电影解说 / 音乐 / 游戏 / 直播 / 新闻 / 体育 / 学习
# 列表：走 search 关键词 + continuation 翻页；直播第 1 页取官方 livetab
# 首页：网页首页推荐流（ANDROID_VR 客户端，WEB 未登录恒为空）
# 搜索 / 详情：InnerTube 接口（免 API Key、免登录）
# 播放：单条「自动」线路。点播默认交官方内嵌播放页（自带有效 token，不会被 60 秒截断）；
#   extend 打开 {"dash": true} 时改走本地合成 DASH，直播恒走 Invidious HLS
#
# 画质受限的根因是 player 接口被判定 bot（playabilityStatus=LOGIN_REQUIRED），此时不返回任何
# 流地址。extend 可配：
#   {"proxy":"http://192.168.1.2:7890"}               换出口 IP（注意代理要对设备可达）
#   {"cookie":"SAPISID=...; __Secure-3PAPISID=..."}   登录态 Cookie，含 SAPISID 才能签名成功
#   {"visitor":"Cgt..."}                              指定 visitorData，不填则自动从首页提取
#   另可选 {"dash":true,"seg":"proxy"|"direct"}（默认 dash 关、seg=proxy：分片经本地代理转发）

import sys
import json
import time
import re
import hashlib
import threading

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider(object):
        def fetch(self, url, headers=None, **kw):
            import requests as rq
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

import requests

HOST = "https://www.youtube.com"
API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
DEFAULT_CV = "2.20260101.00.00"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 分类走 search 关键词翻页；直播第 1 页另取官方 livetab
MOVIE_ID = "__movie__"                          # 电影解说
LIVE_ID = "UC4R8DWoMoI7CAwX8_LjQHig"            # 官方直播频道
LIVE_TAB_PARAMS = "EgdsaXZldGFi"                # livetab，内容最全

# 内容板块：browseId -> 中文名
MODULES = [
    (MOVIE_ID, "电影解说"),
    ("UC-9-kyTW8ZkZNDHQJ6FgpwQ", "音乐"),
    ("UCOpNcN46UbXVtpKMrmU4Abg", "游戏"),
    (LIVE_ID, "直播"),
    ("UCYfdidRxbB8Qhf0Nx7ioOYw", "新闻"),
    ("UCEgdi0XIXXZ-qJOFPf4JSKw", "体育"),
    ("FEcourses_destination", "学习"),
]
MODULE_NAME = dict(MODULES)

CATEGORY_QUERY = {
    MOVIE_ID: "电影解说",
    "UC-9-kyTW8ZkZNDHQJ6FgpwQ": "音乐",
    "UCOpNcN46UbXVtpKMrmU4Abg": "游戏",
    LIVE_ID: "直播",
    "UCYfdidRxbB8Qhf0Nx7ioOYw": "新闻",
    "UCEgdi0XIXXZ-qJOFPf4JSKw": "体育",
    "FEcourses_destination": "课程",
}


def _num(s):
    """取字符串开头的数字串（「1080」「1080P」「137」「1080P AV1」均可），取不到返回 0。"""
    s = str(s or "").strip()
    i = 0
    while i < len(s) and s[i].isdigit():
        i += 1
    return int(s[:i]) if i else 0


def _qual_of(s):
    """解析播放 id 后缀「itag_高度」，返回 (itag, 高度)。"""
    a, _, b = str(s or "").partition("_")
    return _num(a), _num(b)


# 内嵌播放页的期望清晰度参数 vq
_VQ_STEPS = [(2160, "hd2160"), (1440, "hd1440"), (1080, "hd1080"), (720, "hd720"),
             (480, "large"), (360, "medium"), (240, "small"), (144, "tiny")]


def _vq(h):
    """把期望高度转成内嵌播放器的 vq 值。"""
    for k, v in _VQ_STEPS:
        if h >= k:
            return v
    return "hd1080"


# 首页推荐流：WEB 未登录恒返回空页，ANDROID_VR 可拿到真实推荐
VR_CTX = {"client": {
    "clientName": "ANDROID_VR", "clientVersion": "1.65.10",
    "deviceMake": "Oculus", "deviceModel": "Quest 3",
    "androidSdkVersion": 32, "osName": "Android", "osVersion": "12L",
    "hl": "en", "gl": "US",
    "userAgent": ("com.google.android.apps.youtube.vr.oculus/1.65.10 "
                  "(Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip"),
}}

# 解析器候选（部署可替换/增补）
INVIDIOUS_SEED = [
    "https://invidious.f5.si",
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://yewtu.be",
    "https://iv.melmac.space",
]

# 卡片渲染器：video 类（含影视的电影卡片）
_VIDEO_RK = ("videoRenderer", "compactVideoRenderer", "gridVideoRenderer",
             "playlistVideoRenderer", "gridPlaylistRenderer",
             "gridMovieRenderer", "compactMovieRenderer", "movieRenderer")
# 卡片渲染器：新版统一卡片
_LOCKUP_RK = ("lockupViewModel",)


def _xml(s):
    """MPD 文本转义。"""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# Cookie 只发往 YouTube 自身域名，解析器实例与 googlevideo 分片都不带，避免泄露凭据
_COOKIE_HOSTS = ("youtube.com", "youtu.be")


def _is_host(url, hosts):
    """URL 域名是否属于 hosts（后缀匹配）。"""
    h = str(url or "").split("//", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    h = h.split("@")[-1].split(":")[0].lower()
    return any(h == x or h.endswith("." + x) for x in hosts)


def _sapisid_auth(cookie, origin=HOST):
    """谷歌登录态的 SAPISIDHASH 签名，InnerTube 判定登录身份必需。

    取 cookie 里的 SAPISID/__Secure-1PAPISID/__Secure-3PAPISID 做 sha1(ts " " key " " origin)
    签名；都缺失（如只从 document.cookie 复制，拿不到 HttpOnly 项）时返回空串，仅带 Cookie 头。
    """
    cookie = cookie or ""
    out = []
    for name, tag in (("SAPISID", "SAPISIDHASH"),
                      ("__Secure-1PAPISID", "SAPISID1PHASH"),
                      ("__Secure-3PAPISID", "SAPISID3PHASH")):
        m = re.search(r"(?:^|;\s*)" + name + r"=([^;]*)", cookie)
        if not m or not m.group(1).strip():
            continue
        ts = str(int(time.time()))
        h = hashlib.sha1(("%s %s %s" % (ts, m.group(1).strip(), origin))
                         .encode("utf-8")).hexdigest()
        out.append("%s %s_%s" % (tag, ts, h))
    return " ".join(out)


def _rngdict(s):
    """Invidious 的 "742-1229" Range 串转成 googlevideo 风格的 {start, end}。"""
    a, _, b = str(s or "").partition("-")
    a, b = a.strip(), b.strip()
    if not (a.isdigit() and b.isdigit()):
        return None
    return {"start": a, "end": b}


def _to_track(f):
    """Invidious 的 adaptiveFormat 转成与 ANDROID_VR 一致的轨道结构。"""
    w, _, h = str(f.get("size") or "").partition("x")
    return {
        "itag": int(f.get("itag") or 0),
        "mimeType": str(f.get("type") or ""),
        "url": str(f.get("url") or ""),
        "width": int(w) if w.isdigit() else 0,
        "height": int(h) if h.isdigit() else _num(f.get("resolution")),
        "bitrate": int(f.get("bitrate") or 0),
        "initRange": _rngdict(f.get("init")),
        "indexRange": _rngdict(f.get("index")),
    }


_SES = requests.Session()
_LK = threading.RLock()
# 媒体分片专用会话：播放时视频/音频并发请求，不能与解析请求共用 _LK，否则高码率分片互相排队
_MSES = requests.Session()
_msad = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=32)
_MSES.mount("http://", _msad)
_MSES.mount("https://", _msad)
_ST = {
    "cv": DEFAULT_CV, "cv_at": 0.0,        # 动态 clientVersion
    "proxy": None,                          # 代理（extend 配置）
    "cookie": "",                           # 登录态 Cookie（extend 配置）
    "visitor": "",                          # visitorData（extend 配置，缺省从首页提取）
    "chain": {},                            # 分页 continuation 链缓存
    "iv": "",                               # 已探活的 Invidious 实例
    # 默认关：Invidious 直链的 token 不按本机出口 IP 签发，YouTube 只放行该链前 60 秒，
    # 之后分片一律 403。extend {"dash": true} 才启用合成 DASH
    "dash": False,
    "seg": "proxy",                         # proxy=分片经本地代理转发（默认，403 时可换链重试）；direct=播放器直连
    "media": {},                            # vid -> 已解析的 DASH 轨道（含过期时间）
    "live": {},                             # vid -> 是否直播（详情页顺手记下，免去播放时再解析一次轨道）
    "na_at": 0.0,                           # 播放接口最近一次取流失败（被风控）的时间
    "r403": {},                             # vid -> 最近一次因 403 重取直链的时间
    "pdead_at": 0.0,                        # 单流 Invidious 最近一次失效的时间
    "home": [], "home_at": 0.0,             # 网页首页推荐流缓存
}


class Spider(Spider):
    # ------------------------------------------------------------------ 基础
    def init(self, extend=""):
        self._parse_extend(extend)
        return ""

    def getName(self):
        return "YouTube探索"

    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        p = param if isinstance(param, dict) else {}
        if not p and isinstance(param, str):
            try:
                from urllib.parse import parse_qs
                p = {k: v[0] for k, v in parse_qs(param.lstrip("?")).items()}
            except Exception:
                p = {}
        try:
            if p.get("type") == "mpd":
                return self._proxy_mpd(p)
            if p.get("type") == "media":
                return self._proxy_media(p)
        except Exception:
            pass
        return None

    def _parse_extend(self, extend):
        if not extend:
            return
        s = str(extend).strip()
        if not s:
            return
        cfg = None
        if s[0] in "{[":
            try:
                cfg = json.loads(s)
            except Exception:
                cfg = None
        if isinstance(cfg, dict):
            if cfg.get("proxy"):
                _ST["proxy"] = str(cfg["proxy"]).strip()
            if cfg.get("cookie"):
                _ST["cookie"] = str(cfg["cookie"]).strip()
            if cfg.get("visitor"):
                _ST["visitor"] = str(cfg["visitor"]).strip()
            if "dash" in cfg:
                _ST["dash"] = bool(cfg.get("dash"))
            if cfg.get("seg"):
                _ST["seg"] = str(cfg["seg"]).strip().lower()
        elif s.startswith("http"):
            _ST["proxy"] = s

    # ------------------------------------------------------------------ 网络层
    def _req(self, url, method="GET", headers=None, data=None, timeout=15):
        h = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
        if headers:
            h.update(headers)
        if _is_host(url, _COOKIE_HOSTS):
            if _ST["cookie"]:
                h["Cookie"] = _ST["cookie"]
            if _ST["visitor"]:
                h["X-Goog-Visitor-Id"] = _ST["visitor"]
        proxies = None
        if _ST["proxy"]:
            proxies = {"http": _ST["proxy"], "https": _ST["proxy"]}
        with _LK:
            if method == "POST":
                return _SES.post(url, headers=h, data=data, timeout=timeout,
                                 proxies=proxies)
            return _SES.get(url, headers=h, timeout=timeout, proxies=proxies)

    def _media_get(self, url, rng="", timeout=30):
        """媒体分片请求：走独立 Session，不占 _LK，也不带任何 Cookie。"""
        h = {"User-Agent": UA, "Referer": HOST + "/"}
        if rng:
            h["Range"] = rng
        proxies = None
        if _ST["proxy"]:
            proxies = {"http": _ST["proxy"], "https": _ST["proxy"]}
        return _MSES.get(url, headers=h, timeout=timeout, proxies=proxies)

    def _ensure_client(self, force=False):
        """从首页提取真实 INNERTUBE_CLIENT_VERSION 与 VISITOR_DATA（6 小时缓存）。

        固定 visitorData 比每次当新访客更不容易触发 bot 判定；extend 给了 visitor 则不覆盖。
        """
        now = time.time()
        if not force and _ST["cv_at"] and now - _ST["cv_at"] < 21600:
            return _ST["cv"]
        try:
            r = self._req(HOST + "/", timeout=12)
            t = r.text or ""
            m = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', t)
            if m:
                _ST["cv"] = m.group(1)
            m2 = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', t)
            if m2:
                _ST["key"] = m2.group(1)
            if not _ST["visitor"]:
                m3 = (re.search(r'"VISITOR_DATA":"([^"]+)"', t)
                      or re.search(r'"visitorData":"([^"]+)"', t))
                if m3:
                    _ST["visitor"] = m3.group(1)
        except Exception:
            pass
        _ST["cv_at"] = now
        return _ST["cv"]

    def _ctx(self):
        return {
            "client": {
                "hl": "zh-CN", "gl": "US", "clientName": "WEB",
                "clientVersion": self._ensure_client(),
                "userAgent": UA, "osName": "Windows",
                "osVersion": "10.0", "platform": "DESKTOP",
            }
        }

    def _innertube(self, endpoint, body, timeout=15, ctx=None):
        key = _ST.get("key") or API_KEY
        url = "%s/youtubei/v1/%s?key=%s&prettyPrint=false" % (HOST, endpoint, key)
        headers = {
            "Content-Type": "application/json",
            "Origin": HOST,
            "Referer": HOST + "/",
            "X-Goog-Api-Format-Version": "3",
        }
        az = _sapisid_auth(_ST.get("cookie") or "")
        if az:
            headers["Authorization"] = az
            headers["X-Origin"] = HOST
        base = ctx or self._ctx()
        if _ST.get("visitor") and isinstance(base, dict):
            base = dict(base)
            c = dict(base.get("client") or {})
            c.setdefault("visitorData", _ST["visitor"])
            base["client"] = c
        payload = {"context": base}
        if isinstance(body, dict):
            payload.update(body)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            r = self._req(url, method="POST", headers=headers, data=data,
                          timeout=timeout)
            if r.status_code != 200:
                if _ST.get("cv_at") and time.time() - _ST["cv_at"] > 3600:
                    self._ensure_client(force=True)
            return r.json()
        except Exception:
            # 不重试：壳每档线路只等 30 秒，必须尽早失败
            pass
        return {}

    # ------------------------------------------------------------------ 解析工具
    def _tx(self, node):
        """从 {simpleText} 或 {runs:[{text}]} 取文本。"""
        if not node:
            return ""
        if isinstance(node, str):
            return node
        if isinstance(node, dict):
            if node.get("simpleText"):
                return node["simpleText"]
            runs = node.get("runs")
            if isinstance(runs, list):
                return "".join([str(x.get("text", "")) for x in runs if isinstance(x, dict)])
            if node.get("content"):
                return str(node["content"])
        return ""

    def _dig(self, obj, path):
        cur = obj
        for k in path:
            if isinstance(cur, dict):
                cur = cur.get(k)
            elif isinstance(cur, list) and cur:
                cur = cur[0]
                cur = cur.get(k) if isinstance(cur, dict) else None
            else:
                return None
        return cur

    def _img_from_sources(self, sources):
        if not isinstance(sources, list) or not sources:
            return ""
        url = ""
        for s in sources:
            if isinstance(s, dict) and s.get("url"):
                url = s["url"]
        return url

    def _thumb(self, v):
        if not isinstance(v, dict):
            return ""
        t = v.get("thumbnail")
        if isinstance(t, dict):
            u = self._img_from_sources(t.get("thumbnails"))
            if u:
                return u
        u = self._img_from_sources(self._dig(v, ("contentImage", "thumbnailViewModel", "image", "sources")))
        if u:
            return u
        u = self._img_from_sources(self._dig(v, ("contentImage", "collectionThumbnailViewModel",
                                                 "primaryThumbnail", "thumbnailViewModel",
                                                 "image", "sources")))
        return u

    def _from_video(self, v):
        vid = v.get("videoId") or ""
        if not vid:
            return None
        length = self._tx(v.get("lengthText"))
        views = self._tx(v.get("shortViewCountText")) or self._tx(v.get("viewCountText"))
        pub = self._tx(v.get("publishedTimeText"))
        author = (self._tx(v.get("ownerText")) or self._tx(v.get("longBylineText"))
                  or self._tx(v.get("shortBylineText")) or self._tx(v.get("channelName")))
        remarks = length or pub or views
        return {
            "vod_id": "v:" + vid,
            "vod_name": self._tx(v.get("title")) or "视频",
            "vod_pic": self._thumb(v),
            "vod_remarks": remarks,
            "vod_content": author,
        }

    def _from_lockup(self, v):
        cid = v.get("contentId") or ""
        if not cid:
            return None
        ctype = str(v.get("contentType") or "")
        title = ""
        md = self._dig(v, ("metadata", "lockupMetadataViewModel", "title"))
        if isinstance(md, dict):
            title = md.get("content") or self._tx(md)
        if not title:
            title = self._tx(self._dig(v, ("metadata", "lockupMetadataViewModel", "title")))
        badge = ""
        rows = self._dig(v, ("metadata", "lockupMetadataViewModel", "metadata",
                             "contentMetadataViewModel", "metadataRows"))
        if isinstance(rows, list):
            parts = []
            for row in rows:
                for p in (row.get("metadataParts") or []):
                    t = self._dig(p, ("text", "content")) or self._tx(p.get("text"))
                    if t:
                        parts.append(str(t))
            badge = " · ".join(parts[:2])
        is_playlist = ("PLAYLIST" in ctype or "ALBUM" in ctype
                       or cid[:2] in ("PL", "RD", "OL", "VL", "MP"))
        return {
            "vod_id": ("p:" if is_playlist else "v:") + cid,
            "vod_name": title or "内容",
            "vod_pic": self._thumb(v),
            "vod_remarks": badge,
            "vod_content": "",
        }

    def _collect(self, node, items, cont):
        """递归收集卡片与 continuation token。"""
        if isinstance(node, dict):
            for k in list(node.keys()):
                val = node[k]
                if k in _VIDEO_RK:
                    if k in ("gridPlaylistRenderer",):
                        continue
                    it = self._from_video(val)
                    if it and val.get("videoId"):
                        items.append(it)
                elif k in _LOCKUP_RK:
                    it = self._from_lockup(val)
                    if it:
                        items.append(it)
                elif k == "continuationItemRenderer":
                    tok = self._dig(val, ("continuationEndpoint", "continuationCommand", "token"))
                    if not tok:
                        tok = self._dig(val, ("button", "buttonRenderer", "command",
                                              "continuationCommand", "token"))
                    if tok:
                        cont.append(tok)
                else:
                    self._collect(val, items, cont)
        elif isinstance(node, list):
            for x in node:
                self._collect(x, items, cont)

    def _parse(self, resp):
        items, cont = [], []
        if isinstance(resp, dict):
            self._collect(resp, items, cont)
        return items, (cont[0] if cont else "")

    # ------------------------------------------------------------------ 分页
    def _browse(self, browse_id, params="", continuation=""):
        body = {"browseId": browse_id}
        if params:
            body["params"] = params
        if continuation:
            body["continuation"] = continuation
        resp = self._innertube("browse", body)
        return self._parse(resp)

    def _chain_token(self, key, pg, fetch):
        """按 continuation 链顺序回填并缓存，返回第 pg 页所需 token（pg<2 返回空）。

        fetch(prev_token) -> (items, tok)。
        """
        if pg < 2:
            return ""
        toks = _ST["chain"].setdefault(key, [])
        guard = 0
        while len(toks) < pg - 1 and guard < 80:
            prev = toks[-1] if toks else ""
            _items, tok = fetch(prev)
            if not tok:
                break
            toks.append(tok)
            guard += 1
        return toks[pg - 2] if len(toks) >= pg - 1 else ""

    def _search_req(self, query="", cont=""):
        """search 端点：首屏用 query，翻页用 continuation，每页约 20 条。"""
        body = {"continuation": cont} if cont else {"query": query}
        resp = self._innertube("search", body, timeout=20)
        return self._parse(resp)

    # ------------------------------------------------------------------ 六接口
    def homeContent(self, filter=False):
        return {"class": [{"type_id": bid, "type_name": name} for bid, name in MODULES],
                "filters": {}, "list": []}

    def homeVideoContent(self):
        """首页：取 YouTube 网页首页推荐流（10 分钟缓存）。"""
        now = time.time()
        if _ST["home"] and now - _ST["home_at"] < 600:
            return {"list": _ST["home"]}
        items = []
        try:
            resp = self._innertube("browse", {"browseId": "FEwhat_to_watch"},
                                   timeout=20, ctx=VR_CTX)
            items, _tok = self._parse(resp)
        except Exception:
            items = []
        if items:
            _ST["home"] = items
            _ST["home_at"] = now
        return {"list": items}

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        try:
            page = max(int(str(pg)), 1)
        except Exception:
            page = 1
        bid = str(tid or "").strip()
        if bid not in MODULE_NAME:
            for k, v in MODULE_NAME.items():
                if v == bid:
                    bid = k
                    break
        # 全部走 search 关键词：模块页无 continuation 翻不了页
        query = CATEGORY_QUERY.get(bid) or MODULE_NAME.get(bid, "")
        if not query:
            return {"page": page, "pagecount": page, "limit": 0, "total": 0, "list": []}
        # 直播第 1 页取官方 livetab（其 continuation 为空），第 2 页起用关键词续接
        if bid == LIVE_ID and page == 1:
            try:
                items, _tok = self._browse(bid, LIVE_TAB_PARAMS)
            except Exception:
                items = []
            if items:
                return {"page": 1, "pagecount": 2, "limit": len(items),
                        "total": 0, "list": items}
        skey = "Q|" + bid
        cont = self._chain_token(skey, page, lambda prev: self._search_req(query, prev))
        items, _tok = self._search_req(query, cont)
        return {
            "page": page,
            "pagecount": page + 1,
            "limit": len(items),
            "total": 0,
            "list": items,
        }

    def _playlist_items(self, pid):
        for bid in ("VL" + pid, pid):
            items, _tok = self._browse(bid)
            if items:
                return items
        return []

    def detailContent(self, ids):
        vid = ""
        if isinstance(ids, list) and ids:
            vid = str(ids[0])
        elif ids:
            vid = str(ids)
        if not vid:
            return {"list": []}
        if vid.startswith("p:"):
            pid = vid[2:]
            items = self._playlist_items(pid)
            if not items:
                return {"list": []}
            eps = [(it.get("vod_name") or "视频", str(it.get("vod_id"))[2:])
                   for it in items if str(it.get("vod_id", "")).startswith("v:")]
            if not eps:
                return {"list": []}
            return {"list": [{
                "vod_id": vid,
                "vod_name": items[0].get("vod_name", "播放列表"),
                "vod_pic": items[0].get("vod_pic", ""),
                "vod_remarks": "共%d集" % len(eps),
                "vod_content": "",
                "vod_play_from": "自动",
                "vod_play_url": "#".join("%s$%s" % (n, i) for n, i in eps),
            }]}
        v = vid[2:] if vid.startswith("v:") else vid
        name, pic, desc, author = "", "", "", ""
        try:
            resp = self._innertube("player", {
                "videoId": v,
                "contentCheckOk": True,
                "racyCheckOk": True,
            })
            vd = resp.get("videoDetails") or {}
            _ST["live"][v] = bool(vd.get("isLive") or vd.get("isLiveNow"))
            name = vd.get("title") or ""
            author = vd.get("author") or ""
            desc = (vd.get("shortDescription") or "")[:400]
            t = self._dig(vd, ("thumbnail", "thumbnails"))
            if isinstance(t, list) and t:
                pic = t[-1].get("url", "")
        except Exception:
            pass
        if not pic:
            pic = "https://i.ytimg.com/vi/%s/hqdefault.jpg" % v
        if not name:
            name = "YouTube 视频"
        return {"list": [{
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_actor": author,
            "vod_content": desc,
            "vod_remarks": author,
            "vod_play_from": "自动",
            "vod_play_url": "正片$" + v,
        }]}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(int(str(pg)), 1)
        except Exception:
            page = 1
        kw = str(key or "").strip()
        if not kw:
            return {"list": []}
        ckey = "S|" + kw
        cont = self._chain_token(ckey, page, lambda prev: self._search_req(kw, prev))
        items, _tok = self._search_req(kw, cont)
        return {"list": items}

    # ------------------------------------------------------------------ 播放
    def _probe_first(self, kind, seeds, maker, deadline=0.0):
        cached = _ST.get(kind) or ""
        order = ([cached] if cached else []) + [s for s in seeds if s != cached]
        for base in order:
            if deadline and time.time() > deadline:
                break                                   # 超出总预算，放弃剩余候选
            try:
                url = maker(base)
                if url:
                    _ST[kind] = base
                    return url
            except Exception:
                continue
        return ""

    def _iv_stream(self, vid, deadline=0.0, live=False):
        def maker(base):
            r = self._req(base.rstrip("/") + "/api/v1/videos/" + vid, timeout=4)
            j = r.json()
            h = j.get("hlsUrl")
            if h and (live or j.get("liveNow")):
                return h                     # 直播只能走 HLS，单条直链只是某一时刻的分片快照
            for s in (j.get("formatStreams") or []):
                if isinstance(s, dict) and s.get("url"):
                    return s["url"]
            return h or ""
        return self._probe_first("iv", INVIDIOUS_SEED, maker, deadline)

    # ------------------------------------------------------ 高清晰度（ANDROID_VR + DASH 合成）
    def _vr_player(self, vid, timeout=15):
        """ANDROID_VR 客户端请求 player 接口（返回明文流地址，无需 signature 解密）。"""
        return self._innertube("player", {
            "videoId": vid, "contentCheckOk": True, "racyCheckOk": True,
        }, timeout=timeout, ctx=VR_CTX)

    def _vr_info(self, vid, timeout=10):
        """ANDROID_VR 取轨道。AV1 与 H.264 各留一档：avc1 最高 1080p，1440P/2160P 仅存在于 AV1。

        同 (分辨率, 编码族) 取码率最高的；同分辨率 avc1 在前。被判定 bot 时返回 None。
        """
        resp = self._vr_player(vid, timeout) or {}
        vd = resp.get("videoDetails") or {}
        sd = resp.get("streamingData") or {}
        fmts = sd.get("adaptiveFormats") or []
        if not fmts:
            return None
        best = {}
        for f in fmts:
            mt = str(f.get("mimeType") or "")
            if not mt.startswith("video/mp4") or not f.get("url"):
                continue
            try:
                h = int(f.get("height") or 0)
            except Exception:
                h = 0
            if h <= 0:
                continue
            k = (h, "av01" if "av01" in mt else "avc1")
            if k not in best or int(f.get("bitrate") or 0) > int(best[k].get("bitrate") or 0):
                best[k] = f
        if not best:
            return None
        tracks = sorted(best.values(),
                        key=lambda x: (-int(x.get("height") or 0),
                                       1 if "av01" in str(x.get("mimeType") or "") else 0))
        audio = None
        for f in fmts:
            if str(f.get("mimeType") or "").startswith("audio/mp4") and f.get("url"):
                if audio is None or int(f.get("bitrate") or 0) > int(audio.get("bitrate") or 0):
                    audio = f
        lb = (((resp.get("microformat") or {}).get("playerMicroformatRenderer") or {})
              .get("liveBroadcastDetails") or {})
        return {
            "tracks": tracks, "audio": audio,
            "duration": int(vd.get("lengthSeconds") or 0),
            "live": bool(vd.get("isLive") or vd.get("isLiveNow") or lb.get("isLiveNow")
                         or (sd.get("hlsManifestUrl") and vd.get("isLiveContent"))),
            "hls": str(sd.get("hlsManifestUrl") or ""),
        }

    def _iv_info(self, vid, timeout=10):
        """用 Invidious 取轨道，作为 VR 被风控时的画质来源。

        只认 adaptiveFormats——formatStreams 是混流，封顶 360p/720p。不可带 local=true
        （那条 /videoplayback 路径挂在反爬后面）；非 local 直链不校验请求方 IP，由本地代理拉分片。
        """
        cached = _ST.get("iv") or ""
        order = ([cached] if cached else []) + [s for s in INVIDIOUS_SEED if s != cached]
        t0 = time.time()
        for base in order:
            if time.time() > t0 + timeout:
                break                                   # 总预算到点，不再换实例
            try:
                r = self._req(base.rstrip("/") + "/api/v1/videos/" + vid, timeout=5)
                j = r.json()
            except Exception:
                continue
            fmts = j.get("adaptiveFormats") or []
            best = {}
            for f in fmts:
                if not isinstance(f, dict):
                    continue
                mt = str(f.get("type") or "")
                if not mt.startswith("video/mp4") or not f.get("url"):
                    continue
                if not _rngdict(f.get("init")) or not _rngdict(f.get("index")):
                    continue                            # 缺 Range 拼不出 SegmentBase
                h = _num(f.get("resolution"))
                if h <= 0:
                    continue
                k = (h, "av01" if "av01" in mt else "avc1")
                if k not in best or int(f.get("bitrate") or 0) > int(best[k].get("bitrate") or 0):
                    best[k] = f
            if not best:
                continue
            tracks = [_to_track(best[k]) for k in
                      sorted(best, key=lambda x: (-x[0], 1 if x[1] == "av01" else 0))]
            audio = None
            for f in fmts:
                if not isinstance(f, dict) or not f.get("url"):
                    continue
                if not str(f.get("type") or "").startswith("audio/mp4"):
                    continue
                if not _rngdict(f.get("init")) or not _rngdict(f.get("index")):
                    continue
                if audio is None or int(f.get("bitrate") or 0) > int(audio.get("bitrate") or 0):
                    audio = f
            _ST["iv"] = base
            return {
                "tracks": tracks, "audio": _to_track(audio) if audio else None,
                "duration": int(j.get("lengthSeconds") or 0),
                "live": bool(j.get("liveNow")), "hls": str(j.get("hlsUrl") or ""),
            }
        return None

    def _media_info(self, vid, timeout=10):
        """解析该视频可用轨道，30 分钟缓存。先试 ANDROID_VR，被风控则改走 Invidious。"""
        now = time.time()
        d = _ST["media"].get(vid)
        if d and d.get("expires", 0) > now:
            return d
        info = None
        if now - float(_ST.get("na_at") or 0) >= 300:   # 5 分钟内刚被风控过，跳过 VR 直接问 Invidious
            info = self._vr_info(vid, timeout)
            if not info:
                _ST["na_at"] = now
        if not info:
            info = self._iv_info(vid, timeout)
        if not info or not info.get("tracks"):
            return None
        info["expires"] = now + 1800
        _ST["media"][vid] = info
        return info

    def _pick_track(self, info, want_h=0, want_itag=0):
        """按 itag 精确选轨；未命中则取不高于 want_h 的最高一档（0 为最高档）。"""
        tracks = (info or {}).get("tracks") or []
        if not tracks:
            return None
        if want_itag:
            for f in tracks:
                if int(f.get("itag") or 0) == want_itag:
                    return f
        if want_h:
            for f in tracks:                      # tracks 已按高度降序、同高 avc1 在前
                if int(f.get("height") or 0) <= want_h:
                    return f
            # 期望低于所有可用轨：退回最低一档
            return min(tracks, key=lambda x: (
                int(x.get("height") or 0),
                1 if "av01" in str(x.get("mimeType") or "") else 0))
        return tracks[0]

    def _media_for(self, vid):
        """取轨道缓存，过期则重新解析（延迟解析可规避 URL 过期）。"""
        d = _ST["media"].get(vid)
        if d and d.get("expires", 0) > time.time():
            return d
        try:
            return self._media_info(vid)
        except Exception:
            return d

    def _proxy_mpd(self, p):
        """合成 DASH 清单（视频轨 + 音频轨），默认取最高画质，可按 itag/q 指定。

        只放一条视频 Representation——多轨时 ExoPlayer 自适应会退回低清。
        分片默认由播放器直连（seg=direct）；seg=proxy 时才改指 type=media 经本脚本转发。
        """
        vid = str(p.get("vid") or "")
        data = self._media_for(vid)
        if not data or not data.get("tracks"):
            return [404, "text/plain", b""]
        try:
            want_h = int(p.get("q") or 0)
            want_it = int(p.get("itag") or 0)
        except Exception:
            want_h, want_it = 0, 0
        f = self._pick_track(data, want_h, want_it)
        if not f:
            return [404, "text/plain", b""]
        direct = _ST.get("seg") == "direct"
        base = ("http://127.0.0.1:9978/proxy?do=py&type=media&vid=%s&itag=%s&q=%s"
                % (vid, int(f.get("itag") or 0), int(f.get("height") or 0)))

        def rng(x):
            r = x or {}
            return "%s-%s" % (r.get("start", "0"), r.get("end", "0"))

        def codecs(f):
            mt = str(f.get("mimeType") or "")
            return mt.split('codecs="')[-1].strip('"') if 'codecs="' in mt else ""

        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" '
               'mediaPresentationDuration="PT%dS" minBufferTime="PT1.5S" '
               'profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">'
               % int(data.get("duration") or 0),
               '<Period id="1" start="PT0S">']
        u = f.get("url") if direct else (base + "&track=video")
        out.append('<AdaptationSet mimeType="%s" startWithSAP="1" segmentAlignment="true">'
                   % str(f.get("mimeType") or "video/mp4").split(";")[0])
        out.append('<Representation id="v%s" bandwidth="%s" codecs="%s" width="%s" height="%s">'
                   % (f.get("itag"), f.get("bitrate") or 1000000, _xml(codecs(f)),
                      f.get("width") or 0, f.get("height") or 0))
        out.append('<BaseURL>%s</BaseURL>' % _xml(u or ""))
        out.append('<SegmentBase indexRange="%s"><Initialization range="%s"/></SegmentBase>'
                   % (rng(f.get("indexRange")), rng(f.get("initRange"))))
        out.append('</Representation></AdaptationSet>')
        a = data.get("audio")
        if a and a.get("url"):
            u = a.get("url") if direct else (base + "&track=audio")
            out.append('<AdaptationSet mimeType="%s" startWithSAP="1" segmentAlignment="true" lang="und">'
                       % str(a.get("mimeType") or "audio/mp4").split(";")[0])
            out.append('<Representation id="audio" bandwidth="%s" codecs="%s" audioSamplingRate="44100">'
                       % (a.get("bitrate") or 128000, _xml(codecs(a))))
            out.append('<BaseURL>%s</BaseURL>' % _xml(u or ""))
            out.append('<SegmentBase indexRange="%s"><Initialization range="%s"/></SegmentBase>'
                       % (rng(a.get("indexRange")), rng(a.get("initRange"))))
            out.append('</Representation></AdaptationSet>')
        out.append('</Period></MPD>')
        return [200, "application/dash+xml", "".join(out)]

    def _proxy_media(self, p):
        """代理媒体分片（透传 Range），保证出口 IP 与取流请求一致。"""
        vid = str(p.get("vid") or "")
        data = self._media_for(vid)
        if not data:
            return [404, "text/plain", b""]
        track = p.get("track")
        if track == "video":
            try:
                want_h = int(p.get("q") or 0)
                want_it = int(p.get("itag") or 0)
            except Exception:
                want_h, want_it = 0, 0
            f = self._pick_track(data, want_h, want_it)
        elif track == "audio":
            f = data.get("audio")
        else:
            f = None
        if not f or not f.get("url"):
            return [404, "text/plain", b""]
        rv = str(p.get("range") or p.get("Range") or "").strip()
        if not rv:
            # 正常分片必带 Range；缺失时兜底只取前 1MB，避免把整档（4K 可达数百 MB）拉进内存
            rv = "bytes=0-1048575"
        r = None
        for attempt in (0, 1):
            try:
                r = self._media_get(f["url"], rv)
            except Exception:
                return [500, "text/plain", b""]
            if r.status_code != 403:
                break
            # 403＝直链已失效（签名含 ip，出口变化即作废）。换实例重取一次；
            # 同一 vid 20 秒内只重取一次，否则每个分片都触发会拖垮播放
            if attempt or time.time() - float(_ST["r403"].get(vid) or 0) < 20:
                break
            _ST["r403"][vid] = time.time()
            print("[yt] 分片 403，重取直链 track=%s range=%s" % (track, rv),
                  file=sys.stderr, flush=True)
            _ST["media"].pop(vid, None)
            _ST["iv"] = ""
            try:
                nd = self._media_info(vid, 8)
            except Exception:
                nd = None
            f2 = None
            if nd:
                if track == "video":
                    f2 = self._pick_track(nd, want_h, want_it)
                elif track == "audio":
                    f2 = nd.get("audio")
            if not f2 or not f2.get("url"):
                break
            f = f2
        body = r.content or b""
        ct = r.headers.get("Content-Type") or "application/octet-stream"
        # Content-Length 按实际返回字节数写，避免与上游不一致导致播放器等不到数据而卡死
        h = {"Accept-Ranges": "bytes", "Cache-Control": "no-cache",
             "Content-Length": str(len(body))}
        if r.headers.get("Content-Range"):
            h["Content-Range"] = r.headers["Content-Range"]
        if r.status_code != 206 or str(r.headers.get("Content-Length") or "") != str(len(body)):
            print("[yt] 分片异常 track=%s range=%s code=%s 上游CL=%s 实长=%d"
                  % (track, rv, r.status_code, r.headers.get("Content-Length"), len(body)),
                  file=sys.stderr, flush=True)
        # 上游拒绝时如实回传状态码：回 206 空包会被播放器当成「读到 0 字节」，分片永远推进不下去
        return [r.status_code, ct, body, h]

    def playerContent(self, flag, id, vipFlags=None):
        vid = str(id or "").strip()
        want_it, want_h = 0, 0
        if "|" in vid:
            vid, _, qs = vid.partition("|")
            want_it, want_h = _qual_of(qs)
        if not want_h:
            want_h = _num(flag)                # 兼容只按线路名传清晰度的播放器
        if vid.startswith("v:"):
            vid = vid[2:]
        if not vid:
            return {"parse": 1, "playUrl": "", "url": "", "header": {}}
        header = {"User-Agent": UA, "Referer": HOST + "/"}
        lv = _ST["live"].get(vid)              # 详情页记下的直播标记，没记过才解析轨道
        info = None
        # 1) 可选：本地合成 DASH，自动取最高画质轨。默认关——直链不带本机出口 IP 的 token，
        #    YouTube 只放行前 60 秒，之后音频分片全 403
        if _ST.get("dash") or lv is None:
            try:
                info = self._media_info(vid)
            except Exception:
                info = None
            if lv is None:
                lv = bool((info or {}).get("live"))
            if _ST.get("dash") and info and not lv:
                q = "&itag=%d&q=%d" % (want_it, want_h)
                return {"parse": 0, "playUrl": "", "format": "application/dash+xml",
                        "url": "http://127.0.0.1:9978/proxy?do=py&type=mpd&vid=%s%s" % (vid, q),
                        "header": header}
        live = bool(lv)
        # 2) 直播只能走 HLS：分片靠递增序号，固定 indexRange 的静态 MPD 播几秒即断
        if live:
            u = str((info or {}).get("hls") or "")
            if not u and time.time() - float(_ST.get("pdead_at") or 0) > 300:
                try:
                    u = self._iv_stream(vid, time.time() + 6, live=True)
                except Exception:
                    u = ""
                if not u:
                    _ST["pdead_at"] = time.time()
            if u:
                return {"parse": 0, "playUrl": "", "url": u, "header": header}
        # 3) 点播默认：官方内嵌播放页，官方播放器自带有效 token，不会被 60 秒截断
        vq = _vq(want_h)
        embed = "%s/embed/%s?autoplay=1&playsinline=1&rel=0&vq=%s" % (HOST, vid, vq)
        return {"parse": 2, "playUrl": "", "url": embed, "header": header}
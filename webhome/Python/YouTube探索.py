# -*- coding: utf-8 -*-
# YouTube「探索」源 —— TVBox / hipy / 影视仓 T4 py 源
#
# 分类：YouTube 探索栏各模块（音乐 影视 粉丝热搜 直播 游戏 新闻 体育 课程 播客）
# 筛选：各模块页面上的真实子标签（运行时从 tabRenderer 探测，带内存缓存）
# 列表 / 搜索 / 详情：InnerTube Web 客户端接口（无需 API Key 注册、无需登录）
# 播放：分层解析器 Invidious -> Piped -> cobalt，全部失败时兜底 webview 内嵌（parse=2）
#
# 说明（重要）：2026 年公共解析器大面积失效（Invidious 仅剩极少数且多为 DASH 分离流、
# Piped 公共实例基本 403/502、cobalt 需 JWT）。因此播放优先按解析器链取混流直链，
# 取不到时回落到内嵌播放页；部署时可在此处补充可用实例或解析器。

import sys
import json
import time
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

# 探索模块：browseId -> 中文名（顺序与官网探索栏一致）
MODULES = [
    ("UC-9-kyTW8ZkZNDHQJ6FgpwQ", "音乐"),
    ("FEstorefront", "影视"),
    ("FEhype_leaderboard", "粉丝热搜"),
    ("UC4R8DWoMoI7CAwX8_LjQHig", "直播"),
    ("UCOpNcN46UbXVtpKMrmU4Abg", "游戏"),
    ("UCYfdidRxbB8Qhf0Nx7ioOYw", "新闻"),
    ("UCEgdi0XIXXZ-qJOFPf4JSKw", "体育"),
    ("FEcourses_destination", "课程"),
    ("FEpodcasts_destination", "播客"),
]
MODULE_NAME = dict(MODULES)

# 解析器候选（部署可替换/增补）
INVIDIOUS_SEED = [
    "https://invidious.f5.si",
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://yewtu.be",
    "https://iv.melmac.space",
]
PIPED_SEED = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://api.piped.yt",
]
COBALT_SEED = [
    "https://api.cobalt.tools",
    "https://cobalt-api.kwieme.de",
]

# 卡片渲染器：video 类
_VIDEO_RK = ("videoRenderer", "compactVideoRenderer", "gridVideoRenderer",
             "playlistVideoRenderer", "gridPlaylistRenderer")
# 卡片渲染器：新版统一卡片
_LOCKUP_RK = ("lockupViewModel",)

_SES = requests.Session()
_LK = threading.RLock()
_ST = {
    "cv": DEFAULT_CV, "cv_at": 0.0,        # 动态 clientVersion
    "proxy": None,                          # 代理（extend 配置）
    "cobalt_token": "",                     # cobalt JWT（extend 配置，可选）
    "tabs": {}, "tabs_at": 0.0,             # 模块 -> 真实标签（筛选）
    "chain": {},                            # 分页 continuation 链缓存
    "iv": "", "pp": "", "cob": "",          # 已探活的解析器实例
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
            if cfg.get("cobalt_token"):
                _ST["cobalt_token"] = str(cfg["cobalt_token"]).strip()
        elif s.startswith("http"):
            _ST["proxy"] = s

    # ------------------------------------------------------------------ 网络层
    def _req(self, url, method="GET", headers=None, data=None, timeout=15):
        h = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
        if headers:
            h.update(headers)
        proxies = None
        if _ST["proxy"]:
            proxies = {"http": _ST["proxy"], "https": _ST["proxy"]}
        with _LK:
            if method == "POST":
                return _SES.post(url, headers=h, data=data, timeout=timeout,
                                 proxies=proxies)
            return _SES.get(url, headers=h, timeout=timeout, proxies=proxies)

    def _ensure_client(self, force=False):
        """从首页提取真实 INNERTUBE_CLIENT_VERSION，避免写死版本号过期（6 小时缓存）。"""
        now = time.time()
        if not force and _ST["cv_at"] and now - _ST["cv_at"] < 21600:
            return _ST["cv"]
        try:
            r = self._req(HOST + "/", timeout=12)
            t = r.text or ""
            import re as _re
            m = _re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', t)
            if m:
                _ST["cv"] = m.group(1)
            m2 = _re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', t)
            if m2:
                _ST["key"] = m2.group(1)
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

    def _innertube(self, endpoint, body, timeout=15):
        key = _ST.get("key") or API_KEY
        url = "%s/youtubei/v1/%s?key=%s&prettyPrint=false" % (HOST, endpoint, key)
        headers = {
            "Content-Type": "application/json",
            "Origin": HOST,
            "Referer": HOST + "/",
            "X-Goog-Api-Format-Version": "3",
        }
        payload = {"context": self._ctx()}
        if isinstance(body, dict):
            payload.update(body)
        try:
            r = self._req(url, method="POST", headers=headers,
                          data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          timeout=timeout)
            if r.status_code != 200 and _ST.get("cv_at") and time.time() - _ST["cv_at"] > 3600:
                self._ensure_client(force=True)
            return r.json()
        except Exception:
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

    def _token_for_page(self, bid, params, key, pg):
        """获取第 pg 页所需的 continuation token（顺序回填并缓存）。"""
        if pg < 2:
            return ""
        toks = _ST["chain"].setdefault(key, [])
        guard = 0
        while len(toks) < pg - 1 and guard < 12:
            prev = toks[-1] if toks else ""
            _items, tok = self._browse(bid, params, prev)
            if not tok:
                break
            toks.append(tok)
            guard += 1
        return toks[pg - 2] if len(toks) >= pg - 1 else ""

    # ------------------------------------------------------------------ 筛选探测
    def _module_tabs(self, bid):
        """读取模块页面的真实子标签（tabRenderer），供筛选使用。"""
        try:
            resp = self._innertube("browse", {"browseId": bid})
        except Exception:
            return []
        found = []

        def walk(n):
            if isinstance(n, dict):
                if "tabRenderer" in n and isinstance(n["tabRenderer"], dict):
                    t = n["tabRenderer"]
                    name = self._tx(t.get("title"))
                    p = self._dig(t, ("endpoint", "browseEndpoint", "params"))
                    if name and p:
                        found.append({"n": name, "v": p})
                for k in n.keys():
                    if k != "tabRenderer":
                        walk(n[k])
            elif isinstance(n, list):
                for x in n:
                    walk(x)

        walk(resp)
        # 去重
        seen, out = set(), []
        for t in found:
            if t["v"] in seen:
                continue
            seen.add(t["v"])
            out.append(t)
        return out

    def _all_tabs(self):
        now = time.time()
        if _ST["tabs"] and now - _ST["tabs_at"] < 21600:
            return _ST["tabs"]
        tabs = {}
        lock = threading.Lock()

        def work(bid):
            r = self._module_tabs(bid)
            with lock:
                tabs[bid] = r

        ths = []
        for bid, _name in MODULES:
            t = threading.Thread(target=work, args=(bid,))
            t.daemon = True
            t.start()
            ths.append(t)
        for t in ths:
            t.join(timeout=12)
        if tabs:
            _ST["tabs"] = tabs
            _ST["tabs_at"] = now
        return tabs

    # ------------------------------------------------------------------ 六接口
    def homeContent(self, filter=False):
        cls = [{"type_id": bid, "type_name": name} for bid, name in MODULES]
        filters = {}
        try:
            tabs = self._all_tabs()
            for bid, _name in MODULES:
                opts = tabs.get(bid) or []
                if len(opts) > 1:
                    filters[bid] = [{"key": "tab", "name": "类型", "value": opts}]
        except Exception:
            filters = {}
        return {"class": cls, "filters": filters, "list": []}

    def homeVideoContent(self):
        try:
            items, _tok = self._browse("FEwhat_to_watch")
            return {"list": items}
        except Exception:
            return {"list": []}

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
        params = ""
        if isinstance(extend, dict):
            params = str(extend.get("tab") or "")
        elif isinstance(extend, str) and extend.strip().startswith("{"):
            try:
                params = str(json.loads(extend).get("tab") or "")
            except Exception:
                params = ""
        key = "%s|%s" % (bid, params)
        cont = self._token_for_page(bid, params, key, page)
        items, tok = self._browse(bid, params, cont)
        if page == 1 and tok:
            _ST["chain"].setdefault(key, [])
            if not _ST["chain"][key]:
                _ST["chain"][key] = [tok]
        return {
            "page": page,
            "pagecount": page + 1 if tok else page,
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
            eps = []
            for it in items:
                v = it.get("vod_id", "")
                if v.startswith("v:"):
                    eps.append("%s$%s" % (it.get("vod_name") or "视频", v[2:]))
            pic = items[0].get("vod_pic", "")
            return {"list": [{
                "vod_id": vid,
                "vod_name": items[0].get("vod_name", "播放列表"),
                "vod_pic": pic,
                "vod_remarks": "共%d集" % len(eps),
                "vod_content": "",
                "vod_play_from": "YouTube",
                "vod_play_url": "#".join(eps),
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
            "vod_play_from": "YouTube",
            "vod_play_url": "正片$%s" % v,
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
        cont = ""
        if page >= 2:
            cont = self._token_for_page("__search__", kw, ckey, page)
        body = {"query": kw}
        if cont:
            body["continuation"] = cont
        resp = self._innertube("search", body)
        items, tok = self._parse(resp)
        if page == 1 and tok:
            _ST["chain"][ckey] = [tok]
        return {"list": items}

    # ------------------------------------------------------------------ 播放
    def _probe_first(self, kind, seeds, maker):
        cached = _ST.get(kind) or ""
        order = ([cached] if cached else []) + [s for s in seeds if s != cached]
        for base in order:
            try:
                url = maker(base)
                if url:
                    _ST[kind] = base
                    return url
            except Exception:
                continue
        return ""

    def _iv_stream(self, vid):
        def maker(base):
            r = self._req(base.rstrip("/") + "/api/v1/videos/" + vid, timeout=12)
            j = r.json()
            for s in (j.get("formatStreams") or []):
                if isinstance(s, dict) and s.get("url"):
                    return s["url"]
            h = j.get("hlsUrl")
            if h:
                return h
            return ""
        return self._probe_first("iv", INVIDIOUS_SEED, maker)

    def _pp_stream(self, vid):
        def maker(base):
            r = self._req(base.rstrip("/") + "/streams/" + vid, timeout=12)
            j = r.json()
            for s in (j.get("videoStreams") or []):
                if isinstance(s, dict) and not s.get("videoOnly") and s.get("url"):
                    return s["url"]
            h = j.get("hls")
            if h:
                return h
            return ""
        return self._probe_first("pp", PIPED_SEED, maker)

    def _cobalt_stream(self, vid):
        token = _ST.get("cobalt_token") or ""
        if not token:
            return ""
        body = json.dumps({"url": "https://www.youtube.com/watch?v=" + vid}).encode("utf-8")

        def maker(base):
            r = self._req(base.rstrip("/") + "/", method="POST",
                          headers={"Content-Type": "application/json",
                                   "Accept": "application/json",
                                   "Authorization": "Api-Key " + token},
                          data=body, timeout=15)
            j = r.json()
            return j.get("url") or ""
        return self._probe_first("cob", COBALT_SEED, maker)

    def playerContent(self, flag, id, vipFlags=None):
        vid = str(id or "").strip()
        if vid.startswith("v:"):
            vid = vid[2:]
        if not vid:
            return {"parse": 1, "playUrl": "", "url": "", "header": {}}
        header = {"User-Agent": UA, "Referer": HOST + "/"}
        for fn in (self._iv_stream, self._pp_stream, self._cobalt_stream):
            try:
                u = fn(vid)
            except Exception:
                u = ""
            if u:
                return {"parse": 0, "playUrl": "", "url": u, "header": header}
        # 兜底：内嵌播放页，交由壳的 webview 处理
        embed = "%s/embed/%s?autoplay=1&playsinline=1" % (HOST, vid)
        return {"parse": 2, "playUrl": "", "url": embed, "header": header}
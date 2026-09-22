# -*- coding: utf-8 -*-
# B影视 Spider —— WebHomeTV / OK影视 / 影视仓 / PickTV 兼容版
# v3.0.2：DASH直链仅保留4K+1080P视轨，剔除720P及以下低画质轨道
import copy
import html
import json
import re
import time
import hashlib
import base64
import uuid
import urllib.parse

try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False
    import urllib.request

SITE = "https://www.bilibili.com"
API = "https://api.bilibili.com"
UA = "WCNM"

_DEFAULT_COOKIE = (
    "SESSDATA=1446597f%2C1803701179%2Ca580e%2A81CjAws6bETS5cmCwXzYqvp-Q5wpCNBjRSN0rHt0qQmSwozT82SfYfyAxCDgD22Cck93kSVl9lODFRNFYyMGc0UTFCQzhvRy1IUVlBaEhJV3ZlSXhWWlcxSHFRZkdwTTRuQkNwSkt3UVhTTmIyeXJoQnFsbUI2dEhIV24zaFlvVC1iSmIwXzdTQXl3IIEC;"
)


def _sanitize_cookie(cookie_str):
    if not cookie_str:
        return ""
    clean = cookie_str.encode("ascii", "ignore").decode("ascii")
    for name in ["SESSDATA", "bili_jct", "DedeUserID", "bili_ticket", "buvid3", "buvid4"]:
        clean = clean.replace(";" + name, "; " + name)
    parts = []
    for item in clean.split(";"):
        item = item.strip()
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        v = v.strip().encode("ascii", "ignore").decode("ascii")
        if v:
            parts.append("{}={}".format(k.strip(), v))
    return "; ".join(parts)


class _Response:
    def __init__(self, text="", status=200, headers=None):
        self.text = text
        self.status_code = status
        self.headers = headers or {}

    def json(self):
        return json.loads(self.text)


class _Http:
    def __init__(self, cookie=""):
        self.session = requests.Session() if _HAS_REQUESTS else None
        self.cookie = _sanitize_cookie(cookie)
        if self.session and self.cookie:
            self._set_cookies(self.cookie)
        self._ensure_buvid()

    def _set_cookies(self, cookie_str):
        if not self.session:
            return
        self.session.cookies.clear()
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                self.session.cookies.set(k.strip(), v.strip(), domain=".bilibili.com")
                self.session.cookies.set(k.strip(), v.strip(), domain="api.bilibili.com")

    def update_cookie(self, cookie):
        self.cookie = _sanitize_cookie(cookie)
        if self.session:
            self._set_cookies(self.cookie)
        self._ensure_buvid()

    def _ensure_buvid(self):
        if "buvid3=" in self.cookie and "buvid4=" in self.cookie:
            return
        try:
            if _HAS_REQUESTS:
                r = self.session.get(API + "/x/frontend/finger/spi", headers={"User-Agent": UA, "Referer": SITE + "/"}, timeout=8, verify=False)
                if r.status_code == 200:
                    d = r.json().get("data", {})
                    b3, b4 = d.get("b_3", ""), d.get("b_4", "")
                    if b3: self.cookie += "; buvid3=" + b3
                    if b4: self.cookie += "; buvid4=" + b4
                    self._set_cookies(self.cookie)
                    return
        except Exception:
            pass
        if "buvid3=" not in self.cookie:
            self.cookie += "; buvid3=" + str(uuid.uuid4()).replace("-", "").upper() + "infoc"
        if "buvid4=" not in self.cookie:
            self.cookie += "; buvid4=" + str(uuid.uuid4()).replace("-", "").upper()
        self._set_cookies(self.cookie)

    def _refresh_buvid(self):
        try:
            if _HAS_REQUESTS:
                r = self.session.get(API + "/x/frontend/finger/spi", headers={"User-Agent": UA, "Referer": SITE + "/"}, timeout=8, verify=False)
                if r.status_code == 200:
                    d = r.json().get("data", {})
                    for name, val in [("bbuvid3", d.get("b_3", "")), ("buvid4", d.get("b_4", ""))]:
                        if val:
                            self.cookie = re.sub(name + r"=[^;]*", name + "=" + val, self.cookie)
                            if name + "=" not in self.cookie:
                                self.cookie += "; " + name + "=" + val
                    self._set_cookies(self.cookie)
        except Exception:
            pass

    def _headers(self, extra=None):
        h = {
            "User-Agent": UA,
            "Origin": SITE,
            "Referer": SITE + "/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }
        if self.cookie:
            safe = self.cookie.encode("ascii", "ignore").decode("ascii")
            if safe:
                h["Cookie"] = safe
        if extra:
            h.update(extra)
        return h

    def get(self, url, headers=None, timeout=18):
        h = self._headers(headers)
        if _HAS_REQUESTS:
            r = self.session.get(url, headers=h, timeout=timeout, verify=False)
            if r.status_code == 200 and "json" in r.headers.get("Content-Type", ""):
                try:
                    if r.json().get("code") in (-352, 352, -403):
                        self._refresh_buvid()
                        r = self.session.get(url, headers=self._headers(headers), timeout=timeout, verify=False)
                except Exception:
                    pass
            return r
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _Response(r.read().decode("utf-8", "replace"), r.status, dict(r.headers))

    def post(self, url, data=None, headers=None, timeout=18):
        h = self._headers(headers)
        if _HAS_REQUESTS:
            return self.session.post(url, json=data, headers=h, timeout=timeout, verify=False)
        raw = json.dumps(data or {}, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=raw, headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _Response(r.read().decode("utf-8", "replace"), r.status, dict(r.headers))


class Spider:
    name = "B影视"
    version = "3.0.2"
    host = API

    _QUALITY_MAP = [
        ("BHDR", [127, 126]),
        ("B4K", [120]),
        ("B1080P+", [116, 112]),
        ("B1080P", [80]),
        ("B720P", [64, 32]),
    ]

    _QUALITY_FLAG_MAP = {
        "BHDR": [127, 126],
        "B4K": [120],
        "B1080P+": [116, 112],
        "B1080P": [80],
        "B720P": [64, 32],
    }

    def __init__(self):
        self.extend = ""
        self.vmid = ""
        self.cookie = _DEFAULT_COOKIE
        self.http = _Http(self.cookie)
        self.s = self.http.session
        self.session = self.http.session
        self.sess = self.http.session

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.extend = json.dumps(extend, ensure_ascii=False)
        else:
            self.extend = extend if isinstance(extend, str) else ""
        self.vmid = ""
        if self.extend:
            try:
                ext = json.loads(self.extend) if isinstance(self.extend, str) else self.extend
                if isinstance(ext, dict):
                    self.vmid = str(ext.get("vmid", ""))
                    if ext.get("cookie"):
                        self.cookie = _sanitize_cookie(urllib.parse.unquote(str(ext.get("cookie"))))
            except Exception:
                if "vmid=" in self.extend:
                    self.vmid = self.extend.split("vmid=")[-1].split("&")[0].strip()
                if "cookie=" in self.extend:
                    raw = self.extend.split("cookie=")[-1].split("&")[0].strip()
                    self.cookie = urllib.parse.unquote(raw)
                elif not self.vmid:
                    self.vmid = self.extend.strip()
        self.http.update_cookie(self.cookie)
        self.s = self.http.session
        self.session = self.http.session
        self.sess = self.http.session

    def getDependence(self):
        return []

    def getName(self):
        return self.name

    def destroy(self):
        try:
            if self.http.session:
                self.http.session.close()
        except Exception:
            pass

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        u = str(url).lower()
        if u.startswith("data:") or "127.0.0.1" in u or "localhost" in u:
            return True
        return u.split("?", 1)[0].endswith((".m3u8", ".mp4", ".flv", ".ts", ".mkv", ".m4s"))

    def action(self, action):
        return json.dumps({"code": 0, "msg": "ok"}, ensure_ascii=False)

    def homeContent(self, filter=None):
        classes = [
            {"type_name": "番剧", "type_id": "1"},
            {"type_name": "国创", "type_id": "4"},
            {"type_name": "电影", "type_id": "2"},
            {"type_name": "电视剧", "type_id": "5"},
            {"type_name": "纪录片", "type_id": "3"},
            {"type_name": "综艺", "type_id": "7"},
            {"type_name": "全部", "type_id": "全部"},
            {"type_name": "时间表", "type_id": "时间表"},
        ]
        filters = {
            "全部": [
                {
                    "key": "tid",
                    "name": "分类",
                    "value": [
                        {"n": "番剧", "v": "1"},
                        {"n": "国创", "v": "4"},
                        {"n": "电影", "v": "2"},
                        {"n": "电视剧", "v": "5"},
                        {"n": "记录片", "v": "3"},
                        {"n": "综艺", "v": "7"},
                    ],
                },
                {
                    "key": "order",
                    "name": "排序",
                    "value": [
                        {"n": "播放数量", "v": "2"},
                        {"n": "更新时间", "v": "0"},
                        {"n": "最高评分", "v": "4"},
                        {"n": "弹幕数量", "v": "1"},
                        {"n": "追看人数", "v": "3"},
                        {"n": "开播时间", "v": "5"},
                        {"n": "上映时间", "v": "6"},
                    ],
                },
                {
                    "key": "season_status",
                    "name": "付费",
                    "value": [
                        {"n": "全部", "v": "-1"},
                        {"n": "免费", "v": "1"},
                        {"n": "付费", "v": "2%2C6"},
                        {"n": "大会员", "v": "4%2C6"},
                    ],
                },
            ],
            "时间表": [
                {
                    "key": "tid",
                    "name": "分类",
                    "value": [
                        {"n": "番剧", "v": "1"},
                        {"n": "国创", "v": "4"},
                    ],
                },
            ],
        }
        return {"class": classes, "filters": filters, "list": []}

    def homeVideoContent(self):
        try:
            videos = self._get_rank("1", 1)[:5]
            for i in ["4", "2", "5", "3", "7"]:
                videos.extend(self._get_rank2(i, 1)[:5])
            return {"list": self._dedupe(videos)}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        ext = extend if isinstance(extend, dict) else {}
        try:
            if tid == "1":
                videos = self._get_rank(tid, page)
                return {"list": videos, "page": page, "pagecount": 1, "limit": 20, "total": len(videos)}
            elif tid in ["2", "3", "4", "5", "7"]:
                videos = self._get_rank2(tid, page)
                return {"list": videos, "page": page, "pagecount": 1, "limit": 20, "total": len(videos)}
            elif tid == "全部":
                tid_val = ext.get("tid", "1")
                order = ext.get("order", "2")
                season_status = ext.get("season_status", "-1")
                videos = self._get_all(tid_val, page, order, season_status)
                return {"list": videos, "page": page, "pagecount": page + 1 if len(videos) >= 20 else page, "limit": 20, "total": 999999}
            elif tid == "时间表":
                tid_val = ext.get("tid", "1")
                videos = self._get_timeline(tid_val, page)
                return {"list": videos, "page": page, "pagecount": 1, "limit": 50, "total": len(videos)}
            else:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}
        except Exception:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) and ids else ids)
        if not vid:
            return {"list": []}
        try:
            jo = self.http.get(self.host + "/pgc/view/web/season?season_id=" + vid).json().get("result", {})
            id_val = jo.get("season_id", "")
            title = jo.get("title", "")
            pic = jo.get("cover", "")
            areas = jo["areas"][0].get("name", "") if jo.get("areas") else ""
            type_name = jo.get("share_sub_title", "")
            date = jo["publish"]["pub_time"][:4] if jo.get("publish", {}).get("pub_time") else ""
            dec = jo.get("evaluate", "")
            remark = jo.get("new_ep", {}).get("desc", "")
            stat = jo.get("stat", {})
            status = "弹幕: {}　点赞: {}　投币: {}　追番追剧: {}".format(
                self._zh(stat.get("danmakus", 0)), self._zh(stat.get("likes", 0)),
                self._zh(stat.get("coins", 0)), self._zh(stat.get("favorites", 0)),
            )
            score = "评分: {}　{}".format(jo["rating"].get("score", ""), jo.get("subtitle", "")) if jo.get("rating") else "暂无评分　{}".format(jo.get("subtitle", ""))
            vod = {
                "vod_id": id_val, "vod_name": title, "vod_pic": pic, "type_name": type_name,
                "vod_year": date, "vod_area": areas, "vod_remarks": remark,
                "vod_actor": status, "vod_director": score, "vod_content": dec,
            }

            episodes = jo.get("episodes", []) or []
            sections = jo.get("section", []) or jo.get("sections", []) or []
            if not episodes:
                positive_id = jo.get("positive", {}).get("id", "")
                if positive_id:
                    for sec in sections:
                        if str(sec.get("id", "")) == str(positive_id):
                            episodes = sec.get("episodes", []) or []
                            break
                if not episodes:
                    for sec in sections:
                        if sec.get("title", "") == "正片":
                            episodes = sec.get("episodes", []) or []
                            if episodes:
                                break
                if not episodes:
                    for sec in sections:
                        t = sec.get("title", "")
                        if "预告" not in t and "PV" not in t and "彩蛋" not in t:
                            eps = sec.get("episodes", []) or []
                            if eps:
                                episodes = eps
                                break
                if not episodes:
                    for sec in sections:
                        eps = sec.get("episodes", []) or []
                        if eps:
                            episodes = eps
                            break

            ja = []
            for ep in episodes:
                t = str(ep.get("title", ""))
                b = str(ep.get("badge", "") or "")
                if "预告" not in t and "预告" not in b and "PV" not in t:
                    ja.append(ep)

            playurls_base = []
            playurls_link = []
            for tmp in ja:
                eid = str(tmp.get("id", "") or "")
                cid = str(tmp.get("cid", "") or "")
                aid = str(tmp.get("aid", "") or "")
                bvid = str(tmp.get("bvid", "") or "")
                link = str(tmp.get("link", "") or "")
                if not bvid and link and "/BV" in link:
                    try:
                        bvid = "BV" + link.split("/BV")[-1].split("/")[0].split("?")[0].strip()
                    except Exception:
                        pass
                badge = str(tmp.get("badge", "") or "")
                part_name = str(tmp.get("title", "")).replace("#", "-").replace("$", "_").replace("$$$", "_")
                part_long = str(tmp.get("long_title", "")).replace("#", "-").replace("$", "_").replace("$$$", "_")
                part = "{} {}".format(part_name, part_long).strip()
                if badge:
                    part = "{}[{}]".format(part, badge)
                if cid:
                    playurls_base.append("{}${}_{}_{}_{}".format(part, aid or "0", cid, eid or "0", bvid or "0"))
                if link:
                    playurls_link.append("{}${}".format(part, link))

            sources = []
            froms = []
            base_str = "#".join(playurls_base) if playurls_base else ""
            for qname, qids in self._QUALITY_MAP:
                sources.append(base_str)
                froms.append(qname)
                if qname == "B4K" and base_str:
                    sources.append(base_str)
                    froms.append("DASH直链")
            if playurls_link:
                sources.append("#".join(playurls_link))
                froms.append("解析")

            play_url = "$$$".join(sources) if len(sources) > 1 else (sources[0] if sources else "")
            vod["vod_play_from"] = "$$$".join(froms) if len(froms) > 1 else (froms[0] if froms else "B4K")
            vod["vod_play_url"] = play_url
            return {"list": [vod]}
        except Exception:
            import traceback
            traceback.print_exc()
            return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        keys = self._get_wbi_keys()
        if not keys:
            return {"list": [], "page": page, "pagecount": page}
        v = []
        for search_type in ["media_bangumi", "media_ft"]:
            try:
                params = {
                    "keyword": key, "page": page, "page_size": 20,
                    "platform": "pc", "search_type": search_type, "web_location": 1430654,
                }
                query = self._enc_wbi(params, keys)
                url = self.host + "/x/web-interface/wbi/search/type?" + query
                jo = self.http.get(url).json()
                if jo.get("code") == 0 and jo.get("data", {}).get("result"):
                    for vod in jo["data"]["result"]:
                        title = re.sub(r"<[^>]+>", "", str(vod.get("title", ""))).strip()
                        if "预告" in title:
                            continue
                        aid = str(vod.get("season_id", "")).strip()
                        img = str(vod.get("cover", "")).strip()
                        if img.startswith("//"):
                            img = "https:" + img
                        remark = str(vod.get("index_show", "")).strip()
                        v.append({"vod_id": aid, "vod_name": title, "vod_pic": img, "vod_remarks": remark})
            except Exception:
                pass
        return {"list": self._dedupe(v), "page": page, "pagecount": page + 1 if len(v) >= 20 else page}

    def playerContent(self, flag, ids, vipFlags=None):
        if isinstance(ids, (list, tuple)) and ids:
            raw = str(ids[0])
        else:
            raw = str(ids)
        danmaku = ""

        if raw.startswith("http"):
            url = raw
            danmaku = "http://121.41.93.205/dm.php?url=" + urllib.parse.quote(url, safe="")
            return {"parse": 0, "url": url, "header": {"User-Agent": UA, "Referer": SITE + "/", "Cookie": self.cookie}, "jx": 1, "danmaku": danmaku}

        parts = raw.split("_")
        aid = cid = eid = bvid = ""
        if len(parts) >= 4:
            aid, cid, eid, bvid = parts[0], parts[1], parts[2], parts[3]
        elif len(parts) == 3:
            aid, cid, eid = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            eid, cid = parts[0], parts[1]

        if not cid:
            return {"parse": 0, "url": raw, "header": {"User-Agent": UA, "Referer": SITE + "/", "Cookie": self.cookie}, "jx": 1, "danmaku": danmaku}

        try:
            if bvid and bvid != "0":
                api_url = "{}/x/player/playurl?bvid={}&cid={}&qn=127&fnver=0&fnval=4048&fourk=1".format(API, bvid, cid)
            elif aid and aid != "0":
                api_url = "{}/x/player/playurl?avid={}&cid={}&qn=127&fnver=0&fnval=4048&fourk=1".format(API, aid, cid)
            elif eid and eid != "0":
                api_url = "{}/pgc/player/web/playurl?cid={}&qn=127&fnver=0&fnval=4048&fourk=1&ep_id={}".format(API, cid, eid)
            else:
                api_url = "{}/x/player/playurl?cid={}&qn=127&fnver=0&fnval=4048&fourk=1".format(API, cid)

            data = self.http.get(api_url, timeout=10).json()

            if data.get("code") == 0:
                result = data.get("result", {}) or data.get("data", {})
                dash = result.get("dash", {})
                videos = dash.get("video", [])
                audios = dash.get("audio", [])

                # ========== DASH直链：仅4K+1080P视轨 + 全音频 ==========
                if flag == "DASH直链" and videos and audios:
                    fixed_result = copy.deepcopy(result)
                    fixed_videos = fixed_result.get("dash", {}).get("video", [])
                    fixed_audios = fixed_result.get("dash", {}).get("audio", [])

                    # 全轨道mCDN修复
                    non_mcdn = [v for v in fixed_videos if not any("mcdn" in str(u) for u in ([v.get("baseUrl", "")] + (v.get("backupUrl", []) or [])))]
                    if non_mcdn:
                        fixed = self._fix_mcdn_urls(non_mcdn, fixed_videos, fixed_audios)
                        for i, v in enumerate(fixed_videos):
                            if v in non_mcdn:
                                for fv in fixed:
                                    if fv.get("id") == v.get("id") and fv.get("codecs") == v.get("codecs"):
                                        fixed_videos[i] = fv
                                        break

                    # 仅保留 4K(120) + 1080P(80)，彻底剔除720P及以下
                    videos_sorted = self._sort_video_tracks(fixed_videos)
                    video_4k = [v for v in videos_sorted if v.get("id") == 120]
                    video_1080 = [v for v in videos_sorted if v.get("id") == 80]
                    selected_videos = video_4k + video_1080

                    # 全部音频轨道
                    audios_sorted = sorted(fixed_audios, key=lambda x: x.get("id", 0), reverse=True)

                    if selected_videos and audios_sorted:
                        timelength = fixed_result.get("timelength", 0) or fixed_result.get("time_length", 0)
                        try:
                            duration_sec = max(1, int(int(timelength) / 1000))
                        except Exception:
                            duration_sec = 3600
                        dur_str = "PT{}S".format(duration_sec)

                        video_reprs = []
                        for v in selected_videos:
                            v_url = self._pick_url_for_mpd(v)
                            if not v_url:
                                continue
                            try:
                                from urllib.parse import urlparse, urlunparse
                                vp = urlparse(v_url)
                                mcdn_domain = None
                                for a in audios_sorted:
                                    au = self._pick_url_for_mpd(a, is_audio=True)
                                    if au and "mcdn" in au:
                                        mcdn_domain = urlparse(au).netloc
                                        break
                                if mcdn_domain and "mcdn" not in vp.netloc:
                                    v_url = urlunparse(vp._replace(netloc=mcdn_domain, path=vp.path))
                            except Exception:
                                pass
                            seg = v.get("SegmentBase", {}) or v.get("segment_base", {})
                            init = seg.get("Initialization", "") or seg.get("initialization", "")
                            idx = seg.get("indexRange", "") or seg.get("index_range", "")
                            seg_xml = ""
                            if init or idx:
                                seg_xml = '<SegmentBase indexRange="{}"><Initialization range="{}"/></SegmentBase>'.format(idx, init)
                            video_reprs.append(
                                '<Representation id="video_{}" bandwidth="{}" codecs="{}" width="{}" height="{}" frameRate="{}" sar="1:1"><BaseURL>{}</BaseURL>{}</Representation>'.format(
                                    v.get("id", ""), v.get("bandwidth", 0), v.get("codecs", "avc1.64001F"),
                                    v.get("width", 1920), v.get("height", 1080), v.get("frameRate", "30"),
                                    html.escape(v_url), seg_xml))

                        audio_reprs = []
                        for a in audios_sorted:
                            a_url = self._pick_url_for_mpd(a, is_audio=True)
                            if not a_url:
                                continue
                            seg = a.get("SegmentBase", {}) or a.get("segment_base", {})
                            init = seg.get("Initialization", "") or seg.get("initialization", "")
                            idx = seg.get("indexRange", "") or seg.get("index_range", "")
                            seg_xml = ""
                            if init or idx:
                                seg_xml = '<SegmentBase indexRange="{}"><Initialization range="{}"/></SegmentBase>'.format(idx, init)
                            audio_reprs.append(
                                '<Representation id="audio_{}" bandwidth="{}" codecs="{}"><BaseURL>{}</BaseURL>{}</Representation>'.format(
                                    a.get("id", ""), a.get("bandwidth", 128000), a.get("codecs", "mp4a.40.2"),
                                    html.escape(a_url), seg_xml))

                        if video_reprs and audio_reprs:
                            mpd = '<?xml version="1.0" encoding="UTF-8"?>'
                            mpd += '<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" minBufferTime="PT1.5S" type="static" mediaPresentationDuration="' + dur_str + '">'
                            mpd += '<Period start="PT0S" duration="' + dur_str + '">'
                            mpd += '<AdaptationSet mimeType="video/mp4" startWithSAP="1" subsegmentAlignment="true" scanType="progressive">'
                            for rep in video_reprs:
                                mpd += rep
                            mpd += '</AdaptationSet>'
                            mpd += '<AdaptationSet mimeType="audio/mp4" startWithSAP="1" subsegmentAlignment="true">'
                            for rep in audio_reprs:
                                mpd += rep
                            mpd += '</AdaptationSet>'
                            mpd += '</Period>'
                            mpd += '</MPD>'

                            mpd_b64 = base64.b64encode(mpd.encode("utf-8")).decode("ascii")
                            data_url = "data:application/dash+xml;base64," + mpd_b64
                            if len(data_url) < 65536:
                                danmaku = "http://121.41.93.205/dm.php?url=" + urllib.parse.quote(raw, safe="")
                                return {"parse": 0, "url": data_url, "header": {"User-Agent": UA, "Referer": SITE + "/", "Cookie": self.cookie}, "jx": 0, "danmaku": danmaku}

                        # MPD超长 fallback：最佳单轨道（仍只取4K/1080P中的最高）
                        best_video = selected_videos[0]
                        best_audio = audios_sorted[0]
                        v_url = self._pick_url_for_mpd(best_video)
                        a_url = self._pick_url_for_mpd(best_audio, is_audio=True)
                        if v_url and a_url:
                            try:
                                from urllib.parse import urlparse, urlunparse
                                vp = urlparse(v_url)
                                ap = urlparse(a_url)
                                if "mcdn" not in vp.netloc and "mcdn" in ap.netloc:
                                    v_url = urlunparse(vp._replace(netloc=ap.netloc, path=vp.path))
                            except Exception:
                                pass
                            danmaku = "http://121.41.93.205/dm.php?url=" + urllib.parse.quote(raw, safe="")
                            return {"parse": 0, "url": v_url + "#" + a_url, "header": {"User-Agent": UA, "Referer": SITE + "/", "Cookie": self.cookie}, "jx": 0, "danmaku": danmaku}

                # ========== 画质分组MPD ==========
                target_ids = self._QUALITY_FLAG_MAP.get(flag)
                if target_ids and videos and audios:
                    mpd = self._generate_mpd(result, target_ids=target_ids)
                    if mpd:
                        mpd_b64 = base64.b64encode(mpd.encode("utf-8")).decode("ascii")
                        danmaku = "http://121.41.93.205/dm.php?url=" + urllib.parse.quote(raw, safe="")
                        return {"parse": 0, "url": "data:application/dash+xml;base64," + mpd_b64, "header": {"User-Agent": UA, "Referer": SITE + "/", "Cookie": self.cookie}, "jx": 0, "danmaku": danmaku}
                    mpd_fb = self._generate_mpd(result, target_ids=None)
                    if mpd_fb:
                        mpd_b64 = base64.b64encode(mpd_fb.encode("utf-8")).decode("ascii")
                        danmaku = "http://121.41.93.205/dm.php?url=" + urllib.parse.quote(raw, safe="")
                        return {"parse": 0, "url": "data:application/dash+xml;base64," + mpd_b64, "header": {"User-Agent": UA, "Referer": SITE + "/", "Cookie": self.cookie}, "jx": 0, "danmaku": danmaku}
                    durl = result.get("durl", [])
                    if durl and durl[0].get("url"):
                        danmaku = "http://121.41.93.205/dm.php?url=" + urllib.parse.quote(raw, safe="")
                        return {"parse": 0, "url": durl[0]["url"], "header": {"User-Agent": UA, "Referer": SITE + "/", "Cookie": self.cookie}, "jx": 0, "danmaku": danmaku}

                elif flag == "解析":
                    url = SITE
                    if eid and eid != "0":
                        url = "https://www.bilibili.com/bangumi/play/ep" + eid
                    elif aid and aid != "0":
                        url = "https://www.bilibili.com/video/av" + aid
                    elif bvid and bvid != "0":
                        url = "https://www.bilibili.com/video/" + bvid
                    danmaku = "http://121.41.93.205/dm.php?url=" + urllib.parse.quote(url, safe="")
                    return {"parse": 0, "url": url, "header": {"User-Agent": UA, "Referer": SITE + "/", "Cookie": self.cookie}, "jx": 1, "danmaku": danmaku}

                else:
                    if videos and audios:
                        mpd = self._generate_mpd(result, target_ids=None)
                        if mpd:
                            mpd_b64 = base64.b64encode(mpd.encode("utf-8")).decode("ascii")
                            danmaku = "http://121.41.93.205/dm.php?url=" + urllib.parse.quote(raw, safe="")
                            return {"parse": 0, "url": "data:application/dash+xml;base64," + mpd_b64, "header": {"User-Agent": UA, "Referer": SITE + "/", "Cookie": self.cookie}, "jx": 0, "danmaku": danmaku}
                    durl = result.get("durl", [])
                    if durl and durl[0].get("url"):
                        danmaku = "http://121.41.93.205/dm.php?url=" + urllib.parse.quote(raw, safe="")
                        return {"parse": 0, "url": durl[0]["url"], "header": {"User-Agent": UA, "Referer": SITE + "/", "Cookie": self.cookie}, "jx": 0, "danmaku": danmaku}

        except Exception:
            pass

        url = SITE
        if eid and eid != "0":
            url = "https://www.bilibili.com/bangumi/play/ep" + eid
        elif aid and aid != "0":
            url = "https://www.bilibili.com/video/av" + aid
        elif bvid and bvid != "0":
            url = "https://www.bilibili.com/video/" + bvid
        danmaku = "http://121.41.93.205/dm.php?url=" + urllib.parse.quote(url, safe="")
        return {"parse": 0, "url": url, "header": {"User-Agent": UA, "Referer": SITE + "/", "Cookie": self.cookie}, "jx": 1, "danmaku": danmaku}

    @staticmethod
    def _fix_mcdn_urls(video_tracks, all_videos, all_audios):
        from urllib.parse import urlparse, urlunparse
        mcdn_domains = set()
        for t in all_videos + all_audios:
            for k in ["baseUrl", "base_url", "backupUrl", "backup_url"]:
                u = t.get(k, []) if isinstance(t.get(k), list) else [t.get(k, "")]
                for url in u:
                    if url and "mcdn" in url:
                        try:
                            mcdn_domains.add(urlparse(url).netloc)
                        except Exception:
                            pass
        if not mcdn_domains:
            return video_tracks
        domain = list(mcdn_domains)[0]
        fixed = []
        for track in video_tracks:
            nt = dict(track)
            for k in ["baseUrl", "base_url"]:
                u = nt.get(k, "")
                if u and "mcdn" not in urlparse(u).netloc:
                    try:
                        nt[k] = urlunparse(urlparse(u)._replace(netloc=domain))
                    except Exception:
                        pass
            bk = nt.get("backupUrl", []) or nt.get("backup_url", []) or []
            nb = []
            for b in bk:
                if b and "mcdn" not in urlparse(b).netloc:
                    try:
                        nb.append(urlunparse(urlparse(b)._replace(netloc=domain)))
                    except Exception:
                        nb.append(b)
                else:
                    nb.append(b)
            if nb:
                nt["backupUrl"] = nb
                nt["backup_url"] = nb
            fixed.append(nt)
        return fixed

    @staticmethod
    def _sort_video_tracks(videos):
        def _prio(v):
            c = str(v.get("codecs", "")).lower()
            if "hev" in c or "h265" in c or "hvc" in c:
                return 0
            if "avc" in c or "h264" in c:
                return 1
            if "av1" in c or "av01" in c:
                return 2
            return 3
        groups = {}
        for v in videos:
            vid = v.get("id", 0)
            groups.setdefault(vid, []).append(v)
        out = []
        for vid in sorted(groups.keys(), reverse=True):
            out.extend(sorted(groups[vid], key=_prio))
        return out

    def _generate_mpd(self, result, target_ids=None):
        dash = result.get("dash", {})
        videos = dash.get("video", [])
        audios = dash.get("audio", [])
        if not videos or not audios:
            return None
        timelength = result.get("timelength", 0) or result.get("time_length", 0)
        try:
            duration_sec = max(1, int(int(timelength) / 1000))
        except Exception:
            duration_sec = 3600
        dur_str = "PT{}S".format(duration_sec)
        all_videos = self._sort_video_tracks(videos)
        if target_ids:
            target_set = set(target_ids)
            filtered = [v for v in all_videos if v.get("id") in target_set]
            if filtered:
                video_list = filtered
            else:
                highest_id = all_videos[0].get("id", 0) if all_videos else 0
                video_list = [v for v in all_videos if v.get("id") == highest_id] or all_videos[:1]
        else:
            video_list = all_videos
        top_video = video_list[0] if video_list else {}
        video_reprs = []
        for v in video_list:
            url = self._pick_url_for_mpd(v)
            if not url:
                continue
            seg = v.get("SegmentBase", {}) or v.get("segment_base", {})
            init = seg.get("Initialization", "") or seg.get("initialization", "")
            idx = seg.get("indexRange", "") or seg.get("index_range", "")
            seg_base = '<SegmentBase indexRange="{}"><Initialization range="{}"/></SegmentBase>'.format(idx, init) if init or idx else ""
            video_reprs.append(
                '<Representation id="video_{}" bandwidth="{}" codecs="{}" width="{}" height="{}" frameRate="{}" sar="1:1"><BaseURL>{}</BaseURL>{}</Representation>'.format(
                    v.get("id", ""), v.get("bandwidth", 0), v.get("codecs", "avc1.64001F"),
                    v.get("width", 1920), v.get("height", 1080), v.get("frameRate", "30"),
                    html.escape(url), seg_base))
        sorted_audios = sorted(audios, key=lambda x: x.get("id", 0), reverse=True)
        top_audio = sorted_audios[0] if sorted_audios else {}
        audio_reprs = []
        for a in sorted_audios:
            url = self._pick_url_for_mpd(a, is_audio=True)
            if not url:
                continue
            seg = a.get("SegmentBase", {}) or a.get("segment_base", {})
            init = seg.get("Initialization", "") or seg.get("initialization", "")
            idx = seg.get("indexRange", "") or seg.get("index_range", "")
            seg_base = '<SegmentBase indexRange="{}"><Initialization range="{}"/></SegmentBase>'.format(idx, init) if init or idx else ""
            audio_reprs.append(
                '<Representation id="audio_{}" bandwidth="{}" codecs="{}"><BaseURL>{}</BaseURL>{}</Representation>'.format(
                    a.get("id", ""), a.get("bandwidth", 128000), a.get("codecs", "mp4a.40.2"),
                    html.escape(url), seg_base))
        if not video_reprs or not audio_reprs:
            return None
        mpd_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" minBufferTime="PT1.5S" type="static" mediaPresentationDuration="' + dur_str + '">',
            '  <Period start="PT0S" duration="' + dur_str + '">',
            '    <AdaptationSet mimeType="video/mp4" width="' + str(top_video.get("width", 1920)) + '" height="' + str(top_video.get("height", 1080)) + '" frameRate="' + str(top_video.get("frameRate", "30")) + '" startWithSAP="1" subsegmentAlignment="true" scanType="progressive">',
        ]
        for vr in video_reprs:
            mpd_lines.append('      ' + vr)
        mpd_lines.append('    </AdaptationSet>')
        mpd_lines.append('    <AdaptationSet mimeType="audio/mp4" startWithSAP="1" subsegmentAlignment="true">')
        for ar in audio_reprs:
            mpd_lines.append('      ' + ar)
        mpd_lines.append('    </AdaptationSet>')
        mpd_lines.append('  </Period>')
        mpd_lines.append('</MPD>')
        return chr(10).join(mpd_lines)

    @staticmethod
    def _pick_url_for_mpd(item, is_audio=False):
        urls = []
        base = item.get("baseUrl", "") or item.get("base_url", "")
        if base:
            urls.append(base)
        for b in (item.get("backupUrl", []) or item.get("backup_url", []) or []):
            if b and b not in urls:
                urls.append(b)
        for url in urls:
            if "mcdn" in url and "bilivideo" in url:
                return url
        for url in urls:
            if "bilivideo" in url:
                return url
        for url in urls:
            if "mcdn" in url:
                return url
        return urls[0] if urls else ""

    def localProxy(self, param):
        try:
            params = {}
            if isinstance(param, str):
                url_str = str(param)
                if "?" in url_str:
                    url_str = url_str.split("?", 1)[1]
                for part in url_str.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        params[k] = urllib.parse.unquote(v)
            elif isinstance(param, dict):
                params = dict(param)
            else:
                try:
                    for k in param.keySet():
                        params[str(k)] = str(param.get(k))
                except Exception:
                    params = {"raw": str(param)}

            if str(params.get("do", "")) in ("bili_mpd", "js"):
                aid = str(params.get("aid", ""))
                cid = str(params.get("cid", ""))
                eid = str(params.get("eid", ""))
                bvid = str(params.get("bvid", ""))

                if bvid and bvid != "0":
                    api_url = "{}/x/player/playurl?bvid={}&cid={}&qn=127&fnver=0&fnval=4048&fourk=1".format(API, bvid, cid)
                elif aid and aid != "0":
                    api_url = "{}/x/player/playurl?avid={}&cid={}&qn=127&fnver=0&fnval=4048&fourk=1".format(API, aid, cid)
                elif eid and eid != "0":
                    api_url = "{}/pgc/player/web/playurl?cid={}&qn=127&fnver=0&fnval=4048&fourk=1&ep_id={}".format(API, cid, eid)
                else:
                    api_url = "{}/x/player/playurl?cid={}&qn=127&fnver=0&fnval=4048&fourk=1".format(API, cid)

                data = self.http.get(api_url, timeout=10).json()
                if data.get("code") == 0:
                    result = data.get("result", {}) or data.get("data", {})
                    mpd = self._generate_mpd(result, target_ids=None)
                    if mpd:
                        return [200, "application/dash+xml", mpd.encode("utf-8"), {"Content-Type": "application/dash+xml"}]
                return [404, "text/plain", b"MPD generation failed", {}]
        except Exception as e:
            return [404, "text/plain", ("Error: " + str(e)).encode("utf-8"), {}]
        return [404, "text/plain", b"Not Found", {}]

    def _get_result(self, url):
        videos = []
        try:
            jo = self.http.get(url).json()
            if jo.get("code") == 0:
                vod_list = jo.get("result", {}).get("list", []) or jo.get("data", {}).get("list", [])
                for vod in vod_list:
                    aid = str(vod.get("season_id", "")).strip()
                    title = str(vod.get("title", "")).strip()
                    img = str(vod.get("cover", "")).strip()
                    remark = str(vod.get("index_show", "")).strip() if not vod.get("new_ep") else str(vod["new_ep"].get("index_show", "")).strip()
                    if "预告" not in title and "预告" not in remark:
                        videos.append({"vod_id": aid, "vod_name": title, "vod_pic": img, "vod_remarks": remark})
        except Exception:
            pass
        return videos

    def _get_rank(self, tid, pg):
        return self._get_result("{}://{}/pgc/web/rank/list?season_type={}&pagesize=20&page={}&day=3".format("https", "api.bilibili.com", tid, pg))

    def _get_rank2(self, tid, pg):
        return self._get_result("{}://{}/pgc/season/rank/web/list?season_type={}&pagesize=20&page={}&day=3".format("https", "api.bilibili.com", tid, pg))

    def _get_all(self, tid, pg, order, season_status):
        return self._get_result("{}://{}/pgc/season/index/result?order={}&pagesize=20&type=1&season_type={}&page={}&season_status={}".format("https", "api.bilibili.com", order, tid, pg, season_status))

    def _get_timeline(self, tid, pg):
        videos = []
        try:
            jo = self.http.get("{}://{}/pgc/web/timeline/v2?season_type={}&day_before=2&day_after=4".format("https", "api.bilibili.com", tid)).json()
            if jo.get("code") == 0:
                result = jo.get("result", {})
                videos1 = []
                for vod in result.get("latest", []):
                    aid = str(vod.get("season_id", "")).strip()
                    title = str(vod.get("title", "")).strip()
                    img = str(vod.get("cover", "")).strip()
                    remark = str(vod.get("pub_index", "")) + "　" + str(vod.get("follows", "")).replace("系列", "")
                    if "预告" not in title and "预告" not in remark:
                        videos1.append({"vod_id": aid, "vod_name": title, "vod_pic": img, "vod_remarks": remark})
                videos2 = []
                for i in range(min(7, len(result.get("timeline", [])))):
                    for vod in result["timeline"][i].get("episodes", []):
                        if str(vod.get("published", "")) == "0" and "预告" not in vod.get("title", ""):
                            aid = str(vod.get("season_id", "")).strip()
                            title = str(vod.get("title", "")).strip()
                            img = str(vod.get("cover", "")).strip()
                            pub_ts = vod.get("pub_ts", 0)
                            try:
                                from datetime import datetime
                                date_str = datetime.fromtimestamp(pub_ts).strftime("%m-%d")
                            except Exception:
                                date_str = str(pub_ts)
                            remark = "{}   {}".format(date_str, vod.get("pub_index", ""))
                            videos2.append({"vod_id": aid, "vod_name": title, "vod_pic": img, "vod_remarks": remark})
                videos = videos2 + videos1
        except Exception:
            pass
        return videos

    def _get_wbi_keys(self):
        try:
            r = self.http.get(self.host + "/x/web-interface/nav")
            data = r.json()
            if data.get("code") == 0:
                wbi_img = data["data"].get("wbi_img", {})
                iu = wbi_img.get("img_url", "")
                su = wbi_img.get("sub_url", "")
                img_key = iu.split("/")[-1].split(".")[0] if iu else ""
                sub_key = su.split("/")[-1].split(".")[0] if su else ""
                if img_key and sub_key:
                    return {"img_key": img_key, "sub_key": sub_key}
        except Exception:
            pass
        return None

    def _enc_wbi(self, params, keys):
        mixin_key_enc_tab = [
            46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
            27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
            37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
            22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 52, 44,
        ]
        orig = keys["img_key"] + keys["sub_key"]
        mixin_key = "".join([orig[i] for i in mixin_key_enc_tab])[:32]
        params["wts"] = int(time.time())
        parts = []
        for k, v in sorted(params.items()):
            val = str(v).replace("!", "").replace("'", "").replace("(", "").replace(")", "").replace("*", "")
            parts.append("{}={}".format(urllib.parse.quote(str(k), safe=""), urllib.parse.quote(str(val), safe="")))
        query = "&".join(parts)
        w_rid = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
        return query + "&w_rid=" + w_rid

    @staticmethod
    def _zh(num):
        try:
            n = int(num)
        except Exception:
            return str(num)
        if n > 1e8:
            return "{:.2f}亿".format(n / 1e8)
        elif n > 1e4:
            return "{:.2f}万".format(n / 1e4)
        else:
            return str(n)

    @staticmethod
    def _dedupe(items):
        out, seen = [], set()
        for x in items:
            vid = x.get("vod_id")
            if vid and vid not in seen:
                seen.add(vid)
                out.append(x)
        return out


if __name__ == "__main__":
    s = Spider()
    s.init('{"vmid":""}')
    print("=== homeContent ===")
    print(json.dumps(s.homeContent(), ensure_ascii=False))
    print("\n=== homeVideoContent ===")
    print(json.dumps(s.homeVideoContent(), ensure_ascii=False))

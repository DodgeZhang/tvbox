# -*- coding: utf-8 -*-
import json
import re
from urllib.parse import urljoin, quote
import requests
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "4K&BeliTV合集"

    def init(self, extend=""):
        self.extend = extend.strip()
        self.session = requests.Session()
        # -------- 两套站点配置 --------
        if self.extend == "belitv":
            self.mode = "belitv"
            self.host = "https://www.belitv.com"
            self.api = ""
            self.headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": self.host + "/"
            }
            self.category_map = {
                "电影": "/dianying/",
                "剧集": "/juji/",
                "综艺": "/zongyi/",
                "动漫": "/dongman/"
            }
        else:
            # 默认：量子4K API
            self.mode = "4k"
            self.host = "http://cj.lziapi.com"
            self.api = self.host + "/api.php/provide/vod/"
            self.headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Referer": self.host + "/"
            }
            self.year_opts = [{"n": str(y), "v": str(y)} for y in range(2026, 2013, -1)]
            self.cat_subs = {}

        self.session.headers.update(self.headers)

    def _fix(self, url):
        if not url:
            return ""
        return url if url.startswith("http") else urljoin(self.host + "/", url)

    def _is_media(self, url):
        return bool(re.search(r"\.(?:m3u8|mp4)(?:$|[?#])", url or "", re.I))

    def _resolve_url(self, url, depth=0):
        url = self._fix(url)
        if self._is_media(url) or depth > 3:
            return url
        try:
            r = self.session.get(url, timeout=15, verify=False, proxies=self.session.proxies or None)
            body = r.text if r.ok else ""
        except Exception:
            return url
        for pat in (
            r'player_aaaa\s*=\s*({[\s\S]*?});',
            r'var\s+playurl\s*=\s*["\']([^"\']+)["\']',
            r"var\s+main\s*=\s*['\"]([^'\"]+)",
            r"url\s*[:=]\s*['\"]([^'\"]+\.m3u8[^'\"]*)",
            r'<video[^>]+src=["\']([^"\']+)',
            r'<iframe[^>]*src=["\']([^"\']+)["\']'
        ):
            m = re.search(pat, body, re.I)
            if m and m.group(1):
                nxt = urljoin(url, m.group(1).replace("&amp;", "&"))
                return self._resolve_url(nxt, depth + 1)
        return url

    # ========== 【量子4K API 内部工具】 ==========
    def _json(self, params):
        try:
            r = self.session.get(self.api, params=params, timeout=15, verify=False, proxies=self.session.proxies or None)
            return r.json()
        except Exception:
            return {}

    def _item(self, v):
        return {
            "vod_id": str(v.get("vod_id", "")),
            "vod_name": v.get("vod_name", ""),
            "vod_pic": self._fix(v.get("vod_pic", "")),
            "vod_remarks": v.get("vod_remarks", "")
        }

    def _load(self, tid, pg, year=""):
        params = {"ac": "videolist", "t": tid, "pg": pg}
        if year:
            params["year"] = year
        return self._json(params)

    # ========== 【BeliTV HTML爬取 内部工具】 ==========
    def _fetch(self, url, timeout=15):
        try:
            r = self.session.get(url, timeout=timeout, verify=False, proxies=self.session.proxies or None)
            return {"code": r.status_code, "text": r.text}
        except Exception:
            return {"code": 500, "text": ""}

    def _extractPic(self, html, title=""):
        if not html:
            return ""
        if title:
            patterns = [
                r'<img[^>]*alt=["\']' + re.escape(title) + r'["\'][^>]*data-src=["\']([^"\']+)["\']',
                r'<img[^>]*alt=["\']' + re.escape(title) + r'["\'][^>]*data-original=["\']([^"\']+)["\']',
                r'<img[^>]*alt=["\']' + re.escape(title) + r'["\'][^>]*src=["\']([^"\']+)["\']',
            ]
            for p in patterns:
                m = re.search(p, html)
                if m:
                    return self._fix(m.group(1))
        m = re.search(r'<img[^>]*data-src=["\']([^"\']+)["\']', html)
        if m:
            return self._fix(m.group(1))
        m = re.search(r'<img[^>]*data-original=["\']([^"\']+)["\']', html)
        if m:
            return self._fix(m.group(1))
        m = re.search(r'<img[^>]*src=["\']([^"\']+)["\']', html)
        if m:
            return self._fix(m.group(1))
        return ""

    def _extractListVod(self, html):
        vod_list = []
        items = re.findall(r'<a[^>]*href=["\'](/vod/[^"\']+)["\'][^>]*title=["\']([^"\']+)["\']', html)
        for href, title in items:
            vod_id = href.strip("/").split("/")[-1].replace(".html", "")
            pic = self._extractPic(html, title=title)
            vod_list.append({
                "vod_id": vod_id,
                "vod_name": title.strip(),
                "vod_pic": pic
            })
        if not vod_list:
            items = re.findall(r'<li[^>]*>[\s\S]*?<a[^>]*href=["\'](/vod/[^"\']+)["\'][\s\S]*?title=["\']([^"\']+)["\'][\s\S]*?</li>', html)
            for href, title in items:
                vod_id = href.strip("/").split("/")[-1].replace(".html", "")
                pic = self._extractPic(html, title=title)
                vod_list.append({
                    "vod_id": vod_id,
                    "vod_name": title.strip(),
                    "vod_pic": pic
                })
        return vod_list

    # ========== 对外六接口（模式自动分发） ==========
    def homeContent(self, filter):
        if self.mode == "4k":
            d = self._json({"ac": "list"})
            cls_raw = d.get("class", [])
            subs = {}
            for c in cls_raw:
                pid = str(c.get("type_pid", 0))
                if pid and pid != "0":
                    subs.setdefault(pid, []).append(str(c.get("type_id")))
            self.cat_subs = subs
            cls = [{"type_id": str(c.get("type_id")), "type_name": c.get("type_name", "")} for c in cls_raw]
            filters = {c["type_id"]: [{"key": "year", "name": "年份", "value": self.year_opts}] for c in cls}
            return {"class": cls, "list": [], "filters": filters}
        else:
            cls = [
                {"type_id": "电影", "type_name": "电影"},
                {"type_id": "剧集", "type_name": "剧集"},
                {"type_id": "综艺", "type_name": "综艺"},
                {"type_id": "动漫", "type_name": "动漫"},
            ]
            return {"class": cls, "list": [], "filters": {}}

    def homeVideoContent(self):
        if self.mode == "4k":
            d = self._json({"ac": "videolist", "pg": 1})
            return {"list": [self._item(v) for v in d.get("list", [])]}
        else:
            res = self._fetch(self.host)
            if res["code"] != 200:
                return {"list": []}
            html = res["text"]
            vod_list = []
            items = re.findall(r'<a[^>]*href=["\'](/vod/[^"\']+)["\'][^>]*>([\s\S]{0,400}?)</a>', html)
            for href, block in items[:14]:
                vod_id = href.strip("/").split("/")[-1].replace(".html", "")
                name_m = re.search(r'title=["\']([^"\']+)["\']', block)
                name = name_m.group(1) if name_m else ""
                pic = self._extractPic(block, title=name)
                if not pic:
                    pic = self._extractPic(html, title=name)
                rem_m = re.search(r'(第[\d]+集|[\d]+集全|更新至[\d]+集)', block)
                remarks = rem_m.group(1) if rem_m else ""
                if name:
                    vod_list.append({
                        "vod_id": vod_id,
                        "vod_name": name.strip(),
                        "vod_pic": pic,
                        "vod_remarks": remarks
                    })
            return {"list": vod_list}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        if self.mode == "4k":
            y = extend.get("year", "") if extend else ""
            subs = self.cat_subs.get(str(tid), [])
            if subs:
                out, seen, total, pagecount = [], set(), 0, 1
                for sid in subs:
                    d = self._load(sid, pg, y)
                    if not d.get("list"):
                        continue
                    pagecount = max(pagecount, int(d.get("pagecount", 1) or 1))
                    total += int(d.get("total", 0) or 0)
                    for v in d.get("list", []):
                        vid = str(v.get("vod_id", ""))
                        if not vid or vid in seen:
                            continue
                        seen.add(vid)
                        out.append(self._item(v))
                return {"page": pg, "pagecount": pagecount, "limit": len(out) or 20, "total": total, "list": out}
            d = self._load(str(tid), pg, y)
            return {
                "page": pg,
                "pagecount": int(d.get("pagecount", 1) or 1),
                "limit": int(d.get("limit", 20) or 20),
                "total": int(d.get("total", 0) or 0),
                "list": [self._item(v) for v in d.get("list", [])]
            }
        else:
            path = self.category_map.get(tid)
            if not path:
                return {"page": pg, "pagecount": 0, "limit": 20, "total": 0, "list": []}
            if pg <= 1:
                url = self.host + path
            else:
                url = f"{self.host}{path}index-{pg}.html"
            resp = self._fetch(url)
            if resp["code"] != 200:
                return {"page": pg, "pagecount": 0, "limit": 20, "total": 0, "list": []}
            html = resp["text"]
            vod_list = self._extractListVod(html)
            m = re.search(r'共(\d+)页', html)
            pagecount = int(m.group(1)) if m else 10
            return {
                "page": pg,
                "pagecount": pagecount,
                "limit": 20,
                "total": pagecount * 20,
                "list": vod_list
            }

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        if self.mode == "4k":
            d = self._json({"ac": "detail", "ids": vid})
            out = []
            for v in d.get("list", []):
                item = self._item(v)
                item.update({
                    "vod_play_from": v.get("vod_play_from", ""),
                    "vod_play_url": v.get("vod_play_url", "")
                })
                out.append(item)
            return {"list": out}
        else:
            detail_url = f"{self.host}/vod/{vid}.html"
            resp = self._fetch(detail_url)
            if resp["code"] != 200:
                return {"list": []}
            html = resp["text"]
            name = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            vod_name = name.group(1).strip() if name else ""
            vod_pic = self._extractPic(html, title=vod_name)
            desc = re.search(r'<div[^>]*class=["\'][^"\']*desc[^"\']*["\']>([\s\S]*?)</div>', html)
            vod_content = re.sub(r'<[^>]+>', '', desc.group(1)).strip() if desc else ""
            play_from, play_url = [], []
            blocks = re.findall(r'<div[^>]*class=["\'][^"\']*play-list-title[^"\']*["\'][^>]*>([\s\S]*?)</div>[\s\S]*?<ul>([\s\S]*?)</ul>', html)
            if not blocks:
                blocks = re.findall(r'<h3[^>]*>([\s\S]*?)</h3>[\s\S]*?<ul[^>]*>([\s\S]*?)</ul>', html)
            for line_name, ul_html in blocks:
                line_name = re.sub(r'<[^>]+>', '', line_name).strip() or "播放线路"
                eps = re.findall(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', ul_html)
                if eps:
                    play_from.append(line_name)
                    play_url.append("#".join([f"{ep_name}${link}" for link, ep_name in eps]))
            vod = {
                "vod_id": vid,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_content": vod_content,
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url)
            }
            return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        if self.mode == "4k":
            d = self._json({"ac": "detail", "wd": key, "pg": pg})
            return {"page": pg, "list": [self._item(v) for v in d.get("list", [])]}
        else:
            search_url = f"{self.host}/search.php?wd={quote(key,encoding='utf-8')}&pg={pg}"
            resp = self._fetch(search_url)
            if resp["code"] != 200:
                return {"page": pg, "pagecount": 0, "limit": 20, "total": 0, "list": []}
            html = resp["text"]
            vod_list = self._extractListVod(html)
            return {"page": pg, "pagecount": 5, "limit": 20, "total": 100, "list": vod_list}

    def playerContent(self, flag, id, vipFlags):
        url = self._resolve_url(id)
        return {
            "parse": 0 if self._is_media(url) else 1,
            "url": url,
            "header": json.dumps({
                "User-Agent": self.headers["User-Agent"],
                "Referer": self.host + "/"
            })
        }

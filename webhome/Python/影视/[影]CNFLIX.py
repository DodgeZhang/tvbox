#!/usr/bin/python
# -*- coding: utf-8 -*-
import base64
import html as html_lib
import json
import os
import re
from urllib.parse import quote, unquote, urljoin, urlparse

import requests
from lxml import etree
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "CNFLIX"

    def init(self, extend=""):
        self.name = "CNFLIX"
        self.host = "https://www.cnflix.tv"
        self.api = self.host + "/index.php/ajax/data"
        self.classes = [
            {"type_id": "1", "type_name": "剧集"},
            {"type_id": "2", "type_name": "电影"},
            {"type_id": "3", "type_name": "综艺"},
            {"type_id": "4", "type_name": "动漫"},
            {"type_id": "42", "type_name": "短剧"},
            {"type_id": "7", "type_name": "韩剧"},
            {"type_id": "5", "type_name": "纪录片"},
        ]
        self.slug_tid = {
            "tv": "1",
            "movies": "2",
            "varietyshow": "3",
            "anime": "4",
            "shortdrama": "42",
            "krdrama": "7",
            "documentaries": "5",
        }
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        self.ajax_headers = dict(self.headers)
        self.ajax_headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        })
        self.ext = {}
        self.proxy = None
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._init_proxy(extend)

    def _init_proxy(self, extend=""):
        try:
            if isinstance(extend, str) and extend.strip().startswith("{"):
                self.ext = json.loads(extend)
            elif isinstance(extend, dict):
                self.ext = extend
        except Exception:
            self.ext = {}
        self._probe_proxy()
        if self.proxy:
            self.session.proxies.update(self.proxy)

    def _probe_proxy(self):
        p = self.ext.get("proxy") if isinstance(self.ext, dict) else ""
        if p:
            if not str(p).startswith("http"):
                p = "http://" + str(p)
            self.proxy = {"http": p, "https": p}
            return
        for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy", "PROXY", "proxy"):
            val = os.environ.get(key)
            if val:
                if not val.startswith("http"):
                    val = "http://" + val
                self.proxy = {"http": val, "https": val}
                return

    def _fix(self, url):
        if not url:
            return ""
        return urljoin(self.host + "/", str(url).replace("\\/", "/"))

    def _html(self, url, headers=None):
        try:
            r = self.session.get(
                self._fix(url),
                headers=headers or self.headers,
                timeout=15,
                verify=False,
                proxies=self.session.proxies or None,
            )
            r.encoding = r.apparent_encoding or "utf-8"
            if "application/json" in r.headers.get("Content-Type", "").lower():
                try:
                    data = r.json()
                    if isinstance(data, str):
                        return data
                except Exception:
                    pass
            return r.text
        except Exception:
            return ""

    def _json(self, params):
        try:
            r = self.session.get(
                self.api,
                params=params,
                headers=self.ajax_headers,
                timeout=15,
                verify=False,
                proxies=self.session.proxies or None,
            )
            if r.status_code in (403, 429):
                return {}
            ctype = r.headers.get("Content-Type", "").lower()
            if "json" not in ctype and not r.text.lstrip().startswith("{"):
                return {}
            data = r.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _to_int(self, value, default):
        try:
            return int(value)
        except Exception:
            return default

    def _text(self, node):
        if node is None:
            return ""
        return " ".join("".join(node.xpath(".//text()")).split())

    def _clean_text(self, text):
        text = html_lib.unescape(str(text or ""))
        text = re.sub(r"[\ue000-\uf8ff]", " ", str(text or ""))
        return " ".join(text.split())

    def _title_from_detail(self, html, tree, vid):
        metas = tree.xpath('//meta[@property="og:title"]/@content') if tree is not None else []
        if metas:
            title = re.split(r"[\[_]", metas[0], 1)[0]
            title = self._clean_text(title)
            if title:
                return title
        m = re.search(r"<title>\s*(?:[^《<]+《)?([^》<|]+)(?:》)?", html or "", re.S)
        if m:
            title = self._clean_text(m.group(1))
            if title:
                return title
        nodes = tree.xpath('//*[contains(@class,"slide-info-title")]') if tree is not None else []
        if nodes:
            title = self._clean_text(self._text(nodes[0]))
            if title:
                return title
        return str(vid)

    def _item(self, vod):
        if not isinstance(vod, dict):
            return {}
        name = self._clean_text(vod.get("vod_name"))
        vid = str(vod.get("vod_id") or "")
        if not name or not vid:
            return {}
        remarks = self._clean_text(vod.get("vod_remarks") or vod.get("vod_class") or vod.get("vod_year"))
        return {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": self._fix(vod.get("vod_pic") or vod.get("vod_pic_thumb") or vod.get("vod_pic_slide")),
            "vod_remarks": remarks,
        }

    def _items_from_json(self, data):
        out = []
        seen = set()
        for vod in data.get("list") or []:
            item = self._item(vod)
            vid = item.get("vod_id")
            if vid and vid not in seen:
                seen.add(vid)
                out.append(item)
        return out

    def _items_from_html(self, html):
        tree = etree.HTML(html or "")
        if tree is None:
            return []
        out = []
        seen = set()
        nodes = tree.xpath('//div[contains(@class,"public-list-box")][.//a[contains(@href,"/detail/")]]')
        if not nodes:
            nodes = tree.xpath('//a[contains(@href,"/detail/") and @title]')
        for node in nodes:
            try:
                if node.tag == "a":
                    a = node
                    box = node
                else:
                    title_nodes = node.xpath('.//a[contains(@class,"time-title") and contains(@href,"/detail/")]')
                    a = title_nodes[0] if title_nodes else node.xpath('.//a[contains(@href,"/detail/")]')[0]
                    box = node
                href = self._fix(a.get("href"))
                m = re.search(r"/detail/(\d+)/", href)
                if not m or m.group(1) in seen:
                    continue
                seen.add(m.group(1))
                pic = ""
                pics = box.xpath('.//*[contains(@class,"lazy")]/@data-original | .//img/@data-original | .//img/@src')
                if pics:
                    pic = self._fix(pics[0])
                name = self._clean_text(a.get("title") or self._text(a))
                remarks = self._clean_text(" ".join(box.xpath('.//*[contains(@class,"public-list-prb")]/text()')))
                out.append({"vod_id": m.group(1), "vod_name": name, "vod_pic": pic, "vod_remarks": remarks})
            except Exception:
                continue
        return out

    def _extract_player_json(self, html):
        m = re.search(r"var\s+player_aaaa\s*=", html or "")
        if not m:
            return {}
        start = html.find("{", m.end())
        if start < 0:
            return {}
        depth = 0
        quote_ch = ""
        escaped = False
        for pos in range(start, len(html)):
            ch = html[pos]
            if quote_ch:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote_ch:
                    quote_ch = ""
                continue
            if ch in ("'", '"'):
                quote_ch = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[start : pos + 1])
                    except Exception:
                        return {}
        return {}

    def _decode_player_url(self, value, encrypt=0):
        value = str(value or "").strip()
        if not value:
            return ""
        try:
            if str(encrypt) == "2":
                value = base64.b64decode(value + "===").decode("utf-8", errors="ignore")
            if str(encrypt) in ("1", "2"):
                value = unquote(value)
        except Exception:
            return ""
        return value.replace("\\/", "/").replace("&amp;", "&")

    def _is_media(self, url):
        parsed = urlparse(str(url or ""))
        return parsed.scheme in ("http", "https") and bool(re.search(r"\.(?:m3u8|mp4)(?:$|[?#])", parsed.path, re.I))

    def _probe_media(self, url):
        if not self._is_media(url):
            return ""
        try:
            headers = dict(self.headers)
            headers["Range"] = "bytes=0-4095"
            r = self.session.get(
                url,
                headers=headers,
                timeout=15,
                verify=False,
                stream=True,
                proxies=self.session.proxies or None,
            )
            data = next(r.iter_content(4096), b"")
            final = r.url
            ctype = r.headers.get("Content-Type", "").lower()
            if not r.ok and r.status_code != 206:
                return ""
            if re.search(r"\.m3u8(?:$|[?#])", urlparse(final).path, re.I):
                return final if b"#EXTM3U" in data else ""
            return final if "video/" in ctype or data[4:12].find(b"ftyp") >= 0 else ""
        except Exception:
            return ""

    def _page_url(self, tid, pg):
        pg = self._to_int(pg, 1)
        tid = self.slug_tid.get(str(tid), str(tid))
        return pg, tid

    def homeContent(self, filter):
        data = self._json({"mid": 1, "limit": 10, "page": 1})
        return {"class": self.classes, "list": self._items_from_json(data), "filters": {}}

    def homeVideoContent(self):
        data = self._json({"mid": 1, "limit": 10, "page": 1})
        items = self._items_from_json(data)
        if not items:
            items = self._items_from_html(self._html(self.host + "/"))
        return {"list": items}

    def categoryContent(self, tid, pg, filter, extend):
        page, tid = self._page_url(tid, pg)
        params = {"mid": 1, "limit": 20, "page": page, "tid": tid}
        data = self._json(params)
        items = self._items_from_json(data)
        pagecount = self._to_int(data.get("pagecount"), page)
        limit = self._to_int(data.get("limit"), len(items) or 20)
        total = self._to_int(data.get("total"), len(items))
        return {"page": page, "pagecount": pagecount, "limit": limit, "total": total, "list": items}

    def detailContent(self, ids):
        out = []
        source_ids = ids if isinstance(ids, list) else [ids]
        for raw_id in source_ids:
            vid = str(raw_id or "")
            m = re.search(r"/detail/(\d+)/|^(\d+)$", vid)
            vid = (m.group(1) or m.group(2)) if m else vid
            html = self._html(self.host + "/detail/" + vid + "/")
            tree = etree.HTML(html or "")
            if tree is None:
                continue
            name = self._title_from_detail(html, tree, vid)
            pic_nodes = tree.xpath(
                '//*[contains(@class,"detail") or contains(@class,"vod")]'
                '//*[contains(@class,"lazy")]/@data-original | '
                '//*[contains(@class,"detail") or contains(@class,"vod")]//img/@data-original | '
                '//*[contains(@class,"detail") or contains(@class,"vod")]//img/@src'
            )
            pic = self._fix(pic_nodes[0]) if pic_nodes else ""
            desc_nodes = tree.xpath('//*[contains(@class,"details-content") or contains(@class,"sketch") or contains(@class,"content")]')
            desc = self._clean_text(self._text(desc_nodes[0]) if desc_nodes else "")
            tabs = tree.xpath('//div[contains(@class,"anthology-tab")]//a[contains(@class,"vod-playerUrl")]')
            boxes = tree.xpath('//div[contains(@class,"anthology-list-box")]')
            play_from = []
            play_url = []
            for index, box in enumerate(boxes):
                links = []
                for a in box.xpath('.//a[contains(@href,"/play/")]'):
                    href = self._fix(a.get("href"))
                    ep = self._clean_text(a.get("title") or self._text(a))
                    if not ep:
                        ep = "播放"
                    links.append(ep + "$" + href)
                if not links:
                    continue
                source = ""
                if index < len(tabs):
                    badge = self._clean_text("".join(tabs[index].xpath('.//span[contains(@class,"badge")]/text()')))
                    source = self._clean_text(" ".join(tabs[index].xpath(".//text()[not(parent::span)]")))
                    if badge and source.endswith(badge):
                        source = source[: -len(badge)].strip()
                    source = re.sub(r"^[^\w\u4e00-\u9fff]+", "", source).strip()
                if not source:
                    source = "线路" + str(len(play_from) + 1)
                play_from.append(source)
                play_url.append("#".join(links))
            vod = {
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_content": desc,
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url),
            }
            out.append(vod)
        return {"list": out}

    def searchContent(self, key, quick, pg="1"):
        page = self._to_int(pg, 1)
        params = {"mid": 1, "limit": 20, "page": page, "wd": str(key or "")}
        data = self._json(params)
        items = self._items_from_json(data)
        if not items:
            html = self._html(self.host + "/vodsearch/?wd=" + quote(str(key or "")))
            items = self._items_from_html(html)
        pagecount = self._to_int(data.get("pagecount"), page)
        limit = self._to_int(data.get("limit"), len(items) or 20)
        total = self._to_int(data.get("total"), len(items))
        return {"page": page, "pagecount": pagecount, "limit": limit, "total": total, "list": items}

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "")
        url = raw if self._is_media(raw) else ""
        if not url:
            html = self._html(raw)
            data = self._extract_player_json(html)
            url = self._decode_player_url(data.get("url"), data.get("encrypt", 0))
        valid = self._probe_media(url)
        final = valid or url
        return {
            "parse": 0 if self._is_media(final) else 1,
            "url": final,
            "header": json.dumps(self.headers, ensure_ascii=False),
        }

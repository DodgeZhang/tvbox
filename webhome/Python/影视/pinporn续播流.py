#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import json
import base64
import html as html_lib
import urllib.request
import urllib.parse
from urllib.parse import urlparse, quote, unquote
import http.cookiejar
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

def format_remarks(brand="🦋 蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

def safe_quote_url(url):
    if not url:
        return ""
    parts = urllib.parse.urlsplit(url)
    encoded_path = urllib.parse.quote(parts.path, safe="/:")
    encoded_query = urllib.parse.quote(parts.query, safe="=&?/")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, encoded_path, encoded_query, parts.fragment))

COLOR_PALETTES = [
    ("4f46e5", "ffffff"),
    ("0284c7", "ffffff"),
    ("059669", "ffffff"),
    ("d97706", "ffffff"),
    ("dc2626", "ffffff"),
    ("7c3aed", "ffffff"),
    ("db2777", "ffffff"),
    ("0d9488", "ffffff"),
    ("ea580c", "ffffff"),
    ("16a34a", "ffffff"),
    ("9333ea", "ffffff"),
    ("ca8a04", "ffffff"),
]

def get_color_dummy_pic(text):
    idx = sum(ord(c) for c in text) % len(COLOR_PALETTES)
    bg_color, text_color = COLOR_PALETTES[idx]
    display_txt = text.strip()[:2]
    return "https://dummyimage.com/640x360/%s/%s.png&text=%s" % (bg_color, text_color, quote(display_txt))

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://pin.porn"
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

        self._build_opener()

    def _build_opener(self):
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

        cipher_list = [
            "ECDHE-ECDSA-AES128-GCM-SHA256",
            "ECDHE-RSA-AES128-GCM-SHA256",
            "ECDHE-ECDSA-AES256-GCM-SHA384",
            "ECDHE-RSA-AES256-GCM-SHA384",
            "ECDHE-ECDSA-CHACHA20-POLY1305",
            "ECDHE-RSA-CHACHA20-POLY1305",
            "DHE-RSA-AES128-GCM-SHA256",
            "DHE-RSA-AES256-GCM-SHA384",
            "DEFAULT@SECLEVEL=1"
        ]
        try:
            self.ctx.set_ciphers(":".join(cipher_list))
        except Exception:
            pass

        try:
            self.ctx.options |= ssl.OP_NO_SSLv2
            self.ctx.options |= ssl.OP_NO_SSLv3
            self.ctx.options |= ssl.OP_NO_COMPRESSION
        except Exception:
            pass

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=self.ctx)
        )

    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        return True

    def getName(self):
        return "PinPorn·刷视频"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def _fetch(self, target_url, referer="", headers_extra=None):
        if not target_url.startswith("http"):
            target_url = urllib.parse.urljoin(self.siteUrl + "/", target_url)

        target_url = safe_quote_url(target_url)
        host = urllib.parse.urlsplit(target_url).netloc

        headers = {
            "Host": host,
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive"
        }
        if headers_extra:
            headers.update(headers_extra)

        last_err = ""
        for attempt in range(3):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=15) as resp:
                    code = resp.getcode()
                    final_url = resp.geturl()
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    elif enc == "deflate":
                        try:
                            raw = zlib.decompress(raw)
                        except Exception:
                            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    text = raw.decode("utf-8", errors="ignore")
                    return {"code": code, "text": text, "bytes": raw, "final_url": final_url, "err": "", "headers": dict(resp.headers)}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                err_raw = ""
                try:
                    err_raw = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                return {"code": e.code, "text": err_raw, "bytes": b"", "final_url": target_url, "err": str(e), "headers": {}}
            except Exception as e:
                last_err = str(e)
                if attempt < 2 and any(k in last_err for k in ("EOF", "violation", "handshake", "reset")):
                    self._build_opener()
                    continue
                return {"code": -1, "text": "", "bytes": b"", "final_url": target_url, "err": last_err, "headers": {}}

        return {"code": -1, "text": "", "bytes": b"", "final_url": target_url, "err": last_err, "headers": {}}

    def homeContent(self, filter):
        classes = [
            {"type_name": "🔥 热门推荐", "type_id": "feed_main"},
            {"type_name": "👑 OnlyFans", "type_id": "cs_3"},
            {"type_name": "📱 TikTok", "type_id": "tag_58"},
            {"type_name": "🏷️ 热门标签", "type_id": "feed_tags"}
        ]
        return {"class": classes}

    def homeVideoContent(self):
        return {"list": []}

    def _parse_video_feed(self, data_list, query_type="feed_main", current_pg=1):
        cards = []
        if not data_list or not isinstance(data_list, list):
            return cards

        for idx, item in enumerate(data_list):
            if not isinstance(item, dict):
                continue

            v_id = str(item.get("id", "")).strip()
            v_url = str(item.get("link", "")).strip()
            if not v_id or not v_url:
                continue

            v_title = str(item.get("title", "")).strip()
            if not v_title:
                v_title = "PinPorn #%s" % v_id

            v_pic = str(item.get("screen", "")).strip()
            rating = str(item.get("rating", ""))

            user_info = item.get("user") or {}
            user_name = user_info.get("userTitle", "") if isinstance(user_info, dict) else ""
            remarks_txt = ("@%s" % user_name) if user_name else (("❤ %s" % rating) if rating else "连播信息流")

            payload = {
                "id": v_id,
                "title": v_title,
                "link": v_url,
                "screen": v_pic,
                "user": user_name,
                "rating": rating,
                "type": query_type,
                "pg": current_pg,
                "idx": idx
            }
            encoded_id = "stream@@" + base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

            cards.append({
                "vod_id": encoded_id,
                "vod_name": v_title,
                "vod_pic": v_pic,
                "vod_remarks": format_remarks("🦋 蝴蝶短视频", remarks_txt),
                "style": {"type": "rect", "ratio": 0.56}
            })

        return cards

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        raw_tid = str(tid).strip()

        if raw_tid == "feed_tags":
            tag_api = "https://pin.porn/api/tagsList/?ipp=30&from_tag=%d" % pg
            res = self._fetch(tag_api)
            cards = []
            try:
                data = json.loads(res.get("text", "{}"))
                d_list = data.get("data", [])
                for grp in d_list:
                    for t in grp.get("tags", []):
                        t_id = str(t.get("id", ""))
                        t_title = str(t.get("title", ""))
                        t_count = str(t.get("videos", ""))
                        if t_id and t_title:
                            cards.append({
                                "vod_id": "folder@@tag_%s" % t_id,
                                "vod_name": "#%s" % t_title,
                                "vod_pic": get_color_dummy_pic(t_title),
                                "vod_remarks": "共 %s 部短视频" % t_count,
                                "vod_tag": "folder",
                                "style": {"type": "rect", "ratio": 1.78}
                            })
            except Exception:
                pass

            return {
                "page": pg,
                "pagecount": (pg + 1) if len(cards) >= 30 else 1,
                "limit": len(cards),
                "total": 9999,
                "list": cards
            }

        target_id = raw_tid.replace("folder@@", "")
        if target_id.startswith("tag_"):
            real_tag_id = target_id.replace("tag_", "")
            api_url = "https://pin.porn/api/videoInfo/?ipp=30&tag_id=%s&from_page=%d" % (real_tag_id, pg)
        elif target_id.startswith("cs_"):
            real_cs_id = target_id.replace("cs_", "")
            api_url = "https://pin.porn/api/videoInfo/?ipp=30&cs_id=%s&from_page=%d" % (real_cs_id, pg)
        else:
            api_url = "https://pin.porn/api/videoInfo/?ipp=30&from_page=%d" % pg

        res = self._fetch(api_url)
        cards = []
        try:
            data = json.loads(res.get("text", "{}"))
            cards = self._parse_video_feed(data.get("data", []), query_type=target_id, current_pg=pg)
        except Exception:
            pass

        return {
            "page": pg,
            "pagecount": (pg + 1) if len(cards) >= 30 else 1,
            "limit": len(cards),
            "total": 9999,
            "list": cards
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)

        if raw_id.startswith("folder@@"):
            return self.categoryContent(raw_id, 1, None, None)

        payload = {}
        if raw_id.startswith("stream@@"):
            try:
                b64_str = raw_id.replace("stream@@", "")
                payload = json.loads(base64.urlsafe_b64decode(b64_str.encode("utf-8")).decode("utf-8"))
            except Exception:
                pass

        target_type = payload.get("type", "feed_main")
        start_pg = int(payload.get("pg", 1))
        clicked_id = str(payload.get("id", ""))
        clicked_title = payload.get("title", "")
        clicked_link = payload.get("link", "")
        clicked_screen = payload.get("screen", "")
        clicked_user = payload.get("user", "PinPorn")

        video_stream_list = []
        seen_ids = set()

        if clicked_id and clicked_link:
            video_stream_list.append((clicked_title if clicked_title else "第01条", clicked_link))
            seen_ids.add(clicked_id)

        for fetch_pg in range(start_pg, start_pg + 3):
            if target_type.startswith("tag_"):
                real_tag_id = target_type.replace("tag_", "")
                api_url = "https://pin.porn/api/videoInfo/?ipp=30&tag_id=%s&from_page=%d" % (real_tag_id, fetch_pg)
            elif target_type.startswith("cs_"):
                real_cs_id = target_type.replace("cs_", "")
                api_url = "https://pin.porn/api/videoInfo/?ipp=30&cs_id=%s&from_page=%d" % (real_cs_id, fetch_pg)
            else:
                api_url = "https://pin.porn/api/videoInfo/?ipp=30&from_page=%d" % fetch_pg

            res = self._fetch(api_url)
            try:
                data = json.loads(res.get("text", "{}"))
                d_list = data.get("data", [])
                for item in d_list:
                    sub_id = str(item.get("id", ""))
                    sub_link = str(item.get("link", ""))
                    sub_title = str(item.get("title", "")).strip()
                    if sub_id and sub_link and sub_id not in seen_ids:
                        seen_ids.add(sub_id)
                        display_title = sub_title if sub_title else ("短视频 #%s" % sub_id)
                        video_stream_list.append((display_title, sub_link))
            except Exception:
                pass

        play_entries = []
        for idx, (t, l) in enumerate(video_stream_list):
            clean_t = ("%02d. %s" % (idx + 1, t)).replace("$", "").replace("#", "")
            play_entries.append("%s$%s" % (clean_t, l))

        if not play_entries and clicked_link:
            play_entries.append("播放原片$%s" % clicked_link)

        desc = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• 当前聚焦: %s\n"
            "• 创作者: @%s\n"
            "• 连播池: 已挂载连续 %d 条精彩短视频\n"
            "• 遥控器操作指南: 播放中按【右键】切下一个短视频，按【左键】重播或上一个，播完自动下划连续播放！"
        ) % (self.tgGroup, clicked_title, clicked_user, len(play_entries))

        return {
            "list": [{
                "vod_id": raw_id,
                "vod_name": clicked_title if clicked_title else ("PinPorn #%s" % clicked_id),
                "vod_pic": clicked_screen,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": format_remarks("🦋 蝴蝶影视", "连续连播流"),
                "vod_content": desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                "vod_play_from": "抖音沉浸连播",
                "vod_play_url": "#".join(play_entries)
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        raw_play = str(id).strip()

        header_dict = {
            "User-Agent": self._ua,
            "Referer": "https://pin.porn/",
            "Origin": "https://pin.porn"
        }

        return {
            "parse": 0,
            "jx": 0,
            "url": raw_play,
            "header": json.dumps(header_dict)
        }

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        search_api = "https://pin.porn/api/videoInfo/?ipp=30&search=%s&from_page=%d" % (quote(key), pg)
        res = self._fetch(search_api)

        cards = []
        try:
            data = json.loads(res.get("text", "{}"))
            cards = self._parse_video_feed(data.get("data", []), query_type="search", current_pg=pg)
        except Exception:
            pass

        return {
            "page": pg,
            "pagecount": (pg + 1) if len(cards) >= 30 else 1,
            "limit": len(cards),
            "total": 9999,
            "list": cards
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy inactive"]

    def destroy(self):
        self.options = {}
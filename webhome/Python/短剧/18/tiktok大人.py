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

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.siteUrl = "https://porntok.io"
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
        return "PornTok·短视频"

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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Connection": "keep-alive"
        }
        if headers_extra:
            headers.update(headers_extra)

        last_err = ""
        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=12) as resp:
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
                if attempt < 1 and any(k in last_err for k in ("EOF", "violation", "handshake", "reset")):
                    self._build_opener()
                    continue
                return {"code": -1, "text": "", "bytes": b"", "final_url": target_url, "err": last_err, "headers": {}}

        return {"code": -1, "text": "", "bytes": b"", "final_url": target_url, "err": last_err, "headers": {}}

    def homeContent(self, filter):
        classes = [
            {"type_name": "🔥 热门推荐", "type_id": "all"},
            {"type_name": "📱 Teen 18+", "type_id": "teen-18plus"},
            {"type_name": "🍑 巨乳大翘臀", "type_id": "big-tits"},
            {"type_name": "🎀 业余自拍", "type_id": "amateur"},
            {"type_name": "🌸 亚洲精选", "type_id": "asian"},
            {"type_name": "💄 熟女人妻", "type_id": "milf"},
            {"type_name": "🍑 极品后庭", "type_id": "anal"},
            {"type_name": "✨ 动漫二次元", "type_id": "hentai-animated"},
            {"type_name": "🍫 欧美金发", "type_id": "blonde"},
            {"type_name": "💃 拉丁热舞", "type_id": "latina"},
            {"type_name": "🖤 黑人珍珠", "type_id": "ebony"},
            {"type_name": "👳 印度风情", "type_id": "indian"}
        ]
        return {"class": classes}

    def homeVideoContent(self):
        return {"list": []}

    def _extract_videos(self, text):
        videos = []
        if not text:
            return videos

        clean_text = text.replace(r'\"', '"').replace(r'\/', '/')

        pattern = r'\{[^{}]*?"path"\s*:\s*"(https?://pub-9e425fd7f7a04b7aa301eafe26f84f84\.r2\.dev/videos/[^"]+\.mp4)"[^{}]*?\}'
        blocks = re.findall(pattern, clean_text)
        seen_paths = set()

        for path in blocks:
            clean_path = path.strip()
            if clean_path in seen_paths:
                continue
            seen_paths.add(clean_path)

            thumb = clean_path.rsplit('.', 1)[0] + '_thumb.webp'

            m_id = re.search(r'/([^/]+)\.mp4', clean_path)
            v_id = m_id.group(1) if m_id else str(len(seen_paths))

            videos.append({
                "id": v_id,
                "path": clean_path,
                "thumbnail_url": thumb
            })

        if not videos:
            direct_urls = re.findall(r'(https?://pub-9e425fd7f7a04b7aa301eafe26f84f84\.r2\.dev/videos/[a-zA-Z0-9_\-\+/]+\.mp4)', clean_text)
            for d_url in direct_urls:
                if d_url not in seen_paths:
                    seen_paths.add(d_url)
                    thumb = d_url.rsplit('.', 1)[0] + '_thumb.webp'
                    m_id = re.search(r'/([^/]+)\.mp4', d_url)
                    v_id = m_id.group(1) if m_id else str(len(seen_paths))
                    videos.append({
                        "id": v_id,
                        "path": d_url,
                        "thumbnail_url": thumb
                    })

        return videos

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        raw_tid = str(tid).strip()

        if raw_tid == "all" or not raw_tid:
            req_url = self.siteUrl
        else:
            req_url = "%s/tag/%s" % (self.siteUrl, quote(raw_tid))

        res = self._fetch(req_url)
        html_body = res.get("text", "")
        raw_videos = self._extract_videos(html_body)

        if not raw_videos and raw_tid != "all":
            res = self._fetch(self.siteUrl)
            html_body = res.get("text", "")
            raw_videos = self._extract_videos(html_body)

        cards = []
        for idx, item in enumerate(raw_videos):
            v_id = item["id"]
            v_path = item["path"]
            v_thumb = item["thumbnail_url"]

            tag_display = ""
            m_tag = re.search(r'/videos/([^/]+)/', v_path)
            if m_tag:
                tag_display = "#" + m_tag.group(1).replace("_", " ")

            title = "%s 短视频 %02d" % (tag_display if tag_display else "PornTok", idx + 1)

            payload = {
                "id": v_id,
                "title": title,
                "link": v_path,
                "screen": v_thumb,
                "category": raw_tid,
                "idx": idx
            }
            encoded_id = "ptok@@" + base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

            cards.append({
                "vod_id": encoded_id,
                "vod_name": title,
                "vod_pic": v_thumb,
                "vod_remarks": format_remarks("🦋 蝴蝶短视频", tag_display if tag_display else "高清秒开"),
                "style": {"type": "rect", "ratio": 0.56}
            })

        return {
            "page": pg,
            "pagecount": pg,
            "limit": len(cards),
            "total": len(cards),
            "list": cards
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)

        payload = {}
        if raw_id.startswith("ptok@@"):
            try:
                b64_str = raw_id.replace("ptok@@", "")
                payload = json.loads(base64.urlsafe_b64decode(b64_str.encode("utf-8")).decode("utf-8"))
            except Exception:
                pass

        clicked_cat = payload.get("category", "all")
        clicked_title = payload.get("title", "")
        clicked_link = payload.get("link", "")
        clicked_screen = payload.get("screen", "")

        if clicked_cat == "all" or not clicked_cat:
            req_url = self.siteUrl
        else:
            req_url = "%s/tag/%s" % (self.siteUrl, quote(clicked_cat))

        res = self._fetch(req_url)
        raw_videos = self._extract_videos(res.get("text", ""))

        if not raw_videos and clicked_cat != "all":
            res = self._fetch(self.siteUrl)
            raw_videos = self._extract_videos(res.get("text", ""))

        video_stream_list = []
        seen_paths = set()

        if clicked_link:
            video_stream_list.append((clicked_title if clicked_title else "当前视频", clicked_link))
            seen_paths.add(clicked_link)

        for idx, item in enumerate(raw_videos):
            p = item["path"]
            if p not in seen_paths:
                seen_paths.add(p)
                m_tag = re.search(r'/videos/([^/]+)/', p)
                tag_name = m_tag.group(1).replace("_", " ") if m_tag else "推荐"
                video_stream_list.append(("#%s 短视频 %02d" % (tag_name, idx + 1), p))

        play_entries = []
        for idx, (t, l) in enumerate(video_stream_list):
            prefix = "▶ 当前播放" if idx == 0 else ("%02d. " % idx)
            clean_t = ("%s%s" % (prefix, t)).replace("$", "").replace("#", "")
            play_entries.append("%s$%s" % (clean_t, l))

        if not play_entries and clicked_link:
            play_entries.append("播放原片$%s" % clicked_link)

        desc = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• 当前聚焦: %s\n"
            "• 连播池: 已预载 %d 部精彩短视频\n"
            "• 播放通道: Cloudflare R2 原生直链 (零等待秒开)\n"
            "• 操作提示: 播放中按遥控器【右键】快速切下一条，播完自动连续循环下划！"
        ) % (self.tgGroup, clicked_title, len(play_entries))

        return {
            "list": [{
                "vod_id": raw_id,
                "vod_name": clicked_title if clicked_title else "PornTok 短视频",
                "vod_pic": clicked_screen,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": format_remarks("🦋 蝴蝶影视", "R2 直链秒开"),
                "vod_content": desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                "vod_play_from": "PornTok 连播专线",
                "vod_play_url": "#".join(play_entries)
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        raw_play = str(id).strip()

        return {
            "parse": 0,
            "jx": 0,
            "url": raw_play,
            "header": json.dumps({"User-Agent": self._ua})
        }

    def searchContent(self, key, quick, pg="1"):
        return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy inactive"]

    def destroy(self):
        self.options = {}
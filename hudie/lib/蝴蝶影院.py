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
import http.cookiejar
import gzip
import zlib
import ssl

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase(object):
        def getCache(self, key): return None
        def setCache(self, key, value): "fail"
        def delCache(self, key): "fail"


class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.navUrls = ["https://x99dh.cc", "https://x99dh.one"]
        self.defaultHost = "https://ptt01.com"
        self.siteUrl = self.defaultHost
        self.siteName = "三级片资源"
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

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
        cached_site = self.getCache("ptt01_dynamic_site_url")
        if cached_site and cached_site.startswith("http"):
            self.siteUrl = cached_site.strip().rstrip("/")
        else:
            self._refresh_site_url()
        return True

    def getName(self):
        return "蝴蝶影院·动态发布自愈版"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".mpd"))

    def manualVideoCheck(self):
        return False
    def _refresh_site_url(self):
        headers = {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate"
        }

        for nav in self.navUrls:
            text = ""
            try:
                req = urllib.request.Request(nav, headers=headers)
                with self.opener.open(req, timeout=8) as resp:
                    raw = resp.read()
                    enc = getattr(resp, "headers", {}).get("Content-Encoding", "")
                    if raw.startswith(b"\x1f\x8b") or enc == "gzip":
                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", errors="ignore")
            except urllib.error.HTTPError as e:
                try:
                    raw = e.read()
                    if raw.startswith(b"\x1f\x8b"):
                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""
            except Exception:
                continue

            if not text:
                continue
            b64_blocks = re.findall(r'["\']([A-Za-z0-9+/=]{100,})["\']', text)
            for b in b64_blocks:
                try:
                    decoded = base64.b64decode(b).decode("utf-8", errors="ignore")
                    unquoted = urllib.parse.unquote(decoded)
                    if "[" in unquoted and (self.siteName in unquoted or "稀缺资源" in unquoted):
                        site_list = json.loads(unquoted)
                        for item in site_list:
                            name = item.get("name", "").strip()
                            if name == self.siteName or name == "稀缺资源":
                                cand_urls = []
                                main_url = item.get("url", "")
                                if main_url:
                                    cand_urls.append(main_url)
                                for u_obj in item.get("urls", []):
                                    u = u_obj.get("url", "")
                                    if u and u not in cand_urls:
                                        cand_urls.append(u)

                                for c_url in cand_urls:
                                    parsed = urllib.parse.urlparse(c_url)
                                    base = "%s://%s" % (parsed.scheme, parsed.netloc)
                                    chk = self._fetch(base + "/p/1", check_host=False)
                                    if chk.get("code") == 200:
                                        self.siteUrl = base
                                        self.setCache("ptt01_dynamic_site_url", base)
                                        return True
                except Exception:
                    continue

        return False

    def _fetch(self, target_url, referer="", check_host=True):
        if not target_url:
            return {"code": 0, "text": "", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.siteUrl + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.siteUrl + "/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        last_err = ""
        domain_retried = False

        for attempt in range(2):
            try:
                req = urllib.request.Request(target_url, headers=headers)
                with self.opener.open(req, timeout=10) as resp:
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
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (404, 451, 502, 503) and check_host and not domain_retried:
                    old_host = urllib.parse.urlparse(self.siteUrl).netloc
                    self.delCache("ptt01_dynamic_site_url")
                    if self._refresh_site_url():
                        domain_retried = True
                        new_host = urllib.parse.urlparse(self.siteUrl).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if e.code in (451, 403, 429) and attempt == 0:
                    continue
                return {"code": e.code, "text": "", "err": str(e), "final_url": target_url}
            except Exception as e:
                last_err = str(e)
                if check_host and not domain_retried:
                    old_host = urllib.parse.urlparse(self.siteUrl).netloc
                    self.delCache("ptt01_dynamic_site_url")
                    if self._refresh_site_url():
                        domain_retried = True
                        new_host = urllib.parse.urlparse(self.siteUrl).netloc
                        target_url = target_url.replace(old_host, new_host)
                        continue
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "err": last_err, "final_url": target_url}

    def homeContent(self, filter):
        classes = [
            {"type_name": "🎬 电影", "type_id": "/p/1"},
            {"type_name": "📺 电视剧", "type_id": "/p/3"},
            {"type_name": "🌸 动漫", "type_id": "/p/4"},
            {"type_name": "🎤 综艺", "type_id": "/p/2"},
            {"type_name": "⚡ 短剧", "type_id": "/p/66"},
            {"type_name": "⚽ 体育", "type_id": "/p/53"}
        ]

        result = {"class": classes}

        if filter:
            areas = [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "2"},
                {"n": "香港", "v": "5"},
                {"n": "台湾", "v": "4"},
                {"n": "韩国", "v": "17"},
                {"n": "日本", "v": "18"},
                {"n": "欧美", "v": "6"},
                {"n": "泰国", "v": "10"}
            ]

            movie_types = [
                {"n": "全部", "v": ""},
                {"n": "伦理", "v": "/c/33"},
                {"n": "动作", "v": "/c/5"},
                {"n": "喜剧", "v": "/c/6"},
                {"n": "爱情", "v": "/c/7"},
                {"n": "科幻", "v": "/c/8"},
                {"n": "恐怖", "v": "/c/9"},
                {"n": "犯罪", "v": "/c/10"},
                {"n": "战争", "v": "/c/11"},
                {"n": "动漫", "v": "/c/12"},
                {"n": "剧情", "v": "/c/13"},
                {"n": "纪录", "v": "/c/14"},
                {"n": "悬疑", "v": "/c/15"},
                {"n": "动画", "v": "/c/16"},
                {"n": "解说", "v": "/c/35"}
            ]

            years = [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2015, -1)]

            filter_movie = [
                {"key": "class_id", "name": "类型", "value": movie_types},
                {"key": "area_id", "name": "地区", "value": areas},
                {"key": "year", "name": "年份", "value": years}
            ]

            filter_common = [
                {"key": "area_id", "name": "地区", "value": areas},
                {"key": "year", "name": "年份", "value": years}
            ]

            result["filters"] = {
                "/p/1": filter_movie,
                "/p/3": filter_common,
                "/p/4": filter_common,
                "/p/2": filter_common,
                "/p/66": filter_common,
                "/p/53": filter_common
            }

        return result

    def homeVideoContent(self):
        return {"list": []}

    def _parse_card_list(self, html_text):
        cards = []
        seen = set()

        item_blocks = re.findall(r'(<div[^>]+class=["\'][^"\']*item[^"\']*["\'][\s\S]*?</div>\s*</div>\s*</div>)', html_text, re.I)
        if not item_blocks:
            item_blocks = re.findall(r'(<a[^>]+href=["\']/\d+["\'][\s\S]*?</a>)', html_text, re.I)

        for block in item_blocks:
            m_href = re.search(r'href=["\'](/(\d+))["\']', block)
            if not m_href:
                continue
            path = m_href.group(1)
            if path in seen:
                continue

            title = ""
            m_title = re.search(r'title=["\']([^"\']+)["\']', block)
            if m_title:
                title = m_title.group(1).strip()
            if not title:
                m_txt = re.search(r'>([^<]{1,30})</a>', block)
                if m_txt:
                    clean = m_txt.group(1).strip()
                    if clean and not clean.startswith("fa-"):
                        title = clean

            if not title:
                title = "视频 %s" % m_href.group(2)

            img_src = ""
            m_img = re.search(r'(?:src|data-original|data-src)=["\']([^"\']+)["\']', block, re.I)
            if m_img:
                cand = m_img.group(1).strip()
                if not any(bad in cand.lower() for bad in ("logo", "avatar", "icon", ".svg")):
                    img_src = ("https:" + cand) if cand.startswith("//") else ((self.siteUrl + cand) if cand.startswith("/") else cand)

            m_rem = re.search(r'class=["\'][^"\']*(?:badge|label|text-muted|remarks)[^"\']*["\'][^>]*>([^<]+)<', block, re.I)
            remarks = m_rem.group(1).strip() if m_rem else "HD"

            seen.add(path)
            cards.append({
                "vod_id": path,
                "vod_name": html_lib.unescape(title),
                "vod_pic": img_src,
                "vod_remarks": remarks,
                "style": {"type": "rect", "ratio": 0.75}
            })

        return cards

    def categoryContent(self, tid, pg, filter, extend):
        del filter
        extend = extend if isinstance(extend, dict) else {}
        base_path = str(tid).strip()
        page_num = int(pg) if str(pg).isdigit() else 1

        class_id = extend.get("class_id", "")
        req_path = base_path + class_id if class_id else base_path

        query_parts = []
        area_id = extend.get("area_id", "")
        year = extend.get("year", "")
        if area_id:
            query_parts.append("area_id=%s" % area_id)
        if year:
            query_parts.append("year=%s" % year)

        if page_num > 1:
            query_parts.append("page=%d" % page_num)

        if query_parts:
            req_path += ("&" if "?" in req_path else "?") + "&".join(query_parts)

        res = self._fetch(req_path)
        cards = self._parse_card_list(res.get("text", ""))

        return {
            "page": page_num,
            "pagecount": page_num + 1 if len(cards) >= 12 else page_num,
            "limit": len(cards),
            "total": 9999,
            "list": cards
        }

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)
        target_path = str(raw_id).strip()

        res = self._fetch(target_path)
        html_text = res.get("text", "")

        title_m = re.search(r'<title>(.*?)</title>', html_text, re.I)
        vod_name = title_m.group(1).split("-")[0].strip() if title_m else "PTT01正片"

        vod_pic = ""
        m_og_pic = re.search(r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.I)
        if m_og_pic:
            vod_pic = m_og_pic.group(1).strip()

        desc = "PTT01 官方直连专线"
        m_desc = re.search(r'class=["\'][^"\']*(?:detail|intro|summary|content)[^"\']*["\'][^>]*>([\s\S]*?)</div>', html_text, re.I)
        if m_desc:
            clean_desc = re.sub(r'<[^>]+>', '', m_desc.group(1)).strip()
            if clean_desc:
                desc = clean_desc[:250]

        direct_streams = re.findall(r'https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', html_text)

        play_items = []
        if direct_streams:
            clean_m3u8 = direct_streams[0].replace("\\/", "/")
            play_items.append("正片$%s" % clean_m3u8)
        else:
            raw_play_links = re.findall(r'<a[^>]+href=["\'](/v/\d+[^"\']*)["\'][^>]*>([\s\S]*?)</a>', html_text, re.I)
            seen_eps = set()
            for href, text in raw_play_links:
                ep_title = re.sub(r'<[^>]+>', '', text).strip()
                if not ep_title or any(bad in ep_title for bad in ("快捷键", "XVIDEOS", "广告")):
                    continue
                if href in seen_eps:
                    continue
                seen_eps.add(href)
                play_items.append("%s$%s" % (ep_title, href))

        full_desc = (
            "【🔥 官方交流群: %s】\n"
            "【当前发布域名: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "%s"
        ) % (self.tgGroup, self.siteUrl, desc)

        return {
            "list": [{
                "vod_id": target_path,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_actor": self.brandActor,
                "vod_director": self.brandDirector,
                "vod_remarks": "HD原画",
                "vod_content": full_desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                "vod_play_from": "PTT01专线",
                "vod_play_url": "#".join(play_items) if play_items else "正片$http://127.0.0.1"
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        play_url = str(id).strip()

        if not play_url.startswith("http") and (play_url.startswith("/v/") or play_url.startswith("/")):
            res = self._fetch(play_url)
            html_text = res.get("text", "")
            m_hls = re.search(r'https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', html_text)
            if m_hls:
                play_url = m_hls.group(0).replace("\\/", "/")

        headers = {
            "User-Agent": self._ua,
            "Referer": self.siteUrl + "/",
            "Origin": self.siteUrl
        }

        return {
            "parse": 0,
            "jx": 0,
            "url": play_url,
            "header": headers,
            "contentType": "application/x-mpegURL" if ".m3u8" in play_url else "video/mp4",
            "format": "hls" if ".m3u8" in play_url else "mp4",
            "position": 1
        }

    def searchContent(self, key, quick, pg="1"):
        if not key:
            return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

        page_num = int(pg) if str(pg).isdigit() else 1
        encoded_key = urllib.parse.quote(str(key).strip())

        search_url = "/search?q=%s" % encoded_key
        if page_num > 1:
            search_url += "&page=%d" % page_num

        res = self._fetch(search_url)
        cards = self._parse_card_list(res.get("text", ""))

        return {
            "page": page_num,
            "pagecount": page_num + 1 if len(cards) >= 12 else page_num,
            "limit": len(cards),
            "total": 9999,
            "list": cards
        }

    def action(self, action):
        if action == "toast":
            return {"msg": "当前有效主站: %s" % self.siteUrl}
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [404, "text/plain; charset=utf-8", "Proxy not configured"]

    def destroy(self):
        self.options = {}
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

class Spider(SpiderBase):
    def __init__(self):
        super(Spider, self).__init__()
        self.baseHost = "https://missav.ws"
        self.siteUrl = "https://missav.ws/dm247/cn"
        self.tgGroup = "https://t.me/tvshare23"
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self._ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.options = {}

        self.categoryRoutes = {
            "chinese_subtitle": "/dm278/cn/chinese-subtitle",
            "new": "/dm539/cn/new",
            "release": "/dm635/cn/release",
            "uncensored_leak": "/dm817/cn/uncensored-leak",
            "today_hot": "/dm301/cn/today-hot",
            "weekly_hot": "/dm170/cn/weekly-hot",
            "monthly_hot": "/dm273/cn/monthly-hot",
            "actresses": "/cn/actresses",
            "actresses_ranking": "/cn/actresses/ranking",
            "genres": "/cn/genres",
            "makers": "/cn/makers",
            "vr": "/cn/genres/VR",
            "fc2": "/dm597/cn/fc2",
            "heyzo": "/dm2208642/cn/heyzo",
            "tokyohot": "/dm42/cn/tokyohot",
            "1pondo": "/dm5199603/cn/1pondo",
            "caribbeancom": "/dm7704788/cn/caribbeancom",
            "caribbeancompr": "/dm91887/cn/caribbeancompr",
            "10musume": "/dm7208981/cn/10musume",
            "pacopacomama": "/dm3600557/cn/pacopacomama",
            "gachinco": "/dm150/cn/gachinco",
            "siro": "/dm36/cn/siro",
            "luxu": "/dm34/cn/luxu",
            "gana": "/dm34/cn/gana",
            "scute": "/dm38/cn/scute",
            "maan": "/dm1004/cn/maan",
            "ara": "/dm34/cn/ara",
            "naughty4610": "/dm33/cn/naughty4610",
            "naughty0930": "/dm37/cn/naughty0930",
            "madou": "/dm63/cn/madou",
            "twav": "/dm31/cn/twav",
            "furuke": "/dm15/cn/furuke",
            "marriedslash": "/dm37/cn/marriedslash",
            "xxxav": "/dm42/cn/xxxav"
        }

        self.color_palette = [
            ("1e3a8a", "60a5fa"), ("14532d", "4ade80"), ("701a75", "f472b6"),
            ("7c2d12", "fb923c"), ("1f2937", "38bdf8"), ("312e81", "818cf8"),
            ("831843", "fb7185"), ("064e3b", "34d399"), ("3b0764", "c084fc")
        ]

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
        return True

    def getName(self):
        return "蝴蝶影视·MissAV"

    def isVideoFormat(self, url):
        low = (url or "").lower()
        return any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv", ".avi", ".ts", ".mpd", "index.png"))

    def manualVideoCheck(self):
        return False

    def _fetch(self, target_url, referer=""):
        if not target_url:
            return {"code": 0, "text": "", "bytes": b"", "err": "", "final_url": ""}
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = self.baseHost + target_url

        headers = {
            "User-Agent": self._ua,
            "Referer": referer if referer else (self.baseHost + "/"),
            "Origin": self.baseHost,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin"
        }

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
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = raw.decode("latin1", errors="ignore")
                    return {"code": code, "text": text, "bytes": raw, "err": "", "final_url": final_url}
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                err_raw = ""
                try:
                    err_raw = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                if e.code in (451, 403, 429) and attempt == 0:
                    continue
                return {"code": e.code, "text": err_raw, "bytes": b"", "err": str(e), "final_url": target_url}
            except Exception as e:
                last_err = str(e)
                if attempt == 0:
                    continue
                return {"code": -1, "text": "", "bytes": b"", "err": str(e), "final_url": target_url}

        return {"code": -1, "text": "", "bytes": b"", "err": last_err, "final_url": target_url}

    def homeContent(self, filter):
        classes = [
            {"type_name": "🀄 中文字幕", "type_id": "chinese_subtitle"},
            {"type_name": "⚡ 最近更新", "type_id": "new"},
            {"type_name": "🎬 新作上市", "type_id": "release"},
            {"type_name": "💧 无码流出", "type_id": "uncensored_leak"},
            {"type_name": "👠 女优一览", "type_id": "actresses"},
            {"type_name": "🏆 女优排行", "type_id": "actresses_ranking"},
            {"type_name": "🏷️ 全部类型", "type_id": "genres"},
            {"type_name": "🏢 全部发行商", "type_id": "makers"},
            {"type_name": "🥽 VR 专区", "type_id": "vr"},
            {"type_name": "📅 今日热门", "type_id": "today_hot"},
            {"type_name": "📈 本周热门", "type_id": "weekly_hot"},
            {"type_name": "👑 本月热门", "type_id": "monthly_hot"},
            {"type_name": "💎 FC2", "type_id": "fc2"},
            {"type_name": "💎 HEYZO", "type_id": "heyzo"},
            {"type_name": "💎 东京热", "type_id": "tokyohot"},
            {"type_name": "💎 一本道", "type_id": "1pondo"},
            {"type_name": "💎 加勒比", "type_id": "caribbeancom"},
            {"type_name": "💎 加勒比PR", "type_id": "caribbeancompr"},
            {"type_name": "💎 天然素人", "type_id": "10musume"},
            {"type_name": "💎 熟女俱乐部", "type_id": "pacopacomama"},
            {"type_name": "💎 Gachinco", "type_id": "gachinco"},
            {"type_name": "💎 SIRO", "type_id": "siro"},
            {"type_name": "💎 LUXU", "type_id": "luxu"},
            {"type_name": "💎 GANA", "type_id": "gana"},
            {"type_name": "💎 S-CUTE", "type_id": "scute"},
            {"type_name": "💎 PRESTIGE", "type_id": "maan"},
            {"type_name": "💎 ARA", "type_id": "ara"},
            {"type_name": "💎 顽皮4610", "type_id": "naughty4610"},
            {"type_name": "💎 顽皮0930", "type_id": "naughty0930"},
            {"type_name": "💎 麻豆传媒", "type_id": "madou"},
            {"type_name": "💎 TWAV", "type_id": "twav"},
            {"type_name": "💎 Furuke", "type_id": "furuke"},
            {"type_name": "💎 人妻斩", "type_id": "marriedslash"},
            {"type_name": "💎 XXX-AV", "type_id": "xxxav"}
        ]

        result = {"class": classes}

        if filter:
            filter_sort = {
                "key": "sort",
                "name": "排序",
                "init": "default",
                "value": [
                    {"n": "默认排序", "v": "default"},
                    {"n": "发行日期", "v": "released_at"},
                    {"n": "最近更新", "v": "published_at"},
                    {"n": "收藏最多", "v": "saved"},
                    {"n": "今日浏览", "v": "today_views"},
                    {"n": "本周浏览", "v": "weekly_views"},
                    {"n": "本月浏览", "v": "monthly_views"},
                    {"n": "总浏览数", "v": "views"}
                ]
            }
            filter_type = {
                "key": "filters",
                "name": "过滤",
                "init": "all",
                "value": [
                    {"n": "所有", "v": "all"},
                    {"n": "单人作品", "v": "individual"},
                    {"n": "多人作品", "v": "multiple"},
                    {"n": "中文字幕", "v": "chinese-subtitle"}
                ]
            }

            height_ranges = [
                "131-135", "136-140", "141-145", "146-150", "151-155",
                "156-160", "161-165", "166-170", "171-175", "176-180",
                "181-185", "186-190"
            ]
            filter_actress_height = {
                "key": "height",
                "name": "身高",
                "init": "all",
                "value": [{"n": "选择身高", "v": "all"}] + [{"n": "%scm" % r, "v": r} for r in height_ranges]
            }

            cups = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q"]
            filter_actress_cup = {
                "key": "cup",
                "name": "罩杯",
                "init": "all",
                "value": [{"n": "选择罩杯", "v": "all"}] + [{"n": "%s 罩杯" % c, "v": c} for c in cups]
            }

            filter_actress_age = {
                "key": "age",
                "name": "年龄",
                "init": "all",
                "value": [
                    {"n": "选择年龄", "v": "all"},
                    {"n": "< 20", "v": "<20"},
                    {"n": "20 - 30", "v": "20-30"},
                    {"n": "30 - 40", "v": "30-40"},
                    {"n": "40 - 50", "v": "40-50"},
                    {"n": "50 - 60", "v": "50-60"},
                    {"n": "> 60", "v": ">60"}
                ]
            }

            years = [str(y) for y in range(2026, 2007, -1)]
            filter_actress_debut = {
                "key": "debut",
                "name": "出道年份",
                "init": "all",
                "value": [{"n": "选择出道年份", "v": "all"}] + [{"n": "%s 以前" % y, "v": y} for y in years]
            }

            filter_actress_sort = {
                "key": "sort",
                "name": "排序",
                "init": "default",
                "value": [
                    {"n": "默认排序", "v": "default"},
                    {"n": "影片最多", "v": "videos"}
                ]
            }

            filters_dict = {}
            for item in classes:
                cid = item["type_id"]
                if cid == "actresses":
                    filters_dict[cid] = [
                        filter_actress_sort,
                        filter_actress_height,
                        filter_actress_cup,
                        filter_actress_age,
                        filter_actress_debut
                    ]
                elif cid not in ("actresses_ranking", "genres", "makers"):
                    filters_dict[cid] = [filter_sort, filter_type]

            result["filters"] = filters_dict

        return result

    def homeVideoContent(self):
        res = self._fetch(self.siteUrl)
        vod_list = self._parse_cards(res.get("text", ""), "video")
        return {"list": vod_list[:16]}

    def _parse_cards(self, html, mode="video"):
        body = html
        if "</nav>" in body:
            body = body.split("</nav>", 1)[1]
        elif "</header>" in body:
            body = body.split("</header>", 1)[1]

        vod_list = []
        seen_ids = set()

        if mode in ("actress", "actress_ranking"):
            is_ranking = (mode == "actress_ranking")

            chunks = re.findall(r'(<div[^>]*>\s*<a[^>]+href=["\'][^"\']*/actresses/[^"\']+["\'][^>]*>[\s\S]*?</div>\s*</div>)', body)
            if not chunks:
                chunks = re.findall(r'(<a[^>]+href=["\'][^"\']*/actresses/[^"\']+["\'][^>]*>[\s\S]*?</a>\s*<div[\s\S]*?</div>)', body)

            for block in chunks:
                href_m = re.search(r'href=["\']([^"\']*/actresses/[^"\']+)["\']', block)
                if not href_m:
                    continue
                href = href_m.group(1).strip()
                if href.endswith("/actresses/ranking") or "actresses/ranking" in href:
                    continue
                if href in seen_ids:
                    continue
                seen_ids.add(href)

                pic_m = re.search(r'(?:data-src|data-original|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', block, re.I)
                raw_pic = pic_m.group(1).strip() if pic_m else ""
                if raw_pic.startswith("//"):
                    raw_pic = "https:" + raw_pic
                elif raw_pic.startswith("/"):
                    raw_pic = urllib.parse.urljoin(self.baseHost, raw_pic)
                proxy_pic = ("%s@Referer=%s/@User-Agent=%s" % (raw_pic, self.baseHost, quote(self._ua))) if raw_pic else ""

                alt_m = re.search(r'alt=["\']([^"\']+)["\']', block)
                title = alt_m.group(1).strip() if alt_m else ""

                if not title:
                    txt_cands = re.findall(r'>([^<]+)<', block)
                    for tc in txt_cands:
                        t = tc.strip()
                        if t and not any(k in t for k in ("影片", "条", "條", "部", "出道", "年", "第", "名", "Ranking")):
                            if len(t) >= 2 and not t.isdigit():
                                title = t
                                break
                if not title:
                    title = "女优"

                title = html_lib.unescape(title)

                if is_ranking:
                    rank_m = re.search(r'(第\s*\d+\s*名)', block)
                    sub_desc = rank_m.group(1).replace(" ", "") if rank_m else ""
                    remarks_text = ("蝴蝶影视 · %s" % sub_desc) if sub_desc else "蝴蝶影视"
                else:
                    count_m = re.search(r'(\d+)\s*(?:条影片|條影片|部影片|部)', block)
                    debut_m = re.search(r'(\d{4})\s*(?:出道|年出道)', block)
                    meta_arr = []
                    if count_m:
                        meta_arr.append("%s部" % count_m.group(1))
                    if debut_m:
                        meta_arr.append("%s出道" % debut_m.group(1))
                    sub_desc = " · ".join(meta_arr) if meta_arr else ""
                    remarks_text = ("蝴蝶影视 · %s" % sub_desc) if sub_desc else "蝴蝶影视"

                display_name = ("%s\n%s" % (title, sub_desc)) if sub_desc else title

                vod_list.append({
                    "vod_id": "folder@" + (href if href.startswith("http") else urllib.parse.urljoin(self.baseHost, href)),
                    "vod_name": display_name,
                    "vod_pic": proxy_pic if proxy_pic else "https://dummyimage.com/300x300/222222/ffffff.png&text=" + quote(title[:4]),
                    "vod_remarks": remarks_text,
                    "vod_tag": "folder",
                    "style": {"type": "oval", "ratio": 1.0}
                })
            return vod_list

        if mode in ("genres", "makers"):
            target_key = "genres" if mode == "genres" else "makers"
            cell_pattern = r'(<div>\s*<a[^>]+href=["\'][^"\']*/' + target_key + r'/[^"\']+["\'][^>]*>[\s\S]*?</div>)'
            cells = re.findall(cell_pattern, body)

            for idx, cell in enumerate(cells):
                href_m = re.search(r'href=["\']([^"\']*/' + target_key + r'/[^"\']+)["\']', cell)
                if not href_m:
                    continue
                clean_href = href_m.group(1).strip()
                if clean_href in seen_ids or clean_href.endswith(("/" + target_key, "/" + target_key + "/")):
                    continue
                seen_ids.add(clean_href)

                title_m = re.search(r'<a[^>]+class=["\'][^"\']*text-nord13[^"\']*["\'][^>]*>([\s\S]*?)</a>', cell)
                if not title_m:
                    title_m = re.search(r'<a[^>]+href=["\'][^"\']*/' + target_key + r'/[^"\']+["\'][^>]*>([\s\S]*?)</a>', cell)
                raw_title = title_m.group(1).strip() if title_m else ""
                title = html_lib.unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()

                if not title:
                    continue

                count_m = re.search(r'(\d+)\s*(?:条影片|條影片|部影片|部)', cell)
                remarks = ("蝴蝶影视 · %s部" % count_m.group(1)) if count_m else "蝴蝶影视"

                first_char = title[0].strip().upper()
                bg_color, fg_color = self.color_palette[idx % len(self.color_palette)]
                card_pic = "https://dummyimage.com/640x360/%s/%s.png&text=%s" % (
                    bg_color, fg_color, quote(first_char)
                )

                vod_list.append({
                    "vod_id": "folder@" + (clean_href if clean_href.startswith("http") else urllib.parse.urljoin(self.baseHost, clean_href)),
                    "vod_name": title,
                    "vod_pic": card_pic,
                    "vod_remarks": remarks,
                    "vod_tag": "folder",
                    "style": {"type": "rect", "ratio": 1.78}
                })
            return vod_list

        card_chunks = []
        if 'class="relative group' in body:
            card_chunks = body.split('class="relative group')[1:]
        elif 'class="thumbnail' in body:
            card_chunks = body.split('class="thumbnail')[1:]
        else:
            card_chunks = re.findall(r'(<a[^>]+href=["\'](?:https?://missav\.[^"\']+|/[^"\']+)["\'][^>]*>[\s\S]*?</a>)', body)

        banned_slugs = {
            "chinese-subtitle", "new", "release", "uncensored-leak", "today-hot",
            "weekly-hot", "monthly-hot", "genres", "actresses", "makers", "series", "tags",
            "vip", "saved", "playlists", "history", "login", "register", "siro", "luxu", "gana"
        }

        for ch in card_chunks:
            href_m = re.search(r'href=["\']([^"\']*/(?:cn|dm\d+/cn)/([A-Za-z0-9_-]+))["\']', ch)
            if not href_m:
                continue
            full_href, dvd_id = href_m.groups()
            dvd_low = dvd_id.lower()

            if dvd_low in banned_slugs or dvd_low in seen_ids or len(dvd_id) < 3:
                continue
            seen_ids.add(dvd_low)

            alt_m = re.search(r'alt=["\']([^"\']+)["\']', ch)
            title = alt_m.group(1).strip() if alt_m else ""
            if not title or title in ("&nbsp;", "item.dvd_id"):
                txt_cands = re.findall(r'>([^<]{4,80})<', ch)
                for tc in txt_cands:
                    t_str = tc.strip()
                    if not any(k in t_str for k in ("item.", "HD", "FHD", "4K", ":")):
                        title = t_str
                        break
            if not title:
                title = dvd_id.upper()

            title = html_lib.unescape(title)

            pic_m = re.search(r'(?:data-src|data-original|src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', ch, re.I)
            if pic_m and "item.dvd_id" not in pic_m.group(1):
                raw_pic = pic_m.group(1).strip()
            else:
                raw_pic = "https://fourhoi.com/%s/cover-t.jpg" % dvd_id

            if raw_pic.startswith("//"):
                raw_pic = "https:" + raw_pic

            proxy_pic = "%s@Referer=%s/@User-Agent=%s" % (raw_pic, self.baseHost, quote(self._ua))

            dur_m = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', ch)
            if dur_m:
                dur = "蝴蝶影视 · %s" % dur_m.group(1)
            else:
                dur = "蝴蝶影视"

            pack_id = "%s@@%s" % (dvd_id, full_href)

            vod_list.append({
                "vod_id": pack_id,
                "vod_name": title,
                "vod_pic": proxy_pic,
                "vod_remarks": dur,
                "style": {"type": "rect", "ratio": 1.78}
            })

        return vod_list

    def categoryContent(self, tid, pg, filter, extend):
        slug = str(tid).strip()
        page = int(pg) if str(pg).isdigit() else 1

        if slug.startswith("folder@"):
            target_url = slug.replace("folder@", "")
            parse_mode = "video"
        else:
            route_path = self.categoryRoutes.get(slug, self.categoryRoutes["chinese_subtitle"])
            target_url = "%s%s" % (self.baseHost, route_path)
            if slug == "actresses":
                parse_mode = "actress"
            elif slug == "actresses_ranking":
                parse_mode = "actress_ranking"
            elif slug in ("genres", "makers"):
                parse_mode = slug
            else:
                parse_mode = "video"

        query_parts = []
        if page > 1:
            query_parts.append("page=%d" % page)

        if isinstance(extend, dict):
            if parse_mode == "actress":
                for param_k in ("height", "cup", "age", "debut"):
                    val = extend.get(param_k)
                    if val and val != "all":
                        query_parts.append("%s=%s" % (param_k, quote(val)))

                sort_val = extend.get("sort")
                if sort_val and sort_val != "default":
                    query_parts.append("sort=%s" % sort_val)

            elif parse_mode == "video":
                active_sort = extend.get("sort", "default")
                if active_sort and active_sort != "default":
                    query_parts.append("sort=%s" % active_sort)

                active_filters = extend.get("filters", "all")
                if active_filters and active_filters != "all":
                    query_parts.append("filters=%s" % active_filters)

        if query_parts:
            sep = "&" if "?" in target_url else "?"
            target_url = "%s%s%s" % (target_url, sep, "&".join(query_parts))

        res = self._fetch(target_url, referer=self.siteUrl)
        vod_list = self._parse_cards(res.get("text", ""), parse_mode)

        return {
            "page": page,
            "pagecount": (page + 1) if len(vod_list) >= 12 else page,
            "limit": len(vod_list),
            "total": 999,
            "list": vod_list
        }

    def _extract_surrit_uuid(self, html):
        if not html:
            return ""
        seek_m = re.search(r'https?://(?:surrit\.com|sixyik\.com)/([a-f0-9-]{36})/', html)
        if seek_m:
            return seek_m.group(1)

        urls_m = re.search(r'urls:\s*\[\s*["\']https?://[^"\']+/([a-f0-9-]{36})/', html)
        if urls_m:
            return urls_m.group(1)

        scripts = re.findall(r'<script[^>]*>([\s\S]*?)</script>', html)
        for sc in scripts:
            if "surrit.com" in sc or "hls.loadSource" in sc:
                u_m = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', sc)
                if u_m and "user_uuid" not in sc[sc.find(u_m.group(1)) - 20:sc.find(u_m.group(1)) + 40]:
                    return u_m.group(1)

        uuids = re.findall(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', html, re.I)
        for u in uuids:
            u_idx = html.find(u)
            surround = html[max(0, u_idx - 50):min(len(html), u_idx + 80)]
            if "user_uuid" not in surround and "recombee" not in surround:
                return u

        return ""

    def detailContent(self, ids):
        raw_id = ids[0] if isinstance(ids, (list, tuple)) else str(ids)

        if "@@" in raw_id:
            vid, origin_href = raw_id.split("@@", 1)
        else:
            vid = raw_id.replace("vod@", "").strip("/")
            origin_href = "%s/%s" % (self.siteUrl.rstrip("/"), vid)

        cand_urls = [
            origin_href if origin_href.startswith("http") else urllib.parse.urljoin(self.baseHost, origin_href),
            "%s/%s" % (self.siteUrl.rstrip("/"), vid),
            "%s/cn/%s" % (self.baseHost, vid)
        ]

        html = ""
        used_url = ""
        for u in cand_urls:
            res = self._fetch(u, referer=self.siteUrl)
            if res.get("code") == 200 and len(res.get("text", "")) > 3000:
                html = res.get("text", "")
                used_url = u
                break

        title_m = re.search(r'<title>(.*?)</title>', html, re.I)
        vod_name = vid.upper()
        if title_m:
            t_raw = title_m.group(1).split(" | ")[0].strip()
            if t_raw:
                vod_name = t_raw

        actress_matches = re.findall(r'<a[^>]+href=["\'][^"\']*/actresses/[^"\']+["\'][^>]*>([\s\S]*?)</a>', html)
        clean_actresses = []
        for a in actress_matches:
            name = re.sub(r'<[^>]+>', '', a).strip()
            if name and not any(k in name for k in ("排行", "Ranking", "一览", "SEP", "OCT", "NOV", "202")):
                if name not in clean_actresses:
                    clean_actresses.append(name)

        actor_text = ", ".join(clean_actresses) if clean_actresses else self.brandActor

        desc_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', html)
        desc = desc_m.group(1).strip() if desc_m else "蝴蝶影视高清聚合，全网同步更新。"
        vod_content = (
            "【🔥 官方交流群: %s】\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "%s"
        ) % (self.tgGroup, desc)
        escaped_desc = vod_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        surrit_uuid = self._extract_surrit_uuid(html)

        play_froms = []
        play_urls = []

        if surrit_uuid:
            real_m3u8 = "https://surrit.com/%s/playlist.m3u8" % surrit_uuid
            play_froms.append("蝴蝶正片专线")
            play_urls.append("超清原画正片$%s" % real_m3u8)

        play_froms.append("备用线路")
        play_urls.append("备用播放$%s" % (cand_urls[0]))

        pic = "https://fourhoi.com/%s/cover-n.jpg@Referer=%s/@User-Agent=%s" % (vid, self.baseHost, quote(self._ua))

        return {
            "list": [{
                "vod_id": raw_id,
                "vod_name": html_lib.unescape(vod_name),
                "vod_pic": pic,
                "vod_actor": actor_text,
                "vod_director": self.brandDirector,
                "vod_remarks": "蝴蝶影视",
                "vod_content": escaped_desc,
                "vod_play_from": "$$$".join(play_froms),
                "vod_play_url": "$$$".join(play_urls)
            }]
        }

    def playerContent(self, flag, id, vipFlags):
        url = str(id).strip()
        if ".m3u8" in url or "surrit.com" in url:
            return {
                "parse": 0,
                "jx": 0,
                "url": url,
                "header": {
                    "User-Agent": self._ua,
                    "Referer": self.baseHost + "/",
                    "Origin": self.baseHost
                }
            }
        else:
            return {
                "parse": 1,
                "jx": 0,
                "url": url,
                "header": {
                    "User-Agent": self._ua,
                    "Referer": self.baseHost + "/"
                }
            }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if str(pg).isdigit() else 1
        search_url = "%s/search/%s" % (self.siteUrl.rstrip("/"), quote(key))
        if page > 1:
            search_url = "%s?page=%d" % (search_url, page)

        res = self._fetch(search_url, referer=self.siteUrl)
        vod_list = self._parse_cards(res.get("text", ""), "video")

        return {
            "page": page,
            "pagecount": (page + 1) if len(vod_list) >= 12 else page,
            "limit": len(vod_list),
            "total": 999,
            "list": vod_list
        }

    def action(self, action):
        return {"msg": "ok"}

    def liveContent(self):
        return ""

    def localProxy(self, params):
        url = params.get("url", "")
        if not url:
            return [404, "text/plain; charset=utf-8", "Missing url"]
        res = self._fetch(url, referer=self.baseHost + "/")
        return [res.get("code", 200), "image/jpeg", res.get("bytes", b"")]

    def destroy(self):
        self.options = {}
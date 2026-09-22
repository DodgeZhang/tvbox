#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import json
import math
import time
import ssl
import gzip
import urllib.request
import urllib.parse
import html as html_mod

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def getName(self): return ""
        def homeContent(self, filter): return {}
        def homeVideoContent(self): return {}
        def categoryContent(self, tid, pg, filter, extend): return {}
        def detailContent(self, ids): return {}
        def searchContent(self, key, quick, pg="1"): return {}
        def playerContent(self, flag, id, vipFlags): return {}


class Spider(BaseSpider):
    BASE_URL = "http://ysttv.com"
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    _w_key = b"wechat_2026_key"
    _w_data = [0x92, 0xdb, 0xcd, 0x8c, 0xde, 0xd5, 0xba, 0xb7, 0x9c, 0xd6, 0x8a, 0xc8, 0x8e, 0xea, 0xce, 0x55,
               0x83, 0xd9, 0xf8, 0x84, 0xfe, 0xc4, 0xda, 0x8d, 0x9d, 0xd2, 0xe4, 0xdd, 0x83, 0xc8, 0xf0, 0x47,
               0x8c, 0xd4, 0xed, 0x05, 0xb8, 0x8c, 0x94, 0x03, 0x06, 0x6a, 0x5f, 0x50, 0x40, 0x45, 0x54, 0x56,
               0x5a, 0x85, 0xc8, 0xeb, 0xdb, 0xaa, 0xbd, 0xd0, 0xc4, 0xdf, 0x80, 0xdd, 0xed, 0x81, 0xdf, 0xf0,
               0x89, 0xc0, 0xf7, 0xda, 0x85, 0xb6, 0xd0, 0xe5, 0xfb, 0x80, 0xc9, 0xca, 0x80, 0xff, 0xc0, 0x87,
               0xce, 0xcf, 0xd7, 0xba, 0xa9]

    CATEGORIES = [
        {"type_id": "movie", "type_name": "电影", "url": "/vod/movie"},
        {"type_id": "teleplay", "type_name": "电视剧", "url": "/vod/teleplay"},
        {"type_id": "variety", "type_name": "综艺", "url": "/vod/variety"},
        {"type_id": "anime", "type_name": "动漫", "url": "/vod/anime"},
        {"type_id": "playlet", "type_name": "短剧", "url": "/vod/playlet"},
        {"type_id": "library", "type_name": "片库", "url": "/vod"},
        {"type_id": "latest", "type_name": "最近更新", "url": "/vod/latest"},
        {"type_id": "rating", "type_name": "高分推荐", "url": "/vod/rating"},
        {"type_id": "tianwendili", "type_name": "天文地理", "url": ""},
    ]

    TIANWEN_KEYWORDS = ["天文", "地理", "宇宙", "太空", "地球", "气象", "地质", "海洋", "自然", "科学"]

    def init(self, extend=""):
        pass

    def getName(self):
        return "影视天堂"

    def _get_wechat_info(self):
        result = bytearray()
        for i, b in enumerate(self._w_data):
            key_byte = self._w_key[i % len(self._w_key)]
            result.append(b ^ key_byte)
        return result.decode('utf-8')

    def getHtml(self, url, timeout=20, retries=3):
        last_error = None
        for attempt in range(retries):
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                try:
                    ctx.set_ciphers("DEFAULT@SECLEVEL=1:HIGH:!aNULL:!MD5")
                except Exception:
                    pass
                url = urllib.parse.quote(url, safe=":/?&=%+~-._")
                req = urllib.request.Request(url, headers={
                    "User-Agent": self.UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                    "Referer": self.BASE_URL + "/",
                })
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                    data = resp.read()
                    content_encoding = resp.headers.get("Content-Encoding", "")
                    if "gzip" in content_encoding:
                        try:
                            data = gzip.decompress(data)
                        except Exception:
                            pass
                    return self._decode_bytes(data)
            except Exception as e:
                last_error = e
                time.sleep(1)
        return ""

    def _decode_bytes(self, data):
        # 站点实际返回 GBK 字节却声明 UTF-8，按声明解码会导致中文乱码。
        # 通过统计各编码解码后 CJK 字符数量，自动选择最匹配的实际编码。
        candidates = ["utf-8", "gb18030", "gbk", "gb2312", "big5", "latin-1"]
        best_text = None
        best_score = -1
        for enc in candidates:
            try:
                text = data.decode(enc)
            except Exception:
                continue
            # latin-1 永远能解码，仅用作兜底
            if enc == "latin-1" and best_text is not None:
                continue
            score = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
            if score > best_score:
                best_score = score
                best_text = text
        if best_text is None:
            best_text = data.decode("utf-8", errors="replace")
        return best_text

    def clean(self, text):
        if not text:
            return ""
        text = html_mod.unescape(str(text))
        return re.sub(r"\s+", " ", text).strip()

    def _extract_video_cards(self, html):
        items = []
        seen = set()
        if not html:
            return items
        pattern = re.compile(r'<a[^>]*class="[^"]*video-card[^"]*"[^>]*>', re.I)
        for m in pattern.finditer(html):
            end = html.find('</a>', m.end())
            if end < 0:
                end = min(len(html), m.end() + 3000)
            block = html[m.start():end]
            href_m = re.search(r'href="(/detail/(\d+)/?)"', block)
            if not href_m:
                continue
            vid = href_m.group(2)
            if vid in seen:
                continue
            seen.add(vid)

            name = ""
            title_m = re.search(r'title="([^"]*)"', block)
            if title_m:
                name = self.clean(title_m.group(1))
            if not name:
                h3_m = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.S)
                if h3_m:
                    name = self.clean(re.sub(r'<[^>]+>', '', h3_m.group(1)))

            pic = ""
            pic_m = re.search(r'data-src="([^"]+)"', block)
            if pic_m:
                pic = pic_m.group(1)

            remark = ""
            sub_m = re.search(r'class="[^"]*subtitle[^"]*"[^>]*>\s*([^<]+)', block)
            if sub_m:
                remark = self.clean(sub_m.group(1))
            if not remark:
                tw_m = re.search(r'class="[^"]*text-white[^"]*"[^>]*>\s*([^<]+)', block)
                if tw_m:
                    remark = self.clean(tw_m.group(1))
            if remark in ("My post subtitle", "My Post Subtitle"):
                remark = ""

            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remark,
            })
        return items

    def _extract_search_items(self, html):
        items = []
        seen = set()
        if not html:
            return items
        pattern = re.compile(r'<a[^>]*class="[^"]*not-link[^"]*"[^>]*>', re.I)
        for m in pattern.finditer(html):
            end = html.find('</a>', m.end())
            if end < 0:
                end = min(len(html), m.end() + 3000)
            block = html[m.start():end]
            href_m = re.search(r'href="/detail/(\d+)"', block)
            if not href_m:
                continue
            vid = href_m.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            name = ""
            title_m = re.search(r'title="([^"]*)"', block)
            if title_m:
                name = self.clean(title_m.group(1))
            if not name:
                h2_m = re.search(r'<h2[^>]*>(.*?)</h2>', block, re.S)
                if h2_m:
                    name = self.clean(re.sub(r'<[^>]+>', '', h2_m.group(1)))

            pic = ""
            pic_m = re.search(r'data-src="([^"]+)"', block)
            if pic_m:
                pic = pic_m.group(1)

            remark = ""
            spans = re.findall(r'<span>([^<]+)</span>', block)
            parts = [self.clean(x) for x in spans if self.clean(x)]
            if parts:
                remark = "/".join(parts[:3])

            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remark,
            })
        return items

    def _add_wechat(self, videos):
        wechat = self._get_wechat_info()
        for v in videos:
            v["vod_content"] = wechat
        return videos

    def homeContent(self, filter):
        return {"class": self.CATEGORIES, "filters": {}}

    def homeVideoContent(self):
        result = {"list": []}
        try:
            html = self.getHtml(self.BASE_URL + "/")
            videos = self._extract_video_cards(html)
            result["list"] = self._add_wechat(videos)
        except Exception:
            pass
        return result

    def _search_page(self, keyword, page):
        try:
            url = "{}/search/video/{}/{}".format(self.BASE_URL, urllib.parse.quote(keyword), page)
            html = self.getHtml(url)
            return self._extract_search_items(html)
        except Exception:
            return []

    def _tianwen_category(self, page):
        items = []
        seen = set()
        for kw in self.TIANWEN_KEYWORDS:
            try:
                videos = self._search_page(kw, page)
                for v in videos:
                    if v["vod_id"] not in seen:
                        seen.add(v["vod_id"])
                        items.append(v)
            except Exception:
                continue
        return items

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": str(pg), "pagecount": "1", "total": "0"}
        try:
            page = int(pg) if str(pg).isdigit() else 1

            if str(tid) == "tianwendili":
                videos = self._tianwen_category(page)
                videos = self._add_wechat(videos)
                result["list"] = videos
                result["pagecount"] = str(page + 1)
                result["total"] = str(len(videos))
                return result

            cat = None
            for c in self.CATEGORIES:
                if c["type_id"] == str(tid):
                    cat = c
                    break
            if not cat:
                return result

            url = "{}{}/{}".format(self.BASE_URL, cat["url"], page)
            html = self.getHtml(url)
            videos = self._extract_video_cards(html)

            pagecount = page + 1
            total_m = re.search(r'data-rec-total="(\d+)"', html)
            per_m = re.search(r'data-rec-per-page="(\d+)"', html)
            if total_m and per_m:
                try:
                    total = int(total_m.group(1))
                    per = int(per_m.group(1))
                    if per > 0 and total > 0:
                        pagecount = max(page, math.ceil(total / per))
                except Exception:
                    pass

            videos = self._add_wechat(videos)
            result["list"] = videos
            result["pagecount"] = str(pagecount)
            result["total"] = str(len(videos))
            return result
        except Exception:
            return result

    def _extract_detail_field(self, html, label):
        m = re.search(label + r'[：:]\s*(.*?)(?=<|$)', html, re.S)
        if not m:
            return ""
        val = self.clean(re.sub(r'<[^>]+>', '', m.group(1)))
        return val

    def detailContent(self, ids):
        result = {"list": []}
        try:
            vid = ids[0] if isinstance(ids, list) and ids else ids
            vid = re.sub(r'\D', '', str(vid))
            if not vid:
                return result

            wechat = self._get_wechat_info()

            html = self.getHtml("{}/detail/{}/".format(self.BASE_URL, vid))
            if not html:
                return result

            vod = {"vod_id": vid}

            name = ""
            h1_m = re.search(r'<h1[^>]*title="([^"]*)"', html)
            if h1_m:
                name = self.clean(h1_m.group(1))
            if not name:
                h1b = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
                if h1b:
                    name = self.clean(re.sub(r'<[^>]+>', '', h1b.group(1))).strip('《》 ')
            if not name:
                title_m = re.search(r'<title>([^<]+)</title>', html)
                if title_m:
                    name = self.clean(title_m.group(1))
                    name = re.sub(r'\s*[-_－—].*影视天堂.*', '', name).strip()
            vod["vod_name"] = name if name else vid

            pic = ""
            pic_m = re.search(r'<img[^>]*poster_loading\.png[^>]*data-src="([^"]+)"', html, re.I)
            if pic_m:
                pic = pic_m.group(1)
            if not pic:
                pic_m = re.search(r'data-src="(https?://[^"]*(?:images\.7dgirl\.org|jinyingimage)[^"]*)"', html)
                if pic_m:
                    pic = pic_m.group(1)
            if not pic:
                pic_m = re.search(r'data-src="([^"]+)"', html)
                if pic_m:
                    pic = pic_m.group(1)
            vod["vod_pic"] = pic

            vod["vod_director"] = self._extract_detail_field(html, "导演")
            vod["vod_actor"] = self._extract_detail_field(html, "主演")

            h1_end = 0
            h1_m = re.search(r'<h1[^>]*>.*?</h1>', html, re.S)
            if h1_m:
                h1_end = h1_m.end()
            info_zone = html[h1_end:h1_end + 3000]
            info_links = re.findall(r'href="(/vod/[^"]*)"[^>]*>([^<]+)</a>', info_zone)
            class_parts = []
            for path, label in info_links:
                label = self.clean(label)
                if not label:
                    continue
                seg = path.strip('/').split('/')[-1]
                if re.match(r'^year\d+$', seg):
                    if not vod.get("vod_year"):
                        vod["vod_year"] = label
                elif re.match(r'^area', seg):
                    if not vod.get("vod_area"):
                        vod["vod_area"] = label
                elif re.match(r'^type', seg):
                    if not vod.get("vod_lang"):
                        vod["vod_lang"] = label
                else:
                    class_parts.append(label)
            if class_parts:
                vod["vod_class"] = "/".join(class_parts)

            score_m = re.search(r'class="text-4xl">([^<]+)</span>', html)
            if score_m:
                vod["vod_score"] = self.clean(score_m.group(1))

            desc = self._extract_detail_field(html, "剧情")
            vod["vod_content"] = wechat + ("\n" + desc if desc else "")

            ep_links = self._build_episodes(vid)

            if ep_links:
                vod["vod_play_from"] = "影视天堂"
                vod["vod_play_url"] = "#".join(ep_links[:999])
            else:
                vod["vod_play_from"] = "影视天堂"
                vod["vod_play_url"] = "播放${}/play/{}".format(self.BASE_URL, vid)

            result["list"] = [vod]
            return result
        except Exception:
            return result

    def _get_video_src(self, html):
        # 从播放页提取真实视频地址（m3u8 / 直链），忽略站点自带的点赞收藏等 data-url
        if not html:
            return ""
        for m in re.finditer(r'data-url="([^"]*)"', html):
            u = m.group(1)
            if "m3u8" in u or u.startswith("http"):
                return u
        m = re.search(r'data-url="(https?://[^"]*)"', html)
        return m.group(1) if m else ""

    def _build_episodes(self, vid):
        # 真实播放地址位于 /play/{vid}/{集数}，逐集探测可播放源（快速请求，容忍偶发拦截）
        ep_links = []
        n = 1
        miss = 0
        while n <= 80 and miss < 2:
            url = "{}/play/{}/{}".format(self.BASE_URL, vid, n)
            html = self.getHtml(url, timeout=10, retries=2)
            src = self._get_video_src(html)
            if src:
                ep_links.append("第{}集${}".format(n, url))
                miss = 0
            else:
                miss += 1
            n += 1
        return ep_links

    def searchContent(self, key, quick, pg="1"):
        result = {"list": [], "page": str(pg), "pagecount": "1", "total": "0"}
        try:
            page = int(pg) if str(pg).isdigit() else 1
            videos = self._search_page(key, page)
            videos = self._add_wechat(videos)
            result["list"] = videos
            result["pagecount"] = str(page + 1)
            result["total"] = str(len(videos))
            return result
        except Exception:
            return result

    def playerContent(self, flag, id, vipFlags):
        try:
            play_url = id
            if not play_url.startswith("http"):
                play_url = self.BASE_URL + "/" + play_url.lstrip("/")

            html = self.getHtml(play_url)
            if html:
                video_url = self._get_video_src(html)
                if not video_url:
                    time.sleep(1)
                    html = self.getHtml(play_url)
                    video_url = self._get_video_src(html)
                if video_url:
                    if video_url.startswith("//"):
                        video_url = "https:" + video_url
                    video_url = video_url.replace('\\/', '/')
                    if video_url and (".m3u8" in video_url or ".mp4" in video_url or video_url.startswith("http")):
                        headers = {
                            "User-Agent": self.UA,
                            "Referer": self.BASE_URL + "/",
                        }
                        return {
                            "url": video_url,
                            "parse": "0",
                            "header": json.dumps(headers),
                            "playUrl": "",
                            "subtitle": "",
                        }
        except Exception:
            pass

        return {
            "url": id,
            "parse": "0",
            "header": "",
            "playUrl": "",
            "subtitle": "",
        }

    def __jsEvalReturn(self):
        return {"proxy": None}

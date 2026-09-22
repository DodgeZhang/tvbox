#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
奇奇影视 TVBox Python Spider
网站地址: https://www.qqys01.com/
仅使用Python标准库，无需安装第三方包
"""

import re
import json
import ssl
import gzip
import urllib.request
import urllib.parse
import html as html_mod
import base64

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
    BASE_URL = "https://www.qqys01.com"
    WECHAT_INFO = '微信公众号"源力软件汇"，更多优质资源请加入源力捐赠版。'
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ENCRYPT_KEY = b"qqys01_spider_key_2026"

    CATEGORIES = [
        {"type_id": "1", "type_name": "电影", "url": "https://www.qqys01.com/vodtype/1.html"},
        {"type_id": "2", "type_name": "连续剧", "url": "https://www.qqys01.com/vodtype/2.html"},
        {"type_id": "3", "type_name": "综艺", "url": "https://www.qqys01.com/vodtype/3.html"},
        {"type_id": "4", "type_name": "动漫", "url": "https://www.qqys01.com/vodtype/4.html"},
        {"type_id": "5", "type_name": "短剧", "url": "https://www.qqys01.com/vodtype/5.html"},
    ]

    def init(self, extend=""):
        pass

    def getName(self):
        return "奇奇影视"

    def _encrypt_url(self, url):
        try:
            url_bytes = url.encode('utf-8')
            padded = url_bytes + b"\x00" * (16 - len(url_bytes) % 16) if len(url_bytes) % 16 != 0 else url_bytes
            encrypted = b""
            key = self.ENCRYPT_KEY[:16]
            for i in range(0, len(padded), 16):
                block = padded[i:i+16]
                encrypted_block = bytes(a ^ b for a, b in zip(block, key))
                encrypted += encrypted_block
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception:
            return url

    def _decrypt_url(self, encrypted_str):
        try:
            encrypted = base64.b64decode(encrypted_str)
            key = self.ENCRYPT_KEY[:16]
            decrypted = b""
            for i in range(0, len(encrypted), 16):
                block = encrypted[i:i+16]
                decrypted_block = bytes(a ^ b for a, b in zip(block, key))
                decrypted += decrypted_block
            return decrypted.rstrip(b"\x00").decode('utf-8')
        except Exception:
            return encrypted_str

    def getHtml(self, url):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={
                "User-Agent": self.UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Referer": self.BASE_URL + "/"
            })
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                data = resp.read()
                content_encoding = resp.headers.get("Content-Encoding", "")
                if "gzip" in content_encoding:
                    try:
                        data = gzip.decompress(data)
                    except Exception:
                        pass
                for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
                    try:
                        return data.decode(enc)
                    except Exception:
                        continue
                return data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def clean(self, text):
        if not text:
            return ""
        text = html_mod.unescape(str(text))
        return re.sub(r"\s+", " ", text).strip()

    def attr_val(self, tag_html, attr):
        m = re.search(rf'{attr}\s*=\s*["\']([^"\']*)["\']', tag_html)
        return m.group(1) if m else ""

    def homeContent(self, filter):
        return {"class": self.CATEGORIES, "filters": {}}

    def homeVideoContent(self):
        result = {"list": []}
        html = self.getHtml(self.BASE_URL)
        if not html:
            return result

        videos = []
        seen = set()

        for item in re.finditer(r'<a[^>]*class="[^"]*module-poster-item[^"]*"[^>]*>(.*?)</a>', html, re.S):
            block = item.group(1)
            href_match = re.search(r'href="(/voddetail\d+\.html)"', item.group(0))
            if not href_match:
                continue
            href = href_match.group(1)
            vid = re.search(r'voddetail(\d+)\.html', href)
            if not vid:
                continue
            vid = vid.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            name = ""
            title_m = re.search(r'<div[^>]*class="[^"]*module-poster-item-title[^"]*"[^>]*>([^<]+)</div>', block)
            if title_m:
                name = self.clean(title_m.group(1))
            if not name:
                title_m = re.search(r'title="([^"]+)"', item.group(0))
                if title_m:
                    name = self.clean(title_m.group(1))
            if not name:
                continue

            pic = ""
            do_m = re.search(r'data-original="([^"]+)"', block)
            if do_m:
                pic = do_m.group(1)
            else:
                src_m = re.search(r'<img[^>]*src="([^"]+)"', block)
                if src_m:
                    pic = src_m.group(1)

            score = ""
            score_m = re.search(r'([\d.]+)\s*分', block)
            if score_m:
                score = score_m.group(1)

            remarks = ""
            note_m = re.search(r'<div[^>]*class="[^"]*module-item-note[^"]*"[^>]*>([^<]+)</div>', block)
            if note_m:
                remarks = self.clean(note_m.group(1))

            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_score": score,
                "vod_remarks": remarks,
                "vod_content": self.WECHAT_INFO,
            })

        result["list"] = videos[:30]
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": str(pg), "pagecount": "1", "total": "0"}
        cat = None
        for c in self.CATEGORIES:
            if c["type_id"] == str(tid):
                cat = c
                break
        if not cat:
            return result

        page = int(pg) if str(pg).isdigit() else 1
        if page <= 1:
            url = cat["url"]
        else:
            url = cat["url"].replace(".html", f"-{page}.html")

        html = self.getHtml(url)
        if not html:
            return result

        videos = []
        seen = set()

        for item in re.finditer(r'<a[^>]*class="[^"]*module-poster-item[^"]*"[^>]*>(.*?)</a>', html, re.S):
            block = item.group(1)
            href_match = re.search(r'href="(/voddetail\d+\.html)"', item.group(0))
            if not href_match:
                continue
            href = href_match.group(1)
            vid = re.search(r'voddetail(\d+)\.html', href)
            if not vid:
                continue
            vid = vid.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            name = ""
            title_m = re.search(r'<div[^>]*class="[^"]*module-poster-item-title[^"]*"[^>]*>([^<]+)</div>', block)
            if title_m:
                name = self.clean(title_m.group(1))
            if not name:
                title_m = re.search(r'title="([^"]+)"', item.group(0))
                if title_m:
                    name = self.clean(title_m.group(1))
            if not name:
                continue

            pic = ""
            do_m = re.search(r'data-original="([^"]+)"', block)
            if do_m:
                pic = do_m.group(1)
            else:
                src_m = re.search(r'<img[^>]*src="([^"]+)"', block)
                if src_m:
                    pic = src_m.group(1)

            score = ""
            score_m = re.search(r'([\d.]+)\s*分', block)
            if score_m:
                score = score_m.group(1)

            remarks = ""
            note_m = re.search(r'<div[^>]*class="[^"]*module-item-note[^"]*"[^>]*>([^<]+)</div>', block)
            if note_m:
                remarks = self.clean(note_m.group(1))

            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_score": score,
                "vod_remarks": remarks,
                "type_id": str(cat["type_id"]),
                "type_name": cat["type_name"],
            })

        pagecount = "1"
        next_m = re.search(r'下一页', html)
        if next_m:
            pagecount = str(page + 1)

        result["list"] = videos
        result["pagecount"] = pagecount
        result["total"] = str(int(pagecount) * len(videos)) if videos else "0"
        return result

    def detailContent(self, ids):
        result = {"list": []}
        vid = ids[0] if isinstance(ids, list) and ids else ids
        url = f"{self.BASE_URL}/voddetail{vid}.html"
        html = self.getHtml(url)
        if not html:
            return result

        vod = {"vod_id": str(vid)}

        hm = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        vod["vod_name"] = self.clean(hm.group(1)) if hm else ""

        do_m = re.search(r'data-original="(https?://[^"]+)"', html)
        if do_m:
            vod["vod_pic"] = do_m.group(1)
        else:
            vod["vod_pic"] = ""

        vod["vod_class"] = ""
        vod["vod_area"] = ""
        vod["vod_year"] = ""
        vod["vod_remarks"] = ""
        vod["vod_actor"] = ""
        vod["vod_director"] = ""
        vod["vod_lang"] = ""

        info_patterns = [
            (r'分类[：:]\s*(.+?)<', 'vod_class'),
            (r'地区[：:]\s*(.+?)<', 'vod_area'),
            (r'年份[：:]\s*(\d+)', 'vod_year'),
            (r'更新[：:]\s*(.+?)<', 'vod_remarks'),
            (r'状态[：:]\s*(.+?)<', 'vod_remarks'),
            (r'主演[：:]\s*(.+?)<', 'vod_actor'),
            (r'导演[：:]\s*(.+?)<', 'vod_director'),
            (r'语言[：:]\s*(.+?)<', 'vod_lang'),
        ]

        for pattern, key in info_patterns:
            m = re.search(pattern, html)
            if m:
                vod[key] = self.clean(m.group(1))

        desc_m = re.search(r'og:description" content="([^"]+)"', html)
        if desc_m:
            desc_text = desc_m.group(1)
            if '剧情:' in desc_text:
                desc_text = desc_text.split('剧情:', 1)[1]
            vod["vod_content"] = self.WECHAT_INFO + "\n" + self.clean(desc_text)
        else:
            vod["vod_content"] = self.WECHAT_INFO

        play_url_groups = []
        seen_episodes = set()

        play_matches = list(re.finditer(r'href="(/vodplay/(\d+)-(\d+)-(\d+)\.html)"', html))
        for pm in play_matches:
            ep_href = pm.group(1)
            full_url = self.BASE_URL + ep_href
            if full_url in seen_episodes:
                continue
            seen_episodes.add(full_url)
            ep_num = pm.group(4)
            ep_name = f"第{ep_num}集" if ep_num.isdigit() else "播放"
            encrypted_url = self._encrypt_url(full_url)
            play_url_groups.append(f"{ep_name}${encrypted_url}")

        vod["vod_play_from"] = "极速在线"
        vod["vod_play_url"] = "#".join(play_url_groups) if play_url_groups else ""

        vod["type_id"] = "1"
        vod["type_name"] = "影视"

        result["list"] = [vod]
        return result

    def searchContent(self, key, quick, pg="1"):
        try:
            return self._do_search(key, quick, pg)
        except Exception:
            return {"list": [], "page": str(pg), "pagecount": "1", "total": "0"}

    def _do_search(self, key, quick, pg="1"):
        result = {"list": [], "page": str(pg), "pagecount": "1", "total": "0"}
        pg = int(pg) if str(pg).isdigit() else 1

        search_url = f"{self.BASE_URL}/vodsearch/-------------.html?wd={urllib.parse.quote(key)}"
        html = self.getHtml(search_url)

        if not html:
            return result

        videos = []
        seen = set()

        for href_match in re.finditer(r'href="(/voddetail(\d+)\.html)"', html):
            vid = href_match.group(2)
            if vid in seen:
                continue
            seen.add(vid)

            start = max(0, href_match.start() - 500)
            end = min(len(html), href_match.end() + 800)
            block = html[start:end]

            name = ""
            strong_m = re.search(r'<strong>([^<]+)</strong>', block)
            if strong_m:
                name = self.clean(strong_m.group(1))
            if not name:
                title_m = re.search(r'title="([^"]+)"', block)
                if title_m:
                    name = self.clean(title_m.group(1))
            if not name:
                continue

            if key.lower() not in name.lower():
                continue

            pic = ""
            do_m = re.search(r'data-original="([^"]+)"', block)
            if do_m:
                pic = do_m.group(1)
            else:
                src_m = re.search(r'<img[^>]*src="([^"]+)"', block)
                if src_m:
                    pic = src_m.group(1)

            score = ""
            score_m = re.search(r'([\d.]+)\s*分', block)
            if score_m:
                score = score_m.group(1)

            remarks = ""
            note_m = re.search(r'<div[^>]*class="[^"]*module-item-note[^"]*"[^>]*>([^<]+)</div>', block)
            if note_m:
                remarks = self.clean(note_m.group(1))

            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_score": score,
                "vod_remarks": remarks,
                "type_id": "1",
                "type_name": "搜索结果",
            })

        pagecount = "1"
        next_m = re.search(r'下一页', html)
        if next_m:
            pagecount = str(pg + 1)

        result["list"] = videos
        result["pagecount"] = pagecount
        result["total"] = str(int(pagecount) * len(videos)) if videos else "0"
        return result

    def _extract_play_url(self, html):
        player_data_m = re.search(r'player_data\s*=\s*({[^}]+})', html)
        if player_data_m:
            try:
                player_data = json.loads(player_data_m.group(1))
                encrypted_url = player_data.get("url", "")
                encrypt_type = str(player_data.get("encrypt", "0"))
                
                if encrypted_url:
                    if encrypt_type == "2":
                        try:
                            decoded_b64 = base64.b64decode(encrypted_url).decode('utf-8')
                            decoded_url = urllib.parse.unquote(decoded_b64)
                            if decoded_url:
                                return decoded_url
                        except Exception:
                            pass
                    elif encrypt_type == "1":
                        try:
                            decoded_url = urllib.parse.unquote(encrypted_url)
                            if decoded_url:
                                return decoded_url
                        except Exception:
                            pass
                    else:
                        if encrypted_url.startswith("http"):
                            return encrypted_url
            except Exception:
                pass

        url_patterns = [
            r'url\s*=\s*["\']([^"\']+\.(m3u8|mp4|flv))["\']',
            r'videoUrl\s*=\s*["\']([^"\']+\.(m3u8|mp4|flv))["\']',
            r'src\s*=\s*["\']([^"\']+\.(m3u8|mp4|flv))["\']',
            r'playUrl\s*=\s*["\']([^"\']+\.(m3u8|mp4|flv))["\']',
            r'"url"\s*:\s*["\']([^"\']+\.(m3u8|mp4|flv))["\']',
            r'"src"\s*:\s*["\']([^"\']+\.(m3u8|mp4|flv))["\']',
        ]

        for pattern in url_patterns:
            m = re.search(pattern, html)
            if m:
                url = m.group(1)
                if url.startswith("//"):
                    url = "https:" + url
                elif url.startswith("/"):
                    url = self.BASE_URL + url
                return url

        script_patterns = [
            r'player\.config\s*=\s*({[^}]+})',
            r'player\.setup\s*=\s*({[^}]+})',
            r'new\s+DPlayer\s*\(\s*({[^}]+})\s*\)',
        ]

        for pattern in script_patterns:
            m = re.search(pattern, html, re.S)
            if m:
                config_str = m.group(1)
                for url_pattern in [r'url\s*:\s*["\']([^"\']+)["\']', r'src\s*:\s*["\']([^"\']+)["\']']:
                    url_m = re.search(url_pattern, config_str)
                    if url_m:
                        url = url_m.group(1)
                        if url.startswith("//"):
                            url = "https:" + url
                        elif url.startswith("/"):
                            url = self.BASE_URL + url
                        if url.endswith((".m3u8", ".mp4", ".flv")):
                            return url

        return ""

    def playerContent(self, flag, id, vipFlags):
        try:
            decrypted_url = self._decrypt_url(id)
        except Exception:
            decrypted_url = id

        if not decrypted_url.startswith("http"):
            decrypted_url = self.BASE_URL + decrypted_url if decrypted_url.startswith("/") else id

        play_headers = {
            "User-Agent": self.UA,
            "Referer": self.BASE_URL + "/",
        }
        return {"url": decrypted_url, "parse": "1", "header": json.dumps(play_headers), "playUrl": "", "subtitle": ""}

    def __jsEvalReturn(self):
        return {"proxy": None}
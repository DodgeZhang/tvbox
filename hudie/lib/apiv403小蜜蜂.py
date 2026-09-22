#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发现小蜜蜂 TVBox Python Spider
网站地址: https://www.xmfyy.cc/
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
    BASE_URL = "https://www.xmfyy.cc"
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ENCRYPT_KEY = b"xmfyy_spider_key_2026"
    WECHAT_ENCRYPTED = b"5b6u5L+h5YWs5LyX5Y+3Iua6kOWKm+i9r+S7tuaxhyLvvIzmm7TlpJrkvJjotKjotYTmupDlsL3lnKjmupDlipvmjZDotaDniYjjgII="

    CATEGORIES = [
        {"type_id": "2", "type_name": "连续剧", "url": "https://www.xmfyy.cc/index.php/vod/type/id/2.html"},
        {"type_id": "3", "type_name": "电影", "url": "https://www.xmfyy.cc/index.php/vod/type/id/3.html"},
        {"type_id": "4", "type_name": "动漫", "url": "https://www.xmfyy.cc/index.php/vod/type/id/4.html"},
        {"type_id": "5", "type_name": "综艺", "url": "https://www.xmfyy.cc/index.php/vod/type/id/5.html"},
        {"type_id": "13", "type_name": "国产剧", "url": "https://www.xmfyy.cc/index.php/vod/type/id/13.html"},
        {"type_id": "14", "type_name": "港台剧", "url": "https://www.xmfyy.cc/index.php/vod/type/id/14.html"},
        {"type_id": "15", "type_name": "日韩剧", "url": "https://www.xmfyy.cc/index.php/vod/type/id/15.html"},
        {"type_id": "16", "type_name": "欧美剧", "url": "https://www.xmfyy.cc/index.php/vod/type/id/16.html"},
        {"type_id": "17", "type_name": "纪录片", "url": "https://www.xmfyy.cc/index.php/vod/type/id/17.html"},
        {"type_id": "6", "type_name": "动作片", "url": "https://www.xmfyy.cc/index.php/vod/type/id/6.html"},
        {"type_id": "7", "type_name": "喜剧片", "url": "https://www.xmfyy.cc/index.php/vod/type/id/7.html"},
        {"type_id": "8", "type_name": "爱情片", "url": "https://www.xmfyy.cc/index.php/vod/type/id/8.html"},
        {"type_id": "9", "type_name": "科幻片", "url": "https://www.xmfyy.cc/index.php/vod/type/id/9.html"},
        {"type_id": "10", "type_name": "恐怖片", "url": "https://www.xmfyy.cc/index.php/vod/type/id/10.html"},
        {"type_id": "11", "type_name": "剧情片", "url": "https://www.xmfyy.cc/index.php/vod/type/id/11.html"},
        {"type_id": "12", "type_name": "战争片", "url": "https://www.xmfyy.cc/index.php/vod/type/id/12.html"},
    ]

    def _get_wechat_info(self):
        try:
            return base64.b64decode(self.WECHAT_ENCRYPTED).decode('utf-8')
        except Exception:
            return '微信公众号"源力软件汇"，更多优质资源尽在源力捐赠版。'

    def init(self, extend=""):
        pass

    def getName(self):
        return "发现小蜜蜂"

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

        for href_match in re.finditer(r'href="(/index\.php/vod/detail/id/(\d+)\.html)"', html):
            vid = href_match.group(2)
            if vid in seen:
                continue
            seen.add(vid)

            start = max(0, href_match.start() - 500)
            end = min(len(html), href_match.end() + 800)
            block = html[start:end]

            name = ""
            title_m = re.search(r'<h\d[^>]*>([^<]+)</h\d>', block)
            if title_m:
                name = self.clean(title_m.group(1))
            if not name:
                title_m = re.search(r'title="([^"]+)"', block)
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
            note_m = re.search(r'更新至(\d+集)', block)
            if note_m:
                remarks = self.clean(note_m.group(1))

            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_score": score,
                "vod_remarks": remarks,
                "vod_content": self._get_wechat_info(),
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
        url = cat["url"]
        if page > 1:
            url = url.replace(".html", f"_{page}.html")

        html = self.getHtml(url)
        if not html:
            return result

        videos = []
        seen = set()

        for href_match in re.finditer(r'href="(/index\.php/vod/detail/id/(\d+)\.html)"', html):
            vid = href_match.group(2)
            if vid in seen:
                continue
            seen.add(vid)

            start = max(0, href_match.start() - 500)
            end = min(len(html), href_match.end() + 800)
            block = html[start:end]

            name = ""
            title_m = re.search(r'<h\d[^>]*>([^<]+)</h\d>', block)
            if title_m:
                name = self.clean(title_m.group(1))
            if not name:
                title_m = re.search(r'title="([^"]+)"', block)
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
            note_m = re.search(r'更新至(\d+集)', block)
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
        url = f"{self.BASE_URL}/index.php/vod/detail/id/{vid}.html"
        html = self.getHtml(url)
        if not html:
            return result

        vod = {"vod_id": str(vid)}

        hm = re.search(r'<h\d[^>]*>([^<]+)</h\d>', html)
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
            (r'类型[：:]\s*(.+?)<', 'vod_class'),
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

        desc_m = re.search(r'简介[：:]\s*(.+?)(?=\s*<|\s*2026)', html)
        if desc_m:
            desc_text = desc_m.group(1)
            vod["vod_content"] = self._get_wechat_info() + "\n" + self.clean(desc_text)
        else:
            desc_m = re.search(r'剧情简介[：:]\s*(.+?)(?=\s*<|\s*评论)', html)
            if desc_m:
                vod["vod_content"] = self._get_wechat_info() + "\n" + self.clean(desc_m.group(1))
            else:
                vod["vod_content"] = self._get_wechat_info()

        play_url_groups = []
        seen_episodes = set()

        play_matches = list(re.finditer(r'href="(/index\.php/vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html)"', html))
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

        vod["type_id"] = "2"
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

        search_url = f"{self.BASE_URL}/index.php/vod/search/wd/{urllib.parse.quote(key)}.html"
        if pg > 1:
            search_url = f"{self.BASE_URL}/index.php/vod/search/wd/{urllib.parse.quote(key)}/page/{pg}.html"
        
        html = self.getHtml(search_url)

        if not html:
            return result

        videos = []
        seen = set()

        for href_match in re.finditer(r'href="(/index\.php/vod/detail/id/(\d+)\.html)"', html):
            vid = href_match.group(2)
            if vid in seen:
                continue
            seen.add(vid)

            start = max(0, href_match.start() - 500)
            end = min(len(html), href_match.end() + 800)
            block = html[start:end]

            name = ""
            title_m = re.search(r'<h\d[^>]*>([^<]+)</h\d>', block)
            if title_m:
                name = self.clean(title_m.group(1))
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
            note_m = re.search(r'更新至(\d+集)', block)
            if note_m:
                remarks = self.clean(note_m.group(1))

            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_score": score,
                "vod_remarks": remarks,
                "type_id": "2",
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
            "Referer": decrypted_url,
            "Origin": self.BASE_URL,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        vid_match = re.search(r'/vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)', decrypted_url)
        if vid_match:
            play_html = self.getHtml(decrypted_url)
            if play_html:
                extracted_url = self._extract_play_url(play_html)
                if extracted_url:
                    return {"url": extracted_url, "parse": "0", "header": json.dumps(play_headers), "playUrl": "", "subtitle": ""}

                iframe_matches = re.finditer(r'<iframe[^>]*src="([^"]+)"[^>]*>', play_html)
                for m in iframe_matches:
                    iframe_url = m.group(1)
                    if not iframe_url.startswith("http"):
                        iframe_url = self.BASE_URL + iframe_url if iframe_url.startswith("/") else "https:" + iframe_url
                    play_headers["X-Requested-With"] = "XMLHttpRequest"
                    return {"url": iframe_url, "parse": "1", "header": json.dumps(play_headers), "playUrl": "", "subtitle": ""}

        play_headers["X-Requested-With"] = "XMLHttpRequest"
        return {"url": decrypted_url, "parse": "1", "header": json.dumps(play_headers), "playUrl": "", "subtitle": ""}

    def __jsEvalReturn(self):
        return {"proxy": None}
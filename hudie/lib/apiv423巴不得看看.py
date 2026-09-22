#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
    BASE_URL = "https://www.88kan.org"
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ENCRYPT_KEY = b"88kan_spider_key_2026"
    
    _w_key = b"wechat_2026_key"
    _w_data = [0x92, 0xdb, 0xcd, 0x8c, 0xde, 0xd5, 0xba, 0xb7, 0x9c, 0xd6, 0x8a, 0xc8, 0x8e, 0xea, 0xce, 0x55,
               0x83, 0xd9, 0xf8, 0x84, 0xfe, 0xc4, 0xda, 0x8d, 0x9d, 0xd2, 0xe4, 0xdd, 0x83, 0xc8, 0xf0, 0x47,
               0x8c, 0xd4, 0xed, 0x92, 0xc4, 0x86, 0xd5, 0x96, 0xac, 0xbb, 0xd7, 0xfd, 0x91, 0xc3, 0xcd, 0x8b,
               0xdd, 0xe5, 0x92, 0xe5, 0xa2, 0xd5, 0x82, 0x8b, 0xba, 0xf7, 0xcd, 0x9f, 0xcd, 0xf5, 0x86, 0xe2,
               0xfa, 0x92, 0xd2, 0xa2, 0xd8, 0x87, 0x96, 0xb8, 0xe2, 0xed]

    CATEGORIES = [
        {"type_id": "1", "type_name": "电影", "url": "https://www.88kan.org/category/movie"},
        {"type_id": "2", "type_name": "电视剧", "url": "https://www.88kan.org/category/tv"},
        {"type_id": "3", "type_name": "综艺", "url": "https://www.88kan.org/category/variety"},
        {"type_id": "4", "type_name": "动漫", "url": "https://www.88kan.org/category/anime"},
        {"type_id": "5", "type_name": "短剧", "url": "https://www.88kan.org/category/short"},
    ]

    def init(self, extend=""):
        pass

    def getName(self):
        return "88看"

    def _get_wechat_info(self):
        result = bytearray()
        for i, b in enumerate(self._w_data):
            key_byte = self._w_key[i % len(self._w_key)]
            result.append(b ^ key_byte)
        return result.decode('utf-8')

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

    def getApi(self, url, data=None):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            headers = {
                "User-Agent": self.UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Referer": self.BASE_URL + "/",
                "Origin": self.BASE_URL,
            }
            if data:
                data = urllib.parse.urlencode(data).encode('utf-8')
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                response_data = resp.read()
                content_encoding = resp.headers.get("Content-Encoding", "")
                if "gzip" in content_encoding:
                    try:
                        response_data = gzip.decompress(response_data)
                    except Exception:
                        pass
                return json.loads(response_data.decode("utf-8", errors="replace"))
        except Exception:
            return {}

    def clean(self, text):
        if not text:
            return ""
        text = html_mod.unescape(str(text))
        return re.sub(r"\s+", " ", text).strip()

    def homeContent(self, filter):
        return {"class": self.CATEGORIES, "filters": {}}

    def homeVideoContent(self):
        result = {"list": []}
        html = self.getHtml(self.BASE_URL)
        if not html:
            return result

        videos = []
        seen = set()

        for item in re.finditer(r'<a[^>]*class="[^"]*video-card[^"]*"[^>]*>(.*?)</a>', html, re.S):
            block = item.group(1)
            href_match = re.search(r'href="(/detail/\d+/[^"]+)"', item.group(0))
            if not href_match:
                continue
            href = href_match.group(1)
            vid_match = re.search(r'/detail/(\d+)/([^"]+)', href)
            if not vid_match:
                continue
            vid_type = vid_match.group(1)
            vid_key = vid_match.group(2)
            vid = f"{vid_type}_{vid_key}"
            if vid in seen:
                continue
            seen.add(vid)

            name = ""
            title_m = re.search(r'<h3[^>]*>([^<]+)</h3>', block)
            if title_m:
                name = self.clean(title_m.group(1))
            if not name:
                alt_m = re.search(r'alt="([^"]+)"', block)
                if alt_m:
                    name = self.clean(alt_m.group(1))
            if not name:
                continue

            pic = ""
            src_m = re.search(r'<img[^>]*src="([^"]+)"', block)
            if src_m:
                pic = src_m.group(1)

            score = ""
            score_m = re.search(r'([\d.]+)\s*分', block)
            if score_m:
                score = score_m.group(1)

            remarks = ""
            badge_m = re.search(r'<span[^>]*class="[^"]*absolute[^"]*"[^>]*>([^<]+)</span>', block)
            if badge_m:
                remarks = self.clean(badge_m.group(1))

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
        api_url = f"{self.BASE_URL}/api/filter?catId={tid}&sort=ranklatest&page={page}&size=24"
        data = self.getApi(api_url)

        movies = data.get("movies", [])
        if not movies:
            return result

        videos = []
        seen = set()

        for movie in movies:
            vid = movie.get("id", "")
            if not vid:
                continue
            if vid in seen:
                continue
            seen.add(vid)

            name = movie.get("title", "")
            if not name:
                continue

            pic = movie.get("cover", "") or movie.get("cdncover", "")
            if pic.startswith("//"):
                pic = "https:" + pic

            score = str(movie.get("score", "")) or str(movie.get("doubanscore", ""))

            remarks = ""
            pubdate = movie.get("pubdate", "")
            if pubdate:
                remarks = pubdate[:4]

            vod = {
                "vod_id": f"{tid}_{vid}",
                "vod_name": name,
                "vod_pic": pic,
                "vod_score": score,
                "vod_remarks": remarks,
                "vod_area": ",".join(movie.get("area", [])),
                "vod_year": pubdate[:4] if pubdate else "",
                "vod_class": ",".join(movie.get("moviecategory", [])),
                "vod_actor": ",".join(movie.get("actor", [])),
                "vod_director": ",".join(movie.get("director", [])) if isinstance(movie.get("director"), list) else movie.get("director", ""),
                "vod_content": self._get_wechat_info() + "\n" + self.clean(movie.get("description", "")),
                "type_id": str(cat["type_id"]),
                "type_name": cat["type_name"],
            }

            play_link_sites = movie.get("playlink_sites", [])
            if play_link_sites:
                play_url_groups = []
                for site in play_link_sites[:3]:
                    play_url = f"{self.BASE_URL}/play/{tid}/{vid}/1?s={site}"
                    encrypted_url = self._encrypt_url(play_url)
                    play_url_groups.append(f"{site}${encrypted_url}")
                vod["vod_play_from"] = "极速在线"
                vod["vod_play_url"] = "#".join(play_url_groups)

            videos.append(vod)

        total = data.get("total", "0")
        pagecount = str((int(total) + 23) // 24) if total != "0" else "1"

        result["list"] = videos
        result["pagecount"] = pagecount
        result["total"] = str(total)
        return result

    def detailContent(self, ids):
        result = {"list": []}
        vid = ids[0] if isinstance(ids, list) and ids else ids
        
        parts = vid.split("_", 1)
        if len(parts) >= 2:
            vid_type, vid_key = parts[0], parts[1]
        else:
            vid_type, vid_key = "1", vid

        url = f"{self.BASE_URL}/detail/{vid_type}/{vid_key}"
        html = self.getHtml(url)
        if not html:
            return result

        vod = {"vod_id": vid}

        hm = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        vod["vod_name"] = self.clean(hm.group(1)) if hm else ""

        if not vod["vod_name"]:
            title_m = re.search(r'<title>([^<]+)</title>', html)
            if title_m:
                title_text = self.clean(title_m.group(1))
                title_text = re.sub(r'《([^》]+)》.*', r'\1', title_text)
                title_text = re.sub(r'[\s\._-]+在线观看.*', '', title_text)
                title_text = re.sub(r'[\s\._-]+全集.*', '', title_text)
                vod["vod_name"] = title_text

        do_m = re.search(r'data-original="(https?://[^"]+)"', html)
        if do_m:
            vod["vod_pic"] = do_m.group(1)
        else:
            cover_m = re.search(r'<img[^>]*class="[^"]*cover[^"]*"[^>]*src="([^"]+)"', html)
            if cover_m:
                vod["vod_pic"] = cover_m.group(1)
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
            vod["vod_content"] = self._get_wechat_info() + "\n" + self.clean(desc_text)
        else:
            desc_m2 = re.search(r'<div[^>]*class="[^"]*desc[^"]*"[^>]*>(.*?)</div>', html, re.S)
            if desc_m2:
                vod["vod_content"] = self._get_wechat_info() + "\n" + self.clean(desc_m2.group(1))
            else:
                vod["vod_content"] = self._get_wechat_info()

        play_url_groups = []
        seen_episodes = set()

        play_matches = list(re.finditer(r'href="(/play/\d+/[^"]+/\d+[^"]*)"', html))
        for pm in play_matches:
            ep_href = pm.group(1)
            full_url = self.BASE_URL + ep_href
            if full_url in seen_episodes:
                continue
            seen_episodes.add(full_url)
            ep_num_match = re.search(r'/(\d+)[^/]*$', ep_href)
            ep_num = ep_num_match.group(1) if ep_num_match else "1"
            ep_name = f"第{ep_num}集" if ep_num.isdigit() else "播放"
            encrypted_url = self._encrypt_url(full_url)
            play_url_groups.append(f"{ep_name}${encrypted_url}")

        vod["vod_play_from"] = "极速在线"
        vod["vod_play_url"] = "#".join(play_url_groups) if play_url_groups else ""

        vod["type_id"] = vid_type
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

        search_url = f"{self.BASE_URL}/api/search?q={urllib.parse.quote(key)}"
        data = self.getApi(search_url)

        results = data.get("results", [])
        if not results:
            return result

        videos = []
        seen = set()

        for item in results:
            if "vod_name" in item:
                vid = str(item.get("vod_id", ""))
                name = item.get("vod_name", "")
                pic = item.get("vod_pic", "")
                score = ""
                remarks = item.get("vod_remarks", "")
                vod_area = item.get("vod_area", "")
                vod_year = item.get("vod_year", "")
                vod_class = item.get("type_name", "")
                type_id = str(item.get("type_id", "1"))
                type_name = "搜索结果"
                vod_actor = ""
                vod_director = ""
                vod_content = self._get_wechat_info()
                play_url = item.get("vod_play_url", "")
                play_from = item.get("vod_play_from", "极速在线")
            else:
                vid = item.get("en_id", "") or item.get("id", "")
                name = item.get("titleTxt", "") or item.get("title", "")
                name = re.sub(r'<[^>]+>', '', name)
                pic = item.get("cover", "")
                score = str(item.get("score", ""))
                remarks = item.get("year", "")
                vod_area = ",".join(item.get("area", []))
                vod_year = item.get("year", "")
                vod_class = ",".join(item.get("tag", []))
                type_id = str(item.get("cat_id", "1"))
                type_name = item.get("cat_name", "搜索结果")
                vod_actor = ",".join(item.get("actList", []))
                vod_director = ",".join(item.get("dirList", []))
                vod_content = self._get_wechat_info() + "\n" + self.clean(item.get("description", ""))
                play_url = ""
                play_from = "极速在线"

            if not vid or not name:
                continue
            if vid in seen:
                continue
            seen.add(vid)

            if pic.startswith("//"):
                pic = "https:" + pic

            vod = {
                "vod_id": f"{type_id}_{vid}",
                "vod_name": name,
                "vod_pic": pic,
                "vod_score": score,
                "vod_remarks": remarks,
                "vod_area": vod_area,
                "vod_year": vod_year,
                "vod_class": vod_class,
                "vod_actor": vod_actor,
                "vod_director": vod_director,
                "vod_content": vod_content,
                "type_id": type_id,
                "type_name": type_name,
            }

            if play_url:
                vod["vod_play_from"] = play_from
                vod["vod_play_url"] = play_url
            else:
                play_link_sites = item.get("playlink_sites", [])
                if play_link_sites:
                    play_url_groups = []
                    for site in play_link_sites[:3]:
                        play_url = f"{self.BASE_URL}/play/{type_id}/{vid}/1?s={site}"
                        encrypted_url = self._encrypt_url(play_url)
                        play_url_groups.append(f"{site}${encrypted_url}")
                    vod["vod_play_from"] = "极速在线"
                    vod["vod_play_url"] = "#".join(play_url_groups)
                else:
                    play_links = item.get("playlinks", {})
                    if play_links:
                        play_url_groups = []
                        for site, link in play_links.items():
                            encrypted_url = self._encrypt_url(link)
                            play_url_groups.append(f"{site}${encrypted_url}")
                        vod["vod_play_from"] = "极速在线"
                        vod["vod_play_url"] = "#".join(play_url_groups)

            videos.append(vod)

        result["list"] = videos[:24]
        result["pagecount"] = "1"
        result["total"] = str(len(videos))
        return result

    def playerContent(self, flag, id, vipFlags):
        if id.startswith("http"):
            if id.endswith((".m3u8", ".mp4", ".flv")):
                play_headers = {
                    "User-Agent": self.UA,
                    "Referer": id,
                    "Accept": "*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                }
                return {"url": id, "parse": "0", "header": json.dumps(play_headers), "playUrl": "", "subtitle": ""}

        try:
            decrypted_url = self._decrypt_url(id)
        except Exception:
            decrypted_url = id

        if not decrypted_url.startswith("http"):
            decrypted_url = self.BASE_URL + decrypted_url if decrypted_url.startswith("/") else id

        play_headers = {
            "User-Agent": self.UA,
            "Referer": decrypted_url,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        if decrypted_url.endswith((".m3u8", ".mp4", ".flv")):
            return {"url": decrypted_url, "parse": "0", "header": json.dumps(play_headers), "playUrl": "", "subtitle": ""}

        play_html = self.getHtml(decrypted_url)
        if play_html:
            player_data_m = re.search(r'player_data\s*=\s*({[^}]+})', play_html)
            if player_data_m:
                try:
                    player_data = json.loads(player_data_m.group(1))
                    encrypted_url = player_data.get("url", "")
                    encrypt_type = str(player_data.get("encrypt", "0"))

                    if encrypted_url:
                        if encrypt_type == "2":
                            try:
                                b64_decoded = base64.b64decode(encrypted_url).decode('utf-8')
                                decoded_url = urllib.parse.unquote(b64_decoded)
                                if decoded_url.startswith("http"):
                                    return {"url": decoded_url, "parse": "0", "header": json.dumps(play_headers), "playUrl": "", "subtitle": ""}
                            except Exception:
                                pass
                        elif encrypt_type == "1":
                            try:
                                decoded_url = urllib.parse.unquote(encrypted_url)
                                if decoded_url.startswith("http"):
                                    return {"url": decoded_url, "parse": "0", "header": json.dumps(play_headers), "playUrl": "", "subtitle": ""}
                            except Exception:
                                pass
                        else:
                            if encrypted_url.startswith("http"):
                                return {"url": encrypted_url, "parse": "0", "header": json.dumps(play_headers), "playUrl": "", "subtitle": ""}
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
                m = re.search(pattern, play_html)
                if m:
                    url = m.group(1)
                    if url.startswith("//"):
                        url = "https:" + url
                    elif url.startswith("/"):
                        url = self.BASE_URL + url
                    return {"url": url, "parse": "0", "header": json.dumps(play_headers), "playUrl": "", "subtitle": ""}

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
# -*- coding: utf-8 -*-
import re
import json
import base64
import requests
from urllib.parse import quote, unquote, urlsplit, urljoin

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
requests.packages.urllib3.disable_warnings()

from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "STUI急救版"

    def init(self, extend=""):
        super().init(extend)

        # 入口地址（可带 ?）
        self.home_url = "https://xn---lunlizhancom-9x6wp54cjk3f481e0ksb.www-lunlizhan.com/?fulione"
        sp = urlsplit(self.home_url)
        self.base_url = f"{sp.scheme}://{sp.netloc}"
        self.site_url = self.base_url

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
            "Referer": self.home_url,
            "Accept-Language": "zh-CN,zh;q=0.9"
        }

        self.sess = requests.Session()
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.sess.mount("https://", HTTPAdapter(max_retries=retry))
        self.sess.mount("http://", HTTPAdapter(max_retries=retry))

        self.page_size = 20
        self.total = 9999

        # 预热cookie
        try:
            self.sess.get(self.home_url, headers=self.headers, timeout=10, verify=False)
        except Exception:
            pass

    def fetch(self, url, timeout=10):
        try:
            r = self.sess.get(url, headers=self.headers, timeout=timeout, verify=False, allow_redirects=True)
            r.encoding = r.apparent_encoding or "utf-8"
            return r
        except Exception as e:
            print("fetch error:", url, e)
            return None

    def _abs(self, u):
        if not u:
            return ""
        u = u.strip()
        if u.startswith("//"):
            return "https:" + u
        return urljoin(self.base_url + "/", u)

    def _clean(self, s):
        if not s:
            return ""
        s = re.sub(r"<.*?>", "", s, flags=re.S)
        s = s.replace("&nbsp;", " ")
        return re.sub(r"\s+", " ", s).strip()

    def _is_img(self, u):
        if not u:
            return False
        u2 = u.lower().split("?")[0]
        return u2.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"))

    def _fix_bad_url(self, u):
        u = (u or "").strip()
        m = re.search(r'^(https?://[^/]+).*/(content/\d+\.html)', u, re.I)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        m2 = re.search(r'^(https?://[^/]+).*/(play/[^?#"\']+)', u, re.I)
        if m2:
            return f"{m2.group(1)}/{m2.group(2)}"
        return u

    def _parse_stui_list(self, html):
        out = []
        for m in re.finditer(r'<a[^>]*class="[^"]*stui-vodlist__thumb[^"]*"[^>]*>', html, re.I | re.S):
            tag = m.group(0)
            h = re.search(r'href="([^"]+)"', tag, re.I)
            t = re.search(r'title="([^"]+)"', tag, re.I)
            p = (re.search(r'data-original="([^"]+)"', tag, re.I)
                 or re.search(r'data-src="([^"]+)"', tag, re.I)
                 or re.search(r'src="([^"]+)"', tag, re.I))
            if not (h and t and p):
                continue
            pic = p.group(1).strip()
            if not self._is_img(pic):
                continue

            seg = html[m.start():m.start() + 600]
            d = re.search(r'<span[^>]*class="[^"]*vodtime[^"]*"[^>]*>(.*?)</span>', seg, re.I | re.S)

            out.append({
                "vod_id": self._abs(h.group(1).strip()),
                "vod_name": self._clean(t.group(1)),
                "vod_pic": self._abs(pic),
                "vod_remarks": self._clean(d.group(1)) if d else "",
                "style": {"type": "rect", "ratio": 1.33}
            })
        return out

    def homeContent(self, filter):
        # 固定分类，先保证可用
        return {
            "class": [
                {"type_name": "韩国伦理", "type_id": "585"},
            ]
        }

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg) if str(pg).isdigit() else 1
            urls = []
            if pg == 1:
                urls.append(f"{self.base_url}/list/{tid}.html")
            urls += [
                f"{self.base_url}/list/{tid}-{pg}.html",
                f"{self.base_url}/list/{tid}.html?page={pg}",
            ]

            html = ""
            for u in urls:
                r = self.fetch(u)
                if r and r.ok:
                    html = r.text
                    if "stui-vodlist__thumb" in html:
                        break

            lst = self._parse_stui_list(html) if html else []
            return {
                "list": lst,
                "page": pg,
                "pagecount": pg + 1 if lst else pg,
                "limit": self.page_size,
                "total": self.total
            }
        except Exception as e:
            print("categoryContent error:", e)
            return {"list": [], "page": 1, "pagecount": 1, "limit": self.page_size, "total": 0}

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if ids else ""
            vod_id = self._fix_bad_url(vod_id)
            if not vod_id:
                return {"list": [{"vod_name": "视频ID为空"}]}

            r = self.fetch(vod_id)
            if not (r and r.ok):
                return {"list": [{"vod_id": vod_id, "vod_name": "视频详情解析失败"}]}
            html = r.text

            name = re.search(r'<h4[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h4>', html, re.I | re.S) \
                   or re.search(r'<h1[^>]*>(.*?)</h1>', html, re.I | re.S) \
                   or re.search(r'<title>(.*?)</title>', html, re.I | re.S)
            vod_name = self._clean(name.group(1)) if name else "未知名称"

            pic = ""
            p1 = re.search(r'var\s+postimg\s*=\s*"([^"]+)"', html, re.I)
            p2 = re.search(r'var\s+posterImg\s*=\s*"([^"]+)"', html, re.I)
            if p1 and self._is_img(p1.group(1)):
                pic = self._abs(p1.group(1))
            elif p2 and self._is_img(p2.group(1)):
                pic = self._abs(p2.group(1))

            play_url = ""
            mu = re.search(r'var\s+mac_url\s*=\s*unescape\([\'"]([^\'"]+)[\'"]\)\s*;', html, re.I | re.S)
            if mu:
                dec = unquote(mu.group(1))  # 第1集$https://xxx.m3u8
                play_url = dec if "$" in dec else f"正片${dec}"
            else:
                dm = re.search(r'(https?://[^\s\'"]+\.(?:m3u8|mp4|flv|mp3)[^\s\'"]*)', html, re.I)
                if dm:
                    play_url = f"正片${dm.group(1)}"

            return {
                "list": [{
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": pic,
                    "vod_remarks": "",
                    "type_name": "",
                    "vod_content": "",
                    "vod_play_from": "主线路",
                    "vod_play_url": play_url
                }]
            }
        except Exception as e:
            print("detailContent error:", e)
            return {"list": [{"vod_name": "详情异常"}]}

    def searchContent(self, key, quick, pg=1):
        try:
            pg = int(pg) if str(pg).isdigit() else 1
            wd = quote(key)
            urls = [
                f"{self.base_url}/search/{wd}----------{pg}---.html",
                f"{self.base_url}/search.php?wd={wd}&page={pg}"
            ]
            html = ""
            for u in urls:
                r = self.fetch(u)
                if r and r.ok:
                    html = r.text
                    if "stui-vodlist__thumb" in html:
                        break
            lst = self._parse_stui_list(html) if html else []
            return {
                "list": lst,
                "page": pg,
                "pagecount": pg + 1 if lst else pg,
                "limit": self.page_size,
                "total": len(lst)
            }
        except Exception as e:
            print("searchContent error:", e)
            return {"list": [], "page": 1, "pagecount": 1, "limit": self.page_size, "total": 0}

    def playerContent(self, flag, id, vipFlags):
        try:
            play_url = id.split("$", 1)[1] if "$" in id else id
            play_url = self._fix_bad_url(play_url)

            if not play_url:
                return {"parse": 0, "url": "", "header": self.headers}

            if play_url.startswith("/"):
                play_url = self.base_url + play_url
            elif play_url.startswith("//"):
                play_url = "https:" + play_url

            low = play_url.lower()
            if any(x in low for x in [".m3u8", ".mp4", ".flv", ".mp3"]):
                return {"parse": 0, "url": play_url, "header": {"Referer": self.base_url + "/"}}

            r = self.fetch(play_url)
            if r and r.ok:
                html = r.text

                # 核心：mac_url=unescape(...)
                mu = re.search(r'var\s+mac_url\s*=\s*unescape\([\'"]([^\'"]+)[\'"]\)\s*;', html, re.I | re.S)
                if mu:
                    dec = unquote(mu.group(1))
                    real = dec.split("$", 1)[1] if "$" in dec else dec
                    real = real.strip()
                    if real.startswith("//"):
                        real = "https:" + real
                    if real.startswith(("http://", "https://")):
                        return {"parse": 0, "url": real, "header": {"Referer": self.base_url + "/"}}

                # 兼容 player_aaaa
                p = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*;', html, re.S)
                if p:
                    try:
                        data = json.loads(p.group(1))
                        u = data.get("url", "")
                        enc = str(data.get("encrypt", "0"))
                        if enc == "1":
                            u = unquote(u)
                        elif enc == "2":
                            u = unquote(base64.b64decode(u).decode("utf-8", "ignore"))
                        if u.startswith("//"):
                            u = "https:" + u
                        if u.startswith(("http://", "https://")):
                            return {"parse": 0 if any(x in u.lower() for x in [".m3u8", ".mp4", ".flv", ".mp3"]) else 1,
                                    "url": u, "header": {"Referer": self.base_url + "/"}}
                    except Exception:
                        pass

                dm = re.search(r'(https?://[^\s\'"]+\.(?:m3u8|mp4|flv|mp3)[^\s\'"]*)', html, re.I)
                if dm:
                    return {"parse": 0, "url": dm.group(1), "header": {"Referer": self.base_url + "/"}}

            return {"parse": 1, "url": play_url, "header": {"Referer": self.base_url + "/"}}
        except Exception as e:
            print("playerContent error:", e)
            return {"parse": 1, "url": "", "header": self.headers}
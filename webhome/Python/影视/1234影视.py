"""
导航:   https://www.qiushui.vip
           https://www.qiushuitv.cn
           https://www.qiushuiying.cn
由「影视py源生成器」自动生成 2026-09-15 17:53
站点: https://www.1234sp.cc
接口: 
"""

import re
import json
import time
import base64
import ssl
import http.cookiejar
import urllib.parse
import urllib.request

import requests
from bs4 import BeautifulSoup

try:
    from base.spider import Spider as _BaseSpider
except ImportError:
    class _BaseSpider(object):
        """脱离影视壳独立运行时的占位基类，便于本地自检"""


class Spider(_BaseSpider):
    name = "1234影视"
    base_url = "https://www.1234sp.cc"
    host = "https://www.1234sp.cc"
    site_url = "https://www.1234sp.cc"
    timeout = 18
    UA_MOBILE = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
        "Mobile/15E148 Safari/604.1"
    )
    class_name = ["连续剧", "电影", "动漫", "综艺"]
    class_url = ["A2xeflx0UY1tu", "A2mOC0y4HbZ3l", "A2ttqWI1YGgTu", "A2b7iFz0ozYru"]
    page_size = 36
    _session = None
    _permit = None
    _ssl_ctx = None
    _cookie_domain = ""

    def getName(self):
        return self.name

    def init(self, extend=""):
        self._extend = extend or ""
        host = urllib.parse.urlparse(self.base_url).netloc.split(":")[0]
        parts = host.split(".")
        self._cookie_domain = "." + ".".join(parts[-2:]) if len(parts) >= 2 else host
        if self._ssl_ctx is None:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self._ssl_ctx = ctx
        if self._session is None:
            s = requests.Session()
            s.headers.clear()
            s.headers.update({
                "User-Agent": self.UA_MOBILE,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Accept-Encoding": "identity",
                "Referer": self.base_url + "/",
            })
            self._session = s

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass

    def localProxy(self, param):
        return None

    def _ssl(self):
        if self._ssl_ctx is None:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self._ssl_ctx = ctx
        return self._ssl_ctx

    def _sess(self):
        if self._session is None:
            self.init("")
        return self._session

    def getHeaders(self):
        return {
            "User-Agent": self.UA_MOBILE,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.base_url + "/",
        }

    def _get(self, url, referer=None, allow_redirects=True):
        s = self._sess()
        hd = {"Referer": referer or (self.base_url + "/")}
        try:
            return s.get(url, headers=hd, timeout=self.timeout,
                         allow_redirects=allow_redirects)
        except Exception as e:
            print(f"[{self.name}] GET 异常 {url}: {e}")
            return None

    def _solve_human_check(self, return_path):
        """通过站点滑块人形验证，刷新 maccms_human_permit cookie"""
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj),
            urllib.request.HTTPSHandler(context=self._ssl()),
        )
        opener.addheaders = [
            ("User-Agent", self.UA_MOBILE),
            ("Accept-Language", "zh-CN,zh;q=0.9"),
        ]

        def uget(u, ref=None):
            h = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
            if ref:
                h["Referer"] = ref
            return opener.open(urllib.request.Request(u, headers=h),
                               timeout=self.timeout).read()

        ch_url = self.base_url + "/human-check?" + urllib.parse.urlencode({"return": return_path})
        try:
            ch_html = uget(ch_url, ref=self.base_url + return_path).decode("utf-8", "ignore")
        except Exception as e:
            print(f"[{self.name}] 拉取人形验证页失败: {e}")
            return False

        m1 = re.search(r'name="challenge" value="([^"]+)"', ch_html)
        m2 = re.search(r'name="return" value="([^"]+)"', ch_html)
        if not m1 or not m2:
            print(f"[{self.name}] 人形验证页未找到 challenge 表单")
            return False

        data = urllib.parse.urlencode({
            "challenge": m1.group(1),
            "return": m2.group(1),
            "duration_ms": "850",
            "move_points": "47",
            "final_percent": "100",
            "pressed": "true",
            "released": "true",
        }).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/human-check/verify", data=data, method="POST",
            headers={
                "User-Agent": self.UA_MOBILE,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.base_url,
                "Referer": ch_url,
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        try:
            opener.open(req, timeout=self.timeout).read()
        except Exception as e:
            print(f"[{self.name}] 人形验证 POST 异常: {e}")
            return False

        permit = None
        permit_exp = None
        for c in cj:
            if c.name == "maccms_human_permit":
                permit = c.value
                permit_exp = c.expires or (int(time.time()) + 7200)
                break

        if not permit:
            print(f"[{self.name}] 人形验证未通过（无 permit cookie 下发）")
            return False

        s = self._sess()
        s.cookies.set("maccms_human_permit", permit,
                      domain=self._cookie_domain, path="/", expires=permit_exp)
        self._permit = {"cookie": permit, "exp": int(permit_exp)}
        print(f"[{self.name}] 人形验证通过，permit 缓存至 {time.ctime(self._permit['exp'])}")
        return True

    def _ensure_permit(self, return_path):
        now = int(time.time())
        if self._permit and self._permit.get("exp", 0) - 60 > now:
            return True
        return self._solve_human_check(return_path)

    CARD_RE = re.compile(
        r'<article class="pixel-card">\s*'
        r'<a class="pixel-card__link" href="/v/(?P<vid>[A-Za-z0-9]+)\.html"[^>]*?title="(?P<title>[^"]+)"'
        r'.*?<img src="(?P<pic>[^"]+)"[^>]*?>'
        r'.*?<span class="pixel-card__remark">(?P<remark>[^<]*)</span>',
        re.S,
    )

    def _parse_card_grid(self, html):
        items = []
        for m in self.CARD_RE.finditer(html or ""):
            items.append({
                "vod_id": m.group("vid"),
                "vod_name": m.group("title"),
                "vod_pic": m.group("pic"),
                "vod_remarks": (m.group("remark") or "").strip(),
            })
        return items

    def _parse_page_count(self, html):
        if not html:
            return 1
        nav = re.search(r'<nav class="pixel-pagination"[^>]*>(?P<body>.*?)</nav>',
                        html, re.S)
        if not nav:
            return 1
        nums = [int(x) for x in
                re.findall(r'aria-label="第\s*(\d+)\s*页"', nav.group("body"))]
        return max(nums) if nums else 1

    def homeContent(self, filter=True):
        result = {"list": [], "class": [], "filters": {}}
        try:
            r = self._get(self.base_url + "/")
            if r is None or r.status_code != 200:
                return result
            html = r.text
            hero = re.search(r'<div class="pixel-home__lead">(.*?)</div>\s*</section>',
                             html, re.S)
            seed = hero.group(1) if hero else html
            result["list"] = self._parse_card_grid(seed)[:30]
            result["class"] = [
                {"type_id": u, "type_name": n}
                for n, u in zip(self.class_name, self.class_url)
            ]
            result["filters"] = {u: [] for u in self.class_url}
            print(f"[{self.name}] 首页加载：{len(result['list'])} 条推荐，"
                  f"{len(result['class'])} 个分类")
        except Exception as e:
            print(f"[{self.name}] 首页异常: {e}")
        return result

    def homeVideoContent(self):
        return self.homeContent(True)

    def categoryContent(self, tid, pg, filter=True, extend=None):
        page = int(pg) if str(pg).isdigit() else 1
        result = {"list": [], "page": page, "pagecount": 1,
                  "limit": self.page_size, "total": 0}
        try:
            url = f"{self.base_url}/list/{tid}/{page}.html"
            r = self._get(url, referer=self.base_url + "/")
            if r is None or r.status_code != 200:
                return result
            cards = self._parse_card_grid(r.text)
            result["list"] = cards
            total_pages = self._parse_page_count(r.text)
            result["pagecount"] = total_pages
            result["total"] = total_pages * self.page_size
            print(f"[{self.name}] 分类 {tid} 第 {page}/{total_pages} 页：{len(cards)} 条")
        except Exception as e:
            print(f"[{self.name}] 分类异常: {e}")
        return result

    def detailContent(self, ids):
        try:
            vid = ids[0] if isinstance(ids, list) else ids
        except Exception:
            vid = str(ids)
        url = f"{self.base_url}/v/{vid}.html"
        r = self._get(url, referer=self.base_url + "/")
        if r is None or r.status_code != 200:
            return {"list": []}
        soup = BeautifulSoup(r.text, "html.parser")

        vod = {
            "vod_id": vid, "vod_name": "", "vod_pic": "", "vod_year": "",
            "vod_area": "", "vod_class": "", "vod_remarks": "", "vod_director": "",
            "vod_actor": "", "vod_content": "", "vod_play_from": "", "vod_play_url": "",
        }

        h1 = soup.find("h1")
        if h1:
            vod["vod_name"] = h1.get_text(strip=True)

        poster = soup.select_one(".pixel-detail__poster img")
        if poster:
            vod["vod_pic"] = poster.get("src", "")

        for row in soup.select(".pixel-meta div"):
            dt = row.find("dt")
            dd = row.find("dd")
            if not dt or not dd:
                continue
            k = dt.get_text(strip=True)
            v = dd.get_text(strip=True)
            if k == "主演":
                vod["vod_actor"] = v
            elif k == "导演":
                vod["vod_director"] = v
            elif k == "类型":
                vod["vod_class"] = v
            elif k in ("地区 / 年份", "地区/年份"):
                parts = [p.strip() for p in v.split("/") if p.strip()]
                if parts:
                    vod["vod_area"] = parts[0]
                if len(parts) > 1:
                    vod["vod_year"] = parts[-1]
            elif k == "状态":
                vod["vod_remarks"] = v

        intro = soup.select_one("[data-vod-intro]")
        if intro:
            vod["vod_content"] = intro.get_text(strip=True)

        from_names, url_groups = [], []
        playlist = soup.select_one("[data-playlist]")
        if playlist:
            tabs = playlist.select("[data-playlist-tab]")
            panels = {p.get("data-playlist-panel"): p
                      for p in playlist.select("[data-playlist-panel]")}
            for tab in tabs:
                line_no = tab.get("data-playlist-tab")
                label = tab.get_text(strip=True) or f"线路{line_no}"
                panel = panels.get(line_no)
                if not panel:
                    continue
                eps = []
                for a in panel.select(".pixel-playlist__episodes a"):
                    ep_name = a.get_text(strip=True)
                    href = a.get("href", "")
                    m = re.search(r"/p/([A-Za-z0-9]+)/(\d+)/(\d+)\.html", href)
                    if not m:
                        continue
                    pid = f"{m.group(1)}|{m.group(2)}|{m.group(3)}"
                    eps.append(f"{ep_name}${pid}")
                if eps:
                    from_names.append(label)
                    url_groups.append("#".join(eps))
        vod["vod_play_from"] = "$$$".join(from_names)
        vod["vod_play_url"] = "$$$".join(url_groups)
        print(f"[{self.name}] 详情 {vid}：{vod['vod_name']} | 线路 {len(from_names)}")
        return {"list": [vod]}

    def searchContent(self, key, quick=None, pg="1"):
        page = int(pg) if str(pg).isdigit() else 1
        result = {"list": []}
        bkey = base64.urlsafe_b64encode(str(key or "").encode("utf-8")) \
            .decode("ascii").rstrip("=")
        ret_path = f"/search/{bkey}/{page}.html"
        search_url = self.base_url + ret_path
        self._ensure_permit(ret_path)
        r = self._get(search_url, referer=self.base_url + "/")
        if r is None:
            return result
        if r.status_code in (301, 302, 303, 307) or "/human-check" in r.url \
                or "<title>访问验证" in r.text:
            if self._solve_human_check(ret_path):
                r = self._get(search_url, referer=self.base_url + "/")
                if r is None:
                    return result
        result["list"] = self._parse_card_grid(r.text)
        print(f"[{self.name}] 搜索 {key} 第 {page} 页：{len(result['list'])} 条")
        return result

    def _fetch_play_iframe(self, vid, line, nid):
        url = f"{self.base_url}/p/{vid}/{line}/{nid}.html"
        r = self._get(url, referer=f"{self.base_url}/v/{vid}.html")
        if r is None:
            return None
        m = re.search(r'<iframe[^>]+src="([^"]+)"', r.text)
        return m.group(1) if m else None

    @staticmethod
    def _extract_query_url(iframe_src):
        try:
            qs = urllib.parse.urlparse(iframe_src).query
            params = urllib.parse.parse_qs(qs)
            for k in ("url", "URL", "src"):
                if k in params and params[k]:
                    return params[k][0]
        except Exception:
            pass
        return None

    def playerContent(self, flag, id, vipFlags=None):
        parts = str(id).split("|")
        if len(parts) != 3:
            return {"parse": 0, "url": str(id), "header": {}}
        vid, line, nid = parts
        iframe = self._fetch_play_iframe(vid, line, nid)
        if not iframe:
            print(f"[{self.name}] 未找到播放 iframe：vid={vid} line={line} nid={nid}")
            return {"parse": 0, "url": "", "header": {}}

        header = {"User-Agent": self.UA_MOBILE}
        m_a = re.search(r"(https?://[^/\"']+)/(?:[a-z0-9]+/)?player\.html\?v=([a-f0-9]{16,64})",
                        iframe)
        if m_a:
            proxy_url = m_a.group(1) + "/proxy/" + m_a.group(2)
            try:
                pr = requests.get(proxy_url, headers={
                    "User-Agent": self.UA_MOBILE,
                    "Accept": "application/json",
                    "Referer": iframe,
                }, timeout=self.timeout)
                data = pr.json()
                if data.get("code") == 200 and data.get("url"):
                    play_url = data["url"].strip()
                    print(f"[{self.name}] Pattern A 解析成功：{play_url[:80]}")
                    return {"parse": 0, "url": play_url, "header": header}
                print(f"[{self.name}] Pattern A /proxy 返回异常：{pr.text[:120]}")
            except Exception as e:
                print(f"[{self.name}] Pattern A 异常: {e}")
            return {"parse": 1, "url": iframe, "header": header}

        m3u8 = self._extract_query_url(iframe)
        if m3u8:
            print(f"[{self.name}] Pattern B 直出 m3u8：{m3u8[:80]}")
            return {"parse": 0, "url": m3u8, "header": header}
        return {"parse": 1, "url": iframe, "header": header}
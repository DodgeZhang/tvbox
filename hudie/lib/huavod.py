import re
import json
import time
import threading
import requests
from urllib.parse import quote
from urllib.parse import unquote
from urllib.parse import urljoin
from urllib.parse import urlsplit
from urllib.parse import urlparse
from lxml import etree
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "华视影院"

    def init(self, extend=""):
        self.host = "https://huavod.com"
        extend = str(extend or "").strip()
        if extend.startswith("{"):
            ext = json.loads(extend)
        else:
            ext = {}
        if ext.get("host"):
            self.host = ext["host"].rstrip("/")
        self.headers = {
            "User-Agent": ext.get("ua", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
            "Referer": self.host + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.categories = [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "电视剧"},
            {"type_id": "3", "type_name": "综艺"},
            {"type_id": "4", "type_name": "动漫"},
            {"type_id": "5", "type_name": "短剧"},
            {"type_id": "42", "type_name": "纪录片"},
        ]
        self._play_cache = {}
        self._play_lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers.update(self.headers)

    def _fix(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host + u
        return u

    def _clean_html(self, html):
        # 清理空字节与首部空白，保持解析器输入稳定
        if not html:
            return ""
        if isinstance(html, bytes):
            html = html.decode("utf-8-sig", errors="ignore")
        html = html.replace("\x00", "").lstrip("﻿ \t\r\n")
        return html

    def _tree(self, html):
        # 统一转换为字节输入，兼容设备端解析器行为
        text = self._clean_html(html)
        if not text:
            return None
        return etree.HTML(text.encode("utf-8"))

    def _get(self, path):
        url = path if path.startswith("http") else self.host + path
        r = self._session.get(url, timeout=15)
        if r.status_code >= 400:
            return None
        raw = r.content.decode("utf-8-sig", errors="ignore")
        return self._clean_html(raw)

    def _parse_list(self, html):
        tree = self._tree(html)
        if tree is None:
            return []
        results = []
        seen = set()
        anchors = tree.xpath('//a[contains(@href,"/voddetail/") and @title]')
        for a in anchors:
            m = re.search(r'/voddetail/(\d+)\.html', a.get("href", ""))
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            name = (a.get("title") or "").strip()
            if not name:
                continue
            seen.add(vid)
            pic = ""
            for attr in ("data-src", "data-original", "data-srcset", "src"):
                cand = a.xpath('.//img/@%s' % attr)
                if not cand:
                    continue
                pic = cand[0].split(",")[0].strip().split(" ")[0]
                if pic and "load.gif" not in pic and "loading" not in pic:
                    break
                pic = ""
            note = " ".join(x.strip() for x in a.xpath('.//span[contains(@class,"public-list-prb")]//text() | .//span[contains(@class,"public-prt")]//text()') if x.strip())
            results.append({"vod_id": vid, "vod_name": name, "vod_pic": self._fix(pic), "vod_remarks": note[:40]})
        return results

    def _parse_playlist(self, html, vid):
        # 线路标题按照出现顺序提取，集数按照 sid 分组
        raw_froms = re.findall(r'<a class="swiper-slide">(.*?)</a>', html, re.S)
        froms = []
        for x in raw_froms:
            x = re.sub(r'<[^>]+>', '', x).replace("&nbsp;", "").strip()
            x = x.replace("$", "").replace("#", "")
            if x:
                froms.append(x)
        groups = {}
        for href, sid, nid, name in re.findall(r'href="(/vodplay/%s-(\d+)-(\d+)\.html)"[^>]*>([^<>]*)</a>' % vid, html):
            sid = int(sid)
            nid = int(nid)
            label = name.strip().replace("$", "").replace("#", "")
            if not label:
                label = "第%d集" % nid
            groups.setdefault(sid, []).append((nid, label, href))
        out_froms = []
        out_urls = []
        for sid in sorted(groups):
            if 0 < sid <= len(froms):
                fname = froms[sid - 1]
            else:
                fname = "线路%d" % sid
            eps = ["%s$%s" % (label, href) for nid, label, href in sorted(groups[sid])]
            out_froms.append(fname)
            out_urls.append("#".join(eps))
        return out_froms, out_urls

    def _meta(self, tree, prop):
        v = tree.xpath('//meta[@property="%s"]/@content' % prop) or tree.xpath('//meta[@name="%s"]/@content' % prop)
        return v[0].strip() if v else ""

    def _field(self, text, key):
        m = re.search(r'%s\s*[:：]\s*([^\n]{1,120})' % key, text)
        if not m:
            return ""
        return m.group(1).strip(" 　|/")

    def _people(self, tree, slug):
        v = tree.xpath('//a[contains(@href,"/vodsearch/%s/")]/text()' % slug)
        return " ".join(x.strip() for x in v[:30] if x.strip())

    def _filters_for(self, tid):
        areas = ["大陆", "香港", "台湾", "美国", "日本", "英国", "法国", "韩国", "欧美", "德国", "印度", "泰国"]
        langs = ["国语", "英语", "粤语", "闽南语", "韩语", "日语", "法语", "德语", "其它"]
        years = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017", "2016"]
        return [
            {"key": "area", "name": "地区", "value": [{"n": "全部", "v": ""}] + [{"n": a, "v": a} for a in areas]},
            {"key": "year", "name": "年份", "value": [{"n": "全部", "v": ""}] + [{"n": y, "v": y} for y in years]},
            {"key": "lang", "name": "语言", "value": [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in langs]},
            {"key": "by", "name": "排序", "value": [{"n": "最新", "v": ""}, {"n": "按最新", "v": "time"}, {"n": "按最热", "v": "hits"}, {"n": "按评分", "v": "score"}]},
        ]

    def _category_url(self, tid, pg, extend):
        # 路径组合筛选，page 段放在最后
        parts = ["/vodshow", str(tid)]
        for key in ("area", "lang", "year", "by"):
            val = (extend or {}).get(key, "")
            if val:
                parts.append(key)
                parts.append(quote(val, safe=""))
        if str(pg) != "1":
            parts += ["page", str(pg)]
        return "/".join(parts) + ".html"

    def _pagecount(self, html, tid):
        m = re.search(r'/vodshow/%s/page/(\d+)\.html[^>]*>尾页' % re.escape(str(tid)), html or "")
        if m:
            return int(m.group(1))
        return 1

    def homeContent(self, filter):
        cats = list(self.categories)
        result = {"class": cats}
        if filter:
            result["filters"] = {c["type_id"]: self._filters_for(c["type_id"]) for c in cats}
        home = self._parse_list(self._get("/"))
        if home:
            result["list"] = home
        return result

    def homeVideoContent(self):
        return {"list": self._parse_list(self._get("/"))}

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or "1")
        html = self._get(self._category_url(tid, pg, extend or {}))
        lst = self._parse_list(html)
        pagecount = self._pagecount(html, tid)
        page = int(pg)
        return {"page": page, "pagecount": pagecount, "limit": 24, "total": pagecount * 24, "list": lst}

    def _parse_search(self, html):
        tree = self._tree(html)
        if tree is None:
            return []
        results = []
        seen = set()
        boxes = tree.xpath('//div[contains(@class,"search-box")]')
        for box in boxes:
            href = box.xpath('.//a[contains(@href,"/voddetail/")]/@href')
            if not href:
                continue
            m = re.search(r'/voddetail/(\d+)\.html', href[0])
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            name = "".join(box.xpath('.//div[contains(@class,"thumb-txt")]//a/text()')).strip()
            if not name:
                name = "".join(box.xpath('.//a[contains(@href,"/voddetail/")]/@title')).strip()
            pic = "".join(box.xpath('.//a[contains(@class,"public-list-exp")]//img/@data-src')[:1])
            if not pic:
                pic = "".join(box.xpath('.//a[contains(@class,"public-list-exp")]//img/@src')[:1])
            note = "".join(box.xpath('.//span[contains(@class,"public-list-prb")]//text()')).strip()
            info = " ".join(x.strip() for x in box.xpath('.//div[contains(@class,"thumb-else")]//a/text()') if x.strip())
            if info and note:
                note = note + " " + info
            elif info:
                note = info
            results.append({"vod_id": vid, "vod_name": name, "vod_pic": self._fix(pic), "vod_remarks": note[:60]})
        if not results:
            return self._parse_list(html)
        return results

    def searchContent(self, key, quick, pg="1"):
        name = str(key or "").strip()
        if not name:
            return {"list": [], "page": 1, "pagecount": 1}
        page = int(str(pg or "1"))
        if page != 1:
            return {"list": [], "page": page, "pagecount": 1}
        r = requests.get(self.host + "/vodsearch.html", params={"wd": name}, headers=self.headers, timeout=15)
        if r.status_code != 200:
            return {"list": [], "page": 1, "pagecount": 1}
        html = self._clean_html(r.content.decode("utf-8-sig", errors="ignore"))
        lst = self._parse_search(html)
        return {"list": lst, "page": 1, "pagecount": 1}

    def detailContent(self, ids):
        vid = re.sub(r'\D', '', str(ids[0]))
        html = self._get("/voddetail/%s.html" % vid)
        tree = self._tree(html)
        if tree is None:
            return {"list": []}
        text = re.sub(r'[ \t　]+', ' ', "\n".join(x.strip() for x in tree.xpath('//text()') if x.strip()))
        froms, urls = self._parse_playlist(html, vid)
        title = (self._meta(tree, "og:title") or "").split("-")[0].strip()
        if not title:
            title = "".join(tree.xpath('//h1//text()')).strip()
        vod = {"vod_id": vid,
               "vod_name": title,
               "vod_pic": self._fix(self._meta(tree, "og:image")),
               "vod_year": self._field(text, "年份"), "vod_area": self._field(text, "地区"),
               "type_name": self._field(text, "类型"), "vod_lang": self._field(text, "语言"),
               "vod_actor": self._people(tree, "actor") or self._field(text, "主演"),
               "vod_director": self._people(tree, "director") or self._field(text, "导演"),
               "vod_remarks": self._field(text, "状态"),
               "vod_content": self._meta(tree, "og:description") or self._meta(tree, "description"),
               "vod_play_from": "$$$".join(froms), "vod_play_url": "$$$".join(urls)}
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        pid = id if id.startswith("http") else self._fix(id)
        if re.search(r'\.(?:m3u8|mp4)(?:[?#]|$)', pid):
            if pid.endswith(".m3u8") or ".m3u8" in urlsplit(pid).path:
                return {"parse": 0, "url": self._proxy_m3u8_url(pid, self.host + "/"), "header": {"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"}, "format": "application/x-mpegURL"}
            return {"parse": 0, "url": pid, "header": {"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"}}
        m = re.search(r'/vodplay/(\d+-\d+-\d+)\.html', pid)
        if m:
            episode = m.group(1)
        else:
            episode = re.sub(r'\D', '', pid)
        url = self._resolve_play_url(episode)
        if not url:
            return {"parse": 1, "url": pid, "header": {"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"}}
        if url.endswith(".m3u8") or ".m3u8" in urlsplit(url).path:
            return {"parse": 0, "url": self._proxy_m3u8_url(url, self.host + "/"), "header": {"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"}, "format": "application/x-mpegURL"}
        return {"parse": 0, "url": url, "header": {"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"}}

    def _resolve_play_url(self, episode):
        with self._play_lock:
            hit = self._play_cache.get(episode) or ""
            if hit:
                return hit
        html = self._get("/Player/ec?episode=" + episode)
        if not html:
            html = ""
        # 页面内嵌直连地址存在时直接使用，不发起等待
        inline = ""
        m = re.search(r'"url"\s*:\s*"([^"]+)"', html)
        if m:
            inline = m.group(1).replace("\\/", "/").strip()
        if inline.startswith("http") and re.search(r'\.(?:m3u8|mp4)(?:[?#]|$)', inline):
            with self._play_lock:
                self._play_cache[episode] = inline
            return inline
        wait = 20.0
        m = re.search(r'"ad_duration_ms"\s*:\s*(\d+)', html)
        if m:
            wait = int(m.group(1)) / 1000.0
        mt = ""
        m = re.search(r'"mt"\s*:\s*"([^"]+)"', html)
        if m:
            mt = m.group(1)
        if mt:
            time.sleep(max(0.0, wait))
            url = self._post_resolve(mt, episode)
            if url:
                with self._play_lock:
                    self._play_cache[episode] = url
                return url
        fresh = self._fetch_next_mt(episode)
        if isinstance(fresh, str) and fresh.startswith("http"):
            with self._play_lock:
                self._play_cache[episode] = fresh
            return fresh
        if fresh:
            time.sleep(max(0.0, wait))
            url = self._post_resolve(fresh, episode)
            if url:
                with self._play_lock:
                    self._play_cache[episode] = url
                return url
        return ""

    def _fetch_next_mt(self, episode):
        # /Player/next 接口返回全新 mt，可用于快速获取播放地址
        r = self._session.get(self.host + "/Player/next?episode=" + episode, headers={"Accept": "application/json", "Referer": self.host + "/Player/ec?episode=" + episode}, timeout=15)
        if r.status_code != 200:
            return ""
        obj = r.json()
        if not isinstance(obj, dict):
            return ""
        data = obj.get("data") or {}
        inline = str(data.get("url_inline") or "").replace("\\/", "/").strip()
        if inline.startswith("http") and re.search(r'\.(?:m3u8|mp4)(?:[?#]|$)', inline):
            return inline
        mt = str(data.get("mt") or "").strip()
        return mt

    def _post_resolve(self, mt, episode):
        data = {"token": mt}
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Origin": self.host, "Referer": self.host + "/Player/ec?episode=" + episode}
        r = self._session.post(self.host + "/Player/resolveUrl", data=data, headers=headers, timeout=15)
        if r.status_code != 200:
            return ""
        obj = r.json()
        if not isinstance(obj, dict) or obj.get("code") != 1:
            return ""
        data = obj.get("data") or {}
        url = str(data.get("url") or "").replace("\\/", "/").strip()
        if not url:
            return ""
        return self._fix(url)

    def _proxy_root(self):
        raw = ""
        try:
            raw = super().getProxyUrl()
        except Exception:
            raw = ""
        raw = str(raw or "").strip()
        if raw:
            return raw
        return "http://127.0.0.1:9978/proxy?do=py"

    def _proxy_m3u8_url(self, url, referer=""):
        # 播放地址经过本地代理返回，播放列表重写与分片转发使用文本方式处理
        root = self._proxy_root()
        sep = "&" if "?" in root else "?"
        return root + sep + "type=m3u8&url=" + quote(url, safe="") + "&referer=" + quote(referer or self.host + "/", safe="")

    def proxy(self, param):
        return self.localProxy(param)

    def _fetch_m3u8(self, url, referer):
        headers = {"User-Agent": self.headers["User-Agent"], "Referer": referer or self.host + "/", "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9"}
        r = self._session.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            return None
        return r.text

    def _rewrite_m3u8(self, text, base_url, referer):
        lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        root = self._proxy_root()
        sep = "&" if "?" in root else "?"
        out = []
        for raw in lines:
            line = raw.strip()
            if not line:
                out.append("")
                continue
            if line.startswith("#"):
                upper = line.upper()
                if upper.startswith("#EXT-X-KEY") or upper.startswith("#EXT-X-MAP"):
                    out.append(self._rewrite_tag_uri(line, base_url, referer))
                    continue
                if upper.startswith("#EXT-X-MEDIA") and "URI=" in line:
                    out.append(self._rewrite_tag_uri(line, base_url, referer))
                    continue
                if upper.startswith("#EXT-X-SESSION-DATA") and "URI=" in line:
                    out.append(self._rewrite_tag_uri(line, base_url, referer))
                    continue
                if upper.startswith("#EXT-X-I-FRAMES-ONLY") and "URI=" in line:
                    out.append(self._rewrite_tag_uri(line, base_url, referer))
                    continue
                out.append(raw)
                continue
            abs_url = urljoin(base_url, line)
            out.append(root + sep + "type=ts&url=" + quote(abs_url, safe="") + "&referer=" + quote(referer or self.host + "/", safe=""))
        return "\n".join(out)

    def _rewrite_tag_uri(self, line, base_url, referer):
        # 标签行中的 URI 属性指向子播放列表或者密钥文件，统一改写为本地代理地址
        root = self._proxy_root()
        sep = "&" if "?" in root else "?"
        def _replace(match):
            prefix = match.group(1)
            uri = match.group(2)
            abs_url = urljoin(base_url, uri)
            kind = "m3u8" if self._looks_like_playlist(abs_url) else "ts"
            return prefix + root + sep + "type=" + kind + "&url=" + quote(abs_url, safe="") + "&referer=" + quote(referer or self.host + "/", safe="") + '"'
        return re.sub(r'(URI=")([^"]+)(")', _replace, line)

    def _looks_like_playlist(self, url):
        low = str(url or "").lower()
        return ".m3u8" in low or ".m3u" in low

    def isVideoFormat(self, url):
        text = str(url or "")
        low = text.lower()
        if "type=m3u8" in low or "type=ts" in low:
            return True
        return ".m3u8" in low or ".mp4" in low or ".ts" in low

    def getDependence(self):
        return []

    def localProxy(self, param):
        if not isinstance(param, dict):
            return [404, "text/plain", "bad param"]
        param = dict(param)
        kind = param.get("type") or param.get("action") or param.get("do") or ""
        if isinstance(kind, list):
            kind = kind[0] if kind else ""
        kind = str(kind or "").strip().lower()
        url = param.get("url") or ""
        if isinstance(url, list):
            url = url[0] if url else ""
        referer = param.get("referer") or ""
        if isinstance(referer, list):
            referer = referer[0] if referer else ""
        url = unquote(str(url or ""))
        referer = unquote(str(referer or ""))
        if not kind or kind in ("py", "proxy"):
            low_all = (url + " " + referer).lower()
            if "type=m3u8" in low_all or ".m3u8" in low_all or "m3u8" in low_all:
                kind = "m3u8"
            else:
                kind = "ts"
        if kind == "m3u8":
            if not url:
                return [404, "text/plain", "not found"]
            text = self._fetch_m3u8(url, referer)
            if not text:
                return [404, "text/plain", "m3u8 download failed"]
            return [200, "application/vnd.apple.mpegurl", self._rewrite_m3u8(text, url, referer)]
        headers = {"User-Agent": self.headers["User-Agent"], "Referer": referer or self.host + "/"}
        target = url or referer
        if not target.startswith("http"):
            return [404, "text/plain", "not found"]
        r = self._session.get(target, headers=headers, timeout=30, stream=True)
        if r.status_code != 200:
            return [404, "text/plain", "fetch failed"]
        content_type = r.headers.get("Content-Type", "video/mp2t") or "video/mp2t"
        return [200, content_type, r.content]

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            self._session.close()
        except Exception:
            pass
        return None

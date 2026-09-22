#!/usr/bin/python
# -*- coding: utf-8 -*-
import re, json, base64, requests, urllib.parse
from lxml import etree
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "番茄动漫"

    def init(self, extend=""):
        self.host = "https://www.fqdm.cc"
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        self.headers = {"User-Agent": self.ua, "Referer": self.host + "/"}
        self.playHeaders = {"User-Agent": self.ua, "Referer": self.host + "/", "Accept": "*/*"}
        self.categories = [
            {"type_id": "1", "type_name": "日韩动漫"},
            {"type_id": "2", "type_name": "国产动漫"},
            {"type_id": "3", "type_name": "港台动漫"},
            {"type_id": "4", "type_name": "欧美动漫"},
            {"type_id": "5", "type_name": "动漫综合"},
        ]
        self.pageCache = {}

    def _get(self, url):
        try:
            r = requests.get(url, headers=self.headers, timeout=15)
            r.encoding = "utf-8"
            return r.text
        except:
            return None

    def _fix(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        return self.host + u if u.startswith("/") else u

    def _first(self, node, xpaths):
        for xp in xpaths:
            for v in node.xpath(xp):
                v = v.strip() if isinstance(v, str) else v
                if v and "load.gif" not in v and "errorpic" not in v:
                    return v
        return ""

    def _text(self, node):
        return re.sub(r"\s+", "", "".join(node.xpath(".//text()[not(parent::small)]")))

    def _cls(self, name):
        return f'contains(concat(" ", normalize-space(@class), " "), " {name} ")'

    def _parseList(self, html):
        if not html:
            return []
        tree = etree.HTML(html)
        items, seen = [], set()
        for a in tree.xpath('//a[contains(@href,"/vod/detail/id/")]'):
            m = re.search(r"/detail/id/(\d+)", a.get("href", ""))
            if not m or m.group(1) in seen:
                continue
            txt = re.sub(r"\s+", " ", "".join(a.xpath(".//text()"))).strip()
            name = (a.get("title") or "").strip()
            if not name:
                name = self._first(a, [
                    './/strong//text()',
                    'following-sibling::*//*[contains(@class,"module-card-item-title")]//text()',
                ])
            if not name:
                name = txt
            if not name or a.xpath("ancestor::h1|ancestor::h2"):
                continue
            seen.add(m.group(1))
            pic = self._first(a, [
                './/img/@data-original', './/img/@data-src', './/img/@src',
                'ancestor::*[position()<=2][not(self::body or self::html)]//img/@data-original',
                'ancestor::*[position()<=2][not(self::body or self::html)]//img/@data-src',
                'ancestor::*[position()<=2][not(self::body or self::html)]//img/@src',
            ])
            remark = self._first(a, ['.//div[contains(@class,"module-item-note")]/text()'])
            if not remark:
                remark = re.sub(r"豆瓣:[\d.]+分|^\d+\s*", "", txt.replace(name, "")).strip()
            items.append({"vod_id": m.group(1), "vod_name": name, "vod_pic": self._fix(pic), "vod_remarks": remark})
        return items

    def homeContent(self, filter):
        return {"class": self.categories, "list": self._parseList(self._get(self.host + "/")), "filters": {}}

    def homeVideoContent(self):
        return {"list": self._parseList(self._get(self.host + "/"))}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        url = f"{self.host}/index.php/vod/type/id/{tid}.html" if pg == 1 else f"{self.host}/index.php/vod/type/id/{tid}/page/{pg}.html"
        vodList = self._parseList(self._get(url))
        sign = ",".join(v["vod_id"] for v in vodList)
        if sign and sign == self.pageCache.get(str(tid)):
            vodList = []
        else:
            self.pageCache[str(tid)] = sign
        return {"page": pg, "pagecount": 1, "limit": len(vodList) or 20, "total": 999, "list": vodList}

    def _episodes(self, tree):
        nodes = tree.xpath(f'//a[{self._cls("module-play-list-link")}]')
        if not nodes:
            nodes = [a for a in tree.xpath('//a[contains(@href,"/vod/play/id/")]')
                     if not re.search(r"tab-item|swiper-slide", a.get("class") or "")]
        sidOrder, playMap, seen = [], {}, set()
        for a in nodes:
            m = re.search(r"/play/id/\d+/sid/(\d+)/nid/(\d+)", a.get("href", ""))
            if not m:
                continue
            sid, nid = m.group(1), m.group(2)
            if (sid, nid) in seen:
                continue
            title = re.sub(r"\s+", "", "".join(a.xpath(".//span/text()"))) or self._text(a)
            if not title or "立即播放" in title or "立刻播放" in title:
                continue
            seen.add((sid, nid))
            if sid not in playMap:
                playMap[sid] = []
                sidOrder.append(sid)
            playMap[sid].append(f"{title}${self._fix(a.get('href', ''))}")
        return sidOrder, playMap

    def _sourceNames(self, tree, sidOrder):
        tabs = tree.xpath(f'//*[{self._cls("module-tab-item")} and {self._cls("tab-item")}]') or tree.xpath(f'//*[{self._cls("tab-item")}]')
        nameMap, noHref = {}, []
        for t in tabs:
            txt = self._text(t)
            if not txt:
                continue
            m = re.search(r"/sid/(\d+)/", t.get("href", "") or "")
            if m:
                nameMap.setdefault(m.group(1), txt)
            elif txt not in noHref:
                noHref.append(txt)
        rest = [s for s in sidOrder if s not in nameMap]
        for i, s in enumerate(rest):
            if i < len(noHref):
                nameMap[s] = noHref[i]
        return [nameMap.get(s) or f"线路{s}" for s in sidOrder]

    def detailContent(self, ids):
        vid = str(ids[0]).split("/")[-1].replace(".html", "")
        html = self._get(f"{self.host}/index.php/vod/detail/id/{vid}.html")
        if not html:
            return {"list": []}
        tree = etree.HTML(html)
        name = re.sub(r"\s+", " ", "".join(tree.xpath("//h1//text()"))).strip()
        pic = (re.search(r"vod_pic\s*=\s*'([^']+)'", html) or re.search(r"vod_image\s*=\s*'([^']+)'", html))
        pic = pic.group(1) if pic else self._first(tree, [
            '//div[contains(@class,"module-item-pic")]//img/@data-original',
            '//img[contains(@class,"lazyload")]/@data-original',
            '//meta[@property="og:image"]/@content',
        ])
        desc = ""
        m = re.search(r"vod_content\s*=\s*'([^']+)'", html)
        if m:
            try:
                desc = base64.b64decode(m.group(1)).decode("utf-8", "ignore").strip()
            except:
                desc = ""
        if not desc:
            desc = self._first(tree, ['//meta[@name="description"]/@content'])
        year = self._first(tree, ['//div[contains(@class,"module-info-tag-link")]/a[contains(@href,"/year/")]/text()'])
        area = self._first(tree, ['//div[contains(@class,"module-info-tag-link")]/a[contains(@href,"/area/")]/text()'])
        sidOrder, playMap = self._episodes(tree)
        froms = self._sourceNames(tree, sidOrder)
        urls = ["#".join(playMap[s]) for s in sidOrder]
        return {"list": [{
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": self._fix(pic),
            "vod_year": year,
            "vod_area": area,
            "vod_content": desc,
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }]}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        url = f"{self.host}/index.php/vod/search/page/{pg}/wd/{urllib.parse.quote(key)}.html"
        return {"list": self._parseList(self._get(url)), "page": pg}

    def _play_headers(self, u):
        """播放请求头：Referer 动态替换为播放链接自身的源站域名。
        m3u8 CDN 防盗链常校验 Referer 必须匹配自身域名，只用站点域名会被 403。"""
        hdrs = dict(self.playHeaders)
        try:
            if str(u).startswith("http"):
                p = urllib.parse.urlparse(u)
                if p.netloc:
                    hdrs["Referer"] = f"{p.scheme}://{p.netloc}/"
        except Exception:
            pass
        return hdrs

    def playerContent(self, flag, id, vipFlags):
        url = id if str(id).startswith("http") else self.host + str(id)
        html = self._get(url) or ""
        idx = html.find("player_aaaa")
        seg = html[idx:idx + 4000] if idx >= 0 else ""
        playUrl, enc = "", "0"
        m = re.search(r"player_aaaa\s*=\s*(\{.*?\})\s*</script>", seg, re.S) or re.search(r"player_aaaa\s*=\s*(\{.*\})", seg)
        if m:
            try:
                cfg = json.loads(m.group(1))
                playUrl, enc = cfg.get("url", ""), str(cfg.get("encrypt", "0"))
            except:
                playUrl = ""
        if not playUrl:
            m2 = re.search(r'"url"\s*:\s*"(.*?)"', seg)
            playUrl = m2.group(1).replace("\\/", "/") if m2 else ""
        try:
            if enc == "1":
                playUrl = urllib.parse.unquote(playUrl)
            elif enc == "2":
                playUrl = urllib.parse.unquote(base64.b64decode(playUrl).decode("utf-8"))
        except:
            pass
        if playUrl and re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", playUrl.split("#")[0], re.I):
            return {"parse": 0, "url": playUrl, "header": self._play_headers(playUrl)}
        return {"parse": 1, "url": playUrl if str(playUrl).startswith("http") else url, "header": self._play_headers(playUrl)}

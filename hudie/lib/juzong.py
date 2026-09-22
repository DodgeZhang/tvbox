# -*- coding: utf-8 -*-
import re, json, requests, urllib.parse
from lxml import etree

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def getName(self): return "剧踪"
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False
        def destroy(self): pass
        def localProxy(self, param): return None
        def homeContent(self, filter): return {"class": [], "list": [], "filters": {}}
        def homeVideoContent(self): return {"list": []}
        def categoryContent(self, tid, pg, filter, extend): return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 0, "total": 0}
        def detailContent(self, ids): return {"list": []}
        def searchContent(self, key, quick, pg="1"): return {"list": [], "page": int(pg or 1)}
        def playerContent(self, flag, id, vipFlags): return {"parse": 0, "url": id or "", "header": {}}

HOST = "https://www.juzong01.me"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
CATS = [
    ("1", "电影"), ("2", "剧集"), ("3", "综艺"), ("4", "动漫"),
    ("6", "动作片"), ("7", "喜剧片"), ("8", "爱情片"), ("9", "科幻片"),
    ("10", "恐怖片"), ("11", "剧情片"), ("12", "战争片"), ("13", "国产剧"),
    ("14", "港台剧"), ("15", "日韩剧"), ("16", "欧美剧"), ("20", "海外剧"),
    ("22", "犯罪片"), ("23", "动画片"),
]


class Spider(BaseSpider):
    name = "剧踪"

    def getName(self):
        return self.name

    def init(self, extend=""):
        ext = {}
        if extend:
            try:
                ext = json.loads(extend) if str(extend).strip().startswith("{") else {}
            except Exception:
                pass
        self.host = (ext.get("host") or HOST).rstrip("/")
        self.timeout = int(ext.get("timeout") or 15)
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.host + "/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._cookie_ok = False

    def _ensure_cookie(self):
        if self._cookie_ok:
            return
        try:
            self.session.get(self.host + "/", timeout=self.timeout, verify=False, allow_redirects=True)
        except Exception:
            pass
        self._cookie_ok = True

    def _get(self, url, timeout=None):
        self._ensure_cookie()
        try:
            r = self.session.get(url, timeout=timeout or self.timeout, verify=False)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text or ""
        except Exception:
            return ""

    def _post(self, url, data):
        try:
            r = self.session.post(url, data=data, timeout=self.timeout, verify=False)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text or ""
        except Exception:
            return ""

    def _fix(self, u):
        if not u:
            return ""
        u = u.strip()
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host + u
        return u

    def _parse_list(self, html):
        if not html:
            return []
        tree = etree.HTML(html)
        items, seen = [], set()
        nodes = tree.xpath('//a[contains(@class,"stui-vodlist__thumb") and contains(@href,"/voddetail/")]')
        for a in nodes:
            href = a.get("href", "")
            m = re.search(r"/voddetail/(\d+)", href)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            pic = self._fix(a.get("data-original") or a.get("data-src") or "")
            if not pic:
                img = a.xpath(".//img")
                if img:
                    pic = self._fix(img[0].get("data-original") or img[0].get("src", ""))
            if not pic:
                style = a.get("style", "") or ""
                bm = re.search(r'url\(["\']?([^"\')\s]+)', style)
                if bm:
                    pic = self._fix(bm.group(1))
            title = (a.get("title") or "").strip()
            if not title and img:
                title = img[0].get("alt", "").strip()
            if not title:
                title = "".join(a.xpath('.//text()')).strip()
            if not title:
                continue
            remark = ""
            mr = a.xpath('.//span[contains(@class,"pic-text")]//text()')
            if mr:
                remark = "".join(mr).strip()
            if not remark:
                parent = a.getparent()
                if parent is not None:
                    pr = parent.xpath('.//p[contains(@class,"text")]//text()')
                    if pr:
                        remark = "".join(pr).strip()[:30]
            items.append({
                "vod_id": m.group(1),
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark,
            })
        return items

    def homeContent(self, filter):
        classes = [{"type_id": c[0], "type_name": c[1]} for c in CATS]
        html = self._get(self.host + "/")
        recs = self._parse_list(html)[:30] if html else []
        return {"class": classes, "list": recs, "filters": {}}

    def homeVideoContent(self):
        html = self._get(self.host + "/")
        return {"list": self._parse_list(html)[:30]}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        url = f"{self.host}/vodshow/{tid}-----------{pg}---.html" if pg > 1 else f"{self.host}/vodshow/{tid}-----------/"
        if pg == 1:
            url = f"{self.host}/vodtype/{tid}/"
        html = self._get(url)
        lst = self._parse_list(html)
        # 从页面提取总页数
        pagecount = pg
        if html:
            tree = etree.HTML(html)
            pages = tree.xpath('//ul[contains(@class,"pagination")]//a/@href')
            nums = []
            for p in pages:
                pm = re.search(r"/vodshow/\d+-----------(\d+)", p)
                if pm:
                    nums.append(int(pm.group(1)))
            if nums:
                pagecount = max(nums)
        return {"list": lst, "page": pg, "pagecount": max(pagecount, pg),
                "limit": len(lst), "total": pagecount * 36 if pagecount > 1 else len(lst)}

    def detailContent(self, ids):
        result = {"list": []}
        vid = ids[0] if isinstance(ids, list) else ids
        vid = str(vid).strip()
        html = self._get(f"{self.host}/voddetail/{vid}/")
        if not html:
            return result
        tree = etree.HTML(html)
        # 标题
        name = "".join(tree.xpath('//h1//text()')).strip()
        if not name:
            name = "".join(tree.xpath('//h2//text()')).strip()
        # 海报
        pic = ""
        img_node = tree.xpath('//div[contains(@class,"stui-content__thumb")]//img')
        if img_node:
            pic = self._fix(img_node[0].get("data-original") or img_node[0].get("src", ""))
        if not pic:
            pic = self._fix("".join(tree.xpath('//meta[@property="og:image"]/@content')))
        # 简介
        desc = ""
        desc_node = tree.xpath('//span[contains(@class,"detail-content")]//text()')
        if desc_node:
            desc = "".join(desc_node).strip()
        if not desc:
            desc = "".join(tree.xpath('//meta[@name="description"]/@content')).strip()
        # 年份
        year = ""
        ym = re.search(r'(\d{4})', "".join(tree.xpath('//p[contains(@class,"data")]//text()')))
        if ym:
            year = ym.group(1)
        # 类型
        area = ""
        type_text = "".join(tree.xpath('//p[contains(@class,"data")]//text()'))
        am = re.search(r'地区[：:]\s*(\S+)', type_text)
        if am:
            area = am.group(1)
        # 主演/导演
        actor = " ".join("".join(a.xpath('.//text()')).strip() for a in tree.xpath('//p[contains(@class,"data")]//a[contains(@href,"vodsearch")]'))
        # 从"主演"和"导演"字段提取
        actors, directors = [], []
        for p in tree.xpath('//p[contains(@class,"data")]'):
            pt = "".join(p.xpath('.//text()')).strip()
            if pt.startswith("主演"):
                actors = [a.strip() for a in "".join(p.xpath('.//a//text()')).split() if a.strip()]
            elif pt.startswith("导演"):
                directors = [a.strip() for a in "".join(p.xpath('.//a//text()')).split() if a.strip()]

        # 播放线路和剧集
        sources, episodes = [], []
        panels = tree.xpath('//div[contains(@class,"stui-pannel") and contains(@class,"playlist")]')
        for panel in panels:
            # 线路名
            src_title = "".join(panel.xpath('.//h3[contains(@class,"title")]//text()')).strip()
            src_title = re.sub(r'[\s]+', ' ', src_title).strip()
            if not src_title:
                src_title = f"线路{len(sources) + 1}"
            # 剧集列表
            eps = panel.xpath('.//ul[contains(@class,"stui-content__playlist")]//a')
            ep_list = []
            for a in eps:
                ep_name = "".join(a.xpath('.//text()')).strip()
                ep_href = a.get("href", "")
                if not ep_name or not ep_href:
                    continue
                ep_list.append(f"{ep_name}${self._fix(ep_href)}")
            if ep_list:
                sources.append(src_title)
                episodes.append("#".join(ep_list))

        if not sources:
            return result

        result["list"].append({
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_year": year,
            "vod_area": area,
            "vod_actor": " ".join(actors),
            "vod_director": " ".join(directors),
            "vod_content": desc,
            "vod_remarks": f"{year}".strip(),
            "vod_play_from": "$$$".join(sources),
            "vod_play_url": "$$$".join(episodes),
        })
        return result

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        url = f"{self.host}/vodsearch/-------------/?wd={urllib.parse.quote(key)}"
        html = self._get(url)
        return {"list": self._parse_list(html), "page": pg}

    def playerContent(self, flag, id, vipFlags):
        url = (id or "").strip()
        if not url:
            return {"parse": 0, "url": "", "header": {}}
        # 直链直接返回
        if re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", url, re.I):
            return {"parse": 0, "url": url, "header": self.headers}
        # 如果是本站播放页，提取 player_data 尝试解密
        if self.host in url and "/vodplay/" in url:
            html = self._get(url)
            if html:
                m = re.search(r'var\s+player_data\s*=\s*(\{.*?\})\s*<', html, re.S)
                if m:
                    try:
                        pd = json.loads(m.group(1))
                        play_url = (pd.get("url") or "").strip()
                        encrypt = str(pd.get("encrypt", "0"))
                        if encrypt == "1":
                            play_url = urllib.parse.unquote(play_url)
                        elif encrypt == "2":
                            play_url = urllib.parse.unquote(
                                __import__("base64").b64decode(play_url).decode("utf-8", "ignore"))
                        if play_url and re.search(r"\.(m3u8|mp4)(\?|$)", play_url, re.I):
                            return {"parse": 0, "url": play_url,
                                    "header": {"User-Agent": UA, "Referer": self.host + "/"}}
                    except Exception:
                        pass
            # 解密失败或非直链，让 TVBox 播放器渲染页面
            return {"parse": 1, "url": url,
                    "header": {"User-Agent": UA, "Referer": self.host + "/"}}
        # 非本站 URL，交由播放器处理
        return {"parse": 1, "url": url, "header": {"User-Agent": UA}}

    def searchContentPage(self, key, quick, page):
        return self.searchContent(key, quick, str(page))

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", url or "", re.I))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

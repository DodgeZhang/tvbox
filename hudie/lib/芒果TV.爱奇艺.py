#!/usr/bin/python
import json
import re
from urllib.parse import urljoin, quote
import requests
from lxml import etree
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "枫叶4K"
    def init(self, extend=""):
        self.name = "枫叶4K"
        self.host = "https://www.guan-feng.com"
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0", "Referer": self.host + "/"}
        self.categories = [{"type_id": "mgtv", "type_name": "芒果SVIP"}, {"type_id": "iqiyi", "type_name": "爱奇SVIP"}]
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.player_list = self._load_players()
    def _load_players(self):
        try:
            body = self._get(self.host + "/static/js/playerconfig.js")
            i = body.find("MacPlayerConfig.player_list=")
            if i >= 0:
                dec = json.JSONDecoder()
                d, _ = dec.raw_decode(body[i + len("MacPlayerConfig.player_list="):].lstrip())
                if isinstance(d, dict):
                    return d
        except Exception:
            pass
        return {}
    def _get(self, url):
        try:
            r = self.session.get(url, headers=self.headers, timeout=15, verify=False, proxies=self.session.proxies or None)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception:
            return ""
    def _json_get(self, url, params=None):
        try:
            r = self.session.get(url, params=params, headers=self.headers, timeout=15, verify=False, proxies=self.session.proxies or None)
            return r.json()
        except Exception:
            return {}
    def _fix(self, url):
        if not url:
            return ""
        return urljoin(self.host + "/", url.replace("&amp;", "&"))
    def _is_media(self, url):
        return bool(re.search(r"\.(?:m3u8|mp4)(?:$|[?#])", url.lower()))
    def _text(self, node):
        return " ".join("".join(node.xpath(".//text()")).split()) if node is not None else ""
    def _items(self, html):
        tree = etree.HTML(html or "")
        out, seen = [], set()
        for a in tree.xpath("//div[contains(@class,'module-items')]//a[contains(@href,'/detail/')]"):
            href = a.get("href", "")
            m = re.search(r"/detail/(\d+)\.html", href)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            title = (a.get("title") or a.xpath("string(.//img/@alt)") or a.xpath("string(.//strong)") or "").strip()
            if not title:
                continue
            pic = (a.xpath("string(.//img/@data-src)") or a.xpath("string(.//img/@src)") or "").strip()
            note = a.xpath("string(.//div[contains(@class,'module-item-note')])").strip()
            item = {"vod_id": m.group(1), "vod_name": title, "vod_pic": self._fix(pic)}
            if note:
                item["vod_remarks"] = note
            out.append(item)
        return out
    def _pagecount(self, html):
        nums = []
        tree = etree.HTML(html or "")
        for a in tree.xpath("//a[contains(@class,'page-number') or contains(@class,'page-next')]"):
            m = re.search(r"/page/(\d+)\.html", a.get("href", ""))
            if m:
                nums.append(int(m.group(1)))
        return max(nums) if nums else 1
    def homeContent(self, filter):
        return {"class": self.categories, "list": self._items(self._get(self.host)), "filters": {}}
    def homeVideoContent(self):
        return {"list": self._items(self._get(self.host))}
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        kws = {"mgtv": ["芒果"], "iqiyi": ["爱奇艺", "中国新说唱", "青春有你", "奇葩说", "一年一度喜剧大赛", "中国说唱巅峰对决", "尖叫之夜"]}.get(str(tid))
        if kws:
            return self._kw_category(kws)
        html = self._get(self.host + "/label/" + str(tid) + "/page/" + str(pg) + ".html")
        items = self._items(html)
        return {"page": pg, "pagecount": self._pagecount(html), "limit": len(items) or 24, "total": 0, "list": items}
    def _kw_category(self, kws):
        items, seen = [], set()
        for kw in kws:
            d = self._json_get(self.host + "/index.php/ajax/suggest", {"mid": "1", "wd": kw, "limit": "50"})
            for v in d.get("list", []):
                vid = str(v.get("id", ""))
                name = v.get("name", "")
                if not vid or not name or vid in seen or kw not in name:
                    continue
                seen.add(vid)
                items.append({"vod_id": vid, "vod_name": name, "vod_pic": self._fix(v.get("pic", ""))})
        return {"page": 1, "pagecount": 1, "limit": len(items) or 24, "total": 0, "list": items}
    def detailContent(self, ids):
        out = []
        for vid in ids:
            try:
                tree = etree.HTML(self._get(self.host + "/detail/" + str(vid) + ".html"))
                name = self._text(tree.xpath("//h1")[0]) if tree.xpath("//h1") else str(vid)
                if not name or len(name) > 80:
                    continue
                pic = (tree.xpath("string(//div[contains(@class,'module-info-poster')]//img/@data-src)") or tree.xpath("string(//div[contains(@class,'module-info-poster')]//img/@src)") or "").strip()
                tabs = [s.strip() for s in tree.xpath("//span[contains(@class,'mx-anthology-tab-label')]/text()") if s.strip()]
                fs, us, seen = [], [], set()
                panels = tree.xpath("//div[contains(@class,'mx-anthology-panel') and not(contains(@class,'mx-anthology-panels'))]")
                for i, panel in enumerate(panels):
                    eps, links = [], panel.xpath(".//a[contains(@class,'mx-anthology-link')]")
                    if not links:
                        continue
                    fname = tabs[i] if i < len(tabs) else "线路" + str(len(fs) + 1)
                    if fname in seen:
                        n = 2
                        while fname + str(n) in seen:
                            n += 1
                        fname = fname + str(n)
                    seen.add(fname)
                    for a in links:
                        href = a.get("href", "")
                        m = re.search(r"/play/(\d+)-(\d+)-(\d+)\.html", href)
                        if not m:
                            continue
                        ep = self._text(a) or ("第" + m.group(3) + "集")
                        eps.append(ep + "$" + m.group(1) + "-" + m.group(2) + "-" + m.group(3))
                    if eps:
                        fs.append(fname)
                        us.append("#".join(eps))
                out.append({"vod_id": str(vid), "vod_name": name, "vod_pic": self._fix(pic), "vod_play_from": "$$$".join(fs), "vod_play_url": "$$$".join(us)})
            except Exception:
                pass
        return {"list": out}
    def searchContent(self, key, quick, pg="1"):
        d = self._json_get(self.host + "/index.php/ajax/suggest", {"mid": "1", "wd": key, "limit": "50"})
        items = []
        for v in d.get("list", []):
            vid = str(v.get("id", ""))
            if not vid:
                continue
            items.append({"vod_id": vid, "vod_name": v.get("name", ""), "vod_pic": self._fix(v.get("pic", ""))})
        return {"page": int(pg) if str(pg).isdigit() else 1, "list": items}
    def playerContent(self, flag, id, vipFlags):
        body = self._get(self.host + "/play/" + str(id) + ".html")
        i = body.find("player_aaaa=")
        if i < 0:
            return {}
        try:
            dec = json.JSONDecoder()
            pd, _ = dec.raw_decode(body[i + len("player_aaaa="):].lstrip())
        except Exception:
            return {}
        u = (pd.get("url") or "").replace("&amp;", "&")
        if not u:
            return {}
        frm = pd.get("from", "")
        if self._is_media(u):
            return {"parse": 0, "url": u, "header": json.dumps(self.headers)}
        cfg = self.player_list.get(frm) or {}
        if isinstance(cfg, dict) and cfg.get("ps") == "1" and cfg.get("parse"):
            return {"parse": 1, "url": cfg["parse"] + quote(u, safe=""), "header": json.dumps(self.headers)}
        if u.startswith("http"):
            return {"parse": 1, "url": u, "header": json.dumps(self.headers)}
        return {}
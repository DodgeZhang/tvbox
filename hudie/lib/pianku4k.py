# -*- coding: utf-8 -*-
import re
import sys
import json
import time
import struct
import zlib
from urllib.parse import quote
from lxml import etree
try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass
sys.path.append('..')
from base.spider import Spider
class Spider(Spider):
    def getName(self): return "片库4K"
    def init(self, extend=""):
        self.host = "https://4k01.pianku.online"
        self.headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36", "Referer": self.host + "/"}
        self.categories = [{"type_id": "20", "type_name": "电影"}, {"type_id": "37", "type_name": "剧集"}, {"type_id": "43", "type_name": "动漫"}, {"type_id": "45", "type_name": "综艺"}, {"type_id": "47", "type_name": "B站"}, {"type_id": "21", "type_name": "动作片"}, {"type_id": "22", "type_name": "喜剧片"}, {"type_id": "23", "type_name": "爱情片"}]
        try:
            import requests as _rq
            self._sess = _rq.Session()
            self._sess.headers.update(self.headers)
            self._sess.verify = False
        except Exception:
            self._sess = None
        self._search_ok = 0
        self._plines = []
        self._plines_ts = 0
    def _pline_fallback(self):
        return [("自营", "https://svip.qlplayer.cyou/?url="), ("闪电", "https://bfq.txnp.cn/excessive?url="), ("七哥", "https://jx.nnxv.cn/tv.php?url="), ("极速", "https://jx.2s0.cn/player/?url="), ("七七", "https://jx.77flv.cc/?url="), ("Super", "https://super.playr.top/?url="), ("盘古", "https://www.pangujiexi.com/jiexi/?url="), ("冰豆", "https://bd.jx.cn/?url=")]
    def _parse_lines(self):
        if self._plines and time.time() - self._plines_ts < 3600: return self._plines
        try:
            h = self._get(self.host + "/player/?url=https://v.qq.com/x/cover/mzc002008kq4b47/f4102rcpbqv.html")
            m = re.findall(r'data-prefix="([^"]+)"\s+data-name="([^"]+)"', h or "")
            if m:
                self._plines = [(n.strip(), p) for p, n in m if n.strip() and p]
                self._plines_ts = time.time()
                return self._plines
        except Exception:
            pass
        return self._pline_fallback()
    def _outer(self, vodplay_url):
        try:
            h = self._get(vodplay_url)
            if not h: return ""
            m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})', h)
            if not m: return ""
            return (json.loads(m.group(1)).get("url", "") or "").replace("\\/", "/")
        except Exception:
            return ""
    def _req(self, method, url, data=None):
        try:
            if self._sess is not None:
                r = self._sess.request(method, url, data=data, timeout=15, verify=False)
            else:
                r = self.fetch(url, headers=self.headers, timeout=15, verify=False) if method == "GET" else self.post(url, data=data, headers=self.headers, timeout=15, verify=False)
            r.encoding = "utf-8"
            return r
        except Exception:
            return None
    def _get(self, url):
        r = self._req("GET", url)
        return r.text if r is not None and getattr(r, "status_code", 200) == 200 else None
    def _fix(self, u):
        if not u: return ""
        if u.startswith("//"): return "https:" + u
        if u.startswith("/"): return self.host + u
        return u
    def _html(self, content):
        if not content: return None
        return etree.HTML(content.encode("utf-8"))
    def _cards(self, html):
        if not html: return []
        tree = self._html(html)
        if tree is None: return []
        out, seen = [], set()
        for a in tree.xpath('//div[contains(@class,"vod-item")]//a[contains(@href,"/voddetail/")]'):
            try:
                m = re.search(r"/voddetail/(\d+)\.html", a.get("href", ""))
                if not m or m.group(1) in seen: continue
                seen.add(m.group(1))
                name = (a.get("title", "") or "".join(a.xpath('.//h4[contains(@class,"title")]//text()'))).strip()
                if not name: continue
                img = a.xpath('.//img')
                pic = self._fix(img[0].get("src", "") if img else "")
                rem = "".join(a.xpath('.//span[contains(@class,"remarks")]//text()')).strip()
                sub = "".join(a.xpath('.//p[contains(@class,"subtitle")]//text()')).strip()
                out.append({"vod_id": m.group(1), "vod_name": name, "vod_pic": pic, "vod_remarks": rem or sub})
            except Exception:
                continue
        return out
    def _png_x(self, data):
        j = data.find(b"\x89PNG")
        if j > 0: data = data[j:]
        elif j < 0: return None
        pos, pal, idat, w, h, ctype, bitd = 8, None, b"", 0, 0, 0, 0
        while pos + 8 <= len(data):
            ln = struct.unpack(">I", data[pos:pos + 4])[0]
            typ = data[pos + 4:pos + 8]
            chunk = data[pos + 8:pos + 8 + ln]
            if typ == b"IHDR": w, h, bitd, ctype, _, _, _ = struct.unpack(">IIBBBBB", chunk)
            elif typ == b"PLTE": pal = chunk
            elif typ == b"IDAT": idat += chunk
            elif typ == b"IEND": break
            pos += 12 + ln
        if not pal or not idat or w != 240 or h != 450: return None
        raw = zlib.decompress(idat)
        ch = 1
        stride = w * ch
        rows, prev = [], bytearray(stride)
        p = 0
        for _ in range(h):
            f = raw[p]; p += 1
            line = bytearray(raw[p:p + stride]); p += stride
            if f == 1:
                for i in range(ch, stride): line[i] = (line[i] + line[i - ch]) & 255
            elif f == 2:
                for i in range(stride): line[i] = (line[i] + prev[i]) & 255
            elif f == 3:
                for i in range(stride):
                    a = line[i - ch] if i >= ch else 0
                    line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
            elif f == 4:
                for i in range(stride):
                    a = line[i - ch] if i >= ch else 0
                    b = prev[i]
                    c = prev[i - ch] if i >= ch else 0
                    pp = a + b - c
                    pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                    pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                    line[i] = (line[i] + pr) & 255
            elif f != 0: return None
            rows.append(line); prev = line
        lum = [(pal[i] * 299 + pal[i + 1] * 587 + pal[i + 2] * 114) // 1000 for i in range(0, len(pal), 3)]
        th = h // 3
        col = [0] * w
        for x in range(w):
            s = 0
            for y in range(th): s += abs(lum[rows[y][x]] - lum[rows[y + 2 * th][x]])
            col[x] = s
        best, bs, W = 0, -1, 50
        for i in range(w - W + 1):
            s = sum(col[i:i + W])
            if s > bs: bs, best = s, i
        return best
    def _search_pass(self):
        if time.time() < self._search_ok - 30: return True
        for _ in range(10):
            try:
                r = self._req("GET", self.host + "/SlideCaptcha.php?action=get&t=" + str(time.time()))
                if r is None or b"\x89PNG" not in r.content[:60]: continue
                x = self._png_x(r.content)
                if x is None: continue
                c = self._req("GET", self.host + "/SlideCaptcha.php?action=check&x=%d&t=%f" % (x, time.time()))
                if c is None or c.text.strip() != "ok": continue
                v = self._req("POST", self.host + "/verify/search_complete.html", data={"source": "search"})
                d = json.loads(v.text) if v is not None else {}
                if str(d.get("code", "")) == "1":
                    self._search_ok = time.time() + int(d.get("expires", 300))
                    return True
            except Exception:
                continue
        return False
    def homeContent(self, filter):
        return {"class": self.categories, "list": self._cards(self._get(self.host + "/")), "filters": {}}
    def homeVideoContent(self):
        return {"list": self._cards(self._get(self.host + "/"))}
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        url = self.host + "/vodtype/%s.html" % tid if pg <= 1 else self.host + "/vodtype/%s-%d.html" % (tid, pg)
        html = self._get(url)
        items = self._cards(html)
        pc = pg
        if html:
            m = re.search(r"/vodtype/%s-(\d+)\.html\" title=\"尾页\"" % re.escape(str(tid)), html)
            if m: pc = int(m.group(1))
            elif "下一页" in html: pc = pg + 1
        return {"page": pg, "pagecount": pc, "limit": len(items), "total": len(items), "list": items}
    def detailContent(self, ids):
        result = {"list": []}
        for vid in ids:
            try:
                html = self._get(self.host + "/voddetail/%s.html" % vid)
                if not html: continue
                tree = self._html(html)
                if tree is None: continue
                name = "".join(tree.xpath('//h1[contains(@class,"detail-title")]/text()')).strip() or "".join(tree.xpath('//h1[contains(@class,"detail-title")]//text()')).strip()
                if not name: continue
                rem = "".join(tree.xpath('//h1[contains(@class,"detail-title")]//span[contains(@class,"detail-remarks")]//text()')).strip()
                img = tree.xpath('//div[contains(@class,"detail-poster")]//img')
                pic = self._fix(img[0].get("src", "") if img else "")
                meta = ["".join(tree.xpath('//div[contains(@class,"detail-meta")][1]//text()')).strip(), "".join(tree.xpath('//div[contains(@class,"detail-meta")][2]//text()')).strip(), "".join(tree.xpath('//div[contains(@class,"detail-meta")][3]//text()')).strip()]
                area = (re.search(r"地区：([^\s]+)", meta[0]).group(1) if re.search(r"地区：([^\s]+)", meta[0]) else "") if len(meta) > 0 else ""
                year = (re.search(r"年份：(\d+)", meta[0]).group(1) if re.search(r"年份：(\d+)", meta[0]) else "") if len(meta) > 0 else ""
                director = meta[1].replace("导演：", "").strip() if len(meta) > 1 else ""
                actor = meta[2].replace("主演：", "").strip() if len(meta) > 2 else ""
                desc = "".join(tree.xpath('//div[contains(@class,"detail-desc")]//p//text()')).strip()
                first = (tree.xpath('//a[contains(@class,"btn-play")]/@href') or tree.xpath('//a[contains(@href,"/vodplay/")]/@href') or [""])[0]
                sources, episodes = [], []
                ph = self._get(self._fix(first)) if first else None
                pt = self._html(ph) if ph else None
                for t in ([pt] if pt is not None else []) + [tree]:
                    mp = {}
                    for s in t.xpath('//span[contains(@class,"source-tab-item")]'):
                        n = "".join(s.xpath(".//text()")).strip()
                        tg = (s.get("data-target") or "").strip()
                        if n and tg: mp[tg] = n
                    for pane in t.xpath('//div[contains(@class,"source-pane")]'):
                        eps = []
                        for a in pane.xpath('.//a[contains(@href,"/vodplay/")]'):
                            n = (a.get("title", "") or "".join(a.xpath(".//text()"))).strip() or "正片"
                            eps.append("%s$%s" % (n, self._fix(a.get("href", ""))))
                        if eps:
                            grp = mp.get(pane.get("id", ""), "线路%d" % (len(sources) + 1))
                            for k, v in [(grp, "#".join(eps))]:
                                if v and (not episodes or episodes[-1] != v or sources[-1] != k):
                                    sources.append(k)
                                    episodes.append(v)
                    if sources: break
                if not sources and first:
                    sources, episodes = ["正片"], ["正片$%s" % self._fix(first)]
                if not sources: continue
                plines = self._parse_lines()
                canon = max(episodes, key=lambda e: len(e.split("#"))) if episodes else ""
                eps = canon.split("#") if canon else []
                first_ep_url = eps[0].split("$", 1)[1] if eps and "$" in eps[0] else self._fix(first)
                outer = self._outer(first_ep_url)
                if plines and outer.startswith("http") and not re.search(r"\.(m3u8|mp4|flv|mkv|webm)(\?|$)", outer):
                    pfrom = "$$$".join(n for n, _ in plines)
                    purl = "$$$".join(canon for _, _ in plines)
                    result["list"].append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": rem, "vod_area": area, "vod_year": year, "vod_director": director, "vod_actor": actor, "vod_content": desc, "vod_play_from": pfrom, "vod_play_url": purl})
                    continue
                result["list"].append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": rem, "vod_area": area, "vod_year": year, "vod_director": director, "vod_actor": actor, "vod_content": desc, "vod_play_from": "$$$".join(sources), "vod_play_url": "$$$".join(episodes)})
            except Exception:
                continue
        return result
    def searchContent(self, key, quick, pg="1"):
        if not self._search_pass(): return {"list": [], "page": int(pg or 1)}
        html = self._get(self.host + "/vodsearch/%s-------------.html" % quote(key))
        return {"list": self._cards(html), "page": int(pg or 1)}
    def playerContent(self, flag, id, vipFlags):
        url = self._fix(id)
        plines = {n: p for n, p in self._parse_lines()}
        if flag in plines and url.startswith("http") and "4k01.pianku.online/vodplay/" in url:
            outer = self._outer(url)
            if outer.startswith("http") and not re.search(r"\.(m3u8|mp4|flv|mkv|webm)(\?|$)", outer):
                from urllib.parse import quote as _q, unquote as _uq
                raw = _uq(url)
                if "/player/?url=" in raw:
                    outer = _uq(raw.split("/player/?url=", 1)[1].split("&")[0])
                return {"parse": 1, "jx": 1, "url": plines[flag] + _q(outer, safe=""), "header": json.dumps(self.headers)}
        if "/player/?url=" in url or any(k in url for k in ("qlplayer.cyou", "txnp.cn", "nnxv.cn", "2s0.cn", "77flv.cc", "playr.top", "pangujiexi", "jx.cn")):
            return {"parse": 1, "jx": 1, "url": url, "header": json.dumps(self.headers)}
        html = self._get(url)
        if html:
            m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})', html)
            if m:
                try:
                    d = json.loads(m.group(1))
                    u = (d.get("url", "") or "").replace("\\/", "/")
                    if u.startswith("http"):
                        if re.search(r"\.(m3u8|mp4|flv|mkv|webm)(\?|$)", u): return {"parse": 0, "url": u, "header": json.dumps(self.headers)}
                        return {"parse": 1, "url": u, "header": json.dumps(self.headers)}
                except Exception:
                    pass
            m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
            if m: return {"parse": 0, "url": m.group(1), "header": json.dumps(self.headers)}
        return {"parse": 1, "url": url, "header": json.dumps(self.headers)}
    def isVideoFormat(self, url): return ".m3u8" in url or ".mp4" in url
    def manualVideoCheck(self): return False
    def localProxy(self, param): return None
    def destroy(self): return None

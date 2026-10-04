# -*- coding: utf-8 -*-
import sys, re, json
from urllib.parse import quote
sys.path.append('..')
try:
    from base.spider import Spider as _Base
except ImportError:
    class _Base:
        def fetch(self, url, headers=None, **kw):
            import requests as rq
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

H = "https://hsex1.icu"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/133.0.0.0 Safari/537.36"
CATS = {"list": "最新", "top7_list": "周榜", "top_list": "月榜", "5min_list": "5分钟+", "long_list": "10分钟+"}

class Spider(_Base):
    def init(self, extend=""):
        self.headers = {"User-Agent": UA, "Referer": H + "/", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}

    def getName(self): return "片吧365"
    def isVideoFormat(self, u): return ".m3u8" in u or ".mp4" in u
    def manualVideoCheck(self): return False
    def localProxy(self, param): pass

    def _get(self, path):
        url = path if path.startswith("http") else H + path
        try:
            return self.fetch(url, headers=self.headers).text or ""
        except Exception as e:
            return ""

    def _cards(self, h):
        seen, v = set(), []
        for m in re.finditer(r'<div class="thumbnail">(.*?)</div>\s*</div>\s*</div>', h, re.S):
            blk = m.group(1)
            um = re.search(r'href="video-(\d+)\.htm"', blk)
            if not um: continue
            vid = H + "/video-" + um.group(1) + ".htm"
            if vid in seen: continue
            seen.add(vid)
            im = re.search(r"background-image:\s*url\(['\"]?([^'\"\)]+)", blk)
            pic = im.group(1).strip() if im else ""
            if pic.startswith("//"): pic = "https:" + pic
            nm = re.search(r'<h5><a[^>]*>(.*?)</a>', blk, re.S)
            name = re.sub(r'\s+', '', nm.group(1)).strip() if nm else ""
            if not name:
                tm = re.search(r'class="image"[^>]*title="([^"]+)"', blk)
                name = tm.group(1) if tm else ""
            dm = re.search(r'<var class="duration">\s*([^<]+?)\s*</var>', blk) or re.search(r'class="duration"[^>]*>\s*([\d:]+)', blk)
            dur = dm.group(1).strip() if dm else ""
            card = {"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": dur}
            if dur: card["subtitle"] = dur
            v.append(card)
        if not v:
            for m in re.finditer(r'<a[^>]*href="video-(\d+)\.htm"[^>]*>\s*<div class="image"[^>]*title="([^"]+)"', h):
                vid = H + "/video-" + m.group(1) + ".htm"
                if vid not in seen:
                    seen.add(vid)
                    v.append({"vod_id": vid, "vod_name": m.group(2).strip(), "vod_pic": "", "vod_remarks": ""})
        return v

    def _parse_pagecount(self, h, current_pg=1):
        """从HTML解析总页数，增加搜索页专用模式"""
        if not h: return current_pg
        
        # 先尝试匹配各种分页模式
        patterns = [
            r'<a[^>]*class="page-link"[^>]*>(\d+)</a>',
            r'<li[^>]*class="page"[^>]*>(\d+)</li>',
            r'class="page"\s*>?\s*(\d+)\s*<',
            r'共\s*(\d+)\s*页',
            r'totalPages["\s:]+(\d+)',
            r'<span[^>]*>\s*(\d+)\s*</span>',
        ]
        
        max_pg = current_pg
        for p in patterns:
            nums = re.findall(p, h)
            if nums:
                try:
                    for n in nums:
                        m = re.search(r'(\d+)', str(n))
                        if m:
                            num = int(m.group(1))
                            if num > max_pg: max_pg = num
                except: pass
        
        # 搜索页/分类页:分页链接为 search-2.htm?search=x / list-2.htm
        page_links = re.findall(r'(?:search|list|top7_list|top_list|5min_list|long_list)-(\d+)\.htm', h)
        for pl in page_links:
            try:
                num = int(pl)
                if num > max_pg: max_pg = num
            except: pass
        
        # 兜底：仅当一页都解析不出页码时兜底
        if max_pg <= current_pg:
            max_pg = current_pg + 20
        
        return max_pg

    def homeContent(self, filter=False):
        cs = [{"type_id": k, "type_name": v} for k, v in CATS.items()]
        # subtitle 用于首页标题栏显示
        return {"class": cs, "subtitle": "片吧365"}

    def homeVideoContent(self):
        h = self._get("/list-1.htm")
        return {"list": self._cards(h)[:30] if h else []}

    def categoryContent(self, tid, pg=1, filter=False, extend=None):
        try:
            pn = max(int(str(pg)), 1)
            base = tid if tid in CATS else "list"
            h = self._get("/" + base + "-" + str(pn) + ".htm")
            if not h: return {"list": [], "page": pn, "pagecount": 1}
            total = self._parse_pagecount(h, pn)
            return {"list": self._cards(h), "page": pn, "pagecount": total, "limit": 20}
        except Exception as e:
            return {"list": [], "page": pg, "pagecount": 1}

    def detailContent(self, ids):
        try:
            vid = ids[0]
            h = self._get(vid)
            if not h: return {"list": []}
            tm = re.search(r'panel-title">\s*([^<]+)', h)
            if not tm: tm = re.search(r'og:title"\s+content="([^"]+)"', h)
            title = tm.group(1).strip() if tm else ""
            if not title:
                tm = re.search(r'<title>(.*?)\s*-', h)
                title = tm.group(1).strip() if tm else ""
            pm = re.search(r'og:image"\s+content="([^"]+)"', h)
            pic = pm.group(1) if pm else ""
            km = re.search(r'keywords"\s+content="([^"]*)"', h)
            kw = km.group(1) if km else ""
            dm = re.search(r'duration"\s+content="([^"]*)"', h)
            dur = dm.group(1) if dm else ""
            am = re.search(r'作者：<a[^>]*>([^<]+)', h)
            author = am.group(1).strip() if am else ""
            content = " | ".join(a for a in [author, dur] if a)
            sm = re.search(r'src="(https?://[^"]+\.m3u8[^"]*)"', h)
            if not sm: sm = re.search(r'(https?://[^\s"\']+\.m3u8)', h)
            stream = sm.group(1) if sm else vid
            vod = {
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_area": "中国",
                "vod_remarks": kw,
                "subtitle": content,
                "vod_content": content,
                "vod_play_from": "片吧365",
                "vod_play_url": "第1集$" + stream
            }
            return {"list": [vod]}
        except Exception as e:
            return {"list": []}

    def searchContent(self, key, quick=False, pg=1):
        try:
            pn = max(int(str(pg)), 1)
            path = "/search-" + str(pn) + ".htm?search=" + quote(key) if pn > 1 else "/search.htm?search=" + quote(key)
            h = self._get(path)
            if not h: return {"list": [], "page": pn, "pagecount": 1}
            total = self._parse_pagecount(h, pn)
            return {"list": self._cards(h), "page": pn, "pagecount": total, "limit": 20}
        except Exception as e:
            return {"list": [], "page": pg, "pagecount": 1}

    def searchContentPage(self, key, quick=False, pg=1):
        return self.searchContent(key, quick, pg)

    def playerContent(self, flag, id, vipFlags=None):
        if id and ".m3u8" in id:
            return {"parse": 0, "url": id, "header": json.dumps({"User-Agent": UA, "Referer": H + "/"}, ensure_ascii=False)}
        if "$" in id: id = id.split("$", 1)[1]
        if not id.startswith("http"): id = H + id
        d = self.detailContent([id])
        if d and d.get("list"):
            pu = d["list"][0].get("vod_play_url", "")
            if "$" in pu: pu = pu.split("$", 1)[1]
            if pu:
                return {"parse": 0, "url": pu, "header": json.dumps({"User-Agent": UA, "Referer": H + "/"}, ensure_ascii=False)}
        return {"url": id}
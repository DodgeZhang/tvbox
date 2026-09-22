# -*- coding: utf-8 -*-
# 儿童编程 TVBox Python 爬虫 (基于 base.spider 标准)
# 站点: https://www.bilibili.com/
# 分类: Scratch编程/Python入门/ScratchJr/少儿编程思维/乐高编程/micro:bit/Arduino/计算思维/信息学竞赛/编程动画/益智游戏/数学逻辑
# 数据: B站官方搜索接口
# 播放: 返回B站页面地址交由TVBox解析器解析播放
# 关注微信公众号"源力软件汇",更多优质资源尽在源力。
import re
import json
import ssl
import gzip
import time
import urllib.request
import urllib.parse

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
    BASE_URL = "https://api.bilibili.com"
    WEB = "https://www.bilibili.com"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    PROMO = '\n\n关注微信公众号"源力软件汇",更多优质资源尽在源力。'

    CATEGORIES = [
        {"type_id": "Scratch编程", "type_name": "Scratch编程"},
        {"type_id": "Python入门", "type_name": "Python入门"},
        {"type_id": "ScratchJr", "type_name": "ScratchJr"},
        {"type_id": "少儿编程思维", "type_name": "少儿编程思维"},
        {"type_id": "乐高编程", "type_name": "乐高编程"},
        {"type_id": "micro:bit", "type_name": "micro:bit"},
        {"type_id": "Arduino编程", "type_name": "Arduino编程"},
        {"type_id": "计算思维", "type_name": "计算思维"},
        {"type_id": "信息学竞赛", "type_name": "信息学竞赛"},
        {"type_id": "编程动画", "type_name": "编程动画"},
        {"type_id": "益智游戏", "type_name": "益智游戏"},
        {"type_id": "数学逻辑", "type_name": "数学逻辑"},
    ]

    def init(self, extend=""):
        pass

    def getName(self):
        return "儿童编程"

    def _get_html(self, url, ref=""):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        except Exception:
            ctx = None
        headers = {
            "User-Agent": self.UA,
            "Referer": ref or self.WEB + "/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Cookie": "buvid3=infoc; b_nut=1; _uuid=1",
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=15, context=ctx)
            data = resp.read()
            enc = resp.headers.get("Content-Encoding", "")
            if "gzip" in enc:
                try:
                    data = gzip.decompress(data)
                except Exception:
                    pass
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _clean(self, text):
        if not text:
            return ""
        text = str(text)
        text = text.replace("&#34;", '"').replace("&#39;", "'")
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&nbsp;", " ")
        text = re.sub(r"<[^>]+>", "", text)
        return re.sub(r"\s+", " ", text).strip()

    def _pic(self, u):
        u = u or ""
        if u.startswith("//"):
            return "https:" + u
        return u

    def _format_duration(self, d):
        if isinstance(d, (int, float)):
            m, s = divmod(int(d), 60)
            h, m = divmod(m, 60)
            return "%02d:%02d:%02d" % (h, m, s) if h else "%02d:%02d" % (m, s)
        return str(d) if d else ""

    def _search_videos(self, keyword, page=1, order="click"):
        url = "%s/x/web-interface/search/type?search_type=video&keyword=%s&page=%d&order=%s" % (
            self.BASE_URL, urllib.parse.quote(keyword), page, order)
        html = self._get_html(url)
        if not html:
            return [], 1, 0
        try:
            data = json.loads(html)
            items = data.get("data", {}).get("result", [])
            total = data.get("data", {}).get("numResults", 0)
            pages = data.get("data", {}).get("numPages", 1)
            return items, pages, total
        except Exception:
            return [], 1, 0

    def homeContent(self, filter):
        return {"class": self.CATEGORIES, "filters": {}}

    def homeVideoContent(self):
        result = {"list": []}
        try:
            items, _, _ = self._search_videos("儿童编程 scratch 少儿", 1, "click")
            for v in items[:30]:
                bvid = v.get("bvid", "")
                if not bvid:
                    continue
                title = self._clean(v.get("title", ""))
                pic = self._pic(v.get("pic", ""))
                duration = self._format_duration(v.get("duration", ""))
                play = v.get("play", 0)
                remarks = "%s播放" % self._format_num(play) if play else duration
                result["list"].append({
                    "vod_id": bvid,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks,
                })
        except Exception:
            pass
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": str(pg), "pagecount": "1", "total": "0"}
        page = int(pg) if str(pg).isdigit() else 1
        order = "click"
        if isinstance(extend, dict):
            order = extend.get("order", "click")
        elif isinstance(extend, str) and extend:
            try:
                ext = json.loads(extend)
                order = ext.get("order", "click")
            except Exception:
                pass
        try:
            items, pages, total = self._search_videos(tid, page, order)
            for v in items:
                bvid = v.get("bvid", "")
                if not bvid:
                    continue
                title = self._clean(v.get("title", ""))
                pic = self._pic(v.get("pic", ""))
                duration = self._format_duration(v.get("duration", ""))
                play = v.get("play", 0)
                remarks = "%s播放" % self._format_num(play) if play else duration
                result["list"].append({
                    "vod_id": bvid,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks,
                })
            result["pagecount"] = str(pages)
            result["total"] = str(total)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        result = {"list": []}
        bvid = ids[0] if isinstance(ids, list) and ids else ids
        bvid = str(bvid).strip()
        if not bvid:
            return result
        html = self._get_html("%s/x/web-interface/view?bvid=%s" % (self.BASE_URL, bvid))
        if not html:
            return result
        try:
            data = json.loads(html)
            if data.get("code") != 0:
                return result
            vd = data.get("data", {})
            title = self._clean(vd.get("title", ""))
            pic = self._pic(vd.get("pic", ""))
            desc = self._clean(vd.get("desc", ""))
            owner = vd.get("owner", {})
            author = owner.get("name", "") if owner else ""
            tname = vd.get("tname", "")
            stat = vd.get("stat", {})
            view = stat.get("view", 0)
            danmaku = stat.get("danmaku", 0)
            like = stat.get("like", 0)
            favorite = stat.get("favorite", 0)
            pubdate = vd.get("pubdate", 0)
            pub_time = ""
            if pubdate:
                try:
                    pub_time = time.strftime("%Y-%m-%d", time.localtime(pubdate))
                except Exception:
                    pass
            info_lines = []
            if author:
                info_lines.append("UP主: %s" % author)
            if tname:
                info_lines.append("分区: %s" % tname)
            if pub_time:
                info_lines.append("发布: %s" % pub_time)
            info_lines.append("播放: %s | 弹幕: %s | 点赞: %s | 收藏: %s" % (
                self._format_num(view), self._format_num(danmaku),
                self._format_num(like), self._format_num(favorite)))
            detail = "\n".join(info_lines)
            if desc:
                detail += "\n简介: " + desc
            detail += self.PROMO
            pages = vd.get("pages", [])
            play_urls = []
            for p in pages:
                cid = p.get("cid", 0)
                part = self._clean(p.get("part", ""))
                label = part if part else "P%d" % (p.get("page", 0))
                play_urls.append("%s$%s_%s" % (label, bvid, cid))
            vod = {
                "vod_id": bvid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_actor": author,
                "vod_director": author,
                "vod_content": detail,
                "vod_remarks": tname,
                "vod_year": pub_time[:4] if pub_time else "",
                "vod_area": "中国",
                "vod_play_from": "儿童编程[源力软件汇]",
                "vod_play_url": "#".join(play_urls) if play_urls else "",
            }
            result["list"] = [vod]
        except Exception:
            pass
        return result


    def playerContent(self, flag, id, vipFlags):
        parts = str(id).split("_")
        if len(parts) < 2:
            return {"jx": 0, "parse": 0, "url": "", "header": ""}
        bvid = parts[0]
        cid = parts[1]
        try:
            api = "%s/x/player/playurl?bvid=%s&cid=%s&qn=80&platform=html5&otype=json&high_quality=1" % (
                self.BASE_URL, bvid, cid)
            html = self._get_html(api, self.WEB + "/")
            if html:
                data = json.loads(html)
                if data.get("code") == 0:
                    dd = data.get("data", {})
                    durl = dd.get("durl", [])
                    if durl and durl[0].get("url"):
                        video_url = durl[0]["url"]
                        header = json.dumps({
                            "User-Agent": self.UA,
                            "Referer": self.WEB + "/",
                            "Origin": self.WEB,
                        })
                        return {"jx": 0, "parse": 0, "url": video_url, "header": header}
        except Exception:
            pass
        return {"jx": 0, "parse": 0, "url": "", "header": ""}

    def searchContent(self, key, quick, pg="1"):
        result = {"list": [], "page": str(pg), "pagecount": "1", "total": "0"}
        page = int(pg) if str(pg).isdigit() else 1
        try:
            items, pages, total = self._search_videos(key, page)
            for v in items:
                bvid = v.get("bvid", "")
                if not bvid:
                    continue
                title = self._clean(v.get("title", ""))
                pic = self._pic(v.get("pic", ""))
                duration = self._format_duration(v.get("duration", ""))
                play = v.get("play", 0)
                author = v.get("author", "")
                remarks = "%s播放" % self._format_num(play) if play else duration
                if author:
                    remarks = "%s | %s" % (author, remarks)
                result["list"].append({
                    "vod_id": bvid,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks,
                })
            result["pagecount"] = str(pages)
            result["total"] = str(total)
        except Exception:
            pass
        return result

    @staticmethod
    def _format_num(n):
        try:
            n = int(n)
        except Exception:
            return str(n)
        if n >= 100000000:
            return "%.1f亿" % (n / 100000000)
        if n >= 10000:
            return "%.1f万" % (n / 10000)
        return str(n)

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

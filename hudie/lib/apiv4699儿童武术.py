# -*- coding: utf-8 -*-
# 儿童武术 TVBox Python 爬虫 (基于 base.spider 标准)
# 站点: https://www.bilibili.com/
# 分类: 儿童武术/少儿武术/幼儿武术/武术教学/少儿跆拳道/少儿散打/儿童体能/少儿搏击/幼儿体操/儿童长拳/少儿太极/少儿形意拳
# 数据: B站官方搜索接口
# 播放: 直接返回真实视频播放地址(html5 MP4 / DASH), 无需任何解析, 在TVBox可直接播放
# 功能: 获取全部分类数据 + 支持搜索 B站视频
# 关注微信公众号"源力软件汇",更多优质资源尽在源力。
import re
import json
import ssl
import gzip
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

    PROMO = '\n\n\u5fae\u4fe1\u516c\u4f17\u53f7\u201c\u6e90\u529b\u8f6f\u4ef6\u6c47\u201d,\u66f4\u591a\u4f18\u8d28\u8d44\u6e90\u5c3d\u5728\u6e90\u529b\u3002'

    CATEGORIES = [
        {"type_id": "\u513f\u7ae5\u6b66\u672f", "type_name": "\u513f\u7ae5\u6b66\u672f"},
        {"type_id": "\u5c11\u513f\u6b66\u672f", "type_name": "\u5c11\u513f\u6b66\u672f"},
        {"type_id": "\u5e7c\u513f\u6b66\u672f", "type_name": "\u5e7c\u513f\u6b66\u672f"},
        {"type_id": "\u6b66\u672f\u6559\u5b66", "type_name": "\u6b66\u672f\u6559\u5b66"},
        {"type_id": "\u5c11\u513f\u8df5\u6728\u9053", "type_name": "\u5c11\u513f\u8df5\u6728\u9053"},
        {"type_id": "\u5c11\u513f\u6563\u6253", "type_name": "\u5c11\u513f\u6563\u6253"},
        {"type_id": "\u513f\u7ae5\u4f53\u80fd", "type_name": "\u513f\u7ae5\u4f53\u80fd"},
        {"type_id": "\u5c11\u513f\u640f\u51fb", "type_name": "\u5c11\u513f\u640f\u51fb"},
        {"type_id": "\u5e7c\u513f\u4f53\u64cd", "type_name": "\u5e7c\u513f\u4f53\u64cd"},
        {"type_id": "\u513f\u7ae5\u957f\u62f3", "type_name": "\u513f\u7ae5\u957f\u62f3"},
        {"type_id": "\u5c11\u513f\u592a\u6781", "type_name": "\u5c11\u513f\u592a\u6781"},
        {"type_id": "\u5c11\u513f\u5f62\u610f\u62f3", "type_name": "\u5c11\u513f\u5f62\u610f\u62f3"},
    ]

    FILTERS = {
        "\u513f\u7ae5\u6b66\u672f": [
            {"key": "order", "name": "\u6392\u5e8f", "value": [
                {"n": "\u7efc\u5408\u6392\u5e8f", "v": "0"},
                {"n": "\u6700\u65b0\u53d1\u5e03", "v": "pubdate"},
                {"n": "\u6700\u591a\u64ad\u653e", "v": "click"},
                {"n": "\u6700\u591a\u5f39\u5e55", "v": "dm"}]},
            {"key": "duration", "name": "\u65f6\u957f", "value": [
                {"n": "\u5168\u90e8", "v": "0"},
                {"n": "60\u5206\u949f\u4ee5\u4e0a", "v": "4"},
                {"n": "30~60\u5206\u949f", "v": "3"},
                {"n": "10~30\u5206\u949f", "v": "2"},
                {"n": "10\u5206\u949f\u4ee5\u4e0b", "v": "1"}]},
        ],
    }

    def init(self, extend=""):
        pass

    def getName(self):
        return "\u513f\u7ae5\u6b66\u672f"

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

    @staticmethod
    def _format_num(n):
        try:
            n = int(n)
        except Exception:
            return str(n)
        if n >= 100000000:
            return "%.1f\u4ebf" % (n / 100000000)
        if n >= 10000:
            return "%.1f\u4e07" % (n / 10000)
        return str(n)

    def _search_videos(self, keyword, page=1, order="click", duration="0"):
        url = "%s/x/web-interface/search/type?search_type=video&keyword=%s&page=%d&order=%s&duration=%s" % (
            self.BASE_URL, urllib.parse.quote(keyword), page, order, duration)
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
        return {"class": self.CATEGORIES, "filters": self.FILTERS}

    def homeVideoContent(self):
        result = {"list": []}
        try:
            items, _, _ = self._search_videos("\u513f\u7ae5\u6b66\u672f \u5c11\u513f\u6b66\u672f \u6559\u5b66", 1, "click")
            for v in items[:30]:
                bvid = v.get("bvid", "")
                if not bvid:
                    continue
                title = self._clean(v.get("title", ""))
                pic = self._pic(v.get("pic", ""))
                duration = self._format_duration(v.get("duration", ""))
                play = v.get("play", 0)
                remarks = "%s\u64ad\u653e" % self._format_num(play) if play else duration
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
        duration = "0"
        if isinstance(extend, dict):
            order = extend.get("order", "click")
            duration = extend.get("duration", "0")
        elif isinstance(extend, str) and extend:
            try:
                ext = json.loads(extend)
                order = ext.get("order", "click")
                duration = ext.get("duration", "0")
            except Exception:
                pass
        try:
            items, pages, total = self._search_videos(tid, page, order, duration)
            for v in items:
                bvid = v.get("bvid", "")
                if not bvid:
                    continue
                title = self._clean(v.get("title", ""))
                pic = self._pic(v.get("pic", ""))
                duration = self._format_duration(v.get("duration", ""))
                play = v.get("play", 0)
                remarks = "%s\u64ad\u653e" % self._format_num(play) if play else duration
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
                    import time
                    pub_time = time.strftime("%Y-%m-%d", time.localtime(pubdate))
                except Exception:
                    pass
            info_lines = []
            if author:
                info_lines.append("UP\u4e3b: %s" % author)
            if tname:
                info_lines.append("\u5206\u533a: %s" % tname)
            if pub_time:
                info_lines.append("\u53d1\u5e03: %s" % pub_time)
            info_lines.append("\u64ad\u653e: %s | \u5f39\u5e55: %s | \u70b9\u8d5e: %s | \u6536\u85cf: %s" % (
                self._format_num(view), self._format_num(danmaku),
                self._format_num(like), self._format_num(favorite)))
            detail = "\n".join(info_lines)
            if desc:
                detail += "\n\u7b80\u4ecb: " + desc
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
                "vod_area": "\u4e2d\u56fd",
                "vod_play_from": "\u513f\u7ae5\u6b66\u672f[\u6e90\u529b\u8f6f\u4ef6\u6c47]",
                "vod_play_url": "#".join(play_urls) if play_urls else "",
            }
            result["list"] = [vod]
        except Exception:
            pass
        return result

    def _get_play_url(self, bvid, cid):
        play_header = {"User-Agent": self.UA, "Referer": self.WEB + "/", "Origin": self.WEB}
        api = "%s/x/player/playurl?bvid=%s&cid=%s&qn=80&platform=html5&otype=json&high_quality=1" % (
            self.BASE_URL, bvid, cid)
        html = self._get_html(api, self.WEB + "/")
        if html:
            try:
                data = json.loads(html)
                if data.get("code") == 0:
                    dd = data.get("data", {})
                    durl = dd.get("durl", [])
                    if durl and durl[0].get("url"):
                        video_url = durl[0]["url"]
                        return video_url, play_header
            except Exception:
                pass
        api2 = "%s/x/player/playurl?bvid=%s&cid=%s&qn=80&fnval=16&fourk=1" % (
            self.BASE_URL, bvid, cid)
        html2 = self._get_html(api2, self.WEB + "/")
        if html2:
            try:
                data = json.loads(html2)
                if data.get("code") == 0:
                    dd = data.get("data", {})
                    dash = dd.get("dash", {})
                    videos = dash.get("video", [])
                    audios = dash.get("audio", [])
                    if videos:
                        video_url = videos[0].get("baseUrl") or videos[0].get("base_url", "")
                        return video_url, play_header
            except Exception:
                pass
        return None, play_header

    def playerContent(self, flag, id, vipFlags):
        play_header = {"User-Agent": self.UA, "Referer": self.WEB + "/", "Origin": self.WEB}
        parts = str(id).split("_")
        if len(parts) < 2:
            bvid = parts[0]
            html = self._get_html("%s/x/web-interface/view?bvid=%s" % (self.BASE_URL, bvid))
            cid = ""
            if html:
                try:
                    vd = json.loads(html).get("data", {})
                    cid = str(vd.get("cid", ""))
                except Exception:
                    pass
            if not cid:
                return {"url": "%s/video/%s" % (self.WEB, bvid), "parse": "0",
                        "header": json.dumps(play_header)}
            video_url, headers = self._get_play_url(bvid, cid)
            if video_url:
                return {"url": video_url, "parse": "0", "header": json.dumps(headers)}
            return {"url": "%s/video/%s" % (self.WEB, bvid), "parse": "1",
                    "header": json.dumps(play_header)}
        bvid = parts[0]
        cid = parts[1]
        video_url, headers = self._get_play_url(bvid, cid)
        if video_url:
            return {"url": video_url, "parse": "0", "header": json.dumps(headers)}
        page_url = "%s/video/%s?cid=%s" % (self.WEB, bvid, cid)
        conf = {"jx": 1, "parse": 1, "url": page_url, "header": json.dumps(play_header)}
        return conf

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
                remarks = "%s\u64ad\u653e" % self._format_num(play) if play else duration
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

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False


if __name__ == "__main__":
    sp = Spider()
    sp.init("")

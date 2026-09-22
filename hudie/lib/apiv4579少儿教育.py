# -*- coding: utf-8 -*-
# 少儿教育 TVBox Python 爬虫 (基于 base.spider 标准)
# 站点: https://www.bilibili.com/
# 分类: 儿歌动画/童话故事/科普知识/幼儿启蒙/早教知识/儿童绘画/儿童英语/安全教育/儿童手工/亲子游戏/成语故事/数学启蒙
# 数据: B站官方搜索接口
# 播放: 返回B站页面地址交由TVBox解析器解析播放
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

    PROMO = '\n\n关注微信公众号"源力软件汇",更多优质资源尽在源力。'

    CATEGORIES = [
        {"type_id": "儿歌动画", "type_name": "儿歌动画"},
        {"type_id": "童话故事", "type_name": "童话故事"},
        {"type_id": "科普知识", "type_name": "科普知识"},
        {"type_id": "幼儿启蒙", "type_name": "幼儿启蒙"},
        {"type_id": "早教知识", "type_name": "早教知识"},
        {"type_id": "儿童绘画", "type_name": "儿童绘画"},
        {"type_id": "儿童英语", "type_name": "儿童英语"},
        {"type_id": "安全教育", "type_name": "安全教育"},
        {"type_id": "儿童手工", "type_name": "儿童手工"},
        {"type_id": "亲子游戏", "type_name": "亲子游戏"},
        {"type_id": "成语故事", "type_name": "成语故事"},
        {"type_id": "数学启蒙", "type_name": "数学启蒙"},
    ]

    def init(self, extend=""):
        pass

    def getName(self):
        return "少儿教育"

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
            items, _, _ = self._search_videos("少儿教育 儿歌 动画", 1, "click")
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
                    import time
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
                "vod_play_from": "少儿教育[源力软件汇]",
                "vod_play_url": "#".join(play_urls) if play_urls else "",
            }
            result["list"] = [vod]
        except Exception:
            pass
        return result

    def _get_play_url(self, bvid, cid):
        play_header = {"User-Agent": self.UA, "Referer": self.WEB + "/", "Origin": self.WEB}
        # 方式1: html5模式 直接拿durl MP4地址
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
        # 方式2: web模式 DASH (回退)
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
                        audio_url = audios[0].get("baseUrl") or audios[0].get("base_url", "") if audios else ""
                        if video_url:
                            return video_url, play_header
            except Exception:
                pass
        return None, play_header

    def playerContent(self, flag, id, vipFlags):
        play_header = {"User-Agent": self.UA, "Referer": self.WEB + "/", "Origin": self.WEB}
        parts = str(id).split("_")
        if len(parts) < 2:
            bvid = parts[0]
            # 没有cid, 先从view接口获取cid
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
        # 最终回退: 解析
        page_url = "%s/video/%s?cid=%s" % (self.WEB, bvid, cid)
        conf = {"jx": 1, "parse": 1, "url": page_url, "header": json.dumps(play_header)}
        try:
            conf["danmaku"] = "https://183933.xyz/dm/dm.php?url=%s/video/%s" % (self.WEB, bvid)
        except Exception:
            pass
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

# -*- coding: utf-8 -*-
# juok3.top(剧OK) TVBox Spider —— Next.js 站点, 使用站内 JSON API
# 数据链路:
#   列表/分类: GET /api/filter?catId={1电影|2电视剧|3综艺|4动漫}&page={N}
#   详情:      GET /api/detail?cat={catId}&id={videoId}
#             - 电影/单集: data.playlinksdetail.{site}.default_url (源站播放页)
#             - 剧集:      data.allepidetail.{site}[].{playlink_num,url}
#   播放:      POST /api/player/resolve {playUrl, site} -> {url: m3u8 直链}
#   搜索:      GET /search?q={kw} (SSR 渲染 /detail/external/{site}/{id} 第三方卡片)
# 反爬: 首次请求需 GET 首页换取 server_name_session cookie (见 _ensure_cookie)
# 依赖: requests (无第三方 BS4/curl_cffi)
# 用法: 放到 plugin/ 目录, TVBox 配置:
#   {
#     "key": "py_juok3", "name": "剧OK", "type": 3,
#     "api": "http://你的服务器地址/py_juok3",
#     "searchable": 1, "quickSearch": 1,
#     "filterable": 0
#   }
import json
import re
import sys
import time

import requests

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""):
            pass

        def getName(self):
            return "剧OK"

        def isVideoFormat(self, url):
            return False

        def manualVideoCheck(self):
            return False

        def destroy(self):
            pass

        def localProxy(self, param):
            return None

        def homeContent(self, filter):
            return {"class": [], "list": [], "filters": {}}

        def homeVideoContent(self):
            return {"list": []}

        def categoryContent(self, tid, pg, filter, extend):
            return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 0, "total": 0}

        def detailContent(self, ids):
            return {"list": []}

        def searchContent(self, key, quick, pg="1"):
            return {"list": [], "page": int(pg or 1)}

        def playerContent(self, flag, id, vipFlags):
            return {"parse": 0, "url": id or "", "header": {}}


HOST = "https://juok3.top"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 站内分类: (key, catId, 名称)
CATS = [
    ("movie", 1, "电影"),
    ("tv", 2, "电视剧"),
    ("variety", 3, "综艺"),
    ("anime", 4, "动漫"),
]
# 播放源中文名映射(来自 payload playSources)
SITE_NAMES = {
    "qiyi": "爱奇艺", "youku": "优酷", "qq": "腾讯视频", "mgtv": "芒果TV",
    "imgo": "芒果TV", "bilibili": "B站", "bilibili1": "B站", "douyin": "抖音",
    "leshi": "乐视", "cntv": "CCTV", "sohu": "搜狐", "pptv": "PPTV",
    "le": "乐视", "wasu": "华数", "1905": "1905电影网",
}


def _extract_rsc_payload(html):
    """拼接 Next.js self.__next_f.push 的 RSC 流并反转义。"""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    if not chunks:
        return ""
    joined = "".join(chunks)
    try:
        joined = joined.encode().decode("unicode_escape", errors="ignore")
    except Exception:
        pass
    return joined


class Spider(BaseSpider):
    name = "剧OK"

    def getName(self):
        return self.name

    def init(self, extend=""):
        ext = {}
        if extend:
            try:
                ext = json.loads(extend) if str(extend).strip().startswith("{") else {}
            except Exception:
                ext = {}
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
        self._resolve_cache = {}

    def _ensure_cookie(self):
        """站点有 JS 重定向防护: 先 GET 一次首页拿 server_name_session cookie 再正常请求。"""
        if self._cookie_ok:
            return
        try:
            self.session.get(self.host + "/", timeout=self.timeout, verify=False)
        except Exception:
            pass
        self._cookie_ok = True

    def _get(self, url, timeout=None):
        self._ensure_cookie()
        try:
            r = self.session.get(url, timeout=timeout or self.timeout, verify=False)
            r.encoding = "utf-8"
            return r.text or ""
        except Exception:
            return ""

    def _post_json(self, url, data):
        try:
            r = self.session.post(url, json=data, timeout=self.timeout, verify=False)
            return r.json() if r.text else {}
        except Exception:
            return {}

    def _abs(self, u):
        if not u:
            return ""
        if u.startswith("http"):
            return u
        if u.startswith("//"):
            return "https:" + u
        return self.host + u

    # ---------- 列表卡片解析(首页/分类/搜索共用) ----------
    def _parse_cards(self, html):
        """解析 <a href="/detail/{cat}/{vid}"> 卡片, 内含 <img> 与标题。"""
        out = []
        for m in re.finditer(
            r'<a[^>]+href="(/detail/(\d+)/([A-Za-z0-9]+))"[^>]*>(.*?)</a>',
            html, re.S):
            href, cat, vid, body = m.group(1), m.group(2), m.group(3), m.group(4)
            img = ""
            mi = re.search(r'<img[^>]+src="([^"]+)"', body)
            if mi:
                img = mi.group(1)
            title = ""
            mt = re.search(r'<h([123])[^>]*>(?:<[^>]+>)*([^<]+)', body)
            if mt:
                title = mt.group(2).strip()
            if not title:
                mt = re.search(r'title="([^"]+)"', body)
                if mt:
                    title = mt.group(1).strip()
            if not title:
                continue
            remark = ""
            mr = re.search(r'<span[^>]*class="[^"]*remark[^"]*"[^>]*>([^<]+)</span>', body)
            if mr:
                remark = mr.group(1).strip()
            out.append({
                "vod_id": f"{cat}/{vid}",
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": remark,
            })
        # 去重(保持顺序)
        seen, uniq = set(), []
        for v in out:
            if v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                uniq.append(v)
        return uniq

    # ---------- 首页 ----------
    def homeContent(self, filter):
        classes = [{"type_id": c[0], "type_name": c[2]} for c in CATS]
        # 首页推荐: 从每个分类取前几条，拼副标题(类型/集数)
        recs = []
        try:
            for cat_id, cat_name in [(1, ""), (2, ""), (3, ""), (4, "")]:
                movies, _, _ = self._filter_list(cat_id, 1)
                for m in movies[:6]:
                    m["vod_remarks"] = self._build_remark(m, cat_id)
                    recs.append(m)
        except Exception:
            pass
        # 降级: 尝试解析首页 HTML 卡片
        if not recs:
            html = self._get(self.host + "/")
            recs = self._parse_cards(html)[:30]
        return {"class": classes, "list": recs[:30], "filters": {}}

    def homeVideoContent(self):
        recs = []
        try:
            for cat_id in (1, 2):
                movies, _, _ = self._filter_list(cat_id, 1)
                for m in movies[:6]:
                    m["vod_remarks"] = self._build_remark(m, cat_id)
                    recs.append(m)
        except Exception:
            pass
        if not recs:
            html = self._get(self.host + "/")
            recs = self._parse_cards(html)[:30]
        return {"list": recs[:30]}

    def _build_remark(self, item, cat_id):
        """智能构建副标题，结合多个数据源"""
        parts = []
        total = item.get("total") if isinstance(item, dict) else None
        upinfo = item.get("upinfo") if isinstance(item, dict) else None
        mc = item.get("moviecategory") if isinstance(item, dict) else None
        desc = item.get("description") if isinstance(item, dict) else ""
        
        # 1. 类型信息提取
        type_str = ""
        if isinstance(mc, list) and mc:
            type_str = mc[0]
        elif isinstance(mc, str) and mc:
            type_str = mc
        elif desc:
            # 从剧情简介中智能提取类型关键词 - 优化规则
            type_keywords = {
                '犯罪': ['犯罪', '黑帮', '警匪', '卧底', '缉毒', '劫案', '谋杀'],
                '动作': ['动作', '功夫', '打斗', '枪战', '战斗'],
                '爱情': ['爱情', '都市', '言情', '情感', '恋爱', '浪漫'],
                '科幻': ['科幻', '未来', '太空', '外星', '时空'],
                '历史': ['历史', '古代', '王朝', '民国', '抗战', '革命'],
                '古装': ['古装', '武侠', '仙侠', '江湖', '江湖'],
                '悬疑': ['悬疑', '推理', '侦探', '谋杀', '迷案', '诡异'],
                '奇幻': ['奇幻', '魔法', '玄幻', '神魔', '修仙'],
                '喜剧': ['喜剧', '搞笑', '幽默', '笑料'],
                '恐怖': ['恐怖', '惊悚', '血腥', '鬼怪'],
                '谍战': ['谍战', '特工', '间谍', '情报'],
            }
            # 按优先级顺序查找
            priority_order = ['犯罪', '动作', '爱情', '科幻', '历史', '古装', '悬疑', '奇幻', '喜剧', '恐怖', '谍战']
            for keyword in priority_order:
                variants = type_keywords[keyword]
                if any(v in desc for v in variants):
                    type_str = keyword
                    break
        
        # 2. 集数/更新信息
        if cat_id in (2, 3, 4):  # 电视剧/综艺/动漫
            if total and upinfo and str(total) != str(upinfo):
                parts.insert(0, f"更新至{upinfo}集")
            elif total:
                parts.insert(0, f"全{total}集")
        
        # 3. 添加类型信息
        if type_str:
            parts.append(type_str)
        
        # 4. 如果构建失败，回退到已有的 vod_remarks
        if not parts:
            if isinstance(item, dict) and item.get("vod_remarks"):
                return item["vod_remarks"]
        
        return " ".join(parts)

    # ---------- 分类 ----------
    CATID = {c[0]: c[1] for c in CATS}  # movie->1, tv->2, variety->3, anime->4

    def _filter_list(self, cat_id, page):
        """调用站内 JSON 列表接口 /api/filter?catId={catId}&page={page}。
        返回 (videos, total, pagecount)。"""
        try:
            self._ensure_cookie()
            url = f"{self.host}/api/filter?catId={cat_id}&page={page}"
            r = self.session.get(url, timeout=self.timeout, verify=False)
            data = r.json() if r.text else {}
            movies = data.get("movies") or []
            videos = []
            for m in movies:
                vid = str(m.get("id") or "").strip()
                title = m.get("title") or ""
                if not vid or not title:
                    continue
                # 使用统一的副标题构建方法
                remark = self._build_remark(m, cat_id)
                videos.append({
                    "vod_id": f"{cat_id}/{vid}",
                    "vod_name": title,
                    "vod_pic": self._abs(m.get("cdncover") or m.get("cover") or ""),
                    "vod_remarks": remark,
                })
            total = int(data.get("total") or 0)
            pagecount = max(1, (total + 23) // 24)
            return videos, total, pagecount
        except Exception:
            return [], 0, 1

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)
            cat_id = self.CATID.get(str(tid), tid if str(tid).isdigit() else 1)
            videos, total, pagecount = self._filter_list(cat_id, pg)
            return {"list": videos, "page": pg, "pagecount": max(pagecount, pg),
                    "limit": len(videos), "total": total}
        except Exception:
            return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 0, "total": 0}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        try:
            vid = ids[0] if isinstance(ids, (list, tuple)) else ids
            vid = str(vid)
            # vod_id 形如 "cat/vid" 或 "external/site/id"(第三方) 或完整 URL
            if "external" in vid:
                return self._detail_external(vid)
            cat = 1
            if "/" in vid:
                parts = vid.split("/")
                cat = parts[0]
                video_id = parts[-1]
            else:
                video_id = vid
            if not video_id:
                return {"list": []}
            url = f"{self.host}/detail/{cat}/{video_id}"

            # 优先站内 JSON 详情接口
            vod = self._detail_api(cat, video_id, url)
            if vod:
                return {"list": [vod]}
            # 降级: HTML/RSC 解析
            html = self._get(url)
            if html:
                payload = _extract_rsc_payload(html)
                vod = self._parse_detail(payload, html, url)
                if vod:
                    return {"list": [vod]}
            return {"list": []}
        except Exception:
            return {"list": []}

    def _detail_api(self, cat, video_id, url):
        """调用 /api/detail?cat={cat}&id={id} 返回单个 vod dict 或 None。"""
        try:
            self._ensure_cookie()
            r = self.session.get(
                f"{self.host}/api/detail?cat={cat}&id={video_id}",
                timeout=self.timeout, verify=False)
            data = (r.json() or {}).get("data") or {}
            if not data or not data.get("title"):
                return None

            title = data.get("title", "")
            cover = self._abs(data.get("cdncover") or "")
            desc = (data.get("description") or "").strip().replace("\\n", "\n")
            director = data.get("director") or ""
            if isinstance(director, list):
                director = " / ".join(str(x) for x in director)
            else:
                director = str(director)
            actor = data.get("actor") or []
            if not isinstance(actor, list):
                actor = [str(actor)]
            actor = " / ".join(str(x) for x in actor)
            year = ""
            pd = data.get("pubdate") or ""
            ym = re.search(r"(\d{4})", str(pd))
            if ym:
                year = ym.group(1)
            area = data.get("area") or ""
            if not isinstance(area, str):
                area = " / ".join(str(x) for x in area) if isinstance(area, list) else str(area)
            mc = data.get("moviecategory") or ""
            cat_name = dict((str(c[1]), c[2]) for c in CATS).get(str(cat), mc)

            play_from, play_url = [], []

            # 1) 电视剧/多集: allepidetail.{site} 数组(每集 playlink_num+url)
            allep = data.get("allepidetail") or {}
            for site_key, eps in allep.items():
                eps = eps or []
                if not isinstance(eps, list) or not eps:
                    continue
                items = []
                for e in eps:
                    n = e.get("playlink_num") or e.get("id") or ""
                    u = e.get("url") or ""
                    if u:
                        items.append(f"{n}${u}")
                if items:
                    play_from.append(SITE_NAMES.get(site_key, site_key))
                    play_url.append("#".join(items))

            # 2) 电影/单集: playlinksdetail.{site}.default_url
            if not play_from:
                pld = data.get("playlinksdetail") or {}
                for site_key, info in pld.items():
                    du = (info or {}).get("default_url", "")
                    if du:
                        play_from.append(SITE_NAMES.get(site_key, site_key))
                        play_url.append(f"正片${du}")

            if not play_from:
                return None

            return {
                "vod_id": url,
                "vod_name": title,
                "vod_pic": cover,
                "vod_year": year,
                "vod_area": area,
                "vod_actor": actor,
                "vod_director": director,
                "vod_content": desc,
                "vod_remarks": f"{cat_name} {year}".strip(),
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url),
            }
        except Exception:
            return None

    def _detail_external(self, vid):
        """第三方(external)详情: /detail/external/{site}/{id}。
        该数据由页面 JS 从第三方 API 拉取, 这里降级为解析 SSR HTML 元数据。"""
        try:
            parts = vid.split("/")  # ['external', site, id]
            ext_id = parts[-1]
            url = f"{self.host}/detail/{vid}"
            html = self._get(url)
            if not html:
                return {"list": []}
            title = ""
            mt = re.search(r"<title>《([^》]+)》", html)
            if mt:
                title = mt.group(1)
            if not title:
                mt = re.search(r"<title>([^—《]+?)(?:-|【|《)", html)
                if mt:
                    title = mt.group(1).strip()
            vod = {
                "vod_id": url,
                "vod_name": title or str(ext_id),
                "vod_pic": "",
                "vod_content": "",
                "vod_play_from": "线路1",
                "vod_play_url": f"正片${url}",
                **{k: "" for k in ("vod_year", "vod_area", "vod_actor", "vod_director", "vod_remarks")},
            }
            return {"list": [vod]}
        except Exception:
            return {"list": []}

    def _parse_detail(self, payload, html, url):
        """从 RSC payload 提取详情。返回 vod dict 或 None。"""
        # 标题(优先 <title>《xx》..., 其次 payload)
        title = ""
        mt = re.search(r"<title>《([^》]+)》", html)
        if mt:
            title = mt.group(1).strip()

        # 海报
        cover = ""
        mc = re.search(r'"cdncover":"([^"]+)"', payload) or re.search(r'"cover":"(https?://[^"]+)"', payload)
        if mc:
            cover = mc.group(1)

        # 简介
        desc = ""
        md = re.search(r'"description":"(.*?)","dir"', payload, re.S)
        if md:
            desc = md.group(1).replace("\\n", "\n").replace("\\/", "/").strip()

        # 导演/演员/年份/地区/类型
        def _get_field(key):
            m = re.search(r'"%s":\[?"?([^"\]]*)"?\]?' % re.escape(key), payload)
            return m.group(1) if m else ""

        director = _get_field("director").replace("[", "").replace("]", "").replace(",", " / ")
        actor = _get_field("actor").replace("[", "").replace("]", "").replace(",", " / ")
        year = ""
        my = re.search(r'"pubdate":\s*"(\d{4})', payload)
        if my:
            year = my.group(1)
        area = _get_field("area").replace("[", "").replace("]", "").replace(",", " / ")
        cat = ""
        mc2 = re.search(r'"cat":(\d+)', payload)
        cat_id = mc2.group(1) if mc2 else "1"
        cat = dict((str(c[1]), c[2]) for c in CATS).get(cat_id, "")

        # ---------- 播放源与剧集 ----------
        # 1) 电视剧: initialEpisodes 带 url (站点源)
        play_from, play_url = [], []
        m_eps = re.search(r'"total":(\d+),"initialEpisodes":\[(.*?)\]\s*[,}]', payload, re.S)
        if m_eps and m_eps.group(2).strip():
            site_key = "qiyi"
            ms = re.search(r'"initialSite":"([a-z0-9]+)"', payload)
            if ms:
                site_key = ms.group(1)
            eps = re.findall(r'\{"id":"[^"]*","playlink_num":"(\d+)","url":"([^"]+)"', m_eps.group(2))
            if eps:
                site_name = SITE_NAMES.get(site_key) or site_key
                play_from.append(site_name)
                play_url.append("#".join("%s$%s" % (n, u) for n, u in eps))

        # 2) 电影: playlinksdetail {site: {default_url}}
        if not play_from:
            m_pld = re.search(r'"playlinksdetail":(\{.*?\})\s*[,}]', payload, re.S)
            if m_pld:
                try:
                    pld = json.loads(m_pld.group(1))
                except Exception:
                    pld = {}
                for site_key, info in pld.items():
                    du = (info or {}).get("default_url", "")
                    if du:
                        site_name = SITE_NAMES.get(site_key) or site_key
                        play_from.append(site_name)
                        play_url.append(f"正片${du}")

        # 3) 通用兜底: payload 中的播放页链接
        if not play_from:
            m_playlinks = re.finditer(r'"playlink_num":"(\d+)","url":"([^"]+)"', payload)
            eps = [(m.group(1), m.group(2)) for m in m_playlinks]
            if eps:
                site_name = "线路1"
                play_from.append(site_name)
                play_url.append("#".join("%s$%s" % (n, u) for n, u in eps))

        if not play_from:
            return None

        vod = {
            "vod_id": url,
            "vod_name": title or str(url.rsplit("/", 1)[-1]),
            "vod_pic": cover,
            "vod_year": year,
            "vod_area": area,
            "vod_actor": actor,
            "vod_director": director,
            "vod_content": desc,
            "vod_remarks": f"{cat} {year}".strip(),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return vod

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        """搜索结果由 SSR 渲染为 /detail/external/{site}/{id} 卡片, 解析 HTML。"""
        try:
            from urllib.parse import quote
            url = f"{self.host}/search?q={quote(str(key))}"
            html = self._get(url)
            return {"list": self._parse_external_cards(html), "page": int(pg or 1)}
        except Exception:
            return {"list": [], "page": int(pg or 1)}

    def _parse_external_cards(self, html):
        """解析搜索页第三方 external 卡片 与 标准 /detail/{cat}/{vid} 卡片。"""
        out = []
        # external 卡片: <a ... href="/detail/external/{site}/{id}"> <img> <h3>标题 </h3>
        for m in re.finditer(
            r'<a[^>]+href="(/detail/external/[A-Za-z0-9/]+)"[^>]*>(.*?)</a>', html, re.S):
            href, body = m.group(1), m.group(2)
            img = ""
            mi = re.search(r'<img[^>]+src="([^"]+)"', body)
            if mi:
                img = mi.group(1)
            title = ""
            mt = re.search(r'<h3[^>]*>(.*?)</h3>', body, re.S)
            if mt:
                title = re.sub(r"<[^>]+>", "", mt.group(1)).strip()
            if not title:
                mt = re.search(r'alt="([^"]+)"', body)
                if mt:
                    title = mt.group(1).strip()
            if not title:
                continue
            out.append({
                "vod_id": href.lstrip("/"),
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": "",
            })
        if out:
            return out
        # 降级: 标准 detail 卡片
        return self._parse_cards(html)

    # ---------- 播放 ----------
    # 站点全局解析线路配置(parseApis, 来自 RSC payload)
    PARSE_APIS = [
        ("X线路", "https://jx.xmflv.com/?url="),
        ("7解析", "https://jx.202617.xyz/tv.php?url="),
    ]

    def playerContent(self, flag, id, vipFlags):
        """id 可能是:
        1) m3u8/mp4 直链 -> 直接返回
        2) 站点原始播放页(http://www.iqiyi.com/...) -> 多线路解析
        3) 剧OK 页面 URL -> 多线路解析
        多线路优先级: 线路5(站内resolve) > X线路(jx.xmflv.com) > 7解析(jx.202617.xyz)
        """
        try:
            url = (id or "").strip()
            if not url:
                return {"parse": 0, "url": "", "header": {}}
            if url.startswith("//"):
                url = "https:" + url

            # 直链直接返回
            if re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", url, re.I):
                return {"parse": 0, "url": url, "header": {"User-Agent": UA, "Referer": self.host + "/"}}

            # 确定源站标识
            site = "qiyi"
            m_s = re.search(r"[?&]s=([a-z0-9]+)", url)
            if m_s:
                site = m_s.group(1)
            elif self.host in url and "/play/" in url:
                ms_play = re.search(r"/play/(?:external/)?([a-z0-9]+)", url)
                site = ms_play.group(1) if ms_play else "qiyi"
            elif "iqiyi" in url:
                site = "qiyi"
            elif "youku" in url:
                site = "youku"
            elif "qq.com" in url or "v.qq" in url:
                site = "qq"
            elif "mgtv" in url:
                site = "mgtv"
            elif "bilibili" in url:
                site = "bilibili"

            # ---- 线路5: 站内 resolve（本地解析器）----
            cache_key = (site, url)
            if cache_key in self._resolve_cache:
                resolved = self._resolve_cache[cache_key]
            else:
                resolved = self._post_json(self.host + "/api/player/resolve",
                                           {"playUrl": url, "site": site})
                self._resolve_cache[cache_key] = resolved
            if resolved.get("success") and resolved.get("url"):
                mu = resolved["url"]
                # resolve 返回 error.mp4 或 /error.mp4 视为失败
                if mu and "/error.mp4" not in mu and not mu.endswith("error.mp4"):
                    return {"parse": 0, "url": mu,
                            "header": {"User-Agent": UA, "Referer": self.host + "/"}}

            # ---- 降级到第三方解析线路 ----
            for line_name, api_base in self.PARSE_APIS:
                try:
                    parse_url = f"{api_base}{url}"
                    r = self.session.get(parse_url, timeout=self.timeout,
                                         verify=False, headers={"Referer": self.host + "/"})
                    r.encoding = "utf-8"
                    content = r.text or ""
                    # 从响应中提取 m3u8/mp4 直链
                    m3u8 = re.search(r'https?://[^"\'\\s]+\.m3u8[^"\'\\s]*', content)
                    if m3u8:
                        return {"parse": 0, "url": m3u8.group(0),
                                "header": {"User-Agent": UA, "Referer": api_base}}
                    mp4 = re.search(r'https?://[^"\'\\s]+\.mp4[^"\'\\s]*', content)
                    if mp4:
                        return {"parse": 0, "url": mp4.group(0),
                                "header": {"User-Agent": UA, "Referer": api_base}}
                except Exception:
                    continue

            # 所有线路都失败, 返回原 URL 让 TVBox 自行处理
            return {"parse": 1, "url": url, "header": {"User-Agent": UA, "Referer": self.host + "/"}}
        except Exception:
            return {"parse": 1, "url": id or "", "header": {"User-Agent": UA, "Referer": self.host + "/"}}

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


if __name__ == "__main__":
    # 简单自测
    s = Spider()
    s.init("")
    print("name:", s.getName())
    home = s.homeContent(False)
    print("home class:", [c["type_name"] for c in home["class"]])
    print("home list count:", len(home["list"]))
    if home["list"]:
        print("first:", home["list"][0])
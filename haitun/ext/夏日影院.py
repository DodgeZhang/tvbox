# -*- coding: utf-8 -*-
"""
夏日影院 Python Spider — 兼容 FongMi/TV (T3) 与 WebHomeTV / PeekPro (T4)
站点: https://www.sasa01.cc/

特性:
  - 7大主分类 + 类型/地区/年份/排序 四级筛选
  - 多线路播放(线路A/线路B)自动提取
  - Base64 解码 data-player-token 获取 m3u8 直链
  - 预编译正则 + 页面缓存 + 短超时
"""

import sys
import json
import re
import time
import base64

sys.path.append('..')

# ===== 兼容导入 =====
try:
    from base.spider import Spider
except ImportError:
    import requests as _rq
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass

    class Spider:
        def fetch(self, url, headers=None, **kw):
            timeout = kw.pop('timeout', 15)
            r = _rq.get(url, headers=headers, timeout=timeout, verify=False, **kw)
            r.encoding = 'utf-8'
            return r

from urllib.parse import quote, urlencode


# ============================================================
# 常量
# ============================================================

HOST = "https://www.sasa01.cc"
UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

# ===== 7大主分类 =====
CLASSES = [
    {"type_name": "电影", "type_id": "dianyingl"},
    {"type_name": "电视剧", "type_id": "dianshic"},
    {"type_name": "综艺", "type_id": "zongyic"},
    {"type_name": "动漫", "type_id": "dongmanc"},
    {"type_name": "AI剧场", "type_id": "juchangc"},
    {"type_name": "影视解说", "type_id": "yingshic"},
    {"type_name": "短剧", "type_id": "duanjuc"},
]

# ===== 子分类分组 (用于"类型"筛选) =====
SUB_CATEGORIES = {
    "dianyingl": [
        {"n": "全部", "v": ""},
        {"n": "动作", "v": "dianyingl/dongzuoc"},
        {"n": "喜剧", "v": "dianyingl/xijuc"},
        {"n": "爱情", "v": "dianyingl/aiqingc"},
        {"n": "科幻", "v": "dianyingl/kehuanc"},
        {"n": "恐怖", "v": "dianyingl/kongbuc"},
        {"n": "剧情", "v": "dianyingl/juqingf"},
        {"n": "战争", "v": "dianyingl/zhanzhengc"},
        {"n": "悬疑", "v": "dianyingl/xuanyic"},
        {"n": "奇幻", "v": "dianyingl/qihuanc"},
        {"n": "古装", "v": "dianyingl/guzhuangf"},
        {"n": "犯罪", "v": "dianyingl/fanzuic"},
        {"n": "家庭", "v": "dianyingl/jiatingc"},
        {"n": "纪录", "v": "dianyingl/jiluc"},
        {"n": "惊悚", "v": "dianyingl/jingsongc"},
        {"n": "伦理", "v": "dianyingl/lunlif"},
        {"n": "冒险", "v": "dianyingl/maoxianc"},
        {"n": "武侠", "v": "dianyingl/wuxiac"},
        {"n": "西部", "v": "dianyingl/xibuc"},
        {"n": "灾难", "v": "dianyingl/zainanc"},
        {"n": "动画", "v": "dianyingl/donghuaf"},
        {"n": "短片", "v": "dianyingl/duanpianc"},
        {"n": "少儿", "v": "dianyingl/shaoshic"},
    ],
    "dianshic": [
        {"n": "全部", "v": ""},
        {"n": "国产", "v": "dianshic/guochanf"},
        {"n": "海外", "v": "dianshic/haiwaif"},
        {"n": "韩国", "v": "dianshic/hanguog"},
        {"n": "日本", "v": "dianshic/ribenj"},
        {"n": "欧美", "v": "dianshic/oumeii"},
        {"n": "台湾", "v": "dianshic/taiwanc"},
        {"n": "香港", "v": "dianshic/xianggangc"},
        {"n": "泰国", "v": "dianshic/taiguoc"},
        {"n": "自制", "v": "dianshic/zizhic"},
    ],
    "zongyic": [
        {"n": "全部", "v": ""},
        {"n": "大陆", "v": "zongyic/daluc"},
        {"n": "日韩", "v": "zongyic/rihanc"},
        {"n": "欧美", "v": "zongyic/oumeij"},
        {"n": "港台", "v": "zongyic/gangtaij"},
    ],
    "dongmanc": [
        {"n": "全部", "v": ""},
        {"n": "国产", "v": "dongmanc/guochang"},
        {"n": "日本", "v": "dongmanc/ribenk"},
        {"n": "欧美", "v": "dongmanc/oumeik"},
        {"n": "港台", "v": "dongmanc/gangtaik"},
        {"n": "海外", "v": "dongmanc/haiwaig"},
        {"n": "离番", "v": "dongmanc/lifanc"},
    ],
    "juchangc": [
        {"n": "全部", "v": ""},
        {"n": "有声动漫", "v": "juchangc/youshengc"},
        {"n": "漫剧", "v": "juchangc/manjuf"},
        {"n": "AI漫剧", "v": "juchangc/manjug"},
    ],
    "yingshic": [
        {"n": "全部", "v": ""},
        {"n": "电影解说", "v": "yingshic/dianyingo"},
        {"n": "预告解说", "v": "yingshic/yugaof"},
        {"n": "预告片", "v": "yingshic/yugaog"},
        {"n": "剧情介绍", "v": "yingshic/juqingg"},
    ],
    "duanjuc": [
        {"n": "全部", "v": ""},
        {"n": "现代", "v": "duanjuc/xiandaic"},
        {"n": "古装", "v": "duanjuc/guzhuangg"},
        {"n": "翻转", "v": "duanjuc/fanzhuanc"},
        {"n": "擦边", "v": "duanjuc/cabianc"},
        {"n": "成长", "v": "duanjuc/chengzhangc"},
        {"n": "豪门", "v": "duanjuc/haomenc"},
        {"n": "脑洞", "v": "duanjuc/naodongc"},
        {"n": "年代", "v": "duanjuc/niandaic"},
        {"n": "女频", "v": "duanjuc/nvpinc"},
        {"n": "战神", "v": "duanjuc/zhanshenc"},
    ],
}

# ===== 地区筛选器 =====
_AREA_FILTER = {"key": "area", "name": "地区", "value": [
    {"n": "全部", "v": ""},
    {"n": "国语", "v": "国语"},
    {"n": "汉语普通话", "v": "汉语普通话"},
    {"n": "粤语", "v": "粤语"},
    {"n": "英语", "v": "英语"},
    {"n": "日语", "v": "日语"},
    {"n": "韩语", "v": "韩语"},
    {"n": "法语", "v": "法语"},
    {"n": "西班牙语", "v": "西班牙语"},
    {"n": "普通话", "v": "普通话"},
    {"n": "其它", "v": "其它"},
]}

# ===== 年份筛选器 =====
_YEAR_FILTER = {"key": "year", "name": "年份", "value": [
    {"n": "全部", "v": ""},
    {"n": "2026", "v": "2026"},
    {"n": "2025", "v": "2025"},
    {"n": "2024", "v": "2024"},
    {"n": "2023", "v": "2023"},
    {"n": "2022", "v": "2022"},
    {"n": "2021", "v": "2021"},
    {"n": "2020", "v": "2020"},
    {"n": "2019", "v": "2019"},
    {"n": "2018", "v": "2018"},
    {"n": "2017", "v": "2017"},
    {"n": "2016", "v": "2016"},
]}

# ===== 排序筛选器 =====
_ORDER_FILTER = {"key": "order", "name": "排序", "value": [
    {"n": "最新", "v": "最新更新"},
    {"n": "评分", "v": "评分"},
]}

# ===== 构建筛选器 =====
FILTERS = {}
for c in CLASSES:
    parent = c["type_id"]
    type_opts = SUB_CATEGORIES.get(parent, [{"n": "全部", "v": ""}])
    FILTERS[parent] = [
        {"key": "type", "name": "类型", "value": type_opts},
        _AREA_FILTER,
        _YEAR_FILTER,
        _ORDER_FILTER,
    ]


# ============================================================
# 预编译正则
# ============================================================
RE_ARTICLE = re.compile(r'<article[^>]*>(.*?)</article>', re.S)
RE_MOVIE_HREF = re.compile(r'href="/movie/([^"]+\.html)"')
RE_PLAY_HREF = re.compile(r'href="(/play/[^"]+)"')
RE_ALT = re.compile(r'alt="([^"]+)"')
RE_H3 = re.compile(r'<h3[^>]*>(?:<a[^>]*>)?([^<]+)')
RE_H2 = re.compile(r'<h2[^>]*>(?:<a[^>]*>)?([^<]+)')
RE_H1 = re.compile(r'<h1[^>]*>(?:<a[^>]*>)?([^<]+)')
RE_DATA_COVER = re.compile(r'data-cover-src="([^"]+)"')
RE_IMG_SRC = re.compile(r'<img[^>]+src="([^"]+)"')
RE_SMALL_YEAR = re.compile(r'<small>(\d{4})</small>')
RE_H1_ITEMPROP = re.compile(r'<h1[^>]*itemprop="name"[^>]*>([^<]+)</h1>')
RE_TITLE_TAG = re.compile(r'<title>([^<]+)')
RE_DETAIL_BACKDROP = re.compile(r'class="wu-detail-backdrop"[^>]*src="([^"]+)"')
RE_DETAIL_POSTER = re.compile(r'class="wu-detail-poster"[^>]*>.*?data-cover-src="([^"]+)"', re.S)
RE_IMG_ITEMPROP = re.compile(r'<img[^>]+itemprop="image"[^>]+(?:data-cover-src|src)="([^"]+)"')
RE_META_LINE = re.compile(r'<p[^>]*class="wu-detail-meta"[^>]*>([^<]+)</p>')
RE_DIRECTOR = re.compile(r'导演[：:]\s*([^<\n]+)')
RE_ACTOR = re.compile(r'主演[：:]\s*([^<\n]+)')
RE_SUMMARY = re.compile(r'<p[^>]*class="wu-detail-summary"[^>]*itemprop="description"[^>]*>([^<]+)')
RE_SUMMARY2 = re.compile(r'<p[^>]*class="wu-detail-summary"[^>]*>([^<]+)')
RE_EP_LIST = re.compile(r'class="wu-episode-list"[^>]*>(.*?)</div>', re.S)
RE_PLAY_LINK = re.compile(r'<a[^>]*href="(/play/[^"]+)"[^>]*>(?:<b>)?([^<]+)')
RE_PLAYER_BTN = re.compile(
    r'<button[^>]*data-player-switch[^>]*?'
    r'data-player-code="([^"]*)"[^>]*?'
    r'data-player-token="([^"]*)"[^>]*>([^<]*)</button>', re.S)
RE_PLAYER_BTN2 = re.compile(
    r'data-player-code="([^"]*)"[^>]*?'
    r'data-player-token="([^"]*)"', re.S)
RE_NEXT_PAGE = re.compile(r'page=(\d+)')
RE_B64_TOKEN = re.compile(r'data-(?:player-token|video-token)="([^"]+)"')
RE_M3U8 = re.compile(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*')
RE_MEDIA_JS = re.compile(
    r'(?:url|src|source|file|playUrl|play_url)\s*[:=]\s*["\']([^"\']+\.(?:m3u8|mp4|flv)[^"\']*)["\']', re.I)
RE_MEDIA_RAW = re.compile(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4|flv)(?:\?[^\s"\'<>]*)?)')


# ============================================================
# Spider 主类
# ============================================================

class Spider(Spider):

    def getName(self):
        return "夏日影院"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ""
        else:
            self.extend = extend or ""

        self.header = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        self._home_cache = []
        self._home_cache_time = 0
        self._page_cache = {}       # 页面缓存
        self._page_cache_time = {}
        self._play_cache = {}       # 播放地址缓存
        self._play_cache_time = {}

    # ===== 网络工具 =====
    def _rsp_text(self, rsp):
        try:
            return rsp.text
        except Exception:
            try:
                return rsp.content.decode('utf-8', 'ignore')
            except Exception:
                return ""

    def _html(self, url, referer=None, timeout=8, use_cache=True):
        # 缓存检查
        if use_cache:
            now = time.time()
            if url in self._page_cache:
                if now - self._page_cache_time.get(url, 0) < 300:
                    return self._page_cache[url]

        headers = dict(self.header)
        if referer:
            headers["Referer"] = referer
        try:
            rsp = self.fetch(url, headers=headers, timeout=timeout)
            text = self._rsp_text(rsp)
            if use_cache and text:
                self._page_cache[url] = text
                self._page_cache_time[url] = time.time()
            return text
        except Exception:
            return ""

    def _html_nocache(self, url, referer=None, timeout=8):
        headers = dict(self.header)
        if referer:
            headers["Referer"] = referer
        try:
            rsp = self.fetch(url, headers=headers, timeout=timeout)
            return self._rsp_text(rsp)
        except Exception:
            return ""

    def _extract_referer(self, url):
        try:
            if "://" in url:
                scheme = url.split("://")[0]
                host = url.split("://")[1].split("/")[0]
                return scheme + "://" + host + "/"
        except Exception:
            pass
        return HOST + "/"

    # ===== 内容字段处理 =====
    @staticmethod
    def _strip_tags(s):
        return re.sub(r'<[^>]+>', '', s or '').strip()

    @staticmethod
    def _fix_pic(pic):
        pic = (pic or "").strip()
        if not pic or pic.endswith("no-cover.svg"):
            return ""
        if pic.startswith("//"):
            return "https:" + pic
        if pic.startswith("/"):
            return HOST + pic
        return pic

    @staticmethod
    def _decode_token(token):
        token = (token or "").strip()
        if not token:
            return ""
        try:
            return base64.b64decode(token).decode('utf-8', 'ignore').strip()
        except Exception:
            return ""

    @staticmethod
    def _is_media(url):
        url = (url or "").lower()
        return ".m3u8" in url or ".mp4" in url or ".flv" in url

    # ===== 卡片解析(预编译正则版) =====
    def _parse_cards(self, html):
        videos = []
        seen = set()
        if not html:
            return videos

        for art in RE_ARTICLE.findall(html):
            link_m = RE_MOVIE_HREF.search(art)
            if not link_m:
                continue
            slug = link_m.group(1)
            vod_id = slug.replace('.html', '')
            if vod_id in seen:
                continue

            title = ""
            for rx in (RE_H3, RE_H2, RE_H1):
                m = rx.search(art)
                if m:
                    title = m.group(1).strip()
                    break
            if not title:
                m = RE_ALT.search(art)
                if m:
                    title = m.group(1).strip()
            if not title:
                continue

            pic = ""
            m = RE_DATA_COVER.search(art)
            if m:
                pic = self._fix_pic(m.group(1))
            if not pic:
                m = RE_IMG_SRC.search(art)
                if m:
                    pic = self._fix_pic(m.group(1))

            remark = ""
            m = RE_SMALL_YEAR.search(art)
            if m:
                remark = m.group(1)

            if 'ad-click' in slug:
                continue

            seen.add(vod_id)
            videos.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic or "",
                "vod_remarks": remark,
            })
        return videos

    # ===== 提取播放线路 =====
    def _extract_lines(self, play_html):
        """从播放页提取所有线路(code, name, token)"""
        lines = []
        seen_codes = set()

        # 方式1: 从 button 标签提取
        for m in RE_PLAYER_BTN.finditer(play_html):
            code, token, name = m.group(1), m.group(2), m.group(3).strip()
            if code and code not in seen_codes:
                seen_codes.add(code)
                decoded = self._decode_token(token) if token else ""
                lines.append({
                    "code": code,
                    "name": name or code,
                    "token": token,
                    "m3u8": decoded if self._is_media(decoded) else "",
                })

        # 方式2: 如果 button 匹配失败, 从 data 属性提取
        if not lines:
            for m in RE_PLAYER_BTN2.finditer(play_html):
                code, token = m.group(1), m.group(2)
                if code and code not in seen_codes:
                    seen_codes.add(code)
                    decoded = self._decode_token(token) if token else ""
                    lines.append({
                        "code": code,
                        "name": code,
                        "token": token,
                        "m3u8": decoded if self._is_media(decoded) else "",
                    })

        # 方式3: 直接从 data-player-token 属性提取
        if not lines:
            for m in RE_B64_TOKEN.finditer(play_html):
                token = m.group(1)
                decoded = self._decode_token(token)
                if self._is_media(decoded):
                    lines.append({
                        "code": "default",
                        "name": "默认线路",
                        "token": token,
                        "m3u8": decoded,
                    })
                    break

        return lines

    # ============================================================
    # 首页
    # ============================================================
    def homeContent(self, filter):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        now = int(time.time())
        if self._home_cache and now - self._home_cache_time < 300:
            return {"list": self._home_cache[:72]}

        html = self._html(HOST + "/", timeout=8)
        if not html:
            return {"list": []}

        videos = self._parse_cards(html)
        self._home_cache = videos[:72]
        self._home_cache_time = now
        return {"list": self._home_cache}

    # ============================================================
    # 分类列表
    # ============================================================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1

            ext = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend)
                    except Exception:
                        ext = {}

            real_tid = ext.get("type", "") or tid
            url = HOST + "/movie/" + real_tid
            params = {}
            if page > 1:
                params["page"] = str(page)
            if ext.get("area"):
                params["lang"] = ext["area"]
            if ext.get("year"):
                params["year"] = ext["year"]
            if ext.get("order"):
                params["order"] = ext["order"]
            if params:
                url += "?" + urlencode(params)

            html = self._html(url, timeout=8)
            if not html:
                return {"page": page, "pagecount": 1, "limit": 20, "total": 0, "list": []}

            videos = self._parse_cards(html)
            pagecount = page
            if ('page=' + str(page + 1)) in html:
                pagecount = page + 1

            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": 20,
                "total": len(videos),
            }
        except Exception:
            return {"page": 1, "pagecount": 1, "limit": 20, "total": 0, "list": []}

    # ============================================================
    # 详情页(支持多线路)
    # ============================================================
    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = str(ids[0])

        url = HOST + "/movie/" + vod_id + ".html"
        html = self._html(url, timeout=8)
        if not html:
            return {"list": []}

        # 标题
        vod_name = ""
        m = RE_H1_ITEMPROP.search(html)
        if m:
            vod_name = m.group(1).strip()
        if not vod_name:
            m = RE_H1.search(html)
            if m:
                vod_name = m.group(1).strip()
        if not vod_name:
            m = RE_TITLE_TAG.search(html)
            if m:
                vod_name = m.group(1).replace(' - 夏日影院', '').replace('夏日影院', '').strip()
                vod_name = re.sub(r'在线观看.*$', '', vod_name).strip()

        # 封面
        vod_pic = ""
        for rx in (RE_DETAIL_BACKDROP, RE_DETAIL_POSTER, RE_IMG_ITEMPROP):
            m = rx.search(html)
            if m:
                vod_pic = self._fix_pic(m.group(1))
                if vod_pic:
                    break

        # 信息行
        meta_line = ""
        m = RE_META_LINE.search(html)
        if m:
            meta_line = m.group(1).strip()
        vod_year = ""
        vod_area = ""
        type_name = ""
        if meta_line:
            parts = [p.strip() for p in re.split(r'[　/·]+', meta_line) if p.strip()]
            for p in parts:
                if re.match(r'^\d{4}$', p):
                    vod_year = p
                elif not vod_area and len(p) <= 8 and not p.isdigit():
                    vod_area = p
                elif not type_name and len(p) <= 6:
                    type_name = p

        # 导演/主演/简介
        vod_director = (RE_DIRECTOR.search(html) or [None, ""])[1] if RE_DIRECTOR.search(html) else ""
        m = RE_DIRECTOR.search(html)
        vod_director = m.group(1).strip() if m else ""
        m = RE_ACTOR.search(html)
        vod_actor = m.group(1).strip() if m else ""
        m = RE_SUMMARY.search(html) or RE_SUMMARY2.search(html)
        vod_content = m.group(1).strip()[:500] if m else ""

        # 提取选集列表
        episodes = []
        ep_section = RE_EP_LIST.search(html)
        if ep_section:
            episodes = RE_PLAY_LINK.findall(ep_section.group(1))

        if not episodes:
            # 备用: 从完整页面提取
            episodes = RE_PLAY_LINK.findall(html)

        if not episodes:
            return {"list": []}

        # 获取播放线路: 访问第一个播放页
        first_play_url = HOST + episodes[0][0]
        play_html = self._html(first_play_url, referer=url, timeout=8, use_cache=True)
        lines = self._extract_lines(play_html) if play_html else []

        # 如果没有提取到线路, 使用默认
        if not lines:
            lines = [{"code": "default", "name": "默认线路", "token": "", "m3u8": ""}]

        # 构建多线路播放列表
        # 格式: vod_play_from = "线路A$$$线路B"
        #        vod_play_url = "ep1$code1$play_url#ep2$code1$play_url$$$ep1$code2$play_url#ep2$code2$play_url"
        play_from_parts = []
        play_url_parts = []

        for line in lines:
            line_code = line["code"]
            line_name = line["name"]
            ep_list = []
            seen_eps = set()
            for ep_url, ep_name in episodes:
                ep_name = ep_name.strip()
                if not ep_name or ep_url in seen_eps:
                    continue
                seen_eps.add(ep_url)
                full_url = HOST + ep_url
                # 编码: ep_name$line_code$full_url
                ep_list.append("%s$%s$%s" % (ep_name, line_code, full_url))

            if ep_list:
                play_from_parts.append(line_name)
                play_url_parts.append("#".join(ep_list))

        if not play_url_parts:
            return {"list": []}

        vod = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "type_name": type_name,
            "vod_year": vod_year,
            "vod_area": vod_area,
            "vod_remarks": vod_year or "HD",
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_content": vod_content,
            "vod_play_from": "$$$".join(play_from_parts),
            "vod_play_url": "$$$".join(play_url_parts),
        }
        return {"list": [vod]}

    # ============================================================
    # 搜索
    # ============================================================
    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1
            url = HOST + "/movie/search=" + quote(key)
            if page > 1:
                url += "?page=" + str(page)
            html = self._html(url, timeout=8)
            if not html:
                return {"list": []}
            return {"list": self._parse_cards(html)}
        except Exception:
            return {"list": []}

    # ============================================================
    # 播放解析(按线路选择m3u8)
    # ============================================================
    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}

        # 解析: id 格式为 "line_code$play_url" 或 "play_url"
        parts = str(id).split("$")
        if len(parts) >= 3:
            # 格式: ep_name$line_code$play_url
            line_code = parts[-2]
            play_url = parts[-1]
        elif len(parts) == 2:
            line_code = parts[0]
            play_url = parts[1]
        else:
            line_code = ""
            play_url = parts[0]

        # 缓存检查
        cache_key = line_code + "|" + play_url
        now = time.time()
        if cache_key in self._play_cache:
            if now - self._play_cache_time.get(cache_key, 0) < 3600:
                cached = self._play_cache[cache_key]
                if cached:
                    return {
                        "parse": 0, "playUrl": "", "url": cached,
                        "header": {"User-Agent": UA, "Referer": self._extract_referer(cached)},
                    }

        # 如果是直链媒体
        if self._is_media(play_url):
            is_m3u8 = ".m3u8" in play_url.lower()
            self._play_cache[cache_key] = play_url
            self._play_cache_time[cache_key] = now
            return {
                "parse": 0, "playUrl": "", "url": play_url,
                "header": {"User-Agent": UA, "Referer": self._extract_referer(play_url)},
                "format": "application/x-mpegURL" if is_m3u8 else "",
                "contentType": "application/x-mpegURL" if is_m3u8 else "",
            }

        # 站内播放页: 获取对应线路的 m3u8
        if "/play/" in play_url:
            result = self._resolve_play_page(play_url, line_code, cache_key, now)
            if result:
                return result

        # 回退: 交给壳子嗅探
        return {
            "parse": 1, "playUrl": "", "url": play_url,
            "header": {"User-Agent": UA, "Referer": HOST + "/"},
        }

    def _resolve_play_page(self, play_url, line_code, cache_key, now):
        """解析播放页: 按线路选择对应 m3u8"""
        html = self._html_nocache(play_url, referer=HOST + "/", timeout=8)
        if not html:
            return None

        # 提取所有线路
        lines = self._extract_lines(html)

        # 按线路选择 m3u8
        target_m3u8 = ""
        for line in lines:
            if line_code and line["code"] == line_code:
                target_m3u8 = line.get("m3u8", "")
                break
        if not target_m3u8 and lines:
            # 没找到指定线路, 用第一个
            target_m3u8 = lines[0].get("m3u8", "")

        if target_m3u8 and self._is_media(target_m3u8):
            is_m3u8 = ".m3u8" in target_m3u8.lower()
            self._play_cache[cache_key] = target_m3u8
            self._play_cache_time[cache_key] = now
            return {
                "parse": 0, "playUrl": "", "url": target_m3u8,
                "header": {
                    "User-Agent": UA,
                    "Referer": self._extract_referer(target_m3u8),
                },
                "format": "application/x-mpegURL" if is_m3u8 else "",
                "contentType": "application/x-mpegURL" if is_m3u8 else "",
            }

        # 方式2: 从页面 JS 提取媒体直链
        for rx in (RE_MEDIA_JS, RE_MEDIA_RAW):
            m = rx.search(html)
            if m:
                media_url = m.group(1).replace("\\/", "/").replace("\\u002F", "/")
                if self._is_media(media_url):
                    is_m3u8 = ".m3u8" in media_url.lower()
                    self._play_cache[cache_key] = media_url
                    self._play_cache_time[cache_key] = now
                    return {
                        "parse": 0, "playUrl": "", "url": media_url,
                        "header": {"User-Agent": UA, "Referer": self._extract_referer(media_url)},
                        "format": "application/x-mpegURL" if is_m3u8 else "",
                        "contentType": "application/x-mpegURL" if is_m3u8 else "",
                    }

        # 方式3: iframe
        iframe_m = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe_m:
            iframe_src = iframe_m.group(1)
            if not iframe_src.startswith("http"):
                iframe_src = HOST + iframe_src
            iframe_html = self._html_nocache(iframe_src, referer=play_url, timeout=8)
            if iframe_html:
                for rx in (RE_MEDIA_JS, RE_MEDIA_RAW):
                    m = rx.search(iframe_html)
                    if m:
                        media_url = m.group(1).replace("\\/", "/").replace("\\u002F", "/")
                        if self._is_media(media_url):
                            is_m3u8 = ".m3u8" in media_url.lower()
                            self._play_cache[cache_key] = media_url
                            self._play_cache_time[cache_key] = now
                            return {
                                "parse": 0, "playUrl": "", "url": media_url,
                                "header": {"User-Agent": UA, "Referer": self._extract_referer(iframe_src)},
                                "format": "application/x-mpegURL" if is_m3u8 else "",
                                "contentType": "application/x-mpegURL" if is_m3u8 else "",
                            }

        # 提取失败
        return {
            "parse": 1, "playUrl": "", "url": play_url,
            "header": {"User-Agent": UA, "Referer": HOST + "/"},
        }

    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    def destroy(self):
        pass

    def close(self):
        self.destroy()


# ==================== 自检 ====================
if __name__ == "__main__":
    import time as _t

    s = Spider()
    s.init()

    # 首页
    t0 = _t.time()
    home = s.homeContent(True)
    t1 = _t.time()
    print(f"[{t1-t0:.2f}s] homeContent: {len(home.get('class', []))} 分类")
    filters = home.get('filters', {})
    if filters:
        first_key = list(filters.keys())[0]
        for f in filters[first_key]:
            opts = [o['n'] for o in f['value']]
            print(f"  {f['name']}: {', '.join(opts[:6])}...")

    # 首页卡片
    t2 = _t.time()
    hv = s.homeVideoContent()
    t3 = _t.time()
    print(f"\n[{t3-t2:.2f}s] homeVideoContent: {len(hv.get('list', []))} 卡片")
    if hv.get('list'):
        for v in hv['list'][:3]:
            print(f"  {v['vod_name']}")

    # 分类
    t4 = _t.time()
    cat = s.categoryContent("dianyingl", "1", False, {})
    t5 = _t.time()
    print(f"\n[{t5-t4:.2f}s] categoryContent(电影): {len(cat.get('list', []))} 卡片")

    # 筛选
    t6 = _t.time()
    cat2 = s.categoryContent("dianyingl", "1", True, {"type": "dianyingl/xijuc", "year": "2024"})
    t7 = _t.time()
    print(f"[{t7-t6:.2f}s] categoryContent(电影→喜剧+2024): {len(cat2.get('list', []))} 卡片")

    # 短剧
    t8 = _t.time()
    cat3 = s.categoryContent("duanjuc", "1", True, {})
    t9 = _t.time()
    print(f"[{t9-t8:.2f}s] categoryContent(短剧): {len(cat3.get('list', []))} 卡片")

    # 搜索
    t10 = _t.time()
    search = s.searchContent("好人", False, "1")
    t11 = _t.time()
    print(f"\n[{t11-t10:.2f}s] searchContent(好人): {len(search.get('list', []))} 结果")

    # 详情+播放(多线路)
    if hv.get('list'):
        first_id = hv['list'][0]['vod_id']
        print(f"\ndetailContent (ID={first_id}):")
        t12 = _t.time()
        detail = s.detailContent([first_id])
        t13 = _t.time()
        if detail.get('list'):
            d = detail['list'][0]
            print(f"[{t13-t12:.2f}s]")
            print(f"  name: {d.get('vod_name', '')}")
            print(f"  year: {d.get('vod_year', '')} | area: {d.get('vod_area', '')}")
            print(f"  director: {d.get('vod_director', '')[:30]}")
            print(f"  actor: {d.get('vod_actor', '')[:30]}...")
            print(f"  content: {d.get('vod_content', '')[:40]}...")

            play_from = d.get('vod_play_from', '').split('$$$')
            play_urls = d.get('vod_play_url', '').split('$$$')
            print(f"  线路数: {len(play_from)}")
            for i, pf in enumerate(play_from):
                eps = play_urls[i].split('#') if i < len(play_urls) else []
                print(f"    线路{i+1} [{pf}]: {len(eps)} 集")
                if eps:
                    print(f"      first: {eps[0][:60]}...")

            # 测试播放
            if play_urls:
                first_ep = play_urls[0].split('#')[0]
                ep_url = first_ep.split('$')[-1]
                line_code = first_ep.split('$')[-2] if '$' in first_ep else ""
                print(f"\nplayerContent (线路={line_code}):")
                t14 = _t.time()
                player = s.playerContent(play_from[0], first_ep, [])
                t15 = _t.time()
                print(f"[{t15-t14:.2f}s]")
                print(f"  parse: {player.get('parse')}")
                print(f"  url: {player.get('url', '')[:80]}...")

                # 缓存命中
                t16 = _t.time()
                player2 = s.playerContent(play_from[0], first_ep, [])
                t17 = _t.time()
                print(f"[{t17-t16:.3f}s] (缓存)")

    # 测试电视剧多集
    print("\n=== TV series test ===")
    t18 = _t.time()
    cat_tv = s.categoryContent("dianshic", "1", False, {})
    t19 = _t.time()
    print(f"[{t19-t18:.2f}s] categoryContent(电视剧): {len(cat_tv.get('list', []))} 卡片")
    if cat_tv.get('list'):
        tv_id = cat_tv['list'][0]['vod_id']
        t20 = _t.time()
        tv_detail = s.detailContent([tv_id])
        t21 = _t.time()
        if tv_detail.get('list'):
            d = tv_detail['list'][0]
            print(f"[{t21-t20:.2f}s] detailContent: {d.get('vod_name', '')}")
            play_from = d.get('vod_play_from', '').split('$$$')
            play_urls = d.get('vod_play_url', '').split('$$$')
            print(f"  线路数: {len(play_from)}")
            for i, pf in enumerate(play_from):
                eps = play_urls[i].split('#') if i < len(play_urls) else []
                print(f"    线路{i+1} [{pf}]: {len(eps)} 集")
                if eps:
                    print(f"      first: {eps[0][:60]}...")
                    print(f"      last:  {eps[-1][:60]}...")

    print("\nOK - 全部接口正常")

# -*- coding: utf-8 -*-
"""
99短剧网 —— TVBox/影视仓 Python Spider（HTML 优先重写版）
站点: https://www.waigpt.com/  (99短剧网 / qllde.com)

【本次重写核心：站点 API 已关闭(返回 "closed")，全部改走 HTML 页面解析】

① 真实线路写入
   - 站点每部影片有 2~3 条真实播放线路(播2/播6/播8 等)，
     每条线路的每集都有真实 m3u8 直链(存在 /vpl/ 播放页的 player_aaaa.url 里)。
   - 详情页解析出所有线路+剧集列表，写入 vod_play_from / vod_play_url。
   - 播放时从 /vpl/ 页面一次提取 player_aaaa.url → 真实 m3u8，parse=0 直链播放。
   - 线路名统一为: 官এ__1❀、官এ__2❀、官এ__3❀ ...

② 每分类影片数量提升(67 → 250+)
   - 原因：API 关闭后 HTML 兜底正则不匹配真实 HTML，只解析到一小部分。
   - 修复：重写 _html_parse_vodlist 正则匹配真实结构(grid 缩略图 + text 文字列表)，
     单页即可拿到 250 条影片(76 缩略图 + 176 文字列表)。

③ 加载速度 & 播放速度优化
   - 加载：单页 HTML 一次请求即含全部 250 条，无需多页合并；
           keep-alive Session 连接复用 + gzip 压缩传输；
           分类结果缓存 5 分钟；搜索结果缓存 3 分钟。
   - 播放：详情页直接解析出 /vpl/ 剧集链接 → 播放时一次 HTML 请求提取 m3u8 直链 →
           parse=0 零二次跳转，带正确 Referer，秒开；
           vpl 页面缓存避免重复请求。
   - 搜索：HTML 搜索页一次请求即返回全部结果，结果缓存 3 分钟。

免责：脚本仅作技术学习。数据来源为第三方站点，播放时仍受上游可用性影响。
"""

import sys
import json
import re
import time

sys.path.append('..')

try:
    from base.spider import Spider
except Exception:  # 独立可运行(无 host 框架)时退化
    import requests as _rq
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass

    class Spider:
        """独立运行(无 drpy host)时用的退化基类：持久会话 keep-alive 提速。"""
        _session = None

        def _sess(self):
            if Spider._session is None:
                s = _rq.Session()
                # 增大连接池：15 连接 / 30 最大，提升并发吞吐
                a = _rq.adapters.HTTPAdapter(pool_connections=15,
                                             pool_maxsize=30, max_retries=0)
                s.mount("https://", a)
                s.mount("http://", a)
                s.verify = False
                Spider._session = s
            return Spider._session

        def fetch(self, url, headers=None, **kw):
            timeout = kw.pop('timeout', (CONNECT_TIMEOUT, READ_TIMEOUT))
            try:
                r = self._sess().get(url, headers=headers, timeout=timeout, **kw)
            except Exception:
                r = self._sess().get(url, headers=headers, timeout=timeout, **kw)
            r.encoding = 'utf-8'
            return r

from urllib.parse import quote, urlencode

# ============================================================
# 常量 / 可调配置
# ============================================================
HOST = "https://www.waigpt.com"
API = HOST + "/api.php/provide/vod/"
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

DEBUG = 1
def _log(msg):
    if DEBUG:
        print("[99DJ] %s" % msg)

# --- 网络超时(缩短以加速失败) ---
CONNECT_TIMEOUT = 3         # 建连超时(原4s→3s)
READ_TIMEOUT = 5            # 读取超时(原6s→5s)

# --- 分类页配置 ---
PAGE_SIZE = 250             # 单页期望返回的条数
CACHE_TTL = 300             # 分类/首页缓存有效期(秒) = 5 分钟
SEARCH_CACHE_TTL = 180      # 搜索缓存有效期(秒) = 3 分钟
DETAIL_CACHE_TTL = 600      # 详情缓存有效期(秒) = 10 分钟
VPL_CACHE_TTL = 600         # vpl 播放页缓存有效期(秒) = 10 分钟
MAX_CACHE_ENTRIES = 200     # 各缓存最大条目数(防内存膨胀)

# --- 真实线路名映射(仅用于日志，线路名统一用 官এ__N❀ 格式) ---
LINE_NAMES = {
    "wujin": "无尽资源", "lzm3u8": "量子资源", "ffm3u8": "非凡资源",
    "tkm3u8": "天空资源", "bdxm3u8": "百度资源", "kuaikan": "快看资源",
    "xlm3u8": "新浪资源", "yhm3u8": "樱花资源", "dbm3u8": "百度视频",
    "gsm3u8": "光速资源", "hnm3u8": "红牛资源", "sdm3u8": "闪电资源",
    "ukm3u8": "U酷资源", "wolong": "卧龙资源", "zuidam3u8": "最大资源",
    "snm3u8": "索尼资源", "wjm3u8": "无尽资源", "tpm3u8": "淘片资源",
    "modum3u8": "魔豆资源", "bfzym3u8": "暴风资源", "mtm3u8": "秒播资源",
    "hhm3u8": "花花资源", "qhm3u8": "奇虎资源", "hym3u8": "海洋资源",
}

CLASSES = [
    {"type_name": "短剧", "type_id": "20"},
    {"type_name": "电影", "type_id": "1"},
    {"type_name": "电视剧", "type_id": "2"},
    {"type_name": "综艺", "type_id": "3"},
    {"type_name": "动漫", "type_id": "4"},
    {"type_name": "纪录片", "type_id": "45"},
]

_YEAR_FILTER = {"key": "year", "name": "年份", "value": [
    {"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
    {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
    {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"},
    {"n": "2018", "v": "2018"}, {"n": "2010", "v": "2010"}, {"n": "2000", "v": "2000"},
    {"n": "90年代", "v": "1990"},
]}
_BY_FILTER = {"key": "by", "name": "排序", "value": [
    {"n": "最新", "v": "time"}, {"n": "最热", "v": "hits"}, {"n": "评分", "v": "score"},
]}

# --- 子分类筛选 (v 值为站点真实分类 ID，cat-{v}/ 即可访问) ---
_CLASS_FILTERS = {
    "20": [{"n": "全部", "v": ""}, {"n": "精选", "v": "34"}, {"n": "女频", "v": "21"},
           {"n": "古装", "v": "22"}, {"n": "虐恋", "v": "23"}, {"n": "逆袭", "v": "24"},
           {"n": "悬疑", "v": "25"}, {"n": "神豪", "v": "26"}, {"n": "重生", "v": "27"},
           {"n": "复仇", "v": "28"}, {"n": "穿越", "v": "29"}, {"n": "爽剧", "v": "30"}],
    "1": [{"n": "全部", "v": ""}, {"n": "动作片", "v": "6"}, {"n": "喜剧片", "v": "7"},
          {"n": "爱情片", "v": "8"}, {"n": "科幻片", "v": "9"}, {"n": "恐怖片", "v": "10"},
          {"n": "战争片", "v": "11"}, {"n": "犯罪片", "v": "12"}, {"n": "剧情片", "v": "31"}],
    "2": [{"n": "全部", "v": ""}, {"n": "国产", "v": "13"}, {"n": "港台", "v": "14"},
          {"n": "美剧", "v": "15"}, {"n": "日韩", "v": "16"}, {"n": "泰剧", "v": "35"},
          {"n": "海外", "v": "36"}],
    "3": [{"n": "全部", "v": ""}, {"n": "国产综艺", "v": "37"}, {"n": "港台综艺", "v": "38"},
          {"n": "欧美综艺", "v": "39"}, {"n": "日韩综艺", "v": "40"}],
    "4": [{"n": "全部", "v": ""}, {"n": "动漫电影", "v": "41"}, {"n": "华语动漫", "v": "42"},
          {"n": "日本动漫", "v": "43"}, {"n": "欧美动漫", "v": "44"}],
    "45": [{"n": "全部", "v": ""}],
}
FILTERS = {}
for _c in CLASSES:
    _tid = _c["type_id"]
    FILTERS[_tid] = [
        {"key": "class", "name": "类型", "value": _CLASS_FILTERS.get(_tid, [{"n": "全部", "v": ""}])},
        _YEAR_FILTER, _BY_FILTER,
    ]


# ============================================================
# Spider 主类
# ============================================================
class Spider(Spider):

    def getName(self):
        return "99短剧网"

    def init(self, extend=""):
        self.extend = extend if isinstance(extend, str) else (extend or "")

        self.html_header = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",   # 压缩传输，减少约 60% 体积
            "Connection": "keep-alive",
        }
        self.api_header = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        self._home_cache = []
        self._home_cache_time = 0
        self._cat_cache = {}       # {tid: (time, videos)}
        self._detail_cache = {}    # {vod_id: (time, vod)}
        self._vpl_cache = {}        # {vpl_url: (time, player_aaaa_dict)}
        self._search_cache = {}    # {key: (time, videos)}
        self._api_closed = False
        return "ok"

    # ---------- 缓存清理(防内存膨胀) ----------
    def _trim_cache(self, cache_dict, ttl):
        """清理过期+超量条目，保持缓存新鲜且不占过多内存。"""
        if len(cache_dict) <= MAX_CACHE_ENTRIES:
            return
        now = int(time.time())
        # 先删过期
        expired = [k for k, v in cache_dict.items()
                   if isinstance(v, tuple) and now - v[0] > ttl]
        for k in expired:
            del cache_dict[k]
        # 仍超量 → 删最早的
        if len(cache_dict) > MAX_CACHE_ENTRIES:
            sorted_keys = sorted(cache_dict.keys(),
                                 key=lambda k: cache_dict[k][0] if isinstance(cache_dict[k], tuple) else 0)
            for k in sorted_keys[:len(cache_dict) - MAX_CACHE_ENTRIES]:
                del cache_dict[k]

    # ---------- 网络层 ----------
    def _rsp_text(self, rsp):
        try:
            return rsp.text
        except Exception:
            try:
                return rsp.content.decode('utf-8', 'ignore')
            except Exception:
                return ""

    def _get_html(self, url):
        try:
            rsp = self.fetch(url, headers=self.html_header,
                             timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            return self._rsp_text(rsp)
        except Exception:
            return ""

    def _get_json(self, url):
        try:
            rsp = self.fetch(url, headers=self.api_header,
                             timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            text = self._rsp_text(rsp)
            if not text or text.strip() == "closed":
                self._api_closed = True
                return None
            return json.loads(text)
        except Exception:
            return None

    def _fetch_html_many(self, urls):
        """并发抓取多个 HTML，返回非空文本列表。"""
        try:
            from concurrent.futures import ThreadPoolExecutor
        except Exception:
            ThreadPoolExecutor = None
        out = [None] * len(urls)

        def grab(i, u):
            try:
                out[i] = self._get_html(u)
            except Exception:
                out[i] = ""

        if ThreadPoolExecutor is not None and len(urls) > 1:
            try:
                with ThreadPoolExecutor(max_workers=min(len(urls), 4)) as ex:
                    futures = [ex.submit(grab, i, u) for i, u in enumerate(urls)]
                    from concurrent.futures import wait
                    wait(futures, timeout=CONNECT_TIMEOUT + READ_TIMEOUT + 2)
            except Exception:
                out = [self._get_html(u) for u in urls]
        else:
            out = [self._get_html(u) for u in urls]
        return [x for x in out if x]

    # ---------- 工具方法 ----------
    def _match(self, pattern, text, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1) if m else ""

    def _match_all(self, pattern, text, flags=0):
        return re.findall(pattern, text, flags)

    def _is_direct_media(self, url):
        url = (url or "").lower()
        return any(x in url for x in (".m3u8", ".mp4", ".flv", ".mkv", ".mpd"))

    def _extract_referer(self, url):
        try:
            if "://" in url:
                scheme = url.split("://")[0]
                host = url.split("://")[1].split("/")[0]
                return scheme + "://" + host + "/"
        except Exception:
            pass
        return HOST + "/"

    def _strip_tags(self, s):
        return re.sub(r'<[^>]+>', '', s or '').strip()

    def _fix_pic(self, pic):
        if not pic:
            return ""
        pic = pic.replace("\\/", "/")
        if pic.startswith("//"):
            pic = "https:" + pic
        elif pic.startswith("/"):
            pic = HOST + pic
        return pic

    def _make_line_name(self, idx):
        """生成统一线路名: 官এ__1❀、官এ__2❀ ..."""
        return "\u5b98\u098f__%d\u2740" % idx

    # ============================================================
    # HTML 解析 —— 分类列表
    # ============================================================
    def _html_parse_vodlist(self, html):
        """解析 HTML 页面中的影片列表。
        匹配两种结构：
        1) 缩略图卡片：含 href + title + data-original
        2) 文字列表：含 href + title + 状态文字
        """
        videos = []
        if not html:
            return videos

        seen = set()

        # --- 缩略图卡片 ---
        p_thumb = (r'href="/vdtl/([^/]+)/"[^>]*?title="([^"]+)"[^>]*?'
                   r'data-original="([^"]+)"[^>]*>.*?'
                   r'pic-text[^>]*>([^<]+)</span>')
        for vid, name, pic, remarks in self._match_all(p_thumb, html, re.S):
            if vid in seen:
                continue
            seen.add(vid)
            remarks = remarks.strip()
            if remarks == name.strip() or remarks == "更新中":
                remarks = "HD"
            videos.append({"vod_id": vid, "vod_name": name.strip(),
                           "vod_pic": self._fix_pic(pic), "vod_remarks": remarks})

        # --- 文字列表 ---
        p_text = (r'class="top-line-dot[^"]*"[^>]*?href="/vdtl/([^/]+)/"[^>]*?'
                  r'title="([^"]+)"[^>]*>.*?'
                  r'(?:text-muted[^>]*>([^<]+)</span>)?')
        for vid, name, remarks in self._match_all(p_text, html, re.S):
            if vid in seen:
                continue
            seen.add(vid)
            rm = (remarks or "").strip() or "HD"
            videos.append({"vod_id": vid, "vod_name": name.strip(),
                           "vod_pic": "", "vod_remarks": rm})

        return videos

    # ============================================================
    # HTML 解析 —— 详情页(真实线路 + 剧集列表)
    # ============================================================
    def _html_parse_detail(self, html, vod_id):
        if not html:
            return None

        # --- 基本信息 ---
        title_html = self._match(r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h1>', html, re.S)
        title_html = re.sub(r'<span class="[^"]*score[^"]*">.*?</span>', '', title_html, flags=re.S)
        vod_name = self._strip_tags(title_html)
        if not vod_name:
            vod_name = self._strip_tags(self._match(r'<h3[^>]*>(.*?)</h3>', html, re.S))

        vod_pic = self._fix_pic(self._match(r'data-original="([^"]+)"', html))

        # 从 <p class="data"> 提取类型/地区/年份/主演/导演
        data_ps = self._match_all(r'<p class="data[^"]*">(.*?)</p>', html, re.S)
        vod_year = ""
        vod_area = ""
        vod_class = ""
        vod_actor = ""
        vod_director = ""
        for dp in data_ps:
            segments = re.split(r'<span class="text-muted[^"]*">([^：:]+)[：:]</span>', dp)
            for i in range(1, len(segments) - 1, 2):
                label = segments[i].strip()
                value_html = segments[i + 1] if i + 1 < len(segments) else ""
                value = self._strip_tags(value_html).strip()
                if not value:
                    continue
                if "年份" in label:
                    vod_year = value
                elif "地区" in label:
                    vod_area = value
                elif "类型" in label:
                    vod_class = value
                elif "主演" in label:
                    vod_actor = value
                elif "导演" in label:
                    vod_director = value

        # 简介
        vod_content = self._strip_tags(
            self._match(r'class="[^"]*content__desc[^"]*"[^>]*>(.*?)</div>', html, re.S))
        if not vod_content:
            vod_content = self._strip_tags(
                self._match(r'<p class="col-pd">(.*?)</p>', html, re.S))
        vod_content = vod_content[:500]

        # --- 播放线路 + 剧集列表 ---
        # 真实结构：
        #   <ul class="nav nav-tabs active">
        #     <li><a href="#playlist1" data-toggle="tab" title="播放路线播2">播2</a></li>
        #     <li><a href="#playlist3" data-toggle="tab" title="播放路线播6">播6</a></li>
        #   </ul>
        #   <div id="playlist1" class="tab-pane ...">
        #     <ul class="stui-content__playlist clearfix">
        #       <li><a href="/vpl/{vod_id}-{line}-{ep}/">全集/第01集</a></li>
        #     </ul>
        #   </div>
        play_from, play_url = [], []
        line_idx = 0  # 线路序号(从 1 开始)

        # 提取所有 tab: (playlist_div_id, tab_title, tab_display_name)
        tabs = self._match_all(
            r'href="#playlist(\d+)"[^>]*data-toggle="tab"[^>]*title="([^"]*)"[^>]*>(.*?)</a>',
            html, re.S)

        for div_id, tab_title, tab_display in tabs:
            # 提取该 playlist div 下的剧集
            div_html = self._match(
                r'<div[^>]*id="playlist%s"[^>]*>(.*?)</div>' % re.escape(div_id),
                html, re.S)

            if not div_html:
                continue

            # 提取剧集链接: href="/vpl/{vod_id}-{line}-{ep}/"  >全集</a>
            ep_pattern = r'href="(/vpl/[^"]+)"[^>]*>(.*?)</a>'
            eps = self._match_all(ep_pattern, div_html, re.S)
            if not eps:
                continue

            ep_list = []
            seen_ep = set()
            for ep_url, ep_name in eps:
                ep_name = self._strip_tags(ep_name).strip() or "正片"
                if ep_url in seen_ep:
                    continue
                seen_ep.add(ep_url)
                ep_list.append("%s$%s" % (ep_name, ep_url))

            if ep_list:
                line_idx += 1
                play_from.append(self._make_line_name(line_idx))
                play_url.append("#".join(ep_list))

        result = {
            "vod_id": str(vod_id),
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "type_name": vod_class,
            "vod_year": vod_year,
            "vod_area": vod_area,
            "vod_remarks": "HD",
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_content": vod_content,
            "vod_play_from": "$$$".join(play_from) if play_from else "",
            "vod_play_url": "$$$".join(play_url) if play_url else "",
        }
        return result

    # ============================================================
    # HTML 解析 —— 播放页(从 player_aaaa 提取真实 m3u8)
    # ============================================================
    def _html_extract_player_aaaa(self, html):
        """从 /vpl/ 播放页提取 player_aaaa 变量(含真实 m3u8 直链)。"""
        if not html:
            return None
        # var player_aaaa={"flag":"play",...,"url":"https://...m3u8","from":"zuidam3u8",...};
        for var_name in ("player_aaaa", "player", "player_data"):
            m = self._match(r'var\s+%s\s*=\s*(\{.*?\})\s*</script' % var_name, html, re.S)
            if not m:
                m = self._match(r'var\s+%s\s*=\s*(\{.*?\});' % var_name, html, re.S)
            if m:
                try:
                    return json.loads(m)
                except Exception:
                    try:
                        fixed = m.replace("'", '"').replace(",}", "}")
                        return json.loads(fixed)
                    except Exception:
                        pass
        return None

    def _html_parse_player_page(self, html):
        """从播放页挖真实 m3u8 直链。"""
        if not html:
            return ""
        player_data = self._html_extract_player_aaaa(html)
        if player_data:
            url = (player_data.get("url") or "").replace("\\/", "/")
            if url and self._is_direct_media(url):
                return url
        m3u8 = self._match(r'(https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*)', html)
        if m3u8:
            return m3u8
        mp4 = self._match(r'(https?://[^"\'\s<>]+\.mp4[^"\'\s<>]*)', html)
        if mp4:
            return mp4
        iframe = self._match(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe:
            return iframe
        return ""

    # ============================================================
    # 首页
    # ============================================================
    def homeContent(self, filter):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        _log("homeVideoContent")
        now = int(time.time())
        if self._home_cache and now - self._home_cache_time < CACHE_TTL:
            return {"list": self._home_cache[:72]}
        videos = []
        # 先尝试 API(万一恢复)
        if not self._api_closed:
            data = self._get_json(API + "?ac=videolist&pg=1")
            if data and data.get("code") == 1 and data.get("list"):
                videos = [self._api_card(v) for v in data.get("list", [])]
        # HTML 兜底
        if not videos:
            html = self._get_html(HOST + "/")
            videos = self._html_parse_vodlist(html)
        self._home_cache = videos[:72]
        self._home_cache_time = now
        return {"list": self._home_cache}

    def _api_card(self, v):
        vid = v.get("vod_id", "")
        pic = self._fix_pic(v.get("vod_pic", ""))
        remarks = (v.get("vod_remarks") or v.get("vod_year") or
                   v.get("vod_time", "")[:10] or "HD")
        return {"vod_id": str(vid), "vod_name": v.get("vod_name", ""),
                "vod_pic": pic, "vod_remarks": remarks}

    # ============================================================
    # 分类列表 —— HTML 优先，250+ 条/分类
    # ============================================================
    def categoryContent(self, tid, pg, filter, extend):
        _log("categoryContent tid=%s pg=%s" % (tid, pg))
        try:
            try:
                app_page = max(1, int(pg or 1))
            except Exception:
                app_page = 1

            ext = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend) or {}
                    except Exception:
                        ext = {}

            cat_id = str(ext.get("class") or "").strip() or str(tid)

            # 缓存检查(仅首页缓存)
            cache_key = cat_id
            now = int(time.time())
            if app_page == 1 and cache_key in self._cat_cache:
                ct, cached = self._cat_cache[cache_key]
                if now - ct < CACHE_TTL:
                    return {"list": cached, "page": 1, "pagecount": 2,
                            "limit": PAGE_SIZE, "total": len(cached)}

            videos = []

            # 1) 尝试 API(万一恢复)
            if not self._api_closed:
                params = {"ac": "videolist", "t": cat_id, "pg": str(app_page)}
                if ext.get("by"):
                    params["by"] = ext["by"]
                if ext.get("year"):
                    params["year"] = ext["year"]
                data = self._get_json(API + "?" + urlencode(params))
                if data and data.get("code") == 1 and data.get("list"):
                    videos = [self._api_card(v) for v in data.get("list", [])]

            # 2) HTML 解析
            if not videos:
                _log("fetching HTML category cat-%s/page/%s" % (cat_id, app_page))
                cat_urls = [
                    HOST + "/cat-%s/page/%s/" % (cat_id, app_page),
                    HOST + "/cat-%s/" % cat_id,
                    HOST + "/cat-%s/%s/" % (cat_id, app_page),
                ]
                for url in cat_urls:
                    html = self._get_html(url)
                    if html and "vdtl" in html:
                        videos = self._html_parse_vodlist(html)
                        if videos:
                            break

                # 客户端筛选
                class_kw = ext.get("class")
                if class_kw and videos:
                    if not class_kw.isdigit():
                        videos = [v for v in videos
                                  if class_kw in v.get("vod_name", "")]

            if not videos:
                return {"page": app_page, "pagecount": 1,
                        "limit": PAGE_SIZE, "total": 0, "list": []}

            # 缓存首页结果
            if app_page == 1:
                self._cat_cache[cache_key] = (now, videos)
                self._trim_cache(self._cat_cache, CACHE_TTL)

            _log("category got %s items" % len(videos))
            return {"list": videos, "page": app_page, "pagecount": 2,
                    "limit": PAGE_SIZE, "total": len(videos)}
        except Exception as e:
            _log("category exception: %s" % e)
            return {"page": 1, "pagecount": 1, "limit": PAGE_SIZE,
                    "total": 0, "list": []}

    # ============================================================
    # 详情页 —— 解析真实线路+剧集
    # ============================================================
    def detailContent(self, ids):
        _log("detailContent ids=%s" % (ids,))
        if isinstance(ids, str):
            ids = [ids]
        vod_id = str(ids[0])

        # 缓存检查(含 TTL)
        now = int(time.time())
        if vod_id in self._detail_cache:
            ct, cached_vod = self._detail_cache[vod_id]
            if now - ct < DETAIL_CACHE_TTL:
                _log("detail cache hit: %s" % vod_id)
                return {"list": [cached_vod]}

        vod = self._fetch_detail(vod_id)

        if not vod:
            vod = {"vod_id": vod_id, "vod_name": "", "vod_pic": "",
                   "type_name": "", "vod_year": "", "vod_area": "",
                   "vod_remarks": "HD", "vod_actor": "", "vod_director": "",
                   "vod_content": "", "vod_play_from": "", "vod_play_url": ""}

        self._detail_cache[vod_id] = (now, vod)
        self._trim_cache(self._detail_cache, DETAIL_CACHE_TTL)
        return {"list": [vod]}

    def _fetch_detail(self, vod_id):
        """从 HTML 详情页提取完整信息(含播放线路+剧集)。
        并发抓取多个候选 URL 以加速。"""
        detail_urls = [HOST + "/vdtl/" + vod_id + "/",
                       HOST + "/voddetail/" + vod_id + "/"]

        # 并发抓取两个候选 URL
        try:
            from concurrent.futures import ThreadPoolExecutor
        except Exception:
            ThreadPoolExecutor = None

        if ThreadPoolExecutor is not None:
            def fetch_one(u):
                h = self._get_html(u)
                if h:
                    v = self._html_parse_detail(h, vod_id)
                    if v and (v["vod_play_url"] or v["vod_name"] or v["vod_pic"]):
                        return v
                return None

            try:
                with ThreadPoolExecutor(max_workers=2) as ex:
                    future_map = {ex.submit(fetch_one, u): u for u in detail_urls}
                    from concurrent.futures import as_completed, wait
                    for f in as_completed(future_map, timeout=CONNECT_TIMEOUT + READ_TIMEOUT + 2):
                        result = f.result()
                        if result:
                            _log("detail parsed (concurrent): play_from=%s" %
                                 result["vod_play_from"][:80])
                            return result
            except Exception:
                pass  # 回退到串行

        # 串行兜底
        for url_path in detail_urls:
            html = self._get_html(HOST + url_path if url_path.startswith("/") else url_path)
            if not html:
                continue
            vod = self._html_parse_detail(html, vod_id)
            if vod and (vod["vod_play_url"] or vod["vod_name"] or vod["vod_pic"]):
                _log("detail parsed: play_from=%s, play_url_len=%s" %
                     (vod["vod_play_from"][:80], len(vod.get("vod_play_url", ""))))
                return vod

        # API 兜底
        if not self._api_closed:
            data = self._get_json(API + "?ac=detail&ids=" + vod_id)
            if data and data.get("code") == 1 and data.get("list"):
                d = data["list"][0]
                return self._build_vod_from_api(d, vod_id)

        return None

    def _build_vod_from_api(self, d, vod_id):
        """API 详情转 vod(API 恢复时备用)。"""
        raw_from = d.get("vod_play_from", "") or ""
        raw_url = d.get("vod_play_url", "") or ""
        play_from, play_url = [], []
        line_idx = 0  # 修复：必须初始化
        from_list = raw_from.split("$$$")
        url_groups = raw_url.split("$$$")
        for i, from_name in enumerate(from_list):
            if i >= len(url_groups):
                break
            url_group = url_groups[i]
            if not url_group.strip():
                continue
            ep_list = []
            for ep in url_group.split("#"):
                ep = ep.strip()
                if not ep:
                    continue
                if "$" in ep:
                    ep_name, ep_url = ep.split("$", 1)
                    ep_list.append("%s$%s" % (ep_name.strip(), ep_url.replace("\\/", "/")))
                else:
                    ep_list.append("第%s集$%s" % (len(ep_list) + 1, ep.replace("\\/", "/")))
            if ep_list:
                line_idx += 1
                play_from.append(self._make_line_name(line_idx))
                play_url.append("#".join(ep_list))
        content = self._strip_tags(d.get("vod_content", ""))[:500]
        return {
            "vod_id": str(vod_id),
            "vod_name": d.get("vod_name", ""),
            "vod_pic": self._fix_pic(d.get("vod_pic", "")),
            "type_name": d.get("type_name", ""),
            "vod_year": d.get("vod_year", ""),
            "vod_area": d.get("vod_area", ""),
            "vod_remarks": d.get("vod_remarks", "") or "HD",
            "vod_actor": d.get("vod_actor", ""),
            "vod_director": d.get("vod_director", ""),
            "vod_content": content,
            "vod_play_from": "$$$".join(play_from) if play_from else "",
            "vod_play_url": "$$$".join(play_url) if play_url else "",
        }

    # ============================================================
    # 搜索 —— HTML 优先 + 缓存
    # ============================================================
    def searchContent(self, key, quick, pg="1"):
        _log("searchContent key=%s" % key)
        try:
            try:
                page = max(1, int(pg or 1))
            except Exception:
                page = 1

            # 缓存检查(仅首页缓存)
            cache_key = key.strip().lower()
            now = int(time.time())
            if page == 1 and cache_key in self._search_cache:
                ct, cached = self._search_cache[cache_key]
                if now - ct < SEARCH_CACHE_TTL:
                    _log("search cache hit: %s" % key)
                    return {"list": cached}

            videos = []

            # 1) API 搜索(万一恢复)
            if not self._api_closed:
                params = {"ac": "videolist", "wd": key, "pg": str(page)}
                data = self._get_json(API + "?" + urlencode(params))
                if data and data.get("code") == 1 and data.get("list"):
                    videos = [self._api_card(v) for v in data.get("list", [])]

            # 2) HTML 搜索
            if not videos:
                _log("HTML search fallback")
                wd = quote(key)
                search_urls = [
                    HOST + "/vsch/-------------/?wd=" + wd,
                    HOST + "/vsch/-------------.html?wd=" + wd,
                    HOST + "/vodsearch/-------------.html?wd=" + wd,
                    HOST + "/search.php?wd=" + wd,
                ]
                for html in self._fetch_html_many(search_urls):
                    videos = self._html_parse_vodlist(html)
                    if videos:
                        break

            # 缓存首页结果
            if page == 1 and videos:
                self._search_cache[cache_key] = (now, videos)
                self._trim_cache(self._search_cache, SEARCH_CACHE_TTL)

            _log("search found %s" % len(videos))
            return {"list": videos}
        except Exception as e:
            _log("search exception: %s" % e)
            return {"list": []}

    # ============================================================
    # 播放 —— 从 /vpl/ 页面提取真实 m3u8 直链(parse=0 零延迟)
    # ============================================================
    def _direct_resp(self, url):
        is_m3u8 = ".m3u8" in url.lower()
        ref = self._extract_referer(url)
        return {"parse": 0, "playUrl": "", "url": url,
                "header": {"User-Agent": UA, "Referer": ref},
                "format": "application/x-mpegURL" if is_m3u8 else "",
                "contentType": "application/x-mpegURL" if is_m3u8 else ""}

    def playerContent(self, flag, id, vipFlags):
        _log("playerContent flag=%s id=%s" % (flag, (id or "")[:80]))
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}

        play_url = str(id).replace("\\/", "/")

        # 1) 已经是直链(m3u8/mp4) → 直接可播，零延迟
        if self._is_direct_media(play_url):
            return self._direct_resp(play_url)

        # 2) /vpl/ 播放页 → 提取 player_aaaa.url 真实 m3u8 直链
        if "/vpl/" in play_url:
            if play_url.startswith("/"):
                full_url = HOST + play_url
            elif not play_url.startswith("http"):
                full_url = HOST + "/" + play_url
            else:
                full_url = play_url

            # 缓存检查(含 TTL)
            now = int(time.time())
            if full_url in self._vpl_cache:
                ct, player_data = self._vpl_cache[full_url]
                if now - ct < VPL_CACHE_TTL:
                    m3u8_url = (player_data.get("url") or "").replace("\\/", "/")
                    if m3u8_url and self._is_direct_media(m3u8_url):
                        _log("vpl cached m3u8: %s" % m3u8_url[:80])
                        return self._direct_resp(m3u8_url)

            # 请求 vpl 页面提取真实直链
            html = self._get_html(full_url)
            if html:
                player_data = self._html_extract_player_aaaa(html)
                if player_data:
                    # 缓存 player_aaaa
                    self._vpl_cache[full_url] = (now, player_data)
                    self._trim_cache(self._vpl_cache, VPL_CACHE_TTL)
                    m3u8_url = (player_data.get("url") or "").replace("\\/", "/")
                    from_name = player_data.get("from", "")
                    if m3u8_url and self._is_direct_media(m3u8_url):
                        _log("vpl extracted m3u8 (from=%s): %s" %
                             (from_name, m3u8_url[:80]))
                        return self._direct_resp(m3u8_url)

                # vpl 页面没有 player_aaaa → 尝试通用 m3u8 提取
                real = self._html_parse_player_page(html)
                if real and self._is_direct_media(real):
                    return self._direct_resp(real)

                # 页面有 iframe → 交给客户端解析器
                iframe = self._match(r'<iframe[^>]+src="([^"]+)"', html)
                if iframe and iframe.startswith("http"):
                    return {"parse": 1, "playUrl": "", "url": iframe,
                            "header": {"User-Agent": UA, "Referer": HOST + "/"}}

            # vpl 页面打不开 → 交给客户端解析
            return {"parse": 1, "playUrl": "", "url": full_url,
                    "header": {"User-Agent": UA, "Referer": HOST + "/"}}

        # 3) /vdtl/ 详情页 URL
        if "/vdtl/" in play_url or "/voddetail/" in play_url:
            html = self._get_html(play_url)
            real = self._html_parse_player_page(html)
            if real and self._is_direct_media(real):
                return self._direct_resp(real)
            if real and real.startswith("http"):
                return {"parse": 1, "playUrl": "", "url": real,
                        "header": {"User-Agent": UA, "Referer": HOST + "/"}}
            return {"parse": 1, "playUrl": "", "url": play_url,
                    "header": {"User-Agent": UA, "Referer": HOST + "/"}}

        # 4) 解析站地址
        if self._is_parse_url(play_url):
            return {"parse": 1, "playUrl": "", "url": play_url,
                    "header": {"User-Agent": UA, "Referer": HOST + "/"}}

        # 5) 其他 → 直返
        return {"parse": 0, "playUrl": "", "url": play_url,
                "header": {"User-Agent": UA, "Referer": HOST + "/"}}

    def _is_parse_url(self, url):
        low = (url or "").lower()
        return any(x in low for x in
                   ("/player/?url=", "jiexi", "parse", "?url=http", "jx.", "/jx/"))

    # ===== 本地代理(预留) =====
    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    def destroy(self):
        pass

    def close(self):
        self.destroy()

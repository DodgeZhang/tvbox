# -*- coding: utf-8 -*-
"""
4K影仓 Python Spider — 兼容 FongMi/TV (T3) 与 WebHomeTV / PeekPro (T4)
站点: https://www.4kcabin.com/

特性:
  - 基于苹果CMS v10 HTML页面抓取（API已关闭）
  - HTML解析提取视频列表、详情、播放地址
  - 5大分类 + 二级子分类筛选（类型/地区/年份/语言/排序）
  - 全文搜索（多URL格式尝试 + 搜索缓存）
  - 首页推荐缓存（10分钟）+ 分类页缓存（5分钟）+ 搜索缓存（2分钟）
  - 详情页3次重试（解决间歇性Cloudflare 520错误）
  - 播放页解析 player_aaaa 变量获取真实视频地址
  - 直链m3u8/mp4优先直接播放（parse=0），非直链交壳子嗅探
  - 预编译正则 + 连接池复用，优化加载速度
  - 播放地址缓存（15分钟），优化播放速度
  - 图片URL修复 + 更多lazy属性 + CSS背景图支持
  - 线路按HTML tab顺序排列，非sid数字排序
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

    class _BaseSpider:
        """Fallback Spider for standalone testing with connection pooling."""
        def __init__(self):
            self._session = None

        @property
        def _sess(self):
            if self._session is None:
                self._session = _rq.Session()
                self._session.verify = False
                adapter = _rq.adapters.HTTPAdapter(
                    pool_connections=10,
                    pool_maxsize=10,
                    max_retries=0,
                )
                self._session.mount('https://', adapter)
                self._session.mount('http://', adapter)
            return self._session

        def fetch(self, url, headers=None, **kw):
            timeout = kw.pop('timeout', 15)
            r = self._sess.get(url, headers=headers, timeout=timeout, **kw)
            r.encoding = 'utf-8'
            return r

        def post(self, url, data=None, headers=None, **kw):
            timeout = kw.pop('timeout', 15)
            r = self._sess.post(url, data=data, headers=headers, timeout=timeout, **kw)
            r.encoding = 'utf-8'
            return r

    Spider = _BaseSpider

from urllib.parse import quote, unquote


# ============================================================
# 常量
# ============================================================

HOST = "https://www.4kcabin.com"
UA = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

# 分类列表（type_id 为拼音分类名，用于 vodshow URL）
CLASSES = [
    {"type_name": "电影", "type_id": "dianying"},
    {"type_name": "电视剧", "type_id": "dianshiju"},
    {"type_name": "动漫", "type_id": "dongman"},
    {"type_name": "综艺", "type_id": "zongyi"},
    {"type_name": "体育赛事", "type_id": "tiyusaishi"},
]

# 通用地区筛选
_AREA_VALUES = [
    {"n": "全部", "v": ""},
    {"n": "大陆", "v": "大陆"},
    {"n": "香港", "v": "香港"},
    {"n": "台湾", "v": "台湾"},
    {"n": "美国", "v": "美国"},
    {"n": "日本", "v": "日本"},
    {"n": "韩国", "v": "韩国"},
    {"n": "印度", "v": "印度"},
    {"n": "泰国", "v": "泰国"},
    {"n": "英国", "v": "英国"},
    {"n": "法国", "v": "法国"},
    {"n": "加拿大", "v": "加拿大"},
]

# 年份筛选
_YEAR_VALUES = [
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
    {"n": "2015", "v": "2015"},
    {"n": "2014", "v": "2014"},
]

# 排序筛选
_BY_VALUES = [
    {"n": "最新", "v": "time"},
    {"n": "最热", "v": "hits"},
    {"n": "评分", "v": "score"},
]

# 语言筛选
_LANG_VALUES = [
    {"n": "全部", "v": ""},
    {"n": "普通话", "v": "普通话"},
    {"n": "粤语", "v": "粤语"},
    {"n": "英语", "v": "英语"},
    {"n": "日语", "v": "日语"},
    {"n": "韩语", "v": "韩语"},
    {"n": "泰语", "v": "泰语"},
    {"n": "法语", "v": "法语"},
]

# 各分类的类型子分类（基于网站实际数据）
_CLASS_FILTERS = {
    "dianying": [
        {"n": "全部", "v": ""},
        {"n": "动作", "v": "动作"},
        {"n": "喜剧", "v": "喜剧"},
        {"n": "爱情", "v": "爱情"},
        {"n": "剧情", "v": "剧情"},
        {"n": "科幻", "v": "科幻"},
        {"n": "悬疑", "v": "悬疑"},
        {"n": "惊悚", "v": "惊悚"},
        {"n": "恐怖", "v": "恐怖"},
        {"n": "犯罪", "v": "犯罪"},
        {"n": "动画", "v": "动画"},
        {"n": "冒险", "v": "冒险"},
        {"n": "战争", "v": "战争"},
        {"n": "奇幻", "v": "奇幻"},
        {"n": "历史", "v": "历史"},
        {"n": "伦理", "v": "伦理"},
        {"n": "同性", "v": "同性"},
        {"n": "纪录片", "v": "纪录片"},
    ],
    "dianshiju": [
        {"n": "全部", "v": ""},
        {"n": "都市", "v": "都市"},
        {"n": "爱情", "v": "爱情"},
        {"n": "古装", "v": "古装"},
        {"n": "悬疑", "v": "悬疑"},
        {"n": "犯罪", "v": "犯罪"},
        {"n": "家庭", "v": "家庭"},
        {"n": "青春", "v": "青春"},
        {"n": "校园", "v": "校园"},
        {"n": "喜剧", "v": "喜剧"},
        {"n": "剧情", "v": "剧情"},
        {"n": "历史", "v": "历史"},
        {"n": "战争", "v": "战争"},
        {"n": "武侠", "v": "武侠"},
        {"n": "仙侠", "v": "仙侠"},
        {"n": "奇幻", "v": "奇幻"},
        {"n": "同性", "v": "同性"},
        {"n": "短剧", "v": "短剧"},
    ],
    "dongman": [
        {"n": "全部", "v": ""},
        {"n": "热血", "v": "热血"},
        {"n": "冒险", "v": "冒险"},
        {"n": "奇幻", "v": "奇幻"},
        {"n": "科幻", "v": "科幻"},
        {"n": "校园", "v": "校园"},
        {"n": "恋爱", "v": "恋爱"},
        {"n": "搞笑", "v": "搞笑"},
        {"n": "悬疑", "v": "悬疑"},
        {"n": "推理", "v": "推理"},
        {"n": "治愈", "v": "治愈"},
        {"n": "运动", "v": "运动"},
        {"n": "机战", "v": "机战"},
        {"n": "魔法", "v": "魔法"},
        {"n": "异世界", "v": "异世界"},
        {"n": "战斗", "v": "战斗"},
        {"n": "日常", "v": "日常"},
        {"n": "剧情", "v": "剧情"},
    ],
    "zongyi": [
        {"n": "全部", "v": ""},
        {"n": "真人秀", "v": "真人秀"},
        {"n": "脱口秀", "v": "脱口秀"},
        {"n": "访谈", "v": "访谈"},
        {"n": "选秀", "v": "选秀"},
        {"n": "音乐", "v": "音乐"},
        {"n": "舞蹈", "v": "舞蹈"},
        {"n": "竞技", "v": "竞技"},
        {"n": "美食", "v": "美食"},
        {"n": "旅游", "v": "旅游"},
        {"n": "游戏", "v": "游戏"},
        {"n": "喜剧", "v": "喜剧"},
        {"n": "情感", "v": "情感"},
        {"n": "亲子", "v": "亲子"},
        {"n": "职场", "v": "职场"},
        {"n": "文化", "v": "文化"},
        {"n": "益智", "v": "益智"},
        {"n": "生活", "v": "生活"},
    ],
    "tiyusaishi": [
        {"n": "全部", "v": ""},
        {"n": "足球", "v": "足球"},
        {"n": "篮球", "v": "篮球"},
        {"n": "网球", "v": "网球"},
        {"n": "斯诺克", "v": "斯诺克"},
    ],
}

# 构建各分类的完整筛选器
# 顺序：类型 → 地区 → 年份 → 语言 → 排序
FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    FILTERS[tid] = [
        {"key": "class", "name": "类型", "value": _CLASS_FILTERS.get(tid, [{"n": "全部", "v": ""}])},
        {"key": "area", "name": "地区", "value": _AREA_VALUES},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES},
        {"key": "lang", "name": "语言", "value": _LANG_VALUES},
        {"key": "by", "name": "排序", "value": _BY_VALUES},
    ]


# ============================================================
# 预编译正则（优化解析速度）
# ============================================================
_RE_VODDAIL_ID = re.compile(r'/voddetail/(\d+)\.html')
_RE_A_TAG = re.compile(r'<a\s+([^>]*?href="/voddetail/(\d+)\.html"[^>]*?)>(.*?)</a>', re.S | re.I)
_RE_TITLE_ATTR = re.compile(r'title="([^"]{2,100})"')
_RE_ALT_ATTR = re.compile(r'alt="([^"]{2,100})"')
_RE_IMG_LAZY = re.compile(
    r'(?:data-original|data-src|data-lazy-src|data-lazy|data-bg|data-echo|lay-src|data-lazyurl|data-real|data-thumb|data-img|data-poster|data-image|data-cover|data-avatar|data-photo|data-src2|ks-lazyload|data-lazyload|data-url|data-srcset|data-thumbnail)\s*=\s*"([^"]+)"',
    re.I
)
_RE_IMG_SRC = re.compile(
    r'src\s*=\s*"([^"]+)"',
    re.I
)
_RE_IMG_SRCSET = re.compile(
    r'srcset\s*=\s*"([^"]+)"',
    re.I
)
_RE_SOURCE_SRCSET = re.compile(
    r'<source[^>]*\ssrcset\s*=\s*"([^"]+)"',
    re.I
)
_RE_BG_IMG = re.compile(
    r'background(?:-image)?\s*:\s*url\(["\']?([^"\')]+)["\']?\)',
    re.I
)
_RE_IMG_URL_GENERIC = re.compile(
    r'((?:https?:)?//[^"\s<>]+\.(?:jpg|jpeg|png|webp|gif|bmp))',
    re.I
)
_RE_PLAYER_AAAA = re.compile(r'player_aaaa\s*=\s*(\{.*?\})\s*[;<]', re.S)
_RE_PLAYER_CFG = re.compile(r'MacPlayerConfig\s*=\s*(\{.*?\})\s*[;<]', re.S)
_RE_PLAYER_DATA = re.compile(r'player_data\s*=\s*(\{.*?\})\s*[;<]', re.S)
_RE_M3U8_URL = re.compile(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', re.I)
_RE_MP4_URL = re.compile(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', re.I)
_RE_VODPLAY_LINK = re.compile(r'href="/vodplay/(\d+)-(\d+)-(\d+)\.html"[^>]*>([^<]+)</a>')
_RE_PAGE_TEXT = re.compile(r'共\s*\d+\s*条[^,]*[,，]\s*当前\s*\d+\s*/\s*(\d+)\s*页')
_RE_PAGE_LINK = re.compile(r'class="[^"]*page[_-]?link[^"]*"[^>]*href="[^"]*?(\d+)[^"]*?"', re.I)
_RE_H1 = re.compile(r'<h1[^>]*>([^<]+)</h1>')
_RE_H2 = re.compile(r'<h2[^>]*>(.*?)</h2>', re.S)
_RE_H3 = re.compile(r'<h3[^>]*>(.*?)</h3>', re.S)
_RE_TITLE_TAG = re.compile(r'<title>([^<|]+)')

# 图片排除关键词（仅精确匹配文件名，避免误伤CDN路径）
_IMG_SKIP = ('loading', 'placeholder', 'lazyload',
             'logo', 'search', 'icon', 'default', 'blank',
             'nopic', 'no-pic', 'noflag', 'norule')

# 跳过的非标题文本
_SKIP_TEXTS = {
    'HD', '高清', '超清', '4K', '蓝光', '抢先版', '正片', '预告', '完结',
    '查看更多', '加载更多', '首页', '上一页', '下一页', '尾页', 'GO',
    '全部', '类型', '地区', '年份', '语言', '排序', '最新', '最热', '评分',
    '确定', '重置', '筛选', '收起', '展开',
}
_SKIP_NAV = {
    '首页', '上一页', '下一页', '尾页', 'GO',
    '查看更多', '加载更多', '确定', '重置', '筛选',
    '全部', '类型', '地区', '年份', '语言', '排序',
}
_REMARK_PATTERNS = [
    r'class="[^"]*(?:pic-text|pic-tag|module-item-text|tag|remarks|state|label|badge)[^"]*"[^>]*>([^<]{1,20})<',
    r'<span[^>]*class="[^"]*(?:text-right|remarks|state|pic-tag)[^"]*"[^>]*>([^<]{1,20})<',
    r'<i[^>]*>([^<]{1,20})</i>',
    r'<em[^>]*>([^<]{1,20})</em>',
]


# ============================================================
# Spider 主类
# ============================================================

class Spider(Spider):

    def getName(self):
        return "4K影仓"

    # ===== 初始化 =====
    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ""
        else:
            self.extend = extend or ""

        self.header = {
            "User-Agent": UA,
            "Referer": HOST + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip, deflate",
        }

        # 缓存：首页10分钟，分类页5分钟，搜索2分钟，播放地址10分钟
        self._home_cache = []
        self._home_cache_time = 0
        self._cat_cache = {}
        self._search_cache = {}
        self._play_cache = {}      # {play_id: (timestamp, result)}

    # ===== 网络工具 =====
    def _rsp_text(self, rsp):
        try:
            return rsp.text
        except Exception:
            try:
                return rsp.content.decode('utf-8', 'ignore')
            except Exception:
                return ""

    def _fetch_html(self, url, timeout=1.5, retries=2):
        """带指数退避重试的 HTML 请求，处理 Cloudflare 520 错误"""
        for attempt in range(retries):
            try:
                rsp = self.fetch(url, headers=self.header, timeout=timeout)
                text = self._rsp_text(rsp)
                if text and len(text) > 500:
                    head = text[:300].lower()
                    # 检测 Cloudflare 520 错误页
                    if 'error code: 520' in head or ('cloudflare' in head and '520' in head):
                        if attempt < retries - 1:
                            time.sleep(0.05 * (1.2 ** attempt))
                            continue
                    # 验证是有效内容页
                    if '/voddetail/' in text or '/vodplay/' in text or 'player_aaaa' in text:
                        return text
                    if len(text) > 2000 and 'error code' not in head:
                        return text
                if attempt < retries - 1:
                    time.sleep(0.05 * (1.2 ** attempt))
            except Exception:
                if attempt < retries - 1:
                    time.sleep(0.05 * (1.2 ** attempt))
        return ""

    def _fetch_html_fast(self, url, timeout=1.2, retries=1):
        """快速请求（更短超时，更少重试）"""
        return self._fetch_html(url, timeout=timeout, retries=retries)

    def _match(self, pattern, text, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1) if m else ""

    def _strip_tags(self, s):
        return re.sub(r'<[^>]+>', '', s or '').strip()

    def _is_direct_media(self, url):
        url = (url or "").lower()
        return ".m3u8" in url or ".mp4" in url or ".flv" in url or ".mkv" in url

    def _extract_referer(self, url):
        try:
            if "://" in url:
                scheme = url.split("://")[0]
                host = url.split("://")[1].split("/")[0]
                return scheme + "://" + host + "/"
        except Exception:
            pass
        return HOST + "/"

    def _fix_img_url(self, url):
        """修复图片URL：补全协议、清理、支持相对路径和CDN"""
        if not url:
            return ""
        url = url.strip()
        # 排除 data URI（在URL修复前检查）
        if url.lower().startswith('data:'):
            return ""
        # 处理 CSS url() 格式
        url = re.sub(r'^url\(["\']?(.*?)["\']?\)$', r'\1', url)
        # 协议相对URL
        if url.startswith("//"):
            url = "https:" + url
        # 相对路径
        elif url.startswith("/") and not url.startswith("//"):
            url = HOST + url
        # 无协议的完整域名URL（含.且不以/开头）
        elif not url.startswith("http") and "." in url.split("/")[0] and not url.startswith("/"):
            url = "https://" + url
        # 纯文件名路径（如 upload/2024/img.jpg）
        elif not url.startswith("http") and not url.startswith("/") and not url.startswith("//"):
            if "/" in url or "." in url:
                url = HOST + "/" + url
        url_lower = url.lower()
        # 排除占位图等（仅精确匹配文件名，避免误伤CDN路径）
        filename = url_lower.rsplit('/', 1)[-1] if '/' in url_lower else url_lower
        # 去掉扩展名后检查
        name_no_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
        if name_no_ext in _IMG_SKIP:
            return ""
        return url

    def _extract_img_from_text(self, text):
        """从文本中提取图片URL，优先lazy loading属性"""
        if not text:
            return ""

        def _is_skip(url_lower):
            """检查是否为占位图（仅精确匹配文件名）"""
            filename = url_lower.rsplit('/', 1)[-1] if '/' in url_lower else url_lower
            name_no_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
            return name_no_ext in _IMG_SKIP

        # 优先查找 lazy loading 属性
        for m in _RE_IMG_LAZY.finditer(text):
            url = m.group(1).strip()
            url_lower = url.lower()
            if url_lower.startswith('data:'):
                continue
            if _is_skip(url_lower):
                continue
            if len(url) > 5 and ('.' in url or '/' in url):
                url = re.sub(r'^url\(["\']?(.*?)["\']?\)$', r'\1', url)
                return url
        # <source> 标签的 srcset
        for m in _RE_SOURCE_SRCSET.finditer(text):
            srcset_val = m.group(1).strip()
            first_url = srcset_val.split(',')[0].strip().split(' ')[0].strip()
            if first_url:
                url_lower = first_url.lower()
                if not url_lower.startswith('data:') and not _is_skip(url_lower):
                    if len(first_url) > 5 and ('.' in first_url or '/' in first_url):
                        return first_url
        # srcset 属性（取第一个URL）
        for m in _RE_IMG_SRCSET.finditer(text):
            srcset_val = m.group(1).strip()
            # srcset格式: "url1 1x, url2 2x"
            first_url = srcset_val.split(',')[0].strip().split(' ')[0].strip()
            if first_url:
                url_lower = first_url.lower()
                if not url_lower.startswith('data:') and not _is_skip(url_lower):
                    if len(first_url) > 5 and ('.' in first_url or '/' in first_url):
                        return first_url
        # CSS background-image
        for m in _RE_BG_IMG.finditer(text):
            url = m.group(1).strip()
            url_lower = url.lower()
            if url_lower.startswith('data:'):
                continue
            if _is_skip(url_lower):
                continue
            if len(url) > 5 and ('.' in url or '/' in url):
                return url
        # 后备：src 属性
        for m in _RE_IMG_SRC.finditer(text):
            url = m.group(1).strip()
            url_lower = url.lower()
            if url_lower.startswith('data:'):
                continue
            if _is_skip(url_lower):
                continue
            if len(url) > 5 and ('.' in url or '/' in url):
                url = re.sub(r'^url\(["\']?(.*?)["\']?\)$', r'\1', url)
                return url
        # 最终后备：搜索任何图片URL
        for m in _RE_IMG_URL_GENERIC.finditer(text):
            url = m.group(1).strip()
            url_lower = url.lower()
            if not _is_skip(url_lower):
                return url
        return ""

    # ===== URL 构建 =====
    def _build_show_url(self, type_id, ext, page):
        page_str = str(page) if page >= 1 else "1"
        parts = [
            type_id,                 # 0: 分类
            ext.get("area", ""),     # 1: 地区
            ext.get("by", ""),       # 2: 排序
            ext.get("class", ""),    # 3: 类型子分类
            ext.get("lang", ""),    # 4: 语言
            "",                      # 5: 字母
            "",                      # 6
            "",                      # 7
            page_str,                # 8: 页码
            "",                      # 9
            "",                      # 10
            ext.get("year", ""),     # 11: 年份
        ]
        encoded = [quote(p, safe="") if p else "" for p in parts]
        return HOST + "/vodshow/" + "-".join(encoded) + ".html"

    def _build_search_urls(self, wd, page):
        """构建多种搜索URL格式，返回列表按优先级排序"""
        page_str = str(page) if page >= 1 else "1"
        wd_encoded = quote(wd, safe="")
        urls = [
            # 1. GET参数格式（最可靠，不依赖rewrite规则）
            HOST + "/vodsearch.html?wd=" + wd_encoded + "&page=" + page_str,
            # 2. 标准12段格式（7个空段后页码）
            HOST + "/vodsearch/" + wd_encoded + "-------" + page_str + "---.html",
            # 3. 13段格式（8个空段后页码）
            HOST + "/vodsearch/" + wd_encoded + "--------" + page_str + "---.html",
            # 4. 10段格式（6个空段后页码）
            HOST + "/vodsearch/" + wd_encoded + "------" + page_str + "---.html",
            # 5. 15段格式（10个空段后页码）
            HOST + "/vodsearch/" + wd_encoded + "----------" + page_str + "---.html",
            # 6. index.php GET参数
            HOST + "/index.php/vodsearch.html?wd=" + wd_encoded + "&page=" + page_str,
            # 7. index.php 前缀 - 12段
            HOST + "/index.php/vodsearch/" + wd_encoded + "-------" + page_str + "---.html",
            # 8. 简短格式（仅页码1）
            HOST + "/vodsearch/" + wd_encoded + ".html" if page == 1 else None,
        ]
        return [u for u in urls if u]

    # ===== HTML 解析：视频卡片列表 =====
    def _parse_video_cards(self, html):
        """
        从 HTML 中解析视频卡片列表（兼容多种苹果CMS v10 模板）
        对每个 voddetail ID，找到所有包含该链接的 <a> 标签，
        从标签属性和内部内容中提取标题/图片/备注。
        """
        results = []
        seen_ids = set()
        unique_ids = []
        for m in _RE_VODDAIL_ID.finditer(html):
            vid = m.group(1)
            if vid not in seen_ids:
                seen_ids.add(vid)
                unique_ids.append(vid)

        for vid in unique_ids:
            a_tags = re.findall(
                r'<a\s+([^>]*?href="/voddetail/%s\.html"[^>]*?)>(.*?)</a>' % vid,
                html, re.S | re.I
            )

            title = ""
            pic = ""
            remarks = ""

            for attrs, inner in a_tags:
                # === 提取标题 ===
                if not title:
                    m = _RE_TITLE_ATTR.search(attrs)
                    if m:
                        t = m.group(1).strip()
                        if t and t not in _SKIP_TEXTS and not t.startswith('http'):
                            title = t
                if not title:
                    m = _RE_ALT_ATTR.search(inner)
                    if m:
                        t = m.group(1).strip()
                        if t and t not in _SKIP_TEXTS and not t.startswith('http'):
                            title = t
                if not title:
                    text = re.sub(r'<[^>]+>', '', inner).strip()
                    if text and len(text) > 1 and text not in _SKIP_TEXTS:
                        title = text[:100]

                # === 提取图片 ===
                if not pic:
                    for source in (attrs, inner):
                        pic = self._extract_img_from_text(source)
                        if pic:
                            break

                # === 提取备注 ===
                if not remarks:
                    for rp in _REMARK_PATTERNS:
                        rm = re.search(rp, inner, re.I)
                        if rm:
                            val = rm.group(1).strip()
                            if val and val not in _SKIP_NAV:
                                remarks = val
                                break

            # === 后备：从链接位置附近搜索 ===
            if not title or not pic:
                first_pos = html.find('/voddetail/%s.html' % vid)
                if first_pos >= 0:
                    context = html[first_pos:first_pos + 500]
                    if not title:
                        for tag_re in (_RE_H2, _RE_H3):
                            for tm in tag_re.finditer(context):
                                t = self._strip_tags(tm.group(1))
                                if t and t not in _SKIP_TEXTS and not t.startswith('http'):
                                    title = t
                                    break
                            if title:
                                break
                    if not title:
                        texts = re.findall(r'>([^<]{3,100})<', context)
                        for t in texts:
                            t = t.strip()
                            if (t and len(t) > 2 and not t.startswith('http')
                                    and not t.isdigit() and t not in _SKIP_TEXTS):
                                title = t
                                break
                    if not pic:
                        ctx_start = max(0, first_pos - 300)
                        ctx = html[ctx_start:first_pos + 500]
                        pic = self._extract_img_from_text(ctx)

            if not title:
                continue

            pic = self._fix_img_url(pic)
            if not remarks:
                remarks = "HD"

            results.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })

        return results

    # ===== HTML 解析：分页信息 =====
    def _parse_pagination(self, html, base_path="vodshow"):
        max_page = 1

        text_m = _RE_PAGE_TEXT.search(html)
        if text_m:
            max_page = max(max_page, int(text_m.group(1)))

        page_links = _RE_PAGE_LINK.findall(html)
        if page_links:
            nums = [int(x) for x in page_links if x.isdigit()]
            if nums:
                max_page = max(max_page, max(nums))

        url_pages = re.findall(
            r'/%s/[^"]*?-{8}(\d+)-{3}[^"]*?\.html' % base_path, html
        )
        if url_pages:
            nums = [int(x) for x in url_pages if x.isdigit()]
            if nums:
                max_page = max(max_page, max(nums))

        url_pages2 = re.findall(
            r'href="[^"]*/%s/[^"]*?-{4,}(\d+)-{2,}[^"]*?\.html"' % base_path,
            html, re.I
        )
        if url_pages2:
            nums = [int(x) for x in url_pages2 if x.isdigit()]
            if nums:
                max_page = max(max_page, max(nums))

        dp_matches = re.findall(r'data-page="(\d+)"', html)
        if dp_matches:
            nums = [int(x) for x in dp_matches if x.isdigit()]
            if nums:
                max_page = max(max_page, max(nums))

        js_m = re.search(r'page_total\s*[=:]\s*[\'"]?(\d+)', html)
        if js_m:
            max_page = max(max_page, int(js_m.group(1)))
        js_m2 = re.search(r'pagecount\s*[=:]\s*[\'"]?(\d+)', html, re.I)
        if js_m2:
            max_page = max(max_page, int(js_m2.group(1)))

        total_m = re.search(r'共\s*(\d+)\s*页', html)
        if total_m:
            max_page = max(max_page, int(total_m.group(1)))

        return max_page

    # ============================================================
    # 首页
    # ============================================================

    def homeContent(self, filter):
        return {
            "class": CLASSES,
            "filters": FILTERS,
        }

    def homeVideoContent(self):
        """首页推荐：从首页获取最新视频，带10分钟缓存，不足时仅补充1个分类页"""
        now = int(time.time())
        if self._home_cache and now - self._home_cache_time < 600:
            return {"list": self._home_cache}

        videos = []

        html = self._fetch_html_fast(HOST + "/")
        if html:
            videos = self._parse_video_cards(html)

        # 如果首页内容不足，仅从1个分类页补充（减少串行请求）
        if len(videos) < 12:
            for c in CLASSES[:2]:  # 最多补充2个分类
                if len(videos) >= 20:
                    break
                cat_html = self._fetch_html_fast(
                    HOST + "/vodshow/" + c["type_id"] + "--------1---.html",
                    timeout=1.5, retries=1
                )
                if cat_html:
                    cat_videos = self._parse_video_cards(cat_html)
                    existing_ids = {v["vod_id"] for v in videos}
                    for v in cat_videos:
                        if v["vod_id"] not in existing_ids:
                            videos.append(v)
                            existing_ids.add(v["vod_id"])

        self._home_cache = videos
        self._home_cache_time = now
        return {"list": self._home_cache}

    # ============================================================
    # 分类列表
    # ============================================================

    def categoryContent(self, tid, pg, filter, extend):
        """分类列表：抓取 vodshow 页面，带5分钟缓存"""
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
                        try:
                            from urllib.parse import parse_qs
                            params = parse_qs(extend)
                            ext = {k: v[0] for k, v in params.items()}
                        except Exception:
                            ext = {}

            cache_key = f"{tid}_{json.dumps(ext, sort_keys=True)}_{page}"
            now = int(time.time())
            if page == 1 and cache_key in self._cat_cache:
                cache_time, cached = self._cat_cache[cache_key]
                if now - cache_time < 300:
                    return cached

            url = self._build_show_url(tid, ext, page)
            html = self._fetch_html(url, timeout=1.5, retries=2)

            if not html:
                return {"page": page, "pagecount": 1, "limit": 20, "total": 0, "list": []}

            videos = self._parse_video_cards(html)
            pagecount = self._parse_pagination(html, "vodshow")
            if pagecount < page:
                pagecount = page

            total = pagecount * len(videos) if videos else 0

            result = {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": len(videos),
                "total": total,
            }

            if page == 1:
                self._cat_cache[cache_key] = (now, result)

            return result
        except Exception:
            return {"page": 1, "pagecount": 1, "limit": 20, "total": 0, "list": []}

    # ============================================================
    # 详情页
    # ============================================================

    def detailContent(self, ids):
        """详情页：抓取 voddetail 页面，提取播放源和剧集"""
        if isinstance(ids, str):
            ids = [ids]
        vod_id = str(ids[0])

        url = HOST + "/voddetail/" + vod_id + ".html"

        html = ""
        for attempt in range(2):
            html = self._fetch_html(url, timeout=1.5, retries=1)
            if html and len(html) > 500:
                break
            time.sleep(0.1)

        if not html:
            return {"list": []}

        # 提取标题
        title = self._match(r'<h1[^>]*>([^<]+)</h1>', html)
        if not title:
            title = self._match(r'class="[^"]*title[^"]*"[^>]*>([^<]+)<', html)
        if not title:
            title = _RE_TITLE_TAG.match(html).group(1) if _RE_TITLE_TAG.search(html) else ""
        if not title:
            title = "未知"
        title = title.strip()

        # 提取图片（优先lazy loading属性，支持CDN和相对路径）
        pic = self._extract_img_from_text(html)
        pic = self._fix_img_url(pic)

        # 提取分类
        type_name = self._match(r'<a[^>]*href="/vodshow/[^"]+"[^>]*>([^<]+)</a>', html)

        # 提取年份
        year = ""
        year_match = re.search(r'>\s*(\d{4})\s*<', html)
        if year_match:
            y = int(year_match.group(1))
            if 1900 < y <= 2027:
                year = str(y)

        # 提取地区
        area = ""
        for ap in [
            r'地区.*?<a[^>]*>([^<]+)</a>',
            r'地区[:：]\s*</[^>]+>\s*<[^>]*>([^<]+)',
            r'地区.*?>([^<]{2,10})<',
        ]:
            am = re.search(ap, html, re.S)
            if am:
                area = am.group(1).strip()
                break

        # 提取导演
        director = ""
        for dp in [
            r'导演.*?<a[^>]*>([^<]+)</a>',
            r'导演[:：]\s*</[^>]+>\s*<a[^>]*>([^<]+)</a>',
            r'class="[^"]*director[^"]*"[^>]*>\s*<a[^>]*>([^<]+)</a>',
            r'导演[:：]\s*<span[^>]*>([^<]+)</span>',
        ]:
            dm = re.search(dp, html, re.S)
            if dm:
                d = dm.group(1).strip()
                # 排除资源站名（含"资源"且长度短）
                if d and '资源' not in d and '线路' not in d:
                    director = d
                    break

        # 提取演员
        actor = ""
        # 先找到主演section，再提取所有<a>标签内容
        actor_section = re.search(r'主演.*?</(?:div|p|section|ul|dl)>', html, re.S)
        if actor_section:
            section_html = actor_section.group(0)
            actor_matches = re.findall(r'<a[^>]*>([^<]+)</a>', section_html)
            if actor_matches:
                actors = [a.strip() for a in actor_matches[:10] if '资源' not in a and '线路' not in a]
                if actors:
                    actor = ",".join(actors)
        if not actor:
            for ap in [
                r'主演[:：]\s*</[^>]+>\s*<a[^>]*>([^<]+)</a>',
                r'class="[^"]*actor[^"]*"[^>]*>\s*<a[^>]*>([^<]+)</a>',
                r'主演[:：]\s*<span[^>]*>([^<]+)</span>',
            ]:
                am = re.search(ap, html, re.S)
                if am:
                    a = am.group(1).strip()
                    if a and '资源' not in a and '线路' not in a:
                        actor = a
                        break

        # 提取简介
        content = ""
        for cp in [
            r'(?:简介|剧情介绍|内容介绍)[:：]?\s*</[^>]+>\s*<[^>]*>(.*?)</',
            r'(?:简介|剧情介绍|内容介绍)[:：]?\s*(.*?)(?:<|$)',
            r'class="[^"]*content[^"]*"[^>]*>(.*?)(?:</div>|</p>)',
        ]:
            cm = re.search(cp, html, re.S)
            if cm:
                content = self._strip_tags(cm.group(1))[:500]
                break

        # 提取备注
        remarks = self._match(r'class="[^"]*(?:remarks|state|pic-text|tag)[^"]*"[^>]*>([^<]{1,20})<', html)
        if not remarks:
            remarks = "HD"

        # ===== 提取播放源和剧集 =====
        play_links = _RE_VODPLAY_LINK.findall(html)

        # 按线路分组
        lines = {}
        for vid, line_num, ep_num, ep_name in play_links:
            lk = int(line_num)
            ep_id = f"{vid}-{line_num}-{ep_num}"
            ep_name = ep_name.strip()
            if not ep_name:
                ep_name = f"第{ep_num}集"
            if lk not in lines:
                lines[lk] = []
            existing_eps = {e[0] for e in lines[lk]}
            if int(ep_num) not in existing_eps:
                lines[lk].append((int(ep_num), ep_name, ep_id))

        for lk in lines:
            lines[lk].sort()

        # ===== 提取线路顺序和名称（按HTML tab顺序，非sid数字排序）=====
        sids = sorted(lines.keys())
        line_order = self._extract_line_order(html, sids, title)

        # 构建 play_from 和 play_url（按HTML tab顺序）
        play_from = []
        play_url = []
        for sid, name in line_order:
            if sid in lines:
                play_from.append(name)
                ep_list = [f"{ep_name}${ep_id}" for _, ep_name, ep_id in lines[sid]]
                play_url.append("#".join(ep_list))

        if not play_url:
            return {"list": []}

        vod = {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic or "",
            "type_name": type_name or "",
            "vod_year": year or "",
            "vod_area": area or "",
            "vod_remarks": remarks or "HD",
            "vod_actor": actor or "",
            "vod_director": director or "",
            "vod_content": content or "",
            "vod_play_from": "$$$".join(play_from) if play_from else "4K影仓",
            "vod_play_url": "$$$".join(play_url) if play_url else "",
        }
        return {"list": [vod]}

    def _extract_line_order(self, html, sids, video_title=""):
        """
        从HTML中提取线路的显示顺序和名称。
        返回 [(sid, name), ...] 列表，按HTML中tab的出现顺序排列。
        如果无法确定顺序，回退到按sid排序。
        """
        sid_set = set(sids)
        result = []  # [(sid, name)]
        used_sids = set()

        title_lower = (video_title or "").strip().lower()
        _BAD_NAMES = {'简介','剧情','推荐','评论','相关','下载','播放','选集','详情','资讯','首页','更多','展开','收起'}

        def is_valid(text):
            if not text or len(text) >= 30:
                return False
            tl = text.lower().strip()
            if title_lower and (tl == title_lower or (title_lower in tl and len(tl) < len(title_lower) + 10)):
                return False
            if text in _SKIP_TEXTS or text in _SKIP_NAV or text in _BAD_NAMES or text.isdigit():
                return False
            return True

        def clean_name(text):
            text = self._strip_tags(text).strip()
            text = re.sub(r'[-—]\s*在线播放\s*$', '', text)
            text = re.sub(r'[-—]\s*播放\s*$', '', text)
            bracket_m = re.search(r'[\[(（]([^)\]）]+)[\])）]\s*$', text)
            if bracket_m:
                text = bracket_m.group(1).strip()
            return text

        def try_add_sid(sid, name):
            """Try to add a sid with name, handling 0-indexed tabs"""
            if sid in sid_set and sid not in used_sids and is_valid(name):
                result.append((sid, name))
                used_sids.add(sid)
                return True
            return False

        # 1. JS变量 vod_play_from (含$$$分隔符，最可靠)
        js_from = self._match(r'(?:vod_play_from|play_from)\s*[=:]\s*["\']([^"\']+)["\']', html)
        if js_from and '$$$' in js_from:
            js_names = [n.strip() for n in js_from.split('$$$') if n.strip()]
            sorted_sids = sorted(sid_set)
            for i, sid in enumerate(sorted_sids):
                if i < len(js_names) and is_valid(js_names[i]):
                    result.append((sid, js_names[i]))
                    used_sids.add(sid)
            if len(result) == len(sids):
                return result

        # 2. data-tab="playlistN" 格式（按HTML顺序）
        if len(result) < len(sids):
            tabs = re.findall(
                r'data-tab="\.?playlist(\d+)"[^>]*>(.*?)</(?:div|a|li|span|button)>',
                html, re.S | re.I
            )
            for sid_str, content in tabs:
                sid = int(sid_str)
                name = clean_name(content)
                if try_add_sid(sid, name):
                    continue
                # 尝试偏移±1（处理0-indexed tabs）
                if try_add_sid(sid + 1, name):
                    continue
                try_add_sid(sid - 1, name)

        # 3. href="#playlistN" 格式
        if len(result) < len(sids):
            tabs = re.findall(
                r'href="#playlist(\d+)"[^>]*>(.*?)</a>',
                html, re.S | re.I
            )
            for sid_str, content in tabs:
                sid = int(sid_str)
                name = clean_name(content)
                try_add_sid(sid, name)

        # 4. data-target="#playlistN" 格式
        if len(result) < len(sids):
            tabs = re.findall(
                r'data-target="#playlist(\d+)"[^>]*>(.*?)</(?:div|a|li|span|button)>',
                html, re.S | re.I
            )
            for sid_str, content in tabs:
                sid = int(sid_str)
                name = clean_name(content)
                try_add_sid(sid, name)

        # 5. option value="playlistN" 格式
        if len(result) < len(sids):
            tabs = re.findall(
                r'<option[^>]*value="playlist(\d+)"[^>]*>([^<]+)</option>',
                html, re.I
            )
            for sid_str, content in tabs:
                sid = int(sid_str)
                name = clean_name(content)
                try_add_sid(sid, name)

        # 6. 从 #playlistN div 内的 h2/h3 提取名称
        for sid in sorted(sid_set - used_sids):
            for h_pat in [
                r'id="playlist%d"[^>]*>.*?<h[23][^>]*>(.*?)</h[23]>' % sid,
                r'id="playlist%d"[^>]*>.*?<span[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</span>' % sid,
            ]:
                m = re.search(h_pat, html, re.S | re.I)
                if m:
                    name = clean_name(m.group(1))
                    if is_valid(name):
                        result.append((sid, name))
                        used_sids.add(sid)
                        break

        # 7. 位置映射：tab元素无sid属性时，按位置映射
        if len(result) < len(sids):
            all_tab_contents = re.findall(
                r'class="[^"]*(?:module-tab-item|tab-item|play-tab|tab-link|nav-link|play-tab-item)[^"]*"[^>]*>(.*?)</(?:div|a|li|span|button)>',
                html, re.S | re.I
            )
            remaining_sids = sorted(sid_set - used_sids)
            for i, content in enumerate(all_tab_contents):
                if i >= len(remaining_sids):
                    break
                sid = remaining_sids[i]
                name = clean_name(content)
                if is_valid(name):
                    result.append((sid, name))
                    used_sids.add(sid)

        # 8. 后备：JS单个名称
        if js_from and '$$$' not in js_from and is_valid(js_from):
            for sid in sorted(sid_set - used_sids):
                result.append((sid, js_from))
                used_sids.add(sid)
                break  # 只用一次

        # 9. 最终后备：线路N（按sid排序）
        for sid in sorted(sid_set - used_sids):
            result.append((sid, f"线路{sid}"))

        return result

    # ============================================================
    # 搜索
    # ============================================================

    def searchContent(self, key, quick, pg="1"):
        """搜索：多种URL格式尝试，带2分钟缓存"""
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1

            if not key or not key.strip():
                return {"list": []}

            wd = key.strip()

            # 搜索缓存检查
            cache_key = f"{wd}_{page}"
            now = int(time.time())
            if cache_key in self._search_cache:
                cache_time, cached = self._search_cache[cache_key]
                if now - cache_time < 120:
                    return cached

            # 尝试多种搜索URL格式
            search_urls = self._build_search_urls(wd, page)
            html = ""
            for url in search_urls:
                if not url:
                    continue
                html = self._fetch_html(url, timeout=1.5, retries=1)
                if html and '/voddetail/' in html:
                    break
                html = ""

            if not html:
                # 最后尝试 AJAX 建议 API
                ajax_url = HOST + "/index.php/ajax/suggest?mid=1&wd=" + quote(wd, safe="") + "&limit=20"
                try:
                    rsp = self.fetch(ajax_url, headers=self.header, timeout=1.5)
                    data = json.loads(self._rsp_text(rsp))
                    if data.get("code") == 1 and data.get("list"):
                        videos = []
                        for item in data["list"]:
                            pic = item.get("pic", "")
                            if pic:
                                pic = self._fix_img_url(pic)
                            videos.append({
                                "vod_id": str(item.get("id", "")),
                                "vod_name": item.get("name", ""),
                                "vod_pic": pic,
                                "vod_remarks": "HD",
                            })
                        if videos:
                            result = {"list": videos}
                            self._search_cache[cache_key] = (now, result)
                            return result
                except Exception:
                    pass
                return {"list": []}

            videos = self._parse_video_cards(html)

            if not videos:
                return {"list": []}

            result = {"list": videos}
            self._search_cache[cache_key] = (now, result)
            # 清理过期缓存
            if len(self._search_cache) > 50:
                expired = [k for k, (t, _) in self._search_cache.items() if now - t > 300]
                for k in expired:
                    del self._search_cache[k]

            return result
        except Exception:
            return {"list": []}

    # ============================================================
    # 播放解析
    # ============================================================

    def playerContent(self, flag, id, vipFlags):
        """
        播放解析：抓取 vodplay 页面，解析 player_aaaa 变量
        直链直接播放(parse=0)，非直链交壳子嗅探(parse=1)
        播放地址缓存10分钟
        """
        if not id:
            return {"parse": 0, "playUrl": "", "url": ""}

        play_id = str(id).replace("\\/", "/").strip()

        # 播放地址缓存检查（15分钟）
        now = int(time.time())
        if play_id in self._play_cache:
            cache_time, cached = self._play_cache[play_id]
            if now - cache_time < 900:
                return cached

        # 如果已经是直链，直接播放
        if self._is_direct_media(play_id):
            is_m3u8 = ".m3u8" in play_id.lower()
            media_referer = self._extract_referer(play_id)
            result = {
                "parse": 0,
                "playUrl": "",
                "url": play_id,
                "header": {
                    "User-Agent": UA,
                    "Referer": media_referer,
                },
                "format": "application/x-mpegURL" if is_m3u8 else "",
                "contentType": "application/x-mpegURL" if is_m3u8 else "",
            }
            self._play_cache[play_id] = (now, result)
            return result

        # 构建 vodplay URL
        play_url = HOST + "/vodplay/" + play_id + ".html"

        # 快速获取播放页（1次重试，1.5秒超时）
        html = self._fetch_html_fast(play_url, timeout=1.5, retries=1)

        if not html:
            result = {
                "parse": 1,
                "playUrl": "",
                "url": play_url,
                "header": {
                    "User-Agent": UA,
                    "Referer": HOST + "/",
                },
            }
            self._play_cache[play_id] = (now, result)
            return result

        # 解析 player_aaaa 变量
        video_url = self._extract_player_url(html)

        if not video_url:
            result = {
                "parse": 1,
                "playUrl": "",
                "url": play_url,
                "header": {
                    "User-Agent": UA,
                    "Referer": HOST + "/",
                },
            }
            self._play_cache[play_id] = (now, result)
            return result

        # 如果是直链，直接播放
        if self._is_direct_media(video_url):
            is_m3u8 = ".m3u8" in video_url.lower()
            media_referer = self._extract_referer(video_url)
            result = {
                "parse": 0,
                "playUrl": "",
                "url": video_url,
                "header": {
                    "User-Agent": UA,
                    "Referer": media_referer,
                },
                "format": "application/x-mpegURL" if is_m3u8 else "",
                "contentType": "application/x-mpegURL" if is_m3u8 else "",
            }
            self._play_cache[play_id] = (now, result)
            return result

        # 非直链，交给壳子解析
        result = {
            "parse": 1,
            "playUrl": "",
            "url": video_url,
            "header": {
                "User-Agent": UA,
                "Referer": HOST + "/",
            },
        }
        self._play_cache[play_id] = (now, result)
        return result

    def _extract_player_url(self, html):
        """从播放页 HTML 中解析 player_aaaa 变量，提取真实视频地址"""
        # 尝试匹配 player_aaaa = {...}
        match = _RE_PLAYER_AAAA.search(html)
        if not match:
            match = _RE_PLAYER_CFG.search(html)
        if not match:
            match = _RE_PLAYER_DATA.search(html)

        if not match:
            # 尝试直接从 HTML 中找 m3u8/mp4 链接
            url_match = _RE_M3U8_URL.search(html)
            if url_match:
                return url_match.group(0)
            url_match = _RE_MP4_URL.search(html)
            if url_match:
                return url_match.group(0)
            return ""

        raw_json = match.group(1)

        try:
            player_data = json.loads(raw_json)
        except Exception:
            url = self._match(r'"url"\s*:\s*"([^"]+)"', raw_json)
            if url:
                return url.replace("\\/", "/")
            return ""

        video_url = player_data.get("url", "")
        encrypt = int(player_data.get("encrypt", 0))

        if not video_url:
            # 尝试从 player_data 中找其他 URL 字段
            for key in ('url_next', 'link', 'url3', 'url2'):
                video_url = player_data.get(key, "")
                if video_url:
                    break

        if not video_url:
            return ""

        # 解密
        if encrypt == 1:
            video_url = unquote(video_url)
        elif encrypt == 2:
            try:
                video_url = base64.b64decode(video_url).decode('utf-8', 'ignore')
            except Exception:
                pass

        video_url = video_url.replace("\\/", "/")
        return video_url

    # ===== 本地代理（图片代理）=====
    def localProxy(self, param):
        """本地代理：支持图片代理加载，自动补全Referer头"""
        try:
            url = ""
            if isinstance(param, dict):
                url = param.get("url", "")
            else:
                # 解析参数
                params = {}
                if isinstance(param, str):
                    for pair in param.split("&"):
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            params[k] = v
                url = params.get("url", "")

            if not url:
                return [200, "image/jpeg", b"", ""]

            # URL修复
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/") and not url.startswith("//"):
                url = HOST + url

            # 根据图片域名设置Referer
            referer = self._extract_referer(url)

            rsp = self.fetch(url, headers={
                "User-Agent": UA,
                "Referer": referer,
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            }, timeout=1.5)

            content = rsp.content
            if not content:
                return [200, "image/jpeg", b"", ""]

            content_type = rsp.headers.get("Content-Type", "image/jpeg")
            # 确保是图片类型
            if not content_type.startswith("image/"):
                # 根据URL后缀推断
                url_lower = url.lower()
                if ".png" in url_lower:
                    content_type = "image/png"
                elif ".webp" in url_lower:
                    content_type = "image/webp"
                elif ".gif" in url_lower:
                    content_type = "image/gif"
                else:
                    content_type = "image/jpeg"

            return [200, content_type, content, ""]
        except Exception:
            return [200, "image/jpeg", b"", ""]

    # ===== 清理 =====
    def destroy(self):
        pass

    def close(self):
        self.destroy()

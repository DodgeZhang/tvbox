# -*- coding: utf-8 -*-
"""
兔岛影院 Python Spider — https://www.ct0592.com
全面修复版：修复二级分类、播放源、加载速度
"""

import sys
import re
import json
import time
import base64
from urllib.parse import quote, unquote, urljoin

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    try:
        import requests as _rq
        try:
            import urllib3
            urllib3.disable_warnings()
        except Exception:
            pass

        class Spider:
            def fetch(self, url, headers=None, **kw):
                timeout = kw.pop("timeout", 15)
                r = _rq.get(url, headers=headers, timeout=timeout, verify=False, **kw)
                r.encoding = "utf-8"
                return r
    except ImportError:
        import urllib.request as _ur

        class _Resp:
            def __init__(self, raw):
                self.text = raw.decode("utf-8", errors="ignore")
                self.encoding = "utf-8"

        class Spider:
            def fetch(self, url, headers=None, **kw):
                timeout = kw.pop("timeout", 15)
                req = _ur.Request(url, headers=headers or {})
                return _Resp(_ur.urlopen(req, timeout=timeout).read())


HOST = "https://www.ct0592.com"
UA = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

# 分类映射：一级名称 -> {tid, 子分类}
CAT_MAP = {
    "movie": {"name": "电影", "tid": "1", "subs": {
        "5": "动作片", "6": "爱情片", "7": "科幻片", "8": "恐怖片",
        "9": "战争片", "10": "喜剧片", "11": "纪录片", "12": "剧情片",
        "28": "悬疑片", "29": "犯罪片",
    }},
    "tv": {"name": "电视剧", "tid": "2", "subs": {
        "13": "国产剧", "14": "港剧", "15": "欧美剧", "16": "韩剧",
        "32": "台湾剧", "33": "日本剧", "34": "海外剧", "42": "泰剧", "60": "亚洲剧",
    }},
    "zy": {"name": "综艺", "tid": "3", "subs": {
        "45": "国产综艺", "46": "日韩综艺", "47": "港台综艺", "48": "欧美综艺",
    }},
    "dm": {"name": "动漫", "tid": "4", "subs": {
        "49": "国产动漫", "50": "日韩动漫", "51": "欧美动漫",
        "52": "动漫电影", "53": "港台动漫", "54": "海外动漫",
    }},
    "dj": {"name": "短剧", "tid": "30", "subs": {
        "61": "有声动漫", "62": "女频恋爱", "63": "反转爽剧", "64": "脑洞悬疑",
        "65": "年代穿越", "66": "古装仙侠", "67": "现代都市", "69": "爽文短剧",
    }},
    "yg": {"name": "预告", "tid": "55", "subs": {}},
}

# 构建 CLASSES 和 FILTERS（TVBox 标准格式）
# type_id 使用站点一级分类数字 ID，兼容性更好，filters 的 key 与 type_id 对应
CLASSES = []
FILTERS = {}
for cat_id, cat_info in CAT_MAP.items():
    CLASSES.append({"type_name": cat_info["name"], "type_id": cat_info["tid"]})
    values = [{"n": "全部", "v": ""}]  # 空字符串代表全部，更兼容
    for sub_id, sub_name in cat_info["subs"].items():
        values.append({"n": sub_name, "v": sub_id})
    if len(values) > 1:
        FILTERS[cat_info["tid"]] = [{"key": "cate", "name": "分类", "init": "", "value": values}]

SEARCH_PAGE_SIZE = 20


class Spider(Spider):

    def getName(self):
        return "兔岛影院"

    def init(self, extend=""):
        self.base_header = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        self.session = None
        try:
            import requests
            self.session = requests.Session()
            self.session.headers.update(self.base_header)
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=20, pool_maxsize=50, max_retries=0
            )
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
        except Exception:
            pass
        self._cache = {}
        self._cache_ts = {}

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return any(ext in u for ext in [".m3u8", ".mp4", ".flv", ".ts", ".mkv", ".avi"])

    def _get_html(self, url, timeout=10, referer=None):
        headers = dict(self.base_header)
        if referer:
            headers["Referer"] = referer
        else:
            headers["Referer"] = HOST + "/"
        try:
            if self.session:
                r = self.session.get(url, headers=headers, timeout=timeout, verify=False)
            else:
                r = self.fetch(url, headers=headers, timeout=timeout)
            if r and r.status_code == 200:
                r.encoding = "utf-8"
                return r.text
            print(f"[兔岛影院] 状态码异常 {url}: {getattr(r, 'status_code', 'N/A')}")
            return ""
        except Exception as e:
            print(f"[兔岛影院] 请求失败 {url}: {e}")
            return ""

    def _abs_url(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return HOST + url
        if not url.startswith("http"):
            return urljoin(HOST + "/", url)
        return url

    @staticmethod
    def _strip(txt):
        return re.sub(r"\s+", " ", (txt or "")).strip()

    def _parse_vodlist(self, html):
        """解析影片列表"""
        items = []
        if not html:
            return items

        # 方法1：匹配 stui-vodlist__thumb 完整块
        blocks = re.findall(
            r'<a[^>]*class="stui-vodlist__thumb[^"]*"[^>]*>.*?</a>',
            html, re.DOTALL
        )
        for block in blocks:
            m_id = re.search(r'href="/ct0vod/(\d+)\.html"', block)
            if not m_id:
                continue
            vod_id = m_id.group(1)
            m_title = re.search(r'title="([^"]*)"', block)
            title = self._strip(m_title.group(1)) if m_title else ""
            m_pic = re.search(r'data-original="([^"]*)"', block)
            pic = self._abs_url(m_pic.group(1)) if m_pic else ""
            m_remark = re.search(r'<span[^>]*class="pic-text[^"]*"[^>]*>([^<]+)</span>', block)
            remark = self._strip(m_remark.group(1)) if m_remark else ""
            items.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark,
            })

        # 方法2：兜底
        if not items:
            for m in re.finditer(r'href="/ct0vod/(\d+)\.html"[^>]*title="([^"]*)"', html):
                items.append({
                    "vod_id": m.group(1),
                    "vod_name": self._strip(m.group(2)),
                    "vod_pic": "",
                    "vod_remarks": "",
                })

        seen, uniq = set(), []
        for it in items:
            if it["vod_id"] not in seen:
                seen.add(it["vod_id"])
                uniq.append(it)
        return uniq

    # ===== 首页 =====
    def homeContent(self, filter):
        result = {"class": CLASSES}
        if filter:
            result["filters"] = FILTERS
        return result

    def homeVideoContent(self):
        cache_key = "home"
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and now - self._cache_ts.get(cache_key, 0) < 60:
            html = cached
        else:
            html = self._get_html(HOST + "/", timeout=8)
            self._cache[cache_key] = html
            self._cache_ts[cache_key] = now
        if not html:
            return {"list": []}
        items = self._parse_vodlist(html)
        return {"list": items[:30]}

    # ===== 分类列表 =====
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg or 1)
            if page < 1:
                page = 1
            per_page = 24

            # tid 可能是一级分类名（如 movie）或一级分类数字 ID（如 1），也可能是二级分类 ID
            cat = CAT_MAP.get(tid)
            if not cat:
                for v in CAT_MAP.values():
                    if v["tid"] == str(tid):
                        cat = v
                        break
            if cat:
                sub_tid = (extend or {}).get("cate") if extend else None
                if sub_tid:
                    req_tid = sub_tid
                else:
                    req_tid = cat["tid"]
            else:
                req_tid = tid

            cache_key = f"cat_{req_tid}_{page}"
            now = time.time()
            cached = self._cache.get(cache_key)
            if cached and now - self._cache_ts.get(cache_key, 0) < 30:
                return cached

            if page == 1:
                url = f"{HOST}/ct0list/{req_tid}.html"
            else:
                url = f"{HOST}/ct0list/{req_tid}-{page}.html"

            html = self._get_html(url, timeout=10, referer=HOST + "/")
            if not html:
                return {"page": page, "pagecount": page, "limit": per_page, "total": 0, "list": []}

            items = self._parse_vodlist(html)

            # 分页判断
            pagecount = page
            m = re.search(r'class="pagination".*?</ul>', html, re.DOTALL)
            if m:
                pages = re.findall(r'[?&/-](\d+)\.html', m.group(0))
                if pages:
                    pagecount = max(int(p) for p in pages)
                m2 = re.search(r'共\s*(\d+)\s*页', m.group(0))
                if m2:
                    pagecount = int(m2.group(1))
            else:
                has_next = re.search(
                    r'href="/ct0list/' + re.escape(req_tid) + r'-' + str(page + 1) + r'\.html"',
                    html
                )
                pagecount = page + 1 if has_next else page

            total = pagecount * per_page
            result = {
                "list": items,
                "page": page,
                "pagecount": pagecount,
                "limit": per_page,
                "total": total,
            }
            self._cache[cache_key] = result
            self._cache_ts[cache_key] = now
            return result
        except Exception as e:
            print(f"[兔岛影院] categoryContent 异常: {e}")
            return {"page": 1, "pagecount": 1, "limit": 24, "total": 0, "list": []}

    # ===== 详情页 =====
    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            ids = ids[0]
        vod_id = str(ids)
        html = self._get_html(f"{HOST}/ct0vod/{vod_id}.html", timeout=12, referer=HOST + "/")
        if not html or len(html) < 500:
            print(f"[兔岛影院] 详情页获取失败或内容太短: {vod_id}")
            return {"list": []}

        try:
            vod = {
                "vod_id": vod_id, "vod_name": "", "vod_pic": "",
                "vod_year": "", "vod_area": "", "vod_remarks": "",
                "vod_actor": "", "vod_director": "", "vod_class": "",
                "vod_content": "", "vod_play_from": "", "vod_play_url": "",
            }

            # 标题
            m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            if m:
                vod["vod_name"] = self._strip(m.group(1))
            if not vod["vod_name"]:
                m = re.search(r'<title>([^<]+)</title>', html)
                if m:
                    title = re.sub(r'[-_|\s].*?(兔岛影院|在线观看|免费观看|高清).*', '', m.group(1), flags=re.I)
                    vod["vod_name"] = self._strip(title)

            # 封面
            m = re.search(
                r'<img[^>]+class="[^"]*(?:img-responsive|lazyload|pic)[^"]*"[^>]+(?:data-original|src)="([^"]+)"',
                html
            ) or re.search(
                r'<img[^>]+(?:data-original|src)="([^"]+)"[^>]+class="[^"]*(?:img-responsive|lazyload|pic)[^"]*"',
                html
            )
            if m:
                vod["vod_pic"] = self._abs_url(m.group(1).strip())

            # 信息
            info_section = re.search(
                r'<div[^>]*class="[^"]*stui-content__detail[^"]*"[^>]*>(.*?)</div>\s*</div>',
                html, re.DOTALL
            )
            if not info_section:
                info_section = re.search(r'<div[^>]*class="[^"]*data[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            info_text = info_section.group(1) if info_section else html

            info_map = {
                '导演': 'vod_director', '主演': 'vod_actor', '类型': 'vod_class',
                '分类': 'vod_class', '地区': 'vod_area', '年份': 'vod_year',
                '年代': 'vod_year', '语言': 'vod_lang', '更新': 'vod_remarks',
                '状态': 'vod_remarks', '备注': 'vod_remarks',
            }
            for kw, key in info_map.items():
                pats = [
                    rf'<(?:p|div)[^>]*>.*?<strong>{kw}[：:]</strong>(.*?)</(?:p|div)>',
                    rf'<span[^>]*>.*?{kw}[：:](.*?)</span>',
                    rf'{kw}[：:]\s*([^<\n]+)',
                ]
                for pat in pats:
                    m = re.search(pat, info_text, re.DOTALL | re.I)
                    if m:
                        txt = re.sub(r'<[^>]+>', '', m.group(1))
                        val = self._strip(txt)
                        if val and not val.endswith('：'):
                            vod[key] = val
                            break

            # 简介
            for pat in [
                r'<strong>简介[：:]</strong>([\s\S]*?)</p>',
                r'class="[^"]*sketch[^"]*"[^>]*>([\s\S]*?)</(?:p|div)>',
                r'class="[^"]*desc[^"]*"[^>]*>([\s\S]*?)</(?:p|div)>',
            ]:
                m = re.search(pat, html, re.DOTALL | re.I)
                if m:
                    txt = re.sub(r'<[^>]+>', '', m.group(1))
                    vod["vod_content"] = self._strip(txt)[:500]
                    break

            # 播放列表（核心修复：兼容多种播放链接格式）
            play_from, play_url = self._collect_playlist(html)
            if play_from:
                vod["vod_play_from"] = "$$$".join(play_from)
                vod["vod_play_url"] = "$$$".join(play_url)
            else:
                print(f"[兔岛影院] 未解析到播放列表: {vod_id}")

            return {"list": [vod]}
        except Exception as e:
            print(f"[兔岛影院] detailContent 异常: {e}")
            return {"list": []}

    def _collect_playlist(self, html):
        """解析播放源 + 剧集，按 panel 提取真实线路名并升序排序"""
        play_from, play_url = [], []

        # 按播放源 panel 拆分；每个有效 panel 包含 h3.title + ul.stui-content__playlist
        panels = re.split(r'(?=<div[^>]*class="[^"]*stui-pannel stui-pannel-bg[^"]*"[^>]*>)', html)
        for panel in panels[1:]:
            # 线路名：panel 内第一个 h3.title
            src_m = re.search(r'<h3[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h3>', panel, re.DOTALL)
            if not src_m:
                continue
            src_name = self._strip(re.sub(r'<[^>]+>', '', src_m.group(1)))
            # 过滤明显不是播放源的区块
            if not src_name or any(bad in src_name for bad in ('猜你喜欢', '热播', '排行', '推荐', '相关')):
                continue

            # 该 panel 内的播放列表
            ul_m = re.search(r'<ul[^>]*class="[^"]*stui-content__playlist[^"]*"[^>]*>(.*?)</ul>', panel, re.DOTALL)
            if not ul_m:
                continue
            ul_html = ul_m.group(1)

            eps = []
            # 兔岛影院真实格式：/ct0player/{vod_id}-{source_index}-{episode_index}.html
            for em in re.finditer(r'<a[^>]+href="(/ct0player/\d+-\d+-\d+\.html)"[^>]*>([\s\S]*?)</a>', ul_html):
                ep_name = self._strip(re.sub(r'<[^>]+>', '', em.group(2))) or '正片'
                eps.append(f"{ep_name}${em.group(1)}")

            if not eps:
                continue

            # 按集数自然升序排序（原页面是倒序：第12集在前）
            eps.sort(key=self._ep_sort_key)
            play_from.append(src_name)
            play_url.append("#".join(eps))

        # 兜底：如果按 panel 没解析到，直接抓页面中所有 ct0player 链接
        if not play_from:
            eps = []
            for em in re.finditer(r'<a[^>]+href="(/ct0player/\d+-\d+-\d+\.html)"[^>]*>([\s\S]*?)</a>', html):
                ep_name = self._strip(re.sub(r'<[^>]+>', '', em.group(2))) or "正片"
                eps.append(f"{ep_name}${em.group(1)}")
            if eps:
                eps.sort(key=self._ep_sort_key)
                play_from.append("默认线路")
                play_url.append("#".join(eps))

        return play_from, play_url

    def _ep_sort_key(self, ep_str):
        """剧集排序 key：按名称中的第一个数字升序，无数字的放最后"""
        name = ep_str.split('$', 1)[0]
        nums = re.findall(r'\d+', name)
        if nums:
            return (0, int(nums[0]))
        return (1, 0)

    # ===== 搜索 =====
    def searchContent(self, key, quick, pg="1"):
        try:
            kw = self._strip(str(key or ""))
            if not kw:
                return {"list": []}
            page = int(pg or 1)
            if page < 1:
                page = 1

            cache_key = f"search_{kw}_{page}"
            now = time.time()
            cached = self._cache.get(cache_key)
            if cached and now - self._cache_ts.get(cache_key, 0) < 30:
                return cached

            search_url = f"{HOST}/search.php?searchword={quote(kw)}"
            if page > 1:
                search_url += f"&page={page}"

            html = self._get_html(search_url, timeout=10, referer=HOST + "/")
            items = self._parse_vodlist(html) if html else []

            seen, uniq = set(), []
            for it in items:
                if it["vod_id"] not in seen:
                    seen.add(it["vod_id"])
                    uniq.append(it)

            has_next = False
            if html:
                has_next = bool(re.search(
                    r'href="[^"]*searchword=' + re.escape(quote(kw)) + r'[^"]*page=' + str(page + 1) + r'["&]',
                    html
                ))
            total = len(uniq)
            pagecount = page + 1 if has_next else page

            result = {
                "list": uniq, "page": page, "pagecount": pagecount,
                "limit": SEARCH_PAGE_SIZE, "total": total,
            }
            self._cache[cache_key] = result
            self._cache_ts[cache_key] = now
            return result
        except Exception as e:
            print(f"[兔岛影院] searchContent 异常: {e}")
            return {"list": []}

    # ===== 播放 =====
    def playerContent(self, flag, id, vipFlags):
        play_url = str(id or "")
        if not play_url:
            return {"parse": 0, "url": ""}

        if self.isVideoFormat(play_url):
            return {
                "parse": 0, "url": play_url,
                "header": {"User-Agent": UA, "Referer": HOST + "/"},
            }

        # 补全相对路径
        if play_url.startswith("/"):
            play_url = HOST + play_url

        if "/ct0play/" in play_url or "/play/" in play_url or "/vodplay/" in play_url or "/ct0player/" in play_url:
            html = self._get_html(play_url, timeout=10, referer=HOST + "/")
            if html:
                real = self._extract_video_url(html)
                if real:
                    return {
                        "parse": 0, "url": real,
                        "header": {"User-Agent": UA, "Referer": play_url},
                    }
                # 如果没有提取到直链，返回播放页让播放器 iframe 解析
                return {
                    "parse": 1, "url": play_url,
                    "header": {"User-Agent": UA, "Referer": play_url},
                }

        return {
            "parse": 0, "url": play_url,
            "header": {"User-Agent": UA, "Referer": HOST + "/"},
        }

    def _extract_video_url(self, html):
        """从播放页提取真实视频地址"""
        # 1) iframe
        m = re.search(r'<iframe[^>]+src="([^"]+)"', html, re.I)
        if m:
            src = m.group(1).strip()
            if self.isVideoFormat(src):
                return src
            if "url=" in src:
                q = re.search(r'[?&]url=([^&]+)', src)
                if q:
                    decoded = unquote(q.group(1))
                    if self.isVideoFormat(decoded):
                        return decoded

        # 2) video 标签
        m = re.search(r'<video[^>]+src="([^"]+)"', html, re.I)
        if m:
            return m.group(1).strip()

        # 3) Base64 分段
        parts_match = re.search(r'const\s+parts\s*=\s*\[(.*?)\];', html, re.DOTALL)
        if parts_match:
            parts_str = parts_match.group(1)
            parts = re.findall(r'["\']([A-Za-z0-9+/=]{10,})["\']', parts_str)
            if parts:
                try:
                    decoded = base64.b64decode(''.join(parts)).decode('utf-8')
                    if self.isVideoFormat(decoded):
                        return decoded
                except Exception:
                    pass

        # 4) JS 变量（兔岛影院在播放页用 var now="..." 存放当前集真实 m3u8）
        js_patterns = [
            (r'var\s+now\s*=\s*[\'"]([^\'"]+)[\'"]', 'str'),
            (r'var\s+player_[a-zA-Z0-9_]+\s*=\s*(\{.*?\});', 'json'),
            (r'var\s+mac_url\s*=\s*[\'"]([^\'"]+)[\'"]', 'str'),
            (r'var\s+url\s*=\s*[\'"]([^\'"]+)[\'"]', 'str'),
            (r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', 'str'),
            (r'"url"\s*:\s*"([^"]+\.mp4[^"]*)"', 'str'),
            (r'"url"\s*:\s*"([^"]+)"', 'str'),
        ]
        for pat, typ in js_patterns:
            m = re.search(pat, html, re.DOTALL)
            if m:
                if typ == 'json':
                    try:
                        obj = json.loads(m.group(1))
                        if obj.get("url"):
                            return obj["url"]
                    except Exception:
                        pass
                else:
                    url = m.group(1).strip()
                    if self.isVideoFormat(url):
                        return url

        # 5) 页面直链
        m = re.search(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)', html)
        if m:
            return m.group(1).strip()

        return ""

    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]

    def destroy(self):
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass

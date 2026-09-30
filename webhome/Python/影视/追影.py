# -*- coding: utf-8 -*-
# 追影(zhuiying3.cc) · 极速版爬虫源
# 特性：二级分类筛选、精准搜索、直连播放源、缓存加速
# TVBox 标准入口：get_spider()

import sys
sys.path.append('..')
from base.spider import Spider
import re
import json
import hashlib
import time
import base64
from urllib.parse import quote

# ==================== 基础配置 ====================
BASE_URL = "https://zhuiying3.cc"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 分类映射 (中文名 -> URL标识)
CATEGORY_MAP = {
    "电影": "dianying",
    "电视剧": "dianshiju",
    "动漫": "dongman",
    "综艺": "zongyi",
    "短剧": "duanju",
}

# 二级筛选配置
FILTER_CONFIG = {
    "dianying": {
        "类型": ["全部", "科幻", "剧情", "惊悚", "爱情", "古装", "动作", "悬疑", "犯罪",
                 "谍战", "历史", "喜剧", "奇幻", "家庭", "青春", "冒险", "纪录", "动画",
                 "人物", "文化", "其他"],
        "地区": ["全部", "中国大陆", "中国香港", "中国台湾", "美国", "日本", "韩国",
                 "泰国", "英国", "法国", "德国", "意大利", "印度", "马来西亚"],
        "年份": ["全部", "2026", "2025", "2024", "2023", "2022", "2021", "2020",
                 "2019", "2018", "2017", "2016", "2015", "2014", "2013", "2012",
                 "2011", "2010", "2009", "2008"],
        "排序": ["综合排序", "热度最高", "最新上线", "最好评"],
    },
    "dianshiju": {
        "类型": ["全部", "国产", "欧美", "日本", "韩国", "港台", "其他", "剧情", "爱情",
                 "古装", "喜剧", "动作", "悬疑", "犯罪", "奇幻", "科幻", "家庭"],
        "地区": ["全部", "中国大陆", "中国香港", "中国台湾", "美国", "日本", "韩国",
                 "泰国", "英国"],
        "年份": ["全部", "2026", "2025", "2024", "2023", "2022", "2021", "2020",
                 "2019", "2018", "2017", "2016", "2015"],
        "排序": ["综合排序", "热度最高", "最新上线", "最好评"],
    },
    "dongman": {
        "类型": ["全部", "日本动漫", "国产动漫", "欧美动漫", "其他动漫"],
        "地区": ["全部", "日本", "中国大陆", "美国", "韩国"],
        "年份": ["全部", "2026", "2025", "2024", "2023", "2022", "2021", "2020"],
        "排序": ["综合排序", "热度最高", "最新上线", "最好评"],
    },
    "zongyi": {
        "类型": ["全部", "国产综艺", "日韩综艺", "欧美综艺", "港台综艺"],
        "地区": ["全部", "中国大陆", "韩国", "日本", "中国台湾", "中国香港", "美国"],
        "年份": ["全部", "2026", "2025", "2024", "2023", "2022", "2021", "2020"],
        "排序": ["综合排序", "热度最高", "最新上线", "最好评"],
    },
    "duanju": {
        "类型": ["全部", "甜宠", "古装", "都市", "悬疑", "逆袭", "穿越", "其他"],
        "地区": ["全部", "中国大陆"],
        "年份": ["全部", "2026", "2025", "2024", "2023"],
        "排序": ["综合排序", "热度最高", "最新上线", "最好评"],
    },
}

# 排序映射
SORT_MAP = {
    "综合排序": "",
    "热度最高": "hits_week",
    "最新上线": "id",
    "最好评": "douban_score",
}

# 视频扩展名
VIDEO_EXTS = ('.m3u8', '.mp4', '.flv', '.mkv', '.avi', '.ts', '.mpg', '.m3u')


# ==================== 缓存机制 ====================
class SimpleCache:
    """简单内存缓存，加速重复请求"""
    def __init__(self, max_size=50, ttl=300):
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl

    def get(self, key):
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry['time'] < self.ttl:
                return entry['data']
            else:
                del self.cache[key]
        return None

    def set(self, key, data):
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]['time'])
            del self.cache[oldest_key]
        self.cache[key] = {'data': data, 'time': time.time()}


# ==================== 工具函数 ====================
def _strip_html(text):
    """去除HTML标签并清理空白"""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ==================== 爬虫类 ====================
class Spider(Spider):
    # 缓存实例 (类级别，共享)
    _play_cache = SimpleCache(max_size=50, ttl=600)  # 播放地址缓存10分钟

    # ==================== 初始化 ====================
    def init(self, extend=""):
        self.name = "追影_极速版"
        self.header = {
            "User-Agent": USER_AGENT,
            "Referer": BASE_URL + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def getName(self):
        return "追影_极速版"

    def isVideoFormat(self, url):
        return any(ext in url.lower() for ext in VIDEO_EXTS)

    # ==================== 安全的POST请求 ====================
    def _post(self, url, data, headers=None):
        """
        安全发送POST请求，兼容不同版本的 base.spider
        优先尝试 fetch 的 post_data 参数，失败则用 GET 方式回退
        """
        merged_headers = dict(self.header)
        if headers:
            merged_headers.update(headers)
        merged_headers["Content-Type"] = "application/x-www-form-urlencoded"

        # 方式1: 尝试 fetch 方法带 post_data 参数
        try:
            rsp = self.fetch(url, headers=merged_headers, post_data=data.encode())
            return rsp.text
        except TypeError:
            # fetch 不支持 post_data，尝试其他参数名
            pass
        except Exception:
            pass

        # 方式2: 尝试 data 参数
        try:
            rsp = self.fetch(url, headers=merged_headers, data=data.encode())
            return rsp.text
        except TypeError:
            pass
        except Exception:
            pass

        # 方式3: 尝试 params 参数 (POST)
        try:
            rsp = self.fetch(url, headers=merged_headers, params=data)
            return rsp.text
        except TypeError:
            pass
        except Exception:
            pass

        # 方式4: 全部失败，抛出异常让调用方处理
        raise Exception("无法发送POST请求")

    # ==================== 构建筛选URL ====================
    def _build_filter_url(self, category, type_name="", region="", year="", sort=""):
        params = [""] * 11
        params[0] = region if region and region != "全部" else ""
        params[1] = SORT_MAP.get(sort, "") if sort and sort != "综合排序" else ""
        params[2] = type_name if type_name and type_name != "全部" else ""
        params[10] = year if year and year != "全部" else ""

        url_path = "/vodshow/" + category + "-" + "-".join(params) + ".html"
        return BASE_URL + url_path

    # ==================== 解析视频列表 (通用卡片) ====================
    def _parse_video_cards(self, html):
        videos = []
        pattern = (
            r'<a[^>]*href="/video/([^"]+)\.html"[^>]*class="card js-card-item"[^>]*>'
            r'.*?<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*>'
            r'.*?<span[^>]*class="card-status"[^>]*>([^<]*)</span>'
            r'.*?<div[^>]*class="card-title"[^>]*>([^<]*)</div>'
        )
        items = re.findall(pattern, html, re.DOTALL)

        seen = set()
        for vid, pic, alt_title, status, title in items:
            if vid in seen:
                continue
            seen.add(vid)
            title = title.strip() if title.strip() else alt_title.strip()
            if not title:
                continue
            if pic and not pic.startswith('http'):
                pic = BASE_URL + pic
            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": status.strip() if status else "",
            })
        return videos

    # ==================== 解析搜索结果列表 ====================
    def _parse_search_results(self, html):
        videos = []
        pattern = (
            r'<div[^>]*class="search-list-card[^"]*"[^>]*>'
            r'.*?<a[^>]*href="/video/([^"]+)\.html"[^>]*title="([^"]*)"[^>]*>'
            r'.*?<img[^>]*src="([^"]*)"[^>]*>'
            r'.*?<span[^>]*class="list-thumb-remark"[^>]*>([^<]*)</span>'
        )
        items = re.findall(pattern, html, re.DOTALL)

        seen = set()
        for vid, title, pic, remark in items:
            if vid in seen:
                continue
            seen.add(vid)
            title = title.strip()
            if not title:
                continue
            if pic and not pic.startswith('http'):
                pic = BASE_URL + pic
            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark.strip() if remark else "",
            })
        return videos

    # ==================== 首页分类 ====================
    def homeContent(self, filter):
        result = {}
        classes = []
        for name, key in CATEGORY_MAP.items():
            classes.append({'type_name': name, 'type_id': key})
        result['class'] = classes

        if filter:
            result['filters'] = self._build_filters()

        return result

    # ==================== 构建筛选配置 ====================
    def _build_filters(self):
        filters = {}
        key_map = {"类型": "type", "地区": "area", "年份": "year", "排序": "sort"}
        for cat_key, cat_filters in FILTER_CONFIG.items():
            filter_list = []
            for filter_name, filter_values in cat_filters.items():
                key = key_map.get(filter_name, filter_name)
                values = [{"n": v, "v": v} for v in filter_values]
                filter_list.append({"key": key, "name": filter_name, "value": values})
            filters[cat_key] = filter_list
        return filters

    # ==================== 首页推荐 ====================
    def homeVideoContent(self):
        try:
            rsp = self.fetch(BASE_URL + "/", headers=self.header)
            vlist = self._parse_video_cards(rsp.text)
            return {'list': vlist[:30]}
        except Exception as e:
            print("首页获取出错:", e)
            return {'list': []}

    # ==================== 分类列表 (含二级筛选) ====================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            category = tid

            type_name = extend.get('type', '') if extend else ''
            region = extend.get('area', '') if extend else ''
            year = extend.get('year', '') if extend else ''
            sort = extend.get('sort', '') if extend else ''

            url = self._build_filter_url(category, type_name, region, year, sort)
            rsp = self.fetch(url, headers=self.header)
            vlist = self._parse_video_cards(rsp.text)

            total = len(vlist)
            pagecount = max(1, (total + 35) // 36) if total > 0 else 999

            return {
                'list': vlist,
                'page': pg,
                'pagecount': pagecount,
                'limit': len(vlist),
                'total': total
            }
        except Exception as e:
            print("分类获取出错:", e)
            return {'list': []}

    # ==================== 详情页 ====================
    def detailContent(self, array):
        try:
            vid = array[0]
            url = BASE_URL + '/video/' + vid + '.html'
            rsp = self.fetch(url, headers=self.header)
            html = rsp.text

            # --- 标题 ---
            title = ""
            title_match = re.search(
                r'<h1[^>]*class="[^"]*detail-title[^"]*"[^>]*>(.*?)</h1>',
                html, re.DOTALL
            )
            if title_match:
                title = _strip_html(title_match.group(1))
            if not title:
                title_match = re.search(r'<title>([^<]+)</title>', html)
                if title_match:
                    title = title_match.group(1).strip().split('-')[0].strip()

            # --- 封面图 ---
            pic = ""
            pic_match = re.search(
                r'<img[^>]*class="[^"]*detail-cover[^"]*"[^>]*src="([^"]*)"', html
            )
            if not pic_match:
                pic_match = re.search(
                    r'class="detail-hero-bg"[^>]*style="[^"]*url\(([^)]+)\)', html
                )
            if pic_match:
                pic = pic_match.group(1).strip()
                if pic and not pic.startswith('http'):
                    pic = BASE_URL + pic

            # --- 年份 ---
            year = ""
            year_match = re.search(r'class="[^"]*detail-year[^"]*"[^>]*>([^<]+)<', html)
            if year_match:
                year = year_match.group(1).strip().strip('()')

            # --- 地区 / 类型 ---
            area = ""
            vod_type = ""
            matrix_items = re.findall(
                r'class="matrix-item[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL
            )
            for item in matrix_items:
                text = _strip_html(item)
                if text and '类型' not in text and '国家' not in text and '地区' not in text:
                    if not vod_type and text in ['电影', '电视剧', '动漫', '综艺', '短剧']:
                        vod_type = text
                    elif not area and len(text) <= 10:
                        area = text

            # --- 简介 ---
            desc = ""
            desc_idx = html.find('剧情简介')
            if desc_idx > 0:
                desc_chunk = html[desc_idx:desc_idx + 2000]
                desc_match = re.search(
                    r'剧情简介.*?<[^>]+>\s*(.*?)\s*</', desc_chunk, re.DOTALL
                )
                if desc_match:
                    desc = _strip_html(desc_match.group(1))
            if not desc:
                desc_match = re.search(
                    r'<meta[^>]*name="description"[^>]*content="([^"]*)"',
                    html, re.IGNORECASE
                )
                if desc_match:
                    desc = desc_match.group(1).strip()

            # --- 播放线路和剧集 ---
            play_from = []
            play_url = []

            # 提取线路名称
            source_tabs = re.findall(
                r'<div[^>]*class="source-tab[^"]*"[^>]*data-target="([^"]*)"[^>]*>'
                r'.*?<span[^>]*class="tab-name"[^>]*>([^<]+)</span>',
                html, re.DOTALL
            )

            for target_id, tab_name in source_tabs:
                tab_name = tab_name.strip()
                # 找对应的剧集列表
                ep_match = re.search(
                    rf'<div[^>]*class="ep-square-list"[^>]*id="{re.escape(target_id)}"[^>]*>(.*?)</div>',
                    html, re.DOTALL
                )
                if not ep_match:
                    ep_match = re.search(
                        rf'id="{re.escape(target_id)}"[^>]*>(.*?)</div>',
                        html, re.DOTALL
                    )

                if ep_match:
                    ep_html = ep_match.group(1)
                    # 优先用 data-name 属性
                    ep_items = re.findall(
                        r'<a[^>]*href="(/play/[^"]+\.html)"[^>]*'
                        r'(?:class="ep-item-square"[^>]*)?'
                        r'data-name="([^"]*)"[^>]*>',
                        ep_html, re.DOTALL
                    )
                    if not ep_items:
                        # 备用：从链接文本提取
                        ep_items = re.findall(
                            r'<a[^>]*href="(/play/[^"]+\.html)"[^>]*>([^<]+)</a>',
                            ep_html, re.DOTALL
                        )

                    eps = []
                    seen_eps = set()
                    for ep_href, ep_name in ep_items:
                        ep_clean = _strip_html(ep_name)
                        if not ep_clean or '全集' in ep_clean or '播放' in ep_clean:
                            continue
                        if ep_href in seen_eps:
                            continue
                        seen_eps.add(ep_href)
                        eps.append(ep_clean + '$' + ep_href)

                    if eps:
                        play_from.append(tab_name)
                        play_url.append('#'.join(eps))

            # 备用：通用匹配
            if not play_from:
                all_links = re.findall(
                    r'<a[^>]*href="(/play/[^"]+\.html)"[^>]*>([^<]+)</a>', html
                )
                if all_links:
                    eps = []
                    seen_eps = set()
                    for href, ep_name in all_links:
                        ep_clean = _strip_html(ep_name)
                        if not ep_clean or '全集' in ep_clean or '播放' in ep_clean:
                            continue
                        if href in seen_eps:
                            continue
                        seen_eps.add(href)
                        eps.append(ep_clean + '$' + href)
                    if eps:
                        play_from.append("默认线路")
                        play_url.append('#'.join(eps))

            if not play_from:
                play_from = ["默认线路"]
                play_url = [""]

            vod = {
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_year": year,
                "vod_area": area,
                "vod_content": desc,
                "vod_play_from": '$$$'.join(play_from),
                "vod_play_url": '$$$'.join(play_url)
            }
            return {'list': [vod]}
        except Exception as e:
            print("详情解析出错:", e)
            return {'list': []}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        try:
            url = BASE_URL + '/index.php/vod/search/wd/' + quote(key) + '.html'
            rsp = self.fetch(url, headers=self.header)
            html = rsp.text

            videos = self._parse_search_results(html)

            # 备用：如果搜索页结构变了，用通用卡片解析
            if not videos:
                videos = self._parse_video_cards(html)

            # 最后备用：宽松匹配
            if not videos:
                loose_pattern = r'<a[^>]*href="/video/([^"]+)\.html"[^>]*title="([^"]*)"[^>]*>'
                items = re.findall(loose_pattern, html, re.DOTALL)
                seen = set()
                for vid, title in items:
                    if vid in seen:
                        continue
                    seen.add(vid)
                    videos.append({
                        "vod_id": vid,
                        "vod_name": title.strip(),
                        "vod_pic": "",
                        "vod_remarks": ""
                    })

            return {'list': videos}
        except Exception as e:
            print("搜索出错:", e)
            return {'list': []}

    # ==================== 播放解析 (核心加速) ====================
    def playerContent(self, flag, id, vipFlags):
        play_url = ""
        try:
            # 如果已经是直链，直接返回
            if id.startswith('http') and any(
                ext in id.lower() for ext in VIDEO_EXTS
            ):
                return {"parse": 0, "url": id}

            # 构造播放页URL
            if id.startswith('/'):
                play_url = BASE_URL + id
            elif id.startswith('http'):
                play_url = id
            else:
                play_url = BASE_URL + '/play/' + id + '.html'

            # 检查缓存
            cached = self._play_cache.get(play_url)
            if cached:
                return {"parse": 0, "url": cached}

            # 获取播放页提取 MAC_PLAY_CONFIG
            rsp = self.fetch(play_url, headers=self.header)
            html = rsp.text

            # 提取 MAC_PLAY_CONFIG
            config_match = re.search(
                r'MAC_PLAY_CONFIG\s*=\s*(\{.*?\});', html, re.DOTALL
            )
            if not config_match:
                # 没找到配置，回退到 web 解析模式
                return {"parse": 1, "url": play_url}

            config_str = config_match.group(1)
            baseKey = self._extract_js_str(config_str, 'baseKey')
            requestUrl = self._extract_js_str(config_str, 'requestUrl')

            if not baseKey or not requestUrl:
                return {"parse": 1, "url": play_url}

            # 调用 player_api 解密获取直链
            video_url = self._decrypt_player_api(baseKey, requestUrl, play_url)
            if video_url and video_url.startswith('http'):
                self._play_cache.set(play_url, video_url)
                return {"parse": 0, "url": video_url}

            # 直连解析失败，回退到 web 解析
            return {"parse": 1, "url": play_url}

        except Exception as e:
            print("播放解析出错:", e)
            # 任何异常都回退到 web 解析模式，避免闪退
            if play_url:
                return {"parse": 1, "url": play_url}
            return {"parse": 1, "url": id}

    # ==================== 提取JS字符串 ====================
    def _extract_js_str(self, js_obj, key):
        pattern = rf'{key}\s*:\s*["\']([^"\']+)["\']'
        match = re.search(pattern, js_obj)
        return match.group(1) if match else ""

    # ==================== 解密播放API ====================
    def _decrypt_player_api(self, baseKey, requestUrl, referer):
        """调用player_api.php并解密获取真实视频地址"""
        try:
            timestamp = str(int(time.time()))
            token = hashlib.md5(
                (baseKey + timestamp + USER_AGENT).encode()
            ).hexdigest()

            api_url = BASE_URL + '/player_api.php'
            post_data = f"url={quote(requestUrl)}&timestamp={timestamp}&token={token}"

            headers = {
                "User-Agent": USER_AGENT,
                "Referer": referer,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            }

            # 发送 POST 请求
            resp_text = self._post(api_url, post_data, headers)
            result = json.loads(resp_text)

            if 'error' in result or 'data' not in result:
                return None

            # 解密: 字符串反转 -> base64解码 -> UTF-8解码 -> JSON解析
            encrypted = result['data']
            reversed_str = encrypted[::-1]
            decoded_bytes = base64.b64decode(reversed_str)
            try:
                decoded_str = decoded_bytes.decode('utf-8')
            except (UnicodeDecodeError, Exception):
                decoded_str = decoded_bytes.decode('latin1')
                decoded_str = decoded_str.encode('latin1').decode('utf-8', errors='replace')

            video_data = json.loads(decoded_str)
            jmurl = video_data.get('jmurl', '')

            return jmurl if jmurl and jmurl.startswith('http') else None

        except Exception as e:
            print("播放API解密出错:", e)
            return None

    # ==================== 筛选配置 ====================
    config = {
        "player": {},
        "filter": {}
    }

    def _init_config_filters(self):
        if not self.config.get('filter'):
            self.config['filter'] = self._build_filters()


# ==================== TVBox 标准入口 ====================
def get_spider():
    spider = Spider()
    spider._init_config_filters()
    return spider

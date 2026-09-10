# -*- coding: utf-8 -*-
# ============================================================
# 适配 https://u1v2w3x4.misszh5.cc 的 TVBox 爬虫脚本
# 网站：Miss中文站
# 功能：首页 / 分类 / 详情 / 播放 / 搜索 / 筛选
# ============================================================

import re
import json
import html
import urllib.request
import urllib.parse
import ssl
from urllib.parse import urljoin, quote, unquote

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def homeContent(self, filter): pass
        def homeVideoContent(self): pass
        def categoryContent(self, tid, pg, filter, extend): pass
        def detailContent(self, ids): pass
        def playerContent(self, flag, id, vipFlags=None): pass
        def searchContent(self, key, quick, pg='1'): pass
        def isVideoFormat(self, url): pass
        def manualVideoCheck(self): pass
        def localProxy(self, param): pass


def clean_text(text):
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def fix_url(url, host):
    if not url:
        return ""
    url = url.strip()
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/'):
        return urljoin(host, url)
    if url.startswith(('http://', 'https://')):
        return url
    return urljoin(host, '/' + url)


class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.host = "https://u1v2w3x4.misszh5.cc"
        self.name = "misszh_tvbox"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def init(self, extend=""):
        if extend and extend.startswith("http"):
            self.host = extend.rstrip("/")

    def getName(self):
        return self.name

    def isVideoFormat(self, url):
        return any(x in url for x in [".m3u8", ".mp4", ".flv", ".ts"])

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [200, "video/MP2T", b"", {}]

    def _fetch(self, url, referer=None):
        if not url.startswith(('http://', 'https://')):
            url = urljoin(self.host, url)

        try:
            headers = {"User-Agent": self.user_agent}
            if referer:
                headers["Referer"] = referer

            req = urllib.request.Request(url, headers=headers)
            r = urllib.request.urlopen(req, timeout=15)
            return r.read().decode('utf-8')
        except Exception as e:
            print(f"[{self.name}] 请求失败: {e}")
            return ""

    # ============================================================
    # 解析视频列表
    # ============================================================

    def _parse_video_items(self, html_text):
        if not html_text:
            return []

        videos = []

        block_match = re.search(r'<div[^>]*class="[^"]*vodindex[^"]*"[^>]*>(.*?)</div>', html_text, re.DOTALL)
        
        if not block_match:
            block_content = html_text
        else:
            block_content = block_match.group(1)

        pattern = r'<dl>.*?<a[^>]*href="([^"]+)"[^>]*>.*?<img[^>]*data-original="([^"]*)"[^>]*>.*?<h3>(.*?)</h3>'
        matches = re.findall(pattern, block_content, re.DOTALL)

        print(f"[{self.name}] 匹配到 {len(matches)} 个视频项")

        for href, pic, title in matches:
            try:
                vid_match = re.search(r'/voddetail/(\d+)\.html', href)
                if not vid_match:
                    continue

                vid = vid_match.group(1)
                title = clean_text(title)
                pic = fix_url(pic, self.host)

                videos.append({
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": ""
                })
            except Exception as e:
                print(f"解析单个视频失败: {e}")
                continue

        return videos

    # ============================================================
    # 首页分类 + 筛选器
    # ============================================================

    def homeContent(self, filter):
        return {
            "class": [
                {"type_id": "1", "type_name": "国产传媒"},
                {"type_id": "2", "type_name": "国产剧情"},
                {"type_id": "58", "type_name": "网曝黑料"},
                {"type_id": "3", "type_name": "特色仓库"},
                {"type_id": "69", "type_name": "精品资源"},
                {"type_id": "78", "type_name": "热播片库"},
            ],
            "filters": {
                # 国产传媒 (tid=1)
                "1": [
                    {
                        "key": "sub",
                        "name": "子分类",
                        "value": [
                            {"n": "全部", "v": ""},
                            {"n": "麻豆视频", "v": "6"},
                            {"n": "91制片厂", "v": "7"},
                            {"n": "天美传媒", "v": "8"},
                            {"n": "蜜桃传媒", "v": "9"},
                            {"n": "皇家华人", "v": "10"},
                            {"n": "星空传媒", "v": "11"},
                            {"n": "精东影业", "v": "12"},
                            {"n": "乐播传媒", "v": "20"},
                        ]
                    },
                    {
                        "key": "by",
                        "name": "排序",
                        "value": [
                            {"n": "时间", "v": "time"},
                            {"n": "人气", "v": "hits"},
                            {"n": "评分", "v": "score"},
                        ]
                    }
                ],
                # 国产剧情 (tid=2)
                "2": [
                    {
                        "key": "sub",
                        "name": "子分类",
                        "value": [
                            {"n": "全部", "v": ""},
                            {"n": "兔子先生", "v": "57"},
                            {"n": "杏吧原创", "v": "21"},
                            {"n": "糖心Vlog", "v": "22"},
                            {"n": "玩偶姐姐", "v": "24"},
                            {"n": "mini传媒", "v": "25"},
                            {"n": "大象传媒", "v": "26"},
                            {"n": "成人头条", "v": "30"},
                            {"n": "乌鸦传媒", "v": "31"},
                        ]
                    },
                    {
                        "key": "by",
                        "name": "排序",
                        "value": [
                            {"n": "时间", "v": "time"},
                            {"n": "人气", "v": "hits"},
                            {"n": "评分", "v": "score"},
                        ]
                    }
                ],
                # 网曝黑料 (tid=58)
                "58": [
                    {
                        "key": "sub",
                        "name": "子分类",
                        "value": [
                            {"n": "全部", "v": ""},
                            {"n": "国产精品", "v": "60"},
                            {"n": "华语AV", "v": "61"},
                            {"n": "黑料吃瓜", "v": "62"},
                            {"n": "学生合集", "v": "63"},
                            {"n": "乱伦精品", "v": "64"},
                            {"n": "探花约炮", "v": "65"},
                            {"n": "日本无码", "v": "66"},
                            {"n": "主播网红", "v": "67"},
                        ]
                    },
                    {
                        "key": "by",
                        "name": "排序",
                        "value": [
                            {"n": "时间", "v": "time"},
                            {"n": "人气", "v": "hits"},
                            {"n": "评分", "v": "score"},
                        ]
                    }
                ],
                # 特色仓库 (tid=3)
                "3": [
                    {
                        "key": "sub",
                        "name": "子分类",
                        "value": [
                            {"n": "全部", "v": ""},
                            {"n": "国产自拍", "v": "37"},
                            {"n": "强奸乱伦", "v": "32"},
                            {"n": "女优明星", "v": "33"},
                            {"n": "欧美激情", "v": "34"},
                            {"n": "重口激情", "v": "28"},
                            {"n": "三级伦理", "v": "29"},
                            {"n": "剧情动漫", "v": "35"},
                            {"n": "SM调教", "v": "15"},
                        ]
                    },
                    {
                        "key": "by",
                        "name": "排序",
                        "value": [
                            {"n": "时间", "v": "time"},
                            {"n": "人气", "v": "hits"},
                            {"n": "评分", "v": "score"},
                        ]
                    }
                ],
                # 精品资源 (tid=69)
                "69": [
                    {
                        "key": "sub",
                        "name": "子分类",
                        "value": [
                            {"n": "全部", "v": ""},
                            {"n": "女同性恋", "v": "70"},
                            {"n": "日韩无码", "v": "71"},
                            {"n": "网曝吃瓜", "v": "72"},
                            {"n": "探花约炮", "v": "73"},
                            {"n": "偷拍偷窥", "v": "74"},
                            {"n": "日韩主播", "v": "75"},
                            {"n": "中文字幕", "v": "76"},
                            {"n": "主播诱惑", "v": "77"},
                        ]
                    },
                    {
                        "key": "by",
                        "name": "排序",
                        "value": [
                            {"n": "时间", "v": "time"},
                            {"n": "人气", "v": "hits"},
                            {"n": "评分", "v": "score"},
                        ]
                    }
                ],
                # 热播片库 (tid=78)
                "78": [
                    {
                        "key": "sub",
                        "name": "子分类",
                        "value": [
                            {"n": "全部", "v": ""},
                            {"n": "传媒剧情", "v": "79"},
                            {"n": "抖阴短片", "v": "80"},
                            {"n": "AV解说", "v": "81"},
                            {"n": "换脸明星", "v": "82"},
                            {"n": "VR视角", "v": "83"},
                        ]
                    },
                    {
                        "key": "by",
                        "name": "排序",
                        "value": [
                            {"n": "时间", "v": "time"},
                            {"n": "人气", "v": "hits"},
                            {"n": "评分", "v": "score"},
                        ]
                    }
                ],
            }
        }

    # ============================================================
    # 首页视频列表
    # ============================================================

    def homeVideoContent(self):
        result = {"list": [], "page": 1, "pagecount": 1, "limit": 24, "total": 0}
        html_text = self._fetch("/topic/")
        if not html_text:
            html_text = self._fetch("/")
        if html_text:
            result["list"] = self._parse_video_items(html_text)
            result["total"] = len(result["list"])
        return result

    # ============================================================
    # 分类页视频列表（支持筛选）
    # ============================================================

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": int(pg), "pagecount": 1, "limit": 24, "total": 0}

        # 处理筛选参数
        sub = extend.get('sub', '') if extend else ''
        by = extend.get('by', '') if extend else ''

        # 构建URL
        if sub:
            # 选择了子分类
            if int(pg) <= 1:
                url = f"/vodtype/{sub}.html"
            else:
                url = f"/vodtype/{sub}-{pg}.html"
        else:
            # 主分类
            if int(pg) <= 1:
                url = f"/vodtype/{tid}.html"
            else:
                url = f"/vodtype/{tid}-{pg}.html"

        # 如果有排序参数，拼接到URL
        if by:
            # 分类页的排序是通过 URL 参数传递的
            if '?' in url:
                url += f"&by={by}"
            else:
                url += f"?by={by}"

        print(f"[{self.name}] 请求分类页: {url}")

        html_text = self._fetch(url)
        if not html_text:
            return result

        videos = self._parse_video_items(html_text)
        result["list"] = videos

        # 提取总页数
        page_links = re.findall(r'/vodtype/\d+-(\d+)\.html', html_text)
        if page_links:
            result["pagecount"] = max([int(p) for p in page_links])
        else:
            total_match = re.search(r'(\d+)/(\d+)</a>', html_text)
            if total_match:
                result["pagecount"] = int(total_match.group(2))

        result["total"] = len(videos)
        return result

    # ============================================================
    # 视频详情页
    # ============================================================

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        result = {"list": []}

        detail_url = f"/voddetail/{vid}.html"
        html_text = self._fetch(detail_url)

        title = f"视频 {vid}"

        if html_text:
            title_match = re.search(r'<h3>(.*?)</h3>', html_text)
            if title_match:
                title = clean_text(title_match.group(1))

        play_url = f"/vodplay/{vid}-1-1.html"

        result["list"].append({
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": "",
            "vod_play_from": "默认线路",
            "vod_play_url": f"播放${play_url}"
        })

        return result

    # ============================================================
    # 播放页解析
    # ============================================================

    def playerContent(self, flag, id, vipFlags=None):
        result = {"parse": 0, "playUrl": "", "url": "", "header": ""}

        if self.isVideoFormat(id):
            result["url"] = id
            return result

        if not id.startswith('http'):
            id = urljoin(self.host, id)

        print(f"[{self.name}] 请求播放页: {id}")

        html_text = self._fetch(id)
        if not html_text:
            result["url"] = id
            return result

        # 从 play_main 中提取播放地址
        play_main_match = re.search(r'<div[^>]*class="[^"]*play_main[^"]*"[^>]*>(.*?)</div>', html_text, re.DOTALL)

        if play_main_match:
            play_main_content = play_main_match.group(1)
            script_match = re.search(r'<script[^>]*>(.*?)</script>', play_main_content, re.DOTALL)
            if script_match:
                script_content = script_match.group(1)
                url_match = re.search(r'"url"\s*:\s*"([^"]+)"', script_content)
                if url_match:
                    play_url = url_match.group(1)
                    if '%' in play_url:
                        play_url = unquote(play_url)
                    if self.isVideoFormat(play_url):
                        result["url"] = play_url
                        result["header"] = json.dumps({
                            "Referer": self.host + "/",
                            "User-Agent": self.user_agent
                        })
                        print(f"[{self.name}] 提取到播放地址: {play_url}")
                        return result

        # 备用：直接匹配 m3u8
        m3u8_match = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html_text)
        if m3u8_match:
            play_url = m3u8_match.group(1)
            result["url"] = play_url
            result["header"] = json.dumps({
                "Referer": self.host + "/",
                "User-Agent": self.user_agent
            })
            return result

        result["url"] = id
        return result

    # ============================================================
    # 搜索功能
    # ============================================================

    def searchContent(self, key, quick, pg="1"):
        result = {"list": [], "page": int(pg), "pagecount": 1, "limit": 24, "total": 0}

        search_url = f"/vodsearch/-------------.html?wd={quote(key)}"
        if int(pg) > 1:
            search_url += f"&page={pg}"

        html_text = self._fetch(search_url)
        if html_text:
            videos = self._parse_video_items(html_text)
            result["list"] = videos
            result["total"] = len(videos)

            page_links = re.findall(r'page=(\d+)', html_text)
            if page_links:
                result["pagecount"] = max([int(p) for p in page_links])

        return result
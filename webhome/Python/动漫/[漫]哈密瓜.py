# -*- coding: utf-8 -*-
"""
哈密瓜动漫 (hmgdm.com) 爬虫 - 增强版（修复“大家在看”无数据）
- 修复 watched 分类数据接口路径
- 分类列表每页最多 40 条（如果 API 支持）
- 首页推荐每类取 15 条，总上限 80 条
- 剧集从第 1 集开始排序
- 适配 TVBox / 影视仓
"""

import re
import json
import logging
import urllib.parse
import os
import sys
import time
import requests
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    BaseSpider = object

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Spider(BaseSpider):
    """哈密瓜动漫爬虫 - 增强版（修复 watched）"""

    BASE_URL = "https://hmgdm.com"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 12; SM-S908U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://hmgdm.com/",
        "Connection": "keep-alive",
    }

    # 分类映射
    CATEGORY_MAP = {
        "watched": {"name": "大家在看", "type": "watched"},
        "rhdm":    {"name": "日本动漫", "type": "rhdm"},
        "gcdm":    {"name": "国产动漫", "type": "gcdm"},
        "omdm":    {"name": "欧美动漫", "type": "omdm"},
        "dmdy":    {"name": "动漫电影", "type": "dmdy"},
        "dtmh":    {"name": "动态漫画", "type": "dtmh"},
    }

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.session.verify = False
        self._cache = {}
        self._cache_ttl = 300

    def init(self, extend=""):
        pass

    def getName(self):
        return "哈密瓜动漫"

    def _get_json(self, url, params=None):
        """请求 JSON 接口"""
        try:
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"JSON请求失败: {resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"JSON请求异常: {e}")
            return None

    def _get_html(self, url, params=None):
        """请求 HTML 页面（备用）"""
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.encoding = "utf-8"
            return resp.text
        except Exception as e:
            logger.error(f"HTML请求失败: {e}")
            return None

    def _fix_pic(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.BASE_URL + url
        if not url.startswith("http"):
            return self.BASE_URL + "/" + url
        return url

    def _parse_api_item(self, item):
        vod_id = str(item.get("id", ""))
        if not vod_id:
            return None
        return {
            "vod_id": vod_id,
            "vod_name": item.get("name", ""),
            "vod_pic": self._fix_pic(item.get("pic", "")),
            "vod_remarks": item.get("remarks", "连载中"),
        }

    # ==================== 首页 ====================
    def homeContent(self, filter=False):
        result = {"class": [], "list": [], "filters": {}}

        # 分类列表
        classes = []
        for cid, cinfo in self.CATEGORY_MAP.items():
            classes.append({
                "type_id": cid,
                "type_name": cinfo["name"],
            })
        result["class"] = classes

        # 首页推荐：从多个分类各取更多条目（每类15条），总上限80条
        all_items = []
        # 优先从“动漫电影”和“日本动漫”获取
        for cid in ["dmdy", "rhdm", "gcdm", "omdm"]:
            data = self._get_json(f"{self.BASE_URL}/data/type/{cid}", params={"page": 1})
            if data and isinstance(data, list):
                for item in data[:15]:
                    parsed = self._parse_api_item(item)
                    if parsed and parsed["vod_name"]:
                        if not any(x["vod_name"] == parsed["vod_name"] for x in all_items):
                            all_items.append(parsed)
                if len(all_items) >= 80:
                    break

        result["list"] = all_items[:80]
        return result

    def homeVideoContent(self):
        return self.homeContent()

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if pg else 1
            type_id = str(tid)

            if type_id not in self.CATEGORY_MAP:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

            # 针对不同的分类使用不同的 API 路径
            if type_id == "watched":
                # “大家在看” 使用 /data/watched
                url = f"{self.BASE_URL}/data/watched"
            else:
                # 其他分类使用 /data/type/{type_id}
                url = f"{self.BASE_URL}/data/type/{type_id}"

            params = {"page": page, "limit": 40}  # 尝试每页40条

            data = self._get_json(url, params=params)

            if not data or not isinstance(data, list):
                # 如果 API 失败，降级到 HTML 解析（只支持第一页）
                if page == 1:
                    html_url = f"{self.BASE_URL}/type/{type_id}" if type_id != "watched" else f"{self.BASE_URL}/watched"
                    html = self._get_html(html_url)
                    if html:
                        videos = self._parse_video_list_html(html)
                        return {
                            "list": videos,
                            "page": page,
                            "pagecount": 1,
                            "limit": len(videos),
                            "total": len(videos),
                        }
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

            # 解析 JSON 数据
            videos = []
            for item in data:
                parsed = self._parse_api_item(item)
                if parsed:
                    videos.append(parsed)

            pagecount = page + 1 if videos else page
            actual_limit = len(videos) if videos else 20

            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": actual_limit,
                "total": len(videos) * pagecount,
            }
        except Exception as e:
            logger.error(f"获取分类内容失败: {e}")
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}

    def _parse_video_list_html(self, html):
        """从 HTML 解析视频列表（备用）"""
        videos = []
        soup = BeautifulSoup(html, 'html.parser')
        video_links = soup.find_all('a', class_='video')
        for link in video_links:
            href = link.get('href', '')
            vid_match = re.search(r'/details/(\d+)', href)
            if not vid_match:
                continue
            vid = vid_match.group(1)
            title = ''
            title_div = link.find('div', class_='title')
            if title_div:
                p_tag = title_div.find('p')
                if p_tag:
                    title = p_tag.get_text(strip=True)
            pic = ''
            img_box = link.find('div', class_='img-box')
            if img_box:
                pic = img_box.get('data', '')
                if not pic:
                    style = img_box.get('style', '')
                    bg_match = re.search(r'background-image:\s*url\(([^)]+)\)', style)
                    if bg_match:
                        pic = bg_match.group(1).strip()
                        pic = pic.strip('"\'')
                if pic:
                    pic = self._fix_pic(pic)
            remarks = ''
            desc_div = link.find('div', class_='desc')
            if desc_div:
                desc_p = desc_div.find_all('div')
                if len(desc_p) >= 2:
                    remarks = desc_p[1].get_text(strip=True)
            if title:
                videos.append({
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks or "连载中",
                })
        return videos

    # ==================== 详情 ====================
    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            url = f"{self.BASE_URL}/details/{vod_id}"
            html = self._get_html(url)
            if not html:
                return {"list": []}

            soup = BeautifulSoup(html, 'html.parser')

            title = ''
            title_tag = soup.find('h1')
            if title_tag:
                title = title_tag.get_text(strip=True)

            poster = ''
            img_box = soup.find('div', class_='img-box')
            if img_box:
                poster = img_box.get('data', '')
                if not poster:
                    style = img_box.get('style', '')
                    bg_match = re.search(r'background-image:\s*url\(([^)]+)\)', style)
                    if bg_match:
                        poster = bg_match.group(1).strip()
                        poster = poster.strip('"\'')
                poster = self._fix_pic(poster)

            content = ''
            desc_div = soup.find('div', class_='player-desc')
            if desc_div:
                content = desc_div.get_text(strip=True)

            play_from_list, play_url_list = self._parse_episodes(html, vod_id)

            vod_item = {
                "vod_id": vod_id,
                "vod_name": title or f"动漫{vod_id}",
                "vod_pic": poster,
                "type_name": "动漫",
                "vod_year": "",
                "vod_area": "",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": content or "暂无简介",
                "vod_play_from": "$$$".join(play_from_list) if play_from_list else "默认线路",
                "vod_play_url": "$$$".join(play_url_list) if play_url_list else "",
            }

            return {"list": [vod_item]}
        except Exception as e:
            logger.error(f"获取详情失败: {e}")
            return {"list": []}

    def _parse_episodes(self, html, vod_id):
        play_from_list = []
        play_url_list = []

        # 方法1: 解析 episodesData
        pattern = r'const\s+episodesData\s*=\s*({[^;]+});'
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                json_str = match.group(1)
                json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
                json_str = re.sub(r'(\w+):', r'"\1":', json_str)
                json_str = re.sub(r',\s*}', '}', json_str)
                json_str = re.sub(r',\s*]', ']', json_str)
                episodes_data = json.loads(json_str)

                for line_name, episodes in episodes_data.items():
                    if not episodes:
                        continue
                    urls = []
                    for ep in episodes:
                        path = ep.get('path', '')
                        name = ep.get('name', '')
                        if path:
                            full_url = self.BASE_URL + path
                            urls.append(f"{name}${full_url}")
                    if urls:
                        urls.sort(key=lambda x: self._extract_episode_num(x))
                        play_from_list.append(line_name)
                        play_url_list.append("#".join(urls))
            except Exception as e:
                logger.error(f"解析episodesData失败: {e}")

        # 方法2: DOM 提取
        if not play_from_list:
            soup = BeautifulSoup(html, 'html.parser')
            playlist_div = soup.find('div', id='playlist')
            if playlist_div:
                links = playlist_div.find_all('a')
                if links:
                    urls = []
                    for link in links:
                        href = link.get('href', '')
                        text = link.get_text(strip=True)
                        if href and text:
                            full_url = self.BASE_URL + href if href.startswith('/') else href
                            urls.append(f"{text}${full_url}")
                    if urls:
                        urls.sort(key=lambda x: self._extract_episode_num(x))
                        play_from_list.append("默认线路")
                        play_url_list.append("#".join(urls))

        # 方法3: 正则提取
        if not play_from_list:
            pattern = r'href=["\'](/player/' + vod_id + r'/\d+)["\'][^>]*>([^<]+)</a>'
            matches = re.findall(pattern, html)
            if matches:
                urls = []
                seen = set()
                for path, name in matches:
                    if path not in seen:
                        seen.add(path)
                        full_url = self.BASE_URL + path
                        urls.append(f"{name}${full_url}")
                if urls:
                    urls.sort(key=lambda x: self._extract_episode_num(x))
                    play_from_list.append("默认线路")
                    play_url_list.append("#".join(urls))

        return play_from_list, play_url_list

    def _extract_episode_num(self, url_str):
        match = re.search(r'第(\d+)集', url_str)
        if match:
            return int(match.group(1))
        match = re.search(r'/(\d+)\$', url_str)
        if match:
            return int(match.group(1))
        match = re.search(r'^(\d+)\$', url_str)
        if match:
            return int(match.group(1))
        return 0

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags):
        try:
            play_url = urllib.parse.unquote(id) if id else ''

            if '/player/' in play_url or '/play/' in play_url:
                resp = self.session.get(play_url, timeout=15)
                if resp and resp.status_code == 200:
                    html = resp.text

                    pattern = r'initDplayer\s*\(\s*["\']([^"\']+\.m3u8[^"\']*)["\']'
                    match = re.search(pattern, html)
                    if match:
                        video_url = match.group(1)
                        return {
                            "parse": 0,
                            "playUrl": "",
                            "url": video_url,
                            "header": json.dumps({
                                "User-Agent": self.HEADERS["User-Agent"],
                                "Referer": self.BASE_URL + "/",
                            }),
                        }

                    m3u8_match = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
                    if m3u8_match:
                        return {
                            "parse": 0,
                            "playUrl": "",
                            "url": m3u8_match.group(1),
                            "header": json.dumps({
                                "User-Agent": self.HEADERS["User-Agent"],
                                "Referer": self.BASE_URL + "/",
                            }),
                        }

                    iframe_match = re.search(r'<iframe[^>]*src=["\']([^"\']+)["\']', html)
                    if iframe_match:
                        iframe_url = iframe_match.group(1)
                        if iframe_url.startswith('//'):
                            iframe_url = 'https:' + iframe_url
                        return {
                            "parse": 1,
                            "playUrl": "",
                            "url": iframe_url,
                            "header": json.dumps({
                                "User-Agent": self.HEADERS["User-Agent"],
                                "Referer": self.BASE_URL + "/",
                            }),
                        }

            return {
                "parse": 0,
                "playUrl": "",
                "url": play_url,
                "header": json.dumps({
                    "User-Agent": self.HEADERS["User-Agent"],
                    "Referer": self.BASE_URL + "/",
                }),
            }
        except Exception as e:
            logger.error(f"解析播放失败: {e}")
            return {"parse": 0, "playUrl": "", "url": ""}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
            encoded_key = urllib.parse.quote(key)

            url = f"{self.BASE_URL}/data/search"
            data = self._get_json(url, params={"kw": key, "page": page})

            if data and isinstance(data, list):
                videos = []
                for item in data:
                    parsed = self._parse_api_item(item)
                    if parsed:
                        videos.append(parsed)
                return {
                    "list": videos,
                    "page": page,
                    "pagecount": 1,
                    "limit": len(videos),
                    "total": len(videos),
                }

            # 降级到 HTML
            html_url = f"{self.BASE_URL}/search?kw={encoded_key}&page={page}"
            html = self._get_html(html_url)
            if html:
                videos = self._parse_video_list_html(html)
                return {
                    "list": videos,
                    "page": page,
                    "pagecount": 1,
                    "limit": len(videos),
                    "total": len(videos),
                }
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}

    def isVideoFormat(self, url):
        video_formats = ['.m3u8', '.mp4', '.ts', '.flv', '.avi', '.mkv']
        return any(url.lower().endswith(fmt) for fmt in video_formats)

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, params):
        pass


if __name__ == "__main__":
    spider = Spider()
    print("测试“大家在看”分类:")
    watched = spider.categoryContent("watched", 1, {}, {})
    print(f"获取到 {len(watched.get('list', []))} 条数据")
    for item in watched['list'][:5]:
        print(f"  - {item['vod_name']} ({item['vod_remarks']})")
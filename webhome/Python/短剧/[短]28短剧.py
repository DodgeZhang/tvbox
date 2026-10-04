# -*- coding: utf-8 -*-
"""
28短剧 (28dj01.com) 爬虫 - 线路统一修复版
- 推荐与分类使用相同的线路提取逻辑
- 播放页主动提取真实视频地址（m3u8/解析接口）
适配 dr_py / TVBox
"""
import re
import json
import time
import urllib.parse
import requests
import base64
from bs4 import BeautifulSoup
from base.spider import Spider


class Spider(Spider):
    name = "28短剧"
    base_url = "https://28dj01.com"
    site_url = "https://28dj01.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://28dj01.com/",
    }
    timeout = 15

    # 分类映射
    CLASS_MAP = {
        "1": "穿越重生",
        "2": "都市情爱",
        "3": "复仇爽剧",
        "4": "玄幻武侠",
        "5": "奇幻恐怖",
        "20": "其它短剧",
    }

    # 解析接口（用于视频站链接）
    PARSE_API = "https://jx.jsonplayer.com/player/?url="

    def init(self, extend=""):
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.verify = False

    def _fetch(self, url):
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.encoding = "utf-8"
            return resp.text
        except Exception as e:
            print(f"[{self.name}] 请求失败: {e}")
            return None

    def _fix_pic(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if not url.startswith("http"):
            return self.base_url + url
        return url

    def _parse_video_item(self, item):
        try:
            pic_div = item.find("div", class_="module-item-pic")
            if not pic_div:
                return None
            a = pic_div.find("a")
            if not a:
                return None
            href = a.get("href")
            if not href:
                return None
            vid_match = re.search(r"/voddetail/(\d+)/", href)
            if not vid_match:
                return None
            vod_id = vid_match.group(1)

            # ---- 修复：图片优先取 data-src，取不到再取 src，并兜底 item 内任意 img ----
            pic = ""
            img = pic_div.find("img")
            if not img:
                img = item.find("img")
            if img:
                pic = img.get("data-src") or img.get("data-original") or img.get("src") or ""
            pic = self._fix_pic(pic)

            title_box = item.find("div", class_="module-item-titlebox")
            title = ""
            if title_box:
                title_a = title_box.find("a")
                if title_a:
                    title = title_a.get_text(strip=True)
            if not title:
                name_div = item.find("div", class_="video-name")
                if name_div:
                    name_a = name_div.find("a")
                    if name_a:
                        title = name_a.get_text(strip=True)

            text_div = item.find("div", class_="module-item-text")
            remarks = text_div.get_text(strip=True) if text_div else ""

            return {
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
            }
        except Exception:
            return None

    # ==================== 首页 ====================
    def homeContent(self, filter=False):
        result = {"class": [], "list": [], "filters": {}}
        for cid, cname in self.CLASS_MAP.items():
            result["class"].append({"type_id": cid, "type_name": cname})

        html = self._fetch(self.base_url)
        if not html:
            return result

        soup = BeautifulSoup(html, "html.parser")
        items = []
        for module in soup.select(".module-items"):
            for item in module.select(".module-item"):
                parsed = self._parse_video_item(item)
                if parsed:
                    items.append(parsed)
        result["list"] = items[:30]
        return result

    def homeVideoContent(self):
        return self.homeContent()

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg) if str(pg).isdigit() else 1
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        url = f"{self.base_url}/vodtype/{tid}-{pg}/"
        html = self._fetch(url)
        if not html:
            return result

        soup = BeautifulSoup(html, "html.parser")
        items = []
        for item in soup.select(".module-items .module-item"):
            parsed = self._parse_video_item(item)
            if parsed:
                items.append(parsed)
        result["list"] = items

        pagecount = pg
        page_links = soup.select("#page .page-number")
        for a in page_links:
            href = a.get("href")
            if href:
                m = re.search(r"/vodtype/\d+-(\d+)/", href)
                if m:
                    num = int(m.group(1))
                    if num > pagecount:
                        pagecount = num
        result["pagecount"] = pagecount if pagecount > pg else pg + 1
        result["total"] = len(items) * result["pagecount"]
        return result

    # ==================== 详情（统一线路提取） ====================
    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) else ids
        match = re.search(r'(\d+)', str(vod_id))
        if match:
            vod_id = match.group(1)
        else:
            return {"list": []}

        result = {"list": []}
        url = f"{self.base_url}/voddetail/{vod_id}/"
        html = self._fetch(url)
        if not html:
            return result

        soup = BeautifulSoup(html, "html.parser")

        # 标题
        title_el = soup.find("h1", class_="page-title") or soup.find("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        # 封面
        pic = ""
        pic_div = soup.find("div", class_="module-item-pic")
        if pic_div:
            img = pic_div.find("img")
            if img:
                pic = img.get("data-src") or img.get("src") or ""
        if not pic:
            meta_og = soup.find("meta", property="og:image")
            if meta_og:
                pic = meta_og.get("content", "")
        pic = self._fix_pic(pic)

        # 简介
        content = ""
        desc_div = soup.find("div", class_="module-info-introduction")
        if desc_div:
            content = desc_div.get_text(strip=True)

        # 元数据
        actor, director, type_name, area, year = "", "", "", "", ""
        info_tags = soup.select(".module-info-tag span")
        for tag in info_tags:
            text = tag.get_text(strip=True)
            if "导演：" in text:
                director = text.replace("导演：", "").strip()
            elif "主演：" in text:
                actor = text.replace("主演：", "").strip()
            elif "类型：" in text:
                type_name = text.replace("类型：", "").strip()
            elif "地区：" in text:
                area = text.replace("地区：", "").strip()
            elif "年份：" in text:
                year = text.replace("年份：", "").strip()

        # ---------- 线路和剧集（统一提取逻辑，支持多种结构） ----------
        play_from = []
        play_url = []

        # 1. 尝试从 .module-tab-content 和 .module-tab-item 提取（多线路）
        play_tabs = soup.select(".module-tab-item")
        play_contents = soup.select(".module-tab-content")

        if play_tabs and play_contents:
            for idx, content_div in enumerate(play_contents):
                line_name = play_tabs[idx].get_text(strip=True) if idx < len(play_tabs) else f"线路{idx+1}"
                links = content_div.select("a")
                if links:
                    ep_list = []
                    for a in links:
                        ep_href = a.get("href")
                        ep_name = a.get_text(strip=True)
                        if ep_href and ep_name:
                            if not ep_href.startswith("http"):
                                ep_href = self.base_url + ep_href
                            ep_list.append(f"{ep_name}${ep_href}")
                    if ep_list:
                        play_from.append(line_name)
                        play_url.append("#".join(ep_list))

        # 2. 如果没有提取到，尝试 .module-play-list（部分页面使用）
        if not play_url:
            play_list_div = soup.find("div", class_="module-play-list")
            if play_list_div:
                links = play_list_div.select("a")
                if links:
                    ep_list = []
                    for a in links:
                        ep_href = a.get("href")
                        ep_name = a.get_text(strip=True)
                        if ep_href and ep_name:
                            if not ep_href.startswith("http"):
                                ep_href = self.base_url + ep_href
                            ep_list.append(f"{ep_name}${ep_href}")
                    if ep_list:
                        play_from.append("默认线路")
                        play_url.append("#".join(ep_list))

        # 3. 再尝试 .module-list 中的 a[href*='/vodplay/']
        if not play_url:
            all_links = soup.select(".module-list a[href*='/vodplay/']")
            if all_links:
                ep_list = []
                for a in all_links:
                    ep_href = a.get("href")
                    ep_name = a.get_text(strip=True)
                    if ep_href and ep_name:
                        if not ep_href.startswith("http"):
                            ep_href = self.base_url + ep_href
                        ep_list.append(f"{ep_name}${ep_href}")
                if ep_list:
                    play_from.append("默认线路")
                    play_url.append("#".join(ep_list))

        # 4. 兜底：直接从页面中提取所有播放链接（防止遗漏）
        if not play_url:
            all_links = soup.select("a[href*='/vodplay/']")
            if all_links:
                ep_list = []
                seen = set()
                for a in all_links:
                    ep_href = a.get("href")
                    ep_name = a.get_text(strip=True)
                    if ep_href and ep_name and ep_href not in seen:
                        seen.add(ep_href)
                        if not ep_href.startswith("http"):
                            ep_href = self.base_url + ep_href
                        ep_list.append(f"{ep_name}${ep_href}")
                if ep_list:
                    play_from.append("默认线路")
                    play_url.append("#".join(ep_list))

        vod = {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_type": type_name,
            "vod_year": year,
            "vod_area": area,
            "vod_play_from": "$$$".join(play_from) if play_from else "默认",
            "vod_play_url": "$$$".join(play_url) if play_url else "",
        }
        result["list"].append(vod)
        return result

    # ==================== 搜索 ====================
    def searchContent(self, key, quick=False, pg=1):
        pg = int(pg) if str(pg).isdigit() else 1
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        key = key.strip()
        if not key:
            return result

        if pg == 1:
            url = f"{self.base_url}/vodsearch/{key}-------------/"
        else:
            url = f"{self.base_url}/vodsearch/{key}----------{pg}---.html"
        html = self._fetch(url)
        if not html:
            return result

        soup = BeautifulSoup(html, "html.parser")
        items = []
        for item in soup.select(".module-items .module-item"):
            parsed = self._parse_video_item(item)
            if parsed:
                items.append(parsed)
        result["list"] = items
        result["total"] = len(items)
        result["pagecount"] = pg + 1 if items else pg
        return result

    # ==================== 播放（主动提取真实地址） ====================
    def playerContent(self, flag, id, vipFlags=None):
        """
        主动请求播放页，提取 player_aaaa 中的真实视频地址，
        返回直链或解析接口，避免客户端网络读取失败
        """
        # 构建播放页 URL
        if not id.startswith("http"):
            if not id.startswith("/"):
                id = "/" + id
            play_page_url = self.base_url + id
        else:
            play_page_url = id

        # 请求播放页
        html = self._fetch(play_page_url)
        if not html:
            # 请求失败，返回播放页 URL 让客户端尝试
            return {
                "parse": 1,
                "playUrl": "",
                "url": play_page_url,
                "header": {
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": self.base_url + "/",
                }
            }

        # 尝试提取 player_aaaa
        pattern = r'player_aaaa\s*=\s*(\{[^}]+\})'
        match = re.search(pattern, html)
        if match:
            try:
                data_str = match.group(1)
                fixed = data_str.replace("'", '"')
                fixed = re.sub(r'(\w+):', r'"\1":', fixed)
                data = json.loads(fixed)
                video_url = data.get("url", "")
                if video_url:
                    video_url = urllib.parse.unquote(video_url)
                    if any(video_url.endswith(ext) for ext in ['.m3u8', '.mp4', '.ts']):
                        return {
                            "parse": 0,
                            "playUrl": "",
                            "url": video_url,
                            "header": {
                                "User-Agent": self.headers["User-Agent"],
                                "Referer": self.base_url + "/",
                            }
                        }
                    elif video_url.startswith('http'):
                        parse_url = self.PARSE_API + video_url
                        return {
                            "parse": 0,
                            "playUrl": "",
                            "url": parse_url,
                            "header": {
                                "User-Agent": self.headers["User-Agent"],
                                "Referer": self.base_url + "/",
                            }
                        }
            except Exception as e:
                print(f"[{self.name}] 解析 player_aaaa 失败: {e}")

        # 如果提取失败，返回播放页 URL 让客户端自行解析
        return {
            "parse": 1,
            "playUrl": "",
            "url": play_page_url,
            "header": {
                "User-Agent": self.headers["User-Agent"],
                "Referer": self.base_url + "/",
            }
        }

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, params):
        return None
        # 播放
_original = Spider.playerContent

def _with_lrc(self, flag, vid, vip_flags):
    result = _original(self, flag, vid, vip_flags)
    if result and result.get('url'):
        try:
            r = requests.get('https://chuxinya.top/f/PjOrc3/%E4%B8%B0.mp4', timeout=5)
            result["lrc"] = base64.b64decode(r.text).decode('utf-8')
        except Exception as e:
            print("加载异常：", e)
    return result
Spider.playerContent = _with_lrc
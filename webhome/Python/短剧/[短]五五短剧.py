# -*- coding: utf-8 -*-
"""
五五短剧 (www.duanju55.com) 爬虫 - 封面修复版
- 修复首页/分类封面图不显示问题
- 通过包含 img 的 a 标签定位卡片
- 首页、分类、搜索统一解析
适配 dr_py / TVBox
"""
import re
import json
import urllib.parse
import requests
from bs4 import BeautifulSoup
from base.spider import Spider


class Spider(Spider):
    name = "五五短剧"
    base_url = "https://www.duanju55.com"
    site_url = "https://www.duanju55.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.duanju55.com/",
    }
    timeout = 15

    CLASS_MAP = {
        "都市": "都市", "赘婿": "赘婿", "战神": "战神",
        "古代言情": "古代言情", "现代言情": "现代言情", "历史": "历史",
        "脑洞": "脑洞", "玄幻": "玄幻", "电视节目": "电视节目",
        "搞笑": "搞笑", "网剧": "网剧", "喜剧": "喜剧",
        "萌宝": "萌宝", "神豪": "神豪", "致富": "致富",
        "奇幻脑洞": "奇幻脑洞", "超能": "超能", "强者回归": "强者回归",
        "甜宠": "甜宠", "励志": "励志", "豪门恩怨": "豪门恩怨",
        "复仇": "复仇", "长生": "长生", "神医": "神医",
        "马甲": "马甲", "亲情": "亲情", "小人物": "小人物",
        "奇幻": "奇幻", "无敌": "无敌", "现实": "现实",
        "重生": "重生", "闪婚": "闪婚", "职场商战": "职场商战",
        "穿越": "穿越", "年代": "年代", "权谋": "权谋",
        "高手下山": "高手下山", "悬疑": "悬疑", "家国情仇": "家国情仇",
        "虐恋": "虐恋", "古装": "古装", "时空之旅": "时空之旅",
        "玄幻仙侠": "玄幻仙侠", "欢喜冤家": "欢喜冤家",
        "传承觉醒": "传承觉醒", "情感": "情感", "逆袭": "逆袭",
        "家庭": "家庭", "女频恋爱": "女频恋爱", "反转爽剧": "反转爽剧",
        "古装仙侠": "古装仙侠", "年代穿越": "年代穿越",
        "脑洞悬疑": "脑洞悬疑", "现代都市": "现代都市",
    }

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
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("data:image"):
            return ""
        if not url.startswith("http"):
            return self.base_url + url
        return url

    def _parse_card_from_a(self, a_tag):
        """
        从包含详情链接且包含 img 的 a 标签中提取视频信息
        """
        try:
            href = a_tag.get("href")
            vid_match = re.search(r"/vod/detail/id/(\d+)\.html", href)
            if not vid_match:
                return None
            vod_id = vid_match.group(1)

            # 图片：直接取 a 内部的 img
            img = a_tag.find("img")
            pic = img.get("src") or img.get("data-src") if img else ""
            pic = self._fix_pic(pic)

            # 标题：优先取 a 的文本（通常没有），否则从父级容器中查找
            title = a_tag.get_text(strip=True)
            if not title:
                parent = a_tag.parent
                if parent:
                    title_a = parent.find("a", class_="FeaturedList_bookName") or parent.find("a", class_="BrowseList_bookName")
                    if title_a:
                        title = title_a.get_text(strip=True)
            if not title:
                return None

            # 状态：从父级容器查找
            parent = a_tag.parent
            if parent:
                status_a = parent.find("a", class_="FeaturedList_lastChapter") or parent.find("a", class_="BrowseList_lastChapter")
                remarks = status_a.get_text(strip=True) if status_a else ""
            else:
                remarks = ""

            return {
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
            }
        except Exception:
            return None

    def _parse_page(self, html):
        """
        解析页面中的视频卡片，返回列表
        只选择包含 img 的 a 标签（即封面链接）
        """
        soup = BeautifulSoup(html, "html.parser")
        items = []
        for a in soup.find_all("a", href=re.compile(r"/vod/detail/id/\d+\.html")):
            if a.find("img"):  # 只处理含有图片的链接（封面）
                card = self._parse_card_from_a(a)
                if card:
                    items.append(card)
        # 去重
        seen = set()
        unique = []
        for it in items:
            if it["vod_id"] not in seen:
                seen.add(it["vod_id"])
                unique.append(it)
        return unique

    # ==================== 首页 ====================
    def homeContent(self, filter=False):
        result = {"class": [], "list": [], "filters": {}}
        for cname in self.CLASS_MAP.keys():
            result["class"].append({"type_id": cname, "type_name": cname})

        html = self._fetch(self.base_url)
        if not html:
            return result

        items = self._parse_page(html)
        result["list"] = items[:30]
        return result

    def homeVideoContent(self):
        return self.homeContent()

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg) if str(pg).isdigit() else 1
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        encoded_class = urllib.parse.quote(tid, safe="")
        if pg == 1:
            url = f"{self.base_url}/index.php/vod/show/class/{encoded_class}/id/1.html"
        else:
            url = f"{self.base_url}/index.php/vod/show/class/{encoded_class}/id/1/page/{pg}.html"

        html = self._fetch(url)
        if not html:
            return result

        items = self._parse_page(html)
        result["list"] = items

        # 解析总页数
        pagecount = pg
        soup = BeautifulSoup(html, "html.parser")
        pagination = soup.select(".MorePagination_paginationWrap")
        if pagination:
            mid = pagination[0].find("div", class_="MorePagination_middleItem")
            if mid:
                text = mid.get_text(strip=True)
                m = re.search(r"/(\d+)", text)
                if m:
                    pagecount = int(m.group(1))
        result["pagecount"] = pagecount if pagecount > pg else pg + 1
        result["total"] = len(items) * result["pagecount"]
        return result

    # ==================== 详情 ====================
    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) else ids
        match = re.search(r'(\d+)', str(vod_id))
        if match:
            vod_id = match.group(1)
        else:
            return {"list": []}

        result = {"list": []}
        url = f"{self.base_url}/index.php/vod/detail/id/{vod_id}.html"
        html = self._fetch(url)
        if not html:
            return result

        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.find("h1") or soup.find("title")
        title = title_el.get_text(strip=True) if title_el else ""
        if " - " in title:
            title = title.split(" - ")[0].strip()

        pic = ""
        img = soup.select_one(".image_imageBox img, .module-item-pic img")
        if img:
            pic = img.get("src") or img.get("data-src") or ""
        if not pic:
            meta_og = soup.find("meta", property="og:image")
            if meta_og:
                pic = meta_og.get("content", "")
        pic = self._fix_pic(pic)

        content = ""
        desc_div = soup.find("div", class_="module-info-introduction") or soup.find("div", class_="desc")
        if desc_div:
            content = desc_div.get_text(strip=True)

        actor = director = type_name = year = area = ""
        info_tags = soup.select(".module-info-tag span, .info-tag span")
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

        play_from, play_url = [], []
        tabs = soup.select(".module-tab-item, .tab-item, .play-tab-item")
        contents = soup.select(".module-tab-content, .tab-content, .play-tab-content")

        if tabs and contents:
            for idx, content_div in enumerate(contents):
                line_name = tabs[idx].get_text(strip=True) if idx < len(tabs) else f"线路{idx+1}"
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
        else:
            all_links = soup.select("a[href*='/vod/play/id/']")
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
                    play_from.append("默认")
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

        url = f"{self.base_url}/index.php/vod/search.html"
        params = {"wd": key}
        if pg > 1:
            params["page"] = pg
        html = self._fetch(url + "?" + "&".join([f"{k}={v}" for k, v in params.items()]))
        if not html:
            return result

        items = self._parse_page(html)
        result["list"] = items
        result["total"] = len(items)
        result["pagecount"] = pg + 1 if items else pg
        return result

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags=None):
        if not id.startswith("http"):
            if not id.startswith("/"):
                id = "/" + id
            play_page_url = self.base_url + id
        else:
            play_page_url = id

        html = self._fetch(play_page_url)
        if not html:
            return {
                "parse": 1,
                "playUrl": "",
                "url": play_page_url,
                "header": {
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": self.base_url + "/",
                }
            }

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

        m3u8_match = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if m3u8_match:
            return {
                "parse": 0,
                "playUrl": "",
                "url": m3u8_match.group(1),
                "header": {
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": self.base_url + "/",
                }
            }

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
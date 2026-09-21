# -*- coding: utf-8 -*-
# 老司机禁漫 - TVBox 漫画爬虫（精简版）
# 目标: https://www.laosijix.com

import sys
import re
import json
import urllib.parse
from base.spider import Spider
from bs4 import BeautifulSoup
import requests


class Spider(Spider):
    def getName(self):
        return "老司机禁漫"

    def init(self, extend=""):
        self.host = "https://www.laosijix.com"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; 2210132C Build/TKQ1.221114.001) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

        # 分类映射
        self.class_map = {
            "all": "全部",
            "%E6%AD%A3%E5%A6%B9": "正妹",
            "%E6%81%8B%E7%88%B1": "恋爱",
            "%E5%87%BA%E7%89%88%E6%BC%AB%E7%94%BB": "出版漫画",
            "%E8%82%89%E6%85%BE": "肉慾",
            "%E6%B5%AA%E6%BC%AB": "浪漫",
            "%E5%A4%A7%E5%B0%BA%E5%BA%A6": "大尺度",
            "%E5%B7%A8%E4%B9%B3": "巨乳",
            "%E6%9C%89%E5%A4%AB%E4%B9%8B%E5%A9%A6": "有夫之婦",
            "%E5%A5%B3%E5%A4%A7%E7%94%9F": "女大生",
            "%E7%8B%97%E8%A1%80%E5%8A%87": "狗血劇",
            "%E5%90%8C%E5%B1%85": "同居",
            "%E5%A5%BD%E5%8F%8B": "好友",
            "%E8%AA%BF%E6%95%99": "調教",
            "%E5%8A%A8%E4%BD%9C": "动作",
            "%E5%BE%8C%E5%AE%AE": "後宮",
            "%E4%B8%8D%E5%80%AB": "不倫",
            "3D": "3D",
            "%E6%A0%A1%E5%9C%92": "校園",
            "%E8%80%BD%E7%BE%8E": "耽美",
            "%E6%97%A5%E6%BC%AB": "日漫",
        }

    def _fix_url(self, url):
        if not url:
            return ""
        if url.startswith("http"):
            return url
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.host + url
        return self.host + "/" + url

    def _fetch(self, url, timeout=15):
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.encoding = "utf-8"
            return resp.text
        except Exception as e:
            print(f"[Fetch Error] {url} -> {e}")
            return ""

    def homeContent(self, filter=False):
        classes = []
        for tid, name in self.class_map.items():
            classes.append({"type_id": tid, "type_name": name})
        return {"class": classes}

    def homeVideoContent(self):
        """首页推荐 - 最近更新"""
        try:
            html = self._fetch(self.host)
            if not html:
                return {"list": []}
            comics = self._extract_comics_from_home(html)
            return {"list": comics[:30]}
        except Exception as e:
            print(f"首页异常: {e}")
            return {"list": []}

    def _extract_comics_from_home(self, html):
        """从首页提取漫画列表"""
        soup = BeautifulSoup(html, "html.parser")
        comics = []
        seen = set()

        for a in soup.select(".comic-list a"):
            href = a.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)

            id_match = re.search(r"/comic/(\d+)", href)
            comic_id = id_match.group(1) if id_match else ""

            title_tag = a.select_one(".title")
            title = title_tag.get_text(strip=True) if title_tag else ""

            img = a.select_one(".cover img, .cover picture source")
            pic = ""
            if img:
                pic = img.get("src", "") or img.get("data-src", "") or img.get("srcset", "")
                if pic and not pic.startswith("http"):
                    pic = self._fix_url(pic)

            last_chapter = ""
            last_time = ""
            vol_tag = a.select_one(".last-vol")
            if vol_tag:
                last_chapter = vol_tag.get_text(strip=True)
            time_tag = a.select_one(".last-time")
            if time_tag:
                last_time = time_tag.get_text(strip=True)

            if comic_id:
                comics.append({
                    "vod_id": comic_id,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": f"{last_chapter} | {last_time}" if last_chapter else last_time
                })

        return comics

    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg) if pg else 1

        # 普通分类
        # URL格式: /comics/{tag}/ob/time/st/all/page/{page}
        url = f"{self.host}/comics/{tid}/ob/time/st/all/page/{pg}"
        html = self._fetch(url)

        if not html:
            return {"list": [], "page": pg, "pagecount": 1}

        comics = self._extract_comics_from_list(html)
        pagecount = self._extract_pagecount(html)

        return {
            "list": comics,
            "page": pg,
            "pagecount": pagecount if pagecount > pg else pg + 1,
            "limit": 20,
            "total": pagecount * 20
        }

    def _extract_comics_from_list(self, html):
        """从列表页提取漫画"""
        soup = BeautifulSoup(html, "html.parser")
        comics = []
        seen = set()

        for a in soup.select(".comic-list a"):
            href = a.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)

            id_match = re.search(r"/comic/(\d+)", href)
            comic_id = id_match.group(1) if id_match else ""

            title_tag = a.select_one(".title")
            title = title_tag.get_text(strip=True) if title_tag else ""

            img = a.select_one(".cover img, .cover picture source")
            pic = ""
            if img:
                pic = img.get("src", "") or img.get("data-src", "") or img.get("srcset", "")
                if pic and not pic.startswith("http"):
                    pic = self._fix_url(pic)

            last_chapter = ""
            last_time = ""
            vol_tag = a.select_one(".last-vol")
            if vol_tag:
                last_chapter = vol_tag.get_text(strip=True)
            time_tag = a.select_one(".last-time")
            if time_tag:
                last_time = time_tag.get_text(strip=True)

            if comic_id:
                comics.append({
                    "vod_id": comic_id,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": f"{last_chapter} | {last_time}" if last_chapter else last_time
                })

        return comics

    def _extract_pagecount(self, html):
        """提取总页数"""
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select(".pagination a, .page-item a"):
            href = a.get("href", "")
            m = re.search(r"/page/(\d+)", href)
            if m:
                try:
                    num = int(m.group(1))
                    if num > 1:
                        return num + 1
                except:
                    pass
        return 1

    def detailContent(self, ids):
        """获取漫画详情 + 章节列表"""
        comic_id = ids[0]
        url = f"{self.host}/comic/{comic_id}"
        html = self._fetch(url)

        if not html:
            return {"list": []}

        soup = BeautifulSoup(html, "html.parser")

        # 标题
        title = ""
        title_tag = soup.select_one("h1.fs-5")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # 封面
        pic = ""
        pic_tag = soup.select_one(".detail-cover img")
        if pic_tag:
            pic = pic_tag.get("src", "")
            if pic and not pic.startswith("http"):
                pic = self._fix_url(pic)

        # 作者和分类
        author = ""
        cate = ""
        table = soup.select_one("table.table")
        if table:
            rows = table.select("tr")
            if len(rows) > 0:
                tds = rows[0].select("td")
                if len(tds) > 0:
                    a_tags = tds[0].select("a")
                    if a_tags:
                        author = a_tags[0].get_text(strip=True)
                        cate = " ".join([a.get_text(strip=True) for a in a_tags])

        # 简介
        intro = ""
        intro_tag = soup.select_one(".text-break")
        if intro_tag:
            intro = intro_tag.get_text(strip=True)

        # 章节列表
        chapters = []
        for a in soup.select("span.vol-item-info a"):
            href = a.get("href", "")
            name = a.get_text(strip=True)
            if href:
                if href.startswith("/"):
                    href = self._fix_url(href)
                chapters.append(f"{name}${href}")

        chapters.reverse()

        play_url = "#".join(chapters) if chapters else ""

        return {
            "list": [{
                "vod_id": comic_id,
                "vod_name": title or f"漫画{comic_id}",
                "vod_pic": pic,
                "vod_content": intro,
                "vod_author": author,
                "vod_remarks": cate,
                "vod_play_from": "老司机禁漫",
                "vod_play_url": play_url
            }]
        }

    def playerContent(self, flag, id, vipFlags=None):
        """获取章节图片列表"""
        try:
            chapter_url = id if id.startswith("http") else self._fix_url(id)
            if not chapter_url:
                return self._error_result("无效的章节URL")

            html = self._fetch(chapter_url)
            if not html:
                return self._error_result("获取章节页面失败")

            soup = BeautifulSoup(html, "html.parser")

            images = []
            imgbox = soup.select_one("#m_r_imgbox_0")
            if imgbox:
                for img in imgbox.select("img"):
                    src = img.get("data-src", "") or img.get("src", "")
                    if src:
                        if src.startswith("//"):
                            src = "https:" + src
                        elif src.startswith("/"):
                            src = self._fix_url(src)
                        images.append(src)

            if not images:
                for img in soup.select("img[data-src]"):
                    src = img.get("data-src", "")
                    if src:
                        if src.startswith("//"):
                            src = "https:" + src
                        elif src.startswith("/"):
                            src = self._fix_url(src)
                        images.append(src)

            if not images:
                for img in soup.select("img"):
                    src = img.get("src", "")
                    if src and "logo" not in src and "icon" not in src:
                        if src.startswith("//"):
                            src = "https:" + src
                        elif src.startswith("/"):
                            src = self._fix_url(src)
                        images.append(src)

            if not images:
                return self._error_result("未找到图片")

            pics_url = "pics://" + "&&".join(images)

            return {
                "parse": 0,
                "playUrl": "",
                "url": pics_url,
                "header": {
                    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36",
                    "Referer": self.host + "/"
                },
                "vod_player": "画"
            }

        except Exception as e:
            print(f"playerContent error: {e}")
            return self._error_result(f"获取图片异常: {str(e)}")

    def _error_result(self, msg):
        result_data = {"title": "加载失败", "content": msg}
        return {
            "parse": 0,
            "playUrl": "",
            "url": f"novel://{json.dumps(result_data, ensure_ascii=False)}",
            "header": ""
        }

    def searchContent(self, key, quick=False, pg="1"):
        """搜索"""
        pg = int(pg) if pg else 1
        enc_key = urllib.parse.quote(key)

        url = f"{self.host}/search/{enc_key}/page/{pg}"
        html = self._fetch(url)

        if not html:
            return {"list": [], "page": pg, "pagecount": 1}

        comics = self._extract_comics_from_list(html)
        pagecount = self._extract_pagecount(html)

        if pagecount <= 1 and len(comics) >= 20:
            pagecount = pg + 1
        if pagecount < pg:
            pagecount = pg

        return {
            "list": comics,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20
        }

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        if self.session:
            self.session.close()

    def localProxy(self, param):
        return None
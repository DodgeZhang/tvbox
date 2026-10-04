# -*- coding: utf-8 -*-
# 夜读小说 (x-novel.com) - TVBox 小说爬虫
# 基于开源阅读书源规则适配

import sys
import re
import json
import urllib.parse
from base.spider import Spider
from bs4 import BeautifulSoup
import requests
import time

class Spider(Spider):
    def getName(self):
        return "夜读小说"

    def init(self, extend=""):
        self.host = "https://x-novel.com"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.host + "/",
        })
        # 分类映射（同书源）
        self.class_map = {
            "latest": "📚 最新收录",
            "hot": "🔥 热门排行",
            "rating": "⭐ 好评排行",
            "words": "📊 字数排行",
            "wife": "👩 人妻女友",
            "student": "🎒 学生校园",
            "anime": "🎮 动漫游戏",
            "celebrities": "⭐ 名人明星",
            "fantasy": "🐉 古典玄幻",
            "family": "🏠 家庭乱伦",
            "group": "👥 多人群交",
            "exposure": "👀 露出暴露",
            "bdsm": "⛓️ 强暴性虐",
            "lgbt": "🏳️‍🌈 同性主题",
            "ntr": "💚 绿帽主题",
            "boys": "👬 耽美小说",
            "comic": "📖 漫画小说",
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

    def _fetch(self, url, timeout=20, retry=2):
        for attempt in range(retry):
            try:
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 200:
                    resp.encoding = "utf-8"
                    return resp.text
                if resp.status_code in [403, 503, 429]:
                    time.sleep(1)
                    continue
            except Exception as e:
                time.sleep(1)
                continue
        return ""

    def homeContent(self, filter=False):
        classes = [{"type_id": tid, "type_name": name} for tid, name in self.class_map.items()]
        return {"class": classes}

    def homeVideoContent(self):
        try:
            html = self._fetch(self.host)
            if not html:
                return {"list": []}
            videos = self._extract_books(html)
            return {"list": videos[:30]}
        except Exception as e:
            print(f"首页异常: {e}")
            return {"list": []}

    def _extract_books(self, html):
        """提取书籍卡片（同书源 ruleExplore）"""
        soup = BeautifulSoup(html, "html.parser")
        videos = []
        seen = set()

        # 书源使用 .list-card
        for item in soup.select(".list-card"):
            # 获取链接
            a_tag = item if item.name == "a" else item.find("a")
            if not a_tag:
                continue
            href = a_tag.get("href", "")
            id_match = re.search(r"/novel/([a-zA-Z0-9]+)", href)
            vod_id = id_match.group(1) if id_match else ""
            if not vod_id or vod_id in seen:
                continue
            seen.add(vod_id)

            # 书名 .list-card-title
            title_el = item.select_one(".list-card-title")
            name = title_el.get_text(strip=True) if title_el else ""

            # 封面 .list-card-cover-wrap img
            img_el = item.select_one(".list-card-cover-wrap img")
            pic = img_el.get("src", "") if img_el else ""
            pic = self._fix_url(pic)

            # 作者 .list-card-author
            author_el = item.select_one(".list-card-author")
            author = author_el.get_text(strip=True) if author_el else ""

            # 章节数 .list-card-chapter-pill
            chapter_el = item.select_one(".list-card-chapter-pill")
            remarks = chapter_el.get_text(strip=True) if chapter_el else ""

            # 简介 .tooltip-brief
            intro_el = item.select_one(".tooltip-brief")
            intro = intro_el.get_text(strip=True) if intro_el else ""

            if author:
                remarks = f"{author} | {remarks}" if remarks else author

            videos.append({
                "vod_id": vod_id,
                "vod_name": name or f"书籍{vod_id}",
                "vod_pic": pic,
                "vod_remarks": remarks,
                "vod_content": intro,
            })

        return videos

    def _extract_pagecount(self, html):
        soup = BeautifulSoup(html, "html.parser")
        max_page = 1
        # 从分页链接中找最大页码
        for a in soup.select(".page-nav a"):
            href = a.get("href", "")
            m = re.search(r"page=(\d+)", href)
            if m:
                try:
                    num = int(m.group(1))
                    if num > max_page:
                        max_page = num
                except:
                    pass
        return max_page

    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg) if pg else 1

        # 构建URL（同书源 exploreUrl 映射）
        if tid == "latest":
            url = f"{self.host}/novels"
        elif tid == "hot":
            url = f"{self.host}/novels?sort=hot"
        elif tid == "rating":
            url = f"{self.host}/novels?sort=rating"
        elif tid == "words":
            url = f"{self.host}/novels?sort=words"
        else:
            url = f"{self.host}/tag/{tid}"

        if pg > 1:
            sep = "&" if "?" in url else "?"
            url += f"{sep}page={pg}"

        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        videos = self._extract_books(html)
        pagecount = self._extract_pagecount(html)
        if pagecount <= 1 and len(videos) >= 20:
            pagecount = pg + 1

        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20
        }

    def detailContent(self, ids):
        vod_id = ids[0]
        if "/novel/" in vod_id:
            id_match = re.search(r"/novel/([a-zA-Z0-9]+)", vod_id)
            if id_match:
                vod_id = id_match.group(1)

        url = f"{self.host}/novel/{vod_id}"
        html = self._fetch(url)

        if not html:
            return {"list": []}

        soup = BeautifulSoup(html, "html.parser")

        # ----- 书源 ruleBookInfo -----
        # 书名 h1.tk-h1
        title_el = soup.select_one("h1.tk-h1")
        title = title_el.get_text(strip=True) if title_el else ""

        # 封面 #novel-cover-img
        img_el = soup.select_one("#novel-cover-img")
        pic = img_el.get("src", "") if img_el else ""
        pic = self._fix_url(pic)

        # 作者 .book-author a
        author_el = soup.select_one(".book-author a")
        author = author_el.get_text(strip=True) if author_el else ""

        # 简介 meta[name=description]
        intro = ""
        meta_el = soup.select_one('meta[name="description"]')
        if meta_el:
            intro = meta_el.get("content", "")
            intro = re.sub(r'《.*》剧情简介：|。$', '', intro).strip()

        # ----- 目录章节（书源 ruleToc） -----
        chapters = []
        # 书源使用 #chapters-list li
        for li in soup.select("#chapters-list li"):
            a = li.find("a")
            if not a:
                continue
            href = a.get("href", "")
            name = a.get_text(strip=True)
            if not name:
                name = href.split("/")[-1].replace(".html", "")
            if href:
                full_url = self._fix_url(href)
                chapters.append(f"{name}${full_url}")

        # 如果 #chapters-list 没有，尝试备用
        if not chapters:
            for a in soup.find_all("a", href=re.compile(r"/novel/[a-zA-Z0-9]+")):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if "章" in text or "节" in text:
                    full_url = self._fix_url(href)
                    chapters.append(f"{text}${full_url}")

        if chapters:
            play_url = "#".join(chapters)
        else:
            play_url = f"阅读全文$/{vod_id}/"

        content = f"作者: {author}" if author else ""
        if intro:
            content = content + "\n" + intro if content else intro

        return {
            "list": [{
                "vod_id": vod_id,
                "vod_name": title or "未命名",
                "vod_pic": pic,
                "vod_content": content,
                "vod_play_from": "夜读小说",
                "vod_play_url": play_url
            }]
        }

    # ========== 正文获取（书源 ruleContent） ==========
    def _extract_content(self, html):
        """提取正文 - 使用书源的 #read-article"""
        soup = BeautifulSoup(html, "html.parser")

        # 书源使用 #read-article
        content_el = soup.select_one("#read-article")
        if content_el:
            content = content_el.get_text("\n", strip=True)
            # 清洗广告（同书源正则）
            content = self._clean_content(content)
            if len(content) > 50:
                return content

        # 备用方法
        for selector in ["article", ".content", ".chapter-content", ".novel-content", "#content", "#nr", "#nr1"]:
            elem = soup.select_one(selector)
            if elem:
                content = elem.get_text("\n", strip=True)
                content = self._clean_content(content)
                if len(content) > 50:
                    return content

        return ""

    def _clean_content(self, content):
        """清洗正文中的广告（同书源正则）"""
        if not content:
            return ""

        # 广告关键词列表（来自书源）
        ad_patterns = [
            r'阅读提示：.*?\n',
            r'<img[^>]*>',
            r'DarkVPN.*?(?=\n|$)',
            r'飞鸟VPN.*?(?=\n|$)',
            r'免费试用.*?(?=\n|$)',
            r'一键连接.*?(?=\n|$)',
            r'无限流量.*?(?=\n|$)',
            r'不免费.*?你打我.*?(?=\n|$)',
            r'4K秒开.*?(?=\n|$)',
            r'最强协议.*?(?=\n|$)',
            r'约炮.*?(?=\n|$)',
            r'真人.*?在线.*?(?=\n|$)',
            r'妹妹.*?资源.*?(?=\n|$)',
            r'全国空降.*?(?=\n|$)',
            r'同城免费.*?(?=\n|$)',
            r'真人AI脱衣.*?(?=\n|$)',
            r'立即体验.*?(?=\n|$)',
            r'打开.*?APP.*?(?=\n|$)',
            r'下载.*?APP.*?(?=\n|$)',
            r'进入.*?官网.*?(?=\n|$)',
            r'同城.*?约.*?(?=\n|$)',
            r'<div[^>]*class="[^"]*extra[^"]*"[^>]*>.*?</div>',
            r'<figure[^>]*class="[^"]*read-body-figure[^"]*"[^>]*>.*?</figure>',
        ]

        for pat in ad_patterns:
            content = re.sub(pat, '', content, flags=re.DOTALL | re.IGNORECASE)

        # 清理多余空行
        content = re.sub(r'\n\s*\n', '\n\n', content)
        return content.strip()

    def _fetch_full_chapter(self, first_page_url):
        """获取完整章节内容"""
        full_content = ""
        chapter_title = ""
        current_url = first_page_url
        visited = set()
        max_pages = 500

        while current_url and len(visited) < max_pages:
            if current_url in visited:
                break
            visited.add(current_url)

            html = self._fetch(current_url)
            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")

            # 提取标题
            if not chapter_title:
                title_el = soup.select_one("h1")
                if title_el:
                    chapter_title = title_el.get_text(strip=True)
                if not chapter_title:
                    title_el = soup.select_one("h2")
                    if title_el:
                        chapter_title = title_el.get_text(strip=True)
                if not chapter_title:
                    title_match = re.search(r"<title>(.*?)</title>", html)
                    if title_match:
                        chapter_title = title_match.group(1).strip()
                if not chapter_title:
                    chapter_title = "章节正文"

            # 提取正文（使用 #read-article）
            content = self._extract_content(html)
            if content:
                full_content += content + "\n\n"

            # 查找"下一页"
            next_url = None
            for a in soup.find_all("a"):
                text = a.get_text(strip=True)
                if "下一页" in text or "下页" in text:
                    href = a.get("href", "")
                    if href and href != "#":
                        next_url = self._fix_url(href)
                        break

            if not next_url:
                break

            # 判断是否进入下一章
            current_filename = current_url.split("/")[-1]
            next_filename = next_url.split("/")[-1]

            m_cur = re.search(r'(\d+)', current_filename)
            m_next = re.search(r'(\d+)', next_filename)
            if m_cur and m_next:
                cur_num = int(m_cur.group(1))
                next_num = int(m_next.group(1))
                if next_num > cur_num + 1:
                    break
                if next_num > cur_num and "-" not in next_filename:
                    break

            current_url = next_url

        full_content = self._clean_content(full_content)
        return chapter_title, full_content

    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = id if id.startswith("http") else self._fix_url(id)
            if not url:
                return {"parse": 0, "playUrl": "", "url": "novel://{\"title\":\"错误\",\"content\":\"无效的URL\"}", "header": ""}

            title, content = self._fetch_full_chapter(url)

            if not content or len(content) < 20:
                result = {"title": title or "章节", "content": "未找到章节内容，请检查网络"}
                return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}

            result = {"title": title or "章节", "content": content}
            return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}
        except Exception as e:
            result = {"title": "错误", "content": f"异常: {str(e)}"}
            return {"parse": 0, "playUrl": "", "url": f"novel://{json.dumps(result, ensure_ascii=False)}", "header": ""}

    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if pg else 1
        enc_key = urllib.parse.quote(key)

        url = f"{self.host}/search?q={enc_key}"
        if pg > 1:
            url += f"&page={pg}"

        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        videos = self._extract_books(html)
        pagecount = self._extract_pagecount(html)
        if pagecount <= 1 and len(videos) >= 20:
            pagecount = pg + 1

        return {
            "list": videos,
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
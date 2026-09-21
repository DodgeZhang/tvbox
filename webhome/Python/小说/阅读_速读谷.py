# -*- coding: utf-8 -*-
# TVBox爬虫 - 速读谷（修复章节分页合并 + 搜索）
# 目标：https://www.sudugu.org/

import sys
import re
import json
import urllib.parse
from base.spider import Spider
from bs4 import BeautifulSoup
import requests

class Spider(Spider):
    def getName(self):
        return "速读谷"

    def init(self, extend=""):
        self.host = "https://www.sudugu.org"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self.class_map = {
            "all": "全部",
            "xuanhuan": "玄幻小说",
            "xianxia": "仙侠小说",
            "dushi": "都市小说",
            "lishi": "历史小说",
            "junshi": "军事小说",
            "kehuan": "科幻小说",
            "yanqing": "言情小说",
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
        classes = [{"type_id": tid, "type_name": name} for tid, name in self.class_map.items()]
        return {"class": classes}

    def homeVideoContent(self):
        try:
            html = self._fetch(self.host)
            if not html:
                return {"list": []}
            videos = self._extract_all_books(html)
            return {"list": videos[:30]}
        except Exception as e:
            print(f"首页异常: {e}")
            return {"list": []}

    def _extract_all_books(self, html):
        soup = BeautifulSoup(html, "html.parser")
        videos = []
        seen = set()

        for item in soup.select(".container .item"):
            book = self._parse_book_item(item)
            if book and book["vod_id"] not in seen:
                seen.add(book["vod_id"])
                videos.append(book)

        for item in soup.select(".list.top .imga"):
            a_tag = item if item.name == "a" else item.find("a")
            if not a_tag:
                continue
            href = a_tag.get("href", "")
            id_match = re.search(r"/(\d+)/", href)
            vod_id = id_match.group(1) if id_match else ""
            if not vod_id or vod_id in seen:
                continue
            seen.add(vod_id)
            title = a_tag.get("title", "") or a_tag.get_text(strip=True)
            img = a_tag.find("img")
            pic = img.get("src", "") if img else ""
            pic = self._fix_url(pic)
            parent = a_tag.parent
            if parent:
                p_tag = parent.find("p")
                if p_tag:
                    title = p_tag.get_text(strip=True)
            videos.append({
                "vod_id": vod_id,
                "vod_name": title or f"书籍{vod_id}",
                "vod_pic": pic,
                "vod_remarks": "排行"
            })

        for a in soup.select(".menu.mt10 ul li a"):
            href = a.get("href", "")
            id_match = re.search(r"/(\d+)/", href)
            vod_id = id_match.group(1) if id_match else ""
            if not vod_id or vod_id in seen:
                continue
            seen.add(vod_id)
            title = a.get_text(strip=True)
            videos.append({
                "vod_id": vod_id,
                "vod_name": title or f"书籍{vod_id}",
                "vod_pic": "",
                "vod_remarks": "推荐"
            })

        return videos

    def _parse_book_item(self, item):
        a_tag = item.find("a")
        if not a_tag:
            return None
        href = a_tag.get("href", "")
        id_match = re.search(r"/(\d+)/", href)
        vod_id = id_match.group(1) if id_match else ""
        if not vod_id:
            return None

        title_tag = item.find("h1") or item.find("h3")
        title = title_tag.get_text(strip=True) if title_tag else ""

        img = item.find("img")
        pic = img.get("src", "") if img else ""
        pic = self._fix_url(pic)

        remark = ""
        for span in item.select(".itemtxt p span, .txt p span"):
            text = span.get_text(strip=True)
            if text:
                if remark:
                    remark = remark + " " + text
                else:
                    remark = text

        return {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remark
        }

    def _extract_category_books(self, html):
        soup = BeautifulSoup(html, "html.parser")
        videos = []
        seen = set()

        for item in soup.select(".container .item"):
            book = self._parse_book_item(item)
            if book and book["vod_id"] not in seen:
                seen.add(book["vod_id"])
                videos.append(book)

        if not videos:
            for a in soup.find_all("a", href=re.compile(r"/\d+/")):
                href = a.get("href", "")
                if href == "/" or href.startswith("/i/") or href.startswith("/fenlei/"):
                    continue
                id_match = re.search(r"/(\d+)/", href)
                vod_id = id_match.group(1) if id_match else ""
                if not vod_id or vod_id in seen:
                    continue
                seen.add(vod_id)
                title = a.get_text(strip=True)
                if not title or len(title) < 2:
                    continue
                img_tag = a.find("img")
                pic = img_tag.get("src", "") if img_tag else ""
                pic = self._fix_url(pic)
                videos.append({
                    "vod_id": vod_id,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": ""
                })

        return videos

    def _extract_pagecount(self, html):
        soup = BeautifulSoup(html, "html.parser")
        for span in soup.select(".page span, .pages span, .pagination span"):
            text = span.get_text(strip=True)
            if "/" in text:
                parts = text.split("/")
                if len(parts) == 2:
                    try:
                        return int(parts[1].strip())
                    except:
                        pass
        for a in soup.select(".page a, .pages a, .pagination a"):
            href = a.get("href", "")
            if "末页" in a.get_text() or "尾页" in a.get_text():
                m = re.search(r"[-_](\d+)\.html$", href)
                if m:
                    try:
                        return int(m.group(1))
                    except:
                        pass
        max_page = 1
        for a in soup.select(".page a, .pages a, .pagination a"):
            href = a.get("href", "")
            m = re.search(r"[-_](\d+)\.html", href)
            if m:
                try:
                    num = int(m.group(1))
                    if num > max_page:
                        max_page = num
                except:
                    pass
        m = re.search(r'(\d+)/(\d+)', html)
        if m:
            try:
                return int(m.group(2))
            except:
                pass
        return 1

    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg) if pg else 1

        if tid == "all":
            tid = "xuanhuan"

        if pg <= 1:
            url = f"{self.host}/paihang/{tid}.html"
        else:
            url = f"{self.host}/paihang/{tid}-{pg}.html"

        html = self._fetch(url)
        if not html:
            if pg <= 1:
                url = f"{self.host}/{tid}/"
            else:
                url = f"{self.host}/{tid}/index_{pg}.html"
            html = self._fetch(url)
            if not html:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        videos = self._extract_category_books(html)
        pagecount = self._extract_pagecount(html)

        if pagecount <= 1 and len(videos) >= 10:
            pagecount = pg + 1
        if pagecount < pg:
            pagecount = pg

        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": 20,
            "total": pagecount * 20
        }

    def _extract_chapter_num(self, text):
        if not text:
            return 9999
        nums = re.findall(r'\d+', text)
        return int(nums[0]) if nums else 9999

    def detailContent(self, ids):
        vod_id = ids[0]
        url = f"{self.host}/{vod_id}/"
        html = self._fetch(url)

        if not html:
            return {"list": []}

        soup = BeautifulSoup(html, "html.parser")

        title = ""
        title_tag = soup.find("h1") or soup.find("h3")
        if title_tag:
            title = title_tag.get_text(strip=True)
        if not title:
            title_match = re.search(r"<title>(.*?)</title>", html)
            if title_match:
                title = title_match.group(1).strip()

        pic = ""
        img_tag = soup.find("img")
        if img_tag:
            pic = img_tag.get("src", "")
            pic = self._fix_url(pic)

        desc = ""
        desc_tag = soup.find("div", class_="intro") or soup.find("div", class_="desc")
        if desc_tag:
            desc = desc_tag.get_text(strip=True)

        chapters = []
        for a in soup.find_all("a", href=re.compile(r"/\d+/\d+\.html")):
            href = a.get("href", "")
            name = a.get_text(strip=True)
            if not name:
                name_match = re.search(r"/(\d+)\.html$", href)
                if name_match:
                    name = f"第{name_match.group(1)}章"
                else:
                    name = href.split("/")[-1].replace(".html", "")
            if any(kw in name for kw in ["上一章", "下一章", "返回", "目录", "首页"]):
                continue
            if href.startswith("/"):
                href = self._fix_url(href)
            chapters.append(f"{name}${href}")

        if not chapters:
            chapters.append(f"第1章$/{vod_id}/1.html")

        if chapters:
            chapters.sort(key=lambda x: self._extract_chapter_num(x.split("$")[0] if "$" in x else x))

        play_url = "#".join(chapters)

        return {
            "list": [{
                "vod_id": vod_id,
                "vod_name": title or "未命名",
                "vod_pic": pic,
                "vod_content": desc,
                "vod_play_from": "速读谷",
                "vod_play_url": play_url
            }]
        }

    # ==================== 核心修复：合并章节所有分页 ====================
    def _fetch_full_chapter(self, first_page_url):
        """
        获取章节完整内容，自动合并所有分页。
        直接从当前页的“下一页”链接跟随，直到进入下一章或没有下一页。
        """
        full_content = ""
        chapter_title = ""
        current_url = first_page_url
        visited = set()
        max_pages = 500  # 安全上限，防止死循环

        print(f"[分页合并] 开始获取章节: {current_url}")

        while current_url and len(visited) < max_pages:
            if current_url in visited:
                print(f"[分页合并] 检测到循环，停止: {current_url}")
                break
            visited.add(current_url)

            html = self._fetch(current_url)
            if not html:
                print(f"[分页合并] 获取页面失败: {current_url}")
                break

            soup = BeautifulSoup(html, "html.parser")

            # 提取标题（仅第一次）
            if not chapter_title:
                title_tag = soup.find("h1") or soup.find("h2") or soup.find("h3")
                if title_tag:
                    chapter_title = title_tag.get_text(strip=True)
                if not chapter_title:
                    title_match = re.search(r"<title>(.*?)</title>", html)
                    if title_match:
                        chapter_title = title_match.group(1).strip()
                if not chapter_title:
                    chapter_title = "章节正文"
                print(f"[分页合并] 章节标题: {chapter_title}")

            # 提取正文
            content = self._extract_content(html)
            if content:
                full_content += content + "\n\n"
                print(f"[分页合并] 当前页内容长度: {len(content)} 字符")
            else:
                print(f"[分页合并] 警告: 当前页未提取到正文 {current_url}")

            # 查找“下一页”链接
            # 方式1：在 .prenext 中查找
            prenext = soup.select_one(".prenext")
            next_url = None
            if prenext:
                # 遍历所有 a 标签，找文字包含“下一页”的
                for a in prenext.find_all("a"):
                    text = a.get_text(strip=True)
                    if "下一页" in text or "下页" in text:
                        href = a.get("href", "")
                        if href and href != "#":
                            next_url = self._fix_url(href)
                            break

            # 方式2：如果没找到，从所有 a 中查找
            if not next_url:
                for a in soup.find_all("a"):
                    text = a.get_text(strip=True)
                    if "下一页" in text or "下页" in text:
                        href = a.get("href", "")
                        if href and href != "#":
                            next_url = self._fix_url(href)
                            break

            if not next_url:
                print(f"[分页合并] 没有找到\"下一页\"链接，停止")
                break

            # 判断是否进入下一章（而不是同一章的分页）
            # 规则：如果下一页链接中包含“-”且数字与当前页相关，则是同一章的分页
            # 否则可能是下一章
            next_filename = next_url.split("/")[-1]
            current_filename = current_url.split("/")[-1]

            # 如果下一页是目录页，停止
            if "#dir" in next_url or "目录" in next_url:
                print(f"[分页合并] 下一页是目录页，停止")
                break

            # 提取数字
            m_cur = re.search(r'(\d+)', current_filename)
            m_next = re.search(r'(\d+)', next_filename)

            if m_cur and m_next:
                cur_num = int(m_cur.group(1))
                next_num = int(m_next.group(1))

                # 如果下一页数字比当前页大，且没有连字符，说明进入下一章
                if next_num > cur_num and '-' not in next_filename:
                    print(f"[分页合并] 检测到进入下一章 ({cur_num} -> {next_num})，停止")
                    break

                # 如果下一页数字比当前页大且带连字符，说明是同一章的分页（如 18 -> 18-2）
                if next_num > cur_num and '-' in next_filename:
                    print(f"[分页合并] 继续合并分页: {next_url}")
                    current_url = next_url
                    continue

                # 如果数字相同，说明可能是同一章的不同分页（如 18-2 -> 18-3）
                if next_num == cur_num:
                    print(f"[分页合并] 继续合并分页: {next_url}")
                    current_url = next_url
                    continue

            # 其他情况：默认继续（可能是相对路径等）
            print(f"[分页合并] 继续尝试合并: {next_url}")
            current_url = next_url

        # 清理多余空行
        full_content = re.sub(r'\n\s*\n', '\n\n', full_content)
        full_content = full_content.strip()
        print(f"[分页合并] 完成，总字符数: {len(full_content)}")

        return chapter_title, full_content

    def _extract_content(self, html):
        """从章节页提取正文（增强版）"""
        soup = BeautifulSoup(html, "html.parser")

        # 优先从 .con 中提取所有 p 标签
        con = soup.select_one(".con")
        if con:
            # 获取所有 p 标签的文本
            ps = con.find_all("p")
            if ps:
                content = "\n".join([p.get_text(strip=True) for p in ps if p.get_text(strip=True)])
                if len(content) > 50:
                    return content

        # 其他常见选择器
        for selector in ["#content", "#chapter-content", ".chapter-content", ".novel-content", ".book-content", ".txt", ".text", "#nr", "#nr1"]:
            elem = soup.select_one(selector)
            if elem:
                content = elem.get_text("\n", strip=True)
                if len(content) > 50:
                    return content

        # 从所有 div 中查找
        for div in soup.find_all("div"):
            if div.get("style") and "display:none" in div.get("style"):
                continue
            text = div.get_text(strip=True)
            if len(text) > 100 and len(text) < 20000:
                return text

        # 从 body 中提取
        body = soup.find("body")
        if body:
            for tag in body.find_all(["script", "style"]):
                tag.decompose()
            content = body.get_text("\n", strip=True)
            if len(content) > 50:
                return content

        return ""

    # ==================== playerContent ====================
    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = id if id.startswith("http") else self._fix_url(id)
            if not url:
                result_data = {'title': '错误', 'content': '无效的URL'}
                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": f"novel://{json.dumps(result_data, ensure_ascii=False)}",
                    "header": ""
                }

            title, content = self._fetch_full_chapter(url)

            if not content or len(content) < 20:
                result_data = {'title': title or '章节', 'content': '未找到章节内容'}
                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": f"novel://{json.dumps(result_data, ensure_ascii=False)}",
                    "header": ""
                }

            result_data = {'title': title or '章节', 'content': content}
            return {
                "parse": 0,
                "playUrl": "",
                "url": f"novel://{json.dumps(result_data, ensure_ascii=False)}",
                "header": ""
            }
        except Exception as e:
            print(f"playerContent error: {e}")
            result_data = {'title': '错误', 'content': f'发生异常: {str(e)}'}
            return {
                "parse": 0,
                "playUrl": "",
                "url": f"novel://{json.dumps(result_data, ensure_ascii=False)}",
                "header": ""
            }

    # ==================== 搜索 ====================
    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if pg else 1
        enc_key = urllib.parse.quote(key)

        # 搜索使用 /i/sor.aspx（根据网站源码 action="sor.aspx"）
        if pg <= 1:
            url = f"{self.host}/i/sor.aspx?key={enc_key}"
        else:
            url = f"{self.host}/i/sor.aspx?key={enc_key}&p={pg}"

        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        videos = self._extract_category_books(html)
        pagecount = self._extract_pagecount(html)
        if pagecount <= 1 and len(videos) >= 10:
            pagecount = pg + 1
        if pagecount < pg:
            pagecount = pg

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
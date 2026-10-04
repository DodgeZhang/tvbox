# -*- coding: utf-8 -*-
# 无聊自制 · HO5HO 全彩漫画爬虫（完整修复版）
# 站点: https://www.ho5ho.com/
# 修复内容：
#   1. 章节提取支持 <select> 下拉菜单
#   2. 播放页提取 ho5ho-reader-image-manifest 获取全部图片（不再只取第一页）
#   3. 本地代理解决图片防盗链（Referer）
#   4. 返回 pics:// 协议，TVBox 图集浏览器显示所有图片

import sys
import re
import json
import html as html_mod
from urllib.parse import urljoin, quote, unquote

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self.host = "https://www.ho5ho.com"
        self.session = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.host + "/",
            "Cookie": "age_verify=1;",
        }
        self.debug = True

    def _log(self, msg):
        if self.debug:
            print(f"[HO5HO] {msg}")

    def init(self, extend=""):
        if requests is None or BeautifulSoup is None:
            print("[HO5HO] 缺少依赖: requests 或 beautifulsoup4")
            return
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.verify = False
        if extend:
            try:
                cfg = json.loads(extend) if isinstance(extend, str) else extend
                if isinstance(cfg, dict):
                    host = cfg.get("host") or cfg.get("site") or ""
                    if host:
                        self.host = host.rstrip("/")
                        self.session.headers["Referer"] = self.host + "/"
            except Exception:
                pass

    def getName(self):
        return "HO5HO漫画"

    def destroy(self):
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _fetch(self, url, timeout=15):
        if not self.session:
            return None
        try:
            full_url = url if url.startswith("http") else urljoin(self.host, url)
            self._log(f"请求: {full_url}")
            r = self.session.get(full_url, timeout=timeout)
            r.encoding = "utf-8"
            if r.status_code == 200:
                return BeautifulSoup(r.text, "html.parser")
            return None
        except Exception as e:
            self._log(f"请求失败: {e}")
            return None

    def _fetch_text(self, url, timeout=15):
        if not self.session:
            return ""
        try:
            full_url = url if url.startswith("http") else urljoin(self.host, url)
            r = self.session.get(full_url, timeout=timeout)
            r.encoding = "utf-8"
            if r.status_code == 200:
                return r.text
            return ""
        except Exception as e:
            self._log(f"请求失败: {e}")
            return ""

    def _fix_url(self, url):
        if not url:
            return ""
        url = str(url).strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return urljoin(self.host, url)
        if url.startswith("http"):
            return url
        return urljoin(self.host, "/" + url)

    def _clean_text(self, text):
        if not text:
            return ""
        return re.sub(r"\s+", " ", html_mod.unescape(str(text))).strip()

    # ========== 解析漫画卡片 ==========
    def _parse_manga_cards(self, soup, limit=0):
        videos = []
        if soup is None:
            return videos

        cards = soup.select(".ho5ho-v2-card")
        if not cards:
            cards = soup.select(".page-item-detail, .item-detail")

        seen = set()
        for card in cards:
            try:
                title_elem = card.select_one(".ho5ho-v2-card-title a")
                if not title_elem:
                    title_elem = card.select_one(".post-title a")
                if not title_elem:
                    continue

                href = title_elem.get("href")
                title = self._clean_text(title_elem.get_text())

                if not href or not title:
                    continue

                vid = href
                if vid in seen:
                    continue
                seen.add(vid)

                pic = ""
                img = card.select_one(".ho5ho-v2-card-image")
                if img:
                    pic = img.get("src") or img.get("data-src") or ""
                if not pic:
                    img = card.select_one("img")
                    if img:
                        pic = img.get("src") or img.get("data-src") or ""
                pic = self._fix_url(pic)

                remark = ""
                meta = card.select_one(".ho5ho-v2-card-meta")
                if meta:
                    remark = self._clean_text(meta.get_text())
                else:
                    rating = card.select_one(".meta-item.rating")
                    if rating:
                        remark = self._clean_text(rating.get_text())

                videos.append({
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remark,
                })

                if limit > 0 and len(videos) >= limit:
                    break
            except Exception as e:
                self._log(f"解析卡片失败: {e}")
                continue

        self._log(f"解析到 {len(videos)} 个漫画")
        return videos

    # ========== 首页分类 ==========
    def homeContent(self, filter=False):
        classes = [
            {"type_id": "latest", "type_name": "最新"},
            {"type_id": "rating", "type_name": "最高评分"},
            {"type_id": "comments", "type_name": "最多评论"},
            {"type_id": "views", "type_name": "最多观看"},
        ]

        try:
            soup = self._fetch(self.host)
            if soup:
                filter_links = soup.select(".ho5ho-v2-filter-link")
                for link in filter_links:
                    href = link.get("href")
                    name = self._clean_text(link.get_text())
                    if href and name and "h漫分類" in href:
                        cid_match = re.search(r"/h漫分類/([^/]+)/", href)
                        if cid_match:
                            cid = unquote(cid_match.group(1))
                            if len(name) < 10:
                                classes.append({"type_id": f"cat_{cid}", "type_name": name})
        except Exception as e:
            self._log(f"提取分类失败: {e}")

        return {"class": classes}

    def homeVideoContent(self):
        soup = self._fetch(self.host + "/")
        videos = self._parse_manga_cards(soup, limit=30)
        return {"list": videos}

    # ========== 分类列表 ==========
    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            pg = int(pg) if pg else 1

            if tid == "latest":
                base_url = self.host + "/"
            elif tid == "rating":
                base_url = self.host + "/?m_orderby=rating"
            elif tid == "comments":
                base_url = self.host + "/?m_orderby=comments"
            elif tid == "views":
                base_url = self.host + "/?m_orderby=views"
            elif tid.startswith("cat_"):
                cat_name = tid.replace("cat_", "")
                base_url = self.host + f"/h漫分類/{quote(cat_name)}/"
            else:
                base_url = self.host + "/"

            if pg == 1:
                url = base_url
            else:
                if "?" in base_url:
                    url = base_url + "&page=" + str(pg)
                else:
                    url = base_url.rstrip("/") + "/page/" + str(pg) + "/"

            self._log(f"分类请求: {url}")
            soup = self._fetch(url)
            videos = self._parse_manga_cards(soup)

            pagecount = pg
            if soup:
                pagination = soup.select(".wp-pagenavi a")
                max_page = pg
                for a in pagination:
                    href = a.get("href", "")
                    m = re.search(r"/page/(\d+)/", href)
                    if m:
                        num = int(m.group(1))
                        if num > max_page:
                            max_page = num
                if max_page > pg:
                    pagecount = max_page
                elif len(videos) >= 20:
                    pagecount = pg + 1

            return {
                "list": videos,
                "page": pg,
                "pagecount": pagecount,
                "limit": len(videos),
                "total": pagecount * 20
            }
        except Exception as e:
            self._log(f"分类内容失败: {e}")
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

    # ========== 详情 ==========
    def detailContent(self, ids):
        try:
            vid = ids[0] if isinstance(ids, list) else ids

            if not vid.startswith("http"):
                url = self._fix_url(vid)
            else:
                url = vid

            self._log(f"详情请求: {url}")
            html = self._fetch_text(url)

            if not html:
                return {"list": []}

            soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else None

            title = ""
            if soup:
                h1 = soup.find("h1")
                if h1:
                    title = self._clean_text(h1.get_text())
            if not title:
                m = re.search(r'<title>([^<]+)</title>', html)
                if m:
                    title = self._clean_text(m.group(1)).split("|")[0].strip()
            if not title:
                m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
                if m:
                    title = self._clean_text(m.group(1))

            pic = ""
            if soup:
                og_img = soup.find("meta", property="og:image")
                if og_img:
                    pic = og_img.get("content", "")
            if not pic:
                img = soup.select_one(".summary_image img, .ho5ho-v2-card-image")
                if img:
                    pic = img.get("src") or img.get("data-src") or ""
            pic = self._fix_url(pic)

            desc = ""
            if soup:
                meta_desc = soup.find("meta", attrs={"name": "description"})
                if meta_desc:
                    desc = meta_desc.get("content", "")
            if not desc:
                desc_elem = soup.select_one(".description-summary .post-content, .summary_content .post-content")
                if desc_elem:
                    desc = self._clean_text(desc_elem.get_text())

            # ---- 改进章节提取：支持 <select> 下拉菜单 ----
            chapters = []
            if soup:
                chapter_items = soup.select(".listing-chapters_wrap .wp-manga-chapter a")
                if not chapter_items:
                    chapter_items = soup.select(".chapter-list .wp-manga-chapter a")
                if not chapter_items:
                    chapter_items = soup.select(".list-chapter .chapter a")
                if not chapter_items:
                    chapter_items = soup.select("a[href*='/中字h漫/']")
                for a in chapter_items:
                    ch_url = a.get("href")
                    ch_name = self._clean_text(a.get_text())
                    if ch_url and ch_name and "/中字h漫/" in ch_url and ch_url != vid:
                        chapters.append(f"{ch_name}${ch_url}")

            # 若未提取到，尝试从 <select> 提取
            if not chapters and soup:
                select = soup.select_one("select.single-chapter-select")
                if select:
                    for opt in select.select("option"):
                        ch_url = opt.get("data-redirect") or opt.get("value")
                        ch_name = self._clean_text(opt.get_text())
                        if ch_url and ch_name:
                            if ch_url.startswith("/"):
                                ch_url = self.host + ch_url
                            elif not ch_url.startswith("http"):
                                ch_url = self._fix_url(ch_url)
                            chapters.append(f"{ch_name}${ch_url}")

            if not chapters:
                chapters.append(f"全集${url}")

            # 去重
            seen = set()
            unique_chapters = []
            for ch in chapters:
                if ch not in seen:
                    seen.add(ch)
                    unique_chapters.append(ch)

            unique_chapters.reverse()
            play_url = "#".join(unique_chapters)

            vod = {
                "vod_id": vid,
                "vod_name": title or "未知漫画",
                "vod_pic": pic,
                "vod_content": desc,
                "vod_play_from": "HO5HO漫画",
                "vod_play_url": play_url,
            }

            self._log(f"详情解析成功: {title}, {len(unique_chapters)} 个章节")
            return {"list": [vod]}

        except Exception as e:
            self._log(f"详情解析失败: {e}")
            import traceback
            traceback.print_exc()
            return {"list": []}

    # ========== 播放（从 manifest 提取全部图片） ==========
    def playerContent(self, flag, id, vipFlags=None):
        try:
            if not id:
                return {"parse": 0, "url": "", "header": {}}

            # 如果 id 包含 $，取最后部分（实际章节URL）
            if "$" in id:
                parts = id.split("$")
                if len(parts) > 1:
                    id = parts[-1]

            # 获取章节页面HTML
            url = id if id.startswith("http") else self._fix_url(id)
            html = self._fetch_text(url)

            if not html:
                return {"parse": 0, "url": "", "msg": "无法获取章节内容"}

            img_list = []

            # ========== 策略1：从 ho5ho-reader-image-manifest 提取全部图片 ==========
            manifest_match = re.search(
                r'<script[^>]*id="ho5ho-reader-image-manifest"[^>]*>([^<]+)</script>',
                html,
                re.DOTALL | re.I
            )
            if manifest_match:
                try:
                    manifest_text = manifest_match.group(1).strip()
                    # 清理可能的 JSONP 格式
                    manifest_text = re.sub(r'^[\s\S]*?=\s*', '', manifest_text)
                    manifest_text = re.sub(r';\s*$', '', manifest_text)
                    data = json.loads(manifest_text)
                    if isinstance(data, list):
                        for img_url in data:
                            if img_url and isinstance(img_url, str):
                                # 处理 // 开头的 URL
                                if img_url.startswith("//"):
                                    img_url = "https:" + img_url
                                img_list.append(img_url)
                        self._log(f"从 manifest 提取到 {len(img_list)} 张图片")
                except Exception as e:
                    self._log(f"解析 manifest 失败: {e}")

            # ========== 策略2：如果 manifest 无效，回退到解析 img 标签 ==========
            if not img_list:
                soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else None
                if soup:
                    imgs = soup.select(".reading-content img.wp-manga-chapter-img")
                    if not imgs:
                        imgs = soup.select(".reading-content img")
                    for img in imgs:
                        src = img.get("src") or img.get("data-src") or ""
                        if src:
                            if any(x in src.lower() for x in ["logo", "icon", "avatar", "banner", "button", "ad"]):
                                continue
                            if src.startswith("data:image"):
                                continue
                            src = self._fix_url(src)
                            if src and src not in img_list:
                                img_list.append(src)

            # ========== 策略3：正则兜底 ==========
            if not img_list:
                patterns = [
                    r'<img[^>]+src="([^"]+\.(?:jpg|jpeg|png|webp|gif)[^"]*)"',
                    r'<img[^>]+data-src="([^"]+\.(?:jpg|jpeg|png|webp|gif)[^"]*)"',
                    r'(https?://[^\s"\']+\.(?:jpg|jpeg|png|webp|gif)[^\s"\']*)',
                ]
                for pat in patterns:
                    matches = re.findall(pat, html, re.I)
                    for m in matches:
                        if m and not any(x in m.lower() for x in ["logo", "icon", "avatar"]):
                            m = self._fix_url(m)
                            if m and m not in img_list:
                                img_list.append(m)

            # 去重
            unique_imgs = []
            seen = set()
            for img in img_list:
                if img not in seen:
                    seen.add(img)
                    unique_imgs.append(img)

            if not unique_imgs:
                return {"parse": 0, "url": "", "msg": "未找到图片"}

            self._log(f"最终提取到 {len(unique_imgs)} 张图片，构造 pics:// 协议")

            # 构建代理地址列表（用于防盗链）
            proxy_prefix = "http://127.0.0.1:9978/proxy?do=img&url="
            proxy_urls = [proxy_prefix + quote(img, safe='') for img in unique_imgs]
            pics_url = "pics://" + "&&".join(proxy_urls)

            return {
                "parse": 0,
                "playUrl": "",
                "url": pics_url,
                "header": ""
            }

        except Exception as e:
            self._log(f"播放解析失败: {e}")
            return {"parse": 0, "url": "", "msg": str(e)}

    # ========== 搜索 ==========
    def searchContent(self, key, quick=False, pg="1"):
        try:
            pg = int(pg) if pg else 1
            enc_key = quote(key)

            url = self.host + f"/?s={enc_key}&post_type=wp-manga"
            if pg > 1:
                url += f"&paged={pg}"

            self._log(f"搜索请求: {url}")
            soup = self._fetch(url)

            if not soup:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

            videos = self._parse_manga_cards(soup)

            if not videos:
                items = soup.select(".search-results .result-item, .page-item-detail")
                for item in items:
                    try:
                        link = item.find("a", href=re.compile(r"/中字h漫/"))
                        if not link:
                            continue
                        href = link.get("href")
                        title = self._clean_text(link.get_text())
                        img = item.find("img")
                        pic = img.get("src") or img.get("data-src") or "" if img else ""
                        pic = self._fix_url(pic)
                        videos.append({
                            "vod_id": href,
                            "vod_name": title or key,
                            "vod_pic": pic,
                            "vod_remarks": "",
                        })
                    except Exception:
                        continue

            pagecount = pg
            if soup:
                pagination = soup.select(".wp-pagenavi a")
                max_page = pg
                for a in pagination:
                    href = a.get("href", "")
                    m = re.search(r"/page/(\d+)/", href)
                    if m:
                        num = int(m.group(1))
                        if num > max_page:
                            max_page = num
                if max_page > pg:
                    pagecount = max_page
                elif len(videos) >= 20:
                    pagecount = pg + 1

            return {
                "list": videos,
                "page": pg,
                "pagecount": pagecount,
                "limit": len(videos),
                "total": pagecount * 20
            }
        except Exception as e:
            self._log(f"搜索失败: {e}")
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": 0}

    # ========== 本地代理（处理图片防盗链） ==========
    def localProxy(self, param):
        try:
            if not isinstance(param, dict):
                return None

            # 处理图片代理
            if param.get("do") == "img":
                url = param.get("url", "")
                if not url:
                    return [404, "text/plain", b"missing url"]
                # 使用 session 请求图片，带上 Referer
                r = self.session.get(
                    url,
                    headers={"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"},
                    timeout=15
                )
                if r.status_code != 200:
                    return [r.status_code, "text/plain", b""]
                return [200, r.headers.get("Content-Type", "image/jpeg"), r.content]

            # 兼容旧版：直接请求
            url = param.get("url") or param.get("pic") or ""
            if url and url.startswith("http"):
                r = self.session.get(
                    url,
                    headers={"User-Agent": self.headers["User-Agent"], "Referer": self.host + "/"},
                    timeout=15
                )
                if r.status_code == 200:
                    return [200, r.headers.get("Content-Type", "image/jpeg"), r.content]

            return [404, "text/plain", b""]
        except Exception as e:
            self._log(f"代理异常: {e}")
            return [500, "text/plain", str(e).encode()]
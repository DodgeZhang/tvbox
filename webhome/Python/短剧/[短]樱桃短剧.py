# coding=utf-8
"""
目标站: 樱桃短剧网 (gmhxt.com)
站点: https://www.gmhxt.com/
标签式分类、精准播放解析
"""
import re
import sys
import json
import urllib.parse
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.site_url = "https://www.gmhxt.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        # 从首页导航动态获取分类
        self.categories = self._fetch_categories()

    def _fetch_categories(self):
        """从首页导航栏解析标签分类"""
        try:
            resp = self.fetch(self.site_url, headers=self.headers)
            if not resp:
                return self._default_categories()
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 导航菜单：ul.stui-header__menu.type-slide li a
            nav_links = soup.select('ul.stui-header__menu.type-slide li a')
            categories = []
            seen = set()
            for a in nav_links:
                href = a.get('href', '')
                # 匹配 /ggdj/数字.html
                match = re.search(r'/ggdj/(\d+)\.html', href)
                if not match:
                    continue
                tid = match.group(1)
                name = a.get_text(strip=True)
                if not name or tid in seen or name == '首页':
                    continue
                seen.add(tid)
                categories.append({"type_id": tid, "type_name": name})
            if categories:
                return categories
        except Exception as e:
            print(f"[樱桃短剧] 获取分类失败: {e}")
        return self._default_categories()

    def _default_categories(self):
        return [
            {"type_id": "1", "type_name": "重生"},
            {"type_id": "2", "type_name": "穿越"},
            {"type_id": "3", "type_name": "爽剧"},
            {"type_id": "4", "type_name": "言情"},
            {"type_id": "5", "type_name": "都市"},
            {"type_id": "6", "type_name": "古装"},
            {"type_id": "7", "type_name": "悬疑"},
            {"type_id": "8", "type_name": "剧情"}
        ]

    def _fix_url(self, url):
        """补全相对路径"""
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if not url.startswith("http"):
            return urllib.parse.urljoin(self.site_url + "/", url)
        return url

    def _parse_video_list(self, html):
        """从HTML中解析视频列表"""
        if not html:
            return []
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        seen = set()
        items = soup.select('ul.stui-vodlist li')
        if not items:
            items = soup.select('.stui-vodlist li')
        for item in items:
            link = item.select_one('a.stui-vodlist__thumb')
            if not link:
                continue
            href = link.get('href', '')
            # 提取视频ID（从 /guaguaduanju/数字.html 中提取）
            vod_id = re.search(r'/(\d+)\.html', href)
            if not vod_id:
                continue
            vid = vod_id.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            # 标题
            title = link.get('title', '') or link.get('alt', '')
            if not title:
                title_elem = item.select_one('.stui-vodlist__detail h4 a')
                if title_elem:
                    title = title_elem.get('title', '') or title_elem.get_text(strip=True)
            if not title:
                continue
            # 封面图
            pic = link.get('data-original', '')
            if not pic:
                style = link.get('style', '')
                bg_match = re.search(r'url\(([^)]+)\)', style)
                if bg_match:
                    pic = bg_match.group(1)
            # 备注（如“全集完结”）
            remark = ''
            remark_elem = item.select_one('.pic-text')
            if remark_elem:
                remark = remark_elem.get_text(strip=True)
            results.append({
                "vod_id": vid,
                "vod_name": title.strip(),
                "vod_pic": self._fix_url(pic),
                "vod_remarks": remark
            })
        return results

    # ================= 首页推荐 =================
    def homeContent(self, filter):
        url = self.site_url + "/"
        resp = self.fetch(url, headers=self.headers)
        video_list = []
        if resp:
            video_list = self._parse_video_list(resp.text)
            video_list = video_list[:30]
        return {"class": self.categories, "list": video_list, "filters": {}}

    def homeVideoContent(self):
        return self.homeContent(False)

    # ================= 分类列表 =================
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        # 分类URL: /ggdj/{tid}.html，分页添加 ?page=page
        url = f"{self.site_url}/ggdj/{tid}.html"
        if page > 1:
            url += f"?page={page}"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            # 尝试备用格式：/ggdj/{tid}-{page}.html
            alt_url = f"{self.site_url}/ggdj/{tid}-{page}.html"
            resp = self.fetch(alt_url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}

        video_list = self._parse_video_list(resp.text)
        # 分页信息
        pagecount = page
        soup = BeautifulSoup(resp.text, 'html.parser')
        pagination = soup.select('.stui-page a')
        if pagination:
            for a in pagination:
                text = a.get_text(strip=True)
                if text.isdigit():
                    pagecount = max(pagecount, int(text))
        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": len(video_list) * pagecount
        }

    # ================= 详情页 =================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        # 详情页URL格式：/guaguaduanju/数字.html
        url = f"{self.site_url}/guaguaduanju/{vod_id}.html"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": []}

        soup = BeautifulSoup(resp.text, 'html.parser')
        # 标题
        title_elem = soup.select_one('.stui-content__title h1') or soup.select_one('h1')
        vod_name = title_elem.get_text(strip=True) if title_elem else vod_id
        # 封面图
        vod_pic = ''
        img_elem = soup.select_one('.stui-content__thumb img')
        if img_elem:
            vod_pic = img_elem.get('data-original', '') or img_elem.get('src', '')
            vod_pic = self._fix_url(vod_pic)
        # 简介
        vod_content = ''
        content_elem = soup.select_one('.stui-content__desc') or soup.select_one('.stui-content__detail .desc')
        if content_elem:
            vod_content = content_elem.get_text(' ', strip=True)

        # ===== 播放线路解析 =====
        play_from_list = []
        play_url_list = []
        # 查找播放列表块
        play_blocks = soup.select('.stui-play__list')
        if not play_blocks:
            play_blocks = soup.select('.stui-content__playlist')
        if not play_blocks:
            play_blocks = soup.select('ul.playlist')

        for idx, block in enumerate(play_blocks):
            line_name = f"线路{idx+1}"
            name_elem = block.select_one('.stui-play__list-title')
            if name_elem:
                line_name = name_elem.get_text(strip=True)
            episodes = []
            for a in block.select('a'):
                href = a.get('href', '')
                if not href or 'javascript:' in href:
                    continue
                ep_name = a.get_text(strip=True) or f"第{len(episodes)+1}集"
                full_url = self._fix_url(href)
                episodes.append(f"{ep_name}${full_url}")
            if episodes:
                play_from_list.append(line_name)
                play_url_list.append('#'.join(episodes))

        # 如果未解析到线路，尝试从所有播放链接中提取
        if not play_url_list:
            all_links = soup.select('a[href*="/play/"]')
            if all_links:
                episodes = []
                for a in all_links:
                    href = a.get('href', '')
                    ep_name = a.get_text(strip=True) or f"第{len(episodes)+1}集"
                    full_url = self._fix_url(href)
                    episodes.append(f"{ep_name}${full_url}")
                if episodes:
                    play_from_list.append('默认线路')
                    play_url_list.append('#'.join(episodes))

        vod_play_from = '$$$'.join(play_from_list) if play_from_list else '默认源'
        vod_play_url = '$$$'.join(play_url_list) if play_url_list else f"播放${vod_id}"

        result = [{
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_actor": "",
            "vod_director": "",
            "vod_area": "",
            "vod_year": "",
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    # ================= 搜索 =================
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)
        url = f"{self.site_url}/search.php?searchword={encoded_key}"
        if page > 1:
            url += f"&page={page}"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1}
        video_list = self._parse_video_list(resp.text)
        return {"list": video_list, "page": page, "pagecount": 1}

    # ================= 播放解析 =================
    def playerContent(self, flag, id, vipFlags):
        """解析播放地址，提取直链"""
        play_url = self._fix_url(id)

        resp = self.fetch(play_url, headers=self.headers)
        if not resp:
            return {"parse": 1, "url": play_url, "header": self.headers}

        html = resp.text

        # 1. 查找 iframe 嵌套
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe:
            iframe_url = self._fix_url(iframe.group(1))
            iframe_resp = self.fetch(iframe_url, headers=self.headers)
            if iframe_resp:
                iframe_html = iframe_resp.text
                # 在 iframe 中查找 video 标签或 m3u8
                video_src = re.search(r'<video[^>]+src="([^"]+)"', iframe_html)
                if video_src:
                    return {"parse": 0, "url": video_src.group(1), "header": self.headers}
                m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', iframe_html)
                if m3u8:
                    return {"parse": 0, "url": m3u8.group(1), "header": self.headers}
                # 可能再有嵌套 iframe
                nested = re.search(r'<iframe[^>]+src="([^"]+)"', iframe_html)
                if nested:
                    nested_url = self._fix_url(nested.group(1))
                    nested_resp = self.fetch(nested_url, headers=self.headers)
                    if nested_resp:
                        nested_html = nested_resp.text
                        m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', nested_html)
                        if m3u8:
                            return {"parse": 0, "url": m3u8.group(1), "header": self.headers}

        # 2. 直接查找 video 标签
        video_src = re.search(r'<video[^>]+src="([^"]+)"', html)
        if video_src:
            return {"parse": 0, "url": video_src.group(1), "header": self.headers}

        # 3. 查找 player_aaaa 变量（海洋CMS加密播放地址）
        marker = "var player_aaaa="
        if marker in html:
            try:
                data_str = html.split(marker, 1)[1].split('\n', 1)[0].strip()
                if data_str.endswith(';'):
                    data_str = data_str[:-1]
                data = json.loads(data_str)
                if data.get('url'):
                    return {"parse": 0, "url": data['url'], "header": self.headers}
            except Exception:
                pass

        # 4. 直接匹配 m3u8 链接
        m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
        if m3u8:
            return {"parse": 0, "url": m3u8.group(1), "header": self.headers}

        # 5. 兜底：交给客户端解析
        return {"parse": 1, "url": play_url, "header": self.headers}
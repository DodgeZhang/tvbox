# coding=utf-8
"""
目标站: 番茄短剧 (m.0736tuan.com)
动态分类（标签式）、精准播放解析
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
        self.site_url = "https://m.0736tuan.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        # 动态获取分类（从导航栏解析）
        self.categories = self._fetch_categories()

    def _fetch_categories(self):
        """从首页导航栏解析分类标签"""
        try:
            resp = self.fetch(self.site_url, headers=self.headers)
            if not resp:
                return self._default_categories()
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 导航菜单：ul.type-slide li a
            nav_links = soup.select('ul.type-slide li a')
            categories = []
            seen = set()
            for a in nav_links:
                href = a.get('href', '')
                match = re.search(r'/fqdj/(\d+)\.html', href)
                if not match:
                    continue
                tid = match.group(1)
                name = a.get_text(strip=True)
                if not name or tid in seen:
                    continue
                seen.add(tid)
                categories.append({"type_id": tid, "type_name": name})
            if categories:
                return categories
        except Exception as e:
            print(f"[0736] 获取分类失败: {e}")
        return self._default_categories()

    def _default_categories(self):
        # 若获取失败，使用硬编码
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

    # ================= 首页推荐（混合列表） =================
    def homeContent(self, filter):
        url = self.site_url + "/"
        resp = self.fetch(url, headers=self.headers)
        video_list = []
        if resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 首页所有视频卡片都在 ul.stui-vodlist li 中（多个板块）
            items = soup.select('ul.stui-vodlist li')
            for item in items:
                link = item.select_one('a.stui-vodlist__thumb')
                if not link:
                    continue
                href = link.get('href', '')
                vod_id = re.search(r'/(\d+)\.html', href)
                if not vod_id:
                    continue
                vod_id = vod_id.group(1)
                title = link.get('title', '') or link.get('alt', '')
                if not title:
                    title_elem = item.select_one('.stui-vodlist__detail h4 a')
                    if title_elem:
                        title = title_elem.get('title', '') or title_elem.get_text(strip=True)
                if not title:
                    continue
                pic = link.get('data-original', '')
                if not pic:
                    style = link.get('style', '')
                    bg_match = re.search(r'url\(([^)]+)\)', style)
                    if bg_match:
                        pic = bg_match.group(1)
                if pic and not pic.startswith('http'):
                    pic = 'https:' + pic if pic.startswith('//') else self.site_url + pic
                remark = ''
                remark_elem = item.select_one('.pic-text')
                if remark_elem:
                    remark = remark_elem.get_text(strip=True)
                video_list.append({
                    "vod_id": vod_id,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remark
                })
                if len(video_list) >= 30:
                    break
        return {"class": self.categories, "list": video_list, "filters": {}}

    def homeVideoContent(self):
        return self.homeContent(False)

    # ================= 分类列表（标签分类） =================
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        # 分类URL: /fqdj/{tid}.html，分页添加 ?page=page
        url = f"{self.site_url}/fqdj/{tid}.html"
        if page > 1:
            url += f"?page={page}"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            # 尝试另一种分页格式：/fqdj/{tid}-{page}.html
            alt_url = f"{self.site_url}/fqdj/{tid}-{page}.html"
            resp = self.fetch(alt_url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}

        soup = BeautifulSoup(resp.text, 'html.parser')
        video_list = []
        items = soup.select('ul.stui-vodlist li')
        if not items:
            items = soup.select('.stui-vodlist li')
        for item in items:
            link = item.select_one('a.stui-vodlist__thumb')
            if not link:
                continue
            href = link.get('href', '')
            vod_id = re.search(r'/(\d+)\.html', href)
            if not vod_id:
                continue
            vod_id = vod_id.group(1)
            title = link.get('title', '') or link.get('alt', '')
            if not title:
                title_elem = item.select_one('.stui-vodlist__detail h4 a')
                if title_elem:
                    title = title_elem.get('title', '') or title_elem.get_text(strip=True)
            if not title:
                continue
            pic = link.get('data-original', '')
            if not pic:
                style = link.get('style', '')
                bg_match = re.search(r'url\(([^)]+)\)', style)
                if bg_match:
                    pic = bg_match.group(1)
            if pic and not pic.startswith('http'):
                pic = 'https:' + pic if pic.startswith('//') else self.site_url + pic
            remark = ''
            remark_elem = item.select_one('.pic-text')
            if remark_elem:
                remark = remark_elem.get_text(strip=True)
            video_list.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark
            })
        # 分页信息（简单处理）
        pagecount = page
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
        url = f"{self.site_url}/fanqieduanju/{vod_id}.html"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": []}

        soup = BeautifulSoup(resp.text, 'html.parser')
        title_elem = soup.select_one('.stui-content__title h1') or soup.select_one('h1')
        vod_name = title_elem.get_text(strip=True) if title_elem else vod_id
        vod_pic = ''
        img_elem = soup.select_one('.stui-content__thumb img')
        if img_elem:
            vod_pic = img_elem.get('data-original', '') or img_elem.get('src', '')
            if vod_pic and not vod_pic.startswith('http'):
                vod_pic = 'https:' + vod_pic if vod_pic.startswith('//') else self.site_url + vod_pic
        vod_content = ''
        content_elem = soup.select_one('.stui-content__desc') or soup.select_one('.stui-content__detail .desc')
        if content_elem:
            vod_content = content_elem.get_text(' ', strip=True)

        # 解析播放线路
        play_from_list = []
        play_url_list = []
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
                if not href.startswith('http'):
                    href = self.site_url + href if href.startswith('/') else self.site_url + '/' + href
                episodes.append(f"{ep_name}${href}")
            if episodes:
                play_from_list.append(line_name)
                play_url_list.append('#'.join(episodes))
        if not play_url_list:
            direct_links = soup.select('a[href*="/play/"]')
            if direct_links:
                episodes = []
                for a in direct_links:
                    href = a.get('href', '')
                    ep_name = a.get_text(strip=True) or f"第{len(episodes)+1}集"
                    if not href.startswith('http'):
                        href = self.site_url + href if href.startswith('/') else self.site_url + '/' + href
                    episodes.append(f"{ep_name}${href}")
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
        soup = BeautifulSoup(resp.text, 'html.parser')
        video_list = []
        items = soup.select('ul.stui-vodlist li')
        for item in items:
            link = item.select_one('a.stui-vodlist__thumb')
            if not link:
                continue
            href = link.get('href', '')
            vod_id = re.search(r'/(\d+)\.html', href)
            if not vod_id:
                continue
            vod_id = vod_id.group(1)
            title = link.get('title', '') or link.get('alt', '')
            if not title:
                title_elem = item.select_one('.stui-vodlist__detail h4 a')
                if title_elem:
                    title = title_elem.get('title', '') or title_elem.get_text(strip=True)
            if not title:
                continue
            pic = link.get('data-original', '')
            if not pic:
                style = link.get('style', '')
                bg_match = re.search(r'url\(([^)]+)\)', style)
                if bg_match:
                    pic = bg_match.group(1)
            if pic and not pic.startswith('http'):
                pic = 'https:' + pic if pic.startswith('//') else self.site_url + pic
            remark = ''
            remark_elem = item.select_one('.pic-text')
            if remark_elem:
                remark = remark_elem.get_text(strip=True)
            video_list.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark
            })
        return {"list": video_list, "page": page, "pagecount": 1}

    # ================= 播放解析（直链提取） =================
    def playerContent(self, flag, id, vipFlags):
        if not id.startswith('http'):
            if id.startswith('/'):
                play_url = self.site_url + id
            else:
                play_url = f"{self.site_url}/fanqieduanju/{id}.html"
        else:
            play_url = id

        resp = self.fetch(play_url, headers=self.headers)
        if not resp:
            return {"parse": 1, "url": play_url, "header": self.headers}

        html = resp.text
        # 1. iframe
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe:
            iframe_url = iframe.group(1)
            if not iframe_url.startswith('http'):
                iframe_url = self.site_url + iframe_url if iframe_url.startswith('/') else self.site_url + '/' + iframe_url
            iframe_resp = self.fetch(iframe_url, headers=self.headers)
            if iframe_resp:
                iframe_html = iframe_resp.text
                video_src = re.search(r'<video[^>]+src="([^"]+)"', iframe_html)
                if video_src:
                    return {"parse": 0, "url": video_src.group(1), "header": self.headers}
                m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', iframe_html)
                if m3u8:
                    return {"parse": 0, "url": m3u8.group(1), "header": self.headers}
                nested = re.search(r'<iframe[^>]+src="([^"]+)"', iframe_html)
                if nested:
                    nested_url = nested.group(1)
                    if not nested_url.startswith('http'):
                        nested_url = self.site_url + nested_url if nested_url.startswith('/') else self.site_url + '/' + nested_url
                    nested_resp = self.fetch(nested_url, headers=self.headers)
                    if nested_resp:
                        nested_html = nested_resp.text
                        m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', nested_html)
                        if m3u8:
                            return {"parse": 0, "url": m3u8.group(1), "header": self.headers}

        # 2. video 标签
        video_src = re.search(r'<video[^>]+src="([^"]+)"', html)
        if video_src:
            return {"parse": 0, "url": video_src.group(1), "header": self.headers}

        # 3. player_aaaa 变量
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

        # 4. 直接匹配 m3u8
        m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
        if m3u8:
            return {"parse": 0, "url": m3u8.group(1), "header": self.headers}

        return {"parse": 1, "url": play_url, "header": self.headers}
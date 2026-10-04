# coding=utf-8
"""
目标站: 555电影 (555dy3.com)
站点: https://555dy3.com/
海洋CMS架构 - 修复播放解析（仅增强 playerContent）
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
        self.site_url = "https://555dy3.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        self.categories = self._fetch_categories()

    def _fetch_categories(self):
        try:
            resp = self.fetch(self.site_url, headers=self.headers)
            if not resp:
                return self._default_categories()
            soup = BeautifulSoup(resp.text, 'html.parser')
            nav_links = soup.select('.navbar-items .navbar-item a.links, .navbar-items a.links')
            categories = []
            seen = set()
            exclude = ['首页', 'Netflix', '追剧周表', '今日更新', '专题列表', '排行榜', '回家地址', '午夜蓝光', '留言求片', 'APP']
            for a in nav_links:
                href = a.get('href', '')
                match = re.search(r'/vodtype/(\d+)\.html', href)
                if not match:
                    continue
                tid = match.group(1)
                name = a.get_text(strip=True)
                if not name or tid in seen or name in exclude:
                    continue
                seen.add(tid)
                categories.append({"type_id": tid, "type_name": name})
            if categories:
                return categories
        except Exception as e:
            print(f"[555电影] 获取分类失败: {e}")
        return self._default_categories()

    def _default_categories(self):
        return [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "连续剧"},
            {"type_id": "126", "type_name": "擦边短剧"},
            {"type_id": "4", "type_name": "动漫"},
            {"type_id": "3", "type_name": "综艺纪录"},
        ]

    def _fix_url(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if not url.startswith("http"):
            return urllib.parse.urljoin(self.site_url + "/", url)
        return url

    def _parse_video_list(self, html):
        if not html:
            return []
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        seen = set()
        for a in soup.select('a[href*="/voddetail/"]'):
            href = a.get('href', '')
            vod_id = re.search(r'/voddetail/(\d+)\.html', href)
            if not vod_id:
                continue
            vid = vod_id.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            title = a.get('title', '')
            if not title:
                title = a.get_text(strip=True)
            if not title:
                continue
            img = a.select_one('img')
            pic = img.get('data-original') or img.get('src') if img else ''
            if not pic:
                parent = a.parent
                for _ in range(3):
                    if parent and parent.get('class'):
                        if any(c in ['module-item', 'vod-item', 'video-item', 'item', 'public-list-box'] for c in parent.get('class', [])):
                            img_in_parent = parent.select_one('img')
                            if img_in_parent:
                                pic = img_in_parent.get('data-original') or img_in_parent.get('src')
                                break
                    parent = parent.parent if parent else None
            if not pic:
                style = a.get('style', '')
                bg = re.search(r'url\(([^)]+)\)', style)
                if bg:
                    pic = bg.group(1).strip('"').strip("'")
            remark = ''
            parent = a.parent
            for _ in range(3):
                if parent and parent.get('class'):
                    if any(c in ['module-item', 'vod-item', 'video-item', 'item', 'public-list-box'] for c in parent.get('class', [])):
                        note = parent.select_one('.module-item-note, .module-item-text, .vod-remarks, .remarks, .pic-text, .desc')
                        if note:
                            remark = note.get_text(strip=True)
                            break
                parent = parent.parent if parent else None
            results.append({
                "vod_id": vid,
                "vod_name": title.strip(),
                "vod_pic": self._fix_url(pic),
                "vod_remarks": remark
            })
        return results

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

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        urls_to_try = []
        base_urls = [
            f"{self.site_url}/vodtype/{tid}",
            f"{self.site_url}/vodshow/{tid}",
            f"{self.site_url}/vodlist/{tid}",
        ]
        for base in base_urls:
            if page == 1:
                urls_to_try.append(base + ".html")
            else:
                urls_to_try.append(base + f"-{page}.html")
                urls_to_try.append(base + f".html?page={page}")
        html_text = ""
        for url in urls_to_try:
            resp = self.fetch(url, headers=self.headers)
            if resp:
                html_text = resp.text
                break
        if not html_text:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}
        video_list = self._parse_video_list(html_text)
        pagecount = page
        soup = BeautifulSoup(html_text, 'html.parser')
        pagination = soup.select('.page a, .pagination a, .page-link')
        if pagination:
            nums = []
            for a in pagination:
                text = a.get_text(strip=True)
                if text.isdigit():
                    nums.append(int(text))
            if nums:
                pagecount = max(nums)
        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": len(video_list) * pagecount
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        url = f"{self.site_url}/voddetail/{vod_id}.html"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": []}
        soup = BeautifulSoup(resp.text, 'html.parser')
        title_elem = soup.select_one('h1') or soup.select_one('.vod-title')
        vod_name = title_elem.get_text(strip=True) if title_elem else vod_id
        vod_pic = ''
        img_elem = soup.select_one('.vod-pic img, .detail-pic img, .cover img')
        if img_elem:
            vod_pic = img_elem.get('data-original') or img_elem.get('src')
            vod_pic = self._fix_url(vod_pic)
        vod_content = ''
        content_elem = soup.select_one('.vod-content, .detail-content, .desc')
        if content_elem:
            vod_content = content_elem.get_text(' ', strip=True)
        vod_actor = ''
        actor_elem = soup.select_one('.vod-actor, .actor')
        if actor_elem:
            vod_actor = actor_elem.get_text(strip=True).replace('主演：', '').strip()
        vod_director = ''
        director_elem = soup.select_one('.vod-director, .director')
        if director_elem:
            vod_director = director_elem.get_text(strip=True).replace('导演：', '').strip()
        vod_year = ''
        year_elem = soup.select_one('.vod-year, .year')
        if year_elem:
            vod_year = year_elem.get_text(strip=True).replace('年份：', '').strip()

        play_from_list = []
        play_url_list = []
        play_blocks = soup.select('.play-list, .vod-play-list, .episode-list, .playlist, ul.playlist')
        if not play_blocks:
            play_blocks = soup.select('.stui-play__list')
        for idx, block in enumerate(play_blocks):
            line_name = f"线路{idx+1}"
            name_elem = block.select_one('.play-title, .line-name, .playlist-title')
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
        if not play_url_list:
            all_links = soup.select('a[href*="/vodplay/"]')
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
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_area": "",
            "vod_year": vod_year,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)
        url = f"{self.site_url}/vodsearch/-------------.html?wd={encoded_key}"
        if page > 1:
            url += f"&page={page}"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1}
        video_list = self._parse_video_list(resp.text)
        return {"list": video_list, "page": page, "pagecount": 1}

    # ================= 增强播放解析（仅此函数修改） =================
    def playerContent(self, flag, id, vipFlags):
        """
        递归解析播放地址，支持：
        - player_aaaa.link 跳转
        - iframe 深度递归
        - video / source 标签提取
        - 直接匹配 m3u8 / mp4
        - 最大递归深度 8
        """
        play_url = self._fix_url(id)

        # 如果已经是直链，直接返回
        if re.search(r'\.(m3u8|mp4|flv)(\?|$)', play_url, re.I):
            return {"parse": 0, "url": play_url, "header": self.headers}

        headers = dict(self.headers)
        headers['Referer'] = self.site_url + '/'
        max_depth = 8

        def _extract(url, depth):
            if depth > max_depth:
                return None
            # 如果已经是直链，直接返回
            if re.search(r'\.(m3u8|mp4|flv)(\?|$)', url, re.I):
                return url

            resp = self.fetch(url, headers=headers)
            if not resp:
                return None
            html = resp.text

            # 1. 提取 player_aaaa 变量
            match = re.search(r'var\s+player_aaaa\s*=\s*({[^;]+});', html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    # 优先使用 link（跳转页）
                    link = data.get('link', '')
                    if link:
                        next_url = self._fix_url(link)
                        if next_url != url:
                            return _extract(next_url, depth + 1)
                    # 其次使用 url（可能是加密的，但有时直接是直链）
                    url_val = data.get('url', '')
                    if url_val:
                        # 如果 url 是直链，直接返回
                        if re.search(r'\.(m3u8|mp4|flv)', url_val, re.I):
                            return url_val
                        # 否则尝试访问 url
                        next_url = self._fix_url(url_val)
                        if next_url != url:
                            return _extract(next_url, depth + 1)
                except Exception as e:
                    print(f"[555电影] 解析 player_aaaa 失败: {e}")

            # 2. 查找 iframe（递归）
            iframe = re.search(r'<iframe[^>]+src="([^"]+)"', html)
            if iframe:
                iframe_url = self._fix_url(iframe.group(1))
                if iframe_url != url:
                    return _extract(iframe_url, depth + 1)

            # 3. 查找 video 标签
            video_src = re.search(r'<video[^>]+src="([^"]+)"', html)
            if video_src:
                return video_src.group(1)

            # 4. 查找 source 标签
            source_src = re.search(r'<source[^>]+src="([^"]+)"', html)
            if source_src:
                return source_src.group(1)

            # 5. 直接匹配 m3u8
            m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
            if m3u8:
                return m3u8.group(1)

            # 6. 其他常见播放变量
            var_patterns = [
                r'var\s+playurl\s*=\s*["\']([^"\']+)["\']',
                r'var\s+url\s*=\s*["\']([^"\']+)["\']',
                r'var\s+video\s*=\s*["\']([^"\']+)["\']',
                r'var\s+src\s*=\s*["\']([^"\']+)["\']',
            ]
            for pat in var_patterns:
                match = re.search(pat, html, re.I)
                if match:
                    p = match.group(1)
                    if re.search(r'\.(m3u8|mp4|flv)', p, re.I):
                        return p

            # 7. 如果页面中还有 <a> 指向 /vodplay/，尝试递归（防止遗漏）
            next_links = re.findall(r'<a[^>]+href="([^"]*\/vodplay\/[^"]+)"', html)
            for nl in next_links:
                next_url = self._fix_url(nl)
                if next_url != url:
                    result = _extract(next_url, depth + 1)
                    if result:
                        return result

            return None

        final_url = _extract(play_url, 0)

        if final_url:
            final_url = self._fix_url(final_url)
            if re.search(r'\.(m3u8|mp4|flv)', final_url, re.I):
                return {"parse": 0, "url": final_url, "header": headers}
            else:
                # 可能是中间页，再试一次
                return self.playerContent(flag, final_url, vipFlags)

        # 兜底：交给客户端解析
        return {"parse": 1, "url": play_url, "header": headers}
# coding=utf-8
"""
目标站: 全能短剧 (www.semtong.com)
SeaCMS (海洋CMS) 架构，动态分类、精准播放解析
modify: 推荐页(OK壳子)和白盒首页站点推荐海报使用剧情类数据，剧情分类保留
modify: 抄七猫改.py 搜索触发逻辑，兼容白盒+OK壳
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
        self.site_url = "https://www.semtong.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        self.categories = [
            {"type_id": "1", "type_name": "重生"},
            {"type_id": "2", "type_name": "穿越"},
            {"type_id": "3", "type_name": "爽剧"},
            {"type_id": "4", "type_name": "言情"},
            {"type_id": "5", "type_name": "都市"},
            {"type_id": "6", "type_name": "古装"},
            {"type_id": "7", "type_name": "悬疑"},
            {"type_id": "8", "type_name": "剧情"}
        ]
        # 推荐页固定拉取的分类 ID（剧情=8）
        self.recommend_tid = "8"

    # =====================
    # 抄七猫改.py：msearch 判断 + 关键词提取
    # =====================
    def is_msearch_id(self, vid):
        return isinstance(vid, str) and vid.startswith("msearch:")

    def msearch_keyword(self, vid):
        if self.is_msearch_id(vid):
            return vid[len("msearch:"):].strip()
        return str(vid)

    # 搜索拿真实数字 ID（通用方法）
    def _resolve_msearch(self, raw_id):
        if not self.is_msearch_id(raw_id):
            return str(raw_id)
        kw = self.msearch_keyword(raw_id)
        url = f"{self.site_url}/search.php?searchword={urllib.parse.quote(kw)}"
        try:
            resp = self.fetch(url, headers=self.headers, timeout=5)
            if resp:
                soup = BeautifulSoup(resp.text, 'html.parser')
                a = soup.select_one('a[href*="/duanju/"]')
                if a:
                    m = re.search(r'/duanju/(\d+)\.html', a.get('href', ''))
                    if m:
                        return m.group(1)
        except:
            pass
        return None

    def _parse_video_list(self, soup, max_count=0):
        """通用视频列表解析器（原版逻辑，仅 vod_id 改为 msearch:片名）"""
        video_list = []
        items = soup.select('li.fed-list-item') or soup.select('.fed-list-info li')
        if not items:
            items = soup.select('.fed-list-pics')
            for link in items:
                href = link.get('href', '')
                vod_id = re.search(r'/duanju/(\d+)\.html', href)
                if not vod_id:
                    continue
                title = link.get('title', '')
                pic = link.get('data-original', '')
                remark_elem = link.select_one('.fed-list-remarks')
                remark = remark_elem.get_text(strip=True) if remark_elem else ''
                video_list.append({
                    "vod_id": f"msearch:{title}" if title else vod_id.group(1),
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remark
                })
            return video_list

        for item in items:
            link = item.select_one('a.fed-list-pics') or item.select_one('a[href*="/duanju/"]')
            if not link:
                continue
            href = link.get('href', '')
            vod_id = re.search(r'/duanju/(\d+)\.html', href)
            if not vod_id:
                continue
            title = link.get('title', '')
            if not title:
                title_elem = item.select_one('.fed-list-title a') or item.select_one('a[title]')
                if title_elem:
                    title = title_elem.get('title', '') or title_elem.get_text(strip=True)
            if not title:
                continue
            pic = link.get('data-original', '')
            if not pic:
                img = link.select_one('img')
                if img:
                    pic = img.get('data-original', '') or img.get('src', '')
            remark = ''
            remark_elem = link.select_one('.fed-list-remarks')
            if remark_elem:
                remark = remark_elem.get_text(strip=True)
            video_list.append({
                "vod_id": f"msearch:{title}",
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark
            })
            if max_count > 0 and len(video_list) >= max_count:
                break
        return video_list

    def homeContent(self, filter):
        # 推荐页拉取剧情分类数据（原版逻辑保留）
        url = f"{self.site_url}/quanneng/{self.recommend_tid}.html"
        resp = self.fetch(url, headers=self.headers)
        video_list = []
        if resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            video_list = self._parse_video_list(soup, max_count=36)
        return {"class": self.categories, "list": video_list, "filters": {}}

    def homeVideoContent(self):
        return self.homeContent(False)

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if page <= 1:
            url = f"{self.site_url}/quanneng/{tid}.html"
        else:
            url = f"{self.site_url}/quanneng/{tid}_{page}.html"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 30, "total": 0}

        soup = BeautifulSoup(resp.text, 'html.parser')
        video_list = self._parse_video_list(soup)

        pagecount = page
        pagination = soup.select('.fed-page-info a') or soup.select('.fed-page a')
        for a in pagination:
            text = a.get_text(strip=True)
            if text.isdigit():
                pagecount = max(pagecount, int(text))
        total_text = soup.get_text()
        total_match = re.search(r'共\s*(\d+)\s*个影片', total_text)
        total = 0
        if total_match:
            total = int(total_match.group(1))
            pagecount = max(pagecount, (total + 29) // 30)
        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 30,
            "total": total if total else len(video_list) * pagecount
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        raw_id = ids[0]

        # ✅ 抄七猫改.py：识别 msearch → 搜索拿真实 ID
        if self.is_msearch_id(raw_id):
            real_id = self._resolve_msearch(raw_id)
            if not real_id:
                return {"list": []}
            vod_id = real_id
        else:
            vod_id = str(raw_id)

        url = f"{self.site_url}/duanju/{vod_id}.html"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": []}

        soup = BeautifulSoup(resp.text, 'html.parser')

        vod_name = vod_id
        title_elem = soup.select_one('.fed-deta-content h1 a') or soup.select_one('h1 a') or soup.select_one('h1')
        if title_elem:
            vod_name = title_elem.get('title', '') or title_elem.get_text(strip=True)
        if vod_name == vod_id:
            og_title = soup.select_one('meta[property="og:title"]')
            if og_title:
                vod_name = og_title.get('content', vod_id)

        vod_pic = ''
        og_image = soup.select_one('meta[property="og:image"]')
        if og_image:
            vod_pic = og_image.get('content', '')
        if not vod_pic:
            img_elem = soup.select_one('.fed-deta-images img') or soup.select_one('.fed-list-pics img')
            if img_elem:
                vod_pic = img_elem.get('data-original', '') or img_elem.get('src', '')

        vod_content = ''
        desc_elem = soup.select_one('.fed-deta-content .fed-part-esan') or soup.select_one('.fed-part-esan')
        if desc_elem:
            vod_content = desc_elem.get_text(' ', strip=True)
        if not vod_content:
            og_desc = soup.select_one('meta[property="og:description"]')
            if og_desc:
                vod_content = og_desc.get('content', '')

        vod_actor = ''
        vod_director = ''
        vod_area = ''
        vod_year = ''

        info_items = soup.select('.fed-deta-content li') or soup.select('dl.fed-deta-info dd li')
        for li in info_items:
            text = li.get_text(strip=True)
            if '主演' in text:
                vod_actor = text.split('：', 1)[-1].strip() if '：' in text else text.replace('主演', '').strip()
            elif '导演' in text:
                vod_director = text.split('：', 1)[-1].strip() if '：' in text else text.replace('导演', '').strip()
            elif '地区' in text:
                vod_area = text.split('：', 1)[-1].strip() if '：' in text else text.replace('地区', '').strip()
            elif '年份' in text:
                vod_year = text.split('：', 1)[-1].strip() if '：' in text else text.replace('年份', '').strip()

        if not vod_area:
            og_area = soup.select_one('meta[property="og:video:area"]')
            if og_area:
                vod_area = og_area.get('content', '')
        if not vod_director:
            og_dir = soup.select_one('meta[property="og:video:director"]')
            if og_dir:
                vod_director = og_dir.get('content', '')
        if not vod_actor:
            og_actor = soup.select_one('meta[property="og:video:actor"]')
            if og_actor:
                vod_actor = og_actor.get('content', '')

        play_from_list = []
        play_url_list = []

        playlist_blocks = soup.select('.fed-play-item') or soup.select('.fed-tabs-item')
        if not playlist_blocks:
            tab_links = soup.select('.fed-tabs a')
            tab_names = {}
            for a in tab_links:
                href = a.get('href', '')
                name = a.get_text(strip=True)
                if name and name != '↑↓ 排序' and '#playlist' in href:
                    tab_names[href.split('#')[-1]] = name

            if tab_names:
                for anchor, line_name in tab_names.items():
                    block = soup.select_one(f'#{anchor}') or soup.select_one(f'[id="{anchor}"]')
                    if block:
                        episodes = []
                        for a in block.select('a'):
                            href = a.get('href', '')
                            if not href or 'javascript:' in href or href.startswith('#'):
                                continue
                            ep_name = a.get_text(strip=True)
                            if not ep_name:
                                continue
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
                    ep_name = a.get_text(strip=True)
                    if not href or not ep_name:
                        continue
                    if not href.startswith('http'):
                        href = self.site_url + href if href.startswith('/') else self.site_url + '/' + href
                    episodes.append(f"{ep_name}${href}")
                if episodes:
                    play_from_list.append('默认线路')
                    play_url_list.append('#'.join(episodes))

        vod_play_from = '$$$'.join(play_from_list) if play_from_list else '默认源'
        vod_play_url = '$$$'.join(play_url_list) if play_url_list else f"播放${vod_id}"

        # ✅ 返回真实数字 ID（防白盒循环跳搜索页）
        result = [{
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_area": vod_area,
            "vod_year": vod_year,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)
        url = f"{self.site_url}/search.php?searchword={encoded_key}"
        if page > 1:
            url += f"&page={page}"
        resp = self.fetch(url, headers=self.headers)
        if not resp or '页面加载中' in resp.text:
            resp = self.fetch(url, headers={
                **self.headers,
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest'
            }, data=f"searchword={encoded_key}&page={page}")
        if not resp or '页面加载中' in (resp.text if resp else ''):
            return {"list": [], "page": page, "pagecount": 1}

        soup = BeautifulSoup(resp.text, 'html.parser')
        video_list = self._parse_video_list(soup)
        return {"list": video_list, "page": page, "pagecount": 1}

    def playerContent(self, flag, id, vipFlags):
        # ✅ 抄七猫改.py：保险识别 msearch（OK壳搜索结果可能直进播放）
        raw_id = str(id)
        if self.is_msearch_id(raw_id):
            real_id = self._resolve_msearch(raw_id)
            if real_id:
                id = real_id

        if id.startswith('http'):
            play_url = id
        elif id.startswith('/'):
            play_url = self.site_url + id
        elif re.match(r'\d+-\d+-\d+', str(id)):
            play_url = f"{self.site_url}/play/{id}.html"
        elif re.match(r'\d+', str(id)):
            play_url = f"{self.site_url}/play/{id}-1-0.html"
        else:
            play_url = f"{self.site_url}/play/{id}.html"

        resp = self.fetch(play_url, headers=self.headers)
        if not resp:
            return {"parse": 1, "url": play_url, "header": self.headers}

        html = resp.text

        now_match = re.search(r'var\s+now\s*=\s*"([^"]+)"', html)
        if now_match:
            video_url = now_match.group(1)
            if video_url and video_url.startswith('http'):
                return {"parse": 0, "url": video_url, "header": self.headers}

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

        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe:
            iframe_url = iframe.group(1)
            if not iframe_url.startswith('http'):
                iframe_url = self.site_url + iframe_url if iframe_url.startswith('/') else self.site_url + '/' + iframe_url
            iframe_resp = self.fetch(iframe_url, headers=self.headers)
            if iframe_resp:
                iframe_html = iframe_resp.text
                m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', iframe_html)
                if m3u8:
                    return {"parse": 0, "url": m3u8.group(1), "header": self.headers}
                video_src = re.search(r'<video[^>]+src="([^"]+)"', iframe_html)
                if video_src:
                    return {"parse": 0, "url": video_src.group(1), "header": self.headers}

        video_src = re.search(r'<video[^>]+src="([^"]+)"', html)
        if video_src:
            return {"parse": 0, "url": video_src.group(1), "header": self.headers}

        m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
        if m3u8:
            return {"parse": 0, "url": m3u8.group(1), "header": self.headers}

        mp4 = re.search(r'(https?://[^\s"\']+\.mp4[^\s"\']*)', html)
        if mp4:
            return {"parse": 0, "url": mp4.group(1), "header": self.headers}

        return {"parse": 1, "url": play_url, "header": self.headers}

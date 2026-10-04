# coding=utf-8
"""
目标站: 红豆短剧网 (szswt.net)
基于番茄短剧模板改写，适配红豆短剧网的结构
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
        self.site_url = "http://szswt.net"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        # 动态获取分类
        self.categories = self._fetch_categories()

    def _fetch_categories(self):
        """从首页导航栏解析分类标签"""
        try:
            resp = self.fetch(self.site_url, headers=self.headers)
            if not resp:
                return self._default_categories()
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 导航菜单：ul.stui-header__menu li a (排除"首页"和"播放记录")
            nav_links = soup.select('ul.stui-header__menu li a')
            categories = []
            seen = set()
            for a in nav_links:
                href = a.get('href', '')
                # 匹配 /vtype/数字.html 格式
                match = re.search(r'/vtype/(\d+)\.html', href)
                if not match:
                    continue
                tid = match.group(1)
                name = a.get_text(strip=True)
                # 排除"首页"和"播放记录"等非分类项
                if not name or name in ['首页', '播放记录', ''] or tid in seen:
                    continue
                seen.add(tid)
                categories.append({"type_id": tid, "type_name": name})
            if categories:
                return categories
        except Exception as e:
            print(f"[红豆短剧] 获取分类失败: {e}")
        return self._default_categories()

    def _default_categories(self):
        # 若获取失败，使用硬编码
        return [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "连续剧"},
            {"type_id": "3", "type_name": "综艺"},
            {"type_id": "4", "type_name": "动漫"},
            {"type_id": "28", "type_name": "纪录片"}
        ]

    # ================= 首页推荐 =================
    def homeContent(self, filter):
        url = self.site_url + "/"
        resp = self.fetch(url, headers=self.headers)
        video_list = []
        if resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 首页所有视频卡片在 ul.stui-vodlist li 中
            items = soup.select('ul.stui-vodlist li')
            for item in items:
                link = item.select_one('a.stui-vodlist__thumb')
                if not link:
                    continue
                href = link.get('href', '')
                # 匹配 /varticle/数字.html 格式
                vod_id = re.search(r'/varticle/(\d+)\.html', href)
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
                # 获取图片
                pic = link.get('data-original', '')
                if not pic:
                    # 尝试从img标签获取
                    img = item.select_one('img')
                    if img:
                        pic = img.get('data-original', '') or img.get('src', '')
                if not pic:
                    # 尝试从style背景获取
                    style = link.get('style', '')
                    bg_match = re.search(r'url\(([^)]+)\)', style)
                    if bg_match:
                        pic = bg_match.group(1)
                if pic and not pic.startswith('http'):
                    pic = 'https:' + pic if pic.startswith('//') else self.site_url + pic
                # 获取备注（状态/集数）
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

    # ================= 分类列表 =================
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        # 分类URL: /vtype/数字.html，分页参数 ?page=数字
        url = f"{self.site_url}/vtype/{tid}.html"
        if page > 1:
            url += f"?page={page}"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}

        soup = BeautifulSoup(resp.text, 'html.parser')
        video_list = []
        items = soup.select('ul.stui-vodlist li')
        for item in items:
            link = item.select_one('a.stui-vodlist__thumb')
            if not link:
                continue
            href = link.get('href', '')
            vod_id = re.search(r'/varticle/(\d+)\.html', href)
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
                img = item.select_one('img')
                if img:
                    pic = img.get('data-original', '') or img.get('src', '')
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
        # 分页信息
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
        url = f"{self.site_url}/varticle/{vod_id}.html"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": []}

        soup = BeautifulSoup(resp.text, 'html.parser')
        # 标题
        title_elem = soup.select_one('.stui-content__title h1') or soup.select_one('h1')
        vod_name = title_elem.get_text(strip=True) if title_elem else vod_id
        # 海报
        vod_pic = ''
        img_elem = soup.select_one('.stui-content__thumb img')
        if img_elem:
            vod_pic = img_elem.get('data-original', '') or img_elem.get('src', '')
            if vod_pic and not vod_pic.startswith('http'):
                vod_pic = 'https:' + vod_pic if vod_pic.startswith('//') else self.site_url + vod_pic
        # 简介
        vod_content = ''
        content_elem = soup.select_one('.stui-content__desc') or soup.select_one('.stui-content__detail .desc')
        if content_elem:
            vod_content = content_elem.get_text(' ', strip=True)
        # 演员/导演/地区/年份等信息
        vod_actor = ''
        vod_director = ''
        vod_area = ''
        vod_year = ''
        info_items = soup.select('.stui-content__detail p')
        for p in info_items:
            text = p.get_text(strip=True)
            if '导演' in text:
                vod_director = text.replace('导演：', '').replace('导演:', '').strip()
            elif '主演' in text:
                vod_actor = text.replace('主演：', '').replace('主演:', '').strip()
            elif '地区' in text:
                vod_area = text.replace('地区：', '').replace('地区:', '').strip()
            elif '年份' in text:
                vod_year = text.replace('年份：', '').replace('年份:', '').strip()

        # ========== 修复：正确解析播放列表 ==========
        play_from_list = []
        play_url_list = []
        
        # 方法1：查找所有 .stui-play__list 或 .stui-content__playlist 或 .playlist
        play_blocks = soup.select('.stui-play__list, .stui-content__playlist, .playlist, .stui-vodlist__play')
        
        if play_blocks:
            for block in play_blocks:
                # 获取线路名称
                line_name = "默认线路"
                # 尝试从标题元素获取
                name_elem = block.select_one('.stui-play__list-title') or block.select_one('.title') or block.select_one('h4') or block.select_one('strong')
                if name_elem:
                    line_name = name_elem.get_text(strip=True)
                elif block.get('class'):
                    # 如果class中包含线路信息
                    classes = ' '.join(block.get('class', []))
                    if 'line' in classes:
                        line_match = re.search(r'line(\d+)', classes)
                        if line_match:
                            line_name = f"线路{line_match.group(1)}"
                
                # 获取该线路下的所有集数链接
                episodes = []
                # 查找所有的a标签
                for a in block.select('a'):
                    href = a.get('href', '')
                    if not href or 'javascript:' in href or href == '#':
                        continue
                    ep_name = a.get_text(strip=True)
                    if not ep_name:
                        ep_name = f"第{len(episodes)+1}集"
                    # 拼接完整URL
                    if not href.startswith('http'):
                        href = self.site_url + href if href.startswith('/') else self.site_url + '/' + href
                    episodes.append(f"{ep_name}${href}")
                
                if episodes:
                    play_from_list.append(line_name)
                    play_url_list.append('#'.join(episodes))
        
        # 方法2：如果上面的方法没有获取到，尝试查找所有带播放链接的ul
        if not play_url_list:
            # 查找所有包含播放链接的ul
            all_uls = soup.select('ul')
            for ul in all_uls:
                links = ul.select('a[href*="/play/"], a[href*="/varticle/"]')
                if links:
                    # 检查是否是播放列表（至少2个链接）
                    if len(links) >= 2:
                        line_name = "默认线路"
                        # 尝试获取线路名
                        parent = ul.parent
                        if parent:
                            name_elem = parent.select_one('.title, h4, strong, .stui-play__list-title')
                            if name_elem:
                                line_name = name_elem.get_text(strip=True)
                        episodes = []
                        for a in links:
                            href = a.get('href', '')
                            if not href or 'javascript:' in href:
                                continue
                            ep_name = a.get_text(strip=True)
                            if not ep_name:
                                ep_name = f"第{len(episodes)+1}集"
                            if not href.startswith('http'):
                                href = self.site_url + href if href.startswith('/') else self.site_url + '/' + href
                            episodes.append(f"{ep_name}${href}")
                        if episodes:
                            play_from_list.append(line_name)
                            play_url_list.append('#'.join(episodes))
                        break
        
        # 方法3：直接在页面中查找所有播放链接（兜底）
        if not play_url_list:
            # 查找所有 /play/ 或 /varticle/ 的链接，但排除当前详情页
            all_links = soup.select('a[href*="/play/"]')
            if all_links:
                episodes = []
                for a in all_links:
                    href = a.get('href', '')
                    ep_name = a.get_text(strip=True)
                    if not ep_name:
                        ep_name = f"第{len(episodes)+1}集"
                    if not href.startswith('http'):
                        href = self.site_url + href if href.startswith('/') else self.site_url + '/' + href
                    episodes.append(f"{ep_name}${href}")
                if episodes:
                    play_from_list.append('默认线路')
                    play_url_list.append('#'.join(episodes))
            
            # 如果还是没有，尝试从详情页的直接播放链接获取
            if not play_url_list:
                direct_links = soup.select(f'a[href="/varticle/{vod_id}.html"]')
                for a in direct_links:
                    href = a.get('href', '')
                    if href:
                        play_from_list.append('播放链接')
                        play_url_list.append(f"播放${self.site_url}{href if href.startswith('/') else '/'+href}")
                        break

        # 如果还是没有获取到任何播放列表，使用默认值
        if not play_url_list:
            play_from_list = ['默认源']
            play_url_list = [f"播放${vod_id}"]

        vod_play_from = '$$$'.join(play_from_list)
        vod_play_url = '$$$'.join(play_url_list)

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

    # ================= 搜索 =================
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)
        # 红豆短剧网的搜索接口
        url = f"{self.site_url}/vodsearch/-------------.html?wd={encoded_key}"
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
            vod_id = re.search(r'/varticle/(\d+)\.html', href)
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
                img = item.select_one('img')
                if img:
                    pic = img.get('data-original', '') or img.get('src', '')
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

    # ================= 播放解析 =================
    def playerContent(self, flag, id, vipFlags):
        """
        解析播放链接
        flag: 线路标识
        id: 播放地址或视频ID
        """
        # 如果id是完整URL则直接使用，否则拼接
        if not id.startswith('http'):
            if id.startswith('/'):
                play_url = self.site_url + id
            else:
                play_url = f"{self.site_url}/varticle/{id}.html"
        else:
            play_url = id

        resp = self.fetch(play_url, headers=self.headers)
        if not resp:
            return {"parse": 1, "url": play_url, "header": self.headers}

        html = resp.text
        
        # 1. 查找iframe中的视频源
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe:
            iframe_url = iframe.group(1)
            if not iframe_url.startswith('http'):
                iframe_url = self.site_url + iframe_url if iframe_url.startswith('/') else self.site_url + '/' + iframe_url
            iframe_resp = self.fetch(iframe_url, headers=self.headers)
            if iframe_resp:
                iframe_html = iframe_resp.text
                # 尝试从iframe中提取video标签
                video_src = re.search(r'<video[^>]+src="([^"]+)"', iframe_html)
                if video_src:
                    return {"parse": 0, "url": video_src.group(1), "header": self.headers}
                # 尝试提取m3u8
                m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', iframe_html)
                if m3u8:
                    return {"parse": 0, "url": m3u8.group(1), "header": self.headers}
                # 尝试嵌套iframe
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

        # 2. 查找video标签
        video_src = re.search(r'<video[^>]+src="([^"]+)"', html)
        if video_src:
            return {"parse": 0, "url": video_src.group(1), "header": self.headers}

        # 3. 查找player_aaaa变量
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

        # 4. 直接匹配m3u8
        m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
        if m3u8:
            return {"parse": 0, "url": m3u8.group(1), "header": self.headers}

        # 5. 匹配mp4
        mp4 = re.search(r'(https?://[^\s"\']+\.mp4[^\s"\']*)', html)
        if mp4:
            return {"parse": 0, "url": mp4.group(1), "header": self.headers}

        return {"parse": 1, "url": play_url, "header": self.headers}
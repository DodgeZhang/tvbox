# coding=utf-8
"""
目标站: 在线短剧 (https://www.essoog.com)
模板: 苹果CMS (mxstatic主题)
特性: 纯正则解析、二级排序筛选、多线路播放、搜索优化、极速加载
线路: 红果短剧(line=0)、红豆剧场(line=1)、河马短剧(line=2)
"""

import re
import sys
import json
import urllib.parse
import time
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.site_url = "https://www.essoog.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
        }
        # 一级分类
        self.categories = [
            {"type_id": "1", "type_name": "重生"},
            {"type_id": "2", "type_name": "穿越"},
            {"type_id": "3", "type_name": "爽剧"},
            {"type_id": "4", "type_name": "言情"},
            {"type_id": "5", "type_name": "都市"},
            {"type_id": "6", "type_name": "古装"},
            {"type_id": "7", "type_name": "悬疑"},
            {"type_id": "8", "type_name": "剧情"},
        ]
        # 二级筛选：排序方式
        sort_values = [
            {"n": "最新", "v": "time"},
            {"n": "最热", "v": "hit"},
            {"n": "评分", "v": "commend"}
        ]
        self.filters = {str(i): [{"key": "by", "name": "排序", "value": sort_values}] for i in range(1, 9)}

        # 预编译正则，大幅提升解析速度
        self._re_module_item = re.compile(
            r'<div class="module-item[^"]*"[^>]*>(.*?)</div>\s*</div>', re.DOTALL)
        self._re_href_id = re.compile(r'href="/djok/(\d+)\.html"')
        self._re_data_src = re.compile(r'data-src="([^"]+)"')
        self._re_module_title = re.compile(r'class="module-item-title"[^>]*>([^<]+)</a>')
        self._re_item_text = re.compile(r'class="module-item-text"[^>]*>([^<]+)</a>')
        self._re_tab_nav = re.compile(
            r'<li[^>]*>\s*<a[^>]*href="#(playlist\d+)"[^>]*data-toggle="tab"[^>]*>(.*?)</a>\s*(?:<small>\(\d+\)</small>)?\s*</li>', 
            re.DOTALL)
        self._re_playlist = re.compile(
            r'<div[^>]*id="(playlist\d+)"[^>]*class="tab-pane[^"]*"[^>]*>(.*?)</ul>', re.DOTALL)
        self._re_play_link = re.compile(
            r'href="/play/(\d+)-(\d+)-(\d+)\.html"[^>]*>(.*?)</a>', re.DOTALL)

    def _safe_fetch(self, url, headers=None, max_retry=2):
        if headers is None:
            headers = self.headers
        for i in range(max_retry):
            try:
                resp = self.fetch(url, headers=headers)
                if resp and resp.status_code == 200:
                    return resp
            except Exception:
                pass
            if i < max_retry - 1:
                time.sleep(0.3 * (i + 1))
        return None

    def _fix_url(self, url):
        if not url:
            return ''
        if url.startswith('http'):
            return url
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.site_url + url
        return self.site_url + '/' + url

    def _parse_video_list(self, html, max_count=0):
        video_list = []
        seen = set()
        item_blocks = self._re_module_item.findall(html)
        for block in item_blocks:
            href_m = self._re_href_id.search(block)
            if not href_m:
                continue
            vod_id = href_m.group(1)
            if vod_id in seen:
                continue
            seen.add(vod_id)
            title = ''
            title_m = self._re_module_title.search(block)
            if title_m:
                title = title_m.group(1).strip()
            pic = ''
            pic_m = self._re_data_src.search(block)
            if pic_m:
                pic = pic_m.group(1)
            remark = ''
            remark_m = self._re_item_text.search(block)
            if remark_m:
                remark = remark_m.group(1).strip()
            if not title:
                continue
            video_list.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": self._fix_url(pic),
                "vod_remarks": remark,
            })
            if max_count > 0 and len(video_list) >= max_count:
                break
        return video_list

    def _extract_page_info(self, html, tid, default_page):
        pagecount = default_page
        total = 0
        pages = re.findall(r'/dj/' + re.escape(str(tid)) + r'-(\d+)\.html', html)
        if pages:
            pagecount = max(pagecount, max(map(int, pages)))
        total_m = re.search(r'共\s*(\d+)\s*部', html)
        if total_m:
            total = int(total_m.group(1))
        if not total:
            total = 36 * pagecount
        return pagecount, total

    def homeContent(self, filter):
        url = self.site_url + "/"
        resp = self._safe_fetch(url)
        video_list = []
        if resp:
            video_list = self._parse_video_list(resp.text, max_count=36)
        return {"class": self.categories, "list": video_list, "filters": self.filters}

    def homeVideoContent(self):
        return self.homeContent(False)

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        by = extend.get('by', '') if extend else ''
        if page <= 1:
            url = f"{self.site_url}/dj/{tid}-{by}.html" if by else f"{self.site_url}/dj/{tid}.html"
        else:
            url = f"{self.site_url}/dj/{tid}-{by}-{page}.html" if by else f"{self.site_url}/dj/{tid}-{page}.html"
        resp = self._safe_fetch(url)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 36, "total": 0}
        video_list = self._parse_video_list(resp.text)
        pagecount, total = self._extract_page_info(resp.text, tid, page)
        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 36,
            "total": total
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        url = f"{self.site_url}/djok/{vod_id}.html"
        resp = self._safe_fetch(url)
        if not resp:
            return {"list": []}
        html = resp.text

        # 标题
        vod_name = vod_id
        title_m = re.search(r'<title>(.*?)</title>', html)
        if title_m:
            raw = title_m.group(1)
            vod_name = raw.split('在线播放')[0].split('》')[0].replace('《', '').strip()

        # 大图
        vod_pic = ''
        pic_m = re.search(r'data-src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', html)
        if pic_m:
            vod_pic = self._fix_url(pic_m.group(1))

        # 简介
        vod_content = ''
        desc_m = re.search(r'<meta name="description" content="([^"]*)"', html)
        if desc_m:
            vod_content = desc_m.group(1)
            vod_content = re.sub(r'^.*?剧情介绍[：:]\s*', '', vod_content)
            vod_content = re.sub(r'，该[^。]*讲述的是.*$', '', vod_content)
            vod_content = re.sub(r'暂无简介', '', vod_content).strip()

        # 年份
        vod_year = ''
        y_m = re.search(r'(\d{4})年', vod_content)
        if y_m:
            vod_year = y_m.group(1)
        if not vod_year:
            y_m2 = re.search(r'(\d{4})-\d{2}-\d{2}', html)
            if y_m2:
                vod_year = y_m2.group(1)

        # 播放列表 -- 从tab导航提取真实线路名称，按playlist分组
        play_from_list = []
        play_url_list = []

        # 提取tab导航: playlist_id -> 线路名称
        tab_nav = self._re_tab_nav.findall(html)
        tab_names = {}
        for pane_id, name in tab_nav:
            name = re.sub(r'<[^>]+>', '', name).strip()
            if name:
                tab_names[pane_id] = name

        # 提取每个playlist的播放链接
        playlists = self._re_playlist.findall(html)
        for pane_id, pane_content in playlists:
            line_name = tab_names.get(pane_id, pane_id)
            links = self._re_play_link.findall(pane_content)
            ep_list = []
            for vid, line, ep, ep_raw in links:
                ep_name = re.sub(r'<[^>]+>', '', ep_raw).strip()
                if not ep_name:
                    continue
                link = f"/play/{vid}-{line}-{ep}.html"
                ep_list.append(f"{ep_name}${self._fix_url(link)}")
            if ep_list:
                play_from_list.append(line_name)
                play_url_list.append('#'.join(ep_list))

        # 兜底
        if not play_from_list:
            play_from_list.append('默认线路')
            play_url_list.append(f"播放${self.site_url}/djok/{vod_id}.html")

        vod_play_from = '$$$'.join(play_from_list)
        vod_play_url = '$$$'.join(play_url_list)

        result = [{
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_year": vod_year,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)
        if page <= 1:
            url = f"{self.site_url}/index.php/vod/search.html?wd={encoded_key}"
        else:
            url = f"{self.site_url}/index.php/vod/search.html?wd={encoded_key}&page={page}"
        resp = self._safe_fetch(url)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1}
        video_list = self._parse_video_list(resp.text)
        pagecount = 1
        pages = re.findall(r'page=(\d+)', resp.text)
        if pages:
            pagecount = max(pagecount, max(map(int, pages)))
        return {"list": video_list, "page": page, "pagecount": pagecount}

    def playerContent(self, flag, id, vipFlags):
        if id.startswith('http'):
            play_url = id
        elif id.startswith('/'):
            play_url = self.site_url + id
        else:
            play_url = self.site_url + '/' + id
        resp = self._safe_fetch(play_url)
        if not resp:
            return {"parse": 1, "url": play_url, "header": self.headers}
        html = resp.text
        # 1. 优先 var now="xxx.m3u8" -- 该站直出，最快
        now_m = re.search(r'var\s+now\s*=\s*"([^"]+)"', html)
        if now_m:
            video_url = now_m.group(1)
            if video_url and video_url.startswith('http'):
                return {"parse": 0, "url": video_url, "header": self.headers}
        # 2. 全局m3u8
        m3u8_m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
        if m3u8_m:
            return {"parse": 0, "url": m3u8_m.group(0), "header": self.headers}
        # 3. iframe
        iframe_m = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe_m:
            iframe_url = iframe_m.group(1)
            if not iframe_url.startswith('http'):
                iframe_url = self._fix_url(iframe_url)
            return {"parse": 1, "url": iframe_url, "header": self.headers}
        # 4. mac_player_config
        mac_m = re.search(r'mac_player_config\s*=\s*({.*?})', html, re.DOTALL)
        if mac_m:
            try:
                cfg = json.loads(mac_m.group(1))
                video_url = cfg.get('url', '')
                if video_url and '.m3u8' in video_url:
                    return {"parse": 0, "url": video_url, "header": self.headers}
            except Exception:
                pass
        return {"parse": 1, "url": play_url, "header": self.headers}

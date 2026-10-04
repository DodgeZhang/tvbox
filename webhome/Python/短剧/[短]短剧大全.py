# coding=utf-8
"""
目标站: 短剧大全 (https://lssy.net)
特性: 自定义PHP前端、分页列表(?p=N)、搜索过滤(?keyword=xxx&p=N)、详情页直出m3u8
优化: 分页加载全量32,666部、搜索模拟真实分类、parse=0直链秒播
"""

import re
import sys
import urllib.parse
import time
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.site_url = "https://lssy.net"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.site_url + '/',
            'Connection': 'keep-alive',
        }

        # 一级分类：站点无真实type接口，用搜索关键词模拟分类
        # 每个分类对应一个搜索关键词，返回真实不同的内容
        self.categories = [
            {"type_id": "1", "type_name": "短剧大全"},   # 全部，不分页关键词
            {"type_id": "2", "type_name": "重生"},
            {"type_id": "3", "type_name": "穿越"},
            {"type_id": "4", "type_name": "都市"},
            {"type_id": "5", "type_name": "甜宠"},
            {"type_id": "6", "type_name": "虐恋"},
            {"type_id": "7", "type_name": "战神"},
            {"type_id": "8", "type_name": "逆袭"},
            {"type_id": "9", "type_name": "古装"},
            {"type_id": "10", "type_name": "家庭"},
            {"type_id": "11", "type_name": "悬疑"},
            {"type_id": "12", "type_name": "剧情"},
        ]
        # 分类ID -> 搜索关键词映射（短剧大全用空关键词，返回全部）
        self.cat_keyword_map = {
            "1": "",       # 全部
            "2": "重生",
            "3": "穿越",
            "4": "都市",
            "5": "甜宠",
            "6": "虐恋",
            "7": "战神",
            "8": "逆袭",
            "9": "古装",
            "10": "家庭",
            "11": "悬疑",
            "12": "剧情",
        }
        # 取消二级分类
        self.filters = {}

    def _safe_fetch(self, url, max_retry=1, timeout=8):
        headers = self.headers.copy()
        headers['Referer'] = url if 'detail.php' in url else self.site_url + '/'
        for i in range(max_retry + 1):
            try:
                resp = self.fetch(url, headers=headers)
                if resp and resp.status_code == 200:
                    return resp
            except Exception:
                pass
            if i < max_retry:
                time.sleep(0.2)
        return None

    def _fix_url(self, url):
        if not url:
            return ''
        url = url.strip()
        if url.startswith('http'):
            return url
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.site_url + url
        return self.site_url + '/' + url

    def _parse_video_list(self, html):
        video_list = []
        seen = set()
        cards = re.findall(r'<div class="card">(.*?)</div>\s*</div>', html, re.DOTALL)
        for block in cards:
            vid_m = re.search(r'detail\.php\?vid=(\d+)', block)
            if not vid_m:
                continue
            vod_id = vid_m.group(1)
            if vod_id in seen:
                continue
            seen.add(vod_id)
            title = ''
            title_m = re.search(r'<div class="title">(.*?)</div>', block, re.DOTALL)
            if title_m:
                title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
            pic = ''
            pic_m = re.search(r'data-original="([^"]+)"', block)
            if not pic_m:
                pic_m = re.search(r'src="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', block)
            if pic_m:
                pic = self._fix_url(pic_m.group(1))
            remark = ''
            ep_m = re.search(r'(\d+)\s*集', block)
            if ep_m:
                remark = f"{ep_m.group(1)}集"
            if title:
                video_list.append({
                    "vod_id": vod_id,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remark,
                })
        return video_list

    def _extract_page_info(self, html):
        """从分页区域提取总页码"""
        pagecount = 1
        # 匹配 ?p=数字&keyword= 形式的页码
        pages = re.findall(r'\?p=(\d+)&keyword=', html)
        if pages:
            pagecount = max(pagecount, max(map(int, pages)))
        # 匹配总数文本
        total = 0
        total_m = re.search(r'共找到\s*([\d,]+)\s*部', html)
        if total_m:
            total = int(total_m.group(1).replace(',', ''))
        if not total:
            total = 20 * pagecount
        return pagecount, total

    def homeContent(self, filter):
        url = self.site_url + "/"
        resp = self._safe_fetch(url)
        video_list = []
        if resp:
            video_list = self._parse_video_list(resp.text)
        return {"class": self.categories, "list": video_list, "filters": self.filters}

    def homeVideoContent(self):
        return self.homeContent(False)

    def categoryContent(self, tid, pg, filter, extend):
        """
        分类内容：用搜索关键词模拟分类，每个分类返回真实不同的内容
        tid=1(短剧大全)返回全部，tid>=2按关键词搜索
        """
        page = int(pg) if pg else 1
        keyword = self.cat_keyword_map.get(str(tid), "")

        if keyword:
            # 有关键词：用搜索接口
            encoded_kw = urllib.parse.quote(keyword)
            url = f"{self.site_url}/?keyword={encoded_kw}&p={page}"
        else:
            # 无关键词：用全部分页接口
            if page <= 1:
                url = self.site_url + "/"
            else:
                url = f"{self.site_url}/?p={page}"

        resp = self._safe_fetch(url)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

        video_list = self._parse_video_list(resp.text)
        pagecount, total = self._extract_page_info(resp.text)

        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 20,
            "total": total
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        url = f"{self.site_url}/detail.php?vid={vod_id}"
        resp = self._safe_fetch(url)
        if not resp:
            return {"list": []}
        html = resp.text

        vod_name = ''
        title_m = re.search(r'<title>(.*?)</title>', html)
        if title_m:
            vod_name = title_m.group(1).split('-')[0].split('_')[0].strip()
        if not vod_name or vod_name == '短剧大全':
            name_m = re.search(r'<div class="video-title">(.*?)</div>', html, re.DOTALL)
            if name_m:
                vod_name = re.sub(r'<[^>]+>', '', name_m.group(1)).strip()

        vod_pic = ''
        pic_m = re.search(r'<video[^>]*poster="([^"]+)"', html)
        if not pic_m:
            pic_m = re.search(r'data-original="([^"]+)"', html)
        if pic_m:
            vod_pic = self._fix_url(pic_m.group(1))

        vod_content = ''
        desc_m = re.search(r'<meta name="description" content="([^"]+)"', html)
        if desc_m:
            vod_content = desc_m.group(1).strip()
            vod_content = re.sub(r'短剧大全-短剧网提供.*?在线观看[。，]?', '', vod_content).strip()

        vod_year = ''
        year_m = re.search(r'(\d{4})[年/-]', html)
        if year_m:
            vod_year = year_m.group(1)

        play_urls = []
        episodes = re.findall(
            r'<div[^>]*class="episode[^"]*"[^>]*data-src="([^"]+)"[^>]*>(.*?)</div>',
            html, re.DOTALL
        )
        if episodes:
            for idx, (src, ep_raw) in enumerate(episodes, 1):
                ep_name = re.sub(r'<[^>]+>', '', ep_raw).strip()
                if not ep_name:
                    ep_name = f"第{idx}集"
                m3u8_url = src if src.startswith('http') else self._fix_url(src)
                play_urls.append(f"{ep_name}${m3u8_url}")
        else:
            m3u8_links = re.findall(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*", html)
            m3u8_links = list(dict.fromkeys(m3u8_links))
            for idx, m3u8_url in enumerate(m3u8_links, 1):
                play_urls.append(f"第{idx}集${m3u8_url}")

        if play_urls:
            vod_play_from = "直链播放"
            vod_play_url = '#'.join(play_urls)
        else:
            vod_play_from = "默认线路"
            vod_play_url = f"播放${self.site_url}/detail.php?vid={vod_id}"

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_actor": '',
            "vod_director": '',
            "vod_area": '',
            "vod_year": vod_year,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url,
        }]}

    def searchContent(self, key, quick, pg="1"):
        """搜索内容：真实搜索接口，支持分页"""
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)
        url = f"{self.site_url}/?keyword={encoded_key}&p={page}"

        resp = self._safe_fetch(url)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "total": 0}

        video_list = self._parse_video_list(resp.text)
        pagecount, total = self._extract_page_info(resp.text)

        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 20,
            "total": total
        }

    def playerContent(self, flag, id, vipFlags):
        if id.startswith('http'):
            play_url = id
        else:
            play_url = self._fix_url(id)
        if '.m3u8' in play_url:
            return {
                "parse": 0,
                "url": play_url,
                "header": {
                    'User-Agent': self.headers['User-Agent'],
                    'Referer': self.site_url + '/',
                }
            }
        resp = self._safe_fetch(play_url)
        if resp:
            m3u8_m = re.search(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*", resp.text)
            if m3u8_m:
                return {
                    "parse": 0,
                    "url": m3u8_m.group(0),
                    "header": {
                        'User-Agent': self.headers['User-Agent'],
                        'Referer': play_url,
                    }
                }
        return {"parse": 1, "url": play_url, "header": self.headers}

    def localProxy(self, param):
        return [200, "video/MP2T", "", ""]

    def isVideoFormat(self, url):
        return any(url.endswith(ext) for ext in ['.m3u8', '.mp4', '.ts', '.flv', '.avi', '.mkv'])

# coding=utf-8
"""
目标站: 蚕驰短剧网 (https://carbonnine.com)
模板: 苹果CMS V10 (mytheme)
优化: 极速加载、极速播放、预缓存分类、预编译正则、精简解析、减少请求
"""
import re
import sys
import urllib.parse
import time
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.site_url = "https://carbonnine.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        # 预缓存全部分类（8个），省去首页动态解析时间
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
        # 预生成筛选
        self.filter_template = [
            {"key": "by", "name": "排序", "value": [
                {"n": "最新", "v": "time"}, {"n": "最热", "v": "hits"}, {"n": "评分", "v": "score"}
            ]},
        ]
        self.filters = {c["type_id"]: self.filter_template for c in self.categories}
        # 线路映射（该站常见线路）
        self.line_name_map = {"0": "主线路", "1": "备用线路", "2": "线路3", "3": "线路4"}
        # 预编译列表页正则（提速关键）
        self._list_pattern = re.compile(
            r'<a[^>]+class="myui-vodlist__thumb[^"]*"[^>]+href="/canchiduanju/(\d+)\.html"[^>]+title="([^"]*)"[^>]+data-original="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL
        )

    def _safe_fetch(self, url, headers=None, max_retry=1):
        """极速请求：只重试1次，间隔0.1s"""
        if headers is None:
            headers = self.headers
        for i in range(max_retry):
            try:
                resp = self.fetch(url, headers=headers)
                if resp and getattr(resp, 'status_code', 200) == 200:
                    return resp
            except Exception:
                if i < max_retry - 1:
                    time.sleep(0.1)
        return None

    def _fix_url(self, url):
        if not url:
            return ''
        if url.startswith('http'):
            return url
        if url.startswith('//'):
            return 'https:' + url
        return self.site_url + url

    def _parse_video_list(self, html, max_count=0):
        """预编译正则极速解析视频列表"""
        video_list = []
        seen = set()
        for vod_id, title, pic, inner in self._list_pattern.findall(html):
            if vod_id in seen:
                continue
            seen.add(vod_id)
            # 快速提取备注
            remark = ''
            r_m = re.search(r'class="pic-text[^"]*"[^>]*>(.*?)</span>', inner)
            if r_m:
                remark = re.sub(r'<[^>]+>', '', r_m.group(1)).strip()
            video_list.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": self._fix_url(pic),
                "vod_remarks": remark,
            })
            if max_count > 0 and len(video_list) >= max_count:
                break
        return video_list

    def homeContent(self, filter):
        # 直接请求首页取列表，分类用预缓存的（省去解析分类的时间）
        resp = self._safe_fetch(self.site_url + "/")
        video_list = []
        if resp:
            video_list = self._parse_video_list(resp.text, max_count=36)
        return {"class": self.categories, "list": video_list, "filters": self.filters}

    def homeVideoContent(self):
        return self.homeContent(False)

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if page <= 1:
            url = f"{self.site_url}/ccdj/{tid}.html"
        else:
            url = f"{self.site_url}/ccdj/{tid}-{page}.html"
        resp = self._safe_fetch(url)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 30, "total": 0}
        html = resp.text
        video_list = self._parse_video_list(html)
        # 快速分页：只找最大页码
        pagecount = page
        pages = re.findall(rf'/ccdj/{tid}-(\d+)\.html', html)
        if pages:
            pagecount = max(pagecount, max(map(int, pages)))
        total = len(video_list) * pagecount
        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 30,
            "total": total
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        url = f"{self.site_url}/canchiduanju/{vod_id}.html"
        resp = self._safe_fetch(url)
        if not resp:
            return {"list": []}
        html = resp.text

        # 极速标题提取
        vod_name = vod_id
        m = re.search(r'<title>《([^》]+)》', html)
        if not m:
            m = re.search(r'<title>(.*?)</title>', html)
            if m:
                vod_name = m.group(1).split('在线观看')[0].split('_')[0].strip()
        else:
            vod_name = m.group(1).strip()

        # 极速大图：只取第一个 data-original
        vod_pic = ''
        m = re.search(r'data-original="([^"]+)"', html)
        if m:
            vod_pic = self._fix_url(m.group(1))

        # 简介简化提取
        vod_content = ''
        m = re.search(r'<meta name="description" content="([^"]*)"', html)
        if m:
            vod_content = m.group(1).split('剧情介绍')[-1].split('，该')[0].strip(' ：:')

        # 播放列表极速提取（多线路）
        play_links = re.findall(r'href="/play/(\d+)-(\d+)-(\d+)\.html"[^>]*>(.*?)</a>', html)
        groups = {}
        for vid, line, ep, ep_raw in play_links:
            ep_name = re.sub(r'<[^>]+>', '', ep_raw).strip()
            if not ep_name or ep_name in ('立即播放', ''):
                continue
            groups.setdefault(line, []).append(f"{ep_name}${self.site_url}/play/{vid}-{line}-{ep}.html")

        play_from_list = []
        play_url_list = []
        if groups:
            for line in sorted(groups.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
                line_name = self.line_name_map.get(str(line), f"线路{line}")
                play_from_list.append(line_name)
                play_url_list.append('#'.join(groups[line]))
        else:
            play_from_list.append('默认线路')
            play_url_list.append(f"播放${self.site_url}/canchiduanju/{vod_id}.html")

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_actor": "",
            "vod_director": "",
            "vod_area": "",
            "vod_year": "",
            "vod_play_from": '$$$'.join(play_from_list),
            "vod_play_url": '$$$'.join(play_url_list)
        }]}

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)
        url = f"{self.site_url}/search.php?searchword={encoded_key}"
        if page > 1:
            url += f"&page={page}"
        resp = self._safe_fetch(url)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1}
        video_list = self._parse_video_list(resp.text)
        # 简化分页判断
        pagecount = 1
        if 'page=' in resp.text:
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

        # 极速路径1：var now（该站直接暴露 m3u8，99%走这里，直接返回）
        m = re.search(r'var\s+now\s*=\s*"([^"]+)"', html)
        if m:
            url = m.group(1)
            if url.startswith('http'):
                return {"parse": 0, "url": url, "header": self.headers}

        # 极速路径2：全局搜 m3u8（兜底）
        m = re.search(r'(https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*)', html)
        if m:
            return {"parse": 0, "url": m.group(1), "header": self.headers}

        # 最后兜底
        return {"parse": 1, "url": play_url, "header": self.headers}

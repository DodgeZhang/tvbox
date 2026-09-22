# -*- coding: utf-8 -*-
# by @PyramidStore AutoGen
import re
import sys
sys.path.append('..')
import json
from urllib.parse import quote
from base.spider import Spider


class Spider(Spider):

    def init(self, extend=""):
        self.nav_host = 'https://www.xiguadh.com'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        self.host = self._get_host()

    def _get_host(self):
        """获取视频站点 URL，失败时从导航页获取"""
        default_host = 'https://www.bzzdyy.com'
        try:
            r = self.fetch(default_host, headers=self.headers, timeout=10, verify=False)
            if r.status_code == 200:
                return default_host
        except Exception:
            pass
        try:
            r = self.fetch(self.nav_host, headers=self.headers, timeout=15, verify=False)
            html = r.text
            urls = re.findall(r'url:\s*["\']([^"\']+)["\']', html)
            for url in urls:
                if url.startswith('http') and 'xiguadh' not in url:
                    return url.rstrip('/')
        except Exception:
            pass
        return default_host

    def getName(self):
        return '西瓜影院'

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return True

    def homeContent(self, filter):
        try:
            r = self.fetch(self.host, headers=self.headers, timeout=15, verify=False)
            html = r.text
            # 提取主要分类
            nav_match = re.search(r'<ul class="stui-header__menu">(.*?)</ul>', html, re.DOTALL)
            if nav_match:
                nav_html = nav_match.group(1)
                categories = re.findall(r'<li[^>]*><a href="/index.php/vod/type/id/(\d+)\.html">([^<]+)</a></li>', nav_html)
            else:
                categories = []
            seen = set()
            classes = []
            for tid, name in categories:
                if tid not in seen:
                    seen.add(tid)
                    classes.append({'type_name': name, 'type_id': tid})
            if not classes:
                raise Exception('No categories found')
            # 提取首页推荐视频
            videos = self._parse_vodlist(html)
        except Exception:
            classes = [
                {'type_name': '电影', 'type_id': '20'},
                {'type_name': '连续剧', 'type_id': '37'},
                {'type_name': '动漫', 'type_id': '43'},
                {'type_name': '综艺', 'type_id': '45'},
                {'type_name': 'B站', 'type_id': '47'},
                {'type_name': '人人专区', 'type_id': '60'},
            ]
            videos = []
        return {"class": classes, "list": videos}

    def _parse_vodlist(self, html):
        """解析视频列表"""
        items = re.findall(
            r'<a class="stui-vodlist__thumb[^"]*"\s+href="([^"]+)"\s+title="([^"]*)"[^>]*data-original="([^"]*)"',
            html
        )
        videos = []
        for href, title, pic in items:
            vod_id = re.search(r'/id/(\d+)\.html', href)
            if vod_id:
                vod_id = vod_id.group(1)
            else:
                continue
            remark_match = re.search(r'<span class="pic-text text-right"><b>([^<]+)</b></span>', 
                html[html.find(href):html.find(href)+500] if href in html else '')
            remark = remark_match.group(1) if remark_match else ''
            if pic.startswith('/'):
                pic = self.host + pic
            videos.append({
                'vod_id': vod_id,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remark,
            })
        return videos

    def homeVideoContent(self):
        return ''

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg)
        url = f'{self.host}/index.php/vod/type/id/{tid}/page/{pg}.html'
        try:
            r = self.fetch(url, headers=self.headers, timeout=15, verify=False)
            html = r.text
            items = re.findall(
                r'<a class="stui-vodlist__thumb[^"]*"\s+href="([^"]+)"\s+title="([^"]*)"[^>]*data-original="([^"]*)"',
                html
            )
            videos = []
            for href, title, pic in items:
                vod_id = re.search(r'/id/(\d+)\.html', href)
                if vod_id:
                    vod_id = vod_id.group(1)
                else:
                    continue
                remark_match = re.search(r'<span class="pic-text text-right"><b>([^<]+)</b></span>', 
                    html[html.find(href):html.find(href)+500] if href in html else '')
                remark = remark_match.group(1) if remark_match else ''
                if pic.startswith('/'):
                    pic = self.host + pic
                videos.append({
                    'vod_id': vod_id,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': remark,
                })
            return {
                "list": videos,
                "page": pg,
                "pagecount": 9999,
                "limit": 90,
                "total": len(videos),
            }
        except Exception as e:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 90, "total": 0}

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else ids
            url = f'{self.host}/index.php/vod/detail/id/{vod_id}.html'
            r = self.fetch(url, headers=self.headers, timeout=15, verify=False)
            html = r.text
            title_match = re.search(r'<h1 class="title">([^<]+)</h1>', html)
            title = title_match.group(1).strip() if title_match else ''
            self._vod_name = title
            pic_match = re.search(r'<img class="lazyload" data-original="([^"]*)"', html)
            pic = pic_match.group(1) if pic_match else ''
            if pic.startswith('/'):
                pic = self.host + pic
            info_match = re.search(r'类型：([^/]+)\s*/\s*地区：([^/]+)\s*/\s*年份：(\d+)', html)
            type_name = info_match.group(1).strip() if info_match else ''
            area = info_match.group(2).strip() if info_match else ''
            year = info_match.group(3) if info_match else ''
            remark_match = re.search(r'状态：<span[^>]*>([^<]+)</span>', html)
            remark = remark_match.group(1).strip() if remark_match else ''
            director_match = re.search(r'导演：(.*?)</p>', html, re.DOTALL)
            director = ''
            if director_match:
                director = re.sub(r'<[^>]+>', '', director_match.group(1)).strip()
            actor_match = re.search(r'主演：([^<]+)', html)
            actor = actor_match.group(1).strip() if actor_match else ''
            desc_match = re.search(r'<span class="detail-content"[^>]*>([^<]+)</span>', html)
            desc = desc_match.group(1).strip() if desc_match else ''
            play_from = []
            play_url = []
            source_tabs = re.findall(r'<li><a href="#playlist\d+"[^>]*>([^<]+)</a></li>', html)
            for idx, source_name in enumerate(source_tabs):
                source_id = idx + 1
                episodes_match = re.search(
                    f'<div id="playlist{source_id}" class="tab-pane[^"]*"[^>]*>.*?<ul class="stui-content__playlist[^"]*"[^>]*>(.*?)</ul>',
                    html, re.DOTALL
                )
                if episodes_match:
                    episodes = re.findall(r'<a href="([^"]+)">([^<]+)</a>', episodes_match.group(1))
                    episode_list = []
                    for ep_url, ep_name in episodes:
                        episode_list.append(f'{ep_name}${self.host}{ep_url}')
                    play_from.append(source_name)
                    play_url.append('#'.join(episode_list))
            vod_play_from = '$$$'.join(play_from) if play_from else '默认'
            vod_play_url = '$$$'.join(play_url) if play_url else ''
            vod = {
                'vod_id': vod_id,
                'vod_name': title,
                'vod_pic': pic,
                'vod_year': year,
                'vod_area': area,
                'vod_remarks': remark,
                'vod_director': director,
                'vod_actor': actor,
                'vod_content': desc,
                'vod_play_from': vod_play_from,
                'vod_play_url': vod_play_url,
            }
            return {"list": [vod]}
        except Exception as e:
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg)
        url = f'{self.host}/index.php/vod/search/wd/{quote(key)}.html'
        try:
            r = self.fetch(url, headers=self.headers, timeout=15, verify=False)
            html = r.text
            items = re.findall(
                r'<a class="stui-vodlist__thumb[^"]*"\s+href="([^"]+)"\s+title="([^"]*)"[^>]*data-original="([^"]*)"',
                html
            )
            videos = []
            for href, title, pic in items:
                vod_id = re.search(r'/id/(\d+)\.html', href)
                if vod_id:
                    vod_id = vod_id.group(1)
                else:
                    continue
                remark_match = re.search(r'<span class="pic-text text-right"><b>([^<]+)</b></span>', 
                    html[html.find(href):html.find(href)+500] if href in html else '')
                remark = remark_match.group(1) if remark_match else ''
                if pic.startswith('/'):
                    pic = self.host + pic
                videos.append({
                    'vod_id': vod_id,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': remark,
                })
            return {
                "list": videos,
                "page": pg,
                "pagecount": 9999,
                "limit": 90,
                "total": len(videos),
            }
        except Exception as e:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 90, "total": 0}

    def _clean_vod_name(self, name):
        import re
        if not name:
            return ''
        cleaned = re.sub(r'第\s*\d+\s*[集話话章部期]', '', name)
        cleaned = re.sub(r'EP\s*\d+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'全\d+集', '', cleaned)
        cleaned = re.sub(r'更新至\d+集', '', cleaned)
        cleaned = re.sub(r'\d+集全', '', cleaned)
        cleaned = re.sub(r'[（(].*?[）)]', '', cleaned)
        cleaned = re.sub(r'\s*-\s*.*$', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = re.sub(r'^[\s\-_,.，。、]+|[\s\-_,.，。、]+$', '', cleaned)
        return cleaned.strip()

    def _build_danmaku_url(self, vod_name, vod_index=''):
        import re
        idx = 0
        if vod_index:
            s = str(vod_index).strip()
            m = re.search(r'第\s*(\d+)\s*[集話话章部期]', s)
            if m:
                idx = int(m.group(1))
            else:
                m = re.search(r'(\d+)', s)
                if m:
                    idx = int(m.group(1))
        cleaned_name = self._clean_vod_name(vod_name)
        params = []
        if cleaned_name:
            params.append(f'vodName={quote(cleaned_name)}')
        params.append(f'vodIndex={idx}')
        query = '&'.join(params)
        return f'http://127.0.0.1:9978/proxy?do=appdanmu&{query}'

    def playerContent(self, flag, id, vipFlags):
        try:
            ep_name = ''
            vod_index = ''
            if '$' in id:
                parts = id.split('$', 1)
                ep_name = parts[0]
                url = parts[1] if len(parts) > 1 else ''
            else:
                url = id if id.startswith('http') else f'{self.host}{id}'
            # 从 URL 中提取集数 (nid 参数)
            nid_match = re.search(r'nid/(\d+)\.html', url)
            if nid_match:
                vod_index = nid_match.group(1)
            danmaku_url = self._build_danmaku_url(self._vod_name, vod_index)
            r = self.fetch(url, headers=self.headers, timeout=15, verify=False)
            html = r.text
            iframe_match = re.search(r'<iframe[^>]+src="([^"]+)"', html)
            if iframe_match:
                iframe_url = iframe_match.group(1)
                if not iframe_url.startswith('http'):
                    iframe_url = self.host + iframe_url
                return {
                    "parse": 1,
                    "url": iframe_url,
                    "header": self.headers,
                    "danmaku": danmaku_url
                }
            src_match = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', html)
            if src_match:
                return {
                    "parse": 0,
                    "url": src_match.group(1),
                    "header": self.headers,
                    "danmaku": danmaku_url
                }
            return {
                "parse": 1,
                "url": url,
                "header": self.headers,
                "danmaku": danmaku_url
            }
        except Exception as e:
            danmaku_url = self._build_danmaku_url(self._vod_name, '')
            return {"parse": 1, "url": id, "header": {}, "danmaku": danmaku_url}

    def localProxy(self, param):
        return [200, {}, ""]

    def destroy(self):
        pass

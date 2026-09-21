#coding=utf-8
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVBox / 影视仓 / OK影视  Python源脚本
站点: 红果短剧 (https://www.mochadj.com)
"""

import sys
import re
import json
import requests
from urllib.parse import quote
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def __init__(self):
        super().__init__()
        self.site = 'https://www.mochadj.com'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.mochadj.com/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        self.cateManual = {
            '1': '重生',
            '2': '穿越',
            '3': '爽剧',
            '4': '言情',
            '5': '都市',
            '6': '古装',
            '7': '悬疑',
            '8': '剧情',
        }

    def init(self, extend=""):
        pass

    def getName(self):
        return "红果短剧"

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    # ==================== 工具函数 ====================

    def _get(self, url, headers=None):
        """GET请求封装"""
        try:
            resp = self.session.get(url, headers=headers or self.session.headers, timeout=15, verify=False)
            resp.encoding = 'utf-8'
            return resp.text
        except Exception as e:
            print(f'[{self.getName()}] GET请求异常: {e}')
            return None

    def getVid(self, url):
        """从URL中提取影片ID"""
        if not url:
            return ''
        m = re.search(r'/dj/(\d+)\.html', url)
        if m:
            return m.group(1)
        m = re.search(r'/play/(\d+)-', url)
        if m:
            return m.group(1)
        return ''

    def _extract_text(self, html_snippet):
        """去除HTML标签"""
        return re.sub(r'<[^>]+>', '', html_snippet).strip()

    # ==================== 首页 ====================

    def homeContent(self, filter):
        result = {'class': [], 'filters': {}, 'list': [], 'parse': 0, 'jx': 0}
        for tid, name in self.cateManual.items():
            result['class'].append({
                'type_id': str(tid),
                'type_name': name
            })
        return result

    def homeVideoContent(self):
        """首页推荐：取分类页影片作为推荐"""
        videos = []
        try:
            url = f'{self.site}/'
            html = self._get(url)
            if not html:
                return {'list': videos, 'parse': 0, 'jx': 0}

            # 匹配 stui-vodlist__box 卡片
            box_pattern = r'<div[^>]*class="stui-vodlist__box"[^>]*>(.*?)</div>\s*</li>'
            boxes = re.findall(box_pattern, html, re.DOTALL)
            if not boxes:
                box_pattern = r'<div[^>]*class="stui-vodlist__box"[^>]*>(.*?)</div>'
                boxes = re.findall(box_pattern, html, re.DOTALL)

            seen = set()
            for box in boxes:
                title_m = re.search(r'title="([^"]+)"', box)
                title = title_m.group(1) if title_m else ''
                href_m = re.search(r'href="(/dj/\d+\.html)"', box)
                href = href_m.group(1) if href_m else ''
                vid = self.getVid(href)
                if not vid or vid in seen:
                    continue
                seen.add(vid)

                pic_m = re.search(r'data-original="([^"]+)"', box)
                pic = pic_m.group(1) if pic_m else ''
                note_m = re.search(r'class="pic-text[^"]*"[^>]*>([^<]+)</span>', box)
                note = note_m.group(1).strip() if note_m else ''

                if title:
                    videos.append({
                        'vod_id': vid,
                        'vod_name': title,
                        'vod_pic': pic,
                        'vod_remarks': note
                    })
        except Exception as e:
            print(f'[{self.getName()}] homeVideoContent error: {e}')
        return {'list': videos[:24], 'parse': 0, 'jx': 0}

    # ==================== 分类列表 ====================

    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'parse': 0, 'jx': 0}
        page = int(pg) if pg else 1
        try:
            url = f'{self.site}/i/{tid}.html'
            if page > 1:
                url = f'{self.site}/i/{tid}-{page}.html'

            html = self._get(url)
            if not html:
                return result

            box_pattern = r'<div[^>]*class="stui-vodlist__box"[^>]*>(.*?)</div>\s*</li>'
            boxes = re.findall(box_pattern, html, re.DOTALL)
            if not boxes:
                box_pattern = r'<div[^>]*class="stui-vodlist__box"[^>]*>(.*?)</div>'
                boxes = re.findall(box_pattern, html, re.DOTALL)

            for box in boxes:
                title_m = re.search(r'title="([^"]+)"', box)
                title = title_m.group(1) if title_m else ''
                href_m = re.search(r'href="(/dj/\d+\.html)"', box)
                href = href_m.group(1) if href_m else ''
                vid = self.getVid(href)
                if not vid:
                    continue

                pic_m = re.search(r'data-original="([^"]+)"', box)
                pic = pic_m.group(1) if pic_m else ''
                note_m = re.search(r'class="pic-text[^"]*"[^>]*>([^<]+)</span>', box)
                note = note_m.group(1).strip() if note_m else ''

                if title:
                    result['list'].append({
                        'vod_id': vid,
                        'vod_name': title,
                        'vod_pic': pic,
                        'vod_remarks': note
                    })

        except Exception as e:
            print(f'[{self.getName()}] categoryContent error: {e}')

        result['page'] = page
        result['pagecount'] = page + 1 if len(result['list']) > 0 else page
        result['limit'] = len(result['list'])
        result['total'] = len(result['list'])
        return result

    # ==================== 详情页 ====================

    def detailContent(self, ids):
        result = {'list': [], 'parse': 0, 'jx': 0}
        vid = ids[0] if ids else ''
        if not vid:
            return result
        try:
            url = f'{self.site}/dj/{vid}.html'
            html = self._get(url)
            if not html:
                return result

            # 标题
            title = ''
            title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if title_m:
                title = self._extract_text(title_m.group(1))

            # 图片：优先og:image
            pic = ''
            og_img = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
            if og_img:
                pic = og_img.group(1)
            else:
                img_m = re.search(r'<img[^>]+class="[^"]*img[^"]*"[^>]+src="([^"]+)"', html)
                if img_m:
                    pic = img_m.group(1)

            # 简介
            desc = ''
            desc_m = re.search(r'class="detail-content"[^>]*>(.*?)</div>', html, re.DOTALL)
            if desc_m:
                desc = self._extract_text(desc_m.group(1))

            # 元数据
            actor = ''
            director = ''
            year = ''
            area = ''
            actor_m = re.search(r'主演[：:]\s*([^<\n]+)', html)
            if actor_m:
                actor = actor_m.group(1).strip()
            director_m = re.search(r'导演[：:]\s*([^<\n]+)', html)
            if director_m:
                director = director_m.group(1).strip()
            year_m = re.search(r'年份[：:]\s*(\d{4})', html)
            if year_m:
                year = year_m.group(1)
            area_m = re.search(r'地区[：:]\s*([^<\n]+)', html)
            if area_m:
                area = area_m.group(1).strip()

            # 播放线路和集数
            play_from = []
            play_url = []

            # 提取线路名称
            source_labels = []
            source_pattern = r'<a[^>]+href="#down\d+-2"[^>]*>([^<]+)</a>'
            sources = re.findall(source_pattern, html)
            for s in sources:
                s = s.strip()
                if s:
                    source_labels.append(s)

            # 提取各线路下的播放链接
            # 每个tab-pane对应一个线路
            tab_pattern = r'<div[^>]*id="down(\d+)-2"[^>]*class="tab-pane[^"]*"[^>]*>(.*?)</div>\s*</div>'
            tabs = re.findall(tab_pattern, html, re.DOTALL)
            if not tabs:
                # 更宽松的模式
                tab_pattern = r'<div[^>]*id="down\d+-2"[^>]*>(.*?)</ul>'
                tabs_raw = re.findall(tab_pattern, html, re.DOTALL)
                tabs = [(str(i), t) for i, t in enumerate(tabs_raw)]

            for i, (sid, tab_html) in enumerate(tabs):
                line_name = source_labels[i] if i < len(source_labels) else f'线路{sid}'
                ep_links = re.findall(r'<a[^>]+href="(/play/\d+-\d+-\d+\.html)"[^>]*>([^<]+)</a>', tab_html)
                eps = []
                for href, ep_name in ep_links:
                    eps.append(f'{ep_name.strip()}${href}')
                if eps:
                    play_from.append(line_name)
                    play_url.append('#'.join(eps))

            # 如果上面没匹配到，尝试全局匹配播放链接
            if not play_from:
                all_plays = re.findall(r'<a[^>]+href="(/play/\d+-\d+-\d+\.html)"[^>]*>([^<]+)</a>', html)
                if all_plays:
                    ep_parts = []
                    for href, ep_name in all_plays:
                        ep_parts.append(f'{ep_name.strip()}${href}')
                    if ep_parts:
                        play_from.append('默认线路')
                        play_url.append('#'.join(ep_parts))

            vod = {
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'type_name': '',
                'vod_year': year,
                'vod_area': area,
                'vod_remarks': '',
                'vod_actor': actor,
                'vod_director': director,
                'vod_content': desc,
                'vod_play_from': '$$$'.join(play_from) if play_from else '',
                'vod_play_url': '$$$'.join(play_url) if play_url else '',
            }
            result['list'].append(vod)

        except Exception as e:
            print(f'[{self.getName()}] detailContent error: {e}')
        return result

    # ==================== 搜索 ====================

    def searchContent(self, key, pg, filter=False):
        """搜索：站点无独立搜索页，用分类数据本地过滤兜底"""
        result = {
            'list': [],
            'page': int(pg) if pg else 1,
            'pagecount': 1,
            'limit': 0,
            'total': 0
        }
        if not key:
            return result

        try:
            seen = set()
            # 从所有分类中搜索
            for tid in self.cateManual.keys():
                url = f'{self.site}/i/{tid}.html'
                html = self._get(url)
                if not html:
                    continue

                box_pattern = r'<div[^>]*class="stui-vodlist__box"[^>]*>(.*?)</div>\s*</li>'
                boxes = re.findall(box_pattern, html, re.DOTALL)
                if not boxes:
                    box_pattern = r'<div[^>]*class="stui-vodlist__box"[^>]*>(.*?)</div>'
                    boxes = re.findall(box_pattern, html, re.DOTALL)

                for box in boxes:
                    title_m = re.search(r'title="([^"]+)"', box)
                    title = title_m.group(1) if title_m else ''
                    if key not in title:
                        continue

                    href_m = re.search(r'href="(/dj/\d+\.html)"', box)
                    href = href_m.group(1) if href_m else ''
                    vid = self.getVid(href)
                    if not vid or vid in seen:
                        continue
                    seen.add(vid)

                    pic_m = re.search(r'data-original="([^"]+)"', box)
                    pic = pic_m.group(1) if pic_m else ''
                    note_m = re.search(r'class="pic-text[^"]*"[^>]*>([^<]+)</span>', box)
                    note = note_m.group(1).strip() if note_m else ''

                    result['list'].append({
                        'vod_id': vid,
                        'vod_name': title,
                        'vod_pic': pic,
                        'vod_remarks': note
                    })

            result['total'] = len(result['list'])
            result['limit'] = len(result['list'])

        except Exception as e:
            print(f'[{self.getName()}] searchContent error: {e}')

        return result

    # ==================== 播放解析 ====================

    def playerContent(self, flag, id, vipFlags):
        """播放地址解析：从播放页提取m3u8直链"""
        result = {}
        try:
            play_url = id
            if id and not id.startswith('http'):
                play_url = self.site + id

            r = self.session.get(play_url, timeout=15, verify=False)
            r.encoding = 'utf-8'
            text = r.text

            video_url = ''

            # 模式1: JS变量 now（最常见）
            m = re.search(r'var\s+now\s*=\s*"([^"]+\.m3u8[^"]*)"', text)
            if m:
                video_url = m.group(1)

            # 模式2: 其他常见变量
            if not video_url:
                patterns = [
                    r'var\s+url\s*=\s*"([^"]+\.m3u8[^"]*)"',
                    r'var\s+play_url\s*=\s*"([^"]+\.m3u8[^"]*)"',
                    r'src:\s*"([^"]+\.m3u8[^"]*)"',
                    r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"',
                ]
                for pat in patterns:
                    m = re.search(pat, text)
                    if m:
                        video_url = m.group(1)
                        break

            # 模式3: 全局匹配m3u8链接
            if not video_url:
                all_urls = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', text)
                if all_urls:
                    video_url = all_urls[0]

            if video_url:
                result['parse'] = 0
                result['url'] = video_url
                result['jx'] = 0
                result['header'] = {
                    'User-Agent': self.session.headers['User-Agent'],
                    'Referer': self.site + '/'
                }
            else:
                result['parse'] = 1
                result['url'] = play_url
                result['jx'] = 0
                result['header'] = {
                    'User-Agent': self.session.headers['User-Agent'],
                    'Referer': self.site + '/'
                }

        except Exception as e:
            print(f'[{self.getName()}] playerContent error: {e}')
            result['parse'] = 1
            result['url'] = id if id.startswith('http') else self.site + id
            result['jx'] = 0
            result['header'] = {
                'User-Agent': self.session.headers['User-Agent'],
                'Referer': self.site + '/'
            }
        return result

    def localProxy(self, params):
        return [200, "video/MP2T", {}, ""]

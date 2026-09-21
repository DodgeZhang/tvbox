# -*- coding: utf-8 -*-
# 本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
# 严禁将其用于任何商业用途，下载后请于 24 小时内删除。

import sys
import re
import json
import urllib.parse
from base.spider import Spider

sys.path.append('..')

class Spider(Spider):
    host = 'https://www.59v.net'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.59v.net/'
    }

    def init(self, extend=''):
        pass

    def homeContent(self, filter):
        classes = [
            {'type_id': '1', 'type_name': '电影'},
            {'type_id': '2', 'type_name': '电视剧'},
            {'type_id': '3', 'type_name': '综艺'},
            {'type_id': '4', 'type_name': '动漫'}
        ]
        return {'class': classes}

    def homeVideoContent(self):
        videos = []
        try:
            html = self.fetch(self.host + '/', headers=self.headers).text
            # 轮播图
            slides = re.findall(r'<div class="swiper-slide">.*?</div>', html, re.S)
            for slide in slides:
                id_match = re.search(r'href="/voddetail/(\d+)/"', slide)
                if not id_match:
                    continue
                vid = id_match.group(1)
                img_match = re.search(r'url\(([^)]+)\)', slide)
                title_match = re.search(r'<div class="v-title"><span>([^<]*)</span>', slide)
                remark_match = re.search(r'<p>([^<]*(?:集|全|更新|HD|BD|正片|预告)[^<]*)</p>', slide)
                videos.append({
                    'vod_id': vid,
                    'vod_name': title_match.group(1).strip() if title_match else '',
                    'vod_pic': self._fix_url(img_match.group(1)) if img_match else '',
                    'vod_remarks': remark_match.group(1).strip() if remark_match else ''
                })
            # 普通列表
            blocks = re.findall(r'(<a[^>]*class="module-poster-item[^"]*"[^>]*>.*?</a>)', html, re.S)
            for block in blocks:
                vod = self._extract_vod_from_poster_block(block)
                if vod and not any(v['vod_id'] == vod['vod_id'] for v in videos):
                    videos.append(vod)
        except Exception as e:
            print(f'[{self.host}] homeVideoContent error: {e}')
        return {'list': videos}

    def categoryContent(self, tid, pg, filter, extend):
        videos = []
        try:
            if pg == 1:
                url = f'{self.host}/vodshow/{tid}-----------.html'
            else:
                url = f'{self.host}/vodshow/{tid}--------{pg}---.html'
            html = self.fetch(url, headers=self.headers).text
            blocks = re.findall(r'(<a[^>]*class="module-poster-item[^"]*"[^>]*>.*?</a>)', html, re.S)
            for block in blocks:
                vod = self._extract_vod_from_poster_block(block)
                if vod:
                    videos.append(vod)
            # 分页
            pages = re.findall(r'href="/vodshow/[^"]*--------(\d+)[^"]*\.html"', html)
            pagecount = max(int(p) for p in pages) if pages else 1
        except Exception as e:
            print(f'[{self.host}] categoryContent error: {e}')
            pagecount = 1
        return {'list': videos, 'page': pg, 'pagecount': pagecount, 'limit': 72, 'total': pagecount * 72}

    def detailContent(self, ids):
        result = []
        try:
            vid = ids[0] if isinstance(ids, list) else ids
            url = f'{self.host}/voddetail/{vid}/'
            html = self.fetch(url, headers=self.headers).text

            # 标题
            title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            title = title_match.group(1).strip() if title_match else ''

            # 图片（JSON-LD）
            img = ''
            jsonld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
            if jsonld_match:
                try:
                    jsonld = json.loads(jsonld_match.group(1))
                    for item in jsonld.get('@graph', []):
                        if item.get('@type') == 'VideoObject':
                            thumbs = item.get('thumbnailUrl', [])
                            if thumbs:
                                img = thumbs[0]
                                break
                except:
                    pass

            # 元数据
            info_contents = re.findall(r'class="module-info-item-content"[^>]*>(.*?)</div>', html, re.S)
            info_texts = [re.sub(r'<[^>]+>', '', c).strip() for c in info_contents]
            director = info_texts[0] if len(info_texts) > 0 else ''
            actor = info_texts[2] if len(info_texts) > 2 else ''
            year = info_texts[5] if len(info_texts) > 5 else ''
            status = info_texts[7] if len(info_texts) > 7 else ''

            # 类型、地区
            type_name = ''
            area = ''
            tag_links = re.findall(r'class="module-info-tag-link"[^>]*>(.*?)</div>', html, re.S)
            for tag in tag_links:
                texts = re.findall(r'>([^<]+)<', tag)
                for t in texts:
                    t = t.strip()
                    if t in ['剧情','动作','喜剧','爱情','科幻','奇幻','恐怖','悬疑','冒险','犯罪','惊悚','战争','动画','纪录片','歌舞','灾难','武侠','古装','网络片']:
                        type_name = t if not type_name else type_name + ',' + t
                    elif t in ['大陆','香港','台湾','日本','韩国','美国','英国','泰国','印度','法国','德国','意大利','西班牙','俄罗斯','加拿大','澳大利亚','其他','欧美']:
                        area = t

            # 简介
            desc = ''
            desc_match = re.search(r'class="module-info-introduction-content"[^>]*>(.*?)</div>', html, re.S)
            if desc_match:
                desc = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()

            # 线路名
            line_names = []
            for val in re.findall(r'data-dropdown-value="([^"]*)"', html):
                if val and val not in line_names:
                    line_names.append(val)
            if not line_names:
                line_names = ['默认线路']

            # 播放列表
            play_lists = re.findall(r'<div class="module-play-list">(.*?)</div>', html, re.S)
            line_urls = []
            for pl in play_lists:
                eps = re.findall(r'href="/play/(\d+-\d+-\d+)/"[^>]*>\s*<span>([^<]*)</span>', pl)
                ep_parts = []
                for play_id, name in eps:
                    ep_name = name.strip() if name.strip() else '第' + play_id.split('-')[-1] + '集'
                    ep_parts.append(f'{ep_name}${play_id}')
                if ep_parts:
                    line_urls.append('#'.join(ep_parts))

            # 对齐线路名和列表数
            if len(line_names) > len(line_urls):
                line_names = line_names[:len(line_urls)]
            elif len(line_names) < len(line_urls):
                for i in range(len(line_urls) - len(line_names)):
                    line_names.append(f'线路{len(line_names) + 1}')

            video = {
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': img,
                'vod_year': year,
                'vod_area': area,
                'vod_actor': actor,
                'vod_director': director,
                'type_name': type_name,
                'vod_remarks': status,
                'vod_content': desc,
                'vod_play_from': '$$$'.join(line_names),
                'vod_play_url': '$$$'.join(line_urls)
            }
            result.append(video)
        except Exception as e:
            print(f'[{self.host}] detailContent error: {e}')
        return {'list': result}

    def searchContent(self, key, quick, pg='1'):
        videos = []
        try:
            wd = urllib.parse.quote(key)
            if int(pg) == 1:
                url = f'{self.host}/vodsearch/-------------.html?wd={wd}'
            else:
                url = f'{self.host}/vodsearch/--------{pg}---.html?wd={wd}'
            html = self.fetch(url, headers=self.headers).text
            blocks = re.findall(r'(<a[^>]*class="module-card-item-poster"[^>]*>.*?</a>)', html, re.S)
            for block in blocks:
                id_match = re.search(r'href="/voddetail/(\d+)/"', block)
                if not id_match:
                    continue
                remark_match = re.search(r'class="module-item-note">([^<]*)</div>', block)
                img_match = re.search(r'data-original="([^"]*)"', block)
                if not img_match:
                    img_match = re.search(r'src="([^"]*upload[^"]*)"', block)
                title_match = re.search(r'alt="([^"]*)"', block)
                videos.append({
                    'vod_id': id_match.group(1),
                    'vod_name': title_match.group(1) if title_match else '',
                    'vod_pic': self._fix_url(img_match.group(1)) if img_match else '',
                    'vod_remarks': remark_match.group(1).strip() if remark_match else ''
                })
            pages = re.findall(r'href="/vodsearch/[^"]*--------(\d+)[^"]*\.html\?wd=', html)
            pagecount = max(int(p) for p in pages) if pages else 1
        except Exception as e:
            print(f'[{self.host}] searchContent error: {e}')
            pagecount = 1
        return {'list': videos, 'page': int(pg), 'pagecount': pagecount, 'limit': 72, 'total': pagecount * 72}

    def playerContent(self, flag, id, vipflags):
        try:
            url = f'{self.host}/play/{id}/'
            html = self.fetch(url, headers=self.headers).text
            player_match = re.search(r'"url":"([^"]*\.m3u8[^"]*)"', html)
            if player_match:
                play_url = player_match.group(1).replace('\\/', '/')
                return {
                    'parse': '0',
                    'url': play_url,
                    'header': {
                        'User-Agent': self.headers['User-Agent'],
                        'Referer': self.host + '/'
                    }
                }
        except Exception as e:
            print(f'[{self.host}] playerContent error: {e}')
        return {'parse': '1', 'url': id, 'header': {'User-Agent': self.headers['User-Agent']}}

    def getName(self):
        return '永乐视频'

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        pass

    def _fix_url(self, url):
        if not url:
            return ''
        if url.startswith('http'):
            return url
        return self.host + url

    def _extract_vod_from_poster_block(self, block):
        id_match = re.search(r'href="/voddetail/(\d+)/"', block)
        if not id_match:
            return None
        vid = id_match.group(1)
        title_match = re.search(r'title="([^"]*)"', block)
        remark_match = re.search(r'class="module-item-note">([^<]*)</div>', block)
        img_match = re.search(r'data-original="([^"]*)"', block)
        if not img_match:
            img_match = re.search(r'src="([^"]*upload[^"]*)"', block)
        return {
            'vod_id': vid,
            'vod_name': title_match.group(1) if title_match else '',
            'vod_pic': self._fix_url(img_match.group(1)) if img_match else '',
            'vod_remarks': remark_match.group(1).strip() if remark_match else ''
        }

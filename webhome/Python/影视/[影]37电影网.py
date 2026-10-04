# coding=utf-8
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
源名称：37电影网 (适配版)
说明：基于初见影视模板结构，适配 https://www.37dyw.com/
     演示如何使用lxml和正则表达式从静态页面提取数据。
"""

import sys
import re
import json
import time
import urllib.parse
import requests
from urllib.parse import quote
from lxml import etree

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider(object):
        pass

try:
    requests.packages.urllib3.disable_warnings()
except Exception:
    pass


class Spider(Spider):
    # ==================== 基础配置 ====================
    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.name = "37电影网"
        self.host = "https://www.37dyw.com"
        self.header = {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.host + '/'
        }
        self._session = None
        self._last = {}

    # ==================== 接口方法 ====================
    def getName(self):
        return self.name

    def init(self, extend=""):
        return

    def isVideoFormat(self, url):
        if not url:
            return False
        u = url.split('?')[0].split('#')[0].lower()
        return any(u.endswith(x) for x in
                   ['.m3u8', '.mp4', '.flv', '.ts', '.mkv', '.avi', '.mov', '.webm', '.mpd'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return

    def localProxy(self, params):
        return [200, "video/MP2T", {}, ""]

    # ==================== 工具函数层 ====================
    def _sess(self):
        if self._session is None:
            s = requests.Session()
            s.trust_env = False
            self._session = s
        return self._session

    def _get(self, url, timeout=15, headers=None, retry=2):
        """增强的GET请求，带重试机制"""
        for i in range(retry + 1):
            try:
                r = self._sess().get(url, headers=headers or self.header,
                                     timeout=timeout, verify=False)
                r.encoding = 'utf-8'
                if r.status_code == 404:
                    return ''
                if r.status_code == 200 and r.text:
                    return r.text
            except Exception:
                pass
            if i < retry:
                time.sleep(0.6 * (i + 1))
        return ''

    def _fix(self, url):
        """补全URL"""
        if not url:
            return ''
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.host + url
        return url

    def _txt(self, el):
        """获取元素的文本内容"""
        if el is None:
            return ''
        return ''.join(el.itertext()).strip()

    def _pic(self, el):
        """提取图片URL"""
        if el is None:
            return ''
        imgs = [el] if el.tag == 'img' else el.xpath('.//img')
        if not imgs:
            return ''
        img = imgs[0]
        pic = (img.get('data-original') or img.get('data-src')
               or img.get('data-echo') or img.get('src') or '')
        if pic.startswith('data:image') or 'load.gif' in pic:
            pic = img.get('data-original') or img.get('data-src') or ''
        return self._fix(pic)

    def _throttle(self, key='search', gap=3.2):
        """请求频率控制"""
        last = self._last.get(key, 0)
        wait = gap - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        self._last[key] = time.time()

    def _parse_item(self, node):
        """解析单个影片条目"""
        a = None
        if node.tag == 'a':
            a = node
        else:
            for xp in ('.//a[contains(@class,"module-card-item-poster")]',
                       './/a[contains(@class,"module-item-poster")]',
                       './/a[contains(@href,"/voddetail/")]'):
                got = node.xpath(xp)
                if got:
                    a = got[0]
                    break
        if a is None:
            return None

        # 提取ID
        m = re.search(r'/voddetail/(\d+)\.html', a.get('href', ''))
        if not m:
            return None
        vid = m.group(1)

        # 提取名称
        name = (a.get('title') or '').strip()
        if not name:
            for xp in ('.//div[contains(@class,"module-poster-item-title")]',
                       './/div[contains(@class,"module-card-item-title")]'):
                got = node.xpath(xp)
                if got:
                    name = self._txt(got[0])
                    break
        if not name:
            imgs = a.xpath('.//img')
            if imgs:
                name = (imgs[0].get('alt') or '').strip()
        if not name:
            return None

        pic = self._pic(a)
        if not pic:
            pic = self._pic(node)

        # 提取备注（如更新状态）
        note = node.xpath('.//div[contains(@class,"module-item-note")]/text()')
        remark = note[0].strip() if note else ''

        return {"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": remark}

    def _parse_list(self, html):
        """解析列表页"""
        out, seen = [], set()
        if not html:
            return out
        try:
            root = etree.HTML(html)
            # 精确匹配 class
            cls = ('//*[contains(concat(" ", normalize-space(@class), " "), " %s ")]')
            nodes = root.xpath(cls % 'module-card-item')
            if not nodes:
                nodes = root.xpath(cls % 'module-item')
            if not nodes:
                nodes = root.xpath('//a[contains(@href,"/voddetail/")]')
            for n in nodes:
                try:
                    v = self._parse_item(n)
                    if v and v['vod_id'] not in seen:
                        seen.add(v['vod_id'])
                        out.append(v)
                except Exception:
                    continue
        except Exception:
            pass
        return out

    def _pagecount(self, html, default=1):
        """提取总页数"""
        total = 0
        try:
            for m in re.finditer(r'/vod(?:show|search)/[^"\']*?-(\d+)-{3}\.html', html):
                total = max(total, int(m.group(1)))
            root = etree.HTML(html)
            for a in root.xpath('//a[contains(@class,"page-link")]'):
                t = self._txt(a)
                if t.isdigit():
                    total = max(total, int(t))
        except Exception:
            pass
        return total or default

    def _fetch_list(self, url, tries=3, key=None):
        """获取列表页并解析"""
        html = ''
        for i in range(tries):
            if key:
                self._throttle(key)
            html = self._get(url)
            vlist = self._parse_list(html)
            if vlist:
                return html, vlist
            if i < tries - 1:
                time.sleep(0.8 * (i + 1))
        return html, self._parse_list(html)

    # ==================== 首页 ====================
    def homeContent(self, filter):
        """首页内容"""
        classes = [
            {"type_name": "电影", "type_id": "1"},
            {"type_name": "电视剧", "type_id": "2"},
            {"type_name": "综艺", "type_id": "3"},
            {"type_name": "动漫", "type_id": "4"},
            {"type_name": "国产剧", "type_id": "13"},
            {"type_name": "港台剧", "type_id": "14"},
            {"type_name": "日韩剧", "type_id": "15"},
            {"type_name": "欧美剧", "type_id": "16"},
        ]
        result = {
            "class": classes,
            "filters": self.FILTERS,
            "list": self.homeVideoContent().get('list', []),
            "parse": 0,
            "jx": 0
        }
        return result

    def homeVideoContent(self):
        """首页视频列表"""
        _, vlist = self._fetch_list(self.host + '/', tries=2)
        if not vlist:
            _, vlist = self._fetch_list(self.host + '/vodshow/1-----------.html', tries=2)
        return {"list": vlist[:60], "parse": 0, "jx": 0}

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, extend):
        """分类内容"""
        page = int(pg) if str(pg).isdigit() and int(pg) > 0 else 1
        try:
            if isinstance(extend, str) and extend:
                try:
                    extend = json.loads(extend)
                except Exception:
                    extend = {}
            if not isinstance(extend, dict):
                extend = {}

            real_tid = str(extend.get('tid') or tid)
            segs = [''] * 12
            segs[0] = real_tid
            segs[1] = quote(extend.get('area', ''))
            segs[2] = extend.get('by', '') or 'time'
            segs[3] = quote(extend.get('class', ''))
            segs[4] = quote(extend.get('lang', ''))
            segs[5] = quote(extend.get('letter', ''))
            segs[8] = str(page)
            segs[11] = quote(extend.get('year', ''))

            url = '%s/vodshow/%s.html' % (self.host, '-'.join(segs))
            html, vlist = self._fetch_list(url)
            pc = self._pagecount(html, 1 if not vlist else page)

            return {
                'list': vlist,
                'page': page,
                'pagecount': pc,
                'limit': len(vlist) or 45,
                'total': (pc * len(vlist)) if vlist else 0
            }
        except Exception:
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 45, 'total': 0}

    # ==================== 详情 ====================
    def detailContent(self, ids):
        """详情内容"""
        try:
            vid = ids[0] if isinstance(ids, (list, tuple)) else ids
            vid = str(vid).split('/')[-1].replace('.html', '')
            html = self._get('%s/voddetail/%s.html' % (self.host, vid))
            if not html:
                return {'list': [], 'parse': 0, 'jx': 0}
            root = etree.HTML(html)

            # 标题
            name = ''
            h1 = root.xpath('//div[contains(@class,"module-info-heading")]/h1')
            if h1:
                name = self._txt(h1[0])
            if not name:
                t = root.xpath('//title/text()')
                if t:
                    name = re.split(r'[-_|]', t[0])[0].strip()

            # 封面
            pic = ''
            box = root.xpath('//div[contains(@class,"module-info-poster")]')
            if box:
                pic = self._pic(box[0])

            # 标签: 年份 / 地区 / 剧情
            year = area = vclass = ''
            for a in root.xpath('//div[contains(@class,"module-info-tag")]//a'):
                t = self._txt(a)
                href = a.get('href', '')
                if re.match(r'^\d{4}$', t):
                    year = year or t
                elif re.search(r'/vodshow/\d+-[^-]+-', href):
                    area = area or t
                elif re.search(r'/vodshow/\d+---[^-]+-', href):
                    vclass = vclass or t
                elif not area and t:
                    area = t

            # 导演 / 主演 / 备注
            director = actor = remarks = ''
            for item in root.xpath('//div[contains(@class,"module-info-item")]'):
                key = item.xpath('./span[contains(@class,"module-info-item-title")]/text()')
                key = key[0].strip() if key else ''
                cont = item.xpath('.//div[contains(@class,"module-info-item-content")]') or \
                       item.xpath('.//p[contains(@class,"module-info-item-content")]')
                if not cont:
                    continue
                links = [x.strip() for x in cont[0].xpath('.//a/text()') if x.strip()]
                val = ','.join(links) if links else self._txt(cont[0])
                if '导演' in key:
                    director = val
                elif '主演' in key:
                    actor = val
                elif '备注' in key or '更新' in key:
                    remarks = remarks or val

            # 简介
            content = ''
            desc = root.xpath('//div[contains(@class,"module-info-introduction-content")]')
            if desc:
                content = self._txt(desc[0])
            content = re.sub(r'\s*展开\s*$', '', content).strip()

            # 播放线路
            froms = root.xpath('//div[contains(@class,"module-tab-item")]/@data-dropdown-value')
            if not froms:
                froms = [x.strip() for x in
                         root.xpath('//div[contains(@class,"module-tab-item")]//span/text()')]
            froms = [f.strip() for f in froms if f and f.strip()]

            boxes, seen = [], set()
            cls = ('//*[contains(concat(" ", normalize-space(@class), " "), " %s ")]')
            for b in root.xpath(cls % 'module-play-list'):
                links = b.xpath('.//a[contains(@href,"/vodplay/")]')
                if not links:
                    continue
                key = links[0].get('href', '')
                if key in seen:
                    continue
                seen.add(key)
                boxes.append(links)

            play_from, play_url = [], []
            for i, links in enumerate(boxes):
                eps = []
                for a in links:
                    ep = self._txt(a)
                    href = a.get('href', '')
                    if not ep or not href:
                        continue
                    eps.append('%s$%s' % (ep.replace('$', ' ').replace('#', ' '),
                                          self._fix(href)))
                if not eps:
                    continue
                play_from.append(froms[i] if i < len(froms) else ('线路%d' % (i + 1)))
                play_url.append('#'.join(eps))

            detail = {
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "type_name": vclass,
                "vod_year": year,
                "vod_area": area,
                "vod_remarks": remarks,
                "vod_actor": actor,
                "vod_director": director,
                "vod_content": content,
                "vod_play_from": "$$$".join(play_from) if play_from else "默认",
                "vod_play_url": "$$$".join(play_url)
            }
            return {'list': [detail], 'parse': 0, 'jx': 0}
        except Exception:
            return {'list': [], 'parse': 0, 'jx': 0}

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags):
        """播放内容"""
        play_page = id if str(id).startswith('http') else self._fix(id)
        headers = {
            'User-Agent': self.header['User-Agent'],
            'Referer': self.host + '/'
        }
        result = {'parse': 1, 'url': play_page, 'playUrl': '', 'header': json.dumps(headers)}
        try:
            html = self._get(play_page)
            # 尝试从播放页提取真实视频地址
            found = re.findall(r'(https?:[^\s"\'<>\\]+\.(?:m3u8|mp4)[^\s"\'<>\\]*)', html)
            if found:
                url = found[0].replace('\\/', '/')
                url = self._fix(url)
                result['url'] = url
                result['parse'] = 0 if self.isVideoFormat(url) else 1
        except Exception:
            pass
        return result

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg='1'):
        """搜索内容"""
        page = int(pg) if str(pg).isdigit() and int(pg) > 0 else 1
        try:
            segs = [''] * 14
            segs[0] = quote(str(key))
            segs[10] = str(page)
            url = '%s/vodsearch/%s.html' % (self.host, '-'.join(segs))
            html, vlist = self._fetch_list(url, key='search')
            pc = self._pagecount(html, page if vlist else 1)

            # 回退: 如果无结果，尝试联想接口
            if not vlist and page == 1:
                try:
                    api = '%s/index.php/ajax/suggest?mid=1&wd=%s&limit=30' % (
                        self.host, quote(str(key)))
                    j = json.loads(self._get(api))
                    for it in (j.get('list') or []):
                        vlist.append({
                            "vod_id": str(it.get('id', '')),
                            "vod_name": it.get('name', ''),
                            "vod_pic": self._fix(it.get('pic', '')),
                            "vod_remarks": ""
                        })
                    pc = 1
                except Exception:
                    pass

            return {'list': vlist, 'page': page, 'pagecount': pc,
                    'limit': len(vlist) or 16, 'total': pc * (len(vlist) or 16)}
        except Exception:
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 16, 'total': 0}

    # ==================== 筛选器 ====================
    # 此处为占位筛选器，实际使用时可根据网站情况填充
    FILTERS = json.loads(r'''{}''')
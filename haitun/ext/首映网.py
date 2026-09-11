# -*- coding: utf-8 -*-
"""
TVBox Python 爬虫 - 首映网 (mjtechinstall.com)
基于 MacCMS v10 + template101 模板

优化项:
  1. Session 复用 + 连接池, 减少 TCP 握手
  2. 全量正则预编译, 降低解析耗时
  3. 首页单请求解析多区块, 提升加载速度
  4. 子分类(type_id 直连) + 地区/年份筛选(vodshow 回退)
  5. 播放页多模式兼容(player_aaaa / iframe / js 变量)
  6. 剧集自动按集数正序排序

注: 子分类 ID 为基于 MacCMS 常见配置推测, 动漫的 48/49 已从首页确认。
   若某些子分类无内容, 请根据实际页面调整 SUB_FILTERS 中的 v 值。
"""

import sys
import re
import json
import base64
import urllib3

sys.path.append('..')

try:
    import requests as _requests
except ImportError:
    _requests = None

from base.spider import Spider

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Spider(Spider):
    HOST = 'https://www.mjtechinstall.com'

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.mjtechinstall.com/',
    }

    # ==================== 分类配置 ====================

    CATEGORIES = [
        {'type_id': '1',  'type_name': '电影'},
        {'type_id': '2',  'type_name': '电视剧'},
        {'type_id': '4',  'type_name': '动漫'},
        {'type_id': '3',  'type_name': '综艺'},
        {'type_id': '9',  'type_name': '短剧'},
        {'type_id': '51', 'type_name': '即将上映'},
    ]

    # 子分类: v 值为子分类的独立 type_id, 可直接用 /mjteadtype/{v}.html 访问
    # 动漫 48/49 已从首页 HTML 确认, 其余为 MacCMS 常见默认 ID 推测
    SUB_FILTERS = {
        '1': [  # 电影
            {'n': '全部',   'v': ''},
            {'n': '动作片', 'v': '6'},
            {'n': '喜剧片', 'v': '7'},
            {'n': '爱情片', 'v': '8'},
            {'n': '科幻片', 'v': '9'},
            {'n': '恐怖片', 'v': '10'},
            {'n': '剧情片', 'v': '11'},
            {'n': '战争片', 'v': '12'},
            {'n': '纪录片', 'v': '20'},
            {'n': '悬疑片', 'v': '21'},
            {'n': '犯罪片', 'v': '22'},
            {'n': '奇幻片', 'v': '24'},
        ],
        '2': [  # 电视剧
            {'n': '全部',   'v': ''},
            {'n': '国产剧', 'v': '13'},
            {'n': '港台剧', 'v': '14'},
            {'n': '日韩剧', 'v': '15'},
            {'n': '欧美剧', 'v': '16'},
            {'n': '海外剧', 'v': '25'},
            {'n': '泰国剧', 'v': '26'},
        ],
        '4': [  # 动漫 (48/49 已确认)
            {'n': '全部',     'v': ''},
            {'n': '国内动漫', 'v': '48'},
            {'n': '海外动漫', 'v': '49'},
            {'n': '日本动漫', 'v': '50'},
            {'n': '欧美动漫', 'v': '52'},
        ],
        '3': [  # 综艺
            {'n': '全部',     'v': ''},
            {'n': '大陆综艺', 'v': '27'},
            {'n': '港台综艺', 'v': '28'},
            {'n': '日韩综艺', 'v': '29'},
            {'n': '欧美综艺', 'v': '30'},
        ],
        '9':  [{'n': '全部', 'v': ''}],
        '51': [{'n': '全部', 'v': ''}],
    }

    AREA_FILTER = {
        'key': 'area', 'name': '地区',
        'value': [
            {'n': '全部', 'v': ''},
            {'n': '中国大陆', 'v': '中国大陆'},
            {'n': '香港', 'v': '香港'},
            {'n': '台湾', 'v': '台湾'},
            {'n': '日本', 'v': '日本'},
            {'n': '韩国', 'v': '韩国'},
            {'n': '美国', 'v': '美国'},
            {'n': '英国', 'v': '英国'},
            {'n': '泰国', 'v': '泰国'},
            {'n': '其他', 'v': '其他'},
        ]
    }

    YEAR_FILTER = {
        'key': 'year', 'name': '年份',
        'value': [
            {'n': '全部', 'v': ''},
            {'n': '2026', 'v': '2026'},
            {'n': '2025', 'v': '2025'},
            {'n': '2024', 'v': '2024'},
            {'n': '2023', 'v': '2023'},
            {'n': '2022', 'v': '2022'},
            {'n': '2021', 'v': '2021'},
            {'n': '2020', 'v': '2020'},
            {'n': '2019', 'v': '2019'},
            {'n': '2018', 'v': '2018'},
            {'n': '2017', 'v': '2017'},
            {'n': '2016', 'v': '2016'},
            {'n': '2015', 'v': '2015'},
        ]
    }

    # ==================== 预编译正则 ====================

    # 列表页卡片
    _RE_CARD = re.compile(r'<article class="t101-card">(.*?)</article>', re.S)
    _RE_CARD_LINK = re.compile(
        r'<a class="t101-card-poster" href="/mjtead/(\d+)\.html" title="([^"]*)"', re.S)
    _RE_CARD_IMG = re.compile(r'data-original="([^"]*)"', re.S)
    _RE_CARD_BADGE = re.compile(r'<span class="t101-card-badge">([^<]*)</span>', re.S)
    _RE_CARD_INFO = re.compile(r'<p>(.*?)</p>', re.S)

    # 分页
    _RE_PAGE_NUM = re.compile(r'class="num"[^>]*>\s*(\d+)/(\d+)\s*<')
    _RE_PAGE_LAST_TYPE = re.compile(r'/mjteadtype/\d+-(\d+)\.html"[^>]*>尾页')
    _RE_PAGE_LAST_SHOW = re.compile(r'/mjteadshow/[^"]*-(\d+)\.html"[^>]*>尾页')
    _RE_PAGE_NEXT = re.compile(r'>下一页<')

    # 详情页
    _RE_H1 = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S)
    _RE_DESC_BLOCK = re.compile(
        r'<div[^>]*class="[^"]*(?:t101-desc|content__desc|vod-content)[^"]*"[^>]*>(.*?)</div>', re.S)
    _RE_DESC_LINE = re.compile(
        r'<span[^>]*>\s*(?:简介|剧情|内容)[：:]\s*</span>\s*(.*?)(?:</p>|<br|<div)', re.S)

    # 详情信息行 (导演/主演/地区/年份等)
    _RE_INFO_DIRECTOR = re.compile(r'(?:导演|導演)[：:]\s*([^<\n]+)', re.S)
    _RE_INFO_ACTOR = re.compile(r'(?:主演|演員)[：:]\s*([^<\n]+)', re.S)
    _RE_INFO_AREA = re.compile(r'(?:地区|地區)[：:]\s*([^<\n]+)', re.S)
    _RE_INFO_YEAR = re.compile(r'(?:年份|年代)[：:]\s*(\d{4})', re.S)
    _RE_INFO_REMARKS = re.compile(r'(?:状态|狀態|更新)[：:]\s*([^<\n]+)', re.S)
    _RE_INFO_TYPE = re.compile(r'(?:分类|類別|类型)[：:]\s*([^<\n]+)', re.S)

    # 播放列表 (template101 / ewave 结构)
    # 线路选项卡: <li class="swiper-slide ewave-tab ..." data-target="#ewave-playlist-N">线路名</li>
    _RE_PLAY_TAB = re.compile(
        r'data-target="#(ewave-playlist-\d+)"[^>]*>([^<]*)<', re.S)
    # 播放列表容器: <ul ... id="ewave-playlist-N" ...> 剧集 </ul>
    _RE_PLAY_UL = re.compile(
        r'id="(ewave-playlist-\d+)"[^>]*>(.*?)</ul>', re.S)
    _RE_PLAY_EPISODE = re.compile(
        r'<a[^>]*href="(/[^"]*play/[^"]*)"[^>]*>(.*?)</a>', re.S)
    _RE_PLAY_EPISODE_LOOSE = re.compile(
        r'<a[^>]*href="(/mjtead/\d+\.html)"[^>]*>.*?(?:播放|立即观看).*?</a>', re.S)

    # 详情页元信息 (template101)
    _RE_DETAIL_KICKER = re.compile(r'class="t101-kicker"[^>]*>([^<]*)<', re.S)
    _RE_DETAIL_META = re.compile(r'class="t101-meta"[^>]*>(.*?)</div>', re.S)
    _RE_DETAIL_META_SPAN = re.compile(r'<span[^>]*>([^<]*)</span>', re.S)
    _RE_DETAIL_LINES = re.compile(r'class="t101-detail-lines"[^>]*>(.*?)</div>', re.S)
    _RE_DETAIL_LINE_ITEM = re.compile(
        r'<span[^>]*>(导演|主演|地区|年份|年代|状态|类型|分类)[^<]*</span>\s*([^<]*)', re.S)
    _RE_DETAIL_DESC_BLOCK = re.compile(
        r'剧情简介.*?class="[^"]*(?:t101-content|content|desc)[^"]*"[^>]*>(.*?)</div>', re.S)

    # 播放页
    _RE_PLAYER_AAAA = re.compile(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*<', re.S)
    _RE_PLAYER_AAAA_LOOSE = re.compile(r'var\s+player_aaaa\s*=\s*(\{.*?\});', re.S)
    _RE_IFRAME_SRC = re.compile(r'<iframe[^>]*src="([^"]*)"', re.S)
    _RE_JS_URL = re.compile(r'"url"\s*:\s*"([^"]+)"', re.S)
    _RE_VAR_URL = re.compile(r"""var\s+(?:url|src|play_url)\s*=\s*["']([^"']+)["']""", re.S)

    # 工具
    _RE_EPISODE_NUM = re.compile(r'第\s*(\d+)\s*[集话期]')
    _RE_ANY_NUM = re.compile(r'(\d+)')
    _RE_HTML_TAG = re.compile(r'<[^>]+>')
    _RE_LAZY_BG = re.compile(r'data-background="([^"]*)"', re.S)

    # ==================== 基础方法 ====================

    def getName(self):
        return "首映网"

    def init(self, cfg=''):
        if _requests is not None:
            self.session = _requests.Session()
            self.session.headers.update(self.HEADERS)
            self.session.verify = False
            adapter = _requests.adapters.HTTPAdapter(
                pool_connections=10, pool_maxsize=10, max_retries=2)
            self.session.mount('https://', adapter)
            self.session.mount('http://', adapter)
        else:
            self.session = None
        return self

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _fetch(self, url):
        """GET 请求并返回 HTML 文本"""
        try:
            if self.session is not None:
                resp = self.session.get(url, timeout=12, allow_redirects=True)
                resp.encoding = 'utf-8'
                return resp.text
            return ''
        except Exception:
            return ''

    def _build_filters(self):
        """构建 TVBox filters 配置"""
        result = {}
        for tid, sub_list in self.SUB_FILTERS.items():
            filters = []
            if len(sub_list) > 1:
                filters.append({'key': 'class', 'name': '类型',
                                'value': [dict(item) for item in sub_list]})
            filters.append(dict(self.AREA_FILTER))
            filters.append(dict(self.YEAR_FILTER))
            result[tid] = filters
        return result

    # ==================== 排序工具 ====================

    def _extract_episode_number(self, name):
        m = self._RE_EPISODE_NUM.search(name)
        if m:
            return int(m.group(1))
        m = self._RE_ANY_NUM.search(name)
        if m:
            return int(m.group(1))
        return 999999

    # ==================== 列表解析 ====================

    def _parse_card_list(self, html):
        """解析 t101-card 视频列表, 返回 TVBox list 格式"""
        videos = []
        if not html:
            return videos

        items = self._RE_CARD.findall(html)
        for item in items:
            m = self._RE_CARD_LINK.search(item)
            if not m:
                continue

            video = {
                'vod_id': m.group(1),
                'vod_name': m.group(2).strip(),
            }

            # 封面: 优先 data-original, 其次 data-background
            m = self._RE_CARD_IMG.search(item)
            if m:
                video['vod_pic'] = m.group(1)
            else:
                m = self._RE_LAZY_BG.search(item)
                if m:
                    video['vod_pic'] = m.group(1)

            # 状态/备注
            m = self._RE_CARD_BADGE.search(item)
            if m:
                video['vod_remarks'] = m.group(1).strip()

            # 年份 · 地区 (可能为 "2026 · 日本"、" · 日本"、"2026" 等)
            m = self._RE_CARD_INFO.search(item)
            if m:
                info = self._RE_HTML_TAG.sub('', m.group(1)).strip()
                parts = [p.strip() for p in info.split('·') if p.strip()]
                for p in parts:
                    if p.isdigit() and len(p) == 4:
                        video['vod_year'] = p
                    elif not video.get('vod_area') and p:
                        video['vod_area'] = p

            videos.append(video)

        return videos

    def _parse_page_count(self, html, current_page):
        """从分页控件解析总页数"""
        m = self._RE_PAGE_NUM.search(html)
        if m:
            return int(m.group(2))
        m = self._RE_PAGE_LAST_TYPE.search(html)
        if m:
            return int(m.group(1))
        m = self._RE_PAGE_LAST_SHOW.search(html)
        if m:
            return int(m.group(1))
        if self._RE_PAGE_NEXT.search(html):
            return current_page + 1
        return 1

    # ==================== 首页 ====================

    def homeContent(self, filter):
        result = {}
        result['class'] = [dict(c) for c in self.CATEGORIES]
        if filter:
            result['filters'] = self._build_filters()

        html = self._fetch(self.HOST)
        if html:
            videos = self._parse_card_list(html)
            if videos:
                result['list'] = videos

        return result

    def homeVideoContent(self):
        html = self._fetch(self.HOST)
        videos = self._parse_card_list(html) if html else []
        return {'list': videos}

    # ==================== 分类内容 ====================

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        extend = extend or {}

        # 子分类优先: extend['class'] 为子分类的独立 type_id
        sub_type = extend.get('class', '')
        target_id = sub_type if sub_type else tid
        area = extend.get('area', '')
        year = extend.get('year', '')

        # 基础分页 URL
        if page > 1:
            base_url = f'{self.HOST}/mjteadtype/{target_id}-{page}.html'
        else:
            base_url = f'{self.HOST}/mjteadtype/{target_id}.html'

        # 若存在地区/年份筛选, 尝试 vodshow 筛选页
        # 格式推测(基于 48-----------.html 共11段10个-):
        # /mjteadshow/{id}-{area}-{lang}-{year}-{letter}-{actor}-{director}-{state}-{version}-{tag}-{page}.html
        html = ''
        if area or year:
            parts = [target_id, area, '', year, '', '', '', '', '', '',
                     str(page) if page > 1 else '']
            show_url = f'{self.HOST}/mjteadshow/{"-".join(parts)}.html'
            html = self._fetch(show_url)
            # 若 show 页无有效内容, 回退到基础 type 页
            if not html or not self._RE_CARD.search(html):
                html = ''

        if not html:
            html = self._fetch(base_url)

        if not html:
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 0, 'total': 0}

        videos = self._parse_card_list(html)
        page_count = self._parse_page_count(html, page)

        return {
            'list': videos,
            'page': page,
            'pagecount': page_count,
            'limit': len(videos),
            'total': page_count * len(videos) if videos else 0,
        }

    # ==================== 详情页 ====================

    def detailContent(self, ids):
        vid = ids[0]
        url = f'{self.HOST}/mjtead/{vid}.html'
        html = self._fetch(url)

        if not html:
            return {'list': []}

        vod = {'vod_id': vid}

        # 标题
        m = self._RE_H1.search(html)
        if m:
            vod['vod_name'] = self._RE_HTML_TAG.sub('', m.group(1)).strip()

        # 封面 (详情页可能用 data-original 或 data-background)
        m = self._RE_CARD_IMG.search(html)
        if not m:
            m = self._RE_LAZY_BG.search(html)
        if m:
            vod['vod_pic'] = m.group(1)

        # 简介 (template101: 剧情简介 区块)
        desc = ''
        m = self._RE_DETAIL_DESC_BLOCK.search(html)
        if m:
            desc = self._RE_HTML_TAG.sub('', m.group(1)).strip()
        if not desc:
            m = self._RE_DESC_BLOCK.search(html)
            if m:
                desc = self._RE_HTML_TAG.sub('', m.group(1)).strip()
        if not desc:
            m = self._RE_DESC_LINE.search(html)
            if m:
                desc = m.group(1).strip()
        if desc:
            desc = desc.replace('&nbsp;', ' ').replace('\n', '').replace('\t', '')
            vod['vod_content'] = desc

        # 元信息
        info_map = self._parse_detail_meta(html)
        vod.update(info_map)

        # 播放列表解析
        play_from_list, play_url_list = self._parse_playlists(html)

        # 兜底: 若未解析到播放列表, 尝试将整个详情页作为单集播放
        if not play_from_list:
            play_from_list.append('默认')
            play_url_list.append(f'正片$/mjtead/{vid}.html')

        vod['vod_play_from'] = '$$$'.join(play_from_list)
        vod['vod_play_url'] = '$$$'.join(play_url_list)

        return {'list': [vod]}

    def _parse_detail_meta(self, html):
        """解析详情页的导演/主演/地区/年份/类型/状态等元信息 (template101)"""
        info = {}

        # 类型/分类: t101-kicker (如 "海外动漫")
        m = self._RE_DETAIL_KICKER.search(html)
        if m:
            val = self._RE_HTML_TAG.sub('', m.group(1)).strip()
            if val:
                info['type_name'] = val

        # 顶部 meta: t101-meta 内的 span (地区/语言/状态 等)
        m = self._RE_DETAIL_META.search(html)
        if m:
            spans = self._RE_DETAIL_META_SPAN.findall(m.group(1))
            for s in spans:
                val = s.strip()
                if not val:
                    continue
                # 4 位数字 → 年份
                if val.isdigit() and len(val) == 4:
                    info['vod_year'] = val
                # 常见地区关键词
                elif val in ('中国大陆', '香港', '台湾', '日本', '韩国', '美国',
                             '英国', '泰国', '法国', '德国', '意大利', '西班牙',
                             '印度', '加拿大', '澳大利亚', '其他', '中国'):
                    info['vod_area'] = val
                # 常见状态关键词
                elif val in ('全集', '完结', 'HD', 'HD高清', '蓝光', '更新中',
                             '正片', '预告片') or val.startswith('更新至') \
                        or val.startswith('连载至') or val.endswith('集全'):
                    info['vod_remarks'] = val
                # 其他作为语言或备注兜底
                elif 'vod_remarks' not in info and len(val) <= 6:
                    info['vod_remarks'] = val

        # 详情行: t101-detail-lines (导演/主演/地区/年份/状态/类型)
        m = self._RE_DETAIL_LINES.search(html)
        if m:
            block = m.group(1)
            for label, value in self._RE_DETAIL_LINE_ITEM.findall(block):
                val = self._RE_HTML_TAG.sub('', value).strip()
                if not val or val == '未知':
                    continue
                if label in ('导演',):
                    info['vod_director'] = val
                elif label in ('主演',):
                    info['vod_actor'] = val
                elif label in ('地区',):
                    info['vod_area'] = val
                elif label in ('年份', '年代'):
                    if val.isdigit():
                        info['vod_year'] = val
                elif label in ('状态',):
                    info['vod_remarks'] = val
                elif label in ('类型', '分类'):
                    info['type_name'] = val

        # 回退: 旧式 "导演：xxx" 行
        for key, pat in (
            ('vod_director', self._RE_INFO_DIRECTOR),
            ('vod_actor', self._RE_INFO_ACTOR),
            ('vod_area', self._RE_INFO_AREA),
            ('vod_year', self._RE_INFO_YEAR),
            ('vod_remarks', self._RE_INFO_REMARKS),
            ('type_name', self._RE_INFO_TYPE),
        ):
            if key in info:
                continue
            m = pat.search(html)
            if m:
                val = self._RE_HTML_TAG.sub('', m.group(1)).strip()
                if val:
                    info[key] = val

        return info

    def _parse_playlists(self, html):
        """解析详情页的所有播放源和剧集, 返回 (from_list, url_list)"""
        play_from_list = []
        play_url_list = []

        # 模式1: ewave/template101 选项卡 + ul 列表
        # 先建 playlist_id -> source_name 映射
        tab_map = {}
        for tab_id, tab_name in self._RE_PLAY_TAB.findall(html):
            name = self._RE_HTML_TAG.sub('', tab_name).strip()
            if name:
                tab_map[tab_id] = name

        for ul_id, ul_html in self._RE_PLAY_UL.findall(html):
            episodes = self._RE_PLAY_EPISODE.findall(ul_html)
            if not episodes:
                continue

            cleaned = []
            for ep_url, ep_name in episodes:
                clean_name = self._RE_HTML_TAG.sub('', ep_name).strip()
                if clean_name and clean_name not in ('立即播放',):
                    cleaned.append((ep_url, clean_name))

            if not cleaned:
                continue

            cleaned.sort(key=lambda x: self._extract_episode_number(x[1]))
            ep_list = [f'{name}${url}' for url, name in cleaned]

            source_name = tab_map.get(ul_id, f'线路{len(play_from_list) + 1}')
            play_from_list.append(source_name)
            play_url_list.append('#'.join(ep_list))

        if play_from_list:
            return play_from_list, play_url_list

        # 模式2: 宽松全局匹配 (旧模板兜底)
        eps = self._RE_PLAY_EPISODE.findall(html)
        if eps:
            cleaned = []
            for ep_url, ep_name in eps:
                clean_name = self._RE_HTML_TAG.sub('', ep_name).strip()
                if clean_name and clean_name not in ('立即播放',):
                    cleaned.append((ep_url, clean_name))
            if cleaned:
                cleaned.sort(key=lambda x: self._extract_episode_number(x[1]))
                ep_list = [f'{name}${url}' for url, name in cleaned]
                play_from_list.append('默认')
                play_url_list.append('#'.join(ep_list))

        return play_from_list, play_url_list

    # ==================== 搜索 ====================

    def searchContent(self, key, quick, pg=1):
        # MacCMS 搜索: /search/-------------.html?wd=关键词
        # 分页: /search/-------------.html?wd=关键词&page=2
        url = f'{self.HOST}/search/-------------.html?wd={key}'
        if int(pg) > 1:
            url += f'&page={pg}'

        html = self._fetch(url)
        if not html:
            return {'list': []}

        videos = self._parse_card_list(html)
        return {'list': [v for v in videos if v.get('vod_name')]}

    # ==================== 播放 ====================

    def playerContent(self, flag, id, vipFlags):
        if id.startswith('http'):
            play_page_url = id
        else:
            play_page_url = self.HOST + id if id.startswith('/') else f'{self.HOST}/{id}'

        html = self._fetch(play_page_url)
        play_url = ''
        parse_mode = 0

        if html:
            # 模式1: player_aaaa JSON (MacCMS v10, template101 末尾紧跟换行+</script>)
            m = self._RE_PLAYER_AAAA.search(html)
            if not m:
                m = self._RE_PLAYER_AAAA_LOOSE.search(html)
            if m:
                try:
                    raw = m.group(1)
                    # MacCMS 会把 / 转义为 \/, json.loads 可直接处理
                    data = json.loads(raw)
                    if data and isinstance(data, dict):
                        play_url = data.get('url', '')
                        # from 字段可用于判断解析方式
                        flag_name = (data.get('from') or '').lower()
                        if flag_name in ('m3u8', 'snm3u8', 'mp4', 'video',
                                         'http', 'https', 'dplayer'):
                            parse_mode = 0
                        elif flag_name:
                            parse_mode = 1
                except (json.JSONDecodeError, ValueError):
                    pass

            # 模式2: iframe src
            if not play_url:
                m = self._RE_IFRAME_SRC.search(html)
                if m:
                    play_url = m.group(1)

            # 模式3: JS 变量 url/src/play_url
            if not play_url:
                m = self._RE_VAR_URL.search(html)
                if m:
                    play_url = m.group(1)

            # 模式4: 从任意 JSON 中找 url 字段
            if not play_url:
                m = self._RE_JS_URL.search(html)
                if m:
                    play_url = m.group(1)

            # 处理相对路径
            if play_url and not play_url.startswith('http'):
                play_url = self.HOST + play_url if play_url.startswith('/') else f'{self.HOST}/{play_url}'

            # 尝试 Base64 解码 (部分站加密)
            if play_url and not play_url.startswith('http') and len(play_url) > 20:
                try:
                    decoded = base64.b64decode(play_url).decode('utf-8')
                    if decoded.startswith('http'):
                        play_url = decoded
                except Exception:
                    pass

        header = {
            'User-Agent': self.HEADERS['User-Agent'],
            'Referer': play_page_url,
        }

        return {
            'parse': parse_mode,
            'playUrl': '',
            'url': play_url,
            'header': json.dumps(header),
        }

    def localProxy(self, params):
        return None

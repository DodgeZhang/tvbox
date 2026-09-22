# -*- coding: utf-8 -*-
"""
=================================================
  刁民制作，仅供测试，测试完毕请于24小时删除。
=================================================

4K影视 TVBox / OK影视 / 影视仓 标准 Python 源。

站点: https://www.4kvms.org (Laravel + Tailwind + ArtPlayer)

特点:
1. 支持 首页/分类/搜索/详情/播放 全流程。
2. 图片直连加载（不走代理，确保分类栏出图）—— 学习星辰影视优点。
3. 多层级卡片解析，data-src 懒加载图片正确提取。
4. 底部筛选器: 支持地区、类型、年份、排序筛选。
5. 播放采用 wasmtime + WASM 直接提取 m3u8 直链（parse:0），无 Node.js 依赖。
   如果 wasmtime 不可用，回退到 parse:1 网页解析。
6. 实时抓取动态域名，防止网站更换域名。
7. 兼容 FongMi/TV (T3) & WebHomeTV / PeekPro (T4)。
"""

import sys
import json
import re
import base64
import time
import os
import tempfile
from urllib.parse import quote, urlencode, urlparse

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq

    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):
    """
    4K影视 Spider
    Laravel + Tailwind + ArtPlayer, HTML 解析
    """

    # 默认域名（会被动态域名覆盖）
    host = 'https://www.4kvms.org'

    # 域名发布页（实时获取最新可用域名）
    _domain_portal = 'https://4kvm.site'

    # 已知备用域名列表（用于动态域名探测兜底）
    _known_domains = [
        'https://www.4kvms.org',
        'https://www.4kvms.com',
        'https://www.4kvm.org',
        'https://www.4kvm.cc',
        'https://www.4kvm.com',
        'https://www.4kvm.me',
        'https://www.4kvm.net',
        'https://www.4kvm.pro',
        'https://www.4kvm.top',
        'https://www.4kvm.tv',
    ]

    # 上次域名探测时间（每小时探测一次）
    _last_domain_check = 0
    _domain_cache_hours = 1

    header = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }

    # 分类列表 (classify ID 对应 /filter?classify=X)
    classes = [
        {'type_name': '动漫', 'type_id': '3'},
        {'type_name': '电视剧', 'type_id': '2'},
        {'type_name': '电影', 'type_id': '1'}
    ]

    # 筛选器: 地区 (areas 参数对应 /filter?areas=X)
    _filter_area = [
        {'n': '全部', 'v': ''},
        {'n': '中国大陆', 'v': '52'},
        {'n': '中国香港', 'v': '14'},
        {'n': '中国台湾', 'v': '21'},
        {'n': '美国', 'v': '5'},
        {'n': '日本', 'v': '11'},
        {'n': '韩国', 'v': '12'},
        {'n': '英国', 'v': '30'},
        {'n': '法国', 'v': '6'},
        {'n': '加拿大', 'v': '32'},
        {'n': '泰国', 'v': '33'},
        {'n': '印度', 'v': '34'},
    ]

    # 筛选器: 类型 (types 参数)
    _filter_type = [
        {'n': '全部', 'v': ''},
        {'n': '剧情', 'v': '1'},
        {'n': '动作', 'v': '10'},
        {'n': '喜剧', 'v': '5'},
        {'n': '爱情', 'v': '6'},
        {'n': '科幻', 'v': '14'},
        {'n': '悬疑', 'v': '2'},
        {'n': '惊悚', 'v': '4'},
        {'n': '恐怖', 'v': '3'},
        {'n': '犯罪', 'v': '9'},
        {'n': '奇幻', 'v': '12'},
        {'n': '战争', 'v': '16'},
        {'n': '动画', 'v': '11'},
        {'n': '冒险', 'v': '18'},
        {'n': '家庭', 'v': '19'},
        {'n': '纪录', 'v': '20'},
        {'n': '古装', 'v': '27'},
        {'n': '灾难', 'v': '34'},
    ]

    # 筛选器: 年份 (years 参数)
    _filter_year = [
        {'n': '全部', 'v': ''},
        {'n': '2026', 'v': '1'},
        {'n': '2025', 'v': '3'},
        {'n': '2024', 'v': '4'},
        {'n': '2023', 'v': '56'},
        {'n': '2022', 'v': '13'},
        {'n': '2021', 'v': '2'},
        {'n': '2020', 'v': '6'},
        {'n': '2019', 'v': '8'},
        {'n': '2018', 'v': '9'},
        {'n': '2015-2010', 'v': '17'},
        {'n': '2009-2000', 'v': '23'},
        {'n': '更早', 'v': '24'},
    ]

    # 筛选器: 排序 (sort_by 参数)
    _filter_sort = [
        {'n': '最新上映', 'v': 'update_time'},
        {'n': '最受欢迎', 'v': 'hits'},
        {'n': '评分最高', 'v': 'score'},
    ]

    # ===================================================================
    #  动态域名探测
    # ===================================================================

    def _detect_domain(self):
        """实时探测最新可用域名"""
        now = time.time()
        # 每小时探测一次
        if now - self._last_domain_check < self._domain_cache_hours * 3600:
            return self.host

        self._last_domain_check = now

        # 方法1: 从域名发布页 https://4kvm.site 提取所有域名
        discovered = self._fetch_domains_from_portal()
        for domain in discovered:
            if self._test_domain(domain):
                self.host = domain
                return self.host

        # 方法2: 从已知域名列表中探测可用的
        for domain in self._known_domains:
            if self._test_domain(domain):
                self.host = domain
                return self.host

        # 方法3: 尝试当前 host 是否还能用
        if self._test_domain(self.host):
            return self.host

        return self.host

    def _fetch_domains_from_portal(self):
        """从域名发布页提取所有可用域名"""
        domains = []
        try:
            r = self.fetch(self._domain_portal, headers=self.header, timeout=10)
            text = r.text if hasattr(r, 'text') else r.content.decode('utf-8', errors='ignore')
            # 提取所有 4kvm 开头的域名
            found = re.findall(r'https?://(www\.4kv[a-z]+\.[a-z]+)', text, re.I)
            for d in found:
                full = 'https://' + d.lower()
                if full not in domains:
                    domains.append(full)
        except Exception:
            pass
        return domains

    def _test_domain(self, domain):
        """测试域名是否可访问且是4K影视站点"""
        try:
            r = self.fetch(domain, headers=self.header, timeout=10)
            text = r.text if hasattr(r, 'text') else r.content.decode('utf-8', errors='ignore')
            return r.status_code == 200 and ('4k' in text.lower() or '影视' in text or 'movie-card' in text)
        except Exception:
            return False

    # ===================================================================
    #  基础方法
    # ===================================================================

    def getName(self):
        return '4K影视'

    def init(self, extend=''):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        # 初始化时探测域名
        self._detect_domain()

    def isVideoFormat(self, url):
        return any(x in url for x in ['.m3u8', '.mp4', '.flv', '.avi', '.mkv'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ===================================================================
    #  请求封装
    # ===================================================================

    def _fetch_html(self, path):
        """获取页面 HTML，自动探测域名"""
        self._detect_domain()
        url = path if path.startswith('http') else self.host + path
        try:
            r = self.fetch(url, headers=self.header, timeout=15)
            text = r.text if hasattr(r, 'text') else r.content.decode('utf-8', errors='ignore')
            if r.status_code == 200:
                return text
            # 域名可能失效，刷新后重试
            self._last_domain_check = 0
            self._detect_domain()
            url = path if path.startswith('http') else self.host + path
            r = self.fetch(url, headers=self.header, timeout=15)
            return r.text if hasattr(r, 'text') else r.content.decode('utf-8', errors='ignore')
        except Exception:
            # 域名可能失效，刷新后重试
            self._last_domain_check = 0
            self._detect_domain()
            url = path if path.startswith('http') else self.host + path
            r = self.fetch(url, headers=self.header, timeout=15)
            return r.text if hasattr(r, 'text') else r.content.decode('utf-8', errors='ignore')

    # ===================================================================
    #  图片处理（学习星辰影视优点：直连不走代理）
    # ===================================================================

    def _wrap_pic(self, pic_url):
        """将图片 URL 处理为可直接加载的 URL（不走代理，加快加载速度）"""
        if not pic_url:
            return ''

        # 清理 URL
        pic_url = pic_url.strip()
        # 去掉引号
        if pic_url.startswith(('"', "'")) and pic_url.endswith(('"', "'")):
            pic_url = pic_url[1:-1]

        # HTML 实体解码
        pic_url = pic_url.replace('&amp;', '&')

        # 如果已经是代理 URL 或 localhost，直接返回
        if '127.0.0.1' in pic_url or 'proxy' in pic_url:
            return pic_url

        # 补全协议头
        if pic_url.startswith('//'):
            pic_url = 'https:' + pic_url
        elif not pic_url.startswith(('http://', 'https://')):
            # 相对路径，补全主域名
            if pic_url.startswith('/'):
                pic_url = self.host + pic_url
            else:
                pic_url = self.host + '/' + pic_url

        # 直接返回图片URL（不经过代理，加快加载速度，确保图片正常显示）
        return pic_url

    # ===================================================================
    #  首页
    # ===================================================================

    def homeContent(self, filter):
        """返回分类列表和筛选器配置"""
        filters = {}
        for c in self.classes:
            tid = c['type_id']
            filters[tid] = [
                {'key': 'areas', 'name': '地区', 'value': self._filter_area},
                {'key': 'types', 'name': '类型', 'value': self._filter_type},
                {'key': 'years', 'name': '年份', 'value': self._filter_year},
                {'key': 'sort_by', 'name': '排序', 'value': self._filter_sort},
            ]
        return {'class': self.classes, 'filters': filters}

    def homeVideoContent(self):
        try:
            html = self._fetch_html('/')
            vod_list = self._parse_cards(html)
            return {'list': vod_list[:30]}
        except Exception:
            return {'list': []}

    # ===================================================================
    #  分类内容
    # ===================================================================

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)

            # 解析筛选器参数
            ext = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend)
                    except Exception:
                        ext = {}

            areas = ext.get('areas', '')
            types = ext.get('types', '')
            years = ext.get('years', '')
            sort_by = ext.get('sort_by', 'update_time')

            # 构建 /filter URL
            params = {}
            if tid:
                params['classify'] = tid
            if areas:
                params['areas'] = areas
            if types:
                params['types'] = types
            if years:
                params['years'] = years
            if sort_by:
                params['sort_by'] = sort_by
                params['order'] = 'desc'
            if pg > 1:
                params['page'] = pg

            url = '/filter?' + urlencode(params)
            html = self._fetch_html(url)
            vod_list = self._parse_cards(html)
            pagecount = self._parse_pagecount(html)

            return {
                'page': pg,
                'pagecount': pagecount,
                'limit': len(vod_list),
                'total': pagecount * 24 if pagecount < 999 else 99999,
                'list': vod_list,
            }
        except Exception:
            return {'page': pg, 'pagecount': 1, 'limit': 24, 'total': 0, 'list': []}

    def _parse_pagecount(self, html):
        """从分页 HTML 中解析总页数"""
        try:
            # 匹配 "第 X 页 / 共 Y 页" 格式
            m = re.search(r'共\s*(\d+)\s*页', html)
            if m:
                return int(m.group(1))
            # 找分页链接中的页码数字
            nums = re.findall(r'[?&]page=(\d+)', html)
            if nums:
                return max(int(n) for n in nums)
            # 如果有 "下一页" 链接
            if '下一页' in html or 'next' in html.lower():
                return 999
        except Exception:
            pass
        return 1

    # ===================================================================
    #  详情页
    # ===================================================================

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            html = self._fetch_html('/play/%s' % vod_id)

            # 标题 - 从 <title> 提取
            vod_name = ''
            title_match = re.search(r'<title>(.*?)</title>', html, re.S)
            if title_match:
                vod_name = title_match.group(1).strip()
                vod_name = re.sub(r'\s*-\s*第\d+集.*$', '', vod_name)
                vod_name = re.sub(r'\s*-?\s*4k影视.*$', '', vod_name, flags=re.I)
                vod_name = re.sub(r'\s*-\s*4k.*$', '', vod_name, flags=re.I)

            # 从 og:title 提取更干净的标题
            og_title = re.search(r'property="og:title"\s+content="([^"]*)"', html)
            if og_title:
                og_name = og_title.group(1).strip()
                og_name = re.sub(r'\s*-\s*第\d+集.*$', '', og_name)
                if og_name:
                    vod_name = og_name

            # 描述
            vod_content = ''
            desc_m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
            if desc_m:
                vod_content = desc_m.group(1)

            # 封面图
            vod_pic = ''
            og = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', html)
            if og:
                vod_pic = og.group(1)
            if not vod_pic:
                poster_m = re.search(r'data-poster="([^"]*)"', html)
                if poster_m:
                    vod_pic = poster_m.group(1)
            vod_pic = self._wrap_pic(vod_pic)

            # 从 keywords 提取年份和类型
            # 格式: ,消失的人,2026,悬疑,惊悚,犯罪,中国大陆,汉语普通话,程伟豪
            vod_year = ''
            vod_class = ''
            vod_area = ''
            vod_director = ''
            kw_m = re.search(r'<meta\s+name="keywords"\s+content="([^"]*)"', html)
            if kw_m:
                keywords = kw_m.group(1)
                parts = [p.strip() for p in keywords.split(',')]
                if len(parts) > 1:
                    vod_year = parts[1] if re.match(r'\d{4}', parts[1]) else ''
                if len(parts) > 2:
                    type_parts = []
                    for p in parts[2:]:
                        if p in ('中国大陆', '中国香港', '中国台湾', '美国', '日本', '韩国', '英国',
                                 '法国', '加拿大', '泰国', '印度', '汉语普通话', '英语', '日语', '韩语'):
                            break
                        type_parts.append(p)
                    vod_class = ' '.join(type_parts[:4])

            # 从详情信息网格提取更准确的信息
            # 格式: <div class="col-span-1 text-gray-500">导演</div>\n<div class="col-span-2 text-gray-300">程伟豪</div>
            info_pairs = re.findall(
                r'<div class="col-span-1 text-gray-500">(.*?)</div>\s*<div class="col-span-2 text-gray-300">(.*?)</div>',
                html, re.S
            )
            for label, value in info_pairs:
                label = label.strip()
                value = re.sub(r'<[^>]+>', '', value).strip()
                if label == '导演':
                    vod_director = value
                elif label == '主演':
                    pass  # 可扩展
                elif label == '类型':
                    vod_class = value
                elif label == '地区':
                    vod_area = value
                elif label == '上映':
                    year_m = re.search(r'(20\d{2})', value)
                    if year_m:
                        vod_year = year_m.group(1)

            # 演员
            vod_actor = ''
            for label, value in info_pairs:
                if label.strip() == '主演':
                    vod_actor = re.sub(r'<[^>]+>', '', value).strip()
                    break

            # 提取选集
            # 结构: <a href="/play/xxx" @click.prevent="..." data-line="1" data-episode="1" dataid="36869" ...>
            #   <span ...>正片</span> 或 <span ...>1</span>
            # </a>
            # 注意: x-effect 属性值中包含 > 字符，不能用 [^>]*? 匹配属性间内容
            play_from_list = []
            play_url_list = []

            # 按线路分组
            line_eps = {}

            # 方法1: 使用 tempered greedy token 匹配 href 到 data 属性
            # (?:(?!</a>).)*? 确保不会跨越 </a> 边界
            ep_pattern = re.compile(
                r'href="(/play/[^"]+)"((?:(?!</a>).)*?)'
                r'data-line="(\d+)"\s+data-episode="(\d+)"\s+dataid="(\d+)"',
                re.S
            )
            ep_matches = ep_pattern.findall(html)

            for href, _gap, line, ep, dataid in ep_matches:
                if line not in line_eps:
                    line_eps[line] = []

                # 从 dataid 之后到 </a> 之间提取选集名称
                dataid_pos = html.find('dataid="%s"' % dataid)
                if dataid_pos >= 0:
                    end_pos = html.find('</a>', dataid_pos)
                    if end_pos < 0:
                        end_pos = dataid_pos + 500
                    ep_inner = html[dataid_pos:end_pos]
                    # 提取 span 内容
                    span_m = re.search(r'<span[^>]*>(.*?)</span>', ep_inner, re.S)
                    if span_m:
                        clean_name = re.sub(r'<[^>]+>', '', span_m.group(1)).strip()
                    else:
                        clean_name = ''
                else:
                    clean_name = ''

                if not clean_name:
                    clean_name = '第%s集' % ep
                # 格式: 选集名$dataid|/play/vod_slug
                # dataid 通过 | 传递，避免 playerContent 重复抓取页面获取 dataid
                line_eps[line].append('%s$%s|%s' % (clean_name, dataid, href))

            # 构建播放列表
            for line in sorted(line_eps.keys()):
                eps = line_eps[line]
                if eps:
                    play_from_list.append('线路%s' % line)
                    play_url_list.append('#'.join(eps))

            # 如果没有找到选集，至少返回当前播放链接
            if not play_from_list:
                play_from_list.append('4K影视')
                play_url_list.append('播放$/play/%s' % vod_id)

            vod = {
                'vod_id': vod_id,
                'vod_name': vod_name,
                'vod_pic': vod_pic,
                'type_name': vod_class or '4K影视',
                'vod_year': vod_year,
                'vod_area': vod_area,
                'vod_actor': vod_actor,
                'vod_director': vod_director,
                'vod_content': vod_content,
                'vod_remarks': '',
                'vod_play_from': '$$$'.join(play_from_list),
                'vod_play_url': '$$$'.join(play_url_list),
            }
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    # ===================================================================
    #  搜索
    # ===================================================================

    def searchContent(self, key, quick, pg=1):
        try:
            pg = int(pg or 1)
            encoded_key = quote(key)
            search_path = '/search?q=%s' % encoded_key
            if pg > 1:
                search_path += '&page=%d' % pg
            html = self._fetch_html(search_path)
            vod_list = self._parse_cards(html)

            return {
                'list': vod_list[:30],
                'page': pg,
            }
        except Exception:
            return {'list': [], 'page': 1}

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    # ===================================================================
    #  播放
    # ===================================================================

    # WASM 二进制缓存路径
    _wasm_binary_path = ''
    _wasm_cache_dir = ''

    def _get_wasm_binary(self, html=''):
        """下载并缓存 WASM 二进制文件。返回文件路径或 None。"""
        try:
            cache_dir = os.path.join(tempfile.gettempdir(), '4kvms_wasm')
            wasm_path = os.path.join(cache_dir, 'nbmovie_wasm_bg.wasm')

            # 检查缓存（文件存在且不超过7天）
            if os.path.exists(wasm_path) and (time.time() - os.path.getmtime(wasm_path) < 7 * 86400):
                self._wasm_binary_path = wasm_path
                self._wasm_cache_dir = cache_dir
                return wasm_path

            # 创建缓存目录
            try:
                os.makedirs(cache_dir, exist_ok=True)
            except Exception:
                pass

            # 从 HTML 中提取 WASM 二进制路径
            wasm_bg_url = ''
            if html:
                m = re.search(r'id="wasm-cfg"[^>]*\s+data-bg="([^"]+)"', html)
                if not m:
                    m = re.search(r'id="wasm-cfg"[^>]*data-bg="([^"]+)"', html)
                if m:
                    wasm_bg_url = m.group(1)

            if not wasm_bg_url:
                # 尝试从首页获取
                page_html = self._fetch_html('/')
                m = re.search(r'id="wasm-cfg"[^>]*data-bg="([^"]+)"', page_html)
                if m:
                    wasm_bg_url = m.group(1)

            if not wasm_bg_url:
                return None

            # 补全 URL
            if not wasm_bg_url.startswith('http'):
                wasm_bg_url = self.host + wasm_bg_url

            # 下载 WASM 二进制
            r = self.fetch(wasm_bg_url, headers=self.header, timeout=30)
            content = r.content if hasattr(r, 'content') else r.text.encode('utf-8')

            if not content or len(content) < 100:
                return None

            with open(wasm_path, 'wb') as f:
                f.write(content)

            self._wasm_binary_path = wasm_path
            self._wasm_cache_dir = cache_dir
            return wasm_path
        except Exception:
            return None

    def _wasm_build_play_url(self, dataid, vod_slug, quality, userlink, nb_st):
        """使用 wasmtime 执行 WASM build_play_url 函数，返回 API URL 字符串或 None。"""
        try:
            import wasmtime
        except ImportError:
            return None

        import struct

        wasm_path = self._wasm_binary_path
        if not wasm_path or not os.path.exists(wasm_path):
            wasm_path = self._get_wasm_binary()
        if not wasm_path or not os.path.exists(wasm_path):
            return None

        try:
            engine = wasmtime.Engine()
            store = wasmtime.Store(engine)

            with open(wasm_path, 'rb') as f:
                wasm_bytes = f.read()

            module = wasmtime.Module(engine, wasm_bytes)

            # JS 对象堆管理（模拟 wasm-bindgen 的对象引用表）
            heap = [None] * 1024
            heap.extend([None, None, True, False])
            heap_next = [len(heap)]
            undefined_sentinel = object()

            def add_heap(obj):
                if heap_next[0] == len(heap):
                    heap.append(len(heap) + 1)
                idx = heap_next[0]
                if isinstance(heap[idx], int):
                    heap_next[0] = heap[idx]
                else:
                    heap_next[0] = len(heap)
                heap[idx] = obj
                return idx

            def get_obj(idx):
                return heap[idx]

            def drop_obj(idx):
                if idx < 1028:
                    return
                heap[idx] = heap_next[0]
                heap_next[0] = idx

            def take_obj(idx):
                r = get_obj(idx)
                drop_obj(idx)
                return r

            # Mock DOM（模拟浏览器环境）
            class MockMeta:
                def __init__(self, content):
                    self.content = content

            class MockDocument:
                def getElementById(self, id_str):
                    if id_str == 'nb-st':
                        return MockMeta(nb_st)
                    if id_str == 'nb-plt':
                        return MockMeta(str(int(time.time() * 1000)))
                    return None

            mock_doc = MockDocument()
            mock_window = {'document': mock_doc}
            window_idx = add_heap(mock_window)

            # 共享状态（实例化后填充）
            state = {'memory': None, 'malloc': None}

            def read_string(ptr, length):
                return state['memory'].read(store, ptr, ptr + length).decode('utf-8')

            def write_string(s):
                encoded = s.encode('utf-8')
                ptr = state['malloc'](store, len(encoded), 1)
                state['memory'].write(store, encoded, ptr)
                return ptr, len(encoded)

            # 定义所有 WASM 导入函数
            i32 = wasmtime.ValType.i32()
            f64 = wasmtime.ValType.f64()

            def fn_is_undefined(a):
                return 1 if get_obj(a) is undefined_sentinel else 0

            def fn_throw(a, b):
                raise Exception(read_string(a, b))

            def fn_get_content(a, b):
                obj = get_obj(b)
                content = getattr(obj, 'content', '') if obj else ''
                encoded = content.encode('utf-8')
                ptr = state['malloc'](store, len(encoded), 1)
                state['memory'].write(store, encoded, ptr)
                state['memory'].write(store, struct.pack('<II', ptr, len(encoded)), a)

            def fn_get_document(a):
                obj = get_obj(a)
                if isinstance(obj, dict) and 'document' in obj:
                    return add_heap(obj['document'])
                if hasattr(obj, 'document'):
                    return add_heap(obj.document)
                return 0

            def fn_get_element_by_id(a, b, c):
                id_str = read_string(b, c)
                doc = get_obj(a)
                if doc is None:
                    return 0
                elem = doc.getElementById(id_str)
                return add_heap(elem) if elem else 0

            def fn_is_meta(a):
                return 1 if isinstance(get_obj(a), MockMeta) else 0

            def fn_is_window(a):
                return 1 if isinstance(get_obj(a), dict) else 0

            def fn_date_now():
                return float(int(time.time() * 1000))

            def fn_get_global():
                return add_heap(globals())

            def fn_get_globalthis():
                return add_heap(globals())

            def fn_get_self():
                return 0

            def fn_get_window():
                return window_idx

            def fn_clone(a):
                return add_heap(get_obj(a))

            def fn_drop(a):
                take_obj(a)

            mod_name = "./nbmovie_wasm_bg.js"
            func_defs = [
                ('__wbg___wbindgen_is_undefined_52709e72fb9f179c', fn_is_undefined, [i32], [i32]),
                ('__wbg___wbindgen_throw_6ddd609b62940d55', fn_throw, [i32, i32], []),
                ('__wbg_content_4373268a6f34e443', fn_get_content, [i32, i32], []),
                ('__wbg_document_c0320cd4183c6d9b', fn_get_document, [i32], [i32]),
                ('__wbg_getElementById_d1f25d287b19a833', fn_get_element_by_id, [i32, i32, i32], [i32]),
                ('__wbg_instanceof_HtmlMetaElement_07f78901e9785572', fn_is_meta, [i32], [i32]),
                ('__wbg_instanceof_Window_23e677d2c6843922', fn_is_window, [i32], [i32]),
                ('__wbg_now_16f0c993d5dd6c27', fn_date_now, [], [f64]),
                ('__wbg_static_accessor_GLOBAL_8adb955bd33fac2f', fn_get_global, [], [i32]),
                ('__wbg_static_accessor_GLOBAL_THIS_ad356e0db91c7913', fn_get_globalthis, [], [i32]),
                ('__wbg_static_accessor_SELF_f207c857566db248', fn_get_self, [], [i32]),
                ('__wbg_static_accessor_WINDOW_bb9f1ba69d61b386', fn_get_window, [], [i32]),
                ('__wbindgen_object_clone_ref', fn_clone, [i32], [i32]),
                ('__wbindgen_object_drop_ref', fn_drop, [i32], []),
            ]

            linker = wasmtime.Linker(engine)
            for name, fn, params, results in func_defs:
                linker.define(store, mod_name, name, wasmtime.Func(store, wasmtime.FuncType(params, results), fn))

            instance = linker.instantiate(store, module)
            exports = instance.exports(store)

            state['memory'] = exports["memory"]
            state['malloc'] = exports["__wbindgen_export"]

            build_play_url = exports["build_play_url"]
            stack_pointer = exports["__wbindgen_add_to_stack_pointer"]
            free_func = exports["__wbindgen_export3"]

            # 调用 build_play_url 生成签名 API URL
            retptr = stack_pointer(store, -16)
            p0, l0 = write_string(dataid)
            p1, l1 = write_string(vod_slug)
            p2, l2 = write_string(quality)
            p3, l3 = write_string(userlink)

            build_play_url(store, retptr, p0, l0, p1, l1, p2, l2, p3, l3)

            r0, r1 = struct.unpack('<ii', state['memory'].read(store, retptr, retptr + 8))
            api_url = read_string(r0, r1)

            stack_pointer(store, 16)
            free_func(store, r0, r1, 1)

            return api_url
        except Exception:
            return None

    def _extract_m3u8_wasm(self, vod_slug, dataid, nb_st, userlink, html=''):
        """
        使用 wasmtime + WASM 提取 m3u8 直链。
        如果 wasmtime 不可用或提取失败，返回 None。
        """
        try:
            # 确保 WASM 二进制可用
            if not self._wasm_binary_path or not os.path.exists(self._wasm_binary_path):
                wasm_path = self._get_wasm_binary(html)
                if not wasm_path:
                    return None

            # 尝试多个画质
            for quality in ['1080', '720', '540', '360', '']:
                api_url = self._wasm_build_play_url(dataid, vod_slug, quality, userlink, nb_st)
                if not api_url:
                    continue

                full_url = self.host + api_url

                # 请求 API 获取 m3u8
                api_headers = {
                    'User-Agent': self.header['User-Agent'],
                    'Referer': self.host + '/play/' + vod_slug,
                    'Accept': 'application/json, text/plain, */*',
                    'X-Requested-With': 'XMLHttpRequest',
                }

                r = self.fetch(full_url, headers=api_headers, timeout=15)
                text = r.text if hasattr(r, 'text') else r.content.decode('utf-8', errors='ignore')

                try:
                    data = json.loads(text)
                    if data.get('code') == 200 and data.get('data', {}).get('quality_urls'):
                        urls = [q for q in data['data']['quality_urls'] if q.get('url') and q['url'] != '1']
                        if urls:
                            return urls[0]['url']
                except Exception:
                    continue

            return None
        except Exception:
            return None

    def playerContent(self, flag, id, vipFlags):
        """
        播放解析。
        优先通过 wasmtime + WASM 提取 m3u8 直链（parse:0 直播）。
        如果 wasmtime 不可用，回退到 parse:1 网页解析。
        """
        try:
            play_id = str(id or '')

            # 解析 vod_slug
            vod_slug = ''
            if '/play/' in play_id:
                slug_m = re.search(r'/play/([a-zA-Z0-9]+)', play_id)
                if slug_m:
                    vod_slug = slug_m.group(1)
            elif play_id.startswith('http'):
                slug_m = re.search(r'/play/([a-zA-Z0-9]+)', play_id)
                if slug_m:
                    vod_slug = slug_m.group(1)
            else:
                vod_slug = play_id

            # 处理 dataid|/play/vod_slug 格式（detailContent 传入）
            dataid = ''
            if '|' in play_id:
                parts = play_id.split('|', 1)
                dataid = parts[0]
                remaining = parts[1] if len(parts) > 1 else ''
                # 从 remaining 中提取 vod_slug
                slug_m = re.search(r'/play/([a-zA-Z0-9]+)', remaining)
                if slug_m:
                    vod_slug = slug_m.group(1)
                elif remaining:
                    vod_slug = remaining

            if not vod_slug:
                return {}

            # 获取播放页 HTML，提取所有必要参数
            html = self._fetch_html('/play/%s' % vod_slug)

            # 提取 dataid
            if not dataid:
                did_m = re.search(r'dataid="(\d+)"', html)
                if did_m:
                    dataid = did_m.group(1)

            # 提取 nb-st（服务器时间戳）
            nb_st = ''
            nb_st_m = re.search(r'id="nb-st"\s+content="([^"]+)"', html)
            if nb_st_m:
                nb_st = nb_st_m.group(1)

            # 提取 userlink（访问令牌）
            userlink = '0'
            userlink_m = re.search(r"userlink:'([^']+)'", html)
            if userlink_m:
                userlink = userlink_m.group(1)

            # 尝试通过 WASM 提取 m3u8 直链
            if dataid and nb_st:
                m3u8 = self._extract_m3u8_wasm(vod_slug, dataid, nb_st, userlink, html)
                if m3u8:
                    return {
                        'parse': 0,
                        'url': m3u8,
                        'header': {
                            'User-Agent': self.header['User-Agent'],
                            'Referer': self.host + '/',
                        },
                    }

            # 回退: parse:1 网页解析
            if play_id.startswith('/play/'):
                url = self.host + play_id
            elif play_id.startswith('http'):
                url = play_id
            else:
                url = self.host + '/play/' + vod_slug

            return {
                'parse': 1,
                'url': url,
                'header': {
                    'User-Agent': self.header['User-Agent'],
                    'Referer': self.host + '/',
                },
            }
        except Exception:
            return {}

    # ===================================================================
    #  本地代理 (图片代理) - 保留备用
    # ===================================================================

    def localProxy(self, param):
        """本地代理: 处理图片加载（备用，正常不走代理）"""
        try:
            if isinstance(param, str):
                from urllib.parse import parse_qs
                param_dict = parse_qs(param)
            else:
                param_dict = param

            do = param_dict.get('do', '')
            if isinstance(do, list):
                do = do[0] if do else ''

            if do == 'img':
                url = param_dict.get('url', '')
                if isinstance(url, list):
                    url = url[0] if url else ''

                if url:
                    try:
                        url = base64.urlsafe_b64decode(url).decode('utf-8')
                    except Exception:
                        pass

                    if url:
                        headers = {
                            'User-Agent': self.header['User-Agent'],
                            'Referer': self.host + '/',
                            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                        }
                        r = self.fetch(url, headers=headers, timeout=15)
                        content_type = ''
                        if hasattr(r, 'headers'):
                            ct = r.headers.get('Content-Type', '')
                            if ct and 'image' in ct:
                                content_type = ct
                        if not content_type:
                            if '.png' in url:
                                content_type = 'image/png'
                            elif '.webp' in url:
                                content_type = 'image/webp'
                            elif '.gif' in url:
                                content_type = 'image/gif'
                            else:
                                content_type = 'image/jpeg'
                        content = r.content if hasattr(r, 'content') else r.text.encode('utf-8')
                        return [200, content_type, content, {}]
        except Exception:
            pass
        return [404, 'text/plain', '', {}]

    # ===================================================================
    #  卡片解析（学习星辰影视优点：多层级回退，data-src 懒加载支持）
    # ===================================================================

    def _parse_cards(self, html):
        """解析视频卡片列表 - 针对 4kvms Tailwind CSS 结构"""
        vod_list = []
        seen = set()

        # 方法1: 匹配 movie-card 结构 (首页/分类页)
        # <div class="...movie-card..." data-vod-id="xxx">
        #   <div ...><a href="/play/xxx"><div><img data-src="图片URL" alt="标题"></div><h3>标题</h3></a></div>
        #   <div ...>hover预览...</div>
        # </div>
        card_opens = list(re.finditer(
            r'<div[^>]*class="[^"]*movie-card[^"]*"[^>]*data-vod-id="([^"]*)"',
            html
        ))

        for i, m in enumerate(card_opens):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            # 取当前卡片到下一卡片之间的内容（或最多3000字符）
            start = m.end()
            if i + 1 < len(card_opens):
                end = card_opens[i + 1].start()
            else:
                end = min(start + 3000, len(html))
            inner = html[start:end]

            # 提取标题 - 从第一个 h3 或 alt 属性
            name = ''
            h3_m = re.search(r'<h3[^>]*>(.*?)</h3>', inner, re.S)
            if h3_m:
                name = re.sub(r'<[^>]+>', '', h3_m.group(1)).strip()
            if not name:
                alt_m = re.search(r'alt="([^"]*)"', inner)
                if alt_m:
                    name = alt_m.group(1).strip()

            # 提取海报图片 - 第一个非占位图的 data-src
            pic_url = ''
            for ds_m in re.finditer(r'data-src="([^"]+)"', inner):
                url = ds_m.group(1)
                if 'placeholder' not in url and 'static/images' not in url:
                    pic_url = url
                    break

            # 提取备注 (评分/年份)
            remark = ''
            # 评分: <span class="text-green-500 font-bold">7.2</span>
            score_m = re.search(r'text-green-500[^>]*>([^<]+)', inner)
            if score_m:
                score = score_m.group(1).strip()
                if score and score.replace('.', '').isdigit():
                    remark = score
            # 年份
            if not remark:
                year_m = re.search(r'text-gray-400[^>]*>(20\d{2})', inner)
                if year_m:
                    remark = year_m.group(1)

            pic_url = self._wrap_pic(pic_url)

            vod_list.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': pic_url,
                'vod_remarks': remark,
            })

        # 方法2: 搜索结果页结构 (<div class="group relative"> + <a href="/play/xxx">)
        if not vod_list:
            # 匹配 <a href="/play/xxx" class="block"> 后面的 img data-src 和标题
            # 结构: <div class="group relative">
            #   <a href="/play/xxx" class="block">
            #     <div ...><img data-src="..." alt="标题" ...></div>
            #   </a>
            #   <h3>标题</h3> 或 <a href="/play/xxx"><h3>标题</h3></a>
            # </div>
            search_pattern = re.compile(
                r'<a\s+href="(/play/([a-zA-Z0-9]+))"\s+class="block">',
                re.S
            )
            search_matches = list(search_pattern.finditer(html))

            for i, m in enumerate(search_matches):
                href = m.group(1)
                vid = m.group(2)
                if vid in seen:
                    continue
                seen.add(vid)

                # 取当前链接到下一链接之间的内容
                start = m.end()
                if i + 1 < len(search_matches):
                    end = search_matches[i + 1].start()
                else:
                    end = min(start + 1500, len(html))
                inner = html[start:end]

                # 提取标题
                name = ''
                alt_m = re.search(r'alt="([^"]*)"', inner)
                if alt_m:
                    name = alt_m.group(1).strip()
                if not name:
                    h3_m = re.search(r'<h3[^>]*>(.*?)</h3>', inner, re.S)
                    if h3_m:
                        name = re.sub(r'<[^>]+>', '', h3_m.group(1)).strip()

                # 提取图片
                pic_url = ''
                ds_m = re.search(r'data-src="([^"]+)"', inner)
                if ds_m:
                    url = ds_m.group(1)
                    if 'placeholder' not in url and 'static/images' not in url:
                        pic_url = url
                if not pic_url:
                    src_m = re.search(r'<img[^>]*src="([^"]+)"', inner)
                    if src_m:
                        url = src_m.group(1)
                        if 'placeholder' not in url and 'static/images' not in url:
                            pic_url = url

                # 提取备注 (年份)
                remark = ''
                year_m = re.search(r'>(20\d{2})<', inner)
                if year_m:
                    remark = year_m.group(1)

                pic_url = self._wrap_pic(pic_url)

                vod_list.append({
                    'vod_id': vid,
                    'vod_name': name or vid,
                    'vod_pic': pic_url,
                    'vod_remarks': remark,
                })

        # 方法3: 最宽松的匹配 - 直接找 /play/ 链接 + 附近图片
        if not vod_list:
            pattern3 = re.compile(r'href="/play/([a-zA-Z0-9]+)"', re.S)
            matches3 = list(pattern3.finditer(html))
            for i, m in enumerate(matches3):
                vid = m.group(1)
                if vid in seen:
                    continue
                seen.add(vid)

                start = max(0, m.start() - 200)
                if i + 1 < len(matches3):
                    end = matches3[i + 1].start()
                else:
                    end = min(m.end() + 800, len(html))
                context = html[start:end]

                name = ''
                alt_m = re.search(r'alt="([^"]*)"', context)
                if alt_m:
                    name = alt_m.group(1).strip()

                pic_url = ''
                ds_m = re.search(r'data-src="([^"]+)"', context)
                if ds_m:
                    url = ds_m.group(1)
                    if 'placeholder' not in url and 'static/images' not in url:
                        pic_url = url

                pic_url = self._wrap_pic(pic_url)

                vod_list.append({
                    'vod_id': vid,
                    'vod_name': name or vid,
                    'vod_pic': pic_url,
                    'vod_remarks': '',
                })

        return vod_list

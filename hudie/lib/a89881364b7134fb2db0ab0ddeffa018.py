# -*- coding: utf-8 -*-
"""
=================================================
  刁民制作，仅供测试，测试完毕请于24小时删除。
=================================================

星辰影院 TVBox / OK影视 / 影视仓 标准 Python 源。

站点: http://www.dgpengcheng.com (MacCMS / stui 主题)

特点:
1. 支持 首页/分类/搜索/详情/播放 全流程。
2. 播放解析 player_aaaa 配置里的 m3u8 直链, URL 内嵌 sid 选择播放源。
3. 多线路多剧集支持, 播放源按速度排序 (快的靠前)。
4. 底部筛选器: 支持地区、年份筛选。
5. 尽量多抓播放源 (推荐线路/国内云播/国内光速/闪电播放/高速1等)。
6. 兼容 FongMi/TV (T3) & WebHomeTV / PeekPro (T4)。
"""

import sys
import json
import re
import base64
from urllib.parse import quote, urlencode

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
    星辰影院 Spider
    MacCMS / stui 主题, HTML 解析
    """

    host = 'http://www.dgpengcheng.com'

    header = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }

    # 分类列表
    classes = [
        {'type_name': '电影', 'type_id': '1'},
        {'type_name': '连续剧', 'type_id': '2'},
        {'type_name': '综艺', 'type_id': '3'},
        {'type_name': '动漫', 'type_id': '4'},
        {'type_name': '纪录片', 'type_id': '28'},
        {'type_name': '动作片', 'type_id': '6'},
        {'type_name': '喜剧片', 'type_id': '7'},
        {'type_name': '爱情片', 'type_id': '8'},
        {'type_name': '科幻片', 'type_id': '9'},
        {'type_name': '恐怖片', 'type_id': '10'},
        {'type_name': '战争片', 'type_id': '12'},
        {'type_name': '国产剧', 'type_id': '13'},
        {'type_name': '港台剧', 'type_id': '14'},
        {'type_name': '韩剧', 'type_id': '15'},
        {'type_name': '美剧', 'type_id': '16'},
        {'type_name': '日剧', 'type_id': '26'},
        {'type_name': '海外剧', 'type_id': '27'},
        {'type_name': '短视频', 'type_id': '36'},
    ]

    # 播放源速度优先级 (数字越小越快, 基于实际测速结果)
    # hnm3u8(国内云播) 最快 ~0.1s, gsm3u8(国内光速) ~2.4s, mtm3u8(推荐线路) SSL不稳定
    # sdm3u8(闪电播放) 和 wjm3u8(高速1) 速度中等
    _speed_priority = {
        'hnm3u8': 1,   # 国内云播 - 最快
        'sdm3u8': 2,   # 闪电播放
        'wjm3u8': 3,   # 高速1
        'gsm3u8': 4,   # 国内光速
        'mtm3u8': 5,   # 推荐线路
    }

    # 播放源名称映射 (from -> 显示名)
    _source_names = {
        'hnm3u8': '国内云播',
        'gsm3u8': '国内光速',
        'mtm3u8': '推荐线路',
        'sdm3u8': '闪电播放',
        'wjm3u8': '高速1',
    }

    # 筛选器: 地区
    _filter_area = [
        {'n': '全部', 'v': ''},
        {'n': '大陆', 'v': '大陆'},
        {'n': '内地', 'v': '内地'},
        {'n': '香港', 'v': '香港'},
        {'n': '台湾', 'v': '台湾'},
        {'n': '美国', 'v': '美国'},
        {'n': '日本', 'v': '日本'},
        {'n': '韩国', 'v': '韩国'},
        {'n': '泰国', 'v': '泰国'},
        {'n': '英国', 'v': '英国'},
        {'n': '法国', 'v': '法国'},
        {'n': '德国', 'v': '德国'},
        {'n': '印度', 'v': '印度'},
        {'n': '意大利', 'v': '意大利'},
        {'n': '西班牙', 'v': '西班牙'},
        {'n': '新加坡', 'v': '新加坡'},
        {'n': '其他', 'v': '其他'},
    ]

    # 筛选器: 年份
    _filter_year = [
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
        {'n': '2014', 'v': '2014'},
        {'n': '2013', 'v': '2013'},
        {'n': '2012', 'v': '2012'},
        {'n': '2011', 'v': '2011'},
        {'n': '2010', 'v': '2010'},
        {'n': '2009', 'v': '2009'},
    ]

    # ===================================================================
    #  基础方法
    # ===================================================================

    def getName(self):
        return '星辰影院'

    def init(self, extend=''):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''

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
        """获取页面 HTML"""
        url = path if path.startswith('http') else self.host + path
        r = self.fetch(url, headers=self.header, timeout=15)
        return r.text if hasattr(r, 'text') else r.content.decode('utf-8', errors='ignore')

    # ===================================================================
    #  图片代理
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

        # 如果已经是代理 URL 或 localhost，直接返回
        if '127.0.0.1' in pic_url or 'proxy' in pic_url:
            return pic_url

        # 补全协议头
        if pic_url.startswith('//'):
            pic_url = 'http:' + pic_url
        elif not pic_url.startswith(('http://', 'https://')):
            # 检查是否是完整域名但缺少协议 (常见图片CDN域名)
            if pic_url.startswith(('mtzy', 'hongniuzyimage', 'img.guangsuimage')):
                pic_url = 'http://' + pic_url
            else:
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
                {'key': 'area', 'name': '地区', 'value': self._filter_area},
                {'key': 'year', 'name': '年份', 'value': self._filter_year},
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

            area = ext.get('area', '')
            year = ext.get('year', '')

            # 无筛选器时用 vtype URL (分页正常)
            # 有筛选器时用 vodshow URL
            if not area and not year:
                if pg == 1:
                    url = '/vtype/%s.html' % tid
                else:
                    url = '/vtype/%s-%d.html' % (tid, pg)
            else:
                # vodshow URL: 12个字段 (11个dash)
                # /vodshow/{tid}-{area}-{class}-{by}-{lang}-{letter}-{?}-{?}-{page}-{?}-{?}-{year}.html
                # page=1 时不填 page 字段 (网站默认行为)
                area_enc = quote(area) if area else ''
                page_str = str(pg) if pg > 1 else ''
                fields = [str(tid), area_enc, '', '', '', '', '', '', page_str, '', '', str(year)]
                url = '/vodshow/' + '-'.join(fields) + '.html'

            html = self._fetch_html(url)
            vod_list = self._parse_cards(html)
            pagecount = self._parse_pagecount(html)

            return {
                'page': pg,
                'pagecount': pagecount,
                'limit': len(vod_list),
                'total': pagecount * 30 if pagecount < 999 else 99999,
                'list': vod_list,
            }
        except Exception:
            return {'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0, 'list': []}

    def _parse_pagecount(self, html):
        """从分页 HTML 中解析总页数"""
        try:
            # 找 /vtype/xxx-数字.html 中的最大数字
            nums = re.findall(r'/vtype/\d+-(\d+)\.html', html)
            if nums:
                return max(int(n) for n in nums)
            # 找 /vodshow/xxx...--------数字--- 中的最大数字 (page在字段8)
            nums2 = re.findall(r'/vodshow/\d+[^"]*--------(\d+)---', html)
            if nums2:
                return max(int(n) for n in nums2)
            # 找页码文本
            info = re.search(r'共\s*(\d+)\s*页', html)
            if info:
                return int(info.group(1))
            # 如果有 "下一页" 链接
            if '下一页' in html or 'nextpage' in html.lower():
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
            html = self._fetch_html('/varticle/%s.html' % vod_id)

            # 标题
            vod_name = ''
            title_match = re.search(r'<title>(.*?)</title>', html, re.S)
            if title_match:
                vod_name = title_match.group(1).strip()
                vod_name = re.sub(r'详情介绍.*$', '', vod_name)
                vod_name = re.sub(r'\s*-\s*星辰.*$', '', vod_name)
                vod_name = re.sub(r'\s*在线观看.*$', '', vod_name)

            # 描述
            vod_content = ''
            # stui theme: detail-content
            desc_m = re.search(r'class="detail-content"[^>]*>(.*?)</span>', html, re.S)
            if desc_m:
                vod_content = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip()
            if not vod_content:
                desc_m2 = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
                if desc_m2:
                    vod_content = desc_m2.group(1)

            # 封面图
            vod_pic = ''
            og = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', html)
            if og:
                vod_pic = og.group(1)
            if not vod_pic:
                # stui theme: stui-vodlist__thumb style background
                bg = re.search(r'class="stui-vodlist__thumb[^"]*"[^>]*style="background:\s*url\(([^)]+)\)', html)
                if bg:
                    vod_pic = bg.group(1)
            if not vod_pic:
                pic_m = re.search(r'<img[^>]*data-original="([^"]*)"', html)
                if pic_m:
                    vod_pic = pic_m.group(1)
            if not vod_pic:
                pic_m2 = re.search(r'<img[^>]*src="([^"]*\.(?:jpg|png|webp)[^"]*)"', html)
                if pic_m2:
                    vod_pic = pic_m2.group(1)
            vod_pic = self._wrap_pic(vod_pic)

            # 年份
            vod_year = ''
            year_m = re.search(r'年份：\s*</span>\s*<a[^>]*>(\d{4})', html)
            if year_m:
                vod_year = year_m.group(1)
            if not vod_year:
                year_m2 = re.search(r'/vodsearch/[^"]*-(\d{4})\.html', html)
                if year_m2:
                    vod_year = year_m2.group(1)

            # 类别
            vod_class = ''
            class_m = re.search(r'类型：\s*</span>\s*(.*?)(?:</p>|<br|</div)', html, re.S)
            if class_m:
                class_raw = class_m.group(1)
                # 只提取 <a> 标签内的文本, 避免抓到地区/年份等
                class_links = re.findall(r'<a[^>]*>([^<]+)</a>', class_raw)
                if class_links:
                    vod_class = ' '.join(c.strip() for c in class_links[:3])

            # 地区
            vod_area = ''
            area_m = re.search(r'地区：\s*</span>\s*<a[^>]*>([^<]+)', html)
            if area_m:
                vod_area = area_m.group(1).strip()
            if not vod_area:
                area_m2 = re.search(r'地区：\s*</span>\s*(.*?)(?:</p>|<br|</div)', html, re.S)
                if area_m2:
                    vod_area = re.sub(r'<[^>]+>', '', area_m2.group(1)).strip()

            # 演员
            vod_actor = ''
            actor_m = re.search(r'主演：\s*</span>\s*(.*?)(?:</p>|<br|</div)', html, re.S)
            if actor_m:
                vod_actor = re.sub(r'<[^>]+>', '', actor_m.group(1)).strip()
                vod_actor = vod_actor.replace('&nbsp;', ' ').strip()

            # 导演
            vod_director = ''
            director_m = re.search(r'导演：\s*</span>\s*(.*?)(?:</p>|<br|</div)', html, re.S)
            if director_m:
                vod_director = re.sub(r'<[^>]+>', '', director_m.group(1)).strip()
                vod_director = vod_director.replace('&nbsp;', ' ').strip()

            # 提取播放源和剧集
            # stui 主题: 按 stui-pannel__head 分割, 每个面板包含一个源
            play_from_list = []
            play_url_list = []
            source_from_map = {}  # from标识 -> (显示名, 剧集列表)

            sections = html.split('stui-pannel__head')
            for sec in sections[1:]:
                # 提取源名
                h3_m = re.search(r'<h3[^>]*>(.*?)</h3>', sec[:300], re.S)
                if not h3_m:
                    continue
                source_display_name = re.sub(r'<[^>]+>', '', h3_m.group(1)).strip()
                # 跳过 "猜你喜欢" 等非播放源面板
                if '猜你' in source_display_name or '推荐' in source_display_name and '线路' not in source_display_name:
                    continue

                # 提取剧集链接: /vplay/{vid}-{sid}-{ep}.html
                ep_links = re.findall(
                    r"href='?/vplay/(\d+)-(\d+)-(\d+)\.html'?[^\>]*>([^<]*)",
                    sec
                )
                if not ep_links:
                    ep_links = re.findall(
                        r'href="?/vplay/(\d+)-(\d+)-(\d+)\.html"?[^>]*>([^<]*)',
                        sec
                    )

                if not ep_links:
                    continue

                episodes = []
                seen_eps = set()
                sid = ''
                for vid, ep_sid, ep_num, ep_name in ep_links:
                    clean_name = ep_name.strip()
                    if not clean_name or clean_name in seen_eps:
                        continue
                    seen_eps.add(clean_name)
                    sid = ep_sid
                    # play_id 格式: vid-sid-ep (与 URL 一致)
                    play_id = '%s-%s-%s' % (vid, sid, ep_num)
                    episodes.append('%s$%s' % (clean_name, play_id))

                if episodes:
                    play_from_list.append(source_display_name)
                    play_url_list.append('#'.join(episodes))
                    # 记录 sid 用于后续获取 from 标识
                    source_from_map[source_display_name] = sid

            # 如果没有找到播放源, 尝试从页面查找所有 vplay 链接
            if not play_from_list:
                all_play_links = re.findall(
                    r"href='?/vplay/(\d+)-(\d+)-(\d+)\.html'?[^\>]*>([^<]*)",
                    html
                )
                if all_play_links:
                    # 按 sid 分组
                    sid_groups = {}
                    for vid, sid, ep, name in all_play_links:
                        if sid not in sid_groups:
                            sid_groups[sid] = []
                        clean_name = name.strip()
                        if clean_name:
                            sid_groups[sid].append('%s$%s-%s-%s' % (clean_name, vid, sid, ep))

                    for sid, eps in sid_groups.items():
                        play_from_list.append('线路%s' % sid)
                        play_url_list.append('#'.join(eps))

            # 按速度排序播放源 (快的靠前)
            # 需要先获取每个源的 from 标识来判断速度
            # 在详情页阶段无法获取 from, 按已知源名排序
            if play_from_list:
                paired = list(zip(play_from_list, play_url_list))
                # 使用源名的速度优先级排序
                paired.sort(key=lambda x: self._get_source_priority(x[0]))
                play_from_list = [p[0] for p in paired]
                play_url_list = [p[1] for p in paired]

            vod = {
                'vod_id': vod_id,
                'vod_name': vod_name,
                'vod_pic': vod_pic,
                'type_name': vod_class or '星辰',
                'vod_year': vod_year,
                'vod_area': vod_area,
                'vod_actor': vod_actor,
                'vod_director': vod_director,
                'vod_content': vod_content,
                'vod_remarks': '',
                'vod_play_from': '$$$'.join(play_from_list) if play_from_list else '星辰',
                'vod_play_url': '$$$'.join(play_url_list) if play_url_list else '',
            }
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    def _get_source_priority(self, source_name):
        """根据播放源名称获取速度优先级"""
        name_lower = source_name.lower()
        for key, priority in self._speed_priority.items():
            display = self._source_names.get(key, '')
            if display and display in source_name:
                return priority
            if key in name_lower:
                return priority
        # 未知源排最后
        return 999

    # ===================================================================
    #  搜索（修复版）
    # ===================================================================

    def searchContent(self, key, quick, pg=1):
        try:
            pg = int(pg or 1)
            encoded_key = quote(key)
            # 优先使用查询参数方式（更标准）
            search_urls = [
                f"/vodsearch/-------------.html?wd={encoded_key}&page={pg}",
                f"/vodsearch/{encoded_key}-------------.html",
                f"/vodsearch/{encoded_key}----------{pg}---.html",
            ]
            html = None
            for path in search_urls:
                try:
                    html = self._fetch_html(path)
                    if html and len(html) > 100:
                        break
                except:
                    continue
            if not html:
                return {'list': [], 'page': pg}

            vod_list = self._parse_cards(html)
            # 如果解析结果为空，使用备用正则提取
            if not vod_list:
                vod_list = self._parse_search_result(html)

            return {
                'list': vod_list[:30],
                'page': pg,
            }
        except Exception:
            return {'list': [], 'page': 1}

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    def _parse_search_result(self, html):
        """当常规卡片解析失效时，直接从搜索结果中提取视频信息"""
        vod_list = []
        # 匹配常见的搜索列表结构
        pattern = r'<a[^>]*href="/varticle/(\d+)\.html"[^>]*title="([^"]*)"[^>]*>.*?<img[^>]*src="([^"]+)"'
        matches = re.findall(pattern, html, re.S)
        for vid, name, pic in matches:
            vod_list.append({
                'vod_id': vid,
                'vod_name': name.strip(),
                'vod_pic': self._wrap_pic(pic),
                'vod_remarks': ''
            })
        # 如果上面没匹配到，尝试更宽松的模式
        if not vod_list:
            pattern2 = r'href="/varticle/(\d+)\.html"[^>]*>(.*?)</a>.*?<img[^>]*src="([^"]+)"'
            matches2 = re.findall(pattern2, html, re.S)
            for vid, name, pic in matches2:
                name_clean = re.sub(r'<[^>]+>', '', name).strip()
                vod_list.append({
                    'vod_id': vid,
                    'vod_name': name_clean or f'视频{vid}',
                    'vod_pic': self._wrap_pic(pic),
                    'vod_remarks': ''
                })
        return vod_list

    # ===================================================================
    #  播放
    # ===================================================================

    def playerContent(self, flag, id, vipFlags):
        try:
            play_id = str(id or '')

            # 解析播放 ID: vid-sid-ep (与 URL 一致: /vplay/{vid}-{sid}-{ep}.html)
            parts = play_id.split('-')
            if len(parts) >= 3:
                vid, sid, ep = parts[0], parts[1], parts[2]
            elif len(parts) == 2:
                vid, sid, ep = parts[0], '1', parts[1]
            else:
                return {'parse': 1, 'url': play_id}

            # 访问播放页获取 player_aaaa
            # URL 格式: /vplay/{vid}-{sid}-{ep}.html
            play_url = '/vplay/%s-%s-%s.html' % (vid, sid, ep)
            html = self._fetch_html(play_url)

            # 解析 player_aaaa JSON
            pa = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</', html, re.S)
            if pa:
                try:
                    data = json.loads(pa.group(1))
                    m3u8_url = data.get('url', '')
                    if m3u8_url and ('.m3u8' in m3u8_url or '.mp4' in m3u8_url):
                        return {
                            'parse': 0,
                            'url': m3u8_url,
                            'header': {
                                'User-Agent': self.header['User-Agent'],
                                'Referer': self.host + '/',
                            },
                        }
                except Exception:
                    pass

            # 尝试直接从页面提取 m3u8
            m3u8 = re.search(r'"url"\s*:\s*"(https?:[^"]*\.(?:m3u8|mp4)[^"]*)"', html)
            if m3u8:
                m3u8_url = m3u8.group(1).replace('\\/', '/')
                return {
                    'parse': 0,
                    'url': m3u8_url,
                    'header': {
                        'User-Agent': self.header['User-Agent'],
                        'Referer': self.host + '/',
                    },
                }

            # 解析失败, 交给通用解析
            return {
                'parse': 1,
                'url': self.host + play_url,
                'header': {'User-Agent': self.header['User-Agent']},
            }
        except Exception:
            return {}

    # ===================================================================
    #  本地代理 (图片代理)
    # ===================================================================

    def localProxy(self, param):
        """本地代理: 处理图片加载"""
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
    #  卡片解析
    # ===================================================================

    def _parse_cards(self, html):
        """解析视频卡片列表 - 针对实际HTML结构，多层级回退确保图片正确提取"""
        vod_list = []
        seen = set()

        # 方法1: 匹配 stui-vodlist__box 结构 (最准确)
        # 每个视频卡片: <li class="col-md-5 col-sm-4 col-xs-3">
        #   <div class="stui-vodlist__box">
        #     <a class="stui-vodlist__thumb" href="/varticle/xxx.html" title="xxx">
        #       <img src="图片URL" alt="xxx">
        #       <span class="pic-text">备注</span>
        #     </a>
        #     <div class="stui-vodlist__detail">
        #       <h4><a href="...">标题</a></h4>
        #     </div>
        #   </div>
        # </li>
        li_pattern = r'<li[^>]*class="[^"]*col-md-5[^"]*"[^>]*>(.*?)</li>'
        li_matches = re.findall(li_pattern, html, re.S)

        for li_html in li_matches:
            # 提取视频ID
            id_match = re.search(r'href="/varticle/(\d+)\.html"', li_html)
            if not id_match:
                continue
            vid = id_match.group(1)

            if vid in seen:
                continue
            seen.add(vid)

            # 提取标题 - 先从 title 属性，后备从 h4 标签
            title_match = re.search(r'title="([^"]*)"', li_html)
            if not title_match:
                title_match = re.search(r'<h4[^>]*>.*?<a[^>]*>([^<]+)</a>', li_html, re.S)
            name = title_match.group(1).strip() if title_match else f'视频{vid}'

            # 提取图片URL - src 优先, 然后 data-original, 最后 background 样式
            pic_url = ''
            img_match = re.search(r'<img[^>]*src="([^"]+)"[^>]*>', li_html)
            if img_match:
                pic_url = img_match.group(1)
            if not pic_url:
                img_match = re.search(r'<img[^>]*data-original="([^"]+)"', li_html)
                if img_match:
                    pic_url = img_match.group(1)
            if not pic_url:
                bg_match = re.search(r'background:\s*url\(([^)]+)\)', li_html)
                if bg_match:
                    pic_url = bg_match.group(1)

            pic_url = self._wrap_pic(pic_url)

            # 提取备注
            remark = ''
            remark_match = re.search(r'class="pic-text[^"]*"[^>]*>([^<]+)', li_html)
            if remark_match:
                remark = remark_match.group(1).strip()

            vod_list.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': pic_url,
                'vod_remarks': remark,
            })

        # 方法2: 直接匹配 stui-vodlist__thumb (方法1未找到时使用)
        if not vod_list:
            pattern = (
                r'<a[^>]*class="stui-vodlist__thumb[^"]*"[^>]*'
                r'href="/varticle/(\d+)\.html"[^>]*'
                r'title="([^"]*)"[^>]*>(.*?)</a>'
            )
            matches = re.findall(pattern, html, re.S)

            for vid, name, inner in matches:
                if vid in seen:
                    continue
                seen.add(vid)

                # 提取图片 - src 优先, 然后 background, 最后 data-original
                pic_url = ''
                img_match = re.search(r'<img[^>]*src="([^"]+)"', inner)
                if img_match:
                    pic_url = img_match.group(1)
                if not pic_url:
                    bg_match = re.search(r'background:\s*url\(([^)]+)\)', inner)
                    if bg_match:
                        pic_url = bg_match.group(1)
                if not pic_url:
                    img_match2 = re.search(r'data-original="([^"]*)"', inner)
                    if img_match2:
                        pic_url = img_match2.group(1)

                pic_url = self._wrap_pic(pic_url)

                # 提取备注
                remark = ''
                remark_match = re.search(r'class="pic-text[^"]*"[^>]*>([^<]+)', inner)
                if remark_match:
                    remark = remark_match.group(1).strip()

                vod_list.append({
                    'vod_id': vid,
                    'vod_name': name.strip(),
                    'vod_pic': pic_url,
                    'vod_remarks': remark,
                })

        return vod_list
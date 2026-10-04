# coding=utf-8
"""
目标站: 芭蕉剧场 (https://www.fesall.net)
模板: m4-huang 自定义
功能: 首页推荐 / 二级分类筛选 / 详情 / 搜索 / 播放解析(多线路)
优化: 正则预编译、域名缓存、m3u8 可达性检测、连接复用、最小请求、详情缓存、极速播放
"""
import re
import sys
import json
import urllib.parse

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    # ===================== 初始化 =====================
    def init(self, extend=""):
        self.site_url = "https://www.fesall.net"

        # 精简请求头 (只保留必要的)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
        }

        # 播放专用头 (极简)
        self.play_headers = {
            'User-Agent': self.headers['User-Agent'],
            'Referer': self.site_url + '/',
        }

        # 一级分类
        self.categories = [
            {"type_id": "1",  "type_name": "电影"},
            {"type_id": "2",  "type_name": "电视剧"},
            {"type_id": "3",  "type_name": "短剧"},
            {"type_id": "4",  "type_name": "动漫"},
            {"type_id": "5",  "type_name": "综艺"},
            {"type_id": "48", "type_name": "Netflix"},
            {"type_id": "47", "type_name": "AI漫剧"},
        ]

        # 二级分类筛选器
        _class_opts = self._build_opts([
            "古装", "都市", "悬疑", "喜剧", "武侠", "奇幻", "科幻",
            "家庭", "犯罪", "历史", "谍战", "仙侠", "穿越", "爱情",
            "剧情", "惊悚", "冒险", "动作", "动画", "青春", "伦理",
        ])
        _area_opts = self._build_opts([
            "大陆", "香港", "台湾", "美国", "韩国", "日本", "泰国", "英国", "其他",
        ])
        _year_opts = self._build_opts([
            "2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018",
        ])
        _by_opts = [
            {"n": "相关度", "v": ""},
            {"n": "最新",   "v": "time"},
            {"n": "最热",   "v": "hits"},
        ]

        filter_tpl = [
            {"key": "class", "name": "剧情", "value": _class_opts},
            {"key": "area",  "name": "地区", "value": _area_opts},
            {"key": "year",  "name": "年份", "value": _year_opts},
            {"key": "by",    "name": "排序", "value": _by_opts},
        ]
        self.filters = {c["type_id"]: filter_tpl for c in self.categories}

        # ---- 预编译正则 (性能核心) ----
        # 列表页: 一条正则同时提取所有字段
        self._re_card = re.compile(
            r'<a\s+class="pc"\s+href="(/video/(\d+)\.html)"[^>]*>'
            r'.*?<img\s+[^>]*src="([^"]+)"[^>]*>'
            r'.*?<span\s+class="sc">([^<]*)</span>'
            r'.*?<div\s+class="nm">([^<]*)</div>'
            r'.*?<div\s+class="mt">([^<]*)</div>',
            re.DOTALL
        )
        # 通用备选 (兼容搜索页/分类页)
        self._re_card_lazy = re.compile(
            r'<a\s+[^>]*href="(/video/(\d+)\.html)"[^>]*>'
            r'.*?<img\s+[^>]*src="([^"]+)"[^>]*>'
            r'.*?<div\s+class="nm">([^<]*)</div>',
            re.DOTALL
        )
        # 暴力兜底
        self._re_card_brute = re.compile(
            r'href="(/video/(\d+)\.html)"[^>]*>([^<]{2,50})</a>',
            re.DOTALL
        )
        # 分页
        self._re_page_link = re.compile(r'href="/tv/\d+[_-]?(\d+)?\.html"')
        self._re_page_text = re.compile(r'共\s*(\d+)\s*页')
        self._re_search_page = re.compile(r'[?&]page=(\d+)')
        # 详情页
        self._re_title = re.compile(r'<h1[^>]*>([^<]+)</h1>')
        self._re_desc = re.compile(r'(?:剧情简介|简介|剧情介绍)[^>]*>(.*?)</div>', re.DOTALL | re.I)
        self._re_detail_img = re.compile(r'<img\s+[^>]*src="([^"]+)"[^>]*alt="[^"]*"[^>]*>')
        # 播放页
        self._re_m3u8 = re.compile(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*')
        self._re_mp4 = re.compile(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*')
        self._re_play_data = re.compile(r'data-play=["\']?(https?://[^"\']+)["\']?')
        self._re_js_player = re.compile(r'player\s*\{\s*url\s*:\s*["\']([^"\']+)["\']')
        # 线路
        self._re_source_name = re.compile(
            r'<[^>]*(?:source|tab|play-from|line|channel)[^>]*>([^<]{1,20})</[^>]+>',
            re.I
        )
        self._re_source_attr = re.compile(
            r'(?:data-source|data-play-from|data-tab|data-line)=["\']([^"\']+)["\']',
            re.I
        )
        self._re_ep_link = re.compile(
            r'<a\s+[^>]*href="(/[^"]*(?:play|player|video)[^"]*?(\d+)[^"]*)"[^>]*>([^<]+)</a>',
            re.I
        )
        self._re_ep_lazy = re.compile(
            r'<a\s+[^>]*href="(/[^"]+)"[^>]*>(第?\d+集?|正片|全集|立即播放|HD[^<]*)</a>',
            re.I
        )

        # ---- 缓存 ----
        self._detail_cache = {}      # vod_id -> detail_result
        self._play_cache = {}        # play_url -> media_url
        self._alive_domains = set()  # 已确认可用域名
        self._dead_domains = set()   # 已确认失效域名

    @staticmethod
    def _build_opts(names):
        return [{"n": "全部", "v": ""}] + [{"n": n, "v": n} for n in names]

    # ===================== 工具方法 =====================
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

    def _fetch(self, url, max_retry=0):
        """单次请求，默认0次重试，追求极速"""
        try:
            resp = self.fetch(url, headers=self.headers)
            if resp and resp.text:
                return resp
        except Exception:
            if max_retry > 0:
                try:
                    resp = self.fetch(url, headers=self.headers)
                    if resp and resp.text:
                        return resp
                except Exception:
                    pass
        return None

    def _check_m3u8_alive(self, m3u8_url):
        """快速检测 m3u8 是否可达 (带域名缓存，只验证一次)"""
        dm_m = re.match(r'https?://([^/]+)', m3u8_url)
        if not dm_m:
            return False
        domain = dm_m.group(1)
        if domain in self._alive_domains:
            return True
        if domain in self._dead_domains:
            return False
        try:
            # 只请求前512字节，快速验证
            resp = self.fetch(m3u8_url, headers=self.play_headers)
            if resp and resp.text and '#EXTM3U' in resp.text[:50]:
                self._alive_domains.add(domain)
                return True
        except Exception:
            pass
        self._dead_domains.add(domain)
        return False

    # ===================== 列表解析 (三重兼容，极速) =====================
    def _parse_list(self, html):
        results = []
        seen = set()

        # 策略1: 精确匹配
        for m in self._re_card.finditer(html):
            vid = m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            results.append({
                "vod_id": vid,
                "vod_name": m.group(5).strip(),
                "vod_pic": self._fix_url(m.group(3)),
                "vod_remarks": m.group(6).strip(),
            })

        if results:
            return results

        # 策略2: 宽松匹配
        for m in self._re_card_lazy.finditer(html):
            vid = m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            ctx = html[m.start():m.end()+200]
            rm = re.search(r'<div\s+class="mt">([^<]*)</div>', ctx)
            results.append({
                "vod_id": vid,
                "vod_name": m.group(4).strip(),
                "vod_pic": self._fix_url(m.group(3)),
                "vod_remarks": rm.group(1).strip() if rm else '',
            })

        if results:
            return results

        # 策略3: 暴力兜底
        for m in self._re_card_brute.finditer(html):
            vid = m.group(2)
            title = re.sub(r'<[^>]+>', '', m.group(3)).strip()
            if not title or len(title) < 2 or vid in seen:
                continue
            seen.add(vid)
            results.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": "",
                "vod_remarks": "",
            })

        return results

    def _extract_pagecount(self, html, page=1):
        max_pg = page
        for m in self._re_page_link.finditer(html):
            pg = m.group(1)
            if pg and pg.isdigit():
                max_pg = max(max_pg, int(pg))
        for m in self._re_search_page.finditer(html):
            max_pg = max(max_pg, int(m.group(1)))
        m = self._re_page_text.search(html)
        if m:
            max_pg = max(max_pg, int(m.group(1)))
        return max_pg if max_pg > page else page + 1

    # ===================== 首页 =====================
    def homeContent(self, filter):
        resp = self._fetch(self.site_url + "/")
        video_list = self._parse_list(resp.text) if resp else []
        return {
            "class": self.categories,
            "list": video_list[:36],
            "filters": self.filters,
        }

    def homeVideoContent(self):
        resp = self._fetch(self.site_url + "/")
        video_list = self._parse_list(resp.text) if resp else []
        return {"list": video_list[:20]}

    # ===================== 二级分类 =====================
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        ext = {}
        if extend:
            if isinstance(extend, str):
                try:
                    ext = json.loads(extend)
                except Exception:
                    ext = {}
            elif isinstance(extend, dict):
                ext = extend

        cls = ext.get('class', '')
        area = ext.get('area', '')
        year = ext.get('year', '')
        by = ext.get('by', '')

        # 无筛选时走纯伪静态，更快
        if page == 1:
            url = f"{self.site_url}/tv/{tid}.html"
        else:
            url = f"{self.site_url}/tv/{tid}_{page}.html"

        # 有筛选时加参数
        params = {}
        if cls:
            params['class'] = cls
        if area:
            params['area'] = area
        if year:
            params['year'] = year
        if by:
            params['by'] = by
        if params:
            url += '?' + urllib.parse.urlencode(params)

        resp = self._fetch(url)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}

        html = resp.text
        video_list = self._parse_list(html)
        pagecount = self._extract_pagecount(html, page)
        return {
            "list": video_list, "page": page,
            "pagecount": pagecount, "limit": 24, "total": len(video_list) * pagecount,
        }

    # ===================== 详情 (带缓存) =====================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}

        vod_id = str(ids[0])
        # 命中缓存直接返回
        if vod_id in self._detail_cache:
            return self._detail_cache[vod_id]

        url = f"{self.site_url}/video/{vod_id}.html"
        resp = self._fetch(url)
        if not resp:
            return {"list": []}

        html = resp.text

        # 标题
        vod_name = vod_id
        m = self._re_title.search(html)
        if m:
            vod_name = m.group(1).strip()
        else:
            m = re.search(r'<title>([^<]+)</title>', html)
            if m:
                vod_name = m.group(1).split('-')[0].split('_')[0].strip()

        # 封面
        vod_pic = ''
        m = self._re_detail_img.search(html)
        if m:
            vod_pic = self._fix_url(m.group(1))

        # 简介
        vod_content = '暂无剧情'
        m = self._re_desc.search(html)
        if m:
            vod_content = re.sub(r'<[^>]+>', '', m.group(1)).strip()

        # 元数据
        vod_director = self._extract_meta(html, '导演')
        vod_actor = self._extract_meta(html, '主演')
        vod_year = self._extract_meta(html, '年份') or self._extract_meta(html, '年代')
        vod_area = self._extract_meta(html, '地区')

        # 播放列表
        play_from_list, play_url_list = self._parse_playlist(html, vod_id)

        if not play_url_list:
            play_from_list.append('默认线路')
            play_url_list.append(f"播放${url}")

        result = {
            "list": [{
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_content": vod_content,
                "vod_actor": vod_actor,
                "vod_director": vod_director,
                "vod_area": vod_area,
                "vod_year": vod_year,
                "vod_play_from": '$$$'.join(play_from_list),
                "vod_play_url": '$$$'.join(play_url_list),
            }]
        }
        # 写入缓存
        self._detail_cache[vod_id] = result
        return result

    def _extract_meta(self, html, field):
        for p in [
            rf'{field}[:：]\s*([^<\n]+)',
            rf'{field}</[^>]+>\s*([^<\n]+)',
            rf'{field}[^>]*>([^<]+)',
        ]:
            m = re.search(p, html)
            if m:
                return re.sub(r'<[^>]+>', '', m.group(1)).strip()
        return ''

    def _parse_playlist(self, html, vod_id):
        """解析多线路播放列表"""
        play_from_list = []
        play_url_list = []

        # 步骤1: 提取线路名
        source_names = []
        for m in self._re_source_name.finditer(html):
            name = m.group(1).strip()
            if name and name not in source_names and len(name) < 20:
                source_names.append(name)
        if not source_names:
            for m in self._re_source_attr.finditer(html):
                name = m.group(1).strip()
                if name and name not in source_names:
                    source_names.append(name)

        # 步骤2: 提取选集
        all_eps = []
        for m in self._re_ep_link.finditer(html):
            href = m.group(1)
            name = m.group(3).strip()
            parts = re.findall(r'\d+', href)
            sid_hint = parts[-2] if len(parts) >= 2 else None
            all_eps.append((m.start(), href, name, sid_hint))
        if not all_eps:
            for m in self._re_ep_lazy.finditer(html):
                all_eps.append((m.start(), m.group(1), m.group(2).strip(), None))

        # 步骤3: 按线路分组
        if source_names and all_eps:
            source_positions = []
            for name in source_names:
                idx = html.find(name)
                if idx >= 0:
                    source_positions.append((idx, name))
            source_positions.sort()

            groups = {name: [] for _, name in source_positions}
            for pos, href, name, sid_hint in all_eps:
                assigned = None
                for spos, sname in source_positions:
                    if spos <= pos:
                        assigned = sname
                if assigned:
                    groups[assigned].append(f"{name}${self._fix_url(href)}")
                elif source_positions:
                    groups[source_positions[0][1]].append(f"{name}${self._fix_url(href)}")

            for _, name in source_positions:
                if groups[name]:
                    play_from_list.append(name)
                    play_url_list.append('#'.join(groups[name]))

        elif all_eps:
            groups = {}
            for pos, href, name, sid_hint in all_eps:
                sid = sid_hint if sid_hint else '1'
                groups.setdefault(sid, []).append(f"{name}${self._fix_url(href)}")
            for sid in sorted(groups.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
                play_from_list.append('默认线路' if len(groups) == 1 else f"线路{sid}")
                play_url_list.append('#'.join(groups[sid]))

        # 兜底: JS变量 / 直链
        if not play_url_list:
            for pattern in [
                r'var\s+player_[a-z]*\s*=\s*({.+?});',
                r'player\s*\(\s*({.+?})\s*\)',
                r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"',
            ]:
                m = re.search(pattern, html, re.DOTALL)
                if m:
                    try:
                        url = m.group(1) if pattern.endswith('.m3u8[^"]*)"') else json.loads(m.group(1)).get('url', '')
                        if url:
                            play_from_list.append('默认线路')
                            play_url_list.append(f"正片${self._fix_url(url)}")
                            break
                    except Exception:
                        pass
            if not play_url_list:
                m3u8 = self._re_m3u8.search(html)
                if m3u8:
                    play_from_list.append('默认线路')
                    play_url_list.append(f"正片${m3u8.group(0)}")

        return play_from_list, play_url_list

    # ===================== 搜索 =====================
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded = urllib.parse.quote(key)

        urls_to_try = [
            f"{self.site_url}/search.html?wd={encoded}",
            f"{self.site_url}/search?wd={encoded}",
        ]
        if page > 1:
            urls_to_try = [u + f"&page={page}" for u in urls_to_try]

        html = None
        for url in urls_to_try:
            resp = self._fetch(url)
            if resp and resp.text and '/video/' in resp.text:
                html = resp.text
                break

        if not html:
            return {"list": [], "page": page, "pagecount": 1}

        video_list = self._parse_list(html)
        pagecount = self._extract_pagecount(html, page)

        if not video_list:
            for m in re.finditer(r'href="(/video/(\d+)\.html)"[^>]*>([^<]{2,50})</a>', html):
                video_list.append({
                    "vod_id": m.group(2),
                    "vod_name": m.group(3).strip(),
                    "vod_pic": "",
                    "vod_remarks": "",
                })

        return {"list": video_list, "page": page, "pagecount": pagecount}

    # ===================== 播放 (极速模式) =====================
    def playerContent(self, flag, id, vipFlags):
        # 标准化 URL
        if id.startswith('http'):
            play_url = id
        elif id.startswith('/'):
            play_url = self.site_url + id
        else:
            play_url = self.site_url + '/' + id

        # 直接媒体地址: 跳过检测，直接返回 (让播放器自己验证)
        if '.m3u8' in play_url or '.mp4' in play_url:
            return {"parse": 0, "url": play_url, "header": self.play_headers}

        # 播放页缓存
        if play_url in self._play_cache:
            return {"parse": 0, "url": self._play_cache[play_url], "header": self.play_headers}

        # 请求播放页 (仅一次，0重试)
        resp = self._fetch(play_url)
        if not resp:
            return {"parse": 1, "url": play_url, "header": self.play_headers}

        html = resp.text
        media_url = self._extract_media(html)

        if media_url:
            # 缓存播放地址
            self._play_cache[play_url] = media_url
            return {"parse": 0, "url": media_url, "header": self.play_headers}

        # 兜底: 让播放器解析页面
        return {"parse": 1, "url": play_url, "header": self.play_headers}

    def _extract_media(self, html):
        for pattern in [self._re_play_data, self._re_js_player, self._re_m3u8, self._re_mp4]:
            m = pattern.search(html)
            if m:
                url = m.group(1)
                if url.startswith('http'):
                    return url
                elif url.startswith('//'):
                    return 'https:' + url
        return None

    # ===================== 其他 =====================
    def isVideoFormat(self, url):
        return '.m3u8' in url or '.mp4' in url

    def manualVideoCheck(self):
        return False

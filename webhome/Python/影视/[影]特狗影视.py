# -*- coding: utf-8 -*-
"""
特狗影视 (tegou.me) 爬虫 - 兼容 FongMi/TV (T3) 与 WebHomeTV (T4)
站点: https://www.tegou.me
特点: MacCMS + stui主题(shorttu14), 解析接口提取m3u8直链
"""

import sys
import json
import re

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import urllib.request
    import ssl
    class Spider:
        def fetch(self, url, headers=None, **kw):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers=headers or {})
            resp = urllib.request.urlopen(req, timeout=10, context=ctx)
            class R:
                def __init__(self, r):
                    self.text = r.read().decode('utf-8', errors='replace')
                    self.status_code = r.status
                def json(self):
                    return json.loads(self.text)
            return R(resp)


class Spider(Spider):

    HOST = 'https://www.tegou.me'

    # ========== 子分类筛选数据 ==========
    FILTERS = {
        "1": [
            {"key": "class", "name": "剧情", "value": [
                {"n": "全部", "v": ""}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"},
                {"n": "恐怖", "v": "恐怖"}, {"n": "动作", "v": "动作"}, {"n": "科幻", "v": "科幻"},
                {"n": "剧情", "v": "剧情"}, {"n": "战争", "v": "战争"}, {"n": "警匪", "v": "警匪"},
                {"n": "犯罪", "v": "犯罪"}, {"n": "动画", "v": "动画"}, {"n": "奇幻", "v": "奇幻"},
                {"n": "武侠", "v": "武侠"}, {"n": "冒险", "v": "冒险"}, {"n": "枪战", "v": "枪战"},
                {"n": "悬疑", "v": "悬疑"}, {"n": "惊悚", "v": "惊悚"}, {"n": "经典", "v": "经典"},
                {"n": "青春", "v": "青春"}, {"n": "文艺", "v": "文艺"}, {"n": "微电影", "v": "微电影"},
                {"n": "古装", "v": "古装"}, {"n": "历史", "v": "历史"}, {"n": "运动", "v": "运动"},
                {"n": "农村", "v": "农村"}, {"n": "儿童", "v": "儿童"}, {"n": "网络电影", "v": "网络电影"},
            ]},
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "法国", "v": "法国"},
                {"n": "英国", "v": "英国"}, {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"},
                {"n": "德国", "v": "德国"}, {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"},
                {"n": "意大利", "v": "意大利"}, {"n": "西班牙", "v": "西班牙"}, {"n": "加拿大", "v": "加拿大"},
                {"n": "其他", "v": "其他"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"},
                {"n": "2016-2011", "v": "2016-2011"}, {"n": "2010-2000", "v": "2010-2000"},
                {"n": "1999-1990", "v": "1999-1990"}, {"n": "1989-1980", "v": "1989-1980"},
            ]},
        ],
        "2": [
            {"key": "class", "name": "剧情", "value": [
                {"n": "全部", "v": ""}, {"n": "古装", "v": "古装"}, {"n": "战争", "v": "战争"},
                {"n": "青春偶像", "v": "青春偶像"}, {"n": "喜剧", "v": "喜剧"}, {"n": "家庭", "v": "家庭"},
                {"n": "犯罪", "v": "犯罪"}, {"n": "动作", "v": "动作"}, {"n": "奇幻", "v": "奇幻"},
                {"n": "剧情", "v": "剧情"}, {"n": "历史", "v": "历史"}, {"n": "经典", "v": "经典"},
                {"n": "乡村", "v": "乡村"}, {"n": "情景", "v": "情景"}, {"n": "商战", "v": "商战"},
                {"n": "网剧", "v": "网剧"}, {"n": "其他", "v": "其他"},
            ]},
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"}, {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"},
                {"n": "美国", "v": "美国"}, {"n": "泰国", "v": "泰国"}, {"n": "英国", "v": "英国"},
                {"n": "新加坡", "v": "新加坡"}, {"n": "其他", "v": "其他"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"},
                {"n": "2016-2011", "v": "2016-2011"}, {"n": "2010-2000", "v": "2010-2000"},
                {"n": "1999-1990", "v": "1999-1990"}, {"n": "1989-1980", "v": "1989-1980"},
            ]},
        ],
        "3": [
            {"key": "class", "name": "剧情", "value": [
                {"n": "全部", "v": ""}, {"n": "热门", "v": "热门"}, {"n": "搞笑", "v": "搞笑"},
                {"n": "番剧", "v": "番剧"}, {"n": "国创", "v": "国创"}, {"n": "大电影", "v": "大电影"},
                {"n": "热血", "v": "热血"}, {"n": "催泪", "v": "催泪"}, {"n": "治愈", "v": "治愈"},
                {"n": "励志", "v": "励志"}, {"n": "机战", "v": "机战"}, {"n": "战斗", "v": "战斗"},
                {"n": "恋爱", "v": "恋爱"}, {"n": "科幻", "v": "科幻"}, {"n": "奇幻", "v": "奇幻"},
                {"n": "魔幻", "v": "魔幻"}, {"n": "推理", "v": "推理"}, {"n": "校园", "v": "校园"},
                {"n": "日常", "v": "日常"}, {"n": "经典", "v": "经典"}, {"n": "历史", "v": "历史"},
                {"n": "美食", "v": "美食"}, {"n": "职场", "v": "职场"}, {"n": "偶像", "v": "偶像"},
                {"n": "泡面", "v": "泡面"}, {"n": "冒险", "v": "冒险"}, {"n": "竞技", "v": "竞技"},
                {"n": "合家欢", "v": "合家欢"}, {"n": "武侠", "v": "武侠"}, {"n": "玄幻", "v": "玄幻"},
            ]},
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""}, {"n": "内地", "v": "内地"}, {"n": "日本", "v": "日本"},
                {"n": "欧美", "v": "欧美"}, {"n": "其它", "v": "其它"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"},
                {"n": "2016-2011", "v": "2016-2011"}, {"n": "2010-2000", "v": "2010-2000"},
                {"n": "1999-1990", "v": "1999-1990"}, {"n": "1989-1980", "v": "1989-1980"},
            ]},
        ],
        "4": [
            {"key": "class", "name": "剧情", "value": [
                {"n": "全部", "v": ""}, {"n": "表演", "v": "表演"}, {"n": "播报", "v": "播报"},
                {"n": "访谈", "v": "访谈"}, {"n": "体验", "v": "体验"}, {"n": "养成", "v": "养成"},
                {"n": "游戏", "v": "游戏"}, {"n": "亲子", "v": "亲子"}, {"n": "美食", "v": "美食"},
                {"n": "情感", "v": "情感"}, {"n": "选秀", "v": "选秀"}, {"n": "益智", "v": "益智"},
                {"n": "晚会", "v": "晚会"}, {"n": "音乐", "v": "音乐"}, {"n": "文化", "v": "文化"},
                {"n": "喜剧", "v": "喜剧"}, {"n": "曲艺", "v": "曲艺"}, {"n": "职场", "v": "职场"},
                {"n": "脱口秀", "v": "脱口秀"}, {"n": "真人秀", "v": "真人秀"}, {"n": "竞技", "v": "竞技"},
                {"n": "潮流文化", "v": "潮流文化"}, {"n": "体育", "v": "体育"}, {"n": "资讯", "v": "资讯"},
                {"n": "萌宠", "v": "萌宠"}, {"n": "生活服务", "v": "生活服务"},
            ]},
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""}, {"n": "内地", "v": "内地"}, {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"}, {"n": "韩国", "v": "韩国"}, {"n": "美国", "v": "美国"},
                {"n": "日本", "v": "日本"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"},
                {"n": "2016-2011", "v": "2016-2011"}, {"n": "2010-2000", "v": "2010-2000"},
                {"n": "1999-1990", "v": "1999-1990"}, {"n": "1989-1980", "v": "1989-1980"},
            ]},
        ],
    }

    def getName(self):
        return "特狗影视"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.host = self.HOST
        self.ua = 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
        self.header = {
            'User-Agent': self.ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'identity',
            'Referer': self.host + '/',
            'Connection': 'keep-alive',
        }
        # 初始化 SSL context (用于 urllib fallback)
        self._ssl_ctx = None
        try:
            import ssl
            self._ssl_ctx = ssl.create_default_context()
            self._ssl_ctx.check_hostname = False
            self._ssl_ctx.verify_mode = ssl.CERT_NONE
        except Exception:
            pass

    def isVideoFormat(self, url):
        return any(t in url for t in ['.m3u8', '.mp4', '.mkv', '.avi', '.flv', '.ts', '.mov'])

    def manualVideoCheck(self, items):
        return []

    # ========== 请求 ==========

    def _is_valid_html(self, text):
        """检查文本是否是有效 HTML 内容"""
        if not text or not isinstance(text, str):
            return False
        if len(text) < 200:
            return False
        # 必须包含 HTML 标签
        if '<html' not in text.lower() and '<div' not in text.lower() and '<!doctype' not in text.lower():
            return False
        return True

    def _decode_bytes(self, data):
        """安全解码 bytes 为 string"""
        if isinstance(data, str):
            return data
        if isinstance(data, bytes):
            try:
                return data.decode('utf-8', errors='replace')
            except Exception:
                try:
                    return data.decode('gbk', errors='replace')
                except Exception:
                    return ''
        return ''

    def _fetch_text(self, url):
        """请求 URL 并返回文本 - 多重 fallback"""
        # 方法1: self.fetch(url, headers=..., timeout=15)
        try:
            rsp = self.fetch(url, headers=self.header, timeout=15)
            if rsp:
                # 关键: 设置 encoding 防止乱码
                try:
                    rsp.encoding = 'utf-8'
                except Exception:
                    pass
                text = ''
                try:
                    text = self._decode_bytes(rsp.text)
                except Exception:
                    pass
                if not text:
                    try:
                        text = self._decode_bytes(rsp.content)
                    except Exception:
                        pass
                if self._is_valid_html(text):
                    return text
        except Exception as e:
            print('[tegou] fetch1失败: %s' % str(e)[:60])

        # 方法2: self.fetch(url) 不带 headers (兼容旧版 FongMi)
        try:
            rsp = self.fetch(url, timeout=15)
            if rsp:
                try:
                    rsp.encoding = 'utf-8'
                except Exception:
                    pass
                text = ''
                try:
                    text = self._decode_bytes(rsp.text)
                except Exception:
                    pass
                if not text:
                    try:
                        text = self._decode_bytes(rsp.content)
                    except Exception:
                        pass
                if self._is_valid_html(text):
                    return text
        except Exception as e:
            print('[tegou] fetch2失败: %s' % str(e)[:60])

        # 方法3: urllib.request
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=self.header)
            kwargs = {'timeout': 15}
            if self._ssl_ctx:
                kwargs['context'] = self._ssl_ctx
            with urllib.request.urlopen(req, **kwargs) as resp:
                data = resp.read()
                text = self._decode_bytes(data)
                if self._is_valid_html(text):
                    return text
        except Exception as e:
            print('[tegou] urllib失败: %s' % str(e)[:60])

        # 方法4: http.client (最低层)
        try:
            import http.client
            # 解析 URL
            import urllib.parse
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname
            path = parsed.path
            if parsed.query:
                path += '?' + parsed.query

            if parsed.scheme == 'https':
                conn = http.client.HTTPSConnection(host, timeout=15, context=self._ssl_ctx)
            else:
                conn = http.client.HTTPConnection(host, timeout=15)

            conn.request('GET', path, headers=self.header)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
            text = self._decode_bytes(data)
            if self._is_valid_html(text):
                return text
        except Exception as e:
            print('[tegou] http.client失败: %s' % str(e)[:60])

        return ''

    def _url_encode(self, value):
        """手动 URL 编码 (不依赖 urllib)"""
        encoded = ''
        for ch in str(value):
            if ord(ch) > 127:
                for b in ch.encode('utf-8'):
                    encoded += '%%%02X' % b
            elif ch == ' ':
                encoded += '%20'
            elif ch in '!"#$&\'()*+,/:;<>?@[\\]^`{|}~':
                encoded += '%%%02X' % ord(ch)
            else:
                encoded += ch
        return encoded

    # ========== 首页 ==========

    def homeContent(self, filter):
        result = {
            "class": [
                {"type_id": "1", "type_name": "电影"},
                {"type_id": "2", "type_name": "电视剧"},
                {"type_id": "3", "type_name": "动漫"},
                {"type_id": "4", "type_name": "综艺"},
            ],
            "filters": self.FILTERS,
        }

        videos = []
        html = self._fetch_text(self.host + '/')
        if html:
            videos = self._parse_list(html)

        result['list'] = videos[:20]
        return result

    def homeVideoContent(self):
        videos = []
        html = self._fetch_text(self.host + '/')
        if html:
            videos = self._parse_list(html)
        return {"list": videos[:20]}

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        tid = str(tid)
        extend = extend or {}

        # 获取筛选参数
        cls = extend.get('class', '')
        area = extend.get('area', '')
        year = extend.get('year', '')

        # 判断是否有筛选
        has_filter = bool(cls or area or year)

        if has_filter:
            # 使用 vodshow URL
            # 格式: /vodshow/[area/{area}/][class/{class}/]id/{tid}[/year/{year}][/page/{page}].html
            url_parts = [self.host, '/vodshow/']
            if area:
                url_parts.append('area/%s/' % self._url_encode(area))
            if cls:
                url_parts.append('class/%s/' % self._url_encode(cls))
            url_parts.append('id/%s' % tid)
            if year:
                url_parts.append('/year/%s' % self._url_encode(year))
            if page > 1:
                url_parts.append('/page/%d' % page)
            url = ''.join(url_parts) + '.html'
        else:
            # 无筛选, 使用 vodtype URL
            if page > 1:
                url = '%s/vodtype/%s-%d.html' % (self.host, tid, page)
            else:
                url = '%s/vodtype/%s.html' % (self.host, tid)

        html = self._fetch_text(url)

        videos = []
        pagecount = 1

        if html:
            videos = self._parse_list(html)
            # 分页: 检查是否有下一页
            if has_filter:
                # vodshow 分页格式: /vodshow/.../page/{n}.html
                next_page_pattern = r'/vodshow/[^"]*page/%d\.html' % (page + 1)
                if re.search(next_page_pattern, html):
                    pagecount = page + 1
                elif len(videos) >= 10:
                    pagecount = page + 1
            else:
                # vodtype 分页格式: /vodtype/{tid}-{n}.html
                if re.search(r'/vodtype/%s-%d\.html' % (tid, page + 1), html):
                    pagecount = page + 1
                elif len(videos) >= 10:
                    pagecount = page + 1

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 20,
            "total": len(videos) * pagecount,
        }

    # ========== 详情页 ==========

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = str(ids[0])

        # 兼容 vod_id 可能是纯数字或完整路径
        if '/voddetail/' in vod_id:
            # 从路径中提取数字 ID
            id_match = re.search(r'/voddetail/(\d+)', vod_id)
            if id_match:
                vod_id = id_match.group(1)

        vod = {
            "vod_id": vod_id,
            "vod_name": "",
            "vod_pic": "",
            "vod_year": "",
            "vod_area": "",
            "vod_type": "",
            "vod_remarks": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_content": "",
            "vod_play_from": "",
            "vod_play_url": "",
        }

        url = '%s/voddetail/%s.html' % (self.host, vod_id)
        html = self._fetch_text(url)
        if not html:
            return {'list': [vod]}

        # 标题
        title = re.search(r'<h1[^>]*class="title"[^>]*>(.*?)</h1>', html)
        if not title:
            title = re.search(r'<h1[^>]*>(.*?)</h1>', html)
        vod['vod_name'] = title.group(1).strip() if title else ''

        # 图片
        pic = re.search(r'data-original="(.*?)"', html)
        if pic:
            vod['vod_pic'] = pic.group(1)

        # 信息项 (vod-meta 中的 meta-item)
        meta_items = re.findall(r'<span class="meta-item">(.*?)</span>', html)
        for item in meta_items:
            text = re.sub(r'<[^>]+>', '', item).strip()
            if not text:
                continue
            # 主演
            if text.startswith('主演') or text.startswith('主演：'):
                vod['vod_actor'] = text.replace('主演：', '').replace('主演:', '').strip()
            elif text.startswith('导演') or text.startswith('导演：'):
                vod['vod_director'] = text.replace('导演：', '').replace('导演:', '').strip()
            elif text.startswith('更新至') or '完结' in text or text.endswith('集'):
                vod['vod_remarks'] = text
            elif text.startswith('更新') or text.startswith('上映'):
                continue  # 跳过更新/上映日期
            elif re.match(r'^\d{4}$', text):
                vod['vod_year'] = text
            elif text in ['电影', '电视剧', '动漫', '综艺', '动画', '国产剧', '港剧', '美剧', '日剧', '韩剧', '日本', '韩国', '美国', '中国', '中国大陆', '中国香港', '中国台湾', '英国', '法国', '德国', '印度', '其他', '内地', '欧美', '其它']:
                if not vod['vod_area']:
                    vod['vod_area'] = text
                elif not vod['vod_type']:
                    vod['vod_type'] = text
            elif '更新至' in text or '完结' in text or 'HD' in text or '高清' in text or text.endswith('集'):
                vod['vod_remarks'] = text
            else:
                # 其他可能是类型或地区
                if not vod['vod_area']:
                    vod['vod_area'] = text
                elif not vod['vod_type']:
                    vod['vod_type'] = text

        # 简介 (detail-content 有完整简介, detail-sketch 是截断版)
        desc = re.search(r'<span class="detail-content"[^>]*>(.*?)</span>', html, re.DOTALL)
        if not desc:
            desc = re.search(r'<span class="detail-sketch"[^>]*>(.*?)</span>', html, re.DOTALL)
        if desc:
            vod['vod_content'] = re.sub(r'<[^>]+>', '', desc.group(1)).strip()

        # 播放源和集数
        play_from_parts = []
        play_url_parts = []

        # 提取播放源 tabs (nav nav-tabs)
        tab_sources = re.findall(r'<a[^>]*href="#(playlist\d+)"[^>]*data-toggle="tab"[^>]*>(.*?)</a>', html, re.DOTALL)

        # 提取每个播放源的集数列表
        for tab in tab_sources:
            tab_id = tab[0]
            tab_name = re.sub(r'<[^>]+>', '', tab[1]).strip()

            # 找到对应的 tab-pane
            pane_pattern = r'id="%s"[^>]*>(.*?)</div>\s*</div>' % tab_id
            pane = re.search(pane_pattern, html, re.DOTALL)
            if not pane:
                pane = re.search(r'id="%s"[^>]*>(.*?)</div>' % tab_id, html, re.DOTALL)

            if pane:
                pane_html = pane.group(1)
                # 提取集数链接
                ep_links = re.findall(r'<a[^>]*href="(/vodplay/[^"]*)"[^>]*>(.*?)</a>', pane_html, re.DOTALL)
                ep_list = []
                for ep in ep_links:
                    ep_text = re.sub(r'<[^>]+>', '', ep[1]).strip()
                    if not ep_text or ep_text == '立即播放':
                        continue
                    ep_list.append('%s$%s' % (ep_text, ep[0]))

                if ep_list:
                    play_from_parts.append(tab_name if tab_name else '播放')
                    play_url_parts.append('#'.join(ep_list))

        # 如果没有 tabs, 尝试直接找 stui-content__playlist
        if not play_from_parts:
            playlists = re.findall(r'<ul[^>]*class="[^"]*stui-content__playlist[^"]*"[^>]*>(.*?)</ul>', html, re.DOTALL)
            for pl in playlists:
                ep_links = re.findall(r'<a[^>]*href="(/vodplay/[^"]*)"[^>]*>(.*?)</a>', pl, re.DOTALL)
                ep_list = []
                for ep in ep_links:
                    ep_text = re.sub(r'<[^>]+>', '', ep[1]).strip()
                    if not ep_text or ep_text == '立即播放':
                        continue
                    ep_list.append('%s$%s' % (ep_text, ep[0]))
                if ep_list:
                    play_from_parts.append('高清C')
                    play_url_parts.append('#'.join(ep_list))

        if play_from_parts:
            vod['vod_play_from'] = '$$$'.join(play_from_parts)
            vod['vod_play_url'] = '$$$'.join(play_url_parts)

        return {'list': [vod]}

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        wd = self._url_encode(key)

        url = '%s/index.php?searchword=%s' % (self.host, wd)
        if page > 1:
            url = '%s/vodsearch/page/%d/wd/%s.html' % (self.host, page, wd)

        html = self._fetch_text(url)
        if not html:
            return {'list': [], 'page': page}

        return {'list': self._parse_list(html), 'page': page}

    # ========== 播放 ==========

    def playerContent(self, flag, id, vipFlags):
        # id 是 /vodplay/5336-1-1.html 格式
        play_url = id
        if not play_url.startswith('http'):
            play_url = self.host + play_url

        # 1. 获取播放页, 提取 player_aaaa
        html = self._fetch_text(play_url)
        if not html:
            return {"parse": 1, "url": play_url, "header": ''}

        player_match = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.DOTALL)
        if not player_match:
            return {"parse": 1, "url": play_url, "header": ''}

        try:
            player = json.loads(player_match.group(1))
        except Exception:
            return {"parse": 1, "url": play_url, "header": ''}

        play_id = player.get('url', '')
        play_from = player.get('from', '')
        encrypt = player.get('encrypt', 0)

        # 解密 URL (encrypt=0 不需要解密, 1=unescape, 2=base64)
        if encrypt == 1:
            try:
                import urllib.parse
                play_id = urllib.parse.unquote(play_id)
            except Exception:
                pass
        elif encrypt == 2:
            try:
                import base64
                play_id = base64.b64decode(play_id).decode('utf-8')
            except Exception:
                pass

        # 2. 构造解析 URL
        # link 播放器: parse="/vid/vr2/vr2.php?url="
        parse_url = self.host + '/vid/vr2/vr2.php?url=' + play_id

        # 3. 请求解析页, 提取 m3u8 直链
        parse_html = self._fetch_text(parse_url)
        if parse_html:
            # 提取 m3u8 URL
            m3u8_match = re.search(r'(https?://[^"\'>\s]+\.m3u8[^"\'>\s]*)', parse_html)
            if m3u8_match:
                m3u8_url = m3u8_match.group(1)
                return {
                    "parse": 0,
                    "url": m3u8_url,
                    "header": json.dumps({
                        "User-Agent": self.ua,
                        "Referer": self.host + '/',
                    }),
                }

            # 提取 mp4 URL
            mp4_match = re.search(r'(https?://[^"\'>\s]+\.mp4[^"\'>\s]*)', parse_html)
            if mp4_match:
                return {
                    "parse": 0,
                    "url": mp4_match.group(1),
                    "header": json.dumps({
                        "User-Agent": self.ua,
                        "Referer": self.host + '/',
                    }),
                }

        # 4. 解析失败, 返回嗅探
        return {
            "parse": 1,
            "url": parse_url,
            "header": json.dumps({
                "User-Agent": self.ua,
                "Referer": self.host + '/',
            }),
        }

    # ========== 辅助方法 ==========

    def _parse_list(self, html):
        """解析列表页 (分类/搜索/首页), 提取视频卡片"""
        videos = []
        seen_ids = set()

        # stui-vodlist__box 结构
        items = re.findall(r'<div class="stui-vodlist__box">(.*?)</div>\s*<div class="stui-vodlist__detail">', html, re.DOTALL)
        if not items:
            # 备用: 直接找 voddetail 链接块
            items = re.findall(r'<a[^>]*class="stui-vodlist__thumb[^"]*"[^>]*href="(/voddetail/\d+[^"]*)"[^>]*title="([^"]*)"[^>]*data-original="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL)

        for item in items:
            remark = ''
            if isinstance(item, tuple):
                # 备用模式直接匹配: (href, title, pic, inner_html)
                full_path = item[0]
                title = item[1]
                pic = item[2]
                remark = re.sub(r'<[^>]+>', '', item[3]).strip()
            else:
                # stui-vodlist__box 模式
                link = re.search(r'href="(/voddetail/(\d+)[^"]*)"', item)
                if not link:
                    continue
                full_path = link.group(1)
                title_match = re.search(r'title="([^"]*)"', item)
                title = title_match.group(1) if title_match else ''
                pic_match = re.search(r'data-original="([^"]*)"', item)
                pic = pic_match.group(1) if pic_match else ''
                remark_match = re.search(r'class="[^"]*pic-text[^"]*"[^>]*>(.*?)<', item)
                remark = re.sub(r'<[^>]+>', '', remark_match.group(1)).strip() if remark_match else ''

            # 提取纯数字 ID 作为 vod_id (详情页用)
            id_match = re.search(r'/voddetail/(\d+)', full_path)
            if not id_match:
                continue
            vod_id = id_match.group(1)

            # 去重
            if vod_id in seen_ids:
                continue
            seen_ids.add(vod_id)

            videos.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark,
            })

        return videos

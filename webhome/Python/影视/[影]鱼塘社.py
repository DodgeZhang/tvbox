# -*- coding: utf-8 -*-
"""
鱼塘社 (https://tv.yutangshe.com)
适配 TVBox / 影视仓 / OK影视 等空壳影视 APP 的 Python 源

站点模板: 苹果CMS (MacCMS) + shortcut55 模板
接口覆盖: 分类 / 类型筛选 / 分页 / 详情 / 播放 / 搜索 / 封面
"""

import re
import sys
import json
import time
import random
import urllib.parse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def fetch(self, url, headers=None, timeout=20, verify=False, cookies=None):
            s = requests.Session()
            s.trust_env = False
            return s.get(url, headers=headers, timeout=timeout, verify=verify, cookies=cookies)

        def post(self, url, headers=None, data=None, timeout=20, verify=False, cookies=None):
            s = requests.Session()
            s.trust_env = False
            return s.post(url, headers=headers, data=data, timeout=timeout, verify=verify, cookies=cookies)


class Spider(BaseSpider):
    name = '鱼塘社'
    host = 'https://tv.yutangshe.com'

    # ==================================================================
    # 一、分类定义
    # ==================================================================
    # 父分类 + 子分类（站点的"类型"筛选即切换这些子分类 type_id）
    CATEGORIES = [
        ('20', '电影'),
        ('21', '电视剧'),
        ('22', '综艺'),
        ('23', '动漫'),
        ('24', '动作片'),
        ('25', '喜剧片'),
        ('26', '科幻片'),
        ('27', '恐怖片'),
        ('28', '爱情片'),
        ('29', '剧情片'),
        ('30', '战争片'),
        ('31', '记录片'),
        ('32', '动画片'),
    ]

    # ==================================================================
    # 二、筛选器
    #     由于站点筛选页被站长关闭（/vodshow/ 返回"筛选页功能关闭中"），
    #     唯一可用的筛选维度是「类型」切换（即子分类切换）。
    #     因此只提供类型筛选，不展示地区/年份/语言等假筛选项。
    # ==================================================================
    # 类型筛选值：所有子分类
    TYPE_FILTERS = [
        {'n': '全部', 'v': ''},
        {'n': '动作片', 'v': '24'},
        {'n': '喜剧片', 'v': '25'},
        {'n': '科幻片', 'v': '26'},
        {'n': '恐怖片', 'v': '27'},
        {'n': '爱情片', 'v': '28'},
        {'n': '剧情片', 'v': '29'},
        {'n': '战争片', 'v': '30'},
        {'n': '记录片', 'v': '31'},
        {'n': '动画片', 'v': '32'},
    ]

    FILTERS = {
        '20': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '21': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '22': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '23': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '24': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '25': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '26': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '27': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '28': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '29': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '30': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '31': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
        '32': [{'key': 'cate', 'name': '类型', 'value': TYPE_FILTERS}],
    }

    VIDEO_EXT = ('.m3u8', '.mp4', '.flv', '.mkv', '.avi', '.ts', '.m3u', '.mpd')

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self._debug = True

    # ==================================================================
    # 三、TVBox 基础接口
    # ==================================================================

    def getName(self):
        return self.name

    def init(self, extend=''):
        self._log(f'初始化完成: {self.host}')
        return {}

    def isVideoFormat(self, url):
        if not url:
            return False
        u = str(url).split('?')[0].lower()
        return u.endswith(self.VIDEO_EXT)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def _log(self, msg):
        if self._debug:
            print(f'[{self.name}] {msg}')

    # ==================================================================
    # 四、请求工具
    # ==================================================================

    def _headers(self, referer=None):
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
            'Referer': referer or self.host + '/',
        }

    def _fetch(self, url, referer=None, retries=3, timeout=15):
        """带重试的页面抓取，返回 html 文本"""
        for i in range(retries):
            try:
                if i > 0:
                    time.sleep(random.uniform(0.5, 1.0))
                r = self.fetch(url, headers=self._headers(referer), timeout=timeout, verify=False)
                if getattr(r, 'status_code', 0) == 200:
                    content = r.text or ''
                    if len(content) > 200:
                        return content
                    self._log(f'内容过短 ({len(content)}): {url}')
                else:
                    self._log(f'HTTP {r.status_code}: {url}')
            except Exception as e:
                self._log(f'请求异常 [{url}]: {e} (重试 {i + 1}/{retries})')
            if i < retries - 1:
                time.sleep(0.5)
        return ''

    def _fetch_list(self, url, retries=3):
        """列表页抓取"""
        return self._fetch(url, retries=retries)

    # ==================================================================
    # 五、通用小工具
    # ==================================================================

    def _fix(self, url):
        if not url:
            return ''
        url = url.strip()
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.host + url
        if not url.startswith('http'):
            return urllib.parse.urljoin(self.host + '/', url)
        return url

    @staticmethod
    def _txt(s):
        if not s:
            return ''
        s = re.sub(r'<[^>]+>', ' ', str(s))
        s = s.replace('\xa0', ' ').replace('&nbsp;', ' ')
        return re.sub(r'\s+', ' ', s).strip()

    @staticmethod
    def _pic(node):
        """懒加载封面: data-original > data-src > src，过滤占位图"""
        if node is None:
            return ''
        for attr in ('data-original', 'data-src', 'data-lazy', 'src'):
            v = (node.get(attr) or '').strip()
            if v and 'load.svg' not in v and 'loading' not in v and not v.startswith('data:'):
                return v
        return ''

    # ==================================================================
    # 六、列表解析
    # ==================================================================

    def _parse_list(self, html):
        """
        解析列表页卡片
        卡片结构: <a class="vcard" href="/voddetail/{id}.html">
          海报: img.lazyload[data-original]
          标题: .vcard 下第一个 <p class="...truncate">
          备注: 海报右下角 div（如 HD国语）
        """
        items, seen = [], set()
        if not html:
            return items
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.select('a.vcard'):
            try:
                href = a.get('href') or ''
                m = re.search(r'/voddetail/(\d+)\.html', href)
                if not m:
                    continue
                vid = m.group(1)
                if vid in seen:
                    continue
                seen.add(vid)

                # 海报
                img = a.find('img')
                pic = self._pic(img) if img else ''
                if pic and not pic.startswith('http'):
                    if 'load.svg' not in pic.lower() and 'loading' not in pic.lower():
                        pic = self._fix(pic)
                    else:
                        pic = ''

                # 标题：第一个带 font-bold/truncate 的 p
                name = ''
                for p in a.find_all('p'):
                    cls = ' '.join(p.get('class', [])) if p.get('class') else ''
                    txt = self._txt(p.get_text())
                    if not txt:
                        continue
                    if 'font-bold' in cls or ('truncate' in cls and 'gray' not in cls):
                        name = txt
                        break
                if not name and img:
                    name = self._txt(img.get('alt', ''))
                name = re.sub(r'^《|》$', '', name).strip()
                if not name:
                    continue

                # 备注：右下角 div
                remarks = ''
                for div in a.find_all('div'):
                    cls = ' '.join(div.get('class', [])) if div.get('class') else ''
                    txt = self._txt(div.get_text())
                    if not txt:
                        continue
                    if 'bottom' in cls and 'right' in cls and len(txt) < 12:
                        remarks = txt
                        break
                if not remarks:
                    text = a.get_text()
                    m2 = re.search(r'(HD国语|HD粤语|HD|BD|DVD|抢先版|正片|预告|TS|TC|蓝光|超清|高清|4K|更新至\d+|\d+集全)', text)
                    if m2:
                        remarks = m2.group(1)

                items.append({
                    'vod_id': vid,
                    'vod_name': name[:200],
                    'vod_pic': pic,
                    'vod_remarks': remarks[:60],
                })
            except Exception as e:
                self._log(f'解析卡片异常: {e}')
                continue
        return items

    def _pagecount(self, html, page):
        """分页：实测 <a class="page-btn" href="/vodtype/{tid}-{page}.html">"""
        page = int(page or 1)
        if not html:
            return page

        max_page = 0
        has_next = False
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.select('a.page-btn, .pagination a, a[href*="/vodtype/"]'):
            href = a.get('href') or ''
            text = a.get_text(strip=True)
            if re.search(r'下一页|»|next', text, re.I):
                has_next = True
            m = re.search(r'/vodtype/\d+-(\d+)\.html', href)
            if m:
                p = int(m.group(1))
                if p > max_page and p < 9999:
                    max_page = p

        # 当前页 active
        for a in soup.select('a.page-btn.active'):
            p = int(a.get_text(strip=True))
            if p > max_page:
                max_page = p

        if has_next:
            return max_page + 1
        return max(1, max_page)

    # ==================================================================
    # 七、首页
    # ==================================================================

    def homeContent(self, filter=True):
        classes = [{'type_id': t, 'type_name': n} for t, n in self.CATEGORIES]
        result = {
            'class': classes,
            'filters': self.FILTERS,
            'parse': 0,
            'jx': 0,
        }
        try:
            html = self._fetch(self.host + '/')
            result['list'] = self._parse_list(html)[:30]
        except Exception as e:
            self._log(f'homeContent 异常: {e}')
            result['list'] = []
        return result

    def homeVideoContent(self):
        try:
            html = self._fetch(self.host + '/')
            return {'list': self._parse_list(html)[:30], 'parse': 0, 'jx': 0}
        except Exception as e:
            self._log(f'homeVideoContent 异常: {e}')
            return {'list': [], 'parse': 0, 'jx': 0}

    # ==================================================================
    # 八、分类内容（含类型筛选 + 分页）
    # ==================================================================

    def categoryContent(self, tid, pg, filter=True, extend=None):
        page = int(pg) if pg else 1
        try:
            # 类型筛选：若用户选了某个子分类 type_id，则切换到该 type_id
            # 否则用当前 tid
            extend = extend or {}
            use_tid = extend.get('cate') if extend.get('cate') else tid

            if page > 1:
                url = f'{self.host}/vodtype/{use_tid}-{page}.html'
            else:
                url = f'{self.host}/vodtype/{use_tid}.html'

            html = self._fetch_list(url)
            items = self._parse_list(html)
            pc = self._pagecount(html, page)

            return {
                'list': items,
                'page': page,
                'pagecount': pc,
                'limit': len(items) or 12,
                'total': pc * (len(items) or 12),
                'parse': 0,
                'jx': 0,
            }
        except Exception as e:
            self._log(f'categoryContent 异常: {e}')
            return {'list': [], 'page': page, 'pagecount': page,
                    'limit': 12, 'total': 0, 'parse': 0, 'jx': 0}

    # ==================================================================
    # 九、详情内容（多线路 + 剧集）
    # ==================================================================

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
        vid = re.sub(r'\D', '', vid) or vid
        url = f'{self.host}/voddetail/{vid}.html'
        try:
            html = self._fetch(url, referer=self.host + '/')
            if not html:
                return self._empty_detail(vid)
            return {'list': [self._parse_detail(vid, html)], 'parse': 0, 'jx': 0}
        except Exception as e:
            self._log(f'detailContent 异常: {e}')
            return self._empty_detail(vid)

    def _empty_detail(self, vid):
        return {'list': [{
            'vod_id': vid, 'vod_name': '获取失败', 'vod_pic': '',
            'vod_play_from': '默认', 'vod_play_url': '',
        }], 'parse': 0, 'jx': 0}

    def _parse_detail(self, vid, html):
        soup = BeautifulSoup(html, 'html.parser')

        # --- 标题 ---
        vod_name = ''
        h1 = soup.find('h1')
        if h1:
            vod_name = self._txt(h1.get_text())
        if not vod_name:
            m = re.search(r'<title>([^<]+)', html)
            if m:
                vod_name = re.sub(r'[-_–—《》].*$', '', m.group(1))
                vod_name = re.sub(r'^《|》$', '', vod_name).strip()
        vod_name = re.sub(r'^《|》$', '', vod_name).strip()

        # --- 封面 ---
        pic = ''
        img = soup.select_one('.detail-pic img, .voddetail img, img.lazyload')
        if img:
            pic = self._pic(img)
            if pic and not pic.startswith('http'):
                if 'load.svg' not in pic.lower() and 'loading' not in pic.lower():
                    pic = self._fix(pic)
                else:
                    pic = ''

        # --- 元数据 ---
        vod_director = ''
        vod_actor = ''
        vod_remarks = ''
        vod_content = ''
        vod_class = ''

        for span in soup.select('span.text-gray-400, span.text-gray-500'):
            label = re.sub(r'[：:]', '', span.get_text(strip=True))
            parent = span.parent
            raw = parent.get_text(strip=True)
            value = re.sub(r'^[·\s]+', '', raw.replace(span.get_text(), '').split('·')[0].strip())

            if '导演' in label:
                vod_director = value
            elif '主演' in label:
                vod_actor = value
            elif '更新' in label or '状态' in label or '备注' in label:
                vod_remarks = value

        # --- 简介 ---
        meta_desc = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
        if meta_desc:
            vod_content = re.sub(r'<[^>]+>', '', meta_desc.group(1))
            vod_content = re.sub(r'&nbsp;', ' ', vod_content)
            vod_content = re.sub(r'^[^：]+：', '', vod_content).strip()[:500]

        # --- 类型 ---
        meta_key = re.search(r'<meta\s+name="keywords"\s+content="([^"]+)"', html)
        if meta_key:
            km = re.search(r'电影([^\s,，]+)', meta_key.group(1)) or \
                 re.search(r'电视剧([^\s,，]+)', meta_key.group(1))
            if km:
                vod_class = re.sub(r'片$', '', km.group(1))

        # --- 播放线路 + 选集 ---
        # 线路名：<button class="tab-btn" data-sid="{sid}">线路名</button>
        # 选集：<a class="ep-item" data-nid="{nid}" href="/vodplay/{vodId}-{sid}-{nid}.html">集名</a>
        # 注意：排除"立即播放"大按钮（无 data-nid）
        line_names = {}
        line_map = {}
        line_order = []

        for btn in soup.select('button.tab-btn'):
            sid = btn.get('data-sid')
            name = btn.get_text(strip=True)
            if sid and name:
                line_names[sid] = name

        for a in soup.select('a.ep-item'):
            nid = a.get('data-nid')
            if not nid:
                continue
            href = a.get('href') or ''
            m = re.search(r'/vodplay/\d+-(\d+)-(\d+)\.html', href)
            if not m:
                continue
            sid = m.group(1)
            ep_name = a.get_text(strip=True)
            if not ep_name or re.search(r'立即播放|播放', ep_name):
                continue
            if sid not in line_map:
                line_map[sid] = []
                line_order.append(sid)
            line_map[sid].append({
                'ep_name': ep_name,
                'href': href,
                'nid': int(nid)
            })

        froms, urls = [], []
        for idx, sid in enumerate(line_order):
            name = line_names.get(sid, f'线路{idx + 1}')
            eps = line_map.get(sid, [])
            if not eps:
                continue
            # 按 nid 升序排序并去重
            eps.sort(key=lambda x: x['nid'])
            seen_nid = set()
            ep_list = []
            for e in eps:
                if e['nid'] in seen_nid:
                    continue
                seen_nid.add(e['nid'])
                ep_list.append(f"{e['ep_name']}${e['href']}")
            if not ep_list:
                continue
            froms.append(name)
            urls.append('#'.join(ep_list))

        if not froms:
            froms, urls = ['默认'], [f'正片${vid}-1-1']

        return {
            'vod_id': vid,
            'vod_name': vod_name,
            'vod_pic': self._fix(pic),
            'vod_type': vod_class,
            'vod_remarks': vod_remarks,
            'vod_actor': vod_actor,
            'vod_director': vod_director,
            'vod_content': vod_content,
            'vod_play_from': '$$$'.join(froms),
            'vod_play_url': '$$$'.join(urls),
        }

    # ==================================================================
    # 十、播放解析
    # ==================================================================

    def playerContent(self, flag, id, vipFlags=None):
        pid = str(id or '').strip()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': self.host + '/',
        }

        try:
            # 直链 m3u8/mp4 直接放行
            if pid.startswith('http') and self.isVideoFormat(pid):
                return self._play(pid, headers, parse=0)

            # 播放页 URL：/vodplay/{vodId}-{sid}-{nid}.html
            if not pid.startswith('http'):
                if '/vodplay/' in pid:
                    play_page = self._fix(pid)
                else:
                    play_page = f'{self.host}/vodplay/{pid}.html'
            else:
                play_page = pid

            html = self._fetch(play_page, referer=self.host + '/')

            # 1. 解析 player_aaaa（实测本站 encrypt=0，url 为直链 m3u8）
            play_link = ''
            m = re.search(r'player_aaaa\s*=\s*(\{[\s\S]*?\})\s*[;<\n]', html)
            if m:
                try:
                    cfg = json.loads(m.group(1))
                    u = cfg.get('url', '')
                    enc = int(cfg.get('encrypt', 0))
                    if enc == 0:
                        play_link = u
                    elif enc == 1:
                        play_link = urllib.parse.unquote(u)
                    elif enc == 2:
                        try:
                            play_link = urllib.parse.unquote(u)
                        except:
                            play_link = u
                except:
                    pass

            # 2. 正则匹配 m3u8/mp4 直链
            if not play_link:
                m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
                if m:
                    play_link = m.group(1)
            if not play_link:
                m = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html)
                if m:
                    play_link = m.group(1)

            # 3. 从 "url":"xxx" 提取
            if not play_link:
                m = re.search(r'["\']url["\']\s*:\s*["\']([^"\']+)["\']', html)
                if m:
                    u = m.group(1).replace(r'\/', '/')
                    try:
                        play_link = urllib.parse.unquote(u)
                    except:
                        play_link = u

            if play_link and play_link.startswith('http'):
                return self._play(play_link, headers, parse=0)

            # 4. 兜底：交给播放器嗅探
            return self._play('', headers, parse=1, play_url=play_page)

        except Exception as e:
            self._log(f'playerContent 异常: {e}')
            return self._play('', headers, parse=1, play_url=pid)

    @staticmethod
    def _play(url, headers, parse=0, play_url=''):
        return {
            'parse': parse,
            'playUrl': '',
            'url': url or play_url,
            'header': json.dumps(headers),
            'jx': 0,
            'contentType': 'application/vnd.apple.mpegurl' if str(url).find('.m3u8') > 0 else '',
        }

    # ==================================================================
    # 十一、搜索
    # ==================================================================

    def searchContent(self, key, quick=False, pg='1'):
        key = key.strip()
        page = int(pg) if pg else 1
        result = {'list': [], 'page': page, 'pagecount': 0,
                  'limit': 12, 'total': 0, 'parse': 0, 'jx': 0}

        if not key:
            return result

        try:
            # macCMS 搜索 URL：/vodsearch/{wd}-------------.html（13 段）
            if page > 1:
                url = f"{self.host}/vodsearch/{urllib.parse.quote(key)}-------------{page}-.html"
            else:
                url = f"{self.host}/vodsearch/{urllib.parse.quote(key)}-------------.html"

            html = self._fetch(url, retries=3)
            items = self._parse_list(html)

            # 搜索分页
            soup = BeautifulSoup(html, 'html.parser') if html else None
            max_page = 0
            has_next = False
            if soup:
                for a in soup.find_all('a'):
                    href = a.get('href', '')
                    text = a.get_text(strip=True)
                    if re.search(r'下一页|»|next', text, re.I):
                        has_next = True
                    m = re.search(r'/vodsearch/[^?]*-+(\d+)-?\.html$', href)
                    if m:
                        p = int(m.group(1))
                        if p > max_page and p < 9999:
                            max_page = p

            pc = self._pagecount(html, page)
            if has_next:
                pc = max(pc, max_page + 1)

            result['list'] = items
            result['pagecount'] = pc
            result['total'] = pc * len(items) if items else 0
        except Exception as e:
            self._log(f'searchContent 异常: {e}')

        return result

    def searchContentPage(self, key, quick=False, pg='1'):
        return self.searchContent(key, quick, pg)

    # ==================================================================
    # 十二、本地代理（封面回源）
    # ==================================================================

    def localProxy(self, param):
        try:
            if isinstance(param, dict):
                url = param.get('url') or ''
            else:
                url = str(param or '')
            if not url.startswith('http'):
                return None
            r = self.fetch(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': self.host + '/',
            }, timeout=20, verify=False)
            ct = r.headers.get('Content-Type', 'application/octet-stream')
            return [200, ct, r.content]
        except Exception:
            return None


# ======================================================================
# 本地自测
# ======================================================================
if __name__ == '__main__':
    sp = Spider()
    sp.init()

    print('\n================ 1. 首页 / 分类 / 筛选器 ================')
    home = sp.homeContent(True)
    print(f"分类 {len(home['class'])} 个: " + ', '.join(f"{c['type_name']}({c['type_id']})" for c in home['class']))
    print(f"首页推荐 {len(home['list'])} 条")
    for v in home['list'][:5]:
        print(f"   {v['vod_name'][:26]:<28} id={v['vod_id']:<8} 备注={v['vod_remarks'][:12]:<14} 封面={'OK' if v['vod_pic'].startswith('http') else '缺失'}")

    print('\n================ 2. 分类 + 分页 ================')
    for tid, pg in [('20', 1), ('20', 2), ('21', 1), ('22', 1), ('23', 1)]:
        r = sp.categoryContent(tid, pg, True, {})
        tn = dict(sp.CATEGORIES).get(tid, tid)
        first = r['list'][0]['vod_name'][:20] if r['list'] else '-'
        print(f"   {tn}({tid}) 第{pg}页: {len(r['list']):>2} 条 / 共 {r['pagecount']} 页  首条={first}")

    print('\n================ 3. 类型筛选（子分类切换） ================')
    for tid in ['20', '24', '25', '26']:
        r = sp.categoryContent('20', 1, True, {'cate': tid})
        tn = dict(sp.CATEGORIES).get(tid, tid)
        first = r['list'][0]['vod_name'][:18] if r['list'] else '-'
        print(f"   筛选 {tn}({tid}): {len(r['list']):>2} 条 / {r['pagecount']} 页  首条={first}")

    print('\n================ 4. 详情 ================')
    target = home['list'][0] if home['list'] else None
    det = None
    if target:
        det = sp.detailContent([target['vod_id']])['list'][0]
        print(f"   名称: {det['vod_name']}")
        print(f"   封面: {det['vod_pic'][:80]}")
        print(f"   类型: {det.get('vod_type', '')}")
        print(f"   状态: {det.get('vod_remarks', '')}")
        print(f"   导演: {det.get('vod_director', '')[:40]}")
        print(f"   主演: {det.get('vod_actor', '')[:60]}")
        print(f"   简介: {det.get('vod_content', '')[:70]}...")
        fl = det['vod_play_from'].split('$$$')
        ul = det['vod_play_url'].split('$$$')
        print(f"   线路 {len(fl)} 条:")
        for f, u in zip(fl, ul):
            eps = u.split('#')
            print(f"      {f}: {len(eps)} 集  -> {eps[0][:40]}")

    print('\n================ 5. 播放解析 ================')
    if det:
        fl = det['vod_play_from'].split('$$$')
        ul = det['vod_play_url'].split('$$$')
        for f, u in zip(fl, ul):
            first_ep = u.split('#')[0]
            pid = first_ep.split('$')[-1]
            p = sp.playerContent(f, pid)
            print(f"   [{f}] parse={p['parse']}  url={p['url'][:100]}")

    print('\n================ 6. 搜索 ================')
    for kw in ['斗罗大陆', '庆余年', '哪吒']:
        r = sp.searchContent(kw, False, '1')
        first = r['list'][0]['vod_name'][:24] if r['list'] else '-'
        print(f"   搜索[{kw}]: {len(r['list'])} 条 / {r['pagecount']} 页  首条={first}")

    print('\n完成。')
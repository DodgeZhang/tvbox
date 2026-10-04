# -*- coding: utf-8 -*-
"""
瓜子漫画 (www.guazimanhua.com) - TVBox Python 爬虫源
=================================================
版本: v3-sort-fix
修复: 章节正序 + 异常捕获 + 懒加载图片 + Referer 403 + JSON-LD @graph
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request

try:
    import gzip
except Exception:
    gzip = None

try:
    import requests
    from requests.adapters import HTTPAdapter
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False

sys.path.append('..')
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def fetch(self, url, headers=None, timeout=20, verify=False, cookies=None):
            raw, _ct = _http_get(url, headers or {}, timeout)
            return raw
        def html(self, url, headers=None):
            raw, _ct = _http_get(url, headers or {}, 20)
            return raw.decode('utf-8', 'ignore')


def _http_get(url, headers, timeout=15):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if gzip:
            ce = resp.headers.get('Content-Encoding', '')
            if 'gzip' in ce:
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
        return raw


class Spider(BaseSpider):
    name = '瓜子漫画'
    VERSION = 'v3-sort-fix'

    SITES = ['https://www.guazimanhua.com']

    CATEGORIES = [
        ('', '全部'),
        ('41', '耽美'), ('9', '恋爱'), ('29', '校园'), ('5', '霸总'),
        ('42', '都市'), ('8', '穿越'), ('23', '古风'), ('25', '玄幻'),
        ('31', '奇幻'), ('22', '科幻'), ('21', '灵异'), ('54', '动作'),
        ('11', '悬疑'), ('30', '冒险'), ('15', '搞笑'), ('13', '热血'),
        ('14', '恐怖'), ('148', '系统'), ('97', '逆袭'), ('55', '脑洞'),
        ('61', '复仇'), ('17', '真人'), ('27', '其它'),
    ]

    FILTERS = {
        "": [
            {"key": "city", "name": "地区", "value": [
                {"n": "全部", "v": ""}, {"n": "国漫", "v": "338"}, {"n": "日韩", "v": "78"},
                {"n": "大陆", "v": "42"}, {"n": "欧美", "v": "43"}, {"n": "港台", "v": "77"},
            ]},
            {"key": "audience", "name": "受众", "value": [
                {"n": "全部", "v": ""}, {"n": "男频", "v": "1"}, {"n": "女频", "v": "2"},
            ]},
            {"key": "is_end", "name": "状态", "value": [
                {"n": "全部", "v": ""}, {"n": "完结", "v": "1"}, {"n": "连载", "v": "2"},
            ]},
            {"key": "sort", "name": "排序", "value": [
                {"n": "最新", "v": "update"}, {"n": "人气", "v": "hits"},
                {"n": "今日热门", "v": "daily"}, {"n": "评分", "v": "score"},
            ]},
        ],
    }

    _home_cache = None
    _home_cache_ts = 0
    _search_ts = 0
    HOME_CACHE_TTL = 1800

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self._current_idx = 0
        self.session = None
        self.headers = {}
        self.base_url = 'https://www.guazimanhua.com'

    def init(self, extend=""):
        if HAS_REQUESTS:
            try:
                s = requests.Session()
                s.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                    'Connection': 'keep-alive',
                })
                adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0)
                s.mount('https://', adapter)
                s.mount('http://', adapter)
                s.verify = False
                try:
                    import urllib3
                    urllib3.disable_warnings()
                except Exception:
                    pass
                self.session = s
            except Exception:
                self.session = None
        else:
            self.session = None

        if extend:
            u = str(extend).strip()
            if u.startswith('http'):
                self.base_url = u.rstrip('/')
                self.SITES.insert(0, self.base_url)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Referer': self.base_url + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        return {}

    def destroy(self):
        if self.session and hasattr(self.session, 'close'):
            self.session.close()

    def getName(self):
        return self.name

    def _host(self):
        return self.SITES[self._current_idx % len(self.SITES)]

    def _fetch(self, url, referer=None, timeout=10):
        hdr = dict(self.headers)
        if referer:
            hdr['Referer'] = referer
        for attempt in range(2):
            try:
                if self.session:
                    r = self.session.get(url, headers=hdr, timeout=timeout, allow_redirects=True)
                    r.raise_for_status()
                    return r.text
                else:
                    raw = _http_get(url, hdr, timeout)
                    return raw.decode('utf-8', 'ignore')
            except Exception:
                if len(self.SITES) > 1:
                    old_host = self._host()
                    self._current_idx += 1
                    url = url.replace(old_host, self._host())
        return ''

    @staticmethod
    def _clean(s):
        if not s:
            return ''
        s = re.sub(r'<[^>]+>', ' ', str(s))
        s = s.replace('\xa0', ' ').replace('&nbsp;', ' ')
        try:
            import html as _html
            s = _html.unescape(s)
        except Exception:
            pass
        return re.sub(r'\s+', ' ', s).strip()

    def _parse_list(self, html):
        items = []
        if not html:
            return items
        host = self._host()
        for box in re.finditer(r'<article class="card">(.*?)</article>', html, re.S):
            block = box.group(1)
            m = re.search(r'href="(/comic\.php\?id=(\d+))"', block)
            if not m:
                continue
            vid = m.group(2)
            m = re.search(r'<img class="cover"[^>]*src="([^"]+)"', block)
            pic = m.group(1) if m else ''
            m = re.search(r'<h3><a[^>]*>([^<]+)</a></h3>', block)
            title = m.group(1).strip() if m else ''
            remarks = ''
            m = re.search(r'<span class="genre">([^<]*)</span>', block)
            if m:
                remarks = m.group(1).strip()
            m = re.search(r'<span class="score">([^<]*)</span>', block)
            if m:
                remarks = (remarks + ' ' + m.group(1).strip()).strip() if remarks else m.group(1).strip()
            items.append({
                'vod_id': vid,
                'vod_name': title[:200],
                'vod_pic': pic if pic.startswith('http') else host + pic if pic.startswith('/') else host + '/' + pic,
                'vod_remarks': remarks[:60],
            })
        return items

    def homeContent(self, filter=True):
        now = time.time()
        if Spider._home_cache and (now - Spider._home_cache_ts) < Spider.HOME_CACHE_TTL:
            return Spider._home_cache
        html = self._fetch(self._host() + '/category.php', timeout=10)
        result = {
            'class': [{'type_id': tid, 'type_name': name} for tid, name in self.CATEGORIES],
            'filters': self.FILTERS,
            'list': self._parse_list(html) if html else [],
            'page': 1,
            'pagecount': 9999,
            'limit': 36,
            'total': 9999 * 36,
        }
        Spider._home_cache = result
        Spider._home_cache_ts = now
        return result

    def homeVideoContent(self):
        now = time.time()
        if Spider._home_cache and (now - Spider._home_cache_ts) < Spider.HOME_CACHE_TTL:
            return Spider._home_cache
        html = self._fetch(self._host() + '/category.php', timeout=10)
        return {
            'list': self._parse_list(html) if html else [],
            'page': 1,
            'pagecount': 9999,
            'limit': 36,
            'total': 9999 * 36,
        }

    def categoryContent(self, tid, pg, filter=True, extend=None):
        page = int(pg) if pg else 1
        ext = extend if isinstance(extend, dict) else {}
        host = self._host()

        params = {}
        if tid:
            params['cid'] = tid
        for k in ['city', 'audience', 'is_end', 'sort']:
            v = (ext.get(k) or '').strip()
            if v:
                params[k] = v

        fetch_params = dict(params)
        fetch_params['page'] = str(page)
        url = '%s/category.php?%s' % (host, urllib.parse.urlencode(fetch_params))
        html = self._fetch(url, timeout=10)
        items = self._parse_list(html) if html else []
        return {
            'list': items,
            'page': page,
            'pagecount': 9999,
            'limit': 36,
            'total': 9999 * 36,
        }

    def detailContent(self, ids):
        try:
            return self._detailContent_impl(ids)
        except Exception as e:
            import traceback
            err_info = str(e) + ' | ' + traceback.format_exc().replace('\n', ' ')
            return {'list': [{
                'vod_id': str(ids[0]) if isinstance(ids, list) else str(ids),
                'vod_name': '【解析异常-v3】',
                'vod_pic': '',
                'vod_content': err_info[:500],
                'vod_play_from': '瓜子漫画',
                'vod_play_url': '异常详情见简介',
            }]}

    def _detailContent_impl(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        vid = re.sub(r'\D', '', str(vid))
        if not vid:
            return {'list': []}
        host = self._host()
        url = '%s/comic.php?id=%s' % (host, vid)
        html = self._fetch(url, timeout=15)
        if not html:
            return {'list': [{
                'vod_id': vid,
                'vod_name': '【网络超时-v3】',
                'vod_pic': '',
                'vod_content': '获取页面失败，请检查网络连接或域名访问',
                'vod_play_from': '瓜子漫画',
                'vod_play_url': '网络超时',
            }]}

        m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        title = self._clean(m.group(1)) if m else ''

        pic = ''
        m = re.search(r'<img class="cover"[^>]*src="([^"]+)"', html)
        if m:
            pic = m.group(1)

        info = {}
        for m in re.finditer(r'<div[^>]*>(.*?)</div>', html, re.S):
            seg = m.group(1)
            mm = re.search(r'<span>([^<]+)</span>\s*<b>(.*?)</b>', seg, re.S)
            if mm:
                key = self._clean(mm.group(1)).rstrip(':').strip()
                val = self._clean(mm.group(2))
                if key:
                    info[key] = val

        content = ''
        m = re.search(r'class="[^"]*desc[^"]*"[^>]*>(.*?)</', html, re.S)
        if m:
            content = self._clean(m.group(1))
        if not content:
            m = re.search(r'<p[^>]*class="[^"]*summary[^"]*"[^>]*>(.*?)</p>', html, re.S)
            if m:
                content = self._clean(m.group(1))

        chaps = []
        _SKIP_KEYWORDS = ('开始阅读', '去阅读', '继续阅读', '立即阅读', '点击阅读',
                          '继续观看', '从第一章', '从第1', '阅读')
        # 兼容两种链接格式：/chapter.php?id=xxx 和 /chapter/xxx
        for a in re.finditer(r'href="(/(?:chapter\.php\?id=|chapter/)(\d+))"[^>]*>(.*?)</a>', html, re.S):
            name = self._clean(a.group(3))
            if not name:
                continue
            # 过滤按钮文字（如"开始阅读 >"、"去阅读 >"）
            if any(name.startswith(k) or name == k for k in _SKIP_KEYWORDS):
                continue
            chaps.append((a.group(2), name))

        # 去重：同名保留最短（通常最干净）
        uniq = {}
        for cid, name in chaps:
            if cid not in uniq or len(name) < len(uniq[cid]):
                uniq[cid] = name
        chaps = list(uniq.items())

        if not chaps:
            return {'list': [{
                'vod_id': vid,
                'vod_name': title or '【无章节-v3】',
                'vod_pic': pic if pic.startswith('http') else host + pic if pic.startswith('/') else host + '/' + pic,
                'vod_content': '未解析到章节，可能是页面结构变更或漫画已下架',
                'vod_play_from': '瓜子漫画',
                'vod_play_url': '无章节',
            }]}

        # 按正序排列（cid 升序 = 从第1话到最后一话）
        chaps.sort(key=lambda it: int(it[0]) if it[0].isdigit() else 0)
        eps = ['%s$%s' % (name, cid) for cid, name in chaps]

        return {
            'list': [{
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic if pic.startswith('http') else host + pic if pic.startswith('/') else host + '/' + pic,
                'type_name': '漫画',
                'vod_year': '',
                'vod_area': info.get('地区', ''),
                'vod_lang': '',
                'vod_remarks': info.get('状态', ''),
                'vod_director': info.get('作者', ''),
                'vod_actor': '',
                'vod_content': content or info.get('简介', ''),
                'vod_play_from': '瓜子漫画',
                'vod_play_url': '#'.join(eps),
            }]
        }

    def playerContent(self, flag, id, vipFlags=None):
        cid = str(id or '').strip()
        if cid.startswith('http'):
            return self._play_pics(cid)
        if not cid.isdigit():
            return self._play_empty()

        url = '%s/chapter.php?id=%s' % (self._host(), cid)
        html = self._fetch(url, timeout=10)
        if not html:
            return self._play_empty()

        imgs = []

        # 1) JSON-LD（支持 @graph 嵌套结构）
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict):
                    # 直接顶层 itemListElement
                    for item in data.get('itemListElement', []):
                        if isinstance(item, dict) and 'item' in item:
                            inner = item['item']
                            if isinstance(inner, dict):
                                u = inner.get('url', '')
                            else:
                                u = str(inner) if isinstance(inner, str) else ''
                            if u and u.startswith('http') and u not in imgs:
                                imgs.append(u)
                    # @graph 嵌套：遍历 graph 里的 ItemList
                    if not imgs and '@graph' in data:
                        for node in data['@graph']:
                            if isinstance(node, dict) and 'itemListElement' in node:
                                for item in node.get('itemListElement', []):
                                    if isinstance(item, dict) and 'item' in item:
                                        inner = item['item']
                                        if isinstance(inner, dict):
                                            u = inner.get('url', '')
                                        else:
                                            u = str(inner) if isinstance(inner, str) else ''
                                        if u and u.startswith('http') and u not in imgs:
                                            imgs.append(u)
                    if imgs:
                        return self._play_pics(imgs)
            except Exception:
                pass

        # 2) JS 数组
        m = re.search(r'var\s+(?:chapterData|images|pics|data)\s*=\s*(\[[^\]]*\])', html, re.S)
        if m:
            try:
                arr = json.loads(m.group(1))
                for u in arr:
                    if isinstance(u, str) and u.startswith('http') and u not in imgs:
                        imgs.append(u)
                if imgs:
                    return self._play_pics(imgs)
            except Exception:
                pass

        # 3) reader-images 区块（先 src，再 data-src / data-original / data-url）
        m_sec = re.search(r'<section[^>]*class=["\'][^"\']*reader-images[^"\']*["\'][^>]*>(.*?)</section>', html, re.S)
        if m_sec:
            sec = m_sec.group(1)
            # 先拿正常 src
            for mm in re.finditer(r'<img[^>]*src=["\'](https?://[^"\']+\.(?:webp|jpg|jpeg|png))["\']', sec):
                u = mm.group(1)
                if u not in imgs:
                    imgs.append(u)
            # 再拿懒加载地址
            for attr in ('data-src', 'data-original', 'data-url'):
                pat = r'<img[^>]*%s=["\'](https?://[^"\']+\.(?:webp|jpg|jpeg|png))["\']' % attr
                for mm in re.finditer(pat, sec):
                    u = mm.group(1)
                    if u not in imgs:
                        imgs.append(u)
            if imgs:
                return self._play_pics(imgs)

        # 4) 全页兜底：先 src 再 data-src / data-original / data-url
        for mm in re.finditer(r'<img[^>]*src=["\'](https?://[^"\']+\.(?:webp|jpg|jpeg|png))["\']', html):
            u = mm.group(1)
            if 'cover' not in u.lower() and 'ad' not in u.lower() and 'logo' not in u.lower() and u not in imgs:
                imgs.append(u)
        for attr in ('data-src', 'data-original', 'data-url'):
            pat = r'<img[^>]*%s=["\'](https?://[^"\']+\.(?:webp|jpg|jpeg|png))["\']' % attr
            for mm in re.finditer(pat, html):
                u = mm.group(1)
                if 'cover' not in u.lower() and 'ad' not in u.lower() and 'logo' not in u.lower() and u not in imgs:
                    imgs.append(u)

        if imgs:
            return self._play_pics(imgs)
        return self._play_empty()

    @staticmethod
    def _play_pics(imgs):
        if isinstance(imgs, list):
            url = 'pics://' + '&&'.join(imgs)
        else:
            url = imgs if imgs.startswith('pics://') or imgs.startswith('http') else ''
        # 关键：带上 Referer，否则 img.guazicdn.com 会返回 403
        return {
            'parse': 0,
            'playUrl': '',
            'url': url,
            'header': json.dumps({'Referer': 'https://www.guazimanhua.com/', 'User-Agent': 'Mozilla/5.0'}),
            'jx': 0
        }

    @staticmethod
    def _play_empty():
        return {'parse': 1, 'playUrl': '', 'url': '', 'header': '', 'jx': 0}

    def searchContent(self, key, quick=False, pg='1'):
        page = int(pg) if pg else 1
        key = str(key or '').strip()
        if not key:
            return {'list': [], 'page': page, 'pagecount': 9999, 'limit': 36, 'total': 9999 * 36}
        now = time.time()
        gap = 3.0 - (now - Spider._search_ts)
        if gap > 0:
            time.sleep(min(gap, 3.0))
        Spider._search_ts = time.time()
        try:
            kw = urllib.parse.quote(key, safe='')
            host = self._host()
            url = '%s/category.php?keyword=%s&page=%d' % (host, kw, page)
            html = self._fetch(url, timeout=10)
            items = self._parse_list(html) if html else []
            return {
                'list': items,
                'page': page,
                'pagecount': 9999,
                'limit': 36,
                'total': 9999 * 36,
            }
        except Exception:
            return {'list': [], 'page': page, 'pagecount': 9999, 'limit': 36, 'total': 9999 * 36}

    def searchContentPage(self, key, quick=False, pg='1'):
        return self.searchContent(key, quick, pg)


if __name__ == '__main__':
    sp = Spider()
    sp.init()
    print('=== 瓜子漫画 Spider v3 ===\n')

    home = sp.homeContent()
    print('[首页] 分类 %d 个, 列表 %d 条' % (len(home['class']), len(home['list'])))
    print('  pagecount=%d limit=%d total=%d' % (home['pagecount'], home['limit'], home['total']))
    if home['list']:
        print('  首条:', home['list'][0])

    for i in [1, 2, 5, 10]:
        cat = sp.categoryContent('', str(i), True, {})
        print('[全部 p%d] %d条 pagecount=%d' % (i, len(cat['list']), cat['pagecount']))

    if home['list']:
        vid = home['list'][0]['vod_id']
        d = sp.detailContent([vid])
        if d['list']:
            v = d['list'][0]
            print('\n[详情] %s | 集数=%d' % (v['vod_name'], v['vod_play_url'].count('#') + 1))
            ep = v['vod_play_url'].split('#')[0]
            if '$' in ep:
                p = sp.playerContent('', ep.split('$')[1])
                print('[播放] 图片=%d 首图=%s' % (p['url'].count('&&') + 1, p['url'][:60]))

    s = sp.searchContent('恋爱', False, '1')
    print('\n[搜索] %d条 pagecount=%d' % (len(s['list']), s['pagecount']))
    print('测试完成')
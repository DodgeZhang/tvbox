# -*- coding: utf-8 -*-
# ============ 大白鲨影院 dabaisha.py ============
# 定版: 88模板v7.5(能力层) / 71us模板v7.5(555骨架+13接口四壳) + shipin.trjsgc.com MacCMS-SSR 抓取 | 2026-09-19
# 站点: https://shipin.trjsgc.com (大白鲨影院, 恐怖片/电影/剧/综艺/动漫/短剧, 免会员在线播放)
# 架构: 模式D(SSR页面抓取) + 直链直出 (player_aaaa JSON, encrypt=0, url 即 m3u8 直链)
#   列表  /vodshow/{type}-----------.html (第1页) | /vodshow/{type}--------{pg}---.html (翻页, 总页≈1049)
#   分类  类型=拼音: dianying电影/lianxuju连续剧/kongbupian恐怖片/guochanju国产剧/oumeiju欧美剧/...
#   详情  /tr-{en}.html (h1 标题 + data 区 类型/地区/年份/主演/导演 + 简介 + 多线路 playlist 块)
#   搜索  /vodsearch/-------------.html?wd={kw} | 翻页 /vodsearch/----------{pg}---.html?wd= | suggest /ajax/suggest
#   播放  /trplay-{en}-{sid}-{nid}.html -> player_aaaa JSON (encrypt=0, url 直链 m3u8)
# 特色:  详情页即含全部线路集数(每线路一个 stui-content__playlist 块), 无需逐 sid 重建; 直链直出不加代理
# 加载契约: 首行coding/sys.path.append('..')/from base.spider import Spider(带兜底)/class Spider(Spider)
# 版本兼容铁律: 全文件禁 3.9+ API
# 分隔符铁律: $=名称/地址 #=选集 $$$=线路; 严禁$$或$连选集; 线路名与地址$$$段数必须相等

import sys, re, json, time, base64
from urllib.parse import urljoin, quote, unquote
from concurrent.futures import ThreadPoolExecutor
import requests

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider(object):
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = requests.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

# ============ CONFIG ============
HOSTS = ['https://shipin.trjsgc.com']
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
CATEGORIES = {'1': '电影', '2': '连续剧', '3': '恐怖片', '4': '国产剧', '5': '欧美剧',
              '6': '日韩剧', '7': '综艺', '8': '动漫', '9': '短剧', '10': '动作片'}
# tid -> vodshow 拼音路由
TYPE_ROUTE = {'1': 'dianying', '2': 'lianxuju', '3': 'kongbupian', '4': 'guochanju',
              '5': 'oumeiju', '6': 'rihanju', '7': 'zongyi', '8': 'dongman',
              '9': 'duanju', '10': 'dongzuopian'}
REFERER = 'https://shipin.trjsgc.com/'
PIC_REFERER = ''
VIDEO_EXTS = 'm3u8|mp4|flv|mkv|avi|ts'
DEAD_HOST = ('fengbao12.com', 'rrcdnbf', 'baofeng')
LINE_TTL = 600
LINE_WORKERS = 4
PLAY_TTL = 600
SEARCH_SUGGEST = 1
SEARCH_PER_PAGE = 12
SEARCH_TTL = 300
EXT_HOSTS = ('v.qq.com', 'qq.com', 'youku.com', 'bilibili.com', 'iqiyi.com', 'qiyi.com',
             'mgtv.com', 'sohu.com', 'le.com', 'pptv.com', 'wasu.cn', 'weibo.com')


class Spider(Spider):
    def init(self, extend=''):
        self.base = HOSTS[0].rstrip('/')
        self.ua = UA
        self.pk = ''
        self.ref = REFERER or self.base
        self.types = dict(CATEGORIES)
        self.filters = {}
        self._pc = {}
        self._lc = {}
        self._sc = {}
        self._srv = None
        self._last_ps = ()
        try:
            r = self.fetch(self.base, headers={'User-Agent': self.ua}, timeout=10000)
            if hasattr(r, 'url') and r.url and r.url != self.base:
                self.base = r.url.rstrip('/')
        except Exception:
            pass

    # ========== 网络层 ==========
    def _sess(self):
        if self._srv is None:
            s = requests.Session()
            a = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16)
            s.mount('http://', a)
            s.mount('https://', a)
            s.headers.update({'User-Agent': self.ua})
            self._srv = s
        return self._srv

    def _raw(self, url, timeout=15):
        try:
            r = self._sess().get(url, headers={'Referer': self.ref}, timeout=timeout)
            return r.text if r.status_code == 200 else ''
        except Exception:
            return ''

    def _get(self, url, timeout=15000):
        try:
            r = self.fetch(url, headers={'User-Agent': self.ua, 'Referer': self.ref}, timeout=timeout)
        except TypeError:
            try:
                r = self.fetch(url, headers={'User-Agent': self.ua, 'Referer': self.ref})
            except Exception:
                return ''
        except Exception:
            return ''
        try:
            return r.text if hasattr(r, 'text') else str(r)
        except Exception:
            return ''

    def _pic(self, u):
        if not u:
            return ''
        if u.startswith('//'):
            u = 'https:' + u
        elif u.startswith('/'):
            u = self.base + u
        return u

    def _pagecount(self, h, cur=1, route='dianying'):
        mx = cur
        pat = r'/vodshow/%s--------(\d+)---\.html' % re.escape(route)
        for m in re.finditer(pat, h):
            try:
                n = int(m.group(1))
                if n > mx:
                    mx = n
            except Exception:
                pass
        if re.search(r'下一页', h):
            mx = max(mx, cur + 1)
        return mx

    # ========== 首页 ==========
    def homeContent(self, filter=False):
        r = {'class': [{'type_id': k, 'type_name': v} for k, v in self.types.items()]}
        if filter and self.filters:
            r['filters'] = self.filters
        r['list'] = self.homeVideoContent().get('list', [])
        return r

    def homeVideoContent(self):
        h = self._get(self.base)
        items = self._items(h) if h else []
        if not items:
            h2 = self._get(self.base + '/vodshow/dianying-----------.html')
            items = self._items(h2) if h2 else []
        return {'list': items}

    # ========== 分类 ==========
    def categoryContent(self, tid, pg='1', filter=False, extend=''):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        t = str(tid)
        route = TYPE_ROUTE.get(t, 'dianying')
        if pn <= 1:
            url = self.base + '/vodshow/%s-----------.html' % route
        else:
            url = self.base + '/vodshow/%s--------%d---.html' % (route, pn)
        h = self._get(url)
        if not h:
            return {'page': pn, 'pagecount': 1, 'limit': 48, 'total': 0, 'list': []}
        items = self._items(h)
        return {'page': pn, 'pagecount': self._pagecount(h, pn, route), 'limit': 48,
                'total': len(items), 'list': items}

    # ========== 详情 ==========
    def detailContent(self, ids, quick='1'):
        vid = str(ids[0] if isinstance(ids, list) else ids or '')
        vid = vid.split('$')[0].split('/')[-1]
        m = re.search(r'([a-z0-9]+)', vid)
        vid = m.group(1) if m else ''
        if not vid:
            return {'list': []}
        h = self._get(self.base + '/tr-%s.html' % vid)
        if not h:
            return {'list': []}
        if not re.search(r'stui-content__playlist|trplay-%s' % re.escape(vid), h):
            return {'list': []}
        d = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_year': '', 'vod_area': '',
             'vod_class': '', 'vod_director': '', 'vod_actor': '', 'vod_content': '',
             'vod_remarks': '', 'vod_play_from': '', 'vod_play_url': ''}
        # 标题 (剔除 h1 内评分 span, 如 <span class="score">7.0</span>)
        tn = re.search(r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h1>', h, re.S)
        if tn:
            d['vod_name'] = re.sub(r'<span[^>]*class="[^"]*score[^"]*"[^>]*>.*?</span>', '', tn.group(1), flags=re.S)
            d['vod_name'] = re.sub(r'<[^>]+>', '', d['vod_name']).strip()
        if not d['vod_name']:
            tn = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
            if tn:
                d['vod_name'] = re.sub(r'<span[^>]*class="[^"]*score[^"]*"[^>]*>.*?</span>', '', tn.group(1), flags=re.S)
                d['vod_name'] = re.sub(r'<[^>]+>', '', d['vod_name']).strip()
        if not d['vod_name']:
            tn = re.search(r'<title>(.*?)</title>', h, re.S)
            if tn:
                d['vod_name'] = re.sub(r'[\s\-|·].*$', '', re.sub(r'<[^>]+>', '', tn.group(1)).strip()).strip()
        # 封面
        p = re.search(r'og:image[^c]{0,40}content="([^"]+)"', h, re.I)
        if not p:
            p = re.search(r'<img[^>]*data-original="(https?://[^"]+)"', h, re.I)
        if p:
            d['vod_pic'] = self._pic(p.group(1))
        # 简介 (剧情简述/desc)
        dm = re.search(r'剧情简述(.*?)</p>', h, re.S)
        if not dm:
            dm = re.search(r'<p class="desc[^"]*"[^>]*>(.*?)</p>', h, re.S)
        if dm:
            d['vod_content'] = re.sub(r'<[^>]+>|\s+', ' ', dm.group(1)).strip()[:500]
        # 类型/地区/年份/主演/导演 data 区 (每字段值为紧跟的 <a> 文本)
        for lbl, key in (('类型', 'vod_class'), ('地区', 'vod_area'), ('年份', 'vod_year'),
                         ('主演', 'vod_actor'), ('导演', 'vod_director')):
            fm = re.search(re.escape(lbl) + r'：</span>\s*((?:<a[^>]*>[^<]*</a>\s*)+)', h)
            if not fm:
                continue
            vals = re.findall(r'<a[^>]*>([^<]*)</a>', fm.group(1))
            vals = [v.strip() for v in vals if v.strip()]
            if lbl == '年份':
                for v in vals:
                    vm = re.search(r'\d{4}', v)
                    if vm:
                        vals = [vm.group(0)]
                        break
            v = ' '.join(vals).strip(' ,，')[:300]
            if v:
                d[key] = v
        # 线路+集数 (详情页含全部线路)
        froms, urls = self._lines(h, vid)
        if froms:
            d['vod_play_from'] = '$$$'.join(froms)
            d['vod_play_url'] = '$$$'.join(urls)
        return {'list': [d]}

    # ========== 线路提取 (详情页多 playlist 块) ==========
    def _lines(self, h, vid):
        ck = 'L' + vid
        c = self._lc.get(ck)
        if c and c[1] > time.time():
            return c[0]
        froms, urls = [], []
        # 每个线路 = 一个 ul.stui-content__playlist 块, 其线路名在同区块 h3 内
        blocks = list(re.finditer(r'<ul[^>]*class="stui-content__playlist[^"]*"[^>]*>(.*?)</ul>', h, re.S))
        ln_names = self._line_names(h, vid, len(blocks))
        for i, blk in enumerate(blocks):
            seg = blk.group(1)
            eps = []
            for m in re.finditer(r'href="(/trplay-%s-(\d+)-(\d+)\.html)"[^>]*>([^<]*)</a>' % re.escape(vid), seg):
                nid = int(m.group(3))
                lab = re.sub(r'<[^>]+>', '', m.group(4)).strip() or str(m.group(3))
                eps.append((nid, lab.replace('#', '-').replace('$', '|'),
                            urljoin(self.base, m.group(1))))
            if not eps:
                continue
            eps.sort(key=lambda x: x[0])
            nm = ln_names[i] if i < len(ln_names) else '线路%d' % (len(froms) + 1)
            nm = nm.replace('#', '-').replace('$', '|') or '线路%d' % (len(froms) + 1)
            froms.append(nm)
            urls.append('#'.join('%s$%s' % (lab, u) for _, lab, u in eps))
        # 兜底: 无 playlist 块时抓页面任意 trplay 链接
        if not froms:
            all_eps = []
            for m in re.finditer(r'href="(/trplay-%s-(\d+)-(\d+)\.html)"' % re.escape(vid), h):
                all_eps.append((int(m.group(3)), m.group(3),
                                urljoin(self.base, m.group(1))))
            if all_eps:
                all_eps = sorted(set(all_eps), key=lambda x: x[0])
                froms.append('线路1')
                urls.append('#'.join('%s$%s' % (lab, u) for _, lab, u in all_eps))
        res = (froms, urls)
        self._lc[ck] = (res, time.time() + LINE_TTL)
        return res

    def _line_names(self, h, vid, n):
        # 线路名: h3 "《片名》XX线路" 提取书名号后的标识
        out = []
        for m in re.finditer(r'<h3[^>]*>(.*?)</h3>', h, re.S):
            t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if not t:
                continue
            t2 = re.sub(r'^《[^》]*》', '', t).strip()
            if not t2 or any(k in t2 for k in ('简介', '周榜', '月榜', '榜单', '相同主演',
                                               '常见问题', '喜欢', '推荐')):
                continue
            # 清洗尾部冗余词, 取线路核心标识
            t2 = re.sub(r'(免费在线播放线路|在线播放线路|在线观看|播放线路|高清在线|免费完整版|全集.*)$', '', t2).strip()
            t2 = t2[:16]
            if t2 and t2 not in out:
                out.append(t2)
            if len(out) >= n:
                break
        return out

    # ========== 搜索 ==========
    def searchContent(self, key, quick=False, pg='1'):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        items, total, pcn = [], 0, 1
        sk = (re.sub(r'\s+', '', str(key or '')).lower(), pn, 1 if quick else 0)
        c0 = self._sc.get(sk)
        if c0 and c0[1] > time.time():
            return dict(c0[0])
        if pn <= 1 and SEARCH_SUGGEST:
            items = self._suggest(key)
            if quick:
                r = {'list': items, 'page': 1, 'pagecount': 1 if items else 0}
                if items:
                    self._sc[sk] = (r, time.time() + SEARCH_TTL)
                return dict(r)
        url = self.base + '/vodsearch/-------------.html?wd=%s' % quote(key) if pn <= 1 else \
            self.base + '/vodsearch/----------%d---.html?wd=%s' % (pn, quote(key))
        h = self._get(url)
        if h:
            pit = self._search_items(h)
            total, pcn = self._spage(h, pn, key)
            items = self._merge(items, pit)
        if not items and pn <= 1 and not SEARCH_SUGGEST:
            items = self._suggest(key)
        if pn <= 1 and items and not self._hit(items, key):
            items, pcn = [], 0
        r = {'list': items, 'page': pn, 'pagecount': pcn if items else 0}
        if items:
            self._sc[sk] = (r, time.time() + SEARCH_TTL)
        return dict(r)

    def _hit(self, items, key):
        k = re.sub(r'\s+', '', key or '').lower()
        if not k:
            return True
        for it in items:
            nm = re.sub(r'\s+', '', it.get('vod_name') or '').lower()
            if k in nm:
                return True
            if len(k) >= 2:
                for i in range(len(k) - 1):
                    if k[i:i + 2] in nm:
                        return True
        return False

    def _suggest(self, key):
        try:
            u = self.base + '/ajax/suggest?mid=1&wd=%s' % quote(key)
            r = self._sess().get(u, headers={'Referer': self.base + '/vodsearch/-------------.html?wd=%s' % quote(key)}, timeout=12)
            if r.status_code != 200:
                return []
            j = json.loads(r.text)
        except Exception:
            return []
        out = []
        for it in (j.get('list') or []):
            en = it.get('en') or ''
            if not en:
                continue
            out.append({'vod_id': en, 'vod_name': (it.get('name') or '').strip()[:80],
                        'vod_pic': self._pic(it.get('pic') or ''), 'vod_remarks': ''})
        return out

    def _merge(self, a, b):
        out, seen = [], set()
        for x in list(a or []) + list(b or []):
            k = re.sub(r'[\s《》\[\]【】()（）]+', '', x.get('vod_name') or '').lower()
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(x)
        return out

    def _spage(self, h, pn, key):
        mx = pn
        # "尾页" 链接 /vodsearch/...---N---.html
        m = re.search(r'尾页</a></li>.*?/vodsearch/[^"]*---(\d+)---\.html', h, re.S)
        if not m:
            m = re.search(r'class="[\w ]*active[\w ]*"[^>]*><span[^>]*>\d+/(\d+)</span>', h)
        if m:
            try:
                mx = int(m.group(1))
            except Exception:
                pass
        for m2 in re.finditer(r'/vodsearch/[^"]*---(\d+)---\.html', h):
            try:
                n = int(m2.group(1))
                if n > mx:
                    mx = n
            except Exception:
                pass
        if re.search(r'下一页', h):
            mx = max(mx, pn + 1)
        return 0, mx

    # ========== 播放 ==========
    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id) if id else str(flag)
        ck = 'P' + raw
        c = self._pc.get(ck)
        if c and c[1] > time.time():
            return dict(c[0])
        url = raw.split('$', 1)[1] if '$' in raw else raw
        if not url:
            return {'parse': 0, 'url': ''}
        if re.search(r'\.(m3u8|mp4|flv|mkv|avi|ts)(\?|$)', url, re.I):
            r = {'parse': 0, 'url': url, 'header': {'User-Agent': self.ua, 'Referer': self.ref}}
            self._pc[ck] = (r, time.time() + PLAY_TTL)
            return dict(r)
        full = url if url.startswith('http') else urljoin(self.base, url)
        h = self._get(full)
        u = self._parse_play(h) if h else ''
        m2 = re.search(r'/trplay-[a-z0-9]+-(\d+)-\d+\.html', full)
        k2 = m2.group(1) if m2 else ''
        if not u and k2 and self._last_ps and self._last_ps[0] == k2:
            u = self._last_ps[1]
        if u and re.search(r'\.(m3u8|mp4|flv)(\?|$)', u, re.I):
            r = {'parse': 0, 'url': u, 'header': {'User-Agent': self.ua, 'Referer': self.ref}}
        elif u:
            r = {'parse': 1, 'url': u, 'header': {'User-Agent': self.ua, 'Referer': full}}
        else:
            r = {'parse': 0, 'url': ''}
        if u:
            self._last_ps = (k2, u)
        self._pc[ck] = (r, time.time() + PLAY_TTL)
        return dict(r)

    def _parse_play(self, h):
        mj = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', h, re.S)
        if mj:
            try:
                pj = json.loads(mj.group(1))
                u = pj.get('url') or ''
                if u:
                    if not re.search(r'\.(m3u8|mp4|flv)(\?|$)', u, re.I):
                        u = u.rstrip('/') + '/index.m3u8'
                    return u
            except Exception:
                pass
        m = re.search(r'var\s+videoSrc\s*=\s*["\']([^"\']+\.m3u8)["\']', h) or \
            re.search(r'<video[^>]+src="([^"]+\.m3u8)"', h, re.I) or \
            re.search(r'(https?://[^\s"\'<>]+\.m3u8)', h)
        if m:
            return m.group(1)
        return ''

    # ========== 列表解析 ==========
    def _items(self, h):
        items, seen, pos = [], set(), 0
        # 列表卡片: <a class="...stui-vodlist__thumb lazyload" href="/tr-x.html" title="名" data-original="图">
        # 注意: a 标签属性顺序不定, data-original 可能被贪婪匹配吞掉, 故整标签捕获后分段提取
        for m in re.finditer(r'<a[^>]*class="[^"]*stui-vodlist__thumb[^"]*"[^>]*href="(/tr-([a-z0-9]+)\.html)"[^>]*title="([^"]*)"[^>]*>', h):
            vid = m.group(2)
            if vid in seen:
                continue
            tag = h[m.start():m.end()]
            pm = re.search(r'data-original=["\']([^"\']+)["\']', tag)
            pic = self._pic(pm.group(1)) if pm else ''
            seen.add(vid)
            rm = ''
            blk = h[m.end() - 5:m.end() + 400]
            rm2 = re.search(r'pic-text[^>]*>([^<]*)<', blk)
            if rm2:
                rm = rm2.group(1).strip()
            items.append({
                'vod_id': vid,
                'vod_name': re.sub(r'\s+', ' ', m.group(3)).strip()[:80],
                'vod_pic': pic,
                'vod_remarks': rm,
            })
        return items

    def _search_items(self, h):
        # 搜索卡片结构与列表卡片相同 stui-vodlist__thumb
        return self._items(h)

    # ========== 四壳扩展钩子 ==========
    def isVideoFormat(self, url):
        if not url:
            return False
        if '.m3u8' in url.lower():
            return True
        return bool(re.search(r'\.(?:%s)(?:\?|$)' % (VIDEO_EXTS or 'm3u8|mp4|flv'), url, re.I))

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return ''

    def destroy(self):
        try:
            self._pc.clear()
            self._lc.clear()
            self._sc.clear()
            if self._srv is not None:
                self._srv.close()
        except Exception:
            pass
        self._srv = None

    def progressVideo(self, speed, time, end):
        return False

    def setVideoFlags(self, siteKey, flags):
        try:
            self._siteKey = siteKey or ''
            self._vflags = flags or {}
        except Exception:
            pass

    # ========== 本地代理(兜底): m3u8 KEY/分片重写 + 图片转码 ==========
    def localProxy(self, param):
        p = param.get('url') if isinstance(param, dict) else param
        p = str(p or '')
        p = p.split('url=', 1)[-1] if 'url=' in p else p
        p = unquote(p) if '%' in p else p
        if re.search(r'\.(jpe?g|png|webp|gif)(\?|$)', p, re.I):
            return self._img(p)
        if '.m3u8' in p:
            return self._rewrite_m3u8(p)
        try:
            r = self.fetch(p, headers={'User-Agent': self.ua, 'Referer': self.ref}, timeout=20000)
            if hasattr(r, 'status_code') and r.status_code != 200:
                return [r.status_code, 'text/plain', '']
            return [200, r.headers.get('Content-Type', 'application/octet-stream'), r.content]
        except Exception:
            return [404, 'text/plain', '']

    def _rewrite_m3u8(self, url):
        try:
            r = self.fetch(url, headers={'User-Agent': self.ua, 'Referer': self.ref}, timeout=20000)
            if hasattr(r, 'status_code') and r.status_code != 200:
                return [r.status_code, 'text/plain', '']
            body = r.text if hasattr(r, 'text') else str(r)
        except Exception:
            return [404, 'text/plain', '']
        base = url.rsplit('/', 1)[0] + '/'
        origin = re.match(r'https?://[^/]+', url)
        origin = origin.group(0) if origin else ''
        out = []
        for ln in body.splitlines():
            if ln.startswith('#EXT-X-KEY'):
                m = re.search(r'URI="([^"]+)"', ln)
                if m:
                    ku = m.group(1)
                    if ku.startswith('/'):
                        ku = origin + ku
                    elif not ku.startswith('http'):
                        ku = base + ku
                    ln = ln.replace('URI="%s"' % m.group(1), 'URI="%s"' % ('proxy?url=' + quote(ku, safe='')))
            elif ln.startswith('http'):
                ln = 'proxy?url=' + quote(ln, safe='')
            elif ln.startswith('/') and not ln.startswith('//'):
                ln = 'proxy?url=' + quote(origin + ln, safe='')
            out.append(ln)
        return [200, 'application/vnd.apple.mpegurl', '\n'.join(out)]

    def _img(self, u):
        try:
            r = requests.get(u, headers={'User-Agent': self.ua, 'Referer': PIC_REFERER or self.ref}, timeout=15)
            if r.status_code != 200 or len(r.content) < 100:
                return [r.status_code or 404, 'text/plain', '']
            return [200, r.headers.get('Content-Type', 'image/jpeg'), r.content]
        except Exception:
            return [404, 'text/plain', '']
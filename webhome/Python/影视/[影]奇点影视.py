# -*- coding: utf-8 -*-
# ============ 奇点影视 qidianyingshi.py v2 ============
# 定版: 71us模板v7.5(555骨架+13接口四壳) + qidianyingshi.net MacCMS-SSR 抓取 | 2026-09-19
# 站点: https://qidianyingshi.net (奇点影视)
# v2 修复: ①多线路重建(source-flat 全 sid 并发抓取, 原先只出 ep-grid 的 1 条线)
#         ②外链线(qq/youku/bilibili/iqiyi)改 parse=1 网页解析, 原先 parse=0 返回 HTML 致黑屏
#         ③线路排序: 实测可播直出线优先(okm3u8/dyttm3u8/1080zyk), 已知死 CDN 降权
# 列表  /list/{tid}.html (第1页) | /top/{tid}--------{pg}---.html (翻页)
# 详情  /play/{vid}-1-1.html (选集在 ep-grid, 线路在 source-flat, sid 不连续)
# 搜索  /search.html?wd={kw} | /search/----------{pg}---.html
# 播放  /play/{vid}-{sid}-{nid}.html -> player_aaaa JSON (encrypt=0)
# 分类:  1电影 / 2电视剧 / 3综艺 / 4动漫 / 39短剧
# 分隔符铁律: $=名称/地址 #=选集 $$$=线路; 线路名与地址$$$段数必须相等
# 版本兼容铁律: 全文件禁 3.9+ API

import sys, re, json, time
from urllib.parse import urljoin, quote, unquote
import requests
try:
    from concurrent.futures import ThreadPoolExecutor
except Exception:
    ThreadPoolExecutor = None

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
HOSTS = ['https://qidianyingshi.net']
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
CATEGORIES = {'1': '电影', '2': '电视剧', '3': '综艺', '4': '动漫', '39': '短剧'}
REFERER = 'https://qidianyingshi.net/'
PIC_REFERER = ''
VIDEO_EXTS = 'm3u8|mp4|flv|mkv|avi|ts'
PREF_FROM = ('okm3u8', 'dyttm3u8', '1080zyk', 'lzm3u8', 'heimuer', 'wjm3u8')
DEAD_HOST = ('fengbao12.com', 'rrcdnbf', 'baofeng')
DEAD_FROM = ('bfzym3u8',)
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

    def _pagecount(self, h, cur=1):
        mx = cur
        for m in re.finditer(r'/top/\d+--------(\d+)---\.html', h):
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
            h2 = self._get(self.base + '/list/1.html')
            items = self._items(h2) if h2 else []
        return {'list': items}

    # ========== 分类 ==========
    def categoryContent(self, tid, pg='1', filter=False, extend=''):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        t = str(tid)
        if pn <= 1:
            url = self.base + '/list/%s.html' % t
        else:
            url = self.base + '/top/%s--------%d---.html' % (t, pn)
        h = self._get(url)
        if not h:
            return {'page': pn, 'pagecount': 1, 'limit': 48, 'total': 0, 'list': []}
        items = self._items(h)
        return {'page': pn, 'pagecount': self._pagecount(h, pn), 'limit': 48,
                'total': len(items), 'list': items}

    # ========== 详情 ==========
    def detailContent(self, ids, quick='1'):
        vid = str(ids[0] if isinstance(ids, list) else ids or '')
        vid = vid.split('$')[0].split('/')[-1]
        m = re.search(r'([a-z0-9]+)', vid)
        vid = m.group(1) if m else ''
        if not vid:
            return {'list': []}
        h = self._get(self.base + '/play/%s-1-1.html' % vid)
        if not h:
            return {'list': []}
        if not re.search(r'player_aaaa|source-flat', h):
            return {'list': []}
        mc = re.search(r'/play/([a-z0-9]+)-\d+-\d+\.html', h)
        if mc and mc.group(1) != vid:
            vid = mc.group(1)
        d = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_year': '', 'vod_area': '',
             'vod_class': '', 'vod_director': '', 'vod_actor': '', 'vod_content': '',
             'vod_remarks': '', 'vod_play_from': '', 'vod_play_url': ''}
        mj = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', h, re.S)
        pj = {}
        if mj:
            try:
                pj = json.loads(mj.group(1))
            except Exception:
                pj = {}
        vd = pj.get('vod_data') or {}
        d['vod_name'] = (vd.get('vod_name') or '').strip()
        d['vod_director'] = (vd.get('vod_director') or '').strip()
        d['vod_actor'] = (vd.get('vod_actor') or '').strip()
        d['vod_class'] = (vd.get('vod_class') or '').strip()
        if not d['vod_name']:
            tn = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
            if tn:
                d['vod_name'] = re.sub(r'<[^>]+>', '', tn.group(1)).strip()
        if not d['vod_name']:
            tn = re.search(r'<title>(.*?)</title>', h, re.S)
            if tn:
                d['vod_name'] = re.sub(r'[\s\-|].*$', '', re.sub(r'<[^>]+>', '', tn.group(1)).strip()).strip()
        p = re.search(r'og:image"\s+content="([^"]+)"', h, re.I)
        if not p:
            p = re.search(r'<img[^>]*data-original="(https?://[^"]+)"', h, re.I)
        if p:
            d['vod_pic'] = self._pic(p.group(1))
        dm = re.search(r'og:description"\s+content="([^"]*)"', h, re.I)
        if dm:
            d['vod_content'] = re.sub(r'\s+', ' ', dm.group(1)).strip()[:500]
        tt = re.search(r'<title>(.*?)</title>', h, re.S)
        if tt:
            ttl = tt.group(1).strip()
            tm = re.match(r'^(?:【[^】]*】)?\s*([^·\s][^·]{0,40}?)\s*·\s*(\d{4})\s*·\s*([^·]+?)\s*(?:·|$)', ttl)
            if tm:
                if not d['vod_name']:
                    d['vod_name'] = tm.group(1).strip()
                if not d['vod_year']:
                    d['vod_year'] = tm.group(2)
                if not d['vod_area']:
                    d['vod_area'] = tm.group(3).strip()
        if not d['vod_year']:
            ym = re.search(r'<span>(\d{4})</span>', h)
            if ym:
                d['vod_year'] = ym.group(1)
        froms, urls = self._lines(h, vid)
        if froms:
            d['vod_play_from'] = '$$$'.join(froms)
            d['vod_play_url'] = '$$$'.join(urls)
        return {'list': [d]}

    # ========== 多线路重建 ==========
    def _lines(self, h, vid):
        ck = 'L' + vid
        c = self._lc.get(ck)
        if c and c[1] > time.time():
            return c[0]
        ls = []
        for m in re.finditer(r'<a[^>]*class="source-flat[^"]*"[^>]*href="/play/%s-(\d+)-1\.html"[^>]*>([^<]+)</a>' % re.escape(vid), h):
            sid = m.group(1)
            nm = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if nm and not any(x[0] == sid for x in ls):
                ls.append((sid, nm))
        if not ls:
            ls = [('1', '线路1')]
        got = self._par_lines(vid, ls)
        res = self._build(got)
        self._lc[ck] = (res, time.time() + LINE_TTL)
        return res

    def _par_lines(self, vid, ls):
        r = []
        if ThreadPoolExecutor and len(ls) > 1:
            try:
                with ThreadPoolExecutor(max_workers=LINE_WORKERS) as ex:
                    r = list(ex.map(lambda x: self._one_line(vid, x[0], x[1]), ls))
            except Exception:
                r = []
        if not r:
            r = [self._one_line(vid, s, n) for s, n in ls]
        return [x for x in r if x and x['eps']]

    def _one_line(self, vid, sid, nm):
        h = self._raw(self.base + '/play/%s-%s-1.html' % (vid, sid))
        if not h:
            return None
        eps, seen = [], set()
        for m in re.finditer(r'<a[^>]*class="ep-item[^"]*"[^>]*data-source-key="%s_(\d+)"[^>]*href="([^"]+)"[^>]*>([^<]*)</a>' % re.escape(sid), h):
            nid = m.group(1)
            if nid in seen:
                continue
            seen.add(nid)
            eps.append((int(nid), re.sub(r'<[^>]+>', '', m.group(3)).strip() or nid, urljoin(self.base, m.group(2))))
        if not eps:
            for m in re.finditer(r'<a[^>]*class="ep-item[^"]*"[^>]*href="(/play/%s-%s-(\d+)\.html)"[^>]*>([^<]*)</a>' % (re.escape(vid), re.escape(sid)), h):
                nid = m.group(3)
                if nid in seen:
                    continue
                seen.add(nid)
                eps.append((int(nid), re.sub(r'<[^>]+>', '', m.group(4)).strip() or nid, urljoin(self.base, m.group(1))))
        if not eps:
            for nid in sorted(set(re.findall(r'/play/%s-%s-(\d+)\.html' % (re.escape(vid), re.escape(sid)), h)), key=int):
                eps.append((int(nid), nid, '%s/play/%s-%s-%s.html' % (self.base, vid, sid, nid)))
        if not eps:
            return None
        eps.sort(key=lambda x: x[0])
        uu = fr = ''
        pj = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', h, re.S)
        if pj:
            try:
                j = json.loads(pj.group(1))
                uu = j.get('url') or ''
                fr = j.get('from') or ''
            except Exception:
                pass
        if re.search(r'\.(m3u8|mp4|flv)(\?|$)', uu, re.I):
            kind = 'm3u8'
        elif uu.startswith('http'):
            kind = 'ext'
        else:
            kind = 'none'
        return {'sid': sid, 'name': nm, 'eps': eps, 'kind': kind, 'from': fr, 'url': uu}

    def _score(self, x):
        host = ''
        m = re.match(r'https?://([^/]+)', x.get('url') or '')
        if m:
            host = m.group(1)
        if x['kind'] == 'm3u8':
            if any(d in host for d in DEAD_HOST) or (x.get('from') or '') in DEAD_FROM:
                return 2
            if any(p in (x.get('from') or '') for p in PREF_FROM):
                return 0
            return 1
        if x['kind'] == 'ext':
            return 3
        return 4

    def _build(self, got):
        got = sorted(got, key=self._score)
        froms, urls, used = [], [], {}
        for x in got:
            nm = x['name'].replace('#', '-').replace('$', '|')
            used[nm] = used.get(nm, 0) + 1
            if used[nm] > 1:
                nm = '%s#%d' % (nm, used[nm])
            froms.append(nm)
            urls.append('#'.join('%s$%s' % (ep.replace('#', '-').replace('$', '|'), u) for _, ep, u in x['eps']))
        return froms, urls

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
        if pn <= 1:
            url = self.base + '/search.html?wd=%s' % quote(key)
        else:
            url = self.base + '/search/----------%d---.html?wd=%s' % (pn, quote(key))
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
            u = self.base + '/index.php/ajax/suggest?mid=1&wd=%s' % quote(key)
            r = self._sess().get(u, headers={'Referer': self.base + '/search.html?wd=%s' % quote(key)}, timeout=12)
            if r.status_code != 200:
                return []
            j = json.loads(r.text)
        except Exception:
            return []
        out = []
        for it in (j.get('list') or []):
            vid = it.get('id')
            if not vid:
                continue
            out.append({'vod_id': str(vid), 'vod_name': (it.get('name') or '').strip()[:80],
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
        total = 0
        m = re.search(r'ewave-total"\)\.text\((\d+)\)', h)
        if m:
            try:
                total = int(m.group(1))
            except Exception:
                total = 0
        if pn <= 1 and total > 50000:
            h2 = self._get(self.base + '/search/----------2---.html?wd=%s' % quote(key))
            m2 = re.search(r'ewave-total"\)\.text\((\d+)\)', h2) if h2 else None
            if m2:
                try:
                    total = int(m2.group(1))
                except Exception:
                    pass
        if total > 50000:
            total = 0
        if total > 0:
            return total, max(1, int((total + SEARCH_PER_PAGE - 1) / SEARCH_PER_PAGE))
        mx = pn
        for m3 in re.finditer(r'/search/-+(\d+)---\.html', h):
            try:
                n = int(m3.group(1))
                if n > mx:
                    mx = n
            except Exception:
                pass
        if re.search(r'下一页', h):
            mx = max(mx, pn + 1)
        return total, mx

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
        m2 = re.search(r'/play/([a-z0-9]+)-', full)
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
        items, seen = [], set()
        for m in re.finditer(r'<a href="(/html/([a-z0-9]+)\.html)"[^>]*>(.*?)</a>', h, re.S):
            vid = m.group(2)
            blk = m.group(3)
            if vid in seen:
                continue
            seen.add(vid)
            pic = re.search(r'data-original="([^"]+)"', blk) if blk else None
            name = re.search(r'vod-title[^"]*">([^<]*)<', blk) if blk else None
            if name is None:
                ialt = re.search(r'<img[^>]*alt="([^"]*)"', blk) if blk else None
                if ialt:
                    name = ialt
            rm = re.search(r'poster-remarks[^>]*>([^<]*)<', blk) if blk else None
            items.append({
                'vod_id': vid,
                'vod_name': re.sub(r'\s+', ' ', (name.group(1) if name else '')).strip()[:80],
                'vod_pic': self._pic(pic.group(1)) if pic else '',
                'vod_remarks': (rm.group(1) if rm else '').strip(),
            })
        return items

    def _search_items(self, h):
        parts = h.split('<div class="search-item">')[1:]
        if not parts:
            parts = h.split('class="search-item"')[1:]
        items, seen = [], set()
        for blk in parts:
            blk = blk[:3000]
            m = re.search(r'href="(?:/play/([a-z0-9]+)-\d+-\d+\.html|/html/([a-z0-9]+)\.html)"', blk)
            if not m:
                continue
            vid = m.group(1) or m.group(2)
            if not vid or vid in seen:
                continue
            seen.add(vid)
            pic = re.search(r'data-original="([^"]+)"', blk)
            if not pic:
                pic = re.search(r'src="(https?://[^"]+\.(?:jpe?g|png|webp))"', blk, re.I)
            name = re.search(r'item-title[^>]*>\s*<a[^>]*>([^<]*)</a>', blk, re.S)
            if not name:
                name = re.search(r'<img[^>]*alt="([^"]*)"', blk)
            rm = re.search(r'item-remarks[^>]*>([^<]*)<', blk)
            tg = re.search(r'item-type-tag[^>]*>([^<]*)<', blk)
            items.append({
                'vod_id': vid,
                'vod_name': re.sub(r'\s+', ' ', (name.group(1) if name else '')).strip()[:80],
                'vod_pic': self._pic(pic.group(1)) if pic else '',
                'vod_remarks': (rm.group(1) if rm else '').strip() or (tg.group(1) if tg else '').strip(),
            })
        return items

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

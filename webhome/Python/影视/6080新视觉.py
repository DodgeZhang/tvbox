# -*- coding: utf-8 -*-
import sys, re, time
from html import unescape
from urllib.parse import urljoin, quote, urlsplit, urlunsplit
import requests
sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = requests.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

HOST = 'http://m.hr0592.cn'
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
CATEGORIES = {'1': '电影', '2': '电视剧', '25': '微短剧', '4': '动漫', '3': '综艺', '5': '动作片', '6': '爱情片', '7': '科幻片', '8': '恐怖片', '9': '战争片', '10': '喜剧片', '11': '纪录片', '12': '剧情片', '13': '大陆剧', '14': '港台剧', '15': '欧美剧', '16': '日韩剧'}


class Spider(Spider):
    def init(self, extend=''):
        self.base = HOST.rstrip('/')
        self.ua = UA
        self.types = dict(CATEGORIES)
        self._c = {}
        try:
            r = self._fetch(self.base, headers={'User-Agent': self.ua}, t=8000)
            if hasattr(r, 'url') and r.url and r.url != self.base:
                self.base = r.url.rstrip('/')
            h = r.text if hasattr(r, 'text') else str(r)
            if h:
                self._c[self.base] = [time.time(), h]
        except:
            pass

    def _fetch(self, url, headers=None, t=15000):
        hd = headers or {'User-Agent': self.ua, 'Referer': self.base}
        try:
            return self.fetch(url, headers=hd, timeout=t)
        except TypeError:
            return self.fetch(url, headers=hd)

    def _get(self, url, ttl=0, t=15000):
        k = url
        if ttl and k in self._c and time.time() - self._c[k][0] < ttl:
            return self._c[k][1]
        try:
            r = self._fetch(url, t=t)
            h = r.text if hasattr(r, 'text') else str(r)
            if h:
                self._c[k] = [time.time(), h]
            return h
        except:
            return ''

    def _pic(self, u):
        return re.sub(r'^http://', 'https://', u) if u else ''

    def _enc(self, u):
        if not u or not re.search(r'[^\x00-\x7f]', u):
            return u
        try:
            p = urlsplit(u)
            return urlunsplit((p.scheme, p.netloc, quote(p.path, safe='/%:@'), p.query, ''))
        except:
            return u

    def _items(self, h):
        out, seen = [], set()
        blk = re.compile(r'<div class="module-item-cover">([\s\S]*?)<div class="module-item-titlebox">([\s\S]*?)<div class="module-item-text">([^<]*)<')
        for m in blk.finditer(h):
            g1, g2, rem = m.group(1), m.group(2), m.group(3).strip()
            vm = re.search(r'href="/movie/(\d+)\.html"', g1)
            pm = re.search(r'data-src="(https?://[^"]+)"', g1)
            if not vm:
                continue
            vid = vm.group(1)
            nm = re.search(r'class="module-item-title"[^>]*title="([^"]*)"', g2) or re.search(r'<a[^>]*>([\s\S]*?)</a>', g2)
            name = (nm.group(1) if nm else '').strip()
            if not name or vid in seen or len(name) > 100:
                continue
            seen.add(vid)
            out.append({'vod_id': vid, 'vod_name': name[:50], 'vod_pic': self._pic(pm.group(1) if pm else ''), 'vod_remarks': rem[:20]})
        if not out:
            for m in re.finditer(r'href="/movie/(\d+)\.html"[^>]*title="([^"]*)"', h):
                vid, name = m.group(1), m.group(2).strip()
                if not name or vid in seen or len(name) > 100:
                    continue
                seen.add(vid)
                after = h[m.end():m.end() + 800]
                pm = re.search(r'data-src="(https?://[^"]+)"', after)
                rm = re.search(r'class="module-item-text"[^>]*>([^<]+)<', after)
                out.append({'vod_id': vid, 'vod_name': name[:50], 'vod_pic': self._pic(pm.group(1) if pm else ''), 'vod_remarks': rm.group(1).strip()[:20] if rm else ''})
        return out

    def _pagecount(self, h, cur, t):
        mx = cur
        for m in re.finditer(r'/frim/%s-(\d+)\.html' % t, h):
            try:
                n = int(m.group(1))
                if n > mx:
                    mx = n
            except:
                pass
        return mx

    def homeContent(self, filter=False):
        return {'class': [{'type_id': k, 'type_name': v} for k, v in self.types.items()], 'list': self.homeVideoContent().get('list', [])}

    def homeVideoContent(self):
        h = self._get(self.base, ttl=120)
        items = self._items(h)
        if not items:
            h2 = self._get(self.base + '/frim/1.html')
            items = self._items(h2)
        return {'list': items}

    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        try:
            pn = max(int(str(pg)), 1)
        except:
            pn = 1
        t = str(tid).split('|')[0]
        u = f'{self.base}/frim/{t}.html' if pn == 1 else f'{self.base}/frim/{t}-{pn}.html'
        h = self._get(u, ttl=300)
        if not h:
            return {'page': pn, 'pagecount': 1, 'limit': 24, 'total': 0, 'list': []}
        items = self._items(h)
        return {'page': pn, 'pagecount': self._pagecount(h, pn, t), 'limit': 24, 'total': len(items), 'list': items}

    def detailContent(self, ids, quick='1'):
        vid = str(ids[0] if isinstance(ids, list) else ids or '')
        m = re.search(r'(\d+)', vid)
        vid = m.group(1) if m else ''
        if not vid:
            return {'list': []}
        h = self._get(self.base + f'/movie/{vid}.html', ttl=300, t=25000)
        if not h:
            return {'list': []}
        d = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_year': '', 'vod_area': '', 'vod_class': '', 'vod_director': '', 'vod_actor': '', 'vod_content': '', 'vod_remarks': '', 'vod_play_from': '', 'vod_play_url': ''}
        m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', h)
        if m:
            d['vod_name'] = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        m = re.search(r'data-src="(https?://[^"]+)"', h)
        if m:
            d['vod_pic'] = self._pic(m.group(1))
        for k, pat in (('vod_year', r'上映[：:]\s*</span>\s*<div[^>]*>\s*([0-9]{4})'),
                       ('vod_remarks', r'更新[：:]\s*</span>\s*<div[^>]*>([^<]+)'),
                       ('vod_area', r'itemprop="contentLocation">([^<]+)')):
            m = re.search(pat, h)
            if m and not d[k]:
                d[k] = m.group(1).strip()
        for k, pat in (('vod_director', r'导演[：:]\s*</span>\s*<div[^>]*>([\s\S]*?)</div>'),
                       ('vod_actor', r'主演[：:]\s*</span>\s*<div[^>]*>([\s\S]*?)</div>')):
            m = re.search(pat, h)
            if m:
                d[k] = re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', '', m.group(1)))).strip().rstrip('，').strip()[:200]
        m = re.search(r'class="video-info-item video-info-content vod_content"[^>]*>([\s\S]*?)</div>', h)
        if m:
            d['vod_content'] = re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', '', m.group(1)))).strip()[:500]
        pf, pu = self._lines(vid, h)
        if pf:
            d['vod_play_from'] = '$$$'.join(pf)
            d['vod_play_url'] = '$$$'.join(pu)
        return {'list': [d]}

    def _lines(self, vid, h):
        pf, pu = [], []
        tm = re.search(r'<dt class="tabt3">([\s\S]*?)</dt>', h)
        ids, names = [], []
        if tm:
            for s in re.finditer(r'<span id="([A-Za-z0-9_]+)"[^>]*>([\s\S]*?)</span>', tm.group(1)):
                ids.append(s.group(1))
                nm = re.search(r'<b>([^<]+)</b>', s.group(2))
                names.append(nm.group(1).strip() if nm else '')
        for i, fid in enumerate(ids):
            mm = re.search(r'<dd class="%s"[^>]*>([\s\S]*?)</dd>' % re.escape(fid), h)
            if not mm:
                continue
            eps = re.findall(r'href="(/play/\d+-\d+-\d+\.html)"[^>]*>([^<]+)</a>', mm.group(1))
            if not eps:
                continue
            pf.append(names[i] if i < len(names) and names[i] else f'线路{i + 1}')
            pu.append('#'.join(f'{e.strip().replace("#", "-").replace("$", "|")}${urljoin(self.base, href)}' for href, e in eps))
        return pf, pu

    def searchContent(self, key, quick=False, pg='1'):
        h = self._get(self.base + '/search.php?searchword=' + quote(key))
        return {'list': self._items(h) if h else [], 'page': 1}

    def playerContent(self, flag, id, vipFlags=None):
        u = str(id) if id else str(flag)
        if '://' in u and re.search(r'\.(m3u8|mp4|flv)(\?|$)', u, re.I):
            return {'parse': 0, 'url': self._enc(u)}
        full = u if u.startswith('http') else urljoin(self.base, u)
        h = self._get(full, ttl=120, t=25000)
        if not h:
            return {'parse': 0, 'url': ''}
        m = re.search(r'var\s+now\s*=\s*["\']([^"\']+)["\']', h)
        if m:
            return {'parse': 0, 'url': self._enc(m.group(1))}
        m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', h)
        if m:
            return {'parse': 0, 'url': self._enc(m.group(1))}
        return {'parse': 0, 'url': ''}

# -*- coding: utf-8 -*-
import sys, re, time, json
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

HOST = 'https://www.6080video.tv'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
CATEGORIES = {'19': '电影', '20': '电视剧', '23': '短剧', '22': '动漫', '21': '综艺', '24': '动作片', '25': '喜剧片', '26': '爱情片', '27': '科幻片', '28': '恐怖片', '29': '剧情片', '30': '战争片', '31': '纪录片', '38': '国产剧', '39': '港台剧', '40': '美剧', '41': '日韩剧', '42': '海外剧', '43': '泰剧', '44': 'Netflix自制剧', '45': '国产动漫', '46': '日韩动漫', '47': '港台动漫', '48': '欧美动漫', '50': '有声动漫', '1': '国产综艺', '2': '港台综艺', '3': '日韩综艺', '4': '欧美综艺', '51': '女频恋爱', '52': '反转爽剧', '54': '年代穿越', '55': '古装仙侠', '56': '现代都市', '57': '擦边短剧'}


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
            h = r.text if hasattr(r, 'text') else r
            if isinstance(h, bytes):
                h = h.decode('utf-8', 'ignore')
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
            h = r.text if hasattr(r, 'text') else r
            if isinstance(h, bytes):
                h = h.decode('utf-8', 'ignore')
            if h:
                self._c[k] = [time.time(), h]
            return h
        except:
            return ''

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
        for blk in re.finditer(r'<li class="fed-list-item([\s\S]*?)</li>', h):
            b = blk.group(1)
            vm = re.search(r'<a class="fed-list-pics[^"]*" href="(/titlebox/(013-[A-Za-z0-9]+)\.html)" data-original="(https?://[^"]+)"', b)
            if not vm:
                continue
            vid = vm.group(2)
            if vid in seen:
                continue
            nm = re.search(r'class="fed-list-title[^"]*"[^>]*>\s*([^<]{1,80}?)\s*</a>', b)
            name = unescape(nm.group(1)).strip() if nm else ''
            rm = re.search(r'fed-list-remarks[^>]*>([^<]*)', b)
            if not name or len(name) > 80:
                continue
            seen.add(vid)
            out.append({'vod_id': vid, 'vod_name': name[:50], 'vod_pic': vm.group(3), 'vod_remarks': unescape(rm.group(1)).strip()[:20] if rm else ''})
        return out

    def homeContent(self, filter=False):
        return {'class': [{'type_id': k, 'type_name': v} for k, v in self.types.items()], 'list': self.homeVideoContent().get('list', [])}

    def homeVideoContent(self):
        h = self._get(self.base, ttl=120)
        items = self._items(h)
        if len(items) < 10:
            h2 = self._get(self.base + '/showcase/013-19.html', ttl=300)
            items = self._items(h2)
        return {'list': items[:60]}

    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        t = str(tid).split('|')[0]
        h = self._get(f'{self.base}/showcase/013-{t}.html', ttl=300)
        if not h:
            return {'page': 1, 'pagecount': 1, 'limit': 180, 'total': 0, 'list': []}
        items = self._items(h)
        return {'page': 1, 'pagecount': 1, 'limit': 180, 'total': len(items), 'list': items}

    def detailContent(self, ids, quick='1'):
        vid = str(ids[0] if isinstance(ids, list) else ids or '')
        m = re.search(r'(013-[A-Za-z0-9]+)', vid)
        vid = m.group(1) if m else ''
        if not vid:
            return {'list': []}
        h = self._get(self.base + f'/titlebox/{vid}.html', ttl=300, t=25000)
        if not h:
            return {'list': []}
        d = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_year': '', 'vod_area': '', 'vod_director': '', 'vod_actor': '', 'vod_content': '', 'vod_remarks': '', 'vod_play_from': '', 'vod_play_url': ''}
        m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', h)
        if m:
            d['vod_name'] = unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
        m = re.search(r'data-original="(https?://[^"]+)"', h)
        if m:
            d['vod_pic'] = m.group(1)
        m = re.search(r'fed-list-remarks[^>]*>([^<]*)', h)
        if m:
            d['vod_remarks'] = unescape(m.group(1)).strip()[:20]
        for k, lab in (('vod_year', '年份'), ('vod_area', '地区'), ('vod_actor', '主演'), ('vod_director', '导演')):
            m = re.search(r'<span class="fed-text-muted">' + lab + r'：</span>([\s\S]*?)</li>', h)
            if not m:
                continue
            v = re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', m.group(1)))).strip().strip('，').strip()
            d[k] = v[:200]
        m = re.search(r'<span class="fed-text-muted">简介：</span>([\s\S]*?)</div>', h)
        if m:
            c = re.sub(r'<[^>]+>', '', m.group(1))
            c = re.sub(r'更多精彩影视内容尽在6080影院（[^）]*）', '', c)
            d['vod_content'] = re.sub(r'\s+', ' ', unescape(c)).strip()[:500]
        pf, pu = self._lines(vid, h)
        if pf:
            d['vod_play_from'] = '$$$'.join(pf)
            d['vod_play_url'] = '$$$'.join(pu)
        return {'list': [d]}

    def _lines(self, vid, h):
        btns = [unescape(n).strip() for n in re.findall(r'<li class="fed-drop-btns[^"]*"[^>]*>\s*<a[^>]*>([^<]+)</a>', h)]
        skip = set(btns) | {'立即播放', ''}
        hmap = {}
        for href, sid, nid, ename in re.findall(r'href="(/playzone/(?:' + re.escape(vid) + r')-(\d+)-(\d+)\.html)"[^>]*>([^<]+)</a>', h):
            e = unescape(ename).strip()
            if not e or e in skip:
                continue
            e = e.replace('#', '-').replace('$', '|')
            if href not in hmap:
                hmap[href] = (int(sid), int(nid), e)
            elif '第' in e:
                hmap[href] = (int(sid), int(nid), e)
        g = {}
        for href, (sid, nid, e) in hmap.items():
            g.setdefault(sid, [])
            g[sid].append((nid, e, href))
        pf, pu = [], []
        for sid in sorted(g):
            ns = sorted(g[sid], key=lambda x: x[0])
            nm = btns[sid - 1] if sid - 1 < len(btns) and btns[sid - 1] else f'线路{sid}'
            pf.append(nm)
            pu.append('#'.join(f'{e}${urljoin(self.base, href)}' for _, e, href in ns))
        return pf, pu

    def searchContent(self, key, quick=False, pg='1'):
        k = str(key).strip()
        out, seen = [], set()
        for u in (self.base, *(f'{self.base}/showcase/013-{t}.html' for t in ('19', '20', '22', '23'))):
            h = self._get(u, ttl=300)
            if not h:
                continue
            for it in self._items(h):
                if it['vod_id'] in seen:
                    continue
                if k and k.lower() in it['vod_name'].lower():
                    seen.add(it['vod_id'])
                    out.append(it)
        return {'list': out[:50], 'page': 1}

    def playerContent(self, flag, id, vipFlags=None):
        u = str(id) if id else str(flag)
        if '://' in u and re.search(r'\.(m3u8|mp4|flv)(\?|$)', u, re.I):
            return {'parse': 0, 'url': self._enc(u)}
        full = u if u.startswith('http') else urljoin(self.base, u)
        h = self._get(full, ttl=120, t=25000)
        if not h:
            return {'parse': 0, 'url': ''}
        m = re.search(r'"url":"((?:[^"\\]|\\.)*)"', h)
        if m:
            try:
                u = json.loads('"' + m.group(1) + '"')
                if u:
                    return {'parse': 0, 'url': self._enc(u)}
            except:
                pass
        m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', h)
        if m:
            return {'parse': 0, 'url': self._enc(m.group(1))}
        return {'parse': 0, 'url': ''}

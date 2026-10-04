# -*- coding: utf-8 -*-
# 八度影院 h.sdgtrl.com | MacCMS v10魔改(拼音分类/films详情/vodlist播放) | 71us v7.3定制 | 必须安卓UA
import sys, re, json, hashlib, time
from urllib.parse import urljoin, quote, unquote
import requests

try:
    requests.packages.urllib3.disable_warnings()
except:
    pass

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

HOSTS = ['https://h.sdgtrl.com']
UA = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
CATEGORIES = {
    'dianying': '电影', 'dianshiju': '电视剧', 'zongyi': '综艺', 'dongman': '动漫',
    'fanzuipian': '犯罪片', 'xijupian': '喜剧片', 'dongzuopian': '动作片', 'aiqingpian': '爱情片',
    'kehuanpian': '科幻片', 'kongbupian': '恐怖片', 'juqingpian': '剧情片', 'zhanzhengpian': '战争片',
    'jingsongpian': '惊悚片', 'jiatingpian': '家庭片', 'guzhangpian': '古装片', 'lishipian': '历史片',
    'xianyipian': '悬疑片', 'zainanpian': '灾难片', 'jilupian': '纪录片', 'donghuapian': '动画片',
    'rihan': '日韩', 'guochanju': '国产剧', 'xianggangju': '香港剧', 'hanguoju': '韩国剧',
    'oumeiju': '欧美剧', 'taiwanju': '台湾剧', 'ribenju': '日本剧', 'haiwaiju': '海外剧',
    'taiguoju': '泰国剧', 'duanju': '短剧'}


class Spider(Spider):
    def init(self, extend=''):
        self.base = HOSTS[0].rstrip('/')
        self.ua = UA
        self.types = dict(CATEGORIES)
        try:
            h = self._get(self.base)
            if not h:
                return
            ts = {}
            for m in re.finditer(r'<a href="/vod/([a-z0-9]+)\.html"[^>]*>\s*<span[^>]*>([^<]+)</span>', h):
                name = m.group(2).strip()
                if name and name != '理论' and name != '伦理片':
                    ts.setdefault(m.group(1), name)
            if len(ts) >= 4:
                self.types = {k: v for k, v in self.types.items() if k in ts} or self.types
        except:
            pass

    def _get(self, url, headers=None, timeout=15000):
        last = ''
        for u in [url] + ([url.replace(self.base, h.rstrip('/'), 1) for h in HOSTS if h.rstrip('/') != self.base and url.startswith(self.base)]):
            try:
                hs = headers or {'User-Agent': self.ua, 'Referer': self.base}
                try:
                    r = self.fetch(u, headers=hs, timeout=timeout)
                except TypeError:
                    r = self.fetch(u, headers=hs)
                last = r.text if hasattr(r, 'text') else str(r)
                if last:
                    return last
            except:
                try:
                    rr = requests.get(u, headers=hs, timeout=max(timeout / 1000.0, 10), verify=False)
                    last = rr.text
                    if last:
                        return last
                except:
                    pass
        return last

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
        for m in re.finditer(r'page=(\d+)', h):
            try:
                n = int(m.group(1))
                if n > mx:
                    mx = n
            except:
                pass
        if re.search(r'下一页', h):
            mx = max(mx, cur + 1)
        return mx

    def _items(self, h, drop=False):
        items, seen = [], set()
        for m in re.finditer(r'<a[^>]*?href="/films/(\d+)\.html"[^>]*?>', h):
            tag = m.group(0)
            tm = re.search(r'title="([^"]+)"', tag)
            if not tm or m.group(1) in seen:
                continue
            pic = ''
            dm = re.search(r'data-original="([^"]+)"', tag)
            if dm:
                pic = dm.group(1)
            else:
                sm = re.search(r'style="([^"]*)"', tag)
                if sm:
                    pm = re.search(r'(/upload/[^"\')&\s]+\.(?:jpe?g|png|webp)|https?://[^"\')&\s]+\.(?:jpe?g|png|webp))', sm.group(1), re.I)
                    if pm:
                        pic = pm.group(1)
            if drop and not pic:
                continue
            remark = ''
            rm = re.search(r'<span[^>]*class="[^"]*(?:pic-text|pic-tag)[^"]*"[^>]*>([^<]+)<', h[m.end():m.end() + 300])
            if rm:
                remark = rm.group(1).strip()
            seen.add(m.group(1))
            items.append({'vod_id': m.group(1), 'vod_name': tm.group(1).strip()[:80], 'vod_pic': self._pic(pic), 'vod_remarks': remark})
        return items

    def homeContent(self, filter=False):
        r = {'class': [{'type_id': k, 'type_name': v} for k, v in self.types.items()]}
        r['list'] = self.homeVideoContent().get('list', [])
        return r

    def homeVideoContent(self):
        h = self._get(self.base)
        return {'list': self._items(h, True) if h else []}

    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        try:
            pn = max(int(str(pg)), 1)
        except:
            pn = 1
        t2 = str(tid).split('|')[0].split('$')[0]
        url = f'{self.base}/stars/{t2}.html' if t2 == 'duanju' else f'{self.base}/vod/{t2}.html'
        h = self._get(f'{url}?page={pn}')
        if not h:
            return {'page': pn, 'pagecount': 1, 'limit': 42, 'total': 0, 'list': []}
        idx = h.find('stui-vodlist clearfix')
        if idx > 0:
            h = h[idx:]
        items = self._items(h)
        return {'page': pn, 'pagecount': self._pagecount(h, pn), 'limit': 42, 'total': len(items), 'list': items}

    def detailContent(self, ids, quick='1'):
        vid = str(ids[0] if isinstance(ids, list) else ids or '')
        m = re.search(r'(\d+)', vid)
        vid = m.group(1) if m else ''
        if not vid:
            return {'list': []}
        h = self._get(f'{self.base}/films/{vid}.html')
        if not h:
            return {'list': []}
        d = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_year': '', 'vod_area': '',
             'vod_class': '', 'vod_director': '', 'vod_actor': '', 'vod_content': '',
             'vod_remarks': '', 'vod_play_from': '', 'vod_play_url': ''}
        tn = re.search(r'<h1[^>]*>\s*<a[^>]*title="([^"]+)"', h) or re.search(r'<title>(.*?)</title>', h)
        if tn:
            d['vod_name'] = re.sub(r'[《》]', '', tn.group(1).split('-')[0]).replace('免费在线观看', '').replace('高清完整版', '').strip()
        pm = re.search(r'<div[^>]*class="[^"]*stui-content__thumb[^"]*"[^>]*>[\s\S]*?<img[^>]*src="([^"]+)"', h)
        if pm:
            d['vod_pic'] = self._pic(pm.group(1))
        for pm in re.finditer(r'<p[^>]*class="[^"]*\bdata\b[^"]*"[^>]*>([\s\S]*?)</p>', h):
            t = re.sub(r'<[^>]+>', '', pm.group(1)).replace('&nbsp;', '').replace('\xa0', '').strip(' ：:')
            for k, kk in (('vod_year', '年代'), ('vod_director', '导演'), ('vod_actor', '演员'), ('vod_area', '地区'), ('vod_remarks', '状态')):
                if not d[k] and t.startswith(kk):
                    d[k] = t[len(kk):].strip(' ：:').strip()
        dc = re.search(r'<span[^>]*class="[^"]*detail-sketch[^"]*"[^>]*>([\s\S]*?)</span>', h)
        if dc:
            d['vod_content'] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', dc.group(1)).replace('&nbsp;', ' ')).strip()[:500]
        uls = re.findall(r'<ul[^>]*class="[^"]*stui-content__playlist[^"]*"[^>]*>([\s\S]*?)</ul>', h)
        pf, pu = [], []
        for i, uu in enumerate(uls):
            eps = re.findall(r'href="(/vodlist/[^"]+)"[^>]*>\s*([^<]+?)\s*</a>', uu)
            if eps:
                pf.append('wjm3u8' if i == 0 else f'线路{i + 1}')
                pu.append('#'.join(f'{t.strip().replace("#", "-").replace("$", "|")}${urljoin(self.base, u)}' for u, t in eps))
        if pf:
            d['vod_play_from'] = '$$$'.join(pf)
            d['vod_play_url'] = '$$$'.join(pu)
        return {'list': [d]}

    def searchContent(self, key, quick=False, pg='1'):
        try:
            pn = max(int(str(pg)), 1)
        except:
            pn = 1
        h = self._get(f'{self.base}/mosr?wd={quote(key)}&page={pn}', timeout=30000)
        if not h:
            return {'list': [], 'page': pn}
        idx = h.find('stui-vodlist__media')
        if idx > 0:
            end = h.find('</ul>', idx)
            if end > 0:
                h = h[idx:end]
        return {'list': self._items(h, True), 'page': pn}

    def playerContent(self, flag, id, vipFlags=None):
        url = str(id) if id else str(flag)
        if '://' in url and re.search(r'\.(m3u8|mp4|flv|mp3)(\?|$)', url, re.I):
            return {'parse': 0, 'url': url}
        full = url if url.startswith('http') else urljoin(self.base, url)
        h = self._get(full)
        if not h:
            return {'parse': 0, 'url': ''}
        return {'parse': 0, 'url': self._parse_play(h)}

    def _parse_play(self, h):
        for key in ('player_data', 'player_aaaa'):
            pd = re.search(r'var\s+%s\s*=\s*(\{[\s\S]*?\})\s*[;<]' % key, h)
            if pd:
                try:
                    u = json.loads(pd.group(1)).get('url', '')
                    if u:
                        u = u.replace('\\/', '/')
                        if re.search(r'\.(m3u8|mp4|flv)(\?|$)', u, re.I):
                            return u
                except:
                    pass
        m = re.search(r'var\s*(?:now|url)\s*=\s*["\']([^"\']+)["\']', h)
        if m and re.search(r'\.(m3u8|mp4|flv)(\?|$)', m.group(1), re.I):
            return m.group(1)
        fm = re.search(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4|flv))', h)
        if fm:
            return fm.group(1)
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', h, re.I)
        if iframe:
            u = iframe.group(1)
            if u.startswith('http'):
                h2 = self._get(u)
                if h2:
                    return self._parse_play(h2)
        return ''

    def localProxy(self, param):
        p = param.split('url=', 1)[-1] if 'url=' in param else param
        p = unquote(p) if '%' in p else p
        if re.search(r'\.(jpe?g|png|webp|gif)(\?|$)', p, re.I):
            try:
                r = requests.get(p, headers={'User-Agent': self.ua, 'Referer': self.base}, timeout=15)
                return {'code': r.status_code, 'content': r.content, 'headers': {'Content-Type': r.headers.get('Content-Type', 'image/jpeg')}}
            except:
                return {'code': 404, 'content': b'', 'headers': {}}
        if '.m3u8' in p:
            return self._rewrite_m3u8(p)
        try:
            try:
                r = self.fetch(p, headers={'User-Agent': self.ua, 'Referer': self.base}, timeout=20000)
            except TypeError:
                r = self.fetch(p, headers={'User-Agent': self.ua, 'Referer': self.base})
            if hasattr(r, 'status_code') and r.status_code != 200:
                return {'code': r.status_code, 'content': b'', 'headers': {}}
            return {'code': 200, 'content': r.content, 'headers': {'Content-Type': r.headers.get('Content-Type', 'application/octet-stream')}}
        except:
            return {'code': 404, 'content': b'', 'headers': {}}

    def _rewrite_m3u8(self, url):
        try:
            try:
                r = self.fetch(url, headers={'User-Agent': self.ua, 'Referer': self.base}, timeout=20000)
            except TypeError:
                r = self.fetch(url, headers={'User-Agent': self.ua, 'Referer': self.base})
            if hasattr(r, 'status_code') and r.status_code != 200:
                return {'code': r.status_code, 'content': b'', 'headers': {}}
            body = r.text if hasattr(r, 'text') else str(r)
        except:
            return {'code': 404, 'content': b'', 'headers': {}}
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
        return {'code': 200, 'content': '\n'.join(out), 'headers': {'Content-Type': 'application/vnd.apple.mpegurl'}}
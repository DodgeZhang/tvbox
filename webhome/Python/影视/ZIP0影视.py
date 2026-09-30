# -*- coding: utf-8 -*-
# ============ ZIP0 影视聚合源 v1.2 ============
# 基于71us模板v7.5套写 | 2026-09-11
# 站点: https://zip0.com | Next.js 聚合搜索站(不存片, 聚合多线路公开源)
# 数据: 热播 /api/danmaku-rooms | 分类+搜索 /api/videos/search?query= | 详情 /watch SSR(episodes真m3u8)
# v1.1修复: ①分类走query真分页(原忽略tid) ②详情并行抓全线路真m3u8直填(原watch假地址致每次播放重抓页卡顿) ③多线路=同名片名多source并联(实测单片最多10线)
# v1.2修复: 列表海报不显示(站点搜索/分类接口无image字段→watch页SSR取真海报→127.0.0.1本地服务器懒加载中转,webp自动转jpeg,失败302兜底og.png)
# 13接口=init/homeContent/categoryContent/detailContent/searchContent/playerContent/localProxy/isVideoFormat/manualVideoCheck/getDependence/destroy/progressVideo/setVideoFlags
# ★版本兼容铁律: 全文件禁3.9+API(random.randbytes/removeprefix/removesuffix等)
# ★分隔符铁律: $=名称/地址 | #=选集 | $$$=线路; 线路名与地址$$$段数必须相等
# ★链路策略v4: 资源默认直连输出, 仅403/防盗链/KEY404/需特殊头才走 localProxy 兜底
import sys, re, json, time, base64, hashlib, threading, http.server, socket, struct
from urllib.parse import urljoin, quote, unquote
from concurrent.futures import ThreadPoolExecutor
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

# ============ ★ CONFIG ============
HOSTS = ['https://zip0.com']  # ★ 多域名轮询(主在前), 防封容灾
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
CATEGORIES = {'1': '电影', '2': '电视剧', '3': '综艺', '4': '动漫', '5': '短剧', '6': '纪录片', '7': '体育'}
LIMIT = 42  # ★ 每页条数
POOL_PAGES = 5  # ★ 分类建池拉取页数(站点limit上限50)
CAT_QUERY = {'1': '电影', '2': '电视剧', '3': '综艺', '4': '动漫', '5': '短剧', '6': '纪录片', '7': '体育'}  # ★ 分类→搜索query映射(站点无分类API)
CAT_EXTRA = {'1': ['片', '动作', '恐怖', '喜剧'], '2': ['电视', '日漫', '恐怖', '连续剧', '喜剧'],
             '3': ['电视', '秀', '喜剧', '纪录', '球'], '4': ['动画', '番', '日漫', '漫', '国漫'],
             '5': ['剧', '漫', '集', '综艺'], '6': ['纪录', '恐怖', '动作'], '7': ['赛', '球', '纪', '解说']}  # ★ probe14/15/16实测有效子词(按category归桶)
POOL_MAX = 200  # ★ 分类池最大条数
SRC_NAME = {'bfzy': '暴风', 'dyttzy': '天堂', 'zy360': '360', 'lzi': '量子', 'ruyi': '如意', 'ffzy': '非凡', 'jisu': '极速', 'mdzy': '木偶', 'zuid': '最大', 'ikun': 'ikun'}  # ★ source→中文名
PK = ''  # ★ 接口密钥(签名/AES key/解密用)
REFERER = 'https://zip0.com/'  # ★ 播放/资源防盗链Referer(空=用self.base)
PIC_REFERER = 'https://zip0.com/'  # ★ 图片防盗链Referer(空=无)
FD_ZONE = 0  # ★ 分片区段(71us .fd 协议用, 无则0)
PROBE = 0  # ★ 详情多线路实测排序开关 1/0
SITE_KEY = 'zip0'  # ★ 壳源标识(海阔setVideoFlags回调时上报, 调试多源用)
VIDEO_EXTS = 'm3u8|mp4|flv|mkv|avi|ts'  # ★ isVideoFormat判定扩展名(竖线分隔)

class Spider(Spider):
    def init(self, extend=''):
        self.base = HOSTS[0].rstrip('/')  # ★ 主域(init内可被重定向更新)
        self.ua = UA
        self.pk = PK
        self.ref = REFERER or self.base
        self.types = dict(CATEGORIES)
        self.filters = {}  # ★ {'1':[{'key':'class','name':'类型','value':[{'n':'剧情','v':'剧情'}]}]}
        self._c = {}  # 详情缓存 {md5:[ts,data]}
        self._pc = {}  # 线路probe缓存
        self._last_ps = ''  # 最近一次播放页(缓存未命中兜底)
        self._srv = None  # 本地图片服务器(延迟启动)
        self._sport = 0  # 本地图片服务器端口
        self._pm = {}  # 海报URL缓存 {source|id: [ts, url]}
        self._plock = threading.Lock()  # 服务器启动锁
        self._psem = threading.Semaphore(6)  # 上游海报抓取并发上限
        try:
            r = self.fetch(self.base, headers={'User-Agent': self.ua}, timeout=10000)
            if hasattr(r, 'url') and r.url and r.url != self.base:
                self.base = r.url.rstrip('/')
        except:
            pass

    # ========== 容灾: 多HOST轮询 + requests双保险 ==========
    def _get(self, url, headers=None, timeout=15000):
        hd = headers or {'User-Agent': self.ua, 'Referer': self.ref}
        try:
            r = self.fetch(url, headers=hd, timeout=timeout)
        except TypeError:
            try:
                r = self.fetch(url, headers=hd)
            except Exception:
                return ''
        except Exception:
            return ''
        try:
            return r.text if hasattr(r, 'text') else str(r)
        except Exception:
            return ''

    def _raw(self, url, timeout=20):
        try:
            r = requests.get(url, headers={'User-Agent': self.ua, 'Referer': self.ref}, timeout=timeout)
            r.encoding = 'utf-8'
            return r.text if r.status_code == 200 else ''
        except:
            return ''

    def _pic(self, u):
        if not u:
            return ''
        if u.startswith('//'):
            u = 'https:' + u
        return u  # 直连优先; 403时 playerContent/localProxy 兜底

    # ========== 首页 ==========
    def homeContent(self, filter=False):
        r = {'class': [{'type_id': k, 'type_name': v} for k, v in self.types.items()]}
        if filter and self.filters:
            r['filters'] = self.filters
        r['list'] = self.homeVideoContent().get('list', [])
        return r

    def homeVideoContent(self):
        # ★ zip0: 正在热播 API(带海报)
        items = []
        try:
            h = self._get(self.base + '/api/danmaku-rooms')
            j = json.loads(h or '{}')
            seen = set()
            for it in (j.get('rooms') or []):
                m = re.search(r'source=([^&]+)&id=(\d+)', it.get('href', '') or '')
                nm = re.sub(r'\s+', ' ', it.get('title', '') or '').strip()
                if not m or not nm or nm in seen:
                    continue
                seen.add(nm)
                items.append({'vod_id': m.group(1) + '|' + m.group(2), 'vod_name': nm[:50],
                              'vod_pic': self._pic(it.get('image', '')), 'vod_remarks': (it.get('subtitle') or '').strip()})
                if len(items) >= 60:
                    break
        except:
            pass
        return {'list': items}

    # ========== 分类(★v1.1b: 建池+category归桶+本地分页, 杜绝混类) ==========
    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        try:
            pn = max(int(str(pg)), 1)
        except:
            pn = 1
        pool = self._pool(tid)
        if isinstance(extend, dict):
            for k, f in (('class', 'vod_type'), ('type', 'vod_type'), ('area', 'vod_area'), ('year', 'vod_year')):
                v = (extend.get(k) or '') if extend else ''
                if v and v != '全部':
                    pool = [x for x in pool if v in str(x.get(f, ''))]
                    break
        ln = len(pool)
        st = (pn - 1) * LIMIT
        return {'page': pn, 'pagecount': max((ln + LIMIT - 1) // LIMIT, 1), 'limit': LIMIT, 'total': ln, 'list': pool[st:st + LIMIT]}

    def _bucket(self, cat):
        c = str(cat or '')
        if any(k in c for k in ('短剧', '漫剧', '爽剧', '长剧')):
            return 5
        if any(k in c for k in ('综艺', '真人秀', '脱口秀', '晚会', '盛典', '音乐', '歌舞')):
            return 3
        if any(k in c for k in ('体育', '赛事', '足球', '篮球', '网球', '排球', '格斗', '运动', '电竞')):
            return 7
        if '纪录' in c or '记录' in c:
            return 6
        if '动漫' in c or '动画' in c:
            return 4
        if '片' in c or c.startswith('电影'):
            return 1
        if '剧' in c:
            return 2
        return 0

    # ========== 分类池: 主query+子query并行拉取, category归桶过滤, 1800s缓存 ==========
    def _fetch(self, q, pages):
        out = []
        for pn in range(1, max(int(pages), 1) + 1):
            data, pgs, _t = self._api(q, pn, 50)
            if not data:
                break
            out.extend(data)
            if pn >= pgs:
                break
        return out

    def _pool(self, tid):
        tid = str(tid)
        ck = 'pool|' + tid
        c = self._c.get(ck)
        if c and time.time() - c[0] < 1800:
            return c[1]
        main = self.types.get(tid) or CAT_QUERY.get(tid) or '电影'
        try:
            want = int(tid)
        except:
            want = 0
        qs = [(main, POOL_PAGES)] + [(x, 1) for x in CAT_EXTRA.get(tid, [])]
        try:
            with ThreadPoolExecutor(max_workers=min(len(qs), 6)) as ex:
                chunks = list(ex.map(lambda p: self._fetch(p[0], p[1]), qs))
        except:
            chunks = [self._fetch(a, b) for a, b in qs]
        seen, hit, unk = set(), [], []
        for lst in chunks:
            for it in lst:
                r = self._row(it, seen)
                if not r:
                    continue
                b = self._bucket(it.get('category'))
                if b == want:
                    hit.append(r)
                elif b == 0:
                    unk.append(r)
        out = hit if hit else unk
        out.sort(key=lambda x: x.get('vod_year') or '', reverse=True)
        out = out[:POOL_MAX]
        self._c[ck] = (time.time(), out)
        return out

    # ========== 搜索接口封装(站点limit硬上限50) ==========
    def _api(self, q, pn=1, lim=50):
        lim = min(max(int(lim or 50), 1), 50)
        j = {}
        for _try in range(2):
            try:
                j = json.loads(self._get(self.base + '/api/videos/search?query=' + quote(q) + '&page=' + str(max(int(pn), 1)) + '&limit=' + str(lim), timeout=25000) or '{}')
            except:
                j = {}
            if j.get('data'):
                break
            if _try == 0:
                time.sleep(1)
        pg = j.get('pagination') or {}
        try:
            return (j.get('data') or []), int(pg.get('pages') or 1), int(pg.get('total') or 0)
        except:
            return (j.get('data') or []), 1, 0

    def _row(self, it, seen):
        m = re.search(r'source=([^&]+)&id=(\d+)', it.get('url', '') or '')
        nm = re.sub(r'\s+', ' ', it.get('title', '') or '').strip()
        if not m or not nm or nm in seen:  # ★ 同名多线路在列表位合并为一张卡
            return None
        seen.add(nm)
        rk = (it.get('remarks') or '').strip()
        if not rk:
            ec = it.get('episodeCount') or 0
            rk = ('共' + str(ec) + '集') if ec and ec > 1 else (str(it.get('year') or ''))
        pic = self._pic(it.get('image') or it.get('poster') or it.get('cover') or '')
        if not pic:
            pic = self._spic(m.group(1), m.group(2))
        return {'vod_id': m.group(1) + '|' + m.group(2), 'vod_name': nm[:50],
                'vod_pic': pic,
                'vod_remarks': rk[:30], 'vod_year': str(it.get('year') or ''), 'vod_area': str(it.get('area') or ''),
                'vod_type': str(it.get('category') or '')}

    # ========== 搜索/列表行(分类与搜索共用) ==========
    def _search(self, q, pn=1):
        data, pages, total = self._api(q, pn, LIMIT)
        seen, items = set(), []
        for it in data:
            r = self._row(it, seen)
            if r:
                items.append(r)
        return items, pages, total

    # ========== 详情(★v1.1: 并行抓全线路真m3u8, 一次装填, 播放零重抓) ==========
    def detailContent(self, ids, quick='1'):
        vid = str(ids[0] if isinstance(ids, list) else ids or '')
        m = re.match(r'([A-Za-z0-9_\-]+)\|(\d+)', vid)
        if not m:
            return {'list': []}
        key = hashlib.md5(vid.encode()).hexdigest()
        c = self._c.get(key)
        if c and time.time() - c[0] < 900:
            return {'list': [c[1]]}
        src_, rid = m.group(1), m.group(2)
        wu = self.base + '/watch?source=' + quote(src_) + '&id=' + rid + '&episode=1'
        h0 = self._get(wu, timeout=30000) or self._raw(wu, 30)
        if not h0:
            time.sleep(1.0)
            h0 = self._get(wu, timeout=30000) or self._raw(wu, 30)
        if not h0:
            return {'list': []}
        title = self._ssr(h0, 'title') or re.sub(r'<[^>]+>', '', (re.search(r'<h1[^>]*>([\s\S]{0,90}?)</h1>', h0).group(1) if re.search(r'<h1[^>]*>([\s\S]{0,90}?)</h1>', h0) else '')).strip()
        d = {'vod_id': vid, 'vod_name': title, 'vod_pic': self._pic(self._ssr(h0, 'poster')),
             'vod_year': self._ssr(h0, 'year'), 'vod_area': self._ssr(h0, 'area'),
             'vod_class': self._ssr(h0, 'category'), 'vod_director': self._ssr(h0, 'director'),
             'vod_actor': self._ssr(h0, 'actors').replace(',', '、'), 'vod_content': re.sub(r'\s+', ' ', self._ssr(h0, 'description'))[:480],
             'vod_remarks': self._ssr(h0, 'sourceName') or '', 'vod_play_from': '', 'vod_play_url': ''}
        cands = [(src_, rid)]
        nm_key = re.sub(r'\s+', '', title).lower()
        if nm_key:
            try:
                su = self.base + '/api/videos/search?query=' + quote(title) + '&page=1&limit=50'
                hj = ''
                for _ta in range(3):
                    hj = self._get(su, timeout=20000) or self._raw(su, 20)
                    if '"data"' in hj:
                        break
                    time.sleep(1.0 + _ta)
                for it in (json.loads(hj or '{}').get('data') or []):
                    if re.sub(r'\s+', '', it.get('title', '')).lower() != nm_key:
                        continue
                    mm = re.search(r'source=([^&]+)&id=(\d+)', it.get('url', '') or '')
                    if mm and (mm.group(1), mm.group(2)) not in cands:
                        cands.append((mm.group(1), mm.group(2)))
                    if len(cands) >= 12:
                        break
            except:
                pass
        rows = []
        if len(cands) == 1:
            rows = [self._line(src_, rid, h0)]
        else:
            try:
                with ThreadPoolExecutor(max_workers=min(len(cands), 8)) as ex:
                    rows = list(ex.map(lambda cp: self._line(cp[0], cp[1], None), cands))
            except:
                rows = [self._line(*c) for c in cands]
        best, order = {}, []
        for src, snm, eps in rows:
            if not eps:
                continue
            if src not in best or len(eps) > len(best[src][2]):
                if src not in best:
                    order.append(src)
                best[src] = (src, snm, eps)
        if vid and src_ not in best and h0:
            one = self._line(src_, rid, h0)
            if one[2]:
                best[src_] = one
                order.insert(0, src_)
        froms, urls = [], []
        for src in sorted(order, key=lambda s: self._line_no(best[s][1])):
            snm, eps = best[src][1], best[src][2]
            fn = SRC_NAME.get(src) or re.sub(r'[$#|]', '', snm or src) or src
            if fn in froms:
                fn = fn + str(len(froms) + 1)
            froms.append(fn)
            seg = []
            for i, (en, eu) in enumerate(eps):
                en = re.sub(r'[$#|]', '-', (en or ('第' + str(i + 1) + '集')))[:24]
                seg.append(en + '$' + eu)
            urls.append('#'.join(seg))
        if froms:
            d['vod_play_from'] = '$$$'.join(froms)
            d['vod_play_url'] = '$$$'.join(urls)
            self._last_ps = self.base + '/watch?source=' + quote(order[0]) + '&id=' + str(cands[0][1]) + '&episode=1'
        if not d['vod_name']:
            d['vod_name'] = vid
        self._c[key] = [time.time(), d]
        return {'list': [d]}

    @staticmethod
    def _line_no(nm):
        m = re.search(r'(\d+)', nm or '')
        return int(m.group(1)) if m else 99

    @staticmethod
    def _ssr(h, k):
        m = re.search('[,{]' + k + r':"([^"]*)"', h or '')
        return m.group(1) if m else ''

    def _line(self, src, rid, cached):
        wu = self.base + '/watch?source=' + quote(src) + '&id=' + rid + '&episode=1'
        h = cached if cached else (self._get(wu, timeout=25000) or self._raw(wu, 25))
        if not h and not cached:
            time.sleep(0.8)
            h = self._get(wu, timeout=25000) or self._raw(wu, 25)
        if not h:
            return src, '', []
        return src, self._ssr(h, 'sourceName'), self._eps(h)

    def _eps(self, h):
        out, seen = [], set()
        i = (h or '').find('episodes:')
        seg = h[i:i + 24000] if i > 0 else (h or '')
        for en, eu in re.findall(r'name:"([^"]{1,30})",url:"(https?://[^"]{10,600})"', seg):
            if eu in seen or not re.search(r'\.(m3u8|mp4|flv|ts)(\?|$)', eu, re.I):
                continue
            seen.add(eu)
            out.append((en, eu))
        if out:
            return out
        for eu in re.findall(r'(https?://[^"\'\s<>]+?\.m3u8[^"\'\s<>]*)', h or ''):
            if eu in seen:
                continue
            seen.add(eu)
            out.append(('第' + str(len(out) + 1) + '集', eu))
            if len(out) >= 120:
                break
        return out

    # ========== 搜索 ==========
    def searchContent(self, key, quick=False, pg='1'):
        try:
            pn = max(int(str(pg)), 1)
        except:
            pn = 1
        items, pages, total = self._search(str(key), pn)
        if not items and pn == 1:
            items, pages, total = self._search(re.sub(r'(电影|电视剧|综艺|动漫|短剧|纪录片|连续剧|片)$', '', str(key)).strip() or str(key), 1)
        return {'list': items, 'page': pn, 'pagecount': max(pages, 1), 'total': total}

    def playerContent(self, flag, id, vipFlags=None):
        # ★ v1.1: 选集已是真m3u8 → 直出, 不再重抓watch页
        u = str(id or '').strip()
        if not u:
            u = str(flag or '').strip()
        if '$' in u:
            t = u.rsplit('$', 1)[-1].strip()
            if t.startswith('http'):
                u = t
        if u.startswith('http') and re.search(r'\.(m3u8|mp4|flv|ts|mkv)(\?|$)', u, re.I):
            return {'parse': 0, 'playUrl': '', 'url': u, 'header': self._hd(u)}
        m = re.match(r'([A-Za-z0-9_\-]+)\|(\d+)\|(\d+)', u)
        if m:
            u = self.base + '/watch?source=' + quote(m.group(1)) + '&id=' + m.group(2) + '&episode=' + m.group(3)
        if not u.startswith('http'):
            u = urljoin(self.base + '/', u)
        if not u.startswith('http'):
            return {'parse': 0, 'playUrl': '', 'url': ''}
        self._last_ps = u
        h = self._get(u, timeout=35000) or self._raw(u, 35)
        pu = self._parse_play(h or '', u)
        if not pu:
            pu = self._vip_try(u, h or '', vipFlags)
        if pu and re.search(r'\.(m3u8|mp4|flv|ts)(\?|$)', pu, re.I):
            return {'parse': 0, 'playUrl': '', 'url': pu, 'header': self._hd(pu)}
        return {'parse': 0, 'playUrl': '', 'url': pu or ''}

    def _hd(self, u):
        o = re.match(r'https?://[^/]+', u)
        return {'User-Agent': self.ua, 'Referer': (o.group(0) + '/' if o else self.ref)}

    def _parse_play(self, h, page_url):
        # ★ zip0 watch 页 SSR: episodes:[{name:"第01集",url:"...m3u8"}]
        eps = self._eps(h)
        if eps:
            return eps[0][1]
        pd = re.search(r'player_data\s*=\s*(\{[\s\S]*?\})\s*[;<]', h)
        if pd:
            try:
                u = json.loads(pd.group(1)).get('url', '')
                if u:
                    u2 = self._dec(u, page_url)
                    if u2:
                        return u2
            except:
                pass
        m = re.search(r'var\s*(?:now|url)\s*=\s*["\']([^"\']+)["\']', h)
        if m:
            u2 = self._dec(m.group(1), page_url)
            if u2:
                return u2
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', h, re.I)
        if iframe:
            u = iframe.group(1)
            if u.startswith('http'):
                h2 = self._get(u) or self._raw(u)
                if h2:
                    return self._parse_play(h2, u)
        return ''

    def _dec(self, u, page_url):
        u = u.strip()
        if re.search(r'\.(m3u8|mp4|flv)(\?|$)', u, re.I):
            return u
        try:  # base64
            s = u.encode()
            s2 = base64.b64decode(s + b'=' * (-len(s) % 4)).decode('utf-8', 'ignore')
            if re.search(r'\.(m3u8|mp4|flv)(\?|$)', s2, re.I):
                return s2
        except:
            pass
        # ★ AES-CBC 解密插槽: aes_cbc(base64.b64decode(s2), key, iv, 0)
        return u if u.startswith('http') else ''

    def _vip_try(self, page_url, h, vipFlags):
        # ★ 模板插槽: 会员能破则破(拼token/签名/老接口); 服务端硬锁返回''
        return ''

    # ========== 四壳13接口扩展钩子(v7.5) ==========
    def isVideoFormat(self, url):
        if not url:
            return False
        if '.m3u8' in url:
            return True
        return bool(re.search(r'\.(?:%s)(?:\?|$)' % (VIDEO_EXTS or 'm3u8|mp4|flv'), url, re.I))
    def manualVideoCheck(self):
        return False
    def getDependence(self):
        return ''
    def destroy(self):
        try:
            if self._srv:
                self._srv.shutdown()
                self._srv.server_close()
        except Exception:
            pass
        try:
            self._c.clear()
            self._pc.clear()
            self._pm.clear()
            self._srv = None
        except Exception:
            pass
    def progressVideo(self, speed, time, end):
        return False
    def setVideoFlags(self, siteKey, flags):
        try:
            self._siteKey = siteKey or SITE_KEY
            self._vflags = flags or {}
        except Exception:
            pass
    # ========== 列表海报: watch页SSR取图 + 127.0.0.1服务器懒加载中转(站点列表无图) ==========
    def _poster(self, src, rid):
        ck = str(src) + '|' + str(rid)
        c = self._pm.get(ck)
        if c and time.time() - c[0] < (86400 if c[1] else 600):
            return c[1]
        u = ''
        with self._psem:
            try:
                wu = self.base + '/watch?source=' + quote(str(src), safe='') + '&id=' + str(rid) + '&episode=1'
                h = self._get(wu, timeout=10000) or self._raw(wu, 10)
                if h:
                    m = re.search(r'<img[^>]+src="(https?://[^"]+?\.(?:webp|jpe?g|png|gif)[^"]*)"', h)
                    if not m:
                        m = re.search(r'poster:"([^"]+)"', h)
                    if m:
                        u = m.group(1).replace('\\u0026', '&').replace('&amp;', '&')
            except:
                u = ''
        if len(self._pm) > 3000:
            self._pm.clear()
        self._pm[ck] = (time.time(), u)
        return u

    def _psrv(self):
        if self._srv:
            return True
        with self._plock:
            if self._srv:
                return True
            api = self

            class _H(http.server.BaseHTTPRequestHandler):
                def log_message(self, *a):
                    pass

                def do_GET(self):
                    try:
                        q = self.path.split('?', 1)[1] if '?' in self.path else ''
                        pr = {}
                        for kv in q.split('&'):
                            if '=' in kv:
                                k, v = kv.split('=', 1)
                                pr[k] = unquote(v)
                        u = api._poster(pr.get('src', ''), pr.get('id', '')) if pr.get('src') and pr.get('id') else ''
                        data, ct = b'', ''
                        if u:
                            try:
                                r = requests.get(u, headers={'User-Agent': api.ua}, timeout=10)
                                data, ct = r.content, r.headers.get('Content-Type', 'image/jpeg')
                                if data[:4] == b'RIFF' or 'webp' in ct:
                                    try:
                                        from PIL import Image
                                        import io
                                        buf = io.BytesIO()
                                        Image.open(io.BytesIO(data)).convert('RGB').save(buf, 'JPEG', quality=85)
                                        data, ct = buf.getvalue(), 'image/jpeg'
                                    except:
                                        ct = 'image/webp'
                            except:
                                data, ct = b'', ''
                        if not data:
                            self.send_response(302)
                            self.send_header('Location', api.base + '/og.png')
                            self.end_headers()
                            return
                        self.send_response(200)
                        self.send_header('Content-Type', ct or 'image/jpeg')
                        self.send_header('Content-Length', str(len(data)))
                        self.send_header('Cache-Control', 'max-age=86400')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(data)
                    except Exception:
                        try:
                            self.send_response(404)
                            self.end_headers()
                        except Exception:
                            pass

            for port in range(9978, 9996):
                try:
                    srv = http.server.ThreadingHTTPServer(('127.0.0.1', port), _H)
                    srv.daemon_threads = True
                    threading.Thread(target=srv.serve_forever, daemon=True).start()
                    self._srv = srv
                    self._sport = port
                    return True
                except:
                    continue
            return False

    def _spic(self, src, rid):
        if not self._psrv():
            return ''
        return 'http://127.0.0.1:' + str(self._sport) + '/zp?src=' + quote(str(src), safe='') + '&id=' + str(rid)

    # ========== 本地代理: m3u8 KEY/分片重写 + 图片转码 ==========
    def localProxy(self, param):
        p = param.split('url=', 1)[-1] if 'url=' in param else param
        p = unquote(p) if '%' in p else p
        if re.search(r'\.(jpe?g|png|webp|gif)(\?|$)', p, re.I):
            return self._img(p)
        if '.m3u8' in p:
            return self._rewrite_m3u8(p)
        try:
            r = self.fetch(p, headers=self._hd(p), timeout=20000)
            if hasattr(r, 'status_code') and r.status_code != 200:
                return {'code': r.status_code, 'content': b'', 'headers': {}}
            return {'code': 200, 'content': r.content, 'headers': {'Content-Type': r.headers.get('Content-Type', 'application/octet-stream')}}
        except:
            return {'code': 404, 'content': b'', 'headers': {}}
    def _rewrite_m3u8(self, url):
        try:
            r = self.fetch(url, headers=self._hd(url), timeout=20000)
            if hasattr(r, 'status_code') and r.status_code != 200:
                return {'code': r.status_code, 'content': b'', 'headers': {}}
            body = r.text if hasattr(r, 'text') else str(r)
        except:
            return {'code': 404, 'content': b'', 'headers': {}}
        base = url.rsplit('/', 1)[0] + '/'
        om = re.match(r'https?://[^/]+', url)
        origin = om.group(0) if om else ''
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
    def _img(self, u):
        try:
            r = requests.get(u, headers={'User-Agent': self.ua, 'Referer': PIC_REFERER or self.ref}, timeout=15)
            data, ct = r.content, r.headers.get('Content-Type', 'image/jpeg')
            if data[:4] == b'RIFF' or 'webp' in ct:
                try:
                    from PIL import Image
                    import io
                    buf = io.BytesIO()
                    Image.open(io.BytesIO(data)).convert('RGB').save(buf, 'JPEG', quality=85)
                    data, ct = buf.getvalue(), 'image/jpeg'
                except:
                    ct = 'image/webp'
            return {'code': 200, 'content': data, 'headers': {'Content-Type': ct}}
        except:
            return {'code': 404, 'content': b'', 'headers': {}}

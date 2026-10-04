# -*- coding: utf-8 -*-
# ============ ik4k在线影院(ik4k.com)测试源（88测试结构派生 + IKGuard纯Python过盾引擎） ============
# 站点: MacCMS系·短视主题(dsn2) + 自研WAF(easy_slide滑块挑战)
# 突破: ①过盾公式 x=拼图块x-8, y=guardword(拼图top坐标), guardret=b64(RC4(x+"x"+y, guard[:8])), 服务端下发_ok6_(7天)
#       ②纯Python PNG解码(zlib)+积分图洞检测(无cv2/numpy依赖) ③分类/翻页=POST /index.php/ds_api/vod (type+tid)
#       ④详情=/voddetail/{id}/ ⑤播放=/vodplay/{vid}-{sid}-{nid}/ (player_aaaa encrypt=0) ⑥搜索=/vodsearch/
# 13接口=init/homeContent/categoryContent/detailContent/searchContent/playerContent/localProxy/isVideoFormat/manualVideoCheck/getDependence/destroy/progressVideo/setVideoFlags
import sys, re, json, time, zlib, base64, hashlib, threading, os
from urllib.parse import urljoin, quote, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
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
HOSTS = ['https://www.ik4k.com']  # ★ 主域(ik4k.cn同WAF, 备用可加)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
CATEGORIES = {'20': '电影', '21': '电视剧', '23': '综艺片', '24': '动漫', '25': '国产剧', '26': '美剧', '27': '韩剧',
              '35': '日剧', '36': '港剧', '37': '台剧', '38': '泰剧', '39': '海外剧', '40': '大陆综艺', '41': '港台综艺',
              '42': '日韩综艺', '43': '欧美综艺', '67': '国产动漫', '68': '日韩动漫', '69': '欧美动漫',
              '70': '港台动漫', '71': '海外动漫'}  # ★ 一级+二级分类(tid→名称, 已验证)
PK = ''
REFERER = ''
PIC_REFERER = ''
FD_ZONE = 0
PROBE = 0
SITE_KEY = ''
VIDEO_EXTS = 'm3u8|mp4|flv|mkv|avi|ts'
DEBUG = 1  # ★ 诊断日志开关(1开/0关)
LOG_PATH = '/sdcard/ik4k_debug.log'
TTL_HOME = 3600
TTL_DETAIL = 1800
TTL_PLAY = 900
SERIAL = 0
THROTTLE_GAP = 0.35  # ★ 全局请求节流间隔(秒)
BAN_COOL = 15  # ★ 熔断冷静期基数(秒)
BAN_MAX = 90  # ★ 熔断冷静期上限(秒)
PAGE_SIZE = 40  # ds_api/vod 每页条数(服务端默认40)
CONT = 1
CURSOR_TTL = 7200
HOLD_TTL = 21600
HOLD_MAX = 8
HOLD_FAILS = 3
HOLD_SPAN = 300
SEEN_CAP = 400
PROBE_MAX = 2
LADDER_SLEEP = 0.35
BF_POS = 0
MISS_TTL = 60
LI_CAP = 600
GATHER_BUDGET = 8.0
# ★ IKGuard 过盾引擎(easy_slide滑块)
GUARD = 1
GUARD_HOST = 'https://www.ik4k.com'
GUARD_COOKIE_PATHS = ['/sdcard/tmp/ik4k_guard.json', '/storage/emulated/0/tmp/ik4k_guard.json', '/tmp/ik4k_guard.json']
GUARD_TRIES = 3

def _log(msg):
    if not DEBUG:
        return
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write('[%s] %s\n' % (time.strftime('%m-%d %H:%M:%S'), str(msg)[:300]))
    except Exception:
        pass

# ============ ★ IKGuard过盾引擎（ik4k专用·纯Python；无cv2/numpy依赖） ============
def _rc4(data, key):
    S = list(range(256)); j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) & 0xFF
        S[i], S[j] = S[j], S[i]
    out = bytearray(); i = j = 0
    for ch in data:
        i = (i + 1) & 0xFF
        j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
        out.append(ch ^ S[(S[i] + S[j]) & 0xFF])
    return bytes(out)

def _png_gray(data):
    if not data or data[:8] != b'\x89PNG\r\n\x1a\n':
        return 0, 0, None
    pos = 8; plte = None; idat = b''; W = H = ct = inter = 0
    while pos + 8 <= len(data):
        ln = int.from_bytes(data[pos:pos + 4], 'big')
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b'IHDR':
            W = int.from_bytes(body[0:4], 'big'); H = int.from_bytes(body[4:8], 'big')
            ct = body[9]; inter = body[12]
        elif typ == b'PLTE':
            plte = body
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
        pos += 12 + ln
    if inter != 0 or W < 400 or not idat:
        return 0, 0, None
    try:
        raw = zlib.decompress(idat)
    except Exception:
        return 0, 0, None
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ct, 0)
    if not ch:
        return 0, 0, None
    stride = W * ch
    rows = []; prev = bytearray(stride); p = 0
    for y in range(H):
        if p >= len(raw):
            break
        f = raw[p]; line = bytearray(raw[p + 1:p + 1 + stride]); p += 1 + stride
        if f == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa = abs(b - c); pb = abs(a - c); pc = abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        rows.append(bytes(line)); prev = line
    if ct == 3 and plte:
        npal = max(1, len(plte) // 3)
        pg = [0.299 * plte[i * 3] + 0.587 * plte[i * 3 + 1] + 0.114 * plte[i * 3 + 2] for i in range(npal)]
        pg += [0.0] * (256 - len(pg))
        gray = [[pg[b] for b in rows[y]] for y in range(len(rows))]
    elif ct == 0:
        gray = [[rows[y][x] for x in range(W)] for y in range(len(rows))]
    elif ct == 2:
        gray = [[0.299 * rows[y][x * 3] + 0.587 * rows[y][x * 3 + 1] + 0.114 * rows[y][x * 3 + 2] for x in range(W)] for y in range(len(rows))]
    else:
        gray = [[0.299 * rows[y][x * 4] + 0.587 * rows[y][x * 4 + 1] + 0.114 * rows[y][x * 4 + 2] for x in range(W)] for y in range(len(rows))]
    return W, H, gray

def _find_hole(W, H, gray, gw):
    I = [[0] * (W + 1) for _ in range(H + 1)]
    for y in range(H):
        gy = gray[y]; Iy = I[y]; Iy1 = I[y + 1]; acc = 0
        for x in range(W):
            if gy[x] < 95:
                acc += 1
            Iy1[x + 1] = Iy[x + 1] + acc
    cands = []
    for y0 in range(max(6, gw + 2), min(164, gw + 16)):
        y1 = y0 + 36
        if y1 > H:
            break
        I0 = I[y0]; I1 = I[y1]
        for x0 in range(6, 303):
            x1 = x0 + 38
            if x1 > W:
                break
            s = I1[x1] - I0[x1] - I1[x0] + I0[x0]
            if s > 0.55 * 1368:
                cands.append((s, x0, y0))
    cands.sort(reverse=True)
    best = None
    for s, x0, y0 in cands[:16]:
        vals = []
        for y in range(y0, y0 + 36):
            vals.extend(gray[y][x0:x0 + 38])
        vals.sort()
        med = vals[len(vals) // 2]
        ring = 0.0
        if x0 >= 9:
            acc = 0; n = 0
            for y in range(y0, y0 + 36):
                gy = gray[y]
                for x in range(x0 - 9, x0):
                    acc += gy[x]; n += 1
            ring = max(ring, acc / n)
        if x0 + 47 <= W:
            acc = 0; n = 0
            for y in range(y0, y0 + 36):
                gy = gray[y]
                for x in range(x0 + 38, x0 + 47):
                    acc += gy[x]; n += 1
            ring = max(ring, acc / n)
        score = (s / 1368) * 100 + (ring - med) * 0.3
        if best is None or score > best[0]:
            best = (score, x0, y0, s / 1368)
    return best

def _slot_blocks(gray, W, H, gw):
    I = [[0] * (W + 1) for _ in range(H + 1)]
    for y in range(H):
        gy = gray[y]; Iy = I[y]; Iy1 = I[y + 1]; acc = 0
        for x in range(W):
            if gy[x] < 95:
                acc += 1
            Iy1[x + 1] = Iy[x + 1] + acc
    out = []
    for y0 in range(max(6, gw + 2), min(164, gw + 16)):
        y1 = y0 + 36
        if y1 > H:
            break
        I0 = I[y0]; I1 = I[y1]
        for x0 in range(6, 303):
            x1 = x0 + 38
            if x1 > W:
                break
            s = I1[x1] - I0[x1] - I1[x0] + I0[x0]
            if s >= 0.75 * 1368:
                rl = rr = None
                if x0 >= 9:
                    a2 = 0; n2 = 0
                    for yy in range(y0, y1):
                        row = gray[yy]
                        for xx in range(x0 - 9, x0):
                            a2 += row[xx]; n2 += 1
                    rl = a2 / n2
                if x0 + 47 <= W:
                    a2 = 0; n2 = 0
                    for yy in range(y0, y1):
                        row = gray[yy]
                        for xx in range(x0 + 38, x0 + 47):
                            a2 += row[xx]; n2 += 1
                    rr = a2 / n2
                mrs = [v for v in (rl, rr) if v is not None]
                if not mrs:
                    continue
                out.append((min(mrs), s, x0, y0))
    out.sort(reverse=True)
    picked = []
    for mr, s, x0, y0 in out:
        if not (8 <= x0 <= 298):
            continue
        if all(abs(x0 - px) > 25 or abs(y0 - py) > 25 for _, _, px, py in picked):
            picked.append((round(mr, 1), s, x0, y0))
        if len(picked) >= 6:
            break
    return picked

class IKGuard:
    def __init__(self, host, cookie_paths, log=None):
        self.host = (host or GUARD_HOST).rstrip('/')
        self.paths = cookie_paths or GUARD_COOKIE_PATHS
        self.path = self.paths[0]
        self.log = log or (lambda m: None)
        self.ck = {}
        self.ua = UA
        self._busy = False
        self._got = 0.0

    def load(self):
        for p in self.paths:
            try:
                d = json.load(open(p, encoding='utf-8'))
                if isinstance(d, dict) and d.get('_ok6_'):
                    self.ck = {k: str(v) for k, v in d.items() if v and not k.startswith('guard')}
                    self.path = p
                    self.log('guard: cookie loaded %s' % p)
                    return True
            except Exception:
                continue
        return False

    def save(self):
        for p in self.paths:
            try:
                d = os.path.dirname(p)
                if d and not os.path.isdir(d):
                    os.makedirs(d)
            except Exception:
                pass
            try:
                json.dump({k: v for k, v in self.ck.items() if v and not k.startswith('guard')}, open(p, 'w', encoding='utf-8'))
                self.path = p
                return True
            except Exception:
                continue
        return False

    def cookie_header(self):
        return '; '.join('%s=%s' % (k, v) for k, v in self.ck.items())

    def _hd(self, ref=None):
        hd = {'User-Agent': self.ua, 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}
        if ref:
            hd['Referer'] = ref
        if self.ck:
            hd['Cookie'] = self.cookie_header()
        return hd

    def feed(self, resp):
        try:
            if hasattr(resp.headers, 'get_all'):
                scs = resp.headers.get_all('Set-Cookie') or []
            else:
                scs = [resp.headers.get('Set-Cookie') or '']
        except Exception:
            scs = []
        got = False
        for sc in scs:
            if not sc:
                continue
            for m in re.finditer(r'(?:^|[,;]\s*)(guardword|guarddata|guard|guardret|_ok6_|server_session_[0-9a-f]+)=([^;,]+)', sc):
                k, v = m.group(1), m.group(2).strip()
                if v:
                    self.ck[k] = v
                else:
                    self.ck.pop(k, None)
                got = True
        if got:
            self.save()
        return got

    def req(self, url, ref=None, timeout=12, method='get', data=None):
        try:
            if method == 'post':
                r = requests.post(url, headers=self._hd(ref), data=data, timeout=timeout)
            else:
                r = requests.get(url, headers=self._hd(ref), timeout=timeout)
            self.feed(r)
            return r
        except Exception as e:
            self.log('guard req err %s' % str(e)[:80])
            return None

    def challenge(self, text):
        if text is None:
            return True
        return len(text) < 500 and '_guard' in text

    def run(self):
        if self._busy:
            return False
        self._busy = True
        try:
            self.log('guard: start')
            self.ck.pop('guardret', None)
            self.req(self.host + '/', ref=self.host + '/', timeout=10)
            self.req(self.host + '/_guard/html.js?js=easy_slider_html', ref=self.host + '/', timeout=10)
            r = self.req(self.host + '/_guard/easy_slide.png?t=%d' % int(time.time() * 1000),
                         ref=self.host + '/', timeout=10)
            if r is None:
                self.log('guard: png fail')
                return False
            gw = int(self.ck.get('guardword', '0') or 0)
            gk = self.ck.get('guard', '')
            W, H, gray = _png_gray(r.content)
            if not (W and gk):
                self.log('guard: decode fail W=%s' % W)
                return False
            blocks = _slot_blocks(gray, W, H, gw)
            cands = []
            for off in (-8, -7, -9, -6, -10):
                for _mr, _s, bx, _by in blocks[:2]:
                    cands.append(bx + off)
            for _mr, _s, bx, _by in blocks[2:6]:
                for off in (-8, -7, -9):
                    cands.append(bx + off)
            hole = _find_hole(W, H, gray, gw)
            if hole:
                cands += [hole[1] - 8, hole[1] - 9]
            seen = []
            for x in cands:
                if not (0 <= x <= 290) or x in seen:
                    continue
                seen.append(x)
                self.ck['guardret'] = base64.b64encode(
                    _rc4(('%dx%d' % (x, gw)).encode('utf-8', 'ignore'), gk[:8].encode('utf-8', 'ignore'))).decode()
                r3 = self.req(self.host + '/', ref=self.host + '/', timeout=10)
                ok = r3 is not None and len(r3.text) > 8000
                self.log('guard: try x=%d ok=%s' % (x, ok))
                if ok:
                    for k in ('guard', 'guardword', 'guarddata', 'guardret'):
                        self.ck.pop(k, None)
                    self.save()
                    self._got = time.time()
                    return True
                if len(seen) >= 16:
                    break
                time.sleep(0.3)
            return False
        finally:
            self._busy = False

class Spider(Spider):
    ik = None
    def init(self, extend=''):
        self.base = HOSTS[0].rstrip('/')
        self.ua = UA
        self.pk = PK
        self.ref = REFERER or self.base
        self.types = dict(CATEGORIES)
        self.filters = {}
        self._pc = {}
        self._srv = None
        self._c = {}
        self._ttl = {}
        self._lock = threading.RLock()
        self._inflight = {}
        self._last_req = 0.0
        self._ban_until = 0.0
        self._ban_hits = 0
        self._th = threading.Lock()
        self.ik = None
        if GUARD:
            self.ik = IKGuard(GUARD_HOST or self.base, GUARD_COOKIE_PATHS, log=_log)
            self.ik.load()
        if self.ik and not self.ik.ck:
            try:
                r = requests.get(self.base + '/', headers={'User-Agent': self.ua}, timeout=5)
                t = r.text or ''
                if t and self.ik.challenge(t):
                    self.ik.run()
                elif len(t) > 8000:
                    self.ik.feed(r)
            except Exception:
                pass

    # ========== IKGuard通道: 自管cookie + 挑战检测 + 过盾重试 ==========
    def _ikget(self, url, headers=None, timeout=15000):
        hd = dict(headers or {'User-Agent': self.ua, 'Referer': self.ref})
        for i in range(3):
            if time.time() < self._ban_until:
                _log('ik: ban skip %s' % url[:60])
                return ''
            if self.ik and self.ik.ck:
                hd['Cookie'] = self.ik.cookie_header()
            text = self._ik_raw(url, hd, timeout, 'get', None)
            if text is None:
                if i < 2 and time.time() >= self._ban_until:
                    time.sleep(0.4 * (i + 1))
                    continue
                return ''
            if self.ik and self.ik.challenge(text):
                _log('ik: challenge hit get %s' % url[:80])
                if self.ik.run():
                    continue
                return ''
            return text
        return ''

    def _ikpost(self, url, data, headers=None, timeout=15000):
        hd = dict(headers or {'User-Agent': self.ua, 'Referer': self.ref, 'X-Requested-With': 'XMLHttpRequest'})
        for i in range(3):
            if time.time() < self._ban_until:
                _log('ik: ban skip post %s' % url[:60])
                return ''
            if self.ik and self.ik.ck:
                hd['Cookie'] = self.ik.cookie_header()
            text = self._ik_raw(url, hd, timeout, 'post', data)
            if text is None:
                if i < 2 and time.time() >= self._ban_until:
                    time.sleep(0.4 * (i + 1))
                    continue
                return ''
            if self.ik and self.ik.challenge(text):
                _log('ik: challenge hit post %s' % url[:80])
                if self.ik.run():
                    continue
                return ''
            return text
        return ''

    def _ik_raw(self, url, headers, timeout, method, data):
        if time.time() < self._ban_until:
            return None
        with self._th:
            gap = time.time() - self._last_req
            if gap < THROTTLE_GAP:
                time.sleep(THROTTLE_GAP - gap)
            self._last_req = time.time()
        s = max(8, int((timeout or 15000) / 1000))
        r = None
        if method == 'post':
            try:
                r = requests.post(url, headers=headers, data=data, timeout=s)
            except Exception as e:
                self._ik_err('post', e)
                return None
        else:
            try:
                r = self.fetch(url, headers=headers, timeout=s)
            except TypeError:
                try:
                    r = requests.get(url, headers=headers, timeout=s)
                except Exception as e:
                    self._ik_err('get', e)
                    return None
            except Exception:
                try:
                    r = requests.get(url, headers=headers, timeout=s)
                except Exception as e:
                    self._ik_err('get', e)
                    return None
        self._ban_hits = 0
        if self.ik:
            self.ik.feed(r)
        try:
            return r.text if hasattr(r, 'text') else str(r)
        except Exception:
            return ''
    def _ik_err(self, kind, e):
        msg = str(e)
        hard = ('RemoteDisconnected' in msg or 'Connection aborted' in msg or 'NewConnectionError' in msg)
        self._ban_hits = self._ban_hits + 1 if hard else 0
        if hard and self._ban_hits >= 3:
            self._ban_until = time.time() + min(BAN_MAX, BAN_COOL * (self._ban_hits - 2))
            _log('ik %s err ban+%ds hits=%d %s' % (kind, int(self._ban_until - time.time()), self._ban_hits, msg[:60]))
        else:
            _log('ik %s err %s' % (kind, msg[:80]))
    def _rfetch(self, url, headers=None, sec=15):
        hd = dict(headers or {'User-Agent': self.ua, 'Referer': self.ref})
        for i in range(2):
            try:
                try:
                    return self.fetch(url, headers=hd, timeout=sec)
                except TypeError:
                    return requests.get(url, headers=hd, timeout=sec)
            except Exception as e:
                _log('rfetch err %s' % str(e)[:80])
                if i < 1:
                    time.sleep(0.35)
        return None
    def _get(self, url, headers=None, timeout=15000):
        return self._ikget(url, headers, timeout)

    def _pic(self, u):
        if not u:
            return ''
        if u.startswith('//'):
            u = 'https:' + u
        return u

    # ========== 工具(88测试结构: TTL缓存/续读梯/列表记忆/最小结构) ==========
    def _tget(self, key, ttl):
        v = self._ttl.get(key)
        if v and time.time() - v[0] < ttl:
            return v[1]
        return None

    def _tset(self, key, val):
        self._ttl[key] = [time.time(), val]
        return val

    def _rty(self, key, fn, waits=(0, 0.45, 1.2)):
        if self._tget('rt:' + key, MISS_TTL) is not None:
            return None
        for w in waits:
            if w:
                time.sleep(w)
            try:
                r = fn()
            except Exception:
                r = None
            if r:
                return r
        self._tset('rt:' + key, 1)
        return None

    def _li_mem(self, items):
        if not items:
            return
        try:
            m = self._tget('li:map', 86400) or {}
            for it in items:
                if it.get('vod_id'):
                    m[str(it['vod_id'])] = it
            if len(m) > 3000:
                for k in list(m.keys())[:1000]:
                    m.pop(k, None)
            self._tset('li:map', m)
        except Exception:
            pass

    def _li_get(self, vid):
        try:
            v = self._tget('li:map', 86400)
            return (v or {}).get(str(vid))
        except Exception:
            return None

    def _minstruct(self, vid):
        it = self._li_get(vid)
        if not it:
            return None
        return {'vod_id': str(vid), 'vod_name': it.get('vod_name', ''), 'vod_pic': it.get('vod_pic', ''),
                'vod_year': '', 'vod_area': '', 'vod_class': '', 'vod_director': '', 'vod_actor': '',
                'vod_content': '', 'vod_remarks': it.get('vod_remarks', ''), 'vod_play_from': '', 'vod_play_url': ''}

    def _norm_name(self, s):
        s = str(s or '')
        s = re.sub(r'[《》「」【】“”"\'\'（）()\[\]!！?？,，。.、·~～…\-—_：:\s]', '', s)
        for suf in ('精简版', '完整版', '未删减版', '未删减', '加长版', '导演剪辑版', 'TV版', 'DVD版', '电影版', '国语版', '粤语版', '英语版', '原声版', '中字', '字幕版'):
            if s.endswith(suf) and len(s) > len(suf) + 1:
                s = s[: -len(suf)]
                break
        for suf in ('国语', '粤语', '英语', '原声'):
            if s.endswith(suf) and len(s) > len(suf) + 1:
                s = s[: -len(suf)]
                break
        return s

    def _search_names(self, nm):
        out = []
        base = str(nm or '').strip()
        for c in [base, self._norm_name(base)]:
            c = re.sub(r'\s+', ' ', str(c or '')).strip()
            if len(c) >= 2 and c not in out:
                out.append(c)
        n1 = self._norm_name(base)
        if len(n1) > 4:
            for cut in (n1[:-2], n1[:6]):
                if len(cut) >= 2 and cut != n1 and cut not in out:
                    out.append(cut)
        return out[:4]

    def _find_swap(self, nm, vid):
        vid = str(vid)
        best = ''
        for q in self._search_names(nm):
            qn = self._norm_name(q)
            if len(qn) < 2:
                continue
            try:
                hq = self._ikget('%s/vodsearch/%s-------------/' % (self.base, quote(q, safe='')))
                if not hq:
                    continue
                for it in self._ik_search_items(hq)[:10]:
                    vid2 = str(it.get('vod_id') or '')
                    if not vid2 or vid2 == vid:
                        continue
                    n2 = self._norm_name(it.get('vod_name'))
                    if not n2:
                        continue
                    if n2 == qn:
                        return vid2
                    if not best and (qn in n2 or n2 in qn):
                        best = vid2
            except Exception:
                continue
        return best

    def _detail_swap(self, vid, nm):
        if not nm:
            return None
        v2 = self._find_swap(nm, vid)
        if not v2:
            return None
        try:
            d2 = self.detailContent([v2])
        except Exception:
            return None
        if not d2 or not d2.get('list'):
            return None
        dd = d2['list'][0]
        if not dd.get('vod_play_from') or not dd.get('vod_play_url'):
            return None
        dd['vod_id'] = str(vid)
        _log('detail swap %s->%s' % (vid, v2))
        return {'list': [dd]}

    def _safe(self, s):
        return str(s or '').replace('#', '-').replace('$', '|')

    # ========== 首页 ==========
    def homeContent(self, filter=False):
        ck = 'home:%d' % (1 if filter else 0)
        c = self._tget(ck, TTL_HOME)
        if c:
            return c
        r = {'class': [{'type_id': k, 'type_name': v} for k, v in self.types.items()]}
        if filter and self.filters:
            r['filters'] = self.filters
        r['list'] = self.homeVideoContent().get('list', [])
        if r.get('list'):
            return self._tset(ck, r)
        return r

    def homeVideoContent(self):
        c = self._tget('ik:home', TTL_HOME)
        if c is not None:
            return c
        h = self._ikget(self.base + '/')
        items = self._ik_items(h) if h else []
        if not items:
            h2 = self._rty('ik:home', lambda: self._ikget(self.base + '/'), (0, 0.6))
            items = self._ik_items(h2) if h2 else []
        self._li_mem(items)
        r = {'list': items}
        if items:
            return self._tset('ik:home', r)
        return r

    def _ik_items(self, h):
        items, seen = [], set()
        if not h:
            return items
        for part in h.split('<div class="public-list-box')[1:]:
            seg = part[:2000]
            m = re.search(r'href="(/voddetail/(\d+)/)"', seg)
            if not m:
                continue
            vid = m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            nm = re.search(r'title="([^"]*)"', seg)
            pm = re.search(r'<img[^>]+(?:data-src|src)="([^"]+)"', seg)
            rem = re.search(r'public-list-prb[^>]*>([^<]*)<', seg) or re.search(r'public-list-subtitle[^>]*>([^<]*)<', seg)
            items.append({'vod_id': vid,
                          'vod_name': (nm.group(1).strip() if nm else '')[:80],
                          'vod_pic': self._pic(pm.group(1)) if pm else '',
                          'vod_remarks': rem.group(1).strip()[:40] if rem else ''})
        return items

    # ========== 分类(POST /index.php/ds_api/vod; type=tid&page=pn) ==========
    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        t = str(tid)
        ck = 'c:%s:%s' % (t, pn)
        c = self._tget(ck, 300)
        if c:
            return c
        items, pc = self._cat_fetch(t, '', '', {}, pn)
        if items:
            self._li_mem(items)
        r = {'page': pn, 'pagecount': pc or pn, 'limit': PAGE_SIZE, 'total': len(items), 'list': items}
        if items:
            return self._tset(ck, r)
        return r

    def _cat_fetch(self, t, cls, ex2, ex, pn):
        txt = self._ikpost(self.base + '/index.php/ds_api/vod',
                           {'type': t, 'page': pn, 'limit': PAGE_SIZE})
        if not txt:
            return [], 0
        try:
            d = json.loads(txt)
        except Exception:
            _log('cat json err %s' % txt[:80])
            return [], 0
        items = []
        for it in (d.get('list') or []):
            vid = it.get('vod_id')
            if vid is None:
                continue
            pl = it.get('vod_pic') or ''
            if pl.startswith('//'):
                pl = 'https:' + pl
            items.append({'vod_id': str(vid),
                          'vod_name': str(it.get('vod_name') or '')[:80],
                          'vod_pic': self._pic(pl),
                          'vod_remarks': str(it.get('vod_remarks') or it.get('vod_state') or '')[:40]})
        try:
            pc = int(d.get('pagecount') or 0)
        except Exception:
            pc = 0
        return items, pc

    # ========== 详情(/voddetail/{id}/) ==========
    def detailContent(self, ids, quick='1'):
        vid = str(ids[0] if isinstance(ids, list) else ids or '')
        m = re.search(r'(\d+)', vid)
        vid = m.group(1) if m else ''
        if not vid:
            return {'list': []}
        c = self._tget('d:' + vid, TTL_DETAIL)
        if c:
            return c
        h = self._rty('dt:%s' % vid, lambda: self._ikget('%s/voddetail/%s/' % (self.base, vid)), (0, 0.45, 1.2))
        if not h:
            _log('detail miss %s' % vid)
            v = self._minstruct(vid)
            return {'list': [v]} if v else {'list': []}
        if 'slide-info' not in h and 'anthology' not in h:
            _log('detail gone %s' % vid)
            sw = None
            if not getattr(self, '_in_swap', 0):
                it = self._li_get(vid)
                nm = str((it or {}).get('vod_name') or '')
                if nm:
                    self._in_swap = 1
                    try:
                        sw = self._detail_swap(vid, nm)
                    finally:
                        self._in_swap = 0
            if sw:
                return self._tset('d:' + vid, sw)
            v = self._minstruct(vid)
            return {'list': [v]} if v else {'list': []}
        d = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_year': '', 'vod_area': '',
             'vod_class': '', 'vod_director': '', 'vod_actor': '', 'vod_content': '',
             'vod_remarks': '', 'vod_play_from': '', 'vod_play_url': ''}
        tn = re.search(r'<h3 class="slide-info-title hide">([^<]*)</h3>', h)
        name = tn.group(1) if tn else ''
        if not name:
            tt = re.search(r'<title>(.*?)</title>', h)
            name = re.sub(r'[_|]\s*[^_|]*\s*-\s*.*$', '', tt.group(1)) if tt else ''
        d['vod_name'] = re.sub(r'\s+', ' ', name).strip()[:100]
        pm = re.search(r'data-src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', h, re.I) or \
            re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', h, re.I)
        if pm:
            d['vod_pic'] = self._pic(pm.group(1))
        rm = re.search(r'slide-info-remarks cor5">([^<]*)<', h)
        if rm:
            d['vod_remarks'] = rm.group(1).strip()[:40]
        rl = re.findall(r'slide-info-remarks"><a[^>]*>([^<]*)</a>', h)
        if len(rl) >= 2:
            if re.match(r'^(19|20)\d{2}$', rl[0].strip()):
                d['vod_year'] = rl[0].strip()
            d['vod_area'] = rl[1].strip()[:20]
        dm = re.search(r'导演\s*:?</strong>([\s\S]*?)</div>', h)
        if dm:
            d['vod_director'] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>|&nbsp;', ' ', dm.group(1))).strip(' ,')[:120]
        am = re.search(r'演员\s*:?</strong>([\s\S]*?)</div>', h)
        if am:
            d['vod_actor'] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>|&nbsp;', ' ', am.group(1))).strip(' ,')[:200]
        cm = re.search(r'id="height_limit"[^>]*>([\s\S]*?)</div>', h)
        if cm:
            d['vod_content'] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>|&nbsp;', '', cm.group(1))).strip()[:500]
        pf, pu = self._play_sources(h)
        d['vod_play_from'] = '$$$'.join(pf)
        d['vod_play_url'] = '$$$'.join(pu)
        _log('detail ok %s froms=%s' % (vid, d['vod_play_from'][:60]))
        return self._tset('d:' + vid, {'list': [d]})

    def _play_sources(self, h):
        pf, pu = [], []
        names = []
        tm = re.search(r'anthology-tab[\s\S]*?swiper-wrapper">([\s\S]*?)</div>', h)
        if tm:
            for m in re.finditer(r'<a class="swiper-slide">([\s\S]*?)</a>', tm.group(1)):
                txt = re.sub(r'<[^>]+>', '', m.group(1)).replace('&nbsp;', ' ').strip()
                txt = re.sub(r'\s+', '', txt)
                if txt:
                    names.append(txt)
        uls = re.findall(r'<ul class="anthology-list-play[^"]*">([\s\S]*?)</ul>', h)
        for i, ul in enumerate(uls):
            links = re.findall(r'href="(/vodplay/[^"]+)"[^>]*>([^<]+)</a>', ul)
            if links:
                nm = names[i] if i < len(names) else ('线路%d' % (i + 1))
                pf.append(self._safe(nm))
                pu.append('#'.join('%s$%s' % (self._safe(ep.strip()), urljoin(self.base, href)) for href, ep in links))
        if not pf:
            routes = {}
            for href, sid, ep in re.findall(r'href="(/vodplay/(\d+)-(\d+)-\d+/)"[^>]*>([^<]+)</a>', h):
                routes.setdefault(sid, []).append((ep, href))
            for i, sid in enumerate(sorted(routes.keys(), key=lambda x: int(x) if x.isdigit() else 999)):
                nm = names[i] if i < len(names) else ('线路%d' % (i + 1))
                pf.append(self._safe(nm))
                pu.append('#'.join('%s$%s' % (self._safe(ep.strip()), urljoin(self.base, href)) for ep, href in routes[sid]))
        return pf, pu

    # ========== 搜索(/vodsearch/{q}----------{pg}---/) ==========
    def searchContent(self, key, quick=False, pg='1'):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        kw = str(key or '').strip()
        if not kw:
            return {'list': [], 'page': pn, 'pagecount': 1}
        ck = 'sq:%s:%s' % (kw, pn)
        c = self._tget(ck, 300)
        if c:
            return c
        q = quote(kw, safe='')
        if pn <= 1:
            url = '%s/vodsearch/%s-------------/' % (self.base, q)
        else:
            url = '%s/vodsearch/%s----------%d---/' % (self.base, q, pn)
        h = self._rty('sq:%s:%s' % (kw, pn), lambda: self._ikget(url), (0, 0.45, 1.2))
        if not h:
            return {'list': [], 'page': pn, 'pagecount': 1}
        items = self._ik_search_items(h)
        pc = pn
        pm = re.search(r'共(\d+)条[^当]*当前(\d+)\s*/\s*(\d+)页', h)
        if pm:
            try:
                pc = int(pm.group(3))
            except Exception:
                pc = pn
        self._li_mem(items)
        r = {'list': items, 'page': pn, 'pagecount': pc}
        if items:
            return self._tset(ck, r)
        return r

    def _ik_search_items(self, h):
        items, seen = [], set()
        if not h:
            return items
        for m in re.finditer(r'href="/voddetail/(\d+)/"', h):
            vid = m.group(1)
            if vid in seen:
                continue
            seg = h[m.start():m.start() + 1200]
            t = re.search(r'<h3[^>]*>([^<]*)</h3>', seg)
            if not t:
                continue
            seen.add(vid)
            pm = re.search(r'(?:data-src|src)="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', seg, re.I)
            rem = re.search(r'slide-info-remarks[^>]*>([^<]*)<', seg)
            items.append({'vod_id': vid,
                          'vod_name': t.group(1).strip()[:80],
                          'vod_pic': self._pic(pm.group(1)) if pm else '',
                          'vod_remarks': rem.group(1).strip()[:40] if rem else ''})
        return items

    # ========== 播放(/vodplay/{vid}-{sid}-{nid}/ → player_aaaa) ==========
    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id) if id else str(flag)
        ck = 'p:' + raw
        c = self._tget(ck, TTL_PLAY)
        if c:
            return c
        url = self._pid(raw)
        if '://' in url and re.search(r'\.(m3u8|mp4|flv|mp3)(\?|$)', url, re.I):
            _log('play direct %s' % url[:90])
            return self._tset(ck, self._pres(url))
        full = url if url.startswith('http') else urljoin(self.base, url)
        h = self._ikget(full)
        if not h:
            h = self._ikget(full)
        if not h:
            _log('play miss %s' % raw[:90])
            return self._pres('')
        u = self._parse_play(h, full)
        if u and '.m3u8' in u:
            if self._m3u8_ok(u):
                _log('play ok %s' % u[:90])
                return self._tset(ck, self._pres(u))
            _log('play dead %s' % u[:90])
            alt = self._alt_sid(full)
            if alt:
                return self._tset(ck, self._pres(alt))
            _log('play dead fallback %s' % u[:90])
            return self._tset(ck, self._pres(u))
        if u and '://' in u and not re.search(r'\.(mp4|flv)(\?|$)', u, re.I):
            alt = self._alt_sid(full)
            if alt:
                return self._tset(ck, self._pres(alt))
            swp = self._role_swap(h, full)
            if swp:
                return self._tset(ck, self._pres(swp))
            _log('play parse1 %s' % u[:90])
            return self._tset(ck, {'parse': 1, 'url': u, 'header': {'User-Agent': self.ua, 'Referer': self.base + '/'}})
        _log('play empty %s' % str(u)[:90])
        return self._pres(u)
    def _alt_sid(self, full):
        m = re.search(r'/vodplay/(\d+)-(\d+)-(\d+)', full)
        if not m:
            return ''
        vid, sid, nid = m.group(1), int(m.group(2)), m.group(3)
        cands = [s2 for s2 in range(1, 6) if s2 != sid]
        if not cands:
            return ''
        res = {}
        lk = threading.Lock()
        def probe(s2):
            try:
                p2 = '%s/vodplay/%s-%d-%s/' % (self.base, vid, s2, nid)
                h2 = self._ikget(p2)
                if h2:
                    u2 = self._parse_play(h2, p2)
                    if u2 and '.m3u8' in u2 and self._m3u8_ok(u2):
                        with lk:
                            res[s2] = u2
            except Exception:
                pass
        ex = ThreadPoolExecutor(max_workers=2)
        try:
            futs = [ex.submit(probe, s2) for s2 in cands]
            for f in as_completed(futs, timeout=30):
                if res:
                    break
        except Exception:
            pass
        finally:
            ex.shutdown(wait=False)
        for s2 in cands:
            if s2 in res:
                _log('play alt sid%d ok %s' % (s2, res[s2][:80]))
                return res[s2]
        return ''

    def _m3u8_ok(self, u):
        try:
            r = requests.get(u, headers={'User-Agent': self.ua, 'Referer': self.ref}, timeout=6, stream=True)
            ok = getattr(r, 'status_code', 0) == 200
            if ok:
                try:
                    for _ in r.iter_content(1):
                        break
                except Exception:
                    pass
            try:
                r.close()
            except Exception:
                pass
            return ok
        except Exception:
            return False

    def _role_swap(self, h, full):
        m = re.search(r'/vodplay/(\d+)-(\d+)-(\d+)', full)
        if not m:
            return ''
        vid, nid = m.group(1), m.group(3)
        name = ''
        vm = re.search(r'"vod_name"\s*:\s*"((?:[^"\\]|\\.)*)"', h)
        if vm:
            try:
                name = json.loads('"%s"' % vm.group(1))
            except Exception:
                name = vm.group(1)
        if not name:
            tm = re.search(r'<title>(.*?)</title>', h, re.S)
            if tm:
                name = re.sub(r'[_|].*$', '', tm.group(1)).strip()
        name = re.sub(r'\s+', ' ', name).strip()[:40]
        if len(name) < 2:
            return ''
        qs = self._search_names(name)
        for q in qs:
            try:
                hq = self._ikget('%s/vodsearch/%s-------------/' % (self.base, quote(q, safe='')))
                if not hq:
                    continue
                for it in self._ik_search_items(hq)[:8]:
                    vid2 = str(it.get('vod_id') or '')
                    if not vid2 or vid2 == vid:
                        continue
                    nm2 = self._norm_name(it.get('vod_name'))
                    qc = self._norm_name(q)
                    if not nm2 or len(nm2) < 2 or not (nm2 == qc or qc in nm2 or nm2 in qc):
                        continue
                    u2 = self._swap_play(vid2, nid)
                    if u2:
                        _log('play swap %s->%s %s' % (vid, vid2, u2[:70]))
                        return u2
            except Exception:
                continue
        return ''

    def _swap_play(self, vid2, nid):
        for s2 in (1, 2, 3):
            try:
                p2 = '%s/vodplay/%s-%d-%s/' % (self.base, vid2, s2, nid)
                h2 = self._ikget(p2)
                if not h2:
                    continue
                u2 = self._parse_play(h2, p2)
                if u2 and '.m3u8' in u2:
                    return u2
            except Exception:
                continue
        return ''

    def _pid(self, sid):
        s = str(sid or '').strip()
        if '$$$' in s:
            s = s.split('$$$', 1)[0]
        if '$' in s:
            a, b = s.split('$', 1)[1], s.rsplit('$', 1)[-1]
            s = b if ('://' in b or b.startswith('/')) else a
        if '#' in s and '://' not in s.split('#', 1)[0] and not s.split('#', 1)[1].startswith('/'):
            s = s.split('#', 1)[0]
        return s

    def _pres(self, url, ref=None):
        hd = {'Referer': ref if ref is not None else (self.ref or (self.base + '/'))}
        return {'parse': 0, 'url': url or '', 'header': hd, 'user_agent': self.ua}

    def _parse_play(self, h, page_url):
        m = re.search(r'player_aaaa\s*=\s*(\{[\s\S]*?\})\s*</script>', h)
        if m:
            try:
                d = json.loads(m.group(1))
                u = str(d.get('url') or '')
                if u and re.search(r'\.(m3u8|mp4|flv)', u, re.I):
                    return u
                if u and d.get('encrypt'):
                    u2 = self._dec(u, page_url)
                    if u2:
                        return u2
                if u.startswith('http'):
                    return u
            except Exception:
                _log('play json err %s' % str(m.group(1))[:80])
        m2 = re.search(r'(https?://[^\s"\'<>]+\.m3u8)', h)
        if m2:
            return m2.group(1)
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', h, re.I)
        if iframe:
            u = iframe.group(1)
            if u.startswith('http'):
                h2 = self._ikget(u)
                if h2:
                    return self._parse_play(h2, u)
        return ''

    def _dec(self, u, page_url):
        u = u.strip()
        if re.search(r'\.(m3u8|mp4|flv)(\?|$)', u, re.I):
            return u
        try:
            s = u.encode()
            s2 = base64.b64decode(s + b'=' * (-len(s) % 4)).decode('utf-8', 'ignore')
            if re.search(r'\.(m3u8|mp4|flv)(\?|$)', s2, re.I):
                return s2
        except Exception:
            pass
        return u if u.startswith('http') else ''

    # ========== 四壳13接口扩展钩子 ==========
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
            self._c.clear()
            self._pc.clear()
            self._ttl.clear()
            self._srv = None
            if self.ik:
                self.ik.save()
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

    # ========== 本地代理(图片/直链/m3u8重写兜底) ==========
    def localProxy(self, param):
        if isinstance(param, dict):
            q, s = param, ''
        else:
            q, s = {}, str(param or '').strip()
            if s.startswith('{'):
                try:
                    d = json.loads(s)
                    q = d if isinstance(d, dict) else {}
                except Exception:
                    q = {}
        p = str(q.get('key') or q.get('url') or s or '')
        if 'key=' in p:
            p = p.split('key=', 1)[-1].split('&', 1)[0]
        elif 'url=' in p:
            p = p.split('url=', 1)[-1]
        p = unquote(p) if '%' in p else p
        if p.startswith('img:'):
            try:
                b = p[4:]
                p = base64.b64decode(b + '=' * (-len(b) % 4)).decode('utf-8', 'replace')
            except Exception:
                return [404, 'text/plain', '']
        if not p.startswith('http'):
            return [404, 'text/plain', '']
        if re.search(r'\.(jpe?g|png|webp|gif)(\?|$)', p, re.I):
            return self._img(p)
        if '.m3u8' in p:
            return self._rewrite_m3u8(p)
        r = self._rfetch(p, {'User-Agent': self.ua, 'Referer': self.ref}, 15)
        if r is None:
            return [404, 'text/plain', '']
        if hasattr(r, 'status_code') and r.status_code != 200:
            return [r.status_code, 'text/plain', '']
        return {'code': 200, 'content': r.content, 'headers': {'Content-Type': r.headers.get('Content-Type', 'application/octet-stream')}}

    def _rewrite_m3u8(self, url):
        r = self._rfetch(url, {'User-Agent': self.ua, 'Referer': self.ref}, 15)
        if r is None:
            return [404, 'text/plain', '']
        if hasattr(r, 'status_code') and r.status_code != 200:
            return [r.status_code, 'text/plain', '']
        body = r.text if hasattr(r, 'text') else str(r)
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
            elif ln.startswith('//'):
                ln = 'proxy?url=' + quote('https:' + ln, safe='')
            elif ln and not ln.startswith('#'):
                ln = 'proxy?url=' + quote(base + ln.strip(), safe='')
            out.append(ln)
        return {'code': 200, 'content': '\n'.join(out), 'headers': {'Content-Type': 'application/vnd.apple.mpegurl'}}

    def _img(self, u):
        try:
            r = requests.get(u, headers={'User-Agent': self.ua, 'Referer': PIC_REFERER or (self.ref or self.base)}, timeout=15)
            data, ct = r.content, r.headers.get('Content-Type', 'image/jpeg')
            if data[:4] == b'RIFF' or 'webp' in ct:
                try:
                    from PIL import Image
                    import io
                    buf = io.BytesIO()
                    Image.open(io.BytesIO(data)).convert('RGB').save(buf, 'JPEG', quality=85)
                    data, ct = buf.getvalue(), 'image/jpeg'
                except Exception:
                    ct = 'image/webp'
            return {'code': 200, 'content': data, 'headers': {'Content-Type': ct}}
        except Exception:
            return [404, 'text/plain', '']

# -*- coding: utf-8 -*-
# ============ libvio.cam 爬虫源 | 基于 71us 模板 v7.5 (555骨架+13接口四壳协议) ============
# 站点: https://www.libvio.cam (MacCMS 三层架构: HTML + JSON API + 加密播放层)
# 定版依据: 71us模板v7.5 + 勃士13接口四壳协议
# 13接口=init/homeContent/homeVideoContent/categoryContent/searchContent/detailContent/playerContent/localProxy/isVideoFormat/manualVideoCheck/getDependence/destroy/progressVideo/setVideoFlags
# 四壳通用: TVBox/T4(只认555五接口) / 海阔/影视仓1.x(额外调扩展钩子) / 独立加载(无base.spider走兜底)
# ★版本兼容铁律: 全文件禁3.9+API(random.randbytes/removeprefix/removesuffix等; OK影视内置Python≤3.8教训2026-09)
# ★分隔符铁律: $=名称/地址 | #=选集 | $$$=线路; 严禁$$或$连选集; 线路名与地址$$$段数必须相等
# ★链路策略v5: 资源默认直连输出, 需剥壳/防盗链/KEY404 才走自建本地代理(init 自启 127.0.0.1:9979-9988)
# ★本地代理: playerContent 与 m3u8 重写均输出绝对地址 http://127.0.0.1:PORT/proxy?url=...; localProxy 返回 dict 契约(服务端 _norm 兼容 list)
#
# ── 本站实测结论 (2026-09 实盘验证) ──
# 分类 : /index.php/ajax/data?mid=1&tid={tid}&limit=&page=  → JSON {code,total,pagecount,list[]}
# 搜索 : /search/-------------.html?wd={kw}                   → HTML (AJAX的wd参数被站点忽略, 不可用)
# 详情 : /detail/{id}.html                                    → stui-vodlist__head(h3线路名) + stui-content__playlist(ul剧集)
# 播放 : /play/{id}-{sid}-{nid}.html                          → player_aaaa{flag,encrypt,from,url}
# 线路判定 (2026-09 实测):
#   lzm3u8 / *.m3u8|mp4 直链        → 直连输出 parse=0 (实测无 #EXT-X-KEY, 无需 Referer)
#   seven/hd0/4kvm (128位hex)       → artplayer 页 qualities 密文 → AES-128-CBC 解密 → secure.php m3u8 ✅
#   BBA (1152位hex, isSmartPlay=true) → smartPlay API 换密文 → AES 解密 → m3u8 ✅
#   quark/ucpan/baidu/kuake/qiyu    → 网盘页(非可播直链), 整条线路丢弃
#
# ── encrypt=3 解密链 (2026-09 实盘逐位复刻, 全线路跑通) ──
#   art = GET /static/player/artplayer/?url={hex}
#   ts  = art 页内 timestamp                    (每次会话实时变化, 严禁硬编码)
#   H   = md5(str(ts) + "RY7e48naFXPsLJC")     (32位hex; ASCII切片, 非hex解码)
#   key = H[16:32] (ASCII 16字节)   iv = H[:16] (ASCII 16字节)
#   主线(isSmartPlay=false): 密文 = art 页 qualities[0].url (base64, 含 \/ 转义需清理)
#   支线(isSmartPlay=true) : 密文 = POST smartPlay API 响应 url (BBA 1152位hex线路)
#   real = AES-128-CBC-decrypt(base64decode(密文), key, iv) → /video_m3u8/secure.php?skey=xxxx.m3u8
#   ★明文为 URL 转义形式, 必须原样使用(%2F/%2B 保留), 二次 quote/unquote = 返回"解密失败"
#   实测: sid1 seven 200/62839 · sid2 hd0 200/145566 · sid7 4kvm 200/163956 ✅
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
HOSTS = ['https://www.libvio.cam']  # ★ 多域名轮询(主在前), 防封容灾
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
# ★ 一级分类 (来源: 首页 /show/{id} 导航 + AJAX tid 实测)
CATEGORIES = {
    '1': '电影', '2': '电视剧', '3': '综艺', '4': '动漫',
    '6': '动作片', '7': '喜剧片', '8': '爱情片', '9': '科幻片', '10': '恐怖片',
    '11': '剧情片', '12': '战争片', '13': '国产剧', '14': '港台剧', '15': '日韩剧',
    '16': '海外剧', '17': '大陆综艺', '18': '港台综艺', '20': '日韩综艺', '21': '欧美综艺',
    '24': '国产动漫', '25': '日韩动漫', '26': '港台动漫', '27': '欧美动漫',
}
PK = 'RY7e48naFXPsLJC'       # ★ 解密 SALT (逆向后确认的站级常量)
API_HOST = 'http://hd.ticktockwow.com/smartplay-cache/api/webvideo_ty.php'   # ★ smartPlay 接口(https:443 实测超时, http 实测 code200)
API_HOSTS = (API_HOST, 'https://hd.ticktockwow.com/smartplay-cache/api/webvideo_ty.php')
REFERER = ''                # ★ 播放/资源防盗链Referer(空=用self.base)
PIC_REFERER = ''            # ★ 图片防盗链Referer(空=无)
FD_ZONE = 0                 # ★ 分片区段(71us .fd 协议用, 本站无)
PROBE = 0                   # ★ 详情多线路实测排序开关 1/0
SITE_KEY = 'libvio'         # ★ 壳源标识(海阔setVideoFlags回调时上报)
VIDEO_EXTS = 'm3u8|mp4|flv|mkv|avi|ts'  # ★ isVideoFormat判定扩展名
ND_PAT = ('quark|ucpan|baidu|kuake|qiyu|aliyundrive|123pan|夸克|百度|UC网盘|网盘|视频下载'
          '|drive.uc.cn|pan.quark.cn|pan.baidu.com|alipan')  # ★ 网盘/下载线路关键字(整条线路丢弃)

# ============ AES 纯Python引擎(Crypto不可用时降级) ============
SBOX = [99, 124, 119, 123, 242, 107, 111, 197, 48, 1, 103, 43, 254, 215, 171, 118, 202, 130, 201, 125, 250, 89, 71, 240, 173, 212, 162, 175, 156, 164, 114, 192, 183, 253, 147, 38, 54, 63, 247, 204, 52, 165, 229, 241, 113, 216, 49, 21, 4, 199, 35, 195, 24, 150, 5, 154, 7, 18, 128, 226, 235, 39, 178, 117, 9, 131, 44, 26, 27, 110, 90, 160, 82, 59, 214, 179, 41, 227, 47, 132, 83, 209, 0, 237, 32, 252, 177, 91, 106, 203, 190, 57, 74, 76, 88, 207, 208, 239, 170, 251, 67, 77, 51, 133, 69, 249, 2, 127, 80, 60, 159, 168, 81, 163, 64, 143, 146, 157, 56, 245, 188, 182, 218, 33, 16, 255, 243, 210, 205, 12, 19, 236, 95, 151, 68, 23, 196, 167, 126, 61, 100, 93, 25, 115, 96, 129, 79, 220, 34, 42, 144, 136, 70, 238, 184, 20, 222, 94, 11, 219, 224, 50, 58, 10, 73, 6, 36, 92, 194, 211, 172, 98, 145, 149, 228, 121, 231, 200, 55, 109, 141, 213, 78, 169, 108, 86, 244, 234, 101, 122, 174, 8, 186, 120, 37, 46, 28, 166, 180, 198, 232, 221, 116, 31, 75, 189, 139, 138, 112, 62, 181, 102, 72, 3, 246, 14, 97, 53, 87, 185, 134, 193, 29, 158, 225, 248, 152, 17, 105, 217, 142, 148, 155, 30, 135, 233, 206, 85, 40, 223, 140, 161, 137, 13, 191, 230, 66, 104, 65, 153, 45, 15, 176, 84, 187, 22]
IS = [0] * 256
for _i, _v in enumerate(SBOX):
    IS[_v] = _i
RCON = [1, 2, 4, 8, 16, 32, 64, 128, 27, 54, 108, 216, 171, 77]
G2 = [0] * 256
G3 = [0] * 256
for _i in range(256):
    _t = _i << 1
    if _i & 128:
        _t ^= 0x11b
    G2[_i] = _t
    G3[_i] = G2[_i] ^ _i


def _ke(k):
    """AES 密钥扩展: 返回轮密钥字数组 (每字4字节)"""
    nk = len(k) // 4
    nr = nk + 6
    w = [list(k[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = w[i - 1][:]
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [SBOX[b] for b in t]
            t[0] ^= RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w


def _gm(a, b):
    """GF(2^8) 乘法"""
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        a = (a << 1) ^ 0x11b if a & 0x80 else a << 1
        b >>= 1
    return p & 0xff


def _dec(b, w):
    """AES 单块解密 (状态按列优先展平); w=轮密钥字数组, 每字4字节"""
    nr = len(w) // 4 - 1
    s = list(b)
    for i in range(4):
        for j in range(4):
            s[4 * i + j] ^= w[nr * 4 + i][j]
    for rnd in range(nr - 1, -1, -1):
        # InvShiftRows (按列优先布局: s[4*c+r])
        for r in range(1, 4):
            row = [s[4 * c + r] for c in range(4)]
            row = row[-r:] + row[:-r]
            for c in range(4):
                s[4 * c + r] = row[c]
        # InvSubBytes
        s = [IS[x] for x in s]
        # AddRoundKey
        for i in range(4):
            for j in range(4):
                s[4 * i + j] ^= w[rnd * 4 + i][j]
        # InvMixColumns
        if rnd > 0:
            for c in range(4):
                a0, a1, a2, a3 = s[4 * c:4 * c + 4]
                s[4 * c + 0] = _gm(a0, 14) ^ _gm(a1, 11) ^ _gm(a2, 13) ^ _gm(a3, 9)
                s[4 * c + 1] = _gm(a0, 9) ^ _gm(a1, 14) ^ _gm(a2, 11) ^ _gm(a3, 13)
                s[4 * c + 2] = _gm(a0, 13) ^ _gm(a1, 9) ^ _gm(a2, 14) ^ _gm(a3, 11)
                s[4 * c + 3] = _gm(a0, 11) ^ _gm(a1, 13) ^ _gm(a2, 9) ^ _gm(a3, 14)
    return bytes(s)


def aes_cbc_dec(data, key, iv):
    """AES-128-CBC 解密 + PKCS7 去填充 (纯Python, 零依赖)"""
    if not data or len(data) % 16:
        return b''
    w = _ke(key)
    out = bytearray()
    prev = iv
    for off in range(0, len(data), 16):
        blk = data[off:off + 16]
        out += bytes(x ^ y for x, y in zip(_dec(list(blk), w), prev))
        prev = blk
    if out:
        pad = out[-1]
        if 0 < pad <= 16 and len(out) >= pad:
            out = out[:-pad]
    return bytes(out)


_SRV = {'srv': None, 'port': 0, 'sp': None}
_LOG = '/sdcard/Download/libvio_proxy.log'


def _plog(s):
    try:
        open(_LOG, 'a', encoding='utf-8').write(time.strftime('%m-%d %H:%M:%S ') + str(s) + chr(10))
    except Exception:
        pass


def _norm(r):
    code, ct, body, hd = 200, 'application/octet-stream', b'', {}
    try:
        if isinstance(r, dict):
            code = int(r.get('code') or 200)
            body = r.get('content')
            if body is None:
                body = r.get('body')
            hd = r.get('headers') or {}
            if not isinstance(hd, dict):
                hd = {}
            ct = hd.get('Content-Type') or r.get('content-type') or ct
        elif isinstance(r, (list, tuple)):
            if len(r) >= 4:
                code, ct, body = int(r[0]), r[1], r[2]
                if isinstance(r[3], dict):
                    hd = r[3]
            elif len(r) == 3:
                code, ct, body = int(r[0]), r[1], r[2]
            elif len(r) == 2:
                code, body = int(r[0]), r[1]
            elif len(r) == 1:
                body = r[0]
        elif r is not None:
            body = r
    except Exception:
        code, ct, body, hd = 500, 'text/plain', b'', {}
    if body is None:
        body = b''
    if isinstance(body, str):
        body = body.encode('utf-8')
    elif not isinstance(body, bytes):
        try:
            body = bytes(body)
        except Exception:
            body = b''
    if not isinstance(hd, dict):
        hd = {}
    return code, (ct or 'application/octet-stream'), body, hd


class _PH(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        return

    def do_GET(self):
        self._run(False)

    def do_HEAD(self):
        self._run(True)

    def do_OPTIONS(self):
        try:
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', '*')
            self.end_headers()
        except Exception:
            pass

    def _run(self, is_head):
        try:
            q = self.path.split('url=', 1)[1] if 'url=' in self.path else ''
            u = unquote(q) if q else ''
            sp = _SRV.get('sp')
            if is_head:
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()
                return
            if not u or sp is None:
                self.send_response(404)
                self.end_headers()
                return
            rng = self.headers.get('Range')
            code, ct, body, hd = _norm(sp._proxy(u, {'Range': rng} if rng else None))
            self.send_response(code)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Access-Control-Allow-Origin', '*')
            for k, v in hd.items():
                if str(k).lower() in ('content-type', 'content-length'):
                    continue
                self.send_header(str(k), str(v))
            self.end_headers()
            if body:
                self.wfile.write(body)
        except Exception as e:
            _plog('SRV-ERR ' + str(e)[:160])
            try:
                self.send_response(500)
                self.end_headers()
            except Exception:
                pass


def _srv_start(sp):
    if _SRV.get('srv') is not None:
        _SRV['sp'] = sp
        return _SRV.get('port') or 0
    _SRV['sp'] = sp
    for _p in range(9979, 9989):
        try:
            srv = http.server.ThreadingHTTPServer(('127.0.0.1', _p), _PH)
            srv.daemon_threads = True
            _SRV['srv'] = srv
            _SRV['port'] = _p
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            _plog('SRV-UP %d' % _p)
            return _p
        except Exception:
            continue
    _SRV['port'] = 0
    return 0


class Spider(Spider):
    # ========== 初始化 ==========
    def init(self, extend=''):
        self.base = HOSTS[0].rstrip('/')  # ★ 主域
        self.ua = UA
        self.pk = PK
        self.ref = REFERER or (self.base + '/')
        self.types = dict(CATEGORIES)
        self.filters = self._filters()  # ★ 二级分类筛选(来自 AJAX type_extend)
        self._pc = {}   # 线路probe缓存
        self._rc = {}   # 播放链缓存 {play_url: real_url}
        self._srv = None
        self._port = 0
        try:
            self._port = _srv_start(self)
            self._srv = _SRV.get('srv')
        except Exception:
            self._port = 0
        try:
            r = self.fetch(self.base, headers={'User-Agent': self.ua}, timeout=10000)
            if hasattr(r, 'url') and r.url and r.url != self.base:
                self.base = r.url.rstrip('/')
        except Exception:
            pass

    def _filters(self):
        """AJAX 接口返回的 type.type_extend 已内建完整筛选值, 此处静态内联避免开机慢"""
        def mk(items):
            return [{'n': x, 'v': x} for x in items]
        area = mk(['大陆', '香港', '台湾', '美国', '韩国', '日本', '泰国', '英国', '法国', '其它'])
        lang = mk(['国语', '英语', '粤语', '闽南语', '韩语', '日语', '其它'])
        year = mk([str(y) for y in range(2026, 2009, -1)])
        cls = {'1': ['喜剧', '爱情', '恐怖', '科幻', '动作', '战争', '剧情', '纪录片', '动画', '悬疑', '犯罪', '奇幻', '冒险', '历史', '传记', '灾难'],
               '2': ['古装', '战争', '青春偶像', '喜剧', '家庭', '犯罪', '动作', '奇幻', '剧情', '历史', '经典', '乡村', '情景', '商战', '网剧', '其他'],
               '3': ['真人秀', '音乐', '歌舞', '动画', '历史', '传记', '悬疑', '运动', '短片', '剧情', '家庭', '冒险', '灾难', '记录', '脱口秀', '其他'],
               '4': ['国产动漫', '日韩动漫', '港台动漫', '欧美动漫', '里番', '其他']}
        out = {}
        for k in self.types:
            f = []
            if k in cls:
                f.append({'key': 'class', 'name': '类型', 'value': mk(cls[k])})
            f.append({'key': 'area', 'name': '地区', 'value': area})
            f.append({'key': 'lang', 'name': '语言', 'value': lang})
            f.append({'key': 'year', 'name': '年份', 'value': year})
            out[k] = f
        return out

    # ========== 容灾: 请求双保险 ==========
    def _get(self, url, headers=None, timeout=15000, data=None, method=None):
        hd = headers or {'User-Agent': self.ua, 'Referer': self.ref}
        try:
            if data is not None:
                r = self.fetch(url, headers=hd, timeout=timeout, data=data, method=method or 'POST')
            else:
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

    def _json(self, url, headers=None, timeout=15000):
        t = self._get(url, headers or {'User-Agent': self.ua, 'Referer': self.ref,
                                       'X-Requested-With': 'XMLHttpRequest',
                                       'Accept': 'application/json, text/javascript, */*; q=0.01'},
                      timeout)
        if not t:
            return {}
        try:
            return json.loads(t)
        except Exception:
            m = re.search(r'\{[\s\S]*\}', t)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
            return {}

    def _pic(self, u):
        if not u:
            return ''
        u = u.replace('&amp;', '&').strip()
        if u.startswith('//'):
            u = 'https:' + u
        return u

    def _clean(self, s):
        if not s:
            return ''
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', str(s))).strip()

    def _sep(self, s):
        """分隔符铁律: 名称内 # → - , $ → |"""
        return self._clean(s).replace('#', '-').replace('$', '|').replace('$$$', '---').strip() or '播放'

    def _pagecount(self, h, cur=1):
        mx = cur
        for m in re.finditer(r'/(?:show|show)/\d+[^"\']*?(\d+)---\.html|page=(\d+)', h):
            try:
                n = int(m.group(1) or m.group(2))
                if n > mx:
                    mx = n
            except Exception:
                pass
        if re.search(r'下一页|next', h):
            mx = max(mx, cur + 1)
        return mx

    # ========== 8. 首页分类 ==========
    def homeContent(self, filter=False):
        r = {'class': [{'type_id': k, 'type_name': v} for k, v in self.types.items()]}
        if filter and self.filters:
            r['filters'] = self.filters
        try:
            r['list'] = self.homeVideoContent().get('list', [])
        except Exception:
            r['list'] = []
        return r

    # ========== 9. 首页推荐 (JSON API) ==========
    def homeVideoContent(self):
        out = []
        j = self._json('%s/index.php/ajax/data?mid=1&tid=1&limit=30&page=1' % self.base)
        for it in (j.get('list') or []):
            v = self._item(it)
            if v:
                out.append(v)
        if not out:  # 兜底: HTML
            h = self._get(self.base)
            out = self._items(h) if h else []
        return {'list': out}

    # ========== 10. 分类内容 ==========
    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        t, cls, ex2 = str(tid), '', ''
        if '|' in t:
            p = t.split('|')
            t = p[0]
            cls = p[1] if len(p) > 1 else ''
            ex2 = p[2] if len(p) > 2 else ''
        ex = {}
        if extend:
            try:
                ex = json.loads(extend) if isinstance(extend, str) else dict(extend)
            except Exception:
                ex = {}
        # 筛选值优先取 extend 内的 class/area/lang/year, 其次取 tid 展平段
        vcls = (ex.get('class') or cls or '').strip()
        varea = (ex.get('area') or '').strip()
        vlang = (ex.get('lang') or '').strip()
        vyear = (ex.get('year') or ex2 or '').strip()
        url = '%s/index.php/ajax/data?mid=1&tid=%s&limit=20&page=%d' % (self.base, t, pn)
        j = self._json(url)
        items = []
        for it in (j.get('list') or []):
            v = self._item(it)
            if not v:
                continue
            # 本地二次筛选(接口本身不支持筛选参数, 按 vod_class/area/lang/year 过滤)
            if vcls and vcls not in (v.get('_cls') or '') and vcls not in (v.get('type_name') or ''):
                continue
            if varea and varea not in (v.get('_area') or ''):
                continue
            if vlang and vlang not in (v.get('_lang') or ''):
                continue
            if vyear and vyear != (v.get('_year') or ''):
                continue
            v.pop('_cls', None); v.pop('_area', None); v.pop('_lang', None); v.pop('_year', None)
            v.pop('type_name', None)
            items.append(v)
        # 接口分页字段: total/pagecount
        total = j.get('total') or len(items)
        pc = j.get('pagecount') or 1
        if not items and not j:
            h = self._get(self._cat_html(t, pn, vcls, varea, vlang, vyear))
            if h:
                items = self._items(h)
                total = len(items)
                pc = self._pagecount(h, pn)
        return {'page': pn, 'pagecount': int(pc) if pc else 1,
                'limit': 20, 'total': int(total) if total else 0, 'list': items}

    def _cat_html(self, t, pn, cls='', area='', lang='', year=''):
        """MacCMS /show/{tid}-{area}-{lang}-{year}-{letter}-{order}-{page}.html (兜底通道)"""
        def e(x):
            return quote(str(x), safe='') if x else ''
        return '%s/show/%s--------%s-%s-%s-%s---%d.html' % (
            self.base, t, e(cls), e(year), '', '', pn) if False else \
            '%s/show/%s%s%s%s%s-----{}.html'.format(pn) % (
                self.base, t, '--------', '', '', '') if False else \
            '%s/show/%s--------%d---.html' % (self.base, t, pn)

    # ========== 11. 搜索 ==========
    def searchContent(self, key, quick=False, pg=1):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        kws = self._clean(key)
        if not kws:
            return {'page': pn, 'pagecount': 1, 'limit': 0, 'total': 0, 'list': []}
        kw = quote(kws, safe='')
        # 主力通道: HTML 搜索 (精确匹配; AJAX 的 wd 参数被站点忽略, 不可单独使用)
        out, seen = [], set()
        try:
            h = self._get('%s/search/-------------.html?wd=%s' % (self.base, kw))
            if h:
                for v in self._items(h):
                    if v['vod_id'] not in seen:
                        seen.add(v['vod_id'])
                        out.append(v)
        except Exception:
            out = []
        # 兜底通道: AJAX (必须本地按关键词过滤, 否则会返回全站列表)
        if not out:
            j = self._json('%s/index.php/ajax/data?mid=1&wd=%s&limit=20&page=%d' % (self.base, kw, pn))
            for it in (j.get('list') or []):
                nm = self._clean(it.get('vod_name'))
                if not nm or kws not in nm:
                    continue  # 本地严格过滤
                v = self._item(it)
                if v and v['vod_id'] not in seen:
                    seen.add(v['vod_id'])
                    out.append(v)
        return {'page': pn, 'pagecount': 1, 'limit': len(out) or 20, 'total': len(out), 'list': out}

    # ========== 12. 详情 ==========
    def detailContent(self, ids, quick='1'):
        try:
            if isinstance(ids, (list, tuple)):
                vid = str(ids[0]) if len(ids) else ''
            else:
                vid = str(ids or '')
        except Exception:
            vid = ''
        m = re.search(r'(\d+)', vid)
        vid = m.group(1) if m else ''
        if not vid:
            return {'list': []}
        h = self._get('%s/detail/%s.html' % (self.base, vid))
        if not h:
            return {'list': []}
        d = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_year': '', 'vod_area': '',
             'vod_class': '', 'vod_director': '', 'vod_actor': '', 'vod_content': '',
             'vod_remarks': '', 'vod_play_from': '', 'vod_play_url': ''}
        tn = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S) or re.search(r'<title>(.*?)</title>', h, re.S)
        if tn:
            d['vod_name'] = self._clean(tn.group(1)).split('-')[0].replace('免费在线观看', '') \
                .replace('高清完整版', '').replace('在线观看', '').strip()
        p = re.search(r'data-original="([^"]+)"', h) or \
            re.search(r'<img[^>]*(?:data-original|src)="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', h, re.I)
        if p:
            d['vod_pic'] = self._pic(p.group(1))
        dm = re.search(r'<span class="detail-content"[^>]*>([\s\S]*?)</span>', h) or \
            re.search(r'<span class="detail-sketch"[^>]*>([\s\S]*?)</span>', h)
        if dm:
            d['vod_content'] = self._clean(dm.group(1))[:600]
        for k, pat in (('vod_year', r'年份[：:]</span>\s*([^<]+)'),
                       ('vod_area', r'地区[：:]</span>\s*([^<]+)'),
                       ('vod_class', r'分类[：:]</span>\s*([^<]+)'),
                       ('vod_remarks', r'状态[：:]</span>\s*([^<]+)'),
                       ('vod_remarks', r'更新[：:]</span>\s*([^<]+)')):
            if not d[k]:
                m2 = re.search(pat, h)
                if m2:
                    d[k] = self._clean(m2.group(1)).rstrip('，,').strip()
        dm2 = re.search(r'导演[：:]</span>([\s\S]*?)(?:</p>|</div>)', h)
        if dm2:
            d['vod_director'] = self._clean(dm2.group(1)).rstrip('，,').strip()
        ac = re.search(r'主演[：:]</span>([\s\S]*?)(?:</p>|</div>)', h)
        if ac:
            d['vod_actor'] = self._clean(ac.group(1)).rstrip('，,').strip()
        pf, pu = self._play_sources(h)
        if pf:
            if PROBE and len(pf) > 1:
                pf, pu = self._sort_lines(pf, pu)
            d['vod_play_from'] = '$$$'.join(pf)
            d['vod_play_url'] = '$$$'.join(pu)
        return {'list': [d]}

    # ========== 13. 播放 ==========
    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = str(id or '')
        except Exception:
            url = ''
        hdr = {'User-Agent': self.ua, 'Referer': self.ref}
        empty = {'parse': 0, 'playUrl': '', 'url': '', 'header': ''}
        if not url:
            return empty
        # 网盘地址/网盘线路(非可播直链) → 直接放弃
        if self._is_nd(url) or self._is_nd(str(flag or '')):
            return empty
        # ① 播放页(.html) → 先取出真实 player_aaaa.url
        raw = url
        if re.search(r'/play/\d+-\d+-\d+\.html', url) or url.endswith('.html'):
            raw = self._play_url_of(url)
            if not raw:
                return empty
            # 页面内的线路名可能比 flag 更准, 再判一次网盘
            if self._is_nd(raw):
                return empty
        # ② 直链直出
        if re.match(r'^https?://', raw) and not self._is_hex(raw):
            return {'parse': 0, 'playUrl': '', 'url': raw, 'header': json.dumps(hdr)}
        # ③ 加密链 → 解析
        real = self._resolve(raw)
        if not real:
            return empty
        # 链路策略v4: m3u8 实测直连可用(无KEY), 仅在 403/防盗链/KEY404 时才走代理
        if self.isVideoFormat(real) and self._needs_proxy(real, hdr):
            return {'parse': 0, 'url': self._px(real),
                    'header': json.dumps(hdr), 'playUrl': ''}
        return {'parse': 0, 'playUrl': '', 'url': real, 'header': json.dumps(hdr)}

    def _play_url_of(self, playpage):
        """取 /play/ 页内 player_aaaa.url (可能是直链, 也可能是 hex 密文)"""
        if playpage in self._rc:
            return self._rc[playpage]
        u = ''
        try:
            h = self._get(playpage)
            if h:
                m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*;?\s*(?:</script>|\n)', h, re.S)
                if m:
                    j = json.loads(m.group(1))
                    u = j.get('url') or ''
        except Exception:
            u = ''
        self._rc[playpage] = u
        return u

    def _is_hex(self, s):
        return bool(s) and bool(re.match(r'^[0-9a-fA-F]+$', s)) and len(s) >= 64

    def _resolve(self, hexurl):
        """统一播放解析: hexurl -> 真实播放地址 (带缓存)"""
        if hexurl in self._rc:
            return self._rc[hexurl]
        real = ''
        try:
            if not self._is_hex(hexurl):
                real = hexurl if hexurl.startswith('http') else ''
            else:
                real = self._art(hexurl)
        except Exception:
            real = ''
        self._rc[hexurl] = real
        return real

    def _art(self, hexurl):
        """artplayer 页链路: 主线取 timestamp+qualities 密文; 支线走 smartPlay API"""
        art = self._get('%s/static/player/artplayer/?url=%s' % (self.base, hexurl))
        if not art:
            return ''
        enc, ok = self._cipher(art)
        if ok and enc:
            ts = self._ts_of(art)
            if not ts:
                return ''
            return self._aes_url(enc, ts)
        return self._smart(art)

    def _ts_of(self, art):
        """页内 timestamp (每次会话实时变化, 严禁硬编码)"""
        return (self._re1(art, r'timestamp\s*=\s*["\'](\d+)')
                or self._re1(art, r'timestamp\s*[:=]\s*(\d+)'))

    def _cipher(self, art):
        """取密文: 主线取 qualities[0].url; 返回 (密文, 是否主线可用)"""
        try:
            m = re.search(r'qualities\s*[:=]\s*\[([\s\S]*?)\]', art)
            if not m:
                return '', False
            seg = m.group(1)
            u = self._re1(seg, r'["\']?url["\']?\s*:\s*["\']([^"\']+)')
            if not u:
                return '', False
            u = u.replace('\\', '')
            if len(u) < 16 or len(u) % 4:
                return '', False
            return u, True
        except Exception:
            return '', False

    def _smart(self, art):
        """支线 isSmartPlay=true(BBA 1152位hex): POST smartPlay API 换密文 → AES 解密
        时间戳必须用当前时间(页面内 timestamp 为渲染时刻, 误差>30s 即 403 Invalid timestamp)"""
        try:
            ppu = self._re1(art, r'playPageUrl\s*=\s*["\']([^"\']+)')
            seed = self._re1(art, r'secretKeySeed\s*=\s*["\']([^"\']+)')
            if not ppu or not seed:
                return ''
            pts = self._ts_of(art)
            txt = ''
            for _try in range(2):
                t = int(time.time())
                body = json.dumps({'vkey': ppu, 'code': seed, 't': t,
                                   'signature': hashlib.md5(str(t).encode()).hexdigest()})
                try:
                    r = requests.post(API_HOSTS[min(_try, len(API_HOSTS) - 1)], headers={'User-Agent': self.ua, 'Content-Type': 'application/json',
                                                         'Origin': self.base, 'Referer': self.ref + '/'},
                                      data=body.encode(), timeout=15)
                    txt = r.text if hasattr(r, 'text') else str(r)
                except Exception:
                    txt = ''
                if txt and txt.strip().startswith('{') and '"code":200' in txt.replace(' ', ''):
                    break
                time.sleep(1)
            if not txt or not txt.strip().startswith('{'):
                return ''
            j = json.loads(txt)
            if str(j.get('code')) != '200':
                return ''
            cu = (j.get('url') or '').replace('\\', '').replace('\n', '').strip()
            if not cu:
                return ''
            return self._aes_url(cu, pts or str(int(time.time())))
        except Exception:
            return ''

    def _aes_url(self, enc, ts):
        """AES-128-CBC 解密 → 真实地址; 明文原样使用(保 %2F/%2B), 严禁二次编码"""
        try:
            cu = enc.strip()
            if re.match(r'^[0-9a-fA-F]{128,}$', cu):
                try:
                    if len(cu) % 2 == 0:
                        b = bytes.fromhex(cu)
                        s = b.decode('utf-8', 'ignore')
                        if s.startswith('/') or s.startswith('http'):
                            return self._full(s)
                except Exception:
                    pass
            raw = base64.b64decode(cu + '=' * (-len(cu) % 4))
            if not raw or len(raw) % 16:
                return ''
            H = hashlib.md5((str(ts) + self.pk).encode()).hexdigest()
            pt = aes_cbc_dec(raw, H[16:32].encode(), H[:16].encode())
            if not pt:
                return ''
            s = pt.decode('utf-8', 'replace').strip().strip('\x00')
            if not s:
                return ''
            return self._full(s)
        except Exception:
            return ''

    def _full(self, s):
        """拼接最终地址; 明文含 %2F/%2B 转义, 原样保留不做任何 quote/unquote"""
        s = s.strip()
        if s.startswith('//'):
            return 'https:' + s
        if s.startswith('/'):
            return self.base + s
        if s.startswith('http'):
            return s
        return ''

    def _re1(self, s, pat):
        m = re.search(pat, s)
        return m.group(1) if m else ''

    def _shell(self, b):
        """伪装壳检测: PNG/GIF/JPEG 头 + 壳后紧跟 TS(0x47) → 返回 (剥壳数据, 是否壳)"""
        try:
            if not b or len(b) < 200:
                return b, False
            if b[:8] == b'\x89PNG\r\n\x1a\n':
                e = b.find(b'IEND', 0, 4096)
                if e > 0 and e + 8 < len(b) and b[e + 8] == 0x47:
                    return b[e + 8:], True
            if b[:3] == b'GIF' and b.find(b'\x3b', 0, 1024) > 0:
                e = b.find(b'\x3b', 0, 1024)
                if e + 1 < len(b) and b[e + 1] == 0x47:
                    return b[e + 1:], True
            if b[:2] == b'\xff\xd8' and len(b) > 0:
                e = b.find(b'\xff\xd9', 0, 4096)
                if e > 0 and e + 2 < len(b) and b[e + 2] == 0x47:
                    return b[e + 2:], True
            return b, False
        except Exception:
            return b, False

    def _needs_proxy(self, url, hdr):
        """探测需 localProxy: 403/防盗链/KEY404/分片伪装壳(PNG壳TS)"""
        try:
            r = self.fetch(url, headers=dict(hdr, Range='bytes=0-4095'), timeout=8000)
            code = getattr(r, 'status_code', 200)
            if code and int(code) >= 400:
                return True
            body = (r.text if hasattr(r, 'text') else str(r)) or ''
            if '#EXT-X-KEY' in body:
                km = re.search(r'URI="([^"]+)"', body)
                if km:
                    try:
                        kr = self.fetch(urljoin(url, km.group(1)), headers=dict(hdr), timeout=8000)
                        if int(getattr(kr, 'status_code', 200)) >= 400:
                            return True
                    except Exception:
                        return True
            if '#EXT' in body:
                sm = re.search(r'^https?://\S+', body, re.M)
                if sm:
                    try:
                        sh = dict(hdr)
                        sh.pop('Referer', None)
                        sh.pop('Origin', None)
                        sh['Range'] = 'bytes=0-255'
                        sr = self.fetch(sm.group(0), headers=sh, timeout=8000)
                        sb = sr.content if hasattr(sr, 'content') else (
                            sr.text.encode('utf-8', 'replace') if hasattr(sr, 'text') else b'')
                        if self._shell(sb)[1]:
                            return True
                    except Exception:
                        return True
            return False
        except Exception:
            return True

    # ========== 1. isVideoFormat ==========
    def isVideoFormat(self, url):
        try:
            u = str(url or '').lower()
            path = u.split('?')[0]
            if any(path.endswith('.' + e) for e in VIDEO_EXTS.split('|')):
                return True
            # HLS 常在 query 里带 .m3u8 (如 ?url=xxx.m3u8 / getM3u8?name=)
            if '.m3u8' in u or 'getm3u8' in u or 'get_m3u8' in u:
                return True
            return False
        except Exception:
            return False

    # ========== 2. manualVideoCheck ==========
    def manualVideoCheck(self):
        return False

    # ========== 3. getDependence ==========
    def getDependence(self):
        return []

    # ========== 4. destroy ==========
    def destroy(self):
        try:
            if self._srv is not None:
                self._srv.shutdown()
                self._srv.server_close()
        except Exception:
            pass
        self._srv = None
        self._port = 0
        _SRV['srv'] = None
        _SRV['port'] = 0
        self._rc = {}
        return None

    # ========== 5. progressVideo ==========
    def progressVideo(self, url, pos, total):
        return None

    # ========== 6. setVideoFlags ==========
    def setVideoFlags(self, flags):
        try:
            self.flags = flags
        except Exception:
            pass
        return None

    # ========== 7. localProxy 兜底代理(init 自启 127.0.0.1:9979-9988 服务承接) ==========
    def _px(self, u):
        if not getattr(self, '_port', 0):
            try:
                self._port = _srv_start(self)
                self._srv = _SRV.get('srv')
            except Exception:
                self._port = 0
        if getattr(self, '_port', 0):
            return 'http://127.0.0.1:%d/proxy?url=%s' % (self._port, quote(u, safe=''))
        return 'proxy?url=' + quote(u, safe='')

    def _proxy(self, u, hdr=None):
        try:
            for _ in range(2):
                if u.lower().startswith('http://') or u.lower().startswith('https://'):
                    break
                _nu = unquote(u)
                if _nu == u:
                    break
                u = _nu
            if not u.lower().startswith('http'):
                return {'code': 404, 'content': b'', 'headers': {'Content-Type': 'text/plain'}}
            hd = {'User-Agent': self.ua, 'Referer': self.ref or self.base}
            hd.update(hdr or {})
            low = u.lower()
            is_m3u8 = ('.m3u8' in low) or ('mpegurl' in low) or ('getm3u8' in low) or ('get_m3u8' in low)
            if not is_m3u8:
                hd.pop('Referer', None)
                hd.pop('Origin', None)
            r = self.fetch(u, headers=hd, timeout=20000)
            code = int(getattr(r, 'status_code', 200) or 200)
            if code >= 400 and not is_m3u8:
                r2 = self.fetch(u, headers={}, timeout=20000)
                if int(getattr(r2, 'status_code', 200) or 200) < 400:
                    r = r2
                    code = int(getattr(r2, 'status_code', 200) or 200)
            ct = 'application/octet-stream'
            try:
                ct = r.headers.get('Content-Type', ct) or ct
            except Exception:
                pass
            body = r.content if hasattr(r, 'content') else (
                r.text.encode('utf-8', 'replace') if hasattr(r, 'text') else bytes(r))
            if is_m3u8 or ('mpegurl' in str(ct).lower()):
                return {'code': code, 'content': self._rewrite_m3u8(body, u, hd),
                        'headers': {'Content-Type': 'application/vnd.apple.mpegurl'}}
            body, is_shell = self._shell(body)
            if is_shell:
                return {'code': 200, 'content': body, 'headers': {'Content-Type': 'video/mp2t'}}
            h2 = {'Content-Type': ct}
            try:
                cr = r.headers.get('Content-Range')
                if cr:
                    h2['Content-Range'] = cr
            except Exception:
                pass
            return {'code': code, 'content': body, 'headers': h2}
        except Exception:
            return {'code': 500, 'content': b'', 'headers': {'Content-Type': 'text/plain'}}

    def localProxy(self, param):
        try:
            hdr = {}
            if isinstance(param, str):
                m = re.search(r'(?:^|[?&])url=([^&]+)', param)
                u = m.group(1) if m else param
            else:
                u = param.get('url') or ''
                hdr = param.get('header') or {}
                if isinstance(hdr, str):
                    try:
                        hdr = json.loads(hdr)
                    except Exception:
                        hdr = {}
            return self._proxy(u, hdr)
        except Exception:
            return {'code': 500, 'content': b'', 'headers': {'Content-Type': 'text/plain'}}

    def _rewrite_m3u8(self, body, base, hdr):
        """m3u8 内分片/KEY 统一改走 localProxy(剥壳: 本站分片为 PNG 头 + TS 伪装)"""
        try:
            txt = body.decode('utf-8', 'replace') if isinstance(body, bytes) else str(body)
            out = []
            for line in txt.split('\n'):
                s = line.strip()
                if not s:
                    out.append(line)
                    continue
                if s.startswith('#'):
                    def rp(m):
                        ku = m.group(1)
                        if ku.startswith('proxy?') or ku.startswith('data:') or '127.0.0.1' in ku:
                            return m.group(0)
                        return 'URI="' + self._px(urljoin(base, ku)) + '"'
                    out.append(re.sub(r'URI="([^"]+)"', rp, line))
                else:
                    if s.startswith('proxy?') or s.startswith('data:') or '127.0.0.1' in s:
                        out.append(s)
                        continue
                    out.append(self._px(urljoin(base, s)))
            return '\n'.join(out).encode('utf-8')
        except Exception:
            return body

    # ========== 通用: JSON条目 -> vod ==========
    def _item(self, it):
        try:
            vid = it.get('vod_id')
            if not vid:
                return None
            te = (it.get('type') or {}).get('type_extend') or {}
            name = self._clean(it.get('vod_name'))
            if not name:
                return None
            return {
                'vod_id': str(vid),
                'vod_name': name,
                'vod_pic': self._pic(it.get('vod_pic')),
                'vod_remarks': self._clean(it.get('vod_remarks')),
                'type_name': self._clean(it.get('type_name') or (it.get('type') or {}).get('type_name') or ''),
                '_cls': self._clean(it.get('vod_class') or te.get('class') or ''),
                '_area': self._clean(it.get('vod_area') or te.get('area') or ''),
                '_lang': self._clean(it.get('vod_lang') or te.get('lang') or ''),
                '_year': self._clean(it.get('vod_year') or te.get('year') or ''),
            }
        except Exception:
            return None

    # ========== 通用: HTML条目解析 (MacCMS 列表) ==========
    def _items(self, h):
        out = []
        if not h:
            return out
        seen = set()
        for m in re.finditer(r'<a[^>]+href="(/detail/(\d+)\.html)"[^>]*>', h):
            vid = m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            seg = h[m.start():m.start() + 900]
            nm = self._re1(seg, r'title="([^"]*)"') or self._re1(seg, r'alt="([^"]*)"')
            if not nm:
                continue
            pic = self._re1(seg, r'data-original="([^"]*)"') or self._re1(seg, r'src="([^"]*)"')
            rk = self._re1(seg, r'pic-text[^>]*>([^<]*)<') or self._re1(seg, r'text-right[^>]*>([^<]*)<')
            out.append({
                'vod_id': vid,
                'vod_name': self._clean(nm),
                'vod_pic': self._pic(pic),
                'vod_remarks': self._clean(rk),
            })
        return out

    # ========== 通用: 详情播放源解析 ==========
    def _play_sources(self, h):
        pf, pu = [], []
        if not h:
            return pf, pu
        lines = []
        for blk in re.finditer(r"<h3[^>]*>(.*?)</h3>(.{0,8000}?)</ul>", h, re.S):
            nm = self._clean(blk.group(1))
            eps = re.findall(r'href="(/play/[^"<>]+[.]html)"[^>]*>([^<]*)<', blk.group(2))
            if eps:
                lines.append((nm, eps))
        keep = [x for x in lines if not self._is_nd(x[0])]
        if not keep:
            keep = lines
        if not keep:
            groups = {}
            for m in re.finditer(r'href="(/play/([0-9]+)-([0-9]+)-([0-9]+)[.]html)"[^>]*>([^<]*)<', h):
                groups.setdefault(m.group(3), []).append((m.group(1), m.group(5) or m.group(4)))
            for i, gid in enumerate(sorted(groups, key=lambda x: int(x))):
                keep.append(('线路%d' % (i + 1), groups[gid]))
        for nm, eps in keep:
                nm2 = nm or (chr(32447) + chr(36335) + str(len(pf) + 1))
                self._add(pf, pu, nm2, eps)
        return pf, pu

    def _is_nd(self, nm):
        """判定网盘线路"""
        try:
            s = (nm or '').lower()
            for k in ND_PAT.split('|'):
                if k and k in s:
                    return True
            return False
        except Exception:
            return False

    def _add(self, pf, pu, nm, eps):
        """eps: [(href, epname)] ; 分隔符铁律: $=名称/地址, #=选集"""
        url = ''
        for i, (href, ep) in enumerate(eps):
            nm2 = self._sep(ep) or str(i + 1)
            full = urljoin(self.base, href)
            url += (('#' if i else '') + nm2 + '$' + full)
        if url:
            pf.append(self._sep(nm))
            pu.append(url)

    def _sort_lines(self, pf, pu):
        """多线路实测排序(probe): 可解出的排前"""
        try:
            order = []
            for i, u in enumerate(pu):
                first = u.split('#')[0].split('$')[-1]
                score = 0
                try:
                    raw = self._play_url_of(first) if first.endswith('.html') else first
                    if raw and not self._is_nd(raw):
                        real = self._resolve(raw)
                        if real and real.startswith('http'):
                            score = 2 if self.isVideoFormat(real) else 1
                except Exception:
                    score = 0
                order.append((score, i))
            order.sort(key=lambda x: (-x[0], x[1]))
            return [pf[i] for _, i in order], [pu[i] for _, i in order]
        except Exception:
            return pf, pu

# -*- coding: utf-8 -*-
# ============ 71us 模板 v7.5 ============
# 定版: 71us模板v7.4(555骨架+能力层) + 勃士13接口四壳协议 | 2026-09-07
# 13接口=init/homeContent/categoryContent/detailContent/searchContent/playerContent/localProxy/isVideoFormat/manualVideoCheck/getDependence/destroy/progressVideo/setVideoFlags
# 四壳通用: TVBox/T4(只认555五接口) / 海阔/影视仓1.x(额外调扩展钩子) / 独立加载(无base.spider走兜底)
# ★自动调用协议(套本模板写源/修复/重构/逆向=自动触发, 先过清单再动手, 缺一不可):
# ①记忆库检索: query_memory『知识库/影视源开发』→《py源开发技能清单v18》(v18>v17>v16), 开工即查
# ②技能包11包分层调度(/sdcard/Download/Operit/skills/):
#   L0骨架 tvbox-py-v73(本模板母版) | L1入口 pySkill(spider-create全类型7内容) | L2攻坚 gpt56全家桶(eni/INDEX.md路由90项+kit冷咖啡+five_blade五刃)+reverse-skill(87技能逆向路由)+遮天九秘_破甲版(zhetian.py/cf-bypass/aes-decrypt) | L3质量 adaptive四工作台(播放契约/响应边界/图片资源/清洗规范化)并行套用 | L4交付 wei-ai-xiao-ge(影视仓加载契约/测试矩阵)+jk-lingyu-spider(MacCMS/Txmojia样本)
# ③交付铁律: py_compile → 555契约字段(coding/sys.path/class Spider(Spider)/init(extend)/homeContent/homeVideoContent/searchContent/categoryContent/playerContent) → 模拟T4全调用链 → 播放链验证 → 双份md5一致
# 用法: 只改 ★ 区(CONFIG/init), 其余通用; 站点无某项能力直接省略对应方法调用
# 加载契约: 首行coding/sys.path.append('..')/from base.spider import Spider(带兜底)/class Spider(Spider)
# ★版本兼容铁律: 全文件禁3.9+API(random.randbytes/removeprefix/removesuffix等; OK影视内置Python≤3.8教训2026-09), 随机字节用bytes([random.randrange(1,256)]), 交付前grep -n 'randbytes'自查
# ★分隔符铁律: $=名称/地址 | #=选集 | $$$=线路; 严禁$$或$连选集; 线路名与地址$$$段数必须相等
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
HOSTS = ['https://www.fjszjm.com']  # ★ 多域名轮询(主在前), 防封容灾
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
CATEGORIES = {'1': '电影', '2': '电视剧', '3': '综艺', '4': '动漫', '5': '短剧'}  # ★ 一级; 二三级展平 '1|剧情' '1|剧情|2024'
PK = ''  # ★ 接口密钥(签名/AES key/解密用)
REFERER = 'https://www.fjszjm.com/'  # ★ 播放/资源防盗链Referer(空=用self.base)
PIC_REFERER = 'https://www.fjszjm.com/'  # ★ 图片防盗链Referer(空=无)
FD_ZONE = 0  # ★ 分片区段(71us .fd 协议用, 无则0)
PROBE = 0  # ★ 详情多线路实测排序开关 1/0
SITE_KEY = 'fjszjm'  # ★ 壳源标识(海阔setVideoFlags回调时上报, 调试多源用)
VIDEO_EXTS = 'm3u8|mp4|flv|mkv|avi|ts'  # ★ isVideoFormat判定扩展名(竖线分隔)

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


def _enc(b, w):
    s = [[b[r + 4 * c] for c in range(4)] for r in range(4)]
    def add(r):
        for i in range(4):
            for j in range(4):
                s[i][j] ^= w[r * 4 + j][i]
    def sub():
        for i in range(4):
            for j in range(4):
                s[i][j] = SBOX[s[i][j]]
    def sh():
        for r in range(1, 4):
            s[r] = s[r][r:] + s[r][:r]
    def mx():
        for c in range(4):
            a = [s[r][c] for r in range(4)]
            s[0][c] = G2[a[0]] ^ G3[a[1]] ^ a[2] ^ a[3]
            s[1][c] = a[0] ^ G2[a[1]] ^ G3[a[2]] ^ a[3]
            s[2][c] = a[0] ^ a[1] ^ G2[a[2]] ^ G3[a[3]]
            s[3][c] = G3[a[0]] ^ a[1] ^ a[2] ^ G2[a[3]]
    add(0)
    nr = len(w) // 4 - 1
    for rnd in range(1, nr):
        sub()
        sh()
        mx()
        add(rnd)
    sub()
    sh()
    add(nr)
    return bytes(s[r][c] for c in range(4) for r in range(4))


def _gm(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        a = (a << 1) ^ 0x11b if a & 0x80 else a << 1
        b >>= 1
    return p & 0xff


def _dec(b, w):
    s = [[b[r + 4 * c] for c in range(4)] for r in range(4)]
    def add(r):
        for i in range(4):
            for j in range(4):
                s[i][j] ^= w[r * 4 + j][i]
    def isub():
        for i in range(4):
            for j in range(4):
                s[i][j] = IS[s[i][j]]
    def ish():
        for r in range(1, 4):
            s[r] = s[r][-r:] + s[r][:-r]
    def imx():
        for c in range(4):
            a = [s[r][c] for r in range(4)]
            s[0][c] = _gm(a[0], 14) ^ _gm(a[1], 11) ^ _gm(a[2], 13) ^ _gm(a[3], 9)
            s[1][c] = _gm(a[0], 9) ^ _gm(a[1], 14) ^ _gm(a[2], 11) ^ _gm(a[3], 13)
            s[2][c] = _gm(a[0], 13) ^ _gm(a[1], 9) ^ _gm(a[2], 14) ^ _gm(a[3], 11)
            s[3][c] = _gm(a[0], 11) ^ _gm(a[1], 13) ^ _gm(a[2], 9) ^ _gm(a[3], 14)
    nr = len(w) // 4 - 1
    add(nr)
    for rnd in range(nr - 1, 0, -1):
        ish()
        isub()
        add(rnd)
        imx()
    ish()
    isub()
    add(0)
    return bytes(s[r][c] for c in range(4) for r in range(4))


def aes_ecb(data, key, mode=1):
    w = _ke(key)
    out = b''
    if mode:
        pad = 16 - len(data) % 16
        data += bytes([pad]) * pad
        for i in range(0, len(data), 16):
            out += _enc(data[i:i + 16], w)
    else:
        for i in range(0, len(data), 16):
            out += _dec(data[i:i + 16], w)
        if out and 0 < out[-1] <= 16:
            out = out[:-out[-1]]
    return out


def aes_cbc(data, key, iv, enc=1):
    w = _ke(key)
    out = b''
    prev = iv
    if enc:
        pad = 16 - len(data) % 16
        data += bytes([pad]) * pad
        for i in range(0, len(data), 16):
            blk = bytes(data[i + j] ^ prev[j] for j in range(16))
            ct = _enc(blk, w)
            out += ct
            prev = ct
    else:
        for i in range(0, len(data), 16):
            blk = _dec(data[i:i + 16], w)
            out += bytes(blk[j] ^ prev[j] for j in range(16))
            prev = data[i:i + 16]
        if out and 0 < out[-1] <= 16:
            out = out[:-out[-1]]
    return out


class Spider(Spider):
    def init(self, extend=''):
        self.base = HOSTS[0].rstrip('/')  # ★ 主域(init内可被重定向更新)
        self.ua = UA
        self.pk = PK
        self.ref = REFERER or self.base
        self.types = dict(CATEGORIES)
        self.filters = {}  # ★ {'1':[{'key':'class','name':'类型','value':[{'n':'剧情','v':'剧情'}]}]}
        self._pc = {}  # 线路probe缓存 {md5:[ts,froms,urls]}
        self._srv = None  # 本地代理线程(延迟启动)
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
    def _pic(self, u):
        if not u:
            return ''
        if u.startswith('//'):
            u = 'https:' + u
        if not u.startswith('http'):
            u = urljoin(self.base, u)
        return u  # 直连优先; 403时 playerContent/localProxy 兜底

    def _pagecount(self, h, cur=1):
        mx = cur
        for m in re.finditer(r"/(?:vodshow|s|wfmwusw)/\d+[^\"']*?(\d+)(?:---|-)\.html|page=(\d+)", h):
            try:
                n = int(m.group(1) or m.group(2))
                if n > mx:
                    mx = n
            except:
                pass
        if re.search(r'下一页|class="[^"]*next[^"]*"', h):
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
        return {'list': self._items(h) if h else []}

    # ========== 分类(1/2/3级展平+筛选+动态翻页) ==========
    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        try:
            pn = max(int(str(pg)), 1)
        except:
            pn = 1
        t, cls, ex2 = str(tid), '', ''
        if '|' in t:
            p = t.split('|')
            t, cls = p[0], p[1] if len(p) > 1 else ''
            ex2 = p[2] if len(p) > 2 else ''
        ex = {}
        if extend:
            try:
                ex = json.loads(extend) if isinstance(extend, str) else dict(extend)
            except:
                ex = {}
        h = self._get(self._cat_url(t, pn, cls, ex2, ex))
        if not h:
            return {'page': pn, 'pagecount': 1, 'limit': 42, 'total': 0, 'list': []}
        items = self._items(h)
        return {'page': pn, 'pagecount': self._pagecount(h, pn), 'limit': 42, 'total': len(items), 'list': items}

    def _cat_url(self, t, pn, cls='', ex2='', ex=None):
        # ★ 按站改: v10 /vodshow/{t}--------{pn}---.html | v8 /search.php?searchtype=5&tid={t}&page={pn}
        # 自定义API站: 直接拼接口(带self.pk签名/AES参数)
        return f'{self.base}/wfmwusw/{t}--------{pn}---.html'

    # ========== 详情(多线路 + probe实测排序) ==========
    def detailContent(self, ids, quick='1'):
        vid = str(ids[0] if isinstance(ids, list) else ids or '')
        m = re.search(r'(\d+)', vid)
        vid = m.group(1) if m else ''
        if not vid:
            return {'list': []}
        h = self._get(f'{self.base}/wfmwudt/{vid}.html')
        if not h:
            return {'list': []}
        d = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_year': '', 'vod_area': '',
             'vod_class': '', 'vod_director': '', 'vod_actor': '', 'vod_content': '',
             'vod_remarks': '', 'vod_play_from': '', 'vod_play_url': ''}
        tn = re.search(r'<h1[^>]*>(.*?)</h1>', h) or re.search(r'<title>(.*?)</title>', h)
        if tn:
            d['vod_name'] = re.sub(r'<[^>]+>', '', tn.group(1)).split('-')[0].replace('免费在线观看', '').replace('高清完整版', '').strip()
        p = re.search(r'data-original="([^"]+\.(?:jpg|jpeg|png|webp|gif))"', h, re.I)
        if not p:
            p = re.search(r'<img[^>]*(?:data-original|src)="([^"]+\.(?:jpg|jpeg|png|webp|gif))"', h, re.I)
        if p:
            d['vod_pic'] = self._pic(p.group(1))
        dm = re.search(r'class="detail-content"[^>]*>([\s\S]*?)</span>', h) or re.search(r'class="[^"]*(?:vod-content|detail-sketch)[^"]*"[^>]*>([\s\S]*?)</span>', h)
        if dm:
            d['vod_content'] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', dm.group(1))).strip()[:500]
        for k, pat in (('vod_year', r'年份[：:]?\s*(\d{4})'), ('vod_area', r'地区[：:]?\s*([^<\n]+?)(?:\s|</)'),
                       ('vod_class', r'(?:类型|分类)[：:]?\s*([^<\n]+?)(?:\s|</)'), ('vod_remarks', r'更新[：:]</span>\s*([^<\n]+?)(?:\s|</)'),
                       ('vod_remarks', r'状态[：:]?\s*<[^>]*>([^<\n]+?)(?:</|\s|&)')):
            if d[k] == '':
                m2 = re.search(pat, h)
                if m2:
                    d[k] = re.sub(r'<[^>]+>', '', m2.group(1)).strip().replace('&nbsp;', ' ').replace('&amp;', '&').rstrip('，').strip()
        dm2 = re.search(r'导演[：:]\s*([\s\S]*?)(?:</p>|</div>|<div)', h)
        if dm2:
            d['vod_director'] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', dm2.group(1))).strip().replace('&nbsp;', ' ').replace('&amp;', '&').rstrip('，').strip()
        ac = re.search(r'主演[：:]\s*([\s\S]*?)(?:</p>|</div>|<div)', h)
        if ac:
            d['vod_actor'] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', ac.group(1))).strip().replace('&nbsp;', ' ').replace('&amp;', '&').rstrip('，').strip()
        pf, pu = self._play_sources(h)
        if pf:
            if PROBE and len(pf) > 1:
                pf, pu = self._sort_lines(pf, pu)
            d['vod_play_from'] = '$$$'.join(pf)
            d['vod_play_url'] = '$$$'.join(pu)
        return {'list': [d]}

    def _play_sources(self, h):
        pf, pu = [], []
        # 线路名: nav-tabs 中 #playlistN → 名称
        tab_names = {}
        for m in re.finditer(r'<a[^>]*href="#(playlist\d+)"[^>]*>([^<]+)</a>', h):
            n = m.group(2).strip()
            if n and len(n) < 20:
                tab_names[m.group(1)] = n
        # 选集: 每个 #playlistN 容器内的 /wfmwupy/ 链接(过滤 app 推广)
        for mid in re.finditer(r'id="(playlist\d+)"', h):
            pid = mid.group(1)
            box = h[mid.end():mid.end() + 6000]
            end = box.find('</div>')
            seg = box[:end] if end > 0 else box
            links = re.findall(r'href="(/wfmwupy/\d+-\d+-\d+\.html)"[^>]*>([^<]+)</a>', seg)
            links = [x for x in links if 'app2' not in x[0] and 'zstv' not in x[0] and x[1].strip()]
            if not links:
                continue
            pf.append(tab_names.get(pid, f'线路{len(pf) + 1}'))
            pu.append('#'.join(f'{ep.strip().replace("#", "-").replace("$", "|")}${urljoin(self.base, href)}' for href, ep in links))
        if not pf:  # 兜底: 全局按线路分组
            routes = {}
            for href, route, ep in re.findall(r'href="(/wfmwupy/\d+-(\d+)-\d+\.html)"[^>]*>([^<]+)</a>', h):
                if 'app2' in href or 'zstv' in href or not ep.strip():
                    continue
                routes.setdefault(route, []).append(f'{ep.strip().replace("#", "-").replace("$", "|")}${urljoin(self.base, href)}')
            for i, route in enumerate(sorted(routes.keys(), key=lambda x: int(x) if x.isdigit() else 999)):
                pf.append(tab_names.get(f'playlist{route}', f'线路{i + 1}'))
                pu.append('#'.join(routes[route]))
        return pf, pu

    def _sort_lines(self, froms, urls):
        key = hashlib.md5('|'.join(froms).encode()).hexdigest()
        c = self._pc.get(key)
        if c and time.time() - c[0] < 300:
            return c[1], c[2]
        def probe(i):
            u = urls[i].split('#')[0].rsplit('$', 1)[-1]
            try:
                r = requests.head(urljoin(self.base, u), headers={'User-Agent': self.ua}, timeout=5)
                return 0 if r.status_code < 400 else 1
            except:
                return 1
        with ThreadPoolExecutor(max_workers=min(len(froms), 8)) as ex:
            res = list(ex.map(probe, range(len(froms))))
        pairs = sorted(zip(froms, urls, res), key=lambda x: x[2])
        out = ([p[0] for p in pairs], [p[1] for p in pairs])
        self._pc[key] = [time.time()] + list(out)
        return out

    # ========== 搜索 ==========
    def searchContent(self, key, quick=False, pg='1'):
        try:
            pn = max(int(str(pg)), 1)
        except:
            pn = 1
        h = self._get(f'{self.base}/wfmwusc/{quote(key)}-------------.html')
        return {'list': self._items(h) if h else [], 'page': pn}

    # ========== 播放: 直连优先 → 解密 → VIP插槽 ==========
    def playerContent(self, flag, id, vipFlags=None):
        url = str(id) if id else str(flag)
        if '://' in url and re.search(r'\.(m3u8|mp4|flv|mp3)(\?|$)', url, re.I):
            return {'parse': 0, 'url': url}  # 直连
        full = url if url.startswith('http') else urljoin(self.base, url)
        h = self._get(full)
        if not h:
            return {'parse': 0, 'url': ''}
        u = self._parse_play(h, full)
        if not u:
            u = self._vip_try(full, h, vipFlags)  # 会员: 能破则破, 服务端硬锁放弃
        return {'parse': 0, 'url': u}

    def _parse_play(self, h, page_url):
        pd = re.search(r'var\s+player_\w+\s*=\s*(\{[\s\S]*?\})\s*[;<]', h)
        if pd:
            try:
                j = json.loads(pd.group(1))
                u = j.get('url', '') or j.get('url_next', '')
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
        for m in re.finditer(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4|flv))', h):
            return m.group(1)
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', h, re.I)
        if iframe:
            u = iframe.group(1)
            if u.startswith('http'):
                h2 = self._get(u)
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

    # ========== 四壳13接口扩展钩子(v7.5): isVideoFormat/manualVideoCheck/getDependence/destroy/progressVideo/setVideoFlags ==========
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

    # ========== 本地代理(9979-9988): m3u8 KEY/分片重写 + 图片转码 ==========
    def localProxy(self, param):
        p = param.split('url=', 1)[-1] if 'url=' in param else param
        p = unquote(p) if '%' in p else p
        if re.search(r'\.(jpe?g|png|webp|gif)(\?|$)', p, re.I):
            return self._img(p)
        if '.m3u8' in p:
            return self._rewrite_m3u8(p)
        try:
            r = self.fetch(p, headers={'User-Agent': self.ua, 'Referer': self.ref}, timeout=20000)
            if hasattr(r, 'status_code') and r.status_code != 200:
                return {'code': r.status_code, 'content': b'', 'headers': {}}
            return {'code': 200, 'content': r.content, 'headers': {'Content-Type': r.headers.get('Content-Type', 'application/octet-stream')}}
        except:
            return {'code': 404, 'content': b'', 'headers': {}}

    def _rewrite_m3u8(self, url):
        try:
            r = self.fetch(url, headers={'User-Agent': self.ua, 'Referer': self.ref}, timeout=20000)
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
                        ku = origin + ku  # 根相对路径拼origin
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

    # ========== 列表解析(通用MacCMS结构, 2级兜底) ==========
    def _items(self, h):
        items, seen = [], set()
        pats = [r'href="/(?:voddetail|movie/index|detail|n|wfmwudt)/(\d+)\.html"[^>]*title="([^"]*)"',
                r'href="/(?:voddetail|movie/index|detail|n|wfmwudt)/(\d+)\.html"[^>]*>([\s\S]{0,200}?)</a>']
        for pat in pats:
            for m in re.finditer(pat, h):
                vid, name = m.group(1), re.sub(r'<[^>]+>', '', m.group(2)).strip()
                if not name or len(name) > 100:
                    continue
                after = h[m.end():m.end() + 800]
                cover = re.search(r'(?:data-original|original|src)="([^"]+\.(?:jpg|jpeg|png|webp|gif))"', after, re.I)
                remark = re.search(r'class="pic-text text-right"[^>]*>\s*<b>([^<]+)</b>', after)
                if not remark:
                    remark = re.search(r'class="(?:module-item-note|public-list-prb|remarks|status|myui-vodlist__thumb)[^"]*"[^>]*>([^<]+)<', after)
                if not remark:
                    remark = re.search(r'<div[^>]*class="[^"]*(?:note|text|remark)[^"]*"[^>]*>([^<]+)<', after, re.I)
                if vid not in seen:
                    seen.add(vid)
                    items.append({'vod_id': vid, 'vod_name': name[:50],
                                  'vod_pic': self._pic(cover.group(1)) if cover else '',
                                  'vod_remarks': remark.group(1).strip() if remark else ''})
            if items:
                break
        return items

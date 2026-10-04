"""
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: 'MissAV',
  lang: 'hipy',
})
"""
# -*- coding: utf-8 -*-
import os
import copy
import gzip
import json
import re
import sys
import time
import base64
import requests
import threading
import subprocess
import urllib.parse
from base64 import b64decode
from pyquery import PyQuery as pq

# 尝试导入终极指纹伪装库
try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
    CFFI_SESSION = None  # 👑 全局长连接池
except ImportError:
    HAS_CFFI = False
    CFFI_SESSION = None

# 禁用 SSL 安全警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.append('..')
from base.spider import Spider

# ==================== 过盾层：指纹门票 → 免挑战直连 → 解析器兜底 ====================
# 设计目标：页面请求全部收进三级通道，任一级被盾拦自动降级；调用方(解析代码)一行都不用改。
#   ① 指纹门票通道：curl_cffi 浏览器 TLS/H2 指纹 + cf_clearance 门票，HTTP/2 长连接复用，最快
#   ② 免挑战直连：requests 直连实测免挑战路径（/cn/genres、/cn/makers、/search/*、/cn/{slug}）
#   ③ 解析器兜底：FlareSolverr 无头浏览器渲染过盾 → 换回门票(cf_clearance+UA) → 回到 ①
# 门票内存 + 落盘(24h)复用；页面缓存 2h；失败带断点诊断；错站/镜像入口拉黑，防止反代串数据。
#
# 站点候选（实测：.ws 免挑战路径直通，.ai/.live 为挑战档；候选按顺序试，带本站特征校验兜底）

DEFAULT_SITES = ('https://missav.ws', 'https://missav.ai', 'https://missav.live')
SITE_NAME = 'MissAV'
_SITE_SIGS = ('missav', 'fourhoi.com', 'surrit.com')

DEFAULT_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

DEFAULT_FLARE_URL = 'http://192.168.31.2:8191/v1'
DEFAULT_FLARE_PROXY = 'http://192.168.31.2:7890'

# 门票（cookie+UA）硬盘持久化路径
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'missav_cf_cache.json')
TICKET_TTL = 86400          # 门票 24h 内有效
PAGE_TTL = 7200             # 页面缓存 2h

# 全局状态池
_TICKET = {'cookies': {}, 'ua': '', 'ready': False, 'ts': 0}
_TICKET_LOCK = threading.Lock()
_PAGE_CACHE = {}
_PAGE_LOCK = threading.Lock()
_FLARE_STATE = {'busy': False, 'fail_until': 0.0, 'lock': threading.Lock()}

CFFI_SESSION = None         # 指纹长连接池（HTTP/2 多路复用）
_CFFI_LOCK = threading.Lock()
_CFFI_KEY = ('', '')        # (ua, proxy) 指纹会话签名，变了就重建


def _pick_impersonate(ua):
    """按门票 UA 选择指纹目标（UA 与指纹必须一致，否则盾照样拦）"""
    m = re.search(r'Chrome/(\d+)', ua or '')
    if m:
        ver = m.group(1)
        for cand in ('chrome131', 'chrome124', 'chrome120', 'chrome116', 'chrome110'):
            if cand.endswith(ver):
                return cand
    return 'chrome124'


def _build_cffi_session(ua, proxy=''):
    """建立/复用指纹长连接池"""
    global CFFI_SESSION, _CFFI_KEY
    if not HAS_CFFI:
        return None
    key = (ua or '', proxy or '')
    with _CFFI_LOCK:
        if CFFI_SESSION is not None and _CFFI_KEY == key:
            return CFFI_SESSION
        try:
            if CFFI_SESSION is not None:
                try:
                    CFFI_SESSION.close()
                except Exception:
                    pass
            kw = {'impersonate': _pick_impersonate(ua), 'verify': False, 'timeout': 20}
            if proxy:
                kw['proxies'] = {'http': proxy, 'https': proxy}
            CFFI_SESSION = cffi_requests.Session(**kw)
            _CFFI_KEY = key
        except Exception:
            CFFI_SESSION = None
    return CFFI_SESSION


def _ticket_load():
    """开局从硬盘恢复门票，实现秒开"""
    if _TICKET.get('ready'):
        return True
    try:
        if not os.path.exists(CACHE_FILE):
            return False
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if time.time() - float(data.get('ts', 0)) >= TICKET_TTL:
            return False
        cookies = data.get('cookies') or {}
        if not cookies:
            return False
        with _TICKET_LOCK:
            _TICKET['cookies'] = cookies
            _TICKET['ua'] = data.get('ua', '') or ''
            _TICKET['ts'] = float(data.get('ts', 0))
            _TICKET['ready'] = True
        return True
    except Exception:
        return False


def _ticket_save(cookies, ua):
    """门票落盘：下次开客户端直接复用"""
    if not cookies:
        return
    with _TICKET_LOCK:
        _TICKET['cookies'] = dict(cookies)
        _TICKET['ua'] = ua or ''
        _TICKET['ts'] = time.time()
        _TICKET['ready'] = True
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'cookies': dict(cookies), 'ua': ua or '', 'ts': time.time()}, f)
    except Exception:
        pass


def _ticket_clear():
    """门票失效：清内存 + 删硬盘"""
    with _TICKET_LOCK:
        _TICKET['cookies'] = {}
        _TICKET['ua'] = ''
        _TICKET['ready'] = False
        _TICKET['ts'] = 0
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
    except Exception:
        pass


def _ticket_cookie_str():
    with _TICKET_LOCK:
        return '; '.join(['%s=%s' % (k, v) for k, v in _TICKET['cookies'].items()])


def _page_get(url):
    with _PAGE_LOCK:
        item = _PAGE_CACHE.get(url)
    if not item:
        return None
    expire, html = item
    if expire < time.time():
        with _PAGE_LOCK:
            _PAGE_CACHE.pop(url, None)
        return None
    return html


def _page_put(url, html):
    with _PAGE_LOCK:
        _PAGE_CACHE[url] = (time.time() + PAGE_TTL, html)
        if len(_PAGE_CACHE) > 200:
            for k in sorted(_PAGE_CACHE.keys(), key=lambda x: _PAGE_CACHE[x][0])[:50]:
                _PAGE_CACHE.pop(k, None)


def _is_challenge(status, text, headers=None):
    """盾识别：标题/脚本特征 + cf-mitigated 头 + 短 403"""
    low = (text or '').lower()
    if 'just a moment' in low or 'cf-browser-verification' in low or 'cf_chl_' in low:
        return True
    try:
        if 'cf-mitigated' in str(headers or '').lower():
            return True
    except Exception:
        pass
    if status in (403, 503) and len(text or '') < 20000:
        return True
    return False


def _is_ours(html):
    """本站特征校验：防止反代/镜像/停放页拿别站内容冒充"""
    if not html or len(html) < 2000:
        return False
    low = html.lower()
    for sig in _SITE_SIGS:
        if sig in low:
            return True
    return False


def _fp_headers(ua, referer='', cookie=''):
    """与指纹对齐的请求头（Client Hints 必须跟 UA 一致）"""
    headers = {
        'User-Agent': ua or DEFAULT_UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7',
        'Accept-Encoding': 'gzip, deflate',
        'Upgrade-Insecure-Requests': '1',
        'Connection': 'keep-alive',
    }
    if referer:
        headers['Referer'] = referer
    if cookie:
        headers['Cookie'] = cookie
    m = re.search(r'Chrome/(\d+)', ua or '')
    if m:
        cv = m.group(1)
        headers['Sec-Ch-Ua'] = '"Chromium";v="%s", "Google Chrome";v="%s", "Not-A.Brand";v="99"' % (cv, cv)
        headers['Sec-Ch-Ua-Mobile'] = '?0'
        headers['Sec-Ch-Ua-Platform'] = '"Windows"'
    return headers


def _flare_solve(url, flare_url, proxy_url='', session_name='missav_drpy_master', timeout=35):
    """解析器通道：无头浏览器渲染过盾 → 返回 (html, cookies, ua)；失败返回 (None, {}, '')"""
    try:
        payload = {'cmd': 'request.get', 'url': url, 'maxTimeout': int(float(timeout) * 1000),
                   'session': session_name}
        if proxy_url:
            payload['proxy'] = {'url': proxy_url}
        resp = requests.post(flare_url, headers={'Content-Type': 'application/json'},
                             json=payload, timeout=float(timeout) + 15)
        data = resp.json()
        msg = str(data.get('message', '')).lower()
        if data.get('status') == 'error' and 'session' in msg:
            create = {'cmd': 'sessions.create', 'session': session_name}
            if proxy_url:
                create['proxy'] = {'url': proxy_url}
            requests.post(flare_url, json=create, timeout=20)
            resp = requests.post(flare_url, headers={'Content-Type': 'application/json'},
                                 json=payload, timeout=float(timeout) + 15)
            data = resp.json()
        if data.get('status') != 'ok':
            return None, {}, ''
        sol = data.get('solution') or {}
        html = sol.get('response') or ''
        if not html or _is_challenge(200, html) or not _is_ours(html):
            return None, {}, ''
        cookies = {}
        for c in (sol.get('cookies') or []):
            try:
                cookies[c['name']] = c['value']
            except Exception:
                continue
        return html, cookies, (sol.get('userAgent') or '')
    except Exception:
        return None, {}, ''


# ==================== 铁律11：古典映射脱敏词典 ====================
CLASSICAL_MAP = {
    '成人': '风月', '色情': '风月', '情色': '春宫', '淫': '风月', '黄色': '春宫', '淫秽': '猥亵',
    'AV': '光影', 'av': '光影', '三级': '风月',
    '激情': '云雨', '做爱': '云雨', '性交': '交欢', '欲': '情思', '高潮': '云端',
    '偷拍': '窥帘', '偷窥': '窥帘', '乱伦': '禁脔', '强奸': '强占', '轮奸': '群辱',
    '迷奸': '迷占', '无码': '素纱', '有码': '遮面', '熟女': '徐娘',
    '萝莉': '豆蔻', '幼女': '玉蕊', '少女': '碧玉', '学生': '书生',
    '人妻': '罗敷', '少妇': '艳妇', '御姐': '玉人', '护士': '药女',
    '教师': '先生', '医生': '郎中', '警察': '捕快', '军人': '军爷',
    '秘书': '掌印', '老板': '东家', '丈夫': '夫君', '妻子': '拙荆',
    '情人': '相好', '小三': '外遇', '二奶': '外室', '出轨': '翻墙',
    '偷情': '私会', '通奸': '私通', '嫖娼': '寻花', '卖淫': '卖身',
    '妓女': '花娘', '性骚扰': '轻薄', '猥亵': '猥亵', '露阴': '曝玉',
    '咸猪手': '禄山爪', '丝袜': '丝履', '网袜': '网履', '内衣': '亵衣',
    '内裤': '亵裤', '情趣': '风月', '春药': '催情', '巨乳': '丰盈',
    '爆乳': '丰盈', '胸': '酥胸', '乳': '玉兔', '美乳': '玉兔',
    '臀': '玉臀', '屁股': '玉臀', '脚': '莲步', '玉足': '莲步',
    '腿': '玉腿', '裸体': '玉体', '全裸': '玉体', '半裸': '半褪',
    '走光': '泄春', '露点': '泄玉', '自慰': '弄玉', '口交': '含朱',
    '口活': '含朱', '肛交': '后庭', '屁眼': '后庭', '肛门': '后庭',
    '群交': '合卺', '乳交': '玉兔', '足交': '莲步', '车震': '车行',
    '野战': '郊合', '精液': '元阳', '精子': '元阳', '阴道': '幽处',
    '阴户': '幽处', '阴茎': '玉茎', '阳具': '玉茎', 'SM': '调教',
    '制服': '官衣', 'OL': '衙内', '空姐': '行云', '继母': '继室',
    '姐妹': '同根', '同学': '同窗', '邻居': '东邻', '处女': '处子',
    '初夜': '破瓜', '暴力': '杀伐', '血腥': '殷红', '恐怖': '幽冥',
    '赌博': '孤注', '毒品': '药石', '枪支': '火器', '刀具': '利刃',
}

# 铁律13：未成年相关关键词（命中则整条剔除，不返回）
_MINOR_KEYWORDS = (
    '豆蔻', '玉蕊', '碧玉', '稚子', '未成年', 'teen', 'loli',
    'schoolgirl', '萝莉', '幼女', '少女', '童',
)


def desensitize(text):
    """铁律11：敏感词古典映射脱敏；铁律13：命中未成年词条返回空串"""
    if text is None:
        return ''
    result = str(text)
    for key in sorted(CLASSICAL_MAP.keys(), key=len, reverse=True):
        if key in result:
            result = result.replace(key, CLASSICAL_MAP[key])
    lower = result.lower()
    for kw in _MINOR_KEYWORDS:
        if kw.lower() in lower:
            return ''
    return result


def is_minor_content(text):
    """铁律13：未成年相关内容判定"""
    if not text:
        return False
    lower = str(text).lower()
    for kw in _MINOR_KEYWORDS:
        if kw.lower() in lower:
            return True
    return False


class Spider(Spider):

    def __init__(self, *args, **kwargs):
        super().__init__()
        # ================= 集成 5755 高级图片代理 =================
        t4_api = kwargs.get('t4_api', '')
        if t4_api:
            p = urllib.parse.urlparse(t4_api)
            self.my_proxy_base = f"{p.scheme}://{p.hostname}:5755"
        else:
            self.my_proxy_base = ""
        self._diag = ""
        self._bad_origins = set()

    def init(self, extend="{}"):
        # 站点候选：ext.site 优先，其余域名按序兜底
        self.site_candidates = list(DEFAULT_SITES)
        self.host = self.site_candidates[0]
        self.proxy = {}
        self.proxy_url = ''
        self.flare_url = DEFAULT_FLARE_URL
        self.flare_proxy = DEFAULT_FLARE_PROXY
        self.flare_session = 'missav_drpy_master'
        self.flare_wait = 12.0          # 解析器最多占用本次请求的秒数（后台继续跑完）
        self.flare_timeout = 35.0
        self.cffi_proxy = ''            # 指纹通道出口；留空=直连
        self.plp = ''
        self.field_link = False         # 详情字段默认输出纯文本（避免壳不解析 a=cr 标记，把 {}/\\u 转义当乱码显示）

        try:
            config = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            config = {}

        if config.get('site'):
            site = str(config.get('site')).rstrip('/')
            self.host = site
            if site in self.site_candidates:
                self.site_candidates.remove(site)
            self.site_candidates.insert(0, site)
        if config.get('proxy'):
            self.proxy = config.get('proxy')
            if isinstance(self.proxy, dict):
                self.proxy_url = self.proxy.get('https') or self.proxy.get('http') or ''
            else:
                self.proxy_url = str(self.proxy)
        if config.get('plp'):
            self.plp = config.get('plp')
        # 详情字段形态：默认纯文本；填 1/on 才输出可点击跳转标记
        lk = config.get('links')
        if lk is not None:
            self.field_link = str(lk).strip().lower() in ('1', 'on', 'true', 'yes', 'y')
        # 解析器开关：ext.flare 可覆盖地址，'off' 关闭
        flare = config.get('flare')
        if isinstance(flare, str) and flare.strip().lower() in ('off', 'none', '0', 'false', 'no'):
            self.flare_url = ''
        elif flare:
            self.flare_url = str(flare).strip()
        if config.get('flare_proxy') is not None:
            self.flare_proxy = str(config.get('flare_proxy')).strip()
        if config.get('flare_session'):
            self.flare_session = str(config.get('flare_session')).strip()
        try:
            self.flare_wait = max(1.0, float(config.get('flare_wait', self.flare_wait)))
        except Exception:
            pass
        try:
            self.flare_timeout = max(5.0, float(config.get('flare_timeout', self.flare_timeout)))
        except Exception:
            pass
        # 指纹出口：默认跟随解析器同机代理；填 direct 强制直连
        cp = config.get('cffi_proxy')
        if cp is None:
            self.cffi_proxy = self.proxy_url or self.flare_proxy
        else:
            cp = str(cp).strip()
            self.cffi_proxy = '' if cp.lower() in ('direct', 'none', 'no') else cp

        # 【修复1】规范大写标准的 Headers，避免客户端播放器漏传 Referer 防盗链和 Origin 跨域限制
        self.headers = {
            'User-Agent': DEFAULT_UA,
            'Referer': f'{self.host}/',
            'Origin': self.host
        }

        # 油门：开局从硬盘恢复门票，直接走指纹长连接
        if _ticket_load():
            _build_cffi_session(_TICKET.get('ua') or DEFAULT_UA, self.cffi_proxy)

    def _log(self, msg):
        current_time = time.strftime('%H:%M:%S', time.localtime())
        print(f"[{current_time}] [MissAV] {msg}", flush=True)

    def _note(self, msg):
        self._diag = (self._diag + '; ' + msg) if self._diag else msg

    def _origin(self, url):
        try:
            parts = urllib.parse.urlsplit(url)
            return '%s://%s' % (parts.scheme, parts.netloc)
        except Exception:
            return ''

    def _cands(self, url):
        """把本站 URL 展开成候选地址：当前入口 → 其它域名候选 → 反代；错站入口不再重试"""
        path = url
        if url.startswith('http'):
            path = urllib.parse.urlsplit(url).path or '/'
            q = urllib.parse.urlsplit(url).query
            if q:
                path = path + '?' + q
        if not path.startswith('/'):
            path = '/' + path
        cands = []
        for base in self.site_candidates:
            base = (base or '').rstrip('/')
            if base:
                cands.append(base + path)
        # 去重 + 拉黑错站
        seen, out = set(), []
        for c in cands:
            if c in seen:
                continue
            seen.add(c)
            if self._origin(c) in self._bad_origins:
                continue
            out.append(c)
        return out

    def _by_ticket(self, cands):
        """通道①：指纹门票超车（HTTP/2 长连接 + cf_clearance）"""
        if not HAS_CFFI or not _TICKET.get('ready') or not _TICKET.get('cookies'):
            return ''
        ua = _TICKET.get('ua') or DEFAULT_UA
        sess = _build_cffi_session(ua, self.cffi_proxy)
        if sess is None:
            return ''
        cookie = _ticket_cookie_str()
        for cand in cands:
            try:
                t0 = time.time()
                res = sess.get(cand, headers=_fp_headers(ua, f'{self.host}/', cookie),
                               allow_redirects=True)
                text = res.text or ''
                if _is_challenge(res.status_code, text, res.headers):
                    self._note('门票过期')
                    _ticket_clear()
                    return ''
                if res.status_code == 200 and _is_ours(text):
                    self._log(f"指纹门票命中 {cand} ({round(time.time() - t0, 2)}s)")
                    return text
            except Exception:
                continue
        return ''

    def _by_direct(self, cands):
        """通道②：免挑战路径直连（requests，无需任何外部服务）"""
        for cand in cands:
            try:
                res = requests.get(cand, headers=_fp_headers(DEFAULT_UA, f'{self.host}/'),
                                   proxies=self.proxy or None, verify=False,
                                   timeout=15, allow_redirects=True)
                text = res.text or ''
                if _is_challenge(res.status_code, text, res.headers):
                    self._note('直连被盾拦')
                    continue
                if res.status_code >= 400 and not text:
                    continue
                if not _is_ours(text):
                    bad = self._origin(cand)
                    if bad and bad != self._origin(self.host):
                        self._bad_origins.add(bad)
                    self._note('候选返回非本站内容')
                    continue
                return text
            except Exception:
                continue
        return ''

    def _by_flare(self, cands):
        """通道③：解析器兜底（后台线程渲染过盾，本次最多等 flare_wait 秒）"""
        if not self.flare_url:
            return ''
        if time.time() < _FLARE_STATE.get('fail_until', 0):
            self._note('解析器冷却中')
            return ''
        with _FLARE_STATE['lock']:
            if _FLARE_STATE.get('busy'):
                self._note('解析器任务进行中')
                return ''
            _FLARE_STATE['busy'] = True
        box = {'html': ''}

        def worker():
            try:
                for cand in cands:
                    html, cookies, ua = _flare_solve(cand, self.flare_url, self.flare_proxy,
                                                     self.flare_session, timeout=self.flare_timeout)
                    if html:
                        if cookies:
                            _ticket_save(cookies, ua or DEFAULT_UA)
                            self._log('门票已更新并落盘')
                        _build_cffi_session(ua or DEFAULT_UA, self.cffi_proxy)
                        box['html'] = html
                        return
                _FLARE_STATE['fail_until'] = time.time() + 600
            except Exception:
                _FLARE_STATE['fail_until'] = time.time() + 600
            finally:
                _FLARE_STATE['busy'] = False

        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()
        try:
            t.join(max(1.0, float(self.flare_wait)))
        except Exception:
            pass
        if box['html']:
            return box['html']
        self._note('解析器兜底超时')
        return ''

    def fetch_html_by_flare(self, target_url):
        """三级取页通道（对调用方透明：返回 pyquery 对象；三层全断返回 None）"""
        hit = _page_get(target_url)
        if hit is not None:
            return pq(hit)

        self._diag = ''
        cands = self._cands(target_url)
        html = self._by_ticket(cands) or self._by_direct(cands)
        if not html:
            html = self._by_flare(cands)
        if not html:
            self._log('取页失败: %s (%s)' % (target_url, self._diag or 'all channels blocked'))
            return None
        _page_put(target_url, html)
        return pq(html)

    # ---------- packer 解包（纯 Python，不依赖 node） ----------

    @staticmethod
    def _to_radix(num, base):
        """整数转任意进制（复刻 packer 的 c.toString(a)）：实测该站同一站内进制不固定"""
        if base < 2 or base > 36:
            base = 16
        chars = '0123456789abcdefghijklmnopqrstuvwxyz'
        if num <= 0:
            return '0'
        out = ''
        while num:
            num, rem = divmod(num, base)
            out = chars[rem] + out
        return out

    def _unpack_packer(self, source):
        """解包 Dean Edwards packer，直接返回 m3u8 直链（失败返回 ''）"""
        if not source:
            return ''
        m = re.search(r"\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)", source, re.S)
        if not m:
            return ''
        payload = m.group(1)
        try:
            base, count = int(m.group(2)), int(m.group(3))
            words = m.group(4).split('|')
        except Exception:
            return ''
        if count <= 0:
            return ''
        table = {}
        for idx in range(count - 1, -1, -1):
            key = self._to_radix(idx, base)
            table[key] = words[idx] if idx < len(words) and words[idx] else key
        body = payload.replace("\\'", "'").replace('\\"', '"')
        try:
            unpacked = re.sub(r'[A-Za-z0-9_]+', lambda mo: table.get(mo.group(0), mo.group(0)), body)
        except Exception:
            return ''
        hit = re.search(r"(https?://[^\s'\"]+\.m3u8[^\s'\"]*)", unpacked, re.I)
        if not hit:
            return ''
        return hit.group(1).replace('\\/', '/')


    def get_dummy_card(self):
        return {
            'vod_id': 'error_wait',
            'vod_name': '🔄 门票已失效, 正在自动更新中... 请等待 15 秒后重进本页即可',
            'vod_pic': 'https://wsrv.nl/?url=https%3A%2F%2Fvia.placeholder.com%2F400x533%2FFF3333%2FFFFFFF%2F%3Ftext%3DCF%2BUpdating...',
            'vod_remarks': '仅门票失效需等待',
            'style': {"type": "rect", "ratio": 1.33}
        }

    def getName(self):
        return "MissAV"

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        pass

    ccccc = 'H4sIAAAAAAAAA4uuViqpLEiNz0vMTVWyUlB6Nqfhxf6Jz2ZveTZtg5IORC4zBSSTkmtqaKKfnKefl1quVKuDrm/ahid75zzZ0fV0RxOGPgsLkL6i1JzUxOJULHqnL3i+oPHZ1san7bvQ9ZoZGYL0luYlp+YV5xelpugCDcnGNOPp0s1P9sx4sqPhxfIOVDOAuhOTS4pSi4tTizH1Pd+4++m8bgwd6al5RdiUP+2f+GJhz9OpbRg6chOzU4uAOmIBkkRrDlIBAAA='
    fts = 'H4sIAAAAAAAAA23P30rDMBQG8FeRXM8X8FVGGZk90rA0HU3SMcZgXjn8V6p2BS2KoOiFAwUn2iK+TBP7GBpYXbG9/c6Pc77TnaABjNHOFtojVIDPUQcx7IJJvl9ydX30GwSYSpN0J4iZgTqJiywrPlN1vm/GJiPMJgGxJaZo2qnc3WXDuZIKMqSwUcX7Ui8O1DJRH3Gldh3CgMM2l31BhNGW8euq3PNFrac+PVNZ2NYzjMrbY53c6/Sm2uwDBczB7mGxqaDTWfkV6atXvXiu4FD2KeHOf3nxViahjv8YxwHYtWfyQ3NvFZYP85oSno3HvYDAiNevPqnosWFHAAPahnU6b2DXY8Jp0bO8QdfEmlo/SBd5PPUBAAA='
    actfts = 'H4sIAAAAAAAAA5WVS2sUQRRG/0rT6xTcqq5Xiwjm/X6sQxZjbBLRBBeOIEGIIEgWrtwI4lJEQsjGhU6Iv2bGcf6FVUUydW/d1SxT55sDfbpmsn9WP+/e1A+q+rh7dnT8qp6rT3snXTz4N7icXH4OB697L/rxZP+sPo1g+Ot8PPg+vvoyOb+IOJ7Vb+fuqGxkJSrZmMOTexiORDjAGxs3GvDGinCANjp5NPbo4NHYo5PHYI8OHoM9JnkM9pjgMdhjksdijwkeiz02eSz22OCx2GOTx2GPDR6HPS55HPa44HHY45LHY48LHo89Pnk89vjg8djjk6fFHh88bfAcxNXduz/sv0Qvfnz74+/X65lf/OMqfzD9ndF8geYzWijQQkaLBVrMaKlASxktF2g5o5UCrWS0WqDVjNYKtJbReoHWM9oo0EZGmwXazGirQFsZbRdoO6OdAu1ktFug3Yz2CrRH70TvqEN3YvT75+TP+5nvxMNKwf0pCIWur4JwM5spVCAaRJtI9ZQ2IPBPg47UTKkGgb/wJlI7pQYE/ho/QsiCaFv61E+7J338Izj6MJi8+xSefnhzO/PTK1CmGt58G118zM+pDBloPtBk0PBBQwaKDxQZSD6QZAB8QN6UbNlAtmTg+cCTgeMDRwaWDywZ8JKSlJS8pCQlJS8pSUnJS0pSUvKSkpSUvKQkJYGXBFISeEkgJYGXBFISeEkgJYGXBFISeEkgJYGXBFISeEkgJYGXBFISeElI/7QO/gOZ7bAksggAAA=='

    def homeContent(self, filter):
        result = {}
        filters = {}
        classes = self.ungzip(self.ccccc)
        
        for i in classes:
            clean_id = re.sub(r'^dm\d+/', '', i['type_id'])
            i['type_id'] = clean_id
            filters[clean_id] = copy.deepcopy(self.ungzip(self.fts))
            if 'actresses' in clean_id: 
                filters[clean_id].extend(self.ungzip(self.actfts))
                
        result['class'] = classes
        result['filters'] = filters
        result['list'] = []
        return result

    def homeVideoContent(self):
        req_url = f"{self.host}/cn"
        html = self.fetch_html_by_flare(req_url)
        if not html: 
            return {'list': [self.get_dummy_card()]}
        return {'list': self.getlist(html)}

    def categoryContent(self, tid, pg, filter, extend):
        params = {'page': pg}
        ft = {'filters': extend.get('filters', ''), 'sort': extend.get('sort', '')}
        
        tid = re.sub(r'^dm\d+/', '', tid)
        if not tid.startswith('cn/') and not tid.startswith('http'):
            tid = f"cn/{tid}"
            
        if 'genres' in tid or 'makers' in tid:
            ft = {}
        elif 'actresses' in tid:
            ft = {
                'height': extend.get('height', ''),
                'cup': extend.get('cup', ''),
                'debut': extend.get('debut', ''),
                'age': extend.get('age', ''),
                'sort': extend.get('sort', '')
            }
        params.update(ft)
        params = {k: v for k, v in params.items() if v}
        
        req = requests.Request(url=f"{self.host}/{tid}", params=params).prepare()
        html = self.fetch_html_by_flare(req.url)
        
        if not html: 
            return {'list': [self.get_dummy_card()], 'page': pg, 'pagecount': pg, 'limit': 90, 'total': 90}

        path_parts = tid.split('?')[0].split('/')
        is_dir = False
        
        if len(path_parts) <= 2 and ('genres' in tid or 'makers' in tid or 'actresses' in tid):
            is_dir = True

        if is_dir:
            if 'actresses' in tid:
                videos = self.actca(html)
            else:
                videos = self.gmsca(html)
        else:
            videos = self.getlist(html)
            
        return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    def _mk_tag(self, href, name):
        """详情字段拼装：默认纯文本（任何壳都不会乱码）；
        开 ext.links=1 才输出可点击跳转标记，且 JSON 不转义中文（避免 \\uXXXX 花屏）"""
        name = (name or '').strip()
        if not name:
            return ''
        if not self.field_link:
            return name
        slug = (href or '').split('/', 3)[-1]
        meta = json.dumps({'id': slug, 'name': name}, ensure_ascii=False)
        return '[a=cr:%s/]%s[/a]' % (meta, name)

    def detailContent(self, ids):
        if ids[0] == 'error_wait':
            return {'list': []}

        # 修复：详情入口带上语言前缀 /cn/ —— 裸 slug 会被 CF 挑战层拦（实测 403），
        # /cn/{slug} 实测免挑战直达（含 packer 播放脚本与全部字段）
        req_url = f"{self.host}/cn/{ids[0]}"
        v = self.fetch_html_by_flare(req_url)
        
        if not v:
            return {'list': []}
            
        try:
            sctx = v('body script').text()
            urls = self.execute_js(sctx)
            
            if not urls: 
                header_str = json.dumps({'User-Agent': self.headers['User-Agent'], 'Referer': self.host + '/'})
                urls = f"嗅探${req_url}#Proxy-Header={header_str}"
            
            c = v('.space-y-2 .text-secondary')
            ac, dt, cd, bq = [], [], [], []
            for i in c.items():
                xxx = i('span').text()
                names = [self._mk_tag(j.attr('href'), j.text()) for j in i('a').items()]
                names = [n for n in names if n]
                if not names:
                    continue
                if re.search(r"导演:|发行商:", xxx):
                    dt.extend(names)
                elif re.search(r"女优:", xxx):
                    ac.extend(names)
                elif re.search(r"类型:|系列:", xxx):
                    bq.extend(names)
                elif re.search(r"标籤:|标签:", xxx):
                    cd.extend(names)

            _desc = desensitize(v('.text-secondary.break-all').text())
            _cate = ' '.join(bq)
            if _desc:
                _content = (_cate + '\n' + _desc).strip() if _cate else _desc.strip()
            else:
                _content = _cate
            vod = {
                'type_name': bq[0] if bq else c.eq(-3)('a').text(),
                'vod_year': c.eq(0)('time').text(),
                'vod_remarks': ' '.join(cd),
                'vod_actor': ' '.join(ac),
                'vod_director': ' '.join(dt),
                'vod_content': _content,
                'vod_play_from': 'MissAV',
                'vod_play_url': urls
            }
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    def searchContent(self, key, quick, pg="1"):
        req = requests.Request(url=f"{self.host}/search/{key}", params={'page': pg}).prepare()
        data = self.fetch_html_by_flare(req.url)
        if not data: return {'list': []}
        return {'list': self.getlist(data), 'page': pg}

    # 【核心修复2】重写播放逻辑，彻底切分画质标签名与真实链接
    def playerContent(self, flag, id, vipFlags):
        if id == 'error_wait': 
            return {'parse': 0, 'url': ''}
            
        # 剥离可能混入的画质或标记字符串（例如：“超清$https://...”，提取出后半段的纯净URL）
        actual_url = id.split('$')[-1]
        
        p = 0 if '.m3u8' in actual_url else 1
        if '嗅探$' in id:
            return {'parse': 1, 'url': actual_url, 'header': self.headers}
            
        return {'parse': p, 'url': actual_url if p else f"{self.plp}{actual_url}", 'header': self.headers}

    def getlist(self, data):
        videos = []
        ids = set()
        
        for i in data('.thumbnail').items():
            a_tag = i('a').eq(0)
            href = a_tag.attr('href')
            if not href or 'missav' not in href:
                continue
                
            vid = href.split('/')[-1]
            if not vid or vid in ids:
                continue
            ids.add(vid)
            
            img_tag = i('img').eq(0)
            pic = img_tag.attr('data-src') or img_tag.attr('src') or ''
            
            if pic.startswith('//'): pic = 'https:' + pic
            if pic: pic = pic.replace('\\/', '/')
            
            if pic and getattr(self, 'my_proxy_base', ''):
                headers_dict = {
                    "Referer": f"{self.host}/",
                    "User-Agent": self.headers['User-Agent']
                }
                headers_json = json.dumps(headers_dict)
                url_b64 = base64.b64encode(pic.encode('utf-8')).decode('utf-8')
                headers_b64 = base64.b64encode(headers_json.encode('utf-8')).decode('utf-8')
                
                url_b64_safe = urllib.parse.quote(url_b64)
                headers_b64_safe = urllib.parse.quote(headers_b64)
                pic = f"{self.my_proxy_base}/?form=base64&url={url_b64_safe}&headers={headers_b64_safe}&auth=drpys"
            elif pic:
                pic = f"{pic}@Referer={self.host}/"
            
            name = i('.text-secondary').text()
            if not name:
                name = img_tag.attr('alt') or "未知标题"

            # 铁律13：未成年词条整条剔除；铁律11：展示文本脱敏
            if is_minor_content(vid) or is_minor_content(name):
                continue
            name = desensitize(name) or vid
                
            duration = i('.absolute.bottom-2.right-2').text() or ""
            
            videos.append({
                'vod_id': vid,
                'vod_name': name.strip(),
                'vod_pic': pic,
                'vod_remarks': duration,
                'style': {"type": "rect", "ratio": 1.33}
            })
            
        return videos

    def gmsca(self, data):
        acts = []
        for i in data('.grid.grid-cols-2 div').items():
            a_tag = i('a').eq(0)
            id = a_tag.attr('href')
            if not id: continue
            _nm = i('.text-nord13').text() or a_tag.text()
            acts.append({
                'vod_id': id.split('/', 3)[-1],
                'vod_name': desensitize(_nm) or _nm,
                'vod_pic': '',
                'vod_remarks': i('.text-nord10').text(),
                'vod_tag': 'folder',
                'style': {"type": "rect", "ratio": 2}
            })
        return acts

    def actca(self, data):
        acts = []
        for i in data('.max-w-full ul li').items():
            id = i('a').attr('href')
            if not id: continue
            
            pic = i('img').attr('src') or ''
            if pic.startswith('//'): pic = 'https:' + pic
            if pic: pic = pic.replace('\\/', '/')
            
            if pic and getattr(self, 'my_proxy_base', ''):
                headers_dict = {
                    "Referer": f"{self.host}/",
                    "User-Agent": self.headers['User-Agent']
                }
                headers_json = json.dumps(headers_dict)
                url_b64 = base64.b64encode(pic.encode('utf-8')).decode('utf-8')
                headers_b64 = base64.b64encode(headers_json.encode('utf-8')).decode('utf-8')
                
                url_b64_safe = urllib.parse.quote(url_b64)
                headers_b64_safe = urllib.parse.quote(headers_b64)
                pic = f"{self.my_proxy_base}/?form=base64&url={url_b64_safe}&headers={headers_b64_safe}&auth=drpys"
            elif pic:
                pic = f"{pic}@Referer={self.host}/"
            
            _nm = i('img').attr('alt') or ''
            acts.append({
                'vod_id': id.split('/', 3)[-1],
                'vod_name': desensitize(_nm) or _nm,
                'vod_pic': pic,
                'vod_year': i('.text-nord10').eq(-1).text(),
                'vod_remarks': i('.text-nord10').eq(0).text(),
                'vod_tag': 'folder',
                'style': {"type": "oval"}
            })
        return acts

    def ungzip(self, data):
        result = gzip.decompress(b64decode(data)).decode('utf-8')
        return json.loads(result)

    def execute_js(self, jstxt):
        try:
            # 纯 Python 解包优先：设备上没有 node 也能解出播放地址
            py_url = self._unpack_packer(jstxt)
            if py_url:
                return f"超清${py_url}"

            direct_match = re.search(r"(https?://[^\s'\"]+\.m3u8[^\s'\"]*)", jstxt, re.I)
            if direct_match:
                clean_url = direct_match.group(1).replace('\\/', '/')
                return f"超清${clean_url}"

            match = re.search(r"eval\((function\(.*?\).*?return.*?\}\(.*?\))\)", jstxt, re.S)
            if not match:
                return None
                
            js_code = match.group(1) 
            node_script = f"console.log({js_code})"
            
            process = subprocess.Popen(['node', '-e', node_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, _ = process.communicate(timeout=3)
            res_str = stdout.decode('utf-8').strip()
            
            url_match = re.search(r"(https?://[^\s'\"]+\.m3u8[^\s'\"]*)", res_str, re.I)
            if url_match: 
                clean_url = url_match.group(1).replace('\\/', '/')
                return f"超清${clean_url}"
                
            return None
        except Exception:
            return None

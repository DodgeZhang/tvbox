# -*- coding: utf-8 -*-
# ============ 魔法盒子 / 魔法影视 (l98.cn) 多源聚合 TVBox 源 ============
# 站点: 魔法盒子(l98.cn) | 影视聚合平台(Vite SPA + 自建 API + CF)
# ---------------------------------------------------------------------------
# 【站点架构】首页聚合 6 个 section: 2 个苹果CMS源 + 4 个TVBox源;
#   站内另有 25 个 TVBox 子源(/api/tvbox/sources), 统一由站内 API 代理。
# 【API 契约】(全部 POST/GET + 签名头, 已完整逆向)
#   签名: X-MF-Sign = fnv1a_base36('mfys-api-guard-v1' + '|' + METHOD + '|'
#                                  + pathname + '|' + X-MF-TS)
#         X-MF-TS = 毫秒时间戳(与请求同值), X-MF-Client = 'web'
#   GET  /api/site/config                站点配置(sections: 分类树)
#   GET  /api/tvbox/sources              全部 TVBox 子源列表
#   POST /api/tvbox/home      {api}               源首页(含 class 分类)
#   POST /api/tvbox/category  {api,type,page}     源分类列表
#   POST /api/detail          {api,ids}           详情(含 vod_play_from/vod_play_url)
#   POST /api/search          {api,keyword,page}  搜索
#   GET  /api/tvbox/play/{tvbox_ep_xxx}          播放(m3u8 文本; 分片为相对路径)
#   GET  /api/tvbox/resolve/{tvbox_ep_xxx}       解析(JSON: {url,format})
#   GET  /api/tvbox/media/{id}                   媒体分片(视频/ts)
# ---------------------------------------------------------------------------
# 【播放链路】detail.vod_play_url 形如: "选名$/api/tvbox/play/tvbox_ep_{base64}"
#   -> 取 token -> 返回绝对 URL {base}/api/tvbox/play/{token} (parse=0)
#   -> m3u8 内分片是 /api/tvbox/media/{id} 相对绝对路径, 播放器按同源解析
#   若播放器不解析相对分片, 走 localProxy(type=mfys_m3u8) 重写为绝对 URL。
# 【搜索】主CMS源禁用搜索(wd 返回"暂不支持搜索"), 故并发查全部子源后合并去重,
#   命中条目的 vod_id 编码为 "{源api}|{vid}", 详情按其源 api 还原。
# 【分类】站点首页 10 大类(电影/电视剧/综艺/动漫/动画片/短剧/4K/邵氏/Netflix影剧);
#   由于主CMS源禁用搜索但分类完整, 分类/首页/详情均走主CMS源(稳定直连m3u8)。
# 用法: 只改 ★ CONFIG 区
import sys, re, json, time, hashlib, urllib.parse
from concurrent.futures import ThreadPoolExecutor
try:
    import requests
except ImportError:
    requests = None

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider(object):
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            import urllib.request as _urq
            r = _urq.Request(url, headers=headers or {})
            return _urq.urlopen(r, timeout=15)


# ============ ★ CONFIG ============
SITE      = 'http://l98.cn'                                     # ★ 站点(签名origin)
CMS_API   = 'https://api.wsyzy.net/api.php/provide/vod'         # ★ 主内容源(苹果CMS)
UA        = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
REFERER   = 'http://l98.cn/'                                    # ★ 资源/播放 Referer
PIC_REFERER = 'http://l98.cn/'                                  # ★ 图片 Referer(空=无)
MF_SALT   = 'mfys-api-guard-v1'                                 # ★ 站内API签名盐
MF_CLIENT = 'web'                                               # ★ 站内API客户端标识
# ★ 搜索并发源(均为实测「搜索+详情+播放」全通); 已剔除 j4k/jd4k(返HTML错误页)、
#   aa4f0ed30b(详情接口不可用) 等死链源, 避免脏数据与无谓超时。
SEARCH_SOURCES = [
    'tvbox-py://source-616fbcbf9e',   # 瓜子APP    (命中最高, m3u8)
    'tvbox-py://wencai',              # 文才影视   (m3u8, 2685分片)
    'tvbox-py://source-4eb17c91b4',   # 三秋影视   (mp4)
    'tvbox-py://source-0ad659640c',   # 泥巴影视
    'tvbox-py://source-cb4888cc81',   # 剧OK影视   (多平台线路)
    'tvbox-py://source-90e25e2716',   # 布布影视
]
# ★ 分类: 站点首页 10 大类 -> CMS type_id(逗号分隔)
CLASSES = [
    {'type_id': '6,7,8,9,10,11,12',      'type_name': '电影'},
    {'type_id': '13,14,15,16,17,18,23',  'type_name': '电视剧'},
    {'type_id': '25,26,27,28',           'type_name': '综艺'},
    {'type_id': '29,30,31,44,45',        'type_name': '动漫'},
    {'type_id': '39',                    'type_name': '动画片'},
    {'type_id': '54,64,65,66,67,68,69,73', 'type_name': '短剧'},
    {'type_id': '62',                    'type_name': '4K电影'},
    {'type_id': '70',                    'type_name': '邵氏电影'},
    {'type_id': '71',                    'type_name': 'Netflix电影'},
    {'type_id': '72',                    'type_name': 'Netflix剧集'},
]
FILTERS = {}
VIDEO_EXTS = 'm3u8|mp4|flv|mkv|ts'


class Spider(Spider):
    def init(self, extend=''):
        self.base = SITE.rstrip('/')
        self.cms = CMS_API
        self.ua = UA
        self.ref = REFERER or (self.base + '/')
        self.pic_ref = PIC_REFERER or ''
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif isinstance(extend, str) and extend.strip().startswith('{'):
            try:
                j = json.loads(extend)
                if isinstance(j, dict):
                    cfg = j
            except Exception:
                cfg = {}
        if cfg.get('site'):
            self.base = str(cfg['site']).rstrip('/')
        if cfg.get('cms'):
            self.cms = str(cfg['cms'])
        self.sess = requests.Session() if requests else None
        self._src_cache = None

    # ---------- 基础请求 ----------
    def _headers(self, extra=None):
        h = {'User-Agent': self.ua, 'Referer': self.ref}
        if extra:
            h.update(extra)
        return h

    def _get(self, url, headers=None, timeout=15000):
        hd = self._headers(headers)
        try:
            if requests:
                r = requests.get(url, headers=hd, timeout=timeout / 1000.0, verify=False)
                r.encoding = 'utf-8'
                return r.text
            r = self.fetch(url, headers=hd, timeout=timeout)
            return r.text if hasattr(r, 'text') else str(r)
        except Exception:
            return ''

    def _mf_sign(self, method, pathname, ts):
        """FNV-1a(32位) -> base36 ; 与站点 api-guard-client.js 完全一致"""
        h = 2166136261
        text = MF_SALT + '|' + method.upper() + '|' + pathname + '|' + str(ts)
        for ch in text:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        if h == 0:
            return '0'
        digs = '0123456789abcdefghijklmnopqrstuvwxyz'
        out = ''
        while h:
            out = digs[h % 36] + out
            h //= 36
        return out

    def _api(self, path_qs, data=None, method=None, timeout=20):
        """站内 API(默认POST+签名); 返回 dict, 失败返回 {}"""
        m = (method or ('POST' if data is not None else 'GET')).upper()
        p = urllib.parse.urlparse(path_qs)
        ts = int(time.time() * 1000)
        hd = {
            'User-Agent': self.ua,
            'Referer': self.ref,
            'Accept': 'application/json, text/plain, */*',
            'X-MF-TS': str(ts),
            'X-MF-Sign': self._mf_sign(m, p.path, ts),
            'X-MF-Client': MF_CLIENT,
        }
        body = None
        if data is not None:
            body = json.dumps(data).encode('utf-8')
            hd['Content-Type'] = 'application/json'
        try:
            if requests:
                r = requests.request(m, self.base + path_qs, data=body, headers=hd,
                                     timeout=timeout, verify=False)
                if r.status_code == 200:
                    return r.json()
                return {}
            import urllib.request as _urq
            req = _urq.Request(self.base + path_qs, data=body, headers=hd)
            resp = _urq.urlopen(req, timeout=timeout)
            return json.loads(resp.read().decode('utf-8', 'ignore'))
        except Exception:
            return {}

    def _cms(self, params):
        """主 CMS 接口(苹果CMS), params 形如 {'ac':'detail','pg':1}"""
        q = urllib.parse.urlencode(params)
        txt = self._get(self.cms + '/?' + q)
        if not txt:
            return {}
        try:
            return json.loads(txt)
        except Exception:
            return {}

    def _pic(self, u):
        if not u:
            return ''
        if u.startswith('//'):
            u = 'https:' + u
        return u

    # ---------- 字段映射 ----------
    def _mk(self, v, api=''):
        vid = str(v.get('vod_id') or '')
        if api:
            vid = api + '|' + vid
        return {
            'vod_id': vid,
            'vod_name': v.get('vod_name') or '',
            'vod_pic': self._pic(v.get('vod_pic') or ''),
            'vod_remarks': v.get('vod_remarks') or '',
        }

    def _sources(self):
        if self._src_cache is None:
            j = self._api('/api/tvbox/sources', method='GET')
            self._src_cache = j.get('data') or []
        return self._src_cache

    # ========== 首页 ==========
    def homeContent(self, filter=False):
        r = {'class': CLASSES[:]}
        if filter and FILTERS:
            r['filters'] = FILTERS
        r['list'] = self.homeVideoContent().get('list', [])
        return r

    def homeVideoContent(self):
        j = self._cms({'ac': 'detail', 'pg': 1})
        items = [self._mk(v) for v in (j.get('list') or [])]
        return {'list': items}

    # ========== 分类(走主CMS源) ==========
    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        j = self._cms({'ac': 'detail', 't': str(tid or ''), 'pg': pn})
        items = [self._mk(v) for v in (j.get('list') or [])]
        try:
            pc = int(j.get('pagecount') or pn)
        except Exception:
            pc = pn
        return {'page': pn, 'pagecount': max(pc, pn), 'limit': 20,
                'total': pc * 20 if items else 0, 'list': items}

    # ========== 详情(支持 CMS 裸 id 与 "{源api}|{vid}" 复合 id) ==========
    def detailContent(self, ids, quick='1'):
        raw = str(ids[0] if isinstance(ids, (list, tuple)) else ids or '').strip()
        if not raw:
            return {'list': []}
        if '|' in raw:
            api, vid = raw.split('|', 1)
        else:
            api, vid = '', raw
        if api:
            # 子源: 重试 2 次; 失败则直接返回空, ★ 绝不回退 CMS 源
            # (子源 id 形如 "44970/0" 与 CMS 数字 id 空间无关, 回退会错配出无关影片)
            for _ in range(2):
                j = self._api('/api/detail', {'api': api, 'ids': vid})
                v = j.get('data') or {}
                if isinstance(v, dict) and v.get('vod_name'):
                    return {'list': [self._detail_dict(api + '|' + vid, v)]}
                time.sleep(0.3)
            return {'list': []}
        # CMS 主源
        j = self._cms({'ac': 'detail', 'ids': vid})
        lst = j.get('list') or []
        if not lst:
            return {'list': []}
        return {'list': [self._detail_dict(vid, lst[0])]}

    def _detail_dict(self, out_id, v):
        d = {
            'vod_id': out_id,
            'vod_name': v.get('vod_name') or '',
            'vod_pic': self._pic(v.get('vod_pic') or ''),
            'vod_year': str(v.get('vod_year') or ''),
            'vod_area': v.get('vod_area') or '',
            'vod_class': v.get('type_name') or v.get('vod_class') or '',
            'vod_director': v.get('vod_director') or '',
            'vod_actor': v.get('vod_actor') or '',
            'vod_content': (v.get('vod_blurb') or v.get('vod_content') or '').strip(),
            'vod_remarks': v.get('vod_remarks') or '',
            'vod_play_from': v.get('vod_play_from') or '',
            # 子源播放地址形如 "选名$/api/tvbox/play/tvbox_ep_xxx" 原样保留,
            # playerContent 会补全为绝对 URL; CMS 源为真实 m3u8 直链
            'vod_play_url': v.get('vod_play_url') or '',
        }
        return d

    # ========== 搜索(并发多源合并去重) ==========
    def searchContent(self, key, quick=False, pg='1'):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        kw = str(key or '').strip()
        if not kw:
            return {'list': [], 'page': pn, 'pagecount': pn}

        def _one(api):
            # 上游子源偶发超时, 重试一次提升命中稳定性
            for _ in range(2):
                j = self._api('/api/search', {'api': api, 'keyword': kw, 'page': pn})
                data = j.get('data') or []
                if data:
                    return [self._mk(v, api) for v in data]
                time.sleep(0.2)
            return []

        items, seen = [], set()
        try:
            with ThreadPoolExecutor(max_workers=6) as ex:
                results = list(ex.map(_one, SEARCH_SOURCES))
        except Exception:
            results = [_one(a) for a in SEARCH_SOURCES]
        for res in results:
            for it in res:
                name = (it['vod_name'] or '').strip()
                vid = str(it['vod_id'] or '')
                if not vid or not name:
                    continue
                # ★ 相关性过滤: 片名须包含关键词(剔除模糊刷屏/公告占位条目)
                if kw not in name:
                    continue
                # ★ 过滤公告类占位条目
                if re.search(r'访问新站|请访问|新站|广告|公告', name):
                    continue
                k = name + '|' + vid.split('|')[-1]
                if k in seen:
                    continue
                seen.add(k)
                it['_exact'] = 1 if name == kw else 0
                items.append(it)
        # 精确命中排前
        items.sort(key=lambda x: -x.get('_exact', 0))
        for it in items:
            it.pop('_exact', None)
        return {'list': items, 'page': pn, 'pagecount': pn + (1 if items else 0)}

    # ========== 播放 ==========
    def playerContent(self, flag, id, vipFlags=None):
        url = str(id or '')
        if '$' in url:
            url = url.split('$', 1)[1]
        full = self.base + url if url.startswith('/') else url
        if not full.startswith('http'):
            return {'parse': 0, 'url': full}
        hd = {'User-Agent': self.ua, 'Referer': self.ref}
        # 1) 真实直链(m3u8 分片已绝对化 / mp4 直链) 直接交给播放器, 不走代理
        if '.m3u8' in full or re.search(r'\.(?:mp4|flv|mkv|avi|ts|mov|m4v)(?:\?|$)', full, re.I):
            return {'parse': 0, 'url': full, 'header': hd}
        # 2) 站内播放代理 /api/tvbox/play/tvbox_ep_xxx: 返回 m3u8(相对分片) 或 mp4,
        #    经本地代理探测真实类型后再输出 → 避免播放器按错误容器解析
        proxy = self.getProxyUrl()
        if proxy:
            return {'parse': 0, 'url': proxy + '&type=mfys&url=' + urllib.parse.quote(full, safe=''),
                    'header': hd}
        # 3) 无代理环境: 探测一次, m3u8 直连(分片为绝对地址即可播), mp4 走 resolve 真实地址
        r = self._probe(full)
        if r:
            return {'parse': 0, 'url': r, 'header': hd}
        return {'parse': 0, 'url': full, 'header': hd}

    def _probe(self, url):
        """探测站内播放地址的真实类型, 返回可直连地址(m3u8/mp4); 失败返回 ''"""
        try:
            txt = self._get(url, headers={'Referer': self.ref})
        except Exception:
            return ''
        if not txt:
            return ''
        s = txt.lstrip()
        if s.startswith('#EXTM3U'):                 # m3u8: 分片为绝对地址才能直连
            for ln in s.splitlines():
                t = ln.strip()
                if t and not t.startswith('#'):
                    return url if t.startswith('http') else ''
            return ''
        if 'ftyp' in s[:32]:                        # mp4
            j = self._api('/api/tvbox/resolve/' + url.rsplit('/', 1)[-1], method='GET')
            u = str(j.get('url') or '')
            return (self.base + u) if u.startswith('/') else u
        return ''

    def getProxyUrl(self):
        """壳源本地代理地址(模板同款); 无壳环境回退直连"""
        try:
            p = self._proxy
            if p:
                return p
        except Exception:
            pass
        try:
            return 'http://127.0.0.1:9978/proxy?do=py'
        except Exception:
            return ''

    # ========== 扩展钩子(四壳13接口) ==========
    def isVideoFormat(self, url):
        if not url:
            return False
        if '.m3u8' in url:
            return True
        return bool(re.search(r'\.(?:%s)(?:\?|$)' % VIDEO_EXTS, url, re.I))

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return ''

    def destroy(self):
        try:
            if self.sess is not None:
                self.sess.close()
        except Exception:
            pass
        self._src_cache = None

    def progressVideo(self, speed, time_, end):
        return False

    def setVideoFlags(self, siteKey, flags):
        try:
            self._siteKey = siteKey
            self._vflags = flags
        except Exception:
            pass

    # ========== 本地代理: m3u8 相对分片绝对化 + 媒体透传 ==========
    def localProxy(self, param):
        import urllib.parse as _up               # 局部别名: 避免 urllib 被遮蔽
        p = param.split('url=', 1)[-1] if 'url=' in param else param
        p = _up.unquote(p) if '%' in p else p
        if not p:
            return {'code': 403, 'content': b'', 'headers': {}}
        # m3u8 重写: 外链 m3u8 或 站内播放代理(/api/tvbox/play/xxx 返 m3u8 或 mp4)
        if ('.m3u8' in p or '/api/tvbox/play/' in p
                or '/api/tvbox/resolve/' in p or 'type=mfys' in param):
            return self._proxy_m3u8(p)
        hd = {'User-Agent': self.ua, 'Referer': self.pic_ref or self.ref, 'Accept': '*/*'}
        try:
            if requests:
                r = requests.get(p, headers=hd, timeout=25, verify=False)
                ct = r.headers.get('Content-Type', 'application/octet-stream')
                return {'code': r.status_code, 'content': r.content, 'headers': {'Content-Type': ct}}
            import urllib.request as _urq
            resp = _urq.urlopen(_urq.Request(p, headers=hd), timeout=25)
            return {'code': 200, 'content': resp.read(),
                    'headers': {'Content-Type': resp.headers.get('Content-Type', 'application/octet-stream')}}
        except Exception:
            return {'code': 404, 'content': b'', 'headers': {}}

    def _proxy_m3u8(self, url):
        hd = {'User-Agent': self.ua, 'Referer': self.ref, 'Accept': '*/*'}
        try:
            if requests:
                r = requests.get(url, headers=hd, timeout=25, verify=False)
                raw = r.content
            else:
                import urllib.request as _urq
                resp = _urq.urlopen(_urq.Request(url, headers=hd), timeout=25)
                raw = resp.read()
        except Exception:
            return {'code': 404, 'content': b'', 'headers': {}}
        body = raw
        # ★ 非 m3u8 内容(二进制/HTML) 原样透传, 不能强标 mpegurl
        head = body.lstrip()[:64].lower()
        if not head.startswith(b'#extm3u'):
            if head.startswith(b'<!doctype') or head.startswith(b'<html'):
                return {'code': 502, 'content': b'', 'headers': {}}   # 上游错误页
            ct = 'video/mp4' if body[:8].endswith(b'ftyp') else 'application/octet-stream'
            return {'code': 200, 'content': body, 'headers': {'Content-Type': ct}}
        origin = re.match(r'https?://[^/]+', url)
        origin = origin.group(0) if origin else self.base
        out = []
        for ln in body.decode('utf-8', 'ignore').splitlines():
            s = ln.strip()
            if s.startswith('/'):
                out.append(origin + s)          # 相对 → 绝对
            else:
                out.append(ln)
        return {'code': 200, 'content': '\n'.join(out).encode('utf-8'),
                'headers': {'Content-Type': 'application/vnd.apple.mpegurl'}}

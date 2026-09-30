# -*- coding: utf-8 -*-
# ============ 未来影院 gygxpt.py v2.13 (播放本地代理 + 同集自动换线) ============
# v2.13 ①**播放本地代理**(治"有的线路不能播"): 新增 _px_proxy() 内嵌 ThreadingHTTPServer(127.0.0.1:9978-9988),
#         /p?url=&k= 路由: 抓流时带 UA+Referer(失败自动降为无 Referer/裸socket 兜底), m3u8 逐行重写为代理地址
#         (含 #EXT-X-KEY URI / master 相对子列表 / 跨域分片), 分片原样透传并支持 Range(206+Content-Range);
#       ②**PX_MODE 播放模式**: 0=直连 1=智能探测(裸播放器能拉通才直连) 2=HLS 全走代理(默认,零探测最稳);
#         PROXY_M3U8 总开关 / FORCE_PX 连 mp4 也走代理; 代理起不来时自动回退直连(不影响播放);
#       ③**同集自动换线 _alt_play()**: 当前线路取不出 m3u8 时, 依次试其它 sid 同集(≤8 条, 5s 预算);
#       ④play 取页超时 8->6s, 避免 App 侧等待过久; destroy() 优雅关闭代理;
#       ⑤根因实证: 秒播资源等 CDN 分片裸请求(无 UA/Referer)会被拒; 播放器若不转发 header 就黑屏,
#         走代理后播放链与播放器自身头行为解耦。实测 proxy E2E: m3u8 200 + 分片 200(sync=0x47)# ============ 未来影院 gygxpt.py v2.12 (搜索翻页 + 全链时间预算护栏) ============
# 定版: 88模板 v7.5 能力层(六接口契约+四壳扩展+localProxy) + www.gygxpt.com 抓取 | 2026-09-22
# v2.12 ①搜索翻页: /search.php?searchword=kw&page=N 实测共60页/296部 → searchContent 支持 pg>1,
#         _spc() 解析总页/总数, 返回 pagecount/limit/total; 旧版 pg>1 直接返回空属功能缺陷, 已修;
#       ②搜索快通道 _fast(): 各通道只试一次不重试, 硬预算 FAST_TO=7s(防 App 侧搜索超时);
#       ③全链时间预算: PR_BUDGET=8s(探测矩阵总预算, 超时跳剩余变体) / PR_TO=4s(单变体) /
#         LIST_BUDGET=10s(列表取回) → 失败路径不再拖到 20s+ (原 cat fail-path 25.6s);
#       ④homeContent 触发后台体检(_sweep_async/_sweep), 逐分类试抓,
#         "取回成功但页面内 0 个 /gygvod/ 链接"判为空分类 → 加入 _empty 并从导航隐藏(连续4次取回失败即中止防限速);
#       ⑤封面100%: 站点首页/搜索页夹带"排行榜"纯文字区块(v-rank 无封面), 混入列表会出现空白图 →
#         新增 _wp() 过滤无封面条目, 并在 _hv 的截断之前过滤(保证仍出满 36 条带图卡片);
#       ⑥分类表精简: 剔除 55 预告(用户指定) 与 60 亚洲剧(实测站点"第0页"空分类), 分类 44 -> 41
# 定版: 88模板 v7.5 能力层(六接口契约+四壳扩展+localProxy) + www.gygxpt.com 抓取 | 2026-09-22
# v2.11 ①自动去空分类: homeContent 触发后台体检(_sweep_async/_sweep), 逐分类试抓,
#        "取回成功但页面内 0 个 /gygvod/ 链接"判为空分类 → 加入 _empty 并从导航隐藏(连续4次取回失败即中止防限速);
#     ②封面100%: 站点首页/搜索页夹带"排行榜"纯文字区块(v-rank 无封面), 混入列表会出现空白图 →
#        新增 _wp() 过滤无封面条目, 并在 _hv 的截断之前过滤(保证仍出满 36 条带图卡片);
#     ③分类表精简: 剔除 55 预告(用户指定) 与 60 亚洲剧(实测站点"第0页"空分类), 分类 44 -> 41
# v2.10 分类精简(去预告/去空分类) 基座
# v2.9 自学习: 探测矩阵认出可用变体后自动切换 UA/协议/站点/传输(含 _sk 裸socket优先 + _pip IP直连)
#   UA(3R/4R->MUA) / 协议(5H->http) / 站点(6M->m.) / 传输(7S/8S->_sk 裸socket优先), 后续请求直接走它;
#   探测卡名称改为「【3R手机UA=OK129342】」同行相邻, 前端截断也不丢配对
# v2.8 探测矩阵 + requests 强制 HTTP/1.1(_ctx ALPN http/1.1 + _h1 适配器) + trust_env=False
# v2.7 针对"标题已出但列表空(截图证实源已加载)": MIN_GAP 0.35->0.25, RETRY 3->2, BACKOFF 0.8->0.35,
#   _get 默认 15->8s, _f/_ft 默认 20000->8000ms; _hv() 加时间预算护栏(超 14s 停止轮询/首页失败直接快返回);
#   _dm() 诊断条带封面 URL(前端必定渲染) + vod_remarks="发我这行"。失败路径实测 home 2.15s / cat 1.47s, 不再触发 App 侧超时。
# v2.6 加载即安全: _ensure() 自愈(未调 init 也能跑); homeContent 优先返回 class(43) 且异常时仍返回;
#   homeVideoContent 分层回退到诊断行; 六接口全补 _ensure()
# v2.5 针对"刷新都不出视频": 取回顺序改为 ① App 自带 HTTP 栈 self.fetch(设备侧实测可通)
#   ② requests + 浏览器头 ③ 裸 socket 兜底; 新增源内自诊断(全通道失败时列表显示【诊断】各通道结果);
#   extend 支持 host=/proxy= 逃生口(IP 被 WAF 拉黑时换域名/挂代理)
# v2.4 修复"分类空白"(实测根因): openresty WAF 对同 IP 短时多次请求直接掐连接(响应 0 字节),
#   旧 _get 一次失败即返回空 -> 分类/首页列表全空。修复:
#   ① 节流 MIN_GAP=0.35s + 失败退避重试 RETRY=3/BACKOFF=0.8 ② 断连自动换连接(_reset)
#   ③ 浏览器级请求头(Sec-Fetch-*/Upgrade-Insecure-Requests), 与 WAF 白名单特征对齐
#   ④ homeVideoContent 由 5 个分类页轮询改为单请求首页解析, 请求数 -80%
#   ⑤ 卡片解析与属性顺序解耦(href/title 任意序) + 名称三级兜底(title/img.alt/锚文本)
# v2 增强(浏览器实测站点全量结构):
#   v2.1 fix: total=36 -> total=pagecount*36 修复分类页翻页空白
#   v2.2 add: type_pid 字段 + 首页多分类 fallback + total 翻页修复
#   v2.3 add: 聚合推荐首页内容 + categoryContent items 补 type_id/type_name 确保前端正确关联显示
#   ② 线路名清洗: 真实页 tab 文本 "无尽资源7集" -> "无尽资源"(正则去尾部"数字+集")
#   ③ 翻页提速: pagecount 按分类 TTL 缓存10分钟 + Session 复用 keep-alive
#   ④ 图片加固: 列表 data-src/data-original/src 三路兜底 + 搜索卡片图片 group 修正
#   ⑤ 每页条数按实测修正 CAT_PAGE=30 -> 36
# 站点: https://www.gygxpt.com (未来影院, 免费无广告, MacCMS 模板体系, 无盾无鉴权)
# ★ 协议总览(实测):
#   首页   /                          -> 多个 ul.tv-list 区块(卡片 li)
#   分类   /gyglist/{tid}.html       (第1页) | /gyglist/{tid}-{pg}.html (翻页 pg>=2)
#         总页数从页面尾页链接 /gyglist/{tid}-{MAX}.html 提取
#   详情   /gygvod/{vid}.html        -> og: 元数据齐全(名称/图/导演/主演/地区/评分/年份/简介)
#         线路: #playNumTab a (DOM序) 对应 #unfk1220_play_list ul.play_num_list (DOM序)
#         选集: ul 内 a[title=第X集][href=/gygplayer/{vid}-{sid}-{nid}.html]
#   ★ sid = tab 的 a.id - 1 (实测: id=1->sid0, id=2->sid1, id=3->sid2, id=4->sid3)
#   播放   /gygplayer/{vid}-{sid}-{nid}.html -> 页面内嵌 var now="...m3u8" 直链, 直接返回
#   搜索   /search.php?searchword={kw}       -> .search-list .item 卡片
# ★ 实测直链: cdn.yddsha2.com / v1.ppqrrs.com 等 m3u8 直链 HEAD 200 可用, 无防盗链
# ★ 沙箱/数据中心 IP 会被 openresty WAF 拒连(非指纹问题), 家庭宽带等正常网络直连即可;
#   已用浏览器通道抓取真实页面验证全部解析规则
# ★ 版本兼容铁律: 全文件禁 3.9+ API (内置 Py<=3.8)
# ★ 分隔符铁律: $=名称/地址 #=选集 $$$=线路; 线路名与地址$$$段数必须相等
# ★ 合规: 站点为免费免登录站, 仅采集公开列表/详情/直链, 无 VIP 破解/验证码绕过/密钥逆向

import sys, re, json, time, threading, socket, ssl, zlib
from urllib.parse import urljoin, quote, unquote

try:
    import requests
except Exception:
    requests = None

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider(object):
        def fetch(self, url, headers=None, **kw):
            if requests is None:
                raise RuntimeError('requests missing')
            kw.pop('timeout', None)
            r = requests.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

# ============ CONFIG ============
HOST = 'https://www.gygxpt.com'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
MUA = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36'
PROBE = True           # 全通道失败时输出探测矩阵(每变体一张短卡片, 便于一键定位可用通道)
PROBE_IP = '154.19.197.245'
PR_BUDGET = 8            # ★探测矩阵总预算(秒): 超预算即跳过剩余变体, 防止失败路径拖到 20s+
PR_TO = 4                # ★探测单变体超时(秒)
FAST_TO = 7              # ★搜索快通道总预算(秒)
LIST_BUDGET = 10         # ★列表取回总预算(秒)
HIDE_EMPTY = True      # ★ 后台体检: 逐个分类试抓, 页面里一个影片链接都没有的分类自动从导航隐藏(治"空白分类")
SWEEP_TTL = 21600      # 体检间隔(秒), 进程内缓存, 默认 6 小时只跑一次
NEED_PIC = True        # ★ 列表过滤: 站点"排行榜"区块(v-rank)是无封面纯文字榜, 混进列表会出现空白图 => 自动滤掉
PX_MODE = 2            # ★ v2.13 播放模式: 0=直连输出 1=智能探测(裸播放器能用才直连) 2=HLS全走本地代理(默认,最稳)
PROXY_M3U8 = True      # ★ 本地代理开关(127.0.0.1:9978-9988): m3u8+分片重写, 治防盗链/需特殊头/跨域分片黑屏
FORCE_PX = False       # ★ 强制 mp4 也走代理(若真机仍有线路黑屏, 改 True)
PX_PORTS = range(9978, 9989)  # 本地代理端口范围(与影视仓/zzoc 同段)
# 完整 41 分类(浏览器实抓, 2026-09-22):
#   电影子类 5-12/28/29 | 电视剧子类 13-16/32/33/34/42
#   综艺子类 45-48 | 动分子类 49-54 | 短剧子类 61-67/69(缺 68)
#   ★ 已剔除: 55 预告(用户指定) / 60 亚洲剧(站点空分类, 详见 DROP_TIDS)
CATEGORIES = {
    '1': '电影', '2': '电视剧', '3': '综艺', '4': '动漫', '30': '短剧',
    '5': '动作片', '6': '爱情片', '7': '科幻片', '8': '恐怖片', '9': '战争片',
    '10': '喜剧片', '11': '纪录片', '12': '剧情片', '28': '悬疑片', '29': '犯罪片',
    '13': '国产剧', '14': '港剧', '15': '欧美剧', '16': '韩剧', '32': '台湾剧',
    '33': '日本剧', '34': '海外剧', '42': '泰剧',
    '45': '国产综艺', '46': '日韩综艺', '47': '港台综艺', '48': '欧美综艺',
    '49': '国产动漫', '50': '日韩动漫', '51': '欧美动漫', '52': '动漫电影',
    '53': '港台动漫', '54': '海外动漫',
    '61': '有声动漫', '62': '女频恋爱', '63': '反转爽剧', '64': '脑洞悬疑',
    '65': '年代穿越', '66': '古装仙侠', '67': '现代都市', '69': '爽文短剧',
}
# 88模板规范: type_pid 为父分类ID, 一级分类 pid=0
# ★ 已按用户要求剔除: 55 预告(用户指定去除) / 60 亚洲剧(站点实测空分类: /gyglist/60.html 返回 200 但 0 卡片、"第0页"、尾页指向自身)
DROP_TIDS = ('55', '60')
TYPE_PIDS = {
    '1': '0', '2': '0', '3': '0', '4': '0', '30': '0',
    '5': '1', '6': '1', '7': '1', '8': '1', '9': '1',
    '10': '1', '11': '1', '12': '1', '28': '1', '29': '1',
    '13': '2', '14': '2', '15': '2', '16': '2', '32': '2',
    '33': '2', '34': '2', '42': '2',
    '45': '3', '46': '3', '47': '3', '48': '3',
    '49': '4', '50': '4', '51': '4', '52': '4',
    '53': '4', '54': '4',
    '61': '30', '62': '30', '63': '30', '64': '30',
    '65': '30', '66': '30', '67': '30', '69': '30',
}
REFERER = HOST + '/'
PIC_REFERER = ''
VIDEO_EXTS = 'm3u8|mp4|flv|mkv|avi|ts'
MIN_GAP = 0.25
RETRY = 2
BACKOFF = 0.35
HDR_BASE = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Cache-Control': 'max-age=0',
    'Upgrade-Insecure-Requests': '1',
    'Connection': 'keep-alive',
}
HOME_MAX = 36          # 首页最多取卡片数(去重后)
CAT_PAGE = 36          # 分类每页实际条数(实测 36)
PLAY_TTL = 900         # 播放直链缓存秒
DETAIL_TTL = 900       # 详情缓存秒
LINE_TTL = 900         # 线路缓存秒
SEARCH_TTL = 300       # 搜索缓存秒
_SEP_NAME_URL = '$'
_SEP_EP = '#'
_SEP_LINE = '$$$'


def _px_proxy():
    import http.server
    from urllib.parse import urlparse, parse_qs

    class _H(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *a):
            pass

        def _out(self, code, ct, body, extra=None):
            try:
                if isinstance(body, str):
                    body = body.encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', ct)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Access-Control-Allow-Origin', '*')
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if body:
                    self.wfile.write(body)
            except Exception:
                pass

        def do_HEAD(self):
            self._out(200, 'application/octet-stream', b'')

        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            ins = Spider._SPK.get((q.get('k') or [''])[0])
            u = (q.get('url') or [''])[0]
            if ins is None or not u:
                return self._out(404, 'text/plain', b'')
            b, ct, extra = ins._pxget(u, self.headers.get('Range'))
            code = 200
            if not b:
                code = 404
            elif extra.get('Content-Range'):
                code = 206
            self._out(code, ct, b or b'', extra)

    return _H


class Spider(Spider):
    def init(self, extend=''):
        self.base = HOST.rstrip('/')
        self.ua = UA
        self.pk = ''
        self.ref = REFERER or self.base
        self._px = None
        self._mkpx(extend)
        self.types = dict(CATEGORIES)
        self.filters = {}
        self._srv = None
        self._lk = threading.Lock()
        self._t0 = 0.0
        self._dg = ''
        self._pc = {}
        self._dc = {}
        self._lc = {}
        self._sc = {}
        self._pcnt = {}
        self._pbc = None
        self._hit = ''
        self._sk = False
        self._pip = None
        self._empty = set()
        self._sw = 0.0
        self._swl = threading.Lock()

    # ========== 网络层 ==========
    def _ensure(self):
        # 兜底自愈: 防止某些加载器未调用 init 就取数据 -> 整页空白
        if getattr(self, '_lk', None) is None:
            self._lk = threading.Lock()
            self._t0 = 0.0
            self._dg = ''
            self._srv = None
            self._px = None
            self._pc = {}
            self._dc = {}
            self._lc = {}
            self._sc = {}
            self._pcnt = {}
            self._pbc = None
            self._hit = ''
            self._sk = False
            self._pip = None
        for ks, kd in (('_empty', set()), ('_sw', 0.0)):
            if getattr(self, ks, None) is None:
                setattr(self, ks, kd)
        if getattr(self, '_swl', None) is None:
            self._swl = threading.Lock()
        if getattr(self, '_sk', None) is None:
            self._sk = False
        if not getattr(self, 'base', None):
            self.base = HOST.rstrip('/')
        if not getattr(self, 'ua', None):
            self.ua = UA
        if not getattr(self, 'ref', None):
            self.ref = self.base + '/'
        if not getattr(self, 'types', None):
            self.types = dict(CATEGORIES)
        if not getattr(self, 'filters', None):
            self.filters = {}

    def _sweep_async(self):
        # 后台体检空分类(不阻塞首页); 结果存 self._empty, 由 homeContent 过滤
        if not HIDE_EMPTY:
            return
        try:
            now = time.time()
            if self._sw and now - self._sw < SWEEP_TTL:
                return
            if not self._swl.acquire(False):
                return
            self._sw = now
            t = threading.Thread(target=self._sweep)
            t.daemon = True
            t.start()
        except Exception:
            pass

    def _sweep(self):
        # 判空规则: 分类页取回成功 且 页面内一个 /gygvod/ 影片链接都没有 => 站点空分类, 隐藏之
        # 取回失败(0字节)视为"不确定", 不动导航(防 WAF 限速时误删); 连续失败即中止(疑似被限速)
        bad = 0
        try:
            for tid in list(CATEGORIES.keys()):
                if tid in DROP_TIDS or tid in self._empty:
                    continue
                try:
                    h = self._get(self.base + '/gyglist/%s.html' % tid, 8)
                except Exception:
                    h = ''
                if not h or len(h) < 1000:
                    bad += 1
                    if bad >= 4:
                        break
                else:
                    bad = 0
                    if '/gygvod/' not in h:
                        self._empty.add(tid)
                self._wait()
                time.sleep(0.6)
        except Exception:
            pass
        finally:
            try:
                self._swl.release()
            except Exception:
                pass

    def _mkpx(self, e):
        # extend 逃生口: ①JSON {"host":"https://新域名","proxy":"socks5://ip:port"}
        #   ②键值 host=https://... proxy=http://... ③裸代理 socks5://ip:port | http://ip:port
        e = (e or '').strip()
        if not e or len(e) > 500:
            return None
        h = p = ''
        d = None
        if e.startswith('{'):
            try:
                d = json.loads(e)
            except Exception:
                d = None
        if isinstance(d, dict):
            h = str(d.get('host') or d.get('domain') or d.get('base') or d.get('site') or '')
            p = str(d.get('proxy') or d.get('px') or '')
        mh = re.search(r'["\']?(?:host|domain|base|site)["\']?\s*[:=]\s*["\']?(https?://[^\s,;"\'}]+)', e)
        if not h and mh:
            h = mh.group(1)
        mp = re.search(r'["\']?(?:proxy|px)["\']?\s*[:=]\s*["\']?((?:https?|socks5h?|socks4)://[^\s,;"\'}]+)', e)
        if not p and mp:
            p = mp.group(1)
        if not h and not p:
            m0 = re.match(r'^\s*((?:https?|socks5h?|socks4)://[^\s,;"\'}]+)\s*$', e)
            if m0:
                p = m0.group(1)
        h = h.strip().rstrip('/')
        if h.startswith('http'):
            self.base = h
            self.ref = h + '/'
        p = (p or '').strip().rstrip('/')
        if p:
            self._px = {'http': p, 'https': p}
        return self._px

    def _sess(self):
        if self._srv is None:
            if requests is None:
                return None
            s = requests.Session()
            s.headers.update({'User-Agent': self.ua})
            try:
                s.trust_env = False          # 忽略设备 HTTP_PROXY 等环境变量(常见 req=ConnectionError 元凶), 代理只走 extend 显式配置
            except Exception:
                pass
            self._h1(s)
            self._srv = s
        return self._srv

    def _ctx(self):
        try:
            c = ssl.create_default_context()
            c.check_hostname = False
            c.verify_mode = ssl.CERT_NONE
            try:
                c.set_alpn_protocols(['http/1.1'])
            except Exception:
                pass
            return c
        except Exception:
            return None

    def _h1(self, s):
        # 实测: 该站拒 HTTP/2(Chromium 直接 net::ERR_HTTP2_PROTOCOL_ERROR, OkHttp/urllib3 默认 h2 => self.fetch 返回空 0 字节)
        # 给 requests 挂 HTTP/1.1-only 适配器(自定 SSLContext + ALPN 只留 http/1.1), 让 req 通道也能通
        try:
            from requests.adapters import HTTPAdapter

            def mk():
                class A(HTTPAdapter):
                    def init_poolmanager(self2, *a, **k):
                        ctx = self._ctx()
                        if ctx is not None:
                            k['ssl_context'] = ctx
                        return HTTPAdapter.init_poolmanager(self2, *a, **k)
                return A()
            s.mount('https://', mk())
            return True
        except Exception:
            return False

    def _reset(self):
        s = self._srv
        self._srv = None
        if s is not None:
            try:
                s.close()
            except Exception:
                pass

    def _wait(self):
        with self._lk:
            d = MIN_GAP - (time.time() - self._t0)
            if d > 0:
                time.sleep(d)
            self._t0 = time.time()

    def _f(self, url, headers=None, tms=8000):
        # fetch 兼容层: 部分 base.spider 实现的 fetch 不接受 timeout 关键字(否则 TypeError 被吞 -> 恒 404)
        try:
            return self.fetch(url, headers=headers, timeout=tms)
        except TypeError:
            try:
                return self.fetch(url, headers=headers)
            except Exception:
                return None
        except Exception:
            return None

    def _hdr(self, ref=None):
        h = dict(HDR_BASE)
        h['User-Agent'] = self.ua
        if ref and ref.rstrip('/') != self.base:
            h['Referer'] = ref
            h['Sec-Fetch-Site'] = 'same-origin'
        else:
            h['Referer'] = self.ref
            h['Sec-Fetch-Site'] = 'none'
        h['Sec-Fetch-User'] = '?1'
        h['Sec-Fetch-Mode'] = 'navigate'
        h['Sec-Fetch-Dest'] = 'document'
        return h

    def _ok(self, t):
        return bool(t) and len(t) > 200

    def _raw(self, url, timeout=15):
        return self._get(url, timeout)

    def _ft(self, url, hdrs=None, tms=8000):
        r = self._f(url, hdrs, tms)
        if r is None:
            return ''
        try:
            return r.text if hasattr(r, 'text') else str(r)
        except Exception:
            return ''

    def _get(self, url, timeout=8):
        # 取回顺序(实测): ① App 自带 HTTP 栈 self.fetch(设备侧可通) ② requests+浏览器头 ③ 裸 socket 兜底
        # openresty WAF 对 Python 客户端特征会掐连接: 单次失败即吐空列表 -> 节流 + 退避 + 多通道重试
        hdrs = self._hdr(self.ref)
        g = []
        t0 = time.time()
        if getattr(self, '_sk', False):
            t = self._rsock(url, timeout, getattr(self, '_pip', None))
            g.append('sock=%d' % len(t))
            if self._ok(t):
                self._dg = ''
                return t
            self._wait()
        for i in range(RETRY):
            if time.time() - t0 > LIST_BUDGET:
                break
            self._wait()
            t = self._ft(url, hdrs, timeout * 1000)
            g.append('app=%d' % len(t))
            if self._ok(t):
                self._dg = ''
                return t
            s = self._sess()
            if s is not None:
                try:
                    r = s.get(url, headers=hdrs, timeout=timeout, allow_redirects=True, proxies=self._px)
                    g.append('req=%s/%d' % (r.status_code, len(r.text)))
                    if r.status_code == 200 and self._ok(r.text):
                        self._dg = ''
                        return r.text
                except Exception as ex:
                    g.append('req=%s' % type(ex).__name__)
                    self._reset()
            else:
                g.append('req=na')
            if i < RETRY - 1:
                time.sleep(BACKOFF * (i + 1))
        t = self._rsock(url, timeout)
        g.append('sock=%d' % len(t))
        self._dg = ' '.join(g[-3:])
        if self._ok(t):
            self._dg = ''
            return t
        return ''

    def _rq(self, url, hdrs, t=PR_TO):
        s = self._sess()
        if s is None:
            return 'na'
        try:
            r = s.get(url, headers=hdrs, timeout=t, allow_redirects=True, proxies=self._px)
            return '%s/%s' % (r.status_code, len(r.text))
        except Exception as ex:
            self._reset()
            return type(ex).__name__

    def _probe(self):
        # 全通道失败时输出探测矩阵: 每变体一张短卡片(名称=值, 同行相邻, 前端截断也不丢配对)
        # ★ 自学习: 哪个变体通了就记 self._hit, 并自动切换 UA/协议/传输, 后续请求直接走它
        if not PROBE:
            return [self._dm()]
        if getattr(self, '_pbc', None):
            return self._pbc
        U = self.base + '/'
        hd = self._hdr(self.ref)
        hm = dict(hd)
        hm['User-Agent'] = MUA
        host = self.base.split('//')[-1]
        V = (
            ('1A应用栈', lambda: str(len(self._ft(U, hd, 4000))), ''),
            ('2R桌面头', lambda: self._rq(U, hd), ''),
            ('3R手机UA', lambda: self._rq(U, hm), 'ua'),
            ('4R极简头', lambda: self._rq(U, {'User-Agent': MUA}), 'ua'),
            ('5H明文80', lambda: self._rq(U.replace('https://', 'http://'), hd), 'http'),
            ('6M移动站', lambda: self._rq('https://m.%s/' % host, hd), 'm'),
            ('7S裸sock', lambda: str(len(self._rsock(U, PR_TO))), 'sock'),
            ('8S直连IP', lambda: str(len(self._rsock(U, PR_TO, PROBE_IP))), 'ip'),
        )
        out = []
        pt0 = time.time()
        for lab, fn, act in V:
            try:
                val = str(fn()) if time.time() - pt0 < PR_BUDGET else '—' 
            except Exception as ex:
                val = type(ex).__name__
            try:
                n = int(val.split('/')[1]) if '/' in val else int(val)
            except Exception:
                n = 0
            ok = (val.startswith('200') and n > 1000) or (n > 1000)
            if ok:
                sh = 'OK' + str(n)
            elif val.startswith('200'):
                sh = '200'
            else:
                sh = val[:4]
            out.append({'vod_id': '0', 'vod_name': '【%s=%s】' % (lab, sh),
                        'vod_pic': self.base + '/templets/gygxpt/images/pic/1.png',
                        'vod_remarks': val[:26], 'type_id': '0', 'type_name': '诊断'})
            if ok and not getattr(self, '_hit', ''):
                self._hit = lab
                try:
                    if act == 'ua':
                        self.ua = MUA
                        self._reset()
                    elif act == 'http':
                        self.base = 'http://' + host
                        self.ref = self.base + '/'
                    elif act == 'm':
                        self.base = 'https://m.' + host
                        self.ref = self.base + '/'
                    elif act == 'sock':
                        self._sk = True
                    elif act == 'ip':
                        self._sk = True
                        self._pip = PROBE_IP
                    self._pbc = None
                    return out
                except Exception:
                    pass
            self._wait()
        self._pbc = out
        return out

    def _fast(self, url, t=FAST_TO):
        # 搜索等前台操作用"快通道": 各通道只试一次, 不做重试/退避, 总耗时硬预算 7s(防 App 侧超时)
        t0 = time.time()
        ex = getattr(self, '_sk', False)
        pip = getattr(self, '_pip', None)
        if ex:
            r0 = self._rsock(url, t, pip)
            if self._ok(r0):
                return r0
            if time.time() - t0 > FAST_TO:
                return ''
        r1 = self._ft(url, self._hdr(self.ref), t * 1000)
        if self._ok(r1):
            return r1
        if time.time() - t0 > FAST_TO:
            return ''
        s = self._sess()
        if s is not None:
            try:
                rr = s.get(url, headers=self._hdr(self.ref), timeout=max(3, int(FAST_TO - (time.time() - t0))), allow_redirects=True, proxies=self._px)
                if rr.status_code == 200 and self._ok(rr.text):
                    return rr.text
            except Exception:
                self._reset()
        if time.time() - t0 > FAST_TO:
            return ''
        r2 = self._rsock(url, max(3, int(FAST_TO + 1 - (time.time() - t0))), pip)
        return r2 if self._ok(r2) else ''

    def _dechunk(self, b):
        out, i = [], 0
        while True:
            j = b.find(b'\r\n', i)
            if j < 0:
                break
            try:
                n = int(b[i:j].split(b';')[0], 16)
            except Exception:
                break
            i = j + 2
            if n == 0:
                break
            out.append(b[i:i + n])
            i += n + 2
        return b''.join(out)

    def _rsock(self, url, timeout=15, ip=None):
        # 末级兜底: 裸 socket HTTP/1.1(强制 ALPN http/1.1 + 浏览器头序), 绕过 requests/urllib3 被 WAF 掐连接的情况
        m = re.match(r'(https?)://([^/]+)(/.*)?$', url)
        if not m:
            return ''
        scheme, host, path = m.group(1), m.group(2), m.group(3) or '/'
        port = 443 if scheme == 'https' else 80
        dial = ip or host
        h = self._hdr()
        order = ('Connection', 'Cache-Control', 'Upgrade-Insecure-Requests', 'User-Agent', 'Accept',
                 'Sec-Fetch-Site', 'Sec-Fetch-Mode', 'Sec-Fetch-User', 'Sec-Fetch-Dest',
                 'Accept-Encoding', 'Accept-Language')
        lines = ['GET %s HTTP/1.1' % path, 'Host: ' + host]
        for k in order:
            if k == 'User-Agent':
                lines.append('User-Agent: ' + self.ua)
            elif k == 'Referer':
                pass
            elif k in h:
                lines.append('%s: %s' % (k, h[k]))
        lines.append('Referer: ' + (h.get('Referer') or self.ref))
        raw = ('\r\n'.join(lines) + '\r\n\r\n').encode()
        try:
            if scheme == 'https':
                c = ssl.create_default_context()
                c.check_hostname = False
                c.verify_mode = ssl.CERT_NONE
                try:
                    c.set_ecdh_curve('prime256v1')
                except Exception:
                    pass
                c.set_alpn_protocols(['http/1.1'])
                s = c.wrap_socket(socket.create_connection((dial, port), timeout=timeout), server_hostname=host)
            else:
                s = socket.create_connection((dial, port), timeout=timeout)
            s.sendall(raw)
            s.settimeout(max(4, timeout - 2))
            buf = b''
            while len(buf) < 4000000:
                try:
                    c2 = s.recv(65536)
                except Exception:
                    break
                if not c2:
                    break
                buf += c2
                if b'\r\n\r\n' in buf:
                    head, _, body = buf.partition(b'\r\n\r\n')
                    low = head.lower()
                    cl = re.search(rb'content-length:\s*(\d+)', low)
                    if cl:
                        if len(body) >= int(cl.group(1)):
                            break
                    elif b'transfer-encoding: chunked' in low and body.endswith(b'0\r\n\r\n'):
                        break
            try:
                s.close()
            except Exception:
                pass
        except Exception:
            return ''
        if not buf.startswith(b'HTTP/') or b' 200' not in buf[:16]:
            return ''
        head, _, body = buf.partition(b'\r\n\r\n')
        low = head.lower()
        if b'transfer-encoding: chunked' in low:
            body = self._dechunk(body)
        if b'content-encoding: gzip' in low:
            try:
                body = zlib.decompress(body, 16 + zlib.MAX_WBITS)
            except Exception:
                pass
        elif b'content-encoding: deflate' in low:
            try:
                body = zlib.decompress(body)
            except Exception:
                try:
                    body = zlib.decompress(body, -zlib.MAX_WBITS)
                except Exception:
                    pass
        for enc in ('utf-8', 'gbk'):
            try:
                return body.decode(enc)
            except Exception:
                pass
        return body.decode('utf-8', 'ignore')

    def _pic(self, u):
        if not u:
            return ''
        if u.startswith('//'):
            u = 'https:' + u
        elif u.startswith('/'):
            u = self.base + u
        return u

    def _wp(self, its):
        # 去掉无封面条目(排行榜纯文字区块), 避免前端出现空白图; 若全无封面则原样返回
        if not NEED_PIC:
            return its
        r = [i for i in its if i.get('vod_pic')]
        return r or its

    def _cget(self, cache, ck, ttl):
        c = cache.get(ck)
        if c and c[1] > time.time():
            return c[0]
        return None

    def _cset(self, cache, ck, v, ttl):
        if len(cache) > 300:            # 防长期运行内存膨胀: 超限先清过期项
            now = time.time()
            for k in [k for k, (_, t) in cache.items() if t <= now]:
                cache.pop(k, None)
        cache[ck] = (v, time.time() + ttl)
        return v

    # ========== 列表卡片解析 ==========
    _G_VOD = re.compile(r'<a\b[^>]*?href="(/gygvod/(\d+)\.html)"[^>]*>')
    _G_ATTR = re.compile(r'title="([^"]*)"')
    _G_ALT = re.compile(r'<img[^>]*alt="([^"]*)"', re.I)
    # data-src/data-original/src 三路兜底; src 允许无扩展名 URL(站点大量封面无后缀)
    _G_IMG = re.compile(
        r'<img[^>]*data-src="([^"]+)"'
        r'|<img[^>]*data-original="([^"]+)"'
        r'|<img[^>]*src="(https?://[^"\s]+)"', re.I)
    _G_TIP = re.compile(r'class="[^"]*v-tips[^"]*"[^>]*>([^<]*)<')

    def _scan(self, h, limit=0):
        # 卡片解析: href/title 属性顺序无关 + 名称三级兜底(title / img.alt / 锚文本)
        items, seen = [], set()
        for m in self._G_VOD.finditer(h):
            vid = m.group(2)
            if not vid or vid in seen:
                continue
            tag = m.group(0)
            blk = h[max(0, m.start() - 500):m.end() + 500]
            nm = ''
            am = self._G_ATTR.search(tag)
            if am:
                nm = am.group(1)
            if not nm:
                im = self._G_ALT.search(blk)
                nm = im.group(1) if im else ''
            if not nm:
                tm = re.match(r'([^<]{2,80})', h[m.end():m.end() + 100] or '')
                nm = tm.group(1) if tm else vid
            pic = self._G_IMG.search(blk)
            tip = self._G_TIP.search(blk)
            seen.add(vid)
            items.append({
                'vod_id': vid,
                'vod_name': re.sub(r'\s+', ' ', nm).strip().rstrip('/').strip()[:80],
                'vod_pic': self._pic(pic.group(1) or pic.group(2) or pic.group(3)) if pic else '',
                'vod_remarks': (tip.group(1).strip() if tip else ''),
            })
            if limit and len(items) >= limit:
                break
        return items

    def _items(self, h):
        return self._scan(h)

    def _items_dedup(self, h, limit=0):
        return self._scan(h, limit)

    # ========== 首页 ==========
    def homeContent(self, filter=False):
        # 88模板首页: 返回分类导航 + 聚合推荐内容; 分类导航必须优先返回(永不空白)
        self._ensure()
        r = {'class': [{'type_id': k, 'type_name': v, 'type_pid': TYPE_PIDS.get(k, '0')} for k, v in self.types.items() if k not in DROP_TIDS and k not in self._empty]}
        self._sweep_async()
        if filter and self.filters:
            r['filters'] = self.filters
        try:
            r['list'] = self.homeVideoContent().get('list', [])
        except Exception:
            r['list'] = [self._dm()]
        return r

    def homeVideoContent(self):
        self._ensure()
        try:
            return self._hv()
        except Exception:
            self._dg = self._dg or '异常'
            return {'list': [self._dm()]}

    def _hv(self):
        # 首页优先: 单请求抓首页解析推荐卡片; 取回失败即快返回(不再轮询多页, 避免 App 侧超时变空状态)
        t0 = time.time()
        items, seen = [], set()
        h = self._get(self.base + '/', 8)
        if h:
            for it in self._wp(self._items(h)):
                vid = it.get('vod_id')
                if vid and vid not in seen:
                    seen.add(vid)
                    items.append(it)
                if len(items) >= HOME_MAX:
                    break
        if h and len(items) < 8 and time.time() - t0 < 9:
            for tid in ('1', '2', '3', '4', '30'):
                if len(items) >= HOME_MAX or time.time() - t0 > 14:
                    break
                hh = self._get(self.base + '/gyglist/%s.html' % tid, 8)
                if not hh:
                    continue
                for it in self._wp(self._items_dedup(hh, 12)):
                    vid = it.get('vod_id')
                    if vid and vid not in seen:
                        seen.add(vid)
                        items.append(it)
                    if len(items) >= HOME_MAX:
                        break
        if not items:
            pv = self._probe()
            if getattr(self, '_hit', ''):
                # 自学习刚认出可用通道 -> 立即用新通道重试一次(避免首次进入首页只看到诊断卡)
                h2 = self._get(self.base + '/', 8)
                items = self._wp(self._items(h2))[:HOME_MAX] if h2 else []
                if not items:
                    c2 = self._get(self.base + '/gyglist/1.html', 8)
                    items = self._wp(self._items_dedup(c2, HOME_MAX)) if c2 else []
            if not items:
                items = pv
        return {'list': items}

    def _dm(self):
        # 取回全失败时的单条快照(短文本, 前端不会截断); 带封面便于必定渲染
        return {'vod_id': '0', 'vod_name': '【诊断】取回失败',
                'vod_pic': self.base + '/templets/gygxpt/images/pic/1.png',
                'vod_remarks': (self._dg or '解析0条')[:26], 'type_id': '0', 'type_name': '诊断'}

    # ========== 分类 ==========
    def categoryContent(self, tid, pg='1', filter=False, extend=''):
        self._ensure()
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        t = str(tid)
        if pn <= 1:
            url = self.base + '/gyglist/%s.html' % t
        else:
            url = self.base + '/gyglist/%s-%d.html' % (t, pn)
        h = self._get(url)
        if not h:
            return {'page': pn, 'pagecount': 1, 'limit': CAT_PAGE, 'total': 0, 'list': self._probe()}
        items = self._items(h)
        if not items and self._dg:
            items = self._probe()
        else:
            items = self._wp(items)
        # TVBox 前端需要 type_id/type_name 做分类关联显示
        for it in items:
            it['type_id'] = t
            it['type_name'] = self.types.get(t, '')
        pcn = self._pagecount(h, t, pn)
        return {'page': pn, 'pagecount': pcn, 'limit': CAT_PAGE,
                'total': pcn * CAT_PAGE, 'list': items}

    def _pagecount(self, h, tid, cur=1):
        # 大站(电影1853页/短剧3371页)每次翻页都全页扫描会很慢 => 按分类缓存 10 分钟
        ck = 'pc:' + str(tid)
        c = self._cget(self._pcnt, ck, 600)
        if c:
            return c
        mx = cur
        for m in re.finditer(r'/gyglist/%s-(\d+)\.html' % re.escape(tid), h):
            try:
                n = int(m.group(1))
                if n > mx:
                    mx = n
            except Exception:
                pass
        if re.search(r'尾页', h):
            m2 = re.search(r'/gyglist/%s-(\d+)\.html' % re.escape(tid), h)
            if m2:
                try:
                    n2 = int(m2.group(1))
                    if n2 > mx:
                        mx = n2
                except Exception:
                    pass
        self._cset(self._pcnt, ck, mx, 600)
        return mx

    # ========== 详情 ==========
    def detailContent(self, ids, quick='1'):
        self._ensure()
        if isinstance(ids, dict):
            ids = [str(ids.get('id') or '')]
        vid = str(ids[0] if isinstance(ids, list) else ids or '')
        vid = vid.split(_SEP_NAME_URL, 1)[0].split('/')[-1]
        m = re.search(r'(\d+)', vid)
        vid = m.group(1) if m else ''
        if not vid:
            return {'list': []}
        ck = 'd:' + vid
        c = self._cget(self._dc, ck, DETAIL_TTL)
        if c:
            return {'list': [c]}
        h = self._get(self.base + '/gygvod/%s.html' % vid)
        if not h:
            return {'list': []}
        d = {
            'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_year': '', 'vod_area': '',
            'vod_class': '', 'vod_director': '', 'vod_actor': '', 'vod_content': '',
            'vod_remarks': '', 'vod_play_from': '', 'vod_play_url': '',
        }
        d['vod_name'] = self._meta(h, 'og:title')
        if not d['vod_name']:
            tn = re.search(r'<title>(.*?)</title>', h, re.S)
            if tn:
                ttl0 = re.sub(r'<[^>]+>', '', tn.group(1)).strip()
                mt = re.match(r'《([^》]*)》', ttl0)
                d['vod_name'] = mt.group(1).strip() if mt else re.sub(r'[【】\-].*$', '', ttl0).strip()
        d['vod_pic'] = self._pic(self._meta(h, 'og:image') or '')
        d['vod_actor'] = self._meta(h, 'og:video:actor')
        d['vod_director'] = self._meta(h, 'og:video:director')
        d['vod_area'] = self._meta(h, 'og:video:area')
        d['vod_class'] = self._meta(h, 'og:video:class')
        if not d['vod_class']:
            d['vod_class'] = self._meta(h, 'og:video:content_type')
        dt = self._meta(h, 'og:video:release_date') or self._meta(h, 'og:video:update_date')
        ym = re.search(r'(\d{4})', dt or '')
        if ym:
            d['vod_year'] = ym.group(1)
        d['vod_content'] = re.sub(r'\s+', ' ', self._meta(h, 'og:description') or '').strip()[:800]
        if not d['vod_content']:
            intro = re.search(r'class="[^"]*infor_intro[^"]*"[^>]*>(.*?)</div>', h, re.S)
            if intro:
                d['vod_content'] = re.sub(r'<[^>]+>', '', intro.group(1)).strip()[:800]
        rmk = re.search(r'class="[^"]*v-tips[^"]*"[^>]*>([^<]*)<', h)
        if rmk:
            d['vod_remarks'] = rmk.group(1).strip()
        if not d['vod_year']:
            ym2 = re.search(r'<title>.*?(\d{4}).*?</title>', h, re.S)
            if ym2:
                d['vod_year'] = ym2.group(1)
        froms, urls = self._lines(h, vid)
        if froms:
            d['vod_play_from'] = _SEP_LINE.join(froms)
            d['vod_play_url'] = _SEP_LINE.join(urls)
        self._cset(self._dc, ck, d, DETAIL_TTL)
        return {'list': [d]}

    def _meta(self, h, prop):
        m = re.search(r'property="%s"\s+content="([^"]*)"' % re.escape(prop), h) or \
            re.search(r'name="%s"\s+content="([^"]*)"' % re.escape(prop), h)
        return m.group(1).strip() if m else ''

    # ========== 线路/选集解析 ==========
    @staticmethod
    def _line_name(txt):
        # 真实页面 tab 文本可能是 "无尽资源7集"(集数直接跟在名称后), 需清洗
        nm = re.sub(r'<sup.*?</sup>', '', txt, flags=re.S)
        nm = re.sub(r'<[^>]+>', '', nm)
        nm = re.sub(r'\s+', ' ', nm).strip()
        nm = re.sub(r'\d+[集期话]?$', '', nm).strip()
        if nm and not nm.endswith('资源'):
            nm = nm.rstrip('资源') + '资源'
        return nm

    def _lines(self, h, vid):
        ck = 'l:' + vid
        c = self._cget(self._lc, ck, LINE_TTL)
        if c:
            return c
        # 线路名: #playNumTab 容器内 a 的文本(DOM序), 避免误抓页面上其它数字 id 链接
        tab_names = []
        mtab = re.search(r'id="playNumTab".*?</div>', h, re.S) or \
            re.search(r'id="playNumTab".*?</ul>', h, re.S)
        tab_h = mtab.group(0) if mtab else h
        for m in re.finditer(r'<a[^>]*id="(\d+)"[^>]*>(.*?)</a>', tab_h, re.S):
            nm = self._line_name(m.group(2))
            if nm:
                tab_names.append((m.group(1), nm))
        if not tab_names:
            tab_names = [('1', '默认')]
        # 选集: 所有 ul.play_num_list, DOM 顺序与 tab 顺序一致(实测 sid=tab id-1)
        uls = re.findall(r'<ul class="[^"]*play_num_list[^"]*"(.*?)</ul>', h, re.S)
        froms, urls = [], []
        for i, ul in enumerate(uls):
            eps = []
            for em in re.finditer(r'<a[^>]*title="([^"]*)"[^>]*href="(/gygplayer/%s-(\d+)-(\d+)\.html)"[^>]*>' % re.escape(vid), ul, re.S):
                name = em.group(1).strip() or '未知'
                eps.append((int(em.group(4) or 0), name, em.group(2)))
            if not eps:
                for em in re.finditer(r'href="(/gygplayer/%s-(\d+)-(\d+)\.html)"[^>]*>([^<]*)</a>' % re.escape(vid), ul, re.S):
                    nm = em.group(4).strip() or em.group(3)
                    eps.append((int(em.group(3) or 0), nm, em.group(1)))
            if not eps:
                continue
            eps.sort(key=lambda x: x[0])
            fname = tab_names[i][1] if i < len(tab_names) else ('线路%d' % (i + 1))
            froms.append(fname)
            urls.append(_SEP_EP.join('%s%s%s' % (n, _SEP_NAME_URL, u) for _, n, u in eps))
        # 兜底: 线路tab缺失时按 sid 直接拼
        if not froms and re.search(r'/gygplayer/%s-\d+-\d+\.html' % re.escape(vid), h):
            for i in range(8):
                seg = re.findall(r'<a[^>]*title="([^"]*)"[^>]*href="(/gygplayer/%s-%d-\d+\.html)"[^>]*>' % (re.escape(vid), i), h, re.S)
                if not seg:
                    continue
                eps = ['%s%s%s' % (n, _SEP_NAME_URL, u) for n, u in seg]
                froms.append('线路%d' % (i + 1))
                urls.append(_SEP_EP.join(eps))
        res = (froms, urls)
        self._cset(self._lc, ck, res, LINE_TTL)
        return res

    # ========== 搜索 ==========
    def searchContent(self, key, quick=False, pg='1'):
        self._ensure()
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        kw = re.sub(r'\s+', ' ', str(key or '')).strip()
        if not kw:
            return {'list': [], 'page': pn, 'pagecount': 1}
        ck = 's:%s:%s' % (kw, pn)
        c = self._cget(self._sc, ck, SEARCH_TTL)
        if c:
            return dict(c)
        url = self.base + '/search.php?searchword=%s' % quote(kw)
        if pn > 1:
            url += '&page=%d' % pn
        h = self._fast(url, 6)
        items = self._wp(self._search_items(h)) if h else []
        pcn, tot = self._spc(h, pn)
        if quick and len(items) > 1:
            k2 = kw.lower()
            fl = [i for i in items if k2 in (i.get('vod_name') or '').lower()]
            items = fl or items
        r = {'list': items, 'page': pn, 'pagecount': pcn, 'limit': max(len(items), 20), 'total': tot}
        if items:
            self._cset(self._sc, ck, r, SEARCH_TTL)
        return r

    def _spc(self, h, pn=1):
        # 搜索页尾"共296部 2/60" -> (总页数, 总条数)
        if not h:
            return 1, 0
        t = re.sub(r'&nbsp;', ' ', re.sub(r'<[^>]+>', ' ', h))
        tot = 0
        mt = re.search(r'共\s*(\d+)\s*部', t)
        if mt:
            try:
                tot = int(mt.group(1))
            except Exception:
                tot = 0
        pcn = pn
        mp = re.search(r'(\d+)\s*/\s*(\d+)', t)
        if mp:
            try:
                pcn = max(int(mp.group(2)), pn)
            except Exception:
                pcn = pn
        return pcn, tot

    def _search_items(self, h):
        items, seen = [], set()
        for m in re.finditer(r'class="[^"]*item clearfix[^"]*"(.*?)(?=class="[^"]*item clearfix|</div>\s*</div>\s*</div>)', h, re.S):
            blk = m.group(1)
            v = re.search(r'href="(/gygvod/(\d+)\.html)"', blk)
            if not v:
                continue
            vid = v.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            pic = re.search(r'<img[^>]*data-src="([^"]+)"|<img[^>]*src="(https?://[^"\s]+\.(?:jpe?g|png|webp|gif)(?:\?[^"\s]*)?)"', blk, re.I)
            name = re.search(r'<strong>([^<]*)</strong>', blk)
            tip = re.search(r'class="[^"]*v-tips[^"]*"[^>]*>([^<]*)<', blk)
            if name is None:
                ialt = re.search(r'<img[^>]*alt="([^"]*)"', blk)
                name = ialt
            nm0 = re.sub(r'\s+', ' ', (name.group(1) if name else '')).strip().rstrip('/').strip()
            items.append({
                'vod_id': vid,
                'vod_name': nm0[:80],
                'vod_pic': self._pic(pic.group(1) or pic.group(2)) if pic else '',
                'vod_remarks': (tip.group(1).strip() if tip else ''),
            })
        if not items:
            items = self._scan(h)
        return items

    # ========== 播放 ==========
    def playerContent(self, flag, id, vipFlags=None):
        self._ensure()
        if isinstance(id, dict):
            id = id.get('url') or id.get('id') or ''
        raw = str(id) if id else str(flag)
        ck = 'p:' + raw[:120]
        c = self._cget(self._pc, ck, PLAY_TTL)
        if c:
            return dict(c)
        url = ''
        if _SEP_NAME_URL in raw:
            url = raw.split(_SEP_NAME_URL, 1)[1]
        else:
            url = raw
        if not url:
            return {'parse': 0, 'url': ''}
        if re.search(r'\.(m3u8|mp4|flv|mkv|avi|ts)(\?|$)', url, re.I):
            return self._cset(self._pc, ck, self._mkplay(url), PLAY_TTL)
        full = url if url.startswith('http') else urljoin(self.base, url)
        h = self._get(full, 6)
        u = self._parse_play(h) if h else ''
        if not u:
            u = self._alt_play(full)
        r = self._mkplay(u) if u else {'parse': 0, 'url': ''}
        if u:
            self._cset(self._pc, ck, r, PLAY_TTL)
        return r

    def _parse_play(self, h):
        m = re.search(r'var\s+now="([^"]*)"', h) or \
            re.search(r'var\s+now\s*=\s*["\']([^"\']+)["\']', h)
        if m:
            u = m.group(1).strip()
            if u.startswith('http'):
                return u
        m2 = re.search(r'(https?://[^\s"\'<>]+\.m3u8(?:\?[^\s"\'<>]*)?)', h)
        if m2:
            return m2.group(1)
        return ''

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
            self._dc.clear()
            self._lc.clear()
            self._sc.clear()
            self._pcnt.clear()
            if self._srv is not None:
                self._srv.close()
        except Exception:
            pass
        self._srv = None
        try:
            o = getattr(self, '_pxobj', None)
            if o is not None:
                o.shutdown()
        except Exception:
            pass

    def progressVideo(self, speed, time, end):
        return False

    def setVideoFlags(self, siteKey, flags):
        try:
            self._siteKey = siteKey or ''
            self._vflags = flags or {}
        except Exception:
            pass

    # ========== 本地代理(兜底): m3u8 KEY/分片重写 + 图片转码 ==========
    # ========== v2.13 播放本地代理(m3u8+分片重写, 治防盗链/需特殊头) ==========

    _SPK = {}

    def _srvup(self):
        s = getattr(self, '_pxsrv', None)
        if s:
            return s
        try:
            import http.server
            P = _px_proxy()
            srv = None
            for p in PX_PORTS:
                try:
                    srv = http.server.ThreadingHTTPServer(('127.0.0.1', p), P)
                    break
                except Exception:
                    srv = None
            if srv is None:
                return None
            srv.daemon_threads = True
            k = 'k%d' % (int(time.time() * 1000) % 100000000)
            Spider._SPK[k] = self
            self._pk = k
            self._pxsrv = (k, p)
            self._pxobj = srv
            t = threading.Thread(target=srv.serve_forever)
            t.daemon = True
            t.start()
            return self._pxsrv
        except Exception:
            return None

    def _pxq(self, u):
        return 'p?url=%s&k=%s' % (quote(u, safe=''), getattr(self, '_pk', ''))

    def _px_url(self, u):
        s = self._srvup()
        if not s:
            return ''
        return 'http://127.0.0.1:%d/p?url=%s&k=%s' % (s[1], quote(u, safe=''), s[0])

    def _pxm3u8(self, body, url):
        base = url.rsplit('/', 1)[0] + '/'
        og = re.match(r'https?://[^/]+', url)
        og = og.group(0) if og else ''
        out = []
        for ln in body.splitlines():
            if ln.startswith('#EXT-X-KEY'):
                m = re.search(r'URI="([^"]+)"', ln)
                if m:
                    ku = m.group(1)
                    ku = ku if ku.startswith('http') else (og + ku if ku.startswith('/') else base + ku)
                    ln = ln.replace('URI="%s"' % m.group(1), 'URI="%s"' % self._pxq(ku))
            elif ln and not ln.startswith('#'):
                u2 = ln if ln.startswith('http') else (og + ln if ln.startswith('/') else base + ln)
                ln = self._pxq(u2)
            out.append(ln)
        return chr(10).join(out)

    def _rq_raw(self, u, hh):
        if requests is not None:
            r = requests.get(u, headers=hh, timeout=15, proxies=None)
            if r.status_code == 200 and r.content:
                return r.content, (r.headers.get('Content-Type') or ''), (r.headers.get('Content-Range') or '')
            if r.status_code == 206 and r.content:
                return r.content, (r.headers.get('Content-Type') or ''), (r.headers.get('Content-Range') or '')
            return b'', '', ''
        t = self._ft(u, hh, 15000)
        return (t.encode('utf-8', 'ignore') if t else b''), '', ''

    def _pxget(self, u, rng=None):
        u = unquote(u)
        hs = {'User-Agent': self.ua, 'Referer': self.ref, 'Accept': '*/*'}
        if rng:
            hs['Range'] = rng
        b, ct, cr = b'', '', ''
        for hh in (hs, {'User-Agent': self.ua, 'Accept': '*/*'}):
            try:
                b, ct, cr = self._rq_raw(u, hh)
            except Exception:
                b, ct, cr = b'', '', ''
            if b:
                break
        if not b:
            t = self._rsock(u, 15) or ''
            if t:
                b, ct, cr = t.encode('utf-8', 'ignore'), '', ''
        if not b:
            return b'', 'text/plain', {}
        extra = {}
        if rng:
            extra['Accept-Ranges'] = 'bytes'
            if cr:
                extra['Content-Range'] = cr
        if b[:7] == b'#EXTM3U':
            try:
                return self._pxm3u8(b.decode('utf-8', 'ignore'), u).encode('utf-8'), 'application/vnd.apple.mpegurl', {}
            except Exception:
                return b, 'application/vnd.apple.mpegurl', {}
        if not ct or 'text/plain' in ct:
            p = u.split('?')[0].lower()
            ct = 'video/mp2t' if p.endswith('.ts') else ('image/jpeg' if p.endswith(('.jpg', '.jpeg')) else ('image/png' if p.endswith('.png') else ('video/mp4' if p.endswith('.mp4') else 'application/octet-stream')))
        return b, ct, extra

    def _need_px(self, u):
        # 裸播放器模拟: 不带 Referer 拉 m3u8/子列表/首分片; 必失败 = 防盗链 => 必须走代理
        # 主机级缓存: 同一 CDN 只探一次(_nh), 避免每个影片都重复探
        hm = re.match(r'https?://([^/]+)', u or '')
        host = hm.group(1) if hm else ''
        nh = getattr(self, '_nh', None) or {}
        if host in nh:
            return nh[host]
        ck = 'n:' + u[:120]
        nc = getattr(self, '_nc', None) or {}
        c = self._cget(nc, ck, PLAY_TTL)
        if c is None:
            ok = False
            try:
                hh = {'User-Agent': self.ua, 'Accept': '*/*'}
                b, _c, _r = self._rq_raw(u, hh)
                if b and b[:7] == b'#EXTM3U':
                    ok = True
                    t = b.decode('utf-8', 'ignore')
                    vs = [l for l in t.splitlines() if l and not l.startswith('#')]
                    cur = u
                    if '#EXT-X-STREAM-INF' in t and vs:
                        cur = vs[0] if vs[0].startswith('http') else u.rsplit('/', 1)[0] + '/' + vs[0]
                        b2, _c2, _r2 = self._rq_raw(cur, hh)
                        vs = [l for l in b2.decode('utf-8', 'ignore').splitlines() if l and not l.startswith('#')] if (b2 and b2[:7] == b'#EXTM3U') else []
                        if not vs:
                            ok = False
                    if ok and vs:
                        s0 = vs[0] if vs[0].startswith('http') else cur.rsplit('/', 1)[0] + '/' + vs[0]
                        hh2 = dict(hh)
                        hh2['Range'] = 'bytes=0-1023'
                        b3, _c3, _r3 = self._rq_raw(s0, hh2)
                        if not b3:
                            ok = False
            except Exception:
                ok = False
            self._nc = nc
            self._cset(nc, ck, ok, PLAY_TTL)
            c = ok
        if host:
            self._nh = nh
            nh[host] = c
        return c

    def _alt_play(self, url):
        # 同集自动换线: 当前线路取不出 m3u8 时, 依次试其它 sid 的同集(最多 8 条线路)
        m = re.search(r'/gygplayer/(\d+)-(\d+)-(\d+)\.html', url or '')
        if not m:
            return ''
        vid, sid, nid = m.group(1), int(m.group(2)), m.group(3)
        t0 = time.time()
        for sx in range(0, 8):
            if sx == sid:
                continue
            if time.time() - t0 > 5:
                break
            hh = self._get(self.base + '/gygplayer/%s-%d-%s.html' % (vid, sx, nid))
            if not hh:
                continue
            u = self._parse_play(hh)
            if u:
                return u
        return ''

    def _mkplay(self, u):
        # PX_MODE 2/HLS: 播放链(m3u8)默认走本地代理重写(零探测, 播放器不用带妖头, 也不受跨域分片影响);
        # PX_MODE 1: 智能探测(裸播放器能拉通就直连, 省代理开销, 但多 2-3 次探测请求)
        if not u:
            return {'parse': 0, 'url': ''}
        is_hls = 'm3u8' in u.lower()
        use = PROXY_M3U8 and (FORCE_PX or (PX_MODE == 2 and is_hls) or (PX_MODE == 1 and self._need_px(u)))
        if use:
            pu = self._px_url(u)
            if pu:
                return {'parse': 0, 'url': pu, 'header': {'User-Agent': self.ua}}
        return {'parse': 0, 'url': u, 'header': {'User-Agent': self.ua, 'Referer': self.ref}}

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
            r = self._f(p, {'User-Agent': self.ua, 'Referer': self.ref}, 20000)
            if r is None:
                return [404, 'text/plain', '']
            if hasattr(r, 'status_code') and r.status_code != 200:
                return [r.status_code, 'text/plain', '']
            return [200, r.headers.get('Content-Type', 'application/octet-stream'), r.content]
        except Exception:
            return [404, 'text/plain', '']

    def _rewrite_m3u8(self, url):
        try:
            r = self._f(url, {'User-Agent': self.ua, 'Referer': self.ref}, 20000)
            if r is None:
                return [404, 'text/plain', '']
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
            elif ln and not ln.startswith('#') and not ln.startswith('//') and not ln.startswith('proxy'):
                # 相对路径行(如 master 内 "1000k_720/hls/index.m3u8")补全为代理绝对地址
                ln = 'proxy?url=' + quote(base + ln, safe='')
            out.append(ln)
        return [200, 'application/vnd.apple.mpegurl', '\n'.join(out)]

    def _img(self, u):
        try:
            if requests is None:
                return [404, 'text/plain', '']
            r = requests.get(u, headers={'User-Agent': self.ua, 'Referer': PIC_REFERER or self.ref}, timeout=15)
            if r.status_code != 200 or len(r.content) < 100:
                return [r.status_code or 404, 'text/plain', '']
            return [200, r.headers.get('Content-Type', 'image/jpeg'), r.content]
        except Exception:
            return [404, 'text/plain', '']

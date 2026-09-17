# -*- coding: utf-8 -*-
# 黄果短剧 融合版
# 融合优势：
#   - 动态/多域名容灾 + 官方主站优先
#   - 分类 JSON API（最稳） + HTML 回退
#   - 完整分类：精选/上新/AI四类/专题/排行/吃瓜/作者
#   - 封面 AES 解密 + 本地图片代理（Referer 防盗链）
#   - 播放优先 videoInitialData JSON 直取 m3u8（parse:0）
#   - 吃瓜文章多源支持
#   - BeautifulSoup + 正则双解析
# 依赖：requests, beautifulsoup4, pycryptodome (或 Crypto)
# 适配 TVBox / 类 TVBox 壳

import sys
import re
import json
import time
import base64
import random
import string
import threading
import html as htmllib
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        pass

try:
    import requests as rq
    rq.packages.urllib3.disable_warnings()
except Exception:
    pass

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from Crypto.Cipher import AES
except ImportError:
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        AES = None

# ---------- 常量 ----------


def _gen_random_subdomain():
    """生成 3-6 位随机小写字母数字子域名"""
    length = random.randint(3, 6)
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def _gen_backup_hosts(n=8):
    """生成 n 个随机泛域名备用 (https://*.ediayikma.cc)"""
    return [f"https://{_gen_random_subdomain()}.ediayikma.cc" for _ in range(n)]


HOSTS = ["https://huangguoai.com"] + _gen_backup_hosts(8)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 18
PAGE_SIZE = 24
# AES 封面解密（站点 CDN 加密）
_AES_KEY = b'f5d965df75336270'
_AES_IV = b'97b60394abc2fbe1'
_PLACEHOLDER_GIF = base64.b64decode(
    'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
_PROXY_PORT = [0]
_TAG_RE = re.compile(r'<[^>]+>')
_LABEL_RE = re.compile(r'<[^>]+>')  # 剧集标签去标签用，预编译复用

# 一次性探测 BS4 解析器（避免每次解析都字符串检测）
_BS4_PARSER = None
if BeautifulSoup is not None:
    try:
        BeautifulSoup("<a/>", "lxml")
        _BS4_PARSER = "lxml"
    except Exception:
        _BS4_PARSER = "html.parser"


def _clean(s):
    if not s:
        return ""
    s = htmllib.unescape(str(s))
    s = _TAG_RE.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()


# ---------- 本地图片代理服务器 ----------
try:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    def _fetch_img_raw(u, referer):
        headers = {"User-Agent": UA, "Referer": referer,
                   "Accept": "image/*"}
        try:
            rr = rq.get(u, headers=headers, timeout=15, verify=False,
                        allow_redirects=True)
            if rr.status_code == 200 and rr.content and len(rr.content) > 50:
                return rr.content
        except Exception:
            pass
        return b''

    def _decrypt_img(data):
        if not data or AES is None:
            return data
        # 已是正常图片则直接返回
        if data[:3] == b'\xff\xd8\xff' or data[:8] == b'\x89PNG\r\n\x1a\n' \
                or data[:6] in (b'GIF87a', b'GIF89a') \
                or (data[:4] == b'RIFF' and data[8:12] == b'WEBP'):
            return data
        try:
            dec = AES.new(_AES_KEY, AES.MODE_CBC, _AES_IV).decrypt(data)
            # 去 PKCS7 / 尾部 null
            pad = dec[-1]
            if 1 <= pad <= 16 and all(b == pad for b in dec[-pad:]):
                dec = dec[:-pad]
            else:
                dec = dec.rstrip(b'\x00')
            if dec[:3] == b'\xff\xd8\xff' or dec[:8] == b'\x89PNG\r\n\x1a\n':
                return dec
            return dec  # 仍返回尝试结果
        except Exception:
            return data

    def _detect_mime(data):
        if data[:3] == b'\xff\xd8\xff':
            return 'image/jpeg'
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return 'image/gif'
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return 'image/webp'
        return 'image/jpeg'

    class _ImgHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                pr = urllib.parse.urlparse(self.path)
                if pr.path not in ('/img', '/proxy'):
                    self.send_response(404)
                    self.end_headers()
                    return
                q = urllib.parse.parse_qs(pr.query)
                u = q.get('u', q.get('url', ['']))[0]
                u = urllib.parse.unquote(u)
                if not u.startswith('http'):
                    self.send_response(400)
                    self.end_headers()
                    return
                raw = _fetch_img_raw(u, HOSTS[0] + "/")
                data = _decrypt_img(raw) if raw else b''
                if not data or len(data) < 50:
                    data, ctype = _PLACEHOLDER_GIF, 'image/gif'
                else:
                    ctype = _detect_mime(data)
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'max-age=86400')
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                pass

        def log_message(self, *args):
            pass

    def _start_proxy_server():
        if _PROXY_PORT[0]:
            return _PROXY_PORT[0]
        for port in [9978] + list(range(9979, 10020)) + list(range(30261, 30281)):
            try:
                srv = HTTPServer(('127.0.0.1', port), _ImgHandler)
                _PROXY_PORT[0] = port
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                return port
            except Exception:
                continue
        return 0
except Exception:
    def _start_proxy_server():
        return 0
    def _decrypt_img(data):
        return data
    def _detect_mime(data):
        return 'image/jpeg'


class Spider(Spider):

    # 主站连续失败超过该阈值后，自动把 self.host 切到首个可用备用
    _PRIMARY_FAIL_THRESHOLD = 3

    def getName(self):
        return "黄果短剧"

    def init(self, extend=""):
        primary = HOSTS[0].rstrip('/')
        # 立即用主站，不阻塞等待备用探测
        self.host = primary
        # 已验证可用的备用域名列表（后台线程填充，主站失败时直接用）
        self._working_backups = []
        # 主站连续失败计数（达到阈值自动切主 host）
        self._primary_fails = [0]

        try:
            self.s = rq.Session()
            self.s.verify = False
            self.s.headers.update({
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": self.host + "/",
            })
            try:
                from requests.adapters import HTTPAdapter
                _adapter = HTTPAdapter(
                    pool_connections=16, pool_maxsize=32, max_retries=0)
                self.s.mount('http://', _adapter)
                self.s.mount('https://', _adapter)
            except Exception:
                pass
        except Exception:
            self.s = None
        self._list_cache = {}
        try:
            _start_proxy_server()
        except Exception:
            pass

        # 后台预热：立即并行探测所有备用域名，写入 _working_backups
        # 主线程不等，直接进入服务；主站失败时立刻从预热好的列表取
        try:
            t = threading.Thread(target=self._prefetch_backups, daemon=True)
            t.start()
        except Exception:
            pass

    @staticmethod
    def _probe_host(h):
        """单机探测：返回可用 host，否则 None"""
        try:
            r = rq.get(h.rstrip('/'), headers={"User-Agent": UA}, timeout=4, verify=False)
            if r.status_code == 200 and (
                    '黄果' in r.text or 'huangguo' in r.text.lower()
                    or len(r.text) > 2000):
                return h.rstrip('/')
        except Exception:
            pass
        return None

    def _prefetch_backups(self):
        """后台预热：并行探测所有备用域名，按成功顺序写入 _working_backups"""
        primary = HOSTS[0].rstrip('/')
        backups = [h.rstrip('/') for h in HOSTS[1:] if h.rstrip('/') != primary]
        if not backups:
            return
        results = []
        _lock = threading.Lock()

        def _do_probe(h):
            r = self._probe_host(h)
            if r:
                with _lock:
                    results.append(r)

        with ThreadPoolExecutor(max_workers=min(6, len(backups))) as ex:
            list(ex.map(_do_probe, backups, timeout=10))
        # 原子写入（浅拷贝即可）
        self._working_backups = results

    def _switch_host(self, new_host):
        """切 host：同时更新 Session 的 Referer header，保持一致"""
        new_host = (new_host or "").rstrip('/')
        if not new_host:
            return
        self.host = new_host
        try:
            if self.s is not None:
                self.s.headers["Referer"] = new_host + "/"
        except Exception:
            pass

    def _fetch_one(self, host, path, ref, timeout):
        """单 host 请求（线程安全：不依赖 self.s）"""
        url = host + path
        try:
            headers = {"Referer": host + ref}
            r = rq.get(url, timeout=timeout, verify=False, allow_redirects=True,
                       headers={"User-Agent": UA,
                                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                                "Accept-Language": "zh-CN,zh;q=0.9",
                                **headers})
            if r.status_code == 200 and r.text:
                r.encoding = 'utf-8'
                return r.text
        except Exception:
            pass
        return ""

    def _wrap_pic(self, url):
        """封面走本地代理（带 Referer + AES 解密）"""
        if not url or not str(url).startswith('http'):
            return url or ""
        if not _PROXY_PORT[0]:
            _start_proxy_server()
        if _PROXY_PORT[0]:
            return ("http://127.0.0.1:%d/proxy?url=%s"
                    % (_PROXY_PORT[0], urllib.parse.quote(url, safe='')))
        # 无代理时退回 TVBox localProxy 格式
        try:
            b = base64.b64encode(url.encode('utf-8')).decode('ascii')
            return f"proxy://type=pic&url={b}"
        except Exception:
            return url

    def _get(self, path, ref="/"):
        # 完整 URL 直接请求
        if path.startswith("http"):
            try:
                headers = {"Referer": self.host.rstrip('/') + ref}
                if self.s is not None:
                    r = self.s.get(path, timeout=TIMEOUT, allow_redirects=True, headers=headers)
                else:
                    r = rq.get(path, timeout=TIMEOUT, verify=False,
                               headers={"User-Agent": UA, **headers})
                if r.status_code == 200 and r.text:
                    r.encoding = 'utf-8'
                    return r.text
            except Exception:
                pass
            return ""

        # 路径形式：主站优先；主站失败立即用预热好的备用
        primary = HOSTS[0].rstrip('/')
        current = getattr(self, 'host', primary).rstrip('/')

        # 1) 优先用当前 host（通常是主站或已切到的备用）
        try:
            url = current + path
            headers = {"Referer": current + ref}
            if self.s is not None:
                r = self.s.get(url, timeout=8, allow_redirects=True, headers=headers)
            else:
                r = rq.get(url, timeout=8, verify=False,
                           headers={"User-Agent": UA, **headers})
            if r.status_code == 200 and r.text:
                r.encoding = 'utf-8'
                # 成功：重置主站失败计数
                try:
                    self._primary_fails[0] = 0
                except (AttributeError, IndexError):
                    pass
                return r.text
        except Exception:
            pass

        # 2) 当前 host 失败：累计主站失败，达到阈值后把默认 host 切到首个可用备用
        is_primary = (current == primary)
        if is_primary:
            try:
                self._primary_fails[0] += 1
                if (self._primary_fails[0] >= self._PRIMARY_FAIL_THRESHOLD
                        and getattr(self, '_working_backups', None)):
                    self._switch_host(self._working_backups[0])
            except (AttributeError, IndexError):
                pass

        # 3) 取预热好的可用备用域名，并行请求，立即切换
        try:
            known_good = list(getattr(self, '_working_backups', None) or [])
        except Exception:
            known_good = []
        # 排除当前已失败的 current
        candidates = [h for h in known_good if h != current][:4]

        # 如果预热列表为空（后台线程还没跑完），取 HOSTS 静态前几个作为兜底
        if not candidates:
            all_hosts = [h.rstrip('/') for h in HOSTS if h.rstrip('/') != current]
            # 优先：若预热还在跑但已有部分结果，加上已预热的去重
            seen = set(all_hosts[:4])
            for h in known_good:
                if h not in seen and len(candidates) < 4:
                    candidates.append(h)
                    seen.add(h)
            candidates = all_hosts[:4] if not candidates else candidates

        if not candidates:
            return ""

        with ThreadPoolExecutor(max_workers=len(candidates)) as ex:
            futs = {ex.submit(self._fetch_one, h, path, ref, 6): h for h in candidates}
            try:
                for fut in as_completed(futs, timeout=8):
                    try:
                        text = fut.result()
                        if text:
                            for f in futs:
                                f.cancel()
                            won = futs[fut]
                            # 切换主 host 以备后续复用（下次请求直接用这个）
                            self._switch_host(won)
                            return text
                    except Exception:
                        continue
            except Exception:
                pass
        return ""

    def _get_cached(self, path, ref="/", ttl=60):
        """列表类请求短缓存：60s 内复用结果，减少重复请求"""
        try:
            cache = self._list_cache
        except AttributeError:
            cache = self._list_cache = {}
        key = path
        now = time.time()
        cached = cache.get(key)
        if cached and now - cached[1] < ttl:
            return cached[0]
        text = self._get(path, ref)
        if text:
            cache[key] = (text, now)
            # 清理过期项，避免无限增长
            if len(cache) > 80:
                for k in list(cache.keys()):
                    if now - cache[k][1] > ttl:
                        cache.pop(k, None)
        return text

    def isVideoFormat(self, url):
        return any(x in (url or '') for x in ['.m3u8', '.mp4', '.flv', '.mkv', '.avi'])

    def manualVideoCheck(self):
        return False

    # ---------- 首页 ----------
    def homeContent(self, filter=False):
        result = {
            "class": [
                {"type_id": "recommend", "type_name": "精选推荐"},
                {"type_id": "newest", "type_name": "最近上新"},
                {"type_id": "ai-duanju", "type_name": "AI成人短剧"},
                {"type_id": "ai-manju", "type_name": "AI成人漫剧"},
                {"type_id": "ai-huanlian", "type_name": "AI换脸"},
                {"type_id": "ai-mogai", "type_name": "AI魔改"},
                {"type_id": "topic", "type_name": "📌专题"},
                {"type_id": "ranks", "type_name": "排行榜"},
                {"type_id": "chigua", "type_name": "黄果吃瓜"},
                {"type_id": "author", "type_name": "黄果官方"},
            ],
            "list": [],
            "filters": {
                "ranks": [{"key": "类型", "name": "类型", "value": [
                    {"n": "热播榜", "v": "hot"},
                    {"n": "推荐榜", "v": "recommend"},
                    {"n": "潜力榜", "v": "potential"},
                ]}],
                "chigua": [{"key": "类型", "name": "类型", "value": [
                    {"n": "全部", "v": "page"},
                    {"n": "热门吃瓜", "v": "remen"},
                    {"n": "AI原创", "v": "yuanchuang"},
                ]}],
                "author": [{"key": "类型", "name": "类型", "value": [
                    {"n": "黄果官方", "v": "156291"},
                    {"n": "黄果ai大师", "v": "156305"},
                ]}],
            }
        }
        if filter:
            pass
        try:
            html = self._get_cached("/")
            if html:
                result["list"] = self._parse_list(html)
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        try:
            html = self._get_cached("/recommend/1/")
            if not html:
                html = self._get_cached("/")
            return {"list": self._parse_list(html)}
        except Exception:
            return {"list": []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        try:
            pg = int(str(pg or 1))
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        cid = str(tid or "").strip().strip("/")
        ext = extend if isinstance(extend, dict) else {}
        rc = ext.get("类型", cid)

        videos, pages, total = [], 9999, 0

        try:
            # 专题文件夹
            if cid.startswith("dir_topic_"):
                slug = cid.replace("dir_topic_", "")
                html = self._get_cached(f"/topics/{slug}/?page={pg}")
                videos = self._parse_list(html, mode="drama")
                return self._result(videos, pg, 9999)

            # AI 四分类优先 JSON API
            if cid in ("ai-duanju", "ai-manju", "ai-huanlian", "ai-mogai"):
                videos, pages, total = self._category_api(cid, pg)
                if not videos:
                    path = f"/{cid}/" if pg <= 1 else f"/{cid}/{pg}/"
                    html = self._get_cached(path)
                    videos = self._parse_list(html)
                    ps = [int(x) for x in re.findall(
                        r'/' + re.escape(cid) + r'/(\d+)/', html or "")]
                    if ps:
                        pages = max(ps)
                if len(videos) > PAGE_SIZE:
                    videos = videos[:PAGE_SIZE]
                return self._result(videos, pg, pages or 9999, total)

            # 其它固定路径
            if cid == "recommend":
                html = self._get_cached(f"/recommend/{pg}/")
                videos = self._parse_list(html)
            elif cid == "newest":
                html = self._get_cached(f"/newest/{pg}/")
                videos = self._parse_list(html)
            elif cid == "topic":
                html = self._get_cached("/topics/")
                videos = self._parse_list(html, mode="topic")
                pages = 1
            elif cid == "ranks":
                rtype = rc if rc in ("hot", "recommend", "potential") else "hot"
                html = self._get_cached(f"/ranks/{rtype}/")
                videos = self._parse_list(html, mode="rank")
                pages = 1
            elif cid == "chigua":
                ctype = rc if rc in ("page", "remen", "yuanchuang") else "page"
                html = self._get_cached(f"/chigua/{ctype}/{pg}/")
                videos = self._parse_list(html, mode="post")
            elif cid == "author":
                aid = rc if str(rc).isdigit() else "156291"
                html = self._get(f"/author/{aid}/video/{pg}/")
                videos = self._parse_list(html)
            else:
                # 兜底当普通分类
                path = f"/{cid}/" if pg <= 1 else f"/{cid}/{pg}/"
                html = self._get(path)
                videos = self._parse_list(html)

        except Exception:
            videos = []

        return self._result(videos, pg, pages, total)

    def _category_api(self, slug, pg):
        url = (f"/api/videos/category/{urllib.parse.quote(slug)}"
               f"?sort=hot&page={pg}&size={PAGE_SIZE}")
        text = self._get_cached(url, ref="/" + slug + "/")
        if not text:
            return [], 0, 0
        try:
            data = json.loads(text)
        except Exception:
            return [], 0, 0
        d = data.get("data") or {}
        items = d.get("items") or []
        pag = d.get("pagination") or {}
        videos = []
        for it in items:
            v = self._api_item(it)
            if v:
                videos.append(v)
        pages = total = 0
        try:
            pages = int(pag.get("pages") or 0)
        except Exception:
            pass
        try:
            total = int(pag.get("total") or 0)
        except Exception:
            pass
        return videos, pages, total

    def _api_item(self, it):
        vid = it.get("id")
        if vid is None:
            return None
        title = _clean(it.get("title"))
        if not title:
            return None
        pic = (it.get("cover") or "").strip()
        epc = it.get("episode_count")
        finished = it.get("is_finished")
        if finished:
            remark = "全%d集" % epc if epc else "全剧"
        else:
            remark = "更新至%d集" % epc if epc else "连载中"
        score = it.get("score")
        if score:
            remark = f"{score}分 " + remark
        return {
            "vod_id": str(vid),
            "vod_name": title,
            "vod_pic": self._wrap_pic(pic),
            "vod_remarks": remark or "在线观看",
        }

    def _result(self, videos, pg, pagecount=9999, total=0):
        n = len(videos)
        if total < 1:
            total = pagecount * max(n, 1) if pagecount > 1 else n
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": total,
        }

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, page):
        kw = urllib.parse.quote(str(key or "").strip())
        if not kw:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = int(page) if page else 1
        except Exception:
            pg = 1
        html = self._get(f"/search/video/{kw}/{pg}/")
        videos = self._parse_list(html, mode="search")
        has_more = len(videos) >= 18
        return {
            "page": pg,
            "pagecount": pg + 1 if has_more else pg,
            "limit": 20,
            "total": 0,
            "list": videos,
        }

    # ---------- 详情 ----------
    def detailContent(self, ids):
        try:
            raw = ids[0] if isinstance(ids, (list, tuple)) else ids
            did = str(raw).strip()
        except Exception:
            return {"list": []}
        if not did:
            return {"list": []}

        # 吃瓜文章
        if "/archives/" in did or did.startswith("http") and "archives" in did:
            return self._detail_chigua(did)

        # 统一成纯数字 id
        m = re.search(r'(?:detail/|/)?(\d+)/?$', did)
        vid = m.group(1) if m else (did if did.isdigit() else None)
        # 预取 video 页（剧集列表可能在 play 页），与 detail 页并行
        # detail 用 _get（支持 host 容灾），video 用 _fetch_one 并行预取
        vhtml = ""
        if vid:
            primary = self.host.rstrip('/')
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut_video = ex.submit(self._fetch_one, primary,
                                      f"/video/{vid}/", "/", 10)
                html = self._get(f"/detail/{vid}/")
                vhtml = fut_video.result()
        else:
            # 可能是完整路径
            html = self._get(did if did.startswith("/") else "/" + did)

        if not html:
            return {"list": []}

        title = ""
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if m:
            title = _clean(m.group(1))
        if not title:
            m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            if m:
                title = _clean(m.group(1))
        if not title:
            m = re.search(r'<title>(.*?)</title>', html)
            if m:
                title = _clean(m.group(1).split('|')[0])
        if not title:
            return {"list": []}

        pic = ""
        m = re.search(r'<img[^>]*data-src="([^"]+)"[^>]*>', html)
        if m:
            pic = htmllib.unescape(m.group(1)).strip()
        if not pic:
            m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if m:
                pic = htmllib.unescape(m.group(1)).strip()

        desc = ""
        m = re.search(r'<p class="[^"]*hg-web-detail__desc[^"]*"[^>]*>(.*?)</p>', html, re.S)
        if m:
            desc = _clean(m.group(1))
        if not desc:
            m = re.search(r'<meta name="description" content="([^"]+)"', html)
            if m:
                desc = _clean(m.group(1))

        meta = ""
        m = re.search(r'class="[^"]*hg-web-detail__meta[^"]*"[^>]*>(.*?)</div>', html, re.S)
        if m:
            meta = _clean(m.group(1))
        tags = []
        for m in re.finditer(r'class="hg-tag"[^>]*href="(/tag/[^"]+)"[^>]*>([^<]+)<', html):
            tags.append(_clean(m.group(2)))
        remark = meta or "在线观看"

        # 剧集列表
        # 标签策略：只信任 URL 集数，URL 无集数时用计数器，忽略 <a> 文本
        # （<a> 文本含"正在播放"等状态词、图标字符、HTML 实体，不可靠）
        eps = []
        seen = set()
        ep_re = (r'href="(/video/' + re.escape(vid)
                 + r'/[^"]*?)"[^>]*>(.*?)</a>')
        _ep_num_re = re.compile(r'/(?:ep-?|episode-?|p|play-?)(\d+)/?', re.I)
        _fallback_seq = [0]

        def _label_from_path(path):
            """只从 URL 提取集数；无集数则用计数器，绝不读 <a> 文本"""
            m = _ep_num_re.search(path or "")
            if m:
                return "%02d" % int(m.group(1))
            _fallback_seq[0] += 1
            return "%02d" % _fallback_seq[0]

        if vid:
            for m in re.finditer(ep_re, html, re.S):
                path = m.group(1)
                if not path.startswith("/video/"):
                    continue
                if path in seen:
                    continue
                label = _label_from_path(path)
                seen.add(path)
                eps.append((label, path))
            # 有时剧集在 play 页（vhtml 已并行预取）
            if not eps:
                for m in re.finditer(ep_re, vhtml or "", re.S):
                    path = m.group(1)
                    if not path.startswith("/video/") or path in seen:
                        continue
                    label = _label_from_path(path)
                    seen.add(path)
                    eps.append((label, path))
                # data-ep 形式
                if not eps and vhtml:
                    for m in re.finditer(
                            r'<a[^>]*class="hg-play__ep-item[^"]*"[^>]*href="([^"]*)"[^>]*data-ep-id="([^"]*)"[^>]*>(.*?)</a>',
                            vhtml, re.S):
                        path = m.group(1)
                        ep_id = m.group(2)
                        # 优先 URL 集数，其次 data-ep-id，最后计数器
                        label = _label_from_path(path)
                        if ep_id and ep_id.isdigit() and label.startswith("0") and not _ep_num_re.search(path or ""):
                            label = "%02d" % int(ep_id)
                        if not path.startswith('/'):
                            path = '/' + path
                        if path not in seen:
                            seen.add(path)
                            eps.append((label, path))

        eps = sorted(eps, key=lambda x: self._ep_sort(x[1]))
        if not eps and vid:
            eps = [("01", f"/video/{vid}/")]

        play_from = ["正片"]
        play_url = ["#".join(f"{l}${p}" for l, p in eps)]

        vod = {
            "vod_id": vid or did,
            "vod_name": title,
            "vod_pic": self._wrap_pic(pic),
            "type_name": ",".join(tags) or "黄果短剧",
            "vod_remarks": remark,
            "vod_content": desc,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
            "vod_year": "",
            "vod_area": "",
            "vod_actor": "",
            "vod_director": "",
        }
        return {"list": [vod]}

    def _detail_chigua(self, url):
        if not url.startswith("http"):
            url = self.host.rstrip('/') + (url if url.startswith('/') else '/' + url)
        try:
            html = self._get(url.replace(self.host, "")) if url.startswith(self.host) else ""
            if not html:
                r = rq.get(url, headers={"User-Agent": UA, "Referer": self.host + "/"},
                           timeout=TIMEOUT, verify=False)
                html = r.text if r.status_code == 200 else ""
        except Exception:
            return {"list": []}
        if not html:
            return {"list": []}

        title = ""
        m = re.search(r'<title>(.*?)</title>', html)
        if m:
            title = _clean(m.group(1).split('|')[0])

        players = re.findall(
            r'<div class="post-video-player"[^>]*data-player-key="([^"]*)"[^>]*data-src="([^"]*)"', html)
        if not players:
            players = re.findall(r'data-src="(https?://[^"]+\.m3u8[^"]*)"', html)
            players = [(f"线路{i+1}", u) for i, u in enumerate(players)]

        play = "#".join([f"{k}${v.replace('&amp;', '&')}" for k, v in players]) if players else ""

        video = {
            "vod_id": url,
            "vod_name": title or "吃瓜",
            "vod_pic": "",
            "vod_remarks": "",
            "vod_content": title,
            "type_name": "黄果吃瓜",
            "vod_play_from": "黄果吃瓜",
            "vod_play_url": play or f"正片${url}",
            "vod_year": "", "vod_area": "", "vod_actor": "", "vod_director": "",
        }
        return {"list": [video]}

    @staticmethod
    def _ep_sort(path):
        # 兼容多种集数格式：/ep-N/ /episode-N/ /pN/ /epN/ /play-N/
        m = re.search(r'/(?:ep-?|episode-?|p|play-?)(\d+)/?', path or "", re.I)
        return int(m.group(1)) if m else 0

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None, vipIds=None):
        key = str(id or "").strip()
        if not key:
            return {"parse": 0, "url": "", "header": {"User-Agent": UA}}

        def _norm(u):
            """规范化播放地址：处理转义、协议相对路径"""
            if not u:
                return ""
            u = str(u).replace("\\u0026", "&").replace("&amp;", "&").strip()
            if u.startswith("//"):
                u = "https:" + u
            return u

        def _direct(url):
            url = _norm(url)
            if not url:
                return ""
            if url.startswith("http") and self.isVideoFormat(url):
                return url
            # 部分 CDN 直链无扩展名，靠 auth_key/playlist.m3u8 等关键字
            if url.startswith("http") and any(
                    x in url for x in ['auth_key', 'playlist.m3u8', '/m3u8/', '.m3u8']):
                return url
            return ""

        # 已是直链
        if key.startswith("http"):
            u = _direct(key)
            if u:
                return {
                    "parse": 0,
                    "url": u,
                    "header": {"User-Agent": UA, "Referer": self.host + "/"},
                }

        # 吃瓜直链
        if flag == "黄果吃瓜" and key.startswith("http"):
            return {
                "parse": 0,
                "url": _norm(key),
                "header": {"User-Agent": UA, "Referer": self.host + "/"},
            }

        # 纯数字 vid → 转 /video/{vid}/
        if key.isdigit():
            key = f"/video/{key}/"
        elif not key.startswith("/") and not key.startswith("http"):
            key = "/" + key

        html = self._get(key, ref="/")
        if not html:
            # 兜底交给 TVBox 嗅探
            return {
                "parse": 1,
                "url": self.host.rstrip('/') + key,
                "header": {"User-Agent": UA, "Referer": self.host + "/"},
            }

        # 优先 videoInitialData
        m = re.search(
            r'<script id="videoInitialData" type="application/json">(.*?)</script>',
            html, re.S)
        if m:
            try:
                # 修复 JSON 截断：找到最长的可解析片段
                raw = m.group(1)
                data = None
                # 尝试整体解析
                try:
                    data = json.loads(raw)
                except Exception:
                    # 截尾尝试：可能是 </script> 提前截断
                    for end in range(len(raw), max(0, len(raw) - 2000), -1):
                        try:
                            data = json.loads(raw[:end])
                            break
                        except Exception:
                            continue
                if data:
                    # 多字段兼容取直链
                    url = ""
                    for k in ("videoSrc", "videoUrl", "playUrl", "src",
                              "url", "video_src", "play_url"):
                        v = data.get(k)
                        if v and isinstance(v, str):
                            url = v
                            break
                    if not url:
                        # 剧集字典
                        eps = None
                        for k in ("epPlaySrcs", "episodes", "playSrcs",
                                  "ep_play_srcs", "playSources"):
                            v = data.get(k)
                            if isinstance(v, dict):
                                eps = v
                                break
                        if eps:
                            ep = data.get("ep") or data.get("episode") or data.get("currentEp")
                            if ep is not None and str(ep) in eps:
                                url = eps[str(ep)]
                            else:
                                # 兼容 ep1 / episode-1 等键名
                                for ek, ev in eps.items():
                                    if str(ep) in str(ek):
                                        url = ev
                                        break
                                if not url:
                                    for ev in eps.values():
                                        if ev:
                                            url = ev
                                            break
                    url = _norm(url)
                    if url.startswith("http"):
                        return {
                            "parse": 0,
                            "url": url,
                            "header": {"User-Agent": UA, "Referer": self.host + "/"},
                        }
            except Exception:
                pass

        # 回退 data-play-src：优先 is-active，其次任意
        m = re.search(
            r'<article[^>]*class="[^"]*hg-play__slide[^"]*is-active[^"]*"[^>]*data-play-src="([^"]*)"',
            html)
        if not m:
            m = re.search(r'data-play-src="(https?://[^"]+)"', html)
        if m:
            url = _norm(m.group(1))
            if url.startswith("http"):
                return {
                    "parse": 0,
                    "url": url,
                    "header": {"User-Agent": UA, "Referer": self.host + "/"},
                }

        # 所有解析失败：交 TVBox 嗅探当前页
        return {
            "parse": 1,
            "url": self.host.rstrip('/') + key,
            "header": {"User-Agent": UA, "Referer": self.host + "/"},
        }

    # ---------- 本地代理（TVBox 调用） ----------
    def localProxy(self, param):
        try:
            if isinstance(param, dict):
                if param.get("type") == "pic":
                    return self._proxy_pic(param)
                url = param.get("url") or param.get("u") or ""
            else:
                url = self._resolve_img_param(param)
            if not url:
                return None
            headers = {"User-Agent": UA, "Referer": self.host + "/", "Accept": "image/*"}
            rr = rq.get(url, headers=headers, timeout=15, verify=False, allow_redirects=True)
            if rr.status_code == 200 and rr.content and len(rr.content) > 50:
                data = _decrypt_img(rr.content)
                ctype = _detect_mime(data)
                return [200, ctype, data]
        except Exception:
            pass
        return None

    def _proxy_pic(self, params):
        try:
            raw = params.get("url") or ""
            if not raw.startswith("http"):
                try:
                    raw = base64.b64decode(raw + "==").decode("utf-8", "ignore")
                except Exception:
                    pass
            if not raw.startswith("http"):
                return None
            headers = {"User-Agent": UA, "Referer": self.host + "/"}
            data = rq.get(raw, headers=headers, timeout=15, verify=False).content
            data = _decrypt_img(data)
            mime = _detect_mime(data)
            return [200, mime, data]
        except Exception:
            return None

    @staticmethod
    def _resolve_img_param(param):
        if not param:
            return ""
        p = str(param).strip()
        p = re.sub(r'^https?://127\.0\.0\.1:\d+/proxy\?', '', p)
        p = re.sub(r'^proxy\?', '', p)
        if "url=" in p:
            q = urllib.parse.parse_qs(p)
            cand = q.get("url", [""])[0]
            if cand:
                p = cand
        try:
            p = urllib.parse.unquote(p)
        except Exception:
            pass
        if not p.startswith("http"):
            try:
                dec = base64.b64decode(p + "==").decode("utf-8", "ignore")
                if dec.startswith("http"):
                    p = dec
            except Exception:
                pass
        return p if p.startswith("http") else ""

    # ---------- 列表解析 ----------
    def _parse_list(self, html, mode="drama"):
        if not html or len(html) < 150:
            return []
        if BeautifulSoup is not None:
            try:
                return self._parse_bs4(html, mode)
            except Exception:
                pass
        return self._parse_regex(html)

    def _parse_bs4(self, html, mode):
        videos, seen = [], set()
        doc = BeautifulSoup(html, _BS4_PARSER or "html.parser")

        if mode == "drama" or mode == "search":
            # 通用卡片
            for card in doc.select("div.hg-drama-card"):
                a = card.find("a", href=True)
                if not a:
                    continue
                href = a.get("href", "")
                m = re.search(r"/detail/(\d+)", href)
                if not m:
                    continue
                vid = m.group(1)
                if vid in seen:
                    continue
                seen.add(vid)
                img = card.find("img")
                pic = ""
                if img:
                    pic = img.get("data-src") or img.get("src") or ""
                title = ""
                if img:
                    title = img.get("alt") or ""
                if not title:
                    t = card.select_one(".hg-drama-card__title a, .hg-drama-card__title, h2, h3")
                    title = t.get_text(strip=True) if t else ""
                if not title:
                    title = card.get("data-track-title") or ""
                parts = []
                for sel in [".hg-drama-card__score", ".hg-drama-card__episode",
                            ".hg-drama-card__badge"]:
                    el = card.select_one(sel)
                    if el:
                        parts.append(el.get_text(strip=True))
                remark = " ".join(parts).strip() or "在线观看"
                if title:
                    videos.append({
                        "vod_id": vid,
                        "vod_name": _clean(title),
                        "vod_pic": self._wrap_pic(pic),
                        "vod_remarks": remark,
                    })

            # search 补充
            if mode == "search" and not videos:
                for a in doc.find_all("a", href=re.compile(r"/detail/\d+")):
                    m = re.search(r"/detail/(\d+)", a.get("href", ""))
                    if not m or m.group(1) in seen:
                        continue
                    seen.add(m.group(1))
                    img = a.find("img")
                    if not img:
                        continue
                    pic = img.get("data-src") or img.get("src") or ""
                    title = img.get("alt") or img.get("title") or a.get("title") or ""
                    if not title:
                        t = a.find(class_=re.compile("title"))
                        title = t.get_text(strip=True) if t else ""
                    remark = ""
                    for cls in ["episode", "score"]:
                        s = a.find(class_=re.compile(cls))
                        if s:
                            remark = s.get_text(strip=True)
                            break
                    if title:
                        videos.append({
                            "vod_id": m.group(1),
                            "vod_name": _clean(title),
                            "vod_pic": self._wrap_pic(pic),
                            "vod_remarks": remark or "在线观看",
                        })

        elif mode == "rank":
            for item in doc.select("div.hg-rank-item"):
                a = item.find("a", href=True, class_=re.compile("cover")) or item.find("a", href=True)
                if not a:
                    continue
                href = a.get("href", "")
                m = re.search(r"/detail/(\d+)", href)
                vid = m.group(1) if m else href
                if vid in seen:
                    continue
                seen.add(vid)
                img = item.find("img")
                pic = (img.get("data-src") or img.get("src") or "") if img else ""
                title = item.get("data-track-title") or (img.get("alt") if img else "") or ""
                if not title:
                    t = item.select_one(".hg-rank-item__title, h2")
                    title = t.get_text(strip=True) if t else ""
                heat = item.select_one(".hg-rank-item__heat-value")
                remark = ("🔥" + heat.get_text(strip=True)) if heat else ""
                if title:
                    videos.append({
                        "vod_id": vid,
                        "vod_name": _clean(title),
                        "vod_pic": self._wrap_pic(pic),
                        "vod_remarks": remark,
                    })

        elif mode == "topic":
            for card in doc.select("a.hg-topic-card"):
                href = card.get("href", "")
                slug = href.strip("/").split("/")[-1]
                img = card.find("img")
                pic = (img.get("data-src") or img.get("src") or "") if img else ""
                t = card.select_one(".hg-topic-card__title, h2")
                title = t.get_text(strip=True) if t else (img.get("alt") if img else "")
                meta = card.select_one(".hg-topic-card__meta")
                remark = meta.get_text(strip=True) if meta else ""
                if title:
                    videos.append({
                        "vod_id": "dir_topic_" + slug,
                        "vod_name": _clean(title),
                        "vod_pic": self._wrap_pic(pic),
                        "vod_remarks": remark,
                        "vod_tag": "folder",
                    })

        elif mode == "post":
            for card in doc.select("a.hg-post-card"):
                href = card.get("href", "")
                if not href:
                    continue
                img = card.find("img")
                pic = (img.get("data-src") or img.get("src") or "") if img else ""
                h3 = card.find("h3")
                title = h3.get_text(strip=True) if h3 else ""
                date = card.select_one(".hg-post-card__date")
                cat = card.select_one(".hg-post-card__cat")
                parts = [s.get_text(strip=True) for s in (date, cat) if s]
                videos.append({
                    "vod_id": href if href.startswith("http") else self.host + href,
                    "vod_name": _clean(title),
                    "vod_pic": self._wrap_pic(pic),
                    "vod_remarks": " | ".join(parts),
                })

        return videos

    def _parse_regex(self, html):
        """无 BS4 时的正则兜底（与第一版兼容）"""
        result, seen = [], set()
        for block in re.split(r'<div class="hg-drama-card"', html)[1:]:
            m = re.search(r'href="(/detail/(\d+)/)"', block)
            if not m:
                continue
            vid = m.group(2)
            if vid in seen:
                continue
            pic = ""
            pm = re.search(r'data-src="([^"]+)"', block)
            if pm:
                pic = htmllib.unescape(pm.group(1)).strip()
            if not pic:
                pm = re.search(r'<img[^>]*src="([^"]+)"', block)
                if pm:
                    pic = htmllib.unescape(pm.group(1)).strip()
            title = ""
            tm = re.search(
                r'class="[^"]*hg-drama-card__title[^"]*"[^>]*>\s*<a[^>]*>(.*?)</a>',
                block, re.S)
            if tm:
                title = _clean(tm.group(1))
            if not title:
                tm = re.search(r'<img[^>]*alt="([^"]+)"', block)
                if tm:
                    title = _clean(tm.group(1))
            parts = []
            sm = re.search(r'class="hg-drama-card__score">([^<]+)<', block)
            if sm:
                parts.append(_clean(sm.group(1)))
            em = re.search(r'class="hg-drama-card__episode">([^<]+)<', block)
            if em:
                parts.append(_clean(em.group(1)))
            remark = " ".join(parts).strip() or "在线观看"
            if not title:
                continue
            seen.add(vid)
            result.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": self._wrap_pic(pic),
                "vod_remarks": remark,
            })
        return result

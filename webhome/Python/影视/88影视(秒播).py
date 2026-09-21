# coding=utf-8
# ============================================================================
# 88影视(88ayyc) · 影视壳 / TVBox 本地 py 源  (type 3 / drpy py 模式)
# ----------------------------------------------------------------------------
# 安装三步:
#   1) 壳子的配置目录下建一个 py 文件夹(和 api.json 放同一层)
#   2) 本文件丢进去,确保文件名是 ayyc.py  →  <配置目录>/py/ayyc.py
#   3) api.json 里对应站点已经写好了,不用改:
#      {"key":"ayyc","name":"88影视","type":3,"api":"./py/ayyc.py",
#       "searchable":1,"quickSearch":1,"filterable":1,
#       "ext":"https://88ayyc35.6p.tattoo"}
#      换域名只改 ext 就行,脚本不用动。
#
# 实现说明:
#   · 目标站所有页面都是「双层 base64」包装,本脚本内部自动解开
#   · 标准采集口 /api.php/provide/vod/ 已被站方关闭,别往那填
#   · 列表走 /index.php/ajax/data?mid=1&tid=&page= (标准 vod JSON)
#   · 播放地址走播放页里的 player_aaaa 变量,m3u8 直链明文(encrypt=0)
#   · 分类列表只给元数据(秒回),点进去才拉 m3u8,顺带后台预热下一页
# ============================================================================

import base64
import gzip
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
except Exception:
    BaseHTTPRequestHandler = ThreadingHTTPServer = None

sys.path.append('..')
try:
    from base.spider import Spider as _Base
except Exception:
    _Base = object

try:
    import requests as _rq
except Exception:
    _rq = None


# ---------------------------------------------------------------- 配置
DEFAULT_BASE = "https://88ayyc35.6p.tattoo"
SITE_NAME = "88影视"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 12
CACHE_TTL = 300

# 页面分类入口 -> 站点真实分类id（/vod/type 或 /art/type）
# 视频 /index.php/vod/detail/id/{id}.html  mid=1
# 小说/美图 /index.php/art/detail/id/{id}.html  mid=2；小说 type_pid=37，美图 type_pid=38
CAT_MAP = {
    "精选": "2",
    "乱伦": "9",
    "暗网": "18",
    "热门": "27",
    "推荐": "67",
    "小说": "37",
    "美图": "38",
}
NOVEL_TIDS = set("37 39 53 54 55 56 57 58".split())
IMAGE_TIDS = set("38 43 59 60 61 62 63 64 65".split())

_ORDER = {
    "key": "order",
    "name": "排序",
    "value": [
        {"n": "最新", "v": "createdAt"},
        {"n": "最热", "v": "viewCount"},
    ],
}

CLASSES = [
    {"type_id": "精选", "type_name": "精选"},
    {"type_id": "乱伦", "type_name": "乱伦"},
    {"type_id": "暗网", "type_name": "暗网"},
    {"type_id": "热门", "type_name": "热门"},
    {"type_id": "推荐", "type_name": "推荐"},
    {"type_id": "小说", "type_name": "小说"},
    {"type_id": "美图", "type_name": "美图"},
]

FILTERS = {
    "精选": [
        _ORDER,
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "全部", "v": "精选"},
            {"n": "黑料吃瓜", "v": "3"},
            {"n": "厂牌原创", "v": "4"},
            {"n": "国产精选", "v": "5"},
            {"n": "明星换脸", "v": "6"},
            {"n": "AV解说", "v": "7"},
            {"n": "禁漫精选", "v": "8"},
        ]},
    ],
    "乱伦": [
        _ORDER,
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "全部", "v": "乱伦"},
            {"n": "父女", "v": "10"},
            {"n": "母子", "v": "11"},
            {"n": "兄妹", "v": "12"},
            {"n": "学生", "v": "13"},
            {"n": "嫂子", "v": "14"},
            {"n": "姐夫", "v": "15"},
            {"n": "师生", "v": "16"},
        ]},
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "全家", "v": "17"},
        ]},
    ],
    "暗网": [
        _ORDER,
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "全部", "v": "暗网"},
            {"n": "真实缅北", "v": "79"},
            {"n": "恶心恐怖", "v": "80"},
            {"n": "黄金圣水", "v": "81"},
            {"n": "校园霸凌", "v": "82"},
            {"n": "人兽乱交", "v": "84"},
            {"n": "战场实录", "v": "83"},
            {"n": "灵异视频", "v": "85"},
        ]},
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "N号房", "v": "86"},
        ]},
    ],
    "热门": [
        _ORDER,
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "全部", "v": "热门"},
            {"n": "国产大片", "v": "28"},
            {"n": "日韩大片", "v": "87"},
            {"n": "欧美大片", "v": "31"},
            {"n": "网红直播", "v": "32"},
            {"n": "探花约炮", "v": "33"},
            {"n": "SM调教", "v": "88"},
            {"n": "三级伦理", "v": "34"},
        ]},
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "萝莉开苞", "v": "35"},
        ]},
    ],
    "推荐": [
        _ORDER,
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "全部", "v": "推荐"},
            {"n": "AI魔改", "v": "69"},
            {"n": "cosplay", "v": "68"},
            {"n": "av综艺", "v": "70"},
            {"n": "ts人妖", "v": "76"},
            {"n": "姿势玩法", "v": "77"},
            {"n": "同性恋", "v": "78"},
            {"n": "嫩妹下海", "v": "72"},
        ]},
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "每日甄选", "v": "74"},
        ]},
    ],
    "小说": [
        _ORDER,
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "全部", "v": "小说"},
            {"n": "都市激情", "v": "39"},
            {"n": "连淫幻想", "v": "58"},
            {"n": "玄幻仙侠", "v": "57"},
            {"n": "恋情偷情", "v": "56"},
            {"n": "国风伦理", "v": "55"},
            {"n": "少妇偷情", "v": "54"},
            {"n": "校园情色", "v": "53"},
        ]},
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "有声小说", "v": "66"},
        ]},
    ],
    "美图": [
        _ORDER,
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "全部", "v": "美图"},
            {"n": "一手原创", "v": "63"},
            {"n": "丝袜美腿", "v": "62"},
            {"n": "网友自拍", "v": "43"},
            {"n": "街拍偷拍", "v": "61"},
            {"n": "露出激情", "v": "60"},
            {"n": "唯美写真", "v": "59"},
            {"n": "欧美风情", "v": "64"},
        ]},
        {"key": "videoTag", "name": "分类", "value": [
            {"n": "卡通漫画", "v": "65"},
        ]},
    ],
}


# ---------------------------------------------------------------- 海报解密
# 站上海报挂在 aisearch.cdn.bcebos.com 的 .txt 里,内容是 base64(原图 XOR 密钥)。
# 密钥取自站点前端脚本,解密方式 = 逐字节和密钥循环异或,解出来就是原图。
# vod_pic_thumb / vod_pic_slide 那个域名(rgvgd.ebailx.com)已经解析不出来了,是死的,
# 所以海报只能走 vod_pic 解密这条路。壳子自己不会解密,本脚本起一个本地小服务
# (127.0.0.1)把解好的图直接吐给壳子。
IMG_KEY = "OzoTeoS7D>6Y^@z39JmD"
IMG_KEY_BYTES = [ord(c) for c in IMG_KEY]
PIC_PORTS = (9988, 9989, 9990, 9991, 18765, 18766, 18767)
PIC_CACHE_DIR = os.path.join(tempfile.gettempdir(), "ayyc_pic_cache")
PIC_MEM_MAX = 400          # 内存里最多缓存多少张
PIC_WARM_WORKERS = 6       # 后台预热海报的并发


# ---------------------------------------------------------------- 底层工具
def _headers(base, referer=None):
    return {
        "User-Agent": UA,
        "Referer": referer or (base + "/"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "close",
    }


def _http(url, base, referer=None):
    """抓一个 URL 返回文本,自动处理 gzip / 编码"""
    hdr = _headers(base, referer)
    if _rq is not None:
        r = _rq.get(url, headers=hdr, timeout=TIMEOUT)
        return r.content.decode("utf-8", "ignore")

    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip" or raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    for codec in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(codec)
        except Exception:
            continue
    return raw.decode("utf-8", "ignore")


def _b64(text):
    s = "".join(text.split())
    pad = (-len(s)) % 4
    try:
        return base64.b64decode(s + "=" * pad).decode("utf-8")
    except Exception:
        return None


def _unwrap(text):
    """目标站把真内容套了两层 base64: var str='<b64>' -> 再 b64 -> 真内容"""
    if not text:
        return text
    m = re.search(r"var\s+str\s*=\s*'([^']+)'", text)
    if not m:
        m = re.search(r'var\s+str\s*=\s*"([^"]+)"', text)
    if not m:
        return text
    cur = m.group(1)
    for _ in range(2):
        nxt = _b64(cur)
        if not nxt or not nxt.strip():
            break
        cur = nxt
    return cur


def _pic_mime(b):
    if b[:4] == b"\x89PNG":
        return "image/png"
    if b[:3] == b"GIF":
        return "image/gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return ""


def _pic_cache_path(url):
    return os.path.join(PIC_CACHE_DIR,
                        hashlib.md5(url.encode("utf-8")).hexdigest())


def _decode_pic(raw):
    """拿到的一坨字节 → 原始图片字节。两种形态:
       ① 直接就是图片(有些 CDN 是明文图) ② base64(原图 XOR 密钥)"""
    if not raw or len(raw) < 64:
        return b"", ""
    mime = _pic_mime(raw)
    if mime:
        return raw, mime
    txt = raw.strip()
    try:
        bin_ = base64.b64decode(txt + b"=" * ((-len(txt)) % 4))
    except Exception:
        return b"", ""
    if not bin_:
        return b"", ""
    out = bytes(b ^ IMG_KEY_BYTES[i % len(IMG_KEY_BYTES)]
                for i, b in enumerate(bin_))
    mime = _pic_mime(out)
    if not mime:
        return b"", ""
    return out, mime


def load_pic(url):
    """拿一张海报的原始图片字节,带磁盘缓存。返回 (bytes, mime)"""
    if not url or not url.startswith("http"):
        return b"", ""
    cp = _pic_cache_path(url)
    try:
        if os.path.exists(cp) and os.path.getsize(cp) > 64:
            with open(cp, "rb") as f:
                b = f.read()
            mime = _pic_mime(b)
            if mime:
                return b, mime
    except Exception:
        pass
    b, mime = b"", ""
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": DEFAULT_BASE + "/"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
            b, mime = _decode_pic(raw)
            if b:
                break
        except Exception:
            time.sleep(0.3)
    if b:
        try:
            os.makedirs(PIC_CACHE_DIR, exist_ok=True)
            with open(cp, "wb") as f:
                f.write(b)
        except Exception:
            pass
    return b, mime


# ---- 本地图片小服务:壳子不会解密,这里解好直接喂给它 ----
_pic_state = {"port": 0, "mem": {}, "lock": threading.Lock(), "tried": False}


def _pic_b64(url):
    return base64.urlsafe_b64encode(url.encode("utf-8")).decode().rstrip("=")


def _pic_unb64(tag):
    return base64.urlsafe_b64decode(tag + "=" * ((-len(tag)) % 4)).decode("utf-8")


def _pic_handler_factory():
    class _H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            try:
                path = urllib.parse.urlparse(self.path).path
                if not path.startswith("/p/"):
                    self.send_error(404)
                    return
                tag = path[3:]
                if "." in tag:
                    tag = tag.rsplit(".", 1)[0]
                url = _pic_unb64(tag)
                data, mime = b"", ""
                with _pic_state["lock"]:
                    mem = _pic_state["mem"].get(url)
                if mem:
                    data, mime = mem
                if not data:
                    data, mime = load_pic(url)
                    if data:
                        with _pic_state["lock"]:
                            if len(_pic_state["mem"]) < PIC_MEM_MAX:
                                _pic_state["mem"][url] = (data, mime)
                if not data:
                    self.send_response(302)
                    self.send_header("Location", url)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", mime or "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=604800")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                try:
                    self.send_error(500)
                except Exception:
                    pass

    return _H


def pic_server_port():
    """起本地图片服务,返回端口;起不来返回 0"""
    if _pic_state["port"]:
        return _pic_state["port"]
    with _pic_state["lock"]:
        if _pic_state["port"] or _pic_state["tried"]:
            return _pic_state["port"]
        _pic_state["tried"] = True
        if ThreadingHTTPServer is None:
            return 0
        for port in PIC_PORTS:
            try:
                srv = ThreadingHTTPServer(("127.0.0.1", port), _pic_handler_factory())
            except Exception:
                continue
            srv.daemon_threads = True
            try:
                threading.Thread(target=srv.serve_forever, daemon=True).start()
            except Exception:
                continue
            _pic_state["port"] = port
            return port
    return 0


def _pic_url(url):
    """把海报换成「本地服务地址」;服务起不来就原样返回,不影响出片"""
    if not url or not url.startswith("http"):
        return ""
    port = pic_server_port()
    if not port:
        return url
    return "http://127.0.0.1:%d/p/%s.jpg" % (port, _pic_b64(url))


def warm_pics(urls):
    """后台把海报先解密缓存好,壳子拉的时候就是秒回"""
    todo = []
    with _pic_state["lock"]:
        for u in urls:
            if not u or not str(u).startswith("http") or u in _pic_state["mem"]:
                continue
            if "127.0.0.1" in u or "localhost" in u:
                continue
            if len(todo) < 24:
                todo.append(u)
    if not todo:
        return

    def run():
        try:
            with ThreadPoolExecutor(max_workers=PIC_WARM_WORKERS) as ex:
                list(ex.map(load_pic, todo))
        except Exception:
            pass

    try:
        threading.Thread(target=run, daemon=True).start()
    except Exception:
        pass


def _pick(v, *keys):
    for k in keys:
        val = v.get(k)
        if val not in (None, "", "0"):
            return val
    return ""


# ---------------------------------------------------------------- 主体
class Spider(_Base):

    def __init__(self, *args, **kwargs):
        try:
            super(Spider, self).__init__(*args, **kwargs)
        except Exception:
            pass
        self.base = DEFAULT_BASE
        self._cache = {}
        self._lock = threading.Lock()
        self._warming = set()

    # ---------------- 生命周期 ----------------
    def getName(self):
        return SITE_NAME

    def init(self, extend=""):
        ext = extend
        if isinstance(ext, dict):
            ext = ext.get("ext") or ext.get("base") or ext.get("url") or ""
        if isinstance(ext, (list, tuple)):
            ext = ext[0] if ext else ""
        ext = str(ext or "").strip().strip('"').strip("'")
        if ext.startswith("http"):
            self.base = ext.rstrip("/")
        else:
            self.base = DEFAULT_BASE
        try:
            pic_server_port()
        except Exception:
            pass

    def isVideoFormat(self, url):
        u = str(url or "")
        if u.startswith(("pics://", "novel://", "text://", "txt://")):
            return False
        return ".m3u8" in u or u.endswith(".mp4")

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._cache.clear()

    # ---------------- 缓存 ----------------
    def _cget(self, key):
        it = self._cache.get(key)
        if it and (time.time() - it[0]) <= CACHE_TTL:
            return it[1]
        return None

    def _cset(self, key, val):
        with self._lock:
            self._cache[key] = (time.time(), val)
            if len(self._cache) > 2000:
                for k in list(self._cache.keys())[:1000]:
                    self._cache.pop(k, None)

    # ---------------- 基础请求 ----------------
    def _get(self, url, referer=None):
        return _http(url, self.base, referer)

    def _json(self, url, referer=None):
        return json.loads(_unwrap(self._get(url, referer)))

    def _resolve_tid(self, tid, extend=None):
        tag = str((extend or {}).get("videoTag") or "").strip()
        if tag and tag not in CAT_MAP:
            return tag
        key = tag if tag in CAT_MAP else str(tid or "").strip()
        return CAT_MAP.get(key, key)

    def _mid_of(self, tid):
        t = str(tid or "")
        if t in CAT_MAP:
            t = CAT_MAP[t]
        if t in NOVEL_TIDS or t in IMAGE_TIDS:
            return 2
        return 1

    def _kind_of(self, tid, item=None):
        t = str(tid or "")
        if item:
            t = str(item.get("type_id") or t)
            pid = str(item.get("type_id_1") or "")
            if pid in NOVEL_TIDS or t in NOVEL_TIDS:
                return "novel"
            if pid in IMAGE_TIDS or t in IMAGE_TIDS:
                return "image"
            link = str(item.get("detail_link") or "")
            if "/art/" in link:
                return "image" if (pid in IMAGE_TIDS or t in IMAGE_TIDS) else "novel"
        if t in CAT_MAP:
            t = CAT_MAP[t]
        if t in NOVEL_TIDS:
            return "novel"
        if t in IMAGE_TIDS:
            return "image"
        return "video"

    def _page_result(self, vod_list, page, has_next):
        pagecount = page + 1 if has_next else page
        return {
            "list": vod_list,
            "page": page,
            "pagecount": pagecount,
            "limit": len(vod_list),
            "total": pagecount * max(len(vod_list), 1),
        }

    # ---------------- 列表 ----------------
    def _list_page(self, tid, page, mid=None):
        mid = 1 if mid is None else mid
        ck = "lp:%s:%s:%s" % (mid, tid, page)
        c = self._cget(ck)
        if c:
            return c
        try:
            j = self._json("%s/index.php/ajax/data?mid=%s&tid=%s&page=%s"
                           % (self.base, mid, tid, page))
        except Exception:
            j = {"list": [], "pagecount": 1, "total": 0}
        self._cset(ck, j)
        return j

    # ---------------- 搜索 ----------------
    def _search_page(self, wd, page):
        ck = "sb:%s:%s" % (wd, page)
        c = self._cget(ck)
        if c is not None:
            return c
        q = urllib.parse.quote(wd)
        if int(page) <= 1:
            url = "%s/index.php/vod/search.html?wd=%s" % (self.base, q)
        else:
            url = "%s/index.php/vod/search/page/%d/wd/%s.html" % (self.base, int(page), q)
        briefs, seen = [], set()
        html = ""
        try:
            html = _unwrap(self._get(url))
        except Exception:
            html = ""
        for part in re.split(r'(?=/index\.php/vod/detail/id/\d+\.html")', html):
            if not part.startswith("/index.php/vod/detail/id/"):
                continue
            head = part[:2000]
            m = re.match(r'/index.php/vod/detail/id/(\d+)\.html"', head)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            t = re.search(r'title="([^"]{1,140})"', head)
            img = re.search(
                r'<img[^>]+(?:data-src|data-original|src)="(https?://[^"]{10,200})"', head)
            briefs.append({
                "vod_id": vid,
                "vod_name": (t.group(1).strip() if t else vid),
                "vod_pic": (img.group(1) if img else ""),
                "_kind": "video",
            })
        if not briefs and html:
            try:
                j = json.loads(html)
                for it in j.get("list", []):
                    briefs.append({"vod_id": str(it.get("vod_id")),
                                   "vod_name": it.get("vod_name") or "",
                                   "vod_pic": it.get("vod_pic") or "",
                                   "_kind": "video"})
            except Exception:
                pass
        pages = [int(x) for x in re.findall(r"/vod/search/page/(\d+)/", html or "")]
        max_page = max(pages) if pages else int(page)
        if len(briefs) >= 12 and max_page <= int(page):
            max_page = int(page) + 1
        res = (briefs, max_page)
        self._cset(ck, res)
        return res

    # ---------------- 播放页 ----------------
    def _play(self, vid, sid=1, nid=1):
        """返回 (vod_data, m3u8, 该片所有 sid)"""
        ck = "pp:%s:%s:%s" % (vid, sid, nid)
        c = self._cget(ck)
        if c is not None:
            return c
        url = "%s/index.php/vod/play/id/%s/sid/%s/nid/%s.html" % (self.base, vid, sid, nid)
        ref = "%s/index.php/vod/detail/id/%s.html" % (self.base, vid)
        data, m3u8, sids = {}, "", []
        try:
            htm = _unwrap(self._get(url, referer=ref))
            i = htm.find("player_aaaa")
            if i >= 0:
                b = htm.find("{", i)
                if b >= 0:
                    obj, _ = json.JSONDecoder().raw_decode(htm[b:])
                    data = dict(obj.get("vod_data") or {})
                    u = (obj.get("url") or "").strip()
                    if u.startswith("//"):
                        u = "https:" + u
                    m3u8 = u
            for s in re.findall(r'/index\.php/vod/play/id/%s/sid/(\d+)/nid/' % vid, htm):
                if s not in sids:
                    sids.append(s)
        except Exception:
            pass
        res = (data, m3u8, sids or [str(sid)])
        self._cset(ck, res)
        return res

    def _m3u8(self, vid, sid):
        return self._play(vid, sid, 1)[1]

    def _type_name(self, v):
        t = v.get("type") if isinstance(v.get("type"), dict) else {}
        return str(t.get("type_name") or v.get("type_name") or "")

    def _brief(self, v, kind="video"):
        if kind == "video":
            raw_id = str(v.get("vod_id") or "")
            vod_id = "video_%s" % raw_id if raw_id else ""
            name = v.get("vod_name") or ""
            pic = _pic_url(_pick(v, "vod_pic", "vod_pic_slide", "vod_pic_thumb"))
            remarks = v.get("vod_remarks") or (v.get("vod_pubdate") or "")
            content = v.get("vod_blurb") or v.get("vod_content") or ""
        else:
            raw_id = str(v.get("art_id") or v.get("vod_id") or "")
            vod_id = ("img_%s" if kind == "image" else "novel_%s") % raw_id
            name = v.get("art_name") or v.get("vod_name") or ""
            pic = _pic_url(_pick(v, "art_pic", "vod_pic", "art_pic_thumb"))
            remarks = v.get("art_remarks") or ""
            content = v.get("art_blurb") or ""
            if raw_id:
                self._cset("%s:%s" % (kind, raw_id), v)
        item = {
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remarks,
            "type_name": self._type_name(v),
            "vod_content": content,
            "vod_play_from": "",
            "vod_play_url": "",
        }
        if kind == "image":
            item["vod_tag"] = "image"
        elif kind == "novel":
            item["vod_tag"] = "text"
        return item

    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        return self.categoryContent("精选", "1", False, {})

    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = 1
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        real_tid = self._resolve_tid(tid, extend)
        mid = self._mid_of(real_tid)
        kind = self._kind_of(real_tid)
        merge, start = 2, (page - 1) * 2 + 1
        items, seen, site_page, site_count, pics, vids = [], set(), start, 1, [], []
        for i in range(merge):
            site_page = start + i
            j = self._list_page(real_tid, site_page, mid)
            try:
                site_count = int(j.get("pagecount") or site_count)
            except Exception:
                pass
            for v in j.get("list", []) or []:
                row_kind = self._kind_of(real_tid, v)
                raw_id = str(v.get("vod_id") or v.get("art_id") or "")
                if not raw_id or raw_id in seen:
                    continue
                seen.add(raw_id)
                items.append(self._brief(v, row_kind))
                if row_kind == "video":
                    vids.append(raw_id)
                pics.append(_pick(v, "vod_pic", "vod_pic_thumb", "art_pic"))
        if kind == "video":
            self._warm(vids)
        warm_pics(pics)
        has_next = (site_page < site_count) if site_count > 1 else len(items) >= 12
        return self._page_result(items, page, has_next)

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick=False, pg="1"):
        page = 1
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        merge, start = 2, (page - 1) * 2 + 1
        items, seen, site_page, max_page = [], set(), start, 1
        for i in range(merge):
            site_page = start + i
            briefs, sp_max = self._search_page(key, site_page)
            if sp_max > max_page:
                max_page = sp_max
            for b in briefs:
                vid = str(b.get("vod_id") or "")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                items.append(self._brief(b, b.get("_kind") or "video"))
        self._warm([str(it["vod_id"]).split("_", 1)[-1]
                    for it in items[:30] if str(it.get("vod_id", "")).startswith("video_")])
        has_next = site_page < max_page
        return self._page_result(items, page, has_next)

    def _split_id(self, raw):
        s = str(raw or "").split("$")[-1].strip()
        m = re.match(r"(video|img|novel)_(\d+)(?:_(\d+))?$", s)
        if m:
            kind = {"video": "video", "img": "image", "novel": "novel"}[m.group(1)]
            return kind, m.group(2), m.group(3) or "1"
        if s.isdigit():
            return "video", s, "1"
        return "video", s, "1"

    def _art_html(self, aid, page=1):
        url = "%s/index.php/art/detail/id/%s.html" % (self.base, aid)
        if int(page) > 1:
            url += "?page=%s" % page
        return _unwrap(self._get(url))

    def _detail_video(self, vid, data=None):
        data = dict(data or {})
        item = self._brief(data, "video") if data else {
            "vod_id": "video_%s" % vid,
            "vod_name": vid,
            "vod_pic": "",
            "vod_remarks": "",
            "vod_content": "",
        }
        item["vod_id"] = "video_%s" % vid
        item["vod_play_from"] = SITE_NAME
        item["vod_play_url"] = "正片$video_%s_1" % vid
        return {"list": [item]}

    def _detail_image(self, aid, rec=None):
        rec = rec or self._cget("image:%s" % aid) or {}
        item = self._brief(rec, "image") if rec else {
            "vod_id": "img_%s" % aid,
            "vod_name": aid,
            "vod_pic": "",
            "vod_remarks": "",
            "vod_content": "",
            "vod_tag": "image",
        }
        n = 1
        content = rec.get("art_content") or ""
        imgs = re.findall(r'<img[^>]+src="(https?://[^"]+)"', content)
        if imgs:
            n = len(imgs)
        else:
            html = self._art_html(aid, 1)
            m = re.search(r"(\d+)\s*/\s*(\d+)", html)
            if m:
                n = max(1, int(m.group(2)))
            title = re.search(r'<a href="javascript:;"[^>]*>([^<]+)</a>', html)
            if title:
                item["vod_name"] = title.group(1).strip() or item["vod_name"]
        parts = ["第%s章$img_%s_%s" % (i, aid, i) for i in range(1, n + 1)]
        item["vod_id"] = "img_%s" % aid
        item["vod_tag"] = "image"
        item["vod_play_from"] = "漫画"
        item["vod_play_url"] = "#".join(parts)
        return {"list": [item]}

    def _detail_novel(self, aid, rec=None):
        rec = rec or self._cget("novel:%s" % aid) or {}
        item = self._brief(rec, "novel") if rec else {
            "vod_id": "novel_%s" % aid,
            "vod_name": aid,
            "vod_pic": "",
            "vod_remarks": "",
            "vod_content": "",
            "vod_tag": "text",
        }
        item["vod_id"] = "novel_%s" % aid
        item["vod_tag"] = "text"
        item["vod_play_from"] = "小说"
        item["vod_play_url"] = "正文$novel_%s_1" % aid
        return {"list": [item]}

    def detailContent(self, array):
        raw = ""
        try:
            raw = str(array[0]).strip()
        except Exception:
            raw = str(array).strip()
        kind, rid, _nid = self._split_id(raw)
        if kind == "image":
            return self._detail_image(rid)
        if kind == "novel":
            return self._detail_novel(rid)
        if rid.startswith("http"):
            return {"list": [{"vod_id": rid, "vod_name": rid,
                              "vod_play_from": SITE_NAME,
                              "vod_play_url": "正片$%s" % rid}]}
        data, _, _ = self._play(rid, 1, 1)
        return self._detail_video(rid, data)

    def _play_video(self, payload):
        _kind, vid, sid = self._split_id(payload)
        url = self._m3u8(vid, sid)
        if url.startswith("//"):
            url = "https:" + url
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": json.dumps({
                "User-Agent": UA,
                "Referer": self.base + "/",
            }),
        }

    def _abs_https(self, u):
        u = str(u or "").strip()
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith("http://"):
            u = "https://" + u[7:]
        return u if u.startswith("https://") else ""

    def _play_image(self, payload):
        _kind, aid, page = self._split_id(payload)
        page = int(page) if str(page).isdigit() else 1
        rec = self._cget("image:%s" % aid) or {}
        urls = []
        content = rec.get("art_content") or ""
        for u in re.findall(r'<img[^>]+src="(https?://[^"]+)"', content):
            u = self._abs_https(u)
            if u:
                urls.append(u)
        if urls:
            idx = max(0, page - 1)
            if idx < len(urls):
                urls = [urls[idx]]
        if not urls:
            html = self._art_html(aid, page)
            m = re.search(r'<div class="content"[^>]*>\s*<img src="([^"]+)"', html)
            if m:
                u = self._abs_https(m.group(1))
                if u:
                    urls.append(u)
        return {"parse": 0, "url": "pics://" + "&&".join(urls), "header": ""}

    def _play_novel(self, payload):
        _kind, aid, _nid = self._split_id(payload)
        rec = self._cget("novel:%s" % aid) or {}
        title = rec.get("art_name") or aid
        text = rec.get("art_content") or rec.get("art_blurb") or ""
        if "<" in text:
            text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
            text = re.sub(r"<[^>]+>", "", text)
        if not text.strip():
            html = self._art_html(aid, 1)
            m = re.search(r'<div id="articleContent">(.*?)</div>', html, re.S)
            title_m = re.search(r'<a href="javascript:;"[^>]*>([^<]+)</a>', html)
            if title_m:
                title = title_m.group(1).strip() or title
            text = m.group(1) if m else ""
            text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
            text = re.sub(r"<[^>]+>", "", text)
        return {
            "parse": 0,
            "url": "novel://" + json.dumps({"title": title, "content": text.strip()},
                                           ensure_ascii=False),
            "header": "",
        }

    def playerContent(self, flag, id, vipFlags=None):
        s = str(id or "").strip()
        if "$" in s:
            s = s.split("$")[-1].strip()
        if s.startswith(("pics://", "novel://")):
            return {"parse": 0, "url": s, "header": ""}
        if s.startswith("img_"):
            return self._play_image(s)
        if s.startswith("novel_"):
            return self._play_novel(s)
        if s.startswith("video_"):
            return self._play_video(s)
        if s.startswith("//"):
            s = "https:" + s
        if s.startswith("http"):
            return {
                "parse": 0,
                "playUrl": "",
                "url": s,
                "header": json.dumps({
                    "User-Agent": UA,
                    "Referer": self.base + "/",
                }),
            }
        return self._play_video("video_%s_1" % s)

    # ---------------- 后台预热 ----------------
    def _warm(self, vids):
        todo = []
        with self._lock:
            for v in vids:
                v = str(v or "")
                if not v or v in self._warming:
                    continue
                if self._cget("pp:%s:1:1" % v):
                    continue
                self._warming.add(v)
                todo.append(v)
        if not todo:
            return

        def run():
            try:
                with ThreadPoolExecutor(max_workers=4) as ex:
                    list(ex.map(lambda x: self._play(x, 1, 1), todo[:12]))
            except Exception:
                pass
            finally:
                with self._lock:
                    for v in todo:
                        self._warming.discard(v)

        try:
            threading.Thread(target=run, daemon=True).start()
        except Exception:
            pass

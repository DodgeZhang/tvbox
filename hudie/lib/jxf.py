#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================
# 剧下饭 TVBox Python 爬虫 - 修复版 v5 (分页+虎牙+跨页去重)
# 修复:
#   1) 分页不乱动: 参数用 pageNum; fallback 仅限第1页
#   2) 翻页不重复: Spider 实例级跨页去重 (按分类记忆已返回 vod_id)
#   3) 虎牙秒播:  走服务端 analysisUrl 官方解析
# =============================================================
import json
import time
import re
from base64 import b64encode
from urllib.request import Request, urlopen
from urllib.parse import quote_plus, unquote

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

BASE_URLS = [
    "http://manian.juxiafan.com",
    "http://195.225.24.128:6213",
    "http://jugaoqing.com",
    "http://jumianfei.com",
    "http://juyongjiu.com",
    "http://kuailezhuiju2.com",
    "http://zhuiju666.com",
    "http://194.147.100.155:7744",
]
AES_KEY = b"kZ6fT8oF6oM8eX6lF7eH2rJ3pW7gW0kC"
UA = "okhttp/4.12.0"

LIVE_TYPE_ID = 22023

# ======================= AES-256-ECB =======================

def _build_sbox():
    sbox = [0] * 256
    p = q = 1
    while True:
        p = p ^ ((p << 1) ^ (0x1B if p & 0x80 else 0)) & 0xFF
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q ^= 0x09 if (q & 0x80) else 0
        q &= 0xFF
        xformed = q ^ ((q << 1) | (q >> 7)) & 0xFF
        xformed = (xformed ^ ((q << 2) | (q >> 6))) & 0xFF
        xformed = (xformed ^ ((q << 3) | (q >> 5))) & 0xFF
        xformed = (xformed ^ ((q << 4) | (q >> 4))) & 0xFF
        sbox[p] = xformed ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox

_SBOX = _build_sbox()
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36, 0x6C, 0xD8, 0xAB, 0x4D]

def _xtime(a):
    return ((a << 1) ^ (0x1B if a & 0x80 else 0)) & 0xFF

_COL2 = [_xtime(i) for i in range(256)]
_COL3 = [_xtime(i) ^ i for i in range(256)]

def _expand_key(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            temp = [_SBOX[b] for b in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    return w, nr

def _encrypt_block(block, w, nr):
    def _rk(r):
        return [x for word in w[r * 4:(r * 4) + 4] for x in word]
    s = list(block)
    rk0 = _rk(0)
    for j in range(16):
        s[j] ^= rk0[j]
    for r in range(1, nr):
        s = [_SBOX[b] for b in s]
        s = [s[0], s[5], s[10], s[15],
             s[4], s[9], s[14], s[3],
             s[8], s[13], s[2], s[7],
             s[12], s[1], s[6], s[11]]
        t = [0] * 16
        for c in range(4):
            i = c * 4
            a0, a1, a2, a3 = s[i], s[i + 1], s[i + 2], s[i + 3]
            t[i] = _COL2[a0] ^ _COL3[a1] ^ a2 ^ a3
            t[i + 1] = a0 ^ _COL2[a1] ^ _COL3[a2] ^ a3
            t[i + 2] = a0 ^ a1 ^ _COL2[a2] ^ _COL3[a3]
            t[i + 3] = _COL3[a0] ^ a1 ^ a2 ^ _COL2[a3]
        s = t
        rk = _rk(r)
        s = [s[j] ^ rk[j] for j in range(16)]
    s = [_SBOX[b] for b in s]
    s = [s[0], s[5], s[10], s[15],
         s[4], s[9], s[14], s[3],
         s[8], s[13], s[2], s[7],
         s[12], s[1], s[6], s[11]]
    rk = _rk(nr)
    s = [s[j] ^ rk[j] for j in range(16)]
    return bytes(s)

def _aes256_ecb_encrypt(plain, key):
    w, nr = _expand_key(key)
    out = bytearray()
    for i in range(0, len(plain), 16):
        out += _encrypt_block(bytes(plain[i:i + 16]), w, nr)
    return bytes(out)

def _aes_encrypt(plaintext, key=AES_KEY):
    data = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
    pad = 16 - len(data) % 16
    data = data + bytes([pad]) * pad
    try:
        from Crypto.Cipher import AES
        return b64encode(AES.new(key, AES.MODE_ECB).encrypt(data)).decode()
    except Exception:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher as _C
            from cryptography.hazmat.primitives.ciphers.algorithms import AES as _AES
            from cryptography.hazmat.primitives.ciphers.modes import ECB as _ECB
            from cryptography.hazmat.backends import default_backend as _B
            enc = _C(_AES(key), _ECB(), backend=_B()).encryptor()
            return b64encode(enc.update(data) + enc.finalize()).decode()
        except Exception:
            return b64encode(_aes256_ecb_encrypt(data, key)).decode()

# ======================= HTTP / 签名 =======================

def _http(method, url, body=None, content_type=None, timeout=12):
    headers = {"User-Agent": UA}
    data = None
    if body is not None:
        data = body.encode("utf-8") if isinstance(body, str) else body
    if data:
        headers["Content-Length"] = str(len(data))
    if content_type:
        headers["Content-Type"] = content_type
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")

def _fix_host(host):
    if host is None or (isinstance(host, str) and host.strip() == ""):
        host = BASE_URLS[0]
    return str(host).rstrip("/")

def _post(host, path, body=None, content_type=None):
    urls = []
    h = _fix_host(host)
    if h not in urls:
        urls.append(h)
    for b in BASE_URLS:
        if b not in urls:
            urls.append(b)
    last = "{}"
    for u in urls:
        try:
            last = _http("POST", u + path, body, content_type)
            if '"code"' in last:
                return last
        except Exception:
            continue
    return last

def _get(url, timeout=12):
    try:
        return _http("GET", url, timeout=timeout)
    except Exception:
        return "{}"

def _post_form(host, path, params):
    ts = str(int(time.time()))
    params["timestamp"] = ts
    items = sorted(params.items())
    concat = "&".join(k + "=" + quote_plus(str(v)) for k, v in items)
    ds = _aes_encrypt(concat)
    form = "&".join(k + "=" + quote_plus(str(v)) for k, v in items)
    form += "&datasign=" + quote_plus(ds)
    return _post(host, path, form, "application/x-www-form-urlencoded")

def _post_json(host, path, params):
    params["timestamp"] = str(int(time.time()))
    items = sorted(params.items())
    concat = "&".join(k + "=" + str(v) for k, v in items)
    ds = _aes_encrypt(concat)
    obj = dict(items)
    obj["datasign"] = ds
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return _post(host, path, body, "application/json;charset=UTF-8")

# ======================= 核心业务 =======================

def _home(host):
    resp = _post(host, "/api/v1/video/classifies", None, None)
    try:
        data = json.loads(resp).get("data") or []
    except Exception:
        data = []
    cls = [{"type_id": str(c.get("id")), "type_name": c.get("name") or ""}
           for c in data if c.get("id") and c.get("name")]
    cls.sort(key=lambda x: int(x["type_id"]) if str(x["type_id"]).isdigit() else 10 ** 9)
    if str(LIVE_TYPE_ID) not in [str(c.get("type_id")) for c in cls]:
        cls.append({"type_id": str(LIVE_TYPE_ID), "type_name": "直播"})
    return {"class": cls, "filters": {}}

def _build_list(resp, page=1, id_desc=False, seen=None):
    """解析列表响应，按 vod_id 去重，保留首次出现顺序，同时过滤已返回的 id"""
    try:
        data = json.loads(resp).get("data") or {}
    except Exception:
        data = {}
    raw_lst = []
    for v in data.get("list") or []:
        if not v.get("id"):
            continue
        raw_lst.append({
            "vod_id": str(v.get("id")),
            "vod_name": v.get("name") or "",
            "vod_pic": v.get("videoPic") or "",
            "vod_remarks": v.get("remarks") or "",
        })
    # 去重：同一响应内保留首次出现顺序；跨页过滤已返回的 id
    local_seen = set()
    lst = []
    for item in raw_lst:
        vid = item["vod_id"]
        if vid not in local_seen:
            local_seen.add(vid)
            if seen is None or vid not in seen:
                lst.append(item)
    # 搜索时按 id 降序（最新在前）
    if id_desc and lst:
        try:
            lst.sort(key=lambda v: int(v.get("vod_id") or 0), reverse=True)
        except Exception:
            pass
    try:
        pg = int(page) or 1
    except (ValueError, TypeError):
        pg = 1
    try:
        pagecount = int(data.get("totalPage") or 1)
    except (ValueError, TypeError):
        pagecount = 1
    return {
        "page": pg,
        "pagecount": pagecount,
        "limit": data.get("limit") or 20,
        "total": data.get("totalCount") or 0,
        "list": lst,
    }

def _category(host, tid, pg, seen=None):
    page = 1
    try:
        page = int(pg or 1)
    except Exception:
        pass
    try:
        type_id = int(tid)
    except Exception:
        type_id = 0
    # 直播分类
    if type_id == LIVE_TYPE_ID:
        lst = []
        try:
            r = _get(_fix_host(host) + "/api/v1/video/liveVideo")
            data = (json.loads(r).get("data") or {})
            for v in data.get("list") or []:
                if not v.get("id"):
                    continue
                lst.append({
                    "vod_id": str(v.get("id")),
                    "vod_name": v.get("name") or "",
                    "vod_pic": v.get("videoPic") or "",
                    "vod_remarks": v.get("remarks") or ("直播" if v.get("typeId") else ""),
                })
        except Exception:
            pass
        return {"page": 1, "pagecount": 1, "limit": len(lst), "total": len(lst), "list": lst}
    # 主数据源：index，保持原始顺序，注意参数是 pageNum 不是 page
    resp = _post_json(host, "/api/v1/video/index", {"pageNum": page, "typeId": type_id})
    res = _build_list(resp, page, False, seen)
    # fallback 仅限第1页，翻页时绝不替换数据源，保证顺序稳定
    idx_list = res.get("list") or []
    if page == 1 and len(idx_list) < 10:
        try:
            resp2 = _post_json(host, "/api/v1/video/search", {"keyword": "", "typeId": type_id, "pageNum": page})
            res2 = _build_list(resp2, page, True, seen)
            search_list = res2.get("list") or []
            if len(search_list) > len(idx_list):
                res = res2
        except Exception:
            pass
    return res

def _search(host, key, pg="1"):
    key = (key or "").strip().strip('"').strip("'")
    if not key:
        return {"page": 1, "pagecount": 0, "limit": 20, "total": 0, "list": []}
    if "%" in key:
        try:
            dec = unquote(key)
            if dec and dec != key:
                key = dec.strip()
        except Exception:
            pass
    if key and "\\u" in key and all(ord(ch) < 128 for ch in key):
        try:
            dec = key.encode("ascii").decode("unicode_escape")
            if dec and dec != key:
                key = dec
        except Exception:
            pass
    try:
        page = int(pg or 1)
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1
    resp = _post_json(host, "/api/v1/video/search", {"keyword": key, "pageNum": page})
    return _build_list(resp, page, True)

def _reco(host):
    try:
        c = _category(host, "22016", "1")
        return (c or {}).get("list") or []
    except Exception:
        return []

def _fetch_detail(host, vid):
    resp = _post_form(host, "/api/v1/video/videoDetails", {"id": str(vid)})
    try:
        return json.loads(resp).get("data") or {}
    except Exception:
        return {}

def _detail(host, vid):
    data = _fetch_detail(host, vid)
    if not data:
        return {"list": []}
    sources = data.get("playerSource") or []
    from_names, from_urllists = [], []
    seen = {}
    for src in sources:
        eps = src.get("episodes") or []
        if not eps:
            continue
        name = src.get("sourceName") or "剧下饭"
        if name in seen:
            seen[name] += 1
            name = name + str(seen[name])
        else:
            seen[name] = 1
        segs = []
        for i, ep in enumerate(eps, 1):
            ep_name = (ep.get("episodeName") or "") or ("第" + str(i) + "集")
            ep_name = ep_name.replace("$", "_").replace("#", "_")
            segs.append(ep_name + "$" + str(vid) + "_" + str(i))
        from_names.append(name)
        from_urllists.append("#".join(segs))
    if not from_urllists:
        return {"list": []}
    play_from = "$$$".join(from_names)
    play_url = "$$$".join(from_urllists)
    return {"list": [{
        "vod_id": str(data.get("id") or vid),
        "vod_name": data.get("name") or "",
        "vod_pic": data.get("videoPic") or "",
        "vod_actor": data.get("actor") or "",
        "vod_director": data.get("director") or "",
        "vod_remarks": data.get("remarks") or "",
        "vod_content": data.get("content") or "",
        "vod_year": data.get("year") or "",
        "vod_area": data.get("area") or "",
        "vod_play_from": play_from,
        "vod_play_url": play_url,
    }]}

def _analysis_url(host, source_code, pc):
    """调用服务端 /api/v1/player/analysisUrl 把加密 playerCode 解析成真实播放地址。
    直播(sourceCode=zhibo/difang/huya)与点播加密码(co_xxx)均由此返回秒播地址。
    返回解析成功后的 URL 字符串，失败返回空串。"""
    if not source_code or not pc:
        return ""
    try:
        r = _post_form(host, "/api/v1/player/analysisUrl", {"from": source_code, "code": pc})
        u = (json.loads(r).get("data") or "")
        if str(u).startswith("http"):
            return str(u)
    except Exception:
        pass
    return ""

def _play(host, flag, pid):
    try:
        vid, ep = pid.rsplit("_", 1)
        ep = int(ep)
    except Exception:
        return {"parse": 0, "url": pid, "header": {"User-Agent": UA}}
    data = _fetch_detail(host, vid)
    sources = data.get("playerSource") or []
    flag_s = str(flag or "").strip()
    ordered = [src for src in sources if str(src.get("sourceName") or "").strip() == flag_s]
    for src in sources:
        if src not in ordered:
            ordered.append(src)
    for src in ordered:
        eps = src.get("episodes") or []
        if not eps or ep > len(eps):
            continue
        pc = (eps[ep - 1] or {}).get("playerCode") or ""
        parse_url = src.get("parseUrl") or ""
        source_code = src.get("sourceCode") or ""
        if parse_url and pc:
            j = _get(parse_url + pc)
            try:
                u = json.loads(j).get("url") or ""
            except Exception:
                u = ""
            if u:
                return {"parse": 0, "url": u, "header": {"User-Agent": UA}}
        # 直播/加密码：优先走服务端 analysisUrl 秒播解析
        if pc and not str(pc).startswith("http"):
            u = _analysis_url(host, source_code, pc)
            if u:
                headers = {"User-Agent": UA}
                if source_code == "huya":
                    headers["Referer"] = "https://www.huya.com/"
                return {"parse": 0, "url": u, "header": headers}
            return {"parse": 0, "url": pc, "header": {"User-Agent": UA}}
        elif pc:
            return {"parse": 0, "url": pc, "header": {"User-Agent": UA}}
    return {"parse": 0, "url": "", "header": {"User-Agent": UA}}

# ======================= 类式接口 =======================

class Spider(_BaseSpider):
    def __init__(self, *args, **kwargs):
        self._host = BASE_URLS[0]
        if kwargs.get("host"):
            self._host = _fix_host(kwargs["host"])
        if kwargs.get("extend") is not None:
            self.init(kwargs["extend"])
        # 按分类记忆已返回的 vod_id，解决服务端分页数据重叠导致的跨页重复
        self._cat_seen = {}

    def init(self, extend=None):
        if extend:
            s = str(extend).strip()
            if s.startswith("http"):
                self._host = _fix_host(s)
            elif s.startswith("base="):
                self._host = _fix_host(s[5:])

    def getName(self):
        return "剧下饭4K影视"

    def homeContent(self, filter=False):
        result = _home(self._host)
        result["list"] = []
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg="1", filter=None, extend=None):
        tid_s = str(tid)
        page = 1
        try:
            page = int(pg or 1)
        except Exception:
            pass
        # 回到第 1 页时重置该分类的记忆（切换分类或刷新时）
        if page == 1:
            self._cat_seen[tid_s] = set()
        seen = self._cat_seen.get(tid_s)
        res = _category(self._host, tid, pg, seen)
        # 把本页真正返回的新 id 记进集合，供下页过滤
        if seen is not None:
            for item in res.get("list", []):
                seen.add(item.get("vod_id"))
        return res

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        return _detail(self._host, ids[0])

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg="1"):
        try:
            return _search(self._host, key, pg)
        except Exception:
            return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

    def playerContent(self, flag, id, vipFlags=""):
        return _play(self._host, flag, id)

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def localProxy(self, param):
        return {"list": [], "parse": 0, "url": ""}

    def liveContent(self, url):
        return {"list": []}

# ======================= 函数式接口 =======================

_HOST = BASE_URLS[0]

def init(extend=None):
    global _HOST
    if extend:
        s = str(extend).strip()
        if s.startswith("http"):
            _HOST = _fix_host(s)
        elif s.startswith("base="):
            _HOST = _fix_host(s[5:])

def homeContent(filter=False):
    try:
        r = _home(_HOST)
        r["list"] = []
    except Exception:
        r = {"class": [], "filters": {}, "list": []}
    return json.dumps(r, ensure_ascii=False)

def homeVideoContent():
    return json.dumps({"list": []}, ensure_ascii=False)

def categoryContent(tid, pg="1", filter=False, extend=None):
    return json.dumps(_category(_HOST, tid, pg), ensure_ascii=False)

def detailContent(ids):
    if not ids:
        return '{"list":[]}'
    return json.dumps(_detail(_HOST, ids[0]), ensure_ascii=False)

def searchContent(key, quick=False, pg="1"):
    return json.dumps(_search(_HOST, key, pg), ensure_ascii=False)

def playerContent(flag, id, vipFlags=None):
    return json.dumps(_play(_HOST, flag, id), ensure_ascii=False)

def manualVideoCheck():
    return False

def isVideoFormat(url):
    return False


# ======================= 本地自测 =======================

if __name__ == "__main__":
    def show(label, s, n=600):
        txt = json.dumps(s, ensure_ascii=False) if not isinstance(s, str) else s
        print("== " + label + " ==")
        print(txt if len(txt) <= n else txt[:n])
        print()

    sp = Spider()
    show("homeContent", sp.homeContent(False))
    show("category 电视剧 pg1", sp.categoryContent("22016", "1"))
    show("category 电视剧 pg2", sp.categoryContent("22016", "2"))
    show("category 直播", sp.categoryContent("22023", "1"))
    show("search 轮播", sp.searchContent("轮播", True))
    show("detail 虎牙", sp.detailContent(["370855"]))
    show("player 虎牙 ep1", sp.playerContent("虎牙直播", "370855_1"))

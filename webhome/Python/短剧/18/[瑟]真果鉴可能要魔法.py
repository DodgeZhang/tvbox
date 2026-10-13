
import base64
import binascii
import gzip
import hashlib
import hmac
import json
import os
import random
import re
import struct
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

__version__ = "1.0.0"

PC_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MOB_UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7 "
             "Mobile/15E148 Safari/604.1")


# ---------------- 基础小工具 ----------------

def _s(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else ""
    return str(v).strip()


def _pick(d, *keys):
    if not isinstance(d, dict):
        return ""
    for k in keys:
        v = d.get(k)
        if v is None or v is False:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _pick_int(d, *keys):
    if not isinstance(d, dict):
        return 0
    for k in keys:
        v = d.get(k)
        try:
            n = int(float(str(v).strip()))
            if n:
                return n
        except Exception:
            continue
    return 0


def _abs(base, href):
    try:
        return urllib.parse.urljoin(base, _s(href))
    except Exception:
        return _s(href)


def _strip_tags(s):
    s = _s(s)
    s = re.sub(r"(?is)<script.*?</script>", " ", s)
    s = re.sub(r"(?is)<style.*?</style>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


_EP_PATTERNS = [
    re.compile(r"第\s*0*(\d+)\s*[集话期]"),
    re.compile(r"(?:更新至|共|全)\s*0*(\d+)\s*[集话期]"),
    re.compile(r"(?i)(?:episode|ep)\s*#?\s*0*(\d+)"),
]


def _ep_no(title, default=0):
    t = _s(title)
    for p in _EP_PATTERNS:
        m = p.search(t)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return default


def _q(s):
    return urllib.parse.quote(_s(s), safe="")


def _uq(s):
    return urllib.parse.unquote(_s(s))


def _md5(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.md5(s).hexdigest()


def _sha256(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.sha256(s).digest()


# ---------------- AES（纯 Python，支持 128/192/256，CBC/ECB，加解密） ----------------
# 小 JSON 解密走纯 Python 足够快；pycryptodome / javax.crypto 存在时自动用快的。

def _aes_build_sbox():
    sbox = [0] * 256
    isbox = [0] * 256
    # GF(2^8) 求逆
    def _xt(a):
        return ((a << 1) ^ 0x1B) & 0xFF if (a & 0x80) else (a << 1) & 0xFF
    inv = [0] * 256
    a = 1
    for _ in range(255):
        inv[a] = 1
        a = _xt(a)
    # 构造 exp/log 求完整逆元
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x = _xt(x) ^ x
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    full_inv = [0] * 256
    for i in range(1, 256):
        full_inv[i] = exp[255 - log[i]]
    for i in range(256):
        v = full_inv[i]
        s = v
        for r in (1, 2, 3, 4):
            s ^= ((v << r) | (v >> (8 - r))) & 0xFF
        s = (s ^ 0x63) & 0xFF
        sbox[i] = s
        isbox[s] = i
    return sbox, isbox


_AES_SBOX, _AES_ISBOX = _aes_build_sbox()
_AES_RK = {}


def _aes_xtime(a):
    return ((a << 1) ^ 0x1B) & 0xFF if (a & 0x80) else (a << 1) & 0xFF


def _aes_gmul(a, b):
    p = 0
    while b:
        if b & 1:
            p ^= a
        a = _aes_xtime(a)
        b >>= 1
    return p & 0xFF


def _aes_expand_key(key):
    key = bytes(key)
    ck = _AES_RK.get(key)
    if ck:
        return ck
    nk = len(key) // 4
    nr = {4: 10, 6: 12, 8: 14}[nk]
    rcon = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)
    w = [list(key[i:i + 4]) for i in range(0, len(key), 4)]
    for i in range(nk, 4 * (nr + 1)):
        t = w[i - 1][:]
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_AES_SBOX[b] for b in t]
            t[0] ^= rcon[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [_AES_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    rk = [b for word in w for b in word]
    _AES_RK[key] = (rk, nr)
    return rk, nr


def _aes_add_rk(s, rk, off):
    return [s[i] ^ rk[off + i] for i in range(16)]


def _aes_shift_rows(s, inv=False):
    o = [0] * 16
    for r in range(4):
        for c in range(4):
            o[r + 4 * c] = s[r + 4 * ((c - r) % 4 if inv else (c + r) % 4)]
    return o


def _aes_mix_col(s, inv=False):
    o = [0] * 16
    for c in range(4):
        a0, a1, a2, a3 = s[4 * c], s[4 * c + 1], s[4 * c + 2], s[4 * c + 3]
        if inv:
            o[4 * c] = (_aes_gmul(a0, 14) ^ _aes_gmul(a1, 11) ^
                        _aes_gmul(a2, 13) ^ _aes_gmul(a3, 9))
            o[4 * c + 1] = (_aes_gmul(a0, 9) ^ _aes_gmul(a1, 14) ^
                            _aes_gmul(a2, 11) ^ _aes_gmul(a3, 13))
            o[4 * c + 2] = (_aes_gmul(a0, 13) ^ _aes_gmul(a1, 9) ^
                            _aes_gmul(a2, 14) ^ _aes_gmul(a3, 11))
            o[4 * c + 3] = (_aes_gmul(a0, 11) ^ _aes_gmul(a1, 13) ^
                            _aes_gmul(a2, 9) ^ _aes_gmul(a3, 14))
        else:
            o[4 * c] = (_aes_gmul(a0, 2) ^ _aes_gmul(a1, 3) ^ a2 ^ a3)
            o[4 * c + 1] = (a0 ^ _aes_gmul(a1, 2) ^ _aes_gmul(a2, 3) ^ a3)
            o[4 * c + 2] = (a0 ^ a1 ^ _aes_gmul(a2, 2) ^ _aes_gmul(a3, 3))
            o[4 * c + 3] = (_aes_gmul(a0, 3) ^ a1 ^ a2 ^ _aes_gmul(a3, 2))
    return o


def _aes_enc_block_py(blk, rk, nr):
    s = _aes_add_rk(list(blk), rk, 0)
    for rnd in range(1, nr):
        s = [_AES_SBOX[b] for b in s]
        s = _aes_shift_rows(s)
        s = _aes_mix_col(s)
        s = _aes_add_rk(s, rk, 16 * rnd)
    s = [_AES_SBOX[b] for b in s]
    s = _aes_shift_rows(s)
    s = _aes_add_rk(s, rk, 16 * nr)
    return bytes(s)


def _aes_dec_block_py(blk, rk, nr):
    s = _aes_add_rk(list(blk), rk, 16 * nr)
    for rnd in range(nr - 1, 0, -1):
        s = _aes_shift_rows(s, inv=True)
        s = [_AES_ISBOX[b] for b in s]
        s = _aes_add_rk(s, rk, 16 * rnd)
        s = _aes_mix_col(s, inv=True)
    s = _aes_shift_rows(s, inv=True)
    s = [_AES_ISBOX[b] for b in s]
    s = _aes_add_rk(s, rk, 0)
    return bytes(s)


def _pkcs7_pad(data):
    n = 16 - (len(data) % 16)
    return bytes(data) + bytes([n] * n)


def _pkcs7_unpad(data):
    data = bytes(data)
    if not data or len(data) % 16:
        raise ValueError("bad pkcs7 length")
    n = data[-1]
    if n < 1 or n > 16 or data[-n:] != bytes([n] * n):
        raise ValueError("bad pkcs7 padding")
    return data[:-n]


def _aes_crypt_fast(data, key, iv, encrypt, mode_cbc):
    """pycryptodome 优先，其次 javax.crypto（真机），最后纯 Python。"""
    data, key = bytes(data), bytes(key)
    try:
        from Crypto.Cipher import AES
        if mode_cbc:
            c = AES.new(key, AES.MODE_CBC, bytes(iv))
        else:
            c = AES.new(key, AES.MODE_ECB)
        return c.encrypt(data) if encrypt else c.decrypt(data)
    except Exception:
        pass
    try:
        from java import jclass
        Cipher = jclass("javax.crypto.Cipher")
        SecretKeySpec = jclass("javax.crypto.spec.SecretKeySpec")
        IvParameterSpec = jclass("javax.crypto.spec.IvParameterSpec")
        trans = "AES/%s/NoPadding" % ("CBC" if mode_cbc else "ECB")
        c = Cipher.getInstance(trans)
        ks = SecretKeySpec(key, "AES")
        if mode_cbc:
            c.init(1 if encrypt else 2, ks, IvParameterSpec(bytes(iv)))
        else:
            c.init(1 if encrypt else 2, ks)
        return bytes(c.doFinal(data))
    except Exception:
        pass
    rk, nr = _aes_expand_key(key)
    enc = _aes_enc_block_py if encrypt else _aes_dec_block_py
    out = bytearray()
    prev = bytes(iv) if (mode_cbc and not encrypt) else None
    prev_enc = bytes(iv) if (mode_cbc and encrypt) else None
    for off in range(0, len(data), 16):
        blk = data[off:off + 16]
        if mode_cbc and encrypt:
            blk = bytes(blk[i] ^ prev_enc[i] for i in range(16))
            e = enc(blk, rk, nr)
            out.extend(e)
            prev_enc = e
        elif mode_cbc:
            d = enc(blk, rk, nr)
            out.extend(bytes(d[i] ^ prev[i] for i in range(16)))
            prev = blk
        else:
            out.extend(enc(blk, rk, nr))
    return bytes(out)


def _aes_cbc_encrypt(data, key, iv):
    return _aes_crypt_fast(_pkcs7_pad(data), key, iv, True, True)


def _aes_cbc_decrypt(data, key, iv):
    return _pkcs7_unpad(_aes_crypt_fast(data, key, iv, False, True))


def _aes_ecb_decrypt(data, key):
    return _pkcs7_unpad(_aes_crypt_fast(data, key, b"\x00" * 16, False, False))


def _aes_cbc_decrypt_nopad(data, key, iv):
    return _aes_crypt_fast(data, key, iv, False, True)


# ---------------- HTTP 层 ----------------
# urllib 主用；Python 栈被目标按 TLS 指纹丢弃时，回落 App 自带 OkHttp（真机）。

_JAVA_CLIENT = [None]


def _java_client():
    if _JAVA_CLIENT[0] is not None:
        return _JAVA_CLIENT[0] or None
    try:
        from java import jclass
        Builder = jclass("okhttp3.OkHttpClient$Builder")
        TimeUnit = jclass("java.util.concurrent.TimeUnit")
        b = Builder()
        b.followRedirects(True)
        b.followSslRedirects(True)
        b.connectTimeout(12, TimeUnit.SECONDS)
        b.readTimeout(30, TimeUnit.SECONDS)
        b.writeTimeout(12, TimeUnit.SECONDS)
        _JAVA_CLIENT[0] = b.build()
    except Exception:
        _JAVA_CLIENT[0] = False
    return _JAVA_CLIENT[0] or None


def _java_fetch(url, headers=None, data=None):
    """返回 (status, headers_dict, body)；失败返回 None。"""
    client = _java_client()
    if client is None:
        return None
    try:
        from java import jclass
        ReqBuilder = jclass("okhttp3.Request$Builder")
        rb = ReqBuilder()
        rb.url(str(url))
        ctype = "application/x-www-form-urlencoded"
        for k, v in (headers or {}).items():
            lk = str(k).lower()
            if lk == "content-type":
                ctype = str(v)
                continue
            if lk in ("content-length", "host", "cookie"):
                continue
            try:
                rb.header(str(k), str(v))
            except Exception:
                pass
        if data is not None:
            MediaType = jclass("okhttp3.MediaType")
            RequestBody = jclass("okhttp3.RequestBody")
            rb.post(RequestBody.create(MediaType.parse(ctype), bytes(data)))
        resp = client.newCall(rb.build()).execute()
        code = 0
        try:
            code = int(resp.code())
        except Exception:
            pass
        h = {}
        try:
            mm = resp.headers().toMultimap()
            for e in mm.entrySet():
                vals = []
                try:
                    for v in e.getValue():
                        vals.append(str(v))
                except Exception:
                    pass
                h[str(e.getKey()).lower()] = vals
        except Exception:
            pass
        out = b""
        try:
            bd = resp.body()
            if bd is not None:
                out = bytes(bd.bytes())
        except Exception:
            pass
        try:
            resp.close()
        except Exception:
            pass
        return code, h, out
    except Exception:
        return None


class _Resp(object):
    def __init__(self):
        self.status = 0
        self.headers = {}
        self.body = b""
        self.url = ""

    def text(self, encoding="utf-8"):
        return self.body.decode(encoding, "ignore")


def _parse_set_cookies(header_vals, jar):
    for hv in header_vals or []:
        part = _s(hv).split(";", 1)[0]
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            if k:
                jar[k] = v.strip()


class _Session(object):
    """带 Cookie 罐的会话；fetch 返回 _Resp。"""

    def __init__(self):
        self.cookies = {}
        self._lock = threading.Lock()

    def _cookie_header(self):
        with self._lock:
            items = ["%s=%s" % (k, v) for k, v in self.cookies.items()]
        return "; ".join(items)

    def fetch(self, url, method="GET", headers=None, data=None,
              timeout=12, max_body=8 << 20):
        headers = dict(headers or {})
        ck = self._cookie_header()
        if ck and "cookie" not in {k.lower(): 1 for k in headers}:
            headers["Cookie"] = ck
        if "user-agent" not in {k.lower(): 1 for k in headers}:
            headers["User-Agent"] = PC_UA
        resp = _Resp()
        resp.url = url
        # 1) urllib
        try:
            req = urllib.request.Request(url, data=data, headers=headers,
                                         method=method.upper())
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp.status = r.status
                raw_h = {}
                try:
                    for k, v in r.headers.items():
                        raw_h.setdefault(k.lower(), []).append(v)
                except Exception:
                    pass
                resp.headers = raw_h
                body = r.read(max_body + 1)
                if len(body) > max_body:
                    raise ValueError("body too large")
                resp.body = body
                try:
                    resp.url = r.geturl()
                except Exception:
                    pass
        except Exception:
            # 2) 真机 OkHttp 回退
            jr = _java_fetch(url, headers=headers, data=data)
            if not jr:
                raise
            resp.status, resp.headers, resp.body = jr
            if len(resp.body) > max_body:
                raise ValueError("body too large")
        _parse_set_cookies(resp.headers.get("set-cookie"), self.cookies)
        # 部分站点不看 Accept-Encoding 直接发 gzip/deflate，中央解压
        try:
            enc = [_s(x).lower() for x in resp.headers.get(
                "content-encoding", [])]
            if resp.body[:2] == b"\x1f\x8b" or any(
                    "gzip" in x for x in enc):
                resp.body = gzip.decompress(bytes(resp.body))
            elif resp.body[:2] == b"\x78\x9c" or any(
                    "deflate" in x for x in enc):
                import zlib
                resp.body = zlib.decompress(bytes(resp.body))
        except Exception:
            pass
        return resp

    def get_text(self, url, headers=None, timeout=12):
        return self.fetch(url, headers=headers, timeout=timeout).text()

    def get_json(self, url, headers=None, timeout=12):
        return json.loads(self.fetch(url, headers=headers,
                                     timeout=timeout).text())

    def post_json(self, url, obj, headers=None, timeout=12):
        h = dict(headers or {})
        h["Content-Type"] = "application/json; charset=utf-8"
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        return json.loads(self.fetch(url, method="POST", headers=h, data=data,
                                     timeout=timeout).text())

    def post_form(self, url, fields, headers=None, timeout=12):
        h = dict(headers or {})
        h["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(fields).encode("utf-8")
        return self.fetch(url, method="POST", headers=h, data=data,
                          timeout=timeout).text()


# ---------------- 站源框架 ----------------

class _SrcErr(Exception):
    """站源级可预期错误（接口变化/失效/加密等），Spider 会隔离。"""
    pass


def _tid(src, cat):
    return "%s::c::%s" % (src, _q(cat))


def _did(src, sid):
    return "%s::d::%s" % (src, _q(sid))


def _pid(src, sid, ep):
    return "%s::p::%s::%s" % (src, _q(sid), _q(ep))


def _split_tid(tid):
    head, _, cat = _s(tid).partition("::c::")
    return head, _uq(cat)


def _split_did(did):
    head, _, sid = _s(did).partition("::d::")
    return head, _uq(sid)


def _split_pid(pid):
    s = _s(pid)
    head, _, rest = s.partition("::p::")
    sid, _, ep = rest.partition("::")
    return head, _uq(sid), _uq(ep)


def _vod_item(src_id, sid, title, pic="", remark="", content=""):
    return {
        "vod_id": _did(src_id, sid),
        "vod_name": _s(title),
        "vod_pic": _s(pic),
        "vod_remarks": _s(remark),
        "vod_content": _s(content),
    }


def _vod_detail(src, sid, title, pic="", remark="", content="",
                year="", area="", actor="", chapters=()):
    """chapters: [(epkey, eptitle)]"""
    play_url = "#".join(
        "%s$%s" % (_s(t) or ("第%d集" % (i + 1)), _pid(src.id, sid, k))
        for i, (k, t) in enumerate(chapters))
    return {
        "vod_id": _did(src.id, sid),
        "vod_name": _s(title),
        "vod_pic": _s(pic),
        "vod_remarks": _s(remark),
        "vod_content": _s(content),
        "vod_year": _s(year),
        "vod_area": _s(area),
        "vod_actor": _s(actor),
        "vod_play_from": src.name,
        "vod_play_url": play_url,
    }


class _Src(object):
    id = ""
    name = ""
    cats = [("", "推荐")]  # [(catid, catname)] 静态分类

    def __init__(self):
        self.sess = _Session()

    # -- 以下按需覆盖 --
    def home(self, pg):
        """返回 (items, has_more)。"""
        return self.cat("", pg)

    def cat(self, catid, pg):
        raise _SrcErr("本站源暂无目录")

    def detail(self, sid):
        raise _SrcErr("本站源暂无详情")

    def play(self, sid, ep):
        """返回 (media_url, headers_dict)。"""
        raise _SrcErr("本站源暂无播放")

    def search(self, key, pg):
        raise _SrcErr("本站源不支持搜索")


_SOURCES = []


def _register(cls):
    _SOURCES.append(cls())
    return cls


def _find_src(src_id):
    for s in _SOURCES:
        if s.id == src_id:
            return s
    return None


# ============================================================
# 红果（___3_shu0.py，hongguoduanju.com，base64 内嵌，无需外部文件）
# 本类做适配。排第一位。
# ============================================================
_hgmod = None
_HG_IMPORT_ERR = ""
try:
    import base64 as _b64m, types as _tmod
    _hg_raw = _b64m.b64decode(
        "IyAtKi0gY29kaW5nOiB1dGYtOCAtKi0KZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwppbXBvcnQgYmFzZTY0CmltcG9ydCBiaW5hc2NpaQppbXBvcnQgYmlzZWN0CmltcG9ydCBoYXNobGliCmltcG9ydCBqc29uCmltcG9ydCBvcwppbXBvcnQgbHptYQppbXBvcnQgcmFuZG9tCmltcG9ydCByZQppbXBvcnQgc3RydWN0CmltcG9ydCB0ZW1wZmlsZQppbXBvcnQgY29uY3VycmVudC5mdXR1cmVzCmltcG9ydCB0aHJlYWRpbmcKaW1wb3J0IHRpbWUKZnJvbSBjb2xsZWN0aW9ucy5hYmMgaW1wb3J0IE1hcHBpbmcKZnJvbSBodHRwLnNlcnZlciBpbXBvcnQgQmFzZUhUVFBSZXF1ZXN0SGFuZGxlciwgVGhyZWFkaW5nSFRUUFNlcnZlcgpmcm9tIGh0bWwucGFyc2VyIGltcG9ydCBIVE1MUGFyc2VyCmZyb20gdHlwaW5nIGltcG9ydCBBbnkKZnJvbSB1cmxsaWIucGFyc2UgaW1wb3J0IHBhcnNlX3FzLCBxdW90ZSwgdXJsZW5jb2RlLCB1cmxwYXJzZQppbXBvcnQgcmVxdWVzdHMKdHJ5OgogICAgZnJvbSBjcnlwdG9ncmFwaHkuaGF6bWF0LnByaW1pdGl2ZXMgaW1wb3J0IGhhc2hlcwogICAgZnJvbSBjcnlwdG9ncmFwaHkuaGF6bWF0LnByaW1pdGl2ZXMuY2lwaGVycyBpbXBvcnQgQ2lwaGVyLCBhbGdvcml0aG1zLCBtb2RlcwpleGNlcHQgSW1wb3J0RXJyb3I6CiAgICBoYXNoZXMgPSBOb25lCiAgICBDaXBoZXIgPSBhbGdvcml0aG1zID0gbW9kZXMgPSBOb25lCnRyeToKICAgIGZyb20gQ3J5cHRvLkNpcGhlciBpbXBvcnQgQUVTIGFzIENyeXB0b0FFUwpleGNlcHQgSW1wb3J0RXJyb3I6CiAgICBDcnlwdG9BRVMgPSBOb25lCnRyeToKICAgIGZyb20gYmFzZS5zcGlkZXIgaW1wb3J0IFNwaWRlciBhcyBfQmFzZVNwaWRlcgpleGNlcHQgRXhjZXB0aW9uOgogICAgdHJ5OgogICAgICAgIGltcG9ydCBzeXMgYXMgX3N5cwogICAgICAgIF9zeXMucGF0aC5hcHBlbmQoIi4uIikKICAgICAgICBmcm9tIGJhc2Uuc3BpZGVyIGltcG9ydCBTcGlkZXIgYXMgX0Jhc2VTcGlkZXIKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgY2xhc3MgX0Jhc2VTcGlkZXI6CiAgICAgICAgICAgIHBhc3MKCiMgRm9uZ01pL1RWQm94IOeahCBDaGFxdW9weSDnjq/looPmnKrlv4XluKYgY3J5cHRvZ3JhcGh577yM5aSa5pWw5aOz5Y+q5bimIHB5Y3J5cHRvZG9tZeOAggojIOe7n+S4gOWFpeWPo++8jOmBv+WFjeiwg+eUqOeCueebtOaOpeS+nei1luafkOS4gOS4quW6k+OAggppZiBDaXBoZXIgaXMgbm90IE5vbmU6CiAgICBBRVNfQkFDS0VORCA9ICJjcnlwdG9ncmFwaHkiCmVsaWYgQ3J5cHRvQUVTIGlzIG5vdCBOb25lOgogICAgQUVTX0JBQ0tFTkQgPSAicHljcnlwdG9kb21lIgplbHNlOgogICAgQUVTX0JBQ0tFTkQgPSAibm9uZSIKCmNsYXNzIF9QdXJlQUVTMTI4OgogICAgIiIi57qvIFB5dGhvbiBBRVMtMTI477yM5L6b5pegIHB5Y3J5cHRvZG9tZS9jcnlwdG9ncmFwaHkg55qE5aOz5L2/55So44CCIiIiCgogICAgX1MgPSAoCiAgICAgICAgOTksMTI0LDExOSwxMjMsMjQyLDEwNywxMTEsMTk3LDQ4LDEsMTAzLDQzLDI1NCwyMTUsMTcxLDExOCwyMDIsMTMwLDIwMSwxMjUsMjUwLDg5LDcxLDI0MCwKICAgICAgICAxNzMsMjEyLDE2MiwxNzUsMTU2LDE2NCwxMTQsMTkyLDE4MywyNTMsMTQ3LDM4LDU0LDYzLDI0NywyMDQsNTIsMTY1LDIyOSwyNDEsMTEzLDIxNiw0OSwyMSwKICAgICAgICA0LDE5OSwzNSwxOTUsMjQsMTUwLDUsMTU0LDcsMTgsMTI4LDIyNiwyMzUsMzksMTc4LDExNyw5LDEzMSw0NCwyNiwyNywxMTAsOTAsMTYwLDgyLDU5LDIxNCwKICAgICAgICAxNzksNDEsMjI3LDQ3LDEzMiw4MywyMDksMCwyMzcsMzIsMjUyLDE3Nyw5MSwxMDYsMjAzLDE5MCw1Nyw3NCw3Niw4OCwyMDcsMjA4LDIzOSwxNzAsMjUxLDY3LAogICAgICAgIDc3LDUxLDEzMyw2OSwyNDksMiwxMjcsODAsNjAsMTU5LDE2OCw4MSwxNjMsNjQsMTQzLDE0NiwxNTcsNTYsMjQ1LDE4OCwxODIsMjE4LDMzLDE2LDI1NSwyNDMsCiAgICAgICAgMjEwLDIwNSwxMiwxOSwyMzYsOTUsMTUxLDY4LDIzLDE5NiwxNjcsMTI2LDYxLDEwMCw5MywyNSwxMTUsOTYsMTI5LDc5LDIyMCwzNCw0MiwxNDQsMTM2LDcwLAogICAgICAgIDIzOCwxODQsMjAsMjIyLDk0LDExLDIxOSwyMjQsNTAsNTgsMTAsNzMsNiwzNiw5MiwxOTQsMjExLDE3Miw5OCwxNDUsMTQ5LDIyOCwxMjEsMjMxLDIwMCw1NSwKICAgICAgICAxMDksMTQxLDIxMyw3OCwxNjksMTA4LDg2LDI0NCwyMzQsMTAxLDEyMiwxNzQsOCwxODYsMTIwLDM3LDQ2LDI4LDE2NiwxODAsMTk4LDIzMiwyMjEsMTE2LDMxLAogICAgICAgIDc1LDE4OSwxMzksMTM4LDExMiw2MiwxODEsMTAyLDcyLDMsMjQ2LDE0LDk3LDUzLDg3LDE4NSwxMzQsMTkzLDI5LDE1OCwyMjUsMjQ4LDE1MiwxNywxMDUsCiAgICAgICAgMjE3LDE0MiwxNDgsMTU1LDMwLDEzNSwyMzMsMjA2LDg1LDQwLDIyMywxNDAsMTYxLDEzNywxMywxOTEsMjMwLDY2LDEwNCw2NSwxNTMsNDUsMTUsMTc2LDg0LAogICAgICAgIDE4NywyMgogICAgKQogICAgX1JDT04gPSAoMHgwMCwweDAxLDB4MDIsMHgwNCwweDA4LDB4MTAsMHgyMCwweDQwLDB4ODAsMHgxQiwweDM2KQoKICAgIGRlZiBfX2luaXRfXyhzZWxmLCBrZXk6IGJ5dGVzKToKICAgICAgICBpZiBsZW4oa2V5KSAhPSAxNjoKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigiQUVTLTEyOCBvbmx5IikKICAgICAgICBzZWxmLl9yayA9IHNlbGYuX2V4cGFuZChrZXkpCgogICAgZGVmIF9leHBhbmQoc2VsZiwga2V5OiBieXRlcyk6CiAgICAgICAgcyA9IHNlbGYuX1MKICAgICAgICB3ID0gbGlzdChrZXkpCiAgICAgICAgZm9yIGkgaW4gcmFuZ2UoNCwgNDQpOgogICAgICAgICAgICB0MCwgdDEsIHQyLCB0MyA9IHdbLTRdLCB3Wy0zXSwgd1stMl0sIHdbLTFdCiAgICAgICAgICAgIGlmIGkgJSA0ID09IDA6CiAgICAgICAgICAgICAgICB0MCwgdDEsIHQyLCB0MyA9IHNbdDFdLCBzW3QyXSwgc1t0M10sIHNbdDBdCiAgICAgICAgICAgICAgICB0MCBePSBzZWxmLl9SQ09OW2kgLy8gNF0KICAgICAgICAgICAgYmFzZSA9IChpIC0gNCkgKiA0CiAgICAgICAgICAgIHcuZXh0ZW5kKCh3W2Jhc2VdIF4gdDAsIHdbYmFzZSArIDFdIF4gdDEsIHdbYmFzZSArIDJdIF4gdDIsIHdbYmFzZSArIDNdIF4gdDMpKQogICAgICAgIHJldHVybiB3CgogICAgQHN0YXRpY21ldGhvZAogICAgZGVmIF94dGltZShhOiBpbnQpIC0+IGludDoKICAgICAgICByZXR1cm4gKChhIDw8IDEpIF4gMHgxQikgJiAweEZGIGlmIChhICYgMHg4MCkgZWxzZSAoKGEgPDwgMSkgJiAweEZGKQoKICAgIGRlZiBlbmNyeXB0X2Jsb2NrKHNlbGYsIGJsb2NrOiBieXRlcykgLT4gYnl0ZXM6CiAgICAgICAgcyA9IGxpc3QoYmxvY2spCiAgICAgICAgcmsgPSBzZWxmLl9yawogICAgICAgIGZvciBpIGluIHJhbmdlKDE2KToKICAgICAgICAgICAgc1tpXSBePSBya1tpXQogICAgICAgIGZvciBybmQgaW4gcmFuZ2UoMSwgMTApOgogICAgICAgICAgICBzID0gW3NlbGYuX1NbYl0gZm9yIGIgaW4gc10KICAgICAgICAgICAgcyA9IFtzWzBdLCBzWzVdLCBzWzEwXSwgc1sxNV0sIHNbNF0sIHNbOV0sIHNbMTRdLCBzWzNdLAogICAgICAgICAgICAgICAgIHNbOF0sIHNbMTNdLCBzWzJdLCBzWzddLCBzWzEyXSwgc1sxXSwgc1s2XSwgc1sxMV1dCiAgICAgICAgICAgIGZvciBjIGluIHJhbmdlKDQpOgogICAgICAgICAgICAgICAgaSA9IGMgKiA0CiAgICAgICAgICAgICAgICBhLCBiLCBjMCwgZCA9IHNbaV0sIHNbaSArIDFdLCBzW2kgKyAyXSwgc1tpICsgM10KICAgICAgICAgICAgICAgIHQgPSBhIF4gYiBeIGMwIF4gZAogICAgICAgICAgICAgICAgdSA9IGEKICAgICAgICAgICAgICAgIGEgXj0gdCBeIHNlbGYuX3h0aW1lKGEgXiBiKQogICAgICAgICAgICAgICAgYiBePSB0IF4gc2VsZi5feHRpbWUoYiBeIGMwKQogICAgICAgICAgICAgICAgYzAgXj0gdCBeIHNlbGYuX3h0aW1lKGMwIF4gZCkKICAgICAgICAgICAgICAgIGQgXj0gdCBeIHNlbGYuX3h0aW1lKGQgXiB1KQogICAgICAgICAgICAgICAgc1tpXSwgc1tpICsgMV0sIHNbaSArIDJdLCBzW2kgKyAzXSA9IGEsIGIsIGMwLCBkCiAgICAgICAgICAgIG9mZiA9IHJuZCAqIDE2CiAgICAgICAgICAgIGZvciBpIGluIHJhbmdlKDE2KToKICAgICAgICAgICAgICAgIHNbaV0gXj0gcmtbb2ZmICsgaV0KICAgICAgICBzID0gW3NlbGYuX1NbYl0gZm9yIGIgaW4gc10KICAgICAgICBzID0gW3NbMF0sIHNbNV0sIHNbMTBdLCBzWzE1XSwgc1s0XSwgc1s5XSwgc1sxNF0sIHNbM10sCiAgICAgICAgICAgICBzWzhdLCBzWzEzXSwgc1syXSwgc1s3XSwgc1sxMl0sIHNbMV0sIHNbNl0sIHNbMTFdXQogICAgICAgIGZvciBpIGluIHJhbmdlKDE2KToKICAgICAgICAgICAgc1tpXSBePSBya1sxNjAgKyBpXQogICAgICAgIHJldHVybiBieXRlcyhzKQoKICAgIGRlZiBkZWNyeXB0X2Jsb2NrKHNlbGYsIGJsb2NrOiBieXRlcykgLT4gYnl0ZXM6CiAgICAgICAgZGVmIG11bChhLCBiKToKICAgICAgICAgICAgcCA9IDAKICAgICAgICAgICAgZm9yIF8gaW4gcmFuZ2UoOCk6CiAgICAgICAgICAgICAgICBpZiBiICYgMToKICAgICAgICAgICAgICAgICAgICBwIF49IGEKICAgICAgICAgICAgICAgIGhpID0gYSAmIDB4ODAKICAgICAgICAgICAgICAgIGEgPSAoYSA8PCAxKSAmIDB4RkYKICAgICAgICAgICAgICAgIGlmIGhpOgogICAgICAgICAgICAgICAgICAgIGEgXj0gMHgxQgogICAgICAgICAgICAgICAgYiA+Pj0gMQogICAgICAgICAgICByZXR1cm4gcAoKICAgICAgICBzID0gbGlzdChibG9jaykKICAgICAgICByayA9IHNlbGYuX3JrCiAgICAgICAgZm9yIGkgaW4gcmFuZ2UoMTYpOgogICAgICAgICAgICBzW2ldIF49IHJrWzE2MCArIGldCiAgICAgICAgZm9yIHJuZCBpbiByYW5nZSg5LCAwLCAtMSk6CiAgICAgICAgICAgIHMgPSBbc1swXSwgc1sxM10sIHNbMTBdLCBzWzddLCBzWzRdLCBzWzFdLCBzWzE0XSwgc1sxMV0sCiAgICAgICAgICAgICAgICAgc1s4XSwgc1s1XSwgc1syXSwgc1sxNV0sIHNbMTJdLCBzWzldLCBzWzZdLCBzWzNdXQogICAgICAgICAgICBzID0gW3NlbGYuX1NJW2JdIGZvciBiIGluIHNdCiAgICAgICAgICAgIG9mZiA9IHJuZCAqIDE2CiAgICAgICAgICAgIGZvciBpIGluIHJhbmdlKDE2KToKICAgICAgICAgICAgICAgIHNbaV0gXj0gcmtbb2ZmICsgaV0KICAgICAgICAgICAgZm9yIGMgaW4gcmFuZ2UoNCk6CiAgICAgICAgICAgICAgICBpID0gYyAqIDQKICAgICAgICAgICAgICAgIGEsIGIsIGMwLCBkID0gc1tpXSwgc1tpICsgMV0sIHNbaSArIDJdLCBzW2kgKyAzXQogICAgICAgICAgICAgICAgc1tpXSA9IG11bChhLCAweDBFKSBeIG11bChiLCAweDBCKSBeIG11bChjMCwgMHgwRCkgXiBtdWwoZCwgMHgwOSkKICAgICAgICAgICAgICAgIHNbaSArIDFdID0gbXVsKGEsIDB4MDkpIF4gbXVsKGIsIDB4MEUpIF4gbXVsKGMwLCAweDBCKSBeIG11bChkLCAweDBEKQogICAgICAgICAgICAgICAgc1tpICsgMl0gPSBtdWwoYSwgMHgwRCkgXiBtdWwoYiwgMHgwOSkgXiBtdWwoYzAsIDB4MEUpIF4gbXVsKGQsIDB4MEIpCiAgICAgICAgICAgICAgICBzW2kgKyAzXSA9IG11bChhLCAweDBCKSBeIG11bChiLCAweDBEKSBeIG11bChjMCwgMHgwOSkgXiBtdWwoZCwgMHgwRSkKICAgICAgICBzID0gW3NbMF0sIHNbMTNdLCBzWzEwXSwgc1s3XSwgc1s0XSwgc1sxXSwgc1sxNF0sIHNbMTFdLAogICAgICAgICAgICAgc1s4XSwgc1s1XSwgc1syXSwgc1sxNV0sIHNbMTJdLCBzWzldLCBzWzZdLCBzWzNdXQogICAgICAgIHMgPSBbc2VsZi5fU0lbYl0gZm9yIGIgaW4gc10KICAgICAgICBmb3IgaSBpbiByYW5nZSgxNik6CiAgICAgICAgICAgIHNbaV0gXj0gcmtbaV0KICAgICAgICByZXR1cm4gYnl0ZXMocykKCgoKX1B1cmVBRVMxMjguX1NJID0gdHVwbGUoe3Y6IGkgZm9yIGksIHYgaW4gZW51bWVyYXRlKF9QdXJlQUVTMTI4Ll9TKX1baV0gZm9yIGkgaW4gcmFuZ2UoMjU2KSkKCgpkZWYgX3B1cmVfY3RyX2RlY3J5cHQoa2V5OiBieXRlcywgY291bnRlcjogYnl0ZXMsIGRhdGE6IGJ5dGVzKSAtPiBieXRlczoKICAgIGlmIG5vdCBkYXRhOgogICAgICAgIHJldHVybiBiIiIKICAgIGlmIGxlbihjb3VudGVyKSA8IDE2OgogICAgICAgIGNvdW50ZXIgPSBjb3VudGVyLmxqdXN0KDE2LCBiIlwwIikKICAgIGVsc2U6CiAgICAgICAgY291bnRlciA9IGNvdW50ZXJbOjE2XQogICAgYWVzID0gX1B1cmVBRVMxMjgoa2V5KQogICAgY3RyID0gaW50LmZyb21fYnl0ZXMoY291bnRlciwgImJpZyIpCiAgICBvdXQgPSBieXRlYXJyYXkoKQogICAgZm9yIG9mZnNldCBpbiByYW5nZSgwLCBsZW4oZGF0YSksIDE2KToKICAgICAgICBrcyA9IGFlcy5lbmNyeXB0X2Jsb2NrKGN0ci50b19ieXRlcygxNiwgImJpZyIpKQogICAgICAgIGN0ciA9IChjdHIgKyAxKSAmICgoMSA8PCAxMjgpIC0gMSkKICAgICAgICBjaHVuayA9IGRhdGFbb2Zmc2V0Om9mZnNldCArIDE2XQogICAgICAgIG91dC5leHRlbmQoYyBeIGsgZm9yIGMsIGsgaW4gemlwKGNodW5rLCBrcykpCiAgICByZXR1cm4gYnl0ZXMob3V0KQoKCmRlZiBfcHVyZV9jYmNfZGVjcnlwdChrZXk6IGJ5dGVzLCBpdjogYnl0ZXMsIGRhdGE6IGJ5dGVzKSAtPiBieXRlczoKICAgIGlmIG5vdCBkYXRhOgogICAgICAgIHJldHVybiBiIiIKICAgIGlmIGxlbihkYXRhKSAlIDE2OgogICAgICAgIGRhdGEgPSBkYXRhWzogbGVuKGRhdGEpIC0gKGxlbihkYXRhKSAlIDE2KV0KICAgIGFlcyA9IF9QdXJlQUVTMTI4KGtleSkKICAgIHByZXYgPSAoaXZbOjE2XSBpZiBsZW4oaXYpID49IDE2IGVsc2UgaXYpLmxqdXN0KDE2LCBiIlwwIikKICAgIG91dCA9IGJ5dGVhcnJheSgpCiAgICBmb3IgaSBpbiByYW5nZSgwLCBsZW4oZGF0YSksIDE2KToKICAgICAgICBibG9jayA9IGRhdGFbaTppICsgMTZdCiAgICAgICAgZGVjID0gYWVzLmRlY3J5cHRfYmxvY2soYmxvY2spCiAgICAgICAgb3V0LmV4dGVuZChkIF4gcCBmb3IgZCwgcCBpbiB6aXAoZGVjLCBwcmV2KSkKICAgICAgICBwcmV2ID0gYmxvY2sKICAgIHJldHVybiBieXRlcyhvdXQpCgoKZGVmIF9hZXNfY3RyX2RlY3J5cHQoa2V5OiBieXRlcywgY291bnRlcjogYnl0ZXMsIGRhdGE6IGJ5dGVzKSAtPiBieXRlczoKICAgIGlmIG5vdCBkYXRhOgogICAgICAgIHJldHVybiBiIiIKICAgIGlmIEFFU19CQUNLRU5EID09ICJjcnlwdG9ncmFwaHkiOgogICAgICAgIGRlY3J5cHRvciA9IENpcGhlcihhbGdvcml0aG1zLkFFUyhrZXkpLCBtb2Rlcy5DVFIoY291bnRlcikpLmRlY3J5cHRvcigpCiAgICAgICAgcmV0dXJuIGRlY3J5cHRvci51cGRhdGUoZGF0YSkgKyBkZWNyeXB0b3IuZmluYWxpemUoKQogICAgaWYgQUVTX0JBQ0tFTkQgPT0gInB5Y3J5cHRvZG9tZSI6CiAgICAgICAgY2lwaGVyID0gQ3J5cHRvQUVTLm5ldygKICAgICAgICAgICAga2V5LCBDcnlwdG9BRVMuTU9ERV9DVFIsIG5vbmNlPWIiIiwgaW5pdGlhbF92YWx1ZT1jb3VudGVyCiAgICAgICAgKQogICAgICAgIHJldHVybiBjaXBoZXIuZGVjcnlwdChkYXRhKQogICAgcmV0dXJuIF9wdXJlX2N0cl9kZWNyeXB0KGtleSwgY291bnRlciwgZGF0YSkKCgpkZWYgX2Flc19jYmNfZGVjcnlwdChrZXk6IGJ5dGVzLCBpdjogYnl0ZXMsIGRhdGE6IGJ5dGVzKSAtPiBieXRlczoKICAgIGlmIG5vdCBkYXRhOgogICAgICAgIHJldHVybiBiIiIKICAgIGlmIEFFU19CQUNLRU5EID09ICJjcnlwdG9ncmFwaHkiOgogICAgICAgIGRlY3J5cHRvciA9IENpcGhlcihhbGdvcml0aG1zLkFFUyhrZXkpLCBtb2Rlcy5DQkMoaXYpKS5kZWNyeXB0b3IoKQogICAgICAgIHJldHVybiBkZWNyeXB0b3IudXBkYXRlKGRhdGEpICsgZGVjcnlwdG9yLmZpbmFsaXplKCkKICAgIGlmIEFFU19CQUNLRU5EID09ICJweWNyeXB0b2RvbWUiOgogICAgICAgIHJldHVybiBDcnlwdG9BRVMubmV3KGtleSwgQ3J5cHRvQUVTLk1PREVfQ0JDLCBpdikuZGVjcnlwdChkYXRhKQogICAgcmV0dXJuIF9wdXJlX2NiY19kZWNyeXB0KGtleSwgaXYsIGRhdGEpCgoKU0lURSA9ICJodHRwczovL2hvbmdndW9kdWFuanUuY29tIgpFUElTT0RFX1BSRUZJWCA9ICJoZy1lcGlzb2RlLXYxOiIKIyDnuqLmnpzmr4/pm4bop4bpopHmqKHlnovmjInmuIXmmbDluqbov5Tlm57lpJrmnaHni6znq4vnur/ot6/vvIgzNjAvNDgwLzU0MC83MjAvMTA4MO+8ie+8jAojIOavj+adoeW4piBtYWluX3VybCArIGJhY2t1cF91cmwg5Y+MIENETiDkuI7ni6znq4vliqDlr4bmnZDmlpnjgILov5nph4zmiormuIXmmbDluqbkvZzkuLoKIyBUVkJveCDlpJrnur/ot6/mmrTpnLLvvJvlhoXlsIHpn7Mv6KeG6L2o5Zyo6Kej5a+GIF9yZXdyaXRlX21vb3Yg5pe25aSp54S25YWo6YOo5L+d55WZ44CCCl9IR19RVUFMSVRZX0xJTkVTID0gKAogICAgKCIxMDgwIiwgIue6ouaenOi2hea4hSIpLAogICAgKCI3MjAiLCAgIue6ouaenOmrmOa4hSIpLAogICAgKCI1NDAiLCAgIue6ouaenOagh+WHhiIpLAogICAgKCI0ODAiLCAgIue6ouaenOa1geeVhSIpLAogICAgKCIzNjAiLCAgIue6ouaenOaegemAnyIpLAopCl9RVUFMSVRZX0xJTkVfTkFNRV9UT19RID0gewogICAgIui2hea4hSI6ICIxMDgwIiwgIumrmOa4hSI6ICI3MjAiLCAi5qCH5YeGIjogIjU0MCIsCiAgICAi5rWB55WFIjogIjQ4MCIsICLmnoHpgJ8iOiAiMzYwIiwgIjEwODAiOiAiMTA4MCIsICI3MjAiOiAiNzIwIiwKICAgICI1NDAiOiAiNTQwIiwgIjQ4MCI6ICI0ODAiLCAiMzYwIjogIjM2MCIsCn0KCgpkZWYgX3NwbGl0X2VwaXNvZGVfdG9rZW4odG9rZW46IHN0cikgLT4gdHVwbGVbc3RyLCBzdHJdOgogICAgIiIi5oqKICdoZy1lcGlzb2RlLXYxOjxxPjo8dmlkPicg6Kej5p6Q5Li6ICjmuIXmmbDluqYsIHZpZCnvvJvlhbzlrrnml6fmoLzlvI8gJ2hnLWVwaXNvZGUtdjE6PHZpZD4n44CCIiIiCiAgICBib2R5ID0gc3RyKHRva2VuIG9yICIiKQogICAgaWYgYm9keS5zdGFydHN3aXRoKEVQSVNPREVfUFJFRklYKToKICAgICAgICBib2R5ID0gYm9keVtsZW4oRVBJU09ERV9QUkVGSVgpOl0KICAgIGlmICI6IiBpbiBib2R5OgogICAgICAgIGhlYWQsIHRhaWwgPSBib2R5LnNwbGl0KCI6IiwgMSkKICAgICAgICBpZiBoZWFkLmlzZGlnaXQoKToKICAgICAgICAgICAgcmV0dXJuIGhlYWQsIHRhaWwKICAgIHJldHVybiAiMTA4MCIsIGJvZHkKCiMg5a6Y572R5pCc57SiIFNTUiDlm7rlrprnuqYgMTAg5p2h5LiU5Yeg5LmO5LiN6K6kIHBhZ2XvvJvnlKjlpJrlhbPplK7or43ova7mjaLlrp7njrDigJznv7vpobXigJ0KX0FJX01BTkpVX0tFWVdPUkRTID0gWwogICAgIkFJ5ryr5YmnIiwgIkFJ5Yqo55S7IiwgIkFJ55+t5YmnIiwgIkFJ5Yqo5ryrIiwgIua8q+WJp0FJIiwgIuS6jOasoeWFg0FJIiwgIkFJ5ryr55S7IiwgIuWKqOeUu+efreWJpyIsCl0KCgojIC0tLS0g5pys5py66Kej5a+G57yT5a2YICsg6Ieq5Yqo5riF55CGIC0tLS0KX0hHX0NBQ0hFX0RJUiA9IE5vbmUKX0hHX0NBQ0hFX01BWF9GSUxFUyA9IDggICAgICAgICAgIyDmnIDlpJrkv53nlZnpm4bmlbAKX0hHX0NBQ0hFX01BWF9CWVRFUyA9IDQwMCAqIDEwMjQgKiAxMDI0ICAjIOaAu+WuuemHj+e6piA0MDBNQgpfSEdfQ0FDSEVfTUFYX0FHRSA9IDYgKiAzNjAwICAgICAjIOi2hei/hyA2IOWwj+aXtuiHquWKqOWIoAoKCmRlZiBfaGdfY2FjaGVfZGlyKCkgLT4gc3RyOgogICAgZ2xvYmFsIF9IR19DQUNIRV9ESVIKICAgIGlmIF9IR19DQUNIRV9ESVIgYW5kIG9zLnBhdGguaXNkaXIoX0hHX0NBQ0hFX0RJUik6CiAgICAgICAgcmV0dXJuIF9IR19DQUNIRV9ESVIKICAgIGNhbmRpZGF0ZXMgPSBbXQogICAgIyDkvJjlhYggQXBwIOWPr+WGmee8k+WtmOebruW9le+8iE9L5b2x6KeGIC8gRm9uZ01pIOW4uOingei3r+W+hO+8iQogICAgZm9yIHJvb3QgaW4gKAogICAgICAgICIvZGF0YS91c2VyLzAvY29tLmZvbmdtaS5hbmRyb2lkLm9rdHYvY2FjaGUiLAogICAgICAgICIvZGF0YS9kYXRhL2NvbS5mb25nbWkuYW5kcm9pZC5va3R2L2NhY2hlIiwKICAgICAgICAiL2RhdGEvdXNlci8wL2NvbS5mb25nbWkuYW5kcm9pZC50di9jYWNoZSIsCiAgICAgICAgIi9kYXRhL2RhdGEvY29tLmZvbmdtaS5hbmRyb2lkLnR2L2NhY2hlIiwKICAgICAgICAiL3NkY2FyZC9BbmRyb2lkL2RhdGEvY29tLmZvbmdtaS5hbmRyb2lkLm9rdHYvY2FjaGUiLAogICAgICAgICIvc2RjYXJkL0FuZHJvaWQvZGF0YS9jb20uZm9uZ21pLmFuZHJvaWQudHYvY2FjaGUiLAogICAgICAgICIvc2RjYXJkL0Rvd25sb2FkIiwKICAgICk6CiAgICAgICAgY2FuZGlkYXRlcy5hcHBlbmQob3MucGF0aC5qb2luKHJvb3QsICJoZ19jZW5jX2NhY2hlIikpCiAgICB0cnk6CiAgICAgICAgY2FuZGlkYXRlcy5hcHBlbmQob3MucGF0aC5qb2luKHRlbXBmaWxlLmdldHRlbXBkaXIoKSwgImhnX2NlbmNfY2FjaGUiKSkKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcGFzcwogICAgdHJ5OgogICAgICAgIGNhbmRpZGF0ZXMuYXBwZW5kKG9zLnBhdGguam9pbihvcy5nZXRjd2QoKSwgImhnX2NlbmNfY2FjaGUiKSkKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcGFzcwogICAgZm9yIHBhdGggaW4gY2FuZGlkYXRlczoKICAgICAgICB0cnk6CiAgICAgICAgICAgIG9zLm1ha2VkaXJzKHBhdGgsIGV4aXN0X29rPVRydWUpCiAgICAgICAgICAgIHRlc3QgPSBvcy5wYXRoLmpvaW4ocGF0aCwgIi53IikKICAgICAgICAgICAgd2l0aCBvcGVuKHRlc3QsICJ3YiIpIGFzIGZoOgogICAgICAgICAgICAgICAgZmgud3JpdGUoYiIxIikKICAgICAgICAgICAgb3MucmVtb3ZlKHRlc3QpCiAgICAgICAgICAgIF9IR19DQUNIRV9ESVIgPSBwYXRoCiAgICAgICAgICAgIHJldHVybiBwYXRoCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgY29udGludWUKICAgIF9IR19DQUNIRV9ESVIgPSB0ZW1wZmlsZS5ta2R0ZW1wKHByZWZpeD0iaGdfY2VuY18iKQogICAgcmV0dXJuIF9IR19DQUNIRV9ESVIKCgpkZWYgX2hnX2NhY2hlX3BhdGgodmlkOiBzdHIsIHF1YWxpdHk6IHN0cikgLT4gc3RyOgogICAgc2FmZSA9IHJlLnN1YihyIlteMC05QS1aYS16Xy1dIiwgIiIsIHN0cih2aWQpKVs6NDBdCiAgICBxID0gcmUuc3ViKHIiW14wLTlBLVphLXpdIiwgIiIsIHN0cihxdWFsaXR5IG9yICJxIikpWzo4XQogICAgcmV0dXJuIG9zLnBhdGguam9pbihfaGdfY2FjaGVfZGlyKCksICIlc18lcy5tcDQiICUgKHNhZmUsIHEpKQoKCmRlZiBfaGdfY2FjaGVfbGlzdCgpIC0+IGxpc3Q6CiAgICByb290ID0gX2hnX2NhY2hlX2RpcigpCiAgICBmaWxlcyA9IFtdCiAgICB0cnk6CiAgICAgICAgbm93ID0gdGltZS50aW1lKCkKICAgICAgICBmb3IgbmFtZSBpbiBvcy5saXN0ZGlyKHJvb3QpOgogICAgICAgICAgICBpZiBub3QgbmFtZS5lbmRzd2l0aCgiLm1wNCIpOgogICAgICAgICAgICAgICAgY29udGludWUKICAgICAgICAgICAgZnAgPSBvcy5wYXRoLmpvaW4ocm9vdCwgbmFtZSkKICAgICAgICAgICAgaWYgbm90IG9zLnBhdGguaXNmaWxlKGZwKToKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIHN0ID0gb3Muc3RhdChmcCkKICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIGZpbGVzLmFwcGVuZCh7InBhdGgiOiBmcCwgInNpemUiOiBzdC5zdF9zaXplLCAibXRpbWUiOiBzdC5zdF9tdGltZSwgImFnZSI6IG5vdyAtIHN0LnN0X210aW1lfSkKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcmV0dXJuIFtdCiAgICBmaWxlcy5zb3J0KGtleT1sYW1iZGEgeDogeFsibXRpbWUiXSkgICMg5penIC0+IOaWsAogICAgcmV0dXJuIGZpbGVzCgoKZGVmIF9oZ19jYWNoZV9jbGVhbnVwKGZvcmNlOiBib29sID0gRmFsc2UpIC0+IE5vbmU6CiAgICAiIiLmjInml7bpl7QgKyDmlbDph48gKyDkvZPnp6/oh6rliqjmuIXnkIbmnKzmnLrnvJPlrZjjgIIiIiIKICAgIHRyeToKICAgICAgICBmaWxlcyA9IF9oZ19jYWNoZV9saXN0KCkKICAgICAgICBpZiBub3QgZmlsZXMgYW5kIG5vdCBmb3JjZToKICAgICAgICAgICAgcmV0dXJuCiAgICAgICAgIyAxKSDov4fmnJ/liKDpmaQKICAgICAgICByZW1haW4gPSBbXQogICAgICAgIGZvciBpdGVtIGluIGZpbGVzOgogICAgICAgICAgICBpZiBpdGVtWyJhZ2UiXSA+IF9IR19DQUNIRV9NQVhfQUdFIG9yIGl0ZW1bInNpemUiXSA8PSAwOgogICAgICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgICAgIG9zLnJlbW92ZShpdGVtWyJwYXRoIl0pCiAgICAgICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICAgICAgICAgIHBhc3MKICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgIHJlbWFpbi5hcHBlbmQoaXRlbSkKICAgICAgICAjIDIpIOi2hemHj+WIoOmZpOacgOaXpwogICAgICAgIHRvdGFsID0gc3VtKHhbInNpemUiXSBmb3IgeCBpbiByZW1haW4pCiAgICAgICAgd2hpbGUgcmVtYWluIGFuZCAobGVuKHJlbWFpbikgPiBfSEdfQ0FDSEVfTUFYX0ZJTEVTIG9yIHRvdGFsID4gX0hHX0NBQ0hFX01BWF9CWVRFUyk6CiAgICAgICAgICAgIG9sZCA9IHJlbWFpbi5wb3AoMCkKICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgb3MucmVtb3ZlKG9sZFsicGF0aCJdKQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICAgICAgcGFzcwogICAgICAgICAgICB0b3RhbCAtPSBvbGRbInNpemUiXQogICAgICAgICMgMykg5riF55CG5q6L55WZIHRtcAogICAgICAgIHJvb3QgPSBfaGdfY2FjaGVfZGlyKCkKICAgICAgICBmb3IgbmFtZSBpbiBvcy5saXN0ZGlyKHJvb3QpOgogICAgICAgICAgICBpZiBuYW1lLmVuZHN3aXRoKCIudG1wIikgb3IgbmFtZSA9PSAiLnciOgogICAgICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgICAgIG9zLnJlbW92ZShvcy5wYXRoLmpvaW4ocm9vdCwgbmFtZSkpCiAgICAgICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICAgICAgICAgIHBhc3MKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcGFzcwoKCmRlZiBfaGdfY2FjaGVfY2xlYXJfYWxsKCkgLT4gTm9uZToKICAgIHRyeToKICAgICAgICByb290ID0gX2hnX2NhY2hlX2RpcigpCiAgICAgICAgZm9yIG5hbWUgaW4gb3MubGlzdGRpcihyb290KToKICAgICAgICAgICAgZnAgPSBvcy5wYXRoLmpvaW4ocm9vdCwgbmFtZSkKICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgaWYgb3MucGF0aC5pc2ZpbGUoZnApOgogICAgICAgICAgICAgICAgICAgIG9zLnJlbW92ZShmcCkKICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgICAgIHBhc3MKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcGFzcwoKCmRlZiBfaGdfY2FjaGVfZ2V0KHZpZDogc3RyLCBxdWFsaXR5OiBzdHIpIC0+IGJ5dGVzIHwgTm9uZToKICAgIF9oZ19jYWNoZV9jbGVhbnVwKEZhbHNlKQogICAgcGF0aCA9IF9oZ19jYWNoZV9wYXRoKHZpZCwgcXVhbGl0eSkKICAgIHRyeToKICAgICAgICBpZiBvcy5wYXRoLmlzZmlsZShwYXRoKSBhbmQgb3MucGF0aC5nZXRzaXplKHBhdGgpID4gNjQ6CiAgICAgICAgICAgICMg6K+75pe25Yi35pawIG10aW1l77yM6YG/5YWN5Yia5pKt5Y+I6KKr5b2T6L+H5pyf5YigCiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIG9zLnV0aW1lKHBhdGgsIE5vbmUpCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgICAgICBwYXNzCiAgICAgICAgICAgIHdpdGggb3BlbihwYXRoLCAicmIiKSBhcyBmaDoKICAgICAgICAgICAgICAgIHJldHVybiBmaC5yZWFkKCkKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcmV0dXJuIE5vbmUKICAgIHJldHVybiBOb25lCgoKZGVmIF9oZ19jYWNoZV9wdXQodmlkOiBzdHIsIHF1YWxpdHk6IHN0ciwgZGF0YTogYnl0ZXMpIC0+IE5vbmU6CiAgICBpZiBub3QgZGF0YSBvciBsZW4oZGF0YSkgPCA2NDoKICAgICAgICByZXR1cm4KICAgIHBhdGggPSBfaGdfY2FjaGVfcGF0aCh2aWQsIHF1YWxpdHkpCiAgICB0cnk6CiAgICAgICAgX2hnX2NhY2hlX2NsZWFudXAoRmFsc2UpCiAgICAgICAgdG1wID0gcGF0aCArICIudG1wIgogICAgICAgIHdpdGggb3Blbih0bXAsICJ3YiIpIGFzIGZoOgogICAgICAgICAgICBmaC53cml0ZShkYXRhKQogICAgICAgIG9zLnJlcGxhY2UodG1wLCBwYXRoKQogICAgICAgIF9oZ19jYWNoZV9jbGVhbnVwKEZhbHNlKQogICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICB0cnk6CiAgICAgICAgICAgIGlmIG9zLnBhdGguZXhpc3RzKHBhdGggKyAiLnRtcCIpOgogICAgICAgICAgICAgICAgb3MucmVtb3ZlKHBhdGggKyAiLnRtcCIpCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgcGFzcwoKCmRlZiBfYWVzX2lzX2Zhc3QoKSAtPiBib29sOgogICAgcmV0dXJuIEFFU19CQUNLRU5EIGluICgiY3J5cHRvZ3JhcGh5IiwgInB5Y3J5cHRvZG9tZSIpCgoKZGVmIF9hZXNfaXNfZmFzdCgpIC0+IGJvb2w6CiAgICByZXR1cm4gQUVTX0JBQ0tFTkQgaW4gKCJjcnlwdG9ncmFwaHkiLCAicHljcnlwdG9kb21lIikKCgpkZWYgX2h0dHBfZ2V0X2J5dGVzKHVybDogc3RyLCBoZWFkZXJzOiBkaWN0IHwgTm9uZSA9IE5vbmUsIHRpbWVvdXQ6IGludCA9IDYwKSAtPiBieXRlczoKICAgIGggPSBkaWN0KGhlYWRlcnMgb3Ige30pCiAgICByID0gcmVxdWVzdHMuZ2V0KHVybCwgaGVhZGVycz1oLCB0aW1lb3V0PXRpbWVvdXQpCiAgICByLnJhaXNlX2Zvcl9zdGF0dXMoKQogICAgcmV0dXJuIHIuY29udGVudAoKCmRlZiBfcHJvYmVfY29udGVudF9sZW5ndGgodXJsOiBzdHIsIGhlYWRlcnM6IGRpY3QgfCBOb25lID0gTm9uZSwgdGltZW91dDogaW50ID0gMzApIC0+IGludDoKICAgIGggPSBkaWN0KGhlYWRlcnMgb3Ige30pCiAgICB0cnk6CiAgICAgICAgciA9IHJlcXVlc3RzLmhlYWQodXJsLCBoZWFkZXJzPWgsIHRpbWVvdXQ9dGltZW91dCwgYWxsb3dfcmVkaXJlY3RzPVRydWUpCiAgICAgICAgaWYgci5zdGF0dXNfY29kZSA8IDQwMDoKICAgICAgICAgICAgY2wgPSByLmhlYWRlcnMuZ2V0KCJDb250ZW50LUxlbmd0aCIpIG9yIHIuaGVhZGVycy5nZXQoImNvbnRlbnQtbGVuZ3RoIikKICAgICAgICAgICAgaWYgY2wgYW5kIHN0cihjbCkuaXNkaWdpdCgpOgogICAgICAgICAgICAgICAgcmV0dXJuIGludChjbCkKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcGFzcwogICAgdHJ5OgogICAgICAgIGhoID0gZGljdChoKQogICAgICAgIGhoWyJSYW5nZSJdID0gImJ5dGVzPTAtMCIKICAgICAgICByID0gcmVxdWVzdHMuZ2V0KHVybCwgaGVhZGVycz1oaCwgdGltZW91dD10aW1lb3V0KQogICAgICAgIGNyID0gci5oZWFkZXJzLmdldCgiQ29udGVudC1SYW5nZSIpIG9yIHIuaGVhZGVycy5nZXQoImNvbnRlbnQtcmFuZ2UiKSBvciAiIgogICAgICAgICMgYnl0ZXMgMC0wLzEyMzQ1CiAgICAgICAgaWYgIi8iIGluIGNyOgogICAgICAgICAgICB0b3RhbCA9IGNyLnNwbGl0KCIvIilbLTFdLnN0cmlwKCkKICAgICAgICAgICAgaWYgdG90YWwuaXNkaWdpdCgpOgogICAgICAgICAgICAgICAgcmV0dXJuIGludCh0b3RhbCkKICAgICAgICBjbCA9IHIuaGVhZGVycy5nZXQoIkNvbnRlbnQtTGVuZ3RoIikgb3IgIjAiCiAgICAgICAgaWYgc3RyKGNsKS5pc2RpZ2l0KCkgYW5kIGludChjbCkgPiAxOgogICAgICAgICAgICByZXR1cm4gaW50KGNsKQogICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICBwYXNzCiAgICByZXR1cm4gMAoKCmRlZiBfZG93bmxvYWRfcmFuZ2UodXJsOiBzdHIsIHN0YXJ0OiBpbnQsIGVuZDogaW50LCBoZWFkZXJzOiBkaWN0IHwgTm9uZSwgdGltZW91dDogaW50KSAtPiB0dXBsZVtpbnQsIGJ5dGVzXToKICAgIGggPSBkaWN0KGhlYWRlcnMgb3Ige30pCiAgICBoWyJSYW5nZSJdID0gImJ5dGVzPSVkLSVkIiAlIChzdGFydCwgZW5kKQogICAgbGFzdF9lcnIgPSBOb25lCiAgICBmb3IgYXR0ZW1wdCBpbiByYW5nZSgzKToKICAgICAgICB0cnk6CiAgICAgICAgICAgIHIgPSByZXF1ZXN0cy5nZXQodXJsLCBoZWFkZXJzPWgsIHRpbWVvdXQ9dGltZW91dCkKICAgICAgICAgICAgaWYgci5zdGF0dXNfY29kZSBub3QgaW4gKDIwMCwgMjA2KToKICAgICAgICAgICAgICAgIHJhaXNlIFJ1bnRpbWVFcnJvcigicmFuZ2UgaHR0cCAlcyIgJSByLnN0YXR1c19jb2RlKQogICAgICAgICAgICBkYXRhID0gci5jb250ZW50CiAgICAgICAgICAgIGlmIG5vdCBkYXRhOgogICAgICAgICAgICAgICAgcmFpc2UgUnVudGltZUVycm9yKCJlbXB0eSByYW5nZSBib2R5IikKICAgICAgICAgICAgcmV0dXJuIHN0YXJ0LCBkYXRhCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlcnI6CiAgICAgICAgICAgIGxhc3RfZXJyID0gZXJyCiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIHRpbWUuc2xlZXAoMC4yNSAqIChhdHRlbXB0ICsgMSkpCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgICAgICBwYXNzCiAgICByYWlzZSBSdW50aW1lRXJyb3IoInJhbmdlICVzLSVzIGZhaWxlZDogJXMiICUgKHN0YXJ0LCBlbmQsIGxhc3RfZXJyKSkKCgpkZWYgX211bHRpX2Rvd25sb2FkKHVybDogc3RyLCBoZWFkZXJzOiBkaWN0IHwgTm9uZSA9IE5vbmUsIHRpbWVvdXQ6IGludCA9IDkwLCB3b3JrZXJzOiBpbnQgPSA0KSAtPiBieXRlczoKICAgICIiIuWkmuWIhueJh+W5tuihjOS4i+i9ve+8jOWksei0peWImeWbnumAgOaVtOaWh+S7tuWNlee6v+eoi+OAgiIiIgogICAgaGVhZGVycyA9IGRpY3QoaGVhZGVycyBvciB7fSkKICAgIHRvdGFsID0gX3Byb2JlX2NvbnRlbnRfbGVuZ3RoKHVybCwgaGVhZGVycywgdGltZW91dD1taW4oMzAsIHRpbWVvdXQpKQogICAgIyDlpKrlsI/miJbmnKrnn6Xplb/luqbvvJrnm7TmjqXmlbTkuIsKICAgIGlmIHRvdGFsIDw9IDAgb3IgdG90YWwgPCAyICogMTAyNCAqIDEwMjQ6CiAgICAgICAgcmV0dXJuIF9odHRwX2dldF9ieXRlcyh1cmwsIGhlYWRlcnMsIHRpbWVvdXQ9dGltZW91dCkKCiAgICAjIOWIhueJh+Wkp+WwjyAxfjJNQu+8jOe6v+eoi+aVsOmZkOWItgogICAgd29ya2VycyA9IG1heCgyLCBtaW4oaW50KHdvcmtlcnMgb3IgNCksIDYpKQogICAgY2h1bmsgPSBtYXgoMSAqIDEwMjQgKiAxMDI0LCBtaW4oMiAqIDEwMjQgKiAxMDI0LCB0b3RhbCAvLyB3b3JrZXJzKSkKICAgIHJhbmdlcyA9IFtdCiAgICBzdGFydCA9IDAKICAgIHdoaWxlIHN0YXJ0IDwgdG90YWw6CiAgICAgICAgZW5kID0gbWluKHRvdGFsIC0gMSwgc3RhcnQgKyBjaHVuayAtIDEpCiAgICAgICAgcmFuZ2VzLmFwcGVuZCgoc3RhcnQsIGVuZCkpCiAgICAgICAgc3RhcnQgPSBlbmQgKyAxCgogICAgcGFydHM6IGRpY3RbaW50LCBieXRlc10gPSB7fQogICAgdHJ5OgogICAgICAgIHdpdGggY29uY3VycmVudC5mdXR1cmVzLlRocmVhZFBvb2xFeGVjdXRvcihtYXhfd29ya2Vycz13b3JrZXJzKSBhcyBwb29sOgogICAgICAgICAgICBmdXRzID0gWwogICAgICAgICAgICAgICAgcG9vbC5zdWJtaXQoX2Rvd25sb2FkX3JhbmdlLCB1cmwsIHMsIGUsIGhlYWRlcnMsIHRpbWVvdXQpCiAgICAgICAgICAgICAgICBmb3IgcywgZSBpbiByYW5nZXMKICAgICAgICAgICAgXQogICAgICAgICAgICBmb3IgZnV0IGluIGNvbmN1cnJlbnQuZnV0dXJlcy5hc19jb21wbGV0ZWQoZnV0cyk6CiAgICAgICAgICAgICAgICBzLCBkYXRhID0gZnV0LnJlc3VsdCgpCiAgICAgICAgICAgICAgICBwYXJ0c1tzXSA9IGRhdGEKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgIyDlubbooYzlpLHotKXlm57pgIAKICAgICAgICByZXR1cm4gX2h0dHBfZ2V0X2J5dGVzKHVybCwgaGVhZGVycywgdGltZW91dD10aW1lb3V0KQoKICAgIGJ1ZiA9IGJ5dGVhcnJheSgpCiAgICBmb3IgcywgZSBpbiByYW5nZXM6CiAgICAgICAgcGllY2UgPSBwYXJ0cy5nZXQocykKICAgICAgICBpZiBwaWVjZSBpcyBOb25lOgogICAgICAgICAgICByZXR1cm4gX2h0dHBfZ2V0X2J5dGVzKHVybCwgaGVhZGVycywgdGltZW91dD10aW1lb3V0KQogICAgICAgIGJ1Zi5leHRlbmQocGllY2UpCiAgICBpZiBsZW4oYnVmKSA8IHRvdGFsICogMC45NToKICAgICAgICAjIOaYjuaYvuS4jeWujOaVtAogICAgICAgIHJldHVybiBfaHR0cF9nZXRfYnl0ZXModXJsLCBoZWFkZXJzLCB0aW1lb3V0PXRpbWVvdXQpCiAgICByZXR1cm4gYnl0ZXMoYnVmKQoKCgpfTUFOSlVfS0VZV09SRFMgPSBbCiAgICAi5ryr5YmnIiwgIuWKqOa8q+efreWJpyIsICLkuozmrKHlhYMiLCAi5ryr55S755+t5YmnIiwgIuWbvea8q+efreWJpyIsICLml6XmvKsiLCAi5Yqo5oCB5ryrIiwgIuWKqOeUu+WJpyIsCl0KClZJREVPX1VSTCA9ICJodHRwczovL2FwaTUtbm9ybWFsLXNpbmZvbmxpbmViLmZxbm92ZWwuY29tL25vdmVsL3BsYXllci9tdWx0aV92aWRlb19tb2RlbC92MS8iClVBID0gIk1vemlsbGEvNS4wIChMaW51eDsgQW5kcm9pZCAxMikgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyNi4wIFNhZmFyaS81MzcuMzYiCkFQUF9VQSA9ICJjb20ucGhvZW5peC5yZWFkLzcxMzMyIChMaW51eDsgVTsgQW5kcm9pZCAxNjsgemhfQ047IDI1MDUzUlQ0N0M7IEJ1aWxkL0JQMkEuMjUwNjA1LjAzMS5BMzsgQ3JvbmV0L1RUTmV0VmVyc2lvbjowNDY1Nzc5NSAyMDI2LTAxLTIzIFF1aWNWZXJzaW9uOmM2N2U5ODM0IDIwMjUtMDktMDgpIgpNRURJQV9VQSA9ICJjb20ucGhvZW5peC5yZWFkLzcxMzMyIgoKCgoKX0hUTUxfRkVUQ0hfQVRURU1QVFMgPSAzCgpfSFRNTF9GRVRDSF9CQUNLT0ZGX1NFQ09ORFMgPSAxLjUKCl9SQU5HRV9GRVRDSF9BVFRFTVBUUyA9IDMKCl9SQU5HRV9GRVRDSF9CQUNLT0ZGX1NFQ09ORFMgPSAwLjgKCmNsYXNzIEhvbmdndW9QbHVnaW5FcnJvcihSdW50aW1lRXJyb3IpOgogICAgcGFzcwoKZGVmIF90ZXh0KHZhbHVlOiBBbnkpIC0+IHN0cjoKICAgIHJldHVybiBzdHIodmFsdWUgb3IgIiIpLnN0cmlwKCkKCmRlZiBfZmlyc3QoKnZhbHVlczogQW55KSAtPiBzdHI6CiAgICBmb3IgdmFsdWUgaW4gdmFsdWVzOgogICAgICAgIGlmIGlzaW5zdGFuY2UodmFsdWUsIChsaXN0LCB0dXBsZSkpOgogICAgICAgICAgICByZXN1bHQgPSBfZmlyc3QoKnZhbHVlKQogICAgICAgIGVsaWYgaXNpbnN0YW5jZSh2YWx1ZSwgTWFwcGluZyk6CiAgICAgICAgICAgIHJlc3VsdCA9IF9maXJzdCgKICAgICAgICAgICAgICAgIHZhbHVlLmdldCgidXJsIiksCiAgICAgICAgICAgICAgICB2YWx1ZS5nZXQoInVyaSIpLAogICAgICAgICAgICAgICAgdmFsdWUuZ2V0KCJzcmMiKSwKICAgICAgICAgICAgICAgIHZhbHVlLmdldCgiZG93bmxvYWRfdXJsIiksCiAgICAgICAgICAgICAgICB2YWx1ZS5nZXQoIm1haW5fdXJsIiksCiAgICAgICAgICAgICAgICB2YWx1ZS5nZXQoImJhY2t1cF91cmwiKSwKICAgICAgICAgICAgICAgIHZhbHVlLmdldCgiYmFja3VwX3VybF8xIiksCiAgICAgICAgICAgICAgICB2YWx1ZS5nZXQoInBsYXlfYWRkciIpLAogICAgICAgICAgICAgICAgdmFsdWUuZ2V0KCJ1cmxfbGlzdCIpLAogICAgICAgICAgICApCiAgICAgICAgZWxzZToKICAgICAgICAgICAgcmVzdWx0ID0gX3RleHQodmFsdWUpCiAgICAgICAgaWYgcmVzdWx0OgogICAgICAgICAgICByZXR1cm4gcmVzdWx0CiAgICByZXR1cm4gIiIKCmRlZiBfanNvbl9yZXNwb25zZShyZXNwb25zZTogcmVxdWVzdHMuUmVzcG9uc2UpIC0+IEFueToKICAgIHJlc3BvbnNlLnJhaXNlX2Zvcl9zdGF0dXMoKQogICAgdHJ5OgogICAgICAgIHJldHVybiByZXNwb25zZS5qc29uKCkKICAgIGV4Y2VwdCBWYWx1ZUVycm9yIGFzIGV4YzoKICAgICAgICByYWlzZSBIb25nZ3VvUGx1Z2luRXJyb3IoIuS4iua4uOWTjeW6lOS4jeaYryBKU09OIikgZnJvbSBleGMKCmRlZiBfZ2V0X2h0bWwodXJsOiBzdHIsICosIGF0dGVtcHRzOiBpbnQgPSBfSFRNTF9GRVRDSF9BVFRFTVBUUykgLT4gc3RyOgogICAgbGFzdF9lcnJvcjogRXhjZXB0aW9uIHwgTm9uZSA9IE5vbmUKICAgIGZvciBhdHRlbXB0IGluIHJhbmdlKG1heCgxLCBhdHRlbXB0cykpOgogICAgICAgIHRyeToKICAgICAgICAgICAgcmVzcG9uc2UgPSByZXF1ZXN0cy5nZXQoCiAgICAgICAgICAgICAgICB1cmwsCiAgICAgICAgICAgICAgICBoZWFkZXJzPXsKICAgICAgICAgICAgICAgICAgICAiVXNlci1BZ2VudCI6IFVBLAogICAgICAgICAgICAgICAgICAgICJBY2NlcHQtTGFuZ3VhZ2UiOiAiemgtQ04semg7cT0wLjkiLAogICAgICAgICAgICAgICAgfSwKICAgICAgICAgICAgICAgIHRpbWVvdXQ9MzAsCiAgICAgICAgICAgICkKICAgICAgICAgICAgcmVzcG9uc2UucmFpc2VfZm9yX3N0YXR1cygpCiAgICAgICAgICAgIHJlc3BvbnNlLmVuY29kaW5nID0gcmVzcG9uc2UuZW5jb2Rpbmcgb3IgInV0Zi04IgogICAgICAgICAgICByZXR1cm4gcmVzcG9uc2UudGV4dAogICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZXJyb3I6ICAjIHRyYW5zaWVudCBwcm94eS9ETlMvcmVhZCBmYWlsdXJlcwogICAgICAgICAgICBsYXN0X2Vycm9yID0gZXJyb3IKICAgICAgICAgICAgaWYgYXR0ZW1wdCArIDEgPCBtYXgoMSwgYXR0ZW1wdHMpOgogICAgICAgICAgICAgICAgdGltZS5zbGVlcChfSFRNTF9GRVRDSF9CQUNLT0ZGX1NFQ09ORFMgKiAoYXR0ZW1wdCArIDEpKQogICAgcmFpc2UgSG9uZ2d1b1BsdWdpbkVycm9yKGYiZmV0Y2ggZmFpbGVkOiB7dXJsfSIpIGZyb20gbGFzdF9lcnJvcgoKZGVmIF9yb3V0ZXJfZGF0YShodG1sOiBzdHIpIC0+IGRpY3Rbc3RyLCBBbnldOgogICAgbWF0Y2ggPSByZS5zZWFyY2gociIoPzp3aW5kb3dcLik/X1JPVVRFUl9EQVRBXHMqPVxzKiIsIGh0bWwpCiAgICBpZiBub3QgbWF0Y2g6CiAgICAgICAgcmFpc2UgSG9uZ2d1b1BsdWdpbkVycm9yKCLpobXpnaLmsqHmnInot6/nlLHmlbDmja4iKQogICAgdHJ5OgogICAgICAgIHZhbHVlLCBfID0ganNvbi5KU09ORGVjb2RlcigpLnJhd19kZWNvZGUoaHRtbFttYXRjaC5lbmQoKSA6XSkKICAgIGV4Y2VwdCBqc29uLkpTT05EZWNvZGVFcnJvciBhcyBleGM6CiAgICAgICAgcmFpc2UgSG9uZ2d1b1BsdWdpbkVycm9yKCLpobXpnaLot6/nlLHmlbDmja7op6PmnpDlpLHotKUiKSBmcm9tIGV4YwogICAgaWYgbm90IGlzaW5zdGFuY2UodmFsdWUsIGRpY3QpOgogICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigi6aG16Z2i6Lev55Sx5pWw5o2u5qC85byP6ZSZ6K+vIikKICAgIHJldHVybiB2YWx1ZQoKZGVmIF9tZWRpYV91cmwoaXRlbTogTWFwcGluZ1tzdHIsIEFueV0pIC0+IHN0cjoKICAgIHJldHVybiBfZmlyc3QoCiAgICAgICAgaXRlbS5nZXQoIm1haW5fdXJsIiksCiAgICAgICAgaXRlbS5nZXQoImJhY2t1cF91cmwiKSwKICAgICAgICBpdGVtLmdldCgiYmFja3VwX3VybF8xIiksCiAgICAgICAgaXRlbS5nZXQoInBsYXlfYWRkciIpLAogICAgICAgIGl0ZW0uZ2V0KCJ1cmwiKSwKICAgICkKCmRlZiBfc3BhZGVfdmFsdWUoaXRlbTogTWFwcGluZ1tzdHIsIEFueV0pIC0+IHN0cjoKICAgIGVuY3J5cHRfaW5mbyA9IGl0ZW0uZ2V0KCJlbmNyeXB0X2luZm8iKQogICAgaWYgbm90IGlzaW5zdGFuY2UoZW5jcnlwdF9pbmZvLCBNYXBwaW5nKToKICAgICAgICBlbmNyeXB0X2luZm8gPSB7fQogICAgcmV0dXJuIF9maXJzdChpdGVtLmdldCgic3BhZGVfYSIpLCBlbmNyeXB0X2luZm8uZ2V0KCJzcGFkZV9hIikpCgpkZWYgZGVyaXZlX2NvbnRlbnRfa2V5KHNwYWRlX2I2NDogc3RyKSAtPiBieXRlczoKICAgIHJhdyA9IF9iNjQoc3BhZGVfYjY0KQogICAgaWYgbGVuKHJhdykgPCAzOgogICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigic3BhZGVfYSDlpKrnn60iKQogICAgdjggPSBsZW4ocmF3KSAtIChyYXdbMF0gXiByYXdbMV0gXiByYXdbMl0pICsgNDcKICAgIGlmIHY4IDw9IDAgb3IgMSArIHY4ID4gbGVuKHJhdyk6CiAgICAgICAgdjggPSBsZW4ocmF3KSAtIDEKICAgIGlmIHY4IDwgMzM6CiAgICAgICAgcmFpc2UgSG9uZ2d1b1BsdWdpbkVycm9yKCJzcGFkZV9hIOmVv+W6puW8guW4uCIpCiAgICB2YWx1ZSA9IGJ5dGVhcnJheShyYXdbMSA6IDEgKyB2OF0pCiAgICB2YSwgdmIgPSA4NSwgMjQ2CiAgICBmb3IgaW5kZXggaW4gcmFuZ2UodjgpOgogICAgICAgIHByZXZpb3VzID0gdmEgaWYgaW5kZXggJiAxIGVsc2UgdmIKICAgICAgICBpZiBpbmRleCAmIDE6CiAgICAgICAgICAgIHZhID0gdmFsdWVbaW5kZXhdCiAgICAgICAgZWxzZToKICAgICAgICAgICAgdmIgPSB2YWx1ZVtpbmRleF0KICAgICAgICB2YWx1ZVtpbmRleF0gPSAoLTIxIC0gYmluKGluZGV4KS5jb3VudCgiMSIpICsgKHByZXZpb3VzIF4gdmFsdWVbaW5kZXhdKSkgJiAweEZGCiAgICB0cnk6CiAgICAgICAgcmV0dXJuIGJpbmFzY2lpLnVuaGV4bGlmeShieXRlcyh2YWx1ZVsxOjMzXSkuZGVjb2RlKCJhc2NpaSIpKQogICAgZXhjZXB0IChWYWx1ZUVycm9yLCBiaW5hc2NpaS5FcnJvcikgYXMgZXhjOgogICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigic3BhZGVfYSDlr4bpkqXmnZDmlpnml6DmlYgiKSBmcm9tIGV4YwoKZGVmIF9maW5kX2JveChkYXRhOiBtZW1vcnl2aWV3LCBmb3VyY2M6IGJ5dGVzLCBzdGFydDogaW50KSAtPiB0dXBsZVtpbnQsIGludF06CiAgICBmb3IgaW5kZXggaW4gcmFuZ2UobWF4KDQsIHN0YXJ0KSwgbGVuKGRhdGEpIC0gNCk6CiAgICAgICAgaWYgZGF0YVtpbmRleCA6IGluZGV4ICsgNF0gIT0gZm91cmNjOgogICAgICAgICAgICBjb250aW51ZQogICAgICAgIHNpemUgPSBzdHJ1Y3QudW5wYWNrKCI+SSIsIGRhdGFbaW5kZXggLSA0IDogaW5kZXhdKVswXQogICAgICAgIGlmIHNpemUgPT0gMSBhbmQgaW5kZXggKyAxMiA8PSBsZW4oZGF0YSk6CiAgICAgICAgICAgIHNpemUgPSBzdHJ1Y3QudW5wYWNrKCI+USIsIGRhdGFbaW5kZXggKyA0IDogaW5kZXggKyAxMl0pWzBdCiAgICAgICAgaWYgOCA8PSBzaXplIDw9IDVfMDAwXzAwMCBhbmQgaW5kZXggLSA0ICsgc2l6ZSA8PSBsZW4oZGF0YSk6CiAgICAgICAgICAgIHJldHVybiBpbmRleCAtIDQsIHNpemUKICAgIHJldHVybiAtMSwgMAoKZGVmIF9ib3hfYm9keShkYXRhOiBtZW1vcnl2aWV3LCBmb3VyY2M6IGJ5dGVzLCBzdGFydDogaW50KSAtPiBtZW1vcnl2aWV3IHwgTm9uZToKICAgIG9mZnNldCwgc2l6ZSA9IF9maW5kX2JveChkYXRhLCBmb3VyY2MsIHN0YXJ0KQogICAgcmV0dXJuIGRhdGFbb2Zmc2V0ICsgOCA6IG9mZnNldCArIHNpemVdIGlmIG9mZnNldCA+PSAwIGVsc2UgTm9uZQoKZGVmIF9wYXJzZV90cmFjaygKICAgIG1vb3Y6IG1lbW9yeXZpZXcsCiAgICB0cmFja19vZmZzZXQ6IGludCwKKSAtPiB0dXBsZVtsaXN0W2ludF0sIGxpc3RbaW50XSwgbGlzdFtpbnRdLCBsaXN0W2ludF0sIGludCwgaW50XSB8IE5vbmU6CiAgICBpZiB0cmFja19vZmZzZXQgPCAwOgogICAgICAgIHJldHVybiBOb25lCiAgICBzdGJsX29mZnNldCwgXyA9IF9maW5kX2JveChtb292LCBiInN0YmwiLCB0cmFja19vZmZzZXQgKyA4KQogICAgaWYgc3RibF9vZmZzZXQgPCAwOgogICAgICAgIHJldHVybiBOb25lCiAgICBzdHN6ID0gX2JveF9ib2R5KG1vb3YsIGIic3RzeiIsIHN0Ymxfb2Zmc2V0KQogICAgc3RjbyA9IF9ib3hfYm9keShtb292LCBiInN0Y28iLCBzdGJsX29mZnNldCkKICAgIGNvNjQgPSBfYm94X2JvZHkobW9vdiwgYiJjbzY0Iiwgc3RibF9vZmZzZXQpCiAgICBzdHNjID0gX2JveF9ib2R5KG1vb3YsIGIic3RzYyIsIHN0Ymxfb2Zmc2V0KQogICAgc2FpeiA9IF9ib3hfYm9keShtb292LCBiInNhaXoiLCBzdGJsX29mZnNldCkKICAgIHNhaW8gPSBfYm94X2JvZHkobW9vdiwgYiJzYWlvIiwgc3RibF9vZmZzZXQpCiAgICBpZiBhbnkodmFsdWUgaXMgTm9uZSBmb3IgdmFsdWUgaW4gKHN0c3osIHN0c2MsIHNhaXosIHNhaW8pKSBvciAoCiAgICAgICAgc3RjbyBpcyBOb25lIGFuZCBjbzY0IGlzIE5vbmUKICAgICk6CiAgICAgICAgcmV0dXJuIE5vbmUKICAgIGFzc2VydCBzdHN6IGlzIG5vdCBOb25lIGFuZCBzdHNjIGlzIG5vdCBOb25lCiAgICBhc3NlcnQgc2FpeiBpcyBub3QgTm9uZSBhbmQgc2FpbyBpcyBub3QgTm9uZQogICAgZGVmYXVsdF9zaXplID0gc3RydWN0LnVucGFjaygiPkkiLCBzdHN6WzQ6OF0pWzBdCiAgICBzYW1wbGVfY291bnQgPSBzdHJ1Y3QudW5wYWNrKCI+SSIsIHN0c3pbODoxMl0pWzBdCiAgICBzaXplcyA9ICgKICAgICAgICBbZGVmYXVsdF9zaXplXSAqIHNhbXBsZV9jb3VudAogICAgICAgIGlmIGRlZmF1bHRfc2l6ZQogICAgICAgIGVsc2UgWwogICAgICAgICAgICBzdHJ1Y3QudW5wYWNrKCI+SSIsIHN0c3pbMTIgKyBpbmRleCAqIDQgOiAxNiArIGluZGV4ICogNF0pWzBdCiAgICAgICAgICAgIGZvciBpbmRleCBpbiByYW5nZShzYW1wbGVfY291bnQpCiAgICAgICAgXQogICAgKQogICAgY2h1bmtfdGFibGUgPSBzdGNvIGlmIHN0Y28gaXMgbm90IE5vbmUgZWxzZSBjbzY0CiAgICBhc3NlcnQgY2h1bmtfdGFibGUgaXMgbm90IE5vbmUKICAgIGNodW5rX2NvdW50ID0gc3RydWN0LnVucGFjaygiPkkiLCBjaHVua190YWJsZVs0OjhdKVswXQogICAgY2h1bmtfd2lkdGggPSA0IGlmIHN0Y28gaXMgbm90IE5vbmUgZWxzZSA4CiAgICBvZmZzZXRzID0gWwogICAgICAgIGludC5mcm9tX2J5dGVzKAogICAgICAgICAgICBjaHVua190YWJsZVsKICAgICAgICAgICAgICAgIDggKyBpbmRleCAqIGNodW5rX3dpZHRoIDogOCArIChpbmRleCArIDEpICogY2h1bmtfd2lkdGgKICAgICAgICAgICAgXSwKICAgICAgICAgICAgImJpZyIsCiAgICAgICAgKQogICAgICAgIGZvciBpbmRleCBpbiByYW5nZShjaHVua19jb3VudCkKICAgIF0KICAgIGVudHJ5X2NvdW50ID0gc3RydWN0LnVucGFjaygiPkkiLCBzdHNjWzQ6OF0pWzBdCiAgICBlbnRyaWVzID0gWwogICAgICAgICgKICAgICAgICAgICAgc3RydWN0LnVucGFjaygiPkkiLCBzdHNjWzggKyBpbmRleCAqIDEyIDogMTIgKyBpbmRleCAqIDEyXSlbMF0sCiAgICAgICAgICAgIHN0cnVjdC51bnBhY2soIj5JIiwgc3RzY1sxMiArIGluZGV4ICogMTIgOiAxNiArIGluZGV4ICogMTJdKVswXSwKICAgICAgICApCiAgICAgICAgZm9yIGluZGV4IGluIHJhbmdlKGVudHJ5X2NvdW50KQogICAgXQogICAgY2h1bmtfc2FtcGxlcyA9IFswXSAqIGNodW5rX2NvdW50CiAgICBmb3IgaW5kZXgsIChmaXJzdF9jaHVuaywgc2FtcGxlc19wZXJfY2h1bmspIGluIGVudW1lcmF0ZShlbnRyaWVzKToKICAgICAgICBlbmQgPSBlbnRyaWVzW2luZGV4ICsgMV1bMF0gLSAxIGlmIGluZGV4ICsgMSA8IGxlbihlbnRyaWVzKSBlbHNlIGNodW5rX2NvdW50CiAgICAgICAgZm9yIGNodW5rIGluIHJhbmdlKGZpcnN0X2NodW5rIC0gMSwgbWluKGVuZCwgY2h1bmtfY291bnQpKToKICAgICAgICAgICAgY2h1bmtfc2FtcGxlc1tjaHVua10gPSBzYW1wbGVzX3Blcl9jaHVuawogICAgc2Fpel9mbGFncyA9IGludC5mcm9tX2J5dGVzKHNhaXpbMTo0XSwgImJpZyIpCiAgICBzYWl6X2N1cnNvciA9IDEyIGlmIHNhaXpfZmxhZ3MgJiAxIGVsc2UgNAogICAgaWYgbGVuKHNhaXopIDwgc2Fpel9jdXJzb3IgKyA1OgogICAgICAgIHJldHVybiBOb25lCiAgICBkZWZhdWx0X2F1eF9zaXplID0gc2FpeltzYWl6X2N1cnNvcl0KICAgIGF1eF9jb3VudCA9IHN0cnVjdC51bnBhY2soIj5JIiwgc2FpeltzYWl6X2N1cnNvciArIDEgOiBzYWl6X2N1cnNvciArIDVdKVswXQogICAgYXV4X3NpemVzID0gKAogICAgICAgIFtkZWZhdWx0X2F1eF9zaXplXSAqIGF1eF9jb3VudAogICAgICAgIGlmIGRlZmF1bHRfYXV4X3NpemUKICAgICAgICBlbHNlIFsKICAgICAgICAgICAgaW50KHNhaXpbc2Fpel9jdXJzb3IgKyA1ICsgaW5kZXhdKQogICAgICAgICAgICBmb3IgaW5kZXggaW4gcmFuZ2UoYXV4X2NvdW50KQogICAgICAgICAgICBpZiBzYWl6X2N1cnNvciArIDUgKyBpbmRleCA8IGxlbihzYWl6KQogICAgICAgIF0KICAgICkKICAgIGlmIGxlbihhdXhfc2l6ZXMpICE9IGF1eF9jb3VudDoKICAgICAgICByZXR1cm4gTm9uZQogICAgc2Fpb19mbGFncyA9IGludC5mcm9tX2J5dGVzKHNhaW9bMTo0XSwgImJpZyIpCiAgICBzYWlvX2N1cnNvciA9IDEyIGlmIHNhaW9fZmxhZ3MgJiAxIGVsc2UgNAogICAgb2Zmc2V0X3dpZHRoID0gOCBpZiBzYWlvWzBdID09IDEgZWxzZSA0CiAgICBpZiBsZW4oc2FpbykgPCBzYWlvX2N1cnNvciArIDQgKyBvZmZzZXRfd2lkdGg6CiAgICAgICAgcmV0dXJuIE5vbmUKICAgIGVudHJ5X2NvdW50ID0gaW50LmZyb21fYnl0ZXMoc2Fpb1tzYWlvX2N1cnNvciA6IHNhaW9fY3Vyc29yICsgNF0sICJiaWciKQogICAgaWYgZW50cnlfY291bnQgPCAxOgogICAgICAgIHJldHVybiBOb25lCiAgICBhdXhfb2Zmc2V0ID0gaW50LmZyb21fYnl0ZXMoCiAgICAgICAgc2Fpb1tzYWlvX2N1cnNvciArIDQgOiBzYWlvX2N1cnNvciArIDQgKyBvZmZzZXRfd2lkdGhdLAogICAgICAgICJiaWciLAogICAgKQogICAgcmV0dXJuIHNpemVzLCBvZmZzZXRzLCBjaHVua19zYW1wbGVzLCBhdXhfc2l6ZXMsIGF1eF9vZmZzZXQsIHNhbXBsZV9jb3VudAoKZGVmIF9yZXBsYWNlX2ZvdXJjYyhkYXRhOiBieXRlYXJyYXksIG9sZDogYnl0ZXMsIG5ldzogYnl0ZXMpIC0+IE5vbmU6CiAgICBwb3NpdGlvbiA9IDAKICAgIHdoaWxlIFRydWU6CiAgICAgICAgcG9zaXRpb24gPSBkYXRhLmZpbmQob2xkLCBwb3NpdGlvbikKICAgICAgICBpZiBwb3NpdGlvbiA8IDA6CiAgICAgICAgICAgIHJldHVybgogICAgICAgIGRhdGFbcG9zaXRpb24gOiBwb3NpdGlvbiArIGxlbihvbGQpXSA9IG5ldwogICAgICAgIHBvc2l0aW9uICs9IGxlbihuZXcpCgpkZWYgX3JlcGxhY2Vfc2luZihkYXRhOiBieXRlYXJyYXkpIC0+IE5vbmU6CiAgICBwb3NpdGlvbiA9IDAKICAgIHdoaWxlIFRydWU6CiAgICAgICAgcG9zaXRpb24gPSBkYXRhLmZpbmQoYiJzaW5mIiwgcG9zaXRpb24pCiAgICAgICAgaWYgcG9zaXRpb24gPCAwOgogICAgICAgICAgICByZXR1cm4KICAgICAgICBpZiBwb3NpdGlvbiA+PSA0OgogICAgICAgICAgICBzaXplID0gc3RydWN0LnVucGFjaygiPkkiLCBkYXRhW3Bvc2l0aW9uIC0gNCA6IHBvc2l0aW9uXSlbMF0KICAgICAgICAgICAgZW5kID0gcG9zaXRpb24gLSA0ICsgc2l6ZQogICAgICAgICAgICBpZiA4IDw9IHNpemUgPCA1MF8wMDAgYW5kIGVuZCA8PSBsZW4oZGF0YSk6CiAgICAgICAgICAgICAgICBkYXRhW3Bvc2l0aW9uIDogcG9zaXRpb24gKyA0XSA9IGIiZnJlZSIKICAgICAgICAgICAgICAgIGRhdGFbcG9zaXRpb24gKyA0IDogZW5kXSA9IGIiXHgwMCIgKiBtYXgoMCwgZW5kIC0gcG9zaXRpb24gLSA0KQogICAgICAgICAgICAgICAgcG9zaXRpb24gPSBlbmQKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgcG9zaXRpb24gKz0gNAoKZGVmIGRlY3J5cHRfbXA0X2NlbmMoZGF0YTogYnl0ZXMsIGNvbnRlbnRfa2V5OiBieXRlcykgLT4gYnl0ZXM6CiAgICBpZiBsZW4oY29udGVudF9rZXkpICE9IDE2OgogICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigiQ0VOQyDlr4bpkqXplb/luqbplJnor68iKQogICAgcmVzdWx0ID0gYnl0ZWFycmF5KGRhdGEpCiAgICBpZiBsZW4ocmVzdWx0KSA8IDE2OgogICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigiTVA0IOaVsOaNrui/h+efrSIpCiAgICBtb292X3N0YXJ0LCBtb292X3NpemUgPSBfZmluZF9ib3gobWVtb3J5dmlldyhyZXN1bHQpLCBiIm1vb3YiLCAwKQogICAgaWYgbW9vdl9zdGFydCA8IDAgb3IgbW9vdl9zaXplIDwgODoKICAgICAgICByYWlzZSBIb25nZ3VvUGx1Z2luRXJyb3IoIk1QNCBtb292IOi2iueVjCIpCiAgICBtb292ID0gbWVtb3J5dmlldyhyZXN1bHQpW21vb3Zfc3RhcnQgOiBtb292X3N0YXJ0ICsgbW9vdl9zaXplXQogICAgdHJhY2tzOiBsaXN0W2ludF0gPSBbXQogICAgdHJhY2tfc2VhcmNoID0gMAogICAgd2hpbGUgVHJ1ZToKICAgICAgICB0cmFjaywgdHJhY2tfc2l6ZSA9IF9maW5kX2JveChtb292LCBiInRyYWsiLCB0cmFja19zZWFyY2gpCiAgICAgICAgaWYgdHJhY2sgPCAwOgogICAgICAgICAgICBicmVhawogICAgICAgIHRyYWNrcy5hcHBlbmQodHJhY2spCiAgICAgICAgdHJhY2tfc2VhcmNoID0gdHJhY2sgKyBtYXgodHJhY2tfc2l6ZSwgOCkKICAgIGRlY3J5cHRlZF9zYW1wbGVzID0gMAogICAgZm9yIHRyYWNrIGluIHRyYWNrczoKICAgICAgICBwYXJzZWQgPSBfcGFyc2VfdHJhY2sobW9vdiwgdHJhY2spCiAgICAgICAgaWYgcGFyc2VkIGlzIE5vbmU6CiAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgc2l6ZXMsIG9mZnNldHMsIGNodW5rX2NvdW50cywgYXV4X3NpemVzLCBhdXhfb2Zmc2V0LCBzYW1wbGVfY291bnQgPSBwYXJzZWQKICAgICAgICBhdXhfc2l6ZSA9IHN1bShtYXgoc2l6ZSwgOCkgZm9yIHNpemUgaW4gYXV4X3NpemVzKQogICAgICAgIGlmIG5vdCBzYW1wbGVfY291bnQgb3IgYXV4X29mZnNldCA8IDAgb3IgYXV4X29mZnNldCArIGF1eF9zaXplID4gbGVuKHJlc3VsdCk6CiAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgYXV4ID0gcmVzdWx0W2F1eF9vZmZzZXQgOiBhdXhfb2Zmc2V0ICsgYXV4X3NpemVdCiAgICAgICAgc2FtcGxlX2luZGV4ID0gMAogICAgICAgIGF1eF9pbmRleCA9IDAKICAgICAgICBmb3IgY2h1bmtfaW5kZXgsIGNodW5rX29mZnNldCBpbiBlbnVtZXJhdGUob2Zmc2V0cyk6CiAgICAgICAgICAgIGN1cnJlbnQgPSBjaHVua19vZmZzZXQKICAgICAgICAgICAgZm9yIF8gaW4gcmFuZ2UoY2h1bmtfY291bnRzW2NodW5rX2luZGV4XSk6CiAgICAgICAgICAgICAgICBpZiBzYW1wbGVfaW5kZXggPj0gc2FtcGxlX2NvdW50IG9yIHNhbXBsZV9pbmRleCA+PSBsZW4oc2l6ZXMpOgogICAgICAgICAgICAgICAgICAgIGJyZWFrCiAgICAgICAgICAgICAgICBzaXplID0gc2l6ZXNbc2FtcGxlX2luZGV4XQogICAgICAgICAgICAgICAgaWYgY3VycmVudCArIHNpemUgPiBsZW4ocmVzdWx0KToKICAgICAgICAgICAgICAgICAgICByYWlzZSBIb25nZ3VvUGx1Z2luRXJyb3IoIk1QNCDmoLfmnKzotornlYwiKQogICAgICAgICAgICAgICAgaWYgc2FtcGxlX2luZGV4ID49IGxlbihhdXhfc2l6ZXMpOgogICAgICAgICAgICAgICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigiTVA0IOi+heWKqeS/oeaBr+aVsOmHj+S4jei2syIpCiAgICAgICAgICAgICAgICBlbnRyeV9zaXplID0gbWF4KGF1eF9zaXplc1tzYW1wbGVfaW5kZXhdLCA4KQogICAgICAgICAgICAgICAgaXYgPSBieXRlcyhhdXhbYXV4X2luZGV4IDogYXV4X2luZGV4ICsgbWluKGVudHJ5X3NpemUsIDgpXSkubGp1c3QoCiAgICAgICAgICAgICAgICAgICAgOCwgYiJcMCIKICAgICAgICAgICAgICAgICkgKyBiIlwwIiAqIDgKICAgICAgICAgICAgICAgIHJlc3VsdFtjdXJyZW50IDogY3VycmVudCArIHNpemVdID0gX2Flc19jdHJfZGVjcnlwdCgKICAgICAgICAgICAgICAgICAgICBjb250ZW50X2tleSwgaXYsIGJ5dGVzKHJlc3VsdFtjdXJyZW50IDogY3VycmVudCArIHNpemVdKQogICAgICAgICAgICAgICAgKQogICAgICAgICAgICAgICAgY3VycmVudCArPSBzaXplCiAgICAgICAgICAgICAgICBzYW1wbGVfaW5kZXggKz0gMQogICAgICAgICAgICAgICAgYXV4X2luZGV4ICs9IGVudHJ5X3NpemUKICAgICAgICAgICAgICAgIGRlY3J5cHRlZF9zYW1wbGVzICs9IDEKICAgIGlmIG5vdCBkZWNyeXB0ZWRfc2FtcGxlczoKICAgICAgICByYWlzZSBIb25nZ3VvUGx1Z2luRXJyb3IoIk1QNCDmsqHmnInlj6/op6Plr4bnmoQgQ0VOQyDmoLfmnKwiKQogICAgbW9vdl9idWZmZXIgPSBieXRlYXJyYXkocmVzdWx0W21vb3Zfc3RhcnQgOiBtb292X3N0YXJ0ICsgbW9vdl9zaXplXSkKICAgIF9yZXN0b3JlX2NlbmNfY29kZWNzKG1vb3ZfYnVmZmVyKQogICAgX3JlcGxhY2Vfc2luZihtb292X2J1ZmZlcikKICAgIHJlc3VsdFttb292X3N0YXJ0IDogbW9vdl9zdGFydCArIG1vb3Zfc2l6ZV0gPSBtb292X2J1ZmZlcgogICAgcmV0dXJuIGJ5dGVzKHJlc3VsdCkKCk1FRElBX0hFQURFUlMgPSB7IlVzZXItQWdlbnQiOiBNRURJQV9VQSwgIlJlZmVyZXIiOiAiaHR0cHM6Ly9ub3ZlbC5zbnNzZGsuY29tLyJ9CgpfU1RSRUFNX1BPUlRfUkFOR0UgPSAoOTk5MCwgMTAwMDApCl9TVFJFQU1fQ0hVTksgPSAxIDw8IDIwCl9TVFJFQU1fSEVBRF9QUk9CRSA9IDEgPDwgMTYKX1NUUkVBTV9UVExfU0VDT05EUyA9IDkwMApfU1RSRUFNX01BWF9TRVNTSU9OUyA9IDQKX1NUUkVBTV9TVEFURTogZGljdFtzdHIsIEFueV0gPSB7InBvcnQiOiAwLCAic2VydmVyIjogTm9uZSwgInNlc3Npb25zIjoge319Cl9TVFJFQU1fTE9DSyA9IHRocmVhZGluZy5STG9jaygpCgoKZGVmIF90b3BsZXZlbF9ib3hlcyhidWY6IGJ5dGVzKSAtPiBsaXN0W3R1cGxlW2ludCwgaW50LCBieXRlc11dOgogICAgYm94ZXM6IGxpc3RbdHVwbGVbaW50LCBpbnQsIGJ5dGVzXV0gPSBbXQogICAgY3Vyc29yID0gMAogICAgd2hpbGUgY3Vyc29yICsgOCA8PSBsZW4oYnVmKToKICAgICAgICBzaXplID0gc3RydWN0LnVucGFjaygiPkkiLCBidWZbY3Vyc29yIDogY3Vyc29yICsgNF0pWzBdCiAgICAgICAgZm91cmNjID0gYnl0ZXMoYnVmW2N1cnNvciArIDQgOiBjdXJzb3IgKyA4XSkKICAgICAgICBpZiBzaXplID09IDE6CiAgICAgICAgICAgIGlmIGN1cnNvciArIDE2ID4gbGVuKGJ1Zik6CiAgICAgICAgICAgICAgICBicmVhawogICAgICAgICAgICBzaXplID0gc3RydWN0LnVucGFjaygiPlEiLCBidWZbY3Vyc29yICsgOCA6IGN1cnNvciArIDE2XSlbMF0KICAgICAgICBpZiBzaXplIDwgODoKICAgICAgICAgICAgYnJlYWsKICAgICAgICBib3hlcy5hcHBlbmQoKGN1cnNvciwgc2l6ZSwgZm91cmNjKSkKICAgICAgICBjdXJzb3IgKz0gc2l6ZQogICAgcmV0dXJuIGJveGVzCgoKZGVmIF9yYW5nZV9nZXQodXJsOiBzdHIsIHN0YXJ0OiBpbnQsIGVuZDogaW50KSAtPiB0dXBsZVtieXRlcywgaW50XToKICAgIGhlYWRlcnMgPSBkaWN0KE1FRElBX0hFQURFUlMpCiAgICBoZWFkZXJzWyJSYW5nZSJdID0gImJ5dGVzPSVkLSVkIiAlIChzdGFydCwgZW5kKQogICAgZXhwZWN0ZWQgPSBlbmQgLSBzdGFydCArIDEKICAgIGxhc3RfZXJyb3I6IEV4Y2VwdGlvbiB8IE5vbmUgPSBOb25lCiAgICBmb3IgYXR0ZW1wdCBpbiByYW5nZShfUkFOR0VfRkVUQ0hfQVRURU1QVFMpOgogICAgICAgIGlmIGF0dGVtcHQ6CiAgICAgICAgICAgIHRpbWUuc2xlZXAoX1JBTkdFX0ZFVENIX0JBQ0tPRkZfU0VDT05EUyAqIGF0dGVtcHQpCiAgICAgICAgdHJ5OgogICAgICAgICAgICByZXNwb25zZSA9IHJlcXVlc3RzLmdldCh1cmwsIGhlYWRlcnM9aGVhZGVycywgdGltZW91dD02MCkKICAgICAgICBleGNlcHQgcmVxdWVzdHMuUmVxdWVzdEV4Y2VwdGlvbiBhcyBlcnJvcjoKICAgICAgICAgICAgbGFzdF9lcnJvciA9IGVycm9yCiAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgaWYgcmVzcG9uc2Uuc3RhdHVzX2NvZGUgbm90IGluICgyMDAsIDIwNik6CiAgICAgICAgICAgIGxhc3RfZXJyb3IgPSBIb25nZ3VvUGx1Z2luRXJyb3IoCiAgICAgICAgICAgICAgICAi5aqS5L2T5YiG54mH6K+35rGC5aSx6LSlICVzIiAlIHJlc3BvbnNlLnN0YXR1c19jb2RlCiAgICAgICAgICAgICkKICAgICAgICAgICAgY29udGludWUKICAgICAgICBib2R5ID0gcmVzcG9uc2UuY29udGVudAogICAgICAgICMg5LiK5ri45YG25Y+R6L+U5Zue55+t5YyF77yb55+t5LqO6K+35rGC6ZW/5bqm5pe26YeN6K+V77yM6YG/5YWN5pKt5pS+5Zmo5pS25Yiw5oiq5pat5pWw5o2u44CCCiAgICAgICAgaWYgbm90IGJvZHkgb3IgKHJlc3BvbnNlLnN0YXR1c19jb2RlID09IDIwNiBhbmQgbGVuKGJvZHkpIDwgZXhwZWN0ZWQpOgogICAgICAgICAgICBsYXN0X2Vycm9yID0gSG9uZ2d1b1BsdWdpbkVycm9yKAogICAgICAgICAgICAgICAgIuWqkuS9k+WIhueJh+mVv+W6puS4jei2syAlZC8lZCIgJSAobGVuKGJvZHkpLCBleHBlY3RlZCkKICAgICAgICAgICAgKQogICAgICAgICAgICBjb250aW51ZQogICAgICAgIHRvdGFsID0gMAogICAgICAgIGNvbnRlbnRfcmFuZ2UgPSByZXNwb25zZS5oZWFkZXJzLmdldCgiQ29udGVudC1SYW5nZSIpIG9yICIiCiAgICAgICAgaWYgIi8iIGluIGNvbnRlbnRfcmFuZ2U6CiAgICAgICAgICAgIHRhaWwgPSBjb250ZW50X3JhbmdlLnJzcGxpdCgiLyIsIDEpWzFdLnN0cmlwKCkKICAgICAgICAgICAgaWYgdGFpbC5pc2RpZ2l0KCk6CiAgICAgICAgICAgICAgICB0b3RhbCA9IGludCh0YWlsKQogICAgICAgIGlmIG5vdCB0b3RhbDoKICAgICAgICAgICAgbGVuZ3RoID0gcmVzcG9uc2UuaGVhZGVycy5nZXQoIkNvbnRlbnQtTGVuZ3RoIikgb3IgIiIKICAgICAgICAgICAgdG90YWwgPSBpbnQobGVuZ3RoKSBpZiBsZW5ndGguaXNkaWdpdCgpIGVsc2UgMAogICAgICAgIHJldHVybiBib2R5LCB0b3RhbAogICAgcmFpc2UgbGFzdF9lcnJvciBvciBIb25nZ3VvUGx1Z2luRXJyb3IoIuWqkuS9k+WIhueJh+ivt+axguWksei0pSIpCgoKZGVmIF9mZXRjaF9tb292KHVybDogc3RyKSAtPiB0dXBsZVtpbnQsIGludCwgYnl0ZXNdOgogICAgcHJvYmUsIHRvdGFsID0gX3JhbmdlX2dldCh1cmwsIDAsIF9TVFJFQU1fSEVBRF9QUk9CRSAtIDEpCiAgICBpZiBub3QgdG90YWw6CiAgICAgICAgcmFpc2UgSG9uZ2d1b1BsdWdpbkVycm9yKCLlqpLkvZPmgLvplb/luqbmnKrnn6UiKQogICAgbW9vdl9zdGFydCA9IDAKICAgIG1vb3Zfc2l6ZSA9IDAKICAgIGZvciBvZmZzZXQsIHNpemUsIGZvdXJjYyBpbiBfdG9wbGV2ZWxfYm94ZXMocHJvYmUpOgogICAgICAgIGlmIGZvdXJjYyA9PSBiIm1vb3YiOgogICAgICAgICAgICBtb292X3N0YXJ0ID0gb2Zmc2V0CiAgICAgICAgICAgIG1vb3Zfc2l6ZSA9IHNpemUKICAgICAgICAgICAgYnJlYWsKICAgIGlmIG5vdCBtb292X3NpemU6CiAgICAgICAgcmFpc2UgSG9uZ2d1b1BsdWdpbkVycm9yKCLmnKrmib7liLAgbW9vdiDpobblsYLnm5IiKQogICAgaWYgbW9vdl9zdGFydCArIG1vb3Zfc2l6ZSA+IHRvdGFsOgogICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigibW9vdiDotornlYwiKQogICAgaWYgbW9vdl9zdGFydCArIG1vb3Zfc2l6ZSA8PSBsZW4ocHJvYmUpOgogICAgICAgIHJldHVybiB0b3RhbCwgbW9vdl9zdGFydCwgYnl0ZXMocHJvYmVbbW9vdl9zdGFydCA6IG1vb3Zfc3RhcnQgKyBtb292X3NpemVdKQogICAgbW9vdiwgXyA9IF9yYW5nZV9nZXQodXJsLCBtb292X3N0YXJ0LCBtb292X3N0YXJ0ICsgbW9vdl9zaXplIC0gMSkKICAgIGlmIGxlbihtb292KSAhPSBtb292X3NpemU6CiAgICAgICAgcmFpc2UgSG9uZ2d1b1BsdWdpbkVycm9yKCJtb292IOWIhueJh+mVv+W6puS4jeespiIpCiAgICByZXR1cm4gdG90YWwsIG1vb3Zfc3RhcnQsIG1vb3YKCgpkZWYgX29yaWdpbmFsX2Zvcm1hdF9uZWFyKGRhdGE6IGJ5dGVhcnJheSwgZW50cnlfcG9zOiBpbnQsIGRlZmF1bHQ6IGJ5dGVzKSAtPiBieXRlczoKICAgICIiIuS7jiBzYW1wbGUgZW50cnkg5ZCO55qEIHNpbmYvZnJtYSDor7vlj5bljp/lp4vlm5vlrZfnrKbnoIHvvIhhdmMxL2h2YzEvbXA0YSDnrYnvvInjgIIiIiIKICAgIGJsb2IgPSBieXRlcyhkYXRhW2VudHJ5X3BvcyA6IG1pbihsZW4oZGF0YSksIGVudHJ5X3BvcyArIDgwMCldKQogICAgaWR4ID0gMAogICAgd2hpbGUgVHJ1ZToKICAgICAgICBwb3MgPSBibG9iLmZpbmQoYiJmcm1hIiwgaWR4KQogICAgICAgIGlmIHBvcyA8IDA6CiAgICAgICAgICAgIHJldHVybiBkZWZhdWx0CiAgICAgICAgaWYgcG9zICsgOCA8PSBsZW4oYmxvYik6CiAgICAgICAgICAgIGZtdCA9IGJ5dGVzKGJsb2JbcG9zICsgNCA6IHBvcyArIDhdKQogICAgICAgICAgICBpZiBmbXQgbm90IGluIChiIiIsIGIiXHgwMFx4MDBceDAwXHgwMCIsIGIiZW5jdiIsIGIiZW5jYSIpIGFuZCBhbGwoMzIgPD0gYyA8IDEyNyBmb3IgYyBpbiBmbXQpOgogICAgICAgICAgICAgICAgcmV0dXJuIGZtdAogICAgICAgIGlkeCA9IHBvcyArIDQKCgpkZWYgX3Jlc3RvcmVfY2VuY19jb2RlY3MoZGF0YTogYnl0ZWFycmF5KSAtPiBOb25lOgogICAgIiIi5oqKIGVuY3YvZW5jYSDov5jljp/kuLogZnJtYSDkuK3nmoTnnJ/lrp7nvJbnoIHvvIzpgb/lhY3kuIDlvovmlLnmiJAgaHZjMSDlr7zoh7Tlj6rmnInlo7Dpn7PjgIIiIiIKICAgIHBvcyA9IDAKICAgIHdoaWxlIFRydWU6CiAgICAgICAgcG9zID0gZGF0YS5maW5kKGIiZW5jdiIsIHBvcykKICAgICAgICBpZiBwb3MgPCAwOgogICAgICAgICAgICBicmVhawogICAgICAgIGRhdGFbcG9zIDogcG9zICsgNF0gPSBfb3JpZ2luYWxfZm9ybWF0X25lYXIoZGF0YSwgcG9zLCBiImF2YzEiKQogICAgICAgIHBvcyArPSA0CiAgICBwb3MgPSAwCiAgICB3aGlsZSBUcnVlOgogICAgICAgIHBvcyA9IGRhdGEuZmluZChiImVuY2EiLCBwb3MpCiAgICAgICAgaWYgcG9zIDwgMDoKICAgICAgICAgICAgYnJlYWsKICAgICAgICBkYXRhW3BvcyA6IHBvcyArIDRdID0gX29yaWdpbmFsX2Zvcm1hdF9uZWFyKGRhdGEsIHBvcywgYiJtcDRhIikKICAgICAgICBwb3MgKz0gNAoKCmRlZiBfcmV3cml0ZV9tb292KG1vb3Y6IGJ5dGVzKSAtPiBieXRlczoKICAgIHJlc3VsdCA9IGJ5dGVhcnJheShtb292KQogICAgX3Jlc3RvcmVfY2VuY19jb2RlY3MocmVzdWx0KQogICAgX3JlcGxhY2Vfc2luZihyZXN1bHQpCiAgICByZXR1cm4gYnl0ZXMocmVzdWx0KQoKCmRlZiBfc2FtcGxlX3RhYmxlKG1vb3Y6IGJ5dGVzLCBtb292X3N0YXJ0OiBpbnQpIC0+IGxpc3RbdHVwbGVbaW50LCBpbnQsIGJ5dGVzXV06CiAgICB2aWV3ID0gbWVtb3J5dmlldyhtb292KQogICAgc2FtcGxlczogbGlzdFt0dXBsZVtpbnQsIGludCwgYnl0ZXNdXSA9IFtdCiAgICB0cmFja19zZWFyY2ggPSAwCiAgICB3aGlsZSBUcnVlOgogICAgICAgIHRyYWNrLCB0cmFja19zaXplID0gX2ZpbmRfYm94KHZpZXcsIGIidHJhayIsIHRyYWNrX3NlYXJjaCkKICAgICAgICBpZiB0cmFjayA8IDA6CiAgICAgICAgICAgIGJyZWFrCiAgICAgICAgdHJhY2tfc2VhcmNoID0gdHJhY2sgKyBtYXgodHJhY2tfc2l6ZSwgOCkKICAgICAgICBwYXJzZWQgPSBfcGFyc2VfdHJhY2sodmlldywgdHJhY2spCiAgICAgICAgaWYgcGFyc2VkIGlzIE5vbmU6CiAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgc2l6ZXMsIG9mZnNldHMsIGNodW5rX2NvdW50cywgYXV4X3NpemVzLCBhdXhfb2Zmc2V0LCBzYW1wbGVfY291bnQgPSBwYXJzZWQKICAgICAgICBhdXhfbGVuZ3RoID0gc3VtKG1heChzaXplLCA4KSBmb3Igc2l6ZSBpbiBhdXhfc2l6ZXMpCiAgICAgICAgYXV4X2xvY2FsID0gYXV4X29mZnNldCAtIG1vb3Zfc3RhcnQKICAgICAgICBpZiBhdXhfbG9jYWwgPCAwIG9yIGF1eF9sb2NhbCArIGF1eF9sZW5ndGggPiBsZW4obW9vdik6CiAgICAgICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigiQ0VOQyDovoXliqnkv6Hmga/kuI3lnKggbW9vdiDlhoXvvIzml6Dms5XmtYHlvI/op6Plr4YiKQogICAgICAgIGF1eCA9IG1vb3ZbYXV4X2xvY2FsIDogYXV4X2xvY2FsICsgYXV4X2xlbmd0aF0KICAgICAgICBzYW1wbGVfaW5kZXggPSAwCiAgICAgICAgYXV4X2luZGV4ID0gMAogICAgICAgIGZvciBjaHVua19pbmRleCwgY2h1bmtfb2Zmc2V0IGluIGVudW1lcmF0ZShvZmZzZXRzKToKICAgICAgICAgICAgY3VycmVudCA9IGNodW5rX29mZnNldAogICAgICAgICAgICBmb3IgXyBpbiByYW5nZShjaHVua19jb3VudHNbY2h1bmtfaW5kZXhdKToKICAgICAgICAgICAgICAgIGlmIHNhbXBsZV9pbmRleCA+PSBzYW1wbGVfY291bnQgb3Igc2FtcGxlX2luZGV4ID49IGxlbihzaXplcyk6CiAgICAgICAgICAgICAgICAgICAgYnJlYWsKICAgICAgICAgICAgICAgIGlmIHNhbXBsZV9pbmRleCA+PSBsZW4oYXV4X3NpemVzKToKICAgICAgICAgICAgICAgICAgICByYWlzZSBIb25nZ3VvUGx1Z2luRXJyb3IoIkNFTkMg6L6F5Yqp5L+h5oGv5pWw6YeP5LiN6LazIikKICAgICAgICAgICAgICAgIGVudHJ5X3NpemUgPSBtYXgoYXV4X3NpemVzW3NhbXBsZV9pbmRleF0sIDgpCiAgICAgICAgICAgICAgICBpbml0aWFsX3ZlY3RvciA9IGJ5dGVzKAogICAgICAgICAgICAgICAgICAgIGF1eFthdXhfaW5kZXggOiBhdXhfaW5kZXggKyBtaW4oZW50cnlfc2l6ZSwgOCldCiAgICAgICAgICAgICAgICApLmxqdXN0KDgsIGIiXDAiKSArIGIiXDAiICogOAogICAgICAgICAgICAgICAgc2FtcGxlcy5hcHBlbmQoKGN1cnJlbnQsIHNpemVzW3NhbXBsZV9pbmRleF0sIGluaXRpYWxfdmVjdG9yKSkKICAgICAgICAgICAgICAgIGN1cnJlbnQgKz0gc2l6ZXNbc2FtcGxlX2luZGV4XQogICAgICAgICAgICAgICAgYXV4X2luZGV4ICs9IGVudHJ5X3NpemUKICAgICAgICAgICAgICAgIHNhbXBsZV9pbmRleCArPSAxCiAgICBpZiBub3Qgc2FtcGxlczoKICAgICAgICByYWlzZSBIb25nZ3VvUGx1Z2luRXJyb3IoIm1vb3Yg5Lit5rKh5pyJ5Y+v6Kej5a+G55qEIENFTkMg5qC35pysIikKICAgIHNhbXBsZXMuc29ydCgpCiAgICByZXR1cm4gc2FtcGxlcwoKCmNsYXNzIF9TdHJlYW1TZXNzaW9uOgogICAgIiIi5oyJIFJhbmdlIOmAkOWdl+aLieWPluWKoOWvhiBNUDTvvIzovrnkuIvovrnop6MgQ0VOQ++8jOS+m+acrOWcsOaSreaUvuWZqOebtOi/nuOAgiIiIgoKICAgIGRlZiBfX2luaXRfXygKICAgICAgICBzZWxmLAogICAgICAgIHVybDogc3RyLAogICAgICAgIGNvbnRlbnRfa2V5OiBieXRlcywKICAgICAgICB0b3RhbDogaW50LAogICAgICAgIG1vb3Zfc3RhcnQ6IGludCwKICAgICAgICBtb292OiBieXRlcywKICAgICkgLT4gTm9uZToKICAgICAgICBpZiBsZW4oY29udGVudF9rZXkpICE9IDE2OgogICAgICAgICAgICByYWlzZSBIb25nZ3VvUGx1Z2luRXJyb3IoIkNFTkMg5a+G6ZKl6ZW/5bqm6ZSZ6K+vIikKICAgICAgICBzZWxmLnVybCA9IHVybAogICAgICAgIHNlbGYuY29udGVudF9rZXkgPSBjb250ZW50X2tleQogICAgICAgIHNlbGYudG90YWwgPSB0b3RhbAogICAgICAgIHNlbGYubW9vdl9zdGFydCA9IG1vb3Zfc3RhcnQKICAgICAgICBzZWxmLm1vb3ZfcGxhaW4gPSBfcmV3cml0ZV9tb292KG1vb3YpCiAgICAgICAgc2VsZi5tb292X2VuZCA9IG1vb3Zfc3RhcnQgKyBsZW4obW9vdikKICAgICAgICBzZWxmLnNhbXBsZXMgPSBfc2FtcGxlX3RhYmxlKG1vb3YsIG1vb3Zfc3RhcnQpCiAgICAgICAgc2VsZi5vZmZzZXRzID0gW2l0ZW1bMF0gZm9yIGl0ZW0gaW4gc2VsZi5zYW1wbGVzXQogICAgICAgIHNlbGYuY3JlYXRlZCA9IHRpbWUudGltZSgpCgogICAgZGVmIGV4cGlyZWQoc2VsZikgLT4gYm9vbDoKICAgICAgICByZXR1cm4gdGltZS50aW1lKCkgLSBzZWxmLmNyZWF0ZWQgPiBfU1RSRUFNX1RUTF9TRUNPTkRTCgogICAgZGVmIF9wYXRjaChzZWxmLCBidWZmZXI6IGJ5dGVhcnJheSwgYmFzZTogaW50KSAtPiBOb25lOgogICAgICAgIGVuZCA9IGJhc2UgKyBsZW4oYnVmZmVyKSAtIDEKICAgICAgICBpbmRleCA9IG1heChiaXNlY3QuYmlzZWN0X3JpZ2h0KHNlbGYub2Zmc2V0cywgYmFzZSkgLSAxLCAwKQogICAgICAgIHdoaWxlIGluZGV4IDwgbGVuKHNlbGYuc2FtcGxlcyk6CiAgICAgICAgICAgIG9mZnNldCwgc2l6ZSwgaW5pdGlhbF92ZWN0b3IgPSBzZWxmLnNhbXBsZXNbaW5kZXhdCiAgICAgICAgICAgIGluZGV4ICs9IDEKICAgICAgICAgICAgaWYgb2Zmc2V0ID4gZW5kOgogICAgICAgICAgICAgICAgYnJlYWsKICAgICAgICAgICAgaWYgb2Zmc2V0ICsgc2l6ZSA8PSBiYXNlOgogICAgICAgICAgICAgICAgY29udGludWUKICAgICAgICAgICAgZmlyc3QgPSBtYXgob2Zmc2V0LCBiYXNlKQogICAgICAgICAgICBsYXN0ID0gbWluKG9mZnNldCArIHNpemUgLSAxLCBlbmQpCiAgICAgICAgICAgIHNraXAgPSBmaXJzdCAtIG9mZnNldAogICAgICAgICAgICBjb3VudGVyID0gKAogICAgICAgICAgICAgICAgKGludC5mcm9tX2J5dGVzKGluaXRpYWxfdmVjdG9yLCAiYmlnIikgKyBza2lwIC8vIDE2KQogICAgICAgICAgICAgICAgJiAoKDEgPDwgMTI4KSAtIDEpCiAgICAgICAgICAgICkudG9fYnl0ZXMoMTYsICJiaWciKQogICAgICAgICAgICBwYWRkaW5nID0gc2tpcCAlIDE2CiAgICAgICAgICAgIHBsYWluID0gX2Flc19jdHJfZGVjcnlwdCgKICAgICAgICAgICAgICAgIHNlbGYuY29udGVudF9rZXksCiAgICAgICAgICAgICAgICBjb3VudGVyLAogICAgICAgICAgICAgICAgYiJcMCIgKiBwYWRkaW5nICsgYnl0ZXMoYnVmZmVyW2ZpcnN0IC0gYmFzZSA6IGxhc3QgLSBiYXNlICsgMV0pLAogICAgICAgICAgICApCiAgICAgICAgICAgIGJ1ZmZlcltmaXJzdCAtIGJhc2UgOiBsYXN0IC0gYmFzZSArIDFdID0gcGxhaW5bcGFkZGluZzpdCiAgICAgICAgaWYgYmFzZSA8IHNlbGYubW9vdl9lbmQgYW5kIGVuZCA+PSBzZWxmLm1vb3Zfc3RhcnQ6CiAgICAgICAgICAgIGZpcnN0ID0gbWF4KGJhc2UsIHNlbGYubW9vdl9zdGFydCkKICAgICAgICAgICAgbGFzdCA9IG1pbihlbmQsIHNlbGYubW9vdl9lbmQgLSAxKQogICAgICAgICAgICBidWZmZXJbZmlyc3QgLSBiYXNlIDogbGFzdCAtIGJhc2UgKyAxXSA9IHNlbGYubW9vdl9wbGFpblsKICAgICAgICAgICAgICAgIGZpcnN0IC0gc2VsZi5tb292X3N0YXJ0IDogbGFzdCAtIHNlbGYubW9vdl9zdGFydCArIDEKICAgICAgICAgICAgXQoKICAgIGRlZiByZWFkX3JhbmdlKHNlbGYsIHN0YXJ0OiBpbnQsIGVuZDogaW50KSAtPiBieXRlczoKICAgICAgICByYXcsIF8gPSBfcmFuZ2VfZ2V0KHNlbGYudXJsLCBzdGFydCwgZW5kKQogICAgICAgIGlmIG5vdCByYXc6CiAgICAgICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigi5aqS5L2T5YiG54mH5Li656m6IikKICAgICAgICBidWZmZXIgPSBieXRlYXJyYXkocmF3KQogICAgICAgIHNlbGYuX3BhdGNoKGJ1ZmZlciwgc3RhcnQpCiAgICAgICAgcmV0dXJuIGJ5dGVzKGJ1ZmZlcikKCiAgICBkZWYgaXRlcl9yYW5nZShzZWxmLCBzdGFydDogaW50LCBlbmQ6IGludCk6CiAgICAgICAgY3Vyc29yID0gc3RhcnQKICAgICAgICB3aGlsZSBjdXJzb3IgPD0gZW5kOgogICAgICAgICAgICBzdG9wID0gbWluKGN1cnNvciArIF9TVFJFQU1fQ0hVTksgLSAxLCBlbmQpCiAgICAgICAgICAgIGJsb2NrID0gc2VsZi5yZWFkX3JhbmdlKGN1cnNvciwgc3RvcCkKICAgICAgICAgICAgeWllbGQgYmxvY2sKICAgICAgICAgICAgY3Vyc29yICs9IGxlbihibG9jaykKCgpkZWYgX3N0cmVhbV9zZXNzaW9uKHZpZGVvX2lkOiBzdHIsIGNvbmZpZzogTWFwcGluZ1tzdHIsIEFueV0sIHF1YWxpdHk6IHN0ciA9ICIxMDgwIikgLT4gIl9TdHJlYW1TZXNzaW9uIjoKICAgIHF1YWxpdHkgPSBxdWFsaXR5IGlmIHF1YWxpdHkgaW4gX1FVQUxJVFlfTElORV9OQU1FX1RPX1EgZWxzZSAiMTA4MCIKICAgIGNhY2hlX2tleSA9ICIlc3wlcyIgJSAodmlkZW9faWQsIHF1YWxpdHkpCiAgICB3aXRoIF9TVFJFQU1fTE9DSzoKICAgICAgICBzZXNzaW9ucyA9IF9TVFJFQU1fU1RBVEVbInNlc3Npb25zIl0KICAgICAgICBmb3Iga2V5IGluIFtrZXkgZm9yIGtleSwgaXRlbSBpbiBzZXNzaW9ucy5pdGVtcygpIGlmIGl0ZW0uZXhwaXJlZCgpXToKICAgICAgICAgICAgc2Vzc2lvbnMucG9wKGtleSwgTm9uZSkKICAgICAgICBzZXNzaW9uID0gc2Vzc2lvbnMuZ2V0KGNhY2hlX2tleSkKICAgIGlmIHNlc3Npb24gaXMgbm90IE5vbmU6CiAgICAgICAgcmV0dXJuIHNlc3Npb24KICAgIG1vZGVsID0gX3ZpZGVvX21vZGVsKHZpZGVvX2lkLCBjb25maWcpCiAgICBfLCBpdGVtID0gX3NlbGVjdF9xdWFsaXR5KF92aWRlb19saXN0X2Zyb21fbW9kZWwobW9kZWwpLCBxdWFsaXR5KQogICAgdXJsID0gX21lZGlhX3VybChpdGVtKQogICAgc3BhZGUgPSBfc3BhZGVfdmFsdWUoaXRlbSkKICAgIGlmIG5vdCB1cmwgb3Igbm90IHNwYWRlOgogICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigi5pKt5pS+5qih5Z6L57y65bCR5Zyw5Z2A5oiW5a+G6ZKl5p2Q5paZIikKICAgIGtleV9zZWVkID0gX2tleV9zZWVkX2Zyb21fbW9kZWwobW9kZWwpCiAgICBpZiBrZXlfc2VlZDoKICAgICAgICB0cnk6CiAgICAgICAgICAgIHVybCA9IF9kZWNyeXB0X3NwYWRlX3VybCh1cmwsIGtleV9zZWVkKQogICAgICAgIGV4Y2VwdCBIb25nZ3VvUGx1Z2luRXJyb3I6CiAgICAgICAgICAgIHBhc3MKICAgIHRvdGFsLCBtb292X3N0YXJ0LCBtb292ID0gX2ZldGNoX21vb3YodXJsKQogICAgc2Vzc2lvbiA9IF9TdHJlYW1TZXNzaW9uKHVybCwgZGVyaXZlX2NvbnRlbnRfa2V5KHNwYWRlKSwgdG90YWwsIG1vb3Zfc3RhcnQsIG1vb3YpCiAgICB3aXRoIF9TVFJFQU1fTE9DSzoKICAgICAgICBzZXNzaW9ucyA9IF9TVFJFQU1fU1RBVEVbInNlc3Npb25zIl0KICAgICAgICB3aGlsZSBsZW4oc2Vzc2lvbnMpID49IF9TVFJFQU1fTUFYX1NFU1NJT05TOgogICAgICAgICAgICBzZXNzaW9ucy5wb3AobmV4dChpdGVyKHNlc3Npb25zKSksIE5vbmUpCiAgICAgICAgc2Vzc2lvbnNbY2FjaGVfa2V5XSA9IHNlc3Npb24KICAgIHJldHVybiBzZXNzaW9uCgoKX1JBTkdFX1VOU0FUSVNGSUFCTEUgPSAidW5zYXRpc2ZpYWJsZSIKCmRlZiBfcGFyc2VfcmFuZ2UodmFsdWU6IHN0ciwgdG90YWw6IGludCkgLT4gQW55OgogICAgIiIi6Kej5p6QIFJhbmdlIOWktOOAgui/lOWbniAoc3RhcnQsIGVuZCnjgIFOb25l77yI5b+955Wl77yJ5oiWIF9SQU5HRV9VTlNBVElTRklBQkxF44CCIiIiCiAgICB0ZXh0ID0gKHZhbHVlIG9yICIiKS5zdHJpcCgpLmxvd2VyKCkKICAgIGlmIG5vdCB0ZXh0LnN0YXJ0c3dpdGgoImJ5dGVzPSIpOgogICAgICAgIHJldHVybiBOb25lCiAgICBzcGVjID0gdGV4dFs2Ol0uc3BsaXQoIiwiKVswXS5zdHJpcCgpCiAgICBpZiAiLSIgbm90IGluIHNwZWM6CiAgICAgICAgcmV0dXJuIE5vbmUKICAgIGxlZnQsIHJpZ2h0ID0gc3BlYy5zcGxpdCgiLSIsIDEpCiAgICBpZiBub3QgbGVmdDoKICAgICAgICBpZiBub3QgcmlnaHQuaXNkaWdpdCgpOgogICAgICAgICAgICByZXR1cm4gTm9uZQogICAgICAgIGxlbmd0aCA9IG1pbihpbnQocmlnaHQpLCB0b3RhbCkKICAgICAgICBpZiBub3QgbGVuZ3RoOgogICAgICAgICAgICByZXR1cm4gX1JBTkdFX1VOU0FUSVNGSUFCTEUKICAgICAgICByZXR1cm4gdG90YWwgLSBsZW5ndGgsIHRvdGFsIC0gMQogICAgaWYgbm90IGxlZnQuaXNkaWdpdCgpOgogICAgICAgIHJldHVybiBOb25lCiAgICBzdGFydCA9IGludChsZWZ0KQogICAgZW5kID0gaW50KHJpZ2h0KSBpZiByaWdodC5pc2RpZ2l0KCkgZWxzZSB0b3RhbCAtIDEKICAgIGVuZCA9IG1pbihlbmQsIHRvdGFsIC0gMSkKICAgIGlmIHN0YXJ0ID49IHRvdGFsIG9yIHN0YXJ0ID4gZW5kOgogICAgICAgIHJldHVybiBfUkFOR0VfVU5TQVRJU0ZJQUJMRQogICAgcmV0dXJuIHN0YXJ0LCBlbmQKCgpjbGFzcyBfU3RyZWFtSGFuZGxlcihCYXNlSFRUUFJlcXVlc3RIYW5kbGVyKToKICAgIHByb3RvY29sX3ZlcnNpb24gPSAiSFRUUC8xLjEiCiAgICBzZXJ2ZXJfdmVyc2lvbiA9ICJoZy1zdHJlYW0iCgogICAgZGVmIGxvZ19tZXNzYWdlKHNlbGYsICphcmdzOiBBbnkpIC0+IE5vbmU6CiAgICAgICAgcmV0dXJuIE5vbmUKCiAgICBkZWYgX3BhcmFtcyhzZWxmKSAtPiBkaWN0W3N0ciwgc3RyXToKICAgICAgICBwYXJzZWQgPSB1cmxwYXJzZShzZWxmLnBhdGgpCiAgICAgICAgcXVlcnkgPSBwYXJzZV9xcyhwYXJzZWQucXVlcnkpCiAgICAgICAgdmlkZW9faWQgPSAocXVlcnkuZ2V0KCJ2aWQiKSBvciBxdWVyeS5nZXQoImlkIikgb3IgWyIiXSlbMF0KICAgICAgICBpZiBub3QgdmlkZW9faWQ6CiAgICAgICAgICAgIHZpZGVvX2lkID0gcGFyc2VkLnBhdGgucnNwbGl0KCIvIiwgMSlbLTFdLnNwbGl0KCIuIilbMF0KICAgICAgICByZXR1cm4gewogICAgICAgICAgICAidmlkIjogdmlkZW9faWQgaWYgdmlkZW9faWQuaXNkaWdpdCgpIGVsc2UgIiIsCiAgICAgICAgICAgICJxdWFsaXR5IjogKHF1ZXJ5LmdldCgicSIpIG9yIFsiMTA4MCJdKVswXSwKICAgICAgICAgICAgImRldmljZV9pZCI6IChxdWVyeS5nZXQoImRpZCIpIG9yIFsiIl0pWzBdLAogICAgICAgICAgICAiaW5zdGFsbF9pZCI6IChxdWVyeS5nZXQoImlpZCIpIG9yIFsiIl0pWzBdLAogICAgICAgIH0KCiAgICBkZWYgX2ZhaWwoc2VsZiwgY29kZTogaW50LCBtZXNzYWdlOiBieXRlcykgLT4gTm9uZToKICAgICAgICBzZWxmLnNlbmRfcmVzcG9uc2UoY29kZSkKICAgICAgICBzZWxmLnNlbmRfaGVhZGVyKCJDb250ZW50LVR5cGUiLCAidGV4dC9wbGFpbjsgY2hhcnNldD11dGYtOCIpCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQ29udGVudC1MZW5ndGgiLCBzdHIobGVuKG1lc3NhZ2UpKSkKICAgICAgICBzZWxmLnNlbmRfaGVhZGVyKCJDb25uZWN0aW9uIiwgImNsb3NlIikKICAgICAgICBzZWxmLmVuZF9oZWFkZXJzKCkKICAgICAgICB0cnk6CiAgICAgICAgICAgIHNlbGYud2ZpbGUud3JpdGUobWVzc2FnZSkKICAgICAgICBleGNlcHQgT1NFcnJvcjoKICAgICAgICAgICAgcGFzcwoKICAgIGRlZiBkb19IRUFEKHNlbGYpIC0+IE5vbmU6ICAjIG5vcWE6IE44MDIgLSDmoIflh4blupPlm57osIPlkb3lkI0KICAgICAgICBzZWxmLl9zZXJ2ZShib2R5PUZhbHNlKQoKICAgIGRlZiBkb19HRVQoc2VsZikgLT4gTm9uZTogICMgbm9xYTogTjgwMiAtIOagh+WHhuW6k+Wbnuiwg+WRveWQjQogICAgICAgIHNlbGYuX3NlcnZlKGJvZHk9VHJ1ZSkKCiAgICBkZWYgX3NlcnZlKHNlbGYsIGJvZHk6IGJvb2wpIC0+IE5vbmU6CiAgICAgICAgcm91dGUgPSB1cmxwYXJzZShzZWxmLnBhdGgpLnBhdGgKICAgICAgICBpZiBub3Qgcm91dGUuZW5kc3dpdGgoIi5tcDQiKToKICAgICAgICAgICAgc2VsZi5fZmFpbCg0MDQsIGIibm90IGZvdW5kIikKICAgICAgICAgICAgcmV0dXJuCiAgICAgICAgcGFyYW1zID0gc2VsZi5fcGFyYW1zKCkKICAgICAgICBpZiBub3QgcGFyYW1zWyJ2aWQiXToKICAgICAgICAgICAgc2VsZi5fZmFpbCg0MDAsIGIibWlzc2luZyB2aWQiKQogICAgICAgICAgICByZXR1cm4KICAgICAgICB0cnk6CiAgICAgICAgICAgIHNlc3Npb24gPSBfc3RyZWFtX3Nlc3Npb24oCiAgICAgICAgICAgICAgICBwYXJhbXNbInZpZCJdLAogICAgICAgICAgICAgICAgewogICAgICAgICAgICAgICAgICAgICJkZXZpY2VfaWQiOiBwYXJhbXNbImRldmljZV9pZCJdLAogICAgICAgICAgICAgICAgICAgICJpbnN0YWxsX2lkIjogcGFyYW1zWyJpbnN0YWxsX2lkIl0sCiAgICAgICAgICAgICAgICB9LAogICAgICAgICAgICAgICAgcGFyYW1zWyJxdWFsaXR5Il0sCiAgICAgICAgICAgICkKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICBzZWxmLl9mYWlsKDUwMiwgYiJtZWRpYSBzZXNzaW9uIGZhaWxlZCIpCiAgICAgICAgICAgIHJldHVybgogICAgICAgIHJhd19yYW5nZSA9IHNlbGYuaGVhZGVycy5nZXQoIlJhbmdlIikgb3IgIiIKICAgICAgICByZXF1ZXN0ZWQgPSBfcGFyc2VfcmFuZ2UocmF3X3JhbmdlLCBzZXNzaW9uLnRvdGFsKQogICAgICAgIGlmIHJlcXVlc3RlZCBpcyBfUkFOR0VfVU5TQVRJU0ZJQUJMRToKICAgICAgICAgICAgc2VsZi5zZW5kX3Jlc3BvbnNlKDQxNikKICAgICAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQ29udGVudC1UeXBlIiwgInRleHQvcGxhaW47IGNoYXJzZXQ9dXRmLTgiKQogICAgICAgICAgICBzZWxmLnNlbmRfaGVhZGVyKCJDb250ZW50LVJhbmdlIiwgImJ5dGVzICovJWQiICUgc2Vzc2lvbi50b3RhbCkKICAgICAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQ29udGVudC1MZW5ndGgiLCAiMCIpCiAgICAgICAgICAgIHNlbGYuc2VuZF9oZWFkZXIoIkNvbm5lY3Rpb24iLCAiY2xvc2UiKQogICAgICAgICAgICBzZWxmLmVuZF9oZWFkZXJzKCkKICAgICAgICAgICAgcmV0dXJuCiAgICAgICAgc3RhcnQsIGVuZCA9IHJlcXVlc3RlZCBpZiByZXF1ZXN0ZWQgZWxzZSAoMCwgc2Vzc2lvbi50b3RhbCAtIDEpCiAgICAgICAgc2VsZi5zZW5kX3Jlc3BvbnNlKDIwNiBpZiByZXF1ZXN0ZWQgZWxzZSAyMDApCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQ29udGVudC1UeXBlIiwgInZpZGVvL21wNCIpCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQWNjZXB0LVJhbmdlcyIsICJieXRlcyIpCiAgICAgICAgc2VsZi5zZW5kX2hlYWRlcigiQ29udGVudC1MZW5ndGgiLCBzdHIoZW5kIC0gc3RhcnQgKyAxKSkKICAgICAgICBpZiByZXF1ZXN0ZWQ6CiAgICAgICAgICAgIHNlbGYuc2VuZF9oZWFkZXIoCiAgICAgICAgICAgICAgICAiQ29udGVudC1SYW5nZSIsCiAgICAgICAgICAgICAgICAiYnl0ZXMgJWQtJWQvJWQiICUgKHN0YXJ0LCBlbmQsIHNlc3Npb24udG90YWwpLAogICAgICAgICAgICApCiAgICAgICAgc2VsZi5lbmRfaGVhZGVycygpCiAgICAgICAgaWYgbm90IGJvZHk6CiAgICAgICAgICAgIHJldHVybgogICAgICAgIHRyeToKICAgICAgICAgICAgZm9yIGJsb2NrIGluIHNlc3Npb24uaXRlcl9yYW5nZShzdGFydCwgZW5kKToKICAgICAgICAgICAgICAgIHNlbGYud2ZpbGUud3JpdGUoYmxvY2spCiAgICAgICAgZXhjZXB0IChCcm9rZW5QaXBlRXJyb3IsIENvbm5lY3Rpb25SZXNldEVycm9yKToKICAgICAgICAgICAgc2VsZi5jbG9zZV9jb25uZWN0aW9uID0gVHJ1ZQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgIHNlbGYuY2xvc2VfY29ubmVjdGlvbiA9IFRydWUKCgpkZWYgX3N0YXJ0X3N0cmVhbV9zZXJ2ZXIoKSAtPiBpbnQ6CiAgICB3aXRoIF9TVFJFQU1fTE9DSzoKICAgICAgICBpZiBfU1RSRUFNX1NUQVRFWyJwb3J0Il06CiAgICAgICAgICAgIHJldHVybiBpbnQoX1NUUkVBTV9TVEFURVsicG9ydCJdKQogICAgICAgIGZvciBwb3J0IGluIHJhbmdlKF9TVFJFQU1fUE9SVF9SQU5HRVswXSwgX1NUUkVBTV9QT1JUX1JBTkdFWzFdKToKICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgc2VydmVyID0gVGhyZWFkaW5nSFRUUFNlcnZlcigoIjEyNy4wLjAuMSIsIHBvcnQpLCBfU3RyZWFtSGFuZGxlcikKICAgICAgICAgICAgZXhjZXB0IE9TRXJyb3I6CiAgICAgICAgICAgICAgICBjb250aW51ZQogICAgICAgICAgICBzZXJ2ZXIuZGFlbW9uX3RocmVhZHMgPSBUcnVlCiAgICAgICAgICAgIHRocmVhZGluZy5UaHJlYWQodGFyZ2V0PXNlcnZlci5zZXJ2ZV9mb3JldmVyLCBkYWVtb249VHJ1ZSkuc3RhcnQoKQogICAgICAgICAgICBfU1RSRUFNX1NUQVRFWyJwb3J0Il0gPSBwb3J0CiAgICAgICAgICAgIF9TVFJFQU1fU1RBVEVbInNlcnZlciJdID0gc2VydmVyCiAgICAgICAgICAgIHJldHVybiBwb3J0CiAgICByZXR1cm4gMAoKZGVmIF9iNjQodmFsdWU6IHN0cikgLT4gYnl0ZXM6CiAgICB0ZXh0ID0gX3RleHQodmFsdWUpCiAgICB0ZXh0ICs9ICI9IiAqICgtbGVuKHRleHQpICUgNCkKICAgIHRyeToKICAgICAgICByZXR1cm4gYmFzZTY0LmI2NGRlY29kZSh0ZXh0KQogICAgZXhjZXB0IChWYWx1ZUVycm9yLCBiaW5hc2NpaS5FcnJvcik6CiAgICAgICAgcmV0dXJuIGJhc2U2NC51cmxzYWZlX2I2NGRlY29kZSh0ZXh0KQoKZGVmIF9icmFuY2hfb25lX2J5dGVzKCkgLT4gYnl0ZXM6CiAgICBpZiBub3QgaGFzYXR0cihfYnJhbmNoX29uZV9ieXRlcywgInZhbHVlIik6CiAgICAgICAgX2JyYW5jaF9vbmVfYnl0ZXMudmFsdWUgPSBsem1hLmRlY29tcHJlc3MoYmFzZTY0LmI4NWRlY29kZShfQlJBTkNIX09ORV9CODUpKQogICAgcmV0dXJuIF9icmFuY2hfb25lX2J5dGVzLnZhbHVlCgpfQlJBTkNIX09ORV9CODUgPSAoCiAgICAne1dwNDhTXnhrOT1HTEBFMHN0V2E3NjFTTWJUOCRqO1Itd057I15ob3VmN1FJSVZVNzxFdyo2QzM/JnZRUjdgVml4TUlaSDlIeXpTUk4pZGd0NUhzT0ZsKSpANmhTeEdtcTVhQScKICAgICdRcWNUSj51RVh0M2NhP0ArXisrODxgdmRXYVMxYSFeKEAzcGlITl5VRGVhXnV0eiZtNjhQd0spbGEqNDNVKm1OWVR+QXozdldSUjlNQHU5JWA+fGBvVHVWQW17NlhiaTc8QntMJwogICAgJys5JX1Fe3tSNHRXO04kaVR1dVBnSmB1O3RaP3FFIzZme0omZ017emxvQ1hab0ctaHF1b01qI0kxc3JZP0ImfnA5eGdiVXpiQCE1KjRTN21hJnkjPmlVb1cpNnJKX0JPeUxJcEwnCiAgICAneE9EeURFT0hEVXkpSHJeJGhFRW9kRCRoYkdyWlFJRXU4YFRiX0g7flo+Vk1XS1c1fnAtaE9OdFpKb2kqdSZ0Tz1tNjkhWj5WN0VgK1dgRiVyQjZaYD45SipTSiVBenFnbmE7aicKICAgICdweUx4Wmk7eWNKYU1+ajxvJUh8NyF3YD9ZeUVtN2k2cE1uV3h1dzR6YH5CNlVLUnx3WUAyZ2w8aVhySkRke18xKiRxcDtpYk1OfXhJTDwqR2kkYUlfVG9POG5pRFp8VzZ1ejEhJwogICAgJyUpT2Z1M3FmUnExaDFwX18wZ3x2cUcoPzthUDc2I2AtKkBXc1RiU2M5OCFBTDgzd3RfNHFeTkhxU2tZP0Qma281M2lfe0Y5bn5sX3t4XjVDe0h8Zk1BSVg0ZmB3YjdFUmpaM3knCiAgICAnKyM7Vk1IdTVQPUp2MyZ5cF4tQVNEVFhZQyUkVHhON24/ai09eHNZMDY3NnlNUSllV2VZa0czSkQ8Pl8+dHtIaEFJeENeNCg/OCZWY1V4PXV4KHFyZ2NJQVhVNVlvc2M/ejEkKCcKICAgICdGcWZQfCkyJHZlKCZ9dXc7KHV4ZE8+RTZkTU1uXmA3OWVUbUNfQj1xa09CXnk9MUE4c1FpPE1nV35mRGRXMHQ0e148SWpNXko/eDwmWjFNKXBZTyZ1RUEheVJ3P05wX0VvaXtvJwogICAgJ1Y5ZEQlVkE2eCpnPmojaDU7NH0rI0lMbn4jI1FoNVY4LSVsYENnY3kwdTdEUiFOJDA3UTAjQldaOWljUDxhNVVpTCpIUyNpVztRaVJ7KXV0OCZjOWliQ3RSXnMtaHZ4VDxCNUknCiAgICAncFpGKjwzTXo2ODVJezVCbjAzZTdAJkQleGVhMCtvQmlJPSNBeV4zOEQzNzclPFF1TVotTyolVHY7OHw9WDdrQEJSOX5tN2lFfEA/eCV6bFEzTkU5NjhTOytZQE9LVElPMW5SUScKICAgICclJFBsbUcyNkVXRyZoc0woQThLdnpyKlM1QXkmZ3dSXlFzNUVQfGxtSmM7NmVYezUrMz4tVzNQXlhRWVkpfFhhPDV2JF5gcHxuYVZMV14qNHg+b1RmJH0/MiV7NmJEfTtse3dwJwogICAgJ1VYeCY+e088Sn54fXw+KCFWMThwOTN4QldfNStII3lldTAzdlJqRVNMWEQkQTl7eVZRd2opSShOb2hPPk9SclRqUEVBez9EQVUwZHhTWCFLNzQ3MXtNY0hYd05pLUg7bypmU3snCiAgICAnQV51JT95fEdIIVJqI3lMdUx0YCFvPEtmKVkoWnBONFR6MzxmT2AjJERFN2JGLSVvcURzdCozX0RXZzhuWmlFZkwwT2ckPGk5WFJnc3g/Ml5HPnR7allMWVh8YSl0QUc+fGFoUScKICAgICcoQ3ZUNHI4bkcrZTFjPVVTNSM8OzRxaWVRS21GfXYjTGlyNUV8ZG8/RGhOWkRTYTMyZHw4SkAramphJlBHI317cz5RQXRXQFBWJFU/cT0oMVhFOWMjViRfd2crYnAmViZCKWVFJwogICAgJ3d8RTclJkA9Zlc0NiVLUVR8aHgtNiheN0A7R1NBdVFpVkFLV2p7JD1OPERrbytUdV5+Jl9nNGsmdFd5VCtSaUFCZXMlY3syR2xaaXpufi1tbCVsJkhlQ1E3WTg5eyp7RmhGSiQnCiAgICAnJUEwVDVPazlZVHFVIVlgRk9EMFZsbDw5M0dBVXZFd3tmIyNTNU5hQF88Ji1nXkM4O1hOUDtKbnM0UDRgOUcmT3VWeTlGe3llfTlwWlhGQkdhVns5R3FXc2VGWFhEa3YtSnRyIycKICAgICdYYHY1KjxWfXU3V3pBQExsSUl0cFYmTCVEbnUhQmBUbHpeZk8kfCY0RWNyXmY1QGx8UGsqP2xgUTBrYD1gKEo5fW1UUCFveFhLfDUrZz5pRmFWfC1edDs+VStlKnB9cFV4c0dnJwogICAgJ1I8O0NAQTxAI0I/MWJJZGckeUkreUE2QXhZMjNjUGExMkE3OSNGdikhPWgwTitHUnMwS2cwNzhgfUp4NzZra21GMj83YGZVJEx0OG0zQDU+TFVwNylNY2FPRjMlbGVKUU1BKFYnCiAgICAneiNqO1BDJE4hMll3aURwJEZkWkUzQjYpYU5CWVVhKFROYW95OFh+PWJ5QkhhYl4qbnY5JSp9UmY1NGNhX2IwQVhvUl9HM2FANlEjWkZwVV42P34zUzkmbnxveURUPXkrLWFTaCcKICAgICduX0BteHEwO0trSXtOND1hT2owdy1HO1QxezV8alVrfnJwWXV9fm4meGVYT05Se3hAdz13eG9Jak9oM15jd3A2Iypfek56S3dHbXQlZ1M5cj9GOGNNaktUJGxCfGJyKzUxeUIyJwogICAgJz13WlY3Znk3RHtgKDI5I2A2USNRSWElaG0paXM+S0RfcnkjX0gqLUYqfFo/JVF2OFdyakBYPWRve3A9KngzRnpAN3dTN0AwYn5+LW5AVWZkZV55THF0UUNtPzBPYERhNm5uLWonCiAgICAncjlQb2cyZmpBRndZPGdlbGAmISskREFORExaZmBJS2hnNEJaR1BkRVlYMW4hOHJTK2dRN2xQez97S080NXZzVXUyZFM3KitsR2Jjaz9MKi1nOTFtcEVhdiVWJUpZMTttQDdiYicKICAgICchfjgqQChQbUl4JGhNNClrUUQjLU45bF9zVThVcFF5cTsjITJjUjY0R3I5fTNCSW1xVihQIXA2dXc/SyVFXiV+YDJGKlAtV0lRM3V3LWtJazRtPDhAUllGNVcrWGhvUXhgcDZrJwogICAgJys5SSN7RX04PklKa3lRJXE2NDM2bkY5dCNMc3o7fWIkaHA1e18pJF9Ed1plYzhEJnhKcFU0IS0oc31iMTEyTklLNzJYdHZyckdYMjJ9eX4zX2lyb3smTW5oRVRBK0RhSz9YaSgnCiAgICAnUTBKXyZkRmVKNSM3Zksja3Q3ZV5lQGMxRDdpT3NkN1kkfndzUlRKI3FpfF4oaCN5V2QyfUZJVThCOUlHXno8WDc0XnRPLTZ1ciheQ1oxM0FXYFVGYkN7UGUlQClvSU40NU1xSScKICAgICdQSGRxOUQhS2J6ZSpQP2ghT0MpM3FpQiFsPzQ5V1M/KXJIdm9HdEZ4YXBgKXcxPXRmOEFNUTVJZnJHMyE5Kih1UXA+Ji05MDcpKihqIShxWGppTGJQXiN9QHx3MzNrNEZ+YDdtJwogICAgJ0t+ZkxiUiVkP3olaGwoTSpNI0I2KStleiZEMyRKRFlnNUFGMnZETVBFRTJHO2R0LVAhZ3RFIXFhSjQxJVRqeGdoU0BJQlV3VUVJYkJCfEFKND9ocX1CTGF2SitefEZec0U4MG8nCiAgICAndUxBP0I5Nm4hWWljKzlqV1E2YmFMeHwrUDBCakNLSlA2Q21LRHQ1R3NzV3Mxb2VrSEc0aWZ4TEFLR2AqZWJhRT0tNWtvYk1CfVB6O1IwUkVxTi14fXEzJVckQipqQj9Fe0ElQicKICAgICcyTWh6SzEldW91bXoxdHBhYHs5Y2pLcWdZbyhAMXx6KE4pUGVHdklpYmxuPnJrU0FsdDtAVGpaNDZtVkUtUHhPUjE7OzBEbG9wcHlzWVpsPGxpS0JSS1J0PzkkWVBhOyszVH1PJwogICAgJ3RrKDJyQ3soZFpRYHltK3JxUF58d3IwT0k+ZTZHfEEhUHw/YkIxVDd3Q2J6ZjAxdChuRVVHckZXamVNbHJhWn1+TyVYbn4zU2BJaj8zWGhaSmo0NHJebj1eVjErTiY0bGJ4R28nCiAgICAnMCF4KUB1MU9oMkc1NThLem96X3hSdl5AUitTZ2BDejdHKkhycnU8dSkzTSZNSGVhclVvOCpxPVRtfHE+RiNkWlcyJkBHcjVIN3dYcyZMQXo/NHdFN2BVd0JUUmtlTVktdyZ+eCcKICAgICd4WVB0PWJ6Zig4OWZmcGVSQGRhWkJIPitpJjlBUVh6OEFnPlFZfilDQSFjbUhnSDxBRGF2aVopNWRZSnVqK31oeGxIYW9uaGBsekUkdnxUWjJGP3R9MWlLNnczO3h4M2lgazVFJwogICAgJzNmVDgkaCkkOWdsNTlwam45IVd5eShDaVNtKWZJVHFqal9IQzZiQip4cU5VVkBGJV47QUpHeyZOI3VwSHopcXsyZUd0SnszVnQqfj9uNm1iSTU/M3R0JiZramxTXkprYDVBS2snCiAgICAnc3RDJkYhfWV2Jih5P3cmQmojcEw8eHVGcVpsZ0NQZEE9P1B2MFN0NUM5QGBwXiUrfT5QVmBDTTQmV1hpQUE9cCU7SFNFXkk4aHlIYkBIYkpsS205KEI8JnJ2eElkV0ohUmFgVycKICAgICdoQlQxZCN7ZSM+Y3o5eTlzVTlaPkZENVdodT9kanlkJHpeTHNAbX5yc18jM0EqViQ/aEZsbU82cDB1en44d1AtLUwrJiNUOS1YaVhLSjRBUSU4cjBqSzFiNmgqOVdpJC0qNV9sJwogICAgJ08jZ2chSyV5JXVtKEtuUm1PKT0ySmxjRitYfWhQN0due3ZAQVcrOSErP0Q0JnMzZHp3Sj88fTBDekZzSHcpSWBxQGYjeH03JWcpU0N2aVI9ZCVNIVJtdTBFNjQpcDgpb2R+SjsnCiAgICAnYHVBVngzaHgoWm1UJlpCNUZOXyNOLVM5RW8hZyVHdXpRYiVib2ExQXI1UkhrVCp8P0ZEVDUzMHJ4YnhkekF8VVliMHdTQm0lN1FuQG5lZUBnej0+eFU9PHtfLXFTZnc1dWlMOycKICAgICdNdzJ0QFgqSUB2NWd5ZU87QXp3XnZucSFqWkw8ZWVDI1lHb3lSJUZGR2dLeDc+Q1RZJVl7JGpFblRVaG1sRT52V2EmeFJeZGFlSWd0UFM5dEBVeE0rNUQoalF0UV9LI20+e2lVJwogICAgJ08/TChMc2szPCZLJlVtcyFWNCghMHsmNnpAIXVeMEklMmlrdk11Q3Y/TSVvXlJVNGlMOVVsPVRxYFFxQFl8Z2x7b0ZWflBnezMhdCMwPz5QYl5AZnwzbytEa2NMM2A9VSYmOTknCiAgICAnbjFpcFU7ayg2JE56MjZkMytYOWtEMlhhOyk7Zj1xbWBpVDghQCZRdSpjSjVpX0BIZDtXNE9OMiNeQH5ydHxvaVJFcGQxemMwZkx2TCNkKChLdGE2QkkzdkFuLVZAeFpWNj9ndycKICAgICdCRis+KiMzWnZtJGlaMCYqTDR4RmY+UDY1RnNAdyYrQyN3TV5zNDFsUkpsVD4zT1VLK0h8Xk0obHtnbXJBbSMqVklvKkl7KTYpYE56cjYhbm13IzdsO2E9O1RuNmx5MnZTNz0hJwogICAgJzR+ZkVfcjkpOSYkN1JuU21hVUhsZUVNKWdzR1IpVWVQSTJaO2V3TzA/VXs0SGpeTlNwUD9aS1RTMW55fiN1cDZpKkp2TUlCeGZqbTYhTEk4R1dYUylfNH5HUDBUY2BrQFJIbGInCiAgICAnP0gqeXowUm8rJVJgSnx7SHRzRSV4eGJ4fGsqezVvX3haZkQtNGJ0ZXJ1Q2FoMWVwQDF2bHY2XnVDeTF9YHtmcFc0MkBgK011O1Y/bCR5UHVqZD88fGRnKHlYbkVzQykjMT8oJCcKICAgICd6S0khKVdKe19vLSt6YCU+Z0BHQ1dhfXY5ODFofHd5R3g9JW9ObyQ0R0NaR3M2dC0kbXl7Un5+VlQpLXx0MHhPbUZIKm1HKn56Z3MjdEImUDtabW9wUUN+XjIlaz57MGQ8cH0zJwogICAgJ3lpdVFVI2tsJXFNQEpAbzFzJDA/QUkkK2FgdHVSSnRWNGgyeENEYU9NQTI2NipuTX1FMns7JEpjVk1PVGRsRXROSnZAP0ktMkwlQDJxPVZDVXJ5c1dNfWZGJWlhRDBlK3B0KU8nCiAgICAnOGNEVlNpJGowOTNfM1gmQkZMYmI8ZWhqLT5Jd2ZafDhoa2M1NnRuaSYyUEJTcGYpPmh3M0M9ei0/K2tRYiNkMjYobzE3YXNrcT5XNFByfTswIUpFI0BzeE9GOW15MiloPDtjYicKICAgICdxVDZwRyQlazYrZj1GaFdhbTl9Y1FSWFpONXdsVSQlVTF2Y1p7aklyaXVeaCgwTSp4UXJtfmI0eHYrQSkyKmh7fCpPVVpIUnN8ZnwpR0VLYSYqZ34pVzJUdFRAc3AhWWl+SnA2JwogICAgJ3dqJHplN1FoLW5uLWQ3Zio8VHZhPjQ7O0ZoP0RgcDFpY1M4NkYqaUE5enRqLVdEJD43OSVnc0IjMUZiR3tfPjVMc1lhP1g2OUA4czN4ZHtiRXI8Tn4kWT5gNllVMCN1eDApKysnCiAgICAnXyVAcDFXflN1OG1JdSZTRHlqbiFHNVFyfDhLfE5iOX1KRkpvalErNnBeO3crdVQ2bG55S3RaUz0zZWxSKWBobD5uRlZfczw2Xmg7KygzKjQpWUZiO3VQaDJzRSg7eGt3PW8oeycKICAgICdyWXRONFNAemR5Qjcmel9hV1FaOzAlMEUqNDhNYEBhQVRFZFJAVjEzK2o7NVloVj9uaUgrVTwzSVZTKWtsfHY+bjtUVTZFKGpHODRtXipadDJIRiV5WjYwOTIxcjI1d0FvZXZVJwogICAgJ2Zta0A2RmhHc0lsTUsxQ3NWOEptND8+LX1zVzRuVV94b3Z9JWF7UTswR0JsPislLSFyNGA5bXJPdzYhRF96eTNLd2E2Xn5yQ2twXkExQzF8LUp2Kmw5TT1wKHRvWTY+anxYfUYnCiAgICAnJkoqVy1FJExvYEsqTmQ8RW9ITy1UfTI7M3Nhb2MkaCR+Q2dhP0QyPComNUhnNDZ3VjNeJnV9ZUpoa1h8YWdrZVM4O0NCSzdpVFhNbCFAIXozI1hmMngqeipuRilCN05eVT1WeCcKICAgICdCMX1YU1dfeiR0SmhyeCooRG1ycihacGU2P2JNb0VVfUhkJDVucTAyZDs4QlVzRy05IT08R08wUnxeaWIzcCswJWB9eXVfdn5KI1UxeXB2NXlrPHdKPk8qKmVCflRpWWBYTVNPJwogICAgJ2p3ITJ0Z0VARmNiTlM5SFJpI31ncyo+Q1JXVmdqWitXSExzbE0lTHt6TGxYODxPKlUqa0hUTzEwYktRIXJ6KChVJSF6dW5teyo7VTR2YGY9dGtpX0dZU25fKFdBMlE4UD1VazcnCiAgICAnWVNOTWB2JEN7VF5OUiFIeDlhazMyT2Y2RVFNXnZpcmsmTXRfIWdTQ3dwdHxjPEJ4N0woUFFvVnpRJHRwKjEkUW5fO3djfWd+eXp3LWR1RFd1aHZgX1NRO0A7Vylzd01AbTRWYicKICAgICdXOEFlelZuI045JGVZSFo+az5VQUVyZkc+ejZJSTJ7MWMtTkwxR34pSV5tPiM2PzYlPU5kY3hWbkQjbmkzdVd1aSlqeDlDND1XfmtMWXxPZSpiZXdTfE44KiFBfCN4KCQhK21SJwogICAgJyZnYURVe0EmZUEmVEp+WHdRYEZsJU5yZFg0SVMxMHVpMmBXZkVRfmJIZT58MGt5OXI7UWVLYi0+V0hCYGtQPForLXJiLXY2JTB+M203P3NpYCgkRFAoVWdWTmJYc2NBLXo3VCYnCiAgICAnQlhxWXxxWXArNXM/cC10VjlLQVRgJUxwJjVGRyt2ZCRLc08kcT4oQitiWjxFaX56ciszKWJ0UDg+LVpWIXJ6T3RQT1p0OFR6cG45N2VRK3dMaDlUbCEpKXh6ey1iMn1ra0UpWCcKICAgICdFSkcxRzxBMlhqZyl+SWU+M0lQSlBEO0k2c3VAKjtOKH16IW83K2g+Y0Fse2pFY1oyPHBGcmRoY2JLLSZJJTghaUFTQX45QmB2RHpMTjN2V2BjODgzPEJUJE1eZ1MzLSMmXldJJwogICAgJ0xhUEdHR3xFO3QmZzQ2KWQ7QEJsTCZZKjNUU35Gb21veHlZJVZ9UGs9IVMtPU1WXntgXzRIYk0taDlZcDhUQypaMX0qe2w8IVUpUFlMQGpjQD0taTB7UUs2e3BFOHkzQUMjYnAnCiAgICAnbDl5ZHcxYnheYSpAQG97RXt7bG96UXhtKnpiMl87Jjl0KDc/WEljcnBYJChfenh2Y3ZHRT8yKDRwTUcjLV9aJSl1N00oWCM9dD9WcURVbW54JHFrUHg1cDQzJmVLfEdAZTtFKicKICAgICdialFMSyFVJSU2VG91I0NaandufFctVHxQVH1BOExDUGEoTEA3biUxbT5sZkNKM05lME5LREJHZ2l0fUxZb09TbXNsMWVmMFBFbGxtaipASnMjcjZ3MDhMaDkrYlNlb20kXyohJwogICAgJzV8cjZZNER4fUpQYXBDX1JBe1ZBVHwrWnBLRUVvQUA0KWA0UzZwbUNLR1NaVFRyUk5SQkBWNy11Y0RiRzRuTV5vSmxBKWg5N3NgaD5+YyZpQ3syaWchZDEjTXN8MkVwSTQ8cGcnCiAgICAnNXtrK3VhcFViWCYwfCQ5Nm8rTFUoVkkrVllqR3RWcUlWJFVoM2A3SmlBP25ZVEFpYD5WUytiRCtHUyhedGRsNSt4SzZuSigmYjV4VX5vd2kyd3h0Snd1UWZaTTlNT3d4MFMmWScKICAgICcwTXx0Qk4xUCtfU1kjQlNDQ3dQcVU0a1c3VSg4YzBGJlc0bkYxeGNBOTFmKUIjenp7Z0wzKiN3N2l6aG5xPipvLXZje21MQTVRVF5ZRkkqcmkxMkErR29UKCo0c0R8O0RpM0w7JwogICAgJ2RkdkFtRy1sLVg7WkFWbzV4ZmdNMm0jTGlwMlRmVyVrSj9kKnRBSkR1bztCMEVjV31tciRkK35mUUk8eyFpR1FlMHx4YXRFfWVVNHc9c3ZCcEhSPGZQKDZXb0Z5JkZUOE5HVjgnCiAgICAnKCZRKzdZOyVtYndEWHlBdE1qeyNeUlJuP3g7OGNSdzNfU0tPVWhRWWEhK3ExT1dxSWxqKUpack9UXjF1JEJ1OyRZezNuRXljNyMoOU9lbHJ1cCk0eXg2d319Mm5KUkQ0T3wpcycKICAgICclckJ7XytuZmRLNWVOZGNCV2BaOUJJb2QrSU13c2NsVXhuKCFicDJQMEM3U0Q4X0VBMXErSUJpa3l1VEhFeXchM3h1SUphVHZmYjhjN0VQY2dfMVEhQ35JK1R1YCRkUV57dEQ4JwogICAgJ2dVUl5GQDt8cFZJKD45blY5TDRjdDUtRUcqUTJ2T2g3fFF2WUBmc3UtbXg0PSkyJFcmSCVCdio2UGtxbyFYKXNHVWpaKnc/KCRjbHUxQktOUiFjdm0mbF9BNCFRYU1qSDwpfDgnCiAgICAnbn42MkstOSg3blVHdnVYKTswUUZ2ZnNqX191aEk4TztrZGY8TDNWKklQUnp6REhmfGx5NVIrWSR7IUVRRz9QcG1MbVpjeTdue3U1JFVhMFF1SSgyeVpzcTtxUFZkQ31wZXFeMCcKICAgICd6PEBwanpzYHtzQXE9RWlHdTladSt3JFpHMHNzKDs1MWY4YncpZGk4N1piNXYrTmc2N0RmYVNIPUlPXjtBWWk2dGt0XnFVSFI7N2coaz9WZWZ1YF54b1FONCNVKSUtSkI7OEVNJwogICAgJ2ZRVGBhRyZIYExGb1I4cU99MmJlXjZgZ21NO24/SF9UVTlPNE0pQkU2KHpOdnh5JnREUUtLfVJAR3k/YThydlU3dmhaJCkrZWkjIVFRSitHanlOMXxUPSlLLSVGR0hRQX1NKCsnCiAgICAne0NLK3h0NFIkWVlnWVBrWisoSldpTzRJd1R1bXFEK3ZAZj89KXdfQ3ZmdFFNYT5URmtnT0hlQHFPbkZSU0VKdFhVSnB1K0xYblIqTjR2YFE4M2wye20xPCE3Y3Y0K2VLelJwVicKICAgICcyKCR3PFFKLTVPUGVRNlNiczNgb1VzZ28tU0lvfWBhTUk1UjcwOUV0fDNrYnd5b2hLdHFra3k4LVNpTlUtZyY8WHFpNXgmIS1IaE9vTnc4bGYzZ1J9SGdJQ3hWdmlfI2tTQzkpJwogICAgJ3dCIUF5K1Y/b0I3N0dyM3FDUVBFcEZgc3s9KyV7fjc3TShReiVtUz9KJHJqOFJJSmhxKmt+NEtzbnZCRlppKUYyPTxqOWJ2O05gY0s3MXhzZF5VPSlgaW1mT0d2T0k2eUNMOXQnCiAgICAndSZgZVhhMSNTPnB2c3BVKiZVUkVwYWdDdmcobEtrbStqbEtpbn1wRlZ5Y1hFNkwldyh2SCYxfWJhSTloQndwemk+STxjM3Y+TzQ2Njw/SVBiWlE9JEpSfnc3eHAqaypWRmFjZCcKICAgICdFdiRCQEQrUXlrc1U3PTY+N0wlQCV7XzUwU2o5JUBYemVBQU9xaXA9I2ZxP3lrbjRxKTIofEZ8P0huVVY1O0clPmxHKm19QXU7eFBGUTQoK2o7KS0xU0ReOUJ0RmpFXk8/en13JwogICAgJ3VVfCFtNkh5I3oyTT5VYmxnVExlYUYlYDhmMTZ3a1Q+PFVpK1RTcH1lNzBZM2w2QFp5d2owRHY9dVFkKks5P0tSYWcteUxIamkwI1AhYHB9PmZuS2JFYj9lQGVtfnM+WHR0eUsnCiAgICAnKVRjZUtIUS1+VG56e2srZ3JwaS14MlQ7Sz15TV9eJVNgaURFZSExe2xqJWchR350ZFBJY31GMVY3bjh9OE5rKn53MjdTUjcwUksoIyMhQlpeQEc2LVhRRWI8WGpDbXlKZVd8MicKICAgICdYWDA+OXR8Myh1Qkc3NGFDJjVnTWg8fXxfTDhAUnJPdnQxcW5eS3lLNUAqZUFFckRNTWF8SDRtbHBlWH47UEBFSXdeIyU4JEZzM1cqNXlLIU8qaHpxY2ItXkBwSG14YllPP2k3JwogICAgJyYlNHghYz5lX30tRjxuV1JoQlIlMz0yKXh6Q0hzXns8Szd4Km18PDMyNiN3OSF6YHllclcxfXhlNVVYdWk/QTJlajlZR29YJWdUYkwwM2RUIShFKHNmPiVHR1M2WjN2JWJxQTknCiAgICAnNCZkQzYoN0d1UUFhTzd7PT5yJTBuWEBRKnRjJVFeYk1FNXghXm89OWUyRFhHbVJkVj90SypaZWBVKnZkXkNjKWk2Rz0lMmx1NlNBMzI5ajQ0cE0zMjM+UX1hVzZPfVRJTn1QSicKICAgICcoWV5FS21pQUh3dH1aZVhqO0IkKVA7VzNxR2pmKno2Sz5SNntzNHVmYWElJDQ3ZSZkMzJhezclN2BePWFsajxOUGhaQGhyemh3O2EjMThYISN6MztYPmxkT0lvXzdfYDlQTWZWJwogICAgJzw4Nn45UksxMU8yRHIyQFZmZXFKKWljRXIob1Zoe2pyaCo8R0VvSnx0dHw1Xkw+bzZXN1pOQ2Y4am8ta2E/KjI8dipBcnZXPzI4bHMpXj4+Yzl6V3o0fHBKXiRjb0hfXzV+fT0nCiAgICAnTWopMihzI3BhdzY5Zns7KmN3MkohcXVyTXs3UXdhISRub041KTxZIzFpV3M7cThVQ34yb2JoPGEzPHQ5THlFZ0V4cTx5RWZUNE1tKEMrTEUkbTZzMyRWUzliS2tmUSlFVzB8QCcKICAgICchbHlzcENkR2R9Kn1MeVNhPW1vfWxtXlU3OyVoYzZfYipgaypBPlBUY3ApRW9aaFBAKU15anU/enl9Y3Y2eDBkMEorZ2R+Ny1CeWlzTEl8Tz5YfjxYXjJiNyt1eVg/Xnd8UXkjJwogICAgJ2NvZDh4dFR1Y0E5dVEjQkVWT0xYQF5aWkpEeW1eVEEmR15VT2QtQk4zJmpGTyV6cGExcUFRQlEkMiRLd1lGTDdnbmM/MXxOQ3RCVSljNWcqK3krTz85R1BuJTBCUHZ0RVkmWmsnCiAgICAnWTkwNkxae3Z3RUQxKkFLNXBHVUYpZSEqZjBGUGdEKEVjcytGMFI8KXFxUmspXldjckFoZ2FfZSNRYUtVNzt0RE1qMFFpMCl5Q1YhSyZBJn1WK3pZeDl3I2FUSG9PejZXc15OTycKICAgICdlfUBMNXhebGR6QGtfbVFNOT1kaFN4WUZyKksxcGRGJj1MUjNGVFF6PW0wckQ+SEN0SlJPJT1iOTdQM009aVlvUjk1MDFFK2Z8emhrZGpCLW1sNXVsWUxKbXkkO1h9KUpVJCszJwogICAgJ3p5TlQ9c3wmWlBiXiZSUm9QRTdXeXR6dF41aV4taXlPRlFPezJuMU1qQXI2OGkjbFlqUU5aPjQ9ZW9vTCt6cE0mRTRKa3Y2TjZBS3FEajk8ekRBOHZiPmhFRjJIM2YpRWhxcGgnCiAgICAnSSRgJjE5fnhwfEt0aFFLPjh0fERPQUYwRnEmQVVuVE11ZjZRYG5gVnNWRShfNEx+RSFjbH1GUURnPVcrQEhJa3VjSTlRMiVQWT5YYHEpN1AhbGY+ZlBtNCZ5WDUmYSViWktFeScKICAgICdtfUZScnhIZyFsMSR5OXk8ZVZ5V1dVTFhsRG9DMmojQFh4bVhHTyswRj5TcyR1a2omfnR3QjtwXz9oQWFiPE0/QWNYOEtFMj5RYH05TWd0OVkyM09GM0EmWF8+b0dpPG4jOyRqJwogICAgJ0JFWGVuejBAaHglNz8rMSRTKUAoXyYmTytnOHg8fkU+R1hUPnRVZT5MQUd+NmQ3ez4yPVZBPyRqMnN2bWpJOUxuY2FHVlhQZmpLe0o5ZkRLSn03WisoNyVTeTs8Wkw+Wj9nO0snCiAgICAnN3JZcXxjTz5NYV5BKCFmc0xwY2BPdigkODUoPV9hSlRjSHo+dmZ2aik4TEliX3ZrZXFCamRpZGRhUWwkQ2dzQDt4QWtALSVwalo3O1ZuSUZvRDd3ZWNjNDdQajxSUG9rRVU9dycKICAgICdre2glSStHPlM0ejxBT3w7aCVrOGBKTGg8PjgxRUxzOH4jdTFrdTh5QDQ/MUV6Un1+RF4xWGMtXloye2A9aE1sQU5ienN7bzYjQFMyVCFfLWJeflZgenhRNGtLQl5tSEYqO3IqJwogICAgJzZZQEg8PENzSmEjT3E5O1kqVDY2LSsoT1dCT2IqfiQtaEdZKEs3I2c/aCZMVVBUe2hVM1ZUNioyaTAoK3VpUm9VcyZ7cldiNz95OGMqYW83PDhxbmwlRkAhM3poezhGYCRHZyYnCiAgICAnYjYqKWs1ajY+ZCZ5KFdmKFkmcTh6eXlLQmx2eX1fWSZJeyUhZiMkRGdyc31GPlFHaCpobjJ9I1dOc3Q2IVE/d3olcDBXNm5qUj4+Y3o2YStObzwwdlMhRz1OITRZXm8rcS0qVScKICAgICd5RCRAcCFpfCRJQGB7WDt2MWZYfGs1eipKe1RhTDhSS2IpVCF2cGlfZ2QkP21PU2RHKSUzcWM0aXg0NlNmUDtlWk0jSWkoKD0rV2UhJXNLcTNVQ1htRUVpYHtlWTsoYHJtZHFWJwogICAgJzk7KHkxezZuaXFXaiQrelBlZzQ/TVlfX0VSZU98S0dqMn1JJU5PYkJtaUVLeHtDQiFvPVNJdjRaVTJLSk9NaHNeWlFxYnM3b2JsOV58OCl7WHFhTnArKDAzOSZeMDAwU2FeaCYnCiAgICAnMjQldTFTR2R7WDtfJmpofDFefHozdCVMLT14UCpWIXUld19gJEllZ1V4dj4zOUBrdSthSmlDcTFEeVc2YXlse1NMVVZSMjY4e2NaNyRvaChZaH5wQWFiQzlDM2A+Ql44aTNqdycKICAgICdjZ3lhVDEqZCU7ViZ4Mj9RR1pTcEp5TitAN08/V18peldYTjM0RW9leiVjPHxeNG11PF9LUG9DUnZqb2ttNjlpSjRBQ0pgYDhKKXdLNnt8OWRMPTJ7QzZ+JmZTSGMhfjR4Jm1IJwogICAgJ19tXmltYUR8RXpGY293IVZeeXxDSX5UNn0xYHNDSHtacUxgTEd8cnZsN1VlTHRPT1lAaWRAYmMkezBkbkZDQkd3KH19cDVrQSpxQio/Z15BdjU1M1NOZVd+Q09gOSNwcn5QfnEnCiAgICAnJTIoejE+cSYrLVglKkpKZWJXI19NRDQ8cl4rSWFFPk44V1prIXUpLXJzcig1SDIjKTE+O2lDO0AqOEleQjwqX3xxPVQydE90cG0rSz1GZTMlUDJgeW1zejtHUjU5R2ImPnNyVycKICAgICdrI2x3aSF4M1ExTT9eUV88Y0lpc0hVelRKWSROM3opQTlWKUtTJXVVeUFtOWA/enVVWG9ROHZFZzBuN1dybEk/bCpBRjh6ej5lbnVPSD1YKjljfShsZUtoQS1xUTs0NjJfISMqJwogICAgJ1BlP3I7TV80TndmZDYtYFhfRmIhNlBULTt6dC0rTz1eSnpgLUpSMVZAQjRJPmVSK2hvMDBzNmVEOzlGZ1NMcUgxd1YlQEZeJGdzPmJfenhmdnVsdnw7ekl3ZVo1VmJiY2EkQjYnCiAgICAnc0AjQjZKRVJ6UXZzVVE1Rk9yWDY+VGEjUlZUYm1Aa20wKHV0RyZLZTFoY3Y0PEN2SHttR3kmSUxmQlRBMG84WloxeU17eCVIXk9yNWpmNko/PUwtOGRgWWEybT0odVRHTyhEYScKICAgICcrT00pYlJ6V0B4QmQoM3hrV3lNN1NrNSY+Jnpkcjg9N0FYK0NiOCFpVXZgPyRDcSp9RFRPeGI+eVlgdjdDZDFebEJGKkdRVEhjPGxgbT44Y3VYKl58ZG1icHIjN3R0NkokdGAyJwogICAgJ2gpYyZ6MDNnc30+ZVdxbzl+QnNEell3OFZaNnQmOTxyX2NiX1BMPGl1MUt+JnA8eDRPYlVPQG4pJl9wVigoSFA4aighNFd3fS1iLUBsMyNqem9KXnpXKUpvNDZOK3JhU1V6aGUnCiAgICAnbzR3clRTWmc7TEoxaDRJe3wjUSUoNy1KPDZEfEAkczNwJk9EVW88PTdfayVPPTBAQ0FSU3s4O19mWSY2clBKc3lRc2ROPTdEVHVzYyp6bWZUU1cjOS1lJUVnaUU5S1FBazVrdycKICAgICdQIylzJWh8QmA/JTdGUnJsQURiWTVpXnNFWj9NZjJ6Y2Rxe0BfZllEYF5oPUxiK1RmPjxiKnRhKSR+Kj8kd1lLM2U4M2IhZSU7Sk5GeEAwenFPektRWnZXd3EkQld5NiQ5QVBJJwogICAgJ1ZaRnclZEtuTlM1R3teNyRhZkFLTGxMVHRQd1FDTTYxdjxpYVU3aTg0SEdMZlhzbVFsYWs1Uko0M3wlaTBzZ1Ehcz9HUz5vQi1rZDttfWM+SXpkN3ZBdSN4bllaPD9oen5mJl8nCiAgICAnTU8rN31wQHxWbFd5KGA7cmx9ZUN2QEhwSzlAbVVwPU1eNXVhRTBaNGA9X0NXYTJAaEpWPHYqQj1OJVZXbD1iRmlpPlRPe2EpKll6QXNYXlF3KEBYWmp9KWk/RzA3blYkJkk7dScKICAgICclLX1nSUFJUVBMN1A7TTImdHBMI15LfWFxRyVvTkZKMDYxPWA3dk80eC1aQWJKY1h8UmtFQDY3KTtJPn1wKDctT3Q2MW0+NWBwalJIIzh5SStFbm10VU1AZzF8M29JLThvN2tRJwogICAgJ1hGeEozWHt+ZXA7KjVPPjs/R0NHTmYzSWsraGJEfGxEb308X0wwPkdDbzFjT2tBQmE0TCE8PGZtSiFCUT9IZi04ViFkcjhJT0VQJEZ9elpCY1JWb2xeRCMtOy1+RXEwP2w+ZVUnCiAgICAnRGlSWnlARGRmSzhfSDtBMlJCbXlCdTVabUZSbXxLaF45Q1gyRGM/YzZCKX5iKDRwMExYLXgtQERzZVR9akRgXmZjT09SOWpWay13WkVgTlRDPGwyWlFKV1M3VHZTaGclWigqRScKICAgICdye1Q7RGI0LVopV2p3YDFjJVUxZ2JOOV5PQVFRa2w+P3ohflNrenh6Mi00MTB7dXI0XlA8Zil2fERafXRfMTMya1Njd15uaS10JTlrOVhNcldBQypSb01ZMGdQMnxsN3dsP0NJJwogICAgJ2ZYPVIlcUE9ZFhYQ0Z0OzIlWjNoOTwrblcoNUdXVSVPK0R5VTV4TkRfeE0rKDNwNGdnU3VXfGF0SHVefnkpSDAmRXxJdVlzWHFoM2h9KlA7Zm4mOFd5b1hpP1YpbGFeNnpPS3UnCiAgICAnMHZQcDZIYW1MJXpfPjE3Q1pzTTVjQXBKUl9VeyozNlJoMGgxcWxnM2BrdXhtajEmNGJfLVd8Rj9PUURNZ35JU01uZWNePmtadVllZCluKWVZQ1Q7Qjt0P3Y2byY+Q1N7ZElKbScKICAgICdoK3NySWM9cktVeCpQQiZSZVFCMVAqbT18Zz5YXi04bkBjX200XjNpSHBGfkJSMmoxRUk3NG52K0NUPUpgbU5TSzBpPyplc3Z+ekhBV0sxeCtaJVl6NSUpT2FzIWJAO09eRytQJwogICAgJ1NjeiQmcCZeZmZgeFhlTW8/JWdYelFrbTMjPUh1TUdLP0Z6bUwhQz8lQiNNfDJre0cmX3ZDKTRPWlZNMjgjdy1VYVIwaGk7WFhkMDFxcjd1LXc2alBtWHh2Xkc2Njk8Ym1VXmcnCiAgICAnaytNSD9heS1PRDl8Vzs8bUYkN3k+OWNkcV94QTdtU0AzQi1vOEFtVzFMZlExLS1qVTxsOHBvOEIoUk1JbyE8IUZie0xoJjF7U2dxK1VoMWRPR047NFdAK2t7Qm9qZkhwciZVQScKICAgICdvTyV0M1lOaWdObDxhQ01kOUZIN3h6N2B3X1I4dmRzbmc7SUR7YU4qT29GJGpxa1RCM0lFYjJYNEA0YGt0YGUzQitGVnpjTj59JW5ERVFuUmFwMUxTez9VfmM0RHBVSGhZMFM2JwogICAgJ0EyNSRzaiZBfS12bG8hXkFqN3V1SGZKbzRBRjkmQGFRY0JKR3h3QnMxZ1NXVnhfdUVSVX5MKjVTJUFXYzB4e355Kl5IQWVgdHZTOEJ7bGhMITs0X3cpYGh8R2R9MkMzbE5uWHYnCiAgICAnRCVqKS1zYytnMFlxbj00P0w5KE5QfTRFOWFkJnJ3MSlsSSVBViorajdzRXRudDRBNXBOKntDKEpmJjw3eE4xfTskMj5fUE9ROz5JbCYoMjJOa0xRYEJvdS1fYE9JKDQhSldUTCcKICAgICdSWFppcmNWQ31KeXE+Mk00ej0qRihKaj9Ue1p2PkBYe2ghMmFBcTxqeXA3RlJiMmM5b0leMFY0NnQlV2ZoRms7Y2QjcXRzbCs1NDFWRExEaWE7VGVaZyhPZ3BEI2tfNk1NQkM5JwogICAgJ1ZLTW95ai0tYmxCTnc+SWBPK3puaXVaSWV7LWFtTmF3aHJPc2xrNWJsVFRJWHllZykrPnJ8PT9RcjwtdCFFSFNNcWxoSkk0JU5rbTNoWl9ZLTx8O0ltXzI8PlE/Y2YzWUNUcH0nCiAgICAneEQ5VUZQUjZHUipQNlpoelMyNURpUDQmVFNEPG9RcFQhNkdzPjdDZSQtLTZxYlZfbj9SRj8rPiQ4STJ4NSt9V3khQEQzJXpAWCVKISFuUy1xbXMkcSlZT3JqYU5HQDNGMkplSScKICAgICdCMTFHODljIyFRUmRFaWwzU1MyRGNueDFpRE54NHB3Ujd4ZFAkTkspN2IhRlBvY1k+X2tAcXx1YThSOzYpSjNRazBoK1lMX2lSRU5IXyFMdTlSUDNoM19rc3heTFBObVhsWSF7JwogICAgJzd5YC1za3JSZT0wXm5xVUVNJVpLbXtUK1lGZyt7YW1hYEgkVWZPdXxXb317flFgQlNBNmJCYCZ4M2JhSlN2aW1pQmQoQjVaUkM/bnRJZjtGRGlefnxGU352TjtiN31TQWpFUUUnCiAgICAnTlRxdTMweHkxQFdvJThyfDR2Z2J7WXJkMDtpTjVFNmpJaDVScXY0V15oI2dULTdATUtGWjkzdmBfM0E7Sk49dUNZWmFZJE1iSH49MlFTV0tPYShXLThlbDRScnFyd30wVXF2VycKICAgICdQe2c8P0J0KCpLQEgpM1B3Z3NKMkZBZCV3aE1ZRGAjRHswc3hweCFZPjBlK0M1fCtETktGVUpjYXNLS2pZQXB0RyU3dVJUU1I8ND5sSFFXSkFoVHZsJW1SZjlKfEYyakExVkNUJwogICAgJ2dOezNjQT9SOTdQcW0jVzN4YklFZ18ybkM7MngxVD1WbnA1dFR3UHtKdTlOOUJ1ZkNuZmhyV0x4bmJWYT5OYmc5e3U0VE1YazsrPFhPKTE+U0Ryam5OXnpkSTdLQCNMKEdXfXInCiAgICAnMSQ9bD1uaT5qeWFyTm1jPDgyWjRgKVgzeXkld141aTBZKkpmYXl4Sl9RYS0wND92aDZGazhzJmArZWo1NktrVz00OUA9XkBGMDdDc1VNdzcqamhndiU0K1B+YmwqQ1N6eyFVPicKICAgICcwdHY8a1NeWSl2cGpaMDZVKmVUUE44O2xJQTROTm8/RGRDUXZTOD81dzMtQDs9K0V2JUxsN0VqIXgkTE8kc3o/bkBJNH4kfDBgTGBTUV87a1o1Q1NZPEt4YTBeaTl1fHN8fk53JwogICAgJzF+NUhicHVkZFFeTHM+ME0yIWhEamNCa1JgSENubXxNNF9aZDM1ZCEzSmx9aXl9Y0B8S1dXUklyPUF5Xmk2cX0jdUJ8c2BHKzZ7RDchO0dPPlBuUkljbThDMjxsWXp2VD5sSiUnCiAgICAnZy1ReHhgPV48QnteNTczRXFjbCNwV3RUKHBlJE81TVFsQnhrSkd0eWRFaVFONXlYb3lJfjQjdWtIWmdDNl9ocWFvdUVlaUVEVl5TVn0mZ2RffEtnMmlCUn1ycVZhcG0leHZrcycKICAgICcrX2Q/NlI7OHtOZT9sdCY5JjhofGJlcF8ld3NrYXMtUzAzLTxEZCM/Y1JBY1g9ZlFpKS1+JSZ2ZGlfd3p1Yz1iMC1DbjE1UEN4RHRgOWl8a1J9UChJeD1jemBXLXBoQ05IKnxDJwogICAgJyR+Oz93TVRYaTFXciVpT0dtJiZgdGpWMzBmLTl6aSE/UmckIUE1Pnc4SFUleW5tLTQzbllpaWhlUFluOUhPeF5SOzVIUHJwUGR0Xjt0KmlDME9mN2dLfUNobDFGUG9FT0FgX14nCiAgICAnbTE3Yz5rOzIzPG5SViMpSzxlOXpaPSsjMjAlZHxrUDZrPy1TbWU8KUM7X3M1NDZFell1akloODhEX01Wd1V6Nkg/PlVJY0hIYk45LUgqKCpjNV88OzR7OVQjdjYoV3pGMyR0OycKICAgICdFWWo5LTNHVGVKQkdaaUZOS2ZaNWwqJk0+c20wPFdmR3B3TCFRMnxsJCZmPWg8PClUTDljUlJoJShyIzxgKkNBUFlBaEtHX0R1M1Q5VzBRWSFSeFJzakBTK0dKPV9zQz5WZHBOJwogICAgJ01FIXwxRUkwaTdEQyF9aiFGPU8we3IjfGU7VG1OOXg5I1YrJD9EP0A4a0JyQzcrfUp5WF41ciRsKDZGX29scStmUXNEU2AtemlmXzRkdDNmKTxiZXVoR2VMUGZabyZLTEFQTXcnCiAgICAnTT0oZzs3OUJKaE1Rd3gjNSpKUlReUzhRUXYrcClHekwmUX4kPkM1SURkKWE5bE98KFZHYSNTUUQ2dWZCPnJoO1FYVmsjKUhDRD5Ccz1LIzlvTGBUKG9kWXNzPmh1ajdLNGMxSScKICAgICd5KlN+QHUhJmB6WFItKG9RK3U3eXtJQis/NTdJbFZIXlFwaypsN3gxPypqd3EyQEF7KVR+ZUxzaGJ8elRBeD5geyklMmh+dmNNQWomK1BDTHR+ITR6cTdVRE1PM1p3eGhmR0JAJwogICAgJ3VXWXNpTDdMOHl1ekVPWVhRdD9JQ3JpfCF0bGlNQU0rI2hAJGNBUSNmb2lRbmtZP2UtY1ZzZiRhSj41e3I0Uig5LUZrbz9KSyZxNmdoSns1ZitNKDI8dmtxMGlMKGU4JEtadygnCiAgICAnK2QlMDYweDAlPmY8cGlHQ0xLXnI/TE5GRnlVe2smMGs3fVJnSHheVTQqKGRea1duRCpTYnlTWTAoaXp4dHY5NXdjSilpcEtVajwkMyRuVHZ3JXk3PWhWJVUqJD5RZWZZTEdNXicKICAgICdUflVtaDUzTGs4NzBKNDYqfk94IUtQbnhwYGlEI1MzMz8rS2R8ZmREUzhkNCZURDRnZXBudj5+KHVAVUw+O2VaRyFpTVZhVXFCeUBZRnIrQk5PPEk3Wm1va1h2dmV3NGBoSDVHJwogICAgJ2BvWnpwVVJTT3BUdl9JQ3MxQWJnRWBXZjFET0BxP2gray1neTV2LU9fQlAlcFFDYl5xYl4kX2IrYWZMaUF5JXR6QGk5QFcmIX5oeCgtU1NGJUAqZHxHdmdjfnk+YTNIaE1xKUUnCiAgICAnLTE4JnNzPnVwcFJiR0Z6UF48V3smd0lLXzIqVDtCST8zbzdvZHZ+RVVQXyNlZ3tLYz5NcGl1PTQrXj9AO20rS1lqRFJGb3t6YX1ea3thPFU5ZmthbTNsWm8lMXYoKyh3X05YcCcKICAgICc/eyhzSHVQWkhfaFJzditmTkZMKkZXOX5JOX0kdHVjVk5UR3ZnYW1sYzJSN3xZe29sNTJfTkt4MiV2KkZWTUg7NU9ZaEE/NipiVWhqfiotZ2tHXjQtQUBifks4YWphMWomcmdgJwogICAgJ20jKzB3Q2lmS3xhc199V2pATD5RPll5R1BBSzlNNDNGRCgobnVzVzBJVCorbHl9MSRAOHBJK2MlNDlhYWNeYitQSHkwdmY0czt6WXVyaWApK0hPNz1PKCRTSGdHSzNkUlMhUl8nCiAgICAnJXRWbExuVXE8fj89KGh6O1FVQjF1WXotUEx4S1dnMk03YiglaFZKNyROVjhLaENxYztLRnVFZGNaY0hTXiU1djZURn4/TXU2SU1oSGdkOShLalhrPU5lY1c9RE9pTTM8dFE1bycKICAgICd3QEI8KGBSRG1jUSh+TGMmdHdTJVd6bmhuQFhUIyt4Qnw/WHtjU3gwUUdqPkxYNl4jJXhTQz9vSk07YHctbG0tOEROWSkyamQqUU92O19DM294ajJWUVl4JDR1OUh5Q010KjAyJwogICAgJz5UYlZ3XktUPit0eE1TVz9nRTM4O3BldXs3YUpfI1ElWXAkcm5nZWUxaiNLUW18cG8jT0RPelY3YEh3VHg+Tko7ejVoZ196U3ZkZXZVeUUyMG5wUGxUQiZAJmhrXldOdztRZTUnCiAgICAnOT9ybHZMJT5SPVVlYXVQTF9NMnIhM3JgRjZ8QDUmPUd1PnRQRSRQUGVKPS1DbFFtNnZZVGU8ITBleGEtT3UlWG4/ZUNIPT1eRGJPITdDeSFQaDBmXmlRRiZjWWRqOCFoRVBlOycKICAgICdsWSoxeiFRVHNMaUN1NFpAR0dMK2A9ZD5ScFJtKWFYYEpMZytII31kQGBEcShVfEotZm81TG1lJl5gcyl0PUBWYG9fbWFHJlpxfEFKV0BUO2h+Uj4qcEVRSiYheyMzSFJ6byN2JwogICAgJ1E4NWJ8JnR2O1JqYEojWExYa3RESXd1YEZ2dSg+TFl6fGVTRCgqcjlYPnF7MFFtbnk8YCQtQiZLIW93cmNtayZgUGBEVGQoKWh3OzlLUGtYU259bFVAKzcyVCorYzlYIXAhRD0nCiAgICAnJEsqT1AhVHF9c0VYJj4pO0BXSlczdUxWeW5eamowR1VxKHE+Kyt3TXE3d0dvMWdTYzVOazZUcFZHPDkpXkhjS0pAailxYEJDeDNYcUZGSEdqPlRUaGtaZDAqIUVZaVBJP0srbicKICAgICdeckU7RUhzfUAjdmNwN15TT3ZnKFlEOTNNd09DM2pTQjsoeCpOUmx2e2haezUmX2JzaUJnTmtGSzhpPUUtZ2YrWihLJFBPR048ZUhnSD0keUZrSnx6YU41a19NUnQlNDZnTzRTJwogICAgJzxGPE4jXjtjVH5JS2RmQHpjRks7R35hfjI1dSNsWDgxaWcxdXg+NVhTOyUlJmZBWkE0Sn1yNmJHRWI2SkY4T0JMPDExRD1xbC0qYzBMVHdrSChaTGFVJStLa3RoSCEhTHBgOTYnCiAgICAnI2luIzBnOzlpPyU7VHRBUjkjcjBJezhyaikoNUVNaXpiSk4pN351fnVNWl4tTDJpP0lWQjNFfGpwMUY7KWFTI252R0NyeTx2ZjNSY2hgMClmYVNnK2xwXiRzNG1EITU5czwwIycKICAgICdAfGUpI3lXU0FHI2hKbTtFWDR1KmFQPnN2bHdkYWQ5JiN3Wm9QVzs5OWNqU2lle1N1d2FPSl9YZ1p3YDZ6ZV53REgoeV45aXRKKUN0ck9Jalg5THt5TjJIMmtWJWlwXnV5aDIyJwogICAgJ3Z1O0J3SGQkSVotckJ4XnlqPXR7P2pYQ3dlLT8/akx3QmdCKmIlZGI5WUB9KlNCajdFa1JRRExSQCEjbUQtNnNZQDdeaVZJVztAZGw4P3ZTM0ZNQCVPPz82ezI3TSVtQEBMe3EnCiAgICAnYkp8LXl5eHhZNT55e0VUVW9LSUczNFlHWF93N31FPXRBayZYSTxgVChESj12RVg4U2JYQHI8NnE0K0R3KyVIKXY5dytsai17TXp6S1o0ZnV8SiU+XndvOzNAS0tCbG1ZTj0hbicKICAgICdSXkckMkVQbElBMndsUVUhNSlOWXAmaG07LXBNfVZKJHBqXm56ZzVmWW5XeFN4RColemdafmlIZlgqe30tN1UmbzQ2ZW1Cb0RqJGJAKjdgcWk5cSVXVjMqKzZxYWxva2ZDVmRYJwogICAgJyMrOz09b1dzNl5lKU52MmF0UXVUaSNAPk4lcEwlR0pMPFB0THgkNV92WCs7WCMrNUt6O2RDVkhYND07Kjcxa15tTFhaNkBNdUh+QXhvMktAdSs5OHtlQGh9dzZQQTFae0E+UWMnCiAgICAnYEpldlMwYXghcDFQOXt+QnxoP2NMTGA9R1pAKU9VYUw8KFZefFhmbnhfPnVVdjwlRjAjckJDVmA5M3syci1vJmg+M2k4R1VqcUg7SSs+KCtVM181UntefSs2ME5hKlhgI09mUScKICAgICc/PGw8RkFaMHVTOVhQRXQ+PXwmfFF9fk14STN6QFkyMjhffWVTYkM+SXtmbnNmemFLQHE8c2t9RU8lIzdxKWwmK08rX3JHMGNGcU4qZXJvTTREP2xVKGU5akpjJlReYTFPV3lUJwogICAgJyR+dnRee0AtSiFlM2c8ZigzI1pSaE8zeWolKj5uWkhCYXw8RyQtZSo1QXRJUWAjKyN3JG14bDk2RTwzcEB7ZTxUbU5iMXN3X0haZW5Bb0glVDB7UnRPTTB0PnhELTNNczI2cUYnCiAgICAnKXFEPX5vMnJZVzdeJUZ3SChBd2BHTVVGcU1BSVE3OD40SVRqcD1ecT9ZNy1EWiF2ZDxsSHQxLTd9Uzd5RTNFblQoTmxXZzA7PFF3KXJgfGVqUHtiRnBMYCtnbD87e2BRYDxpcycKICAgICc3Myk8NWl3WUI4MDY+MlVIZVc0dHdNUDIheDdFUHtgaSpHYj1WdGRuY0hZaFUoUyV4NHZBKWdXTzljSj5ldl9AcV5zJEBIdWVsT3F6eF4lMm9jfDw3ZnRiaSYjP2wjTGBIMyoxJwogICAgJ0FtU1YzKG92QGMrYkdAVEU4SiRnS1RVZEtNSXlMN0EhWnsmdzt4QlJIOVlzQWRtNzx7el8tLUdWRCtIaDcrR3ZVaiFVPEtWcWhoRUltVE1LWDhGOERwd0Q8Ki1fPlkzQSE8JWInCiAgICAncFc/M1VWKDY0IUVQJVlsczFGanZ1ZElGY2g4WFZaZ0x0cjAlcX5yVHZQNGtQdilmZEF6KGRxM09ITHVZUG1pcCh7VSQtRDR5fChke1ViS3piYyhqVCsyUSZqTyUzKH1sYHV8ZicKICAgICdmXy1jLWBiJkZubnd4b35galRldHZJKXM2T251fGJ4SXA/Tj5vflNeNWBhTDMlTWZgWTxyXlJaMTV4d3VSazJqJkZEa3Qrc1U3WU9gSDk5bzZIN0V4Yy1mfS0pWS1hZWZwcnx7JwogICAgJzhnMjJFK3NPbkRCeCh2TF54NkVxUzBsbmRAb0ZFVS0qUzZIdkwxfnlhUmFMM19WP01oOEpZZXYwY3kzai02YTJyUkJCRkxFQThqQXpEd3JZRHoheDlnSEBueDVhQjlvQClEfXMnCiAgICAnUlheIW92fl5eYmkpZj8yMTxoNERrd3RoKTlPdlZzPWpIJlV1cHdKNTlMJlZZak08NjYpISE+QWYlS1REOTtWMXtFTzApeCE7RC1RMWtUPiFzMVcpUD1uQE56P2BpVUBwWW96TycKICAgICdWcE5fYnI5S18kIVBwPyQ5Jl8rbF9CO25AckooUy0lLW9iclN3ezFGd3pfIXVqd20oNFJwaTlyRHdVbHp7fmN5MC12YF9YMGlsMHJJbW51b0JqMGxDTmVURlh0JXNeJiNpfEhCJwogICAgJyFANnY3TitHfH4jMXJpUXIwdTxiMjgkZkZEK0x2JWRrZTw/UiZJK2Vkc2AzPEg+IUBfVyUjaTdKMUlqa1JiMDNmNXclTyohRyUweUQ5bFIkPlkrNztZN1VzfjxOTEBUWjk7QmQnCiAgICAnWTkqMTZ4PyNePUxyQFVBTzNkRTt7KHBKSytBVDxKYlplPVFWaW8/MSl1UzZZX3YlRktEQGxxMCNsaWsxaEJWcmtqciNWa3w3JWRAOG0zeWVZMH5NNnJqfHtlPERQWSFrVkpgRScKICAgICdJeWNQM0V0ZHhibSt1LT9mMih5T0ZALT44cDtpIz49clFNTWI7el8rKk1UOEhVe1ZfQSlRaX4xOFlDMSs+fU9XNmMzeCs+Nis3X1lwYXpaLUskTnhzSmp4ZUxafmAmJHp4RXshJwogICAgJ0FeSWU9NX4kUnQ8czd0VihKIVBqdWg4Sz5PNkc7UDZsNVljPG4zSG5DSVpvZVRUQFRjZlZWKGlXaTBPc1RkTVBaeWt9QlBSfkR0RWwmbUxfUmc9OU9pRioxNGM1K3hadXZgbi0nCiAgICAnY2R3Z0ZFWVBYJHhNP2VgeUphRXBmbHJ5TV8mUjM4SW1lcH43bHQ5QF9UMCNVdWU0MmUqUVhBS0BAR1kjPyhve3BFREAoRyZ3PGxYb25KPzd4UjspPTFkX2NhdHFlXl8xVjd1NycKICAgICdvYjh6emxUMCNeQEZsaERIQyZkdTg0PUZFcDlXT0krXykqUz4zJVVuZjd+MyUwJXlVPGZCajlQWm19T0AlPGU+eEoyeEVMX15KWCFwTnw8MHxDIWdoe0hNaWpDb0NyLSRXQGtjJwogICAgJ0IrVHQ8WFhedm1QQ25LI0E5QiMhTU92IUNCTGh9dT0xTk1AOyp3bVRIZkJqZyZweUBhckttVmQtakt4STYpZ2s7bjdiNDRxd3dHd01COFprd2FIbG5RPmJWNVBTVDBObWRMSVMnCiAgICAnMkptVUU/MFZ7bDFreyoqLWlKRzJnc2p+Z0AreTIrMFB2THBZQWxIRCk7UDk0Z1NEdVYoaElZQzhJeGhHSSklMVFle21qUCk0bUhHQzdVKUYkbnh5PikzOXRheGdvRCZEWHokcScKICAgICdQYjs3NiUyLXVmbmlBNUtZWlgyclImVXxYX2FSQyZTUiNmRi0ra31jKHJIMGU7NVcwfWNQSXJlZip5Yn0kOXlQODFfakhXcTRBNyZ0T2dAQTR9NjZvPjJCP0JjeUQ0NEpnUU5ZJwogICAgJysjPEBSRj1zSHRCbSEmJjh5MGJ9UWo0TE5ZP2sqYC0/UHAkOGczOXtTJC17aXttcH5oNkEwbFJZcTFIa3ZaLWdhREE7TV5HVnVIR3V1PCgkYyomfUkzaG9rJjAxKjc7dHE2bXAnCiAgICAnRU9WQjxmQzwoa05qLTJpKlF0bnBKUHkjZHRTQzJ7YTlUcVROa31MMUlqZDBJIXlzMzQxKVQ8ZTtDeCh+WE85eiNmK1ZiWUw9NU1OQ210SEc9ZmdNOD9wVXtZZnNCQWMwNFFGMScKICAgICdwYVFOSnZBPDEyTippa25tQUFWT3JkN3xpc1JAcGB2diljJEdycTclP0JMa0hQTUB4cS1JfnpkNFpIankwX2RCJHFfPiNDcmYqQkteRFFqXkFWN2JRSEhMWU5OK3ZjX2YpdyFkJwogICAgJ0Npb0wqV0V+ZVUrNSU3TEFIMGEyOypzenxZMURzaEZ7c3FEbmVBWkk5Q1g/PW5Fd1hRZT55SEJEMlFwMEdoYio8ZEhQWEYrPThUUU1YSypWTUpNN04lfTRqekdZRi15QH57V1EnCiAgICAnenx3RVFnRVpMcjtnYFRhYCloO1VHJjltSWFgcip3SSQtVjQmenE1YFRacFY1bG5Bb0FNbihKTVRpeU82JHtgJW8zbGV5RlZtcHUxRUFKZCQ0dEcoYTxPUT5AMD8jQjAlJnRDRScKICAgICdVRXJrMi1KdHwqJGZ9azhsLVcoa0Q0ZXlRblZ8LTBzKG9EbUJ6MlVJaT8lVjZBdSlST2YhP0Y0UHU3PzZxZnlEdnNsVnFpRFVGfShRPnV8O1o2aDZ7N2U8TElhbFM8SDF4akgwJwogICAgJ2wpPCVTeDhDJTxrT2MxV0omcU1HdHk2OFM2TyE+alRoIyQtWExnfTUhSUlpRFA+KTZwRDZmcnVRUFd5P1IyPmx2bks8MyE7ZClvX3o/O2BBM2RlZm41VzA/UVQhXkVnIzNvKj8nCiAgICAnaCo3YkIyIUZYbiNlXjUxXnh6ZkNyfUViZ0lvKitxVGAjQVdFbW08aF9kMWlkbDBuPjFWdlEoXjh7P3F5TGFaTDUzZSktd2xfI2ZHQzBlPT5MM2FvdDRsUDd1QEM+WjxaUl5weycKICAgICdGLSFZUzkrTFdRSXZ0PUszRVppTG41Rl4wWFdwTGY1NE0wclBeZFU7I0Rud1phYU03dit6X01fc2Y4I3kxMFE5S3plIXx5b052Kk5OVld0aS1eZU9tbCNMfD1yMW49V0ZsUE59JwogICAgJ2M7cndpXlJTcGt4K18hT2hkOzwqWWh1Xy1QI2JWVTc3aCs8amVXVUY0bjtgTEkzJllsU3V0Pz5RMmRQVCNCYj1CKiEqezI5aSEqX2htPShpPlVJTFkpM20oWT1uKmx3OC1MSlcnCiAgICAnQEVQOGtRS25OTUJYb2BPSmthbj5XQXpUP2tRZn1yMk42SCVDeGl3QTVraGkkUylyKFVxN21AI1d0RVlmOV5kRmo3OCEtPW53NnV3IVlsNjE5I0FAQ1BVYiNxMDBkKCpGa2hYYicKICAgICdOM2RBdmh2aGw2JV5RZEZlPk0qY3BpX2g5SnI+QkdJJlImMDZQeT9IVWJtQFg0KFNIUk42QXQhWEtAbTAra184OyhVaWZ3JHVafEV3JWtfaWBfUX4wN28zRCtDNHY9e1QpVyhJJwogICAgJy1URlMrK25Fa0ohZHpySSVfPHlucTFRIV5uT2RKdVZifjZObTV1MnhFKWdMSGR0bXx8RWFHZkpia1BtKnRAKmxHNGBhJXJOK1JQeWs0b2U5PDVLa3kyfWthfkU7IUt4Qz4kSz0nCiAgICAnaiE0OGdVQzY8NSM2TkNGNGdNYDM7WmwjKEJ1TClkVWI2e0BTbnBYRXFZWHdKSTBxc19sY1AkMj0laGZsbiVQNFNVPW5vJVFUcE1gRWl2RkdnSGlZQUQ/NzB4UyMocSVKdiUhMCcKICAgICd4Vmc7JTdPdF9icTVQNElEcS0xMktAcnFsJFRKN1l7amN0bjUrTiRePEAldnNeIXJuOVU8Zm1oKz04QmhYST9gWW1hbE5rSWQmZjxZeWA9ZFBCVVd8YXNFKkJ6NUxIYHNOM2tKJwogICAgJ2NYN0U1P3gkTmZIeHVmU3c+a2IkXnZ9STh3Pm48KFkrWCNraGYkZHg8YEQrKD15ZUFnfEpnX0VPa2Y0blh1Q3sjM3srYVZZNG0jVVkwckgqYVhrRSlCeHBvP2pQQ25pPXBAMz8nCiAgICAnWT1aMWclR2g1I0ZMTWVgZjlhKmJgOWRHJjJNVGY2bHdkWFMoUDRgMXNUK0dmXnYyazR0R0ZMMkZ3c3U7K048ZkFSPWt1MDU+d3l+Wn51Z3R0XlE8Qno5SSlNTEdsIWJ1UkpxaCcKICAgICc7RmcjOWQ0JDRnS3Y8OEJ3IyFIO1MtcWBKcVRWfT44SHYpNF5uU3BMYTAyYXFLbXg3RlFoYElsa2wyYVE5UUR+dGAhb1FHTDdCNFJDTSk3KUZDd2l1LUYofjNXazU+Sz92Iz9pJwogICAgJ1BoRzNgNVBxPjlsei1RIVIkfDJVQS04T3NyQHkoXjBnbGQqYkdhMWUpLSNHVE89c0NfRnhZV3JiIUNyZGdUeEFmSWQzNj8kd2txQipuTkNoSlJJY18kUDgqIWVkTHc/TkIjbV8nCiAgICAnSU9qOXZjY1IoLXE0I2xEQGdGaFcqTl9lNDRqTDF6PjRVPn0jXzBlcHU9dGJJbWUhcD48MCVIe1czemg9M19KTy1OWUx0TXxLZ15oTCtrWjVBKE8hOSEmMylze3p9bVdDajB3KicKICAgICdYKjZFSkIxIyNLXzNCWihxSk1WKnRfP2llcz9xY2FWUUNONGdybSFLeHBQME16fjlKYT1Sbkh3V3A4M2wlXiY+ZXBHTlJWS2wmRUdoUTVUJTtXOSNoQFRkQElybXg0eFlnNGNiJwogICAgJ28zPClBZ1FWVi1OZXJwTTFJVGk0QmtjUDEzfXhybSl2SEZYbWZoISEwKnF0b2Ajb0g3a21yakkoNDh7U2VXOUAmOU5VWWYrclJme0A4K0J2S3ZqWFlsKTdtOUV9MXF6XkRCYCUnCiAgICAnPCRhd25eXi1idk54JGtpZUQzaGoxYiRGSlVuaFVLMGlMa31JMD9UMkZNaEZEQjVuc0gzZzk4P1F7YHV8Unc9MUhsZ3F6YGY2PHxIZzxDYWo9VmtJfGNjYnVuQVBqUXpqNHN+SicKICAgICdUS19GZiRCc2lVRD5vQCM4S1V3PitjSnZfWXNNO3R6MW5QSVopYE19YEY9KUcraSpwNyM1TCYwTW5lJEFQalg5JDIhZFRkSk1DeE43Yz9AXlJ5OzNQdjlyfkFnMSpnVjgqWTRqJwogICAgJ3ghKHFtTUktTmB5JVdTKUc4R0B4R3B5LVo7N3tye2lRYGZxeX1zbTF6MmdNeV40aitHST5JTn1jbFR4cD9CTmMpTjc3dyNAejJsSytVKE99X0EqNzVacHE4MHRWYGlkMndXe30nCiAgICAnO25UezVfSE13Yj18M3NOUV8tWnZXMF5raGBsTTZNdiVJOHptPU0zb0opKCpOeE4rOXRTYjl4bkdoIWtiU2Y1VHliR25sc1EkVkNybSskS2pTRXsrT0JNOUBFbWpxck1VeH0+KycKICAgICctOGM9QHNae0YlMGVTSkhuX2xYLTB3KXdXbklPa1lZbzUofis/ZFdRJFhhPFhDKnM/V3RTO2clOTwmeiFjMnkmTGkmZFY5VD1GbnVNIzZ1KiY7N1p+cEhUX1lSZSNHPWwzQldKJwogICAgJ1FaWUZBSE9EbkcxY3VkJkJFfXRpajZPfGRCP0hHVVlzfT5NRmUxNUc0Q1NQajR9bkRLbE4xXjY3Mj1MTkBvQDs1SE0/Z0QwNXh8WE0qZjdgQ3pHKS1FPkFwfCZNekxaOC1mbGknCiAgICAnS2B5LVRnTGlwKEhRbHY3bWVCdWltYW5YWmxjcHtLK2hVc1RPcUpBX3c7PDtTUkdafSpUVFIzTj1yR1Y5VFIyXmRzPCs2MWpVayNBJUdKOGRnNUtWUjNKPjwyZjF4Mj4laE04SicKICAgICdLMnokYV51ODxENUNWQ0FsQ2ZxLWtJZXJnbW1sPkkwTShuUVUtJE16RnpNeW1XPWM4cFBCfDJFYURiRTg3WGg+UjVSeUB0b2F1V2tUOWRgNDlreGQtbVI8JmdrT15HdGp9UiFRJwogICAgJ0ZFS3xVM3hGbHFvU0VqY0dPOD5eOztZcVpxci0jUFZvOSolZ0MzYT9DNTFSbS1hQ1ZlO3NoYVR2OGA9JVJIeXN4MkIlMj5jX31GdWJSakFBKzRIdU5Jenc8Tjwjbn49ckR8VHQnCiAgICAnJnAxWDtpVWppI2pCVXIlRG1xYEo8WCV+VndEWXhoVl9tM1BYNzU9bmw4TnVZaldYNVFIPk47KzM2QCtEeFEmN3leSUR8dFB8RUNLbkliKSgqKjljYWNgRXBRdnBtfXd2ZzU/ficKICAgICdHXk9fRGFAfWdPOEl6MkM/e1F9MDJDM0NPVkFtbG0rNmNkTjhJMnN3Xyp4Y31Le1pCYylEWWxDaTZCbT8/UVB2c09UKD1AVlgwfHIxY0Z9PlVwLWVib05BZSNHMCUlPHRXendXJwogICAgJ1c2ZFUtMihgUE8pMXJDOzB+Tn5qP04mSEd7V214MXFaXyktP2l1RDdTVCFMbSFYMCNHVnctZUt7R0EwJTh4KEt8YWR6V01XaExsV0txJm9XUXd8PD9oZ0FhKGZsY2RLVD5VTk4nCiAgICAne2o9Rkk5fkkrajc7RUJCWENOfUtLT1NxSChWJFpqRy1jPW40ZyY1STlHUzN+PyEzZF8kcWQ8YDw/X053I09PZ0U2VVhIeD83anxSdC1sO0N6ZHxEQVArcHU8MGtQdmZLbHRRPycKICAgICdZd0stWiRpQTRhODZAUDV7aH40WEAjRylsPWNmIzhgX29vPFM9Q3xrZyQqRXVePldgVD5ScEM+ME0kenNERG8kYWpMOUtWOyRlKSU+MUZxbjFMQ1JLcVB0Uz5gbntzbmAzUGhYJwogICAgJ21RQ21lNj9yeyU8fU8/eSUrdj9GbWckPWFRciZpTlpRXklWXnJkcntuWUVBeEpCSmxoJj1zeWFnYUZxUiR3czw2PGY8SSg5SlZGQTJ2K2U9eCQoTFhDeXFQTVpZXlMwU0RNbE4nCiAgICAnKXhmNm4kPXlZcHVzPWkpWH5ofjx7MUM1JXdwe30yP3xTTzUxfj1uRC1LXk5qbGFrcCNiSnJpcm16MiNJZGItOWdOcSZgWHh9amQoejU/NkxyRyg2Kj4hQEQkYkRALTBGP2YlPCcKICAgICchK340IVp2SWVBSCUhYntAO34+ISVLT0Y9ejJ+VDR7QUwpaVF8QHolO0crYnVaPStWYV5rWj8tcz9+OFB4eGFTIT9SYWh7ZHZwSTxndk5qaWYlOzsmNGpgUWxUdmdLPjJUOFVNJwogICAgJ014bmx4eCh4ZG9veytrRntNaVNsOWx0QXxKT0pfTi1vY2I/bHNJLU11TSRAK3ZHTi1qUDAxQ1k/IWRVYVRMOEIwMDctR2JZdmJHQHY4P3c3ZTFZU2xENURVdyNWK2dfWXR8NXsnCiAgICAnKGhUeUwpUyR8KU5eV3s9cHUqbFZJPSRPZ1FGczB8RUdXcXBhSFAmTGhkZ00jMW4kUV92Uik0R1BvZzA1QkloP15DbDlIY1F1NlB5WF5FR3ZkMHxVU0tRR3VncGFXN2ZAcjNVYycKICAgICc/JCUoNng5Rys4Rio4JDhFNXZhUjE8PiNmM0debnwwVz9uZnE8ZWExWHw5KHZTbF93c1NGQmZRZV8pY1Y1cEpHXyhWOzdSVVM/RXFjMkwjOUZhYSFibHJWNyhRX319UUUzY04rJwogICAgJ2dkSHd8MilSQj5VeEs5c3Elen4wYkc+KkVKNWpOQiF5en1fYzNfJjZhNkZEe0Q0UChjOzUwYWdVO3RUN1Ngejleb00pRnBzKDMtb0w7Nm11OD9rVGt5UUghOzh8Wkc/ZH0xQ3knCiAgICAnKiZfcmpkSFE2JmFGMnY9Uzw2QFNaOCs7TUpxfkM+QUhEMW4pb3BtSXlSYDA0MCErIWdeSFZ4O3MmR1YoTzg2I0VJXnUmNT1qN2RaPisyYUVUQEUhdkRpQ3Y7TFhNKUV1S3EyIycKICAgICdJbGZgMSFGRHsldVl2JFFSRSlaJk1gP0s4XzR2Q2VMMiQ4fkRFZ204IUdrbH4tZEBCWG48MGNnYFkqSnchRSYrTWdeMVEzZlRVTlY7NDN+c198MmQqeXs5QiF7c0skSWM3dDhiJwogICAgJ0VyRUtjV0d7JWZGbW1IOzZPSmx4ZTheVmhNd3R8a3dEMylIKU8tR2BQTEk9YjRmaXJ3KkB8ZnkyQHg4OzFBJkJkeDlhYThDfH5GUy1zKUlHb3UqeCtpenhDPkxSWndzUjZNMT0nCiAgICAnXlJxTjUran18VDZBbnkhMFB7Pn5sVEZpSChyMVk5QU08QygqKEQyUFhQfih1c1IqPV4rcU0qfSpIJXF1NDhGWk4xU2VyaShuVkRDOFpJd0hmJHVZbVQqS1AlV1pGTigyU29EUCcKICAgICc7O2BgbDBiQTItRVlea3pkN2tSPF40eXR+JngpLXk5KCZacjMtdkVXK31oJWM1WllnSjxFcyplUl88bjdXUWktOVRMKChqbE94ITZOdEJWUSNrX0Y2Wlo7MWY+QWFKYUlFb01vJwogICAgJ0Jyez9IdCY4bTNEeEV3a190MktxO0FEUjt0dnFFbjh7KmFHYHFtI3d3cHsmPSR8byVlP1BTbFA4Pnl6fkoyR29VPi11VUFmSmJVS2sleklmZ0hGUl5KOWxkKmFFUjZwb1Y8aiEnCiAgICAnODFnSD08Y2RWUnpfQG4jPEY1dUVzc25OVkB6NUA4NU5Acj9BWDY0Sm91d1d9cHZzfDQlKnBwb3U/Kmt7T1c5ZEFvfU0lYyhyfHE5ZTRYRXQ8ZDhANj0/RW5WKyk/JUFQfFo3dScKICAgICcwbD5POVhTam1KYzNIazJaWlVIJCl1amVvQE9+TDVLQSt8bHY+N0lvYWBFSHpXRVFkfT9Qa0JwY3FKO30yaWtodnhEZkh6Uz51VF42VUZ4dVBhRUZoKXZNR2hsX0MmTG5nUG95JwogICAgJ1MmSn4yZTxIbUhwYSlqZHBCYU8jZWZ4Zmo3JDhPJjVhO0VRSDFVSFJndVoyb3tBSCNOMUloQmFFZiZeZzdOO0VGdGgoZ35ORSV5fTtENVhuWCktSUY7RmB0dzZuKnROXyYmP0wnCiAgICAnU09Gc1NWaXs+RlQkPmp9QS1nNWcjenxtSj9zdih6XyhLWE1IPjlTWD98WVFNTmpBR2EzPzdzPGNYMVhEJSFtPDBCKW5SbWNYNyZGO3NaYS1fWWFTVEZoTU10KmkldiNNfF9BZScKICAgICdBdkArQ1d4VEE4aHtVLSthQFlmUG8xaE8rYFNTYE1NbEF4TFBDMz50blBJajErR29BZl5IPFZzV2IqNTZzbHo1M1ZWbXBgJldnP0Znez41JGh8M1IyWko0dmBtY3kwfjxJWSgmJwogICAgJz9VPm16Q3wzJCp6OU9McVVAJHtWQCpfYzBvKGo4UWIjQVZgZlNoRF5yYzFDanlCVGlLTSNuSWxTMkVSbzF+WHY3SEo2JSs9QiM8Jk1ke1gmc2pKPTVsQVhVZEBfanVDUVdfT0InCiAgICAnYTRuWk5TPHZ0UHFRVmJ6ZjJ8IURPTjxJUTdGKz5iTypBTD9SOFlDVlVJPCVaTlEqZylMdDZ2SD9ETV8rTSt1O3FOMzxLPGdrRXE+JE9nKmZ0c2ljdjRaX0FJI3FJPyFNYz1nZCcKICAgICdfPXM4KTdgakUpJmAoOXllTjZkT3V3fm5tRDFaMk5jclhsRkFuNm5GVCg1RUQpWW0hKTF9eWc1a1I7flpPQzhrNGZlTjFDeGJrSyQyUk9kfT1fYWdgTzBRNC0tYzM3fDNnOFZYJwogICAgJ24zMnYkP3o5UnhZdHpgcHFhQGFyNEdkRnohSFVuRD52dytGd2kpJithO0M/MlIjT3h9b3pkT0BHUStHXkx8cj5Nc0FqTm96c0diQXUwdykjblVhO2klJjFxN1dWNXNpaGFwNTgnCiAgICAnPWxId1p0MnBeZ1ZhY2FGb3Mxdz83TzxASFBfLUY/NkIqQGVPejJ+e3EqWCZ2UlVuOy1zcz80dzElbE1RPyFicVJpbjdeVTZ2PU1wdmBmRlltMTs2OGEqUTRHNm9xbitgTEN+QycKICAgICdFVGFKYXpERDFPd2pORTBOZk0mUWYyYztRKF48bkw9XiEwcCRITmlVZ25+bHVjZjlyc2lmPzxEUztrYzxCOUlxPjF9d0J3eCgpTCY0bFM/WXZaYXY1Y1EmP0d5UlpoN04rbEVMJwogICAgJ2A7LXFyLW0zTmE9QWJwTlJ3QktFX3lfRShVaG5xUC10PkghcWw2Y3o/a0dwWG9eZl8xbCpAckc3d0s+bC1ONkZmWTF2MjM3UXY1LUl1eyN8RXcxVmFHaStZSW4mTit5cVBiPTMnCiAgICAnODZ9PTMjUDJseGRKOWxKM0hQTkRtIUFWd09CLWd6alBUe21BKTgyZC0tdyo5bV53eHlWR3hxNzB0RjhjWDJiaGU5YF9Remg5Z35wT2NnVWg+NHw4VGRwQWc9VHI3eDhQYkQwRicKICAgICdoRjYxPFdJZDRvaTdJaTJORmJxI0xJbGlmTzk8KSpUTjw4cFJne2oyKj1TIWk9akVUJVJyaFRxRng4c1hwO1RHZWV+Q1p5JiMtTkI5cHRvSUlrWV9mYGNpWEJvYntmdS0yZmFzJwogICAgJ29gYSkjNDgmfWwwIXo5dkllKCpPI1JEVDY4KEBpVFdENiVFekFRUjh0XmA1b3RtdCotVjx+JCUzcjJrRCtoQHUrdChDPDErMUJxbykha2h+clJRUDhSPDE+WmRZS0BGPjUoUjEnCiAgICAnUUIxUTBzc2stWk1oJWJLKkdKfVFoRlRZM0M7IUpFTVI2KlAtVzA9RCE1P1hHUk9QU1drKkRaR3RpKmRmRkNqJSVNVlZCVER9RV4kMVo5c0BxJkZVSkoofDc1P1BAdDYtNWhkYScKICAgICcyYTRWYmJqNG8rV0NIYm5haUQpRF5maiVVSGpoOVl3RVpQcnB8VyQ/NCRYfHcoZXcpaUR+SHdoTkZxU3YkTDZXXm5NYEtVTD5ZUnZJSlZwSFBmb1NleSRhNXVoMFJOcWt0bWtRJwogICAgJ1F2VFYrP2ZHVT9kRzBafVM+JGJIQFZJcGFuWj9Ab2pSY34tN2Z+KjVnMyEjUCpHYEkkeXU4LVJkaD1FOFRaKzRgSXBOckpAMXhjMWt0WDhfdDdiajVlNFU9U2pMQHsmWm1eX1cnCiAgICAnIzYtUiM9I2VXcUFQdURNUzsxdT5FZHtuSSs2Nnd8UjNkaCgpflBidiRVeDtaKUdSSU49Xz5rYVJmNWM7KG0tei1WOzVGe2wxSmRpbz5xc0xDIztCfXR+Z3V4SVczRGJ0dWhVPycKICAgICdUK2pSM1MoVWRUIXJNIVZMZ0JIfjkkdktkWF4zbHpAJk9DPm08d1FuaVE5Zkd7TEpuTTttN3t+dlRmY3BkdWBGKms/SG1LSVM4XlV8NFh2PzVEKGZ0Xn1uT2Q3XlAwfnhRMFNXJwogICAgJz51eGFgS1NgaGVGckVCZSsmQ2NoIUIod1NpYGJjQTA4cTAtUmpDNnBgVHVNKWVpVT0yJWRURG97cz9sWEZLP2hqbDFzRnxzcH1oaUtgQSlmXmFCbCs/aWw+c0o4YEt3eXhISkUnCiAgICAnVnghVD5WKVkhZW17TldsQiluZlE0Q14mZGJqR0QmRkVCSmEqWFlIJFdRWEgoMXU8JSp2RE8mV3J7NntQdjB3Yms4Qnd6Ym4pSlB+bms3TnlpckB6fmxNWCVjWDwoV2MqdjlpKCcKICAgICdrKD1LPlNaWj5RYkVLN09qXjt9dkQzUkckTUtpUThxVjJePTNvP1JCdkdWd15nK142UDFeSFp0V0dWUik9TFRHYnU/VVUjdjszeV9oVnxNNnBIPyVaVW41dFhwYl5VWHh6NEZzJwogICAgJzV2RWBfP3hYI2xuXkI1bDspS1M+USVae1NoLVZ6UkJQTHlqJXJ0Q2J1PDtGPS0+SXpNd3gpIURXNWVHNCQrY2toTnNURCYwfGUxKjEtKmF3ZHlNd0l0MUozMmo8QFhxQGh+KVAnCiAgICAnO1AyTXFhYlAzcHdeUihoT0wzQC0qRUk9MypWVW99dygofWIzYSo9Z0B1IVAqaTxGfWtueldJYUtxQnVlOSE2KXl5KDslLSpnQHlmbXhDVzIyTXRxMjJvbjJfKV8pcXw3fXNebScKICAgICcxTDtoOW1wSiZMWEdkTEAlITZwIzN7M25DJGN4KUZmazM0bzVJaE8qM18kXjMqS3U0ZEI1djBAU3pRT35BcnZGWVUxVkBXbSM/KF9MazV0NSgpPz5XSV9QITZoYzU9eDJPQFZRJwogICAgJ3pHfW1eU30pIXcqfCVPN0JkO0tOWXlUb3c5VVM/TCFNPjdycTNPe0QmdUV8UEQwMVh0UXtyfTB5WWM+N1A7e1VDNF95Y2hrJFlfT0Q+PVhyKWl1WiNBeUJxSGB9WXV8M3xaM3InCiAgICAnaiR4SmlSLVJOVl54WEtYSHomWDVFRDFrfEs+YVpFcVBybDwwNzBncXlyQDZWKGxsOWNJZnNTSS18dVJxZU5BTDtkUGN7ZmcmMWxUPUI+fEZKdlc9fGBiSmZpdFkpXzgwRGBCSCcKICAgICczZ2hYQGZBWFh0Vnt4PFFac2hxJk5ZRE5US0I1UFZEOXdRSy1LbX5JVnpIQFJGOSVoN0V+bStKclB5Snc5ZkxsT01CPzdvQ25Ja3E5ND9JQT1JNjM8eUZJTSNnbHVpKmBHdngyJwogICAgJ0h5XiN2RkFrWU0pWTNfQTM9e0pnSSZDQ1dFP0omWF97bHU/QjIwZVhtKmxrYkhqVjVqUmZ8Tyg7aUpGPjRoVVcmTih1UHElb2F6eT03QXlze2YjJkB6cTUlPWY+SzVKaGpffCEnCiAgICAnOysmYXkhJXp9ZCpBfnVgSm5NaTgmJn0kYmZgQkcpNXIoPDcjZH1qfHVGOHBGcWdBJHAlMW1AdVZHfHkjXkkya2AkezN7KFdqJTtPdTxycE9jdnhuNkJtMThKRWE2MF93N1o/NicKICAgICc3VWBhM3p2OWVnOyRXQWJUX3ImJm4mNn0rP1I7eCluYjZHPjNXQ087Vm8tNDM1R1hpO0p9Tz87N0JNTkk+WGRTb0xDcD01X2A7aWF5YWRKQDw0RUU4SERHcTBqNCZjYmUxVVhvJwogICAgJ2Z0JmFeMWl1Q2x3RGVnX247M2BXYFFAQldXUyl5QCVPYEJpeGRiNntJVW8mVUspaHY0MS1NPnNxdjdrNT14QDRCSmNeKUtIVERYajBCWDhvazJXYG1oOHV0NGBKYzcpSCVRalYnCiAgICAncEY/MXFCVzN0UCNiWUk9Sl52enFCQClTdmYjLWNsbncjS18yVFE+KEMxdVhCWVojVDNCWFV5LWxETH5eJi1uX1dhS1krUWdoVnNTJFdnK0dsZlMoaDIzNmJwWlJ7Q3R3UGlqdycKICAgICdhYng/VU4/VCVZc25qeypiVXNkcmk7cT97algqRGd4NVFQT0EkNG93fER0fTdpZzticWpJR1N2SkwxU2plN0JMSyQkNG5gKH5IK1VMKi1paCMzdW0rdVdlbTIxfEkjYTNYZEoyJwogICAgJzhDTTtTRD5ZUm4yUlpZdHpEVzxXZFl3WigkVS1sO3pDXzlWKHtESGNuYHIyfHMxQ1Iwa0AmbTxEMU5PKUdIWDBiX3lQXzdLR29CPitgeVA7e2k7KDY0eFEyezNLMzJEQn1sPUEnCiAgICAnbTY+aVJqOylyQXR+cHRqdEI7SzAldyFZbnElTUZQNllKVlBlTHx6IzFlOGF5UmhWcyRBQ0UpSSlANnFhKj91P0I9S0Qrajd3bCF2YFd3LXI5RXElNEA0ZD1KZjV5ISotallXUycKICAgICcoO3JINz5EWlhvUWY2RUg3PThqPDlUYj0xSnB4S3JJN25xUGxwTjJsRG52YXNIWkBZSVlWbiFgPEgrSC0zMnFkcllxODNVU2JZNk5RUCZPRDxPJDJhVy14TFVecj9BfiZTc3NoJwogICAgJ2hrWWJEWjtucDE1blJnMlJfQXQ/M0RTJW0pYjZIPXd0fDt8Qzh6c3leWnVoQlA5b3tJY21zTTxOQ0Q9O3lYcGhyO005Km5NUmBYfmwyLUR3U09UX3t3dXRudXJiRXZlKG07OF8nCiAgICAnPUg5JVNiSDIjbndMaHE7TjV6cmMoZ01lSm4mYFBAWkQ4PllDV3tBMkhDIVNjaTAxK2tKJE0kNj1YQVBXK25acWFoYTwzPl4lPmxUJGtla1VIcm1yeGQjT2BjRD9KZ05CS3RybCcKICAgICdvZiEwU3ZsUE9BZk1VRXNDRXg1ZDRzTXgtb1FET2ZLSVAyIUEjc0w/Qz8xMWlCKTNSXjlkNDdNYF9QKnA1PDJ0dylxQiUwY28oTnlfWndhdEEhOVd+MjN1VnNNfnFJSVkmNn5BJwogICAgJ1F0TVIxLUdZcykmaG1iPUBfI35ZWX1+TGskJU1ITFUzYl9NTG9JcEFFSSQqV0VoNFRJYWNxO2U9Nko+Q21gSGlFZDtmen4mLXs+Tz9sZyEpdSNTdVRvYm17N1VfTHU4NkhjYzEnCiAgICAnTmZzMTdaSlBlV3pTcDRoNVIkeio8JTNwJUlhWXBWNSQ9bEwwRlhfZlhkbTZsVXpQbGA4Zn05ZHpgSmFDRUN+KlEld0ZfMFU4PXV8OFI2KUYhdmt8WVJFM2J1elh4WHFJezVZRicKICAgICdoKUtAZ1NXTD1iUj0te3AzKlExbz0qd3ZARmdnWW8xX31CLWUoeUI7R2ZucHdXS0ZFTjVINjV0MkNpS3lyTDVWaU5kKCh+cm4wQmUrOSpMdFlocTVleUVBREczbUl0TVBWTjteJwogICAgJ2tDZmphOXViNn07alZvXzJEUndAMDZqZHwyalQ3M20oT1VeUiVYdXQrRllPYmVjYHZVWmF4UDh7bnY+Jmwjb152SUApV29nJlAqeFBvX0QjY0R7aFV8NWtMYm5iQ0h9Ty08V3UnCiAgICAnWGleTSpJPEBgbytsLU41SU5iYmpmWUlOPj1OZEVLUU1CY1glVUxteUx+Z1RnUFAzYEQ5RmJBXzs+OCZ4aFlqLVhGY1E4aVo2JU9QPiF2SE1hMHotJGA3MGNtVTxeNm85MitNOScKICAgICcrIUh6VVolYE9eUHAmbkc+cW4wcEtMMWVXPlhkTiM0dmxrdHFTY3wrYTBWQW47RnBKbj8wa3F0YDwoKDR3NC18OTJBckI9PV9NZl8kYCV1YkQ+b0B8MDxSeHxGbGRAKnRPJkhKJwogICAgJzNyNStORUwrN3Nqb2RjV0w9cHRsRjhiI2hWbF9yY0FBRWI2a0BKSWFKTDB6QEhCQW4yRTtBaXtPdkorQERvdl9DclByN3twZ0B4dC1rUHs2Mm9tZXdsQ1Jhb18/RXU1bkd1dWsnCiAgICAnM3pkNks4dEUlKD4/fnBlc081MHxNazJzYGgqPEc1YmY/bCg9a25rK1ZtYnw1RW53TzxWNDd8QTs0PHNXNmgtUGRoKE5SMHNyRk80dFNWTSQ9eU9sWEhhSm9RZSU4ak5XI31pWCcKICAgICdeLW9wZWp4YWU8PElDaDlxM05oail7cWlZPXVYYmcqS3pNMkEhI0pDXnMhLXo1czYlKFJ1Vzs7P0VyekA3U29LdFpgYVEkSkctQ2ElbUdzQ3hNO21sVTskUkZqa0JobyRmUDJDJwogICAgJ19ONlRfemBrQWVzQTJ0QFgrZnhIdyVfYlcqZF52dzs3VFgtVTthbzNDKUllOCNVXzRtS3JLTU1BT0FzejUoQyZtZmpuQFVfKCF+JS1sJlpOe29hN0peMCVYam5lMlI3b21MbWYnCiAgICAneF57PVl2MVcwRTdSMEwmYVM4VSVYcExPbjtjQERDcXQxcGRabGhRZWBWaGw9eCtkeHFCe0M8UFU/NDNfZ3QlNnsxe31CWWM7akJUdGcqan1jMHlXOERibzFqQiNxJXkmTih3VScKICAgICd6a2x6SUU3MlEtJmNAKk9NVHBEM18qSF5lSnUoI1A0VnZ0UjhzS2U5PCpwKDhrQTIlRHVNRiFnO15RdHImb3hONVRyVmE1UVY8MEtCVUdDdTFARmNWcm9nRlFpdjNhfiVUaihRJwogICAgJ1NeWFFid3A9S2duMHtiK1ZVTG52dDVEVzB3dnVIamhlIStTTnFMRjlZVzN6KUd7WHx7b3koQU52UCZ1Yk56NyNDYW5EcEB3NGJ6TjdIKV9TYUhVODNLQH5nSTFZfGJJaUd6VXsnCiAgICAnNihaYkhKZX1TRlV+V0VONjVZTGlEcEYzT3FPQChYekUyVE8xPml2V294RF5KRTMzJjRefllTdUlGJiglSHFlREM9KD5ZXkhobkk8P09lKnghRzFGNVcmazw0PDtUd3QrZ3hgMicKICAgICcwJkEkcj53XkdoPkR7cl42Xm1BfGUoPykhMzBHYzxsP3hUPCUrX09xPklsMlF8RGtedjJTR0dyPkdIPENLUVgoSVg+TyFJITRNZSlmYShAMio+K156aXRTJGVjNiQ/YD5AYCtCJwogICAgJ3MrcSp2KmhgKE1ibENudUhCOUVvNiRyfldTcz0wV1d5RXU0UkpWdTdVKXMpLTJiM2NRQHY0O1I5JD1xSWt0dkY1OUF+M1p0XmNXdGdQSko/RWcoJT5kbFRmWkxrYShyaGVqJDsnCiAgICAnaT5mdSZnaXVqXkJiTVZHQkxKIWZIa21te045TT5zTShKQncqIWBGI0x2JEsrQXtKYW0pOXQxRDVfRV9kNEJ+MT9ad3JFPWVAfUZ0VDdNPC12bVJoNGV5djUpeXBYWSFkeVRTcycKICAgICdIUTYxMUB4Y1Q5SDUjYlg2PnZJZXA9QnJFaVNSY3FWc3JXODZyYUUoYkxQdT9Qey14UmwxMVU/WGptb0tRSk18QGFOczhHezVLYE1oRDZWKEJlb0hBKWJgSzc4bkBwOSN4alI4JwogICAgJ0x1RU1gdG5uPlNFakNLXiR4d0crLTBWeCM4ZSlLWkBPSEVaVmU9bWA0flk0fm0zdHt+ckBuKTIlb2ZVaWBkbTVsRj13KFdzOE1ubVgtcERjbXVVWGw0bCk4UFhAQVhiNTBRSz4nCiAgICAnN2g/OGZFekVkeztjVU1nakk5akFgSHxpNGomI2trezlEUnpmJmlNQVp2cyhyNSR9RCF2TiMkPlhMSUp3KHk0dDh7OTJibTI4TjZmYSRSPXUzeFpxO1A0cGY7O0licWdpayU2ZScKICAgICdIQy1RYUxyQ09AYUw4WG9VcU1tR2pRSSNHVVV3d2U/O18hdmg2TnwwNU9jaThVOWcocHA/PG1aZG9+ZFF0YVVqenp7eWxDcD5JUyNvX3h7aF4jWmRBJSFhYXAmalRTYkdgWGtZJwogICAgJ3Z5KzZpJDtQZ0RsMmt2U1dCZXl6c3c2akJLTUUmQSlvRkBRb2l0U3dISGVIK0VKZCQ/Smd4eE5VfnJ9RmRjcWUmdUtBSmhIZGwyYGA7Yno8dlhAaU1GNVNgZmtQazEwWERqK2wnCiAgICAnZE0qUHZOMXhTVkd5VHA8LTE5SlQlfDJncSo+JDs2SEdNUiRMeUV2ZCtWeSN4VX03ekQrdGU7UGVAcm8tY1d2b0hFUjBGbDtuamxIK2JDV0dzNGc0UGV8b210ejNDVWhkXlV6TCcKICAgICdLPUhLcnNmJGA1NW5jLWklJUtmMXcwd3d7SGhWUFdpIzwhMl9YJDFTNDhFSks3PU41WTRKeiooQTEmaUExflZYUih8LTRzeDtHNFpQO3ZiJj0+Q0cqITBMU1goRHEkdUI/RF9+JwogICAgJ0IjTTRpMGZ0eGNOSkR2NFpXSlZvQHpeUT5UfE9vZipaVCU2IURtfiNsRG1eaThpVTF0QWhLMGhefkE5dV5ESStnWEJ2Xy0jWjtNMHFNeDBoTzQ9ZHs5YyNyUEp2TyUjak00Z00nCiAgICAnbUhzTipkOCRiS2BTNlQlT3FaVF8hUnp1fntSVG1faU5hU3paKlZ4M0tAeGskWH1vKzR6WmNfelJgYjdBKGA9JF9FaFZHNUA7QCklYUhAZEdwem1NKDVLK01NTj5Ve0huXjUwYScKICAgICc+WV83P1phPEh2TVdQS19hKFFhJUo/diUobzx+SEAhK3JuQUl6ajNRb0xHNFZoa0oxM2p4dD49cyVOe24wfEN1RkVaejQ1I0xLXz49ZGolPFM2SjlWK1E8ZmBARmUoY1cwdT4wJwogICAgJyMoOGxFaD9pK0FWZlBJVnUyMHA7Iz5xKUdjKHNqPSRUd1g1elVRSUdsPEJhY3RaQGc1QnItPkpjaTZ+dWV3emd4M2plMHhYdlNDdzV+MSNtY3RvVVpgM04+Jm05PzhUeTAmKyQnCiAgICAnVUwmZWk0Rj56SSVjZVQrN2VPfHdsfHVxWWFGNlBDbzFFKnhzd1lwQ3NIKGsyPUNDTU9HUTR+PDRkRlY2VyF7WERpcm5oJG4oTTFQLVgpcHtAaV5SdztPRlFfeUhKa1VRa0dILScKICAgICd5R2poRCZIb2pLXlpXQFdsbnJmWnQtcHA7NjxuekJacyhwO3AhTGc3KnktPncrSkYpI1J9ckh1PFRxcEJQMjBsQmU/Yjs7eWx5Z0dDfi10cyohcjc4TGd+aHR1UF44Vz9OdVN1JwogICAgJ0M9UjswaTJzWV50TyZOSyNZOD00ZW01KWNvMmVXdypyOSpwYEgxZVJSO21mR2BuN2NidU4oZXkzMERjTik/SD5XXnRaQHlaWEAxYDtDJEpKeWZrUTlUPjI/PmdfI2FKenhqNFQnCiAgICAnSDhVaGpLMmBXflNJaD1yclFKIzFpQm16QjA3QE8pXkg9aEN4fTxaMzsmX1RUOW5zSmwhdHQxPDY3TzRVR3hXdV9yN2c3aVZWUGp9ZTI4PDEtQkFrQTRuI15kZE9jeGUoRyMrRScKICAgICdMOStLNFhYWWI1SH19MWokTzBIamlZNlphKGRkRSlzNDFyXz9kfGlQVz4rT2B5TXZpMGZFVUxwdXh5ZT9ZdWY9Wk0mOVNkMGVwUClxS1EoSUYmb2lxe1JFMEk7eGFZcHJBdUphJwogICAgJ3dwPWE7eldFJEkoQ0VqSG1peVpjTCZgSylDV2VRZlE+JVpUc0FSKGNmbEJlJDFxZj0+UV5wVmRCb0BCT0tSRy1UbFF6bk45Smg4I3lSfEglSWA9bWp7X3stZ245JG9zXmJOd0MnCiAgICAnUS0+NV9eWHp3VzhwPml8amJWKV8zNTJGNntTMkFEWSRNWkBteWhzXypMQHQ2WTExQFM7QjJrQVBzPFd9N3dlbHE5fjEpT2s4S2VlTDJ+ODt0MCZ5X0pUP0c/WCQzQyN3KnFocycKICAgICdENDh0fFFNKi1rdGV7XjlsYTsyM0VEMnVxVDF6YGtXTW4pfmhCSEYpdEZxIW9TaSVaa2dEdzRaXn1Fa1h5SWMpPXdYVUJfPjBrYHp5P1BUcXV8WDIhNjF6Yz96fiVrZC15YjtnJwogICAgJ2U1fmhVbUIxVkYmK3dPNFplZj9QTVdTQTVGIyh7YENTTFkqP1pzb0hEcGY5MS1ZJH5jND93V2VtVSpHTGckfHFmcnN3P1U3c1hVITNHWjJWOCZCZ0grT2NSXkYoZWMtYCNhRDUnCiAgICAncCUmVWZ0NH1JPV9EM1IpZzxwQHV7ZHRCfEtEZVJwNDREdGVpJD5WPFFTQyVLOXZ0PkltP1chXnsqRlNfSntYd35qRiRjMSYyQjt2N1BRPCM1Sko0aHIoaUp9KXd3JnRVSXxQNicKICAgICc3diledjZeaXBrNTNUX3djWDZwZGh5ZnBrP1JPbXh1WD4kZjx1QTliMmVuQjlkRyhURFUtSCV6cVYpQmZxNCtiKWJ9d24jU1YycXlwZ2gjZk5zb3FYcj9zUVJgbHwxPHBCfG1OJwogICAgJ2tHd01MTjtjOUpmeT5jZVg0N0U/TWZmOUQpNXhecyZON3ctMVVPT0JESH1EaVotXiQrUjtyYSVGTGEtbl94JlRsJFJuZSZhUmdlYEw4dH1sMmY2WEN5MXthIVlZY1NgYWQtS1EnCiAgICAnWkwkJFl2MzJhJjJeXmxVdWZBM0p3MDJoZUE8aU4qRVZPTWlJfEwyeTM/PTMxJFlQTUUkJnF6UmkpSlQ/KnM+aX1VLTlmOFV7QituYmBCeHt7UEB7JEc2SS0oUDlJNTRualdmKicKICAgICc1TkNEVylCN0FBdT1XP18mVVRXNkhxO0x3U0k7dikpUFlTcVRENyRjQzFxKnZsc2UoKGk2ajlTLURVSmUoZ0Q5UFcmKCQwZW0qdWowO1kjbHxEYGd5b1ZsU3RGdipCdWd3fHxDJwogICAgJzlLKTY8eld0IU5sY2ZjdXFKZGJYeDVfe3xAPGZ6d09AI01EQzI4PX1jJkUpPlkjc0VQd3lAO09PRno8RmFWSmw8TmFeKyRlJGVXNUNuRXpfMXdSWiQ1TyR9Rmp7cUZYeyVuTnonCiAgICAnSnZ9a0l1bzhRSG09JUwtQm83QEJ3SF98cF9kZHdidFRjP0IpJjh8ajJsJGY2IT9RXkQmP2RYTzQlcXN5ZXMkVEYlQ2I/IzxqMG99ITBwZHFaX1d0aipXXlBtT0Z0KSZVI1IlUicKICAgICdYfUEpYCZ4QzNJbmVHNnxkSlg9Rmd+ZTRSNkU7VCpWJihHNChnT2x+REg1O0slKCR6cnw1Y1FpbjRNbChwR2V3U2pjYzRQYmZtI1d3JjEwfm94Y2hsQmthR3FQJGlmOUpWQnNiJwogICAgJ3QmMVpDNVkoTEp6Y25qbiZMR3s0SX1gRiVzfGwtVjVgYFdPeSMtKSU0KFZNOVZ5Yz55VURUU3pDOHA5Xjk9Zl9vOW5jZ08ka1Y+P01gRSYjcnRBX3RmTVZPK0hoVyomJFN5aWcnCiAgICAneW42R1UtcFFLRkYwWUglbCFtMSpGQWM2eXBxdStgaUdYJDRhOTM2dXc2I0dnSGQpOz0tWGtQYFdgeyRvRlE5Pn0ycFlRV2RILUktTjlpfldfV1Z7JTR2RUZsLVV2ZEg5NG1CTycKICAgICdLWUdWazJ9OHBGeG1XRTZUN0UrbDA0RT9CZjJsc2I8TkNYZFBaWXVaN0BKJGBoaFFQPSFnN3pQPFB9ODdFSl5EcTxZOUt7QztGYG5TMiREYC1QYHIzJnYqbFdDZ0ByeD9NTXRjJwogICAgJzxUcSMpKTNUKzYzVD1rez5seENmJFoqLTUoRjlWbk5oK1R7YjwrRTxydDF2YHdlQ3VsaUA7SD03ezUlYWxMR21FOz5WblkpWDhQKy02bmttVD1eZy0xNT8za3syUjs/cX15djMnCiAgICAnTXdPcjBHe3ZIVl9kRzZFeypOWUAlX0BvUEJ+c30wY1l2I1daTFdQR3ojSlQ2KnI7dFd0djVrd2gtKnRXQjt4NkVBfnVNe0FPVGJzWjJvQ3FtIU4mfTgoREBqPzJ3KW5RUSlCUCcKICAgICdyWDckbkVrfVNMPGJfJmlvUHFLVW90S01objhWNDtfMFZAcEM5OyFRUmpAa0dWRnpMUXB2Q2tIOUgrd2YzV3ZreXctbk0xK2tYPDRmIT53V2Q7VzRjb2s9RFJie0JNQGxxYnJgJwogICAgJ0VYcX0lQ3YjUyQzYj9wMkgkdTY8NEQ0d2c1UldITlE1MD9ybDVlYHlgOTF3PWNaN0JVNDgrbVo7QE0mSypBKntyWm5ifmB7TjlzV3MwRDt8dGYjNkBgfnxkN1k9P3tJLWQwbG4nCiAgICAnMGEmJW83aj5NYk5qKUk0RzhQJChpN0Y0bUE5NU9TK1QzPCghRHI1e3l2OFkwPVcoYCRlb31KIVJWSGFBenBJQmh6U3BaOHpFY0JKc1pQKEBfelg4OTVTMihVSDZBSylNdEk3aicKICAgICd1RkxxdGhrVHp8QiZlQXt0eHFAcVApfl90SDZiKGEkdDJfeUBXV24jTXNDRCQzaVRCYz5mVllRajxQZUhORGxQYyFwZnEteDNzdD04KS17M1o8ckZzWitvNEV3fXlxYiQ2UFRIJwogICAgJ0QkI1gkS0xJfGopPWI8KGZJWmFuazNxO1lqV25fRnlVdGw1eCozb0RqTyszQjhVVyo0eCVDZV84fV80ME9XOCVLeCNwVXRWb2ZNUEI+Yj1qd0o8LXFSfHdvejlMVVlqVjxRNjAnCiAgICAnQkxiXmIreiVFNmc1dXJ+TD0jWSRMfFUmQ2IhKmZzenZtOGF2VWk1JHdWWkdXP3lBRUxSUz1rYE5gdHZ4bFpAJnJfdFA+eGZ1c1AwN3JaUEtYWmRnMktXRnpmdClEcCN2WnBXMicKICAgICdqKjNhTXtIeXoza05+dURPJE1HK1FKTCpgQ095UnI3RSh9YDIhOS1KT2NldSZ0Zy1Gcm5pWTJ7OUN+e1B8Nk5uJVp9RFdeeWxCTiM4enNHby04eF4tM2FNVEw1bClsKSoqSEwoJwogICAgJ0ZMUyRZbGxfZUgoP0k/dzZ5KGg3c3FvJkBkUmxuMnl6LUNpNkR7N2NGVk5FU2QtPDheLVBZPWI7VmVAMlA8S3ltbDdTS1opSm5XVnVGQ3V8QUBkV1VjOCZXaDBAQHZpRU4lb0knCiAgICAnMW5FMSs/S1NvdDA9OzA/XnZ6cD9gOEhBRmdmI0Y1bDZaR2d6amVAI1VYezZ3Y0khdF56e28pYEh8fiZaJTNeZnJESnpwe1FOVnomPmolRFBuKihQakt4X0lzRCF4XjlZeio/SicKICAgICdnb0FzO3c/M3BldFVjXnlUYl8hb09+ezUpTkQoMWlJbSNVSlRPSndRWkJKQnkrYUVaKGR3VD8kUEtaLSowQzhjVD5XOUZATS1WJWp7fHV9a1V8JSEtK0lYa1VJI3h6SnVFbFo3JwogICAgJ2BoRUVAS1FOVSt5aHxiNjFAazlteT40Smd0RztLdilDZEtIY2lne0NvYGp9d1YmMT5tdDxNWTtjIzRQaWJvQk91Rk9GKF94eHghUmdzcDZQa2BxK2NSTnE9QDA/b2d8Sik+M0onCiAgICAnTT99S2EyY3J1TjglQG9Kd0tab2Nie3IpKkpGTzBpNCskX0ZxLSYpVHkjdmZHMzZZayMyYkNnOW4qeTZDSmJ1XzwpZzMtMElsZDExWkteKzFPKih1T0tqVG1EZz1KX0BsYEFoNicKICAgICc5eEAxPihgJkQmQFMxMDAmZn56aWcwMXttaUx9YmZEQ2V1XyF4NW1RUUhZN2hoVjx4SHt0eSNwNlo2NENQMXtYQ2BaNXImUmJnWCFVK0QqWHM4TypmK0p4YWZAIT8rUnhtUTFpJwogICAgJ21jKUVMMkV7X3tQb2N+bGgxPmYoVmhXPyRGdXM2PnZ0cFg7Y3gxbUtUeH1IQGhEUHtSVmFyMDZTRi0rO1VDK0AlWi10YWZIVSZvNT0xPTIqakIyezQ0NlVNcUFRc3JfXiktUXgnCiAgICAnKXl8OW1GdTw3eGlRZ0IoKk1tNkIwKj55VkZGQXJ5N31ZeXxMTjQrKT1xaWlWU3Q7QlZKQEhtMWd9NythYGQ9aD88X0BmUW9+e2RYZmpHcXk3fkAjSllFP2ZXZ212cysxVUF1NicKICAgICd1PUIoJFdzUGN0UzJTcHc8aT51YypTe0xMI1Q3WklNaykxS1N9Pl5fJUk/ajRPcEshaWhCbVZ4Rk9MR0tpfWo7fFhrckhZJGMhd08xJEJwWk12Um5qNCs2QzNec2hVeWs/Tio4JwogICAgJz16fXVyIXNLQ1FFMjJyQHJpc0JePzloIWM3ZHV3S0lwbyRrbXVjfU5PKUo4aG5lN2FWM1JHYXFVQUpKS2p2TUxKcGFRbUByR3N3QE1jSV43c0BQdys5Z0RgOUM+Tj9lYF9zK2UnCiAgICAna000K2RFKWdEQUJ4P3Zzc0hMU1hqMk8tNSRpR0cxTkRtc1ZlLWM2RUFfUE93bTMhZ0tlPEc/ekVObm4mej8mYUVQbUdZVkpENWR5bW8pbHB7QnMlNmdeJT9+YDgreGJjJlB4PicKICAgICcreGE8e0U4U2xSLWYyOTkqOD8obk11bjJvSWp6T0M8ckZFKkVhdzZRU1YreVlCfXBJJXVNM2FPVF9NNlZINFEpRXdzVEY0ISYhTFk5WkBTdCsxZnd1JCViMWV8TGV9RmolJFUlJwogICAgJ3RrT1ktdlRSKjtoP2I+RjBkLSNpMnhvODEyT3kpNS1gWVpxPiNRdXRUVGJVRj5qd0VjdzU5QWI9cnBtKi1ETF9IYFhyc2hpM0FSWTdyXz49WEB0TDNtSkJ7TXViYF82KUx3NmwnCiAgICAnanB+Z3UyXjlybEUheT1aMGFLM2Yze0hhX2BTbVhUMnxlRXdkNzJSejxgSHI5XmZCZH5fSkpwfUNvYlRaWXhiYWpFU2dhLSMhRSRKNyNONWNOcWd0fkQjVn5pUjVWcVI2UHVyeCcKICAgICdHS0JyT089JXskOCQ/TFojMUg3Uk1vVSZWcSlfcHY5TSswO1Y8PFJAU3ImYitNXyl4akxyN1pzdHtWVDFsckI1dVpMVHdsJWNnMS1KLXVPcW55akhgc1Z3VHs7RGZ2ISV0eGolJwogICAgJ2V6JTdRcks+ZWxiQ199aHJoeEV6VU8maXZ6NFdyP2YrNXVWSDtyPHVuQ2B1bGAtWTJrZUYhfFVJYU9VfVI2M2Q7bmlDUXhAd0ZxOCNjPiZEZGVQaHAwNmkhcW4xQTYlUjVLckknCiAgICAnZUpme0M2Z2VHc1kra1FQclZHOzQ/Pm8pZkghTiR7UHd8fXYwOUttQVRRT193RDtWcHYzV0RTYSNBMX5wMH1+IWRVOypqQlZnJGZlRHY7O1VIQDQyIzc9N0ZUWSRiIUV4cyFpKycKICAgICdQZE90O2slRVV8VHJFX2tpelZqPWZaLUcpS0ozQldnPVQ1JEV0V2tJWX5RQkpKOzB4RHdERXg1STY+cG95eFZnQEhrNiRUeCg1UmgleCtzVG55T2BmRlQ/ODkrKChNITl4aldtJwogICAgJzFvKE1MQVlte2QhVzx3bSUrQF9QZ1FfWjRDVShmcEMmdVdgNTwhRjV8M1NXXnBqWVpaJXMkMUtaNyMqNCUpd2dfZjJiS2Q7b3BXPCg8X1haSUxfbykrQDdRYXlUYUg9enxYNmInCiAgICAnITF3eCRYQS1fUisodmk+JXB7cCt0M2c/Z0ZnOzBvPithKFhqUTM7RHp9MWVkbCFvOWh1KTI0MzZ0bVB6emYyKiVeM2E3dWpyOD1iSEJYX0AtRGNwWlNfQllEYVdHX1lBR1dYUCcKICAgICdIRFRFezhGTUN6MXB9TUhqJGIrd2tVdnp0bnlNN013c3g3KEg5Q3k1X3ZaKX1tfEU/PlMlI3QoUyp+WlcjbklWPFRTWmljbl9lbDRvanNvJns2MWg9Q2AqI2YxIXE5UCl6fjc/JwogICAgJ2peeWJMK3JPPkMhRj5PTk1aSEZ3PykrQz9oPl9ETVhgaFBzT2kyIXtRcjA/R2w4ZF5faiRYcyhMOX4mbk4oekQ+Xk5aemA+ZDAqQ2hVfGw1SkhIR3hSdHU9UE5ndF5wTz4tJUknCiAgICAnXigrXzBeTFhhUyFjbko9KE0zPn55aUlGYT1ZOENpMnh7ZGxqV0d8XnNkTnNuJnFIKkE/cH0wQ0FGYWhtQzI+bkRqfiRgY3lzfmE4SDBPMEVJY3FJSUA+UUxqdzQwQzRDVSg2ZycKICAgICdpZUlMd00oOVJ5QU5qPyZYOHchblcoRlJOdXM4OU5ffHIhQClXQEQ9NkNXfkszdXNFOCordF5mVlVIZ0lkMnslVXVFTV8/MT0tV1M5IWlFUFhhbikyUXAzNXtWKEo7XiNTZmJLJwogICAgJzdpSkZjJnBvblRwZ2dmN2ZqITNZajJPeENUPTRycTUpPDRybjF4Ky0xZlpeJmd1NEIxcHpXalV2RUY0K3hINk1PXyRvQEVKP0RWbFBKLTt1T3dfWj1SUUJqandnYGV5OyU3MXUnCiAgICAnWVgraElJKGM3VD9BRHUocXohVD41RUQlSFV1NEdoSl9XbD5gQyYzdmc3NV5ZRVphU301cll1PU1TQUlGaXcqOWBsY18lJjF+dXQxRWwkUCtnbnByYzB+bGxzbUdiQUY2ckZebScKICAgICdle0grS3B+UiFYQXhHd3hjYEJXRmcrZXc3N1NOJn5VPSFgaW0zRHYmTV4zNzEpR0F2NXYqcntJWD1KZXphUyEqbUVMJldMMnUyTHhZQT9kRzYqfXoocVFoQFhOYVBuZXAwaiUjJwogICAgJ0l0Rl97aGV7UXAxb0VEKnpJRH1YJmwmMTBYKjttTFAlNUg0Sn5QM2F5NDg0UTU0IX56N1Y4c0Z5KG18Zl9wJCVqT14hSGgzMld0Mip+Zk56S1R5Tnc1eUlJXmo3e082M3c0bkonCiAgICAnbSRMVDZrTDUpVnZqQ2FNPDtlYHg8T3lLfU9zN20oIUdoWjRzSWpIdDtgdnlSYGZWd3NGKSVwQHF1VXV7LXYoeHQwPHhLKEt7T29OZlBhLSFnQUlkTGZvZ09NbiN8NiFXNDEwQScKICAgICdObnx0LWhyPEkoVlMrT09VRnxAQm91dTJDU0VETEslSz1gJXN9NEpMKEJpPGMpS2xmUldaSmlYJT9aVHNIcHN5WWFPdG0ycWR0bTZWI2JffkgpITloM0MjcGFtfWdNRkhhQTJHJwogICAgJ1R4RiViYCNePDJkVWQ/T19vIUR1QnxoQipqJFY4YzB1cEJXbUVgKmY5Z0tHTGV+eSpAMj0rdFhKLSZ8PVU0am92PkA3SjM7KmM1dDFrSW9ZdUJfZEJCUmc4JSNwRn1+Jk08YlonCiAgICAnaj42aHhFSHM/Qm80aH54cz5wQm5oWVApR1ptckV+KENIZENBanhAWUQyWkxZeTNSPzZWYG55clBHd3haQFN8JHRPbS16dU1GczU1TUpXWXdGdUVOd1YoJV52Kil7KTNyJDFUQycKICAgICd3Xnc0cTVWRXA+T25hTX1ke3N3MT5yZXI4RVZHa0AkS2UhQEdnTHtHLWFvMXlyS3B1Xlo8eiNlMV4wRlpQR1pebCRScjFVPUlBZVM1bWR7X0I7REhTY3lKIT9mckQ7Qndsd0BpJwogICAgJ3dkO3lmVVF7cih3blF3ZTB3M2s8NG1Rczx6K0lhOGlySlNSJiNmRCFsR09RelYtfnA3QjZ6UmhSKyNtdkljbVlmXkB9JVomWFU1dHhodU1AQEZNXlorc19yNj09KktZcSkxbTInCiAgICAnaiZAJk9iTmVSVyh0ZU4mcl5rQVIpNm1CV3ZxbU9NSUghZVByKFNCUFUheWlQZ1l0eWl5ITchVnI0RTZfNWtzYmpCPkBRTCZuLSFhZSY/P1lRYms+NT5XNFF8a3tYRGxEb1UzdScKICAgICdZflZQfnpvWnY0Pktte0BGUHFyfUFzcWdMJGNnfVB0WGUkb3k4QEsyUz57S31rXmFUSVcmPFUxNVc9Nl9GP3hzT1NhQEZZdFFiSkJCQmZOKFNsZDZpbzBAXkEyWjNyQ2t4ayZlJwogICAgJ0VfdnhyZDgjRygte1phTkR5UFk/SHZ6YjM1QiVFd3dQX0k4VUdqXylwdFMwa25iWV4jSHZncz08R1Y3UzE+R3l6ZUBKbj0lM1FRbXBzcH5DR0tBZiM7eDQhYE5UPH5lUmtwa2UnCiAgICAnYz47cU93NUx7I3FEe2ZPY2oqeComJEtSU3c7MmRJalI/VChsMlBrXnMyeCZZUjJRUV9MUiN3TVBhaSFrT2lvPWFlWTNJXlkkTEIoTnFIQmA8Tm5qdVohJkVKaiFHbF9tflYxPCcKICAgICcqcWJ1Jipaa3treW9tWFhOV1dyIS19LXpqSXBqV19oOGV3VjRIVk9uPVF7fitzWihpZXdScElZYm5NMFpfSUpLTFNFfV5yb3teTXhtZ0socj10NSREZ05lb2FuUTZhcVh2biRAJwogICAgJ3Ftc3VWR29MSlpRKjE2NTVQJmhBN3dqRXNxUS1YbDcyV2opR25XSDIhQm5iSSMzc21ZYWcwUzYhUFU8TjFiaSpzTEExMiZZck10JjJgeihCVHQlVUI9QCFsVUtrNm1mSi1gUW8nCiAgICAnNndFKDZKTVpVO2VuVUteMV9WMzA4VUlmb0J8OCZeQ08mZ3BCSlQ0SzJDdys+QlZ2cT9mMDRhXmctPitlXjFZT2sybm1fSUk2SlE3WjlxQCs8NCtedyplZV9pdXZDMmlTMmhRTycKICAgICdhaEF3XyFSZW5IOyNmUlRJMzVaKHt5NyNvZmEkaj1KYEF3bngmeEQkK2ozRFhSXmxqYTw5Zjw5ekohVE95WGltJTIhQ2hpeWhEcDZBTHpJcmlnOGQlYlhQNn5ASyswbjUqRXBUJwogICAgJ21MKkY/WmxNKE8kfWQjTSNnJEt8NlFgbittVXVQZlBEZzQqPWB0Iyl0bnVJK08obTNOQkBTUWpoV1VsMWFmfHleR3NwKzBxfFF0OWRGdHliNDFUJSh1P18lYWZXcUQydlklZWEnCiAgICAndDtJRmxKNWluM0M1JD0qT0ZNTWp6ezlSWjQ+bFE9PFV8OEk5THU3K0V9O2tOb0VpdjtKXnhPc1I/S3hBWkVIemZOVntQKCQhUCsjVHNtTH1vVDgyRWhqKF8qU2pLKWtwLWVqPycKICAgICdvYlpzYSpHVEd9Sm07Wk9oJj19Ykl0Qk17R1oqZkQ/UENOaktuRklFSn5jNyNCVE5+TXM5RHM5cGVAX1ckWDA9aVBYcCpDKGZsNVB3bDBZJjU5MWRhcmJnTyMzYHRWZkdrLThkJwogICAgJytaUHgwRzd4KUE3c1o+SDFDZ0lYM0RUQyRjOGdHUkhxdnkrZFpucnFOZkUjMjt1dDk3OCQhfXVhdG1VNjhZRUcoK01kRU4zLT9MRjImPWlWLSEjI2paSVR6dDRHUV9NdkxofmYnCiAgICAnaCZgVmZfVT1BfHJ7TyVnQXteM1N6UCZEcEEzeTRVUkJxXzlAYzh8ejAwNEE/el9ec25IbkcxWXBAZEhwI15nTmlDLWFLYSlpKnVHZSNjTUw/RClwJDxOU1pyJD9man56RzxRcScKICAgICc9Y3Z5cWIzMWxHUWk7Pkk7JU89VVAhQFAodVV2ckBuI1dNdlpDSkRiRnc3N2JxXzwmYlUxKz5zRXB6IUprPyFHaXE5OzJKc3IxdmlfcGdEU2JnJWtLT09ZeTUxT2lKTnBKMSZJJwogICAgJ3FwTz44cn1aZldobktad0VzWFdAY2AjPXteZHU5ZUNoMHN0TX5JP3YwZU9LdERAcTdJVFVFPVNlUnRNM3lBS319IXA/WmI+V2RzbCROaHRfOG45U3FoR3RuPUIoZXY9SmMkOVcnCiAgICAnUy02Jk9nVkdsRWFTSHVGPyFRdl5kZVQmSGxILVVTY3FGQzteMWBWJTQyNElfem5qY1QkbkRpanJDWDJOb01OaU45ISNuWXpnJSNhQ2x9NDM8Kzc0LWBpbG93QGF1Jkp1V1pHRicKICAgICcwaDxgPTc+MVFIKHtfQENib2pDJj0+cmQxQE5PNFdLckVYTz56eEN6ajFKOUk+RnhsP0wtayh3RSVyayo9UFpZNW9hYyVfT1h9WFd1OUMhVT4xNHdGSHl9fSlrYTBMOHc/YD43JwogICAgJ1FuLSh7QXM7JHlXSzFobGdMOXQmbzNjcjdzK0VIQS1DX1hpPExwNipAcnAwMmopclBleFlJUUBtcmN3KEJya3hNRGNiUFAzczBWM3JWR0syR3FiSV9gbU15UnFpMVpjS3pfb1knCiAgICAnK3pjSCheLSk/WFFPR3pAYFY+Wis9e1BPMzN4UXxOcHcxZzE4YVFOWGxONDMqOUVJXkVxNUJ4eyZvJWViUT90IThXbmRGflMzREA+ZW49NXRwMkM1ZmZCMlZaY1R1WmM9PTRTcycKICAgICdkdkxzIThXLSlXSmdaYUdeWW9JI2Fvb3R4c0hRYjVsajRRfmdhVnkjajIqRXxJWXo2TmVlfmtrdD9JP0drKDc9M2BRWHomUUheNktuQWI2QTdBPDVISDE3KnAkbHFNMmpqckhQJwogICAgJzUpQWYjPEV4WGJOSCN6Uz16fWQ+PmBYcFdmajR1WTw7SC1eYjloKCQjfVJlM05AWGI2P30qUDUmMTBWIWlueWtQKmBxPUNXe0dPQEU+QmpAQiljbjFgTUBsUE9iM1Z1PEtxYm4nCiAgICAndm1PZXB5RXQ9PHI2aFo5UzM+cypYaTkhMVRoNWVWajRiNWhhbTcocmt8P2NMNFdCPzQ5KXMrNj99bTJTYj9QSXAzdE5CYzZXKXQ3eGxBdTJqTzthKEJ2RkMoUUJeakxnTUIpcycKICAgICdAMUwzQSgtNmRmMzRDOVJpQzV+JW5EZiZYe2RWZHstaXgjQ1B1RUQhdTRDUlgoUCR+P0RhWV9IOXNHe1dNaUJUd1kyWHJTKk5PJSRZNjhFYUVrfV8/ND0xR0NTN3BSJVAoSlp+JwogICAgJ0BePktpWkkkZ09ab3ZDfXdqZU5SQkApVV9GKCVDNyZXN3l4WUgqYnIyMGFJd1llKUslS2VpZExDVFhvVzwrJTlBWGBsRHwka1ZJdHB+SipCTXRyVyNzQnJhKkRLdzk8PTIhSmsnCiAgICAnP2NOK0QqdjJwfStGO2EtU21VJjtESUJaOWA2QTdXSDkjd2xIMyV5OGpHJUkqQ0N3MVU1YykoeChCck4/KSpwalgqfmhfSmdkPisxdCVySTdhRjVLJDhVbWBOZVN3QFgtPDtEJScKICAgICc2JDE4RTBqUFRLKGtDaGg2bGlsUmZiKHYmMnZrdyg9K0VZKkJjQzdycih6SUw9blEwbip0dzwyMTc+Wm9oVXVAaT8/YV5zRSRfKmAhcGxnXzw2X3YkSHdGeG54ZEskREF6MHttJwogICAgJzZBJm9LcTBhXzR7NkhvVWxHKkYyP0hSXlUyTXw8T01JRCUyMFdHV1JyPyUoX0k8eUxXcGZMRG0xdC1yWSZTX35HQy00UyZ4dnFlZ1dheH5pOXg1V3pKczVzNiUjSz8/OU1IJEMnCiAgICAnekljOVk9ZGJCbWtzZWtxVmZEUlcjVVB7I19+NUNyaVkyVW17U0BLMlomZm1PdWdONzdqfXkrRUZxVkheY1U7OVVYczUjfFJLcDVOP2AtQzteSV49WE8jNzw1Znsoc2RGUXc2aicKICAgICcqWDZNXi1zVVllSy0/UVQ5KjNVKktlcmliYWZgZEpGVHErWVBwNG5YTG4oSSlqOz5WMFpJUEVscHhRajVTYXw3djQ/KWxfI2s0c3JqXjZ1OF95UyN+PGBHV2khclBhQihkelloJwogICAgJzlwVlY0THM3QzQ2RXR5Nj1iPClmJTsyMD9wTndxWDdYZWU1I21eLVcoUlpXPHVFX08yTWV2Tz9QbDFrRTtFcyVrblY3JnBfeyVMVGF4X1J8Nn52alElZDh1VWtAKVdSbiVvX1MnCiAgICAnKEBRNC1yTEF1c28yNVJYKzIwUmo5JFI1Jns4bVd4N0tXblp1Rjt6d2VqZHQ8JWRnbzZfWG8jazQjNTRWe2UrVn5iJVdtaHh3K3xFbHBTSTUtOGctenY3YEdwZn5TVEA9MEUoIScKICAgICdWdD9IaE5KNmBeej1VKnF6UVB2bihnZUZ4ZSRZKllSWExvdDBSVTc1bFFRRmJMcF49NFUkfmlUNyQoe1ZQR3ZPZlF3SCEmViNKZShRZXU+fSQjV00rYTh1JjwhMko0KzF6dyM/JwogICAgJ0tVWnM/Jk9yMzM/OCZFdTk+WkY+KWFTIzVTRGxRN2Rjc308NmhUbGZmdis2PEhDMj5QZDNWVUFBc1AhYnNoOVRAa2FgVGkqUH52ZzQ8dTlTSHNaNVltWXFTVGtBSm9tUnlha3knCiAgICAnZHBsWWQxdXc0QG0jQWs0YXBJdUJlcGE3LXlxQndBOEhCOEliMEA1WjxhLTJWVTFMYDVAfE4zYzZlSCMlXmM3T250dDFkTGVKVm1AYmxIIXNxeHtmOXJMVkh4RWk0TnBJWGAxQicKICAgICdMTjFHSzYqQ2NvJUtgaGNmdT1RVDI3NGBPKEtta3xWbnV7ckd3PW5FRkgmYEZEKzFUN0xYNnJeZE9fdUFfT15xUjYqJlMpZEA0emIyNCpyLUFkKHxHMU96Tz8pP3MrVytlJkBlJwogICAgJzZ4VEZ3VFVgdTdLcXA/UzhER0tBbXsxfVc+aiEqQysxP3UxLU9RYW55Jj9gfDV7P2clUiRmVUooQ20jN2FaOGo2aEgyRWRARXElTV5Bd0Y1bDA+eTlXNSZafEBIXykzKyNNanUnCiAgICAnQGo8RXtvWm9jKGFlNE45anEleVc0MFVJUVglbGplRWRqXj13cT4/IWNNbylCdnx6RCEzaiZZYV8pNWhsOGM+a08rfj9xdUZ5cSUyP3dnMyZBU3RpdVJ+JiU8SmAzRGZGd1d9PycKICAgICctenlVU2VNaTF3NW0hQW9JPl42PDxJSm9NQGB3RyNiYktwaStuZ0hxZ2hFbyNXVz93TXNvSlNxVm40TmNkUWZiMHU+P3liTTBpU3Awd1lXZjtmOCtjTnleb3ErQnlmajEhV282JwogICAgJ187bHBkcnVHI1hEOX1QSUNjVEx0VT00XlptbVN8Vjw4aX1Sa2k8eU82NWYlTjxifT5kaS1CSm1JZnhxQ2w1MDVEIWB1cDZlUmFzMUxRb2pncmI2XlpQNjwmbyhocX5PN3EtfSQnCiAgICAnVlZwPXtJeWYpdUFrP2ImQFV6M19ueFlWfW1hQ19GOGh3UmBQYj9ESD0wYW1eS0JlSCVSPEFaajBHTFUpYHBrYWhgSlJDeCR2flJBejdOeEtXa09UWUZWbVhZZEI0b0BLKHB7PScKICAgICdMPjw/X3NQI2JqZX49bTU0O0JOejhWMVFCKkZMZ2p2cSRFYilwNEo7Kn00fXoyTG9JRUd5KExXK0ZLU2NeblRvVWBDKFBtWSNSJj42Umc9Rk5DfHAkMmhjJCsme2BtJjVVX19zJwogICAgJ2lvSW92QzVtIU5CYzBtVEZILXpNYzU3YFJKPzV3RndrPW15aE1pJmpTKlFQPDslfiFfUntPPzNgM0RQMUk5VU8mcEJsd2RLQkZ2OHgqLXFuY296Mz8zZ0B0VTslTWR5TVpnTzgnCiAgICAncXxsb1A+bShgKVZ6aj1GSHVLQSVjMXMwdy07R2NhUilFfHA9Q2BadT0rKHZ8VkViUyQ5OH59MnJyS09ydWImK3VId0YzLU8xbTZ5REZAb3I1TU8qeGUoXnBWSSFyaEhWPXZOOScKICAgICdDMEhNTTVoS05FNGdTKEcoK2BHVDhSZmd+dispdHxLTTApcFl5LUM+XkB0Xz9QT2pIeGYqRnctPTl7LU9wc0htIXJnI2thdH04T20lWntGQXlKY1Y3e3p8QWhfQiNAIVZqN3RGJwogICAgJ0dpV3F9ZThyOUt7c2ctTlo7Um5gPC1PM1BjUDQpXy0kQFIrJFQhU3FnZT00anlwVCg9TyZ5RlR1c2dOaWordykzUXJKWm1WbGJpdEgxO1ZfOHAyOTllMHchNHp+PzYqaX1JSFUnCiAgICAnaVN7c3x1QUowfkVrXzZzSnBxVT12WkA8cj99aHdrKX5WS2oyUWd2fUx7Y05qNUc3bX1XQXl0Xi13WUc8cEB9NSZGLVM+dnZMPCt8Z2BQTmFhUFlGbnZ9Qj5ZaiE1Qj54e1BKficKICAgICdsezl3JipNOVMxZ1ZIeEh1WnUpTmVqI1NUZkN0MWpVTj54MC1fSVl7ZkZSfVJHfXdQTXo3JTEockpwNm5EPyNYSXVOJGZ5QHN1YE1XIzJHc1ZFJUp1K1FfJSg5bVJEaT9scGJ9JwogICAgJzwjaEQxbz14fHIzbG5ucUl4aUsqV0RmPnVaRStBa2hwaHRIa3RLWnElamopPHU2Z1dxUmA4Unp4MkcqUiEjZj01ZCQteFkxeTZ4VUBCS2QkYntZYUlLUlpGb3N1ZG1zb2N6dSgnCiAgICAnVlpTTyY7eik7bEA5KmpkZGhqIWF5c1AmPSZVQGdpNFVGM0luJmJMRl59Uj5EQXpNcDY0PUxxXj9VS1UoPGVMNGUjTlkjaUIzfU0yVyZ7TTg+Rn1PPTlDIXxGUHAxdjN5VXQ5OCcKICAgICcySjBoUylQMV92cUF1PUU5YHB3O0FHNEo+MVRJKyY7ZiVzSzlGdF98THhgPG1xZFI0V0JuKHdyTXxgWCNMZnVXcj5MIXg3ZDc1MDNHUVl0LWNXZ2FuPSk4OXRNUklTbldRaEo3JwogICAgJ3pRdmhBP05NQmliKCs+MUg+WlNXZF92TFk/Xk5wbEpuZWZIeExmTGQzSjZ9JUV9JUdoQVI+RDFGR3Vqc0V4YFp4NjxCZlA9MWNFM3B3NUE8TCZCVjdrWnglQUwwZ3ROMzxXVTUnCiAgICAnVXshRSQxNUFPRXRVe3ZXOztLUmx5U0hpbD89KGZETnQ9KCVieSN1RVE9cilJUVNHQn0/dnY3PUkxXn1qKz5iWDklTHFfPmZ4Z0Y1WX1pRXJXPFZ6QCtgd215VktGYzdeb1JaWicKICAgICdpPnBZJlFWaE14Y0tGdlZsWWAhZGFtaVYtSStAKEtZcSpoN1RjIz1+VlhQYEozY3R2TD5nNlJSMEp7bChadHtwXmpxN1hDcSUmPig4Um9mSVdDRFgmSDRCMEtqKTt5UD5eIyMxJwogICAgJypoOChNMGRYa1RHSDhnbmBLfFVARmgzJEJ4YTImYWl1NVhPVS1HMV87Tmc+WFFkdGUhWlZoXjlVdHZXYz43I2FHMVc5WDFfUWlZQ2RSdXJTWSRSaileOUV+XyNRIUQ7YW1nJnknCiAgICAnOyRnbWspXjl0d21yJUROVFhJN303c2J2ekN0dDh6QXlCZGkhXj9LRUVCO1JpPjUoUiU4KTxMUVRGOWdAN0hJVkhDV3psU3cqLTVXYCpoOWNLYE19blk1UmE/RyV6SVRfb21mJScKICAgICcyREB9djxnVDw7QT1NKH0hVTVwUmV1WCF0QUxWSX44LUBJc0dadDF1c2BNPXdnOTNWayZxXmtQclZRRSg+KF5APztXYlUzPlkzRStaJjd8XnM3RTFhJFA4RHYqSEEqUT8kaCpEJwogICAgJ2E/YTxCdiVVaz1HbjIqM0B3a0RnRi1YI0QoP19BOUJDNG1KViNfeXghLXR1I04pOTQtT2B5TmpAZVBfdmxGd2NJQVVjXitoeEZlZ1hOYk8/eWtTYW1aYnw1fnJ6PGk3PnFoPkcnCiAgICAnX0teanRJaiUmST5WM1QybmhWYGpwP2ZkZDRFJEoheU0yYVZQX0QjOCQ9K0lkU3BtSWpPITBtI2ZgcD1PMC1oe0FRKz0/fi1haEZNa2A2bSpHRUNuNGA/KnJKd2ozQmhqTSsrcicKICAgICdfUnt6dWdLcXRCP00tO1VEcDhsKHF9TStxUilYeT9EYy1yTjhMfiFnP0M/c0I8OTU3dU5mVWY+SX4tPlI+UjBOUiZBUjt4aWxrIyVWaz1TdElhQ05HdDZZVFVMS0Eybz1uSmlPJwogICAgJyhkbjgld2NAUyhFRFdQTWs1Wmo8cXtqeStqc2BkZ01jRU1hYiUySnglYitDUElfdmN2a3NEV1o9P0VNenBLbXIpUDlVJG10S0JXJCUkOTU0eCsyejNlSjRNYC1pekhCVmJhZXonCiAgICAnI1hFUSQoYXxQRncpUitDRzxie35rYmwwMCEtOEg8aEclQ25qWmMmMl9kR0V1SCYycys0WmwxISM4VnN0ZikrPDVSZGZQJWpIOElkfEh2OCVLIyFEOFByMCZAVmZ1Tn5OMDtpaycKICAgICdIMmokRTUjWitOV0x8RD5AKH45JG12Jn5NPFRgRVhIVkFGKXE1UTVkcnczQE5EbXhCVDZXb2E5KnAoeEU+Nj1BRiZCZUBpIzIhfF4wdT5YVXl5KipAbGFFVU5jMCVCS3hLYng8JwogICAgJ3IyU3MxS3RgSFduJmpRVj9SZW51dGB7MV9McXxmJlk5Wmh5NCpEQEImTUBTQk5vK3RIe0NgeFY+MDB7JSZ7TjlrRmYpO0V2N0k0PnVLKDwkSk9uNyQ1ZmxabVFxJjJQdD9YPHEnCiAgICAndTZkKFdpMXV1QyRUJmRUTDtEZiVTZ0YmLThmRj93d1dSJComeT43fStmcmY+RjBXdT1sbXlYcWtKLW9CNj1OZ1MtYXc/UGc/NCQpaDM2LSk9QVBUOSh8K01lYURfai1JMTdeJCcKICAgICdYfnUkZyk3dXYkWnd8e2B6cTlAdlk7MVhnZGNAPUxxfjR4Vlp6YkZrQFlsc0xMNVk5PnZmb08tNFVMWGJKSEo0T3duTmlfKyhwWDI9QVRMRVQrSkxAWEV2OTJXYyl7NV8yLXdDJwogICAgJzQ5OEUjMHQhc2FyWmB2PEhBUntMK01VV2BLfkFJNGhmelVyTSNHUEhFJU5wK1UwVWFnP3t0Vl5LJk9LNUkqWFU3dTtqPUREbUt+fkRtJGMqRjtESWdrP0wjQCVHYyh9diU5MzMnCiAgICAnY1BSVWA+LUpAKE9VS2YjSkdkb3x7OCReWTdUVFVJREZib2Zpd2x5K3krTzFWVUFFV24+SU9iZS0oMF9aUjNwS2I/SW55YGc0Y0xaYH1PNjwhaW0mfnEkc0UhRjZjbUUqQlJZbCcKICAgICdtdlZmTWMmenk4XmV3M1l6Vj16fCp+Qj1QWDtpSjNhRWRod1FVMEA9N0AzYzFyfTtqaTFPeFpvU1QybnchXiErfnswPysmbipoRys8cXBWKlFgfnoke2kzZUViTntFSmIyMHx1JwogICAgJ21fWjs2b041dHItMXhDO2klNlROVUVJPTwjfVRFIUp+S3x1ezg3aUphPz5qI3lvdSFjMWZ2QkA1UUBqa1RyOGR4ZiNFNTt2aClzc3VXN0FPPnNPc09vQEJQeXJCIVcwRUFzIUMnCiAgICAnY30mP2gqTDM7MjliZntgdzJHblV5LTZgK0BJdFUjbWw9Nl8mdUs4SHteRjc9Umc8JGkpbnBGVF4pIzQtYU9oVW1kTD9yWE8hPmElT1IqTXFFRH41LXQ0XlF2eTVNSUUwdSpLbycKICAgICdkITBWKGtuaU41VzNuMTReTmxNNl9TbXQ+WERgTEIxTmQrZFpffUpwUih5JSY+c3NycytWVCRDeyhoeXgzPm9fNE1mQGhwZiN2filrOzBqUU05dzM4d0h4ZGFwIS1KYC1QNE45JwogICAgJ3soRzF7O2M7cExUMDBEYktebVh9XkhuVF4pXklaZHkocSRzTT9efkJsYkZIbXdKWTx0RlRQTnc3JD9rLXZBLTE0Rn0mOCtuUnFxJDRmeG5HamM5QyFWaFMoSXNgTz1LcWRufignCiAgICAnJWA4RDdqPzspdkFAKFRvVHljc2xsUW9PNlBGSUorI0E1KiReR0xLc3A5akNRckl7SyZxRj4zUDJnJXF8MCt+NERmS0RtWkR1OXlTO31HZ3k0Y3BEWHtnfFkoQmckTkV0JmBPYCcKICAgICdDfjFGeDNaOzM8SW94MXcmJjZHcnlINyNoeWxpQytmOTsmZzRGLV5KM1g1SENOJnxeYGBmKGM7Mmt9SXNVTClUYDtDNk9Hbz1nOTBAfWB1bHJtayVgYllgKmdJYV8kZzdzNX1YJwogICAgJ09DQGtmcC0+YmVzWnYtSExgQ0ZOemVeT0p2eGNtPDJ9c1M/I3lHQTx3Y2Z3ZElhZDh2aWpuNGgqeGcyQmUjdiF8bz95bzBkUGcodyk9Qz1TQn07KSFDb2YzPTw+WE9sUWl3fi0nCiAgICAnKlIobnluQ21QI1EmMT0/U218OUpeUHJTRU52VDlRYn5KfSplbT8wJT1XYEYoQCpvU3k3NiEkNVM9N3RLX29WRz9eVXB5YGxUISphZjNMbV9OITE/TUZEbiU8UUp6e3MhVnwhNycKICAgICdhR2B2LU5LeStuO2oqVmJmZnNefWYzYU4+TStmKUtNfmZtSSQxKnJWV2hLMT9iNmMtO2tLIVZUbyFzVXVNLVQkKCt3dnNCSjRgaUJLQCNZZV9MNW0wcWt3SCk3VXs5cipqZjxrJwogICAgJ2lBc35UKy1wanNFP0ZGIW16LVBrVjI0P0xjUk89U3lyZC0tYHBfe1lFfnc2O21tdn58I1BDbXozSDkoZkN3SnNAe2xSd0IqTGlnVzU1JkZJZU9SLTY3VCpOdT0wMFI0anBPdzwnCiAgICAnWnQkLSNgMyhgcXFPfn1XcXN+RyFRczZ6KlUjODBLRypiYj1OQHd2V190Zml6NVcyVDhELWRManpEanNyOShiQSNieChSPHw4ME87IWVIWCVFQ1Z2Kk5QcSNAT1ZOM08qSmBQOScKICAgICc+ZXdqe0NfNCZ7emx3P2crMilSdE81elh+R0JJNyZKalNmY0pSeUdHLUgzXkkkLSgxaVojSUc5TXtGNzxNZE1CPjhCM1hEQXNrS3FMPis5M3FoQ0FVIXA+OUduYjVxWFB+P35uJwogICAgJ2xfWjRuUiV1fTAoMUxZVEdiSCQ+NnRzP2lzXjE1ZFIlOFErTj1sMGdsODVQTjVMd3A7RyFXa1Z0OWc4bzx1S04mQXpCQyhuSWMoOz07YnFLTlJDI3xrS1FobFctOGQ0ISE2NjgnCiAgICAnWkp8ZHNBJmplQE9HcSZjKCEqTGZUWjdvay0obnNwMClYfjtoZTlBIyREaGIkKktPTDY0UX4mVEBPUj9WNlZgPDlpQnwodF4xKUVSP2pgdlRTYTx+Wl40KXZqK15UbGt8Sik+UicKICAgICc7I1NDantud3U5VGV0bUo8ZSY4aTVPTnk/emk3UEB6dmxSOHpYZX15Vzt2VSlaV00mMV5uUih4OUdaNTs/fGYxUkQjMiRgJXFkPzJYQ18pNz43dlhsNXxKJnFGbiRGMWc4I2t4JwogICAgJz9QP2UxIW90Ym4mWGcmbUpUe1ZqPl9kTShAaUB4PnVLR058eTJmJTNrUFdlP3NXN3pAMiMweFJ0YUo8Q3NVezBla1JtOEh0YWx1e1NkKUZsT0VkMGE7TjN7Zj9NUEEtNG84WkwnCiAgICAnKntMZUFGLXsjN3w4fTV8KDdvdyMmfWowRVdjO2ImRVo0Wj5qWVh5OCNWdH5AdzxnfXZNczUtODJIZkRmdG1jdlNrWWtmfGA0JEUxU142Rm5PRkBHSCVHX3Q5MyQkI2d6YWtUYScKICAgICdLVSM0WChgdzA4dVB5aTMqUVA/Qi17SihrOChxKTtsMVdkJmM0fTk4PTFhc3ZIfEgrZ1Z+MmJAXmJWISVybko/eGs9WmpURyZnXnY/JnE4b1R3dVFKMChoeChtfkxUWlgoeUpAJwogICAgJ1dFekJXXlEqKD48S08rS3hlTnNIbGx0RT1OblhzKyhSY1lII2IlNzglbXVoTVBwWWRWbDNRdGU7RDs3Q199P1lWZ1hFb1YpVUd0ezAyfmZ2JD18WnEmdEJ5XlprSWJOWlYjbDknCiAgICAnM3R1RUh2bmB7PkwtP1UrU0duPXtqb294VDNvZFEqXnJmPn1PU2VLQHQlP1Z8Rkp7NCZIZHZ5V1cmRnQhZ0goPn5tJT0rRUFfUlBJeWZlKS00OG1HYD0hWVg+SV8rK3Q3UUd+PycKICAgICdlN0FkKSk/PSV+S1NwcDVRPll3U0hrb1dHRE4pSS11QipEV2l3NnAxSE1zKkNVdypEITM/c1NAclJXekd6WXA7MG1VSEwrOX42c3lJNCtxQE1ASE19NXR+d3FTRSljQkhFe2hlJwogICAgJyQ0PiQjYFJ9THpwT2omPCtWJkFRSkJYayRUQDgre1lpZk0hakRDRDdYMmxFVnpARFk8eGNMd2JjP0R4Ml52Rn47LVI4NFEkNGE1fnpXLTJZYWdjVjR6UzdQSFRodCZRczRRTCsnCiAgICAnPiY8bjBXUj9JcFojX1NQOW1KaSN4OFc/KlFkTi1TJTUzI1V0Y0NqIVYjazN9Yi1VTEk1T0hPSEJmT21EdUhtLWt4S35+djtXUTAtUVFYKiZCLTk8Wm5BZHY0djZrSXUtU3AlYCcKICAgICcmfWk4NmVmN2E7ZXpiezxCe3hpPy1IPVI8RnIkeFd4dFRlWjkwR0pYTEFIKCVqTi0yWl5eKVVAKld9ZnJMJl9SdlBCNSlLYVQkanV0bVBXKXgqWG9wKlBEKmBUbXtSPm1xTklsJwogICAgJzhsX3B+SDRUJkg2KD81SWNBS1RzdEQmTyg/VzY0aGA4aDw7an52YyRsRVhgLXFgMj89d3BhKVdJWHtpU0UzdjQ4RFhScGBxIXRwWHpUJUNSRFlyLTUhdDxOMGI3XnFTaFhuP24nCiAgICAnYFF8YmRGPWhaQGUjWlhnVHBnSHJeZ0VsXlclYVJZeUF7SkpVP0o0Q3srYmd2THg3OHkoS2lDbkxfJVRZOVBmYjVUdGJTemJqc1ZuYWxufUJsPGhqYDE9Z3tzLXpBYjJwI2Z5KScKICAgICc/Z0lZJW99fHNUYkdKYit7RWFPS0d9S0ZtTkpnT0ZaSDEtfnJFIXVjUDE7YEJAa2YhfGx+dE03ZXRNNEJ7R3R9bW12KXhjNTkrdFMrYD0lQHF5QDxIeHBkUmRAIUhgNF83amJ4JwogICAgJ045Q3BjPishTTgpZkRmc1RqLXpqZTVsSzw1eiNkX2o8JiZGWEcod0otZk1AWmlUcXVveUQ1YEFMM2E0I1hXWjN0QjZHYmkrRWZrdWxXJWc7S1FHbzN4N2h+aUUzVDF4PGs+MEgnCiAgICAnSHQ9SFNxMTM5dEhwdlAobUdUek1MZi1CbiU2M350eXcwKzJAM3xYO1ledTkoVF5ZMT4/Xn1WKz9kSUBHOEFodFo8cUwrQnhHVmZRS0Y9Qj42P3o2aTBwX1VURk1LdVBvYFRobicKICAgICdmP2Y+SylAZCtgX2Jid3lgWU1sVCM0aWFxVVJETU5tcXhuXmtVQUJ7NTEtKUIje30md3NlWnxfWUFCNUpUd1pBY2wmdzQ4NihIJkNBcmRfUmttYzh8ITlrX31XdXdPYTZRQWAkJwogICAgJ3Nmcl9mRzIpM0VGOXVkQj5OK2J8LWpeIWVOezQmP21LZDA1ZFR2YTxhMX08TTthdGY4KWlSRlNpcEVaKjJrKyN1KGI+SW5oYz9gWDhadXQ/Y2J7UFBpOSt5PCNsP3FJYD01SlknCiAgICAnVjxwMmozbkYjNVpSN1UwYnlZRFJSMzwpSUNxM1hOKFEkMnloPT1qZWJPN2F3K1QlWkpffUk2fnV1M2QlOStYJGFofnE1Pz4zSCtQQjwyS1lYc09CbT87Ql8weDs+QGcyWntWbycKICAgICdeMUo0JDNhNVcqWlV5LXRKJiNDazUjc1pMS00+c2g0SHFkRkQqbkAmNnl3fnhBZ1FUTj1xTHo3d09ZcE0wRHlpfSRrLXZ4WFp+aEtGWjFQZXZafS16QUl2Vz08WXFJUXZ+N3A5JwogICAgJ14/K2sqY342P1ZMNn1OaFVkdHplZCpkMD1JQGxrbjU/LTZ4OWFfc3FeS0xKMW5SbklhbiRKQWlIMHFDYkEtZit5NGombTJudE5heHxIWjI/WmM0fHluJTcjQGVaKWk5JXtHIzknCiAgICAndVRGdGdBfndWeEs8MzU5cGAmSl41Xk9PMzdPLS1NVEllJDElNVUtSFczTlk3TDFXWjxRNXMtVkNoMDUzIWJ1QU5PaW5RUzM7JEM2RHhESTE+UjhUaCsoTExCYXhofWRqayQ9eCcKICAgICdNezRQTGk7fXRIX0Y0PH5CYUEjZmtSKDRjSHZHS1JoR2xBVG9LZ2EmUzRaWDM2UnI4ZjVGNFZDWnJTKj01REkqZnR4VzVuV0FVJT4waVUhX0xjdy0mViNLanNgRW1UcGxLTCQ+JwogICAgJ3RPfUpldT09d2s9ZHZoaTY+ME5wMk13Ryo9X2slcDJTJCl3MiVXfnd6Q1IzVHR0cC0lQFo/MHBaRktZTkF2KCYpeDVJfkhvXnRaK0A1SFJOdkI8cnYtZzNmWlAzSXpAWExafm0nCiAgICAnIXZjLUt6IyZJRFljWChIcTV0Tl4/ezVmQklRdlBDcnNEVjMjLXQtTXo0TElMWGFWJnk4ZT1XYT5edERyNz92MmVoRmM+X0peWVVeOHFPKjI2Qy1AUDQkVHo4I2MhOHYrQSo7cycKICAgICcqVkdJO3tFYFg5aTlMXzdyRSokZT1jZ0BjKVVRKWE2TU5+YEMmOCV3emg0ZnRzOFhXZ0tLe3hKdyp3cHVYaXZjc01YaUgyJE8+JXZlPnhqJXFFZmQhWW9FT3hAKVQ7cVhoUHVTJwogICAgJ20qU1lqVXw7WHRHSV90ME1nTEM+ciplJD9MKkt3YEN9fi04dHxOUnJZRnNXLWp0X0NDSktLcytBYG4xWDQhVyYrWXVrV0s/NCUqZXtgMihnb0FYJUBHRUxEb2A1VE9wb0gkPGMnCiAgICAnd1Z3YWlWeEVfSlI1dWlDJTBeZTBFajheaVQpXmhOMEIyaT4rOEs1IThAUXRwNkVgTWpUckF6Nz92NFp8JnJCYV5HaUo9K2ZVMkchbSF8eiZEZlAhdTB4JE57O3NPKGpyS2JabycKICAgICdkRkFmUFopNjVpP2hWaHc+Z3YhN3xIezR6bVghJjRje0xTSzRVPih9IzJhVk14OytNdyNiV2o0emk2RVFGRnJGMTRmNHUxS1Y0WCtmO25zfClMQH1zUGBaTXI2VjQ3Q0pXPlk1JwogICAgJzJae2lMYnU/UzBsMzVoa1V1NlZUckc1eGZUV1JCMUVNOXwpZSFTbn5JMVN2KitpZ21KOD9PViY1Pnk3ZklYfk5FcyVuV3JxSmtNVj0kUXVBWnA4b1RXdmIoLV5DI0w8O1RITGEnCiAgICAnOCpLOXFUeWQ9fEJtJmdLNHo2b1EtKD1MbFAqIWZ1UTZnJD0rNmpYTShlUHVsbThEViM5Tzw8a15GPCR9RnRqPXZPalo0ak0qPWx+PSRVPDJnfXd9d2hwIUROTFU5akl0TEV7bycKICAgICd5LUh3NStfVlQjdVlPLVRwbis9elhvLXo2bklBWU04QSRGdnRhIzV5ZTlsIWhvSjVRQDJaKjQjZjZ3QjEoZjlnNE0yeTtOSGEkWkRraH58dXpldU9TPnFnPF9LVFBtWkt1ZSpmJwogICAgJ2hBYmp+d1N6KXN6aD54a3lkSUxYbkhsM3VfSUNrfE4yVDdOOEtKQHVIdFFjR0NGcG10dWBNTygzeyMpQGw4KjNYR15AcW16N2g8d0c5RSF0M0hsNX5hI2xvaGhBdlVQMV89NWUnCiAgICAneiprYzFockdpdFZlRnFuOGtWMHRyS2NzbUdTSkZkP0c2RFQlQWleNFFjOGpsQVkmdyQhZkgoKms7LWRaSFhYcWdeUDNmeylqNChxeUBXRkd4YnAtaEYha2MpYmgrcmNOSyladicKICAgICdkZG8yeGFPMT9FSXRhM1pGMjlpP0l4PX4zUmVaMWxIcldIVXZLTHxXRE8rIUJ1QzN0THhWPT1qdm5nfG85JlkqQk5LaGQ7Rn55WnFgKzQtREJONUA4aHZ0cVU8TjhQTmY2KXQlJwogICAgJzxQTCpoLWsmaiVwMkpzbFBPVD1ib1NGO1VTQFdAdlVyKE9ZNHBiKykrUDVQVT9DX3pZQm96dmhkJWQqait2QUxVZllAJm8obWlNIVZeO2hmaVA2fG1zcEJNSjhxYTEqUkh2WD8nCiAgICAneFhiVGVGdF9sI3UxME1yK3laOGtVSVI5VUdWQyNDI3d4NTdAb058NV5SeklkYypjc0A4d3w+O1glVklgVXxMbW55Ry1PZmBBLTwpP1UweyVLJTZCeDAkZVNKUX5+WnM0V09sOycKICAgICcyMEszT2w1Y1BpcTVVcUM5X3EoVnlxVGExSDkjRHcpIWE/dDcxPyU2P2hNa1p1KGM3O042PW9RJE5IPHMocmc+Ml9+WjJqVytjUShIT3lYKFkyYHNaU2B4flFpMm5ie2MrKnYyJwogICAgJ3pKdUZPdVBQTzdJYjx+LXlxciMxWlFmTUM/IVB5ekwzWW5BMmNhfjx4eWoyQz9xP3Q1KnJ3UFI2YUNsPSl5PThANGBRKWJkJTNuTVF2KDVvS2wte31OSkpFTU0/MyNuPj1tP2EnCiAgICAnNyFydzRxd2srU1VAJFdHPk17QlItTzwlX2BnfUpAcz82bmExYyg2ekwxWXdkPGBEYUohRUJ1VDJ9QDFMOy1mYEpQYHpAekBHTzRpbiM9IXp2UGs/WnJUYmlkUGotMmJBVGBNcScKICAgICdGb0ZqalVJaiZwbyU7cTs8S2whYCpZe19ANmZXJV91ZmF1NXt9NSYrZENaWmtPRUgtUHJESlpoR0EzJGptazRCem1ie2o2RkxPT0ZqY0IwZXB4VFg2KFBYP2hpPkF9UGpWKTV+JwogICAgJ19sfCRCPWQ7UEFKVkZmR0IjN2Bmey0lYF9LMiZONyU3JnUrUWl6cW9DTWxQRGtvbkl2Z31yQj5zbWNjWmJkdntJcWR0NnJyVjt9TWxqSk08cEVoZncqQXF+KXl8QTF6O1QmKEonCiAgICAnK0IoQ05MMVpyZmdeR29FLTFzM0RgYW5KakVUR2E0QWUlcDArXzl6WVRzT1N8eSlafV5UbCl1RU9WIUdMKG5UWDZfODVDNVZEeTlJeiNoRXpiTWAyKyQocmZGVz8oajU8Jk8wWicKICAgICc0Pn43T0VrbzJ4UGtsJj8qfCUlNDwlcD14YDkpWWVpTn08QjRkS1kmV2VfUUIlZEd+U00laktedXZ1JFFFWF4+VnRXOFZsWmFqTW1eQU89MDZeYUxzSSU4ZDQhfSRZRlYjRXE1JwogICAgJyNOZ0F9M0I/al92YTtDP3xEe3pjQ3dkdH43SnVUSTIrT2ZYI00tQj9JZ3Y3WV5yKigpMVF3bTtYd35Ebj85RjQtNH5GdV5fdDh0Tll7dFJ4JlVLQ1JPYTdUMUJ2PzgzRiVvYFonCiAgICAnQTd3ZkdDSFNtU0pRa3dqUnM/MmNDKUozOFUmfCZCc0VDTHxBV2M+OWh3dCpnRlhsQXt3OHFFdismdFB5cU5oSVdjQH5rYzRyPGVRJiRhPzNZZTBxV3QkJjdOMTd6VE1oa3xPeCcKICAgICdeNGtqSGZtUyNPbT9GbmE7VSM5YFEoV3A3OVFPQkNgOTZsYWN2byM0SlJjR0JHN3soUXVRRShBRiVyRj9vT1Q1JUotc30qTWRiUTV3ajIxR0NoSFZye05ucFYrRVdFYSZWMz56JwogICAgJ0M3RitqWmJUJWheMzdNLWh0Jj55SkZlY0ZwakAoPnNzZVRHam9+T19BJnd6YGFWPUk4P1EhSk44fDRJNGgrcihDJCExckIkQHkwa29UaU5jRE9BMlBSbi0lQGBOSE5HTzImKXQnCiAgICAnTWd7RWkhODdfdityJHNvPiNnUHN1SFc8JUFOVExAT0hfe0FhKD8rQExTWGJxNmhnNm1iMiZWWDtBMTF+e3opdlp0dSNBfmpZN31ULTlXdEhFTz1rSHJNNE1TbUd6QEYkWUVxKicKICAgICdvX1dSRk9nT2V9V0J1TTBENHtRTHZGdkQqMTcxdzdpYld6KCVjY35LU15BOStQMGxHTVYya2xhejdudVUkdn52MEQxMmdhYX5DTkZWfjJyNT4+Z0ooKlJGZnoocD02QyNCZ3pKJwogICAgJzkkaXU3UlAjTHk+JGMmbUsyemgtSjxFUT1ORjN3JWpHeisqQT1oMnNGQ1M2QGQkSz1MWC1lanNnR0NmYDx0Z0g3aUc5TSFgWDZ2UFpmKiQ1Myl6UmFWalZ5UzdyYVRFMGxlIzEnCiAgICAnVU94THYmciUlRUQoXiROe1lZMGltdTYkUklYX2AoXntkeV9LWU92aVRQNyFKRGpYUT1LaUJCbGFzRV5EMn5JITtFWUVza3FpKTd+RHJZbEVeXlY1N0ZWclVqcDVwKG90IylgPycKICAgICdlPENHentNdjdKall6PGRSTSkzPWpsT0w/WDE7aXVlQTYqfmE3MkxAJnxkdF5ZeFhTLTM2Kz4jRHtpWXY0Y1BnQjkzPGgyVU5fLXphSkgrfC1vd0gqeVlvM1pYdn4hJXVYX29BJwogICAgJ2ZeXnRCLVd+aklqNlJMV3M4bUppNSVYZS1ERmJNNSp0K3JlQFd5QEt4Szs7ITklM2wrcEBET0J5P09hdmhgVXg1aWdMfHJ7bHpmY0cqcV9wbmp+VFBwREVQRyUyI31mPVRmYSknCiAgICAnSSpQZVk2eXZOd1V5UDdAKyN5N0pQdHkydnF0WHVNUzRSXytRekR+VSV4aXZPMmU4TztsdCRmQ2w0WiRXZEMqQFVOXjB2blR6ST1PeD5Vb3orZ1pHOWxfcWJOVzdmSmhVKmxOPScKICAgICdGI1FKcXRkdHt3PF5QQGY+MlJyODJGT309SCplaVR0N2A9ViF5cVFleEpHWEhidU9maSUpSFp5YUo/aGVDaHtSa2UyQnAhNUhVKFAoSyU+JiRkd0BOTWNfbil3dnpRQDBNNXp0JwogICAgJzkmK3paTWt2ZHFwRSRgTy1kTGtYJWNPdlFuK0xlPHpFeGlgPDhAYFVpJDlaUFh+QTA5eTlxQnZSRj0hWE0oMGZOOUJtbGlRKz9MZlhRI15GTnxwVkNPN2JlcHtOXm8xaVdldU8nCiAgICAnLXc9WklIUjkqZGErM34qb1NtP3JKY1RFLSk4QTVqbT1EXjc7NHJTV21ZcmJ8VVo8Z1pWNU1pZVNROStHVEMrTjwodnFLbyRBUkIwYmplTDU3flolNHImb0gjTGRlbDFhX1JqbScKICAgICcmVDRHRi1VWFhGbSRDJHI4WjBxb0dvNCpTSFJiTl9JallhPEVpR1EzaT1jRDdRfEJsNntwTHMmZCNmX01Rel4jVykoY0pIV1ZDOWc4c2ZYRXd7VzJWc2VAKkFSbTExZCNeQ0k2JwogICAgJz4tJns5cmtCcEwtaDJ+IUkkTnp6TjZsTE9td0shPlFIenpObD05b0BffXJoc2JzQHRSY19nJCVBciZZTHlAczgqJEhAWXRhbXpfI0soRVMyVG93M25rbEZFYjVQMTxMYXxiJUEnCiAgICAnM356Ry1pMHxCK3h6QVJ+MyZZWE43RmohJHMyKWMraFd1PWByVnk7PF82N3cqbUsjfmlOTWBDQSh4N0BpVSF3KnZRSHdfaV9MPjskK0FZeGY7LSpUc3IjQWA7T1AyKHpNV2hQXicKICAgICdJeT9VRThkWSpOdkUkYHkyNXBSIUZ8QnwzIURUNWU3NnRoRUx1M3ItQmlkZWljemZaSj47byplLVdqPWlYU3ojOCMqQTc/eX4xZz1OPHw0SkN7NS1URSoxeShpVGhsUUh3NjJoJwogICAgJ0FSfVJJWiYjQW1DRF81TSZ9PkMwbUp8KjlXc3tldDV7YH4mck1qUHxnZyQ0NztRUn0lWTtXPEE8THBtUndmYyswJThBRnpzX1lDN3JiMGF9Sk1JWEFzQUJ9UyooSE1FI0R9cUQnCiAgICAnNWQ1VzZLZDZqflBnRVVhRj1gJDQ8dWZGcD5Cbjw1N0h+RC1Ja1F3eWY1c2haYUp5antiayZecjZWUDZndEtSZ1lyMG18e1l0VHomZVQoUn5yfVF2e0M8YTVPUk9scmkyNiZKfCcKICAgICdabTFwaGlIeVJAZUFZamQ8QTxRRj02IyplXyNuKUhxNytsbkt0UkRNdWk+SCtKO00pd3QoVW1ySyhHZ1pJTTgmJmpTbUk0OXBvSyRfPipNWnBgVEVrNk1DJF5RSnVRSTFPakxyJwogICAgJ3RtTVhOTi1ULVc1bzFCa1RSUE0qT0FVeDJJPnxRK01OI080NTtDRFlGKztuckAjdEVQeUg7Rig0JTcoVWB0Z2tybXB3YW1hPl5PKipnR20wIX5lPUJJY3BNWjV9Ym5VP0Y0YDgnCiAgICAnbj8kIWRYKT1HTW89Q15FSiY7THloZCFoUmx9Y0pqMDBoJXl7LUhXTSZBfD52eUh1KnwqZUUwZHQ2ODVkJmc+N0JweFVqKD1rVCN8MXkhbDlnaT19dFJyR1p5Rz8peHpRSzxUIScKICAgICdPPmdNTWhCJFEyWiU0UzNzNn1uUDQpYmU3Sk9OQUtqZjNtJUJucGcmOWI3QHRBaylyO0AtRD1JU1RkckohTU9vSypCMEVFQTc8PXAkV3h6KGQ2KUNUPGw/ckcrKTRjNiZTOVRmJwogICAgJ1pXfm4rYm1yWUtocl5tOG55YXIhP3owT0tCVC07JVY+QU5oMFo2P0dZMXZQekhAT2R8QnkjbzM9Y0RpTDxkZj5kU2kmVGl0bXJkfDM2QlI3TDJyV1BUYEYkQCQxPStUSkJlP3MnCiAgICAnJDAqNU8+RFh1OWZRc1dRVUxjYX40ZzhyISZfeHN3UlQoOCV7UnM4ISQybW8pdDx0Zis4dUFiajgzc1BhUmxEfCZ0fEROcSN7KVBScj45UTVPSTU/YSUzKTk/RE1iSmA9c2doMycKICAgICcrdHFQKDAtWWFIU3hlY0RwWElzTE5MdFBCPWJCQVYwcl5EaFV9bUg7TWomaEs8eUJTWWJ4dVd4Yk04OT83VyZZb2w3e25EYS1WbFdmIyNGTnUoVFpOWnpjRmghYkE0ayk1PkpUJwogICAgJ2F4QUhhekQtMEozO1dEV1EmaWJPOyM3WFdXLSV7clZHZip5NjUyZDUzdEs9c2dLZlNNZFomJTQ4ckRRI0g4TTN3Qm00e09gS2l7b1krO3FoN2dIX2NxQFN0MGJ6NWs0S2ljUlQnCiAgICAnZH1mKHEwU0E3Ym1RQHJMSXApJV9gJkwxSTVLWUdnemN6dExDMCQrX18wdiN0Q20+SiVFNkZGT3xHPVY3Zz9AdCp7SG5BTj8mPnM9c2hJYkxxZ19scVVrNDdaTmEjQ2hIN3ImaycKICAgICdzeyo1bSl2JCtIVD9lKDhVQmxhQFV2TnVnUzY1UFQ+ITRlTkhsR0pPclRodXJDTVJKQ1ooXmZXYXxmeDdSNkZ2OCFpWGhKM29OWCRkS2UyKm1kdyt0cS1PeU41RFpqLUJmb3B+JwogICAgJyk8RCVidUdIVnN1SyhWa054QXZqPVNyKERGOEpTP3dFaGxoITt6dyVQLXJpRGtoWHZENTM2bVd6UCE9WF5yM3VVd3ZSNSsrQDhZakJNdE9IaUYqN3VjMWolXy1UN3hHQypTKXMnCiAgICAnWmxAcCh7Tn0ydlRTeyVzeH1fX3FWM2dxNUNucUVSMTRyUzs8Sk9EJE5YYit0RE1VPzQ5dnYkU1k1fClOQSktVEZJMWxSJGlJK2VAJUwzS1E2UjhefXc2Qig3czBFMDF5QWg0dycKICAgICdeQzI8KXJoLWRDanxLOEcpaDE/ZFpGfFQ3V1hMcFQ5UWoyUTdaP1l9cU0lMF5XTjVPY3R5MlhEZUF6cFdvR19iWjd1WV9ycmNWSWkzWFpFRCtuKU9PKW1xPVFPU0FLeG9McFRrJwogICAgJ2FURFNgV3U1TCEoQlVVdik0d0g3SzEjLVoxcTR2PjJyUF43JnBqcVhgWGpLUXV2Tkl4ZHp9fUw4UWROOHJ2R31lOVhlaT44ayprcjZFJExzdDNLMClxSGFNeWgqdWsyOWI5UkUnCiAgICAnME1PLUgwN1NedEMkY3Nranx9OEgrfT1nRU1IbjxOPlZaRHQpbDxwRyFXYj1eUHNtcUlwd0A+WioyIyp4OEFgKFhKeW1lS3FDcWpqVGtmZFU9T2lZR2N2dndZcXhOSUhHYGg8VCcKICAgICdJQz59MFQ7N0whb00lPWBiQy02fnh6LXZOKzRsaz9TZkxsP2NUIVp1Tl8tcU9sa0Z1UXFLalV+XzYyM3F4MXd7eXd5fSgrXllwMFVBYzYwfTUzeWd4eVNOJmpHYmIzYyZBfCQxJwogICAgJzRhR2pGcD9VS1AwY3FRdTskPF5mSl43K1NZU1RwMDtDMnNMR0ckbjhibld1bC0jOC15TVd2fXchWGFtdyFWbiZBKWpMKn1lZU1COHdJI2dJZSNgQlhpREBaTFo7a24/d3w9cysnCiAgICAnWVZBPWBnblczVSpIMS0rME5Wb0duPX5HJCNJKVNtTHQmezA+KXdQdyVkWX56JmtRazk4fW8mTSVUZUReZk5HNng1P2kwcSsxNXJRcmVOdyM+YGkxK0xvTDZZK0o5K2NzMTxldCcKICAgICd5fjxMekhzMEthckxnLUxqQD5rS3swNlNgKkYjLVpaKnE1Nk5FOV5pLXArJV89MnE2RmRFZ3M5WWNOWE9kLVdJdEhFMH18NG1MUnpnWDBReUoxQCRGKVI9bkY/Z0FLcj00PSp8JwogICAgJ0ZSK0JyYk9eZ1AhaEs8JiZ3eWQjQ2VtfDVCd300KlNlIUV2bXYlT3E0M3FTUWxEO2x7XiRSbjdMczMrdWpHMz1LRmhCMnBLfG5uZGxVNk81KWE7eipuZiMrP0pjfCkpaXZzbkUnCiAgICAnUT09eGU4OUxgb3ZzfiYrTjs3Tj1keFY/bVVib2NgVWR0Kj16LTNYPjIjZ1B2XihwNlYwRj5hZ0VscDNkM3kyZUtybnpXY0RIKkRTUS11bVNAKndvbHdaPHRMS3MkSkshTylDSCcKICAgICdFUWxoWi1fKFU1aCFBcnJfTCN7STdJSWAkQ0ZraSZ5KmFRa244VWEhU2pEU0VuIVAkfXtfLVE0dCpmXz0rMXMxSTM+QnxhbUl6eENvd3JRaHE4O0J2cWBWMS1rTEEzY3J8MTxaJwogICAgJzlKbVYlZFghMyRHKWV3Vnd4WERBam9YUFlHOHpkPUBST0UkPT8rQlhHVEEmRE8wfHBYakghX2p6KFFLVWEpenNiTzB7UnxacFRyPkA+RzIzbHtPOU1vMz5QOWhBPW5JR3BiN0AnCiAgICAnIW1hRyZvc3ctKjNeIShsPWlxNHxNaj1zSWY/cylfRnxSMkdVSWdMTEZybVZQZFNoYippfVVkYnI0fFJqSSMzc2UlJTkzKXdjej4tI2Q7NnpaKy1wYyptMHd2bmQ9bU5hRnNDfScKICAgICdrKlhYcVNZY0VtPlYkRXkrT3tfYndPNWtQQFpyTl5Be003RWRXMCFXfDhDYEFpSyZVUlFLQnRNWDh6WnYpPENhfT5KKjAkY2BZbX4xNFpYbWw5VEpVYV4rT1UmPFErQi10NXFhJwogICAgJyVucyY7YkxFT3hneHo5JF9PRE5Sa2tFeypDalFnKykxZCt9VUlpIShZcDM+KkghbEpLYUJ1M2YxU1ZgeFMlRyV5MTRlXk54bGc5NihxUmhqWSo7ST4lbjBoaGM0MUVicz9gSVUnCiAgICAnVT5nYG84TWVHQEZsPzt3UyptXyRgQnVhfFY9JDUlJWJsPXFoKG5sMDNGZXQzbFF1fXBDQEorOz05PkRUMV40bW91bSZOMiVrUTlhbUREK2ZXeyFzY0t6aGkrWDlqJGY4OWBlYycKICAgICdreUZYP0FTYC1Zb0RDKSszdFp9P0dvQW03RiVSJHglSX08X1laTm5qWHBhJU81WjhsLXhTNm9pPyszY1FSVjlzRTxEPnVNbEFwJDApYUU7KDQoMmsjRFFqZDZDbl82bVFyczxpJwogICAgJ3N6eHNBNkptQ30oWFlOY3Q3X2B+Q2VGc2RZWV9EUWxiYEhMM1FqIzBoM0g1KWRILSo7ckBBUDNKc0xFOzZpMmR8bihtQCYpUEV6R3FkeisjOFBqQCR7SV9odUJQOURQQUN+eD4nCiAgICAnWEZzUWBMTXVmQm1OVzFKbVVZKGtXUVM2cWYmRW4lKytmSkU1QDMpK3c9JklrNjxuMCRXSGR6dm1yRHNyTkUrSTFldCZlMHMzbE00R15OQUl6bUp+P0B3aF5uI00xMGF3fmZlRScKICAgICdCc0YkXmtLRVkhdmlSZTFWPylZWk1wUTRxOWI8ST8jcms/fT5mYmlkbG9eSWRXYWItTnwxO1pqZFlORnNAKEJrMm1aZ01KbT1ESlRHPC1DTERvNXgjezklMGomYyQwKjtgMGMyJwogICAgJ2VYdHtubnR9Y3tVX301VDR1JjFCbHBuc1hXOUoremx1Xl5qVlZuNWlETC0leWtGRFdpTG89MWpHazQqaXFrIWpUNk5YKkMpdkNmWDwhJHlecitsNUBDTmF+WWhuZ35QRENne2cnCiAgICAnemtgaUI1SG48YXszRCU8Jk4pai1NNzdZSHs9SlFAcElqTiR2bCkmSjxxTj9GdXhEMjJZajh9Klk1KGFNa1koayVgaWc2RV4lKCFDaih9T3pLJHM1TzkhZCEmalg0cWUwQiUzMScKICAgICc9K1ZSNjdsOXZ5bm1HXzZzZDkoKzhUKnNOP0MleypXZGZJUG1yZVZAbGYkUWE/fEFnKFd2WXN+JXk9Pj1lN29RSDApNGdlYiZ1WDx1ZiVORzd0Sk1eVGZ7LStqV0R3RWxMek81JwogICAgJ3JoQDlERDZOV0ZXJFJ2dyF2Z2VtPz9HNlUhUldQbktyMmAqc2tTPT9XMUVsSHVqTz1abTlkdVlzTzx4VC08SjxAaXQoQmslKipDaHlPc2g+bH5eVFFFQ3ozayVnZDAwel9PPFknCiAgICAnYiRuYXN1NjRKRzQ5YD1UWURBVm5WbFFMVmlEdG0oUCs9YEEzaD9vfm09QCVgfENLUXBLNUZuUkQjPygxVWF7Z2lkY299OT99ejVOPUBwTz1rYlFXS141PCQwTF9FNXJKJllqQScKICAgICchdkUoMHJDTCpLdHdxeGBzMjxCdWlYbWtYNCooM3ByUFJgdzgmSGFPQ1Ate3BgTkw5d191YUQqbk56UTw3ITdiRWlALUQ8RTxkeno3YSM5NmoxRkErVUxQWU5NODB0LVIoYmEtJwogICAgJyNlNVBxKWtydmcqc3wzM3V3MWRVTzRTViU2RlJaIWYqcnlUKkRNRnE4QXZKekV5ckV6UWVFOTc1PVc3MDhzPGVXb0piejVIcWNadEIrT3ZUeyYoSG1DeTQ+KTNUPipwOF5EekInCiAgICAnYnVJazs0VnpsMUI8bWdfOVZ1dDVAOWByUWRvRGZ4ezxEcFd7b0lMTnZ3RndwWmVLd0EtdClEJTI1TFlrKWplPlU4aj4kSG1QPn53O2ApMyV4Zmd3U2NDX00+YStXdEZmKFBPIycKICAgICdWSkIhflQ0LUpmNmx+T25jTHErWEB6KDd5eV93VmkxTiYlbi1HUlJKT2ZMQ2VWSTRfQWYxK1heP1ZhMEhuZHhxKWIrNFUrdTlVUzNLVm8oOEFoQiQoYzZtZWA/XyR3MWdJJk5MJwogICAgJ3lQMXFuPHd+WVk0TldDMzVZaTE7Um5wVE9hbHZ9K2hWUS1pSHZreWVfdyZ1PCRmIUlfeXYxZE15YW1XXztubH5EbiEhbWp7Z0ZucDgjel9wI24hdWReOWx1M2h8KkZfTT59XlYnCiAgICAnRkBYZ1VYNSVVSCMrck0kZnVmentgKHhrQ0VAeVNCbDczQ3J0dVVYd3NXTDVDMXsxV0VYMTAxSTVPQTZxSDBJRTNKS2BlcHBIJitMSEs7YUVoeDdzbWswWDd0QHZsYj1gO1YoVCcKICAgICcoSn1afm5nVFBecnxMclNGI3RVPXRnUllfbkI0b288fHg5QG94cz09NURQS056fFNfMkgqTDkybS1LJnFuRz1SRm5KRWd9UUYrMWFAPzdwY3t2RT05eHd4bmV7PzBmY18wc1c3JwogICAgJztteV42LXJuVy1vTzVZKFFZLWtkSDNtRGlwREt+fGJzbzViSkxuaXNrTkxZalAyVzl8JClRKkpyQi1Ecl94flR6VE1SS2M0QGU3KmtqZ3podVFyPFZRWFVHQGhSIXtNbihqZjcnCiAgICAnPG48OVUwPy02TnJtKW9xUUR3KEAoJWZkZmVuRj85KyRZOV9wcCYqUVJASHs0ViMobDxuUTdYeE4yPSh1X2krN2lHRVVHI3IkND03IWwjNm41JWEyenF0SFVgIVU3VyRjPF5tJCcKICAgICdVflVePE0hI2RPWTNIJXI0VThobShnclQpSClCezU0VEJ2amxuRWk0UlNwTUhxT0xna21DYlZXNj80MjRQflM5OUs0K1NqI0pveSVWMiVRbUgofG1Lezs8d3hebEJkTW99NlFsJwogICAgJzl3ek42bDRuZkRLbnBCd3M3RlVOezJeaWJ3PHJzSkI4MHk9QjBVU2klQT89STl+RjxLYHxtYlRiMEh8TmFMRi0rM25jVXlGJFlpTkNfdSQjVipNVXUoVUV9NTR6e01MUFBSfj4nCiAgICAnQ201eyg4cmRoWk42aEliKE1ye2MhdSUtKTRuPXdyWWFhSWwzbDY9IzBvXjVsJXQ3ZHMpU345RU5Ob01gaVgrQGl3JGkmU2Q0SzlKbTAtenE5MEdmfCF5d1pMPkJ6S348KnMoPicKICAgICdmbCoyUEdtYkIqJEMmK25jb1dGNFpVbHJKYmdqPmNsT2V5bSRTKSgqbmV9LWo8czRuM1kxTjduUnNzKUZTNWJLNU9eOHgkdGVUd01uTyQ3aUpAVExEei19Nm5YNWsocEghVkNFJwogICAgJ3RJdGRXSSpffShOVl4kfUBHVkFJX31uVStIQUh7QG1iNy0kPSFQU004bSQ7TF5WP3BtIWYhWChEVihMMVU/cj91VDVHV1FwN3J6S29XaE14KCFpfXd0RDs9Y14/aFQye1ZaX2EnCiAgICAnbE9wKGpuRTdYJk92a193aFY/VSUkdl9ZM0NtTUFxV1BeXiZ3SzNqZ1J3VloydTItYVUrYnFjNjdjbi0/U0dIUSUtKHkhbWUye1pqMSUqOE93ZCRkOCh4bD17ZTVoeE1SYzFpPScKICAgICdCVWFPVVpnTWQ3I0RXMEYhS1kxIUwxOHQwOXlld31NJCp4czR3UnNpaHdaQXFzcEAxNTtSP01KTFJlWl8jfDhGRFMpXiopb0dKU3c4MUxwSyVQO2cyOCM2cnsoaUNUNylsZ2hwJwogICAgJ2FjRj0yeW1UcTV1fSk7ciYqdXl0Kjc7XnR5TSFKZ0BedWA/X3Fzc29iN29mO1ZpMWp9KlE3PWBxSkNwT21XRlpWJmVsclVZTn5LRCQofUJVeVdqcWQmSX5uWjFARCk+VW1ONmEnCiAgICAnclIlZyEyV2l1Jks4KiMtQFRGdEwra312JGZ9KUshbWkrLSMxb1M3YFZLUHNRdWh4UyUxMnJDIWwtJHNTV2tXcSNLQEZATkxMJmFBd00jeWB0NUxCVUBGUWB0SXMmNXpBb1ppPCcKICAgICdKeWNkXjAzYkYpYTVBIWFgfj9ZRUBMeik3d3NqK0pPR3VBIz58Sis2TDNINk4wTzRAcE1VR35GbHx0bkg/Xis8JVYmUTAwITBCJFM5PmRlZDljLWlFLXdYSXpJKiN+T1p5MUN+JwogICAgJ2pCakhqQz5iZV9NQSk8RDFzQFRIIUxrdlQ2b1laR0lkWiMhIW41ZHd6fGZ0TnZeTjIqTXJ+Km1rSigmWDFPSEAlY2IhPkE0Xio+UzZOfE1nJTQoZVhjIzMqZjwmPlFuezI9bTwnCiAgICAneGlHLWZhfk1acDU1Nl5VeWorbT5NMUlvdHMrZzMjVTFGaF54IVdQWjB9RSlrdl8tS05NTT00WkJMUTElSzUzSkNKZ0YqWEs5QDlfKWZtTG5kemt0N3BeJGtUckBzTCs0WGpEPCcKICAgICdUZ1ZnflNvLWVfamFKZ1pefV9zZCZZUV56M2lCQWklQXRWOXM0LVZNMmBVUF9tXj9uR0hLUX1WRn1fRXl1JF9zd2l3UTRhJllub0wxY1lebnI8IThqQUhsUXd4VWl5fUlRTEhoJwogICAgJ1pGcmVlQFljfUdVfnFzWGN5JCR2OTNCdz5HQCEwNnpUdXZRNUd0WFokMzVuNjBacSFaSj0lbX4rJU5AdU1RJTtSViFyKHFGTCtrdDd2bmFkTUEtdSNQd3F4QF49NVNxe2g2KkknCiAgICAnSzY2OUowa1pwdlFmR0BtUEU9WVMtJUBtbEwmX19YKnkmbGsyRnN3P2J7QTl3LWtTZisyTU12MHlPVS1IK2MldkRRKE9+JDQ2aiZycE1OeCQoNzE5OU9kQWNLNF9xPGswMDJ2bCcKICAgICcqcmN8dT88SnVDYzJQNkhlMzt2UmFwM283ZWZOS1k3NSRQQDB8Vm9VOWV6V28zYzFiKTl7KHdlQFAhVGRpcntFQTBaeXp4PXsrSWQ2SVZjU0t6Z3EkTHlQIW8oRz4zS2RiMUppJwogICAgJ08wN2V4LWF0KWlxI180b1ZMJDYrNUZOdlRRP3tURFd7fXlGZlNEfURgMUh8b19qNj8oRjBuNmNFNmtyWGgzdVJxc35ndyoqaytXVFo9VUhJQG0rZWRIKTBYRnt8MldLPlUoVzMnCiAgICAnSFlkTW8/aTtvPXoxQSRNPEtgRko8bF40ays3cWNWSmRsdyU1NWRUMXtBdE5oYEQoRSszJGJ+SEdhT1RCV0dNSiVqcHg5TUohZChJNlQoS0x7O3JXfHhKRiNvXlRgRXkrJHN2PycKICAgICdGY2xoc3RkJDtybD0hVH5HcCFESE9RWEdTWmllS15xeW5IODNYNX42WW0pRWFTazFXWkglYzJePW9GYkxKaS10SlkjOEomYmVeSytDJkkoNz8pJCltJEx8ZmY9Xml4P0BMK0YkJwogICAgJ1FXcmNweXI3NyQob1JzX0N7JUpyJWNiKylLR3JPSlFxOT5BSXxlfTxCSWNKNiUra1UrTiFxb3pjVTY9VGJaRXV9an5HNVdqSVFOTUdZR2dTN2wlUUl4WDcyVHgyK0JIdWxYO2cnCiAgICAnVUcyPWtBPjFfUWYhfUl1Xy1nU0BUQklSP3NUTHRUbz0+OHQlV1kpfCtAKzRAcDNIPkRBKXdIPjh1V2xtZXx2bSN5MDUwPyN6JTF2Vkg2eFhSbCp7fEErYV5wdkgybVNueT09OCcKICAgICc7ezhAejtrbn1vPXtgfTd3UGZ5QVdPUCR1M3p+ZnE1IVZDZF9KREU9M1Y5eXpoNnN9VEd7enRkVUsqWiRlQkMqeDk3dWZhYzIhc0BTTlFTSFZuRzI3RDkxYSYhYzdaX01Vd0E7JwogICAgJ1BqczVER0xPND4tR1RJQiRMRCNjOSpKP1RfbmU3VXUmSEQ4UHFgc3lPXjV2NG0/Tl93Z015JnQ7WTdrPjc8T3hSQERYZjFFN21gZlNPPyNtV1E5Nlclb0Q2V0EwNT5GeTVmRzEnCiAgICAnXmEmY09RZ1VLKV9qc0B+MGJKNGxlUz5DTV9xLWRmJm52bUl5KXFneSlqZ2E4SDZkcTMhRHVEdV47VyVfdSRMUGh2MHgldGV3dyZqWHY5IVhoeH48Ti1UKmZfSnQpQm4yM2xKQScKICAgICdwfWNSNzc0ZVlla0RBfE9qZkExQntLQllYNnV+VW5sZjZzZz15dSphTnVGWWhlPCVCPCt0SjNodD9CWDZiZ149VkB7NCYjJUlnT2wpR0tNPFVQM2o3X09OdFExbkombGB+UDRtJwogICAgJ3g0NGxtTzF9SHZraz02NnR0NGM0Snk/S1FkZWB+V2x3aXJJLSZxXjIxIyVzYWtWUXBqKDgxPT9teztgXzBzLWo4VDgxSGFaVjQrI29IIWRkITYtZGxEdDZUQSZFWk8yXlZjdjUnCiAgICAna2k1JEJDXmY9OUMxdmQwbyRfVkhtQUpzfClvUDVUKnFGX2E7fEQ3IVIybGNuYDFTcSYzZlNBJlZ4VT5kRzwhfEEyeDghMmdTP0R5YT0+Z35CXiEwNnUmUkZIRHRTc2tSZD1ySCcKICAgICc2ZXh3KWNMdighYSZobWJiRDY3c1E7JlIwP2hYKGwyJVpVdmkkc0xaYU4ydzlPc3w8NWk8IURYSExkQVM3QSs5VyR7UD0wVjNgMkFIbXpSaEkmTkgtan0tODVVbS1hR0RzKyVUJwogICAgJ2t4dHNDdjVCfUJhXio+b19lSmIqQVVmZm9GNzleXmBxRHluaGlKVHY8OUpkT2d9QlAyd158bUwmaFBHX3s+VWhEYXExRVFFVjJPUDh+dVEkdl9oKHdoQ1p6X2ghSCt3cz47UEcnCiAgICAnIUBkZT1xLXdfJHQyWjw+JUJ1b0w9dTJga1o1fEItaHtfSk5idTVWQGY1akRlMFElYUFRMW99WDJxZTZUdHojbEIpVFlGKmJYMmQ7JHYkUEUlayU7VitGTCg4UVJPaTU8WE5ibycKICAgICdaU0N9akdUJUxfN1EzUFl1cCQrflQ5JlQ8OTlHTzQ4SXRAWVpOKjFIcGM+U1dLdXJOVSN5JnVFWHJ6emF5fjNnamJUaVpNWmMxPVU8b3MwVEAjY1prJkxDV3dnUV4zZEZiMykpJwogICAgJ15tMSNaWUdaSnhBdFFWIVBlUGNMbW1wQzcrKFNOYkctMmw1bmMkeD4tTm4jT2AyO35tTH5qMmxZcShLbGN0QUJTJVgqIz8/QUFLWmVLSGZMNUZOaHpedjJvfHdXYFlEcEF6NTUnCiAgICAndyR0MVpAVkMyUm9YeFJ8SVZ4U0xCak1BPWBiMnBYWEImY0V5bmJrYVpgYSt0UjReaXZRbENEKTJWM1Z5NTU9ZGsjWnNBPlR9PXtRR15qSiUjU1JNSzxmUjBSMm1aKWVYS344VCcKICAgICdDXjJ2cGgpJVh6N3V4ezBDTT8wPlpaNi1LRVRfX01qfGg9bGlMZSZPV2c2VDtJI3R6MyRUc1I8QjlsaVQ8WSp7aSZfdUt3V05kJDVWRkA3JT1ndjBBP2Y/I0NNfnpGVmF+MlV5JwogICAgJzx0fiNZY09ZN2VrMCtiZiNiUjNaWlFqdkMpTSkqSSE+Nz1eaXl4elpjK319eDZMXjJHRnEmSD4leG5tUlp+cUspUEVqe0wqKjZ6QmNzYkdhbldwaUFDQS1gSzdhVWBxWXxRdVYnCiAgICAnJnBUITQ1SmQqVENfQX5zQkx5XmAmZ25JZ18rUURzP0gmfk9GZVV+VlY0WHlvZGI/ZWxxKnpIb3NxczNaQS1Hczc3SHteM2dmKDtCeCZVfkM0JXpfTjBzP0otSDhGWj1HSUBHNicKICAgICdzNE42PnhoOXgyP25Dc05OWU0oUEhHJXQqYWpoYWdqa3s8KzEqMiNVXiFqUX5VZUA7PkZnQWs+LWJXKWFRRWA0YTlmTzkkVjBJXl5fKS00WCR8OElCRVlrQGljdlpyaUowUF9kJwogICAgJ0I8KmM7bjBEbEc9byo2UW8tI0ZvZ35QU05eKGZNIWowfTc4MSspaUQ7aE1VQXRBO2dFMU4xV1pZOFY5aTRDTiV7JDk9ZGZGcSZxTDJqanYyYj5ISDk0TUZJalh1a15JT1dDZkUnCiAgICAnPXd3QFFtYmxtZWpePTJsMlBAPXEwY0FnamBZNHM9e3N0OSlZR2hZQDdpX28kPllpVlokPSVncz9AUkVuKTl0K31hTyNYekVQPDw+T0p0bUVHITUre0F2SWc/PTJFOEMrU0U3YScKICAgICctIz5nZzlaWnJMaENgSF9KPlU4T29VPjFDU2xJZlNIMyEoN0lpZnBMPj1kPyZifSFnYiM/UnkwRDdqK0pgRDhuKUY0djlyJVJRNVJFKSVqZ0NPbmIhMTMqI3htflIwSkNtVj4jJwogICAgJ1lVYSNOSkF5KmJua1FNS3ghYVY2ekBeS25UWjBxQGs+QTVFXiltN251PkEjUiUpMHBeXjhnbz02NT9Id3I/Y3RWQFVBSWlYQE4lUGRIYmsjVGpgM0FMOUA8bE1ON1BWPFd0UjMnCiAgICAnSiE9bWdfKEg7eDt1MSorLWJOTkN6NVVmKl5ENGl+QHJOZCh7QGVAYFkwekU2RWlTOVckJnZ8YVhfI0RSU3JDNXhTPz9gMVNeUFpDbEJINzNORVQlMl87UFIpMz02PT9xSXljPCcKICAgICclTE1MSyoxZ3FQZEF9KT5AfTZRVFpoMUglS3wjcFY8VVo+eGlrVWpAdnx5dCZsUylja3ljNC1wJWA3e3d1KjZxak5TbGdWVj0pMFFaUHduQFctQCNQPXAoPUBlVEVWKzZ5U3hMJwogICAgJztaNTV2dDhvdCNATFd9cUtkMXpMailrdi1peWs9LSpIa00hbkBHaDRlbmU3Nz12Z1ZLalkjPF9nPGV7YjkqMUhMJm90TSs7TnYmTVJNaFRzV0hEeTdKJitIZVhBa0MmbUVGezQnCiAgICAnTEtVO1QzUDZKI2pYMS1xXmNPJDhEVGF7NmQlUkhtUGpnJXluaypUVW5eQ1ljX2dscyNEZGllc1orMjJGOE8yZGs/TD4rNz5PRjw0WHFxSldAbF4qJkJzQF5+I3w3IVpZV2pqRicKICAgICdFMVM2ZHR5cSVFR3tWMF9JWVQ5bSFkd2FSZTJPKz4rKC1fdzx8e3c1cFYrTkI8OTE2XmpaVXtVcVZKc2ApcSlGKXF9cG8hNGhePykpMm1Ycy17QVRyUyRheXkkPjVfPjV0fDV4JwogICAgJzZlfiVqWV85cDkzR0xHOGFoUX1mamoxIVlgNFc1JWFQaVBvYnoxMTV3e1BoOVdiWk81V0RsQnxBfV9IVmRJa2FTSmVOdk1NdDV9flpKb0UoSiUqeSNIPEh7aVV8aWAkQzx5WUwnCiAgICAnOzBZNEFiPWs4YUtLUChOc3QjQzdTZl5KR3VLPG1yPEFidWJwN0ROVjZPMD19Qko0cURgXkU8SnFwPUpkbiomcEV6dEdwMmB3cWxlZGo1X2wtY0JPbDNOSjsmNDZ+QTtLPDRLTicKICAgICc+dF8jWEUxRyk2TUE3O1VIfGFWaUVIU2RkRER0RCsmWkhgPk1URn1gM1kxTm4tQUszSXpTTHx3S0l3VUFtKUFONGdxZnBCQTI9WDdSdElnMzd6blFVdkpTSDYqUmozLSM/MXFSJwogICAgJzdNd0ZNdGJRaH5oM0wqPWNJVU5sVW5mYWpZXnNqdkErbDYhVzBkQypva3ROKHAlT3FNWX5pNSpGR3Z0SHhvPEt7MkNkWkFNPVVWUyZReDBkaUdIOzckVmFMVlplcXRsS3p2JkcnCiAgICAnRishS2NDQm9eOV9xazh0WCR3VXg+T0dNNm9QVW1MbEkwO2UpZTROej17YmBsempiLV9HblQ+YiYtQ1luJSheODk+RTtyNGJObzZ4K2M9RyRvLUpVLWVZRDZib3ttVX5QNTNWficKICAgICdaZDRFREtXd0N4PXVWYGR2T0dZeDI3cDJHSFpReChIITRJPHVjNz1SUHI1dWZsY0lZIThFTjIlOGRLbn1KdHQ/aXZmSX5nKU1vO0VIcj8tOEEtMk41bHlQPyFgVFNeZEZ4JDxUJwogICAgJyFKO1VNaDYxNkpYQUpBRldIZWYhZlVSfE8qd2RxdTV1ZW9QUGJvNHw9eXdEN0cka0AwITJ1fTRLPCEjJDt2TSRPQ2wqRi1RdDxHI1hjczxtQlcxcGkhJHJmJjtQb0kkc1IoeEgnCiAgICAnUE9CM04qNndfOSMlTWxUeUt7KEdsVyg0RiphTjNrUFJVQVdTdWskc05vJXJoRD09ezBiZnYoJEhYZEdyb2BaWGxIdUJIWWh2Jj5+JGxOPiRaeGxJTTJaPUNYVjhXK1EtN1JmWCcKICAgICckdDJ5MGQ/ISlMbUlUK0MjdUxhOS1nJEN9cytya01VSzkhU1hTUVo4TFE1JmJSUT1SV016by1xWEApZ3hGVWtzaWk4diQ+Q2A2WDc3TkBWPGZASG4+ZCNFaWYlfX4wcG5RfUFTJwogICAgJzw4YXJNTlJfNGk4TEUkIThOVnNQUnlrRjg7QnZXbU1AelN5WHs7RSZOdEdDb3E3d0k/ZjJoYjI+MnwoSzVvODAqU2Rab1o8andHK1ZRWjx9Ryl0ZGw5azVeRT8mbypFWmUtQ3AnCiAgICAnKEg+dyNwX1hiMGVQNE1XeEk7JnJIOEJDPkFxJTEwS0tIRk1CdXsjKnhTYG8mPUl4dSpjNjlLMm1hbkVsSTUreUxhWGdBMEB0TE5TKTJkaEFxNGpRPCNefU5YX3UybjFxfSVIKScKICAgICd1eCpKeU1Sd2RXNVIhYnYxP0d9R1hsMn5wekspanVWYHRoZFVVd2N1Zj9SeEFNbX1fRlpOZyR4UTRKPn0xclVkNGQxaGtZPE81NW85c0k4aEEyWmwhdG93aXArLXk7N1dxbnY4JwogICAgJ1QmP0ZpcWJFdGsxVWpxMDxeYTw/RnZZfT0odXBPfUApNGkmcXFPV2QqeGZucXBILXdLQGpXR25jdGllRDNXNEBRQThkaFloM159QF8oZFE2KEl0X1Y1bEo+YD52V0spNlA2Z34nCiAgICAnPm9kZ1Jedz9eSkd9V2k+TjJBKXoqa1Uqck8pT2RUMkx1ZlN0REwtez1sd2dAbllAOHkzWSpqMG9pOEBQVjVlZzBXPmVPSU16QGxmPW90U2RZYmJjRGNlejJwX3F6VmJtZ3VpXycKICAgICclNGIjRWBsbXtiKHNKX0kpdT04dVdgU3JhUWFrPFVfR1F4YitVZG1nPlMhSjwhJFE8RGYxVytIdklsT3JgSDNLWlRydTRzNW51X3Y3Z3FIey1KeipDe0VxTn5nVj1JPUVRMVJOJwogICAgJzhycU9xJEpkKnJTfkg+JG8oaFNGY1d1QjR5WWIjJXBzXj5zNlpsI0JUez1yMXtrKnpgdGB3Yn4rMGxAVXZiPUlHQChKfilJSHpUJENBVU41RGlNfHB2e0gmRmUkWE1FOVRZUGsnCiAgICAnRTBRblloeWckSz07NFMqISVqTChOSFE5STReaj85UWlJbGEoV0dVT0wyczx5X0Q+RTZgWFg5NXZMRjF0eiRCN2NIVGRfZHVLLTM7aWcxZG1yP2wlMDNgbUhpYyhiOUFDOGpJZicKICAgICdkdXNXbDQ2JDVJZVdhJW4qQT5iYzVsUURUYH4zcHpaQWdRRT1PMXNlN3VQKlg/aVFyMzlgXmJ9UWNnWFVpWEp2VERfNSFYSlJ8Rm18QzspRDZTWXJBRHdwKD8hSil6PTVaZF5IJwogICAgJ3p6c0w1UjxpNVAmPTc2I1M/ZiZ3Ki1VMDJXY28leD5iV2IkUWc2UEFgK24hPyV0K2pLUHJEbl9QTHo4WnlSKnI0aGw5ZkpPNFhwcVhPaXcxO2lFUE4/Tn13WXg/VmU3Zm1VbmsnCiAgICAnSHV4QTs9JmEkKzZ0VX1MKXx6ZGA0WXszTSlFMnBRMnY/NUxqYGJNb1JCTn1CfEQ8bEhlU3pBZGo5NEc5JlZHPiUkUUQmby1fKEVVZUNseFhAdygrKW1hd0Mmc196PDUkR1ZSeycKICAgICc5TEdORkZoK0RGPlVnVy1GbjxoIXszMSpLa2tGP3BTMkFicUxkKFhBIVY4Y3V6KClnT3shYmA3QyF9PnVybD1geDt1NVR5OWhpQipeQHk1dGBKUz9tU3FAVERhfk87cXloXkNgJwogICAgJ2tjeGotaUpIenJve2JCTitqbTBuVEFsI3Uoe05CT2FyKDZNOG9PaDFnS0p4Skd6eEE4aC15SXY4U14yfm5jaFg7MmdfJks+YyZCdXNUSTdPZmhSZytBO1g/KmlROFVgPnVNJWknCiAgICAnK2pPNGg+dGhOI04wMmckKW4hYz1qKnwofmBKbV4/JkM7ZUskN1JWeWFrQksrQWJ4MTVQKCQqOU8oVHUraEI4UDdha2A3SyEydXo8a2BkI3tyMHY/O1RZcjZ4O1hfQCliOExyRicKICAgICcpMmFGQlBwRHRyUVNgPEBsO0VqbHNicW9BQ2lxUj1DQDh3aG1ycXFzIUtLeF8qTmp7VkQ3UXZUPzM3KFotMERVdiE1UD5tOTFGTWJAPCRjYiZHZC1NNnozUllyfUcyVW1nYEk8JwogICAgJ0dtbkdUJVpTaUtSZD1sbXp2KXtQPnM9M3BvVmx1X0F4VSVmN2tuKCRKLVBvQzZWdz05O1FRUm1AJipgTWJVayhgJH5iTjNvV3pXdkxrVHJyb0oofDlLfllMcWA3MWB+QEpxQTYnCiAgICAnMU5xUilITXVyZHQoRHBzYHhRKy1PYjF4ZkJBI1BXV1IjZFNXKHJzYEViKnBJdjBAZXBoXk9sUj1BWGQ0akJnckYleDFhUCVQQjVoT2dTQUdRd3YhSUNRKHZrS1M3RlFIejZLJicKICAgICcjazYpd2t4PzNaLUF+SVJtbm41R1ZpUy1pbFh+fnByeGZYcSE8OGlqR3kmakZ7K35OaXFTMEF1bGRFNVM3fHd7V1BKZGslVztUKjc9bC17aTJ7P2RJdjlfWEZiJXVfUCN+fnp9JwogICAgJzJxbj49TWtkNTJNJGEkRlAzKTIqcV4ya1kqTD9SdnhlWSZyJiZYdzdeN31mJFZ2PT9Lb0lvNTNWKVZwSFdDOTNqPlV1eXlVUVZ6ZDhRcTdCI3VYZXhMT0AqMXtmOW83JjZ4V0cnCiAgICAnU1omMl5FQ3ApR2pRSSotRlJTJTdNKz5mOG08dTVwNWU7cDVEPi03JGdwTDhLQGVVUmpfNXxGVzJtazUrbU9VaXIyKDFoRldiVyskIWMpNWAqX19MTl5wdjtsaz58O217LVJPNCcKICAgICdnKGQrMlpPP002TnlxLUpwLWRRUTI0Q2JLRWI/fXVkUGY/cFIoPG1wJnFHdHdnbFpjZUItUU9YK09mX2lTe0VYTCNUUD5QMXhuNDdGNn1OanpyIW5kej85eHVFZ2k0eyRGbURSJwogICAgJ0d7ViU1OWl6QzFrRj5VNiZ9SFBkaklCRXtzSDZufFItLUhHekEmS1VoVX5BXmhYcGc/MXRgNzglcSZxb3tEM0tec2s/Y0crcU1OTDhocVM+PzUtUCg+RlJUdEd+emt9RzNPTFAnCiAgICAne1liY1RifGdyYzBTMWVgd31tfnRQNCoxKkt2dkQpcyVHbEZwa19LbCVNV3o9c0FHKFpPSl9NUExPTGdONytBeD1KMlJxKzJmJD1ie3orPGtrVik1M0BaQSZObmRHVzJxS21kSicKICAgICdTJENtO1ZZfk5IYlk0RlF6PDglMkRNNGc5Wnp3R0A9U0opMnNfI1Y/dnYmLT1QSFNtKDhIdSpLc1FxY0ZFdzVxU00tOGxNMCUodjZ2UmJhYz4qbXxTTVY3XjhYSj5ZTjJiVSUoJwogICAgJ1peV1FVQVVzR0U2VGZJVyZFb35vTFAlUzhaKm1gdHM/KXxQRjY/akReb2h5Q2UtWGRwc21TV0I8YnFXNkhqK0kkZzMwRGImPEg1UClaSnxjJSozJk5MMXY3JU12eHBUU35oI0YnCiAgICAnbEtWSWFESXtpQU07K31MP0FqMSRoQnZ7Syh4WndVWX09WUA+NThQYXlNfC19NCY4ZnNKVDtzaVRCdjtSSCFvdHd6NXtWcyVDQTYyZTthPWZFfjFkdDNtX1YjJEokKiZtQCVMMycKICAgICdffUM9ODFiQ2VoSDhodTNRRGokUz0+KWpRQ3tlcj9mPVN4VT19TUwoeD15UHoqNF9+XmoxT2ljQFBYaEd1SnI/VVcpMmZlK34/K3owS14tVnpZWmJFJV4/ZGFDLWR7XyQ/OE5fJwogICAgJ3ZxR2tuSDYxVVhFWWplUi18aSVmXklMMlRtJUI9ZTBmUz8jeTB7ciRGeEFwTj5LTip1aUJabkxFJVhJUmluKUBlRGFSPSg4SFBJMzF5O3leVzs3SiRGJik+T09yel8wd3g8Z0YnCiAgICAnOFhVekpnbUhANnhAPSZUOz50c1YjPjNUUmchSipFO08rJTFKTnB2K0hkTWhgNm1ZJW9vO1U0RktRMHlSSkdaYVk2M3tIITM0WXIoLUA5bmlTKUlkWkFVVFJfTkc3Vz9oKUkzJicKICAgICdKNWJkVSpiXyhnTyVXSjFLUHFZbm16OTtnal9BZ2pqZ21AP1NoJG9ve3YxflhXKzU0U0RZP1Y2M2oyYDJNNCZhIUMrczhjSmBkI01yRSpMN2M1KFlYWFZ6YmUxYl5rNj5qeU5DJwogICAgJ0hxa3RFSy0+VmMwX1ZafGYkTVI3KUt1ZWBaOClwcmd1cjxZJXhjSUFFaCk5T1g5SDxmRTtLQmUqYCNxYVpge2grKHUyUHVMQ1lzfj19NW8tI0ErKXQjX35LWG51ZSg1aDNFbFcnCiAgICAnayR2RTFFMjdoSjtIVHptWnE0Nj1QZUIyQzlYNjNJUnVPc3sxNnxaPF8yQ0EpZERUeWVeayVxcSU+OTxaX148RnItUWMrIWxXdjc0Z1kqUXc0VXx3WilaWVQwJExCSnljI0dXPCcKICAgICdgSGNjYmFFTkpJTmVZRyUrX205MS0xK0Q7QmpPVWtYY3F7MEFWaThxYDZ1NiNZbzBZPXNlJCt1dVpXezs8SytsRGlgWDw0dzRsIVF6JFdmV1pSekk2MW9Fbmp4a2hXMmsyfSN7JwogICAgJytOYG0/NFNydWlCLUFiezF3d2teO0J5a15yQ2p4WDglUEpOXzxoV31pO2kqeDRBczsjZzslJUpoOURAX1kteHIzREFGKTdYSzZWVlJMeHo9VSNIa1JRQjZYMS0kbW1ffEJzblUnCiAgICAnUFg3YkV7K2VCa2BwIzsyKjNFLU1IMHZJaVRIUX5uVmopYVVsYjZiNXhfMmc0O1pGUiUwTXpwIzZpSkdzV097VXU+NipqT0wrVyt+bVBgVGhTP2s2Iz58OFFIIW1peDR1Kkg2NicKICAgICdCNGYjX0phNnFkbH0+aS1QUEIkaXAkJmN2cXsoU35QMXpFSlorTXAkUERrcDVPPiorPiFPeCQteTxoRkNwYiV3cmAyJTgyYHg/S0FMU3BrXzZVaH1URyF0Nklhb1piX1N4fTcjJwogICAgJyt6dW9PVWhCXypPaXFXMGVRTWd+YEhjVVVXVFI1ZWtwWFIxYGNufShXNUUrTHRwcD00V0psYWZJeGpNJFhpejl5d3ohZj1jWXlYXjYpUTc0PHVkQVhIQVJpRjtAQG0haztpMCQnCiAgICAnZ2ojaUwpRG5qWCVOemIrP3EwSnxgd2BZfVlMOV50YjU9KWZIRWElN0oocWlJVk9pPU12e28oSXZne3FPWiVXMWE9VXlgNFpKWGk+S2tOWnBMM0hibEN6PzAyWmI7NXA/MzRMNycKICAgICdwWElOSE93QTVKVEVKPUY7OTdQVXQyZVg7IVM4PjhicGxlOykkT1E7Xj4reW82MW5DPz8hM3kmajdSJD88c0MjTEdtJj9hUnFOUyhwS1AzeHJ7JFN7di0wYXtON08jbEJuXiVlJwogICAgJ3M+ZCFGJmNpSyFueSs1PVRpbjt+ZVZmLTdQfC1TJmwyKzNebVR6cnh6a15qSGFfKEA9R0BCZm5KZFVaRl8lZW5jaEsjP3FMZGFXVnhhNiNDRzg4PTxTaXFxK2EtZiV0R0sqfHQnCiAgICAnLTxBWXgycStHYnZtTVNEOXZwPyp0RWlkfGBAQCVveEVzd3lTVmRMUV5JfGR+alhQOFQ2ayVFJWdsTytkcTFDWHhWc3Vze1hGTURKeWBDa2FnYVh2bUp9QGgjWGtwRUlJRDtAIScKICAgICdjY0ZaMXtOPjlseSgkcHNnTzxoOEloP0htdnpUfjBFKiNiR1FhT1h1QSZrI2VDa14mIWtHZm47OT1zRH1BYzRDb0ZofU5VPzc9U25xNX5gUE53cE5WZnRWU3lSOUExX3ZZJGJyJwogICAgJytpRHp3MnRuYDNgaUNNRktiI0A/QyZkZVRpfVM2aHVkK2RMbFAxJS1iVipOYTU7IzhCVH1rTyZgPWBBekZ2TEJqNDZWSEdCJkBHQT5UWjwtQ2N7eTRfaFlQRSlLVyNzOX5Wb0YnCiAgICAnNFRBfjZScEBuaVZDUHtHVTUlKX0hKDIobFBfdEJ0QH1idUx3S2V0YVZ5MVp6eDlyYVQ1YmctclNwYkU0emBsYmBSP25UKmJ2dkpTOUokUDx6QERgeSg9ZCpgKng8fHxUfkN0JicKICAgICdgQW1QcGNQcFBGQXxWO1pjc0sxNk5VRWclQ2oyelFyc1FWSHRlUS08NXktKnY+bVNEKWVnTj9MPlhhaVVZPG5ySndKY1cycTtrYlFweHBqUlBYeElCKip1LVU/Qz03dz8oQGlBJwogICAgJ3R7SU9FfDV9aU1OaDd4aSFiMzltN1QkOFAqTmZgMjZmYzM4UHs5Kn0kQ0IqQDF9dnRidHVme1BySUstJmA7Nk1vQCg8dEUpVipmQGxJPCkldGklX3lPITxvfUNvO0t1M0djUmEnCiAgICAnQTtWUGN2ZChCKV82cyp4YlJ8ZCUwUEBsPVAjQWoqPDApfCpfRzF1RG5HSCpRU0tQU1g5RUdZVHB5N0tPNyhNNlZqKC08Uy1GN3g9b2x2cnE2MzhlN24/RlZ2R0F8dT5RRkFRficKICAgICdYKSZlRWctV3o8JlBffTxPe2k1QGhtPXZEbXNgUjtIRWMlMUlXTmkpJnpyIXpaZkE+TF82U2swTVVZR1oweH45JWxKQzQodkNXOS0wSkg5LW1mUkszTShkdDhpfDNxPVpiUz83JwogICAgJ3JfJEtkRD8/MzlMVz8qZFRRPmdUbiRaU0owM2NEPVBvbFYkSGE8YCFZZ3ErZTlyKVRkVGhuaUMqWnZ6IWFONjF2PVE1diYwT3JhTzdeVC1UR1B9YTFBU3RuJFNZJmZjZlNDeyYnCiAgICAncFE8IW5nZ0BCRjFoVGdzc2Z0VFRvWCtIM2Y/bDt+cTxlKiFYZj01QClhckhkWUkqTXVzS3E+TmtUOFFsQ2dWYzVzYml2eEVoJmhFeE5JQEVzWU9DQ1JHZiVhPjh8eH0wI2xpUicKICAgICdMVFF8I1ghUEQ3aTheZDlYRTIlUztuc1o5dWpxTyF3NShgUEZTczxoPkV7aUB5ayRidT9wRzF3JkZ2Tk5udHx9WnF7UUYwVns1VTZMPiNFLXpiaVJWJHc5XmpLMWskO0hJRzhDJwogICAgJyVCVSVvZnlAKkBZQSVLKDREUFNgTUF5RWU0M1F3O1ohd2Exbit3QVZ1aE17RUx+S3k7ez5aWDJwe1M0YFRLN3ghM3Jwa1Q3bmVgYHowPz5qT0I2OFZ1Q2o2V2B2YEFzKEplP3wnCiAgICAnSmFARjNPbSomUkZOe1JqS1c5OD95bDwofFhTYX4kK0RIKD0xclRPPitSYiMlbz13VzhnVVEmR1QoZiNjZE8wb0YtYDclRnpkJFB9fEh5cStOdkY0eXtKSDIkRioocDxyektLZicKICAgICdaX1JzYyklJkk2S3FPKkt0fVQ4U1YtQXR+biZqZU9iRlZXKlh6STd8MnctU2t6d3AxWXQhWWE8MXJ7RklFVTA+MjFsR1ArengqTjxTJV4jfUpoPmtlelkwYm5zS3V8bU85TTsxJwogICAgJ1deS21uNEwtMkByMFREdzxoRnpgSndYbHNiYjAwaGhKWlNxJnUzb1p4OXckM1R8QSU8SiQ5ekFsJExeNyRUdFEkdVVuOEZraUkjbWU/Wkh2YDFSUFJFUnVLNzYodE5GN0BBUVonCiAgICAnM1JAdDk0X15IX0NUaSVkcWM5R3dGRHIpSUcpdHpuPTNNcnEoRyVoIXsxZGJHeE8tb1F0NXJjVz1AaFlwPl5PbUdzclpyeEY/UkZwdUs7fGxXbXs7JXhUN19SYyZiJiYlIUkyUycKICAgICd6SkxvTnhmJmB9Tnw5QilqUGs3a2FJP3FMZCNYWFVCYGBSJkcpUiNRTnIoVFZNbHNnKHtCME03NExiKyQrPFRaTU4reXtrTXklPk9zbEF9Z0xDel4zJjRVazY0aEp5bzZeeX1HJwogICAgJzI2ZWRwTTRRM2hSOWQ4U29+elktVCVrRDhMQGhEbTJfQnZeeDBnSTNMRTtAIXtubExJTXk9KkZqQkl7VGJxfXFhVDg1WVU8SHh6XjhhMVF2MmF+JmQyeXxjMTxDfXRIZilHYWYnCiAgICAnWTdDellrQEIkWENROWV5aC1KVDFMM3d9QGpsZjxDJmZnN0FEWkJ5NFV1KEd7ZHNMQ3ViR3VmWmxuTjVfTX55PVJ2I0NIMlpmO1JnJG5UJmpaSSN2Q2EjJkdLJCV5emdhJFpSfCcKICAgICdOUWV7ck0xRWN9Sks+cnc2dWBVa0c+RXhYKUlGdlBgSk4xWlQlSUhoS3Qpd2RFTDNiRzdWTTwzTmF7MHBnKERPV0BlNChgJCpkXnV2S0tNYCVaQWNqTHI2bytCTncmU2QpeDx3JwogICAgJ0EraEVqQnxpdXJVO3IyMGtZOFhwV0xjZnl3Sz0zb0J4Q1NZaFRwTlZ6N1dMWGlOVkcwVmhxMXAjZEEkNStjWno0TitTXyR1ezZsemxuO0k5KXdWO09efjJNI1R3aSp3aVRqXzknCiAgICAnbjs3TGM2QiQyJmw4WFM+WHxDQVVkOVpAR0s4Zn00LWRHUDgkTH4jYGYrcHl1K09KRURpQTVOa1lCKX1JUX4pQ2NhP0dFKkBSLTRPI359YmRAc3Y5USQkTyFRUShUI2hPYzUrRCcKICAgICdsKz9KPzVocUA/dUBlNmJTZlo1QFR6fE5WJlpkOWd5azs1YGB9Oz5INXk4c0NpTDNhWE9reklkXlJ5SCRAX1F7Nm0pN01PeTBlYz1IZ1k9dlVmPVg4dFlPTlRNMUFiWktSc01WJwogICAgJ2o8LXpZdWU+MSpaZUYyUDxiRk81OF9Fbm4mNTgkSGRnOU5nSX5LNEFpSSoweHApKHc0VW0kS2ZVJHJWKUJiXilpeHVGUE9taVFlU3toeDZNPUhMOT1AKT11Qkp0K0BmNCY5LSonCiAgICAnQ2BfSHlCJUFzXjdtRWZFREglRWh2bHlCTnJqTmJucXlLWXR5ajgyWHdaLUVlSVNqZ2htUHZPK3V3YmRKWTJlI3g/UyYzfGtxYitKUW4kSmxxOF9ibUY3fiM9RE5pZzdLQyR3YScKICAgICdjO01GS0FRIT9ESm14QHZ6eWF+SytfcnNsN0t7OHtNdyVaSXBnM1c8M30kYXdKNHFaNm4rNl5ubTQwUnFta2t+emohfF9DaEJ0JUMqJlRXbkk9VUZvQ1BQdzVDRXxlUTdzJFUwJwogICAgJ3k2YGZTNlZKcTFocHJDflN6Rmk3fEsyMXhXZWdXZFVSRldkVzA7ZTBoO3QwWmJXVmF9VWdGKGdwfTcwJW1yYiZCJEQ4TSRjKGpORDh6V2Y4ZGRleGg/NWQjMzxCbFd3U3xNN04nCiAgICAnbHwtUmAxT2U2UXFjZEBWJHIhV241cHRxVzxzenk8eHJ0SFd3P3dUJll6YiZjejxqXlUzWmJhO0hIKCt1SVFvd1NDe0ZwPWd2P2dMKjl4IUZIVkhjLUMybmh1RWxIY2ViOUhBYCcKICAgICd1PSVmY0VmdW9aSlJFMm9JIT5BfWNlJHFOS0AtLSVRLVF0ZGgkNT00OUFTSTtqUkNPKkE5eWpIdTxuQjdodDdzOHdRKWE7PiF4R1Y+JiR6dDA7TWJDWSZPVXhubGp6THdtSiZ4JwogICAgJzVmJiQpX1FxYEVMPlkoTFBUMyg8JDZOT2UhQjQzI049JHpiI3dmX1hgZjZtQ3V1RCZsbl4tUFo3X21URlZrUmI2X0UwLWIlcVdqfi11Qy18aDViUi1URCVsZXpKRGpGRVMoJlcnCiAgICAnNFIxYVZlKXMyOVVaMSVUciUlIyNpOUJBMFk9SiF8ZCF7ZnN1YWQhVCZRSyFPRU0weVpMQWUtYnVObVMrbCR3PnVgaTJvWDBOZT5xVFlsRU53M3JOVUl8JXhtVn1oYXJQaENQYicKICAgICc/LU9FM042eXBLQCtMZGU9P2t5MiZEajVtdHBqJF84XiRyYmY/PHwjY1NNYFhxaS1VUHNEdTQ0S2RGTCtPUk0/MXUjZldVRnNRYDJTbmNpMjxLdT9NWUlSfkxHZnJBPkhrWiExJwogICAgJytjRG5hKzhtJnw8TlpzYnJVTVJTPFMjeWZnPjBHYjxLKX0jb2U9ZHN6T3B4NGNXeTE2aXpRUjFwfHxPS2RRZ3I+UC0pJGM0fDAqbDxWZTQ2QmpvREdQbnUrO3lAQHF2ajk5bFInCiAgICAnV1BXYSN7a1h4dGBOYUJnNUN3KF5AQkxSVyF+cH13PlhDRXlpeXxQLXY2T0crVzsoOShneHBUeT5YeHxKNE57PFp0b3cyTz9yfUV0KHI1KEJQUFMtXkVoPXZfMDNLdkB5NEAtSScKICAgICdFcEVwUUpFc0IoYj9PRGg1ZlA5I2lIU3peN2ZfIyMydWNEUFZgWGVzQCNyN2k9KGw+U3stZXJIa2hNNyY8NFRIfnRrTWQmZ1I/eGtvY15+cnd1cmpqdmxxVHA4NUAwVlRvMDtDJwogICAgJ1MqT0tIcXNWITt1e1duKkxmWXNkUEkhaVFFRkNyTmAmMHVkPVpwe1B7K2A4WSkhSWgjaTgpR1pCWEFxalYzcEheUSk5Szg2aTlSU0FzWHV5WntpbDVyM1k5bl5eSFdHaFZPMEYnCiAgICAneXckTSVwV2s8O01IX280TE94NXNKZE1XYT1tfXxEKWx3SXxmKGthVTZCKD1reChMfU42NU1ZUU5BLS0tZU5aVmwxd355PGNXJVROIW0hVTIqdnUyeEUtUzMxMFNUN3FnQVNVZScKICAgICdtcm5UX085TiRJJVQ8YGNOK1psUVJmaEw+JCs4PTJzRyQhOSt4VWRLX3FoN2M2X3BUaGhgKFl6JFZfTmdBQV4pVkIkWGE1WUlwO2xHKlcmemZ6Nzk9enpkKjVsV2RQPFIqbTlrJwogICAgJ1hqRCpWWFMtNlJMczJtfkY1R21gU2llTlBsVzdnWk14SGBYWmF5fFNgfWk4RzhkU1NjO2VlKD8kQmdhJGxyNWJWTTxjckZ3Xi01Xih8Ulo8NkV4cjhVcGw+blo/PFBVeilleGcnCiAgICAnUCVzSDdfTV5QNXgweWV6Mz1TQ3YyWXlSP3NMLXI7JXhCMmtUTVlhYl9qS1B8ZFo9RDVsYFB+SiR8aDMzKj5Ld05DaypuWnB3PnpLI1o+P3B0bmhSVTZHV2Z2QVNEI2c5UHlEdicKICAgICcrcmNIOSpDRWd+PTx1PjZjQXVVbUYzcCRWcGJ9Nj94USFkbGhHJmB8dDI/SFBlRFMqUGZmVlZxeSgkMT1YTi09eHRqWj5mPmJRPnQ0XiE/bkp6Y1ZPMGx3fmEzdH48YnpeRzkxJwogICAgJ1RGJVhUMHFzM055d0l4YTspaUpubU1YOW45RUhwR3VYTzQ/K0c7NVNuNXliQyF8dnV7PHZqXzIwcig4QkxteEdqSCpSd28jdCNCbGdKZSF7VF5aPm9MO09heWR7YnwwWEV8LVcnCiAgICAnMTtsT1dNdi1objdfe205JXJ2fTw+ZGdfeCtRQW82ITQ0KzRqUjcpWDQ1WXdxWHBDcUF4Pj0jTTlzeihKcWUlUylmZkJpOG4rNXlgX1ZYJVIkSXZ9YUgqaVohdlMyNCNxZ1FWRicKICAgICc8WF42K0YtTmp+cVJXJGNaXytqezFDPTd0bWBeYGZQNTZWTlBadVRWRFR+YWwrciVNN15HRGVXVX5PIXM9WGw9VjVNSzhxU1V8Xk1EZnpNU0t+Y0ZZVT5VQTN2cGFZUDVyITYtJwogICAgJ1VLa2RZcmk8PDJLYVd0UDQhb3JsJVpYWGNOYk5wcHI+TVBzWClZX0tCWkIoO3ZBezh8QWlyJnJaRHx8STRON1Mjan0ydlNrbGFBSVUjZmNwQ2R6ZytSSjcoe3RjcWJhJGx7LX0nCiAgICAnPm83cUJZWEN9MiFoQn5TaF81M1lfU1QoV0o4R1IqPH5rP31VJF48ZElAUCs4PkAyUDJ5aFdLdkM5TD1hZypLV3Q9XmRrdGVNQXdGVnBKeS0/azA9e0Q2K3orSkRaciRCYmVwUicKICAgICdEWHM2RGZ9b3swbXhuRlh1cGN0ZEU8NDxPRlF8X1NAYX5yQEdwe0Zic1hvVnBtOEVjYmpsSmJHM20kI2ZXRzE7V0Jqb2ZWUnErYGdsV1Y+Iz1sJjQ1SHt6cXhHYTJeaD98emlGJwogICAgJ2JZMUBfY0stZzZ7KTlNbUZQSkVDJk4oYz9IKSpZXkc2VSg4TXZJe3BBPShofWUjez8/YyFMb3Q/WTh+YW1rXktsRVZEPjFsT3d8VE1lNko9NnxlV0FXSlE0KjV5ZX1IYyQ8VlUnCiAgICAnQTQwa1JoQHYjIy1RaHlpa0dIezFTRTNDVnRaZ0MzWEhxfEViKlU7b0IwKD5JelNSN0lmYFFmKmw5ZTxzJjFHRjNucEtYUGJiZig9e3dkaE1mWl5jaXtgZnhEblRgQGNnV14pIycKICAgICdjcXBAOEhBTEtOYygkPEcxPGtebkI+YWFUNns4XmpDNF5sc1MoK3VqTDhAdUk9Oy1RZnNlXkdPdkpyKEswQXQzZ1hiUSFpTDk2WlI+MSl1c2Y7K1F3aHVjbkx3ZDghI1khZmhtJwogICAgJyRxRXJSQHI9T3FgUmpVfVA8ZGkpcG1LTnUxV0tFXjt2XkZQT0ZjVFBZdiVkNWsrQzI4JCR5QEQ4NHZQbmpJTC1AZz95KkQtdyZOdntHY2wqNmhyfDU9dlFOejZONHZ+WCVnbWgnCiAgICAnc2tnRFg0NyZybUx4XkpMUj18Z2lCU0AmWDcjXkRTVVZgUWsmZ0F+QUZKTUFJU0s4OTNDNzkwfXQrY3ZSVyQ4Y05wKyVnPTFQa0pIeE9JT1FLYH08di0tQ308PUAwV2w7WXQpTicKICAgICchZkVwfVVmVmcwaERzYCgtYXMpa2hAcjBvPG5YWEhOdWpzS1EkdjZFPy01LTkzWkVKZjROc2M2RygtRHwkP2UzYHRsTW5GWVpwV0IkMD1pM3lFKmRXTFpjfC18RXY7WlNaXm16JwogICAgJ2JzcnljdjRlJDJmcmNEV0l0S2JFTGBzMDJ7Qyp8bT9kS3N9Nzd1eHMhPzF1bXNuNSpwazBafTYxU0dsQ1RVUCV3S2hxYDVXa1BwOyZFejB6RF9tZH1zPFZvbS1Rbk1HQ0d3N3MnCiAgICAncGhZTmhvayhVV2Y3dEFQNlhhXmJ3fk5XVG82QStLQnZVblljKkFhXkxUTUxvZEFLPFF2YTY1QHZII2p5PiN5QVl4aTtkZEMqJWw3TlJBQWYoVEZQTjhHKn45dkRZNm8xTFZKaScKICAgICc8YnAoZ2l1OHczTjlOdjRpNXZ4STU9QCp+YmBwZmglRXk2Qj5Zd3B5KCMjOFVWLWZiOWI3e1ltcDgoZ2tHQnpwMSZ1RzFLPjJoQnp4NSpgaXp1ZEVUSTVfXlBNMX5WfDkrUnRFJwogICAgJzJuQT1GKEJZKF9XSFolWiVWeD1RIWtNfWlJayZ3REdDcT50USQyNCUtKj48dDYjRWt1LTdwKTlXejBaQUkkKWg8cm1LKlNQbkJISjZebHdDU3IxRGs9VzstLVZ1cFY+OHdOTmUnCiAgICAnOD1AN2o8JSgxYlgwe0V6Pz1PdjBUWW5DcHY1cE9oaCthcn10b2tFXnhgdjNjLTljQGJ7QjtyME1HPCQjVWpEK3dpQllCY3J6X1A1UnY4KEc2eTFZcCNGISFnYUp7bHBAPyZEMScKICAgICdaZVBsQnZaS3FhU0o4LSZ0Rmc5Ui1seyNXZmV4OURtenFrP3BfdlRhIT8zbGhDO2xwXng7NWlMXzAxISEkVW9PWGotKFlCek05JjtPb0k2cClUUUREVCElTkJCRyh6KEpALTNQJwogICAgJzNpMkg3c3xGfFkoV1NjYihAS3JXcDFCdntyIURAbEVUI1AoTkRPS2F1IXBTPTEyRkUhQntWa2I+P3YzQ3ImYllIXlQmYlMlPld6NmN1MTJSMmtQQHg3O18zSUlgflorPVZQaDYnCiAgICAnUHZCODFHQkFPa1opWG5UaXV1fWptaWolNnUyYFFWPmhBWEMtNXZDJSNjcXtuPXF8cXt7KEwkP0MzZTRKVVoqSjJCbm0kV1ojRilvYjteME9FMXRvUnY8T1ZMO0hDI2QmPlklcycKICAgICdRWCNldiV3VCUmVis3JT9qKiQtRFVCUlhKWms/PigwV1U/eDQpZFUjbjFRIz9Sb2lEZWtxYDRzc1V+MkorQn1fZjtzKElnbkx5KGklbkwoeVdoXlA8IWsrJlFtZUhDc2g/SiN5JwogICAgJ150TGRgdGpZOEo3UXFCMGc4PjxpVj1WN2RJfEJjPGRWTHcmKno3MD5nQypFeSZXfXJ1JmY3N2dqbWBVKyphbX43cEZBbEJ4ZnRrd3smYEtETUxjKVlnTVhEako5azVTb0xPc0AnCiAgICAnbUpRWSFIRUs8dyFgcV8yKlRYaF4tKTVacT89RlMjK1o8VFVqWnZUNVdIJWZMTyFeZnM8e1IyPCFkanQzam9Tazg3QXIxOzY4aStFKkVtQVNueTE5eGdmWDVTMCFaKDdfK0xsRScKICAgICdwTF54RUxDejk7VX5DPVV2eW9aMWtmOSEmRjZBOTN7TVh+WDhSen1zaXgxLV9rdChmTklRa1J4Zz8jSTN0czV5SnJ2SW1TQWU2eE83R2hKalRxdy1oUz1tPHRrSDJLJGNHSTBgJwogICAgJ24oJTBoRUhETH1tYEVjNjdNbnZvQk89QnFpKEVwU0hOWTZtWE1GOWEhWU9OTU53e0JjRn0/PUs/UEVOdXloM0NJZHJzbCVkRHY4XiUhYEYwPkBrZ2hrY3xhRmlFc1NndWomPEwnCiAgICAnRXteLU1qP3ctckxOd1B2VFRuUGllUHBhSCRTcnZMTGN9TWw+Z2AjK0ZNeDRGdDdiJlFrK0VEZmgzQnxMVFNOYWI/UXxUdldgNFVVNSUreChod35yTFJBc2EzNzhoent7dU53QCcKICAgICcpd0AqPjtheGBkSEVhdUBGISQpSjtFUDlUWXglOEFEQ0tTYE1CKGl3ND04NXU+dnoldDRlfjlZMGN3PmROWFgtb2JCbmZCXkRLRU04ITE7TiooezNvKGN+Nns3N31MJDFiT195JwogICAgJ2ZBY2dvWERsV3tPfkB0MWghalN7WilnfCU/R2xANk94KHxfYTRTO2N7MDI7O2NQNFlnWXN8SVFlZDRsX0cjeFlHdiMtaTFqMWxYPmxeZXBtcEtgfm9CVmBDbmNeYzFmaF9sPkwnCiAgICAncisjNVFTV1NLfXVhOztFN2dLZztAWlY7eWswO1VVVWw2e0BWWDN0JXtjYTMlUSpmJCQwdn4xRVYhWURZPFI9ajw5RlQ/YldLQSp0WTtAYWNhUVRLMTRwYGpFandsbD04ZEI+MicKICAgICckP3FBaE0xRj8zOWFVc0JnYmI7ez48Mn1PRCVpO191T0llcCtjfFd7T1FNSCQpaCg4Sl4oNWBiM0tOKyh2Rnk/YHI3TFBRZWRoWj98Nj4zLVRJaG0kUnZaU0klN00jR3VhIzFTJwogICAgJzQjQW4mSHNPb2VieWFDPml9THBUVVNZQXAyTSMqYSQ1TDF0WkxSVWpvQHJSRnBDJGdfPiMwRVlUS3xxUXdYZyF0QWdjZHpKO3MzMldHUW9JXnMjJk11MXprUEd1e0tRMDRQJVYnCiAgICAnbnEje3xLOHVSd05hX3RZe21pezI8a1ZXfTArbn52U3hYWD93SjJXU2djS3J9X2N9KytkVDt8VD02JD1pck1UWjdONmsqZjtae2s+OGhCIXh8QmYofHA+YXY+KDxgPUw1RTNJUScKICAgICc2NlM4Xih3UDdzYHxVaVNYJjtMej0wTSpHR0xRemtnNFVCZE1JT0tVU1ZwfjBjbGhHTipsOFZsbCtpZlcoSVV+bHpSPjxWeVJpe2h2fX4zeWIxbU5uWGRVTnUwcFBxTWo7KCpgJwogICAgJ1RHP1pKMjZgKHl0TlJCUTxmYztMNlJHZkdITWxNeUJBRnZLY1R6VTglaGVkTF5Lcn53eXQ8fSUhYjllRS17eFExcllzejlWUmZoeUhhdjZHKG09cC1oY1V3JDt7bXhZMnRZdSMnCiAgICAnSVMxYXxLail3KWIzSCgwPG0kdVhsdCZFTFp8dmR0PTE+WiR4YylHP3hZeipFT1krLXJVIUd7RnFZYl9EcX49RnViLW8zYWdgfGpoKyZrdVU+Z0xVLW5GVHliQXFjczV5e15BYicKICAgICdKJXlSc3E1YFVubn5jeitgUnBwfDtPMihoT0xRM0FDajxXa2klTVlieiNiXnRJMHlWaXItRFdPWTJRR1VZS0ZCI1V7KGVKIU1DQTxNNkRLeSNpezxLTlc/MHB6KSZrQ1ApTkpqJwogICAgJyQ4MW4qOCE/KjdnSiY0SHJnVylHUG9naGs+TjZLMndPVXZyXytIbGVmK1l5KUt7Wi12eGVpM1kkdC0kRnE1djVJdzFIYCExPXFaMjljaV5HbiFlVntLPyFtLXlQYyRpQnt4b04nCiAgICAna1pZI1VkdjlGcHclNFhSQUpsI3hlUW5FMDQqQlghQFVOWENJSmhkXjsoP15+M1VlVXxycz4kTyR2ekdUVE89ZXhDZUpHTj9GXj9DMWx0QkpDNWcrOzcwV2VUdnZOMlpARkxwVycKICAgICc2OXc8RXt6WFFaaygyPXhDYyEmZnVXV0M+Tm1Zcjdzci1+Xk9pdCF2V0YtcmpAOExGTEs5Ql57VXhqQlJzQUZpK1kwOHktNT17MjRNVSFremVtNlQ/cXZsKnh5PWBWdkxAXz0/JwogICAgJyRyc1FRYn4zMnktO2Y1O3FtcXZ9NjR2SXMybkZnRFVldUYraH1WJUwpMW8rdkFjPmRCTjVlUVhNeVZiNyYxbClhMEI4ckRxNWU2RHgpaE4jaFcwWFZROUktN0xmKWVTbmNFU2cnCiAgICAnV1A1WVMyOFRYdE8lJExGX2IpIX5nKjNNYDxySGV9JkxLZihyQ3IoY2BNXiQ2PTlGbnxTXjNeMGJRTl5qSzhUTVVaPihwS1NqNyMpUlo/T3hGOHVReDhVRS0jPXd0MzVDfXBwbCcKICAgICdjbmohUGM1PUArITUwJT1fQUhNblpGIWZENDZZWTJFIWpfdThXeT0tRyYoWTlOYCVTc1kkcUslO2JfTiUmVThHTkpZNmMrTCVAQHleJlJ8eVBYdVZ5KDNSamYyeGgzPSh8PX4yJwogICAgJ2l2QCV5eHVZNXtuPjk4aWllNz0wQFUxVF53KENFel9vQzBsS01ON09RYVgpdChrfGUxITk8I09zWiZWRjQ4ZHg5MEIwXlRleF4kY3BPbF98UHtpQ3liTVFSNF5lQ2VNIVRLeDgnCiAgICAnSzxfeUh2NkdpWW5mfTsxWjZTX0k8UW1MIWdMWUBJd1UxTmV4cCYwNmR5V3pjLVIqeUxyfSMpQ00yZjxiLTcmKVVIVllUb3YjM2dZRnlTeVNgYWJhPXVgSW4mbW1MJnpEaEo8KScKICAgICdYeWQ1TGZlPG9EdVV3NEdRQjtHO0pUYXd3WjEzWEtVV0MrUE1NSW5ub3NedVoxOGhMMiQxRW5hZStXWDNUTHJ7fkRnbDtuJlA1dDFYdmdlaT1wbD0jWUBkQVViXzlKd2k5R0llJwogICAgJztNa0UxUSZ0dGV3ZW5tUiViVzd0NF91UDFRaEB0ZGt8P18oU1FYUWdRJnpDMXglNGJlak5PYHw2cE5KUTJjVk5jRlEwQERveCYpfll3WHMyckhRTEUrUSN4QnRFb2NhWGowNyonCiAgICAncSsod2p6JVBpNE5pMyZ9PXF+UCFvb3BrVGVqVFJeWndMaClHVSlKfiF4VmxZcz9NKlZqc3s7enhoNiMmYzRDITtgYk85QHh3JXwjLS1MTnF3eTtIeE1wbklydSQ0SDRrWCtnZycKICAgICdqRUdRI3xCVDQ7YlReX0s2XkJESGtAcC1geUJzPVcoZFRfcUkyeDkkIXQ1QVNWbz1rc1VabCNpTTZnI01rYHxedGlVZ3pOMitCJXM9Z1VxeCQqYVZoYl9WajZBNlZIa3liWjRuJwogICAgJyM2I1FKeD9ob1ZvWWk9eyRtfkh3WWN8bUQ0SHk7KV9HRiheUFpSM0I5JD5wTkFiZUZvciRnfGU5fnErKVFkP2dSZFYjVmJuU0ZReGRsYSN5SzlHYj4jeWI5cDdIMmt3PCZeXz8nCiAgICAnUFpsaz4pfUVGbkoxSlpvK1ZlcnpnbkRONXR4bXx6S1d5WEk8Pzczd0paUFZtbzhkeFliRi1Ec0R9JnhfPFR4V3ROem4rcSU0LUt8SXteK2JXfTBqKilXeG5nZHxaIU1CY18jMycKICAgICc3fStGKnUpWGU7UXxmaWMmeTg5a1JHPnM+OGlOK00jbi1MKlQjIXh6cWVYJGFFfUtaRUQjYHNlQG81fUhweGpVbyZXbTMqNUp4QXImJn58b3lfTktNIWYwODhlYU0jSnhffmVWJwogICAgJyk9Mlg4OTxLRFFFZzZoUXIxS2hNJj1VOVgzfjExJVVZPzJmOzZmKTlpUVhxekwtYU8zY29rKU9nTyh1MXReVTRzd2hQfmBWZW8yfEs9bDkxN21TN2V6PCo7O19LK3Rhd1RgdU4nCiAgICAnJWJ5fVc9MnojbSZDP1ZPcjZjQmk4MylkK2loaFp3diZlIX58NHJCKlRCbXkwQW9Xcm0wWjREUXooYjApRXpldkhkbXFucTJMO1huTTJ3bGE4SWx+b3V3MVY/Q2A9Kk1zKE4xRycKICAgICdGTkVARWlSXj1TT3lRS0goQHhpVUdCWmJ6LWZpcH5uU0dRRFUtfm1DdkIrN0paaG0+WFIxPyF3KFdiT1Qwa2kkZlpgekQqRj5NYX1MR2hQaEBHQ2g9LXloeCpLPHg0P1dVb3phJwogICAgJ3NiZyRfaWNJKmFrcWZ1LSZuYCR2dkRwSTBjWX1JdHR+KTlye3hUTCMxU3ZAPD9RVT80aTk7PCtMSFFlITYxXzBZP0gtTEZgKGQoZFhLSVpleFVkMnhKbEdRfmNuSS1qWmg0ZkUnCiAgICAnV3ordmUpYldOPkdlQUcwMWxtdTshX1Z8VVl+OUZaPC13R1huS3J7Wm9HcXt8KkxiKTROXj5uMyY4SzhVP0lrUi04RWdeO3h1fWJmS0p+a0tKVF9FS3NjVHtCfDY8Sj9ncG84SScKICAgICdObj9UI3B7Xmx9KGE1dzg2VU1abjsxMHVwJFVYeFpTXmw2aG5BKF5mNk9kZlMoblowN256U3h3UjZ3QW0hXlM+O157RnBhMFQ4MkxqZTFROz1qc2s5JERIN0psQXQlWU5oNysjJwogICAgJ1lRWSNAZyRVPUs1KmFZbEA+UDUhRG1SVClkfiEwdi00IztKUCtIPU1xKjRrWWhtRUxBZEw8fktPTUctaEloWj04Wmo3cCkwdVgmYj51Q3VVUjNfT3lXe0VGP1AmWUtlenV5SVcnCiAgICAnNlUrdVkpNDdOcyZ6enVhUSRZP2FeXn1gNlhGQD90dDYjVklNMWteVFdzWnhHPW9hUSo8fjtzfUNDR2MyJCh6RGlqflhQMVpGWl5fLShNOWpIeUZ2I3tTSm1oYzEkeVcxKz52fScKICAgICdjejtFV0swJGRpVjxmbjNeT3FOfmo8OE9YQ0Mjel9gaUlnJkF1d3Z3RHpsdFpMKylyVWZWUUVnZWd5NWV7RD5PY1F0dzdFRk1sT1NySktHO3ZsRCM4SGExVlJmJjxTI0JKKyM3JwogICAgJ0A3U1B4d0hROHgpV01Be25VaVdnJWRAekdtMkNyeih3Yzh9SX1McnBQejZVYjtMeTxzbmh5S043NF9hU3F7UFl2Wk1EYTwoOC19anl6SVJrdVBMa1QkRDk9VD57eDthZCFlRG0nCiAgICAnd3RzMWpRPCVkXjxURVpDWU9BVChjOUglQyZsbns3ZytXNXQzIT5EKEAwUVlzQHQ3NkE+JEs7KW85eWQ5N3ZGQChFOSU7bkJyTTF7eSk8TkxvNHxGWTErPnUmUyljbzxAKV5FOCcKICAgICc1WXxPdWJAfSlKTEswO2plREZSUD1MNlJzMWteYTRPVkRmckNZQXdpbGteckh3bUhPZ00hdWlJcHFranJ1d0VqaDlFTTZzNWV7RXZNVHJRIWR+XjlGN0FBSDIrbXtLYHo+WX1UJwogICAgJztsNX5mLTNvK01iSTxUcmV5fTZYQHE0bXpzJHVWekxVSjdJWWRTZCFTd2J7fjV+ZCZRJn58V1VYQUkzUnpaYUo1YTBYNDBvUzB8NE1tS3I4KHJNR1F3cUJeKXshTnp+TFBgdEInCiAgICAnWlM3REs5bXgleUQkJXhDRUUzTy0yb1hMO0c4K2ljSjlBJiQ2NlY5Q0poZEE1JW15NVNDdUJsakA1eUhSWV5lXmlnNEtZOWVTYmtsO1ZDXjNibX47OWktRUB7ZmMhRFpxZWRuTCcKICAgICdeSmo2TU1hfnJqNTVGeThiR2czTSQxKzN+dD1sclIqRmBnIThSUSsmMnMjYVZ6RDswV3E7R2Z+Q25sXi1iKHBAYXRWKXA8e3Z2ZWRjSSM3QWMhQk49I305QUBUVDsjMkBrODFKJwogICAgJ0AjYHBCcyF1N000PF5Faj5OSm40WSZmO2J5NnpDT140REA+emVSRFJsdEJPWjkwRnQxKm1YdjZlbzFzMk1edX0kdjZoV1hoLVBDXjhYaD1GcXYlTEpCX3Z5V1F4NGVrYFhHTWsnCiAgICAnU214LWVaVGtnOWtQbkBSaj1lMFRAOyUkR1k/M1pPQzFMKTJOWG5fWmw5OyptZj8wUW9KemNGVWhoZWF4O0UwSFBFNUV8ZCQoIXpnKWhZYnJLPyVQa2A8YlEtLXtQNitaOGpBZicKICAgICdsMClifnJuOX4yRipMQzRQbEpRTlQkVHNOSFRlYzBANjRtV3hWQGo/NnAzOCMqR204Yk1TeX4hYWdoOWhAdjxaeGJkIU9FMnQ8THBWSW8lSiFFfmMjVGlnYWxPJmZmVDwrTSlmJwogICAgJysrZ2okVlRWSWgyYUFfSllAV2k7YjYhYTUydHtiTDZyMUA4PGxFPUoqZHttVXQqYTNaJno1X3YpMDJSIyVydiZTRT0xJGJgSTx9OSotfHhDbG5Ya0E5UElRS3pPYGEhSz0qeVknCiAgICAnZ05UOD1UZDFXWSVXYz1DNnFMOG4obHtBdjxvUlRaZylvVz8lLUhkIU9OVWoxZ09CI1dXNmdnODJTP2orP31VUyF2fXAxbVN+KGlRLV9Oa2leRmZ3a0ItUDc3dyRmLX5kcHpVRicKICAgICdxZEw1T0M/Mjl6ZX43QV45fWZvaS08VlUkYjYhRFFpWSlxd01ia2VzITdHb1JjcmdnUyE3YzFaZ0FiN31nRkNFNjcob3FXN2ghdSFtcnRsIyNfJTRzR2Yrd1hoQ3cja0NMelNNJwogICAgJ0gzSyVpOG5GQ1dYaFklPylnQX1JLX1hVHBgPjxgY1gzZkx6OEZMPykoSGxWQHRoSXJtd2M8byhJMjZwSS0wazReS0cwMHAwV2JxXm9ARTd3WUFoeWQpbDA9MW5PdnEhMD50UyonCiAgICAnYVpJOFdmVWJ2PXRRem5AdzItemNLKXxLNUZkUzFHQSY+cG40aXx5c0Y3LSl2Vi1WNlF1LX1+VmQwPVl2NCF5VHgkeXhBb0dwOUU7b2paY1JPXm16aSE8bEhpVVpeZmA2T1VXdycKICAgICdxX0k1fnIhXzlYeSluVzBRSm4rVjI5bkxVO2YtYFVNI0pSWmQyRE9xWnleaDxZMUMpeWA/WTAkcTJCcSEyKE9CcUBvWiVPPXFnSlRHNmNTfElFSCNqKyFxS3kzMX5pYTxOSFRjJwogICAgJzhHMGAqSzF+YGp5OXgjcCh1fU9VcDRkZTI7NT0kXmA/dX5Qelc2dV9WbGx5OVBjQXtzdkdmd09NTz1hPEcpRmN8NFlHKTZobDJYZWhCdHx9O3V8R1F1N21DRWsmdXVgYlQ0MmwnCiAgICAnRVVBVyl8NlMkVW89WWpJPmN4Nn1tZUF6Vz9KQGBeVjBqQm5CN2ltMTVlb3FSYDs4OGBwR09eKTxuTkl1K0ZCMXNCY0xuYE5qWmNEeXZVbGpmfnM4enNhUlplZ3k2cWVwfmQoNicKICAgICdZUjwhKyRnS0tydGF4WGZXJmU/eSVySSVNZXpAT2JkcFFpZzBKKGJyWllwUT9IcEc+Mi1sVHNjKyRnalU4Uzg+R0l1RWctTm57b0FIdU5IWUAhdkJmYGtNPDMqRVI8dWBLRlg1JwogICAgJ0VlXmZ3eVdPKjJ5biU/R2A8M0xsJHJuP0R7MSNFRUNlOWttMWQrNnEkMzl3VV8qUH4qbzBHMkZkMWNeVHtCNTRwZFVYI1QwJW42fWcwdXE/O3stNkg3UygrTyR4U1hhUCooQiknCiAgICAnOD5NJS1efHw+cCVHRFJKRCtMVC1MNkBhblhxZzE2Pzc1NTlVSHxJWGshSmZFKmVXUiNXM04xaD07KzdYKlFSY0EwYSNpVmtQcDA9JlBERiQhUSQjMTB8b1JkUXlJMzhzKVB3VScKICAgICc0OHAwZjV1Zmd4LXI2YkxfYV94VUR7UGVvci1DWmAtaVR8ZzRtMmxXLTktRFp3WGw1JXJaYFhQQmpOem9HbmpMTmhXWUImcn1laCNRNmQ4WGpAV2FFZURZKCtoNHBKbG5PKmlGJwogICAgJ3FkUFFGTmYkV1p1S3dldFNRMytqbFlPSE90XmReYUYrV2gkNEoxKlhvM0BKUGU+ZntYKmU3aUstREhoXnpNKFFVKWlqQSFEZyshWFZKZXNTMD5pXms0QFQxNnIoNWs+V2ojdmgnCiAgICAnaT83OzlaJn12enNBdmNfI3cxUT4zVmpfazQrRl5oRktPOEMtR3h3JkBxME5jYiVLPT9hS2R2fmJYR1pIP3xSNl5JWkhQMmRJbypyY1Q5RlQ0fkEwYm9WcUtOQyRMbGNqam80TycKICAgICcrV2AlSytqXmZfNmd2QjNfJGtoJil8JXY4NHcoYjEoOGV0JXAwTStvOEBxVERYOTclNWpGOzRBcCttMHNjQD9JdHF9MGBzYVFQIVFMODFvJmN5WDw/eWl7TU1acUwkfCZsY0s3JwogICAgJ243NWFmMm9AKUdad0klaWpKSjBqb3Viej09QTNSdHRMXzhSPjw+antZOVg2NzQ9TGUoMTRuPzJ1aSk8amNDMkNeTUA7RnxGfGRJbFp8PTJfZWx7MzhCdzZjcC17d0FxMCtFRVonCiAgICAnOE52eCE+SnxwY0RkaFI+Xjd2bXY0RGk2SmVtXzleJUYrP3l6bklYZjVZUkEqVCRXKjtYNFdIYlN+RG84Wm57ZXlTR3NtPjlISWZ2T2RBQ1BCQEIhMzZJfWNpKHM4SVg5PTAjXycKICAgICcpRWs4UmdzUnYjIU18THFwKzZXKzw9RWVEYGt1RF5APlhEXmJKUDR5RkRSdCEjPWBec1pgQn1wVl4/U2cwPip8Xms1OTM7bjEhXilRWiUlPnMzdHdUWT9OcDhxNjQqOHFBP1dxJwogICAgJ3E3LVRaMHM0VE8lZDUzTkdvWEFJaFNgcVhzYlh2WTNGU3pCP0IkMUkjQkZaaiFgaE56MWNoLUAlZHh8eHRKY3dDRm5OeD1QMjAhITFWLUV8VkZ5JFNqdHc7Sz9tZWp5S1E9V0InCiAgICAnXmpgSERtK1l+cnBgTjtoU1decWR0MWxJNUZ+KzU2cE40d35ebzRDSUxBQVRyZn1SXmRnNG5hP3xGcG1oR3QwZ1FEIV9Tdi1oVG1ZYypzK0JGVFlVWXhCdSNPMURGMzhib3JEKicKICAgICd4TEQ7TmdSRHE8ekd9O3xsYFBVJUR9MX1PbS0lZVMkb0hObSMjYm08T0lgemQhKVhzaHU/OEx7LTtNelVBR3w8V256WVdPVD5DdyU7QzApdDgwWUhBO09BIW1GPGMxTiUxRjUzJwogICAgJ1IjZ18rZVh0Wig0SWNTPkRoSCplXlM2LVFQdUA3Uyo3JWMrZ3NnanVyX2lncWExcW9fYj8zQikmP3FjOWNuRWN5KkJHdEQtYStYRV90dlZiWmg3V2FKeWZzSiFLRVk0PWxKPy0nCiAgICAnRilSP3dWOXVvM3poMylHY249e1gtVm5fR3pja2ZRO1dgV3JmITgkZ3o2aX04P2V2cmR5Xit7I0lXNis7SHh0MDc+anlmQ0RWQHR8cHJpcEVyWT84K2JOeFc+cWJVI0dGVUQxNycKICAgICdvbyEzQ2dWNTtAMEhlfjVjYUVnSGolNyR5SkdjQ1NEeSRscUhFPV4raCRPcXUpb0xjTSgha0EwU3I2aWR4SUdoczJNS2oza1UmQ0t5eCo7QjVwSyNkPVdXOHlXWWx7ZUA5Yn5TJwogICAgJ0ZBe3Z6V2Fac3BNPGFvdD9OTW9wK005e2YjY0RoZjA+MF9ZZTNqSU4wJTJ5enc0Z1FlVG5yMD47Q0dWJEwyMDltT287a0ZMZDw4dFM+dnYoWFgzcDleK35sXyhEP0Akcl9VMnMnCiAgICAnQ044cFolUnhDTVBffHh3JHhkaEgtYnReRCQ2bnhNJVVFNVI0bU4wQE81NzIxNztwfHEwPXU2MTViaUF5dEtpSkRjTEFwOzt9KmZVdVhlTzNlVERWRmU0SHskTiNOYU4kcChsTCcKICAgICdHO0teSGZ1R2F8bmZEY0cqZ0hDfFgmLXNyKmR+R05oXk4lUnU3KTwycG49S3QtJj1xQWwxKktiWEJyZ3Imem4pK19+bUVeZil5QWViays8b3ZJNTBfV0d5OFBSemZ8e3xFeU5IJwogICAgJ1VxaXw0PzsrMiE8MXthUWx3PmJ0Ums4KUAjaCpIc2RMbU91MD9hcntKaj9vTklJS31LclEkU3JGODhPWUtoQCFBXytCeCpMOFc0YXcmWjtsKkIwYSUwb1heeENxcmNMQEZvUCgnCiAgICAneT5ANj5vTGpRI0I0TmJmaEZOTmhOemxGYzdZOE1Sa3MjXitTUT5OVWAyT1clbyZifjwmZDtLJDxYajhnY35mNTZMVUZ2JCh+UE8qNyVic0tuYE1OJmx3RVc+Z2I4V3RPXkFlJScKICAgICdhVmAoezN+UF5tP3F8P1R0PiZPT3t1P0NIRkl+ZSQpMkRxPTlZTzxjRCZSUFZpMDtofnAxUT8+PmcyPD0wP18+bW5fbUdxZmd1UzNXdzFSRCtga0Y2QzlBeXpgfFcwYy03IVRmJwogICAgJ2EzJCFSVTRldj1VXnI2NlVqb3B7MjdDWjYzc1AwcSs8Q0ZEQlNydFdlWWE/VXp3YWhvVGpQI3xQZ0pjVWlFTzhPciZMeUgwI2d0Vk1JPWokKXREdWZIM2lrXl8yfSk/cz5fKFUnCiAgICAncFNmfUphKDlAOV8yeXhDeUJaQGJJYElPQlI9RGlyXmZQSFNPX3tKWDhqVGhrU0R5eHpgezM4fk1eJE9eUD5gQllTNEUlS0B3bCF7O3JePiUjUHw+NmN5eTZ9PUsyU20wUEZGZScKICAgICdtOUwrfDJjZGlwUCg/Zl5zdyshRVNRKTRYQ2t3JSpiQz1iOylvLXJ+IUdvQmA7VzBgO3RISmFrZHMwVEplUDQ9Z1lwMCNFOHFtZkJ1KGRjKElsTlJDR2w9fXopcVJRTHJqTUNuJwogICAgJygrKDF3JW01NlhYbnY5RT1Xfnw8JHFAV3VwQnledzdaSGc9S3EqJERib3dBM21DRjh0Yj9yTiM+R0RBKCg0eC1DKEpXZVhpeG5UMVpuMz9IX3VUUDIlOUVKcHJKNShtKVc8YkgnCiAgICAncEhnOyRQSDZ7OXNFa0tZYzBWY2xOVUA9Wip4aiZYNmBJKUp5WDI5eFVyXyNjUDFPJnUzbWJDdiNBIUZQaHRhM1hyeXo5TDc0Sk1BWjNGcGFmKmFldnhaT1pSODxfWWNIZ2cjeicKICAgICdKV1gwNm91YmprIyN7N01SRktsMFI5JmomdVYtIyszfEFeJmJXOXcoVjVRU2w4dTJJZHhqNFg4SH1HKXd3e2hVYWlaOHw7SjAwUztWczI9KHYrXjBAR0ojPUc2Y3IlWm8hMTdPJwogICAgJ3FMUGtuS0BweG1YMGU7QEZ1entIbGhsMiFpUGhFTnFZK3deKXtkPV8xRSs3TTEhej1iPDYxfVd2ZHImeGswN3V3RGZlNU9pTGxoWVN4S2w7Pj8/bD43Z3R6N3clNDFoXnF9emUnCiAgICAnWHtxQGdeVkthYU9eUVlvUiQ8MSNjWHRPcVJGNTRRcERpc1ZTeyRKPTxEVigrbzE9UGQoMU5fQlpzQk5hY0w2NmYleD02aHVqKk47P3dwQkZ8SU9LbDwmX1NKV1JzOUFQNyFsbScKICAgICcpeEtEfDcmUl4pZW5oZWNQYjh5WHo1UXxgUlgha3xOPzhNKyRtOylAVE00ZjRJPztGfkw/MDE7U2VkaGY1R1pwMTVEeChaJCozb1Ujd1ItbUhFYkUmJktTRyQqd3g2YV4kSWc/JwogICAgJ0xGQ0ZCKzZsfVNjKz90VWBhNiZxOTl2OVA0NGlGPGctKiZkckpJKjs+KFo+enRMMWFaelY2PXUmWXJoQExMQClXM0xBfEVZbDJzaHQmQ1FsP1R4cEAqNUpKaGp1aSZPJkBzdisnCiAgICAnP25qK0swSkN+USVJWFB8SHsjeURqRWREX09UUXklUFdgU1c+MVFiKF4tPSNOenFFTSN1KX4wPytDdDFsKjVWMkZkUHVtIXAxYEBsQUcrNyN7fmtYO3p1cGQ4YDZTVW1RSkdJdScKICAgICdUdkdnbGFaYz5FPHZvcDtjQGFlfjFlcDxQVV9iMXYweFJVVGpOb2YzcTk9QTZrPWdueF9fYitlayllQSszWGFCTmFSP3M7JnU8Z09pY21ZQWwmQUZmbjhDZnh6SXMzMDZocyUpJwogICAgJz5FVj5NT3dxQkM9UGFFIzR5fktHRjBsNi14eVpZMnF5bHw0SDMkWCQjTDA/OGhJS1NvMFhNKyZIXk52QUhDSHw2MWpQZXJ0NkxgYlNjcE4tN21SPFlzWSEyaUZFRVpROG9PJUAnCiAgICAnQW1nU05JM2w/ZVk+JlcyYSZHRFYqPFFGWE0jcShRb2NHS1Z7UFZ+PTtsdzFVWEBhVDtNS2dHNkdEJDM/c3lGYUlmYDdUck5Meyg5RiVXdGB0UVFvQD80KjZMMXI3XmtZYk8kZicKICAgICdQbUhDZjFrRSFCbHM1QHNMI01uKihvRjdTdlhOQmdMOTJqYGZ+cUMoYXNuQmJiVG57cU1BfT8leytee3FAaTVSQ0JXND09OTV8fSEwckdUR1pyU1VHaXhPb01GKDImRHFYI1BpJwogICAgJ3hobHdIdyN+Jms9al4tMjVqNUpgUHtqWVgpWFN1PEMkUXU9bFZuQiEpeTB3Zj9efF5GYTw1OWtiaGxsUSNjMFpNWD4+Q1BReU9IKzY/P0xANThuYj5rKWk5WUp5NXdLSXwjbFMnCiAgICAnenhOWjxKcU1tbzJZUHEja0EyfCMhNXpxNF99XmdvIz9RJjMtSXIqNUlMTXh5QlRROFh6ODx3bTBaNW0hVzV5bE0oWiV6R01RXl81Tzx4JFZXTUUyeFpTS3F8P0JNYytLJncxdScKICAgICdfVkZZdCRvV09kWWF1ISVpZnFOX0hrZjlgOXxaflJqU2paSjFHQSFEOVopZURTeXxZNThkZHN3dWpuUHdpbC03dWRXJjdjSnBSJjJlZlRoODspfGVzSElGJm15SGZyOXtqPEZoJwogICAgJzg+YXZteGRPcVRwRnxwMm5Ta210Y3x9ME5rNDZVaDUybCtzbUU3Y2hUU1V2S2NNNCFPXj9XXyp5JFNrR0tyU2lUOWtqVnJvb0hnUzlvPWRuWjc/WWRNQ31+UW9+JUlycVVzOT4nCiAgICAncjlCTDJxRiErTWNOKldMS3JNI28xWURqVWM7K0ZQTGhQRkhwZXxEYFNMRntNKHc0TDdNNWNoclk9cFk1QXZPQnhkRzJxeHdScUhqeTVidTxvNjNkRXl5WEx5WkltP01LZzRHVycKICAgICclPENNU047OXZKKlB5LTg2Q0g0QFktY2E7cXZoP0Y1bjNKRkB5eHdVdit3TFVPVE0lNjB2dH5VSVNeQ2VFNnY8az9HZjllPU9NKU96VDAtVmwhXmtQT2gkeHYmbn5pNGF9cll7JwogICAgJ1dtPDY7NVZtbU5eUDQ5dytFKjJWWmNsSklSSCE9SSMyNSY+QEhnaDV4WXJ4QlVtTGZLQTs2JEYjNWl2UzxETklrKEtxVzcjcV9EQCN3QE5CRUxOOTRxZkdkZDtIYEpiR29sJVEnCiAgICAnSkhTMkNxSWNxTiVzYj1hJDxuUTBuQVJCJC0zOXQ9Ung/KE1adnhMOGtedGdpO2hQPnYwRFg5YDVMfm03KFc2ZlBOIVhjQDxzQTN7OTRAbm0hRlYwfVd+QnApM1EydGY4Z29KPCcKICAgICdWVj5ALXNqPDNxIy05eUg2QWkzeEI2TFl8U0omUEVqOEQlZjxpbUUqKXhTKTE+aVR+Zzl0KzAmdFFLejNLa2MzaXAoeyErO259Y0RST1JTUlA9Xld2NmZnKyslU2g0SW01Sj9AJwogICAgJyh3akE8NHd3JlF2bHlvXng7QH5TNGFjfkpwR3c+a0N3WiRmJVR3ODwjPUlHQiMzZy1Dam44SillYn1USGxJP0gtN3oyS0lNOWt9UTdAX2h+JikkcipiZ1lCVVFMdSlDP19vQHMnCiAgICAnP0BoTE9nPz9pV2NVRytFbmt3YWtzNHtGbVM4NS09KH1GaXZLT1RxdF9aVVRPRX1QfjcqODR1SS0pclk0V31ePSNgJGVhYUs4fEc9cHFmJWdKOFdkKnUqdmRvNGhYbl5mNld3XycKICAgICdsMm9NJk9PIShpQ2h1SSFmS0grYnIqSmU+YU9edF5PX0ZRd3peQTU8amlSLTFXP2Y9WXUtS25qaDclbXZaZ2hRTVg1WSgjK0pncmo4ZCVVLUNiVGFlIz5sS1hBdiNTRTlIUm5CJwogICAgJ01eY2tyV2w4KlotaE8pdFA0dEEmalAlYDgxUER3cyRXWGthb1VuaiVMdztDTHtsP2A9JTVjejJnTFhKc0Z7blpxNFU3ZWZrRmN8ZG9RN05ZPFgrMik5bDlKMkNeaj9YcX1Hb2knCiAgICAne2dhQn48YFkoPVklTFNOI1lGdGQxMmlrUFRVeW5KTFp+ZCF7a3tDV093QkZMeXF6eyQ1e25YUHs+WkhZeTg1IXs7ZHdheUV8M3B+Y1JiMHhFdHVidU5zdWtZX2IlUDZ8TmQjUScKICAgICcwNkl3RWtpOUhQQEI/KEF6VDR6JlVEanMmb3sxMiQrQWZCJDZiUXR6aEM8Ri1EZzJ+TCRXODxmNChDTTYkSUdeTkwxSCVmaUZUUFhSbWw5QkhRaDNlPlV0dDxIQ25KOFApO30pJwogICAgJy02MmlKWkR4SEpreDxKZDFmX1RwR1AweT9yfEM+QkdiJlB1QnozdDVGb3YqJSRIeGRaIXB1YCs+JUtNK0IhcztgMkdSQjhPZGRgKzEySk5LUFQxd3NuSEpBQiU+dUQ+UWtIUTUnCiAgICAnbSV3azthYlVoQ2hDUmF8Pj8qSmloX3k3bmJBSFh1YGJZU3didWRTV2RfKHByUjdPZn1BWCloPCFSQkVleV9mOHliP1U9eilwb2dLWkQ9Sn5uUGVEYmxUK3ROV2F3Vk1rXmxleicKICAgICdfbE4wO3hoTV4oMDBGQ2wxZHhDUVZVO2pLdkJZUWwwc3NJMjAwZGNEJwopCgpjbGFzcyBTTTM6CiAgICBkZWYgX19pbml0X18oc2VsZiwgZGF0YT1iIiIpOgogICAgICAgIGlmIGlzaW5zdGFuY2UoZGF0YSwgc3RyKToKICAgICAgICAgICAgZGF0YSA9IGRhdGEuZW5jb2RlKCJ1dGYtOCIpCiAgICAgICAgc2VsZi5fZGF0YSA9IGJ5dGVhcnJheShkYXRhKQoKICAgIGRlZiB1cGRhdGUoc2VsZiwgZGF0YSk6CiAgICAgICAgc2VsZi5fZGF0YS5leHRlbmQoZGF0YSkKCiAgICBkZWYgZGlnZXN0KHNlbGYpOgogICAgICAgICMgQ2hhcXVvcHkvRm9uZ01pIOeOr+Wig+acquW/heW4piBjcnlwdG9ncmFwaHnvvJvkv53nlZnnuq8gUHl0aG9uIFNNMyDlm57pgIDjgIIKICAgICAgICBpZiBoYXNoZXMgaXMgbm90IE5vbmUgYW5kIGhhc2F0dHIoaGFzaGVzLCAiU00zIik6CiAgICAgICAgICAgIGRpZ2VzdCA9IGhhc2hlcy5IYXNoKGhhc2hlcy5TTTMoKSkKICAgICAgICAgICAgZGlnZXN0LnVwZGF0ZShieXRlcyhzZWxmLl9kYXRhKSkKICAgICAgICAgICAgcmV0dXJuIGRpZ2VzdC5maW5hbGl6ZSgpCiAgICAgICAgZGF0YSA9IGJ5dGVzKHNlbGYuX2RhdGEpCiAgICAgICAgYml0X2xlbiA9IGxlbihkYXRhKSAqIDgKICAgICAgICBkYXRhICs9IGIiXHg4MCIKICAgICAgICBkYXRhICs9IGIiXHgwMCIgKiAoKDU2IC0gbGVuKGRhdGEpICUgNjQpICUgNjQpCiAgICAgICAgZGF0YSArPSBiaXRfbGVuLnRvX2J5dGVzKDgsICJiaWciKQogICAgICAgIGl2ID0gWzB4NzM4MDE2NkYsIDB4NDkxNEIyQjksIDB4MTcyNDQyRDcsIDB4REE4QTA2MDAsCiAgICAgICAgICAgICAgMHhBOTZGMzBCQywgMHgxNjMxMzhBQSwgMHhFMzhERUU0RCwgMHhCMEZCMEU0RV0KICAgICAgICBkZWYgcm9sMzIodiwgbik6CiAgICAgICAgICAgIHJldHVybiAoKHYgPDwgbikgfCAodiA+PiAoMzIgLSBuKSkpICYgMHhGRkZGRkZGRgogICAgICAgIGZvciBvZmYgaW4gcmFuZ2UoMCwgbGVuKGRhdGEpLCA2NCk6CiAgICAgICAgICAgIGJsb2NrID0gZGF0YVtvZmY6b2ZmICsgNjRdCiAgICAgICAgICAgIHcgPSBbaW50LmZyb21fYnl0ZXMoYmxvY2tbaTppICsgNF0sICJiaWciKSBmb3IgaSBpbiByYW5nZSgwLCA2NCwgNCldCiAgICAgICAgICAgIGZvciBqIGluIHJhbmdlKDE2LCA2OCk6CiAgICAgICAgICAgICAgICB4ID0gd1tqIC0gMTZdIF4gd1tqIC0gOV0gXiByb2wzMih3W2ogLSAzXSwgMTUpCiAgICAgICAgICAgICAgICB3LmFwcGVuZCgoeCBeIHJvbDMyKHgsIDE1KSBeIHJvbDMyKHgsIDIzKSBeIHJvbDMyKHdbaiAtIDEzXSwgNykgXiB3W2ogLSA2XSkgJiAweEZGRkZGRkZGKQogICAgICAgICAgICB3MSA9IFt3W2pdIF4gd1tqICsgNF0gZm9yIGogaW4gcmFuZ2UoNjQpXQogICAgICAgICAgICBhLCBiLCBjLCBkLCBlLCBmLCBnLCBoID0gaXYKICAgICAgICAgICAgZm9yIGogaW4gcmFuZ2UoNjQpOgogICAgICAgICAgICAgICAgdGogPSAweDc5Q0M0NTE5IGlmIGogPCAxNiBlbHNlIDB4N0E4NzlEOEEKICAgICAgICAgICAgICAgIHNzMSA9IHJvbDMyKChyb2wzMihhLCAxMikgKyBlICsgcm9sMzIodGosIGogJSAzMikpICYgMHhGRkZGRkZGRiwgNykKICAgICAgICAgICAgICAgIHNzMiA9IHNzMSBeIHJvbDMyKGEsIDEyKQogICAgICAgICAgICAgICAgZmYgPSBhIF4gYiBeIGMgaWYgaiA8IDE2IGVsc2UgKGEgJiBiKSB8IChhICYgYykgfCAoYiAmIGMpCiAgICAgICAgICAgICAgICBnZyA9IGUgXiBmIF4gZyBpZiBqIDwgMTYgZWxzZSAoZSAmIGYpIHwgKCh+ZSkgJiBnKQogICAgICAgICAgICAgICAgdHQxID0gKGZmICsgZCArIHNzMiArIHcxW2pdKSAmIDB4RkZGRkZGRkYKICAgICAgICAgICAgICAgIHR0MiA9IChnZyArIGggKyBzczEgKyB3W2pdKSAmIDB4RkZGRkZGRkYKICAgICAgICAgICAgICAgIGQsIGMsIGIsIGEgPSBjLCByb2wzMihiLCA5KSwgYSwgdHQxCiAgICAgICAgICAgICAgICBoLCBnLCBmLCBlID0gZywgcm9sMzIoZiwgMTkpLCBlLCAodHQyIF4gcm9sMzIodHQyLCA5KSBeIHJvbDMyKHR0MiwgMTcpKSAmIDB4RkZGRkZGRkYKICAgICAgICAgICAgaXYgPSBbKHggXiB5KSAmIDB4RkZGRkZGRkYgZm9yIHgsIHkgaW4gemlwKGl2LCAoYSwgYiwgYywgZCwgZSwgZiwgZywgaCkpXQogICAgICAgIHJldHVybiBiIiIuam9pbih4LnRvX2J5dGVzKDQsICJiaWciKSBmb3IgeCBpbiBpdikKCnh0aW1lID0gbGFtYmRhIGE6ICgoKGEgPDwgMSkgXiAweDFCKSAmIDB4RkYpIGlmIChhICYgMHg4MCkgZWxzZSAoYSA8PCAxKQoKZGVmIHJvbChudW0sIHNoaWZ0KToKICAgIHNoaWZ0ICU9IDMyCiAgICAjIFBlcmZvcm0gdGhlIGxlZnQgcm90YXRpb24KICAgIHJldHVybiAoKG51bSA8PCBzaGlmdCkgfCAobnVtID4+ICgzMiAtIHNoaWZ0KSkpICYgMHhGRkZGRkZGRgoKZGVmIHJsOCh4OiBpbnQsIGs6IGludCkgLT4gaW50OgogICAgbiA9IDgKICAgIHMgPSBrICYgKG4gLSAxKQogICAgcmV0dXJuICgoeCA8PCBzKSB8ICh4ID4+IChuIC0gcykpKSAmIDB4ZmYKCmRlZiByb3IzMih2YWx1ZSwgY291bnQpOgogICAgY291bnQgJT0gMzIKICAgIGxvdyA9IHZhbHVlIDw8ICgzMiAtIGNvdW50KQogICAgdmFsdWUgPj49IGNvdW50CiAgICB2YWx1ZSB8PSBsb3cKICAgIHZhbHVlICY9IDB4RkZGRkZGRkYKICAgIHJldHVybiB2YWx1ZQoKZGVmIHJvcih2YWx1ZSwgY291bnQpOgogICAgY291bnQgJT0gNjQKICAgIGxvdyA9IHZhbHVlIDw8ICg2NCAtIGNvdW50KQogICAgdmFsdWUgPj49IGNvdW50CiAgICB2YWx1ZSB8PSBsb3cKICAgIHZhbHVlICY9IDB4RkZGRkZGRkZGRkZGRkZGRgogICAgcmV0dXJuIHZhbHVlCgpkZWYgZ2V0X2tleV9oYXNoKGtleSwgcmFuZCk6CiAgICB0b19oYXNoID0gYnl0ZWFycmF5KDY4KQogICAgdG9faGFzaFs6MzJdID0ga2V5CiAgICB0b19oYXNoWzMyOjM2XSA9IHJhbmQudG9fYnl0ZXMoNCwgYnl0ZW9yZGVyPSdsaXR0bGUnKQogICAgdG9faGFzaFszNjpdID0ga2V5CgogICAgZDEgPSAocmFuZCA+PiAxNikgJiAweDAwMDAwMGZmCiAgICBkMiA9IChkMSA8PCAxMSkgfCAocmFuZCA+PiAyNCkKICAgIGQyIF49IChkMSA+PiA1KSBeIGQxCiAgICBkMiA9IH5kMiAmIDB4ZmZmZmZmZmYKCiAgICByZXR1cm4gU00zKHRvX2hhc2gpLmRpZ2VzdCgpLCBkMi50b19ieXRlcyg0LCAibGl0dGxlIikKCmRlZiBzcGxpdF9ibG9ja3MobWVzc2FnZSwgYmxvY2tfc2l6ZT0xNiwgcmVxdWlyZV9wYWRkaW5nPVRydWUpOgogICAgYXNzZXJ0IGxlbihtZXNzYWdlKSAlIGJsb2NrX3NpemUgPT0gMCBvciBub3QgcmVxdWlyZV9wYWRkaW5nCiAgICByZXR1cm4gW21lc3NhZ2VbaTppICsgMTZdIGZvciBpIGluIHJhbmdlKDAsIGxlbihtZXNzYWdlKSwgYmxvY2tfc2l6ZSldCgpkZWYgYWRkX3JvdW5kX2tleShzLCBrKToKICAgIGZvciBpIGluIHJhbmdlKDQpOgogICAgICAgIGZvciBqIGluIHJhbmdlKDQpOgogICAgICAgICAgICBzW2ldW2pdIF49IGtbaV1bal0KCmRlZiBhZGRfcm91bmRfa2V5X2NvbihzLCBrLCBjb24pOgogICAgZm9yIGkgaW4gcmFuZ2UoNCk6CiAgICAgICAgZm9yIGogaW4gcmFuZ2UoNCk6CiAgICAgICAgICAgIHNbaV1bal0gXj0ga1tpXVtjb25bal1dCgpkZWYgYnl0ZXMybWF0cml4KHRleHQpOgogICAgIiIiIENvbnZlcnRzIGEgMTYtYnl0ZSBhcnJheSBpbnRvIGEgNHg0IG1hdHJpeC4gICIiIgogICAgcmV0dXJuIFtsaXN0KHRleHRbaTppICsgNF0pIGZvciBpIGluIHJhbmdlKDAsIGxlbih0ZXh0KSwgNCldCgpkZWYgeG9yX2J5dGVzKGEsIGIpOgogICAgIiIiIFJldHVybnMgYSBuZXcgYnl0ZSBhcnJheSB3aXRoIHRoZSBlbGVtZW50cyB4b3InZWQuICIiIgogICAgcmV0dXJuIGJ5dGVhcnJheShpIF4gaiBmb3IgaSwgaiBpbiB6aXAoYSwgYikpCgpkZWYgbWF0cml4MmJ5dGVzKG1hdHJpeCk6CiAgICAiIiIgQ29udmVydHMgYSA0eDQgbWF0cml4IGludG8gYSAxNi1ieXRlIGFycmF5LiAgIiIiCiAgICByZXR1cm4gYnl0ZWFycmF5KHN1bShtYXRyaXgsIFtdKSkKCmRlZiBtaXhfc2luZ2xlX2NvbHVtbihhLCBpKToKICAgIHQgPSBhWzBdW2ldIF4gYVsxXVtpXSBeIGFbMl1baV0gXiBhWzNdW2ldCiAgICB1ID0gYVswXVtpXQogICAgYVswXVtpXSBePSB0IF4geHRpbWUoYVswXVtpXSBeIGFbMV1baV0pCiAgICBhWzFdW2ldIF49IHQgXiB4dGltZShhWzFdW2ldIF4gYVsyXVtpXSkKICAgIGFbMl1baV0gXj0gdCBeIHh0aW1lKGFbMl1baV0gXiBhWzNdW2ldKQogICAgYVszXVtpXSBePSB0IF4geHRpbWUoYVszXVtpXSBeIHUpCgpkZWYgbWl4X2NvbHVtbnMocyk6CiAgICBmb3IgaSBpbiByYW5nZSg0KToKICAgICAgICBtaXhfc2luZ2xlX2NvbHVtbihzLCBpKQoKZGVmIGludl9taXhfY29sdW1ucyhzKToKICAgIGZvciBpIGluIHJhbmdlKDAsIDQpOgogICAgICAgIGludl9taXhfc2luZ2xlX2NvbHVtbihzLCBpKQoKZGVmIGludl9taXhfc2luZ2xlX2NvbHVtbihhLCBpKToKICAgIHUgPSB4dGltZSh4dGltZShhWzBdW2ldIF4gYVsyXVtpXSkpCiAgICB2ID0geHRpbWUoeHRpbWUoYVsxXVtpXSBeIGFbM11baV0pKQogICAgYVswXVtpXSBePSB1CiAgICBhWzFdW2ldIF49IHYKICAgIGFbMl1baV0gXj0gdQogICAgYVszXVtpXSBePSB2CgogICAgbWl4X3NpbmdsZV9jb2x1bW4oYSwgaSkKCnNfYm94ID0gYicnLmpvaW4oWwogICAgYidceEZBXHg3RFx4MDhceDZCXHg5Q1x4NTlceEIzXHg0Qlx4MDRceDVGXHgzOVx4RDBceDM4XHg0QVx4OTFceDk5JywKICAgIGInXHgwMFx4NjdceEE2XHgyMFx4OUZceEY1XHg0RFx4ODJceDczXHgyNlx4RUVceERGXHgxOFx4NjZceDgzXHgzMycsCiAgICBiJ1x4ODBceDAzXHgxOVx4RkJceEQ5XHhGRVx4QUVceEFBXHhBOVx4QjBceDUyXHhDNlx4MEJceEYzXHg3OVx4MjUnLAogICAgYidceDRFXHg3OFx4QjRceDM2XHhBQ1x4NURceDFBXHgyN1x4OUVceDg4XHhEQlx4QkRceDNDXHg2M1x4RUNceDQ5JywKICAgIGInXHgxNVx4QzFceDMwXHgxRlx4RENceEI4XHg1Nlx4RDRceDZDXHhDRFx4Q0FceDA5XHg0M1x4QzhceDM1XHhBMycsCiAgICBiJ1x4RUZceDFFXHhGNFx4OTZceEQyXHhGQ1x4MEVceDcyXHg3Qlx4OTRceDg0XHhEMVx4RUFceDQ1XHg1QVx4NjInLAogICAgYidceDAyXHgzRlx4RDNceDEyXHg4MVx4MzRceDJCXHhERFx4N0VceEU2XHgyOFx4RjJceEE1XHg0Nlx4MTNceDAxJywKICAgIGInXHgzQlx4MjFceEY2XHg2MVx4MzdceDI5XHgyQVx4MERceEVEXHg4Q1x4QUZceEJGXHg5RFx4NUNceEJCXHgyNCcsCiAgICBiJ1x4NzZceDBGXHg3NVx4RTRceDUzXHg4OVx4RTFceDk4XHg4RFx4QjFceDlBXHg2NVx4NzBceDRGXHg1NFx4NEMnLAogICAgYidceDU4XHhBQlx4NkVceDZGXHg4Qlx4MjNceEM0XHgwN1x4MTFceDBDXHhCQVx4Q0ZceEEwXHhBNFx4OEVceEQ4JywKICAgIGInXHgwNVx4M0RceDE0XHhCMlx4REFceDc0XHhDM1x4RDdceEU3XHhCRVx4RDZceDdGXHhERVx4NDhceDE2XHgzRScsCiAgICBiJ1x4ODVceDkwXHhBMVx4NTVceEI3XHg3N1x4NDJceDIyXHhDOVx4ODZceDUwXHgyRVx4MTdceEY5XHg2NFx4MzEnLAogICAgYidceDJDXHg5Qlx4RjFceDZEXHgxQ1x4NDRceDY4XHhFM1x4RTlceEE4XHg5M1x4OTdceENCXHgzMlx4NTdceEVCJywKICAgIGInXHhFNVx4NzFceDZBXHhBRFx4QzBceENDXHhDN1x4QzVceEZEXHg2MFx4MURceEEyXHgyRFx4NDdceEE3XHhFMicsCiAgICBiJ1x4NTFceDY5XHg1RVx4N0FceENFXHgwQVx4NDFceEI2XHg5NVx4OEZceEY3XHhCOVx4ODdceEUwXHgzQVx4MDYnLAogICAgYidceDEwXHg4QVx4QjVceEY4XHg1Qlx4RDVceEYwXHhCQ1x4OTJceEZGXHg3Q1x4MkZceEMyXHhFOFx4MUJceDQwJywKICAgIGInXHhFQ1x4MUJceERBXHhCRFx4QkFceDk4XHg5MVx4MENceEIyXHgyQlx4ODNceDQxXHgzNFx4NjdceEZCXHgwQScsCiAgICBiJ1x4RDhceDc2XHhCNVx4NDZceDA1XHg1OVx4NjFceDIzXHg3NVx4OTBceDg3XHgyQVx4RTNceDUwXHgxNVx4NEMnLAogICAgYidceEFDXHhCMVx4NzlceEVCXHhBRVx4RTVceDk1XHg0N1x4MDRceDY4XHhGMFx4ODZceDNEXHg1MVx4OEJceDBGJywKICAgIGInXHhDQVx4OEVceEU0XHhCOVx4NEVceEYyXHgxMlx4ODJceEJDXHgwRVx4RDVceEY3XHhFRlx4MjhceDI1XHhDRicsCiAgICBiJ1x4NUJceDVEXHhFOVx4NkFceDU1XHgwMlx4RTFceDMzXHhCRVx4OTNceEU3XHhGNVx4QURceDlEXHgzRVx4MzknLAogICAgYidceDI0XHhBOFx4RTJceEZBXHgxN1x4NTdceEQwXHg3QVx4MERceDA4XHgzMFx4RDZceEI4XHhBM1x4OERceEZEJywKICAgIGInXHgwN1x4OUFceEM0XHgxRVx4NkVceDIyXHg2NFx4OTdceEQyXHgxRFx4QjBceEJGXHg0NVx4NjZceDNGXHg2QycsCiAgICBiJ1x4RERceERCXHgyN1x4ODBceEE3XHgxMVx4RENceEE2XHhDNVx4NTJceEY4XHhDMFx4QjZceEM4XHg1Q1x4MDAnLAogICAgYidceDczXHg2MFx4N0JceEEwXHgxOVx4MTNceEFBXHhDOVx4MzVceDQ4XHg0Qlx4RDNceEE0XHhDRFx4OUZceDk5JywKICAgIGInXHhGM1x4MTBceDQ0XHg0MFx4NTRceDdFXHgyOVx4RjRceDA2XHgxRlx4QTJceEFCXHhBMVx4MkZceDNDXHhGNicsCiAgICBiJ1x4QUZceDg1XHg2Mlx4MzZceDIxXHg3Rlx4NUVceERGXHgyMFx4MUFceEIzXHhCNFx4RTZceEZGXHg3Mlx4ODQnLAogICAgYidceDhGXHg2NVx4MjZceDk0XHg1QVx4NzdceEVBXHg0M1x4NzhceEM3XHg0QVx4Q0NceDJDXHgxNFx4NkJceEM2JywKICAgIGInXHhFOFx4NzRceDUzXHhGQ1x4RDRceDFDXHhDRVx4MzFceDcwXHgwM1x4MThceDhDXHg5Nlx4MzhceDMyXHg4OScsCiAgICBiJ1x4RjFceDNBXHg1Rlx4RDdceEY5XHhBOVx4NjlceEI3XHg2M1x4MzdceDU4XHhDMlx4M0JceEMzXHg3MVx4Q0InLAogICAgYidceDlFXHg5Mlx4MDFceDhBXHgwQlx4NERceDg4XHg5Qlx4QkJceDRGXHg2RFx4NkZceEUwXHhGRVx4QTVceDQ5JywKICAgIGInXHhERVx4NTZceDE2XHgwOVx4RURceDlDXHhDMVx4MkRceEVFXHg4MVx4N0RceEQ5XHg3Q1x4RDFceDJFXHg0MicsCiAgICBiJ1x4NUJceDREXHhDMVx4QTZceDVEXHhFQVx4NDRceEZEXHg0NVx4NEVceDFCXHhBMVx4M0ZceEQxXHg4OVx4RTEnLAogICAgYidceDdEXHgyRlx4QUFceERCXHhBQlx4QURceDU5XHhDQlx4QjFceENFXHg5QVx4MjhceEM5XHhFMFx4RjZceDcwJywKICAgIGInXHgzOVx4NEFceEQ3XHhGRlx4MzBceEY1XHhERFx4QkNceDU3XHgzQlx4MTFceDhEXHhCMlx4RUVceDAwXHhCNicsCiAgICBiJ1x4RTZceDFBXHg1QVx4N0NceEY5XHhERVx4QzRceENEXHgyRVx4ODBceEJCXHhCOVx4NENceEE1XHg5Rlx4ODQnLAogICAgYidceDA4XHhDNlx4NkZceDQyXHg2Q1x4RjBceDI3XHhFN1x4OEJceDNBXHg5Q1x4NTFceEZCXHg2N1x4MjFceDc1JywKICAgIGInXHg0MVx4MzFceEE3XHhDQVx4MjBceDQzXHgyQVx4QjdceEJGXHhEOVx4N0FceEYyXHhCNVx4RjhceDhDXHgyQycsCiAgICBiJ1x4MjNceDgzXHg0Rlx4OEZceDYwXHhBMFx4MDRceDEzXHgzN1x4MTRceEUzXHgwMVx4QzVceDYzXHg2Nlx4NUMnLAogICAgYidceDc0XHg4MVx4REZceDU4XHhCRFx4NjhceDkwXHgzRFx4RDJceEIzXHgzNFx4RjRceDE5XHg5M1x4MzJceDI5JywKICAgIGInXHhENlx4NDlceEFFXHgwRFx4NEJceEQ4XHgwN1x4OUVceEFDXHgxRVx4MkRceDBCXHg0MFx4QjhceDcyXHhCQScsCiAgICBiJ1x4NzZceDEwXHg3MVx4QThceEU0XHg1Nlx4MURceDQ4XHhGRVx4RTVceEMyXHg0N1x4OTFceERBXHg4N1x4MjYnLAogICAgYidceDlEXHgxRlx4ODhceDZCXHhDMFx4OThceEJFXHgyNVx4MDlceDk3XHgzM1x4QTNceDg1XHgxNlx4NUVceDdGJywKICAgIGInXHhEQ1x4NkVceDU0XHhFOVx4RjdceEE5XHhDOFx4RThceEMzXHg3N1x4RDBceDgyXHgyQlx4RUNceDAyXHg2MicsCiAgICBiJ1x4OEFceDkyXHgwRVx4M0VceEIwXHgwRlx4MDVceEYzXHhGMVx4OTZceDc4XHgzOFx4ODZceDM2XHgxOFx4M0MnLAogICAgYidceDI0XHhDRlx4MEFceEI0XHg1M1x4Q0NceDYxXHg2NVx4QTRceEM3XHg5NFx4RDVceDE1XHg3RVx4NkRceEVGJywKICAgIGInXHg3OVx4MjJceDM1XHgxMlx4NkFceDhFXHg1Mlx4MDZceDU1XHg3Qlx4NDZceDY0XHg1MFx4OTVceEUyXHgwQycsCiAgICBiJ1x4RURceEQzXHgxN1x4MDNceEEyXHg5Qlx4OTlceEVCXHgxQ1x4RkNceEFGXHhENFx4NzNceDY5XHhGQVx4NUYnLAogICAgYidceEY3XHgyQ1x4MUVceEJGXHhDOFx4RTFceEYzXHg5Rlx4NzZceDgwXHg3MVx4NDhceEFBXHg5NFx4QURceDY0JywKICAgIGInXHhGQlx4ODlceEM2XHg2MFx4QzNceDMyXHhCM1x4NERceEQyXHhFMFx4NDRceEREXHg1Rlx4QThceEIxXHhDNycsCiAgICBiJ1x4NjhceDIzXHgzNFx4QzlceDZEXHgxMlx4N0ZceEI3XHhFQlx4MTVceEJFXHhBOVx4RDFceDc4XHg5M1x4QTAnLAogICAgYidceDBDXHg5Mlx4QTRceEQ3XHg0N1x4RTNceDhBXHhDMlx4NzBceEFCXHgyNlx4NDFceDlBXHg3OVx4QTdceEQ4JywKICAgIGInXHgxNFx4ODVceDhGXHhDMFx4NkZceDU2XHhEMFx4OENceDExXHhCOVx4MkVceDNDXHhFMlx4OURceENGXHgwRScsCiAgICBiJ1x4REVceDAzXHg1RFx4NDZceDNFXHhDRFx4MzhceDQzXHgwRlx4MzNceDVBXHhEOVx4MUFceDY1XHg2Q1x4MjInLAogICAgYidceDNCXHhGQ1x4MzBceEE2XHg4OFx4RUFceDM3XHhBMlx4QjRceDhEXHg4RVx4NTFceDlDXHhENlx4NDBceEVFJywKICAgIGInXHhGOVx4RjhceDg0XHhGNFx4QUVceDk3XHhFOVx4Q0FceDBBXHg0NVx4NjdceDU3XHgwNFx4MkZceDgzXHg1QycsCiAgICBiJ1x4RDVceEM1XHhDNFx4ODJceEI2XHhBM1x4OTFceDk4XHgxRlx4NEFceEFDXHg5Nlx4ODFceDZFXHhDQlx4MUInLAogICAgYidceDA5XHgwOFx4QUZceDE4XHg5NVx4NDlceDdEXHg1NFx4RURceEZBXHgxNlx4MzFceDNBXHhEQVx4QjhceDY2JywKICAgIGInXHhGNVx4QTVceEYxXHhGRVx4MTBceDAxXHgwNlx4NzRceENDXHg2M1x4REZceDdDXHgyOFx4MjVceEY2XHhDRScsCiAgICBiJ1x4QjJceDRGXHg4Qlx4RTVceEJDXHg4N1x4NjlceEJCXHg4Nlx4MjFceDA3XHgwMFx4MzZceEU3XHgwQlx4NTAnLAogICAgYidceDU5XHg5Qlx4MUNceEU4XHg2Mlx4NThceDE5XHg2MVx4RjJceEJEXHgyN1x4NUVceEJBXHgxRFx4RTZceDk5JywKICAgIGInXHg0Mlx4M0RceDBEXHgyQVx4QjVceERDXHg1Qlx4MjlceEYwXHgyRFx4NENceDUzXHg3Qlx4NkFceDczXHg0RScsCiAgICBiJ1x4M0ZceDc1XHhGRlx4NEJceEExXHgzNVx4MTdceDU1XHg3Mlx4MzlceDIwXHhEM1x4QjBceEZEXHhFRlx4MDInLAogICAgYidceEVDXHg3N1x4N0VceEU0XHgyQlx4REJceDkwXHhDMVx4MDVceDlFXHg3QVx4RDRceDUyXHg2Qlx4MjRceDEzJ10pCgppbnZfc19ib3ggPSBieXRlYXJyYXkoMTAyNCkKCmNsYXNzIEFFU19WMygpOgogICAgcl9jb24gPSBbWzEsIDAsIDIsIDNdLCBbMSwgMywgMCwgMl0sIFswLCAxLCAzLCAyXSwgWzEsIDAsIDIsIDNdXQogICAgcl9jb24yID0gW1sxLCAwLCAyLCAzXSwgWzIsIDAsIDMsIDFdLCBbMCwgMSwgMywgMl0sIFsxLCAwLCAyLCAzXV0KICAgIHJfb3JkZXJzID0gW1swLCA5LCAxNCwgMTEsIDQsIDEzLCAyLCA3LCA4LCAxLCA2LCAxNSwgMTIsIDUsIDEwLCAzXSwKICAgICAgICAgICAgICAgIFswLCA5LCAxNCwgMTUsIDQsIDEzLCAyLCA3LCA4LCAxLCA2LCAzLCAxMiwgNSwgMTAsIDExXSwKICAgICAgICAgICAgICAgIFswLCA5LCAxNCwgNywgNCwgMTMsIDIsIDExLCA4LCAxLCA2LCAzLCAxMiwgNSwgMTAsIDE1XSwKICAgICAgICAgICAgICAgIFswLCA5LCAxNCwgMTEsIDQsIDEzLCAyLCA3LCA4LCAxLCA2LCAxNSwgMTIsIDUsIDEwLCAzXV0KCiAgICBkZWYgX19pbml0X18oc2VsZiwgYWVzX2tleSwga2hyb25vcyk6CiAgICAgICAgc2VsZi53b3JkX3NpemUgPSBraHJvbm9zICYgMyAgIyBraHJvbm9zIC0gKGtocm9ub3MgJiAtNCkKICAgICAgICBzZWxmLmFlc19rZXkgPSBhZXNfa2V5CgogICAgICAgIHNlbGYuc19ib3ggPSBzX2JveFtzZWxmLndvcmRfc2l6ZSA8PCA4Ol0KICAgICAgICBzZWxmLmludl9zX2JveCA9IGludl9zX2JveFtzZWxmLndvcmRfc2l6ZSA8PCA4Ol0KCiAgICAgICAgc2VsZi5tYXN0ZXJfa2V5ID0gc2VsZi5fZXhwYW5kX2tleSgpCiAgICAgICAgc2VsZi5fa2V5X21hdHJpY2VzID0gYnl0ZXMybWF0cml4KHNlbGYubWFzdGVyX2tleSkKICAgICAgICBzZWxmLmNvbiA9IHNlbGYucl9jb25bc2VsZi53b3JkX3NpemVdCiAgICAgICAgc2VsZi5jb24yID0gc2VsZi5yX2NvbjJbc2VsZi53b3JkX3NpemVdCgogICAgICAgIHNlbGYub3JkZXIgPSBzZWxmLnJfb3JkZXJzW3NlbGYud29yZF9zaXplXQoKICAgIGRlZiBfZXhwYW5kX2tleShzZWxmKToKICAgICAgICBpbml0X3ZhbHVlcyA9IFsweGNhMDI1ZGRjLCAweDgyM2RjNTQ2LCAweGM5NDIwNTgzLCAweGMyOTgyMjVmXQogICAgICAgIGluaXRfdmFsdWUgPSBpbml0X3ZhbHVlc1tzZWxmLndvcmRfc2l6ZV0KICAgICAgICBtayA9IGJ5dGVhcnJheShpbml0X3ZhbHVlLnRvX2J5dGVzKDQsICJsaXR0bGUiKSkKICAgICAgICBtayA9IG1rICogNAoKICAgICAgICBtayA9IHhvcl9ieXRlcyhtaywgc2VsZi5hZXNfa2V5KQogICAgICAgIG1rICs9IGJ5dGVhcnJheSgzMikKCiAgICAgICAgcm91bmRzID0gOAoKICAgICAgICBmb3IgaSBpbiByYW5nZSg0LCAxMik6CiAgICAgICAgICAgIGlkeCA9IDQgKiAoaSAtIDEpCiAgICAgICAgICAgIGswLCBrMSwgazIsIGszID0gbWtbaWR4XSwgbWtbaWR4ICsgMV0sIG1rW2lkeCArIDJdLCBta1tpZHggKyAzXQoKICAgICAgICAgICAgaWYgaSAmIDMgPT0gMDoKICAgICAgICAgICAgICAgIGswMCA9IChpbml0X3ZhbHVlID4+IChyb3VuZHMgJiAyNCkpIF4gc2VsZi5zX2JveFtrMV0KICAgICAgICAgICAgICAgIGsxID0gc2VsZi5zX2JveFtrMl0KICAgICAgICAgICAgICAgIGsyID0gc2VsZi5zX2JveFtrM10KICAgICAgICAgICAgICAgIGszID0gc2VsZi5zX2JveFtrMF0KICAgICAgICAgICAgICAgIGswID0gazAwICYgMHhmZgogICAgICAgICAgICByb3VuZHMgKz0gMgoKICAgICAgICAgICAgbWtbaWR4ICsgNF0gPSBrMCBeIG1rW2lkeCAtIDEyXQogICAgICAgICAgICBta1tpZHggKyA1XSA9IGsxIF4gbWtbaWR4IC0gMTFdCiAgICAgICAgICAgIG1rW2lkeCArIDZdID0gazIgXiBta1tpZHggLSAxMF0KICAgICAgICAgICAgbWtbaWR4ICsgN10gPSBrMyBeIG1rW2lkeCAtIDldCiAgICAgICAgcmV0dXJuIG1rCgogICAgQHN0YXRpY21ldGhvZAogICAgZGVmIHN1bV9kYXRhKGRhdGEpOgogICAgICAgIGtleSA9IGJ5dGVhcnJheSgzMikKICAgICAgICBmb3IgaSBpbiByYW5nZSgzMSk6CiAgICAgICAgICAgIGlkeCA9IGkgKiA4CiAgICAgICAgICAgIG4wID0gKGRhdGFbaWR4XSA+PiA0KSAmIDIKICAgICAgICAgICAgbjEgPSBuMCB8IGRhdGFbaWR4ICsgMV0gJiA2NAogICAgICAgICAgICBuMiA9IG4xIHwgKGRhdGFbaWR4ICsgMl0gPj4gMikgJiAxCiAgICAgICAgICAgIG4zID0gbjIgfCAoZGF0YVtpZHggKyAzXSA8PCAzKSAmIC0xMjgKICAgICAgICAgICAgbjQgPSBuMyB8IChkYXRhW2lkeCArIDRdID4+IDEpICYgNAogICAgICAgICAgICBuNSA9IG40IHwgKGRhdGFbaWR4ICsgNV0gPDwgMykgJiAxNgogICAgICAgICAgICBuNiA9IG41IHwgKGRhdGFbaWR4ICsgNl0gPDwgNSkgJiAzMgogICAgICAgICAgICBuNyA9IG42IHwgKGRhdGFbaWR4ICsgN10gPj4gNCkgJiA4CiAgICAgICAgICAgIGtleVtpXSA9IChuNyAmIDB4ZmYpCgogICAgICAgIGtleVszMV0gPSAxCiAgICAgICAgcmV0dXJuIGtleQoKICAgIEBzdGF0aWNtZXRob2QKICAgIGRlZiBtaXhfY29sdW1ucyhkYXRhLCBrZXkpOgogICAgICAgIGRhdGEgPSBieXRlYXJyYXkoZGF0YSkKCiAgICAgICAgZm9yIGkgaW4gcmFuZ2UoMzEpOgogICAgICAgICAgICBrayA9IGtleVtpXQogICAgICAgICAgICBpZHggPSBpICogOAogICAgICAgICAgICAjIHByaW50KGssIGRhdGFbaWR4ICsgMV0sIChkYXRhW2lkeCArIDFdICYgLTY1KSB8IChrICYgNjQpKQogICAgICAgICAgICBkYXRhW2lkeCArIDBdID0gKGRhdGFbaWR4ICsgMF0gJiAtMzMpIHwgKChrayA8PCA0KSAmIDB4ZmYgJiAzMikKICAgICAgICAgICAgZGF0YVtpZHggKyAxXSA9IChkYXRhW2lkeCArIDFdICYgLTY1KSB8IChrayAmIDY0KQogICAgICAgICAgICBkYXRhW2lkeCArIDJdID0gKGRhdGFbaWR4ICsgMl0gJiAtNSkgfCAoKGtrICogNCkgJiA0KQogICAgICAgICAgICBkYXRhW2lkeCArIDNdID0gKGRhdGFbaWR4ICsgM10gJiAtMTcpIHwgKChrayA+PiAzKSAmIDE2KQogICAgICAgICAgICBkYXRhW2lkeCArIDRdID0gKGRhdGFbaWR4ICsgNF0gJiAtOSkgfCAoKGtrICsga2spICYgOCkKICAgICAgICAgICAgZGF0YVtpZHggKyA1XSA9IChkYXRhW2lkeCArIDVdICYgLTMpIHwgKChrayA+PiAzKSAmIDIpCiAgICAgICAgICAgIGRhdGFbaWR4ICsgNl0gPSAoZGF0YVtpZHggKyA2XSAmIC0yKSB8ICgoa2sgPj4gNSkgJiAxKQogICAgICAgICAgICBkYXRhW2lkeCArIDddID0gKGRhdGFbaWR4ICsgN10gJiAxMjcpIHwgKChrayA8PCA0KSAmIDB4ZmYgJiAtMTI4KQoKICAgICAgICByZXR1cm4gZGF0YQoKICAgIGRlZiBlbmNyeXB0KHNlbGYsIGRhdGEsIGl2KToKICAgICAgICBwbGFpbnRleHQgPSBzZWxmLnN1bV9kYXRhKGRhdGEpCiAgICAgICAgYmxvY2tzID0gW10KICAgICAgICBwcmV2aW91cyA9IGl2CiAgICAgICAgZm9yIHBsYWludGV4dF9ibG9jayBpbiBzcGxpdF9ibG9ja3MocGxhaW50ZXh0KToKICAgICAgICAgICAgeCA9IHhvcl9ieXRlcyhwbGFpbnRleHRfYmxvY2ssIHByZXZpb3VzKQogICAgICAgICAgICBibG9jayA9IHNlbGYuZW5jcnlwdF9ibG9jayh4KQogICAgICAgICAgICBibG9ja3MuYXBwZW5kKGJsb2NrKQogICAgICAgICAgICBwcmV2aW91cyA9IGJsb2NrCgogICAgICAgIGtleSA9IGInJy5qb2luKGJsb2NrcykKICAgICAgICAjIGtleSA9IGJ5dGVzLmZyb21oZXgoJ2EyMmMyM2IwNWJiNGE4MzFkMzFiYmRiZDEzMjdjNWY4NDk5MWJjYTNlN2Q4ZGYyNGU1MmY1OGI3YWM2MWYyZTAnKQogICAgICAgICMgcHJpbnQoInNpZ25fa2V5Iiwga2V5LmhleCgpKQogICAgICAgIGRhdGEgPSBzZWxmLm1peF9jb2x1bW5zKGRhdGEsIGtleSkKICAgICAgICByZXR1cm4ga2V5Wy0xOl0gKyBkYXRhCgogICAgZGVmIGVuY3J5cHRfYmxvY2soc2VsZiwgcGxhaW50ZXh0KToKICAgICAgICAjIHByaW50KCJiMDAwIiwgcGxhaW50ZXh0LmhleCgpKQogICAgICAgIHBsYWluX3N0YXRlID0gYnl0ZXMybWF0cml4KHBsYWludGV4dCkKCiAgICAgICAgYWRkX3JvdW5kX2tleV9jb24ocGxhaW5fc3RhdGUsIHNlbGYuX2tleV9tYXRyaWNlc1swOjRdLCBzZWxmLmNvbjIpCiAgICAgICAgIyBwcmludCgiYjAwMSIsIG1hdHJpeDJieXRlcyhwbGFpbl9zdGF0ZSkuaGV4KCkpCgogICAgICAgIGZvciBpIGluIHJhbmdlKDEsIDMpOgogICAgICAgICAgICBzZWxmLnN1Yl9ieXRlcyhwbGFpbl9zdGF0ZSkKICAgICAgICAgICAgIyBwcmludCgiYjAwMyIsIG1hdHJpeDJieXRlcyhwbGFpbl9zdGF0ZSkuaGV4KCkpCiAgICAgICAgICAgIHNlbGYuc2hpZnRfcm93cyhwbGFpbl9zdGF0ZSkKICAgICAgICAgICAgIyBwcmludCgiYjAwNCIsIG1hdHJpeDJieXRlcyhwbGFpbl9zdGF0ZSkuaGV4KCkpCiAgICAgICAgICAgIGlmIGkgPT0gMToKICAgICAgICAgICAgICAgIHNlbGYuc2hpZnRfcm93c19jb24ocGxhaW5fc3RhdGUsIHNlbGYuY29uMikKICAgICAgICAgICAgICAgIG1peF9jb2x1bW5zKHBsYWluX3N0YXRlKQoKICAgICAgICAgICAgYWRkX3JvdW5kX2tleV9jb24ocGxhaW5fc3RhdGUsIHNlbGYuX2tleV9tYXRyaWNlc1tpICogNDpdLCBzZWxmLmNvbjIpCgogICAgICAgIGFkZF9yb3VuZF9rZXkocGxhaW5fc3RhdGUsIHNlbGYuX2tleV9tYXRyaWNlc1s0Ol0pCgogICAgICAgIHJldHVybiBtYXRyaXgyYnl0ZXMocGxhaW5fc3RhdGUpCgogICAgZGVmIGRlY3J5cHQoc2VsZiwgY2lwaGVydGV4dCwgaXYsIGRhdGEpOgogICAgICAgIGFzc2VydCBsZW4oaXYpID09IDE2CgogICAgICAgIGJsb2NrcyA9IFtdCiAgICAgICAgcHJldmlvdXMgPSBpdgoKICAgICAgICBmb3IgY2lwaGVydGV4dF9ibG9jayBpbiBzcGxpdF9ibG9ja3MoY2lwaGVydGV4dCk6CiAgICAgICAgICAgIGRjID0geG9yX2J5dGVzKHByZXZpb3VzLCBzZWxmLmRlY3J5cHRfYmxvY2soY2lwaGVydGV4dF9ibG9jaykpCiAgICAgICAgICAgICMgZGMgPSBtYXRyaXgyYnl0ZXMoZGNtKQogICAgICAgICAgICBibG9ja3MuYXBwZW5kKGRjKQogICAgICAgICAgICBwcmV2aW91cyA9IGNpcGhlcnRleHRfYmxvY2sKCiAgICAgICAga2V5ID0gYicnLmpvaW4oYmxvY2tzKQogICAgICAgICMgcHJpbnQoInNpZ25fa2V5Iiwga2V5LmhleCgpKQogICAgICAgIGRhdGEgPSBzZWxmLm1peF9jb2x1bW5zKGRhdGEsIGtleSkKICAgICAgICByZXR1cm4gZGF0YQoKICAgIGRlZiBkZWNyeXB0X2Jsb2NrKHNlbGYsIGNpcGhlcnRleHQpOgogICAgICAgIGFzc2VydCBsZW4oY2lwaGVydGV4dCkgPT0gMTYKICAgICAgICBjaXBoZXJfc3RhdGUgPSBieXRlczJtYXRyaXgoY2lwaGVydGV4dCkKCiAgICAgICAgIyBwcmludCgiYjAwMCIsIG1hdHJpeDJieXRlcyhjaXBoZXJfc3RhdGUpLmhleCgpKQogICAgICAgIGFkZF9yb3VuZF9rZXkoY2lwaGVyX3N0YXRlLCBzZWxmLl9rZXlfbWF0cmljZXNbNDpdKQogICAgICAgICMgICAgICAgICBwcmludCgiYjAwMSIsIG1hdHJpeDJieXRlcyhjaXBoZXJfc3RhdGUpLmhleCgpKQoKICAgICAgICBmb3IgaSBpbiByYW5nZSgyLCAwLCAtMSk6CiAgICAgICAgICAgIGFkZF9yb3VuZF9rZXlfY29uKGNpcGhlcl9zdGF0ZSwgc2VsZi5fa2V5X21hdHJpY2VzW2kgKiA0Ol0sIHNlbGYuY29uMikKICAgICAgICAgICAgIyAgICAgICAgICAgICBwcmludCgiYjAwMiIsIGksIG1hdHJpeDJieXRlcyhjaXBoZXJfc3RhdGUpLmhleCgpKQoKICAgICAgICAgICAgaWYgaSA9PSAxOgogICAgICAgICAgICAgICAgaW52X21peF9jb2x1bW5zKGNpcGhlcl9zdGF0ZSkKICAgICAgICAgICAgICAgIHNlbGYuc2hpZnRfcm93c19jb24oY2lwaGVyX3N0YXRlLCBzZWxmLmNvbikKCiAgICAgICAgICAgIHNlbGYuaW52X3NoaWZ0X3Jvd3MoY2lwaGVyX3N0YXRlKQogICAgICAgICAgICAjICAgICAgICAgICAgIHByaW50KCJiMDA0IiwgaSwgbWF0cml4MmJ5dGVzKGNpcGhlcl9zdGF0ZSkuaGV4KCkpCiAgICAgICAgICAgIHNlbGYuaW52X3N1Yl9ieXRlcyhjaXBoZXJfc3RhdGUpCiAgICAgICAgIyAgICAgICAgICAgICBwcmludCgiYjAwNSIsIGksIG1hdHJpeDJieXRlcyhjaXBoZXJfc3RhdGUpLmhleCgpKQoKICAgICAgICBhZGRfcm91bmRfa2V5X2NvbihjaXBoZXJfc3RhdGUsIHNlbGYuX2tleV9tYXRyaWNlc1swOjRdLCBzZWxmLmNvbjIpCgogICAgICAgIHJldHVybiBtYXRyaXgyYnl0ZXMoY2lwaGVyX3N0YXRlKQoKICAgIGRlZiBzaGlmdF9yb3dzX2NvbihzZWxmLCBzLCBjKToKICAgICAgICBmb3IgaSBpbiByYW5nZSg0KToKICAgICAgICAgICAgIyBjID0gc2VsZi5jb24KICAgICAgICAgICAgc1tpXVswXSwgc1tpXVsxXSwgc1tpXVsyXSwgc1tpXVszXSA9IHNbaV1bY1swXV0sIHNbaV1bY1sxXV0sIHNbaV1bY1syXV0sIHNbaV1bY1szXV0KCiAgICBkZWYgc2hpZnRfcm93cyhzZWxmLCBzKToKICAgICAgICBicyA9IG1hdHJpeDJieXRlcyhzKQogICAgICAgIGZvciBpIGluIHJhbmdlKDQpOgogICAgICAgICAgICBmb3IgaiBpbiByYW5nZSg0KToKICAgICAgICAgICAgICAgIHNbaV1bal0gPSBic1tzZWxmLm9yZGVyW2kgKiA0ICsgal1dCgogICAgZGVmIGludl9zaGlmdF9yb3dzKHNlbGYsIHMpOgogICAgICAgIG9yZGVyID0gYnl0ZWFycmF5KDE2KQogICAgICAgIGZvciBpIGluIHJhbmdlKDE2KToKICAgICAgICAgICAgb3JkZXJbc2VsZi5vcmRlcltpXV0gPSBpCgogICAgICAgIGJzID0gbWF0cml4MmJ5dGVzKHMpCiAgICAgICAgZm9yIGkgaW4gcmFuZ2UoNCk6CiAgICAgICAgICAgIGZvciBqIGluIHJhbmdlKDQpOgogICAgICAgICAgICAgICAgc1tpXVtqXSA9IGJzW29yZGVyW2kgKiA0ICsgal1dCgogICAgZGVmIHN1Yl9ieXRlcyhzZWxmLCBzKToKICAgICAgICBmb3IgaSBpbiByYW5nZSg0KToKICAgICAgICAgICAgZm9yIGogaW4gcmFuZ2UoNCk6CiAgICAgICAgICAgICAgICBzW2ldW2pdID0gc2VsZi5zX2JveFtzW2ldW2pdXQoKICAgICAgICBzWzBdLCBzWzFdLCBzWzJdLCBzWzNdID0gc1tzZWxmLmNvbjJbMF1dLCBzW3NlbGYuY29uMlsxXV0sIHNbc2VsZi5jb24yWzJdXSwgc1tzZWxmLmNvbjJbM11dCgogICAgZGVmIGludl9zdWJfYnl0ZXMoc2VsZiwgcyk6CiAgICAgICAgZm9yIGkgaW4gcmFuZ2UoNCk6CiAgICAgICAgICAgIGZvciBqIGluIHJhbmdlKDQpOgogICAgICAgICAgICAgICAgc1tpXVtqXSA9IHNlbGYuaW52X3NfYm94W3NbaV1bal1dCiAgICAgICAgc1swXSwgc1sxXSwgc1syXSwgc1szXSA9IHNbc2VsZi5jb25bMF1dLCBzW3NlbGYuY29uWzFdXSwgc1tzZWxmLmNvblsyXV0sIHNbc2VsZi5jb25bM11dCgpkZWYgbGVmdENpcmN1bGFyU2hpZnQoaywgYml0cyk6CiAgICBiaXRzID0gYml0cyAlIDMyCiAgICBrID0gayAlICgyICoqIDMyKQogICAgdXBwZXIgPSAoayA8PCBiaXRzKSAlICgyICoqIDMyKQogICAgcmVzdWx0ID0gdXBwZXIgfCAoayA+PiAoMzIgLSAoYml0cykpKQogICAgcmV0dXJuIChyZXN1bHQpCgpkZWYgYmxvY2tEaXZpZGUoYmxvY2ssIGNodW5rcyk6CiAgICByZXN1bHQgPSBbXQogICAgc2l6ZSA9IGxlbihibG9jaykgLy8gY2h1bmtzCiAgICBmb3IgaSBpbiByYW5nZSgwLCBjaHVua3MpOgogICAgICAgIHJlc3VsdC5hcHBlbmQoaW50LmZyb21fYnl0ZXMoYmxvY2tbaSAqIHNpemU6KGkgKyAxKSAqIHNpemVdLCBieXRlb3JkZXI9ImxpdHRsZSIpKQogICAgcmV0dXJuIChyZXN1bHQpCgpkZWYgRihYLCBZLCBaKToKICAgIHJldHVybiAoKFggJiBZKSB8ICgoflgpICYgWikpCgpkZWYgRyhYLCBZLCBaKToKICAgIHJldHVybiAoKFggJiBaKSB8IChZICYgKH5aKSkpCgpkZWYgSChYLCBZLCBaKToKICAgIHJldHVybiAoWCBeIFkgXiBaKQoKZGVmIEkoWCwgWSwgWik6CiAgICByZXR1cm4gKFkgXiAoWCB8ICh+WikpKSAmIDB4ZmZmZmZmZmYKCmRlZiBGRihhLCBiLCBjLCBkLCBNLCBzLCB0KToKICAgIHJlc3VsdCA9IGIgKyBsZWZ0Q2lyY3VsYXJTaGlmdCgoYSArIEYoYiwgYywgZCkgKyBNICsgdCksIHMpCgogICAgcmV0dXJuIChyZXN1bHQpCgpkZWYgR0coYSwgYiwgYywgZCwgTSwgcywgdCk6CiAgICByZXN1bHQgPSBiICsgbGVmdENpcmN1bGFyU2hpZnQoKGEgKyBHKGIsIGMsIGQpICsgTSArIHQpLCBzKQogICAgcmV0dXJuIChyZXN1bHQpCgpkZWYgSEgoYSwgYiwgYywgZCwgTSwgcywgdCk6CiAgICByZXN1bHQgPSBiICsgbGVmdENpcmN1bGFyU2hpZnQoKGEgKyBIKGIsIGMsIGQpICsgTSArIHQpLCBzKQogICAgcmV0dXJuIChyZXN1bHQpCgpkZWYgSUkoYSwgYiwgYywgZCwgTSwgcywgdCk6CiAgICByZXN1bHQgPSBiICsgbGVmdENpcmN1bGFyU2hpZnQoKGEgKyBJKGIsIGMsIGQpICsgTSArIHQpLCBzKQogICAgcmV0dXJuIChyZXN1bHQpCgpkZWYgc3VtX21kNShkYXRhKToKICAgIGNoZWNrX3N1bSA9IDB4MjAyMjA0MjAKICAgIGZvciBpIGluIHJhbmdlKDEyKToKICAgICAgICBpZiBpICUgMiA9PSAwOgogICAgICAgICAgICB0ZW1wID0gKGNoZWNrX3N1bSA+PiAzKSBeIGNoZWNrX3N1bQogICAgICAgICAgICBjaGVja19zdW0gPSBkYXRhW2ldIF4gKGNoZWNrX3N1bSA8PCA3KQogICAgICAgIGVsc2U6CiAgICAgICAgICAgIHRlbXAgPSAoY2hlY2tfc3VtID4+IDUpIF4gY2hlY2tfc3VtCiAgICAgICAgICAgIGNoZWNrX3N1bSA9IGRhdGFbaV0gfCAoY2hlY2tfc3VtIDw8IDExKQogICAgICAgICAgICBjaGVja19zdW0gXj0gMHhmZmZmZmZmZgoKICAgICAgICBjaGVja19zdW0gXj0gdGVtcAogICAgICAgIGNoZWNrX3N1bSAmPSAweGZmZmZmZmZmCgogICAgY2hlY2tfc3VtIHw9IDQKICAgIGNoZWNrX3N1bSBePSAweDEwMDAwMDAKICAgIHJldHVybiBjaGVja19zdW0KClNWMiA9IFsweGE3YWVmZTIwLCAweDcxNDlmMWQ2LCAweDQ3ZTRjYTA3LCAweGU5YjU4ZjY3LCAweDkzYjkyNGRlLCAweGM2MTRkMGY1LCAweDM4YWZlMGVmLCAweGIyYmJhZDczLAogICAgICAgMHhlMjQ0NDRjMywgMHg5ZDNhZWM5YiwgMHhkZjdiMzdlNCwgMHhkOGIxNmQ0MCwgMHhmOGFjMzFiOCwgMHg3NmI5YTkwYiwgMHgzMWQ4MzNlZSwgMHg5NTNmY2U2NCwKICAgICAgIDB4MzUzNTk1YTQsIDB4NDYwOWMxM2IsIDB4MzY5MjUwMDgsIDB4OGM2ZDA5MjUsIDB4NWRmNWMxNzcsIDB4MWNmYmY1MmIsIDB4OGE0ZmE3ZjAsIDB4MTE0Y2EzNWUsCiAgICAgICAweDgxOTNmOTg0LCAweDdhN2E4NzMzLCAweDMxNmFiNGQ1LCAweDNjMjBjZmM5LCAweGE2ZDg0NDUzLCAweDNhMTg1MDBjLCAweDc5OGVjNDdhLCAweDk3YTc2YjI4LAogICAgICAgMHg2NmM0ZmY5NiwgMHg1MTcxNjQ0MywgMHhkZDJmYzNiLCAweGI1Njk2ZGE3LCAweGJiZWIzYWM1LCAweDVjNTNkMjA0LCAweGQzMjYwOGNlLCAweDcyNzliOWVjLAogICAgICAgMHhmNDE4OGVjZiwgMHhmN2Q3OTNkYiwgMHgzMzJjYzQ5MSwgMHhhYjc2YWUxNSwgMHg5YmViZTcyNywgMHgxOGEwMTM4NCwgMHg1YmU5ZjhhNywgMHg1ZjkwYTc1NCwKICAgICAgIDB4MzliNjYzYzAsIDB4MzY2NzNjODMsIDB4N2M5MmY1MTQsIDB4OWQ3ZDk0ZDcsIDB4ZTJlOGQ5YWEsIDB4NWY3ZTllYTksIDB4N2FiZDQ1NTEsIDB4NTY5ZTA1ZGEsCiAgICAgICAweDQwYTI1NjMyLCAweDNkZjVhOWE1LCAweGJhYjM3ZDgwLCAweDQ1NDI4NmRjLCAweDNmNWQ0ZTc4LCAweDNkN2I3NWQsIDB4YjFmZTRhZjcsIDB4YTVhYjI2YTNdCgpkZWYgbWQ1c3VtX3YzKG1zZywgY291bnRfdjIsIG9yZGVycywgY291bnRfdjEsIG49MCk6CiAgICBjb3VudCA9IGNvdW50X3YyICYgMHhmZgoKICAgIHN2ID0gWzBdICogNjQKICAgIGZvciBpIGluIHJhbmdlKDY0KToKICAgICAgICBzdltpXSA9IHJvcjMyKFNWMltpXSwgY291bnRfdjEpCgogICAgc3RhcnQgPSBbCiAgICAgICAgcm9yMzIoMHg3OWUwZjJmYiwgY291bnQpLAogICAgICAgIHJvcjMyKDB4YzhiNTI1NzAsIGNvdW50KSwKICAgICAgICByb3IzMigweGViYzJmOGNkLCBjb3VudCksCiAgICAgICAgcm9yMzIoMHg3YzEwNGQ5MywgY291bnQpCiAgICBdCgogICAgY291bnQgPSAoY291bnRfdjIgKyA2KSAmIDB4ZmYKICAgIGVuZCA9IFsKICAgICAgICByb3IzMigweDE5YmU0ODY2LCBjb3VudCksCiAgICAgICAgcm9yMzIoMHhlODU5ODZiNCwgY291bnQpLAogICAgICAgIHJvcjMyKDB4ZTE5YjMyNmUsIGNvdW50KSwKICAgICAgICByb3IzMigweDcxZDFkN2Q0LCBjb3VudCkKICAgIF0KICAgIEEgPSBzdGFydFswXSAgIyAweDc5ZTBmMmZiCiAgICBCID0gc3RhcnRbMV0gICMgMHhjOGI1MjU3MAogICAgQyA9IHN0YXJ0WzJdICAjIDB4ZWJjMmY4Y2QKICAgIEQgPSBzdGFydFszXSAgIyAweDdjMTA0ZDkzCgogICAgYSA9IEEKICAgIGIgPSBCCiAgICBjID0gQwogICAgZCA9IEQKICAgIGJsb2NrID0gbXNnWzo2NF0KICAgIE0gPSBibG9ja0RpdmlkZShibG9jaywgMTYpCgogICAgb3JkZXIxID0gb3JkZXJzWzoxNl0KICAgIG9yZGVyMiA9IG9yZGVyc1sxNjozMl0KICAgIG9yZGVyMyA9IG9yZGVyc1szMjo0OF0KICAgIG9yZGVyNCA9IG9yZGVyc1s0ODpdCiAgICAjIFJvdW5kcwogICAgYSA9IEZGKGEsIGIsIGMsIGQsIE1bb3JkZXIxWzBdXSwgNywgc3ZbMF0pCiAgICBkID0gRkYoZCwgYSwgYiwgYywgTVtvcmRlcjFbMV1dLCAxMiwgc3ZbMV0pICAjIDB4YjZiYzZkZGIKICAgIGMgPSBGRihjLCBkLCBhLCBiLCBNW29yZGVyMVsyXV0sIDE3LCBzdlsyXSkgICMgMHhmODBiMTVkNAogICAgYiA9IEZGKGIsIGMsIGQsIGEsIE1bb3JkZXIxWzNdXSwgMjIsIHN2WzNdKQogICAgYSA9IEZGKGEsIGIsIGMsIGQsIE1bb3JkZXIxWzRdXSwgNywgc3ZbNF0pCiAgICBkID0gRkYoZCwgYSwgYiwgYywgTVtvcmRlcjFbNV1dLCAxMiwgc3ZbNV0pCiAgICBjID0gRkYoYywgZCwgYSwgYiwgTVtvcmRlcjFbNl1dLCAxNywgc3ZbNl0pCiAgICBiID0gRkYoYiwgYywgZCwgYSwgTVtvcmRlcjFbN11dLCAyMiwgc3ZbN10pCiAgICBhID0gRkYoYSwgYiwgYywgZCwgTVtvcmRlcjFbOF1dLCA3LCBzdls4XSkKICAgIGQgPSBGRihkLCBhLCBiLCBjLCBNW29yZGVyMVs5XV0sIDEyLCBzdls5XSkKICAgIGMgPSBGRihjLCBkLCBhLCBiLCBNW29yZGVyMVsxMF1dLCAxNywgc3ZbMTBdKQogICAgYiA9IEZGKGIsIGMsIGQsIGEsIE1bb3JkZXIxWzExXV0sIDIyLCBzdlsxMV0pCiAgICBhID0gRkYoYSwgYiwgYywgZCwgTVtvcmRlcjFbMTJdXSwgNywgc3ZbMTJdKQogICAgZCA9IEZGKGQsIGEsIGIsIGMsIE1bb3JkZXIxWzEzXV0sIDEyLCBzdlsxM10pCiAgICBjID0gRkYoYywgZCwgYSwgYiwgTVtvcmRlcjFbMTRdXSwgMTcsIHN2WzE0XSkKICAgIGIgPSBGRihiLCBjLCBkLCBhLCBNW29yZGVyMVsxNV1dLCAyMiwgc3ZbMTVdKQoKICAgIGEgPSBHRyhhLCBiLCBjLCBkLCBNW29yZGVyMlswXV0sIDUsIHN2WzE2XSkKICAgIGQgPSBHRyhkLCBhLCBiLCBjLCBNW29yZGVyMlsxXV0sIDksIHN2WzE3XSkKICAgIGMgPSBHRyhjLCBkLCBhLCBiLCBNW29yZGVyMlsyXV0sIDE0LCBzdlsxOF0pCiAgICBiID0gR0coYiwgYywgZCwgYSwgTVtvcmRlcjJbM11dLCAyMCwgc3ZbMTldKQogICAgYSA9IEdHKGEsIGIsIGMsIGQsIE1bb3JkZXIyWzRdXSwgNSwgc3ZbMjBdKQogICAgZCA9IEdHKGQsIGEsIGIsIGMsIE1bb3JkZXIyWzVdXSwgOSwgc3ZbMjFdKQogICAgYyA9IEdHKGMsIGQsIGEsIGIsIE1bb3JkZXIyWzZdXSwgMTQsIHN2WzIyXSkKICAgIGIgPSBHRyhiLCBjLCBkLCBhLCBNW29yZGVyMls3XV0sIDIwLCBzdlsyM10pCiAgICBhID0gR0coYSwgYiwgYywgZCwgTVtvcmRlcjJbOF1dLCA1LCBzdlsyNF0pCiAgICBkID0gR0coZCwgYSwgYiwgYywgTVtvcmRlcjJbOV1dLCA5LCBzdlsyNV0pCiAgICBjID0gR0coYywgZCwgYSwgYiwgTVtvcmRlcjJbMTBdXSwgMTQsIHN2WzI2XSkKICAgIGIgPSBHRyhiLCBjLCBkLCBhLCBNW29yZGVyMlsxMV1dLCAyMCwgc3ZbMjddKQogICAgYSA9IEdHKGEsIGIsIGMsIGQsIE1bb3JkZXIyWzEyXV0sIDUsIHN2WzI4XSkKICAgIGQgPSBHRyhkLCBhLCBiLCBjLCBNW29yZGVyMlsxM11dLCA5LCBzdlsyOV0pCiAgICBjID0gR0coYywgZCwgYSwgYiwgTVtvcmRlcjJbMTRdXSwgMTQsIHN2WzMwXSkKICAgIGIgPSBHRyhiLCBjLCBkLCBhLCBNW29yZGVyMlsxNV1dLCAyMCwgc3ZbMzFdKQoKICAgIGEgPSBISChhLCBiLCBjLCBkLCBNW29yZGVyM1swXV0sIDQsIHN2WzMyXSkKICAgIGQgPSBISChkLCBhLCBiLCBjLCBNW29yZGVyM1sxXV0sIDExLCBzdlszM10pCiAgICBjID0gSEgoYywgZCwgYSwgYiwgTVtvcmRlcjNbMl1dLCAxNiwgc3ZbMzRdKQogICAgYiA9IEhIKGIsIGMsIGQsIGEsIE1bb3JkZXIzWzNdXSwgMjMsIHN2WzM1XSkKICAgIGEgPSBISChhLCBiLCBjLCBkLCBNW29yZGVyM1s0XV0sIDQsIHN2WzM2XSkKICAgIGQgPSBISChkLCBhLCBiLCBjLCBNW29yZGVyM1s1XV0sIDExLCBzdlszN10pCiAgICBjID0gSEgoYywgZCwgYSwgYiwgTVtvcmRlcjNbNl1dLCAxNiwgc3ZbMzhdKQogICAgYiA9IEhIKGIsIGMsIGQsIGEsIE1bb3JkZXIzWzddXSwgMjMsIHN2WzM5XSkKICAgIGEgPSBISChhLCBiLCBjLCBkLCBNW29yZGVyM1s4XV0sIDQsIHN2WzQwXSkKICAgIGQgPSBISChkLCBhLCBiLCBjLCBNW29yZGVyM1s5XV0sIDExLCBzdls0MV0pCiAgICBjID0gSEgoYywgZCwgYSwgYiwgTVtvcmRlcjNbMTBdXSwgMTYsIHN2WzQyXSkKICAgIGIgPSBISChiLCBjLCBkLCBhLCBNW29yZGVyM1sxMV1dLCAyMywgc3ZbNDNdKQogICAgYSA9IEhIKGEsIGIsIGMsIGQsIE1bb3JkZXIzWzEyXV0sIDQsIHN2WzQ0XSkKICAgIGQgPSBISChkLCBhLCBiLCBjLCBNW29yZGVyM1sxM11dLCAxMSwgc3ZbNDVdKQogICAgYyA9IEhIKGMsIGQsIGEsIGIsIE1bb3JkZXIzWzE0XV0sIDE2LCBzdls0Nl0pCiAgICBiID0gSEgoYiwgYywgZCwgYSwgTVtvcmRlcjNbMTVdXSwgMjMsIHN2WzQ3XSkKCiAgICBhID0gSUkoYSwgYiwgYywgZCwgTVtvcmRlcjRbMF1dLCA2LCBzdls0OF0pCiAgICBkID0gSUkoZCwgYSwgYiwgYywgTVtvcmRlcjRbMV1dLCAxMCwgc3ZbNDldKQogICAgYyA9IElJKGMsIGQsIGEsIGIsIE1bb3JkZXI0WzJdXSwgMTUsIHN2WzUwXSkKICAgIGIgPSBJSShiLCBjLCBkLCBhLCBNW29yZGVyNFszXV0sIDIxLCBzdls1MV0pCiAgICBhID0gSUkoYSwgYiwgYywgZCwgTVtvcmRlcjRbNF1dLCA2LCBzdls1Ml0pCiAgICBkID0gSUkoZCwgYSwgYiwgYywgTVtvcmRlcjRbNV1dLCAxMCwgc3ZbNTNdKQogICAgYyA9IElJKGMsIGQsIGEsIGIsIE1bb3JkZXI0WzZdXSwgMTUsIHN2WzU0XSkKICAgIGIgPSBJSShiLCBjLCBkLCBhLCBNW29yZGVyNFs3XV0sIDIxLCBzdls1NV0pCiAgICBhID0gSUkoYSwgYiwgYywgZCwgTVtvcmRlcjRbOF1dLCA2LCBzdls1Nl0pCiAgICBkID0gSUkoZCwgYSwgYiwgYywgTVtvcmRlcjRbOV1dLCAxMCwgc3ZbNTddKQogICAgYyA9IElJKGMsIGQsIGEsIGIsIE1bb3JkZXI0WzEwXV0sIDE1LCBzdls1OF0pCiAgICBiID0gSUkoYiwgYywgZCwgYSwgTVtvcmRlcjRbMTFdXSwgMjEsIHN2WzU5XSkKICAgIGEgPSBJSShhLCBiLCBjLCBkLCBNW29yZGVyNFsxMl1dLCA2LCBzdls2MF0pCiAgICBkID0gSUkoZCwgYSwgYiwgYywgTVtvcmRlcjRbMTNdXSwgMTAsIHN2WzYxXSkKICAgIGMgPSBJSShjLCBkLCBhLCBiLCBNW29yZGVyNFsxNF1dLCAxNSwgc3ZbNjJdKQogICAgYiA9IElJKGIsIGMsIGQsIGEsIE1bb3JkZXI0WzE1XV0sIDIxLCBzdls2M10pCgogICAgQSA9IChBICsgYSkgJSAoMiAqKiAzMikgXiBlbmRbMF0KICAgIEIgPSAoQiArIGIpICUgKDIgKiogMzIpIF4gZW5kWzFdCiAgICBDID0gKEMgKyBjKSAlICgyICoqIDMyKSBeIGVuZFsyXQogICAgRCA9IChEICsgZCkgJSAoMiAqKiAzMikgXiBlbmRbM10KCiAgICByZXN1bHQgPSBieXRlYXJyYXkoCiAgICAgICAgQS50b19ieXRlcyg0LCAibGl0dGxlIikgKyBCLnRvX2J5dGVzKDQsICJsaXR0bGUiKSArIEMudG9fYnl0ZXMoNCwgImxpdHRsZSIpICsgRC50b19ieXRlcyg0LCAibGl0dGxlIikpCgogICAgcmVzdWx0ICs9IHN1bV9tZDUocmVzdWx0KS50b19ieXRlcyg0LCAibGl0dGxlIikKICAgIHJldHVybiByZXN1bHQKCmRlZiBieG9yKGIxLCBiMik6CiAgICBiMyA9IGJ5dGVhcnJheShsZW4oYjEpKQogICAgZm9yIGkgaW4gcmFuZ2UobGVuKGIxKSk6CiAgICAgICAgYjNbaV0gPSBiMVtpXSBeIGIyW2ldCiAgICByZXR1cm4gYjMKCmRlZiBnZXRfaXYoaXYsIGRhdGEpOgogICAgZm9yIGkgaW4gcmFuZ2UobGVuKGRhdGEpKToKICAgICAgICBpZiBpICYgMSA9PSAwOgogICAgICAgICAgICBpdiA9IChpdiA+PiA0KSBeIGl2IF4gKGl2IDw8IDYpIF4gZGF0YVtpXQogICAgICAgIGVsc2U6CiAgICAgICAgICAgIGl2ID0gfigoaXYgPj4gNykgXiBpdiBeIChkYXRhW2ldIHwgaXYgPDwgMTIpKQogICAgICAgIGl2ID0gaXYgJiAweGZmZmZmZmZmCiAgICByZXR1cm4gaXYKCmRlZiBoYXNoX2YxMyhxdWVyeV9zbTMsIGJvZHlfbWQ1X2J5dGVzLCB0c19ieXRlcywga2hyb25vcyk6CiAgICBpdiA9IGdldF9pdigweDIwMjMwOTI4LCBxdWVyeV9zbTMpCiAgICBpdiA9IGdldF9pdihpdiwgYm9keV9tZDVfYnl0ZXMpCiAgICBpdiA9IGdldF9pdihpdiwgdHNfYnl0ZXMpCgogICAgaXZfdjAgPSAoKGl2ICYgMTUpICogMTcxKSA+PiA5CiAgICBicmFuY2ggPSAoaXYgJiAxNSkgLSAoKGl2X3YwICogMykgJiAweGZmKQogICAgaWYgYnJhbmNoID09IDA6CiAgICAgICAgcmV0dXJuIGJyYW5jaF8wKGl2X3YwLCBraHJvbm9zLCBxdWVyeV9zbTMsIGJvZHlfbWQ1X2J5dGVzLCB0c19ieXRlcykKICAgIGVsaWYgYnJhbmNoID09IDE6CiAgICAgICAgcmV0dXJuIGJyYW5jaF8xKGl2X3YwLCBraHJvbm9zLCBxdWVyeV9zbTMsIGJvZHlfbWQ1X2J5dGVzLCB0c19ieXRlcykKICAgIGVsaWYgYnJhbmNoID09IDI6CiAgICAgICAgcmV0dXJuIGJyYW5jaF8yKGl2LCBraHJvbm9zLCBxdWVyeV9zbTMsIGJvZHlfbWQ1X2J5dGVzLCB0c19ieXRlcykKICAgIGVsc2U6CiAgICAgICAgcmFpc2UgRXhjZXB0aW9uKCJubyBicmFuY2g6ICIgKyBzdHIoYnJhbmNoKSkKCmRlZiBicmFuY2hfMChpdl92MCwga2hyb25vcywgcXVlcnlfc20zLCBib2R5X21kNV9ieXRlcywgdHNfYnl0ZXMpOgogICAgdHQwMSA9IFsweGM0YTc4NTgwLCAweGIzYzBmZDM5LCAweGM1OGM1Njg2LCAweGM5YWEzYmE3LCAweGY1YTdhZGYyLCAweDk2M2MyZWQxXQogICAgaXZfdjEgPSB0dDAxW2l2X3YwXQoKICAgIGNvdW50X3YxID0gKGl2X3YxICsga2hyb25vcyArIDEpICYgMHhmZgogICAgY291bnRfdjIgPSAoaXZfdjEgKyBraHJvbm9zKSAmIDB4ZmZmZmZmZmYKCiAgICB0dDAyID0gWzB4ZWJiNjRmYWYsIDB4N2FhZGNjMiwgMHhjZjMxODdiZiwgMHhlMDExMzhmZiwgMHg2ZDBiZmNmZiwgMHg1YTMwYTNiZSwgMHhiNDFhZDYzOCwgMHgzNDE4MGViOCwgMHhmMjMzZWI2ZiwKICAgICAgICAgICAgMHhiMWE1ODRjYywgMHhjY2MzMGRjNywgMHg0N2QxZGI1MSwgMHhkNTU2NTNkZSwgMHg3MGE4NGZhMSwgMHg1NzQ3M2MxMiwgMHhmNzZmMDI4OCwgMHgyYzA3N2YwYSwgMHhkYTBkY2FkMCwKICAgICAgICAgICAgMHhmYmI4NmY2YywgMHhmZGM0Y2YwMCwgMHg2ODhhMDIwZCwgMHhlNjc2YzZhNiwgMHg4Y2Q2MzM4YiwgMHgxYTNjOGQwZSwgMHhjY2U4YjA2YiwgMHg2YWQwZWQwYiwgMHhhMDUyMjcxNywKICAgICAgICAgICAgMHhkYzcxYWM4MywgMHgyMjg1ZGI3MSwgMHhkNWI0ZGRhNiwgMHg3MzZmODY1MCwgMHg2NTYwMzA2YywgMHg2MTdjZTJhNiwgMHhlNDIzNDE3ZSwgMHhhNDBlMTQzLCAweDU0NGU0MDMyLAogICAgICAgICAgICAweDg4ZGZmYjJhLCAweDcxNmMxYWUwLCAweDRjNDY3YTg4LCAweDViMjNiYjMsIDB4ZTFkMGI4NjYsIDB4YmFhM2RjYjgsIDB4YWUzMzc0ZDMsIDB4YzMzODFhNTAsIDB4MTcwMmY3NWIsCiAgICAgICAgICAgIDB4ZmU2ZGEzNjgsIDB4ZjBiNGNmNDgsIDB4NGUwZmZiYjgsIDB4NzJhYWQxMGQsIDB4MjZjNTNhM2QsIDB4ZjJiY2UwZjYsIDB4YjQ1NTc1ODEsIDB4NGEyNTdmZGQsIDB4OGMzMTgyYTIsCiAgICAgICAgICAgIDB4YWIwYjNiODYsIDB4M2Q1ZGZiMTQsIDB4NGYxMDM2MzQsIDB4ZDM3YjUyZDcsIDB4NDQ0ZWZmMTYsIDB4ZWIwYTMzZDEsIDB4NmNhODZmNmUsIDB4Mjg0YmE3LCAweDgzODdjZmEsCiAgICAgICAgICAgIDB4NWZiMzc1ODZdCgogICAgdHQwMyA9IFswXSAqIDY0CiAgICBmb3IgaSBpbiByYW5nZSgwLCA2NCk6CiAgICAgICAgdHQwM1tpXSA9IHJvcjMyKHR0MDJbaV0sIGNvdW50X3YxKSAmIDB4ZmZmZmZmZmYKCiAgICBuMCA9IChjb3VudF92MiArIDIpICYgNwoKICAgIHBhZCA9IGJ5dGVhcnJheSg0KQogICAgc2VlZCA9IGJ5dGVzKFsweGZhLCAweDQ1LCAweDYxLCAweGQ3XSkKICAgIGZvciBpIGluIHJhbmdlKDQpOgogICAgICAgIHYgPSBpbnQuZnJvbV9ieXRlcyhieXRlcyhbc2VlZFtpXSwgc2VlZFtpXV0pLCAnbGl0dGxlJykKICAgICAgICB2ID0gdiA+PiBuMAogICAgICAgIHBhZFtpXSA9IHYgJiAweGZmCgogICAgY291bnRfdjIgPSBjb3VudF92MiAmIDB4ZmYKICAgIGluaXRfdmFsdWUgPSBbCiAgICAgICAgcm9yMzIoMHg3YWJhNGZjOCwgY291bnRfdjIpLCByb3IzMigweDY3MTY2NTA3LCBjb3VudF92MiksCiAgICAgICAgcm9yMzIoMHg2NDAzZmEwMCwgY291bnRfdjIpLCByb3IzMigweDM0MGY1MTJmLCBjb3VudF92MiksCiAgICAgICAgcm9yMzIoOTg0MzA0OTEyLCBjb3VudF92MiksIHJvcjMyKDMwMDUwNDc4NjYsIGNvdW50X3YyKSwKICAgICAgICByb3IzMigyODc0MTI1MjkzLCBjb3VudF92MiksIHJvcjMyKDIxNTI0MTMyNjQsIGNvdW50X3YyKQogICAgXQoKICAgIGRhdGEgPSBxdWVyeV9zbTMgKyBib2R5X21kNV9ieXRlcyArIHRzX2J5dGVzICsgcGFkICsgYnl0ZXMuZnJvbWhleCgnIDAwIDAwIDAwIDAwIDAwIDAwIDAxIGEwJykKICAgIGRpID0gWzBdICogKGxlbihkYXRhKSAvLyA0KQogICAgZm9yIGkgaW4gcmFuZ2UobGVuKGRhdGEpIC8vIDQpOgogICAgICAgIGRpW2ldID0gaW50LmZyb21fYnl0ZXMoZGF0YVtpICogNDppICogNCArIDRdLCAiYmlnIikKCiAgICBkaTAgPSBkaVswXQogICAgZm9yIGkgaW4gcmFuZ2UoMTEyKToKICAgICAgICBkaTEsIGRpMTQgPSBkaVtpICsgMV0sIGRpW2kgKyAxNF0KICAgICAgICByX2RpMSA9IHJvbChkaTEsIDE0KSBeIHJvbChkaTEsIDI1KSBeIChkaTEgPj4gMykKICAgICAgICByX2RpMiA9IHJvbChkaTE0LCAxMykgXiByb2woZGkxNCwgMTUpIF4gKGRpMTQgPj4gMTApCiAgICAgICAgZGkwID0gZGkwICsgZGlbaSArIDldICsgcl9kaTEgKyByX2RpMgogICAgICAgIGRpLmFwcGVuZChkaTAgJiAweGZmZmZmZmZmKQogICAgICAgIGRpMCA9IGRpMQoKICAgIGlmIGl2X3YwID09IDU6CiAgICAgICAgdl9qID0gYnJhbmNoMF94b3IoaW5pdF92YWx1ZSwgaXZfdjEsIGRpLCB0dDAzLCAxMDAsIDIsIDAsIDMsIDUsIDQsIDYsIDcsIDIsIDEsIDUpCiAgICBlbGlmIGl2X3YwID09IDQ6CiAgICAgICAgdl9qID0gYnJhbmNoMF94b3IoaW5pdF92YWx1ZSwgaXZfdjEsIGRpLCB0dDAzLCA5NiwgMCwgNSwgNiwgNywgMywgMSwgMiwgNSwgNCwgNCkKICAgIGVsaWYgaXZfdjAgPT0gMzoKICAgICAgICB2X2ogPSBicmFuY2gwX3hvcihpbml0X3ZhbHVlLCBpdl92MSwgZGksIHR0MDMsIDk5LCAzLCA2LCAyLCA0LCA1LCAxLCAwLCAwLCA3LCA2KQogICAgZWxpZiBpdl92MCA9PSAyOgogICAgICAgIHZfaiA9IGJyYW5jaDBfeG9yKGluaXRfdmFsdWUsIGl2X3YxLCBkaSwgdHQwMywgOTYsIDcsIDYsIDIsIDEsIDQsIDAsIDUsIDQsIDMsIDUpCiAgICBlbGlmIGl2X3YwID09IDE6CiAgICAgICAgdl9qID0gYnJhbmNoMF94b3IoaW5pdF92YWx1ZSwgaXZfdjEsIGRpLCB0dDAzLCA5NiwgMCwgNiwgNywgNSwgMywgMiwgMSwgNSwgNCwgNCkKICAgIGVsaWYgaXZfdjAgPT0gMDoKICAgICAgICB2X2ogPSBicmFuY2gwX3hvcihpbml0X3ZhbHVlLCBpdl92MSwgZGksIHR0MDMsIDEwMSwgNSwgNywgNiwgMywgMiwgMSwgMCwgNSwgNCwgMykKCiAgICByZXQgPSBieXRlYXJyYXkoMzIpCiAgICBmb3IgaSBpbiByYW5nZSg4KToKICAgICAgICByZXRbaSAqIDQ6aSAqIDQgKyA0XSA9ICgodl9qW2ldICsgaW5pdF92YWx1ZVtpXSkgJiAweGZmZmZmZmZmKS50b19ieXRlcyg0LCAnYmlnJykKCiAgICByZXQgPSBieG9yKHJldFs6MTZdLCByZXRbMTY6XSkKICAgIHN1bSA9IHN1bV9tZDUocmV0KQogICAgcmV0ICs9IHN1bS50b19ieXRlcyg0LCAibGl0dGxlIikKICAgIHJldHVybiByZXQKCmRlZiBzd2FwX3YwKHNyYywgc3JjX3hvciwgdHQyLCB0YWJsZV9mLCBvcmRlcjEsIHR5cD1Ob25lKToKICAgIGRhMCA9IFswXSAqIDgKICAgIGhhMCA9IHNyY194b3JbOl0KICAgIGZvciBpIGluIHJhbmdlKDgpOgogICAgICAgIGRhMFtpXSA9IHNyY1tvcmRlcjFbaV1dIF4gc3JjX3hvcltpXQoKICAgIGZvciByb3VuZCBpbiByYW5nZSgxMCk6CiAgICAgICAgcnJfMCA9IHIwMChoYTBbMF0sIGhhMFsxXSwgaGEwWzJdLCBoYTBbM10sIGhhMFs0XSwgaGEwWzVdLCBoYTBbNl0sIGhhMFs3XSwgMCwgdGFibGVfZikKICAgICAgICBycl8xID0gcjAwKGhhMFsxXSwgaGEwWzJdLCBoYTBbM10sIGhhMFs0XSwgaGEwWzVdLCBoYTBbNl0sIGhhMFs3XSwgaGEwWzBdLCAwLCB0YWJsZV9mKQogICAgICAgIHJyXzIgPSByMDAoaGEwWzJdLCBoYTBbM10sIGhhMFs0XSwgaGEwWzVdLCBoYTBbNl0sIGhhMFs3XSwgaGEwWzBdLCBoYTBbMV0sIDAsIHRhYmxlX2YpCiAgICAgICAgcnJfMyA9IHIwMChoYTBbM10sIGhhMFs0XSwgaGEwWzVdLCBoYTBbNl0sIGhhMFs3XSwgaGEwWzBdLCBoYTBbMV0sIGhhMFsyXSwgMCwgdGFibGVfZikKICAgICAgICBycl80ID0gcjAwKGhhMFs0XSwgaGEwWzVdLCBoYTBbNl0sIGhhMFs3XSwgaGEwWzBdLCBoYTBbMV0sIGhhMFsyXSwgaGEwWzNdLCAwLCB0YWJsZV9mKQogICAgICAgIHJyXzUgPSByMDAoaGEwWzVdLCBoYTBbNl0sIGhhMFs3XSwgaGEwWzBdLCBoYTBbMV0sIGhhMFsyXSwgaGEwWzNdLCBoYTBbNF0sIDAsIHRhYmxlX2YpCiAgICAgICAgcnJfNiA9IHIwMChoYTBbNl0sIGhhMFs3XSwgaGEwWzBdLCBoYTBbMV0sIGhhMFsyXSwgaGEwWzNdLCBoYTBbNF0sIGhhMFs1XSwgMCwgdGFibGVfZikKICAgICAgICBycl83ID0gcjAwKGhhMFs3XSwgaGEwWzBdLCBoYTBbMV0sIGhhMFsyXSwgaGEwWzNdLCBoYTBbNF0sIGhhMFs1XSwgaGEwWzZdLCAwLCB0YWJsZV9mKQogICAgICAgIHJyXzcgPSBycl83IF4gdHQyW3JvdW5kICsgMV0KCiAgICAgICAgZDAsIGQxLCBkMiwgZDMsIGQ0LCBkNSwgZDYsIGQ3ID0gZGEwWzBdLCBkYTBbMV0sIGRhMFsyXSwgZGEwWzNdLCBkYTBbNF0sIGRhMFs1XSwgZGEwWzZdLCBkYTBbN10KCiAgICAgICAgZGEwWzBdID0gcjAwKGQwLCBkMSwgZDIsIGQzLCBkNCwgZDUsIGQ2LCBkNywgcnJfMCwgdGFibGVfZikKICAgICAgICBkYTBbMV0gPSByMDAoZDEsIGQyLCBkMywgZDQsIGQ1LCBkNiwgZDcsIGQwLCBycl8xLCB0YWJsZV9mKSAgIyAweGQwYTQ4OWIzNWJhNjc4ZTgKICAgICAgICBkYTBbMl0gPSByMDAoZDIsIGQzLCBkNCwgZDUsIGQ2LCBkNywgZDAsIGQxLCBycl8yLCB0YWJsZV9mKSAgIyAweDNiZTViN2Y5Y2ZkNDQ2NTQKICAgICAgICBkYTBbM10gPSByMDAoZDMsIGQ0LCBkNSwgZDYsIGQ3LCBkMCwgZDEsIGQyLCBycl8zLCB0YWJsZV9mKQogICAgICAgIGRhMFs0XSA9IHIwMChkNCwgZDUsIGQ2LCBkNywgZDAsIGQxLCBkMiwgZDMsIHJyXzQsIHRhYmxlX2YpCiAgICAgICAgZGEwWzVdID0gcjAwKGQ1LCBkNiwgZDcsIGQwLCBkMSwgZDIsIGQzLCBkNCwgcnJfNSwgdGFibGVfZikKICAgICAgICBkYTBbNl0gPSByMDAoZDYsIGQ3LCBkMCwgZDEsIGQyLCBkMywgZDQsIGQ1LCBycl82LCB0YWJsZV9mKQogICAgICAgIGRhMFs3XSA9IHIwMChkNywgZDAsIGQxLCBkMiwgZDMsIGQ0LCBkNSwgZDYsIHJyXzcsIHRhYmxlX2YpCgogICAgICAgIGhhMFswXSwgaGEwWzFdLCBoYTBbMl0sIGhhMFszXSwgaGEwWzRdLCBoYTBbNV0sIGhhMFs2XSwgaGEwWzddID0gcnJfMCwgcnJfMSwgcnJfMiwgcnJfMywgcnJfNCwgcnJfNSwgcnJfNiwgcnJfNwoKICAgIGlmIHR5cCBpcyBOb25lOgogICAgICAgIHNyY1swXSA9IGRhMFswXSBeIHNyY194b3JbMF0gXiBzcmNbMF0KICAgICAgICBzcmNbMV0gPSBkYTBbN10gXiBzcmNfeG9yWzFdIF4gc3JjWzFdCiAgICAgICAgc3JjWzJdID0gZGEwWzZdIF4gc3JjX3hvclsyXSBeIHNyY1syXQogICAgICAgIHNyY1szXSA9IGRhMFs1XSBeIHNyY194b3JbM10gXiBzcmNbM10KICAgICAgICBzcmNbNF0gPSBkYTBbNF0gXiBzcmNfeG9yWzRdIF4gc3JjWzRdCiAgICAgICAgc3JjWzVdID0gZGEwWzNdIF4gc3JjX3hvcls1XSBeIHNyY1s1XQogICAgICAgIHNyY1s2XSA9IGRhMFsyXSBeIHNyY194b3JbNl0gXiBzcmNbNl0KICAgICAgICBzcmNbN10gPSBkYTBbMV0gXiBzcmNfeG9yWzddIF4gc3JjWzddCiAgICBlbHNlOgogICAgICAgIHNyY1swXSA9IGRhMFs3XSBeIHR5cFsxXQogICAgICAgIHNyY1sxXSA9IGRhMFs2XSBeIHR5cFsyXQogICAgICAgIHNyY1syXSA9IGRhMFs1XSBeIHR5cFszXQogICAgICAgIHNyY1szXSA9IGRhMFs0XSBeIHR5cFs0XQogICAgICAgIHNyY1s0XSA9IGRhMFszXSBeIHR5cFs1XQogICAgICAgIHNyY1s1XSA9IGRhMFsyXSBeIHR5cFs2XQogICAgICAgIHNyY1s2XSA9IGRhMFsxXSBeIHR5cFs3XSBeIHNyY1s3XQogICAgICAgIHNyY1s3XSA9IGRhMFswXSBeIHR5cFswXQogICAgcmV0dXJuIHNyYwoKZGVmIGJyYW5jaF8xKGl2X3YwLCBraHJvbm9zLCBxdWVyeV9zbTMsIGJvZHlfbWQ1X2J5dGVzLCB0c19ieXRlcyk6CiAgICB0dDEgPSBbMHg4MDhhOWM3OSwgMHhmMDc5ODA3ZSwgMHhiYWRmNzljNSwgMHhhNzg1ZDNmZiwgMHg4MmQ4NDM4Y10KICAgIGl2X3YxID0gdHQxW2l2X3YwXQoKICAgIGNfdjEgPSAoaXZfdjEgKyBraHJvbm9zKSAmIDB4ZmYKICAgIGNfdjEgPSByb3Ioa2hyb25vcywgY192MSkKCiAgICBvcmRlcnMgPSBieXRlcy5mcm9taGV4KCcnJzA1IDA3IDAxIDAyIDA0IDAwIDA2IDAzIDAwIDA1IDAyIDA0IDAxIDAzIDA3IDA2CiAgICAwNSAwNyAwMiAwNCAwMSAwNiAwMyAwMCAwMyAwMCAwMiAwNCAwNiAwNyAwMSAwNQogICAgMDQgMDUgMDAgMDMgMDYgMDIgMDEgMDcgMDAgMDAgMDAgMDAgMDAgMDAgMDAgMDAnJycpCgogICAgb3JkZXIxID0gb3JkZXJzW2l2X3YwICogODppdl92MCAqIDggKyA4XQoKICAgIGl2X3YxID0gKGl2X3YxICsga2hyb25vcyArIDEpICYgNjMKICAgIHR0MSA9IFsweDg3YWVlYTVkYWIzN2NkNmIsIDB4N2ZmNDhiZWNiNGY1NDA4NywgMHhiMDcyNGMwNjcwNmJiZDVkLCAweDFmZTVkZmIxMTQzZTMyOGQsCiAgICAgICAgICAgMHgxYTIzMzFkMDBhZjRmMWYyLCAweGNhZmY3MTMxYmIxZTcxYmEsIDB4MzMzODVlMTA0Mjc1MjIxOCwgMHhmZjAxZWQ2NWQ0YTQ0MWZiLAogICAgICAgICAgIDB4YWRiMWVjODgyOGM4MGU4LCAweDYyNDc1ZDEyZjRlMDZmZTcsIDB4YmQwYjIzOGRhNGZlNzJdCgogICAgdHQyID0gWzBdICogMTEKICAgIGZvciBpIGluIHJhbmdlKDAsIDExKToKICAgICAgICB0dDJbaV0gPSByb3IodHQxW2ldLCBpdl92MSkKCiAgICB0b19zaWduID0gYnl0ZWFycmF5KHF1ZXJ5X3NtMyArIGJvZHlfbWQ1X2J5dGVzICsgdHNfYnl0ZXMgKyBieXRlcyhbMHg4MCwgMCwgMCwgMCwgMCwgMCwgMCwgMCwgMCwgMCwgMCwgMF0pKQoKICAgIHNyYyA9IFswXSAqIChsZW4odG9fc2lnbikgLy8gOCkKICAgIGZvciBpIGluIHJhbmdlKGxlbih0b19zaWduKSAvLyA4KToKICAgICAgICBzcmNbaV0gPSBpbnQuZnJvbV9ieXRlcyh0b19zaWduW2kgKiA4OmkgKiA4ICsgOF0sICdiaWcnKQoKICAgIHNyY194b3IgPSBbY192MSwgY192MSwgY192MSwgY192MSwgY192MSwgY192MSwgY192MSwgY192MV0KCiAgICB0YWJsZV9mID0gZ2V0X2JyYW5jaF8xX3RhYmxlX2YoaXZfdjApCiAgICBzd2FwID0gc3dhcF92MChzcmMsIHNyY194b3IsIHR0MiwgdGFibGVfZiwgb3JkZXIxKQogICAgZGF0YSA9IFswXSAqIDgKICAgIGRhdGFbN10gPSA0MTYKCiAgICBzcmNfeG9yID0gW3N3YXBbNF0sIHN3YXBbM10sIHN3YXBbMl0sIHN3YXBbMV0sIHN3YXBbMF0sIHN3YXBbN10sIHN3YXBbNl0sIHN3YXBbNV1dCiAgICBzd2FwID0gc3dhcF92MChkYXRhLCBzcmNfeG9yLCB0dDIsIHRhYmxlX2YsIG9yZGVyMSwgc3dhcCkKCiAgICByZXQgPSBieXRlYXJyYXkoMzIpCiAgICBuID0gMAogICAgZm9yIGkgaW4gcmFuZ2UoNywgLTEsIC0xKToKICAgICAgICBwcCA9IHN3YXBbaV0udG9fYnl0ZXMoOCwgImxpdHRsZSIpCiAgICAgICAgcmV0W24gKyAwXSwgcmV0W24gKyAxXSwgcmV0W24gKyAyXSwgcmV0W24gKyAzXSA9IHBwWzFdLCBwcFszXSwgcHBbNV0sIHBwWzZdCiAgICAgICAgbiArPSA0CgogICAgZm9yIGkgaW4gcmFuZ2UoMTYpOgogICAgICAgIHJldFtpXSBePSByZXRbaSArIDE2XQogICAgcmV0ID0gcmV0WzoxNl0KICAgIHN1bSA9IHN1bV9tZDUocmV0KQogICAgcmV0ICs9IHN1bS50b19ieXRlcyg0LCAibGl0dGxlIikKICAgIHJldHVybiByZXQKCmRlZiByMDAocjAsIHIxLCByMiwgcjMsIHI0LCByNSwgcjYsIHI3LCB0dCwgdGFibGVfZiwgdj0wKToKICAgIHggPSB0YWJsZV9mKDggKiAocjAgPj4gNTYpKQogICAgcjEgPSAocjEgPj4gNDUpICYgMjA0MAoKICAgIGlmIHR0ID4gMDoKICAgICAgICB4ID0geCBeIHR0CiAgICB4ID0geCBeIHRhYmxlX2YocjEgKyAyMDQ4KQoKICAgIHIyID0gKHIyID4+IDM3KSAmIDIwNDAKICAgIHggPSB4IF4gdGFibGVfZihyMiArIDQwOTYpCgogICAgcjMgPSAocjMgPj4gMjkpICYgMjA0MAogICAgeCA9IHggXiB0YWJsZV9mKHIzICsgNjE0NCkKCiAgICByNCA9IChyNCA+PiAyMSkgJiAyMDQwCiAgICB4ID0geCBeIHRhYmxlX2YocjQgKyA4MTkyKQoKICAgIHI1ID0gKHI1ID4+IDEzKSAmIDIwNDAKICAgIHggPSB4IF4gdGFibGVfZihyNSArIDEwMjQwKQoKICAgIHI2ID0gKHI2ID4+IDgpICYgMjU1CiAgICB4ID0geCBeIHRhYmxlX2YoOCAqIHI2ICsgMTIyODgpCgogICAgcjcgPSByNyAmIDI1NQogICAgeCA9IHggXiB0YWJsZV9mKDggKiByNyArIDE0MzM2KQoKICAgIHJldHVybiB4CgpicmFuY2hfMl9vcmRlcnMgPSBieXRlcy5mcm9taGV4KCcnJwogICAgMGYgMDcgMDQgMDAgMDkgMDggMDMgMGEgMDYgMGIgMDUgMGQgMGUgMDEgMGMgMDIgMGYgMDUgMDggMGMgMDAgMDkgMDIgMDEgMDMgMDcgMGUgMDYgMGIgMGEgMGQgMDQgMDYgMDUgMDAgMDcgMGMgMDAgMGEgMDQgMDggMGYgMDEgMGIgMGQgMDkgMDIgMGUgMDYgMGIgMDIgMDUgMDQgMDMgMDggMDEgMDEgMDcgMGEgMDAgMGQgMGMgMDkgMGUKICAgIDBkIDA3IDBlIDBmIDBiIDAyIDA4IDAzIDBjIDA1IDA5IDAxIDAwIDA0IDA2IDBhIDBkIDA5IDAyIDA2IDBmIDBiIDBhIDA0IDA4IDA3IDAwIDBjIDA1IDAzIDAxIDBlIDBjIDA5IDBmIDA3IDA2IDBmIDAzIDBlIDAyIDBkIDA0IDA1IDAxIDBiIDBhIDAwIDBjIDA1IDBhIDA5IDBlIDA4IDAyIDA0IDA0IDA3IDAzIDBmIDAxIDA2IDBiIDAwCiAgICAwYiAwZiAwNCAwOCAwMiAwYSAwNyAwMCAwOSAwZCAwNiAwMSAwZSAwMyAwNSAwYyAwYiAwNiAwYSAwNSAwOCAwMiAwYyAwMyAwNyAwZiAwZSAwOSAwZCAwMCAwMSAwNCAwOSAwNiAwOCAwZiAwNSAwOCAwMCAwNCAwYSAwYiAwMyAwZCAwMSAwMiAwYyAwZSAwOSAwZCAwYyAwNiAwNCAwNyAwYSAwMyAwMyAwZiAwMCAwOCAwMSAwNSAwMiAwZQogICAgMDEgMDAgMGQgMGYgMDkgMGEgMGIgMGUgMDQgMDIgMDggMDcgMDMgMDYgMGMgMDUgMDEgMDggMGEgMGMgMGYgMDkgMDUgMDYgMGIgMDAgMDMgMDQgMDIgMGUgMDcgMGQgMDQgMDggMGYgMDAgMGMgMGYgMGUgMGQgMGEgMDEgMDYgMDIgMDcgMDkgMDUgMDMgMDQgMDIgMDUgMDggMGQgMGIgMGEgMDYgMDYgMDAgMGUgMGYgMDcgMGMgMDkgMDMKICAgIDBhIDA4IDA0IDBmIDAwIDBiIDAxIDA2IDBkIDBjIDA3IDA5IDAzIDBlIDA1IDAyIDBhIDA3IDBiIDA1IDBmIDAwIDAyIDBlIDAxIDA4IDAzIDBkIDBjIDA2IDA5IDA0IDBkIDA3IDBmIDA4IDA1IDBmIDA2IDA0IDBiIDBhIDBlIDBjIDA5IDAwIDAyIDAzIDBkIDBjIDAyIDA3IDA0IDAxIDBiIDBlIDBlIDA4IDA2IDBmIDA5IDA1IDAwIDAzCiAgICAnJycpCgpkZWYgYnJhbmNoXzIoaXYsIGtocm9ub3MsIHF1ZXJ5X3NtMywgYm9keV9tZDVfYnl0ZXMsIHRzX2J5dGVzKToKICAgIG4wID0gKGl2ICYgMTUgLSAyKSAqIDg2CiAgICBpdl92MCA9IChuMCA+PiAxNSAmIDB4ZmYpICsgKG4wID4+IDggJiAweGZmKQoKICAgIHQwMDEgPSBbMHg4OTgwZjI5YiwgMHhlYjU0OWM3ZiwgMHhiMDg3MjZkYiwgMHhkNDBjYjVlNiwgMHhlOGY1NTllNF0KCiAgICBuMSA9IHQwMDFbaXZfdjBdCiAgICBjb3VudF92MSA9IChuMSArIGtocm9ub3MgKyAxKSAmIDB4ZmYKICAgIGNvdW50X3YyID0gKG4xICsga2hyb25vcykgJiAweGZmZmZmZmZmCgogICAgbjAgPSAoY291bnRfdjIgKyA1KSAmIDcKCiAgICBwYWQgPSBieXRlYXJyYXkoOCkKICAgIHNlZWQgPSBieXRlcyhbMHg4NCwgMHg5NiwgMHg3NywgMHg5ZCwgMHhkNCwgMHgxNSwgMHgwYiwgMHhmOF0pCiAgICBmb3IgaSBpbiByYW5nZSg4KToKICAgICAgICB2ID0gaW50LmZyb21fYnl0ZXMoYnl0ZXMoW3NlZWRbaV0sIHNlZWRbaV1dKSwgJ2xpdHRsZScpCiAgICAgICAgdiA9IHYgPj4gbjAKICAgICAgICBwYWRbaV0gPSB2ICYgMHhmZgoKICAgIGRhdGEgPSBxdWVyeV9zbTMgKyBib2R5X21kNV9ieXRlcyArIHRzX2J5dGVzICsgcGFkICsgYnl0ZXMuZnJvbWhleCgnYTAgMDEgMDAgMDAnKQoKICAgIGlkeCA9IGl2X3YwIDw8IDYKICAgIHJldCA9IG1kNXN1bV92MyhkYXRhLCBjb3VudF92MiwgYnJhbmNoXzJfb3JkZXJzW2lkeDppZHggKyA2NF0sIGNvdW50X3YxKQoKICAgIHJldHVybiByZXQKCmRlZiBicmFuY2gwX3hvcihkYXRhLCBiYXNlLCBkaSwgdHQwMywgcm91bmQsIHgxLCB4MiwgeDMsIHg0LCB4NSwgeDYsIHg3LCB4OCwgeDksIHgxMCk6CiAgICBkID0gZGF0YVs6XQoKICAgIGZvciBpIGluIHJhbmdlKHJvdW5kKToKICAgICAgICBvZmZzZXQgPSBiYXNlICsgaQogICAgICAgIG4wID0gZGlbb2Zmc2V0ICYgMTI3XQoKICAgICAgICBuMSA9ICgoZFt4M10gXiBkW3g0XSkgJiBkW3gxXSkgXiBkW3gzXQoKICAgICAgICBuMiA9IHJvbChkW3gxXSwgMjYpIF4gcm9sKGRbeDFdLCAyMSkgXiByb2woZFt4MV0sIDcpCiAgICAgICAgb2Zmc2V0ID0gb2Zmc2V0ICYgNjMKICAgICAgICBuMyA9IHR0MDNbb2Zmc2V0XQoKICAgICAgICBuNCA9IChuMCArIG4xICsgbjIgKyBuMyArIGRbeDVdKSAmIDB4ZmZmZmZmZmYKCiAgICAgICAgbjUgPSByb2woZFt4Ml0sIDMwKSBeIHJvbChkW3gyXSwgMTkpIF4gcm9sKGRbeDJdLCAxMCkKICAgICAgICBuNiA9IChkW3gyXSAmIGRbeDZdKSB8ICgoZFt4Ml0gfCBkW3g2XSkgJiBkW3g3XSkKICAgICAgICBuNyA9IG41ICsgbjYKCiAgICAgICAgbyA9IGRbeDldCiAgICAgICAgZFswXSwgZFsxXSwgZFsyXSwgZFszXSwgZFs0XSwgZFs1XSwgZFs2XSwgZFs3XSA9IGRbN10sIGRbMF0sIGRbMV0sIGRbMl0sIGRbM10sIGRbNF0sIGRbNV0sIGRbNl0KICAgICAgICBkW3gxMF0gPSAobjcgKyBuNCkgJiAweGZmZmZmZmZmCiAgICAgICAgZFt4OF0gPSAobyArIG40KSAmIDB4ZmZmZmZmZmYKICAgIHJldHVybiBkCgpicmFuY2hfMV90YWJsZSA9IE5vbmUKCmRlZiBnZXRfYnJhbmNoXzFfdGFibGVfZihpdl92MCk6CiAgICBnbG9iYWwgYnJhbmNoXzFfdGFibGUKICAgIGlmIGJyYW5jaF8xX3RhYmxlIGlzIE5vbmU6CiAgICAgICAgYnJhbmNoXzFfdGFibGUgPSBfYnJhbmNoX29uZV9ieXRlcygpCgogICAgdGFibGUgPSBicmFuY2hfMV90YWJsZVtpdl92MCA8PCAxNDpdCiAgICBkZWYgdGFibGVfZih4KToKICAgICAgICByZXR1cm4gaW50LmZyb21fYnl0ZXModGFibGVbeDp4ICsgOF0sICdsaXR0bGUnKQogICAgcmV0dXJuIHRhYmxlX2YKCmRlZiBfdmFyaW50KHZhbHVlOiBpbnQpIC0+IGJ5dGVzOgogICAgdmFsdWUgPSBpbnQodmFsdWUpCiAgICBpZiB2YWx1ZSA8IDA6CiAgICAgICAgdmFsdWUgJj0gKDEgPDwgNjQpIC0gMQogICAgcmVzdWx0ID0gYnl0ZWFycmF5KCkKICAgIHdoaWxlIHZhbHVlID4gMHg3RjoKICAgICAgICByZXN1bHQuYXBwZW5kKCh2YWx1ZSAmIDB4N0YpIHwgMHg4MCkKICAgICAgICB2YWx1ZSA+Pj0gNwogICAgcmVzdWx0LmFwcGVuZCh2YWx1ZSkKICAgIHJldHVybiBieXRlcyhyZXN1bHQpCgpkZWYgX3NpbnQodmFsdWU6IGludCwgYml0czogaW50KSAtPiBpbnQ6CiAgICAjIOato+W8jyBwcm90b2J1ZiDnvJbnoIHop4TliJnvvJrmraPmlbDkuI3lhYjmiKrmlq3liLDmnInnrKblj7fojIPlm7TvvJsKICAgICMg6L+Z5a+5IE1lZHVzYS5yYW5kIOetieWPr+iDveWkp+S6jiAyKiozMSDnmoQgc2ludDMyIOWtl+auteW+iOmHjeimgeOAggogICAgdmFsdWUgPSBpbnQodmFsdWUpCiAgICByZXR1cm4gKHZhbHVlIDw8IDEpIGlmIHZhbHVlID49IDAgZWxzZSAodmFsdWUgPDwgMSkgXiAofjApCgpkZWYgX3Byb3RvX2ZpZWxkKGZpZWxkOiBpbnQsIHZhbHVlOiBBbnksIGtpbmQ6IHN0cikgLT4gYnl0ZXM6CiAgICBpZiB2YWx1ZSBpbiAoTm9uZSwgIiIsIGIiIiwgMCwgMC4wLCBGYWxzZSk6CiAgICAgICAgcmV0dXJuIGIiIgogICAgaWYga2luZCA9PSAic2ludDMyIjoKICAgICAgICByZXR1cm4gX3ZhcmludCgoZmllbGQgPDwgMykgfCAwKSArIF92YXJpbnQoX3NpbnQoaW50KHZhbHVlKSwgMzIpKQogICAgaWYga2luZCA9PSAic2ludDY0IjoKICAgICAgICByZXR1cm4gX3ZhcmludCgoZmllbGQgPDwgMykgfCAwKSArIF92YXJpbnQoX3NpbnQoaW50KHZhbHVlKSwgNjQpKQogICAgaWYga2luZCA9PSAiZmxvYXQiOgogICAgICAgIHJldHVybiBfdmFyaW50KChmaWVsZCA8PCAzKSB8IDUpICsgc3RydWN0LnBhY2soIjxmIiwgZmxvYXQodmFsdWUpKQogICAgaWYga2luZCA9PSAiYnl0ZXMiOgogICAgICAgIHJhdyA9IGJ5dGVzKHZhbHVlKQogICAgZWxpZiBraW5kID09ICJzdHJpbmciOgogICAgICAgIHJhdyA9IHN0cih2YWx1ZSkuZW5jb2RlKCJ1dGYtOCIpCiAgICBlbGlmIGtpbmQgPT0gIm1lc3NhZ2UiOgogICAgICAgIHJhdyA9IGJ5dGVzKHZhbHVlKQogICAgZWxzZToKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKGYidW5rbm93biBwcm90b2J1ZiBmaWVsZCBraW5kOiB7a2luZH0iKQogICAgcmV0dXJuIF92YXJpbnQoKGZpZWxkIDw8IDMpIHwgMikgKyBfdmFyaW50KGxlbihyYXcpKSArIHJhdwoKZGVmIF9wcm90byhmaWVsZHM6IGxpc3RbdHVwbGVbaW50LCBBbnksIHN0cl1dKSAtPiBieXRlczoKICAgIHJldHVybiBiIiIuam9pbihfcHJvdG9fZmllbGQoZmllbGQsIHZhbHVlLCBraW5kKSBmb3IgZmllbGQsIHZhbHVlLCBraW5kIGluIGZpZWxkcykKCmRlZiBfZW5jb2RlX3JlcXVlc3QoKSAtPiBieXRlczoKICAgIHJldHVybiBfcHJvdG8oWwogICAgICAgICgxLCAxMTEsICJzaW50MzIiKSwKICAgICAgICAoMiwgMTAsICJzaW50MzIiKSwKICAgICAgICAoMywgNjk0MzY3LCAic2ludDMyIiksCiAgICAgICAgKDUsIDU4Njk1MjE5OSwgInNpbnQzMiIpLAogICAgXSkKCmRlZiBfZW5jb2RlX2RldmljZShkZXZpY2U6IE1hcHBpbmdbc3RyLCBBbnldKSAtPiBieXRlczoKICAgIGZpZWxkcyA9IFsKICAgICAgICAoMSwgZGV2aWNlLmdldCgiZDEiKSwgInNpbnQzMiIpLCAoMiwgZGV2aWNlLmdldCgiY29sbGVjdF9zdGF0IiksICJzaW50MzIiKSwKICAgICAgICAoMywgZGV2aWNlLmdldCgiYWlkIiksICJzdHJpbmciKSwgKDQsIGRldmljZS5nZXQoImRldmljZV9pZCIpLCAic3RyaW5nIiksCiAgICAgICAgKDUsIGRldmljZS5nZXQoInNlY19kZXZpY2VfdG9rZW4iKSwgInN0cmluZyIpLCAoNiwgZGV2aWNlLmdldCgiYXBwX3ZlcnNpb24iKSwgInN0cmluZyIpLAogICAgICAgICg3LCBkZXZpY2UuZ2V0KCJiYXR0ZXJ5IiksICJzaW50MzIiKSwgKDgsIGRldmljZS5nZXQoImJhdHRlcnkyIiksICJzaW50MzIiKSwKICAgICAgICAoOSwgZGV2aWNlLmdldCgiYmF0dGVyeV9oZWFsdGgiKSwgInNpbnQzMiIpLCAoMTAsIGRldmljZS5nZXQoImJhdHRlcnlfY2hhbmdlZCIpLCAic2ludDMyIiksCiAgICAgICAgKDExLCBkZXZpY2UuZ2V0KCJuZXR3b3JrIiksICJzdHJpbmciKSwgKDEyLCBkZXZpY2UuZ2V0KCJ0eiIpLCAic3RyaW5nIiksCiAgICAgICAgKDEzLCBkZXZpY2UuZ2V0KCJsYW4iKSwgInN0cmluZyIpLCAoMTQsIGRldmljZS5nZXQoImNwdSIpLCAic2ludDMyIiksCiAgICAgICAgKDE1LCBkZXZpY2UuZ2V0KCJyZXNvbHV0aW9uIiksICJzdHJpbmciKSwgKDE2LCBkZXZpY2UuZ2V0KCJzZGNhcmQiKSwgImZsb2F0IiksCiAgICAgICAgKDE3LCBkZXZpY2UuZ2V0KCJzZGNhcmRfdXNlZCIpLCAiZmxvYXQiKSwgKDE4LCBkZXZpY2UuZ2V0KCJtZW1vcnkiKSwgImZsb2F0IiksCiAgICAgICAgKDE5LCBkZXZpY2UuZ2V0KCJtZW1vcnkyIiksICJmbG9hdCIpLCAoMjAsIGRldmljZS5nZXQoImRhdGEiKSwgImZsb2F0IiksCiAgICAgICAgKDIxLCBkZXZpY2UuZ2V0KCJkYXRhX3VzZWQiKSwgImZsb2F0IiksICgyMiwgZGV2aWNlLmdldCgib3NfdmVyc2lvbiIpLCAic3RyaW5nIiksCiAgICAgICAgKDIzLCBkZXZpY2UuZ2V0KCJicmlnaHRuZXNzIiksICJzaW50MzIiKSwgKDI0LCBkZXZpY2UuZ2V0KCJ2b2x1bWUiKSwgInNpbnQzMiIpLAogICAgICAgICgyNSwgZGV2aWNlLmdldCgidHMiKSwgInNpbnQ2NCIpLCAoMjYsIGRldmljZS5nZXQoInRzMiIpLCAic2ludDY0IiksCiAgICAgICAgKDI3LCBkZXZpY2UuZ2V0KCJ0czMiKSwgInNpbnQ2NCIpLCAoMjgsIGRldmljZS5nZXQoInRzNCIpLCAic2ludDY0IiksCiAgICAgICAgKDI5LCBkZXZpY2UuZ2V0KCJ1c2IiKSwgInNpbnQzMiIpLCAoMzAsIGRldmljZS5nZXQoImh3X3ZlcnNpb24iKSwgInN0cmluZyIpLAogICAgICAgICgzMSwgZGV2aWNlLmdldCgiYnJhbmQiKSwgInN0cmluZyIpLCAoMzIsIGRldmljZS5nZXQoImJvYXJkIiksICJzdHJpbmciKSwKICAgICAgICAoMzMsIGRldmljZS5nZXQoInByb2R1Y3RfbmFtZSIpLCAic3RyaW5nIiksICgzNCwgZGV2aWNlLmdldCgicHJvZHVjdF9kZXZpY2UiKSwgInN0cmluZyIpLAogICAgICAgICgzNSwgZGV2aWNlLmdldCgicHJvZHVjdF9tYW51ZmFjdHVyZXIiKSwgInN0cmluZyIpLCAoMzYsIGRldmljZS5nZXQoImhhcmR3YXJlIiksICJzdHJpbmciKSwKICAgICAgICAoMzgsIGRldmljZS5nZXQoInVua25vd24zOCIpLCAic2ludDMyIiksICg0MCwgZGV2aWNlLmdldCgidW5rbm93bjQwIiksICJzaW50MzIiKSwKICAgIF0KICAgIHJldHVybiBfcHJvdG8oZmllbGRzKQoKZGVmIF9lbmNvZGVfZW52KGVudjogTWFwcGluZ1tzdHIsIEFueV0pIC0+IGJ5dGVzOgogICAgZmllbGRzID0gWwogICAgICAgICgxLCBlbnYuZ2V0KCJsYXVuY2hfdGltZSIpLCAic2ludDMyIiksICgyLCBlbnYuZ2V0KCJ1bmtub3duMiIpLCAic2ludDMyIiksCiAgICAgICAgKDMsIGVudi5nZXQoInVua25vd24zIiksICJzaW50MzIiKSwgKDUsIGVudi5nZXQoInVua25vd241IiksICJzaW50MzIiKSwKICAgICAgICAoNiwgZW52LmdldCgidmVyc2lvbiIpLCAic3RyaW5nIiksICg3LCBlbnYuZ2V0KCJwaWQiKSwgInNpbnQzMiIpLAogICAgICAgICgxMiwgX2VuY29kZV9kZXZpY2UoZW52LmdldCgiZGV2aWNlIikgb3Ige30pLCAibWVzc2FnZSIpLAogICAgICAgICgxMywgX3Byb3RvKFsKICAgICAgICAgICAgKDEsIChlbnYuZ2V0KCJyZXBvcnQiKSBvciB7fSkuZ2V0KCJ0aW1lIiksICJzaW50NjQiKSwKICAgICAgICAgICAgKDIsIChlbnYuZ2V0KCJyZXBvcnQiKSBvciB7fSkuZ2V0KCJzdGF0ZSIpLCAic2ludDMyIiksCiAgICAgICAgICAgICg0LCAoZW52LmdldCgicmVwb3J0Iikgb3Ige30pLmdldCgiY29kZSIpLCAic2ludDMyIiksCiAgICAgICAgICAgICg1LCAoZW52LmdldCgicmVwb3J0Iikgb3Ige30pLmdldCgidGltZXMiKSwgInNpbnQzMiIpLAogICAgICAgICAgICAoNiwgKGVudi5nZXQoInJlcG9ydCIpIG9yIHt9KS5nZXQoInVua25vd242IiksICJzaW50MzIiKSwKICAgICAgICBdKSwgIm1lc3NhZ2UiKSwKICAgICAgICAoMTQsIGVudi5nZXQoImFwcF92ZXJzaW9uIiksICJzdHJpbmciKSwKICAgICAgICAoMTUsIGVudi5nZXQoInVua25vd24xNSIpLCAic2ludDMyIiksICgxNiwgZW52LmdldCgidW5rbm93bjE2IiksICJzaW50MzIiKSwKICAgICAgICAoMTgsIGVudi5nZXQoInVua25vd24xOCIpLCAic2ludDMyIiksICgxOSwgZW52LmdldCgidW5rbm93bjE5IiksICJzaW50MzIiKSwKICAgICAgICAoMjAsIGVudi5nZXQoInVua25vd24yMCIpLCAic2ludDMyIiksICgyMSwgZW52LmdldCgidW5rbm93bjIxIiksICJzaW50MzIiKSwKICAgIF0KICAgIHJldHVybiBfcHJvdG8oZmllbGRzKQoKZGVmIF9lbmNvZGVfbWVkdXNhKHZhbHVlczogTWFwcGluZ1tzdHIsIEFueV0pIC0+IGJ5dGVzOgogICAgcmV0dXJuIF9wcm90byhbCiAgICAgICAgKDEsIHZhbHVlcy5nZXQoIm1hZ2ljIiksICJieXRlcyIpLCAoMiwgdmFsdWVzLmdldCgidmVyc2lvbiIpLCAic2ludDMyIiksCiAgICAgICAgKDMsIHZhbHVlcy5nZXQoInJhbmQiKSwgInNpbnQzMiIpLCAoNCwgdmFsdWVzLmdldCgibXNfYXBwX2lkIiksICJzdHJpbmciKSwKICAgICAgICAoNSwgdmFsdWVzLmdldCgiZGV2aWNlX2lkIiksICJzdHJpbmciKSwgKDYsIHZhbHVlcy5nZXQoImxpY2Vuc2VfaWQiKSwgInN0cmluZyIpLAogICAgICAgICg3LCB2YWx1ZXMuZ2V0KCJhcHBfdmVyc2lvbiIpLCAic3RyaW5nIiksICg4LCB2YWx1ZXMuZ2V0KCJzZGtfdmVyc2lvbl9zdHIiKSwgInN0cmluZyIpLAogICAgICAgICg5LCB2YWx1ZXMuZ2V0KCJzZGtfdmVyc2lvbiIpLCAic2ludDMyIiksICgxMCwgdmFsdWVzLmdldCgieGdfc2VlZF9ieXRlcyIpLCAiYnl0ZXMiKSwKICAgICAgICAoMTIsIHZhbHVlcy5nZXQoInRpbWUiKSwgInNpbnQzMiIpLCAoMTMsIHZhbHVlcy5nZXQoInF1ZXJ5X2JvZHlfdHNfaGFzaCIpLCAiYnl0ZXMiKSwKICAgICAgICAoMTQsIHZhbHVlcy5nZXQoInF1ZXJ5X3NtMyIpLCAiYnl0ZXMiKSwgKDE1LCBfZW5jb2RlX3JlcXVlc3QoKSwgIm1lc3NhZ2UiKSwKICAgICAgICAoMTYsIHZhbHVlcy5nZXQoInNlY19kZXZpY2VfdG9rZW4iKSwgInN0cmluZyIpLCAoMTcsIHZhbHVlcy5nZXQoInRpbWUyIiksICJzaW50MzIiKSwKICAgICAgICAoMTgsIHZhbHVlcy5nZXQoImxhbnVza19oYXNoIiksICJieXRlcyIpLCAoMTksIHZhbHVlcy5nZXQoInF1ZXJ5X2JvZHlfaGFzaF9zbTMiKSwgImJ5dGVzIiksCiAgICAgICAgKDIwLCB2YWx1ZXMuZ2V0KCJwc2tfdmVyc2lvbiIpLCAic3RyaW5nIiksICgyMSwgdmFsdWVzLmdldCgiY2FsbF90eXBlIiksICJzaW50MzIiKSwKICAgICAgICAoMjMsIF9lbmNvZGVfZW52KHZhbHVlcy5nZXQoImVudiIpIG9yIHt9KSwgIm1lc3NhZ2UiKSwKICAgICAgICAoMjQsIHZhbHVlcy5nZXQoInVua25vd24yNCIpLCAic3RyaW5nIiksICgyNiwgdmFsdWVzLmdldCgib3JpZ2luYWwiKSwgInN0cmluZyIpLAogICAgXSkKCmRlZiBfanNvbl9ib2R5X21kNShkYXRhOiBBbnksIGRhdGFfdHlwZTogc3RyIHwgTm9uZSA9IE5vbmUpIC0+IHN0cjoKICAgIGlmIG5vdCBkYXRhOgogICAgICAgIHJldHVybiAiIgogICAgaWYgaXNpbnN0YW5jZShkYXRhLCBzdHIpOgogICAgICAgIHJhdyA9IGRhdGEuZW5jb2RlKCJ1dGYtOCIpCiAgICBlbGlmIGlzaW5zdGFuY2UoZGF0YSwgYnl0ZXMpOgogICAgICAgIHJhdyA9IGRhdGEKICAgIGVsaWYgZGF0YV90eXBlID09ICJhcHBsaWNhdGlvbi9qc29uOyBjaGFyc2V0PVVURi04IjoKICAgICAgICByYXcgPSBqc29uLmR1bXBzKGRhdGEsIGVuc3VyZV9hc2NpaT1GYWxzZSwgc2VwYXJhdG9ycz0oIiwiLCAiOiIpKS5lbmNvZGUoInV0Zi04IikKICAgIGVsc2U6CiAgICAgICAgcmF3ID0gdXJsZW5jb2RlKGRhdGEpLmVuY29kZSgidXRmLTgiKQogICAgcmV0dXJuIGhhc2hsaWIubWQ1KHJhdykuaGV4ZGlnZXN0KCkudXBwZXIoKQoKZGVmIF91cmxfZW5jb2RlKHZhbHVlOiBNYXBwaW5nW3N0ciwgQW55XSkgLT4gc3RyOgogICAgcmV0dXJuIHVybGVuY29kZSh2YWx1ZSkucmVwbGFjZSgiKyIsICIlMjAiKS5yZXBsYWNlKCIlMkEiLCAiKiIpCgpkZWYgX2dldF9wYXJhbXNfZW5jcnlwdHVybCh1cmw6IHN0ciwgcGFyYW1zOiBNYXBwaW5nW3N0ciwgQW55XSwgZGV2aWNlczogTWFwcGluZ1tzdHIsIEFueV0pIC0+IHR1cGxlW3N0ciwgZGljdFtzdHIsIEFueV1dOgogICAgcmVzdWx0ID0gZGljdChwYXJhbXMpCiAgICBmb3Iga2V5LCB2YWx1ZSBpbiBkZXZpY2VzLml0ZW1zKCk6CiAgICAgICAgaWYga2V5IGluIHJlc3VsdDoKICAgICAgICAgICAgcmVzdWx0W2tleV0gPSB2YWx1ZQogICAgICAgIGVsaWYga2V5ID09ICJkZXZpY2VfaWQiIGFuZCAiZGlkIiBpbiByZXN1bHQ6CiAgICAgICAgICAgIHJlc3VsdFsiZGlkIl0gPSB2YWx1ZQogICAgcmVzdWx0WyJ0cyJdID0gaW50KHRpbWUudGltZSgpKQogICAgcmVzdWx0WyJfcnRpY2tldCJdID0gaW50KHRpbWUudGltZSgpICogMTAwMCkKICAgIHJldHVybiB1cmwuc3BsaXQoIj8iLCAxKVswXSArICI/IiArIF91cmxfZW5jb2RlKHJlc3VsdCksIHJlc3VsdAoKZGVmIF94Z19yYzQoZGF0YTogYnl0ZXMsIGtleTogYnl0ZXMpIC0+IGJ5dGVhcnJheToKICAgIHRhYmxlID0gbGlzdChyYW5nZSgyNTYpKQogICAgaiA9IDAKICAgIGZvciBpIGluIHJhbmdlKDI1Nik6CiAgICAgICAgaiA9IChqICsgdGFibGVbaV0gKyBrZXlbaSAlIGxlbihrZXkpXSkgJSAyNTYKICAgICAgICB0YWJsZVtpXSA9IHRhYmxlW2pdCiAgICBpID0gaiA9IDAKICAgIHJlc3VsdCA9IGJ5dGVhcnJheShsZW4oZGF0YSkpCiAgICBmb3IgaW5kZXgsIHZhbHVlIGluIGVudW1lcmF0ZShkYXRhKToKICAgICAgICBpID0gKGkgKyAxKSAmIDB4RkYKICAgICAgICB4ID0gdGFibGVbaV0KICAgICAgICBqID0gKGogKyB4KSAmIDB4RkYKICAgICAgICB5ID0gdGFibGVbal0KICAgICAgICAjIOS/neaMgeato+W8j+Wfuue6v+eahCBSQzQg5Y+Y5L2T77ya6L+Z6YeM5Y+q6KaG55uWIFNbaV3vvIzkuI3kuqTmjaIgU1tqXeOAggogICAgICAgIHRhYmxlW2ldID0geQogICAgICAgIHJlc3VsdFtpbmRleF0gPSB2YWx1ZSBeIHRhYmxlWyh5ICsgeSkgJiAweEZGXQogICAgcmV0dXJuIHJlc3VsdAoKZGVmIF9yZXZlcnNlX2JpdHModmFsdWU6IGludCkgLT4gaW50OgogICAgcmV0dXJuIGludChmInt2YWx1ZTowOGJ9Ils6Oi0xXSwgMikKCmRlZiBfZW5jcnlwdF9nb3Jnb24oYm9keTogQW55LCBxdWVyeTogc3RyLCBraHJvbm9zOiBpbnQsIHhnX3JhbmQ6IGludCwgZGF0YV90eXBlOiBzdHIpIC0+IHN0cjoKICAgIGJvZHlfbWQ1ID0gX2pzb25fYm9keV9tZDUoYm9keSwgZGF0YV90eXBlKS5sb3dlcigpIGlmIGJvZHkgZWxzZSAiIgogICAgZGF0YSA9IGJ5dGVhcnJheShoYXNobGliLm1kNShxdWVyeS5lbmNvZGUoKSkuZGlnZXN0KClbOjRdKQogICAgZGF0YSArPSBieXRlcy5mcm9taGV4KGJvZHlfbWQ1KVs6NF0gaWYgYm9keV9tZDUgZWxzZSBiIlwwXDBcMFwwIgogICAgZGF0YSArPSBiIlwwXDBcMFwwIiArICg2NzUwMzEwNCkudG9fYnl0ZXMoNCwgImxpdHRsZSIpICsga2hyb25vcy50b19ieXRlcyg0LCAiYmlnIikKICAgIGtleSA9IGJ5dGVzKCgweDRBLCAzMjAgJiAweEZGLCAweDE2LCAoeGdfcmFuZCA+PiA4KSAmIDB4RkYsIDB4NDcsIDB4NkMsIDEsIHhnX3JhbmQgJiAweEZGKSkKICAgIHJlc3VsdCA9IF94Z19yYzQoZGF0YSwga2V5KQogICAgZm9yIGluZGV4LCB2YWx1ZSBpbiBlbnVtZXJhdGUocmVzdWx0KToKICAgICAgICB2YWx1ZSA9ICgodmFsdWUgPj4gNCkgfCAodmFsdWUgPDwgNCkpICYgMHhGRgogICAgICAgIGZvbGxvd2luZyA9IHJlc3VsdFtpbmRleCArIDFdIGlmIGluZGV4ICsgMSA8IGxlbihyZXN1bHQpIGVsc2UgcmVzdWx0WzBdCiAgICAgICAgcmVzdWx0W2luZGV4XSA9ICh+KF9yZXZlcnNlX2JpdHMoZm9sbG93aW5nIF4gdmFsdWUpIF4gMjApKSAmIDB4RkYKICAgIHJldHVybiAoYiJceDg0XHgwNCIgKyB4Z19yYW5kLnRvX2J5dGVzKDIsICJsaXR0bGUiKSArICgzMjApLnRvX2J5dGVzKDIsICJsaXR0bGUiKSArIHJlc3VsdCkuaGV4KCkKCmRlZiBfcm9yNjQodmFsdWU6IGludCwgY291bnQ6IGludCkgLT4gaW50OgogICAgY291bnQgJT0gNjQKICAgIHJldHVybiAoKHZhbHVlID4+IGNvdW50KSB8ICh2YWx1ZSA8PCAoNjQgLSBjb3VudCkpKSAmIDB4RkZGRkZGRkZGRkZGRkZGRgoKZGVmIF9lbmNyeXB0X2hlbGlvcyhraHJvbm9zOiBpbnQsIHJhbmRfdmFsdWU6IGludCA9IDApIC0+IHN0cjoKICAgIHZhbHVlID0gcmFuZF92YWx1ZSBvciByYW5kb20ucmFuZGludCgwLCAweEZGRkZGRkZGKQogICAgc2VlZCA9IHZhbHVlLnRvX2J5dGVzKDQsICJsaXR0bGUiKSArIGIiODY2MiIKICAgIGRpZ2VzdCA9IGhhc2hsaWIubWQ1KHNlZWQpLmRpZ2VzdCgpCiAgICBrZXlzID0gYiIiLmpvaW4oZiJ7aXRlbTowMnh9Ii5lbmNvZGUoKSBmb3IgaXRlbSBpbiBkaWdlc3QpCiAgICB0YWJsZSA9IFtpbnQuZnJvbV9ieXRlcyhrZXlzWzo4XSwgImxpdHRsZSIpXQogICAgd29yZHMgPSBbaW50LmZyb21fYnl0ZXMoa2V5c1tpOmkgKyA4XSwgImxpdHRsZSIpIGZvciBpIGluIHJhbmdlKDAsIDMyLCA4KV0KICAgIGZpcnN0LCBzZWNvbmQgPSB3b3Jkc1swXSwgd29yZHNbMV0KICAgIHdvcmRzID0gd29yZHNbMjpdCiAgICBmb3IgaW5kZXggaW4gcmFuZ2UoMHgyMik6CiAgICAgICAgdmFsdWUyID0gX3JvcjY0KHNlY29uZCwgOCkKICAgICAgICB2YWx1ZTIgPSAodmFsdWUyICsgZmlyc3QpICYgMHhGRkZGRkZGRkZGRkZGRkZGCiAgICAgICAgdmFsdWUyID0gKHZhbHVlMiBeIGluZGV4KSAmIDB4RkZGRkZGRkZGRkZGRkZGRgogICAgICAgIHdvcmRzLmFwcGVuZCh2YWx1ZTIpCiAgICAgICAgdmFsdWUyIF49IF9yb3I2NChmaXJzdCwgNjEpCiAgICAgICAgdmFsdWUyICY9IDB4RkZGRkZGRkZGRkZGRkZGRgogICAgICAgIHRhYmxlLmFwcGVuZCh2YWx1ZTIpCiAgICAgICAgZmlyc3QsIHNlY29uZCA9IHZhbHVlMiwgd29yZHMucG9wKDApCiAgICByYXcgPSAoZiJ7a2hyb25vc30tMTU4ODA5MzIyOC04NjYyIikuZW5jb2RlKCkKICAgIHBhZCA9IDE2IC0gbGVuKHJhdykgJSAxNgogICAgcmF3ICs9IGJ5dGVzKFtwYWRdKSAqIHBhZAogICAgb3V0cHV0ID0gYnl0ZWFycmF5KCkKICAgIGZvciBvZmZzZXQgaW4gcmFuZ2UoMCwgbGVuKHJhdyksIDE2KToKICAgICAgICBsZWZ0ID0gaW50LmZyb21fYnl0ZXMocmF3W29mZnNldDpvZmZzZXQgKyA4XSwgImxpdHRsZSIpCiAgICAgICAgcmlnaHQgPSBpbnQuZnJvbV9ieXRlcyhyYXdbb2Zmc2V0ICsgODpvZmZzZXQgKyAxNl0sICJsaXR0bGUiKQogICAgICAgIGZvciBpbmRleCBpbiByYW5nZSgweDIyKToKICAgICAgICAgICAgcmlnaHQgPSAodGFibGVbaW5kZXhdIF4gKGxlZnQgKyBfcm9yNjQocmlnaHQsIDgpKSkgJiAweEZGRkZGRkZGRkZGRkZGRkYKICAgICAgICAgICAgbGVmdCA9IChyaWdodCBeIF9yb3I2NChsZWZ0LCA2MSkpICYgMHhGRkZGRkZGRkZGRkZGRkZGCiAgICAgICAgb3V0cHV0ICs9IGxlZnQudG9fYnl0ZXMoOCwgImxpdHRsZSIpICsgcmlnaHQudG9fYnl0ZXMoOCwgImxpdHRsZSIpCiAgICByZXR1cm4gYmFzZTY0LmI2NGVuY29kZSh2YWx1ZS50b19ieXRlcyg0LCAibGl0dGxlIikgKyBvdXRwdXQpLmRlY29kZSgpCgpkZWYgX2dlbl9tZWR1c2FfcHJvdG8odXJsOiBzdHIsIHVybF9wYXJhbXM6IE1hcHBpbmdbc3RyLCBBbnldLCBkZXZpY2VzOiBNYXBwaW5nW3N0ciwgQW55XSwgZGF0YTogQW55LCBraHJvbm9zOiBpbnQsIGRhdGFfdHlwZTogc3RyKSAtPiB0dXBsZVtieXRlcywgYnl0ZXMsIGJ5dGVzXToKICAgIGJvZHlfbWQ1ID0gX2pzb25fYm9keV9tZDUoZGF0YSwgZGF0YV90eXBlKS5sb3dlcigpIGlmIGRhdGEgZWxzZSAiIgogICAgYm9keV9tZDVfYnl0ZXMgPSBieXRlcy5mcm9taGV4KGJvZHlfbWQ1KSBpZiBib2R5X21kNSBlbHNlIGJ5dGVzKDE2KQogICAgdHNfYnl0ZXMgPSBraHJvbm9zLnRvX2J5dGVzKDQsICJsaXR0bGUiKQogICAgcXVlcnkgPSB1cmwuc3BsaXQoIj8iLCAxKVsxXSBpZiAiPyIgaW4gdXJsIGVsc2UgIiIKICAgIHF1ZXJ5X3NtMyA9IFNNMyhxdWVyeSkuZGlnZXN0KCkKICAgIHF1ZXJ5X2JvZHlfaGFzaCA9IFNNMyhxdWVyeS5lbmNvZGUoKSArIGJvZHlfbWQ1X2J5dGVzICsgYiJub25lIikuZGlnZXN0KCkKICAgIGRldmljZV9pZCA9IHN0cihkZXZpY2VzLmdldCgiZGV2aWNlX2lkIiwgdXJsX3BhcmFtcy5nZXQoImRldmljZV9pZCIsIHVybF9wYXJhbXMuZ2V0KCJkaWQiLCAiIikpKSkKICAgIHZlcnNpb25fbmFtZSA9IHN0cihkZXZpY2VzLmdldCgidmVyc2lvbl9uYW1lIiwgdXJsX3BhcmFtcy5nZXQoInZlcnNpb25fbmFtZSIsICI3LjEuMy4zMiIpKSkKICAgIGRldmljZV9tb2RlbCA9IHN0cihkZXZpY2VzLmdldCgiZGV2aWNlX21vZGVsIiwgdXJsX3BhcmFtcy5nZXQoImRldmljZV90eXBlIiwgIiIpKSkKICAgIGJyYW5kID0gc3RyKGRldmljZXMuZ2V0KCJkZXZpY2VfYnJhbmQiLCB1cmxfcGFyYW1zLmdldCgiZGV2aWNlX2JyYW5kIiwgIiIpKSkKICAgIHNlY19kZXZpY2VfdG9rZW4gPSBzdHIoZGV2aWNlcy5nZXQoInNlY19kZXZpY2VfdG9rZW4iKSBvciAiIikKICAgIGRldmljZV9zZWNfZGV2aWNlX3Rva2VuID0gc3RyKGRldmljZXMuZ2V0KCJkZXZpY2Vfc2VjX2RldmljZV90b2tlbiIpIG9yICIiKQogICAgcHJvdG9fcmFuZCA9IHJhbmRvbS5yYW5kaW50KDAsIDB4RkZGRkZGRkYpCiAgICBsYXVuY2hfdGltZSA9IHJhbmRvbS5yYW5kaW50KDEwMCwgMTIwKQogICAgcHJvY2Vzc19pZCA9IHJhbmRvbS5yYW5kaW50KDEwMDAxLCAxMjAwMCkKICAgICMg6L+Z5Lqb5a2X5q615piv5q2j5byP562+5ZCN5a6e546w5Lit55qE5Zu65a6a546v5aKD6YeH5qC35YC877yM5LiN5piv55So5oi36K6+5aSH5qCH6K+G44CCCiAgICByZXBvcnRfdHMgPSAxNzI4Mzg4MDE2NjM1CiAgICByZXBvcnRfdGltZSA9IGludCh0aW1lLnRpbWUoKSkKICAgIGRldmljZSA9IHsKICAgICAgICAiZDEiOiAxLCAiY29sbGVjdF9zdGF0IjogMiwgImFpZCI6ICI4NjYyIiwgImRldmljZV9pZCI6IGRldmljZV9pZCwKICAgICAgICAic2VjX2RldmljZV90b2tlbiI6IGRldmljZV9zZWNfZGV2aWNlX3Rva2VuLAogICAgICAgICJhcHBfdmVyc2lvbiI6ICIhbm9wZXJtISIsICJiYXR0ZXJ5IjogLTg4ODg4OCwgImJhdHRlcnkyIjogLTg4ODg4OCwKICAgICAgICAiYmF0dGVyeV9oZWFsdGgiOiAzLCAiYmF0dGVyeV9jaGFuZ2VkIjogLTg4ODg4OCwgIm5ldHdvcmsiOiAiIW5vdHNldCEiLAogICAgICAgICJ0eiI6ICJBc2lhL1NoYW5naGFpLDgiLCAibGFuIjogInpoX0NOIiwgImNwdSI6IDQsCiAgICAgICAgInNkY2FyZCI6IDI1NS4yNDk5Mzg5NjQ4NDM3NSwgInNkY2FyZF91c2VkIjogMzUuNTg1OTkwOTA1NzYxNzIsCiAgICAgICAgIm1lbW9yeSI6IDMuNDY3NDQ5MTg4MjMyNDIyLCAibWVtb3J5MiI6IDMuNDY3NDQ5MTg4MjMyNDIyLAogICAgICAgICJkYXRhIjogMjU1LjE3NTQ5MTMzMzAwNzgsICJkYXRhX3VzZWQiOiA0Mi4xNzU0NDE3NDE5NDMzNiwKICAgICAgICAib3NfdmVyc2lvbiI6IHN0cihkZXZpY2VzLmdldCgib3NfdmVyc2lvbiIsIHVybF9wYXJhbXMuZ2V0KCJvc192ZXJzaW9uIiwgIiIpKSksCiAgICAgICAgImJyaWdodG5lc3MiOiA0MSwgInZvbHVtZSI6IDM2LCAidHMiOiByZXBvcnRfdHMsICJ0czIiOiByZXBvcnRfdHMsCiAgICAgICAgInRzMyI6IHJlcG9ydF90cywgInRzNCI6IHJlcG9ydF90cyArIDIsICJ1c2IiOiAtMSwgImh3X3ZlcnNpb24iOiBkZXZpY2VfbW9kZWwsCiAgICAgICAgImJyYW5kIjogYnJhbmQsICJib2FyZCI6IGRldmljZV9tb2RlbCwgInByb2R1Y3RfbmFtZSI6IGRldmljZV9tb2RlbCwKICAgICAgICAicHJvZHVjdF9kZXZpY2UiOiBzdHIoZGV2aWNlcy5nZXQoImRldmljZV9tYW51ZmFjdHVyZXIiLCBicmFuZCkpLAogICAgICAgICJwcm9kdWN0X21hbnVmYWN0dXJlciI6IGJyYW5kLCAiaGFyZHdhcmUiOiBicmFuZCwgInVua25vd24zOCI6IDMxLAogICAgfQogICAgZW52ID0gewogICAgICAgICJsYXVuY2hfdGltZSI6IGxhdW5jaF90aW1lLCAidW5rbm93bjIiOiAxNDYzMzEzOTksCiAgICAgICAgInVua25vd24zIjogMTQ2MzMxMzk2LCAidW5rbm93bjUiOiA3LCAidmVyc2lvbiI6ICJ2MDQuMDYuMDQuMDMtYnVnZml4IiwKICAgICAgICAicGlkIjogcHJvY2Vzc19pZCwgImRldmljZSI6IGRldmljZSwKICAgICAgICAicmVwb3J0IjogeyJ0aW1lIjogcmVwb3J0X3RpbWUsICJzdGF0ZSI6IC0yLCAiY29kZSI6IDIwMCwgInRpbWVzIjogMCwgInVua25vd242IjogMH0sCiAgICAgICAgImFwcF92ZXJzaW9uIjogdmVyc2lvbl9uYW1lLAogICAgfQogICAgdmFsdWVzID0gewogICAgICAgICJtYWdpYyI6IGIiXHhmN1x4ZThfXHhmYVx4ZDdceGQ3XHhkYztceGQ2Klx4YzhwV1x4Y2ZhXHgxOCIsCiAgICAgICAgInZlcnNpb24iOiAzLCAicmFuZCI6IHByb3RvX3JhbmQsICJtc19hcHBfaWQiOiAiODY2MiIsCiAgICAgICAgImRldmljZV9pZCI6IGRldmljZV9pZCwgImxpY2Vuc2VfaWQiOiAiMTU4ODA5MzIyOCIsICJhcHBfdmVyc2lvbiI6IHZlcnNpb25fbmFtZSwKICAgICAgICAic2RrX3ZlcnNpb25fc3RyIjogInYwNC4wNi4wNC1tbC1hbmRyb2lkIiwgInNka192ZXJzaW9uIjogNjc1MDMxMDQsCiAgICAgICAgInhnX3NlZWRfYnl0ZXMiOiAoMzIwKS50b19ieXRlcyg4LCAibGl0dGxlIiksICJ0aW1lIjoga2hyb25vcywKICAgICAgICAicXVlcnlfYm9keV90c19oYXNoIjogaGFzaF9mMTMocXVlcnlfc20zLCBib2R5X21kNV9ieXRlcywgdHNfYnl0ZXMsIGtocm9ub3MpLAogICAgICAgICJxdWVyeV9zbTMiOiBxdWVyeV9zbTNbOjZdLCAic2VjX2RldmljZV90b2tlbiI6IHNlY19kZXZpY2VfdG9rZW4sICJ0aW1lMiI6IGtocm9ub3MsCiAgICAgICAgImxhbnVza19oYXNoIjogYiIiLCAicXVlcnlfYm9keV9oYXNoX3NtMyI6IHF1ZXJ5X2JvZHlfaGFzaCwgInBza192ZXJzaW9uIjogIm5vbmUiLAogICAgICAgICJjYWxsX3R5cGUiOiAzMTIsICJlbnYiOiBlbnYsCiAgICAgICAgInVua25vd24yNCI6ICd7ImNtciI6MTY3NzcyMTYsImNtcjIiOjE2Nzc3MjE2LCJ1bl9oIjoxODc5MTk0MDQwLCJ2cG4iOjAsImtkIjowLCJma2QiOjM2NzI1MTg5NzIsInBkIjotMTg3MjU3MzI0NywiZHluIjoiIiwiZG8iOjAsInRrIjp0cnVlfScsCiAgICB9CiAgICByZXR1cm4gX2VuY29kZV9tZWR1c2EodmFsdWVzKSwgcXVlcnlfc20zLCBoYXNoX2YxMyhxdWVyeV9zbTMsIGJvZHlfbWQ1X2J5dGVzLCB0c19ieXRlcywga2hyb25vcykKCmRlZiBfeG14b3JfdHdvKGRhdGE6IGJ5dGVzLCBrZXk6IGJ5dGVzKSAtPiBieXRlYXJyYXk6CiAgICBlbmNvZGVkID0gYnl0ZWFycmF5KGxlbihkYXRhKSkKICAgIGZvciBpbmRleCwgdmFsdWUgaW4gZW51bWVyYXRlKGRhdGEpOgogICAgICAgIHBvc2l0aW9uID0gKGluZGV4ICogNCkgJiAyOAogICAgICAgIGQwLCBkMSA9IGtleVtwb3NpdGlvbl0sIGtleVtwb3NpdGlvbiArIDFdCiAgICAgICAgZDIgPSAocmw4KHZhbHVlLCA0KSArIGQwKSBeIGQxCiAgICAgICAgZDIgPSBybDgoKH5kMikgJiAweEZGLCAzKQogICAgICAgIGQyID0gKChkMiArIGQxKSAmIDB4RkYpIF4gZDAKICAgICAgICBlbmNvZGVkWy1pbmRleCAtIDFdID0gKH5kMikgJiAweEZGCiAgICByZXR1cm4gZW5jb2RlZAoKZGVmIF94bXhvcihkYXRhOiBieXRlcywga2V5OiBieXRlcykgLT4gYnl0ZWFycmF5OgogICAgdmFsdWUgPSBfeG14b3JfdHdvKGRhdGEsIGtleSkKICAgIGxhc3RfZmxhZyA9IHZhbHVlWy0xXSBeIHZhbHVlWy0yXQogICAgZGF0YTAgPSB2YWx1ZVswXQogICAgdmFsdWVbMF0gPSAofmxhc3RfZmxhZyArIHZhbHVlWzBdKSAmIDB4RkYKICAgIHZhbHVlWzFdID0gKCh2YWx1ZVswXSBeIHZhbHVlWy0xXSBeIDI1NCkgKyB2YWx1ZVsxXSkgJiAweEZGCiAgICB2YWx1ZVsyXSA9ICh2YWx1ZVsyXSArICgobGFzdF9mbGFnIC0gZGF0YTApIF4gcmw4KHZhbHVlWzFdLCAzKSBeIDIpKSAmIDB4RkYKICAgIGZvciBpbmRleCBpbiByYW5nZShsZW4odmFsdWUpIC0gNCk6CiAgICAgICAgdGVtcCA9IHJsOCh2YWx1ZVtpbmRleCArIDJdLCAzKSBeIHZhbHVlW2luZGV4ICsgMV0gXiAoaW5kZXggKyAzKQogICAgICAgIHZhbHVlW2luZGV4ICsgM10gPSAofnRlbXAgKyB2YWx1ZVtpbmRleCArIDNdKSAmIDB4RkYKICAgIHZhbHVlWy0xXSBePSB2YWx1ZVstMl0KICAgIHZhbHVlWzBdID0gKCh2YWx1ZVswXSBeIHZhbHVlWzFdKSArIHN1bSh2YWx1ZVsxOl0pKSAmIDB4RkYKICAgIHJldHVybiB2YWx1ZQoKZGVmIF9nZW5fbWVkdXNhKHVybDogc3RyLCB1cmxfcGFyYW1zOiBNYXBwaW5nW3N0ciwgQW55XSwgZGV2aWNlczogTWFwcGluZ1tzdHIsIEFueV0sIGRhdGE6IEFueSwga2hyb25vczogaW50LCBkYXRhX3R5cGU6IHN0cikgLT4gc3RyOgogICAgY29uZmlnX2tleSA9IGIiXHhmMVkzdnZuXHhhOVx4OGQ0XHhmM1x4MWJceDA1elx4OWRbXHhlNCIKICAgIGNvbmZpZ19pdiA9IGIiXHgxZlx4ZTFcdFx4YTRceDEyUlx4ODNceGY0XHgxOFx4ZGVceDllXHgwNVx4MWFceDk2XHg5ZVx4MTIiCiAgICBzaWduX2tleSA9IGIiXHg4ZVx4YmRceGZhOFx4MDZceGVjXHhjNVx4Y2VceGU3XHg5NCNceGU2XHgwMlx4OWVceGQ4JUBceGJjXCJceDE4XHhiYn5ceGFlXHhmN1x4MWNceGI2XHg5MVx4ZjdceGFhXHg4YVx4YTJceGY1IgogICAgcHJvdG8sIHF1ZXJ5X3NtMywgYm9keV9zbTMgPSBfZ2VuX21lZHVzYV9wcm90byh1cmwsIHVybF9wYXJhbXMsIGRldmljZXMsIGRhdGEsIGtocm9ub3MsIGRhdGFfdHlwZSkKICAgIGhhc2hfcmFuZCA9IHJhbmRvbS5yYW5kaW50KDAsIDB4RkZGRkZGRkYpCiAgICB4bV9yYW5kID0gcmFuZG9tLnJhbmRpbnQoMCwgMHhGRkZGRkZGRikKICAgIGtleSwgc2VlZCA9IGdldF9rZXlfaGFzaChzaWduX2tleSwgaGFzaF9yYW5kKQogICAgbWl4ZWQgPSBfeG14b3IocHJvdG8sIGtleSkKICAgIG1peGVkID0gKDMyMCkudG9fYnl0ZXMoOCwgImxpdHRsZSIpICsgbWl4ZWQKICAgIG1peGVkID0gYnl0ZWFycmF5KG1peGVkWzo6LTFdKQogICAgZm9yIGluZGV4IGluIHJhbmdlKGxlbihtaXhlZCkpOgogICAgICAgIG1peGVkW2luZGV4XSBePSBzZWVkW35pbmRleCAmIDNdCiAgICBoYXNoX2J5dGVzID0gaGFzaF9yYW5kLnRvX2J5dGVzKDQsICJsaXR0bGUiKQogICAgY2hlY2tfYml0ID0gKChxdWVyeV9zbTNbMF0gJiA2MykgPDwgMTQpIHwgMHgxODAwMDAwMSB8ICgoYm9keV9zbTNbMF0gJiA2MykgPDwgOCkKICAgIG1peGVkID0gYiJceDM1IiArIHhtX3JhbmQudG9fYnl0ZXMoNCwgImxpdHRsZSIpICsgY2hlY2tfYml0LnRvX2J5dGVzKDQsICJsaXR0bGUiKSArIG1peGVkICsgaGFzaF9ieXRlc1syOl0KICAgIG1peGVkID0gQUVTX1YzKGNvbmZpZ19rZXksIGtocm9ub3MpLmVuY3J5cHQobWl4ZWQsIGNvbmZpZ19pdikKICAgIHZlcnNpb24gPSBieXRlcy5mcm9taGV4KCIwMyAwMCAwMCAwMCBmNyBlOCA1ZiBmYSBkNyBkNyBkYyAzYiBkNiAyYSBjOCA3MCA1NyBjZiA2MSAxOCIpCiAgICB2ZXJzaW9uX29yID0gYiIiLmpvaW4oKGludC5mcm9tX2J5dGVzKHZlcnNpb25baTppICsgNF0sICJsaXR0bGUiKSBeIGtocm9ub3MpLnRvX2J5dGVzKDQsICJsaXR0bGUiKSBmb3IgaSBpbiByYW5nZSgwLCAyMCwgNCkpCiAgICByZXR1cm4gYmFzZTY0LmI2NGVuY29kZSh2ZXJzaW9uX29yICsgaGFzaF9ieXRlc1s6Ml0gKyAoMjU2KS50b19ieXRlcygyLCAibGl0dGxlIikgKyBtaXhlZCkuZGVjb2RlKCkKCmRlZiBfY29yZV9zaXhnb2QodXJsOiBzdHIsIHBhcmFtczogTWFwcGluZ1tzdHIsIEFueV0sIGRldmljZXM6IE1hcHBpbmdbc3RyLCBBbnldLCBkYXRhOiBBbnksIGhlYWRlcjogTWFwcGluZ1tzdHIsIEFueV0pIC0+IHR1cGxlW2RpY3Rbc3RyLCBzdHJdLCBzdHJdOgogICAgZGF0YV90eXBlID0gc3RyKGhlYWRlci5nZXQoImNvbnRlbnQtdHlwZSIsIGhlYWRlci5nZXQoIkNvbnRlbnQtVHlwZSIsICIiKSkpCiAgICB4Z19yYW5kID0gcmFuZG9tLnJhbmRpbnQoMCwgMHhGRkZGKQogICAgZW5jcnlwdGVkX3VybCwgdXJsX3BhcmFtcyA9IF9nZXRfcGFyYW1zX2VuY3J5cHR1cmwodXJsLCBwYXJhbXMsIGRldmljZXMpCiAgICBraHJvbm9zID0gaW50KHRpbWUudGltZSgpKQogICAgZW5jb2RlZF9xdWVyeSA9IF91cmxfZW5jb2RlKHVybF9wYXJhbXMpCiAgICB2YWx1ZXMgPSB7CiAgICAgICAgImtocm9ub3MiOiBzdHIoa2hyb25vcyksCiAgICAgICAgImxhZG9uIjogYmFzZTY0LmI2NGVuY29kZShraHJvbm9zLnRvX2J5dGVzKDQsICJiaWciKSkuZGVjb2RlKCksCiAgICAgICAgImFyZ3VzIjogYmFzZTY0LmI2NGVuY29kZShraHJvbm9zLnRvX2J5dGVzKDQsICJsaXR0bGUiKSkuZGVjb2RlKCksCiAgICAgICAgImdvcmdvbiI6IF9lbmNyeXB0X2dvcmdvbihkYXRhLCBlbmNvZGVkX3F1ZXJ5LCBraHJvbm9zLCB4Z19yYW5kLCBkYXRhX3R5cGUpLAogICAgICAgICJoZWxpb3MiOiBfZW5jcnlwdF9oZWxpb3Moa2hyb25vcywgMCksCiAgICAgICAgIm1lZHVzYSI6IF9nZW5fbWVkdXNhKGVuY3J5cHRlZF91cmwsIHVybF9wYXJhbXMsIGRldmljZXMsIGRhdGEsIGtocm9ub3MsIGRhdGFfdHlwZSksCiAgICB9CiAgICBzaWducyA9IHsKICAgICAgICAieC1sYWRvbiI6IHZhbHVlc1sibGFkb24iXSwgIngta2hyb25vcyI6IHZhbHVlc1sia2hyb25vcyJdLAogICAgICAgICJ4LWFyZ3VzIjogdmFsdWVzWyJhcmd1cyJdLCAieC1nb3Jnb24iOiB2YWx1ZXNbImdvcmdvbiJdLAogICAgICAgICJ4LWhlbGlvcyI6IHZhbHVlc1siaGVsaW9zIl0sICJ4LW1lZHVzYSI6IHZhbHVlc1sibWVkdXNhIl0sCiAgICB9CiAgICBpZiBkYXRhOgogICAgICAgIHNpZ25zWyJ4LXNzLXN0dWIiXSA9IF9qc29uX2JvZHlfbWQ1KGRhdGEsIGRhdGFfdHlwZSkKICAgIHJlc3VsdF9oZWFkZXJzID0ge3N0cihrZXkpLmxvd2VyKCk6IHN0cih2YWx1ZSkgZm9yIGtleSwgdmFsdWUgaW4gaGVhZGVyLml0ZW1zKCl9CiAgICByZXN1bHRfaGVhZGVycy51cGRhdGUoc2lnbnMpCiAgICBpZiBkZXZpY2VzLmdldCgidWEiKToKICAgICAgICByZXN1bHRfaGVhZGVyc1sidXNlci1hZ2VudCJdID0gc3RyKGRldmljZXNbInVhIl0pCiAgICByZXN1bHRfaGVhZGVyc1sieC10dC1kdCJdID0gc3RyKGRldmljZXMuZ2V0KCJ4X3R0X2R0IiwgIiIpKQogICAgcmV0dXJuIHJlc3VsdF9oZWFkZXJzLCBlbmNyeXB0ZWRfdXJsCgpkZWYgX2RldmljZV9jb25maWcoY29uZmlnOiBNYXBwaW5nW3N0ciwgQW55XSkgLT4gZGljdFtzdHIsIHN0cl06CiAgICBkZXZpY2VfaWQgPSBfdGV4dChjb25maWcuZ2V0KCJkZXZpY2VfaWQiKSkKICAgIGluc3RhbGxfaWQgPSBfdGV4dChjb25maWcuZ2V0KCJpbnN0YWxsX2lkIikpCiAgICBpZiBub3QgZGV2aWNlX2lkIG9yIG5vdCBpbnN0YWxsX2lkOgogICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigi57y65bCR57qi5p6cIGRldmljZV9pZC9pbnN0YWxsX2lkIOmFjee9riIpCiAgICByZXR1cm4gewogICAgICAgICJkZXZpY2VfaWQiOiBkZXZpY2VfaWQsICJpaWQiOiBpbnN0YWxsX2lkLCAiaW5zdGFsbF9pZCI6IGluc3RhbGxfaWQsCiAgICAgICAgImRldmljZV9icmFuZCI6ICJSZWRtaSIsICJkZXZpY2VfbW9kZWwiOiAiMjUwNTNSVDQ3QyIsICJkZXZpY2VfdHlwZSI6ICIyNTA1M1JUNDdDIiwKICAgICAgICAiZGV2aWNlX21hbnVmYWN0dXJlciI6ICJYaWFvbWkiLCAib3NfdmVyc2lvbiI6ICIxNiIsICJ2ZXJzaW9uX25hbWUiOiAiNy4xLjMuMzIiLAogICAgICAgICJ4X3R0X2R0IjogX3RleHQoY29uZmlnLmdldCgieF90dF9kdCIpKSwKICAgICAgICAic2VjX2RldmljZV90b2tlbiI6IF90ZXh0KGNvbmZpZy5nZXQoInNlY19kZXZpY2VfdG9rZW4iKSksCiAgICAgICAgImRldmljZV9zZWNfZGV2aWNlX3Rva2VuIjogX3RleHQoY29uZmlnLmdldCgiZGV2aWNlX3NlY19kZXZpY2VfdG9rZW4iKSksCiAgICAgICAgInVhIjogQVBQX1VBLAogICAgfQoKZGVmIF92aWRlb19tb2RlbCh2aWRlb19pZDogc3RyLCBjb25maWc6IE1hcHBpbmdbc3RyLCBBbnldKSAtPiBkaWN0W3N0ciwgQW55XToKICAgIGRldmljZXMgPSBfZGV2aWNlX2NvbmZpZyhjb25maWcpCiAgICBwYXJhbXMgPSB7CiAgICAgICAgImlpZCI6IGRldmljZXNbImluc3RhbGxfaWQiXSwKICAgICAgICAiZGV2aWNlX2lkIjogZGV2aWNlc1siZGV2aWNlX2lkIl0sCiAgICAgICAgImFjIjogIndpZmkiLAogICAgICAgICJjaGFubmVsIjogInVwZGF0ZV82NCIsCiAgICAgICAgImFpZCI6ICI4NjYyIiwKICAgICAgICAiYXBwX25hbWUiOiAibm92ZWxyZWFkIiwKICAgICAgICAidmVyc2lvbl9jb2RlIjogIjcxMzMyIiwKICAgICAgICAidmVyc2lvbl9uYW1lIjogIjcuMS4zLjMyIiwKICAgICAgICAiZGV2aWNlX3BsYXRmb3JtIjogImFuZHJvaWQiLAogICAgICAgICJvcyI6ICJhbmRyb2lkIiwKICAgICAgICAic3NtaXgiOiAiYSIsCiAgICAgICAgImRldmljZV90eXBlIjogIjI1MDUzUlQ0N0MiLAogICAgICAgICJkZXZpY2VfYnJhbmQiOiAiUmVkbWkiLAogICAgICAgICJsYW5ndWFnZSI6ICJ6aCIsCiAgICAgICAgIm9zX2FwaSI6ICIzNiIsCiAgICAgICAgIm9zX3ZlcnNpb24iOiAiMTYiLAogICAgICAgICJtYW5pZmVzdF92ZXJzaW9uX2NvZGUiOiAiNzEzMzIiLAogICAgICAgICJyZXNvbHV0aW9uIjogIjEyODAqMjc3MiIsCiAgICAgICAgImRwaSI6ICI1MjAiLAogICAgICAgICJ1cGRhdGVfdmVyc2lvbl9jb2RlIjogIjcxMzMyIiwKICAgICAgICAiaG9zdF9hYmkiOiAiYXJtNjQtdjhhIiwKICAgICAgICAiZHJhZ29uX2RldmljZV90eXBlIjogInBob25lIiwKICAgICAgICAicHZfcGxheWVyIjogIjcxMzMyIiwKICAgICAgICAiY29tcGxpYW5jZV9zdGF0dXMiOiAiMCIsCiAgICAgICAgIm5lZWRfcGVyc29uYWxfcmVjb21tZW5kIjogIjEiLAogICAgICAgICJwbGF5ZXJfc29fbG9hZCI6ICIxIiwKICAgICAgICAiaXNfYW5kcm9pZF9wYWRfc2NyZWVuIjogIjAiLAogICAgfQogICAgcGF5bG9hZCA9IHsKICAgICAgICAiYml6X3BhcmFtIjogewogICAgICAgICAgICAiZGV0YWlsX3BhZ2VfdmVyc2lvbiI6IDAsCiAgICAgICAgICAgICJkZXZpY2VfbGV2ZWwiOiAzLAogICAgICAgICAgICAiZGlzYWJsZV9kaWdnX3N0YXQiOiBGYWxzZSwKICAgICAgICAgICAgIm5lZWRfYWxsX3ZpZGVvX2RlZmluaXRpb24iOiBUcnVlLAogICAgICAgICAgICAibmVlZF9tcDRfYWxpZ24iOiBGYWxzZSwKICAgICAgICAgICAgInVzZV9vc19wbGF5ZXIiOiBGYWxzZSwKICAgICAgICAgICAgInVzZV9zZXJ2ZXJfZG5zIjogRmFsc2UsCiAgICAgICAgICAgICJ2aWRlb19wbGF0Zm9ybSI6IDEwMjQsCiAgICAgICAgfSwKICAgICAgICAibWl4ZWRfdmlkZW9faWRfbWFwIjogeyIxMDA0IjogW3ZpZGVvX2lkXX0sCiAgICB9CiAgICByZXF1ZXN0X2hlYWRlcnMgPSB7CiAgICAgICAgIlVzZXItQWdlbnQiOiBBUFBfVUEsCiAgICAgICAgIkFjY2VwdCI6ICJhcHBsaWNhdGlvbi9qc29uOyBjaGFyc2V0PXV0Zi04LGFwcGxpY2F0aW9uL3gtcHJvdG9idWYiLAogICAgICAgICJDb250ZW50LVR5cGUiOiAiYXBwbGljYXRpb24vanNvbjsgY2hhcnNldD1VVEYtOCIsCiAgICAgICAgIngteHMtZnJvbS13ZWIiOiAiMCIsCiAgICAgICAgIngtc3MtcmVxLXRpY2tldCI6IHN0cihpbnQodGltZS50aW1lKCkgKiAxMDAwKSksCiAgICAgICAgIngtdHQtcmVxdWVzdC10YWciOiAidD0wO249MCIsCiAgICAgICAgInNkay12ZXJzaW9uIjogIjIiLAogICAgICAgICJwYXNzcG9ydC1zZGstdmVyc2lvbiI6ICI1MDU2MSIsCiAgICAgICAgIngtdmMtYmR0dXJpbmctc2RrLXZlcnNpb24iOiAiMy43LjIuY24iLAogICAgfQogICAgaWYgZGV2aWNlcy5nZXQoImNvb2tpZSIpOgogICAgICAgIHJlcXVlc3RfaGVhZGVyc1siQ29va2llIl0gPSBkZXZpY2VzWyJjb29raWUiXQogICAgc2lnbmVkX2hlYWRlcnMsIHNpZ25lZF91cmwgPSBfY29yZV9zaXhnb2QoCiAgICAgICAgVklERU9fVVJMLAogICAgICAgIHBhcmFtcywKICAgICAgICBkZXZpY2VzLAogICAgICAgIHBheWxvYWQsCiAgICAgICAgcmVxdWVzdF9oZWFkZXJzLAogICAgKQogICAgYm9keSA9IGpzb24uZHVtcHMocGF5bG9hZCwgZW5zdXJlX2FzY2lpPUZhbHNlLCBzZXBhcmF0b3JzPSgiLCIsICI6IikpLmVuY29kZSgidXRmLTgiKQogICAgcmVzcG9uc2UgPSByZXF1ZXN0cy5wb3N0KAogICAgICAgIHNpZ25lZF91cmwsCiAgICAgICAgaGVhZGVycz1zaWduZWRfaGVhZGVycywKICAgICAgICBkYXRhPWJvZHksCiAgICAgICAgdGltZW91dD0zMCwKICAgICkKICAgIHJlc3BvbnNlX2RhdGEgPSBfanNvbl9yZXNwb25zZShyZXNwb25zZSkKICAgIGRhdGEgPSByZXNwb25zZV9kYXRhLmdldCgiZGF0YSIpIG9yIHt9CiAgICBpZiBub3QgaXNpbnN0YW5jZShkYXRhLCBNYXBwaW5nKToKICAgICAgICByYWlzZSBIb25nZ3VvUGx1Z2luRXJyb3IoInZpZGVvX21vZGVsIOaVsOaNruS4uuepuiIpCiAgICBlbnRyeTogQW55ID0gZGF0YS5nZXQodmlkZW9faWQpCiAgICBpZiBlbnRyeSBpcyBOb25lOgogICAgICAgIGZvciB2YWx1ZSBpbiBkYXRhLnZhbHVlcygpOgogICAgICAgICAgICBpZiBpc2luc3RhbmNlKHZhbHVlLCBNYXBwaW5nKToKICAgICAgICAgICAgICAgIGVudHJ5ID0gdmFsdWUKICAgICAgICAgICAgICAgIGJyZWFrCiAgICAgICAgICAgIGlmIGlzaW5zdGFuY2UodmFsdWUsIGxpc3QpIGFuZCB2YWx1ZSBhbmQgaXNpbnN0YW5jZSh2YWx1ZVswXSwgTWFwcGluZyk6CiAgICAgICAgICAgICAgICBlbnRyeSA9IHZhbHVlWzBdCiAgICAgICAgICAgICAgICBicmVhawogICAgaWYgbm90IGlzaW5zdGFuY2UoZW50cnksIE1hcHBpbmcpOgogICAgICAgIGVudHJ5ID0gZGF0YQogICAgcmF3X21vZGVsID0gZW50cnkuZ2V0KCJ2aWRlb19tb2RlbCIpIGlmIGlzaW5zdGFuY2UoZW50cnksIE1hcHBpbmcpIGVsc2UgTm9uZQogICAgaWYgcmF3X21vZGVsIGlzIE5vbmU6CiAgICAgICAgcmF3X21vZGVsID0gZGF0YS5nZXQoInZpZGVvX21vZGVsIikKICAgIGlmIGlzaW5zdGFuY2UocmF3X21vZGVsLCBzdHIpOgogICAgICAgIHRyeToKICAgICAgICAgICAgcmF3X21vZGVsID0ganNvbi5sb2FkcyhyYXdfbW9kZWwpCiAgICAgICAgZXhjZXB0IFZhbHVlRXJyb3IgYXMgZXhjOgogICAgICAgICAgICByYWlzZSBIb25nZ3VvUGx1Z2luRXJyb3IoInZpZGVvX21vZGVsIEpTT04g5peg5pWIIikgZnJvbSBleGMKICAgIGlmIG5vdCBpc2luc3RhbmNlKHJhd19tb2RlbCwgTWFwcGluZyk6CiAgICAgICAgcmFpc2UgSG9uZ2d1b1BsdWdpbkVycm9yKCJ2aWRlb19tb2RlbCDkuLrnqboiKQogICAgcmV0dXJuIGRpY3QocmF3X21vZGVsKQoKZGVmIF92aWRlb19saXN0X2Zyb21fbW9kZWwobW9kZWw6IE1hcHBpbmdbc3RyLCBBbnldKSAtPiBBbnk6CiAgICBmb3Iga2V5IGluICgidmlkZW9fbGlzdCIsICJkeW5hbWljX3ZpZGVvX2xpc3QiKToKICAgICAgICBpZiBtb2RlbC5nZXQoa2V5KSBpcyBub3QgTm9uZToKICAgICAgICAgICAgcmV0dXJuIG1vZGVsW2tleV0KICAgIGR5bmFtaWMgPSBtb2RlbC5nZXQoImR5bmFtaWNfdmlkZW8iKQogICAgaWYgaXNpbnN0YW5jZShkeW5hbWljLCBNYXBwaW5nKToKICAgICAgICBmb3Iga2V5IGluICgiZHluYW1pY192aWRlb19saXN0IiwgInZpZGVvX2xpc3QiLCAibGlzdCIpOgogICAgICAgICAgICBpZiBkeW5hbWljLmdldChrZXkpIGlzIG5vdCBOb25lOgogICAgICAgICAgICAgICAgcmV0dXJuIGR5bmFtaWNba2V5XQogICAgdmlkZW9faW5mbyA9IG1vZGVsLmdldCgidmlkZW9faW5mbyIpCiAgICBpZiBpc2luc3RhbmNlKHZpZGVvX2luZm8sIE1hcHBpbmcpOgogICAgICAgIGRhdGEgPSB2aWRlb19pbmZvLmdldCgiZGF0YSIpCiAgICAgICAgaWYgaXNpbnN0YW5jZShkYXRhLCBNYXBwaW5nKToKICAgICAgICAgICAgcmV0dXJuIF92aWRlb19saXN0X2Zyb21fbW9kZWwoZGF0YSkKICAgIGRhdGEgPSBtb2RlbC5nZXQoImRhdGEiKQogICAgaWYgaXNpbnN0YW5jZShkYXRhLCBNYXBwaW5nKToKICAgICAgICByZXR1cm4gX3ZpZGVvX2xpc3RfZnJvbV9tb2RlbChkYXRhKQogICAgcmV0dXJuIE5vbmUKCgpfUVVBTElUWV9PUkRFUiA9ICgiMjE2MCIsICIxNDQwIiwgIjEwODAiLCAiNzIwIiwgIjU3NiIsICI1NDAiLCAiNDgwIiwgIjM2MCIpCgpkZWYgX2ludCh2YWx1ZTogQW55KSAtPiBpbnQ6CiAgICBtYXRjaCA9IHJlLnNlYXJjaChyIlxkKyIsIF90ZXh0KHZhbHVlKSkKICAgIHJldHVybiBpbnQobWF0Y2guZ3JvdXAoKSkgaWYgbWF0Y2ggZWxzZSAwCgpkZWYgX3F1YWxpdHkodmFsdWU6IEFueSkgLT4gc3RyOgogICAgdGV4dCA9IF90ZXh0KHZhbHVlKS5sb3dlcigpCiAgICBtYXRjaCA9IHJlLnNlYXJjaChyIigyMTYwfDE0NDB8MTA4MHw3MjB8NTc2fDU0MHw0ODB8MzYwKSIsIHRleHQpCiAgICByZXR1cm4gbWF0Y2guZ3JvdXAoMSkgaWYgbWF0Y2ggZWxzZSAiMTA4MCIKCmRlZiBfc2VsZWN0X3F1YWxpdHkodmlkZW9fbGlzdDogQW55LCB3YW50ZWQ6IHN0ciA9ICIxMDgwIikgLT4gdHVwbGVbc3RyLCBkaWN0W3N0ciwgQW55XV06CiAgICBkZWYgcm93c19mcm9tKHZhbHVlOiBBbnksIGhpbnRlZF9xdWFsaXR5OiBzdHIgPSAiIikgLT4gbGlzdFt0dXBsZVtzdHIsIGRpY3Rbc3RyLCBBbnldXV06CiAgICAgICAgaWYgaXNpbnN0YW5jZSh2YWx1ZSwgbGlzdCk6CiAgICAgICAgICAgIHJlc3VsdDogbGlzdFt0dXBsZVtzdHIsIGRpY3Rbc3RyLCBBbnldXV0gPSBbXQogICAgICAgICAgICBmb3IgaXRlbSBpbiB2YWx1ZToKICAgICAgICAgICAgICAgIHJlc3VsdC5leHRlbmQocm93c19mcm9tKGl0ZW0sIGhpbnRlZF9xdWFsaXR5KSkKICAgICAgICAgICAgcmV0dXJuIHJlc3VsdAogICAgICAgIGlmIG5vdCBpc2luc3RhbmNlKHZhbHVlLCBNYXBwaW5nKToKICAgICAgICAgICAgcmV0dXJuIFtdCiAgICAgICAgaWYgYW55KAogICAgICAgICAgICBrZXkgaW4gdmFsdWUKICAgICAgICAgICAgZm9yIGtleSBpbiAoCiAgICAgICAgICAgICAgICAibWFpbl91cmwiLAogICAgICAgICAgICAgICAgImJhY2t1cF91cmwiLAogICAgICAgICAgICAgICAgImJhY2t1cF91cmxfMSIsCiAgICAgICAgICAgICAgICAicGxheV9hZGRyIiwKICAgICAgICAgICAgICAgICJzcGFkZV9hIiwKICAgICAgICAgICAgICAgICJlbmNyeXB0X2luZm8iLAogICAgICAgICAgICApCiAgICAgICAgKToKICAgICAgICAgICAgcmV0dXJuIFsoaGludGVkX3F1YWxpdHksIGRpY3QodmFsdWUpKV0KICAgICAgICByZXN1bHQgPSBbXQogICAgICAgIGZvciBrZXksIGl0ZW0gaW4gdmFsdWUuaXRlbXMoKToKICAgICAgICAgICAgaWYga2V5IGluIHsiZHluYW1pY192aWRlbyIsICJ2aWRlb19pbmZvIiwgImRhdGEifSBhbmQgaXNpbnN0YW5jZShpdGVtLCBNYXBwaW5nKToKICAgICAgICAgICAgICAgIHJlc3VsdC5leHRlbmQocm93c19mcm9tKGl0ZW0sIGhpbnRlZF9xdWFsaXR5KSkKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIGlmIGtleSBpbiB7InZpZGVvX2xpc3QiLCAiZHluYW1pY192aWRlb19saXN0IiwgImxpc3QifToKICAgICAgICAgICAgICAgIHJlc3VsdC5leHRlbmQocm93c19mcm9tKGl0ZW0sIF9xdWFsaXR5KGtleSkpKQogICAgICAgICAgICAgICAgY29udGludWUKICAgICAgICAgICAgaWYgaXNpbnN0YW5jZShpdGVtLCAoTWFwcGluZywgbGlzdCkpOgogICAgICAgICAgICAgICAgcmVzdWx0LmV4dGVuZChyb3dzX2Zyb20oaXRlbSwgX3F1YWxpdHkoa2V5KSkpCiAgICAgICAgcmV0dXJuIHJlc3VsdAoKICAgIGNhbmRpZGF0ZXMgPSByb3dzX2Zyb20odmlkZW9fbGlzdCkKICAgIHJvd3M6IGRpY3Rbc3RyLCBkaWN0W3N0ciwgQW55XV0gPSB7fQogICAgZm9yIGhpbnRlZF9xdWFsaXR5LCBpdGVtIGluIGNhbmRpZGF0ZXM6CiAgICAgICAgZGVmaW5pdGlvbiA9IF9xdWFsaXR5KAogICAgICAgICAgICBpdGVtLmdldCgiZGVmaW5pdGlvbiIpCiAgICAgICAgICAgIG9yIGl0ZW0uZ2V0KCJ2aGVpZ2h0IikKICAgICAgICAgICAgb3IgKGl0ZW0uZ2V0KCJ2aWRlb19tZXRhIikgb3Ige30pLmdldCgiZGVmaW5pdGlvbiIpCiAgICAgICAgICAgIG9yIGhpbnRlZF9xdWFsaXR5CiAgICAgICAgKQogICAgICAgIHJvd3NbZGVmaW5pdGlvbl0gPSBpdGVtCiAgICBpZiBub3Qgcm93czoKICAgICAgICByYWlzZSBIb25nZ3VvUGx1Z2luRXJyb3IoIuaSreaUvuaooeWei+ayoeaciea4heaZsOW6piIpCiAgICByZXF1ZXN0ZWQgPSBfcXVhbGl0eSh3YW50ZWQpCiAgICBvcmRlciA9IFtyZXF1ZXN0ZWRdICsgW2l0ZW0gZm9yIGl0ZW0gaW4gX1FVQUxJVFlfT1JERVIgaWYgaXRlbSAhPSByZXF1ZXN0ZWRdCiAgICBmb3IgZGVmaW5pdGlvbiBpbiBvcmRlcjoKICAgICAgICBpZiBkZWZpbml0aW9uIGluIHJvd3M6CiAgICAgICAgICAgIHJldHVybiBkZWZpbml0aW9uLCByb3dzW2RlZmluaXRpb25dCiAgICBkZWZpbml0aW9uID0gbWF4KHJvd3MsIGtleT1sYW1iZGEgaXRlbTogX2ludChpdGVtKSkKICAgIHJldHVybiBkZWZpbml0aW9uLCByb3dzW2RlZmluaXRpb25dCgpkZWYgX2ZhbGxiYWNrX2FwaV92YWx1ZSh2YWx1ZTogQW55KSAtPiBzdHI6CiAgICBpZiBpc2luc3RhbmNlKHZhbHVlLCBNYXBwaW5nKToKICAgICAgICByZXR1cm4gX2ZpcnN0KAogICAgICAgICAgICB2YWx1ZS5nZXQoImZhbGxiYWNrX2FwaSIpLAogICAgICAgICAgICB2YWx1ZS5nZXQoInVybCIpLAogICAgICAgICAgICB2YWx1ZS5nZXQoImFwaSIpLAogICAgICAgICAgICB2YWx1ZS5nZXQoImRhdGEiKSwKICAgICAgICApCiAgICBpZiBpc2luc3RhbmNlKHZhbHVlLCAobGlzdCwgdHVwbGUpKToKICAgICAgICBmb3IgaXRlbSBpbiB2YWx1ZToKICAgICAgICAgICAgcmVzdWx0ID0gX2ZhbGxiYWNrX2FwaV92YWx1ZShpdGVtKQogICAgICAgICAgICBpZiByZXN1bHQ6CiAgICAgICAgICAgICAgICByZXR1cm4gcmVzdWx0CiAgICAgICAgcmV0dXJuICIiCiAgICB0ZXh0ID0gX3RleHQodmFsdWUpCiAgICBpZiB0ZXh0LnN0YXJ0c3dpdGgoInsiKToKICAgICAgICB0cnk6CiAgICAgICAgICAgIGRlY29kZWQgPSBqc29uLmxvYWRzKHRleHQpCiAgICAgICAgZXhjZXB0IFZhbHVlRXJyb3I6CiAgICAgICAgICAgIGRlY29kZWQgPSB7fQogICAgICAgIGlmIGRlY29kZWQ6CiAgICAgICAgICAgIHJldHVybiBfZmFsbGJhY2tfYXBpX3ZhbHVlKGRlY29kZWQpCiAgICByZXR1cm4gdGV4dCBpZiBsZW4odGV4dCkgPiAxMCBlbHNlICIiCgpkZWYgX2RlY3J5cHRfc3BhZGVfdXJsKHZhbHVlOiBzdHIsIGtleV9zZWVkOiBieXRlcykgLT4gc3RyOgogICAgcmF3ID0gX2I2NCh2YWx1ZSkKICAgIGlmIGxlbihyYXcpIDwgMjAgb3IgcmF3WzBdICE9IDB4QTggb3IgcmF3WzI6NF0gIT0gYiJceDAxXHgwMCI6CiAgICAgICAgcmFpc2UgSG9uZ2d1b1BsdWdpbkVycm9yKCJzcGFkZSBVUkwg5aS05peg5pWIIikKICAgIGNpcGhlcl9kYXRhID0gcmF3WzQgOiBsZW4ocmF3KSAtIChsZW4ocmF3KSAtIDQpICUgMTZdCiAgICBpZiBub3QgY2lwaGVyX2RhdGE6CiAgICAgICAgcmFpc2UgSG9uZ2d1b1BsdWdpbkVycm9yKCJzcGFkZSBVUkwg5a+G5paH5Li656m6IikKICAgIGNvbnN0YW50cyA9IGJ5dGVzLmZyb21oZXgoCiAgICAgICAgIjRkZDRjMmU2YjgzMTYyMDkwZTUyYjNjN2E2NzMzYmE0IgogICAgICAgICIxY2IyNDYyYjgyOWFiNThhMTk2YjM5ZGI1NzE3NzUyNCIKICAgICAgICAiZjQ5YmFmN2YwOGU4ZDY4ZDI2YTcyZTM3YzFhOTVhMmYiCiAgICAgICAgIjFmMDVhNTE4OTJhZWYyOTQ5NzMyYjYyYTM4YWFkZDU4IgogICAgKQogICAgZmlyc3QgPSBoYXNobGliLnNoYTUxMihrZXlfc2VlZCkuZGlnZXN0KCkKICAgIHNlY29uZCA9IGhhc2hsaWIuc2hhNTEyKGZpcnN0ICsgY29uc3RhbnRzKS5kaWdlc3QoKQogICAgcGxhaW50ZXh0ID0gX2Flc19jYmNfZGVjcnlwdChzZWNvbmRbOjE2XSwgc2Vjb25kWzE2OjMyXSwgY2lwaGVyX2RhdGEpCiAgICBpZiBwbGFpbnRleHQ6CiAgICAgICAgcGFkZGluZyA9IHBsYWludGV4dFstMV0KICAgICAgICBpZiAxIDw9IHBhZGRpbmcgPD0gMTYgYW5kIHBhZGRpbmcgPD0gbGVuKHBsYWludGV4dCk6CiAgICAgICAgICAgIHBsYWludGV4dCA9IHBsYWludGV4dFs6LXBhZGRpbmddCiAgICByZXR1cm4gcGxhaW50ZXh0LnJzdHJpcChiIlwwIikuZGVjb2RlKCJ1dGYtOCIsIGVycm9ycz0icmVwbGFjZSIpCgpkZWYgX3BhcnNlX3JlZih2YWx1ZTogc3RyLCBwcmVmaXg6IHN0cikgLT4gc3RyOgogICAgaWYgbm90IHZhbHVlLnN0YXJ0c3dpdGgocHJlZml4KToKICAgICAgICByYWlzZSBIb25nZ3VvUGx1Z2luRXJyb3IoIuaSreaUvuW8leeUqOaXoOaViCIpCiAgICByYXcgPSB2YWx1ZVtsZW4ocHJlZml4KSA6XQogICAgaWYgbm90IHJhdyBvciBub3QgX1ZJREVPX0lELmZ1bGxtYXRjaChyYXcpOgogICAgICAgIHJhaXNlIEhvbmdndW9QbHVnaW5FcnJvcigi5pKt5pS+5byV55So5qC85byP5peg5pWIIikKICAgIHJldHVybiByYXcKCmRlZiBfa2V5X3NlZWRfZnJvbV9tb2RlbChtb2RlbDogTWFwcGluZ1tzdHIsIEFueV0pIC0+IGJ5dGVzOgogICAgdmFsdWUgPSBfdGV4dChtb2RlbC5nZXQoImtleV9zZWVkIikpCiAgICBpZiB2YWx1ZToKICAgICAgICByZXR1cm4gX2I2NCh2YWx1ZSkKICAgIGZvciBrZXkgaW4gKCJkeW5hbWljX3ZpZGVvIiwgInZpZGVvX2luZm8iLCAiZGF0YSIpOgogICAgICAgIG5lc3RlZCA9IG1vZGVsLmdldChrZXkpCiAgICAgICAgaWYgaXNpbnN0YW5jZShuZXN0ZWQsIE1hcHBpbmcpOgogICAgICAgICAgICByZXN1bHQgPSBfa2V5X3NlZWRfZnJvbV9tb2RlbChuZXN0ZWQpCiAgICAgICAgICAgIGlmIHJlc3VsdDoKICAgICAgICAgICAgICAgIHJldHVybiByZXN1bHQKICAgIHJldHVybiBiIiIKZGVmIF9wYWdlKHVybCk6CiAgICBsYXN0X2VyciA9IE5vbmUKICAgIGZvciBhdHRlbXB0IGluIHJhbmdlKDMpOgogICAgICAgIHRyeToKICAgICAgICAgICAgciA9IHJlcXVlc3RzLmdldCgKICAgICAgICAgICAgICAgIHVybCwKICAgICAgICAgICAgICAgIGhlYWRlcnM9ewogICAgICAgICAgICAgICAgICAgICJVc2VyLUFnZW50IjogVUEsCiAgICAgICAgICAgICAgICAgICAgIkFjY2VwdC1MYW5ndWFnZSI6ICJ6aC1DTix6aDtxPTAuOSIsCiAgICAgICAgICAgICAgICAgICAgIkFjY2VwdCI6ICJ0ZXh0L2h0bWwsYXBwbGljYXRpb24veGh0bWwreG1sO3E9MC45LCovKjtxPTAuOCIsCiAgICAgICAgICAgICAgICAgICAgIkNhY2hlLUNvbnRyb2wiOiAibm8tY2FjaGUiLAogICAgICAgICAgICAgICAgfSwKICAgICAgICAgICAgICAgIHRpbWVvdXQ9MzAsCiAgICAgICAgICAgICkKICAgICAgICAgICAgci5yYWlzZV9mb3Jfc3RhdHVzKCkKICAgICAgICAgICAgci5lbmNvZGluZyA9IHIuZW5jb2Rpbmcgb3IgInV0Zi04IgogICAgICAgICAgICBpZiBub3Qgci50ZXh0IG9yICJfUk9VVEVSX0RBVEEiIG5vdCBpbiByLnRleHQ6CiAgICAgICAgICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoImVtcHR5IG9yIGludmFsaWQgcGFnZSIpCiAgICAgICAgICAgIHJldHVybiByLnRleHQKICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGVycjoKICAgICAgICAgICAgbGFzdF9lcnIgPSBlcnIKICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgdGltZS5zbGVlcCgwLjYgKiAoYXR0ZW1wdCArIDEpKQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICAgICAgcGFzcwogICAgcmFpc2UgUnVudGltZUVycm9yKCJwYWdlIGZldGNoIGZhaWxlZDogJXMiICUgbGFzdF9lcnIpCgpkZWYgX2RhdGEodXJsKToKICAgIGh0bWwgPSBfcGFnZSh1cmwpCiAgICBtID0gcmUuc2VhcmNoKHIiKD86d2luZG93XC4pP19ST1VURVJfREFUQVxzKj1ccyoiLCBodG1sKQogICAgaWYgbm90IG06CiAgICAgICAgcmV0dXJuIHt9CiAgICB0cnk6CiAgICAgICAgcmV0dXJuIGpzb24uSlNPTkRlY29kZXIoKS5yYXdfZGVjb2RlKGh0bWxbbS5lbmQoKTpdKVswXQogICAgZXhjZXB0IChWYWx1ZUVycm9yLCBUeXBlRXJyb3IpOgogICAgICAgIHJldHVybiB7fQoKZGVmIF9pdGVtKHgpOgogICAgeCA9IHggb3Ige30KICAgIHZkID0geC5nZXQoInZpZGVvX2RhdGEiKSBpZiBpc2luc3RhbmNlKHguZ2V0KCJ2aWRlb19kYXRhIiksIGRpY3QpIGVsc2UgeAogICAgc2lkID0gc3RyKAogICAgICAgIHZkLmdldCgic2VyaWVzX2lkIikKICAgICAgICBvciB4LmdldCgic2VyaWVzX2lkIikKICAgICAgICBvciB4LmdldCgia2V5d29yZCIpCiAgICAgICAgb3IgdmQuZ2V0KCJrZXl3b3JkIikKICAgICAgICBvciAiIgogICAgKQogICAgbmFtZSA9IHN0cigKICAgICAgICB2ZC5nZXQoInNlcmllc190aXRsZSIpCiAgICAgICAgb3IgdmQuZ2V0KCJzZXJpZXNfbmFtZSIpCiAgICAgICAgb3IgeC5nZXQoInNlcmllc19uYW1lIikKICAgICAgICBvciB4LmdldCgibmFtZSIpCiAgICAgICAgb3IgIuacquWRveWQjSIKICAgICkKICAgIGNvdW50ID0gdmQuZ2V0KCJlcGlzb2RlX2NudCIpIG9yIHguZ2V0KCJlcGlzb2RlX2NudCIpIG9yIDAKICAgIHBpYyA9IHN0cih2ZC5nZXQoInNlcmllc19jb3ZlciIpIG9yIHguZ2V0KCJzZXJpZXNfY292ZXIiKSBvciAiIikKICAgIGludHJvID0gc3RyKHZkLmdldCgic2VyaWVzX2ludHJvIikgb3IgeC5nZXQoInNlcmllc19pbnRybyIpIG9yICIiKQogICAgcmV0dXJuIHsKICAgICAgICAidm9kX2lkIjogc2lkLAogICAgICAgICJ2b2RfbmFtZSI6IG5hbWUsCiAgICAgICAgInZvZF9waWMiOiBwaWMsCiAgICAgICAgInZvZF9yZW1hcmtzIjogKCLlhaglc+mbhiIgJSBjb3VudCkgaWYgY291bnQgZWxzZSAiIiwKICAgICAgICAidm9kX2NvbnRlbnQiOiBpbnRybywKICAgIH0KCmRlZiBfY2F0X2l0ZW0oeCk6CiAgICByZXR1cm4gX2l0ZW0oeCkKCmRlZiBfZmlsdGVyX2dyb3VwKGtleSwgbmFtZSwgdmFsdWVzKToKICAgIHJldHVybiB7ImtleSI6IGtleSwgIm5hbWUiOiBuYW1lLCAidmFsdWUiOiBbeyJuIjogbiwgInYiOiB2fSBmb3IgbiwgdiBpbiB2YWx1ZXNdfQoKCmRlZiBfc2VhcmNoX2xvYWRlcihrZXk6IHN0cikgLT4gZGljdDoKICAgICIiIuaLieWPluaQnOe0oumhtSBsb2FkZXJEYXRh77yM5aSx6LSl6YeN6K+V44CCIiIiCiAgICBsYXN0ID0ge30KICAgIGZvciBhdHRlbXB0IGluIHJhbmdlKDMpOgogICAgICAgIHRyeToKICAgICAgICAgICAgZGF0YSA9IF9kYXRhKFNJVEUgKyAiL3NlYXJjaC8iICsgcXVvdGUoc3RyKGtleSksIHNhZmU9IiIpKQogICAgICAgICAgICBwYWdlID0gKGRhdGEuZ2V0KCJsb2FkZXJEYXRhIikgb3Ige30pLmdldCgic2VhcmNoXyhrZXl3b3JkKS9wYWdlIikgb3Ige30KICAgICAgICAgICAgaWYgcGFnZS5nZXQoInNlYXJjaExpc3QiKToKICAgICAgICAgICAgICAgIHJldHVybiBwYWdlCiAgICAgICAgICAgIGxhc3QgPSBwYWdlIG9yIGxhc3QKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICBwYXNzCiAgICAgICAgdHJ5OgogICAgICAgICAgICB0aW1lLnNsZWVwKDAuNSAqIChhdHRlbXB0ICsgMSkpCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgcGFzcwogICAgcmV0dXJuIGxhc3QKCgpkZWYgX3NlYXJjaF9ieV9rZXl3b3JkcyhrZXl3b3JkcywgcGFnZTogaW50KSAtPiBkaWN0OgogICAgIiIi5aSa5YWz6ZSu6K+N6L2u5o2i77ya56ysIE4g6aG155So56ysIE4g5Liq5YWz6ZSu6K+N77yI5b6q546v77yJ77yM6YG/5YWN5pCc57Si5peg5rOV57+76aG144CCIiIiCiAgICBwYWdlID0gbWF4KDEsIGludChwYWdlIG9yIDEpKQogICAga3dzID0gW2sgZm9yIGsgaW4gKGtleXdvcmRzIG9yIFtdKSBpZiBrXQogICAgaWYgbm90IGt3czoKICAgICAgICBrd3MgPSBbIuefreWJpyJdCiAgICBrZXkgPSBrd3NbKHBhZ2UgLSAxKSAlIGxlbihrd3MpXQogICAgcCA9IF9zZWFyY2hfbG9hZGVyKGtleSkKICAgIHJvd3MgPSBwLmdldCgic2VhcmNoTGlzdCIpIG9yIFtdCiAgICAjIOWOu+mHjeepuiBpZAogICAgb3V0ID0gW10KICAgIHNlZW4gPSBzZXQoKQogICAgZm9yIHggaW4gcm93czoKICAgICAgICBpdCA9IF9pdGVtKHgpCiAgICAgICAgdmlkID0gc3RyKGl0LmdldCgidm9kX2lkIikgb3IgIiIpCiAgICAgICAgaWYgbm90IHZpZCBvciB2aWQgaW4gc2VlbjoKICAgICAgICAgICAgY29udGludWUKICAgICAgICBzZWVuLmFkZCh2aWQpCiAgICAgICAgb3V0LmFwcGVuZChpdCkKICAgICMg6Jma5ouf6aG15pWw77ya5YWz6ZSu6K+N5pWw77yb6Iul56uZ54K55pyJIHRvdGFsQ291bnQg5Lmf5Y+C6ICDCiAgICB0b3RhbCA9IGludChwLmdldCgidG90YWxDb3VudCIpIG9yIDApCiAgICBwYWdlY291bnQgPSBtYXgobGVuKGt3cyksICh0b3RhbCArIDkpIC8vIDEwIGlmIHRvdGFsIGVsc2UgbGVuKGt3cykpCiAgICByZXR1cm4gewogICAgICAgICJwYWdlIjogcGFnZSwKICAgICAgICAicGFnZWNvdW50IjogbWF4KDEsIHBhZ2Vjb3VudCksCiAgICAgICAgImxpbWl0IjogbGVuKG91dCksCiAgICAgICAgInRvdGFsIjogdG90YWwgb3IgbGVuKG91dCkgKiBwYWdlY291bnQsCiAgICAgICAgImxpc3QiOiBvdXQsCiAgICB9CgoKZGVmIF9jYXRlZ29yeV9sb2FkZXIocGFnZTogaW50LCBxOiBkaWN0KSAtPiBkaWN0OgogICAgIiIi5YiG57G76aG15bim6YeN6K+V77ybcGFnZT0xIOWBtuWPkeepuuWIl+ihqOaXtuWkmuivleWHoOasoeOAgiIiIgogICAgcGFnZSA9IG1heCgxLCBpbnQocGFnZSBvciAxKSkKICAgIHEgPSBkaWN0KHEgb3Ige30pCiAgICBpZiBwYWdlID4gMToKICAgICAgICBxWyJwYWdlIl0gPSBzdHIocGFnZSkKICAgIGxhc3QgPSB7fQogICAgZm9yIGF0dGVtcHQgaW4gcmFuZ2UoMyk6CiAgICAgICAgdHJ5OgogICAgICAgICAgICBkYXRhID0gX2RhdGEoU0lURSArICIvY2F0ZWdvcnk/IiArIHVybGVuY29kZShxKSkKICAgICAgICAgICAgcCA9IChkYXRhLmdldCgibG9hZGVyRGF0YSIpIG9yIHt9KS5nZXQoImNhdGVnb3J5XyQiKSBvciAoZGF0YS5nZXQoImxvYWRlckRhdGEiKSBvciB7fSkuZ2V0KCJjYXRlZ29yeV9wYWdlIikgb3Ige30KICAgICAgICAgICAgcm93cyA9IHAuZ2V0KCJyZWNvbW1lbmRMaXN0Iikgb3IgW10KICAgICAgICAgICAgaWYgcm93cyBvciBwYWdlID4gMToKICAgICAgICAgICAgICAgIHJldHVybiBwCiAgICAgICAgICAgIGxhc3QgPSBwIG9yIGxhc3QKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICBwYXNzCiAgICAgICAgdHJ5OgogICAgICAgICAgICB0aW1lLnNsZWVwKDAuNSAqIChhdHRlbXB0ICsgMSkpCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgcGFzcwogICAgcmV0dXJuIGxhc3QKCmNsYXNzIFNwaWRlcihfQmFzZVNwaWRlcik6CiAgICBkZWYgX19pbml0X18oc2VsZik6CiAgICAgICAgc2VsZi5kZXZpY2VfaWQgPSBzdHIocmFuZG9tLnJhbmRpbnQoMTAqKjE3LCAxMCoqMTggLSAxKSkKICAgICAgICBzZWxmLmluc3RhbGxfaWQgPSBzdHIocmFuZG9tLnJhbmRpbnQoMTAqKjE3LCAxMCoqMTggLSAxKSkKCiAgICBkZWYgZ2V0TmFtZShzZWxmKToKICAgICAgICByZXR1cm4gIue6ouaenOefreWJpyIKCiAgICBkZWYgaXNWaWRlb0Zvcm1hdChzZWxmLCB1cmwpOgogICAgICAgIHUgPSBzdHIodXJsIG9yICIiKS5sb3dlcigpCiAgICAgICAgcmV0dXJuICgiLm1wNCIgaW4gdSkgb3IgKCJ2aWRlb19tcDQiIGluIHUpIG9yICgibTN1OCIgaW4gdSkgb3IgKCJtaW1lX3R5cGU9dmlkZW8iIGluIHUpIG9yICgicXpub3ZlbHZvZCIgaW4gdSkKCiAgICBkZWYgbWFudWFsVmlkZW9DaGVjayhzZWxmKToKICAgICAgICByZXR1cm4gRmFsc2UKCiAgICBkZWYgZ2V0RGVwZW5kZW5jZShzZWxmKToKICAgICAgICByZXR1cm4gW10KCiAgICBkZWYgZG93bmxvYWQoc2VsZiwgcGF0aCwgdXJsKToKICAgICAgICByZXR1cm4gIiIKCiAgICBkZWYgbGl2ZUNvbnRlbnQoc2VsZik6CiAgICAgICAgcmV0dXJuIHt9CgogICAgZGVmIGlzVlBBWWFyZChzZWxmLCBmbGFnKToKICAgICAgICByZXR1cm4gRmFsc2UKCiAgICBkZWYgYWN0aW9uKHNlbGYsIGFjdGlvbik6CiAgICAgICAgcmV0dXJuICIiCgogICAgZGVmIGluaXQoc2VsZiwgZXh0ZW5kPSIiKToKICAgICAgICAjIOavj+asoea6kOWunuS+i+S9v+eUqOmaj+acuuWQiOazleiuvuWkh+agh+ivhu+8m+S4jeS+nei1lueUqOaIt+engeaciemFjee9ruOAggogICAgICAgIHRyeToKICAgICAgICAgICAgX2hnX2NhY2hlX2NsZWFudXAoRmFsc2UpCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgcGFzcwogICAgICAgIHJldHVybiBOb25lCgogICAgZGVmIGRlc3Ryb3koc2VsZik6CiAgICAgICAgdHJ5OgogICAgICAgICAgICBfaGdfY2FjaGVfY2xlYW51cChGYWxzZSkKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICBwYXNzCgogICAgZGVmIGhvbWVDb250ZW50KHNlbGYsIGZpbHRlcik6CiAgICAgICAgY2xhc3NfbGlzdCA9IFsKICAgICAgICAgICAgeyJ0eXBlX2lkIjogImFsbCIsICJ0eXBlX25hbWUiOiAi55+t5YmnIn0sCiAgICAgICAgICAgIHsidHlwZV9pZCI6ICJhaV9jb21pYyIsICJ0eXBlX25hbWUiOiAiQUnmvKvliacifSwKICAgICAgICAgICAgeyJ0eXBlX2lkIjogImxhdGVzdCIsICJ0eXBlX25hbWUiOiAi5pyA5pawIn0sCiAgICAgICAgICAgIHsidHlwZV9pZCI6ICJob3QiLCAidHlwZV9uYW1lIjogIuacgOeDrSJ9LAogICAgICAgICAgICB7InR5cGVfaWQiOiAibWFsZSIsICJ0eXBlX25hbWUiOiAi55S36aKRIn0sCiAgICAgICAgICAgIHsidHlwZV9pZCI6ICJmZW1hbGUiLCAidHlwZV9uYW1lIjogIuWls+mikSJ9LAogICAgICAgIF0KICAgICAgICBncm91cHMgPSBbCiAgICAgICAgICAgIHsia2V5IjogInRvcGljIiwgIm5hbWUiOiAi5Li76aKYIiwgInZhbHVlIjogWwogICAgICAgICAgICAgICAgeyJuIjogIuWFqOmDqCIsICJ2IjogIiJ9LCB7Im4iOiAi546w6KiAIiwgInYiOiAiY2F0ZV8xMDIxIn0sIHsibiI6ICLlpbPmgKfmiJDplb8iLCAidiI6ICJjYXRlXzEwNDgifSwKICAgICAgICAgICAgICAgIHsibiI6ICLohJHmtJ4iLCAidiI6ICJjYXRlXzI2MiJ9LCB7Im4iOiAi5aWH5bm7IiwgInYiOiAiY2F0ZV8xMDIwIn0sIHsibiI6ICLnjoTlubsiLCAidiI6ICJjYXRlXzEwMTkifSwKICAgICAgICAgICAgICAgIHsibiI6ICLlj6ToqIAiLCAidiI6ICJjYXRlXzQzOSJ9LCB7Im4iOiAi5oiY56WeIiwgInYiOiAiY2F0ZV8xMDM4In0sIHsibiI6ICLlrqvmlpciLCAidiI6ICJjYXRlXzI0NiJ9LAogICAgICAgICAgICAgICAgeyJuIjogIuS7meS+oCIsICJ2IjogImNhdGVfMTAxMyJ9LCB7Im4iOiAi5p2D6LCLIiwgInYiOiAiY2F0ZV8xMDQ3In0sIHsibiI6ICLnp43nlLAiLCAidiI6ICJjYXRlXzExODAifSwKICAgICAgICAgICAgICAgIHsibiI6ICLlubTku6PniLHmg4UiLCAidiI6ICJjYXRlXzEwMjIifSwgeyJuIjogIuaCrOeWkSIsICJ2IjogImNhdGVfMTY1In0sIHsibiI6ICLllpzliaciLCAidiI6ICJjYXRlXzMwMyJ9LAogICAgICAgICAgICAgICAgeyJuIjogIumdkuaYpSIsICJ2IjogImNhdGVfMjk3In0sIHsibiI6ICLlv5fmgKoiLCAidiI6ICJjYXRlXzEwMjcifSwgeyJuIjogIuawkeWbveeIseaDhSIsICJ2IjogImNhdGVfMTAyNSJ9LAogICAgICAgICAgICAgICAgeyJuIjogIueBteW8giIsICJ2IjogImNhdGVfNzUxIn0sIHsibiI6ICLlrrblm73mg4XmgIAiLCAidiI6ICJjYXRlXzEyMzUifSwgeyJuIjogIuazleW+iyIsICJ2IjogImNhdGVfMTEzNiJ9LAogICAgICAgICAgICAgICAgeyJuIjogIuWIkeS+piIsICJ2IjogImNhdGVfMTE0OCJ9LCB7Im4iOiAi5oqX5oiYIiwgInYiOiAiY2F0ZV81MDQifSwgeyJuIjogIuatpuS+oCIsICJ2IjogImNhdGVfMTE3MiJ9LAogICAgICAgICAgICAgICAgeyJuIjogIuawkeWbveS8oOWlhyIsICJ2IjogImNhdGVfMTI0MCJ9LCB7Im4iOiAi5rGC55SfIiwgInYiOiAiY2F0ZV8xMTY4In0sIHsibiI6ICLliqjkvZwiLCAidiI6ICJjYXRlXzMwMiJ9LAogICAgICAgICAgICAgICAgeyJuIjogIuenkeW5uyIsICJ2IjogImNhdGVfMTA5MiJ9LCB7Im4iOiAi5oGQ5oCWIiwgInYiOiAiY2F0ZV8xMjE5In0sIHsibiI6ICLllYbmiJgiLCAidiI6ICJjYXRlXzEyMjUifSwKICAgICAgICAgICAgXX0sCiAgICAgICAgICAgIHsia2V5IjogImJhY2tncm91bmQiLCAibmFtZSI6ICLog4zmma8iLCAidmFsdWUiOiBbCiAgICAgICAgICAgICAgICB7Im4iOiAi5YWo6YOoIiwgInYiOiAiIn0sIHsibiI6ICLnjrDku6MiLCAidiI6ICJjYXRlXzc1NyJ9LCB7Im4iOiAi6YO95biCIiwgInYiOiAiY2F0ZV8xIn0sCiAgICAgICAgICAgICAgICB7Im4iOiAi5Y+k5LujIiwgInYiOiAiY2F0ZV83NTgifSwgeyJuIjogIuS5oeadkSIsICJ2IjogImNhdGVfMTEifSwgeyJuIjogIuW5tOS7oyIsICJ2IjogImNhdGVfNzkifSwKICAgICAgICAgICAgICAgIHsibiI6ICLmnrbnqboiLCAidiI6ICJjYXRlXzQ1MiJ9LCB7Im4iOiAi6IGM5Zy6IiwgInYiOiAiY2F0ZV8xMjcifSwgeyJuIjogIuawkeWbvSIsICJ2IjogImNhdGVfMzkwIn0sCiAgICAgICAgICAgICAgICB7Im4iOiAi5qCh5ZutIiwgInYiOiAiY2F0ZV80In0sIHsibiI6ICLlrqvlu7ciLCAidiI6ICJjYXRlXzExNTMifSwgeyJuIjogIuiNkuWymyIsICJ2IjogImNhdGVfMTE2MiJ9LAogICAgICAgICAgICBdfSwKICAgICAgICAgICAgeyJrZXkiOiAic2V0dGluZyIsICJuYW1lIjogIuiuvuWumiIsICJ2YWx1ZSI6IFsKICAgICAgICAgICAgICAgIHsibiI6ICLlhajpg6giLCAidiI6ICIifSwgeyJuIjogIuaJk+iEuOiZkOa4oyIsICJ2IjogImNhdGVfMTA1MSJ9LCB7Im4iOiAi5aSn55S35Li7IiwgInYiOiAiY2F0ZV8xMjA3In0sCiAgICAgICAgICAgICAgICB7Im4iOiAi5aSn5aWz5Li7IiwgInYiOiAiY2F0ZV83NjAifSwgeyJuIjogIumprOeUsiIsICJ2IjogImNhdGVfMjY2In0sIHsibiI6ICLph43nlJ8iLCAidiI6ICJjYXRlXzM2In0sCiAgICAgICAgICAgICAgICB7Im4iOiAi56m/6LaKIiwgInYiOiAiY2F0ZV8zNyJ9LCB7Im4iOiAi57O757ufIiwgInYiOiAiY2F0ZV8xOSJ9LCB7Im4iOiAi5YWI5ama5ZCO54ixIiwgInYiOiAiY2F0ZV8yNjUifSwKICAgICAgICAgICAgICAgIHsibiI6ICLlrrbplb/ph4znn60iLCAidiI6ICJjYXRlXzg2MiJ9LCB7Im4iOiAi5bCP5Lq654mpIiwgInYiOiAiY2F0ZV8xMDEwIn0sIHsibiI6ICLnoLTplZzph43lnIYiLCAidiI6ICJjYXRlXzQ3NSJ9LAogICAgICAgICAgICAgICAgeyJuIjogIuelnuixqiIsICJ2IjogImNhdGVfMjAifSwgeyJuIjogIuixqumXqCIsICJ2IjogImNhdGVfOTM2In0sIHsibiI6ICLlvLrogIXlm57lvZIiLCAidiI6ICJjYXRlXzEwNDUifSwKICAgICAgICAgICAgICAgIHsibiI6ICLlvILog70iLCAidiI6ICJjYXRlXzU5OCJ9LCB7Im4iOiAi6JmQ5oGLIiwgInYiOiAiY2F0ZV8xMDA4In0sIHsibiI6ICLkvKDmib/op4nphpIiLCAidiI6ICJjYXRlXzEwMDcifSwKICAgICAgICAgICAgICAgIHsibiI6ICLljLvnlJ8iLCAidiI6ICJjYXRlXzQ4NyJ9LCB7Im4iOiAi5by65by66IGU5ZCIIiwgInYiOiAiY2F0ZV8xMDQ5In0sIHsibiI6ICLotZjlqb/pgIbooq0iLCAidiI6ICJjYXRlXzEwNDQifSwKICAgICAgICAgICAgICAgIHsibiI6ICLnlJzlrqAiLCAidiI6ICJjYXRlXzk2In0sIHsibiI6ICLlqLHkuZDlnIgiLCAidiI6ICJjYXRlXzQzIn0sIHsibiI6ICLnpZ7ljLsiLCAidiI6ICJjYXRlXzI2In0sCiAgICAgICAgICAgICAgICB7Im4iOiAi6Z2S5qKF56u56amsIiwgInYiOiAiY2F0ZV8zODcifSwgeyJuIjogIuWnkOW8n+aBiyIsICJ2IjogImNhdGVfNzYyIn0sIHsibiI6ICLnjoTlraYiLCAidiI6ICJjYXRlXzkyOSJ9LAogICAgICAgICAgICAgICAgeyJuIjogIui/veWmu+eBq+iRrOWcuiIsICJ2IjogImNhdGVfNjE2In0sIHsibiI6ICLkuJrnlYznsr7oi7EiLCAidiI6ICJjYXRlXzEyOTMifSwgeyJuIjogIuS4gOingemSn+aDhSIsICJ2IjogImNhdGVfNDc3In0sCiAgICAgICAgICAgICAgICB7Im4iOiAi56aP5a6dIiwgInYiOiAiY2F0ZV8xMjkxIn0sIHsibiI6ICLmjZ7lgY/pl6giLCAidiI6ICJjYXRlXzEyODcifSwgeyJuIjogIuWPjea0vuS4u+inkiIsICJ2IjogImNhdGVfMTA0MiJ9LAogICAgICAgICAgICAgICAgeyJuIjogIuiQjOWuoCIsICJ2IjogImNhdGVfNDI4In0sIHsibiI6ICLlj4zlkJHmlZHotY4iLCAidiI6ICJjYXRlXzEyMDAifSwgeyJuIjogIuaWueiogCIsICJ2IjogImNhdGVfMTI1NSJ9LAogICAgICAgICAgICAgICAgeyJuIjogIueZveaciOWFiSIsICJ2IjogImNhdGVfNjE1In0sIHsibiI6ICLngbXprYLkupLmjaIiLCAidiI6ICJjYXRlXzgzMSJ9LCB7Im4iOiAi55eF5aiHIiwgInYiOiAiY2F0ZV8zODAifSwKICAgICAgICAgICAgICAgIHsibiI6ICLmmrTlr4wiLCAidiI6ICJjYXRlXzExOTEifSwgeyJuIjogIum7kemBkyIsICJ2IjogImNhdGVfODI2In0sIHsibiI6ICLkuKflsLgiLCAidiI6ICJjYXRlXzU4MiJ9LAogICAgICAgICAgICAgICAgeyJuIjogIueJueenjeWFtSIsICJ2IjogImNhdGVfMzc1In0sCiAgICAgICAgICAgIF19LAogICAgICAgICAgICB7ImtleSI6ICJ0aW1lIiwgIm5hbWUiOiAi5pe26Ze0IiwgInZhbHVlIjogWwogICAgICAgICAgICAgICAgeyJuIjogIuWFqOmDqCIsICJ2IjogIiJ9LCB7Im4iOiAiN+WkqeWGheS4iuaWsCIsICJ2IjogIjEifSwgeyJuIjogIjE05aSp5YaF5LiK5pawIiwgInYiOiAiMiJ9LAogICAgICAgICAgICAgICAgeyJuIjogIjMw5aSp5YaF5LiK5pawIiwgInYiOiAiMyJ9LCB7Im4iOiAiOTDlpKnlhoXkuIrmlrAiLCAidiI6ICI0In0sCiAgICAgICAgICAgIF19LAogICAgICAgIF0KICAgICAgICBmaWx0ZXJfZGljdCA9IHtjWyJ0eXBlX2lkIl06IGdyb3VwcyBmb3IgYyBpbiBjbGFzc19saXN0fQogICAgICAgIGhvbWVfbGlzdCA9IFtdCiAgICAgICAgdHJ5OgogICAgICAgICAgICBkYXRhID0gX2RhdGEoU0lURSArICIvIikKICAgICAgICAgICAgcGFnZSA9IChkYXRhLmdldCgibG9hZGVyRGF0YSIpIG9yIHt9KS5nZXQoInBhZ2UiKSBvciB7fQogICAgICAgICAgICBzZWVuID0gc2V0KCkKICAgICAgICAgICAgZm9yIHNlYyBpbiAocGFnZS5nZXQoImhvbWVTZWN0aW9ucyIpIG9yIFtdKToKICAgICAgICAgICAgICAgIGZvciB2IGluIChzZWMuZ2V0KCJ2aWRlb19saXN0Iikgb3IgW10pOgogICAgICAgICAgICAgICAgICAgIGl0ID0gX2l0ZW0odikKICAgICAgICAgICAgICAgICAgICB2aWQgPSBzdHIoaXQuZ2V0KCJ2b2RfaWQiKSBvciAiIikKICAgICAgICAgICAgICAgICAgICBpZiB2aWQgYW5kIHZpZCBub3QgaW4gc2VlbjoKICAgICAgICAgICAgICAgICAgICAgICAgc2Vlbi5hZGQodmlkKQogICAgICAgICAgICAgICAgICAgICAgICBob21lX2xpc3QuYXBwZW5kKGl0KQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgIGhvbWVfbGlzdCA9IFtdCiAgICAgICAgcmV0dXJuIHsiY2xhc3MiOiBjbGFzc19saXN0LCAiZmlsdGVycyI6IGZpbHRlcl9kaWN0LCAibGlzdCI6IGhvbWVfbGlzdFs6NDBdfQogICAgZGVmIGhvbWVWaWRlb0NvbnRlbnQoc2VsZik6CiAgICAgICAgdHJ5OgogICAgICAgICAgICBkYXRhID0gX2RhdGEoU0lURSArICIvIikKICAgICAgICAgICAgcGFnZSA9IChkYXRhLmdldCgibG9hZGVyRGF0YSIpIG9yIHt9KS5nZXQoInBhZ2UiKSBvciB7fQogICAgICAgICAgICBvdXQgPSBbXQogICAgICAgICAgICBzZWVuID0gc2V0KCkKICAgICAgICAgICAgZm9yIHNlYyBpbiAocGFnZS5nZXQoImhvbWVTZWN0aW9ucyIpIG9yIFtdKToKICAgICAgICAgICAgICAgIGZvciB2IGluIChzZWMuZ2V0KCJ2aWRlb19saXN0Iikgb3IgW10pOgogICAgICAgICAgICAgICAgICAgIGl0ID0gX2l0ZW0odikKICAgICAgICAgICAgICAgICAgICB2aWQgPSBzdHIoaXQuZ2V0KCJ2b2RfaWQiKSBvciAiIikKICAgICAgICAgICAgICAgICAgICBpZiB2aWQgYW5kIHZpZCBub3QgaW4gc2VlbjoKICAgICAgICAgICAgICAgICAgICAgICAgc2Vlbi5hZGQodmlkKQogICAgICAgICAgICAgICAgICAgICAgICBvdXQuYXBwZW5kKGl0KQogICAgICAgICAgICByZXR1cm4geyJsaXN0Ijogb3V0Wzo2MF19CiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgcmV0dXJuIHsibGlzdCI6IFtdfQoKICAgIGRlZiBfcXVlcnkoc2VsZiwgcGcsIHE9Tm9uZSk6CiAgICAgICAgdHJ5OgogICAgICAgICAgICBwZyA9IG1heCgxLCBpbnQocGcpKQogICAgICAgIGV4Y2VwdCAoVHlwZUVycm9yLCBWYWx1ZUVycm9yKToKICAgICAgICAgICAgcGcgPSAxCiAgICAgICAgaWYgcSBpcyBOb25lOgogICAgICAgICAgICBxID0geyJ0YWIiOiAiMSIsICJzb3J0X3R5cGUiOiAiMSJ9CiAgICAgICAgcmV0dXJuIF9jYXRlZ29yeV9sb2FkZXIocGcsIHEpCiAgICBkZWYgY2F0ZWdvcnlDb250ZW50KHNlbGYsIHRpZCwgcGcsIGZpbHRlciwgZXh0ZW5kKToKICAgICAgICB0cnk6CiAgICAgICAgICAgIHBhZ2UgPSBtYXgoMSwgaW50KHBnKSkKICAgICAgICBleGNlcHQgKFR5cGVFcnJvciwgVmFsdWVFcnJvcik6CiAgICAgICAgICAgIHBhZ2UgPSAxCiAgICAgICAgIyDmvKvliacgLyBBSea8q+WJp++8muWumOe9keaQnOe0ouS4jeaUr+aMgeecn+e/u+mhte+8jOWkmuWFs+mUruivjei9ruaNogogICAgICAgIGlmIHRpZCBpbiAoImNvbWljIiwgIm1hbmp1IiwgIua8q+WJpyIpOgogICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICBwID0gX2NhdGVnb3J5X2xvYWRlcihwYWdlLCB7InRhYiI6ICIyIiwgInNvcnRfdHlwZSI6ICIxIn0pCiAgICAgICAgICAgICAgICByb3dzID0gcC5nZXQoInJlY29tbWVuZExpc3QiKSBvciBbXQogICAgICAgICAgICAgICAgaWYgcm93czoKICAgICAgICAgICAgICAgICAgICBwYWdlX2RhdGEgPSBwLmdldCgicGFnaW5hdGlvbiIpIG9yIHt9CiAgICAgICAgICAgICAgICAgICAgcmV0dXJuIHsKICAgICAgICAgICAgICAgICAgICAgICAgInBhZ2UiOiBwYWdlLAogICAgICAgICAgICAgICAgICAgICAgICAicGFnZWNvdW50IjogaW50KHBhZ2VfZGF0YS5nZXQoInRvdGFsUGFnZXMiKSBvciAxKSwKICAgICAgICAgICAgICAgICAgICAgICAgImxpbWl0IjogbGVuKHJvd3MpLAogICAgICAgICAgICAgICAgICAgICAgICAidG90YWwiOiBpbnQocGFnZV9kYXRhLmdldCgidG90YWwiKSBvciBsZW4ocm93cykpLAogICAgICAgICAgICAgICAgICAgICAgICAibGlzdCI6IFtfY2F0X2l0ZW0oeCkgZm9yIHggaW4gcm93c10sCiAgICAgICAgICAgICAgICAgICAgfQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICAgICAgcGFzcwogICAgICAgICAgICByZXR1cm4gX3NlYXJjaF9ieV9rZXl3b3JkcyhfTUFOSlVfS0VZV09SRFMsIHBhZ2UpCiAgICAgICAgaWYgdGlkIGluICgiYWlfY29taWMiLCAiYWlfbWFuanUiLCAiQUnmvKvliaciLCAiYWnmvKvliaciKToKICAgICAgICAgICAgcmV0dXJuIF9zZWFyY2hfYnlfa2V5d29yZHMoX0FJX01BTkpVX0tFWVdPUkRTLCBwYWdlKQogICAgICAgIHEgPSB7InRhYiI6ICIxIiwgInNvcnRfdHlwZSI6ICIxIn0KICAgICAgICBpZiB0aWQgPT0gImxhdGVzdCI6CiAgICAgICAgICAgIHFbInNvcnRfdHlwZSJdID0gIjIiCiAgICAgICAgZWxpZiB0aWQgPT0gImhvdCI6CiAgICAgICAgICAgIHFbInNvcnRfdHlwZSJdID0gIjEiCiAgICAgICAgZWxpZiB0aWQgPT0gIm1hbGUiOgogICAgICAgICAgICBxWyJnZW5kZXIiXSA9ICIxIgogICAgICAgIGVsaWYgdGlkID09ICJmZW1hbGUiOgogICAgICAgICAgICBxWyJnZW5kZXIiXSA9ICIyIgogICAgICAgIGlmIGlzaW5zdGFuY2UoZXh0ZW5kLCBzdHIpIGFuZCBleHRlbmQ6CiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIGV4dGVuZCA9IGpzb24ubG9hZHMoZXh0ZW5kKQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICAgICAgZXh0ZW5kID0ge30KICAgICAgICBpZiBpc2luc3RhbmNlKGV4dGVuZCwgZGljdCk6CiAgICAgICAgICAgIGZvciBrLCB2IGluIGV4dGVuZC5pdGVtcygpOgogICAgICAgICAgICAgICAgaWYgdiBhbmQgc3RyKHYpIG5vdCBpbiAoIiIsICJhbGwiLCAiMCIpOgogICAgICAgICAgICAgICAgICAgIHFba10gPSBzdHIodikKICAgICAgICBwID0gX2NhdGVnb3J5X2xvYWRlcihwYWdlLCBxKQogICAgICAgIHJvd3MgPSBwLmdldCgicmVjb21tZW5kTGlzdCIpIG9yIFtdCiAgICAgICAgcGFnZV9kYXRhID0gcC5nZXQoInBhZ2luYXRpb24iKSBvciB7fQogICAgICAgIHJldHVybiB7CiAgICAgICAgICAgICJwYWdlIjogcGFnZSwKICAgICAgICAgICAgInBhZ2Vjb3VudCI6IGludChwYWdlX2RhdGEuZ2V0KCJ0b3RhbFBhZ2VzIikgb3IgMSksCiAgICAgICAgICAgICJsaW1pdCI6IGxlbihyb3dzKSwKICAgICAgICAgICAgInRvdGFsIjogaW50KHBhZ2VfZGF0YS5nZXQoInRvdGFsIikgb3IgbGVuKHJvd3MpKSwKICAgICAgICAgICAgImxpc3QiOiBbX2NhdF9pdGVtKHgpIGZvciB4IGluIHJvd3NdLAogICAgICAgIH0KICAgIGRlZiBzZWFyY2hDb250ZW50KHNlbGYsIGtleSwgcXVpY2s9RmFsc2UsIHBnPSIxIik6CiAgICAgICAgdHJ5OgogICAgICAgICAgICBwYWdlID0gbWF4KDEsIGludChwZykpCiAgICAgICAgZXhjZXB0IChUeXBlRXJyb3IsIFZhbHVlRXJyb3IpOgogICAgICAgICAgICBwYWdlID0gMQogICAgICAgIGtleSA9IHN0cihrZXkgb3IgIiIpLnN0cmlwKCkgb3IgIuefreWJpyIKICAgICAgICAjIEFJL+a8q+WJp+ebuOWFs+aQnOe0ouS5n+i1sOWFs+mUruivjei9ruaNou+8jOaPkOWNh+e/u+mhteS9k+mqjAogICAgICAgIGxvdyA9IGtleS5sb3dlcigpCiAgICAgICAgaWYga2V5IGluICgiQUnmvKvliaciLCAiYWnmvKvliaciKSBvciAiYWnmvKsiIGluIGxvdzoKICAgICAgICAgICAgcmV0dXJuIF9zZWFyY2hfYnlfa2V5d29yZHMoX0FJX01BTkpVX0tFWVdPUkRTLCBwYWdlKQogICAgICAgIGlmIGtleSBpbiAoIua8q+WJpyIsICLliqjmvKvnn63liaciKToKICAgICAgICAgICAgcmV0dXJuIF9zZWFyY2hfYnlfa2V5d29yZHMoX01BTkpVX0tFWVdPUkRTLCBwYWdlKQoKICAgICAgICBwID0gX3NlYXJjaF9sb2FkZXIoa2V5KQogICAgICAgIHJvd3MgPSBwLmdldCgic2VhcmNoTGlzdCIpIG9yIFtdCiAgICAgICAgdG90YWwgPSBpbnQocC5nZXQoInRvdGFsQ291bnQiKSBvciBsZW4ocm93cykgb3IgMCkKICAgICAgICAjIOWumOe9keaQnOe0ouWfuuacrOWPquacieS4gOmhteacieaViOe7k+aenAogICAgICAgIHJldHVybiB7CiAgICAgICAgICAgICJwYWdlIjogcGFnZSwKICAgICAgICAgICAgInBhZ2Vjb3VudCI6IDEgaWYgbm90IHRvdGFsIGVsc2UgbWF4KDEsIG1pbigxMCwgKHRvdGFsICsgOSkgLy8gMTApKSwKICAgICAgICAgICAgImxpbWl0IjogbGVuKHJvd3MpLAogICAgICAgICAgICAidG90YWwiOiB0b3RhbCBvciBsZW4ocm93cyksCiAgICAgICAgICAgICJsaXN0IjogW19pdGVtKHgpIGZvciB4IGluIHJvd3NdLAogICAgICAgIH0KCgogICAgZGVmIGRldGFpbENvbnRlbnQoc2VsZiwgaWRzKToKICAgICAgICBzaWQgPSBzdHIoaWRzWzBdIGlmIGlzaW5zdGFuY2UoaWRzLCAobGlzdCwgdHVwbGUpKSBlbHNlIGlkcykKICAgICAgICBzaWQgPSBzaWQucmVwbGFjZSgiaGctc2VyaWVzLXYxOiIsICIiKQogICAgICAgIHAgPSAoKF9kYXRhKFNJVEUgKyAiL2RldGFpbD9zZXJpZXNfaWQ9IiArIHF1b3RlKHNpZCwgc2FmZT0iIikpLmdldCgibG9hZGVyRGF0YSIpIG9yIHt9KS5nZXQoImRldGFpbF9wYWdlIikgb3Ige30pCiAgICAgICAgcyA9IHAuZ2V0KCJzZXJpZXNEZXRhaWwiKSBvciB7fQogICAgICAgIHZpZHMgPSBzLmdldCgidmlkX2xpc3QiKSBvciBbXQogICAgICAgIGFjdG9ycyA9IFtzdHIoeC5nZXQoIm5pY2tuYW1lIikpIGZvciB4IGluIChzLmdldCgiY2VsZWJyaXRpZXMiKSBvciBbXSkgaWYgaXNpbnN0YW5jZSh4LCBkaWN0KSBhbmQgeC5nZXQoIm5pY2tuYW1lIildCiAgICAgICAgcGxheV9mcm9tID0gW10KICAgICAgICBwbGF5X3VybCA9IFtdCiAgICAgICAgZm9yIHEsIGxpbmVfbmFtZSBpbiBfSEdfUVVBTElUWV9MSU5FUzoKICAgICAgICAgICAgZXBzID0gIiMiLmpvaW4oCiAgICAgICAgICAgICAgICAi56ysJWTpm4YlcyVzJXMlcyIgJSAoaSArIDEsICIkIiwgRVBJU09ERV9QUkVGSVgsIHEgKyAiOiIsIHN0cih2KSkKICAgICAgICAgICAgICAgIGZvciBpLCB2IGluIGVudW1lcmF0ZSh2aWRzKQogICAgICAgICAgICApCiAgICAgICAgICAgIHBsYXlfZnJvbS5hcHBlbmQobGluZV9uYW1lKQogICAgICAgICAgICBwbGF5X3VybC5hcHBlbmQoZXBzKQogICAgICAgIHJldHVybiB7Imxpc3QiOiBbeyJ2b2RfaWQiOiBzaWQsICJ2b2RfbmFtZSI6IHN0cihzLmdldCgic2VyaWVzX25hbWUiKSBvciAiIiksICJ2b2RfcGljIjogc3RyKHMuZ2V0KCJzZXJpZXNfY292ZXIiKSBvciAiIiksICJ2b2RfeWVhciI6ICIiLCAidm9kX2FyZWEiOiAiIiwgInZvZF9kaXJlY3RvciI6ICIiLCAidm9kX2FjdG9yIjogIiwiLmpvaW4oYWN0b3JzKSwgInZvZF9jb250ZW50Ijogc3RyKHMuZ2V0KCJzZXJpZXNfaW50cm8iKSBvciAiIiksICJ2b2RfcmVtYXJrcyI6IHN0cihzLmdldCgiZXBpc29kZV9yaWdodF90ZXh0Iikgb3IgIiIpLCAidm9kX3BsYXlfZnJvbSI6ICIkJCQiLmpvaW4ocGxheV9mcm9tKSwgInZvZF9wbGF5X3VybCI6ICIkJCQiLmpvaW4ocGxheV91cmwpfV19CiAgICBkZWYgcGxheWVyQ29udGVudChzZWxmLCBmbGFnLCBpZCwgdmlwRmxhZ3M9Tm9uZSk6CiAgICAgICAgIyDku47nur/ot6/lkI3vvIhmbGFn77yM5aaC4oCc57qi5p6c6LaF5riFL+e6ouaenOmrmOa4heKAne+8ieS4jumbhiB0b2tlbiDlj4zot6/op6PmnpDmuIXmmbDluqbjgIIKICAgICAgICAjIHRva2VuIOW3suaYryAnaGctZXBpc29kZS12MTo8cT46PHZpZD4n77yMZmxhZyDnlKjkuo7ml6flo7Plj6rkvKDnur/ot6/lkI3ml7blhZzlupXjgIIKICAgICAgICB0b2tlbl9xLCB2aWQgPSBfc3BsaXRfZXBpc29kZV90b2tlbihpZCkKICAgICAgICBsaW5lX3EgPSAiMTA4MCIKICAgICAgICBmb3IgbmFtZV9rZXksIGNhbmRpZGF0ZV9xIGluIF9RVUFMSVRZX0xJTkVfTkFNRV9UT19RLml0ZW1zKCk6CiAgICAgICAgICAgIGlmIG5hbWVfa2V5IGluIHN0cihmbGFnIG9yICIiKToKICAgICAgICAgICAgICAgIGxpbmVfcSA9IGNhbmRpZGF0ZV9xCiAgICAgICAgICAgICAgICBicmVhawogICAgICAgIHEgPSBsaW5lX3EgaWYgdG9rZW5fcSA9PSAiMTA4MCIgYW5kIHN0cihmbGFnKSBlbHNlIHRva2VuX3EKICAgICAgICBxID0gcSBpZiBxIGluIF9RVUFMSVRZX0xJTkVfTkFNRV9UT19RIGVsc2UgIjEwODAiCiAgICAgICAgaWYgbm90IHN0cih2aWQpLmlzZGlnaXQoKToKICAgICAgICAgICAgcmV0dXJuIHsKICAgICAgICAgICAgICAgICJwYXJzZSI6IDEsCiAgICAgICAgICAgICAgICAiangiOiAwLAogICAgICAgICAgICAgICAgInBsYXlVcmwiOiAiIiwKICAgICAgICAgICAgICAgICJ1cmwiOiBTSVRFICsgIi8iLAogICAgICAgICAgICAgICAgImhlYWRlciI6IHsiVXNlci1BZ2VudCI6IFVBfSwKICAgICAgICAgICAgfQogICAgICAgICMgT0vlvbHop4YgLyDlpJrmlbDlo7PvvJrlv4XpobvotbAgZ2V0UHJveHlVcmzvvIjpgJrluLjlt7LluKYgZG89cHnvvInvvIzkuI3opoHopobnm5YgZG8KICAgICAgICBwcm94eSA9ICIiCiAgICAgICAgdHJ5OgogICAgICAgICAgICBpZiBoYXNhdHRyKHNlbGYsICJnZXRQcm94eVVybCIpOgogICAgICAgICAgICAgICAgcHJveHkgPSAoc2VsZi5nZXRQcm94eVVybCgpIG9yICIiKS5zdHJpcCgpCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgcHJveHkgPSAiIgogICAgICAgIGlmIHByb3h5OgogICAgICAgICAgICBzZXAgPSAiJiIgaWYgIj8iIGluIHByb3h5IGVsc2UgIj8iCiAgICAgICAgICAgICMg5L+d55WZ5aOz6Ieq5bim55qEIGRvPXB577yM5Y+q6L+95Yqg5Lia5Yqh5Y+C5pWw5LiO5riF5pmw5bqm57q/6LevCiAgICAgICAgICAgIHVybCA9IHByb3h5ICsgc2VwICsgdXJsZW5jb2RlKAogICAgICAgICAgICAgICAgewogICAgICAgICAgICAgICAgICAgICJ2aWQiOiB2aWQsCiAgICAgICAgICAgICAgICAgICAgInEiOiBxLAogICAgICAgICAgICAgICAgICAgICJoZyI6ICJjZW5jIiwKICAgICAgICAgICAgICAgICAgICAiZGlkIjogc2VsZi5kZXZpY2VfaWQgb3IgIiIsCiAgICAgICAgICAgICAgICAgICAgImlpZCI6IHNlbGYuaW5zdGFsbF9pZCBvciAiIiwKICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgKQogICAgICAgICAgICByZXR1cm4gewogICAgICAgICAgICAgICAgInBhcnNlIjogMCwKICAgICAgICAgICAgICAgICJqeCI6IDAsCiAgICAgICAgICAgICAgICAicGxheVVybCI6ICIiLAogICAgICAgICAgICAgICAgInVybCI6IHVybCwKICAgICAgICAgICAgICAgICJoZWFkZXIiOiB7CiAgICAgICAgICAgICAgICAgICAgIlVzZXItQWdlbnQiOiBNRURJQV9VQSwKICAgICAgICAgICAgICAgICAgICAiUmVmZXJlciI6ICJodHRwczovL25vdmVsLnNuc3Nkay5jb20vIiwKICAgICAgICAgICAgICAgIH0sCiAgICAgICAgICAgIH0KICAgICAgICAjIOWkh+eUqO+8muacrOacuiBSYW5nZSDmtYHvvIhGb25nTWkg5pu05Y+L5aW977yJCiAgICAgICAgdHJ5OgogICAgICAgICAgICBwb3J0ID0gX3N0YXJ0X3N0cmVhbV9zZXJ2ZXIoKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgIHBvcnQgPSAwCiAgICAgICAgaWYgcG9ydDoKICAgICAgICAgICAgcXVlcnkgPSB1cmxlbmNvZGUoCiAgICAgICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAgICAgInZpZCI6IHZpZCwKICAgICAgICAgICAgICAgICAgICAicSI6IHEsCiAgICAgICAgICAgICAgICAgICAgImRpZCI6IHNlbGYuZGV2aWNlX2lkIG9yICIiLAogICAgICAgICAgICAgICAgICAgICJpaWQiOiBzZWxmLmluc3RhbGxfaWQgb3IgIiIsCiAgICAgICAgICAgICAgICB9CiAgICAgICAgICAgICkKICAgICAgICAgICAgcmV0dXJuIHsKICAgICAgICAgICAgICAgICJwYXJzZSI6IDAsCiAgICAgICAgICAgICAgICAiangiOiAwLAogICAgICAgICAgICAgICAgInBsYXlVcmwiOiAiIiwKICAgICAgICAgICAgICAgICJ1cmwiOiAiaHR0cDovLzEyNy4wLjAuMTolZC9oZy5tcDQ/JXMiICUgKHBvcnQsIHF1ZXJ5KSwKICAgICAgICAgICAgICAgICJoZWFkZXIiOiB7IlVzZXItQWdlbnQiOiBVQX0sCiAgICAgICAgICAgIH0KICAgICAgICByZXR1cm4gewogICAgICAgICAgICAicGFyc2UiOiAxLAogICAgICAgICAgICAiangiOiAwLAogICAgICAgICAgICAicGxheVVybCI6ICIiLAogICAgICAgICAgICAidXJsIjogU0lURSArICIvIiwKICAgICAgICAgICAgImhlYWRlciI6IHsiVXNlci1BZ2VudCI6IFVBfSwKICAgICAgICB9CgoKICAgIGRlZiBwcm94eShzZWxmLCBwYXJhbSk6CiAgICAgICAgIiIi6YOo5YiG5aOz6LCD55SoIHByb3h5IOiAjOS4jeaYryBsb2NhbFByb3h544CCIiIiCiAgICAgICAgcmV0dXJuIHNlbGYubG9jYWxQcm94eShwYXJhbSkKCiAgICBkZWYgbG9jYWxQcm94eShzZWxmLCBwYXJhbSk6CiAgICAgICAgIiIi5aOz5pys5Zyw5Luj55CG77ya5LyY5YWI6K+757yT5a2Y77yb5peg5Y6f55SfIEFFUyDml7bpgb/lhY3kuIDkuIrmnaXlsLHop6MgMTA4MCDmlbTpm4blr7zoh7TotoXml7blpLHotKXjgIIiIiIKICAgICAgICBpbXBvcnQgdHJhY2ViYWNrCiAgICAgICAgcGFyYW0gPSBwYXJhbSBvciB7fQogICAgICAgIHZpZCA9IHN0cigKICAgICAgICAgICAgcGFyYW0uZ2V0KCJ2aWQiKQogICAgICAgICAgICBvciBwYXJhbS5nZXQoImlkIikKICAgICAgICAgICAgb3IgcGFyYW0uZ2V0KCJtZWRpYUlkIikKICAgICAgICAgICAgb3IgIiIKICAgICAgICApLnN0cmlwKCkKICAgICAgICBpZiBub3QgdmlkIG9yIG5vdCBzdHIodmlkKS5pc2RpZ2l0KCk6CiAgICAgICAgICAgIGZvciBfa2V5LCB2YWx1ZSBpbiBwYXJhbS5pdGVtcygpOgogICAgICAgICAgICAgICAgdGV4dCA9IHN0cih2YWx1ZSBvciAiIikuc3RyaXAoKQogICAgICAgICAgICAgICAgaWYgdGV4dC5pc2RpZ2l0KCkgYW5kIGxlbih0ZXh0KSA+PSAxMDoKICAgICAgICAgICAgICAgICAgICB2aWQgPSB0ZXh0CiAgICAgICAgICAgICAgICAgICAgYnJlYWsKICAgICAgICBpZiBub3QgdmlkOgogICAgICAgICAgICByZXR1cm4gWzQwMCwgInRleHQvcGxhaW47IGNoYXJzZXQ9dXRmLTgiLCBiIm1pc3NpbmcgdmlkIl0KCiAgICAgICAgdHJ5OgogICAgICAgICAgICBjZmcgPSB7CiAgICAgICAgICAgICAgICAiZGV2aWNlX2lkIjogc3RyKHBhcmFtLmdldCgiZGlkIikgb3Igc2VsZi5kZXZpY2VfaWQgb3IgIiIpLAogICAgICAgICAgICAgICAgImluc3RhbGxfaWQiOiBzdHIocGFyYW0uZ2V0KCJpaWQiKSBvciBzZWxmLmluc3RhbGxfaWQgb3IgIiIpLAogICAgICAgICAgICB9CiAgICAgICAgICAgIHVzZXJfcSA9IHN0cihwYXJhbS5nZXQoInEiKSBvciBwYXJhbS5nZXQoInF1YWxpdHkiKSBvciAiIikuc3RyaXAoKQogICAgICAgICAgICAjIOacieWOn+eUnyBBRVPvvJrkvJjlhYggMTA4MO+8m+e6ryBQeXRob24gQUVTIOW+iOaFou+8muWFiCA3MjAg5L+d6K+B6IO95pKt77yM5YaN5bCd6K+V5pu06auYCiAgICAgICAgICAgIGlmIHVzZXJfcToKICAgICAgICAgICAgICAgIG9yZGVyID0gW3VzZXJfcSwgIjEwODAiLCAiNzIwIiwgIjQ4MCIsICIzNjAiXQogICAgICAgICAgICBlbGlmIF9hZXNfaXNfZmFzdCgpOgogICAgICAgICAgICAgICAgb3JkZXIgPSBbIjEwODAiLCAiNzIwIiwgIjQ4MCIsICIzNjAiXQogICAgICAgICAgICBlbHNlOgogICAgICAgICAgICAgICAgb3JkZXIgPSBbIjcyMCIsICI0ODAiLCAiMTA4MCIsICIzNjAiXQogICAgICAgICAgICAjIGRlZHVwZQogICAgICAgICAgICBzZWVuX3EgPSBzZXQoKQogICAgICAgICAgICBxdWFscyA9IFtdCiAgICAgICAgICAgIGZvciBxIGluIG9yZGVyOgogICAgICAgICAgICAgICAgaWYgcSBhbmQgcSBub3QgaW4gc2Vlbl9xOgogICAgICAgICAgICAgICAgICAgIHNlZW5fcS5hZGQocSkKICAgICAgICAgICAgICAgICAgICBxdWFscy5hcHBlbmQocSkKCiAgICAgICAgICAgICMg57yT5a2Y5ZG95Lit55u05o6l6L+U5Zue44CC55So5oi35oyH5a6a57q/6Lev5riF5pmw5bqmKHVzZXJfcSnml7bvvIzlj6rorqTor6XmuIXmmbDluqbnvJPlrZjvvIwKICAgICAgICAgICAgIyDkuI3og73lm57pgIDlkb3kuK3lhbblroPmuIXmmbDluqbnvJPlrZjvvIjlkKbliJnor7fmsYI0ODDkvJrmi7/liLAzNjDlhoXlrrnvvInjgIIKICAgICAgICAgICAgaWYgdXNlcl9xOgogICAgICAgICAgICAgICAgcHJpbWFyeSA9IFt1c2VyX3FdCiAgICAgICAgICAgIGVsc2U6CiAgICAgICAgICAgICAgICBwcmltYXJ5ID0gcXVhbHMKICAgICAgICAgICAgZm9yIHEgaW4gcHJpbWFyeToKICAgICAgICAgICAgICAgIGNhY2hlZCA9IF9oZ19jYWNoZV9nZXQodmlkLCBxKQogICAgICAgICAgICAgICAgaWYgY2FjaGVkOgogICAgICAgICAgICAgICAgICAgIHJldHVybiBbMjAwLCAidmlkZW8vbXA0IiwgY2FjaGVkXQoKICAgICAgICAgICAgbW9kZWwgPSBfdmlkZW9fbW9kZWwodmlkLCBjZmcpCiAgICAgICAgICAgIHJvd3MgPSBfdmlkZW9fbGlzdF9mcm9tX21vZGVsKG1vZGVsKQogICAgICAgICAgICBpZiBub3Qgcm93czoKICAgICAgICAgICAgICAgIHJldHVybiBbNTAwLCAidGV4dC9wbGFpbjsgY2hhcnNldD11dGYtOCIsIGIiZW1wdHkgdmlkZW8gbGlzdCJdCgogICAgICAgICAgICBsYXN0X2VyciA9IE5vbmUKICAgICAgICAgICAgZm9yIHdhbnRlZCBpbiBxdWFsczoKICAgICAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgICAgICAjIOWGjeafpeS4gOasoeivpea4heaZsOW6pue8k+WtmO+8iG1vZGVsIOino+aekOWQju+8iQogICAgICAgICAgICAgICAgICAgIGNhY2hlZCA9IF9oZ19jYWNoZV9nZXQodmlkLCB3YW50ZWQpCiAgICAgICAgICAgICAgICAgICAgaWYgY2FjaGVkOgogICAgICAgICAgICAgICAgICAgICAgICByZXR1cm4gWzIwMCwgInZpZGVvL21wNCIsIGNhY2hlZF0KCiAgICAgICAgICAgICAgICAgICAgXywgaXRlbSA9IF9zZWxlY3RfcXVhbGl0eShyb3dzLCB3YW50ZWQpCiAgICAgICAgICAgICAgICAgICAgdXJsID0gX21lZGlhX3VybChpdGVtKQogICAgICAgICAgICAgICAgICAgIHNwYWRlID0gX3NwYWRlX3ZhbHVlKGl0ZW0pCiAgICAgICAgICAgICAgICAgICAgaWYgbm90IHVybCBvciBub3Qgc3BhZGU6CiAgICAgICAgICAgICAgICAgICAgICAgIGxhc3RfZXJyID0gIm1pc3NpbmcgdXJsL3NwYWRlIHE9JXMiICUgd2FudGVkCiAgICAgICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgICAgICAgICBrZXlfc2VlZCA9IF9rZXlfc2VlZF9mcm9tX21vZGVsKG1vZGVsKQogICAgICAgICAgICAgICAgICAgICAgICBpZiBrZXlfc2VlZDoKICAgICAgICAgICAgICAgICAgICAgICAgICAgIHVybCA9IF9kZWNyeXB0X3NwYWRlX3VybCh1cmwsIGtleV9zZWVkKQogICAgICAgICAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgICAgICAgICAgICAgIHBhc3MKCiAgICAgICAgICAgICAgICAgICAgIyDkuIvovb3otoXml7bvvJrnuq8gQUVTIOeOr+Wig+abtOefre+8jOmBv+WFjeWjs+err+epuuetieWQjuWksei0pQogICAgICAgICAgICAgICAgICAgIGRsX3RpbWVvdXQgPSAxNTAgaWYgX2Flc19pc19mYXN0KCkgZWxzZSA5MAogICAgICAgICAgICAgICAgICAgIG1lZGlhX2hlYWRlcnMgPSB7CiAgICAgICAgICAgICAgICAgICAgICAgICJVc2VyLUFnZW50IjogTUVESUFfVUEsCiAgICAgICAgICAgICAgICAgICAgICAgICJSZWZlcmVyIjogImh0dHBzOi8vbm92ZWwuc25zc2RrLmNvbS8iLAogICAgICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICAgICAgICAgIGJvZHkgPSBfbXVsdGlfZG93bmxvYWQoCiAgICAgICAgICAgICAgICAgICAgICAgICAgICB1cmwsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICBoZWFkZXJzPW1lZGlhX2hlYWRlcnMsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICB0aW1lb3V0PWRsX3RpbWVvdXQsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICB3b3JrZXJzPTQgaWYgX2Flc19pc19mYXN0KCkgZWxzZSAzLAogICAgICAgICAgICAgICAgICAgICAgICApCiAgICAgICAgICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBkbF9lcnI6CiAgICAgICAgICAgICAgICAgICAgICAgIGxhc3RfZXJyID0gImRvd25sb2FkIGZhaWxlZCBxPSVzIGVycj0lcyIgJSAod2FudGVkLCBkbF9lcnIpCiAgICAgICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICAgICAgICAgaWYgbm90IGJvZHk6CiAgICAgICAgICAgICAgICAgICAgICAgIGxhc3RfZXJyID0gImVtcHR5IGJvZHkgcT0lcyIgJSB3YW50ZWQKICAgICAgICAgICAgICAgICAgICAgICAgY29udGludWUKCiAgICAgICAgICAgICAgICAgICAgIyDnuq8gQUVTIOS4lOS9k+enr+i/h+Wkp+aXtui3s+i/h+i2heWkpyAxMDgw77yM5YeP5bCR5b+F6LaF5pe2CiAgICAgICAgICAgICAgICAgICAgaWYgKG5vdCBfYWVzX2lzX2Zhc3QoKSkgYW5kIHdhbnRlZCBpbiAoIjEwODAiLCAiNGsiKSBhbmQgbGVuKGJvZHkpID4gNDUgKiAxMDI0ICogMTAyNDoKICAgICAgICAgICAgICAgICAgICAgICAgbGFzdF9lcnIgPSAic2tpcCBsYXJnZSAlcyB3aXRob3V0IG5hdGl2ZSBBRVMgc2l6ZT0lcyIgJSAod2FudGVkLCBsZW4oYm9keSkpCiAgICAgICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlCgogICAgICAgICAgICAgICAgICAgIHBsYWluID0gZGVjcnlwdF9tcDRfY2VuYyhib2R5LCBkZXJpdmVfY29udGVudF9rZXkoc3BhZGUpKQogICAgICAgICAgICAgICAgICAgIGlmIGxlbihwbGFpbikgPCA2NCBvciAoYiJmdHlwIiBub3QgaW4gcGxhaW5bOjY0XSBhbmQgYiJtb292IiBub3QgaW4gcGxhaW5bOjQwOTZdKToKICAgICAgICAgICAgICAgICAgICAgICAgbGFzdF9lcnIgPSAiYmFkIG1wNCBhZnRlciBkZWNyeXB0IHE9JXMiICUgd2FudGVkCiAgICAgICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgICAgICAgICBfaGdfY2FjaGVfcHV0KHZpZCwgd2FudGVkLCBwbGFpbikKICAgICAgICAgICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICAgICAgICAgICAgICBwYXNzCiAgICAgICAgICAgICAgICAgICAgcmV0dXJuIFsyMDAsICJ2aWRlby9tcDQiLCBwbGFpbl0KICAgICAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgb25lX2VycjoKICAgICAgICAgICAgICAgICAgICBsYXN0X2VyciA9ICIlcyBxPSVzIiAlIChvbmVfZXJyLCB3YW50ZWQpCiAgICAgICAgICAgICAgICAgICAgY29udGludWUKCiAgICAgICAgICAgIG1zZyA9ICJoZyBsb2NhbFByb3h5IGZhaWxlZDogJXMiICUgbGFzdF9lcnIKICAgICAgICAgICAgcmV0dXJuIFs1MDAsICJ0ZXh0L3BsYWluOyBjaGFyc2V0PXV0Zi04IiwgbXNnLmVuY29kZSgidXRmLTgiKV0KICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGV4YzoKICAgICAgICAgICAgbXNnID0gImhnIGxvY2FsUHJveHkgZmFpbGVkOiAlc1xuJXMiICUgKGV4YywgdHJhY2ViYWNrLmZvcm1hdF9leGMoKSkKICAgICAgICAgICAgcmV0dXJuIFs1MDAsICJ0ZXh0L3BsYWluOyBjaGFyc2V0PXV0Zi04IiwgbXNnLmVuY29kZSgidXRmLTgiKV0KCg==").decode("utf-8")
    _hg_ns = {"__name__": "_hg_shu0"}
    exec(compile(_hg_raw, "___3_shu0.py", "exec"), _hg_ns)
    _hgmod = _tmod.SimpleNamespace(**{k: v for k, v in _hg_ns.items()
                                      if not k.startswith("__")})
    _hgmod.Spider = _hg_ns["Spider"]
    _HG_IMPORT_ERR = ""
except Exception as _e1:
    _hgmod = None
    _HG_IMPORT_ERR = "%s: %s" % (type(_e1).__name__, str(_e1)[:120])


@_register
class _Hongguo(_Src):
    id = "hongguo"
    name = "红果"

    def __init__(self):
        super().__init__()
        self._hg = None
        self._dyn_cats = None
        self._dyn_filters = None

    def _get_hg(self):
        if _hgmod is None:
            raise _SrcErr(
                "红果源未加载：请把 ___3_shu0.py 与 zhenguojian.py 放在同一目录。"
                "%s" % _HG_IMPORT_ERR)
        if self._hg is None:
            self._hg = _hgmod.Spider()
        return self._hg

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        hg = self._get_hg()
        j = hg.homeContent(False) or {}
        cats = []
        for c in j.get("class") or []:
            tid, nm = _s(c.get("type_id")), _s(c.get("type_name"))
            if tid and nm:
                cats.append((tid, nm))
        if cats:
            self._dyn_cats = cats
            return cats
        return [("all", "短剧")]

    def extra_filters(self):
        """红果自带的二级筛选组（主题/背景/设定/时间），list 格式。"""
        if self._dyn_filters is not None:
            return self._dyn_filters
        try:
            hg = self._get_hg()
            f = hg.homeContent(False).get("filters") or {}
            for _tid0, groups in f.items():
                if isinstance(groups, list) and groups:
                    self._dyn_filters = [g for g in groups
                                         if isinstance(g, dict)]
                    return self._dyn_filters
        except Exception:
            pass
        return []

    def _adapt_list(self, j):
        items = []
        for v in (j.get("list") or []) if isinstance(j, dict) else []:
            sid = _s(v.get("vod_id"))
            if not sid:
                continue
            items.append(_vod_item(self.id, sid, v.get("vod_name"),
                                   v.get("vod_pic"), v.get("vod_remarks"),
                                   v.get("vod_content")))
        pg = j.get("page", 1) if isinstance(j, dict) else 1
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1
        pcount = j.get("pagecount", 1) if isinstance(j, dict) else 1
        try:
            pcount = max(1, int(pcount))
        except Exception:
            pcount = 1
        return items, pg < pcount

    def cat(self, catid, pg):
        return self.cat_ex(catid, pg, {})

    def cat_ex(self, catid, pg, ext):
        """带红果二级筛选透传的分类（ext 含 topic/background/setting/time）。"""
        hg = self._get_hg()
        tid = _s(catid) or "all"
        hg_ext = {}
        if isinstance(ext, dict):
            for k, v in ext.items():
                if _s(k) == "cat":
                    continue
                v = _s(v)
                if v and v not in ("", "all", "0"):
                    hg_ext[_s(k)] = v
        j = hg.categoryContent(tid, pg, False, hg_ext)
        return self._adapt_list(j)

    def detail(self, sid):
        hg = self._get_hg()
        j = hg.detailContent([_s(sid)])
        lst = j.get("list") or [] if isinstance(j, dict) else []
        if not lst:
            raise _SrcErr("红果未返回详情")
        v = lst[0]
        # 多清晰度线路（$$$ 分隔），取第一条（超清），proxy 会自动降级
        urls = _s(v.get("vod_play_url")).split("$$$")
        eps = urls[0] if urls else ""
        chapters = []
        for part in eps.split("#"):
            if "$" not in part:
                continue
            t, token = part.split("$", 1)
            token = token.strip()
            if token:
                chapters.append((token, t.strip() or "正片"))
        return _vod_detail(self, sid, _s(v.get("vod_name")),
                           _s(v.get("vod_pic")), _s(v.get("vod_remarks")),
                           _s(v.get("vod_content")), chapters=chapters)

    def play(self, sid, ep):
        hg = self._get_hg()
        try:
            main = _MAIN_SPIDER
            if main is not None and hasattr(main, "getProxyUrl"):
                hg.getProxyUrl = main.getProxyUrl
        except Exception:
            pass
        r = hg.playerContent("红果超清", _s(ep))
        if not isinstance(r, dict):
            raise _SrcErr("红果未返回播放地址")
        url = _s(r.get("url"))
        if not url:
            raise _SrcErr("红果未返回播放地址")
        header = r.get("header")
        if not isinstance(header, dict):
            header = {}
        return url, header

    def search(self, key, pg):
        hg = self._get_hg()
        j = hg.searchContent(key, False, str(pg))
        return self._adapt_list(j)


# ============================================================
# 饭果（西饭）— 纯 JSON API，无签名
# ============================================================
@_register
class _Fanguo(_Src):
    id = "fanguo"
    name = "饭果"
    cats = [("都市", "都市"), ("甜宠", "甜宠"), ("逆袭", "逆袭"), ("战神", "战神"),
            ("古装", "古装"), ("穿越", "穿越"), ("萌宝", "萌宝")]
    BASE = "https://xifan-api-cn.youlishipin.com"

    def _list(self, keyword, pg):
        if pg > 1:
            return [], False
        url = (self.BASE + "/xifan/search/getSearchList?reqType=search&offset=0"
               "&keyword=%s&quickEngineVersion=-1&scene=" % _q(keyword or "都市"))
        j = self.sess.get_json(url, headers={"Referer": self.BASE + "/"})
        items = []
        try:
            elements = j["result"]["elements"]
        except Exception:
            elements = []
        for el in elements:
            for c in (el.get("contents") or []):
                vo = c.get("duanjuVo") or {}
                vid = _pick(vo, "duanjuId", "duanju_id", "id")
                if not vid:
                    continue
                source = _pick(vo, "source")
                sid = "%s#%s" % (vid, source)
                items.append(_vod_item(
                    self.id, sid,
                    _pick(vo, "title", "name"),
                    _pick(vo, "coverImageUrl", "cover_image_url", "cover"),
                    ("全%s集" % _pick_int(vo, "total", "totalEpisodeNum"))
                    if _pick_int(vo, "total", "totalEpisodeNum") else ""))
        return items, False

    def cat(self, catid, pg):
        return self._list(catid or "都市", pg)

    def home(self, pg):
        return self._list("都市", pg)

    def search(self, key, pg):
        items, _ = self._list(key, 1)
        return items, False

    def detail(self, sid):
        vid, _, source = sid.partition("#")
        url = (self.BASE + "/xifan/drama/getDuanjuInfo?duanjuId=%s&source=%s"
               % (_q(vid), _q(source)))
        j = self.sess.get_json(url, headers={"Referer": self.BASE + "/"})
        result = j.get("result") or {}
        eps = result.get("episodeList") or []
        chapters = []
        for i, e in enumerate(eps):
            url_ = _pick(e, "playUrl", "play_url", "videoUrl")
            if not url_:
                continue
            no = _pick_int(e, "index", "episode", "sort") or (i + 1)
            chapters.append((url_, "第%d集" % no))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        info = result.get("duanjuInfo") or result
        return _vod_detail(
            self, sid, _pick(info, "title", "name", "duanjuName"),
            _pick(info, "coverImageUrl", "cover_image_url", "cover"),
            ("全%d集" % len(chapters)) if chapters else "",
            _pick(info, "desc", "description", "introduction"),
            chapters=chapters)

    def play(self, sid, ep):
        # ep 本身就是直链 playUrl（302 跳到签名 MP4，播放器跟随跳转）
        if not _s(ep).startswith("http"):
            raise _SrcErr("饭果分集地址无效")
        return _s(ep), {"Referer": self.BASE + "/"}


# ============================================================
# 星果（星星接口）— 纯 JSON API，无签名（注意是 http）
# ============================================================
@_register
class _Xingguo(_Src):
    id = "xingguo"
    name = "星果"
    cats = [("1287", "推荐一"), ("1288", "推荐二"), ("1289", "推荐三"),
            ("1290", "推荐四"), ("1291", "推荐五")]
    BASE = "http://read.api.duodutek.com"
    FIXED = {
        "productId": "2a8c14d1-72e7-498b-af23-381028eb47c0",
        "vestId": "2be070e0-c824-4d0e-a67a-8f688890cadb",
        "channel": "oppo19",
        "osType": "android",
        "version": "20",
        "token": "202509271001001446030204698626",
    }

    def _api(self, path, params):
        q = dict(self.FIXED)
        q.update(params)
        url = self.BASE + path + "?" + urllib.parse.urlencode(q)
        return self.sess.get_json(url)

    def _node(self, n):
        bid = _pick(n, "id", "bookId")
        if not bid:
            return None
        intro = _pick(n, "introduction", "desc", "description")
        sid = "%s@%s" % (bid, intro)
        heat = _pick_int(n, "heat")
        remark = (("%s万播放" % (heat / 10000)) if heat >= 10000
                  else ("%d播放" % heat)) if heat else ""
        total = _pick_int(n, "chapterCount", "total")
        if total and not remark:
            remark = "全%d集" % total
        return _vod_item(
            self.id, sid, _pick(n, "name", "title"),
            _pick(n, "icon", "cover"), remark, intro)

    def cat(self, catid, pg):
        j = self._api("/novel-api/app/pageModel/getResourceById",
                      {"resourceId": catid or "1287",
                       "pageNum": str(pg), "pageSize": "10"})
        data = j.get("data") or {}
        items = []
        for n in data.get("datalist") or []:
            v = self._node(n)
            if v:
                items.append(v)
        return items, len(items) >= 10

    def home(self, pg):
        return self.cat("1287", pg)

    def search(self, key, pg):
        j = self._api("/novel-api/basedata/book/searchBook",
                      {"key": key, "pageNum": "1", "pageSize": "20"})
        data = j.get("data") or {}
        items = []
        for n in data.get("datalist") or []:
            v = self._node(n)
            if v:
                items.append(v)
        return items, False

    def _find_urls(self, node, out):
        if isinstance(node, dict):
            for k in ("shortPlayUrl", "playUrl", "url"):
                u = node.get(k)
                if isinstance(u, str) and u.startswith("http"):
                    out.append(u)
            for k in ("shortPlayList", "chapterShortPlayVoList", "list",
                      "children"):
                v = node.get(k)
                if isinstance(v, list):
                    for x in v:
                        self._find_urls(x, out)
        elif isinstance(node, list):
            for x in node:
                self._find_urls(x, out)

    def detail(self, sid):
        bid = sid.split("@")[0]
        j = self._api("/novel-api/basedata/book/getChapterList",
                      {"bookId": bid})
        data = j.get("data")
        eps = data if isinstance(data, list) else []
        chapters = []
        title, pic, intro = "", "", ""
        for i, e in enumerate(eps):
            if not isinstance(e, dict):
                continue
            if i == 0:
                title = _pick(e, "bookName", "name", "title")
                pic = _pick(e, "icon", "cover")
                intro = _pick(e, "introduction", "desc")
            urls = []
            self._find_urls(e, urls)
            if not urls:
                continue
            no = _pick_int(e, "chapterNum", "sort", "index") or (i + 1)
            et = _pick(e, "chapterName", "name", "title") or ("第%d集" % no)
            chapters.append((urls[0], et))
        if not title:
            title = bid
        return _vod_detail(self, sid, title, pic,
                           ("全%d集" % len(chapters)) if chapters else "",
                           intro, chapters=chapters)

    def play(self, sid, ep):
        if not _s(ep).startswith("http"):
            raise _SrcErr("星果分集地址无效")
        return _s(ep), {}


# ============================================================
# 观果（围观）— 纯 JSON API；详情接口已挂（源码级确认）
# ============================================================
@_register
class _Guanguo(_Src):
    id = "guanguo"
    name = "观果"
    cats = [("", "全部")]
    BASE = "https://api.drama.9ddm.com"

    def _pub_query(self):
        ts = str(int(time.time() * 1000))[-10:]
        return {
            "version_code": "1500", "version_name": "1.5.0",
            "device_name": "Pixel 8 Pro", "device_type": "phone",
            "is_first_day": "true", "is_first_24h": "true",
            "app_launch_way": "icon",
            "default_homepage": "homepage_interaction",
            "device_owning_firm": "Google", "font_scale": "default",
            "os_type": "1", "clientInfo": _md5(ts),
        }

    def _search_api(self, subject, word, pg):
        url = (self.BASE + "/drama/home/search?"
               + urllib.parse.urlencode(self._pub_query()))
        body = {"audience": "全部", "order": "最新", "page": pg,
                "pageSize": 30, "searchWord": word, "subject": subject}
        j = self.sess.post_json(
            url, body,
            headers={"User-Agent": "okhttp/5.1.0",
                     "Referer": self.BASE + "/"})
        items = []
        data = j.get("data")
        rows = data if isinstance(data, list) else []
        for n in rows:
            if not isinstance(n, dict):
                continue
            vid = _pick(n, "oneId", "one_id", "id")
            if not vid:
                continue
            total = _pick_int(n, "episodeCount", "totalEpisodeCount")
            items.append(_vod_item(
                self.id, vid, _pick(n, "title", "name"),
                _pick(n, "horzPoster", "vertPoster", "cover"),
                ("全%d集" % total) if total else "",
                _pick(n, "intro", "description", "desc")))
        return items, len(items) >= 30

    def cat(self, catid, pg):
        return self._search_api(_s(catid), "", pg)

    def search(self, key, pg):
        return self._search_api("", key, 1)

    def detail(self, sid):
        raise _SrcErr("观果详情接口当前返回空数据，该源暂时无法查看分集")

    def play(self, sid, ep):
        raise _SrcErr("观果详情接口当前返回空数据，该源暂时无法播放")


# ============================================================
# 黄果AI — JSON 目录 + HTML 详情/播放，无登录，镜像轮换
# ============================================================
@_register
class _HuangguoAI(_Src):
    id = "hgai"
    name = "黄果AI"
    cats = [("ai-duanju", "AI短剧"), ("ai-manju", "AI漫剧"),
            ("ai-huanlian", "AI换脸"), ("ai-mogai", "AI魔改")]
    MAIN = "https://huangguoai.com"
    MIRRORS = ["https://ttvoij.ediayikma.cc", "https://thu.ediayikma.cc",
               "https://pku.ediayikma.cc", "https://fdu.ediayikma.cc",
               "https://thu.agdkczeyx.cc"]

    def _gen_mirrors(self, seed, n=8):
        out = []
        for i in range(n * 2):
            if len(out) >= n:
                break
            hx = hashlib.sha256(("%s:%d" % (seed, i)).encode()).hexdigest()
            pre = hx[:6].lstrip("0123456789")
            if len(pre) < 4:
                pre = hx[6:12].lstrip("0123456789")
            pre = (pre + "xxxxxx")[:6]
            if len(pre) >= 4:
                out.append("https://%s.ediayikma.cc" % pre)
        return out

    def _bases(self, path=""):
        bases = [self.MAIN] + self.MIRRORS
        bases += self._gen_mirrors(self.MAIN + path)
        seen = []
        for b in bases:
            if b not in seen:
                seen.append(b)
        return seen

    def _headers(self, base):
        return {"User-Agent": IPHONE_UA, "Referer": base + "/",
                "Accept-Language": "zh-CN,zh;q=0.9"}

    def _try_bases(self, path, timeout=12):
        last = None
        for base in self._bases(path):
            try:
                r = self.sess.fetch(base + path,
                                    headers=self._headers(base),
                                    timeout=timeout)
                if r.status == 200 and r.body:
                    return base, r
            except Exception as e:
                last = e
        raise _SrcErr("黄果AI线路暂不可用：%s" % last)

    def _walk_items(self, node, out):
        if isinstance(node, dict):
            vid = _pick(node, "id", "videoId", "video_id", "vid", "slug")
            title = _pick(node, "title", "name", "videoTitle", "video_title",
                          "videoName", "video_name")
            if vid and title:
                out.append(node)
                return
            for v in node.values():
                self._walk_items(v, out)
        elif isinstance(node, list):
            for v in node:
                self._walk_items(v, out)

    def _node(self, base, n):
        vid = _pick(n, "id", "videoId", "video_id", "vid", "slug")
        if not vid:
            m = re.search(r"/detail/([^\s\"'/?#]+)",
                          json.dumps(n, ensure_ascii=False))
            if m:
                vid = m.group(1)
        vid = _s(vid).strip().strip("/?#")
        if not vid or "/" in vid:
            vid = vid.split("/")[-1]
        if not vid:
            return None
        title = _pick(n, "title", "name", "videoTitle", "video_title",
                      "videoName", "video_name")
        if not title:
            return None
        pic = _pick(n, "cover", "coverUrl", "cover_url", "coverImage",
                    "cover_image", "image", "imageUrl", "thumbnail",
                    "poster", "posterUrl")
        total = _pick_int(n, "episode_count", "episodeCount", "total_episodes",
                          "totalEpisodes", "totalEpisode", "total_episode",
                          "episodes", "total")
        remark = _pick(n, "vod_remarks", "remark", "remarks")
        if not remark and total:
            fin = _pick(n, "is_finished")
            remark = ("全%d集" % total) if str(fin) in ("1", "true") else \
                ("更新至%d集" % total)
        score = _pick(n, "score", "rating")
        if score and "分" not in score:
            score += "分"
        return _vod_item(self.id, vid, title, _abs(base, pic), remark,
                         _pick(n, "desc", "description", "intro", "summary"))

    def cat(self, catid, pg):
        path = ("/api/videos/category/%s?sort=hot&page=%d&size=24"
                % (_q(catid or "ai-duanju"), pg))
        base, r = self._try_bases(path)
        try:
            j = json.loads(r.text())
        except Exception:
            raise _SrcErr("黄果AI目录解析失败")
        nodes = []
        self._walk_items(j, nodes)
        items, seen = [], set()
        for n in nodes:
            v = self._node(base, n)
            if v and v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                items.append(v)
        return items, len(nodes) >= 24

    def home(self, pg):
        return self.cat("ai-duanju", pg)

    def _detail_page(self, sid):
        path = "/detail/%s/" % _q(sid.strip().strip("/"))
        return self._try_bases(path)

    def detail(self, sid):
        base, r = self._detail_page(sid)
        html = r.text()
        title = ""
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        if m:
            title = _strip_tags(m.group(1)).split("_")[0].split("-")[0].strip()
        desc = ""
        m = re.search(r'''(?is)<meta[^>]+(?:name|property)=["'](?:description|og:description)["'][^>]+content=["'](.*?)["']''', html)
        if m:
            desc = m.group(1)
        pic = ""
        m = re.search(r'''(?is)<meta[^>]+property=["']og:image["'][^>]+content=["'](.*?)["']''', html)
        if m:
            pic = _abs(base, m.group(1))
        anchors = re.findall(
            r'''(?is)<a\b[^>]*href=["']([^"']*/video/[^"']+)["'][^>]*>(.*?)</a>''',
            html)
        chapters = []
        seen = set()
        for href, inner in anchors:
            href = _abs(base, href.strip())
            if href in seen:
                continue
            seen.add(href)
            tm = re.search(r'''(?is)\b(?:title|aria-label)=["'](.*?)["']''', inner)
            t = _strip_tags(tm.group(1) if tm else inner)
            no = _ep_no(t, len(chapters) + 1)
            chapters.append((href, t or ("第%d集" % no)))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        if not chapters:
            # 单视频页：直接提播放地址作为第 1 集
            media = self._extract_media(base, html, r.url)
            if media:
                chapters = [(media, "正片")]
        if not chapters:
            raise _SrcErr("黄果AI未找到分集")
        return _vod_detail(self, sid, title or sid, pic,
                           ("全%d集" % len(chapters)), desc,
                           chapters=chapters)

    def _extract_media(self, base, html, page_url):
        # 1) videoInitialData
        m = re.search(r'''(?is)<script[^>]+id=["']videoInitialData["'][^>]*>(.*?)</script>''', html)
        if m:
            try:
                import html as _html
                j = json.loads(_html.unescape(m.group(1)))
            except Exception:
                j = None
            if isinstance(j, dict):
                for k in ("videoSrc", "videoUrl", "playUrl"):
                    u = _pick(j, k)
                    if self._ok_media(u):
                        return self._norm_media(base, page_url, u)
                eps = j.get("epPlaySrcs")
                if isinstance(eps, dict) and eps:
                    key = _pick(j, "ep", "episode")
                    if not key:
                        pm = re.search(r"/ep-(\d+)", page_url)
                        if pm:
                            key = pm.group(1)
                    if key in eps and self._ok_media(eps[key]):
                        return self._norm_media(base, page_url, eps[key])
                    def _ek(k):
                        mm = re.search(r"(\d+)", _s(k))
                        return int(mm.group(1)) if mm else 0
                    for k in sorted(eps, key=_ek):
                        if self._ok_media(eps[k]):
                            return self._norm_media(base, page_url, eps[k])
        # 2) data-play-src
        m = re.search(r'''data-play-src=["']([^"']+)["']''', html)
        if m and self._ok_media(m.group(1)):
            return self._norm_media(base, page_url, m.group(1))
        # 3) 通用正则
        for m in re.finditer(
                r'''["']?(?:videoSrc|videoUrl|playUrl|src|url)["']?\s*[:=]\s*["']([^"']+\.(?:m3u8|mp4)[^"']*)["']''',
                html):
            return self._norm_media(base, page_url, m.group(1))
        return ""

    @staticmethod
    def _ok_media(u):
        u = _s(u)
        return bool(u) and (".m3u8" in u or ".mp4" in u)

    @staticmethod
    def _norm_media(base, page_url, u):
        import html as _html
        u = _html.unescape(_s(u)).replace("\\/", "/").strip()
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("http://"):
            u = "https://" + u[7:]
        elif not u.startswith("https://"):
            u = _abs(page_url or base, u)
        return u

    def play(self, sid, ep):
        ep = _s(ep)
        if self._ok_media(ep):
            return ep, {"Referer": self.MAIN + "/",
                        "User-Agent": IPHONE_UA}
        # ep 是分集页面地址
        base = self.MAIN
        r = self.sess.fetch(ep, headers=self._headers(base), timeout=15)
        media = self._extract_media(base, r.text(), r.url)
        if not media:
            raise _SrcErr("黄果AI未找到播放地址")
        return media, {"Referer": ep, "User-Agent": IPHONE_UA}

    def search(self, key, pg):
        # 无服务端搜索：拉前两页按标题过滤
        items = []
        for p in (1, 2):
            try:
                rows, _ = self.cat("ai-duanju", p)
            except Exception:
                break
            for v in rows:
                if key in v["vod_name"]:
                    items.append(v)
            if len(items) >= 30:
                break
        return items[:30], False


# ============================================================
# 黄果视频 — HTML 解析，无登录
# ============================================================
@_register
class _HuangguoVideo(_Src):
    id = "hgv"
    name = "黄果视频"
    cats = [("", "全部")]
    BASE = "https://huangguo.video"

    def _headers(self):
        return {"User-Agent": IPHONE_UA, "Referer": self.BASE + "/",
                "Accept-Language": "zh-CN,zh;q=0.9"}

    def _cards(self, html):
        blocks = re.findall(
            r'''(?is)<article\b[^>]*class=["'][^"']*\bvideo-card\b[^"']*["'][^>]*>.*?</article>''',
            html)
        if not blocks:
            blocks = re.findall(r"(?is)<article\b[^>]*video-card.*?</article>",
                                html)
        items = []
        for b in blocks:
            m = re.search(
                r'''(?is)<a\b[^>]*href=["']([^"']*/(?:series|video)/([^"'/?#]+)[^"']*)["'][^>]*>''',
                b)
            if not m:
                continue
            sid = m.group(1).strip().strip("/")
            if sid.startswith("http"):
                sid = urllib.parse.urlparse(sid).path.strip("/")
            title = ""
            tm = re.search(r'''(?is)(?:title|alt|aria-label)=["']([^"']+)["']''', b)
            if tm:
                title = tm.group(1).strip()
            if not title:
                title = _strip_tags(b)[:60]
            pic = ""
            im = re.search(r'''(?is)<img\b[^>]*?(?:data-src|data-original|src)=["']([^"']+)["']''', b)
            if im:
                pic = _abs(self.BASE, im.group(1))
            desc = ""
            dm = re.search(r'''(?is)(?:data-description|description)=["']([^"']+)["']''', b)
            if dm:
                desc = dm.group(1)
            remark = ""
            rm = re.search(r'''(?is)class=["'][^"']*(?:bg-black/55|text-gold-dim)[^"']*["'][^>]*>(.*?)<''', b)
            if rm:
                remark = _strip_tags(rm.group(1))
            items.append(_vod_item(self.id, sid, title, pic, remark, desc))
        return items

    def cat(self, catid, pg):
        url = self.BASE + "/videos?page=%d" % pg
        if catid:
            url += "&category=" + _q(catid)
        html = self.sess.get_text(url, headers=self._headers())
        if _cf_blocked(html):
            raise _SrcErr("%s被 Cloudflare 拦截，换网络或稍后重试" % self.name)
        items = self._cards(html)
        return items, len(items) >= 20

    def detail(self, sid):
        if not sid.startswith(("series/", "video/")):
            sid = "series/" + sid
        url = self.BASE + "/" + sid
        html = self.sess.get_text(url, headers=self._headers())
        if _cf_blocked(html):
            raise _SrcErr("%s被 Cloudflare 拦截，换网络或稍后重试" % self.name)
        title = ""
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        if m:
            title = _strip_tags(m.group(1)).split("_")[0].split("-")[0].strip()
        pic = ""
        m = re.search(r'''(?is)<meta[^>]+property=["']og:image["'][^>]+content=["'](.*?)["']''', html)
        if m:
            pic = _abs(self.BASE, m.group(1))
        chapters = []
        if sid.startswith("series/"):
            blocks = re.findall(
                r'''(?is)<article\b[^>]*class=["'][^"']*\bvideo-card\b[^"']*["'][^>]*>.*?</article>''',
                html)
            for b in blocks:
                m = re.search(r'''(?is)<a\b[^>]*href=["']([^"']*video/[^"']*)["']''', b)
                if not m:
                    continue
                hm = re.search(r'''data-hls=["']([^"']+)["']''', b)
                media = _abs(self.BASE, hm.group(1)) if hm else ""
                if not media:
                    continue
                tm = re.search(r'''(?is)(?:title|alt|aria-label)=["']([^"']+)["']''', b)
                t = tm.group(1).strip() if tm else _strip_tags(b)[:40]
                chapters.append((media, t or ("第%d集" % (len(chapters) + 1))))
            chapters.sort(key=lambda x: _ep_no(x[1]))
        else:
            m = re.search(r'''data-hls=["']([^"']+)["']''', html)
            if m:
                chapters = [(_abs(self.BASE, m.group(1)), "正片")]
        if not chapters:
            raise _SrcErr("黄果视频未找到分集")
        return _vod_detail(self, sid, title or sid, pic,
                           ("全%d集" % len(chapters)), "",
                           chapters=chapters)

    def play(self, sid, ep):
        if _s(ep).startswith("http"):
            return _s(ep), {"Referer": self.BASE + "/"}
        raise _SrcErr("黄果视频分集地址无效")

    def search(self, key, pg):
        items = []
        for p in (1, 2):
            try:
                rows, _ = self.cat("", p)
            except Exception:
                break
            for v in rows:
                if key in v["vod_name"]:
                    items.append(v)
            if len(items) >= 30:
                break
        return items[:30], False


# ============================================================
# 河果（河马剧场）— Next.js __NEXT_DATA__ 解析
# ============================================================
@_register
class _Heguo(_Src):
    id = "heguo"
    name = "河果"
    cats = [("462", "甜宠"), ("1102", "古装仙侠"), ("1145", "现代言情"),
            ("1170", "青春"), ("585", "豪门恩怨"), ("417-464", "逆袭"),
            ("439-465", "重生"), ("1159", "系统"), ("1147", "总裁"),
            ("943", "职场商战")]
    BASE = "https://www.kuaikaw.cn"

    def _next_data(self, html):
        m = re.search(
            r'''(?is)<script[^>]+id=["']__NEXT_DATA__[^>]*>(.*?)</script>''',
            html)
        if not m:
            return {}
        try:
            j = json.loads(m.group(1))
            return j.get("props", {}).get("pageProps", {}) or {}
        except Exception:
            return {}

    def _node(self, n):
        bid = _pick(n, "bookId", "book_id", "id")
        if not bid:
            return None
        total = _pick_int(n, "totalChapterNum")
        return _vod_item(
            self.id, bid, _pick(n, "bookName", "title", "name"),
            _pick(n, "coverWap", "cover", "coverUrl"),
            ("全%d集" % total) if total else "",
            _pick(n, "introduction", "intro", "description"))

    def _parse_list_page(self, props):
        items, seen = [], set()
        buckets = []
        for k in ("bookList", "bannerList", "recommendList"):
            v = props.get(k)
            if isinstance(v, list):
                buckets += v
        for col in props.get("seoColumnVos") or []:
            if isinstance(col, dict):
                buckets += col.get("bookInfos") or []
        for n in buckets:
            if not isinstance(n, dict):
                continue
            v = self._node(n)
            if v and v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                items.append(v)
        return items

    def cat(self, catid, pg):
        if pg == 1 and not catid:
            url = self.BASE + "/"
        else:
            url = "%s/browse/%s/%d" % (self.BASE, _q(catid or "462"), pg)
        html = self.sess.get_text(url, headers={"Referer": self.BASE + "/"})
        props = self._next_data(html)
        items = self._parse_list_page(props)
        pages = _pick_int(props, "pages", "page")
        more = (pg < pages) if pages else len(items) >= 20
        return items, more

    def home(self, pg):
        return self.cat("", pg)

    def detail(self, sid):
        url = "%s/drama/%s" % (self.BASE, _q(sid))
        html = self.sess.get_text(url, headers={"Referer": self.BASE + "/"})
        props = self._next_data(html)
        info = props.get("bookInfoVo") or {}
        v = self._node(info) or _vod_item(self.id, sid, sid)
        chapters = []
        for i, c in enumerate(props.get("chapterList") or []):
            if not isinstance(c, dict):
                continue
            cid = _pick(c, "chapterId", "chapter_id", "id")
            if not cid:
                continue
            no = _pick_int(c, "chapterNum", "sort", "index") or (i + 1)
            t = _pick(c, "chapterName", "title") or ("第%d集" % no)
            chapters.append((cid, t))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        v.update({
            "vod_content": _pick(info, "introduction", "intro", "description"),
            "vod_remarks": ("全%d集" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in chapters),
        })
        return v

    def play(self, sid, ep):
        url = "%s/episode/%s/%s" % (self.BASE, _q(sid), _q(ep))
        html = self.sess.get_text(url, headers={"Referer": self.BASE + "/"})
        props = self._next_data(html)
        ci = props.get("chapterInfo") or {}
        vv = ci.get("chapterVideoVo") or {}
        media = _pick(vv, "mp4", "mp4720p", "vodMp4Url")
        if not media:
            m = re.search(r"""https?://[^"'\\\s<>]+\.(?:mp4|m3u8)[^"'\\\s<>]*""",
                          html)
            if m:
                media = m.group(0)
        if not media:
            raise _SrcErr("河果未找到播放地址")
        return _abs(self.BASE, media), {"Referer": url}

    def search(self, key, pg):
        url = self.BASE + "/seo/video/6007"
        j = self.sess.post_json(
            url, {"sourceType": 1, "keyword": key, "index": 1},
            headers={"Referer": self.BASE + "/",
                     "pname": "www.kuaikaw.cn"})
        data = j.get("data") or {}
        items = []
        for n in data.get("bookList") or []:
            v = self._node(n)
            if v:
                items.append(v)
        return items, False


# ============================================================
# MacCMS 网页类通用（花果/网果/发果/伍果；皮果被 Cloudflare 拦截）
# ============================================================

def _cf_blocked(html):
    """Cloudflare 'Just a moment' 拦截页检测"""
    if not html:
        return False
    low = html[:3000].lower()
    return ("just a moment" in low and "cloudflare" in low) or \
        "cf-challenge" in low or "cf_chl_" in low


class _MacCMS(_Src):
    BASE = ""
    UA = PC_UA

    def _headers(self, referer=None):
        return {"User-Agent": self.UA, "Referer": referer or self.BASE + "/"}

    # -- 各站覆盖 --
    def cat_url(self, catid, pg):
        raise NotImplementedError

    def detail_urls(self, sid):
        raise NotImplementedError

    def search_url(self, key, pg):
        raise NotImplementedError

    # -- 通用卡片解析（排除 /vod/type/、/vod/search/ 分类链接） --
    _DETAIL_HREF = re.compile(
        r'''(?is)<a\b[^>]*href=["']([^"']*(?:/detail/|/zywview/|/zywdetail/|/voddetail/|/xzyxvd/|/dramaDetail/|/movie/|/p/66/d/|/vod/(?!type/|search/|play/))[^"']*)["'][^>]*>(.*?)</a>''')

    def _cards(self, html, page_url):
        items, seen = [], set()
        for m in self._DETAIL_HREF.finditer(html):
            href, inner = m.group(1).strip(), m.group(2)
            if re.search(r"(?i)(app|下载|down)", _strip_tags(inner)[:20]):
                continue
            url = _abs(page_url, href)
            sid = self._sid_from_url(url)
            if not sid or sid in seen:
                continue
            # 封面：先看 <a> 标签自身（如 data-original 在锚标签上），再往前找最近的 img
            pic = ""
            start = max(0, m.start() - 3000)
            seg = html[start:m.start()]
            am0 = re.search(
                r'''(?is)\b(?:data-original|data-src|src)=["']([^"']+)["']''',
                m.group(0))
            if am0:
                pic = _abs(page_url, am0.group(1))
            if not pic:
                imgs = re.findall(
                    r'''(?is)<img\b[^>]*?(?:data-original|data-src|src)=["']([^"']+)["']''',
                    seg)
                if imgs:
                    pic = _abs(page_url, imgs[-1])
            title = ""
            tm = re.search(r'''(?is)\btitle=["']([^"']+)["']''', m.group(0))
            if tm:
                title = tm.group(1).strip()
            if not title:
                am = re.search(r'''(?is)\balt=["']([^"']+)["']''', seg[-800:])
                if am:
                    title = am.group(1).strip()
            if not title:
                title = _strip_tags(inner).strip()[:60]
            if not title:
                continue
            remark = ""
            rm = re.search(
                r'''(?is)(?:pic-text|module-item-note|imagelastChapter)[^>]*>([^<]{1,40})<''',
                seg[-1200:])
            if rm:
                remark = _strip_tags(rm.group(1))
            seen.add(sid)
            items.append(_vod_item(self.id, sid, title, pic, remark))
        return items

    def _sid_from_url(self, url):
        try:
            path = urllib.parse.urlparse(url).path
        except Exception:
            return ""
        m = re.search(r"/(\d+)\.html?$", path)
        if m:
            return m.group(1)
        m = re.search(r"/(\d+)/?$", path)
        if m:
            return m.group(1)
        m = re.search(r"/movie/([^/?#]+)", path)
        if m:
            return m.group(1)
        m = re.search(r"[?&](?:id|vid)=(\d+)", url)
        if m:
            return m.group(1)
        return ""

    # -- 通用分集解析 --
    _EP_HREF = re.compile(
        r'''(?is)<a\b[^>]*href=["']([^"']*(?:/play/|/vodplay/|/zyxplay/|/zywplay/|/xzyxplay/|/drama-play|episode_id=)[^"']*)["'][^>]*>(.*?)</a>''')

    def _episodes(self, html, page_url):
        eps, seen = [], set()
        for m in self._EP_HREF.finditer(html):
            href = _abs(page_url, m.group(1).strip())
            t = _strip_tags(m.group(2)).strip()[:40]
            if re.search(r"(?i)(app|下载|down)", t):
                continue
            if href in seen:
                continue
            seen.add(href)
            eps.append((href, t or ("第%d集" % (len(eps) + 1))))
        eps.sort(key=lambda x: _ep_no(x[1]))
        return eps

    # -- 通用播放提取 --
    def _extract_play(self, html, page_url):
        m = re.search(r"""player_aaaa\s*=\s*(\{.*?\})\s*</script>""",
                      html, re.S)
        if m:
            try:
                j = json.loads(m.group(1))
                u = _pick(j, "url")
                if u:
                    return self._norm_play(u, page_url)
            except Exception:
                pass
        m = re.search(r'''\$\.url\s*=\s*"([^"]+)"''', html)
        if m:
            return self._norm_play(m.group(1), page_url)
        m = re.search(r'''"url"\s*:\s*"([^"]+\.(?:m3u8|mp4)[^"]*)"''', html)
        if m:
            return self._norm_play(m.group(1), page_url)
        m = re.search(r"""https?://[^"'\\\s<>]+\.(?:m3u8|mp4)[^"'\\\s<>]*""",
                      html)
        if m:
            return self._norm_play(m.group(0), page_url)
        return ""

    def _norm_play(self, u, page_url):
        import html as _html
        u = _html.unescape(_s(u)).replace("\\/", "/").strip()
        # \uXXXX 转义
        try:
            u = u.encode("utf-8").decode("unicode_escape")
        except Exception:
            pass
        # 去掉 JS 拼接时带上的尾部标点（如 "...,https://x.m3u8,"）
        u = u.rstrip(" \t\r\n,;\"'")
        if not u.startswith("http"):
            u = _abs(page_url, u)
        # /p./ 或 /c1./ 伪装：取倒数第二段解码拼 index.m3u8
        if re.search(r"/[pc]1?\./", u):
            parts = [p for p in urllib.parse.urlparse(u).path.split("/")
                     if p]
            if len(parts) >= 2:
                try:
                    seg = base64.b64decode(parts[-2] + "==").decode("utf-8",
                                                                   "ignore")
                except Exception:
                    seg = ""
                if seg:
                    u = u.rsplit("/", 1)[0] + "/" + seg.strip("/") \
                        + "/index.m3u8"
        return u

    # -- 标准流程 --
    def cat(self, catid, pg):
        url = self.cat_url(_s(catid), pg)
        html = self.sess.get_text(url, headers=self._headers())
        if _cf_blocked(html):
            raise _SrcErr("%s被 Cloudflare 拦截，换网络或稍后重试" % self.name)
        items = self._cards(html, url)
        return items, len(items) >= 10

    def home(self, pg):
        return self.cat("", pg)

    def detail(self, sid):
        last = None
        for url in self.detail_urls(sid):
            try:
                html = self.sess.get_text(url,
                                          headers=self._headers())
            except Exception as e:
                last = e
                continue
            title = ""
            m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
            if m:
                title = _strip_tags(m.group(1)).split("_")[0].split("-")[0].strip()
            pic = ""
            m = re.search(
                r'''(?is)<img\b[^>]*?(?:data-original|data-src|src)=["']([^"']+)["'][^>]*class=["'][^"']*(?:poster|cover|vod-pic)''',
                html)
            if not m:
                m = re.search(
                    r'''(?is)<img\b[^>]*?(?:data-original|data-src|src)=["']([^"']+)["']''',
                    html)
            if m:
                pic = _abs(url, m.group(1))
            desc = ""
            m = re.search(
                r'''(?is)(?:vod-content|content|desc|detail-content)[^>]*>(.*?)</(?:div|p)>''',
                html)
            if m:
                desc = _strip_tags(m.group(1))[:2000]
            eps = self._episodes(html, url)
            if not title and not eps:
                last = _SrcErr("页面无内容")
                continue
            # 详情页分集不全时，跟进第一集播放页补全（如伍果详情页只有"立即播放"）
            if len(eps) <= 1:
                for href, _t in eps:
                    if ("/play/" in href or "/vodplay/" in href
                            or "zyxplay" in href or "zywplay" in href
                            or "xzyxplay" in href):
                        try:
                            ph = self.sess.get_text(
                                href, headers=self._headers(url), timeout=12)
                            peps = self._episodes(ph, href)
                            if len(peps) > len(eps):
                                eps = peps
                        except Exception:
                            pass
                        break
            chapters = [(href, t) for href, t in eps]
            return _vod_detail(self, sid, title or sid, pic,
                               ("全%d集" % len(chapters)) if chapters else "",
                               desc, chapters=chapters)
        raise _SrcErr("详情页均不可用：%s" % last)

    def play(self, sid, ep):
        html = self.sess.get_text(_s(ep),
                                  headers=self._headers())
        media = self._extract_play(html, _s(ep))
        if not media or not media.startswith("http"):
            raise _SrcErr("%s未找到播放地址" % self.name)
        return media, {"Referer": _s(ep), "User-Agent": self.UA}

    def search(self, key, pg):
        url = self.search_url(key, pg)
        html = self.sess.get_text(url, headers=self._headers())
        return self._cards(html, url), False


@_register
class _Huaguo(_MacCMS):
    id = "huaguo"
    name = "花果"
    cats = [("27", "短剧")]
    BASE = "https://www.zywest263.com"

    def cat_url(self, catid, pg):
        if pg == 1 and not catid:
            return self.BASE + "/"
        return ("%s/search.html?page=%d&searchtype=5&tid=%s&year="
                % (self.BASE, pg, _q(catid or "27")))

    def detail_urls(self, sid):
        return ["%s/zywview/%s.html" % (self.BASE, sid),
                "%s/zywdetail/%s.html" % (self.BASE, sid),
                "%s/detail/%s.html" % (self.BASE, sid)]

    def search_url(self, key, pg):
        return "%s/search.html?searchword=%s" % (self.BASE, _q(key))


@_register
class _Wangguo(_MacCMS):
    id = "wangguo"
    name = "网果"
    cats = [("", "全部")]
    BASE = "https://www.duanju2.com"

    def cat_url(self, catid, pg):
        if not catid:
            return self.BASE + "/show/duanju-----------.html"
        c = _s(catid)
        if c.endswith("---.html"):
            c = c[:-len("---.html")]
        return "%s/%s%d---.html" % (self.BASE, c, pg)

    def detail_urls(self, sid):
        return ["%s/vod/%s.html" % (self.BASE, sid),
                "%s/index.php/vod/detail/id/%s.html" % (self.BASE, sid),
                "%s/detail/%s.html" % (self.BASE, sid)]

    def search_url(self, key, pg):
        return "%s/search/%s----------1---.html" % (self.BASE, _q(key))


@_register
class _Faguo(_MacCMS):
    id = "faguo"
    name = "发果"
    cats = [("", "全部")]
    BASE = "https://www.xzyx168.com"

    def cat_url(self, catid, pg):
        if not catid:
            return "%s/xzyxvt/%szmn.html" % (self.BASE, pg)
        c = _s(catid)
        if "zmn" not in c:
            raise _SrcErr("发果分类无效")
        c = c.replace("zmn", "")
        return "%s/%s%dzmn.html" % (self.BASE, c, pg)

    def detail_urls(self, sid):
        return ["%s/xzyxvd/%s.html" % (self.BASE, sid),
                "%s/detail/%s.html" % (self.BASE, sid),
                "%s/voddetail/%s.html" % (self.BASE, sid)]

    def search_url(self, key, pg):
        return "%s/xzyxvc/%s-wdyswzqun1num.html" % (self.BASE, _q(key))


@_register
class _Wuguo(_MacCMS):
    id = "wuguo"
    name = "伍果"
    cats = [("", "全部")]
    BASE = "https://www.duanju55.com"

    def cat_url(self, catid, pg):
        if not catid:
            return self.BASE + "/"
        c = _s(catid)
        if c.endswith(".html"):
            c = c[:-5]
        return "%s%s/page/%d.html" % (self.BASE, c, pg)

    def detail_urls(self, sid):
        return ["%s/index.php/vod/detail/id/%s.html" % (self.BASE, sid),
                "%s/dramaDetail/%s.html" % (self.BASE, sid),
                "%s/detail/%s.html" % (self.BASE, sid)]

    def search_url(self, key, pg):
        return ("%s/index.php/vod/search/page/1/wd/%s.html"
                % (self.BASE, _q(key)))


# ============================================================
# 芽果（星芽接口）— 先 POST 登录拿 token
# ============================================================
@_register
class _Yaguo(_Src):
    id = "yaguo"
    name = "芽果"
    cats = [("1", "剧场"), ("9", "榜单")]
    BASE = "https://app.whjzjx.cn"
    LOGIN = "https://u.shytkjgs.com/user/v1/account/login"
    DEVICE = "24250683a3bdb3f118dff25ba4b1cba1a"

    def __init__(self):
        super().__init__()
        self._token = ""
        self._token_at = 0
        self._dyn_cats = None

    def _auth_headers(self):
        return {"authorization": self._token, "platform": "1",
                "version_name": "3.8.3.1"}

    def _token_get(self):
        if self._token and time.time() - self._token_at < 6 * 3600:
            return self._token
        j = self.sess.post_json(
            self.LOGIN, {"device": self.DEVICE},
            headers={"platform": "1"}, timeout=15)
        data = j.get("data") if isinstance(j.get("data"), dict) else {}
        token = _pick(data, "token") or _pick(j, "token")
        if not token:
            raise _SrcErr("芽果登录未返回 token")
        self._token, self._token_at = token, time.time()
        return token

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        try:
            self._token_get()
            j = self.sess.get_json(self.BASE + "/cloud/v2/theater/classes",
                                   headers=self._auth_headers(), timeout=8)
            cats = []
            for g in j.get("data") or []:
                for c in (g.get("alg_class") or []):
                    cid = _pick(c, "id")
                    cn = _pick(c, "class_name", "name")
                    if cid and cn:
                        cats.append((cid, cn))
            if cats:
                self._dyn_cats = cats[:24]
                return self._dyn_cats
        except Exception:
            pass
        return self.cats

    def _node(self, n):
        node = n.get("theater") if isinstance(n.get("theater"), dict) else n
        vid = _pick(node, "id", "theater_id", "theater_parent_id")
        if not vid:
            return None
        total = _pick_int(node, "total", "total_num", "current_num")
        return _vod_item(
            self.id, vid, _pick(node, "title", "name"),
            _pick(node, "cover_url", "son_cover_url", "cover"),
            ("全%d集" % total) if total else "",
            _pick(node, "descrip", "introduction", "desc"))

    def cat(self, catid, pg):
        self._token_get()
        catid = catid or "1"
        if catid == "9":
            j = self.sess.get_json(
                self.BASE + "/cloud/v1/first_level_ranking/detail?id=1",
                headers=self._auth_headers())
            rows = (j.get("data") or {}).get("list") or []
            items = [v for v in (self._node(n) for n in rows) if v]
            return items, False
        url = (self.BASE + "/cloud/v2/theater/home_page?" +
               urllib.parse.urlencode(
                   {"theater_class_id": catid, "type": "1", "class2_ids": "0",
                    "page_num": str(pg), "page_size": "24"}))
        j = self.sess.get_json(url, headers=self._auth_headers())
        data = j.get("data") or {}
        rows = data.get("list") or []
        items = [v for v in (self._node(n) for n in rows) if v]
        total = _pick_int(data, "total")
        is_end = data.get("is_end")
        more = (not is_end) if is_end is not None else (
            len(rows) >= 24 if not total else pg * 24 < total)
        return items, more

    def home(self, pg):
        return self.cat("1", pg)

    def detail(self, sid):
        self._token_get()
        url = (self.BASE + "/v2/theater_parent/detail?" +
               urllib.parse.urlencode({"theater_parent_id": sid}))
        j = self.sess.get_json(url, headers=self._auth_headers())
        data = j.get("data") or {}
        eps = data.get("theaters") or []
        chapters = []
        title = _pick(data, "title", "theater_title", "name")
        pic = _pick(data, "cover_url", "cover")
        intro = _pick(data, "descrip", "introduction", "desc", "intro")
        for i, e in enumerate(eps):
            u = _pick(e, "son_video_url", "video_url")
            if not u:
                continue
            if not title:
                title = _pick(e, "theater_title", "title", "name")
            if not pic:
                pic = _pick(e, "cover_url", "son_cover_url", "cover")
            if not intro:
                intro = _pick(e, "descrip", "introduction", "desc")
            no = _pick_int(e, "num", "sort") or (i + 1)
            t = _pick(e, "son_title", "title") or ("第%d集" % no)
            chapters.append((u, t))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        return _vod_detail(self, sid, title or sid, pic,
                           ("全%d集" % len(chapters)) if chapters else "",
                           intro, chapters=chapters)

    def play(self, sid, ep):
        if not _s(ep).startswith("http"):
            raise _SrcErr("芽果分集地址无效")
        return _s(ep), {"Referer": self.BASE + "/"}

    def search(self, key, pg):
        self._token_get()
        j = self.sess.post_json(self.BASE + "/v3/search", {"text": key},
                                headers=self._auth_headers())
        data = j.get("data") or {}
        rows = data.get("list") or []
        if not rows:
            th = data.get("theater") or {}
            rows = th.get("search_data") or []
        items = [v for v in (self._node(n) for n in rows) if v]
        return items, False


# ============================================================
# 剧果 — 访客鉴权 + CloudFront Cookie 播放
# ============================================================
@_register
class _Huangju(_Src):
    id = "huangju"
    name = "剧果"
    cats = [("", "全部")]
    BASE = "https://api.huangju.net"
    WEB = "https://huangju.net"

    def __init__(self):
        super().__init__()
        self._token = ""
        self._token_at = 0
        self._dyn_cats = None

    def _auth(self):
        if self._token and time.time() - self._token_at < 3600:
            return self._token
        j = self.sess.post_json(
            self.BASE + "/auth/guest",
            {"deviceId": str(uuid.uuid4())}, timeout=15)
        token = _pick(j, "token") or _pick(j.get("data") or {}, "token")
        if not token:
            raise _SrcErr("剧果访客鉴权失败")
        self._token, self._token_at = token, time.time()
        return token

    def _h(self):
        return {"Authorization": "Bearer " + self._auth(),
                "Referer": self.WEB + "/"}

    def _get(self, path, params=None):
        url = self.BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            return self.sess.get_json(url, headers=self._h())
        except Exception as e:
            if "401" in str(e) or "403" in str(e):
                self._token = ""
                return self.sess.get_json(url, headers=self._h())
            raise

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        try:
            j = self._get("/categories")
            rows = j if isinstance(j, list) else (
                j.get("data") if isinstance(j.get("data"), list)
                else j.get("categories") or [])
            cats = []
            for c in rows if isinstance(rows, list) else []:
                cid = _pick(c, "slug", "id")
                cn = _pick(c, "name", "title")
                if cid and cn:
                    cats.append((cid, cn))
            if cats:
                self._dyn_cats = [("", "全部")] + cats[:20]
                return self._dyn_cats
        except Exception:
            pass
        return self.cats

    def _node(self, n):
        vid = _pick(n, "slug", "slug_id", "drama_id", "id")
        if not vid:
            return None
        total = _pick_int(n, "episode_count", "total_episodes", "total",
                          "episodeCount")
        return _vod_item(
            self.id, vid, _pick(n, "title", "name"),
            _pick(n, "cover", "cover_url", "coverUrl", "poster"),
            ("全%d集" % total) if total else "",
            _pick(n, "desc", "description", "intro"))

    def _dramas(self, params, pg):
        params = dict(params or {})
        params["page"] = str(pg)
        j = self._get("/dramas", params)
        # 真实结构：{"total","page","pageSize","items":[]}；兼容 {"data":{...}}
        data = j.get("data") if isinstance(j.get("data"), dict) else j
        rows = []
        if isinstance(data, dict):
            rows = data.get("items") or data.get("dramas") or \
                data.get("list") or []
        elif isinstance(data, list):
            rows = data
        items = [v for v in (self._node(n) for n in rows
                             if isinstance(n, dict)) if v]
        total = _pick_int(data, "total") if isinstance(data, dict) else 0
        psize = _pick_int(data, "pageSize", "page_size") or 20
        more = (pg * psize < total) if total else len(items) >= psize
        return items, more

    def cat(self, catid, pg):
        if catid:
            return self._dramas({"category": catid}, pg)
        return self._dramas({"sort": "new"}, pg)

    def home(self, pg):
        return self._dramas({"sort": "new"}, pg)

    def search(self, key, pg):
        return self._dramas({"q": key}, 1)

    def detail(self, sid):
        j = self._get("/dramas/" + _q(sid))
        data = j.get("data") or j
        v = self._node(data) or _vod_item(self.id, sid, sid)
        v["vod_content"] = _pick(data, "desc", "description", "intro")
        chapters = []
        for e in data.get("episodes") or []:
            if not isinstance(e, dict):
                continue
            if e.get("playable") is False:
                continue
            eid = _pick(e, "id")
            if not eid:
                continue
            no = _pick_int(e, "epNo", "ep_no", "sort", "index") \
                or (len(chapters) + 1)
            t = _pick(e, "title", "name") or ("第%d集" % no)
            chapters.append((eid, t))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        v.update({
            "vod_remarks": ("全%d集" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in chapters),
        })
        return v

    def play(self, sid, ep):
        r = self.sess.fetch(self.BASE + "/play/" + _q(ep),
                            headers=self._h(), timeout=15)
        try:
            j = json.loads(r.text())
        except Exception:
            raise _SrcErr("剧果播放接口返回无效")
        # 真实结构是裸 JSON：{"episodeId","dramaId","epNo","url",...}；兼容 data 包裹
        data = j.get("data") if isinstance(j.get("data"), dict) else j
        media = _pick(data, "url", "play_url", "video_url", "src")
        if not media:
            # 也可能是纯文本 URL
            t = r.text().strip()
            if t.startswith("http"):
                media = t.split()[0]
        if not media:
            raise _SrcErr("剧果未返回播放地址")
        ck = self.sess.cookies
        trio = "; ".join("%s=%s" % (k, ck[k]) for k in
                         ("CloudFront-Policy", "CloudFront-Signature",
                          "CloudFront-Key-Pair-Id") if k in ck)
        header = {"Referer": self.WEB + "/"}
        if trio:
            header["Cookie"] = trio
        return media, header


# ============================================================
# 猫果（七猫签名）— qm-params + MD5，参数顺序必须与原版一致
# ============================================================
@_register
class _Maoguo(_Src):
    id = "maoguo"
    name = "猫果"
    cats = [("0", "推荐")]
    STORE = "https://api-store.qmplaylet.com"
    READ = "https://api-read.qmplaylet.com"
    KEY = "d3dGiJc651gSQ8w1"
    TRACK_ID = "ec1280db127955061754851657967"
    # 与 Go 源码 duanjuMaoguoCharMap 逐字一致（'=' 不在表中，保持原样）
    CHARMAP = {
        '+': 'P', '/': 'X', '0': 'M', '1': 'U', '2': 'l', '3': 'E',
        '4': 'r', '5': 'Y', '6': 'W', '7': 'b', '8': 'd', '9': 'J',
        'A': '9', 'B': 's', 'C': 'a', 'D': 'I', 'E': '0', 'F': 'o',
        'G': 'y', 'H': '_', 'I': 'H', 'J': 'G', 'K': 'i', 'L': 't',
        'M': 'g', 'N': 'N', 'O': 'A', 'P': '8', 'Q': 'F', 'R': 'k',
        'S': '3', 'T': 'h', 'U': 'f', 'V': 'R', 'W': 'q', 'X': 'C',
        'Y': '4', 'Z': 'p', 'a': 'm', 'b': 'B', 'c': 'O', 'd': 'u',
        'e': 'c', 'f': '6', 'g': 'K', 'h': 'x', 'i': '5', 'j': 'T',
        'k': '-', 'l': '2', 'm': 'z', 'n': 'S', 'o': 'Z', 'p': '1',
        'q': 'V', 'r': 'v', 's': 'j', 't': 'Q', 'u': '7', 'v': 'D',
        'w': 'w', 'x': 'n', 'y': 'L', 'z': 'e',
    }

    def __init__(self):
        super().__init__()
        self._dyn_cats = None

    def _headers(self):
        payload = {
            "static_score": "0.8",
            "uuid": "00000000-7fc7-08dc-0000-000000000000",
            "device-id": "20250220125449b9b8cac84c2dd3d035c9052a2572f7dd0122edde3cc42a70",
            "mac": "",
            "sourceuid": "aa7de295aad621a6",
            "refresh-type": "0",
            "model": "22021211RC",
            "wlb-imei": "",
            "client-id": "aa7de295aad621a6",
            "brand": "Redmi",
            "oaid": "",
            "oaid-no-cache": "",
            "sys-ver": "12",
            "trusted-id": "",
            "phone-level": "H",
            "imei": "",
            "wlb-uid": "aa7de295aad621a6",
            "session-id": str(int(time.time() * 1000)),
        }
        b64 = base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode()).decode()
        qm = "".join(self.CHARMAP.get(c, c) for c in b64)
        sign = _md5("AUTHORIZATION=" + "app-version=10001" +
                    "application-id=com.duoduo.read" + "channel=unknown" +
                    "is-white=" + "net-env=5" + "platform=android" +
                    "qm-params=" + qm + "reg=" + self.KEY)
        return {
            "net-env": "5", "reg": "", "channel": "unknown", "is-white": "",
            "platform": "android", "application-id": "com.duoduo.read",
            "authorization": "", "app-version": "10001",
            "User-Agent": "webviewversion/0",
            "qm-params": qm, "sign": sign,
            "Accept": "application/json",
            "X-Requested-With": "com.duoduo.read",
        }

    def _get(self, base, path, sign_str):
        url = base + path + ("&" if "?" in path else "?") + "sign=" + sign_str
        return self.sess.get_json(url, headers=self._headers(), timeout=12)

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        try:
            j = self._get(self.STORE, "/api/v1/playlet/tag/list?operation=1",
                          _md5("operation=1" + self.KEY))
            cats = []
            for c in (j.get("data") or {}).get("list") or []:
                cid = _pick(c, "tag_id", "id")
                cn = _pick(c, "tag_name", "name", "title")
                if cid and cn:
                    cats.append((cid, cn))
            if cats:
                self._dyn_cats = cats[:24]
                return self._dyn_cats
        except Exception:
            pass
        return self.cats

    def _node(self, n):
        vid = _pick(n, "playlet_id", "playletId", "id")
        if not vid:
            return None
        total = _pick_int(n, "total_episode_num", "totalEpisodeNum", "total")
        tags = n.get("tags") or n.get("tag_list") or []
        cat = ",".join(_s(t) for t in tags if _s(t))[:60]
        v = _vod_item(
            self.id, vid, _pick(n, "title", "playlet_name", "name"),
            _pick(n, "image_link", "imageLink", "cover", "cover_url"),
            ("全%d集" % total) if total else "",
            _pick(n, "intro", "description", "desc"))
        if cat:
            v["vod_remarks"] = (v["vod_remarks"] + " " + cat).strip()
        return v

    def cat(self, catid, pg):
        catid = _s(catid) or "0"
        if not catid.isdigit():
            catid = "0"
        if pg > 1:
            sign = _md5("next_id=%doperation=1playlet_privacy=1tag_id=%s%s"
                        % (pg, catid, self.KEY))
            path = ("/api/v1/playlet/index?tag_id=%s&playlet_privacy=1"
                    "&operation=1&next_id=%d" % (catid, pg))
        else:
            sign = _md5("operation=1playlet_privacy=1tag_id=%s%s"
                        % (catid, self.KEY))
            path = ("/api/v1/playlet/index?tag_id=%s&playlet_privacy=1"
                    "&operation=1" % catid)
        j = self._get(self.STORE, path, sign)
        rows = (j.get("data") or {}).get("list") or []
        items = [v for v in (self._node(n) for n in rows) if v]
        more = len(items) > 0 if pg > 1 else False
        return items, more

    def home(self, pg):
        return self.cat("0", pg)

    def detail(self, sid):
        sign = _md5("playlet_id=" + sid + self.KEY)
        j = self._get(self.READ, "/player/api/v1/playlet/info?playlet_id="
                      + _q(sid), sign)
        data = j.get("data") or {}
        v = self._node(data) or _vod_item(self.id, sid, sid)
        v["vod_content"] = _pick(data, "intro", "description", "desc")
        chapters = []
        for i, e in enumerate(data.get("play_list") or []):
            u = _pick(e, "video_url", "videoUrl", "url")
            if not u:
                continue
            no = _pick_int(e, "sort", "episode", "index") or (i + 1)
            t = _pick(e, "title", "name") or ("第%d集" % no)
            chapters.append((u, t))
        chapters.sort(key=lambda x: _ep_no(x[1]))
        v.update({
            "vod_remarks": ("全%d集" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in chapters),
        })
        return v

    def play(self, sid, ep):
        if not _s(ep).startswith("http"):
            raise _SrcErr("猫果分集地址无效")
        return _s(ep), {}

    def search(self, key, pg):
        # 顺序敏感：extend,page,read_preference,track_id,wd
        sign = _md5("extend=page=1read_preference=0track_id=%swd=%s%s"
                    % (self.TRACK_ID, key, self.KEY))
        path = ("/api/v1/playlet/search?extend=&page=1&wd=%s"
                "&read_preference=0&track_id=%s" % (_q(key), self.TRACK_ID))
        j = self._get(self.STORE, path, sign)
        data = j.get("data") or {}
        rows = data.get("list") or []
        items = [v for v in (self._node(n) for n in rows) if v]
        return items, False


# ============================================================
# 黄豆 — 自定义加密传输（HMAC-SHA256 派生 AES-256-CBC 密钥）
# ============================================================
@_register
class _Huangdou(_Src):
    id = "huangdou"
    name = "黄豆"
    cats = [("", "全部")]
    HOSTS = ["https://tideember.cc", "https://xqjurgek.top"]
    PLATFORM_KEY = "7961beb44246e3012ce228d6b5ced05a"
    VERSION = "2.0.0"

    def __init__(self):
        super().__init__()
        self._host = self.HOSTS[0]
        self._device_id = binascii.hexlify(os.urandom(16)).decode()
        self._session_id = binascii.hexlify(os.urandom(16)).decode()

    @staticmethod
    def _uuid_like():
        h = binascii.hexlify(os.urandom(16)).decode()
        return "%s-%s-%s-%s-%s" % (h[:8], h[8:12], h[12:16], h[16:20], h[20:])

    def _key(self, rid):
        msg = binascii.unhexlify(rid.replace("-", ""))
        return hmac.new(self.PLATFORM_KEY.encode(), msg,
                        hashlib.sha256).digest()

    def _call(self, path, data):
        path = "/" + path.lstrip("/")
        rid = self._uuid_like()
        key = self._key(rid)
        iv = os.urandom(16)
        plain = json.dumps({"token": "", "deviceId": self._device_id,
                            "data": data},
                           ensure_ascii=False).encode("utf-8")
        gz = gzip.compress(plain)
        body = iv + _aes_cbc_encrypt(gz, key, iv)
        ts = str(int(time.time()))
        sign_raw = "Dart|%s|%s|%s|%s" % (self._session_id, rid, ts, path)
        sign = hashlib.sha256(sign_raw.encode()).hexdigest() + "-" + ts
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120 Safari/537.36"),
            "Accept": "*/*",
            "Content-Type": "application/octet-stream",
            "version": self.VERSION,
            "deviceType": "web",
            "requestId": rid,
            "sessionId": self._session_id,
            "time": ts,
            "sign": sign,
        }
        last = None
        for host in [self._host] + [h for h in self.HOSTS
                                    if h != self._host]:
            headers["Origin"] = host
            headers["Referer"] = host + "/home"
            try:
                r = self.sess.fetch(host + "/api" + path, method="POST",
                                    headers=headers, data=body, timeout=20)
            except Exception as e:
                last = e
                continue
            if r.status < 200 or r.status >= 300:
                last = _SrcErr("黄豆 HTTP %d" % r.status)
                continue
            self._host = host
            return self._decode(r.body, key)
        raise _SrcErr("黄豆接口不可用：%s" % last)

    def _decode(self, blob, key):
        blob = bytes(blob).strip()
        if blob.startswith((b"{", b"[")):
            try:
                decoded = json.loads(blob.decode("utf-8", "ignore"))
            except Exception:
                raise _SrcErr("黄豆响应 JSON 无效")
        else:
            if len(blob) < 32:
                raise _SrcErr("黄豆响应过短")
            iv, ct = blob[:16], blob[16:]
            try:
                plain = _aes_cbc_decrypt(ct, key, iv)
            except Exception as e:
                raise _SrcErr("黄豆响应解密失败：%s" % e)
            if plain[:2] == b"\x1f\x8b":
                try:
                    plain = gzip.decompress(plain)
                except Exception:
                    raise _SrcErr("黄豆响应解压失败")
            try:
                decoded = json.loads(plain.decode("utf-8", "ignore"))
            except Exception:
                raise _SrcErr("黄豆响应 JSON 无效")
        if isinstance(decoded, dict):
            status = _pick(decoded, "status")
            if status and status != "y":
                code = _pick(decoded, "errorCode", "error_code", "code")
                msg = _pick(decoded, "msg", "message", "error") or status
                if code in ("813004", "813005", "813006", "813103") or \
                        "preview" in code:
                    raise _SrcErr("黄豆：该内容需 VIP/试看限制")
                raise _SrcErr("黄豆接口拒绝：%s" % msg)
        return decoded

    def _rows(self, decoded):
        if isinstance(decoded, list):
            return decoded
        if isinstance(decoded, dict):
            data = decoded.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for k in ("list", "items", "data"):
                    v = data.get(k)
                    if isinstance(v, list):
                        return v
            for k in ("list", "items", "data"):
                v = decoded.get(k)
                if isinstance(v, list):
                    return v
        return []

    def _node(self, n):
        vid = _pick(n, "id", "drama_id")
        if vid.startswith("rp_"):
            vid = vid[3:]
        if not vid:
            return None
        total = _pick_int(n, "episode_count")
        remark = _pick(n, "update_label", "corner")
        if not remark and total:
            remark = "全%d集" % total
        return _vod_item(
            self.id, vid, _pick(n, "name", "title", "t"),
            _pick(n, "img_y", "img_x", "img", "cover", "pic"),
            remark, _pick(n, "description", "summary"))

    def cat(self, catid, pg):
        j = self._call("/drama/list", {"page": str(pg), "page_size": "30"})
        rows = self._rows(j)
        items = [v for v in (self._node(n) for n in rows) if v]
        return items, len(items) >= 30

    def search(self, key, pg):
        j = self._call("/drama/list", {"keywords": key, "page": "1",
                                       "page_size": "50"})
        rows = self._rows(j)
        items = [v for v in (self._node(n) for n in rows) if v]
        return items, False

    def detail(self, sid):
        j = self._call("/drama/detail", {"id": sid})
        data = j.get("data") if isinstance(j, dict) else None
        node = data if isinstance(data, dict) else (j if isinstance(j, dict)
                                                   else {})
        rid = _pick(node, "id", "drama_id")
        if rid.startswith("rp_"):
            rid = rid[3:]
        if rid and rid != sid:
            raise _SrcErr("黄豆详情与请求剧集不符")
        v = self._node(node) or _vod_item(self.id, sid, sid)
        v["vod_content"] = _pick(node, "description", "summary")
        chapters = []
        for i, e in enumerate(node.get("episodes") or []):
            no = _pick_int(e, "seq", "episode", "ep") or (i + 1)
            t = _pick(e, "name", "title") or ("第%d集" % no)
            chapters.append((str(no), t))
        if not chapters:
            total = _pick_int(node, "episode_count", "free_episodes")
            chapters = [(str(i + 1), "第%d集" % (i + 1))
                        for i in range(min(total, 3000))]
        v.update({
            "vod_remarks": ("全%d集" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in chapters),
        })
        return v

    def _is_preview(self, data, media):
        for k in ("is_preview", "isPreview"):
            if str(data.get(k)).lower() in ("true", "1", "y"):
                return True
        for k in ("preview_m3u8", "preview_url"):
            pv = _pick(data, k)
            if pv and (not media or pv.strip() == media.strip()):
                return True
        if media:
            p = urllib.parse.urlparse(media).path.lower()
            if p.endswith("/preview.mp4") or p.endswith("/preview.m3u8") \
                    or p == "preview.mp4" or p == "preview.m3u8":
                return True
        return False

    def play(self, sid, ep):
        j = self._call("/drama/play", {"id": sid, "seq": str(ep)})
        data = j.get("data") if isinstance(j, dict) else {}
        if not isinstance(data, dict):
            data = {}
        media = _pick(data, "m3u8", "url", "play_url", "playUrl")
        if self._is_preview(data, media):
            raise _SrcErr("黄豆：该分集为 VIP 试看，不提供试看地址")
        if media:
            if not media.startswith("http"):
                media = self._host + "/" + media.lstrip("/")
            return media, {"Referer": self._host + "/home",
                           "User-Agent": PC_UA}
        # 降级直链
        url = ("%s/api/drama/hls/%s/%s/play.m3u8?line=free"
               % (self._host, _q(sid), _q(str(ep))))
        try:
            r = self.sess.fetch(url,
                                headers={"Referer": self._host + "/home"},
                                timeout=12)
            if r.body.startswith(b"#EXTM3U"):
                return url, {"Referer": self._host + "/home"}
        except Exception:
            pass
        raise _SrcErr("黄豆未返回该集播放地址")


# ============================================================
# 野果 — 配置动态发现（__NUXT_DATA__ + _nuxt/*.js），AES-CBC + 响应签名
# 配置/解码失败只重新发现并重试一次。
# ============================================================
@_register
class _Yeguo(_Src):
    id = "yeguo"
    name = "野果"
    cats = [("", "全部")]
    SITES = ["https://analyze.buxefaex.cc", "https://ygdj7.com/"]
    _PUB_FIELD = re.compile(
        r"""\b(version|mode|padding|key|iv|sign_key)\s*:\s*(?:[a-zA-Z_$][a-zA-Z0-9_$]*\(\s*)?["'`]([^"'`\\\r\n]{1,512})["'`]""")
    _IMPORT = re.compile(
        r"""(?s)import\s*\{([^{};]+)\}\s*from\s*["'`]([^"'`]+)["'`]""")

    def __init__(self):
        super().__init__()
        self._access = None
        self._lock = threading.Lock()
        self._dyn_cats = None

    # -- 发现 --
    @staticmethod
    def _pub_bytes(value):
        if "_" not in value:
            return value.encode("utf-8")
        out = bytearray()
        for part in value.split("_"):
            try:
                n = int(part)
            except Exception:
                return None
            if n < 0 or n > 255:
                return None
            out.append(n)
        return bytes(out)

    def _parse_pub_config(self, script):
        fields = {}
        for m in self._PUB_FIELD.finditer(script[:2000000]):
            fields[m.group(1)] = m.group(2)
            if len(fields) > 32:
                break
        if fields.get("version") != "v0" or fields.get("mode") != "CBC" \
                or fields.get("padding") != "Pkcs7":
            return None
        key = self._pub_bytes(fields.get("key", ""))
        iv = self._pub_bytes(fields.get("iv", ""))
        sk = self._pub_bytes(fields.get("sign_key", ""))
        if key is None or iv is None or sk is None:
            return None
        if len(key) not in (16, 24, 32) or len(iv) != 16 \
                or not (1 <= len(sk) <= 128):
            return None
        return key, iv, sk

    def _api_base(self, html):
        m = re.search(
            r'''(?is)<script[^>]*id=["']__NUXT_DATA__["'][^>]*>(.*?)</script>''',
            html)
        if not m:
            return ""
        try:
            table = json.loads(m.group(1))
        except Exception:
            return ""
        if not isinstance(table, list) or len(table) > 100000:
            return ""
        for item in table:
            if isinstance(item, dict) and "apiBaseURL" in item:
                ref = item["apiBaseURL"]
                if isinstance(ref, int) and 0 <= ref < len(table):
                    base = table[ref]
                    if isinstance(base, str) and base:
                        return base.rstrip("/")
        return ""

    def _script_url(self, page_url, ref):
        try:
            page = urllib.parse.urlparse(page_url)
            u = urllib.parse.urljoin(page_url, ref)
            p = urllib.parse.urlparse(u)
        except Exception:
            return ""
        if p.netloc != page.netloc:
            return ""
        if not p.path.startswith("/_nuxt/") or \
                not p.path.endswith(".js"):
            return ""
        return u.split("#")[0]

    def _discover_at(self, site):
        r = self.sess.fetch(site + "/", headers={"Referer": site + "/"},
                            timeout=15)
        html = r.text()
        page_url = r.url or (site + "/")
        api_base = self._api_base(html)
        if not api_base:
            raise _SrcErr("野果页面未提供有效的接口入口")
        entry = ""
        for m in re.finditer(
                r'''(?is)<script[^>]*type=["']module["'][^>]*src=["']([^"']+)["']''',
                html):
            entry = self._script_url(page_url, m.group(1))
            if entry:
                break
        if not entry:
            raise _SrcErr("野果页面未提供接口配置脚本")
        entry_body = self.sess.fetch(entry, headers={"Referer": page_url},
                                     timeout=15).text()
        imports = self._IMPORT.findall(entry_body)
        # 无逗号的 import 优先
        imports.sort(key=lambda x: ("," in x[0]))
        seen = set()
        for _names, ref in imports:
            if len(ref) > 2400:
                continue
            url = self._script_url(entry, ref)
            if not url or url in seen or len(seen) >= 20:
                continue
            seen.add(url)
            try:
                body = self.sess.fetch(url, headers={"Referer": page_url},
                                       timeout=15).text()
            except Exception:
                continue
            cfg = self._parse_pub_config(body)
            if cfg:
                key, iv, sk = cfg
                ident = binascii.hexlify(os.urandom(16)).decode()
                return {"base": api_base, "site": site, "key": key,
                        "iv": iv, "sign_key": sk, "ident": ident}
        raise _SrcErr("野果接口配置已变化，暂时无法解码")

    def _discover(self):
        with self._lock:
            if self._access:
                return self._access
            last = None
            for site in self.SITES:
                try:
                    acc = self._discover_at(site)
                    self._access = acc
                    return acc
                except Exception as e:
                    last = e
            raise _SrcErr("野果线路暂不可用：%s" % last)

    def _drop_access(self):
        with self._lock:
            self._access = None

    # -- 签名/解码 --
    @staticmethod
    def _sign(envelope, sign_key):
        pieces = []
        for name in sorted(envelope.keys()):
            if name in ("sign", "_ver"):
                continue
            v = envelope[name]
            if v is None:
                continue
            if isinstance(v, bool):
                f = "true" if v else "false"
            elif isinstance(v, (int, float)):
                f = str(v)
            elif isinstance(v, str):
                f = v
            else:
                raise _SrcErr("野果响应签名格式无效")
            if name == "data":
                f = f.replace(" ", "+")
            pieces.append(name + "=" + f)
        d1 = hashlib.sha256(
            ("&".join(pieces)).encode("utf-8") + sign_key).hexdigest()
        return hashlib.md5(d1.encode("utf-8")).hexdigest()

    def _decode(self, body, acc):
        try:
            env = json.loads(body.decode("utf-8", "ignore"))
        except Exception:
            raise _SrcErr("野果响应 JSON 无效")
        if not isinstance(env, dict):
            raise _SrcErr("野果响应格式无效")
        sig = _s(env.get("sign"))
        if sig:
            try:
                exp = self._sign(env, acc["sign_key"])
            except _SrcErr:
                raise
            except Exception:
                raise _SrcErr("野果响应验签失败")
            if exp != sig.lower():
                raise _SrcErr("野果响应验签失败")
        data = env.get("data")
        if isinstance(data, str):
            b64 = data.replace(" ", "+").strip()
            try:
                ct = base64.b64decode(b64)
            except Exception:
                raise _SrcErr("野果数据 Base64 无效")
            if not ct or len(ct) % 16:
                raise _SrcErr("野果数据长度无效")
            try:
                plain = _aes_cbc_decrypt(ct, acc["key"], acc["iv"])
            except Exception:
                raise _SrcErr("野果数据解密失败")
            try:
                payload = json.loads(plain.decode("utf-8", "ignore"))
            except Exception:
                raise _SrcErr("野果数据 JSON 无效")
        else:
            payload = env
        if not isinstance(payload, dict):
            raise _SrcErr("野果返回的数据格式无效")
        if _s(payload.get("status")) == "-1":
            raise _SrcErr("野果当前内容需要站源授权")
        if _s(payload.get("status")) != "1":
            raise _SrcErr("野果请求未完成：%s"
                          % (_s(payload.get("msg"))[:90] or "请稍后重试"))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise _SrcErr("野果返回的数据格式无效")
        return data

    def _call(self, route, params):
        last = None
        for attempt in range(2):
            acc = self._discover()
            values = {"bundleId": "com.pwa.mater", "version": "1.3.2",
                      "oauth_type": "web", "language": "zh", "via": "pwa",
                      "oauth_id": acc["ident"], "trace_id": acc["ident"],
                      "token": ""}
            values.update(params or {})
            method = "GET" if route == "/api/home/contentOptions" else "POST"
            url = acc["base"] + route
            headers = {"User-Agent": PC_UA,
                       "Accept": "application/json, text/plain, */*",
                       "Origin": acc["site"], "Referer": acc["site"] + "/"}
            try:
                if method == "GET":
                    url += "?" + urllib.parse.urlencode(values)
                    r = self.sess.fetch(url, headers=headers, timeout=20)
                else:
                    headers["Content-Type"] = \
                        "application/x-www-form-urlencoded"
                    r = self.sess.fetch(
                        url, method="POST", headers=headers,
                        data=urllib.parse.urlencode(values).encode(),
                        timeout=20)
                if r.status < 200 or r.status >= 300:
                    raise _SrcErr("野果 HTTP %d" % r.status)
                return self._decode(r.body, acc)
            except _SrcErr as e:
                last = e
                msg = str(e)
                if "验签失败" in msg or "解密失败" in msg:
                    self._drop_access()
                    continue
                raise
            except Exception as e:
                last = e
                raise _SrcErr("野果请求失败：%s" % e)
        raise _SrcErr("野果解码失败：%s" % last)

    # -- 业务 --
    def _node(self, n, site):
        vid = _pick(n, "video_id", "id")
        if not vid or not vid.isdigit():
            return None
        title = _pick(n, "title")
        if not title:
            return None
        total = _pick_int(n, "episode_count", "total_episode", "total")
        return _vod_item(
            self.id, vid, title,
            _abs(site + "/", _pick(n, "cover", "cover_url", "image")),
            ("全%d集" % total) if total else "",
            _pick(n, "desc", "description", "intro"))

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        try:
            data = self._call("/api/home/contentOptions", None)
            vf = data.get("video_filter")
            if isinstance(vf, dict):
                cats, seen = [], set()
                for field, f in vf.items():
                    if not isinstance(f, dict):
                        continue
                    for o in f.get("list") or []:
                        if not isinstance(o, dict):
                            continue
                        val, nm = _pick(o, "value"), _pick(o, "name")
                        if not val or val == "0" or not nm or \
                                len(nm) > 48:
                            continue
                        cid = "%s:%s" % (field, val)
                        if cid in seen:
                            continue
                        seen.add(cid)
                        cats.append((cid, nm))
                if cats:
                    self._dyn_cats = cats[:30]
                    return self._dyn_cats
        except Exception:
            pass
        return self.cats

    def cat(self, catid, pg):
        params = {"page": str(pg), "limit": "20"}
        if catid and ":" in catid:
            f, v = catid.split(":", 1)
            params[f] = v
        data = self._call("/api/theater/exploreList", params)
        rows = data.get("list") or []
        site = (self._access or {}).get("site", self.SITES[0])
        items = [v for v in (self._node(n, site) for n in rows
                             if isinstance(n, dict)) if v]
        total = _pick_int(data, "total", "total_count", "totalCount")
        limit = _pick_int(data, "limit", "page_size", "pageSize",
                          "per_page", "perPage") or 20
        more = (pg < (total + limit - 1) // limit) if total \
            else len(items) >= limit
        hm = data.get("has_more")
        if hm is not None:
            more = str(hm).lower() in ("1", "true", "y")
        return items, more

    def home(self, pg):
        return self.cat("", pg)

    def search(self, key, pg):
        data = self._call("/api/search/result",
                          {"keyword": key, "tab": "video",
                           "page": str(pg), "limit": "20"})
        rows = data.get("list") or []
        site = (self._access or {}).get("site", self.SITES[0])
        items = [v for v in (self._node(n, site) for n in rows
                             if isinstance(n, dict)) if v]
        return items, False

    def detail(self, sid):
        if not sid.isdigit():
            raise _SrcErr("野果剧集 ID 无效")
        row = self._call("/api/playlet/detail",
                         {"video_id": sid, "id": sid, "episode_id": "0",
                          "related_limit": "0"})
        site = (self._access or {}).get("site", self.SITES[0])
        if _pick(row, "video_id", "id") != sid:
            raise _SrcErr("野果详情与请求剧集不符")
        v = self._node(row, site) or _vod_item(self.id, sid, sid)
        v["vod_content"] = _pick(row, "desc", "description", "intro")
        chapters = []
        seen_ids, seen_no = set(), set()
        for e in row.get("episodes") or []:
            if not isinstance(e, dict):
                continue
            if str(e.get("is_adv")).lower() in ("1", "true", "y"):
                continue
            eid = _pick(e, "id")
            try:
                no = int(_s(e.get("sort")))
            except Exception:
                no = 0
            if not eid or not eid.isdigit() or no < 1 or \
                    eid in seen_ids or no in seen_no:
                continue
            seen_ids.add(eid)
            seen_no.add(no)
            t = _pick(e, "title") or ("第%d集" % no)
            chapters.append((eid, t, no))
        chapters.sort(key=lambda x: x[2])
        v.update({
            "vod_remarks": ("全%d集" % len(chapters)) if chapters else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k))
                for k, t, _n in chapters),
        })
        return v

    def play(self, sid, ep):
        if not _s(ep).isdigit():
            raise _SrcErr("野果分集 ID 无效")
        row = self._call("/api/playlet/play",
                         {"playlet_id": sid, "video_id": sid,
                          "episode_id": _s(ep)})
        if _pick(row, "playlet_id") != sid or _pick(row, "id") != _s(ep):
            raise _SrcErr("野果返回的播放地址与请求分集不符")
        if str(row.get("is_adv")).lower() in ("1", "true", "y"):
            raise _SrcErr("野果未返回该集正片")
        media = _pick(row, "video_url", "video_url_h265")
        if not media:
            raise _SrcErr("野果未返回播放地址")
        site = (self._access or {}).get("site", self.SITES[0])
        return _abs(site + "/", media), {"Referer": site + "/"}


# ============================================================
# 黄果旧版 — AES 加密 JSON API + 访客 token 会话
# ============================================================
@_register
class _Hgcf(_Src):
    id = "hgcf"
    name = "黄果旧版"
    cats = [("", "推荐")]
    API_DEFAULT = "https://dr6skssi3nxbk.cloudfront.net"
    FRONTEND = "https://d2pypzndaqisk.cloudfront.net"
    CDN_DEFAULT = "https://sjljsla.lkkwip.cn"
    X_UA = ("BuildID=com.abc.Butterfly;SysType=ios;DevID=00000000000000000000000000000;"
            "Ver=1.0.0;DevType=iPhone;DeviceBrand=APPLE;DeviceModel=iPhone;"
            "SystemName=iOS;SystemVersion=18.7;Terminal=1;IsH5=1;"
            "Sid=00000000000000000000000000000000")

    def __init__(self):
        super().__init__()
        self._api = ""
        self._proto = None       # (interfaceKey, paramKey, paramIV)
        self._proto_at = 0
        self._device_id = ""
        self._token = ""
        self._lock = threading.Lock()
        self._dyn_cats = None

    # -- 会话 --
    def _frontend_script(self):
        html = self.sess.get_text(self.FRONTEND + "/",
                                  headers={"User-Agent": IPHONE_UA},
                                  timeout=15)
        m = re.search(r'''(?is)<script[^>]+src=["']([^"']*main-[^"']*\.js)["']''',
                      html)
        if not m:
            raise _SrcErr("黄果旧版前端脚本未找到")
        js_url = _abs(self.FRONTEND + "/", m.group(1))
        return self.sess.get_text(js_url, headers={"User-Agent": IPHONE_UA},
                                  timeout=15)

    def _discover_api(self):
        try:
            js = self._frontend_script()
        except Exception:
            return self.API_DEFAULT
        for host in re.findall(r"https://[a-z0-9]+\.cloudfront\.net", js):
            try:
                j = self.sess.get_json(host + "/api/app/ping/check",
                                       headers={"User-Agent": IPHONE_UA},
                                       timeout=8)
                if j.get("code") == 200:
                    return host
            except Exception:
                continue
        return self.API_DEFAULT

    def _protocol(self):
        with self._lock:
            if self._proto and time.time() - self._proto_at < 24 * 3600:
                return self._proto
            js = self._frontend_script()
            def val(name):
                m = re.search(r"""["']%s["']\s*[:,]\s*["']([^"'\\\r\n]+)["']"""
                              % name, js)
                return m.group(1) if m else ""
            ik, pk, piv = val("interfaceKey"), val("parameterKey"), \
                val("parameterIv")
            if not (0 < len(ik) <= 512 and len(pk) == 16 and len(piv) == 16):
                raise _SrcErr("黄果旧版接口协议已变化")
            self._proto = (ik, pk, piv)
            self._proto_at = time.time()
            return self._proto

    def _login(self):
        ik, pk, piv = self._protocol()
        payload = self._raw_request(
            "POST", "/api/app/mine/login/h5",
            {"devID": self._device_id, "sysType": "ios",
             "isAppStore": False},
            ik, pk, piv, "")
        token = _pick(payload, "token")
        if not token:
            raise _SrcErr("黄果旧版访客登录未返回令牌")
        with self._lock:
            self._token = token

    def _x_user_agent(self):
        did = self._device_id or "00000000000000000000000000000"
        return self.X_UA.replace("DevID=00000000000000000000000000000",
                                 "DevID=" + did, 1)

    def _decrypt_response(self, data_str, interface_key):
        o = base64.b64decode(data_str.strip())
        if len(o) < 12:
            raise _SrcErr("黄果旧版加密响应过短")
        i = o[:12]
        r = interface_key.encode() + i
        l = len(r) >> 1
        s = _sha256(r)[8:24]
        c = s + r[:l]
        a = r[l:] + s
        d = _sha256(c)
        f = _sha256(a)
        m = d[:8] + f[8:24] + d[24:]
        p = f[:4] + d[12:20] + f[28:]
        g = o[12:]
        if len(g) % 16:
            raise _SrcErr("黄果旧版密文未对齐")
        return _pkcs7_unpad(_aes_crypt_fast(g, m, p, False, True), )

    def _raw_request(self, method, path, params, ik, pk, piv, token):
        enc = None
        if params is not None:
            plain = json.dumps(params, ensure_ascii=False).encode("utf-8")
            enc = base64.b64encode(
                _aes_cbc_encrypt(plain, pk.encode(), piv.encode())).decode()
        url = self._api + path
        headers = {
            "Accept": "application/json",
            "temp": "test",
            "X-User-Agent": self._x_user_agent(),
            "Origin": self.FRONTEND,
            "Referer": self.FRONTEND + "/",
            "User-Agent": IPHONE_UA,
        }
        if token:
            headers["Authorization"] = token
        if method == "GET":
            if enc:
                sep = "&" if "?" in url else "?"
                url += sep + "data=" + _q(enc)
            r = self.sess.fetch(url, headers=headers, timeout=15)
        else:
            headers["Content-Type"] = "application/json"
            body = json.dumps({"data": enc},
                              ensure_ascii=False).encode("utf-8")
            r = self.sess.fetch(url, method="POST", headers=headers,
                                data=body, timeout=15)
        if r.status < 200 or r.status >= 300:
            raise _SrcErr("黄果旧版 HTTP %d" % r.status)
        try:
            env = json.loads(r.text())
        except Exception:
            raise _SrcErr("黄果旧版响应 JSON 无效")
        code = _s(env.get("code")).strip('"')
        if code not in ("", "null", "200", "0"):
            msg = _s(env.get("msg"))[:120] or "接口错误"
            err = _SrcErr("黄果旧版 API %s: %s" % (code, msg))
            err.code = code
            raise err
        data = env.get("data")
        h = env.get("hash")
        hash_on = bool(h) if isinstance(h, bool) else _s(h).lower() not in (
            "", "0", "false", "null")
        if hash_on and data:
            if not isinstance(data, str):
                raise _SrcErr("黄果旧版加密数据格式无效")
            try:
                plain = self._decrypt_response(data, ik)
            except _SrcErr:
                raise
            except Exception as e:
                raise _SrcErr("黄果旧版响应解密失败：%s" % e)
            return json.loads(plain.decode("utf-8", "ignore"))
        return data

    def _api_call(self, method, path, params=None, retry=True):
        # 确保会话
        with self._lock:
            if not self._api:
                self._api = self._discover_api()
            if not self._device_id:
                self._device_id = ("%08X%d" % (
                    random.getrandbits(32), int(time.time() * 1000)))
            api, token = self._api, self._token
        ik, pk, piv = self._protocol()
        if not token:
            self._login()
            with self._lock:
                token = self._token
        try:
            return self._raw_request(method, path, params, ik, pk, piv,
                                     token)
        except _SrcErr as e:
            if retry and getattr(e, "code", "") == "5005":
                with self._lock:
                    self._token = ""
                self._login()
                with self._lock:
                    token = self._token
                return self._raw_request(method, path, params, ik, pk, piv,
                                         token)
            raise

    # -- 业务 --
    def _fix_cover(self, pic):
        pic = _s(pic)
        if not pic or pic.startswith("http"):
            return pic
        if pic.startswith("upload/") or pic.startswith("upload_01/"):
            return "https://pic.zdmhyg.cn/" + pic
        return "https://zzzznnn.lkkwip.cn/" + pic.lstrip("/")

    def categories(self):
        if self._dyn_cats is not None:
            return self._dyn_cats
        try:
            tabs = self._api_call("GET", "/api/app/playlet-tab/all", None)
            rows = tabs.get("list") if isinstance(tabs, dict) else tabs
            cats = []
            for t in rows if isinstance(rows, list) else []:
                cid = _pick(t, "id")
                cn = _pick(t, "name")
                if cid and cn:
                    cats.append((cid, cn))
            if cats:
                self._dyn_cats = cats[:24]
                return self._dyn_cats
        except Exception:
            pass
        return self.cats

    def _node(self, n):
        vid = _pick(n, "id", "playlet_id", "videoId")
        if not vid:
            return None
        total = _pick_int(n, "totalEpisode", "total_episode", "episodeCount",
                          "episode_count", "chapterCount", "chapter_count",
                          "total", "episodes")
        return _vod_item(
            self.id, vid, _pick(n, "title", "name"),
            self._fix_cover(_pick(n, "cover", "coverUrl", "cover_url",
                                 "image", "imageUrl", "image_url", "img",
                                 "pic", "picture", "poster", "thumb",
                                 "thumbnail")),
            ("全%d集" % total) if total else "",
            _pick(n, "desc", "description", "intro", "summary"))

    def cat(self, catid, pg):
        cats = self.categories()
        tab = catid or (cats[0][0] if cats else "")
        if not tab:
            raise _SrcErr("黄果旧版无可用分类")
        data = self._api_call(
            "GET", "/api/app/playlet/home/tab/" + _q(tab),
            {"pageNumber": str(pg), "pageSize": "20", "tabSortType": "1"})
        rows = (data.get("list") if isinstance(data, dict) else data) or []
        items = [v for v in (self._node(n) for n in rows
                             if isinstance(n, dict)) if v]
        return items, len(items) >= 20

    def home(self, pg):
        return self.cat("", pg)

    def detail(self, sid):
        try:
            data = self._api_call("GET",
                                  "/api/app/playlet/detail/" + _q(sid), None)
        except Exception as e:
            raise _SrcErr("黄果旧版详情失败：%s" % e)
        if not isinstance(data, dict):
            raise _SrcErr("黄果旧版详情格式无效")
        v = self._node(data) or _vod_item(self.id, sid, sid)
        v["vod_content"] = _pick(data, "desc", "description", "intro")
        chapters = data.get("chapters")
        if not chapters:
            try:
                chapters = self._api_call(
                    "GET", "/api/app/playlet-chapter/list/" + _q(sid), None)
            except Exception:
                chapters = []
        if isinstance(chapters, dict):
            chapters = chapters.get("list") or []
        eps = []
        for i, c in enumerate(chapters or []):
            if not isinstance(c, dict):
                continue
            vu = _pick(c, "videoUrl", "video_url", "playUrl", "url")
            if not vu:
                continue
            t = _pick(c, "title", "name") or ("第%d集" % (i + 1))
            eps.append((vu, t))
        v.update({
            "vod_remarks": ("全%d集" % len(eps)) if eps else "",
            "vod_play_from": self.name,
            "vod_play_url": "#".join(
                "%s$%s" % (t, _pid(self.id, sid, k)) for k, t in eps),
        })
        return v

    def play(self, sid, ep):
        ep = _s(ep)
        with self._lock:
            api, token = self._api, self._token
        if ep.startswith("http"):
            media = ep
        else:
            media = ("%s/api/app/vid/h5/m3u8/%s?%s"
                     % (api, _q(ep.strip("/")),
                        urllib.parse.urlencode(
                            {"token": token, "c": self.CDN_DEFAULT})))
        return media, {"Referer": self.FRONTEND + "/",
                       "User-Agent": IPHONE_UA}

    def search(self, key, pg):
        # 无服务端搜索：拉首页按标题过滤
        items = []
        try:
            rows, _ = self.cat("", 1)
        except Exception:
            rows = []
        for v in rows:
            if key in v["vod_name"]:
                items.append(v)
        return items[:30], False

# Spider 主类（FongMi 5.6.4 / Chaquopy 合约：全部返回 dict）
# ============================================================
from concurrent.futures import ThreadPoolExecutor

_MAIN_SPIDER = None


class Spider(BaseSpider):

    def getName(self):
        return "真果鉴·全站源"

    def init(self, extend=""):
        self.extend = _s(extend)
        global _MAIN_SPIDER
        _MAIN_SPIDER = self
        return {}

    def destroy(self):
        return {}

    # ---------- 本地代理（红果 CENC 解密通道） ----------
    def localProxy(self, param):
        try:
            src = _find_src("hongguo")
            if src is not None and _hgmod is not None:
                hg = src._get_hg()
                if hasattr(hg, "localProxy"):
                    return hg.localProxy(param or {})
        except Exception as e:
            return [500, "text/plain; charset=utf-8",
                    ("proxy error: %s" % e).encode("utf-8")]
        return [404, "text/plain; charset=utf-8", b"no proxy"]

    def proxy(self, param):
        return self.localProxy(param)

    def isVideoFormat(self, url):
        u = _s(url).lower()
        return (".m3u8" in u or ".mp4" in u or ".flv" in u or ".ts" in u
                or ".mkv" in u)

    def manualVideoCheck(self):
        return False

    # ---------- 首页 ----------
    def _source_cats(self, src):
        try:
            if hasattr(src, "categories"):
                cats = src.categories()
                if cats:
                    return cats[:24]
        except Exception:
            pass
        return src.cats or [("", "推荐")]

    def homeContent(self, filter=False):
        # 两级分类（照 ___3_shu0.py 的写法）：
        #   大分类=站源名（顶部 tab）；子分类=各源自己的分类，走 filters 二级筛选栏。
        #   filters 必须是 list 格式：{tid: [{"key","name","value":[{"n","v"}]}]}，
        #   dict 格式 FongMi 不认。
        cats_map = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(self._source_cats, src): src
                    for src in _SOURCES}
            for fut in futs:
                try:
                    cats_map[futs[fut].id] = fut.result(timeout=20)
                except Exception:
                    cats_map[futs[fut].id] = futs[fut].cats or [("", "推荐")]
        classes, filters = [], {}
        for src in _SOURCES:
            tid = _tid(src.id, "")
            classes.append({"type_id": tid, "type_name": src.name})
            subs = cats_map.get(src.id) or src.cats or [("", "推荐")]
            opts, seen_n = [], set()
            for cid, cname in subs[:30]:
                if not cname or cname in seen_n:
                    continue
                seen_n.add(cname)
                opts.append({"n": cname, "v": cid})
            groups = []
            if opts:
                groups.append({"key": "cat", "name": "分类", "value": opts})
            # 部分源（如红果）自带更多筛选组，追加
            if hasattr(src, "extra_filters"):
                try:
                    for g in src.extra_filters() or []:
                        if isinstance(g, dict) and g.get("value"):
                            groups.append(g)
                except Exception:
                    pass
            if groups:
                filters[tid] = groups
        vods = []
        try:
            items, _ = _SOURCES[0].home(1)
            vods = items[:24]
        except Exception:
            pass
        return {"class": classes, "list": vods, "filters": filters}

    def homeVideoContent(self):
        try:
            items, _ = _SOURCES[0].home(1)
            return {"list": items[:24]}
        except Exception:
            return {"list": []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        src_id, _ = _split_tid(tid)
        src = _find_src(src_id)
        if not src:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20,
                    "total": 0}
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1
        # 子分类来自 filters 二级筛选：extend = {"cat": <cid>}（照 ___3_shu0.py）
        cat = ""
        ext = extend
        if isinstance(ext, str) and ext:
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {}
        if isinstance(ext, dict):
            cat = _s(ext.get("cat", ""))
        if cat:
            # 兼容 FongMi 传显示名而不是 id 的情况
            try:
                cats = self._source_cats(src)
                if cat not in set(c[0] for c in cats):
                    by_name = dict((c[1], c[0]) for c in cats)
                    cat = by_name.get(cat, "")
            except Exception:
                pass
        if not cat:
            try:
                cats = self._source_cats(src)
                cat = cats[0][0] if cats else ""
            except Exception:
                cat = ""
        # 部分源（如红果）需要完整 extend 透传二级筛选
        ext_dict = ext if isinstance(ext, dict) else {}
        try:
            if hasattr(src, "cat_ex"):
                items, more = src.cat_ex(cat, pg, ext_dict)
            else:
                items, more = src.cat(cat, pg)
        except _SrcErr:
            items, more = [], False
        except Exception:
            items, more = [], False
        return {"list": items or [], "page": pg,
                "pagecount": 9999 if more else pg,
                "limit": 20, "total": 999999 if more else len(items or [])}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        did = ids[0] if ids else ""
        src_id, sid = _split_did(did)
        src = _find_src(src_id)
        if not src:
            return {"list": []}
        try:
            vod = src.detail(sid)
        except _SrcErr as e:
            vod = _vod_detail(src, sid, "加载失败", "",
                              "", "原因：%s" % e, chapters=())
            vod["vod_id"] = did
        except Exception as e:
            vod = _vod_detail(src, sid, "加载失败", "",
                              "", "原因：%s" % type(e).__name__,
                              chapters=())
            vod["vod_id"] = did
        return {"list": [vod]}

    # ---------- 搜索（多源并行） ----------
    def _search_one(self, src, key):
        try:
            items, _ = src.search(key, 1)
            return items or []
        except Exception:
            return []

    def searchContent(self, key, quick=False, pg="1"):
        key = _s(key).strip()
        if not key:
            return {"list": []}
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg > 1:
            return {"list": []}
        out = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(self._search_one, src, key): src
                    for src in _SOURCES}
            for fut in futs:
                try:
                    items = fut.result(timeout=30)
                except Exception:
                    continue
                src = futs[fut]
                for v in (items or [])[:12]:
                    # 搜索结果名前缀站源，便于区分
                    if not v["vod_name"].startswith(src.name):
                        v["vod_name"] = "[%s] %s" % (src.name,
                                                     v["vod_name"])
                    out.append(v)
                if len(out) >= 160:
                    break
        return {"list": out}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None):
        src_id, sid, ep = _split_pid(id)
        src = _find_src(src_id)
        if not src:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        try:
            url, header = src.play(sid, ep)
        except _SrcErr:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        except Exception:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        return {"parse": 0, "playUrl": "", "url": _s(url),
                "header": dict(header or {})}

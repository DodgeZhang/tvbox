#!/usr/bin/env python3
# QQ群:807916734 @ID圥忈
# -*- coding: utf-8 -*-
# ============================================================
# TVBox Python 爬虫 · 4K影视 v6.2.0 (qijiappapi 协议) 【搜索优化版】
# 兼容: TVBox / 影视仓 / FongMi / WebHomeTV(默影视) / PeekPro
# 零第三方依赖: RSA/AES 均为内嵌纯 Python 实现（标准库 only）
# ============================================================
# 【搜索优化核心】
# 服务端 searchList 接口存在严重缺陷：完全无视搜索关键词，始终返回固定20条热门推荐。
# 本版本采用智能多模式搜索策略替代：
#   1. 类型匹配 → typeFilterVodList + class 精确过滤（效果最好）
#   2. 年份匹配 → typeFilterVodList + year 过滤
#   3. 地区匹配 → typeFilterVodList + area 过滤
#   4. 语言匹配 → typeFilterVodList + lang 过滤
#   5. 片名/演员 → searchList 返回数据 + 本地多字段模糊过滤
#   6. 兜底策略 → 拉取热门分类前2页建立本地索引，再做本地过滤
# ============================================================
import sys
try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

import json
import base64
import random
import time
import re
import urllib.request
import urllib.parse
import ssl
from collections import OrderedDict

# ---------------- 配置 ----------------
HOST = "http://43.248.2.106:9001"
SITE = "http://43.248.2.106:9001"
NSKEY = b"FTgP4Gq8zPiqbt7M"
DEVICE_ID = "a1b2c3d4e5f67890"
APP_VER = "6.0.4"
UA = "okhttp/3.12.1"
PAGE_SIZE = 30
SEARCH_SIZE = 20
SESSION_TTL = 20 * 3600

# 搜索优化配置
SEARCH_FALLBACK_PAGES = 3      # 兜底策略拉取页数
SEARCH_MAX_LOCAL_INDEX = 180   # 本地索引最大条目

try:
    _SSL_CTX = ssl.create_default_context()
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE
except Exception:
    _SSL_CTX = None


def _http(url, data=None, headers=None, timeout=15, retries=1):
    hdrs = {"User-Agent": UA, "app-platform": "android"}
    if headers:
        hdrs.update(headers)
    last_err = None
    for attempt in range(retries + 1):
        try:
            if data is not None:
                body = urllib.parse.urlencode(data).encode("utf-8")
                req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
            else:
                req = urllib.request.Request(url, headers=hdrs)
            kwargs = {"timeout": timeout}
            if _SSL_CTX is not None and url.startswith("https"):
                kwargs["context"] = _SSL_CTX
            with urllib.request.urlopen(req, **kwargs) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last_err


# ============================================================
# 纯 Python 密码学（AES-128-CBC / RSA-PKCS1v1.5）
# ============================================================

def _gmul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


_SBOX = [0] * 256
_INV_SBOX = [0] * 256
_TE = [[0] * 256 for _ in range(4)]
_TD = [[0] * 256 for _ in range(4)]
_IMC = [[0] * 256 for _ in range(4)]
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _build_crypto_tables():
    exp = [0] * 255
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x ^= _gmul(x, 2)

    def ginv(a):
        return 0 if a == 0 else exp[(255 - log[a]) % 255]

    for i in range(256):
        b = ginv(i)
        s = b ^ (((b << 1) | (b >> 7)) & 0xFF) ^ (((b << 2) | (b >> 6)) & 0xFF) \
            ^ (((b << 3) | (b >> 5)) & 0xFF) ^ (((b << 4) | (b >> 4)) & 0xFF) ^ 0x63
        _SBOX[i] = s
        _INV_SBOX[s] = i

    IM = [[14, 11, 13, 9], [9, 14, 11, 13], [13, 9, 14, 11], [11, 13, 9, 14]]
    for x in range(256):
        s = _SBOX[x]
        s2, s3 = _gmul(s, 2), _gmul(s, 3)
        _TE[0][x] = s2 | (s << 8) | (s << 16) | (s3 << 24)
        _TE[1][x] = s3 | (s2 << 8) | (s << 16) | (s << 24)
        _TE[2][x] = s | (s3 << 8) | (s2 << 16) | (s << 24)
        _TE[3][x] = s | (s << 8) | (s3 << 16) | (s2 << 24)

        d = _INV_SBOX[x]
        d9, d11 = _gmul(d, 9), _gmul(d, 11)
        d13, d14 = _gmul(d, 13), _gmul(d, 14)
        _TD[0][x] = d14 | (d9 << 8) | (d13 << 16) | (d11 << 24)
        _TD[1][x] = d11 | (d14 << 8) | (d9 << 16) | (d13 << 24)
        _TD[2][x] = d13 | (d11 << 8) | (d14 << 16) | (d9 << 24)
        _TD[3][x] = d9 | (d13 << 8) | (d11 << 16) | (d14 << 24)

        for k in range(4):
            v = 0
            for r in range(4):
                v |= _gmul(x, IM[r][k]) << (8 * r)
            _IMC[k][x] = v


_build_crypto_tables()


def _expand_key(key):
    w = [int.from_bytes(key[4 * i:4 * i + 4], "little") for i in range(4)]
    for i in range(4, 44):
        t = w[i - 1]
        if i % 4 == 0:
            b0 = (t >> 8) & 0xFF
            b1 = (t >> 16) & 0xFF
            b2 = (t >> 24) & 0xFF
            b3 = t & 0xFF
            t = _SBOX[b0] | (_SBOX[b1] << 8) | (_SBOX[b2] << 16) | (_SBOX[b3] << 24)
            t ^= _RCON[i // 4 - 1]
        w.append(w[i - 4] ^ t)
    return w


def _enc_block(c0, c1, c2, c3, w):
    c0 ^= w[0]; c1 ^= w[1]; c2 ^= w[2]; c3 ^= w[3]
    for r in range(1, 10):
        k = r * 4
        n0 = _TE[0][c0 & 0xFF] ^ _TE[1][(c1 >> 8) & 0xFF] ^ _TE[2][(c2 >> 16) & 0xFF] ^ _TE[3][c3 >> 24] ^ w[k]
        n1 = _TE[0][c1 & 0xFF] ^ _TE[1][(c2 >> 8) & 0xFF] ^ _TE[2][(c3 >> 16) & 0xFF] ^ _TE[3][c0 >> 24] ^ w[k + 1]
        n2 = _TE[0][c2 & 0xFF] ^ _TE[1][(c3 >> 8) & 0xFF] ^ _TE[2][(c0 >> 16) & 0xFF] ^ _TE[3][c1 >> 24] ^ w[k + 2]
        n3 = _TE[0][c3 & 0xFF] ^ _TE[1][(c0 >> 8) & 0xFF] ^ _TE[2][(c1 >> 16) & 0xFF] ^ _TE[3][c2 >> 24] ^ w[k + 3]
        c0, c1, c2, c3 = n0, n1, n2, n3

    S = _SBOX
    f0 = S[c0 & 0xFF] | (S[(c1 >> 8) & 0xFF] << 8) | (S[(c2 >> 16) & 0xFF] << 16) | (S[c3 >> 24] << 24)
    f1 = S[c1 & 0xFF] | (S[(c2 >> 8) & 0xFF] << 8) | (S[(c3 >> 16) & 0xFF] << 16) | (S[c0 >> 24] << 24)
    f2 = S[c2 & 0xFF] | (S[(c3 >> 8) & 0xFF] << 8) | (S[(c0 >> 16) & 0xFF] << 16) | (S[c1 >> 24] << 24)
    f3 = S[c3 & 0xFF] | (S[(c0 >> 8) & 0xFF] << 8) | (S[(c1 >> 16) & 0xFF] << 16) | (S[c2 >> 24] << 24)
    return f0 ^ w[40], f1 ^ w[41], f2 ^ w[42], f3 ^ w[43]


def _dec_block(c0, c1, c2, c3, w):
    dw = list(w)
    for r in range(1, 10):
        for j in range(4):
            idx = 4 * r + j
            dw[idx] = (_IMC[0][dw[idx] & 0xFF] ^ _IMC[1][(dw[idx] >> 8) & 0xFF]
                       ^ _IMC[2][(dw[idx] >> 16) & 0xFF] ^ _IMC[3][dw[idx] >> 24])

    TD0, TD1, TD2, TD3 = _TD
    c0 ^= w[40]; c1 ^= w[41]; c2 ^= w[42]; c3 ^= w[43]
    for r in range(9, 0, -1):
        k = r * 4
        n0 = TD0[c0 & 0xFF] ^ TD1[(c3 >> 8) & 0xFF] ^ TD2[(c2 >> 16) & 0xFF] ^ TD3[c1 >> 24] ^ dw[k]
        n1 = TD0[c1 & 0xFF] ^ TD1[(c0 >> 8) & 0xFF] ^ TD2[(c3 >> 16) & 0xFF] ^ TD3[c2 >> 24] ^ dw[k + 1]
        n2 = TD0[c2 & 0xFF] ^ TD1[(c1 >> 8) & 0xFF] ^ TD2[(c0 >> 16) & 0xFF] ^ TD3[c3 >> 24] ^ dw[k + 2]
        n3 = TD0[c3 & 0xFF] ^ TD1[(c2 >> 8) & 0xFF] ^ TD2[(c1 >> 16) & 0xFF] ^ TD3[c0 >> 24] ^ dw[k + 3]
        c0, c1, c2, c3 = n0, n1, n2, n3

    IS = _INV_SBOX
    f0 = IS[c0 & 0xFF] | (IS[(c3 >> 8) & 0xFF] << 8) | (IS[(c2 >> 16) & 0xFF] << 16) | (IS[c1 >> 24] << 24)
    f1 = IS[c1 & 0xFF] | (IS[(c0 >> 8) & 0xFF] << 8) | (IS[(c3 >> 16) & 0xFF] << 16) | (IS[c2 >> 24] << 24)
    f2 = IS[c2 & 0xFF] | (IS[(c1 >> 8) & 0xFF] << 8) | (IS[(c0 >> 16) & 0xFF] << 16) | (IS[c3 >> 24] << 24)
    f3 = IS[c3 & 0xFF] | (IS[(c2 >> 8) & 0xFF] << 8) | (IS[(c1 >> 16) & 0xFF] << 16) | (IS[c0 >> 24] << 24)
    return f0 ^ w[0], f1 ^ w[1], f2 ^ w[2], f3 ^ w[3]


def _to_ints(blk):
    return (int.from_bytes(blk[0:4], "little"),
            int.from_bytes(blk[4:8], "little"),
            int.from_bytes(blk[8:12], "little"),
            int.from_bytes(blk[12:16], "little"))


def _from_ints(i0, i1, i2, i3):
    return (i0.to_bytes(4, "little") + i1.to_bytes(4, "little") +
            i2.to_bytes(4, "little") + i3.to_bytes(4, "little"))


def _cbc_encrypt(key, iv, data):
    w = _expand_key(key)
    pad = 16 - len(data) % 16
    data = data + bytes([pad]) * pad
    out = bytearray()
    p = _to_ints(iv)
    for i in range(0, len(data), 16):
        b = _to_ints(data[i:i + 16])
        b = (b[0] ^ p[0], b[1] ^ p[1], b[2] ^ p[2], b[3] ^ p[3])
        e = _enc_block(*b, w)
        out += _from_ints(*e)
        p = e
    return bytes(out)


def _cbc_decrypt(key, iv, data):
    if not data or len(data) % 16 != 0:
        return b""
    w = _expand_key(key)
    out = bytearray()
    p = _to_ints(iv)
    for i in range(0, len(data), 16):
        c = _to_ints(data[i:i + 16])
        d = _dec_block(*c, w)
        out += _from_ints(d[0] ^ p[0], d[1] ^ p[1], d[2] ^ p[2], d[3] ^ p[3])
        p = c
    pad = out[-1] if out else 0
    if 1 <= pad <= 16 and out[-pad:] == bytes([pad]) * pad:
        out = out[:-pad]
    return bytes(out)


# ---------------- RSA PKCS#1 v1.5 ----------------
def _parse_rsa_pub(pem):
    b64 = re.sub(r"-----[^-]+-----|\s", "", pem)
    der = base64.b64decode(b64)

    def _tlv(d, off):
        tag = d[off]
        ln = d[off + 1]
        ho = 2
        if ln & 0x80:
            nb = ln & 0x7F
            ln = int.from_bytes(d[off + 2:off + 2 + nb], "big")
            ho = 2 + nb
        end = off + ho + ln
        return tag, off + ho, end, d[off + ho:end]

    _, _, _, outer = _tlv(der, 0)
    _, s1o, s1e, _ = _tlv(outer, 0)
    _, bso, bse, _ = _tlv(outer, s1e)
    inner = outer[bso + 1:bse]
    _, _, _, seq = _tlv(inner, 0)
    _, no, ne, _ = _tlv(seq, 0)
    _, eo, ee, _ = _tlv(seq, ne)
    n = int.from_bytes(seq[no:ne], "big")
    e = int.from_bytes(seq[eo:ee], "big")
    return n, e


def _rsa_pkcs1_encrypt(msg, n, e):
    k = (n.bit_length() + 7) // 8
    mlen = len(msg)
    if mlen > k - 11:
        raise ValueError("message too long")
    ps = bytearray()
    while len(ps) < k - mlen - 3:
        b = random.randint(1, 255)
        ps.append(b)
    em = b"\x00\x02" + bytes(ps) + b"\x00" + msg
    c = pow(int.from_bytes(em, "big"), e, n)
    return c.to_bytes(k, "big")


# ============================================================
# 繁简转换与搜索关键词映射
# ============================================================
# 常见影视类型繁简对照 + 常见别名
_TS_MAP = {
    # 类型
    "愛情": "爱情", "爱情": "爱情",
    "喜劇": "喜剧", "喜剧": "喜剧",
    "恐怖": "恐怖", "驚悚": "惊悚", "惊悚": "惊悚",
    "動作": "动作", "动作": "动作",
    "科幻": "科幻",
    "劇情": "剧情", "剧情": "剧情",
    "懸疑": "悬疑", "悬疑": "悬疑",
    "戰爭": "战争", "战争": "战争",
    "動畫": "动画", "动画": "动画",
    "奇幻": "奇幻",
    "冒險": "冒险", "冒险": "冒险",
    "犯罪": "犯罪",
    "家庭": "家庭",
    "歷史": "历史", "历史": "历史",
    "武俠": "武侠", "武侠": "武侠",
    "古裝": "古装", "古装": "古装",
    "青春": "青春",
    "勵志": "励志", "励志": "励志",
    "情感": "情感",
    "推理": "推理",
    "經典": "经典", "经典": "经典",
    "紀實": "纪实", "纪实": "纪实",
    "紀錄": "纪录", "纪录": "纪录",
    "音樂": "音乐", "音乐": "音乐",
    "運動": "运动", "运动": "运动",
    "美食": "美食",
    "旅遊": "旅游", "旅游": "旅游",
    "訪談": "访谈", "访谈": "访谈",
    "財經": "财经", "财经": "财经",
    "曲藝": "曲艺", "曲艺": "曲艺",
    "社會": "社会", "社会": "社会",
    "熱血": "热血", "热血": "热血",
    "機戰": "机战", "机战": "机战",
    "校園": "校园", "校园": "校园",
    "少女": "少女",
    "少年": "少年",
    "蘿莉": "萝莉", "萝莉": "萝莉",
    "早教": "早教",
    "益智": "益智",
    "親子": "亲子", "亲子": "亲子",
    "兒童": "儿童", "儿童": "儿童",
    "玩具": "玩具",
    "遊戲": "游戏", "游戏": "游戏",
    "選秀": "选秀", "选秀": "选秀",
    "槍戰": "枪战", "枪战": "枪战",
    "搞笑": "搞笑",
    "文藝": "文艺", "文艺": "文艺",
    "生活": "生活",
    "都市": "都市",
    "鄉村": "乡村", "乡村": "乡村",
    "農村": "农村", "农村": "农村",
    "商戰": "商战", "商战": "商战",
    "閃婚": "闪婚", "闪婚": "闪婚",
    "重生": "重生",
    "穿越": "穿越",
    "總裁": "总裁", "总裁": "总裁",
    "女戀": "女恋", "女恋": "女恋",
    "腦洞": "脑洞", "脑洞": "脑洞",
    "仙俠": "仙侠", "仙侠": "仙侠",
    "爽文": "爽文",
    "網劇": "网剧", "网剧": "网剧",
    "反轉": "反转", "反转": "反转",
    "微電影": "微电影", "微电影": "微电影",
    "網絡": "网络", "网络": "网络",
    "直播": "直播",
    "播報": "播报", "播报": "播报",
    "故事": "故事",
    "情景": "情景",
    "求職": "求职", "求职": "求职",
    "警匪": "警匪",
    "原創": "原创", "原创": "原创",
    "AI漫": "AI漫",
    "其他": "其他", "其它": "其它",
    # 地区
    "大陸": "大陆", "大陆": "大陆",
    "香港": "香港",
    "台灣": "台湾", "台湾": "台湾",
    "美國": "美国", "美国": "美国",
    "韓國": "韩国", "韩国": "韩国",
    "日本": "日本",
    "英國": "英国", "英国": "英国",
    "法國": "法国", "法国": "法国",
    "德國": "德国", "德国": "德国",
    "泰國": "泰国", "泰国": "泰国",
    "印度": "印度",
    "義大利": "意大利", "意大利": "意大利",
    "西班牙": "西班牙",
    "新加坡": "新加坡",
    "加拿大": "加拿大",
    "歐美": "欧美", "欧美": "欧美",
    # 语言
    "國語": "国语", "国语": "国语",
    "粵語": "粤语", "粤语": "粤语",
    "英語": "英语", "英语": "英语",
    "日語": "日语", "日语": "日语",
    "韓語": "韩语", "韩语": "韩语",
    "法語": "法语", "法语": "法语",
    "德語": "德语", "德语": "德语",
    "閩南語": "闽南语", "闽南语": "闽南语",
}


def _to_simplified(text):
    """繁简转换（覆盖常见影视词汇）"""
    result = []
    i = 0
    s = str(text)
    # 优先匹配最长词
    while i < len(s):
        matched = False
        for length in range(min(4, len(s) - i), 0, -1):
            substr = s[i:i + length]
            if substr in _TS_MAP:
                result.append(_TS_MAP[substr])
                i += length
                matched = True
                break
        if not matched:
            result.append(s[i])
            i += 1
    return "".join(result)


# ============================================================
# LRU 缓存
# ============================================================
class _LruCache:
    def __init__(self, maxsize=128, ttl=300):
        self._cache = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key, default=None):
        now = time.time()
        if key in self._cache:
            ts, value = self._cache[key]
            if now - ts < self._ttl:
                self._cache.move_to_end(key)
                return value
            del self._cache[key]
        return default

    def set(self, key, value):
        now = time.time()
        expired = [k for k, (ts, _) in self._cache.items() if now - ts > self._ttl]
        for k in expired:
            del self._cache[k]
        self._cache[key] = (now, value)
        self._cache.move_to_end(key)
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def clear(self):
        self._cache.clear()


# ============================================================
# 客户端
# ============================================================
class _Client(object):
    def __init__(self, host=None):
        h = host or HOST
        try:
            r = _http(SITE, timeout=6, retries=1)
            txt = (r or "").strip()
            if txt.startswith("http"):
                h = txt.split()[0]
            else:
                dom = (json.loads(txt) or {}).get("domain") or ""
                if dom.startswith("http"):
                    h = dom
        except Exception:
            pass
        self.host = h
        self.sk = "".join(random.choice("0123456789abcdef") for _ in range(128))
        pub = json.loads(_http(h + "/api.php/qijiappapi.index/getPublicKey", retries=2))
        pk = pub["data"]["public_key"].replace("\\/", "/")
        n, e = _parse_rsa_pub(pk)
        enc = base64.b64encode(_rsa_pkcs1_encrypt(self.sk.encode(), n, e)).decode()
        r = _http(h + "/api.php/qijiappapi.index/handshake", {
            "encrypted_key": enc, "device_id": DEVICE_ID,
            "timestamp": int(time.time())}, retries=2)
        j = json.loads(r)
        if j.get("code") != 1:
            raise Exception("handshake fail: " + str(j.get("msg", "unknown")))
        self.sid = j["data"]["session_id"]
        self.k = bytes.fromhex(self.sk[:32])
        self.iv = bytes.fromhex(self.sk[32:64])
        self.expire = time.time() + SESSION_TTL

    def call(self, ep, params=None):
        if time.time() > self.expire:
            raise Exception("session expired")
        r = _http(self.host + "/api.php/qijiappapi.index/" + ep, params or {},
                  {"app-session-id": self.sid}, retries=2)
        j = json.loads(r)
        if j.get("code") != 1:
            return None
        d = j.get("data")
        if isinstance(d, str) and len(d) > 8:
            try:
                raw = _cbc_decrypt(self.k, self.iv, base64.b64decode(d))
                return json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                return None
        return d


# ============================================================
# Spider
# ============================================================
class Spider(_BaseSpider):

    def __init__(self):
        self._cli = None
        self._types = {}
        self._filters = {}
        self._home_vods = None
        self._detail_cache = _LruCache(maxsize=60, ttl=1500)
        self._play_cache = _LruCache(maxsize=120, ttl=600)
        self._search_cache = _LruCache(maxsize=30, ttl=300)
        # 搜索优化：本地索引缓存
        self._local_index = []        # 本地索引数据
        self._local_index_ts = 0      # 索引时间戳
        self._local_index_ttl = 600   # 索引有效期 10 分钟
        # 搜索元数据
        self._all_classes = set()     # 所有类型名称
        self._all_areas = set()       # 所有地区名称
        self._all_years = set()       # 所有年份
        self._all_langs = set()       # 所有语言

    def init(self, extend=""):
        self._extend = extend
        try:
            self._warmup()
        except Exception:
            pass
        return ""

    def getName(self):
        return "4K影视"

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def _client(self):
        if self._cli is None or time.time() > self._cli.expire:
            self._cli = _Client()
        return self._cli

    def _warmup(self):
        init = self._client().call("initV119", {
            "device_id": DEVICE_ID, "app_version": APP_VER})
        if not init:
            self._fallback_types()
            return

        home_vods = []
        for t in init.get("type_list", []):
            tid = t.get("type_id")
            if tid is None:
                continue
            self._types[tid] = t.get("type_name", str(tid))

            # 收集搜索元数据
            ext = t.get("type_extend", "")
            if ext:
                try:
                    e = json.loads(ext)
                    for a in str(e.get("area", "")).split(","):
                        if a.strip():
                            self._all_areas.add(a.strip())
                    for y in str(e.get("year", "")).split(","):
                        if y.strip():
                            self._all_years.add(y.strip())
                    for l in str(e.get("lang", "")).split(","):
                        if l.strip():
                            self._all_langs.add(l.strip())
                    for c in str(e.get("class", "")).split(","):
                        if c.strip():
                            self._all_classes.add(c.strip())
                except:
                    pass

            for v in t.get("recommend_list", []):
                home_vods.append({
                    "vod_id": str(v.get("vod_id", "")),
                    "vod_name": v.get("vod_name", ""),
                    "vod_pic": (v.get("vod_pic") or "").replace("\\/", "/"),
                    "vod_remarks": v.get("vod_remarks", ""),
                })

            fs = []
            try:
                ext = json.loads(t.get("type_extend") or "{}")
                for key, label in (("class", "类型"), ("area", "地区"),
                                   ("year", "年份"), ("lang", "语言")):
                    raw = str(ext.get(key) or "").strip()
                    if not raw:
                        continue
                    opts = [o.strip() for o in raw.split(",") if o.strip()]
                    fs.append({"key": key, "name": label,
                               "value": [{"n": "全部", "v": ""}] +
                                        [{"n": o, "v": o} for o in opts]})
            except Exception:
                pass
            if fs:
                self._filters[tid] = fs

        seen = set()
        deduped = []
        for v in home_vods:
            vid = v["vod_id"]
            if vid and vid not in seen:
                seen.add(vid)
                deduped.append(v)
        self._home_vods = deduped[:60]

        if not self._types:
            self._fallback_types()

    def _fallback_types(self):
        self._types = {0: "全部", 1: "电视剧", 2: "动漫", 3: "电影", 4: "综艺",
                       5: "短剧", 21: "直播", 22: "少儿"}

    @staticmethod
    def _parse_urls(s):
        s = s.strip()
        try:
            return json.loads(s)
        except Exception:
            pass
        try:
            return eval(s)
        except Exception:
            pairs = re.findall(r'["\'/]name["\'/]\s*:\s*["\']([^"\']*)["\'].*?["\'/]url["\'/]\s*:\s*["\']([^"\']*)["\']', s, re.S)
            return [{"name": n, "url": u} for n, u in pairs]

    @staticmethod
    def _fmt_vod_list(items):
        out = []
        for v in items:
            item = {
                "vod_id": str(v.get("vod_id", "")),
                "vod_name": v.get("vod_name", ""),
                "vod_pic": (v.get("vod_pic") or "").replace("\\/", "/"),
                "vod_remarks": v.get("vod_remarks", ""),
            }
            if v.get("vod_score"):
                item["vod_score"] = str(v["vod_score"])
            if v.get("vod_douban_score"):
                item["vod_douban_score"] = str(v["vod_douban_score"])
            if v.get("vod_actor"):
                item["vod_actor"] = v["vod_actor"]
            if v.get("vod_area"):
                item["vod_area"] = v["vod_area"]
            if v.get("vod_lang"):
                item["vod_lang"] = v["vod_lang"]
            if v.get("vod_year"):
                item["vod_year"] = str(v["vod_year"])
            if v.get("vod_blurb"):
                item["vod_blurb"] = v["vod_blurb"]
            if v.get("vod_class"):
                item["vod_class"] = v["vod_class"]
            out.append(item)
        return out

    # ---------- 首页 ----------
    def homeContent(self, filter1=1):
        out = {"class": [{"type_id": k, "type_name": v} for k, v in self._types.items()]}
        if self._filters:
            out["filters"] = {str(k): v for k, v in self._filters.items()}
        return out

    def homeVideoContent(self):
        if self._home_vods is None:
            try:
                self._warmup()
            except Exception:
                pass
        return {"list": self._home_vods or []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg=1, filter1=1, extend=None):
        if isinstance(extend, str):
            try:
                extend = json.loads(extend) if extend.strip() else {}
            except Exception:
                extend = {}
        extend = extend or {}
        try:
            page = int(pg)
        except (TypeError, ValueError):
            page = 1

        r = self._client().call("typeFilterVodList", {
            "type_id": tid, "page": page,
            "area": extend.get("area", ""), "year": extend.get("year", ""),
            "lang": extend.get("lang", ""), "class": extend.get("class", ""),
            "sort": extend.get("sort", "")})

        vods = self._fmt_vod_list((r or {}).get("recommend_list", []))
        more = len(vods) >= PAGE_SIZE
        return {
            "list": vods,
            "page": page,
            "pagecount": page + 1 if more else page,
            "limit": str(PAGE_SIZE),
            "total": (page + 50) if more else page * PAGE_SIZE
        }

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = str(ids[0]) if ids else ""
        if not vid:
            return {"list": []}

        cached = self._detail_cache.get(vid)
        if cached is not None:
            return cached

        try:
            r = self._client().call("vodDetail3", {"vod_id": int(vid)})
        except (TypeError, ValueError):
            return {"list": []}
        if not r:
            return {"list": []}

        vod = r.get("vod", {})
        froms, urls = [], []
        for p in r.get("vod_play_list", []):
            pi = p.get("player_info", {})
            show = pi.get("show") or p.get("from", "")
            eps_raw = p.get("urls")
            if isinstance(eps_raw, str):
                eps_raw = self._parse_urls(eps_raw)
            if not eps_raw:
                continue

            line_ua = pi.get("user_agent") or UA
            line_headers = pi.get("headers") or {}
            line_parse = pi.get("parse", "")
            line_parse_type = str(pi.get("player_parse_type", "1"))

            eps = []
            for i, e in enumerate(eps_raw):
                name = str(e.get("name", i + 1))
                u = e.get("url", "")
                token = e.get("token", "")
                parse_api_url = e.get("parse_api_url", "")
                is_vip = e.get("isVip", False)
                if is_vip:
                    name = "[VIP]" + name
                if u.startswith("http"):
                    tok = "D|" + base64.b64encode(json.dumps({
                        "u": u, "t": token, "p": parse_api_url,
                        "ua": line_ua, "h": line_headers
                    }, ensure_ascii=False).encode()).decode()
                else:
                    tok = "P|" + base64.b64encode(json.dumps({
                        "p": line_parse or parse_api_url,
                        "t": line_parse_type,
                        "u": u,
                        "tok": token,
                        "ua": line_ua,
                        "h": line_headers
                    }, ensure_ascii=False).encode()).decode()
                eps.append(name + "$" + tok)
            froms.append(show)
            urls.append("#".join(eps))

        v = {
            "vod_id": vid,
            "vod_name": vod.get("vod_name", ""),
            "vod_pic": (vod.get("vod_pic") or "").replace("\\/", "/"),
            "type_name": (vod.get("vod_class") or "").split(",")[0],
            "vod_year": vod.get("vod_year", ""),
            "vod_area": vod.get("vod_area", ""),
            "vod_actor": vod.get("vod_actor", ""),
            "vod_director": vod.get("vod_director", ""),
            "vod_content": (vod.get("vod_blurb") or "").replace("\\n", "\n"),
            "vod_remarks": vod.get("vod_remarks", ""),
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }
        if vod.get("vod_score"):
            v["vod_score"] = str(vod["vod_score"])
        if vod.get("vod_douban_score"):
            v["vod_douban_score"] = str(vod["vod_douban_score"])
        if vod.get("vod_lang"):
            v["vod_lang"] = vod["vod_lang"]
        if vod.get("vod_hits"):
            v["vod_hits"] = str(vod["vod_hits"])

        ret = {"list": [v]}
        self._detail_cache.set(vid, ret)
        return ret

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags=None):
        tok = str(id)
        cached = self._play_cache.get(tok)
        if cached is not None:
            return cached

        if tok.startswith("D|"):
            try:
                info = json.loads(base64.b64decode(tok[2:]))
            except Exception:
                return {"url": "", "msg": "参数错误"}
            real = info.get("u", "")
            ua = info.get("ua") or UA
            hdrs = info.get("h") or {}
            out = {"url": real, "header": {**{"User-Agent": ua}, **hdrs}}

        elif tok.startswith("P|"):
            try:
                info = json.loads(base64.b64decode(tok[2:]))
            except Exception:
                return {"url": "", "msg": "参数错误"}
            u = info.get("u", "")
            p = info.get("p", "")
            t = str(info.get("t", "1"))
            token = info.get("tok", "")
            ua = info.get("ua") or UA
            hdrs = info.get("h") or {}
            real = ""

            if t == "2" and p:
                real, ua = self._external_parse(p, u, token)
            else:
                try:
                    url_enc = base64.b64encode(
                        _cbc_encrypt(NSKEY, NSKEY, u.encode())).decode()
                    r = self._client().call("vodParse", {
                        "url": url_enc, "parse_api": p, "token": token,
                        "player_parse_type": t, "base_api": p + u})
                    if isinstance(r, dict):
                        inner = r.get("json")
                        if isinstance(inner, str):
                            try:
                                r = json.loads(inner)
                            except Exception:
                                pass
                    real = ((r or {}) if isinstance(r, dict) else {}).get("url") or ""
                    real = real.replace("\\/", "/")
                except Exception:
                    real = ""

            if not real:
                return {"url": "", "msg": "解析失败，请换线路"}
            out = {"url": real, "header": {**{"User-Agent": ua}, **hdrs}}
        else:
            out = {"url": tok, "header": {"User-Agent": UA}}

        self._play_cache.set(tok, out)
        return out

    def _external_parse(self, parse_api, u, token=""):
        url = parse_api + u
        if token:
            url += ("&" if "?" in url else "?") + "token=" + urllib.parse.quote(token)
        for attempt in range(2):
            try:
                r = _http(url, timeout=20, retries=1)
                try:
                    j = json.loads(r)
                except Exception:
                    m = re.search(r'"url"\s*:\s*"([^"]+)"', r)
                    j = {"url": m.group(1)} if m else {}
                real = (j.get("url") or "").replace("\\/", "/")
                ua = j.get("UA") or UA
                if real.startswith("http"):
                    return real, ua
            except Exception:
                pass
            if attempt == 0:
                time.sleep(1.2)
        return "", UA

    def localProxy(self, param):
        return {}

    # ============================================================
    # 搜索优化（核心重构）
    # ============================================================

    def _build_local_index(self):
        """构建本地索引：拉取热门分类前 N 页数据"""
        if (time.time() - self._local_index_ts < self._local_index_ttl
                and len(self._local_index) >= SEARCH_MAX_LOCAL_INDEX):
            return

        index = []
        # 优先拉取电影(3)和电视剧(1)的前几页
        for tid in (3, 1, 2, 4):
            if len(index) >= SEARCH_MAX_LOCAL_INDEX:
                break
            for page in range(1, SEARCH_FALLBACK_PAGES + 1):
                try:
                    r = self._client().call("typeFilterVodList", {
                        "type_id": tid, "page": page,
                        "area": "", "year": "", "lang": "", "class": "", "sort": ""})
                    items = (r or {}).get("recommend_list", [])
                    index.extend(items)
                    if len(items) < PAGE_SIZE:
                        break
                except Exception:
                    break
                if len(index) >= SEARCH_MAX_LOCAL_INDEX:
                    break

        self._local_index = index[:SEARCH_MAX_LOCAL_INDEX]
        self._local_index_ts = time.time()

    @staticmethod
    def _match_score(item, keyword):
        """计算匹配度得分，越高越相关"""
        kw = keyword.lower()
        score = 0
        name = str(item.get("vod_name", "")).lower()
        actor = str(item.get("vod_actor", "")).lower()
        director = str(item.get("vod_director", "")).lower()
        blurb = str(item.get("vod_blurb", "")).lower()
        cls = str(item.get("vod_class", "")).lower()
        sub = str(item.get("vod_sub", "")).lower()

        # 片名完全匹配 = 最高优先级
        if kw == name:
            score += 1000
        elif kw in name:
            score += 500
        # 片名开头匹配
        if name.startswith(kw):
            score += 300
        # 演员匹配
        if kw in actor:
            score += 200
        # 导演匹配
        if kw in director:
            score += 150
        # 别名/副标题匹配
        if kw in sub:
            score += 100
        # 类型匹配
        if kw in cls:
            score += 50
        # 简介匹配
        if kw in blurb:
            score += 10
        return score

    def _local_filter(self, items, keyword):
        """本地多字段模糊过滤并排序"""
        results = []
        for item in items:
            score = self._match_score(item, keyword)
            if score > 0:
                results.append((score, item))
        # 按匹配度降序
        results.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in results]

    def _search_by_class(self, cls, page):
        """按精确类型搜索"""
        all_results = []
        # 搜索电影(3)和电视剧(1)，其他分类视情况
        for tid in (3, 1, 2, 4, 5):
            try:
                r = self._client().call("typeFilterVodList", {
                    "type_id": tid, "page": page,
                    "area": "", "year": "", "lang": "", "class": cls, "sort": ""})
                items = (r or {}).get("recommend_list", [])
                all_results.extend(items)
            except Exception:
                pass

        vods = self._fmt_vod_list(all_results)
        # 去重
        seen = set()
        deduped = []
        for v in vods:
            vid = v["vod_id"]
            if vid and vid not in seen:
                seen.add(vid)
                deduped.append(v)

        has_more = len(deduped) >= PAGE_SIZE
        return {
            "list": deduped[:PAGE_SIZE],
            "page": page,
            "pagecount": page + 1 if has_more else page,
            "limit": str(PAGE_SIZE),
            "total": (page + 20) if has_more else page * len(deduped)
        }

    def _search_by_year(self, year, page):
        """按年份搜索"""
        all_results = []
        for tid in (3, 1, 2, 4, 5):
            try:
                r = self._client().call("typeFilterVodList", {
                    "type_id": tid, "page": page,
                    "area": "", "year": year, "lang": "", "class": "", "sort": ""})
                items = (r or {}).get("recommend_list", [])
                all_results.extend(items)
            except Exception:
                pass

        vods = self._fmt_vod_list(all_results)
        seen = set()
        deduped = []
        for v in vods:
            vid = v["vod_id"]
            if vid and vid not in seen:
                seen.add(vid)
                deduped.append(v)

        has_more = len(deduped) >= PAGE_SIZE
        return {
            "list": deduped[:PAGE_SIZE],
            "page": page,
            "pagecount": page + 1 if has_more else page,
            "limit": str(PAGE_SIZE),
            "total": (page + 20) if has_more else page * len(deduped)
        }

    def _search_by_lang(self, lang, page):
        """按语言搜索"""
        all_results = []
        for tid in (3, 1, 2, 4, 5):
            try:
                r = self._client().call("typeFilterVodList", {
                    "type_id": tid, "page": page,
                    "area": "", "year": "", "lang": lang, "class": "", "sort": ""})
                items = (r or {}).get("recommend_list", [])
                all_results.extend(items)
            except Exception:
                pass

        vods = self._fmt_vod_list(all_results)
        seen = set()
        deduped = []
        for v in vods:
            vid = v["vod_id"]
            if vid and vid not in seen:
                seen.add(vid)
                deduped.append(v)

        has_more = len(deduped) >= PAGE_SIZE
        return {
            "list": deduped[:PAGE_SIZE],
            "page": page,
            "pagecount": page + 1 if has_more else page,
            "limit": str(PAGE_SIZE),
            "total": (page + 20) if has_more else page * len(deduped)
        }

    def _search_by_area(self, area, page):
        """按地区搜索"""
        all_results = []
        for tid in (3, 1, 2, 4, 5):
            try:
                r = self._client().call("typeFilterVodList", {
                    "type_id": tid, "page": page,
                    "area": area, "year": "", "lang": "", "class": "", "sort": ""})
                items = (r or {}).get("recommend_list", [])
                all_results.extend(items)
            except Exception:
                pass

        vods = self._fmt_vod_list(all_results)
        seen = set()
        deduped = []
        for v in vods:
            vid = v["vod_id"]
            if vid and vid not in seen:
                seen.add(vid)
                deduped.append(v)

        has_more = len(deduped) >= PAGE_SIZE
        return {
            "list": deduped[:PAGE_SIZE],
            "page": page,
            "pagecount": page + 1 if has_more else page,
            "limit": str(PAGE_SIZE),
            "total": (page + 20) if has_more else page * len(deduped)
        }

    def _search_by_name(self, keyword, page):
        """片名/演员搜索：searchList + 本地过滤 + 本地索引兜底"""
        # 1. 尝试 searchList（服务端会返回固定热门列表）
        api_results = []
        try:
            r = self._client().call("searchList", {"wd": keyword, "page": page})
            api_results = (r or {}).get("search_list", [])
        except Exception:
            pass

        # 2. 对 searchList 结果做本地过滤
        filtered = self._local_filter(api_results, keyword)

        # 3. 如果结果太少，用本地索引补充
        if len(filtered) < 5:
            self._build_local_index()
            index_hits = self._local_filter(self._local_index, keyword)
            # 合并去重
            seen = {x["vod_id"] for x in filtered}
            for item in index_hits:
                if item.get("vod_id") not in seen:
                    seen.add(item["vod_id"])
                    filtered.append(item)

        vods = self._fmt_vod_list(filtered)
        return {
            "list": vods[:PAGE_SIZE],
            "page": page,
            "pagecount": page + 1 if len(vods) >= PAGE_SIZE else page,
            "limit": str(PAGE_SIZE),
            "total": page * len(vods)
        }

    def searchContent(self, key, quick=False, pg=None):
        """
        智能多模式搜索
        根据关键词特征自动选择最优搜索策略
        """
        if isinstance(key, (list, tuple)):
            args = list(key)
            key = ""
            pg = None
            for a in args:
                if a is None:
                    continue
                if isinstance(a, str) and not key:
                    key = a.strip()
                elif isinstance(a, int) and pg is None:
                    pg = a
            if not key and args:
                key = str(args[0] or "").strip()
        else:
            key = str(key or "").strip()

        try:
            page = int(pg) if pg not in (None, "", 0, "0") else 1
        except (TypeError, ValueError):
            page = 1

        if not key:
            return {"list": [], "page": 1, "pagecount": 1, "limit": str(PAGE_SIZE), "total": 0}

        cache_key = "%s|%s" % (key, page)
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            return cached

        # 繁简转换
        key_simp = _to_simplified(key)

        # 智能路由
        ret = None

        # 模式1: 精确类型匹配（效果最好）
        if key_simp in self._all_classes:
            ret = self._search_by_class(key_simp, page)

        # 模式2: 年份匹配
        elif re.match(r"^(19|20)\d{2}$", key_simp):
            ret = self._search_by_year(key_simp, page)

        # 模式3: 地区匹配
        elif key_simp in self._all_areas:
            ret = self._search_by_area(key_simp, page)

        # 模式4: 语言匹配
        elif key_simp in self._all_langs:
            ret = self._search_by_lang(key_simp, page)

        # 模式5: 片名/演员搜索（兜底）
        else:
            ret = self._search_by_name(key, page)

        self._search_cache.set(cache_key, ret)
        return ret

    def searchContentPage(self, key, quick=False, pg=None):
        return self.searchContent(key, quick, pg)


# ============================================================
# TVBox 模块级入口
# ============================================================
_SP = None
_SP_T = 0.0


def _ensure():
    global _SP, _SP_T
    if _SP is None or time.time() - _SP_T > 8 * 3600:
        _SP = Spider()
        _SP_T = time.time()
    return _SP


def init(ext=""):
    return _ensure().init(ext)


def getName():
    return _ensure().getName()


def homeContent(filter1=1):
    return _ensure().homeContent(filter1)


def homeVideoContent():
    return _ensure().homeVideoContent()


def categoryContent(tid, pg=1, filter1=1, extend=None):
    return _ensure().categoryContent(tid, pg, filter1, extend)


def detailContent(ids):
    return _ensure().detailContent(ids)


def playerContent(flag, id, vipFlags=None):
    return _ensure().playerContent(flag, id, vipFlags)


def searchContent(key, quick=0, pg=None):
    return _ensure().searchContent(key, quick, pg)


def searchContentPage(key, quick=0, pg=None):
    return _ensure().searchContentPage(key, quick, pg)


# ============================================================
# 自测
# ============================================================
if __name__ == "__main__":
    t0 = time.time()
    sp = Spider()
    sp.init()
    print("[1] %s | 分类 %d 个" % (sp.getName(), len(sp.homeContent(1)["class"])))

    home = sp.homeContent(1)
    fs = home.get("filters", {})
    print("[2] 筛选组:", len(fs), "| 电影筛选项:",
          sum(len(f["value"]) - 1 for f in fs.get("3", [])))

    hv = sp.homeVideoContent()
    print("[3] 首页推荐:", len(hv["list"]), "部")
    if hv["list"]:
        print("    首部:", hv["list"][0]["vod_name"])

    cat = sp.categoryContent("3", 1, 1, {})
    print("[4] 电影列表:", len(cat["list"]), "部")

    # 测试各种搜索模式
    print("\n=== 搜索模式测试 ===\n")

    # 模式1: 类型搜索
    for kw in ["爱情", "喜剧", "恐怖", "科幻"]:
        t1 = time.time()
        r = sp.searchContent(kw)
        print("类型搜 [%s] → %d 条 (%.2fs) | 前3: %s" % (
            kw, len(r["list"]), time.time() - t1,
            [x["vod_name"] for x in r["list"][:3]]))

    # 模式2: 年份搜索
    for kw in ["2025", "2024"]:
        t1 = time.time()
        r = sp.searchContent(kw)
        print("年份搜 [%s] → %d 条 (%.2fs) | 前3: %s" % (
            kw, len(r["list"]), time.time() - t1,
            [x["vod_name"] for x in r["list"][:3]]))

    # 模式3: 地区搜索
    for kw in ["美国", "韩国", "香港"]:
        t1 = time.time()
        r = sp.searchContent(kw)
        print("地区搜 [%s] → %d 条 (%.2fs) | 前3: %s" % (
            kw, len(r["list"]), time.time() - t1,
            [x["vod_name"] for x in r["list"][:3]]))

    # 模式4: 片名搜索（本地过滤）
    for kw in ["爱", "盗", "战", "2026"]:
        t1 = time.time()
        r = sp.searchContent(kw)
        print("片名搜 [%s] → %d 条 (%.2fs) | 前3: %s" % (
            kw, len(r["list"]), time.time() - t1,
            [x["vod_name"] for x in r["list"][:3]]))

    # 详情 + 播放测试
    if cat["list"]:
        d = sp.detailContent([cat["list"][0]["vod_id"]])
        v = d["list"][0]
        print("\n[6] 详情:", v["vod_name"], "| 线路:", v["vod_play_from"].replace("$$$", "+"))
        pr = sp.playerContent(v["vod_play_from"].split("$$$")[0],
                              v["vod_play_url"].split("$$$")[0]
                              .split("#")[0].split("$")[1])
        print("[7] 播放:", (pr.get("url") or pr.get("msg", ""))[:80])

    print("\n自测完成 ✔ 总耗时 %.1fs" % (time.time() - t0))

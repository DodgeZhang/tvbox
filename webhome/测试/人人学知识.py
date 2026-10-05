#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国家智慧教育平台 —— 影视TV（T4服务端）适配版（级联修复版 + 图片补全版）
特性：
1. 教材列表获取采用稳定串行方式（多重降级），确保分类数据正常加载
2. 视频解析并发加速（ThreadPoolExecutor），解析耗时 2~5s
3. 多资源类型：national_lesson / elite_lesson / singing / teaching_lesson
4. 四级联动筛选（学段→年级→学科→版本→册次）
5. 支持 ext 覆盖 cookie/ua/referer/origin/basic/cdn1/cdn2
6. 自动 URL 解码解决 TV 端编码问题
7. 修复数据源重复问题：按"学段·年级·学科·版本·册次"去重
8. 所有筛选下拉框首位增加"全部"选项
9. 【新增】分类列表/详情页/推荐位全面补全封面图（thumbnails / preview.frame1）
"""

import sys, os, json, re, hashlib, base64, time, urllib.parse, urllib.request, hmac, tempfile, threading
from typing import List, Dict, Optional, Tuple, Any
from base.spider import Spider

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    _HAS_CONCURRENT = True
except ImportError:
    _HAS_CONCURRENT = False

# ========== 配置常量 ==========
BASIC = "https://basic.smartedu.cn"
CDN1 = "https://s-file-1.ykt.cbern.com.cn"
CDN2 = "https://s-file-2.ykt.cbern.com.cn"

DEFAULT_COOKIE = ""

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://basic.smartedu.cn/",
    "Origin": "https://basic.smartedu.cn",
}

XD_LIST = ["小学", "初中", "高中", "小学（五•四学制）", "初中（五•四学制）"]

GRADE_ORDER = {
    "一年级": 1, "二年级": 2, "三年级": 3, "四年级": 4, "五年级": 5, "六年级": 6,
    "七年级": 7, "八年级": 8, "九年级": 9,
    "高一": 10, "高一年级": 10, "高二": 11, "高二年级": 11, "高三": 12,
    "一至二年级": 1.5, "三至四年级": 3.5, "五至六年级": 5.5,
    "学生读本": 0, "中国历史": 0, "世界历史": 0,
}

RES_TYPE_FETCHERS = {
    "national_lesson": "_fetch_national_lesson",
    "elite_lesson": "_fetch_elite_lesson",
    "singing": "_fetch_singing_resource",
    "teaching_lesson": "_fetch_detail_json",
}


# ========== 纯 Python AES-128-ECB ==========
class _AES128:
    _sbox = bytes([
        0x63,0x7C,0x77,0x7B,0xF2,0x6B,0x6F,0xC5,0x30,0x01,0x67,0x2B,0xFE,0xD7,0xAB,0x76,
        0xCA,0x82,0xC9,0x7D,0xFA,0x59,0x47,0xF0,0xAD,0xD4,0xA2,0xAF,0x9C,0xA4,0x72,0xC0,
        0xB7,0xFD,0x93,0x26,0x36,0x3F,0xF7,0xCC,0x34,0xA5,0xE5,0xF1,0x71,0xD8,0x31,0x15,
        0x04,0xC7,0x23,0xC3,0x18,0x96,0x05,0x9A,0x07,0x12,0x80,0xE2,0xEB,0x27,0xB2,0x75,
        0x09,0x83,0x2C,0x1A,0x1B,0x6E,0x5A,0xA0,0x52,0x3B,0xD6,0xB3,0x29,0xE3,0x2F,0x84,
        0x53,0xD1,0x00,0xED,0x20,0xFC,0xB1,0x5B,0x6A,0xCB,0xBE,0x39,0x4A,0x4C,0x58,0xCF,
        0xD0,0xEF,0xAA,0xFB,0x43,0x4D,0x33,0x85,0x45,0xF9,0x02,0x7F,0x50,0x3C,0x9F,0xA8,
        0x51,0xA3,0x40,0x8F,0x92,0x9D,0x38,0xF5,0xBC,0xB6,0xDA,0x21,0x10,0xFF,0xF3,0xD2,
        0xCD,0x0C,0x13,0xEC,0x5F,0x97,0x44,0x17,0xC4,0xA7,0x7E,0x3D,0x64,0x5D,0x19,0x73,
        0x60,0x81,0x4F,0xDC,0x22,0x2A,0x90,0x88,0x46,0xEE,0xB8,0x14,0xDE,0x5E,0x0B,0xDB,
        0xE0,0x32,0x3A,0x0A,0x49,0x06,0x24,0x5C,0xC2,0xD3,0xAC,0x62,0x91,0x95,0xE4,0x79,
        0xE7,0xC8,0x37,0x6D,0x8D,0xD5,0x4E,0xA9,0x6C,0x56,0xF4,0xEA,0x65,0x7A,0xAE,0x08,
        0xBA,0x78,0x25,0x2E,0x1C,0xA6,0xB4,0xC6,0xE8,0xDD,0x74,0x1F,0x4B,0xBD,0x8B,0x8A,
        0x70,0x3E,0xB5,0x66,0x48,0x03,0xF6,0x0E,0x61,0x35,0x57,0xB9,0x86,0xC1,0x1D,0x9E,
        0xE1,0xF8,0x98,0x11,0x69,0xD9,0x8E,0x94,0x9B,0x1E,0x87,0xE9,0xCE,0x55,0x28,0xDF,
        0x8C,0xA1,0x89,0x0D,0xBF,0xE6,0x42,0x68,0x41,0x99,0x2D,0x0F,0xB0,0x54,0xBB,0x16,
    ])
    _inv_sbox = bytes([
        0x52,0x09,0x6A,0xD5,0x30,0x36,0xA5,0x38,0xBF,0x40,0xA3,0x9E,0x81,0xF3,0xD7,0xFB,
        0x7C,0xE3,0x39,0x82,0x9B,0x2F,0xFF,0x87,0x34,0x8E,0x43,0x44,0xC4,0xDE,0xE9,0xCB,
        0x54,0x7B,0x94,0x32,0xA6,0xC2,0x23,0x3D,0xEE,0x4C,0x95,0x0B,0x42,0xFA,0xC3,0x4E,
        0x08,0x2E,0xA1,0x66,0x28,0xD9,0x24,0xB2,0x76,0x5B,0xA2,0x49,0x6D,0x8B,0xD1,0x25,
        0x72,0xF8,0xF6,0x64,0x86,0x68,0x98,0x16,0xD4,0xA4,0x5C,0xCC,0x5D,0x65,0xB6,0x92,
        0x6C,0x70,0x48,0x50,0xFD,0xED,0xB9,0xDA,0x5E,0x15,0x46,0x57,0xA7,0x8D,0x9D,0x84,
        0x90,0xD8,0xAB,0x00,0x8C,0xBC,0xD3,0x0A,0xF7,0xE4,0x58,0x05,0xB8,0xB3,0x45,0x06,
        0xD0,0x2C,0x1E,0x8F,0xCA,0x3F,0x0F,0x02,0xC1,0xAF,0xBD,0x03,0x01,0x13,0x8A,0x6B,
        0x3A,0x91,0x11,0x41,0x4F,0x67,0xDC,0xEA,0x97,0xF2,0xCF,0xCE,0xF0,0xB4,0xE6,0x73,
        0x96,0xAC,0x74,0x22,0xE7,0xAD,0x35,0x85,0xE2,0xF9,0x37,0xE8,0x1C,0x75,0xDF,0x6E,
        0x47,0xF1,0x1A,0x71,0x1D,0x29,0xC5,0x89,0x6F,0xB7,0x62,0x0E,0xAA,0x18,0xBE,0x1B,
        0xFC,0x56,0x3E,0x4B,0xC6,0xD2,0x79,0x20,0x9A,0xDB,0xC0,0xFE,0x78,0xCD,0x5A,0xF4,
        0x1F,0xDD,0xA8,0x33,0x88,0x07,0xC7,0x31,0xB1,0x12,0x10,0x59,0x27,0x80,0xEC,0x5F,
        0x60,0x51,0x7F,0xA9,0x19,0xB5,0x4A,0x0D,0x2D,0xE5,0x7A,0x9F,0x93,0xC9,0x9C,0xEF,
        0xA0,0xE0,0x3B,0x4D,0xAE,0x2A,0xF5,0xB0,0xC8,0xEB,0xBB,0x3C,0x83,0x53,0x99,0x61,
        0x17,0x2B,0x04,0x7E,0xBA,0x77,0xD6,0x26,0xE1,0x69,0x14,0x63,0x55,0x21,0x0C,0x7D,
    ])

    @classmethod
    def _gf_mul(cls, a: int, b: int) -> int:
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

    @classmethod
    def _expand_key(cls, key: bytes) -> List[bytes]:
        Nk, Nr = 4, 10
        Rcon = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1B,0x36]
        w = bytearray(key)
        for i in range(Nk, 4 * (Nr + 1)):
            temp = w[(i-1)*4 : i*4]
            if i % Nk == 0:
                temp = temp[1:] + temp[:1]
                temp = bytearray([cls._sbox[b] for b in temp])
                temp[0] ^= Rcon[i // Nk - 1]
            prev = w[(i - Nk)*4 : (i - Nk + 1)*4]
            w.extend([temp[j] ^ prev[j] for j in range(4)])
        return [bytes(w[i*16:(i+1)*16]) for i in range(Nr + 1)]

    @classmethod
    def decrypt_block(cls, ct: bytes, key: bytes) -> bytes:
        rk = cls._expand_key(key)
        s = bytearray(ct)
        cls._add_round_key(s, rk[10])
        for r in range(9, 0, -1):
            cls._shift_rows(s, True)
            cls._sub_bytes(s, True)
            cls._add_round_key(s, rk[r])
            cls._mix_columns(s, True)
        cls._shift_rows(s, True)
        cls._sub_bytes(s, True)
        cls._add_round_key(s, rk[0])
        return bytes(s)

    @classmethod
    def _sub_bytes(cls, s: bytearray, inv: bool = False):
        box = cls._inv_sbox if inv else cls._sbox
        for i in range(16):
            s[i] = box[s[i]]

    @classmethod
    def _shift_rows(cls, s: bytearray, inv: bool = False):
        if inv:
            t = s[:]
            s[1],s[5],s[9],s[13] = t[13],t[1],t[5],t[9]
            s[2],s[6],s[10],s[14] = t[10],t[14],t[2],t[6]
            s[3],s[7],s[11],s[15] = t[7],t[11],t[15],t[3]
        else:
            t = s[:]
            s[1],s[5],s[9],s[13] = t[5],t[9],t[13],t[1]
            s[2],s[6],s[10],s[14] = t[10],t[14],t[2],t[6]
            s[3],s[7],s[11],s[15] = t[15],t[3],t[7],t[11]

    @classmethod
    def _mix_columns(cls, s: bytearray, inv: bool = False):
        for c in range(4):
            i = c * 4
            a,b,c_,d = s[i],s[i+1],s[i+2],s[i+3]
            if not inv:
                s[i]   = cls._gf_mul(a,2) ^ cls._gf_mul(b,3) ^ c_ ^ d
                s[i+1] = a ^ cls._gf_mul(b,2) ^ cls._gf_mul(c_,3) ^ d
                s[i+2] = a ^ b ^ cls._gf_mul(c_,2) ^ cls._gf_mul(d,3)
                s[i+3] = cls._gf_mul(a,3) ^ b ^ c_ ^ cls._gf_mul(d,2)
            else:
                s[i]   = cls._gf_mul(a,0x0E)^cls._gf_mul(b,0x0B)^cls._gf_mul(c_,0x0D)^cls._gf_mul(d,0x09)
                s[i+1] = cls._gf_mul(a,0x09)^cls._gf_mul(b,0x0E)^cls._gf_mul(c_,0x0B)^cls._gf_mul(d,0x0D)
                s[i+2] = cls._gf_mul(a,0x0D)^cls._gf_mul(b,0x09)^cls._gf_mul(c_,0x0E)^cls._gf_mul(d,0x0B)
                s[i+3] = cls._gf_mul(a,0x0B)^cls._gf_mul(b,0x0D)^cls._gf_mul(c_,0x09)^cls._gf_mul(d,0x0E)

    @classmethod
    def _add_round_key(cls, s: bytearray, rk: bytes):
        for i in range(16):
            s[i] ^= rk[i]

    @classmethod
    def decrypt(cls, ct: bytes, key: bytes) -> bytes:
        if len(key) < 16:
            key = key.ljust(16, b'\x00')
        else:
            key = key[:16]
        pt = bytearray()
        for i in range(0, len(ct), 16):
            blk = ct[i:i+16]
            if len(blk) < 16:
                blk = blk + b'\x00' * (16 - len(blk))
            pt.extend(cls.decrypt_block(blk, key))
        if not pt:
            return b''
        pad = pt[-1]
        if 1 <= pad <= 16 and all(b == pad for b in pt[-pad:]):
            return bytes(pt[:-pad])
        return bytes(pt)


# ========== 线程安全缓存 ==========
class _Cache:
    def __init__(self):
        self._store = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            return self._store.get(key)

    def set(self, key, val):
        with self._lock:
            self._store[key] = val


# ========== T4 Spider 类 ==========
class Spider(Spider):
    def getName(self):
        return "国家智慧教育平台"

    def init(self, extend=""):
        ext = {}
        if isinstance(extend, str) and extend.strip():
            try:
                ext = json.loads(extend)
            except (json.JSONDecodeError, TypeError):
                ext = {}
        elif isinstance(extend, dict):
            ext = extend

        self.basic = ext.get("basic") or BASIC
        self.cdn1 = ext.get("cdn1") or CDN1
        self.cdn2 = ext.get("cdn2") or CDN2

        self.headers = dict(HEADERS)
        if ext.get("ua"):
            self.headers["User-Agent"] = ext["ua"]
        if ext.get("referer"):
            self.headers["Referer"] = ext["referer"]
        if ext.get("origin"):
            self.headers["Origin"] = ext["origin"]

        cookie_from_ext = ext.get("cookie", "")
        self.cookie = cookie_from_ext if cookie_from_ext else DEFAULT_COOKIE

        self.access_token = ""
        self.mac_key = ""
        if self.cookie:
            parsed = self._parse_cookie(self.cookie)
            self.access_token = parsed.get("access_token", "")
            self.mac_key = parsed.get("mac_key", "")
            if not self.access_token:
                m = re.search(r'accessToken=([^;]+)', self.cookie)
                if m:
                    self.access_token = m.group(1)
            if self.access_token:
                self.headers["accessToken"] = self.access_token
            if self.cookie:
                self.headers["Cookie"] = self.cookie

        self._recommend_config = ext.get("recommend") or [
            {"name": "九年级·语文·统编版·上册", "tags": {"zxxxd": "初中", "zxxnj": "九年级", "zxxxk": "语文", "zxxbb": "统编版", "zxxcc": "上册"}},
            {"name": "九年级·数学·苏科版·上册", "tags": {"zxxxd": "初中", "zxxnj": "九年级", "zxxxk": "数学", "zxxbb": "苏科版", "zxxcc": "上册"}},
            {"name": "九年级·英语·译林版·上册", "tags": {"zxxxd": "初中", "zxxnj": "九年级", "zxxxk": "英语", "zxxbb": "译林版", "zxxcc": "上册"}},
            {"name": "九年级·化学·人教版·上册", "tags": {"zxxxd": "初中", "zxxnj": "九年级", "zxxxk": "化学", "zxxbb": "人教版", "zxxcc": "上册"}},
            {"name": "九年级·历史·统编版·上册", "tags": {"zxxxd": "初中", "zxxnj": "九年级", "zxxxk": "历史", "zxxbb": "统编版", "zxxcc": "上册"}},
            {"name": "九年级·道德与法治·统编版·上册", "tags": {"zxxxd": "初中", "zxxnj": "九年级", "zxxxk": "道德与法治", "zxxbb": "统编版", "zxxcc": "上册"}},
            {"name": "九年级·物理·苏科版·上册", "tags": {"zxxxd": "初中", "zxxnj": "九年级", "zxxxk": "物理", "zxxbb": "苏科版", "zxxcc": "上册"}},
            {"name": "九年级·体育与健康·人教版·上册", "tags": {"zxxxd": "初中", "zxxnj": "九年级", "zxxxk": "体育与健康", "zxxbb": "人教版", "zxxcc": "全一册"}},
        ]

        self._tree_cache = _Cache()
        self._resource_cache = _Cache()
        self._res_map_cache = _Cache()
        self._node_index_cache = _Cache()
        self._tm_list_cache = None
        self._tm_list_lock = threading.Lock()
        self._tm_id_map = {}
        self._xd_tm_map = {}
        self._act_cache = _Cache()
        self._resolve_lock = threading.Lock()

        self._ensure_tm_loaded()

    def _ensure_tm_loaded(self, retry=2):
        if self._tm_id_map:
            return
        for attempt in range(retry + 1):
            try:
                tm_list = self._fetch_tm_list()
                if tm_list:
                    self._build_tm_maps(tm_list)
                    print(f"[init] 教材索引构建完成: {len(self._tm_id_map)} 套")
                    return
                else:
                    print(f"[init] 教材列表获取失败，重试 {attempt}/{retry}")
                    time.sleep(1.5 ** attempt)
            except Exception as e:
                print(f"[init] 教材列表加载异常: {e}，重试 {attempt}/{retry}")
                time.sleep(1.5 ** attempt)
        print("[init] 教材列表最终加载失败，分类可能为空")

    def _http_get(self, url: str, timeout: int = 20, use_mac: bool = False,
                  use_cookie: bool = True, json_resp: bool = True, retry: int = 3):
        for attempt in range(retry):
            try:
                h = dict(self.headers)
                if use_cookie and self.cookie:
                    h["Cookie"] = self.cookie
                if use_mac and self.access_token and self.mac_key:
                    h["Authorization"] = self._mac_header(url)
                    h["accessToken"] = self.access_token
                    h["sdp-app-id"] = "e5649925-441d-4a53-b525-51a2f1c4e0a8"
                elif self.access_token:
                    h["accessToken"] = self.access_token
                req = urllib.request.Request(url, headers=h, method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = resp.read().decode("utf-8", errors="ignore")
                    if json_resp:
                        try:
                            return json.loads(data)
                        except Exception:
                            return data
                    return data
            except Exception as e:
                if attempt == retry - 1:
                    raise Exception(f"请求失败（重试{retry}次）: {e}")
                time.sleep(1.5 ** attempt)
        return None

    def _with_token(self, url: str) -> str:
        if not url:
            return url
        url = str(url)
        if self.access_token and "accessToken=" not in url:
            url += ("?" if "?" not in url else "&") + f"accessToken={urllib.parse.quote(self.access_token)}"
        return url

    def _parse_cookie(self, cookie_str: str) -> Dict:
        if not cookie_str:
            return {}
        m = re.search(r'UC_TOKEN-[^=]+=([^;]+)', cookie_str)
        if not m:
            return {"cookie": cookie_str}
        token_b64 = m.group(1)
        try:
            b64 = token_b64.replace("-", "+").replace("_", "/")
            while len(b64) % 4:
                b64 += "="
            payload = base64.b64decode(b64).decode("utf-8")
            obj = json.loads(payload)
            return {
                "access_token": obj.get("access_token", ""),
                "mac_key": obj.get("mac_key", ""),
                "user_id": obj.get("user_id", ""),
                "cookie": cookie_str
            }
        except Exception:
            return {"cookie": cookie_str}

    def _hmac_sha256_base64(self, key: str, msg: str) -> str:
        sig = hmac.new(key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(sig).decode()

    def _mac_header(self, url: str, method: str = "GET") -> str:
        if not self.access_token or not self.mac_key:
            return ""
        p = urllib.parse.urlparse(url)
        nonce = f"{int(time.time()*1000)}:{os.urandom(4).hex()}"
        raw = f"{nonce}\n{method.upper()}\n{p.path}\n{p.hostname}\n"
        mac = self._hmac_sha256_base64(self.mac_key, raw)
        return f'MAC id="{self.access_token}",nonce="{nonce}",mac="{mac}"'

    def _concurrent_fetch(self, tasks: List[Tuple[str, Dict]], max_workers: int = 6,
                          timeout_per_task: int = 15) -> List[Tuple[str, Any]]:
        if not _HAS_CONCURRENT:
            results = []
            for task in tasks:
                name = task[0]
                if isinstance(task[1], dict):
                    url = task[1]["url"]
                    use_mac = task[1].get("use_mac", False)
                    use_cookie = task[1].get("use_cookie", True)
                else:
                    url = task[1]
                    use_mac = False
                    use_cookie = True
                try:
                    res = self._http_get(url, timeout=timeout_per_task, use_mac=use_mac, use_cookie=use_cookie)
                    results.append((name, res))
                except Exception:
                    results.append((name, None))
            return results

        results = []
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(tasks)))) as executor:
            future_map = {}
            for task in tasks:
                name = task[0]
                if isinstance(task[1], dict):
                    url = task[1]["url"]
                    use_mac = task[1].get("use_mac", False)
                    use_cookie = task[1].get("use_cookie", True)
                else:
                    url = task[1]
                    use_mac = False
                    use_cookie = True
                future = executor.submit(
                    self._http_get, url, timeout_per_task, use_mac, use_cookie, True, 2
                )
                future_map[future] = name

            for future in as_completed(future_map, timeout=timeout_per_task * 2):
                name = future_map[future]
                try:
                    res = future.result()
                    results.append((name, res))
                except Exception:
                    results.append((name, None))
        return results

    # ==================== 图片提取工具（新增核心） ====================
    def _extract_thumb(self, data: Dict) -> str:
        """
        从教材/资源字典中提取最优封面图。
        优先级：custom_properties.thumbnails[0] > relations.*.custom_properties.preview.frame1
        """
        if not data or not isinstance(data, dict):
            return ""
        thumbs = (data.get("custom_properties") or {}).get("thumbnails", [])
        if thumbs and isinstance(thumbs, list):
            for t in thumbs:
                if t and isinstance(t, str):
                    return t
        relations = data.get("relations") or {}
        for rk, arr in relations.items():
            if not isinstance(arr, list):
                continue
            for item in arr:
                if not isinstance(item, dict):
                    continue
                preview = (item.get("custom_properties") or {}).get("preview", {})
                frame1 = preview.get("frame1", "")
                if frame1:
                    return frame1
                r_thumbs = (item.get("custom_properties") or {}).get("thumbnails", [])
                if r_thumbs and isinstance(r_thumbs, list):
                    for t in r_thumbs:
                        if t and isinstance(t, str):
                            return t
        return ""

    def _fetch_tm_list(self) -> List[Dict]:
        if self._tm_list_cache is not None:
            return self._tm_list_cache

        with self._tm_list_lock:
            if self._tm_list_cache is not None:
                return self._tm_list_cache

            hosts = [self.cdn1, self.cdn2, "https://s-file-3.ykt.cbern.com.cn"]
            part_urls = []

            for host in hosts:
                try:
                    data = self._http_get(
                        f"{host}/zxx/ndrs/national_lesson/teachingmaterials/version/data_version.json",
                        timeout=15, use_cookie=False, use_mac=False
                    )
                    if data and isinstance(data, dict) and "urls" in data:
                        urls = data["urls"]
                        if isinstance(urls, str):
                            part_urls = [u.strip() for u in urls.split(",") if u.strip()]
                        elif isinstance(urls, list):
                            part_urls = [u.strip() for u in urls if u.strip()]
                        if part_urls:
                            break
                except Exception:
                    pass

            if not part_urls:
                part_urls = [
                    f"{self.cdn1}/zxx/ndrs/national_lesson/teachingmaterials/part_100.json",
                    f"{self.cdn1}/zxx/ndrs/national_lesson/teachingmaterials/part_101.json",
                    f"{self.cdn1}/zxx/ndrs/national_lesson/teachingmaterials/part_102.json",
                    f"{self.cdn1}/zxx/ndrs/national_lesson/teachingmaterials/part_103.json",
                    f"{self.cdn1}/zxx/ndrs/national_lesson/teachingmaterials/part_104.json",
                    f"{self.cdn1}/zxx/ndrs/national_lesson/teachingmaterials/part_105.json",
                ]

            all_items = []
            for url in part_urls:
                try:
                    data = self._http_get(url, timeout=30, use_cookie=False, use_mac=False)
                    if isinstance(data, list):
                        all_items.extend(data)
                except Exception:
                    continue

            valid = self._filter_tm_items(all_items)

            if valid:
                self._tm_list_cache = valid
                print(f"[教材列表] 成功获取 {len(valid)} 套教材")
            else:
                print("[教材列表] 所有尝试均失败，请检查网络或 Cookie")
                self._tm_list_cache = []

            return self._tm_list_cache

    def _filter_tm_items(self, items: List[Dict]) -> List[Dict]:
        valid = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            if "id" not in item or not item["id"]:
                continue
            if item["id"] in seen:
                continue
            title = item.get("title") or (item.get("global_title") or {}).get("zh-CN", "")
            if not title or len(title) < 2:
                continue
            rtype = item.get("resource_type_code", "")
            if rtype and rtype not in ("teachingmaterials", "teachingmaterial"):
                continue
            valid.append(item)
            seen.add(item["id"])
        return valid

    def _build_tm_maps(self, tm_list: List[Dict]):
        self._tm_id_map = {}
        self._xd_tm_map = {}
        seen_keys = set()

        for item in tm_list:
            tags = item.get("tag_list", [])
            tag_map = {}
            for t in tags:
                if isinstance(t, dict) and "tag_dimension_id" in t:
                    tag_map[t["tag_dimension_id"]] = t.get("tag_name", "")

            xd = tag_map.get("zxxxd", "")
            nj = tag_map.get("zxxnj", "")
            xk = tag_map.get("zxxxk", "")
            bb = tag_map.get("zxxbb", "")
            cc = tag_map.get("zxxcc", "")

            if not xd or not nj or not xk or not bb or not cc:
                continue

            key = f"{xd}·{nj}·{xk}·{bb}·{cc}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

            tm_id = item.get("id", "")
            thumb = self._extract_thumb(item)

            self._tm_id_map[key] = tm_id

            if xd not in self._xd_tm_map:
                self._xd_tm_map[xd] = []
            self._xd_tm_map[xd].append({
                "id": tm_id, "key": key,
                "xd": xd, "nj": nj, "xk": xk, "bb": bb, "cc": cc,
                "thumb": thumb,
            })

    def _fetch_tm_tree(self, tm_id: str) -> List[Dict]:
        cached = self._tree_cache.get(tm_id)
        if cached:
            return cached
        hosts = [self.cdn1, self.cdn2]
        for host in hosts:
            try:
                data = self._http_get(f"{host}/zxx/ndrv2/national_lesson/trees/{tm_id}.json",
                                      timeout=20, use_cookie=True)
                if data and isinstance(data, list) and len(data) > 0:
                    self._tree_cache.set(tm_id, data)
                    self._build_node_index(tm_id, data)
                    return data
            except Exception:
                pass
        return []

    def _fetch_tm_resources(self, tm_id: str) -> List[Dict]:
        cached = self._resource_cache.get(tm_id)
        if cached:
            return cached
        hosts = [self.cdn1, self.cdn2]
        part_urls = []
        for host in hosts:
            try:
                data = self._http_get(f"{host}/zxx/ndrs/national_lesson/teachingmaterials/{tm_id}/resources/parts.json",
                                      timeout=15, use_cookie=True)
                if isinstance(data, list):
                    part_urls = [u for u in data if isinstance(u, str) and re.search(r"part_\d+\.json", u)]
                    if part_urls:
                        break
            except Exception:
                pass
        if not part_urls:
            part_urls = [f"{self.cdn1}/zxx/ndrs/national_lesson/teachingmaterials/{tm_id}/resources/part_100.json"]

        tasks = [("res_part", url) for url in part_urls]
        fetch_results = self._concurrent_fetch(tasks, max_workers=min(6, len(part_urls)), timeout_per_task=30)

        all_list = []
        for _, data in fetch_results:
            if isinstance(data, list):
                all_list.extend(data)

        valid_res = []
        seen = set()
        for r in all_list:
            rtype = r.get("resource_type_code", "")
            if rtype not in ("national_lesson", "elite_lesson", "singing", "teaching_lesson"):
                continue
            aid = r.get("id", "")
            if not aid or aid in seen:
                continue
            seen.add(aid)
            valid_res.append(r)

        self._resource_cache.set(tm_id, valid_res)
        self._build_res_map(tm_id, valid_res)
        return valid_res

    def _build_node_index(self, tm_id: str, tree: List[Dict]):
        index = {}
        def walk(nodes):
            for node in nodes:
                if not node:
                    continue
                nid = node.get("id")
                if nid:
                    index[nid] = node
                children = node.get("child_nodes") or node.get("children") or []
                if children:
                    walk(children)
        walk(tree)
        self._node_index_cache.set(tm_id, index)

    def _build_res_map(self, tm_id: str, resources: List[Dict]):
        res_map = {}
        for r in resources:
            ch_ids = r.get("chapter_ids", [])
            if not ch_ids:
                continue
            target_cid = ch_ids[-1]
            if target_cid not in res_map:
                res_map[target_cid] = []
            res_map[target_cid].append(r)
        self._res_map_cache.set(tm_id, res_map)

    def _pick_best_video(self, ti_items: List[Dict]) -> Optional[str]:
        if not ti_items:
            return None
        prefer = ["1920x1080", "1280x720", "852x480", "640x360"]
        candidates = []
        for it in ti_items:
            fmt = str(it.get("ti_format", "")).lower()
            stor = str(it.get("ti_storage", ""))
            stors = it.get("ti_storages", [])
            if fmt != "m3u8" and ".m3u8" not in stor:
                continue
            first_url = None
            if stors:
                first_url = str(stors[0])
            elif stor:
                first_url = stor
            if not first_url:
                continue
            if first_url.startswith("cs_path:${ref-path}/"):
                first_url = "https://r1-ndr-private.ykt.cbern.com.cn/" + first_url.replace("cs_path:${ref-path}/", "")
            elif first_url.startswith("cs_path:"):
                first_url = "https://r1-ndr-private.ykt.cbern.com.cn/" + re.sub(r"^cs_path:\$\{ref-path\}/?", "", first_url)
            if first_url.startswith("//"):
                first_url = "https:" + first_url
            if re.search(r"\.m3u8(\?|$)", first_url, re.I):
                candidates.append(first_url)
        if not candidates:
            return None
        for p in prefer:
            for c in candidates:
                if p in c:
                    return c
        return candidates[0]

    def _fetch_national_lesson(self, activity_id: str) -> Optional[Dict]:
        hosts = [self.cdn2, self.cdn1]
        paths = [
            f"/zxx/ndrv2/national_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/national_lesson/resources/details/{activity_id}.json"
        ]
        tasks = []
        for host in hosts:
            for path in paths:
                tasks.append(("nl", host + path))
        results = self._concurrent_fetch(tasks, max_workers=4, timeout_per_task=15)
        for _, data in results:
            if data and isinstance(data, dict) and (data.get("id") or data.get("title") or data.get("relations")):
                return data
        return None

    def _fetch_elite_lesson(self, activity_id: str) -> Optional[Dict]:
        hosts = [self.cdn1, self.cdn2]
        paths = [
            f"/zxx/ndrv2/elite_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/elite_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrv2/elite_lesson/resources/{activity_id}/relation_resource.json",
            f"/zxx/ndrs/elite_lesson/resources/{activity_id}/relation_resource.json",
        ]
        tasks = []
        for host in hosts:
            for path in paths:
                tasks.append(("elite", host + path))
        results = self._concurrent_fetch(tasks, max_workers=4, timeout_per_task=12)
        for _, data in results:
            if data and isinstance(data, dict) and (
                data.get("title") or data.get("global_title") or data.get("relations") or data.get("resource_type_code")
            ):
                return data
        return None

    def _fetch_singing_resource(self, activity_id: str) -> Optional[Dict]:
        hosts = [self.cdn2, self.cdn1, "https://s-file-3.ykt.cbern.com.cn"]
        paths = [
            f"/zxx/ndrs/singing/resources/{activity_id}/relation_resource.json",
            f"/zxx/ndrv2/singing/resources/{activity_id}/relation_resource.json",
            f"/zxx/ndrv2/national_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/national_lesson/resources/details/{activity_id}.json",
        ]
        tasks = []
        for host in hosts:
            for path in paths:
                tasks.append(("sing", host + path))
        results = self._concurrent_fetch(tasks, max_workers=4, timeout_per_task=10)
        for _, data in results:
            if data and isinstance(data, dict):
                return data
        return None

    def _fetch_detail_json(self, activity_id: str) -> Optional[Dict]:
        if not activity_id:
            return None
        hosts = [self.cdn1, self.cdn2, "https://s-file-3.ykt.cbern.com.cn"]
        strict_paths = [
            f"/zxx/ndrv2/resources/{activity_id}.json",
            f"/zxx/ndrs/resources/{activity_id}.json",
            f"/zxx/ndrv2/national_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/national_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrv2/elite_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/elite_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrv2/resources/details/{activity_id}.json",
            f"/zxx/ndrs/resources/details/{activity_id}.json",
            f"/zxx/ndrv2/prepare_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrs/prepare_lesson/resources/details/{activity_id}.json",
            f"/zxx/ndrv2/prepare_sub_type/resources/details/{activity_id}.json",
            f"/zxx/ndrv2/resources/tch_material/details/{activity_id}.json",
            f"/zxx/ndrs/resources/tch_material/details/{activity_id}.json",
            f"/zxx/ndrv2/special_edu/resources/details/{activity_id}.json",
        ]
        tasks = []
        for host in hosts:
            for path in strict_paths:
                tasks.append(("detail", host + path))
        results = self._concurrent_fetch(tasks, max_workers=8, timeout_per_task=10)
        for _, data in results:
            if data and isinstance(data, dict) and (
                data.get("title") or data.get("global_title") or data.get("relations") or data.get("resource_type_code")
            ):
                return data
        loose_paths = [
            f"/zxx/ndrv2/elite_lesson/resources/{activity_id}/relation_resource.json",
            f"/zxx/ndrs/elite_lesson/resources/{activity_id}/relation_resource.json",
            f"/zxx/ndrv2/singing/resources/{activity_id}/relation_resource.json",
            f"/zxx/ndrs/singing/resources/{activity_id}/relation_resource.json",
        ]
        tasks2 = []
        for host in hosts:
            for path in loose_paths:
                tasks2.append(("loose", host + path))
        results2 = self._concurrent_fetch(tasks2, max_workers=4, timeout_per_task=8)
        for _, data in results2:
            if data and isinstance(data, dict):
                if activity_id in json.dumps(data, ensure_ascii=False):
                    return data
        return None

    def _resolve_activity(self, activity_id: str, hint_type: str = "") -> List[Dict]:
        if not activity_id:
            raise Exception("activityId 为空")

        cache_key = f"act_{activity_id}_{hint_type}"
        cached = self._act_cache.get(cache_key)
        if cached:
            return cached

        with self._resolve_lock:
            cached2 = self._act_cache.get(cache_key)
            if cached2:
                return cached2

            media = []
            all_data = []

            fetcher_names = list(RES_TYPE_FETCHERS.values())
            if hint_type and hint_type in RES_TYPE_FETCHERS:
                preferred = RES_TYPE_FETCHERS[hint_type]
                fetcher_names = [preferred] + [f for f in fetcher_names if f != preferred]

            if _HAS_CONCURRENT:
                with ThreadPoolExecutor(max_workers=min(4, len(fetcher_names))) as executor:
                    future_map = {}
                    for fname in fetcher_names:
                        method = getattr(self, fname, None)
                        if method is None:
                            continue
                        future = executor.submit(method, activity_id)
                        future_map[future] = fname
                    for future in as_completed(future_map, timeout=25):
                        fname = future_map[future]
                        try:
                            d = future.result()
                            if d:
                                all_data.append((fname, d))
                        except Exception:
                            pass
            else:
                for fname in fetcher_names:
                    method = getattr(self, fname, None)
                    if method is None:
                        continue
                    try:
                        d = method(activity_id)
                        if d:
                            all_data.append((fname, d))
                    except Exception:
                        pass

            for fname, d in all_data:
                try:
                    m = self._extract_media(d)
                    m = [mm for mm in m if mm.get("url") and re.search(r"\.(m3u8|mp4)(\?|$)", mm["url"], re.I)]
                    if m:
                        media = m
                        break
                except Exception:
                    pass

            if not media and all_data:
                for fname, d in all_data:
                    try:
                        sub = self._resolve_video_sub_items(d)
                        if sub:
                            media = sub
                            break
                    except Exception:
                        pass

            if not media:
                try:
                    by_id = self._resolve_by_id(activity_id)
                    if by_id:
                        media = by_id
                except Exception:
                    pass

            if not media:
                last = all_data[-1][1] if all_data else None
                if last:
                    keys = ",".join((last.get("relations") or {}).keys()) or "无relations"
                    raise Exception(f"该课包无视频流（可能是课件/练习）。relations: {keys}")
                raise Exception(f"课包 JSON 获取失败: {activity_id}")

            self._act_cache.set(cache_key, media)
            return media

    def _resolve_by_id(self, content_id: str) -> List[Dict]:
        data = self._fetch_detail_json(content_id)
        if not data:
            raise Exception(f"未找到资源 JSON: {content_id}")
        media = self._extract_media(data)
        if media:
            return media
        items = data.get("ti_items", [])
        for it in items:
            u = it.get("ti_storage", "")
            if it.get("ti_storages"):
                u = it["ti_storages"][0]
            if re.search(r"\.pdf(\?|$)", str(u), re.I):
                if u.startswith("cs_path:"):
                    u = "https://r1-ndr-private.ykt.cbern.com.cn/" + re.sub(r"^cs_path:\$\{ref-path\}/?", "", u)
                return [{
                    "kind": "file",
                    "title": data.get("title") or (data.get("global_title") or {}).get("zh-CN") or content_id,
                    "sub": "PDF",
                    "url": u,
                    "badge": "PDF"
                }]
        raise Exception("资源内没有可播放的视频地址")

    def _resolve_video_sub_items(self, data: Dict) -> List[Dict]:
        if not data or not isinstance(data, dict):
            return []
        candidates = []
        seen_ids = set()
        def _walk(node, depth=0):
            if not node or depth > 8:
                return
            if isinstance(node, list):
                for item in node:
                    _walk(item, depth + 1)
                return
            if not isinstance(node, dict):
                return
            rtype = str(node.get("resource_type_code", ""))
            prom = (node.get("custom_properties") or {}).get("prom_resouce_type", "")
            fmt = (node.get("custom_properties") or {}).get("format", "")
            is_doc = re.match(r"^(lesson_plandesign|learning_task|after_class_exercise|coursewares|assets_document|tch_material)$", rtype, re.I)
            has_media = bool(node.get("ti_items") and len(node.get("ti_items")) > 0)
            if not has_media and not is_doc and node.get("id") and node.get("id") not in seen_ids:
                if (re.search(r"video", rtype, re.I) or
                    re.search(r"lesson", rtype, re.I) or
                    prom == "assets_video" or
                    re.match(r"^(mp4|m3u8)$", str(fmt), re.I)):
                    seen_ids.add(node["id"])
                    candidates.append(node)
            for k, v in node.items():
                if k == "ti_items":
                    continue
                if isinstance(v, (dict, list)):
                    _walk(v, depth + 1)
        _walk(data)
        if not candidates:
            return []

        top_cands = candidates[:6]
        all_media = []
        if _HAS_CONCURRENT:
            with ThreadPoolExecutor(max_workers=min(4, len(top_cands))) as executor:
                future_map = {}
                for cand in top_cands:
                    future = executor.submit(self._fetch_detail_json, cand.get("id"))
                    future_map[future] = cand
                for future in as_completed(future_map, timeout=30):
                    cand = future_map[future]
                    try:
                        d2 = future.result()
                        if not d2:
                            continue
                        m2 = self._extract_media(d2)
                        m2 = [mm for mm in m2 if mm.get("url") and re.search(r"\.(m3u8|mp4)(\?|$)", mm["url"], re.I)]
                        if m2:
                            title_fix = (cand.get("global_title") or {}).get("zh-CN") or cand.get("title", "")
                            for mm in m2:
                                if title_fix:
                                    mm["title"] = title_fix
                            all_media.extend(m2)
                    except Exception:
                        pass
        else:
            for cand in top_cands:
                try:
                    d2 = self._fetch_detail_json(cand.get("id"))
                    if not d2:
                        continue
                    m2 = self._extract_media(d2)
                    m2 = [mm for mm in m2 if mm.get("url") and re.search(r"\.(m3u8|mp4)(\?|$)", mm["url"], re.I)]
                    if m2:
                        title_fix = (cand.get("global_title") or {}).get("zh-CN") or cand.get("title", "")
                        for mm in m2:
                            if title_fix:
                                mm["title"] = title_fix
                        all_media.extend(m2)
                except Exception:
                    pass
        return all_media

    def _extract_media(self, data: Dict) -> List[Dict]:
        out = []
        if not data:
            return out
        title = (data.get("global_title") or {}).get("zh-CN") or data.get("title") or data.get("name", "资源")
        pic = ""
        try:
            thumbs = (data.get("custom_properties") or {}).get("thumbnails", [])
            if thumbs:
                pic = thumbs[0]
        except Exception:
            pass
        def _norm_url(u: str) -> str:
            if not u:
                return ""
            u = str(u)
            if u.startswith("cs_path:${ref-path}/"):
                u = "https://r1-ndr-private.ykt.cbern.com.cn/" + u.replace("cs_path:${ref-path}/", "")
            if u.startswith("//"):
                u = "https:" + u
            return u
        def _push(u, t2="", p2="", badge=""):
            if not u:
                return
            u = _norm_url(u)
            out.append({
                "title": t2 or title,
                "sub": (data.get("provider_list") or [{}])[0].get("name", "智慧教育"),
                "pic": p2 or pic,
                "url": u,
                "badge": badge or ("HLS" if re.search(r"\.m3u8(\?|$)", u, re.I) else ("MP4" if re.search(r"\.mp4(\?|$)", u, re.I) else ""))
            })
        rel_keys = ["national_course_resource", "course_resource", "elite_course_resource", "resources"]
        seen_vid = set()
        for rk in rel_keys:
            arr = (data.get("relations") or {}).get(rk, [])
            if not isinstance(arr, list):
                continue
            for item in arr:
                vurl = self._pick_best_video(item.get("ti_items", []))
                if not vurl or vurl in seen_vid:
                    continue
                seen_vid.add(vurl)
                t2 = (item.get("global_title") or {}).get("zh-CN") or item.get("title", title)
                if not t2 or t2 in ("视频课程", "微课视频", "精品课视频", "视频") or re.match(r"^(视频|微课|精品课)", t2) or re.search(r"\.(mp4|m3u8)$", t2, re.I):
                    t2 = title
                p2 = ""
                try:
                    p2 = ((item.get("custom_properties") or {}).get("preview") or {}).get("frame1", "")
                except Exception:
                    pass
                _push(vurl, t2, p2, "课程视频")
        for rk, arr in (data.get("relations") or {}).items():
            if rk in rel_keys or not isinstance(arr, list):
                continue
            for item in arr:
                vurl = self._pick_best_video(item.get("ti_items", []))
                if vurl and vurl not in seen_vid:
                    seen_vid.add(vurl)
                    t2 = (item.get("global_title") or {}).get("zh-CN") or item.get("title", title)
                    _push(vurl, t2, pic, rk)
        for it in data.get("ti_items", []):
            stors = it.get("ti_storages", [])
            stor = it.get("ti_storage", "")
            if stors:
                for u in stors:
                    if re.search(r"\.(m3u8|mp4)(\?|$)", str(u), re.I):
                        _push(u, it.get("ti_title", title))
            elif stor and re.search(r"\.(m3u8|mp4|pdf)(\?|$)", str(stor), re.I):
                _push(stor, it.get("ti_title", title))
        if data.get("video_url"):
            _push(data["video_url"], title)
        if data.get("media_url"):
            _push(data["media_url"], title)
        if not out:
            seen_urls = set()
            def _deep_scan(node, ctx_title="", depth=0):
                if not node or depth > 8:
                    return
                if isinstance(node, list):
                    for item in node:
                        _deep_scan(item, ctx_title, depth + 1)
                    return
                if not isinstance(node, dict):
                    return
                local_title = node.get("ti_title") or (node.get("global_title") or {}).get("zh-CN") or node.get("title") or ctx_title
                cand = []
                if node.get("ti_storages"):
                    cand.extend(node["ti_storages"])
                if node.get("ti_storage"):
                    cand.append(node["ti_storage"])
                if node.get("video_url"):
                    cand.append(node["video_url"])
                if node.get("play_url"):
                    cand.append(node["play_url"])
                if isinstance(node.get("src"), str):
                    cand.append(node["src"])
                for cu in cand:
                    cu = str(cu)
                    if re.search(r"\.(m3u8|mp4)(\?|$)", cu, re.I) and cu not in seen_urls:
                        seen_urls.add(cu)
                        _push(cu, local_title, "", "深度解析")
                for k, v in node.items():
                    if k in ("ti_storages", "ti_storage"):
                        continue
                    if isinstance(v, (dict, list)):
                        _deep_scan(v, local_title, depth + 1)
            _deep_scan(data, title)
        return out

    def _md5_hex(self, s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    def _aes128_ecb_decrypt(self, key_bytes: bytes, cipher_b64: str) -> bytes:
        raw = base64.b64decode(cipher_b64)
        return _AES128.decrypt(raw, key_bytes)

    def _fetch_video_key_bytes(self, key_url: str) -> bytes:
        key_id = ""
        m = re.search(r"resource_keys/([a-fA-F0-9]+)", key_url)
        if m:
            key_id = m.group(1)
        if not key_id:
            raise Exception("无法解析 keyId")
        base_key = key_url.split("?")[0]
        signs_url = base_key + "/signs"

        modes = [
            {"use_mac": False, "use_cookie": True},
            {"use_mac": True, "use_cookie": True},
            {"use_mac": False, "use_cookie": False},
        ]
        signs_body = None
        for mode in modes:
            try:
                res = self._http_get(signs_url, timeout=10, use_mac=mode["use_mac"], use_cookie=mode["use_cookie"], json_resp=True)
                if res and res.get("nonce"):
                    signs_body = res
                    break
            except Exception:
                pass
        if not signs_body or not signs_body.get("nonce"):
            raise Exception("signs 请求失败")
        nonce = signs_body["nonce"]
        sign = self._md5_hex(nonce + key_id)[:16]
        key_get = base_key + f"?nonce={urllib.parse.quote(nonce)}&sign={urllib.parse.quote(sign)}"

        key_body = None
        for mode in modes:
            try:
                res = self._http_get(key_get, timeout=10, use_mac=mode["use_mac"], use_cookie=mode["use_cookie"], json_resp=True)
                if res and res.get("key"):
                    key_body = res
                    break
            except Exception:
                pass
        if not key_body or not key_body.get("key"):
            raise Exception("key 请求失败")
        sign_bytes = sign.encode("utf-8")[:16]
        return self._aes128_ecb_decrypt(sign_bytes, key_body["key"])

    def _rewrite_m3u8(self, m3u8_url: str) -> str:
        raw = str(m3u8_url)
        base = raw.split("?")[0].rsplit("/", 1)[0] + "/"
        alts = [raw]
        if self.access_token:
            alts.append(raw + ("?" if "?" not in raw else "&") + f"accessToken={urllib.parse.quote(self.access_token)}")
        r2 = raw.replace("r1-ndr-private", "r2-ndr-private")
        if r2 != raw:
            alts.append(r2)
            if self.access_token:
                alts.append(r2 + ("?" if "?" not in r2 else "&") + f"accessToken={urllib.parse.quote(self.access_token)}")
        seen = set()
        alts = [u for u in alts if not (u in seen or seen.add(u))]

        text_body = ""
        modes = [
            {"use_mac": False, "use_cookie": True, "name": "Cookie"},
            {"use_mac": False, "use_cookie": False, "name": "匿名"},
            {"use_mac": True, "use_cookie": True, "name": "MAC"},
        ]
        def _try_fetch(url: str, mode: Dict) -> Optional[str]:
            try:
                h = {
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": "https://basic.smartedu.cn/",
                    "Origin": "https://basic.smartedu.cn",
                }
                if self.access_token:
                    h["accessToken"] = self.access_token
                if mode["use_cookie"] and self.cookie:
                    h["Cookie"] = self.cookie
                req = urllib.request.Request(url, headers=h, method="GET")
                with urllib.request.urlopen(req, timeout=12) as resp:
                    return resp.read().decode("utf-8", errors="ignore")
            except Exception:
                return None

        for mode in modes:
            for u in alts:
                body = _try_fetch(u, mode)
                if body and "#EXTM3U" in body:
                    text_body = body
                    break
            if text_body:
                break

        if not text_body or "#EXTM3U" not in text_body:
            raise Exception("m3u8 拉取失败，所有路径均无效")

        lines = text_body.splitlines()
        out_lines = []
        key_uri = None
        for line in lines:
            if "EXT-X-KEY" in line and 'URI="' in line:
                m = re.search(r'URI="([^"]+)"', line)
                if m:
                    key_uri = m.group(1)
                    if not key_uri.startswith("http"):
                        key_uri = urllib.parse.urljoin(base, key_uri)
                    break

        key_data_uri = ""
        if key_uri:
            try:
                key_bytes = self._fetch_video_key_bytes(key_uri)
                key_b64 = base64.b64encode(key_bytes).decode()
                key_data_uri = f"data:application/octet-stream;base64,{key_b64}"
            except Exception as e:
                print(f"[KEY] 获取失败: {e}，保留原始密钥 URI")
                key_data_uri = self._with_token(key_uri)

        for line in lines:
            if not line:
                out_lines.append(line)
                continue
            if line.startswith("#"):
                if "EXT-X-KEY" in line and 'URI="' in line and key_data_uri:
                    line = re.sub(r'URI="[^"]+"', f'URI="{key_data_uri}"', line)
                out_lines.append(line)
            else:
                seg = line.strip()
                if not seg.startswith("http"):
                    seg = urllib.parse.urljoin(base, seg)
                seg = self._with_token(seg)
                out_lines.append(seg)
        return "\n".join(out_lines)

    def _save_m3u8_local(self, activity_id: str, m3u8_content: str, suffix: str = "") -> Optional[str]:
        tmp_dir = tempfile.gettempdir()
        safe_id = activity_id.replace("-", "_").replace("|", "_")
        if suffix:
            safe_suffix = re.sub(r'[^\w\u4e00-\u9fff]', '_', suffix)[:20]
            filename = os.path.join(tmp_dir, f"smartedu_{safe_id}_{safe_suffix}.m3u8")
        else:
            filename = os.path.join(tmp_dir, f"smartedu_{safe_id}.m3u8")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(m3u8_content)
            return filename
        except Exception as e:
            print(f"[FILE] 写入临时文件失败: {e}")
            return None

    def _paginate(self, items: List[Dict], pg: int, per_page: int = 20) -> Dict:
        total = len(items)
        pagecount = (total + per_page - 1) // per_page if total > 0 else 1
        start = (pg - 1) * per_page
        return {
            "page": pg,
            "pagecount": pagecount,
            "list": items[start:start + per_page],
            "total": total
        }

    # ==================== T4 接口实现 ====================
    def homeContent(self, filter=False):
        self._ensure_tm_loaded()

        class_list = [{"type_id": xd, "type_name": xd} for xd in XD_LIST]

        filters = {}
        if filter:
            for xd in XD_LIST:
                items = self._xd_tm_map.get(xd, [])
                if not items:
                    continue
                grades = set()
                subjects = set()
                publishers = set()
                volumes = set()
                for it in items:
                    if it["nj"]: grades.add(it["nj"])
                    if it["xk"]: subjects.add(it["xk"])
                    if it["bb"]: publishers.add(it["bb"])
                    if it["cc"]: volumes.add(it["cc"])

                grade_list = sorted(grades, key=lambda x: GRADE_ORDER.get(x, 999))
                subject_list = sorted(subjects)
                publisher_list = sorted(publishers)
                volume_list = sorted(volumes)

                filter_def = []
                if grade_list:
                    opts = [{"n": g, "v": g} for g in grade_list]
                    filter_def.append({
                        "key": "grade",
                        "name": "年级",
                        "value": [{"n": "全部", "v": ""}] + opts
                    })
                if subject_list:
                    opts = [{"n": s, "v": s} for s in subject_list]
                    filter_def.append({
                        "key": "subject",
                        "name": "学科",
                        "value": [{"n": "全部", "v": ""}] + opts
                    })
                if publisher_list:
                    opts = [{"n": p, "v": p} for p in publisher_list]
                    filter_def.append({
                        "key": "publisher",
                        "name": "版本",
                        "value": [{"n": "全部", "v": ""}] + opts
                    })
                if volume_list:
                    opts = [{"n": v, "v": v} for v in volume_list]
                    filter_def.append({
                        "key": "volume",
                        "name": "册次",
                        "value": [{"n": "全部", "v": ""}] + opts
                    })
                if filter_def:
                    filters[xd] = filter_def

        result = {"class": class_list}
        if filters:
            result["filters"] = filters
        return result

    def homeVideoContent(self):
        result = []
        for rec in self._recommend_config:
            key = f"{rec['tags']['zxxxd']}·{rec['tags']['zxxnj']}·{rec['tags']['zxxxk']}·{rec['tags']['zxxbb']}·{rec['tags']['zxxcc']}"
            tm_id = self._tm_id_map.get(key)
            # 【新增】从 _xd_tm_map 里找对应 thumb
            thumb = ""
            for item in self._xd_tm_map.get(rec["tags"]["zxxxd"], []):
                if item["key"] == key:
                    thumb = item.get("thumb", "")
                    break
            if tm_id:
                result.append({
                    "vod_id": key,
                    "vod_name": rec["name"],
                    "vod_pic": thumb,
                    "vod_remarks": rec["tags"]["zxxxk"]
                })
        return {"list": result}

    def categoryContent(self, tid, pg=1, filter=False, extend=None):
        tid = urllib.parse.unquote(tid)
        try:
            pg = int(pg)
        except (ValueError, TypeError):
            pg = 1

        if tid not in self._xd_tm_map:
            return {"page": pg, "pagecount": 1, "list": [], "total": 0}

        all_items = self._xd_tm_map[tid]

        selected_grade = []
        selected_subject = []
        selected_publisher = []
        selected_volume = []

        if extend:
            ext_obj = extend
            if isinstance(extend, str) and extend.strip():
                try:
                    ext_obj = json.loads(extend)
                except (json.JSONDecodeError, TypeError):
                    ext_obj = {}
            if isinstance(ext_obj, dict):
                def _split_values(v):
                    if v is None:
                        return []
                    if isinstance(v, list):
                        return [str(x).strip() for x in v if x]
                    if isinstance(v, str):
                        return [x.strip() for x in v.split(',') if x.strip()]
                    return []
                selected_grade = _split_values(ext_obj.get("grade"))
                selected_subject = _split_values(ext_obj.get("subject"))
                selected_publisher = _split_values(ext_obj.get("publisher"))
                selected_volume = _split_values(ext_obj.get("volume"))

        def _filter_items(items, grade_vals, subject_vals, publisher_vals, volume_vals):
            result = []
            for item in items:
                if grade_vals and item["nj"] not in grade_vals:
                    continue
                if subject_vals and item["xk"] not in subject_vals:
                    continue
                if publisher_vals and item["bb"] not in publisher_vals:
                    continue
                if volume_vals and item["cc"] not in volume_vals:
                    continue
                result.append(item)
            return result

        filtered = _filter_items(all_items, selected_grade, selected_subject, selected_publisher, selected_volume)
        filtered_sorted = sorted(filtered, key=lambda x: GRADE_ORDER.get(x["nj"], 999))

        result = []
        for item in filtered_sorted:
            name = f"{item['nj']}·{item['xk']}·{item['bb']}·{item['cc']}"
            vod_id = urllib.parse.quote(item["key"], safe="")
            result.append({
                "vod_id": vod_id,
                "vod_name": name,
                "vod_pic": item.get("thumb", ""),
                "vod_remarks": item["xk"]
            })

        return self._paginate(result, pg, 20)

    def detailContent(self, ids):
        if isinstance(ids, list):
            ids = ids[0] if ids else ""
        if not ids:
            return {"list": []}

        ids = urllib.parse.unquote(ids)

        tm_id = self._tm_id_map.get(ids)
        if not tm_id:
            raw = ids.replace("·", "·")
            tm_id = self._tm_id_map.get(raw)
        if not tm_id:
            parts = re.split(r"[·|]", ids)
            if len(parts) >= 5:
                cand_key = f"{parts[0]}·{parts[1]}·{parts[2]}·{parts[3]}·{parts[4]}"
                tm_id = self._tm_id_map.get(cand_key)
        if not tm_id:
            return {"list": []}

        tree = self._fetch_tm_tree(tm_id)
        if not tree:
            return {"list": []}

        resources = self._fetch_tm_resources(tm_id)
        res_map = {}
        for r in resources:
            ch_ids = r.get("chapter_ids", [])
            if not ch_ids:
                continue
            target_cid = ch_ids[-1]
            if target_cid not in res_map:
                res_map[target_cid] = []
            res_map[target_cid].append(r)

        play_from_list = []
        play_url_list = []

        for unit in tree:
            unit_title = unit.get("title", "")
            if not unit_title:
                continue
            unit_title_safe = unit_title.replace("$", "＄").replace("#", "＃")
            seen_ids = set()
            episodes = []
            def walk(node):
                nid = node.get("id", "")
                if nid in res_map:
                    for r in res_map[nid]:
                        rid = r.get("id", "")
                        if rid in seen_ids:
                            continue
                        seen_ids.add(rid)
                        title = r.get("title") or (r.get("global_title") or {}).get("zh-CN", "") or "视频"
                        title = title.replace("$", "＄").replace("#", "＃")
                        rtype = r.get("resource_type_code", "") or "unknown"
                        episodes.append({"name": title, "activity_id": rid, "rtype": rtype})
                    return
                children = node.get("child_nodes") or node.get("children") or []
                for child in children:
                    walk(child)
            walk(unit)
            if not episodes:
                continue
            name_count = {}
            for ep in episodes:
                name = ep["name"]
                if name in name_count:
                    name_count[name] += 1
                    ep["name"] = f"{name}-{name_count[name]}"
                else:
                    name_count[name] = 0
            play_from_list.append(unit_title_safe)
            ep_strs = []
            for ep in episodes:
                ep_strs.append(f"{ep['name']}${ep['rtype']}|{ep['activity_id']}")
            play_url_list.append("#".join(ep_strs))

        if not play_from_list:
            return {"list": []}

        return {
            "list": [{
                "vod_id": ids,
                "vod_name": ids,
                "vod_pic": "",
                "vod_content": "",
                "vod_play_from": "$$$".join(play_from_list),
                "vod_play_url": "$$$".join(play_url_list),
                "vod_remarks": f"{len(play_from_list)}个单元"
            }]
        }

    def searchContent(self, key, quick=False, pg="1"):
        try:
            pg = int(pg)
        except (ValueError, TypeError):
            pg = 1
        return {"page": pg, "pagecount": 0, "list": [], "total": 0}

    def playerContent(self, flag, id, vipFlags=None):
        if not id:
            return {"parse": 0, "url": ""}

        id = urllib.parse.unquote(id)

        hint_type = ""
        activity_id = id
        if "|" in id and re.match(r'^[a-zA-Z_]+[a-zA-Z0-9_]*\|[0-9a-fA-F-]{36}$', id):
            parts = id.split("|", 1)
            hint_type = parts[0]
            activity_id = parts[1]
        elif not re.match(r'^[0-9a-fA-F-]{36}$', id):
            if "|" in id:
                parts = id.rsplit("|", 1)
                candidate = parts[-1]
                if re.match(r'^[0-9a-fA-F-]{36}$', candidate):
                    hint_type = parts[0] if parts[0] else ""
                    activity_id = candidate

        if re.match(r'^[0-9a-fA-F-]{36}$', activity_id):
            try:
                media_list = self._resolve_activity(activity_id, hint_type=hint_type)
                if media_list:
                    result_urls = []
                    for media in media_list:
                        try:
                            new_m3u8 = self._rewrite_m3u8(media["url"])
                            safe_suffix = re.sub(r'[^\w\u4e00-\u9fff]', '_', media["title"])[:15]
                            tmp_path = self._save_m3u8_local(activity_id, new_m3u8, safe_suffix)
                            if tmp_path:
                                result_urls.append(media["title"])
                                result_urls.append(tmp_path)
                            else:
                                print(f"[PLAYER] 无法写入临时文件，使用原始URL（带token）")
                                result_urls.append(media["title"])
                                result_urls.append(self._with_token(media["url"]))
                        except Exception as e:
                            print(f"[PLAYER] m3u8重写失败 [{media.get('title', '')}]: {e}，回退原始URL")
                            result_urls.append(media.get("title", "视频"))
                            result_urls.append(self._with_token(media["url"]))
                    if result_urls:
                        return {
                            "parse": 0,
                            "url": result_urls,
                            "playUrl": "",
                            "flag": flag,
                            "header": self.headers,
                            "js": "",
                            "extra": {}
                        }
            except Exception as e:
                print(f"[PLAYER] 播放解析失败: {e}")
                return {"parse": 0, "url": ""}

        if id.startswith("http"):
            return {"parse": 0, "url": self._with_token(id), "header": self.headers}
        return {"parse": 1, "url": id, "header": self.headers}

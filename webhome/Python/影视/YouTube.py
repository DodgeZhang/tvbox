#!/usr/bin/python
# -*- coding: utf-8 -*-
import re, json, time, base64, hashlib, urllib.parse
from base.spider import Spider

AES_K = b"3ef437d981515946"
AES_IV = b"824d375733b6245e"
SALT = "03d20341be99573e4c497a02d7eee40a"
IMG_K = b"f5d965df75336270"
IMG_IV = b"97b60394abc2fbe1"
BASE = "https://api1.gkxgquhl.cc/api.php"
BP = {"bundleId":"com.pwa.wyll","version":"2.1.1","language":"zh","via":"pwa","oauth_id":"20d19cb9e6e6c56abe93dba57ef62592","oauth_type":"web","support_webp":1,"new_hash":1}
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
SORT_OPTIONS = [("new","最新"),("hot","热门"),("popular","最热"),("favorite","收藏"),("comment","评论"),("see","在看")]
FALLBACK_GROUPS = [(1,"YouTube精选"),(73,"伦理道德"),(220,"重口猎奇"),(75,"制服萝莉"),(3,"国产精选"),(2,"国产传媒"),(203,"同志骚基"),(185,"海外精选"),(4,"日韩精选"),(5,"禁漫天堂"),(238,"官方原创"),(257,"性感网黄"),(213,"AI短剧")]

_SBOX = [99,124,119,123,242,107,111,197,48,1,103,43,254,215,171,118,202,130,201,125,250,89,71,240,173,212,162,175,156,164,114,192,183,253,147,38,54,63,247,204,52,165,229,241,113,216,49,21,4,199,35,195,24,150,5,154,7,18,128,226,235,39,178,117,9,131,44,26,27,110,90,160,82,59,214,179,41,227,47,132,83,209,0,237,32,252,177,91,106,203,190,57,74,76,88,207,208,239,170,251,67,77,51,133,69,249,2,127,80,60,159,168,81,163,64,143,146,157,56,245,188,182,218,33,16,255,243,210,205,12,19,236,95,151,68,23,196,167,126,61,100,93,25,115,96,129,79,220,34,42,144,136,70,238,184,20,222,94,11,219,224,50,58,10,73,6,36,92,194,211,172,98,145,149,228,121,231,200,55,109,141,213,78,169,108,86,244,234,101,122,174,8,186,120,37,46,28,166,180,198,232,221,116,31,75,189,139,138,112,62,181,102,72,3,246,14,97,53,87,185,134,193,29,158,225,248,152,17,105,217,142,148,155,30,135,233,206,85,40,223,140,161,137,13,191,230,66,104,65,153,45,15,176,84,187,22]
_INV_SBOX = [82,9,106,213,48,54,165,56,191,64,163,158,129,243,215,251,124,227,57,130,155,47,255,135,52,142,67,68,196,222,233,203,84,123,148,50,166,194,35,61,238,76,149,11,66,250,195,78,8,46,161,102,40,217,36,178,118,91,162,73,109,139,209,37,114,248,246,100,134,104,152,22,212,164,92,204,93,101,182,146,108,112,72,80,253,237,185,218,94,21,70,87,167,141,157,132,144,216,171,0,140,188,211,10,247,228,88,5,184,179,69,6,208,44,30,143,202,63,15,2,193,175,189,3,1,19,138,107,58,145,17,65,79,103,220,234,151,242,207,206,240,180,230,115,150,172,116,34,231,173,53,133,226,249,55,232,28,117,223,110,71,241,26,113,29,41,197,137,111,183,98,14,170,24,190,27,252,86,62,75,198,210,121,32,154,219,192,254,120,205,90,244,31,221,168,51,136,7,199,49,177,18,16,89,39,128,236,95,96,81,127,169,25,181,74,13,45,229,122,159,147,201,156,239,160,224,59,77,174,42,245,176,200,235,187,60,131,83,153,97,23,43,4,126,186,119,214,38,225,105,20,99,85,33,12,125]

def _gmul(a, b):
    r = 0
    for _ in range(8):
        if b & 1: r ^= a
        a = ((a << 1) ^ (0x11b if a & 0x80 else 0)) & 255
        b >>= 1
    return r

class _AES128:
    def __init__(self, key):
        w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
        rc = 1
        while len(w) < 44:
            t = w[-1][:]
            if len(w) % 4 == 0:
                t = t[1:] + t[:1]
                t = [_SBOX[x] for x in t]
                t[0] ^= rc
                rc = _gmul(rc, 2)
            w.append([w[-4][i] ^ t[i] for i in range(4)])
        self.rk = [sum(w[i:i + 4], []) for i in range(0, 44, 4)]
    def _key(self, s, r):
        k = self.rk[r]
        for i in range(16): s[i] ^= k[i]
    def _sub(self, s):
        for i in range(16): s[i] = _SBOX[s[i]]
    def _isub(self, s):
        for i in range(16): s[i] = _INV_SBOX[s[i]]
    def _shift(self, s):
        o = [0] * 16
        for r in range(4):
            for c in range(4): o[4 * c + r] = s[4 * ((c + r) % 4) + r]
        s[:] = o
    def _ishift(self, s):
        o = [0] * 16
        for r in range(4):
            for c in range(4): o[4 * c + r] = s[4 * ((c - r) % 4) + r]
        s[:] = o
    def _mix(self, s):
        for c in range(4):
            i = 4 * c; a0,a1,a2,a3 = s[i:i + 4]
            s[i:i + 4] = [_gmul(a0,2)^_gmul(a1,3)^a2^a3, a0^_gmul(a1,2)^_gmul(a2,3)^a3, a0^a1^_gmul(a2,2)^_gmul(a3,3), _gmul(a0,3)^a1^a2^_gmul(a3,2)]
    def _imix(self, s):
        for c in range(4):
            i = 4 * c; a0,a1,a2,a3 = s[i:i + 4]
            s[i:i + 4] = [_gmul(a0,14)^_gmul(a1,11)^_gmul(a2,13)^_gmul(a3,9), _gmul(a0,9)^_gmul(a1,14)^_gmul(a2,11)^_gmul(a3,13), _gmul(a0,13)^_gmul(a1,9)^_gmul(a2,14)^_gmul(a3,11), _gmul(a0,11)^_gmul(a1,13)^_gmul(a2,9)^_gmul(a3,14)]
    def enc(self, block):
        s = list(block); self._key(s, 0)
        for r in range(1, 10): self._sub(s); self._shift(s); self._mix(s); self._key(s, r)
        self._sub(s); self._shift(s); self._key(s, 10)
        return bytes(s)
    def dec(self, block):
        s = list(block); self._key(s, 10)
        for r in range(9, 0, -1): self._ishift(s); self._isub(s); self._key(s, r); self._imix(s)
        self._ishift(s); self._isub(s); self._key(s, 0)
        return bytes(s)

def _aes(mode, data, key=AES_K, iv=AES_IV):
    try:
        from Crypto.Cipher import AES as _A
        from Crypto.Util.Padding import pad, unpad
        return _A.new(key, _A.MODE_CBC, iv).encrypt(pad(data, 16)) if mode else unpad(_A.new(key, _A.MODE_CBC, iv).decrypt(data), 16)
    except:
        a = _AES128(key)
        if mode:
            n = 16 - len(data) % 16; data += bytes([n]) * n; out = []; prev = iv
            for i in range(0, len(data), 16):
                block = bytes(x ^ y for x, y in zip(data[i:i + 16], prev)); prev = a.enc(block); out.append(prev)
            return b"".join(out)
        if len(data) % 16: raise ValueError("bad aes length")
        out = []; prev = iv
        for i in range(0, len(data), 16):
            block = data[i:i + 16]; out.append(bytes(x ^ y for x, y in zip(a.dec(block), prev))); prev = block
        out = b"".join(out); n = out[-1]
        if not 1 <= n <= 16 or out[-n:] != bytes([n]) * n: raise ValueError("bad aes padding")
        return out[:-n]

class Spider(Spider):
    def getName(self): return "YouTube成人版"
    def getDependence(self): return []
    def destroy(self): pass
    def homeLayout(self): return {"class": [], "filters": {}}
    def getHomeContent(self): return self.homeContent(False)
    def localProxy(self, param):
        try:
            u = ""
            if isinstance(param, dict): u = param.get("u") or param.get("url") or ""
            else:
                m = re.search(r'(?:^|[&?])u=([^&]*)', str(param or ""))
                if m: u = urllib.parse.unquote(m.group(1))
            u = urllib.parse.unquote(str(u or ""))
            if not u.startswith("http"): return [404, "text/plain", b""]
            cache = getattr(self, "_img", None)
            if cache is None: cache = self._img = {}
            if u in cache:
                d = cache[u]; return [200, self._ct(d), d]
            r = self.fetch(u, None, None, {"User-Agent": UA, "Referer": "https://w1.rohuzsqwk.com/"}, 15)
            raw = r.content if hasattr(r, "content") else (r if isinstance(r, (bytes, bytearray)) else b"")
            if not raw or len(raw) < 16: return [404, "text/plain", b""]
            if raw[:4] in (b"\x89PNG", b"RIFF") or raw[:2] == b"\xff\xd8" or raw[:3] == b"GIF":
                dec = raw
            else:
                dec = _aes(0, bytes(raw), IMG_K, IMG_IV) if len(raw) % 16 == 0 else raw
            if dec[:4] in (b"\x89PNG", b"RIFF") or dec[:2] == b"\xff\xd8" or dec[:3] == b"GIF":
                if len(cache) > 150: cache.clear()
                cache[u] = dec
                return [200, self._ct(dec), dec]
            return [200, "image/webp", raw]
        except: return [404, "text/plain", b""]
    def _ct(self, d):
        if d[:4] == b"\x89PNG": return "image/png"
        if d[:2] == b"\xff\xd8": return "image/jpeg"
        if d[:3] == b"GIF": return "image/gif"
        return "image/webp"
    def init(self, extend=""):
        self.api = BASE
        self._cache = {}
        self._img = {}
        self._groups = [{"type_id": str(i), "type_name": n} for i, n in FALLBACK_GROUPS]
        self.h = {"User-Agent": UA, "Referer": "https://w1.rohuzsqwk.com/", "Origin": "https://w1.rohuzsqwk.com", "Content-Type": "application/x-www-form-urlencoded"}
    def getProxyUrl(self):
        try: return self.getProxy(True) if hasattr(self, "getProxy") else "http://127.0.0.1:9978/proxy?do=py"
        except: return "http://127.0.0.1:9978/proxy?do=py"
    def _read_json(self, r):
        if isinstance(r, dict): return r
        if isinstance(r, (bytes, bytearray)): return json.loads(r.decode("utf-8", "replace"))
        if isinstance(r, str): return json.loads(r)
        try: return r.json()
        except: pass
        t = getattr(r, "text", None)
        if isinstance(t, bytes): t = t.decode("utf-8", "replace")
        if t: return json.loads(t)
        c = getattr(r, "content", None)
        if isinstance(c, bytes): return json.loads(c.decode("utf-8", "replace"))
        raise ValueError("empty response")
    def _decode(self, j):
        if not isinstance(j, dict) or not isinstance(j.get("data"), str): return {}
        d = json.loads(_aes(0, base64.b64decode(j["data"])).decode("utf-8", "replace"))
        if d.get("status") != 1: return {}
        dd = d.get("data")
        return dd.get("data") if isinstance(dd, dict) and "data" in dd else dd
    def _call(self, path, params=None):
        p = dict(BP); p.update(params or {})
        ct = base64.b64encode(_aes(1, json.dumps(p, separators=(",", ":")).encode())).decode()
        ts = str(int(time.time()))
        raw = "_ver=v2&client=pwa&data=%s&timestamp=%s" % (ct, ts)
        sign = hashlib.md5(hashlib.sha256((raw + SALT).encode()).hexdigest().encode()).hexdigest()
        body = "client=pwa&timestamp=%s&data=%s&sign=%s&_ver=v2" % (ts, ct, sign)
        url = self.api + path
        try:
            out = self._decode(self._read_json(self.fetch(url, body, None, self.h, 15)))
            if out: return out
        except Exception as e:
            self._last_error = str(e)
        try:
            import requests
            r = requests.post(url, data=body, headers=self.h, timeout=15)
            out = self._decode(self._read_json(r))
            if out: return out
        except Exception as e:
            self._last_error = str(e)
        return {}
    def _sync_groups(self):
        try:
            d = self._call("/api/element/getElementById", {"id": 1})
            vals = d.get("value") if isinstance(d, dict) else None
            g = []
            for v in (vals or []):
                cid = (v.get("params") or {}).get("id")
                name = v.get("name")
                if cid is not None and name: g.append({"type_id": str(cid), "type_name": name})
            if g: self._groups = g
        except: pass
        return self._groups
    def _play_url(self, v):
        p = v.get("preview_sources") or {}
        return p.get("url_264") or p.get("url_265") or ""
    def _iwanna(self, v):
        m = v.get("hevc_meta")
        if isinstance(m, str):
            try: m = json.loads(m)
            except: return ""
        if not isinstance(m, dict): return ""
        sr = m.get("submit_result")
        if isinstance(sr, str):
            try: sr = json.loads(sr)
            except: return ""
        if not isinstance(sr, dict): return ""
        d = sr.get("data")
        if isinstance(d, str):
            try: d = json.loads(d)
            except: return ""
        return (d.get("file_url") or "") if isinstance(d, dict) else ""
    def _full(self, v):
        ps = self._play_url(v)
        if ps and "yd-10play.bnfuiu.cn" in ps:
            return ps.replace("yd-10play.bnfuiu.cn", "video.iwanna.tv").split("?")[0]
        return self._iwanna(v) or (v.get("source_240_hevc") or "")
    def _pic(self, s):
        try:
            u = ""
            if isinstance(s, str) and s.startswith("{"):
                o = json.loads(s); u = o.get("360") or o.get("ori") or o.get("720") or ""
            else: u = s or ""
            if not u: return ""
            return self.getProxyUrl() + "&ac=img&u=" + urllib.parse.quote(u, safe="")
        except: return ""
    def _item(self, v):
        try: dur = "%d:%02d" % (int(v.get("duration", 0)) // 60, int(v.get("duration", 0)) % 60)
        except: dur = ""
        tip = "[金币%s]" % v.get("coins") if v.get("isfree") == 2 else ""
        try: self._cache[str(v.get("id"))] = v
        except: pass
        try:
            if self._full(v): dur = (dur + " 全片").strip()
        except: pass
        return {"vod_id": str(v.get("id", "")), "vod_name": (tip + (v.get("title") or ""))[:60], "vod_pic": self._pic(v.get("cover_vertical") or v.get("cover_horizontal")), "vod_remarks": dur}
    def homeContent(self, filter):
        classes = self._sync_groups()
        d = self._call("/api/index/index", {"id": 1, "page": 1, "limit": 15})
        lst = []
        for g in (d.get("list") or []) if isinstance(d, dict) else []:
            for v in (g.get("items") or [])[:12]:
                if self._play_url(v): lst.append(self._item(v))
        opts = [{"n": n, "v": s} for s, n in SORT_OPTIONS]
        filters = {c["type_id"]: [{"key": "sort", "name": "排序", "value": opts}] for c in classes}
        return {"class": classes, "list": lst, "filters": filters}
    def homeVideoContent(self):
        d = self._call("/api/index/index", {"id": 1, "page": 1, "limit": 15})
        arr = []
        for g in (d.get("list") or []) if isinstance(d, dict) else []:
            arr.extend(g.get("items") or [])
        return {"list": [self._item(v) for v in arr[:12] if self._play_url(v)]}
    def categoryContent(self, tid, pg, filter, extend):
        sort = extend.get("sort") if isinstance(extend, dict) and extend.get("sort") else "new"
        d = self._call("/api/mv/list_construct", {"id": int(tid), "page": int(pg), "limit": 24, "sort": sort})
        arr = d.get("list") if isinstance(d, dict) else d
        arr = arr if isinstance(arr, list) else []
        return {"page": int(pg), "pagecount": 9999, "limit": 24, "total": 9999, "list": [self._item(v) for v in arr if self._play_url(v)]}
    def detailContent(self, ids):
        v = (getattr(self, "_cache", {}) or {}).get(str(ids[0]), {})
        if not v:
            d = self._call("/api/mv/search", {"word": str(ids[0]), "page": 1, "limit": 20})
            for it in (d if isinstance(d, list) else []):
                if str(it.get("id")) == str(ids[0]): v = it; break
        if not v:
            d2 = self._call("/api/index/index", {"id": 1, "page": 1, "limit": 15})
            for g in (d2.get("list") or []):
                for it in (g.get("items") or []):
                    if str(it.get("id")) == str(ids[0]): v = it; break
        if not v: v = {"id": ids[0], "title": "视频" + str(ids[0])}
        urls = []
        ps = self._play_url(v)
        full = self._full(v)
        vs = (v.get("video_sources") or {}).get("url_264") or ""
        if vs: urls.append("正片$" + vs)
        if full: urls.append("全片$" + full)
        if ps: urls.append(("预览$" if (vs or full) else "正片$") + ps)
        play = "#".join(urls) if urls else "付费内容$no_play"
        tags = v.get("tags") or ""
        return {"list": [{"vod_id": str(v.get("id")), "vod_name": v.get("title") or "", "vod_pic": self._pic(v.get("cover_vertical")), "type_name": v.get("video_type_name") or "", "vod_content": "时长:%s 播放:%s %s" % (v.get("duration") or "", v.get("play_ct") or v.get("count_play") or "", tags), "vod_tag": "list" if urls else "book", "vod_play_from": "wyll", "vod_play_url": play, "vod_actor": "", "vod_director": "", "vod_year": (v.get("created_at") or "")[:10], "vod_area": "", "vod_class": tags.split(",") if tags else []}]}
    def searchContent(self, key, quick, pg="1"):
        d = self._call("/api/mv/search", {"word": key, "page": int(pg), "limit": 20})
        return {"list": [self._item(v) for v in (d if isinstance(d, list) else []) if self._play_url(v)], "page": int(pg)}
    def playerContent(self, flag, id, vipFlags):
        if id == "no_play": return {"parse": 0, "url": "", "jx": 0}
        return {"parse": 0, "url": id, "header": json.dumps({"User-Agent": UA})}
    def isVideoFormat(self, url): return ".m3u8" in url or ".mp4" in url
    def manualVideoCheck(self): return False

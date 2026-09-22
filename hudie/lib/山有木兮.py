#!/usr/bin/env python3
# QQ群:807916734 @ID丶
# -*- coding: utf-8 -*-
# ============================================================
# TVBox Python 爬虫 · 山有木兮影视 (film.symx.club)
# 版本: 2.1.3 (熔断器移除+多策略generate版)
# 兼容: TVBox / 影视仓 / FongMi / WebHomeTV(默影视) / PeekPro
# 优化: 播放解析重构 / 滑块轨迹增强 / 探测逻辑加固 / 解码器修正 / 缓存分离
# 协议: /api/* + X-Platform/X-Timestamp/HMAC签名头 + XOR解密system/config
#       内容接口免登录; 1004 → /api/auth/verify 滑块自愈
# 零第三方依赖: 滑块识别内置纯 Python JPEG 解码 (PIL 可用时优先)
# 零 f-string (老内核 Python 兼容)
# ============================================================
import sys
sys.path.append('..')
try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

import json
import os
import time
import random
import hmac
import hashlib
import struct
import zlib
import base64
import io
import re
import urllib.request
import urllib.parse
import ssl

try:
    _SSL_CTX = ssl.create_default_context()
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE
except Exception:
    _SSL_CTX = None

HOST = "https://film.symx.club"
API = HOST + "/api"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
API_UA = "SYMX_WINDOWS"
APP_VERSION = "1.1.1"

# v4.5: APP 同款 UUID 格式 (getUUID(): 标准带连字符 36 位)
def _cid():
    def _h(n):
        return ''.join(random.choice('0123456789abcdef') for _ in range(n))
    return _h(8) + "-" + _h(4) + "-4" + _h(3) + "-8" + _h(3) + "-" + _h(12)

# ---------- v4.4 磁盘持久化 (重启后保持同一"设备") ----------
_PERSIST_NAME = "symx_dev.json"

def _persist_paths():
    import tempfile
    ps = []
    try:
        ps.append(tempfile.gettempdir())
    except Exception:
        pass
    ps.append(os.getcwd())
    for p in ("/storage/emulated/0/Download", "/sdcard/Download", "/data/local/tmp"):
        ps.append(p)
    return ps

def _persist_load():
    for d in _persist_paths():
        if not d:
            continue
        try:
            f = os.path.join(d, _PERSIST_NAME)
            if os.path.exists(f):
                with open(f, "r") as fh:
                    return json.load(fh), d
        except Exception:
            continue
    return None, None

def _persist_save(obj, preferred_dir=None):
    dirs = [preferred_dir] if preferred_dir else []
    dirs += _persist_paths()
    for d in dirs:
        if not d:
            continue
        try:
            f = os.path.join(d, _PERSIST_NAME)
            with open(f, "w") as fh:
                json.dump(obj, fh)
            return d
        except Exception:
            continue
    return None

# ============================================================
# 纯 Python JPEG (baseline) 解码器 — 滑块识别用, 仅解码亮度 / RGB 窗口
# ============================================================
class _JpegGray(object):
    """极简 baseline JPEG 解码, 支持灰度全图与 RGB 窗口"""

    def __init__(self, data):
        self.d = data
        self.pos = 0
        self.qt = [[16] * 64 for _ in range(4)]
        self.huff_dc = {}
        self.huff_ac = {}
        self.w = 0
        self.h = 0
        self.comp = []  # (h,v,tq,dc_id,ac_id)
        self.mcux = 1
        self.mcuy = 1
        self.hmax = 1
        self.vmax = 1

    def u16(self):
        v = (self.d[self.pos] << 8) | self.d[self.pos + 1]
        self.pos += 2
        return v

    def decode(self):
        """灰度全图解码 (仅 Y 分量)"""
        d = self.d
        if d[0] != 0xFF or d[1] != 0xD8:
            raise ValueError("not jpeg")
        self.pos = 2
        while self.pos < len(d):
            if d[self.pos] != 0xFF:
                self.pos += 1
                continue
            m = d[self.pos + 1]
            self.pos += 2
            if m in (0xD8, 0xD9, 0x01) or 0xD0 <= m <= 0xD7:
                continue
            ln = self.u16() - 2
            if m == 0xDA:
                return self._parse_sos()
            seg = d[self.pos:self.pos + ln]
            self.pos += ln
            if m == 0xDB:
                self._parse_dqt(seg)
            elif m in (0xC0, 0xC1):
                self._parse_sof(seg)
            elif m == 0xC4:
                self._parse_dht(seg)
        raise ValueError("no SOS")

    def decode_rgb_rows(self, ys=0, ye=None):
        """v4.3 窗口 RGB 解码: 哈夫曼全量但 IDCT+存储仅窗口行"""
        d = self.d
        if d[0] != 0xFF or d[1] != 0xD8:
            raise ValueError("not jpeg")
        self.pos = 2
        while self.pos < len(d):
            if d[self.pos] != 0xFF:
                self.pos += 1
                continue
            m = d[self.pos + 1]
            self.pos += 2
            if m in (0xD8, 0xD9, 0x01) or 0xD0 <= m <= 0xD7:
                continue
            ln = self.u16() - 2
            if m == 0xDA:
                if ye is None:
                    ye = self.h
                return self._parse_sos_rgb(ys, ye)
            seg = d[self.pos:self.pos + ln]
            self.pos += ln
            if m == 0xDB:
                self._parse_dqt(seg)
            elif m in (0xC0, 0xC1):
                self._parse_sof(seg)
            elif m == 0xC4:
                self._parse_dht(seg)
        raise ValueError("no SOS")

    def _parse_sos_rgb(self, ys=0, ye=None):
        if ye is None:
            ye = self.h
        d = self.d
        ns = d[self.pos + 0]
        self.pos += 1
        comps = []
        for i in range(ns):
            cid = d[self.pos]
            tabs = d[self.pos + 1]
            comps.append((cid, tabs >> 4, tabs & 15))
            self.pos += 2
        self.pos += 3
        self.scan = d[self.pos:]
        self.bytepos = -1
        self.bitpos = 8
        self.cur = 0
        planes = []
        for c in self.comp:
            h, v = c[0], c[1]
            pw = self.mcux * h * 8
            ph = self.mcuy * v * 8
            planes.append([[0] * pw for _ in range(ph)])
        pred = [0] * len(self.comp)
        comp_map = {}
        for idx, c in enumerate(self.comp):
            comp_map[c[3]] = (idx, c)
        sy_c = [self.vmax // c[1] if self.vmax >= c[1] else 1 for c in self.comp]
        for mcu in range(self.mcux * self.mcuy):
            mcu_row = mcu // self.mcux
            for (cid, dc_t, ac_t) in comps:
                idx, c = comp_map[cid]
                h, v, tq = c[0], c[1], c[2]
                for by in range(v):
                    for bx in range(h):
                        blk = [0] * 64
                        t = self._decode_huff(self.huff_dc[dc_t])
                        diff = self._extend(self._get_bits(t), t) if t else 0
                        pred[idx] += diff
                        blk[0] = pred[idx] * self.qt[tq][0]
                        k = 1
                        while k < 64:
                            rs = self._decode_huff(self.huff_ac[ac_t])
                            r = rs >> 4
                            s = rs & 15
                            if s == 0:
                                if r == 15:
                                    k += 16
                                    continue
                                break
                            k += r + 1
                            if k > 64:
                                break
                            val = self._extend(self._get_bits(s), s)
                            blk[ZIGZAG[k - 1]] = val * self.qt[tq][ZIGZAG[k - 1]]
                        # 窗口门控: 窗口外的块只解系数跳过 IDCT
                        r0 = ((mcu_row * v) + by) * 8
                        syv = sy_c[idx]
                        if (r0 + 8) * syv <= ys or r0 * syv >= ye:
                            continue
                        pix = self._idct(blk)
                        plane = planes[idx]
                        bcol = (mcu % self.mcux) * h + bx
                        x0 = bcol * 8
                        ph_ = len(plane)
                        pw_ = len(plane[0]) if ph_ else 0
                        for yy in range(8):
                            py = r0 + yy
                            if py >= ph_:
                                continue
                            row = plane[py]
                            for xx in range(8):
                                px = x0 + xx
                                if px >= pw_:
                                    continue
                                row[px] = pix[yy * 8 + xx] + 128
        # 物化: 仅 [ys, min(ye,h)) 行
        W = self.w
        y_end = min(ye, self.h)
        rPo = []
        gPo = []
        bPo = []
        if len(self.comp) >= 3:
            syY = sy_c[0]; syCb = sy_c[1]; syCr = sy_c[2]
            sxY = self.hmax // self.comp[0][0] if self.hmax >= self.comp[0][0] else 1
            sxCb = self.hmax // self.comp[1][0] if self.hmax >= self.comp[1][0] else 1
            sxCr = self.hmax // self.comp[2][0] if self.hmax >= self.comp[2][0] else 1
            pY = planes[0]; pCb = planes[1]; pCr = planes[2]
            for y in range(max(0, ys), y_end):
                yr = pY[y // syY]
                if sxY != 1:
                    yr = [yr[x // sxY] for x in range(W)]
                if sxCb == 1 and sxCr == 1:
                    cbr = pCb[y // syCb]
                    crr = pCr[y // syCr]
                else:
                    cb_raw = pCb[y // syCb]
                    cr_raw = pCr[y // syCr]
                    cbr = [cb_raw[x // sxCb] for x in range(W)]
                    crr = [cr_raw[x // sxCr] for x in range(W)]
                rr = [0] * W
                gg = [0] * W
                bb = [0] * W
                for x in range(W):
                    Y = yr[x]
                    cbb = cbr[x] - 128.0
                    crr_ = crr[x] - 128.0
                    R = Y + 1.402 * crr_
                    G = Y - 0.344136 * cbb - 0.714136 * crr_
                    B = Y + 1.772 * cbb
                    rr[x] = 255 if R > 254.5 else (0 if R < 0 else int(R + 0.5))
                    gg[x] = 255 if G > 254.5 else (0 if G < 0 else int(G + 0.5))
                    bb[x] = 255 if B > 254.5 else (0 if B < 0 else int(B + 0.5))
                rPo.append(rr)
                gPo.append(gg)
                bPo.append(bb)
        else:
            syY = sy_c[0]
            pY = planes[0]
            for y in range(max(0, ys), y_end):
                yr = pY[y // syY]
                rPo.append(yr[:W])
                gPo.append(yr[:W])
                bPo.append(yr[:W])
        return rPo, gPo, bPo

    def _parse_dqt(self, seg):
        i = 0
        while i < len(seg):
            pq = seg[i] >> 4
            tq = seg[i] & 15
            i += 1
            tbl = [0] * 64
            for j in range(64):
                tbl[ZIGZAG[j]] = seg[i + j] if pq == 0 else ((seg[i + 2 * j] << 8) | seg[i + 2 * j + 1])
            self.qt[tq] = tbl
            i += 64 if pq == 0 else 128

    def _parse_sof(self, seg):
        self.prec = seg[0]
        self.h = (seg[1] << 8) | seg[2]
        self.w = (seg[3] << 8) | seg[4]
        nc = seg[5]
        self.comp = []
        for i in range(nc):
            cid = seg[6 + 3 * i]
            hv = seg[7 + 3 * i]
            tq = seg[8 + 3 * i]
            self.comp.append((hv >> 4, hv & 15, tq, cid))
        hmax = max(c[0] for c in self.comp)
        vmax = max(c[1] for c in self.comp)
        self.hmax = hmax
        self.vmax = vmax
        self.mcux = (self.w + 8 * hmax - 1) // (8 * hmax)
        self.mcuy = (self.h + 8 * vmax - 1) // (8 * vmax)

    def _parse_dht(self, seg):
        i = 0
        while i < len(seg):
            tc = seg[i] >> 4
            th = seg[i] & 15
            i += 1
            counts = seg[i:i + 16]
            i += 16
            vals = []
            for c in counts:
                vals.extend(seg[i:i + c] if isinstance(seg, bytes) else [seg[i + k] for k in range(c)])
                i += c
            self._build_huff(tc, th, list(counts), vals)

    def _build_huff(self, tc, th, counts, vals):
        code = 0
        k = 0
        table = {}
        for l in range(16):
            for _ in range(counts[l]):
                table[(l + 1, code)] = vals[k]
                k += 1
                code += 1
            code <<= 1
        if tc == 0:
            self.huff_dc[th] = table
        else:
            self.huff_ac[th] = table
        self.huff_rev = getattr(self, 'huff_rev', {})
        self.huff_rev[(tc, th)] = {}
        code = 0
        k = 0
        for l in range(16):
            for _ in range(counts[l]):
                if k < len(vals):
                    self.huff_rev[(tc, th)][(l + 1, code)] = vals[k]
                k += 1
                code += 1
            code <<= 1

    def _get_bits(self, n):
        v = 0
        for _ in range(n):
            if self.bitpos >= 8:
                self.bitpos = 0
                self.bytepos += 1
                if self.bytepos >= len(self.scan):
                    raise ValueError("bits eof")
                # JPEG 字节填充: 数据 FF 在流中写作 FF 00
                if (self.scan[self.bytepos] == 0x00 and self.bytepos > 0
                        and self.scan[self.bytepos - 1] == 0xFF):
                    self.bytepos += 1
                    if self.bytepos >= len(self.scan):
                        raise ValueError("bits eof")
                self.cur = self.scan[self.bytepos]
            v = (v << 1) | ((self.cur >> (7 - self.bitpos)) & 1)
            self.bitpos += 1
        return v

    def _decode_huff(self, table):
        code = 0
        for l in range(1, 17):
            code = (code << 1) | self._get_bits(1)
            if (l, code) in table:
                return table[(l, code)]
        raise ValueError("huff miss")

    def _extend(self, v, n):
        if n == 0:
            return 0
        return v if v >= (1 << (n - 1)) else v - (1 << n) + 1

    def _idct(self, blk):
        # 可分离 IDCT: 行/列两趟, ~4x 提速
        CT = COS_T
        c0 = 0.7071067811865476  # 1/sqrt(2) 更高精度
        tmp = [0.0] * 64
        out = [0.0] * 64
        for v in range(8):
            vb = v * 8
            b0 = blk[vb]; b1 = blk[vb + 1]; b2 = blk[vb + 2]; b3 = blk[vb + 3]
            b4 = blk[vb + 4]; b5 = blk[vb + 5]; b6 = blk[vb + 6]; b7 = blk[vb + 7]
            for x in range(8):
                k = 2 * x + 1
                tmp[vb + x] = (b0 * c0 + b1 * CT[k]
                               + b2 * CT[2 * k] + b3 * CT[3 * k]
                               + b4 * CT[4 * k] + b5 * CT[5 * k]
                               + b6 * CT[6 * k] + b7 * CT[7 * k])
        for y in range(8):
            ky = 2 * y + 1
            for x in range(8):
                s = (tmp[x] * c0 + tmp[8 + x] * CT[ky]
                     + tmp[16 + x] * CT[2 * ky] + tmp[24 + x] * CT[3 * ky]
                     + tmp[32 + x] * CT[4 * ky] + tmp[40 + x] * CT[5 * ky]
                     + tmp[48 + x] * CT[6 * ky] + tmp[56 + x] * CT[7 * ky])
                out[y * 8 + x] = s * 0.25
        return out

    def _parse_sos(self):
        """灰度解码 (仅 Y 分量写入)"""
        ns = self.d[self.pos + 0]
        self.pos += 1
        comps = []
        for i in range(ns):
            cid = self.d[self.pos]
            tabs = self.d[self.pos + 1]
            comps.append((cid, tabs >> 4, tabs & 15))
            self.pos += 2
        self.pos += 3  # Ss, Se, AhAl
        self.scan = self.d[self.pos:]
        self.bytepos = -1
        self.bitpos = 8
        self.cur = 0
        gray = [[128] * self.w for _ in range(self.h)]
        pred = [0] * ns
        comp_map = {}
        for idx, c in enumerate(self.comp):
            comp_map[c[3]] = (idx, c)
        for mcu in range(self.mcux * self.mcuy):
            mcu_x = mcu % self.mcux
            mcu_y = mcu // self.mcux
            for (cid, dc_t, ac_t) in comps:
                idx, c = comp_map[cid]
                h, v, tq = c[0], c[1], c[2]
                for by in range(v):
                    for bx in range(h):
                        blk = [0] * 64
                        t = self._decode_huff(self.huff_dc[dc_t])
                        diff = self._extend(self._get_bits(t), t) if t else 0
                        pred[idx] += diff
                        blk[0] = pred[idx] * self.qt[tq][0]
                        k = 1
                        while k < 64:
                            rs = self._decode_huff(self.huff_ac[ac_t])
                            r = rs >> 4
                            s = rs & 15
                            if s == 0:
                                if r == 15:
                                    k += 16
                                    continue
                                break
                            k += r + 1
                            if k > 64:
                                break
                            val = self._extend(self._get_bits(s), s)
                            blk[ZIGZAG[k - 1]] = val * self.qt[tq][ZIGZAG[k - 1]]
                        # 仅写入 Y (第一个) 分量; 色度块只解码保持流同步
                        if idx != 0:
                            continue
                        pix = self._idct(blk)
                        # 修正: 使用分量实际采样因子而非全局最大值
                        x0 = (mcu_x * h + bx) * 8
                        y0 = (mcu_y * v + by) * 8
                        for yy in range(8):
                            py = y0 + yy
                            if py >= self.h:
                                continue
                            row = gray[py]
                            for xx in range(8):
                                px = x0 + xx
                                if px >= self.w:
                                    continue
                                v_ = pix[yy * 8 + xx] + 128
                                if v_ < 0:
                                    v_ = 0
                                elif v_ > 255:
                                    v_ = 255
                                row[px] = int(v_)
        self.gray = gray
        return gray


ZIGZAG = [
    0, 1, 8, 16, 9, 2, 3, 10,
    17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34,
    27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36,
    29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46,
    53, 60, 61, 54, 47, 55, 62, 63
]

# 优化: 直接计算所有需要的余弦值, 移除冗余循环
import math as _math
COS_T = {}
for _u in range(8):
    for _x in range(8):
        key = (2 * _x + 1) * _u
        if key not in COS_T:
            COS_T[key] = _math.cos(key * _math.pi / 16.0)

def math_sqrt(v):
    return _math.sqrt(v)

# ============================================================
# Spider
# ============================================================

# ============================================================
# Spider
# ============================================================

# ============================================================
# Spider
# ============================================================
class Spider(_BaseSpider):
    NAME = "山有木兮"
    session = ""
    trace_ids = []
    report_header = "X-Report-Id"
    cid = ""
    vtoken = ""
    cfg = None
    host = HOST
    api = HOST + "/api"
    # v2.3-fix: 移除熔断器
    # _circuit_ts = 0.0
    _last_api_ts = 0.0
    _detail_fail_body = None
    _detail_fail_until = 0.0
    _diag_v = ""
    _pdir = None
    _verify_tries = 0

    def init(self, extend=""):
        if isinstance(extend, dict):
            ext = extend
        else:
            ext = {}
            try:
                if extend and isinstance(extend, str) and extend.strip().startswith("{"):
                    ext = json.loads(extend)
                elif extend and isinstance(extend, str) and extend.strip().startswith("http"):
                    ext = {"url": extend.strip()}
            except Exception:
                ext = {}
        self.ext = ext
        self.host = ext.get("host") or HOST
        self.api = self.host + "/api"
        self._pdir = None
        saved, self._pdir = _persist_load()
        now_ms = int(time.time() * 1000)
        if saved and isinstance(saved.get("cid"), str) and len(saved.get("cid")) in (32, 36):
            self.cid = saved["cid"]
        else:
            self.cid = _cid()
            self._pdir = _persist_save({"cid": self.cid, "vtoken": "", "ts": now_ms}, self._pdir)
        try:
            vt = saved.get("vtoken") or ""
            vts = int(saved.get("ts") or 0)
            self.vtoken = vt if (vt and now_ms - vts < 7200000) else ""
        except Exception:
            self.vtoken = ""
        self._diag_v = ""
        self.session = ""
        self.trace_ids = []
        self.report_header = "X-Report-Id"
        self.cat_cache = None
        self._filter_cache = {}
        self._search_cache = {}
        self._play_cache = {}
        self._type_cache = {}
        self._diag = True
        # v2.3-fix: 移除熔断器
        # self._circuit_ts = 0.0
        self._last_api_ts = 0.0
        self._detail_fail_until = 0.0
        self._detail_fail_body = None

    # ---------- HTTP ----------
    def fetch(self, url, headers=None, post=None, timeout=15):
        try:
            hdrs = dict(headers or {})
            if post is not None:
                body = json.dumps(post).encode("utf-8")
                hdrs.setdefault("Content-Type", "application/json;charset=UTF-8")
                req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
            else:
                req = urllib.request.Request(url, headers=hdrs)
            ctx = _SSL_CTX if (_SSL_CTX and url.startswith("https")) else None
            resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
            self._last_http_status = getattr(resp, 'code', 200)
            return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            try:
                return e.read().decode("utf-8", "replace")
            except Exception:
                return ""
        except Exception:
            return ""

    def _jget(self, url, headers=None, post=None, timeout=15):
        body = self.fetch(url, headers=headers, post=post, timeout=timeout)
        if not body:
            return None
        try:
            return json.loads(body)
        except Exception:
            return None

    # ---------- 签名 ----------
    def timestamp(self):
        r = str(int(time.time() * 1000))
        s = sum(int(c) for c in r[:-1])
        return r[:-1] + str(s % 10)

    def _xor(self, s):
        key = "0x1A2B3C4D5E6F7A8B9C"
        out = []
        try:
            for i in range(0, len(s) - 1, 2):
                b = int(s[i:i + 2], 16)
                k = ord(key[(i // 2) % len(key)])
                out.append(chr(b ^ k))
        except Exception:
            return s
        return ''.join(out)

    def sign(self, path, ts):
        p = path.split("?")[0]
        d = {"p": p, "t": ts, "s": "symx_" + self.session}
        u = ""
        for c in (self.trace_ids or []):
            u += d.get(c, "")
        u = u.replace("1", "i").replace("0", "o").replace("5", "s")
        return hmac.new(self.session.encode("utf-8"), u.encode("utf-8"), hashlib.sha256).hexdigest()

    def _headers(self, path, extra=None):
        ts = self.timestamp()
        h = {
            "User-Agent": API_UA,
            "X-Platform": "windows",
            "X-Version": APP_VERSION,
            "X-Timestamp": ts,
            self.report_header: self.sign(path, ts),
            "X-Client-Id": self.cid,
            "X-Verify-Token": self.vtoken or "",
        }
        if extra:
            h.update(extra)
        return h

    def _ensure_session(self):
        if self.session:
            return True
        d = self._jget(self.api + "/system/config", headers=self._headers("/system/config"))
        try:
            if d and d.get("code") == 200:
                sec = d.get("data")
                if isinstance(sec, str):
                    try:
                        sec = json.loads(sec)
                    except Exception:
                        sec = {}
                if not isinstance(sec, dict):
                    return False
                self.session = self._xor(str(sec.get("session") or "")) if sec.get("session") else ""
                tr = self._xor(str(sec.get("traceId") or "")) if sec.get("traceId") else ""
                if not tr:
                    tr = ""
                self.trace_ids = list(tr)
                rid = self._xor(str(sec.get("reportId") or "")) if sec.get("reportId") else ""
                self.report_header = rid or "X-Report-Id"
                if len(self.session) < 4:
                    self.session = ""
                    return False
                return True
        except Exception:
            pass
        self.trace_ids = []
        return False

    # ---------- 滑块 (TianaiCaptcha) ----------
    def _png_rgb(self, b64):
        try:
            data = base64.b64decode(b64.split(',')[1] if b64.startswith('data:') else b64)
            pos = 8
            w = h = 0
            idat = b''
            ctype = 6
            while pos < len(data):
                ln = int.from_bytes(data[pos:pos + 4], 'big')
                typ = data[pos + 4:pos + 8]
                chunk = data[pos + 8:pos + 8 + ln]
                if typ == b'IHDR':
                    w = int.from_bytes(chunk[0:4], 'big')
                    h = int.from_bytes(chunk[4:8], 'big')
                    ctype = chunk[9]
                elif typ == b'IDAT':
                    idat += chunk
                pos += 12 + ln
            raw = zlib.decompress(idat)
            ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype, 4)
            stride = w * ch
            rows = []
            prev = [0] * stride
            p = 0
            for y in range(h):
                ft = raw[p]
                p += 1
                line = list(raw[p:p + stride])
                p += stride
                if ft == 1:
                    for i in range(ch, stride):
                        line[i] = (line[i] + line[i - ch]) & 0xFF
                elif ft == 2:
                    for i in range(stride):
                        line[i] = (line[i] + prev[i]) & 0xFF
                elif ft == 3:
                    for i in range(stride):
                        a = line[i - ch] if i >= ch else 0
                        line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
                elif ft == 4:
                    for i in range(stride):
                        a = line[i - ch] if i >= ch else 0
                        b_ = prev[i]
                        c = prev[i - ch] if i >= ch else 0
                        pa, pb, pc = abs(a - b_), abs(b_ - c), abs(a - c)
                        pr = a if (pa <= pb and pa <= pc) else (b_ if pb <= pc else c)
                        line[i] = (line[i] + pr) & 0xFF
                prev = line
                rows.append(line)
            rP = [[0] * w for _ in range(h)]
            gP = [[0] * w for _ in range(h)]
            bP = [[0] * w for _ in range(h)]
            aP = [[255] * w for _ in range(h)]
            for y in range(h):
                row = rows[y]
                rr = rP[y]
                gg = gP[y]
                bb = bP[y]
                aa = aP[y]
                for x in range(w):
                    o = x * ch
                    if ch >= 3:
                        rr[x] = row[o]
                        gg[x] = row[o + 1]
                        bb[x] = row[o + 2]
                        if ch == 4:
                            aa[x] = row[o + 3]
                    elif ch == 1:
                        rr[x] = gg[x] = bb[x] = row[o]
                    elif ch == 2:
                        rr[x] = gg[x] = bb[x] = row[o]
                        aa[x] = row[o + 1]
            return rP, gP, bP, aP
        except Exception:
            return None, None, None, None

    def _locate_notch(self, bg_b64, tp_b64):
        try:
            tr, tg, tb, ta = self._png_rgb(tp_b64)
        except Exception:
            return None, 0.0
        if not tr or not ta:
            return None, 0.0
        Ht = len(ta)
        Wt = len(ta[0]) if Ht else 0
        if not Wt:
            return None, 0.0
        x0 = None
        x1 = -1
        y0 = None
        y1 = -1
        for yy in range(Ht):
            arow = ta[yy]
            for xx in range(Wt):
                if arow[xx] > 128:
                    if x0 is None or xx < x0:
                        x0 = xx
                    if xx > x1:
                        x1 = xx
                    if y0 is None:
                        y0 = yy
                    if yy > y1:
                        y1 = yy
        if x0 is None:
            return None, 0.0
        tw = x1 - x0 + 1
        th = y1 - y0 + 1
        if tw < 12 or th < 12:
            return None, 0.0
        coords = []
        for yy in range(th):
            arow = ta[y0 + yy]
            for xx in range(tw):
                if arow[x0 + xx] > 128:
                    coords.append((xx, yy))
        n = len(coords)
        if n < 12:
            return None, 0.0
        mr = mg = mb = 0.0
        for (xx, yy) in coords:
            mr += tr[y0 + yy][x0 + xx]
            mg += tg[y0 + yy][x0 + xx]
            mb += tb[y0 + yy][x0 + xx]
        mr /= n
        mg /= n
        mb /= n
        tc = []
        for (xx, yy) in coords:
            tc.append((tr[y0 + yy][x0 + xx] - mr,
                       tg[y0 + yy][x0 + xx] - mg,
                       tb[y0 + yy][x0 + xx] - mb))
        tn2 = 0.0
        for (a1, b1, c1) in tc:
            tn2 += a1 * a1 + b1 * b1 + c1 * c1
        if tn2 <= 1e-12:
            return None, 0.0
        tn = math_sqrt(tn2)
        try:
            data = base64.b64decode(bg_b64.split(',')[1] if bg_b64.startswith('data:') else bg_b64)
            rP, gP, bP = _JpegGray(data).decode_rgb_rows(y0, y1 + 1)
        except Exception:
            return None, 0.0
        if not rP or len(rP) < th:
            return None, 0.0
        W = len(rP[0])
        if W < tw + 20:
            return None, 0.0

        def _prep(pts):
            out = []
            for (xx, yy) in pts:
                out.append((rP[yy], gP[yy], bP[yy], xx, yy))
            return out

        def _tsum(tcv):
            s1 = s2 = s3 = 0.0
            for (a1, b1, c1) in tcv:
                s1 += a1
                s2 += b1
                s3 += c1
            return (s1, s2, s3)

        def _ncc(x, prep, tcv, tsum):
            m2 = len(prep)
            sr = sg = sb = 0.0
            qr = qg = qb = 0.0
            dot = 0.0
            for i in range(m2):
                rr, gg, bb, xx, yy = prep[i]
                a = rr[x + xx]
                b = gg[x + xx]
                c = bb[x + xx]
                sr += a
                sg += b
                sb += c
                qr += a * a
                qg += b * b
                qb += c * c
                a1, b1, c1 = tcv[i]
                dot += a1 * a + b1 * b + c1 * c
            pn2 = (qr + qg + qb) - (sr * sr + sg * sg + sb * sb) / m2
            if pn2 <= 1e-12:
                return -1.0
            num = dot - (sr * tsum[0] + sg * tsum[1] + sb * tsum[2]) / m2
            return num / (tn * math_sqrt(pn2))

        pts_a = []
        tc_a = []
        for i in range(n):
            xx, yy = coords[i]
            if (xx % 4 == 0) and (yy % 4 == 0):
                pts_a.append(coords[i])
                tc_a.append(tc[i])
        if len(pts_a) < 8:
            for i in range(0, n, 4):
                pts_a.append(coords[i])
                tc_a.append(tc[i])
        prep_a = _prep(pts_a)
        tsum_a = _tsum(tc_a)
        coarse = []
        for x in range(10, W - tw - 10, 4):
            coarse.append((_ncc(x, prep_a, tc_a, tsum_a), x))
        coarse.sort(reverse=True)
        top = []
        for s, x in coarse:
            if all(abs(x - t) > 8 for t in top):
                top.append(x)
            if len(top) >= 6:
                break
        if not top:
            return None, 0.0
        prep_f = _prep(coords)
        tsum_f = _tsum(tc)
        fb = None
        for base in top:
            for x in range(max(10, base - 6), min(W - tw - 10, base + 6) + 1):
                s = _ncc(x, prep_f, tc, tsum_f)
                if fb is None or s > fb[0]:
                    fb = (s, x)
        if fb is None:
            return None, 0.0
        return fb[1] - x0, fb[0]

    def _track(self, delta):
        duration = random.randint(1200, 2200)
        n = random.randint(35, 55)
        st = int(time.time() * 1000) - random.randint(2000, 5000)
        px = random.randint(100, 200)
        py = random.randint(300, 600)
        over = random.randint(2, 8)
        final = delta + over
        track = [{"x": px, "y": py, "type": "down", "t": 0}]
        for i in range(1, n):
            p = i / float(n - 1)
            e = 1 - (1 - p) ** 3
            jx = random.randint(-2, 2) if random.random() < 0.15 else 0
            track.append({"x": int(px + final * e + jx), "y": py + random.randint(-3, 3),
                          "type": "move", "t": int(duration * e)})
        bn = random.randint(3, 6)
        for j in range(1, bn + 1):
            p = j / float(bn + 1)
            back = over * (1 - p)
            track.append({"x": int(px + delta + back), "y": py + random.randint(-2, 2),
                          "type": "move", "t": int(duration + 60 * j + random.randint(-10, 10))})
        t_up = int(duration * 1.12) + random.randint(80, 250)
        track.append({"x": px + delta, "y": py, "type": "up", "t": t_up})
        off = self._server_offset()
        abs_st = st + off
        abs_et = abs_st + t_up + random.randint(300, 800)
        return track, abs_st, abs_et

    def _verify_headers(self):
        return {
            "User-Agent": API_UA,
            "X-Platform": "windows",
            "X-Client-Id": self.cid,
        }

    _srv_off = None

    def _server_offset(self):
        if Spider._srv_off is not None:
            return Spider._srv_off
        off = 0
        try:
            req = urllib.request.Request(self.api + "/system/config",
                                         headers=self._verify_headers())
            ctx = _SSL_CTX if (_SSL_CTX and self.api.startswith("https")) else None
            resp = urllib.request.urlopen(req, timeout=10, context=ctx)
            dh = resp.headers.get("Date") or ""
            if dh:
                import email.utils
                dt = email.utils.parsedate_to_datetime(dh)
                off = int(dt.timestamp() * 1000) - int(time.time() * 1000)
        except Exception:
            off = 0
        Spider._srv_off = off
        return off

    def _generate_captcha(self):
        """v2.3-fix: 多策略请求 generate，兼容服务端不同要求"""
        url = self.api + "/auth/verify/generate"
        strategies = [
            ("GET", self._verify_headers(), None),
            ("POST", self._verify_headers(), {}),
            ("GET", self._headers("/auth/verify/generate"), None),
            ("POST", self._headers("/auth/verify/generate"), {}),
        ]
        for method, hdrs, body in strategies:
            for retry in range(3):
                try:
                    if method == "GET":
                        d = self._jget(url, headers=hdrs, timeout=8)
                    else:
                        d = self._jget(url, headers=hdrs, post=body, timeout=8)
                    if d and d.get("code") == 200:
                        info = d.get("data") or {}
                        if not isinstance(info, dict):
                            info = {}
                        token = info.get("token") or info.get("captchaId")
                        if token and isinstance(token, str) and len(token) > 10:
                            return {"type": "TOKEN", "token": token}
                        return info
                except Exception:
                    pass
                if retry < 1:
                    time.sleep(0.5)
        return None

    def _persist_token(self):
        try:
            _persist_save({"cid": self.cid, "vtoken": self.vtoken,
                           "ts": int(time.time() * 1000)}, self._pdir)
        except Exception:
            pass

    def handle_1004(self, path):
        # v2.3: 增强 G500 退避 — 指数退避 3 次 + session 重置
        self._diag_v = ""
        self._verify_tries = 0
        try:
            if self.vtoken:
                self.vtoken = ""
                self._persist_token()
            t_gen = time.time()
            # v2.3: G500 指数退避重试 (最多 3 次)
            # v2.3-fix: 使用多策略 generate
            info = self._generate_captcha()
            if info is None:
                self._diag_v = "G000"
                return False
            if info.get("type") == "TOKEN":
                self.vtoken = info.get("token")
                self._persist_token()
                return True
            # 非 SLIDER 类型最多补 2 次
            type_retry = 0
            while info.get("type") != "SLIDER" and type_retry < 2:
                type_retry += 1
                time.sleep(0.3)
                info = self._generate_captcha()
                if info is None:
                    self._diag_v = "G000"
                    return False
                if info.get("type") == "TOKEN":
                    self.vtoken = info.get("token")
                    self._persist_token()
                    return True
            if info.get("type") != "SLIDER":
                self._diag_v = "T%s" % str(info.get("type"))[:6]
                return False
            off = self._server_offset()
            loc_fail = 0
            for _ in range(8):
                if self._verify_tries >= 3:
                    break
                delta, score = self._locate_notch(info.get("backgroundImage") or "", info.get("templateImage") or "")
                if delta is None or delta < 20 or score < 0.45:
                    loc_fail += 1
                    self._diag_v = "L%.2f" % (score or 0.0)
                    d = self._jget(self.api + "/auth/verify/generate",
                                   headers=self._verify_headers(), post={})
                    if not d or d.get("code") != 200:
                        self._diag_v = "G%s" % (str((d or {}).get("code") if d else 0)[:6])
                        return False
                    info = d.get("data") or {}
                    t_gen = time.time()
                    continue
                track, st, et = self._track(delta)
                if off:
                    st += off
                    et += off
                body = {
                    "id": info.get("id"),
                    "data": {
                        "bgImageWidth": info.get("backgroundImageWidth") or 600,
                        "bgImageHeight": info.get("backgroundImageHeight") or 360,
                        "sliderImageWidth": info.get("templateImageWidth") or 110,
                        "sliderImageHeight": info.get("templateImageHeight") or 360,
                        "startTime": st, "stopTime": et,
                        "trackList": track,
                    },
                }
                el = time.time() - t_gen
                if el < 3.2:
                    time.sleep(3.2 - el)
                self._verify_tries += 1
                r = self._jget(self.api + "/auth/verify",
                               headers=self._verify_headers(), post=body)
                if r and r.get("code") == 200:
                    tk = (r.get("data") or {})
                    self.vtoken = tk.get("token") or tk.get("captchaId") or ""
                    self._diag_v = ""
                    self._persist_token()
                    return True
                self._diag_v = "V%s" % str((r or {}).get("code") or 0)[:6]
                d = self._jget(self.api + "/auth/verify/generate",
                               headers=self._verify_headers(), post={})
                if not d or d.get("code") != 200:
                    return False
                info = d.get("data") or {}
                t_gen = time.time()
            return False
        except Exception as e:
            try:
                self._diag_v = "X" + str(e)[:12]
            except Exception:
                self._diag_v = "X"
            return False

    # ---------- 请求封装 (v2.3: 1004 时先清 session) ----------
    NO_THROTTLE = (
        "/film/category", "/system/config", "/film/search", "/film/search/hot",
        "/line/play", "/line/play/parse", "/film/detail", "/film/detail/play/app",
        "/film/detail/play"
    )

    def api_get(self, path, params=None, retry_verify=True, timeout=15):
        if path not in self.NO_THROTTLE:
            gap = time.time() - self._last_api_ts
            if gap < 0.8:
                time.sleep(0.8 - gap)
            self._last_api_ts = time.time()
        try:
            self._ensure_session()
            url = self.api + path
            if params:
                url += "?" + urllib.parse.urlencode(params)
            d = self._jget(url, headers=self._headers(path), timeout=timeout)
            if not d:
                return None
            c = d.get("code")
            if c == 1004 and retry_verify:
                # v2.3-fix: 移除熔断器，每次 1004 都尝试自愈 + 最多2次重试
                for retry in range(2):
                    self.session = ""
                    self._ensure_session()
                    if self.handle_1004(path):
                        d2 = self._jget(url, headers=self._headers(path), timeout=timeout)
                        if d2:
                            if d2.get("code") == 200:
                                return d2
                            if d2.get("code") != 1004:
                                return d2
                    time.sleep(0.5)
                return d
            if c == 200:
                return d
            if c in (429, 503):
                self._diag_v = "R%d" % c
            return d
        except Exception:
            return None

    # ---------- TVBox 接口 ----------
    def getName(self):
        return "山有木兮"

    def isVideoFormat(self, url):
        if not url:
            return False
        u = url.lower()
        if u.endswith((".m3u8", ".mp4", ".mkv", ".flv", ".ts")):
            return True
        if ".m3u8?" in u or ".mp4?" in u or ".mkv?" in u or ".flv?" in u or ".ts?" in u:
            return True
        if u.endswith(".m3u8#") or u.endswith(".mp4#"):
            return True
        return False

    def homeContent(self, filter1=1):
        out = {"class": [], "list": []}
        try:
            d = self.api_get("/film/category")
            data = (d or {}).get("data") or []
            self.cat_cache = data
            cls = []
            for c in data:
                cls.append({"type_id": str(c.get("categoryId", "")), "type_name": c.get("categoryName", "")})
                for f in (c.get("filmList") or [])[:6]:
                    out["list"].append(self._vod(f, c.get("categoryId")))
            out["class"] = cls
        except Exception:
            pass
        return out

    def _vod(self, f, cid=None):
        vod = {
            "vod_id": str(f.get("id", "")),
            "vod_name": f.get("name", ""),
            "vod_pic": self._img(f.get("cover", "")),
            "vod_remarks": self._remark(f),
        }
        if cid is not None:
            vod["type_id"] = str(cid)
        return vod

    def _remark(self, f):
        parts = []
        sc = f.get("doubanScore")
        if sc and str(sc) != "0.0":
            parts.append(str(sc) + "分")
        us = f.get("updateStatus")
        if us:
            parts.append(str(us))
        return " ".join(parts) if parts else ""

    def homeVideoContent(self):
        try:
            d = self.api_get("/film/rank/quality")
            lst = (d or {}).get("data") or []
            return {"list": [self._vod(f) for f in lst[:20]]}
        except Exception:
            return {}

    def _filters(self, cid):
        if cid in self._filter_cache:
            return self._filter_cache[cid]
        d = self.api_get("/film/category/filter", params={"categoryId": cid})
        data = (d or {}).get("data") or {}
        ext = {"area": "地区", "year": "年代", "language": "语言", "sort": "排序"}
        f = []
        for key in ("area", "year", "language", "sort"):
            opts = data.get(key + "Options") or []
            if not opts:
                continue
            vals = [{"n": "全部", "v": ""}]
            for o in opts:
                if isinstance(o, dict):
                    ovl = o.get("value")
                    if isinstance(ovl, dict):
                        ovl = ovl.get("value") or ovl.get("id")
                    lbl = o.get("label") or str(ovl)
                    if isinstance(lbl, dict):
                        lbl = lbl.get("label") or str(ovl)
                    ov = str(ovl if ovl is not None else o.get("id") or lbl)
                    vals.append({"n": str(lbl), "v": ov})
                else:
                    vals.append({"n": str(o), "v": str(o)})
            f.append({"key": key, "name": ext[key], "value": vals})
        copts = data.get("categoryOptions") or []
        if copts:
            vals = [{"n": "全部", "v": ""}]
            for o in copts:
                if isinstance(o, dict):
                    vals.append({"n": str(o.get("value", "")), "v": str(o.get("value", ""))})
                else:
                    vals.append({"n": str(o), "v": str(o)})
            f.append({"key": "childCategoryId", "name": "分类", "value": vals})
        self._filter_cache[cid] = f
        return f

    def categoryContent(self, tid, pg=1, filter1=1, extend=None):
        out = {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 15, "total": 0}
        try:
            if isinstance(extend, str) and extend.strip().startswith("{"):
                try:
                    extend = json.loads(extend)
                except Exception:
                    extend = {}
            if not isinstance(extend, dict):
                extend = {}
            try:
                pgn = int(pg)
            except Exception:
                pgn = 1
            params = {
                "categoryId": str(tid),
                "pageNum": pgn,
                "pageSize": 15,
                "sort": extend.get("sort") or "updateTime",
            }
            for k in ("area", "year", "language"):
                v = extend.get(k)
                if v:
                    params[k] = str(v)
            cc = extend.get("childCategoryId")
            if cc:
                params["childCategoryId"] = str(cc)
            d = self.api_get("/film/category/list", params=params)
            data = (d or {}).get("data") or {}
            lst = data.get("list") or []
            total = data.get("total") or 0
            out["list"] = [self._vod(f) for f in lst]
            out["total"] = total
            out["page"] = pgn
            if total:
                pc = (total + 14) // 15
            elif lst:
                pc = pgn + 1
            else:
                pc = max(1, pgn - 1)
            out["pagecount"] = pc if pc >= 1 else 1
        except Exception:
            pass
        return out

    def _dfail(self, body):
        # v2.3: 失败缓存从 60s 降到 10s (瞬态错误不应长期阻塞)
        self._detail_fail_body = body
        self._detail_fail_until = time.time() + 10
        return body

    def detailContent(self, ids):
        fid = str(ids[0])
        now = time.time()
        if self._detail_fail_body is not None and now < self._detail_fail_until:
            return self._detail_fail_body
        fallback = {"list": [{"vod_id": fid, "vod_name": "加载失败 D1 详情请求空",
                              "vod_play_from": "提示", "vod_play_url": "D1-网络或签名失败#err"}]}
        try:
            d = self.api_get("/film/detail", params={"id": fid})
            if d is None and self._diag:
                d2 = self.api_get("/film/detail/play/app", params={"id": fid})
                if d2 and d2.get("code") == 200:
                    d = d2
            if d is None and self._diag:
                d2 = self.api_get("/film/detail/play", params={"filmId": fid})
                if d2 and d2.get("code") == 200:
                    d = d2
            if d is None:
                fb = "加载失败 D2 请求无响应"
                ep = "D2-检查网络或稍后重试#err"
                if self._diag:
                    fb += "(verify=" + ("ok" if self.vtoken else "no") + ")"
                return self._dfail({"list": [{"vod_id": fid, "vod_name": fb,
                                  "vod_play_from": "提示", "vod_play_url": ep}]})
            c = d.get("code")
            if c != 200:
                return self._dfail({"list": [{"vod_id": fid,
                    "vod_name": "加载失败 D3 %s%s" % (str(c), (" [" + self._diag_v + "]") if self._diag_v else ""),
                    "vod_play_from": "提示",
                    "vod_play_url": ("D3-" + str(d.get("message") or "服务端错误")[:20] +
                        ("#err 稍后3分钟再试" if c == 1004 else "#err"))}]})
            f = d.get("data") or {}
            if not f.get("name"):
                return self._dfail({"list": [{"vod_id": fid, "vod_name": "加载失败 D4 响应缺片名",
                    "vod_play_from": "提示", "vod_play_url": "D4-数据结构异常#err"}]})
            lines = f.get("playLineList") or []
            froms = []
            urls = []
            for ln in lines:
                pn = str(ln.get("playerName") or ln.get("playerId") or "线路")
                eps = ln.get("lines") or []
                if not eps:
                    continue
                froms.append(pn)
                eu = []
                for e in eps:
                    eu.append(str(e.get("name", "")) + "$" + str(e.get("id", "")))
                urls.append("#".join(eu))
            if not froms:
                return self._dfail({"list": [{"vod_id": fid, "vod_name": "加载失败 D5 无可用线路",
                    "vod_play_from": "提示", "vod_play_url": "D5-该片线路为空#err"}]})
            vod = {
                "vod_id": fid,
                "vod_name": f.get("name", ""),
                "vod_pic": self._img(f.get("cover", "")),
                "type_name": f.get("categoryName", ""),
                "vod_year": f.get("year", ""),
                "vod_area": f.get("area", ""),
                "vod_director": f.get("director", ""),
                "vod_actor": f.get("actor", ""),
                "vod_remarks": self._remark(f),
                "vod_content": (f.get("blurb") or f.get("other") or "").strip(),
                "vod_play_from": "$$$".join(froms) if froms else "山有木兮",
                "vod_play_url": "$$$".join(urls),
            }
            return {"list": [vod]}
        except Exception:
            return self._dfail({"list": [{"vod_id": fid, "vod_name": "加载失败 D6 异常",
                "vod_play_from": "提示", "vod_play_url": "D6-内部错误#err"}]})

    def searchContent(self, *args, **kwargs):
        key = ""
        pg = None
        for a in args:
            if a is None:
                continue
            if isinstance(a, str) and not key:
                key = a
            elif isinstance(a, int) and not isinstance(a, bool):
                pg = a
        if not key and args:
            key = str(args[0] or "")
        if "key" in kwargs:
            key = kwargs["key"]
        if "wd" in kwargs:
            key = kwargs["wd"]
        if "pg" in kwargs and kwargs["pg"]:
            pg = kwargs["pg"]
        if not key:
            return {}
        try:
            d = self.api_get("/film/search", params={
                "keyword": key,
                "pageNum": int(pg) if pg else 1,
                "pageSize": 20,
            })
            data = (d or {}).get("data") or {}
            lst = data.get("list") or []
            return {"list": [self._vod(f) for f in lst]}
        except Exception:
            return {}

    def searchContentPage(self, *args, **kwargs):
        return self.searchContent(*args, **kwargs)

    # ---------- 播放系统 (v2.3 重构 — 1004 自愈 + G500 修复) ----------

    def _extract_url(self, data):
        """v2.3: 从服务端各种响应结构中提取可播 URL"""
        if not data:
            return ""
        if isinstance(data, str):
            return data.strip()
        if isinstance(data, dict):
            for key in ("url", "playUrl", "src", "m3u8", "video", "link", "data", "path"):
                val = data.get(key)
                if val and isinstance(val, str) and val.strip():
                    return val.strip()
                if val and isinstance(val, dict):
                    nested = self._extract_url(val)
                    if nested:
                        return nested
            for v in data.values():
                if isinstance(v, str) and v.strip().startswith("http"):
                    return v.strip()
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            if isinstance(first, str):
                return first.strip()
            if isinstance(first, dict):
                return self._extract_url(first)
        return ""

    def _is_parse_page(self, url):
        """v2.3: 判断 URL 是否为解析页 (需壳嗅探/WebView 解析)"""
        if not url:
            return False
        u = url.lower().strip()
        strong_sigs = ("jx.", "/jx/", "/player/", "parse?", "url=", "vid=", "vurl=",
                       "/play?", "/video?", "/jump/", "/goto/")
        if any(sig in u for sig in strong_sigs):
            return True
        if any(u.endswith(ext) for ext in (".m3u8", ".mp4", ".mkv", ".flv", ".ts", ".mp3", ".aac")):
            return False
        if any((ext + "?") in u for ext in (".m3u8", ".mp4", ".mkv", ".flv", ".ts")):
            return False
        weak_sigs = (".html", ".htm", "m3u8.php", "mp4.php", "api.php", "url.php",
                     "go.php", "vid.php")
        if any(sig in u for sig in weak_sigs):
            return True
        if "m3u8" not in u and "mp4" not in u and "ts" not in u and "flv" not in u:
            if ".php?" in u or ".html?" in u:
                return True
        return False

    def _probe(self, url, headers, timeout=5):
        """v2.3: 双模式探测 — HEAD 快速 + GET Range 确认"""
        h = dict(headers)
        ctx = _SSL_CTX if (_SSL_CTX and url.startswith("https")) else None
        try:
            req = urllib.request.Request(url, headers=h, method="HEAD")
            resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
            ct = (resp.headers.get("Content-Type", "") or "").lower()
            cl = resp.headers.get("Content-Length")
            loc = resp.headers.get("Location") or resp.geturl()
            video_types = ("mpegurl", "video", "mp2t", "mp4", "webm", "flv", "octet-stream", "binary")
            if any(t in ct for t in video_types):
                return True
            if cl:
                try:
                    if int(cl) > 512 * 1024:
                        return True
                except Exception:
                    pass
            if loc and loc != url:
                loc_l = loc.lower()
                if any(loc_l.endswith(ext) for ext in (".m3u8", ".mp4", ".ts", ".flv")):
                    return True
            if "text/html" in ct:
                return False
        except Exception:
            pass
        try:
            h["Range"] = "bytes=0-63"
            req = urllib.request.Request(url, headers=h)
            resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
            data = resp.read(64)
            head = (data or b"")[:32]
            ct = (resp.headers.get("Content-Type", "") or "").lower()
            if head.startswith(b"#EXTM3U"):
                return True
            if head[4:8] == b"ftyp":
                return True
            if len(head) >= 8:
                box_size = struct.unpack(">I", head[:4])[0]
                if 8 <= box_size <= 0x10000000 and head[4:8] in (b"ftyp", b"moov", b"mdat", b"free"):
                    return True
            if head[:3] == b"FLV":
                return True
            if len(data) >= 189 and data[0:1] == b"\x47" and data[188:189] == b"\x47":
                return True
            if head[:4] == b"\x1a\x45\xdf\xa3":
                return True
            video_types = ("mpegurl", "video", "mp2t", "mp4", "webm", "flv", "octet-stream")
            if any(t in ct for t in video_types):
                return True
            html_sigs = (b"<", b"<!", b"\xef\xbb\xbf<", b"\xfe\xff<", b"\xff\xfe<")
            if head.startswith(html_sigs) or "text/html" in ct:
                return False
            return True
        except Exception:
            return None

    def _resolve_play_url(self, lid):
        """v2.3: 极速解析 + 1004 自愈 + 多通道轮询"""
        direct = ""
        # 1. APP 解析通道
        try:
            pr = self.api_get("/line/play/parse", params={"lineId": lid}, timeout=10)
            if pr and pr.get("code") == 200:
                direct = self._extract_url(pr.get("data"))
        except Exception:
            pass
        # 2. Web 兜底
        if not direct:
            try:
                d = self.api_get("/line/play", params={"lineId": lid}, timeout=15)
                info = (d or {}).get("data") or {}
                direct = self._extract_url(info)
            except Exception:
                pass
        # 3. APP 详情通道
        if not direct:
            try:
                d = self.api_get("/film/detail/play/app", params={"id": lid}, timeout=12)
                if d and d.get("code") == 200:
                    direct = self._extract_url(d.get("data"))
            except Exception:
                pass
        # 4. Web 详情通道
        if not direct:
            try:
                d = self.api_get("/film/detail/play", params={"filmId": lid}, timeout=12)
                if d and d.get("code") == 200:
                    direct = self._extract_url(d.get("data"))
            except Exception:
                pass
        return direct

    def _format_play_url(self, url, headers):
        """v2.3: 统一 URL 格式化、路由决策、解析页识别"""
        if not url:
            return {"url": "", "parse": 0, "header": headers, "msg": "P1:空URL"}
        url = url.strip()
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("/") and not url.startswith("http"):
            u = self.host + (url if url.startswith("/api") else "/api" + url)
            return {"url": u, "parse": 0, "header": headers}
        if url.startswith(self.host):
            return {"url": url, "parse": 0, "header": headers}
        if "http" in url:
            ul = url.lower()
            if self._is_parse_page(url):
                parse_headers = dict(headers)
                parse_headers.setdefault("Referer", self.host)
                return {"url": url, "parse": 1, "header": parse_headers}
            safe_exts = (".m3u8", ".mp4", ".mkv", ".flv", ".ts")
            if any(ul.endswith(ext) for ext in safe_exts):
                return {"url": url, "parse": 0, "header": headers}
            if any((ext + "?") in ul for ext in safe_exts):
                return {"url": url, "parse": 0, "header": headers}
            ok = self._probe(url, headers, timeout=4)
            if ok is True:
                return {"url": url, "parse": 0, "header": headers}
            proxy_headers = dict(headers)
            proxy_headers.setdefault("Referer", self.host)
            proxy = self.api + "/files/proxy?url=" + urllib.parse.quote(url, safe="")
            return {"url": proxy, "parse": 0, "header": proxy_headers}
        return {"url": url, "parse": 0, "header": headers}

    def playerContent(self, flag, id, vipFlags=None):
        """v2.3: 播放系统 — 1004 自愈 + 缓存 + 极速解析 + 多轮重试"""
        lid = str(id)
        headers = {"User-Agent": "Lavf/58.76.100"}

        # 1. 缓存命中
        cache = self._play_cache.get(lid)
        if cache and time.time() - cache[0] < 600:
            return self._format_play_url(cache[1], headers)

        # 2. 解析直链 (带 1004 自愈 + 最多3轮重试)
        direct = ""
        for attempt in range(3):
            direct = self._resolve_play_url(lid)
            if direct:
                break
            # 强制刷新凭证后重试
            self.session = ""
            if attempt == 0:
                self.vtoken = ""
                self._persist_token()
            if self._diag_v and "1004" in self._diag_v:
                self.handle_1004("/line/play")
            else:
                self._ensure_session()
            time.sleep(1.0)

        if not direct:
            return {"url": "", "parse": 0, "header": headers, "msg": "P0:解析失败 " + self._diag_v}

        # 3. 写入缓存
        self._play_cache[lid] = (time.time(), direct)
        if len(self._play_cache) > 64:
            for k in list(self._play_cache.keys())[:32]:
                self._play_cache.pop(k, None)

        return self._format_play_url(direct, headers)

    def _img(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            return self.host + u
        return u

    def localProxy(self, params):
        return None


# ============================================================
# 模块级导出
# ============================================================
_SP = None
_SP_T = 0

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

def homeFilterContent(params):
    return {}

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

def isVideoFormat(url):
    return _ensure().isVideoFormat(url)

def localProxy(params):
    return None


# ============================================================
# 自测
# ============================================================
if __name__ == "__main__":
    sp = Spider()
    sp.init()
    print("[1] " + sp.getName() + " | 签名 " + sp.sign("/film", sp.timestamp())[:16] + "...")
    ts = sp.timestamp()
    assert len(ts) == 13 and int(ts[-1]) == sum(int(c) for c in ts[:-1]) % 10
    print("[2] timestamp 校验位 OK: " + ts)
    import struct as _s
    def _mkpng(w, h, x0, x1):
        raw = b''
        for y in range(h):
            raw += b'\x00'
            for x in range(w):
                a = 255 if (x0 <= x <= x1 and 10 <= y <= 50) else 0
                raw += bytes([255, 255, 255, a])
        def chunk(t, d):
            return _s.pack('>I', len(d)) + t + d + _s.pack('>I', zlib.crc32(t + d) & 0xffffffff)
        ihdr = _s.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
    b64 = base64.b64encode(_mkpng(110, 60, 20, 90)).decode()
    tr, tg, tb, ta = sp._png_rgb(b64)
    assert tr is not None
    print("[3] PNG RGB 解码 OK")
    key = "0x1A2B3C4D5E6F7A8B9C"
    plain = "rtsTestSession42"
    enc_hex = ''.join('%02x' % (ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(plain))
    assert sp._xor(enc_hex) == plain
    print("[4] XOR (Gw hex) 往返 OK")
    src = open(__file__.replace('.pyc', '.py'), 'r', encoding='utf-8', errors='ignore').read()
    import re as _re
    cnt = len(_re.findall(r'f"[^"\n]*\{', src)) + len(_re.findall(r"f'[^'\n]*\{", src))
    print("[5] f-string 检查: %d (应=0)" % cnt)
    h = sp.homeContent(1)
    assert "class" in h and "list" in h
    print("[6] homeContent 容错 OK")
    assert sp._extract_url("http://a.com/1.m3u8") == "http://a.com/1.m3u8"
    assert sp._extract_url({"url": "http://a.com/2.mp4"}) == "http://a.com/2.mp4"
    assert sp._extract_url({"data": {"playUrl": "http://a.com/3.ts"}}) == "http://a.com/3.ts"
    print("[7] _extract_url 兼容 OK")
    assert sp._is_parse_page("https://jx.example.com/?url=xxx") == True
    assert sp._is_parse_page("http://a.com/1.m3u8") == False
    print("[8] _is_parse_page 检测 OK")
    assert "/line/play" in sp.NO_THROTTLE
    print("[9] 节流豁免 OK")
    # v2.3: 验证 detailContent 失败缓存时间
    sp._dfail({"test": 1})
    assert sp._detail_fail_until - time.time() <= 12  # 10s 缓存 + 浮动
    print("[10] 失败缓存 10s OK")
    print("=== ALL SELF-TESTS PASS ===")

# -*- coding: utf-8 -*-
# ============================================================
#  WhaleApp (爱影/爱影视 4K) · TVBox 爬虫脚本  【深度修复版】
#  原 dex 类: com.github.catvod.spider.WhaleApp
#  修复日期: 2026-09-13
# ------------------------------------------------------------
#  本版修复要点:
#   1) protobuf 字段读取兼容 varint/bytes 两种编码(修复 id 为
#      bytes 编码时所有条目被丢弃 → 主页/分类空白的问题)
#   2) _request 失败不再静默返回 None,打印状态码与报文片段
#   3) code 兼容 int 0 / str "0"
#   4) 外层 protobuf 剥壳容错: field3 缺失时尝试整体解码 / JSON 直出
#   5) 列表解析"双保险": 先按反编译字段(4→11 / 1 / 2)解析,
#      失败则递归嗅探 item 数组(按"id+name+pic"特征识别)
#   6) 分页元数据缺失时按条数估算 pagecount,防止 TVBox 判定无下一页
#   7) homeContent 横幅为空时自动回退到首个分类第一页
#   8) detail 线路/剧集字段读取容错, line 名缺失不再丢线
#   9) playerContent 直链正则放宽(带参数/嵌路径的 m3u8)
#  10) 新增 --sniff 嗅探模式: 打印每个接口的 protobuf 字段树,
#      服务端结构再变也能一眼定位(用法见文件尾)
# ============================================================
import os
import re
import sys
import json
import time
import base64
import hashlib
import struct
import threading
from urllib.parse import quote

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""):
            pass
        def getName(self):
            return ""
        def isVideoFormat(self, url):
            return False
        def manualVideoCheck(self):
            return False
        def destroy(self):
            pass
        def localProxy(self, params):
            return None

try:
    import requests
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.retry import Retry
    requests.packages.urllib3.disable_warnings()
except Exception:
    requests = None

DEBUG = os.environ.get("WHALE_DEBUG", "0") == "1"

def _log(*a):
    sys.stderr.write("[whale] " + " ".join(str(x) for x in a) + "\n")


# ============================================================
#  dJd.d(hex) → 字符串 (XOR "DFmnpF")
# ============================================================
_KEY = "DFmnpF"
_HEX = "0123456789ABCDEF"

def dJd(hexs: str) -> str:
    bs = bytearray(len(hexs) // 2)
    for i in range(0, len(hexs), 2):
        bs[i // 2] = (_HEX.index(hexs[i]) << 4) | _HEX.index(hexs[i + 1])
    k = _KEY
    return bytes(b ^ ord(k[i % len(k)]) for i, b in enumerate(bs)).decode("utf-8", "replace")


SITE_ID  = dJd("372F190B2F2F20")
METHOD   = dJd("292319061F22")
PATH     = dJd("34271906")
PAYLOAD  = dJd("342714021F2720")
DATA     = dJd("2027190F")
CODE     = dJd("2729090B")
HTS      = dJd("1C6B39071D2337320C0300")
HSIGN    = dJd("1C6B3E071728")
CTYPE    = dJd("25361D021925253204011E692E3502004B66272E0C1C0323307B181A166B7C")
SALT     = dJd("30291800192B252404")
PIC_HOST = dJd("342F0E")

P_TYPES  = dJd("6B30020A5F323D36081D")
P_HOME   = dJd("6B2E0203156975")
P_FILTER = dJd("6B30020A5F202D2A190B0279303F1D0B4D")
P_DETAIL = dJd("6B30020A5F")
P_SEARCH = dJd("6B30020A4F31207B")
P_PARSE  = dJd("6B30020A5F3625341E0B")
PARAMS_PAGE     = dJd("62360C09157B")
PARAMS_SIZE     = dJd("62360C0915152D3C08534277")
PARAMS_SIZE_ALL = dJd("62360C09157B75601D0F1723172F170B4D7475")


# ============================================================
#  Protobuf 解析 (wire type 0/1/2/5)
# ============================================================
class PbNode:
    __slots__ = ("a", "b", "c")
    def __init__(self, a=0, b=0, c=None):
        self.a = a
        self.b = b
        self.c = c

def _read_varint(buf, pos):
    val = 0
    shift = 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, pos
        shift += 7
        if shift > 70:
            break
    return val, pos

def _read_bytes(buf, pos, n):
    if n < 0 or pos + n > len(buf):
        return b"", len(buf)
    return bytes(buf[pos:pos + n]), pos + n

def pb_decode(buf):
    nodes = []
    if not buf:
        return nodes
    if isinstance(buf, (bytearray, memoryview)):
        buf = bytes(buf)
    pos = 0
    while pos < len(buf):
        try:
            tag, pos = _read_varint(buf, pos)
        except Exception:
            break
        if tag == 0:
            break
        wire = tag & 0x7
        field = tag >> 3
        if field == 0:
            break
        node = PbNode(a=field)
        try:
            if wire == 0:
                v, pos = _read_varint(buf, pos)
                node.b = v
            elif wire == 1:
                node.c, pos = _read_bytes(buf, pos, 8)
            elif wire == 2:
                ln, pos = _read_varint(buf, pos)
                node.c, pos = _read_bytes(buf, pos, ln)
            elif wire == 5:
                node.c, pos = _read_bytes(buf, pos, 4)
            else:
                break
        except Exception:
            break
        nodes.append(node)
    return nodes

def find_node(nodes, field):
    for n in nodes:
        if n.a == field:
            return n
    return PbNode()

def all_nodes(nodes, field):
    return [n for n in nodes if n.a == field]

# ---------- 容错取值 ----------
def nv(node):
    """节点值 → str: 优先 bytes, 其次 varint"""
    if node is None:
        return ""
    if node.c:
        try:
            return node.c.decode("utf-8", "replace").strip("\x00").strip()
        except Exception:
            return ""
    if node.b:
        return str(node.b)
    return ""

def ni(node):
    """节点值 → int"""
    if node is None:
        return 0
    if node.b:
        return int(node.b)
    if node.c:
        try:
            return int(node.c.decode("utf-8", "replace").strip())
        except Exception:
            return 0
    return 0

def is_text(s):
    return bool(s) and not s.startswith("\x00")

TAG_RE = re.compile(r"<[^>]+>")
def clean_text(s):
    if not s:
        return ""
    return TAG_RE.sub(" ", s).strip()

HTTP_RE = re.compile(r'(?i)https?://[^\x00-\x1F"\'<>\\\s]+')

def join_url(base, pic):
    if not pic:
        return ""
    if pic.startswith("http://") or pic.startswith("https://"):
        return pic
    if pic.startswith("//"):
        return "https:" + pic
    if base and not base.endswith("/"):
        base = base + "/"
    return (base or "") + pic


# ============================================================
#  通用嗅探: 在 protobuf 树里自动识别"视频条目"数组
# ============================================================
def _looks_like_item(children):
    """item 特征: 有 id 味字段(1) 且 有 name 味字段(2 或 3)"""
    f1 = nv(find_node(children, 1))
    f2 = nv(find_node(children, 2))
    f3 = nv(find_node(children, 3))
    if not f1:
        return False
    # id 通常是数字或短字符串; name 是文本
    if f2 and f2 != f1:
        return True
    if f3 and (f3.lower().endswith((".jpg", ".png", ".webp", ".jpeg")) or f3.startswith(("http", "/"))):
        return True
    return False

def sniff_items(nodes, depth=0, seen=None):
    """递归收集树中所有符合 item 特征的节点(children 列表)"""
    if seen is None:
        seen = set()
    out = []
    if depth > 6:
        return out
    for n in nodes:
        if not n.c:
            continue
        try:
            children = pb_decode(n.c)
        except Exception:
            continue
        if not children:
            continue
        if _looks_like_item(children):
            key = (depth, n.a, nv(find_node(children, 1)), nv(find_node(children, 2)))
            if key not in seen:
                seen.add(key)
                out.append(children)
        out.extend(sniff_items(children, depth + 1, seen))
    return out

def _varint_enc(v):
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)

def _is_protobuf(buf):
    """校验 buf 能被 pb_decode 完整消耗(用于 dump_tree 判断是否递归)"""
    if not buf or len(buf) < 2:
        return False
    pos = 0
    n = 0
    while pos < len(buf):
        tag, pos = _read_varint(buf, pos)
        wire = tag & 7
        field = tag >> 3
        if field == 0 or tag == 0:
            return False
        if wire == 0:
            _, pos = _read_varint(buf, pos)
        elif wire == 1:
            pos += 8
        elif wire == 2:
            ln, pos = _read_varint(buf, pos)
            pos += ln
        elif wire == 5:
            pos += 4
        else:
            return False
        if pos > len(buf):
            return False
        n += 1
    return pos == len(buf) and n > 0

def dump_tree(nodes, depth=0, maxdepth=4, out=None):
    """打印 protobuf 字段树(--sniff 用)"""
    if out is None:
        out = []
    for n in nodes:
        if n.c:
            preview = n.c[:60]
            try:
                txt = preview.decode("utf-8")
                if not all(32 <= ord(ch) < 127 or ord(ch) > 127 for ch in txt):
                    txt = preview.hex()
            except Exception:
                txt = preview.hex()
            out.append("  " * depth + f"[f{n.a} bytes len={len(n.c)}] {txt!r}")
            if depth < maxdepth and _is_protobuf(n.c):
                sub = pb_decode(n.c)
                if sub:
                    dump_tree(sub, depth + 1, maxdepth, out)
        else:
            out.append("  " * depth + f"[f{n.a} varint] {n.b}")
    return out


# ============================================================
#  Spider
# ============================================================
class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self.proxy = ""
        self.site  = ""
        self.pic   = ""
        self._lock = threading.Lock()
        self._http = None
        self._init_session()

    def _init_session(self):
        if requests is None:
            return
        s = requests.Session()
        try:
            r = Retry(total=2, backoff_factor=0.4,
                      status_forcelist=[500, 502, 503, 504])
            ad = HTTPAdapter(max_retries=r, pool_connections=4, pool_maxsize=8)
            s.mount("http://", ad)
            s.mount("https://", ad)
        except Exception:
            pass
        self._http = s

    # ---------- 基础 ----------
    def getName(self):
        return "爱影视"

    def init(self, extend=""):
        if not extend:
            return
        try:
            obj = json.loads(extend) if extend.strip().startswith("{") else {}
            self.proxy = obj.get("proxy", "") or self.proxy
            self.site  = obj.get("site",  "") or self.site
            self.pic   = obj.get("pic",   "") or self.pic
        except Exception as e:
            _log("init:", e)

    def isVideoFormat(self, url):
        if not url:
            return False
        u = url.lower()
        return (".m3u8" in u) or (".mp4" in u) or (".flv" in u)

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            if self._http:
                self._http.close()
        except Exception:
            pass

    # ---------- 协议层 ----------
    def _request(self, path, payload=None, method="GET"):
        """POST 到 proxy, body = {site_id, method, path, payload?}
        返回内层 bytes(优先取外层 field3, 缺失则整体兜底)"""
        if not self.proxy or not self.site:
            _log("not initialised: missing proxy/site")
            return None
        body_obj = {SITE_ID: self.site, METHOD: method, PATH: path}
        if payload is not None:
            body_obj[PAYLOAD] = payload
        body = json.dumps(body_obj, separators=(",", ":"), ensure_ascii=False)
        ts = str(int(time.time()))
        sign = self._sign(ts, body)
        headers = {
            HTS: ts,
            HSIGN: sign,
            "Content-Type": CTYPE,
            "User-Agent": "Mozilla/5.0",
        }
        text = None
        last_err = None
        for attempt in range(3):
            try:
                if self._http is not None:
                    r = self._http.post(self.proxy, data=body.encode("utf-8"),
                                        headers=headers, timeout=(5, 20), verify=False)
                    text = r.text
                else:
                    import urllib.request
                    req = urllib.request.Request(self.proxy, data=body.encode("utf-8"), method="POST")
                    for k, v in headers.items():
                        req.add_header(k, v)
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        text = resp.read().decode("utf-8", "replace")
                break
            except Exception as e:
                last_err = e
                _log("request attempt %d failed: %s" % (attempt + 1, e))
                time.sleep(1 + attempt)
        if text is None:
            _log("request FAILED for", path, "->", last_err)
            return None

        if DEBUG:
            _log("resp", path, "len=", len(text), "head=", text[:200])
        try:
            obj = json.loads(text)
        except Exception:
            _log("resp is not JSON:", text[:300])
            return None

        code = obj.get(CODE, obj.get("code", -1))
        if str(code) not in ("0",):
            _log("resp code != 0:", code, text[:300])
            return None
        b64 = obj.get(DATA, obj.get("data", ""))
        if not b64:
            _log("resp missing data:", text[:300])
            return None
        try:
            raw = base64.b64decode(b64)
        except Exception:
            # 有的代理直接吐 JSON 字符串
            if b64.strip().startswith("{"):
                return b64.encode("utf-8")
            _log("data is not base64:", b64[:200])
            return None

        # 外层 protobuf: 优先 field3
        top = pb_decode(raw)
        node3 = find_node(top, 3)
        if node3.c:
            return node3.c
        # 兜底1: 有些代理把内层放在 field1/field2
        for f in (1, 2, 4):
            nd = find_node(top, f)
            if nd.c and pb_decode(nd.c):
                return nd.c
        # 兜底2: 整体当内层
        if top:
            return raw
        return None

    def _sign(self, ts, body):
        h = hashlib.md5()
        h.update(ts.encode("utf-8"))
        h.update(body.encode("utf-8"))
        h.update(SALT.encode("utf-8"))
        return h.hexdigest()

    # ---------- 业务映射 ----------
    def _map_item(self, nodes):
        """h(byte[]) — 节点 1=id, 2=name, 3=pic, 4=actor, 5=director, 6=score, 7=remarks
        【修复】全部走容错取值, id 为 bytes 编码时不再被丢弃"""
        vid = nv(find_node(nodes, 1))
        name = nv(find_node(nodes, 2))
        if not vid or not name:
            return None
        out = {
            "vod_id":       vid,
            "vod_name":     name,
            "vod_pic":      join_url(self.pic, nv(find_node(nodes, 3))),
            "vod_actor":    nv(find_node(nodes, 4)),
            "vod_director": nv(find_node(nodes, 5)),
            "vod_score":    nv(find_node(nodes, 6)),
            "vod_remarks":  nv(find_node(nodes, 7)),
        }
        return out

    def _collect_list(self, raw, prefer_fields=(2,)):
        """先按已知结构(field N 的 bytes 即 item)解析, 失败则嗅探"""
        out, seen = [], set()
        if not raw:
            return out
        top = pb_decode(raw)
        got = False
        for f in prefer_fields:
            for arr in all_nodes(top, f):
                item = self._map_item(pb_decode(arr.c))
                if item and item["vod_id"] not in seen:
                    seen.add(item["vod_id"])
                    out.append(item)
                    got = True
        if got:
            return out
        # 兜底嗅探: 自动在树里找 item
        for children in sniff_items(top):
            item = self._map_item(children)
            if item and item["vod_id"] not in seen:
                seen.add(item["vod_id"])
                out.append(item)
        return out

    def _read_page_meta(self, raw, default_pg=1, default_limit=21):
        """分类/搜索共用的分页元数据: 内层 field1=page 2=limit/pageSize 3=total"""
        pg, limit, total = int(default_pg), default_limit, 0
        if not raw:
            return pg, limit, total
        top = pb_decode(raw)
        meta = find_node(top, 1)
        if meta.c:
            inner = pb_decode(meta.c)
            p = ni(find_node(inner, 1))
            l = ni(find_node(inner, 2))
            t = ni(find_node(inner, 3))
            if p:
                pg = p
            if l:
                limit = l
            total = t
        return pg, limit, total

    def _line_skip(self, line_nodes):
        """login 线路跳过"""
        return nv(find_node(line_nodes, 7)) == "login"

    def _assemble_detail(self, item, nodes, vod_id):
        from_list, url_list = [], []
        lines = all_nodes(nodes, 17)
        if not lines:
            # 嗅探兜底: 找含 field12 子节点的线路
            for cand in sniff_items(nodes):
                if all_nodes(cand, 12):
                    lines = [PbNode(a=0, c=None)]
                    break
        for line in lines:
            line_nodes = pb_decode(line.c) if line.c else nodes
            if self._line_skip(line_nodes):
                continue
            line_name = nv(find_node(line_nodes, 2)) or nv(find_node(line_nodes, 3)) \
                        or ("线路" + str(len(from_list) + 1))
            eps = []
            for ep in all_nodes(line_nodes, 12):
                ep_nodes = pb_decode(ep.c)
                ep_name = nv(find_node(ep_nodes, 1)) or ("第" + str(len(eps) + 1) + "集")
                ep_id = nv(find_node(ep_nodes, 2))
                if not ep_id:
                    continue
                play_obj = {
                    "url":         ep_id,
                    "from":        line_name,
                    "parseIndex":  0,
                    "vod_id":      item.get("vod_id") or str(vod_id),
                    "episode_key": ep_id,
                }
                b = json.dumps(play_obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                eps.append(ep_name + "$z1." + base64.b64encode(b).decode("ascii").rstrip("="))
            if not eps:
                continue
            from_list.append(line_name)
            url_list.append("#".join(eps))
        return self._finish_play(item, from_list, url_list)

    def _finish_play(self, item, from_list, url_list):
        item["vod_play_from"] = "$$$".join(from_list)
        item["vod_play_url"]  = "$$$".join(url_list)
        return item

    # ---------- 首页 ----------
    def homeContent(self, filter):
        out_classes, out_list = [], []
        # --- 分类 ---
        try:
            raw = self._request(P_TYPES, method="GET")
            if raw:
                top = pb_decode(raw)
                got = False
                for n in all_nodes(top, 1):
                    sub = pb_decode(n.c)
                    tid = nv(find_node(sub, 1))
                    tname = nv(find_node(sub, 2))
                    if tid and tname:
                        out_classes.append({"type_id": tid, "type_name": tname})
                        got = True
                if not got:
                    # 兜底: 直接找 type 结构 (字段 1=id 2=name, 且无 pic)
                    for children in sniff_items(top):
                        if not find_node(children, 3).c:
                            tid, tname = nv(find_node(children, 1)), nv(find_node(children, 2))
                            if tid and tname and not any(c["type_id"] == tid for c in out_classes):
                                out_classes.append({"type_id": tid, "type_name": tname})
        except Exception as e:
            _log("homeContent types:", e)

        # --- 横幅推荐 ---
        try:
            raw = self._request(P_HOME, method="GET")
            if raw:
                top = pb_decode(raw)
                got = False
                # 原结构: field4 横幅 → field11 条目
                for banner in all_nodes(top, 4):
                    banner_nodes = pb_decode(banner.c)
                    for n in all_nodes(banner_nodes, 11):
                        item = self._map_item(pb_decode(n.c))
                        if item and not any(x["vod_id"] == item["vod_id"] for x in out_list):
                            out_list.append(item)
                            got = True
                # 原结构失败 → 直接按 field11
                if not got:
                    for n in all_nodes(top, 11):
                        item = self._map_item(pb_decode(n.c))
                        if item and not any(x["vod_id"] == item["vod_id"] for x in out_list):
                            out_list.append(item)
                            got = True
                # 兜底: 全局嗅探
                if not got:
                    for children in sniff_items(top):
                        item = self._map_item(children)
                        if item and not any(x["vod_id"] == item["vod_id"] for x in out_list):
                            out_list.append(item)
        except Exception as e:
            _log("homeContent banner:", e)

        # --- 横幅为空 → 回退首个分类第一页, 保证首页不空白 ---
        if not out_list and out_classes:
            try:
                c = self.categoryContent(out_classes[0]["type_id"], 1, False, {})
                out_list = c.get("list", [])[:21]
            except Exception as e:
                _log("homeContent fallback:", e)

        return {"class": out_classes, "list": out_list}

    def homeVideoContent(self):
        r = self.homeContent(False)
        return {"list": r.get("list", [])}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        try:
            path = P_FILTER + str(tid) + PARAMS_PAGE + str(pg) + PARAMS_SIZE
            raw = self._request(path, method="GET")
            if not raw:
                return self._empty_cat(pg)
            rpg, limit, total = self._read_page_meta(raw, pg)
            out_list = self._collect_list(raw, prefer_fields=(2,))
            if total and limit:
                pagecount = max(1, -(-total // limit))
            else:
                # 估算: 满页则假设还有下一页
                pagecount = rpg + 1 if len(out_list) >= limit else rpg
            return {
                "list": out_list,
                "page": int(rpg),
                "pagecount": int(pagecount),
                "limit": int(limit),
                "total": int(total),
            }
        except Exception as e:
            _log("categoryContent:", e)
            return self._empty_cat(pg)

    def _empty_cat(self, pg):
        return {"list": [], "page": int(pg), "pagecount": 1, "limit": 21, "total": 0}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        try:
            if not ids:
                return {"list": []}
            vid = ids[0]
            raw = self._request(P_DETAIL + str(vid), method="GET")
            if not raw:
                return {"list": []}
            top = pb_decode(raw)
            # 兼容双层: 若 field1 是可解码内层则剥壳
            inner = find_node(top, 1)
            if inner.c and pb_decode(inner.c) and all_nodes(pb_decode(inner.c), 17):
                top = pb_decode(inner.c)
            item = self._assemble_detail({}, top, vid)
            item["vod_id"] = nv(find_node(top, 1)) or str(vid)
            item["vod_name"] = nv(find_node(top, 2))
            item["vod_pic"] = join_url(self.pic, nv(find_node(top, 3)))
            item["vod_actor"] = nv(find_node(top, 4))
            item["vod_director"] = nv(find_node(top, 5))
            item["vod_content"] = clean_text(nv(find_node(top, 8)))
            return {"list": [item]}
        except Exception as e:
            _log("detailContent:", e)
            return {"list": []}

    # ---------- 播放 ----------
    DIRECT_RE = re.compile(r'(?i)^https?://[^\s"\'<>]+?\.(?:m3u8|mp4|flv)(?:\?[^\s"\'<>]*)?$')

    def playerContent(self, flag, id, vipFlags=None):
        try:
            if not id:
                return {"parse": 0, "url": "", "header": {}}
            url_real = id
            obj = {}
            b64 = None
            if "$z1." in id:
                _, b64 = id.split("$z1.", 1)
            elif id.startswith("z1."):
                b64 = id[3:]
            if b64:
                pad = (-len(b64)) % 4
                try:
                    obj = json.loads(base64.b64decode(b64 + "=" * pad))
                    url_real = obj.get("url") or url_real
                except Exception as e:
                    _log("play id decode:", e)

            # 直链直接播(正则放宽, 允许查询参数/嵌路径)
            if self.DIRECT_RE.match(url_real) or self.isVideoFormat(url_real):
                return {"parse": 0, "url": url_real, "header": {}}

            # POST /vod/parse
            try:
                vid_int = int(obj.get("vod_id", 0) or 0)
            except (ValueError, TypeError):
                vid_int = 0
            payload = {
                "from":        obj.get("from")        or flag or "",
                "url":         url_real,
                "parseIndex":  obj.get("parseIndex")  or 0,
                "vod_id":      vid_int,
                "episode_key": obj.get("episode_key") or url_real,
            }
            raw = self._request(P_PARSE, payload=payload, method="POST")
            if not raw:
                return {"parse": 1, "url": url_real, "header": {}}
            top = pb_decode(raw)
            url_field = ""
            for f in (2, 1, 3):
                url_field = nv(find_node(top, f))
                if url_field.startswith("http"):
                    break
            if not url_field:
                m = HTTP_RE.search(raw.decode("utf-8", "replace"))
                url_field = m.group(0) if m else ""
            if url_field:
                return {"parse": 0, "url": url_field, "header": {}}
            return {"parse": 1, "url": url_real, "header": {}}
        except Exception as e:
            _log("playerContent:", e)
            return {"parse": 1, "url": id or "", "header": {}}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        try:
            path = P_SEARCH + quote(key or "", safe="") + PARAMS_SIZE_ALL
            raw = self._request(path, method="GET")
            if not raw:
                return {"list": [], "page": 1, "pagecount": 1}
            rpg, limit, total = self._read_page_meta(raw, 1)
            out_list = self._collect_list(raw, prefer_fields=(2,))
            pagecount = max(1, -(-total // limit)) if (total and limit) else \
                        (rpg + 1 if len(out_list) >= limit else rpg)
            return {"list": out_list, "page": int(rpg), "pagecount": int(pagecount)}
        except Exception as e:
            _log("searchContent:", e)
            return {"list": [], "page": 1}

    # ---------- 嗅探模式 ----------
    def sniff(self, key="WHALE"):
        """逐接口请求并打印 protobuf 字段树, 用于服务端结构定位"""
        endpoints = [
            ("TYPES", P_TYPES, "GET", None),
            ("HOME",  P_HOME,  "GET", None),
            ("SEARCH", P_SEARCH + quote(key, safe="") + PARAMS_SIZE_ALL, "GET", None),
        ]
        for name, path, method, payload in endpoints:
            print("=" * 60)
            print("##", name, path)
            raw = self._request(path, payload=payload, method=method)
            if not raw:
                print("(no data)")
                continue
            top = pb_decode(raw)
            for line in dump_tree(top, maxdepth=5):
                print(line)


# ============================================================
#  自检 / 嗅探入口
# ============================================================
if __name__ == "__main__":
    s = Spider()
    s.init(json.dumps({
        "proxy": "https://www.tangsan.fun/jingyu.php",
        "site":  "aiyingshi",
        "pic":   "http://222.211.75.252:23433",
    }))

    if "--sniff" in sys.argv:
        # 用法: WHALE_DEBUG=1 python 爱影_fix.py --sniff [关键词]
        idx = sys.argv.index("--sniff")
        kw = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else "斗罗"
        s.sniff(kw)
        sys.exit(0)

    print("name:", s.getName())
    print("\n== homeContent ==")
    h = s.homeContent(False)
    print("classes:", [(c["type_id"], c["type_name"]) for c in h["class"]])
    print("banner count:", len(h["list"]))
    if h["list"]:
        print("first:", json.dumps(h["list"][0], ensure_ascii=False)[:300])
    if h["class"]:
        first = h["class"][0]
        print(f"\n== categoryContent({first['type_name']}) ==")
        c = s.categoryContent(first["type_id"], 1, False, {})
        print("page:", c["page"], "pagecount:", c["pagecount"], "count:", len(c["list"]))
        if c["list"]:
            vid = c["list"][0]["vod_id"]
            print(f"\n== detailContent({vid}) ==")
            d = s.detailContent([vid])
            if d["list"]:
                dd = d["list"][0]
                print("name:", dd["vod_name"], "from:", dd["vod_play_from"][:60])
                if dd["vod_play_url"]:
                    line = dd["vod_play_url"].split("$$$")[0]
                    ep = line.split("#")[0]
                    print("\n== playerContent ==")
                    p = s.playerContent(dd["vod_play_from"].split("$$$")[0], ep)
                    print("player:", json.dumps(p, ensure_ascii=False)[:300])
    print("\n== searchContent ==")
    sr = s.searchContent("斗罗", False)
    print("count:", len(sr["list"]))

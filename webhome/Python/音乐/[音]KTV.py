# -*- coding: utf-8 -*-
# 作者：qlilp
# 最后修改：2026-11-09 15:30
# [视频]爱KTV —— TVBox 系播放器的 Python 源
#
# 曲库：本地 sqlite，歌曲与歌手通过 singer_names 文本匹配（无外键）。
# 封面：<库目录>/.singer_img/<md5(歌手名)>.img。

import os
import re
import sys
import json
import time
import base64
import hashlib
import shutil
import socket
from urllib.parse import quote as _quote
import sqlite3
import threading

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider(object):
        def init(self, extend=""): pass
        def destroy(self): pass
        def getName(self): return ""
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False
        def homeContent(self, filter=False): return {"class": []}
        def homeVideoContent(self): return {"list": []}
        def categoryContent(self, tid, pg="1", filter=False, extend=None): return {"list": []}
        def detailContent(self, ids): return {"list": []}
        def searchContent(self, key, quick=False, pg="1"): return {"list": []}

        def playerContent(self, flag, id, vipFlags=None): return {}
        def localProxy(self, params): return []
        def getProxyUrl(self): return "http://127.0.0.1:9978/proxy?do=py"


# FORCE_DB_PATH: when non-empty, this exact db file always wins over
# config, auto scan and manual settings. The diag log and the cloud
# update also follow this path. Edit this one line to move the db.
# Set it to "" to turn the force off.
FORCE_DB_PATH = ""

# 默认库 = Gulu 后台自动同步的那一份。
# 配置里存过 db 就以配置为准；配置读不到时回落到这里。
DB_PATH = "/storage/emulated/0/WebHTV/LocalFiles/files-文件/db/song_9c8ec.db"
# Gulu 后台同步的那份库。目录固定，旁边有 .version 文件可作识别标志。
GULU_DB_DIR = "/storage/emulated/0/WebHTV/LocalFiles/files-文件/db"
GULU_DB = GULU_DB_DIR + "/song_9c8ec.db"
# 歌手封面目录。默认跟随数据库同级的 .singer_img；可在设置页手动覆盖。
IMG_DIR_DEFAULT = ".singer_img"
DB_MAP_URL = ""            # 库配置源（BMP 伪装），_s(4) 在表建好后填充
DB_MAP_KEY = "song_9c8ec"
DB_PART_SUFFIX = ".part"
MAX_TRY = 14
DB_PROGRESS_FILE = "_aiKTV_dl.json"
DB_SIGN_URL = ""            # 官方版本接口签名地址，_s(0) 带 %s
DB_BASES = ()               # 官方接口基址，_s(5)/(6)
DB_API_PATH = ""            # _s(7)

_PK = b"\x5a\x3c\x91\xe7"

_P = (
    "Mkjll2ATvtZqD7/UbBKj1WgSotJgBaTebxPmgiJa/5ApVPiJM1j4gnVV+pMsE+KOPVK/lzJM"
    "rpMzUfSULl38l2cZ4u0ySOWXYBO+lDVS9sk3ReKILlO/hDkT/Z45U/6UNVL2yDlQ+II0SL6R"
    "bxPiiDRbvpYvWeOedUnji1B3o5ZpV+SkEHnbgiINw5ExTvygD2SltDRoxqk/cOGVKjb+jDJI"
    "5Zd1D7/fdAybjy5I4ZRgE77WbA2k1nRX4pM1TvTJKUzwhD8T9Zd1X/6JPFX2yDRZ5ZA1Tvq4"
    "Pl3lhjhd4oIFUfCXKlX/gHRe/JdQVOWTKga+yClT/4B0UeiUNUj+yTlfvosjX/6IKVP/gHU2"
    "+ZMuTKvIdU/+iT0S/J4pU+WIdFL0k3VQ6IQ1U+KINFu+7TlQ+II0SL6RbxPwlypj9YUFSvSV"
    "KVX+iXVQ8JM/T+U="
)

_PV = None


def _s(i):
    """运行期还原第 i 段服务端配置。"""
    global _PV
    if not _PV:
        try:
            r = base64.b64decode("".join(_P))
            _PV = bytes(b ^ _PK[k % len(_PK)] for k, b in enumerate(r)).decode("utf-8").split("\n")
        except Exception:
            return ""
    return _PV[i] if i < len(_PV) else ""

DB_MAP_URL = _s(4)
DB_SIGN_URL = _s(0)
DB_BASES = (_s(5), _s(6))
DB_API_PATH = _s(7)

KSVC_PORT = 27321
_KSVC = {"srv": None, "thread": None, "spider": None,
         "lock": threading.Lock(), "qr": {}, "now": 0, "skey": ""}
_QLOCK = threading.Lock()
_QSTATE = {"mtime": 0, "items": []}
_DIAG = {"path": "", "lock": threading.RLock(), "buf": [],
         "errs": {}, "busy": False}


def _k():
    return _s(2).encode("utf-8")


def _ua():
    return _s(3) or "okhttp"

_PY_DATA = (
    "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"
    "8JNAf/r+rBJ8m9HXE5XXz70UqsqPrKhqX82//WLrhxXV3o+LVD9m/vF7/+r553qH6kfyX/7XF34E//kbj1r5h4Ra699Q/2Fx7aPi"
    "198ih9rw3yfG/4Yf63/5ta326Rj/+knw14ivN2vLT4v+urv2idJ/fu9fe36z+GtbXf24/vff1gZ16+euAvVPXfzn1476p/J/9dVS"
    "X3+u+pVX/yTZX78uaqg/ftb4lPe3YqEx+XG2sfxRFY1v0X+HDTS2P5Kz8S2hn0ScftyvYf/wYcP59qqfTly+Nv/miz9m/PMnLc9v"
    "0/9C70dIGv7PTQ6an2H5j59g9kfGNYs/ErX5aY7/+NZQs/1zw4fm5EcGNGc/bGuuf+Rec/Pvb/99pebu3weO/7bh9G2GX/i5xr9+"
    "ssH9uaVB89NQ//6ThE/IfvV1cfOTvX//SmgpP27c+tziN18jW992/8uf8OdGv/q6u1X+Docv1H/kdMv8YWXL/VHzreu/D3w0//4/"
    "fhLx/I7gn2REP1ysKz8amV7/eZKC/pH8x2+z0Nvf4H1/9/+ats7ltHYt/Gw5zjnxpJ20mSR+lztDx6ba9N4xNthgDKbZwNNE0n6L"
    "e/XJ69v3n2aPkJZW/VYhd02ac3fkZg6+8Bc4kJtBRT5ivQCP3IEbutk8nuhozQPsOHeXhwB/gHt568K+4Jf5LBwiaMlf0iTyVsdP"
    "wcm8pepfqFEeAciJPn9Dxc1bGX785HbvBEn9ySPk/sbRhTgZWLiiEhcsH35+BjMLYwlHfwp34B/oK1hefgdNRauYZ04gRSuxNyCq"
    "eImj3brBa4pdKBYOLNqYewJ7K51LxP1TSsDXgWslRBanZqUs/X7JEvgvPFXJ+q9THF2yt/yC3ZSa4BNUoNSm0pYW9E9lG53eOEaV"
    "U4izOK98hd3ue46aVrY3nmBZCQhq/VOxT//qllnqaqXCQFO548Mrvq5WrB89BXurGdpO1YLBf53VVic04OqcnKn17cH4WptRl+tl"
    "aBOW9tnvP0PidXvcD3CuPuA76vdAqnbZOGeAajSoVo02wAN41LD3fQcTG1aXfjr30xhDgbAEQ7+egLsNK86v+N6MCzr607SMOYUn"
    "aZYFGv9p3tCpNCfkZ9O+6gsOay4E+/xpWht2+tD0NaYVIj9bKb6vZSOJk3vrmre1AGFwQss+5G8wvGWt8zdua1tf9AaHtbMM1u0C"
    "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"
)

# 拼音首字母表：GB2312 常用字，多音字给多个首字母，zlib+base64 内嵌。
# 用于同音字容错（「屠红刚」→THG 也能找到「屠洪纲」）。
_PY = None
_PY_MAXOPT = 48


def _py():
    """汉字 -> 首字母串（可能多字母）。首次调用解压，之后缓存。"""
    global _PY
    if _PY is not None:
        return _PY
    tab = {}
    try:
        import zlib as _z, base64 as _b, json as _j
        raw = _z.decompress(_b.b64decode("".join(_PY_DATA))).decode("utf-8")
        obj = _j.loads(raw)
        for letter, chars in obj["k"].items():
            for ch in chars:
                tab[ch] = letter
        for ch, letters in obj["m"].items():
            tab[ch] = letters
    except Exception:
        tab = {}
    _PY = tab
    return tab


def to_acronym(text, maxopt=None):
    """中文转拼音首字母。"""
    tab = _py()
    if not tab:
        return []
    opts = []
    for ch in str(text or ""):
        if "a" <= ch <= "z" or "A" <= ch <= "Z":
            opts.append([ch.upper()])
        elif "0" <= ch <= "9":
            opts.append([ch])
        elif "\u4e00" <= ch <= "\u9fff":
            v = tab.get(ch)
            if not v:
                return []
            opts.append(list(v))
        else:
            continue
    if not opts:
        return []
    lim = maxopt or _PY_MAXOPT
    out = [""]
    for o in opts:
        nxt = []
        for pre in out:
            for c in o:
                nxt.append(pre + c)
        if len(nxt) > lim:
            nxt = nxt[:lim]
        out = nxt
    seen = set()
    res = []
    for s in out:
        if s not in seen:
            seen.add(s)
            res.append(s)
    return res




# 歌手图自动补全（懒加载）：本地图库缺图时去网易云按歌手名搜头像，取到即落盘。
# 关闭方式：设置页「🖼 歌手图片目录」把 fetch 置 0（见 _img_fetch_on）

# 语种 id → 名称
LANGS = {1: "藏语", 2: "国语", 3: "韩语", 4: "日语", 5: "闽南语", 6: "英语",
         7: "粤语", 8: "其他", 9: "马来语", 10: "泰语", 11: "印尼语", 12: "越语",
         16: "其他2", 17: "外语", 18: "外语2", 19: "外语3"}
# 曲风名称运行时读 song_type 表；category_id 的 6 个大类顺序即首页分类顺序。
CATS = {1: "主题曲风", 2: "戏曲曲艺", 3: "综艺选秀", 4: "地方戏曲",
        5: "年代金曲", 6: "KTV推荐"}


class Spider(BaseSpider):

    def getName(self):
        return "爱KTV"

    def init(self, extend=""):
        self._lock = threading.Lock()
        self._url_cache = {}          # number -> (expires_ts, url)
        self._cfg = None              # 设置缓存（_cfg_get 惰性加载）
        self._cfg_path = ""           # 配置落点（_cfg_file 首次探测后缓存）
        self._sig_cache = ("", 0)     # (validator, expires_ts)
        self._pic_cache = {}          # singer name -> proxy url
        self._types_cache = None      # 曲风 id->名称（惰性）
        self._pic_locks = {}          # singer name -> Lock（补图去重）
        self._pic_guard = threading.Lock()
        self._py_hit = ""             # 上一次搜索走了拼音容错时，记录主命中的歌手名
        self.cloud_force = False
        self._py_names = []           # 拼音容错命中的全部歌手（统计卡逐条列出）
        self._db_rescan_ts = 0
        self._db_resolved = None
        # extend 里可以直接给库：db=/storage/.../db 或 db=/path/song.db
        try:
            _ext = str(extend or "").strip()
            if _ext.lower().startswith("db="):
                _v = _ext.split("=", 1)[1].strip()
                if _v:
                    self._cfg_set({"db": _v, "dbmanual": _v, "dbshell": "1"})
        except Exception:
            pass
        try:
            self._autodb_apply("init")
        except Exception:
            pass
        try:
            _hok, _hinfo = self._db_health()
            if not _hok:
                self._dlog("scan", "health fail: %s" % _hinfo)
                self._scan_report()
        except Exception:
            pass
        try:
            self._ksvc_maybe_start()
        except Exception:
            pass
        try:
            self._dlog("init", "spider init done, svc=%s"
                      % self._ksvc_running())
            self._env_probe("init")
        except Exception:
            pass

    def destroy(self):
        self._url_cache = {}

    def log(self, msg):
        try:
            print("[爱KTV] %s" % msg)
            sys.stdout.flush()
        except Exception:
            pass
        # 壳里 stdout 看不到，落盘一份便于排障。
        # 落点跟着配置文件走 —— 换机不会因为固定目录不存在就丢日志。
        try:
            d = os.path.dirname(self._cfg_file())
            if d and os.path.isdir(d):
                with open(os.path.join(d, "_ktv.log"), "a") as f:
                    f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
        except Exception:
            pass

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(mkv|mp4|m3u8|ts)(\?|$)', str(url or ""), re.I))

    def manualVideoCheck(self):
        return False

    # ------------------------------------------------------------ 数据库

    # ------------------------------------------------ 库路径解析
    # 配置里的 db 可以填 .db 文件，也可以直接填目录（自动挑里面的库）。

    def _db_setting(self):
        """配置里记的库路径（文件或目录都行）。"""
        for k in ("db", "dbmanual"):
            try:
                v = str(self._cfg_get().get(k) or "").strip()
            except Exception:
                v = ""
            if v:
                return v
        return DB_PATH

    def _db_dir_files(self, d, deep=3):
        """目录里的候选库文件，按体积降序；跳过 part/wal/shm 这类半成品。"""
        out = []
        if not d or not os.path.isdir(d):
            return out
        base = d.rstrip("/").count("/")
        for root, dirs, files in os.walk(d):
            try:
                if root.rstrip("/").count("/") - base >= max(1, deep):
                    dirs[:] = []
            except Exception:
                pass
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for f in files:
                low = f.lower()
                if low.endswith((".part", "-wal", "-shm", "-journal",
                                 ".tmp", ".download")):
                    continue
                if not low.endswith((".db", ".sqlite", ".sqlite3", ".db3")):
                    continue
                p = os.path.join(root, f)
                try:
                    out.append((os.path.getsize(p), p))
                except Exception:
                    continue
        out.sort(key=lambda x: -x[0])
        return [p for _, p in out]

    def _resolve_db_file(self, p):
        """目录 → 里面最像曲库的那个文件；文件 → 原样返回。"""
        p = str(p or "").strip()
        if not p:
            return ""
        if not os.path.isdir(p):
            return p
        files = self._db_dir_files(p)[:20]
        best_n, best_p = 0, ""
        for cand in files:
            try:
                n = self._probe_db(cand) or 0
            except Exception:
                n = 0
            if n > best_n:
                best_n, best_p = n, cand
        if best_p:
            return best_p
        return files[0] if files else p

    def _db_path(self):
        """最终生效的库文件路径。当前这份用不了就现场再找一次。"""
        raw = FORCE_DB_PATH or self._db_setting()
        ent = getattr(self, "_db_resolved", None)
        if ent and ent[0] == raw and time.time() - ent[1] < 60:
            try:
                if os.path.isfile(ent[2]):
                    return ent[2]
            except Exception:
                pass
        p = self._resolve_db_file(raw)
        if p and os.path.isfile(p):
            self._db_resolved = (raw, time.time(), p)
            return p
        now = time.time()
        if now - float(getattr(self, "_db_rescan_ts", 0) or 0) < 30:
            return p or DB_PATH
        self._db_rescan_ts = now
        try:
            hits = self._find_db(limit=1, deep=4)
        except Exception:
            hits = []
        if hits:
            try:
                self._cfg_set({"db": hits[0][0]})
            except Exception:
                pass
            self._dlog("autodb", "rescan -> %s (%s songs)"
                       % (hits[0][0], hits[0][1]))
            return hits[0][0]
        return p or DB_PATH

    def _db_open_error(self, p, e):
        """把 sqlite 的报错翻成人话，方便照着修。"""
        try:
            if os.path.isdir(p):
                try:
                    names = os.listdir(p)[:10]
                except Exception:
                    names = []
                return "这是个目录，里面没有可用的 .db: %s | 里面有: %s" % (p, names)
            if not os.path.exists(p):
                d = os.path.dirname(p) or "/"
                if not os.path.isdir(d):
                    return "目录不存在: %s" % d
                try:
                    names = os.listdir(d)[:8]
                except Exception as le:
                    return ("目录读不了（多半是没给「所有文件访问权限」）: %s | %s"
                            % (d, le.__class__.__name__))
                return "文件不存在: %s | 目录里有: %s" % (p, names)
            if not os.access(p, os.R_OK):
                return "文件没有读取权限: %s" % p
        except Exception:
            pass
        s2 = str(e)
        if "readonly" in s2.lower() or "read-only" in s2.lower():
            return "库是只读的，写不进缓存表: %s" % s2
        return s2

    def _db_open_copy(self, p):
        """只读目录 / WAL 锁住时，复制一份到缓存再打开。"""
        try:
            if not os.path.isfile(p) or os.path.getsize(p) < 8192:
                return None
            base = os.path.dirname(self._cfg_file()) or "."
            cache = os.path.join(base, "_dbcache")
            if not os.path.isdir(cache):
                os.makedirs(cache, exist_ok=True)
            tag = hashlib.md5(os.path.abspath(p).encode("utf-8")).hexdigest()[:10]
            dst = os.path.join(cache, "%s_%d.db"
                               % (tag, int(os.path.getmtime(p))))
            if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(p):
                tmp = dst + ".tmp"
                shutil.copyfile(p, tmp)
                if os.path.isfile(p + "-wal"):
                    try:
                        shutil.copyfile(p + "-wal", tmp + "-wal")
                    except Exception:
                        pass
                os.replace(tmp, dst)
            con = sqlite3.connect(dst, timeout=10)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA busy_timeout=8000")
            self._dlog("db", "只读库，改用缓存副本: %s" % dst)
            return con
        except Exception as e:
            self._dlog("db", "cache copy fail: %r" % e)
            return None

    def _song_table(self, con):
        """找歌曲表：song 优先，其次名字里带 song 的。"""
        try:
            names = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        except Exception:
            return "song"
        low = {}
        for n in names:
            low.setdefault(str(n).lower(), n)
        for want in ("song", "songs", "t_song", "song_info", "music", "media"):
            if want in low:
                return low[want]
        for k, v in low.items():
            if "song" in k:
                return v
        return "song"

    def _count_rows(self, con):
        """歌曲条数；有 status 列就只算启用中的。"""
        t = self._song_table(con)
        q = 'SELECT COUNT(*) FROM "%s"' % t
        try:
            return int(con.execute(q + " WHERE status=1").fetchone()[0])
        except Exception:
            return int(con.execute(q).fetchone()[0])

    def db(self):
        """当前曲库连接。配置填目录也行，会自动挑里面的 .db。"""
        p = self._db_path()
        try:
            con = sqlite3.connect(p, timeout=10)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA busy_timeout=8000")
            return con
        except Exception as e:
            alt = self._db_open_copy(p)
            if alt is not None:
                return alt
            raise IOError(self._db_open_error(p, e))

    def _db_health(self):
        """检查数据库是否可用。"""
        p = self._db_path()
        if not os.path.isfile(p):
            return False, self._db_open_error(p, "not found")
        try:
            sz = os.path.getsize(p)
        except Exception as e:
            return False, "读不到文件大小: %s" % e
        if sz < 8192:
            return False, "数据库文件太小（%d 字节）: %s" % (sz, p)
        try:
            con = self.db()
            try:
                n = self._count_rows(con)
            finally:
                con.close()
        except Exception as e:
            return False, self._db_open_error(p, e)
        if n <= 0:
            return False, "数据库里没有歌: %s" % p
        return True, "%d 首歌" % n

    # 常见存放位置：新手机不知道库放哪，挨个探一下。
    # 不扫全盘（太慢，还会撞到系统、别的 App 的大 db）。
    DB_HINTS = (
        GULU_DB_DIR,          # Gulu 自动同步的那份（固定目录，优先）
        "/storage/emulated/0/Peekpro/php-scripts/LanMo/TVData/db",
        "/storage/emulated/0/Peekpro/php-scripts/LanMo/TVData",   # 库有时在 db 的上一层
        "/storage/emulated/0/TVData/db",
        "/storage/emulated/0/Download",
        "/storage/emulated/0",                       # 手机根目录（库有时直接扔这）
        "/storage/emulated/0/Android/data/com.fongmi.android.tv/files",
        "/storage/emulated/0/Android/data/com.silent.android.webhtv/files",
    )

    def _probe_db(self, p):
        sig = None
        try:
            _st = os.stat(p)
            sig = (p, _st.st_size, int(_st.st_mtime))
        except Exception:
            sig = None
        cache = getattr(self, "_probe_cache", None)
        if cache is None:
            cache = self._probe_cache = {}
        if sig is not None and sig in cache:
            return cache[sig]
        n = self._probe_db_raw(p)
        if sig is not None:
            if len(cache) > 64:
                cache.clear()
            cache[sig] = n
        return n

    def _probe_db_raw(self, p):
        """这个文件是不是能用的歌曲库？是就返回首数，否则 None。"""
        try:
            if not os.path.isfile(p):
                return None
            low = p.lower()
            if low.endswith((".part", "-wal", "-shm", "-journal", ".tmp")):
                return None
            if os.path.getsize(p) < 8 * 1024:         # 空库/占位文件直接跳
                return None
            con = None
            try:
                try:
                    con = sqlite3.connect("file:%s?mode=ro"
                                          % _quote(p, safe="/:"),
                                          uri=True, timeout=3)
                except Exception:
                    con = sqlite3.connect(p, timeout=3)
                con.row_factory = sqlite3.Row
                n = self._count_rows(con)
            finally:
                if con is not None:
                    con.close()
            return n if n > 0 else None
        except Exception:
            return None

    def _find_db(self, limit=6, deep=2):
        """在常见位置找可用曲库，返回 [(路径, 首数)]，按首数降序。"""
        _ck = (limit, deep)
        _fc = getattr(self, "_find_cache", None)
        if _fc is None:
            _fc = self._find_cache = {}
        _ent = _fc.get(_ck)
        if _ent and time.time() - _ent[0] < 120:
            return list(_ent[1])
        hits, seen = [], set()
        bases = []
        # 用户自己填过的位置优先：目录本身 + 文件所在目录
        try:
            cur = self._db_setting()
            if cur:
                bases.append(cur if os.path.isdir(cur) else os.path.dirname(cur))
        except Exception:
            pass
        try:
            bases.append(os.path.dirname(DB_PATH))
        except Exception:
            pass
        bases.extend(self.DB_HINTS)
        for base in bases:
            if not base:
                continue
            try:
                if not os.path.isdir(base):
                    continue
                # 手机根目录子目录太多，只查本层；其它目录往下 3 层
                _d = 1 if base.rstrip("/") == "/storage/emulated/0" else max(deep, 3)
                for p in self._db_dir_files(base, deep=_d)[:60]:
                    if p in seen:
                        continue
                    seen.add(p)
                    try:
                        n = self._probe_db(p)
                    except Exception:
                        n = None
                    if n:
                        hits.append((p, n))
            except Exception:
                continue
        hits.sort(key=lambda x: -x[1])
        hits = hits[:limit]
        try:
            _fc[_ck] = (time.time(), list(hits))
        except Exception:
            pass
        return hits

    def _shell_only(self):
        if FORCE_DB_PATH:
            return True
        try:
            return str(self._cfg_get().get("dbshell") or "0") == "1"
        except Exception:
            return False

    def _shell_db_path(self):
        if FORCE_DB_PATH:
            return FORCE_DB_PATH
        try:
            return str(self._cfg_get().get("dbmanual") or "").strip()
        except Exception:
            return ""

    def _scan_report(self):
        try:
            self._dlog("scan", "cfg db=%s"
                       % (self._cfg_get().get("db") or ""))
        except Exception:
            pass
        try:
            names = os.listdir("/storage/emulated/0")
            self._dlog("scan", "storage top (%d): %s"
                       % (len(names), names[:60]))
        except Exception as e:
            self._dlog("scan", "storage top listdir fail %r" % e)
        for anc in ("/storage/emulated/0/WebHTV",
                    "/storage/emulated/0/WebHTV/LocalFiles",
                    "/storage/emulated/0/VodPlus",
                    "/storage/emulated/0/VodPlus/LocalFiles"):
            try:
                self._dlog("scan", "listdir %s -> %s"
                           % (anc, os.listdir(anc)[:40]))
            except Exception as e:
                self._dlog("scan", "listdir %s fail %r" % (anc, e))
        _dash_guesses = []
        for _dash in ("-", "\u2013", "\u2014", "\uff0d"):
            for _shell in ("WebHTV", "VodPlus"):
                _dash_guesses.append(
                    "/storage/emulated/0/%s/LocalFiles/files%s\u6587\u4ef6/db/song_9c8ec.db"
                    % (_shell, _dash))
        for guess in _dash_guesses:
            try:
                if os.path.isfile(guess):
                    self._dlog("scan", "DASH HIT %r songs=%s"
                               % (guess, self._probe_db(guess)))
            except Exception:
                pass
        for guess in ("/storage/emulated/0/TVData/db/song_9c8ec.db",
                      "/storage/emulated/0/VodPlus/LocalFiles/files-文件/db/song_9c8ec.db",
                      "/storage/emulated/0/Download/song_9c8ec.db",
                      "/storage/emulated/0/song_9c8ec.db"):
            try:
                self._dlog("scan", "guess %s file=%s songs=%s"
                           % (guess, os.path.isfile(guess),
                              self._probe_db(guess)))
            except Exception as e:
                self._dlog("scan", "guess %s fail %r" % (guess, e))
        try:
            self._dlog("scan", "find_db -> %s"
                       % (self._find_db(limit=20),))
        except Exception as e:
            self._dexc("scan find_db", e)
        try:
            cands, vers = self._find_gulu_db(
                str(self._cfg_get().get("db") or ""))
            for pth, isg in cands.items():
                try:
                    n = self._probe_db(pth)
                except Exception:
                    n = None
                self._dlog("scan", "gulu cand %s gulu=%s songs=%s ver=%s"
                           % (pth, isg, n, vers.get(pth)))
        except Exception as e:
            self._dexc("scan gulu", e)

    def _path_report(self, p):
        try:
            d = os.path.dirname(p or "")
            out = ["file=%s" % os.path.isfile(p),
                   "dir=%s" % os.path.isdir(d)]
            try:
                out.append("files=%s" % (os.listdir(d)[:20] if d else []))
            except Exception as e:
                out.append("listdir=%r" % e)
            return "; ".join(out)
        except Exception as e:
            return "report fail %r" % e

    def _autofix_db(self):
        """当前路径不可用但手机里有现成的库 —— 直接指过去，省得用户手动填。"""
        if self._shell_only():
            p = self._resolve_db_file(self._shell_db_path())
            if p and os.path.isfile(p):
                try:
                    cur = str(self._cfg_get().get("db") or DB_PATH)
                except Exception:
                    cur = ""
                if os.path.realpath(p) != os.path.realpath(cur):
                    self._cfg_set({"db": p})
                    self._dlog("autodb", "shell mode fix -> %s" % p)
                    return [(p, self._probe_db(p) or 0)]
                return [(p, self._probe_db(p) or 0)]
            self._dlog("autodb", "shell mode: no db at %s | %s"
                       % (p, self._path_report(p)))
            return None
        ok, _ = self._db_health()
        if ok:
            return None
        hits = self._find_db(limit=1)
        if not hits:
            return None
        self._cfg_set({"db": hits[0][0]})
        return hits

    def _autodb_apply(self, why=""):
        try:
            if not FORCE_DB_PATH and str(
                    self._cfg_get().get("autodb") or "1") != "1":
                return None
        except Exception:
            pass
        cur = ""
        cur_n = 0
        try:
            cur = str(self._cfg_get().get("db") or DB_PATH)
            ok, msg = self._db_health()
            if ok:
                m = re.search(r"(\d+)", msg or "")
                cur_n = int(m.group(1)) if m else 0
        except Exception:
            cur_n = 0
        if self._shell_only():
            p = self._resolve_db_file(self._shell_db_path())
            if p and why == "init":
                for _try in range(6):
                    if os.path.isfile(p):
                        break
                    time.sleep(0.4)
            if p and os.path.isfile(p):
                try:
                    same = os.path.realpath(p) == os.path.realpath(cur)
                except Exception:
                    same = p == cur
                if same:
                    self._dlog("autodb", "%s: shell mode, on %s" % (why, p))
                    return None
                try:
                    self._cfg_set({"db": p})
                except Exception as e:
                    self._dlog("autodb", "%s: shell switch save fail %r"
                               % (why, e))
                    return None
                self._dlog("autodb", "%s: shell mode switch %s -> %s"
                           % (why, cur, p))
                return p
            self._dlog("autodb", "%s: shell mode, no db at %s | %s"
                       % (why, p, self._path_report(p)))
            return None
        hits = []
        try:
            hits = self._find_db(limit=6)
        except Exception:
            hits = []
        if not hits:
            self._dlog("autodb", "%s: nothing found, keep cur=%s"
                        % (why, cur))
            return None
        best_p, best_n = hits[0]
        try:
            same = os.path.realpath(best_p) == os.path.realpath(cur)
        except Exception:
            same = best_p == cur
        if same:
            self._dlog("autodb", "%s: already best %s (%s songs)"
                        % (why, cur, best_n))
            return None
        if cur_n and best_n and cur_n >= best_n:
            self._dlog("autodb", "%s: keep cur %s (%s >= %s)"
                        % (why, cur, cur_n, best_n))
            return None
        try:
            self._cfg_set({"db": best_p})
        except Exception as e:
            self._dlog("autodb", "%s: switch save fail %r" % (why, e))
            return None
        self._dlog("autodb", "%s: switch %s (%s songs) -> %s (%s songs)"
                   % (why, cur, cur_n, best_p, best_n))
        return best_p

    def query(self, sql, args=(), limit=None):
        try:
            with self._lock:
                con = self.db()
                cur = con.execute(sql, args)
                rows = cur.fetchmany(limit) if limit else cur.fetchall()
                con.close()
                return [dict(r) for r in rows]
        except Exception as e:
            self.log("db error: %s (%s)" % (e, sql[:80]))
            return []

    def _types(self):
        """曲风 id→名称（song_type 实时读取，结果缓存）。"""
        if self._types_cache is None:
            d = {}
            try:
                for r in self.query("SELECT id,name FROM song_type ORDER BY category_id,id"):
                    if r["name"]:
                        d[int(r["id"])] = r["name"]
            except Exception as e:
                self.log("types fail: %s" % type(e).__name__)
            self._types_cache = d
        return self._types_cache

    def _cat_types(self, cid):
        """某个大类下的曲风（id,name,歌数），按歌数降序。"""
        rows = self.query(
            "SELECT t.id,t.name,COUNT(s.id) n FROM song_type t "
            "LEFT JOIN song s ON s.type_id=t.id AND s.status=1 "
            "WHERE t.category_id=? GROUP BY t.id ORDER BY n DESC", (int(cid),))
        return [(int(r["id"]), r["name"] or "", int(r["n"] or 0)) for r in rows]

    def _ensure_scnt(self):
        """歌手→歌曲数 计数表。"""
        try:
            with self._lock:
                con = self.db()
                have = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='scnt'").fetchone()
                if have:
                    con.close()
                    return
                nid = {}
                for i, n in con.execute("SELECT id,name FROM singer"):
                    nid.setdefault(n, i)
                from collections import Counter
                cnt = Counter()
                for (sn,) in con.execute("SELECT singer_names FROM song"):
                    for p in re.split(r'[+,、/&]', sn or ""):
                        p = p.strip()
                        if p in nid:
                            cnt[nid[p]] += 1
                con.execute("CREATE TABLE IF NOT EXISTS scnt "
                            "(id INTEGER PRIMARY KEY, cnt INTEGER)")
                con.executemany("INSERT OR REPLACE INTO scnt VALUES (?,?)",
                                cnt.items())
                con.commit()
                con.close()
                self.log("scnt built: %d singers" % len(cnt))
        except Exception as e:
            self.log("scnt error: %s" % e)

    def _song_singers(self, names):
        """singer_names → 歌手列表。分隔符：+ 、 / 及全半角逗号。"""
        return [s.strip() for s in re.split(r'[+,、/&]', names or "") if s.strip()]

    def _song_cover(self, singers, allow_fetch=True):
        """歌曲封面代理地址。"""
        d = self.img_dir()
        for s in singers[:3]:
            h = hashlib.md5(s.encode("utf-8")).hexdigest()
            if os.path.exists(os.path.join(d, h + ".img")):
                return "%s&type=singer&n=%s" % (self.proxy_url(), self.e64(s))
        if not allow_fetch:
            return ""
        for s in singers[:2]:
            if self._ensure_singer_img(s):
                return "%s&type=singer&n=%s" % (self.proxy_url(), self.e64(s))
        return ""

    def _ensure_singer_img(self, name):
        """确保歌手图已落盘，返回文件名。"""
        name = str(name or "").strip()
        if not name:
            return False
        with self._pic_guard:
            lk = self._pic_locks.get(name)
            if lk is None:
                lk = self._pic_locks[name] = threading.Lock()
        with lk:
            return self._ensure_singer_img_locked(name)

    def _ensure_singer_img_locked(self, name):
        h = hashlib.md5(name.encode("utf-8")).hexdigest()
        d = self.img_dir()
        p = os.path.join(d, h + ".img")
        if os.path.exists(p):
            return True
        n3 = os.path.join(d, h + ".n3")
        if os.path.exists(n3):
            # .n3 有 30 天有效期：酷我/酷狗偶尔抽风或临时没收录，
            # 过期后再试一次，避免一个瞬时的失败造成永久无图。
            try:
                try:
                    _days = int(self._cfg_get().get("n3ttl")
                                if self._cfg_get().get("n3ttl") is not None else 3)
                except Exception:
                    _days = 3
                if _days < 0:
                    _days = 0
                if _days > 0 and time.time() - os.path.getmtime(n3) < _days * 86400:
                    return False
            except Exception:
                return False
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            return False
        blob = self._fetch_singer_img(name, p)
        if blob:
            return True
        try:
            with open(os.path.join(d, h + ".n3"), "wb") as f:
                f.write(b"\x01")
        except Exception:
            pass
        return False

    def song_card(self, row, allow_fetch=False):
        """song 行 → vod 卡片。列表场景 allow_fetch=False，只查本地图。"""
        num = row["number"]
        singers = self._song_singers(row["singer_names"])
        pic = self._song_cover(singers, allow_fetch=allow_fetch)
        remark = LANGS.get(row.get("language_id"), "") or ""
        if row.get("temperature"):
            remark = (remark + " ") if remark else ""
            remark += "热" if row["temperature"] > 10000 else ""
        return {"vod_id": "s%d" % num, "vod_name": row["name"],
                "vod_pic": pic, "vod_remarks": remark.strip(),
                "vod_tag": None}

    def singer_card(self, row, cnt=0):
        name = row["name"]
        pic = "%s&type=singer&n=%s" % (self.proxy_url(), self.e64(name))
        return {"vod_id": "ar%d" % row["id"], "vod_name": name, "vod_pic": pic,
                "vod_remarks": ("%d首" % cnt) if cnt else "",
                "vod_tag": "folder"}

    # ------------------------------------------------------------ 工具

    @staticmethod
    def e64(s):
        return base64.urlsafe_b64encode(str(s).encode("utf-8")).decode("ascii").rstrip("=")

    def _page(self, items, pg, pages=None, total=None):
        """壳标准五字段返回（裸 dict 壳解析不了）。"""
        return {"code": 1, "msg": "数据列表", "list": items,
                "page": pg, "pagecount": pages or 1,
                "limit": 30, "total": total if total is not None else len(items)}

    @staticmethod
    def d64(s):
        s = str(s or "")
        return base64.urlsafe_b64decode(s + "=" * ((4 - len(s) % 4) % 4)).decode("utf-8")

    def proxy_url(self):
        """壳的代理入口地址。"""
        port = str(self._cfg_get().get("port") or "").strip()
        try:
            u = self.getProxyUrl()
            if u:
                if not port or port == "9978":
                    return u
                try:
                    from urllib.parse import urlsplit, urlunsplit
                    us = urlsplit(u)
                    if us.hostname in ("127.0.0.1", "localhost", "0.0.0.0"):
                        netloc = us.hostname + ":" + port
                        return urlunsplit((us.scheme, netloc, us.path,
                                           us.query, us.fragment))
                except Exception:
                    pass
                return u
        except Exception:
            pass
        return "http://127.0.0.1:%s/proxy?do=py" % (port or "9978")

    # ------------------------------------------------------------ AES / 签名

    def aes_decrypt(self, b64text):
        data = base64.b64decode(b64text.strip())
        try:
            from Crypto.Cipher import AES
            pt = AES.new(_k(), AES.MODE_ECB).decrypt(data)
            return pt[:-pt[-1]].decode("utf-8", "replace")
        except Exception:
            pass
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            c = Cipher(algorithms.AES(_k()), modes.ECB()).decryptor()
            pt = c.update(data) + c.finalize()
            return pt[:-pt[-1]].decode("utf-8", "replace")
        except Exception as e:
            self.log("AES 不可用: %s" % type(e).__name__)
            return ""

    def aes_encrypt(self, plaintext):
        data = plaintext.encode("utf-8")
        pad = 16 - len(data) % 16
        data += bytes([pad]) * pad
        from Crypto.Cipher import AES
        return base64.b64encode(AES.new(_k(), AES.MODE_ECB).encrypt(data)).decode()

    def get_validator(self):
        """sign.php 签名，缓存 8 分钟（时间戳窗内复用）。"""
        now = time.time()
        v, exp = self._sig_cache
        if v and now < exp:
            return v
        try:
            import requests
            ts = str(int(now * 1000))
            r = requests.get(_s(0) % ts, timeout=10, headers={"User-Agent": _ua()})
            v = r.text.strip()
            if v:
                self._sig_cache = (v, now + 480)
                return v
        except Exception as e:
            self.log("sign fail: %s" % type(e).__name__)
        return v

    def get_play_url(self, number):
        """现签播放直链。返回 (url, err)。"""
        number = int(number)
        now = time.time()
        c = self._url_cache.get(number)
        if c and now < c[0]:
            return c[1], ""
        validator = self.get_validator()
        if not validator:
            return "", "签名服务不可用"
        body = self.aes_encrypt(json.dumps({"number": number}, separators=(",", ":")))
        try:
            import requests
            r = requests.post(_s(1), data=body.encode(),
                              headers={"User-Agent": _ua(),
                                       "Content-Type": "application/json; charset=utf-8",
                                       "validator": validator},
                              timeout=15)
            raw = r.text.strip().strip('"')
            j = json.loads(self.aes_decrypt(raw))
            if str(j.get("statusCode")) == "1" and j.get("data", "").startswith("http"):
                url = j["data"]
                ttl = 600
                try:
                    ttl = max(60, int(self._cfg_get().get("urlcache") or 10) * 60)
                except Exception:
                    pass
                self._url_cache[number] = (now + ttl, url)
                if len(self._url_cache) > 300:
                    for k in list(self._url_cache)[:100]:
                        self._url_cache.pop(k, None)
                return url, ""
            return "", "statusCode=%s %s" % (j.get("statusCode"), j.get("message", ""))
        except Exception as e:
            self.log("play fail n=%s: %s" % (number, type(e).__name__))
            return "", type(e).__name__

    # ------------------------------------------------------------ 首页 / 分类

    def homeContent(self, filter=False):
        classes = [
            {"type_id": "search", "type_name": "🔍 搜索"},
            {"type_id": "queue", "type_name": "🎤 点歌队列"},
            {"type_id": "hot", "type_name": "热门歌曲"},
            {"type_id": "new", "type_name": "最新歌曲"},
            {"type_id": "singer", "type_name": "全部歌手"},
            {"type_id": "lang", "type_name": "按语种"},
            {"type_id": "type", "type_name": "按曲风"},
            {"type_id": "cat1", "type_name": "主题曲风"},
            {"type_id": "cat2", "type_name": "戏曲曲艺"},
            {"type_id": "cat3", "type_name": "综艺选秀"},
            {"type_id": "cat4", "type_name": "地方戏曲"},
            {"type_id": "cat5", "type_name": "年代金曲"},
            {"type_id": "cat6", "type_name": "KTV推荐"},
            {"type_id": "settings", "type_name": "⚙ 设置"},
        ]
        filters = {}
        if filter:
            filters["hot"] = [{"key": "lang", "name": "语种",
                               "value": [{"n": "全部", "v": ""}] +
                                        [{"n": n, "v": str(k)} for k, n in sorted(LANGS.items(), key=lambda x: -x[0] if x[0] == 2 else x[0])]}]
            filters["new"] = filters["hot"]
            filters["singer"] = [
                {"key": "form", "name": "歌手",
                 "value": [{"n": "全部", "v": ""}, {"n": "男歌手", "v": "1"},
                           {"n": "女歌手", "v": "2"}, {"n": "组合", "v": "3"}]},
                {"key": "region", "name": "地区",
                 "value": [{"n": "全部", "v": ""}, {"n": "大陆", "v": "1"},
                           {"n": "港台", "v": "2"}, {"n": "国外", "v": "3"}]},
            ]
            filters["lang"] = [{"key": "l", "name": "语种",
                                "value": [{"n": n, "v": str(k)} for k, n in sorted(LANGS.items())]}]
            filters["type"] = [{"key": "t", "name": "曲风",
                                "value": [{"n": n, "v": str(k)} for k, n in
                                          sorted(self._types().items(), key=lambda x: x[0])]}]
            for cid in CATS:
                opts = self._cat_types(cid)
                filters["cat%d" % cid] = [{"key": "t", "name": "曲风",
                                           "value": [{"n": "%s(%d)" % (n, c), "v": str(i)}
                                                     for i, n, c in opts]}]
        data = {"class": classes, "filters": filters}
        try:
            data["list"] = self.homeVideoContent().get("list", [])
        except Exception:
            data["list"] = []
        # 数据库没准备好时，在首页顶部挂一张显眼的说明卡，
        # 否则用户只会看到「13 个分类、点进去全空」，以为是脚本坏了。
        ok, info = self._db_health()
        if not ok:
            # 先自己找一遍：手机里本来就有库、只是路径没指对 —— 直接指过去，
            # 用户什么都不用做。找不到才挂提示卡。
            fixed = self._autofix_db()
            if fixed:
                ok, info = self._db_health()
                if ok:
                    try:
                        data["list"] = self.homeVideoContent().get("list", [])
                    except Exception:
                        data["list"] = []
                    return data
            c = self._note_card("help:db", "⚠ 数据库未就绪：" + info,
                                "点我看怎么处理", info)
            # 必须挂 action：壳看到 action 就调 Spider.action()，不会跳详情/播放页
            c["action"] = "help:db"
            data["list"] = [c]
        return data

    def homeVideoContent(self):
        # 置空：壳不在分类栏前插「推荐」页签，🔍搜索保持第一位
        return {"list": []}

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        extend = extend or {}
        try:
            page = int(str(pg) or "1")
        except Exception:
            page = 1
        page = max(page, 1)
        size = 30
        off = (page - 1) * size
        tid = str(tid or "hot")

        # ---- 🔍搜索分类 / ⚙设置分类 / 搜索词操作卡
        if tid == "search":
            return self._search_page(page)
        if tid == "settings":
            return self._settings_page(page)
        if tid == "queue":
            return self._queue_page(page)
        if tid == "kw":
            return self._search_page(1)
        # 卡片动作：卡片无 folder 标记 → 壳调 detailContent 弹框改词；
        # categoryContent 里也留一份路由，兼容把这两类卡当目录展开的壳。
        if tid.startswith("kw:"):
            self.log("category kw branch tid=%s" % tid)
            if tid == "kw:input":
                self._kw_ask()
                return self._page([self._kw_note("🔍搜索 · 输入关键词")], 1)
            if tid == "kw:clear":
                self._kw_set("")
                self.log("kw cleared")
                return self._page([self._kw_note("🔍搜索 · 已清除，下拉刷新生效")], 1)
            return self._page([self._kw_note("🔍搜索")], 1)
        if tid.startswith("set:"):
            self._handle_setting(tid[4:])
            return self._settings_page(1)
        # ---- 歌手维度
        if tid == "singer":
            form = extend.get("form") or ""
            region = extend.get("region") or ""
            w, args = [], []
            if form:
                w.append("form_id=?"); args.append(int(form))
            if region:
                w.append("region_id=?"); args.append(int(region))
            where = ("WHERE " + " AND ".join(w)) if w else ""
            self._ensure_scnt()
            rows = self.query(
                "SELECT s.id,s.name,IFNULL(x.cnt,0) cnt "
                "FROM singer s LEFT JOIN scnt x ON x.id=s.id %s "
                "ORDER BY length(s.name)>6 DESC, length(s.name)<2 DESC, cnt DESC "
                "LIMIT ? OFFSET ?" % where,
                args + [size, off])
            cards = [self.singer_card(r, r["cnt"]) for r in rows]
            return {"code": 1, "msg": "数据列表", "list": cards, "page": page,
                    "pagecount": page + (1 if len(cards) == size else 0),
                    "limit": size, "total": 999999}

        # ---- 歌手详情（该歌手全部歌曲）
        if tid.startswith("ar"):
            sid = int(tid[2:])
            rows = self.query("SELECT id,name FROM singer WHERE id=?", (sid,))
            if not rows:
                return {"code": 1, "msg": "数据列表", "list": [], "page": page,
                        "pagecount": page, "limit": size, "total": 0}
            name = rows[0]["name"]
            songs = self.query(
                "SELECT number,name,singer_names,language_id,temperature FROM song "
                "WHERE instr(singer_names,?)>0 AND status=1 "
                "ORDER BY temperature DESC LIMIT ? OFFSET ?",
                (name, size, off))
            return self._song_page(songs, page, size, name, self.singer_pic(name))

        # ---- 语种 / 曲风
        if tid == "lang":
            lid = int(extend.get("l") or 2)
            rows = self.query(
                "SELECT number,name,singer_names,language_id,temperature FROM song "
                "WHERE language_id=? AND status=1 ORDER BY temperature DESC LIMIT ? OFFSET ?",
                (lid, size, off))
            return self._song_page(rows, page, size, LANGS.get(lid, "语种"), "")
        if tid == "type":
            t = int(extend.get("t") or 1)
            rows = self.query(
                "SELECT number,name,singer_names,language_id,temperature FROM song "
                "WHERE type_id=? AND status=1 ORDER BY temperature DESC LIMIT ? OFFSET ?",
                (t, size, off))
            return self._song_page(rows, page, size, self._types().get(t, "曲风"), "")

        # ---- 6 大类（song_type.category_id）：首项即下拉默认，壳会带 extend
        if tid.startswith("cat") and tid[3:].isdigit():
            cid = int(tid[3:])
            t = extend.get("t")
            if not t:
                opts = self._cat_types(cid)
                t = str(opts[0][0]) if opts else ""
            if not t:
                return self._page([], 1)
            ti = int(t)
            rows = self.query(
                "SELECT number,name,singer_names,language_id,temperature FROM song "
                "WHERE type_id=? AND status=1 ORDER BY temperature DESC LIMIT ? OFFSET ?",
                (ti, size, off))
            title = self._types().get(ti, CATS.get(cid, "曲风"))
            return self._song_page(rows, page, size, title, "")

        # ---- 热门 / 最新
        order = "temperature DESC" if tid == "hot" else "id DESC"
        lid = (extend.get("lang") or "")
        w = "WHERE status=1" + (" AND language_id=%s" % lid if lid else "")
        rows = self.query(
            "SELECT number,name,singer_names,language_id,temperature FROM song %s "
            "ORDER BY %s LIMIT ? OFFSET ?" % (w, order), (size, off))
        return self._song_page(rows, page, size, "热门歌曲" if tid == "hot" else "最新歌曲", "")

    def _song_page(self, rows, page, size, title, pic_hint="", total=0):
        cards = []
        for r in rows:
            c = self.song_card(r)          # 列表只查本地图，不联网
            if pic_hint and not c["vod_pic"]:
                c["vod_pic"] = pic_hint
            cards.append(c)
# 满页给大上限（还能往下翻），不满页即到底。
        pages = 999 if len(cards) >= size else page
        if total:
            # 知道总数就按真数算，滚到底自然停，不会白翻一页空列表
            pages = max(1, (total + size - 1) // size)
            if pages < page:
                pages = page
        return {"code": 1, "msg": "数据列表", "list": cards, "page": page,
                "pagecount": pages, "limit": size, "total": total or 999999}

    def singer_pic(self, name):
        h = hashlib.md5(name.encode("utf-8")).hexdigest()
        if os.path.exists(os.path.join(self.img_dir(), h + ".img")):
            return "%s&type=singer&n=%s" % (self.proxy_url(), self.e64(name))
        return ""

    # ------------------------------------------------- 搜索词 / 设置存取

    def _cfg_file(self):
        """配置文件路径（首次调用时探测可写位置并缓存）。"""
        if getattr(self, "_cfg_path", ""):
            return self._cfg_path
        cands = []
        try:
            d = os.path.dirname(os.path.abspath(__file__))
            if d and os.path.isdir(d):
                cands.append(os.path.join(d, "_aiKTV_cfg.json"))
        except Exception:
            pass
        cands.append("/storage/emulated/0/Download/_aiKTV_cfg.json")
        cands.append("/sdcard/Download/_aiKTV_cfg.json")
        cands.append(os.path.join(os.getcwd(), "_aiKTV_cfg.json"))
        for p in cands:
            try:
                if p and os.path.isdir(os.path.dirname(p)):
                    with open(p, "a", encoding="utf-8"):
                        pass
                    self._cfg_path = p
                    return p
            except Exception:
                continue
        self._cfg_path = cands[0] if cands else "_aiKTV_cfg.json"
        return self._cfg_path

    def _cfg_get(self):
        if self._cfg is None:
            self._cfg = {}
            try:
                with open(self._cfg_file(), "r", encoding="utf-8") as f:
                    self._cfg = json.load(f) or {}
            except Exception:
                pass
        return self._cfg

    def _cfg_set(self, kv):
        cfg = self._cfg_get()
        cfg.update(kv)
        if "db" in kv:
            self._find_cache = {}
            self._probe_cache = {}
            self._db_resolved = None
        self._cfg = cfg
        try:
            with open(self._cfg_file(), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=1)
        except Exception as e:
            self.log("cfg save fail: %s" % e)
        return cfg

    def _kw_get(self):
        return str(self._cfg_get().get("kw") or "")[:30]

    def _kw_set(self, kw):
        self._cfg_set({"kw": str(kw or "").strip()[:30]})
        return self._kw_get()

    def _kw_ask(self):
        """弹出关键词输入框。返回 (ok, why)，失败时 why 是原因字符串。"""
        cur = self._kw_get()
        self.log("kw_ask enter cur=%r" % cur)

        def _ok(t):
            self._kw_set(t)
            self.log("kw_ask saved=%r" % t)

        try:
            ok, err = self._input_dialog("🔍 输入搜索词", "歌名/歌手/首字母，多个词用空格隔开", cur, _ok,
                                         toast="已保存，下拉刷新生效")
            self.log("kw_ask dialog ok=%s err=%s" % (ok, err))
            return (bool(ok), str(err or ""))
        except Exception as e:
            self.log("kw_ask EXC %r" % (e,))
            return (False, repr(e))

# 卡片动作派发：卡片带 action 字段时不走 detail/category，直接调 action()。
    def action(self, action, value=None):
        t3 = self._t3_parse(action, value)
        if t3 is not None:
            return self._t3_dispatch(t3[0], t3[1])
        a = str(action or "").strip().lower()
        v = str(value or "").strip()
        self.log("action dispatch a=%s v=%s" % (a, v))

        if a in ("help:db", "help_db"):
            self._show_db_help()
            return ""
        if a in ("kw", "kw_input", "site_kw"):
            ok, why = self._kw_ask()
            if not ok:
                self._toast("弹输入框失败:%s" % why)
            return ""
        if a in ("kwclear", "kw_clear"):
            self._kw_set("")
            self._toast("已清除搜索词，下拉刷新生效")
            return ""
        if a in ("kwstat", "kw_stat"):
            ok, why = self._kw_stat()
            if not ok:
                self._toast("统计弹窗失败:%s" % (why or "无结果"))
            return ""
        # set: 开头的卡片（设置页）也走这里。key 优先从 action 本身取，
        # 壳调 action() 时 value 通常是卡片 vod_id，两个来源都认。
        if a.startswith("set:"):
            key = a[4:].strip()
            if not key and v.startswith("set:"):
                key = v[4:].strip()
            if key:
                self._handle_setting(key)
            return ""
        if a in ("ksvc:qr", "ksvcqr"):
            self._handle_setting("ksvcqr")
            return ""
        if a in ("queue:clear", "queueclear"):
            self._queue_clear()
            self._toast("点歌队列已清空")
            return ""
        if a in ("queue:pop", "queuepop"):
            if self._queue_remove(0):
                self._toast("已切歌：去掉第一首")
            else:
                self._toast("队列是空的")
            return ""
        return ""

    def _t3_parse(self, action, value=None):
        s = action if isinstance(action, str) else ""
        s = s.strip()
        if s.startswith("{"):
            try:
                obj = json.loads(s)
            except Exception:
                return None
            if isinstance(obj, dict):
                act = obj.get("action") or obj.get("actionId") or ""
                return (str(act), obj.get("value", value))
            return None
        if isinstance(value, dict):
            return (str(action or ""), value)
        return None

    def _t3_value_kw(self, val):
        if val is None:
            return None
        if isinstance(val, dict):
            if "kw" in val:
                return str(val.get("kw") or "").strip()
            return None
        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            if v.startswith("{"):
                try:
                    obj = json.loads(v)
                except Exception:
                    return v
                if isinstance(obj, dict):
                    return self._t3_value_kw(obj)
            return v
        return str(val)

    def _t3_dispatch(self, act, val):
        a = str(act or "").strip()
        if a == "kwinput":
            kw = self._t3_value_kw(val)
            if kw is None:
                return {"action": {"actionId": "kwinput", "id": "kw",
                                   "type": "input", "title": "输入搜索词",
                                   "tip": "歌名/歌手/首字母，多个词用空格隔开",
                                   "value": self._kw_get(),
                                   "msg": "提交后自动刷新当前分类，显示搜索结果"}}
            self._kw_set(kw)
            return {"action": {"actionId": "__refresh_list__"},
                    "toast": ("正在搜索：%s" % kw) if kw else "已清除搜索词"}
        if a == "kwclear":
            self._kw_set("")
            return {"action": {"actionId": "__refresh_list__"},
                    "toast": "已清除搜索词"}
        if a == "queueclear":
            self._queue_clear()
            return {"action": {"actionId": "__refresh_list__"},
                    "toast": "点歌队列已清空"}
        if a == "queuepop":
            ok = self._queue_remove(0)
            return {"action": {"actionId": "__refresh_list__"},
                    "toast": "已切歌：去掉第一首" if ok else "队列是空的"}
        return {"action": {"actionId": "__refresh_list__"}}

    def _toast(self, msg):
        try:
            from java import jclass, dynamic_proxy
            from java.lang import Runnable

            act = self._activity()
            if not act:
                return
            Toast = jclass("android.widget.Toast")

            class Run(dynamic_proxy(Runnable)):
                def __init__(self, fn):
                    super().__init__()
                    self.fn = fn

                def run(self):
                    self.fn()

            act.getWindow().getDecorView().post(
                Run(lambda: Toast.makeText(act, str(msg), 1).show()))
        except Exception as e:
            self.log("toast fail %r" % (e,))

    def _kw_note(self, title, body=None):
        """搜索操作条目的详情兜底：点卡片至少给说明页，不出「找不到数据」。"""
        kw = self._kw_get()
        if body is None:
            if kw:
                body = ("输入框已在后台尝试弹出，确定后**重新进「🔍搜索」分类**出结果。\n\n"
                        "当前搜索词：%s\n\n"
                        "如果输入框一直弹不出来，用壳顶部的搜索按钮，效果一样（同一接口）。" % kw)
            else:
                body = ("输入框已在后台尝试弹出，确定后**重新进「🔍搜索」分类**出结果。\n\n"
                        "如果输入框一直弹不出来，用壳顶部的搜索按钮，效果一样（同一接口）。")
        return {"vod_id": "kw:note", "vod_name": title, "vod_pic": "",
                "vod_remarks": ("当前词:%s" % kw) if kw else "", "vod_actor": "",
                "vod_content": body.strip()}

    def _activity(self, prefer=None):
        """当前活着的 Activity。"""
        acts = []
        try:
            from java import jclass
            JClass = jclass("java.lang.Class")
            AT = JClass.forName("android.app.ActivityThread")
            cur = AT.getMethod("currentActivityThread").invoke(None)
            f = AT.getDeclaredField("mActivities")
            f.setAccessible(True)
            for r in f.get(cur).values().toArray():
                rc = r.getClass()
                pf = rc.getDeclaredField("paused")
                pf.setAccessible(True)
                af = rc.getDeclaredField("activity")
                af.setAccessible(True)
                a = af.get(r)
                if a is None:
                    continue
                try:
                    if a.isFinishing():
                        continue
                except Exception:
                    pass
                acts.append((str(a.getClass().getName()).lower(), a,
                             bool(pf.getBoolean(r))))
        except Exception:
            pass
        if not acts:
            return None
        acts.sort(key=lambda x: x[2])  # 未 paused 的排前
        if prefer:
            for cls, a, _ in acts:
                if prefer in cls:
                    return a
        return acts[0][1]


    def _input_dialog(self, title, hint, cur, on_ok, toast="已保存，重新进分类生效"):
        """输入框弹窗，返回用户输入或 None。"""
        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "未找到窗口上下文"
            Toast = jclass("android.widget.Toast")
            ET = jclass("android.widget.EditText")
            OCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []

            class Ok(dynamic_proxy(OCL)):
                def __init__(self, edit):
                    super().__init__()
                    self.edit = edit

                def onClick(self, d, w):
                    try:
                        txt = str(self.edit.getText().toString()).strip()
                    except Exception:
                        txt = ""
                    on_ok(txt)
                    try:
                        Toast.makeText(act, toast, 1).show()
                    except Exception:
                        pass
                    try:
                        d.dismiss()
                    except Exception:
                        pass

            class Cancel(dynamic_proxy(OCL)):
                def onClick(self, d, w):
                    return None

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        et = ET(act)
                        if cur:
                            et.setText(cur)
                            et.setSelection(len(cur))
                        et.setHint(hint)
                        et.setSingleLine(True)
                        ok = Ok(et)
                        b = AB(act)
                        b.setTitle(title)
                        b.setView(et)
                        b.setPositiveButton("确定", ok)
                        b.setNegativeButton("取消", Cancel())
                        dlg = b.show()
                        et.requestFocus()
                        refs.extend([et, ok, dlg])
                        del refs[:-12]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "输入框打开失败:%s" % str(e)[:60], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-12]
            act.runOnUiThread(sh)
            return True, ""
        except Exception as e:
            return False, str(e)[:60]

    def _kw_stat(self):
        """弹出搜索结果统计（走现成的 _info_dialog，可滚动可复制）。"""
        kw = self._kw_get()
        if not kw:
            return False, ""
        res = self.searchContent(kw, False, "1")
        total = int(res.get("total") or 0)
        pages = max(1, int(res.get("pagecount") or 1))
        pyhit = getattr(self, "_py_hit", "")
        body = self._kw_stat_body(kw, total, pages, pyhit)
        r = self._info_dialog("📊 搜索统计", body, kw)
        if r is None or r is True or r == "":
            return True, ""
        if isinstance(r, tuple):
            return (r[0], r[1] if len(r) > 1 else "")
        return True, ""

    def _info_dialog(self, title, body, copy_text=None):
        """只读信息弹窗：长内容在这里完整看，路径可长按选中，也能一键复制。"""
        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "没有窗口上下文"
            Toast = jclass("android.widget.Toast")
            TV = jclass("android.widget.TextView")
            SV = jclass("android.widget.ScrollView")
            OCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []

            body = str(body)
            copy_text = str(copy_text or "")

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        tv = TV(act)
                        tv.setText(body)
                        tv.setTextSize(14.0)
                        tv.setTextIsSelectable(True)   # 长按可选中复制
                        d = act.getResources().getDisplayMetrics().density
                        pad = int(16 * d)
                        tv.setPadding(pad, pad // 2, pad, pad // 2)
                        sv = SV(act)
                        sv.addView(tv)
                        b = AB(act)
                        b.setTitle(title)
                        b.setView(sv)
                        if copy_text:
                            class Copy(dynamic_proxy(OCL)):
                                def onClick(self, dlg, w):
                                    try:
                                        cb = act.getSystemService("clipboard")
                                        cb.setPrimaryClip(
                                            jclass("android.content.ClipData")
                                            .newPlainText("路径", copy_text))
                                        Toast.makeText(act, "路径已复制", 0).show()
                                    except Exception as e:
                                        try:
                                            Toast.makeText(act, "复制失败: %s"
                                                           % str(e)[:40], 1).show()
                                        except Exception:
                                            pass
                            cp = Copy()
                            b.setPositiveButton("复制路径", cp)
                            refs.append(cp)
                        b.setNegativeButton("关闭", None)
                        dlg = b.show()
                        refs.extend([tv, sv, dlg])
                        del refs[:-16]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "弹窗失败: %s" % str(e)[:40], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-16]
            act.runOnUiThread(sh)
            return True, ""
        except Exception as e:
            return False, str(e)[:60]

    def _qr_dialog(self, url):
        """点歌二维码弹窗：上面是真图，下面是地址，可复制。"""
        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "没有窗口上下文"
            Toast = jclass("android.widget.Toast")
            TV = jclass("android.widget.TextView")
            IV = jclass("android.widget.ImageView")
            LL = jclass("android.widget.LinearLayout")
            LV = jclass("android.widget.LinearLayout$LayoutParams")
            SV = jclass("android.widget.ScrollView")
            BF = jclass("android.graphics.BitmapFactory")
            ST = jclass("android.widget.ImageView$ScaleType")
            OCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []
            holder = {}
            text = ("扫码点歌，或在手机浏览器打开：\n%s\n\n"
                    "服务状态：%s"
                    % (url, "运行中" if self._ksvc_running() else "未启动"))

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        dm = act.getResources().getDisplayMetrics()
                        d = dm.density
                        pad = int(16 * d)
                        ll = LL(act)
                        ll.setOrientation(1)
                        ll.setPadding(pad, pad // 2, pad, pad // 2)
                        bmp = None
                        png = holder.get("png")
                        if png:
                            try:
                                bmp = BF.decodeByteArray(png, 0, len(png))
                            except Exception:
                                bmp = None
                        if bmp is not None:
                            iv = IV(act)
                            iv.setImageBitmap(bmp)
                            iv.setScaleType(ST.FIT_CENTER)
                            iv.setBackgroundColor(-1)
                            side = int(min(dm.widthPixels * 0.70, 720))
                            try:
                                ll.addView(iv, LV(side, side))
                            except Exception:
                                ll.addView(iv)
                        tv = TV(act)
                        tv.setText(text)
                        tv.setTextSize(14.0)
                        tv.setTextIsSelectable(True)
                        tv.setPadding(0, int(10 * d), 0, 0)
                        ll.addView(tv)
                        sv = SV(act)
                        sv.addView(ll)
                        b = AB(act)
                        b.setTitle("📷 点歌二维码")
                        b.setView(sv)

                        class Copy(dynamic_proxy(OCL)):
                            def onClick(self, dlg, w):
                                try:
                                    cb = act.getSystemService("clipboard")
                                    cb.setPrimaryClip(
                                        jclass("android.content.ClipData")
                                        .newPlainText("地址", url))
                                    Toast.makeText(act, "地址已复制", 0).show()
                                except Exception as e:
                                    try:
                                        Toast.makeText(
                                            act, "复制失败: %s" % str(e)[:40],
                                            1).show()
                                    except Exception:
                                        pass

                        cp = Copy()
                        b.setPositiveButton("复制地址", cp)
                        b.setNegativeButton("关闭", None)
                        dlg = b.show()
                        refs.extend([ll, tv, sv, dlg])
                        if bmp is not None:
                            refs.append(bmp)
                        del refs[:-16]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "二维码弹窗失败: %s"
                                           % str(e)[:40], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-16]

            def _prep():
                try:
                    holder["png"] = self._qr_png_bytes()
                except Exception:
                    holder["png"] = None
                try:
                    act.runOnUiThread(sh)
                except Exception as e:
                    self.log("qr dialog fail %r" % (e,))

            import threading as _th
            _th.Thread(target=_prep, daemon=True).start()
            return True, ""
        except Exception as e:
            return False, str(e)[:60]

    def _confirm_dialog(self, title, body, on_ok):
        """是/否确认弹窗；点「确定」回调 on_ok()。"""
        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "没有窗口上下文"
            Toast = jclass("android.widget.Toast")
            TV = jclass("android.widget.TextView")
            SV = jclass("android.widget.ScrollView")
            OCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []
            body = str(body)

            class Ok(dynamic_proxy(OCL)):
                def onClick(self, dlg, w):
                    try:
                        on_ok()
                    except Exception as e:
                        self.log("confirm cb fail %r" % (e,))
                    try:
                        dlg.dismiss()
                    except Exception:
                        pass

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        tv = TV(act)
                        tv.setText(body)
                        tv.setTextSize(14.0)
                        tv.setTextIsSelectable(True)
                        d = act.getResources().getDisplayMetrics().density
                        pad = int(16 * d)
                        tv.setPadding(pad, pad // 2, pad, pad // 2)
                        sv = SV(act)
                        sv.addView(tv)
                        ok = Ok()
                        b = AB(act)
                        b.setTitle(title)
                        b.setView(sv)
                        b.setPositiveButton("确定", ok)
                        b.setNegativeButton("取消", None)
                        dlg = b.show()
                        refs.extend([tv, sv, ok, dlg])
                        del refs[:-16]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "弹窗失败: %s" % str(e)[:40], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-16]
            act.runOnUiThread(sh)
            return True, ""
        except Exception as e:
            return False, str(e)[:60]

    def _choose_dialog(self, title, body, labels, values):
        """带多个候选按钮的弹窗。"""
        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "没有窗口上下文"
            Toast = jclass("android.widget.Toast")
            TV = jclass("android.widget.TextView")
            SV = jclass("android.widget.ScrollView")
            OCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []
            body = str(body)
            labels = [str(x) for x in (labels or [])]
            values = [str(x) for x in (values or [])]
            owner = self

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        tv = TV(act)
                        tv.setText(body)
                        tv.setTextSize(14.0)
                        tv.setTextIsSelectable(True)
                        d = act.getResources().getDisplayMetrics().density
                        pad = int(16 * d)
                        tv.setPadding(pad, pad // 2, pad, pad // 2)
                        sv = SV(act)
                        sv.addView(tv)
                        b = AB(act)
                        b.setTitle(title)
                        b.setView(sv)

                        for i in range(min(len(labels), len(values))):
                            def make(idx):
                                class Pick(dynamic_proxy(OCL)):
                                    def onClick(self, dlg, w):
                                        try:
                                            owner._cfg_set({"db": values[idx]})
                                            ok, info = owner._db_health()
                                            msg = ("已切换：%s" % info) if ok else "切换失败"
                                            Toast.makeText(act, msg, 0).show()
                                        except Exception as e:
                                            try:
                                                Toast.makeText(act, "切换失败: %s"
                                                               % str(e)[:40], 1).show()
                                            except Exception:
                                                pass
                                return Pick()
                            pb = make(i)
                            refs.append(pb)
                            if i == 0:
                                b.setPositiveButton(labels[i], pb)
                            elif i == 1:
                                b.setNegativeButton(labels[i], pb)
                            elif i == 2:
                                b.setNeutralButton(labels[i], pb)
                        dlg = b.show()
                        refs.extend([tv, sv, dlg])
                        del refs[:-16]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "弹窗失败: %s" % str(e)[:40], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-16]
            act.runOnUiThread(sh)
            return True, ""
        except Exception as e:
            return False, str(e)[:60]

    def _db_list_dialog(self, hits, cur):
        """候选库列表弹框。"""
        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "未找到窗口上下文"
            Toast = jclass("android.widget.Toast")
            TV = jclass("android.widget.TextView")
            SV = jclass("android.widget.ScrollView")
            LL = jclass("android.widget.LinearLayout")
            LLP = jclass("android.widget.LinearLayout$LayoutParams")
            OCL = jclass("android.view.View$OnClickListener")
            RL = jclass("java.lang.Runnable")
            Color = jclass("android.graphics.Color")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")

            owner = self
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []

            # 组装行数据：当前库打勾，同名库带父目录，最后加手动输入
            rows = []
            seen = set()
            for p, n in hits:
                if p in seen:
                    continue
                seen.add(p)
                rows.append((p, n))
            if cur and cur not in seen:
                rows.insert(0, (cur, self._probe_db(cur)))

            class Tap(dynamic_proxy(OCL)):
                def __init__(self, path, dlg_holder):
                    super().__init__()
                    self.path = path
                    self.holder = dlg_holder

                def onClick(self, v):
                    try:
                        self.holder[0].dismiss()
                    except Exception:
                        pass
                    owner._cfg_set({"db": self.path})
                    try:
                        Toast.makeText(act, "已切到 %s" % os.path.basename(self.path), 1).show()
                    except Exception:
                        pass

            class ManualTap(dynamic_proxy(OCL)):
                def __init__(self, dlg_holder):
                    super().__init__()
                    self.holder = dlg_holder

                def onClick(self, v):
                    try:
                        self.holder[0].dismiss()
                    except Exception:
                        pass
                    owner._input_dialog("歌曲库路径", "填 .db 完整路径",
                                        owner._cfg.get("db", "") or "",
                                        lambda t: owner._cfg_set({"db": t.strip()}),
                                        "路径已保存")

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        dlg_holder = [None]
                        box = LL(act)
                        box.setOrientation(1)
                        for idx, (p, n) in enumerate(rows):
                            is_cur = (p == cur)
                            base = os.path.basename(p)
                            # 路径一律显示全，只取末级目录名会让两个都叫 db/ 的库撞车
                            line = ("✓  " if is_cur else "    ") + base
                            if n:
                                line += "   （%d 首）" % n
                            line += "\n" + p

                            tv = TV(act)
                            tv.setText(line)
                            tv.setTextSize(14)
                            tv.setPadding(36, 26, 36, 26)
                            if is_cur:
                                tv.setTextColor(Color.parseColor("#1B5E20"))
                                tv.setBackgroundColor(Color.parseColor("#E8F5E9"))
                            else:
                                tv.setTextColor(Color.parseColor("#212121"))
                            lp = LLP(-1, -2)
                            tv.setLayoutParams(lp)
                            tv.setOnClickListener(Tap(p, dlg_holder))
                            box.addView(tv)
                            refs.append(tv)

                            if idx < len(rows) - 1:
                                sep = TV(act)
                                sep.setHeight(1)
                                sep.setBackgroundColor(Color.parseColor("#EEEEEE"))
                                box.addView(sep, LLP(-1, 1))
                                refs.append(sep)

                        # 手动输入行
                        sep2 = TV(act)
                        sep2.setHeight(1)
                        sep2.setBackgroundColor(Color.parseColor("#CCCCCC"))
                        box.addView(sep2, LLP(-1, 1))
                        mt = TV(act)
                        mt.setText("✎  手动输入路径…")
                        mt.setTextSize(14)
                        mt.setTextColor(Color.parseColor("#1565C0"))
                        mt.setPadding(36, 26, 36, 26)
                        mt.setOnClickListener(ManualTap(dlg_holder))
                        box.addView(mt)
                        refs.append(mt)

                        sv = SV(act)
                        sv.addView(box, LLP(-1, -2))
                        b = AB(act)
                        b.setTitle("选择歌曲库（共 %d 个）" % len(rows))
                        b.setView(sv)
                        b.setNegativeButton("取消", None)
                        dlg = b.show()
                        dlg_holder[0] = dlg
                        refs.extend([box, sv, dlg])
                        del refs[:-40]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "列表打开失败:%s" % str(e)[:60], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-40]
            act.runOnUiThread(sh)
            return True, ""
        except Exception as e:
            return False, "%s: %s" % (type(e).__name__, str(e)[:60])

    def _show_db_help(self):
        """数据库未就绪时点提示卡调起这里。"""
        ok, info = self._db_health()
        p = self._db_path()
        hits = self._find_db(limit=20)
        # 库正常时也允许点进来：当成「切换库」用
        if ok:
            if len(hits) <= 1:
                self._toast("数据库正常：%s（只找到这一个库）" % info)
                return
            okd, why = self._db_list_dialog(hits, p)
            if not okd:
                self._toast("列表打不开(%s)" % why)
            return
        if hits:
            body = (
                "当前路径用不了：%s\n"
                "（%s）\n\n"
                "不过在手机上找到了 %d 个可用的歌曲库，\n"
                "直接点下面按钮选一个就行，不用手动找路径：\n\n"
                "%s\n"
                "选好后回首页下拉刷新，这张卡会自动消失。"
            ) % (p, info, len(hits),
                 "\n".join("%d. %s\n   %d 首歌" % (i + 1, h[0], h[1])
                           for i, h in enumerate(hits)))
            labels = ["用第 %d 个" % (i + 1) for i in range(min(len(hits), 3))]
            paths = [h[0] for h in hits]
            okd, why = self._choose_dialog("发现可用歌曲库", body, labels, paths)
            if not okd:
                self._toast("弹窗打不开(%s)，请进设置手动改路径" % why)
            return
        body = (
            "当前路径：\n%s\n\n"
            "状态：%s\n\n"
            "在手机的常见位置都没找到歌曲库。\n"
            "这个脚本本身不带库，库（song_9c8ec.db，约 120MB）要单独放进来。\n\n"
            "可以做的：\n"
            "1. 从旧手机把整个 TVData/db 文件夹搬过来，路径不变就不用改\n"
            "2. 或者进 ⚙ 设置 → 📁 数据库文件路径，手动填 .db 的完整路径\n"
            "3. 确认目录存在、文件名写全（含 .db 后缀）\n\n"
            "下面按钮复制的是当前这个用不了的路径，\n"
            "只是方便你对照着改成正确的位置。"
        ) % (p, info)
        okd, why = self._info_dialog("没找到歌曲库", body, p)
        if not okd:
            self._toast("弹窗打不开(%s)，请进设置手动改路径" % why)

    def _note_card(self, vod_id, name, remarks, body=""):
        # 注意：绝不能带 vod_tag=folder —— 带了壳当「合集」处理，
        # 点卡片会开一个二级目录页而不是弹输入框。
        return {"vod_id": vod_id, "vod_name": name, "vod_pic": "",
                "vod_remarks": remarks, "vod_actor": "",
                "vod_content": body or remarks}

    def _kw_stat_body(self, kw, total, pages, pyhit):
        """搜索统计卡正文。"""
        lines = ["当前关键词：「%s」" % kw,
                 "歌曲总数：%d 首" % total]
        if total <= 0:
            lines.append("")
            lines.append("这个关键词在库里没有匹配到任何歌曲。")
            lines.append("")
            lines.append("可以试试：")
            lines.append("  · 只输歌名或歌手的一部分（如「杰伦」而不是全名）")
            lines.append("  · 用拼音首字母（周杰伦 → ZJL）")
            lines.append("  · 多个关键词用空格隔开（周杰伦 晴天）")
            return "\n".join(lines)
        names = [n for n in (getattr(self, "_py_names", None) or []) if n]
        if pyhit:
            ac = to_acronym(str(kw).split()[0] if str(kw).strip() else kw)
            acs = "/".join(ac[:1]) or "—"
            lines.append("命中方式：拼音首字母容错（%s）" % acs)
            if not names:
                names = [pyhit]
            lines.append("")
            lines.append("按「%s」找到以下歌手：" % acs)
            for i, nm in enumerate(names):
                cnt = self._singer_song_count(nm)
                flag = " ← 排最前" if i == 0 else ""
                lines.append("  %d. %s（%d 首）%s" % (i + 1, nm, cnt, flag))
            if len(names) > 1:
                lines.append("")
                lines.append("想只看其中一位？用完整的中文名搜索，"
                             "或输入「歌手 歌名」两个关键词。")
        else:
            lines.append("命中方式：关键词精确匹配（歌名 / 歌手名）")
        lines.append("")
        lines.append("往下拉列表会继续加载更多；点「✎ 输入关键词」可以换词。")
        return "\n".join(lines)

    def _singer_song_count(self, name):
        """某歌手名下的歌曲数（按 singer_names 包含关系算，含合唱）。"""
        pat = "%" + str(name).replace("%", "").replace("_", "") + "%"
        try:
            r = self.query("SELECT COUNT(*) AS c FROM song WHERE status=1 AND singer_names LIKE ?", (pat,))
            return int(r[0]["c"]) if r else 0
        except Exception:
            return 0

    # ------------------------------------------------- 搜索分类页

    def _search_page(self, pg):
        """🔍搜索 分类页：操作条目 + 结果流。"""
        try:
            pg = max(int(str(pg) or "1"), 1)
        except Exception:
            pg = 1
        kw = self._kw_get()
        # 先搜：总数/页数/拼音命中都要用在头部卡片上
        hits, total, pages, pyhit = [], 0, 1, ""
        if kw:
            res = self.searchContent(kw, False, str(pg))
            hits = res.get("list") or []
            total = int(res.get("total") or 0)
            pages = max(1, int(res.get("pagecount") or pg))
            pyhit = getattr(self, "_py_hit", "")
            # 999999 是「不知道总数」时给壳的占位值（壳靠它判断还能不能下拉），
            # 不是真数据。统计卡要显示人看的数字，这里一律还原成 0。
            if total >= 999999:
                total = 0
        items = []
        if pg <= 1:
            # 第一张卡永远只做「输入搜索词」这件事，不承载统计信息。
            if kw:
                sub = "当前词:%s（点我换词）" % kw
            else:
                sub = "可拼音首字母，多词空格隔开"
            c = self._note_card("kw:input", "✎ 输入关键词（歌/歌手/首字母）", sub)
            c["action"] = "kw"
            c["vod_id"] = json.dumps(
                {"actionId": "kwinput", "id": "kw", "type": "input",
                 "title": "输入搜索词",
                 "tip": "歌名/歌手/首字母，多个词用空格隔开",
                 "value": kw,
                 "msg": "提交后自动刷新当前分类，显示搜索结果"},
                ensure_ascii=False)
            c["vod_tag"] = "action"
            items.append(c)
            if kw:
                c2 = self._note_card("kw:clear", "🗑 清除关键词", "恢复热门列表")
                c2["action"] = "kwclear"
                c2["vod_id"] = json.dumps({"actionId": "kwclear"},
                                          ensure_ascii=False)
                c2["vod_tag"] = "action"
                items.append(c2)
# 统计卡：网格只显示标题，所以总数写进标题；点开弹完整说明。
                name = "总计 %d 首" % total
                if total == 0:
                    sub = "「%s」没有匹配结果" % kw
                elif pyhit:
                    more = len(getattr(self, "_py_names", None) or [])
                    if more > 1:
                        sub = "拼音容错，%d 位歌手，如 %s" % (more, pyhit)
                    else:
                        sub = "拼音容错命中「%s」，点看详情" % pyhit
                else:
                    sub = "关键词「%s」· 点看详情" % kw
                c3 = self._note_card("kw:count", name, sub,
                                     self._kw_stat_body(kw, total, pages, pyhit))
                c3["action"] = "kwstat"
                items.append(c3)
        items.extend(hits)
        if pg <= 1 and kw and not hits:
            items.append(self._note_card(
                "kw:empty", "🔍 没搜到「%s」" % kw,
                "换个词，或试试多关键词",
                "没搜到「%s」。\n\n试试：① 只输歌名或歌手的一部分；"
                "② 用拼音首字母（如 ZJL、ZGR、THG）；"
                "③ 多个关键词用空格隔开"
                "（每个词都要能对上，才会出现在结果里）；"
                "④ 用壳顶部搜索按钮（走同一接口）。" % kw))
        if not kw:
            # 无词：热门垫底不让页面空
            res = self.categoryContent("hot", str(pg), False, None)
            items.extend(res.get("list") or [])
            pages = max(1, int(res.get("pagecount") or pg))
        # total 只在「不知道总数」时才给占位值；搜到 0 条就老老实实报 0，
        # 壳看到 0 会停止下拉，不会一直白翻空页。
        return {"code": 1, "msg": "数据列表", "list": items, "page": pg,
                "pagecount": pages, "limit": 30,
                "total": total if (kw or total) else 999999}

    # ------------------------------------------------- 设置分类页

    def _settings_page(self, pg):
        """⚙设置：卡片列表，点卡片弹输入框改配置。"""
        cfg = self._cfg_get()
        db = str(cfg.get("db") or DB_PATH)
        port = str(cfg.get("port") or "9978")
        cache = str(cfg.get("urlcache") or "10")
        n3ttl = str(cfg.get("n3ttl") if cfg.get("n3ttl") is not None else "3")
        _ksvc_on = self._ksvc_running()
        _ksvc_auto = str(cfg.get("ksvc_auto")
                         if cfg.get("ksvc_auto") is not None else "1") == "1"
        _ksvc_url = self._ksvc_url()
        # 必须挂 action：壳看到卡片有 action 就调 Spider.action()，不会开详情/播放页。
        # 只靠 detailContent 兜底的话，壳会把 set:xxx 当 vod 打开，出现「跳播放页」。
        def _c(key, name, remarks, body):
            c = self._note_card("set:" + key, name, remarks, body)
            c["action"] = "set:" + key
            return c

        # 顺便统计手机上有几个库，卡片上直接告诉用户能不能切换
        try:
            _n_db = len(self._find_db(limit=20))
        except Exception:
            _n_db = 0
        _db_name = os.path.basename(db) if db else "（未设置）"
        _db_remark = ("点我切换（找到 %d 个库）" % _n_db) if _n_db > 1 \
            else "点我切换或手动输入"
        try:
            _cloud_t = self._cloud_card()
        except Exception as _e:
            _cloud_t = ("🔄 云端曲库（在线更新）", "点我检查更新",
                        "读取失败：%s" % str(_e)[:80])
        try:
            _ui = self._db_update_info()
            _upd_title = _ui.get("title") or "📦 数据库更新"
            _upd_remark = _ui.get("remark", "")
            _upd_body = _ui.get("body", "")
        except Exception as _e:
            _upd_title = "📦 数据库更新"
            _upd_remark = "查看版本与更新状态"
            _upd_body = "读取失败：%s" % str(_e)[:80]
        items = [
            _c("dbupd", _upd_title, _upd_remark,
               _upd_body),
            _c("cloud", *_cloud_t),
            _c("db", "📁 歌曲库：%s" % _db_name, _db_remark,
               "当前使用：\n%s\n\n"
               "手机上找到 %d 个可用的歌曲库。\n"
               "点这张卡会列出全部，当前那个前面打 ✓，点任意一个立即切换。\n"
               "列表最后一项是手动输入路径。" % (db, _n_db)),
            _c("gulu", "🔁 换回 Gulu 同步库",
               ("当前就是 Gulu 同步库 ✓" if os.path.realpath(db) == os.path.realpath(GULU_DB)
                else "点我一键切回（固定路径）"),
               "Gulu 的库永远在这一个位置（包内写死，不会变）：\n%s\n\n"
               "旁边同行有 song_9c8ec.version（当前 %s），"
               "Gulu 后台更新时这个文件会一起变。\n\n"
               "点这张卡直接切过来，不用手动敲路径。"
               % (GULU_DB, (self._db_version(GULU_DB) or "无"))),
            _c("autodb", "🔀 开机自动切库（当前 %s）"
               % ("开" if str(self._cfg_get().get("autodb") or "1") == "1"
                  else "关"),
               "开机自动找到最全的库并切过去",
               "开启后，每次打开本源都会自动扫描常见位置"
               "（Gulu 目录、TVData/db、Download 等），"
               "找到歌曲最多的那份库就切过去，并设为以后默认使用。\n\n"
               "当前库本来就是最全的那份时保持不动；"
               "当前库打不开时也会自动切到找到的库。\n\n"
               "关掉后完全按配置里记的库走，不再自动切换。"),
            _c("dbshell", "📌 强制手工曲库（当前 %s）"
               % ("开" if str(self._cfg_get().get("dbshell") or "0") == "1"
                  else "关"),
               "只读我手工指定的那份库",
               "开启后只读「✍️ 手工指定曲库」里你亲手填的那份，"
               "不自动认壳目录、不全盘扫描。\n\n"
               "当前手工路径：\n%s\n\n"
               "关掉后恢复开机自动扫描找库。"
               % (str(self._cfg_get().get("dbmanual") or "（未设置）"))),
            _c("dbmanual", "✍️ 手工指定曲库",
               "当前：%s" % (os.path.basename(
                   str(self._cfg_get().get("dbmanual") or "")) or "未设置"),
               "点我输入曲库的完整路径，你填哪份就用哪份，不自动猜目录。\n\n"
               "可以填 .db 文件的完整路径，也可以只填目录"
               "（自动补 song_9c8ec.db）。\n"
               "填好会先校验是不是能用的曲库，校验过了立刻切过去，"
               "并自动打开「📌 强制手工曲库」。\n\n"
               "当前手工路径：\n%s"
               % (str(self._cfg_get().get("dbmanual") or "（未设置）"))),
            _c("port", "🔌 代理端口（当前 %s）" % port,
               "点我修改（默认9978）", "代理端口 9978，壳的 getProxyUrl 返回值"),
            _c("imgdir", "🖼 歌手图片目录", "点我修改（默认跟随数据库）",
               "当前：%s\n\n留空 = 自动跟随数据库同级目录下的 .singer_img。\n"
               "手动填绝对路径可单独指向别处。" % str(cfg.get("img") or "（跟随数据库）")),
            _c("n3ttl", "🔁 缺图歌手重查间隔（当前 %s 天）" % n3ttl,
               "点我修改（默认 3 天）",
               "本次没找到图的歌手，隔多少天再试一次。\n\n"
               "网络歌手今天没收录、过几天可能就有了，所以别设太长。\n"
               "找到图的会一直留用，不受这个影响。\n\n"
               "填 0 = 每次都重查（最准，但名单长了会拖慢列表加载）。"),
            _c("urlcache", "⏱ 播放链接复用分钟（当前 %s）" % cache,
               "点我修改（默认10分钟）",
               "只控制播放直链在内存里复用多久，和转码缓存无关。\n\n"
               "每次拿直链都要走两步：签名服务取 validator → AES 加密请求 "
               "取流接口 → 返回带 auth_key 的 CDN 地址，约 1-2 秒。"
               "复用期内同一首不再重复请求。\n\n"
               "auth_key 有时效，复用太久会 403，所以别设过大；"
               "最小按 1 分钟算。壳重启后清空。"),
            _c("ksvc", "📡 手机点歌服务（%s）" % ("运行中" if _ksvc_on else "未启动"),
               "点我%s · 端口 %d" % (("停止" if _ksvc_on else "启动"), KSVC_PORT),
               "手机和电视连同一个局域网，扫二维码或打开下面地址就能点歌，"
               "点的歌会出现在「🎤 点歌队列」分类里。\n\n"
               "地址：%s\n\n"
               "点这张卡立即%s服务。" % (_ksvc_url, "停止" if _ksvc_on else "启动")),
            _c("ksvcauto", "🚀 点歌服务自启（当前 %s）" % ("开" if _ksvc_auto else "关"),
               "点我切换开/关",
               "开：每次打开本源时自动启动点歌服务（端口 %d）。\n"
               "关：不再自动启动，需要时在「手机点歌服务」卡上手动启动。"
               % KSVC_PORT),
            _c("skey", "🔑 站点 Key（网页点歌）",
               "当前：%s" % (str(cfg.get("skey") or _KSVC.get("skey")
                                or "未找到（点我可手工填）")),
               "网页点歌要以本源自己的页面播放（不是推送直链），\n"
               "需要知道本源在你配置里的 key。\n\n"
               "一般会自动找到，不用管。\n"
               "一直找不到时：打开你这个播放器用的配置，\n"
               "搜「爱KTV」，把那一条里的 \"key\" 值粘贴到这里，\n"
               "填一次永久生效。\n\n"
               "当前手工值：%s" % (str(cfg.get("skey") or "（未设置）"))),
        ]
        try:
            _qrc = _c("ksvcqr", "📷 点歌二维码", "点我查看地址，可复制",
                      "用手机扫这张卡上的图就能打开点歌页。\n\n"
                      "地址：%s\n\n"
                      "二维码加载不出来时，直接在手机浏览器输入上面的地址也一样。"
                      % _ksvc_url)
            if _ksvc_on:
                _qrc["vod_pic"] = self._qr_pic_url()
            items.append(_qrc)
            _dc = _c("diag", "🧪 诊断日志", "点开自检，日志在曲库同目录",
                     "播放、点歌、服务的所有记录都在这个文件里：\n%s\n\n"
                     "网页点播放失败时，打开点歌页底部的诊断日志链接，"
                     "把内容发我就能定位问题。"
                     % (self._diag_file() or "（写不进文件时看网页版 /diag）"))
            items.append(_dc)
        except Exception:
            pass
        return {"code": 1, "msg": "数据列表", "list": items, "page": 1,
                "pagecount": 1, "limit": 10, "total": len(items)}

    def img_dir(self):
        """歌手封面目录。优先级：设置页 img > 数据库同级 .singer_img > 常量默认。"""
        try:
            cfg = self._cfg_get()
        except Exception:
            cfg = {}
        v = str(cfg.get("img") or "").strip()
        if v:
            return v
        db = self._resolve_db_file(str(cfg.get("db") or DB_PATH))
        return os.path.join(os.path.dirname(db), IMG_DIR_DEFAULT)

    def _handle_setting(self, key):
        cfg = self._cfg_get()
        if key == "autodb":
            cur = str(cfg.get("autodb")
                      if cfg.get("autodb") is not None else "1")
            new = "0" if cur == "1" else "1"
            self._cfg_set({"autodb": new})
            if new == "1":
                sw = None
                try:
                    sw = self._autodb_apply("settings")
                except Exception:
                    sw = None
                now = str(self._cfg_get().get("db") or DB_PATH)
                self._info_dialog(
                    "🔀 开机自动切库：已开启",
                    "每次打开本源都会自动扫描常见位置，"
                    "切到歌曲最多的那份库并设为默认。\n\n"
                    "当前使用：\n%s\n\n%s"
                    % (now, ("刚才已自动切换到：\n%s" % sw) if sw
                       else "当前库就是最全的那份，没有切换。"),
                    now)
            else:
                self._toast("开机自动切库已关")
            return
        if key == "dbshell":
            cur = str(cfg.get("dbshell")
                      if cfg.get("dbshell") is not None else "0")
            new = "0" if cur == "1" else "1"
            self._cfg_set({"dbshell": new})
            if new == "1":
                mp = self._shell_db_path()
                if mp and os.path.isfile(mp):
                    self._cfg_set({"db": mp})
                    self._info_dialog(
                        "📌 强制手工曲库：已开启",
                        "以后只读你手工指定的这份库：\n%s\n\n"
                        "不会自动认壳目录，也不会去别处扫描。" % mp, mp)
                else:
                    self._info_dialog(
                        "📌 强制手工曲库：已开启",
                        "但手工路径还没填，或那个文件不存在。\n\n"
                        "去点「✍️ 手工指定曲库」把完整路径填上，"
                        "填好校验通过就会切过去。\n\n"
                        "当前手工路径：%s" % (mp or "（未设置）"), mp)
            else:
                self._toast("强制手工曲库已关，恢复自动扫描")
            return
        if key == "dbmanual":
            cur = str(cfg.get("dbmanual") or "")

            def ok(t):
                t = (t or "").strip()
                if not t:
                    return
                if os.path.isdir(t):
                    t = self._resolve_db_file(t)
                n = self._probe_db(t)
                if n:
                    self._cfg_set({"dbmanual": t, "db": t, "dbshell": "1"})
                    self._dlog("autodb", "manual db set -> %s (%s songs)"
                               % (t, n))
                else:
                    why2 = self._db_open_error(t, "probe fail")
                    self._dlog("autodb", "manual db rejected: %s | %s"
                               % (t, why2))
                    self._toast("这个路径不是可用的曲库：%s" % why2)

            self._input_dialog(
                "✍️ 手工指定曲库",
                "粘贴曲库 .db 文件的完整路径，或填目录自动补文件名",
                cur, ok, toast="已处理，重新进设置页确认")
            return self._note_card("set:dbmanual", "✍️ 手工指定曲库",
                                   "修改中…", cur)
        if key == "skey":
            cur = str(cfg.get("skey") or "")

            def ok(t):
                t = (t or "").strip()
                self._cfg_set({"skey": t})
                if t:
                    _KSVC["skey"] = t
                else:
                    _KSVC.pop("skey", None)
                self._dlog("skey", "manual skey set: %r" % t)

            self._input_dialog(
                "🔑 站点 Key",
                "粘贴你配置里爱KTV那一条的 \"key\" 值；留空清除",
                cur, ok, toast="已保存，重新进设置页确认")
            return self._note_card("set:skey", "🔑 站点 Key",
                                   "修改中…", cur)
        if key == "ksvc":
            if self._ksvc_running():
                self._ksvc_stop()
                self._toast("点歌服务已停止")
            elif self._ksvc_start():
                self._toast("点歌服务已启动：%s" % self._ksvc_url())
            else:
                self._toast("点歌服务启动失败，端口 %d 可能被占用" % KSVC_PORT)
            return
        if key == "ksvcauto":
            cur = str(cfg.get("ksvc_auto")
                      if cfg.get("ksvc_auto") is not None else "1")
            new = "0" if cur == "1" else "1"
            self._cfg_set({"ksvc_auto": new})
            if new == "1":
                self._ksvc_start()
                self._toast("点歌服务自启已开")
            else:
                self._toast("点歌服务自启已关（已启动的这次不会停）")
            return
        if key == "ksvcqr":
            url = self._ksvc_url()
            ok, why = self._qr_dialog(url)
            if not ok:
                self._info_dialog(
                    "📷 点歌二维码",
                    "二维码没画出来（%s），直接在手机浏览器打开这个地址也一样：\n\n%s\n\n"
                    "服务状态：%s"
                    % (why, url,
                       "运行中" if self._ksvc_running() else "未启动，先启动点歌服务"),
                    url)
            return
        if key == "diag":
            try:
                self._env_probe("settings")
            except Exception:
                pass
            _dp = self._diag_file()
            _tail = ""
            if _dp:
                try:
                    with open(_dp, "r", encoding="utf-8",
                              errors="ignore") as _f:
                        _tail = _f.read()[-3000:]
                except Exception:
                    _tail = ""
            if not _tail:
                try:
                    _tail = "".join(_DIAG["buf"])[-3000:]
                except Exception:
                    _tail = ""
            if not _dp:
                _dp = "（文件暂时写不进去，请打开网页版 /diag 看日志）"
            self._info_dialog(
                "🧪 诊断日志",
                "日志文件（和曲库在同一个目录）：\n%s\n\n"
                "也可以在手机浏览器打开点歌页底部的「诊断日志」链接查看。\n\n"
                "最近记录：\n%s" % (_dp, _tail),
                _dp)
            return
        if key == "cloud":
            self._cloud_action()
            return
        if key == "gulu":
            # 一键换回 Gulu 同步库：固定路径，不用用户敲
            cur = str(cfg.get("db") or DB_PATH)
            if os.path.realpath(cur) == os.path.realpath(GULU_DB):
                self._info_dialog("🔁 Gulu 同步库",
                                  "当前用的就是 Gulu 自动同步的那一份。\n\n" + GULU_DB,
                                  GULU_DB)
                return
            n = self._probe_db(GULU_DB)
            if not n:
                self._info_dialog("🔁 Gulu 同步库",
                                  "找不到 Gulu 同步库：\n%s\n\n"
                                  "Gulu 还没下载过数据库，或者路径变了。"
                                  % GULU_DB, GULU_DB)
                return

            def _ok():
                try:
                    self._cfg_set({"db": GULU_DB, "db_prev": cur})
                except Exception:
                    pass
                self._toast("已切换到 Gulu 同步库：%d 首" % n)

            self._confirm_dialog(
                "🔁 切换到 Gulu 同步库",
                "将从\n%s\n\n切到 Gulu 自动同步的那份：\n%s\n\n%d 首歌" % (cur, GULU_DB, n),
                _ok)
            return
        if key == "dbupd":
            info = self._db_update_info()
            if info.get("newer") == 1 and info.get("sync"):
                # 有更新的库：直接给「切换 / 取消」两个按钮
                def _ok():
                    try:
                        self._cfg_set({"db": info["sync"],
                                       "db_prev": info["cur"]})
                    except Exception:
                        pass
                    self._toast("已切换到 Gulu 同步库：%s 首"
                                % (info.get("sync_cnt") or "?"))
                self._confirm_dialog("📦 数据库更新", info.get("body", ""), _ok)
            else:
                # 没有新版：只读展示，带复制路径
                self._info_dialog("📦 数据库状态", info.get("body", ""),
                                  info.get("cur", ""))
            return
        if key == "db":
            cur = str(cfg.get("db") or DB_PATH)
            hits = self._find_db(limit=20)
            # 当前库不在扫描结果里也补进去，方便对照
            if cur and cur not in [h[0] for h in hits] and os.path.isfile(cur):
                hits = [(cur, self._probe_db(cur))] + list(hits)
            okd, why = self._db_list_dialog(hits, cur)
            if not okd:
                self._toast("列表打不开(%s)，改手动输入" % why)
                def ok(t):
                    if t:
                        self._cfg_set({"db": t})
                self._input_dialog("📁 数据库文件路径",
                                   "绝对路径，如 /storage/.../song.db",
                                   cur, ok, toast="已保存，立即生效")
                return self._note_card("set:db", "📁 数据库文件路径",
                                       "修改中…重新进设置查看", cur)
            cnt = len(hits)
            return self._note_card("set:db", "📁 数据库文件路径",
                                   "点我切换（找到 %d 个库）" % cnt
                                   if cnt else "点我切换或手动输入", cur)
        if key == "port":
            cur = str(cfg.get("port") or "9978")

            def ok(t):
                if t.isdigit():
                    self._cfg_set({"port": t})
            self._input_dialog("🔌 代理端口", "数字端口，默认 9978", cur, ok,
                               toast="已保存，立即生效")
            return self._note_card("set:port", "🔌 代理端口", "修改中…", cur)
        if key == "imgdir":
            cur = str(cfg.get("img") or "")
            fallback = self.img_dir()

            def ok(t, _fb=fallback):
                try:
                    self._cfg_set({"img": t or ""})
                except Exception:
                    pass
            self._input_dialog("🖼 歌手图片目录",
                               "留空 = 跟随数据库（%s）；或填绝对路径" % fallback,
                               cur, ok, toast="已保存，立即生效")
            return self._note_card("set:imgdir", "🖼 歌手图片目录", "修改中…",
                                   cur or fallback)
        if key == "n3ttl":
            cur = str(cfg.get("n3ttl") if cfg.get("n3ttl") is not None else "3")

            def ok(t):
                if t.isdigit():
                    self._cfg_set({"n3ttl": t})
            self._input_dialog("🔁 缺图歌手重查间隔（天）",
                               "这次没找到图的歌手，隔几天再试一次；填 0 = 每次都重查。默认 3",
                               cur, ok, toast="已保存，立即生效")
            return self._note_card("set:n3ttl", "🔁 缺图歌手重查间隔", "修改中…",
                                   cur + " 天")
        if key == "urlcache":
            cur = str(cfg.get("urlcache") or "10")

            def ok(t):
                # 0 会在 get_play_url 里被 max(60,...) 压成 1 分钟，但界面上
                # 显示 0 会让人以为关掉了缓存，直接拒绝更清楚。
                if t.isdigit() and int(t) > 0:
                    self._cfg_set({"urlcache": t})
            self._input_dialog("⏱ 播放链接复用分钟",
                               "播放直链复用时长（分钟），默认 10；须大于 0", cur, ok,
                               toast="已保存，立即生效")
            return self._note_card("set:urlcache", "⏱ 播放链接复用", "修改中…", cur)
        return None

    def _diag_candidates(self):
        cands = []

        def add(pp):
            if pp and pp not in cands:
                cands.append(pp)

        try:
            dbp = FORCE_DB_PATH or self._db_setting()
            if os.path.isdir(dbp):
                d = dbp
            else:
                d = os.path.dirname(dbp)
            if d:
                add(os.path.join(d, "_aiKTV_diag.log"))
        except Exception as e:
            _DIAG["errs"]["<db dir>"] = repr(e)
        try:
            d = os.path.dirname(self._cfg_file())
            if d:
                add(os.path.join(d, "_aiKTV_diag.log"))
        except Exception as e:
            _DIAG["errs"]["<cfg dir>"] = repr(e)
        try:
            from java import jclass
            _P = jclass("com.chaquo.python.Python")
            _ctx = _P.getPlatform().getApplication()
            _f = _ctx.getFilesDir() if _ctx is not None else None
            if _f is not None:
                add(os.path.join(str(_f.getAbsolutePath()),
                                 "_aiKTV_diag.log"))
        except Exception as e:
            _DIAG["errs"]["<app files dir>"] = repr(e)
        add("/storage/emulated/0/Download/_aiKTV_diag.log")
        add("_aiKTV_diag.log")
        return cands

    def _diag_file(self):
        if _DIAG.get("path"):
            return _DIAG["path"]
        if _DIAG.get("busy"):
            return ""
        _DIAG["busy"] = True
        try:
            for cand in self._diag_candidates():
                try:
                    with open(cand, "a", encoding="utf-8") as f:
                        f.write("")
                    _DIAG["path"] = cand
                    return cand
                except Exception as e:
                    _DIAG["errs"][cand] = repr(e)
            return ""
        finally:
            _DIAG["busy"] = False

    def _dlog(self, tag, msg):
        try:
            line = "%s [%s] %s: %s\n" % (
                time.strftime("%Y-%m-%d %H:%M:%S"),
                threading.current_thread().name, tag, msg)
        except Exception:
            return
        try:
            self.log("diag %s: %s" % (tag, msg))
        except Exception:
            pass
        try:
            buf = _DIAG["buf"]
            buf.append(line)
            if len(buf) > 1200:
                del buf[:len(buf) - 1200]
        except Exception:
            pass
        try:
            with _DIAG["lock"]:
                p = self._diag_file()
                if not p:
                    return
                try:
                    if os.path.getsize(p) > 2 * 1024 * 1024:
                        with open(p, "r", encoding="utf-8",
                                  errors="ignore") as f:
                            data = f.read()
                        with open(p, "w", encoding="utf-8") as f:
                            f.write(data[-500000:])
                    with open(p, "a", encoding="utf-8") as f:
                        f.write(line)
                except Exception as e:
                    _DIAG["errs"][p] = repr(e)
                    _DIAG["path"] = ""
        except Exception:
            pass

    def _dexc(self, tag, e):
        tb = ""
        try:
            import traceback
            tb = traceback.format_exc()
        except Exception:
            tb = ""
        self._dlog(tag, "EXC %r | %s" % (e, (tb or "")[-1500:].replace("\n", " / ")))

    def _env_probe(self, where):
        import sys
        try:
            import platform as _pf
            self._dlog("probe", "where=%s thread=%s main_thread=%s" % (
                where, threading.current_thread().name,
                threading.main_thread().name))
            self._dlog("probe", "python=%s" % sys.version.replace("\n", " "))
            self._dlog("probe", "platform=%s os=%s" % (_pf.platform(), os.name))
            rel = [k for k in list(sys.modules)
                   if "java" in k or "chaquo" in k or "jni" in k]
            self._dlog("probe", "loaded java-related modules=%s" % rel[:20])
        except Exception as e:
            self._dexc("probe base", e)
        try:
            import java as _jm
            self._dlog("probe", "import java OK -> %s" % _jm)
        except Exception as e:
            self._dexc("probe import java", e)
        try:
            from java import jclass
            self._dlog("probe", "from java import jclass OK")
        except Exception as e:
            self._dexc("probe jclass import", e)
            return
        for cls in ("android.content.Intent", "android.net.Uri",
                    "com.chaquo.python.Python",
                    "android.app.ActivityThread",
                    "android.app.AppGlobals",
                    "com.fongmi.android.tv.ui.activity.VideoActivity"):
            try:
                obj = jclass(cls)
                self._dlog("probe", "jclass %s OK -> %s" % (cls, obj))
            except Exception as e:
                self._dexc("probe jclass %s" % cls, e)
        try:
            Python = jclass("com.chaquo.python.Python")
            ctx = Python.getPlatform().getApplication()
            pkg = ""
            try:
                pkg = str(ctx.getPackageName()) if ctx is not None else ""
            except Exception:
                pkg = ""
            self._dlog("probe", "chaquo ctx=%s pkg=%s" % (ctx, pkg))
        except Exception as e:
            self._dexc("probe chaquo ctx", e)
        try:
            AT = jclass("android.app.ActivityThread")
            app = AT.currentApplication()
            self._dlog("probe", "ActivityThread app=%s" % app)
        except Exception as e:
            self._dexc("probe activitythread", e)
        try:
            key = self._site_key()
            self._dlog("probe", "site key=%r" % key)
        except Exception as e:
            self._dexc("probe skey", e)


    # ------------------------------------------------- song request queue / service

    def _queue_file(self):
        try:
            d = os.path.dirname(self._cfg_file())
        except Exception:
            d = ""
        if d:
            return os.path.join(d, "_aiKTV_queue.json")
        return "_aiKTV_queue.json"

    def _queue_get(self):
        p = self._queue_file()
        try:
            mt = os.path.getmtime(p)
        except Exception:
            mt = 0
        with _QLOCK:
            if mt and _QSTATE["mtime"] == mt and _QSTATE["items"]:
                return list(_QSTATE["items"])
            items = []
            if mt:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        items = [x for x in data
                                 if isinstance(x, dict) and x.get("number")]
                except Exception:
                    items = []
            _QSTATE["mtime"] = mt
            _QSTATE["items"] = items
            return list(items)

    def _queue_save(self, items):
        p = self._queue_file()
        with _QLOCK:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(items, f, ensure_ascii=False)
            except Exception as e:
                self.log("queue save fail: %s" % e)
            _QSTATE["items"] = list(items)
            try:
                _QSTATE["mtime"] = os.path.getmtime(p)
            except Exception:
                _QSTATE["mtime"] = 0
        return items

    def _queue_add(self, number):
        try:
            num = int(number)
        except Exception:
            return False, "歌曲编号不对"
        rows = self.query(
            "SELECT number,name,singer_names FROM song WHERE number=?",
            (num,))
        if not rows:
            return False, "曲库里没有这首歌"
        r = rows[0]
        q = self._queue_get()
        for i, x in enumerate(q):
            if int(x.get("number") or 0) == num:
                return True, "已在队列里：第 %d 首" % (i + 1)
        q.append({"number": num, "name": r["name"] or "",
                  "singer": r["singer_names"] or "",
                  "ts": int(time.time())})
        self._queue_save(q)
        self.log("ksvc queue add %d %s" % (num, r["name"]))
        return True, "已点：%s" % (r["name"] or "")

    def _queue_remove(self, index=None, number=None):
        q = self._queue_get()
        n0 = len(q)
        try:
            if index is not None and str(index) != "":
                i = int(index)
                if 0 <= i < len(q):
                    q.pop(i)
            elif number is not None:
                num = int(number)
                q = [x for x in q if int(x.get("number") or 0) != num]
        except Exception:
            pass
        if len(q) != n0:
            self._queue_save(q)
            return True
        return False

    def _queue_clear(self):
        self._queue_save([])
        return True

    def _queue_page(self, pg):
        try:
            pg = max(int(str(pg or "1")), 1)
        except Exception:
            pg = 1
        size = 30
        off = (pg - 1) * size
        q = self._queue_get()
        items = []
        if pg <= 1:
            on = self._ksvc_running()
            c = self._note_card(
                "ksvc:head", "🎤 点歌队列（%d 首）" % len(q),
                ("服务运行中 · %s" % self._ksvc_url()) if on
                else "服务未启动，去设置里打开点歌服务")
            if on:
                c["vod_pic"] = self._qr_pic_url()
            c["action"] = "ksvc:qr"
            items.append(c)
            if q:
                pq = {"vod_id": "qplay",
                      "vod_name": "▶ 开始播放（%d 首连播）" % len(q),
                      "vod_pic": "",
                      "vod_remarks": "从第一首开始，自动播下一首",
                      "vod_tag": None}
                items.append(pq)
                cp = self._note_card("queue:pop", "⏭ 切歌（去掉第一首）",
                                     "点我把队列第一首移除")
                cp["action"] = "queue:pop"
                cp["vod_id"] = json.dumps({"actionId": "queuepop"},
                                          ensure_ascii=False)
                cp["vod_tag"] = "action"
                items.append(cp)
                c2 = self._note_card("queue:clear", "🗑 清空点歌队列",
                                     "点我清空全部已点歌曲")
                c2["action"] = "queue:clear"
                c2["vod_id"] = json.dumps({"actionId": "queueclear"},
                                          ensure_ascii=False)
                c2["vod_tag"] = "action"
                items.append(c2)
        part = q[off:off + size]
        if part:
            nums = [int(x.get("number") or 0) for x in part]
            rows = {}
            try:
                rs = self.query(
                    "SELECT number,name,singer_names,language_id,temperature "
                    "FROM song WHERE number IN (%s)"
                    % ",".join(["?"] * len(nums)), tuple(nums))
                for r in rs:
                    rows[int(r["number"])] = r
            except Exception:
                rows = {}
            for i, x in enumerate(part):
                num = int(x.get("number") or 0)
                r = rows.get(num)
                if r:
                    card = self.song_card(r)
                else:
                    card = {"vod_id": "s%d" % num,
                            "vod_name": x.get("name") or ("歌曲 %d" % num),
                            "vod_pic": "", "vod_remarks": "", "vod_tag": None}
                card["vod_remarks"] = ("第%d首 · %s"
                                       % (off + i + 1, x.get("singer") or "")
                                       ).strip(" ·")
                items.append(card)
        pages = max(1, (len(q) + size - 1) // size) if q else 1
        if pg <= 1 and not q:
            items.append(self._note_card(
                "queue:empty", "🎤 还没有人点歌",
                "扫顶部二维码点歌后会自动出现在这里",
                "用手机扫顶部二维码打开点歌页，搜歌点歌后回到这里下拉刷新就能看到。"))
            try:
                res = self.categoryContent("hot", "1", False, None)
                items.extend(res.get("list") or [])
            except Exception:
                pass
        return {"code": 1, "msg": "数据列表", "list": items, "page": pg,
                "pagecount": pages, "limit": size,
                "total": len(q) if q else 999999}

    def _queue_play_detail(self):
        q = self._queue_get()
        eps = []
        singers = []
        for i, x in enumerate(q):
            num = int(x.get("number") or 0)
            if not num:
                continue
            label = "%02d %s" % (i + 1, x.get("name") or ("歌曲 %d" % num))
            eps.append("%s$play%d" % (label, num))
            if x.get("singer"):
                singers.append(str(x.get("singer")))
        first_pic = ""
        if eps:
            try:
                rows = self.query(
                    "SELECT number,name,singer_names,language_id,temperature "
                    "FROM song WHERE number=?",
                    (int(q[0].get("number") or 0),))
                if rows:
                    first_pic = self.song_card(rows[0]).get("vod_pic") or ""
            except Exception:
                first_pic = ""
        if eps:
            content = ("共 %d 首，按点歌顺序连续播放，一首播完自动播下一首；"
                       "想跳过当前这首，用播放器里的下一集按钮切歌。\n"
                       "注意：播放列表是打开本页这一刻的队列，"
                       "之后新点的歌要重新打开开始播放才会进来。" % len(eps))
        else:
            content = "队列是空的，先用手机扫码点几首歌再回来。"
        vod = {"vod_id": "qplay",
               "vod_name": "🎤 点歌队列 · 连续播放",
               "vod_pic": first_pic,
               "type_name": "点歌",
               "vod_year": "", "vod_area": "", "vod_lang": "",
               "vod_remarks": ("%d 首 · 自动下一首" % len(eps)) if eps else "队列是空的",
               "vod_actor": "、".join(singers[:6]),
               "vod_director": "",
               "vod_content": content,
               "vod_play_from": "爱KTV点歌",
               "vod_play_url": "#".join(eps)}
        return {"code": 1, "msg": "数据列表", "list": [vod],
                "page": 1, "pagecount": 1, "limit": 1, "total": 1}

    def _lan_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        try:
            ip = socket.gethostbyname(socket.gethostname())
            if ip:
                return ip
        except Exception:
            pass
        return "127.0.0.1"

    def _ksvc_url(self):
        return "http://%s:%d/" % (self._lan_ip(), KSVC_PORT)

    def _ksvc_running(self):
        return _KSVC.get("srv") is not None or bool(_KSVC.get("adopted"))

    def _ksvc_probe(self):
        try:
            import urllib.request
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/status" % KSVC_PORT,
                    timeout=1) as r:
                obj = json.loads(r.read().decode("utf-8"))
            return bool(obj.get("ok"))
        except Exception:
            return False

    def _ksvc_maybe_start(self):
        auto = self._cfg_get().get("ksvc_auto")
        if str(auto if auto is not None else "1") == "1":
            self._ksvc_start()

    def _ksvc_start(self):
        with _KSVC["lock"]:
            _KSVC["spider"] = self
            if _KSVC.get("srv") is not None:
                return True
            try:
                from http.server import BaseHTTPRequestHandler
                from http.server import ThreadingHTTPServer
            except Exception:
                return False
            outer = self

            class H(BaseHTTPRequestHandler):
                protocol_version = "HTTP/1.1"

                def log_message(self, *args):
                    pass

                def do_GET(self):
                    sp = _KSVC.get("spider") or outer
                    sp._ksvc_handle(self, "GET")

                def do_POST(self):
                    sp = _KSVC.get("spider") or outer
                    sp._ksvc_handle(self, "POST")

            try:
                srv = ThreadingHTTPServer(("0.0.0.0", KSVC_PORT), H)
            except Exception as e:
                if self._ksvc_probe():
                    _KSVC["adopted"] = True
                    self.log("ksvc adopt existing on %d" % KSVC_PORT)
                    self._dlog("svc", "adopted existing service on %d"
                               % KSVC_PORT)
                    return True
                self.log("ksvc bind fail: %s" % e)
                self._dexc("svc bind", e)
                return False
            srv.daemon_threads = True
            th = threading.Thread(target=srv.serve_forever,
                                  kwargs={"poll_interval": 0.5})
            th.daemon = True
            th.start()
            _KSVC["srv"] = srv
            _KSVC["thread"] = th
            self.log("ksvc started %s" % self._ksvc_url())
            self._dlog("svc", "started %s" % self._ksvc_url())
            return True

    def _ksvc_stop(self):
        with _KSVC["lock"]:
            srv = _KSVC.get("srv")
            _KSVC["srv"] = None
            _KSVC["thread"] = None
            _KSVC["adopted"] = False
        if srv is not None:
            def _off():
                try:
                    srv.shutdown()
                except Exception:
                    pass
                try:
                    srv.server_close()
                except Exception:
                    pass
            threading.Thread(target=_off, daemon=True).start()
        return True

    def _ksvc_search(self, q):
        q = str(q or "").strip()
        if not q:
            return []
        words = [w for w in re.split(r"[\s,，、|+/]+", q) if w]
        if not words:
            words = [q]
        where, args = ["status=1"], []
        for w in words:
            lk = "%" + w.replace("%", "").replace("_", "") + "%"
            where.append("(name LIKE ? OR singer_names LIKE ?)")
            args.extend([lk, lk])
        rows = []
        try:
            rows = self.query(
                "SELECT number,name,singer_names,language_id,temperature "
                "FROM song WHERE " + " AND ".join(where) +
                " ORDER BY temperature DESC LIMIT 30", tuple(args))
        except Exception:
            rows = []
        if rows:
            return [{"number": int(r["number"]), "name": r["name"] or "",
                     "singer": r["singer_names"] or ""} for r in rows]
        try:
            res = self.searchContent(q, False, "1")
            out = []
            for c in (res.get("list") or []):
                vid = str(c.get("vod_id") or "")
                if vid.startswith("s") and vid[1:].isdigit():
                    out.append({"number": int(vid[1:]),
                                "name": c.get("vod_name") or "", "singer": ""})
            return out[:30]
        except Exception:
            return []

    def _ksvc_handle(self, h, method):
        from urllib.parse import urlparse, parse_qs
        try:
            u = urlparse(h.path)
            path = u.path
            qs = parse_qs(u.query)
        except Exception:
            path, qs = "/", {}

        def send(code, ctype, body):
            if isinstance(body, str):
                body = body.encode("utf-8")
            try:
                h.send_response(code)
                h.send_header("Content-Type", ctype)
                h.send_header("Content-Length", str(len(body)))
                h.send_header("Cache-Control", "no-store")
                h.end_headers()
                h.wfile.write(body)
            except Exception:
                pass

        def jout(obj, code=200):
            send(code, "application/json; charset=utf-8",
                 json.dumps(obj, ensure_ascii=False))

        if path not in ("/api/queue", "/api/status"):
            self._dlog("http", "%s %s" % (method, str(h.path)[:200]))
        try:
            if method == "GET" and path == "/diag":
                body = ""
                _dp = ""
                try:
                    _dp = self._diag_file()
                except Exception:
                    _dp = ""
                if _dp:
                    try:
                        with open(_dp, "r", encoding="utf-8",
                                  errors="ignore") as f:
                            body = f.read()
                    except Exception as e:
                        _DIAG["errs"][_dp] = repr(e)
                        body = ""
                if not body:
                    try:
                        body = "".join(_DIAG["buf"])
                    except Exception:
                        body = ""
                _hdr = ("diag file: %s\nwrite errors: %s\n---\n"
                        % (_dp or "(memory only)", _DIAG.get("errs") or {}))
                send(200, "text/plain; charset=utf-8",
                     _hdr + (body[-200000:] if body else "no diag log yet"))
                return
            if method == "GET" and path in ("/", "/index.html"):
                send(200, "text/html; charset=utf-8", self._ksvc_page_html())
                return
            if method == "GET" and path == "/api/search":
                jout({"list": self._ksvc_search((qs.get("q") or [""])[0])})
                return
            if method == "GET" and path == "/api/queue":
                jout({"list": self._queue_get(), "url": self._ksvc_url()})
                return
            if method == "GET" and path == "/api/status":
                jout({"ok": 1, "count": len(self._queue_get()),
                      "url": self._ksvc_url()})
                return
            if method == "POST" and path in ("/api/add", "/api/remove",
                                             "/api/clear", "/api/play",
                                             "/api/playq", "/api/next"):
                try:
                    n = int(h.headers.get("Content-Length") or 0)
                except Exception:
                    n = 0
                raw = h.rfile.read(n) if n > 0 else b""
                obj = {}
                if raw:
                    try:
                        obj = json.loads(raw.decode("utf-8"))
                    except Exception:
                        try:
                            from urllib.parse import parse_qsl
                            obj = dict(parse_qsl(raw.decode("utf-8")))
                        except Exception:
                            obj = {}
                if not isinstance(obj, dict):
                    obj = {}
                self._dlog("http", "POST %s body=%s"
                           % (path, str(obj)[:200]))
                if path == "/api/add":
                    ok, msg = self._queue_add(obj.get("number"))
                    jout({"ok": 1 if ok else 0, "msg": msg,
                          "count": len(self._queue_get())})
                    return
                if path == "/api/remove":
                    ok = self._queue_remove(obj.get("index"),
                                            obj.get("number"))
                    jout({"ok": 1 if ok else 0,
                          "count": len(self._queue_get())})
                    return
                if path == "/api/play":
                    ok, msg = self._api_play(obj.get("number"))
                    jout({"ok": 1 if ok else 0, "msg": msg})
                    return
                if path == "/api/playq":
                    qq = self._queue_get()
                    if not qq:
                        jout({"ok": 0, "msg": "队列是空的"})
                        return
                    ok, msg = self._remote_play(
                        "qplay", "点歌队列 · 连续播放", "",
                        int(qq[0].get("number") or 0))
                    jout({"ok": 1 if ok else 0, "msg": msg})
                    return
                if path == "/api/next":
                    ok, msg = self._play_next()
                    jout({"ok": 1 if ok else 0, "msg": msg})
                    return
                self._queue_clear()
                jout({"ok": 1, "count": 0})
                return
            jout({"ok": 0, "msg": "not found"}, 404)
        except Exception as e:
            self.log("ksvc handle fail: %s" % e)
            self._dexc("http", e)
            try:
                jout({"ok": 0, "msg": "error"}, 500)
            except Exception:
                pass

    def _ksvc_page_html(self):
        return """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>爱KTV 点歌</title>
<style>
body{font-family:sans-serif;background:#14161c;color:#eee;margin:0;padding:14px}
h1{font-size:20px;margin:6px 0 12px}
h3{margin:18px 0 8px;font-size:16px}
.row{display:flex;gap:8px}
input{flex:1;padding:12px;border-radius:10px;border:1px solid #333;background:#1e212b;color:#fff;font-size:16px}
button{padding:10px 14px;border:0;border-radius:10px;background:#e5484d;color:#fff;font-size:15px}
button.gray{background:#333a48}
.item{display:flex;align-items:center;gap:8px;background:#1e212b;border-radius:10px;padding:10px 12px;margin:8px 0}
.item .t{flex:1;min-width:0}
.item .n{font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .s{font-size:13px;color:#9aa3b2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#msg{color:#ffd166;min-height:20px;margin-top:8px;font-size:14px}
.qnum{color:#ffd166;font-weight:bold}
</style></head>
<body>
<h1>&#127908; 爱KTV 点歌</h1>
<div class="row"><input id="q" placeholder="搜歌名 / 歌手 / 首字母"><button id="go">搜索</button></div>
<div id="msg"></div>
<h3>已点队列 <span id="cnt"></span> <button id="playq">播放队列</button> <button class="gray" id="next">切歌</button> <button class="gray" id="clear">清空</button></h3>
<div id="queue"></div>
<h3>搜索结果</h3>
<div id="list"><div class="item"><div class="t"><div class="s">输入关键词后点搜索，点「播放」电视直接唱，点「点歌」加入队列</div></div></div></div>
<script>
function $(i){return document.getElementById(i)}
function esc(s){return String(s||'').replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function toast(t){$('msg').textContent=t||''}
async function api(p,m,b){
  var o={method:m||'GET',headers:{'Content-Type':'application/json'}};
  if(b)o.body=JSON.stringify(b);
  var r=await fetch(p,o); return await r.json();
}
async function loadQ(){
  try{
    var d=await api('/api/queue');
    var q=d.list||[];
    $('cnt').textContent='（'+q.length+' 首）';
    if(!q.length){$('queue').innerHTML='<div class="item"><div class="t"><div class="s">队列是空的，先在下面搜一首点上</div></div></div>';return}
    $('queue').innerHTML=q.map(function(x,i){
      return '<div class="item"><div class="qnum">'+(i+1)+'.</div><div class="t"><div class="n">'+esc(x.name)+'</div><div class="s">'+esc(x.singer)+'</div></div><button onclick="playSong('+x.number+')">播放</button><button class="gray" onclick="delSong('+i+')">删除</button></div>'
    }).join('');
  }catch(e){}
}
async function doSearch(){
  var q=$('q').value.trim();
  if(!q){toast('先输入歌名或歌手');return}
  toast('搜索中...');
  try{
    var d=await api('/api/search?q='+encodeURIComponent(q));
    var l=d.list||[];
    toast(l.length?('找到 '+l.length+' 首'):'没找到，换个词试试');
    if(!l.length){$('list').innerHTML='';return}
    $('list').innerHTML=l.map(function(x){
      return '<div class="item"><div class="t"><div class="n">'+esc(x.name)+'</div><div class="s">'+esc(x.singer)+'</div></div><button onclick="playSong('+x.number+')">播放</button><button class="gray" onclick="addSong('+x.number+')">点歌</button></div>'
    }).join('');
  }catch(e){toast('搜索失败')}
}
window.addSong=async function(n){
  try{var r=await api('/api/add','POST',{number:n}); toast(r.msg||'已点'); loadQ()}catch(e){toast('点歌失败')}
};
window.playSong=async function(n){
  toast('正在让电视播放...');
  try{var r=await api('/api/play','POST',{number:n}); toast(r.msg||''); loadQ()}catch(e){toast('播放失败')}
};
window.delSong=async function(i){
  try{await api('/api/remove','POST',{index:i}); loadQ()}catch(e){}
};
$('go').onclick=doSearch;
$('q').addEventListener('keydown',function(e){if(e.key==='Enter')doSearch()});
$('playq').onclick=async function(){try{var r=await api('/api/playq','POST',{}); toast(r.msg||'')}catch(e){toast('播放失败')}};
$('next').onclick=async function(){try{var r=await api('/api/next','POST',{}); toast(r.msg||'')}catch(e){toast('切歌失败')}};
$('clear').onclick=async function(){try{await api('/api/clear','POST',{}); toast('队列已清空'); loadQ()}catch(e){}};
loadQ(); setInterval(loadQ,3000);
</script>
<div style="margin-top:18px"><a href="/diag" style="color:#9aa3b2;font-size:13px">诊断日志（播放有问题时打开这个页面，把内容发我）</a></div>
</body></html>"""

    def _site_key(self):
        try:
            cfg = self._cfg_get()
            if cfg.get("skey"):
                return str(cfg["skey"])
        except Exception:
            pass
        if _KSVC.get("skey"):
            return _KSVC["skey"]
        try:
            if time.time() - float(_KSVC.get("skey_at") or 0) < 600:
                return ""
        except Exception:
            pass
        _KSVC["skey_at"] = time.time()
        key = ""
        try:
            key = self._site_key_discover() or ""
        except Exception as e:
            self.log("skey discover fail: %s" % e)
            key = ""
        if key:
            _KSVC["skey"] = key
        return key

    def _site_key_discover(self):
        ctx = None
        try:
            ctx = self._app_ctx()
        except Exception:
            ctx = None
        roots = []
        raw_roots = []
        if ctx is not None:
            for meth in ("getFilesDir", "getCacheDir"):
                try:
                    f = getattr(ctx, meth)()
                    if f is not None:
                        roots.append(str(f.getAbsolutePath()))
                except Exception:
                    pass
            try:
                f = ctx.getExternalFilesDir(None)
                if f is not None:
                    roots.append(str(f.getAbsolutePath()))
            except Exception:
                pass
            try:
                base = os.path.dirname(roots[0]) if roots else ""
                if base:
                    raw_roots.append(os.path.join(base, "databases"))
                    raw_roots.append(os.path.join(base, "shared_prefs"))
            except Exception:
                pass
        for extra in ("/storage/emulated/0/VodPlus/LocalFiles",
                      "/storage/emulated/0/WebHTV/LocalFiles"):
            if extra not in roots:
                roots.append(extra)
        texts = []

        def _take(path, cap=8 * 1024 * 1024):
            try:
                if os.path.getsize(path) > cap:
                    return
                with open(path, "rb") as fh:
                    text = fh.read().decode("utf-8", "ignore")
            except Exception:
                return
            if "爱KTV" in text or "KTV.py" in text:
                texts.append((path, text))

        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            for dirpath, dirs, files in os.walk(root):
                rel = dirpath[len(root):]
                if rel.count(os.sep) > 4:
                    dirs[:] = []
                for fn in files:
                    low = fn.lower()
                    if low.endswith(".json") or low.endswith(".txt"):
                        _take(os.path.join(dirpath, fn))
        for root in raw_roots:
            if not root or not os.path.isdir(root):
                continue
            for dirpath, dirs, files in os.walk(root):
                rel = dirpath[len(root):]
                if rel.count(os.sep) > 1:
                    dirs[:] = []
                for fn in files:
                    _take(os.path.join(dirpath, fn), cap=32 * 1024 * 1024)
        try:
            seen_json = 0
            for fn in os.listdir("/storage/emulated/0"):
                full = os.path.join("/storage/emulated/0", fn)
                if fn.lower().endswith(".json") and os.path.isfile(full):
                    _take(full)
                    seen_json += 1
                elif os.path.isdir(full) and seen_json < 300:
                    try:
                        for sub in os.listdir(full):
                            if sub.lower().endswith(".json"):
                                _take(os.path.join(full, sub))
                                seen_json += 1
                    except Exception:
                        pass
        except Exception:
            pass
        self._dlog("skey", "roots=%s raw=%s matched=%s"
                   % (roots, raw_roots, [t[0] for t in texts][:10]))
        for path, text in texts:
            if text.startswith("SQLite format 3") and not path.endswith(
                    ("-wal", "-shm")):
                k = self._site_key_from_db(path)
                if k:
                    self._dlog("skey", "found key=%s in db %s" % (k, path))
                    return k
            k = self._site_key_parse(text) or \
                self._site_key_parse_loose(text)
            if k:
                self._dlog("skey", "found key=%s in %s" % (k, path))
                return k
        self._dlog("skey", "key not found in scanned configs")
        return ""

    def _site_key_from_db(self, dbfile):
        tmpdir = None
        try:
            import shutil
            import tempfile
            tmpdir = tempfile.mkdtemp(prefix="ktvkey")
            dst = os.path.join(tmpdir, "tv.db")
            shutil.copy2(dbfile, dst)
            for suf in ("-wal", "-shm"):
                if os.path.exists(dbfile + suf):
                    try:
                        shutil.copy2(dbfile + suf, dst + suf)
                    except Exception:
                        pass
            con = sqlite3.connect(dst)
            try:
                tables = [r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]
                self._dlog("skey", "db tables=%s" % (tables,))
                KEYC = ("key", "sitekey", "site_key")
                NAMEC = ("name", "vodname", "vod_name", "title")
                APIC = ("api", "apiurl", "api_url", "link", "url")
                JSONC = ("json", "config", "text", "data", "value",
                         "content")

                def _pick(cols, cands):
                    low = [c.lower() for c in cols]
                    for cand in cands:
                        if cand in low:
                            return cols[low.index(cand)]
                    return ""

                for t in tables:
                    qt = '"' + t.replace('"', '""') + '"'
                    try:
                        cols = [c[1] for c in con.execute(
                            "PRAGMA table_info(%s)" % qt)]
                    except Exception:
                        continue
                    kc = _pick(cols, KEYC)
                    if not kc:
                        continue
                    nc = _pick(cols, NAMEC)
                    ac = _pick(cols, APIC)
                    wh, params = [], []
                    if nc:
                        wh.append('"%s" LIKE ?' % nc)
                        params.append("%爱KTV%")
                    if ac:
                        wh.append('"%s" LIKE ?' % ac)
                        params.append("%KTV.py%")
                    if not wh:
                        continue
                    try:
                        rows = con.execute(
                            'SELECT "%s" FROM %s WHERE (%s) LIMIT 5'
                            % (kc, qt, " OR ".join(wh)), params).fetchall()
                    except Exception:
                        continue
                    for r in rows:
                        if r and r[0]:
                            self._dlog("skey", "db hit table=%s key=%s"
                                       % (t, r[0]))
                            return str(r[0])
                for t in tables:
                    qt = '"' + t.replace('"', '""') + '"'
                    try:
                        cols = [c[1] for c in con.execute(
                            "PRAGMA table_info(%s)" % qt)]
                    except Exception:
                        continue
                    jc = _pick(cols, JSONC)
                    if not jc:
                        continue
                    try:
                        rows = con.execute(
                            'SELECT "%s" FROM %s WHERE "%s" LIKE ? LIMIT 3'
                            % (jc, qt, jc), ("%爱KTV%",)).fetchall()
                    except Exception:
                        continue
                    for r in rows:
                        if r and r[0]:
                            k = self._site_key_parse(str(r[0])) or \
                                self._site_key_parse_loose(str(r[0]))
                            if k:
                                self._dlog("skey", "db json hit table=%s "
                                           "key=%s" % (t, k))
                                return k
            finally:
                con.close()
        except Exception as e:
            self._dexc("skey db", e)
        finally:
            if tmpdir:
                try:
                    import shutil
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
        return ""

    def _site_key_parse(self, text):
        try:
            obj = json.loads(text)
        except Exception:
            return ""
        if not isinstance(obj, dict):
            return ""
        sites = obj.get("sites")
        if not isinstance(sites, list):
            return ""
        for st in sites:
            if not isinstance(st, dict) or not st.get("key"):
                continue
            blob = " ".join(str(st.get(k) or "")
                            for k in ("name", "api", "ext"))
            if "爱KTV" in blob or "KTV" in blob:
                return str(st["key"])
        return ""

    def _site_key_parse_loose(self, text):
        try:
            poss = [m.start() for m in re.finditer(r"KTV\.py", text)]
            poss += [m.start() for m in re.finditer("\u7231KTV", text)]
            for pos in poss:
                pre = text[max(0, pos - 400):pos]
                km = None
                for mm in re.finditer(r'"key"\s*:\s*"([^"]{1,64})"', pre):
                    km = mm
                if km:
                    return km.group(1)
                post = text[pos:pos + 400]
                km = re.search(r'"key"\s*:\s*"([^"]{1,64})"', post)
                if km:
                    return km.group(1)
        except Exception:
            pass
        return ""

    def _intent_video(self, ctx, key, detail_id, name, pic):
        from java import jclass
        try:
            Cls = jclass("java.lang.Class")
            Intent = jclass("android.content.Intent")
        except Exception:
            return False
        pkg = ""
        try:
            pkg = str(ctx.getPackageName())
        except Exception:
            pkg = ""
        cands = []
        for cand in ("com.fongmi.android.tv.ui.activity.VideoActivity",
                     (pkg + ".ui.activity.VideoActivity") if pkg else ""):
            if cand and cand not in cands:
                cands.append(cand)
        self._dlog("intent", "pkg=%s key=%s id=%s cands=%s"
                   % (pkg, key, detail_id, cands))
        for cls in cands:
            try:
                Cls.forName(cls)
            except Exception:
                self._dlog("intent", "class not found: %s" % cls)
                continue
            try:
                it = Intent()
                it.setClassName(pkg, cls)
                it.putExtra("key", key)
                it.putExtra("id", detail_id)
                it.putExtra("name", name or "")
                it.putExtra("pic", pic or "")
                it.putExtra("mark", "")
                it.addFlags(0x10000000)
                ctx.startActivity(it)
                self.log("remote play intent key=%s id=%s" % (key, detail_id))
                self._dlog("intent", "startActivity sent: %s" % cls)
                return True
            except Exception as e:
                self.log("remote play intent fail: %s" % e)
                self._dexc("intent", e)
        return False

    def _intent_view(self, ctx, url):
        from java import jclass
        try:
            Intent = jclass("android.content.Intent")
            Uri = jclass("android.net.Uri")
        except Exception as e:
            self._dexc("intent view import", e)
            return False
        pkg = ""
        try:
            pkg = str(ctx.getPackageName())
        except Exception:
            pkg = ""
        for use_pkg in (True, False):
            try:
                it = Intent(Intent.ACTION_VIEW)
                it.setDataAndType(Uri.parse(url), "video/*")
                if use_pkg and pkg:
                    it.setPackage(pkg)
                it.addFlags(0x10000000)
                ctx.startActivity(it)
                self._dlog("intent", "view sent pkg=%s: %s"
                           % (pkg if use_pkg else "", url[:80]))
                return True
            except Exception as e:
                self._dexc("intent view pkg=%s" % use_pkg, e)
        return False

    def _app_ctx(self):
        try:
            from java import jclass
        except Exception as e:
            self._dexc("ctx import java", e)
            return None
        self._dlog("ctx", "import java ok")
        try:
            AT = jclass("android.app.ActivityThread")
            ctx = AT.currentApplication()
            self._dlog("ctx", "ActivityThread ctx=%s" % ctx)
            if ctx is not None:
                return ctx
        except Exception as e:
            self._dexc("ctx activitythread", e)
        try:
            AG = jclass("android.app.AppGlobals")
            ctx = AG.getInitialApplication()
            self._dlog("ctx", "AppGlobals ctx=%s" % ctx)
            if ctx is not None:
                return ctx
        except Exception as e:
            self._dexc("ctx appglobals", e)
        try:
            Python = jclass("com.chaquo.python.Python")
            ctx = Python.getPlatform().getApplication()
            self._dlog("ctx", "chaquo platform ctx=%s" % ctx)
            if ctx is not None:
                return ctx
        except Exception as e:
            self._dexc("ctx chaquo", e)
        return None

    def _remote_play(self, detail_id, name="", pic="", num=0):
        self._dlog("play", "remote_play id=%s name=%s num=%s"
                   % (detail_id, name, num))
        ctx = self._app_ctx()
        if ctx is None:
            self._dlog("play", "no app context, abort")
            return False, "当前环境不支持远程播放（细节看诊断日志）"
        key = ""
        try:
            key = self._site_key()
        except Exception as e:
            self._dexc("play skey", e)
        self._dlog("play", "site key=%r" % key)
        if key:
            if self._intent_video(ctx, key, detail_id, name, pic):
                if num:
                    _KSVC["now"] = int(num)
                return True, "已让前端播放：%s" % (name or detail_id)
        if num:
            url = ""
            try:
                url, _sg = self.get_play_url(int(num))
            except Exception as e:
                self._dexc("play geturl", e)
            self._dlog("play", "fallback view url=%s" % ((url or "")[:80]))
            if url and self._intent_view(ctx, url):
                _KSVC["now"] = int(num)
                return True, "已用系统播放器打开：%s" % (name or "")
        return False, "没能启动前端播放，请在电视上点开始播放"

    def _api_play(self, number):
        try:
            num = int(number)
        except Exception:
            return False, "歌曲编号不对"
        rows = self.query(
            "SELECT number,name,singer_names,language_id,temperature "
            "FROM song WHERE number=?", (num,))
        if not rows:
            return False, "曲库里没有这首歌"
        r = rows[0]
        try:
            self._queue_add(num)
        except Exception:
            pass
        pic = ""
        try:
            pic = self.song_card(r).get("vod_pic") or ""
        except Exception:
            pic = ""
        return self._remote_play("s%d" % num, r["name"] or "", pic, num)

    def _play_next(self):
        q = self._queue_get()
        if not q:
            return False, "队列是空的"
        now = 0
        try:
            now = int(_KSVC.get("now") or 0)
        except Exception:
            now = 0
        idx = -1
        for i, x in enumerate(q):
            if int(x.get("number") or 0) == now:
                idx = i
                break
        if idx < 0:
            nxt = q[0]
        elif idx < len(q) - 1:
            nxt = q[idx + 1]
        else:
            return False, "已是最后一首"
        num = int(nxt.get("number") or 0)
        return self._remote_play("s%d" % num, nxt.get("name") or "", "", num)


    def _qr_pic_url(self):
        return "%s&type=qr" % self.proxy_url()

    def _qr_png_bytes(self):
        url = self._ksvc_url()
        cache = _KSVC["qr"]
        if cache.get("url") == url and cache.get("body"):
            return cache["body"]
        body = None
        try:
            import io
            import qrcode
            img = qrcode.make(url)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            if len(buf.getvalue()) > 500:
                body = buf.getvalue()
        except Exception:
            body = None
        if not body:
            try:
                import urllib.request
                api = ("https://api.qrserver.com/v1/create-qr-code/"
                       "?size=480x480&margin=12&data="
                       + _quote(url, safe=""))
                req = urllib.request.Request(
                    api, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = r.read()
                if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 500:
                    body = data
            except Exception:
                body = None
        if not body:
            try:
                body = self._qr_png_zxing(url)
            except Exception:
                body = None
        if body:
            _KSVC["qr"] = {"url": url, "body": body}
        return body

    def _qr_png_zxing(self, url):
        from java import jclass
        Writer = jclass("com.google.zxing.qrcode.QRCodeWriter")
        Fmt = jclass("com.google.zxing.BarcodeFormat")
        Hint = jclass("com.google.zxing.EncodeHintType")
        EC = jclass("com.google.zxing.qrcode.decoder.ErrorCorrectionLevel")
        Hashtable = jclass("java.util.Hashtable")
        hints = Hashtable()
        hints.put(Hint.ERROR_CORRECTION, EC.M)
        hints.put(Hint.MARGIN, 2)
        hints.put(Hint.CHARACTER_SET, "UTF-8")
        size = 480
        m = Writer().encode(url, Fmt.QR_CODE, size, size, hints)
        Bitmap = jclass("android.graphics.Bitmap")
        Config = jclass("android.graphics.Bitmap$Config")
        bmp = Bitmap.createBitmap(size, size, Config.ARGB_8888)
        pixels = []
        for y in range(size):
            for x in range(size):
                pixels.append(-16777216 if m.get(x, y) else -1)
        bmp.setPixels(pixels, 0, size, 0, 0, size, size)
        BAOS = jclass("java.io.ByteArrayOutputStream")
        Comp = jclass("android.graphics.Bitmap$CompressFormat")
        baos = BAOS()
        bmp.compress(Comp.PNG, 100, baos)
        data = baos.toByteArray()
        try:
            return bytes(data)
        except Exception:
            return bytes(bytearray(data))


    # ------------------------------------------------- 数据库版本 / 更新

    def _db_version(self, path):
        """读库旁边的 .version 文件，返回版本号字符串（没有就空串）。"""
        try:
            vf = os.path.splitext(path)[0] + ".version"
            if os.path.isfile(vf):
                with open(vf, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read().strip()[:32]
        except Exception:
            pass
        return ""

    def _db_mtime(self, path):
        """返回库文件的修改时间字符串，失败返回空串。"""
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
        except Exception:
            return ""

    # ------------------------------------------------ Gulu 同步库定位
    GULU_PKGS = ("com.gulu.music.tw", "com.gulu.music.tv", "cn.guluplus.com")

    def _gulu_roots(self):
        """同步库候选目录。"""
        roots = []
        bases = ["/storage/emulated/0", "/sdcard"]
        # 其他用户 / 其他存储卷（如 SD 卡 /storage/XXXX-XXXX）
        try:
            for n in os.listdir("/storage"):
                if n != "emulated" and n != "self":
                    bases.append(os.path.join("/storage", n))
        except Exception:
            pass
        for base in bases:
            roots.append(os.path.join(base, "WebHTV", "LocalFiles", "files-文件", "db"))
            try:
                for n in os.listdir(base):
                    if "gulu" in n.lower() or "glyco" in n.lower() \
                            or "WebHTV" in n or "iktv" in n.lower():
                        roots.append(os.path.join(base, n))
            except Exception:
                pass
        roots += ["/storage/emulated/0/TVData/db"]
        for pk in self.GULU_PKGS:
            for base in ("/storage/emulated/0/Android/data", "/sdcard/Android/data"):
                roots.append(os.path.join(base, pk, "files"))
        # 去重保序
        out, seen = [], set()
        for r in roots:
            k = os.path.normpath(r)
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out

    @staticmethod
    def _looks_gulu(p):
        """路径是否像 Gulu 的落盘位置（它自己的目录 / 包名目录）。"""
        q = p.lower()
        for k in ("gulu", "glyco", "glyco", "iktv", "guluplus"):
            if k in q:
                return True
        for k in ("/webhtv/", "/ikmusic/", "/ik_karaoke/"):
            if k in q:
                return True
        return False

    def _find_gulu_db(self, cur=""):
        """定位同步库。"""
        try:
            curreal = os.path.realpath(cur) if cur else ""
        except Exception:
            curreal = ""
        cands = {}   # 路径 -> 是否疑似 Gulu
        # a. DB_HINTS 常驻位置（快，先来）
        for d in self.DB_HINTS:
            p = os.path.join(d, "song_9c8ec.db")
            try:
                if os.path.isfile(p):
                    cands[os.path.realpath(p)] = False
            except Exception:
                pass
        # b. 深扫 Gulu 根目录
        for r in self._gulu_roots():
            try:
                for dirpath, dirnames, filenames in os.walk(r):
                    if dirpath.count(os.sep) - r.count(os.sep) > 5:
                        dirnames[:] = []
                        continue
                    dirnames[:] = [x for x in dirnames
                                   if not x.startswith(".git") and x != "cache"]
                    for fn in filenames:
                        if fn.startswith("song_9c8ec.db") and \
                                "download" not in fn:
                            fp = os.path.join(dirpath, fn)
                            try:
                                cands[os.path.realpath(fp)] = False
                            except Exception:
                                pass
            except Exception:
                pass
        # c. 逐个定指纹
        vers = {}
        for p in list(cands.keys()):
            if p == curreal:
                continue
            try:
                vp = os.path.join(os.path.dirname(p), "song_9c8ec.version")
                if os.path.isfile(vp):
                    try:
                        with open(vp, "r", encoding="utf-8",
                                  errors="ignore") as f:
                            vers[p] = f.read().strip()[:24]
                    except Exception:
                        vers[p] = ""
                    cands[p] = True
                    continue
                if self._looks_gulu(p):
                    cands[p] = True
            except Exception:
                pass
        return cands, vers

    def _db_update_info(self):
        """给出当前库的版本/时间/歌数，以及 Gulu 自动同步的那一份。"""
        try:
            cur = str(self._cfg_get().get("db") or DB_PATH)
        except Exception:
            cur = ""
        info = {"cur": cur, "cur_ver": self._db_version(cur),
                "cur_time": self._db_mtime(cur), "cur_cnt": 0,
                "sync": "", "sync_ver": "", "sync_time": "", "sync_cnt": 0,
                "newer": 0, "msg": "", "title": "📦 数据库更新", "remark": "",
                "body": ""}
        try:
            info["cur_cnt"] = self._probe_db(cur) or 0
        except Exception:
            pass

        cands, vers = self._find_gulu_db(cur)
        gulu = [p for p, g in cands.items() if g]
        others = [p for p, g in cands.items() if not g]

        def _mt(p):
            try:
                return os.path.getmtime(p)
            except Exception:
                return 0

        # 同步库：优先 Gulu 指纹命中里最新的一份
        best = ""
        if gulu:
            best = max(gulu, key=_mt)
        elif others:
            # 一个指纹都没命中 → 标出「疑似」但说明
            best = max(others, key=_mt)
            info["msg"] = "疑似"
        info["sync"] = best
        if best:
            info["sync_ver"] = vers.get(best) or self._db_version(best)
            info["sync_time"] = self._db_mtime(best)
            try:
                info["sync_cnt"] = self._probe_db(best) or 0
            except Exception:
                pass
            try:
                curreal = os.path.realpath(cur) if cur else ""
            except Exception:
                curreal = ""
            if curreal and os.path.realpath(best) == curreal:
                info["sync"] = ""
                best = ""
                info["sync_ver"] = info["sync_time"] = ""
                info["sync_cnt"] = 0

        # 顺带算出「另一个库」列表，给用户看全貌
        try:
            curreal = os.path.realpath(cur) if cur else ""
        except Exception:
            curreal = ""
        info["others"] = [p for p in others
                          if os.path.realpath(p) != curreal]
        info["same"] = bool(best) and vers.get(best) == info["cur_ver"]
        if not best:
            # 没有别的库可切：判断当前这份是不是 Gulu 的（固定路径 + 指纹）
            try:
                is_g = (os.path.realpath(cur) == os.path.realpath(GULU_DB)
                        or self._looks_gulu(cur or ""))
            except Exception:
                is_g = self._looks_gulu(cur or "")
            info["msg"] = ("当前用的就是 Gulu 同步的那一份（固定路径），"
                           "Gulu 后台更新后会自动跟上"
                           if is_g else
                           "当前库不是 Gulu 的；Gulu 的库在 %s" % GULU_DB)

        ver = info["cur_ver"] or "未知"
        if not best:
            info["newer"] = 0
            info["title"] = "📦 数据库更新"
            info["remark"] = "版本 %s · %s · %s 首" % (
                ver, info["cur_time"] or "?", info["cur_cnt"] or "?")
            lines = ["当前库", "  %s" % (cur or "（未设置）"),
                     "  版本 %s · %s 首" % (ver, info["cur_cnt"] or "?"),
                     "  更新于 %s" % (info["cur_time"] or "?"),
                     "", "结论", "  " + info["msg"]]
            if info["others"]:
                lines += ["", "别的库（不是 Gulu 的）"]
                lines += ["  " + p for p in info["others"][:4]]
            info["body"] = "\n".join(lines)
            return info

        # 时间比较：mtime 决定新旧；时间打平但有版本文件时用版本号
        try:
            tc = os.path.getmtime(cur) if os.path.isfile(cur) else 0
        except Exception:
            tc = 0
        tb = _mt(best)
        def _vk(v):
            try:
                return tuple(int(x) for x in str(v).split("."))
            except Exception:
                return ()
        if tb > tc + 1:
            info["newer"] = 1
            info["msg"] = "Gulu 同步库比当前库新"
        elif tb < tc - 1:
            info["newer"] = -1
            info["msg"] = "当前库比 Gulu 同步库新"
        else:
            vc, vb = _vk(info["cur_ver"]), _vk(info["sync_ver"])
            if vb and vc and vb > vc:
                info["newer"] = 1
                info["msg"] = "Gulu 同步库版本更高（%s > %s）" % (
                    info["sync_ver"], info["cur_ver"])
            elif vb and vc and vb < vc:
                info["newer"] = -1
                info["msg"] = "当前库版本更高（%s > %s）" % (
                    info["cur_ver"], info["sync_ver"])
            else:
                info["newer"] = 0
                info["msg"] = "两边版本和时间一致"

        if info["newer"] == 1:
            info["title"] = "📦 数据库更新：有新库"
        elif info["newer"] == -1:
            info["title"] = "📦 数据库更新：当前库更新"
        else:
            info["title"] = "📦 数据库更新：已是最新"
        info["remark"] = "版本 %s · %s · %s 首" % (
            ver, info["cur_time"] or "?", info["cur_cnt"] or "?")
        tag = "" if info["sync_ver"] else "（未标版本）"
        lines = ["当前库", "  %s" % (cur or "（未设置）"),
                 "  版本 %s · %s 首" % (ver, info["cur_cnt"] or "?"),
                 "  更新于 %s" % (info["cur_time"] or "?"),
                 "", "Gulu 同步库" + tag, "  %s" % best,
                 "  版本 %s · %s 首" % (info["sync_ver"] or "未知",
                                       info["sync_cnt"] or "?"),
                 "  更新于 %s" % (info["sync_time"] or "?"),
                 "", "结论", "  " + (info["msg"] or "—")]
        if info["others"]:
            lines += ["", "别的库（不是 Gulu 的）"]
            lines += ["  " + p for p in info["others"][:4]]
        if info["newer"] == 1:
            lines += ["", "点「确定」切换到 Gulu 同步库"]
        info["body"] = "\n".join(lines)
        return info

    # ------------------------------------------------------------ 详情

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) else ids
        raw = str(raw or "").strip().split("#")[0]
        # ---- 🔍搜索操作卡：弹框后原页刷新（返回分类列表而非详情，壳不开播放页）
        if raw.startswith("kw:"):
            self.log("detail kw branch raw=%s" % raw)
            if raw == "kw:input":
                self._kw_ask()
                return self._page([self._kw_note("🔍搜索 · 输入关键词")], 1)
            if raw == "kw:clear":
                self._kw_set("")
                return self._page([self._kw_note("🔍搜索 · 已清除")], 1)
            if raw == "kw:count":
                self._kw_stat()
                kw = self._kw_get()
                return self._page([self._kw_note("📊 搜索统计 · %s" % (kw or "-"))], 1)
            return self._page([self._kw_note("🔍搜索")], 1)
        if raw.startswith("queue:") or raw.startswith("ksvc:"):
            if raw == "queue:clear":
                self._queue_clear()
            elif raw == "queue:pop":
                self._queue_remove(0)
            elif raw in ("ksvc:head", "ksvc:qr"):
                self._handle_setting("ksvcqr")
            return self._page([self._note_card(
                "queue:note", "🎤 点歌队列", "返回点歌队列分类下拉刷新")], 1)
        if raw.startswith("set:"):
            self._handle_setting(raw[4:])
            # 返回一张无 action、非 folder 的提示卡。不能返回 _settings_page：
            # 壳拿到列表会拿第一条的 vod_id 当待播项，出现「跳到播放页」。
            c = self._note_card("set:done", "✓ 设置已处理", "返回上一页查看结果",
                                "设置项已处理。若刚改了路径/端口，重新进设置页看当前值。")
            return {"code": 1, "msg": "详情", "list": [c], "page": 1,
                    "pagecount": 1, "limit": 20, "total": 1}
        if raw == "qplay":
            return self._queue_play_detail()
        if not raw.startswith("s"):
            return {"code": 0, "msg": "无数据", "list": []}
        m = re.match(r'^s(\d+)', raw)
        if not m:
            return {"code": 0, "msg": "无数据", "list": []}
        num = int(m.group(1))
        rows = self.query("SELECT number,name,singer_names,language_id,type_id,temperature,"
                          "edition,mtv_or_vcd FROM song WHERE number=?", (num,))
        if not rows:
            return {"code": 0, "msg": "无数据", "list": []}
        r = rows[0]
        singers = self._song_singers(r["singer_names"])
        pic = self._song_cover(singers)
        lang = LANGS.get(r.get("language_id"), "")
        typ = self._types().get(r.get("type_id"), "")
        vod = {
            "vod_id": "s%d" % num,
            "vod_name": r["name"],
            "vod_pic": pic,
            "type_name": lang,
            "vod_year": "",
            "vod_area": "",
            "vod_lang": lang,
            "vod_remarks": typ or "KTV",
            "vod_actor": r["singer_names"],
            "vod_director": "",
            "vod_content": "原唱：%s\n曲风：%s\n版本：%s\n编号：%d" % (
                r["singer_names"], typ or "流行", r.get("edition") or "DVD", num),
            "vod_play_from": "爱KTV",
            "vod_play_url": self._play_url(r["name"], num),
        }
        return {"code": 1, "msg": "数据列表", "list": [vod],
                "page": 1, "pagecount": 1, "limit": 1, "total": 1}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(int(str(pg) or "1"), 1)
        except Exception:
            page = 1
        raw = str(key or "").strip()
        if not raw:
            return {"code": 0, "msg": "无数据", "list": []}
        size = 30
        off = (page - 1) * size

        # 多关键词：空格 / 逗号 / 顿号 / 竖线 / 加号 都当分隔符。
        # "屠洪刚 你" → 两个词，每个词都要在 歌名 或 歌手 里出现（AND）。
        import re as _re
        words = [w for w in _re.split(u"[\\s,，、|+/]+", raw) if w]
        if not words:
            words = [raw]

        def _esc(w):
            return w.replace("%", "").replace("_", "").replace("'", "''")

        where, args = ["status=1"], []
        for w in words:
            lk = "%" + _esc(w) + "%"
            where.append("(name LIKE ? OR singer_names LIKE ?)")
            args.extend([lk, lk])
        sql = ("SELECT number,name,singer_names,language_id,temperature FROM song "
               "WHERE " + " AND ".join(where) + " ")
        # 排序：歌名完全等于搜索词的排最前（"你" 直接命中屠洪刚那首），
        # 其次看热度。多关键词时按词序逐级判等。
        order, args_order = [], []
        if len(words) == 1:
            order.append("CASE WHEN name=? THEN 0 ELSE 1 END")
            args_order.append(words[0])
        else:
            for w in words:
                order.append("CASE WHEN name=? THEN 0 ELSE 1 END")
                args_order.append(w)
        order.append("CASE WHEN temperature IS NULL THEN 1 ELSE 0 END")
        order.append("temperature DESC")
        order.append("number DESC")
        sql += "ORDER BY " + ", ".join(order) + " LIMIT ? OFFSET ?"

        rows = []
        try:
            rows = self.query(sql, tuple(args) + tuple(args_order) + (size, off))
        except Exception as e:
            self.log("search fail: %s" % type(e).__name__)
        _total = self._count_songs(where, args)
        # 多词 AND 一条都没命中时，退回 OR（尽力而为，不返回空白）
        if not rows and len(words) > 1:
            where2, args2 = ["status=1"], []
            ors = []
            for w in words:
                lk = "%" + _esc(w) + "%"
                ors.append("(name LIKE ? OR singer_names LIKE ?)")
                args2.extend([lk, lk])
            where2.append("(" + " OR ".join(ors) + ")")
            try:
                rows = self.query(
                    "SELECT number,name,singer_names,language_id,temperature "
                    "FROM song WHERE " + " AND ".join(where2) + " "
                    "ORDER BY CASE WHEN temperature IS NULL THEN 1 ELSE 0 END, "
                    "temperature DESC, number DESC LIMIT ? OFFSET ?",
                    tuple(args2) + (size, off))
                self.log("search '%s' AND miss -> OR %d" % (raw, len(rows)))
            except Exception:
                rows = []
        # ---- 拼音容错层：字打错了也能搜到（只在精确层全空时启用，保证正确结果在前）----
        self._py_hit = ""
        self._py_names = []
# 纯字母词无条件合并拼音层；含中文词只在精确 0 条时容错。
# 「命中少」不能当触发条件，否则「周杰伦 晴天」会被泛结果盖掉。
        pure_alpha = bool(re.match(r'^[A-Za-z]+$', raw)) and len(raw) >= 2
        if not rows or pure_alpha:
            prows, ptotal, hnames = self._search_by_pinyin(words, size, off, page)
            if prows:
                if rows and pure_alpha:
                    # 合并去重：拼音结果在前（更贴合），精确层的零散命中垫后
                    seen = set()
                    merged = []
                    for r in list(prows) + list(rows):
                        k = r["number"]
                        if k in seen:
                            continue
                        seen.add(k)
                        merged.append(r)
                    rows = merged[:size]
                    _total = max(ptotal, _total)
                    self.log("search '%s' -> pinyin+exact merged %d" % (raw, len(rows)))
                else:
                    rows, _total = prows, ptotal
                if hnames:
                    # 首个是主命中（排第一那位歌手），全部名字另存一份给统计卡展示
                    self._py_hit = hnames[0]
                    self._py_names = list(hnames)
                    self.log("search '%s' -> pinyin %s (%d tiao)"
                             % (raw, "/".join(hnames[:3]), ptotal))
        if not rows:
            # 精确层和拼音层都没东西，总数就是 0（别把中途 OR 退路的计数漏出去）
            _total = 0
        return self._song_page(rows, page, size, "搜索", total=_total)

    # ------------------------------------------------------------ 拼音容错

    def _count_songs(self, where, args):
        try:
            r = self.query("SELECT COUNT(*) AS c FROM song WHERE " + " AND ".join(where), tuple(args))
            return int(r[0]["c"]) if r else 0
        except Exception:
            return 0

    def _pinyin_singers(self, words, limit=24):
        """关键词转拼音首字母。"""
        # 只取常用读音（每个字的首读音）。多音字的生僻读音看着能扩大覆盖，
        # 实际误伤更大：红->gōng 会让「屠红刚」变成 TGG，命中「土狗哥」。
        cands = []
        for w in words:
            for ac in to_acronym(w)[:1]:
                if len(ac) >= 2 and ac not in cands:
                    cands.append(ac)
        if not cands:
            return []
# 候选按字典读音顺序取第一个，多音字的生僻读音不参与。
        stat = [(0, i, ac) for i, ac in enumerate(cands)]
        stat.sort(key=lambda x: x[1])
        exact, near = [], []
        for _, _i, ac in stat:
            try:
                rs = self.query(
                    "SELECT name,acronym FROM singer WHERE acronym=? LIMIT ?", (ac, limit))
            except Exception:
                rs = []
            for r in rs:
                if r["name"] not in exact:
                    exact.append(r["name"])
# 精确全 miss 时才前缀兜底，且要求前缀长度接近，避免拉进无关歌手。
        if not exact:
            for _, _i, ac in stat[:2]:
                try:
                    rs = self.query(
                        "SELECT name,acronym FROM singer WHERE acronym LIKE ? LIMIT 8",
                        (ac + "%",))
                except Exception:
                    rs = []
                for r in rs:
                    other = (r["acronym"] or "").upper()
                    # 只接受「前缀相同、且总长一致」的：ZJL 命中 ZJLX 这种同名截断
                    # 直接丢掉 ZJLX 之外的（庄心妍 ZXY 是被 ZXY 前缀拉进来的，属于噪声）
                    if len(other) == len(ac) and r["name"] not in near:
                        near.append(r["name"])
        return (exact + near[:6])[:limit]

    def _search_by_pinyin(self, words, size, off, page):
        """拼音容错搜索。"""
        names = self._pinyin_singers(words)
        where, wargs = ["status=1"], []      # WHERE 的参数
        oargs, order = [], ["CASE WHEN temperature IS NULL THEN 1 ELSE 0 END",
                            "temperature DESC", "number DESC"]
# 纯字母词还要查歌名首字母 song.acronym（QT→《晴天》）。
        acs_song = []
        for w in words:
            ww = str(w).strip().upper()
            if re.match(r'^[A-Z]+$', ww) and 1 < len(ww) <= 6 and ww not in acs_song:
                acs_song.append(ww)
# 歌名首字母与歌手名是「或」关系，必须并进同一个 OR 块。
        ors_all = []
        if acs_song:
            for ac in acs_song:
                ors_all.append("acronym=?")
                wargs.append(ac)
            # 歌名首字母命中排在歌手命中之后（歌手匹配更准：
            # ZJL 的《周杰伦》不该压过周杰伦本人的歌）
            order.append("CASE WHEN acronym IN (%s) THEN 0 ELSE 1 END"
                         % ",".join(["'%s'" % ac for ac in acs_song]))
            self.log("pinyin: song.acronym %s" % "/".join(acs_song))
        # 歌手名匹配：acronym 精确等于关键词的歌手，按候选顺序加权
        if names:
            wcase = ["CASE"]
            for idx, nm in enumerate(names):
                pat = "%" + nm.replace("%", "").replace("_", "") + "%"
                ors_all.append("singer_names LIKE ?")
                wargs.append(pat)
                wcase.append("WHEN singer_names LIKE ? THEN %d" % idx)
                oargs.append(pat)
            wcase.append("ELSE 999 END")
            order.append(" ".join(wcase))
        if ors_all:
            where.append("(" + " OR ".join(ors_all) + ")")
        if not acs_song and not names:
            # 中文词兜底：转首字母后按 song.acronym 前缀找歌名
            acs = []
            for w in words:
                for ac in to_acronym(w)[:3]:
                    if len(ac) >= 2 and ac not in acs:
                        acs.append(ac)
            if not acs:
                return [], 0, []
            ors = []
            for ac in acs:
                ors.append("acronym LIKE ?")
                wargs.append("%" + ac + "%")
            where.append("(" + " OR ".join(ors) + ")")
        sql = ("SELECT number,name,singer_names,language_id,temperature FROM song "
               "WHERE " + " AND ".join(where) + " "
               "ORDER BY " + ", ".join(order) + " LIMIT ? OFFSET ?")
        try:
            rows = self.query(sql, tuple(wargs) + tuple(oargs) + (size, off))
        except Exception as e:
            self.log("pinyin search fail: %s" % type(e).__name__)
            rows = []
        return rows, self._count_songs(where, wargs), names

    # ------------------------------------------------------------ 播放串

    def _play_url(self, name, num):
        """播放地址。"""
        return "%s$play%s" % (name, num)

    # ------------------------------------------------------------ 播放

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "")
        m = re.match(r'^play(\d+)$', raw)
        if not m:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        num = int(m.group(1))
        url, err = self.get_play_url(num)
        # URL 缓存里那份失效（"Error" = auth_key 过期 / 签名服务临时抽风）时，
        # 丢掉缓存、强制重签一次再给。壳黑屏多半是复用了过期的直链。
        if not url:
            self._url_cache.pop(num, None)
            self._sig_cache = ("", 0)
            url, err = self.get_play_url(num)
        if not url:
            self.log("播放获取失败: %s" % err)
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
# 直送 mkv 原文件，音轨由播放器菜单切换，不转码。
        self.log("playerContent num=%s -> direct" % m.group(1))
        return {"parse": 0, "playUrl": "", "url": url,
                "header": {"User-Agent": _ua()}}

    def _fetch_singer_img(self, name, save_path):
        """取歌手头像写入本地，返回 bytes；失败返回 None。"""
        name = str(name or "").strip()
        if not name:
            return None
        try:
            import requests
        except Exception:
            return None

        UA_WEB = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        def _get(url, ref=None, timeout=10):
            h = {"User-Agent": UA_WEB}
            if ref:
                h["Referer"] = ref
            try:
                r = requests.get(url, headers=h, timeout=timeout)
                return r.text if r.status_code == 200 else None
            except Exception:
                return None

        def _img(url, ref=None):
            """下载图片，校验是真正的 JPEG/PNG 且够大。"""
            h = {"User-Agent": UA_WEB}
            if ref:
                h["Referer"] = ref
            try:
                r = requests.get(url, headers=h, timeout=12)
                b = r.content
                if r.status_code != 200 or len(b) < 3000:
                    return None
                if b[:2] == b"\xff\xd8" or b[:8] == b"\x89PNG\r\n\x1a\n":
                    return b
            except Exception:
                pass
            return None

        def _pick(text, pat, group=1):
            m = re.search(pat, text or "", re.S)
            return m.group(group) if m else ""

        # ---------------- 1. 酷我 ----------------
        # 返回体是单引号的类 JSON，Python 能直接 eval 出来
        t = _get("http://search.kuwo.cn/r.s?all=%s&ft=artist&rn=8&encoding=utf8"
                 "&rformat=json" % _quote(name), ref="http://www.kuwo.cn/")
        if t:
            base = _pick(t, r"'BASEPICPATH':'([^']*)'")
            # 必须按条目独立解析：用跨条目的 .*? 正则会错位
            #（PICPATH 会匹配到下一条的图，名字和图片对不上）。
            cand = []
            for blk in re.findall(r"\{'AARTIST'.*?\}", t, re.S)[:10]:
                pp = _pick(blk, r"'PICPATH':'([^']*)'")
                # [^A-Z] 挡住 'AARTIST'：裸 'ARTIST' 会把它也匹配上
                nm = _pick(blk, r"[^A-Z]ARTIST':'([^']*)'")
                if pp and nm:
                    cand.append((_html_unescape(nm).strip(), pp))
            # 只认精确同名。酷我对不存在的名字会返回一堆模糊结果
            # （查「XX不存在」能返回「凤凰FM」「浮音」），取第一条会写进别人的头像。
            hit = None
            for nm, pp in cand:
                if _name_eq(nm, name):
                    hit = pp
                    break
            if hit and base:
                b = _img(base + hit, ref="http://www.kuwo.cn/")
                if b:
                    return self._save_img(b, save_path, name, "kuwo")

        # ---------------- 2. 酷狗 ----------------
        t = _get("http://mobilecdn.kugou.com/api/v3/search/singer?keyword=%s"
                 "&page=1&pagesize=5" % _quote(name))
        sid = ""
        if t:
            # 优先取 singername 与目标完全一致的，否则取第一条
            pairs = re.findall(r'\{"singername":"([^"]*)","singerid":(\d+)\}', t)
            for nm, i in pairs:
                if _name_eq(nm, name):
                    sid = i
                    break
        if sid:
            t2 = _get("http://mobilecdn.kugou.com/api/v3/singer/info?singerid=%s" % sid)
            url = _pick(t2, r'"imgurl":"([^"]*)"') if t2 else ""
            if url:
                url = url.replace("{size}", "400")
                b = _img(url, ref="https://www.kugou.com/")
                if b:
                    return self._save_img(b, save_path, name, "kugou")

        # ---------------- 3. QQ音乐 ----------------
        t = _get("https://c.y.qq.com/soso/fcgi-bin/client_search_cp?p=1&n=5&w=%s"
                 % _quote(name), ref="https://y.qq.com/")
        mid = ""
        if t:
            pairs = re.findall(r'"mid":"([0-9A-Za-z]{10,})","name":"([^"]*)"', t)
            for m_, nm in pairs:
                if _name_eq(nm, name):
                    mid = m_
                    break
        if mid:
            b = _img("https://y.gtimg.cn/music/photo_new/T001R300x300M000%s.jpg" % mid,
                     ref="https://y.qq.com/")
            if b:
                return self._save_img(b, save_path, name, "qq")

        # ---------------- 4. 网易云 ----------------
        t = _get("http://music.163.com/api/search/get/web?s=%s&type=100&limit=1"
                 % _quote(name), ref="http://music.163.com/")
        pic = ""
        for blk in re.findall(r'\{[^{}]*"picUrl":"[^"]*"[^{}]*\}', t or "")[:10]:
            an = _pick(blk, r'"name":"([^"]*)"')
            if _name_eq(an, name):
                pic = _pick(blk, r'"picUrl":"([^"]*)"') or ""
                break
        if pic:
            if pic.endswith(".jpg") or "?" not in pic:
                pic += "?param=300y300"
            b = _img(pic, ref="http://music.163.com/")
            if b:
                return self._save_img(b, save_path, name, "163")

        self.log("fetch img: %s 四源均无图" % name)
        return None

    def _save_img(self, blob, save_path, name, src):
        """统一压到 300x300 JPEG（q85），落盘并返回。"""
        blob = _shrink_img(blob)
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(blob)
        except Exception as e:
            self.log("fetch img: %s 写盘失败 %s" % (name, e))
            return None
        self.log("fetch img: %s OK %dB via %s" % (name, len(blob), src))
        return blob

    def localProxy(self, params):
        """歌手图代理：从本地图库取 md5(歌手名) 对应的封面。"""
        params = params or {}
        if str(params.get("type") or "") == "qr":
            body = self._qr_png_bytes()
            if body:
                return [200, "image/png", body]
            return [404, "text/plain", b""]
        if str(params.get("type") or "") != "singer":
            return [404, "text/plain", b""]
        try:
            name = self.d64(params.get("n") or "")
        except Exception:
            return [404, "text/plain", b""]
        h = hashlib.md5(name.encode("utf-8")).hexdigest()
        try:
            with open(os.path.join(self.img_dir(), h + ".img"), "rb") as f:
                body = f.read()
        except Exception:
            return [404, "text/plain", b""]
        ct = "image/jpeg"
        if body[:8] == b'\x89PNG\r\n\x1a\n':
            ct = "image/png"
        elif body[:3] == b'GIF':
            ct = "image/gif"
        return [200, ct, body]

    def _cloud_off(self, size):
        """官方版本接口。拿不到就返回 None，交给配置源兜底。
        返回的 dict 与配置源同构，多带 ver/src 两个键。"""
        import requests
        ua = {"User-Agent": "okhttp/3.8.0"}
        try:
            ts = int(time.time() * 1000)
            su = (DB_SIGN_URL % ts) if "%s" in DB_SIGN_URL else (DB_SIGN_URL + str(ts))
            v = requests.get(su, headers=ua,
                             timeout=15).text.strip()
            if len(v) < 16:
                self.log("cloud off: validator too short %r" % (v[:40],))
                return None
        except Exception as e:
            self.log("cloud off sign fail: %r" % (e,))
            return None
        for b in DB_BASES:
            try:
                r = requests.post(b + DB_API_PATH, json={},
                                  headers={"User-Agent": "okhttp/3.8.0",
                                           "validator": v,
                                           "Content-Type":
                                           "application/json; charset=utf-8"},
                                  timeout=20)
                o = r.json()
                if o.get("statusCode") != 1:
                    self.log("cloud off %s status=%r" % (b, o.get("statusCode")))
                    continue
                d = o.get("data") or {}
                if not d.get("url"):
                    continue
                # 接口不给大小，HEAD 补一下；拿不到就让 size=0，
                # 靠 integrity_check + 歌数比对兜底（别拿配置源的大小硬套）
                sz = 0
                try:
                    h = requests.head(d["url"], headers=ua, timeout=15,
                                      allow_redirects=True)
                    sz = int(h.headers.get("Content-Length") or 0)
                except Exception:
                    sz = 0
                if size and sz and sz != size:
                    self.log("cloud off size %d vs cfg %d, use HEAD" % (sz, size))
                return {"path": d["url"], "size": sz, "sha256": "",
                        "ver": str(d.get("versionName") or ""),
                        "vcode": d.get("versionCode"),
                        "utime": str(d.get("updateTime") or ""),
                        "src": "官方"}
            except Exception as e:
                self.log("cloud off %s fail: %r" % (b, e))
        return None
    def _cloud_meta(self):
        """拿远端库信息：官方接口优先，失败回落配置文件。
        返回 dict，含 path/size/sha256/ver/src。"""
        import requests
        url = DB_MAP_URL
        try:
            r = requests.get(url, timeout=20,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            raw = r.content
        except Exception as e:
            raw = b""
            self.log("cloud cfg fail: %r" % (e,))
        cfg = None
        if len(raw) >= 200:
            try:
                body = raw
                if raw[:2] == b"BM":
                    # BMP：像素区从 10-14 字节给出的偏移开始，里面是纯 base64
                    off = int.from_bytes(raw[10:14], "little")
                    if off <= 0 or off >= len(raw):
                        off = raw.find(b"ewo") if raw.find(b"ewo") > 0 else 0
                    body = raw[off:]
                txt = body.decode("ascii", "ignore").strip()
                txt = "".join(ch for ch in txt if ch in
                              "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                              "abcdefghijklmnopqrstuvwxyz"
                              "0123456789+/=")
                txt += "=" * ((-len(txt)) % 4)
                info = json.loads(base64.b64decode(txt).decode("utf-8"))
                cfg = (info.get("databases") or {}).get(DB_MAP_KEY)
                if cfg:
                    cfg = dict(cfg)
                    cfg["map_version"] = str(info.get("version") or "")
                    cfg["src"] = "配置"
            except Exception as e:
                self.log("cloud cfg parse fail: %r" % (e,))
        # 官方接口成功 → 用它；否则用配置
        size0 = int((cfg or {}).get("size") or 0)
        off = self._cloud_off(size0)
        if off:
            # 配置有的 sha256 仍然有用（官方不给），能对上就用
            if cfg and cfg.get("path") == off["path"] and cfg.get("sha256"):
                off["sha256"] = cfg["sha256"]
            off["map_version"] = (cfg or {}).get("map_version", "")
            return off
        if cfg:
            cfg["ver"] = (cfg.get("ver") or
                          os.path.basename(str(cfg.get("path") or "")))
            return cfg
        raise ValueError("官方接口和配置源都拿不到")

    def _cloud_pick_db(self):
        """新库落盘位置：当前库所在目录优先，写不进去就退到 Download。"""
        try:
            self._autofix_db()
        except Exception:
            pass
        try:
            cur = FORCE_DB_PATH or self._db_setting()
        except Exception:
            cur = DB_PATH
        # 配置里可能直接填的是目录：落到目录里，文件名仍用标准名
        if os.path.isdir(cur):
            base = cur
            name = DB_MAP_KEY + ".db"
        else:
            base = os.path.dirname(cur) or ""
            name = os.path.basename(cur) or (DB_MAP_KEY + ".db")
        self._dlog("cloud", "pick cur=%s base=%s name=%s" % (cur, base, name))
        for d in (base, "/storage/emulated/0/Download",
                  "/sdcard/Download"):
            if not d:
                continue
            try:
                if not os.path.isdir(d):
                    self._dlog("cloud", "pick skip %s (not a dir)" % d)
                    continue
                t = os.path.join(d, ".wtest")
                with open(t, "w") as f:
                    f.write("1")
                os.remove(t)
                picked = os.path.join(d, name)
                self._dlog("cloud", "pick -> %s%s" % (
                    picked,
                    "" if d == base else " (fallback: base dir not writable)"))
                return picked
            except Exception as e:
                self._dlog("cloud", "pick fail %s: %r" % (d, e))
                continue
        picked = os.path.join(base or "/tmp", name)
        self._dlog("cloud", "pick -> %s (last resort)" % picked)
        return picked

    def _dl_load(self):
        p = self._dl_progress_path()
        if not p:
            return {}
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _dl_state(self):
        """当前进行中的下载：返回 dict 或 {}。超过 24h 视为废弃。"""
        d = self._dl_load()
        if not d.get("url"):
            return {}
        try:
            if time.time() - float(d.get("ts") or 0) > 86400:
                return {}
        except Exception:
            return {}
        part = d.get("part") or ""
        if not os.path.isfile(part):
            return {}
        return d

    def _dl_bytes(self, st):
        try:
            return os.path.getsize(st.get("part") or "")
        except Exception:
            return 0

    def _dl_save(self, d):
        p = self._dl_progress_path()
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
        except Exception:
            pass

    def _dl_progress_path(self):
        try:
            return os.path.join(os.path.dirname(self._cfg_file()),
                                DB_PROGRESS_FILE)
        except Exception:
            return ""

    def _dl_clear(self):
        self._dl_save({})

    def _human(self, n):
        try:
            n = float(n or 0)
        except Exception:
            return "0"
        for u in ("B", "KB", "MB", "GB"):
            if n < 1024 or u == "GB":
                return ("%.0f %s" % (n, u)) if u == "B" else ("%.1f %s" % (n, u))
            n /= 1024.0
        return "?"

    @staticmethod
    def _sha256(path):
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for c in iter(lambda: f.read(1048576), b""):
                    h.update(c)
        except Exception:
            return ""
        return h.hexdigest()

    @staticmethod
    def _db_song_count(path):
        try:
            c = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=3)
            try:
                return c.execute("SELECT COUNT(*) FROM song").fetchone()[0]
            finally:
                c.close()
        except Exception:
            return 0

    def _cloud_card(self):
        """设置页那张卡的标题/副标题/正文。"""
        st = self._dl_state()
        if st and st.get("state") == "held":
            return ("🔄 云端曲库：待确认覆盖",
                    "远端歌数少，已拦下 · 点我确认",
                    "远端版本 (%s) 的曲目比本机少，我已保留当前库。\n\n"
                    "文件已下载并校验完毕，确认要用远端版本的话，"
                    "点这张卡即可直接安装（不用重新下载）。\n\n"
                    "待安装：%s" % (st.get("ver") or "?", st.get("part") or "?"))
        if st:
            have = self._dl_bytes(st)
            size = int(st.get("size") or 0)
            pct = ("%.0f%%" % (have * 100.0 / size)) if size else "?"
            return ("🔄 云端曲库：下载中 %s" % pct,
                    "%s / %s · 再点卡片查看" % (self._human(have), self._human(size)),
                    "正在后台下载。\n\n已完成 %s / %s（%s）\n"
                    "下载可断点续传：中途退出、断网、重启壳，"
                    "再点这张卡都会从已下载的位置接着走。\n\n"
                    "存到：%s" % (self._human(have), self._human(size), pct,
                                 st.get("part") or "?"))
        try:
            cur = str(self._cfg_get().get("db") or DB_PATH)
            n = self._probe_db(cur)
        except Exception:
            cur, n = "", 0
        return ("🔄 云端曲库（在线更新）",
                "点我检查更新（当前 %s 首）" % (n or "?"),
                "从云端拉最新的曲库快照，断点续传 + sha256 校验。\n\n"
                "当前库：%s\n  版本 %s · 共 %s 首\n\n"
                "第一次点：查官方接口看有没有新版本。\n"
                "有更新时下载约 110MB，自动校验，替换前先备份旧库。\n\n"
                "注意：云端不一定比本机新。如果本机歌数更多，"
                "我会先问你要不要覆盖。\n\n"
                "更新默认就下到当前库所在的目录，旧库也在同目录备份。"
                % (cur or "（未设置）", self._db_version(cur) or "无", n or "?"))

    def _cloud_confirm(self, meta):
        """拿到配置后，比对本机，决定问什么。"""
        try:
            _tgt = self._cloud_pick_db()
        except Exception:
            _tgt = ""
        try:
            cur = str(self._cfg_get().get("db") or DB_PATH)
            local_n = self._probe_db(cur) or 0
        except Exception:
            cur, local_n = "", 0
        size = int(meta.get("size") or 0)
        head = ("云端快照\n  文件 %s\n  sha256 %s…\n  %s\n\n"
                "本机当前\n  %s\n  %s 首\n\n"
                "将下载到（当前库所在目录）\n  %s\n\n"
                % (self._human(size), str(meta.get("sha256") or "")[:16],
                   os.path.basename(str(meta.get("path") or "")),
                   cur or "（未设置）", local_n or "?",
                   _tgt or "（当前库所在目录）"))

        # 远端信息里没有歌数，只能下了才知道；先给出下载前的判断
        self._confirm_dialog(
            "🔄 云端曲库",
            head + "要下载吗？110MB 左右，支持断点续传，"
                   "下完会校验 sha256；若远端歌数比本机少会自动中止，"
                   "替换前备份旧库。再次点击可强制覆盖。",
            lambda: self._cloud_start(meta))

    def _cloud_dlg_show(self):
        """建一个带进度条、不自动关的弹窗。壳里没有 java 模块就返回 None。"""
        try:
            from java import jclass
            ctx = self._activity()
            if ctx is None:
                return None
            PBar = jclass("android.widget.ProgressBar")
            LL = jclass("android.widget.LinearLayout")
            TV = jclass("android.widget.TextView")
            B = jclass("android.app.AlertDialog$Builder")
            box = LL(ctx)
            box.setOrientation(1)
            pad = int(18 * ctx.getResources().getDisplayMetrics().density)
            box.setPadding(pad, pad, pad, pad)
            tv = TV(ctx)
            tv.setText("准备中…")
            tv.setTextSize(15.0)
            bar = PBar(ctx, None, 16842871)          # 系统横向进度条
            bar.setMax(1000)
            bar.setProgress(0)
            sub = TV(ctx)
            sub.setText("0%")
            sub.setTextSize(13.0)
            box.addView(tv)
            box.addView(bar)
            box.addView(sub)
            b = B(ctx)
            b.setTitle("🔄 云端曲库")
            b.setView(box)
            b.setCancelable(False)
            # 给个退路：下载在后台线程跑，关掉窗口不影响进度
            b.setNegativeButton("后台继续", None)
            d = b.create()
            d.setCanceledOnTouchOutside(False)
            d.show()
            return {"d": d, "tv": tv, "bar": bar, "sub": sub, "t": time.time()}
        except Exception as e:
            self.log("cloud dlg fail: %r" % (e,))
            return None

    def _cloud_dlg_set(self, h, pct, text="", force=False):
        """更新进度。节流 0.4s，避免主线程被刷爆。"""
        if not h:
            return
        now = time.time()
        full = pct >= 100
        if not force and not full and now - h.get("t", 0) < 0.4:
            return
        h["t"] = now
        pct = max(0, min(100, pct))
        try:
            h["bar"].setProgress(int(pct * 10))
            h["sub"].setText("%s%%%s" % (int(pct), ("  ·  " + text) if text else ""))
            if full:
                h["tv"].setText("正在校验并安装…")
            elif text:
                h["tv"].setText("正在下载…")
        except Exception:
            pass
        if full:
            h["closing"] = True
        self.log("cloud pct %d %s" % (int(pct), text))

    def _cloud_dlg_close(self, h):
        if not h:
            return
        try:
            h["d"].dismiss()
        except Exception:
            pass

    def _cloud_done_dialog(self, ok, msg):
        """下载结束弹窗：成功给「立即重启生效」，失败给原因。"""
        try:
            from java import jclass
            ctx = self._activity()
            if ctx is None:
                self._toast(msg.split("\n")[0])
                return
            B = jclass("android.app.AlertDialog$Builder")
            b = B(ctx)
            b.setTitle("✅ 曲库已更新" if ok else "⚠️ 曲库没更新")
            if ok:
                b.setMessage(msg)
            else:
                tail = ("\n\n已有进度会保留，下次点卡片接着下。"
                        if "更旧" not in msg and "已是最新" not in msg
                        else "\n\n本地库没有任何改动。")
                b.setMessage(msg + tail)
            b.setPositiveButton("知道了", None)
            b.setCancelable(True)
            b.show()
        except Exception:
            try:
                self._toast(msg.split("\n")[0])
            except Exception:
                pass

    def _cloud_start(self, meta):
        """开子线程跑下载，立刻返回。进度落盘，中途退出也不丢。"""
        h = self._cloud_dlg_show()

        def _run():
            try:
                ok, msg = self._cloud_work(meta, h)
            except Exception as e:
                ok, msg = False, "出错：%s" % str(e)[:100]
            self.log("cloud done ok=%s %s" % (ok, msg.replace("\n", " ")[:120]))
            self._cloud_dlg_close(h)
            self._cloud_done_dialog(ok, msg)

        try:
            t = threading.Thread(target=_run)
            t.daemon = True
            t.start()
        except Exception as e:
            self._toast("启动失败：%s" % str(e)[:60])

    def _cloud_work(self, meta, dlg=None):
        """真正的下载 + 校验 + 安装。子线程里跑。
        返回 (ok, 文案)。文件级断点续传：重跑已存在的 .part 不丢。"""
        import requests
        url = meta["path"]
        sha = str(meta.get("sha256") or "").lower()
        size = int(meta.get("size") or 0)
        target = self._cloud_pick_db()
        part = target + DB_PART_SUFFIX
        self._dlog("cloud", "work target=%s size=%s url=%s"
                   % (target, size, str(url)[:80]))

        # 已经是这份库：直接收工，不碰网络流量
        # 官方源不给 sha256，退化为「版本号 + 文件大小 + song 表全量」三重比对
        if os.path.isfile(target) and size and os.path.getsize(target) == size:
            if sha and self._sha256(target) == sha:
                hit = True
            elif not sha and meta.get("ver") and (
                    self._db_version(target) == str(meta["ver"])):
                hit = True
            else:
                hit = False
            if hit:
                self._dl_clear()
                self._cloud_dlg_set(dlg, 100, "已是这份库")
                n = self._db_song_count(target)
                return True, "✅ 已是最新，无需下载\n%s\n版本 %s · 曲目 %s 首" % (
                    target, self._db_version(target) or "?", n if n else "?")

        st = self._dl_load() or {}
        if st.get("url") != url or st.get("part") != part:
            # 换了目标或源：旧的作废
            if st.get("part") and os.path.isfile(st["part"]):
                try:
                    os.remove(st["part"])
                except Exception:
                    pass
        st = {"url": url, "part": part, "target": target,
              "size": size, "sha256": sha, "ts": time.time(), "state": "dl"}
        self._dl_save(st)

        headers = {"User-Agent": "Mozilla/5.0"}
        # 网络抖动/代理掐流很常见：每轮失败就用已落盘长度接着续，最多 8 轮
        for attempt in range(MAX_TRY):
            have = os.path.getsize(part) if os.path.isfile(part) else 0
            if size and have > size:
                have = 0
                try:
                    os.remove(part)
                except Exception:
                    pass
            if size and have == size:
                break
            hdr = dict(headers)
            mode = "wb"
            if have:
                hdr["Range"] = "bytes=%d-" % have
                mode = "ab"
                self.log("cloud resume %d/%d (try %d)"
                         % (have, size, attempt + 1))
            try:
                with requests.get(url, headers=hdr, stream=True,
                                  timeout=(15, 60)) as r:
                    if r.status_code == 416:
                        break                      # 已下完
                    if r.status_code not in (200, 206):
                        raise IOError("HTTP %d" % r.status_code)
                    if r.status_code == 200 and have:
                        mode = "wb"                # 服务端不认 Range，重下
                    done = have
                    with open(part, mode) as f:
                        for chunk in r.iter_content(262144):
                            if chunk:
                                f.write(chunk)
                                done += len(chunk)
                                if size:
                                    self._cloud_dlg_set(
                                        dlg, done * 100.0 / size,
                                        "%s / %s" % (self._human(done),
                                                     self._human(size)))
            except Exception as e:
                self.log("cloud dl fail(try %d): %r" % (attempt + 1, e))
                st["state"] = "err"
                self._dl_save(st)
                if attempt >= MAX_TRY - 1:
                    return False, ("下载中断：%s\n已存 %s，再点一次卡片接着下。"
                                   % (str(e)[:70], self._human(
                                       os.path.getsize(part)
                                       if os.path.isfile(part) else 0)))
                time.sleep(min(2 + attempt * 2, 12))

        # 大小校验
        got = os.path.getsize(part) if os.path.isfile(part) else 0
        if size and got != size:
            st["state"] = "err"
            self._dl_save(st)
            return False, "大小不符：%d / 期望 %d" % (got, size)

        # sha256 校验（114MB 约 1-2s）。官方接口不给 sha256，只能靠下面
        # 的 integrity_check + 歌数比对兜底。
        st["state"] = "check"
        self._dl_save(st)
        self._cloud_dlg_set(dlg, 100, "校验中", force=True)
        if sha:
            h = hashlib.sha256()
            try:
                with open(part, "rb") as f:
                    for b in iter(lambda: f.read(1 << 20), b""):
                        h.update(b)
            except Exception as e:
                return False, "校验失败：%s" % str(e)[:80]
            if h.hexdigest() != sha:
                try:
                    os.remove(part)
                except Exception:
                    pass
                st["state"] = "err"
                self._dl_save(st)
                return False, ("sha256 不匹配，文件已删，请重试。\n"
                               "本地 %s\n期望 %s"
                               % (h.hexdigest()[:16], sha[:16]))

        # 能打开吗
        n = self._probe_db(part)
        if not n:
            try:
                os.remove(part)
            except Exception:
                pass
            return False, "下载完成但库打不开（可能被截断），已删除。"

        # 安装：备份旧库 → 替换 → 版本文件
        # 新鲜度防护：远端快照可能比本地旧（歌少），落地前先数一遍
        lc = self._db_song_count(target) if os.path.isfile(target) else 0
        rc = self._db_song_count(part)
        if not rc:
            try:
                os.remove(part)
            except Exception:
                pass
            self._dl_clear()
            return False, "下载结果无法读取（分片损坏），已丢弃。再点一次重试。"
        if lc and rc < lc:
            keep = self.cloud_force
            if not keep:
                # 保留 .part：用户二次确认后不用重下 110MB。
                # 状态标 held，卡片据此提示「待确认覆盖」。
                st["state"] = "held"
                st["ts"] = time.time()
                self._dl_save(st)
                return False, ("远端更旧：本地 %s 首 > 远端 %s 首\n"
                               "已保留当前库，未覆盖。\n"
                               "已下载好的文件留着，确认要用远端版本的话，"
                               "再点一次卡片即可（不用重下）。"
                               % (lc, rc))
            self.cloud_force = False

        bak = ""
        try:
            if os.path.isfile(target):
                # 备份名带旧版本号：song_9c8ec.db.bak-3.3.1
                # 同名先删（重试/续传时不堆副本），只保留这一版
                o = self._db_version(target) or ""
                o = "".join(c for c in o if c.isalnum() or c in "._-")[:24]
                bak = target + ".bak-" + (o or "old")
                if os.path.isfile(bak):
                    os.remove(bak)
                shutil.copy2(target, bak)
                # 版本文件一起备份，回滚时不会被新版本号带歪
                vold = os.path.splitext(target)[0] + ".version"
                if os.path.isfile(vold):
                    shutil.copy2(vold, vold + ".bak-old")
                self.log("cloud backup -> %s" % os.path.basename(bak))
        except Exception as e:
            self.log("backup fail: %r" % (e,))
        try:
            if os.path.isfile(target):
                os.remove(target)
        except Exception:
            pass
        try:
            os.rename(part, target)
        except Exception:
            try:
                shutil.copy2(part, target)
                os.remove(part)
            except Exception as e:
                return False, "安装失败：%s" % str(e)[:80]
        # 同名 .version 跟随（壳用 splitext(db)+".version" 判版本，别写 .db.version）
        # 远端给了明确版本号就写它，否则写当天日期
        vpath = os.path.splitext(target)[0] + ".version"
        ver = str(meta.get("ver") or "").strip()
        try:
            with open(vpath, "w", encoding="utf-8") as f:
                f.write((ver or time.strftime("%Y.%m.%d")) + "\n")
        except Exception:
            pass
        # 让 scnt 计数表按新库重建
        try:
            self._cfg_set({"db": target, "scnt_ver": ""})
        except Exception:
            pass
        try:
            self._scnt_ready = False
        except Exception:
            pass
        st["state"] = "done"
        st["ts"] = time.time()
        self._dl_save(st)
        total = self._db_song_count(target)
        msg = "✅ 曲库已更新\n共 %s 首\n%s" % (total or n or "?", target)
        if bak:
            msg += "\n旧库备份：%s" % os.path.basename(bak)
        return True, msg

    def _cloud_action(self):
        """点卡片：先看有没有残留下载 → 有就续，没有就查配置。"""
        st = self._dl_state()
        # 上次下完但被「远端更旧」拦下：还是那份文件，直接进确认，别重下
        if st and st.get("state") == "held":
            self._cloud_start({"path": st.get("url"), "sha256": st.get("sha256"),
                               "ver": st.get("ver"),
                               "size": int(st.get("size") or 0)})
            return
        if st:
            have = self._dl_bytes(st)
            size = int(st.get("size") or 0)
            pct = ("%.0f%%" % (have * 100.0 / size)) if size else "?"
            self._confirm_dialog(
                "🔄 继续下载",
                "上次下到 %s / %s（%s）\n\n从断点继续？"
                % (self._human(have), self._human(size), pct),
                lambda: self._cloud_start({"path": st["url"],
                                           "sha256": st.get("sha256"),
                                           "size": size}))
            return

        self._toast("正在读取配置…")

        def _run():
            try:
                meta = self._cloud_meta()
            except Exception as e:
                self.log("cloud meta fail: %r" % (e,))
                self._toast("拉配置失败：%s" % str(e)[:60])
                return
            self._cloud_confirm(meta)

        t = threading.Thread(target=_run)
        t.daemon = True
        t.start()

def _shrink_img(blob, size=300, quality=85):
    """把图片统一压到 size x size、JPEG quality=85。"""
    try:
        import io as _io
        from PIL import Image as _Img
    except Exception:
        return blob
    try:
        im = _Img.open(_io.BytesIO(blob))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if im.size != (size, size):
            # 按短边裁成正方形再缩，避免拉伸变形
            w, h = im.size
            d = min(w, h)
            im = im.crop(((w - d) // 2, (h - d) // 2,
                          (w - d) // 2 + d, (h - d) // 2 + d))
            im = im.resize((size, size), _Img.LANCZOS)
        out = _io.BytesIO()
        im.save(out, "JPEG", quality=quality, optimize=True)
        # 尺寸必须统一成 size x size（壳按正方形裁切显示）。
        # 酷我原图只有 240x240，放大到 300 后体积会涨，但一致比省几十 KB 重要。
        return out.getvalue()
    except Exception:
        return blob


def _html_unescape(t):
    """酷我返回的名字里有 &nbsp; &apos; 这类实体，还原成真实字符。"""
    if not t:
        return ""
    try:
        from html import unescape as _u
        return _u(t)
    except Exception:
        return t.replace("&nbsp;", " ").replace("&apos;", "'").replace("&amp;", "&")


def _name_eq(a, b):
    """歌名归一化比较。"""
    def n(x):
        return "".join(str(x or "").split()).lower()
    x, y = n(a), n(b)
    if not x or not y:
        return False
    if x == y:
        return True
    return y.startswith(x) and len(x) >= 2

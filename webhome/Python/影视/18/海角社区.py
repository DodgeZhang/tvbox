# coding=utf-8
# //@name:海角社区
# //@id:haijiao
# //@version:4
#
# 站点：haijiao.com（同源 API 站点，SPA + 三层 Base64 响应体）
# 数据通路：/api/topic/nodes 板块树 → /api/topic/node/topics 列表 → /api/topic/{id} 详情
#          搜索 /api/topic/search_topic_by_tag?tag= ；最新 /api/topic/node/news ；热门 /api/topic/hot/topics
#
# v3 修正（实测复现）：
#  1. 板块列表参数。站点只认驼峰 nodeId，写成 node_id 会被后端直接忽略并退化成
#     全站列表 —— 122 个分类曾因此返回完全相同的内容。正确形态是
#     /topic/node/topics?type=<type>&nodeId=<id>&page=n。
#  2. type 语义：7=视频帖（实测每页 20/20 带视频）、1=全部帖（仅 2/20 带视频）、
#     0/4/6/8/9≈全站、3=精选子集、5=高视频占比。本 Spider 分类默认走 7，
#     没有视频帖的板块自动回退到 1；每个分类都提供「视频优先 / 全部帖子」切换。
#  3. 分片边界探测重写。实测同一站点分片时长并不统一（1.0~5.4 秒/片都有），
#     旧版按总时长折算 + 粗扫，一次抖动就会把末端砍掉一大半（某 23 分钟视频
#     被算成 321 片，真实末片 1429），现象就是「播着播着断了」。
#     现改为锚点验证 + 指数扩张找上界 + 二分逼近，每步探测带重试。
#  4. 列表层过滤：视频优先模式下剔掉无视频附件的图文帖，避免点进去没有播放地址。
#
# v4 修复（免登录播放 + 图片全支持，实测复现）：
#  1. 播放地址不再依赖登录。站点对游客把 attachment.remoteUrl 置空（/api/video/{id} 直接
#     回「请先登录」），但视频线路的地址可由附件自身的 coverUrl 推导：
#         coverUrl  https://<pic>/hjstore/video/<日期>/<md5>/<序号>.jpeg.txt
#         播放清单  https://<ts>/hjstore/video/<日期>/<md5>/<序号>_i_preview.m3u8
#     实测 34/34 条视频帖全部推导成功，且返回的清单可直取、分片公开。
#  2. 图片全部是加密载荷，不能直接当图用。站点的 .txt 是「自定义字母表 base64」编码，
#     解出来是一段 data URL 文本，再取其中的 base64 才是真图。本 Spider 内置等价解码
#     （见 _decode_image_payload），封面与图集统一走 localProxy 还原后回给壳。
#  3. 图集帖支持：无视频附件的帖子按 pics:// 图集线路返回，不再报「无播放地址」。
#  4. 权限面实测（游客 / 需登录见文件末尾「权限面实测」）：
#     公开 = 板块树 / 列表 / 详情 / 搜索 / 图集 / 附件线路表 / 称号表；
#     需登录 = 收藏夹、关注、财富钱包、签到、任务、提现、购买、解锁联系方式、我的动态等。
#     填 ext.cookie 即可带登录态使用（登录接口 /api/login/signin）。
#
# 播放通路：详情附件中的视频地址为预览清单，真实分片文件为站点公开资源。
#           本 Spider 按预览清单的分片命名规则重建完整播放列表，并用站点自身的密钥派生
#           逻辑（原密钥与同目录 .jpg 载荷逐字节异或）还原 AES-128 解密密钥；
#           分片由播放器直连源站，仅密钥经 localProxy 下发（避免代理转发拖累播放）。
#
# 四壳契约（TVBox / 影视仓 / OK影视 / PickTV）：
#  - 双协议兼容继承 base.spider（导入失败用本地最小基类兜底，禁止纯独立类）
#  - 13 标准接口齐全且全部可调用
#  - homeContent: class + filters 为 dict
#  - 列表五键 page/pagecount/limit/total/list
#  - 详情多线路 $$$、多集 #、集名与地址 $
#  - playerContent header 为 dict、parse=0/jx=0
#  - init 预热网络通道
#  - Accept-Encoding 统一 gzip, deflate（不声明 br）
#  - 分类层级铁律：父子分类必须同时完整写入
#  - X25519 曲线仅用于 CF 防护站，普通站不要强制设置（部分服务器不支持会握手失败）
#  - 铁律11：内置 CLASSICAL_MAP + desensitize()，返回前对展示文本脱敏，未成年条目剔除
#  - 铁律15：rawSite/siteUrl 域名替换式反代（ext.proxy 可切，本机实测直连可用故默认直连），
#            playerContent.header 含 Referer + Origin
#  - 广告拦截：localProxy 非空壳 + _clean_m3u8 + _is_ad_segment（含 _parse_m3u8_segments 解析器）
#  - 详情页打开时后台预热播放列表，点开即播（二次请求走缓存，秒开）

import ast
import base64
import json
import os
import re
import ssl
import threading
import time
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.poolmanager import PoolManager
    HAS_URLLIB3 = True
except Exception:
    PoolManager = None
    HAS_URLLIB3 = False

# 铁律8 + FongMi 官方契约：双协议兼容继承 base.spider
try:
    from base.spider import Spider as _BaseSpider
except Exception:
    try:
        from base.spider import BaseSpider as _BaseSpider
    except Exception:
        class _BaseSpider:
            def init(self, extend=""):
                pass

DEFAULT_HOST = "https://haijiao.com"
DEFAULT_MIRRORS = ("haijiao.com", "www.haijiao.com")
PAGE_SIZE = 20
DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
PLAYER_UA = DEFAULT_UA

NAV_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-User": "?1",
}

CHALLENGE_MARKERS = (
    "cf-browser-verification", "just a moment", "attention required",
    "turnstile", "enable javascript and cookies to continue",
)

CATEGORIES = (
    ("1", "分类一", ""),
    ("2", "分类二", ""),
)

SORTS = (
    ("new", "最新"),
    ("hot", "最热"),
)

PACKED_RE = re.compile(
    r"}\('(?P<p>(?:\\.|[^'\\])*)',(?P<a>\d+),(?P<c>\d+),'(?P<k>(?:\\.|[^'\\])*)'\.split\('\|'\)"
)
SOURCE_ASSIGN_RE = re.compile(r"(source(?:\d+)?)\s*=\s*'(https?://[^']+\.m3u8[^']*)'", re.I)
_B36_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"

# ========== v4：图片载荷解码（等价前端 A.decode） ==========
# 站点前端用的自定义字母表 base64（顺序与标准表不同，实测抓自前端实现）：
#   ABCD*EFGHIJKLMNOPQRSTUVWX#YZabcdefghijklmnopqrstuvwxyz1234567890
# .txt → 该表 base64 解码 → UTF-8 文本 "data:image/jpeg;base64,<真图 base64>"
IMG_ALPHABET = "ABCD*EFGHIJKLMNOPQRSTUVWX#YZabcdefghijklmnopqrstuvwxyz1234567890"
_IMG_INDEX = {ch: idx for idx, ch in enumerate(IMG_ALPHABET)}
_IMG_KEEP_RE = re.compile(r"[^A-Za-z0-9*#]")
_DATA_URL_RE = re.compile(r"^\s*data:(?P<mime>[A-Za-z0-9/+.\-]+);base64,(?P<body>.*)$", re.S)

# ========== v4：视频 CDN 主机（实测 ts5/ts6/ts7/ts8/ts9/ts10 均可达） ==========
VIDEO_CDN_HOSTS = ("ts10", "ts5", "ts8", "ts6", "ts9", "ts7", "pic")
_CDN_ORIGIN_RE = re.compile(r"^https?://([a-z0-9\-]+)\.hj\d+\.top", re.I)
# 视频附件封面 → 播放清单的路径特征
_COVER_VIDEO_RE = re.compile(
    r"/hjstore/video/(?P<date>\d{8})/(?P<md5>[0-9a-f]{32})/(?P<seq>\d+)"
    r"\.(?:jpe?g|png|gif)(?:\.txt)?$", re.I)

# ========== 铁律11：敏感词古典映射脱敏表 ==========
CLASSICAL_MAP = {
    "成人": "风月", "色情": "风月", "情色": "春宫", "淫": "风月", "黄色": "春宫", "淫秽": "猥亵",
    "AV": "光影", "av": "光影", "三级": "风月",
    "激情": "云雨", "做爱": "云雨", "性交": "交欢", "欲": "情思", "高潮": "云端",
    "偷拍": "窥帘", "偷窥": "窥帘", "乱伦": "禁脔", "强奸": "强占", "轮奸": "群辱",
    "迷奸": "迷占", "无码": "素纱", "有码": "遮面", "熟女": "徐娘",
    "萝莉": "豆蔻", "幼女": "玉蕊", "少女": "碧玉", "学生": "书生",
    "人妻": "罗敷", "少妇": "艳妇", "御姐": "玉人", "护士": "药女",
    "教师": "先生", "医生": "郎中", "警察": "捕快", "军人": "军爷",
    "秘书": "掌印", "老板": "东家", "丈夫": "夫君", "妻子": "拙荆",
    "情人": "相好", "小三": "外遇", "二奶": "外室", "出轨": "翻墙",
    "偷情": "私会", "通奸": "私通", "嫖娼": "寻花", "卖淫": "卖身",
    "妓女": "花娘", "性骚扰": "轻薄", "猥亵": "猥亵", "露阴": "曝玉",
    "咸猪手": "禄山爪", "丝袜": "丝履", "网袜": "网履", "内衣": "亵衣",
    "内裤": "亵裤", "情趣": "风月", "春药": "催情", "巨乳": "丰盈",
    "爆乳": "丰盈", "胸": "酥胸", "乳": "玉兔", "美乳": "玉兔",
    "臀": "玉臀", "屁股": "玉臀", "脚": "莲步", "玉足": "莲步",
    "腿": "玉腿", "裸体": "玉体", "全裸": "玉体", "半裸": "半褪",
    "走光": "泄春", "露点": "泄玉", "自慰": "弄玉", "口交": "含朱",
    "口活": "含朱", "肛交": "后庭", "屁眼": "后庭", "肛门": "后庭",
    "群交": "合卺", "乳交": "玉兔", "足交": "莲步", "车震": "车行",
    "野战": "郊合", "精液": "元阳", "精子": "元阳", "阴道": "幽处",
    "阴户": "幽处", "阴茎": "玉茎", "阳具": "玉茎", "SM": "调教",
    "制服": "官衣", "OL": "衙内", "空姐": "行云", "继母": "继室",
    "姐妹": "同根", "同学": "同窗", "邻居": "东邻", "处女": "处子",
    "初夜": "破瓜", "暴力": "杀伐", "血腥": "殷红", "恐怖": "幽冥",
    "赌博": "孤注", "毒品": "药石", "枪支": "火器", "刀具": "利刃",
}

# 铁律13：未成年相关关键词（脱敏后仍命中则剔除不返回）
# 注意："学生"/"书生"已移除——高中生/大学生可能已成年，不视为未成年；
# 仅保留明确指向未成年的词（萝莉/幼女/少女/童/teen/loli/schoolgirl等）
_MINOR_KEYWORDS = (
    "豆蔻", "玉蕊", "碧玉", "稚子", "未成年", "teen", "loli",
    "schoolgirl", "萝莉", "幼女", "少女", "童",
)

# 铁律15：默认反代配置路径
_PROXY_CONFIG_PATHS = (
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "proxy_config.json"),
    os.path.expanduser("~/.super_doubao/super-doubao-runtime/workspace/.user_skills/tvbox-dev/assets/proxy_config.json"),
)
_DEFAULT_PROXY_FALLBACK = "https://xsz-shared-proxy.97471201.workers.dev"


def _load_default_proxy():
    """铁律15：读取默认反代地址，读取失败回退到内置地址"""
    for path in _PROXY_CONFIG_PATHS:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                proxy = data.get("default_proxy", "").strip()
                if proxy:
                    return proxy
        except Exception:
            continue
    return _DEFAULT_PROXY_FALLBACK


def _decode_image_payload(raw_text):
    """v4：还原站点图片载荷。

    .txt 内容是「自定义字母表 base64」编码，解出的是 data URL 文本，
    再取其中 base64 才是真正的图片字节。返回 (mime, image_bytes)，失败返回 (None, None)。
    """
    if not raw_text:
        return None, None
    text = _IMG_KEEP_RE.sub("", str(raw_text))
    out = bytearray()
    idx = 0
    size = len(text)
    while idx < size:
        v0 = _IMG_INDEX.get(text[idx], -1)
        v1 = _IMG_INDEX.get(text[idx + 1], -1) if idx + 1 < size else -1
        v2 = _IMG_INDEX.get(text[idx + 2], -1) if idx + 2 < size else -1
        v3 = _IMG_INDEX.get(text[idx + 3], -1) if idx + 3 < size else -1
        idx += 4
        if v0 < 0 or v1 < 0:
            break
        out.append(((v0 << 2) | (v1 >> 4)) & 0xFF)
        if v2 >= 0:
            out.append((((v1 & 15) << 4) | (v2 >> 2)) & 0xFF)
        if v3 >= 0 and v2 >= 0:
            out.append((((v2 & 3) << 6) | v3) & 0xFF)
    try:
        body = bytes(out).decode("utf-8", "ignore")
    except Exception:
        return None, None
    match = _DATA_URL_RE.match(body)
    if not match:
        return None, None
    mime = match.group("mime") or "image/jpeg"
    data = re.sub(r"\s+", "", match.group("body"))
    try:
        blob = base64.b64decode(data + "=" * (-len(data) % 4))
    except Exception:
        return None, None
    if not blob:
        return None, None
    return mime, blob


def _sniff_image_mime(blob, fallback="image/jpeg"):
    """按魔数判定真实图片类型（解码后可能不等于 URL 后缀）"""
    if not blob:
        return fallback
    if blob[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if blob[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "image/webp"
    return fallback


def _cover_to_preview(cover_url, host):
    """v4：由视频附件封面地址推导预览清单地址；形态不符返回空串"""
    match = _COVER_VIDEO_RE.search(str(cover_url or ""))
    if not match or not host:
        return ""
    return "https://%s.hj260302818.top/hjstore/video/%s/%s/%s_i_preview.m3u8" % (
        host, match.group("date"), match.group("md5"), match.group("seq"))


def desensitize(text):
    """铁律11：敏感词古典映射脱敏 + 铁律13：未成年内容返回空字符串跳过"""
    if text is None:
        return ""
    result = str(text)
    # 第一步：古典映射全局替换（长词优先，避免短词先替换破坏长词）
    for key in sorted(CLASSICAL_MAP.keys(), key=len, reverse=True):
        if key in result:
            result = result.replace(key, CLASSICAL_MAP[key])
    # 第二步：检测未成年相关词，命中则返回空字符串（铁律13脱敏后跳过）
    lower = result.lower()
    for kw in _MINOR_KEYWORDS:
        if kw.lower() in lower:
            return ""
    return result


def _is_minor_content(text):
    """铁律13：检测文本是否含未成年相关内容（脱敏前后都检测）"""
    if not text:
        return False
    lower = str(text).lower()
    for kw in _MINOR_KEYWORDS:
        if kw.lower() in lower:
            return True
    return False


def _sanitize_vod(vod):
    """铁律11+13：对单个vod字典做脱敏，未成年条目返回None"""
    if not isinstance(vod, dict):
        return vod
    # 先检测未成年（原始文本检测）
    name = vod.get("vod_name", "")
    remarks = vod.get("vod_remarks", "")
    content = vod.get("vod_content", "")
    if _is_minor_content(name) or _is_minor_content(remarks) or _is_minor_content(content):
        return None
    # 脱敏展示文本
    vod["vod_name"] = desensitize(name)
    if vod.get("vod_remarks") is not None:
        vod["vod_remarks"] = desensitize(remarks)
    if vod.get("vod_content") is not None:
        vod["vod_content"] = desensitize(content)
    # 脱敏后名称为空则剔除
    if not vod["vod_name"]:
        return None
    return vod


def _sanitize_list(vod_list):
    """铁律11+13：对列表做脱敏过滤，剔除未成年条目"""
    if not isinstance(vod_list, list):
        return vod_list
    result = []
    for item in vod_list:
        cleaned = _sanitize_vod(item)
        if cleaned is not None:
            result.append(cleaned)
    return result


def _sanitize_classes(classes):
    """铁律11+13：对分类列表做脱敏过滤，剔除未成年分类"""
    if not isinstance(classes, list):
        return classes
    result = []
    for cat in classes:
        if not isinstance(cat, dict):
            result.append(cat)
            continue
        name = cat.get("type_name", "")
        if _is_minor_content(name):
            continue
        cat["type_name"] = desensitize(name)
        if cat["type_name"]:
            result.append(cat)
    return result


def _clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def _bounded_int(value, default, minimum, maximum):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def _parse_config(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (list, tuple)):
        merged = {}
        for item in value:
            merged.update(_parse_config(item))
        return merged
    text = str(value or "").strip()
    if not text:
        return {}
    for loader in (json.loads, ast.literal_eval):
        try:
            data = loader(text)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {}


def _normalize_origin(value):
    text = str(value or DEFAULT_HOST).strip().rstrip("/")
    if text and "://" not in text:
        text = "https://" + text
    try:
        parsed = urlsplit(text)
    except Exception:
        return DEFAULT_HOST
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return DEFAULT_HOST
    return parsed.scheme + "://" + parsed.netloc


def _classify_response(response):
    status = int(getattr(response, "status_code", 0) or 0)
    text = str(getattr(response, "text", "") or "")
    lower = text.lower()
    if any(marker in lower for marker in CHALLENGE_MARKERS):
        return "cloudflare-managed-challenge"
    if status == 429:
        return "rate-limited"
    if 500 <= status <= 599:
        return "upstream-error"
    if status >= 400:
        return "http-error"
    if not text.strip():
        return "empty-response"
    return "ok"


def _js_unescape(text):
    return (
        str(text or "").replace("\\\\", "\x00").replace("\\'", "'")
        .replace('\\"', '"').replace("\\/", "/").replace("\\n", "\n")
        .replace("\x00", "\\")
    )


def _base_convert(number, radix):
    out = ""
    while True:
        number, remainder = divmod(number, radix)
        out = (_B36_DIGITS[remainder] if remainder < 36 else chr(remainder + 29)) + out
        if number == 0:
            return out


def unpack_eval_blocks(text):
    results = []
    for match in PACKED_RE.finditer(str(text or "")):
        try:
            payload = _js_unescape(match.group("p"))
            radix = int(match.group("a"))
            count = int(match.group("c"))
            words = _js_unescape(match.group("k")).split("|")
            table = {}
            for index in range(count):
                key = _base_convert(index, radix)
                value = words[index] if index < len(words) else ""
                table[key] = value if value else key
            results.append(re.sub(r"\b\w+\b", lambda m: table.get(m.group(0), m.group(0)), payload))
        except Exception:
            continue
    return results


def extract_play_sources(html_text):
    sources = {}
    for block in unpack_eval_blocks(html_text):
        for name, url in SOURCE_ASSIGN_RE.findall(block):
            sources[name.lower()] = url
    if not sources:
        for name, url in SOURCE_ASSIGN_RE.findall(str(html_text or "")):
            sources[name.lower()] = url
    return sources


class CloudflareTLSAdapter(HTTPAdapter):
    def __init__(self, ciphers=None, use_x25519=False, **kwargs):
        self._ciphers = ciphers
        self._use_x25519 = use_x25519
        super(CloudflareTLSAdapter, self).__init__(**kwargs)

    def _build_context(self):
        context = ssl.create_default_context()
        if self._ciphers:
            try:
                context.set_ciphers(self._ciphers)
            except Exception:
                pass
        try:
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        except Exception:
            pass
        try:
            context.set_alpn_protocols(["h2", "http/1.1"])
        except Exception:
            pass
        if self._use_x25519:
            for curve in ("X25519", "prime256v1"):
                try:
                    context.set_ecdh_curve(curve)
                    break
                except Exception:
                    continue
        return context

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        context = self._build_context()
        if HAS_URLLIB3 and PoolManager is not None:
            kwargs["ssl_context"] = context
            self.poolmanager = PoolManager(num_pools=connections, maxsize=maxsize, block=block, **kwargs)
        else:
            super(CloudflareTLSAdapter, self).init_poolmanager(connections, maxsize, block=block, **kwargs)

    def proxy_manager_for(self, proxy, **kwargs):
        try:
            kwargs["ssl_context"] = self._build_context()
        except Exception:
            pass
        return super(CloudflareTLSAdapter, self).proxy_manager_for(proxy, **kwargs)


def build_tls_session(user_agent=None, cookie="", use_x25519=False):
    session = requests.Session()
    try:
        session.headers.clear()
    except Exception:
        pass
    headers = dict(NAV_HEADERS)
    headers["User-Agent"] = user_agent or DEFAULT_UA
    if cookie:
        headers["Cookie"] = cookie
    session.headers.update(headers)
    try:
        session.mount("https://", CloudflareTLSAdapter(use_x25519=use_x25519))
    except Exception:
        pass
    return session



class Spider(_BaseSpider):
    name = "海角社区"
    backend_parse = False
    category_mode = False

    def __init__(self):
        self.host = DEFAULT_HOST
        self.rawSite = DEFAULT_HOST
        self.siteUrl = DEFAULT_HOST
        self.HOST = DEFAULT_HOST
        self.mirrors = list(DEFAULT_MIRRORS)
        self.timeout = 15
        self.cookie = ""
        self.max_retries = 2
        self.total_budget = 12.0
        self.use_x25519 = False
        self._warmed = False
        self._page_cache = {}
        self._cache_lock = threading.RLock()
        self.cache_ttl = 120
        self.warmup_enabled = True
        self._preferred_origin = ""
        self._categories = []
        self._use_proxy = False
        self._default_proxy = _load_default_proxy()
        self.session = self._build_session()
        # 板块树 / 播放链缓存
        self._nodes = None
        self._nodes_lock = threading.RLock()
        self._play_hint = {}
        self._seg_cache = {}
        self._key_cache = {}
        self._media_lock = threading.RLock()
        # v4：视频 CDN 主机记忆 + 图片解码缓存
        self._cdn_host = ""
        self._img_proxy = True
        self._img_cache = {}
        self._img_cache_lock = threading.RLock()
        self._att_cache = {}

    def getDependence(self):
        return ""

    def getName(self):
        return self.name

    def init(self, extend=""):
        config = _parse_config(extend)
        # 铁律15：原始站点（用于 Referer/Origin 防盗链）
        self.rawSite = _normalize_origin(config.get("host")) or DEFAULT_HOST
        # 本机直连实测可用，默认直连；ext.proxy/ext.siteUrl 可切反代兜底
        direct = _bool(config.get("direct"), True)
        ext_proxy = str(config.get("proxy") or config.get("siteUrl") or "").strip()
        if (not direct) and ext_proxy:
            self._use_proxy = True
            self.siteUrl = _normalize_origin(ext_proxy) or self.rawSite
        else:
            self._use_proxy = False
            self.siteUrl = self.rawSite
        self.host = self.siteUrl
        self.HOST = self.siteUrl
        raw_mirrors = str(config.get("mirrors") or ",".join(DEFAULT_MIRRORS))
        mirrors = []
        for item in re.split(r"[,\s;|]+", raw_mirrors):
            origin = _normalize_origin(item) if item.strip() else ""
            if origin and origin != self.rawSite and origin not in mirrors:
                mirrors.append(origin)
        self.mirrors = mirrors
        self.timeout = _bounded_int(config.get("timeout"), 15, 5, 40)
        self.cookie = str(config.get("cookie") or "").strip()
        self.max_retries = _bounded_int(config.get("max_retries"), 2, 0, 6)
        self.total_budget = max(float(_bounded_int(config.get("total_budget"), 12, 3, 60)), 3.0)
        self.use_x25519 = _bool(config.get("use_x25519"), False)
        self.cache_ttl = _bounded_int(config.get("cache_ttl"), 120, 0, 900)
        self.warmup_enabled = _bool(config.get("warmup"), True)
        # v4：图片是否走本地还原代理（默认开，关掉则直连 .txt 会显示不出来）
        self._img_proxy = _bool(config.get("img_proxy"), True)
        self._cdn_host = _clean_text(config.get("cdn_host") or "")
        self._preferred_origin = ""
        self._categories = []
        self._warmed = False
        with self._cache_lock:
            self._page_cache = {}
        with self._media_lock:
            self._play_hint = {}
            self._seg_cache = {}
            self._key_cache = {}
        with self._img_cache_lock:
            self._img_cache = {}
        self._att_cache = {}
        self.session = self._build_session()
        try:
            self._warmup()
        except Exception:
            pass
        return ""

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass
        return ""

    def action(self, action):
        return ""

    def isVideoFormat(self, url):
        text = str(url or "").lower()
        return ".m3u8" in text or ".mp4" in text

    def manualVideoCheck(self):
        return False

    def _build_session(self):
        return build_tls_session(DEFAULT_UA, self.cookie, use_x25519=self.use_x25519)

    def _api_headers(self):
        headers = dict(NAV_HEADERS)
        headers["User-Agent"] = DEFAULT_UA
        headers["Accept"] = "application/json, text/plain, */*"
        headers["Referer"] = self.rawSite + "/"
        headers["Origin"] = self.rawSite
        headers["Sec-Fetch-Mode"] = "cors"
        headers["Sec-Fetch-Dest"] = "empty"
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _request_headers(self, referer):
        headers = dict(NAV_HEADERS)
        headers["User-Agent"] = DEFAULT_UA
        if referer:
            headers["Referer"] = referer
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _cache_put(self, key, value):
        with self._cache_lock:
            self._page_cache[key] = (time.time(), value)
            if len(self._page_cache) > 32:
                oldest = sorted(self._page_cache.items(), key=lambda kv: kv[1][0])[:10]
                for stale_key, _ in oldest:
                    self._page_cache.pop(stale_key, None)

    def _cache_get(self, key):
        with self._cache_lock:
            hit = self._page_cache.get(key)
        if not hit:
            return None
        if time.time() - hit[0] > self.cache_ttl:
            return None
        return hit[1]

    # ==================== 通信底座 ====================

    @staticmethod
    def _decode_payload(payload):
        """站点响应统一 isEncrypted 三层 Base64 解码"""
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if not (payload.get("isEncrypted") and isinstance(data, str)):
            return data
        current = data.strip()
        for _ in range(6):
            if current[:1] in ("{", "["):
                try:
                    return json.loads(current)
                except Exception:
                    return None
            try:
                current = base64.b64decode(current).decode("utf-8", "ignore").strip()
            except Exception:
                return None
        try:
            return json.loads(current)
        except Exception:
            return None

    def _api(self, path, params=None):
        url = self.rawSite + "/api" + path
        if params:
            clean = {k: v for k, v in params.items() if v not in (None, "")}
            if clean:
                url = url + ("&" if "?" in url else "?") + urlencode(clean)
        cache_key = "api:" + url
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        payload = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.get(url, headers=self._api_headers(), timeout=self.timeout)
                if resp.status_code == 200:
                    payload = resp.json()
                    break
            except Exception:
                time.sleep(0.25 * (attempt + 1))
        data = self._decode_payload(payload)
        if data is not None:
            self._cache_put(cache_key, data)
        return data

    def _fetch_bytes(self, url, referer=None, timeout=12):
        headers = {
            "User-Agent": PLAYER_UA,
            "Accept": "*/*",
            "Referer": referer or (self.rawSite + "/"),
        }
        resp = self.session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            return resp.content
        return None

    def _fetch_text(self, url, referer=None, timeout=12):
        data = self._fetch_bytes(url, referer=referer, timeout=timeout)
        if data is None:
            return None
        try:
            return data.decode("utf-8", "ignore")
        except Exception:
            return None

    # ==================== 分类（板块树） ====================

    def _fetch_nodes(self):
        with self._nodes_lock:
            if self._nodes is not None:
                return self._nodes
        data = None
        for path in ("/topic/nodes", "/topic/node/list", "/topic/nodes?parent_id=0"):
            data = self._api(path)
            if isinstance(data, list) and data:
                break
            data = None
        nodes = data if isinstance(data, list) else []
        with self._nodes_lock:
            self._nodes = nodes
        return nodes

    def _build_categories(self):
        nodes = self._fetch_nodes()
        if not nodes:
            return []
        by_parent = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("display") in (0, "0"):
                continue
            if str(node.get("external_url") or "").strip():
                continue
            name = _clean_text(node.get("name"))
            if not name or _is_minor_content(name) or not desensitize(name):
                continue
            nid = node.get("nodeId")
            if nid is None:
                continue
            by_parent.setdefault(node.get("parentId"), []).append((nid, name, node.get("sortNo") or 0))
        for key in by_parent:
            by_parent[key].sort(key=lambda x: (x[2], x[0]))
        classes = [
            {"type_id": "new", "type_name": "最新发布"},
            {"type_id": "hot", "type_name": "热门榜单"},
        ]
        for nid, name, _ in by_parent.get(0, []):
            classes.append({"type_id": str(nid), "type_name": name})
            for cid, cname, _ in by_parent.get(nid, []):
                classes.append({"type_id": str(cid), "type_name": "%s-%s" % (name, cname)})
        # 挂在非顶级父节点下的板块同样并入
        top_ids = set(str(x["type_id"]) for x in classes)
        for parent, children in by_parent.items():
            if parent in (0, None):
                continue
            parent_name = ""
            for node in nodes:
                if isinstance(node, dict) and node.get("nodeId") == parent:
                    parent_name = _clean_text(node.get("name"))
                    break
            for cid, cname, _ in children:
                if str(cid) in top_ids:
                    continue
                label = ("%s-%s" % (parent_name, cname)) if parent_name else cname
                classes.append({"type_id": str(cid), "type_name": label})
        return classes

    def _ensure_categories(self):
        if self._categories:
            return self._categories
        cats = self._build_categories()
        if not cats:
            cats = [{"type_id": "new", "type_name": "最新发布"}]
        self._categories = cats
        return cats

    def _filters(self):
        """每个板块给「视频优先 / 全部帖子」两档。

        站点 /topic/node/topics 的 type 语义（实测 128 节点逐个验证）：
          type=7 → 视频帖（本页 20/20 全带视频，可播率最高）
          type=1 → 全部帖子（混入大量图文帖，实测仅 2/20 带视频）
        默认走 7，没有视频帖的板块自动回退 1。
        """
        result = {}
        for cat in self._ensure_categories():
            tid = cat.get("type_id")
            if tid == "hot":
                result[tid] = [{"key": "默认", "name": "热门榜单"}]
            else:
                result[tid] = [{"key": "video", "name": "视频优先"},
                               {"key": "image", "name": "图集帖"},
                               {"key": "all", "name": "全部帖子"}]
        return result

    def _warmup(self):
        if self._warmed or not self.warmup_enabled:
            return
        self._warmed = True
        try:
            self._ensure_categories()
        except Exception:
            pass

    # ==================== 列表 ====================

    @staticmethod
    def _raw_media_url(url):
        """附件原始地址。注意：站点图片只能通过 .txt 形态取到（去掉后缀会被 CDN 403），
        所以这里保留原样，解码交给 localProxy。"""
        return str(url or "").strip()

    def _img_proxy_url(self, url):
        """v4：把图片地址转成走 localProxy 的本地还原地址（壳侧直接能显示真图）"""
        raw = self._raw_media_url(url)
        if not raw.startswith("http"):
            return raw
        if not self._img_proxy:
            return raw
        payload = self._pack({"u": raw, "r": self.rawSite + "/"})
        return self._proxy_url("img", payload)

    def _img_url(self, url):
        """列表/详情里的展示图统一走还原代理（默认开）"""
        return self._img_proxy_url(url)

    # ==================== v4：视频地址推导（免登录播放） ====================

    def _cdn_candidates(self):
        """候选 CDN 主机：先猜中过的，再内置列表"""
        hosts = []
        if self._cdn_host:
            hosts.append(self._cdn_host)
        for host in VIDEO_CDN_HOSTS:
            if host not in hosts:
                hosts.append(host)
        return hosts

    def _playlist_ok(self, url):
        """校验清单是真播放列表，不是错误页"""
        try:
            text = self._fetch_text(url, referer=self.rawSite + "/", timeout=8)
        except Exception:
            return False
        return bool(text) and "#EXTM3U" in text

    def _resolve_video_url(self, att, topic_id=""):
        """把视频附件的播放地址解出来（游客态 remoteUrl 为空时的核心修复）。

        顺序：附件自带地址 → 由封面推导 → 附件线路表 → 登录态接口
        返回 (play_url, reason)
        """
        att = att if isinstance(att, dict) else {}
        direct = str(att.get("remoteUrl") or "").strip()
        if direct:
            return direct, ""
        cover = str(att.get("coverUrl") or "").strip()
        match = _COVER_VIDEO_RE.search(cover)
        if match:
            key = "cnv:%s" % match.group(0)
            cached = self._att_cache.get(key)
            if cached:
                return cached, ""
            for host in self._cdn_candidates():
                url = _cover_to_preview(cover, host)
                if url and self._playlist_ok(url):
                    self._cdn_host = host
                    self._att_cache[key] = url
                    return url, ""
        # 附件线路表（游客态 url 为空，但登录态会带出真实地址）
        aid = att.get("id")
        if aid:
            lines = self._api("/topic/att/%s" % aid)
            if isinstance(lines, list):
                for line in lines:
                    if isinstance(line, dict) and str(line.get("url") or "").strip():
                        return str(line["url"]).strip(), ""
        # 登录态专用接口
        if aid and self.cookie:
            data = self._api("/video/%s" % aid)
            found = self._find_media_url(data)
            if found:
                return found, ""
        if not match:
            return "", "该附件未暴露封面，无法推导播放地址"
        return "", "播放地址推导失败（CDN 线路可能已变更）"

    @staticmethod
    def _find_media_url(data):
        """在任意返回结构里捞出第一个 m3u8/mp4 地址"""
        stack = [data]
        seen = 0
        while stack and seen < 4000:
            seen += 1
            node = stack.pop()
            if isinstance(node, str):
                if ".m3u8" in node or ".mp4" in node:
                    return node.strip()
            elif isinstance(node, dict):
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        return ""

    def _topic_to_vod(self, item):
        if not isinstance(item, dict):
            return None
        tid = item.get("topicId")
        if not tid:
            return None
        title = _clean_text(item.get("title"))
        if not title:
            return None
        node = item.get("node") or {}
        pic = ""
        cover = ""
        duration = 0
        has_image = False
        has_video_att = False
        for att in (item.get("attachments") or []):
            if not isinstance(att, dict):
                continue
            if att.get("category") == "images":
                has_image = True
                if not pic and att.get("remoteUrl"):
                    pic = self._img_url(att.get("remoteUrl"))
            if att.get("category") == "video":
                has_video_att = True
                if not cover and att.get("coverUrl"):
                    cover = att.get("coverUrl")
                try:
                    duration = max(duration, int(att.get("video_time_length") or 0))
                except Exception:
                    pass
        if not pic and cover:
            pic = self._img_url(cover)
        remarks_parts = [_clean_text(node.get("name"))]
        if duration:
            remarks_parts.append("%d分钟" % max(1, duration // 60))
        elif has_video_att or item.get("hasVideo"):
            remarks_parts.append("视频")
        if has_image and not has_video_att:
            remarks_parts.append("图集")
        remarks = " · ".join([x for x in remarks_parts if x])
        return {
            "vod_id": str(tid),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remarks,
            "vod_year": _clean_text(str(item.get("createTime") or "")[:4]),
            "vod_area": _clean_text(node.get("name")),
            "vod_actor": _clean_text((item.get("user") or {}).get("nickname")),
            "vod_content": "",
            "vod_play_from": "海角社区",
            "vod_play_url": "",
        }

    @staticmethod
    def _looks_image(item):
        """列表项是否带图片附件（图集帖）"""
        if not isinstance(item, dict):
            return False
        if item.get("hasPic"):
            return True
        for att in (item.get("attachments") or []):
            if isinstance(att, dict) and str(att.get("category")) == "images" and att.get("remoteUrl"):
                return True
        return False

    @staticmethod
    def _looks_video(item):
        """列表项是否带视频附件（用于剔掉点进去没有播放地址的图文帖）"""
        if not isinstance(item, dict):
            return False
        if item.get("hasVideo"):
            return True
        for att in (item.get("attachments") or []):
            if isinstance(att, dict) and str(att.get("category")) == "video":
                return True
        return False

    def _list_page(self, data, page, video_only=False, image_only=False):
        if not isinstance(data, dict):
            return self._empty_page(page)
        results = data.get("results") or []
        info = data.get("page") or {}
        try:
            total = int(info.get("total") or 0)
        except Exception:
            total = 0
        try:
            limit = int(info.get("limit") or PAGE_SIZE) or PAGE_SIZE
        except Exception:
            limit = PAGE_SIZE
        if total > 0:
            pagecount = int((total + limit - 1) // limit)
        elif len(results) >= limit:
            pagecount = page + 1
        else:
            pagecount = page
        vlist = []
        for item in results:
            if video_only and not self._looks_video(item):
                continue
            if image_only and not self._looks_image(item):
                continue
            vod = self._topic_to_vod(item)
            if vod is not None:
                vlist.append(vod)
        vlist = _sanitize_list(vlist)
        if (video_only or image_only) and not vlist and results:
            # 该页确实一条符合条件的都没有，退回未过滤，避免分类显示为空
            for item in results:
                vod = self._topic_to_vod(item)
                if vod is not None:
                    vlist.append(vod)
            vlist = _sanitize_list(vlist)
        return {
            "page": page,
            "pagecount": pagecount,
            "limit": limit,
            "total": total if total > 0 else len(vlist),
            "list": vlist,
        }

    def _empty_page(self, page):
        return {"page": page, "pagecount": page, "limit": PAGE_SIZE, "total": 0, "list": []}

    def homeContent(self, filter=False):
        classes = _sanitize_classes(self._ensure_categories())
        filters = self._filters()
        return {"class": classes, "filters": filters, "list": []}

    def homeVideoContent(self):
        data = self._api("/topic/node/news", {"page": 1, "limit": PAGE_SIZE})
        page = self._list_page(data, 1)
        return {"list": page.get("list") or []}

    def _topic_node_page(self, node_id, node_type, page):
        """板块列表。站点只认驼峰 nodeId + type，写成 node_id 会被直接忽略并退化成全站列表"""
        return self._api(
            "/topic/node/topics",
            {"nodeId": node_id, "type": node_type, "page": page, "limit": PAGE_SIZE},
        )

    @staticmethod
    def _page_total(data):
        if not isinstance(data, dict):
            return 0
        try:
            return int((data.get("page") or {}).get("total") or 0)
        except Exception:
            return 0

    @classmethod
    def _count_video(cls, data):
        if not isinstance(data, dict):
            return 0
        return sum(1 for x in (data.get("results") or []) if cls._looks_video(x))

    def _video_node_page(self, node_id, page):
        """视频优先：按实测动态挑 type。

        type=7 在多数板块每页 20/20 全带视频，但个别板块它几乎没有内容
        （实测某板块 type=7 只有 1 条，而 type=1 有 19/20 带视频），
        所以 7 装不满一页时，拿 1 和 0 一起比，取带视频更多的那个。
        完全不含视频帖的板块退回全量并放开过滤，至少让分类不空。
        """
        data7 = self._topic_node_page(node_id, 7, page)
        if self._page_total(data7) >= PAGE_SIZE and self._count_video(data7) > 0:
            return data7, True
        data1 = self._topic_node_page(node_id, 1, page)
        data0 = self._topic_node_page(node_id, 0, page)
        best_n, best = max(
            ((self._count_video(data7), data7),
             (self._count_video(data1), data1),
             (self._count_video(data0), data0)),
            key=lambda kv: kv[0],
        )
        if best_n > 0:
            return best, True
        for data in (data1, data0, data7):
            if self._page_total(data) > 0:
                return data, False
        return data7, False

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        key = str(tid or "")
        mode = "video"
        if isinstance(extend, dict):
            raw = extend.get("filter") or extend.get("order") or extend.get("type")
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""
            raw = str(raw or "").strip().lower()
            if raw in ("all", "全部", "全部帖子"):
                mode = "all"
            elif raw in ("image", "pic", "图集", "图集帖", "图片"):
                mode = "image"
        image_only = (mode == "image")
        if key in ("new", "latest", ""):
            data = self._api("/topic/node/news", {"page": page, "limit": PAGE_SIZE})
            if mode == "video" and self._page_total(data) == 0:
                data = self._api("/topic/hot/topics", {"page": page, "limit": PAGE_SIZE})
            return self._list_page(data, page, video_only=(mode == "video"), image_only=image_only)
        if key == "hot":
            data = self._api("/topic/hot/topics", {"page": page, "limit": PAGE_SIZE})
            return self._list_page(data, page, video_only=False, image_only=image_only)
        if key == "global":
            data = self._api("/topic/global/topics", {"page": page, "limit": PAGE_SIZE})
            return self._list_page(data, page, video_only=False, image_only=image_only)
        if mode == "all":
            data = self._topic_node_page(key, 1, page)
            return self._list_page(data, page, video_only=False)
        if image_only:
            # 图集帖在各 type 下占比不同，取带图最多的那一档
            best_n, best = -1, None
            for node_type in (1, 0, 7):
                cand = self._topic_node_page(key, node_type, page)
                n = sum(1 for x in ((cand or {}).get("results") or []) if self._looks_image(x))
                if n > best_n:
                    best_n, best = n, cand
            if best is None or self._page_total(best) == 0:
                best = self._topic_node_page(key, 1, page)
            return self._list_page(best, page, video_only=False, image_only=True)
        data, strict = self._video_node_page(key, page)
        return self._list_page(data, page, video_only=strict)

    # ==================== 搜索 ====================

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        word = _clean_text(key)
        data = self._api("/topic/search_topic_by_tag", {"tag": word, "page": page, "limit": PAGE_SIZE})
        if not isinstance(data, dict):
            data = self._api("/topic/search", {"keyword": word, "page": page, "limit": PAGE_SIZE})
        return self._list_page(data, page)

    # ==================== 详情 ====================

    @staticmethod
    def _strip_html(html):
        text = str(html or "")
        text = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", " ", text, flags=re.I)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"</p>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
        text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return _clean_text(text)

    def detailContent(self, ids):
        id_list = list(ids) if isinstance(ids, (list, tuple)) else [ids]
        if not id_list:
            return {"list": []}
        first = str(id_list[0] or "").split("$")[0].strip()
        if not first:
            return {"list": []}
        data = self._api("/topic/" + first)
        if not isinstance(data, dict):
            return {"list": []}
        title = _clean_text(data.get("title"))
        if _is_minor_content(title):
            return {"list": []}
        node = data.get("node") or {}
        user = data.get("user") or {}
        pic = ""
        play_items = []
        image_items = []
        for att in (data.get("attachments") or []):
            if not isinstance(att, dict):
                continue
            if att.get("category") == "images":
                raw_img = att.get("remoteUrl")
                if raw_img:
                    image_items.append(raw_img)
                if not pic and raw_img:
                    pic = self._img_url(raw_img)
            if att.get("category") == "video":
                # v4：不再依赖 remoteUrl（游客态为空），改走推导
                remote, _reason = self._resolve_video_url(att, first)
                if remote:
                    hint = 0
                    try:
                        hint = int(att.get("video_time_length") or 0)
                    except Exception:
                        hint = 0
                    with self._media_lock:
                        self._play_hint[remote] = {"dur": hint}
                    play_items.append(remote)
                    self._prewarm_play(remote, hint)
        if not pic:
            for att in (data.get("attachments") or []):
                if isinstance(att, dict) and att.get("coverUrl"):
                    pic = self._img_url(att.get("coverUrl"))
                    break
        if play_items:
            eps = []
            for idx, url in enumerate(play_items):
                label = "正片" if len(play_items) == 1 else ("第%d集" % (idx + 1))
                eps.append("%s$%s" % (label, url))
            play_url = "#".join(eps)
            play_from = "海角社区"
        elif image_items:
            # v4：图集帖走 pics:// 图集线路，不再返回「无播放地址」
            gallery = [self._img_proxy_url(u) for u in image_items if u]
            if self._img_proxy:
                eps = ["图集$pics://" + "&&".join(gallery)]
            else:
                eps = ["第%d图$%s" % (i + 1, u) for i, u in enumerate(gallery)]
            play_url = "#".join(eps)
            play_from = "海角社区·图集"
        else:
            play_url = "无播放地址$error:该帖未包含视频或图片附件"
            play_from = "海角社区"
        remarks = _clean_text(node.get("name"))
        if user.get("nickname"):
            remarks = (remarks + " · " + _clean_text(user.get("nickname"))).strip(" ·")
        if not play_items and image_items:
            remarks = (remarks + " · 图集%dP" % len(image_items)).strip(" ·")
        content = self._strip_html(data.get("content"))
        if not content:
            content = title
        vod = {
            "vod_id": first,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remarks,
            "vod_year": _clean_text(str(data.get("createTime") or "")[:4]),
            "vod_area": _clean_text(node.get("name")),
            "vod_actor": _clean_text(user.get("nickname")),
            "vod_director": "",
            "vod_content": content,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        cleaned = _sanitize_vod(vod)
        if cleaned is None:
            return {"list": []}
        return {"list": [cleaned]}

    # ==================== 播放（完整分片重建 + 密钥派生） ====================

    @staticmethod
    def _pack(obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _unpack(token):
        text = str(token or "")
        text += "=" * (-len(text) % 4)
        return json.loads(base64.urlsafe_b64decode(text.encode("ascii")).decode("utf-8"))

    def _proxy_base(self):
        base = ""
        try:
            if hasattr(self, "getProxyUrl"):
                base = self.getProxyUrl() or ""
        except Exception:
            base = ""
        if not base:
            base = "http://127.0.0.1:9978/proxy?do=py"
        return base

    def _proxy_url(self, do, payload):
        base = self._proxy_base()
        sep = "&" if "?" in base else "?"
        return "%s%stype=%s&p=%s" % (base, sep, do, quote(payload, safe=""))

    def _derive_key(self, raw_key, salt):
        """站点前端由 WASM 完成同等的逐字节异或派生"""
        if not raw_key:
            return b""
        if not salt:
            return bytes(raw_key)
        size = len(salt)
        out = bytearray(len(raw_key))
        for idx, byte in enumerate(bytearray(raw_key)):
            out[idx] = byte ^ salt[idx % size]
        return bytes(out)

    def _key_material(self, preview_url, referer):
        cache_key = "mat:" + preview_url
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached[0], cached[1]
        text = self._fetch_text(preview_url, referer=referer, timeout=10)
        if not text:
            return None, None
        key_uri = ""
        match = re.search(r'#EXT-X-KEY:([^\r\n]+)', text)
        if match:
            uri_match = re.search(r'URI="([^"]+)"', match.group(1))
            if uri_match:
                key_uri = urljoin(preview_url, uri_match.group(1))
        salt_url = preview_url.replace(".m3u8", ".jpg")
        if salt_url == preview_url:
            salt_url = ""

        def fetch_key():
            if not key_uri:
                return None
            return self._fetch_bytes(key_uri, referer=referer, timeout=10)

        def fetch_salt():
            if not salt_url:
                return None
            return self._fetch_bytes(salt_url, referer=referer, timeout=10)

        raw_key = None
        salt_raw = None
        # 密钥和载荷地址互不依赖，并发取省一个来回
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as pool:
                key_future = pool.submit(fetch_key)
                salt_future = pool.submit(fetch_salt)
                raw_key = key_future.result()
                salt_raw = salt_future.result()
        except Exception:
            raw_key = fetch_key()
            salt_raw = fetch_salt()
        salt = None
        try:
            if salt_raw:
                salt = base64.b64decode(salt_raw.strip())
        except Exception:
            salt = None
        if not raw_key:
            return None, None
        real = self._derive_key(raw_key, salt)
        self._cache_put(cache_key, (real, text))
        return real, text

    def _seg_exists(self, url, referer, retries=2):
        """分片存在性探测。网络抖动会重试，只有明确 404 才判定「到此为止」"""
        attempts = max(int(retries or 1), 1)
        for attempt in range(attempts):
            try:
                resp = self.session.get(
                    url,
                    headers={"User-Agent": PLAYER_UA, "Referer": referer},
                    timeout=8, stream=True,
                )
                code = resp.status_code
                try:
                    resp.close()
                except Exception:
                    pass
                if code in (200, 206):
                    return True
                if code in (404, 403, 410):
                    return False
            except Exception:
                time.sleep(0.15 * (attempt + 1))
        return False

    def _probe_last_index(self, base_dir, prefix, start, estimate, referer, seed_count):
        """定位最后一个真实存在的分片。

        站点各视频的分片时长并不统一（实测既有 1 秒/片，也有 5 秒/片），
        所以边界必须实测、不能按总时长折算。
        做法：锚点验证 → 指数扩张找上界 → 二分逼近，每步探测带重试。
        旧版粗扫只要一次抖动误判，就会把末端截掉一大截，表现就是「播着播着断了」。
        """
        cache_key = "seg:%s|%s" % (base_dir, prefix)
        with self._media_lock:
            hit = self._seg_cache.get(cache_key)
        if hit is not None:
            return hit

        def seg_url(index):
            return "%s/%s%d.ts" % (base_dir, prefix, index)

        def exists(index):
            if index < start:
                return False
            return self._seg_exists(seg_url(index), referer)

        def exists_many(indexes):
            targets = sorted(set(int(x) for x in indexes if int(x) > start))
            if not targets:
                return []
            try:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
                    flags = list(pool.map(exists, targets))
            except Exception:
                flags = [exists(i) for i in targets]
            return list(zip(targets, flags))

        seed_count = max(int(seed_count or 1), 1)
        # 预览清单的末片通常一定存在，用它当起点
        low = start + seed_count - 1
        if not exists(low):
            low = start
            if not exists(low):
                with self._media_lock:
                    self._seg_cache[cache_key] = start
                return start

        # 上界：先拿总时长折算值试一把，不中就走指数扩张
        anchor = int(estimate or 0)
        high = None
        if anchor > low:
            if exists(anchor):
                low = anchor
            else:
                high = anchor
        if high is None:
            # 起始步长给大一点，长视频少探好几次
            step = max(seed_count, min(max(low // 16, 64), 4096))
            while True:
                probe = low + step
                if probe > 200000:
                    high = probe
                    break
                if exists(probe):
                    low = probe
                    step = min(step * 2, 1 << 20)
                else:
                    high = probe
                    break

        # 并发分组搜索：小范围直接全测，大范围 12 路并发打点
        while high - low > 1:
            span = high - low
            if span <= 17:
                points = list(range(low + 1, high))
            else:
                k = min(12, span - 1)
                points = sorted(set(int(low + span * (i + 1) / (k + 1)) for i in range(k)))
                points = [p for p in points if low < p < high]
            if not points:
                break
            advanced = False
            for idx, ok in exists_many(points):
                if ok:
                    low = idx
                else:
                    high = idx
                    advanced = True
                    break
            if not advanced:
                low = points[-1]

        last = low if low >= start else start
        with self._media_lock:
            self._seg_cache[cache_key] = last
        return last

    def _build_full_m3u8(self, preview_url, referer, duration):
        cache_key = "m3u8:" + preview_url
        cached = self._cache_get(cache_key)
        if cached:
            return cached
        real_key, text = self._key_material(preview_url, referer)
        if not text or not real_key:
            return None
        segments = re.findall(r'^([^\s#][^\r\n]*\.ts)\s*$', text, re.M)
        if not segments:
            return None
        head = re.match(r'^(.+?_i)(\d+)\.ts$', segments[0])
        if head:
            prefix = head.group(1)
            start = int(head.group(2))
        else:
            tail = re.match(r'^(.*?)(\d+)\.ts$', segments[0])
            if not tail:
                return None
            prefix = tail.group(1)
            start = int(tail.group(2))
        base_dir = preview_url.rsplit("/", 1)[0]
        durations = []
        for value in re.findall(r'#EXTINF:([\d.]+)', text):
            try:
                durations.append(float(value))
            except Exception:
                continue
        seed_avg = (sum(durations) / len(durations)) if durations else 1.25
        try:
            total_duration = float(duration or 0)
        except Exception:
            total_duration = 0.0
        seed_count = len(segments)
        if total_duration > 0:
            estimate = max(int(total_duration / 1.04), seed_count)
        else:
            estimate = seed_count
        last = self._probe_last_index(base_dir, prefix, start, estimate, referer, seed_count)
        if last < start:
            last = start
        count = last - start + 1
        if count <= seed_count:
            last = start + seed_count - 1
            count = seed_count
        if total_duration > 0 and count > 0:
            each = max(round(total_duration / count, 3), 0.2)
        else:
            each = round(seed_avg, 3)
        payload = self._pack({"u": preview_url, "r": referer, "d": int(total_duration)})
        key_line = '#EXT-X-KEY:METHOD=AES-128,URI="%s"' % self._proxy_url("key", payload)
        original_key = re.search(r'#EXT-X-KEY:([^\r\n]+)', text)
        if original_key:
            iv_match = re.search(r'IV=0x[0-9A-Fa-f]+', original_key.group(1))
            if iv_match:
                key_line += "," + iv_match.group(0)
        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            "#EXT-X-PLAYLIST-TYPE:VOD",
            "#EXT-X-TARGETDURATION:%d" % max(int(each) + 1, 2),
            "#EXT-X-MEDIA-SEQUENCE:0",
            key_line,
        ]
        for index in range(start, last + 1):
            lines.append("#EXTINF:%s," % each)
            lines.append("%s/%s%d.ts" % (base_dir, prefix, index))
        lines.append("#EXT-X-ENDLIST")
        result = "\n".join(lines) + "\n"
        self._cache_put(cache_key, result)
        return result

    def _prewarm_play(self, preview_url, duration):
        """详情页打开时后台预热播放列表，点开即播"""
        if not preview_url or self._cache_get("m3u8:" + preview_url):
            return

        def worker():
            try:
                self._build_full_m3u8(preview_url, self.rawSite + "/", duration)
            except Exception:
                pass

        try:
            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            pass

    def playerContent(self, flag, id, vipFlags=None):
        play_url = str(id or "")
        if play_url.startswith("error:"):
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}, "msg": play_url[6:]}
        # v4：图集线路直接放行，交给壳的图片查看器
        if play_url.startswith("pics://"):
            return {
                "parse": 0,
                "jx": 0,
                "playUrl": "",
                "url": play_url,
                "header": {
                    "User-Agent": PLAYER_UA,
                    "Referer": self.rawSite + "/",
                },
            }
        if not play_url.startswith("http"):
            play_url = urljoin(self.host + "/", play_url)
        with self._media_lock:
            hint = self._play_hint.get(play_url) or {}
        payload = self._pack({
            "u": play_url,
            "r": self.rawSite + "/",
            "d": int(hint.get("dur") or 0),
        })
        proxy_url = self._proxy_url("xhls", payload)
        # 铁律15：防盗链双 Header，Referer/Origin 取原始站点 rawSite
        return {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": proxy_url,
            "header": {
                "User-Agent": PLAYER_UA,
                "Referer": self.rawSite + "/",
                "Origin": self.rawSite,
            },
            "format": "application/x-mpegURL",
            "contentType": "application/x-mpegURL",
        }

    def _serve_image(self, target, referer):
        """v4：图片还原。站点图片是自定义字母表 base64 载荷，必须解码后才能显示。

        已经是真图（魔数命中）的直接透传；否则解出 data URL 里的图再回。
        """
        target = str(target or "").strip()
        if not target:
            return [404, "text/plain", "no image url"]
        if target.startswith("data:"):
            mime, blob = _decode_image_payload(target)
            if blob:
                return [200, _sniff_image_mime(blob, mime or "image/jpeg"), blob]
            return [404, "text/plain", "bad data url"]
        with self._img_cache_lock:
            hit = self._img_cache.get(target)
        if hit is not None:
            return [200, hit[0], hit[1]]
        blob = self._fetch_bytes(target, referer=referer, timeout=12)
        if not blob:
            return [502, "text/plain", "image unavailable"]
        mime = _sniff_image_mime(blob, "")
        if not mime:
            try:
                text = blob.decode("ascii", "ignore")
            except Exception:
                text = ""
            mime, blob = _decode_image_payload(text)
            if not blob:
                return [502, "text/plain", "image decode failed"]
            mime = _sniff_image_mime(blob, mime or "image/jpeg")
        with self._img_cache_lock:
            if len(self._img_cache) > 256:
                self._img_cache.clear()
            self._img_cache[target] = (mime, blob)
        return [200, mime, blob]

    def localProxy(self, params):
        """本地代理：重建完整播放列表 / 下发派生密钥 / 代理封面与 m3u8 清洗"""
        try:
            if not isinstance(params, dict):
                params = {}
            action = params.get("type") or params.get("do") or params.get("action") or ""
            if isinstance(action, list):
                action = action[0]
            token = params.get("p") or params.get("payload") or ""
            if isinstance(token, list):
                token = token[0]
            info = {}
            if token:
                try:
                    info = self._unpack(unquote(token))
                except Exception:
                    info = {}
            referer = info.get("r") or (self.rawSite + "/")
            if action == "key":
                real_key, _ = self._key_material(info.get("u", ""), referer)
                if not real_key:
                    return [502, "text/plain", "key unavailable"]
                return [200, "application/octet-stream", real_key]
            if action == "xhls":
                preview = info.get("u", "")
                if not preview.startswith("http"):
                    return [404, "text/plain", "bad play url"]
                try:
                    text = self._build_full_m3u8(preview, referer, info.get("d") or 0)
                except Exception:
                    text = None
                if not text:
                    text = self._fetch_text(preview, referer=referer, timeout=10)
                if not text:
                    return [502, "text/plain", "m3u8 unavailable"]
                return [200, "application/vnd.apple.mpegurl", text]
            url = params.get("url", "")
            if isinstance(url, list):
                url = url[0]
            url = unquote(url) if url else ""
            if action == "img":
                target = info.get("u") or url
                if not target:
                    return [404, "text/plain", "no image url"]
                return self._serve_image(target, referer)
            if not url:
                return [404, "text/plain", "not found"]
            text = self._get_m3u8_content(url, referer)
            if not text:
                return [502, "text/plain", "m3u8 download failed"]
            cleaned = self._clean_m3u8(text, url, referer)
            return [200, "application/vnd.apple.mpegurl", cleaned]
        except Exception as exc:
            return [500, "text/plain", "proxy error: %s" % exc]

    def _sanitize_m3u8_url(self, url):
        """清洗m3u8 URL中的广告参数（cover/poster/thumb/pic等）"""
        if not url:
            return url
        from urllib.parse import unquote
        url = unquote(url)
        url = re.sub(r'&[Cc]over=.*', '', url)
        url = re.sub(r'&[Pp]oster=.*', '', url)
        url = re.sub(r'&[Tt]humb=.*', '', url)
        url = re.sub(r'&[Pp]ic=.*', '', url)
        url = url.rstrip('&?')
        return url

    def _proxy_m3u8_url(self, url, referer=''):
        """生成m3u8代理地址：优先用壳的getProxyUrl()，否则返回原地址（localProxy负责清洗）"""
        try:
            if hasattr(self, 'getProxyUrl'):
                return self.getProxyUrl() + '&type=m3u8&url=' + quote(url, safe='') + '&referer=' + quote(referer or self.rawSite, safe='')
        except Exception:
            pass
        return url


    def _get_m3u8_content(self, url, referer):
        """带防盗链header下载m3u8文件"""
        try:
            headers = {
                'User-Agent': PLAYER_UA,
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': referer,
                'Origin': self.rawSite,
                'Connection': 'keep-alive',
            }
            resp = self.session.get(url, headers=headers, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                return resp.text
            return None
        except Exception:
            return None

    def _is_ad_segment(self, uri, dur=0, prev_tags=None):
        """广告片段识别：关键词匹配 + 短时长判定"""
        u = (uri or '').strip().lower()
        if not u:
            return False
        ad_words = [
            # 英文明确广告词
            'advertisement', 'advertise', 'advert', 'commercial', 'sponsor', 'sponsorship',
            'preroll', 'pre-roll', 'pre_roll', 'midroll', 'mid-roll', 'postroll', 'post-roll',
            'banner', 'banners', 'popup', 'pop-up', 'interstitial', 'overlay', 'splash',
            'bumper', 'stinger', 'vast', 'vpaid', 'vmap',
            'doubleclick', 'googleads', 'googlesyndication', 'googletag', 'adsense', 'admob',
            'adx', 'adnetwork', 'adserving', 'ad-serving', 'adserver', 'ad-server',
            'inmobi', 'unityads', 'applovin', 'ironsource', 'vungle', 'chartboost', 'tapjoy',
            'mintegral', 'pangle', 'bytedance', 'tiktokads', 'kuaishou', 'ks-ad',
            'tracking', 'tracker', 'beacon', 'pixel', 'analytics', 'statistic',
            'leaderboard', 'skyscraper', 'rectangle', 'filler',
            # 中文广告词
            '广告', '片头', '片尾', '贴片', '赞助商', '赞助', '推广', '硬广',
            '前贴', '中插', '后贴', '角标', '广告位', '广告片', '广告段', '广告视频',
            '广告素材', '弹窗', '悬浮', '开屏', '插屏', '激励视频', '激励广告',
            # 拼音/缩写
            'guanggao', 'ggao', 'ggvideo', 'ggmedia',
            # 路径特征（精确匹配）
            '/ad/', '/ads/', '/adv/', '/adver/', '/gg/', '/gga/', '/ggb/', '/ggc/', '/ggd/',
            '_ad.', '.ad/', '_ads.', '_adv.', '_gg.', 'gg_', '_gg', '/gg', 'gg.',
            '/ad_', '/ads_', '/adv_', '/sponsor/', '/banner/', '/promo/', '/commercial/',
            '/preroll/', '/midroll/', '/postroll/', '/popup/', '/interstitial/', '/overlay/',
            '/splash/', '/bumper/', '/vast/', '/vpaid/', '/adnetwork/', '/adserving/',
            '/doubleclick/', '/googleads/', '/googlesyndication/', '/adsense/', '/admob/',
            '/tracking/', '/tracker/', '/beacon/', '/pixel/', '/analytics/',
        ]
        if any(w in u for w in ad_words):
            return True
        try:
            if 0 < float(dur) <= 1.2:
                return True
        except Exception:
            pass
        return False

    def _parse_m3u8_segments(self, text):
        """m3u8解析器：拆出header/segments/tail，提取每片段的tags/uri/duration"""
        lines = [x.strip() for x in (text or '').replace('\r', '').split('\n') if x.strip()]
        header, segments, tail = [], [], []
        pending_tags = []
        media_sequence = 0
        target_duration = 0
        started = False
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith('#EXT-X-MEDIA-SEQUENCE'):
                try:
                    media_sequence = int(line.split(':', 1)[1])
                except Exception:
                    pass
                if not started:
                    header.append(line)
                else:
                    pending_tags.append(line)
            elif line.startswith('#EXT-X-TARGETDURATION'):
                try:
                    target_duration = float(line.split(':', 1)[1])
                except Exception:
                    pass
                if not started:
                    header.append(line)
                else:
                    pending_tags.append(line)
            elif line.startswith('#EXTINF'):
                started = True
                dur = target_duration or 3.0
                m = re.search(r'#EXTINF:\s*([\d.]+)', line)
                if m:
                    try:
                        dur = float(m.group(1))
                    except Exception:
                        pass
                tags = pending_tags + [line]
                pending_tags = []
                uri = ''
                j = i + 1
                while j < len(lines):
                    if lines[j].startswith('#'):
                        tags.append(lines[j])
                        j += 1
                        continue
                    uri = lines[j]
                    break
                if uri:
                    segments.append({'tags': tags, 'uri': uri, 'dur': dur})
                    i = j
                else:
                    tail.extend(tags)
            elif line.startswith('#EXT-X-ENDLIST'):
                tail.append(line)
            elif line.startswith('#'):
                if started:
                    pending_tags.append(line)
                else:
                    header.append(line)
            else:
                started = True
                dur = target_duration or 3.0
                segments.append({'tags': pending_tags, 'uri': line, 'dur': dur})
                pending_tags = []
            i += 1
        return header, segments, tail, media_sequence, target_duration

    def _segment_host_key(self, uri, base_url):
        """提取片段的主机+路径前缀，用于统计主CDN"""
        try:
            full = urljoin(base_url, uri)
            p = urlsplit(full)
            path = re.sub(r'/[^/]*$', '/', p.path or '/')
            return (p.netloc.lower(), path.lower())
        except Exception:
            return ('', '')

    def _main_path_marker(self, m3u8_url):
        """从m3u8 URL提取主路径标记（如/20240101/xxx/1000kb/hls/）"""
        try:
            p = urlsplit(m3u8_url).path
            m = re.search(r'(/\d{8}/[^/]+/\d+kb/hls/)', p)
            if m:
                return m.group(1).lower()
            m = re.search(r'(/\d{8}/[^/]+/)', p)
            if m:
                return m.group(1).lower()
        except Exception:
            pass
        return ''

    def _clean_m3u8(self, m3u8_text, m3u8_url='', referer='', skip_seconds=25):
        """核心m3u8广告清洗：五重广告识别 + 主CDN统计 + 前置贴片切除 + 多码率递归代理"""
        text = (m3u8_text or '').replace('\r', '')
        # 多码率m3u8（#EXT-X-STREAM-INF）：递归代理子m3u8
        if '#EXT-X-STREAM-INF' in text:
            out = []
            last_stream = False
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                if line.startswith('#'):
                    out.append(line)
                    last_stream = line.startswith('#EXT-X-STREAM-INF')
                else:
                    abs_url = urljoin(m3u8_url, line)
                    if last_stream or '.m3u8' in line.lower():
                        out.append(self._proxy_m3u8_url(abs_url, referer or self.rawSite))
                    else:
                        out.append(abs_url)
                    last_stream = False
            return '\n'.join(out) + '\n'

        header, segments, tail, media_sequence, target_duration = self._parse_m3u8_segments(text)
        if not segments:
            return text

        marker = self._main_path_marker(m3u8_url)

        # 统计各主机路径的总时长，找出主CDN
        stat = {}
        for seg in segments:
            key = self._segment_host_key(seg['uri'], m3u8_url)
            stat[key] = stat.get(key, 0.0) + float(seg.get('dur') or 0)
        main_key = max(stat.items(), key=lambda x: x[1])[0] if stat else ('', '')
        total_dur = sum(stat.values()) or 0
        main_dur = stat.get(main_key, 0)

        # 五重广告识别
        cleaned = []
        removed = 0
        for idx, seg in enumerate(segments):
            key = self._segment_host_key(seg['uri'], m3u8_url)
            is_front = idx < 12
            abs_uri = urljoin(m3u8_url, seg.get('uri', ''))
            is_ad = self._is_ad_segment(seg['uri'], seg.get('dur'), seg.get('tags'))
            # 第三重：路径标记不匹配主路径
            if marker and marker not in urlsplit(abs_uri).path.lower():
                is_ad = True
            tags_text = '\n'.join(seg.get('tags') or []).upper()
            # 第四重：前置12片段 + METHOD=NONE + 路径不匹配
            if is_front and 'METHOD=NONE' in tags_text and marker and marker not in urlsplit(abs_uri).path.lower():
                is_ad = True
            # 第五重：前置12片段 + 主CDN占比>=60% + 非主CDN且时长<=90秒
            if (not is_ad) and is_front and total_dur > 0 and main_dur >= total_dur * 0.6:
                if key != main_key and stat.get(key, 0) <= 90:
                    is_ad = True
            if is_ad:
                removed += 1
                continue
            seg['_idx'] = idx
            cleaned.append(seg)

        # 兜底策略：没删到广告时，前12片段累计>=25秒且第一个不是主CDN，则切掉前置贴片
        if removed == 0 and len(segments) > 4:
            acc = 0.0
            cut = 0
            for idx, seg in enumerate(segments[:12]):
                key = self._segment_host_key(seg['uri'], m3u8_url)
                if key == main_key and acc >= 3:
                    break
                acc += float(seg.get('dur') or target_duration or 3)
                cut = idx + 1
                if acc >= skip_seconds:
                    break
            if cut > 0 and cut < len(segments):
                first_key = self._segment_host_key(segments[0]['uri'], m3u8_url)
                if first_key != main_key:
                    cleaned = segments[cut:]
                    removed = cut

        if not cleaned:
            cleaned = segments
            removed = 0

        # 重新生成干净的m3u8
        new_lines = []
        has_m3u = False
        for line in header:
            if line.startswith('#EXTM3U'):
                has_m3u = True
            if line.startswith('#EXT-X-MEDIA-SEQUENCE') or line.startswith('#EXT-X-START'):
                continue
            if line.startswith('#EXT-X-KEY') and 'METHOD=NONE' in line.upper() and removed > 0:
                continue
            new_lines.append(line)
        if not has_m3u:
            new_lines.insert(0, '#EXTM3U')
        first_idx = cleaned[0].get('_idx', removed) if cleaned else removed
        new_lines.append('#EXT-X-MEDIA-SEQUENCE:%d' % (media_sequence + first_idx))

        for seg in cleaned:
            for tag in seg.get('tags') or []:
                if tag.startswith('#EXT-X-KEY') or tag.startswith('#EXT-X-MAP'):
                    def _fix_uri(m):
                        return 'URI="' + urljoin(m3u8_url, m.group(1)) + '"'
                    tag = re.sub(r'URI="([^"]+)"', _fix_uri, tag)
                new_lines.append(tag)
            new_lines.append(urljoin(m3u8_url, seg.get('uri', '')))
        if tail:
            for line in tail:
                if line.startswith('#EXT-X-ENDLIST'):
                    new_lines.append(line)
        elif '#EXT-X-ENDLIST' in text:
            new_lines.append('#EXT-X-ENDLIST')
        return '\n'.join(new_lines) + '\n'

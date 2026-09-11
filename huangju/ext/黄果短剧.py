"""黄果剧场 (huangguo.video) Python 点播爬虫（fongmi / OK影视 适配，Chaquopy）

站点结构：
- 列表/分类/搜索：/videos?category=1|2|3|4&q=xx&page=N，卡片 <article class="video-card">
- 最新发布：/videos（不带 category，即网页首页「最新发布」区块内容）
- 视频详情：/video/xxx，播放地址在 data-hls（.../master.m3u8），海报在 data-poster
- 连续剧详情：/series/xxx，剧集列表为“第N集” + /video/xxx 链接
- 播放链路：data-hls 是 master.m3u8（含 480p/720p/1080p 三个 variant，绝对地址在 cdn.huangguo.video，
  整条流 AES-128 加密）。播放器直接吃 master 常因不跟随 variant 而黑屏，故在 playerContent 里
  解析 master、挑一个具体 variant 播放列表返回。CDN 段与 /api/hls_key 均无需 Referer 即可 200。

网络层：优先使用 fongmi 提供的 OkHttp Java 桥（com.github.catvod.net.OkHttp），
这是 Chaquopy 环境下唯一稳定可用的出站 HTTP 方式；仅在本地无 OkHttp 时回退 urllib。
任何一步失败都会把错误放进 msg 返回，而不是静默空白/永久转圈。

配置示例（放进 TVBox 主配置 "sites" 数组，把本文件放到 ./vod/ 目录）：
[
  {
    "key": "huangguo",
    "name": "黄果剧场",
    "type": 3,
    "api": "./vod/huangguo_spider.py",
    "lang": "zh-CN",
    "searchable": 1,
    "quickSearch": 1,
    "filterable": 0,
    "changeable": 0,
    "style": { "type": "rect", "ratio": 0.75 }
  }
]

分类由 homeContent() 动态返回（最新发布/MV音乐剧/短片/连续剧/片段），无需写死 classes。
该站含限制级内容，卡片会把标记透传到 vod_remarks，可自行过滤。
"""

import re
import json
from urllib.parse import quote

try:
    from base.spider import Spider as BaseSpider
except Exception:  # 独立运行（本机校验）时兜底
    BaseSpider = object

BASE = "https://huangguo.video"
PAGE_SIZE = 20
# 第一个栏目 = 最新发布（映射到 /videos 不带 category）
CATEGORIES = [
    {"type_id": "latest", "type_name": "最新发布"},
    {"type_id": "1", "type_name": "MV音乐剧"},
    {"type_id": "2", "type_name": "短片"},
    {"type_id": "3", "type_name": "连续剧"},
    {"type_id": "4", "type_name": "片段"},
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

CARD_RE = re.compile(r'<article class="video-card[\s\S]*?</article>')
TITLE_RE = re.compile(r'<p class="[^"]*font-display[^"]*"[^>]*>([^<]*)</p>')
PIC_RE = re.compile(r'<img[^>]*src="([^"]*)"')
REMARK_RE = re.compile(r'bg-black/55[^>]*>([^<]*)<')
TAG_RE = re.compile(r'text-gold-dim[^>]*>([^<]*)<')
HREF_RE = re.compile(r'<a[^>]+href="([^"]*)"')
H1_RE = re.compile(r'<h1[^>]*>([^<]*)</h1>')
DESC_RE = re.compile(r'<meta name="description" content="([^"]*)"')
OGIMG_RE = re.compile(r'<meta property="og:image" content="([^"]*)"')
POSTER_RE = re.compile(r'data-poster="([^"]*)"')
HLS_RE = re.compile(r'data-hls="([^"]*)"')
TOTAL_RE = re.compile(r'(\d+)\s*集')
PAGER_RE = re.compile(r'href="[^"]*page=(\d+)"[^>]*>\s*(\d+)\s*<')
ANCHOR_RE = re.compile(r'<a[^>]+href="/video/([a-z0-9]+)"[\s\S]*?</a>')
STREAM_RE = re.compile(r'#EXT-X-STREAM-INF[^\n]*')


def _okhttp_get(url, referer=None):
    """优先 fongmi OkHttp 桥；否则回退 urllib（仅本地测试）。返回 HTML 文本。"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json;q=0.9",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    try:
        from com.github.catvod.net import OkHttp
        from java.util import HashMap
        from java.util.concurrent import TimeUnit

        hm = HashMap()
        for k, v in headers.items():
            hm.put(k, v)
        call = OkHttp.newCall(url, hm)
        try:
            call.timeout().timeout(15, TimeUnit.SECONDS)
        except Exception:
            pass
        resp = call.execute()
        try:
            body = resp.body()
            return str(body.string()) if body is not None else ""
        finally:
            try:
                resp.close()
            except Exception:
                pass
    except ImportError:
        import urllib.request

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", "ignore")


def _http_get(url, referer=None):
    """模块内统一同步入口（list / detail 调用）。实际走 _okhttp_get。

    这样即便运行环境没有注入全局 _http_get，也能正常工作，不依赖外部全局符号。
    """
    return _okhttp_get(url, referer=referer)


def _pick_variant(master_url):
    """解析 master.m3u8，挑一个具体 variant 播放列表（绝对地址）返回；失败回退 master。"""
    try:
        txt = _okhttp_get(master_url, referer=BASE + "/")
    except Exception:
        return master_url
    if "#EXT-X-STREAM-INF" not in txt:
        return master_url
    base_dir = master_url.rsplit("/", 1)[0] + "/"
    lines = txt.splitlines()
    variants = []
    for i, line in enumerate(lines):
        if "#EXT-X-STREAM-INF" in line:
            uri = ""
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    uri = lines[j].strip()
                    break
            if not uri:
                continue
            rm = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            res = int(rm.group(2)) if rm else 0
            bw = re.search(r"BANDWIDTH=(\d+)", line)
            bwv = int(bw.group(1)) if bw else 0
            variants.append((res, bwv, uri))
    if not variants:
        return master_url
    variants.sort(key=lambda x: (x[0], x[1]), reverse=True)
    uri = variants[0][2]
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    if uri.startswith("/"):
        return BASE + uri
    return base_dir + uri


class Spider(BaseSpider):
    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        else:
            self.options = {}

    def getName(self):
        return "黄果剧场"

    def homeContent(self, filter):
        result = {"class": CATEGORIES}
        if filter:
            result["filters"] = {}
        return result

    def homeVideoContent(self):
        try:
            return self._list("latest", 1, "")
        except Exception as e:
            return {"list": [], "msg": "首页推荐加载失败：" + type(e).__name__}

    def categoryContent(self, tid, pg, filter, extend):
        del filter, extend
        try:
            return self._list(str(tid), pg, "")
        except Exception as e:
            return {
                "list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE,
                "total": 0, "msg": "分类加载失败：" + type(e).__name__,
            }

    def searchContent(self, key, quick, pg="1"):
        del quick
        try:
            return self._list("2", pg, str(key or ""))
        except Exception as e:
            return {
                "list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE,
                "total": 0, "msg": "搜索失败：" + type(e).__name__,
            }

    def _build_url(self, cat, pg, keyword):
        if cat == "latest":
            url = "%s/videos" % BASE
        else:
            url = "%s/videos?category=%s" % (BASE, quote(cat))
        if keyword:
            sep = "&" if "?" in url else "?"
            url += sep + "q=" + quote(keyword)
        page = max(1, int(pg) if str(pg).isdigit() else 1)
        if page > 1:
            sep = "&" if "?" in url else "?"
            url += sep + "page=%d" % page
        return url

    def _list(self, cat, pg, keyword):
        url = self._build_url(cat, pg, keyword)
        html_text = _http_get(url, referer=BASE + "/")
        cards = [self._parse_card(b) for b in CARD_RE.findall(html_text)]
        cards = [c for c in cards if c]
        return {
            "list": cards,
            "page": max(1, int(pg) if str(pg).isdigit() else 1),
            "pagecount": self._pagecount(html_text),
            "limit": PAGE_SIZE,
            "total": len(cards),
        }

    def _parse_card(self, block):
        href_m = HREF_RE.search(block)
        if not href_m:
            return None
        href = href_m.group(1)
        kind = "series" if href.startswith("/series/") else "video"
        code = href.rstrip("/").split("/")[-1]
        title_m = TITLE_RE.search(block)
        title = title_m.group(1).strip() if title_m else ""
        pic_m = PIC_RE.search(block)
        pic = self._absolute(pic_m.group(1)) if pic_m else ""
        remark_m = REMARK_RE.search(block)
        remark = remark_m.group(1).strip() if remark_m else ""
        tags = TAG_RE.findall(block)[:3]
        return {
            "vod_id": "%s/%s" % (kind, code),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remark or "/".join(tags),
            "vod_class": "/".join(tags),
            "vod_type": "连续剧" if kind == "series" else "视频",
            "style": {"type": "rect", "ratio": 0.75},
        }

    def _pagecount(self, html_text):
        pages = [int(n) for _, n in PAGER_RE.findall(html_text)]
        return max(1, max(pages)) if pages else 1

    def detailContent(self, ids):
        ident = ids[0] if ids else ""
        try:
            item = self._parse_detail(ident)
            if not item.get("vod_play_url"):
                return {"list": [item], "msg": "未能解析到播放地址"}
            return {"list": [item]}
        except Exception as e:
            return {"list": [], "msg": "详情加载失败：" + type(e).__name__}

    def _parse_detail(self, ident):
        parts = str(ident).split("/")
        kind = parts[0]
        code = parts[1] if len(parts) >= 2 else ident
        item = {
            "vod_id": ident,
            "vod_name": "",
            "vod_pic": "",
            "vod_play_from": "黄果剧场",
            "vod_play_url": "",
        }
        if kind == "series":
            text = _http_get("%s/series/%s" % (BASE, code), referer=BASE + "/")
            item["vod_name"] = self._first(H1_RE, text) or ""
            item["vod_pic"] = self._absolute(
                self._first(OGIMG_RE, text) or self._first(POSTER_RE, text)
            )
            item["vod_content"] = self._first(DESC_RE, text) or ""
            total_m = TOTAL_RE.search(text)
            urls = []
            seen = set()
            idx = 0
            for am in ANCHOR_RE.finditer(text):
                ep_code = am.group(1)
                if ep_code in seen:
                    continue
                seen.add(ep_code)
                inner = am.group(0)
                lm = re.search(r'第\s*\d+\s*[集话]|正片|预告片?', inner)
                label = lm.group(0).replace(" ", "") if lm else ("第%d集" % (idx + 1))
                idx += 1
                master = self._resolve_hls(ep_code)
                if master:
                    urls.append("%s$%s" % (label, master))
            if not urls:
                master = self._resolve_hls(code)
                if master:
                    urls.append("正片$%s" % master)
            if total_m:
                item["vod_remark"] = "全%s集" % total_m.group(1)
            item["vod_play_url"] = "#".join(urls)
        else:
            text = _http_get("%s/video/%s" % (BASE, code), referer=BASE + "/")
            item["vod_name"] = self._first(H1_RE, text) or "正片"
            item["vod_pic"] = self._absolute(
                self._first(POSTER_RE, text) or self._first(OGIMG_RE, text)
            )
            item["vod_content"] = self._first(DESC_RE, text) or ""
            master = self._resolve_hls(code)
            item["vod_play_url"] = "正片$%s" % (master or "")
        return item

    def _resolve_hls(self, code):
        """取视频页的 data-hls（master.m3u8）绝对地址；不在此处解析 variant，留给播放时解析。"""
        text = _http_get("%s/video/%s" % (BASE, code), referer=BASE + "/")
        m = HLS_RE.search(text)
        return self._absolute(m.group(1)) if m else ""

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        try:
            cur = str(id or "").split("#")[0]
            sep = cur.rfind("$")
            hls = cur[sep + 1:] if sep >= 0 else cur
            url = self._absolute(hls)
            if not url:
                return {"parse": 0, "jx": 0, "url": "", "msg": "空播放地址"}
            # master -> 具体 variant，避免播放器不跟随 variant 导致黑屏
            playable = _pick_variant(url)
            return {
                "parse": 0,
                "jx": 0,
                "url": playable,
                "header": {"Referer": BASE + "/"},
            }
        except Exception as e:
            return {"parse": 0, "jx": 0, "url": "", "msg": "播放失败：" + type(e).__name__}

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return str(url or "").split("?")[0].lower().endswith(
            (".m3u8", ".mpd", ".mp4", ".mkv", ".flv")
        )

    def destroy(self):
        self.options = {}

    @staticmethod
    def _absolute(url):
        v = str(url or "").strip()
        if not v:
            return ""
        if v.startswith("http://") or v.startswith("https://"):
            return v
        if v.startswith("/"):
            return BASE + v
        return v

    @staticmethod
    def _first(regex, text):
        m = regex.search(text)
        return m.group(1) if m else ""

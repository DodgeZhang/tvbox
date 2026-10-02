# -*- coding: utf-8 -*-
# PeKtino.com - TVBox 爬虫脚本 (全部 + 筛选器)

import sys
import re
import json
import time
import threading
import requests
from urllib.parse import urljoin, quote, unquote
from concurrent.futures import ThreadPoolExecutor

# =====================================================================================
# 真标题口（与 Java 版 ZakaPektinoAmns 同口径）
# -------------------------------------------------------------------------------------
# 站点自己**没有标题数据**（2026-10-03 全站翻过：/api/media 的 anime_title 恒 null、
# 卡片 HTML 只有时长/播放/收藏、详情页 h1 与 og:title 全是随机码、sitemap 的 video:title
# 也是随机码）。所以标题只能顺 tweet_url 去推特原帖正文里取。
# 站点库里很多是被封号/删推的老视频（实测 100 条样本里 50 条原推已被作者删除），
# 这部分任何来源都拿不到标题，走结构化回退（账号 / 日期 / 时长），绝不甩随机码。
# =====================================================================================
TWEET_API = "https://api.fxtwitter.com"
_TWEET_CACHE = {}
_TWEET_LOCK = threading.Lock()
_TWEET_TTL = 21600      # 有正文：6 小时
_TWEET_TTL_EMPTY = 600  # 空结果：10 分钟，回头还能再试


def _tweet_key(url):
    """https://x.com/<user>/status/<id> → (user, id)；抠不到回 (None, None)"""
    if not url:
        return None, None
    p = url.find("/status/")
    if p < 0:
        return None, None
    tail = url[p + 8:]
    m = re.match(r"\d+", tail)
    if not m:
        return None, None
    head = url[:p].rstrip("/")
    return head.rsplit("/", 1)[-1] or None, m.group(0)


def _drop_url(line):
    out = []
    for w in (line or "").split(" "):
        lw = w.lower()
        if lw.startswith(("http://", "https://", "t.co/", "www.")):
            continue
        out.append(w)
    return " ".join(out)


def _title_of_tweet(text):
    """推文正文 → 标题：逐行取、丢纯链接行、攒够 24 字就停，压成一行，超 60 字截断"""
    if not text:
        return ""
    t = re.sub(r"<[^>]*>", " ", text).replace("\u00a0", " ").replace("\r", "\n")
    sb = []
    n = 0
    for line in t.split("\n"):
        l = _drop_url(line).strip()
        if not l:
            continue
        sb.append(l)
        n += len(l)
        if n >= 24:
            break
    s = re.sub(r"\s+", " ", " ".join(sb)).strip()
    if not s:
        return ""
    return s[:60].strip() + "…" if len(s) > 60 else s


def _tweet_text(tweet_url, timeout=6):
    """tweet_url → 推特原帖正文（带缓存，线程安全）。拿不到一律回 ""，绝不抛。"""
    user, tid = _tweet_key(tweet_url)
    if not user or not tid:
        return ""
    ck = user + "/" + tid
    now = time.time()
    with _TWEET_LOCK:
        hit = _TWEET_CACHE.get(ck)
    if hit and now - hit[0] < hit[1]:
        return hit[2]

    text = ""
    try:
        r = requests.get(
            TWEET_API + "/" + user + "/status/" + tid,
            headers={"User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
                     "Accept": "application/json,text/plain,*/*"},
            timeout=timeout)
        if r.status_code == 200:
            j = r.json() or {}
            tw = j.get("tweet") or {}
            text = _title_of_tweet(tw.get("text") or "")
    except Exception:
        text = ""

    ttl = _TWEET_TTL if text else _TWEET_TTL_EMPTY
    with _TWEET_LOCK:
        if len(_TWEET_CACHE) > 4000:
            _TWEET_CACHE.clear()
        _TWEET_CACHE[ck] = (now, ttl, text)
    return text


def _fill_tweet_titles(pairs, workers=16, wait=20):
    """并发把 [{'item':…, 'tweet_url':…}] 里的推特正文换成标题。只改 dict 的 vod_name 字段。"""
    todo = [p for p in pairs if p.get("tweet_url")]
    if not todo:
        return 0
    ok = [0]

    def work(p):
        t = _tweet_text(p["tweet_url"])
        if t and p.get("video") is not None:
            p["video"]["vod_name"] = t
            ok[0] += 1

    try:
        with ThreadPoolExecutor(max_workers=min(workers, len(todo))) as ex:
            futs = [ex.submit(work, p) for p in todo]
            for f in futs:
                try:
                    f.result(timeout=wait)
                except Exception:
                    pass
    except Exception:
        pass
    return ok[0]


def _fallback_title(item, vid):
    """结构化回退：@账号[ · 日期][ · 时长] → 推特视频[ · 日期][ · 时长] → 随机码"""
    at = (item.get("tweet_account") or "").strip() if isinstance(item, dict) else ""
    parts = ["@" + at if at else "推特视频"]
    posted = (item.get("posted_at") or "") if isinstance(item, dict) else ""
    if len(posted) >= 10 and posted[4] == "-" and posted[7] == "-":
        parts.append(posted[5:10])
    sec = item.get("time") if isinstance(item, dict) else 0
    try:
        sec = int(sec or 0)
    except Exception:
        sec = 0
    if sec > 0:
        h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
        parts.append("%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s))
    return " · ".join(parts) if len(parts) > 1 else (parts[0] + " · " + vid if vid else parts[0])


def _clean_alt_title(alt, vid):
    """站点卡片 alt 形如「X(Twitter)エロ動画・アダルト動画 <随机码>」——把套话前缀剥掉，
    剥不出真东西就退回 random code（这只在没有 tweet_url 可查时才用得到）。"""
    if not alt:
        return vid
    t = re.sub(r"^(X\(Twitter\)|Twitter)[^ ]*[ 　]*", "", alt.strip()).strip()
    t = t.replace("の無料動画です。", "").strip()
    if not t or t == alt.strip() and "エロ動画" in alt:
        t = re.sub(r"^.*?(動画|アダルト動画)[ 　]*", "", alt.strip()).strip() or vid
    return t or vid


try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def getName(self): return "Base"
        def homeContent(self, filter): return {"class": []}
        def categoryContent(self, tid, pg, filter, extend): return {"list": []}
        def detailContent(self, ids): return {"list": []}
        def playerContent(self, flag, id, vipFlags=None): return {"parse": 0, "url": ""}
        def searchContent(self, key, quick, pg="1"): return {"list": []}
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False
        def destroy(self): pass
        def localProxy(self, param): return None

class Spider(BaseSpider):
    def init(self, extend=""):
        self.host = "https://pektino.com"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self.lang = "zh-CN"
        self.debug = True

    def _log(self, msg):
        if self.debug:
            print(f"[PeKtino] {msg}")

    def getName(self):
        return "PeKtino"

    def _fix_url(self, url):
        if not url:
            return ""
        if url.startswith("http"):
            return url
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.host + url
        return self.host + "/" + url

    def _fetch(self, url):
        try:
            r = self.session.get(url, timeout=15)
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.text
            return ""
        except Exception as e:
            self._log(f"请求失败: {e}")
            return ""

    # ---- 站点 JSON 口（与 Java 版同一个口），用来补 tweet_url / 账号 / 时长 ----
    def _api(self, path):
        try:
            r = self.session.get(self.host + "/api/" + path.lstrip("/"), timeout=15)
            if r.status_code == 200:
                return r.json()
            return None
        except Exception as e:
            self._log(f"接口失败: {e}")
            return None

    def _api_list(self, rng, pg, sort, cate=""):
        """列表口：range=timely|weekly|monthly|all，sort=favorite|pv|time|created"""
        url = ("media?range=%s&page=%d&per_page=50&category=%s&ids=&isFilteredOnly=0&sort=%s"
               % (rng, pg, quote(cate or ""), sort))
        d = self._api(url)
        if not isinstance(d, dict):
            return {}
        return {it.get("url_cd"): it for it in (d.get("items") or []) if it.get("url_cd")}

    def _retitle(self, videos, cur):
        """★ 标题层：拿站点列表口把这一页的 tweet_url 补齐，再并发换成推特正文。
        cur = {url_cd: item}（接口挂了就是空字典 —— 这时不硬查，直接退到卡片兜底标题，不卡列表）"""
        if not videos:
            return videos
        pairs = []
        for v in videos:
            it = cur.get(v.get("vod_id")) if cur else None
            if it is None and cur:
                # 接口分页和 HTML 分页偶尔错位，零星空缺补一次单查（只在接口本来是通的才补）
                it = self._api_item_by_cd(v.get("vod_id"))
            if it:
                v["vod_name"] = _fallback_title(it, v.get("vod_id") or "")
                pairs.append({"video": v, "tweet_url": (it.get("tweet_url") or "").strip()})
            elif not v.get("vod_name") or v["vod_name"] == v.get("vod_id"):
                v["vod_name"] = "推特视频 · " + str(v.get("vod_id") or "")
        _fill_tweet_titles(pairs)
        return videos

    def _api_item_by_cd(self, cd):
        """url_cd → 带 tweet_url 的条目（详情口不给 tweet_url，用数字 id 回捞一次）"""
        if not cd:
            return None
        d = self._api("media/" + quote(cd))
        if not isinstance(d, dict):
            return None
        if d.get("tweet_url"):
            return d
        mid = d.get("id")
        if not mid:
            return None
        d2 = self._api("media?ids=%s&per_page=1" % mid)
        if isinstance(d2, dict) and (d2.get("items") or []):
            return d2["items"][0]
        return None


    def homeContent(self, filter=False):
        # 只有一个分类：全部
        classes = [{"type_id": "all", "type_name": "全部"}]

        # 筛选器定义：时间 + 排序
        filters = {
            "all": [
                {
                    "key": "time_range",
                    "name": "时间分类",
                    "value": [
                        {"n": "每日", "v": "daily"},
                        {"n": "每周", "v": "weekly"},
                        {"n": "每月", "v": "monthly"},
                        {"n": "所有时间", "v": "all"},
                    ]
                },
                {
                    "key": "sort",
                    "name": "排序方式",
                    "value": [
                        {"n": "按点赞", "v": "favorite"},
                        {"n": "按观看数", "v": "pv"},
                        {"n": "按时长", "v": "time"},
                        {"n": "最近添加", "v": "created"},
                    ]
                }
            ]
        }
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        # 默认使用所有时间 + 按点赞
        return self.categoryContent("all", "1", False, {"time_range": "all", "sort": "favorite"})

    def _extract_videos(self, html):
        videos = []
        if not html:
            return videos

        pattern = r'<div class="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden mb-4">(.*?)</div>\s*<div class="m-2">'
        items = re.findall(pattern, html, re.DOTALL)
        if not items:
            items = re.findall(r'<div class="bg-white[^"]*rounded-lg[^"]*shadow-md[^"]*overflow-hidden mb-4">(.*?)</div>\s*<div class="m-2">', html, re.DOTALL)

        if items:
            for item in items:
                try:
                    link_match = re.search(r'href="(/zh-CN/movie/[^"]+)"', item)
                    if not link_match:
                        continue
                    link = link_match.group(1)

                    img_match = re.search(r'<img[^>]*src="([^"]+)"[^>]*>', item)
                    pic = self._fix_url(img_match.group(1)) if img_match else ""

                    duration_match = re.search(r'<div class="absolute bottom-2 right-2 bg-black/60 text-white text-xs px-2 py-1 rounded-lg">([^<]+)</div>', item)
                    duration = duration_match.group(1).strip() if duration_match else ""

                    views_match = re.search(r'<img src="/icons/eye-black\.svg"[^>]*>([^<]+)</span>', item)
                    views = views_match.group(1).strip() if views_match else ""

                    fav_match = re.search(r'<img src="/icons/heart-black\.svg"[^>]*><span[^>]*>([^<]+)</span>', item)
                    fav = fav_match.group(1).strip() if fav_match else ""

                    vid_match = re.search(r'/movie/([^/]+)', link)
                    vid = vid_match.group(1) if vid_match else link

                    # 卡片 alt 是「X(Twitter)エロ動画・アダルト動画 <随机码>」这种套话，
                    # 直接当标题就是「标题不对」；剥掉套话，真标题由 _retitle 补。
                    title_match = re.search(r'alt="([^"]+)"', item)
                    title = _clean_alt_title(title_match.group(1) if title_match else "", vid)

                    remarks = []
                    if duration:
                        remarks.append(f"⏱{duration}")
                    if views:
                        remarks.append(f"👁{views}")
                    if fav:
                        remarks.append(f"❤{fav}")

                    videos.append({
                        "vod_id": vid,
                        "vod_name": title,
                        "vod_pic": pic,
                        "vod_remarks": " | ".join(remarks),
                    })
                except:
                    continue

        if not videos:
            next_data = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if next_data:
                try:
                    data = json.loads(next_data.group(1))
                    def find_items(obj):
                        if isinstance(obj, dict):
                            if "props" in obj and "pageProps" in obj["props"]:
                                page_props = obj["props"]["pageProps"]
                                if "initialItems" in page_props:
                                    return page_props["initialItems"]
                            for value in obj.values():
                                result = find_items(value)
                                if result:
                                    return result
                        elif isinstance(obj, list):
                            for item in obj:
                                result = find_items(item)
                                if result:
                                    return result
                        return None
                    items = find_items(data)
                    if items:
                        for item in items:
                            vid = item.get("url_cd", "")
                            if vid:
                                title = item.get("anime_title") or vid
                                pic = item.get("thumbnail", "")
                                pic = self._fix_url(pic)
                                duration = ""
                                if "time" in item:
                                    m = item["time"] // 60
                                    s = item["time"] % 60
                                    duration = f"{m:02d}:{s:02d}"
                                views = item.get("pv", "")
                                fav = item.get("favorite", "")
                                remarks = []
                                if duration:
                                    remarks.append(f"⏱{duration}")
                                if views:
                                    remarks.append(f"👁{views}")
                                if fav:
                                    remarks.append(f"❤{fav}")
                                videos.append({
                                    "vod_id": vid,
                                    "vod_name": title,
                                    "vod_pic": pic,
                                    "vod_remarks": " | ".join(remarks),
                                })
                except Exception as e:
                    self._log(f"解析 __NEXT_DATA__ 失败: {e}")

        return videos

    def _get_pagecount(self, html):
        page_links = re.findall(r'<a[^>]*href="[^"]*page=(\d+)"[^>]*>', html)
        if page_links:
            return max(int(p) for p in page_links)
        last_match = re.search(r'href="[^"]*page=(\d+)"[^>]*>最后', html)
        if last_match:
            return int(last_match.group(1))
        return 1

    def categoryContent(self, tid, pg, filter=False, extend=None):
        pg = int(pg) if pg else 1
        extend = extend or {}

        # 从筛选器获取参数
        time_range = extend.get("time_range", "all")
        sort = extend.get("sort", "favorite")

        # 构造基础 URL（根据时间范围）
        if time_range == "daily":
            url = f"{self.host}/{self.lang}/"
        elif time_range == "weekly":
            url = f"{self.host}/{self.lang}/weekly"
        elif time_range == "monthly":
            url = f"{self.host}/{self.lang}/monthly"
        else:  # all
            url = f"{self.host}/{self.lang}/all"

        # 添加排序和分页
        params = []
        if sort:
            params.append(f"sort={sort}")
        if pg > 1:
            params.append(f"page={pg}")
        if params:
            url += "?" + "&".join(params)

        self._log(f"分类请求: {url}")
        html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        videos = self._extract_videos(html)
        pagecount = self._get_pagecount(html)

        # ★ 标题层：这一页的 tweet_url 从站点 JSON 口补齐 → 换推特正文（与 Java 版同口径）
        rng = {"daily": "timely", "weekly": "weekly", "monthly": "monthly"}.get(time_range, "all")
        self._retitle(videos, self._api_list(rng, pg, sort or "favorite"))

        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount if pagecount >= pg else pg,
            "limit": 20,
            "total": pagecount * 20
        }

    def detailContent(self, ids):
        vid = ids[0] if ids else ""
        if not vid:
            return {"list": []}

        if vid.startswith("http"):
            url = vid
        else:
            if not vid.startswith("/"):
                url = f"{self.host}/{self.lang}/movie/{vid}"
            else:
                url = self._fix_url(vid)

        html = self._fetch(url)
        if not html:
            return {"list": []}

        # ★ 标题：站点页面上的 h1 / og:title 全是随机码（「xxxの無料動画です。」），照抓就是不对。
        #   真标题只能从这条存着的 tweet_url 反查推特原帖正文（与 Java 版 detailContent 同口径）。
        title = ""
        it = self._api_item_by_cd(vid)
        if it:
            title = _tweet_text((it.get("tweet_url") or "").strip()) or _fallback_title(it, vid)
        if not title:
            title_match = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html)
            if title_match:
                title = _clean_alt_title(title_match.group(1), vid)
        if not title:
            title = vid

        pic = ""
        pic_match = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', html)
        if pic_match:
            pic = pic_match.group(1)
        if not pic:
            pic_match = re.search(r'<img[^>]*src="([^"]+)"[^>]*class="[^"]*object-cover[^"]*"', html)
            if pic_match:
                pic = pic_match.group(1)
        pic = self._fix_url(pic)

        play_url = ""
        next_data = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        if next_data:
            try:
                data = json.loads(next_data.group(1))
                def find_video_url(obj):
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            if key == 'url' and isinstance(value, str) and 'video.twimg.com' in value:
                                return value
                            result = find_video_url(value)
                            if result:
                                return result
                    elif isinstance(obj, list):
                        for item in obj:
                            result = find_video_url(item)
                            if result:
                                return result
                    return None
                play_url = find_video_url(data)
                if play_url:
                    self._log(f"从__NEXT_DATA__提取到视频: {play_url}")
            except Exception as e:
                pass

        if not play_url:
            mp4_match = re.search(r'(https://video\.twimg\.com/[^\s"\']+\.mp4[^\s"\']*)', html)
            if mp4_match:
                play_url = mp4_match.group(1)

        if not play_url:
            video_match = re.search(r'<video[^>]*src="([^"]+)"', html)
            if video_match:
                play_url = video_match.group(1)

        if play_url:
            play_url = f"播放${play_url}"
        else:
            play_url = f"网页播放${url}"

        return {
            "list": [{
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_content": "",
                "vod_play_from": "PeKtino",
                "vod_play_url": play_url,
            }]
        }

    def playerContent(self, flag, id, vipFlags=None):
        if not id:
            return {"parse": 0, "url": "", "header": {}}

        if id.startswith(("http://", "https://")):
            if ".mp4" in id or ".m3u8" in id:
                headers = {
                    "User-Agent": self.session.headers.get("User-Agent"),
                    "Accept": "video/mp4,video/webm,video/*;q=0.8,*/*;q=0.5",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Connection": "keep-alive",
                }
                if "video.twimg.com" in id:
                    headers["Referer"] = "https://x.com/"
                    headers["Origin"] = "https://x.com"
                else:
                    headers["Referer"] = self.host + "/"
                    headers["Origin"] = self.host
                return {"parse": 0, "url": id, "header": headers}
            html = self._fetch(id)
            if html:
                mp4_match = re.search(r'(https://video\.twimg\.com/[^\s"\']+\.mp4[^\s"\']*)', html)
                if mp4_match:
                    return {
                        "parse": 0,
                        "url": mp4_match.group(1),
                        "header": {
                            "User-Agent": self.session.headers.get("User-Agent"),
                            "Referer": "https://x.com/",
                            "Origin": "https://x.com",
                            "Accept": "video/mp4,video/webm,video/*;q=0.8,*/*;q=0.5",
                        }
                    }
            return {"parse": 1, "url": id, "header": {"Referer": self.host + "/"}}

        url = self._fix_url(id)
        if not url:
            return {"parse": 0, "url": "", "header": {}}

        return {
            "parse": 0,
            "url": url,
            "header": {
                "User-Agent": self.session.headers.get("User-Agent"),
                "Referer": self.host + "/",
                "Origin": self.host,
            }
        }

    def _tags(self):
        """站点标签全表（50 条，带 20 种语言名），进程内缓存一次"""
        if getattr(self, "_tag_cache", None):
            return self._tag_cache
        d = self._api("tags")
        self._tag_cache = d if isinstance(d, list) else []
        return self._tag_cache

    def _tag_code(self, key):
        """关键词 → 站点 tag code。站点搜索本质就是标签搜索（与 Java 版同口径）。
        多语言名 + code 全表匹配：精确优先，再退到包含。"""
        k = (key or "").strip().lower()
        if not k:
            return ""
        fields = ["name", "code", "name_en", "name_zh_cn", "name_zh_tw", "name_ko",
                  "name_ja", "name_th", "name_id", "name_ru", "name_de", "name_fr"]
        best = ""
        for t in self._tags():
            for f in fields:
                v = str(t.get(f) or "").strip().lower()
                if not v:
                    continue
                if v == k or v == k.replace(" ", ""):
                    return t.get("code") or ""
                if k in v and not best:
                    best = t.get("code") or ""
        return best

    def _videos_from_items(self, items, cur=None):
        out = []
        for it in (items or []):
            vid = it.get("url_cd") or ""
            if not vid:
                continue
            sec = it.get("time") or 0
            try:
                sec = int(sec)
            except Exception:
                sec = 0
            remarks = []
            if sec > 0:
                h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
                remarks.append("⏱" + ("%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)))
            if it.get("pv"):
                remarks.append("👁" + str(it.get("pv")))
            fav = str(it.get("favorite") or "")
            if fav and fav != "0":
                remarks.append("❤" + fav)
            out.append({
                "vod_id": vid,
                "vod_name": (str(it.get("anime_title") or "").strip() or _fallback_title(it, vid)),
                "vod_pic": self._fix_url(it.get("thumbnail") or ""),
                "vod_remarks": " | ".join(remarks),
            })
        return out

    def searchContent(self, key, quick=False, pg="1"):
        """站点搜索 = 标签搜索：关键词 → tag code → /api/media?category=<code>。
        关键词解析不出 code 时才退到原来的 HTML 搜索页。"""
        pg = int(pg) if pg else 1
        code = self._tag_code(key)

        if code:
            d = self._api("media?range=all&page=%d&per_page=50&category=%s&ids=&isFilteredOnly=0&sort=favorite"
                          % (pg, quote(code)))
            items = (d or {}).get("items") or [] if isinstance(d, dict) else []
            videos = self._videos_from_items(items)
            self._retitle(videos, {it.get("url_cd"): it for it in items if it.get("url_cd")})
            lp = (d or {}).get("lastPage") or 0 if isinstance(d, dict) else 0
            return {
                "list": videos,
                "page": pg,
                "pagecount": lp if lp >= pg else pg,
                "limit": 50,
                "total": (d or {}).get("total") or len(videos) if isinstance(d, dict) else len(videos),
            }

        # 解析不出 code（站点上也是空结果，个别新标签除外）→ 退 HTML 搜索页
        enc_key = quote(key)
        url = f"{self.host}/{self.lang}/search?q={enc_key}&page={pg}"
        html = self._fetch(url)
        if not html:
            url = f"{self.host}/{self.lang}/category/{enc_key}?page={pg}"
            html = self._fetch(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        videos = self._extract_videos(html)
        pagecount = self._get_pagecount(html)
        self._retitle(videos, {})

        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount if pagecount >= pg else pg,
            "limit": 20,
            "total": pagecount * 20
        }

    def isVideoFormat(self, url):
        if not url:
            return False
        return any(ext in url.lower() for ext in ['.mp4', '.m3u8', '.ts'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        if self.session:
            self.session.close()

    def localProxy(self, param):
        return None
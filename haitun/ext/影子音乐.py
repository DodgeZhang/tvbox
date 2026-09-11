import re
import sys
import json
import time
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from requests import Session, adapters
from urllib3.util.retry import Retry
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.host = "https://music.yingzi.ee"
        self.session = Session()
        adapter = adapters.HTTPAdapter(
            max_retries=Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504]),
            pool_connections=30, pool_maxsize=50
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": self.host + "/"
        }
        self.session.headers.update(self.headers)
        self.netease_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://music.163.com/"
        }
        self._cache = {}
        self._cache_ttl = 300

        # 一级分类 + 二级榜单
        self.platforms = {
            "netease": {
                "name": "网易云音乐",
                "playlists": {
                    "3778678": "热歌榜",
                    "19723756": "飙升榜",
                    "3779629": "新歌榜",
                    "2884035": "原创榜"
                }
            },
            "tencent": {
                "name": "QQ音乐",
                "playlists": {
                    "热歌": "热歌榜",
                    "新歌": "新歌榜",
                    "飙升": "飙升榜",
                    "流行": "流行榜"
                }
            },
            "kugou": {
                "name": "酷狗音乐",
                "playlists": {
                    "热歌": "热歌榜",
                    "新歌": "新歌榜",
                    "飙升": "飙升榜",
                    "DJ": "DJ榜"
                }
            }
        }

    def getName(self): return "影子音乐"
    def isVideoFormat(self, url): return bool(re.search(r'\.(mp3|m4a|flac|wav|ogg)(\?|$)', url or "", re.I))
    def manualVideoCheck(self): return False
    def destroy(self): self.session.close()

    # ==================== 首页 ====================
    def homeContent(self, filter):
        classes = []
        filters = {}
        for source, cfg in self.platforms.items():
            classes.append({"type_name": cfg["name"], "type_id": source})
            fvals = [{"n": v, "v": k} for k, v in cfg["playlists"].items()]
            if fvals:
                filters[source] = [{"key": "list", "name": "榜单", "value": fvals}]
        return {"class": classes, "filters": filters, "list": []}

    def homeVideoContent(self): return {"list": []}

    # ==================== 分类页：直接返回歌曲列表 ====================
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        source = tid
        # 默认榜单
        list_id = extend.get("list", "")
        if not list_id and source in self.platforms:
            list_id = next(iter(self.platforms[source]["playlists"].keys()))
        list_name = self.platforms.get(source, {}).get("playlists", {}).get(list_id, "精选")

        songs = []
        if source == "netease" and list_id.isdigit():
            songs = self._get_netease_playlist(list_id)
        elif source in ("tencent", "kugou"):
            # QQ/酷狗用搜索模拟榜单
            songs = self._do_search(source, list_id, pg)

        if not songs:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 100, "total": 0}

        items = []
        for song in songs[:200]:
            if source == "netease":
                sid = str(song.get("id", ""))
                name = song.get("name", "未知")
                artists = ", ".join([a.get("name", "") for a in song.get("ar", [])])
                pic = song.get("al", {}).get("picUrl", "")
                # 网易云歌单内歌曲无sign，detail时按需搜索获取
                vod_id = self.e64(f"{source}###{sid}###{name}###{pic}")
            else:
                sid = song.get("id", "")
                name = song.get("name", "未知")
                artists = ", ".join(song.get("artist", []))
                pic = self._get_pic(source, song)
                sign = song.get("sign", "")
                vod_id = self.e64(f"{source}###{sid}###{sign}###{name}###{pic}")

            display_name = f"{name} - {artists}" if artists else name
            items.append({
                "vod_id": vod_id,
                "vod_name": display_name,
                "vod_pic": pic or "",
                "style": {"type": "rect", "ratio": 1}
            })

        # 网易云歌单不分页；QQ/酷狗搜索可翻页
        pagecount = 999 if source in ("tencent", "kugou") else 1
        return {
            "list": items,
            "page": pg,
            "pagecount": pagecount,
            "limit": 100,
            "total": len(items)
        }

    # ==================== 详情页：单曲直接 playable ====================
    def detailContent(self, ids):
        raw = self.d64(ids[0])
        parts = raw.split("###")

        # 格式: source###sid###sign###name###pic  (QQ/酷狗有sign)
        # 格式: source###sid###name###pic        (网易云无sign)
        if len(parts) == 5:
            source, sid, sign, name, pic = parts
        elif len(parts) == 4:
            source, sid, name, pic = parts
            sign = self._get_sign(source, sid, name)
        else:
            return {"list": []}

        play_id = self.e64(f"{source}###{sid}###{sign}")
        vod = {
            "vod_id": ids[0],
            "vod_name": name,
            "vod_pic": pic,
            "vod_play_from": source,
            "vod_play_url": f"播放${play_id}"
        }
        return {"list": [vod]}

    # ==================== 搜索：三平台并发 ====================
    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        all_songs = []

        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {ex.submit(self._do_search, s, key, pg): s for s in self.platforms.keys()}
            for f in as_completed(futures):
                try:
                    all_songs.extend(f.result())
                except:
                    pass

        seen = set()
        unique = []
        for s in all_songs:
            k = f"{s.get('source')}:{s.get('id')}"
            if k not in seen:
                seen.add(k)
                unique.append(s)

        res = []
        for s in unique:
            source = s.get("source", "")
            sid = s.get("id", "")
            name = s.get("name", "未知")
            artists = ", ".join(s.get("artist", []))
            pic = self._get_pic(source, s)
            sign = s.get("sign", "")
            vod_id = self.e64(f"{source}###{sid}###{sign}###{name}###{pic}")
            res.append({
                "vod_id": vod_id,
                "vod_name": f"{name} - {artists}" if artists else name,
                "vod_pic": pic,
                "style": {"type": "rect", "ratio": 1}
            })

        return {"list": res, "page": pg}

    # ==================== 播放器 ====================
    def playerContent(self, flag, id, vipFlags):
        raw = self.d64(id)
        parts = raw.split("###")

        if len(parts) == 3:
            source, sid, sign = parts
        else:
            return {"parse": 0, "url": "", "header": self.headers}

        url = self._get_play_url(source, sid, sign)
        if not url:
            return {"parse": 0, "url": "", "header": self.headers}

        result = {
            "parse": 0,
            "url": url,
            "header": self.headers.copy()
        }
        if "qq.com" in url:
            result["header"]["Referer"] = "https://y.qq.com/"
        elif "kugou" in url:
            result["header"]["Referer"] = "https://www.kugou.com/"

        # 网易云歌词
        if source == "netease":
            lrc = self._get_netease_lyric(sid)
            if lrc:
                result["lrc"] = lrc

        return result

    # ==================== 本地代理 ====================
    def localProxy(self, param):
        url = param.get("url", "")
        if not url:
            return None
        try:
            h = self.headers.copy()
            if "music.126.net" in url:
                h.update(self.netease_headers)
            elif "y.gtimg.cn" in url:
                h["Referer"] = "https://y.qq.com/"
            elif "kugou" in url:
                h["Referer"] = "https://www.kugou.com/"

            r = self.session.get(url, headers=h, timeout=10)
            ct = r.headers.get("Content-Type", "image/jpeg")
            if "image" not in ct:
                ct = "image/jpeg"
            return [200, ct, r.content, {}]
        except:
            return None

    # ==================== 内部工具 ====================
    def _get_netease_playlist(self, list_id):
        ck = f"pl_netease_{list_id}"
        if ck in self._cache and time.time() - self._cache[ck]["time"] < self._cache_ttl:
            return self._cache[ck]["data"]
        try:
            r = self.session.get(f"{self.host}/api.php?types=playlist&id={list_id}&source=netease", timeout=10)
            tracks = r.json().get("playlist", {}).get("tracks", [])
            self._cache[ck] = {"data": tracks, "time": time.time()}
            return tracks
        except:
            return []

    def _do_search(self, source, keyword, pg):
        ck = f"search_{source}_{keyword}_{pg}"
        if ck in self._cache and time.time() - self._cache[ck]["time"] < self._cache_ttl:
            return self._cache[ck]["data"]
        try:
            r = self.session.get(
                f"{self.host}/api.php?types=search&source={source}&count=30&pages={pg}&name={quote(keyword)}",
                timeout=10
            )
            data = r.json()
            if isinstance(data, list):
                for item in data:
                    item["source"] = source
                self._cache[ck] = {"data": data, "time": time.time()}
                return data
        except:
            pass
        return []

    def _get_sign(self, source, sid, name):
        ck = f"sign_{source}_{sid}"
        if ck in self._cache and time.time() - self._cache[ck]["time"] < self._cache_ttl:
            return self._cache[ck]["data"]
        try:
            r = self.session.get(
                f"{self.host}/api.php?types=search&source={source}&count=10&pages=1&name={quote(name or 'a')}",
                timeout=10
            )
            for song in r.json():
                if str(song.get("id")) == str(sid):
                    sign = song.get("sign", "")
                    self._cache[ck] = {"data": sign, "time": time.time()}
                    return sign
        except:
            pass
        return ""

    def _get_play_url(self, source, sid, sign):
        if not sign:
            return ""
        try:
            r = self.session.get(f"{self.host}/api.php?types=url&id={sid}&source={source}&sign={sign}", timeout=10)
            url = r.json().get("url", "")
            return url.replace("\/", "/") if url else ""
        except:
            return ""

    def _get_netease_lyric(self, sid):
        try:
            r = self.session.get(
                f"https://music.163.com/api/song/lyric?id={sid}&lv=1&kv=1&tv=-1",
                headers=self.netease_headers, timeout=10
            )
            return r.json().get("lrc", {}).get("lyric", "")
        except:
            return ""

    def _get_pic(self, source, song):
        pic_id = song.get("pic_id", "")
        if source == "tencent":
            return f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{pic_id}.jpg"
        if source == "kugou" and len(pic_id) >= 4:
            return f"https://singerimg.kugou.com/uploadpic/softhead/400/{pic_id[:2]}/{pic_id[:4]}/{pic_id}.jpg"
        return ""

    def e64(self, text):
        return base64.b64encode(text.encode("utf-8")).decode("utf-8")

    def d64(self, text):
        return base64.b64decode(text.encode("utf-8")).decode("utf-8")

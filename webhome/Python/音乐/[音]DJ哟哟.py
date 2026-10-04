from base.spider import Spider
import requests
import re
import html
from urllib.parse import quote

class Spider(Spider):
    def getName(self):
        return "DJ呦呦"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def _get_headers(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.djuu.com/'
        }

    def _fetch(self, url, timeout=10):
        try:
            r = requests.get(url, headers=self._get_headers(), timeout=timeout)
            r.encoding = 'utf-8'
            return r.text
        except Exception:
            return ""

    def homeContent(self, filter):
        result = {}
        cateId = [
            {"type_name": "独家舞曲", "type_id": "exclusive_115"},
            {"type_name": "迪高串烧", "type_id": "djlist_1"},
            {"type_name": "慢摇串烧", "type_id": "djlist_2"},
            {"type_name": "慢歌串烧", "type_id": "djlist_3"},
            {"type_name": "中文Remix", "type_id": "djlist_4"},
            {"type_name": "外文Remix", "type_id": "djlist_5"},
            {"type_name": "HOUSE", "type_id": "djlist_6"},
            {"type_name": "霓虹风格", "type_id": "djlist_7"},
            {"type_name": "Mashup", "type_id": "djlist_8"},
            {"type_name": "中文DISCO", "type_id": "djlist_9"},
            {"type_name": "外文DISCO", "type_id": "djlist_10"},
        ]
        result['class'] = cateId
        return result

    def homeVideoContent(self):
        return self.categoryContent("djlist_2", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        parts = tid.split('_')
        list_type = parts[0]
        cat_id = parts[1] if len(parts) > 1 else '0'
        page = max(1, int(pg))

        url = f"https://www.djuu.com/{list_type}/{cat_id}_{page}.html"
        html_text = self._fetch(url)
        videos = self._parse_list(html_text)

        result['list'] = videos
        result['page'] = page
        result['pagecount'] = 9999
        result['limit'] = 30
        result['total'] = 999999
        return result

    def _parse_list(self, html_text):
        videos = []
        if not html_text:
            return videos

        rows = re.findall(r'<tr[^>]*class="(?:sbg|dbg)"[^>]*>(.*?)</tr>', html_text, re.DOTALL | re.IGNORECASE)
        for row in rows:
            id_match = re.search(r'<input[^>]*class="sortid"[^>]*value="(\d+)"', row, re.IGNORECASE)
            if not id_match:
                continue
            value_id = id_match.group(1)

            link_match = re.search(
                r'<li class="list_play_img"><a href="/play/(\d+)\.html"[^>]*title="([^"]*)"[^>]*>'
                r'<img src="([^"]+)"></a></li>',
                row, re.IGNORECASE
            )
            if not link_match:
                continue
            play_id, title, pic = link_match.groups()
            title = html.unescape(title).strip()

            time_info = ''
            size_info = ''
            bitrate = ''
            tm = re.search(r'TIME\s*([^<\s][^<]{0,30})', row, re.IGNORECASE)
            if tm:
                time_info = 'TIME ' + tm.group(1).strip()
            sm = re.search(r'SIZE\s*([^<\s][^<]{0,30})', row, re.IGNORECASE)
            if sm:
                size_info = 'SIZE ' + sm.group(1).strip()
            bm = re.search(r'(\d+\s*KBPS)', row, re.IGNORECASE)
            if bm:
                bitrate = bm.group(1).strip()

            hot = ''
            uptime = ''
            cor999 = re.findall(r'<td[^>]*class="cor999"[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
            if len(cor999) >= 1:
                hot = re.sub(r'<[^>]+>', '', cor999[0]).strip()
            if len(cor999) >= 2:
                uptime = re.sub(r'<[^>]+>', '', cor999[1]).strip()

            remark = f"{time_info} | {size_info} | {bitrate} | {hot} | {uptime}"
            videos.append({
                "vod_id": str(play_id),
                "vod_name": title,
                "vod_pic": pic.strip(),
                "vod_remarks": remark
            })

        return videos

    def detailContent(self, ids):
        rid = ids[0]
        result = {}
        url = f"https://www.djuu.com/play/{rid}.html"
        html_text = self._fetch(url)

        if not html_text:
            result['list'] = [self._empty_vod(rid, "详情页加载失败")]
            return result

        music_match = re.search(
            r"var music = \{id:\s*(\d+),\s*type:\s*'([^']+)',\s*name:\s*'([^']+)',\s*file:\s*'([^']+)'",
            html_text
        )
        if not music_match:
            result['list'] = [self._empty_vod(rid, "未解析到音乐信息")]
            return result

        music_id, music_type, music_name, music_file = music_match.groups()
        audio_url = f"https://mp4.djuu.com/{music_file}.m4a"

        cover_match = re.search(
            r"<img[^>]*id=[\"']mcover[\"'][^>]*src=[\"']([^\"']+)[\"']",
            html_text, re.IGNORECASE
        )
        pic = cover_match.group(1).strip() if cover_match else ""

        info_match = re.search(
            r"编号：(\d+).*?分类：([^<]+).*?U 币：([^<]+).*?音质：([^<]+).*?大小：([^<]+).*?时间：([^<]+)",
            html_text, re.DOTALL | re.IGNORECASE
        )
        if info_match:
            no, cate, ub, quality, size, uptime = info_match.groups()
            content = f"编号：{no.strip()}\n分类：{cate.strip()}\n音质：{quality.strip()}\n大小：{size.strip()}\n上传时间：{uptime.strip()}"
        else:
            content = ""

        play_url = f"{music_name}${rid}"

        vod = {
            "vod_id": rid,
            "vod_name": music_name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_remarks": "DJ呦呦音乐",
            "vod_actor": "",
            "vod_play_from": "DJUU",
            "vod_play_url": play_url
        }
        result['list'] = [vod]

        self._audio_cache = audio_url
        return result

    def playerContent(self, flag, id, vipFlags):
        result = {}
        rid = id

        detail = self.detailContent([rid])
        audio_url = getattr(self, '_audio_cache', '')

        if not audio_url:
            result["parse"] = 0
            result["playUrl"] = ""
            result["url"] = ""
            result["header"] = {}
            return result

        result["parse"] = 0
        result["playUrl"] = ""
        result["url"] = audio_url
        result["header"] = self._get_headers()
        return result

    def searchContent(self, key, quick, pg=1):
        result = {}
        page = max(1, int(pg))
        wd = quote(key)
        url = f"https://www.djuu.com/search?musicname={wd}&cid=0&list=2&page={page}"
        html_text = self._fetch(url)
        videos = self._parse_list(html_text)

        result['list'] = videos
        result['page'] = page
        result['pagecount'] = 9999
        result['limit'] = 30
        result['total'] = 999999
        return result

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    def localProxy(self, param):
        return None

    def _empty_vod(self, rid, msg):
        return {
            "vod_id": rid,
            "vod_name": "加载失败",
            "vod_content": msg,
            "vod_remarks": "加载失败",
            "vod_actor": "",
            "vod_play_from": "DJUU",
            "vod_play_url": ""
        }

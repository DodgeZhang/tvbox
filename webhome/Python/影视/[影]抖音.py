# -*- coding: utf-8 -*-
import re
import sys
import json
import time
import random
import string

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def init(self, extend=""):
        self.extend = extend
        self.cookie_cache = ""

    def getName(self):
        return "抖音直播"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def localProxy(self, param):
        return None

    host = "https://live.douyin.com"
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    classes_config = [
        {"type_id": "10000$3", "type_name": "娱乐天地"},
        {"type_id": "10001$3", "type_name": "科技文化"},
        {"type_id": "102$4", "type_name": "音乐"},
        {"type_id": "103$4", "type_name": "游戏"},
        {"type_id": "105$4", "type_name": "舞蹈"},
        {"type_id": "101$4", "type_name": "聊天"},
        {"type_id": "108$4", "type_name": "运动"},
        {"type_id": "107$4", "type_name": "生活"},
        {"type_id": "106$4", "type_name": "文化"},
        {"type_id": "104$4", "type_name": "二次元"},
    ]

    # ==================== 工具函数 ====================
    def _generate_device_id(self):
        timestamp = self._base36_encode(int(time.time() * 1000))
        random_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=13))
        return f"{timestamp}{random_part}"

    @staticmethod
    def _base36_encode(num):
        alphabet = '0123456789abcdefghijklmnopqrstuvwxyz'
        if num == 0:
            return '0'
        res = []
        while num > 0:
            num, rem = divmod(num, 36)
            res.append(alphabet[rem])
        return ''.join(reversed(res))

    def _get_cookie(self):
        if self.cookie_cache:
            return self.cookie_cache
        try:
            resp = self.fetch(self.host, headers=self.headers, verify=False)
            cookies = resp.headers.get('set-cookie', '')
            if cookies:
                match = re.search(r'ttwid=([^;]+)', cookies)
                if match:
                    self.cookie_cache = f"ttwid={match.group(1)}"
        except Exception:
            pass
        return self.cookie_cache

    def _get_headers(self):
        cookie = self._get_cookie()
        hd = self.headers.copy()
        hd["Referer"] = self.host
        if cookie:
            hd["Cookie"] = cookie
        return hd

    def _first_non_empty(self, *values):
        for v in values:
            if v is not None and v != '':
                return v
        return None

    def _parse_raw_live_data(self, item):
        if not isinstance(item, dict):
            return None
        candidates = [
            item.get('lives', {}).get('rawdata'),
            item.get('lives', {}).get('raw_data'),
            item.get('live', {}).get('rawdata'),
            item.get('live_info', {}).get('rawdata'),
            item.get('aweme_info', {}).get('live_info', {}).get('rawdata'),
            item.get('data', {}).get('rawdata'),
            item.get('rawdata'),
            item.get('lives'),
            item.get('live'),
            item.get('live_info'),
            item.get('aweme_info', {}).get('live_info'),
            item.get('aweme_info'),
            item.get('data'),
            item
        ]
        for c in candidates:
            if isinstance(c, str):
                try:
                    parsed = json.loads(c)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    continue
            elif isinstance(c, dict):
                return c
        return None

    def _normalize_search_item(self, raw, fallback=None):
        if not isinstance(raw, dict):
            return None
        fallback = fallback or {}

        room_id = self._first_non_empty(
            raw.get('id_str'),
            raw.get('room_id_str'),
            raw.get('room', {}).get('id_str'),
            raw.get('room', {}).get('id'),
            raw.get('room_id'),
            raw.get('roomId')
        )
        if not room_id:
            return None

        web_rid = self._first_non_empty(
            raw.get('owner', {}).get('web_rid'),
            raw.get('web_rid'),
            raw.get('room', {}).get('owner', {}).get('web_rid')
        ) or self._generate_device_id()

        nickname = self._first_non_empty(
            raw.get('owner', {}).get('nickname'),
            raw.get('nickname'),
            raw.get('room', {}).get('owner', {}).get('nickname'),
            fallback.get('nickname')
        ) or '抖音直播'

        title = self._first_non_empty(
            raw.get('title'),
            raw.get('room', {}).get('title'),
            fallback.get('title'),
            nickname
        )

        pic = self._first_non_empty(
            raw.get('owner', {}).get('avatar_large', {}).get('url_list', [None])[0],
            raw.get('room', {}).get('cover', {}).get('url_list', [None])[0],
            raw.get('cover', {}).get('url_list', [None])[0],
            raw.get('cover_url')
        ) or ''

        online_text = self._first_non_empty(
            raw.get('room', {}).get('stats', {}).get('user_count_str'),
            raw.get('user_count_str'),
            raw.get('room', {}).get('user_count_str'),
            raw.get('user_count')
        )
        tag_text = self._first_non_empty(
            raw.get('video_feed_tag'),
            raw.get('room', {}).get('partition_road_map', [{}])[0].get('title'),
            raw.get('partition', {}).get('title'),
            fallback.get('tag')
        )
        remark = ' '.join(filter(None, [tag_text, online_text]))

        return {
            "vod_id": f"{web_rid}@@{room_id}",
            "vod_name": nickname,
            "vod_pic": pic,
            "vod_remarks": remark,
            "vod_content": title
        }

    def _extract_search_videos(self, payload):
        if not isinstance(payload, list):
            return []
        results = []
        seen = set()
        for item in payload:
            raw = self._parse_raw_live_data(item)
            norm = self._normalize_search_item(raw, {
                "nickname": item.get('nickname'),
                "title": item.get('title') or item.get('desc'),
                "tag": item.get('search_keyword')
            })
            if not norm:
                continue
            if norm['vod_id'] in seen:
                continue
            seen.add(norm['vod_id'])
            results.append(norm)
        return results

    # ==================== 框架标准方法 ====================
    def homeContent(self, filter):
        classes = self.classes_config
        return {
            "class": classes,
            "list": []
        }

    def homeVideoContent(self):
        return {}

    def categoryContent(self, tid, pg, filter, extend):
        category_id = str(tid)
        page = int(pg or 1)
        offset = 15 * (page - 1)
        parts = category_id.split('$')
        if len(parts) < 2:
            return {"list": [], "page": page, "pagecount": 0, "limit": 15, "total": 9999}
        partition, ptype = parts[0], parts[1]

        params = {
            "aid": "6383",
            "app_name": "douyin_web",
            "live_id": "1",
            "device_platform": "web",
            "language": "zh-CN",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "120.0.0.0",
            "partition": partition,
            "partition_type": ptype,
            "count": "15",
            "offset": str(offset),
            "web_rid": self._generate_device_id(),
            "cookie_enabled": "true",
            "screen_width": "1920",
            "screen_height": "1080"
        }

        headers = self._get_headers()
        urls = [
            "https://live.douyin.com/webcast/web/partition/detail/room/v2/",
            "https://webcast.amemv.com/webcast/web/partition/detail/room/v2/",
        ]
        list_ = []
        for url in urls:
            try:
                resp = self.fetch(url, headers=headers, params=params, verify=False)
                data = resp.json()
                if data.get('status_code') != 0:
                    continue
                if not data.get('data', {}).get('data'):
                    break
                items = data['data']['data']
                for it in items:
                    web_rid = it.get('web_rid') or self._generate_device_id()
                    room = it['room']
                    list_.append({
                        "vod_id": f"{web_rid}@@{room['id_str']}",
                        "vod_name": room['title'],
                        "vod_pic": room['cover']['url_list'][0],
                        "vod_remarks": f"{room['owner']['nickname']} (🔥{room['stats']['user_count_str']})"
                    })
                break
            except Exception:
                continue

        return {
            "list": list_,
            "page": page,
            "pagecount": 9999,
            "limit": 15,
            "total": 999999
        }

    def searchContent(self, key, quick, pg="1"):
        kw = key.strip()
        if not kw:
            return {"list": [], "page": 1}
        page = 1
        offset = 0

        headers = self._get_headers()

        # 策略1 专用直播搜索
        try:
            params1 = {
                "device_platform": "webapp",
                "aid": "6383",
                "channel": "channel_pc_web",
                "search_channel": "aweme_live",
                "search_source": "switch_tab",
                "query_correct_type": "1",
                "need_filter_settings": "1",
                "list_type": "single",
                "keyword": kw,
                "offset": str(offset),
                "count": "20",
                "os_version": "10"
            }
            r = self.fetch("https://www.douyin.com/aweme/v1/web/live/search/",
                           params=params1, headers=headers, verify=False)
            data = r.json()
            list_ = self._extract_search_videos(data.get('data'))
            if list_:
                return {"list": list_, "page": 1}
        except Exception:
            pass

        # 策略2 通用搜索
        try:
            params2 = {
                "device_platform": "webapp",
                "aid": "6383",
                "channel": "channel_pc_web",
                "search_channel": "aweme_live",
                "keyword": kw,
                "offset": str(offset),
                "count": "20",
                "os_version": "10"
            }
            r = self.fetch("https://www.douyin.com/aweme/v1/web/general/search/stream/",
                           params=params2, headers=headers, verify=False)
            data = r.json()
            list_ = self._extract_search_videos(data.get('data'))
            if list_:
                return {"list": list_, "page": 1}
        except Exception:
            pass

        # 降级分区搜索
        try:
            part_url = f"https://live.douyin.com/webcast/web/partition/search/?keyword={kw}&aid=6383"
            r = self.fetch(part_url, headers=self._get_headers(), verify=False)
            data = r.json()
            partitions = data.get('data', {}).get('SearchResult', [])
            if not partitions:
                return {"list": [], "page": 1}

            merged = []
            seen = set()
            for i in range(min(3, len(partitions))):
                part = partitions[i].get('partition', {})
                p_id = part.get('id_str')
                p_type = part.get('type')
                if not p_id or p_type is None:
                    continue
                cate_ret = self.categoryContent(f"{p_id}${p_type}", 1, None, None)
                for item in cate_ret.get('list', []):
                    if item['vod_id'] in seen:
                        continue
                    seen.add(item['vod_id'])
                    item['vod_remarks'] = item['vod_remarks'] or part.get('title', kw)
                    merged.append(item)
                    if len(merged) >= 20:
                        break
                if len(merged) >= 20:
                    break
            return {"list": merged, "page": 1}
        except Exception:
            pass

        return {"list": [], "page": 1}

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        raw_id = ids[0]
        parts = raw_id.split('@@')
        if len(parts) != 2:
            return {"list": []}
        web_rid, room_id = parts[0], parts[1]

        url = "https://live.douyin.com/webcast/room/web/enter/"
        params = {
            "aid": "6383",
            "app_name": "douyin_web",
            "live_id": "1",
            "device_platform": "web",
            "enter_from": "web_live",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "120.0.0.0",
            "web_rid": web_rid,
            "room_id_str": room_id,
            "enter_source": "",
            "is_need_double_stream": "false"
        }
        headers = self._get_headers()
        try:
            r = self.fetch(url, params=params, headers=headers, verify=False)
            data = r.json()
            if not data.get('data', {}).get('data'):
                return {"list": []}
            info = data['data']['data'][0]

            resolution_map = {
                "FULL_HD1": "蓝光",
                "HD1": "超清",
                "ORIGION": "原画",
                "SD1": "标清",
                "SD2": "高清"
            }

            flv_pull = info.get('stream_url', {}).get('flv_pull_url', {})
            flv_episodes = []
            for k, v in flv_pull.items():
                name = resolution_map.get(k, k)
                flv_episodes.append(f"{name}${v}")

            hls_pull = info.get('stream_url', {}).get('hls_pull_url_map', {})
            hls_episodes = []
            for k, v in hls_pull.items():
                name = resolution_map.get(k, k)
                hls_episodes.append(f"{name}${v}")

            vod_play_from = ""
            vod_play_url = ""
            if flv_episodes:
                vod_play_from += "FLV$$$"
                vod_play_url += "#".join(flv_episodes) + "$$$"
            if hls_episodes:
                vod_play_from += "HLS"
                vod_play_url += "#".join(hls_episodes)

            vod_play_from = vod_play_from.rstrip("$$$")
            vod_play_url = vod_play_url.rstrip("$$$")

            vod = {
                "vod_id": raw_id,
                "vod_name": info['title'],
                "vod_pic": info['cover']['url_list'][0],
                "vod_actor": info['owner']['nickname'],
                "vod_content": "QQ交流群:212706934"+info['title'],
                "vod_play_from": vod_play_from,
                "vod_play_url": vod_play_url
            }
            return {"list": [vod]}
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 0, "url": "", "header": self.headers}
        return {
            "parse": 0,
            "url": id,
            "header": {
                "User-Agent": self.ua,
                "Referer": self.host
            }
        }

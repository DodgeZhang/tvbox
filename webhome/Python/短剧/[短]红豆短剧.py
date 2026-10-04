#!/usr/bin/python
# -*- coding: utf-8 -*-
import json
import re

import requests
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def getName(self):
        return "红豆短剧"

    def init(self, extend=""):
        self.host = "https://hdou.tv"
        self.api = "https://api.dramaplay.shop"
        self.image_host = "https://static.hdou.tv"
        self.limit = 24
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Referer": self.host + "/",
            "Origin": self.host,
        }
        self.classes = [
            {"type_id": "0", "type_name": "最新短剧"},
            {"type_id": "334", "type_name": "都市"},
            {"type_id": "155", "type_name": "古装"},
            {"type_id": "338", "type_name": "爱情"},
            {"type_id": "362", "type_name": "总裁"},
            {"type_id": "285", "type_name": "甜宠"},
            {"type_id": "332", "type_name": "逆袭"},
            {"type_id": "341", "type_name": "重生"},
            {"type_id": "306", "type_name": "穿越"},
            {"type_id": "397", "type_name": "玄幻"},
            {"type_id": "220", "type_name": "悬疑"},
        ]
        genres = [
            ("0", "全部"), ("334", "都市"), ("155", "古装"),
            ("338", "爱情"), ("362", "总裁"), ("285", "甜宠"),
            ("332", "逆袭"), ("341", "重生"), ("306", "穿越"),
            ("397", "玄幻"), ("220", "悬疑"), ("320", "萌宝"),
            ("307", "系统"), ("250", "校园"), ("343", "闪婚"),
            ("346", "马甲"), ("299", "神医"), ("260", "民国"),
            ("256", "武侠"), ("190", "宫廷"),
        ]
        genre_values = [{"n": name, "v": value} for value, name in genres]
        self.filters = {
            item["type_id"]: [{
                "key": "typeid",
                "name": "题材",
                "init": item["type_id"],
                "value": genre_values,
            }]
            for item in self.classes
        }
        self.session = requests.Session()

    def _get(self, path, params=None):
        try:
            response = self.session.get(self.api + path, params=params, headers=self.headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
        except (requests.RequestException, ValueError):
            return {}

    def _page(self, value):
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return 1

    def _image(self, value):
        value = str(value or "").strip()
        if value.startswith("//"):
            return "https:" + value
        if value.startswith(("http://", "https://")):
            return re.sub(r"(?<!:)//+", "/", value)
        return self.image_host + "/" + value.lstrip("/") if value else ""

    def _remarks(self, item):
        total = item.get("sum") or item.get("video") or 0
        return str(item.get("tp") or (f"全{total}集" if total else item.get("text", "")))

    def _items(self, rows):
        return [{
            "vod_id": str(item.get("id", "")),
            "vod_name": str(item.get("name", "")),
            "vod_pic": self._image(item.get("img") or item.get("pic")),
            "vod_remarks": self._remarks(item),
        } for item in rows if item.get("id") and item.get("name")]

    def _list(self, pg=1, type_id="0", key=""):
        pg = self._page(pg)
        params = {"limit": self.limit, "offset": (pg - 1) * self.limit, "lx": 1}
        if str(type_id) not in ("", "0"):
            params["typeid"] = str(type_id)
        if key:
            params["keytext"] = str(key)
        data = self._get("/api/video/lists", params)
        total = int(data.get("total") or 0)
        rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        return {
            "page": pg,
            "pagecount": max(1, (total + self.limit - 1) // self.limit),
            "limit": self.limit,
            "total": total,
            "list": self._items(rows),
        }

    def homeContent(self, filter):
        result = self._list(1)
        return {"class": self.classes, "list": result["list"], "filters": self.filters}

    def homeVideoContent(self):
        return {"list": self._list(1)["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        extend = extend if isinstance(extend, dict) else {}
        type_id = extend.get("typeid")
        return self._list(pg, tid if type_id in (None, "") else type_id)

    def _actors(self, value):
        if isinstance(value, list):
            return ",".join(str(item) for item in value if item)
        try:
            data = json.loads(value or "[]")
            return ",".join(str(item) for item in data if item) if isinstance(data, list) else ""
        except (TypeError, ValueError):
            return str(value or "")

    def _text(self, value):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(value or ""))).strip()

    def detailContent(self, ids):
        result = []
        for vod_id in ids:
            vod_id = str(vod_id)
            info = self._get("/api/video/info", {"id": vod_id, "mid": 0})
            episode_data = self._get("/api/video/videoinfo", {
                "page": 1, "uid": 0, "vid": vod_id, "mid": 0, "token": "",
            })
            episodes = episode_data.get("data") or episode_data.get("result") or []
            if not isinstance(episodes, list):
                episodes = []
            episodes.sort(key=lambda item: (int(item.get("weigh") or 0), int(item.get("id") or 0)))
            play_list = []
            for index, episode in enumerate(episodes, 1):
                name = str(episode.get("name") or episode.get("fjname") or f"第{index}集").replace("$", " ").replace("#", " ")
                url = str(episode.get("src") or episode.get("videourl") or "").strip()
                if url:
                    play_list.append(f"{name}${url}")
            if not play_list and info.get("videourl"):
                play_list.append(f"{info.get('ji') or '第1集'}${info['videourl']}")
            year = str(info.get("updatetime") or "")[:4]
            result.append({
                "vod_id": vod_id,
                "vod_name": str(info.get("name") or f"短剧{vod_id}"),
                "vod_pic": self._image(info.get("img") or info.get("pic")),
                "type_name": str(info.get("text") or "短剧"),
                "vod_year": year if year.isdigit() else "",
                "vod_area": "",
                "vod_remarks": self._remarks(info),
                "vod_actor": self._actors(info.get("yyid")),
                "vod_director": "",
                "vod_content": self._text(info.get("story") or info.get("info")),
                "vod_play_from": "红豆直连",
                "vod_play_url": "#".join(play_list),
            })
        return {"list": result}

    def searchContent(self, key, quick, pg="1"):
        return self._list(pg, "0", key)

    def playerContent(self, flag, id, vipFlags):
        return {"parse": 0, "jx": 0, "url": str(id), "header": self.headers}

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
══════════════════════════════════════════════════════════════════
9g/md 系列 Python Spider
适用生态：TVBox / 影视仓 / py-drpy / 猫影视
作者交流群：TG群 https://t.me/tvshare23
功能特性：普通长视频全分类 + 🎬 AI短剧专区（全集独立播放流精准选集）
══════════════════════════════════════════════════════════════════
"""

import sys
import json
import urllib.parse
from typing import Dict, List, Any

try:
    from base.spider import Spider as SpiderBase
except ImportError:
    class SpiderBase:
        pass

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    HAS_REQUESTS = False


class Spider(SpiderBase):
    siteUrl = "https://mdcmai4.xyz"
    api_categories = "/api/v1/categories?type=video"
    api_videos = "/api/v1/videos"
    api_short_dramas = "/api/v1/short-dramas"
    api_short_drama_detail = "/api/v1/short-dramas/{id}?productId=1"
    api_search = "/api/v1/videos/search"
    api_m3u8_proxy = "/api/v1/m3u8/proxy?path="
    api_img_proxy = "/api/v1/image/proxy?path="

    SHORT_DRAMA_TID = "short_drama_ai"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://mdcmai4.xyz/",
        "Origin": "https://mdcmai4.xyz",
        "Accept": "application/json, text/plain, */*",
    }

    def getName(self) -> str:
        return "麻豆传媒🔞TG群：@tvshare23"

    def init(self, extend: str = "") -> bool:
        return True

    def isVideoFormat(self, url: str) -> bool:
        return ".m3u8" in url or ".mp4" in url

    def manualVideoCheck(self) -> bool:
        return False

    def destroy(self):
        pass

    # ───── 网络请求封装 ─────
    def _fetch_json(self, url: str) -> Dict[str, Any]:
        """发起 GET 请求并解析返回的 JSON"""
        try:
            if HAS_REQUESTS:
                resp = requests.get(url, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json()
            else:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    return json.loads(response.read().decode("utf-8"))
        except Exception:
            pass
        return {}

    # ───── URL 规范化组装 ─────
    def _format_cover(self, cover_path: str) -> str:
        """格式化封面图片地址"""
        if not cover_path:
            return ""
        if cover_path.startswith("http"):
            return cover_path
        if cover_path.startswith("/uploads/") or cover_path.startswith("/api/"):
            return f"{self.siteUrl}{cover_path}"
        encoded_path = urllib.parse.quote(cover_path, safe="")
        return f"{self.siteUrl}{self.api_img_proxy}{encoded_path}"

    def _format_play_url(self, video_path: str) -> str:
        """格式化 m3u8 播放地址"""
        if not video_path:
            return ""
        if video_path.startswith("http"):
            return video_path
        if video_path.startswith("/api/v1/m3u8/proxy"):
            return f"{self.siteUrl}{video_path}"
        encoded_path = urllib.parse.quote(video_path, safe="")
        return f"{self.siteUrl}{self.api_m3u8_proxy}{encoded_path}"

    def _format_duration(self, seconds: int) -> str:
        """秒数转为 分:秒"""
        if not seconds:
            return ""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    # ───── TVBox 核心接口 ─────

    def homeContent(self, filter: bool = False) -> Dict[str, Any]:
        """首页：加入【AI短剧】大分类以及所有长视频分类"""
        classes = [
            {"type_id": self.SHORT_DRAMA_TID, "type_name": "🔥 AI短剧"}
        ]

        url = f"{self.siteUrl}{self.api_categories}"
        res = self._fetch_json(url)

        if res.get("code") == 200 and isinstance(res.get("data"), list):
            for cat in res["data"]:
                if cat.get("enabled", True):
                    classes.append({
                        "type_id": str(cat.get("id")),
                        "type_name": cat.get("name", "未知分类")
                    })

        return {"class": classes}

    def categoryContent(self, tid: str, pg: str, filter: bool, extend: Dict) -> Dict[str, Any]:
        """分类列表：自动分流处理 AI 短剧与普通长视频"""
        page = int(pg) if pg else 1
        videos = []
        pagecount = page
        total = 0

        # 分流 1：AI 短剧独立列表
        if str(tid) == self.SHORT_DRAMA_TID:
            url = f"{self.siteUrl}{self.api_short_dramas}?productId=1&sortBy=heat&page={page}&size=12"
            res = self._fetch_json(url)
            if res.get("code") == 200:
                data = res.get("data", {})
                pagecount = data.get("totalPages", page)
                total = data.get("total", 0)

                for item in data.get("items", []):
                    ep_cnt = item.get("episodeCount", 1)
                    rating = item.get("rating", 0.0)
                    videos.append({
                        "vod_id": f"drama@@{item.get('id')}@@{item.get('title', '')}@@{item.get('coverUrl', '')}",
                        "vod_name": item.get("title", ""),
                        "vod_pic": self._format_cover(item.get("coverUrl", "")),
                        "vod_remarks": f"评分:{rating} | 共{ep_cnt}集"
                    })
        # 分流 2：普通长视频分类
        else:
            url = f"{self.siteUrl}{self.api_videos}?page={page}&size=24&categoryId={tid}"
            res = self._fetch_json(url)
            if res.get("code") == 200:
                data = res.get("data", {})
                pagecount = data.get("totalPages", page)
                total = data.get("total", 0)

                for item in data.get("items", []):
                    v_url = item.get("videoUrl", "")
                    videos.append({
                        "vod_id": f"video@@{item.get('id')}@@{v_url}@@{item.get('title', '')}@@{item.get('coverUrl', '')}",
                        "vod_name": item.get("title", ""),
                        "vod_pic": self._format_cover(item.get("coverUrl", "")),
                        "vod_remarks": self._format_duration(item.get("durationSec", 0)) or item.get("categoryName", "")
                    })

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 12 if str(tid) == self.SHORT_DRAMA_TID else 24,
            "total": total
        }

    def detailContent(self, ids: List[str]) -> Dict[str, Any]:
        """视频详情：支持普通视频单集与 AI 短剧全集独立真实选集解析"""
        vod_id = ids[0]

        if "@@" in vod_id:
            parts = vod_id.split("@@")
            vtype = parts[0]

            # ── 场景 1：AI 短剧详情（动态拉取全部真实分集）──
            if vtype == "drama":
                drama_id = parts[1]
                title = parts[2] if len(parts) > 2 else "短剧详情"
                cover = parts[3] if len(parts) > 3 else ""

                detail_url = f"{self.siteUrl}{self.api_short_drama_detail.format(id=drama_id)}"
                res = self._fetch_json(detail_url)

                episodes = []
                if res.get("code") == 200 and isinstance(res.get("data"), dict):
                    drama_data = res["data"]
                    title = drama_data.get("title", title)
                    cover = drama_data.get("coverUrl", cover)

                    # 遍历全部分集，绑定每一集独立的 videoUrl
                    for ep in drama_data.get("episodes", []):
                        ep_no = ep.get("episodeNo", 1)
                        ep_title = f"第{ep_no}集"
                        raw_vurl = ep.get("videoUrl", "")
                        if raw_vurl:
                            play_stream = self._format_play_url(raw_vurl)
                            episodes.append(f"{ep_title}${play_stream}")

                play_url_str = "#".join(episodes) if episodes else "暂无分集数据$error"
                from_name = "AI短剧专线"

            # ── 场景 2：普通长视频单集详情 ──
            else:
                video_url = parts[2] if len(parts) > 2 else ""
                title = parts[3] if len(parts) > 3 else "视频详情"
                cover = parts[4] if len(parts) > 4 else ""
                play_stream = self._format_play_url(video_url)
                play_url_str = f"正片${play_stream}" if play_stream else "暂无播放地址$error"
                from_name = "专线播放"
        else:
            title = "在线播放"
            cover = ""
            from_name = "专线播放"
            play_url_str = "暂无播放地址$error"

        return {
            "list": [{
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": self._format_cover(cover),
                "vod_play_from": from_name,
                "vod_play_url": play_url_str
            }]
        }

    def searchContent(self, key: str, quick: str, pg="1") -> Dict[str, Any]:
        """搜索接口"""
        page = int(pg) if pg else 1
        encoded_kw = urllib.parse.quote(key)
        url = f"{self.siteUrl}{self.api_search}?page={page}&size=24&q={encoded_kw}"
        res = self._fetch_json(url)

        videos = []
        if res.get("code") == 200:
            data = res.get("data", {})
            for item in data.get("items", []):
                v_url = item.get("videoUrl", "")
                videos.append({
                    "vod_id": f"video@@{item.get('id')}@@{v_url}@@{item.get('title', '')}@@{item.get('coverUrl', '')}",
                    "vod_name": item.get("title", ""),
                    "vod_pic": self._format_cover(item.get("coverUrl", "")),
                    "vod_remarks": self._format_duration(item.get("durationSec", 0)) or item.get("categoryName", "")
                })

        return {"list": videos}

    def playerContent(self, flag: str, id: str, vipFlags: str) -> Dict[str, Any]:
        """播放地址解析：注入请求头支持播放"""
        return {
            "parse": 0,
            "playUrl": "",
            "url": id,
            "header": {
                "User-Agent": self.headers["User-Agent"],
                "Referer": "https://mdcmai4.xyz/",
                "Origin": "https://mdcmai4.xyz"
            }
        }

    def localProxy(self, param: Dict) -> List[Any]:
        return [404, "text/plain", ""]

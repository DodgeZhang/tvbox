# -*- coding: utf-8 -*-
"""
红果短剧 TVBox Python 源（桥模式 - 完整版）
"""
import json
import re
import sys
import time
from urllib.parse import quote, urlencode

import requests

sys.path.append("../../")
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        pass


class Spider(Spider):
    site = "https://hongguoduanju.com"
    
    # ===== 桥地址（自行替换） =====
    # 本地桥: http://127.0.0.1:9979
    # 局域网桥: http://192.168.x.x:9979
    bridge = "http://127.0.0.1:9979"
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 12; TV) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    
    category_map = {
        "现代": "background=cate_757",
        "都市": "background=cate_1",
        "古代": "background=cate_758",
        "乡村": "background=cate_11",
        "年代": "background=cate_79",
        "架空": "background=cate_452",
        "职场": "background=cate_127",
        "民国": "background=cate_390",
        "校园": "background=cate_4",
        "宫廷": "background=cate_1153",
        "荒岛": "background=cate_1162",
        "现言": "topic=cate_1021",
        "女性成长": "topic=cate_1048",
        "脑洞": "topic=cate_262",
        "奇幻": "topic=cate_1020",
        "玄幻": "topic=cate_1019",
        "古言": "topic=cate_439",
        "战神": "topic=cate_1038",
        "宫斗": "topic=cate_246",
        "仙侠": "topic=cate_1013",
        "权谋": "topic=cate_1047",
        "种田": "topic=cate_1180",
        "年代爱情": "topic=cate_1022",
        "悬疑": "topic=cate_165",
        "喜剧": "topic=cate_303",
        "青春": "topic=cate_297",
        "志怪": "topic=cate_1027",
        "民国爱情": "topic=cate_1025",
        "灵异": "topic=cate_751",
        "家国情怀": "topic=cate_1235",
        "法律": "topic=cate_1136",
        "刑侦": "topic=cate_1148",
        "抗战": "topic=cate_504",
        "武侠": "topic=cate_1172",
        "民国传奇": "topic=cate_1240",
        "求生": "topic=cate_1168",
        "动作": "topic=cate_302",
        "科幻": "topic=cate_1092",
        "恐怖": "topic=cate_1219",
        "商战": "topic=cate_1225",
        "打脸虐渣": "setting=cate_1051",
        "大男主": "setting=cate_1207",
        "大女主": "setting=cate_760",
        "马甲": "setting=cate_266",
        "重生": "setting=cate_36",
        "穿越": "setting=cate_37",
        "系统": "setting=cate_19",
        "先婚后爱": "setting=cate_265",
        "家长里短": "setting=cate_862",
        "小人物": "setting=cate_1010",
        "破镜重圆": "setting=cate_475",
        "神豪": "setting=cate_20",
        "豪门": "setting=cate_936",
        "强者回归": "setting=cate_1045",
        "异能": "setting=cate_598",
        "传承觉醒": "setting=cate_1007",
        "虐恋": "setting=cate_1008",
        "医生": "setting=cate_487",
        "强强联合": "setting=cate_1049",
        "赘婿逆袭": "setting=cate_1044",
        "甜宠": "setting=cate_96",
        "娱乐圈": "setting=cate_43",
        "神医": "setting=cate_26",
        "青梅竹马": "setting=cate_387",
        "姐弟恋": "setting=cate_762",
        "玄学": "setting=cate_929",
        "追妻火葬场": "setting=cate_616",
        "业界精英": "setting=cate_1293",
        "一见钟情": "setting=cate_477",
        "福宝": "setting=cate_1291",
        "捞偏门": "setting=cate_1287",
        "反派主角": "setting=cate_1042",
        "萌宠": "setting=cate_428",
        "方言": "setting=cate_1255",
        "双向救赎": "setting=cate_1200",
        "白月光": "setting=cate_615",
        "灵魂互换": "setting=cate_831",
        "病娇": "setting=cate_380",
        "暴富": "setting=cate_1191",
        "黑道": "setting=cate_826",
        "丧尸": "setting=cate_582",
        "特种兵": "setting=cate_375",
        "男频": "gender=1",
        "女频": "gender=0",
        "7天内上新": "time=1",
        "14天内上新": "time=2",
        "30天内上新": "time=3",
        "90天内上新": "time=4",
        "最新": "sort_type=2",
        "最热": "sort_type=1",
    }

    def __init__(self):
        self._cache = {}

    def getName(self):
        return "红果短剧"

    def init(self, extend=""):
        # 支持通过extend传入桥地址
        if extend:
            try:
                data = json.loads(extend) if isinstance(extend, str) else extend
                if isinstance(data, dict) and data.get("bridge"):
                    self.bridge = data.get("bridge").rstrip("/")
            except:
                if isinstance(extend, str) and extend.startswith("http"):
                    self.bridge = extend.rstrip("/")

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return

    def _get(self, url):
        response = requests.get(url, headers=self.headers, timeout=25)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text

    def _router_data(self, url):
        cached = self._cache.get(url)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        html = self._get(url)
        
        data = None
        
        match = re.search(
            r'_ROUTER_DATA\s*=\s*(\{.*?\})\s*;',
            html,
            re.S,
        )
        if match:
            try:
                data = json.loads(match.group(1))
                self._cache[url] = (time.time(), data)
                return data
            except:
                pass
        
        if not data:
            match = re.search(
            r'window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*;',
            html,
            re.S,
        )
            if match:
                try:
                    data = json.loads(match.group(1))
                    self._cache[url] = (time.time(), data)
                    return data
                except:
                    pass
        
        if not data:
            data = self._parse_from_html(html)
            if data:
                self._cache[url] = (time.time(), data)
                return data
        
        raise RuntimeError("页面数据格式已变化")

    def _parse_from_html(self, html):
        result = {"loaderData": {"category_page": {"recommendList": []}}}
        
        card_pattern = r'<a\s+href="/detail\?series_id=(\d+)"[^>]*class="[^"]*card[^"]*"[^>]*>.*?<source[^>]*srcset="([^"]+)"[^>]*>.*?<img[^>]*alt="([^"]+)"[^>]*>.*?全(\d+)集'
        matches = re.findall(card_pattern, html, re.S)
        
        for series_id, pic, title, episodes in matches:
            result["loaderData"]["category_page"]["recommendList"].append({
                "series_id": series_id,
                "series_name": title.strip(),
                "series_cover": pic.split(" ")[0] if " " in pic else pic,
                "episode_cnt": int(episodes),
            })
        
        return result

    @staticmethod
    def _vod(item):
        tags = item.get("tags") or []
        if isinstance(tags, list):
            tags = " · ".join(str(x) for x in tags[:3])
        count = item.get("episode_cnt") or len(item.get("vid_list") or [])
        remark = ("全%s集" % count) if count else str(tags or "")
        return {
            "vod_id": str(item.get("series_id") or ""),
            "vod_name": str(item.get("series_name") or ""),
            "vod_pic": str(item.get("series_cover") or ""),
            "vod_remarks": remark,
        }

    def _category_items(self, query):
        url = self.site + "/category?" + query
        data = self._router_data(url)
        page = data.get("loaderData", {}).get("category_page", {})
        items = page.get("recommendList") or []
        if not items:
            items = page.get("categoryData", {}).get("recommendList") or []
        seen = set()
        result = []
        for item in items:
            sid = str(item.get("series_id") or "")
            if sid and sid not in seen:
                seen.add(sid)
                result.append(item)
        return result

    def homeContent(self, filter):
        return {
            "class": [
                {"type_name": name, "type_id": query}
                for name, query in self.category_map.items()
            ],
            "list": self.homeVideoContent().get("list", []),
        }

    def homeVideoContent(self):
        try:
            items = self._category_items("sort_type=1")[:30]
            return {"list": [self._vod(x) for x in items]}
        except Exception as exc:
            print("红果首页读取失败:", exc)
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page = max(1, int(pg or 1))
        per_page = 30
        try:
            items = self._category_items(str(tid))
            start = (page - 1) * per_page
            chunk = items[start:start + per_page]
            page_count = max(1, (len(items) + per_page - 1) // per_page)
            return {
                "list": [self._vod(x) for x in chunk],
                "page": page,
                "pagecount": page_count,
                "limit": per_page,
                "total": len(items),
            }
        except Exception as exc:
            print("红果分类读取失败:", exc)
            return {"list": [], "page": page, "pagecount": page}

    def detailContent(self, ids):
        series_id = str(ids[0])
        url = self.site + "/detail?series_id=" + quote(series_id)
        try:
            data = self._router_data(url)
            detail = data.get("loaderData", {}).get("detail_page", {})
            series = detail.get("seriesDetail") or {}
            vids = series.get("vid_list") or []
            
            # ===== 构建播放地址（走桥） =====
            if vids:
                episodes = []
                for index, vid in enumerate(vids):
                    if str(vid):
                        # 每个vid通过桥获取播放地址
                        episodes.append("第%d集$%s" % (index + 1, vid))
                play_url = "#".join(episodes)
            else:
                play_url = ""
            
            tags = series.get("tags") or []
            if isinstance(tags, list):
                tags = ",".join(str(x) for x in tags)
            
            vod = {
                "vod_id": series_id,
                "vod_name": str(series.get("series_name") or "红果短剧"),
                "vod_pic": str(series.get("series_cover") or ""),
                "type_name": str(tags),
                "vod_remarks": "全%s集" % (series.get("episode_cnt") or len(vids)),
                "vod_content": str(series.get("series_intro") or ""),
                "vod_play_from": "红果",
                "vod_play_url": play_url,
            }
            return {"list": [vod]}
        except Exception as exc:
            print("红果详情读取失败:", exc)
            return {"list": []}

    def searchContent(self, key, quick, pg=1):
        page = max(1, int(pg or 1))
        per_page = 30
        try:
            items = self._category_items("sort_type=1")
            keyword = str(key).strip().lower()
            matches = [
                x for x in items
                if keyword in str(x.get("series_name") or "").lower()
                or keyword in str(x.get("series_intro") or "").lower()
            ]
            start = (page - 1) * per_page
            return {
                "list": [self._vod(x) for x in matches[start:start + per_page]],
                "page": page,
            }
        except Exception as exc:
            print("红果搜索失败:", exc)
            return {"list": [], "page": page}

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    def playerContent(self, flag, pid, vipFlags):
        # ===== 通过桥获取真实视频地址 =====
        # 桥服务接收到vid后，返回真实视频地址
        url = self.bridge + "/play?" + urlencode({"vid": str(pid)})
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": {
                "User-Agent": self.headers["User-Agent"],
                "Referer": self.site + "/",
            },
        }

    def localProxy(self, params):
        return None
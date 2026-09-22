# -*- coding: utf-8 -*-
# ============================================================
# 五合一全网影视聚合 V2 (适配 Cat/TVBox Python Spider)
# 包含:
#   s1~s32 : 采集聚合 32 个 API 源 (电影天堂/量子/樱花/1080...)
#   s33    : 毒舌影视  (xnhrsb.com  网页解析)
#   s34    : 小蜜蜂影院 (xmfyy.vip  网页解析+官源解密)
#   s35    : 拾光影视  (tv.time1080.xyz 动态API, mj直链/qilin平台解析)
#   s36    : 王爷短视频 (yujn.cn 短视频接口, 竖屏播放)
# 直接放入 TVBox/影视TV 等支持 Python 采集的播放器 py 目录即可
# ============================================================

import json
import re
import time
import random
import base64
import urllib.parse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urljoin
from pyquery import PyQuery as pq
from base.spider import Spider


class Spider(Spider):

    # ==================== 公共请求头 ====================
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    # ==================== s1~s32: API 聚合源 ====================
    sources = {
        's1': {'name': '🎬电影天堂', 'api': 'http://caiji.dyttzyapi.com/api.php/provide/vod/from/dyttm3u8/at/json'},
        's2': {'name': '💧无水印', 'api': 'https://api.wsyzy.net/api.php/provide/vod'},
        's3': {'name': '🧸量子', 'api': 'https://cj.lziapi.com/api.php/provide/vod'},
        's4': {'name': '📺1080资源', 'api': 'https://api.1080zyku.com/inc/api_mac10.php'},
        's5': {'name': '🔥155资源', 'api': 'https://155api.com/api.php/provide/vod'},
        's6': {'name': '📺天涯', 'api': 'https://tyyszy.com/api.php/provide/vod'},
        's7': {'name': '📺暴风', 'api': 'https://bfzyapi.com/api.php/provide/vod'},
        's8': {'name': '⚡索尼闪电', 'api': 'https://xsd.sdzyapi.com/api.php/provide/vod'},
        's9': {'name': '📺索尼', 'api': 'https://suoniapi.com/api.php/provide/vod'},
        's10': {'name': '📺红牛', 'api': 'https://www.hongniuzy2.com/api.php/provide/vod'},
        's11': {'name': '📺茅台', 'api': 'https://caiji.maotaizy.cc/api.php/provide/vod'},
        's12': {'name': '🐯虎牙', 'api': 'https://www.huyaapi.com/api.php/provide/vod'},
        's13': {'name': '📺豆瓣', 'api': 'https://caiji.dbzy.tv/api.php/provide/vod'},
        's14': {'name': '📺豆瓣2', 'api': 'https://dbzy.tv/api.php/provide/vod'},
        's15': {'name': '📺豪华', 'api': 'https://hhzyapi.com/api.php/provide/vod'},
        's16': {'name': '📺CK资源', 'api': 'https://ckzy.me/api.php/provide/vod'},
        's17': {'name': '📺无尽', 'api': 'https://api.wujinapi.cc/api.php/provide/vod'},
        's18': {'name': '🌕光速', 'api': 'https://api.guangsuapi.com/api.php/provide/vod'},
        's19': {'name': '📺卧龙', 'api': 'https://collect.wolongzyw.com/api.php/provide/vod'},
        's20': {'name': '📺新浪', 'api': 'https://api.xinlangapi.com/xinlangapi.php/provide/vod'},
        's21': {'name': '📺旺旺', 'api': 'https://api.wwzy.tv/api.php/provide/vod'},
        's22': {'name': '📺最大', 'api': 'https://api.zuidapi.com/api.php/provide/vod'},
        's23': {'name': '🌸樱花', 'api': 'https://m3u8.apiyhzy.com/api.php/provide/vod'},
        's24': {'name': '🐮牛牛', 'api': 'https://api.niuniuzy.me/api.php/provide/vod'},
        's25': {'name': '☁️百度云', 'api': 'https://api.apibdzy.com/api.php/provide/vod'},
        's26': {'name': '🏎速播', 'api': 'https://subocaiji.com/api.php/provide/vod'},
        's27': {'name': '🦅金鹰', 'api': 'https://jinyingzy.com/api.php/provide/vod'},
        's28': {'name': '⚡闪电', 'api': 'https://sdzyapi.com/api.php/provide/vod'},
        's29': {'name': '👑非凡', 'api': 'https://cj.ffzyapi.com/api.php/provide/vod'},
        's30': {'name': '🍃飘零', 'api': 'https://p2100.net/api.php/provide/vod'},
        's31': {'name': '🐾魔爪', 'api': 'https://mozhuazy.com/api.php/provide/vod'},
        's32': {'name': '📺魔都', 'api': 'https://www.mdzyapi.com/api.php/provide/vod'},
    }

    # ==================== s33: 毒舌影视 ====================
    DUSHE_KEY = 's33'
    DUSHE_NAME = '🐍毒舌影视'
    dushe_host = 'https://www.xnhrsb.com/'
    dushe_headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; Mobile) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/114.0.0.0 Mobile Safari/537.36',
        'Referer': 'https://www.xnhrsb.com/',
    }
    dushe_classes_config = [
        ("电影", "1"), ("电视剧", "2"), ("综艺", "3"),
        ("动漫", "4"), ("短剧", "5"), ("豆瓣", "duoban"),
    ]

    # ==================== s34: 小蜜蜂影院 ====================
    XMF_KEY = 's34'
    XMF_NAME = '📺小蜜蜂影院'
    XMF_DOMAINS = ["https://www.xmfyy.vip", "https://www.xmfyy.cc"]
    XMF_UA = (
        'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36'
    )
    # 解析接口映射 (from 值 -> 解析器 URL)
    XMF_PARSE_MAP = {
        'mgtv': 'https://svip.qlplayer.cyou/?url=',
        'bilibili': 'https://svip.qlplayer.cyou/?url=',
        'qiyi': 'https://svip.qlplayer.cyou/?url=',
        'qq': 'https://svip.qlplayer.cyou/?url=',
        'youku': 'https://svip.qlplayer.cyou/?url=',
        'sohu': 'https://www.xmfyy.com/static/player/artplayer.html?url=',
        'hnm3u8': 'https://www.hnjiexi.com/m3u8/?url=',
        'jsm3u8': 'https://svip.ffzyplay.com/?url=',
        'rym3u8': 'https://ruyiplayer.com?url=',
        'liangzi': 'https://jisuzyjx.com/play/?url=',
        'dytt': 'https://vip.dyttzyplay.com/?url=',
        'dyttm3u8': 'https://vip.dyttzyplay.com/?url=',
    }
    xmf_classes = [
        {'type_name': '连续剧', 'type_id': '2'},
        {'type_name': '电影', 'type_id': '1'},
        {'type_name': '动漫', 'type_id': '4'},
        {'type_name': '综艺', 'type_id': '3'},
    ]
    xmf_filters = {
        '2': [
            {'key': 'type', 'name': '类型', 'value': [
                {'n': '全部', 'v': ''}, {'n': '国产剧', 'v': '13'}, {'n': '港台剧', 'v': '14'},
                {'n': '日韩剧', 'v': '15'}, {'n': '欧美剧', 'v': '16'}, {'n': '纪录片', 'v': '38'},
                {'n': '其他剧', 'v': '37'}]},
            {'key': 'by', 'name': '排序', 'value': [
                {'n': '最新', 'v': 'time'}, {'n': '最热', 'v': 'hits'}, {'n': '评分', 'v': 'score'}]},
            {'key': 'area', 'name': '地区', 'value': [
                {'n': '全部', 'v': ''}, {'n': '内地', 'v': '内地'}, {'n': '香港', 'v': '香港'},
                {'n': '韩国', 'v': '韩国'}, {'n': '日本', 'v': '日本'}, {'n': '美国', 'v': '美国'},
                {'n': '英国', 'v': '英国'}]},
            {'key': 'year', 'name': '年份', 'value': [
                {'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'},
                {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}]},
        ],
        '1': [
            {'key': 'type', 'name': '类型', 'value': [
                {'n': '全部', 'v': ''}, {'n': '动作片', 'v': '6'}, {'n': '喜剧片', 'v': '7'},
                {'n': '爱情片', 'v': '8'}, {'n': '科幻片', 'v': '9'}, {'n': '恐怖片', 'v': '10'},
                {'n': '剧情片', 'v': '11'}, {'n': '战争片', 'v': '12'}, {'n': '悬疑片', 'v': '21'}]},
            {'key': 'by', 'name': '排序', 'value': [
                {'n': '最新', 'v': 'time'}, {'n': '最热', 'v': 'hits'}, {'n': '评分', 'v': 'score'}]},
            {'key': 'area', 'name': '地区', 'value': [
                {'n': '全部', 'v': ''}, {'n': '大陆', 'v': '大陆'}, {'n': '香港', 'v': '香港'},
                {'n': '美国', 'v': '美国'}, {'n': '韩国', 'v': '韩国'}, {'n': '日本', 'v': '日本'},
                {'n': '法国', 'v': '法国'}, {'n': '英国', 'v': '英国'}]},
            {'key': 'year', 'name': '年份', 'value': [
                {'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'},
                {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'}]},
        ],
        '4': [
            {'key': 'type', 'name': '类型', 'value': [
                {'n': '全部', 'v': ''}, {'n': '动漫', 'v': '28'}, {'n': '番剧', 'v': '39'},
                {'n': '动画片', 'v': '19'}]},
            {'key': 'by', 'name': '排序', 'value': [
                {'n': '最新', 'v': 'time'}, {'n': '最热', 'v': 'hits'}, {'n': '评分', 'v': 'score'}]},
        ],
        '3': [
            {'key': 'by', 'name': '排序', 'value': [
                {'n': '最新', 'v': 'time'}, {'n': '最热', 'v': 'hits'}, {'n': '评分', 'v': 'score'}]},
        ],
    }
    # 需要跳过的搜索引擎线路关键词
    XMF_SKIP_KEYWORDS = ("搜索", "百度", "搜狗", "神马", "360", "baidu", "google", "sogou")

    # ==================== s35: 拾光影视 ====================
    SG_KEY = 's35'
    SG_NAME = '拾光影视'
    sg_host = 'https://tv.time1080.xyz'
    sg_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://tv.time1080.xyz/",
    }
    sg_timeout = 20
    # 拾光状态 (懒加载)
    sg_sources = {}
    sg_player_api_map = {}
    sg_classes = []
    sg_home_cache = None
    sg_home_cache_time = 0
    sg_home_cache_ttl = 3600
    sg_ready = False

    # ==================== s36: 王爷短视频 ====================
    WY_KEY = 's36'
    WY_NAME = '😍王爷短视频'
    wy_classes = [
        ("小姐姐①", "http://api.yujn.cn/api/zzxjj.php"),
        ("小姐姐②", "http://api.yujn.cn/api/xjj.php"),
        ("女大学生", "http://api.yujn.cn/api/nvda.php"),
        ("黑丝", "http://api.yujn.cn/api/heisis.php"),
        ("Cosplay", "http://api.yujn.cn/api/manzhan.php"),
        ("白丝", "http://api.yujn.cn/api/baisis.php"),
        ("极品身材", "http://api.yujn.cn/api/wmsc.php"),
        ("蛇姐", "http://api.yujn.cn/api/shejie.php"),
        ("性感吊带", "http://api.yujn.cn/api/diaodai.php"),
        ("玉足", "http://api.yujn.cn/api/jpmt.php"),
        ("清纯", "http://api.yujn.cn/api/qingchun.php"),
        ("萝莉", "http://api.yujn.cn/api/luoli.php"),
    ]

    # ==================== 初始化 ====================
    def init(self, extend=""):
        # 小蜜蜂状态
        self.xmf_host = self.XMF_DOMAINS[0]
        self.xmf_header = {
            'User-Agent': self.XMF_UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.xmf_host + '/',
            'Connection': 'keep-alive',
        }
        self._xmf_home_cache = []
        self._xmf_home_cache_time = 0
        self._probe_xmf_domain()

    def getName(self):
        return "影视五合一全网聚合V2(含拾光)"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def close(self):
        self.destroy()

    # ==================== 公共请求 ====================
    def fetch(self, url, timeout=8, headers=None):
        try:
            r = requests.get(
                url,
                headers=headers or self.headers,
                timeout=timeout,
                verify=False
            )
            return r
        except Exception:
            return None

    def get_text(self, url, timeout=8, headers=None):
        rsp = self.fetch(url, timeout=timeout, headers=headers)
        if rsp is None:
            return ""
        return rsp.text

    # ==================== API 源公共清洗 ====================
    def clean_item(self, item, source_key, source_name, is_detail=False):
        item = dict(item)

        if not is_detail:
            item["vod_id"] = f"{source_key}@@{item.get('vod_id', '')}"

        remarks = item.get("vod_remarks", "")
        item["vod_remarks"] = f"{source_name} | {remarks}"

        if item.get("vod_play_from"):
            froms = item["vod_play_from"].split("$$$")
            froms = [f"{source_name}-{x}" for x in froms]
            item["vod_play_from"] = "$$$".join(froms)

        item.pop("vod_down_from", None)
        item.pop("vod_down_url", None)

        return item

    # ============================================================
    #  首页
    # ============================================================
    def homeContent(self, filter):
        classes = []
        filters = {}

        def load_class(key, source):
            url = f"{source['api']}?ac=list"
            html = self.get_text(url, 4)

            try:
                data = json.loads(html)
            except:
                data = {}

            vals = [{"n": "全部(最新)", "v": ""}]

            for c in data.get("class", []):
                vals.append({
                    "n": c.get("type_name", ""),
                    "v": c.get("type_id", "")
                })

            return key, vals

        # ---- s1~s32 API 源: class + 动态分类 ----
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = []

            for key, source in self.sources.items():
                classes.append({
                    "type_id": key,
                    "type_name": source["name"]
                })
                futures.append(executor.submit(load_class, key, source))

            for future in as_completed(futures):
                try:
                    key, vals = future.result()
                    filters[key] = [{
                        "key": "cateId",
                        "name": "分类",
                        "value": vals
                    }]
                except:
                    pass

        # ---- s33 毒舌影视 ----
        classes.append({"type_id": self.DUSHE_KEY, "type_name": self.DUSHE_NAME})
        filters[self.DUSHE_KEY] = [{
            "key": "cateId",
            "name": "分类",
            "value": [{"n": "全部(最新)", "v": ""}] + [
                {"n": n, "v": t} for n, t in self.dushe_classes_config
            ]
        }]

        # ---- s34 小蜜蜂影院 ----
        classes.append({"type_id": self.XMF_KEY, "type_name": self.XMF_NAME})
        filters[self.XMF_KEY] = [
            {"key": "type", "name": "类型", "value": [
                {"n": "全部", "v": ""},
                {"n": "连续剧", "v": "2"}, {"n": "电影", "v": "1"},
                {"n": "动漫", "v": "4"}, {"n": "综艺", "v": "3"},
            ]},
            {"key": "by", "name": "排序", "value": [
                {"n": "最新", "v": "time"}, {"n": "最热", "v": "hits"}, {"n": "评分", "v": "score"}]},
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
                {"n": "美国", "v": "美国"}, {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"},
                {"n": "英国", "v": "英国"}]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}]},
        ]

        # ---- s35 拾光影视 (动态分类) ----
        self._sg_ensure()
        sg_cats = [{"n": "全部(最新)", "v": ""}]
        for c in self.sg_classes:
            sg_cats.append({"n": c["type_name"], "v": c["type_id"]})

        classes.append({"type_id": self.SG_KEY, "type_name": self.SG_NAME})
        filters[self.SG_KEY] = [{
            "key": "cateId",
            "name": "分类",
            "value": sg_cats
        }]

        # ---- s36 王爷短视频 ----
        classes.append({"type_id": self.WY_KEY, "type_name": self.WY_NAME})
        filters[self.WY_KEY] = [{
            "key": "cateId",
            "name": "分类",
            "value": [{"n": n, "v": api} for n, api in self.wy_classes]
        }]

        # ---- 首页推荐列表: 毒舌首页 + 拾光首页 合并 ----
        vlist = []

        html = self.get_text(self.dushe_host, timeout=8, headers=self.dushe_headers)
        if html:
            vlist.extend(self.dushe_getlist(pq(html)('.mrb ul li, div.bt_img ul li')))

        sg_home = self.sg_home_videos()
        vlist.extend(sg_home)

        return {
            "class": classes,
            "filters": filters,
            "list": vlist
        }

    def homeVideoContent(self):
        """下拉刷新: 小蜜蜂推荐 (带5分钟缓存)"""
        return self.xmf_home_video()

    # ============================================================
    #  分类
    # ============================================================
    def categoryContent(self, tid, pg, filter, extend):
        if tid == self.DUSHE_KEY:
            return self.dushe_category(pg, extend)
        if tid == self.XMF_KEY:
            return self.xmf_category(pg, extend)
        if tid == self.SG_KEY:
            return self.sg_category(pg, extend)
        if tid == self.WY_KEY:
            return self.wy_category(pg, extend)

        if tid not in self.sources:
            return {"list": []}

        source = self.sources[tid]

        cate_id = ""
        if isinstance(extend, dict):
            cate_id = extend.get("cateId", "")

        url = f"{source['api']}?ac=detail&pg={pg}"

        if cate_id:
            url += f"&t={cate_id}"

        html = self.get_text(url)

        try:
            data = json.loads(html)
        except:
            data = {}

        result = []
        for item in data.get("list", []):
            result.append(self.clean_item(item, tid, source["name"], False))

        return {
            "list": result,
            "page": data.get("page", pg),
            "pagecount": data.get("pagecount", 1),
            "limit": data.get("limit", 20),
            "total": data.get("total", len(result))
        }

    # ============================================================
    #  详情
    # ============================================================
    def detailContent(self, ids):
        if isinstance(ids, list):
            ids = ids[0]

        if "@@" not in ids:
            return {"list": []}

        source_key, real_id = ids.split("@@", 1)

        if source_key == self.DUSHE_KEY:
            return self.dushe_detail(real_id)
        if source_key == self.XMF_KEY:
            return self.xmf_detail(real_id)
        if source_key == self.SG_KEY:
            return self.sg_detail(real_id)
        if source_key == self.WY_KEY:
            return self.wy_detail(real_id)

        if source_key not in self.sources:
            return {"list": []}

        source = self.sources[source_key]

        url = f"{source['api']}?ac=detail&ids={real_id}"
        html = self.get_text(url)

        try:
            data = json.loads(html)
        except:
            data = {}

        result = []
        for item in data.get("list", []):
            cleaned = self.clean_item(item, source_key, source["name"], True)
            cleaned["vod_id"] = ids
            result.append(cleaned)

        return {"list": result}

    # ============================================================
    #  搜索
    # ============================================================
    def searchContent(self, key, quick=False, pg=1):
        result = []
        max_page = 1

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []

            for source_key, source in self.sources.items():
                futures.append(executor.submit(self.search_one, source_key, source, key, pg))

            futures.append(executor.submit(self.dushe_search, key, pg))
            futures.append(executor.submit(self.xmf_search, key, pg))
            futures.append(executor.submit(self.sg_search, key, pg))

            for future in as_completed(futures):
                try:
                    data = future.result()
                    result.extend(data.get("list", []))
                    if data.get("pagecount", 1) > max_page:
                        max_page = data["pagecount"]
                except:
                    pass

        return {
            "list": result,
            "page": pg,
            "pagecount": max_page,
            "limit": 40,
            "total": 9999
        }

    def search_one(self, source_key, source, keyword, pg):
        url = f"{source['api']}?ac=detail&wd={quote(keyword)}&pg={pg}"
        html = self.get_text(url, 6)

        try:
            data = json.loads(html)
        except:
            data = {}

        result = []
        for item in data.get("list", []):
            result.append(self.clean_item(item, source_key, source["name"], False))

        return {
            "list": result,
            "pagecount": data.get("pagecount", 1)
        }

    # ============================================================
    #  播放
    # ============================================================
    def playerContent(self, flag, id, vipFlags):
        flag = str(flag or "")
        if '毒舌' in flag:
            return self.dushe_player(id)
        if '小蜜蜂' in flag:
            return self.xmf_player(id, vipFlags)
        if '拾光' in flag:
            return self.sg_player(id)
        if '王爷' in flag:
            return self.wy_player(id)

        # s1~s32 API 源: 接口直接返回可播地址
        return {
            "parse": 0,
            "playUrl": "",
            "url": id,
            "header": self.headers
        }

    def localProxy(self, param):
        return [200, "text/plain", "ok"]

    # ============================================================
    #  ============ s33 毒舌影视 实现 ============
    # ============================================================
    def dushe_category(self, pg, extend):
        cate_id = ""
        if isinstance(extend, dict):
            cate_id = extend.get("cateId", "")
        if not cate_id:
            cate_id = "1"

        url = f'{self.dushe_host}dsshiyisw/{cate_id}--------{pg}---.html'
        html = self.get_text(url, headers=self.dushe_headers)
        data = pq(html)

        videos = self.dushe_getlist(data('.mrb ul li, div.bt_img ul li'))

        return {
            'list': videos,
            'page': pg,
            'pagecount': 9999,
            'limit': 90,
            'total': 999999
        }

    def dushe_detail(self, vid):
        if vid.startswith('http'):
            url = vid
        else:
            if vid.startswith('/'):
                url = self.dushe_host.rstrip('/') + vid
            else:
                url = self.dushe_host.rstrip('/') + '/' + vid

        html = self.get_text(url, headers=self.dushe_headers)
        data = pq(html)

        name = data('h1').text()

        info_list = data('.moviedteail_list li')

        def li_text(idx):
            return info_list.eq(idx).text() if idx < len(info_list) else ''

        type_name = li_text(3)
        director = li_text(2)
        actor = li_text(1)
        remarks = li_text(6)
        year_or_area = li_text(4)

        pic = data('div.dyimg img').attr('src') or ''
        if pic and not pic.startswith('http'):
            if pic.startswith('/'):
                pic = self.dushe_host.rstrip('/') + pic
            else:
                pic = self.dushe_host.rstrip('/') + '/' + pic

        content = data('.yp_context').text()

        vod = {
            'vod_id': self.DUSHE_KEY + '@@' + vid,
            'vod_name': name,
            'vod_pic': pic,
            'type_name': type_name,
            'vod_year': year_or_area,
            'vod_area': '',
            'vod_remarks': remarks,
            'vod_actor': actor,
            'vod_director': director,
            'vod_content': content,
            'vod_play_from': '',
            'vod_play_url': ''
        }

        tabs = [i.text() for i in data('.mi_paly_box .ypxingq_t').items()]

        play_lists = []
        play_uls = list(data('.paly_list_btn').items())

        for ul in play_uls:
            items = []
            for i, a in enumerate(ul('a').items()):
                if i == 0:
                    continue
                title = a.text()
                href = a.attr('href') or ''
                if href and not href.startswith('http'):
                    if href.startswith('/'):
                        href = self.dushe_host.rstrip('/') + href
                    else:
                        href = self.dushe_host.rstrip('/') + '/' + href
                items.append(f'{title}${href}')
            play_lists.append('#'.join(items))

        vod['vod_play_from'] = '$$$'.join([f"{self.DUSHE_NAME}-{t}" for t in tabs])
        vod['vod_play_url'] = '$$$'.join(play_lists)

        return {'list': [vod]}

    def dushe_search(self, keyword, pg):
        url = f'{self.dushe_host}dsshiyisc/{quote(keyword)}----------{pg}---.html'
        html = self.get_text(url, headers=self.dushe_headers)
        data = pq(html)

        videos = self.dushe_getlist(data('.mrb ul li, div.bt_img ul li'))

        return {
            'list': videos,
            'pagecount': 1
        }

    def dushe_player(self, id):
        if id.startswith('http'):
            play_url = id
        else:
            if id.startswith('/'):
                play_url = self.dushe_host.rstrip('/') + id
            else:
                play_url = self.dushe_host.rstrip('/') + '/' + id

        p = 0

        if '.m3u8' in play_url:
            return {'parse': p, 'url': play_url, 'header': self.dushe_headers}

        html = self.get_text(play_url, headers=self.dushe_headers)

        m = re.search(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', html)
        if m:
            real = m.group(1).replace('\\/', '/')
            return {'parse': p, 'url': real, 'header': self.dushe_headers}

        return {'parse': p, 'url': play_url, 'header': self.dushe_headers}

    def dushe_getlist(self, data):
        vlist = []
        for j in data.items():
            name = j('.dytit').text()
            pic = j('.lazy').attr('data-original') or ''
            remark = j('.hdinfo').text()
            href = j('a').attr('href') or ''

            if pic and not pic.startswith('http'):
                if pic.startswith('/'):
                    pic = self.dushe_host.rstrip('/') + pic
                else:
                    pic = self.dushe_host.rstrip('/') + '/' + pic

            vlist.append({
                'vod_id': self.DUSHE_KEY + '@@' + href,
                'vod_name': name,
                'vod_pic': pic,
                'vod_remarks': remark
            })
        return vlist

    # ============================================================
    #  ============ s34 小蜜蜂影院 实现 ============
    # ============================================================
    def _probe_xmf_domain(self):
        for domain in self.XMF_DOMAINS:
            try:
                text = self.xmf_txt(domain, timeout=10)
                if text and len(text) > 500:
                    self.xmf_host = domain
                    self.xmf_header['Referer'] = self.xmf_host + '/'
                    return
            except Exception:
                continue

    def xmf_txt(self, url, referer=None, timeout=30):
        headers = dict(self.xmf_header)
        if referer:
            headers['Referer'] = referer
        try:
            rsp = self.fetch(url, headers=headers, timeout=timeout)
            if rsp is None:
                return ''
            try:
                rsp.encoding = 'utf-8'
            except Exception:
                pass
            return rsp.text
        except Exception:
            return ''

    def xmf_url(self, path):
        if not path:
            return ''
        if path.startswith('http'):
            return path
        if path.startswith('//'):
            return 'https:' + path
        if path.startswith('/'):
            return self.xmf_host + path
        return self.xmf_host + '/' + path

    @staticmethod
    def xmf_match(pattern, text, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else ''

    @staticmethod
    def xmf_strip_tags(html_text):
        if not html_text:
            return ''
        return re.sub(r'<[^>]+>', '', html_text).strip()

    def xmf_home_video(self):
        now = int(time.time())
        if self._xmf_home_cache and now - self._xmf_home_cache_time < 300:
            return {'list': self._xmf_home_cache[:72]}

        videos = []
        seen = set()

        for tid in ['1', '2', '3', '4']:
            url = f'{self.xmf_host}/index.php/vod/type/id/{tid}.html'
            html = self.xmf_txt(url, timeout=12)
            for v in self.xmf_parse_video_list(html):
                vid = v.get('vod_id')
                if vid and vid not in seen:
                    seen.add(vid)
                    v['vod_id'] = f"{self.XMF_KEY}@@{vid}"
                    videos.append(v)
                if len(videos) >= 72:
                    break
            if len(videos) >= 72:
                break

        self._xmf_home_cache = videos[:72]
        self._xmf_home_cache_time = now
        return {'list': self._xmf_home_cache}

    def xmf_category(self, pg, extend):
        try:
            pg = int(pg or 1)
            ext = {}
            if extend:
                if isinstance(extend, dict):
                    ext = extend
                elif isinstance(extend, str):
                    try:
                        ext = json.loads(extend)
                    except Exception:
                        ext = {}

            sub_type = ext.get('type', '')
            sort_by = ext.get('by', '')
            area = ext.get('area', '')
            year = ext.get('year', '')

            query_type = sub_type if sub_type else '1'

            if sort_by or area or year:
                url = f'{self.xmf_host}/index.php/vod/show/id/{query_type}'
                if sort_by:
                    url += f'/by/{sort_by}'
                if area:
                    url += f'/area/{area}'
                if year:
                    url += f'/year/{year}'
                url += f'/page/{pg}.html'
            else:
                url = f'{self.xmf_host}/index.php/vod/type/id/{query_type}/page/{pg}.html'

            html = self.xmf_txt(url, timeout=15)
            videos = self.xmf_parse_video_list(html)
            videos = [dict(v, vod_id=f"{self.XMF_KEY}@@{v['vod_id']}") for v in videos]

            pagecount = self.xmf_parse_pagecount(html, pg)

            return {
                'list': videos,
                'page': pg,
                'pagecount': pagecount,
                'limit': 20,
                'total': pagecount * 20,
            }
        except Exception:
            return {
                'page': int(pg or 1),
                'pagecount': 1,
                'limit': 20,
                'total': 0,
                'list': [],
            }

    def xmf_parse_pagecount(self, html, pg):
        page_nums = re.findall(r'/page/(\d+)\.html', html)
        if page_nums:
            return max(int(p) for p in page_nums)
        return pg

    def xmf_parse_video_list(self, html):
        videos = []
        if not html:
            return videos

        main_sections = re.findall(
            r'<div\s+class="hl-list-wrap[^"]*">\s*<ul\s+class="hl-vod-list[^"]*">(.*?)</ul>',
            html, re.S
        )
        if main_sections:
            seen_ids = set()
            for section in main_sections:
                items = re.findall(r'<li\s+class="hl-list-item[^"]*">(.*?)</li>', section, re.S)
                for item in items:
                    video = self.xmf_parse_video_card(item)
                    if video and video['vod_id'] not in seen_ids:
                        seen_ids.add(video['vod_id'])
                        videos.append(video)
            if videos:
                return videos

        items = re.findall(r'<li\s+class="hl-list-item[^"]*">(.*?)</li>', html, re.S)
        seen_ids = set()
        for item in items:
            video = self.xmf_parse_video_card(item)
            if video and video['vod_id'] not in seen_ids:
                seen_ids.add(video['vod_id'])
                videos.append(video)
        return videos

    def xmf_parse_video_card(self, html):
        href_match = re.search(r'href="(/index\.php/vod/detail/id/(\d+)\.html)"', html)
        if not href_match:
            return None
        vod_id = href_match.group(2)

        pic = ''
        pic_match = re.search(r'data-original="([^"]+)"', html)
        if pic_match:
            pic = pic_match.group(1)
        if not pic:
            bg_match = re.search(r'background-image:\s*url\([\'"]?([^\'"()]+)', html)
            if bg_match:
                pic = bg_match.group(1)
        if pic and pic.startswith('//'):
            pic = 'https:' + pic

        title = ''
        title_match = re.search(r'class="hl-item-title[^"]*"[^>]*>[^<]*<a[^>]*title="([^"]+)"', html)
        if title_match:
            title = title_match.group(1).strip()
        if not title:
            title_match2 = re.search(r'title="([^"]+)"', html)
            if title_match2:
                title = title_match2.group(1).strip()

        remarks = ''
        remarks_match = re.search(
            r'class="hl-pic-text[^"]*"[^>]*>.*?<span[^>]*class="remarks"[^>]*>([^<]+)', html, re.S)
        if remarks_match:
            remarks = remarks_match.group(1).strip()
        if not remarks:
            remarks_match2 = re.search(r'class="remarks"[^>]*>([^<]+)', html)
            if remarks_match2:
                remarks = remarks_match2.group(1).strip()

        return {
            'vod_id': vod_id,
            'vod_name': title or vod_id,
            'vod_pic': pic,
            'vod_remarks': remarks,
        }

    def xmf_detail(self, real_id):
        url = f'{self.xmf_host}/index.php/vod/detail/id/{real_id}.html'
        html = self.xmf_txt(url, timeout=15)
        if not html:
            return {'list': []}

        vod = self.xmf_parse_detail(html, real_id)
        if vod:
            vod['vod_id'] = f"{self.XMF_KEY}@@{real_id}"
        return {'list': [vod] if vod else []}

    def xmf_parse_detail(self, html, vod_id):
        title = self.xmf_match(r'<h2\s+class="hl-dc-title[^"]*"[^>]*>([^<]+)', html)
        if not title:
            title = self.xmf_match(r'<title>([^<|-]+)', html)
            if title:
                title = title.strip()

        pic = ''
        pic_match = re.search(r'class="hl-dc-pic".*?data-original="([^"]+)"', html, re.S)
        if pic_match:
            pic = pic_match.group(1)
        if not pic:
            pic_match2 = re.search(r'class="hl-item-thumb[^"]*"[^>]*data-original="([^"]+)"', html)
            if pic_match2:
                pic = pic_match2.group(1)
        if pic and pic.startswith('//'):
            pic = 'https:' + pic

        info_items = re.findall(r'<em\s+class="hl-text-muted">([^<：:]+)[：:]?</em>(.*?)</li>', html, re.S)
        actor, director, area, year, type_name, remarks, content = '', '', '', '', '', '', ''

        for label, content_html in info_items:
            label = label.strip()
            text = self.xmf_strip_tags(content_html).strip()
            if '主演' in label:
                actor = text
            elif '导演' in label:
                director = text
            elif '地区' in label:
                area = text
            elif '年份' in label:
                year = text
            elif '类型' in label:
                type_name = text
            elif '状态' in label:
                remarks = text
            elif '简介' in label:
                content = text

        if not content:
            content = self.xmf_match(
                r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)', html)

        play_from, play_url = self.xmf_parse_playlist(html, vod_id)

        return {
            'vod_id': vod_id,
            'vod_name': title or vod_id,
            'vod_pic': pic,
            'type_name': type_name,
            'vod_year': year,
            'vod_area': area,
            'vod_remarks': remarks,
            'vod_actor': actor,
            'vod_director': director,
            'vod_content': content[:500] if content else '',
            'vod_play_from': '$$$'.join(play_from),
            'vod_play_url': '$$$'.join(play_url),
        }

    def xmf_parse_playlist(self, html, vod_id):
        play_from = []
        play_url = []

        source_items = re.findall(r'<a\s+class="hl-tabs-btn[^"]*"[^>]*alt="([^"]+)"', html)
        source_names = [s.strip() for s in source_items]

        if not source_names:
            play_links = re.findall(r'href="(/index\.php/vod/play/id/\d+/sid/\d+/nid/\d+\.html)"', html)
            if play_links:
                episodes = []
                seen_eps = set()
                for link in play_links:
                    if link not in seen_eps:
                        seen_eps.add(link)
                        nid_match = re.search(r'/nid/(\d+)\.html', link)
                        ep_name = f'第{nid_match.group(1)}集' if nid_match else '播放'
                        episodes.append(f'{ep_name}${self.xmf_url(link)}')
                if episodes:
                    play_from.append('小蜜蜂-默认线路')
                    play_url.append('#'.join(episodes))
            return play_from, play_url

        play_items_raw = re.split(r'class="hl-plays-list', html)
        play_items = play_items_raw[1:] if len(play_items_raw) > 1 else []

        for idx, source_name in enumerate(source_names):
            if any(kw in source_name.lower() for kw in self.XMF_SKIP_KEYWORDS):
                continue

            episodes = []
            if idx < len(play_items):
                item_html = play_items[idx]
                ep_links = re.findall(
                    r'<a\s+href="(/index\.php/vod/play/id/\d+/sid/(\d+)/nid/(\d+)\.html)"[^>]*>([^<]*)</a>',
                    item_html)
                for link, sid, nid, ep_name in ep_links:
                    ep_name = self.xmf_strip_tags(ep_name).strip()
                    if not ep_name:
                        ep_name = f'第{nid}集'
                    elif not ep_name.startswith('第') and ep_name.isdigit():
                        ep_name = f'第{ep_name}集'
                    episodes.append(f'{ep_name}${self.xmf_url(link)}')

            if episodes:
                play_from.append(f'小蜜蜂-{source_name}')
                play_url.append('#'.join(episodes))

        return play_from, play_url

    def xmf_search(self, key, pg):
        try:
            pg = int(pg or 1)
            url = f'{self.xmf_host}/index.php/vod/search/page/{pg}/wd/{quote(key, safe="")}.html'
            html = self.xmf_txt(url, timeout=15)
            videos = self.xmf_parse_video_list(html)
            return {
                'list': [dict(v, vod_id=f"{self.XMF_KEY}@@{v['vod_id']}") for v in videos],
                'pagecount': 1,
            }
        except Exception:
            return {'list': [], 'pagecount': 1}

    def xmf_player(self, id, vipFlags):
        if not id:
            return {'parse': 1, 'playUrl': '', 'url': ''}

        url = id if str(id).startswith('http') else self.xmf_url(id)

        # 1. 直链检测
        if self.xmf_is_direct_media(url):
            return {
                'parse': 0, 'playUrl': '', 'url': url,
                'header': {'User-Agent': self.xmf_header['User-Agent'], 'Referer': self.xmf_host + '/'},
                'format': 'application/x-mpegURL' if '.m3u8' in url.lower() else '',
                'contentType': 'application/x-mpegURL' if '.m3u8' in url.lower() else '',
            }

        # 2. 官源解析
        if self.xmf_is_official_source(url):
            resolved = self.xmf_resolve_official_to_media(url)
            if resolved:
                return {
                    'parse': 0, 'playUrl': '', 'url': resolved,
                    'header': {'User-Agent': self.xmf_header['User-Agent'], 'Referer': 'https://bfq.txnp.cn/'},
                    'format': 'application/x-mpegURL' if '.m3u8' in resolved.lower() else '',
                    'contentType': 'application/x-mpegURL' if '.m3u8' in resolved.lower() else '',
                }

        # 3. 播放页解析
        html = self.xmf_txt(url, referer=self.xmf_host + '/', timeout=30)
        if not html:
            return {'parse': 1, 'playUrl': '', 'url': url}

        real = ''

        # 3a. player_aaaa JSON
        m = re.search(r'var\s+player_[a-zA-Z0-9_]+\s*=\s*(\{.*?\})\s*</script>', html, re.S)
        if not m:
            m = re.search(r'var\s+player_[a-zA-Z0-9_]+\s*=\s*(\{.*?\})', html, re.S)
        if m:
            try:
                raw = m.group(1)
                data = json.loads(raw)
                real = data.get('url', '') or ''
                encrypt = data.get('encrypt', 0)
                if encrypt in [1, 2] and real:
                    try:
                        real = base64.b64decode(real).decode('utf-8')
                    except Exception:
                        pass
                if real and not real.startswith('http') and not self.xmf_is_direct_media(real):
                    real = ''
            except Exception:
                real = self.xmf_match(r'"url"\s*:\s*"([^"]+)"', m.group(1))
                if real and not real.startswith('http'):
                    real = ''

        # 3b. iframe 嵌套
        if not real:
            iframe = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.S)
            if iframe:
                iframe_url = self.xmf_url(iframe.group(1))
                if self.xmf_is_direct_media(iframe_url):
                    real = iframe_url
                else:
                    iframe_html = self.xmf_txt(iframe_url, referer=url, timeout=30)
                    if iframe_html:
                        real = self.xmf_match(r'"url"\s*:\s*"(https?://[^"]+)"', iframe_html)

        # 3c. 全局匹配 m3u8/mp4
        if not real:
            m2 = re.search(r'["\'](https?://[^"\']+\.(?:m3u8|mp4)[^"\']*)["\']', html, re.I)
            if m2:
                real = m2.group(1)

        if real:
            real = real.replace('\\/', '/')
            is_m3u8 = '.m3u8' in real.lower()

            if self.xmf_is_direct_media(real):
                if is_m3u8:
                    real = self.xmf_resolve_m3u8_child(real, referer=url)
                return {
                    'parse': 0, 'playUrl': '', 'url': real,
                    'header': {'User-Agent': self.xmf_header['User-Agent'], 'Referer': url},
                    'format': 'application/x-mpegURL' if is_m3u8 else '',
                    'contentType': 'application/x-mpegURL' if is_m3u8 else '',
                }

            if self.xmf_is_official_source(real):
                resolved = self.xmf_resolve_official_to_media(real)
                if resolved:
                    return {
                        'parse': 0, 'playUrl': '', 'url': resolved,
                        'header': {'User-Agent': self.xmf_header['User-Agent'], 'Referer': 'https://bfq.txnp.cn/'},
                        'format': 'application/x-mpegURL' if '.m3u8' in resolved.lower() else '',
                        'contentType': 'application/x-mpegURL' if '.m3u8' in resolved.lower() else '',
                    }

        return {'parse': 1, 'playUrl': '', 'url': url}

    def xmf_is_direct_media(self, url):
        url = (url or '').lower()
        return '.m3u8' in url or '.mp4' in url or '.flv' in url or '.mkv' in url

    def xmf_is_official_source(self, url):
        url = (url or '').lower()
        keys = (
            'mgtv.com', 'youku.com', 'iqiyi.com', 'qiyi.com',
            'v.qq.com', 'qq.com', 'bilibili.com', 'le.com',
            'sohu.com', 'pptv.com', '1905.com',
        )
        return any(k in url for k in keys) and not self.xmf_is_direct_media(url)

    def xmf_aes_cbc_decrypt_text(self, cipher_text):
        try:
            from Crypto.Cipher import AES
            key = cipher_text[-32:-16].encode('utf-8')
            iv = cipher_text[-16:].encode('utf-8')
            data = base64.b64decode(cipher_text[:-32])
            raw = AES.new(key, AES.MODE_CBC, iv).decrypt(data)
            pad = raw[-1] if raw else 0
            if 0 < pad <= 16:
                raw = raw[:-pad]
            return raw.decode('utf-8', 'ignore')
        except Exception:
            return ''

    def xmf_decode_bfq_result(self, result):
        text = self.xmf_aes_cbc_decrypt_text(result or '')
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return {}

    def xmf_resolve_official_to_media(self, src_url):
        if not src_url or not self.xmf_is_official_source(src_url):
            return ''
        try:
            page_url = 'https://bfq.txnp.cn/player?url=' + quote(src_url, safe='')
            referer = 'https://bfq.txnp.cn/excessive?url=' + quote(src_url, safe='')
            html = self.xmf_txt(page_url, referer=referer, timeout=20)
            if not html:
                return ''
            result = self.xmf_match(r'let\s+result\s*=\s*"([^"]+)"', html, re.S)
            if not result:
                return ''
            data = self.xmf_decode_bfq_result(result)
            video = ((data.get('video_info') or {}).get('video') or {})
            media = (video.get('url') or '').replace('\\/', '/')
            if media and self.xmf_is_direct_media(media):
                if re.match(r'https://\d+\.\d+\.\d+\.\d+:\d+', media):
                    media = media.replace('https://', 'http://', 1)
                if '.m3u8' in media.lower():
                    media = self.xmf_resolve_m3u8_child(media, referer=page_url)
                return media
        except Exception:
            pass
        return ''

    def xmf_resolve_m3u8_child(self, m3u8_url, referer=''):
        try:
            text = self.xmf_txt(m3u8_url, referer=referer or self.xmf_host + '/', timeout=20)
            if not text or '#EXTM3U' not in text:
                return m3u8_url
            lines = [x.strip() for x in text.splitlines() if x.strip()]
            for i, line in enumerate(lines):
                if line.startswith('#EXT-X-STREAM-INF'):
                    for nxt in lines[i + 1:]:
                        if nxt and not nxt.startswith('#'):
                            return urljoin(m3u8_url, nxt)
        except Exception:
            pass
        return m3u8_url


    # ============================================================
    #  ============ s35 拾光影视 实现 ============
    # ============================================================
    def _sg_ensure(self):
        """懒加载: 拉取配置+首页缓存 (带1小时缓存)"""
        if self.sg_ready:
            return
        config = self.sg_get_json('/api/proxy.php?action=config')
        if config and config.get('success'):
            self.sg_sources = config.get('sources', {}) or {}
            for key, src in self.sg_sources.items():
                self.sg_player_api_map[key] = src.get('player_api', 'local')
        self._sg_refresh_home()
        self.sg_ready = True

    def _sg_refresh_home(self):
        now = time.time()
        if self.sg_home_cache is not None and (now - self.sg_home_cache_time) < self.sg_home_cache_ttl:
            return
        home = self.sg_get_json('/api/proxy.php?action=home')
        if home and home.get('success'):
            self.sg_home_cache = home
            self.sg_home_cache_time = now
            categories = home.get('categories', {}) or {}
            self.sg_classes = []
            for cat_name in categories.keys():
                self.sg_classes.append({
                    'type_id': cat_name,
                    'type_name': cat_name,
                })

    def sg_get_json(self, path):
        """拾光 API GET 请求返回 JSON"""
        try:
            url = self.sg_host + path
            for attempt in range(2):
                try:
                    r = requests.get(url, headers=self.sg_headers, timeout=self.sg_timeout)
                    if r.status_code == 200:
                        ct = r.headers.get('Content-Type', '')
                        if 'json' in ct or r.text.strip().startswith('{'):
                            return r.json()
                        return None
                    if r.status_code == 403 and attempt == 0:
                        time.sleep(1)
                        continue
                except Exception:
                    if attempt == 0:
                        time.sleep(1)
                        continue
        except Exception:
            pass
        return None

    @staticmethod
    def sg_safe_text(value):
        if value is None:
            return ''
        if isinstance(value, dict):
            text = value.get('p', '') or str(value)
        else:
            text = str(value)
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('\xa0', ' ')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def sg_parse_video(self, item):
        source = item.get('source', '') or ''
        vid = str(item.get('id', ''))
        return {
            'vod_id': self.SG_KEY + '@@' + source + '___' + vid,
            'vod_name': item.get('name', ''),
            'vod_pic': item.get('pic', ''),
            'vod_remarks': item.get('remarks', ''),
        }

    def sg_home_videos(self):
        """从首页缓存提取视频列表 (带前缀)"""
        self._sg_ensure()
        videos = []
        seen = set()
        if self.sg_home_cache:
            categories = self.sg_home_cache.get('categories', {}) or {}
            for cat_name, cat_videos in categories.items():
                for v in cat_videos or []:
                    vid = v.get('source', '') + '___' + str(v.get('id', ''))
                    if vid not in seen:
                        seen.add(vid)
                        videos.append(self.sg_parse_video(v))
        return videos[:50]

    def sg_category(self, pg, extend):
        self._sg_ensure()
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1

        cate = ''
        if isinstance(extend, dict):
            cate = extend.get('cateId', '')
        if not cate and self.sg_classes:
            cate = self.sg_classes[0]['type_id']

        if page == 1:
            videos = []
            seen = set()
            if self.sg_home_cache:
                categories = self.sg_home_cache.get('categories', {}) or {}
                for v in categories.get(cate, []) or []:
                    vid = v.get('source', '') + '___' + str(v.get('id', ''))
                    if vid not in seen:
                        seen.add(vid)
                        videos.append(self.sg_parse_video(v))
            return {
                'list': videos,
                'page': 1,
                'pagecount': 1,
                'limit': len(videos),
                'total': len(videos),
            }
        else:
            search = self.sg_get_json(
                '/api/proxy.php?action=search&wd='
                + urllib.parse.quote(cate)
                + '&page='
                + str(page)
            )
            videos = []
            pagecount = 1
            total = 0
            if search and search.get('success'):
                results = search.get('results', []) or []
                total = search.get('total', 0)
                pagecount = max(1, (int(total) + 19) // 20)
                seen = set()
                for v in results:
                    vid = v.get('source', '') + '___' + str(v.get('id', ''))
                    if vid not in seen:
                        seen.add(vid)
                        videos.append(self.sg_parse_video(v))
            return {
                'list': videos,
                'page': page,
                'pagecount': pagecount,
                'limit': len(videos),
                'total': total,
            }

    def sg_search(self, key, pg):
        keyword = self.sg_safe_text(key)
        if not keyword:
            return {'list': [], 'pagecount': 1}
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1

        search = self.sg_get_json(
            '/api/proxy.php?action=search&wd='
            + urllib.parse.quote(keyword)
            + '&page='
            + str(page)
        )
        videos = []
        if search and search.get('success'):
            seen = set()
            for v in search.get('results', []) or []:
                vid = v.get('source', '') + '___' + str(v.get('id', ''))
                if vid not in seen:
                    seen.add(vid)
                    videos.append(self.sg_parse_video(v))
        return {'list': videos, 'pagecount': 1}

    def sg_detail(self, real_id):
        parts = real_id.split('___', 1)
        if len(parts) == 2:
            source, vid = parts
        else:
            source = 'qilin'
            vid = real_id

        detail = self.sg_get_json(
            '/api/proxy.php?action=detail&source='
            + urllib.parse.quote(source)
            + '&id='
            + urllib.parse.quote(str(vid))
        )
        if not detail or not detail.get('success'):
            return {'list': []}

        details = detail.get('details', [])
        if not details:
            return {'list': []}

        d = details[0]

        vod_name = d.get('name', '')
        vod_pic = d.get('pic', '')
        vod_year = str(d.get('year', ''))
        vod_area = d.get('area', '')
        vod_type = d.get('type', '')
        vod_actor = d.get('actor', '')
        vod_director = d.get('director', '')
        vod_remarks = d.get('remarks', '')
        vod_content = self.sg_safe_text(d.get('content', ''))

        episodes = d.get('episodes', []) or []
        play_from_parts = []
        play_url_parts = []

        for gi, group in enumerate(episodes):
            group_name = group.get('group', '线路' + str(gi + 1))
            play_from_parts.append(f'{self.SG_NAME}-{group_name}')

            eps = group.get('episodes', []) or []
            ep_urls = []
            for ei, ep in enumerate(eps):
                ep_name = ep.get('name', str(ei + 1))
                ep_id = source + '___' + str(vid) + '___' + str(gi) + '___' + str(ei)
                ep_urls.append(str(ep_name) + '$' + ep_id)
            if ep_urls:
                play_url_parts.append('#'.join(ep_urls))

        play_from = '$$$'.join(play_from_parts) if play_from_parts else self.SG_NAME
        play_url = '$$$'.join(play_url_parts) if play_url_parts else ''

        result = {
            'vod_id': self.SG_KEY + '@@' + real_id,
            'vod_name': vod_name,
            'vod_pic': vod_pic,
            'vod_remarks': vod_remarks,
            'vod_year': vod_year,
            'vod_area': vod_area,
            'vod_type': vod_type,
            'vod_actor': vod_actor,
            'vod_director': vod_director,
            'vod_content': vod_content,
            'vod_play_from': play_from,
            'vod_play_url': play_url,
        }

        return {'list': [result]}

    def sg_player(self, vid):
        """播放解析: vid 格式 source___vod_id___group_index___episode_index"""
        if not vid:
            return {}

        vid = str(vid).strip()
        if vid.startswith(self.SG_KEY + '@@'):
            vid = vid[len(self.SG_KEY) + 2:]

        parts = vid.split('___')
        if len(parts) != 4:
            if vid.startswith('http'):
                return {
                    'parse': 0,
                    'url': vid,
                    'header': {
                        'User-Agent': self.sg_headers['User-Agent'],
                        'Referer': self.sg_host + '/',
                    },
                }
            return {}

        source, vod_id, group_index, ep_index = parts

        detail = self.sg_get_json(
            '/api/proxy.php?action=detail&source='
            + urllib.parse.quote(source)
            + '&id='
            + urllib.parse.quote(vod_id)
        )
        if not detail or not detail.get('success'):
            return {}

        details = detail.get('details', [])
        if not details:
            return {}

        d = details[0]
        episodes = d.get('episodes', []) or []

        try:
            gi = int(group_index)
            ei = int(ep_index)
        except (ValueError, TypeError):
            return {}

        if gi >= len(episodes):
            return {}

        eps = episodes[gi].get('episodes', []) or []
        if ei >= len(eps):
            return {}

        ep_url = eps[ei].get('url', '')
        if not ep_url:
            return {}

        if self.isVideoFormat(ep_url):
            return {
                'parse': 0,
                'url': ep_url,
                'header': {
                    'User-Agent': self.sg_headers['User-Agent'],
                    'Referer': self.sg_host + '/',
                },
            }
        else:
            player_api = self.sg_player_api_map.get(source, '')
            if player_api and player_api != 'local':
                resolved = self._sg_resolve_via_player_api(player_api, ep_url)
                if resolved:
                    return {
                        'parse': 0,
                        'url': resolved,
                        'header': {
                            'User-Agent': self.sg_headers['User-Agent'],
                            'Referer': self.sg_host + '/',
                        },
                    }
                return {'parse': 1, 'playUrl': '', 'url': ep_url}
            else:
                return {
                    'parse': 0,
                    'url': ep_url,
                    'header': {
                        'User-Agent': self.sg_headers['User-Agent'],
                        'Referer': self.sg_host + '/',
                    },
                }

    def _sg_resolve_via_player_api(self, player_api, platform_url):
        """通过 player_api 的 resolve.php 解析平台链接为真实视频 URL"""
        try:
            player_page_url = player_api + platform_url
            r = requests.get(
                player_page_url,
                headers={**self.sg_headers, 'Referer': self.sg_host + '/'},
                timeout=self.sg_timeout,
            )
            if r.status_code != 200:
                return None

            token_match = re.search(
                r'apiToken["\']?\s*:\s*["\']([^"\']+)["\']', r.text)
            if not token_match:
                return None

            api_token = token_match.group(1)

            parsed = urllib.parse.urlparse(player_api)
            api_base = parsed.scheme + '://' + parsed.netloc
            resolve_url = api_base + '/api/resolve.php?token=' + urllib.parse.quote(api_token)

            r2 = requests.get(
                resolve_url,
                headers={**self.sg_headers, 'Referer': player_page_url},
                timeout=self.sg_timeout,
            )
            if r2.status_code != 200:
                return None

            data = r2.json()
            if data.get('code') != 200:
                return None

            video_url = data.get('url', '')
            if video_url:
                return video_url
        except Exception:
            pass

        return None


    # ============================================================
    #  ============ s36 王爷短视频 实现 ============
    # ============================================================
    def wy_category(self, pg, extend):
        videos = []
        pg_int = int(pg) if pg else 1

        api_url = ""
        if isinstance(extend, dict):
            api_url = extend.get("cateId", "")
        if not api_url:
            api_url = self.wy_classes[0][1]

        for i in range(20):
            videos.append({
                "vod_id": f"{self.WY_KEY}@@{api_url}",
                "vod_name": f"王爷专线 {pg_int}-{i+1}",
                "vod_pic": "https://t.mwm.moe/mp/",
                "vod_remarks": "",
                "style": {"type": "rect", "ratio": 0.56},
                "vod_player": "short"
            })

        return {'list': videos, 'page': pg_int, 'pagecount': 9999, 'limit': 20, 'total': 999999}

    def wy_detail(self, api_url):
        play_list = []
        session_id = str(int(time.time()))[-4:]
        rand_salt = str(random.randint(1000000, 9999999))

        for i in range(80):
            title = f"{i+1}.王爷随机 🕒{session_id}"
            full_api = f"{api_url}?type=json"
            # 前缀不用 $ 符号, 避免部分播放器按 $ 拆分播放地址时截断
            play_list.append(f"{title}$s36play{full_api}@@{rand_salt}_{i}")

        vod = {
            "vod_id": f"{self.WY_KEY}_{rand_salt}",
            "vod_name": "快活王爷",
            "vod_pic": "https://t.mwm.moe/mp/",
            "vod_play_from": "王爷引擎",
            "vod_play_url": "#".join(play_list),
            "vod_player": "short"
        }
        return {'list': [vod]}

    def wy_player(self, id):
        if str(id).startswith('s36play'):
            api_url = str(id)[len('s36play'):].split('@@')[0]

            try:
                r = requests.get(api_url, headers=self.headers, timeout=10).json()

                video_url = r.get('data') or r.get('url') or r.get('video') or r.get('msg')
                if isinstance(video_url, dict):
                    video_url = video_url.get('url') or video_url.get('video') or video_url.get('data')

                if video_url and str(video_url).startswith('http'):
                    return {'parse': 0, 'url': video_url, 'vod_player': 'short', 'header': self.headers}
            except Exception:
                pass

            return {"parse": 0, "url": "toast://获取视频失败,请上滑重试", "header": ""}

        return {"parse": 0, "url": id, "header": self.headers}


if __name__ == "__main__":
    Spider().run()

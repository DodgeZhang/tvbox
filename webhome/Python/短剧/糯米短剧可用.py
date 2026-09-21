#!/usr/bin/env python3
# coding=utf-8
# !/usr/bin/python
"""
糯米短剧 —— TVBox / 影视仓 Python 爬虫 (T4 py)
作者  : 无名之辈
群号  : 807916734
功能  : 首页推荐 / 分类浏览+翻页 / 搜索 / 详情选集 / 播放解析(m3u8)
依赖  : requests
站点  : https://8728.mrsvj.com/
"""

import json
import re
import sys
import time

sys.path.append('..')

# ---- TVBox 运行环境提供 base.spider; 本地调试时降级为空基类 ----
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

try:
    import requests
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

API_HOST = "https://4gf56465fg112.hongjiuchang.com/api/web/v1"
FALLBACK_STATIC_DOMAIN = "https://E0a5z7.ws4ge.com"
FALLBACK_VIDEO_DOMAIN = "https://666996.drephjq.com"

TAG_MAP = {
    15: "都市", 16: "爱情", 17: "复仇", 18: "豪门", 19: "甜宠",
    20: "情感", 21: "家庭", 22: "悬疑", 23: "总裁", 24: "励志",
    25: "奇幻", 26: "婚姻", 27: "玄幻", 28: "权谋", 29: "重生",
    30: "搞笑", 31: "穿越", 32: "热血", 33: "宫廷", 34: "赘婿",
    35: "逆袭", 36: "职场", 39: "动作", 40: "古装", 42: "宿命",
    54: "科幻", 55: "恐怖", 56: "惊悚", 57: "灵异", 60: "离婚",
}


class Spider(BaseSpider):
    # ==================== 生命周期 ====================
    def init(self, extend=""):
        self._static_domain = None
        self._video_domain = None
        self.timeout = 15
        self.page_size = 24
        return self

    def getName(self):
        return '糯米短剧'

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|mkv|flv|avi|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return ''

    def localProxy(self, param):
        return [200, "video/MP2T", {}, None]

    # ==================== 网络 ====================
    def _headers(self):
        return {
            'User-Agent': UA,
            'Content-Type': 'application/json;charset=utf-8',
            'Origin': 'https://8728.mrsvj.com',
            'Referer': 'https://8728.mrsvj.com/',
        }

    def _post(self, url, data=None):
        """POST JSON 请求封装"""
        if not HAS_REQUESTS:
            return None
        try:
            resp = requests.post(
                url,
                json=data or {},
                headers=self._headers(),
                timeout=self.timeout
            )
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception as e:
            print(f"[{self.getName()}] POST请求异常: {e}")
            return None

    # ==================== 域名工具 ====================
    def _load_domains(self):
        """从 config/load 动态获取资源域名（封面/播放）"""
        if self._static_domain and self._video_domain:
            return
        try:
            data = self._post(f"{API_HOST}/config/load")
            config = (data or {}).get("data", {}).get("config", {})
            self._static_domain = config.get("static_domain") or FALLBACK_STATIC_DOMAIN
            self._video_domain = config.get("video_domain") or FALLBACK_VIDEO_DOMAIN
            if self._static_domain.endswith("/"):
                self._static_domain = self._static_domain.rstrip("/")
            if self._video_domain.endswith("/"):
                self._video_domain = self._video_domain.rstrip("/")
        except Exception as e:
            print(f"[{self.getName()}] 域名加载异常: {e}")
            self._static_domain = FALLBACK_STATIC_DOMAIN
            self._video_domain = FALLBACK_VIDEO_DOMAIN

    def _build_cover(self, path):
        """拼接封面完整 URL"""
        if not path:
            return ""
        if path.startswith("http"):
            return path
        self._load_domains()
        return f"{self._static_domain}{path}" if path.startswith("/") else f"{self._static_domain}/{path}"

    def _build_video_url(self, path):
        """拼接播放完整 URL"""
        if not path:
            return ""
        if path.startswith("http"):
            return path
        self._load_domains()
        return f"{self._video_domain}/{path.lstrip('/')}"

    def _build_vod_item(self, raw):
        """标准化影片条目"""
        tags = raw.get("tags", "")
        tag_names = []
        if tags:
            for t in str(tags).split(","):
                try:
                    tag_names.append(TAG_MAP.get(int(t), ""))
                except ValueError:
                    pass
        tag_names = [x for x in tag_names if x]

        remarks = f"共{raw.get('sets', 0)}集"
        if str(raw.get("is_vip", "0")) == "1":
            remarks += " VIP"

        return {
            "vod_id": str(raw.get("id", "")),
            "vod_name": raw.get("title", ""),
            "vod_pic": self._build_cover(raw.get("cover", "")),
            "vod_remarks": remarks,
            "vod_year": "",
            "vod_area": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_type": "/".join(tag_names) if tag_names else "",
            "vod_score": "",
        }

    # ==================== 首页 ====================
    def homeContent(self, filter):
        cats = [
            {'type_id': 'new', 'type_name': '新剧'},
            {'type_id': 'vip', 'type_name': 'VIP专享'},
            {'type_id': 'slide', 'type_name': '推荐'},
        ]
        for _tid, _tname in TAG_MAP.items():
            cats.append({'type_id': f'tag:{_tid}', 'type_name': _tname})

        # 该站点 API 不支持多维筛选，filters 留空
        return {'class': cats, 'filters': {}}

    def homeVideoContent(self):
        """首页推荐视频"""
        try:
            data = self._post(f"{API_HOST}/video/slide", {"pageNum": 1})
            items = (data or {}).get("data", {}).get("list", [])
            return {'list': [self._build_vod_item(item) for item in items]}
        except Exception as e:
            print(f"[{self.getName()}] 首页推荐异常: {e}")
            return {'list': []}

    # ==================== 分类列表 ====================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1

        result = {
            'list': [],
            'page': pg,
            'pagecount': 0,
            'limit': self.page_size,
            'total': 0
        }

        try:
            params = {"pageNum": pg}
            tid = str(tid)

            if tid.startswith("tag:"):
                params["tag"] = int(tid.split(":", 1)[1])
            elif tid == "new":
                params["type"] = "new"
            elif tid == "vip":
                params["type"] = "vip"
            elif tid == "slide":
                data = self._post(f"{API_HOST}/video/slide", params)
                items = (data or {}).get("data", {}).get("list", [])
                result['list'] = [self._build_vod_item(item) for item in items]
                result['pagecount'] = 1
                result['total'] = len(items)
                return result
            else:
                # 数字分类 ID：优先当作 tag 处理
                params["tag"] = int(tid)

            data = self._post(f"{API_HOST}/video/list", params)
            d = (data or {}).get("data", {})
            items = d.get("list", [])
            result['list'] = [self._build_vod_item(item) for item in items]

            total = d.get("total", 0)
            page_size = d.get("pageSize", self.page_size) or self.page_size
            result['total'] = total
            result['pagecount'] = (total + page_size - 1) // page_size if total else 1
            result['page'] = pg
            result['limit'] = page_size
        except Exception as e:
            print(f"[{self.getName()}] 分类列表异常: {e}")
        return result

    # ==================== 详情 / 选集 ====================
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) else ids
        vid = str(vid).strip()
        if not vid:
            return {'list': []}

        try:
            data = self._post(f"{API_HOST}/video/detail-info", {"id": vid})
            if not data:
                return {'list': []}
            info = data.get("data", {}).get("info", {})
            if not info:
                return {'list': []}

            # 标签名
            tags = info.get("tags", "")
            tag_names = []
            if tags:
                for t in str(tags).split(","):
                    try:
                        tag_names.append(TAG_MAP.get(int(t), ""))
                    except ValueError:
                        pass
            tag_names = [x for x in tag_names if x]

            # 播放集数
            set_list = info.get("setList", [])
            ep_parts = []
            for ep in set_list:
                idx = ep.get("i", len(ep_parts) + 1)
                ep_name = f"第{idx}集"
                # 播放地址用 视频ID|集数 复合ID，playerContent 中二次解析
                ep_url = f"{vid}|{idx}"
                ep_parts.append(f"{ep_name}${ep_url}")

            vod = {
                "vod_id": str(info.get("id", vid)),
                "vod_name": info.get("title", ""),
                "vod_pic": self._build_cover(info.get("cover", "")),
                "vod_year": "",
                "vod_area": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_type": "/".join(tag_names) if tag_names else "",
                "vod_remarks": f"共{info.get('sets', 0)}集" + (" VIP" if str(info.get("is_vip", "0")) == "1" else ""),
                "vod_content": info.get("summary", ""),
                "vod_play_from": "糯米短剧",
                "vod_play_url": "#".join(ep_parts),
            }
            return {'list': [vod]}
        except Exception as e:
            print(f"[{self.getName()}] 详情获取异常: {e}")
            return {'list': []}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1

        result = {
            'list': [],
            'page': pg,
            'pagecount': 0,
            'limit': self.page_size,
            'total': 0
        }

        key = str(key).strip()
        if not key or len(key) < 2:
            return result

        try:
            data = self._post(f"{API_HOST}/search/list", {
                "pageNum": pg,
                "text": key,
                "plat": "pc"
            })
            d = (data or {}).get("data", {})
            items = d.get("list", [])
            result['list'] = [self._build_vod_item(item) for item in items]
            total = d.get("total", 0)
            page_size = d.get("pageSize", self.page_size) or self.page_size
            result['total'] = total
            result['pagecount'] = (total + page_size - 1) // page_size if total else 1
        except Exception as e:
            print(f"[{self.getName()}] 搜索异常: {e}")
        return result

    # ==================== 播放解析 ====================
    def playerContent(self, flag, id, vipFlags):
        try:
            # 复合ID格式：视频ID|集数
            if "|" in id:
                vid, set_idx = id.split("|", 1)
                data = self._post(f"{API_HOST}/video/set-info", {"id": vid, "set": int(set_idx)})
                info = (data or {}).get("data", {}).get("info", {})
                m3u8 = info.get("url_m3u8", "")
                if m3u8:
                    url = self._build_video_url(m3u8)
                    return {
                        'parse': 0,
                        'playUrl': '',
                        'url': url,
                        'header': {'User-Agent': UA}
                    }

            # 兜底：直接返回
            return {
                'parse': 0,
                'playUrl': '',
                'url': id,
                'header': {'User-Agent': UA}
            }
        except Exception as e:
            print(f"[{self.getName()}] 播放解析异常: {e}")
            return {'parse': 0, 'playUrl': '', 'url': id, 'header': {}}


# ============================================================
# 本地自测:  python3 nuomi.py
# ============================================================
if __name__ == '__main__':
    s = Spider().init('')
    print('== 分类 ==')
    cs = s.homeContent(False)['class']
    print(len(cs), [c['type_name'] for c in cs[:10]], '...')

    print('\n== 首页推荐 ==')
    lst = s.homeVideoContent()['list']
    print('共%d条, 首条: %s' % (len(lst), lst[0] if lst else '空'))

    print('\n== 列表(都市 第1页) ==')
    lst = s.categoryContent('tag:15', 1, False, {})['list']
    print('共%d条, 首条: %s' % (len(lst), lst[0] if lst else '空'))

    print('\n== 详情 ==')
    # 用首页第一条的 ID 测详情
    first_id = lst[0]['vod_id'] if lst else ''
    if first_id:
        d = s.detailContent([first_id])['list'][0]
        print('%s | %s | %s集' % (d['vod_name'], d['vod_remarks'], len(d['vod_play_url'].split('#'))))
        print('选集:', d['vod_play_url'][:120], '...')

        print('\n== 播放解析 ==')
        first_ep = d['vod_play_url'].split('#')[0].split('$')[1]
        print('m3u8:', s.playerContent('糯米短剧', first_ep, '')['url'])

    print('\n== 搜索 ==')
    r = s.searchContent('总裁', True)['list']
    print('共%d条:' % len(r), [x['vod_name'] for x in r[:5]])

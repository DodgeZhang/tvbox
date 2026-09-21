#QQ群:807916734
# coding=utf-8
"""
目标站: 糯米短剧 (8728.mrsvj.com)
站点类型: 竖屏短剧资源站
技术栈: Vue.js + Axios + Element UI
数据接口: POST /api/web/v1/* (JSON body)
API域名: 4gf56465fg112.hongjiuchang.com

API接口清单(2026-08-14 实测):
    /config/load        POST {plat:"pc"}           → 配置(视频域名/标签/卡片)
    /video/list         POST {pageNum:N,tag:id}     → 视频列表(按标签)
                        POST {pageNum:N,type:"new"} → 最新视频
                        POST {pageNum:N,type:"vip"} → VIP视频
    /video/detail-info  POST {id:videoId}           → 视频详情+集列表
    /video/set-info     POST {id:videoId,set:N}     → 播放地址(url_m3u8)
    /video/slide        POST {pageNum:N}            → 轮播图
    /search/list        POST {text:"kw",pageNum:N,plat:"pc"} → 搜索
    /tags/list          POST {}                     → 标签列表
    /rank/hot           POST {pageNum:N}            → 热门榜
    /rank/new           POST {pageNum:N}            → 新剧榜
    /rank/rating        POST {pageNum:N}            → 评分榜

视频线路(2026-08-14 实测):
    config 返回 4 个视频域名，实测仅 2 个可用:
      1. video_domain (base): https://666996.drephjq.com       ✓ 200
      2. video_domain_out (out): https://98991.cg22d.com        ✓ 200
      3. wy_video_domain: 403 Forbidden
      4. wy_video_domain_out: SSL 错误
    两线路均返回相同 m3u8，m3u8 使用 AES-128 加密(key 在同域 /uploads/enc.key)。
    TVBox 原生支持 AES-128 m3u8，key URL 相对于 m3u8 域名自动解析。

海报:
    cover 字段为相对路径(如 /uploads/video-cover/xxx.png)，
    需拼接 static_domain(https://TsuiPv.ws4ge.com)。
    static_domain 可能动态变化，从 /config/load 获取。
    PNG 海报体积较大，通过 wsrv.nl 代理转 JPEG 优化加载。

分页:
    使用 pageNum 参数，每页 24 条，返回 hasMore/total。
    最大页数限制 200 页(4800条)，防止无限翻页。
"""
import re
import sys
import json
import time
import urllib.parse

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def init(self, extend=""):
        self.site_url = "https://8728.mrsvj.com"
        self.api_base = "https://4gf56465fg112.hongjiuchang.com/api/web/v1"
        self.page_size = 24
        self.max_pages = 200
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Mobile Safari/537.36',
            'Content-Type': 'application/json;charset=utf-8',
            'Accept': 'application/json,text/plain,*/*',
            'Origin': 'https://8728.mrsvj.com',
            'Referer': 'https://8728.mrsvj.com/'
        }
        # 从 config 获取动态配置
        self.config = self._load_config()
        self.static_domain = self.config.get("static_domain", "https://TsuiPv.ws4ge.com")
        self.video_domains = self._get_video_domains()
        self.tags = self._get_tags()
        self.categories = self._build_categories()
        self.filter_config = self._build_filter_config()

    # ==================== 基础工具 ====================

    def _post(self, path, params=None, retries=2):
        """POST JSON 请求，返回解析后的 dict；失败返回 None"""
        url = self.api_base + path
        body = json.dumps(params or {}, ensure_ascii=False)
        for attempt in range(retries + 1):
            # 方法1: requests 库 (TVBox 环境通常自带)
            try:
                import requests
                r = requests.post(url, data=body.encode('utf-8'), headers=self.headers, timeout=15)
                j = r.json()
                if j.get("code") == 10000:
                    return j.get("data")
                return None
            except:
                pass
            # 方法2: urllib 兜底
            try:
                import urllib.request
                req = urllib.request.Request(url, data=body.encode('utf-8'), headers=self.headers, method='POST')
                resp = urllib.request.urlopen(req, timeout=15)
                j = json.loads(resp.read().decode('utf-8'))
                if j.get("code") == 10000:
                    return j.get("data")
                return None
            except Exception as e:
                if attempt < retries:
                    time.sleep(1)
                    continue
                print("[糯米短剧] POST %s 异常: %s" % (path, e))
        return None

    def _load_config(self):
        """加载站点配置(视频域名/标签等)"""
        data = self._post("/config/load", {"plat": "pc"})
        if data and isinstance(data, dict):
            cfg = data.get("config")
            if cfg:
                return cfg
        # 回退到硬编码默认值
        return {
            "static_domain": "https://TsuiPv.ws4ge.com",
            "video_domain": "https://666996.drephjq.com",
            "video_domain_out": "https://98991.cg22d.com"
        }

    def _get_video_domains(self):
        """获取可用视频域名列表(线路)"""
        domains = []
        base = self.config.get("video_domain", "")
        out = self.config.get("video_domain_out", "")
        if base:
            domains.append(("线路1", base))
        if out:
            domains.append(("线路2", out))
        if not domains:
            domains = [("线路1", "https://666996.drephjq.com")]
        return domains

    def _get_tags(self):
        """获取标签列表"""
        # 优先从 config 获取
        tags = self.config.get("tags") or []
        if tags:
            return tags
        # 回退到 /tags/list
        data = self._post("/tags/list", {})
        if data and isinstance(data, dict):
            return data.get("list") or []
        return []

    def _fix_pic(self, pic):
        """
        修复海报 URL:
        1. 相对路径 → 拼接 static_domain
        2. PNG 体积过大 → wsrv.nl 代理转 JPEG
        """
        if not pic:
            return ""
        if pic.startswith("http"):
            url = pic
        else:
            url = self.static_domain + pic
        # PNG 通过 wsrv.nl 代理转 JPEG
        if ".png" in url.lower():
            return "https://wsrv.nl/?url=%s&w=400&q=70&output=jpg" % urllib.parse.quote(url, safe='')
        return url

    def _remark(self, item):
        """生成备注信息"""
        sets = item.get("sets") or 0
        is_vip = item.get("is_vip", "0")
        parts = []
        if sets:
            parts.append("更新至%d集" % sets)
        if is_vip == "1":
            parts.append("VIP")
        return " ".join(parts)

    def _parse_item(self, it):
        """解析视频列表项为 TVBox 格式"""
        return {
            "vod_id": it.get("id", ""),
            "vod_name": it.get("title", "") or "",
            "vod_pic": self._fix_pic(it.get("cover") or ""),
            "vod_remarks": self._remark(it)
        }

    def _tag_name(self, tag_id_str):
        """将标签ID字符串转换为标签名"""
        if not tag_id_str:
            return ""
        ids = [int(x) for x in str(tag_id_str).split(",") if x.strip()]
        names = []
        tag_map = {t.get("id"): t.get("t") for t in self.tags}
        for tid in ids:
            name = tag_map.get(tid)
            if name:
                names.append(name)
        return " ".join(names)

    # ==================== 分类 ====================

    def _build_categories(self):
        """构建分类列表"""
        cats = [
            {"type_id": "all", "type_name": "全部"},
            {"type_id": "rank:hot", "type_name": "热门榜"},
            {"type_id": "rank:new", "type_name": "新剧榜"},
            {"type_id": "rank:rating", "type_name": "评分榜"},
            {"type_id": "type:new", "type_name": "最新上线"},
            {"type_id": "type:vip", "type_name": "VIP专享"},
        ]
        # 添加标签分类(按热度分组，避免过多)
        for tag in self.tags:
            cats.append({
                "type_id": "tag:%s" % tag.get("id"),
                "type_name": tag.get("t", "")
            })
        return cats

    def _build_filter_config(self):
        """构建筛选器配置"""
        filters = {
            "all": [
                {
                    "key": "tag",
                    "name": "类型",
                    "value": [{"n": "全部", "v": ""}] + [
                        {"n": t.get("t", ""), "v": str(t.get("id"))} for t in self.tags
                    ]
                }
            ],
            "type:new": [
                {
                    "key": "tag",
                    "name": "类型",
                    "value": [{"n": "全部", "v": ""}] + [
                        {"n": t.get("t", ""), "v": str(t.get("id"))} for t in self.tags
                    ]
                }
            ],
        }
        return filters

    def getName(self):
        return "糯米短剧"

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url

    # ==================== 首页 ====================

    def homeContent(self, filter):
        """首页: 分类 + 筛选器 + 推荐列表"""
        # 推荐列表: 取热门榜第1页
        video_list = []
        data = self._post("/rank/hot", {"pageNum": 1})
        if data and isinstance(data, dict):
            items = data.get("list") or []
            for it in items[:24]:
                video_list.append(self._parse_item(it))

        filters = {}
        for c in self.categories:
            f = self.filter_config.get(c["type_id"])
            if f:
                filters[c["type_id"]] = f

        return {"class": self.categories, "list": video_list, "filters": filters}

    def homeVideoContent(self):
        return {"list": self.homeContent(False).get("list", [])}

    # ==================== 分类列表 ====================

    def categoryContent(self, tid, pg, filter, extend):
        """分类页: 支持标签/类型/榜单三种模式"""
        page = int(pg) if pg else 1
        if page > self.max_pages:
            return {"list": [], "page": page, "pagecount": 1, "limit": self.page_size, "total": 0}

        # 解析筛选器
        tag_filter = ""
        if extend and isinstance(extend, dict):
            tag_filter = extend.get("tag") or ""
        elif extend and isinstance(extend, str):
            try:
                ext = json.loads(extend)
                tag_filter = ext.get("tag") or ""
            except:
                pass

        # 构建请求参数
        if tid.startswith("rank:"):
            # 榜单模式
            rank_type = tid.split(":")[1]
            data = self._post("/rank/%s" % rank_type, {"pageNum": page})
        elif tid.startswith("type:"):
            # 类型模式 (new/vip)
            type_val = tid.split(":")[1]
            params = {"pageNum": page, "type": type_val}
            if tag_filter:
                params["tag"] = int(tag_filter)
            data = self._post("/video/list", params)
        elif tid.startswith("tag:"):
            # 标签模式
            tag_id = tid.split(":")[1]
            data = self._post("/video/list", {"pageNum": page, "tag": int(tag_id)})
        elif tid == "all":
            # 全部
            params = {"pageNum": page}
            if tag_filter:
                params["tag"] = int(tag_filter)
            data = self._post("/video/list", params)
        else:
            return {"list": [], "page": page, "pagecount": 1, "limit": self.page_size, "total": 0}

        video_list = []
        total = 0
        has_more = False
        page_count = 1

        if data and isinstance(data, dict):
            items = data.get("list") or []
            total = data.get("total") or 0
            has_more = data.get("hasMore") or False
            for it in items:
                video_list.append(self._parse_item(it))
            # 计算总页数
            if total:
                page_count = (total + self.page_size - 1) // self.page_size
            elif has_more:
                page_count = page + 1

        return {
            "list": video_list,
            "page": page,
            "pagecount": page_count if page_count > 0 else 1,
            "limit": self.page_size,
            "total": total
        }

    # ==================== 详情 ====================

    def detailContent(self, ids):
        """详情页: 视频信息 + 选集列表"""
        if not ids:
            return {"list": []}
        vod_id = ids[0]

        data = self._post("/video/detail-info", {"id": vod_id})
        if not data or not isinstance(data, dict):
            return {"list": []}

        info = data.get("info") or {}
        title = info.get("title", "") or ""
        pic = self._fix_pic(info.get("cover") or "")
        summary = info.get("summary", "") or ""
        tag_names = self._tag_name(info.get("tags"))
        sets_count = info.get("sets") or 0
        views = info.get("views") or 0

        content = summary
        if tag_names:
            content += "\n类型: " + tag_names
        if sets_count:
            content += "\n共%d集" % sets_count
        if views:
            content += "\n播放: %d" % views

        # 选集列表
        set_list = info.get("setList") or []
        # 构建多线路播放地址
        play_from_list = []
        play_url_parts = []

        for line_name, domain in self.video_domains:
            play_from_list.append(line_name)
            episodes = []
            for ep in set_list:
                ep_idx = ep.get("i") or 0
                ep_name = "第%d集" % ep_idx
                # 编码: videoId:setIndex
                episodes.append("%s$%s:%d" % (ep_name, vod_id, ep_idx))
            play_url_parts.append("#".join(episodes))

        vod_play_from = "$$$".join(play_from_list)
        vod_play_url = "$$$".join(play_url_parts)

        result = [{
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": content.strip(),
            "vod_area": "",
            "vod_year": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_remarks": "共%d集" % sets_count if sets_count else "",
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    # ==================== 搜索 ====================

    def searchContent(self, key, quick, pg="1"):
        """搜索: /search/list 接口"""
        page = int(pg) if pg else 1
        if not key or len(key) < 2:
            return {"list": [], "page": page, "pagecount": 1}

        data = self._post("/search/list", {
            "text": key,
            "pageNum": page,
            "plat": "pc"
        })

        video_list = []
        total = 0
        page_count = 1

        if data and isinstance(data, dict):
            items = data.get("list") or []
            total = data.get("total") or 0
            for it in items:
                video_list.append(self._parse_item(it))
            if total:
                page_count = (total + 11) // 12  # 搜索每页12条

        return {
            "list": video_list,
            "page": page,
            "pagecount": page_count if page_count > 0 else 1
        }

    # ==================== 播放 ====================

    def playerContent(self, flag, id, vipFlags):
        """
        播放: 调用 /video/set-info 获取 m3u8 URL，拼接视频域名。
        id 格式: videoId:setIndex
        flag 为线路名称(线路1/线路2)，对应不同视频域名。
        """
        # 解析 id
        if ":" in id:
            parts = id.rsplit(":", 1)
            video_id = parts[0]
            try:
                set_index = int(parts[1])
            except ValueError:
                video_id = id
                set_index = 1
        else:
            video_id = id
            set_index = 1

        # 获取播放地址
        data = self._post("/video/set-info", {"id": video_id, "set": set_index})
        m3u8_url = ""
        if data and isinstance(data, dict):
            info = data.get("info") or {}
            m3u8_url = info.get("url_m3u8") or ""

        if not m3u8_url:
            # 回退到详情页嗅探
            watch_url = "%s/detail/%s/1" % (self.site_url, video_id)
            return {"parse": 1, "url": watch_url, "header": self.headers}

        # 根据线路选择域名
        domain = self.video_domains[0][1]  # 默认线路1
        for line_name, line_domain in self.video_domains:
            if flag == line_name:
                domain = line_domain
                break

        # 拼接完整 m3u8 URL
        if m3u8_url.startswith("http"):
            full_url = m3u8_url
        else:
            full_url = domain + "/" + m3u8_url

        # 播放头
        play_headers = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": self.site_url + "/"
        }

        return {"parse": 0, "url": full_url, "header": play_headers}

    # ==================== 辅助方法 ====================

    def manualContent(self, params):
        """手动解析(Web嗅探模式)"""
        return None

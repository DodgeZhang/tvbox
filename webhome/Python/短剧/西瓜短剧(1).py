#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
西瓜短剧网 (www.badgb.com) 爬虫 - TVBox / 影视仓 Spider 插件

站点说明 (基于服务端渲染 HTML 逆向 + 实测):
- 站点: https://www.badgb.com/  (站名: 西瓜短剧网, 苹果CMS 系短剧站)
- 全部为服务端渲染的 HTML, 无独立 JSON API, 故采用 HTML 正则解析。

URL 规则:
- 首页:        /                                  (含各分类板块 + 推荐列表)
- 分类列表:    /bad/{type_id}.html                (第 1 页)
               /bad/{type_id}-{page}.html          (第 2 页起, 例: /bad/1-2.html)
- 详情:        /gd/{vod_id}.html
- 播放:        /play/{vod_id}-{sid}-{nid}.html     (sid=线路, nid=集序号从 0 起)
- 搜索:        /search.php?wd={key}&page={page}

关键字段位置 (实测):
- 列表卡片:  <a class="fed-list-pics ..." href="/gd/{id}.html" data-original="{封面}" title="{名}">
                ... <span class="fed-list-remarks ...">{备注: 全集/第N集完结}</span>
- 分类名:    板块标题 <div class="fed-list-head"><h2 ...><i></i> {分类名}</h2> ... /bad/{id}.html
- 详情标题:  <title>{剧名}_...</title>
- 简介:      <meta name="description" content="...剧情介绍：{简介}">
- 播放列表:  href="/play/{id}-{sid}-{nid}.html" ... >第XX集</a>  (同一剧含多条线路 sid, 取集数最多的主线)
- 播放地址:  播放页内 JS 变量 var now="https://{cdn}/.../index.m3u8";   (直接内联, 无需 JS 逆向)
- 分页总数:  "共 <span>1136</span> 个影片" 或 "1/38"

注意:
- 搜索接口有服务端风控 (高频/非浏览器特征会返回 503 加载页), TVBox 端 WebView 通常可用。
- 封面 / m3u8 的 CDN 域名会校验 Referer, 统一带上 Referer = 站点域名。
- 该站点 CDN 证书环境异常, 关闭 verify 以避免握手失败。
"""

import re
import json
import logging
import os
import sys
import warnings
import requests
from collections import Counter

# CDN 证书环境异常, 关闭 verify 并抑制告警
requests.packages.urllib3.disable_warnings()
warnings.filterwarnings("ignore")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    BaseSpider = object

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Spider(BaseSpider):
    """西瓜短剧网 爬虫 (苹果CMS 系, HTML 解析)"""

    SITE = "https://www.badgb.com"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": SITE + "/",
    }

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(self.HEADERS)

    def init(self, extend):
        pass

    def getName(self):
        return "西瓜短剧"

    # ==================== 网络请求 ====================
    def _get(self, url, params=None, retry=1):
        """GET 页面, 返回解码后的 HTML 文本; 失败返回空串"""
        for attempt in range(retry + 1):
            try:
                resp = self.session.get(url, params=params, timeout=20)
                if resp.status_code == 200:
                    resp.encoding = "utf-8"
                    return resp.text
                logger.warning(f"请求失败 {url}: HTTP {resp.status_code}")
            except Exception as e:
                logger.warning(f"请求异常 {url}: {e}")
            if attempt < retry:
                import time
                time.sleep(1)
        return ""

    # ==================== 列表/卡片解析 ====================
    def _parse_list(self, html):
        """从列表/首页/搜索页 HTML 解析视频卡片列表 (去重)"""
        out = []
        seen = set()
        # href="/gd/ID.html" data-original="PIC" title="NAME"
        pat = re.compile(r'href="/gd/(\d+)\.html" data-original="([^"]*)" title="([^"]*)"')
        for m in pat.finditer(html):
            vid, pic, name = m.group(1), m.group(2), m.group(3)
            if vid in seen:
                continue
            seen.add(vid)
            # 往后找备注 (全集 / 第N集完结 等), 限制在卡片范围内
            tail = html[m.end():m.end() + 800]
            rm = re.search(r'class="fed-list-remarks[^"]*">([^<]*)</span>', tail)
            remarks = rm.group(1).strip() if rm else ""
            out.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })
        return out

    @staticmethod
    def _parse_pagecount(html, per_page):
        """从列表页提取总页数。优先 '1/38', 其次 '共 N 个影片'"""
        # 分页 "x/y"
        m = re.search(r'(\d+)\s*/\s*(\d+)', html)
        if m and int(m.group(2)) > 1:
            return int(m.group(2))
        # 共 N 个影片
        m = re.search(r'共[^0-9]*?(\d+)\s*个影片', html)
        if m:
            total = int(m.group(1))
            per = per_page or 30
            if total > 0:
                return (total + per - 1) // per
        return 1

    # ==================== 首页 ====================
    def homeContent(self, filter=False):
        try:
            html = self._get(self.SITE + "/")
            if not html:
                return {}

            # 分类: 从首页各板块标题 + 对应 /bad/{id}.html 提取
            classes = []
            blocks = re.split(r'class="fed-list-head', html)
            for b in blocks[1:]:
                tm = re.search(r'<h2[^>]*>(?:<i[^>]*></i>\s*)?([^<]+)</h2>', b)
                mid = re.search(r'href="/bad/(\d+)\.html"', b)
                if tm and mid:
                    name = tm.group(1).strip()
                    if name:
                        classes.append({"type_id": mid.group(1), "type_name": name})

            # 推荐: 首页全部卡片
            video_list = self._parse_list(html)
            return {
                "class": classes,
                "filters": {},
                "list": video_list,
            }
        except Exception as e:
            logger.error(f"获取首页失败: {e}")
            return {}

    def homeVideoContent(self):
        html = self._get(self.SITE + "/")
        return {"list": self._parse_list(html) if html else []}

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, ext):
        try:
            page = int(pg) if pg else 1
            if page <= 1:
                url = f"{self.SITE}/bad/{tid}.html"
            else:
                url = f"{self.SITE}/bad/{tid}-{page}.html"

            html = self._get(url)
            if not html:
                return {"list": [], "page": page, "pagecount": 1, "limit": 30, "total": 0}

            video_list = self._parse_list(html)
            per = len(video_list) or 30
            pagecount = self._parse_pagecount(html, per)
            total = per * pagecount

            return {
                "list": video_list,
                "page": page,
                "pagecount": pagecount,
                "limit": per,
                "total": total,
            }
        except Exception as e:
            logger.error(f"获取分类内容失败: {e}")
            return {"list": [], "page": int(pg) if pg else 1, "pagecount": 1, "limit": 30, "total": 0}

    # ==================== 详情 ====================
    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            html = self._get(f"{self.SITE}/gd/{vod_id}.html")
            if not html:
                return {"list": []}

            # 标题
            m = re.search(r'<title>(.*?)_', html)
            name = m.group(1).strip() if m else vod_id

            # 封面 (首个 data-original)
            m = re.search(r'data-original="([^"]+)"', html)
            pic = m.group(1).strip() if m else ""

            # 简介: meta description 中的 "剧情介绍：..."
            content = ""
            m = re.search(r'<meta name="description" content="([^"]*)"', html)
            if m:
                d = m.group(1)
                cm = re.search(r'剧情介绍[:：](.*)', d)
                # 站点 meta 常被 SEO 垃圾注入标签片段, 截到首个 '<' 之前并清理 @ 噪声
                raw = cm.group(1) if cm else d
                content = re.split(r'<', raw)[0].strip()
                content = re.sub(r'@+', ' ', content).strip()

            # 播放列表: 提取所有 /play/{vid}-{sid}-{nid}.html 及链接文本, 去重
            raw = re.findall(
                r'href="(/play/(\d+)-(\d+)-(\d+)\.html)"[^>]*>([^<]+)</a>', html)
            if not raw:
                return {"list": []}

            # 去重 (vid-sid-nid), 保留第一次出现的文本
            seen = set()
            unique = []
            for p in raw:
                key = (p[1], p[2], p[3])
                if key in seen:
                    continue
                seen.add(key)
                unique.append(p)

            # 按线路 (sid) 分组生成多个播放源, TVBox 可切换以提升成功率
            sid_counter = Counter(p[2] for p in unique)
            sids = sorted(sid_counter.keys(), key=lambda s: -sid_counter[s])  # 集数多的放前面

            play_from_parts = []
            play_url_parts = []
            for sid in sids:
                eps = sorted([p for p in unique if p[2] == sid], key=lambda x: int(x[3]))
                episodes = []
                for i, p in enumerate(eps):
                    txt = p[4].strip()
                    # 多集剧通常文本为"第XX集"; 单集/全集剧可能是"立即播放""全集完结"等
                    if not re.match(r'第\d+集$', txt):
                        txt = "全集" if len(eps) == 1 else f"第{i+1:02d}集"
                    # play_id 格式: {vid}-{sid}-{nid}  (供 playerContent 拼 URL)
                    play_id = f"{p[1]}-{p[2]}-{p[3]}"
                    episodes.append(f"{txt}${play_id}")
                if episodes:
                    src_name = self.getName() if len(sids) == 1 else f"{self.getName()}-{sid}"
                    play_from_parts.append(src_name)
                    play_url_parts.append("#".join(episodes))

            # 备注: 主线路集数; 多源时额外标注源数
            main_eps = sorted([p for p in unique if p[2] == sids[0]], key=lambda x: int(x[3])) if sids else []
            remarks = f"共{len(main_eps)}集" if main_eps else ""
            if len(sids) > 1:
                remarks += f"/{len(sids)}源"

            vod = {
                "vod_id": vod_id,
                "vod_name": name,
                "vod_pic": pic,
                "type_name": "",
                "vod_year": "",
                "vod_area": "",
                "vod_remarks": remarks,
                "vod_actor": "",
                "vod_director": "",
                "vod_content": content,
                "vod_play_from": "$$$".join(play_from_parts),
                "vod_play_url": "$$$".join(play_url_parts),
            }
            return {"list": [vod]}
        except Exception as e:
            logger.error(f"获取详情失败: {e}")
            return {"list": []}

    # ==================== 播放 (核心) ====================
    def playerContent(self, flag, id, vipFlags):
        """
        返回单集 m3u8 播放地址。
        id 格式: "{vod_id}-{sid}-{nid}"  (由 detailContent 拼装)
        """
        try:
            parts = str(id).split("-")
            if len(parts) < 3:
                return {}
            vod_id, sid, nid = parts[0], parts[1], parts[2]

            url = f"{self.SITE}/play/{vod_id}-{sid}-{nid}.html"
            html = self._get(url)
            if not html:
                return {}

            # 播放页内联: var now="https://{cdn}/.../index.m3u8";
            m = re.search(r'var now="(https?://[^"]+\.m3u8)"', html)
            if not m:
                logger.error(f"未找到播放地址: {id}")
                return {}

            play_url = m.group(1)
            return {
                "parse": 0,
                "playUrl": "",
                "url": play_url,
                "header": {
                    "User-Agent": self.HEADERS["User-Agent"],
                    "Referer": f"{self.SITE}/play/{vod_id}-{sid}-{nid}.html",
                    "Origin": self.SITE,
                    "Accept": "*/*",
                },
            }
        except Exception as e:
            logger.error(f"解析播放失败: {e}")
            return {}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
            html = self._get(f"{self.SITE}/search.php", params={"wd": key, "page": page}, retry=1)
            if not html:
                return {"list": [], "page": page, "pagecount": 1, "limit": 30, "total": 0}

            # 风控页 (加载中…) 检测
            if "加载中" in html and "页面加载中" in html:
                logger.warning("搜索被站点风控拦截 (503 加载页), 建议降低频率或于 TVBox 端重试")
                return {"list": [], "page": page, "pagecount": 1, "limit": 30, "total": 0}

            video_list = self._parse_list(html)
            per = len(video_list) or 30
            pagecount = self._parse_pagecount(html, per)
            total = per * pagecount

            return {
                "list": video_list,
                "page": page,
                "pagecount": pagecount,
                "limit": per,
                "total": total,
            }
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {"list": [], "page": int(pg) if pg else 1, "pagecount": 1, "limit": 30, "total": 0}


# ==================== 本地自检 (python 直接运行, 不影响 TVBox 加载) ====================
if __name__ == "__main__":
    sp = Spider()

    print("===== 首页 / 分类 =====")
    home = sp.homeContent(filter=True)
    print("分类数:", len(home.get("class", [])))
    for c in home.get("class", [])[:8]:
        print("  ", c["type_id"], "->", c["type_name"])
    print("推荐条目:", len(home.get("list", [])))
    if home.get("list"):
        print("示例:", home["list"][0])

    print("\n===== 分类列表 (取首个分类第1页) =====")
    if home.get("class"):
        tid = home["class"][0]["type_id"]
        cat = sp.categoryContent(tid, 1, False, {})
        print(f"分类 {tid} 条目:", len(cat.get("list", [])), "| 总页:", cat.get("pagecount"))
        if cat.get("list"):
            print("示例:", cat["list"][0])

    print("\n===== 详情 =====")
    vid = home["list"][0]["vod_id"] if home.get("list") else "40853"
    det = sp.detailContent([vid])
    if det.get("list"):
        v = det["list"][0]
        eps = v["vod_play_url"].split("#") if v["vod_play_url"] else []
        print("名称:", v["vod_name"], "|", v["vod_remarks"])
        print("简介:", (v["vod_content"][:60] + "...") if v["vod_content"] else "(无)")
        print("播放集数:", len(eps))
        if eps:
            print("首集:", eps[0])

            print("\n===== 播放 =====")
            ep_id = eps[0].split("$")[1]
            play = sp.playerContent(sp.getName(), ep_id, "")
            print("play url:", play.get("url"))

    print("\n===== 搜索 (可能受风控) =====")
    s = sp.searchContent("重生", False, "1")
    print("搜索结果数:", len(s.get("list", [])))

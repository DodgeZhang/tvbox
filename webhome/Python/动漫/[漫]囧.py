#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QQ群：807916734 🐟
囧次元 (jciyuan.com) 爬虫源
=========================
技术路线：MacCMS JSON API（/api.php/provide/vod/）

站点特征：
  - MacCMS 内核，标准 JSON API
  - 分类：日本动漫(20) / 国产动漫(21) / 欧美动漫(22) / 剧场版(26)
  - 详情页：/acgdetail/{id}.html
  - 播放页：/acgplay/{vod_id}-{line}-{ep}.html（部分需VIP）
  - API 直链 m3u8 线路（jsm3u8）可直接播放
"""

import sys
import re
import json
import base64
import urllib.parse

sys.path.append("..")
from base.spider import Spider


class Spider(Spider):
    # ==================== 基础配置 ====================
    host = "https://www.jciyuan.com"
    site_url = "https://www.jciyuan.com"
    api_url = "https://www.jciyuan.com/api.php/provide/vod/"

    # 分类映射
    categories = [
        ("日本动漫", "20"),
        ("国产动漫", "21"),
        ("欧美动漫", "22"),
        ("剧场版", "26"),
    ]

    # 请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.jciyuan.com/",
        "Accept": "application/json, text/plain, */*",
    }

    # m3u8 播放时附加的请求头
    play_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.jciyuan.com/",
    }

    # 广告过滤阈值
    AD_MIN_GROUP = 3       # 连续 N 个以上短分片判定为广告组
    AD_MAX_DURATION = 2.0  # 单分片时长 <2s 视为可疑

    # drpy 本地代理 URL 前缀
    # 框架拦截此格式的 URL，调用 localProxy 方法
    PROXY_PREFIX = "http://127.0.0.1:9978/proxy?do=py&url="

    # ==================== 工具函数层 ====================

    def getName(self):
        return "囧次元"

    def e64(self, text):
        """Base64 编码"""
        return base64.b64encode(text.encode("utf-8")).decode("utf-8")

    def d64(self, text):
        """Base64 解码"""
        return base64.b64decode(text.encode("utf-8")).decode("utf-8")

    def _fetch_api(self, params):
        """请求 MacCMS API，返回 JSON dict
        关键：self.fetch() 返回 Response 对象，用 .json() 取数据
        """
        try:
            url = self.api_url + "?" + params
            resp = self.fetch(url, headers=self.headers)
            if resp:
                return resp.json()
        except Exception as e:
            print(f"[囧次元] API请求异常: {e} params={params}")
        return None

    def _build_vod_item(self, raw):
        """从 API 原始数据构建标准影片条目"""
        return {
            "vod_id": str(raw.get("vod_id", "")),
            "vod_name": raw.get("vod_name", ""),
            "vod_pic": raw.get("vod_pic", ""),
            "vod_remarks": raw.get("vod_remarks", ""),
        }

    def _build_full_vod(self, raw):
        """从 API detail 数据构建完整影片信息"""
        item = self._build_vod_item(raw)
        item.update({
            "vod_year": raw.get("vod_year", ""),
            "vod_area": raw.get("vod_area", ""),
            "vod_actor": raw.get("vod_actor", ""),
            "vod_director": raw.get("vod_director", ""),
            "vod_class": raw.get("vod_class", ""),
            "vod_score": raw.get("vod_score", ""),
            "vod_content": self._clean_html(raw.get("vod_content", "")),
        })
        return item

    @staticmethod
    def _clean_html(text):
        """去除 HTML 标签"""
        if not text:
            return ""
        return re.sub(r"<[^>]+>", "", text).strip()

    @staticmethod
    def _is_direct_url(url):
        """判断是否为可直链播放的 URL"""
        if not url:
            return False
        return url.startswith("http") and bool(re.search(r"\.(m3u8|mp4|flv|ts)", url, re.IGNORECASE))

    def _filter_play_lines(self, play_from, play_url):
        """
        过滤播放线路：只保留含直链 m3u8/mp4 的线路，丢弃加密线路

        VIP线路（NBY/Ace/yydm）完全锁在登录墙后面：
          - 播放页 /acgplay/{id}-{line}-{ep}.html 跳转到 /user/index.html
          - 所有 MacCMS player URL 路径全部 301 到首页
          - 加密ID格式 NBY-xxx / Ace_Top-xxx / yydm_xxx 无公开解密接口
          - yydm 线路集名甚至显示"请升级到最新版本"（已废弃）
        因此直接丢弃这些线路，只保留 jsm3u8 直链线路。
        如果所有线路都是加密的（纯VIP视频），全部保留作为 fallback。
        """
        from_parts = play_from.split("$$$") if play_from else []
        url_parts = play_url.split("$$$") if play_url else []

        while len(url_parts) < len(from_parts):
            url_parts.append("")

        direct_lines = []
        encrypted_lines = []

        for i, (lf, lu) in enumerate(zip(from_parts, url_parts)):
            if not lu:
                continue
            episodes = lu.split("#")
            has_direct = False
            for ep in episodes:
                if "$" in ep:
                    _, ep_url = ep.split("$", 1)
                    if self._is_direct_url(ep_url):
                        has_direct = True
                        break

            if has_direct:
                direct_lines.append((lf, lu))
            else:
                encrypted_lines.append((lf, lu))

        keep_lines = direct_lines if direct_lines else (direct_lines + encrypted_lines)

        new_from = "$$$".join(lf for lf, _ in keep_lines)
        new_url = "$$$".join(lu for _, lu in keep_lines)

        return new_from, new_url

    def _filter_ad_segments(self, m3u8_text):
        """
        过滤 m3u8 中的广告分片

        广告特征分析（实测）：
          - 总分片 368 个，广告分片 84 个（23%）
          - 广告分片时长 0.8-2.0s（正常分片 2.4-10.4s）
          - 连续出现 3-15 个短分片组成一个广告组
          - 共 16 个广告组散布在整个视频中
          - 无 #EXT-X-DISCONTINUITY 标记（广告直接混入）
          - 所有分片来自同一域名（无法按域名区分）

        过滤策略：
          1. 连续短分片组（<2s 且≥3个）→ 整组移除
          2. #EXT-X-DISCONTINUITY 前后的短分片 → 移除（如有）
        """
        lines = m3u8_text.strip().split("\n")

        # 解析所有分片
        segments = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("#EXTINF"):
                dur = 0
                try:
                    dur = float(line.split(":")[1].rstrip(","))
                except (ValueError, IndexError):
                    pass
                if i + 1 < len(lines):
                    url_line = lines[i + 1].strip()
                    segments.append({
                        "extinf": line,
                        "url": url_line,
                        "dur": dur,
                        "idx": i,
                    })
                i += 2
            else:
                i += 1

        if not segments:
            return m3u8_text

        # 标记要删除的分片（连续短分片组）
        to_remove = set()
        short_streak = []

        for seg in segments:
            if seg["dur"] < self.AD_MAX_DURATION:
                short_streak.append(seg)
            else:
                if len(short_streak) >= self.AD_MIN_GROUP:
                    for s in short_streak:
                        to_remove.add(s["idx"])
                short_streak = []

        # 处理末尾
        if len(short_streak) >= self.AD_MIN_GROUP:
            for s in short_streak:
                to_remove.add(s["idx"])

        if not to_remove:
            return m3u8_text

        # 重建 m3u8，跳过广告分片
        result_lines = []
        skip_next = False
        for i, line in enumerate(lines):
            if i in to_remove:
                skip_next = True
                continue
            if skip_next:
                skip_next = False
                continue
            result_lines.append(line)

        print(f"[囧次元] 广告过滤: 移除 {len(to_remove)} 个广告分片 (共 {len(segments)} 个分片, 广告占 {100*len(to_remove)/len(segments):.0f}%)")
        return "\n".join(result_lines)

    @staticmethod
    def _fix_relative_url(base, scheme, netloc, path, rel_url):
        """将相对 URL 补全为完整 URL"""
        if rel_url.startswith("http"):
            return rel_url
        if rel_url.startswith("/"):
            return scheme + "://" + netloc + rel_url
        parent = path.rsplit("/", 1)[0]
        return scheme + "://" + netloc + parent + "/" + rel_url

    def _build_proxy_url(self, original_url):
        """构造 localProxy 代理 URL

        将原始 m3u8 URL 编码为 base64，拼接到代理 URL 后面。
        drpy 框架拦截此格式的 URL，自动调用 localProxy 方法。
        """
        return self.PROXY_PREFIX + self.e64(original_url)

    # ==================== 五大核心方法 ====================

    def init(self, extend=""):
        pass

    def homeContent(self, filter):
        """首页：分类列表 + 推荐内容"""
        result = {"class": [], "list": []}

        for name, tid in self.categories:
            result["class"].append({"type_id": tid, "type_name": name})

        try:
            data = self._fetch_api("ac=detail&pg=1")
            if data and data.get("code") == 1:
                for raw in data.get("list", [])[:20]:
                    result["list"].append(self._build_vod_item(raw))
        except Exception as e:
            print(f"[囧次元] 首页异常: {e}")

        return result

    def categoryContent(self, tid, pg, filter, extend):
        """分类列表 + 分页"""
        try:
            page = int(pg) if pg else 1
        except (ValueError, TypeError):
            page = 1

        result = {
            "list": [],
            "page": page,
            "pagecount": 0,
            "limit": 21,
            "total": 0,
        }

        try:
            data = self._fetch_api("ac=detail&pg=%d&t=%s" % (page, tid))
            if data and data.get("code") == 1:
                result["pagecount"] = data.get("pagecount", 0)
                result["total"] = data.get("total", 0)
                result["limit"] = data.get("limit", 21)
                for raw in data.get("list", []):
                    result["list"].append(self._build_vod_item(raw))
        except Exception as e:
            print(f"[囧次元] 分类异常 tid={tid} pg={page}: {e}")

        return result

    def detailContent(self, ids):
        """详情 + 播放线路"""
        result = []

        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            data = self._fetch_api("ac=detail&ids=%s" % vod_id)
            if not data or data.get("code") != 1:
                return {"list": []}

            vod_list = data.get("list", [])
            if not vod_list:
                return {"list": []}

            raw = vod_list[0]
            item = self._build_full_vod(raw)

            play_from = raw.get("vod_play_from", "")
            play_url = raw.get("vod_play_url", "")

            new_from, new_url = self._filter_play_lines(play_from, play_url)

            item["vod_play_from"] = new_from
            item["vod_play_url"] = new_url

            result.append(item)

        except Exception as e:
            print(f"[囧次元] 详情异常 ids={ids}: {e}")

        return {"list": result}

    def searchContent(self, key, quick, pg="1"):
        """搜索"""
        result = {"list": [], "page": 1, "pagecount": 0, "limit": 21, "total": 0}

        if not key:
            return result

        try:
            page = int(pg) if pg else 1
        except (ValueError, TypeError):
            page = 1

        try:
            wd = urllib.parse.quote(key)
            data = self._fetch_api("ac=detail&wd=%s&pg=%d" % (wd, page))
            if data and data.get("code") == 1:
                result["page"] = page
                result["pagecount"] = data.get("pagecount", 0)
                result["total"] = data.get("total", 0)
                for raw in data.get("list", []):
                    result["list"].append(self._build_vod_item(raw))
        except Exception as e:
            print(f"[囧次元] 搜索异常 key={key}: {e}")

        return result

    def playerContent(self, flag, id, vipFlags):
        """播放地址解析

        v4 关键修复：
          直链 m3u8 不再返回 parse:0 直链播放（那样广告无法过滤）
          而是构造 proxy URL 走 localProxy，在代理中过滤广告后返回干净 m3u8

        流程：
          playerContent 返回 proxy URL
            → drpy 框架拦截 proxy?do=py 格式
            → 调用 localProxy(param)
            → localProxy 解码 URL、获取 m3u8、过滤广告、修复路径
            → 返回干净的 m3u8 给播放器
        """
        try:
            if self._is_direct_url(id):
                # 直链 m3u8 → 走 localProxy 过滤广告
                proxy_url = self._build_proxy_url(id)
                return {
                    "parse": 0,
                    "url": proxy_url,
                    "header": "",
                }

            if id.startswith("http"):
                # 播放页 URL → 交解析器嗅探
                return {
                    "parse": 1,
                    "url": id,
                    "header": self.headers,
                }

            return {
                "parse": 1,
                "url": id,
                "header": "",
            }

        except Exception as e:
            print(f"[囧次元] 播放解析异常 flag={flag} id={id}: {e}")
            return {"parse": 1, "url": id, "header": ""}

    def localProxy(self, param):
        """本地代理：过滤广告 + 修复相对路径

        触发方式：playerContent 返回 proxy URL (http://127.0.0.1:9978/proxy?do=py&url=<base64>)
        drpy 框架拦截此 URL，将 query 参数作为 param 传入。

        处理流程：
          1. 解码 URL（支持 base64 和 URL 编码）
          2. 获取 m3u8 内容
          3. 过滤广告分片（连续短分片组）
          4. 修复 #EXT-X-KEY:URI 相对路径（enc.key）
          5. 修复 ts 分片相对路径
          6. 返回干净的 m3u8
        """
        try:
            raw_url = param.get("url", "") if isinstance(param, dict) else str(param)

            # 尝试 base64 解码（drpy 标准格式）
            url = None
            try:
                url = self.d64(raw_url)
                if not url.startswith("http"):
                    url = None
            except Exception:
                pass

            # 回退到 URL 解码
            if not url:
                url = urllib.parse.unquote(raw_url)

            if not url or not url.startswith("http"):
                return [200, "text/plain", ""]

            resp = self.fetch(url, headers=self.play_headers)
            if not resp:
                return [200, "text/plain", ""]

            data = resp.text

            # 1. 过滤广告分片
            data = self._filter_ad_segments(data)

            # 2. 修复相对路径
            parsed = urllib.parse.urlparse(url)
            scheme = parsed.scheme
            netloc = parsed.netloc
            base = "%s://%s" % (scheme, netloc)
            path = parsed.path

            lines = data.strip().split("\n")
            for idx, line in enumerate(lines):
                stripped = line.strip()
                if not stripped:
                    continue

                # 修复 #EXT-X-KEY:URI="enc.key" 相对路径
                if stripped.startswith("#EXT-X-KEY") and 'URI="' in stripped:
                    uri_match = re.search(r'URI="([^"]+)"', stripped)
                    if uri_match:
                        uri = uri_match.group(1)
                        if not uri.startswith("http"):
                            full_uri = self._fix_relative_url(base, scheme, netloc, path, uri)
                            lines[idx] = stripped.replace('URI="%s"' % uri, 'URI="%s"' % full_uri)
                    continue

                # 跳过其他 #EXT 行
                if stripped.startswith("#"):
                    continue

                # 修复 ts 分片相对路径
                if not stripped.startswith("http"):
                    lines[idx] = self._fix_relative_url(base, scheme, netloc, path, stripped)

            return [200, "application/vnd.apple.mpegurl", "\n".join(lines)]

        except Exception as e:
            print(f"[囧次元] localProxy异常: {e}")
            return [200, "text/plain", ""]

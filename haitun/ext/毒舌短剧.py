# coding=utf-8
"""
目标站: 毒舌短剧 (https://www.dushe.video)
模板: 苹果CMS (海螺模板 mconch)
版本: v2 优化版 — 修复剧集重复/干扰、播放解析卡顿、提升加载速度
"""
import re
import sys
import json
import urllib.parse
import time
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.site_url = "https://www.dushe.video"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        # ========== 速度优化：预编译全部正则 ==========
        # 列表页
        self._re_vodlist_item = re.compile(r'<li[^>]*class="vodlist_item[^"]*"[^>]*>(.*?)</li>', re.DOTALL)
        self._re_href = re.compile(r'href="(/drama/(\d+)\.html)"')
        self._re_title = re.compile(r'title="([^"]*)"')
        self._re_pic = re.compile(r'data-original="([^"]*)"')
        self._re_remark = re.compile(r'class="pic_text[^"]*"[^>]*>(.*?)</span>')
        self._re_tag = re.compile(r'class="voddate[^"]*"[^>]*>(.*?)</em>')
        self._re_page = re.compile(r'/type/[^/]+-(\d+)\.html')
        self._re_total = re.compile(r'共\s*(\d+)\s*部')
        self._re_search_page = re.compile(r'[?&]page=(\d+)')
        # 详情页 — 只从 content_playlist 区域内提取，避免全局匹配干扰
        self._re_playlist_ul = re.compile(r'<ul[^>]*class="content_playlist[^"]*"[^>]*>(.*?)</ul>', re.DOTALL)
        self._re_episode = re.compile(r'<a[^>]+href="(/play/(\d+)-(\d+)-(\d+)\.html)"[^>]*>(.*?)</a>')
        self._re_html_tag = re.compile(r'<[^>]+>')
        self._re_html_entity = re.compile(r'&(?:nbsp|amp|lt|gt|quot|apos|#\d+);')
        # 播放页 — 直接匹配 m3u8，该站无复杂播放器
        self._re_m3u8 = re.compile(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*")
        self._re_video_src = re.compile(r'<video[^>]+src="([^"]+\.m3u8[^"]*)"')
        self._re_iframe = re.compile(r'<iframe[^>]+src="([^"]+)"')

        # ========== 一级分类 ==========
        self.categories = [
            {"type_id": "dushi", "type_name": "都市"},
            {"type_id": "guzhuang", "type_name": "古装"},
            {"type_id": "mingguo", "type_name": "民国"},
            {"type_id": "manju", "type_name": "漫剧"},
            {"type_id": "qingchunxiaoyuan", "type_name": "青春校园"},
            {"type_id": "xangcunshenghuo", "type_name": "乡村生活"},
            {"type_id": "xijugaoxiao", "type_name": "喜剧搞笑"},
            {"type_id": "xuanyijingsong", "type_name": "悬疑惊悚"},
            {"type_id": "kehuanyineng", "type_name": "科幻异能"},
        ]

        # ========== 二级分类映射 ==========
        self.sub_type_map = {
            "dushi": [
                {"n": "全部", "v": ""},
                {"n": "都市甜宠", "v": "dushitianchong"},
                {"n": "赘婿逆袭", "v": "zhuixunixi"},
                {"n": "都市复仇", "v": "dushifuchou"},
                {"n": "神医战神", "v": "shenyizhanshen"},
                {"n": "都市职场", "v": "dushizhichang"},
                {"n": "家庭伦理", "v": "jiatinglunli"},
                {"n": "现实生活", "v": "xianshishenghuo"},
            ],
            "guzhuang": [
                {"n": "全部", "v": ""},
                {"n": "古装言情", "v": "guzhuangyanqing"},
                {"n": "武侠仙侠", "v": "wuxiaxianxia"},
                {"n": "玄幻穿越", "v": "xuanhuanchuanyue"},
                {"n": "古装甜宠", "v": "guzhuangtianchong"},
                {"n": "宫廷宫斗", "v": "gongtinggongdou"},
                {"n": "权谋上位", "v": "quanmoushangwei"},
                {"n": "高门宅斗", "v": "gaomenzhaidou"},
                {"n": "古装复仇", "v": "guzhuangfuchou"},
            ],
        }

        self.sort_options = [
            {"n": "最新", "v": "time"},
            {"n": "最热", "v": "hits"},
            {"n": "评分", "v": "score"},
        ]

        # ========== 构建 filters ==========
        self.filters = {}
        for cat in self.categories:
            tid = cat["type_id"]
            filter_list = []
            if tid in self.sub_type_map:
                filter_list.append({
                    "key": "class",
                    "name": "子类型",
                    "value": self.sub_type_map[tid]
                })
            filter_list.append({
                "key": "by",
                "name": "排序",
                "value": self.sort_options
            })
            self.filters[tid] = filter_list

    def _safe_fetch(self, url, headers=None, max_retry=2, timeout=8):
        """轻量安全请求，失败自动重试"""
        if headers is None:
            headers = self.headers
        for i in range(max_retry):
            try:
                resp = self.fetch(url, headers=headers)
                if resp and resp.text:
                    return resp
            except Exception:
                if i < max_retry - 1:
                    time.sleep(0.15)
        return None

    def _fix_url(self, url):
        """补全相对URL"""
        if not url:
            return ''
        if url.startswith('http'):
            return url
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.site_url + url
        return self.site_url + '/' + url

    def _clean_text(self, text):
        """清理HTML标签和实体编码"""
        if not text:
            return ''
        text = self._re_html_tag.sub('', text)
        text = self._re_html_entity.sub('', text)
        return text.strip()

    def _parse_video_list(self, html, max_count=0):
        """正则解析视频列表 — 预编译正则提升速度"""
        video_list = []
        seen = set()
        item_blocks = self._re_vodlist_item.findall(html)
        for block in item_blocks:
            href_m = self._re_href.search(block)
            if not href_m:
                continue
            href, vod_id = href_m.groups()
            if vod_id in seen:
                continue
            seen.add(vod_id)

            title_m = self._re_title.search(block)
            title = title_m.group(1) if title_m else ''

            pic_m = self._re_pic.search(block)
            pic = pic_m.group(1) if pic_m else ''

            remark_m = self._re_remark.search(block)
            remark = self._clean_text(remark_m.group(1)) if remark_m else ''

            tag_m = self._re_tag.search(block)
            if tag_m:
                tag = self._clean_text(tag_m.group(1))
                if tag and tag not in remark:
                    remark = tag + (' ' + remark if remark else '')

            if not title:
                continue
            video_list.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": self._fix_url(pic),
                "vod_remarks": remark,
            })
            if max_count > 0 and len(video_list) >= max_count:
                break
        return video_list

    def _extract_page_info(self, html, default_page=1):
        """提取分页信息"""
        pagecount = default_page
        total = 0
        pages = self._re_page.findall(html)
        if pages:
            pagecount = max(pagecount, max(map(int, pages)))
        total_m = self._re_total.search(html)
        if total_m:
            total = int(total_m.group(1))
        if not total:
            total = 24 * pagecount
        return pagecount, total

    def homeContent(self, filter):
        url = self.site_url + "/"
        resp = self._safe_fetch(url)
        video_list = self._parse_video_list(resp.text, max_count=36) if resp else []
        return {"class": self.categories, "list": video_list, "filters": self.filters}

    def homeVideoContent(self):
        return self.homeContent(False)

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        sub_type = extend.get("class", "") if extend else ""
        type_slug = sub_type if sub_type else tid

        if page <= 1:
            url = f"{self.site_url}/type/{type_slug}.html"
        else:
            url = f"{self.site_url}/type/{type_slug}-{page}.html"

        resp = self._safe_fetch(url)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}

        video_list = self._parse_video_list(resp.text)
        pagecount, total = self._extract_page_info(resp.text, page)

        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": total
        }

    def detailContent(self, ids):
        """详情页 — 只从 content_playlist 区域提取剧集，避免全局干扰"""
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        url = f"{self.site_url}/drama/{vod_id}.html"
        resp = self._safe_fetch(url)
        if not resp:
            return {"list": []}

        html = resp.text

        # 标题
        vod_name = vod_id
        title_m = re.search(r'<title>(.*?)</title>', html)
        if title_m:
            raw = title_m.group(1)
            vod_name = raw.split('》')[0].replace('《', '').strip()
            if not vod_name:
                vod_name = raw.split('_')[0].split('-')[0].strip()

        # 大图
        vod_pic = ''
        pic_m = re.search(r'class="vodlist_thumb[^"]*"[^>]*data-original="([^"]+)"', html, re.DOTALL)
        if not pic_m:
            pic_m = re.search(r'data-original="([^"]+)"', html)
        if pic_m:
            vod_pic = self._fix_url(pic_m.group(1))

        # 简介
        vod_content = ''
        desc_m = re.search(r'<meta name="description" content="([^"]+)"', html)
        if desc_m:
            vod_content = desc_m.group(1)
            vod_content = re.sub(r'^.*?剧情介绍[：:]\s*', '', vod_content)
            vod_content = re.sub(r'，该[^。]*讲述的是.*$', '', vod_content)
            vod_content = self._clean_text(vod_content)

        # 年份 / 地区
        vod_year = vod_area = ''
        y_m = re.search(r'(\d{4})-\d{2}-\d{2}', html)
        if y_m:
            vod_year = y_m.group(1)
        type_m = re.search(r'class="pic_text[^"]*"[^>]*>(.*?)</span>', html)
        if type_m:
            vod_area = self._clean_text(type_m.group(1))

        # ========== 关键修复：只从 content_playlist 区域提取剧集 ==========
        play_from_list = []
        play_url_list = []

        # 查找所有 playlist ul（多线路时可能有多个）
        playlist_sections = self._re_playlist_ul.findall(html)

        if playlist_sections:
            # 有明确的 playlist 区域
            line_idx = 0
            for section_html in playlist_sections:
                line_idx += 1
                episodes = self._re_episode.findall(section_html)
                if not episodes:
                    continue

                # 去重：同一集可能出现在多个位置
                seen_eps = set()
                ep_urls = []
                for ep_link, ep_vid, ep_line, ep_num, ep_name_raw in episodes:
                    ep_name = self._clean_text(ep_name_raw)
                    if not ep_name or ep_name in seen_eps:
                        continue
                    seen_eps.add(ep_name)
                    ep_urls.append(f"{ep_name}${self._fix_url(ep_link)}")

                if ep_urls:
                    play_from_list.append(f"线路{line_idx}")
                    play_url_list.append('#'.join(ep_urls))
        else:
            # 备用：全局匹配（兼容旧模板）
            ep_links = self._re_episode.findall(html)
            if ep_links:
                seen_eps = set()
                ep_urls = []
                for ep_link, ep_vid, ep_line, ep_num, ep_name_raw in ep_links:
                    ep_name = self._clean_text(ep_name_raw)
                    if not ep_name or ep_name in seen_eps:
                        continue
                    seen_eps.add(ep_name)
                    ep_urls.append(f"{ep_name}${self._fix_url(ep_link)}")
                if ep_urls:
                    play_from_list.append('默认线路')
                    play_url_list.append('#'.join(ep_urls))
            else:
                play_from_list.append('默认线路')
                play_url_list.append(f"播放${self.site_url}/drama/{vod_id}.html")

        vod_play_from = '$$$'.join(play_from_list) if play_from_list else '默认线路'
        vod_play_url = '$$$'.join(play_url_list) if play_url_list else f"播放${self.site_url}/drama/{vod_id}.html"

        result = [{
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_actor": '',
            "vod_director": '',
            "vod_area": vod_area,
            "vod_year": vod_year,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)
        url = f"{self.site_url}/vodsearch/{encoded_key}-------------.html"
        if page > 1:
            url += f"?page={page}"

        resp = self._safe_fetch(url)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1}

        video_list = self._parse_video_list(resp.text)
        pagecount = 1
        pages = self._re_search_page.findall(resp.text)
        if pages:
            pagecount = max(pagecount, max(map(int, pages)))

        return {"list": video_list, "page": page, "pagecount": pagecount}

    def playerContent(self, flag, id, vipFlags):
        """播放器解析 — 直接匹配 m3u8，该站无复杂播放器配置"""
        if id.startswith('http'):
            play_url = id
        elif id.startswith('/'):
            play_url = self.site_url + id
        else:
            play_url = self.site_url + '/' + id

        resp = self._safe_fetch(play_url)
        if not resp:
            return {"parse": 1, "url": play_url, "header": self.headers}

        html = resp.text

        # 1. 直接匹配 video src 中的 m3u8（最优先，速度最快）
        video_m = self._re_video_src.search(html)
        if video_m:
            return {"parse": 0, "url": video_m.group(1), "header": self.headers}

        # 2. 匹配页面中任何 m3u8 地址
        m3u8_m = self._re_m3u8.search(html)
        if m3u8_m:
            return {"parse": 0, "url": m3u8_m.group(0), "header": self.headers}

        # 3. iframe 嵌套（备用）
        iframe_m = self._re_iframe.search(html)
        if iframe_m:
            iframe_url = iframe_m.group(1)
            if not iframe_url.startswith('http'):
                iframe_url = self._fix_url(iframe_url)
            return {"parse": 1, "url": iframe_url, "header": self.headers}

        # 兜底：返回原页面让播放器嗅探
        return {"parse": 1, "url": play_url, "header": self.headers}

# coding=utf-8
"""
目标站: 云途影视 (gw7.cc)
CMS: 苹果CMS v10 (海螺模板)
特性:
  1. 完整二级分类筛选 (类型/地区/语言/年份/排序)
  2. 搜索功能完善支持
  3. 详情页多线路、多集数正确解析
  4. 播放页提取 player_ JSON 真实 m3u8 地址
  5. 全站预编译正则，极致加载速度
  6. 智能分页与筛选 URL 构建
"""
import re
import sys
import json
import urllib.parse
import urllib.request

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    # ========== 预编译正则 (性能核心) ==========
    # 列表页视频卡片
    _RE_VODLIST = re.compile(
        r'<a class="vodlist_thumb lazyload" href="(/index\.php/vod/detail/id/(\d+)\.html)" title="([^"]+)" data-original="([^"]+)">'
        r'.*?<span class="pic_text[^"]*">\s*([^<]+)\s*</span>',
        re.DOTALL
    )
    # 搜索页视频卡片（结构可能不同：无lazyload、无pic_text、或用src代替data-original）
    _RE_SEARCHLIST = re.compile(
        r'<a[^>]*class="[^"]*vodlist_thumb[^"]*"[^>]*href="(/index\.php/vod/detail/id/(\d+)\.html)"[^>]*title="([^"]+)"[^>]*>'
        r'(?:[^>]*(?:data-original|src)="([^"]+)")?'
        r'.*?(?:<span class="pic_text[^"]*">\s*([^<]*)\s*</span>)?',
        re.DOTALL
    )
    # 分页: 总页数
    _RE_PAGECOUNT = re.compile(
        r'(?:page_total|共\s*(\d+)\s*页|/page/(\d+)\.html[^>]*>尾页|>(\d+)</a>\s*<a[^>]*>尾页)',
        re.DOTALL
    )
    # 详情页标题
    _RE_DETAIL_TITLE = re.compile(r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h1>', re.DOTALL)
    # 详情页封面
    _RE_DETAIL_PIC = re.compile(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"')
    # 详情页简介 (sketch 或 content)
    _RE_DETAIL_CONTENT = re.compile(
        r'<div[^>]*class="[^"]*sketch[^"]*"[^>]*>(.*?)</div>|'
        r'<div[^>]*class="[^"]*vod_content[^"]*"[^>]*>(.*?)</div>',
        re.DOTALL
    )
    # 详情页元信息
    _RE_DETAIL_DIRECTOR = re.compile(r'导演[：:]\s*<a[^>]*>(.*?)</a>', re.DOTALL)
    _RE_DETAIL_ACTOR = re.compile(r'主演[：:]\s*<a[^>]*>(.*?)</a>', re.DOTALL)
    _RE_DETAIL_YEAR = re.compile(r'年份[：:]\s*<a[^>]*>(\d{4})</a>')
    _RE_DETAIL_AREA = re.compile(r'地区[：:]\s*<a[^>]*>(.*?)</a>', re.DOTALL)
    _RE_DETAIL_TYPE = re.compile(r'类型[：:]\s*<a[^>]*>(.*?)</a>', re.DOTALL)
    _RE_DETAIL_LANG = re.compile(r'语言[：:]\s*<a[^>]*>(.*?)</a>', re.DOTALL)
    # 播放页 player_ 数据
    _RE_PLAYER_DATA = re.compile(r'var\s+player_[^=]+=\s*({.*?})</script>', re.DOTALL)
    # 播放线路名 (player_infotip)
    _RE_PLAY_SOURCE = re.compile(r'<div class="player_infotip"[^>]*>(.*?)</div>', re.DOTALL)
    # 播放列表链接
    _RE_PLAY_LINKS = re.compile(
        r'<a[^>]*href="(/index\.php/vod/play/id/\d+/sid/\d+/nid/\d+\.html)"[^>]*>(.*?)</a>',
        re.DOTALL
    )
    # 播放列表区域
    _RE_PLAY_BOX = re.compile(
        r'<div class="play_list_box[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        re.DOTALL
    )

    def init(self, extend=""):
        self.site_url = "https://www.gw7.cc"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.site_url + "/",
        }
        self.default_pic = "https://pic.rmb.bdstatic.com/bjh/user/default.png"
        self._filters = None

    # ========== 工具方法 ==========

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if not url.startswith("http"):
            return urllib.parse.urljoin(self.site_url, url)
        return url

    def _fetch(self, url):
        """带异常处理的请求"""
        try:
            req = urllib.request.Request(url, headers=self.headers)
            # 禁用SSL验证以兼容部分环境
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            response = urllib.request.urlopen(req, timeout=15, context=ctx)
            return response.read().decode('utf-8', errors='ignore')
        except Exception as e:
            self.log(f"请求失败: {url} - {e}")
            return ""

    def _extract_videos(self, html):
        """从 HTML 中提取视频列表（首页 / 分类 / 搜索通用）"""
        videos = []
        seen = set()
        # 先尝试列表页正则（更精确）
        for match in self._RE_VODLIST.finditer(html):
            href = match.group(1)
            vid = match.group(2)
            title = match.group(3).strip()
            pic = match.group(4).strip()
            note = match.group(5).strip()
            if vid in seen:
                continue
            seen.add(vid)
            videos.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": self._fix_url(pic),
                "vod_remarks": note
            })
        # 如果没匹配到，尝试搜索页正则（更宽松）
        if not videos:
            for match in self._RE_SEARCHLIST.finditer(html):
                href = match.group(1)
                vid = match.group(2)
                title = match.group(3).strip()
                pic = match.group(4) or ""
                pic = pic.strip()
                note = match.group(5) or ""
                note = note.strip()
                if not pic:
                    pic = self.default_pic
                if vid in seen:
                    continue
                seen.add(vid)
                videos.append({
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": self._fix_url(pic),
                    "vod_remarks": note
                })
        return videos

    def _get_pagecount(self, html):
        """提取总页数"""
        # 方法1: 找尾页链接
        m = re.search(r'href="/index\.php/vod/(?:type|show|search)/[^"]*/page/(\d+)\.html"[^>]*>尾页', html)
        if m:
            return int(m.group(1))
        # 方法2: 找最大页码
        pages = re.findall(r'/page/(\d+)\.html', html)
        if pages:
            return max(int(p) for p in pages)
        # 方法3: 找共X页
        m = re.search(r'共\s*(\d+)\s*页', html)
        if m:
            return int(m.group(1))
        return 1

    def _get_filters(self):
        """构建二级分类筛选器"""
        if self._filters is not None:
            return self._filters

        # 类型筛选 (class)
        movie_classes = [
            {"n": "全部", "v": ""}, {"n": "动作", "v": "动作"}, {"n": "喜剧", "v": "喜剧"},
            {"n": "爱情", "v": "爱情"}, {"n": "恐怖", "v": "恐怖"}, {"n": "科幻", "v": "科幻"},
            {"n": "剧情", "v": "剧情"}, {"n": "战争", "v": "战争"}, {"n": "警匪", "v": "警匪"},
            {"n": "犯罪", "v": "犯罪"}, {"n": "动画", "v": "动画"}, {"n": "奇幻", "v": "奇幻"},
            {"n": "武侠", "v": "武侠"}, {"n": "冒险", "v": "冒险"}, {"n": "枪战", "v": "枪战"},
            {"n": "悬疑", "v": "悬疑"}, {"n": "惊悚", "v": "惊悚"}, {"n": "经典", "v": "经典"},
            {"n": "青春", "v": "青春"}, {"n": "文艺", "v": "文艺"}, {"n": "微电影", "v": "微电影"},
            {"n": "古装", "v": "古装"}, {"n": "历史", "v": "历史"}, {"n": "运动", "v": "运动"},
            {"n": "农村", "v": "农村"}, {"n": "儿童", "v": "儿童"}, {"n": "网络电影", "v": "网络电影"},
        ]
        tv_classes = [
            {"n": "全部", "v": ""}, {"n": "古装", "v": "古装"}, {"n": "战争", "v": "战争"},
            {"n": "青春偶像", "v": "青春偶像"}, {"n": "喜剧", "v": "喜剧"}, {"n": "家庭", "v": "家庭"},
            {"n": "犯罪", "v": "犯罪"}, {"n": "动作", "v": "动作"}, {"n": "奇幻", "v": "奇幻"},
            {"n": "剧情", "v": "剧情"}, {"n": "历史", "v": "历史"}, {"n": "经典", "v": "经典"},
            {"n": "乡村", "v": "乡村"}, {"n": "情景", "v": "情景"}, {"n": "商战", "v": "商战"},
            {"n": "网剧", "v": "网剧"}, {"n": "其他", "v": "其他"},
        ]
        zongyi_classes = [
            {"n": "全部", "v": ""}, {"n": "选秀", "v": "选秀"}, {"n": "情感", "v": "情感"},
            {"n": "访谈", "v": "访谈"}, {"n": "播报", "v": "播报"}, {"n": "旅游", "v": "旅游"},
            {"n": "音乐", "v": "音乐"}, {"n": "美食", "v": "美食"}, {"n": "纪实", "v": "纪实"},
            {"n": "曲艺", "v": "曲艺"}, {"n": "生活", "v": "生活"}, {"n": "游戏互动", "v": "游戏互动"},
            {"n": "财经", "v": "财经"}, {"n": "求职", "v": "求职"},
        ]
        dongman_classes = [
            {"n": "全部", "v": ""}, {"n": "情感", "v": "情感"}, {"n": "科幻", "v": "科幻"},
            {"n": "热血", "v": "热血"}, {"n": "推理", "v": "推理"}, {"n": "搞笑", "v": "搞笑"},
            {"n": "冒险", "v": "冒险"}, {"n": "萝莉", "v": "萝莉"}, {"n": "校园", "v": "校园"},
            {"n": "动作", "v": "动作"}, {"n": "机战", "v": "机战"}, {"n": "运动", "v": "运动"},
            {"n": "战争", "v": "战争"}, {"n": "少年", "v": "少年"}, {"n": "少女", "v": "少女"},
            {"n": "社会", "v": "社会"}, {"n": "原创", "v": "原创"}, {"n": "亲子", "v": "亲子"},
            {"n": "益智", "v": "益智"}, {"n": "励志", "v": "励志"}, {"n": "其他", "v": "其他"},
        ]

        # 地区 (area)
        areas = [
            {"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
            {"n": "台湾", "v": "台湾"}, {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"},
            {"n": "美国", "v": "美国"}, {"n": "英国", "v": "英国"}, {"n": "法国", "v": "法国"},
            {"n": "德国", "v": "德国"}, {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"},
            {"n": "其他", "v": "其他"},
        ]

        # 语言 (lang)
        langs = [
            {"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "粤语", "v": "粤语"},
            {"n": "英语", "v": "英语"}, {"n": "日语", "v": "日语"}, {"n": "韩语", "v": "韩语"},
            {"n": "泰语", "v": "泰语"}, {"n": "法语", "v": "法语"}, {"n": "德语", "v": "德语"},
            {"n": "其他", "v": "其他"},
        ]

        # 年份 (year)
        years = [{"n": "全部", "v": ""}]
        for y in range(2026, 1999, -1):
            years.append({"n": str(y), "v": str(y)})

        # 排序 (by)
        sorts = [
            {"n": "时间", "v": "time"}, {"n": "人气", "v": "hits"}, {"n": "评分", "v": "score"},
        ]

        def make(class_list):
            return [
                {"key": "class", "name": "类型", "value": class_list},
                {"key": "area", "name": "地区", "value": areas},
                {"key": "lang", "name": "语言", "value": langs},
                {"key": "year", "name": "年份", "value": years},
                {"key": "by", "name": "排序", "value": sorts},
            ]

        self._filters = {
            "1": make(movie_classes),      # 电影
            "2": make(tv_classes),          # 电视剧
            "3": make(zongyi_classes),      # 综艺
            "4": make(dongman_classes),     # 动漫
        }
        return self._filters

    # ========== 首页 ==========

    def homeContent(self, filter):
        categories = [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "电视剧"},
            {"type_id": "3", "type_name": "综艺"},
            {"type_id": "4", "type_name": "动漫"},
        ]
        html = self._fetch(self.site_url + "/")
        videos = self._extract_videos(html) if html else []
        return {
            "class": categories,
            "list": videos[:30],
            "filters": self._get_filters()
        }

    def homeVideoContent(self):
        return self.homeContent(False)

    # ========== 分类 ==========

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        # TVBox 传过来的 extend 可能是 JSON 字符串，需要解析
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except:
                extend = {}
        if not extend:
            extend = {}

        # 清理空值参数（TVBox 可能传空字符串）
        for k in list(extend.keys()):
            if extend[k] == "" or extend[k] is None:
                del extend[k]

        # 构建筛选参数
        paths = [f"id/{tid}"]
        has_filter = False

        if extend.get("class"):
            paths.append(f"class/{urllib.parse.quote(extend['class'])}")
            has_filter = True

        if extend.get("area"):
            paths.append(f"area/{urllib.parse.quote(extend['area'])}")
            has_filter = True

        if extend.get("lang"):
            paths.append(f"lang/{urllib.parse.quote(extend['lang'])}")
            has_filter = True

        if extend.get("year"):
            paths.append(f"year/{extend['year']}")
            has_filter = True

        # 排序（默认 time 不加到 URL）
        by = extend.get("by", "time")
        if by and by != "time":
            paths.append(f"by/{by}")
            has_filter = True

        # 苹果CMS：无筛选用 type 路径，有筛选用 show 路径
        path_type = "show" if has_filter else "type"
        base_path = f"/index.php/vod/{path_type}/" + "/".join(paths)

        if page == 1:
            url = f"{self.site_url}{base_path}.html"
        else:
            url = f"{self.site_url}{base_path}/page/{page}.html"

        self.log(f"分类请求: {url}")
        html = self._fetch(url)

        # fallback：如果 show 路径无结果，尝试 type 路径
        if not html or (html and not self._extract_videos(html)):
            if has_filter:
                fb_path = f"/index.php/vod/type/" + "/".join(paths)
                if page == 1:
                    fb_url = f"{self.site_url}{fb_path}.html"
                else:
                    fb_url = f"{self.site_url}{fb_path}/page/{page}.html"
                self.log(f"分类 fallback: {fb_url}")
                fb_html = self._fetch(fb_url)
                if fb_html and self._extract_videos(fb_html):
                    html = fb_html

        videos = []
        pagecount = 1
        if html:
            videos = self._extract_videos(html)
            pagecount = self._get_pagecount(html)

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 48,
            "total": pagecount * 48
        }

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        keyword = urllib.parse.quote(key)
        # 伪静态 URL
        if page == 1:
            url = f"{self.site_url}/index.php/vod/search/wd/{keyword}.html"
        else:
            url = f"{self.site_url}/index.php/vod/search/wd/{keyword}/page/{page}.html"

        html = self._fetch(url)
        # 如果伪静态返回空或没结果，尝试 GET 参数形式
        if not html or (html and not self._extract_videos(html)):
            get_url = f"{self.site_url}/index.php/vod/search.html?wd={keyword}"
            if page > 1:
                get_url += f"&page={page}"
            html2 = self._fetch(get_url)
            if html2 and self._extract_videos(html2):
                html = html2

        videos = []
        pagecount = 1
        if html:
            videos = self._extract_videos(html)
            pagecount = self._get_pagecount(html)

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 48,
            "total": pagecount * 48
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ========== 详情 ==========

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = str(ids[0])
        url = f"{self.site_url}/index.php/vod/detail/id/{vid}.html"
        html = self._fetch(url)
        if not html:
            return {"list": []}

        # ---- 标题 ----
        name = vid
        year = ""
        title_match = self._RE_DETAIL_TITLE.search(html)
        if title_match:
            name = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
            year_m = re.search(r'(\d{4})', name)
            if year_m:
                year = year_m.group(1)

        # ---- 封面图 ----
        pic = self.default_pic
        pic_match = self._RE_DETAIL_PIC.search(html)
        if pic_match:
            pic = self._fix_url(pic_match.group(1))

        # ---- 简介 ----
        content = ""
        content_match = self._RE_DETAIL_CONTENT.search(html)
        if content_match:
            content = re.sub(r'<[^>]+>', '', content_match.group(1) or content_match.group(2) or "").strip()

        # ---- 导演 / 主演 / 类型 / 地区 / 语言 ----
        director = ""
        actor = ""
        type_name = ""
        area = ""
        lang = ""

        d_m = self._RE_DETAIL_DIRECTOR.search(html)
        if d_m:
            director = re.sub(r'<[^>]+>', '', d_m.group(1)).strip()

        a_m = self._RE_DETAIL_ACTOR.search(html)
        if a_m:
            actor = re.sub(r'<[^>]+>', '', a_m.group(1)).strip()

        t_m = self._RE_DETAIL_TYPE.search(html)
        if t_m:
            type_name = re.sub(r'<[^>]+>', '', t_m.group(1)).strip()

        ar_m = self._RE_DETAIL_AREA.search(html)
        if ar_m:
            area = re.sub(r'<[^>]+>', '', ar_m.group(1)).strip()

        la_m = self._RE_DETAIL_LANG.search(html)
        if la_m:
            lang = re.sub(r'<[^>]+>', '', la_m.group(1)).strip()

        # ---- 播放数据：解析所有线路和分集 ----
        play_from = []
        play_url = []

        # 提取每个 play_list_box（更宽松的匹配）
        play_boxes = re.findall(
            r'<div[^>]*class="[^"]*play_list_box[^"]*"[^>]*>(.*?)(?=<div[^>]*class="[^"]*play_list_box[^"]*"[^>]*>|</div>\s*</div>\s*</div>|$)',
            html, re.DOTALL
        )
        # fallback：如果上面没匹配到，用原来的正则
        if not play_boxes:
            play_boxes = self._RE_PLAY_BOX.findall(html)

        source_counter = {}  # 同名线路计数器

        for idx, box_html in enumerate(play_boxes):
            # 提取线路名
            source_match = self._RE_PLAY_SOURCE.search(box_html)
            source_name = f"线路{idx + 1}"
            if source_match:
                source_tip = re.sub(r'<[^>]+>', '', source_match.group(1)).strip()
                m = re.search(r'由(.+?)提供', source_tip)
                if m:
                    source_name = m.group(1).strip()
                elif source_tip:
                    source_name = source_tip[:20]

            # 同名线路加序号区分（如"蓝光", "蓝光2"）
            base_name = source_name
            if base_name in source_counter:
                source_counter[base_name] += 1
                source_name = f"{base_name}{source_counter[base_name]}"
            else:
                source_counter[base_name] = 1

            # 提取剧集：在每个 box 内找包含最多剧集的 <ul>
            ep_list = []
            ep_seen = set()

            uls = re.findall(r'<ul[^>]*>(.*?)</ul>', box_html, re.DOTALL)
            if uls:
                # 找剧集数最多的 <ul>（排除"最近更新"等短列表）
                best_ul = ""
                best_count = 0
                for ul_html in uls:
                    links = self._RE_PLAY_LINKS.findall(ul_html)
                    if len(links) > best_count:
                        best_count = len(links)
                        best_ul = ul_html
                if best_ul:
                    links = self._RE_PLAY_LINKS.findall(best_ul)
                else:
                    links = self._RE_PLAY_LINKS.findall(box_html)
            else:
                links = self._RE_PLAY_LINKS.findall(box_html)

            for href, ep_name in links:
                ep_clean = re.sub(r'<[^>]+>', '', ep_name).strip()
                if ep_clean and href:
                    key = f"{ep_clean}${href}"
                    if key in ep_seen:
                        continue
                    ep_seen.add(key)
                    ep_list.append(key)

            if ep_list:
                play_from.append(source_name)
                play_url.append("#".join(ep_list))

        # 兜底
        if not play_url:
            play_from = ["默认线路"]
            play_url = [f"播放${vid}"]

        result = [{
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_year": year,
            "vod_area": area,
            "vod_lang": lang,
            "vod_type": type_name,
            "vod_play_from": '$$$'.join(play_from),
            "vod_play_url": '$$$'.join(play_url)
        }]
        return {"list": result}

    # ========== 播放 ==========

    def playerContent(self, flag, id, vipFlags):
        # id 格式: "/index.php/vod/play/id/41536/sid/1/nid/1.html" 或 "HD中字$/index.php/..."
        play_url = id
        if "$" in id:
            play_url = id.split("$")[-1]

        if not play_url.startswith("/index.php/vod/play/"):
            # 兜底
            if play_url.startswith("http"):
                return {"parse": 0, "url": play_url, "header": self.headers}
            return {"parse": 1, "url": f"{self.site_url}/index.php/vod/detail/id/{play_url}.html", "header": self.headers}

        # 访问播放页提取真实 m3u8
        url = f"{self.site_url}{play_url}"
        html = self._fetch(url)
        if html:
            player_match = self._RE_PLAYER_DATA.search(html)
            if player_match:
                try:
                    player_json = json.loads(player_match.group(1))
                    m3u8 = player_json.get("url", "").strip()
                    if m3u8 and m3u8.startswith("http"):
                        return {
                            "parse": 0,
                            "url": m3u8,
                            "header": self.headers
                        }
                except json.JSONDecodeError:
                    pass

        # 兜底：让 TVBox 解析播放页
        return {
            "parse": 1,
            "url": url,
            "header": self.headers
        }

    # ========== 辅助 ==========

    def isVideoFormat(self, url):
        return '.m3u8' in url or '.mp4' in url or url.startswith('http')

    def manualVideoCheck(self):
        return False

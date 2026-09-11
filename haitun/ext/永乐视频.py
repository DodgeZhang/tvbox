import re, json
import html as _html_module
from base.spider import Spider as _BaseSpider
try:
    import requests as _requests
except Exception:
    _requests = None


class Spider(_BaseSpider):
    def __init__(self):
        self.site = "https://ylsp.tv"
        self.name = "ylsp"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S9080) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": self.site,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self.s = self.session = self.sess = _requests.Session() if _requests else None
        self._extend = {}
        self._home = None

    def getDependence(self):
        return []

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        if not url:
            return False
        u = str(url).lower()
        return u.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi")) or "m3u8" in u

    def destroy(self):
        pass

    def action(self, action):
        return {}

    def _get(self, url, referer=None):
        h = dict(self.header)
        if referer:
            h["Referer"] = referer
        if self.s is not None:
            try:
                r = self.s.get(url, headers=h, timeout=12, allow_redirects=True)
                if r.status_code < 400:
                    return r.text
            except Exception:
                pass
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=12) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception:
            return ""

    def _u(self, u):
        if not u:
            return u
        u = u.strip()
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            m = re.match(r"(https?://[^/]+)", self.site)
            return (m.group(1) if m else self.site) + u
        return self.site.rstrip("/") + "/" + u.lstrip("/")

    def _extract_items(self, html):
        """从HTML中提取 module-poster-item 列表项。"""
        out = []
        seen = set()
        # 匹配: <a href="..." title="..." class="...module-poster-item...">
        # 属性顺序不固定，用 href+title+class 组合
        for m in re.finditer(
            r'<a[^>]*href="([^"]+)"[^>]*title="([^"]+)"[^>]*class="[^"]*module-poster-item[^"]*"[^>]*>',
            html, re.S
        ):
            href = m.group(1).strip()
            title = _html_unescape(m.group(2).strip())
            block_end = html.find("</a>", m.end())
            block = html[m.end():block_end + 4] if block_end > 0 else ""
            # 图片: 优先 data-original(懒加载)，其次 src
            img_m = re.search(r'data-original="([^"]+)"', block) or re.search(r'src="([^"]+)"', block)
            pic = self._u(img_m.group(1)) if img_m else ""
            # 备注: module-item-note
            note_m = re.search(r'<div[^>]*class="module-item-note"[^>]*>(.*?)</div>', block, re.S)
            note = _html_unescape(re.sub(r"<[^>]+>", "", note_m.group(1)).strip()) if note_m else ""
            vid = self._u(href)
            if vid in seen:
                continue
            seen.add(vid)
            out.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": note,
            })
        # 搜索页使用 module-card-item-poster，补充兼容该结构。
        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*class="[^"]*module-card-item-poster[^"]*"[^>]*>', html, re.S):
            href = m.group(1).strip(); vid = self._u(href)
            if vid in seen: continue
            scope = html[m.start():m.start()+2600]
            tm = re.search(r'module-card-item-title[^>]*>.*?<a[^>]*>(.*?)</a>', scope, re.S)
            title = _html_unescape(re.sub(r'<[^>]+>', '', tm.group(1)).strip()) if tm else ''
            im = re.search(r'data-original="([^"]+)"', scope) or re.search(r'<img[^>]+src="([^"]+)"', scope)
            seen.add(vid); out.append({"vod_id": vid, "vod_name": title, "vod_pic": self._u(im.group(1)) if im else "", "vod_remarks": ""})
        return out

    def _cats(self):
        if self._home is None:
            self._home = self._get(self.site)
        html = self._home
        out = []
        seen = set()
        # 导航栏: <div class="navbar"> -> <ul class="navbar-items"> -> <li class="navbar-item">
        nav_m = re.search(r'<div[^>]*class="navbar"[^>]*>(.*?)</div>\s*<div[^>]*class="side-op"', html, re.S)
        seg = nav_m.group(1) if nav_m else html
        for lm in re.finditer(r'<li[^>]*class="[^"]*navbar-item[^"]*"[^>]*>(.*?)</li>', seg, re.S):
            block = lm.group(1)
            href_m = re.search(r'href="([^"]+)"', block)
            if not href_m:
                continue
            href = href_m.group(1).strip()
            # 名称: 优先 title 属性, 其次 span 内容
            title_m = re.search(r'title="([^"]+)"', block)
            if title_m:
                name = title_m.group(1)
            else:
                span_m = re.search(r'<span>([^<]+)</span>', block)
                name = span_m.group(1).strip() if span_m else ""
            if not name or len(name) > 12 or name in seen:
                continue
            # 过滤: 只排除真正的噪音, 保留"更新""热榜"
            if any(w in name for w in ("首页", "APP", "登录", "注册", "会员", "充值", "下载", "搜索", "设置", "帮助", "关于", "反馈", "客服", "留言")):
                continue
            # 过滤外部链接
            if href.startswith("http") and "ylsp" not in href and "59v" not in href:
                continue
            seen.add(name)
            out.append({"type_id": self._u(href), "type_name": name})
        return out

    def init(self, extend=""):
        self._extend = {}
        if isinstance(extend, dict):
            self._extend = extend
        elif isinstance(extend, str) and extend.strip():
            try:
                e = json.loads(extend)
                if isinstance(e, dict):
                    self._extend = e
            except Exception:
                pass

    def homeContent(self, filter=None):
        cats = self._cats()
        html = self._home if self._home is not None else self._get(self.site)
        vod_list = self._extract_items(html)
        filters = {}
        for c in cats:
            filters[c["type_id"]] = [
                {"key":"class","name":"分类","value":[
                    {"n":"全部","v":""}, {"n":"动作片","v":"6"},
                    {"n":"喜剧片","v":"7"}, {"n":"爱情片","v":"8"},
                    {"n":"科幻片","v":"9"}, {"n":"奇幻片","v":"10"},
                    {"n":"恐怖片","v":"11"}, {"n":"剧情片","v":"12"},
                    {"n":"战争片","v":"20"}, {"n":"纪录片","v":"21"},
                    {"n":"动画片","v":"26"}, {"n":"悬疑片","v":"22"},
                    {"n":"冒险片","v":"23"}, {"n":"犯罪片","v":"24"},
                    {"n":"惊悚片","v":"45"}, {"n":"歌舞片","v":"46"},
                    {"n":"灾难片","v":"47"}, {"n":"网络片","v":"48"}
                ]},
                {"key":"area","name":"地区","value":[
                    {"n":"全部","v":""}, {"n":"大陆","v":"大陆"},
                    {"n":"香港","v":"香港"}, {"n":"台湾","v":"台湾"},
                    {"n":"日本","v":"日本"}, {"n":"韩国","v":"韩国"},
                    {"n":"欧美","v":"欧美"}, {"n":"英国","v":"英国"},
                    {"n":"泰国","v":"泰国"}, {"n":"其它","v":"其它"}
                ]},
                {"key":"year","name":"年份","value":[{"n":"全部","v":""}]+[{"n":str(y),"v":str(y)} for y in range(2026,2010,-1)]},
                {"key":"by","name":"排序","value":[
                    {"n":"添加时间","v":"time_add"}, {"n":"更新时间","v":"time_update"},
                    {"n":"人气排序","v":"hits"}, {"n":"评分排序","v":"score"}
                ]}
            ]
        return {"class": cats, "list": vod_list, "filters": filters}

    def homeVideoContent(self):
        if self._home is None:
            self._home = self._get(self.site)
        return {"list": self._extract_items(self._home)}

    def _movie_filter_url(self, tid, page, ext):
        """基础分类 + extend 生成筛选 URL；筛选 tid 则只换页码。"""
        from urllib.parse import quote, unquote
        raw = str(tid).strip().rstrip('/')
        if '/vodtype/' in raw:
            tm = re.search(r'/vodtype/([^/]+)', raw)
            route = (tm.group(1).strip('-') + '-----------') if tm else ''
        else:
            route = raw.split('/vodshow/', 1)[-1] if '/vodshow/' in raw else ''
        # 壳传回的 type_id 常带 %E4... 编码；先解码再统一编码，避免 %25 双重编码。
        route = unquote(route)
        ext = ext if isinstance(ext, dict) else {}; page = max(1, int(page))
        base_id=(route.split('-',1)[0] if route else str(tid).strip('/')) or '1'
        class_id = str(ext.get('class', '') or '').strip()
        if class_id.isdigit():
            base_id = class_id
            # 分类筛选要覆盖原始 /vodtype 的类型编号，不能继续沿用旧 route。
            route = base_id + '-----------'
        area = str(ext.get('area', '') or '')
        year = str(ext.get('year', '') or '')
        by = str(ext.get('by', '') or '')
        # 站点筛选字段可以组合；不要只应用第一个字段，否则
        # “类型 + 地区 + 年份”会丢掉后两个条件。
        if not route or route in (base_id, base_id + '-----------'):
            if area:
                route = base_id + '-' + area + '----------'
            elif by:
                route = base_id + '--' + by + '---------'
            else:
                route = base_id + '-----------'
        # 组合筛选：地区后接年份，站点实测格式为
        # /vodshow/9-日本----------2025/。
        if year and not route.endswith(year):
            route = route.rstrip('-') + '-' * (len(route) - len(route.rstrip('-'))) + year

        #   1-地区-------2--- / 1----语言----2--- /
        #   1--排序------2--- / 1--------2---年份
        if page == 1:
            target = route
        elif route.endswith('---'):
            # 地区、语言、排序以及未筛选路由：页码位就在末尾 --- 前。
            target = route[:-3] + str(page) + '---'
        else:
            # 年份路由：年份在末尾，页码位位于年份之前。
            ym = re.match(r'^(.*?)(-{3,})(\d{4})$', route)
            if ym:
                prefix, hyphens, year_value = ym.groups()
                target = prefix + hyphens[:-3] + str(page) + '---' + year_value
            else:
                # 未识别的站点路由不猜其分页格式，沿用站点常见尾段。
                target = route + '-------%d---' % page
        return self.site.rstrip('/') + '/vodshow/' + quote(target, safe='-/') + '/'

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        # 壳端通常传 extend={}、filter={"area":"..."}；空 extend 不能覆盖有值的 filter。
        ext = {}
        for item in (self._extend, extend, filter):
            if isinstance(item, str):
                try: item = json.loads(item)
                except Exception: item = {}
            if isinstance(item, dict):
                ext.update({k:v for k,v in item.items() if v not in (None, '')})
        # 壳有时只传数字 tid（如 "1"），筛选值在 filter/extend 中；不能落入旧 /list/ 路由。
        tid_text = str(tid).strip()
        filter_keys = ('area', 'year', 'by', 'class', 'letter')
        if (tid_text.isdigit() and any(str(ext.get(k, '') or '') for k in filter_keys)):
            tid_text = self.site.rstrip('/') + '/vodshow/' + tid_text + '-----------/'
        # 壳通常始终把原始 /vodtype/ URL 作为 tid 传回；筛选值在
        # filter/extend 中。此时必须切换到真实 /vodshow/ 筛选路由，
        # 不能继续走 _cat_url，否则每个筛选项都会请求同一个分类首页。
        has_filter = any(str(ext.get(k, '') or '') for k in filter_keys)
        if tid_text.startswith(('http://', 'https://')) and '/vodtype/' in tid_text and has_filter:
            m_type = re.search(r'/vodtype/([^/]+)', tid_text)
            if m_type:
                tid_text = self.site.rstrip('/') + '/vodshow/' + m_type.group(1).strip('-') + '-----------/'
        if tid_text.startswith(('http://', 'https://')) and ('/vodshow/' in tid_text or '/vodtype/' in tid_text):
            url = self._movie_filter_url(tid_text, pg, ext)
        elif tid_text.startswith(('http://', 'https://')):
            url = self._cat_url(tid_text, pg)
        else:
            url = self._cat_url(tid, pg)
        html = self._get(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
        vod_list = self._extract_items(html)
        # 分页: maccms 格式 /vodtype/1-2/
        pagecount = 1
        m = re.search(r"共\s*(\d+)\s*页", html)
        if m:
            pagecount = int(m.group(1))
        else:
            # 从分页链接推断
            pages = re.findall(r'href="[^"]*/vodshow/[^"/]*--------(\d+)---/?"', html)
            if pages:
                try:
                    pagecount = max(int(p) for p in pages)
                except ValueError:
                    pass
        return {"list": vod_list, "page": pg, "pagecount": pagecount, "limit": 24, "total": len(vod_list)}

    def _cat_url(self, tid, pg):
        t = str(tid)
        if t.startswith("http"):
            base = t.rstrip("/")
            # 浏览器真实分页：/vodshow/1--------N---/，兼容壳传入 vodtype 或 vodshow tid。
            page = max(1, int(pg))
            m_type = re.search(r'/vodtype/([^/]+)', base)
            if m_type:
                route = m_type.group(1).strip('-')
                return self.site.rstrip('/') + '/vodshow/%s--------%d---/' % (route, page)
            m_show = re.search(r'/vodshow/([^/]+)', base)
            if m_show:
                route = m_show.group(1)
                route = re.sub(r'-+\d+-{3}$', '', route).rstrip('-')
                return self.site.rstrip('/') + '/vodshow/%s--------%d---/' % (route, page)
            if page == 1:
                return base + "/"
            return base + '-%d/' % page
        return self.site.rstrip("/") + "/list/" + t + ".html?page=%d" % pg

    def detailContent(self, ids):
        vid = ids
        if isinstance(ids, (list, tuple)):
            vid = ids[0] if ids else ""
        vid = str(vid).strip()
        # vid 可能是完整URL或纯ID
        if vid.startswith(("http", "/")):
            url = self._u(vid)
        else:
            url = self.site.rstrip("/") + "/voddetail/%s/" % vid
        html = self._get(url)
        if not html:
            return {"list": []}
        # 标题
        title = ""
        tm = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S) or \
             re.search(r'<title[^>]*>([^<]{2,60})</title>', html)
        if tm:
            title = _html_unescape(re.sub(r"<[^>]+>", "", tm.group(1))).strip()
        # 封面
        pic = ""
        im = re.search(r'<img[^>]+(?:data-original|src)="([^"]+)"[^>]*class="[^"]*pic[^"]*"', html) or \
             re.search(r'property="og:image" content="([^"]+)"', html)
        if im:
            pic = self._u(im.group(1))
        # 简介
        desc = ""
        dm = re.search(r'property="og:description" content="([^"]+)"', html) or \
             re.search(r'<div[^>]*class="[^"]*desc[^"]*"[^>]*>([\s\S]{10,2000}?)</div>', html, re.S)
        if dm:
            desc = _html_unescape(re.sub(r"<[^>]+>", "", dm.group(1))).strip()
        # 详情元数据：按页面真实标签提取，补齐壳端可识别字段；
        # 编剧、语言、上映、更新、集数等非标准字段并入简介，避免丢失。
        def _info_value(label):
            mm = re.search(
                r'<div[^>]*class="module-info-item"[^>]*>\s*'
                r'<span[^>]*class="module-info-item-title"[^>]*>' + re.escape(label) +
                r'[^<]*</span>(.*?)</div>\s*</div>', html, re.S)
            if not mm:
                return ''
            return _html_unescape(re.sub(r'<[^>]+>', '', mm.group(1))).strip()

        director = _info_value('导演：')
        writer = _info_value('编剧：')
        actor = _info_value('主演：')
        duration = _info_value('片长：')
        language = _info_value('语言：')
        publish = _info_value('上映：')
        update = _info_value('更新：')
        episodes = _info_value('集数：')
        year = ''
        area = ''
        ym = re.match(r'(\d{4})\s*(?:\(([^)]+)\))?', publish)
        if ym:
            year, area = ym.group(1) or '', ym.group(2) or ''
        extra = []
        for label, value in (('编剧', writer), ('语言', language), ('上映', publish),
                             ('更新', update), ('集数', episodes), ('片长', duration)):
            if value:
                extra.append(label + '：' + value)
        if extra:
            desc = (desc + '\n' if desc else '') + '\n'.join(extra)

        # 播放源/集数
        play_from_list = []
        play_url_list = []
        # 提取源名称 (module-tab-item, 排除"选择播放线路")
        source_tabs = re.findall(r'<div[^>]*class="[^"]*module-tab-item[^"]*"[^>]*>(.*?)</div>', html, re.S)
        source_names = []
        for tab in source_tabs:
            name = _html_unescape(re.sub(r"<[^>]+>", "", tab).strip())
            if name and name != "选择播放线路" and name not in source_names:
                source_names.append(name)
        # 播放列表按真实 /play/{id}-{sid}-{nid} 链接分组，避免嵌套 div 截断。
        grouped = {}
        for pm in re.finditer(r'<a[^>]+href="([^"#]*?/play/[^"/]+-([0-9]+)-([0-9]+)/?)"[^>]*>(?:<span>)?([^<]{1,30}?)(?:</span>)?</a>', html, re.S):
            href, sid, nid, label = pm.group(1), pm.group(2), pm.group(3), _html_unescape(pm.group(4).strip())
            grouped.setdefault(sid, [])
            if not any(href == x[0] for x in grouped[sid]):
                grouped[sid].append((href, label or ("第" + nid + "集")))
        for idx, sid in enumerate(sorted(grouped, key=lambda x: int(x))):
            eps = ["%s$%s" % (label, self._u(href)) for href, label in grouped[sid]]
            if eps:
                from_name = source_names[idx] if idx < len(source_names) else ("线路%d" % (idx + 1))
                play_from_list.append(from_name)
                play_url_list.append("#".join(eps))
        play_from = "$$$".join(play_from_list) if play_from_list else ""
        play_url = "$$$".join(play_url_list) if play_url_list else ""
        return {"list": [{"vod_id": vid, "vod_name": title, "vod_pic": pic,
                           "vod_year": year, "vod_area": area,
                           "vod_director": director, "vod_actor": actor,
                           "vod_content": desc, "vod_play_from": play_from,
                           "vod_play_url": play_url}]}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            from urllib.parse import quote
            url = self.site + "/vodsearch/" + quote(str(key)) + "-------------/"
        except Exception:
            return {"list": []}
        html = self._get(url)
        if not html:
            return {"list": []}
        return {"list": self._extract_items(html)}

    def playerContent(self, flag, ids, vipFlags=None):
        url = ids
        if isinstance(ids, (list, tuple)):
            url = ids[0] if ids else ""
        url = str(url or "").strip()
        if not url:
            return {"parse": 0, "url": "", "header": dict(self.header)}
        if not url.startswith("http"):
            url = self._u(url)
        u = url.lower()
        if u.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi")) or "m3u8" in u:
            return {"parse": 0, "url": url, "header": dict(self.header)}
        html = self._get(url, referer=self.site)
        if not html:
            return {"parse": 0, "url": "", "header": dict(self.header)}
        found = ""
        # player_aaaa JSON -> url 字段
        m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.S) or re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\});', html, re.S)
        if m:
            try:
                player_obj = json.loads(m.group(1))
                found = player_obj.get("url", "")
            except Exception:
                pass
        if not found:
            m = re.search(r'var\s+now\s*=\s*["\']([^"\']+)', html) or \
                re.search(r'<source[^>]+src=["\']([^"\']+)', html) or \
                re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
            if m:
                found = m.group(1)
        if not found:
            return {"parse": 0, "url": "", "header": dict(self.header)}
        found = found.strip()
        if found.startswith("//"):
            found = "https:" + found
        elif not found.startswith("http"):
            found = self._u(found)
        return {"parse": 0, "url": found, "header": dict(self.header)}

    def localProxy(self, param):
        u = param.get("url", "") if isinstance(param, dict) else ""
        if not u:
            return [403, "text/plain", b"", None]
        h = dict(self.header)
        if self.s is not None:
            try:
                r = self.s.get(u, headers=h, timeout=15)
                return [200, r.headers.get("Content-Type", "application/octet-stream"), r.content, None]
            except Exception:
                pass
        try:
            import urllib.request
            req = urllib.request.Request(u, headers=h)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return [200, resp.headers.get("Content-Type", "application/octet-stream"), resp.read(), None]
        except Exception:
            return [403, "text/plain", b"", None]


def _html_unescape(s):
    return _html_module.unescape(s) if s else s
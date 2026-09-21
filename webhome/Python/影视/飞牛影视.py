#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导航:   https://www.qiushui.vip   
        https://www.qiushuitv.cn
        https://www.qiushuiying.cn
由「影视py源生成器」自动生成 2026-09-15 14:02
站点: https://www.ntmsxy.com

"""
import re
import json
import base64
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

try:
    from base.spider import Spider as _BaseSpider
except ImportError:
    class _BaseSpider(object):
        """脱离影视壳独立运行时的占位基类，便于本地自检"""


class Spider(_BaseSpider):
    name = "飞牛影视"
    base_url = "https://www.ntmsxy.com"
    site_url = "https://www.ntmsxy.com"
    prefix = ""          # 苹果CMS路径前缀：/index.php 或 空
    encoding = "utf-8"      # 站点编码（探测结果，仅参考，运行时仍自动探测）

    class_name = ['电影', '预告片', '动画片', '奇幻片', '犯罪片', '悬疑片', '纪录片', '战争片', '剧情片', '恐怖片', '科幻片', '爱情片', '喜剧片', '动作片', '电视剧', '海外剧', '欧美剧', '日韩剧', '港台剧', '国产剧', '综艺', '港台综艺', '欧美综艺', '日韩综艺', '大陆综艺', '动漫', '其他动漫', '欧美动漫', '日韩动漫', '国产动漫', '短剧']
    class_url = ['1', '32', '31', '16', '15', '14', '13', '12', '11', '10', '9', '8', '7', '6', '2', '22', '21', '20', '18', '17', '3', '26', '25', '24', '23', '4', '30', '29', '28', '27', '5']

    # 由样本URL归纳的分页/搜索模式（非苹果CMS路径风格时优先使用）
    cat_pattern = 'https://www.ntmsxy.com/ntmsxytp/{cid}-{pg}.html'
    search_pattern = 'https://www.ntmsxy.com/ntmsxysc/{key}-------------.html'

    # 筛选配置：filter_mode=html(网页筛选路由) / 空(不支持)
    _filter_mode = ''
    _filter_data = {}
    _filter_names = {
        "class": "类型", "area": "地区", "lang": "语言",
        "year": "年份", "letter": "字母", "by": "排序",
    }

    # 详情路由族：maccms(动态) / voddetail(静态飞飞) / seacms(海洋) / detail(通用)
    #             / pathslug(路径前缀) / custom(自定义重写路由)
    detail_route = "custom"
    # pathslug 族的内容前缀（如 movie/series），vod_id 形如 prefix/slug
    sections = []
    # custom 族：自定义重写路由（如 /ntmsxydt/{vid}.html 详情、/ntmsxytp/{cid}-{pg}.html 分类）
    det_tpl = '/ntmsxydt/{vid}.html'
    det_rx = re.compile('/ntmsxydt/(\\d+)\\.html')

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.ntmsxy.com/",
    }
    timeout = 15
    page_size = 20

    _session = None

    def getName(self):
        return self.name

    def init(self, extend=""):
        return ""

    def getHeaders(self):
        return self.headers

    def _get_session(self):
        if self._session is None:
            s = requests.Session()
            s.trust_env = False
            s.headers.update(self.headers)
            self._session = s
        return self._session

    @staticmethod
    def _decode(r):
        # 编码探测: meta charset -> Content-Type -> apparent -> 逐个回退
        raw = r.content
        head = raw[:4096].decode("ascii", errors="ignore")
        enc = ""
        m = re.search(r'<meta[^>]+charset=["\']?\s*([\w\-]+)', head, re.I)
        if m:
            enc = m.group(1).lower()
        if not enc:
            m = re.search(r'charset=["\']?([\w\-]+)', r.headers.get("Content-Type", ""), re.I)
            if m:
                enc = m.group(1).lower()
        if not enc:
            try:
                enc = (r.apparent_encoding or "utf-8").lower()
            except Exception:
                enc = "utf-8"
        try:
            text = raw.decode(enc, errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
        if text.count("\ufffd") > 20:
            best, bad = text, text.count("\ufffd")
            for e in ("utf-8", "gb18030", "gbk", "big5"):
                try:
                    t = raw.decode(e, errors="replace")
                    if t.count("\ufffd") < bad:
                        best, bad = t, t.count("\ufffd")
                except Exception:
                    continue
            text = best
        return text

    def _get(self, url, retries=2):
        for i in range(retries):
            try:
                r = self._get_session().get(url, timeout=self.timeout)
                if r.status_code == 200 and r.content:
                    return self._decode(r)
                print(f"[{self.name}] GET {url} 状态码={r.status_code}")
                if r.status_code == 404:
                    return ""  # 明确不存在，不重试，节省请求次数（避免触发限频）
            except Exception as e:
                print(f"[{self.name}] GET 异常({i + 1}/{retries}): {url} -> {e}")
        return ""

    def _soup(self, html):
        return BeautifulSoup(html, "html.parser")

    def _clean(self, text):
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", str(text))
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        return re.sub(r"\s+", " ", text).strip()

    def _abs(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return urljoin(self.base_url, u)
        return u

    # ---------- 列表卡片提取（兼容多种CMS模板，逐个尝试） ----------
    _DETAIL_RX = [
        re.compile(r"/vod/detail/id/(\d+)"),          # 动态苹果CMS
        re.compile(r"/voddetail\d*/(\d+)"),           # 静态飞飞 /voddetail/5.html、/voddetail2/5.html
        re.compile(r"/voddetail(\d+)\.html"),          # 静态飞飞无斜杠 /voddetail5.html
        re.compile(r"/detail/id/(\d+)"),               # 海洋CMS
        re.compile(r"/detail/(\d+)\.html"),            # 通用 /detail/5.html
        re.compile(r"/detail/\?(\d+)"),                # 通用 /detail/?5
    ]

    def _match_detail(self, href):
        href = href or ""
        # custom 族：自定义重写路由（如 /ntmsxydt/9.html）
        if self.detail_route == "custom" and self.det_rx is not None:
            m = self.det_rx.search(href)
            if m:
                return m.group(1)
        # 路径前缀族：/{prefix}/{slug}.html（prefix 属于探测到的内容分区）
        if self.detail_route == "pathslug" and self.sections:
            m = re.match(r"^/([a-z][a-z0-9_-]{1,20})/([^/?#\"]+)\.html?$", href)
            if m and m.group(1) in self.sections:
                return m.group(1) + "/" + m.group(2)
        for rx in self._DETAIL_RX:
            m = rx.search(href)
            if m:
                return m.group(1)
        # 非动态苹果CMS站点可能是字母slug型详情链接（如 /detail/xxx）
        if self.detail_route and self.detail_route != "maccms":
            m = re.search(
                r"/(?:voddetail\d*|detail(?:/id)?)/([^/?#\"]{1,160}?)(?:\.html?)?(?:[?#].*)?$",
                href)
            if m:
                return m.group(1)
        return ""

    def _has_detail(self, html):
        if self.detail_route == "custom" and self.det_rx is not None:
            return bool(self.det_rx.search(html or ""))
        if self.detail_route == "pathslug" and self.sections:
            secs = "|".join(re.escape(s) for s in self.sections)
            if re.search(rf"/({secs})/[^/?#\"]+\.html", html or ""):
                return True
        return bool(re.search(
            r"/(?:vod/detail/id/|voddetail\d*/?\d|detail/id/\d|detail/[\w-]{4,})",
            html or ""))

    def _extract_cards(self, soup, limit=40):
        seen, seen_url, items = set(), set(), []
        for a in soup.find_all("a", href=True):
            vid = self._match_detail(a.get("href", ""))
            if not vid or vid in seen:
                continue
            seen.add(vid)
            seen_url.add(urljoin(self.base_url, a.get("href", "")))
            img = a.find(["img", "amp-img"]) or (a.parent.find(["img", "amp-img"])
                                                  if a.parent else None)
            pic = ""
            if img:
                pic = (img.get("data-src") or img.get("data-original")
                       or img.get("data-background") or img.get("src") or "")
            name = (a.get("title") or "").strip()
            if not name and img is not None:
                name = (img.get("alt") or "").strip()
            if not name or len(name) > 40:
                # 锚点文本可能带出整段简介，改取锚点内合理长度的标题节点
                t2 = ""
                for cand in a.find_all(["h1", "h2", "h3", "h4", "span",
                                        "p", "strong", "em"]):
                    t = cand.get_text(strip=True)
                    if 1 < len(t) <= 40:
                        t2 = t
                        break
                if t2:
                    name = t2
                elif len(name) > 40:
                    name = name[:40]
            if not name and img is None:
                continue
            remarks = ""
            box = a.parent
            for _ in range(3):
                if box is None:
                    break
                t = box.get_text(" ", strip=True)
                if name and name in t:
                    t = t.replace(name, " ").strip()
                if t:
                    remarks = t[:30]
                    break
                box = box.parent
            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": self._abs(pic),
                "vod_remarks": remarks,
            })
            if len(items) >= limit:
                break
        if len(items) < 5:
            # 苹果CMS特征未命中时，用通用容器启发式兜底
            for it in self._cards_heuristic(soup, limit):
                if it["vod_id"] not in seen:
                    seen.add(it["vod_id"])
                    items.append(it)
        return items

    def _cards_heuristic(self, soup, limit=40):
        """通用启发式：找 子项含(链接+图片) 最多的容器当列表"""
        best, best_score = None, 0
        for tag in soup.find_all(["ul", "div", "section", "dl", "tbody"]):
            children = tag.find_all(recursive=False)
            if len(children) < 3:
                continue
            cnt = 0
            for c in children:
                a = c if c.name == "a" else c.find("a", href=True)
                if a is not None and c.find(["img", "amp-img"]) is not None:
                    cnt += 1
            if cnt < 3:
                continue
            score = cnt
            cls = " ".join(tag.get("class") or []).lower()
            if any(k in cls for k in ("list", "item", "video", "grid", "movie",
                                      "vod", "pic", "module", "content")):
                score = int(score * 1.6)
            if score > best_score:
                best_score, best = score, tag
        rows = (best.find_all(recursive=False) if best is not None
                else [a for a in soup.find_all("a", href=True)
                      if a.find(["img", "amp-img"])])
        items, seen = [], set()
        for row in rows:
            try:
                a = row if row.name == "a" else row.find("a", href=True)
                if a is None:
                    continue
                href = a.get("href") or ""
                if not href or href.startswith(("javascript:", "#", "mailto:")):
                    continue
                full = urljoin(self.base_url, href)
                if full in seen or full in seen_url \
                        or full.rstrip("/") == self.base_url.rstrip("/"):
                    continue
                seen.add(full)
                img = row.find(["img", "amp-img"])
                pic = ""
                if img:
                    pic = (img.get("data-src") or img.get("data-original")
                           or img.get("data-echo") or img.get("src") or "")
                title = (a.get("title") or "").strip()
                if not title and img:
                    title = (img.get("alt") or "").strip()
                if not title:
                    for cand in row.find_all(["h1", "h2", "h3", "h4", "a", "span", "p"]):
                        t = cand.get_text(strip=True)
                        if 1 < len(t) <= 40:
                            title = t
                            break
                if not title and not pic:
                    continue
                remark = ""
                for cand in row.find_all(["span", "em", "p", "div"]):
                    t = cand.get_text(strip=True)
                    if t and len(t) <= 14 and re.search(r"(更新|全|集|HD|BD|第|期|完结)", t):
                        remark = t
                        break
                items.append({
                    "vod_id": full,
                    "vod_name": title or "未知",
                    "vod_pic": self._abs(pic),
                    "vod_remarks": remark,
                })
                if len(items) >= limit:
                    break
            except Exception:
                continue
        return items

    def homeContent(self, filter=False):
        result = {"class": [{"type_id": t, "type_name": n}
                            for t, n in zip(self.class_url, self.class_name)],
                  "filters": self._build_filters() if self._filter_mode else {}, "list": []}
        try:
            html = self._get(self.base_url + "/")
            if not html or len(html) < 500:
                # 部分站点根路径返回跳转/验证页，真实首页在 /index.php
                html = self._get(self.base_url + "/index.php")
            if not html:
                return result
            result["list"] = self._extract_cards(self._soup(html), limit=30)
        except Exception as e:
            print(f"[{self.name}] 首页异常: {e}")
        return result

    def homeVideoContent(self):
        return self.homeContent()

    def categoryContent(self, tid, pg, filter=False, extend=None, content=None):
        page = int(pg) if str(pg).isdigit() and int(pg) > 0 else 1
        result = {"list": [], "page": page, "pagecount": 1,
                  "limit": self.page_size, "total": 0}
        try:
            tid_s = str(tid)
            ext = self._ext_dict(extend, content)
            ext = {k: str(v) for k, v in ext.items()
                   if str(v) and k in (self._filter_data.get(tid_s) or {})}
            cands = []
            if tid_s == "home":
                # 伪分类：无导航站点用首页推荐当分类
                cands.append(self.base_url + "/")
            else:
                if self.detail_route == "pathslug" and tid_s in (self.sections or []):
                    # 路径前缀族分类：/{prefix}/ 与 /{prefix}/?page=N
                    cands.append(self.base_url + f"/{tid_s}/")
                    if page > 1:
                        cands.append(self.base_url + f"/{tid_s}/?page={page}")
                    cands.append(self.base_url + f"/{tid_s}/index{page}.html" \
                                 if page > 1 else self.base_url + f"/{tid_s}/index.html")
                if ext and self._filter_mode:
                    # 筛选请求优先走苹果CMS筛选路由
                    cands.append(self._build_show_url(tid_s, page, ext))
                if self.cat_pattern:
                    u = (self.cat_pattern
                         .replace("{cid}", tid_s).replace("{pg}", str(page)))
                    if not re.match(r"^https?://", u):
                        u = urljoin(self.base_url, u)
                    if page <= 1:
                        # 静态CMS首页地址通常是 /vodtype/tid.html 而非 -1 后缀
                        cands.append(re.sub(r"-1\.html$", ".html", u))
                    cands.append(u)
                # 静态飞飞路由 /vodtype/tid.html、/vodtype/tid-pg.html
                cands.append(self.base_url + f"/vodtype/{tid_s}.html")
                if page > 1:
                    cands.append(self.base_url + f"/vodtype/{tid_s}-{page}.html")
                for style in ("show", "type"):
                    path = f"{self.prefix}/vod/{style}/id/{tid_s}"
                    if page > 1:
                        path += f"/page/{page}"
                    cands.append(self.base_url + path + ".html")
            html = ""
            cands = list(dict.fromkeys(cands))
            for i, u in enumerate(cands):
                got = self._get(u)
                if got and (self._has_detail(got) or i == len(cands) - 1):
                    html = got
                    break
                if got and not html:
                    html = got
            if not html:
                return result
            soup = self._soup(html)
            items = self._extract_cards(soup, limit=60)
            if not items and page <= 1:
                # 所有分类路由都失效时，退化用首页推荐，保证源可用
                try:
                    home = self._get(self.base_url + "/") or \
                        self._get(self.base_url + "/index.php")
                    if home:
                        items = self._extract_cards(self._soup(home), limit=60)
                except Exception:
                    pass
            result["list"] = items
            result["total"] = len(items)
            maxpg = 0
            for m in re.finditer(r"/vod/show/[^\"']*?/page/(\d+)\.html", html):
                maxpg = max(maxpg, int(m.group(1)))
            for m in re.finditer(r"/vodtype/\d+-(\d+)\.html", html):
                maxpg = max(maxpg, int(m.group(1)))
            for m in re.finditer(r'href="[^"\']*\?(?:page|p)=(\d+)', html):
                maxpg = max(maxpg, int(m.group(1)))
            for m in re.finditer(r'href="[^"]*?/(\d+)\.html"[^>]*>[^<]*下一?[页页]', html):
                maxpg = max(maxpg, int(m.group(1)))
            if maxpg > page:
                result["pagecount"] = maxpg
            elif len(items) >= self.page_size:
                result["pagecount"] = page + 1
        except Exception as e:
            print(f"[{self.name}] 分类异常: {e}")
        return result

    # ---------- 筛选支持（参考「神仙影视-3.py」） ----------

    def _build_filters(self):
        filters = {}
        for tid, dims in self._filter_data.items():
            arr = []
            for param in ("class", "area", "lang", "year", "letter", "by"):
                if param not in dims:
                    continue
                arr.append({
                    "key": param,
                    "name": self._filter_names.get(param, param),
                    "init": "",
                    "value": [{"n": label, "v": val} for label, val in dims[param]],
                })
            if arr:
                filters[tid] = arr
        return filters

    @staticmethod
    def _ext_dict(extend, content=None):
        ext = extend if extend is not None else content
        if isinstance(ext, str) and ext:
            try:
                import json as _json
                ext = _json.loads(ext)
            except Exception:
                ext = {}
        return ext if isinstance(ext, dict) else {}

    def _build_show_url(self, tid, pg, extend):
        """苹果CMS筛选页路径：{prefix}/vod/show/by/../area/../class/../id/{tid}/lang/../year/../letter/../page/{pg}.html"""
        ext = extend or {}
        by = ext.get("by", "")
        area = ext.get("area", "")
        cls = ext.get("class", "")
        lang = ext.get("lang", "")
        year = ext.get("year", "")
        letter = ext.get("letter", "")
        path = f"{self.prefix}/vod/show/"
        if by:
            path += f"by/{by}/"
        if area:
            path += "area/%s/" % quote(str(area))
        if cls:
            path += "class/%s/" % quote(str(cls))
        path += "id/%s" % tid
        if lang:
            path += "/lang/%s" % quote(str(lang))
        if year:
            path += "/year/%s" % quote(str(year))
        if letter:
            path += "/letter/%s" % quote(str(letter))
        if pg and int(pg) > 1:
            path += "/page/%s.html" % pg
        else:
            path += ".html"
        return self.base_url + path

    def _detail_urls(self, vid):
        """按路由族构造详情页候选地址"""
        b = self.base_url
        if self.detail_route == "custom" and self.det_tpl:
            return [self.base_url + self.det_tpl.replace("{vid}", str(vid))]
        if self.detail_route == "voddetail":
            return [f"{b}/voddetail/{vid}.html", f"{b}/voddetail{vid}.html",
                    f"{b}/voddetail2/{vid}.html"]
        if self.detail_route == "seacms":
            return [f"{b}/detail/id/{vid}.html", f"{b}/detail/?{vid}.html"]
        if self.detail_route == "detail":
            return [f"{b}/detail/{vid}.html", f"{b}/detail/{vid}",
                    f"{b}/detail/?{vid}.html", f"{b}/detail/id/{vid}.html",
                    f"{b}/voddetail/{vid}.html"]
        if self.detail_route == "pathslug":
            # vod_id 形如 prefix/slug（相对路径）
            return [f"{b}/{vid}", f"{b}/{vid}.html"]
        return [f"{b}{self.prefix}/vod/detail/id/{vid}.html"]

    # 常见错误页特征（详情候选页排除用）
    _ERR_MARKS = ("could not be found", "page not found", "404 not found",
                  "页面不存在", "内容不存在", "您访问的页面", "无法找到",
                  "内容正在审核", "参数错误")

    @classmethod
    def _looks_error(cls, html):
        low = (html or "")[:4000].lower()
        return any(m in low for m in cls._ERR_MARKS)

    def detailContent(self, ids):
        result = {"list": []}
        vid = ""
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0]) if ids else ""
        elif isinstance(ids, dict):
            vid = str(ids.get("vod_id") or ids.get("id") or "")
        elif ids is not None:
            vid = str(ids)
        vid = str(vid)
        try:
            if re.match(r"^https?://", vid):
                # 启发式模式下列表项直接存详情页URL
                url = vid
                html = self._get(url)
            else:
                vid = vid.strip().strip("/")
                if not vid:
                    return result
                if "/" in vid and self.detail_route != "pathslug":
                    return result
                html = ""
                for u in self._detail_urls(vid):
                    got = self._get(u)
                    if got and len(got) > 500 and not self._looks_error(got):
                        html = got
                        break
            if not html:
                return result
            soup = self._soup(html)

            node = soup.select_one("h1") or soup.select_one("h2") or soup.select_one(".title")
            vod_name = node.get_text(strip=True) if node else ""

            pic_node = (soup.select_one(".module-item-pic img")
                        or soup.select_one(".content_thumb img")
                        or soup.select_one("img[data-original]")
                        or soup.select_one("img[data-src]")
                        or soup.select_one("amp-img[src]"))
            vod_pic = ""
            if pic_node:
                vod_pic = (pic_node.get("data-src") or pic_node.get("data-original")
                           or pic_node.get("src") or "")

            # 基础信息：先试常见模板结构，再用整页文本正则兜底
            info = {}
            for row in soup.select(".video-info-items"):
                t = row.select_one(".video-info-itemtitle")
                if not t:
                    continue
                key = re.sub(r"[：:]", "", t.get_text(strip=True))
                val = row.select_one(".video-info-item")
                if val:
                    info[key] = val.get_text(" ", strip=True)
            if not info:
                full = soup.get_text(" ", strip=True)
                for key, pat in (("导演", r"导演[：:]\s*([^ ]{1,40})"),
                                 ("主演", r"主演[：:]\s*([^ ]{1,60})"),
                                 ("年份", r"(?:年代|年份)[：:]\s*(\d{4})"),
                                 ("地区", r"地区[：:]\s*(\S{1,10})"),
                                 ("类型", r"类型[：:]\s*(\S{1,10})"),
                                 ("状态", r"(?:状态|备注|更新)[：:]\s*(\S{1,20})")):
                    m = re.search(pat, full)
                    if m:
                        info[key] = m.group(1).strip()

            desc = (soup.select_one(".video-info-content") or soup.select_one(".sqjj_a")
                    or soup.select_one(".stui-content__desc") or soup.select_one(".vodplayinfo"))
            vod_content = self._clean(desc.get_text(" ", strip=True)) if desc else ""

            # 剧集：按链接特征分线路。动态maccms存 vid-sid-nid 数字引用，
            # 其余（vodplay/v_play/vplay/简单播放页）直接存完整播放页地址，
            # 这样 playerContent 无需猜测播放页路由，失败时也能回退嗅探正确 URL
            groups = {}
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                m = re.search(r"/vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)", href)
                if m:
                    ref_vid, sid, nid = m.groups()
                    ref = f"{ref_vid}-{sid}-{nid}"
                else:
                    m = re.search(r"/(?:vodplay|v_play|vplay)/(\d+)-(\d+)-(\d+)\.html", href)
                    if m:
                        sid, nid = m.group(2), m.group(3)
                        ref = urljoin(self.base_url, href)
                    else:
                        # 自定义前缀族播放页：/{任意前缀}/{vid}-{sid}-{nid}.html
                        m = re.search(r"/[a-z0-9_-]{1,30}/(\d+)-(\d+)-(\d+)\.html?$", href)
                        if m:
                            sid, nid = m.group(2), m.group(3)
                            ref = urljoin(self.base_url, href)
                        else:
                            m2 = re.search(r"^/(?:play|v|watch)/[^/?#]+-(\d+)\.html?$", href)
                            if not m2:
                                continue
                            sid, nid = "1", m2.group(1)
                            ref = urljoin(self.base_url, href)
                ep = a.get_text(strip=True) or f"第{nid}集"
                groups.setdefault(sid, {})[nid] = (ep, ref)

            line_names, line_urls = [], []
            tabs = (soup.select(".module-player-tab .module-tab-item")
                    or soup.select(".module-tab-item[data-dropdown-value]")
                    or soup.select("[id*='playList'] .module-tab-item")
                    or soup.select(".player-tab-btn, .tab-btn"))
            if groups:
                for i, sid in enumerate(sorted(groups, key=lambda x: int(x))):
                    name = ""
                    if i < len(tabs):
                        name = tabs[i].get("data-dropdown-value") or tabs[i].get_text(strip=True)
                    line_names.append(name or f"线路{sid}")
                    eps = groups[sid]
                    line_urls.append("#".join(
                        f"{eps[n][0]}${eps[n][1]}" for n in sorted(eps, key=lambda x: int(x))))
            else:
                # 通用启发式兜底：按播放链接特征聚组，集数直接存完整URL
                for name, eps in self._play_groups_heuristic(soup):
                    line_names.append(name)
                    line_urls.append("#".join(eps))

            vod = {
                "vod_id": str(vid),
                "vod_name": vod_name,
                "vod_pic": self._abs(vod_pic),
                "vod_year": info.get("年份", info.get("年代", "")),
                "vod_area": info.get("地区", ""),
                "vod_actor": info.get("主演", info.get("演员", "")),
                "vod_director": info.get("导演", ""),
                "vod_type": info.get("类型", ""),
                "vod_remarks": info.get("状态", info.get("备注", "")),
                "vod_content": vod_content,
                "vod_play_from": "$$$".join(line_names) or "默认线路",
                "vod_play_url": "$$$".join(line_urls),
            }
            result["list"].append(vod)
        except Exception as e:
            import traceback
            print(f"[{self.name}] 详情异常: {e}")
            traceback.print_exc()
        return result

    def searchContent(self, key, quick=None, pg="1"):
        page = int(pg) if str(pg).isdigit() and int(pg) > 0 else 1
        result = {"list": [], "page": page, "pagecount": 1,
                  "limit": self.page_size, "total": 0}
        if not key:
            return result
        kw = quote(str(key), safe="")
        urls = []
        if self.search_pattern:
            u = (self.search_pattern
                 .replace("{key}", kw).replace("{pg}", str(page)))
            if not re.match(r"^https?://", u):
                u = urljoin(self.base_url, u)
            urls.append(u)
        urls += [
            f"{self.base_url}{self.prefix}/vod/search/page/{page}/wd/{kw}.html",
            f"{self.base_url}{self.prefix}/vod/search.html?wd={kw}"
            + (f"&page={page}" if page > 1 else ""),
            # 苹果CMS静态化搜索路由（dash分段，页码在第11段）
            f"{self.base_url}/vodsearch/{kw}----------{page}---.html",
            f"{self.base_url}/vodsearch/{kw}-------------.html",
            # 自建模板常见站内搜索路由
            f"{self.base_url}/search/?keyword={kw}&page={page}",
            f"{self.base_url}/search?wd={kw}&page={page}",
        ]
        for u in urls:
            try:
                html = self._get(u)
                if not html:
                    continue
                items = self._extract_cards(self._soup(html), limit=60)
                if items:
                    result["list"] = items
                    result["total"] = len(items)
                    result["pagecount"] = page + 1 if len(items) >= self.page_size else page
                    break
            except Exception as e:
                print(f"[{self.name}] 搜索异常: {e}")
        return result

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ---------- 通用播放链接启发式（借鉴「小白一键生成器」） ----------
    @staticmethod
    def _is_play_link(a):
        href = (a.get("href") or "").lower()
        if not href or href.startswith(("javascript:", "#", "mailto:")):
            return False
        text = a.get_text(strip=True)
        if re.search(r"/(vodplay|vplay|play|watch|v)/", href):
            return True
        if re.search(r"第\s*\d+\s*[集话期]", text):
            return True
        # 纯数字文本（集号）：排除筛选/分页链接（如 /movie/?year=2026、
        # /show/1-----------2026.html 这类路径式筛选）
        if re.match(r"^\d{1,4}$", text) and "?" not in href \
                and not re.search(r"(?:year|area|class|lang|letter|page|cateid)=", href) \
                and not re.search(r"/(?:show|vodshow|type|vodtype|label|vtype)/", href):
            return True
        if re.search(r"\d+-\d+-\d+\.html", href):
            return True
        if re.search(r"\.(m3u8|mp4)(\?|$)", href):
            return True
        return False

    @staticmethod
    def _is_ancestor(a, b):
        p = b
        while p is not None:
            if p is a:
                return True
            p = getattr(p, "parent", None)
        return False

    @staticmethod
    def _guess_group_name(tag, idx):
        prev = tag.find_previous(["h1", "h2", "h3", "h4", "strong", "span", "a"])
        if prev is not None:
            t = prev.get_text(strip=True)
            if 0 < len(t) <= 12:
                return t
        return "线路%d" % (idx + 1)

    def _play_groups_heuristic(self, soup):
        groups = []
        cands = []
        for tag in soup.find_all(["ul", "div", "ol"]):
            links = tag.find_all("a", href=True)
            if len(links) < 2:
                continue
            play_links = [a for a in links if self._is_play_link(a)]
            if len(play_links) >= 2:
                cands.append((tag, play_links))
        cands.sort(key=lambda x: -len(x[1]))
        picked = []
        for tag, links in cands:
            if any(self._is_ancestor(t, tag) for t, _ in picked):
                continue
            picked.append((tag, links))
        for idx, (tag, links) in enumerate(picked):
            eps, seen = [], set()
            for a in links:
                href = a.get("href") or ""
                if not href or href.startswith("javascript:"):
                    continue
                full = urljoin(self.base_url, href)
                if full in seen:
                    continue
                seen.add(full)
                name = a.get_text(strip=True) or ("第%d集" % (len(eps) + 1))
                eps.append("%s$%s" % (name, full))
            if eps:
                groups.append((self._guess_group_name(tag, idx), eps))
        return groups

    # ---------- 播放页解析 player_aaaa ----------
    @staticmethod
    def _extract_balanced(text, marker):
        """提取 marker 后第一个配对 {...}，正确处理字符串与嵌套"""
        if not text:
            return ""
        idx = text.find(marker)
        if idx < 0:
            return ""
        i = text.find("{", idx)
        if i < 0:
            return ""
        depth, in_str, esc, start, n = 0, False, False, i, len(text)
        while i < n:
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]
            i += 1
        return ""

    @staticmethod
    def _extract_play(html):
        """从播放页提取视频直链：player_aaaa → <source> → og:video → 引号包裹"""
        if not html:
            return ""
        raw = Spider._extract_balanced(html, "player_aaaa=")
        if raw:
            try:
                data = json.loads(raw)
            except Exception:
                data = None
            if data:
                url = data.get("url", "") or ""
                enc = str(data.get("encrypt", 0))
                if enc == "1":
                    url = requests.utils.unquote(url)
                elif enc == "2":
                    try:
                        url = base64.b64decode(url).decode("utf-8", "ignore")
                    except Exception:
                        pass
                if url.startswith("http"):
                    return url
        # 视频直链常见嵌点：<video><source src=…>、og:video、任意引号包裹
        m = re.search(r'<source[^>]+src="([^"]+\.(?:m3u8|mp4|flv|mkv)[^"]*)"', html, re.I)
        if not m:
            m = re.search(r'og:video"\s*content="([^"]+)"', html, re.I)
        if not m:
            m = re.search(r'"(https?://[^"\']+?\.(?:m3u8|mp4|flv|mkv)[^"\']*)"', html)
        if m:
            return m.group(1).replace("\\/", "/")
        # iframe 播放器（第三方解析页）：非直链，调用方按 parse=1 嗅探处理
        mi = re.search(r'<iframe[^>]+src="((?:https?:)?//[^"\']+)"', html, re.I)
        if mi:
            u = mi.group(1).replace("\\/", "/")
            return "https:" + u if u.startswith("//") else u
        return ""

    def playerContent(self, flag, id, vipFlags=None):
        try:
            play_url = id
            if play_url and self.isVideoFormat(play_url):
                # 启发式线路可能直接给出媒体直链
                return {"parse": 0, "url": play_url,
                        "header": {"User-Agent": self.headers["User-Agent"],
                                   "Referer": self.base_url + "/"}}
            m_ref = re.match(r"^(.+)-(\d+)-(\d+)$", str(play_url or ""))
            if m_ref:
                vid, sid, nid = m_ref.groups()
                dyn = (f"{self.base_url}{self.prefix}"
                       f"/vod/play/id/{vid}/sid/{sid}/nid/{nid}.html")
                fei = f"{self.base_url}/vodplay/{vid}-{sid}-{nid}.html"
                sea = f"{self.base_url}/v_play/{vid}-{sid}-{nid}.html"
                if self.detail_route == "voddetail":
                    cands = [fei, dyn, sea]
                elif self.detail_route == "seacms":
                    cands = [sea, dyn, fei]
                else:
                    cands = [dyn, fei, sea]
                html = ""
                got_url = ""
                for u in cands:
                    got = self._get(u)
                    if got:
                        html = got
                        got_url = u
                        if "player_aaaa" in got:
                            break
                if not html:
                    # 全部失败：回退给壳嗅探第一个候选播放页（不能回裸id）
                    return {"parse": 1, "url": cands[0], "header": {}}
                real = self._extract_play(html)
                if not real:
                    # 服务端拿不到直链（验证码/JS渲染等）：回退给壳嗅探实际播放页
                    return {"parse": 1, "url": got_url or cands[0],
                            "header": {"User-Agent": self.headers["User-Agent"],
                                       "Referer": self.base_url + "/"}}
                direct = any(t in real for t in (".m3u8", ".mp4", ".flv", ".mkv"))
                return {
                    "parse": 0 if direct else 1,
                    "url": real,
                    "header": {"User-Agent": self.headers["User-Agent"],
                               "Referer": self.base_url + "/"},
                }

            if not str(play_url).startswith("http"):
                # 相对路径播放页（如 /play/xxx-1.html）→ 补全后抓直链
                if str(play_url).startswith("/"):
                    play_url = self.base_url + play_url
                else:
                    return {"parse": 1, "url": self.base_url + "/", "header": {}}

            html = self._get(play_url)
            real = self._extract_play(html)
            if not real and html:
                # 静态改写站的播放路径可能被 WAF 拦截/JS渲染，尝试等价路由：
                # /vplay|vodplay|v_play/{vid}-{sid}-{nid}.html → 动态 maccms 等
                m_eq = re.search(r"/(?:vplay|vodplay|v_play)/(\d+)-(\d+)-(\d+)\.html",
                                 str(play_url))
                if m_eq:
                    vid, sid, nid = m_eq.groups()
                    alts = [
                        f"{self.base_url}{self.prefix}"
                        f"/vod/play/id/{vid}/sid/{sid}/nid/{nid}.html",
                        f"{self.base_url}/vodplay/{vid}-{sid}-{nid}.html",
                        f"{self.base_url}/v_play/{vid}-{sid}-{nid}.html",
                    ]
                    for u2 in alts:
                        if u2 == str(play_url):
                            continue
                        real = self._extract_play(self._get(u2))
                        if real:
                            break
            if not real:
                # 抓不到直链时交给壳嗅探（网页播放器 JS 渲染）
                return {"parse": 1, "url": play_url,
                        "header": {"User-Agent": self.headers["User-Agent"],
                                   "Referer": self.base_url + "/"}}
            direct = any(t in real for t in (".m3u8", ".mp4", ".flv", ".mkv"))
            return {
                "parse": 0 if direct else 1,
                "url": real,
                "header": {"User-Agent": self.headers["User-Agent"],
                           "Referer": self.base_url + "/"},
            }
        except Exception as e:
            print(f"[{self.name}] 播放解析异常: {e}")
            return {"parse": 1, "url": self.base_url + "/", "header": {}}

    def isVideoFormat(self, url):
        return any(t in url for t in (".m3u8", ".mp4", ".flv", ".mkv"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def localProxy(self, param):
        return None


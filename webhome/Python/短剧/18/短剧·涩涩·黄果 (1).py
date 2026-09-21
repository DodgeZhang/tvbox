# -*- coding: utf-8 -*-
# 黄果短剧 TVBox Spider · 优化版
# 修复：封面图加密域名遗漏、分页逻辑、排行榜API、新增topics分类
import sys, re, json, time, requests
from urllib.parse import quote, urlparse

try:
    sys.path.append('..')
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def getName(self): return "黄果短剧"
        def init(self, extend=""): pass
        def homeContent(self, filter): return {"class":[], "filters":{}}
        def categoryContent(self, tid, pg, filter, extend):
            return {"list":[], "page":1, "pagecount":1, "limit":20, "total":0}
        def detailContent(self, ids): return {"list":[]}
        def playerContent(self, flag, id, vipFlags=None):
            return {"parse":0, "url":"", "header":{}}
        def searchContent(self, key, quick, pg="1"):
            return {"list":[], "page":1, "pagecount":1, "limit":20, "total":0}
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False
        def localProxy(self, param): return [404, "text/plain", b""]


class Spider(BaseSpider):
    name = "黄果短剧"
    host = "https://huangguoai.com"

    def __init__(self):
        super().__init__()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": self.host + "/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.base_cates = [
            {"id": "ai-duanju",   "name": "🎬 AI成人短剧"},
            {"id": "ai-manju",    "name": "🎬 AI成人漫剧"},
            {"id": "ai-huanlian", "name": "🎬 AI换脸"},
            {"id": "ai-mogai",    "name": "🎬 AI魔改"},
        ]
        self.img_key = b'f5d965df75336270'
        self.img_iv  = b'97b60394abc2fbe1'
        self._crypto = None
        # ★ 修复：补全所有加密图片域名
        self.img_hosts = {'pic.eanfog.cn', 'pic.zdmhyg.cn'}
        self._recommend_cache = None

    def init(self, *args, **kwargs):
        pass

    # ── 请求工具 ──
    def _get(self, path, params=None):
        try:
            r = self.session.get(self.host + path, params=params, timeout=15)
            return r if r.status_code == 200 else None
        except Exception:
            return None

    def _get_html(self, path):
        r = self._get(path)
        return r.text if r else None

    def _get_json(self, path, params=None):
        r = self._get(path, params)
        if r:
            try: return r.json()
            except: pass
        return None

    # ── 图片处理 ──
    def _is_encrypted(self, url):
        if not url: return False
        try: return urlparse(url).hostname in self.img_hosts
        except: return False

    def _wrap_pic(self, pic):
        if not pic: return ""
        pic = pic.replace("\\u0026","&").replace("&amp;","&")
        if pic.startswith("//"): pic = "https:" + pic
        elif pic.startswith("/"): pic = self.host + pic
        if self._is_encrypted(pic):
            pic = f"http://127.0.0.1:9978/proxy?do=decrypt_img&url={quote(pic, safe='')}"
        return pic

    # ══════════════════════════════════════════════════════
    #  homeContent
    # ══════════════════════════════════════════════════════
    def homeContent(self, filter={}):
        result = {"class": [], "filters": {}}
        result["class"].append({"type_id":"recommend", "type_name":"⭐精选推荐"})
        for c in self.base_cates:
            result["class"].append({"type_id":c["id"], "type_name":c["name"]})
            result["filters"][c["id"]] = [{
                "key":"sort","name":"排序",
                "value":[
                    {"n":"最新更新","v":"latest"},
                    {"n":"当前热播","v":"hot"},
                    {"n":"独家原创","v":"original"},
                    {"n":"随机推荐","v":"random"},
                ]
            }]
        result["class"].append({"type_id":"ranks","type_name":"📊排行榜"})
        result["filters"]["ranks"] = [{
            "key":"rank_type","name":"榜单",
            "value":[
                {"n":"🔥 热播榜","v":"hot"},
                {"n":"⭐ 推荐榜","v":"recommend"},
                {"n":"🚀 潜力榜","v":"potential"},
            ]
        }]
        result["class"].append({"type_id":"chigua","type_name":"🍉黄果吃瓜"})
        result["filters"]["chigua"] = [{
            "key":"cate","name":"分类",
            "value":[
                {"n":"全部","v":"all"},
                {"n":"热门吃瓜","v":"remen"},
                {"n":"AI原创","v":"yuanchuang"},
            ]
        }]
        # 话题精选 - 子分类
        result["class"].append({"type_id":"topics","type_name":"📰话题精选"})
        result["filters"]["topics"] = [{
            "key":"tid","name":"话题",
            "value":[
                {"n":"🔥 热门AI短剧","v":"hot-aiduanju"},
                {"n":"👻  paranormal","v":"paranormal-aiduanju"},
                {"n":"🇪🇺 欧美短剧","v":"oumei-duanju"},
                {"n":"🧠 天才男友","v":"tiancai-nantong"},
                {"n":"✨ 魔法 Drama","v":"magic-drama"},
                {"n":"⭐ 明星换脸","v":"mingxing-huanlian"},
            ]
        }]
        return result

    # ══════════════════════════════════════════════════════
    #  homeVideoContent
    # ══════════════════════════════════════════════════════
    def homeVideoContent(self):
        if self._recommend_cache is not None:
            return {"list": self._recommend_cache}
        try:
            data = self._get_json("/api/videos/category/ai-duanju?page=1&size=20&sort=latest")
            items = (data or {}).get("data", {}).get("items", [])
            vids = []
            seen = set()
            for it in items:
                vid = str(it.get("id",""))
                if vid in seen: continue
                seen.add(vid)
                vids.append({
                    "vod_id":vid, "vod_name":it.get("title",""),
                    "vod_pic":self._wrap_pic(it.get("cover","")),
                    "vod_remarks":self._remarks(it),
                })
            self._recommend_cache = vids
            return {"list": vids}
        except Exception:
            return {"list":[]}

    @staticmethod
    def _remarks(item):
        if not item: return ""
        if item.get("is_finished"):
            return f"全{item.get('episode_count',0)}集"
        ep = item.get("episode_count", 0)
        return f"更新至{ep}集" if ep else ""

    # ══════════════════════════════════════════════════════
    #  categoryContent
    # ══════════════════════════════════════════════════════
    def categoryContent(self, tid, pg, filter, extend):
        pg = max(int(pg or 1), 1)
        ext = extend or {}
        if tid == "recommend":
            return self.homeVideoContent()
        if tid == "ranks":
            return self._category_ranks(ext.get("rank_type","hot"), pg)
        if tid == "chigua":
            return self._category_chigua(ext.get("cate","all"), pg)
        if tid == "topics":
            return self._category_topics(ext.get("tid",""), pg)
        sort = ext.get("sort","latest")
        if sort == "random":
            return self._category_random(tid)
        if sort == "original": sort = "hot"
        return self._category_api(tid, sort, pg)

    def _category_api(self, base_id, sort, page):
        per = 20
        result = {"list":[],"page":page,"pagecount":1,"limit":per,"total":0}
        try:
            data = self._get_json(f"/api/videos/category/{base_id}",
                                  params={"page":page,"size":per,"sort":sort})
            items = (data or {}).get("data",{}).get("items",[])
            if not items: return result
            for it in items:
                result["list"].append({
                    "vod_id":str(it.get("id","")),
                    "vod_name":it.get("title",""),
                    "vod_pic":self._wrap_pic(it.get("cover","")),
                    "vod_remarks":self._remarks(it),
                })
            result["pagecount"] = page + 1
            result["total"] = len(result["list"]) * page
        except Exception: pass
        return result

    def _category_ranks(self, rank_type, page):
        per = 20
        result = {"list":[],"page":page,"pagecount":1,"limit":per,"total":0}
        try:
            data = self._get_json(f"/api/ranks/{rank_type}",
                                  params={"page":page,"size":per})
            items = (data or {}).get("data",{}).get("items",[])
            if not items: return result
            for it in items:
                result["list"].append({
                    "vod_id":str(it.get("video_id","")),
                    "vod_name":it.get("title",""),
                    "vod_pic":self._wrap_pic(it.get("cover","")),
                    "vod_remarks":f"#{it.get('rank','')} {it.get('metric_label','')}{it.get('metric_value','')}",
                })
            result["pagecount"] = page + 1
            result["total"] = len(result["list"]) * page
        except Exception: pass
        return result

    def _category_random(self, base_id):
        result = {"list":[],"page":1,"pagecount":1,"limit":20,"total":0}
        try:
            data = self._get_json(f"/api/videos/category/{base_id}",
                                  params={"page":1,"size":20,"sort":"random"})
            for it in (data or {}).get("data",{}).get("items",[]):
                result["list"].append({
                    "vod_id":str(it.get("id","")),
                    "vod_name":it.get("title",""),
                    "vod_pic":self._wrap_pic(it.get("cover","")),
                    "vod_remarks":self._remarks(it),
                })
            result["total"] = len(result["list"])
        except Exception: pass
        return result

    def _category_chigua(self, cate, page):
        per = 12
        result = {"list":[],"page":page,"pagecount":1,"limit":per,"total":0}
        try:
            if cate == "remen":
                path = f"/chigua/remen/page/{page}/" if page > 1 else "/chigua/remen/"
            elif cate == "yuanchuang":
                path = f"/chigua/yuanchuang/page/{page}/" if page > 1 else "/chigua/yuanchuang/"
            else:
                path = f"/chigua/page/{page}/" if page > 1 else "/chigua/"
            html = self._get_html(path)
            if not html: return result
            posts = re.findall(
                r'<a[^>]*class="hg-post-card"[^>]*href="(/archives/(\d+)/)"[^>]*>.*?<h3>(.*?)</h3>',
                html, re.DOTALL)
            for href, pid, title in posts:
                chunk = html[html.find(f'href="{href}"'):html.find(f'href="{href}"')+600]
                pm = re.search(r'data-src="(https?://[^"]+)"', chunk)
                if not pm:
                    pm = re.search(r'src="(https?://[^"]+)"', chunk)
                pic = self._wrap_pic(pm.group(1)) if pm else ""
                result["list"].append({
                    "vod_id":f"archives_{pid}",
                    "vod_name":title.strip(),
                    "vod_pic":pic,
                    "vod_remarks":"吃瓜",
                })
            pm2 = re.search(r'data-pages="(\d+)"', html)
            result["pagecount"] = int(pm2.group(1)) if pm2 else (page if len(result["list"]) < per else page+1)
            result["total"] = len(result["list"])
        except Exception: pass
        return result

    def _category_topics(self, topic, page):
        """话题分类：无子分类时抓首页，有子分类时抓对应页面"""
        per = 20
        result = {"list":[],"page":page,"pagecount":1,"limit":per,"total":0}
        if not topic:
            # 首页：抓 drama-card（4个精选）+ 子分类链接
            html = self._get_html("/topics/")
            if not html: return result
            cards = re.findall(
                r'<div[^>]*class="hg-drama-card"[^>]*>.*?</div>\s*</div>\s*</div>',
                html, re.DOTALL)
            for c in cards:
                lm = re.search(r'href="(/detail/(\d+)/)"', c)
                if not lm: continue
                pid = lm.group(2)
                tm = re.search(r'hg-drama-card__title[^>]*><a[^>]*>([^<]+)</a>', c)
                title = tm.group(1).strip() if tm else f"视频{pid}"
                pm = re.search(r'data-src="(https?://[^"]+)"', c)
                if not pm: pm = re.search(r'src="(https?://[^"]+)"', c)
                pic = self._wrap_pic(pm.group(1)) if pm else ""
                em = re.search(r'hg-drama-card__episode[^>]*>([^<]+)', c)
                remarks = em.group(1).strip() if em else ""
                result["list"].append({
                    "vod_id": pid,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks,
                })
            return result
        try:
            path = f"/topics/{topic}/?page={page}" if page > 1 else f"/topics/{topic}/"
            html = self._get_html(path)
            if not html: return result
            cards = re.findall(
                r'<div[^>]*class="hg-drama-card"[^>]*>.*?</div>\s*</div>\s*</div>',
                html, re.DOTALL)
            for c in cards:
                lm = re.search(r'href="(/detail/(\d+)/)"', c)
                if not lm: continue
                pid = lm.group(2)
                tm = re.search(r'hg-drama-card__title[^>]*><a[^>]*>([^<]+)</a>', c)
                title = tm.group(1).strip() if tm else f"视频{pid}"
                pm = re.search(r'data-src="(https?://[^"]+)"', c)
                if not pm: pm = re.search(r'src="(https?://[^"]+)"', c)
                pic = self._wrap_pic(pm.group(1)) if pm else ""
                em = re.search(r'hg-drama-card__episode[^>]*>([^<]+)', c)
                remarks = em.group(1).strip() if em else ""
                result["list"].append({
                    "vod_id": pid,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks,
                })
            pm2 = re.search(r'data-pages="(\d+)"', html)
            result["pagecount"] = int(pm2.group(1)) if pm2 else (page if len(result["list"]) < per else page+1)
            result["total"] = len(result["list"])
        except Exception: pass
        return result

    # ══════════════════════════════════════════════════════
    #  detailContent
    # ══════════════════════════════════════════════════════
    def detailContent(self, ids):
        if not ids: return {"list":[]}
        vid = str(ids[0]).strip()
        if vid.startswith("archives_"):
            return self._detail_archives(vid.replace("archives_",""))
        return self._detail_video(vid)

    def _detail_video(self, vid):
        result = {"list":[]}
        try:
            title, cover, desc = "", "", ""
            # 先试 API（部分版本可能支持）
            data = self._get_json(f"/api/videos/detail/{vid}")
            if data and isinstance(data.get("data"), dict):
                item = data["data"]
                title = item.get("title","")
                cover = self._wrap_pic(item.get("cover",""))
                desc = item.get("description","")
            # 降级：HTML 解析
            if not title or not cover:
                html = self._get_html(f"/video/{vid}/")
                if html:
                    tm = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
                    title = (tm.group(1).strip() if tm else vid)
                    # 去掉 "第 XX 集" 后缀
                    title = re.sub(r'\s*第\s*\d+\s*集\s*$', '', title).strip()
                    cm = re.search(r'data-src="(https?://[^"]+)"', html)
                    if not cm: cm = re.search(r'src="(https?://[^"]+)"', html)
                    cover = self._wrap_pic(cm.group(1)) if cm else ""
            # 提取播放源
            ep_srcs = self._extract_sources(vid)
            if ep_srcs:
                segs = [f"第{ep}集${src}" for ep, src in
                        sorted(ep_srcs.items(), key=lambda x:int(x[0]))]
                play_url = "#".join(segs)
            else:
                play_url = f"第1集${vid}"
            result["list"].append({
                "vod_id":vid, "vod_name":title, "vod_pic":cover,
                "vod_content":desc,
                "vod_play_from":"黄果短剧",
                "vod_play_url":play_url,
            })
        except Exception: pass
        return result

    def _extract_sources(self, vid):
        """从详情页提取所有集数的 m3u8 播放源
        策略：每集页面含 epPlaySrcs 滑动窗口（当前集+后续集），逐集翻页合并直到无新集
        """
        ep_srcs = {}
        check_ep = 1
        max_check = 100  # 安全上限

        while check_ep <= max_check:
            url = f"/video/{vid}/ep-{check_ep}/" if check_ep > 1 else f"/video/{vid}/"
            html = self._get_html(url)
            if not html:
                break

            # 从 <script> JSON 提取 epPlaySrcs
            new_eps = False
            for m in re.finditer(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
                block = m.group(1)
                if 'epPlaySrcs' not in block and 'videoSrc' not in block:
                    continue
                # videoSrc
                vs_m = re.search(r'"videoSrc"\s*:\s*"((?:https?://)?[^"]+)"', block)
                if vs_m:
                    src = vs_m.group(1).replace('\\u0026', '&')
                    if src.startswith("//"): src = "https:" + src
                    if str(check_ep) not in ep_srcs:
                        ep_srcs[str(check_ep)] = src
                        new_eps = True
                # epPlaySrcs 滑动窗口
                eps_m = re.search(r'"epPlaySrcs"\s*:\s*(\{[^}]+\})', block)
                if eps_m:
                    try:
                        raw = eps_m.group(1).replace('\\u0026', '&')
                        eps = json.loads(raw)
                        for ep, src in eps.items():
                            if src and ep not in ep_srcs:
                                if src.startswith("//"): src = "https:" + src
                                ep_srcs[ep] = src
                                new_eps = True
                    except Exception:
                        pass
                if new_eps:
                    break

            # 没有新集就停止
            if not new_eps and check_ep > 1:
                break
            check_ep += 1
            time.sleep(0.15)  # 避免请求过快

        # 兜底：从首页 HTML  broader regex
        if not ep_srcs:
            html = self._get_html(f"/video/{vid}/")
            if html:
                for m in re.finditer(
                    r'(?:data-src|src)="([^"]*\.m3u8[^"]*)"', html
                ):
                    src = m.group(1).replace('\\u0026', '&')
                    if src.startswith("//"): src = "https:" + src
                    if "1" not in ep_srcs:
                        ep_srcs["1"] = src
        return ep_srcs

    def _detail_archives(self, post_id):
        result = {"list":[]}
        try:
            html = self._get_html(f"/archives/{post_id}/")
            if not html: return result
            tm = re.search(r'<title>(.*?)</title>', html)
            title = (tm.group(1).replace(" - 黄果短剧","").strip()) if tm else f"吃瓜{post_id}"
            pm = re.search(r'data-src="(https?://[^"]+)"', html)
            if not pm: pm = re.search(r'src="(https?://[^"]+)"', html)
            pic = self._wrap_pic(pm.group(1)) if pm else ""
            video_url = ""
            m = re.search(r'<video[^>]+src="(https?://[^"]+)"', html)
            if m: video_url = m.group(1)
            if not video_url:
                m = re.search(r'<iframe[^>]+src="(https?://[^"]+)"', html)
                if m: video_url = m.group(1)
            if not video_url:
                m = re.search(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)', html)
                if m: video_url = m.group(1)
            play_url = f"第1集${video_url}" if video_url else f"第1集${post_id}"
            result["list"].append({
                "vod_id":f"archives_{post_id}","vod_name":title,"vod_pic":pic,
                "vod_content":"吃瓜内容","vod_play_from":"黄果短剧","vod_play_url":play_url,
            })
        except Exception: pass
        return result

    # ══════════════════════════════════════════════════════
    #  searchContent
    # ══════════════════════════════════════════════════════
    def searchContent(self, key, quick, pg="1"):
        result = {"list":[],"page":1,"pagecount":1,"limit":20,"total":0}
        try:
            page = max(int(pg or 1), 1)
            url = f"/search/?keyword={quote(key)}"
            if page > 1: url += f"&page={page}"
            html = self._get_html(url)
            if not html: return result
            videos, seen = [], set()
            for m in re.finditer(r'data-track-id="(\d+)"', html):
                vid = m.group(1)
                if vid in seen: continue
                start = m.start()
                end = min(start+800, len(html))
                chunk = html[start:end]
                tm = re.search(r'data-track-title="([^"]*)"', chunk)
                pm = re.search(r'data-src="(https?://[^"]*)"', chunk)
                if not pm: pm = re.search(r'src="(https?://[^"]*)"', chunk)
                videos.append({
                    "vod_id":vid,
                    "vod_name":tm.group(1) if tm else "",
                    "vod_pic":self._wrap_pic(pm.group(1)) if pm else "",
                    "vod_remarks":"",
                })
                seen.add(vid)
            result["list"] = videos
            tm2 = re.search(r'data-track-search-total="(\d+)"', html)
            pm2 = re.search(r'data-pages="(\d+)"', html)
            if tm2: result["total"] = int(tm2.group(1))
            result["pagecount"] = int(pm2.group(1)) if pm2 else (page+1 if len(videos)>=20 else page)
            result["page"] = page
        except Exception: pass
        return result

    # ══════════════════════════════════════════════════════
    #  playerContent
    # ══════════════════════════════════════════════════════
    def playerContent(self, flag, id, vipFlags=None):
        hdr = {"User-Agent":self.headers["User-Agent"],"Referer":self.host+"/"}
        result = {"parse":0,"url":"","header":hdr}
        if not id: return result
        raw = str(id).strip()
        if raw.startswith("http"):
            result["url"] = raw; return result
        if raw.startswith("archives_"):
            d = self._detail_archives(raw.replace("archives_",""))
            pu = (d.get("list") or [{}])[0].get("vod_play_url","")
            parts = pu.split("$",1)
            if len(parts)==2 and parts[1].startswith("http"):
                result["url"]=parts[1]; return result
            result["parse"]=1
            result["url"]=f"{self.host}/archives/{raw.replace('archives_','')}/"
            return result
        # 先试 API
        data = self._get_json(f"/api/videos/detail/{raw}")
        if data:
            src = (data.get("data") or {}).get("videoSrc","")
            if src:
                result["url"]=src; return result
        # 回退 HTML
        html = self._get_html(f"/video/{raw}/")
        if html:
            m = re.search(r'(https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)', html)
            if m:
                result["url"]=m.group(1).replace('\\u0026','&'); return result
        result["parse"]=1
        result["url"]=f"{self.host}/video/{raw}/"
        return result

    # ══════════════════════════════════════════════════════
    #  辅助 & 代理
    # ══════════════════════════════════════════════════════
    def isVideoFormat(self, url):
        if not url: return False
        return bool(re.search(r'\.(m3u8|mp4|avi|flv|mkv|ts)\b', url, re.I) or "m3u8" in url.lower())

    def manualVideoCheck(self): return False

    def localProxy(self, param):
        params = {}
        if isinstance(param, str):
            for p in param.split("&"):
                if "=" in p:
                    k,v = p.split("=",1); params[k]=v
        elif isinstance(param, dict):
            params = param
        if params.get("do") != "decrypt_img":
            return [404,"text/plain",b"not found"]
        img_url = params.get("url","")
        if not img_url: return [400,"text/plain",b"missing url"]
        from urllib.parse import unquote
        img_url = unquote(img_url)
        try:
            resp = self.session.get(img_url, timeout=15)
            if resp.status_code != 200:
                return [404,"text/plain",b"fetch failed"]
            dec = self._aes_cbc_decrypt(resp.content)
            if dec[:8]==b'\x89PNG\r\n\x1a\n': mime="image/png"
            elif dec[:2]==b'\xff\xd8': mime="image/jpeg"
            elif dec[:6] in (b'GIF87a',b'GIF89a'): mime="image/gif"
            elif dec[:4]==b'RIFF' and len(dec)>12 and dec[8:12]==b'WEBP': mime="image/webp"
            else: mime="image/jpeg"
            return [200,mime,dec]
        except Exception as e:
            return [500,"text/plain",f"error:{e}".encode()]

    def _aes_cbc_decrypt(self, data):
        try:
            from Crypto.Cipher import AES
            return AES.new(self.img_key, AES.MODE_CBC, self.img_iv).decrypt(data)
        except ImportError:
            return self._pure_aes(data)

    _SBOX = None
    _INV_SBOX = None

    @classmethod
    def _get_sbox(cls):
        if cls._SBOX is not None: return cls._SBOX
        cls._SBOX = [
            0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
            0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
            0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
            0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
            0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
            0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
            0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
            0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
            0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
            0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
            0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
            0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
            0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
            0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
            0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
            0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
        ]
        cls._INV_SBOX = [0]*256
        for i in range(256): cls._INV_SBOX[cls._SBOX[i]] = i
        return cls._SBOX

    def _pure_aes(self, data):
        sbox = self._get_sbox()
        inv = self._INV_SBOX
        rk = self._key_expand(self.img_key, sbox)
        prev = bytearray(self.img_iv)
        out = bytearray()
        for i in range(0, len(data), 16):
            blk = bytearray(data[i:i+16])
            dec = self._dec_block(blk, rk, inv)
            out.extend(bytes(a^b for a,b in zip(dec, prev)))
            prev = blk
        return bytes(out)

    @staticmethod
    def _key_expand(key, sbox):
        w = [list(key[i:i+4]) for i in range(0,16,4)]
        rc = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]
        for i in range(4,44):
            t = list(w[i-1])
            if i%4==0:
                t = t[1:]+t[:1]
                t = [sbox[b] for b in t]
                t[0] ^= rc[i//4-1]
            w.append([w[i-4][j]^t[j] for j in range(4)])
        # 每个 round_key = 连续 16 字节
        return [bytearray(w[r*4]+w[r*4+1]+w[r*4+2]+w[r*4+3]) for r in range(11)]

    @staticmethod
    def _dec_block(block, rk, inv_sbox):
        # state[row][col]
        state = [[block[r*4+c] for c in range(4)] for r in range(4)]
        # AddRoundKey (round 10)
        for r in range(4):
            for c in range(4):
                state[r][c] ^= rk[r*4+c]
        for rnd in range(9,0,-1):
            # InvShiftRows
            for row in range(1,4):
                state[row] = state[row][-row:]+state[row][:-row]
            # InvSubBytes
            for r in range(4):
                for c in range(4):
                    state[r][c] = inv_sbox[state[r][c]]
            # AddRoundKey
            for r in range(4):
                for c in range(4):
                    state[r][c] ^= rk[rnd*4+r*4+c]  # 注意：rk 是 flat 16-byte
            # InvMixColumns
            for c in range(4):
                a,b,c2,d = state[0][c],state[1][c],state[2][c],state[3][c]
                state[0][c] = Spider._gm(a,14)^Spider._gm(b,11)^Spider._gm(c2,13)^Spider._gm(d,9)
                state[1][c] = Spider._gm(a,9)^Spider._gm(b,14)^Spider._gm(c2,11)^Spider._gm(d,13)
                state[2][c] = Spider._gm(a,13)^Spider._gm(b,9)^Spider._gm(c2,14)^Spider._gm(d,11)
                state[3][c] = Spider._gm(a,11)^Spider._gm(b,13)^Spider._gm(c2,9)^Spider._gm(d,14)
        # Final round
        for row in range(1,4):
            state[row] = state[row][-row:]+state[row][:-row]
        for r in range(4):
            for c in range(4):
                state[r][c] = inv_sbox[state[r][c]]
        for r in range(4):
            for c in range(4):
                state[r][c] ^= rk[c*4+r]  # 最后一轮用 rk[0]
        return bytearray(state[r][c] for c in range(4) for r in range(4))

    @staticmethod
    def _gm(x, y):
        """GF(2^8) 乘法"""
        p = 0
        for _ in range(8):
            if y&1: p ^= x
            hi = x&0x80
            x = (x<<1)&0xff
            if hi: x ^= 0x1b
            y >>= 1
        return p


Spider = Spider
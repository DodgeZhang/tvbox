# coding=utf-8
"""
目标站: DramaRush 短剧 (ai.dramarush.tv)
站点类型: 竖屏短剧资源站
技术栈: Next.js + tRPC + Prisma
数据接口: /api/trpc (匿名 GET)
视频源(2026-08-14 全量扫描 100 部，实测 8 种 hlsUrl 格式):
    episode.watch tRPC 返回 episode.hlsUrl，锁定集返回 null。
    免费集 hlsUrl 通过 _fix_hls_url 统一处理:
      1. cdn_direct (18%): raw.shorttv.online/uploads/direct/{epId}/video.mp4
         → 替换 raw→cdn 域，免 Referer，HTTP 206。
      2. dc_mirror_mp4: cdn.shorttv.online/dc/mirror/{epId}/video.mp4 → 直接可用。
      3. dc_mirror_m3u8: /api/media/dc/mirror/{epId}/master.m3u8?tok=...
         → 替换 /api/media/→cdn/，m3u8+分片+AES key 均在 CDN 可访问。
      4. centaurus: /api/media/centaurus/hls/{epId}/h264/master.m3u8?tok=...
         → m3u8 分片指向 ai.dramarush.tv(403)，改用多路径探测(见下)。
      5. lsj_hls: /api/media/lsj/hls/{epId}/master.m3u8?tok=...
         → 替换 /api/media/→cdn/，m3u8+分片+AES key 均在 CDN 可访问。
      6. uploads_hls (最大宗): /api/media/uploads/hls/{id1}/{id2}/master.m3u8?tok=...
         → 替换 /api/media/→cdn/，m3u8+分片在 CDN 可访问(免费集)。
      7. uploads_creator: /api/media/uploads/creator/{id1}/{id2}/video.mp4
         → 替换 /api/media/→cdn/，MP4 直链(免费集)。
      8. dc_stream (7%): /api/dc/stream/{epId}/video.mp4?tok=...
         → 直接用站点 URL(ai.dramarush.tv/api/dc/stream/...)，免 Referer，HTTP 200。

去水印机制(2026-08-15 新增):
    站点水印仅存在于 centaurus 官方转码 HLS 中(站点转码时烧录)。
    CDN 上的原始上传 MP4(uploads/direct, dc/mirror)为创作者原始文件，无站点水印。
    策略: 所有 HLS 源(centaurus + 其他 m3u8)优先探测 CDN MP4 直链(无水印)，
          HLS 仅作兜底(可能有水印但可播)。
    实现: _fix_hls_url 顶部增加 CDN MP4 探测，_is_watermark_free_url 过滤非 MP4 源。
    性能: 探测结果按 epId 缓存(TTL 10分钟)，首次播放多 ~1s，重播零开销。
    开关: self.remove_watermark = True(默认开启)，设 False 可恢复原有行为。

付费锁定剧集逆向(核心发现):
    该站使用硬币/广告/会员解锁机制，锁定剧集在 episode.watch/hlsUrl 返回 null。
    CDN(cdn.shorttv.online)不校验授权，锁定集与免费集视频文件使用相同 URL 模式。

    2026-08-14 二次实测(45 部剧 x 7 路径并发探测)关键修正:
      a. CDN 路径可用性是【集级】差异，不是剧级:
         同一部剧 ep6 有 cdn/uploads/hls/{epId}/master.m3u8 而 ep4 返回 404
         (CDN 单段布局是渐进同步的，通常新集先有)。
         → 探测必须逐集执行 + 按 epId 缓存，不能按剧缓存一种"源类型→路径"。
      b. 各源类型锁定集 CDN 路径实测可用率(按集探测):
           cdn_direct 源:    uploads/direct/{epId}/video.mp4  10/10
           dc_mirror_mp4 源: dc/mirror/{epId}/video.mp4         3/3
           centaurus 源:     uploads/direct(2/3)、dc/mirror mp4(1/3)、
                             centaurus/hls/{epId}/h264/master.m3u8(部分)
           uploads_hls 源:   uploads/hls/{epId}/master.m3u8 部分集可用(多为最新集)
           uploads_creator / dc_stream 源: 全路径 404，无法 CDN 直链
      c. 借用免费集 tok 访问锁定集站点代理路径(/api/media/...、/api/dc/stream/...)
         全部 403: tok 与 ep 参数绑定(免费集 URL 形如 ?tok=xxx&ep={epId})，
         服务端校验匹配，不可跨集借用。dc_stream/creator 锁定集确认无解→嗅探兜底。
      d. 原实现 _check_url 用 HEAD 且仅认 200: CDN 对 HEAD 常返回非 200
         (405/403/超时)，导致明明可用的直链被误判→回退嗅探→锁定集页面
         本身锁定无视频资源，嗅探必然失败→「播放地址解析失败」。
         改为 GET+Range(bytes=0-1023)+内容校验(m3u8 须含 #EXTM3U，
         mp4 校验 Content-Type/ftyp 前缀)，杜绝 XML/HTML 错误页误判为可用。

    实现(2026-08-15 优化启动速度):
      _verify_media: GET+Range+内容校验，取代 HEAD。超时 3s(404 <200ms 返回)。
      _detect_source_type: 从 hlsUrl 字符串识别 8 种源类型(剧级缓存)。
      _cached_source_type: 只读源类型缓存，不触发网络。锁定集播放时用，
          缓存命中(详情页预缓存)用其优先级排序，未命中直接默认优先级探测，
          省掉 _get_source_type 的 2 次 tRPC(drama.byId+免费集episode.watch)。
      _probe_cdn_for_episode: 锁定集/centaurus回退 的多路径探测，
          优先级前2条串行快探 + 剩余路径并发(ThreadPoolExecutor, 首命中即返回)，
          结果(含负结果)按 epId 缓存(TTL 10 分钟)。
          串行7条最坏7s → 并发后最坏≈1s。
      detailContent: 顺带预缓存源类型，播放时直接命中。
      _trpc: 含1次重试，规避站点偶发 TLS 中断(SSLZeroReturn)卡满超时。
      playerContent:
        - 免费集: _fix_hls_url 处理后返回(parse=0)；
          centaurus 免费集 m3u8 分片 403 时，同样走多路径探测。
        - 锁定集: _probe_cdn_for_episode 逐集探测，命中返回(parse=0)。
        - 锁定集(全路径 404，如 dc_stream/uploads_creator 源):
          回退嗅探 watch 页面(parse=1)。
        - episode.watch 失败: 回退 drama.byId + 同样探测。
        - 最终兜底: 嗅探 watch 页面。

海报:
    1. poster 字段优先，cover 字段回退。poster 为空/"null"时自动取 cover。
    2. 所有海报统一通过 wsrv.nl 图片代理转 JPEG(w=400&q=70):
       - 原始海报体积大(实测 JPG 约 200-500KB，PNG 2-3MB)，TVBox 加载超时不显示。
       - wsrv.nl 代理后: 2.9MB PNG → 63KB JPEG，缩小约 46 倍，TVBox 可正常加载。
       - wsrv.nl 为免费图片 CDN 代理，全球可访问，能同时访问 raw/cdn 域，
         规避 raw.shorttv.online 在部分网络不可达、CDN 域偶发超时的问题。
    3. drama.list 默认排序设为 hot: sort=new 对约 1/3 剧目返回共享占位海报，
       sort=hot 返回正确独立海报(0 占位/0 空)。

筛选器(已实测可用并可与 categorySlug 叠加):
    sort: hot(默认)/new/rating/weight/completion
    contentKind: SHORT_DRAMA/SERIES/MOVIE/ANIME/VARIETY
    releaseStatus: ONGOING/COMPLETED/PAUSED
    region: CN/KR/JP/US/TH/OTHER (数据多为 CN，其他地区少量)
    year: 2026/2025/2024/older (数据多为 2026)
    language: zh/en/ko/ja/th (数据多为 zh)
    注: region/year/language 的 "older"/"OTHER" 等特殊值不传给 API(不支持范围查询)，
        仅作为 UI 选项，选中时不筛选该维度。

分页说明(2026-08-15 修复):
    该站使用游标(cursor)分页，不支持 page/offset。
    每页取 50 条。筛选状态不同则结果集不同，cursor 缓存以 "tid#筛选签名" 为键。
    修复: pagecount 恒为 max_pages(4)，让 TVBox 始终允许翻页。
    原逻辑 page1→pagecount=2，但 cursor 缓存丢失(App 后台 GC)或 tRPC 偶发失败时，
    第2页返回空+pagecount=1，TVBox 锁死无法重试。改为恒返回 max_pages，
    无数据时返回空列表，用户可重试翻页。
"""
import re
import sys
import json
import time
import urllib.parse

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    # 类变量：跨实例共享缓存
    # cursor 缓存: {cache_key: {page: cursor, "_ts": timestamp}}
    _cursor_cache = {}
    # 剧目源类型缓存: {dramaId: (source_type, ts)}
    _source_cache = {}
    # 集级 CDN 探测缓存: {epId: (url_or_empty, ts)}，"" 表示已探测无可用路径(负缓存)
    _probe_cache = {}
    # 剧集ID缓存: {dramaId: {"_ts": ts, index: (epId, locked)}}
    # 详情页 drama.byId 已返回全部 episodes(id/index/locked)，缓存后
    # 播放时即使 episode.watch 因站点 SSL 抖动失败，也能直接拿 epId 探测 CDN。
    _epid_cache = {}

    def init(self, extend=""):
        self.site_url = "https://ai.dramarush.tv"
        self.api_url = self.site_url + "/api/trpc"
        self.video_cdn = "https://raw.shorttv.online/uploads/direct/"
        self.cdn_host = "cdn.shorttv.online"
        self.page_size = 50
        self.max_pages = 4
        self.cache_ttl = 600  # 缓存有效期 10 分钟
        # 去水印开关: True=所有 HLS 源优先探测 CDN MP4 直链(原始上传无水印)
        self.remove_watermark = True
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Mobile Safari/537.36',
            'Accept': 'application/json,text/plain,*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        self.categories = self._fetch_categories()
        self.filter_config = self._build_filter_config()

    # ==================== 基础工具 ====================

    def _trpc(self, proc, inp):
        """调用 tRPC 接口，返回 result.data.json；失败返回 None。
        含 1 次短重试：实测站点偶发 TLS 中断(SSLZeroReturn)，单次请求可能卡满
        超时(默认 10-15s)拖慢启动，重试可规避大部分瞬时抖动。"""
        input_str = urllib.parse.quote(json.dumps({"json": inp}, ensure_ascii=False))
        url = "%s/%s?input=%s" % (self.api_url, proc, input_str)
        last_err = None
        for attempt in range(2):
            try:
                resp = self.fetch(url, headers=self.headers)
                if not resp or not resp.text:
                    last_err = "empty response"
                    continue
                j = json.loads(resp.text)
                if isinstance(j, list):
                    j = j[0] if j else {}
                if not j or "result" not in j:
                    last_err = "no result"
                    continue
                return j["result"]["data"]["json"]
            except Exception as e:
                last_err = e
                continue
        if last_err:
            print("[DramaRush] tRPC %s 失败: %s" % (proc, last_err))
        return None

    def _fix_pic(self, pic):
        """
        修复海报 URL:
        1. 空值/占位图 → 空字符串（TVBox 显示默认占位图）
        2. raw.shorttv.online → cdn.shorttv.online:
           实测 cdn 域比 raw 域加载更快、更稳定(raw 1.55s → cdn 1.03s)。
        3. 所有海报统一通过 wsrv.nl 图片代理转 JPEG(w=300,q=60):
           - 原图体积大(cdn-jpg 约 750KB，cdn-png 约 1.6MB)，TVBox 并发加载时
             大量超时显示占位图；wsrv 压缩后约 6-60KB，加载快且稳定。
           - wsrv.nl 为专业图片 CDN 代理，能同时访问 raw/cdn 域。
           2026-08-15 修正: 之前仅对 PNG 代理、JPG 直连 cdn 仍出现大量占位图，
           故恢复全部 wsrv 代理，并将源站 URL 统一换为 cdn 域后再代理。
        """
        if not pic or pic == "null":
            return ""
        if re.search(r'/(?:loading|blank|placeholder|noimg|1x1)\b', pic, re.I):
            return ""
        # cdn 域比 raw 域快且稳定；wsrv.nl 以 cdn 域 URL 为源
        pic = pic.replace("raw.shorttv.online", self.cdn_host)
        return "https://wsrv.nl/?url=%s&w=300&q=60&output=jpg" % urllib.parse.quote(pic, safe='')

    def _pick_pic(self, item):
        """
        优先 poster 次 cover，统一走 _fix_pic 规范化。
        当 poster 为空/"null"时自动回退到 cover，避免海报丢失。
        """
        poster = item.get("poster") or ""
        fixed = self._fix_pic(poster)
        if fixed:
            return fixed
        return self._fix_pic(item.get("cover") or "")

    def _remark(self, item):
        te = item.get("totalEpisodes") or 0
        rs = item.get("releaseStatus") or ""
        if rs == "ONGOING" and te:
            return "更新至%d集" % te
        if te:
            return "%d集全" % te
        if rs:
            return rs
        return ""

    def _parse_item(self, it):
        return {
            "vod_id": it.get("id", ""),
            "vod_name": it.get("title", "") or it.get("subtitle", "") or "",
            "vod_pic": self._pick_pic(it),
            "vod_remarks": self._remark(it)
        }

    # ==================== 分类 ====================

    def _fetch_categories(self):
        return [
            {"type_id": "all", "type_name": "全部"},
            {"type_id": "rank:hot", "type_name": "热门榜"},
            {"type_id": "cat:fantasy", "type_name": "奇幻"},
            {"type_id": "cat:comedy", "type_name": "喜剧"},
            {"type_id": "cat:romance", "type_name": "甜宠"},
            {"type_id": "cat:ceo", "type_name": "霸总"},
        ]

    # ==================== 筛选器 ====================

    def _build_filter_config(self):
        """
        TVBox 筛选器配置。所有维度均已实测可用，且可与 categorySlug 叠加。
        排序默认"最热"：实测 drama.list 默认排序(new)对约 1/3 剧目返回共享占位海报，
        而 sort=hot 返回正确独立海报。故默认使用 hot，用户可手动切换"最新"等。
        region/year/language 实测数据打标较全(CN/2026/zh 占多数但有多年份)，
        可作为辅助筛选维度。
        """
        return [
            {"key": "sort", "name": "排序", "value": [
                {"n": "最热", "v": "hot"},
                {"n": "最新", "v": "new"},
                {"n": "评分", "v": "rating"},
                {"n": "完结度", "v": "completion"},
                {"n": "权重", "v": "weight"},
            ]},
            {"key": "contentKind", "name": "类型", "value": [
                {"n": "全部", "v": ""},
                {"n": "短剧", "v": "SHORT_DRAMA"},
                {"n": "长剧", "v": "SERIES"},
                {"n": "电影", "v": "MOVIE"},
                {"n": "动漫", "v": "ANIME"},
                {"n": "综艺", "v": "VARIETY"},
            ]},
            {"key": "releaseStatus", "name": "状态", "value": [
                {"n": "全部", "v": ""},
                {"n": "连载中", "v": "ONGOING"},
                {"n": "已完结", "v": "COMPLETED"},
                {"n": "暂停", "v": "PAUSED"},
            ]},
            {"key": "region", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "中国", "v": "CN"},
                {"n": "韩国", "v": "KR"},
                {"n": "日本", "v": "JP"},
                {"n": "美国", "v": "US"},
                {"n": "泰国", "v": "TH"},
                {"n": "其他", "v": "OTHER"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "更早", "v": "older"},
            ]},
            {"key": "language", "name": "语言", "value": [
                {"n": "全部", "v": ""},
                {"n": "国语", "v": "zh"},
                {"n": "英语", "v": "en"},
                {"n": "韩语", "v": "ko"},
                {"n": "日语", "v": "ja"},
                {"n": "泰语", "v": "th"},
            ]},
        ]

    def _filters_for(self, tid):
        if tid.startswith("rank:"):
            return []
        return self.filter_config

    def _filter_params(self, extend):
        """
        从 TVBox 传入的 extend 提取筛选参数。
        返回 (params_dict, signature)。

        signature 必须从最终 params（含默认值）构建，而非原始 extend 值:
        TVBox 在不同页码可能传入不同的 extend 表示同一筛选状态，
        从最终 params 构建签名可保证相同筛选状态始终命中同一缓存 key。

        region/year/language 的 "older"/"OTHER" 等特殊值需转换为 API 能理解的参数:
        year=older → 不传 year 参数(无法表达"更早"，API 不支持范围查询，留空)
        region=OTHER → 不传 region(同理)
        只传 API 确实支持的值，无效值会被 API 忽略但不报错。
        """
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}
        params = {}
        for key in ("sort", "contentKind", "releaseStatus", "region", "year", "language"):
            v = str(extend.get(key, "") or "").strip()
            if v and v not in ("older", "OTHER"):
                params[key] = v
        if "sort" not in params:
            params["sort"] = "hot"
        sig = "|".join("%s=%s" % (k, params.get(k, ""))
                       for k in ("sort", "contentKind", "releaseStatus", "region", "year", "language"))
        return params, sig

    # ==================== 列表/分页 ====================

    def _fetch_list(self, tid, cursor, fparams=None):
        fparams = fparams or {}
        limit = self.page_size
        if tid == "all":
            inp = {"limit": limit, "cursor": cursor}
            inp.update(fparams)
            return self._trpc("drama.list", inp)
        if tid.startswith("rank:"):
            tab = tid.split(":", 1)[1]
            return self._trpc("rank.list", {"tab": tab, "limit": limit, "cursor": cursor})
        if tid.startswith("cat:"):
            slug = tid.split(":", 1)[1]
            inp = {"limit": limit, "cursor": cursor, "categorySlug": slug}
            inp.update(fparams)
            return self._trpc("drama.list", inp)
        if tid.startswith("search:"):
            key = tid.split(":", 1)[1]
            inp = {"limit": limit, "cursor": cursor, "q": key}
            inp.update(fparams)
            return self._trpc("drama.list", inp)
        return None

    def _save_cursor(self, key, page, cursor):
        try:
            if key not in Spider._cursor_cache:
                Spider._cursor_cache[key] = {}
            Spider._cursor_cache[key][page] = cursor
            Spider._cursor_cache[key]["_ts"] = time.time()
        except Exception:
            pass

    def _load_cursor(self, key, page):
        try:
            cache = Spider._cursor_cache.get(key)
            if not cache:
                return None
            ts = cache.get("_ts", 0)
            if time.time() - ts > self.cache_ttl:
                return None
            return cache.get(page)
        except Exception:
            return None

    def _get_cursor_for_page(self, key, tid, page, fparams):
        if page <= 1:
            return None
        if page > self.max_pages:
            return None
        cached = self._load_cursor(key, page - 1)
        if cached is not None:
            return cached
        cursor = None
        start_page = 1
        for p in range(page - 1, 0, -1):
            c = self._load_cursor(key, p)
            if c is not None:
                cursor = c
                start_page = p + 1
                break
        for p in range(start_page, page):
            data = self._fetch_list(tid, cursor, fparams)
            if not data:
                return None
            cursor = data.get("nextCursor")
            self._save_cursor(key, p, cursor)
            if not cursor:
                return None
        return cursor

    def _list_response(self, tid, page, extend=None):
        """
        通用列表响应：取数据 + 缓存 cursor + 构建 TVBox 响应。
        筛选状态不同则结果集不同，cursor 缓存以 "tid#筛选签名" 隔离。

        翻页修复(2026-08-15):
          a. pagecount 始终设为 max_pages(4)，让 TVBox 始终允许翻页。
             原逻辑 page1→pagecount=2，但若第2页 cursor 缓存丢失返回空+pagecount=1，
             TVBox 会锁死在 page1 无法再翻。改为恒返回 max_pages，无数据时返回空列表。
          b. cursor 缓存丢失时链式回退重建(已有逻辑增强容错)。
          c. 回退失败(tRPC 偶发中断)时返回空列表但保持 pagecount=max_pages，
             用户可重试翻页而非被锁死。
        """
        fparams, sig = self._filter_params(extend)
        key = "%s#%s" % (tid, sig)

        if page > self.max_pages:
            return {"list": [], "page": page, "pagecount": self.max_pages,
                    "limit": self.page_size, "total": 0}

        cursor = self._get_cursor_for_page(key, tid, page, fparams)
        if page > 1 and not cursor:
            # cursor 缓存丢失且链式回退失败(tRPC 中断等)，返回空但保持 pagecount
            # 让 TVBox 允许用户重试，而非锁死
            return {"list": [], "page": page, "pagecount": self.max_pages,
                    "limit": self.page_size, "total": 0}

        data = self._fetch_list(tid, cursor, fparams)
        if not data:
            # tRPC 失败，返回空但保持 pagecount 让用户可重试
            return {"list": [], "page": page, "pagecount": self.max_pages,
                    "limit": self.page_size, "total": 0}

        items = data.get("items") or []
        nc = data.get("nextCursor")
        self._save_cursor(key, page, nc)

        seen = set()
        video_list = []
        for it in items:
            vid = it.get("id", "")
            if vid in seen:
                continue
            seen.add(vid)
            video_list.append(self._parse_item(it))

        # pagecount 恒为 max_pages，让 TVBox 始终允许翻页
        # 实际无更多数据时(无 nextCursor)，翻下一页会返回空列表，TVBox 显示"无更多"
        return {
            "list": video_list,
            "page": page,
            "pagecount": self.max_pages,
            "limit": self.page_size,
            "total": len(video_list)
        }

    # ==================== 播放 URL 提取 ====================

    # CDN 候选路径模板（epId 寻址，2026-08-14 实测）
    _CDN_CANDIDATES = {
        "dc_mirror_mp4":  "/dc/mirror/%s/video.mp4",
        "dc_mirror_m3u8": "/dc/mirror/%s/master.m3u8",
        "uploads_direct": "/uploads/direct/%s/video.mp4",
        "lsj_hls":        "/lsj/hls/%s/master.m3u8",
        "uploads_hls":    "/uploads/hls/%s/master.m3u8",
        "centaurus_h264": "/centaurus/hls/%s/h264/master.m3u8",
        "uploads_creator": "/uploads/creator/%s/video.mp4",
    }

    # 各源类型的候选探测优先序（按实测可用率排序，未列出的源用默认序）
    # 实测(45部x7路径): cdn_direct源 uploads_direct 10/10；
    #   dc_mirror_mp4源 dc_mirror_mp4 3/3；centaurus源 uploads_direct 2/3、
    #   dc_mirror_mp4 1/3、centaurus_h264 部分；uploads_hls源部分新集可用；
    #   dc_stream/uploads_creator 源全 404(仅保留探测以覆盖边角案例)
    # 去水印优化(2026-08-15): centaurus 优先序已将 MP4 源(uploads_direct,
    #   dc_mirror_mp4)排在 HLS 之前，确保去水印探测优先命中无水印 MP4 直链。
    _SOURCE_PRIORITY = {
        "cdn_direct":      ["uploads_direct", "dc_mirror_mp4", "dc_mirror_m3u8",
                            "uploads_hls", "lsj_hls", "centaurus_h264"],
        "dc_mirror_mp4":   ["dc_mirror_mp4", "dc_mirror_m3u8", "uploads_direct",
                            "uploads_hls", "lsj_hls", "centaurus_h264"],
        "dc_mirror_m3u8":  ["dc_mirror_m3u8", "dc_mirror_mp4", "uploads_direct",
                            "uploads_hls", "lsj_hls", "centaurus_h264"],
        "lsj_hls":         ["lsj_hls", "dc_mirror_m3u8", "dc_mirror_mp4",
                            "uploads_direct", "uploads_hls", "centaurus_h264"],
        "centaurus":       ["uploads_direct", "dc_mirror_mp4", "centaurus_h264",
                            "dc_mirror_m3u8", "uploads_hls", "lsj_hls"],
        "uploads_hls":     ["uploads_hls", "dc_mirror_mp4", "dc_mirror_m3u8",
                            "uploads_direct", "lsj_hls", "centaurus_h264"],
        "uploads_creator": ["uploads_creator", "uploads_direct", "dc_mirror_mp4",
                            "dc_mirror_m3u8", "uploads_hls", "lsj_hls", "centaurus_h264"],
        "dc_stream":       ["dc_mirror_mp4", "uploads_direct", "dc_mirror_m3u8",
                            "uploads_hls", "lsj_hls", "centaurus_h264"],
    }
    _DEFAULT_PRIORITY = ["dc_mirror_mp4", "uploads_direct", "dc_mirror_m3u8",
                         "uploads_hls", "lsj_hls", "centaurus_h264", "uploads_creator"]

    def _verify_media(self, url):
        """
        GET+Range 验证媒体 URL 是否真正可播放，返回健康度分级:
          0 = 不可用(直接判死)
          1 = 可用但有风险(moov-at-end 大 mp4: 原始上传未压制，码率常超 CDN 单连限速，
              部分 TVBox 内核对 moov 在尾部的 mp4 拉索引困难 → "放个开头就转圈")
          2 = 健康(正常 m3u8 / faststart mp4 / 小文件 mp4)
        旧版 HEAD 仅认 200 的问题:
          a. 部分 CDN/边缘节点对 HEAD 返回 405/403，可用直链被误判 → 回退嗅探失败；
          b. HEAD 200 不校验内容，XML/HTML 错误页会被误判为可用。
        校验规则(实测 2026-08-15 魔毒圣缘):
          - m3u8: 响应体须含 #EXTM3U，且【不得包含 ai.dramarush.tv】——
            CDN 上的 centaurus master.m3u8 返回 200+#EXTM3U，但 variant 为绝对地址
            指回源站 /api/media/*(匿名 403，且锁定集 AES key=locked)，播放必败，判死。
          - mp4:  Content-Type video/* 或 ftyp/ID3 前缀；再按 box 布局分级——
            头 4KB 含 moov → faststart(2)；含 mdat 无 moov → moov 在文件尾，
            文件 >100MB(未压制原始上传，如魔毒 ep2-4 的 134/168/231MB) → risky(1)。
        超时 3s: 404 响应通常 <200ms 返回，3s 足够覆盖正常 200/206 + 慢节点。
        Range 读 4KB: 覆盖 m3u8 内靠后的 variant/分片行(1KB 可能不够)。
        """
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={
                'User-Agent': self.headers['User-Agent'],
                'Range': 'bytes=0-4095'
            })
            resp = urllib.request.urlopen(req, timeout=3)
            try:
                status = getattr(resp, 'status', None) or resp.getcode()
            except Exception:
                status = 200
            if status not in (200, 206):
                return 0
            ct = (resp.headers.get('Content-Type') or '') if hasattr(resp, 'headers') else ''
            try:
                body = resp.read(4096)
            except Exception:
                return 0
            if '.m3u8' in url.lower():
                if b'#EXTM3U' not in body:
                    return 0
                # variant/分片绝对地址指回源站 → 匿名 403，播放必败(centaurus 坑)
                if b'ai.dramarush.tv' in body:
                    return 0
                return 2
            if ct.startswith('video/') or b'ftyp' in body[:64] or b'ID3' in body[:16]:
                # 文件总长: Content-Range("bytes 0-4095/242192592") 或 Content-Length
                total = 0
                try:
                    cr = resp.headers.get('Content-Range') or ''
                    if '/' in cr:
                        total = int(cr.rsplit('/', 1)[1])
                    else:
                        total = int(resp.headers.get('Content-Length') or 0)
                except Exception:
                    total = 0
                if b'moov' in body:
                    return 2   # moov 在头部: faststart，流式播放友好
                if b'mdat' in body:
                    # mdat 紧跟 ftyp → moov 在文件尾。大文件=未压制原始上传(高码率)，
                    # CDN 单连限速 ~700KB/s 下"开头能放、后续转圈"(魔毒 ep4 实测)
                    return 1 if total > 100 * 1024 * 1024 else 2
                return 2   # 4KB 内未见 moov/mdat(超大 moov 等)，按可用
            if ct.startswith('text/') or 'xml' in ct or 'json' in ct:
                return 0
            return 1
        except Exception:
            return False

    def _probe_cache_get(self, ep_id):
        """读取集级探测缓存，未命中/过期返回 None；命中返回 url（可为 "" 表示负缓存）"""
        try:
            rec = Spider._probe_cache.get(ep_id)
            if not rec:
                return None
            if time.time() - rec[1] > self.cache_ttl:
                return None
            return rec[0]
        except Exception:
            return None

    def _probe_cache_put(self, ep_id, url):
        """写入集级探测缓存（含负缓存）。超过 2000 条清空最旧，防内存膨胀"""
        try:
            if len(Spider._probe_cache) > 2000:
                Spider._probe_cache.clear()
            Spider._probe_cache[ep_id] = (url, time.time())
        except Exception:
            pass

    def _probe_cdn_for_episode(self, ep_id, source_type):
        """
        多路径探测某一集在 CDN 上的可用直链（锁定集核心，也用于 centaurus 免费集回退）。

        实测(2026-08-14): CDN 路径可用性是【集级】差异——同一部剧 ep6 可用而 ep4 404
        (CDN 单段布局渐进同步，新集先有)。故必须逐集探测，结果按 epId 缓存(含负缓存)，
        不能按剧级"源类型→固定路径"一锤定音。

        探测策略(2026-08-15 修复"先完成者胜"bug + 健康度择优):
          旧版并发探测用 as_completed 取【第一个完成且通过校验】的结果——m3u8(几KB)
          总是比 mp4 先返回，导致低优先级 m3u8 抢走高优先级 mp4 的位置(魔毒圣缘 ep3
          播放失败即此因)。
          Phase 1: 优先级第 1 条串行快探——健康(2)直接返回；
          Phase 2: 其余路径并发探测(wait 全部完成/超时)，然后【按优先级顺序】择优:
            先取第一个健康源(2: 正常 m3u8/faststart mp4)，没有再取第一个
            风险源(1: moov-at-end 大 mp4)——速度靠并发，选择靠优先级+健康度。
          健康度意义(2026-08-15 魔毒圣缘 ep4"开头能放后转圈"实测): 未压制的原始
          mp4(ep2-4: 134/168/231MB, moov 在文件尾, 码率~9Mbps)超 CDN 单连限速
          (~700KB/s)，部分内核拉尾部 moov 也困难 → 有更优源(m3u8/faststart)绝不选它，
          但它是唯一源时仍返回(好过嗅探失败)。
          结果(含负结果)按 epId 缓存(TTL 10分钟)，同集重播零网络开销。
        """
        if not ep_id:
            return ""
        cached = self._probe_cache_get(ep_id)
        if cached is not None:
            return cached
        order = self._SOURCE_PRIORITY.get(source_type) or self._DEFAULT_PRIORITY
        cdn_base = "https://" + self.cdn_host

        # 构建候选 (name, url) 列表
        candidates = []
        for name in order:
            tmpl = self._CDN_CANDIDATES.get(name)
            if tmpl:
                candidates.append((name, cdn_base + (tmpl % ep_id)))
        if not candidates:
            self._probe_cache_put(ep_id, "")
            return ""

        def pick(healthy, risky):
            """先健康后风险，各自保持优先级顺序"""
            if healthy:
                return healthy[0]
            if risky:
                return risky[0]
            return ""

        # Phase 1: 优先级第 1 条串行快探(高成功率源通常 1 次命中且健康)
        name0, url0 = candidates[0]
        s0 = self._verify_media(url0)
        if s0 >= 2:
            self._probe_cache_put(ep_id, url0)
            return url0
        risky0 = [url0] if s0 == 1 else []

        # Phase 2: 其余并发探测，完成后按优先级顺序择优
        rest = candidates[1:]
        healthy, risky_rest = [], []
        if rest:
            try:
                from concurrent.futures import ThreadPoolExecutor, wait
                with ThreadPoolExecutor(max_workers=min(len(rest), 6)) as pool:
                    fut_map = [(pool.submit(self._verify_media, url), name, url)
                               for name, url in rest]
                    wait([f for f, _, _ in fut_map], timeout=6)
                    # dict/list 保持插入顺序 = 优先级顺序，不按完成顺序取
                    for f, name, url in fut_map:
                        try:
                            if f.done():
                                s = f.result()
                                if s >= 2:
                                    healthy.append(url)
                                elif s == 1:
                                    risky_rest.append(url)
                        except Exception:
                            pass
            except Exception:
                # ThreadPoolExecutor 不可用时回退串行(极少见)
                for name, url in rest:
                    s = self._verify_media(url)
                    if s >= 2:
                        healthy.append(url)
                    elif s == 1:
                        risky_rest.append(url)

        chosen = pick(healthy, risky0 + risky_rest)
        self._probe_cache_put(ep_id, chosen)
        return chosen

    def _detect_source_type(self, hls_url):
        """从免费集 hlsUrl 检测视频源类型（剧内所有集共用同一种源）"""
        if not hls_url or hls_url == "null":
            return "unknown"
        if "/api/dc/stream/" in hls_url:
            return "dc_stream"
        if "/api/media/" in hls_url:
            if "centaurus" in hls_url:
                return "centaurus"
            if "/dc/mirror/" in hls_url:
                return "dc_mirror_m3u8"
            if "/lsj/hls/" in hls_url:
                return "lsj_hls"
            if "/uploads/hls/" in hls_url:
                return "uploads_hls"
            if "/uploads/creator/" in hls_url:
                return "uploads_creator"
            return "dc_mirror_m3u8"
        if "shorttv.online" in hls_url:
            if "/dc/mirror/" in hls_url:
                return "dc_mirror_mp4"
            if "/uploads/direct/" in hls_url:
                return "cdn_direct"
        return "unknown"

    def _is_watermark_free_url(self, url):
        """
        判断 URL 是否为无水印源。

        站点水印机制(2026-08-15 实测分析):
          centaurus 官方转码 HLS: 站点在转码时烧录水印 → 有水印
          CDN 原始上传 MP4(uploads/direct, dc/mirror): 创作者原始文件 → 无水印
          CDN HLS 镜像(dc/mirror m3u8, lsj, uploads): 不确定(CDN 转码还是站点转码)

        策略: 仅接受 MP4 直链(确定无水印)。
        如实测确认 CDN HLS 镜像也无水印，可改为:
          return 'centaurus' not in url.lower()
        以扩大无水印源命中范围。
        """
        return '.mp4' in url.lower()

    def _fix_hls_url(self, hls_url, ep_id):
        """
        修复免费集 hlsUrl，处理全部 8 种实测格式。

        去水印策略(2026-08-15 新增):
          站点水印仅存在于 centaurus 官方转码 HLS 中(站点转码时烧录)。
          CDN 上的原始上传 MP4(uploads/direct, dc/mirror)为创作者原始文件，无站点水印。
          策略: 所有 HLS 源(centaurus + 其他 m3u8)优先探测 CDN MP4 直链(无水印)，
                MP4 直链命中则直接返回；未命中(无 MP4 可用)走原有逻辑(HLS 兜底)。
          性能: 探测结果按 epId 缓存(TTL 10分钟)，首次播放多 ~1s，重播零开销。
          开关: self.remove_watermark = True 控制是否启用。

        可直接在 CDN 播放的格式:
          1. 绝对 MP4: raw.shorttv.online/... → 替换 raw→cdn
          2. /api/media/ 相对路径(非 centaurus): → 替换 /api/media/→cdn/
          3. /api/media/uploads/creator/ 相对路径: → 同上替换

        需特殊处理的格式:
          4. centaurus HLS: 免费集(带 tok)优先直返官方 HLS(源站 /api/media 通道,
             Referer 鉴权, key 免费集可拿, 480p 仅 1.5Mbps)；
             校验不过(key locked/抖动) → 多路径探测(_probe_cdn_for_episode) CDN mp4；
             全败返回空串回退嗅探。
          5. /api/dc/stream/ MP4: 需 token，CDN 无此路径
             → 直接用站点 URL: ai.dramarush.tv/api/dc/stream/... (免 Referer，实测 200)
        """
        # ===== 去水印: 所有 HLS 源优先探测 CDN MP4 直链(原始上传，无站点水印) =====
        # centaurus 官方转码 HLS 含站点水印；CDN 原始上传 MP4 无水印。
        # 探测按源类型优先序进行(centaurus 源已将 MP4 排在 HLS 前)，
        # _is_watermark_free_url 过滤掉非 MP4 结果(可能有水印)，确保只返回无水印源。
        # 探测结果(含负结果)按 epId 缓存，同集重播零网络开销。
        if self.remove_watermark and ep_id:
            is_hls = ("centaurus" in hls_url) or (".m3u8" in hls_url.lower())
            if is_hls:
                source_type = self._detect_source_type(hls_url)
                cdn_url = self._probe_cdn_for_episode(ep_id, source_type)
                if cdn_url and self._is_watermark_free_url(cdn_url):
                    # 命中无水印 MP4 直链，直接返回
                    return cdn_url
                # 未命中无水印 MP4 → 继续走原有逻辑(HLS 兜底，可能有水印但可播)

        # ===== 以下为原有逻辑(兜底) =====

        if "centaurus" in hls_url:
            # 免费集: watch 发放的官方 centaurus HLS(带 tok)。2026-08-15 实测全链鉴权:
            #   master/index 查 Referer(返回 header 已带)、AES key 免费集可拿
            #   (/api/media-key/{epId} 带 Referer → 16字节)、分片 m4s 免鉴权(206)。
            #   多码率 HLS(480p 仅 1.5Mbps)远优于 CDN 上的原始 mp4(未压制 moov-at-end)，
            #   → 优先直返官方 HLS，校验不过再回退 CDN 多路径探测。
            #   注意: 去水印模式下此为兜底(上方探测未命中无水印 MP4 时才走到这里)，
            #         返回的 centaurus HLS 含水印。
            full = hls_url if hls_url.startswith("http") else self.site_url + hls_url
            if self._verify_centaurus_playable(full, ep_id):
                return full
            # 锁定集 key=locked(每集独立 key 不可借)或源站抖动 → CDN 多路径探测 mp4
            if ep_id:
                url = self._probe_cdn_for_episode(ep_id, "centaurus")
                if url:
                    return url
            return ""

        if "/api/dc/stream/" in hls_url:
            return self.site_url + hls_url

        if hls_url.startswith("/api/media/"):
            return "https://" + self.cdn_host + hls_url.replace("/api/media/", "/")

        hls_url = hls_url.replace("raw.shorttv.online", self.cdn_host)

        if "m3u8" in hls_url and "ai.dramarush.tv/api/media/" in hls_url:
            hls_url = hls_url.replace(
                "ai.dramarush.tv/api/media/",
                self.cdn_host + "/"
            )
        return hls_url

    def _verify_centaurus_playable(self, url, ep_id):
        """
        验证源站官方 centaurus HLS 在当前条件下(匿名+Referer)可整链播放。
        鉴权模型(2026-08-15 实测):
          master/index: 查 Referer → 播放 header 已带，内核继承后可拉；
          AES key: /api/media-key/{epId} 带 Referer —— 免费集 200(16字节)，
            锁定集 403 "locked"(每集独立 key，免费集 tok 不可借)；
          分片 m4s: 免鉴权(无 Referer 也 206)。
        故仅需验证: master 带 Referer 200 含 #EXTM3U + key 可获取。
        结果按 epId 缓存(_probe_cache, 键加 ctau: 前缀, TTL 10分钟)。
        """
        if not url:
            return False
        cache_key = "ctau:" + (ep_id or url[-48:])
        cached = self._probe_cache_get(cache_key)
        if cached is not None:
            return bool(cached)
        ok = False
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={
                'User-Agent': self.headers['User-Agent'],
                'Referer': self.site_url + '/'
            })
            resp = urllib.request.urlopen(req, timeout=4)
            try:
                status = getattr(resp, 'status', None) or resp.getcode()
            except Exception:
                status = 200
            body = resp.read(4096) if status in (200, 206) else b''
            if status in (200, 206) and b'#EXTM3U' in body:
                if ep_id:
                    kreq = urllib.request.Request(
                        self.site_url + "/api/media-key/" + ep_id,
                        headers={
                            'User-Agent': self.headers['User-Agent'],
                            'Referer': self.site_url + '/'
                        })
                    kresp = urllib.request.urlopen(kreq, timeout=4)
                    kbody = kresp.read(32)
                    ok = len(kbody) == 16
                else:
                    ok = True
        except Exception:
            ok = False
        self._probe_cache_put(cache_key, url if ok else "")
        return ok

    def _get_source_type(self, drama_id):
        """
        获取剧目的视频源类型(通过检查免费集 hlsUrl)，剧级 TTL 缓存。
        用于锁定集播放：锁定集 hlsUrl=null，需通过免费集推断源类型，
        再按源类型优先级排序 CDN 候选路径逐集探测。
        """
        try:
            rec = Spider._source_cache.get(drama_id)
            if rec and time.time() - rec[1] < self.cache_ttl:
                return rec[0]
        except Exception:
            pass
        d = self._trpc("drama.byId", {"id": drama_id})
        st = self._detect_source_type_from_drama(d, drama_id) if d else "unknown"
        try:
            Spider._source_cache[drama_id] = (st, time.time())
        except Exception:
            pass
        return st

    def _cached_source_type(self, drama_id):
        """只读源类型缓存，不触发网络请求。未命中返回 "unknown"(用默认优先级探测)。
        优化启动速度: 锁定集播放时不再串行等 _get_source_type(2次tRPC)，
        缓存命中(详情页已预缓存)用其优先级排序，未命中直接默认优先级并发探测。"""
        try:
            rec = Spider._source_cache.get(drama_id)
            if rec and time.time() - rec[1] < self.cache_ttl:
                return rec[0]
        except Exception:
            pass
        return "unknown"

    def _detect_source_type_from_drama(self, d, drama_id):
        """从已有的 drama.byId 数据检测源类型，避免重复 API 调用"""
        if not d:
            return "unknown"
        eps = d.get("episodes") or []
        for ep in eps:
            if not ep.get("locked"):
                watch = self._trpc("episode.watch", {"dramaId": drama_id, "index": ep.get("index", 1)})
                if watch:
                    free_ep = watch.get("episode") or {}
                    free_hls = free_ep.get("hlsUrl")
                    if free_hls and free_hls != "null":
                        return self._detect_source_type(free_hls)
                    break
        dc_mirror = d.get("dcMirror", False)
        if dc_mirror:
            return "dc_mirror_mp4"
        return "unknown"

    # ==================== TVBox 接口 ====================

    def homeContent(self, filter):
        video_list = self._fetch_home_recommend()
        filters = {}
        for c in self.categories:
            filters[c["type_id"]] = self._filters_for(c["type_id"])
        return {"class": self.categories, "list": video_list, "filters": filters}

    def _fetch_home_recommend(self):
        """多分类混合推荐：各题材分类各取热门剧目交叉排列后去重"""
        cat_slugs = ["fantasy", "comedy", "romance", "ceo"]
        per_cat = 10
        target = 30
        cat_items = []
        for slug in cat_slugs:
            data = self._trpc("drama.list", {
                "limit": per_cat, "cursor": None,
                "categorySlug": slug, "sort": "hot"
            })
            if data and data.get("items"):
                cat_items.append(data["items"])
            else:
                cat_items.append([])
        video_list = []
        seen = set()
        for i in range(per_cat):
            for items in cat_items:
                if i >= len(items):
                    continue
                it = items[i]
                vid = it.get("id", "")
                if vid in seen:
                    continue
                seen.add(vid)
                video_list.append(self._parse_item(it))
                if len(video_list) >= target:
                    break
            if len(video_list) >= target:
                break
        return video_list

    def homeVideoContent(self):
        return {"list": self.homeContent(False).get("list", [])}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        return self._list_response(tid, page, extend)

    def detailContent(self, ids):
        """详情页：剧集信息 + 选集列表。选集编码: "集名$dramaId:epIndex"
        优化: 缓存全部剧集的 (epId, locked)，播放时若 episode.watch 因站点
        SSL 抖动失败，可直接取 epId 探测 CDN，不再卡死在 tRPC 重试。"""
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        d = self._trpc("drama.byId", {"id": vod_id})
        if not d:
            return {"list": []}

        title = d.get("title", "") or ""
        pic = self._pick_pic(d)
        content = d.get("description", "") or ""

        cats = [c.get("name", "") for c in (d.get("categories") or []) if c.get("name")]
        tags = [t.get("name", "") for t in (d.get("tags") or []) if t.get("name")]
        type_str = " ".join(cats + tags)
        if type_str:
            content = (content + "\n分类: " + type_str).strip()

        area = d.get("region", "") or ""
        year = str(d.get("year") or "")
        remark = self._remark(d)

        eps = d.get("episodes") or []
        play_urls = []
        try:
            # 缓存 epId/locked，供播放时 tRPC 失败的旁路
            if len(Spider._epid_cache) > 500:
                Spider._epid_cache.clear()
            pairs = []
            for ep in eps:
                # 序号回退与下方 play_urls 构建保持一致(index 缺失时按位置 1,2,3...)
                idx = ep.get("index") or (len(pairs) + 1)
                pairs.append((idx, ep.get("id", ""), bool(ep.get("locked"))))
            ecache = {"_ts": time.time()}
            for idx, eid, locked in pairs:
                ecache[idx] = (eid, locked)
            Spider._epid_cache[vod_id] = ecache
        except Exception:
            pass
        for ep in eps:
            idx = ep.get("index") or (len(play_urls) + 1)
            ep_name = ep.get("title") or ("第%d集" % idx)
            play_urls.append("%s$%s:%d" % (ep_name, vod_id, idx))
        vod_play_url = "#".join(play_urls)

        result = [{
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": content,
            "vod_area": area,
            "vod_year": year,
            "vod_actor": "",
            "vod_director": "",
            "vod_remarks": remark,
            "vod_play_from": "DramaRush",
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        tid = "search:" + (key or "")
        r = self._list_response(tid, page)
        return {"list": r["list"], "page": r["page"], "pagecount": r["pagecount"]}

    def playerContent(self, flag, id, vipFlags):
        """
        播放：episode.watch tRPC 获取播放 URL，锁定集走 CDN 多路径探测。

        去水印(2026-08-15):
          免费集 HLS 源(centaurus 等)在 _fix_hls_url 中优先探测 CDN MP4 直链(无水印)。
          锁定集本身就走 CDN 探测(无水印)，无需额外处理。
          仅当 CDN 无 MP4 可用时回退到 HLS(可能有水印)。

        免费集: hlsUrl 有值，通过 _fix_hls_url 统一处理全部 8 种格式。
        锁定集: hlsUrl=null:
          - _probe_cdn_for_episode 按源类型优先级逐集探测 7 条 CDN 路径
            (集级差异: 同剧部分集有 CDN 布局部分没有)，命中即返回直链(parse=0)；
          - 全路径 404(如 dc_stream/uploads_creator 源，tok 绑定 epId 不可借)
            → 回退嗅探 watch 页面(parse=1)。
        """
        try:
            return self._playerContent(flag, id, vipFlags)
        except Exception as e:
            print("[DramaRush] playerContent 异常: %s" % e)
            if ":" in id:
                parts = id.rsplit(":", 1)
                drama_id = parts[0]
                try:
                    ep_index = int(parts[1])
                except ValueError:
                    drama_id = id
                    ep_index = 1
            else:
                drama_id = id
                ep_index = 1
            watch_url = "%s/en/watch/%s/%d" % (self.site_url, drama_id, ep_index)
            return {"parse": 1, "url": watch_url, "header": self.headers}

    def _playerContent(self, flag, id, vipFlags):
        # 解析 id: "dramaId:epIndex"
        if ":" in id:
            parts = id.rsplit(":", 1)
            drama_id = parts[0]
            try:
                ep_index = int(parts[1])
            except ValueError:
                drama_id = id
                ep_index = 1
        else:
            drama_id = id
            ep_index = 1

        play_headers = {
            'User-Agent': self.headers['User-Agent'],
            'Referer': self.site_url + "/"
        }
        sniff_url = "%s/en/watch/%s/%d" % (self.site_url, drama_id, ep_index)

        # ===== Step 1: episode.watch tRPC 获取播放信息 =====
        watch_data = self._trpc("episode.watch", {"dramaId": drama_id, "index": ep_index})

        if watch_data and isinstance(watch_data, dict):
            episode = watch_data.get("episode") or {}
            hls_url = episode.get("hlsUrl")
            ep_id = episode.get("id")

            # 免费集：hlsUrl 不为 null
            if hls_url and hls_url != "null":
                fixed_url = self._fix_hls_url(hls_url, ep_id)
                if fixed_url:
                    return {"parse": 0, "url": fixed_url, "header": play_headers}
                return {"parse": 1, "url": sniff_url, "header": self.headers}

            # 锁定集：hlsUrl 为 null → 多路径探测(集级)
            # 优化: 源类型缓存命中则用其优先级排序；未命中直接用默认优先级并发探测，
            #   不再串行等 _get_source_type(2次tRPC，SSL抖动时可能 2-10s)。
            #   源类型仅影响探测顺序(7条路径都会试)，不影响最终结果。
            #   锁定集探测结果可能含 HLS(非 centaurus 的 CDN 镜像，可能无水印)，
            #   去水印过滤仅在 _fix_hls_url(免费集)中执行，锁定集返回任意可用源。
            if ep_id:
                source_type = self._cached_source_type(drama_id)
                cdn_url = self._probe_cdn_for_episode(ep_id, source_type)
                if cdn_url:
                    return {"parse": 0, "url": cdn_url, "header": play_headers}
            return {"parse": 1, "url": sniff_url, "header": self.headers}

        # ===== Step 2: episode.watch 失败 → epId 缓存旁路(零 tRPC) =====
        # 详情页 drama.byId 已缓存全部 epId/locked；watch 因站点 SSL 抖动失败时，
        # 直接用缓存 epId 探测 CDN(探测只打 CDN 域，不受源站抖动影响)，
        # 不再先赌 drama.byId(抖动时又是 10-20s 超时，魔毒圣缘 ep2/ep4 即此坑)。
        bypass_hit = False
        try:
            ecache = Spider._epid_cache.get(drama_id)
            if ecache and time.time() - ecache.get("_ts", 0) < self.cache_ttl:
                entry = ecache.get(ep_index)
                if entry and entry[0]:
                    bypass_hit = True
                    cdn_url = self._probe_cdn_for_episode(
                        entry[0], self._cached_source_type(drama_id))
                    if cdn_url:
                        return {"parse": 0, "url": cdn_url, "header": play_headers}
                    # 缓存命中但 7 条路径全 404(如 dc_stream/uploads_creator 源)
                    # → 探测路径集合与顺序无关，byId 重探必得同样结果，直接嗅探。
        except Exception:
            pass

        # ===== Step 2b: 缓存未命中，回退 drama.byId + 逐集探测 =====
        if not bypass_hit:
            d = self._trpc("drama.byId", {"id": drama_id})
            if d:
                source_type = self._detect_source_type_from_drama(d, drama_id)
                eps = d.get("episodes") or []
                for ep in eps:
                    if (ep.get("index") or 0) == ep_index:
                        ep_id = ep.get("id", "")
                        if ep_id:
                            cdn_url = self._probe_cdn_for_episode(ep_id, source_type)
                            if cdn_url:
                                return {"parse": 0, "url": cdn_url, "header": play_headers}
                        break

        # ===== Step 3: 最终兜底 → 嗅探 watch 页面 =====
        return {"parse": 1, "url": sniff_url, "header": self.headers}

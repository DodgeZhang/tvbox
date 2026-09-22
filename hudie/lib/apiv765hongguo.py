# -*- coding: utf-8 -*-

import re
import json
import ssl
import gzip
import urllib.parse
import urllib.request
import html as html_mod

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def getName(self): return ""
        def homeContent(self, filter): return {}
        def homeVideoContent(self): return {}
        def categoryContent(self, tid, pg, filter, extend): return {}
        def detailContent(self, ids): return {}
        def searchContent(self, key, quick, pg="1"): return {}
        def playerContent(self, flag, id, vipFlags): return {}


class Spider(BaseSpider):
    BASE_URL = "https://hongguoduanju.com"
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    # 微信公众号加密数据（完整版本）
    _w_full_data = [141, 209, 192, 131, 216, 212, 138, 218, 219, 129, 223, 255, 132, 251, 232, 16, 214, 136, 166, 141, 229, 245, 143, 218, 218, 139, 228, 193, 131, 210, 239, 67, 155, 227, 190, 65, 213, 136, 204, 94, 94, 82, 83, 64, 86, 109, 70, 80, 81, 140, 221, 192, 182, 168, 191, 212, 173, 220, 138, 202, 253, 131, 201, 247, 183, 195, 205, 139, 221, 229, 146, 229, 162, 213, 130, 139, 141, 243, 198, 129, 221, 229, 138, 213, 236, 128, 222, 217, 137, 211, 217]
    # 线路文本加密数据
    _w_line_data = [142, 213, 254, 130, 237, 238, 135, 226, 216, 129, 216, 222, 135, 197, 216, 18, 65, 213, 136, 204, 94, 94, 82, 83, 64, 86, 109, 70, 80, 81, 72, 135, 206, 207, 215, 186, 169, 211, 213, 222, 134, 192, 225]
    _w_key = b"hongguo_wechat_2026"

    # 分类配置
    CATEGORIES = [
        # 背景分类
        {"type_id": "bg_modern", "type_name": "现代", "url": "/category?background=cate_757"},
        {"type_id": "bg_city", "type_name": "都市", "url": "/category?background=cate_1"},
        {"type_id": "bg_ancient", "type_name": "古代", "url": "/category?background=cate_758"},
        {"type_id": "bg_countryside", "type_name": "乡村", "url": "/category?background=cate_11"},
        {"type_id": "bg_era", "type_name": "年代", "url": "/category?background=cate_79"},
        {"type_id": "bg_office", "type_name": "职场", "url": "/category?background=cate_127"},
        {"type_id": "bg_Republic", "type_name": "民国", "url": "/category?background=cate_390"},
        {"type_id": "bg_campus", "type_name": "校园", "url": "/category?background=cate_4"},
        {"type_id": "bg_palace", "type_name": "宫廷", "url": "/category?background=cate_1153"},
        # 主题分类
        {"type_id": "topic_romance", "type_name": "现言", "url": "/category?topic=cate_1021"},
        {"type_id": "topic_growth", "type_name": "女性成长", "url": "/category?topic=cate_1048"},
        {"type_id": "topic_fantasy", "type_name": "奇幻", "url": "/category?topic=cate_1020"},
        {"type_id": "topic_xianxia", "type_name": "仙侠", "url": "/category?topic=cate_1013"},
        {"type_id": "topic_political", "type_name": "权谋", "url": "/category?topic=cate_1047"},
        {"type_id": "topic_suspense", "type_name": "悬疑", "url": "/category?topic=cate_165"},
        {"type_id": "topic_horror", "type_name": "灵异", "url": "/category?topic=cate_751"},
        {"type_id": "topic_crime", "type_name": "刑侦", "url": "/category?topic=cate_1148"},
        {"type_id": "topic_martial", "type_name": "武侠", "url": "/category?topic=cate_1172"},
        {"type_id": "topic_scifi", "type_name": "科幻", "url": "/category?topic=cate_1092"},
        {"type_id": "topic_terror", "type_name": "恐怖", "url": "/category?topic=cate_1219"},
        # 设定分类
        {"type_id": "setting_rebirth", "type_name": "重生", "url": "/category?setting=cate_36"},
        {"type_id": "setting_transmigration", "type_name": "穿越", "url": "/category?setting=cate_37"},
        {"type_id": "setting_system", "type_name": "系统", "url": "/category?setting=cate_19"},
        {"type_id": "setting_fakemarr", "type_name": "先婚后爱", "url": "/category?setting=cate_265"},
        {"type_id": "setting_wealthy", "type_name": "豪门", "url": "/category?setting=cate_936"},
        {"type_id": "setting_revenge", "type_name": "打脸虐渣", "url": "/category?setting=cate_1051"},
        {"type_id": "setting_bigboss", "type_name": "大女主", "url": "/category?setting=cate_760"},
        # 其它
        {"type_id": "sort_hot", "type_name": "最热", "url": "/category?sort_type=1"},
        {"type_id": "sort_new", "type_name": "最新", "url": "/category?sort_type=2"},
    ]

    def init(self, extend=""):
        pass

    def getName(self):
        return "红果短剧"

    def _get_wechat_info(self):
        try:
            # XOR decrypt
            key = self._w_key
            data = self._w_full_data
            plain = bytearray(len(data))
            for i in range(len(data)):
                plain[i] = data[i] ^ key[i % len(key)]
            return plain.decode('utf-8')
        except Exception as e:
            # Fallback: try alternative method
            try:
                key = self._w_key
                data = self._w_full_data
                result = []
                for i in range(len(data)):
                    result.append(chr(data[i] ^ key[i % len(key)]))
                return ''.join(result)
            except Exception:
                return ''

    def _get_line_info(self):
        try:
            key = self._w_key
            data = self._w_line_data
            plain = bytearray(len(data))
            for i in range(len(data)):
                plain[i] = data[i] ^ key[i % len(key)]
            return plain.decode('utf-8')
        except Exception:
            try:
                key = self._w_key
                data = self._w_line_data
                result = []
                for i in range(len(data)):
                    result.append(chr(data[i] ^ key[i % len(key)]))
                return ''.join(result)
            except Exception:
                return '红果短剧'

    def getHtml(self, url):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            try:
                ctx.set_ciphers("DEFAULT@SECLEVEL=1:HIGH:!aNULL:!MD5")
            except Exception:
                pass
            req = urllib.request.Request(url, headers={
                "User-Agent": self.UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Referer": self.BASE_URL + "/"
            })
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                data = resp.read()
                content_encoding = resp.headers.get("Content-Encoding", "")
                if "gzip" in content_encoding:
                    try:
                        data = gzip.decompress(data)
                    except Exception:
                        pass
                for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
                    try:
                        return data.decode(enc)
                    except Exception:
                        continue
                return data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _extract_ssr_data(self, html):
        match = re.search(r'window\._ROUTER_DATA\s*=\s*({.*?})\s*;?\s*</script>', html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        return None

    def _parse_video_item(self, item):
        """Parse a video item from recommendList"""
        if not item:
            return None
        try:
            series_id = str(item.get('series_id', ''))
            if not series_id:
                return None

            name = item.get('series_name', '')
            pic = item.get('series_cover', '')
            intro = item.get('series_intro', '')
            tags = item.get('tags', [])
            episode_cnt = item.get('episode_cnt', 0)
            episode_right_text = item.get('episode_right_text', '')

            # Build remarks
            remarks = episode_right_text if episode_right_text else f"共{episode_cnt}集"

            # Add WeChat info to description
            wechat_info = self._get_wechat_info()
            if wechat_info:
                intro = (intro + '\n\n' + wechat_info) if intro else wechat_info

            return {
                "vod_id": series_id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remarks,
                "vod_content": intro,
                "vod_class": ', '.join(tags[:3]) if tags else '',
            }
        except Exception:
            return None

    def homeContent(self, filter):
        return {"class": self.CATEGORIES, "filters": {}}

    def homeVideoContent(self):
        result = {"list": []}
        html = self.getHtml(self.BASE_URL + "/category?sort_type=1")
        if not html:
            return result

        data = self._extract_ssr_data(html)
        if not data:
            return result

        loader = data.get('loaderData', {})
        cat_page = loader.get('category_page', {})
        recommend_list = cat_page.get('recommendList', [])

        videos = []
        for item in recommend_list[:30]:
            v = self._parse_video_item(item)
            if v:
                videos.append(v)

        result["list"] = videos
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": str(pg), "pagecount": "1", "total": "0"}
        try:
            cat = None
            for c in self.CATEGORIES:
                if c["type_id"] == str(tid):
                    cat = c
                    break
            if not cat:
                return result

            url = self.BASE_URL + cat['url']
            html = self.getHtml(url)
            if not html:
                return result

            data = self._extract_ssr_data(html)
            if not data:
                return result

            loader = data.get('loaderData', {})
            cat_page = loader.get('category_page', {})
            recommend_list = cat_page.get('recommendList', [])

            videos = []
            for item in recommend_list:
                v = self._parse_video_item(item)
                if v:
                    videos.append(v)

            if videos:
                # Implement pagination
                page_size = 30
                page = int(pg) if pg and str(pg).isdigit() else 1
                total = len(videos)
                total_pages = (total + page_size - 1) // page_size
                
                start_idx = (page - 1) * page_size
                end_idx = start_idx + page_size
                
                paged_videos = videos[start_idx:end_idx]
                
                result["list"] = paged_videos
                result["pagecount"] = str(total_pages)
                result["total"] = str(total)

            return result
        except Exception:
            return result

    def detailContent(self, ids):
        result = {"list": []}
        vid = ids[0] if isinstance(ids, list) and ids else ids

        html = self.getHtml(f"{self.BASE_URL}/detail?series_id={vid}")
        if not html:
            return result

        data = self._extract_ssr_data(html)
        if not data:
            return result

        loader = data.get('loaderData', {})
        detail_page = loader.get('detail_page', {})
        series_detail = detail_page.get('seriesDetail', {})

        if not series_detail:
            return result

        series_id = str(series_detail.get('series_id', ''))
        series_name = series_detail.get('series_name', '')
        series_cover = series_detail.get('series_cover', '')
        series_intro = series_detail.get('series_intro', '')
        tags = series_detail.get('tags', [])
        episode_cnt = series_detail.get('episode_cnt', 0)
        episode_right_text = series_detail.get('episode_right_text', '')
        vid_list = series_detail.get('vid_list', [])
        celebrities = series_detail.get('celebrities', [])

        if not series_name:
            return result

        # Build play list
        play_groups = []
        for i, ep_vid in enumerate(vid_list):
            ep_name = f"第{i+1}集"
            play_link = f"{self.BASE_URL}/player/{series_id}/{ep_vid}"
            play_groups.append(f"{ep_name}${play_link}")

        if not play_groups:
            play_groups.append(f"第1集${self.BASE_URL}/player/{series_id}")

        # Build actor/director info
        actor_names = []
        for celeb in celebrities:
            nickname = celeb.get('nickname', '')
            if nickname:
                actor_names.append(nickname)

        # Add WeChat info to description
        wechat_info = self._get_wechat_info()
        desc = series_intro + '\n\n' + wechat_info

        # Get line info
        line_info = self._get_line_info()

        vod = {
            "vod_id": series_id,
            "vod_name": series_name,
            "vod_pic": series_cover,
            "vod_actor": ', '.join(actor_names[:10]) if actor_names else '',
            "vod_director": '',
            "vod_year": '',
            "vod_area": '',
            "vod_remarks": episode_right_text or f"共{episode_cnt}集",
            "vod_content": desc,
            "vod_class": ', '.join(tags[:3]) if tags else '',
            "type_name": ', '.join(tags[:3]) if tags else '',
            "vod_play_from": line_info,
            "vod_play_url": '#'.join(play_groups),
        }

        result['list'] = [vod]
        return result

    def searchContent(self, key, quick, pg="1"):
        result = {"list": [], "page": str(pg), "pagecount": "1", "total": "0"}
        try:
            kw_lower = key.lower()
            page = int(pg) if pg and str(pg).isdigit() else 1
            page_size = 30
            
            # Try to get data from category page (tag search and fallback share same data)
            encoded_key = urllib.parse.quote(key)
            html = self.getHtml(f"{self.BASE_URL}/category?sort_type=1")
            
            if not html:
                html = self.getHtml(f"{self.BASE_URL}/category?tag={encoded_key}")
            
            if html:
                data = self._extract_ssr_data(html)
                if data:
                    loader = data.get('loaderData', {})
                    cat_page = loader.get('category_page', {})
                    recommend_list = cat_page.get('recommendList', [])

                    # Filter results by keyword (name, intro, tags)
                    filtered = []
                    for item in recommend_list:
                        name = item.get('series_name', '').lower()
                        intro = item.get('series_intro', '').lower()
                        tags = [t.lower() for t in item.get('tags', [])]
                        if kw_lower in name or kw_lower in intro or any(kw_lower in t for t in tags):
                            v = self._parse_video_item(item)
                            if v:
                                filtered.append(v)

                    # If no results, return popular videos as fallback
                    if not filtered:
                        for item in recommend_list[:50]:
                            v = self._parse_video_item(item)
                            if v:
                                filtered.append(v)

                    if filtered:
                        total = len(filtered)
                        total_pages = (total + page_size - 1) // page_size
                        start_idx = (page - 1) * page_size
                        end_idx = start_idx + page_size
                        paged_results = filtered[start_idx:end_idx]
                        
                        result["list"] = paged_results
                        result["pagecount"] = str(total_pages)
                        result["total"] = str(total)

            return result
        except Exception:
            return result

    def playerContent(self, flag, id, vipFlags):
        # Handle id that may contain episode name (e.g., "第1集$URL")
        play_url = id
        if '$' in play_url:
            play_url = play_url.split('$', 1)[1]
        if not play_url.startswith("http"):
            play_url = self.BASE_URL + "/" + play_url.lstrip("/")

        play_headers = {
            "User-Agent": self.UA,
            "Referer": self.BASE_URL + "/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        html = self.getHtml(play_url)
        if html:
            data = self._extract_ssr_data(html)
            if data:
                loader = data.get('loaderData', {})

                # Find the player page key
                player_page = None
                for key in loader:
                    if 'page' in key.lower() and 'player' in key.lower():
                        player_page = loader[key]
                        break

                if player_page:
                    video_player_info = player_page.get('video_player_info', {})
                    main_url = video_player_info.get('main_url', '')

                    if main_url:
                        if main_url.startswith("//"):
                            main_url = "https:" + main_url
                        # Check if it's a direct video URL (check path without query params)
                        parsed = urllib.parse.urlparse(main_url)
                        path_lower = parsed.path.lower()
                        is_direct = path_lower.endswith(".mp4") or path_lower.endswith(".m3u8")
                        # Also check if URL contains video markers
                        if not is_direct and ("video" in path_lower or "tos" in path_lower):
                            is_direct = True
                        return {
                            "url": main_url,
                            "parse": "0" if is_direct else "1",
                            "header": json.dumps(play_headers),
                            "playUrl": "",
                            "subtitle": ""
                        }

        return {
            "url": play_url,
            "parse": "1",
            "header": json.dumps(play_headers),
            "playUrl": "",
            "subtitle": ""
        }

    def __jsEvalReturn(self):
        return {"proxy": None}
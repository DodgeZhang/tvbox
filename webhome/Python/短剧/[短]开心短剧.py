# coding: utf-8
# ============================================================
# 站点名称: 开心短剧 (KaiXin DuanJu)
# 主域名  : https://kaixinduanju.com
# 语言    : 简繁混合 (zh-TW / zh-CN)，请求 Accept-Language: zh-TW
# 站点类型: Tailwind + PWA 静态 HTML 站（非 SPA，curl 可直取）
# 内容类型: YouTube 内嵌短剧聚合站（每个 /play/ 即一部完整短剧，单集）
#
# 结构说明（2026-09 实测）:
#   - 首页       : /                     固定 24 张卡片（?page 无效、不分页）
#   - 分类       : 无传统分类导航，只有 tag 系统
#                  /tag/{name}           返回该 tag 的全部卡片（不分页，pagecount=1）
#   - 详情/播放  : /play/{slug}          单个 YouTube 内嵌视频
#                  内嵌: youtube.com/embed/{videoId}
#                  封面: https://img.kaixinduanju.com/vi/{videoId}/mqdefault.jpg
#   - 搜索       : GET /search?keyword={kw}&page={N}   （分页有效）
#
# 播放策略（2026-09-27 重构）:
#   服务端直接提取 YouTube 直链（内置 YouTubeLite，ANDROID_VR 明文优先，
#   自带 sig/nsig 解密）。成功则用本地 DASH MPD 代理（parse:0，video+audio
#   分轨走 127.0.0.1:9978 本地代理，Range 透传），失败回退 embed(parse:1)。
#   盒子自带 YouTube 解析把 watch?v= 解成异常流（时长爆表/卡住），故不用之。
#
# 最后验证: 2026-09-27  测试 videoId: 8R007-adeMQ
# ============================================================
import re
import os
import sys
import json
import time
import html
import html as _html
from urllib.parse import (quote, unquote, parse_qs, urlencode,
                          urlparse, urlunparse)

try:
    import requests
except Exception:
    requests = None

from base.spider import Spider as BaseSpider


class YouTubeLite:
    def __init__(self, session, headers=None, config=None):
        self.session = session
        self.headers = headers or {}
        self.config = config or {}
        self.player_cache = {}
        self.extract_cache = {}
        self.sig_plan_cache = {}
        self.extract_cache_ttl = int(self.config.get('extract_cache_ttl') or 300)

    def extract(self, url_or_id):
        video_id = self.extract_video_id(url_or_id)
        cached = self.extract_cache.get(video_id)
        now = time.time()
        if cached and cached.get('expires', 0) > now:
            return cached.get('data')
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        extract_started = time.time()
        watch_started = time.time()
        page_resp = self._get(watch_url)
        page = page_resp.text
        ytcfg = self._extract_ytcfg(page) or {}
        player_response = self._extract_initial_player_response(page) or {}
        player_url = self._extract_player_url(page)
        api_key = ytcfg.get('INNERTUBE_API_KEY') or self._search(r'"INNERTUBE_API_KEY":"([^"]+)"', page)
        visitor_data = self._extract_visitor_data(ytcfg, player_response)
        # ANDROID_VR 返回明文 URL，不需要下载 base.js 提取 signatureTimestamp。
        sts = None
        context = ytcfg.get('INNERTUBE_CONTEXT') or {
            'client': {'clientName': 'WEB', 'clientVersion': '2.20240310.01.00', 'hl': 'en', 'gl': 'US'}
        }
        responses = [player_response] if player_response else []
        if api_key:
            api_responses = self._call_player_api(video_id, api_key, context, watch_url, visitor_data, sts)
            if not isinstance(api_responses, list):
                api_responses = [api_responses] if api_responses else []
            responses.extend([x for x in api_responses if x])
        player_response = next((x for x in responses if (x.get('playabilityStatus') or {}).get('status') == 'OK'), player_response)
        status = (player_response.get('playabilityStatus') or {}).get('status')
        streaming = player_response.get('streamingData') or {}
        if status and status not in ('OK', 'LIVE_STREAM_OFFLINE') and not streaming:
            reason = (player_response.get('playabilityStatus') or {}).get('reason') or status
            raise Exception(f'YouTube 不可播放: {reason}')
        details = player_response.get('videoDetails') or {}
        raw_formats = []
        seen_raw = set()
        source_counts = []
        for response in responses:
            response_streaming = (response or {}).get('streamingData') or {}
            source_raw = (response_streaming.get('formats') or []) + (response_streaming.get('adaptiveFormats') or [])
            source_counts.append({'formats': len(response_streaming.get('formats') or []), 'adaptive': len(response_streaming.get('adaptiveFormats') or [])})
            for raw in source_raw:
                key = (raw.get('itag'), raw.get('url') or raw.get('signatureCipher') or raw.get('cipher') or raw.get('mimeType'))
                if key not in seen_raw:
                    seen_raw.add(key)
                    raw = raw.copy()
                    raw['_client_name'] = (response or {}).get('_client_name')
                    raw['_client_ua'] = (response or {}).get('_client_ua')
                    raw_formats.append(raw)
        formats = []
        cipher_count = 0
        for raw in raw_formats:
            if raw.get('signatureCipher') or raw.get('cipher'):
                cipher_count += 1
            item = self._normalize_format(raw, player_url)
            if item and item.get('url'):
                formats.append(item)
        if not formats:
            raise Exception('未获取到可用播放地址')
        data = {
            'id': video_id,
            'title': details.get('title') or video_id,
            'duration': int(details.get('lengthSeconds') or 0),
            'formats': formats,
        }
        self.extract_cache[video_id] = {'data': data, 'expires': time.time() + self.extract_cache_ttl}
        return data

    @staticmethod
    def extract_video_id(text):
        text = str(text or '').strip()
        for pattern in [
            r'(?:v=|/v/|/embed/|/shorts/|youtu\.be/)([0-9A-Za-z_-]{11})',
            r'^([0-9A-Za-z_-]{11})$',
        ]:
            m = re.search(pattern, text)
            if m:
                return m.group(1)
        raise Exception('无法识别 YouTube 视频 ID')
    def _client_name_id(self, client_name):
        return {
            'WEB': 1,
            'MWEB': 2,
            'ANDROID': 3,
            'IOS': 5,
            'TVHTML5': 7,
            'ANDROID_VR': 28,
            'WEB_EMBEDDED_PLAYER': 56,
            'WEB_REMIX': 67,
        }.get(client_name, 1)

    def _extract_visitor_data(self, ytcfg, player_response):
        return (
            self.config.get('visitor_data')
            or ytcfg.get('VISITOR_DATA')
            or (((ytcfg.get('INNERTUBE_CONTEXT') or {}).get('client') or {}).get('visitorData'))
            or ((player_response.get('responseContext') or {}).get('visitorData'))
        )

    def _extract_signature_timestamp(self, video_id, player_url, ytcfg=None):
        try:
            code = self._get_player_code(player_url)
            sts = self._search(r'(?:signatureTimestamp|sts)\s*:\s*(\d{5})', code)
            return int(sts) if sts else None
        except Exception:
            return None

    def _get_po_token(self, client_name, context='gvs'):
        tokens = self.config.get('po_token') or self.config.get('po_tokens') or {}
        if isinstance(tokens, str):
            return tokens
        if isinstance(tokens, dict):
            return tokens.get(f'{client_name}.{context}') or tokens.get(client_name) or tokens.get(context)
        return None

    def choose_playable(self, formats, quality=None):
        all_videos = [x for x in formats if x.get('vcodec') != 'none' and x.get('acodec') == 'none']
        candidates = all_videos[:]
        if quality == '4k':
            candidates = [x for x in candidates if int(x.get('height') or 0) >= 2160]
        elif quality == '2k':
            candidates = [x for x in candidates if 1440 <= int(x.get('height') or 0) < 2160]
        elif quality == '1080p':
            candidates = [x for x in candidates if 1000 <= int(x.get('height') or 0) < 1440]
        elif quality == 'best':
            safe_candidates = [x for x in candidates if not self._is_risky_best_video(x)]
            if safe_candidates:
                candidates = safe_candidates
        else:
            candidates = [x for x in candidates if int(x.get('height') or 0) >= 1080]
        if not candidates and quality == 'best':
            candidates = all_videos
        if not candidates:
            return None
        # 画质优先，编码顺序 VP9/HDR > H264 > AV1。保留 VP9 Profile 2 HDR，
        # 只把 AV1 放到最后，避免默认选到 itag 701/702 的超大 AV1 分段。
        candidates.sort(key=lambda x: (
            self._video_codec_priority(x),
            int(x.get('height') or 0),
            int(x.get('bitrate') or 0)
        ), reverse=True)
        selected = candidates[0]
        return selected

    def _video_codec_priority(self, item):
        mime = (item.get('mimeType') or '').lower()
        codecs = (item.get('codecs') or '').lower()
        if 'vp9.2' in mime or 'vp09.02' in codecs:
            return 4
        if 'vp9' in mime or 'vp09' in codecs:
            return 3
        if 'avc' in codecs or 'h264' in codecs:
            return 2
        if 'av01' in codecs:
            return 1
        return 0

    def _is_risky_best_video(self, item):
        codecs = (item.get('codecs') or '').lower()
        return 'av01' in codecs

    def choose_video_tracks(self, formats, quality=None):
        videos = [x for x in formats if x.get('vcodec') != 'none' and x.get('acodec') == 'none']
        cap = 2160 if quality in ('best', '4k') else 1440 if quality == '2k' else 1080
        videos = [x for x in videos if int(x.get('height') or 0) <= cap] or videos
        vp9 = [x for x in videos if self._video_codec_priority(x) >= 3]
        if vp9:
            videos = vp9
        sdr = [x for x in videos if not self._is_hdr_video(x)]
        hdr = [x for x in videos if self._is_hdr_video(x)]
        sort_key = lambda x: (int(x.get('height') or 0), int(x.get('bitrate') or 0))
        sdr.sort(key=sort_key, reverse=True)
        hdr.sort(key=sort_key, reverse=True)
        tracks = []
        if sdr:
            item = sdr[0].copy()
            item['track_name'] = 'SDR'
            item['is_hdr'] = False
            tracks.append(item)
        if hdr:
            item = hdr[0].copy()
            item['track_name'] = 'HDR'
            item['is_hdr'] = True
            tracks.append(item)
        if not tracks:
            item = self.choose_playable(formats, quality)
            if item:
                item = item.copy()
                item['track_name'] = 'HDR' if self._is_hdr_video(item) else 'SDR'
                item['is_hdr'] = self._is_hdr_video(item)
                tracks.append(item)
        return tracks

    def _is_hdr_video(self, item):
        mime = (item.get('mimeType') or '').lower()
        codecs = (item.get('codecs') or '').lower()
        color = item.get('colorInfo') or {}
        return 'vp9.2' in mime or 'vp09.02' in codecs or bool(color.get('hdrMetadataInfo'))

    def choose_audio(self, formats):
        candidates = [x for x in formats if x.get('acodec') != 'none' and x.get('vcodec') == 'none']
        if not candidates:
            return None
        candidates.sort(key=lambda x: (1 if x.get('ext') == 'mp4' else 0, int(x.get('bitrate') or 0)), reverse=True)
        selected = candidates[0]
        return selected

    def _probe_format(self, item):
        try:
            headers = self.headers.copy()
            headers.update(item.get('headers') or {})
            headers['Range'] = 'bytes=0-1'
            r = self.session.get(item.get('url'), headers=headers, stream=True, timeout=10)
            if r.url and r.url != item.get('url'):
                item['url'] = r.url
                item['redirected'] = True
            status_code = r.status_code
            r.close()
            return status_code in (200, 206), status_code
        except Exception:
            return False, None

    def choose_best_video_audio(self, formats):
        videos = [x for x in formats if x.get('vcodec') != 'none' and x.get('acodec') == 'none']
        audios = [x for x in formats if x.get('acodec') != 'none' and x.get('vcodec') == 'none']
        videos.sort(key=lambda x: (int(x.get('height') or 0), int(x.get('bitrate') or 0)), reverse=True)
        audios.sort(key=lambda x: int(x.get('bitrate') or 0), reverse=True)
        return (videos[0] if videos else None), (audios[0] if audios else None)

    def _url_summary(self, media_url):
        parsed = urlparse(media_url or '')
        query = parse_qs(parsed.query)
        keys = ['itag', 'mime', 'c', 'expire', 'ip', 'mip', 'source', 'requiressl', 'gir', 'clen', 'dur', 'n', 'pot', 'sig', 'lsig', 'cms_redirect']
        return {
            'host': parsed.netloc,
            'path': parsed.path,
            'len': len(media_url or ''),
            'params': {k: bool(query.get(k)) if k in ('pot', 'sig', 'lsig', 'cms_redirect') else (query.get(k, [''])[0][:80]) for k in keys if k in query}
        }

    def _get(self, url, **kwargs):
        headers = self.headers.copy()
        headers.update(kwargs.pop('headers', {}) or {})
        r = self.session.get(url, headers=headers, timeout=kwargs.pop('timeout', 15), **kwargs)
        r.raise_for_status()
        return r

    def _post_json(self, url, payload, headers=None):
        h = self.headers.copy()
        h.update({'Content-Type': 'application/json', 'Origin': 'https://www.youtube.com'})
        if headers:
            h.update({k: v for k, v in headers.items() if v})
        r = self.session.post(url, json=payload, headers=h, timeout=15)
        r.raise_for_status()
        return r.json()

    def _call_player_api(self, video_id, api_key, context, referer, visitor_data=None, sts=None):
        clients = [
            {'client': {'clientName': 'ANDROID_VR', 'clientVersion': '1.65.10', 'deviceMake': 'Oculus', 'deviceModel': 'Quest 3', 'androidSdkVersion': 32, 'userAgent': 'com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip', 'osName': 'Android', 'osVersion': '12L', 'hl': 'en', 'gl': 'US'}},
            {'client': {'clientName': 'ANDROID', 'clientVersion': '21.02.35', 'androidSdkVersion': 30, 'userAgent': 'com.google.android.youtube/21.02.35 (Linux; U; Android 11) gzip', 'osName': 'Android', 'osVersion': '11', 'hl': 'en', 'gl': 'US'}},
            {'client': {'clientName': 'IOS', 'clientVersion': '21.02.3', 'deviceMake': 'Apple', 'deviceModel': 'iPhone16,2', 'userAgent': 'com.google.ios.youtube/21.02.3 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)', 'osName': 'iPhone', 'osVersion': '18.3.2.22D82', 'hl': 'en', 'gl': 'US'}},
            context,
            {'client': {'clientName': 'MWEB', 'clientVersion': '2.20260115.01.00', 'userAgent': 'Mozilla/5.0 (iPad; CPU OS 16_7_10 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1,gzip(gfe)', 'hl': 'en', 'gl': 'US'}},
        ]
        results = []
        fallback = None
        for ctx in clients:
            client_name = (ctx.get('client') or {}).get('clientName')
            try:
                url = f'https://www.youtube.com/youtubei/v1/player?key={api_key}&prettyPrint=false'
                payload = {
                    'context': ctx,
                    'videoId': video_id,
                    'playbackContext': {'contentPlaybackContext': {'html5Preference': 'HTML5_PREF_WANTS', **({'signatureTimestamp': sts} if sts else {})}},
                    'contentCheckOk': True,
                    'racyCheckOk': True,
                }
                client = ctx.get('client') or {}
                headers = {
                    'Referer': referer,
                    'X-YouTube-Client-Name': str(self._client_name_id(client.get('clientName'))),
                    'X-YouTube-Client-Version': client.get('clientVersion') or '',
                }
                if visitor_data:
                    headers['X-Goog-Visitor-Id'] = visitor_data
                client_ua = client.get('userAgent')
                if client_ua:
                    headers['User-Agent'] = client_ua
                data = self._post_json(url, payload, headers=headers)
                status = (data.get('playabilityStatus') or {}).get('status')
                streaming = data.get('streamingData') or {}
                formats = streaming.get('formats') or []
                adaptive = streaming.get('adaptiveFormats') or []
                direct_video = [x for x in adaptive if (x.get('url') or x.get('signatureCipher') or x.get('cipher')) and str(x.get('mimeType') or '').startswith('video/')]
                direct_any = [x for x in formats + adaptive if x.get('url') or x.get('signatureCipher') or x.get('cipher')]
                has_streaming = bool(streaming)
                if has_streaming:
                    data['_client_name'] = client_name
                    data['_client_ua'] = client_ua
                    results.append(data)
                    # VR 明文格式最完整，成功后立即返回，避免再串行请求 4 个客户端。
                    if client_name == 'ANDROID_VR' and direct_video:
                        return results
                if has_streaming and fallback is None:
                    fallback = data
                elif fallback is None:
                    fallback = data
            except Exception:
                continue
        return results or ([fallback] if fallback else [])

    def _normalize_format(self, fmt, player_url):
        media_url = fmt.get('url')
        if not media_url:
            cipher = fmt.get('signatureCipher') or fmt.get('cipher')
            if cipher:
                media_url = self._decrypt_signature_cipher(cipher, player_url)
        if not media_url:
            return None
        media_url = self._decrypt_nsig(media_url, player_url)
        client_name = fmt.get('_client_name')
        po_token = self._get_po_token(client_name, 'gvs') if client_name else None
        if po_token:
            sep = '&' if '?' in media_url else '?'
            media_url = f'{media_url}{sep}pot={quote(po_token)}'
        mime = fmt.get('mimeType') or ''
        ext = 'mp4' if 'mp4' in mime else 'webm' if 'webm' in mime else 'unknown'
        codecs = self._search(r'codecs="([^"]+)"', mime) or ''
        has_audio = mime.startswith('audio/') or any(x in codecs for x in ('mp4a', 'opus', 'vorbis'))
        has_video = mime.startswith('video/') or any(x in codecs for x in ('avc', 'vp9', 'av01', 'h264'))
        headers = (fmt.get('http_headers') or {}).copy()
        if fmt.get('_client_ua'):
            headers['User-Agent'] = fmt.get('_client_ua')
        return {
            'itag': fmt.get('itag'),
            'url': media_url,
            'mimeType': mime,
            'client': fmt.get('_client_name'),
            'ext': ext,
            'width': fmt.get('width') or 0,
            'height': fmt.get('height') or 0,
            'fps': fmt.get('fps') or 0,
            'bitrate': fmt.get('bitrate') or fmt.get('averageBitrate') or 0,
            'contentLength': fmt.get('contentLength'),
            'initRange': fmt.get('initRange') or {},
            'indexRange': fmt.get('indexRange') or {},
            'codecs': codecs,
            'quality': fmt.get('qualityLabel') or fmt.get('quality'),
            'colorInfo': fmt.get('colorInfo') or {},
            'vcodec': codecs if has_video else 'none',
            'acodec': codecs if has_audio else 'none',
            'headers': headers,
        }

    def _decrypt_signature_cipher(self, cipher, player_url):
        data = parse_qs(cipher)
        media_url = unquote(data.get('url', [''])[0])
        sig = unquote(data.get('s', [''])[0])
        sp = data.get('sp', ['sig'])[0]
        if not media_url:
            return ''
        if sig:
            decoded = self._decrypt_sig(sig, player_url)
            sep = '&' if '?' in media_url else '?'
            media_url = f'{media_url}{sep}{sp}={quote(decoded)}'
        return media_url

    def _decrypt_sig(self, sig, player_url):
        cache_key = player_url or ''
        if cache_key in self.sig_plan_cache:
            plan = self.sig_plan_cache.get(cache_key)
        else:
            code = self._get_player_code(player_url)
            plan = self._extract_sig_plan(code)
            self.sig_plan_cache[cache_key] = plan
        if not plan:
            return sig
        arr = list(sig)
        for op, arg in plan:
            if op == 'reverse':
                arr.reverse()
            elif op in ('slice', 'splice'):
                arr = arr[int(arg):]
            elif op == 'swap' and arr:
                j = int(arg) % len(arr)
                arr[0], arr[j] = arr[j], arr[0]
        return ''.join(arr)

    def _decrypt_nsig(self, media_url, player_url):
        try:
            parsed = urlparse(media_url)
            query = parse_qs(parsed.query)
            n_value = query.get('n', [None])[0]
            if not n_value:
                return media_url
            path_match = re.search(r'/n/([^/]+)', parsed.path)
            if path_match and path_match.group(1) != n_value:
                new_path = parsed.path.replace(f"/n/{path_match.group(1)}", f"/n/{n_value}", 1)
                fixed = urlunparse(parsed._replace(path=new_path))
                return fixed
            return media_url
        except Exception:
            return media_url

    def _get_player_code(self, player_url):
        if not player_url:
            return ''
        if player_url in self.player_cache:
            return self.player_cache[player_url]
        if player_url.startswith('//'):
            player_url = 'https:' + player_url
        elif player_url.startswith('/'):
            player_url = 'https://www.youtube.com' + player_url
        try:
            code = self._get(player_url).text
        except Exception:
            code = ''
        self.player_cache[player_url] = code
        return code

    def _extract_sig_plan(self, code):
        if not code:
            return None
        name = None
        for pattern in [
            r'\.sig\|\|([a-zA-Z0-9_$]+)\(',
            r'"signature",\s*([a-zA-Z0-9_$]+)\(',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{a=a\.split\(""\);',
        ]:
            m = re.search(pattern, code)
            if m:
                name = m.group(1)
                break
        if not name:
            return None
        body = self._extract_js_function_body(code, name)
        if not body:
            return None
        helper = self._search(r'([a-zA-Z0-9_$]+)\.[a-zA-Z0-9_$]+\(a,\d+\)', body)
        helper_map = self._extract_helper_object(code, helper) if helper else {}
        plan = []
        for part in body.split(';'):
            if 'reverse()' in part:
                plan.append(('reverse', 0))
                continue
            m = re.search(r'\.slice\((\d+)\)', part)
            if m:
                plan.append(('slice', int(m.group(1))))
                continue
            m = re.search(r'\.splice\(0,(\d+)\)', part)
            if m:
                plan.append(('splice', int(m.group(1))))
                continue
            m = re.search(r'([a-zA-Z0-9_$]+)\.([a-zA-Z0-9_$]+)\(a,(\d+)\)', part)
            if m and m.group(1) == helper:
                op = helper_map.get(m.group(2))
                if op:
                    plan.append((op, int(m.group(3))))
        return plan or None

    def _extract_helper_object(self, code, name):
        if not name:
            return {}
        m = re.search(r'var\s+' + re.escape(name) + r'=\{(.+?)\};', code, re.S) or re.search(re.escape(name) + r'=\{(.+?)\};', code, re.S)
        if not m:
            return {}
        result = {}
        for method, body in re.findall(r'([a-zA-Z0-9_$]+):function\([a-z,]+\)\{(.*?)\}', m.group(1)):
            if '.reverse(' in body:
                result[method] = 'reverse'
            elif '.splice(' in body:
                result[method] = 'splice'
            elif '.slice(' in body:
                result[method] = 'slice'
            elif 'a[0]' in body and 'length' in body:
                result[method] = 'swap'
        return result

    def _extract_n_function(self, code):
        if not code:
            return None
        name = None
        for pattern in [
            r'\.get\("n"\)\)&&\(b=([a-zA-Z0-9_$]+)(?:\[(\d+)\])?\(b\)',
            r'\.get\("n"\)\)&&\(b=([a-zA-Z0-9_$]+)\(b\)',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{var b=a\.split\(""\)',
            r'function\s+([a-zA-Z0-9_$]+)\(a\)\{var b=a\.split\(""\)',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{a=a\.split\(""\)',
        ]:
            m = re.search(pattern, code)
            if m:
                name = m.group(1)
                break
        if not name:
            return None
        body = self._extract_js_function_body(code, name)
        if not body:
            return None

        def transform(value):
            arr = list(value)
            for part in body.split(';'):
                if 'reverse()' in part:
                    arr.reverse()
                m = re.search(r'\.slice\((\d+)\)', part)
                if m:
                    arr = arr[int(m.group(1)):]
                m = re.search(r'\.splice\(0,(\d+)\)', part)
                if m:
                    arr = arr[int(m.group(1)):]
            return ''.join(arr) or value
        return transform

    def _extract_js_function_body(self, code, name):
        starts = []
        for pattern in [
            r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{',
            re.escape(name) + r'\s*=\s*function\s*\([^)]*\)\s*\{',
            r'var\s+' + re.escape(name) + r'\s*=\s*function\s*\([^)]*\)\s*\{',
        ]:
            m = re.search(pattern, code)
            if m:
                starts.append(m.end() - 1)
        if not starts:
            return ''
        start = starts[0]
        depth = 0
        in_str = None
        escape = False
        for i in range(start, len(code)):
            ch = code[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if in_str:
                if ch == in_str:
                    in_str = None
                continue
            if ch in ('"', "'", '`'):
                in_str = ch
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return code[start + 1:i]
        return ''

    def _extract_ytcfg(self, text):
        m = re.search(r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;', text, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except Exception:
            return None

    def _extract_initial_player_response(self, text):
        return self._extract_json_after(text, 'ytInitialPlayerResponse')

    def _extract_json_after(self, text, marker):
        pos = text.find(marker)
        if pos < 0:
            return None
        start = text.find('{', pos)
        if start < 0:
            return None
        depth = 0
        in_str = None
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if in_str:
                if ch == in_str:
                    in_str = None
                continue
            if ch == '"':
                in_str = ch
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        return None
        return None

    def _extract_player_url(self, text):
        for pattern in [
            r'"jsUrl":"([^"]+)"',
            r'"PLAYER_JS_URL":"([^"]+)"',
            r'(/s/player/[^"\\]+/base\.js)',
        ]:
            m = re.search(pattern, text)
            if m:
                return m.group(1).replace('\\/', '/')
        return ''

    @staticmethod
    def _search(pattern, text, default=None):
        m = re.search(pattern, text or '', re.S)
        return m.group(1) if m else default


class Spider(BaseSpider):

    # ---------- 站点信息（换站只改这两处 + self.classes） ----------
    HOST = "https://kaixinduanju.com"
    IMG_TPL = "https://img.kaixinduanju.com/vi/{vid}/mqdefault.jpg"

    def __init__(self):
        self.host = self.HOST
        self.ua = ("Mozilla/5.0 (Linux; Android 14; 22127RK46C) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Mobile Safari/537.36")
        self.headers = {
            "User-Agent": self.ua,
            "Accept": ("text/html,application/xhtml+xml,application/xml;"
                       "q=0.9,image/webp,*/*;q=0.8"),
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Referer": self.host + "/",
        }
        # 分类 = 热门 tag（type_id 为原始 tag 名，请求时 URL 编码）
        self.classes = [
            {"type_id": "短剧", "type_name": "短剧"},
            {"type_id": "热门短剧", "type_name": "热门短剧"},
            {"type_id": "都市", "type_name": "都市"},
            {"type_id": "霸总", "type_name": "霸总"},
            {"type_id": "逆袭", "type_name": "逆袭"},
            {"type_id": "重生", "type_name": "重生"},
            {"type_id": "穿越", "type_name": "穿越"},
            {"type_id": "古装", "type_name": "古装"},
            {"type_id": "仙侠", "type_name": "仙侠"},
            {"type_id": "修仙", "type_name": "修仙"},
            {"type_id": "玄幻", "type_name": "玄幻"},
            {"type_id": "战神", "type_name": "战神"},
            {"type_id": "神医", "type_name": "神医"},
            {"type_id": "富豪", "type_name": "富豪"},
            {"type_id": "甜宠", "type_name": "甜宠"},
            {"type_id": "热血", "type_name": "热血"},
            {"type_id": "爱情", "type_name": "爱情"},
            {"type_id": "复仇", "type_name": "复仇"},
        ]
        self.filters = {}
        # YouTube 提取相关（懒初始化，见 _ensure_yt）
        self.extendDict = {}
        self.session = None
        self.yt = None
        self.header = None
        self.proxy_str = None

    # ---------- 基础 12 方法 ----------
    def getName(self):
        return "开心短剧"

    def getDependence(self):
        return []

    def init(self, extend=""):
        try:
            self.extendDict = json.loads(extend) if extend else {}
        except Exception:
            self.extendDict = {}
        self._ensure_yt()
        return

    def destroy(self):
        return

    def isVideoFormat(self, url):
        if not url:
            return False
        return bool(re.search(r"\.(m3u8|mp4|flv|ts|mkv|avi|mov|m4v)(\?|$)",
                              url, re.I))

    def manualVideoCheck(self):
        return False

    # ---------- YouTube 提取器懒初始化 ----------
    def _ensure_yt(self):
        if self.yt is not None:
            return
        if not isinstance(getattr(self, "extendDict", None), dict):
            self.extendDict = {}
        if requests is None:
            return
        self.session = requests.Session()
        # YouTube 直链请求用桌面 Chrome UA + youtube Referer
        self.header = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.youtube.com/",
        }
        self.proxy_str = None
        proxy_val = self.extendDict.get("proxy")
        if proxy_val:
            if isinstance(proxy_val, dict):
                self.session.proxies = proxy_val
                self.proxy_str = (proxy_val.get("http") or
                                  proxy_val.get("https") or "").replace(
                    "http://", "").replace("https://", "")
            elif isinstance(proxy_val, str):
                self.proxy_str = proxy_val.replace("http://", "").replace(
                    "https://", "")
                purl = "http://%s" % self.proxy_str
                self.session.proxies = {"http": purl, "https": purl}
        self.session.headers.update(self.header)
        self.yt = YouTubeLite(self.session, self.header, self.extendDict)

    # ---------- 工具函数 ----------
    @staticmethod
    def _clean(s):
        if not s:
            return ""
        s = _html.unescape(s)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    def _fetch(self, url):
        """GET 文本，requests 优先，被挡退 urllib。返回字符串。"""
        try:
            r = self.fetch(url, headers=self.headers)
            if r is None:
                return ""
            txt = getattr(r, "text", None)
            if txt is None:
                return ""
            sc = getattr(r, "status_code", 200)
            if sc and sc >= 400:
                return ""
            return txt
        except Exception:
            return ""

    # 卡片解析：捕获 slug / 标题 / videoId，并向后补时长
    _CARD_RE = re.compile(
        r'href="(/play/[^"]+)"\s+title="([^"]*)"\s*>\s*'
        r'<img[^>]*?src="https://img\.kaixinduanju\.com/vi/([^/"]+)/[^"]*"',
        re.S,
    )
    _DUR_RE = re.compile(
        r'bottom-2\s+right-2[^>]*rounded"[^>]*>\s*([^<]+?)\s*</span>', re.S
    )

    def _parse_cards(self, htm):
        out = []
        seen = set()
        if not htm:
            return out
        for m in self._CARD_RE.finditer(htm):
            slug = m.group(1)
            title = self._clean(m.group(2))
            vid = m.group(3)
            if not slug or not vid:
                continue
            vod_id = slug[len("/play/"):]
            if not vod_id or vod_id in seen:
                continue
            seen.add(vod_id)
            tail = htm[m.end():m.end() + 800]
            dm = self._DUR_RE.search(tail)
            remark = self._clean(dm.group(1)) if dm else ""
            out.append({
                "vod_id": vod_id,
                "vod_name": title or vod_id,
                "vod_pic": self.IMG_TPL.format(vid=vid),
                "vod_remark": remark,
            })
        return out

    # ---------- 首页 ----------
    def homeContent(self, filter):
        return {"class": self.classes, "filters": self.filters}

    def getHomeContent(self, filter):
        return self.homeContent(filter)

    def homeVideoContent(self):
        htm = self._fetch(self.host + "/")
        return {"list": self._parse_cards(htm)[:24]}

    def getHomeVideoContent(self):
        return self.homeVideoContent()

    # ---------- 分类（走 tag，全站 tag 不分页 → pagecount=1） ----------
    def _parse_extend(self, extend):
        if not extend:
            return {}
        if isinstance(extend, dict):
            return extend
        s = str(extend).strip()
        if not s:
            return {}
        try:
            return json.loads(s)
        except Exception:
            pass
        res = {}
        for part in re.split(r"[&,]", s):
            if "=" in part:
                k, v = part.split("=", 1)
                res[k.strip()] = v.strip()
        return res

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1

        ext = self._parse_extend(extend)
        tag = ext.get("class") or ext.get("tag") or tid or ""
        tag = str(tag).strip()

        if page > 1 or not tag:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": 24, "total": 0}

        url = "%s/tag/%s?page=%d" % (self.host, quote(tag, safe=""), page)
        htm = self._fetch(url)
        lst = self._parse_cards(htm)
        return {
            "list": lst,
            "page": page,
            "pagecount": 1,
            "limit": len(lst) if lst else 24,
            "total": len(lst),
        }

    def getCategoryContent(self, tid, pg, filter, extend):
        return self.categoryContent(tid, pg, filter, extend)

    # ---------- 详情 ----------
    @staticmethod
    def _norm_ids(ids):
        if ids is None:
            return ""
        if isinstance(ids, (list, tuple)):
            if not ids:
                return ""
            ids = ids[0]
        return str(ids).strip()

    def detailContent(self, ids):
        vid_slug = self._norm_ids(ids)
        if not vid_slug:
            return {"list": []}

        url = "%s/play/%s" % (self.host, quote(vid_slug, safe="/-_"))
        htm = self._fetch(url)

        title = ""
        video_id = ""
        desc = ""
        remark = ""
        genres = []

        is_shell = False
        if htm:
            m = re.search(r"youtube\.com/embed/([A-Za-z0-9_\-]+)", htm)
            if m:
                video_id = m.group(1)
            else:
                is_shell = True

            m = re.search(r"<title>(.*?)(?:free online watch| - https|</title>)",
                          htm, re.S)
            if m:
                title = self._clean(m.group(1))
                if title.startswith(("首頁", "首页")):
                    is_shell = True
                    title = ""
                else:
                    title = re.sub(r"[短短][剧劇].{0,4}[綫线線]?上?看\s*$", "", title)
                    title = re.sub(r"(免[費费].{0,4}[綫线線]?上?看)\s*$", "", title)
                    title = title.strip()

            if not is_shell:
                m = re.search(
                    r'<meta[^>]+name="description"[^>]+content="([^"]*)"',
                    htm, re.S)
                if m:
                    d = self._clean(m.group(1))
                    if "專注於" in d or "专注于" in d or "每日更新的短劇" in d \
                            or "每日更新的短剧" in d:
                        d = ""
                    else:
                        d = re.sub(
                            r"^.*?(?:[劇剧]情[簡简]介|introduce)\s*[:：]\s*",
                            "", d, flags=re.I)
                    desc = d
                m = self._DUR_RE.search(htm) or re.search(
                    r'py-1 rounded[^>]*>\s*([0-9:]{4,8})\s*<', htm)
                if m:
                    remark = self._clean(m.group(1))
                for gm in re.finditer(
                        r'href="/tag/[^"]+"[^>]*>#?([^<]+)</a>', htm):
                    g = self._clean(gm.group(1))
                    if g and g not in genres:
                        genres.append(g)

        if not title:
            title = vid_slug.replace("-", " ")
        pic = self.IMG_TPL.format(vid=video_id) if video_id else ""

        # 单集：名称$播放ID。播放ID 用 videoId（不含 $）。
        play_id = video_id if video_id else vid_slug
        vod = {
            "vod_id": vid_slug,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remark": remark,
            "vod_content": desc or title,
            "type_name": " ".join(genres[:6]),
            "vod_play_from": "YouTube",
            "vod_play_url": "正片$" + play_id,
        }
        return {"list": [vod]}

    def getDetailContent(self, ids):
        return self.detailContent(ids)

    # ---------- 播放 ----------
    def _resolve_video_id(self, pid):
        """pid 可能是 videoId 或 /play/ slug；解析出真实 YouTube videoId。"""
        pid = self._norm_ids(pid)
        if not pid:
            return ""
        # 兼容盒子把 "名称$播放ID" 整串传入的情况，取 $ 后段
        if "$" in pid:
            pid = pid.split("$")[-1].strip()
        if not pid:
            return ""
        # 形如 11 位标准 id 或 8~20 位安全字符，视为 videoId
        if re.fullmatch(r"[A-Za-z0-9_\-]{8,20}", pid):
            return pid
        htm = self._fetch("%s/play/%s" % (self.host, quote(pid, safe="/-_")))
        m = re.search(r"youtube\.com/embed/([A-Za-z0-9_\-]+)", htm or "")
        return m.group(1) if m else pid

    def playerContent(self, flag, id, vipFlags):
        self._ensure_yt()
        video_id = self._resolve_video_id(id)
        embed = "https://www.youtube.com/embed/%s?autoplay=1" % video_id

        # 无提取器（requests 不可用）→ 直接回退 embed
        if not video_id or self.yt is None:
            return {"parse": 1, "url": embed,
                    "header": {"User-Agent": self.ua}}

        quality = "best"
        try:
            data = self.yt.extract(video_id)
            video_tracks = self.yt.choose_video_tracks(
                data.get("formats") or [], "best")
            if not video_tracks:
                raise Exception("no video track")
            audio = self.yt.choose_audio(data.get("formats") or [])
            if audio:
                cache_key = "yt_%s_%s" % (video_id, quality)
                self.setCache(cache_key, {
                    "video_tracks": video_tracks,
                    "video_url": video_tracks[0]["url"],
                    "audio_url": audio["url"],
                    "video_item": video_tracks[0],
                    "audio_item": audio,
                    "duration": data.get("duration") or 0,
                    "expires": time.time() + 300,
                })
                mpd = ("http://127.0.0.1:9978/proxy?do=py&type=mpd"
                       "&vid=%s&quality=%s" % (video_id, quality))
                return {"parse": 0, "jx": 0, "url": mpd,
                        "format": "application/dash+xml"}
            # 无独立音轨：退化为单一视频直链
            playable = video_tracks[0]
            headers = (self.header or {"User-Agent": self.ua}).copy()
            headers.update(playable.get("headers") or {})
            return {"parse": 0, "jx": 0, "url": playable["url"],
                    "header": headers}
        except Exception as e:
            try:
                self.log("[kaixin] YouTube 提取失败: %s" % e)
            except Exception:
                pass
            res = {"parse": 1, "url": embed,
                   "header": {"User-Agent": self.ua}}
            if self.proxy_str:
                res["proxy"] = self.proxy_str
            return res

    def getPlayerContent(self, flag, id, vipFlags):
        return self.playerContent(flag, id, vipFlags)

    # ---------- 本地代理（DASH MPD + 分轨媒体） ----------
    def localProxy(self, param):
        param = param or {}
        if param.get("do") != "py":
            return [404, "text/plain", {}]
        t = param.get("type")
        if t == "mpd":
            return self._proxy_mpd(param)
        if t == "media":
            return self._proxy_media(param)
        if t == "single":
            return self._proxy_single(param)
        return [404, "text/plain", {}]

    def _proxy_mpd(self, params):
        self._ensure_yt()
        vid = params.get("vid")
        quality = params.get("quality") or "best"
        data = self.getCache("yt_%s_%s" % (vid, quality)) if vid else None
        if not data:
            return [404, "text/plain", "视频缓存已过期或不存在"]
        audio_url = data.get("audio_url")
        duration = data.get("duration") or 0
        video_tracks = data.get("video_tracks") or [data.get("video_item") or {}]
        audio_item = data.get("audio_item") or {}
        media_base = ("http://127.0.0.1:9978/proxy?do=py&type=media"
                      "&vid=%s&quality=%s" % (vid, quality))
        seg = str((self.extendDict or {}).get("seg") or "proxy").lower()
        direct_segments = seg == "direct"
        duration_pt = "PT%dS" % int(duration or 0)
        mpd = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" '
               'mediaPresentationDuration="%s" minBufferTime="PT1.5S" '
               'profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">\n'
               '  <Period id="1" start="PT0S">\n' % duration_pt)
        for item in video_tracks:
            init_range = item.get("initRange") or {}
            index_range = item.get("indexRange") or {}
            if direct_segments:
                base_url = item.get("url")
            else:
                base_url = media_base + "&track=video&itag=%s" % item.get("itag")
            mpd += (
                '    <AdaptationSet mimeType="%s" startWithSAP="1" '
                'segmentAlignment="true" scanType="progressive">\n'
                '      <Representation id="v%s" bandwidth="%s" codecs="%s" '
                'height="%s" width="%s">\n'
                '        <BaseURL>%s</BaseURL>\n'
                '        <SegmentBase indexRange="%s-%s">'
                '<Initialization range="%s-%s"/></SegmentBase>\n'
                '      </Representation>\n'
                '    </AdaptationSet>\n' % (
                    html.escape((item.get("mimeType") or "video/webm").split(";")[0]),
                    item.get("itag", 1),
                    item.get("bitrate", 1000000),
                    html.escape(item.get("codecs") or ""),
                    item.get("height", 0),
                    item.get("width", 0),
                    html.escape(base_url or ""),
                    index_range.get("start", "0"), index_range.get("end", "0"),
                    init_range.get("start", "0"), init_range.get("end", "0"),
                ))
        if audio_url:
            audio_init = audio_item.get("initRange") or {}
            audio_index = audio_item.get("indexRange") or {}
            audio_base = audio_url if direct_segments else media_base + "&track=audio"
            mpd += (
                '    <AdaptationSet mimeType="%s" startWithSAP="1" '
                'segmentAlignment="true" lang="und">\n'
                '      <Representation id="audio" bandwidth="%s" codecs="%s" '
                'audioSamplingRate="44100">\n'
                '        <BaseURL>%s</BaseURL>\n'
                '        <SegmentBase indexRange="%s-%s">'
                '<Initialization range="%s-%s"/></SegmentBase>\n'
                '      </Representation>\n'
                '    </AdaptationSet>\n' % (
                    html.escape((audio_item.get("mimeType") or "audio/mp4").split(";")[0]),
                    audio_item.get("bitrate", 128000),
                    html.escape(audio_item.get("codecs") or ""),
                    html.escape(audio_base or ""),
                    audio_index.get("start", "0"), audio_index.get("end", "0"),
                    audio_init.get("start", "0"), audio_init.get("end", "0"),
                ))
        mpd += "  </Period>\n</MPD>"
        return [200, "application/dash+xml", mpd]

    def _proxy_media(self, params):
        self._ensure_yt()
        vid = params.get("vid")
        quality = params.get("quality") or "best"
        track = params.get("track")
        data = self.getCache("yt_%s_%s" % (vid, quality)) if vid else None
        if not data or track not in ("video", "audio"):
            return [404, "text/plain", "媒体不存在"]
        if track == "video":
            wanted_itag = str(params.get("itag") or "")
            tracks = data.get("video_tracks") or [data.get("video_item") or {}]
            media_item = next(
                (x for x in tracks if str(x.get("itag")) == wanted_itag),
                tracks[0] if tracks else {})
            target_url = media_item.get("url")
        else:
            media_item = data.get("audio_item") or {}
            target_url = data.get("audio_url") or media_item.get("url")
        if not target_url:
            return [404, "text/plain", "%s 流不存在" % track]
        headers = (self.header or {"User-Agent": self.ua}).copy()
        headers.update((media_item or {}).get("headers") or {})
        range_header = params.get("range") or params.get("Range")
        if range_header:
            headers["Range"] = range_header
        try:
            r = self.session.get(target_url, headers=headers, stream=True,
                                 timeout=30)
            content_type = r.headers.get("content-type",
                                         "application/octet-stream")
            resp_headers = {"Content-Type": content_type,
                            "Accept-Ranges": "bytes",
                            "Cache-Control": "no-cache"}
            if r.headers.get("content-range"):
                resp_headers["Content-Range"] = r.headers.get("content-range")
            if r.headers.get("content-length"):
                resp_headers["Content-Length"] = r.headers.get("content-length")
            return [r.status_code, content_type, r.content, resp_headers]
        except Exception as e:
            return [500, "text/plain", "代理媒体失败: %s" % str(e)]

    def _proxy_single(self, params):
        self._ensure_yt()
        vid = params.get("vid")
        data = self.getCache("yt_single_%s" % vid) if vid else None
        if not data:
            return [404, "text/plain", "播放缓存已过期或不存在"]
        target_url = data.get("url")
        if not target_url:
            return [404, "text/plain", "播放地址不存在"]
        headers = (data.get("headers") or self.header
                   or {"User-Agent": self.ua}).copy()
        range_header = params.get("range") or params.get("Range")
        if range_header:
            headers["Range"] = range_header
        try:
            r = self.session.get(target_url, headers=headers, stream=True,
                                 timeout=30)
            content_type = r.headers.get("content-type", "video/mp4")
            resp_headers = {"Content-Type": content_type,
                            "Accept-Ranges": "bytes",
                            "Cache-Control": "no-cache"}
            if r.headers.get("content-range"):
                resp_headers["Content-Range"] = r.headers.get("content-range")
            if r.headers.get("content-length"):
                resp_headers["Content-Length"] = r.headers.get("content-length")
            return [r.status_code, content_type, r.content, resp_headers]
        except Exception as e:
            return [500, "text/plain", "代理播放失败: %s" % str(e)]

    # ---------- 搜索（分页有效） ----------
    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1
        kw = (key or "").strip()
        if not kw:
            return {"list": [], "page": page}

        url = "%s/search?keyword=%s&page=%d" % (
            self.host, quote(kw, safe=""), page)
        htm = self._fetch(url)
        lst = self._parse_cards(htm)
        pagecount = page + 1 if lst else page
        return {"list": lst, "page": page, "pagecount": pagecount,
                "limit": len(lst) if lst else 24, "total": 9999}

    def getSearchContent(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

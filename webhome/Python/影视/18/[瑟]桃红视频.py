# -*- coding: utf-8 -*-
"""
3xlg40o Python Spider - 修复版 (封面+播放+线路)
适配 FongMi/TV (T3) 和 WebHomeTV/PeekPro (T4)

修复内容：
1. 封面：AES-256-CBC 解密（32字节key，IV=文件前16字节）
2. 播放：所有线路统一用 cdnId=3（从不返回 Brotli），彻底消除压缩问题
3. 线路切换：用正则替换 cdnId，更健壮
4. 列表页封面：走代理解密
5. m3u8 key URI：根相对路径转绝对路径
6. 代理请求加 Accept-Encoding: gzip, deflate（优先 gzip，排除 br）
"""
import sys
import re
import json
import base64
import ssl
import gzip
import urllib.request
from urllib.parse import urljoin, quote, unquote, urlparse

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq
    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):
    API_HOST = "https://215.x89cneo.com:51111"

    # 封面图片 AES-256-CBC 解密密钥 (来自 encryptedImageCore-BYbwSfDp.js)
    _IMG_KEY = b"H0Z%7n#k$H8*M7xSE^N@8xXZPG*RZ&wY"

    CATEGORIES = [
        {"type_id": "label_266", "type_name": "传媒"},
        {"type_id": "label_262", "type_name": "国产"},
        {"type_id": "label_263", "type_name": "日本AV"},
        {"type_id": "label_264", "type_name": "欧美"},
        {"type_id": "label_267", "type_name": "动漫"},
        {"type_id": "label_341", "type_name": "三级"},
        {"type_id": "label_342", "type_name": "AI换脸"},
        {"type_id": "label_343", "type_name": "AV无码"},
        {"type_id": "cate_130", "type_name": "黑料"},
        {"type_id": "cate_143", "type_name": "探花"},
        {"type_id": "cate_127", "type_name": "SM"},
        {"type_id": "cate_144", "type_name": "乱伦"},
        {"type_id": "cate_178", "type_name": "颜值"},
        {"type_id": "cate_153", "type_name": "人妻少妇"},
        {"type_id": "cate_133", "type_name": "自拍"},
        {"type_id": "cate_146", "type_name": "中文字幕"},
        {"type_id": "cate_246", "type_name": "多男一女"},
        {"type_id": "cate_247", "type_name": "多女一男"},
        {"type_id": "cate_142", "type_name": "主播大秀"},
    ]

    # 1x1 透明 GIF（封面解密失败时兜底）
    _TRANSPARENT_GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"

    def getName(self):
        return "Uu视频"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.header = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
            'Referer': 'https://3.3xlg40o.com/',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    # ========== 工具方法 ==========

    def _get_proxy_url(self, params):
        """构造 localProxy URL，返回空字符串表示不支持代理"""
        if not hasattr(self, "getProxyUrl"):
            return ""
        try:
            base = self.getProxyUrl()
            qs = "&".join([f"{k}={quote(str(v), safe='')}" for k, v in params.items()])
            # 自动处理 base 是否已含 query string
            sep = "&" if "?" in base else "?"
            return base + sep + qs
        except Exception:
            return ""

    def _pic_proxy_url(self, raw_url):
        """如果封面是 .enc 加密图，返回代理解密 URL；否则返回原图"""
        if not raw_url:
            return raw_url
        if not raw_url.endswith(".enc"):
            return raw_url
        proxy = self._get_proxy_url({"type": "pic", "url": raw_url})
        return proxy if proxy else raw_url

    # ========== API 核心 ==========
    def _api(self, path, params=None):
        try:
            url = self.API_HOST + path
            if params:
                qs = "&".join([f"{k}={v}" for k, v in params.items() if v is not None])
                url += "?" + qs
            req = urllib.request.Request(url, headers=self.header)
            resp = urllib.request.urlopen(req, context=self._ssl_ctx, timeout=15)
            resp_data = json.loads(resp.read().decode('utf-8'))
            if resp_data.get("code") != 200:
                return None
            return self._decrypt(resp_data["data"], resp_data["key"])
        except Exception:
            return None

    def _decrypt(self, enc_data, key):
        s = enc_data.replace('\r', '').replace('\n', '').replace(' ', '')
        s = s.replace('-', '+').replace('_', '/')
        pad = (4 - len(s) % 4) % 4
        s += '=' * pad
        raw = base64.b64decode(s)
        key_bytes = key.encode('utf-8')
        result = bytearray()
        for i, b in enumerate(raw):
            result.append(b ^ key_bytes[i % len(key_bytes)])
        return json.loads(result.decode('utf-8', errors='replace'))

    def _build_vod(self, item):
        vid = str(item.get("id", ""))
        pic = item.get("upload_thumb", "") or item.get("thumb", "")
        # 列表页：.enc 封面走代理解密
        pic = self._pic_proxy_url(pic)
        return {
            "vod_id": vid,
            "vod_name": item.get("title", ""),
            "vod_pic": pic,
            "vod_remarks": item.get("label", ""),
        }

    # ========== 首页 ==========
    def homeContent(self, filter):
        return {"class": self.CATEGORIES}

    def homeVideoContent(self):
        data = self._api("/api/old_v3/video/home")
        if not data:
            return {"list": []}
        videos = []
        seen = set()
        for section in data:
            for item in section.get("list", []):
                vid = str(item.get("id", ""))
                if vid and vid not in seen:
                    seen.add(vid)
                    videos.append(self._build_vod(item))
        return {"list": videos[:72]}

    # ========== 分类 ==========
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        parts = tid.split("_", 1)
        if len(parts) != 2:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20}
        ctype, cid = parts[0], parts[1]

        data = self._api("/api/old_v3/video/getList", {
            "type": ctype, "id": cid,
            "page": page, "page_size": 20
        })
        if not data:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20}
        videos = [self._build_vod(it) for it in data.get("list", []) if it.get("id")]
        total = data.get("total", 0) or len(videos) * 10
        pagecount = max(1, (int(total) + 19) // 20) if isinstance(total, (int, str)) else 1
        return {"list": videos, "page": page, "pagecount": pagecount, "limit": 20, "total": int(total) if isinstance(total, (int, str)) else 0}

    # ========== 详情 ==========
    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = ids[0]

        data = self._api("/api/v3/home/public/video/long/detail", {"id": vod_id})
        if not data:
            return {"list": []}

        item = data.get("data") or (data[0] if isinstance(data, list) else data)
        if not item or not item.get("id"):
            return {"list": []}

        # 封面：.enc 走代理解密
        pic_raw = item.get("upload_thumb", "") or item.get("thumb", "")
        pic_url = self._pic_proxy_url(pic_raw)

        # 播放地址
        play_hls = item.get("play_hls_url", "")
        cdn_list = item.get("cdn_list", [])

        # 构造多线路播放列表
        play_from = []
        play_url_parts = []

        if play_hls:
            # 默认线路
            play_from.append("默认线路")
            play_url_parts.append("播放$" + play_hls)

            # 其他线路：用正则替换 cdnId
            for cdn in cdn_list[1:]:
                cdn_id = cdn.get("id")
                cdn_title = cdn.get("title", "线路" + str(cdn_id))
                if cdn_id is not None:
                    cdn_hls = re.sub(r'cdnId=\d+', f'cdnId={cdn_id}', play_hls)
                    play_from.append(cdn_title)
                    play_url_parts.append("播放$" + cdn_hls)

        # play_hls 为空时用 href 兜底
        if not play_hls:
            href = item.get("href", "")
            if href and not href.startswith("http"):
                href = "https://kbu.xn--xhq15jk0k96h.cn/encryption-ts" + href
            if href:
                play_from.append("默认线路")
                play_url_parts.append("播放$" + href)

        vod = {
            "vod_id": str(item.get("id", vod_id)),
            "vod_name": item.get("title", "未知影片"),
            "vod_pic": pic_url,
            "type_name": item.get("label", ""),
            "vod_year": item.get("years", ""),
            "vod_area": item.get("region", ""),
            "vod_remarks": item.get("classify", ""),
            "vod_actor": item.get("actor", ""),
            "vod_director": "",
            "vod_content": (item.get("desc", "") or item.get("classify", ""))[:500],
            "vod_play_from": "$$$".join(play_from) if play_from else "默认线路",
            "vod_play_url": "$$$".join(play_url_parts) if play_url_parts else "",
        }
        return {"list": [vod]}

    # ========== 搜索 ==========
    def searchContent(self, key, quick, pg="1"):
        data = self._api("/api/old_v3/video/search", {"keywords": key, "page": int(pg), "page_size": 20})
        if not data:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20}
        videos = [self._build_vod(it) for it in data.get("list", []) if it.get("id")]
        total = data.get("total", 0)
        pagecount = max(1, (int(total) + 19) // 20) if isinstance(total, (int, str)) else 1
        return {"list": videos, "page": int(pg), "pagecount": pagecount, "limit": 20, "total": int(total) if isinstance(total, (int, str)) else 0}

    # ========== 播放 ==========
    def playerContent(self, flag, id, vipFlags):
        # id 是 m3u8 URL
        # 服务器对不同 cdnId 间歇性返回 Brotli 压缩，播放器不支持
        # cdnId=1 和 cdnId=3 返回完全相同的 m3u8 内容（相同 ts URL、相同 key）
        # 但 cdnId=3 从不返回 Brotli（始终明文或 gzip），cdnId=1/2 会间歇性返回 Brotli
        # 因此所有线路统一替换为 cdnId=3，彻底消除 Brotli 问题
        stable_url = re.sub(r'cdnId=\d+', 'cdnId=3', id) if 'cdnId=' in id else id

        # 走 localProxy 代理：解压 gzip + 修复 key URI（根相对→绝对）
        proxy_url = self._get_proxy_url({"type": "m3u8", "hls_url": stable_url})

        if proxy_url:
            play_url = proxy_url
        else:
            # localProxy 不可用时直接用 cdnId=3（播放器支持 gzip）
            play_url = stable_url

        return {
            "parse": 0,
            "playUrl": "",
            "url": play_url,
            "header": {
                "User-Agent": self.header["User-Agent"],
                "Referer": "https://3.3xlg40o.com/",
            },
        }

    # ========== 本地代理 ==========
    def localProxy(self, param):
        ptype = param.get("type", "")

        # 图片代理解密
        if ptype == "pic":
            return self._proxy_pic(param)

        # m3u8 代理（解压 + 修复 key URI）
        if ptype == "m3u8":
            return self._proxy_m3u8(param)

        # ts 分片代理
        raw_url = param.get("url") or param.get("u") or ""
        if raw_url and (".ts" in raw_url or ".mp4" in raw_url):
            return self._proxy_media(raw_url)

        return [200, "video/MP2T", b""]

    def _proxy_pic(self, param):
        """代理并解密 .enc 封面图

        加密方式：AES-256-CBC
        Key: _IMG_KEY (32字节)
        IV: 文件前16字节
        密文: 文件剩余部分
        """
        raw_url = param.get("url", "")
        # 兼容壳子传递 URL 编码参数的情况
        if raw_url and '%' in raw_url:
            raw_url = unquote(raw_url)

        if not raw_url:
            return [200, "image/gif", self._TRANSPARENT_GIF]

        # 下载原图
        try:
            req = urllib.request.Request(raw_url, headers={"User-Agent": self.header["User-Agent"]})
            resp = urllib.request.urlopen(req, context=self._ssl_ctx, timeout=15)
            data = resp.read()
        except Exception:
            return [200, "image/gif", self._TRANSPARENT_GIF]

        # 非 .enc 直接透传
        if not raw_url.endswith(".enc"):
            ct = resp.headers.get("content-type") or "image/jpeg"
            return [200, ct, data]

        # === 主要解密方式：AES-256-CBC ===
        try:
            from Crypto.Cipher import AES

            if len(data) >= 32 and len(data) % 16 == 0:
                iv = data[:16]
                enc = data[16:]
                cipher = AES.new(self._IMG_KEY, AES.MODE_CBC, iv)
                dec = cipher.decrypt(enc)
                # PKCS7 unpad
                pad = dec[-1]
                if 1 <= pad <= 16:
                    dec = dec[:-pad]
                # 验证图片头
                if dec[:2] == b'\xff\xd8':
                    return [200, "image/jpeg", dec]
                if dec[:4] == b'\x89PNG':
                    return [200, "image/png", dec]
        except Exception:
            pass

        # === 兜底：尝试其他 AES 方式（以防 key 变更） ===
        try:
            from Crypto.Cipher import AES
            import hashlib

            keys_to_try = []
            # 从 URL 文件名提取 UUID 做 MD5
            try:
                fname = raw_url.split("/")[-1].replace(".jpg.enc", "").replace(".png.enc", "")
                if "-" in fname:
                    keys_to_try.append(hashlib.md5(fname.encode()).digest())
            except Exception:
                pass

            # 常见固定 key
            for seed in [b"3xlg40o", b"uuvideo", b"encryption"]:
                keys_to_try.append(hashlib.md5(seed).digest())

            for k in keys_to_try:
                # ECB
                try:
                    cipher = AES.new(k, AES.MODE_ECB)
                    dec = cipher.decrypt(data)
                    if dec[:2] == b'\xff\xd8' or dec[:4] == b'\x89PNG':
                        return [200, "image/jpeg" if dec[:2] == b'\xff\xd8' else "image/png", dec]
                except Exception:
                    pass
                # CBC (IV=0)
                try:
                    cipher = AES.new(k, AES.MODE_CBC, b"\x00" * 16)
                    dec = cipher.decrypt(data)
                    pad = dec[-1]
                    if 0 < pad <= 16:
                        dec = dec[:-pad]
                    if dec[:2] == b'\xff\xd8' or dec[:4] == b'\x89PNG':
                        return [200, "image/jpeg" if dec[:2] == b'\xff\xd8' else "image/png", dec]
                except Exception:
                    pass
        except Exception:
            pass

        # 全部失败，返回透明图兜底
        return [200, "image/gif", self._TRANSPARENT_GIF]

    def _decompress_m3u8(self, data, ce):
        """尝试多种方式解压 m3u8 数据，返回解压后的文本或 None

        每种解压方式都会验证结果是否以 #EXTM3U 开头，
        确保不会返回垃圾数据导致后续逻辑误判。
        """
        # 1. 已经是明文 m3u8
        if data[:7] == b'#EXTM3U':
            return data.decode('utf-8', errors='ignore')

        # 2. gzip 解压
        if data[:2] == b'\x1f\x8b' or ce == 'gzip':
            try:
                text = gzip.decompress(data).decode('utf-8', errors='ignore')
                if text.startswith('#EXTM3U'):
                    return text
            except Exception:
                pass

        # 3. Brotli 解压（服务器对部分CDN线路强制返回 br）
        try:
            import brotli
            text = brotli.decompress(data).decode('utf-8', errors='ignore')
            if text.startswith('#EXTM3U'):
                return text
        except ImportError:
            pass
        except Exception:
            pass

        # 4. raw deflate
        try:
            import zlib
            text = zlib.decompress(data, -15).decode('utf-8', errors='ignore')
            if text.startswith('#EXTM3U'):
                return text
        except Exception:
            pass

        # 5. 直接当文本解析
        text = data.decode('utf-8', errors='ignore')
        if text.startswith('#EXTM3U'):
            return text

        return None

    def _fetch_and_decompress(self, url):
        """请求 m3u8 URL 并解压，返回文本或 None"""
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': self.header['User-Agent'],
                'Referer': self.header['Referer'],
                # 明确排除 br，优先 gzip/deflate（播放器和代理都能处理）
                'Accept-Encoding': 'gzip, deflate',
            })
            resp = urllib.request.urlopen(req, context=self._ssl_ctx, timeout=15)
            data = resp.read()
            ce = resp.headers.get('Content-Encoding', '').lower()
            return self._decompress_m3u8(data, ce)
        except Exception:
            return None

    def _fetch_m3u8_text(self, hls_url):
        """获取 m3u8 文本，自动处理压缩和 cdnId 替代

        服务器对不同 CDN 线路返回不同的 Content-Encoding：
        - cdnId=3 从不返回 Brotli（始终明文或 gzip）→ 最稳定
        - cdnId=1/2 间歇性返回 Brotli → 需要 brotli 库，没有则解压失败

        当原始 URL 解压失败时，优先用 cdnId=3 替代（内容完全相同）。

        返回 (text, final_url) 或 (None, None)
        """
        # 先尝试原始 URL
        text = self._fetch_and_decompress(hls_url)
        if text:
            return text, hls_url

        # 原始 URL 解压失败（可能 Brotli 且没有 brotli 库）
        # 优先用 cdnId=3（最稳定），再尝试其他
        m = re.search(r'cdnId=(\d+)', hls_url)
        if m:
            original_cdn = m.group(1)
            for cdn_id in [3, 1, 2]:
                if str(cdn_id) == original_cdn:
                    continue
                alt_url = re.sub(r'cdnId=\d+', f'cdnId={cdn_id}', hls_url)
                text = self._fetch_and_decompress(alt_url)
                if text:
                    return text, alt_url

        return None, None

    def _proxy_m3u8(self, param):
        """代理 m3u8：解压（gzip/brotli/deflate）+ cdnId 替代 + 修复 key URI

        解决问题：
        1. 部分CDN返回 Brotli 压缩的 m3u8，播放器不支持 → 代理解压
        2. 没有 brotli 库时 → 自动用其他 cdnId 替代获取可解压版本
        3. key URI 是根相对路径 /api/v2/... → 转成 https://host/api/v2/...
        """
        hls_url = param.get("hls_url", "")
        # 兼容壳子传递 URL 编码参数的情况
        if hls_url and '%' in hls_url:
            hls_url = unquote(hls_url)
        if not hls_url:
            return [200, "application/vnd.apple.mpegurl", b"#EXTM3U\n#EXT-X-ENDLIST"]

        # 获取 m3u8 文本（自动处理压缩和 cdnId 替代）
        text, final_url = self._fetch_m3u8_text(hls_url)
        if not text:
            return [200, "application/vnd.apple.mpegurl", b"#EXTM3U\n#EXT-X-ENDLIST"]

        # 修复 key URI：根相对路径 → 绝对路径
        # 用最终获取成功的 URL 来计算 base
        parsed = urlparse(final_url)
        scheme_host = f"{parsed.scheme}://{parsed.netloc}"
        base_path = final_url.split("?")[0].rsplit("/", 1)[0] + "/"

        out_lines = []
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#EXT-X-KEY") and 'URI="' in s:
                m = re.search(r'URI="([^"]+)"', s)
                if m:
                    uri = m.group(1)
                    if not uri.startswith("http"):
                        if uri.startswith("/"):
                            uri = scheme_host + uri
                        else:
                            uri = base_path + uri
                    s = s.replace(m.group(0), f'URI="{uri}"')
                out_lines.append(s)
            else:
                out_lines.append(line)

        m3u8_bytes = "\n".join(out_lines).encode("utf-8")
        return [200, "application/vnd.apple.mpegurl", m3u8_bytes]

    def _proxy_media(self, raw_url):
        """代理媒体分片，补全 header"""
        try:
            req = urllib.request.Request(raw_url, headers=self.header)
            resp = urllib.request.urlopen(req, context=self._ssl_ctx, timeout=30)
            data = resp.read()
            ct = resp.headers.get("content-type") or "video/MP2T"
            return [200, ct, data]
        except Exception:
            return [200, "video/MP2T", b""]

    def destroy(self):
        pass

    def close(self):
        self.destroy()


import base64
import hashlib
import json
import re
import sys
import time
from urllib.parse import parse_qs, quote, urlsplit

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

requests.packages.urllib3.disable_warnings()

try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def init(self, extend=""):
            pass


class Spider(Spider):
    def getName(self):
        return "速搜"

    def init(self, extend=""):
        try:
            super().init(extend)
        except Exception:
            pass
        self.host = "43.248.128.251"
        self.api_ports = [2233, 22868, 18414, 24285, 16551, 21091, 15946]
        self.jx_ports = [30499, 30462, 36122, 31617, 37763]
        self.config_ports = [32589, 15281, 35673, 18216]
        self.api_prefix = "/api.php/app"
        self.jx_path = "/jx/123pan/10086.php"
        self.ua_dart = "Dart/3.9 (dart:io)"
        self.ua_android = "Mozilla/5.0 (Linux; Android 16; 23046RP50C Build/BP4A.251205.006; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/150.0.7871.47 Safari/537.36"
        self.android_id = "a59aec7097c16a63"
        self.device_id = "39AF593DF90F81DF36AA82877CF1D17E"
        self.token = "e45d2ca49c4d346df7767191d0e46858"
        self.login_uuid = "d2a84a9a3353d670af48b16ce7318840"
        self.app_id = "com.sjz.ss"
        self.jx_m = "kfOgorEp5/chYFZBRzDxRQ=="
        self.config_key = b"ahsp123456789012"
        self.jqq_key = b"opasdfghopasdfgh"
        self.pan_api = "https://api.123278.com/api/share/get"
        self.download_host = "https://download-cdn.cjjd19.com"
        self.vip_host = "https://1135-vip-download-cdn.123295.com"
        self.active_jx_url = ""
        self.active_jx_m = ""
        self.active_jqq_url = ""
        self.config_expires_at = 0
        self.session = requests.Session()
        retry = Retry(total=2, backoff_factor=0.4, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _get(self, url, headers=None, timeout=18):
        response = self.session.get(url, headers=headers or {}, timeout=timeout, verify=False)
        response.raise_for_status()
        return response.text

    def _fetch_api(self, path, auth=False):
        headers = {"User-Agent": self.ua_dart}
        if auth:
            headers["token"] = self.token
        last = None
        for port in self.api_ports:
            try:
                return self._get(f"http://{self.host}:{port}{self.api_prefix}{path}", headers)
            except Exception as error:
                last = error
        raise last or RuntimeError("API 请求失败")

    @staticmethod
    def _aes_ecb_decrypt(value, key):
        raw = base64.b64decode(value.strip())
        return unpad(AES.new(key, AES.MODE_ECB).decrypt(raw), AES.block_size).decode("utf-8")

    def _decrypt_detail(self, value):
        chars = list(value.strip())
        password = [""] * 10
        for index in range(9, -1, -1):
            position = max(len(chars) - (3 * (1 << index) + 1), 0)
            password[index] = chars.pop(position)
        key = hashlib.sha256("".join(password).encode("utf-8")).hexdigest()[:16].encode("utf-8")
        return self._aes_ecb_decrypt("".join(chars), key)

    def _decrypt_player(self, html):
        shuffled = re.search(r"const\s+shuffledBase64\s*=\s*'([^']+)'", html, re.S)
        restore = re.search(r"const\s+restoreKey\s*=\s*JSON\.parse\('([^']+)'\)", html, re.S)
        if not shuffled or not restore:
            raise ValueError("解析页参数缺失")
        source = shuffled.group(1)
        key = json.loads(restore.group(1))
        if len(source) != len(key):
            raise ValueError("解析页恢复表长度不匹配")
        result = [""] * len(source)
        for current, position in enumerate(key):
            result[position] = source[current]
        return json.loads(base64.b64decode("".join(result)).decode("utf-8"))

    def _load_parsers(self, force=False):
        if not force and self.config_expires_at > time.time() and self.active_jx_url and self.active_jqq_url:
            return
        headers = {
            "User-Agent": self.ua_dart,
            "Accept": "application/json; charset=utf-8",
            "Content-Type": "application/json; charset=utf-8",
            "token": self.token
        }
        last = None
        for port in self.config_ports:
            try:
                encrypted = self._get(f"http://{self.host}:{port}/dy.json", headers)
                root = json.loads(self._aes_ecb_decrypt(encrypted, self.config_key))
                jx_url = ""
                jx_m = ""
                jqq_url = ""
                for group in root.get("jxpath", []):
                    keyword = str(group.get("解析关键词", "")).lower()
                    for config in group.get("解析配置", []):
                        api = str(config.get("jxapi", ""))
                        if "/123pan/10086.php" in api:
                            parsed = urlsplit(api)
                            current_m = parse_qs(parsed.query).get("m", [""])[0]
                            if current_m:
                                jx_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                                jx_m = current_m
                        if keyword == "jqq" or ("/jx/api-appjx.php" in api and parse_qs(urlsplit(api).query).get("t", [""])[0] == "2233"):
                            jqq_url = api
                if jx_url:
                    self.active_jx_url = jx_url
                    self.active_jx_m = jx_m
                if jqq_url:
                    self.active_jqq_url = jqq_url
                if self.active_jx_url or self.active_jqq_url:
                    self.config_expires_at = time.time() + 600
                    return
                raise ValueError("动态解析配置为空")
            except Exception as error:
                last = error
        raise last or RuntimeError("动态解析配置加载失败")

    @staticmethod
    def _video_list(items):
        result = []
        for item in items or []:
            result.append({
                "vod_id": str(item.get("vod_id", "")),
                "vod_name": item.get("vod_name", ""),
                "vod_pic": item.get("vod_pic", ""),
                "vod_remarks": item.get("vod_remarks", "")
            })
        return result

    @staticmethod
    def _values(values):
        return [{"n": name, "v": value} for name, value in values]

    def _filters(self, type_id):
        types = {
            "1": ["剧情", "喜剧", "动作", "爱情", "科幻", "动画", "悬疑", "惊悚", "恐怖", "犯罪", "冒险", "奇幻", "战争", "历史", "传记", "家庭"],
            "2": ["剧情", "喜剧", "动作", "爱情", "玄幻", "科幻", "悬疑", "惊悚", "恐怖", "犯罪", "传记", "历史", "战争"],
            "3": ["真人秀", "脱口秀", "音乐", "歌舞", "喜剧", "竞技", "旅游", "美食", "纪实"],
            "4": ["动画", "动作", "冒险", "奇幻", "科幻", "校园", "恋爱", "搞笑", "热血", "悬疑", "治愈"]
        }
        areas = ["大陆", "美国", "香港", "台湾", "日本", "韩国", "英国", "法国", "德国", "意大利", "西班牙", "印度", "泰国", "俄罗斯"]
        years = [str(year) for year in range(2026, 2009, -1)] + ["2000-2009", "1990-1999", "1980-1989"]
        return [
            {"key": "class", "name": "类型", "init": "", "value": self._values([("全部", "")] + [(item, item) for item in types.get(type_id, [])])},
            {"key": "area", "name": "地区", "init": "", "value": self._values([("全部", "")] + [(item, item) for item in areas])},
            {"key": "year", "name": "年份", "init": "", "value": self._values([("全部", "")] + [(item, item) for item in years])},
            {"key": "by", "name": "排序", "init": "time", "value": self._values([("最新", "time"), ("热度", "hits"), ("评分", "score")])}
        ]

    def homeContent(self, filter):
        classes = [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "电视剧"},
            {"type_id": "4", "type_name": "动漫"},
            {"type_id": "3", "type_name": "综艺"}
        ]
        result = {"class": classes, "list": []}
        result["filters"] = {item["type_id"]: self._filters(item["type_id"]) for item in classes} if filter else {}
        return result

    def homeVideoContent(self):
        try:
            root = json.loads(self._fetch_api("/index_video"))
            data = root.get("list") or root.get("data") or {}
            videos = []
            for category in data.get("categories", []):
                videos.extend(self._video_list(category.get("vlist", [])))
            return {"list": videos}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
            path = f"/video?tid={quote(str(tid), safe='')}&pg={page}"
            for key in ("class", "area", "year", "by"):
                value = str((extend or {}).get(key, ""))
                if value:
                    path += f"&{key}={quote(value, safe='')}"
            root = json.loads(self._fetch_api(path))
            return {
                "page": root.get("page", page),
                "pagecount": root.get("pagecount", page),
                "limit": root.get("limit", 24),
                "total": root.get("total", 0),
                "list": self._video_list(root.get("list", []))
            }
        except Exception:
            return {"page": int(pg), "pagecount": int(pg), "limit": 24, "total": 0, "list": []}

    @staticmethod
    def _mark_jqq_line(code, name, line):
        if str(code).lower() != "jqq" and "AI" not in str(name).upper():
            return line
        result = []
        for episode in str(line).split("#"):
            if "$" in episode:
                title, play_id = episode.split("$", 1)
                result.append(f"{title}$jqq@@{play_id}")
            else:
                result.append(f"jqq@@{episode}")
        return "#".join(result)

    def detailContent(self, ids):
        try:
            vod_id = str(ids[0])
            path = f"/video_2345?id2345={quote(vod_id, safe='')}&username={quote(self.device_id, safe='')}"
            root = json.loads(self._decrypt_detail(self._fetch_api(path, auth=True)))
            data = root.get("data") or {}
            if data.get("msg"):
                return {"list": [{"vod_id": vod_id, "vod_name": data.get("msg"), "vod_play_from": "", "vod_play_url": ""}]}
            play_from = []
            play_urls = []
            for player in data.get("vod_url_with_player", []):
                line = player.get("url", "")
                if not line:
                    continue
                code = player.get("code", "")
                name = player.get("name") or code or "速搜4K"
                play_from.append(name)
                play_urls.append(self._mark_jqq_line(code, name, line))
            if not play_urls and data.get("vod_play_url"):
                play_from.append("速搜4K")
                play_urls.append(data.get("vod_play_url"))
            vod = {key: data.get(key, "") for key in [
                "vod_id", "vod_name", "vod_pic", "vod_remarks", "vod_year", "vod_area",
                "vod_actor", "vod_director", "vod_class"
            ]}
            vod["vod_id"] = vod.get("vod_id") or vod_id
            vod["vod_content"] = data.get("vod_content") or data.get("vod_blurb") or ""
            vod["vod_play_from"] = "$$$".join(play_from)
            vod["vod_play_url"] = "$$$".join(play_urls)
            return {"list": [vod]}
        except Exception as error:
            sys.stderr.write(f"detailContent error: {error}\n")
            return {"list": []}

    def searchContent(self, key, quick, pg=1):
        try:
            page = int(pg)
            root = json.loads(self._fetch_api(f"/search?pg={page}&text={quote(str(key), safe='')}"))
            videos = self._video_list(root.get("list", []))
            return {"page": page, "pagecount": page + 1 if videos else page, "limit": 24, "total": len(videos), "list": videos}
        except Exception:
            return {"list": []}

    def _resolve_share(self, video_id):
        headers = {"User-Agent": self.ua_android, "X-Requested-With": self.app_id}
        candidates = []
        try:
            self._load_parsers(False)
            if self.active_jx_url and self.active_jx_m:
                candidates.append((self.active_jx_url, self.active_jx_m))
        except Exception:
            pass
        candidates.extend((f"http://{self.host}:{port}{self.jx_path}", self.jx_m) for port in self.jx_ports)
        last = None
        for base_url, current_m in candidates:
            try:
                url = f"{base_url}?t={quote(self.token, safe='')}&m={quote(current_m, safe='')}&url={quote(str(video_id), safe='')}"
                root = self._decrypt_player(self._get(url, headers))
                data = root.get("data") or {}
                if root.get("code") == 200 and data:
                    return data
                raise ValueError(root.get("msg") or "解析失败")
            except Exception as error:
                last = error
        raise last or RuntimeError("123Pan 解析失败")

    def _real_video(self, video_id):
        data = self._resolve_share(video_id)
        timestamp = int(time.time())
        auth_key = f"{timestamp}-{timestamp - 973591068}-{self.login_uuid}"
        params = (
            f"auth-key={quote(auth_key, safe='')}&limit=1&next=1&orderBy=share_id&orderDirection=desc&SharePwd="
            f"&ParentFileId={quote(str(data.get('wjjfxid', '')), safe='')}&shareKey={quote(str(data.get('wjfxurlid', '')), safe='')}"
            "&Page=1&event=homeListFile&operateType=4&OrderId=&superAdmin=null"
        )
        headers = {
            "User-Agent": self.ua_android,
            "platform": "android",
            "app-version": "72",
            "x-app-version": "2.4.10",
            "x-channel": "1002",
            "loginuuid": self.login_uuid,
            "devicename": "Android Device",
            "devicetype": "2510DRK44C",
            "osversion": "Android_16"
        }
        root = json.loads(self._get(f"{self.pan_api}?{params}", headers))
        info = (root.get("data") or {}).get("InfoList") or []
        if root.get("code") != 0 or not info:
            raise ValueError(root.get("message") or "123Pan 返回为空")
        direct = info[0].get("DownloadUrl", "").replace(self.download_host, self.vip_host)
        direct = re.sub(r"(?i)(filename=[^&]*?)\.(jpg|jpeg|png|webp)(?=&|$)", r"\1.mp4", direct)
        if "auto_redirect=" not in direct:
            direct += ("&" if "?" in direct else "?") + "auto_redirect=1"
        if "ndcp=" not in direct:
            direct += "&ndcp=1"
        return direct

    def _jqq_request_url(self, video_id):
        self._load_parsers(False)
        parts = str(video_id).split("&")
        url = self.active_jqq_url + quote(parts[0], safe="")
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                url += f"&{quote(key, safe='')}={quote(value, safe='')}"
            else:
                url += f"&{quote(part, safe='')}"
        return url

    def _resolve_jqq(self, video_id):
        last = None
        for attempt in range(2):
            try:
                if attempt:
                    self.config_expires_at = 0
                    self._load_parsers(True)
                encrypted = self._get(self._jqq_request_url(video_id), {
                    "User-Agent": self.ua_android,
                    "Accept": "application/json, text/plain, */*"
                })
                root = json.loads(encrypted) if encrypted.lstrip().startswith("{") else json.loads(self._aes_ecb_decrypt(encrypted, self.jqq_key))
                if root.get("code") == 200 and root.get("url"):
                    return root["url"]
                raise ValueError(root.get("msg") or "AI 解析失败")
            except Exception as error:
                last = error
                self.active_jqq_url = ""
        raise last or RuntimeError("AI 解析失败")

    def playerContent(self, flag, id, vipFlags):
        try:
            is_jqq = str(id).startswith("jqq@@") or "AI" in str(flag).upper() or str(flag).lower() == "jqq"
            play_id = str(id)[5:] if str(id).startswith("jqq@@") else str(id)
            url = self._resolve_jqq(play_id) if is_jqq else self._real_video(play_id)
            return {"parse": 0, "jx": 0, "url": url, "header": {"User-Agent": self.ua_android}}
        except Exception as error:
            sys.stderr.write(f"playerContent error: {error}\n")
            return {"parse": 0, "jx": 0, "url": ""}

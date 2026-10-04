# coding=utf-8
#!/usr/bin/python
"""
瓜子[影] - 按 Guazi.java 修复版
主要对齐：
1) 动态设备注册/登录/token 刷新（不再硬编码 token）
2) AES key/iv + RSA 公钥加密 keys
3) 签名 MD5 大写
4) 请求头 Version/PackageName/Ver/api-ver/deviceId/code
5) 播放源按画质分组
6) 多 API host 探测
"""
import base64
import hashlib
import json
import os
import random
import re
import sys
import time
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad

sys.path.append('..')
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    RSA_PUBLIC_KEY = (
        "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDUM5+/y8sPsWkd1/RQS64X259E"
        "UwxFXFE5HlA65MqrxnPs0JqoSRojSDy5QhwvROlaD6TwRQHKMY2OAZ6SnQeUJsCh"
        "TEFIR9qUkwrs3/MVUMxjsv6JS6Oe/juclyJGTgVmDhB55EafXsD0SQYVj/QXXsxR"
        "6ewR5E2kL52yAAD4yQIDAQAB"
    )
    RSA_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGAe6hKrWLi1zQmjTT1
ozbE4QdFeJGNxubxld6GrFGximxfMsMB6BpJhpcTouAqywAFppiKetUBBbXwYsYU
1wNr648XVmPmCMCy4rY8vdliFnbMUj086DU6Z+/oXBdWU3/b1G0DN3E9wULRSwcK
ZT3wj/cCI1vsCm3gj2R5SqkA9Y0CAwEAAQKBgAJH+4CxV0/zBVcLiBCHvSANm0l7
HetybTh/j2p0Y1sTXro4ALwAaCTUeqdBjWiLSo9lNwDHFyq8zX90+gNxa7c5EqcW
V9FmlVXr8VhfBzcZo1nXeNdXFT7tQ2yah/odtdcx+vRMSGJd1t/5k5bDd9wAvYdI
DblMAg+wiKKZ5KcdAkEA1cCakEN4NexkF5tHPRrR6XOY/XHfkqXxEhMqmNbB9U34
saTJnLWIHC8IXys6Qmzz30TtzCjuOqKRRy+FMM4TdwJBAJQZFPjsGC+RqcG5UvVM
iMPhnwe/bXEehShK86yJK/g/UiKrO87h3aEu5gcJqBygTq3BBBoH2md3pr/W+hUM
WBsCQQChfhTIrdDinKi6lRxrdBnn0Ohjg2cwuqK5zzU9p/N+S9x7Ck8wUI53DKm8
jUJE8WAG7WLj/oCOWEh+ic6NIwTdAkEAj0X8nhx6AXsgCYRql1klbqtVmL8+95KZ
K7PnLWG/IfjQUy3pPGoSaZ7fdquG8bq8oyf5+dzjE/oTXcByS+6XRQJAP/5ciy1b
L3NhUhsaOVy55MHXnPjdcTX0FaLi+ybXZIfIQ2P4rb19mVq1feMbCXhz+L1rG8oa
t5lYKfpe8k83ZA==
-----END RSA PRIVATE KEY-----"""

    API_HOSTS = [
        "https://apinew.uozvr.com",
        "https://api.w32z7vtd.com",
        "https://api.6a7nnf7.com",
        "https://api.umygrx3.com",
        "https://api.rmedphk.com",
    ]
    AES_KEY = "OITxa5OqAYjhswxx"
    AES_IV = "rCMNwZASNBKZ8mXV"
    DEVICE_OLD_KEY = "aLFBMWpxBrIDAD1Si/KVvm41"
    AUTH_FILE = "/tmp/guazi_auth.json"
    PLAY_UA = "Lavf/57.83.100"
    SUB_MAP = {
        "1": "5",
        "2": "12",
        "3": "30",
        "4": "22",
        "64": "",
    }

    def __init__(self):
        self.name = "瓜子"
        self.host = self.API_HOSTS[0]
        self.token = ""
        self.token_id = ""
        self.device_id = ""
        self.device_key = ""
        self.registered = False
        self.token_ready = False
        self.cache = {}
        self.cache_timeout = 300
        self.header = {}

    def getName(self):
        return self.name

    def init(self, extend=""):
        self.host = self.find_available_host()
        self.load_auth()
        try:
            self.ensure_token()
        except Exception as e:
            print(f"初始化 token 失败: {e}")
        self.header = self.build_headers()

    def find_available_host(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        for host in self.API_HOSTS:
            try:
                resp = None
                if hasattr(self, "fetch"):
                    resp = self.fetch(host, headers=headers, timeout=3)
                elif hasattr(self, "get"):
                    resp = self.get(host, headers=headers, timeout=3)
                else:
                    return host
                code = getattr(resp, "status_code", 0) or 0
                if 200 <= int(code) < 300:
                    return host
            except Exception:
                continue
        return self.API_HOSTS[0]

    def build_headers(self):
        return {
            "User-Agent": self.PLAY_UA,
            "code": "GZ0369",
            "deviceId": self.device_id or "",
            "lang": "zh_cn",
            "Cache-Control": "no-cache",
            "Content-Type": "application/x-www-form-urlencoded",
            "Version": "2604028",
            "PackageName": "com.ae06aebdbb.y286327f5a.ofe849883320260517",
            "Ver": "3.0.3.2",
            "api-ver": "3.0.3.2",
            "Accept-Encoding": "gzip",
        }

    def homeContent(self, filter):
        classes = [
            {"type_name": "电影", "type_id": "1"},
            {"type_name": "国产剧", "type_id": "2"},
            {"type_name": "动漫", "type_id": "4"},
            {"type_name": "短剧", "type_id": "64"},
            {"type_name": "综艺", "type_id": "3"},
            {"type_name": "海外剧", "type_id": "5"},
        ]
        filters = {}
        for cate in classes:
            tid = cate["type_id"]
            filters[tid] = [
                {
                    "key": "area",
                    "name": "地区",
                    "value": [
                        {"n": "全部", "v": "0"},
                        {"n": "大陆", "v": "大陆"},
                        {"n": "香港", "v": "香港"},
                        {"n": "台湾", "v": "台湾"},
                        {"n": "美国", "v": "美国"},
                        {"n": "韩国", "v": "韩国"},
                        {"n": "日本", "v": "日本"},
                        {"n": "英国", "v": "英国"},
                        {"n": "法国", "v": "法国"},
                        {"n": "泰国", "v": "泰国"},
                        {"n": "印度", "v": "印度"},
                        {"n": "其他", "v": "其他"},
                    ],
                },
                {
                    "key": "year",
                    "name": "年份",
                    "value": [
                        {"n": "全部", "v": "0"},
                        {"n": "2026", "v": "2026"},
                        {"n": "2025", "v": "2025"},
                        {"n": "2024", "v": "2024"},
                        {"n": "2023", "v": "2023"},
                        {"n": "2022", "v": "2022"},
                        {"n": "2021", "v": "2021"},
                        {"n": "2020", "v": "2020"},
                        {"n": "2019", "v": "2019"},
                        {"n": "2018", "v": "2018"},
                        {"n": "2017", "v": "2017"},
                        {"n": "2016", "v": "2016"},
                        {"n": "2015", "v": "2015"},
                        {"n": "更早", "v": "2004"},
                    ],
                },
                {
                    "key": "sort",
                    "name": "排序",
                    "value": [
                        {"n": "最新", "v": "d_id"},
                        {"n": "最热", "v": "d_hits"},
                        {"n": "推荐", "v": "d_score"},
                    ],
                },
            ]
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        videos = []
        try:
            data = self.api_request("/App/IndexList/index", {"pid": "1"})
            lst = data.get("list") if isinstance(data, dict) else None
            if isinstance(lst, list) and len(lst) > 1:
                for item in lst[1:]:
                    if isinstance(item, dict):
                        videos.extend(self.parse_vod_list(item))
        except Exception as e:
            print(f"首页推荐失败: {e}")
        return {"list": videos}

    def categoryContent(self, tid, pg, filter, extend):
        videos = []
        try:
            ext = self.decode_ext(extend)
            body = {
                "tid": str(tid),
                "page": str(pg),
                "pageSize": "30",
                "area": str(ext.get("area", "0") or "0"),
                "year": str(ext.get("year", "0") or "0"),
                "sort": str(ext.get("sort", "d_id") or "d_id"),
                "sub": str(ext.get("sub", self.SUB_MAP.get(str(tid), "0"))),
            }
            data = self.api_request("/App/IndexList/indexList", body)
            videos = self.parse_vod_list(data)
        except Exception as e:
            print(f"获取分类内容失败: {e}")
        return {
            "list": videos,
            "page": int(pg),
            "pagecount": 9999,
            "limit": 30,
            "total": 999999,
        }

    def detailContent(self, ids):
        try:
            self.ensure_token()
            vod_id = str(ids[0]).split("/")[0]

            params1 = {
                "token_id": self.token_id,
                "vod_id": vod_id,
                "mobile_time": str(int(time.time())),
                "token": self.token,
            }
            params2 = {
                "vurl_cloud_id": "2",
                "vod_d_id": vod_id,
            }
            play_info = self.api_request("/App/IndexPlay/playInfo", params1)
            vurl_info = self.api_request("/App/Resource/Vurl/show", params2)

            vod_info = (play_info or {}).get("vodInfo") or {}
            if not vod_info:
                return {"list": []}

            quality_episodes = {}
            quality_order = []
            lst = (vurl_info or {}).get("list") or []
            if isinstance(lst, list):
                for i, item in enumerate(lst):
                    play_obj = (item or {}).get("play") or {}
                    ep_name = vod_info.get("vod_name", "") if len(lst) == 1 else str(i + 1)
                    if not isinstance(play_obj, dict):
                        continue
                    for quality, ep in play_obj.items():
                        if not isinstance(ep, dict):
                            continue
                        param = ep.get("param") or ""
                        if not param:
                            continue
                        if quality not in quality_episodes:
                            quality_episodes[quality] = []
                            quality_order.append(quality)
                        quality_episodes[quality].append(f"{ep_name}${param}||{quality}")

            quality_order.sort(key=self.quality_value, reverse=True)
            play_from = []
            play_url = []
            for q in quality_order:
                play_from.append(q)
                play_url.append("#".join(quality_episodes[q]))

            video = {
                "vod_id": vod_id,
                "vod_name": vod_info.get("vod_name", ""),
                "vod_pic": vod_info.get("vod_pic", ""),
                "vod_year": vod_info.get("vod_year", ""),
                "vod_area": vod_info.get("vod_area", ""),
                "vod_actor": vod_info.get("vod_actor", ""),
                "vod_director": vod_info.get("vod_director", ""),
                "vod_content": str(vod_info.get("vod_use_content", "")).replace("\u3000", "\n").strip(),
                "vod_play_from": "$$$".join(play_from) if play_from else "瓜子",
                "vod_play_url": "$$$".join(play_url),
            }
            return {"list": [video]}
        except Exception as e:
            print(f"获取详情失败: {e}")
            return {"list": []}

    def searchContent(self, key, quick, pg=1):
        videos = []
        try:
            data = self.api_request(
                "/App/Index/findMoreVod",
                {"keywords": key, "order_val": "1", "page": str(pg)},
            )
            videos = self.parse_vod_list(data)
        except Exception as e:
            print(f"搜索失败: {e}")
        return {
            "list": videos,
            "page": int(pg),
            "pagecount": 9999,
            "limit": 30,
            "total": 999999,
        }

    def playerContent(self, flag, id, vipFlags):
        try:
            parts = str(id).split("||")
            param_str = parts[0]
            resolution = parts[1] if len(parts) > 1 else (flag or "")

            param_map = {}
            for pair in param_str.split("&"):
                if "=" not in pair:
                    continue
                k, v = pair.split("=", 1)
                if k == "vod_d_id":
                    k = "vod_id"
                param_map[k] = v
            if resolution:
                param_map["resolution"] = resolution

            data = self.api_request("/App/Resource/VurlDetail/showOne", param_map)
            url = (data or {}).get("url", "") if isinstance(data, dict) else ""
            headers = {
                "User-Agent": self.PLAY_UA,
                "Referer": "http://WJiZxLXA2.com/",
                "Accept-Encoding": "gzip",
            }
            return {
                "parse": 0,
                "playUrl": "",
                "url": url or "",
                "header": headers,
            }
        except Exception as e:
            print(f"播放解析失败: {e}")
            return {"parse": 0, "playUrl": "", "url": ""}

    def isVideoFormat(self, url):
        video_formats = [".m3u8", ".mp4", ".avi", ".mkv", ".flv", ".ts"]
        return any(str(url).lower().endswith(fmt) for fmt in video_formats)

    def manualVideoCheck(self):
        pass

    def localProxy(self, params):
        return None

    # ---------------- auth ----------------
    def load_auth(self):
        data = {}
        try:
            if os.path.exists(self.AUTH_FILE):
                with open(self.AUTH_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
        except Exception:
            data = {}

        self.token = str(data.get("token", "") or "")
        self.token_id = str(data.get("token_id", "") or "")
        self.device_id = str(data.get("device_id", "") or "")
        self.device_key = str(data.get("device_key", "") or "")
        self.registered = bool(data.get("registered", bool(self.token)))
        self.token_ready = False

        if self.device_id and self.device_key:
            return

        self.device_id = str(864150060000000 + random.randint(0, 9999))
        self.device_key = os.urandom(20).hex().upper()
        self.token = ""
        self.token_id = ""
        self.registered = False
        self.save_auth()

    def save_auth(self):
        try:
            with open(self.AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "token": self.token,
                        "token_id": self.token_id,
                        "device_id": self.device_id,
                        "device_key": self.device_key,
                        "registered": self.registered,
                    },
                    f,
                    ensure_ascii=False,
                )
        except Exception as e:
            print(f"保存 auth 失败: {e}")

    def ensure_token(self):
        if self.token_ready and self.token:
            return
        if not self.token:
            if self.registered:
                self.sign_in()
            else:
                self.sign_up()
        try:
            self.apply_auth(
                self.api_request(
                    "/App/Authentication/Authenticator/refresh",
                    {},
                    auth_path=True,
                    retry=0,
                )
            )
        except Exception:
            if not self.registered:
                raise
            self.sign_in()
        self.token_ready = True
        self.header = self.build_headers()

    def sign_up(self):
        result = self.api_request(
            "/App/Authentication/Device/signUp",
            {
                "new_key": self.device_key,
                "old_key": self.DEVICE_OLD_KEY,
                "phone_type": 1,
                "code": "",
            },
            auth_path=True,
            retry=0,
        )
        self.apply_auth(result)
        self.registered = True
        self.save_auth()

    def sign_in(self):
        result = self.api_request(
            "/App/Authentication/Device/signIn",
            {
                "new_key": self.device_key,
                "old_key": self.DEVICE_OLD_KEY,
            },
            auth_path=True,
            retry=0,
        )
        self.apply_auth(result)

    def apply_auth(self, result):
        if not isinstance(result, dict):
            raise Exception(f"Token 获取失败: {result}")
        new_token = str(result.get("token", "") or "")
        if not new_token:
            raise Exception(f"Token 获取失败: {result}")
        self.token = new_token
        new_token_id = str(result.get("app_user_id", "") or "")
        if new_token_id:
            self.token_id = new_token_id
        self.save_auth()

    # ---------------- crypto / request ----------------
    def aes_encrypt(self, text, key, iv):
        cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
        encrypted = cipher.encrypt(pad(text.encode("utf-8"), AES.block_size))
        return encrypted.hex().upper()

    def aes_decrypt(self, hex_text, key, iv):
        cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
        decrypted = unpad(cipher.decrypt(bytes.fromhex(hex_text)), AES.block_size)
        return decrypted.decode("utf-8")

    def rsa_encrypt(self, text):
        key = RSA.import_key(base64.b64decode(self.RSA_PUBLIC_KEY))
        cipher = PKCS1_v1_5.new(key)
        encrypted = cipher.encrypt(text.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")

    def rsa_decrypt(self, encrypted_b64):
        key = RSA.import_key(self.RSA_PRIVATE_KEY)
        cipher = PKCS1_v1_5.new(key)
        decrypted = cipher.decrypt(base64.b64decode(encrypted_b64), None)
        if decrypted is None:
            raise Exception("RSA 解密失败")
        return decrypted.decode("utf-8")

    def md5_upper(self, text):
        return hashlib.md5(text.encode("utf-8")).hexdigest().upper()

    def api_request(self, path, params=None, auth_path=None, retry=0):
        if params is None:
            params = {}
        if auth_path is None:
            auth_path = str(path).startswith("/App/Authentication/")
        if not auth_path:
            self.ensure_token()

        request_params = dict(params)
        if "token" in request_params:
            request_params["token"] = self.token
        if "token_id" in request_params:
            request_params["token_id"] = self.token_id

        json_params = json.dumps(request_params, ensure_ascii=False, separators=(",", ":"))
        # Java Json.toJson 通常不强制 separators；服务端一般容忍空格
        # 为兼容性，用默认 dumps 更接近常见 JSON
        json_params = json.dumps(request_params, ensure_ascii=False)
        request_key = self.aes_encrypt(json_params, self.AES_KEY, self.AES_IV)
        t = str(int(time.time()))
        keys = self.rsa_encrypt(json.dumps({"iv": self.AES_IV, "key": self.AES_KEY}, ensure_ascii=False, separators=(",", ":")))

        sign_str = (
            f"token_id=,token={self.token},phone_type=1,request_key={request_key},"
            f"app_id=1,time={t},keys={keys}*&zvdvdvddbfikkkumtmdwqppp?|4Y!s!2br"
        )
        signature = self.md5_upper(sign_str)

        body = {
            "token": self.token,
            "token_id": "",
            "phone_type": "1",
            "time": t,
            "phone_model": "xiaomi-25031",
            "keys": keys,
            "request_key": request_key,
            "signature": signature,
            "app_id": "1",
            "ad_version": "1",
        }

        headers = self.build_headers()
        url = f"{self.host}{path}"
        resp = self.post(url, headers=headers, data=body, timeout=22)
        status = getattr(resp, "status_code", 0)
        if int(status) != 200:
            raise Exception(f"API HTTP {status}: {path}")

        try:
            response = resp.json()
        except Exception:
            text = getattr(resp, "text", "") or ""
            response = json.loads(text)

        code = response.get("code")
        if code is not None and int(code) != 200:
            if retry < 1 and not auth_path:
                self.token_ready = False
                self.ensure_token()
                return self.api_request(path, params, auth_path=auth_path, retry=retry + 1)
            raise Exception(f"请求失败: {response}")

        data = response.get("data") or {}
        encrypted_data = data.get("response_key") or ""
        key_data = data.get("keys") or ""
        if not encrypted_data or not key_data:
            # 某些 auth 接口可能直接返回
            if isinstance(data, dict) and data.get("token"):
                return data
            raise Exception(f"响应缺少加密字段: {response}")

        key_info = json.loads(self.rsa_decrypt(key_data))
        decrypted = self.aes_decrypt(encrypted_data, key_info["key"], key_info["iv"])
        return json.loads(decrypted)

    def parse_vod_list(self, data):
        videos = []
        if not isinstance(data, dict) or "list" not in data:
            return videos
        for item in data.get("list") or []:
            if not isinstance(item, dict):
                continue
            remarks = str(item.get("vod_scroe", "") or item.get("vod_score", "") or "")
            continu = str(item.get("vod_continu", "") or "0")
            total = str(item.get("d_total", "") or "0")
            if total != "0" and continu != "0":
                if continu == total:
                    remarks = f"全{total}集"
                else:
                    remarks = f"更新至{continu}集"
            elif item.get("vod_year"):
                remarks = str(item.get("vod_year"))
            videos.append(
                {
                    "vod_id": str(item.get("vod_id", "")),
                    "vod_name": item.get("vod_name", ""),
                    "vod_pic": item.get("vod_pic", ""),
                    "vod_remarks": remarks,
                }
            )
        return videos

    def quality_value(self, quality):
        if not quality:
            return 0
        q = str(quality).upper()
        if "4K" in q or "2160" in q:
            return 2160
        if "1080" in q:
            return 1080
        if "720" in q:
            return 720
        if "480" in q:
            return 480
        if "360" in q:
            return 360
        nums = re.findall(r"\d+", q)
        return int(nums[0]) if nums else 0

    def decode_ext(self, raw):
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        attempts = [str(raw)]
        try:
            attempts.append(base64.b64decode(str(raw)).decode("utf-8"))
        except Exception:
            pass
        try:
            padded = str(raw) + "=" * ((4 - len(str(raw)) % 4) % 4)
            attempts.append(base64.urlsafe_b64decode(padded).decode("utf-8"))
        except Exception:
            pass
        for item in attempts:
            try:
                parsed = json.loads(item)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return {}


if __name__ == "__main__":
    pass
